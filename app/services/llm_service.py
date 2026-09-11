import os
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.chat import ChatResponse
from app.services.memory_service import memory_service

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

    def _assemble_contextual_prompt(self, user_prompt: str, override_prompt: Optional[str] = None) -> str:
        """Injects Intermediate Memory and relevant Long-Term Memory into the system prompt."""
        parts = [override_prompt or self.system_prompt]

        # 1. Inject Intermediate Memory (Active Digest & Today's Briefing)
        intermediate_context = memory_service.get_intermediate_context()
        if intermediate_context:
            parts.append(intermediate_context)

        # 2. Inject Relevant Long-Term Memory (Search if query seems inquiry-based)
        keywords = [
            "email", "mail", "inbox", "message", "sent", "from", "unread", "yesterday",
            "invoice", "receipt", "flight", "ticket", "project", "contract", "meeting"
        ]
        if any(kw in user_prompt.lower() for kw in keywords):
            # Extract basic search terms
            words = [
                w.strip("?,!.") for w in user_prompt.split()
                if w.lower() not in ("what", "did", "the", "a", "an", "is", "was", "any", "my", "me", "tell", "show", "have", "i", "got", "about")
            ]
            search_query = " ".join(words)
            if search_query:
                results = memory_service.search_emails(search_query, limit=3)
                if results:
                    email_lines = ["--- RELEVANT EMAILS FROM ARCHIVE (LONG-TERM MEMORY) ---"]
                    for r in results:
                        email_lines.append(
                            f"• [Date: {r.get('date', '')}] From: {r.get('sender', '')}\n"
                            f"  Subject: {r.get('subject', '')}\n"
                            f"  Details: {r.get('summary', '') or r.get('snippet', '')}"
                        )
                    email_lines.append("---------------------------------------------------------")
                    parts.append("\n".join(email_lines))

        return "\n\n".join(parts)

    def _build_payload(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        full_system_prompt = self._assemble_contextual_prompt(prompt, system_prompt)
        temp = temperature if temperature is not None else self.temperature

        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": stream,
            "options": {
                "temperature": temp
            }
        }

    async def generate_reply(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> ChatResponse:
        """Blocking reply method. Captures both thinking process and final answer."""
        payload = self._build_payload(prompt, system_prompt, temperature, stream=False)
        candidate_urls = self._get_target_urls()
        last_connect_error: Optional[Exception] = None

        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            logger.info(f"[Blocking] Querying Ollama at {endpoint} with model: {self.model}")

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
                msg = data.get("message", {})
                content = msg.get("content", "")
                thinking = msg.get("thinking", "")

                if not content and thinking:
                    content = thinking

                total_duration_ns = data.get("total_duration")
                total_duration_sec = round(total_duration_ns / 1e9, 2) if total_duration_ns else None

                self.base_url = base_url
                return ChatResponse(
                    reply=content,
                    thinking=thinking if thinking != content else None,
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
                logger.exception("Unexpected error in generate_reply")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Internal error processing chat: {str(exc)}"
                )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not connect to Ollama at {candidate_urls}. Error: {last_connect_error}."
        )

    async def stream_reply(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> AsyncGenerator[str, None]:
        """Real-time SSE token stream generator with 3-tier memory context."""
        payload = self._build_payload(prompt, system_prompt, temperature, stream=True)
        candidate_urls = self._get_target_urls()

        client = httpx.AsyncClient(timeout=self.timeout)
        target_endpoint = None

        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            try:
                response = await client.send(
                    client.build_request("POST", endpoint, json=payload),
                    stream=True
                )
                if response.status_code == 200:
                    target_endpoint = endpoint
                    self.base_url = base_url
                    break
                else:
                    await response.aclose()
            except httpx.ConnectError:
                continue

        if not target_endpoint:
            await client.aclose()
            err_payload = json.dumps({
                "type": "error",
                "error": f"Could not connect to Ollama at {candidate_urls}.",
                "done": True
            })
            yield f"data: {err_payload}\n\n"
            return

        try:
            async for line in response.aiter_lines():
                if not line or not line.strip():
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = chunk.get("message", {})
                thinking = msg.get("thinking", "")
                content = msg.get("content", "")
                is_done = chunk.get("done", False)

                if thinking:
                    yield f"data: {json.dumps({'type': 'thinking', 'token': thinking, 'done': False})}\n\n"

                if content:
                    yield f"data: {json.dumps({'type': 'answer', 'token': content, 'done': False})}\n\n"

                if is_done:
                    total_duration_ns = chunk.get("total_duration")
                    total_sec = round(total_duration_ns / 1e9, 2) if total_duration_ns else None
                    event_data = {
                        "type": "done",
                        "token": "",
                        "done": True,
                        "model": chunk.get("model", self.model),
                        "total_duration_seconds": total_sec
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"

        except Exception as exc:
            logger.exception("Error while streaming tokens from Ollama")
            err_payload = json.dumps({"type": "error", "error": str(exc), "done": True})
            yield f"data: {err_payload}\n\n"
        finally:
            await response.aclose()
            await client.aclose()


# Singleton instance for dependency injection
llm_service = OllamaLLMService()


def get_llm_service() -> OllamaLLMService:
    return llm_service
