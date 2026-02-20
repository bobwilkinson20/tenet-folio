"""Integration tests for lot API endpoints."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Account, HoldingLot, LotDisposal, Security, generate_uuid
from tests.fixtures import get_or_create_security


@pytest.fixture
def lot_account(db: Session) -> Account:
    """Create a test account for lot tests."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="lot_ext_001",
        name="Lot Test Account",
        institution_name="Test Brokerage",
        is_active=True,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


@pytest.fixture
def lot_security(db: Session) -> Security:
    """Create a test security for lot tests."""
    return get_or_create_security(db, "AAPL", "Apple Inc.")


@pytest.fixture
def lot_security_2(db: Session) -> Security:
    """Create a second test security for lot tests."""
    return get_or_create_security(db, "GOOGL", "Alphabet Inc.")


@pytest.fixture
def manual_lot(db: Session, lot_account: Account, lot_security: Security) -> HoldingLot:
    """Create a manual lot for testing."""
    lot = HoldingLot(
        account_id=lot_account.id,
        security_id=lot_security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@pytest.fixture
def activity_lot(db: Session, lot_account: Account, lot_security: Security) -> HoldingLot:
    """Create an activity-sourced lot for testing."""
    lot = HoldingLot(
        account_id=lot_account.id,
        security_id=lot_security.id,
        ticker="AAPL",
        acquisition_date=date(2025, 2, 1),
        cost_basis_per_unit=Decimal("155.00"),
        original_quantity=Decimal("5.00"),
        current_quantity=Decimal("5.00"),
        is_closed=False,
        source="activity",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


@pytest.fixture
def closed_lot(db: Session, lot_account: Account, lot_security: Security) -> HoldingLot:
    """Create a closed lot for testing."""
    lot = HoldingLot(
        account_id=lot_account.id,
        security_id=lot_security.id,
        ticker="AAPL",
        acquisition_date=date(2024, 6, 1),
        cost_basis_per_unit=Decimal("140.00"),
        original_quantity=Decimal("8.00"),
        current_quantity=Decimal("0.00"),
        is_closed=True,
        source="manual",
    )
    db.add(lot)
    db.commit()
    db.refresh(lot)
    return lot


class TestGetAccountLots:
    """Tests for GET /{account_id}/lots."""

    def test_empty_account(self, client, lot_account):
        """Returns empty list for account with no lots."""
        response = client.get(f"/api/accounts/{lot_account.id}/lots")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_lots(self, client, lot_account, manual_lot):
        """Returns lots for the account."""
        response = client.get(f"/api/accounts/{lot_account.id}/lots")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == manual_lot.id
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["security_name"] == "Apple Inc."
        assert float(data[0]["current_quantity"]) == 10.0
        assert float(data[0]["total_cost_basis"]) == 1500.0

    def test_excludes_closed_by_default(self, client, lot_account, manual_lot, closed_lot):
        """Closed lots are excluded by default."""
        response = client.get(f"/api/accounts/{lot_account.id}/lots")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == manual_lot.id

    def test_include_closed(self, client, lot_account, manual_lot, closed_lot):
        """include_closed=true returns closed lots too."""
        response = client.get(
            f"/api/accounts/{lot_account.id}/lots?include_closed=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_account_not_found(self, client):
        """Returns 404 for unknown account."""
        response = client.get(f"/api/accounts/{generate_uuid()}/lots")
        assert response.status_code == 404

    def test_includes_disposals(self, client, db, lot_account, manual_lot, lot_security):
        """Returns disposal information with lots."""
        # Reduce current_quantity to account for disposal
        manual_lot.current_quantity = Decimal("7.00")
        db.flush()

        disposal = LotDisposal(
            holding_lot_id=manual_lot.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2025, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("175.00"),
            source="manual",
            disposal_group_id="grp_001",
        )
        db.add(disposal)
        db.commit()

        response = client.get(f"/api/accounts/{lot_account.id}/lots")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert len(data[0]["disposals"]) == 1
        d = data[0]["disposals"][0]
        assert float(d["quantity"]) == 3.0
        # realized = (175 - 150) * 3 = 75
        assert float(d["realized_gain_loss"]) == 75.0


class TestGetLotsBySecurity:
    """Tests for GET /{account_id}/lots/by-security/{security_id}."""

    def test_returns_lots(self, client, lot_account, lot_security, manual_lot):
        """Returns lots for the given security."""
        response = client.get(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == manual_lot.id

    def test_security_not_found(self, client, lot_account):
        """Returns 404 for unknown security."""
        response = client.get(
            f"/api/accounts/{lot_account.id}/lots/by-security/{generate_uuid()}"
        )
        assert response.status_code == 404

    def test_account_not_found(self, client, lot_security):
        """Returns 404 for unknown account."""
        response = client.get(
            f"/api/accounts/{generate_uuid()}/lots/by-security/{lot_security.id}"
        )
        assert response.status_code == 404

    def test_filters_by_security(
        self, client, db, lot_account, lot_security, lot_security_2, manual_lot
    ):
        """Only returns lots for the specified security."""
        other_lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security_2.id,
            ticker="GOOGL",
            acquisition_date=date(2025, 3, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            is_closed=False,
            source="manual",
        )
        db.add(other_lot)
        db.commit()

        response = client.get(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}"
        )
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"


class TestGetLotSummaries:
    """Tests for GET /{account_id}/lots/summary."""

    def test_returns_summaries(self, client, lot_account, manual_lot, lot_security):
        """Returns lot summaries grouped by security."""
        response = client.get(f"/api/accounts/{lot_account.id}/lots/summary")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["security_id"] == lot_security.id
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["lot_count"] == 1
        assert float(data[0]["lotted_quantity"]) == 10.0

    def test_empty_account(self, client, lot_account):
        """Returns empty list for account with no lots."""
        response = client.get(f"/api/accounts/{lot_account.id}/lots/summary")
        assert response.status_code == 200
        assert response.json() == []

    def test_account_not_found(self, client):
        """Returns 404 for unknown account."""
        response = client.get(f"/api/accounts/{generate_uuid()}/lots/summary")
        assert response.status_code == 404


class TestCreateLot:
    """Tests for POST /{account_id}/lots."""

    def test_create_success(self, client, lot_account, lot_security):
        """Creates a new lot."""
        response = client.post(
            f"/api/accounts/{lot_account.id}/lots",
            json={
                "ticker": "AAPL",
                "acquisition_date": "2025-03-15",
                "cost_basis_per_unit": 160.0,
                "quantity": 20.0,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ticker"] == "AAPL"
        assert float(data["current_quantity"]) == 20.0
        assert float(data["cost_basis_per_unit"]) == 160.0
        assert data["source"] == "manual"
        assert data["security_name"] == "Apple Inc."
        assert float(data["total_cost_basis"]) == 3200.0

    def test_unknown_ticker(self, client, lot_account):
        """Returns 400 for unknown ticker."""
        response = client.post(
            f"/api/accounts/{lot_account.id}/lots",
            json={
                "ticker": "FAKE",
                "acquisition_date": "2025-03-15",
                "cost_basis_per_unit": 10.0,
                "quantity": 5.0,
            },
        )
        assert response.status_code == 400
        assert "Unknown security ticker" in response.json()["detail"]

    def test_account_not_found(self, client):
        """Returns 404 for unknown account."""
        response = client.post(
            f"/api/accounts/{generate_uuid()}/lots",
            json={
                "ticker": "AAPL",
                "acquisition_date": "2025-03-15",
                "cost_basis_per_unit": 160.0,
                "quantity": 20.0,
            },
        )
        assert response.status_code == 404


class TestUpdateLot:
    """Tests for PUT /{account_id}/lots/{lot_id}."""

    def test_update_cost_basis(self, client, lot_account, manual_lot):
        """Updates the cost basis of a lot."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/{manual_lot.id}",
            json={"cost_basis_per_unit": 155.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert float(data["cost_basis_per_unit"]) == 155.0
        assert float(data["total_cost_basis"]) == 1550.0

    def test_update_quantity(self, client, lot_account, manual_lot):
        """Updates the quantity of a lot."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/{manual_lot.id}",
            json={"quantity": 15.0},
        )
        assert response.status_code == 200
        data = response.json()
        assert float(data["original_quantity"]) == 15.0
        assert float(data["current_quantity"]) == 15.0

    def test_update_acquisition_date(self, client, lot_account, manual_lot):
        """Updates the acquisition date of a lot."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/{manual_lot.id}",
            json={"acquisition_date": "2025-02-01"},
        )
        assert response.status_code == 200
        assert response.json()["acquisition_date"] == "2025-02-01"

    def test_lot_not_found(self, client, lot_account):
        """Returns 404 for unknown lot."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/{generate_uuid()}",
            json={"cost_basis_per_unit": 155.0},
        )
        assert response.status_code == 404

    def test_activity_lot_400(self, client, lot_account, activity_lot):
        """Returns 400 when trying to update an activity-sourced lot."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/{activity_lot.id}",
            json={"cost_basis_per_unit": 160.0},
        )
        assert response.status_code == 400
        assert "Cannot edit activity-sourced lots" in response.json()["detail"]

    def test_lot_wrong_account(self, client, db, manual_lot):
        """Returns 404 when lot belongs to a different account."""
        other_account = Account(
            provider_name="SnapTrade",
            external_id="other_ext",
            name="Other Account",
            is_active=True,
        )
        db.add(other_account)
        db.commit()

        response = client.put(
            f"/api/accounts/{other_account.id}/lots/{manual_lot.id}",
            json={"cost_basis_per_unit": 155.0},
        )
        assert response.status_code == 404


class TestDeleteLot:
    """Tests for DELETE /{account_id}/lots/{lot_id}."""

    def test_delete_success(self, client, db, lot_account, manual_lot):
        """Deletes a manual lot."""
        response = client.delete(
            f"/api/accounts/{lot_account.id}/lots/{manual_lot.id}"
        )
        assert response.status_code == 204

        # Verify lot is gone
        lot = db.query(HoldingLot).filter_by(id=manual_lot.id).first()
        assert lot is None

    def test_lot_not_found(self, client, lot_account):
        """Returns 404 for unknown lot."""
        response = client.delete(
            f"/api/accounts/{lot_account.id}/lots/{generate_uuid()}"
        )
        assert response.status_code == 404

    def test_activity_lot_400(self, client, lot_account, activity_lot):
        """Returns 400 when trying to delete an activity-sourced lot."""
        response = client.delete(
            f"/api/accounts/{lot_account.id}/lots/{activity_lot.id}"
        )
        assert response.status_code == 400
        assert "Cannot delete activity-sourced lots" in response.json()["detail"]

    def test_lot_wrong_account(self, client, db, manual_lot):
        """Returns 404 when lot belongs to a different account."""
        other_account = Account(
            provider_name="SnapTrade",
            external_id="other_ext_2",
            name="Other Account 2",
            is_active=True,
        )
        db.add(other_account)
        db.commit()

        response = client.delete(
            f"/api/accounts/{other_account.id}/lots/{manual_lot.id}"
        )
        assert response.status_code == 404


class TestAccountDeleteCascade:
    """Tests for account deletion cascading to lots and disposals."""

    def test_cascade_deletes_lots_and_disposals(
        self, client, db, lot_account, manual_lot, lot_security
    ):
        """Deleting an account removes its lots and disposals."""
        # Reduce current_quantity for disposal
        manual_lot.current_quantity = Decimal("7.00")
        db.flush()

        disposal = LotDisposal(
            holding_lot_id=manual_lot.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2025, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("175.00"),
            source="manual",
        )
        db.add(disposal)
        db.commit()

        lot_id = manual_lot.id
        disposal_id = disposal.id

        response = client.delete(f"/api/accounts/{lot_account.id}")
        assert response.status_code == 204

        assert db.query(HoldingLot).filter_by(id=lot_id).first() is None
        assert db.query(LotDisposal).filter_by(id=disposal_id).first() is None


class TestReassignDisposals:
    """Tests for PUT /{account_id}/lots/disposals/{group_id}/reassign."""

    def test_basic_reassign(self, client, db, lot_account, lot_security):
        """Reassigns disposals from one lot to another."""
        # Create two lots
        lot_a = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2025, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("7.00"),
            is_closed=False,
            source="manual",
        )
        lot_b = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2025, 2, 1),
            cost_basis_per_unit=Decimal("110.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            is_closed=False,
            source="manual",
        )
        db.add_all([lot_a, lot_b])
        db.flush()

        group_id = generate_uuid()
        disposal = LotDisposal(
            holding_lot_id=lot_a.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2025, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("150.00"),
            source="manual",
            disposal_group_id=group_id,
        )
        db.add(disposal)
        db.commit()

        # Reassign from lot_a to lot_b
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/disposals/{group_id}/reassign",
            json={
                "assignments": [
                    {"lot_id": lot_b.id, "quantity": 3.0},
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["holding_lot_id"] == lot_b.id
        assert float(data[0]["quantity"]) == 3.0
        # realized = (150 - 110) * 3 = 120
        assert float(data[0]["realized_gain_loss"]) == 120.0

    def test_wrong_quantity(self, client, db, lot_account, lot_security):
        """Returns 400 when reassignment quantity doesn't match."""
        lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2025, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("7.00"),
            is_closed=False,
            source="manual",
        )
        db.add(lot)
        db.flush()

        group_id = generate_uuid()
        disposal = LotDisposal(
            holding_lot_id=lot.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2025, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("150.00"),
            source="manual",
            disposal_group_id=group_id,
        )
        db.add(disposal)
        db.commit()

        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/disposals/{group_id}/reassign",
            json={
                "assignments": [
                    {"lot_id": lot.id, "quantity": 5.0},
                ],
            },
        )
        assert response.status_code == 400
        assert "does not match" in response.json()["detail"]

    def test_group_not_found(self, client, lot_account):
        """Returns 400 when disposal group doesn't exist."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/disposals/{generate_uuid()}/reassign",
            json={
                "assignments": [
                    {"lot_id": generate_uuid(), "quantity": 1.0},
                ],
            },
        )
        assert response.status_code == 400
        assert "No disposals found" in response.json()["detail"]

    def test_account_not_found(self, client):
        """Returns 404 for unknown account."""
        response = client.put(
            f"/api/accounts/{generate_uuid()}/lots/disposals/{generate_uuid()}/reassign",
            json={
                "assignments": [
                    {"lot_id": generate_uuid(), "quantity": 1.0},
                ],
            },
        )
        assert response.status_code == 404


class TestLotBatchEndpoint:
    """Tests for PUT /{account_id}/lots/by-security/{security_id}/batch."""

    def test_batch_create(self, client, lot_account, lot_security):
        """Creates lots via batch endpoint."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}/batch",
            json={
                "updates": [],
                "creates": [
                    {
                        "ticker": "AAPL",
                        "acquisition_date": "2025-04-01",
                        "cost_basis_per_unit": 170.0,
                        "quantity": 15.0,
                    },
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["ticker"] == "AAPL"
        assert float(data[0]["current_quantity"]) == 15.0

    def test_batch_update(self, client, db, lot_account, lot_security, manual_lot):
        """Updates lots via batch endpoint."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}/batch",
            json={
                "updates": [
                    {
                        "id": manual_lot.id,
                        "cost_basis_per_unit": 155.0,
                    },
                ],
                "creates": [],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert float(data[0]["cost_basis_per_unit"]) == 155.0

    def test_batch_create_and_update(
        self, client, lot_account, lot_security, manual_lot
    ):
        """Batch creates and updates lots atomically."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}/batch",
            json={
                "updates": [
                    {
                        "id": manual_lot.id,
                        "cost_basis_per_unit": 155.0,
                    },
                ],
                "creates": [
                    {
                        "ticker": "AAPL",
                        "acquisition_date": "2025-05-01",
                        "cost_basis_per_unit": 180.0,
                        "quantity": 5.0,
                    },
                ],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_account_not_found(self, client, lot_security):
        """Returns 404 for unknown account."""
        response = client.put(
            f"/api/accounts/{generate_uuid()}/lots/by-security/{lot_security.id}/batch",
            json={"updates": [], "creates": []},
        )
        assert response.status_code == 404

    def test_security_not_found(self, client, lot_account):
        """Returns 404 for unknown security."""
        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/by-security/{generate_uuid()}/batch",
            json={"updates": [], "creates": []},
        )
        assert response.status_code == 404

    def test_batch_update_wrong_lot(self, client, db, lot_account, lot_security):
        """Returns 400 when updating a lot that doesn't belong to the account/security."""
        other_account = Account(
            provider_name="SnapTrade",
            external_id="batch_other",
            name="Other",
            is_active=True,
        )
        db.add(other_account)
        db.flush()
        other_lot = HoldingLot(
            account_id=other_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2025, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            is_closed=False,
            source="manual",
        )
        db.add(other_lot)
        db.commit()

        response = client.put(
            f"/api/accounts/{lot_account.id}/lots/by-security/{lot_security.id}/batch",
            json={
                "updates": [
                    {"id": other_lot.id, "cost_basis_per_unit": 110.0},
                ],
                "creates": [],
            },
        )
        assert response.status_code == 400
        assert "does not belong" in response.json()["detail"]
