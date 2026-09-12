import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from app.config import settings
from app.services.gmail_service import gmail_service
from app.services.whatsapp_service import whatsapp_service
from app.services.sms_service import sms_service
from app.services.outlook_service import outlook_service

logger = logging.getLogger(__name__)


class BackgroundSyncService:
    """Manages periodic, non-blocking background synchronization across all sources
    (WhatsApp via Beeper, Gmail via OAuth, and Outlook if authenticated).
    
    Ensures Working Memory (<48h) and Episodic Memory stay continuously updated
    without manual user intervention.
    """

    def __init__(self):
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._lock: asyncio.Lock = asyncio.Lock()
        self.last_sync_time: Optional[str] = None
        self.last_sync_results: Dict[str, Any] = {}
        self.sync_count: int = 0

    async def start(self):
        """Starts the background sync loop."""
        if self.is_running:
            logger.warning("Background sync worker is already running.")
            return

        self.is_running = True
        logger.info(
            f"🚀 Background sync worker initialized. "
            f"Interval: every {settings.BACKGROUND_SYNC_INTERVAL_MINUTES} minutes."
        )
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stops the background sync worker gracefully."""
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Background sync worker stopped.")

    async def _run_loop(self):
        """Internal background loop running at configured intervals."""
        # Initial wait of 8 seconds to allow server startup and port bindings to settle
        await asyncio.sleep(8)

        while self.is_running:
            try:
                logger.info("⏰ Background sync interval triggered...")
                results = await self.sync_once()
                logger.info(
                    f"✅ Background sync cycle completed. "
                    f"Gmail: {results.get('gmail', {}).get('synced_count', 0)}, "
                    f"WhatsApp: {results.get('whatsapp', {}).get('synced_count', 0)}, "
                    f"SMS: {results.get('sms', {}).get('synced_count', 0)}"
                )
            except Exception as exc:
                logger.exception(f"Unexpected error during background sync: {exc}")

            # Sleep for the configured interval
            interval_seconds = max(60, settings.BACKGROUND_SYNC_INTERVAL_MINUTES * 60)
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break

    async def sync_once(self) -> Dict[str, Any]:
        """Executes a full multi-modal sync across Gmail, WhatsApp, and Outlook.
        Guarded by an asyncio.Lock so multiple sync runs never overlap or conflict.
        """
        async with self._lock:
            start_time = datetime.now()
            results: Dict[str, Any] = {
                "started_at": start_time.isoformat(),
                "gmail": {"status": "skipped", "synced_count": 0},
                "whatsapp": {"status": "skipped", "synced_count": 0},
                "outlook": {"status": "skipped", "synced_count": 0}
            }

            # 1. Sync Gmail
            try:
                if gmail_service.is_authenticated():
                    g_res = await gmail_service.sync_emails(max_results=15)
                    results["gmail"] = {
                        "status": "success" if g_res.get("success") else "failed",
                        "synced_count": g_res.get("synced_count", 0),
                        "message": g_res.get("message", "")
                    }
                else:
                    results["gmail"]["status"] = "not_authenticated"
            except Exception as exc:
                logger.error(f"Error during Gmail background sync: {exc}")
                results["gmail"] = {"status": "error", "error": str(exc), "synced_count": 0}

            # 2. Sync WhatsApp (Beeper SQLite)
            # Run in worker thread to prevent blocking the async event loop during SQLite snapshot
            try:
                if whatsapp_service.is_available():
                    w_res = await asyncio.to_thread(whatsapp_service.sync_messages)
                    results["whatsapp"] = {
                        "status": "success" if w_res.get("success") else "failed",
                        "synced_count": w_res.get("synced_count", 0),
                        "counts_by_tier": w_res.get("counts_by_tier", {}),
                        "message": w_res.get("message", "")
                    }
                else:
                    results["whatsapp"]["status"] = "db_not_found"
            except Exception as exc:
                logger.error(f"Error during WhatsApp background sync: {exc}")
                results["whatsapp"] = {"status": "error", "error": str(exc), "synced_count": 0}

            # 3. Sync Google Messages / SMS (Beeper SQLite)
            try:
                if sms_service.is_available():
                    s_res = await asyncio.to_thread(sms_service.sync_messages, 50)
                    results["sms"] = {
                        "status": "success" if s_res.get("success") else "failed",
                        "synced_count": s_res.get("synced_count", 0),
                        "message": s_res.get("message", "")
                    }
                else:
                    results["sms"]["status"] = "not_available"
            except Exception as exc:
                logger.error(f"Error during Google SMS background sync: {exc}")
                results["sms"] = {"status": "error", "error": str(exc), "synced_count": 0}

            # 4. Sync Outlook (if configured)
            try:
                if outlook_service.is_authenticated():
                    o_res = await outlook_service.sync_emails(max_results=15)
                    results["outlook"] = {
                        "status": "success" if o_res.get("success") else "failed",
                        "synced_count": o_res.get("synced_count", 0),
                        "message": o_res.get("message", "")
                    }
                else:
                    results["outlook"]["status"] = "not_configured_or_authenticated"
            except Exception as exc:
                logger.error(f"Error during Outlook background sync: {exc}")
                results["outlook"] = {"status": "error", "error": str(exc), "synced_count": 0}


            end_time = datetime.now()
            duration = round((end_time - start_time).total_seconds(), 2)

            results["completed_at"] = end_time.isoformat()
            results["duration_seconds"] = duration

            self.last_sync_time = end_time.isoformat()
            self.last_sync_results = results
            self.sync_count += 1

            return results

    def get_status(self) -> Dict[str, Any]:
        """Returns the current status of the background synchronization worker."""
        return {
            "enabled": settings.BACKGROUND_SYNC_ENABLED,
            "is_running": self.is_running,
            "interval_minutes": settings.BACKGROUND_SYNC_INTERVAL_MINUTES,
            "total_cycles_completed": self.sync_count,
            "last_sync_time": self.last_sync_time,
            "last_sync_results": self.last_sync_results,
            "sources": {
                "gmail_authenticated": gmail_service.is_authenticated(),
                "whatsapp_available": whatsapp_service.is_available(),
                "sms_available": sms_service.is_available(),
                "outlook_authenticated": outlook_service.is_authenticated()
            }

        }


background_sync_service = BackgroundSyncService()
