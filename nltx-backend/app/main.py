"""
NLTX Main FastAPI Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from app.config import get_settings
from app.database import init_db
from app.api import auth, nlp, transactions, wallet, analytics, users, meta
from app.bots import whatsapp_bot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)
settings = get_settings()

# ===========================
#  CREATE APP
# ===========================
app = FastAPI(
    title="NLTX API",
    description="Natural Language Transaction Exchange — Conversational Blockchain Payments",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# ===========================
#  MIDDLEWARE
# ===========================
@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    formatted_process_time = f"{process_time:.2f}ms"
    logger.info(f"Method: {request.method} Path: {request.url.path} Status: {response.status_code} Time: {formatted_process_time}")
    return response

# ===========================
#  CORS (allow frontend)
# ===========================
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
# In DEBUG mode allow all origins so that file:// / Live Server always works
if settings.DEBUG:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,   # must be False when allow_origins=["*"]
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# ===========================
#  STARTUP
# ===========================
@app.on_event("startup")
async def startup():
    logger.info("🚀 NLTX API starting up...")
    init_db()
    logger.info("✅ Database tables created/verified")
    logger.info(f"📖 API Docs: http://localhost:{settings.API_PORT}/api/docs")

# ===========================
#  ROUTERS
# ===========================
app.include_router(auth.router)
app.include_router(nlp.router)
app.include_router(transactions.router)
app.include_router(wallet.router)
app.include_router(analytics.router)
app.include_router(users.router)
app.include_router(meta.router)
if settings.WHATSAPP_WEBHOOK_ENABLED:
    app.include_router(whatsapp_bot.router)
    logger.info("WhatsApp webhook routes enabled (optional)")

# ===========================
#  ROOT + HEALTH
# ===========================
@app.get("/")
async def root():
    return {
        "name": "NLTX API",
        "version": settings.APP_VERSION,
        "description": "Natural Language Transaction Exchange",
        "docs": "/api/docs",
        "status": "running",
        "primary_messenger": "telegram",
        "messaging_info": "/api/meta/messaging",
    }

@app.get("/api/health")
async def health():
    from app.services.blockchain_service import get_blockchain_service
    bc = get_blockchain_service()
    net_status = bc.get_network_status()
    return {
        "status": "healthy",
        "api": "running",
        "database": "connected",
        "blockchain": net_status,
        "version": settings.APP_VERSION
    }

# ===========================
#  ERROR HANDLERS
# ===========================
@app.exception_handler(404)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={"error": "Endpoint not found", "docs": "/api/docs"})

@app.exception_handler(500)
async def server_error(request, exc):
    logger.error(f"Server error: {exc}")
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
