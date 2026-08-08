"""
NLTX Wallet API Routes
GET  /api/wallet/balances       — Get all token balances across networks
GET  /api/wallet/price/{token}  — Get live token price
GET  /api/wallet/gas/{network}  — Estimate gas fee
GET  /api/wallet/network-status — Check blockchain connection status
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.database import User, Wallet, Network
from app.services.auth_service import get_current_active_user
from app.services.blockchain_service import get_blockchain_service, get_price_service
from app.services.account_wallets import ensure_default_wallets

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


@router.get("/balances")
async def get_balances(
    include_prices: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return token balances for this user's registered wallet addresses (RPC + live prices).
    """
    ensure_default_wallets(db, current_user)
    price_svc = get_price_service()
    bc = get_blockchain_service()
    tokens_needed = ["ETH", "USDT", "USDC", "MATIC", "SOL", "BTC"]
    prices = (
        await price_svc.get_multiple_prices(tokens_needed) if include_prices else {}
    )

    wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id).all()
    result = []

    for w in wallets:
        addr = w.address

        if w.network == Network.ETHEREUM:
            native = bc.get_eth_balance(addr, "ethereum")
            bal = float(native.get("balance") or 0)
            _append_row(result, prices, include_prices, "ethereum", "ETH", bal, addr)

            for tok in ("USDT", "USDC"):
                tbal = bc.get_token_balance(addr, tok, "ethereum")
                b = float(tbal.get("balance") or 0)
                _append_row(result, prices, include_prices, "ethereum", tok, b, addr)

        elif w.network == Network.POLYGON:
            native = bc.get_eth_balance(addr, "polygon")
            bal = float(native.get("balance") or 0)
            _append_row(result, prices, include_prices, "polygon", "MATIC", bal, addr)
            for tok in ("USDT", "USDC"):
                tbal = bc.get_token_balance(addr, tok, "polygon")
                b = float(tbal.get("balance") or 0)
                _append_row(result, prices, include_prices, "polygon", tok, b, addr)

        elif w.network == Network.SOLANA:
            sol_bal = await _fetch_sol_balance(addr)
            _append_row(result, prices, include_prices, "solana", "SOL", sol_bal, addr)

    total_usd = sum(x["usd_value"] for x in result)
    return {
        "balances": result,
        "total_usd": round(total_usd, 2),
        "last_updated": "just now",
    }


def _append_row(result, prices, include_prices, network, token, balance, address):
    price_usd = prices.get(token, {}).get("price_usd", 1.0) if include_prices else 0
    ch = prices.get(token, {}).get("change_24h", 0.0) if include_prices else 0.0
    usd_value = round(balance * price_usd, 2)
    result.append({
        "network": network,
        "token": token,
        "balance": balance,
        "address": address,
        "price_usd": price_usd,
        "usd_value": usd_value,
        "change_24h": ch,
    })


async def _fetch_sol_balance(address: str) -> float:
    import aiohttp
    from app.config import get_settings

    settings = get_settings()
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.SOLANA_RPC_URL,
                json=body,
                timeout=aiohttp.ClientTimeout(total=4),
            ) as resp:
                if resp.status != 200:
                    return 0.0
                data = await resp.json()
                lamports = data.get("result", {}).get("value")
                if lamports is None:
                    return 0.0
                return round(lamports / 1e9, 6)
    except Exception:
        return 0.0


@router.get("/price/{token}")
async def get_token_price(token: str):
    """Get live USD price for a token from CoinGecko."""
    price_svc = get_price_service()
    result = await price_svc.get_price(token.upper())
    if result.get("price_usd", 0) == 0:
        raise HTTPException(status_code=404, detail=f"Price not available for {token}")
    return result


@router.get("/gas/{network}")
async def estimate_gas(network: str):
    """Estimate gas cost in USD for the given network."""
    valid_networks = ["ethereum", "polygon", "solana"]
    if network not in valid_networks:
        raise HTTPException(status_code=400, detail=f"Invalid network. Choose: {valid_networks}")
    bc = get_blockchain_service()
    return bc.estimate_gas_usd(network)


@router.get("/network-status")
async def get_network_status():
    """Check connectivity status for all supported blockchains."""
    bc = get_blockchain_service()
    return bc.get_network_status()


@router.get("/spending-limits")
async def get_spending_limits(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Return current user's spending limits and usage."""
    from app.models.database import SpendingLimit
    limit = db.query(SpendingLimit).filter(SpendingLimit.user_id == current_user.id).first()
    if not limit:
        return {"daily_limit": 5000, "daily_used": 0, "message": "Default limits applied"}

    return {
        "daily_limit":       limit.daily_limit,
        "weekly_limit":      limit.weekly_limit,
        "monthly_limit":     limit.monthly_limit,
        "single_tx_max":     limit.single_tx_max,
        "require_2fa_above": limit.require_2fa_above,
        "daily_used":        limit.daily_used,
        "weekly_used":       limit.weekly_used,
        "monthly_used":      limit.monthly_used,
        "daily_remaining":   max(0, limit.daily_limit - limit.daily_used),
    }


@router.get("/address")
async def get_wallet_addresses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return the user's testnet wallet addresses with explorer links and faucet URLs.
    This is what users should fund to send real testnet transactions.
    """
    from app.services.account_wallets import ensure_default_wallets
    from app.services.testnet_service import get_testnet_service, EXPLORER
    ensure_default_wallets(db, current_user)
    wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id).all()
    testnet = get_testnet_service()
    result = []
    for w in wallets:
        tnet = w.testnet_network or ("sepolia" if w.network == Network.ETHEREUM else "amoy")
        bal  = testnet.get_balance(w.address, tnet) if w.network in (Network.ETHEREUM, Network.POLYGON) else 0.0
        result.append({
            "network":       w.network.value,
            "testnet":       tnet,
            "address":       w.address,
            "balance":       round(bal, 8),
            "label":         w.label,
            "explorer":      f"https://{'sepolia.etherscan.io' if tnet == 'sepolia' else 'amoy.polygonscan.com'}/address/{w.address}",
            "faucet":        "https://sepoliafaucet.com" if tnet == "sepolia" else "https://faucet.polygon.technology",
        })
    return {"addresses": result, "testnet_mode": True,
            "note": "Fund your Sepolia address with free ETH to send real testnet transactions."}

