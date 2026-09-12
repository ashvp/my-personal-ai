import os
import time
import threading
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import duckdb

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "assistant.duckdb")

os.makedirs(DATA_DIR, exist_ok=True)


class MemoryService:
    """Manages the 3-tier memory system using DuckDB:

    1. Short-Term: Active conversation turns (per session).
    2. Intermediate: Rolling daily digest of emails, active tasks & key facts.
    3. Long-Term: Complete historical email & message archive with full search.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_schema()

    def _get_connection(self):
        return duckdb.connect(self.db_path)

    def _init_schema(self):
        with self._lock:
            conn = self._get_connection()
            try:
                # 1. Historical Emails / Messages Table (Long-Term Archive)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS emails (
                        id VARCHAR PRIMARY KEY,
                        thread_id VARCHAR,
                        source VARCHAR DEFAULT 'gmail',
                        sender VARCHAR,
                        recipient VARCHAR,
                        subject VARCHAR,
                        snippet VARCHAR,
                        body_clean VARCHAR,
                        summary VARCHAR,
                        date VARCHAR,
                        is_read BOOLEAN DEFAULT FALSE,
                        labels VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 2. Unified Messages Table (WhatsApp, Chats, Multi-Modal) with 3 Cognitive Tiers
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id VARCHAR PRIMARY KEY,
                        source VARCHAR DEFAULT 'whatsapp',
                        thread_id VARCHAR,
                        thread_title VARCHAR,
                        sender VARCHAR,
                        is_sent_by_me BOOLEAN,
                        content VARCHAR,
                        timestamp BIGINT,
                        date_str VARCHAR,
                        memory_tier VARCHAR, -- 'working', 'episodic', 'long_term'
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 3. Intermediate Memory (Active Digest & Daily Briefing)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS intermediate_memory (
                        id VARCHAR PRIMARY KEY,
                        category VARCHAR,
                        content VARCHAR,
                        source_id VARCHAR,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 3. Short-Term Memory (Recent Chat Turns)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        id INTEGER PRIMARY KEY,
                        session_id VARCHAR,
                        role VARCHAR,
                        content VARCHAR,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute("""
                    CREATE SEQUENCE IF NOT EXISTS chat_history_seq START 1;
                """)
                logger.info(f"DuckDB schema initialized at {self.db_path}")
            finally:
                conn.close()

    # --- Long-Term Memory (Emails) ---

    def email_exists(self, email_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                result = conn.execute("SELECT 1 FROM emails WHERE id = ?", [email_id]).fetchone()
                return result is not None
            finally:
                conn.close()

    def store_email(self, email: Dict[str, Any]):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO emails (
                        id, thread_id, source, sender, recipient,
                        subject, snippet, body_clean, summary,
                        date, is_read, labels
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    email.get("id"),
                    email.get("thread_id", ""),
                    email.get("source", "gmail"),
                    email.get("sender", ""),
                    email.get("recipient", ""),
                    email.get("subject", "(No Subject)"),
                    email.get("snippet", ""),
                    email.get("body_clean", ""),
                    email.get("summary", ""),
                    email.get("date", ""),
                    email.get("is_read", False),
                    email.get("labels", "")
                ])
            finally:
                conn.close()

    def search_emails(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches historical emails using DuckDB text matching."""
        with self._lock:
            conn = self._get_connection()
            try:
                term = f"%{query}%"
                rows = conn.execute("""
                    SELECT id, sender, subject, date, summary, snippet
                    FROM emails
                    WHERE subject ILIKE ? OR body_clean ILIKE ? OR sender ILIKE ? OR summary ILIKE ? OR source ILIKE ? OR labels ILIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, [term, term, term, term, term, term, limit]).fetchall()

                cols = ["id", "sender", "subject", "date", "summary", "snippet"]
                return [dict(zip(cols, row)) for row in rows]
            finally:
                conn.close()

    def get_recent_emails(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT id, sender, subject, date, summary, snippet, is_read
                    FROM emails
                    ORDER BY created_at DESC
                    LIMIT ?
                """, [limit]).fetchall()

                cols = ["id", "sender", "subject", "date", "summary", "snippet", "is_read"]
                return [dict(zip(cols, row)) for row in rows]
            finally:
                conn.close()

    # --- Multi-Modal Messages & 3-Tier Chat Storage ---

    def store_messages_batch(self, messages: List[Dict[str, Any]]):
        """Batch inserts or replaces messages into DuckDB."""
        if not messages:
            return
        with self._lock:
            conn = self._get_connection()
            try:
                conn.executemany("""
                    INSERT OR REPLACE INTO messages (
                        id, source, thread_id, thread_title, sender,
                        is_sent_by_me, content, timestamp, date_str, memory_tier
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (
                        m.get("id"),
                        m.get("source", "whatsapp"),
                        m.get("thread_id", ""),
                        m.get("thread_title", "Unknown"),
                        m.get("sender", ""),
                        m.get("is_sent_by_me", False),
                        m.get("content", ""),
                        m.get("timestamp", 0),
                        m.get("date_str", ""),
                        m.get("memory_tier", "long_term")
                    )
                    for m in messages
                ])
            finally:
                conn.close()

    def get_working_messages(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Working Memory: Fetches active messages from today and yesterday."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT id, source, thread_title, sender, is_sent_by_me, content, date_str
                    FROM messages
                    WHERE memory_tier = 'working'
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit]).fetchall()
                cols = ["id", "source", "thread_title", "sender", "is_sent_by_me", "content", "date_str"]
                return [dict(zip(cols, row)) for row in rows]
            finally:
                conn.close()

    def get_episodic_narrative(self, contact_or_thread: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Episodic Memory: Reconstructs the story/conversation with a specific contact or topic."""
        with self._lock:
            conn = self._get_connection()
            try:
                term = f"%{contact_or_thread}%"
                rows = conn.execute("""
                    SELECT id, source, thread_title, sender, is_sent_by_me, content, date_str
                    FROM messages
                    WHERE thread_title ILIKE ? OR sender ILIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [term, term, limit]).fetchall()
                cols = ["id", "source", "thread_title", "sender", "is_sent_by_me", "content", "date_str"]
                # Return in chronological order for narrative flow
                result = [dict(zip(cols, row)) for row in rows]
                result.reverse()
                return result
            finally:
                conn.close()

    def get_latest_message_timestamp(self, source: str = "whatsapp") -> Optional[int]:
        """Returns the timestamp (ms) of the most recent message stored in DuckDB."""
        with self._lock:
            conn = self._get_connection()
            try:
                row = conn.execute(
                    "SELECT MAX(timestamp) FROM messages WHERE source = ?",
                    [source]
                ).fetchone()
                return row[0] if row and row[0] is not None else None
            finally:
                conn.close()

    def refresh_message_memory_tiers(self):
        """Ages existing messages across the 3 cognitive memory tiers based on elapsed time:
        Working (<48h) -> Episodic (2-30d) -> Long-Term (>30d).
        """
        with self._lock:
            conn = self._get_connection()
            try:
                now_sec = time.time()
                working_cutoff_ms = int((now_sec - (48 * 3600)) * 1000)
                episodic_cutoff_ms = int((now_sec - (30 * 24 * 3600)) * 1000)

                conn.execute("""
                    UPDATE messages
                    SET memory_tier = 'episodic'
                    WHERE memory_tier = 'working' AND timestamp < ?
                """, [working_cutoff_ms])

                conn.execute("""
                    UPDATE messages
                    SET memory_tier = 'long_term'
                    WHERE memory_tier = 'episodic' AND timestamp < ?
                """, [episodic_cutoff_ms])
            finally:
                conn.close()

    def search_messages(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Searches across all message archives (Long-Term & Episodic)."""
        with self._lock:
            conn = self._get_connection()
            try:
                term = f"%{query}%"
                rows = conn.execute("""
                    SELECT id, source, thread_title, sender, is_sent_by_me, content, date_str, memory_tier
                    FROM messages
                    WHERE content ILIKE ? OR thread_title ILIKE ? OR sender ILIKE ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [term, term, term, limit]).fetchall()
                cols = ["id", "source", "thread_title", "sender", "is_sent_by_me", "content", "date_str", "memory_tier"]
                return [dict(zip(cols, row)) for row in rows]
            finally:
                conn.close()

    def get_recent_messages(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Gets recent messages across all chats."""
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT id, source, thread_title, sender, is_sent_by_me, content, date_str, memory_tier
                    FROM messages
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, [limit]).fetchall()
                cols = ["id", "source", "thread_title", "sender", "is_sent_by_me", "content", "date_str", "memory_tier"]
                return [dict(zip(cols, row)) for row in rows]
            finally:
                conn.close()

    # --- Intermediate Memory (Daily Digest & Active Context) ---

    def update_intermediate_item(self, item_id: str, category: str, content: str, source_id: Optional[str] = None):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO intermediate_memory (
                        id, category, content, source_id, updated_at
                    ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, [item_id, category, content, source_id or ""])
            finally:
                conn.close()

    def get_intermediate_context(self) -> str:
        """Returns active briefing context to inject into Qwen's system prompt."""
        with self._lock:
            conn = self._get_connection()
            try:
                # Fetch recent active items (e.g. today's email highlights)
                rows = conn.execute("""
                    SELECT category, content
                    FROM intermediate_memory
                    ORDER BY updated_at DESC
                    LIMIT 20
                """).fetchall()

                if not rows:
                    return ""

                lines = ["--- CURRENT ACTIVE CONTEXT (INTERMEDIATE MEMORY) ---"]
                for cat, content in rows:
                    lines.append(f"• [{cat.upper()}] {content}")
                lines.append("--------------------------------------------------")
                return "\n".join(lines)
            finally:
                conn.close()

    # --- Short-Term Memory (Session Chat History) ---

    def add_chat_turn(self, session_id: str, role: str, content: str):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO chat_history (id, session_id, role, content)
                    VALUES (nextval('chat_history_seq'), ?, ?, ?)
                """, [session_id, role, content])
            finally:
                conn.close()

    def get_recent_chat_turns(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        with self._lock:
            conn = self._get_connection()
            try:
                rows = conn.execute("""
                    SELECT role, content
                    FROM (
                        SELECT id, role, content
                        FROM chat_history
                        WHERE session_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                    ) sub
                    ORDER BY id ASC
                """, [session_id, limit]).fetchall()

                return [{"role": r[0], "content": r[1]} for r in rows]
            finally:
                conn.close()


memory_service = MemoryService()


def get_memory_service() -> MemoryService:
    return memory_service
