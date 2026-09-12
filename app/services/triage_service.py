import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Set, Tuple, Optional

from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

# Known promotional / marketing brands and noise patterns
PROMOTIONAL_SENDERS = {
    "swiggy", "zomato", "bigbasket", "zepto", "blinkit", "uber", "ola", "rapido",
    "amazon", "flipkart", "myntra", "ajio", "tataneu", "meesho", "nykaa",
    "linkedin", "instagram", "facebook", "twitter", "x.com", "threads",
    "noreply", "no-reply", "donotreply", "mailer-daemon", "newsletter",
    "promotions", "marketing", "offers", "discount", "cashback", "hdfc", "icici", "sbi", "axis", "credimit"
}

# Regex patterns for detecting times & temporal commitments
TIME_REGEX = re.compile(
    r'\b(?:at\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\b|'
    r'\b(?:at\s+)(\d{1,2}(?::\d{2})?)\b|'
    r'\b(\d{1,2}\s*(?:o\'clock|am|pm|AM|PM))\b',
    re.IGNORECASE
)

COMMITMENT_KEYWORDS = [
    "meeting", "meet", "call", "sync", "discussion", "catch up", "catchup",
    "interview", "presentation", "demo", "review", "deadline", "submission",
    "submit", "exam", "quiz", "test", "class", "lecture", "lab", "appointment",
    "meet.google.com", "zoom.us", "teams.microsoft.com", "calendar"
]

QUESTION_KEYWORDS = [
    "?", "free", "are you", "when", "where", "what time", "can you",
    "could you", "let me know", "send me", "update", "status", "reach"
]


