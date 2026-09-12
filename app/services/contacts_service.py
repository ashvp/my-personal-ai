import os
import sys
import re
import sqlite3
import logging
from typing import Dict, Any, List, Optional

import httpx
from app.config import settings
from app.services.memory_service import memory_service
from app.services.whatsapp_service import get_beeper_db_path, DEFAULT_BEEPER_DB_PATH

logger = logging.getLogger(__name__)


def format_phone_for_dialer(raw_phone: str) -> str:
    """Cleans phone number for Indian cellular SIM dialing.
    
    If it has 12 digits starting with '91' (e.g. 919940020084 or +919940020084),
    strips the '91' country code so the phone directly dials the 10-digit mobile number
    (e.g. 9940020084) on the Indian telecom network.
    """
    digits = re.sub(r"[^\d]", "", raw_phone)
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]  # 10 digits
    if len(digits) == 10:
        return digits
    return digits


class ContactsService:
    """Manages verified contact synchronization and 1-tap cellular call & message cards.
    
    Reads from local Beeper SQLite store (bridges from Google Contacts, WhatsApp, and Android SMS),
    deduplicates human names and phone numbers, and indexes them in DuckDB for instant sub-second lookup.
    """

    def __init__(self, db_path: str = DEFAULT_BEEPER_DB_PATH):
        self.db_path = db_path

    def is_available(self) -> bool:
        return bool(self.db_path and os.path.exists(self.db_path))

    def _get_sqlite_connection(self):
        if not self.is_available():
            raise FileNotFoundError(f"Beeper database not found at {self.db_path}")

        # In WSL accessing Windows /mnt/c, SQLite WAL shared-memory locks fail over DrvFS.
        # Making a fast snapshot in /tmp bypasses DrvFS locking entirely.
        if "/mnt/" in self.db_path or sys.platform != "win32":
            import shutil
            import tempfile

            temp_dir = tempfile.gettempdir()
            snapshot_db = os.path.join(temp_dir, "beeper_contacts_snapshot.db")
            shutil.copy2(self.db_path, snapshot_db)

            for ext in ["-wal", "-shm"]:
                wal_file = self.db_path + ext
                if os.path.exists(wal_file):
                    try:
                        shutil.copy2(wal_file, snapshot_db + ext)
                    except Exception:
                        pass

            return sqlite3.connect(snapshot_db)

        uri = f"file:{self.db_path}?mode=ro"
        return sqlite3.connect(uri, uri=True)

    def sync_contacts(self) -> Dict[str, Any]:
        """Syncs all contacts and verified phone numbers from Beeper into DuckDB."""
        if not self.is_available():
            return {
                "success": False,
                "message": f"Beeper database not found at {self.db_path}. Ensure Beeper is installed."
            }

        try:
            conn = self._get_sqlite_connection()
            cursor = conn.cursor()

            # Query participants and their phone identifiers
            cursor.execute("""
                SELECT
                    COALESCE(p.full_name, p.nickname, '') as name,
                    pi.identifier as phone_number
                FROM participants p
                JOIN participant_identifiers pi ON p.id = pi.participant_id
                WHERE pi.identifier_type = 'phone'
                  AND (p.is_self = 0 OR p.is_self IS NULL);
            """)
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return {
                    "success": True,
                    "synced_count": 0,
                    "message": "No phone identifiers found in Beeper participants store."
                }

            # Deduplicate by phone number, prioritizing friendly human names over raw digits
            contacts_map: Dict[str, str] = {}
            for raw_name, raw_phone in rows:
                phone = (raw_phone or "").strip()
                name = (raw_name or "").strip()
                if not phone or len(phone) < 5:
                    continue

                if phone not in contacts_map:
                    contacts_map[phone] = name or phone
                else:
                    curr_name = contacts_map[phone]
                    # Upgrade if current name is a raw number and new name is a human name
                    if (curr_name == phone or curr_name.startswith("+")) and name and not name.startswith("+"):
                        contacts_map[phone] = name

            records = []
            named_count = 0
            for phone, name in contacts_map.items():
                clean_id = re.sub(r"[^a-zA-Z0-9_]", "_", phone)
                records.append({
                    "id": f"contact_{clean_id}",
                    "name": name,
                    "phone_number": phone,
                    "source": "beeper"
                })
                if not name.startswith("+"):
                    named_count += 1

            # Store in DuckDB via SQLAlchemy ORM
            saved = memory_service.store_contacts_batch(records)
            logger.info(f"Ingested {saved} unique contacts ({named_count} named) into DuckDB.")

            return {
                "success": True,
                "synced_count": saved,
                "named_contacts": named_count,
                "message": f"Successfully indexed {saved} contacts ({named_count} named people) into DuckDB."
            }

        except Exception as exc:
            logger.exception("Error syncing contacts from Beeper")
            return {
                "success": False,
                "message": f"Contact sync failed: {str(exc)}"
            }

    def find_contact(self, name_or_query: str) -> Optional[Dict[str, Any]]:
        """Looks up a contact in DuckDB."""
        return memory_service.find_contact(name_or_query)

    def search_contacts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches contacts in DuckDB."""
        return memory_service.search_contacts(query, limit=limit)

    # --- Autonomous Cellular Calling Engine ---

    async def trigger_autonomous_call(self, phone_number: str) -> Dict[str, Any]:
        """Silently and autonomously triggers a direct cellular phone call on the user's Android SIM
        via MacroDroid Webhook.
        """
        webhook_url = getattr(settings, "MACRODROID_WEBHOOK_URL", None) or os.getenv("MACRODROID_WEBHOOK_URL")
        if not webhook_url:
            return {"triggered": False, "reason": "MACRODROID_WEBHOOK_URL not configured in .env"}

        dial_number = format_phone_for_dialer(phone_number)
        target_url = f"{webhook_url.rstrip('/')}?+{dial_number}"
        logger.info(f"Triggering autonomous cellular call via MacroDroid: {target_url} (raw: {phone_number})")

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(target_url)
                if res.status_code in (200, 204):
                    logger.info(f"MacroDroid successfully initiated cellular call to {dial_number}")
                    return {"triggered": True, "target": dial_number}
                else:
                    logger.warning(f"MacroDroid returned status {res.status_code}: {res.text}")
                    return {"triggered": False, "status_code": res.status_code, "error": res.text}
        except Exception as exc:
            logger.exception(f"Error calling MacroDroid webhook: {exc}")
            return {"triggered": False, "error": str(exc)}

    def trigger_autonomous_call_sync(self, phone_number: str) -> Dict[str, Any]:
        """Synchronous version of trigger_autonomous_call."""
        webhook_url = getattr(settings, "MACRODROID_WEBHOOK_URL", None) or os.getenv("MACRODROID_WEBHOOK_URL")
        if not webhook_url:
            return {"triggered": False, "reason": "MACRODROID_WEBHOOK_URL not configured in .env"}

        dial_number = format_phone_for_dialer(phone_number)
        target_url = f"{webhook_url.rstrip('/')}?+{dial_number}"
        logger.info(f"[Sync] Triggering autonomous cellular call via MacroDroid: {target_url} (raw: {phone_number})")

        try:
            res = httpx.get(target_url, timeout=6.0)
            if res.status_code in (200, 204):
                return {"triggered": True, "target": dial_number}
            else:
                return {"triggered": False, "status_code": res.status_code, "error": res.text}
        except Exception as exc:
            logger.exception(f"Error calling MacroDroid webhook: {exc}")
            return {"triggered": False, "error": str(exc)}

    async def initiate_call_card(self, name_or_query: str) -> str:
        """Autonomously dials the contact via MacroDroid and returns a rich confirmation card."""
        contact = self.find_contact(name_or_query)

        if not contact:
            suggestions = self.search_contacts(name_or_query, limit=4)
            if suggestions:
                lines = [
                    f"I couldn't find an exact match for **{name_or_query}**, but found these contacts in your phonebook:",
                    ""
                ]
                for s in suggestions:
                    phone = s.get("phone_number", "")
                    name = s.get("name", "Unknown")
                    lines.append(f"• **{name}** (`{phone}`) — Ask me to *\"Call {name}\"*")
                return "\n".join(lines)
            else:
                return (
                    f"I couldn't find a contact named **{name_or_query}** in your local contacts database.\n\n"
                    "You can ask me to search contacts or check spelling."
                )

        name = contact.get("name", name_or_query)
        phone = contact.get("phone_number", "")
        clean_phone = phone.strip()
        dial_number = format_phone_for_dialer(clean_phone)
        wa_phone = re.sub(r"[^\d]", "", clean_phone)

        # 1. Autonomously trigger the call on phone SIM
        call_res = await self.trigger_autonomous_call(dial_number)

        # 2. Fetch recent conversational context with this person
        recent_narrative = memory_service.get_episodic_narrative(name, limit=2)
        context_block = ""
        if recent_narrative:
            last_msg = recent_narrative[-1]
            sender = last_msg.get("sender", "Them")
            content = last_msg.get("content", "")
            date_str = last_msg.get("date_str", "")
            context_block = (
                f"\n\n> 💬 **Last Conversation ({date_str}):**\n"
                f"> *{sender}:* \"{content[:120]}\""
            )

        if call_res.get("triggered"):
            card = (
                f"### 📞 Calling **{name}**...\n"
                f"**Dialing:** `{dial_number}` on your phone's cellular SIM\n\n"
                f"🟢 **Autonomous Call Placed!**\n"
                f"Your Android phone is placing the direct cellular call to **{name}** (`{dial_number}`) right now. Pick up your phone to speak!{context_block}\n\n"
                f"---\n"
                f"*Quick Actions:* [💬 Message on WhatsApp](https://wa.me/{wa_phone}) | [📱 Send SMS](sms:{dial_number}) | [Manual Dial](tel:{dial_number})"
            )
        else:
            err = call_res.get("error") or call_res.get("reason", "Webhook error")
            card = (
                f"### 📞 Outgoing Call: **{name}**\n"
                f"**Number:** `{dial_number}`{context_block}\n\n"
                f"⚠️ *Autonomous trigger noticed an issue ({err}). Tap below to dial directly:*\n\n"
                f"[🟢 Tap to Call {name}](tel:{dial_number})\n\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_number})"
            )

        return card

    def generate_call_card_markdown(self, name_or_query: str) -> str:
        """Synchronous wrapper for autonomous calling and markdown generation."""
        contact = self.find_contact(name_or_query)

        if not contact:
            suggestions = self.search_contacts(name_or_query, limit=4)
            if suggestions:
                lines = [
                    f"I couldn't find an exact match for **{name_or_query}**, but found these similar contacts:",
                    ""
                ]
                for s in suggestions:
                    phone = s.get("phone_number", "")
                    name = s.get("name", "Unknown")
                    lines.append(f"• **{name}** (`{phone}`) — Ask me to *\"Call {name}\"*")
                return "\n".join(lines)
            else:
                return (
                    f"I couldn't find a contact named **{name_or_query}** in your local contacts database.\n\n"
                    "You can trigger a contact sync or verify the spelling."
                )

        name = contact.get("name", name_or_query)
        phone = contact.get("phone_number", "")
        clean_phone = phone.strip()
        dial_number = format_phone_for_dialer(clean_phone)
        wa_phone = re.sub(r"[^\d]", "", clean_phone)

        # 1. Trigger call synchronously
        call_res = self.trigger_autonomous_call_sync(dial_number)

        # 2. Context
        recent_narrative = memory_service.get_episodic_narrative(name, limit=2)
        context_block = ""
        if recent_narrative:
            last_msg = recent_narrative[-1]
            sender = last_msg.get("sender", "Them")
            content = last_msg.get("content", "")
            date_str = last_msg.get("date_str", "")
            context_block = (
                f"\n\n> 💬 **Last Message ({date_str}):**\n"
                f"> *{sender}:* \"{content[:120]}\""
            )

        if call_res.get("triggered"):
            card = (
                f"### 📞 Calling **{name}**...\n"
                f"**Dialing:** `{dial_number}` on your phone's cellular SIM\n\n"
                f"🟢 **Autonomous Call Placed!**\n"
                f"Your phone is dialing {name} (`{dial_number}`) right now. Pick up to speak!{context_block}\n\n"
                f"---\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_number}) | [Re-dial](tel:{dial_number})"
            )
        else:
            err = call_res.get("error") or call_res.get("reason", "Webhook error")
            card = (
                f"### 📞 Outgoing Call: **{name}**\n"
                f"**Number:** `{dial_number}`{context_block}\n\n"
                f"⚠️ *Could not auto-dial ({err}). Manual fallback:*\n\n"
                f"[🟢 Tap to Call {name}](tel:{dial_number})\n\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_number})"
            )

        return card


contacts_service = ContactsService()


def get_contacts_service() -> ContactsService:
    return contacts_service
