"""Portfolio API endpoints."""

import logging
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Account, DailyHoldingValue, HoldingLot, LotDisposal, Security
from models.activity import Activity
from schemas.account import (
    AllocationTarget,
    AllocationTargetResponse,
    AllocationTargetUpdate,
    CashFlowAccountSummary,
)
from schemas.portfolio_returns import (
    PeriodReturn,
    PortfolioReturnsResponse,
    ScopeReturnsResponse,
)
from schemas.portfolio_valuation import (
    AccountDHVDiagnostic,
    DHVDiagnosticsResponse,
    PortfolioValueHistoryResponse,
    SeriesData,
    ValuePoint,
)
from services.asset_type_service import AssetTypeService
from services.classification_service import ClassificationService
from services.portfolio_returns_service import PortfolioReturnsService, _signed_cash_flow
from services.portfolio_service import PortfolioService
from services.portfolio_valuation_service import PortfolioValuationService
from utils.query_params import parse_account_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
service = AssetTypeService()


@router.get("/allocation", response_model=AllocationTargetResponse)
def get_allocation_targets(db: Session = Depends(get_db)):
    """
    Get current target allocation for all asset types.

    Returns:
        Current allocation targets with total and validity check
    """
    asset_types = service.list_all(db)

    allocations = [
        AllocationTarget(asset_type_id=at.id, target_percent=at.target_percent)
        for at in asset_types
    ]

    total = service.get_total_target_percent(db)
    is_valid = total == Decimal("100.00")

    return {
        "allocations": allocations,
        "total_percent": total,
        "is_valid": is_valid,
    }


@router.put("/allocation", response_model=AllocationTargetResponse)
def update_allocation_targets(
    update_data: AllocationTargetUpdate, db: Session = Depends(get_db)
):
    """
    Update target allocation for multiple asset types.

    Validates that targets sum to exactly 100%.

    Args:
        update_data: List of allocation targets

    Returns:
        Updated allocation targets

    Raises:
        HTTPException: If targets don't sum to 100%
    """
    # Convert to list of dicts for service
    allocations_dict = [
        {
            "asset_type_id": alloc.asset_type_id,
            "target_percent": alloc.target_percent,
        }
        for alloc in update_data.allocations
    ]

    # Update via service (validates sum = 100%)
    service.update_all_targets(db, allocations_dict)

    # Return updated state
    return get_allocation_targets(db)


class GroupBy(str, Enum):
    """Aggregation level for value history."""

    total = "total"
    account = "account"
    asset_class = "asset_class"


def _get_account_ids_for_filter(
    db: Session,
    allocation_only: bool,
    account_ids: list[str] | None = None,
    include_inactive: bool = False,
) -> list[str] | None:
    """Get filtered account IDs or None for all accounts.

    Args:
        db: Database session
        allocation_only: If True, return only allocation account IDs
        account_ids: If provided, restrict to these account IDs
        include_inactive: If True, include inactive accounts in results.
            Use for historical queries where deactivated accounts' past
            data should remain visible.

    Returns:
        List of account IDs if filtering, None if all accounts
    """
    if not allocation_only and account_ids is None and include_inactive:
        return None  # No filter needed — all accounts, all history
    query = db.query(Account.id)
    if not include_inactive:
        query = query.filter(Account.is_active.is_(True))
    if allocation_only:
        query = query.filter(Account.include_in_allocation.is_(True))
    if account_ids is not None:
        query = query.filter(Account.id.in_(account_ids))
    return [a.id for a in query.all()]


