import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.v1.endpoints.chat import router as chat_router_v1
from app.api.v1.endpoints.gmail import router as gmail_router
from app.api.v1.endpoints.whatsapp import router as whatsapp_router
from app.api.v1.endpoints.outlook import router as outlook_router
from app.api.v1.endpoints.sync import router as sync_router
from app.api.v1.endpoints.sms import router as sms_router
from app.api.v1.endpoints.contacts import router as contacts_router
from app.api.v2.endpoints.chat import router as chat_router_v2
from app.api.v2.endpoints.graph import router as graph_router_v2
from app.services.background_sync import background_sync_service

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("personal_ai_assistant")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Ollama base URL: {settings.OLLAMA_BASE_URL}")
    logger.info(f"Default model: {settings.OLLAMA_MODEL}")

    if settings.BACKGROUND_SYNC_ENABLED:
        await background_sync_service.start()

    if getattr(settings, "ENABLE_V2_GRAPH", True):
        try:
            from app.services.graph_service import graph_service
            import asyncio
            await asyncio.to_thread(graph_service.sync_all_stored_contacts)
        except Exception as g_sync_exc:
            logger.warning(f"Error during startup graph contact sync: {g_sync_exc}")

    yield

    if settings.BACKGROUND_SYNC_ENABLED:
        await background_sync_service.stop()

    logger.info(f"Shutting down {settings.APP_NAME}")



app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Personal AI Assistant Server backend.\n\n"
        "Connects to a local Qwen model (via Ollama) to process real-time requests, "
        "manage user tasks, and deliver updates to mobile clients."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS for mobile apps, web frontends, and cross-origin tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"], summary="Health check")
async def health_check():
    """Health check endpoint to verify server status and model configuration."""
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "default_model": settings.OLLAMA_MODEL
    }


# --- Version 1.0 Routes (Pure Vector RAG & 3-Tier Cognitive Memory) ---
app.include_router(chat_router_v1, prefix="/api/v1", tags=["Chat (v1)"])
app.include_router(gmail_router, tags=["Gmail Sync"])
app.include_router(gmail_router, prefix="/api/v1", tags=["Gmail Sync (v1)"])
app.include_router(whatsapp_router, tags=["WhatsApp Sync"])
app.include_router(whatsapp_router, prefix="/api/v1", tags=["WhatsApp Sync (v1)"])
app.include_router(outlook_router, tags=["Outlook Sync"])
app.include_router(outlook_router, prefix="/api/v1", tags=["Outlook Sync (v1)"])
app.include_router(sync_router, tags=["Background Sync"])
app.include_router(sync_router, prefix="/api/v1", tags=["Background Sync (v1)"])
app.include_router(sms_router, tags=["SMS Sync"])
app.include_router(sms_router, prefix="/api/v1", tags=["SMS Sync (v1)"])
app.include_router(contacts_router, tags=["Contacts & Calling"])
app.include_router(contacts_router, prefix="/api/v1", tags=["Contacts & Calling (v1)"])

# --- Version 2.0 Routes (Bitemporal Knowledge Graph Engine) ---
app.include_router(chat_router_v2, prefix="/api/v2", tags=["Chat (v2)"])
app.include_router(graph_router_v2, prefix="/api/v2", tags=["Knowledge Graph (v2)"])

# Root /chat routes according to configured DEFAULT_API_VERSION (v1 or v2)
active_version = str(getattr(settings, "DEFAULT_API_VERSION", "v2")).strip().lower()
if active_version == "v2":
    app.include_router(chat_router_v2, tags=["Chat (Active v2)"])
else:
    app.include_router(chat_router_v1, tags=["Chat (Active v1)"])

# Serve PWA Frontend
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/manifest.json", include_in_schema=False)
    async def serve_manifest():
        return FileResponse(os.path.join(FRONTEND_DIR, "manifest.json"))

    @app.get("/sw.js", include_in_schema=False)
    async def serve_sw():
        return FileResponse(
            os.path.join(FRONTEND_DIR, "sw.js"),
            media_type="application/javascript"
        )
