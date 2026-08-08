"""
NLTX WhatsApp Bot Skeleton
Based on Meta WhatsApp Business API (Twilio or Direct)
"""
import logging
from fastapi import APIRouter, Request, Response
from app.services.nlp_service import get_nlp_service

router = APIRouter(prefix="/api/bots/whatsapp", tags=["Bots"])
logger = logging.getLogger(__name__)

@router.get("/webhook")
async def whatsapp_verify(request: Request):
    """Verify webhook for Meta."""
    params = request.query_params
    if params.get("hub.verify_token") == "nltx_secret_token":
        return Response(content=params.get("hub.challenge"))
    return Response(content="Invalid verify token", status_code=403)

@router.post("/webhook")
async def whatsapp_message(request: Request):
    """Handle incoming WhatsApp messages."""
    data = await request.json()
    logger.info(f"WhatsApp Message received: {data}")
    
    # In a real implementation:
    # 1. Extract phone number and message text
    # 2. Lookup user by phone in DB
    # 3. Call NLP service
    # 4. Generate response or transaction preview
    # 5. Send back using Meta Graph API
    
    return {"status": "received"}

def run_whatsapp_bot():
    """WhatsApp usually runs as a webhook inside the FastAPI app."""
    # This is integrated into main.py via the router
    print("🟢 WhatsApp Webhook Router initialized.")

if __name__ == "__main__":
    print("Run via main.py")
