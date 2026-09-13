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

import urllib.parse

logger = logging.getLogger(__name__)


def format_phone_for_dialer(raw_phone: str) -> str:
    """Cleans phone number for Indian cellular SIM dialing (10 digits) or international dialing."""
    digits = re.sub(r"[^\d]", "", raw_phone)
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        return digits[1:]
    if len(digits) == 10:
        return digits
    if raw_phone.strip().startswith("+"):
        return f"+{digits}"
    return digits


def format_phone_for_whatsapp(raw_phone: str) -> str:
    """Formats phone number for WhatsApp with country code (e.g. 919940020084)."""
    digits = re.sub(r"[^\d]", "", raw_phone)
    if len(digits) == 10:
        return f"91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
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

        return sqlite3.connect(self.db_path)

    def sync_contacts(self) -> Dict[str, Any]:
        """Alias for sync_contacts_from_beeper used by background sync service."""
        return self.sync_contacts_from_beeper()

    def sync_contacts_from_beeper(self) -> Dict[str, Any]:
        """Reads distinct verified human contacts from Beeper SQLite and synchronizes to DuckDB."""
        if not self.is_available():
            return {
                "success": False,
                "message": f"Beeper store not found at {self.db_path}"
            }

        try:
            conn = self._get_sqlite_connection()
            cursor = conn.cursor()

            query = """
                SELECT DISTINCT 
                    COALESCE(u.full_name, c.display_name, '') as name,
                    COALESCE(u.phone_number, '') as phone_number,
                    c.id as contact_id,
                    'beeper' as source
                FROM contacts c
                LEFT JOIN contact_phones cp ON c.id = cp.contact_id
                LEFT JOIN users u ON cp.phone_number = u.phone_number
                WHERE (u.phone_number IS NOT NULL AND u.phone_number != '')
                   OR (cp.phone_number IS NOT NULL AND cp.phone_number != '')
            """
            try:
                cursor.execute(query)
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                cursor.execute("""
                    SELECT DISTINCT 
                        display_name as name,
                        phone_number,
                        id as contact_id,
                        'beeper' as source
                    FROM contacts
                    WHERE phone_number IS NOT NULL AND phone_number != ''
                """)
                rows = cursor.fetchall()

            contacts_to_index = []
            seen_phones = set()

            for row in rows:
                name = (row[0] or "").strip()
                raw_phone = (row[1] or "").strip()
                contact_id = str(row[2]) if len(row) > 2 else ""

                if not name or not raw_phone:
                    continue

                clean_phone = re.sub(r"[^\d+]", "", raw_phone)
                if clean_phone in seen_phones:
                    continue
                seen_phones.add(clean_phone)

                contacts_to_index.append({
                    "id": contact_id or f"cnt_{clean_phone}",
                    "name": name,
                    "phone_number": clean_phone,
                    "normalized_name": name.lower(),
                    "source": "beeper_contacts"
                })

            conn.close()

            if contacts_to_index:
                memory_service.index_contacts(contacts_to_index)
                logger.info(f"Synchronized and indexed {len(contacts_to_index)} contacts from Beeper into DuckDB.")

            return {
                "success": True,
                "count": len(contacts_to_index),
                "synced_count": len(contacts_to_index),
                "named_contacts": len(contacts_to_index),
                "message": f"Successfully indexed {len(contacts_to_index)} contacts."
            }

        except Exception as exc:
            logger.exception("Error syncing contacts from Beeper SQLite store")
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

        dial_phone = format_phone_for_dialer(phone_number)
        encoded_phone = urllib.parse.quote(dial_phone)

        # Clean 10-digit number without '91' prefix or encoded '+' for carrier dialing
        target_url = f"{webhook_url.rstrip('/')}?{encoded_phone}"
        logger.info(f"Triggering autonomous cellular call via MacroDroid: {target_url} (dialing: {dial_phone})")

        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(target_url)
                if res.status_code in (200, 204):
                    logger.info(f"MacroDroid successfully initiated cellular call to {dial_phone}")
                    return {"triggered": True, "target": dial_phone}
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

        dial_phone = format_phone_for_dialer(phone_number)
        encoded_phone = urllib.parse.quote(dial_phone)

        target_url = f"{webhook_url.rstrip('/')}?{encoded_phone}"
        logger.info(f"[Sync] Triggering autonomous cellular call via MacroDroid: {target_url} (dialing: {dial_phone})")

        try:
            res = httpx.get(target_url, timeout=6.0)
            if res.status_code in (200, 204):
                return {"triggered": True, "target": dial_phone}
            else:
                return {"triggered": False, "status_code": res.status_code, "error": res.text}
        except Exception as exc:
            logger.exception(f"Error calling MacroDroid webhook: {exc}")
            return {"triggered": False, "error": str(exc)}

    # --- Autonomous WhatsApp Messaging Engine ---

    def _get_whatsapp_webhook_url(self) -> Optional[str]:
        webhook_url = getattr(settings, "MACRODROID_WHATSAPP_WEBHOOK_URL", None) or os.getenv("MACRODROID_WHATSAPP_WEBHOOK_URL")
        if not webhook_url:
            base = getattr(settings, "MACRODROID_WEBHOOK_URL", None) or os.getenv("MACRODROID_WEBHOOK_URL")
            if base:
                webhook_url = re.sub(r"/call$", "/whatsapp", base)
        return webhook_url

    async def trigger_autonomous_whatsapp(self, phone_number: str, message_text: str) -> Dict[str, Any]:
        """Silently and autonomously sends a WhatsApp message via MacroDroid Webhook.
        
        MacroDroid opens WhatsApp to the contact, enters the message text, waits for the configured
        delay, taps Send, and returns to the previous screen.
        """
        webhook_url = self._get_whatsapp_webhook_url()
        if not webhook_url:
            return {"triggered": False, "reason": "MACRODROID_WHATSAPP_WEBHOOK_URL not configured in .env"}

        wa_number = format_phone_for_whatsapp(phone_number)
        encoded_msg = urllib.parse.quote(message_text.strip())
        target_url = f"{webhook_url.rstrip('/')}?phone={wa_number}&msg={encoded_msg}"
        logger.info(f"Triggering autonomous WhatsApp via MacroDroid: {target_url} (to: {wa_number})")

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get(target_url)
                if res.status_code in (200, 204):
                    logger.info(f"MacroDroid successfully triggered WhatsApp send to {wa_number}")
                    return {"triggered": True, "target": wa_number, "message": message_text.strip()}
                else:
                    logger.warning(f"MacroDroid WhatsApp returned status {res.status_code}: {res.text}")
                    return {"triggered": False, "status_code": res.status_code, "error": res.text}
        except Exception as exc:
            logger.exception(f"Error calling MacroDroid WhatsApp webhook: {exc}")
            return {"triggered": False, "error": str(exc)}

    async def send_whatsapp_message(self, name_or_query: str, message_text: str) -> str:
        """Autonomously sends a WhatsApp message to the contact and returns a confirmation card."""
        contact = self.find_contact(name_or_query)

        if not contact:
            clean_digits = re.sub(r"[^\d]", "", name_or_query)
            if len(clean_digits) == 10 or (len(clean_digits) == 12 and clean_digits.startswith("91")):
                contact = {"name": name_or_query, "phone_number": name_or_query}
            else:
                suggestions = self.search_contacts(name_or_query, limit=4)
                if suggestions:
                    lines = [
                        f"I couldn't find an exact match for **{name_or_query}**, but found these contacts:",
                        ""
                    ]
                    for s in suggestions:
                        phone = s.get("phone_number", "")
                        name = s.get("name", "Unknown")
                        lines.append(f"• **{name}** (`{phone}`) — Say: *\"WhatsApp {name}: {message_text}\"*")
                    return "\n".join(lines)
                else:
                    return (
                        f"I couldn't find a contact named **{name_or_query}** in your local contacts database.\n\n"
                        "Please check spelling or provide the 10-digit phone number."
                    )

        name = contact.get("name", name_or_query)
        phone = contact.get("phone_number", "")
        clean_phone = phone.strip()
        wa_number = format_phone_for_whatsapp(clean_phone)
        dial_number = format_phone_for_dialer(clean_phone)
        from app.services.llm_service import clean_interpreted_message
        clean_msg = clean_interpreted_message(message_text).strip()
        logger.info(f"[WhatsApp Service] Sending sanitized message to {name} ({clean_phone}): \"{clean_msg}\"")
        encoded_msg = urllib.parse.quote(clean_msg)

        # 1. Trigger autonomous WhatsApp send via MacroDroid
        send_res = await self.trigger_autonomous_whatsapp(clean_phone, clean_msg)

        # 2. Record outbound message in intermediate memory for context continuity
        memory_service.update_intermediate_item(
            item_id=f"wa_sent_{wa_number}",
            category="whatsapp_sent",
            content=f"Sent WhatsApp to {name} ({wa_number}): \"{clean_msg}\"",
            source_id=wa_number
        )

        if send_res.get("triggered"):
            card = (
                f"### 💬 WhatsApp Sent: **{name}**\n"
                f"**Recipient:** `{wa_number}`\n"
                f"**Message:**\n"
                f"> \"{clean_msg}\"\n\n"
                f"🟢 **Autonomous WhatsApp Triggered!**\n"
                f"Your phone is opening WhatsApp and sending this message to **{name}** right now.\n\n"
                f"---\n"
                f"*Quick Actions:* [💬 View in WhatsApp](https://wa.me/{wa_number}?text={encoded_msg}) | [📞 Call {name}](tel:{dial_number})"
            )
        else:
            err = send_res.get("error") or send_res.get("reason", "Webhook error")
            card = (
                f"### 💬 WhatsApp Draft: **{name}**\n"
                f"**Recipient:** `{wa_number}`\n"
                f"**Message:**\n"
                f"> \"{clean_msg}\"\n\n"
                f"⚠️ *Autonomous trigger noticed an issue ({err}). You can tap below to send directly:*\n\n"
                f"[🟢 Send via WhatsApp](https://wa.me/{wa_number}?text={encoded_msg})\n\n"
                f"*Quick Actions:* [📞 Call {name}](tel:{dial_number})"
            )

        return card

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
        dial_phone = format_phone_for_dialer(clean_phone)
        wa_phone = format_phone_for_whatsapp(clean_phone)

        # 1. Autonomously trigger the call on phone SIM
        call_res = await self.trigger_autonomous_call(dial_phone)

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
                f"**Dialing:** `{dial_phone}` on your phone's cellular SIM\n\n"
                f"🟢 **Autonomous Call Placed!**\n"
                f"Your Android phone is placing the direct cellular call right now. Pick up your phone to speak!{context_block}\n\n"
                f"---\n"
                f"*Quick Actions:* [💬 Message on WhatsApp](https://wa.me/{wa_phone}) | [📱 Send SMS](sms:{dial_phone}) | [Re-dial](tel:{dial_phone})"
            )
        else:
            err = call_res.get("error") or call_res.get("reason", "Webhook error")
            card = (
                f"### 📞 Outgoing Call: **{name}**\n"
                f"**Number:** `{dial_phone}`{context_block}\n\n"
                f"⚠️ *Autonomous trigger noticed an issue ({err}). Tap below to dial directly:*\n\n"
                f"[🟢 Tap to Call {name}](tel:{dial_phone})\n\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_phone})"
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
        dial_phone = format_phone_for_dialer(clean_phone)
        wa_phone = format_phone_for_whatsapp(clean_phone)

        # 1. Trigger call synchronously
        call_res = self.trigger_autonomous_call_sync(dial_phone)

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
                f"**Dialing:** `{dial_phone}` on your phone's cellular SIM\n\n"
                f"🟢 **Autonomous Call Placed!**\n"
                f"Your phone is dialing {name} right now. Pick up to speak!{context_block}\n\n"
                f"---\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_phone}) | [Re-dial](tel:{dial_phone})"
            )
        else:
            err = call_res.get("error") or call_res.get("reason", "Webhook error")
            card = (
                f"### 📞 Outgoing Call: **{name}**\n"
                f"**Number:** `{dial_phone}`{context_block}\n\n"
                f"⚠️ *Could not auto-dial ({err}). Manual fallback:*\n\n"
                f"[🟢 Tap to Call {name}](tel:{dial_phone})\n\n"
                f"*Quick Actions:* [💬 WhatsApp](https://wa.me/{wa_phone}) | [📱 SMS](sms:{dial_phone})"
            )

        return card


contacts_service = ContactsService()


def get_contacts_service() -> ContactsService:
    return contacts_service
