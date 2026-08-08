"""
NLTX NLP Service — GPT-4 Powered Intent Detection & Entity Extraction
Handles:
  - Intent classification (SEND, RECEIVE, BALANCE, SWAP, SCHEDULE, PRICE, HELP, LIMITS)
  - Entity extraction (amount, token, recipient, memo, network)
  - Context-aware multi-turn conversation
  - Fallback to local rule-based parser if OpenAI is unavailable
"""
import json
import re
import time
import logging
from typing import Optional
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ============================
#  SYSTEM PROMPT
# ============================
SYSTEM_PROMPT = """You are NLTX, an AI assistant for a blockchain payment platform.
Your job is to parse natural language commands into structured JSON for cryptocurrency transactions.

You MUST respond ONLY with valid JSON in this exact format:
{
  "intent": "SEND|RECEIVE|BALANCE|SWAP|SCHEDULE|PRICE|LIMITS|HISTORY|HELP|UNKNOWN",
  "entities": {
    "amount": <number or null>,
    "token": "<ETH|USDT|USDC|BTC|SOL|MATIC or null>",
    "to_username": "<@username or null>",
    "to_address": "<0x... wallet address or null>",
    "from_token": "<token or null>",
    "to_token": "<token for swap or null>",
    "memo": "<reason/description or null>",
    "network": "<ethereum|polygon|solana or null>",
    "frequency": "<daily|weekly|monthly or null>",
    "schedule_date": "<date string or null>",
    "query_token": "<token to get price/balance of or null>"
  },
  "confidence": <0.0 to 1.0>,
  "response_text": "<friendly confirmation message>",
  "requires_confirmation": <true|false>,
  "error": "<null or error message if invalid>"
}

Rules:
- For SEND: extract amount, token, recipient (username or address), memo
- For SWAP: extract amount, from_token, to_token
- For BALANCE: extract query_token (or null for all)
- For SCHEDULE: extract amount, token, recipient, frequency, schedule_date
- For PRICE: extract query_token
- Default token is USDT if not specified
- Default network: polygon for USDT/USDC, ethereum for ETH, solana for SOL
- Always be friendly and helpful
- If intent unclear, return UNKNOWN with confidence < 0.5
"""


