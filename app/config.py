import os
from typing import Set, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Personal AI Assistant"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Local LLM (Ollama) Settings
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3.5:2b"
    LLM_TIMEOUT_SECONDS: float = 120.0

    # Model Routing Settings
    MODEL_ROUTER: str = "qwen3:0.6b"
    MODEL_FAST: str = "qwen3:1.7b"
    MODEL_REASONING: str = "qwen3.5:2b"

    # LLM Defaults (kept internal to backend)
    DEFAULT_SYSTEM_PROMPT: str = (
        "You are an intelligent, proactive personal executive AI assistant. "
        "Be concise, helpful, and direct. "
        "CRITICAL: Never simulate, roleplay, or draft messages to contacts in chat. "
        "Whenever the user asks you to reach out, message, or tell someone something, "
        "the system sends it autonomously via WhatsApp."
    )
    DEFAULT_TEMPERATURE: float = 0.7

    # Device Auth: Sensitive tokens MUST come from .env (no secrets in codebase)
    AUTHORIZED_DEVICE_TOKENS: str = ""

    # Background Automated Sync Engine
    BACKGROUND_SYNC_ENABLED: bool = True
    BACKGROUND_SYNC_INTERVAL_MINUTES: int = 1

    # Optional Outlook / Azure App ID (loaded from .env)
    APPLICATION_ID_OUTLOOK: str = ""
    DIRECTORY_ID_OUTLOOK: str = ""

    # MacroDroid Autonomous Cellular Calling Webhook (loaded from .env)
    MACRODROID_WEBHOOK_URL: Optional[str] = None
    MACRODROID_WHATSAPP_WEBHOOK_URL: Optional[str] = None

    def get_authorized_tokens(self) -> Set[str]:
        if not self.AUTHORIZED_DEVICE_TOKENS:
            return set()
        return {
            token.strip()
            for token in self.AUTHORIZED_DEVICE_TOKENS.split(",")
            if token.strip()
        }

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
