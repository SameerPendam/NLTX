"""
NLTX Blockchain Service
Handles: 
  - Ethereum & Polygon (Web3.py)
  - Solana (HTTP RPC)
  - Gas estimation
  - Transaction submission & monitoring
  - Address resolution (ENS)
  - Token price fetching (CoinGecko)
"""
import asyncio
import aiohttp
import logging
import json
from datetime import datetime, timedelta
from typing import Optional
from web3 import Web3
try:
    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
except ImportError:
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        geth_poa_middleware = None
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ERC-20 ABI (minimal - for token transfers)
ERC20_ABI = json.loads('''[
  {"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"type":"function"},
  {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"type":"function"}
]''')

# Known ERC-20 token contract addresses (mainnet)
TOKEN_CONTRACTS = {
    "USDT":  "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "USDC":  "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "MATIC": "0x7D1AfA7B718fb893dB30A3aBc0Cfc608AaCfeBB0",
    "LINK":  "0x514910771AF9Ca656af840dff83E8264EcF986CA",
}

# CoinGecko token IDs
COINGECKO_IDS = {
    "ETH":  "ethereum",
    "BTC":  "bitcoin",
    "SOL":  "solana",
    "MATIC":"matic-network",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB":  "binancecoin",
    "LINK": "chainlink",
}


class BlockchainService:
    def __init__(self):
        # Connect to Ethereum
        self.w3_eth = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL))
        # Connect to Polygon (PoA chain needs middleware)
        self.w3_polygon = Web3(Web3.HTTPProvider(settings.POLYGON_RPC_URL))
        if geth_poa_middleware:
            try:
                self.w3_polygon.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception:
                pass  # Middleware already present or not needed

        self.solana_rpc = settings.SOLANA_RPC_URL

    # ================================
    #  CONNECTION STATUS
    # ================================
    def get_network_status(self) -> dict:
        return {
            "ethereum": {
                "connected": self.w3_eth.is_connected(),
                "block": self.w3_eth.eth.block_number if self.w3_eth.is_connected() else None,
            },
            "polygon": {
                "connected": self.w3_polygon.is_connected(),
                "block": self.w3_polygon.eth.block_number if self.w3_polygon.is_connected() else None,
            },
            "solana": {"connected": True, "block": "N/A"},  # Solana via async HTTP
        }

    # ================================
    #  ETH / POLYGON BALANCE
    # ================================
    def get_eth_balance(self, address: str, network: str = "ethereum") -> dict:
        """Returns native token balance (ETH or MATIC)."""
        try:
            w3 = self.w3_eth if network == "ethereum" else self.w3_polygon
            checksum = Web3.to_checksum_address(address)
            balance_wei = w3.eth.get_balance(checksum)
            balance = Web3.from_wei(balance_wei, "ether")
            return {"token": "ETH" if network == "ethereum" else "MATIC", "balance": float(balance), "network": network}
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return {"token": "ETH", "balance": 0.0, "network": network, "error": str(e)}

    def get_token_balance(self, address: str, token: str, network: str = "ethereum") -> dict:
        """Returns ERC-20 token balance."""
        contract_addr = TOKEN_CONTRACTS.get(token.upper())
        if not contract_addr:
            return {"token": token, "balance": 0.0, "error": "Unknown token"}
        try:
            w3 = self.w3_eth if network == "ethereum" else self.w3_polygon
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_addr),
                abi=ERC20_ABI
            )
            checksum = Web3.to_checksum_address(address)
            decimals = contract.functions.decimals().call()
            raw_balance = contract.functions.balanceOf(checksum).call()
            balance = raw_balance / (10 ** decimals)
            return {"token": token, "balance": float(balance), "network": network}
        except Exception as e:
            logger.error(f"Token balance failed: {e}")
            return {"token": token, "balance": 0.0, "error": str(e)}

    # ================================
    #  GAS ESTIMATION
    # ================================
    def estimate_gas_usd(self, network: str = "ethereum") -> dict:
        """Estimate gas cost for a standard ETH transfer in USD."""
        try:
            w3 = self.w3_eth if network == "ethereum" else self.w3_polygon
            gas_price_wei = w3.eth.gas_price
            gas_limit = 21000  # standard ETH transfer
            gas_eth = Web3.from_wei(gas_price_wei * gas_limit, "ether")
            # Use approximate price
            eth_price = 2500.0  # fallback price; real system fetches live
            gas_usd = float(gas_eth) * eth_price
            return {
                "network": network,
                "gas_price_gwei": float(Web3.from_wei(gas_price_wei, "gwei")),
                "gas_usd": round(gas_usd, 4),
                "gas_eth": float(gas_eth)
            }
        except Exception as e:
            # Return reasonable defaults if RPC unreachable (demo mode)
            defaults = {"ethereum": 2.40, "polygon": 0.08, "solana": 0.0005}
            return {"network": network, "gas_usd": defaults.get(network, 0.10), "gas_eth": 0.001, "demo": True}

    # ================================
    #  ENS RESOLUTION
    # ================================
    def resolve_ens(self, name: str) -> Optional[str]:
        """Resolve ENS name to Ethereum address."""
        try:
            if not name.endswith(".eth"):
                return None
            address = self.w3_eth.ens.address(name)
            return address
        except Exception as e:
            logger.warning(f"ENS resolution failed for {name}: {e}")
            return None

    # ================================
    #  TRANSACTION BUILDER (Demo MPC)
    # ================================
    def build_transaction(
        self,
        from_address: str,
        to_address: str,
        amount_eth: float,
        network: str = "ethereum"
    ) -> dict:
        """
        Build a raw transaction dict.
        In production: signed via MPC (Fireblocks/Shamir) before submission.
        """
        try:
            w3 = self.w3_eth if network == "ethereum" else self.w3_polygon
            checksum_from = Web3.to_checksum_address(from_address)
            checksum_to = Web3.to_checksum_address(to_address)
            amount_wei = Web3.to_wei(amount_eth, "ether")
            nonce = w3.eth.get_transaction_count(checksum_from)
            gas_price = w3.eth.gas_price

            tx = {
                "nonce": nonce,
                "to": checksum_to,
                "value": amount_wei,
                "gas": 21000,
                "gasPrice": gas_price,
                "chainId": 1 if network == "ethereum" else 137,
            }
            return {"status": "built", "tx": tx, "network": network}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ================================
    #  DEMO TRANSACTION (simulated)
    # ================================
    def simulate_transaction(self, from_addr: str, to_addr: str, amount: float, token: str, network: str) -> dict:
        """
        Simulates a transaction for demo/testing.
        Returns a fake tx hash with realistic structure.
        """
        import hashlib, time
        fake_hash = "0x" + hashlib.sha256(f"{from_addr}{to_addr}{amount}{time.time()}".encode()).hexdigest()
        return {
            "status": "confirmed",
            "tx_hash": fake_hash,
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "token": token,
            "network": network,
            "block_number": 19_450_000 + int(time.time() % 10000),
            "confirmations": 12,
            "gas_used": 21000,
            "gas_usd": self.estimate_gas_usd(network)["gas_usd"],
            "demo_mode": True
        }


