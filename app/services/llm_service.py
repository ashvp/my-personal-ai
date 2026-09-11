import os
import logging
from typing import Dict, Any, List, Optional
import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.chat import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)


def get_wsl_host_ip() -> Optional[str]:
    """Detects Windows host IP when running inside WSL2 via /etc/resolv.conf."""
    try:
        if os.path.exists("/etc/resolv.conf"):
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    if line.strip().startswith("nameserver"):
                        return line.split()[1].strip()
    except Exception:
        pass
    return None


class OllamaLLMService:
    def __init__(
        self,
        base_url: str = settings.OLLAMA_BASE_URL,
        model: str = settings.OLLAMA_MODEL,
        system_prompt: str = settings.DEFAULT_SYSTEM_PROMPT,
        temperature: float = settings.DEFAULT_TEMPERATURE
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.system_prompt = system_prompt
        self.temperature = temperature
        self.timeout = settings.LLM_TIMEOUT_SECONDS

    def _get_target_urls(self) -> List[str]:
        urls = [self.base_url]
        wsl_host = get_wsl_host_ip()
        if wsl_host:
            wsl_url = f"http://{wsl_host}:11434"
            if wsl_url not in urls:
                urls.append(wsl_url)
        return urls

    async def generate_reply(self, request: ChatRequest) -> ChatResponse:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": request.message}
        ]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }

        candidate_urls = self._get_target_urls()
        last_connect_error: Optional[Exception] = None

        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            logger.info(f"Querying Ollama at {endpoint} using model: {self.model}")

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(endpoint, json=payload)

                if response.status_code != 200:
                    logger.error(f"Ollama error {response.status_code}: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Ollama service error: {response.text}"
                    )

                data = response.json()
                assistant_content = data.get("message", {}).get("content", "")
                total_duration_ns = data.get("total_duration")
                total_duration_sec = round(total_duration_ns / 1e9, 2) if total_duration_ns else None

                # Keep working base URL for subsequent calls
                self.base_url = base_url

                return ChatResponse(
                    reply=assistant_content,
                    model=data.get("model", self.model),
                    total_duration_seconds=total_duration_sec
                )

            except httpx.ConnectError as exc:
                logger.warning(f"Failed to connect to {base_url}: {exc}")
                last_connect_error = exc
                continue
            except httpx.TimeoutException as exc:
                logger.error(f"Timeout querying {base_url}: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=f"Request to model '{self.model}' timed out after {self.timeout}s."
                )
            except HTTPException:
                raise
            except Exception as exc:
                logger.exception("Unexpected error communicating with local LLM")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal error processing chat: {str(exc)}"
                )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Could not connect to Ollama at {candidate_urls}. "
                f"Error: {last_connect_error}. "
                "Make sure Ollama is running on the host (`ollama serve` or Ollama app)."
            )
        )


# Singleton instance for dependency injection
llm_service = OllamaLLMService()


def get_llm_service() -> OllamaLLMService:
    return llm_service
