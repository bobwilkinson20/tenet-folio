"""Pydantic schemas for lot-based cost basis tracking."""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class HoldingLotCreate(BaseModel):
    """Schema for creating a manual holding lot."""

    ticker: str
    acquisition_date: date
    cost_basis_per_unit: Decimal
    quantity: Decimal


class HoldingLotUpdate(BaseModel):
    """Schema for updating a holding lot."""

    acquisition_date: date | None = None
    cost_basis_per_unit: Decimal | None = None
    quantity: Decimal | None = None


class LotDisposalResponse(BaseModel):
    """Schema for LotDisposal API response."""

    id: str
    holding_lot_id: str
    account_id: str
    security_id: str
    disposal_date: date
    quantity: Decimal
    proceeds_per_unit: Decimal
    realized_gain_loss: Decimal | None = None  # Computed by service layer
    source: str
    activity_id: str | None = None
    disposal_group_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HoldingLotResponse(BaseModel):
    """Schema for HoldingLot API response."""

    id: str
    account_id: str
    security_id: str
    ticker: str
    acquisition_date: date | None
    cost_basis_per_unit: Decimal
    original_quantity: Decimal
    current_quantity: Decimal
    is_closed: bool
    source: str
    activity_id: str | None = None
    created_at: datetime
    updated_at: datetime

    # Computed fields — populated by the service layer, not stored on the model
    total_cost_basis: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    unrealized_gain_loss_percent: Decimal | None = None
    security_name: str | None = None
    disposals: list[LotDisposalResponse] = []

    model_config = ConfigDict(from_attributes=True)


class DisposalAssignment(BaseModel):
    """Schema for a single lot assignment in a disposal reassignment."""

    lot_id: str
    quantity: Decimal


class DisposalReassignRequest(BaseModel):
    """Schema for reassigning a disposal group to different lots."""

    assignments: list[DisposalAssignment]


class LotBatchUpdate(BaseModel):
    """Schema for a single lot update within a batch save."""

    id: str
    acquisition_date: date | None = None
    cost_basis_per_unit: Decimal | None = None
    quantity: Decimal | None = None


class LotBatchCreate(BaseModel):
    """Schema for a single lot create within a batch save."""

    ticker: str
    acquisition_date: date
    cost_basis_per_unit: Decimal
    quantity: Decimal


class LotBatchRequest(BaseModel):
    """Schema for batch lot save (updates + creates atomically)."""

    updates: list[LotBatchUpdate] = []
    creates: list[LotBatchCreate] = []


class LotSummaryResponse(BaseModel):
    """Aggregated lot summary for a security within an account."""

    security_id: str
    ticker: str
    security_name: str | None = None
    total_quantity: Decimal | None = None
    lotted_quantity: Decimal
    lot_count: int
    total_cost_basis: Decimal | None = None
    unrealized_gain_loss: Decimal | None = None
    realized_gain_loss: Decimal
    lot_coverage: Decimal | None = None
