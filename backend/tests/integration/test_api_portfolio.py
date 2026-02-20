"""Integration tests for portfolio allocation API endpoints."""

from datetime import date, datetime, time, timezone
from fastapi.testclient import TestClient
from decimal import Decimal

from models import (
    Account,
    AccountSnapshot,
    AssetClass,
    DailyHoldingValue,
    HoldingLot,
    LotDisposal,
    Security,
    SyncSession,
)


class TestPortfolioAPI:
    """Integration tests for /api/portfolio endpoints."""

    def test_get_allocation_empty(self, client: TestClient):
        """Test getting allocation when no asset types exist."""
        response = client.get("/api/portfolio/allocation")
        assert response.status_code == 200
        data = response.json()
        assert data["allocations"] == []
        assert data["total_percent"] == "0.00"
        assert data["is_valid"] is False

    def test_get_allocation_with_types(self, client: TestClient, db):
        """Test getting allocation with asset types."""
        type1 = AssetClass(name="Stocks", color="#3B82F6", target_percent=Decimal("60.00"))
        type2 = AssetClass(name="Bonds", color="#10B981", target_percent=Decimal("40.00"))
        db.add_all([type1, type2])
        db.commit()

        response = client.get("/api/portfolio/allocation")
        assert response.status_code == 200
        data = response.json()
        assert len(data["allocations"]) == 2
        assert data["total_percent"] == "100.00"
        assert data["is_valid"] is True

    def test_update_allocation_valid(self, client: TestClient, db):
        """Test updating allocation with valid 100% total."""
        type1 = AssetClass(name="Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        db.add_all([type1, type2])
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": type1.id, "target_percent": "70.00"},
                    {"asset_type_id": type2.id, "target_percent": "30.00"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_percent"] == "100.00"
        assert data["is_valid"] is True

        # Verify in database
        db.refresh(type1)
        db.refresh(type2)
        assert type1.target_percent == Decimal("70.00")
        assert type2.target_percent == Decimal("30.00")

    def test_update_allocation_invalid_total(self, client: TestClient, db):
        """Test updating allocation with invalid total fails."""
        type1 = AssetClass(name="Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        db.add_all([type1, type2])
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": type1.id, "target_percent": "60.00"},
                    {"asset_type_id": type2.id, "target_percent": "30.00"},  # Total = 90%
                ]
            },
        )
        assert response.status_code == 400
        assert "100%" in response.json()["detail"]

    def test_update_allocation_missing_type(self, client: TestClient, db):
        """Test updating allocation with non-existent type is skipped."""
        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": "nonexistent", "target_percent": "100.00"},
                ]
            },
        )
        # Non-existent IDs are silently skipped by the service
        assert response.status_code == 200

    def test_update_allocation_negative_percent(self, client: TestClient, db):
        """Test updating allocation with negative percentage fails."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": asset_type.id, "target_percent": "-10.00"},
                ]
            },
        )
        # Fails validation (sum check catches negative as not 100%)
        assert response.status_code == 400

    def test_update_allocation_over_100(self, client: TestClient, db):
        """Test updating allocation over 100% fails."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": asset_type.id, "target_percent": "110.00"},
                ]
            },
        )
        assert response.status_code == 400
        assert "100%" in response.json()["detail"]

    def test_update_allocation_single_type_100_percent(self, client: TestClient, db):
        """Test updating single asset type to 100%."""
        asset_type = AssetClass(name="Stocks", color="#3B82F6")
        db.add(asset_type)
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": asset_type.id, "target_percent": "100.00"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["total_percent"] == "100.00"

    def test_update_allocation_precision(self, client: TestClient, db):
        """Test allocation handles decimal precision."""
        type1 = AssetClass(name="Stocks", color="#3B82F6")
        type2 = AssetClass(name="Bonds", color="#10B981")
        type3 = AssetClass(name="Real Estate", color="#F59E0B")
        db.add_all([type1, type2, type3])
        db.commit()

        response = client.put(
            "/api/portfolio/allocation",
            json={
                "allocations": [
                    {"asset_type_id": type1.id, "target_percent": "33.33"},
                    {"asset_type_id": type2.id, "target_percent": "33.33"},
                    {"asset_type_id": type3.id, "target_percent": "33.34"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_percent"] == "100.00"
        assert data["is_valid"] is True


class TestValueHistory:
    """Tests for /api/portfolio/value-history endpoint."""

    def test_today_total_includes_all_accounts_even_partial_dhv(
        self, client: TestClient, db
    ):
        """Portfolio value for today uses live summary (all accounts),
        not just DHV rows that happen to exist for today.

        Reproduces the bug where stale accounts (no DHV for today) were
        excluded from the chart's today data point.
        """
        from datetime import timedelta

        today = date.today()
        yesterday = today - timedelta(days=1)

        # Create two accounts
        acc_fresh = Account(
            provider_name="SnapTrade", external_id="fresh_001",
            name="Fresh Account", is_active=True,
        )
        acc_stale = Account(
            provider_name="SimpleFIN", external_id="stale_001",
            name="Stale Account", is_active=True,
        )
        db.add_all([acc_fresh, acc_stale])
        db.flush()

        # Create sync session and snapshots
        sync_session = SyncSession(is_complete=True)
        db.add(sync_session)
        db.flush()

        snap_fresh = AccountSnapshot(
            account_id=acc_fresh.id,
            sync_session_id=sync_session.id,
            status="success",
            total_value=Decimal("3000000"),
        )
        snap_stale = AccountSnapshot(
            account_id=acc_stale.id,
            sync_session_id=sync_session.id,
            status="success",
            total_value=Decimal("1500000"),
        )
        db.add_all([snap_fresh, snap_stale])
        db.flush()

        # Create securities
        sec_a = Security(ticker="AAPL", name="Apple")
        sec_b = Security(ticker="VTI", name="Vanguard Total")
        db.add_all([sec_a, sec_b])
        db.flush()

        # Fresh account: has DHV for today
        dhv_fresh = DailyHoldingValue(
            valuation_date=today,
            account_id=acc_fresh.id,
            account_snapshot_id=snap_fresh.id,
            security_id=sec_a.id,
            ticker="AAPL",
            quantity=Decimal("100"),
            close_price=Decimal("30000"),
            market_value=Decimal("3000000"),
        )
        db.add(dhv_fresh)

        # Stale account: DHV only for yesterday (simulates stale sync)
        dhv_stale = DailyHoldingValue(
            valuation_date=yesterday,
            account_id=acc_stale.id,
            account_snapshot_id=snap_stale.id,
            security_id=sec_b.id,
            ticker="VTI",
            quantity=Decimal("100"),
            close_price=Decimal("15000"),
            market_value=Decimal("1500000"),
        )
        db.add(dhv_stale)
        db.commit()

        response = client.get("/api/portfolio/value-history?group_by=total")
        assert response.status_code == 200
        data = response.json()

        # Find today's data point
        today_str = today.isoformat()
        today_points = [
            dp for dp in data["data_points"] if dp["date"] == today_str
        ]
        assert len(today_points) == 1

        # Today's value should include BOTH accounts (~$4.5M), not just
        # the fresh one (~$3M) which is the only one with DHV for today
        today_value = Decimal(today_points[0]["value"])
        assert today_value == Decimal("4500000")


class TestDHVDiagnostics:
    """Tests for GET /api/portfolio/dhv-diagnostics."""

    def test_empty_db(self, client: TestClient):
        """Empty database returns empty diagnostics."""
        response = client.get("/api/portfolio/dhv-diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert data["accounts"] == []
        assert data["total_missing_days"] == 0

    def test_with_gaps(self, client: TestClient, db):
        """Detects DHV gaps for accounts."""
        from datetime import datetime, timedelta, timezone

        yesterday = date.today() - timedelta(days=1)
        three_days_ago = yesterday - timedelta(days=2)

        account = Account(
            provider_name="SnapTrade", external_id="diag_001",
            name="Test Account", is_active=True,
        )
        db.add(account)
        db.flush()

        sync_session = SyncSession(is_complete=True)
        db.add(sync_session)
        db.flush()

        # Set timestamp to noon UTC on three_days_ago (noon avoids UTC/local day mismatch)
        from datetime import time
        sync_session.timestamp = datetime.combine(three_days_ago, time(12, 0), tzinfo=timezone.utc)
        db.flush()

        snap = AccountSnapshot(
            account_id=account.id,
            sync_session_id=sync_session.id,
            status="success",
            total_value=Decimal("1000"),
        )
        db.add(snap)
        db.flush()

        sec = Security(ticker="AAPL", name="Apple")
        db.add(sec)
        db.flush()

        # Only has DHV for three_days_ago, missing day_before and yesterday
        dhv = DailyHoldingValue(
            valuation_date=three_days_ago,
            account_id=account.id,
            account_snapshot_id=snap.id,
            security_id=sec.id,
            ticker="AAPL",
            quantity=Decimal("10"),
            close_price=Decimal("100"),
            market_value=Decimal("1000"),
        )
        db.add(dhv)
        db.commit()

        response = client.get("/api/portfolio/dhv-diagnostics")
        assert response.status_code == 200
        data = response.json()
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["missing_days"] == 2
        assert data["total_missing_days"] == 2


def _create_account_with_lot_data(db, *, is_active=True):
    """Helper to create an account with sync session, snapshot, security, DHV, and lot."""
    account = Account(
        provider_name="SnapTrade",
        external_id=f"cost_{is_active}",
        name="Test Account",
        is_active=is_active,
    )
    db.add(account)
    db.flush()

    sync_session = SyncSession(is_complete=True)
    db.add(sync_session)
    db.flush()

    snap = AccountSnapshot(
        account_id=account.id,
        sync_session_id=sync_session.id,
        status="success",
        total_value=Decimal("10000"),
    )
    db.add(snap)
    db.flush()

    security = Security(ticker="AAPL", name="Apple Inc")
    db.add(security)
    db.flush()

    today = date.today()
    dhv = DailyHoldingValue(
        valuation_date=today,
        account_id=account.id,
        account_snapshot_id=snap.id,
        security_id=security.id,
        ticker="AAPL",
        quantity=Decimal("10"),
        close_price=Decimal("200"),
        market_value=Decimal("2000"),
    )
    db.add(dhv)

    lot = HoldingLot(
        account_id=account.id,
        security_id=security.id,
        ticker="AAPL",
        acquisition_date=date(2024, 1, 15),
        cost_basis_per_unit=Decimal("150"),
        original_quantity=Decimal("10"),
        current_quantity=Decimal("10"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.flush()

    return account, security, snap, lot


class TestPortfolioCostBasis:
    """Tests for GET /api/portfolio/cost-basis."""

    def test_cost_basis_no_lots(self, client: TestClient):
        """Returns has_lots=false when no lots exist."""
        response = client.get("/api/portfolio/cost-basis")
        assert response.status_code == 200
        data = response.json()
        assert data["has_lots"] is False
        assert data["lot_count"] == 0
        assert data["total_cost_basis"] is None

    def test_cost_basis_with_lots(self, client: TestClient, db):
        """Computes cost basis and unrealized G/L from lots and DHV."""
        account, security, snap, lot = _create_account_with_lot_data(db)
        db.commit()

        response = client.get("/api/portfolio/cost-basis")
        assert response.status_code == 200
        data = response.json()
        assert data["has_lots"] is True
        assert data["lot_count"] == 1

        # cost_basis = 150 * 10 = 1500
        assert Decimal(data["total_cost_basis"]) == Decimal("1500")
        # market_value = 200 * 10 = 2000
        assert Decimal(data["total_market_value"]) == Decimal("2000")
        # unrealized = 2000 - 1500 = 500
        assert Decimal(data["total_unrealized_gain_loss"]) == Decimal("500")
        # No disposals yet
        assert Decimal(data["total_realized_gain_loss_ytd"]) == Decimal("0")
        # Coverage should be present
        assert data["coverage_percent"] is not None

    def test_cost_basis_realized_ytd(self, client: TestClient, db):
        """Includes YTD realized gain/loss from disposals."""
        account, security, snap, lot = _create_account_with_lot_data(db)

        disposal = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(date.today().year, 2, 1),
            quantity=Decimal("2"),
            proceeds_per_unit=Decimal("220"),
            source="manual",
        )
        db.add(disposal)
        db.commit()

        response = client.get("/api/portfolio/cost-basis")
        assert response.status_code == 200
        data = response.json()

        # realized = (220 - 150) * 2 = 140
        assert Decimal(data["total_realized_gain_loss_ytd"]) == Decimal("140")

    def test_cost_basis_inactive_accounts_excluded(self, client: TestClient, db):
        """Lots from inactive accounts are excluded."""
        _create_account_with_lot_data(db, is_active=False)
        db.commit()

        response = client.get("/api/portfolio/cost-basis")
        assert response.status_code == 200
        data = response.json()
        assert data["has_lots"] is False


class TestRealizedGains:
    """Tests for GET /api/portfolio/realized-gains."""

    def test_realized_gains_empty(self, client: TestClient):
        """Returns empty list when no disposals exist."""
        response = client.get("/api/portfolio/realized-gains")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert Decimal(data["total_realized_gain_loss"]) == Decimal("0")
        assert data["year"] is None

    def test_realized_gains_with_data(self, client: TestClient, db):
        """Returns disposal items with computed gain/loss."""
        account, security, snap, lot = _create_account_with_lot_data(db)

        disposal = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(2025, 6, 15),
            quantity=Decimal("5"),
            proceeds_per_unit=Decimal("250"),
            source="manual",
        )
        db.add(disposal)
        db.commit()

        response = client.get("/api/portfolio/realized-gains")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        item = data["items"][0]
        assert item["ticker"] == "AAPL"
        assert item["security_name"] == "Apple Inc"
        assert item["account_name"] == "Test Account"
        assert Decimal(item["quantity"]) == Decimal("5")
        assert Decimal(item["cost_basis_per_unit"]) == Decimal("150")
        assert Decimal(item["proceeds_per_unit"]) == Decimal("250")
        # total_proceeds = 250 * 5 = 1250
        assert Decimal(item["total_proceeds"]) == Decimal("1250")
        # total_cost = 150 * 5 = 750
        assert Decimal(item["total_cost"]) == Decimal("750")
        # gain = 1250 - 750 = 500
        assert Decimal(item["gain_loss"]) == Decimal("500")

        assert Decimal(data["total_realized_gain_loss"]) == Decimal("500")

    def test_realized_gains_year_filter(self, client: TestClient, db):
        """Filters disposals by year."""
        account, security, snap, lot = _create_account_with_lot_data(db)

        d1 = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(2025, 3, 1),
            quantity=Decimal("2"),
            proceeds_per_unit=Decimal("200"),
            source="manual",
        )
        d2 = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(2024, 11, 1),
            quantity=Decimal("3"),
            proceeds_per_unit=Decimal("180"),
            source="manual",
        )
        db.add_all([d1, d2])
        db.commit()

        # Filter to 2025 only
        response = client.get("/api/portfolio/realized-gains?year=2025")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["year"] == 2025

        # Filter to 2024
        response = client.get("/api/portfolio/realized-gains?year=2024")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["year"] == 2024

    def test_realized_gains_all_years(self, client: TestClient, db):
        """No year param returns all disposals."""
        account, security, snap, lot = _create_account_with_lot_data(db)

        d1 = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(2025, 3, 1),
            quantity=Decimal("2"),
            proceeds_per_unit=Decimal("200"),
            source="manual",
        )
        d2 = LotDisposal(
            holding_lot_id=lot.id,
            account_id=account.id,
            security_id=security.id,
            disposal_date=date(2024, 11, 1),
            quantity=Decimal("3"),
            proceeds_per_unit=Decimal("180"),
            source="manual",
        )
        db.add_all([d1, d2])
        db.commit()

        response = client.get("/api/portfolio/realized-gains")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["year"] is None


def _create_two_accounts_with_dhv(db):
    """Create two active accounts with DHV data for filtering tests.

    Returns (account_a, account_b) where:
    - account_a has $5000 DHV (AAPL)
    - account_b has $3000 DHV (VTI)
    """
    from datetime import timedelta

    today = date.today()
    yesterday = today - timedelta(days=1)

    acc_a = Account(
        provider_name="SnapTrade", external_id="filter_a",
        name="Account A", is_active=True, include_in_allocation=True,
    )
    acc_b = Account(
        provider_name="SnapTrade", external_id="filter_b",
        name="Account B", is_active=True, include_in_allocation=True,
    )
    db.add_all([acc_a, acc_b])
    db.flush()

    sync = SyncSession(
        timestamp=datetime.combine(yesterday, time(12, 0), tzinfo=timezone.utc),
        is_complete=True,
    )
    db.add(sync)
    db.flush()

    snap_a = AccountSnapshot(
        account_id=acc_a.id, sync_session_id=sync.id,
        status="success", total_value=Decimal("5000"),
    )
    snap_b = AccountSnapshot(
        account_id=acc_b.id, sync_session_id=sync.id,
        status="success", total_value=Decimal("3000"),
    )
    db.add_all([snap_a, snap_b])
    db.flush()

    sec_aapl = Security(ticker="AAPL", name="Apple")
    sec_vti = Security(ticker="VTI", name="Vanguard Total")
    db.add_all([sec_aapl, sec_vti])
    db.flush()

    # DHV for yesterday for both accounts
    db.add(DailyHoldingValue(
        valuation_date=yesterday, account_id=acc_a.id,
        account_snapshot_id=snap_a.id, security_id=sec_aapl.id,
        ticker="AAPL", quantity=Decimal("50"),
        close_price=Decimal("100"), market_value=Decimal("5000"),
    ))
    db.add(DailyHoldingValue(
        valuation_date=yesterday, account_id=acc_b.id,
        account_snapshot_id=snap_b.id, security_id=sec_vti.id,
        ticker="VTI", quantity=Decimal("30"),
        close_price=Decimal("100"), market_value=Decimal("3000"),
    ))

    # DHV for today for both accounts
    db.add(DailyHoldingValue(
        valuation_date=today, account_id=acc_a.id,
        account_snapshot_id=snap_a.id, security_id=sec_aapl.id,
        ticker="AAPL", quantity=Decimal("50"),
        close_price=Decimal("100"), market_value=Decimal("5000"),
    ))
    db.add(DailyHoldingValue(
        valuation_date=today, account_id=acc_b.id,
        account_snapshot_id=snap_b.id, security_id=sec_vti.id,
        ticker="VTI", quantity=Decimal("30"),
        close_price=Decimal("100"), market_value=Decimal("3000"),
    ))

    db.commit()
    return acc_a, acc_b, sec_aapl, sec_vti, snap_a, snap_b


class TestValueHistoryAccountFilter:
    """Tests for value-history endpoint with account_ids filter."""

    def test_account_ids_filters_value_history(self, client: TestClient, db):
        """value-history respects account_ids filter."""
        acc_a, acc_b, *_ = _create_two_accounts_with_dhv(db)

        response = client.get(
            f"/api/portfolio/value-history?group_by=total&account_ids={acc_a.id}"
        )
        assert response.status_code == 200
        data = response.json()

        # Should only include account A's value ($5000)
        for dp in data["data_points"]:
            assert Decimal(dp["value"]) == Decimal("5000")

    def test_account_ids_omitted_returns_all(self, client: TestClient, db):
        """Omitting account_ids returns all accounts (backward compat)."""
        _create_two_accounts_with_dhv(db)

        response = client.get("/api/portfolio/value-history?group_by=total")
        assert response.status_code == 200
        data = response.json()

        # Should include both accounts' values ($8000)
        for dp in data["data_points"]:
            assert Decimal(dp["value"]) == Decimal("8000")

    def test_account_ids_nonexistent_empty(self, client: TestClient, db):
        """account_ids with valid UUID that doesn't match returns empty data."""
        _create_two_accounts_with_dhv(db)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = client.get(
            f"/api/portfolio/value-history?group_by=total&account_ids={fake_uuid}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data_points"] == []

    def test_account_ids_invalid_format_returns_400(self, client: TestClient, db):
        """account_ids with invalid UUID format returns 400."""
        _create_two_accounts_with_dhv(db)

        response = client.get(
            "/api/portfolio/value-history?group_by=total&account_ids=not-a-uuid"
        )
        assert response.status_code == 400
        assert "Invalid account ID format" in response.json()["detail"]


class TestCostBasisAccountFilter:
    """Tests for cost-basis endpoint with account_ids filter."""

    def test_account_ids_filters_cost_basis(self, client: TestClient, db):
        """cost-basis respects account_ids filter."""
        acc_a, _, sec_aapl, _, snap_a, _ = _create_two_accounts_with_dhv(db)

        # Add lot only for account A
        lot = HoldingLot(
            account_id=acc_a.id, security_id=sec_aapl.id,
            ticker="AAPL", acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("80"), original_quantity=Decimal("50"),
            current_quantity=Decimal("50"), is_closed=False, source="manual",
        )
        db.add(lot)
        db.commit()

        response = client.get(
            f"/api/portfolio/cost-basis?account_ids={acc_a.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_lots"] is True
        assert data["lot_count"] == 1
        # cost_basis = 80 * 50 = 4000
        assert Decimal(data["total_cost_basis"]) == Decimal("4000")

    def test_account_ids_excludes_other_account_lots(
        self, client: TestClient, db
    ):
        """cost-basis with account_ids excludes lots from other accounts."""
        acc_a, acc_b, sec_aapl, sec_vti, snap_a, snap_b = (
            _create_two_accounts_with_dhv(db)
        )

        # Lots in both accounts
        lot_a = HoldingLot(
            account_id=acc_a.id, security_id=sec_aapl.id,
            ticker="AAPL", acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("80"), original_quantity=Decimal("50"),
            current_quantity=Decimal("50"), is_closed=False, source="manual",
        )
        lot_b = HoldingLot(
            account_id=acc_b.id, security_id=sec_vti.id,
            ticker="VTI", acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("90"), original_quantity=Decimal("30"),
            current_quantity=Decimal("30"), is_closed=False, source="manual",
        )
        db.add_all([lot_a, lot_b])
        db.commit()

        # Filter to account B only
        response = client.get(
            f"/api/portfolio/cost-basis?account_ids={acc_b.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lot_count"] == 1
        # cost_basis = 90 * 30 = 2700
        assert Decimal(data["total_cost_basis"]) == Decimal("2700")

    def test_cost_basis_omitted_returns_all(self, client: TestClient, db):
        """Omitting account_ids returns lots from all active accounts."""
        acc_a, acc_b, sec_aapl, sec_vti, *_ = _create_two_accounts_with_dhv(db)

        lot_a = HoldingLot(
            account_id=acc_a.id, security_id=sec_aapl.id,
            ticker="AAPL", acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("80"), original_quantity=Decimal("50"),
            current_quantity=Decimal("50"), is_closed=False, source="manual",
        )
        lot_b = HoldingLot(
            account_id=acc_b.id, security_id=sec_vti.id,
            ticker="VTI", acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("90"), original_quantity=Decimal("30"),
            current_quantity=Decimal("30"), is_closed=False, source="manual",
        )
        db.add_all([lot_a, lot_b])
        db.commit()

        response = client.get("/api/portfolio/cost-basis")
        assert response.status_code == 200
        data = response.json()
        assert data["lot_count"] == 2


class TestReturnsAccountFilter:
    """Tests for returns endpoint with account_ids filter."""

    def test_account_ids_filters_returns(self, client: TestClient, db):
        """returns endpoint respects account_ids filter."""
        acc_a, acc_b, *_ = _create_two_accounts_with_dhv(db)

        response = client.get(
            f"/api/portfolio/returns?scope=portfolio&periods=1D&account_ids={acc_a.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"] is not None

    def test_returns_omitted_returns_all(self, client: TestClient, db):
        """Omitting account_ids returns portfolio-level results for all accounts."""
        _create_two_accounts_with_dhv(db)

        response = client.get(
            "/api/portfolio/returns?scope=portfolio&periods=1D"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["portfolio"] is not None

    def test_returns_account_ids_filters_account_list(
        self, client: TestClient, db
    ):
        """account_ids filters the per-account list in 'all' scope."""
        acc_a, acc_b, *_ = _create_two_accounts_with_dhv(db)

        response = client.get(
            f"/api/portfolio/returns?scope=all&periods=1D&account_ids={acc_a.id}"
        )
        assert response.status_code == 200
        data = response.json()

        # Only account A should appear in accounts list
        assert len(data["accounts"]) == 1
        assert data["accounts"][0]["scope_name"] == "Account A"

