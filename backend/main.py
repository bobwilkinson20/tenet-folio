"""FastAPI application entry point."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import accounts, asset_classes, config, dashboard, lots, market_data, plaid, portfolio, preferences, providers, reports, schwab, securities, snaptrade, sync
from config import settings
from database import get_session_local
from logging_config import setup_logging
from models import UserPreference
from services.asset_type_service import AssetTypeService
from services.credential_manager import ACTIVE_PROFILE
from services.portfolio_valuation_service import PortfolioValuationService
from services.valuation_scheduler import _backfill_lock, backfill_loop

DHV_VERIFIED_KEY = "system.dhv_verified_through"

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run portfolio valuation backfill on startup."""
    logger.info("Active profile: %s", ACTIVE_PROFILE or "default")
    SessionLocal = get_session_local()
    db = SessionLocal()
    startup_backfill_ok = False
    try:
        with _backfill_lock:
            service = PortfolioValuationService()
            result = service.backfill(db)
            if result.dates_calculated > 0:
                logger.info(
                    "Valuation backfill: %d days, %d holdings written",
                    result.dates_calculated,
                    result.holdings_written,
                )
            if result.errors:
                for error in result.errors:
                    logger.warning("Valuation backfill warning: %s", error)
            startup_backfill_ok = True
    except Exception:
        logger.warning("Valuation backfill failed on startup", exc_info=True)

    # Check for and repair historical DHV gaps, skipping if already verified
    # through yesterday. The verified-through date is cached so the diagnostic
    # only runs once after deploy or when new gaps could have appeared.
    try:
        yesterday = date.today() - timedelta(days=1)
        verified_pref = (
            db.query(UserPreference)
            .filter(UserPreference.key == DHV_VERIFIED_KEY)
            .first()
        )
        verified_through = None
        if verified_pref:
            verified_through = date.fromisoformat(json.loads(verified_pref.value))

        if verified_through is None or verified_through < yesterday:
            gaps = service.diagnose_gaps(db)
            total_missing = sum(g["missing_days"] for g in gaps)
            total_partial = sum(g.get("partial_days", 0) for g in gaps)
            if total_missing > 0 or total_partial > 0:
                logger.info(
                    "Found %d missing + %d partial DHV gaps across %d accounts — repairing",
                    total_missing,
                    total_partial,
                    sum(1 for g in gaps if g["missing_days"] > 0 or g.get("partial_days", 0) > 0),
                )
                repair_result = service.full_backfill(db)
                logger.info(
                    "DHV gap repair: %d days, %d holdings written",
                    repair_result.dates_calculated,
                    repair_result.holdings_written,
                )

            # Update verified-through date
            if verified_pref:
                verified_pref.value = json.dumps(yesterday.isoformat())
            else:
                db.add(UserPreference(
                    key=DHV_VERIFIED_KEY,
                    value=json.dumps(yesterday.isoformat()),
                ))
            db.commit()
        else:
            logger.debug("DHV integrity verified through %s — skipping gap check", verified_through)
    except Exception:
        logger.warning("DHV gap check failed on startup", exc_info=True)

    try:
        AssetTypeService().seed_default_asset_classes(db)
    except Exception:
        logger.warning("Asset class seeding failed on startup", exc_info=True)
    finally:
        db.close()

    # Start background valuation scheduler
    startup_date = date.today() if startup_backfill_ok else None
    shutdown_event = asyncio.Event()
    scheduler_task = asyncio.create_task(
        backfill_loop(shutdown_event, startup_date=startup_date)
    )

    yield

    # Graceful shutdown of the scheduler
    shutdown_event.set()
    try:
        await asyncio.wait_for(scheduler_task, timeout=10)
    except asyncio.TimeoutError:
        logger.warning("Valuation scheduler did not stop in time — cancelling")
        scheduler_task.cancel()
    except Exception:
        logger.warning("Error stopping valuation scheduler", exc_info=True)


app = FastAPI(
    title="Portfolio Manager",
    description="Personal portfolio tracking and asset allocation",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(accounts.router)
app.include_router(asset_classes.router)
app.include_router(dashboard.router)
app.include_router(lots.router)
app.include_router(market_data.router)
app.include_router(portfolio.router)
app.include_router(securities.router)
app.include_router(sync.router)
app.include_router(preferences.router)
app.include_router(plaid.router)
app.include_router(schwab.router)
app.include_router(snaptrade.router)
app.include_router(providers.router)
app.include_router(reports.router)
app.include_router(config.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    response = {"status": "ok"}
    if ACTIVE_PROFILE:
        response["profile"] = ACTIVE_PROFILE
    return response
