from fastapi import APIRouter, Depends, HTTPException, Body
import random, string
from app.services.auth_service import get_current_active_user, create_access_token
from app.models.database import User, PlatformLink
from app.services.account_wallets import primary_wallet_display, ensure_default_wallets
from app.database import get_db
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/users", tags=["Users"])

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    settings: Optional[dict] = None

class PlatformLinkRequest(BaseModel):
    platform: str  # telegram, discord, whatsapp
    code: str
    platform_id: Optional[str] = None  # e.g. Telegram numeric user id
    platform_username: Optional[str] = None

@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    ensure_default_wallets(db, current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "wallet_address": primary_wallet_display(db, current_user),
        "created_at": current_user.created_at,
        "settings": {
            "daily_limit": 5000,
            "two_factor": True,
            "theme": "dark",
            "undo_window": 30
        }
    }

@router.put("/me")
async def update_me(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    if data.first_name is not None:
        current_user.first_name = data.first_name
    if data.last_name is not None:
        current_user.last_name = data.last_name
    if data.email is not None:
        current_user.email = data.email
    
    db.commit()
    db.refresh(current_user)
    return {"message": "Profile updated successfully"}

@router.get("/list")
async def list_users(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return all registered users except the current user (for send-money UI)."""
    users = db.query(User).filter(User.id != current_user.id, User.is_active == True).all()
    result = []
    for u in users:
        result.append({
            "id": u.id,
            "username": u.username,
            "first_name": u.first_name or "",
            "last_name": u.last_name or "",
            "display_name": f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username,
            "wallet_address": primary_wallet_display(db, u),
        })
    return {"users": result, "total": len(result)}


@router.get("/profile/{username}")
async def get_user_profile(username: str, db: Session = Depends(get_db)):
    clean = username.replace("@", "").lower()
    user = db.query(User).filter(User.username == clean).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ensure_default_wallets(db, user)
    return {
        "username": user.username,
        "wallet_address": primary_wallet_display(db, user),
        "first_name": user.first_name
    }
# Temp store for linking codes: {code: user_id}
LINK_CODES = {}


def _link_verify_response(db: Session, user_id: str, status: str) -> dict:
    """Return platform link result + JWT so bots can call authenticated APIs."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    access_token = create_access_token({"sub": user.id, "username": user.username})
    return {"status": status, "user_id": user_id, "access_token": access_token}


@router.post("/platform/link-code")
async def generate_link_code(current_user: User = Depends(get_current_active_user)):
    """Generate a random 6-character linking code."""
    code = "NLTX-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    LINK_CODES[code] = current_user.id
    return {"code": code, "expires_in": 300}

@router.post("/platform/link-verify")
async def verify_link_code(payload: PlatformLinkRequest, db: Session = Depends(get_db)):
    """Internal use by bots to verify code and link user."""
    user_id = LINK_CODES.pop(payload.code, None)
    if not user_id:
        raise HTTPException(status_code=404, detail="Invalid or expired code")

    existing = db.query(PlatformLink).filter(
        PlatformLink.user_id == user_id,
        PlatformLink.platform == payload.platform,
    ).first()

    if existing:
        if payload.platform_id and existing.platform_id != payload.platform_id:
            existing.platform_id = payload.platform_id
            if payload.platform_username:
                existing.username = payload.platform_username
            db.commit()
        return _link_verify_response(db, user_id, "already_linked")

    if not payload.platform_id:
        return _link_verify_response(db, user_id, "success")

    link = PlatformLink(
        user_id=user_id,
        platform=payload.platform,
        platform_id=payload.platform_id,
        username=payload.platform_username or "",
    )
    db.add(link)
    db.commit()
    return _link_verify_response(db, user_id, "success")
