"""Tests for the LotReconciliationService."""

import pytest
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models import (
    Account,
    AccountSnapshot,
    Holding,
    HoldingLot,
    LotDisposal,
    Security,
    SyncSession,
)
from models.activity import Activity
from services.lot_reconciliation_service import LotReconciliationService


# --- Fixtures ---


@pytest.fixture
def recon_account(db: Session) -> Account:
    """Create a test account for reconciliation tests."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="recon_ext_001",
        name="Recon Test Account",
        is_active=True,
    )
    db.add(acc)
    db.flush()
    return acc


@pytest.fixture
def recon_security(db: Session) -> Security:
    """Create a test security for reconciliation tests."""
    sec = Security(ticker="AAPL", name="Apple Inc.")
    db.add(sec)
    db.flush()
    return sec


@pytest.fixture
def second_security(db: Session) -> Security:
    """Create a second test security."""
    sec = Security(ticker="GOOG", name="Alphabet Inc.")
    db.add(sec)
    db.flush()
    return sec


# --- Helpers ---


def _make_sync_session(
    db: Session,
    ts: datetime | None = None,
) -> SyncSession:
    """Create a sync session with a given timestamp."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    ss = SyncSession(timestamp=ts, is_complete=True)
    db.add(ss)
    db.flush()
    return ss


def _make_snapshot(
    db: Session,
    account: Account,
    sync_session: SyncSession,
    holdings_data: list[dict] | None = None,
) -> AccountSnapshot:
    """Create an AccountSnapshot with optional holdings.

    holdings_data: list of dicts with keys:
        security_id, ticker, quantity, snapshot_price
    """
    snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("0"),
    )
    db.add(snap)
    db.flush()

    for h in (holdings_data or []):
        holding = Holding(
            account_snapshot_id=snap.id,
            security_id=h["security_id"],
            ticker=h["ticker"],
            quantity=h["quantity"],
            snapshot_price=h.get("snapshot_price", Decimal("100.00")),
            snapshot_value=h["quantity"] * h.get("snapshot_price", Decimal("100.00")),
        )
        db.add(holding)

    db.flush()
    return snap


# --- TestInitialSeeding ---


