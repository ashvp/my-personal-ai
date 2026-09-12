import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

try:
    import msal
except ImportError:
    pass

from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_FILE = os.path.join(BASE_DIR, "outlook_token.json")

GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"


class OutlookService:
    """Manages Microsoft Graph API integration for College / Professional Outlook accounts.

    Ingests emails into DuckDB tagged as 'outlook_college' with labels 'college,academic,professional'.
    """

    def __init__(self, token_path: str = TOKEN_FILE):
        self.token_path = token_path

    def is_authenticated(self) -> bool:
        return os.path.exists(self.token_path)

    def _get_access_token(self) -> Optional[str]:
        """Loads and silently refreshes the Microsoft Graph access token."""
        if not self.is_authenticated():
            logger.warning(f"Outlook token file not found at {self.token_path}")
            return None

        try:
            with open(self.token_path, "r") as f:
                token_data = json.load(f)

            client_id = token_data.get("client_id")
            authority = token_data.get("authority", "https://login.microsoftonline.com/common")
            refresh_token = token_data.get("refresh_token")

            # Try refreshing token silently if msal is available
            if refresh_token:
                app = msal.PublicClientApplication(client_id=client_id, authority=authority)
                result = app.acquire_token_by_refresh_token(
                    refresh_token=refresh_token,
                    scopes=["https://graph.microsoft.com/Mail.Read"]
                )
                if "access_token" in result:
                    # Update saved token file
                    token_data["access_token"] = result["access_token"]
                    if "refresh_token" in result:
                        token_data["refresh_token"] = result["refresh_token"]
                    with open(self.token_path, "w") as f:
                        json.dump(token_data, f, indent=2)
                    return result["access_token"]

            return token_data.get("access_token")
        except Exception as exc:
            logger.error(f"Error refreshing Outlook token: {exc}")
            return None

    def _clean_html_body(self, html_content: str) -> str:
        if not html_content:
            return ""
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            return soup.get_text(separator=" ", strip=True)[:4000]
        except Exception:
            return html_content[:4000]

    async def sync_emails(self, max_results: int = 15) -> Dict[str, Any]:
        """Fetches recent college/professional emails from Microsoft Graph API

        and indexes them into DuckDB with 'college,academic,professional' tags.
        """
        token = self._get_access_token()
        if not token:
            return {
                "success": False,
                "message": "Outlook not authenticated. Please run 'python authenticate_outlook.py' first."
            }

        url = f"{GRAPH_API_ENDPOINT}/me/messages"
        params = {
            "$top": max_results,
            "$select": "id,conversationId,from,toRecipients,subject,bodyPreview,body,receivedDateTime,isRead,categories",
            "$orderby": "receivedDateTime desc"
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, headers=headers)

            if response.status_code != 200:
                logger.error(f"Microsoft Graph API error {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "message": f"Graph API returned status {response.status_code}: {response.text[:200]}"
                }

            data = response.json()
            messages = data.get("value", [])

            if not messages:
                return {"success": True, "synced_count": 0, "message": "No messages found in Outlook inbox."}

            synced_count = 0
            for msg in messages:
                raw_id = msg.get("id", "")
                email_id = f"outlook_{raw_id[-24:]}" if raw_id else ""

                if not email_id or memory_service.email_exists(email_id):
                    continue

                from_info = msg.get("from", {}).get("emailAddress", {})
                sender_name = from_info.get("name", "")
                sender_addr = from_info.get("address", "Unknown Sender")
                sender_display = f"{sender_name} <{sender_addr}>" if sender_name else sender_addr

                to_list = [
                    t.get("emailAddress", {}).get("address", "")
                    for t in msg.get("toRecipients", [])
                ]
                recipient = ", ".join(filter(None, to_list))

                subject = msg.get("subject") or "(No Subject)"
                snippet = msg.get("bodyPreview") or ""

                body_obj = msg.get("body", {})
                raw_body = body_obj.get("content", "")
                content_type = body_obj.get("contentType", "text")

                clean_body = self._clean_html_body(raw_body) if content_type.lower() == "html" else raw_body[:4000]
                if not clean_body:
                    clean_body = snippet

                received_str = msg.get("receivedDateTime", "")
                # Format friendly date
                try:
                    dt = datetime.fromisoformat(received_str.replace("Z", "+00:00"))
                    date_display = dt.strftime("%a, %d %b %Y %H:%M:%S")
                except Exception:
                    date_display = received_str

                quick_summary = f"[COLLEGE] {sender_name or sender_addr}: {subject} — {snippet[:120]}"

                email_record = {
                    "id": email_id,
                    "thread_id": msg.get("conversationId", ""),
                    "source": "outlook_college",
                    "sender": sender_display,
                    "recipient": recipient,
                    "subject": subject,
                    "snippet": snippet,
                    "body_clean": clean_body,
                    "summary": quick_summary,
                    "date": date_display,
                    "is_read": msg.get("isRead", False),
                    "labels": "college,academic,professional,outlook"
                }

                # Save to DuckDB
                memory_service.store_email(email_record)

                # Save to Active Working Briefing (Intermediate Memory)
                memory_service.update_intermediate_item(
                    item_id=f"outlook_{email_id}",
                    category="college_mail",
                    content=quick_summary,
                    source_id=email_id
                )

                synced_count += 1

            logger.info(f"Outlook sync complete. Ingested {synced_count} college emails into DuckDB.")
            return {
                "success": True,
                "synced_count": synced_count,
                "message": f"Successfully ingested {synced_count} college emails into DuckDB as professional correspondence."
            }

        except Exception as exc:
            logger.exception("Error syncing Outlook messages")
            return {
                "success": False,
                "message": f"Outlook sync failed: {str(exc)}"
            }


outlook_service = OutlookService()


def get_outlook_service() -> OutlookService:
    return outlook_service
