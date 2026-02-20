"""Integration tests for dashboard API endpoint."""

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
from tests.fixtures import create_sync_session_with_holdings, get_or_create_security


def _create_dashboard_test_data(db: Session):
    """Set up accounts, snapshots, holdings, asset classes, and securities.

    Creates:
    - 2 asset classes (US Stocks 60%, Bonds 40%)
    - 2 accounts (Vanguard with include_in_allocation=True, Schwab with False)
    - 1 sync_session with holdings and account snapshots
    - 2 securities (AAPL -> US Stocks, BND -> Bonds)

    Returns:
        Tuple of (vanguard_account, schwab_account, sync_session, us_stocks, bonds)
    """
    us_stocks = AssetClass(
        name="US Stocks", color="#3B82F6", target_percent=Decimal("60.00")
    )
    bonds = AssetClass(
        name="Bonds", color="#10B981", target_percent=Decimal("40.00")
    )
    db.add_all([us_stocks, bonds])
    db.flush()

    vanguard = Account(
        provider_name="SnapTrade",
        external_id="ext_vanguard",
        name="Vanguard IRA",
        is_active=True,
        include_in_allocation=True,
    )
    schwab = Account(
        provider_name="SnapTrade",
        external_id="ext_schwab",
        name="Schwab Taxable",
        is_active=True,
        include_in_allocation=False,
    )
    db.add_all([vanguard, schwab])
    db.flush()

    snap = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
    db.add(snap)
    db.flush()

    # Account snapshots
    vanguard_acct_snap = AccountSnapshot(
        account_id=vanguard.id,
        sync_session_id=snap.id,
        status="success",
        total_value=Decimal("8000.00"),
    )
    schwab_acct_snap = AccountSnapshot(
        account_id=schwab.id,
        sync_session_id=snap.id,
        status="success",
        total_value=Decimal("2000.00"),
    )
    db.add_all([vanguard_acct_snap, schwab_acct_snap])
    db.flush()

    # Securities
    aapl = Security(ticker="AAPL", name="Apple", manual_asset_class_id=us_stocks.id)
    bnd = Security(ticker="BND", name="Vanguard Bond", manual_asset_class_id=bonds.id)
    db.add_all([aapl, bnd])
    db.flush()

    today = date.today()

    # Holdings for Vanguard (allocation account)
    db.add(
        Holding(
            account_snapshot_id=vanguard_acct_snap.id,
            security_id=aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("5000.00"),
        )
    )
    db.add(
        DailyHoldingValue(
            valuation_date=today,
            account_id=vanguard.id,
            account_snapshot_id=vanguard_acct_snap.id,
            security_id=aapl.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("500"),
            market_value=Decimal("5000.00"),
        )
    )
    db.add(
        Holding(
            account_snapshot_id=vanguard_acct_snap.id,
            security_id=bnd.id,
            ticker="BND",
            quantity=Decimal("30"),
            snapshot_price=Decimal("100"),
            snapshot_value=Decimal("3000.00"),
        )
    )
    db.add(
        DailyHoldingValue(
            valuation_date=today,
            account_id=vanguard.id,
            account_snapshot_id=vanguard_acct_snap.id,
            security_id=bnd.id,
            ticker="BND",
            quantity=Decimal("30"),
            close_price=Decimal("100"),
            market_value=Decimal("3000.00"),
        )
    )

    # Holdings for Schwab (non-allocation account)
    db.add(
        Holding(
            account_snapshot_id=schwab_acct_snap.id,
            security_id=aapl.id,
            ticker="AAPL",
            quantity=Decimal("4"),
            snapshot_price=Decimal("500"),
            snapshot_value=Decimal("2000.00"),
        )
    )
    db.add(
        DailyHoldingValue(
            valuation_date=today,
            account_id=schwab.id,
            account_snapshot_id=schwab_acct_snap.id,
            security_id=aapl.id,
            ticker="AAPL",
            quantity=Decimal("4"),
            close_price=Decimal("500"),
            market_value=Decimal("2000.00"),
        )
    )

    db.commit()
    return vanguard, schwab, snap, us_stocks, bonds


