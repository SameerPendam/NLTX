"""
NLTX Database Session — SQLAlchemy engine & dependency
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from app.config import get_settings
from app.models.database import Base
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

# SQLite needs check_same_thread=False; ignored for Postgres
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _run_migrations():
    """
    Lightweight startup migrations for SQLite.
    Adds new columns to existing tables without dropping data.
    """
    if "sqlite" not in settings.DATABASE_URL:
        return  # Postgres handles migrations differently

    new_wallet_columns = [
        ("encrypted_key",   "TEXT"),
        ("testnet_network",  "TEXT DEFAULT 'sepolia'"),
    ]
    with engine.connect() as conn:
        # Fetch existing wallet column names
        result = conn.execute(text("PRAGMA table_info(wallets)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_def in new_wallet_columns:
            if col_name not in existing:
                try:
                    conn.execute(text(f"ALTER TABLE wallets ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added wallets.{col_name}")
                except Exception as e:
                    logger.warning(f"Migration skip ({col_name}): {e}")


def init_db():
    """Create all tables on startup, then run lightweight migrations."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def get_db():
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
