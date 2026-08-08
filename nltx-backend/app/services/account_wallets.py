"""
Account wallet helpers — real testnet keypairs per user, primary address lookup,
and recipient resolution (NLTX username, raw address, ENS).

Each new user gets:
  - A real Sepolia (Ethereum testnet) address + encrypted private key
  - A real Amoy (Polygon testnet) address + encrypted private key
  - A pseudo Solana address (read-only demo — Solana testnet signing not implemented)
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

from sqlalchemy.orm import Session
from web3 import Web3

from app.models.database import Network, User, Wallet
from app.services.testnet_service import generate_keypair

logger = logging.getLogger(__name__)


# ─── Wallet creation ───────────────────────────────────────────────────────────

def ensure_default_wallets(db: Session, user: User) -> None:
    """Create one wallet row per supported network if the user has none."""
    existing = db.query(Wallet).filter(Wallet.user_id == user.id).count()
    if existing > 0:
        return

    # Ethereum → Sepolia testnet
    eth_address, eth_enc_key = generate_keypair()
    db.add(Wallet(
        user_id         = user.id,
        network         = Network.ETHEREUM,
        address         = eth_address,
        encrypted_key   = eth_enc_key,
        testnet_network = "sepolia",
        is_primary      = True,
        label           = "Primary Ethereum (Sepolia Testnet)",
    ))

    # Polygon → Amoy testnet (same EVM keypair as ETH for simplicity)
    poly_address, poly_enc_key = generate_keypair()
    db.add(Wallet(
        user_id         = user.id,
        network         = Network.POLYGON,
        address         = poly_address,
        encrypted_key   = poly_enc_key,
        testnet_network = "amoy",
        is_primary      = True,
        label           = "Primary Polygon (Amoy Testnet)",
    ))

    # Solana — read-only pseudo address (testnet signing not in scope)
    import base64, hashlib
    h = hashlib.sha256(f"nltx:sol:{user.id}".encode()).digest()
    sol_addr = base64.urlsafe_b64encode(h)[:44].decode("ascii").rstrip("=")
    db.add(Wallet(
        user_id         = user.id,
        network         = Network.SOLANA,
        address         = sol_addr,
        encrypted_key   = None,
        testnet_network = "solana-devnet",
        is_primary      = True,
        label           = "Primary Solana (Devnet - read only)",
    ))

    db.flush()
    logger.info(f"Created testnet wallets for user {user.username}: ETH={eth_address}")


# ─── Lookup helpers ────────────────────────────────────────────────────────────

def get_primary_wallet(db: Session, user_id: str, network: Network) -> Optional[Wallet]:
    return (
        db.query(Wallet)
        .filter(Wallet.user_id == user_id, Wallet.network == network)
        .order_by(Wallet.is_primary.desc(), Wallet.created_at.asc())
        .first()
    )


def get_primary_wallet_address(db: Session, user_id: str, network: Network) -> Optional[str]:
    w = get_primary_wallet(db, user_id, network)
    return w.address if w else None


# ─── Recipient resolution ──────────────────────────────────────────────────────

def resolve_transfer_recipient(
    db: Session,
    *,
    to_username: Optional[str],
    to_address: Optional[str],
    network: Network,
    resolve_ens,
) -> Tuple[str, Optional[str]]:
    """
    Returns (resolved_address, nltx_username_or_none).
    Raises ValueError if resolution fails.
    """
    if to_address:
        addr = to_address.strip()
        if addr.endswith(".eth"):
            resolved = resolve_ens(addr)
            if not resolved:
                raise ValueError(f"Could not resolve ENS name: {addr}")
            return Web3.to_checksum_address(resolved), None
        if addr.startswith("0x") and len(addr) == 42:
            return Web3.to_checksum_address(addr), None
        raise ValueError("Invalid recipient address")

    if not to_username:
        raise ValueError("Recipient username or address is required")

    clean = to_username.strip().lstrip("@").lower()
    recipient_user = db.query(User).filter(User.username == clean).first()
    if not recipient_user:
        raise ValueError(f"No NLTX user found with username: {clean}")

    ensure_default_wallets(db, recipient_user)
    rw = get_primary_wallet_address(db, recipient_user.id, network)
    if not rw:
        raise ValueError("Recipient has no wallet for this network")

    if network in (Network.ETHEREUM, Network.POLYGON):
        return Web3.to_checksum_address(rw), recipient_user.username
    return rw, recipient_user.username


def primary_wallet_display(db: Session, user: User) -> Optional[str]:
    """First primary EVM address for API compatibility."""
    w = (
        db.query(Wallet)
        .filter(Wallet.user_id == user.id, Wallet.network == Network.ETHEREUM)
        .order_by(Wallet.is_primary.desc())
        .first()
    )
    return w.address if w else None