@router.get("/value-history", response_model=PortfolioValueHistoryResponse)
def get_value_history(
    start: Optional[date] = Query(None, description="Start date (inclusive)"),
    end: Optional[date] = Query(None, description="End date (inclusive)"),
    group_by: GroupBy = Query(GroupBy.total, description="Aggregation level"),
    allocation_only: bool = Query(
        False, description="Filter to allocation accounts only"
    ),
    account_ids: Optional[str] = Query(
        None, description="Comma-separated account IDs to filter by"
    ),
    db: Session = Depends(get_db),
):
    """Get historical portfolio value as a time series.

    Returns pre-computed daily valuations aggregated by the requested level:
    - total: single series of total portfolio value per day
    - account: one series per account
    - asset_class: one series per asset class (using classification waterfall)
    """
    parsed_ids = parse_account_ids(account_ids)
    # Historical charts include inactive accounts — their past DHV records are
    # factually accurate and should remain visible after deactivation.
    # Current-state views (dashboard, allocations) continue to filter to
    # is_active=True only via separate calls.
    filtered_ids = _get_account_ids_for_filter(
        db, allocation_only, parsed_ids, include_inactive=True
    )

    # Determine date range from stored data
    date_query = db.query(
        func.min(DailyHoldingValue.valuation_date),
        func.max(DailyHoldingValue.valuation_date),
    )
    if filtered_ids is not None:
        date_query = date_query.filter(DailyHoldingValue.account_id.in_(filtered_ids))
    min_date, max_date = date_query.one()

    if min_date is None or max_date is None:
        # No valuation data exists
        return PortfolioValueHistoryResponse(
            start_date=start or date.today(),
            end_date=end or date.today(),
            data_points=[] if group_by == GroupBy.total else None,
            series={} if group_by != GroupBy.total else None,
        )

    effective_start = start or min_date
    # When no explicit end date, include today so live data point can be appended
    effective_end = end or max(max_date, date.today())

    if group_by == GroupBy.total:
        return _get_total_history(
            db, effective_start, effective_end, account_ids=filtered_ids
        )
    elif group_by == GroupBy.account:
        return _get_account_history(
            db, effective_start, effective_end, account_ids=filtered_ids
        )
    else:
        return _get_asset_class_history(
            db, effective_start, effective_end, account_ids=filtered_ids
        )


def _get_total_history(
    db: Session,
    start: date,
    end: date,
    account_ids: list[str] | None = None,
) -> PortfolioValueHistoryResponse:
    """Aggregate daily portfolio total.

    Appends a live data point for today using PortfolioService
    when the requested end date includes today.
    """
    query = db.query(
        DailyHoldingValue.valuation_date,
        func.sum(DailyHoldingValue.market_value).label("total_value"),
    ).filter(
        DailyHoldingValue.valuation_date >= start,
        DailyHoldingValue.valuation_date <= end,
    )

    if account_ids is not None:
        query = query.filter(DailyHoldingValue.account_id.in_(account_ids))

    rows = (
        query
        .group_by(DailyHoldingValue.valuation_date)
        .order_by(DailyHoldingValue.valuation_date)
        .all()
    )

    data_points = [
        ValuePoint(date=row.valuation_date, value=row.total_value)
        for row in rows
    ]

    # Always use live portfolio summary for today's data point.
    # DHV rows for today may only exist for freshly-synced accounts (stale
    # accounts don't get new DHV rows), so the raw DHV sum can undercount.
    # PortfolioService.get_portfolio_summary() uses each account's latest
    # DHV date independently, giving the correct total.
    today = date.today()
    if end >= today:
        portfolio_service = PortfolioService()
        current_data = portfolio_service.get_portfolio_summary(
            db, account_ids=account_ids
        )
        if current_data:
            today_total = sum(
                cd.total_value for cd in current_data.values()
            )
            # Replace any partial DHV-based today entry with the live total
            data_points = [dp for dp in data_points if dp.date != today]
            data_points.append(ValuePoint(date=today, value=today_total))

    return PortfolioValueHistoryResponse(
        start_date=start,
        end_date=end,
        data_points=data_points,
    )


