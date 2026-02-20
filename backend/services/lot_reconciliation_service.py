"""Lot reconciliation engine — creates and disposes lots during sync.

Compares previous vs. current account snapshots to detect position changes,
matches deltas against activity records, and creates/disposes HoldingLot
records accordingly.
"""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import asc
from sqlalchemy.orm import Session

from models import (
    Account,
    AccountSnapshot,
    HoldingLot,
    Holding,
    LotDisposal,
    SyncSession,
    generate_uuid,
)
from integrations.provider_protocol import ProviderHolding
from models.activity import Activity

logger = logging.getLogger(__name__)


class LotReconciliationService:
    """Reconciles holding lots against snapshots and activities."""

    @staticmethod
    def reconcile_account(
        db: Session,
        account: Account,
        previous_snapshot: AccountSnapshot | None,
        current_snapshot: AccountSnapshot,
        sync_session: SyncSession,
        provider_holdings: list[ProviderHolding] | None = None,
    ) -> None:
        """Reconcile lots for an account after a sync.

        Two-phase algorithm:
        1. Seed missing lots — ensure every current position has lot coverage
        2. Delta reconciliation — match quantity changes against activities

        Args:
            db: Database session
            account: The account being reconciled
            previous_snapshot: Previous successful AccountSnapshot (None on first sync)
            current_snapshot: The snapshot just created by this sync
            sync_session: The current sync session
            provider_holdings: Optional list of ProviderHolding for cost basis
        """
        is_first_sync = previous_snapshot is None

        prev_map = _build_holding_map(db, previous_snapshot) if previous_snapshot else {}
        curr_map = _build_holding_map(db, current_snapshot)

        if not curr_map and not prev_map:
            return

        # Build provider cost basis lookup: security_id -> cost_basis_per_unit
        provider_cost_basis: dict[str, Decimal] = {}
        if provider_holdings:
            # Map ticker -> security_id from current holdings
            ticker_to_security: dict[str, str] = {}
            for sec_id, info in curr_map.items():
                ticker_to_security[info["ticker"].upper()] = sec_id

            for ph in provider_holdings:
                if ph.cost_basis is not None and ph.cost_basis > 0:
                    sec_id = ticker_to_security.get(ph.symbol.upper())
                    if sec_id:
                        provider_cost_basis[sec_id] = ph.cost_basis

        # Prefetch all open lots for this account (avoids N+1 queries)
        open_lots_by_security = _fetch_open_lots_by_security(db, account)

        # Phase 1: Seed missing lots
        _seed_missing_lots(
            db, account, prev_map, curr_map, provider_cost_basis, is_first_sync,
            open_lots_by_security,
        )

        # Phase 2: Delta reconciliation (only if we have a previous snapshot)
        if previous_snapshot is not None:
            # Re-fetch after seeding so new initial lots are included
            open_lots_by_security = _fetch_open_lots_by_security(db, account)
            _reconcile_deltas(
                db, account, prev_map, curr_map, previous_snapshot,
                sync_session, provider_cost_basis, open_lots_by_security,
            )

        db.flush()
        logger.info(
            "Lot reconciliation complete for account %s (%s)",
            account.name, account.id[:8],
        )


def _build_holding_map(
    db: Session, snapshot: AccountSnapshot
) -> dict[str, dict]:
    """Build a map of security_id -> holding info from a snapshot.

    Returns:
        Dict of security_id -> {quantity, snapshot_price, ticker}
    """
    holdings = (
        db.query(Holding)
        .filter_by(account_snapshot_id=snapshot.id)
        .all()
    )
    result = {}
    for h in holdings:
        result[h.security_id] = {
            "quantity": h.quantity,
            "snapshot_price": h.snapshot_price,
            "ticker": h.ticker,
        }
    return result


def _fetch_open_lots_by_security(
    db: Session, account: Account
) -> dict[str, list[HoldingLot]]:
    """Fetch all open lots for an account, grouped by security_id.

    Lots within each group are ordered by acquisition_date ASC (NULLS FIRST),
    then created_at ASC — the FIFO disposal order.
    """
    all_open = (
        db.query(HoldingLot)
        .filter_by(account_id=account.id, is_closed=False)
        .order_by(
            asc(HoldingLot.acquisition_date).nulls_first(),
            asc(HoldingLot.created_at),
        )
        .all()
    )
    result: dict[str, list[HoldingLot]] = {}
    for lot in all_open:
        result.setdefault(lot.security_id, []).append(lot)
    return result


