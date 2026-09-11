import os
from typing import Set
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
        "You are an intelligent, proactive personal AI assistant. "
        "Be concise, helpful, and clear."
    )
    DEFAULT_TEMPERATURE: float = 0.7

    # Device Auth: comma-separated list of approved tokens
    AUTHORIZED_DEVICE_TOKENS: str = "dev_a87f2b1c4e90d3e5f6a1b2c3d4e5f607"

    def get_authorized_tokens(self) -> Set[str]:
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
