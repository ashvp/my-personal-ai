from fastapi import APIRouter, Depends, status
from app.services.gmail_service import GmailService, get_gmail_service
from app.services.memory_service import MemoryService, get_memory_service
from app.core.security import verify_device_token

router = APIRouter(prefix="/gmail", tags=["Gmail Sync"])


@router.post(
    "/sync",
    summary="Sync recent Gmail messages",
    description="Fetches recent emails, extracts sender/subject/body, saves to DuckDB, and updates Intermediate Memory.",
    dependencies=[Depends(verify_device_token)]
)
async def sync_gmail(
    max_results: int = 15,
    gmail: GmailService = Depends(get_gmail_service)
):
    """Triggers an on-demand sync of recent emails."""
    return await gmail.sync_emails(max_results=max_results)


@router.get(
    "/status",
    summary="Check Gmail sync status",
    description="Returns whether Gmail OAuth is authenticated and how many emails are currently in DuckDB.",
    dependencies=[Depends(verify_device_token)]
)
async def gmail_status(
    gmail: GmailService = Depends(get_gmail_service),
    memory: MemoryService = Depends(get_memory_service)
):
    """Returns authentication status and total stored emails count."""
    is_auth = gmail.is_authenticated()
    recent = memory.get_recent_emails(limit=5)

    return {
        "authenticated": is_auth,
        "recent_synced_sample": recent,
        "intermediate_briefing_active": bool(memory.get_intermediate_context())
    }