# ================================
#  PRICE SERVICE (CoinGecko)
# ================================
class PriceService:
    BASE_URL = "https://api.coingecko.com/api/v3"
    
    # Fallback prices (used when API is unavailable)
    FALLBACK_PRICES = {
        "ETH": 2489.0, "BTC": 65430.0, "SOL": 101.0,
        "MATIC": 0.24, "USDT": 1.0, "USDC": 1.0, "BNB": 380.0,
    }
    
    _cache = {} # token: {price, change_24h, expiry}
    CACHE_DURATION = 60 # seconds

    async def get_price(self, token: str) -> dict:
        """Fetch live price from CoinGecko or Cache."""
        token = token.upper()
        
        # Check Cache
        cached = self._cache.get(token)
        if cached and datetime.utcnow() < cached["expiry"]:
            return {
                "token": token,
                "price_usd": cached["price"],
                "change_24h": cached["change_24h"],
                "source": "cache"
            }

        cg_id = COINGECKO_IDS.get(token)
        if not cg_id:
            return {"token": token, "price_usd": 0.0, "source": "unknown"}

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            price = data.get(cg_id, {}).get("usd", 0)
                            change_24h = data.get(cg_id, {}).get("usd_24h_change", 0)
                            
                            # Store in Cache
                            self._cache[token] = {
                                "price": price,
                                "change_24h": change_24h,
                                "expiry": datetime.utcnow() + timedelta(seconds=self.CACHE_DURATION)
                            }

                            return {
                                "token": token,
                                "price_usd": price,
                                "change_24h": round(change_24h, 2),
                                "source": "coingecko"
                            }
        except Exception as e:
            logger.warning(f"CoinGecko API error: {e}, using fallback price")

        # Fallback
        price = self.FALLBACK_PRICES.get(token.upper(), 0.0)
        return {"token": token.upper(), "price_usd": price, "change_24h": 0.0, "source": "fallback"}

    async def get_multiple_prices(self, tokens: list) -> dict:
        """Fetch prices for multiple tokens at once."""
        ids = [COINGECKO_IDS[t.upper()] for t in tokens if t.upper() in COINGECKO_IDS]
        if not ids:
            return {t: self.FALLBACK_PRICES.get(t.upper(), 0.0) for t in tokens}

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.BASE_URL}/simple/price?ids={','.join(ids)}&vs_currencies=usd&include_24hr_change=true"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = {}
                        for t in tokens:
                            cg_id = COINGECKO_IDS.get(t.upper())
                            result[t.upper()] = {
                                "price_usd": data.get(cg_id, {}).get("usd", self.FALLBACK_PRICES.get(t.upper(), 0)),
                                "change_24h": round(data.get(cg_id, {}).get("usd_24h_change", 0), 2)
                            }
                        return result
        except Exception:
            pass

        return {t.upper(): {"price_usd": self.FALLBACK_PRICES.get(t.upper(), 0), "change_24h": 0.0} for t in tokens}


# Singletons
_blockchain_service: Optional[BlockchainService] = None
_price_service: Optional[PriceService] = None

def get_blockchain_service() -> BlockchainService:
    global _blockchain_service
    if _blockchain_service is None:
        _blockchain_service = BlockchainService()
    return _blockchain_service

def get_price_service() -> PriceService:
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service
