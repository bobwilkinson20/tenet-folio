"""Integration tests for the activities API endpoint."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Account, HoldingLot, Security
from models.activity import Activity


@pytest.fixture
def account_with_activities(db: Session):
    """Create an account with multiple activities for testing."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="ext_api_test",
        name="API Test Account",
        institution_name="Test Brokerage",
        is_active=True,
    )
    db.add(acc)
    db.flush()

    activities = [
        Activity(
            account_id=acc.id,
            provider_name="SnapTrade",
            external_id=f"act_{i:03d}",
            activity_date=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
            type=act_type,
            description=f"Activity {i}",
            ticker="AAPL" if act_type in ("buy", "sell") else None,
            amount=Decimal(f"{(i + 1) * 100}"),
            currency="USD",
        )
        for i, act_type in enumerate(
            ["buy", "sell", "dividend", "buy", "transfer", "deposit"]
        )
    ]
    db.add_all(activities)
    db.commit()
    db.refresh(acc)
    return acc


class TestGetAccountActivities:
    """Tests for GET /api/accounts/{id}/activities."""

    def test_returns_activities(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6

    def test_ordered_by_date_desc(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities"
        )
        data = response.json()
        dates = [d["activity_date"] for d in data]
        assert dates == sorted(dates, reverse=True)

    def test_pagination_limit(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?limit=2"
        )
        data = response.json()
        assert len(data) == 2

    def test_pagination_offset(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?limit=2&offset=4"
        )
        data = response.json()
        assert len(data) == 2

    def test_type_filter(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?activity_type=buy"
        )
        data = response.json()
        assert len(data) == 2
        assert all(d["type"] == "buy" for d in data)

    def test_type_filter_no_match(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?activity_type=fee"
        )
        data = response.json()
        assert len(data) == 0

    def test_404_for_nonexistent_account(self, client):
        response = client.get(
            "/api/accounts/nonexistent-id/activities"
        )
        assert response.status_code == 404

    def test_empty_account_returns_empty_list(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_empty",
            name="Empty Account",
            is_active=True,
        )
        db.add(acc)
        db.commit()

        response = client.get(f"/api/accounts/{acc.id}/activities")
        assert response.status_code == 200
        assert response.json() == []

    def test_excludes_raw_data_from_response(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_raw",
            name="Raw Data Account",
            is_active=True,
        )
        db.add(acc)
        db.flush()

        act = Activity(
            account_id=acc.id,
            provider_name="SnapTrade",
            external_id="act_raw",
            activity_date=datetime(2025, 1, 15, tzinfo=timezone.utc),
            type="buy",
            raw_data='{"secret": "data"}',
        )
        db.add(act)
        db.commit()

        response = client.get(f"/api/accounts/{acc.id}/activities")
        data = response.json()
        assert len(data) == 1
        assert "raw_data" not in data[0]

    def test_response_schema_fields(self, client, db, account_with_activities):
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?limit=1"
        )
        data = response.json()
        assert len(data) == 1
        item = data[0]

        # Verify expected fields are present
        expected_fields = {
            "id", "account_id", "provider_name", "external_id",
            "activity_date", "settlement_date", "type", "description",
            "ticker", "units", "price", "amount", "currency", "fee",
            "is_reviewed", "notes", "user_modified",
            "created_at",
        }
        assert set(item.keys()) == expected_fields

    def test_filter_reviewed_true(self, client, db, account_with_activities):
        """Filter to only reviewed activities."""
        # Mark one activity as reviewed
        act = db.query(Activity).filter(
            Activity.account_id == account_with_activities.id
        ).first()
        act.is_reviewed = True
        db.commit()

        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?reviewed=true"
        )
        data = response.json()
        assert len(data) == 1
        assert data[0]["is_reviewed"] is True

    def test_filter_reviewed_false(self, client, db, account_with_activities):
        """Filter to only unreviewed activities."""
        # Mark one as reviewed so we can verify the filter excludes it
        act = db.query(Activity).filter(
            Activity.account_id == account_with_activities.id
        ).first()
        act.is_reviewed = True
        db.commit()

        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?reviewed=false"
        )
        data = response.json()
        assert len(data) == 5
        assert all(d["is_reviewed"] is False for d in data)

    def test_filter_start_date(self, client, db, account_with_activities):
        """Filter activities on or after start_date."""
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?start_date=2025-01-04"
        )
        data = response.json()
        # Activities on Jan 4, 5, 6
        assert len(data) == 3

    def test_filter_end_date(self, client, db, account_with_activities):
        """Filter activities on or before end_date."""
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities?end_date=2025-01-03"
        )
        data = response.json()
        # Activities on Jan 1, 2, 3
        assert len(data) == 3

    def test_filter_date_range(self, client, db, account_with_activities):
        """Filter activities within a date range."""
        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities"
            "?start_date=2025-01-02&end_date=2025-01-04"
        )
        data = response.json()
        # Activities on Jan 2, 3, 4
        assert len(data) == 3

    def test_filter_combined_type_and_reviewed(self, client, db, account_with_activities):
        """Combine type filter with reviewed filter."""
        # Mark one buy as reviewed
        buys = db.query(Activity).filter(
            Activity.account_id == account_with_activities.id,
            Activity.type == "buy",
        ).all()
        buys[0].is_reviewed = True
        db.commit()

        response = client.get(
            f"/api/accounts/{account_with_activities.id}/activities"
            "?activity_type=buy&reviewed=false"
        )
        data = response.json()
        assert len(data) == 1
        assert data[0]["type"] == "buy"
        assert data[0]["is_reviewed"] is False