def _seed_missing_lots(
    db: Session,
    account: Account,
    prev_map: dict[str, dict],
    curr_map: dict[str, dict],
    provider_cost_basis: dict[str, Decimal],
    is_first_sync: bool,
    open_lots_by_security: dict[str, list[HoldingLot]],
) -> None:
    """Seed initial lots for positions that have no lot coverage.

    For each security in the current snapshot, determines the "reference
    quantity" (how many shares should already be covered by lots) and
    creates an initial lot for any gap.
    """
    for security_id, curr_info in curr_map.items():
        curr_qty = curr_info["quantity"]
        if curr_qty <= 0:
            continue

        # Reference quantity: how much we expect to already have lots for
        if is_first_sync:
            reference_qty = curr_qty
        else:
            prev_info = prev_map.get(security_id)
            reference_qty = prev_info["quantity"] if prev_info else Decimal("0")

        if reference_qty <= 0:
            continue

        # Check existing open lot coverage (from prefetched data)
        existing_coverage = open_lots_by_security.get(security_id, [])
        covered_qty = sum(
            (lot.current_quantity for lot in existing_coverage), Decimal("0")
        )

        gap = reference_qty - covered_qty
        if gap <= 0:
            continue

        # Determine cost basis: provider > snapshot price > $0
        cost_basis = provider_cost_basis.get(security_id)
        if cost_basis is None:
            cost_basis = curr_info["snapshot_price"] or Decimal("0")

        lot = HoldingLot(
            account_id=account.id,
            security_id=security_id,
            ticker=curr_info["ticker"],
            acquisition_date=None,
            cost_basis_per_unit=cost_basis,
            original_quantity=gap,
            current_quantity=gap,
            is_closed=False,
            source="initial",
        )
        db.add(lot)
        logger.info(
            "Seeded initial lot: %s shares of %s (cost basis: %s)",
            gap, curr_info["ticker"], cost_basis,
        )

    db.flush()


def _reconcile_deltas(
    db: Session,
    account: Account,
    prev_map: dict[str, dict],
    curr_map: dict[str, dict],
    previous_snapshot: AccountSnapshot,
    sync_session: SyncSession,
    provider_cost_basis: dict[str, Decimal],
    open_lots_by_security: dict[str, list[HoldingLot]],
) -> None:
    """Reconcile quantity deltas between snapshots against activities.

    For each security with a quantity change:
    - BUY (delta > 0): Match against buy activities, create lots
    - SELL (delta < 0): Apply FIFO disposal across open lots
    """
    # Query activities between previous and current sync timestamps
    prev_timestamp = previous_snapshot.sync_session.timestamp
    curr_timestamp = sync_session.timestamp

    activities = (
        db.query(Activity)
        .filter(
            Activity.account_id == account.id,
            Activity.activity_date > prev_timestamp,
            Activity.activity_date <= curr_timestamp,
            Activity.type.in_(["buy", "sell"]),
        )
        .order_by(Activity.activity_date.asc())
        .all()
    )

    # Group activities by ticker (case-insensitive)
    activities_by_ticker: dict[str, list[Activity]] = {}
    for act in activities:
        if act.ticker:
            key = act.ticker.upper()
            if key not in activities_by_ticker:
                activities_by_ticker[key] = []
            activities_by_ticker[key].append(act)

    # Collect all security IDs that appear in either snapshot
    all_security_ids = set(prev_map.keys()) | set(curr_map.keys())

    for security_id in all_security_ids:
        prev_info = prev_map.get(security_id)
        curr_info = curr_map.get(security_id)

        prev_qty = prev_info["quantity"] if prev_info else Decimal("0")
        curr_qty = curr_info["quantity"] if curr_info else Decimal("0")

        delta = curr_qty - prev_qty
        if delta == 0:
            continue

        # Get ticker for activity matching
        ticker = (curr_info or prev_info)["ticker"]
        ticker_upper = ticker.upper()

        # Get matching activities
        matched_activities = activities_by_ticker.get(ticker_upper, [])

        if delta > 0:
            # BUY: create lots for the increase
            matched_buys = [a for a in matched_activities if a.type == "buy"]
            _create_lots_for_buy(
                db, account, security_id, ticker, delta,
                matched_buys, curr_info, provider_cost_basis,
            )
        else:
            # SELL: apply FIFO disposal
            abs_delta = abs(delta)
            matched_sells = [a for a in matched_activities if a.type == "sell"]

            sell_price = _get_sell_price(matched_sells, curr_info, prev_info)
            sell_date = _get_sell_date(matched_sells, sync_session)

            # Determine source and activity_id
            if matched_sells:
                source = "activity"
                activity_id = matched_sells[0].id
            else:
                source = "inferred"
                activity_id = None

            _apply_fifo_disposal(
                db, account, security_id, abs_delta,
                sell_price, sell_date, source, activity_id,
                open_lots_by_security.get(security_id, []),
            )


