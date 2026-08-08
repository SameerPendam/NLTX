"""
NLTX Core Configuration — loads from .env file
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "NLTX"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Security / Auth
    SECRET_KEY: str = "nltx_super_secret_jwt_key_change_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Database
    DATABASE_URL: str = "sqlite:///./nltx.db"

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_FALLBACK_MODEL: str = "gpt-3.5-turbo"

    # Telegram (primary messenger — free Bot API via @BotFather)
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_BOT_USERNAME: str = ""  # without @; used for t.me deep links in the web app
    TELEGRAM_WEBHOOK_URL: str = ""

    # Discord (optional — set DISCORD_BOT_TOKEN and run: python run.py --discord)
    DISCORD_BOT_TOKEN: str = ""
    DISCORD_GUILD_ID: str = ""

    # WhatsApp Business API (optional — set WHATSAPP_WEBHOOK_ENABLED=True after Meta setup)
    WHATSAPP_WEBHOOK_ENABLED: bool = False
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    # Blockchain RPC
    ETHEREUM_RPC_URL: str = "https://mainnet.infura.io/v3/demo"
    POLYGON_RPC_URL: str = "https://polygon-rpc.com"
    SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"

    # Security
    FRAUD_DETECTION_THRESHOLD: float = 0.75
    MAX_DAILY_LIMIT: float = 10000.0
    UNDO_WINDOW_SECONDS: int = 30

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:5500,http://127.0.0.1:8080,*"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