def _get_account_history(
    db: Session,
    start: date,
    end: date,
    account_ids: list[str] | None = None,
) -> PortfolioValueHistoryResponse:
    """Aggregate daily values per account."""
    query = db.query(
        DailyHoldingValue.valuation_date,
        DailyHoldingValue.account_id,
        func.sum(DailyHoldingValue.market_value).label("account_value"),
    ).filter(
        DailyHoldingValue.valuation_date >= start,
        DailyHoldingValue.valuation_date <= end,
    )

    if account_ids is not None:
        query = query.filter(DailyHoldingValue.account_id.in_(account_ids))

    rows = (
        query
        .group_by(DailyHoldingValue.valuation_date, DailyHoldingValue.account_id)
        .order_by(DailyHoldingValue.valuation_date, DailyHoldingValue.account_id)
        .all()
    )

    # Preload account names to avoid per-row queries
    account_ids = {row.account_id for row in rows}
    accounts = db.query(Account).filter(Account.id.in_(account_ids)).all()
    account_names = {a.id: a.name for a in accounts}

    # Build per-account series
    account_points: dict[str, list[ValuePoint]] = {}

    for row in rows:
        aid = row.account_id
        if aid not in account_points:
            account_points[aid] = []
        account_points[aid].append(
            ValuePoint(date=row.valuation_date, value=row.account_value)
        )

    series = {
        aid: SeriesData(
            account_name=account_names.get(aid, aid), data_points=points
        )
        for aid, points in account_points.items()
    }

    return PortfolioValueHistoryResponse(
        start_date=start,
        end_date=end,
        series=series,
    )


def _get_asset_class_history(
    db: Session,
    start: date,
    end: date,
    account_ids: list[str] | None = None,
) -> PortfolioValueHistoryResponse:
    """Aggregate daily values per asset class using classification waterfall."""
    query = db.query(DailyHoldingValue).filter(
        DailyHoldingValue.valuation_date >= start,
        DailyHoldingValue.valuation_date <= end,
    )

    if account_ids is not None:
        query = query.filter(DailyHoldingValue.account_id.in_(account_ids))

    rows = query.order_by(DailyHoldingValue.valuation_date).all()

    # Batch-classify all unique (account_id, ticker) pairs (2 DB queries)
    classification_service = ClassificationService()
    unique_pairs = list({(row.account_id, row.ticker) for row in rows})
    classifications = classification_service.classify_holdings_batch(db, unique_pairs)

    pair_to_class: dict[tuple[str, str], str] = {}
    class_meta: dict[str, dict[str, str]] = {}

    for pair, asset_class in classifications.items():
        if asset_class:
            pair_to_class[pair] = asset_class.id
            if asset_class.id not in class_meta:
                class_meta[asset_class.id] = {
                    "name": asset_class.name,
                    "color": asset_class.color,
                }
        else:
            pair_to_class[pair] = "unassigned"

    if "unassigned" not in class_meta and "unassigned" in pair_to_class.values():
        class_meta["unassigned"] = {
            "name": "Unassigned",
            "color": "#9CA3AF",
        }

    # Aggregate by date + asset class
    # (date, class_id) -> accumulated value
    date_class_values: dict[tuple[date, str], Decimal] = {}

    for row in rows:
        class_id = pair_to_class[(row.account_id, row.ticker)]
        key = (row.valuation_date, class_id)
        date_class_values[key] = (
            date_class_values.get(key, Decimal("0")) + row.market_value
        )

    # Build series per asset class
    class_points: dict[str, list[ValuePoint]] = {}
    for (d, class_id), value in sorted(date_class_values.items()):
        if class_id not in class_points:
            class_points[class_id] = []
        class_points[class_id].append(ValuePoint(date=d, value=value))

    series = {
        class_id: SeriesData(
            asset_class_name=class_meta[class_id]["name"],
            asset_class_color=class_meta[class_id]["color"],
            data_points=points,
        )
        for class_id, points in class_points.items()
    }

    return PortfolioValueHistoryResponse(
        start_date=start,
        end_date=end,
        series=series,
    )