def _create_lots_for_buy(
    db: Session,
    account: Account,
    security_id: str,
    ticker: str,
    delta: Decimal,
    matched_buys: list[Activity],
    curr_info: dict | None,
    provider_cost_basis: dict[str, Decimal],
) -> None:
    """Create lots for a quantity increase (buy delta).

    Matches against buy activities in order, creating "activity" lots for
    matched units (capped at delta), and an "inferred" lot for any remainder.
    """
    remaining = delta

    for buy in matched_buys:
        if remaining <= 0:
            break

        buy_qty = buy.units if buy.units else Decimal("0")
        if buy_qty <= 0:
            continue

        # Cap at remaining delta
        lot_qty = min(buy_qty, remaining)

        cost_basis = buy.price if buy.price else Decimal("0")
        acq_date = buy.activity_date.date() if buy.activity_date else None

        lot = HoldingLot(
            account_id=account.id,
            security_id=security_id,
            ticker=ticker,
            acquisition_date=acq_date,
            cost_basis_per_unit=cost_basis,
            original_quantity=lot_qty,
            current_quantity=lot_qty,
            is_closed=False,
            source="activity",
            activity_id=buy.id,
        )
        db.add(lot)
        remaining -= lot_qty

        logger.info(
            "Created activity lot: %s shares of %s @ %s (activity %s)",
            lot_qty, ticker, cost_basis, buy.id[:8],
        )

    # Create inferred lot for any remainder
    if remaining > 0:
        # Cost basis precedence: provider > snapshot price > $0
        cost_basis = provider_cost_basis.get(security_id)
        if cost_basis is None and curr_info:
            cost_basis = curr_info["snapshot_price"] or Decimal("0")
        if cost_basis is None:
            cost_basis = Decimal("0")

        lot = HoldingLot(
            account_id=account.id,
            security_id=security_id,
            ticker=ticker,
            acquisition_date=None,
            cost_basis_per_unit=cost_basis,
            original_quantity=remaining,
            current_quantity=remaining,
            is_closed=False,
            source="inferred",
        )
        db.add(lot)

        logger.info(
            "Created inferred lot: %s shares of %s @ %s",
            remaining, ticker, cost_basis,
        )

    db.flush()


def _get_sell_price(
    matched_sells: list[Activity],
    curr_info: dict | None,
    prev_info: dict | None,
) -> Decimal:
    """Determine the sell price from activities or snapshot fallback.

    Priority: activity price > current snapshot price > previous snapshot price > $0
    """
    for sell in matched_sells:
        if sell.price and sell.price > 0:
            return sell.price

    if curr_info and curr_info["snapshot_price"] and curr_info["snapshot_price"] > 0:
        return curr_info["snapshot_price"]

    if prev_info and prev_info["snapshot_price"] and prev_info["snapshot_price"] > 0:
        return prev_info["snapshot_price"]

    return Decimal("0")


def _get_sell_date(
    matched_sells: list[Activity],
    sync_session: SyncSession,
) -> date:
    """Determine the sell date from activities or sync session fallback."""
    for sell in matched_sells:
        if sell.activity_date:
            return sell.activity_date.date()

    return sync_session.timestamp.date()


def _apply_fifo_disposal(
    db: Session,
    account: Account,
    security_id: str,
    quantity: Decimal,
    proceeds_per_unit: Decimal,
    disposal_date: date,
    source: str,
    activity_id: str | None,
    open_lots: list[HoldingLot],
) -> int:
    """Apply FIFO disposal across open lots.

    Disposes quantity from the oldest lots first. The caller must provide
    lots already sorted in FIFO order (acquisition_date ASC NULLS FIRST,
    created_at ASC). Creates LotDisposal records sharing a disposal_group_id.

    Returns:
        Number of disposals created.
    """
    if not open_lots:
        logger.warning(
            "No open lots for FIFO disposal: %s shares of security %s",
            quantity, security_id,
        )
        return 0

    remaining = quantity
    disposal_group_id = generate_uuid()
    disposal_count = 0

    for lot in open_lots:
        if remaining <= 0:
            break

        dispose_qty = min(lot.current_quantity, remaining)
        if dispose_qty <= 0:
            continue

        disposal = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security_id,
            disposal_date=disposal_date,
            quantity=dispose_qty,
            proceeds_per_unit=proceeds_per_unit,
            source=source,
            activity_id=activity_id,
            disposal_group_id=disposal_group_id,
        )
        db.add(disposal)

        lot.current_quantity -= dispose_qty
        if lot.current_quantity == 0:
            lot.is_closed = True

        remaining -= dispose_qty
        disposal_count += 1

        logger.info(
            "FIFO disposal: %s shares from lot %s (remaining: %s)",
            dispose_qty, lot.id[:8], lot.current_quantity,
        )

    if remaining > 0:
        logger.warning(
            "FIFO disposal incomplete: %s shares unallocated for security %s",
            remaining, security_id,
        )

    db.flush()
    return disposal_count
