"""Integration tests for portfolio value history API endpoint."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
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
from tests.fixtures import get_or_create_security


def _create_account(db: Session, name: str = "Test Account", **kwargs) -> Account:
    acc = Account(
        provider_name=kwargs.get("provider_name", "SnapTrade"),
        external_id=kwargs.get("external_id", f"ext_{name}"),
        name=name,
        is_active=True,
    )
    db.add(acc)
    db.flush()
    return acc


def _create_sync_session(db: Session, ts: datetime) -> SyncSession:
    snap = SyncSession(timestamp=ts, is_complete=True)
    db.add(snap)
    db.flush()
    return snap


def _seed_valuation_data(db: Session):
    """Create accounts, sync_sessions, and daily_holding_values for testing.

    Creates:
    - 2 accounts (Vanguard IRA, Schwab Taxable)
    - 3 days of valuation data (Jan 6-8, 2025)
    - AAPL in Vanguard, GOOG in Schwab
    """
    acct1 = _create_account(db, "Vanguard IRA", external_id="ext_vanguard")
    acct2 = _create_account(db, "Schwab Taxable", external_id="ext_schwab")

    snap = _create_sync_session(
        db, datetime(2025, 1, 5, tzinfo=timezone.utc)
    )

    # AccountSnapshots
    acct1_snap = AccountSnapshot(
        account_id=acct1.id,
        sync_session_id=snap.id,
        status="success",
        total_value=Decimal("0"),
    )
    acct2_snap = AccountSnapshot(
        account_id=acct2.id,
        sync_session_id=snap.id,
        status="success",
        total_value=Decimal("0"),
    )
    db.add_all([acct1_snap, acct2_snap])
    db.flush()

    # Create securities
    sec_aapl = get_or_create_security(db, "AAPL")
    sec_goog = get_or_create_security(db, "GOOG")

    # Holdings (for snapshot reference)
    db.add(Holding(
        account_snapshot_id=acct1_snap.id,
        security_id=sec_aapl.id,
        ticker="AAPL", quantity=Decimal("10"), snapshot_price=Decimal("150"),
        snapshot_value=Decimal("1500"),
    ))
    db.add(Holding(
        account_snapshot_id=acct2_snap.id,
        security_id=sec_goog.id,
        ticker="GOOG", quantity=Decimal("5"), snapshot_price=Decimal("2800"),
        snapshot_value=Decimal("14000"),
    ))

    # Daily holding values for 3 days
    for day_offset, aapl_price, goog_price in [
        (0, Decimal("150"), Decimal("2800")),
        (1, Decimal("152"), Decimal("2820")),
        (2, Decimal("155"), Decimal("2850")),
    ]:
        d = date(2025, 1, 6 + day_offset)
        db.add(DailyHoldingValue(
            valuation_date=d,
            account_id=acct1.id,
            account_snapshot_id=acct1_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=aapl_price,
            market_value=Decimal("10") * aapl_price,
        ))
        db.add(DailyHoldingValue(
            valuation_date=d,
            account_id=acct2.id,
            account_snapshot_id=acct2_snap.id,
            security_id=sec_goog.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            close_price=goog_price,
            market_value=Decimal("5") * goog_price,
        ))

    db.commit()
    return acct1, acct2, snap


class TestValueHistoryAPI:
    """Integration tests for GET /api/portfolio/value-history."""

    def test_empty_no_data(self, client: TestClient):
        """Returns empty response when no valuation data exists."""
        response = client.get("/api/portfolio/value-history")
        assert response.status_code == 200
        data = response.json()
        assert data["data_points"] == []

    def test_total_default(self, client: TestClient, db: Session):
        """group_by=total returns daily portfolio totals."""
        _seed_valuation_data(db)

        response = client.get("/api/portfolio/value-history")
        assert response.status_code == 200
        data = response.json()

        assert data["start_date"] == "2025-01-06"
        # end_date extends to today when no explicit end param
        assert data["end_date"] == date.today().isoformat()
        # 3 historical + 1 today live point
        assert len(data["data_points"]) == 4
        assert data["series"] is None

        # Day 1: AAPL 10*150 + GOOG 5*2800 = 1500 + 14000 = 15500
        assert data["data_points"][0]["date"] == "2025-01-06"
        assert Decimal(data["data_points"][0]["value"]) == Decimal("15500.00")

        # Day 3: AAPL 10*155 + GOOG 5*2850 = 1550 + 14250 = 15800
        assert data["data_points"][2]["date"] == "2025-01-08"
        assert Decimal(data["data_points"][2]["value"]) == Decimal("15800.00")

        # Today's live data point is appended
        assert data["data_points"][3]["date"] == date.today().isoformat()

    def test_total_with_date_range(self, client: TestClient, db: Session):
        """Respects start/end query parameters."""
        _seed_valuation_data(db)

        response = client.get(
            "/api/portfolio/value-history?start=2025-01-07&end=2025-01-07"
        )
        assert response.status_code == 200
        data = response.json()

        assert len(data["data_points"]) == 1
        assert data["data_points"][0]["date"] == "2025-01-07"

    def test_group_by_account(self, client: TestClient, db: Session):
        """group_by=account returns per-account series."""
        acct1, acct2, _ = _seed_valuation_data(db)

        response = client.get(
            "/api/portfolio/value-history?group_by=account"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["data_points"] is None
        assert len(data["series"]) == 2

        # Find series by account name
        vanguard_series = data["series"][acct1.id]
        schwab_series = data["series"][acct2.id]

        assert vanguard_series["account_name"] == "Vanguard IRA"
        assert len(vanguard_series["data_points"]) == 3

        assert schwab_series["account_name"] == "Schwab Taxable"
        assert len(schwab_series["data_points"]) == 3

        # Verify values
        assert Decimal(vanguard_series["data_points"][0]["value"]) == Decimal("1500.00")
        assert Decimal(schwab_series["data_points"][0]["value"]) == Decimal("14000.00")

    def test_group_by_asset_class(self, client: TestClient, db: Session):
        """group_by=asset_class returns per-asset-class series."""
        acct1, acct2, _ = _seed_valuation_data(db)

        # Create asset class and assign to securities
        equities = AssetClass(
            name="US Equities",
            color="#3B82F6",
            target_percent=Decimal("100"),
        )
        db.add(equities)
        db.flush()

        # Assign AAPL to equities via security (already created by _seed_valuation_data)
        aapl = db.query(Security).filter_by(ticker="AAPL").first()
        aapl.name = "Apple"
        aapl.manual_asset_class_id = equities.id
        db.commit()

        response = client.get(
            "/api/portfolio/value-history?group_by=asset_class"
        )
        assert response.status_code == 200
        data = response.json()

        assert data["data_points"] is None
        assert len(data["series"]) >= 1

        # AAPL should be in US Equities; GOOG should be unassigned
        has_equities = False
        has_unassigned = False
        for series_data in data["series"].values():
            if series_data.get("asset_class_name") == "US Equities":
                has_equities = True
                assert len(series_data["data_points"]) == 3
            if series_data.get("asset_class_name") == "Unassigned":
                has_unassigned = True

        assert has_equities
        assert has_unassigned

    def test_default_range_uses_full_data(self, client: TestClient, db: Session):
        """No params returns full available date range including today."""
        _seed_valuation_data(db)

        response = client.get("/api/portfolio/value-history")
        data = response.json()

        assert data["start_date"] == "2025-01-06"
        # end_date extends to today when no explicit end param
        assert data["end_date"] == date.today().isoformat()
        # 3 historical + 1 today live point
        assert len(data["data_points"]) == 4

    def test_start_after_end_returns_empty(self, client: TestClient, db: Session):
        """start > end returns empty data_points."""
        _seed_valuation_data(db)

        response = client.get(
            "/api/portfolio/value-history?start=2025-01-09&end=2025-01-06"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data_points"] == []

    def test_out_of_range_returns_empty(self, client: TestClient, db: Session):
        """Date range outside stored data returns empty."""
        _seed_valuation_data(db)

        response = client.get(
            "/api/portfolio/value-history?start=2026-01-01&end=2026-01-31"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data_points"] == []

    def test_today_data_point_appended(self, client: TestClient, db: Session):
        """When end date includes today, a live data point is appended."""
        acct = _create_account(db, "Today Account")
        snap = _create_sync_session(
            db, datetime(2025, 1, 5, tzinfo=timezone.utc)
        )

        # AccountSnapshot for current portfolio lookup
        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000.00"),
        )
        db.add(acct_snap)
        db.flush()

        sec_aapl = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL", quantity=Decimal("10"), snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000.00"),
        ))

        # Historical data point (yesterday)
        yesterday = date.today() - timedelta(days=1)
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("490"),
            market_value=Decimal("4900.00"),
        ))

        db.commit()

        today_str = date.today().isoformat()

        # Request explicitly including today via end param
        response = client.get(
            f"/api/portfolio/value-history?start={yesterday.isoformat()}&end={today_str}"
        )
        assert response.status_code == 200
        data = response.json()

        # Should have yesterday's data point + today's live point
        dates = [dp["date"] for dp in data["data_points"]]
        assert yesterday.isoformat() in dates
        assert today_str in dates

    def test_today_data_point_appended_without_end_param(
        self, client: TestClient, db: Session
    ):
        """Today's live data point is appended even when no end param is given."""
        acct = _create_account(db, "Today Account")
        snap = _create_sync_session(
            db, datetime(2025, 1, 5, tzinfo=timezone.utc)
        )

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000.00"),
        )
        db.add(acct_snap)
        db.flush()

        sec_aapl = get_or_create_security(db, "AAPL")
        db.add(Holding(
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL", quantity=Decimal("10"), snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000.00"),
        ))

        yesterday = date.today() - timedelta(days=1)
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=acct.id,
            account_snapshot_id=acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("490"),
            market_value=Decimal("4900.00"),
        ))

        db.commit()

        # No end param — effective_end should still include today
        response = client.get("/api/portfolio/value-history")
        assert response.status_code == 200
        data = response.json()

        today_str = date.today().isoformat()
        dates = [dp["date"] for dp in data["data_points"]]
        assert yesterday.isoformat() in dates
        assert today_str in dates

    def test_allocation_only_filters_history(
        self, client: TestClient, db: Session
    ):
        """allocation_only=true only includes allocation accounts in history."""
        alloc_acct = _create_account(
            db, "Alloc Account", external_id="ext_alloc"
        )
        alloc_acct.include_in_allocation = True

        non_alloc_acct = _create_account(
            db, "Non-Alloc Account", external_id="ext_nonalloc"
        )
        non_alloc_acct.include_in_allocation = False
        db.flush()

        snap = _create_sync_session(
            db, datetime(2025, 1, 5, tzinfo=timezone.utc)
        )

        alloc_acct_snap = AccountSnapshot(
            account_id=alloc_acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("1500"),
        )
        non_alloc_acct_snap = AccountSnapshot(
            account_id=non_alloc_acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("14000"),
        )
        db.add_all([alloc_acct_snap, non_alloc_acct_snap])
        db.flush()

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")

        # Daily values for both accounts
        d = date(2025, 1, 6)
        db.add(DailyHoldingValue(
            valuation_date=d,
            account_id=alloc_acct.id,
            account_snapshot_id=alloc_acct_snap.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("150"),
            market_value=Decimal("1500"),
        ))
        db.add(DailyHoldingValue(
            valuation_date=d,
            account_id=non_alloc_acct.id,
            account_snapshot_id=non_alloc_acct_snap.id,
            security_id=sec_goog.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            close_price=Decimal("2800"),
            market_value=Decimal("14000"),
        ))

        db.commit()

        # Without filter: total = 1500 + 14000 = 15500
        response = client.get("/api/portfolio/value-history")
        data = response.json()
        assert Decimal(data["data_points"][0]["value"]) == Decimal("15500")

        # With filter: total = 1500 (alloc account only)
        response = client.get(
            "/api/portfolio/value-history?allocation_only=true"
        )
        data = response.json()
        # 1 historical + 1 today live point
        assert Decimal(data["data_points"][0]["value"]) == Decimal("1500")

    def test_today_value_matches_dashboard(
        self, client: TestClient, db: Session
    ):
        """Value-history today data point matches dashboard total_net_worth.

        When accounts are in a mixed-DHV state (Account A has today's DHV,
        Account B only has yesterday's), both endpoints should report the
        same total value for today.
        """
        # Use date.today() for DHV dates because the value-history endpoint
        # uses date.today() internally to determine the live "today" data point.
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Account A: fresh (has DHV for today)
        acc_a = _create_account(db, "Fresh Account", external_id="ext_fresh")
        # Account B: stale (DHV only for yesterday)
        acc_b = _create_account(db, "Stale Account", external_id="ext_stale")

        snap = _create_sync_session(
            db, datetime(2025, 1, 5, tzinfo=timezone.utc)
        )

        snap_a = AccountSnapshot(
            account_id=acc_a.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000"),
        )
        snap_b = AccountSnapshot(
            account_id=acc_b.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("3000"),
        )
        db.add_all([snap_a, snap_b])
        db.flush()

        sec_aapl = get_or_create_security(db, "AAPL")
        sec_goog = get_or_create_security(db, "GOOG")

        # Account A: holdings + DHV for today
        db.add(Holding(
            account_snapshot_id=snap_a.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000"),
        ))
        db.add(DailyHoldingValue(
            valuation_date=today,
            account_id=acc_a.id,
            account_snapshot_id=snap_a.id,
            security_id=sec_aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("500"),
            market_value=Decimal("5000"),
        ))

        # Account B: holdings + DHV for yesterday only
        db.add(Holding(
            account_snapshot_id=snap_b.id,
            security_id=sec_goog.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            snapshot_price=Decimal("600"),
            snapshot_value=Decimal("3000"),
        ))
        db.add(DailyHoldingValue(
            valuation_date=yesterday,
            account_id=acc_b.id,
            account_snapshot_id=snap_b.id,
            security_id=sec_goog.id,
            ticker="GOOG",
            quantity=Decimal("5"),
            close_price=Decimal("600"),
            market_value=Decimal("3000"),
        ))

        db.commit()

        # Get value-history today data point
        vh_response = client.get("/api/portfolio/value-history?group_by=total")
        assert vh_response.status_code == 200
        vh_data = vh_response.json()

        today_str = today.isoformat()
        today_points = [
            dp for dp in vh_data["data_points"] if dp["date"] == today_str
        ]
        assert len(today_points) == 1
        vh_today_value = Decimal(today_points[0]["value"])

        # Get dashboard total_net_worth
        dash_response = client.get("/api/dashboard")
        assert dash_response.status_code == 200
        dash_data = dash_response.json()
        dash_net_worth = Decimal(dash_data["total_net_worth"])

        # Both endpoints must agree on today's total
        assert vh_today_value == dash_net_worth
        # And the total must include both accounts (5000 + 3000)
        assert vh_today_value == Decimal("8000")