@router.get("/dhv-diagnostics", response_model=DHVDiagnosticsResponse)
def get_dhv_diagnostics(db: Session = Depends(get_db)):
    """Analyze DHV gaps for each active account.

    Returns per-account gap analysis showing expected vs actual DHV days
    and lists of missing dates.
    """
    valuation_service = PortfolioValuationService()
    account_gaps = valuation_service.diagnose_gaps(db)

    accounts = [AccountDHVDiagnostic(**gap) for gap in account_gaps]
    total_missing = sum(gap["missing_days"] for gap in account_gaps)
    total_partial = sum(gap.get("partial_days", 0) for gap in account_gaps)

    return DHVDiagnosticsResponse(
        accounts=accounts,
        total_missing_days=total_missing,
        total_partial_days=total_partial,
    )


def _get_active_account_ids(db: Session) -> list[str]:
    """Return IDs of all active accounts."""
    return [
        a.id
        for a in db.query(Account.id).filter(Account.is_active.is_(True)).all()
    ]


@router.get("/cost-basis")
def get_cost_basis(
    account_ids: Optional[str] = Query(
        None, description="Comma-separated account IDs to filter by"
    ),
    db: Session = Depends(get_db),
):
    """Portfolio-wide cost basis summary.

    Aggregates open lots across all active accounts and computes
    unrealized and YTD realized gain/loss.
    """
    parsed_ids = parse_account_ids(account_ids)
    filtered_ids = _get_account_ids_for_filter(db, False, parsed_ids)
    active_account_ids = filtered_ids if filtered_ids is not None else _get_active_account_ids(db)

    if not active_account_ids:
        return {
            "has_lots": False,
            "lot_count": 0,
            "coverage_percent": None,
            "total_cost_basis": None,
            "total_market_value": None,
            "total_unrealized_gain_loss": None,
            "total_realized_gain_loss_ytd": None,
        }

    # Open lots for active accounts
    open_lots = (
        db.query(HoldingLot)
        .filter(
            HoldingLot.account_id.in_(active_account_ids),
            HoldingLot.is_closed.is_(False),
        )
        .all()
    )

    if not open_lots:
        return {
            "has_lots": False,
            "lot_count": 0,
            "coverage_percent": None,
            "total_cost_basis": None,
            "total_market_value": None,
            "total_unrealized_gain_loss": None,
            "total_realized_gain_loss_ytd": None,
        }

    # Get latest DHV close prices per (account_id, security_id)
    # Subquery: max valuation_date per (account_id, security_id)
    latest_date_sub = (
        db.query(
            DailyHoldingValue.account_id,
            DailyHoldingValue.security_id,
            func.max(DailyHoldingValue.valuation_date).label("max_date"),
        )
        .filter(DailyHoldingValue.account_id.in_(active_account_ids))
        .group_by(DailyHoldingValue.account_id, DailyHoldingValue.security_id)
        .subquery()
    )

    latest_dhvs = (
        db.query(DailyHoldingValue)
        .join(
            latest_date_sub,
            (DailyHoldingValue.account_id == latest_date_sub.c.account_id)
            & (DailyHoldingValue.security_id == latest_date_sub.c.security_id)
            & (DailyHoldingValue.valuation_date == latest_date_sub.c.max_date),
        )
        .all()
    )

    # Map (account_id, security_id) -> close_price
    price_map: dict[tuple[str, str], Decimal] = {}
    for dhv in latest_dhvs:
        price_map[(dhv.account_id, dhv.security_id)] = dhv.close_price

    # Compute cost basis and market value from lots
    total_cost_basis = Decimal("0")
    total_market_value = Decimal("0")
    lotted_value = Decimal("0")

    for lot in open_lots:
        lot_cost = lot.cost_basis_per_unit * lot.current_quantity
        total_cost_basis += lot_cost

        price = price_map.get((lot.account_id, lot.security_id))
        if price is not None:
            mv = price * lot.current_quantity
            total_market_value += mv
            lotted_value += mv

    total_unrealized = total_market_value - total_cost_basis

    # YTD realized gain/loss
    ytd_start = date(date.today().year, 1, 1)
    ytd_disposals = (
        db.query(LotDisposal)
        .join(HoldingLot, LotDisposal.holding_lot_id == HoldingLot.id)
        .options(joinedload(LotDisposal.holding_lot))
        .filter(
            LotDisposal.account_id.in_(active_account_ids),
            LotDisposal.disposal_date >= ytd_start,
        )
        .all()
    )

    total_realized_ytd = Decimal("0")
    for disposal in ytd_disposals:
        gain = (
            disposal.proceeds_per_unit - disposal.holding_lot.cost_basis_per_unit
        ) * disposal.quantity
        total_realized_ytd += gain

    # Coverage percent
    portfolio_service = PortfolioService()
    summary = portfolio_service.get_portfolio_summary(
        db, account_ids=parsed_ids
    )
    total_portfolio_value = Decimal("0")
    if summary:
        total_portfolio_value = sum(cd.total_value for cd in summary.values())

    coverage_percent = None
    if total_portfolio_value > 0:
        coverage_percent = float(lotted_value / total_portfolio_value * 100)

    logger.info(
        "Cost basis summary: %d lots, cost_basis=%s, market_value=%s, unrealized=%s",
        len(open_lots),
        total_cost_basis,
        total_market_value,
        total_unrealized,
    )

    return {
        "has_lots": True,
        "lot_count": len(open_lots),
        "coverage_percent": coverage_percent,
        "total_cost_basis": str(total_cost_basis),
        "total_market_value": str(total_market_value),
        "total_unrealized_gain_loss": str(total_unrealized),
        "total_realized_gain_loss_ytd": str(total_realized_ytd),
    }


