"""
NLTX Database Models — SQLAlchemy ORM
Covers: Users, Wallets, Transactions, NLP Logs, Spending Limits, Platforms
"""
from sqlalchemy import (
    Column, String, Float, Boolean, Integer, DateTime,
    ForeignKey, Text, Enum as SAEnum, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid, enum

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ========== ENUMS ==========
class TxStatus(str, enum.Enum):
    PENDING   = "pending"
    CONFIRMED = "confirmed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    UNDONE    = "undone"

class TxType(str, enum.Enum):
    SEND     = "send"
    RECEIVE  = "receive"
    SWAP     = "swap"
    SCHEDULE = "schedule"

class Network(str, enum.Enum):
    ETHEREUM = "ethereum"
    POLYGON  = "polygon"
    SOLANA   = "solana"

class AccountType(str, enum.Enum):
    PERSONAL   = "personal"
    ENTERPRISE = "enterprise"
    DAO        = "dao"


# ========== USER ==========
class User(Base):
    __tablename__ = "users"

    id             = Column(String, primary_key=True, default=gen_uuid)
    email          = Column(String, unique=True, nullable=False, index=True)
    username       = Column(String, unique=True, nullable=False, index=True)
    first_name     = Column(String, nullable=False)
    last_name      = Column(String)
    hashed_password= Column(String, nullable=False)
    account_type   = Column(SAEnum(AccountType), default=AccountType.PERSONAL)
    is_active      = Column(Boolean, default=True)
    is_verified    = Column(Boolean, default=False)
    kyc_level      = Column(Integer, default=0)           # 0=none, 1=basic, 2=full
    two_fa_enabled = Column(Boolean, default=False)
    two_fa_secret  = Column(String, nullable=True)
    preferred_lang = Column(String, default="en")
    ens_name       = Column(String, nullable=True)
    created_at     = Column(DateTime, server_default=func.now())
    updated_at     = Column(DateTime, onupdate=func.now())

    # Relationships
    wallets        = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")
    transactions   = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    spending_limits= relationship("SpendingLimit", back_populates="user", uselist=False, cascade="all, delete-orphan")
    nlp_logs       = relationship("NLPLog", back_populates="user", cascade="all, delete-orphan")
    platform_links = relationship("PlatformLink", back_populates="user", cascade="all, delete-orphan")


# ========== WALLET ==========
class Wallet(Base):
    __tablename__ = "wallets"

    id              = Column(String, primary_key=True, default=gen_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False)
    network         = Column(SAEnum(Network), nullable=False)
    address         = Column(String, nullable=False)
    is_primary      = Column(Boolean, default=False)
    label           = Column(String, default="Main Wallet")
    # Real testnet keypair (private key stored AES-256 encrypted)
    encrypted_key   = Column(String, nullable=True)  # Fernet-encrypted private key hex
    testnet_network = Column(String, default="sepolia")  # sepolia | amoy
    created_at      = Column(DateTime, server_default=func.now())

    user            = relationship("User", back_populates="wallets")


# ========== TRANSACTION ==========
class Transaction(Base):
    __tablename__ = "transactions"

    id            = Column(String, primary_key=True, default=gen_uuid)
    user_id       = Column(String, ForeignKey("users.id"), nullable=False)
    tx_type       = Column(SAEnum(TxType), nullable=False)
    status        = Column(SAEnum(TxStatus), default=TxStatus.PENDING)
    network       = Column(SAEnum(Network), nullable=False)

    # Parties
    from_address  = Column(String)
    to_address    = Column(String)
    to_username   = Column(String)     # NLTX username recipient

    # Amounts
    amount        = Column(Float, nullable=False)
    token         = Column(String, default="ETH")  # ETH, USDT, SOL, etc.
    usd_value     = Column(Float)
    gas_fee_usd   = Column(Float, default=0.0)
    exchange_rate = Column(Float)

    # Metadata
    memo          = Column(String)
    tx_hash       = Column(String)     # Blockchain hash after execution
    nlp_command   = Column(String)     # Original user command
    block_number  = Column(Integer)
    confirmations = Column(Integer, default=0)

    # Timing
    undo_expires_at = Column(DateTime)
    executed_at     = Column(DateTime)
    confirmed_at    = Column(DateTime)
    created_at      = Column(DateTime, server_default=func.now())

    user            = relationship("User", back_populates="transactions")


# ========== SPENDING LIMIT ==========
class SpendingLimit(Base):
    __tablename__ = "spending_limits"

    id                = Column(String, primary_key=True, default=gen_uuid)
    user_id           = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
    daily_limit       = Column(Float, default=5000.0)
    weekly_limit      = Column(Float, default=25000.0)
    monthly_limit     = Column(Float, default=100000.0)
    single_tx_max     = Column(Float, default=10000.0)
    require_2fa_above = Column(Float, default=500.0)

    # Usage tracking (resets daily/weekly/monthly)
    daily_used        = Column(Float, default=0.0)
    weekly_used       = Column(Float, default=0.0)
    monthly_used      = Column(Float, default=0.0)
    last_reset_daily  = Column(DateTime, server_default=func.now())
    last_reset_weekly = Column(DateTime, server_default=func.now())

    user              = relationship("User", back_populates="spending_limits")


# ========== NLP LOG ==========
class NLPLog(Base):
    __tablename__ = "nlp_logs"

    id              = Column(String, primary_key=True, default=gen_uuid)
    user_id         = Column(String, ForeignKey("users.id"))
    platform        = Column(String, default="web")  # web, telegram, discord, whatsapp
    raw_input       = Column(Text, nullable=False)
    parsed_intent   = Column(String)    # SEND, BALANCE, SWAP, SCHEDULE, etc.
    parsed_entities = Column(JSON)      # Extracted: amount, token, recipient, memo
    confidence      = Column(Float)     # 0.0 to 1.0
    model_used      = Column(String)    # gpt-4o, gpt-3.5-turbo
    response_ms     = Column(Integer)   # Processing time in ms
    resulting_tx_id = Column(String, ForeignKey("transactions.id"), nullable=True)
    success         = Column(Boolean, default=True)
    created_at      = Column(DateTime, server_default=func.now())

    user            = relationship("User", back_populates="nlp_logs")


# ========== PLATFORM LINK ==========
class PlatformLink(Base):
    __tablename__ = "platform_links"

    id          = Column(String, primary_key=True, default=gen_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    platform    = Column(String, nullable=False)  # telegram, discord, whatsapp
    platform_id = Column(String, nullable=False)  # External user/chat ID
    username    = Column(String)
    is_active   = Column(Boolean, default=True)
    linked_at   = Column(DateTime, server_default=func.now())

    user        = relationship("User", back_populates="platform_links")


# ========== SCHEDULED PAYMENT ==========
class ScheduledPayment(Base):
    __tablename__ = "scheduled_payments"

    id           = Column(String, primary_key=True, default=gen_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    to_username  = Column(String)
    to_address   = Column(String)
    amount       = Column(Float, nullable=False)
    token        = Column(String, default="USDT")
    network      = Column(SAEnum(Network), default=Network.POLYGON)
    memo         = Column(String)
    frequency    = Column(String, default="monthly")  # daily, weekly, monthly
    next_run     = Column(DateTime)
    last_run     = Column(DateTime)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, server_default=func.now())
