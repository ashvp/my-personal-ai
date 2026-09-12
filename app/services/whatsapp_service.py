import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

import glob

def get_beeper_db_path() -> str:
    """Detects Beeper index.db dynamically across Windows and WSL without exposing usernames."""
    # 1. Optional explicit override via .env
    custom_path = os.getenv("BEEPER_DB_PATH")
    if custom_path and os.path.exists(custom_path):
        return custom_path

    # 2. Native Windows environment (%APPDATA%)
    appdata = os.getenv("APPDATA")
    if appdata:
        p = os.path.join(appdata, "BeeperTexts", "index.db")
        if os.path.exists(p):
            return p

    # 3. WSL environment: dynamically search across mounted Windows user profiles
    wsl_candidates = glob.glob("/mnt/c/Users/*/AppData/Roaming/BeeperTexts/index.db")
    for candidate in wsl_candidates:
        if os.path.exists(candidate):
            return candidate

    return ""


DEFAULT_BEEPER_DB_PATH = get_beeper_db_path()


class WhatsAppService:
    """Manages ingestion of WhatsApp messages from local Beeper SQLite store
    into DuckDB using the 3-Tier Cognitive Memory architecture:
    1. Working Memory (Today & Yesterday / < 48 hours): High-resolution active context.
    2. Episodic Memory (2 to 30 days): Contextual narratives per conversation.
    3. Long-Term Memory (> 30 days): Deep searchable historical archive.
    """

    def __init__(self, db_path: str = DEFAULT_BEEPER_DB_PATH):
        self.db_path = db_path

    def is_available(self) -> bool:
        return os.path.exists(self.db_path)

    def _get_sqlite_connection(self):
        if not self.is_available():
            raise FileNotFoundError(f"Beeper database not found at {self.db_path}")

        # In WSL accessing Windows /mnt/c, SQLite WAL shared-memory locks fail over DrvFS.
        # Making an instantaneous local snapshot in /tmp bypasses DrvFS locking entirely
        # and guarantees zero file conflict with the running Beeper desktop app.
        if "/mnt/" in self.db_path or sys.platform != "win32":
            import shutil
            import tempfile

            temp_dir = tempfile.gettempdir()
            snapshot_db = os.path.join(temp_dir, "beeper_index_snapshot.db")
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

    def sync_messages(self) -> Dict[str, Any]:
        """Syncs all WhatsApp messages from Beeper's index.db into DuckDB."""
        if not self.is_available():
            return {
                "success": False,
                "message": f"Beeper SQLite store not found at {self.db_path}. Is Beeper installed and WhatsApp linked?"
            }

        try:
            conn = self._get_sqlite_connection()
            cursor = conn.cursor()

            # 1. Fetch thread titles (group names and explicitly named chats)
            cursor.execute("SELECT threadID, thread FROM threads;")
            threads_map = {}
            for tid, traw in cursor.fetchall():
                try:
                    t_data = json.loads(traw) if traw else {}
                    title = t_data.get("title") or t_data.get("name")
                    if title and title.strip().lower() not in ("unknown", "null", ""):
                        threads_map[tid] = title.strip()
                except Exception:
                    pass

            # 2. For 1-on-1 chats without a thread title, resolve contact from participants table
            cursor.execute("""
                SELECT room_id, full_name, nickname, id
                FROM participants
                WHERE is_self = 0 OR is_self IS NULL;
            """)
            for room_id, full_name, nick, user_id in cursor.fetchall():
                if room_id not in threads_map or not threads_map[room_id]:
                    contact_name = full_name or nick
                    if not contact_name and user_id:
                        if "whatsapp" in user_id:
                            clean_id = user_id.split(":")[0].replace("@whatsapp_", "").replace("lid-", "")
                            contact_name = f"+{clean_id}" if clean_id.isdigit() else clean_id
                        else:
                            contact_name = user_id.split(":")[0].lstrip("@")
                    if contact_name:
                        threads_map[room_id] = contact_name

            # First, age existing messages across memory tiers
            memory_service.refresh_message_memory_tiers()

            # Check latest stored message timestamp to do fast incremental sync
            latest_ts = memory_service.get_latest_message_timestamp(source="whatsapp")
            if latest_ts and latest_ts > 0:
                # 5-minute safety overlap to catch any slightly out-of-order writes
                cutoff_ms = latest_ts - (5 * 60 * 1000)
                cursor.execute("""
                    SELECT id, roomID, senderContactID, timestamp, isSentByMe, message
                    FROM mx_room_messages
                    WHERE message IS NOT NULL AND timestamp >= ?
                    ORDER BY timestamp ASC;
                """, (cutoff_ms,))
            else:
                cursor.execute("""
                    SELECT id, roomID, senderContactID, timestamp, isSentByMe, message
                    FROM mx_room_messages
                    WHERE message IS NOT NULL
                    ORDER BY timestamp ASC;
                """)

            raw_rows = cursor.fetchall()
            conn.close()

            if not raw_rows:
                return {"success": True, "synced_count": 0, "message": "No new messages found in Beeper store."}

            now_sec = time.time()
            working_cutoff = now_sec - (48 * 3600)        # 48 hours ago
            episodic_cutoff = now_sec - (30 * 24 * 3600)  # 30 days ago

            records = []
            working_by_thread: Dict[str, Dict[str, Any]] = {}

            counts = {"working": 0, "episodic": 0, "long_term": 0}

            for row in raw_rows:
                msg_id, room_id, sender_id, ts, is_me, msg_raw = row
                try:
                    m_data = json.loads(msg_raw) if msg_raw else {}
                except Exception:
                    continue

                text = m_data.get("text") or ""
                if not text:
                    attachments = m_data.get("attachments") or []
                    if attachments:
                        text = "[Media / Attachment]"
                    else:
                        continue

                ts_sec = (ts / 1000.0) if ts else now_sec
                date_str = datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d %H:%M:%S")

                # Categorize into 3-tier memory
                if ts_sec >= working_cutoff:
                    tier = "working"
                    counts["working"] += 1
                elif ts_sec >= episodic_cutoff:
                    tier = "episodic"
                    counts["episodic"] += 1
                else:
                    tier = "long_term"
                    counts["long_term"] += 1

                thread_title = threads_map.get(room_id, "Direct Chat")
                sender_label = "Me" if is_me else thread_title

                record = {
                    "id": f"wa_{msg_id}",
                    "source": "whatsapp",
                    "thread_id": room_id or "",
                    "thread_title": thread_title,
                    "sender": sender_label,
                    "is_sent_by_me": bool(is_me),
                    "content": text,
                    "timestamp": int(ts or (now_sec * 1000)),
                    "date_str": date_str,
                    "memory_tier": tier
                }
                records.append(record)

                # Keep latest message per thread for Working Memory digest
                if tier == "working":
                    working_by_thread[thread_title] = {
                        "thread_id": room_id,
                        "latest_sender": sender_label,
                        "latest_text": text,
                        "date_str": date_str
                    }

            # 3. Store batch into DuckDB
            memory_service.store_messages_batch(records)
            logger.info(f"Ingested {len(records)} WhatsApp messages into DuckDB.")

            # 4. Update Working Memory (Intermediate Memory) with active chats from today/yesterday
            for thread_title, item in working_by_thread.items():
                summary = (
                    f"Chat with {thread_title}: {item['latest_sender']}: "
                    f"\"{item['latest_text'][:100]}\" ({item['date_str']})"
                )
                memory_service.update_intermediate_item(
                    item_id=f"wa_thread_{item['thread_id']}",
                    category="whatsapp",
                    content=summary,
                    source_id=item['thread_id']
                )

            return {
                "success": True,
                "synced_count": len(records),
                "counts_by_tier": counts,
                "active_threads_in_working_memory": len(working_by_thread),
                "message": (
                    f"Successfully ingested {len(records)} WhatsApp messages into DuckDB "
                    f"({counts['working']} Working, {counts['episodic']} Episodic, {counts['long_term']} Long-Term)."
                )
            }

        except Exception as exc:
            logger.exception("Error syncing WhatsApp messages from Beeper")
            return {
                "success": False,
                "message": f"Sync failed: {str(exc)}"
            }


whatsapp_service = WhatsAppService()


def get_whatsapp_service() -> WhatsAppService:
    return whatsapp_service