class TestCreateActivity:
    """Tests for POST /api/accounts/{id}/activities."""

    def test_create_with_all_fields(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_create",
            name="Create Test",
            is_active=True,
        )
        db.add(acc)
        db.commit()

        response = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={
                "activity_date": "2025-06-15T12:00:00Z",
                "type": "deposit",
                "amount": "5000.00",
                "description": "Wire transfer",
                "ticker": None,
                "notes": "Monthly contribution",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "deposit"
        assert Decimal(data["amount"]) == Decimal("5000.00")
        assert data["description"] == "Wire transfer"
        assert data["notes"] == "Monthly contribution"
        assert data["provider_name"] == "Manual"
        assert data["user_modified"] is True
        assert data["external_id"].startswith("manual_")

    def test_create_minimal_fields(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_create_min",
            name="Minimal Test",
            is_active=True,
        )
        db.add(acc)
        db.commit()

        response = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={
                "activity_date": "2025-06-15T12:00:00Z",
                "type": "withdrawal",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "withdrawal"
        assert data["amount"] is None
        assert data["description"] is None
        assert data["notes"] is None

    def test_create_404_for_missing_account(self, client):
        response = client.post(
            "/api/accounts/nonexistent-id/activities",
            json={
                "activity_date": "2025-06-15T12:00:00Z",
                "type": "deposit",
            },
        )
        assert response.status_code == 404

    def test_create_422_for_missing_required_fields(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_create_422",
            name="422 Test",
            is_active=True,
        )
        db.add(acc)
        db.commit()

        # Missing type
        response = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={"activity_date": "2025-06-15T12:00:00Z"},
        )
        assert response.status_code == 422

        # Missing activity_date
        response = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={"type": "deposit"},
        )
        assert response.status_code == 422

    def test_create_sets_unique_external_id(self, client, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_create_eid",
            name="External ID Test",
            is_active=True,
        )
        db.add(acc)
        db.commit()

        r1 = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={"activity_date": "2025-06-15T12:00:00Z", "type": "deposit"},
        )
        r2 = client.post(
            f"/api/accounts/{acc.id}/activities",
            json={"activity_date": "2025-06-16T12:00:00Z", "type": "deposit"},
        )
        assert r1.json()["external_id"] != r2.json()["external_id"]


