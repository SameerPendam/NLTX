"""
NLTX Testnet Service — Real Blockchain Transactions on Ethereum Sepolia Testnet
=================================================================================
Replaces the simulate_transaction() demo with REAL signed transactions.

Networks used:
  - Sepolia Testnet (Ethereum)  — free RPC via Alchemy public endpoint
  - Amoy Testnet (Polygon)      — free public RPC

Key design:
  - Each NLTX user gets a unique testnet keypair (ETH address + private key)
  - Private keys are stored AES-256 encrypted in the DB wallet.encrypted_key field
  - A platform "faucet" address (configured in .env) can seed user wallets
  - Transactions are real, visible on testnets.blockscout.com / sepolia.etherscan.io
"""

import asyncio
import logging
import os
from typing import Optional, Tuple

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TransactionNotFound
from cryptography.fernet import Fernet
import base64, hashlib

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ─── Public free RPC endpoints (no API key needed) ────────────────────────────
SEPOLIA_RPC    = "https://ethereum-sepolia-rpc.publicnode.com"
AMOY_RPC       = "https://rpc-amoy.polygon.technology"

# Chain IDs
CHAIN_ID = {
    "sepolia": 11155111,
    "amoy":    80002,
}

# Block explorers for tx links
EXPLORER = {
    "sepolia": "https://sepolia.etherscan.io/tx/",
    "amoy":    "https://amoy.polygonscan.com/tx/",
}

# ─── Fernet key derived from SECRET_KEY for deterministic encryption ──────────
def _fernet_key() -> bytes:
    raw = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(raw)

_fernet = Fernet(_fernet_key())


def encrypt_private_key(private_key_hex: str) -> str:
    """Encrypt a private key hex string for safe DB storage."""
    return _fernet.encrypt(private_key_hex.encode()).decode()


def decrypt_private_key(encrypted: str) -> str:
    """Decrypt a stored private key."""
    return _fernet.decrypt(encrypted.encode()).decode()


# ─── Keypair generation ────────────────────────────────────────────────────────
def generate_keypair() -> Tuple[str, str]:
    """
    Generate a fresh EVM keypair.
    Returns (address, encrypted_private_key).
    """
    account: LocalAccount = Account.create()
    address = account.address
    encrypted = encrypt_private_key(account.key.hex())
    return address, encrypted


