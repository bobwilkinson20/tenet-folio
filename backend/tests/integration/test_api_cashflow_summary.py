"""Integration tests for GET /api/portfolio/cashflow-summary."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Account
from models.activity import Activity


@pytest.fixture
def two_accounts(db: Session):
    """Create two accounts for testing."""
    acc1 = Account(
        provider_name="SnapTrade",
        external_id="ext_cf_1",
        name="Cash Flow Account 1",
        is_active=True,
    )
    acc2 = Account(
        provider_name="SnapTrade",
        external_id="ext_cf_2",
        name="Cash Flow Account 2",
        is_active=True,
    )
    db.add_all([acc1, acc2])
    db.commit()
    return acc1, acc2


class TestCashflowSummary:
    """Tests for GET /api/portfolio/cashflow-summary."""

    def test_empty_when_no_accounts(self, client, db):
        """No accounts at all returns empty list."""
        response = client.get("/api/portfolio/cashflow-summary")
        assert response.status_code == 200
        assert response.json() == []

    def test_includes_accounts_with_no_activities(self, client, db, two_accounts):
        """Active accounts appear even when they have zero activities."""
        acc1, acc2 = two_accounts

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        assert len(data) == 2

        by_account = {d["account_id"]: d for d in data}
        for acc in (acc1, acc2):
            entry = by_account[acc.id]
            assert entry["activity_count"] == 0
            assert entry["unreviewed_count"] == 0
            assert Decimal(entry["total_inflows"]) == Decimal("0")
            assert Decimal(entry["total_outflows"]) == Decimal("0")
            assert Decimal(entry["net_flow"]) == Decimal("0")

    def test_excludes_inactive_accounts(self, client, db):
        """Inactive accounts should not appear in the summary."""
        active = Account(
            provider_name="SnapTrade",
            external_id="ext_active",
            name="Active Account",
            is_active=True,
        )
        inactive = Account(
            provider_name="SnapTrade",
            external_id="ext_inactive",
            name="Inactive Account",
            is_active=False,
        )
        db.add_all([active, inactive])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        assert len(data) == 1
        assert data[0]["account_id"] == active.id

    def test_groups_by_account(self, client, db, two_accounts):
        acc1, acc2 = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_a1_1",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("1000"),
            ),
            Activity(
                account_id=acc2.id,
                provider_name="SnapTrade",
                external_id="cf_a2_1",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="withdrawal",
                amount=Decimal("500"),
            ),
        ])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        assert len(data) == 2

        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("1000")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("0")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("1000")

        assert Decimal(by_account[acc2.id]["total_inflows"]) == Decimal("0")
        assert Decimal(by_account[acc2.id]["total_outflows"]) == Decimal("-500")
        assert Decimal(by_account[acc2.id]["net_flow"]) == Decimal("-500")

    def test_non_cash_flow_types_appear_with_zero_totals(self, client, db, two_accounts):
        """Non-cash-flow activities are counted but don't affect flow totals."""
        acc1, acc2 = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_buy",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="buy",
                amount=Decimal("1000"),
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_sell",
                activity_date=datetime(2025, 3, 2, tzinfo=timezone.utc),
                type="sell",
                amount=Decimal("1500"),
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_div",
                activity_date=datetime(2025, 3, 3, tzinfo=timezone.utc),
                type="dividend",
                amount=Decimal("50"),
            ),
        ])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        # acc1 has activities but zero cash flow totals
        assert by_account[acc1.id]["activity_count"] == 3
        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("0")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("0")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("0")

        # acc2 has no activities at all
        assert by_account[acc2.id]["activity_count"] == 0

    def test_date_range_filtering(self, client, db, two_accounts):
        acc1, acc2 = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_jan",
                activity_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("1000"),
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_mar",
                activity_date=datetime(2025, 3, 15, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("2000"),
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_jun",
                activity_date=datetime(2025, 6, 15, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("3000"),
            ),
        ])
        db.commit()

        # Filter to Feb-Apr — only the March deposit matches
        response = client.get(
            "/api/portfolio/cashflow-summary?start_date=2025-02-01&end_date=2025-04-30"
        )
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("2000")
        assert by_account[acc1.id]["activity_count"] == 1
        # acc2 still appears with zero activities
        assert by_account[acc2.id]["activity_count"] == 0

    def test_unreviewed_count(self, client, db, two_accounts):
        acc1, _ = two_accounts

        acts = [
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id=f"cf_rev_{i}",
                activity_date=datetime(2025, 3, i + 1, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("1000"),
                is_reviewed=(i == 0),  # Only first is reviewed
            )
            for i in range(3)
        ]
        db.add_all(acts)
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert by_account[acc1.id]["activity_count"] == 3
        assert by_account[acc1.id]["unreviewed_count"] == 2

    def test_sign_convention_deposit_inflow(self, client, db, two_accounts):
        """Deposits should be counted as positive inflows."""
        acc1, _ = two_accounts

        db.add(Activity(
            account_id=acc1.id,
            provider_name="SnapTrade",
            external_id="cf_dep_sign",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="deposit",
            amount=Decimal("5000"),
        ))
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("5000")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("0")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("5000")

    def test_sign_convention_withdrawal_outflow(self, client, db, two_accounts):
        """Withdrawals should be counted as negative outflows."""
        acc1, _ = two_accounts

        db.add(Activity(
            account_id=acc1.id,
            provider_name="SnapTrade",
            external_id="cf_wdl_sign",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="withdrawal",
            amount=Decimal("2000"),
        ))
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("0")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("-2000")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("-2000")

    def test_transfer_uses_amount_sign(self, client, db, two_accounts):
        """Transfer activities use the amount sign as-is."""
        acc1, _ = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_xfer_pos",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="transfer",
                amount=Decimal("3000"),  # Positive = inflow
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_xfer_neg",
                activity_date=datetime(2025, 3, 2, tzinfo=timezone.utc),
                type="transfer",
                amount=Decimal("-1000"),  # Negative = outflow
            ),
        ])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("3000")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("-1000")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("2000")

    def test_transfer_in_out_sign_convention(self, client, db, two_accounts):
        """transfer_in is always positive inflow, transfer_out is always negative outflow."""
        acc1, _ = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="Manual",
                external_id="cf_xfer_in",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="transfer_in",
                amount=Decimal("2000"),
            ),
            Activity(
                account_id=acc1.id,
                provider_name="Manual",
                external_id="cf_xfer_out",
                activity_date=datetime(2025, 3, 2, tzinfo=timezone.utc),
                type="transfer_out",
                amount=Decimal("800"),
            ),
        ])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("2000")
        assert Decimal(by_account[acc1.id]["total_outflows"]) == Decimal("-800")
        assert Decimal(by_account[acc1.id]["net_flow"]) == Decimal("1200")

    def test_null_amount_excluded_from_totals(self, client, db, two_accounts):
        """Activities with null amount are counted but excluded from flow totals."""
        acc1, _ = two_accounts

        db.add_all([
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_null_amt",
                activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
                type="deposit",
                amount=None,
            ),
            Activity(
                account_id=acc1.id,
                provider_name="SnapTrade",
                external_id="cf_has_amt",
                activity_date=datetime(2025, 3, 2, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("1000"),
            ),
        ])
        db.commit()

        response = client.get("/api/portfolio/cashflow-summary")
        data = response.json()
        by_account = {d["account_id"]: d for d in data}

        assert by_account[acc1.id]["activity_count"] == 2  # Both counted
        assert Decimal(by_account[acc1.id]["total_inflows"]) == Decimal("1000")  # Only non-null in totals
