"""Public metadata for clients (no auth)."""
from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/meta", tags=["Meta"])


@router.get("/messaging")
async def messaging_info():
    """
    NLTX uses Telegram as the primary messenger (free Bot API, easy setup).
    Discord and WhatsApp are optional extensions.
    """
    s = get_settings()
    return {
        "primary": "telegram",
        "telegram": {
            "bot_username": (s.TELEGRAM_BOT_USERNAME or "").lstrip("@") or None,
            "docs_url": "https://core.telegram.org/bots",
        },
        "optional": [
            {"id": "discord", "enabled": bool(s.DISCORD_BOT_TOKEN and "your-discord" not in s.DISCORD_BOT_TOKEN.lower())},
            {"id": "whatsapp", "enabled": bool(s.WHATSAPP_WEBHOOK_ENABLED)},
        ],
    }