def _create_mixed_freshness_accounts(
    db: Session,
    fresh_value: Decimal,
    stale_value: Decimal,
    stale_include_in_allocation: bool = True,
) -> tuple[Account, Account]:
    """Create two accounts with different DHV freshness dates.

    Fresh account has today's DHV; stale account's latest DHV is 3 days old.
    Each account gets its own SyncSession with a realistic timestamp matching
    its DHV valuation date.

    Returns:
        Tuple of (fresh_account, stale_account)
    """
    now = datetime.now(timezone.utc)
    three_days_ago = now - timedelta(days=3)

    acc_fresh = Account(
        provider_name="SnapTrade",
        external_id="ext_fresh",
        name="Fresh Account",
        is_active=True,
        include_in_allocation=True,
    )
    acc_stale = Account(
        provider_name="SimpleFIN",
        external_id="ext_stale",
        name="Stale Account",
        is_active=True,
        include_in_allocation=stale_include_in_allocation,
    )
    db.add_all([acc_fresh, acc_stale])
    db.flush()

    create_sync_session_with_holdings(
        db, acc_fresh, now, [("AAPL", fresh_value)],
    )
    create_sync_session_with_holdings(
        db, acc_stale, three_days_ago, [("BND", stale_value)],
    )

    return acc_fresh, acc_stale


