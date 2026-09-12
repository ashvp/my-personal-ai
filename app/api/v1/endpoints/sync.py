from fastapi import APIRouter, Depends, status
from app.services.background_sync import background_sync_service
from app.core.security import verify_device_token

router = APIRouter(prefix="/sync", tags=["Background Sync"])


@router.get(
    "/status",
    summary="Get background sync worker status",
    description="Returns the status of the automatic background synchronizer, last execution time, and connected data sources.",
    dependencies=[Depends(verify_device_token)]
)
async def get_sync_status():
    """Returns status and metrics for the background sync engine."""
    return background_sync_service.get_status()


@router.post(
    "/trigger",
    summary="Trigger immediate multi-modal sync",
    description="Forces an immediate synchronization cycle across Gmail, WhatsApp, and Outlook without waiting for the next timer interval.",
    dependencies=[Depends(verify_device_token)]
)
async def trigger_sync():
    """Immediately triggers a sync across all available data sources."""
    results = await background_sync_service.sync_once()
    return {
        "success": True,
        "message": "Immediate background sync cycle completed.",
        "results": results
    }
