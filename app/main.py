import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.v1.endpoints.chat import router as chat_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("personal_ai_assistant")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Ollama base URL: {settings.OLLAMA_BASE_URL}")
    logger.info(f"Default model: {settings.OLLAMA_MODEL}")
    yield
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


# Include chat router at root (/chat) and API versioned (/api/v1/chat)
app.include_router(chat_router, tags=["Chat"])
app.include_router(chat_router, prefix="/api/v1", tags=["Chat (v1)"])
