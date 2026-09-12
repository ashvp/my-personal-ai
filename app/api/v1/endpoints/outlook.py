from fastapi import APIRouter, Depends, status
from app.services.outlook_service import OutlookService, get_outlook_service
from app.services.memory_service import MemoryService, get_memory_service
from app.core.security import verify_device_token

router = APIRouter(prefix="/outlook", tags=["Outlook Sync"])


@router.post(
    "/sync",
    summary="Sync recent Outlook / College emails",
    description="Fetches recent emails via Microsoft Graph API, tags them as 'outlook_college', saves to DuckDB, and updates Active Briefing.",
    dependencies=[Depends(verify_device_token)]
)
async def sync_outlook(
    max_results: int = 15,
    outlook: OutlookService = Depends(get_outlook_service)
):
    """Triggers an on-demand sync of recent Outlook / College emails."""
    return await outlook.sync_emails(max_results=max_results)


@router.get(
    "/status",
    summary="Check Outlook sync status",
    description="Returns whether Microsoft Graph OAuth is authenticated and shows recent college emails in DuckDB.",
    dependencies=[Depends(verify_device_token)]
)
async def outlook_status(
    outlook: OutlookService = Depends(get_outlook_service),
    memory: MemoryService = Depends(get_memory_service)
):
    is_auth = outlook.is_authenticated()
    recent = memory.search_emails("college", limit=5)

    return {
        "authenticated": is_auth,
        "recent_college_emails_sample": recent,
        "token_file": outlook.token_path
    }
