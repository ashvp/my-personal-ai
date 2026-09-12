import os
import json
import logging
from typing import Dict, Any, List, Optional, AsyncGenerator
import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.chat import ChatResponse
from app.services.memory_service import memory_service
from app.services.triage_service import triage_service
from app.services.contacts_service import contacts_service

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


CLASSIFIER_FEW_SHOT_SYSTEM = (
    "You are a fast intent classifier for a personal AI assistant.\n"
    "Classify the user's message into exactly ONE of the following 6 categories:\n"
    "- CALL_CONTACT: Requesting to phone, call, ring, dial, or get contact info / 1-tap call action for a person or friend (e.g., 'Call Madhu', 'Ring Prasad Appa', 'Dial mom', 'What is Madhu's number?').\n"
    "- DAILY_BRIEFING: Requesting daily updates, morning briefings, schedule, agenda, overview of the day, or what needs to be done.\n"
    "- MESSAGE_LOOKUP: Searching, checking, or reading WhatsApp messages, texts, chats, or conversations.\n"
    "- EMAIL_LOOKUP: Searching, checking, counting, or reading emails, inboxes, or mail messages.\n"
    "- DEEP_REASON: Complex logic, code debugging, math problems, multi-step planning, or in-depth analytical reasoning.\n"
    "- FAST_CHAT: General conversation, greetings, drafting emails/replies, writing, summarization, casual questions, and quick everyday tasks.\n\n"
    "Respond with ONLY the category name. Do not explain or include any other text."
)