class TestInitialSeeding:
    """Tests for Phase 1: seeding initial lots."""

    def test_first_sync_seeds_all_holdings(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """First sync (no prev snapshot) creates initial lots for all holdings."""
        ss = _make_sync_session(db)
        snap = _make_snapshot(db, recon_account, ss, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, None, snap, ss
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "initial"
        assert lots[0].original_quantity == Decimal("100")
        assert lots[0].current_quantity == Decimal("100")
        assert lots[0].acquisition_date is None
        assert lots[0].cost_basis_per_unit == Decimal("150.00")

    def test_first_sync_uses_provider_cost_basis(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """First sync uses provider cost basis over snapshot price."""
        from integrations.provider_protocol import ProviderHolding

        ss = _make_sync_session(db)
        snap = _make_snapshot(db, recon_account, ss, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        provider_holdings = [
            ProviderHolding(
                account_id="ext_001", symbol="AAPL",
                quantity=Decimal("100"), price=Decimal("155.00"),
                market_value=Decimal("15500.00"), currency="USD",
                cost_basis=Decimal("120.00"),
            )
        ]

        LotReconciliationService.reconcile_account(
            db, recon_account, None, snap, ss,
            provider_holdings=provider_holdings,
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].cost_basis_per_unit == Decimal("120.00")

    def test_first_sync_multiple_securities(
        self, db: Session, recon_account: Account,
        recon_security: Security, second_security: Security
    ):
        """First sync seeds initial lots for multiple securities."""
        ss = _make_sync_session(db)
        snap = _make_snapshot(db, recon_account, ss, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
            {"security_id": second_security.id, "ticker": "GOOG",
             "quantity": Decimal("50"), "snapshot_price": Decimal("2800.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, None, snap, ss
        )

        aapl_lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        goog_lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=second_security.id
        ).all()
        assert len(aapl_lots) == 1
        assert len(goog_lots) == 1
        assert aapl_lots[0].original_quantity == Decimal("100")
        assert goog_lots[0].original_quantity == Decimal("50")

    def test_subsequent_sync_seeds_missing_lots(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Subsequent sync seeds lots for positions that existed but have no lots."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("155.00")},
        ])

        # No existing lots — should seed based on previous qty
        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "initial"
        assert lots[0].original_quantity == Decimal("100")

    def test_no_seed_when_lots_already_cover(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """No initial lot created when existing lots already cover the position."""
        # Create existing lot that covers the position
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("140.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1  # Only the original manual lot
        assert lots[0].source == "manual"

    def test_partial_seed_for_gap(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Seed only the gap when lots partially cover the position."""
        # Create existing lot that covers 60 of 100
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("140.00"),
            original_quantity=Decimal("60"),
            current_quantity=Decimal("60"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            is_closed=False,
        ).order_by(HoldingLot.source.asc()).all()

        assert len(lots) == 2
        # initial lot fills gap of 40
        initial_lot = [lt for lt in lots if lt.source == "initial"][0]
        assert initial_lot.original_quantity == Decimal("40")

    def test_empty_portfolio_creates_no_lots(
        self, db: Session, recon_account: Account
    ):
        """First sync with no holdings creates no lots."""
        ss = _make_sync_session(db)
        snap = _make_snapshot(db, recon_account, ss, [])

        LotReconciliationService.reconcile_account(
            db, recon_account, None, snap, ss
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id
        ).all()
        assert len(lots) == 0

    def test_seed_plus_delta_increase(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Subsequent sync: seed for previous qty + inferred lot for delta increase."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("120"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).order_by(HoldingLot.source.asc()).all()

        assert len(lots) == 2
        initial = [lt for lt in lots if lt.source == "initial"][0]
        inferred = [lt for lt in lots if lt.source == "inferred"][0]
        assert initial.original_quantity == Decimal("100")  # seed for prev qty
        assert inferred.original_quantity == Decimal("20")   # delta

    def test_seed_plus_delta_decrease(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Subsequent sync: seed for previous qty + FIFO disposal for delta decrease."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("80"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()

        # Should have seeded 100, then disposed 20
        assert len(lots) == 1
        assert lots[0].source == "initial"
        assert lots[0].original_quantity == Decimal("100")
        assert lots[0].current_quantity == Decimal("80")

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(disposals) == 1
        assert disposals[0].quantity == Decimal("20")


# --- TestNewPosition ---


class TestNewPosition:
    """Tests for new securities appearing in current snapshot."""

    def test_new_security_no_activity_creates_inferred_lot(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """New security with no matching activity creates an inferred lot."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [])  # No AAPL before

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("50"), "snapshot_price": Decimal("150.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "inferred"
        assert lots[0].original_quantity == Decimal("50")
        assert lots[0].cost_basis_per_unit == Decimal("150.00")
        assert lots[0].acquisition_date is None

    def test_new_security_with_buy_activity_creates_activity_lot(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """New security with matching buy activity creates an activity lot."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [])

        # Create a buy activity between snapshots
        activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_001",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("50"),
            price=Decimal("145.00"),
            amount=Decimal("-7250.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("50"), "snapshot_price": Decimal("150.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "activity"
        assert lots[0].original_quantity == Decimal("50")
        assert lots[0].cost_basis_per_unit == Decimal("145.00")
        assert lots[0].activity_id == activity.id
        assert lots[0].acquisition_date == date(2025, 1, 1)


# --- TestQuantityIncrease ---


class TestQuantityIncrease:
    """Tests for position quantity increases (buy delta)."""

    def test_partial_activity_match(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Buy activity matches part of delta; remainder gets inferred lot."""
        # Pre-existing lot covering previous qty
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        # Activity covers 30 of the 50 share increase
        activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_002",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("30"),
            price=Decimal("148.00"),
            amount=Decimal("-4440.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("150"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            is_closed=False,
        ).order_by(HoldingLot.created_at.asc()).all()

        assert len(lots) == 3  # manual + activity + inferred
        sources = sorted([lt.source for lt in lots])
        assert sources == ["activity", "inferred", "manual"]

        activity_lot = [lt for lt in lots if lt.source == "activity"][0]
        assert activity_lot.original_quantity == Decimal("30")
        assert activity_lot.cost_basis_per_unit == Decimal("148.00")

        inferred_lot = [lt for lt in lots if lt.source == "inferred"][0]
        assert inferred_lot.original_quantity == Decimal("20")  # 50 - 30
        assert inferred_lot.cost_basis_per_unit == Decimal("155.00")  # snapshot price

    def test_activity_qty_exceeds_delta_capped(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Buy activity quantity exceeding delta is capped to delta."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        # Activity says 50 shares but delta is only 20
        activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_003",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("50"),
            price=Decimal("148.00"),
            amount=Decimal("-7400.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("120"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            is_closed=False,
        ).all()

        # manual (100) + activity (20, capped) = 2 lots, no inferred
        assert len(lots) == 2
        activity_lot = [lt for lt in lots if lt.source == "activity"][0]
        assert activity_lot.original_quantity == Decimal("20")  # capped at delta


# --- TestQuantityDecrease ---


class TestQuantityDecrease:
    """Tests for position quantity decreases (sell delta)."""

    def test_fifo_sell_against_single_lot(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """FIFO sell against a single lot reduces current_quantity."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("70"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        db.refresh(lot)
        assert lot.current_quantity == Decimal("70")
        assert lot.is_closed is False

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(disposals) == 1
        assert disposals[0].quantity == Decimal("30")
        assert disposals[0].source == "inferred"
        assert disposals[0].proceeds_per_unit == Decimal("155.00")

    def test_fifo_across_multiple_lots(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """FIFO sell across multiple lots (oldest first, shared disposal_group_id)."""
        # Create two lots: oldest (40 shares) and newer (60 shares)
        lot1 = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("120.00"),
            original_quantity=Decimal("40"),
            current_quantity=Decimal("40"),
            is_closed=False,
            source="manual",
        )
        lot2 = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("140.00"),
            original_quantity=Decimal("60"),
            current_quantity=Decimal("60"),
            is_closed=False,
            source="manual",
        )
        db.add_all([lot1, lot2])
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("50"), "snapshot_price": Decimal("160.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        db.refresh(lot1)
        db.refresh(lot2)

        # Lot1 (oldest) fully consumed: 40 sold
        assert lot1.current_quantity == Decimal("0")
        assert lot1.is_closed is True

        # Lot2: 10 sold (50 total - 40 from lot1)
        assert lot2.current_quantity == Decimal("50")
        assert lot2.is_closed is False

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).order_by(LotDisposal.quantity.desc()).all()

        assert len(disposals) == 2
        # Shared disposal group
        assert disposals[0].disposal_group_id == disposals[1].disposal_group_id
        assert disposals[0].disposal_group_id is not None

        # Verify quantities
        disposal_qtys = sorted([d.quantity for d in disposals])
        assert disposal_qtys == [Decimal("10"), Decimal("40")]

    def test_sell_with_activity(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Sell with matching activity uses activity price/source."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        # Create sell activity
        sell_activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="sell_001",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="sell",
            ticker="AAPL",
            units=Decimal("30"),
            price=Decimal("160.00"),
            amount=Decimal("4800.00"),
            currency="USD",
        )
        db.add(sell_activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("70"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(disposals) == 1
        assert disposals[0].source == "activity"
        assert disposals[0].proceeds_per_unit == Decimal("160.00")
        assert disposals[0].activity_id == sell_activity.id
        assert disposals[0].disposal_date == date(2025, 1, 1)


# --- TestFullSell ---


class TestFullSell:
    """Tests for complete position removal."""

    def test_full_sell_disposes_and_closes_lot(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Security completely removed from snapshot → full disposal, lot closed."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [])  # AAPL gone

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        db.refresh(lot)
        assert lot.current_quantity == Decimal("0")
        assert lot.is_closed is True

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(disposals) == 1
        assert disposals[0].quantity == Decimal("100")


# --- TestEdgeCases ---


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_no_previous_snapshot_first_sync(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """First sync with no previous snapshot seeds initial lots only."""
        ss = _make_sync_session(db)
        snap = _make_snapshot(db, recon_account, ss, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("50"), "snapshot_price": Decimal("150.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, None, snap, ss
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "initial"
        # No disposals created (no delta phase)
        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id
        ).all()
        assert len(disposals) == 0

    def test_unchanged_quantity_no_delta(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Unchanged quantity between syncs creates no new lots or disposals (when covered)."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "manual"

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id
        ).all()
        assert len(disposals) == 0

    def test_sell_with_no_existing_lots_seeds_then_disposes(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Sell with no existing lots: seeds initial lot first, then disposes."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("80"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        # Seeded 100, disposed 20 → 80 remaining
        assert len(lots) == 1
        assert lots[0].source == "initial"
        assert lots[0].original_quantity == Decimal("100")
        assert lots[0].current_quantity == Decimal("80")

        disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id
        ).all()
        assert len(disposals) == 1
        assert disposals[0].quantity == Decimal("20")

    def test_multiple_securities_handled_independently(
        self, db: Session, recon_account: Account,
        recon_security: Security, second_security: Security
    ):
        """Each security is reconciled independently."""
        lot_aapl = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        lot_goog = HoldingLot(
            account_id=recon_account.id,
            security_id=second_security.id,
            ticker="GOOG",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("2500.00"),
            original_quantity=Decimal("50"),
            current_quantity=Decimal("50"),
            is_closed=False,
            source="manual",
        )
        db.add_all([lot_aapl, lot_goog])
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
            {"security_id": second_security.id, "ticker": "GOOG",
             "quantity": Decimal("50"), "snapshot_price": Decimal("2800.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("120"), "snapshot_price": Decimal("155.00")},  # +20
            {"security_id": second_security.id, "ticker": "GOOG",
             "quantity": Decimal("30"), "snapshot_price": Decimal("2900.00")},  # -20
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        # AAPL: gained 20 → inferred lot
        aapl_lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(aapl_lots) == 2

        # GOOG: lost 20 → disposal
        db.refresh(lot_goog)
        assert lot_goog.current_quantity == Decimal("30")

        goog_disposals = db.query(LotDisposal).filter_by(
            account_id=recon_account.id, security_id=second_security.id
        ).all()
        assert len(goog_disposals) == 1
        assert goog_disposals[0].quantity == Decimal("20")

    def test_null_acquisition_date_lots_disposed_first_in_fifo(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Lots with NULL acquisition_date are disposed first (NULLS FIRST)."""
        lot_null = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=None,
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("30"),
            current_quantity=Decimal("30"),
            is_closed=False,
            source="initial",
        )
        lot_dated = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("120.00"),
            original_quantity=Decimal("70"),
            current_quantity=Decimal("70"),
            is_closed=False,
            source="manual",
        )
        db.add_all([lot_null, lot_dated])
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("60"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        db.refresh(lot_null)
        db.refresh(lot_dated)

        # NULL date lot fully consumed first (30 shares)
        assert lot_null.current_quantity == Decimal("0")
        assert lot_null.is_closed is True

        # Dated lot partially consumed (10 more needed: 40 - 30 = 10)
        assert lot_dated.current_quantity == Decimal("60")
        assert lot_dated.is_closed is False


# --- TestProviderCostBasis ---


class TestProviderCostBasis:
    """Tests for provider cost basis handling."""

    def test_provider_cost_basis_used_for_inferred_lots(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Provider cost basis is used for inferred lots when no activity."""
        from integrations.provider_protocol import ProviderHolding

        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("130"), "snapshot_price": Decimal("155.00")},
        ])

        provider_holdings = [
            ProviderHolding(
                account_id="ext_001", symbol="AAPL",
                quantity=Decimal("130"), price=Decimal("155.00"),
                market_value=Decimal("20150.00"), currency="USD",
                cost_basis=Decimal("142.00"),
            )
        ]

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2,
            provider_holdings=provider_holdings,
        )

        inferred_lot = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="inferred",
        ).first()
        assert inferred_lot is not None
        assert inferred_lot.cost_basis_per_unit == Decimal("142.00")

    def test_activity_price_takes_precedence_over_provider(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Activity price takes precedence over provider cost basis."""
        from integrations.provider_protocol import ProviderHolding

        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        # Buy activity with specific price
        activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_004",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("30"),
            price=Decimal("148.00"),
            amount=Decimal("-4440.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("130"), "snapshot_price": Decimal("155.00")},
        ])

        provider_holdings = [
            ProviderHolding(
                account_id="ext_001", symbol="AAPL",
                quantity=Decimal("130"), price=Decimal("155.00"),
                market_value=Decimal("20150.00"), currency="USD",
                cost_basis=Decimal("142.00"),
            )
        ]

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2,
            provider_holdings=provider_holdings,
        )

        # Activity lot uses activity price, not provider cost basis
        activity_lot = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="activity",
        ).first()
        assert activity_lot is not None
        assert activity_lot.cost_basis_per_unit == Decimal("148.00")

    def test_no_provider_falls_back_to_snapshot_price(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Without provider cost basis, uses snapshot price for inferred lots."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("130"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        inferred_lot = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="inferred",
        ).first()
        assert inferred_lot is not None
        assert inferred_lot.cost_basis_per_unit == Decimal("155.00")

    def test_provider_cost_basis_for_initial_seed(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Initial seed uses provider cost basis when available."""
        from integrations.provider_protocol import ProviderHolding

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("155.00")},
        ])

        provider_holdings = [
            ProviderHolding(
                account_id="ext_001", symbol="AAPL",
                quantity=Decimal("100"), price=Decimal("155.00"),
                market_value=Decimal("15500.00"), currency="USD",
                cost_basis=Decimal("120.00"),
            )
        ]

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2,
            provider_holdings=provider_holdings,
        )

        initial_lot = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="initial",
        ).first()
        assert initial_lot is not None
        assert initial_lot.cost_basis_per_unit == Decimal("120.00")


# --- TestCaseInsensitiveTicker ---


class TestCaseInsensitiveTicker:
    """Tests for case-insensitive ticker matching with activities."""

    def test_case_insensitive_activity_matching(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Activity ticker matching is case-insensitive."""
        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [])

        # Activity with lowercase ticker
        activity = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_005",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="aapl",  # lowercase
            units=Decimal("50"),
            price=Decimal("145.00"),
            amount=Decimal("-7250.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("50"), "snapshot_price": Decimal("150.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id, security_id=recon_security.id
        ).all()
        assert len(lots) == 1
        assert lots[0].source == "activity"


# --- TestMultipleBuyActivities ---


class TestMultipleBuyActivities:
    """Tests for matching multiple buy activities to a single delta."""

    def test_multiple_buys_matched_in_order(
        self, db: Session, recon_account: Account, recon_security: Security
    ):
        """Multiple buy activities are matched in chronological order."""
        lot = HoldingLot(
            account_id=recon_account.id,
            security_id=recon_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("100"),
            current_quantity=Decimal("100"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        ss1 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 1), time(12, 0), tzinfo=timezone.utc)
        )
        snap1 = _make_snapshot(db, recon_account, ss1, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("100"), "snapshot_price": Decimal("150.00")},
        ])

        # Two buy activities (both after the previous snapshot timestamp)
        act1 = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_010",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(14, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("20"),
            price=Decimal("148.00"),
            amount=Decimal("-2960.00"),
            currency="USD",
        )
        act2 = Activity(
            account_id=recon_account.id,
            provider_name="SnapTrade",
            external_id="buy_011",
            activity_date=datetime.combine(
                date(2025, 1, 1), time(16, 0), tzinfo=timezone.utc
            ),
            type="buy",
            ticker="AAPL",
            units=Decimal("15"),
            price=Decimal("149.00"),
            amount=Decimal("-2235.00"),
            currency="USD",
        )
        db.add_all([act1, act2])
        db.flush()

        ss2 = _make_sync_session(
            db, datetime.combine(date(2025, 1, 2), time(12, 0), tzinfo=timezone.utc)
        )
        snap2 = _make_snapshot(db, recon_account, ss2, [
            {"security_id": recon_security.id, "ticker": "AAPL",
             "quantity": Decimal("135"), "snapshot_price": Decimal("155.00")},
        ])

        LotReconciliationService.reconcile_account(
            db, recon_account, snap1, snap2, ss2
        )

        activity_lots = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="activity",
        ).order_by(HoldingLot.acquisition_date.asc()).all()

        assert len(activity_lots) == 2
        assert activity_lots[0].original_quantity == Decimal("20")
        assert activity_lots[0].cost_basis_per_unit == Decimal("148.00")
        assert activity_lots[1].original_quantity == Decimal("15")
        assert activity_lots[1].cost_basis_per_unit == Decimal("149.00")

        # No inferred lot (activities cover full delta of 35)
        inferred = db.query(HoldingLot).filter_by(
            account_id=recon_account.id,
            security_id=recon_security.id,
            source="inferred",
        ).all()
        assert len(inferred) == 0
