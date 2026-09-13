import os
import re
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


def _convert_pronouns(text: str) -> str:
    """Converts 3rd-person references referring to the recipient into 2nd-person."""
    text = re.sub(r"\bon\s+(?:his|her|their)\s+way\b", "on your way", text, flags=re.IGNORECASE)
    text = re.sub(r"\bwith\s+(?:him|her|them)\b", "with you", text, flags=re.IGNORECASE)
    text = re.sub(r"\bto\s+(?:him|her|them)\b", "to you", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfor\s+(?:him|her|them)\b", "for you", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:his|her|their)\s+(car|keys|phone|charger|office|house|home|bag|laptop|wallet|turn|place|side)\b", r"your \1", text, flags=re.IGNORECASE)
    return text


def clean_interpreted_message(raw_msg: str) -> str:
    """Cleans up raw message extractions, removing third-person meta-framing,
    fixing pronouns, and ensuring the message is written directly from the user's perspective.
    
    Examples:
      'tell amma that im going to ymca today' -> "I'm going to YMCA today."
      'him to come early' -> 'Please come early.'
      'to buy milk on his way' -> 'Please buy milk on your way.'
      'him not to wait for dinner' -> 'Please do not wait for dinner.'
      'that I will be 15 mins late' -> 'I will be 15 mins late.'
      'if he reached safely' -> 'Did you reach safely?'
    """
    if not raw_msg:
        return ""

    text = raw_msg.strip().strip('"\'')
    if not text:
        return ""

    # 1. Strip conversational meta-intents at the start (e.g. "tell amma that", "please tell mom", "ask prasad to", etc.)
    meta_prefixes = [
        # Match "tell <Name/Relation> that/saying/to/about..." or when "that" is omitted before I/I'm/we/my
        r"^(?:please\s+)?(?:tell|text|message|ask|inform|ping|remind)\s+(?:[A-Za-z0-9_'\s]+?)\s+(?:that\s+|saying\s+that\s+|saying\s+|to\s+|not\s+to\s+|if\s+|whether\s+|about\s+|(?=i\b|im\b|i'm\b|we\b|my\b))",
        r"^(?:please\s+)?(?:tell|text|message|ask|inform|ping|remind)\s+(?:him|her|them|someone|me)\s+(?:to\s+|that\s+)?",
        r"^(?:telling|saying|asking|informing)\s+(?:(?:[A-Za-z0-9_'\s]+?)\s+)?(?:to\s+|that\s+)?",
        r"^(?:saying\s+that|telling\s+that)\s+",
        r"^(?:saying|telling)\s+",
    ]
    for pattern in meta_prefixes:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

    # Handle negative commands: "him not to...", "her not to...", "not to...", "don't..."
    neg_match = re.match(r"^(?:(?:him|her|them|me)\s+)?(?:not\s+to|don't\s+to|dont\s+to|don't|dont)\s+(.+)$", text, re.IGNORECASE)
    if neg_match:
        body = neg_match.group(1).strip()
        body = _convert_pronouns(body)
        return f"Please do not {body.rstrip('.')}."

    # Handle "him to ...", "her to ...", "them to ...", "me to ...", "to ..."
    to_match = re.match(r"^(?:(?:him|her|them|me)\s+)?to\s+(.+)$", text, re.IGNORECASE)
    if to_match:
        text = to_match.group(1).strip()
    else:
        # Also handle bare "him that ...", "her that ..." or "that ..."
        that_match = re.match(r"^(?:(?:him|her|them|me)\s+)?that\s+(.+)$", text, re.IGNORECASE)
        if that_match:
            text = that_match.group(1).strip()
        else:
            # Handle stray leading pronouns: "him ...", "her ..."
            pronoun_lead = re.match(r"^(?:him|her|them)\s+(.+)$", text, re.IGNORECASE)
            if pronoun_lead:
                text = pronoun_lead.group(1).strip()

    # Handle auxiliary questions: "if he/she/they ...", "whether he/she/they ..."
    aux_match = re.match(r"^(?:if|whether)\s+(?:he|she|they|you)\s+(has|have|is|are|was|were|can|could|will|would)\s+(.+)$", text, re.IGNORECASE)
    if aux_match:
        aux = aux_match.group(1).lower()
        rest = aux_match.group(2).strip().rstrip("?.")
        aux_map = {"has": "have", "is": "are", "was": "were"}
        aux_2nd = aux_map.get(aux, aux).capitalize()
        rest = _convert_pronouns(rest)
        return f"{aux_2nd} you {rest}?"

    # Handle simple past question: "if he reached safely" -> "Did you reach safely?"
    q_simple = re.match(r"^(?:if|whether)\s+(?:he|she|they)\s+(.+)$", text, re.IGNORECASE)
    if q_simple:
        rest = q_simple.group(1).strip()
        rest = _convert_pronouns(rest)
        words = rest.split()
        if words:
            first_w = words[0].lower()
            past_to_base = {"reached": "reach", "came": "come", "got": "get", "left": "leave", "called": "call", "finished": "finish"}
            if first_w in past_to_base:
                words[0] = past_to_base[first_w]
                return f"Did you {' '.join(words).rstrip('?.')}?"
            elif first_w.endswith("ed"):
                base = first_w[:-2] if not first_w.endswith("eed") else first_w[:-1]
                words[0] = base
                return f"Did you {' '.join(words).rstrip('?.')}?"
        return f"Did you {rest.rstrip('?.')}?"

    # Convert remaining pronouns
    text = _convert_pronouns(text)

    # Imperative verb detection vs First-person statements
    words = text.split()
    if words:
        first = words[0].lower()
        first_person_starts = {
            "i", "i'm", "im", "i've", "ive", "i'll", "ill", "we", "we're", "we'll",
            "please", "can", "could", "would", "will", "are", "is", "did", "do",
            "hey", "hi", "hello", "sorry", "thanks", "thank", "good", "happy", "yes", "no", "ok", "okay"
        }
        # Notice: 'tell', 'ask', 'remind', 'inform' are intentionally excluded here so they are never prepended with 'Please'
        imperative_verbs = {
            "come", "bring", "buy", "pick", "call", "send", "reach", "get", "check",
            "take", "give", "wait", "meet", "let", "order", "start", "finish", "stop",
            "leave", "drop", "make", "help", "pay", "share", "forward", "update",
            "see", "show", "open", "close", "turn", "switch", "keep", "hold", "stay", "go"
        }
        if first in imperative_verbs:
            words[0] = words[0].lower()
            text = "Please " + " ".join(words)
        elif first == "i" or text.startswith("i "):
            text = "I " + text[2:]
        elif first in ("i'm", "im"):
            text = "I'm " + (" ".join(words[1:]) if len(words) > 1 else "")
        elif first in ("i'll", "ill"):
            text = "I'll " + (" ".join(words[1:]) if len(words) > 1 else "")
        elif first in ("i've", "ive"):
            text = "I've " + (" ".join(words[1:]) if len(words) > 1 else "")
        elif first not in first_person_starts and not text.startswith("Please"):
            text = text[0].upper() + text[1:]
        else:
            text = text[0].upper() + text[1:]

    # Ensure ending punctuation
    if text and text[-1] not in (".", "?", "!"):
        if any(text.lower().startswith(q) for q in ["did ", "are ", "is ", "can ", "could ", "what ", "where ", "when ", "why ", "how ", "have ", "will "]):
            text += "?"
        else:
            text += "."

    return text