CLASSIFIER_FEW_SHOT_MESSAGES = [
    {"role": "system", "content": CLASSIFIER_FEW_SHOT_SYSTEM},
    # Few-shot examples:
    {"role": "user", "content": "Call Madhu."},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "Ring Prasad Appa"},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "Dial Chitra Amma"},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "Phone Rachit Agarwal"},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "What is Madhu's phone number?"},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "Can you call my dad?"},
    {"role": "assistant", "content": "CALL_CONTACT"},
    {"role": "user", "content": "Give me updates for the day."},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "Morning briefing."},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "What's on my radar today?"},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "Brief me on my day."},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "What do I have to do today?"},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "Give me an executive briefing of my day."},
    {"role": "assistant", "content": "DAILY_BRIEFING"},
    {"role": "user", "content": "What was my last WhatsApp message?"},
    {"role": "assistant", "content": "MESSAGE_LOOKUP"},
    {"role": "user", "content": "What did Rahul text me yesterday?"},
    {"role": "assistant", "content": "MESSAGE_LOOKUP"},
    {"role": "user", "content": "Did anyone message me about the Goa trip?"},
    {"role": "assistant", "content": "MESSAGE_LOOKUP"},
    {"role": "user", "content": "Check my recent chats for the WiFi password."},
    {"role": "assistant", "content": "MESSAGE_LOOKUP"},
    {"role": "user", "content": "What was my last email?"},
    {"role": "assistant", "content": "EMAIL_LOOKUP"},
    {"role": "user", "content": "Did Google reply to my job application?"},
    {"role": "assistant", "content": "EMAIL_LOOKUP"},
    {"role": "user", "content": "Check my inbox for flight tickets or confirmation numbers."},
    {"role": "assistant", "content": "EMAIL_LOOKUP"},
    {"role": "user", "content": "How many unread emails do I have from today?"},
    {"role": "assistant", "content": "EMAIL_LOOKUP"},
    {"role": "user", "content": "Draft a polite reply saying I will review the proposal by tomorrow."},
    {"role": "assistant", "content": "FAST_CHAT"},
    {"role": "user", "content": "Summarize these meeting notes in 3 bullet points."},
    {"role": "assistant", "content": "FAST_CHAT"},
    {"role": "user", "content": "Hello, how are you? What can you do?"},
    {"role": "assistant", "content": "FAST_CHAT"},
    {"role": "user", "content": "Write a quick caption for an Instagram post about coffee."},
    {"role": "assistant", "content": "FAST_CHAT"},
    {"role": "user", "content": "Analyze the time complexity and memory overhead of these two distributed consensus algorithms."},
    {"role": "assistant", "content": "DEEP_REASON"},
    {"role": "user", "content": "There is a subtle race condition in this mutex lock code, debug it step-by-step."},
    {"role": "assistant", "content": "DEEP_REASON"},
    {"role": "user", "content": "Solve this riddle: If three frogs jump across five stones under specific constraints..."},
    {"role": "assistant", "content": "DEEP_REASON"},
    {"role": "user", "content": "Compare the tax implications of stock options vs RSUs across different vesting schedules."},
    {"role": "assistant", "content": "DEEP_REASON"},
]


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
        self.router_model = getattr(settings, "MODEL_ROUTER", "qwen3:0.6b")
        self.fast_model = getattr(settings, "MODEL_FAST", "qwen3:1.7b")
        self.reasoning_model = getattr(settings, "MODEL_REASONING", "qwen3.5:2b")
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

    async def classify_intent(self, user_prompt: str) -> str:
        """Classifies user intent using the 0.6B micro-model with few-shot prompting."""
        messages = list(CLASSIFIER_FEW_SHOT_MESSAGES)
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.router_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 10
            }
        }

        candidate_urls = self._get_target_urls()
        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    response = await client.post(endpoint, json=payload)
                if response.status_code == 200:
                    data = response.json()
                    raw = data.get("message", {}).get("content", "").strip().upper()
                    if "CALL_CONTACT" in raw:
                        intent = "CALL_CONTACT"
                    elif "DAILY_BRIEFING" in raw:
                        intent = "DAILY_BRIEFING"
                    elif "MESSAGE_LOOKUP" in raw:
                        intent = "MESSAGE_LOOKUP"
                    elif "EMAIL_LOOKUP" in raw:
                        intent = "EMAIL_LOOKUP"
                    elif "DEEP_REASON" in raw:
                        intent = "DEEP_REASON"
                    else:
                        intent = "FAST_CHAT"

                    logger.info(f"[Intent Router] '{user_prompt[:40]}...' -> {intent} (raw: '{raw}') via {self.router_model}")
                    return intent
            except Exception as exc:
                logger.warning(f"Intent classification call failed to {base_url}: {exc}")
                continue

        # Heuristic fallback if router network or models hiccup
        lower = user_prompt.lower().strip()
        if any(lower.startswith(p) for p in ["call ", "ring ", "dial ", "phone "]) or any(w in lower for w in ["phone number of", "call to ", "phone number for", "contact details of"]):
            logger.info(f"[Intent Fallback] Detected CALL_CONTACT via heuristic keywords for: '{user_prompt[:40]}'")
            return "CALL_CONTACT"
        elif any(w in lower for w in ["briefing", "update for the day", "updates for the day", "today's update", "todays update", "on my plate", "on my radar", "agenda", "what do i have to do"]):
            logger.info(f"[Intent Fallback] Detected DAILY_BRIEFING via heuristic keywords for: '{user_prompt[:40]}'")
            return "DAILY_BRIEFING"
        elif any(w in lower for w in ["whatsapp", "text", "message", "chat"]):
            return "MESSAGE_LOOKUP"
        elif any(w in lower for w in ["email", "mail", "inbox"]):
            return "EMAIL_LOOKUP"

        logger.warning(f"All router endpoints failed for prompt '{user_prompt[:40]}'. Falling back to FAST_CHAT.")
        return "FAST_CHAT"

    def _prepare_routed_execution(
        self,
        prompt: str,
        intent: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> tuple[str, str, float]:
        """Prepares the destination model, focused system prompt, and temperature based on intent."""

        # 0. CALL_CONTACT: Instant 1-tap cellular dialer card
        if intent == "CALL_CONTACT":
            model = self.fast_model
            temp = 0.1
            card = contacts_service.generate_call_card_markdown(prompt)
            sys_prompt = (
                "You are a personal AI phone assistant. The user wants to call or contact someone.\n"
                f"Present the following verified contact card directly without altering the phone numbers:\n\n{card}"
            )
            return model, sys_prompt, temp

        # 1. DAILY_BRIEFING: Intelligent multi-modal cognitive triage (Schedule -> People -> Promos)
        if intent == "DAILY_BRIEFING":
            model = self.fast_model
            temp = 0.3
            sys_prompt = triage_service.build_briefing_prompt(prompt)
            return model, sys_prompt, temp

        # 2. MESSAGE_LOOKUP: Query DuckDB WhatsApp / Chat messages and use Fast Model
        if intent == "MESSAGE_LOOKUP":
            model = self.fast_model
            temp = 0.2

            lower_prompt = prompt.lower()
            if any(w in lower_prompt for w in ["last", "latest", "recent"]):
                messages = memory_service.get_recent_messages(limit=6)

            else:
                words = [
                    w.strip("?,!.") for w in prompt.split()
                    if w.lower() not in ("what", "did", "the", "a", "an", "is", "was", "any", "my", "me", "tell", "show", "have", "i", "got", "about", "whatsapp", "message", "messages", "text", "texts", "chat", "chats")
                ]
                search_term = " ".join(words)
                messages = memory_service.search_messages(search_term, limit=6) if search_term else memory_service.get_recent_messages(limit=6)
                if not messages:
                    messages = memory_service.get_recent_messages(limit=6)

            msg_lines = []
            for m in messages:
                direction = "Sent by me" if m.get("is_sent_by_me") else f"From {m.get('sender', '')}"
                msg_lines.append(
                    f"• [{m.get('date_str', '')}] In '{m.get('thread_title', '')}' - {direction}:\n"
                    f"  \"{m.get('content', '')}\""
                )
            context = "\n".join(msg_lines) if msg_lines else "No matching messages found in database."

            sys_prompt = (
                "You are a personal AI chat assistant. The user is asking about their WhatsApp messages and conversations.\n"
                "Here is the verified message data retrieved from their local database:\n\n"
                f"{context}\n\n"
                "Instructions:\n"
                "1. Answer the user's question directly and concisely based ONLY on the messages above.\n"
                "2. Explicitly note who sent the message, the contact/group name, and the timestamp.\n"
                "3. Be concise, direct, and factual."
            )
            return model, sys_prompt, temp

        # 2. EMAIL_LOOKUP: Query DuckDB and use Fast Model
        if intent == "EMAIL_LOOKUP":
            model = self.fast_model
            temp = 0.2  # Low temperature for strict factual accuracy

            lower_prompt = prompt.lower()
            if any(w in lower_prompt for w in ["last", "latest", "recent"]):
                emails = memory_service.get_recent_emails(limit=3)
            else:
                words = [
                    w.strip("?,!.") for w in prompt.split()
                    if w.lower() not in ("what", "did", "the", "a", "an", "is", "was", "any", "my", "me", "tell", "show", "have", "i", "got", "about", "email", "emails", "mail", "inbox")
                ]
                search_term = " ".join(words)
                emails = memory_service.search_emails(search_term, limit=3) if search_term else memory_service.get_recent_emails(limit=3)
                if not emails:
                    emails = memory_service.get_recent_emails(limit=3)

            email_lines = []
            for e in emails:
                email_lines.append(
                    f"• From: {e.get('sender', '')}\n"
                    f"  Date: {e.get('date', '')}\n"
                    f"  Subject: {e.get('subject', '')}\n"
                    f"  Content: {e.get('summary', '') or e.get('snippet', '')}"
                )
            emails_context = "\n\n".join(email_lines) if email_lines else "No matching emails found in database."

            sys_prompt = (
                "You are a personal AI email assistant. The user is asking about their emails.\n"
                "Here is the verified email data retrieved from their local database:\n\n"
                f"{emails_context}\n\n"
                "Instructions:\n"
                "1. Answer the user's question directly and concisely based ONLY on the email data above.\n"
                "2. Clearly mention the sender, subject, date, and key details.\n"
                "3. Do not assume or hallucinate details not present in the data."
            )
            return model, sys_prompt, temp

        # 2. DEEP_REASON: Complex logic/analysis using Reasoning Model
        elif intent == "DEEP_REASON":
            model = self.reasoning_model
            temp = temperature if temperature is not None else 0.6
            intermediate_context = memory_service.get_intermediate_context()
            parts = [
                system_prompt or (
                    "You are an expert analytical AI assistant. "
                    "Analyze the user's problem thoroughly and logically, considering constraints, trade-offs, and edge cases before providing your conclusion."
                )
            ]
            if intermediate_context:
                parts.append(intermediate_context)
            return model, "\n\n".join(parts), temp

        # 3. FAST_CHAT: Quick general chat, drafting, summarization using Fast Model
        else:
            model = self.fast_model
            temp = temperature if temperature is not None else self.temperature
            intermediate_context = memory_service.get_intermediate_context()
            parts = [system_prompt or self.system_prompt]
            if intermediate_context:
                parts.append(intermediate_context)
            return model, "\n\n".join(parts), temp

    def _build_payload(
        self,
        prompt: str,
        target_model: str,
        system_prompt: str,
        temperature: float,
        stream: bool = False
    ) -> Dict[str, Any]:
        return {
            "model": target_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }

    async def generate_reply(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> ChatResponse:
        """Blocking reply method with dynamic 3-model intent routing."""
        intent = await self.classify_intent(prompt)
        if intent == "CALL_CONTACT":
            card = await contacts_service.initiate_call_card(prompt)
            return ChatResponse(
                reply=card,
                thinking="Looking up verified contact and placing autonomous cellular call...",
                model=f"Autonomous Call Engine [{intent}]",
                total_duration_seconds=0.15
            )

        target_model, routed_sys_prompt, temp = self._prepare_routed_execution(
            prompt, intent, system_prompt, temperature
        )

        payload = self._build_payload(
            prompt=prompt,
            target_model=target_model,
            system_prompt=routed_sys_prompt,
            temperature=temp,
            stream=False
        )
        candidate_urls = self._get_target_urls()
        last_connect_error: Optional[Exception] = None

        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            logger.info(f"[Blocking] Querying Ollama at {endpoint} with routed model: {target_model} (Intent: {intent})")

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
                    model=f"{data.get('model', target_model)} [{intent}]",
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
                    detail=f"Request to model '{target_model}' timed out after {self.timeout}s."
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
        """Real-time SSE token stream generator with dynamic 3-model intent routing."""
        intent = await self.classify_intent(prompt)
        if intent == "CALL_CONTACT":
            yield f"data: {json.dumps({'type': 'thinking', 'token': 'Looking up contact and placing autonomous cellular call on phone SIM...', 'done': False})}\n\n"
            card = await contacts_service.initiate_call_card(prompt)
            yield f"data: {json.dumps({'type': 'answer', 'token': card, 'done': False})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'token': '', 'done': True, 'model': f'Autonomous Call Engine [{intent}]', 'intent': intent, 'total_duration_seconds': 0.15})}\n\n"
            return

        target_model, routed_sys_prompt, temp = self._prepare_routed_execution(
            prompt, intent, system_prompt, temperature
        )

        payload = self._build_payload(
            prompt=prompt,
            target_model=target_model,
            system_prompt=routed_sys_prompt,
            temperature=temp,
            stream=True
        )
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
                        "model": f"{chunk.get('model', target_model)} [{intent}]",
                        "intent": intent,
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
