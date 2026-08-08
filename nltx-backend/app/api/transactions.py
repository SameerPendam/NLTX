"""
NLTX Transactions API Routes
POST /api/transactions/send      — Execute a send transaction
POST /api/transactions/undo/{id} — Undo a transaction within 30s
GET  /api/transactions/          — List user transactions
GET  /api/transactions/{id}      — Get single transaction
GET  /api/transactions/stats     — Spending summary
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.models.database import User, Transaction, TxType, TxStatus, Network, SpendingLimit
from app.services.auth_service import get_current_active_user
from app.services.blockchain_service import get_blockchain_service, get_price_service
from app.services.nlp_service import get_nlp_service
from app.services.security_service import get_security_service
from app.services.testnet_service import get_testnet_service
from app.services.account_wallets import (
    ensure_default_wallets,
    get_primary_wallet,
    get_primary_wallet_address,
    resolve_transfer_recipient,
)
from app.config import get_settings

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])
settings = get_settings()


def _parse_network(network: str) -> Network:
    try:
        return Network(network.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid network. Use: ethereum, polygon, solana",
        )


# ===== SCHEMAS =====
class SendRequest(BaseModel):
    to_username: Optional[str] = None
    to_address: Optional[str] = None
    amount: float
    token: str = "USDT"
    network: str = "polygon"
    memo: Optional[str] = None
    nlp_command: Optional[str] = None    # Original NL command if from NLP
    confirmed: bool = False              # Client must confirm after preview
    otp_code: Optional[str] = None       # 2FA code if needed

class SendResponse(BaseModel):
    transaction_id: str
    status: str
    tx_hash: Optional[str]
    amount: float
    token: str
    to_username: Optional[str]
    undo_expires_at: str
    gas_usd: float
    message: str
    explorer_url: Optional[str] = None
    is_real_tx: Optional[bool] = False

class SwapRequest(BaseModel):
    from_token: str
    to_token: str
    amount: float
    network: str = "polygon"
    nlp_command: Optional[str] = None
    confirmed: bool = False
    otp_code: Optional[str] = None

@router.post("/swap")
async def swap_transaction(
    payload: SwapRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Execute a token swap (simulated)."""
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Swap must be confirmed by user")
    
    # Simulate swap execution
    from_price_data = await get_price_service().get_price(payload.from_token)
    to_price_data = await get_price_service().get_price(payload.to_token)
    
    from_price = from_price_data.get("price_usd", 1.0)
    to_price = to_price_data.get("price_usd", 1.0)
    
    usd_value = payload.amount * from_price

    # 2FA Check
    limit = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
    threshold = limit.require_2fa_above if limit else 500.0
    if current_user.two_fa_enabled or usd_value > threshold:
        if not payload.otp_code:
            raise HTTPException(status_code=403, detail="2FA_REQUIRED")
        if not get_security_service().verify_2fa(current_user.id, payload.otp_code):
            raise HTTPException(status_code=403, detail="Invalid 2FA code")

    to_amount = usd_value / to_price if to_price > 0 else 0
    
    # Store in DB
    tx = Transaction(
        user_id=current_user.id,
        tx_type=TxType.SWAP,
        status=TxStatus.CONFIRMED,
        network=payload.network,
        amount=payload.amount,
        token=payload.from_token,
        usd_value=usd_value,
        memo=f"Swap {payload.amount} {payload.from_token} for ~{to_amount:.4f} {payload.to_token}",
        nlp_command=payload.nlp_command,
        executed_at=datetime.utcnow(),
        confirmed_at=datetime.utcnow()
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    
    return {
        "status": "confirmed",
        "transaction_id": tx.id,
        "from_token": payload.from_token,
        "to_token": payload.to_token,
        "from_amount": payload.amount,
        "to_amount": round(to_amount, 6),
        "usd_value": round(usd_value, 2),
        "message": f"✅ Successfully swapped {payload.amount} {payload.from_token} for {to_amount:.6f} {payload.to_token}"
    }


# ===== ROUTES =====
@router.post("/send", response_model=SendResponse)
async def send_transaction(
    payload: SendRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Execute a blockchain send transaction.
    - Validates spending limits
    - Runs fraud detection
    - Submits to blockchain (demo mode: simulated)
    - Starts 30s undo countdown
    """
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Transaction must be confirmed by user before execution")

    if not payload.to_username and not payload.to_address:
        raise HTTPException(status_code=400, detail="Recipient (username or address) is required")

    net = _parse_network(payload.network)
    ensure_default_wallets(db, current_user)
    bc = get_blockchain_service()

    try:
        to_address, resolved_recipient_username = resolve_transfer_recipient(
            db,
            to_username=payload.to_username,
            to_address=payload.to_address,
            network=net,
            resolve_ens=bc.resolve_ens,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from_address = get_primary_wallet_address(db, current_user.id, net)
    if not from_address:
        raise HTTPException(status_code=400, detail="No wallet configured for this network")

    display_to_username = resolved_recipient_username or payload.to_username

    # 2FA Check
    price_svc = get_price_service()
    price_data = await price_svc.get_price(payload.token)
    usd_value = payload.amount * price_data.get("price_usd", 1.0)

    limit = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
    threshold = limit.require_2fa_above if limit else 500.0
    if current_user.two_fa_enabled or usd_value > threshold:
        if not payload.otp_code:
            raise HTTPException(status_code=403, detail="2FA_REQUIRED")
        if not get_security_service().verify_2fa(current_user.id, payload.otp_code):
            raise HTTPException(status_code=403, detail="Invalid 2FA code")

    # Fraud check
    nlp_svc = get_nlp_service()
    fraud_result = nlp_svc.run_fraud_checks(payload.amount, to_address or "")
    if fraud_result["recommendation"] == "block":
        raise HTTPException(status_code=403, detail=f"Transaction blocked by fraud detection. Reason: {fraud_result['flags']}")

    # Spending limit check
    limit = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
    if limit:
        price_svc = get_price_service()
        price_data = await price_svc.get_price(payload.token)
        usd_value = payload.amount * price_data.get("price_usd", 1.0)

        if usd_value > limit.single_tx_max:
            raise HTTPException(status_code=400, detail=f"Exceeds single tx limit of ${limit.single_tx_max:,.0f}")
        if limit.daily_used + usd_value > limit.daily_limit:
            raise HTTPException(status_code=400, detail=f"Exceeds daily limit of ${limit.daily_limit:,.0f}")
        if limit.monthly_used + usd_value > limit.monthly_limit:
            raise HTTPException(status_code=400, detail=f"Exceeds monthly limit of ${limit.monthly_limit:,.0f}")
    else:
        usd_value = payload.amount  # Fallback

    # ─── Execute on testnet or simulate ──────────────────────────────────────
    testnet = get_testnet_service()
    tx_result = None

    if payload.token.upper() == "ETH" and net in (Network.ETHEREUM, Network.POLYGON):
        # Real testnet transaction
        from_wallet = get_primary_wallet(db, current_user.id, net)
        testnet_net = from_wallet.testnet_network if from_wallet else "sepolia"
        enc_key = from_wallet.encrypted_key if from_wallet else None

        if enc_key:
            tx_result = testnet.send_eth(
                from_encrypted_key = enc_key,
                to_address         = to_address,
                amount_eth         = payload.amount,
                network            = testnet_net,
                memo               = payload.memo or ""
            )
            if tx_result["status"] == "error":
                raise HTTPException(status_code=400, detail=tx_result["error"])
        else:
            # Wallet exists but no key (old user before testnet upgrade)
            tx_result = testnet.simulate(from_address, to_address, payload.amount, payload.token, payload.network)
    else:
        # USDT, USDC, MATIC, SOL — simulate (testnet ERC-20 transfers need faucet tokens)
        tx_result = testnet.simulate(from_address, to_address, payload.amount, payload.token, payload.network)

    # ─── Store transaction in DB ──────────────────────────────────────────────
    undo_expires = datetime.utcnow() + timedelta(seconds=settings.UNDO_WINDOW_SECONDS)
    tx = Transaction(
        user_id       = current_user.id,
        tx_type       = TxType.SEND,
        status        = TxStatus.CONFIRMED if tx_result["status"] in ("confirmed", "simulated") else TxStatus.PENDING,
        network       = net,
        from_address  = tx_result.get("from") or from_address,
        to_address    = to_address,
        to_username   = display_to_username,
        amount        = payload.amount,
        token         = payload.token,
        usd_value     = usd_value,
        gas_fee_usd   = tx_result.get("gas_usd", 0),
        memo          = payload.memo,
        tx_hash       = tx_result.get("tx_hash"),
        block_number  = tx_result.get("block_number"),
        confirmations = tx_result.get("confirmations", 0),
        nlp_command   = payload.nlp_command,
        undo_expires_at = undo_expires,
        executed_at   = datetime.utcnow(),
        confirmed_at  = datetime.utcnow(),
    )
    db.add(tx)

    # Update spending usage
    if limit:
        limit.daily_used += usd_value
        limit.monthly_used += usd_value

    db.commit()
    db.refresh(tx)

    is_real_tx = tx_result.get("demo_mode") is False
    explorer_url = tx_result.get("explorer_url", "")
    demo_note = "" if is_real_tx else " (testnet simulated — fund wallet with Sepolia ETH for real tx)"

    return SendResponse(
        transaction_id  = tx.id,
        status          = tx.status.value,
        tx_hash         = tx.tx_hash,
        amount          = tx.amount,
        token           = tx.token,
        to_username     = tx.to_username,
        undo_expires_at = undo_expires.isoformat(),
        gas_usd         = tx.gas_fee_usd,
        message         = (
            f"✅ Sent {payload.amount} {payload.token} to {display_to_username or to_address}.\n"
            f"Hash: {tx.tx_hash}\n"
            + (f"Explorer: {explorer_url}\n" if explorer_url else "")
            + f"You have 30s to undo.{demo_note}"
        )
    )


@router.post("/undo/{transaction_id}")
async def undo_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Cancel a transaction within the 30-second undo window."""
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id
    ).first()

    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.status == TxStatus.UNDONE:
        raise HTTPException(status_code=400, detail="Transaction already undone")
    if tx.undo_expires_at and datetime.utcnow() > tx.undo_expires_at:
        raise HTTPException(status_code=400, detail="Undo window has expired (30s limit)")

    tx.status = TxStatus.UNDONE
    db.commit()
    return {"message": f"✅ Transaction {transaction_id[:8]}... has been successfully undone!", "status": "undone"}


@router.get("/")
async def list_transactions(
    skip: int = 0,
    limit: int = 20,
    tx_type: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List all transactions for the current user with optional filters."""
    query = db.query(Transaction).filter(Transaction.user_id == current_user.id)
    if tx_type:
        query = query.filter(Transaction.tx_type == tx_type)
    if status:
        query = query.filter(Transaction.status == status)

    total = query.count()
    txs = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "total": total,
        "transactions": [
            {
                "id": tx.id,
                "type": tx.tx_type.value if tx.tx_type else None,
                "status": tx.status.value if tx.status else None,
                "network": tx.network.value if tx.network else None,
                "amount": tx.amount,
                "token": tx.token,
                "usd_value": tx.usd_value,
                "to_username": tx.to_username,
                "to_address": tx.to_address,
                "memo": tx.memo,
                "tx_hash": tx.tx_hash,
                "gas_fee_usd": tx.gas_fee_usd,
                "can_undo": (
                    tx.status == TxStatus.CONFIRMED and
                    tx.undo_expires_at and
                    datetime.utcnow() < tx.undo_expires_at
                ),
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in txs
        ]
    }


@router.get("/stats")
async def transaction_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Spending summary for the past 30 days."""
    since = datetime.utcnow() - timedelta(days=30)
    txs = db.query(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.created_at >= since,
        Transaction.status == TxStatus.CONFIRMED
    ).all()

    sent = sum(t.usd_value or 0 for t in txs if t.tx_type == TxType.SEND)
    received = sum(t.usd_value or 0 for t in txs if t.tx_type == TxType.RECEIVE)
    gas_spent = sum(t.gas_fee_usd or 0 for t in txs)

    return {
        "period_days": 30,
        "total_sent_usd": round(sent, 2),
        "total_received_usd": round(received, 2),
        "net_flow_usd": round(received - sent, 2),
        "total_gas_usd": round(gas_spent, 4),
        "transaction_count": len(txs),
        "avg_tx_usd": round(sent / len(txs), 2) if txs else 0,
    }


@router.get("/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get a single transaction by ID."""
    tx = db.query(Transaction).filter(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id
    ).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return tx