@router.get("/realized-gains")
def get_realized_gains(
    year: Optional[int] = Query(None, description="Filter by year"),
    db: Session = Depends(get_db),
):
    """Realized gains report with optional year filter."""
    active_account_ids = _get_active_account_ids(db)

    query = (
        db.query(LotDisposal)
        .join(HoldingLot, LotDisposal.holding_lot_id == HoldingLot.id)
        .options(joinedload(LotDisposal.holding_lot))
        .filter(LotDisposal.account_id.in_(active_account_ids))
    )

    if year is not None:
        year_start = date(year, 1, 1)
        year_end = date(year, 12, 31)
        query = query.filter(
            LotDisposal.disposal_date >= year_start,
            LotDisposal.disposal_date <= year_end,
        )

    disposals = query.order_by(LotDisposal.disposal_date.desc()).all()

    # Preload account and security names
    account_ids = {d.account_id for d in disposals}
    security_ids = {d.security_id for d in disposals}

    accounts = {
        a.id: a.name
        for a in db.query(Account).filter(Account.id.in_(account_ids)).all()
    } if account_ids else {}

    securities = {
        s.id: s
        for s in db.query(Security).filter(Security.id.in_(security_ids)).all()
    } if security_ids else {}

    items = []
    total_realized = Decimal("0")

    for d in disposals:
        cost_basis_per_unit = d.holding_lot.cost_basis_per_unit
        total_proceeds = d.proceeds_per_unit * d.quantity
        total_cost = cost_basis_per_unit * d.quantity
        gain_loss = total_proceeds - total_cost
        total_realized += gain_loss

        sec = securities.get(d.security_id)

        items.append({
            "disposal_id": d.id,
            "disposal_date": d.disposal_date.isoformat(),
            "ticker": sec.ticker if sec else "",
            "security_name": sec.name if sec else "",
            "account_name": accounts.get(d.account_id, ""),
            "quantity": str(d.quantity),
            "cost_basis_per_unit": str(cost_basis_per_unit),
            "proceeds_per_unit": str(d.proceeds_per_unit),
            "total_cost": str(total_cost),
            "total_proceeds": str(total_proceeds),
            "gain_loss": str(gain_loss),
            "source": d.source,
        })

    logger.info(
        "Realized gains report: %d disposals, total=%s, year=%s",
        len(items),
        total_realized,
        year,
    )

    return {
        "items": items,
        "total_realized_gain_loss": str(total_realized),
        "year": year,
    }


