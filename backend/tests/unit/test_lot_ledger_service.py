"""Tests for the LotLedgerService."""

import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from models import Account, HoldingLot, LotDisposal, Security
from schemas.lot import (
    DisposalAssignment,
    DisposalReassignRequest,
    HoldingLotCreate,
    HoldingLotUpdate,
    LotBatchCreate,
    LotBatchUpdate,
)
from services.lot_ledger_service import LotLedgerService


# --- Fixtures ---


@pytest.fixture
def lot_account(db: Session) -> Account:
    """Create a test account for lot tests."""
    acc = Account(
        provider_name="SnapTrade",
        external_id="lot_ext_001",
        name="Lot Test Account",
        is_active=True,
    )
    db.add(acc)
    db.flush()
    return acc


@pytest.fixture
def lot_security(db: Session) -> Security:
    """Create a test security for lot tests."""
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


@pytest.fixture
def sample_lot(db: Session, lot_account: Account, lot_security: Security) -> HoldingLot:
    """Create a sample manual lot."""
    lot = HoldingLot(
        account_id=lot_account.id,
        security_id=lot_security.id,
        ticker="AAPL",
        acquisition_date=date(2024, 1, 15),
        cost_basis_per_unit=Decimal("150.00"),
        original_quantity=Decimal("10.00"),
        current_quantity=Decimal("10.00"),
        is_closed=False,
        source="manual",
    )
    db.add(lot)
    db.flush()
    return lot


# --- TestCreateLot ---