def extract_followup_intent(prompt: str, history: Optional[List[Dict[str, str]]]) -> tuple[str, str]:
    """Extracts drafted message and recipient from conversation history for follow-ups like 'send that to him in whatsapp'."""
    clean = prompt.strip()
    followup_patterns = [
        r"^(?:send|text|forward)\s+(?:that|this|it)\s+(?:message\s+)?(?:to\s+([A-Za-z0-9\s+]+?))?(?:\s+(?:in|on|via|through)\s+whatsapp)?$",
        r"^(?:send|forward)\s+(?:it|this|that)(?:\s+(?:in|on|via|through)\s+whatsapp)?$",
        r"^(?:yes|sure|ok|okay)?\s*(?:send\s+(?:it|that|this)|do\s+it)(?:\s+(?:to\s+([A-Za-z0-9\s+]+?))?)?(?:\s+(?:in|on|via|through)\s+whatsapp)?$"
    ]
    matched = False
    explicit_recip = ""
    for pat in followup_patterns:
        m = re.search(pat, clean, re.IGNORECASE)
        if m:
            matched = True
            if m.groups() and m.group(1):
                explicit_recip = m.group(1).strip()
            break

    if not matched:
        return "", ""

    recip = explicit_recip
    msg = ""
    last_assistant_msg = ""
    if history:
        for turn in reversed(history):
            if turn.get("role") == "assistant":
                last_assistant_msg = turn.get("content", "")
                break

    # If recipient is a pronoun or missing, check previous turns
    if not recip or recip.lower() in ("him", "her", "them", "someone", "it", "that"):
        if history:
            for turn in reversed(history):
                content = str(turn.get("content", ""))
                for known in ["Prasad Appa", "Prasad", "Appa", "Madhu", "Rachit", "Amma", "Mom", "Dad"]:
                    if known.lower() in content.lower():
                        recip = known
                        break
                if recip and recip.lower() not in ("him", "her", "them"):
                    break

    # Extract drafted message from last assistant turn
    if last_assistant_msg:
        quote_matches = re.findall(r'"([^"]{5,})"', last_assistant_msg)
        if quote_matches:
            msg = max(quote_matches, key=len)
        else:
            lines = [l.strip() for l in last_assistant_msg.split("\n") if l.strip()]
            for l in lines:
                if not l.startswith(("[", "Note:", "Reason:", "*", "Thought")):
                    msg = l
                    break

    return recip, msg




