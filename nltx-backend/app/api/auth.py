"""
NLTX Auth API Routes
POST /api/auth/register
POST /api/auth/login
POST /api/auth/refresh
GET  /api/auth/me
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import timedelta
from typing import Optional

from app.database import get_db
from app.models.database import User, SpendingLimit, AccountType
from app.services.account_wallets import ensure_default_wallets
from app.services.auth_service import (
    hash_password, verify_password,
    create_access_token, get_current_active_user
)
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()


# ===== SCHEMAS =====
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    first_name: str
    last_name: Optional[str] = None
    password: str
    account_type: Optional[str] = "personal"

class RegisterResponse(BaseModel):
    id: str
    email: str
    username: str
    access_token: str
    token_type: str = "bearer"
    message: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    email: str


# ===== ROUTES =====
@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new NLTX user with hashed password + default spending limits."""
    # Check email uniqueness
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check username uniqueness
    clean_username = payload.username.lstrip("@").lower()
    if db.query(User).filter(User.username == clean_username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    try:
        acct = AccountType(payload.account_type.lower()) if payload.account_type else AccountType.PERSONAL
    except ValueError:
        acct = AccountType.PERSONAL

    # Create user
    user = User(
        email=payload.email,
        username=clean_username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        hashed_password=hash_password(payload.password),
        account_type=acct,
    )
    db.add(user)
    db.flush()  # Get user.id before commit

    # Create default spending limits
    limits = SpendingLimit(user_id=user.id)
    db.add(limits)
    ensure_default_wallets(db, user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "username": user.username})
    return RegisterResponse(
        id=user.id, email=user.email, username=user.username,
        access_token=token, message="Account created successfully!"
    )


@router.post("/login", response_model=LoginResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login with email/username + password."""
    # Try email or username
    user = db.query(User).filter(
        (User.email == form_data.username) | (User.username == form_data.username)
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Account is disabled")

    token = create_access_token({"sub": user.id, "username": user.username})
    return LoginResponse(
        access_token=token, user_id=user.id, username=user.username, email=user.email
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Return the authenticated user's profile."""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "account_type": current_user.account_type,
        "is_verified": current_user.is_verified,
        "kyc_level": current_user.kyc_level,
        "two_fa_enabled": current_user.two_fa_enabled,
        "preferred_lang": current_user.preferred_lang,
        "ens_name": current_user.ens_name,
    }


@router.post("/logout")
async def logout():
    """Client-side logout (JWT stateless — client discards token)."""
    return {"message": "Logged out successfully. Please discard your token."}
