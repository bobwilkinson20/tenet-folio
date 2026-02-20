"""Unit tests for PortfolioService."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import (
    Account,
    AccountSnapshot,
    AssetClass,
    DailyHoldingValue,
    Holding,
    Security,
    SyncSession,
)
from services.portfolio_service import PortfolioService, STALE_THRESHOLD_DAYS
from tests.fixtures import create_sync_session_with_holdings, get_or_create_security
from utils.ticker import ZERO_BALANCE_TICKER


def _create_account(db: Session, name: str, **kwargs) -> Account:
    acc = Account(
        provider_name=kwargs.get("provider_name", "SnapTrade"),
        external_id=kwargs.get("external_id", f"ext_{name}"),
        name=name,
        is_active=kwargs.get("is_active", True),
        include_in_allocation=kwargs.get("include_in_allocation", True),
    )
    if "assigned_asset_class" in kwargs:
        acc.assigned_asset_class = kwargs["assigned_asset_class"]
    db.add(acc)
    db.flush()
    return acc



def _create_daily_values(
    db: Session,
    account: Account,
    snap: SyncSession,
    val_date: date,
    holdings_data: list[tuple[str, Decimal]],
):
    """Create DailyHoldingValue rows for an account."""
    acct_snap = (
        db.query(AccountSnapshot)
        .filter(
            AccountSnapshot.account_id == account.id,
            AccountSnapshot.sync_session_id == snap.id,
        )
        .first()
    )
    if acct_snap is None:
        acct_snap = AccountSnapshot(
            account_id=account.id,
            sync_session_id=snap.id,
            status="success",
            total_value=sum(mv for _, mv in holdings_data),
        )
        db.add(acct_snap)
        db.flush()

    for ticker, market_value in holdings_data:
        security = get_or_create_security(db, ticker)
        db.add(
            DailyHoldingValue(
                valuation_date=val_date,
                account_id=account.id,
                account_snapshot_id=acct_snap.id,
                security_id=security.id,
                ticker=ticker,
                quantity=Decimal("1"),
                close_price=market_value,
                market_value=market_value,
            )
        )
    db.flush()


class TestPortfolioServiceSummary:
    """Tests for PortfolioService.get_portfolio_summary()."""

    def test_returns_daily_valuation_data(self, db: Session):
        """Always returns data from DailyHoldingValue."""
        service = PortfolioService()
        acct = _create_account(db, "TestAcct")

        create_sync_session_with_holdings(
            db,
            acct,
            datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )
        db.commit()

        result = service.get_portfolio_summary(db)
        assert acct.id in result
        assert result[acct.id].source == "daily_valuation"
        assert result[acct.id].total_value == Decimal("5000")
        assert len(result[acct.id].holdings) == 1
        assert result[acct.id].holdings[0].ticker == "AAPL"

    def test_uses_latest_daily_date(self, db: Session):
        """When multiple daily dates exist, uses the most recent."""
        service = PortfolioService()
        acct = _create_account(db, "TestAcct")

        snap = create_sync_session_with_holdings(
            db,
            acct,
            datetime(2025, 1, 7, tzinfo=timezone.utc),
            [("AAPL", Decimal("4800"))],
        )

        # Add a newer daily valuation
        _create_daily_values(
            db, acct, snap, date(2025, 1, 9), [("AAPL", Decimal("5100"))]
        )
        db.commit()

        result = service.get_portfolio_summary(db)
        assert acct.id in result
        assert result[acct.id].source == "daily_valuation"
        assert result[acct.id].total_value == Decimal("5100")

    def test_no_data_returns_empty(self, db: Session):
        """When neither exists, returns empty dict."""
        service = PortfolioService()
        _create_account(db, "TestAcct")
        db.commit()

        result = service.get_portfolio_summary(db)
        assert result == {}

    def test_account_ids_filter(self, db: Session):
        """Only returns requested accounts."""
        service = PortfolioService()
        acct_a = _create_account(db, "AcctA", external_id="ext_a")
        acct_b = _create_account(db, "AcctB", external_id="ext_b")

        create_sync_session_with_holdings(
            db, acct_a, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )
        create_sync_session_with_holdings(
            db, acct_b, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("GOOG", Decimal("3000"))],
        )
        db.commit()

        result = service.get_portfolio_summary(db, account_ids=[acct_a.id])
        assert acct_a.id in result
        assert acct_b.id not in result

    def test_allocation_only_filter(self, db: Session):
        """allocation_only=True excludes non-allocation accounts."""
        service = PortfolioService()
        included = _create_account(
            db, "Included", external_id="ext_incl", include_in_allocation=True
        )
        excluded = _create_account(
            db, "Excluded", external_id="ext_excl", include_in_allocation=False
        )

        create_sync_session_with_holdings(
            db, included, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )
        create_sync_session_with_holdings(
            db, excluded, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("GOOG", Decimal("3000"))],
        )
        db.commit()

        result = service.get_portfolio_summary(db, allocation_only=True)
        assert included.id in result
        assert excluded.id not in result

    def test_total_value_from_daily(self, db: Session):
        """Uses SUM(market_value) for daily-sourced data."""
        service = PortfolioService()
        acct = _create_account(db, "TestAcct")

        snap = SyncSession(
            timestamp=datetime(2025, 1, 5, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()

        _create_daily_values(
            db, acct, snap, date(2025, 1, 10),
            [("AAPL", Decimal("5000")), ("GOOG", Decimal("3000"))],
        )
        db.commit()

        result = service.get_portfolio_summary(db)
        assert result[acct.id].total_value == Decimal("8000")

    def test_multiple_accounts(self, db: Session):
        """Multiple accounts all sourced from daily valuation."""
        service = PortfolioService()
        acct_a = _create_account(db, "AcctA", external_id="ext_a")
        acct_b = _create_account(db, "AcctB", external_id="ext_b")

        create_sync_session_with_holdings(
            db, acct_a, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )
        create_sync_session_with_holdings(
            db, acct_b, datetime(2025, 1, 8, tzinfo=timezone.utc),
            [("GOOG", Decimal("3000"))],
        )
        db.commit()

        result = service.get_portfolio_summary(db)
        assert result[acct_a.id].source == "daily_valuation"
        assert result[acct_b.id].source == "daily_valuation"
        assert result[acct_a.id].total_value == Decimal("5000")
        assert result[acct_b.id].total_value == Decimal("3000")

    def test_mixed_dhv_dates_uses_per_account_latest(self, db: Session):
        """Each account uses its own latest DHV date independently.

        Account A has latest DHV = today, Account B has latest = yesterday.
        get_portfolio_summary should return both accounts with correct
        per-account values and correct as_of dates.
        """
        service = PortfolioService()
        now = datetime.now(timezone.utc)
        today = now.date()
        yesterday = today - timedelta(days=1)

        acct_a = _create_account(db, "AcctA", external_id="ext_a_mixed")
        acct_b = _create_account(db, "AcctB", external_id="ext_b_mixed")

        # Account A: synced today
        create_sync_session_with_holdings(
            db,
            acct_a,
            now,
            [("AAPL", Decimal("5000"))],
        )

        # Account B: synced yesterday (stale)
        create_sync_session_with_holdings(
            db,
            acct_b,
            now - timedelta(days=1),
            [("GOOG", Decimal("3000"))],
        )

        db.commit()

        result = service.get_portfolio_summary(db)

        # Both accounts should be present
        assert acct_a.id in result
        assert acct_b.id in result

        # Correct per-account values
        assert result[acct_a.id].total_value == Decimal("5000")
        assert result[acct_b.id].total_value == Decimal("3000")

        # Correct per-account as_of dates
        assert result[acct_a.id].as_of == today
        assert result[acct_b.id].as_of == yesterday

        # Both use daily_valuation source
        assert result[acct_a.id].source == "daily_valuation"
        assert result[acct_b.id].source == "daily_valuation"

    def test_zero_dhv_account_excluded_from_summary(self, db: Session):
        """Account with snapshots but no DHV rows is absent from summary.

        Account A has DHV data, Account B has an AccountSnapshot but zero
        DHV rows. get_portfolio_summary should return only Account A;
        Account B should not appear (the dashboard layer handles defaulting
        it to $0).
        """
        service = PortfolioService()

        acct_a = _create_account(db, "AcctA", external_id="ext_a_zero")
        acct_b = _create_account(db, "AcctB", external_id="ext_b_zero")

        # Account A: normal sync with DHV
        create_sync_session_with_holdings(
            db,
            acct_a,
            datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )

        # Account B: snapshot exists but no holdings/DHV
        snap = SyncSession(
            timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()
        db.add(AccountSnapshot(
            account_id=acct_b.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("0"),
        ))

        db.commit()

        result = service.get_portfolio_summary(db)

        # Only Account A should be in the result
        assert acct_a.id in result
        assert acct_b.id not in result
        assert result[acct_a.id].total_value == Decimal("5000")

    def test_holdings_without_dhv_excluded_from_summary(self, db: Session):
        """Account with snapshot+holdings but no DHV rows is absent from summary.

        This is an unexpected state (holdings exist in the snapshot but
        valuation never ran), verifying that the service handles it
        gracefully. Only DHV data drives the portfolio summary.
        """
        service = PortfolioService()
        acct = _create_account(db, "HoldingsOnly", external_id="ext_hold_only")

        snap = SyncSession(
            timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000"),
        )
        db.add(acct_snap)
        db.flush()

        sec = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))
        # No DailyHoldingValue rows created

        db.commit()

        result = service.get_portfolio_summary(db)

        assert acct.id not in result

    def test_mixed_accounts_one_with_dhv_one_without(self, db: Session):
        """One account has DHV, another has holdings but no DHV rows.

        Account A has normal DHV data. Account B has a snapshot with
        holdings but no DHV rows. Only Account A should appear in the
        portfolio summary; Account B is invisible at this layer.
        """
        service = PortfolioService()

        acct_a = _create_account(db, "WithDHV", external_id="ext_with_dhv")
        acct_b = _create_account(db, "NoDHV", external_id="ext_no_dhv")

        # Account A: normal sync (creates snapshot + holdings + DHV)
        create_sync_session_with_holdings(
            db,
            acct_a,
            datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )

        # Account B: snapshot + holdings but no DHV
        snap = SyncSession(
            timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct_b.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("3000"),
        )
        db.add(acct_snap)
        db.flush()

        sec = get_or_create_security(db, "GOOG")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            snapshot_price=Decimal("600"),
            snapshot_value=Decimal("3000"),
        ))
        # No DHV for Account B

        db.commit()

        result = service.get_portfolio_summary(db)

        assert acct_a.id in result
        assert acct_b.id not in result
        assert result[acct_a.id].total_value == Decimal("5000")


class TestGetCurrentHoldings:
    """Tests for PortfolioService.get_current_holdings()."""

    def test_returns_flat_list(self, db: Session):
        """Returns a flat list of holdings across all accounts."""
        service = PortfolioService()
        acct_a = _create_account(db, "AcctA", external_id="ext_a")
        acct_b = _create_account(db, "AcctB", external_id="ext_b")

        create_sync_session_with_holdings(
            db, acct_a, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("5000"))],
        )
        create_sync_session_with_holdings(
            db, acct_b, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("GOOG", Decimal("3000")), ("MSFT", Decimal("2000"))],
        )
        db.commit()

        holdings = service.get_current_holdings(db)
        assert len(holdings) == 3
        tickers = {h.ticker for h in holdings}
        assert tickers == {"AAPL", "GOOG", "MSFT"}

    def test_empty_portfolio(self, db: Session):
        """Returns empty list when no accounts have data."""
        service = PortfolioService()
        _create_account(db, "TestAcct")
        db.commit()

        holdings = service.get_current_holdings(db)
        assert holdings == []


class TestCalculateAllocation:
    """Tests for PortfolioService.calculate_allocation()."""

    @pytest.fixture
    def asset_types(self, db):
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.commit()
        return {"stocks": stocks, "bonds": bonds}

    def test_single_asset_type(self, db: Session, asset_types):
        """All holdings classified under one type."""
        service = PortfolioService()
        acct = _create_account(
            db, "TestAcct", assigned_asset_class=asset_types["stocks"]
        )
        create_sync_session_with_holdings(
            db, acct, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("1500")), ("GOOG", Decimal("500"))],
        )
        db.commit()

        result = service.calculate_allocation(db)

        assert len(result["by_type"]) == 1
        stocks_data = result["by_type"][asset_types["stocks"].id]
        assert stocks_data["value"] == Decimal("2000")
        assert stocks_data["percent"] == Decimal("100.00")
        assert result["unassigned"]["value"] == Decimal("0.00")
        assert result["total"] == Decimal("2000")

    def test_multiple_types(self, db: Session, asset_types):
        """Holdings split across multiple types."""
        service = PortfolioService()
        acct = _create_account(db, "TestAcct")

        sec_stock = Security(ticker="AAPL", manual_asset_class=asset_types["stocks"])
        sec_bond = Security(ticker="BND", manual_asset_class=asset_types["bonds"])
        db.add_all([sec_stock, sec_bond])
        db.flush()

        create_sync_session_with_holdings(
            db, acct, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("600")), ("BND", Decimal("400"))],
        )
        db.commit()

        result = service.calculate_allocation(db)

        assert len(result["by_type"]) == 2
        assert result["total"] == Decimal("1000")
        assert result["by_type"][asset_types["stocks"].id]["value"] == Decimal("600")
        assert result["by_type"][asset_types["bonds"].id]["value"] == Decimal("400")

    def test_unassigned_holdings(self, db: Session, asset_types):
        """Unclassified holdings go to unassigned bucket."""
        service = PortfolioService()
        acct = _create_account(db, "TestAcct")

        sec = Security(ticker="AAPL", manual_asset_class=asset_types["stocks"])
        db.add(sec)
        db.flush()

        create_sync_session_with_holdings(
            db, acct, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("1000")), ("UNKNOWN", Decimal("500"))],
        )
        db.commit()

        result = service.calculate_allocation(db)

        assert result["unassigned"]["value"] == Decimal("500")
        assert result["total"] == Decimal("1500")

    def test_allocation_only_filter(self, db: Session, asset_types):
        """allocation_only excludes non-allocation accounts."""
        service = PortfolioService()
        included = _create_account(
            db, "Included", external_id="ext_incl",
            include_in_allocation=True,
            assigned_asset_class=asset_types["stocks"],
        )
        excluded = _create_account(
            db, "Excluded", external_id="ext_excl",
            include_in_allocation=False,
            assigned_asset_class=asset_types["bonds"],
        )

        create_sync_session_with_holdings(
            db, included, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("AAPL", Decimal("1000"))],
        )
        create_sync_session_with_holdings(
            db, excluded, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("BND", Decimal("500"))],
        )
        db.commit()

        result = service.calculate_allocation(db, allocation_only=True)

        assert result["total"] == Decimal("1000")
        assert len(result["by_type"]) == 1
        assert asset_types["stocks"].id in result["by_type"]

    def test_empty_portfolio(self, db: Session):
        """Empty portfolio returns zero values."""
        service = PortfolioService()
        _create_account(db, "TestAcct")
        db.commit()

        result = service.calculate_allocation(db)

        assert result["total"] == Decimal("0.00")
        assert result["by_type"] == {}
        assert result["unassigned"]["value"] == Decimal("0.00")

    def test_multi_account_different_sync_sessions(self, db: Session, asset_types):
        """Allocation includes holdings from accounts with different sync sessions."""
        service = PortfolioService()
        acct_a = _create_account(
            db, "AcctA", external_id="ext_a",
            assigned_asset_class=asset_types["stocks"],
        )
        acct_b = _create_account(
            db, "AcctB", external_id="ext_b",
            assigned_asset_class=asset_types["bonds"],
        )

        create_sync_session_with_holdings(
            db, acct_a, datetime(2025, 1, 8, tzinfo=timezone.utc),
            [("VTI", Decimal("2000"))],
        )
        create_sync_session_with_holdings(
            db, acct_b, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("BND", Decimal("1000"))],
        )
        db.commit()

        result = service.calculate_allocation(db)

        assert result["total"] == Decimal("3000")
        assert result["by_type"][asset_types["stocks"].id]["value"] == Decimal("2000")
        assert result["by_type"][asset_types["bonds"].id]["value"] == Decimal("1000")


class TestGetHoldingsForAssetType:
    """Tests for PortfolioService.get_holdings_for_asset_type()."""

    @pytest.fixture
    def asset_types(self, db):
        stocks = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        bonds = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([stocks, bonds])
        db.commit()
        return {"stocks": stocks, "bonds": bonds}

    def test_holdings_for_specific_type(self, db: Session, asset_types):
        """Returns holdings classified under the requested type."""
        service = PortfolioService()
        acct = _create_account(
            db, "Stock Account", assigned_asset_class=asset_types["stocks"]
        )
        create_sync_session_with_holdings(
            db, acct, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("VTI", Decimal("2000"))],
        )
        db.commit()

        result = service.get_holdings_for_asset_type(db, asset_types["stocks"].id)

        assert len(result) == 1
        assert result[0]["ticker"] == "VTI"
        assert result[0]["account_name"] == "Stock Account"
        assert result[0]["market_value"] == Decimal("2000")

    def test_unassigned_type_id(self, db: Session, asset_types):
        """asset_type_id='unassigned' returns unclassified holdings."""
        service = PortfolioService()
        acct = _create_account(db, "My Account")

        create_sync_session_with_holdings(
            db, acct, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("UNKNOWN", Decimal("500"))],
        )
        db.commit()

        result = service.get_holdings_for_asset_type(db, "unassigned")

        assert len(result) == 1
        assert result[0]["ticker"] == "UNKNOWN"

    def test_excludes_non_allocation_accounts(self, db: Session, asset_types):
        """allocation_only excludes non-allocation accounts."""
        service = PortfolioService()
        included = _create_account(
            db, "Included", external_id="ext_incl",
            include_in_allocation=True,
            assigned_asset_class=asset_types["stocks"],
        )
        excluded = _create_account(
            db, "Excluded", external_id="ext_excl",
            include_in_allocation=False,
            assigned_asset_class=asset_types["stocks"],
        )

        create_sync_session_with_holdings(
            db, included, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("VTI", Decimal("2000"))],
        )
        create_sync_session_with_holdings(
            db, excluded, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("VOO", Decimal("1000"))],
        )
        db.commit()

        result = service.get_holdings_for_asset_type(
            db, asset_types["stocks"].id, allocation_only=True
        )

        assert len(result) == 1
        assert result[0]["account_name"] == "Included"

    def test_empty_portfolio(self, db: Session):
        """Returns empty list when no accounts have data."""
        service = PortfolioService()
        _create_account(db, "TestAcct")
        db.commit()

        result = service.get_holdings_for_asset_type(db, "unassigned")
        assert result == []

    def test_multi_account_with_different_sync_sessions(self, db: Session, asset_types):
        """Holdings from multiple accounts with different sync sessions."""
        service = PortfolioService()
        acct_a = _create_account(
            db, "Account A", external_id="ext_a",
            assigned_asset_class=asset_types["stocks"],
        )
        acct_b = _create_account(
            db, "Account B", external_id="ext_b",
            assigned_asset_class=asset_types["stocks"],
        )

        create_sync_session_with_holdings(
            db, acct_a, datetime(2025, 1, 8, tzinfo=timezone.utc),
            [("VTI", Decimal("2000"))],
        )
        create_sync_session_with_holdings(
            db, acct_b, datetime(2025, 1, 10, tzinfo=timezone.utc),
            [("VOO", Decimal("1000"))],
        )
        db.commit()

        result = service.get_holdings_for_asset_type(db, asset_types["stocks"].id)

        assert len(result) == 2
        tickers = {r["ticker"] for r in result}
        assert tickers == {"VTI", "VOO"}


class TestGetValuationStatus:
    """Tests for PortfolioService.get_valuation_status()."""

    def test_ok_status_all_dhv_present(self, db: Session):
        """Status is 'ok' when all non-cash holdings have DHV rows."""
        service = PortfolioService()
        acct = _create_account(db, "OkAcct")
        now = datetime.now(timezone.utc)

        create_sync_session_with_holdings(
            db, acct, now,
            [("AAPL", Decimal("5000")), ("GOOG", Decimal("3000"))],
        )
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "ok"

    def test_missing_status_no_dhv(self, db: Session):
        """Status is 'missing' when account has snapshot+holdings but no DHV."""
        service = PortfolioService()
        acct = _create_account(db, "MissingAcct")

        snap = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000"),
        )
        db.add(acct_snap)
        db.flush()

        sec = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "missing"
        assert result[acct.id].valuation_date is None

    def test_stale_status_old_dhv(self, db: Session):
        """Status is 'stale' when valuation date is older than threshold."""
        service = PortfolioService()
        acct = _create_account(db, "StaleAcct")

        # Use a large gap to avoid timezone edge cases
        old_ts = datetime.now(timezone.utc) - timedelta(days=STALE_THRESHOLD_DAYS + 2)
        create_sync_session_with_holdings(
            db, acct, old_ts,
            [("AAPL", Decimal("5000"))],
        )
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "stale"

    def test_partial_status_fewer_dhv_than_holdings(self, db: Session):
        """Status is 'partial' when some non-cash holdings are missing DHV."""
        service = PortfolioService()
        acct = _create_account(db, "PartialAcct")
        now = datetime.now(timezone.utc)
        today = now.date()

        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("8000"),
        )
        db.add(acct_snap)
        db.flush()

        # Two non-cash holdings in the snapshot
        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_goog.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            snapshot_price=Decimal("600"),
            snapshot_value=Decimal("3000"),
        ))

        # Only one DHV row (AAPL) — GOOG is missing
        db.add(DailyHoldingValue(
            valuation_date=today,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("500"),
            market_value=Decimal("5000"),
        ))
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "partial"

    def test_ok_zero_balance_sentinel(self, db: Session):
        """Account with 0 holdings and _ZERO_BALANCE DHV → 'ok'."""
        service = PortfolioService()
        acct = _create_account(db, "ZeroAcct")
        now = datetime.now(timezone.utc)
        today = now.date()

        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("0"),
        )
        db.add(acct_snap)
        db.flush()

        # No holdings, but _ZERO_BALANCE sentinel DHV
        sec = get_or_create_security(db, ZERO_BALANCE_TICKER, name="Zero Balance Sentinel")
        db.add(DailyHoldingValue(
            valuation_date=today,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec.id,
            ticker=ZERO_BALANCE_TICKER,
            quantity=Decimal("0"),
            close_price=Decimal("0"),
            market_value=Decimal("0"),
        ))
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "ok"

    def test_missing_when_only_sentinel_dhv_with_real_holdings(self, db: Session):
        """Holdings + only _ZERO_BALANCE DHV → 'missing', not 'partial'.

        If a stale sentinel exists but the account now has real holdings,
        zero real DHV rows means the account has no valuation data.
        """
        service = PortfolioService()
        acct = _create_account(db, "SentinelAcct")
        now = datetime.now(timezone.utc)
        today = now.date()

        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000"),
        )
        db.add(acct_snap)
        db.flush()

        # Real holding in the snapshot
        sec_aapl = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))

        # Only a _ZERO_BALANCE sentinel DHV (stale from prior snapshot)
        sec_zb = get_or_create_security(db, ZERO_BALANCE_TICKER, name="Zero Balance Sentinel")
        db.add(DailyHoldingValue(
            valuation_date=today,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_zb.id,
            ticker=ZERO_BALANCE_TICKER,
            quantity=Decimal("0"),
            close_price=Decimal("0"),
            market_value=Decimal("0"),
        ))
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "missing"

    def test_cash_only_account_with_dhv_ok(self, db: Session):
        """Cash-only account with matching DHV → 'ok'."""
        service = PortfolioService()
        acct = _create_account(db, "CashAcct")
        now = datetime.now(timezone.utc)

        create_sync_session_with_holdings(
            db, acct, now, [("USD", Decimal("10000"))],
        )
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "ok"

    def test_cash_holding_missing_dhv(self, db: Session):
        """Cash holding without DHV row → 'missing' (DHV expected for all holdings)."""
        service = PortfolioService()
        acct = _create_account(db, "CashNoDhv")
        now = datetime.now(timezone.utc)

        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("10000"),
        )
        db.add(acct_snap)
        db.flush()

        sec_usd = get_or_create_security(db, "USD")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_usd.id,
            ticker="USD",
            quantity=Decimal("10000"),
            snapshot_price=Decimal("1"),
            snapshot_value=Decimal("10000"),
        ))
        # No DHV rows
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        assert result[acct.id].status == "missing"

    def test_partial_includes_cash_in_counts(self, db: Session):
        """Cash holdings count toward the holding/DHV comparison."""
        service = PortfolioService()
        acct = _create_account(db, "CashPartialAcct")
        now = datetime.now(timezone.utc)
        today = now.date()

        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("6000"),
        )
        db.add(acct_snap)
        db.flush()

        # One cash + one non-cash holding
        sec_usd = get_or_create_security(db, "USD")
        sec_aapl = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_usd.id,
            ticker="USD",
            quantity=Decimal("1000"),
            snapshot_price=Decimal("1"),
            snapshot_value=Decimal("1000"),
        ))
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))

        # Only AAPL has DHV — USD cash holding is missing DHV
        db.add(DailyHoldingValue(
            valuation_date=today,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("500"),
            market_value=Decimal("5000"),
        ))
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id in result
        # 2 holdings, 1 DHV → partial (cash IS counted)
        assert result[acct.id].status == "partial"

    def test_never_synced_account_excluded(self, db: Session):
        """Account with no AccountSnapshot at all is excluded from results."""
        service = PortfolioService()
        acct = _create_account(db, "NeverSynced")
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert acct.id not in result

    def test_mixed_statuses_multiple_accounts(self, db: Session):
        """Multiple accounts return independent statuses."""
        service = PortfolioService()
        now = datetime.now(timezone.utc)

        # Account A: ok (has DHV matching holdings)
        acct_a = _create_account(db, "AcctA", external_id="ext_a_val")
        create_sync_session_with_holdings(
            db, acct_a, now, [("AAPL", Decimal("5000"))],
        )

        # Account B: missing (snapshot + holdings, no DHV)
        acct_b = _create_account(db, "AcctB", external_id="ext_b_val")
        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()
        acct_snap_b = AccountSnapshot(
            account_id=acct_b.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("3000"),
        )
        db.add(acct_snap_b)
        db.flush()
        sec = get_or_create_security(db, "GOOG")
        db.add(Holding(
            account_snapshot_id=acct_snap_b.id,
            security_id=sec.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            snapshot_price=Decimal("600"),
            snapshot_value=Decimal("3000"),
        ))

        db.commit()

        result = service.get_valuation_status(db, [acct_a.id, acct_b.id])
        assert result[acct_a.id].status == "ok"
        assert result[acct_b.id].status == "missing"

    def test_valuation_date_populated(self, db: Session):
        """valuation_date is set to the latest DHV date when DHV exists."""
        service = PortfolioService()
        acct = _create_account(db, "DateAcct")
        now = datetime.now(timezone.utc)
        today = now.date()

        create_sync_session_with_holdings(
            db, acct, now, [("AAPL", Decimal("5000"))],
        )
        db.commit()

        result = service.get_valuation_status(db, [acct.id])
        assert result[acct.id].valuation_date == today
