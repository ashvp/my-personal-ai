from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Text, Boolean, BigInteger, Integer, Float, DateTime, func, Sequence
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy Declarative Base for DuckDB."""
    pass


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="gmail")
    sender: Mapped[Optional[str]] = mapped_column(String, default="")
    recipient: Mapped[Optional[str]] = mapped_column(String, default="")
    subject: Mapped[Optional[str]] = mapped_column(String, default="(No Subject)")
    snippet: Mapped[Optional[str]] = mapped_column(String, default="")
    body_clean: Mapped[Optional[str]] = mapped_column(Text, default="")
    summary: Mapped[Optional[str]] = mapped_column(String, default="")
    date: Mapped[Optional[str]] = mapped_column(String, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    labels: Mapped[Optional[str]] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "source": self.source,
            "sender": self.sender,
            "recipient": self.recipient,
            "subject": self.subject,
            "snippet": self.snippet,
            "body_clean": self.body_clean,
            "summary": self.summary,
            "date": self.date,
            "is_read": self.is_read,
            "labels": self.labels,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, default="whatsapp")
    thread_id: Mapped[Optional[str]] = mapped_column(String, default="")
    thread_title: Mapped[Optional[str]] = mapped_column(String, default="")
    sender: Mapped[Optional[str]] = mapped_column(String, default="")
    is_sent_by_me: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[Optional[str]] = mapped_column(Text, default="")
    timestamp: Mapped[int] = mapped_column(BigInteger, default=0)
    date_str: Mapped[Optional[str]] = mapped_column(String, default="")
    memory_tier: Mapped[str] = mapped_column(String, default="long_term")  # 'working', 'episodic', 'long_term'
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "thread_id": self.thread_id,
            "thread_title": self.thread_title,
            "sender": self.sender,
            "is_sent_by_me": self.is_sent_by_me,
            "content": self.content,
            "timestamp": self.timestamp,
            "date_str": self.date_str,
            "memory_tier": self.memory_tier,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class IntermediateMemory(Base):
    __tablename__ = "intermediate_memory"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    category: Mapped[Optional[str]] = mapped_column(String, default="")
    content: Mapped[Optional[str]] = mapped_column(Text, default="")
    source_id: Mapped[Optional[str]] = mapped_column(String, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "content": self.content,
            "source_id": self.source_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


chat_history_id_seq = Sequence("chat_history_id_seq")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, chat_history_id_seq, primary_key=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String)
    content: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    phone_number: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, default="beeper")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "phone_number": self.phone_number,
            "source": self.source
        }


# --- Bitemporal Knowledge Graph Models ---

class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String, default="Concept", index=True)
    aliases: Mapped[Optional[str]] = mapped_column(Text, default="")
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "aliases": self.aliases,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class TemporalEdge(Base):
    __tablename__ = "temporal_edges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    subject: Mapped[str] = mapped_column(String, index=True)
    predicate: Mapped[str] = mapped_column(String, index=True)
    object: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    valid_from: Mapped[str] = mapped_column(String, index=True)
    valid_to: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)  # None indicates CURRENTLY ACTIVE
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())

    @property
    def is_active(self) -> bool:
        return self.valid_to is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "is_active": self.is_active,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

