from fastapi import APIRouter, Depends, status
from app.services.whatsapp_service import WhatsAppService, get_whatsapp_service
from app.services.memory_service import MemoryService, get_memory_service
from app.core.security import verify_device_token

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp Sync"])


@router.post(
    "/sync",
    summary="Sync WhatsApp messages from Beeper",
    description="Reads messages from local Beeper SQLite store, categorizes them into 3-tier memory (working, episodic, long-term), and stores them in DuckDB.",
    dependencies=[Depends(verify_device_token)]
)
async def sync_whatsapp(
    whatsapp: WhatsAppService = Depends(get_whatsapp_service)
):
    """Triggers an on-demand sync of WhatsApp messages from Beeper."""
    return whatsapp.sync_messages()


@router.get(
    "/status",
    summary="Check WhatsApp sync status",
    description="Returns whether Beeper store is available, total messages, and active working memory items.",
    dependencies=[Depends(verify_device_token)]
)
async def whatsapp_status(
    whatsapp: WhatsAppService = Depends(get_whatsapp_service),
    memory: MemoryService = Depends(get_memory_service)
):
    is_avail = whatsapp.is_available()
    working_msgs = memory.get_working_messages(limit=5)
    recent_msgs = memory.get_recent_messages(limit=5)

    return {
        "beeper_available": is_avail,
        "beeper_path": whatsapp.db_path,
        "working_memory_sample": working_msgs,
        "recent_messages_sample": recent_msgs
    }
