"""Sync API endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from integrations.exceptions import ProviderAuthError, ProviderError
from schemas import SyncSessionResponse
from services.portfolio_valuation_service import PortfolioValuationService
from services.sync_service import SyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Dependency injection for testing
_sync_service_override: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Get SyncService instance, allowing for test overrides."""
    if _sync_service_override is not None:
        return _sync_service_override
    return SyncService()


def set_sync_service_override(service: Optional[SyncService]) -> None:
    """Set a SyncService override for testing."""
    global _sync_service_override
    _sync_service_override = service


@router.post("", response_model=SyncSessionResponse)
def trigger_sync(
    db: Session = Depends(get_db),
    sync_service: SyncService = Depends(get_sync_service),
):
    """Trigger a unified portfolio sync from all configured providers.

    Upserts accounts from providers, then fetches and stores holdings for all
    active accounts. Always returns 200 with the sync session. Success/failure
    is communicated via is_complete and sync_log entries in the response.

    Args:
        db: Database session

    Returns:
        The created sync session with holdings and sync_log

    Raises:
        HTTPException:
            - 409 Conflict: Sync is already in progress
            - 500 Internal Server Error: Unexpected sync error
            - 502 Bad Gateway: Provider authentication or connection error
    """
    # Early check to avoid starting valuation backfill if sync is already running
    if sync_service.is_sync_in_progress():
        raise HTTPException(
            status_code=409,
            detail="Sync already in progress. Please wait for the current sync to complete.",
        )

    try:
        # Valuation backfill: fill any DHV gaps through yesterday before
        # sync creates today's data. This is the only backfill step during
        # sync — the startup backfill in main.py provides a safety net for
        # any gaps that aren't filled here.
        try:
            valuation_service = PortfolioValuationService()
            backfill_result = valuation_service.backfill(db)
            if backfill_result.dates_calculated > 0:
                logger.info(
                    "Pre-sync valuation: %d days, %d holdings written",
                    backfill_result.dates_calculated,
                    backfill_result.holdings_written,
                )
        except Exception:
            logger.warning("Pre-sync valuation backfill failed", exc_info=True)

        sync_session = sync_service.trigger_sync(db)

        return sync_session

    except ValueError as e:
        # Sync lock contention
        if "already in progress" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Sync already in progress. Please wait for the current sync to complete.",
            )
        raise  # Re-raise other ValueErrors

    except ProviderAuthError as e:
        logger.warning("Provider auth error during sync: %s", e)
        raise HTTPException(
            status_code=502,
            detail=(
                f"Provider authentication failed for {e.provider_name}. "
                "Please check your credentials and try again."
            ),
        )

    except ProviderError as e:
        logger.warning("Provider error during sync: %s", e)
        raise HTTPException(
            status_code=502,
            detail="A provider error occurred during sync. Check the logs for details.",
        )

    except Exception:
        # Safety catch for truly unexpected errors — never expose str(e)
        logger.error("Unexpected error during sync", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during sync.",
        )
