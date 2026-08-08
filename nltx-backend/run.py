"""
NLTX Server Entrypoint — run.py

Usage:
  python run.py                   API + scheduler + Telegram bot (if token set)
  python run.py --no-telegram     API + scheduler only
  python run.py --discord         Also start Discord bot (optional)
  python run.py --all             Telegram + Discord
"""
import uvicorn
import threading
import sys
import os

# Ensure working directory is the backend folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import get_settings

settings = get_settings()


def start_api():
    """Start the FastAPI backend server."""
    print("\n" + "=" * 50)
    print(f"  NLTX API Server v{settings.APP_VERSION}")
    print(f"  http://localhost:{settings.API_PORT}")
    print(f"  API Docs: http://localhost:{settings.API_PORT}/api/docs")
    print("=" * 50 + "\n")
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="info",
    )


def start_telegram():
    """Start Telegram bot in a background thread."""
    from app.bots.telegram_bot import run_telegram_bot
    t = threading.Thread(target=run_telegram_bot, daemon=True)
    t.start()
    return t


def start_discord():
    """Start Discord bot in a background thread."""
    from app.bots.discord_bot import run_discord_bot
    t = threading.Thread(target=run_discord_bot, daemon=True)
    t.start()
    return t


def start_scheduler():
    """Start the autonomous payment scheduler thread."""
    from app.services.scheduler_service import process_scheduled_payments
    t = threading.Thread(target=process_scheduled_payments, daemon=True)
    t.start()
    return t


def _telegram_token_configured() -> bool:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        return False
    low = token.lower()
    return "your-telegram" not in low and "changeme" not in low


if __name__ == "__main__":
    args = sys.argv[1:]

    print("Starting NLTX Autonomous Engine...")
    start_scheduler()

    if "--no-telegram" not in args:
        if _telegram_token_configured():
            print("Starting Telegram bot (primary messenger)...")
            start_telegram()
        else:
            print(
                "INFO: Telegram bot skipped — set TELEGRAM_BOT_TOKEN in .env to enable. "
                "Use --no-telegram to suppress this message."
            )
    else:
        print("INFO: Telegram bot disabled (--no-telegram).")

    if "--all" in args or "--discord" in args:
        print("Starting Discord bot (optional)...")
        start_discord()

    start_api()