LLM_ACTION_SYSTEM_PROMPT = (
    "You are an autonomous executive AI assistant action engine.\n"
    "Your job is to understand the user's intent from their request and recent conversation history, "
    "and output a single JSON action object.\n\n"
    "CRITICAL RULES:\n"
    "1. The user NEVER wants you to roleplay, draft, or simulate messages in the chat box.\n"
    "2. When action is 'whatsapp', the 'message' field MUST be written completely from the USER'S direct first-person perspective, "
    "exactly as if the user typed it themselves on their own phone.\n"
    "3. NEVER include conversational meta-framing like 'tell amma that', 'tell him that', 'ask her to', or 'Please tell...'.\n"
    "   - For personal updates ('tell amma that im going to ymca today'), the message is simply: \"I'm going to YMCA today.\"\n"
    "   - For status/arrival updates ('tell dad ill be 10 mins late'), the message is: \"I will be 10 minutes late.\"\n"
    "   - For requests to the recipient ('ask prasad to buy pizza'), the message is a polite direct request: \"Please buy pizza.\"\n"
    "   - For negative commands ('tell mom not to wait for dinner'), the message is: \"Please do not wait for me for dinner.\"\n"
    "4. If the user asks to phone, dial, call, ring, or get contact details of someone, choose action 'call'.\n"
    "5. If the user asks about today's agenda, briefing, schedule, or updates, choose action 'daily_briefing'.\n"
    "6. If the user asks to search or read their past messages/chats, choose action 'message_lookup'.\n"
    "7. If the user asks to search or read their emails, choose action 'email_lookup'.\n"
    "8. For general questions, explanations, greetings, or analytical reasoning, choose action 'chat'.\n\n"
    "You MUST respond ONLY with valid JSON in this schema:\n"
    "{\n"
    '  "action": "whatsapp" | "call" | "daily_briefing" | "message_lookup" | "email_lookup" | "chat",\n'
    '  "recipient": "person name, relationship (e.g. appa, mom, amma), or phone number (empty if not applicable)",\n'
    '  "message": "first-person message to send to recipient (e.g. \'I\'m going to YMCA today.\') if whatsapp, else empty",\n'
    '  "query": "search query if message_lookup or email_lookup, else empty"\n'
    "}\n\n"
    "Examples:\n"
    "- 'tell amma that im going to ymca today' -> {\"action\": \"whatsapp\", \"recipient\": \"amma\", \"message\": \"I'm going to YMCA today.\", \"query\": \"\"}\n"
    "- 'tell dad that ill be late' -> {\"action\": \"whatsapp\", \"recipient\": \"dad\", \"message\": \"I'll be late.\", \"query\": \"\"}\n"
    "- 'tell prasad that the server is updated' -> {\"action\": \"whatsapp\", \"recipient\": \"prasad\", \"message\": \"The server is updated.\", \"query\": \"\"}\n"
    "- 'Ask Prasad to buy pizza and come home today' -> {\"action\": \"whatsapp\", \"recipient\": \"Prasad\", \"message\": \"Please buy pizza and come home today.\", \"query\": \"\"}\n"
    "- 'Text appa telling him to come early' -> {\"action\": \"whatsapp\", \"recipient\": \"appa\", \"message\": \"Please come early.\", \"query\": \"\"}\n"
    "- 'tell mom not to wait for dinner' -> {\"action\": \"whatsapp\", \"recipient\": \"mom\", \"message\": \"Please do not wait for me for dinner.\", \"query\": \"\"}\n"
    "- 'call appa' -> {\"action\": \"call\", \"recipient\": \"appa\", \"message\": \"\", \"query\": \"\"}\n"
    "- 'send that to him in whatsapp' -> {\"action\": \"whatsapp\", \"recipient\": \"<resolved from history>\", \"message\": \"<extracted from previous turn>\", \"query\": \"\"}\n"
    "- 'what was my last email?' -> {\"action\": \"email_lookup\", \"recipient\": \"\", \"message\": \"\", \"query\": \"last email\"}\n"
    "- 'did anyone text me about dinner?' -> {\"action\": \"message_lookup\", \"recipient\": \"\", \"message\": \"\", \"query\": \"dinner\"}\n"
    "- 'what\\'s on my plate today?' -> {\"action\": \"daily_briefing\", \"recipient\": \"\", \"message\": \"\", \"query\": \"\"}\n"
    "- 'how do black holes form?' -> {\"action\": \"chat\", \"recipient\": \"\", \"message\": \"\", \"query\": \"\"}"
)


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

    async def resolve_action(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """LLM-native action engine. Understands intent, recipient, and message in a single warm call.
        Eliminates regex rules and brittle pattern matching.
        """
        # Format conversation history into prompt context
        history_snippet = ""
        if history:
            turns = []
            for h in history[-8:]:
                r = "User" if h.get("role") == "user" else "Assistant"
                c = str(h.get("content", "")).strip().replace("\n", " ")
                if c:
                    turns.append(f"{r}: {c[:300]}")
            if turns:
                history_snippet = "Recent Conversation History:\n" + "\n".join(turns) + "\n\n"

        user_content = f"{history_snippet}User request: \"{prompt}\"\n\nJSON output:"

        payload = {
            "model": self.fast_model,
            "format": "json",
            "messages": [
                {"role": "system", "content": LLM_ACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            "stream": False,
            "options": {
                "temperature": 0.0,
                "num_predict": 350
            }
        }

        candidate_urls = self._get_target_urls()
        for base_url in candidate_urls:
            endpoint = f"{base_url}/api/chat"
            logger.info(f"[Action Engine: LLM] Querying model='{self.fast_model}' at {endpoint} (timeout=25.0s, format=json) for: '{prompt[:60]}'")
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(endpoint, json=payload)
                if resp.status_code == 200:
                    msg_obj = resp.json().get("message", {})
                    raw_content = msg_obj.get("content", "")
                    raw_thinking = msg_obj.get("thinking", "")

                    # Extract JSON object from content or thinking
                    json_str = raw_content
                    if not json_str or "{" not in json_str:
                        json_str = raw_thinking

                    match = re.search(r"\{.*?\}", json_str, re.DOTALL)
                    if match:
                        parsed = json.loads(match.group(0))
                        if isinstance(parsed, dict) and "action" in parsed:
                            action = str(parsed.get("action", "chat")).lower().strip()
                            recip = str(parsed.get("recipient", "")).strip()
                            msg = str(parsed.get("message", "")).strip()

                            # If action is whatsapp and message/recip was blank for a follow-up, check history
                            if action == "whatsapp":
                                if not recip or recip.lower() in ("him", "her", "them", "someone", "it"):
                                    f_recip, f_msg = extract_followup_intent(prompt, history)
                                    if f_recip:
                                        recip = f_recip
                                    if not msg and f_msg:
                                        msg = f_msg

                                if msg:
                                    msg = clean_interpreted_message(msg)

                            parsed["action"] = action
                            parsed["recipient"] = recip
                            parsed["message"] = msg
                            logger.info(f"[Action Engine: LLM] Resolved: action='{action}', recipient='{recip}', message='{msg}'")
                            return parsed
            except Exception as exc:
                logger.warning(f"[Action Engine: LLM] Call to {self.fast_model} failed on {base_url}: {exc}")
                continue

        # Fallback if Ollama is unreachable
        logger.warning(f"[Action Engine: Fallback] LLM action resolution unavailable for: '{prompt[:50]}'")
        lower = prompt.lower().strip()
        if any(lower.startswith(p) for p in ["call ", "ring ", "dial "]):
            target = re.sub(r"^(?:call|ring|dial)\s+", "", prompt, flags=re.IGNORECASE).strip()
            return {"action": "call", "recipient": target, "message": "", "query": ""}
        return {"action": "chat", "recipient": "", "message": "", "query": ""}

    async def classify_intent(self, user_prompt: str) -> str:
        """Backward-compatibility wrapper delegating to resolve_action."""
        action_data = await self.resolve_action(user_prompt)
        action = action_data.get("action", "chat")
        mapping = {
            "whatsapp": "SEND_WHATSAPP",
            "call": "CALL_CONTACT",
            "daily_briefing": "DAILY_BRIEFING",
            "message_lookup": "MESSAGE_LOOKUP",
            "email_lookup": "EMAIL_LOOKUP",
            "chat": "FAST_CHAT",
        }
        return mapping.get(action, "FAST_CHAT")

    def _prepare_routed_execution(
        self,
        prompt: str,
        intent: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None
    ) -> tuple[str, str, float]:
        """Prepares destination model, focused system prompt, and temperature based on intent."""

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
        stream: bool = False,
        history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for turn in history:
                role = turn.get("role")
                content = turn.get("content")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": str(content)})
        messages.append({"role": "user", "content": prompt})

        return {
            "model": target_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature
            }
        }

    async def generate_reply(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> ChatResponse:
        """Blocking reply method with dynamic action resolution and conversation memory."""
        action_data = await self.resolve_action(prompt, history)
        action = action_data.get("action", "chat")
        recipient = action_data.get("recipient", "").strip()
        message_text = action_data.get("message", "").strip()
        query_text = action_data.get("query", "").strip()

        if action == "whatsapp":
            if not recipient:
                return ChatResponse(
                    reply="Who would you like to message on WhatsApp, and what should I say?\n\n*Example:* `Tell Madhu I will be there in 10 minutes`",
                    thinking="Detected WhatsApp action but could not identify the recipient.",
                    model=f"Action Engine [{self.fast_model}]",
                    total_duration_seconds=0.05
                )
            cleaned_msg = clean_interpreted_message(message_text) if message_text else message_text
            card = await contacts_service.send_whatsapp_message(recipient, cleaned_msg)
            return ChatResponse(
                reply=card,
                thinking=f"Executing WhatsApp action: sending message to {recipient}...",
                model=f"Action Engine [{self.fast_model}]",
                total_duration_seconds=0.35
            )

        if action == "call":
            target = recipient or prompt
            card = await contacts_service.initiate_call_card(target)
            return ChatResponse(
                reply=card,
                thinking=f"Executing cellular call action: placing call to {target}...",
                model=f"Action Engine [{self.fast_model}]",
                total_duration_seconds=0.15
            )

        action_to_intent = {
            "daily_briefing": "DAILY_BRIEFING",
            "message_lookup": "MESSAGE_LOOKUP",
            "email_lookup": "EMAIL_LOOKUP",
            "deep_reason": "DEEP_REASON",
            "chat": "FAST_CHAT",
        }
        intent = action_to_intent.get(action, "FAST_CHAT")
        lookup_prompt = query_text if (action in ("message_lookup", "email_lookup") and query_text) else prompt

        target_model, routed_sys_prompt, temp = self._prepare_routed_execution(
            lookup_prompt, intent, system_prompt, temperature
        )

        payload = self._build_payload(
            prompt=prompt,
            target_model=target_model,
            system_prompt=routed_sys_prompt,
            temperature=temp,
            stream=False,
            history=history
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
        temperature: Optional[float] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """Real-time SSE token stream generator with dynamic action resolution and conversation memory."""
        action_data = await self.resolve_action(prompt, history)
        action = action_data.get("action", "chat")
        recipient = action_data.get("recipient", "").strip()
        message_text = action_data.get("message", "").strip()
        query_text = action_data.get("query", "").strip()

        if action == "whatsapp":
            if not recipient:
                reply_payload = json.dumps({"type": "answer", "token": "Who would you like to message on WhatsApp, and what should I say?\n\n*Example:* `Tell Madhu I will be there in 10 minutes`", "done": False})
                done_payload = json.dumps({"type": "done", "token": "", "done": True, "model": f"Action Engine [{self.fast_model}]", "intent": "SEND_WHATSAPP", "total_duration_seconds": 0.05})
                yield f"data: {reply_payload}\n\n"
                yield f"data: {done_payload}\n\n"
                return

            cleaned_msg = clean_interpreted_message(message_text) if message_text else message_text
            thinking_payload = json.dumps({"type": "thinking", "token": f'Sending WhatsApp to {recipient} with message: "{cleaned_msg}"...', "done": False})
            yield f"data: {thinking_payload}\n\n"
            card = await contacts_service.send_whatsapp_message(recipient, cleaned_msg)
            card_payload = json.dumps({"type": "answer", "token": card, "done": False})
            yield f"data: {card_payload}\n\n"
            done_payload = json.dumps({"type": "done", "token": "", "done": True, "model": f"Action Engine [{self.fast_model}]", "intent": "SEND_WHATSAPP", "total_duration_seconds": 0.35})
            yield f"data: {done_payload}\n\n"
            return

        if action == "call":
            target = recipient or prompt
            thinking_payload = json.dumps({"type": "thinking", "token": f"Looking up {target} and placing autonomous cellular call on phone SIM...", "done": False})
            yield f"data: {thinking_payload}\n\n"
            card = await contacts_service.initiate_call_card(target)
            card_payload = json.dumps({"type": "answer", "token": card, "done": False})
            yield f"data: {card_payload}\n\n"
            done_payload = json.dumps({"type": "done", "token": "", "done": True, "model": f"Action Engine [{self.fast_model}]", "intent": "CALL_CONTACT", "total_duration_seconds": 0.15})
            yield f"data: {done_payload}\n\n"
            return

        action_to_intent = {
            "daily_briefing": "DAILY_BRIEFING",
            "message_lookup": "MESSAGE_LOOKUP",
            "email_lookup": "EMAIL_LOOKUP",
            "deep_reason": "DEEP_REASON",
            "chat": "FAST_CHAT",
        }
        intent = action_to_intent.get(action, "FAST_CHAT")
        lookup_prompt = query_text if (action in ("message_lookup", "email_lookup") and query_text) else prompt

        target_model, routed_sys_prompt, temp = self._prepare_routed_execution(
            lookup_prompt, intent, system_prompt, temperature
        )

        payload = self._build_payload(
            prompt=prompt,
            target_model=target_model,
            system_prompt=routed_sys_prompt,
            temperature=temp,
            stream=True,
            history=history
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
