"""Integration tests for lot reconciliation during sync.

End-to-end tests using MockProviderRegistry + MockSnapTradeClient to verify
that the sync pipeline correctly creates and disposes lots.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from integrations.provider_protocol import ProviderHolding
from integrations.snaptrade_client import SnapTradeAccount, SnapTradeHolding
from models import Account, HoldingLot, LotDisposal, Security
from services.sync_service import SyncService
from tests.fixtures.mocks import MockProviderRegistry, MockSnapTradeClient


# --- Fixtures ---


@pytest.fixture
def sync_accounts():
    """Sample accounts for sync tests."""
    return [
        SnapTradeAccount(
            id="st_lot_001",
            name="Lot Test Brokerage",
            brokerage_name="Test Broker",
            account_number="LOT001",
        ),
    ]


@pytest.fixture
def sync_holdings_v1():
    """Initial holdings (first sync)."""
    return [
        SnapTradeHolding(
            account_id="st_lot_001",
            symbol="AAPL",
            quantity=100.0,
            price=150.0,
            market_value=15000.0,
            currency="USD",
        ),
        SnapTradeHolding(
            account_id="st_lot_001",
            symbol="GOOG",
            quantity=50.0,
            price=2800.0,
            market_value=140000.0,
            currency="USD",
        ),
    ]


@pytest.fixture
def sync_holdings_v2():
    """Updated holdings (second sync - AAPL increased, GOOG same)."""
    return [
        SnapTradeHolding(
            account_id="st_lot_001",
            symbol="AAPL",
            quantity=130.0,
            price=155.0,
            market_value=20150.0,
            currency="USD",
        ),
        SnapTradeHolding(
            account_id="st_lot_001",
            symbol="GOOG",
            quantity=50.0,
            price=2850.0,
            market_value=142500.0,
            currency="USD",
        ),
    ]


@pytest.fixture
def sync_holdings_v3():
    """Updated holdings (third sync - AAPL decreased, GOOG gone)."""
    return [
        SnapTradeHolding(
            account_id="st_lot_001",
            symbol="AAPL",
            quantity=100.0,
            price=160.0,
            market_value=16000.0,
            currency="USD",
        ),
    ]


# --- TestSyncCreatesLots ---


class TestSyncCreatesLots:
    """Tests that the sync pipeline creates lots via reconciliation."""

    def test_first_sync_creates_initial_lots(
        self, db: Session, sync_accounts, sync_holdings_v1
    ):
        """First sync creates initial lots for all holdings."""
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)

        session = service.trigger_sync(db)
        assert session.is_complete is True

        # Verify accounts were created
        account = db.query(Account).filter_by(external_id="st_lot_001").first()
        assert account is not None

        # Verify initial lots were created
        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 2

        aapl_lots = [lt for lt in lots if lt.ticker == "AAPL"]
        goog_lots = [lt for lt in lots if lt.ticker == "GOOG"]
        assert len(aapl_lots) == 1
        assert len(goog_lots) == 1

        assert aapl_lots[0].source == "initial"
        assert aapl_lots[0].original_quantity == Decimal("100")
        assert aapl_lots[0].current_quantity == Decimal("100")

        assert goog_lots[0].source == "initial"
        assert goog_lots[0].original_quantity == Decimal("50")

    def test_second_sync_creates_inferred_lots_for_increase(
        self, db: Session, sync_accounts, sync_holdings_v1, sync_holdings_v2
    ):
        """Second sync creates inferred lots for quantity increases."""
        # First sync
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)
        service.trigger_sync(db)

        # Second sync with increased AAPL
        client._holdings = sync_holdings_v2
        service.trigger_sync(db)

        account = db.query(Account).filter_by(external_id="st_lot_001").first()
        aapl_security = db.query(Security).filter_by(ticker="AAPL").first()

        aapl_lots = (
            db.query(HoldingLot)
            .filter_by(account_id=account.id, security_id=aapl_security.id)
            .order_by(HoldingLot.source.asc())
            .all()
        )

        assert len(aapl_lots) == 2
        initial = [lt for lt in aapl_lots if lt.source == "initial"][0]
        inferred = [lt for lt in aapl_lots if lt.source == "inferred"][0]

        assert initial.original_quantity == Decimal("100")
        assert inferred.original_quantity == Decimal("30")  # 130 - 100

    def test_third_sync_with_sell_creates_fifo_disposal(
        self, db: Session, sync_accounts, sync_holdings_v1,
        sync_holdings_v2, sync_holdings_v3
    ):
        """Third sync with quantity decrease creates FIFO disposals."""
        # First sync
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)
        service.trigger_sync(db)

        # Second sync (AAPL +30)
        client._holdings = sync_holdings_v2
        service.trigger_sync(db)

        # Third sync (AAPL -30, GOOG gone)
        client._holdings = sync_holdings_v3
        service.trigger_sync(db)

        account = db.query(Account).filter_by(external_id="st_lot_001").first()
        aapl_security = db.query(Security).filter_by(ticker="AAPL").first()
        goog_security = db.query(Security).filter_by(ticker="GOOG").first()

        # AAPL: 100 (initial) + 30 (inferred) → sell 30 → FIFO from inferred first?
        # Actually FIFO is by acquisition_date ASC NULLS FIRST.
        # Both initial and inferred have None acquisition_date, so by created_at.
        # The initial lot was created first, so it's disposed first.
        aapl_lots = (
            db.query(HoldingLot)
            .filter_by(account_id=account.id, security_id=aapl_security.id)
            .order_by(HoldingLot.created_at.asc())
            .all()
        )

        # Check total remaining = 100
        total_remaining = sum(lt.current_quantity for lt in aapl_lots)
        assert total_remaining == Decimal("100")

        # GOOG: fully disposed
        goog_lots = (
            db.query(HoldingLot)
            .filter_by(account_id=account.id, security_id=goog_security.id)
            .all()
        )
        assert len(goog_lots) == 1
        assert goog_lots[0].is_closed is True
        assert goog_lots[0].current_quantity == Decimal("0")

        # GOOG disposal should exist
        goog_disposals = db.query(LotDisposal).filter_by(
            account_id=account.id, security_id=goog_security.id
        ).all()
        assert len(goog_disposals) == 1
        assert goog_disposals[0].quantity == Decimal("50")

    def test_activity_sourced_lot_via_sync(
        self, db: Session, sync_accounts, sync_holdings_v1, sync_holdings_v2
    ):
        """Buy activity between syncs creates activity-sourced lot.

        We insert the Activity record directly between syncs (simulating
        provider activity sync) so the reconciliation engine can find it
        in the timestamp window.
        """
        from models.activity import Activity

        # First sync (no activities)
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)
        service.trigger_sync(db)

        account = db.query(Account).filter_by(external_id="st_lot_001").first()

        # Insert activity directly with a date between the two sync timestamps.
        # The activity_date must be > first sync timestamp and <= second sync
        # timestamp. We use datetime.now() which will be after the first sync.
        activity = Activity(
            account_id=account.id,
            provider_name="SnapTrade",
            external_id="buy_sync_001",
            activity_date=datetime.now(timezone.utc),
            type="buy",
            ticker="AAPL",
            units=Decimal("30"),
            price=Decimal("148.00"),
            amount=Decimal("-4440.00"),
            currency="USD",
        )
        db.add(activity)
        db.flush()

        # Second sync with increased AAPL (no provider activities needed — already in DB)
        client._holdings = sync_holdings_v2
        service.trigger_sync(db)

        aapl_security = db.query(Security).filter_by(ticker="AAPL").first()

        activity_lots = (
            db.query(HoldingLot)
            .filter_by(
                account_id=account.id,
                security_id=aapl_security.id,
                source="activity",
            )
            .all()
        )

        assert len(activity_lots) == 1
        assert activity_lots[0].original_quantity == Decimal("30")
        assert activity_lots[0].cost_basis_per_unit == Decimal("148.00")
        assert activity_lots[0].activity_id == activity.id


# --- TestReconciliationDoesNotBlockSync ---


class TestReconciliationDoesNotBlockSync:
    """Tests that reconciliation failures don't block the sync pipeline."""

    def test_reconciliation_failure_does_not_block_sync(
        self, db: Session, sync_accounts, sync_holdings_v1
    ):
        """If reconciliation raises, sync still completes and holdings are synced."""
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)

        with patch(
            "services.sync_service.LotReconciliationService.reconcile_account",
            side_effect=RuntimeError("Reconciliation exploded"),
        ):
            session = service.trigger_sync(db)

        # Sync should still complete
        assert session.is_complete is True

        # Account should be synced
        account = db.query(Account).filter_by(external_id="st_lot_001").first()
        assert account is not None
        assert account.last_sync_status == "success"

        # Holdings should exist (sync wasn't blocked)
        from models import Holding, AccountSnapshot
        snap = (
            db.query(AccountSnapshot)
            .filter_by(
                account_id=account.id,
                sync_session_id=session.id,
            )
            .first()
        )
        assert snap is not None
        holdings = db.query(Holding).filter_by(account_snapshot_id=snap.id).all()
        assert len(holdings) == 2

        # No lots should exist (reconciliation failed)
        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 0