class TestUpdateActivity:
    """Tests for PATCH /api/accounts/{id}/activities/{activity_id}."""

    @pytest.fixture
    def account_and_activity(self, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_update",
            name="Update Test",
            is_active=True,
        )
        db.add(acc)
        db.flush()
        act = Activity(
            account_id=acc.id,
            provider_name="SnapTrade",
            external_id="act_upd_001",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="transfer",
            amount=Decimal("1000"),
        )
        db.add(act)
        db.commit()
        return acc, act

    def test_update_type_sets_user_modified(self, client, db, account_and_activity):
        acc, act = account_and_activity
        response = client.patch(
            f"/api/accounts/{acc.id}/activities/{act.id}",
            json={"type": "deposit"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "deposit"
        assert data["user_modified"] is True

    def test_update_amount_sets_user_modified(self, client, db, account_and_activity):
        acc, act = account_and_activity
        response = client.patch(
            f"/api/accounts/{acc.id}/activities/{act.id}",
            json={"amount": "2000.00"},
        )
        assert response.status_code == 200
        data = response.json()
        assert Decimal(data["amount"]) == Decimal("2000.00")
        assert data["user_modified"] is True

    def test_update_notes_only_does_not_set_user_modified(self, client, db, account_and_activity):
        acc, act = account_and_activity
        response = client.patch(
            f"/api/accounts/{acc.id}/activities/{act.id}",
            json={"notes": "Just a note"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Just a note"
        assert data["user_modified"] is False

    def test_update_404_for_missing_activity(self, client, db, account_and_activity):
        acc, _ = account_and_activity
        response = client.patch(
            f"/api/accounts/{acc.id}/activities/nonexistent-id",
            json={"notes": "test"},
        )
        assert response.status_code == 404

    def test_update_404_for_wrong_account(self, client, db, account_and_activity):
        _, act = account_and_activity
        other_acc = Account(
            provider_name="SnapTrade",
            external_id="ext_other",
            name="Other Account",
            is_active=True,
        )
        db.add(other_acc)
        db.commit()

        response = client.patch(
            f"/api/accounts/{other_acc.id}/activities/{act.id}",
            json={"notes": "test"},
        )
        assert response.status_code == 404

    def test_update_activity_date_on_manual_activity(self, client, db):
        """Updating activity_date on a manual activity succeeds."""
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_date_manual",
            name="Date Manual Test",
            is_active=True,
        )
        db.add(acc)
        db.flush()
        act = Activity(
            account_id=acc.id,
            provider_name="Manual",
            external_id="manual_date_001",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="deposit",
            amount=Decimal("500"),
        )
        db.add(act)
        db.commit()

        response = client.patch(
            f"/api/accounts/{acc.id}/activities/{act.id}",
            json={"activity_date": "2025-04-15T00:00:00Z"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "2025-04-15" in data["activity_date"]
        assert data["user_modified"] is True

    def test_update_activity_date_on_synced_activity_returns_400(
        self, client, db, account_and_activity
    ):
        """Updating activity_date on a synced activity returns 400."""
        acc, act = account_and_activity
        response = client.patch(
            f"/api/accounts/{acc.id}/activities/{act.id}",
            json={"activity_date": "2025-04-15T00:00:00Z"},
        )
        assert response.status_code == 400
        assert "synced" in response.json()["detail"].lower()


class TestDeleteActivity:
    """Tests for DELETE /api/accounts/{id}/activities/{activity_id}."""

    @pytest.fixture
    def account_with_manual_activity(self, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_del",
            name="Delete Test",
            is_active=True,
        )
        db.add(acc)
        db.flush()
        manual_act = Activity(
            account_id=acc.id,
            provider_name="Manual",
            external_id="manual_del_001",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="deposit",
            amount=Decimal("1000"),
        )
        synced_act = Activity(
            account_id=acc.id,
            provider_name="SnapTrade",
            external_id="synced_del_001",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="buy",
            amount=Decimal("500"),
        )
        db.add_all([manual_act, synced_act])
        db.commit()
        return acc, manual_act, synced_act

    def test_delete_manual_activity(self, client, db, account_with_manual_activity):
        acc, manual_act, _ = account_with_manual_activity
        response = client.delete(
            f"/api/accounts/{acc.id}/activities/{manual_act.id}"
        )
        assert response.status_code == 204

    def test_delete_synced_activity_returns_400(
        self, client, db, account_with_manual_activity
    ):
        acc, _, synced_act = account_with_manual_activity
        response = client.delete(
            f"/api/accounts/{acc.id}/activities/{synced_act.id}"
        )
        assert response.status_code == 400
        assert "manual" in response.json()["detail"].lower()

    def test_delete_nonexistent_activity_returns_404(
        self, client, db, account_with_manual_activity
    ):
        acc, _, _ = account_with_manual_activity
        response = client.delete(
            f"/api/accounts/{acc.id}/activities/nonexistent-id"
        )
        assert response.status_code == 404

    def test_delete_wrong_account_returns_404(
        self, client, db, account_with_manual_activity
    ):
        _, manual_act, _ = account_with_manual_activity
        other_acc = Account(
            provider_name="SnapTrade",
            external_id="ext_del_other",
            name="Other Delete Test",
            is_active=True,
        )
        db.add(other_acc)
        db.commit()

        response = client.delete(
            f"/api/accounts/{other_acc.id}/activities/{manual_act.id}"
        )
        assert response.status_code == 404

    def test_activity_gone_after_delete(self, client, db, account_with_manual_activity):
        acc, manual_act, _ = account_with_manual_activity
        act_id = manual_act.id

        client.delete(f"/api/accounts/{acc.id}/activities/{act_id}")

        remaining = db.query(Activity).filter(Activity.id == act_id).first()
        assert remaining is None

    def test_delete_nullifies_lot_fk_references(self, client, db):
        """Deleting an activity nullifies FK references in holding_lots."""
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_del_fk",
            name="FK Test",
            is_active=True,
        )
        db.add(acc)
        db.flush()

        sec = Security(ticker="AAPL", name="Apple")
        db.add(sec)
        db.flush()

        act = Activity(
            account_id=acc.id,
            provider_name="Manual",
            external_id="manual_fk_001",
            activity_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
            type="buy",
            amount=Decimal("1000"),
        )
        db.add(act)
        db.flush()

        lot = HoldingLot(
            account_id=acc.id,
            security_id=sec.id,
            ticker="AAPL",
            acquisition_date=datetime(2025, 3, 1, tzinfo=timezone.utc).date(),
            cost_basis_per_unit=Decimal("150"),
            original_quantity=Decimal("10"),
            current_quantity=Decimal("10"),
            source="activity",
            activity_id=act.id,
        )
        db.add(lot)
        db.commit()
        lot_id = lot.id

        response = client.delete(f"/api/accounts/{acc.id}/activities/{act.id}")
        assert response.status_code == 204

        db.expire_all()
        lot = db.query(HoldingLot).filter(HoldingLot.id == lot_id).first()
        assert lot is not None
        assert lot.activity_id is None


class TestMarkReviewed:
    """Tests for POST /api/accounts/{id}/activities/mark-reviewed."""

    @pytest.fixture
    def account_with_unreviewed(self, db):
        acc = Account(
            provider_name="SnapTrade",
            external_id="ext_review",
            name="Review Test",
            is_active=True,
        )
        db.add(acc)
        db.flush()

        acts = []
        for i in range(3):
            act = Activity(
                account_id=acc.id,
                provider_name="SnapTrade",
                external_id=f"act_rev_{i:03d}",
                activity_date=datetime(2025, 2, i + 1, tzinfo=timezone.utc),
                type="deposit",
                amount=Decimal("100"),
            )
            acts.append(act)
        db.add_all(acts)
        db.commit()
        for act in acts:
            db.refresh(act)
        return acc, acts

    def test_marks_multiple(self, client, db, account_with_unreviewed):
        acc, acts = account_with_unreviewed
        ids = [a.id for a in acts[:2]]
        response = client.post(
            f"/api/accounts/{acc.id}/activities/mark-reviewed",
            json={"activity_ids": ids},
        )
        assert response.status_code == 200
        assert response.json()["updated_count"] == 2

        # Verify in DB
        reviewed = db.query(Activity).filter(
            Activity.id.in_(ids)
        ).all()
        assert all(a.is_reviewed for a in reviewed)

    def test_idempotent(self, client, db, account_with_unreviewed):
        acc, acts = account_with_unreviewed
        ids = [acts[0].id]

        # First call
        r1 = client.post(
            f"/api/accounts/{acc.id}/activities/mark-reviewed",
            json={"activity_ids": ids},
        )
        assert r1.json()["updated_count"] == 1

        # Second call — already reviewed
        r2 = client.post(
            f"/api/accounts/{acc.id}/activities/mark-reviewed",
            json={"activity_ids": ids},
        )
        assert r2.json()["updated_count"] == 0

    def test_ignores_other_account_ids(self, client, db, account_with_unreviewed):
        acc, acts = account_with_unreviewed

        other_acc = Account(
            provider_name="SnapTrade",
            external_id="ext_review_other",
            name="Other Review",
            is_active=True,
        )
        db.add(other_acc)
        db.flush()
        other_act = Activity(
            account_id=other_acc.id,
            provider_name="SnapTrade",
            external_id="act_other_rev",
            activity_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
            type="deposit",
            amount=Decimal("100"),
        )
        db.add(other_act)
        db.commit()

        # Try to mark the other account's activity via this account's endpoint
        response = client.post(
            f"/api/accounts/{acc.id}/activities/mark-reviewed",
            json={"activity_ids": [other_act.id]},
        )
        assert response.json()["updated_count"] == 0

        # The other activity should still be unreviewed
        db.refresh(other_act)
        assert other_act.is_reviewed is False

    def test_empty_list(self, client, db, account_with_unreviewed):
        acc, _ = account_with_unreviewed
        response = client.post(
            f"/api/accounts/{acc.id}/activities/mark-reviewed",
            json={"activity_ids": []},
        )
        assert response.status_code == 200
        assert response.json()["updated_count"] == 0

    def test_404_for_missing_account(self, client):
        response = client.post(
            "/api/accounts/nonexistent-id/activities/mark-reviewed",
            json={"activity_ids": ["some-id"]},
        )
        assert response.status_code == 404
