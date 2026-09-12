import os
import base64
import logging
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    pass

from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CREDS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


class GmailService:
    def __init__(self):
        self._service = None

    def is_authenticated(self) -> bool:
        return os.path.exists(TOKEN_FILE)

    def _get_service(self):
        if self._service is not None:
            return self._service

        if not os.path.exists(TOKEN_FILE):
            logger.warning("token.json not found. Gmail not authenticated yet.")
            return None

        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_FILE, 'w') as f:
                    f.write(creds.to_json())

            self._service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
            return self._service
        except Exception as exc:
            logger.error(f"Error initializing Gmail API service: {exc}")
            return None

    def _extract_body(self, payload: Dict[str, Any]) -> str:
        """Recursively extracts plain text or stripped HTML from email payload parts."""
        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                data = part.get("body", {}).get("data")
                if data:
                    try:
                        text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                        if mime_type == "text/plain":
                            return text
                        elif mime_type == "text/html" and not body:
                            soup = BeautifulSoup(text, "html.parser")
                            body = soup.get_text(separator=" ", strip=True)
                    except Exception:
                        pass
                # Check nested parts
                if "parts" in part:
                    nested = self._extract_body(part)
                    if nested:
                        return nested
        else:
            data = payload.get("body", {}).get("data")
            if data:
                try:
                    text = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                    mime_type = payload.get("mimeType", "")
                    if mime_type == "text/html":
                        soup = BeautifulSoup(text, "html.parser")
                        return soup.get_text(separator=" ", strip=True)
                    return text
                except Exception:
                    pass

        return body

    async def sync_emails(self, max_results: int = 10, query: str = "newer_than:7d") -> Dict[str, Any]:
        """Fetches recent emails, stores them into DuckDB, and populates Intermediate Memory."""
        service = self._get_service()
        if not service:
            return {
                "success": False,
                "message": "Gmail not authenticated. Please run 'python authenticate_gmail.py' first."
            }

        try:
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=query
            ).execute()

            messages = results.get('messages', [])
            if not messages:
                return {"success": True, "synced_count": 0, "message": "No new messages found."}

            synced_count = 0
            for msg_item in messages:
                msg_id = msg_item['id']

                # Skip if already ingested into DuckDB
                if memory_service.email_exists(msg_id):
                    continue

                try:
                    msg_data = service.users().messages().get(
                        userId='me',
                        id=msg_id,
                        format='full'
                    ).execute()

                    headers = {
                        h['name'].lower(): h['value']
                        for h in msg_data.get('payload', {}).get('headers', [])
                    }

                    subject = headers.get('subject', '(No Subject)')
                    sender = headers.get('from', 'Unknown Sender')
                    recipient = headers.get('to', '')
                    date_str = headers.get('date', '')
                    snippet = msg_data.get('snippet', '')
                    body = self._extract_body(msg_data.get('payload', {}))
                    clean_body = body[:4000] if body else snippet

                    sender_display = sender.split('<')[0].strip(' "\'') or sender
                    quick_summary = f"{sender_display}: {subject} — {snippet[:120]}"

                    email_record = {
                        "id": msg_id,
                        "thread_id": msg_data.get('threadId', ''),
                        "source": "gmail",
                        "sender": sender,
                        "recipient": recipient,
                        "subject": subject,
                        "snippet": snippet,
                        "body_clean": clean_body,
                        "summary": quick_summary,
                        "date": date_str,
                        "is_read": 'UNREAD' not in msg_data.get('labelIds', []),
                        "labels": ",".join(msg_data.get('labelIds', []))
                    }

                    # Save to DuckDB (Long-Term Memory)
                    memory_service.store_email(email_record)

                    # Save to Active Digest (Intermediate Memory)
                    memory_service.update_intermediate_item(
                        item_id=f"email_{msg_id}",
                        category="email",
                        content=quick_summary,
                        source_id=msg_id
                    )

                    synced_count += 1
                except Exception as msg_err:
                    logger.warning(f"Failed to fetch individual message {msg_id}: {msg_err}")
                    continue

            logger.info(f"Gmail sync complete. Ingested {synced_count} new emails into DuckDB.")
            return {
                "success": True,
                "synced_count": synced_count,
                "message": f"Successfully ingested {synced_count} emails into DuckDB memory."
            }

        except Exception as exc:
            err_str = str(exc)
            if any(term in err_str.lower() for term in ["name resolution", "remotedisconnected", "connection", "socket", "timeout"]):
                logger.warning(f"Gmail sync temporarily skipped (network/DNS glitch): {exc}")
            else:
                logger.exception("Error syncing Gmail messages")
            return {
                "success": False,
                "message": f"Gmail sync failed: {err_str}"
            }


gmail_service = GmailService()


def get_gmail_service() -> GmailService:
    return gmail_service
