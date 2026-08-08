"""
NLTX NLP API Routes
POST /api/nlp/parse        — Parse a NL command, return intent + entities
POST /api/nlp/execute      — Parse + execute (BALANCE/PRICE/HISTORY/LIMITS auto-execute; SEND/SWAP return confirmation)
GET  /api/nlp/history      — Get this user's NLP command log
GET  /api/nlp/stats        — NLP accuracy + usage stats for current user
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app.models.database import User, NLPLog, SpendingLimit
from app.services.account_wallets import ensure_default_wallets
from app.services.nlp_service import get_nlp_service
from app.services.auth_service import get_current_active_user
from app.config import get_settings

router = APIRouter(prefix="/api/nlp", tags=["NLP"])
settings = get_settings()


# ===== SCHEMAS =====
class ParseRequest(BaseModel):
    text: str
    platform: str = "web"
    conversation_history: Optional[List[dict]] = None

class ParseResponse(BaseModel):
    intent: str
    entities: dict
    confidence: float
    response_text: str
    requires_confirmation: bool
    error: Optional[str]
    model_used: str
    response_ms: int
    log_id: str


# ===== ROUTES =====
@router.post("/parse", response_model=ParseResponse)
async def parse_command(
    payload: ParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Parse a natural language command using GPT-4 (or rule-based fallback).
    Does NOT execute the transaction — just parses and returns structured intent.
    """
    nlp = get_nlp_service()
    ensure_default_wallets(db, current_user)
    limit = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
    daily_remaining = (
        max(0.0, limit.daily_limit - limit.daily_used) if limit else 5000.0
    )

    user_context = {
        "username": current_user.username,
        "preferred_network": "sepolia",
        "daily_remaining": daily_remaining,
    }

    result = await nlp.parse_command(
        text=payload.text,
        user_context=user_context,
        conversation_history=payload.conversation_history
    )

    # Log this NLP interaction
    log = NLPLog(
        user_id=current_user.id,
        platform=payload.platform,
        raw_input=payload.text,
        parsed_intent=result.get("intent"),
        parsed_entities=result.get("entities"),
        confidence=result.get("confidence"),
        model_used=result.get("model_used", "unknown"),
        response_ms=result.get("response_ms", 0),
        success=result.get("error") is None
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return ParseResponse(log_id=log.id, **{k: result[k] for k in [
        "intent", "entities", "confidence", "response_text",
        "requires_confirmation", "error", "model_used", "response_ms"
    ]})


@router.post("/execute")
async def execute_nlp_command(
    payload: ParseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Full one-shot: parse NL command + auto-execute informational intents.
    - BALANCE, PRICE, HISTORY, LIMITS, HELP: execute immediately and return data
    - SEND, SWAP, SCHEDULE: return parsed result for frontend confirmation step
    """
    nlp = get_nlp_service()
    result = await nlp.parse_command(payload.text)
    intent  = result.get("intent", "UNKNOWN")
    entities = result.get("entities", {})

    # ── HELP ──────────────────────────────────────────────────────────────────
    if intent == "HELP":
        return {
            "type": "info", "intent": "HELP",
            "data": {"commands": [
                "💸 Send X TOKEN to @username  —  e.g. 'Send 0.001 ETH to alice'",
                "💰 Check balance  —  e.g. 'What's my ETH balance?'",
                "🔄 Swap tokens  —  e.g. 'Swap 0.01 ETH to USDC'",
                "📈 Price check  —  e.g. 'What's the price of SOL?'",
                "📅 Schedule  —  e.g. 'Schedule 200 USDT monthly to savings'",
                "📋 History  —  e.g. 'Show my last 5 transactions'",
                "🔒 Limits  —  e.g. 'What are my spending limits?'",
                "📬 Wallet  —  type 'Show my wallet address'",
            ]},
            "response_text": (
                "👋 Here's what I can do for you:\n\n"
                "💸 Send — e.g. 'Send 0.001 ETH to alice'\n"
                "💰 Balance — e.g. 'What's my ETH balance?'\n"
                "🔄 Swap — e.g. 'Swap 0.01 ETH to USDC'\n"
                "📈 Price — e.g. 'Price of BTC'\n"
                "📋 History — e.g. 'Show my last transactions'\n"
                "🔒 Limits — e.g. 'What are my spending limits?'\n\n"
                "⚡ Running on Sepolia Testnet — get free ETH at https://sepoliafaucet.com"
            ),
        }

    # ── LIMITS ────────────────────────────────────────────────────────────────
    if intent == "LIMITS":
        ensure_default_wallets(db, current_user)
        lim = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
        data = {
            "daily_limit":      lim.daily_limit      if lim else 5000,
            "daily_used":       lim.daily_used        if lim else 0,
            "daily_remaining":  max(0, (lim.daily_limit - lim.daily_used)) if lim else 5000,
            "weekly_limit":     lim.weekly_limit      if lim else 25000,
            "monthly_limit":    lim.monthly_limit     if lim else 100000,
            "single_tx_max":    lim.single_tx_max     if lim else 10000,
            "require_2fa_above":lim.require_2fa_above if lim else 500,
        }
        text = (
            f"📊 Your Spending Limits:\n"
            f"  Daily: ${data['daily_limit']:,.0f} (used ${data['daily_used']:,.2f}, left ${data['daily_remaining']:,.2f})\n"
            f"  Weekly: ${data['weekly_limit']:,.0f}  |  Monthly: ${data['monthly_limit']:,.0f}\n"
            f"  Max single tx: ${data['single_tx_max']:,.0f}  |  2FA above: ${data['require_2fa_above']:,.0f}"
        )
        return {"type": "info", "intent": "LIMITS", "data": data, "response_text": text}

    # ── BALANCE: live testnet balances ────────────────────────────────────────
    if intent == "BALANCE":
        from app.services.blockchain_service import get_price_service
        from app.services.testnet_service import get_testnet_service
        from app.models.database import Wallet as WalletModel, Network as NetEnum
        ensure_default_wallets(db, current_user)
        testnet   = get_testnet_service()
        price_svc = get_price_service()
        wallets   = db.query(WalletModel).filter(WalletModel.user_id == current_user.id).all()
        balances  = []
        for w in wallets:
            if w.network == NetEnum.ETHEREUM:
                bal   = testnet.get_balance(w.address, w.testnet_network or "sepolia")
                price = (await price_svc.get_price("ETH")).get("price_usd", 2500)
                balances.append({"network": f"Ethereum ({w.testnet_network or 'sepolia'})", "token": "ETH",
                                  "balance": round(bal, 8), "usd": round(bal * price, 4), "address": w.address})
            elif w.network == NetEnum.POLYGON:
                bal   = testnet.get_balance(w.address, w.testnet_network or "amoy")
                price = (await price_svc.get_price("MATIC")).get("price_usd", 0.24)
                balances.append({"network": f"Polygon ({w.testnet_network or 'amoy'})", "token": "MATIC",
                                  "balance": round(bal, 8), "usd": round(bal * price, 4), "address": w.address})
            elif w.network == NetEnum.SOLANA:
                balances.append({"network": "Solana (devnet)", "token": "SOL", "balance": 0.0, "usd": 0.0, "address": w.address})
        lines = ["💼 Your Testnet Wallet Balances:\n"]
        for b in balances:
            lines.append(f"  {b['network']}: {b['balance']} {b['token']} (≈ ${b['usd']})")
            lines.append(f"  Address: {b['address'][:22]}...")
        lines.append("\n💡 Get free Sepolia ETH: https://sepoliafaucet.com")
        return {"type": "info", "intent": "BALANCE", "data": balances, "response_text": "\n".join(lines)}

    # ── PRICE: live CoinGecko ─────────────────────────────────────────────────
    if intent == "PRICE":
        from app.services.blockchain_service import get_price_service
        token      = (entities.get("query_token") or entities.get("token") or "ETH").upper()
        price_data = await get_price_service().get_price(token)
        price      = price_data.get("price_usd", 0)
        change     = price_data.get("change_24h", 0)
        arrow      = "📈" if change >= 0 else "📉"
        text       = f"{arrow} {token} = ${price:,.2f} USD  ({change:+.2f}% 24h)\nSource: CoinGecko"
        return {"type": "info", "intent": "PRICE", "data": price_data, "response_text": text}

    # ── HISTORY: last 5 transactions ──────────────────────────────────────────
    if intent == "HISTORY":
        from app.models.database import Transaction as TxModel
        txs = (
            db.query(TxModel)
            .filter(TxModel.user_id == current_user.id)
            .order_by(TxModel.created_at.desc())
            .limit(5).all()
        )
        if not txs:
            return {"type": "info", "intent": "HISTORY", "data": [],
                    "response_text": "No transactions yet.\nTry: 'Send 0.001 ETH to alice'"}
        lines = ["📋 Your Last 5 Transactions:\n"]
        em_map = {"confirmed": "✅", "pending": "⏳", "failed": "❌", "undone": "↩️", "simulated": "🧪"}
        for t in txs:
            em   = em_map.get(t.status.value if t.status else "", "❓")
            dest = t.to_username or (t.to_address[:14] + "..." if t.to_address else "?")
            lines.append(f"{em} {(t.tx_type.value or 'TX').upper()}: {t.amount} {t.token} → {dest}")
            if t.tx_hash:
                lines.append(f"   Hash: {t.tx_hash[:24]}...")
            if t.created_at:
                lines.append(f"   {t.created_at.strftime('%Y-%m-%d %H:%M UTC')}")
        return {
            "type": "info", "intent": "HISTORY",
            "data": [{
                "id": t.id, "type": t.tx_type.value if t.tx_type else None,
                "status": t.status.value if t.status else None,
                "amount": t.amount, "token": t.token,
                "to": t.to_username or t.to_address,
                "hash": t.tx_hash,
                "created_at": t.created_at.isoformat() if t.created_at else None
            } for t in txs],
            "response_text": "\n".join(lines)
        }

    # ── SEND / SWAP / SCHEDULE → return for frontend confirmation ─────────────
    return {
        "type":        "confirmation_required" if result.get("requires_confirmation") else "info",
        "intent":      intent,
        "entities":    entities,
        "confidence":  result.get("confidence"),
        "response_text": result.get("response_text"),
        "fraud_check": nlp.run_fraud_checks(entities.get("amount") or 0, entities.get("to_address") or ""),
    }


@router.get("/history")
async def get_nlp_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Return user's NLP command history."""
    logs = (
        db.query(NLPLog)
        .filter(NLPLog.user_id == current_user.id)
        .order_by(NLPLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": log.id, "raw_input": log.raw_input,
            "intent": log.parsed_intent, "confidence": log.confidence,
            "model_used": log.model_used, "platform": log.platform,
            "response_ms": log.response_ms, "success": log.success,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.get("/stats")
async def get_nlp_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """NLP usage statistics for the current user."""
    since = datetime.utcnow() - timedelta(days=30)
    logs = db.query(NLPLog).filter(
        NLPLog.user_id == current_user.id,
        NLPLog.created_at >= since
    ).all()

    total = len(logs)
    successful = sum(1 for l in logs if l.success)
    avg_confidence = sum(l.confidence or 0 for l in logs) / total if total else 0
    avg_response_ms = sum(l.response_ms or 0 for l in logs) / total if total else 0

    intent_breakdown = {}
    for log in logs:
        intent = log.parsed_intent or "UNKNOWN"
        intent_breakdown[intent] = intent_breakdown.get(intent, 0) + 1

    return {
        "total_commands": total,
        "successful": successful,
        "accuracy_pct": round((successful / total * 100) if total else 0, 1),
        "avg_confidence": round(avg_confidence, 3),
        "avg_response_ms": round(avg_response_ms),
        "intent_breakdown": intent_breakdown,
        "period_days": 30,
    }