@router.get("/returns", response_model=PortfolioReturnsResponse)
def get_returns(
    scope: str = Query("all", description="'all', 'portfolio', or account UUID"),
    periods: str = Query(
        "1D,1M,QTD,3M,YTD,1Y",
        description="Comma-separated period codes",
    ),
    include_inactive: bool = Query(
        False, description="Include inactive accounts",
    ),
    account_ids: Optional[str] = Query(
        None, description="Comma-separated account IDs to filter by"
    ),
    db: Session = Depends(get_db),
):
    """Portfolio and per-account IRR returns across time horizons."""
    period_list = [p.strip() for p in periods.split(",") if p.strip()]
    parsed_ids = parse_account_ids(account_ids)
    returns_service = PortfolioReturnsService()
    result = returns_service.get_returns(
        db,
        scope=scope,
        periods=period_list,
        include_inactive=include_inactive,
        account_ids=parsed_ids,
    )

    def _to_scope_response(scope_returns):
        return ScopeReturnsResponse(
            scope_id=scope_returns.scope_id,
            scope_name=scope_returns.scope_name,
            periods=[
                PeriodReturn(
                    period=pr.period,
                    irr=str(pr.irr) if pr.irr is not None else None,
                    start_date=pr.start_date,
                    end_date=pr.end_date,
                    has_sufficient_data=pr.has_sufficient_data,
                )
                for pr in scope_returns.periods
            ],
        )

    logger.info(
        "Returns requested: scope=%s, periods=%s, include_inactive=%s",
        scope, period_list, include_inactive,
    )

    return PortfolioReturnsResponse(
        portfolio=_to_scope_response(result.portfolio) if result.portfolio else None,
        accounts=[_to_scope_response(a) for a in result.accounts],
    )


@router.get("/cashflow-summary", response_model=list[CashFlowAccountSummary])
def get_cashflow_summary(
    start_date: Optional[date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[date] = Query(None, description="End date (inclusive)"),
    include_inactive: bool = Query(False, description="Include inactive accounts"),
    db: Session = Depends(get_db),
):
    """Per-account summary of activities for cash flow review.

    Returns inflows, outflows, net flow, and unreviewed counts
    grouped by account. Includes all active accounts (and optionally
    inactive ones) so users can add manual activities to any account.
    """
    query = db.query(Activity)

    if start_date:
        query = query.filter(
            Activity.activity_date >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        )
    if end_date:
        query = query.filter(
            Activity.activity_date <= datetime.combine(end_date, time(23, 59, 59), tzinfo=timezone.utc)
        )

    activities = query.all()

    # Load accounts
    account_query = db.query(Account)
    if not include_inactive:
        account_query = account_query.filter(Account.is_active.is_(True))
    all_accounts = {a.id: a.name for a in account_query.all()}

    # Seed account_data with all active accounts (zero values)
    def empty_entry():
        return {
            "inflows": Decimal("0"),
            "outflows": Decimal("0"),
            "count": 0,
            "unreviewed": 0,
        }
    account_data: dict[str, dict] = {
        aid: empty_entry() for aid in all_accounts
    }

    # Accumulate activity data — only cash-flow types contribute to totals
    cash_flow_types = PortfolioReturnsService.CASH_FLOW_TYPES

    for act in activities:
        if act.account_id not in account_data:
            # Skip orphaned activities (deleted accounts)
            continue
        entry = account_data[act.account_id]
        entry["count"] += 1
        if not act.is_reviewed:
            entry["unreviewed"] += 1
        if act.type in cash_flow_types and act.amount is not None:
            signed = _signed_cash_flow(act.type, act.amount)
            if signed > 0:
                entry["inflows"] += signed
            else:
                entry["outflows"] += signed

    result = []
    for aid, data in account_data.items():
        result.append(CashFlowAccountSummary(
            account_id=aid,
            account_name=all_accounts.get(aid, "Unknown"),
            total_inflows=data["inflows"],
            total_outflows=data["outflows"],
            net_flow=data["inflows"] + data["outflows"],
            activity_count=data["count"],
            unreviewed_count=data["unreviewed"],
        ))

    return result

