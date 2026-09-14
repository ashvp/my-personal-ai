import os
import time
import logging
from typing import List, Dict, Any, Optional

from sqlalchemy import create_engine, select, or_, update, func, text
from sqlalchemy.orm import sessionmaker, scoped_session

from app.models.memory import Base, Email, Message, IntermediateMemory, ChatHistory, Contact, Entity, TemporalEdge

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "assistant.duckdb")

os.makedirs(DATA_DIR, exist_ok=True)


class MemoryService:
    """Manages the 3-Tier Cognitive Memory Engine using SQLAlchemy ORM and DuckDB:
    
    1. Short-Term Memory: Active conversation turns (ChatHistory ORM).
    2. Intermediate Memory: Rolling daily context, action items & digests (IntermediateMemory ORM).
    3. Long-Term Memory: Multi-modal emails and messages with 3 cognitive tiers:
       - Working Memory (<48h)
       - Episodic Memory (2-30d)
       - Historical Archive (>30d)
    """

    def __init__(self, db_path: Optional[str] = None):
        if not db_path:
            db_path = os.environ.get("DUCKDB_PATH", DB_PATH)
        self.db_path = db_path
        # Normalize path for SQLAlchemy DuckDB dialect
        if db_path == ":memory:":
            uri = "duckdb:///:memory:"
        else:
            norm_path = db_path.replace("\\", "/")
            uri = f"duckdb:///{norm_path}"
        self.engine = create_engine(uri, echo=False)
        self.SessionFactory = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.Session = scoped_session(self.SessionFactory)
        self._init_schema()

    def _init_schema(self):
        """Initializes tables using SQLAlchemy Declarative metadata."""
        try:
            Base.metadata.create_all(bind=self.engine)
            # Drop legacy secondary ART index on contacts that causes DuckDB index deletion error
            with self.engine.connect() as conn:
                for idx in ["ix_contacts_name", "contacts_name_idx"]:
                    try:
                        conn.execute(text(f"DROP INDEX IF EXISTS {idx};"))
                    except Exception:
                        pass
                conn.commit()
            logger.info(f"SQLAlchemy DuckDB schema initialized successfully at {self.db_path}")
        except Exception as exc:
            logger.exception(f"Error initializing SQLAlchemy DuckDB schema: {exc}")

    def get_session(self):
        """Returns a fresh thread-local SQLAlchemy session."""
        return self.Session()

    # --- Long-Term Memory (Emails) ---

    def email_exists(self, email_id: str) -> bool:
        """Checks if an email ID is already stored in DuckDB via ORM select."""
        session = self.get_session()
        try:
            stmt = select(Email.id).where(Email.id == email_id)
            result = session.scalar(stmt)
            return result is not None
        finally:
            session.close()

    def store_email(self, email_data: Dict[str, Any]):
        """Inserts or updates an email record via SQLAlchemy ORM."""
        session = self.get_session()
        try:
            email_id = email_data.get("id")
            existing = session.get(Email, email_id)
            if existing:
                for key, val in email_data.items():
                    if hasattr(existing, key):
                        setattr(existing, key, val)
            else:
                new_email = Email(
                    id=email_id,
                    thread_id=email_data.get("thread_id", ""),
                    source=email_data.get("source", "gmail"),
                    sender=email_data.get("sender", ""),
                    recipient=email_data.get("recipient", ""),
                    subject=email_data.get("subject", "(No Subject)"),
                    snippet=email_data.get("snippet", ""),
                    body_clean=email_data.get("body_clean", ""),
                    summary=email_data.get("summary", ""),
                    date=email_data.get("date", ""),
                    is_read=email_data.get("is_read", False),
                    labels=email_data.get("labels", "")
                )
                session.add(new_email)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error storing email {email_data.get('id')} via SQLAlchemy: {exc}")
        finally:
            session.close()

    def search_emails(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches historical emails using SQLAlchemy ilike pattern matching."""
        session = self.get_session()
        try:
            term = f"%{query}%"
            stmt = (
                select(Email)
                .where(
                    or_(
                        Email.subject.ilike(term),
                        Email.body_clean.ilike(term),
                        Email.sender.ilike(term),
                        Email.summary.ilike(term),
                        Email.source.ilike(term),
                        Email.labels.ilike(term)
                    )
                )
                .order_by(Email.created_at.desc())
                .limit(limit)
            )
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    def get_recent_emails(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetches recent emails via SQLAlchemy ORM ordered by creation timestamp."""
        session = self.get_session()
        try:
            stmt = select(Email).order_by(Email.created_at.desc()).limit(limit)
            results = session.scalars(stmt).all()
            return [e.to_dict() for e in results]
        finally:
            session.close()

    # --- Multi-Modal Messages & 3-Tier Cognitive Engine ---

    def store_messages_batch(self, messages: List[Dict[str, Any]]):
        """Batch upserts messages into DuckDB using SQLAlchemy ORM merging."""
        if not messages:
            return

        session = self.get_session()
        try:
            for m in messages:
                msg_obj = Message(
                    id=m.get("id"),
                    source=m.get("source", "whatsapp"),
                    thread_id=m.get("thread_id", ""),
                    thread_title=m.get("thread_title", "Unknown"),
                    sender=m.get("sender", ""),
                    is_sent_by_me=m.get("is_sent_by_me", False),
                    content=m.get("content", ""),
                    timestamp=m.get("timestamp", 0),
                    date_str=m.get("date_str", ""),
                    memory_tier=m.get("memory_tier", "long_term")
                )
                session.merge(msg_obj)
            session.commit()
            logger.info(f"SQLAlchemy batch merged {len(messages)} messages.")
        except Exception as exc:
            session.rollback()
            logger.exception(f"Error in SQLAlchemy store_messages_batch: {exc}")
        finally:
            session.close()

    def get_working_messages(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Working Memory: Fetches active messages (<48h) via SQLAlchemy ORM."""
        session = self.get_session()
        try:
            stmt = (
                select(Message)
                .where(Message.memory_tier == "working")
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
            results = session.scalars(stmt).all()
            return [m.to_dict() for m in results]
        finally:
            session.close()

    def get_episodic_narrative(self, contact_or_thread: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Episodic Memory: Reconstructs chronological story with a contact/topic."""
        session = self.get_session()
        try:
            term = f"%{contact_or_thread}%"
            stmt = (
                select(Message)
                .where(
                    or_(
                        Message.thread_title.ilike(term),
                        Message.sender.ilike(term)
                    )
                )
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
            results = list(session.scalars(stmt).all())
            # Return in chronological order
            results.reverse()
            return [m.to_dict() for m in results]
        finally:
            session.close()

    def get_latest_message_timestamp(self, source: str = "whatsapp") -> Optional[int]:
        """Returns the timestamp (ms) of the most recent message in DuckDB via func.max()."""
        session = self.get_session()
        try:
            stmt = select(func.max(Message.timestamp)).where(Message.source == source)
            return session.scalar(stmt)
        finally:
            session.close()

    def refresh_message_memory_tiers(self):
        """Ages existing messages across the 3 cognitive memory tiers based on elapsed time:
        Working (<48h) -> Episodic (2-30d) -> Long-Term (>30d).
        """
        session = self.get_session()
        try:
            now_sec = time.time()
            working_cutoff_ms = int((now_sec - (48 * 3600)) * 1000)
            episodic_cutoff_ms = int((now_sec - (30 * 24 * 3600)) * 1000)

            # Age Working -> Episodic
            session.execute(
                update(Message)
                .where(Message.memory_tier == "working", Message.timestamp < working_cutoff_ms)
                .values(memory_tier="episodic")
            )

            # Age Episodic -> Long-Term Archive
            session.execute(
                update(Message)
                .where(Message.memory_tier == "episodic", Message.timestamp < episodic_cutoff_ms)
                .values(memory_tier="long_term")
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error aging message tiers via SQLAlchemy: {exc}")
        finally:
            session.close()

    def search_messages(self, query: str, limit: int = 6) -> List[Dict[str, Any]]:
        """Searches across all message archives (Long-Term & Episodic) using SQLAlchemy."""
        session = self.get_session()
        try:
            term = f"%{query}%"
            stmt = (
                select(Message)
                .where(
                    or_(
                        Message.content.ilike(term),
                        Message.thread_title.ilike(term),
                        Message.sender.ilike(term)
                    )
                )
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )
            results = session.scalars(stmt).all()
            return [m.to_dict() for m in results]
        finally:
            session.close()

    def get_recent_messages(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Gets recent messages across all chats."""
        session = self.get_session()
        try:
            stmt = select(Message).order_by(Message.timestamp.desc()).limit(limit)
            results = session.scalars(stmt).all()
            return [m.to_dict() for m in results]
        finally:
            session.close()

    # --- Intermediate Memory (Daily Digest & Active Context) ---

    def update_intermediate_item(self, item_id: str, category: str, content: str, source_id: Optional[str] = None):
        """Upserts an item into Intermediate Memory using SQLAlchemy ORM."""
        session = self.get_session()
        try:
            existing = session.get(IntermediateMemory, item_id)
            if existing:
                existing.category = category
                existing.content = content
                existing.source_id = source_id or ""
            else:
                new_item = IntermediateMemory(
                    id=item_id,
                    category=category,
                    content=content,
                    source_id=source_id or ""
                )
                session.add(new_item)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error updating intermediate item {item_id}: {exc}")
        finally:
            session.close()

    def get_intermediate_context(self) -> str:
        """Returns active briefing context to inject into Qwen's system prompt."""
        session = self.get_session()
        try:
            stmt = select(IntermediateMemory).order_by(IntermediateMemory.updated_at.desc()).limit(20)
            items = session.scalars(stmt).all()

            if not items:
                return ""

            lines = ["--- CURRENT ACTIVE CONTEXT (INTERMEDIATE MEMORY) ---"]
            for item in items:
                lines.append(f"• [{item.category.upper()}] {item.content}")
            lines.append("--------------------------------------------------")
            return "\n".join(lines)
        finally:
            session.close()

    # --- Short-Term Memory (Session Chat History) ---

    def add_chat_turn(self, session_id: str, role: str, content: str):
        """Records a chat turn via SQLAlchemy ORM."""
        session = self.get_session()
        try:
            entry = ChatHistory(session_id=session_id, role=role, content=content)
            session.add(entry)
            session.commit()
        except Exception as exc:
            session.rollback()
            logger.error(f"Error saving chat turn via SQLAlchemy: {exc}")
        finally:
            session.close()

    def get_recent_chat_turns(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """Retrieves recent chat turns for multi-turn context."""
        session = self.get_session()
        try:
            stmt = (
                select(ChatHistory)
                .where(ChatHistory.session_id == session_id)
                .order_by(ChatHistory.id.desc())
                .limit(limit)
            )
            results = list(session.scalars(stmt).all())
            results.reverse()
            return [{"role": r.role, "content": r.content} for r in results]
        finally:
            session.close()

    # --- Contacts & Cellular Dialing Memory ---

    def index_contacts(self, contacts: List[Dict[str, Any]]) -> int:
        """Alias for store_contacts_batch used by contact sync services."""
        return self.store_contacts_batch(contacts)

    def store_contacts_batch(self, contacts: List[Dict[str, Any]]) -> int:
        """Batch upserts contacts into DuckDB using native SQL ON CONFLICT."""
        if not contacts:
            return 0

        clean_contacts = [
            {
                "id": str(c.get("id")),
                "name": str(c.get("name", "Unknown")),
                "phone_number": str(c.get("phone_number", "")),
                "source": str(c.get("source", "beeper"))
            }
            for c in contacts if c.get("id")
        ]
        if not clean_contacts:
            return 0

        session = self.get_session()
        try:
            stmt = text("""
                INSERT INTO contacts (id, name, phone_number, source, updated_at)
                VALUES (:id, :name, :phone_number, :source, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    phone_number = EXCLUDED.phone_number,
                    source = EXCLUDED.source,
                    updated_at = CURRENT_TIMESTAMP
            """)
            session.execute(stmt, clean_contacts)
            session.commit()
            logger.info(f"Batch upserted {len(clean_contacts)} contacts into DuckDB.")
            return len(clean_contacts)
        except Exception as exc:
            session.rollback()
            logger.exception(f"Error in store_contacts_batch: {exc}")
            return 0
        finally:
            session.close()

    def get_known_contacts_map(self) -> Dict[str, str]:
        """Returns a fast map of {phone_number: name} for delta-only contact syncing."""
        session = self.get_session()
        try:
            stmt = select(Contact.phone_number, Contact.name)
            rows = session.execute(stmt).all()
            return {r[0]: (r[1] or "") for r in rows if r[0]}
        finally:
            session.close()

    def get_contact_count(self) -> int:
        """Returns total number of contacts stored in DuckDB."""
        session = self.get_session()
        try:
            stmt = select(func.count(Contact.id))
            return session.scalar(stmt) or 0
        finally:
            session.close()

    def search_contacts(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches contacts by name or phone number."""
        session = self.get_session()
        try:
            clean_q = query.strip()
            if not clean_q:
                return []
            pattern = f"%{clean_q}%"
            stmt = (
                select(Contact)
                .where(
                    or_(
                        Contact.name.ilike(pattern),
                        Contact.phone_number.ilike(pattern)
                    )
                )
                .limit(limit)
            )
            results = session.scalars(stmt).all()
            return [c.to_dict() for c in results]
        finally:
            session.close()

    def find_contact(self, name_or_query: str) -> Optional[Dict[str, Any]]:
        """Finds the best matching contact for a call or messaging request.
        
        Handles voice/chat phrasing like 'Call Madhu', 'dial Prasad Appa', etc.
        Prioritizes:
        1. Exact name match (case-insensitive)
        2. Name starts-with
        3. Word/substring match, prioritizing real names over raw numbers
        """
        session = self.get_session()
        try:
            clean = name_or_query.strip()
            # Strip common action verbs
            for prefix in ["call to ", "call ", "ring to ", "ring ", "dial ", "phone ", "to ", "my "]:
                if clean.lower().startswith(prefix):
                    clean = clean[len(prefix):].strip()
                    break

            if not clean:
                return None

            lower_clean = clean.lower()

            # Expand family relationship aliases
            alias_map = {
                "dad": ["appa", "papa", "dad", "father"],
                "father": ["appa", "papa", "dad", "father"],
                "papa": ["appa", "papa", "dad", "father"],
                "appa": ["appa", "papa", "dad", "father"],
                "mom": ["amma", "mom", "mother", "maa"],
                "mother": ["amma", "mom", "mother", "maa"],
                "amma": ["amma", "mom", "mother", "maa"],
                "maa": ["amma", "mom", "mother", "maa"],
            }
            if lower_clean in alias_map:
                for alias in alias_map[lower_clean]:
                    stmt_alias = select(Contact).where(Contact.name.ilike(f"%{alias}%"))
                    alias_match = session.scalars(stmt_alias).first()
                    if alias_match:
                        return alias_match.to_dict()

            # 1. Exact match on name
            stmt_exact = select(Contact).where(func.lower(Contact.name) == lower_clean)
            exact = session.scalars(stmt_exact).first()
            if exact:
                return exact.to_dict()

            # 2. Starts with name
            stmt_starts = select(Contact).where(Contact.name.ilike(f"{clean}%"))
            starts = session.scalars(stmt_starts).first()
            if starts:
                return starts.to_dict()

            # 3. Substring / contains match
            stmt_contains = select(Contact).where(Contact.name.ilike(f"%{clean}%"))
            matches = list(session.scalars(stmt_contains).all())
            if matches:
                # Prioritize real names over entries where name is a raw phone number
                named_matches = [m for m in matches if not m.name.startswith("+")]
                if named_matches:
                    return named_matches[0].to_dict()
                return matches[0].to_dict()

            # 4. Try matching phone number directly
            stmt_phone = select(Contact).where(Contact.phone_number.ilike(f"%{clean}%"))
            phone_match = session.scalars(stmt_phone).first()
            if phone_match:
                return phone_match.to_dict()

            return None
        finally:
            session.close()



memory_service = MemoryService()


def get_memory_service() -> MemoryService:
    return memory_service
