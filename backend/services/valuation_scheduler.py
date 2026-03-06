"""Background valuation backfill scheduler.

Periodically checks whether daily holding value (DHV) backfill is needed
and runs it asynchronously, preventing gaps when the server runs across
multiple days without a sync.
"""

import asyncio
import logging
import threading
from datetime import date

from database import get_session_local
from services.portfolio_valuation_service import PortfolioValuationService
from services.sync_service import SyncService

logger = logging.getLogger(__name__)

# Module-level lock prevents concurrent backfill runs (e.g., scheduler
# firing while startup backfill is still in progress).
_backfill_lock = threading.Lock()

# How often the scheduler checks for backfill work (seconds).
BACKFILL_INTERVAL = 3600  # 1 hour


def run_backfill_if_needed(last_run_date: date | None) -> date | None:
    """Run valuation backfill if it hasn't already been done today.

    Args:
        last_run_date: The date of the last successful backfill run,
            or None if never run.

    Returns:
        date.today() on success, or last_run_date if skipped/failed.
    """
    today = date.today()

    if last_run_date == today:
        logger.debug("Valuation backfill already ran today — skipping")
        return last_run_date

    acquired = _backfill_lock.acquire(blocking=False)
    if not acquired:
        logger.debug("Valuation backfill lock held — skipping")
        return last_run_date

    try:
        if SyncService.is_sync_in_progress():
            logger.debug("Sync in progress — deferring backfill")
            return last_run_date

        SessionLocal = get_session_local()
        db = SessionLocal()
        try:
            service = PortfolioValuationService()
            result = service.backfill(db)
            if result.dates_calculated > 0:
                logger.info(
                    "Scheduled valuation backfill: %d days, %d holdings written",
                    result.dates_calculated,
                    result.holdings_written,
                )
            else:
                logger.debug("Scheduled valuation backfill: nothing to do")
            return today
        except Exception:
            logger.warning("Scheduled valuation backfill failed", exc_info=True)
            return last_run_date
        finally:
            db.close()
    finally:
        _backfill_lock.release()


async def backfill_loop(
    shutdown_event: asyncio.Event,
    startup_date: date | None = None,
) -> None:
    """Async entry point for the periodic backfill scheduler.

    Runs in a background task, checking every BACKFILL_INTERVAL seconds
    whether backfill is needed.

    Args:
        shutdown_event: Set this event to stop the loop cleanly.
        startup_date: Date of the startup backfill (to avoid redundant
            work on the same day).
    """
    logger.info("Valuation scheduler started (interval=%ds)", BACKFILL_INTERVAL)
    last_run_date = startup_date
    loop = asyncio.get_running_loop()

    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=BACKFILL_INTERVAL
            )
            # If we get here, the event was set — exit
            break
        except asyncio.TimeoutError:
            # Timer expired — time to check for backfill
            pass

        try:
            last_run_date = await loop.run_in_executor(
                None, run_backfill_if_needed, last_run_date
            )
        except Exception:
            logger.warning("Valuation scheduler iteration failed", exc_info=True)

    logger.info("Valuation scheduler stopped")