# --- TestFirstSyncInitialLots ---


class TestFirstSyncInitialLots:
    """Tests specifically for first-sync initial lot behavior."""

    def test_first_sync_with_multiple_holdings(
        self, db: Session, sync_accounts, sync_holdings_v1
    ):
        """First sync creates initial lots for all holdings."""
        client = MockSnapTradeClient(
            accounts=sync_accounts,
            holdings=sync_holdings_v1,
        )
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)

        session = service.trigger_sync(db)
        assert session.is_complete is True

        account = db.query(Account).filter_by(external_id="st_lot_001").first()
        lots = (
            db.query(HoldingLot)
            .filter_by(account_id=account.id, is_closed=False)
            .all()
        )

        assert len(lots) == 2
        for lot in lots:
            assert lot.source == "initial"
            assert lot.acquisition_date is None
            assert lot.is_closed is False

        tickers = sorted([lt.ticker for lt in lots])
        assert tickers == ["AAPL", "GOOG"]

    def test_first_sync_with_provider_cost_basis(
        self, db: Session
    ):
        """First sync uses provider cost basis for initial lots when available."""
        accounts = [
            SnapTradeAccount(
                id="st_cb_001",
                name="Cost Basis Account",
                brokerage_name="Test Broker",
                account_number="CB001",
            ),
        ]

        # Use ProviderHolding directly with cost_basis
        holdings = [
            ProviderHolding(
                account_id="st_cb_001",
                symbol="MSFT",
                quantity=Decimal("50"),
                price=Decimal("400.00"),
                market_value=Decimal("20000.00"),
                currency="USD",
                cost_basis=Decimal("350.00"),
            ),
        ]

        # Create a mock client that returns ProviderHoldings with cost_basis
        client = MockSnapTradeClient(accounts=accounts, holdings=[])

        # Override sync_all to return holdings with cost_basis
        original_sync_all = client.sync_all

        def custom_sync_all():
            result = original_sync_all()
            result.holdings = holdings
            return result

        client.sync_all = custom_sync_all

        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)

        session = service.trigger_sync(db)
        assert session.is_complete is True

        account = db.query(Account).filter_by(external_id="st_cb_001").first()
        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()

        assert len(lots) == 1
        assert lots[0].cost_basis_per_unit == Decimal("350.00")
        assert lots[0].source == "initial"

    def test_empty_portfolio_sync_creates_no_lots(self, db: Session):
        """Sync with no holdings creates no lots."""
        accounts = [
            SnapTradeAccount(
                id="st_empty_001",
                name="Empty Account",
                brokerage_name="Test Broker",
                account_number="EMPTY001",
            ),
        ]

        client = MockSnapTradeClient(accounts=accounts, holdings=[])
        registry = MockProviderRegistry({"SnapTrade": client})
        service = SyncService(provider_registry=registry)

        session = service.trigger_sync(db)
        assert session.is_complete is True

        account = db.query(Account).filter_by(external_id="st_empty_001").first()
        lots = db.query(HoldingLot).filter_by(account_id=account.id).all()
        assert len(lots) == 0
