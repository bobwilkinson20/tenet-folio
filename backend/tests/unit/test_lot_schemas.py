"""Unit tests for lot-based cost basis Pydantic schemas."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.lot import (
    DisposalAssignment,
    DisposalReassignRequest,
    HoldingLotCreate,
    HoldingLotResponse,
    HoldingLotUpdate,
    LotBatchCreate,
    LotBatchRequest,
    LotBatchUpdate,
    LotDisposalResponse,
    LotSummaryResponse,
)


# --- HoldingLotCreate ---


class TestHoldingLotCreate:
    def test_valid_create(self):
        schema = HoldingLotCreate(
            ticker="AAPL",
            acquisition_date=date(2025, 1, 15),
            cost_basis_per_unit=Decimal("150.50"),
            quantity=Decimal("10.00"),
        )
        assert schema.ticker == "AAPL"
        assert schema.acquisition_date == date(2025, 1, 15)
        assert schema.cost_basis_per_unit == Decimal("150.50")
        assert schema.quantity == Decimal("10.00")

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            HoldingLotCreate(
                ticker="AAPL",
                acquisition_date=date(2025, 1, 15),
                cost_basis_per_unit=Decimal("150.50"),
                # quantity missing
            )


# --- HoldingLotUpdate ---


class TestHoldingLotUpdate:
    def test_all_fields_optional(self):
        schema = HoldingLotUpdate()
        assert schema.acquisition_date is None
        assert schema.cost_basis_per_unit is None
        assert schema.quantity is None

    def test_partial_update(self):
        schema = HoldingLotUpdate(cost_basis_per_unit=Decimal("200.00"))
        assert schema.cost_basis_per_unit == Decimal("200.00")
        assert schema.quantity is None


# --- HoldingLotResponse ---


class TestHoldingLotResponse:
    def test_from_attributes(self):
        now = datetime.now(timezone.utc)
        schema = HoldingLotResponse(
            id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            ticker="AAPL",
            acquisition_date=date(2025, 1, 15),
            cost_basis_per_unit=Decimal("150.50"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("7.00"),
            is_closed=False,
            source="activity",
            created_at=now,
            updated_at=now,
        )
        assert schema.ticker == "AAPL"
        assert schema.disposals == []
        assert schema.total_cost_basis is None
        assert schema.unrealized_gain_loss is None
        assert schema.security_name is None

    def test_with_computed_fields(self):
        now = datetime.now(timezone.utc)
        schema = HoldingLotResponse(
            id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            ticker="AAPL",
            acquisition_date=None,
            cost_basis_per_unit=Decimal("150.50"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("10.00"),
            is_closed=False,
            source="inferred",
            created_at=now,
            updated_at=now,
            total_cost_basis=Decimal("1505.00"),
            unrealized_gain_loss=Decimal("245.00"),
            unrealized_gain_loss_percent=Decimal("16.28"),
            security_name="Apple Inc.",
        )
        assert schema.acquisition_date is None
        assert schema.total_cost_basis == Decimal("1505.00")
        assert schema.security_name == "Apple Inc."

    def test_with_disposals(self):
        now = datetime.now(timezone.utc)
        disposal = LotDisposalResponse(
            id="disp-1",
            holding_lot_id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            disposal_date=date(2025, 6, 15),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("175.25"),
            source="activity",
            created_at=now,
        )
        schema = HoldingLotResponse(
            id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            ticker="AAPL",
            acquisition_date=date(2025, 1, 15),
            cost_basis_per_unit=Decimal("150.50"),
            original_quantity=Decimal("10.00"),
            current_quantity=Decimal("7.00"),
            is_closed=False,
            source="activity",
            created_at=now,
            updated_at=now,
            disposals=[disposal],
        )
        assert len(schema.disposals) == 1
        assert schema.disposals[0].quantity == Decimal("3.00")


# --- LotDisposalResponse ---


class TestLotDisposalResponse:
    def test_valid_response(self):
        now = datetime.now(timezone.utc)
        schema = LotDisposalResponse(
            id="disp-1",
            holding_lot_id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            disposal_date=date(2025, 6, 15),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("175.25"),
            realized_gain_loss=Decimal("74.25"),
            source="activity",
            disposal_group_id="group-1",
            created_at=now,
        )
        assert schema.realized_gain_loss == Decimal("74.25")
        assert schema.disposal_group_id == "group-1"

    def test_nullable_fields(self):
        now = datetime.now(timezone.utc)
        schema = LotDisposalResponse(
            id="disp-1",
            holding_lot_id="lot-1",
            account_id="acc-1",
            security_id="sec-1",
            disposal_date=date(2025, 6, 15),
            quantity=Decimal("3.00"),
            proceeds_per_unit=Decimal("175.25"),
            source="manual",
            created_at=now,
        )
        assert schema.realized_gain_loss is None
        assert schema.activity_id is None
        assert schema.disposal_group_id is None


# --- DisposalReassignRequest ---


class TestDisposalReassignRequest:
    def test_valid_request(self):
        schema = DisposalReassignRequest(
            assignments=[
                DisposalAssignment(lot_id="lot-1", quantity=Decimal("5.00")),
                DisposalAssignment(lot_id="lot-2", quantity=Decimal("3.00")),
            ]
        )
        assert len(schema.assignments) == 2
        assert schema.assignments[0].lot_id == "lot-1"

    def test_empty_assignments(self):
        schema = DisposalReassignRequest(assignments=[])
        assert schema.assignments == []


# --- LotBatchRequest ---


class TestLotBatchRequest:
    def test_valid_batch(self):
        schema = LotBatchRequest(
            updates=[
                LotBatchUpdate(id="lot-1", cost_basis_per_unit=Decimal("200.00")),
            ],
            creates=[
                LotBatchCreate(
                    ticker="GOOG",
                    acquisition_date=date(2025, 3, 1),
                    cost_basis_per_unit=Decimal("140.00"),
                    quantity=Decimal("5.00"),
                ),
            ],
        )
        assert len(schema.updates) == 1
        assert len(schema.creates) == 1

    def test_defaults_to_empty_lists(self):
        schema = LotBatchRequest()
        assert schema.updates == []
        assert schema.creates == []


# --- LotSummaryResponse ---


class TestLotSummaryResponse:
    def test_valid_summary(self):
        schema = LotSummaryResponse(
            security_id="sec-1",
            ticker="AAPL",
            security_name="Apple Inc.",
            total_quantity=Decimal("50.00"),
            lotted_quantity=Decimal("45.00"),
            lot_count=3,
            total_cost_basis=Decimal("6750.00"),
            unrealized_gain_loss=Decimal("1000.00"),
            realized_gain_loss=Decimal("500.00"),
            lot_coverage=Decimal("0.90"),
        )
        assert schema.lot_count == 3
        assert schema.total_quantity == Decimal("50.00")
        assert schema.lot_coverage == Decimal("0.90")

    def test_nullable_fields(self):
        schema = LotSummaryResponse(
            security_id="sec-1",
            ticker="AAPL",
            lotted_quantity=Decimal("0"),
            lot_count=0,
            realized_gain_loss=Decimal("0"),
        )
        assert schema.security_name is None
        assert schema.total_quantity is None
        assert schema.total_cost_basis is None
        assert schema.unrealized_gain_loss is None
        assert schema.lot_coverage is None
