import os
import sys
import time
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from app.config import settings
from app.services.memory_service import memory_service
from app.services.graph_service import graph_service
from app.services.whatsapp_service import get_beeper_db_path, DEFAULT_BEEPER_DB_PATH

logger = logging.getLogger(__name__)


class SMSService:
    """Manages ingestion of Google Messages / Android SMS from Beeper's local SQLite store
    into DuckDB using the 3-Tier Cognitive Memory architecture:
    1. Working Memory (Today & Yesterday / < 48 hours)
    2. Episodic Memory (2 to 30 days)
    3. Long-Term Memory (> 30 days)
    """

    def __init__(self, db_path: str = DEFAULT_BEEPER_DB_PATH):
        self.db_path = db_path

    def is_available(self) -> bool:
        return bool(self.db_path and os.path.exists(self.db_path))

    def _get_sqlite_connection(self):
        if not self.is_available():
            raise FileNotFoundError(f"Beeper database not found at {self.db_path}")

        # In WSL accessing Windows /mnt/c, SQLite WAL shared-memory locks fail over DrvFS.
        # Making an instantaneous local snapshot in /tmp bypasses DrvFS locking entirely.
        if "/mnt/" in self.db_path or sys.platform != "win32":
            import shutil
            import tempfile

            temp_dir = tempfile.gettempdir()
            snapshot_db = os.path.join(temp_dir, "beeper_sms_snapshot.db")
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

    def sync_messages(self, limit: Optional[int] = 50) -> Dict[str, Any]:
        """Syncs Google Messages / SMS from Beeper into DuckDB.
        
        Args:
            limit: Maximum number of recent SMS to fetch (default: 50). Pass None for all.
        """
        if not self.is_available():
            return {
                "success": False,
                "message": f"Beeper store not found at {self.db_path}. Ensure Google Messages is connected in Beeper."
            }

        try:
            conn = self._get_sqlite_connection()
            cursor = conn.cursor()

            # 1. Identify all Google Messages / SMS rooms and resolve contact names
            cursor.execute("""
                SELECT room_id, full_name, nickname, id
                FROM participants
                WHERE id LIKE '%gmessages%' OR id LIKE '%sms%';
            """)
            sms_rooms: Dict[str, str] = {}
            for room_id, full_name, nick, user_id in cursor.fetchall():
                contact_name = full_name or nick
                if not contact_name and user_id:
                    clean_id = user_id.split(":")[0].replace("@gmessages_", "").replace("@sms_", "")
                    contact_name = f"+{clean_id}" if clean_id.isdigit() else clean_id
                sms_rooms[room_id] = contact_name or "SMS Contact"

            if not sms_rooms:
                conn.close()
                return {
                    "success": True,
                    "synced_count": 0,
                    "message": "No Google Messages / SMS rooms found in Beeper store."
                }

            # 2. Check thread titles if any
            placeholders = ",".join("?" for _ in sms_rooms)
            cursor.execute(f"""
                SELECT threadID, thread
                FROM threads
                WHERE threadID IN ({placeholders});
            """, list(sms_rooms.keys()))
            for tid, traw in cursor.fetchall():
                try:
                    t_data = json.loads(traw) if traw else {}
                    title = t_data.get("title") or t_data.get("name")
                    if title and title.strip().lower() not in ("unknown", "null", ""):
                        sms_rooms[tid] = title.strip()
                except Exception:
                    pass

            # 3. Query recent messages for these SMS rooms
            query_sql = f"""
                SELECT id, roomID, senderContactID, timestamp, isSentByMe, message
                FROM mx_room_messages
                WHERE roomID IN ({placeholders}) AND message IS NOT NULL
                ORDER BY timestamp DESC
            """
            if limit:
                query_sql += f" LIMIT {int(limit)}"

            cursor.execute(query_sql, list(sms_rooms.keys()))
            raw_rows = cursor.fetchall()
            conn.close()

            if not raw_rows:
                return {
                    "success": True,
                    "synced_count": 0,
                    "message": "No SMS messages found in Google Messages rooms."
                }

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

                # Categorize into 3 cognitive tiers
                if ts_sec >= working_cutoff:
                    tier = "working"
                    counts["working"] += 1
                elif ts_sec >= episodic_cutoff:
                    tier = "episodic"
                    counts["episodic"] += 1
                else:
                    tier = "long_term"
                    counts["long_term"] += 1

                contact_name = sms_rooms.get(room_id, "SMS")
                sender_label = "Me" if is_me else contact_name

                record = {
                    "id": f"sms_{msg_id}",
                    "source": "sms",
                    "thread_id": room_id or "",
                    "thread_title": contact_name,
                    "sender": sender_label,
                    "is_sent_by_me": bool(is_me),
                    "content": text,
                    "timestamp": int(ts or (now_sec * 1000)),
                    "date_str": date_str,
                    "memory_tier": tier
                }
                records.append(record)

                if tier == "working":
                    working_by_thread[contact_name] = {
                        "thread_id": room_id,
                        "latest_sender": sender_label,
                        "latest_text": text,
                        "date_str": date_str
                    }

            # 4. Store in DuckDB via SQLAlchemy ORM
            memory_service.store_messages_batch(records)
            logger.info(f"Ingested {len(records)} Google SMS messages into DuckDB.")

            # 4b. Extract and assert temporal graph facts (V2)
            if getattr(settings, "ENABLE_V2_GRAPH", True):
                try:
                    for r in records:
                        if r.get("content"):
                            graph_service.extract_and_assert_from_text(
                                text=r["content"],
                                date_str=r.get("date_str") or datetime.now().strftime("%Y-%m-%d"),
                                source_id=r.get("id")
                            )
                except Exception as g_exc:
                    logger.warning(f"Error extracting graph facts from SMS batch: {g_exc}")

            # 5. Update Working Memory
            for contact_name, item in working_by_thread.items():
                summary = (
                    f"SMS from {contact_name}: {item['latest_sender']}: "
                    f"\"{item['latest_text'][:100]}\" ({item['date_str']})"
                )
                memory_service.update_intermediate_item(
                    item_id=f"sms_thread_{item['thread_id']}",
                    category="sms",
                    content=summary,
                    source_id=item['thread_id']
                )

            return {
                "success": True,
                "synced_count": len(records),
                "counts_by_tier": counts,
                "active_threads_in_working_memory": len(working_by_thread),
                "message": (
                    f"Successfully ingested {len(records)} Google SMS messages into DuckDB "
                    f"({counts['working']} Working, {counts['episodic']} Episodic, {counts['long_term']} Long-Term)."
                )
            }

        except Exception as exc:
            logger.exception("Error syncing Google SMS messages from Beeper")
            return {
                "success": False,
                "message": f"Google SMS sync failed: {str(exc)}"
            }


sms_service = SMSService()


def get_sms_service() -> SMSService:
    return sms_service
