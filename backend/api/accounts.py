"""Accounts API endpoints."""

import logging
from datetime import date, datetime, time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload

from api.helpers import get_latest_account_snapshot, get_or_404, holding_response_dict
from database import get_db

from schemas import (
    AccountCreate, AccountResponse, AccountUpdate, AccountWithValue,
    ActivityCreate, ActivityResponse, ActivityUpdate,
    BulkMarkReviewedRequest, DeactivateAccountRequest, HoldingResponse,
    ManualAccountCreate, ManualHoldingInput,
)
from models import Account, AccountSnapshot, DailyHoldingValue, Holding, HoldingLot, LotDisposal
from models.activity import Activity
from models.utils import generate_uuid
from services.account_service import AccountService
from services.lot_ledger_service import LotLedgerService
from services.manual_holdings_service import ManualHoldingsService
from services.portfolio_service import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _account_response_dict(account: Account) -> dict:
    """Build a response dict for an Account with asset class details."""
    return {
        "id": account.id,
        "provider_name": account.provider_name,
        "external_id": account.external_id,
        "name": account.name,
        "institution_name": account.institution_name,
        "is_active": account.is_active,
        "deactivated_at": account.deactivated_at,
        "superseded_by_account_id": account.superseded_by_account_id,
        "superseded_by_name": account.superseded_by.name if account.superseded_by else None,
        "account_type": account.account_type,
        "include_in_allocation": account.include_in_allocation,
        "assigned_asset_class_id": account.assigned_asset_class_id,
        "created_at": account.created_at,
        "updated_at": account.updated_at,
        "last_sync_time": account.last_sync_time,
        "last_sync_status": account.last_sync_status,
        "last_sync_error": account.last_sync_error,
        "balance_date": account.balance_date,
        "assigned_asset_class_name": account.assigned_asset_class.name if account.assigned_asset_class else None,
        "assigned_asset_class_color": account.assigned_asset_class.color if account.assigned_asset_class else None,
    }


@router.get("", response_model=list[AccountWithValue])
def list_accounts(db: Session = Depends(get_db)):
    """List all accounts with asset class details and total values."""
    accounts = db.query(Account).all()

    # Use PortfolioService (DHV-based) for market values of active accounts
    portfolio = PortfolioService().get_portfolio_summary(db)

    # Build account value map: prefer DHV values, fall back to AccountSnapshot
    account_value_map: dict[str, float] = {}
    for account in accounts:
        if account.id in portfolio:
            account_value_map[account.id] = float(portfolio[account.id].total_value)
        else:
            # Fallback for inactive accounts or accounts without DHV data
            latest_acct_snap = get_latest_account_snapshot(db, account.id)
            if latest_acct_snap is not None:
                account_value_map[account.id] = float(latest_acct_snap.total_value)

    # Populate asset class details from relationship
    result = []
    for account in accounts:
        account_dict = _account_response_dict(account)
        account_dict["value"] = account_value_map.get(account.id)
        result.append(account_dict)

    return result