class TriageService:
    """Intelligent Cognitive Triage Engine.
    
    Segments incoming personal multi-modal data into priority tiers:
    1. Schedule & Commitments (Meetings, deadlines, time-sensitive tasks)
    2. People Waiting on You (1-on-1 personal chats awaiting reply)
    3. Important Academic / Work Correspondence
    4. Promotional & Low-Priority Noise (Summarized into 1 line)
    """

    def is_promotional(self, sender: str, subject: str = "", content: str = "") -> bool:
        """Determines whether an email or message is promotional noise."""
        search_text = f"{sender} {subject} {content[:150]}".lower()
        for kw in PROMOTIONAL_SENDERS:
            if kw in search_text:
                return True
        return False

    def extract_time_and_commitment(self, text: str) -> Tuple[Optional[str], bool]:
        """Detects if text mentions a meeting/deadline and extracts the time."""
        lower_text = text.lower()
        has_commitment = any(kw in lower_text for kw in COMMITMENT_KEYWORDS)
        
        match = TIME_REGEX.search(text)
        time_str = match.group(0).strip() if match else None
        
        return time_str, (has_commitment or bool(time_str and any(kw in lower_text for kw in ["today", "tomorrow", "tonight", "morning", "afternoon", "evening"])))

    def triage_daily_data(self) -> Dict[str, Any]:
        """Queries Working Memory (<48h) and triages all items into cognitive tiers."""
        # 1. Fetch recent messages & emails
        working_messages = memory_service.get_working_messages(limit=50)
        recent_emails = memory_service.get_recent_emails(limit=25)

        commitments: List[Dict[str, Any]] = []
        pending_people: Dict[str, Dict[str, Any]] = {}
        important_emails: List[Dict[str, Any]] = []
        promotional_brands: Set[str] = set()

        # --- A. Triage WhatsApp Messages ---
        for msg in working_messages:
            sender = msg.get("sender", "")
            thread_title = msg.get("thread_title", "")
            content = msg.get("content", "")
            is_sent_by_me = msg.get("is_sent_by_me", False)
            date_str = msg.get("date_str", "")

            # Check for promotional noise in chat (e.g. business accounts)
            if self.is_promotional(sender=sender, content=content):
                for kw in PROMOTIONAL_SENDERS:
                    if kw in (sender + " " + content[:60]).lower():
                        promotional_brands.add(kw.capitalize())
                continue

            # Check for schedule commitments / meetings
            time_str, is_commitment = self.extract_time_and_commitment(content)
            if is_commitment:
                commitments.append({
                    "time": time_str or "Scheduled / Deadline",
                    "source": "WhatsApp",
                    "contact": thread_title if thread_title != "Direct Chat" else sender,
                    "snippet": content[:180],
                    "date_str": date_str
                })

            # Check if this is a personal chat awaiting user reply
            if not is_sent_by_me:
                contact_name = thread_title if thread_title and thread_title != "Direct Chat" else sender
                if contact_name and contact_name.lower() not in ("me", "unknown"):
                    is_question = any(q in content.lower() for q in QUESTION_KEYWORDS)
                    # Keep latest message per person
                    if contact_name not in pending_people or is_question:
                        pending_people[contact_name] = {
                            "contact": contact_name,
                            "content": content[:160],
                            "date_str": date_str,
                            "is_question": is_question
                        }

        # --- B. Triage Gmail Messages ---
        for email in recent_emails:
            sender = email.get("sender", "")
            subject = email.get("subject", "")
            snippet = email.get("snippet", "") or email.get("summary", "")
            date_str = email.get("date", "")

            # Check for promotional noise
            if self.is_promotional(sender=sender, subject=subject, content=snippet):
                for kw in PROMOTIONAL_SENDERS:
                    if kw in (sender + " " + subject).lower():
                        promotional_brands.add(kw.capitalize())
                continue

            # Check for calendar/meeting invites
            time_str, is_commitment = self.extract_time_and_commitment(f"{subject} {snippet}")
            if is_commitment or "invitation:" in subject.lower():
                commitments.append({
                    "time": time_str or "Today",
                    "source": "Gmail",
                    "contact": sender.split("<")[0].strip(),
                    "snippet": f"{subject} — {snippet[:140]}",
                    "date_str": date_str
                })
            else:
                important_emails.append({
                    "sender": sender.split("<")[0].strip() or sender,
                    "subject": subject,
                    "snippet": snippet[:150],
                    "date_str": date_str
                })

        return {
            "commitments": commitments[:6],
            "pending_people": list(pending_people.values())[:5],
            "important_emails": important_emails[:4],
            "promotional_brands": sorted(list(promotional_brands))
        }

    def build_briefing_prompt(self, user_query: str) -> str:
        """Constructs a high-resolution, prioritized executive context for the Fast Model."""
        triage = self.triage_daily_data()
        now = datetime.now()
        
        # Friendly greeting by time of day
        hour = now.hour
        time_greeting = "Good morning" if 5 <= hour < 12 else ("Good afternoon" if 12 <= hour < 17 else "Good evening")
        current_time_str = now.strftime("%A, %d %B %Y at %I:%M %p")

        # 1. Format Commitments
        commit_lines = []
        if triage["commitments"]:
            for c in triage["commitments"]:
                commit_lines.append(f"• [{c['time']}] {c['contact']}: \"{c['snippet']}\" ({c['source']})")
        else:
            commit_lines.append("• No explicit meetings or hard deadlines detected in recent messages/emails.")

        # 2. Format People Waiting on You
        people_lines = []
        if triage["pending_people"]:
            for p in triage["pending_people"]:
                urgency = "⚠️ Awaiting Reply" if p["is_question"] else "💬 Recent message"
                people_lines.append(f"• {p['contact']} ({urgency}): \"{p['content']}\"")
        else:
            people_lines.append("• No pending questions from contacts.")

        # 3. Format Important Emails
        email_lines = []
        if triage["important_emails"]:
            for e in triage["important_emails"]:
                email_lines.append(f"• {e['sender']}: {e['subject']} — {e['snippet']}")
        else:
            email_lines.append("• No urgent non-promotional emails.")

        # 4. Format Promotional Noise
        promo_summary = ", ".join(triage["promotional_brands"][:6]) if triage["promotional_brands"] else "None"

        prompt_context = f"""
Current Date & Time: {current_time_str}

=== TRIAGED INTELLIGENCE DATA ===

[1. TODAY'S SCHEDULE, COMMITMENTS & MEETINGS]
{chr(10).join(commit_lines)}

[2. PEOPLE AWAITING YOUR REPLY]
{chr(10).join(people_lines)}

[3. IMPORTANT / OFFICIAL CORRESPONDENCE]
{chr(10).join(email_lines)}

[4. LOW-PRIORITY PROMOTIONAL NOISE (COLLAPSED)]
Filtered senders: {promo_summary}

=== EXECUTIVE BRIEFING INSTRUCTIONS ===
1. Start with an energetic, executive {time_greeting} greeting.
2. Present the briefing in strict order of importance:
   - 🗓️ **Today's Schedule & Commitments**: List meetings/deadlines in chronological order with 1-line context.
   - 💬 **People Waiting on You**: Clearly state who messaged and what they asked (e.g., Madhu asking if you're free).
   - 📬 **Important Updates**: 1-2 lines for significant emails or notices.
   - 🏷️ **Low-Priority Updates**: Mention filtered promo apps briefly in 1 single sentence (e.g. "You also have promos from Swiggy and BigBasket").
3. End with 1-2 proactive next-step offers (e.g. "Would you like me to draft a quick reply to [Name], or prepare notes for your [Time] meeting?").
4. Keep the tone sharp, executive, organized, and concise. No fluff.
"""
        return prompt_context


triage_service = TriageService()
