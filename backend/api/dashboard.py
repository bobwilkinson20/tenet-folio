"""Dashboard API endpoints."""

import logging
from datetime import timezone
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Account, AssetClass
from services.classification_service import ClassificationService
from services.portfolio_service import PortfolioService
from utils.query_params import parse_account_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class AccountSummary(BaseModel):
    """Summary of a single account with sync status."""

    id: str
    name: str
    provider_name: str
    institution_name: Optional[str] = None
    value: Decimal
    # Per-account sync status
    last_sync_time: Optional[str] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    balance_date: Optional[str] = None
    # Per-account valuation health
    valuation_status: Optional[Literal["ok", "partial", "missing", "stale"]] = None
    valuation_date: Optional[str] = None  # ISO date (YYYY-MM-DD)


class AllocationData(BaseModel):
    """Allocation data for dashboard."""

    asset_type_id: str
    asset_type_name: str
    asset_type_color: str
    target_percent: Decimal
    actual_percent: Decimal
    delta_percent: Decimal
    value: Decimal


class DashboardResponse(BaseModel):
    """Dashboard data response."""

    total_net_worth: Decimal
    allocation_total: Decimal
    accounts: list[AccountSummary]
    allocations: list[AllocationData]
    unassigned_count: int
    unassigned_value: Decimal


@router.get("", response_model=DashboardResponse)
def get_dashboard(
    allocation_only: bool = Query(False, description="Filter to allocation accounts only"),
    account_ids: Optional[str] = Query(
        None, description="Comma-separated account IDs to filter by"
    ),
    db: Session = Depends(get_db),
):
    """Get dashboard summary with account values and per-account sync status."""
    parsed_ids = parse_account_ids(account_ids)

    # Get active accounts, optionally filtered to allocation-only and/or account IDs
    account_query = db.query(Account).filter(Account.is_active.is_(True))
    if allocation_only:
        account_query = account_query.filter(
            Account.include_in_allocation.is_(True)
        )
    if parsed_ids is not None:
        account_query = account_query.filter(Account.id.in_(parsed_ids))
    active_accounts = account_query.all()

    # Get current portfolio data using best-available source per account
    portfolio_service = PortfolioService()
    current_data = portfolio_service.get_portfolio_summary(
        db, account_ids=parsed_ids
    )

    # Get valuation status for all active accounts
    active_account_ids = [a.id for a in active_accounts]
    valuation_statuses = portfolio_service.get_valuation_status(db, active_account_ids) if active_account_ids else {}

    # Build account summaries with sync status
    accounts = []
    for account in active_accounts:
        # Format last sync time
        last_sync_time = None
        if account.last_sync_time:
            timestamp = account.last_sync_time
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            last_sync_time = timestamp.isoformat()

        # Format balance date
        balance_date_str = None
        if account.balance_date:
            bd = account.balance_date
            if bd.tzinfo is None:
                bd = bd.replace(tzinfo=timezone.utc)
            balance_date_str = bd.isoformat()

        # Use current portfolio data for account value
        account_value = Decimal("0")
        if account.id in current_data:
            account_value = current_data[account.id].total_value

        # Valuation health status
        val_info = valuation_statuses.get(account.id)
        val_status = val_info.status if val_info else None
        val_date = val_info.valuation_date.isoformat() if val_info and val_info.valuation_date else None

        accounts.append(
            AccountSummary(
                id=account.id,
                name=account.name,
                provider_name=account.provider_name,
                institution_name=account.institution_name,
                value=account_value,
                last_sync_time=last_sync_time,
                last_sync_status=account.last_sync_status,
                last_sync_error=account.last_sync_error,
                balance_date=balance_date_str,
                valuation_status=val_status,
                valuation_date=val_date,
            )
        )

    total_net_worth = sum(acc.value for acc in accounts)

    # Calculate allocation using PortfolioService (allocation accounts only)
    allocations = []
    allocation_total = Decimal("0")
    unassigned_count = 0
    unassigned_value = Decimal("0")

    allocation_result = portfolio_service.calculate_allocation(
        db, account_ids=parsed_ids, allocation_only=True
    )

    if allocation_result["total"] > 0:
        allocation_total = allocation_result["total"]

        # Get asset types for targets
        asset_types = db.query(AssetClass).all()
        asset_type_map = {at.id: at for at in asset_types}

        # Build allocation response
        for type_id, data in allocation_result["by_type"].items():
            asset_type = asset_type_map.get(type_id)
            if asset_type:
                actual_percent = data["percent"]
                target_percent = asset_type.target_percent
                delta_percent = actual_percent - target_percent

                allocations.append(
                    AllocationData(
                        asset_type_id=type_id,
                        asset_type_name=data["name"],
                        asset_type_color=data["color"],
                        target_percent=target_percent,
                        actual_percent=actual_percent,
                        delta_percent=delta_percent,
                        value=data["value"],
                    )
                )

        unassigned_value = allocation_result["unassigned"]["value"]
        classification_service = ClassificationService()
        unassigned_count = classification_service.count_unassigned_securities(db)

    return DashboardResponse(
        total_net_worth=total_net_worth,
        allocation_total=allocation_total,
        accounts=accounts,
        allocations=allocations,
        unassigned_count=unassigned_count,
        unassigned_value=unassigned_value,
    )