class TestCreateLot:
    def test_create_lot_success(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot_data = HoldingLotCreate(
            ticker="AAPL",
            acquisition_date=date(2024, 3, 1),
            cost_basis_per_unit=Decimal("170.00"),
            quantity=Decimal("5.00"),
        )
        lot = LotLedgerService.create_lot(db, lot_account.id, lot_data)

        assert lot.id is not None
        assert lot.account_id == lot_account.id
        assert lot.security_id == lot_security.id
        assert lot.ticker == "AAPL"
        assert lot.acquisition_date == date(2024, 3, 1)
        assert lot.cost_basis_per_unit == Decimal("170.00")
        assert lot.original_quantity == Decimal("5.00")
        assert lot.current_quantity == Decimal("5.00")
        assert lot.is_closed is False

    def test_create_lot_unknown_ticker(self, db: Session, lot_account: Account):
        lot_data = HoldingLotCreate(
            ticker="UNKNOWN",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("10.00"),
            quantity=Decimal("1.00"),
        )
        with pytest.raises(ValueError, match="Unknown security ticker"):
            LotLedgerService.create_lot(db, lot_account.id, lot_data)

    def test_create_lot_field_mapping(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Quantity from schema maps to both original_quantity and current_quantity."""
        lot_data = HoldingLotCreate(
            ticker="AAPL",
            acquisition_date=date(2024, 6, 15),
            cost_basis_per_unit=Decimal("200.50"),
            quantity=Decimal("25.5"),
        )
        lot = LotLedgerService.create_lot(db, lot_account.id, lot_data)

        assert lot.original_quantity == Decimal("25.5")
        assert lot.current_quantity == Decimal("25.5")

    def test_create_lot_source_is_manual(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot_data = HoldingLotCreate(
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            quantity=Decimal("1.00"),
        )
        lot = LotLedgerService.create_lot(db, lot_account.id, lot_data)
        assert lot.source == "manual"


# --- TestUpdateLot ---


class TestUpdateLot:
    def test_update_cost_basis(self, db: Session, sample_lot: HoldingLot):
        update_data = HoldingLotUpdate(cost_basis_per_unit=Decimal("160.00"))
        updated = LotLedgerService.update_lot(db, sample_lot.id, update_data)

        assert updated.cost_basis_per_unit == Decimal("160.00")
        # Other fields unchanged
        assert updated.original_quantity == Decimal("10.00")
        assert updated.current_quantity == Decimal("10.00")

    def test_update_quantity(self, db: Session, sample_lot: HoldingLot):
        update_data = HoldingLotUpdate(quantity=Decimal("15.00"))
        updated = LotLedgerService.update_lot(db, sample_lot.id, update_data)

        assert updated.original_quantity == Decimal("15.00")
        assert updated.current_quantity == Decimal("15.00")

    def test_update_quantity_with_disposals(
        self, db: Session, sample_lot: HoldingLot, lot_account: Account, lot_security: Security
    ):
        """When some quantity has been disposed, new quantity adjusts current_quantity."""
        # Simulate a disposal: 3 units disposed
        sample_lot.current_quantity = Decimal("7.00")
        db.flush()

        update_data = HoldingLotUpdate(quantity=Decimal("12.00"))
        updated = LotLedgerService.update_lot(db, sample_lot.id, update_data)

        # disposed = 10 - 7 = 3, new_current = 12 - 3 = 9
        assert updated.original_quantity == Decimal("12.00")
        assert updated.current_quantity == Decimal("9.00")
        assert updated.is_closed is False

    def test_update_quantity_below_disposed_rejected(
        self, db: Session, sample_lot: HoldingLot
    ):
        """Cannot set quantity below already-disposed amount."""
        sample_lot.current_quantity = Decimal("7.00")
        db.flush()

        # disposed = 3, trying to set quantity to 2 (< 3)
        update_data = HoldingLotUpdate(quantity=Decimal("2.00"))
        with pytest.raises(ValueError, match="cannot be less than"):
            LotLedgerService.update_lot(db, sample_lot.id, update_data)

    def test_update_activity_source_rejected(self, db: Session, lot_account: Account, lot_security: Security):
        """Activity-sourced lots cannot be edited."""
        lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            source="activity",
        )
        db.add(lot)
        db.flush()

        update_data = HoldingLotUpdate(cost_basis_per_unit=Decimal("110.00"))
        with pytest.raises(ValueError, match="Cannot edit activity-sourced"):
            LotLedgerService.update_lot(db, lot.id, update_data)

    def test_update_not_found(self, db: Session):
        update_data = HoldingLotUpdate(cost_basis_per_unit=Decimal("100.00"))
        with pytest.raises(ValueError, match="Lot not found"):
            LotLedgerService.update_lot(db, "nonexistent-id", update_data)

    def test_update_partial_fields(self, db: Session, sample_lot: HoldingLot):
        """Only provided fields are updated."""
        original_date = sample_lot.acquisition_date
        update_data = HoldingLotUpdate(
            acquisition_date=date(2024, 6, 1),
        )
        updated = LotLedgerService.update_lot(db, sample_lot.id, update_data)

        assert updated.acquisition_date == date(2024, 6, 1)
        assert updated.acquisition_date != original_date
        # Cost basis and quantity unchanged
        assert updated.cost_basis_per_unit == Decimal("150.00")
        assert updated.original_quantity == Decimal("10.00")


# --- TestDeleteLot ---


class TestDeleteLot:
    def test_delete_success(self, db: Session, sample_lot: HoldingLot):
        lot_id = sample_lot.id
        LotLedgerService.delete_lot(db, lot_id)

        assert db.query(HoldingLot).filter_by(id=lot_id).first() is None

    def test_delete_cascades_disposals(
        self, db: Session, sample_lot: HoldingLot, lot_account: Account, lot_security: Security
    ):
        """Deleting a lot cascades to its disposals."""
        disposal = LotDisposal(
            holding_lot_id=sample_lot.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2024, 6, 1),
            quantity=Decimal("2.00"),
            proceeds_per_unit=Decimal("180.00"),
            source="manual",
        )
        db.add(disposal)
        db.flush()
        disposal_id = disposal.id

        LotLedgerService.delete_lot(db, sample_lot.id)

        assert db.query(LotDisposal).filter_by(id=disposal_id).first() is None

    def test_delete_activity_source_rejected(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            source="activity",
        )
        db.add(lot)
        db.flush()

        with pytest.raises(ValueError, match="Cannot delete activity-sourced"):
            LotLedgerService.delete_lot(db, lot.id)

    def test_delete_not_found(self, db: Session):
        with pytest.raises(ValueError, match="Lot not found"):
            LotLedgerService.delete_lot(db, "nonexistent-id")

    def test_delete_inferred_allowed(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Inferred lots can be deleted."""
        lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            source="inferred",
        )
        db.add(lot)
        db.flush()
        lot_id = lot.id

        LotLedgerService.delete_lot(db, lot_id)
        assert db.query(HoldingLot).filter_by(id=lot_id).first() is None


# --- TestApplyLotBatch ---


class TestApplyLotBatch:
    def test_creates_only(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        creates = [
            LotBatchCreate(
                ticker="AAPL",
                acquisition_date=date(2024, 1, 1),
                cost_basis_per_unit=Decimal("100.00"),
                quantity=Decimal("5.00"),
            ),
            LotBatchCreate(
                ticker="AAPL",
                acquisition_date=date(2024, 3, 1),
                cost_basis_per_unit=Decimal("110.00"),
                quantity=Decimal("3.00"),
            ),
        ]
        result = LotLedgerService.apply_lot_batch(
            db, lot_account.id, lot_security.id, creates=creates
        )
        assert len(result) == 2
        assert all(lot.source == "manual" for lot in result)

    def test_updates_only(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        updates = [
            LotBatchUpdate(
                id=sample_lot.id,
                cost_basis_per_unit=Decimal("155.00"),
            ),
        ]
        result = LotLedgerService.apply_lot_batch(
            db, lot_account.id, lot_security.id, updates=updates
        )
        assert len(result) == 1
        assert result[0].cost_basis_per_unit == Decimal("155.00")

    def test_mixed_updates_and_creates(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        updates = [
            LotBatchUpdate(id=sample_lot.id, cost_basis_per_unit=Decimal("155.00")),
        ]
        creates = [
            LotBatchCreate(
                ticker="AAPL",
                acquisition_date=date(2024, 6, 1),
                cost_basis_per_unit=Decimal("200.00"),
                quantity=Decimal("2.00"),
            ),
        ]
        result = LotLedgerService.apply_lot_batch(
            db, lot_account.id, lot_security.id, updates=updates, creates=creates
        )
        assert len(result) == 2

    def test_wrong_account_rejected(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Cannot update a lot that belongs to a different account."""
        other_account = Account(
            provider_name="SimpleFIN",
            external_id="other_ext",
            name="Other Account",
            is_active=True,
        )
        db.add(other_account)
        db.flush()

        updates = [LotBatchUpdate(id=sample_lot.id)]
        with pytest.raises(ValueError, match="does not belong to account"):
            LotLedgerService.apply_lot_batch(
                db, other_account.id, lot_security.id, updates=updates
            )

    def test_wrong_security_rejected(
        self, db: Session, lot_account: Account, lot_security: Security,
        second_security: Security, sample_lot: HoldingLot
    ):
        """Cannot update a lot that belongs to a different security."""
        updates = [LotBatchUpdate(id=sample_lot.id)]
        with pytest.raises(ValueError, match="does not belong to account"):
            LotLedgerService.apply_lot_batch(
                db, lot_account.id, second_security.id, updates=updates
            )

    def test_returns_all_open_lots(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Result includes pre-existing open lots plus new ones."""
        creates = [
            LotBatchCreate(
                ticker="AAPL",
                acquisition_date=date(2024, 6, 1),
                cost_basis_per_unit=Decimal("200.00"),
                quantity=Decimal("2.00"),
            ),
        ]
        result = LotLedgerService.apply_lot_batch(
            db, lot_account.id, lot_security.id, creates=creates
        )
        # sample_lot + 1 new lot
        assert len(result) == 2


# --- TestGetLots ---


class TestGetLots:
    def test_get_lots_for_account(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        lots = LotLedgerService.get_lots_for_account(db, lot_account.id)
        assert len(lots) == 1
        assert lots[0].id == sample_lot.id

    def test_get_lots_for_security(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        lots = LotLedgerService.get_lots_for_security(
            db, lot_account.id, lot_security.id
        )
        assert len(lots) == 1
        assert lots[0].id == sample_lot.id

    def test_closed_excluded_by_default(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        closed_lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("0.00"),
            is_closed=True,
            source="manual",
        )
        db.add(closed_lot)
        db.flush()

        lots = LotLedgerService.get_lots_for_account(db, lot_account.id)
        assert len(lots) == 0

    def test_closed_included_when_requested(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        closed_lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("0.00"),
            is_closed=True,
            source="manual",
        )
        db.add(closed_lot)
        db.flush()

        lots = LotLedgerService.get_lots_for_account(
            db, lot_account.id, include_closed=True
        )
        assert len(lots) == 1

    def test_empty_result(self, db: Session, lot_account: Account):
        lots = LotLedgerService.get_lots_for_account(db, lot_account.id)
        assert lots == []

    def test_ordering_by_acquisition_date(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot_late = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 6, 1),
            cost_basis_per_unit=Decimal("200.00"),
            original_quantity=Decimal("3.00"),
            current_quantity=Decimal("3.00"),
            source="manual",
        )
        lot_early = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            source="manual",
        )
        db.add_all([lot_late, lot_early])
        db.flush()

        lots = LotLedgerService.get_lots_for_account(db, lot_account.id)
        assert lots[0].acquisition_date == date(2024, 1, 1)
        assert lots[1].acquisition_date == date(2024, 6, 1)


# --- TestLotSummary ---


class TestLotSummary:
    def test_basic_aggregation(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Summary computes lotted_quantity and total_cost_basis."""
        lot1 = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            source="manual",
        )
        lot2 = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 3, 1),
            cost_basis_per_unit=Decimal("120.00"),
            original_quantity=Decimal("5.00"),
            current_quantity=Decimal("5.00"),
            source="manual",
        )
        db.add_all([lot1, lot2])
        db.flush()

        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id
        )

        assert summary["lotted_quantity"] == Decimal("15.00")
        assert summary["lot_count"] == 2
        # total_cost_basis = (100 * 10) + (120 * 5) = 1000 + 600 = 1600
        assert summary["total_cost_basis"] == Decimal("1600.00")
        assert summary["ticker"] == "AAPL"
        assert summary["security_name"] == "Apple Inc."

    def test_with_market_price(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Unrealized gain/loss computed when market_price provided."""
        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id,
            market_price=Decimal("170.00"),
        )

        # market_value = 170 * 10 = 1700, cost_basis = 150 * 10 = 1500
        assert summary["unrealized_gain_loss"] == Decimal("200.00")

    def test_without_market_price(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Unrealized gain/loss is None when no market price."""
        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id
        )
        assert summary["unrealized_gain_loss"] is None

    def test_with_total_quantity(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Lot coverage computed when total_quantity provided."""
        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id,
            total_quantity=Decimal("20.00"),
        )

        # lotted = 10, total = 20 => coverage = 0.5
        assert summary["lot_coverage"] == Decimal("0.5")

    def test_realized_gains(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Realized gain/loss computed from disposals."""
        disposal = LotDisposal(
            holding_lot_id=sample_lot.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2024, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("180.00"),
            source="manual",
        )
        db.add(disposal)
        sample_lot.current_quantity = Decimal("7.00")
        db.flush()

        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id
        )

        # realized = (180 - 150) * 3 = 90
        assert summary["realized_gain_loss"] == Decimal("90.00")

    def test_no_lots(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Summary with no lots returns zeros."""
        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id
        )

        assert summary["lotted_quantity"] == Decimal("0")
        assert summary["lot_count"] == 0
        assert summary["total_cost_basis"] is None
        assert summary["realized_gain_loss"] == Decimal("0")

    def test_multi_security_summaries(
        self, db: Session, lot_account: Account, lot_security: Security, second_security: Security
    ):
        """Account-level summaries group by security."""
        lot_aapl = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("150.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            source="manual",
        )
        lot_goog = HoldingLot(
            account_id=lot_account.id,
            security_id=second_security.id,
            ticker="GOOG",
            acquisition_date=date(2024, 2, 1),
            cost_basis_per_unit=Decimal("140.00"),
            original_quantity=Decimal("8.00"),
            current_quantity=Decimal("8.00"),
            source="manual",
        )
        db.add_all([lot_aapl, lot_goog])
        db.flush()

        summaries = LotLedgerService.get_lot_summaries_for_account(
            db, lot_account.id
        )

        assert len(summaries) == 2
        assert lot_security.id in summaries
        assert second_security.id in summaries
        assert summaries[lot_security.id]["ticker"] == "AAPL"
        assert summaries[second_security.id]["ticker"] == "GOOG"

    def test_lot_coverage_with_zero_quantity(
        self, db: Session, lot_account: Account, lot_security: Security, sample_lot: HoldingLot
    ):
        """Lot coverage is None when total_quantity is zero."""
        summary = LotLedgerService.get_lot_summary(
            db, lot_account.id, lot_security.id,
            total_quantity=Decimal("0"),
        )
        assert summary["lot_coverage"] is None


# --- TestReassignDisposals ---


class TestReassignDisposals:
    def _create_disposal_scenario(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Helper to set up a disposal scenario with two lots."""
        lot1 = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("7.00"),  # 3 disposed
            source="manual",
        )
        lot2 = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 3, 1),
            cost_basis_per_unit=Decimal("120.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            source="manual",
        )
        db.add_all([lot1, lot2])
        db.flush()

        disposal = LotDisposal(
            holding_lot_id=lot1.id,
            account_id=lot_account.id,
            security_id=lot_security.id,
            disposal_date=date(2024, 6, 1),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("150.00"),
            source="manual",
            disposal_group_id="group_A",
        )
        db.add(disposal)
        db.flush()

        return lot1, lot2, disposal

    def test_basic_reassign(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=lot2.id, quantity=Decimal("3.00")),
            ]
        )
        new_disposals = LotLedgerService.reassign_disposals(
            db, lot_account.id, "group_A", reassign
        )

        assert len(new_disposals) == 1
        assert new_disposals[0].holding_lot_id == lot2.id
        assert new_disposals[0].quantity == Decimal("3.00")
        assert new_disposals[0].disposal_group_id != "group_A"

    def test_quantity_updates(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Lot quantities are updated after reassignment."""
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=lot2.id, quantity=Decimal("3.00")),
            ]
        )
        LotLedgerService.reassign_disposals(
            db, lot_account.id, "group_A", reassign
        )

        db.refresh(lot1)
        db.refresh(lot2)

        # lot1 should be restored: 7 + 3 = 10
        assert lot1.current_quantity == Decimal("10.00")
        # lot2 should be reduced: 10 - 3 = 7
        assert lot2.current_quantity == Decimal("7.00")

    def test_quantity_mismatch_rejected(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=lot2.id, quantity=Decimal("5.00")),
            ]
        )
        with pytest.raises(ValueError, match="does not match"):
            LotLedgerService.reassign_disposals(
                db, lot_account.id, "group_A", reassign
            )

    def test_group_not_found(self, db: Session, lot_account: Account):
        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id="any", quantity=Decimal("1.00")),
            ]
        )
        with pytest.raises(ValueError, match="No disposals found"):
            LotLedgerService.reassign_disposals(
                db, lot_account.id, "nonexistent", reassign
            )

    def test_wrong_security_rejected(
        self, db: Session, lot_account: Account, lot_security: Security, second_security: Security
    ):
        """Cannot reassign to a lot from a different security."""
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        other_lot = HoldingLot(
            account_id=lot_account.id,
            security_id=second_security.id,
            ticker="GOOG",
            acquisition_date=date(2024, 1, 1),
            cost_basis_per_unit=Decimal("100.00"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            source="manual",
        )
        db.add(other_lot)
        db.flush()

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=other_lot.id, quantity=Decimal("3.00")),
            ]
        )
        with pytest.raises(ValueError, match="does not belong to security"):
            LotLedgerService.reassign_disposals(
                db, lot_account.id, "group_A", reassign
            )

    def test_metadata_preserved(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Disposal date, proceeds, and source are preserved from original."""
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=lot2.id, quantity=Decimal("3.00")),
            ]
        )
        new_disposals = LotLedgerService.reassign_disposals(
            db, lot_account.id, "group_A", reassign
        )

        assert new_disposals[0].disposal_date == date(2024, 6, 1)
        assert new_disposals[0].proceeds_per_unit == Decimal("150.00")
        assert new_disposals[0].source == "manual"

    def test_lot_closes_on_full_disposal(
        self, db: Session, lot_account: Account, lot_security: Security
    ):
        """Lot is_closed set to True when current_quantity reaches 0."""
        lot1, lot2, disposal = self._create_disposal_scenario(
            db, lot_account, lot_security
        )

        # Create a lot with exactly 3 units
        small_lot = HoldingLot(
            account_id=lot_account.id,
            security_id=lot_security.id,
            ticker="AAPL",
            acquisition_date=date(2024, 5, 1),
            cost_basis_per_unit=Decimal("130.00"),
            original_quantity=Decimal("3.00"),
            current_quantity=Decimal("3.00"),
            source="manual",
        )
        db.add(small_lot)
        db.flush()

        reassign = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id=small_lot.id, quantity=Decimal("3.00")),
            ]
        )
        LotLedgerService.reassign_disposals(
            db, lot_account.id, "group_A", reassign
        )

        db.refresh(small_lot)
        assert small_lot.current_quantity == Decimal("0.00")
        assert small_lot.is_closed is True