class TestDashboardAPI:
    """Integration tests for GET /api/dashboard."""

    def test_dashboard_returns_allocation_total(
        self, client: TestClient, db: Session
    ):
        """Response includes the allocation_total field."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        assert "allocation_total" in data
        # allocation_total should be a numeric string
        allocation_total = Decimal(data["allocation_total"])
        assert allocation_total > 0

    def test_allocation_total_matches_sum(
        self, client: TestClient, db: Session
    ):
        """allocation_total equals sum of allocation values + unassigned."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        data = response.json()

        allocation_total = Decimal(data["allocation_total"])
        values_sum = sum(
            Decimal(a["value"]) for a in data["allocations"]
        ) + Decimal(data["unassigned_value"])

        assert allocation_total == values_sum

    def test_allocation_total_only_includes_allocation_accounts(
        self, client: TestClient, db: Session
    ):
        """allocation_total only includes accounts with include_in_allocation=True."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        data = response.json()

        # Vanguard has $8000 in holdings (5000 AAPL + 3000 BND), allocation account
        # Schwab has $2000 in holdings (2000 AAPL), NOT allocation account
        allocation_total = Decimal(data["allocation_total"])
        total_net_worth = Decimal(data["total_net_worth"])

        # allocation_total should be $8000 (only Vanguard)
        assert allocation_total == Decimal("8000.00")
        # total_net_worth should be $10000 (both accounts)
        assert total_net_worth == Decimal("10000.00")

    def test_allocation_total_zero_when_no_data(self, client: TestClient):
        """Empty database returns allocation_total of 0."""
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        assert Decimal(data["allocation_total"]) == Decimal("0")
        assert Decimal(data["total_net_worth"]) == Decimal("0")

    def test_dashboard_uses_daily_when_newer(
        self, client: TestClient, db: Session
    ):
        """Dashboard uses daily valuations when newer than snapshot."""
        acct = Account(
            provider_name="SnapTrade",
            external_id="ext_daily",
            name="Daily Account",
            is_active=True,
            include_in_allocation=True,
        )
        db.add(acct)
        db.flush()

        us_stocks = AssetClass(
            name="US Stocks", color="#3B82F6", target_percent=Decimal("100.00")
        )
        db.add(us_stocks)
        db.flush()

        aapl = Security(ticker="AAPL", name="Apple", manual_asset_class_id=us_stocks.id)
        db.add(aapl)
        db.flush()

        # Old sync_session (Jan 5)
        snap = SyncSession(
            timestamp=datetime(2025, 1, 5, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("5000.00"),
        )
        db.add(acct_snap)
        db.flush()

        db.add(
            Holding(
                account_snapshot_id=acct_snap.id,
                security_id=aapl.id,
                ticker="AAPL",
                quantity=Decimal("10"),
                snapshot_price=Decimal("500"),
                snapshot_value=Decimal("5000.00"),
            )
        )

        # Newer daily value (Jan 9) with higher value
        db.add(
            DailyHoldingValue(
                account_id=acct.id,
                account_snapshot_id=acct_snap.id,
                valuation_date=date(2025, 1, 9),
                security_id=aapl.id,
                ticker="AAPL",
                quantity=Decimal("10"),
                close_price=Decimal("600"),
                market_value=Decimal("6000.00"),
            )
        )

        db.commit()

        response = client.get("/api/dashboard")
        data = response.json()

        # Should use daily value (6000) not snapshot (5000)
        total_net_worth = Decimal(data["total_net_worth"])
        assert total_net_worth == Decimal("6000.00")

    def test_dashboard_uses_latest_daily_valuation(
        self, client: TestClient, db: Session
    ):
        """Dashboard uses the latest daily valuation date."""
        acct = Account(
            provider_name="SnapTrade",
            external_id="ext_snap",
            name="Snap Account",
            is_active=True,
            include_in_allocation=True,
        )
        db.add(acct)
        db.flush()

        us_stocks = AssetClass(
            name="US Stocks", color="#3B82F6", target_percent=Decimal("100.00")
        )
        db.add(us_stocks)
        db.flush()

        aapl = Security(ticker="AAPL", name="Apple", manual_asset_class_id=us_stocks.id)
        db.add(aapl)
        db.flush()

        snap = SyncSession(
            timestamp=datetime(2025, 1, 10, tzinfo=timezone.utc), is_complete=True
        )
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acct.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("7000.00"),
        )
        db.add(acct_snap)
        db.flush()

        # Sync-created DHV (Jan 10)
        db.add(
            DailyHoldingValue(
                account_id=acct.id,
                account_snapshot_id=acct_snap.id,
                valuation_date=date(2025, 1, 10),
                security_id=aapl.id,
                ticker="AAPL",
                quantity=Decimal("10"),
                close_price=Decimal("700"),
                market_value=Decimal("7000.00"),
            )
        )

        # Older daily value (Jan 8)
        db.add(
            DailyHoldingValue(
                account_id=acct.id,
                account_snapshot_id=acct_snap.id,
                valuation_date=date(2025, 1, 8),
                security_id=aapl.id,
                ticker="AAPL",
                quantity=Decimal("10"),
                close_price=Decimal("650"),
                market_value=Decimal("6500.00"),
            )
        )

        db.commit()

        response = client.get("/api/dashboard")
        data = response.json()

        # Should use latest daily value (7000 from Jan 10)
        total_net_worth = Decimal(data["total_net_worth"])
        assert total_net_worth == Decimal("7000.00")

    def test_dashboard_all_widgets_consistent(
        self, client: TestClient, db: Session
    ):
        """Total net worth equals sum of account values."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        data = response.json()

        total_net_worth = Decimal(data["total_net_worth"])
        account_sum = sum(Decimal(a["value"]) for a in data["accounts"])

        assert total_net_worth == account_sum

    def test_allocation_only_filters_accounts(
        self, client: TestClient, db: Session
    ):
        """allocation_only=true returns only allocation accounts."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard?allocation_only=true")
        assert response.status_code == 200
        data = response.json()

        # Only Vanguard (allocation account) should be returned
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["name"] == "Vanguard IRA"

    def test_allocation_only_filters_net_worth(
        self, client: TestClient, db: Session
    ):
        """allocation_only=true net worth only sums allocation accounts."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard?allocation_only=true")
        data = response.json()

        total_net_worth = Decimal(data["total_net_worth"])
        # Only Vanguard with $8000
        assert total_net_worth == Decimal("8000.00")

    def test_default_includes_all(
        self, client: TestClient, db: Session
    ):
        """Without allocation_only, all active accounts are included."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        data = response.json()

        # Both Vanguard and Schwab
        assert len(data["accounts"]) == 2
        total_net_worth = Decimal(data["total_net_worth"])
        assert total_net_worth == Decimal("10000.00")

    def test_account_ids_filters_accounts(
        self, client: TestClient, db: Session
    ):
        """account_ids parameter filters to specified accounts."""
        vanguard, schwab, *_ = _create_dashboard_test_data(db)

        response = client.get(f"/api/dashboard?account_ids={vanguard.id}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["name"] == "Vanguard IRA"
        assert Decimal(data["total_net_worth"]) == Decimal("8000.00")

    def test_account_ids_filters_net_worth(
        self, client: TestClient, db: Session
    ):
        """account_ids filters net worth to selected accounts only."""
        vanguard, schwab, *_ = _create_dashboard_test_data(db)

        response = client.get(f"/api/dashboard?account_ids={schwab.id}")
        data = response.json()

        assert Decimal(data["total_net_worth"]) == Decimal("2000.00")

    def test_account_ids_with_allocation_only_intersection(
        self, client: TestClient, db: Session
    ):
        """account_ids + allocation_only = intersection of both filters."""
        vanguard, schwab, *_ = _create_dashboard_test_data(db)

        # Schwab is not an allocation account, so intersection is empty
        response = client.get(
            f"/api/dashboard?account_ids={schwab.id}&allocation_only=true"
        )
        data = response.json()
        assert len(data["accounts"]) == 0
        assert Decimal(data["total_net_worth"]) == Decimal("0")

    def test_account_ids_nonexistent_returns_empty(
        self, client: TestClient, db: Session
    ):
        """account_ids with valid UUID that doesn't match any account returns empty."""
        _create_dashboard_test_data(db)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/api/dashboard?account_ids={fake_uuid}")
        assert response.status_code == 200
        data = response.json()

        assert len(data["accounts"]) == 0
        assert Decimal(data["total_net_worth"]) == Decimal("0")

    def test_account_ids_invalid_format_returns_400(
        self, client: TestClient, db: Session
    ):
        """account_ids with invalid UUID format returns 400."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard?account_ids=not-a-uuid")
        assert response.status_code == 400
        assert "Invalid account ID format" in response.json()["detail"]

    def test_account_ids_multiple(
        self, client: TestClient, db: Session
    ):
        """account_ids with multiple comma-separated IDs works."""
        vanguard, schwab, *_ = _create_dashboard_test_data(db)

        response = client.get(
            f"/api/dashboard?account_ids={vanguard.id},{schwab.id}"
        )
        data = response.json()

        assert len(data["accounts"]) == 2
        assert Decimal(data["total_net_worth"]) == Decimal("10000.00")

    def test_stale_account_uses_latest_dhv(
        self, client: TestClient, db: Session
    ):
        """Dashboard includes stale accounts using their latest DHV value.

        Account A has today's DHV ($5000), Account B's latest DHV is 3 days
        old ($3000). Dashboard should show both accounts and use B's
        stale-but-latest DHV value. total_net_worth == sum of both.
        """
        acc_fresh, acc_stale = _create_mixed_freshness_accounts(
            db,
            fresh_value=Decimal("5000"),
            stale_value=Decimal("3000"),
        )
        db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        # Both accounts should appear
        assert len(data["accounts"]) == 2

        account_values = {a["name"]: Decimal(a["value"]) for a in data["accounts"]}
        assert account_values["Fresh Account"] == Decimal("5000")
        assert account_values["Stale Account"] == Decimal("3000")

        # total_net_worth includes both
        assert Decimal(data["total_net_worth"]) == Decimal("8000")

    def test_widgets_consistent_with_stale_accounts(
        self, client: TestClient, db: Session
    ):
        """total_net_worth == sum(account.value) even with mixed-freshness DHV.

        When accounts have different DHV dates, the widget consistency
        invariant (total_net_worth equals sum of account values) must hold.
        The stale account has include_in_allocation=False to additionally
        verify that non-allocation accounts still count toward net worth
        but are excluded under allocation_only=true.
        """
        _create_mixed_freshness_accounts(
            db,
            fresh_value=Decimal("7500"),
            stale_value=Decimal("2500"),
            stale_include_in_allocation=False,
        )
        db.commit()

        # Default: all active accounts contribute to net worth
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        total_net_worth = Decimal(data["total_net_worth"])
        account_sum = sum(Decimal(a["value"]) for a in data["accounts"])

        # Widget consistency invariant
        assert total_net_worth == account_sum
        # Both accounts included (7500 + 2500)
        assert total_net_worth == Decimal("10000")

        # allocation_only: stale non-allocation account excluded
        response = client.get("/api/dashboard?allocation_only=true")
        assert response.status_code == 200
        data = response.json()

        assert len(data["accounts"]) == 1
        assert Decimal(data["total_net_worth"]) == Decimal("7500")

    def test_zero_dhv_account_shows_value_zero(
        self, client: TestClient, db: Session
    ):
        """Account with snapshots but no DHV rows appears with value $0.

        Account A has normal DHV data ($5000). Account B has an
        AccountSnapshot but zero DHV rows (e.g. newly connected, sync
        created snapshot but valuation hasn't run yet). Dashboard should
        list both accounts, with B at $0, and total_net_worth should
        still equal sum(account.value).
        """
        acc_a = Account(
            provider_name="SnapTrade",
            external_id="ext_normal",
            name="Normal Account",
            is_active=True,
            include_in_allocation=True,
        )
        acc_b = Account(
            provider_name="SimpleFIN",
            external_id="ext_no_dhv",
            name="No DHV Account",
            is_active=True,
            include_in_allocation=True,
        )
        db.add_all([acc_a, acc_b])
        db.flush()

        # Account A: normal sync with holdings + DHV
        now = datetime.now(timezone.utc)
        create_sync_session_with_holdings(
            db, acc_a, now, [("AAPL", Decimal("5000"))],
        )

        # Account B: snapshot exists but no holdings/DHV
        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()
        db.add(AccountSnapshot(
            account_id=acc_b.id,
            sync_session_id=snap.id,
            status="success",
            total_value=Decimal("0"),
        ))

        db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        # Both accounts should appear
        assert len(data["accounts"]) == 2

        account_values = {a["name"]: Decimal(a["value"]) for a in data["accounts"]}
        assert account_values["Normal Account"] == Decimal("5000")
        assert account_values["No DHV Account"] == Decimal("0")

        # Widget consistency: total == sum of account values
        total_net_worth = Decimal(data["total_net_worth"])
        account_sum = sum(Decimal(a["value"]) for a in data["accounts"])
        assert total_net_worth == account_sum
        assert total_net_worth == Decimal("5000")

    def test_holdings_without_dhv_shows_value_zero(
        self, client: TestClient, db: Session
    ):
        """Account with snapshot+holdings but no DHV rows shows value $0.

        This is an unexpected state: the snapshot has holdings recorded
        but DailyHoldingValue rows were never written (e.g. valuation
        crashed mid-sync). The dashboard should still list the account
        with value $0 since portfolio data is driven entirely by DHV.
        """
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_hold_no_dhv",
            name="Holdings No DHV",
            is_active=True,
            include_in_allocation=True,
        )
        db.add(acc)
        db.flush()

        snap = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acc.id,
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
        # No DailyHoldingValue rows

        db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        # Account should appear but with $0 value
        assert len(data["accounts"]) == 1
        assert Decimal(data["accounts"][0]["value"]) == Decimal("0")
        assert Decimal(data["total_net_worth"]) == Decimal("0")

    def test_valuation_status_ok_for_normal_accounts(
        self, client: TestClient, db: Session
    ):
        """Normal accounts with complete DHV data have valuation_status='ok'."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        for acct in data["accounts"]:
            assert acct["valuation_status"] == "ok"
            assert acct["valuation_date"] is not None

    def test_valuation_status_missing_when_no_dhv(
        self, client: TestClient, db: Session
    ):
        """Account with snapshot+holdings but no DHV has valuation_status='missing'."""
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_val_missing",
            name="Missing Val Account",
            is_active=True,
            include_in_allocation=True,
        )
        db.add(acc)
        db.flush()

        snap = SyncSession(timestamp=datetime.now(timezone.utc), is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap = AccountSnapshot(
            account_id=acc.id,
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

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["valuation_status"] == "missing"
        assert data["accounts"][0]["valuation_date"] is None

    def test_valuation_status_fields_present_in_response(
        self, client: TestClient, db: Session
    ):
        """Response always includes valuation_status and valuation_date fields."""
        _create_dashboard_test_data(db)

        response = client.get("/api/dashboard")
        data = response.json()

        for acct in data["accounts"]:
            assert "valuation_status" in acct
            assert "valuation_date" in acct

    def test_valuation_status_null_for_never_synced(
        self, client: TestClient, db: Session
    ):
        """Account with no snapshots has valuation_status=null."""
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_never_synced",
            name="Never Synced",
            is_active=True,
            include_in_allocation=True,
        )
        db.add(acc)
        db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["valuation_status"] is None
        assert data["accounts"][0]["valuation_date"] is None

    def test_mixed_accounts_one_with_dhv_one_without(
        self, client: TestClient, db: Session
    ):
        """One account has DHV, another has holdings but no DHV rows.

        Account A has normal sync data ($5000). Account B has a snapshot
        with $3000 in holdings but no DHV rows. Dashboard should show
        both accounts, with B at $0, and total_net_worth should only
        reflect Account A's value.
        """
        acc_a = Account(
            provider_name="SnapTrade",
            external_id="ext_with_dhv",
            name="With DHV",
            is_active=True,
            include_in_allocation=True,
        )
        acc_b = Account(
            provider_name="SimpleFIN",
            external_id="ext_hold_no_dhv",
            name="Holdings No DHV",
            is_active=True,
            include_in_allocation=True,
        )
        db.add_all([acc_a, acc_b])
        db.flush()

        # Account A: normal sync with DHV
        now = datetime.now(timezone.utc)
        create_sync_session_with_holdings(
            db, acc_a, now, [("AAPL", Decimal("5000"))],
        )

        # Account B: snapshot + holdings but no DHV
        snap = SyncSession(timestamp=now, is_complete=True)
        db.add(snap)
        db.flush()

        acct_snap_b = AccountSnapshot(
            account_id=acc_b.id,
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
        # No DHV for Account B

        db.commit()

        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()

        # Both accounts listed
        assert len(data["accounts"]) == 2

        account_values = {a["name"]: Decimal(a["value"]) for a in data["accounts"]}
        assert account_values["With DHV"] == Decimal("5000")
        assert account_values["Holdings No DHV"] == Decimal("0")

        # Widget consistency
        total_net_worth = Decimal(data["total_net_worth"])
        account_sum = sum(Decimal(a["value"]) for a in data["accounts"])
        assert total_net_worth == account_sum
        assert total_net_worth == Decimal("5000")