@router.post("", response_model=AccountResponse)
def create_account(account_data: AccountCreate, db: Session = Depends(get_db)):
    """Create a new account."""
    account = Account(**account_data.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.post("/manual", response_model=AccountResponse)
def create_manual_account(
    data: ManualAccountCreate, db: Session = Depends(get_db)
):
    """Create a new manual account."""
    account = ManualHoldingsService.create_manual_account(
        db, name=data.name, institution_name=data.institution_name
    )
    return account


@router.get("/{account_id}", response_model=AccountResponse)
def get_account(account_id: str, db: Session = Depends(get_db)):
    """Get a specific account by ID with asset class details."""
    account = get_or_404(db, Account, account_id, "Account not found")
    return _account_response_dict(account)


@router.get("/{account_id}/holdings", response_model=list[HoldingResponse])
def get_account_holdings(account_id: str, db: Session = Depends(get_db)):
    """Get the latest holdings for a specific account."""
    get_or_404(db, Account, account_id, "Account not found")

    # Find the latest AccountSnapshot for this account
    latest_acct_snap = get_latest_account_snapshot(db, account_id)

    # If no snapshot participation, return empty list
    if latest_acct_snap is None:
        return []

    # Query holdings from that account snapshot with eager-loaded security
    holdings = (
        db.query(Holding)
        .options(joinedload(Holding.security))
        .filter(Holding.account_snapshot_id == latest_acct_snap.id)
        .all()
    )

    # Build DHV lookup: security_id → (close_price, market_value)
    from sqlalchemy import func
    dhv_lookup: dict[str, tuple] = {}
    latest_date = (
        db.query(func.max(DailyHoldingValue.valuation_date))
        .filter(
            DailyHoldingValue.account_id == account_id,
            DailyHoldingValue.account_snapshot_id == latest_acct_snap.id,
        )
        .scalar()
    )
    if latest_date is not None:
        dhv_rows = (
            db.query(DailyHoldingValue)
            .filter(
                DailyHoldingValue.account_id == account_id,
                DailyHoldingValue.account_snapshot_id == latest_acct_snap.id,
                DailyHoldingValue.valuation_date == latest_date,
            )
            .all()
        )
        for dhv in dhv_rows:
            dhv_lookup[dhv.security_id] = (dhv.close_price, dhv.market_value)

    # Build lot summary data
    market_prices = {
        sid: data[0] for sid, data in dhv_lookup.items() if data[0] is not None
    }
    total_quantities = {
        h.security_id: h.quantity for h in holdings
    }
    lot_summaries = LotLedgerService.get_lot_summaries_for_account(
        db, account_id, market_prices=market_prices, total_quantities=total_quantities
    )

    # Build response with security_name, market data from DHV, and lot data
    result = []
    for holding in holdings:
        dhv_data = dhv_lookup.get(holding.security_id)
        entry = {
            "id": holding.id,
            "account_snapshot_id": holding.account_snapshot_id,
            "security_id": holding.security_id,
            "ticker": holding.ticker,
            "quantity": holding.quantity,
            "snapshot_price": holding.snapshot_price,
            "snapshot_value": holding.snapshot_value,
            "created_at": holding.created_at,
            "security_name": holding.security.name if holding.security else None,
            "market_price": dhv_data[0] if dhv_data else None,
            "market_value": dhv_data[1] if dhv_data else None,
        }

        # Merge lot summary fields if lots exist for this security
        lot_summary = lot_summaries.get(holding.security_id)
        if lot_summary and lot_summary["lot_count"] > 0:
            cost_basis = lot_summary["total_cost_basis"]
            unrealized = lot_summary.get("unrealized_gain_loss")
            entry["cost_basis"] = cost_basis
            entry["gain_loss"] = unrealized
            entry["lot_coverage"] = lot_summary.get("lot_coverage")
            entry["lot_count"] = lot_summary["lot_count"]
            entry["realized_gain_loss"] = lot_summary.get("realized_gain_loss")
            # Compute gain_loss_percent
            if unrealized is not None and cost_basis and cost_basis != 0:
                entry["gain_loss_percent"] = unrealized / cost_basis
            else:
                entry["gain_loss_percent"] = None

        result.append(entry)

    return result


@router.get("/{account_id}/activities", response_model=list[ActivityResponse])
def get_account_activities(
    account_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    activity_type: Optional[str] = Query(default=None),
    reviewed: Optional[bool] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Get activities for a specific account with pagination and optional filters."""
    get_or_404(db, Account, account_id, "Account not found")

    query = db.query(Activity).filter(Activity.account_id == account_id)

    if activity_type:
        query = query.filter(Activity.type == activity_type)

    if reviewed is not None:
        query = query.filter(Activity.is_reviewed == reviewed)

    if start_date:
        query = query.filter(Activity.activity_date >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(Activity.activity_date <= datetime.combine(end_date, time(23, 59, 59)))

    activities = (
        query.order_by(Activity.activity_date.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return activities


@router.post("/{account_id}/activities", response_model=ActivityResponse, status_code=201)
def create_activity(
    account_id: str,
    body: ActivityCreate,
    db: Session = Depends(get_db),
):
    """Create a manual activity for an account."""
    get_or_404(db, Account, account_id, "Account not found")

    activity = Activity(
        account_id=account_id,
        provider_name="Manual",
        external_id=f"manual_{generate_uuid()}",
        activity_date=body.activity_date,
        type=body.type,
        amount=body.amount,
        description=body.description,
        ticker=body.ticker,
        notes=body.notes,
        user_modified=True,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)

    logger.info("Created manual activity %s for account %s", activity.id, account_id)
    return activity


@router.post("/{account_id}/activities/mark-reviewed")
def mark_activities_reviewed(
    account_id: str,
    body: BulkMarkReviewedRequest,
    db: Session = Depends(get_db),
):
    """Bulk mark activities as reviewed."""
    get_or_404(db, Account, account_id, "Account not found")

    updated_count = (
        db.query(Activity)
        .filter(
            Activity.id.in_(body.activity_ids),
            Activity.account_id == account_id,
            Activity.is_reviewed.is_(False),
        )
        .update({Activity.is_reviewed: True}, synchronize_session=False)
    )
    db.commit()

    logger.info(
        "Marked %d activities as reviewed for account %s", updated_count, account_id
    )
    return {"updated_count": updated_count}


@router.patch("/{account_id}/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(
    account_id: str,
    activity_id: str,
    body: ActivityUpdate,
    db: Session = Depends(get_db),
):
    """Update an activity."""
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.account_id == account_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    update_dict = body.model_dump(exclude_unset=True)

    if "activity_date" in update_dict and activity.provider_name != "Manual":
        raise HTTPException(
            status_code=400,
            detail="Cannot change activity_date on synced activities",
        )

    material_changed = (
        "type" in update_dict
        or "amount" in update_dict
        or "activity_date" in update_dict
    )

    for key, value in update_dict.items():
        setattr(activity, key, value)

    if material_changed:
        activity.user_modified = True
        logger.info(
            "Material change on activity %s: %s",
            activity_id,
            list(update_dict.keys()),
        )

    db.commit()
    db.refresh(activity)

    logger.info("Updated activity %s for account %s", activity_id, account_id)
    return activity


@router.delete("/{account_id}/activities/{activity_id}", status_code=204)
def delete_activity(
    account_id: str,
    activity_id: str,
    db: Session = Depends(get_db),
):
    """Delete a manual activity."""
    activity = (
        db.query(Activity)
        .filter(Activity.id == activity_id, Activity.account_id == account_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    if activity.provider_name != "Manual":
        raise HTTPException(
            status_code=400,
            detail="Only manual activities can be deleted",
        )

    # Nullify FK references from lots/disposals before deleting
    db.query(HoldingLot).filter(HoldingLot.activity_id == activity_id).update(
        {HoldingLot.activity_id: None}, synchronize_session=False
    )
    db.query(LotDisposal).filter(LotDisposal.activity_id == activity_id).update(
        {LotDisposal.activity_id: None}, synchronize_session=False
    )

    db.delete(activity)
    db.commit()

    logger.info("Deleted manual activity %s for account %s", activity_id, account_id)
    return Response(status_code=204)


@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str, account_data: AccountUpdate, db: Session = Depends(get_db)
):
    """Update an account."""
    account = get_or_404(db, Account, account_id, "Account not found")
    update_dict = account_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(account, key, value)

    # Mark name as user-edited if it was updated
    if "name" in update_dict:
        account.name_user_edited = True

    # Clear deactivation fields when re-activating
    if update_dict.get("is_active") is True:
        account.deactivated_at = None
        account.superseded_by_account_id = None

    db.commit()
    db.refresh(account)

    return _account_response_dict(account)


@router.post("/{account_id}/deactivate", response_model=AccountResponse)
def deactivate_account(
    account_id: str,
    body: DeactivateAccountRequest,
    db: Session = Depends(get_db),
):
    """Deactivate an account, optionally recording a $0 closing snapshot.

    The closing snapshot ensures historical portfolio charts show the account's
    value going to $0 on the deactivation date, rather than abruptly vanishing
    at the last sync date.
    """
    account = get_or_404(db, Account, account_id, "Account not found")
    if not account.is_active:
        raise HTTPException(status_code=400, detail="Account is already inactive")

    if body.superseded_by_account_id is not None:
        replacement = db.query(Account).filter(
            Account.id == body.superseded_by_account_id
        ).first()
        if replacement is None:
            raise HTTPException(status_code=400, detail="Replacement account not found")
        if replacement.id == account_id:
            raise HTTPException(
                status_code=400, detail="An account cannot supersede itself"
            )
        if not replacement.is_active:
            raise HTTPException(
                status_code=400, detail="Replacement account must be active"
            )

    result = AccountService.deactivate_account(
        db,
        account_id,
        create_closing_snapshot=body.create_closing_snapshot,
        superseded_by_account_id=body.superseded_by_account_id,
    )
    return _account_response_dict(result)


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: str, db: Session = Depends(get_db)):
    """Delete an account and all related data."""
    account = get_or_404(db, Account, account_id, "Account not found")
    account_name = account.name

    # Get account snapshot IDs for this account (needed for Holding deletion)
    acct_snap_ids = [
        s.id for s in
        db.query(AccountSnapshot.id).filter(AccountSnapshot.account_id == account_id).all()
    ]

    # Delete in FK order to avoid constraint violations
    db.query(LotDisposal).filter(LotDisposal.account_id == account_id).delete(synchronize_session=False)
    db.query(HoldingLot).filter(HoldingLot.account_id == account_id).delete(synchronize_session=False)
    db.query(DailyHoldingValue).filter(DailyHoldingValue.account_id == account_id).delete(synchronize_session=False)
    if acct_snap_ids:
        db.query(Holding).filter(Holding.account_snapshot_id.in_(acct_snap_ids)).delete(synchronize_session=False)
    db.query(Activity).filter(Activity.account_id == account_id).delete(synchronize_session=False)
    db.query(AccountSnapshot).filter(AccountSnapshot.account_id == account_id).delete(synchronize_session=False)
    db.delete(account)
    db.commit()

    logger.info("Deleted account %s (%s)", account_name, account_id)


def _get_manual_account(account_id: str, db: Session) -> Account:
    """Helper to fetch and validate a manual account."""
    account = get_or_404(db, Account, account_id, "Account not found")
    if not ManualHoldingsService.is_manual_account(account):
        raise HTTPException(
            status_code=400, detail="Holdings can only be modified on manual accounts"
        )
    return account


@router.post("/{account_id}/holdings", response_model=HoldingResponse)
def add_holding(
    account_id: str,
    holding_data: ManualHoldingInput,
    db: Session = Depends(get_db),
):
    """Add a holding to a manual account."""
    account = _get_manual_account(account_id, db)
    holding = ManualHoldingsService.add_holding(db, account, holding_data)
    # Refresh to ensure security relationship is loaded
    db.refresh(holding)
    return holding_response_dict(holding)


@router.put("/{account_id}/holdings/{holding_id}", response_model=HoldingResponse)
def update_holding(
    account_id: str,
    holding_id: str,
    holding_data: ManualHoldingInput,
    db: Session = Depends(get_db),
):
    """Update a holding on a manual account."""
    account = _get_manual_account(account_id, db)
    try:
        holding = ManualHoldingsService.update_holding(
            db, account, holding_id, holding_data
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Holding not found")
    # Refresh to ensure security relationship is loaded
    db.refresh(holding)
    return holding_response_dict(holding)


@router.delete("/{account_id}/holdings/{holding_id}", status_code=204)
def delete_holding(
    account_id: str,
    holding_id: str,
    db: Session = Depends(get_db),
):
    """Delete a holding from a manual account."""
    account = _get_manual_account(account_id, db)
    try:
        ManualHoldingsService.delete_holding(db, account, holding_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Holding not found")