# ============================
#  NLP SERVICE CLASS
# ============================
class NLPService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("sk-proj-your") else None
        self.model = settings.OPENAI_MODEL
        self.fallback_model = settings.OPENAI_FALLBACK_MODEL

    async def parse_command(
        self,
        text: str,
        user_context: Optional[dict] = None,
        conversation_history: Optional[list] = None
    ) -> dict:
        """
        Main entry: parse NL command → structured intent + entities.
        Falls back to rule-based parser if OpenAI is unavailable.
        """
        start_ms = int(time.time() * 1000)

        # Try GPT-4 first
        if self.client:
            result = await self._parse_with_openai(text, user_context, conversation_history)
        else:
            # Fallback: rule-based parser
            result = self._rule_based_parser(text)

        result["response_ms"] = int(time.time() * 1000) - start_ms
        result["raw_input"] = text
        return result

    # ============================
    #  OPENAI PARSER
    # ============================
    async def _parse_with_openai(self, text: str, user_context: dict = None, history: list = None) -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Add context about the user if available
        if user_context:
            ctx_str = f"""User context:
- Username: {user_context.get('username', 'unknown')}
- Balances: {json.dumps(user_context.get('balances', {}))}
- Daily limit remaining: ${user_context.get('daily_remaining', 5000)}
- Preferred network: {user_context.get('preferred_network', 'polygon')}"""
            messages.append({"role": "system", "content": ctx_str})

        # Add last N conversation turns for context
        if history:
            for turn in history[-6:]:
                messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": text})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=500
            )
            raw = response.choices[0].message.content
            result = json.loads(raw)
            result["model_used"] = self.model
            result["source"] = "openai"
            return result

        except Exception as e:
            logger.warning(f"GPT-4 failed ({e}), trying fallback model...")
            try:
                response = await self.client.chat.completions.create(
                    model=self.fallback_model,
                    messages=messages,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                    max_tokens=400
                )
                raw = response.choices[0].message.content
                result = json.loads(raw)
                result["model_used"] = self.fallback_model
                result["source"] = "openai_fallback"
                return result
            except Exception as e2:
                logger.error(f"OpenAI fallback also failed: {e2}")
                return self._rule_based_parser(text)

    # ============================
    #  RULE-BASED FALLBACK PARSER
    # ============================
    def _rule_based_parser(self, text: str) -> dict:
        """Local regex-based parser when OpenAI is unavailable."""
        lower = text.lower().strip()
        entities = {
            "amount": None, "token": None, "to_username": None,
            "to_address": None, "from_token": None, "to_token": None,
            "memo": None, "network": None, "frequency": None,
            "schedule_date": None, "query_token": None
        }

        # Extract amount
        amount_match = re.search(r'\b(\d+(?:\.\d+)?)\b', text)
        if amount_match:
            entities["amount"] = float(amount_match.group(1))

        # Extract token
        tokens = ["ETH", "BTC", "SOL", "USDT", "USDC", "MATIC", "BNB"]
        for tok in tokens:
            if tok.lower() in lower or tok in text:
                entities["token"] = tok
                break

        # Extract recipient (@username or wallet address)
        username_match = re.search(r'@(\w+)', lower)
        if not username_match:
            # fallback to 'to <name>' skipping tokens/amounts
            username_match = re.search(r'\bto\s+([a-zA-Z_]\w*)\b', lower)
            
        if username_match:
            name = username_match.group(1)
            entities["to_username"] = f"@{name}"

        wallet_match = re.search(r'0x[a-fA-F0-9]{40}', text)
        if wallet_match:
            entities["to_address"] = wallet_match.group(0)

        # Extract memo
        memo_match = re.search(r'for\s+(.+?)(?:\s+on\s+|\s+via\s+|$)', lower)
        if memo_match:
            entities["memo"] = memo_match.group(1).strip()

        # Determine intent
        if any(w in lower for w in ["send", "pay", "transfer"]):
            intent = "SEND"
            confidence = 0.85 if entities["amount"] and entities["to_username"] else 0.60
            response = f"I'll send {entities['amount']} {entities['token'] or 'USDT'} to {entities['to_username']}. Please confirm."
        elif any(w in lower for w in ["swap", "exchange", "convert"]):
            intent = "SWAP"
            # Try to get from/to tokens
            swap_match = re.search(r'(\w+)\s+(?:to|for)\s+(\w+)', lower)
            if swap_match:
                entities["from_token"] = swap_match.group(1).upper()
                entities["to_token"] = swap_match.group(2).upper()
            confidence = 0.80
            response = f"Swap request noted. From: {entities['from_token']} To: {entities['to_token']}."
        elif any(w in lower for w in ["balance", "how much", "portfolio", "wallet"]):
            intent = "BALANCE"
            for tok in tokens:
                if tok.lower() in lower:
                    entities["query_token"] = tok
            confidence = 0.90
            response = "Fetching your balance information..."
        elif any(w in lower for w in ["price", "rate", "worth", "value"]):
            intent = "PRICE"
            for tok in tokens:
                if tok.lower() in lower:
                    entities["query_token"] = tok
            confidence = 0.85
            response = f"Fetching price for {entities.get('query_token', 'ETH')}..."
        elif any(w in lower for w in ["schedule", "recurring", "automatic", "every month", "monthly"]):
            intent = "SCHEDULE"
            entities["frequency"] = "monthly" if "month" in lower else "weekly" if "week" in lower else "daily"
            confidence = 0.75
            response = f"Setting up recurring payment of {entities['amount']} {entities['token'] or 'USDT'}"
        elif any(w in lower for w in ["limit", "spending"]):
            intent = "LIMITS"
            confidence = 0.85
            response = "Fetching your spending limits..."
        elif any(w in lower for w in ["history", "recent", "last", "transactions"]):
            intent = "HISTORY"
            confidence = 0.85
            response = "Fetching your recent transaction history..."
        elif any(w in lower for w in ["help", "what can", "commands", "how to"]):
            intent = "HELP"
            confidence = 0.95
            response = "Here's what I can do for you..."
        else:
            intent = "UNKNOWN"
            confidence = 0.30
            response = "I'm not sure what you meant. Try: 'Send 50 USDT to Alice' or 'Show my ETH balance'"

        # Default token
        if not entities["token"] and intent in ["SEND", "SWAP", "SCHEDULE"]:
            entities["token"] = "USDT"

        return {
            "intent": intent,
            "entities": entities,
            "confidence": confidence,
            "response_text": response,
            "requires_confirmation": intent in ["SEND", "SWAP", "SCHEDULE"],
            "error": None,
            "model_used": "rule_based",
            "source": "fallback"
        }

    # ============================
    #  FRAUD DETECTION
    # ============================
    def run_fraud_checks(self, amount: float, to_address: str, user_history: list = None) -> dict:
        """
        Simple rule-based fraud scoring.
        In production: plug in a real ML fraud detection model.
        """
        score = 0.0
        flags = []

        # Large amount flag
        if amount > 5000:
            score += 0.3
            flags.append("large_amount")

        # Very large single transaction
        if amount > 10000:
            score += 0.4
            flags.append("exceeds_single_tx_limit")

        # New recipient (would check against history in real system)
        if user_history and len(user_history) < 3:
            score += 0.1
            flags.append("new_account_high_value")

        # Blacklisted address pattern (demo check)
        if to_address and "000000000000" in to_address:
            score += 0.5
            flags.append("suspicious_address")

        is_flagged = score >= settings.FRAUD_DETECTION_THRESHOLD

        return {
            "fraud_score": round(score, 3),
            "is_flagged": is_flagged,
            "flags": flags,
            "recommendation": "block" if score > 0.8 else "review" if is_flagged else "allow"
        }


# Singleton instance
_nlp_service: Optional[NLPService] = None

def get_nlp_service() -> NLPService:
    global _nlp_service
    if _nlp_service is None:
        _nlp_service = NLPService()
    return _nlp_service
