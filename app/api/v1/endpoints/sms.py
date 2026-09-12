from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func

from app.services.sms_service import SMSService, get_sms_service
from app.services.memory_service import MemoryService, get_memory_service
from app.models.memory import Message
from app.core.security import verify_device_token

router = APIRouter(prefix="/sms", tags=["SMS Sync"])


@router.post(
    "/sync",
    summary="Sync Google Messages / SMS from Beeper",
    description="Fetches recent Google Messages (SMS) from Beeper SQLite, classifies into 3-tier memory, and ingests into DuckDB.",
    dependencies=[Depends(verify_device_token)]
)
async def sync_sms(
    limit: int = Query(default=50, description="Number of recent SMS to fetch (default: 50)"),
    sms: SMSService = Depends(get_sms_service)
):
    """Triggers an ingestion of Google Messages / SMS into DuckDB."""
    return sms.sync_messages(limit=limit)


@router.get(
    "/status",
    summary="Check SMS ingestion status",
    description="Returns availability of Google Messages bridge in Beeper and counts of SMS stored in DuckDB.",
    dependencies=[Depends(verify_device_token)]
)
async def sms_status(
    sms: SMSService = Depends(get_sms_service),
    memory: MemoryService = Depends(get_memory_service)
):
    """Returns status and recent SMS count from DuckDB."""
    is_avail = sms.is_available()
    session = memory.get_session()
    try:
        count = session.scalar(
            select(func.count(Message.id)).where(Message.source == "sms")
        ) or 0
        recent = session.scalars(
            select(Message)
            .where(Message.source == "sms")
            .order_by(Message.timestamp.desc())
            .limit(5)
        ).all()

        return {
            "beeper_available": is_avail,
            "total_sms_in_duckdb": count,
            "recent_sample": [
                {
                    "from": m.thread_title,
                    "content": m.content[:100],
                    "date": m.date_str,
                    "tier": m.memory_tier
                }
                for m in recent
            ]
        }
    finally:
        session.close()