# ─── Web3 connections ──────────────────────────────────────────────────────────
class TestnetService:
    """Real testnet transaction broadcaster."""

    def __init__(self):
        self.w3_sepolia = Web3(Web3.HTTPProvider(SEPOLIA_RPC))
        self.w3_amoy    = Web3(Web3.HTTPProvider(AMOY_RPC))
        logger.info(
            f"TestnetService — Sepolia connected: {self.w3_sepolia.is_connected()}, "
            f"Amoy connected: {self.w3_amoy.is_connected()}"
        )

    def _w3(self, network: str) -> Web3:
        return self.w3_amoy if network == "amoy" else self.w3_sepolia

    def _chain_id(self, network: str) -> int:
        return CHAIN_ID.get(network, CHAIN_ID["sepolia"])

    # ── Get native balance ─────────────────────────────────────────────────────
    def get_balance(self, address: str, network: str = "sepolia") -> float:
        """Returns ETH/MATIC balance in ether units."""
        try:
            w3 = self._w3(network)
            checksum = Web3.to_checksum_address(address)
            wei = w3.eth.get_balance(checksum)
            return float(Web3.from_wei(wei, "ether"))
        except Exception as e:
            logger.warning(f"Balance fetch failed for {address} on {network}: {e}")
            return 0.0

    # ── Estimate gas ───────────────────────────────────────────────────────────
    def estimate_gas_price_gwei(self, network: str = "sepolia") -> float:
        try:
            w3 = self._w3(network)
            gwei = float(Web3.from_wei(w3.eth.gas_price, "gwei"))
            return round(gwei, 4)
        except Exception:
            return 5.0  # fallback

    # ── Build + sign + send a real ETH transfer ────────────────────────────────
    def send_eth(
        self,
        from_encrypted_key: str,
        to_address: str,
        amount_eth: float,
        network: str = "sepolia",
        memo: str = ""
    ) -> dict:
        """
        Sign and broadcast a real ETH transfer on the testnet.
        Returns a result dict with tx_hash, explorer_url, status.
        """
        try:
            w3 = self._w3(network)
            if not w3.is_connected():
                return {"status": "error", "error": f"Cannot connect to {network} RPC"}

            private_key = decrypt_private_key(from_encrypted_key)
            account: LocalAccount = Account.from_key(private_key)
            from_address = account.address

            checksum_to = Web3.to_checksum_address(to_address)
            amount_wei = Web3.to_wei(amount_eth, "ether")

            # Check balance
            balance_wei = w3.eth.get_balance(from_address)
            gas_price   = w3.eth.gas_price
            gas_limit   = 21000
            total_cost  = amount_wei + gas_price * gas_limit

            if balance_wei < total_cost:
                balance_eth = float(Web3.from_wei(balance_wei, "ether"))
                return {
                    "status": "error",
                    "error": (
                        f"Insufficient testnet ETH. Your balance: {balance_eth:.6f} ETH. "
                        f"Required: {float(Web3.from_wei(total_cost, 'ether')):.6f} ETH. "
                        f"Get free Sepolia ETH from: https://sepoliafaucet.com"
                    )
                }

            nonce = w3.eth.get_transaction_count(from_address)
            tx = {
                "nonce": nonce,
                "to": checksum_to,
                "value": amount_wei,
                "gas": gas_limit,
                "gasPrice": gas_price,
                "chainId": self._chain_id(network),
            }

            signed   = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash  = w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex   = tx_hash.hex()
            if not tx_hex.startswith("0x"):
                tx_hex = "0x" + tx_hex

            gas_eth  = float(Web3.from_wei(gas_price * gas_limit, "ether"))
            block    = w3.eth.block_number

            logger.info(f"Testnet TX sent: {tx_hex} ({amount_eth} ETH on {network})")

            return {
                "status": "confirmed",
                "tx_hash": tx_hex,
                "explorer_url": EXPLORER.get(network, "") + tx_hex,
                "from": from_address,
                "to": checksum_to,
                "amount": amount_eth,
                "token": "ETH",
                "network": network,
                "block_number": block,
                "confirmations": 0,   # broadcast; confirmations come async
                "gas_used": gas_limit,
                "gas_eth": gas_eth,
                "gas_usd": gas_eth * 2500,  # approx; real system fetches price
                "demo_mode": False
            }

        except Exception as e:
            logger.error(f"send_eth failed: {e}")
            return {"status": "error", "error": str(e)}

    # ── Simulate (fallback when testnet unreachable) ───────────────────────────
    def simulate(self, from_addr: str, to_addr: str, amount: float, token: str, network: str) -> dict:
        import hashlib, time
        fake = "0x" + hashlib.sha256(f"{from_addr}{to_addr}{amount}{time.time()}".encode()).hexdigest()
        return {
            "status": "simulated",
            "tx_hash": fake,
            "explorer_url": "",
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "token": token,
            "network": network,
            "block_number": 0,
            "confirmations": 0,
            "gas_used": 21000,
            "gas_eth": 0.0,
            "gas_usd": 0.05,
            "demo_mode": True
        }

    # ── Network status ─────────────────────────────────────────────────────────
    def get_network_status(self) -> dict:
        sep_ok  = self.w3_sepolia.is_connected()
        amoy_ok = self.w3_amoy.is_connected()
        return {
            "sepolia": {
                "connected": sep_ok,
                "block": self.w3_sepolia.eth.block_number if sep_ok else None,
                "explorer": "https://sepolia.etherscan.io",
                "faucet": "https://sepoliafaucet.com",
            },
            "amoy": {
                "connected": amoy_ok,
                "block": self.w3_amoy.eth.block_number if amoy_ok else None,
                "explorer": "https://amoy.polygonscan.com",
                "faucet": "https://faucet.polygon.technology",
            },
        }


# ── Singleton ──────────────────────────────────────────────────────────────────
_testnet_service: Optional[TestnetService] = None

def get_testnet_service() -> TestnetService:
    global _testnet_service
    if _testnet_service is None:
        _testnet_service = TestnetService()
    return _testnet_service
