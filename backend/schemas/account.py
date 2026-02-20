"""Pydantic schemas for API request/response validation."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator
from datetime import date, datetime
from typing import Optional
from decimal import Decimal


class AccountType(str, Enum):
    """Valid account types."""

    taxable = "taxable"
    traditional_ira = "traditional_ira"
    roth_ira = "roth_ira"
    four_01k = "401k"
    roth_401k = "roth_401k"
    five_29 = "529"
    hsa = "hsa"
    charitable = "charitable"
    other = "other"


class AssetClassBase(BaseModel):
    """Base schema for AssetClass."""

    name: str
    target_percent: Decimal = Decimal("0.00")


class AssetClassCreate(BaseModel):
    """Schema for creating an AssetClass."""

    name: str
    color: str  # Hex color code, e.g., "#3B82F6"


class AssetClassUpdate(BaseModel):
    """Schema for updating an AssetClass."""

    name: Optional[str] = None
    color: Optional[str] = None
    target_percent: Optional[Decimal] = None


class AssetClassResponse(AssetClassBase):
    """Schema for AssetClass API response."""

    id: str
    color: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetClassWithCounts(AssetClassResponse):
    """Schema for AssetClass with assignment counts."""

    security_count: int
    account_count: int


class AssetClassListResponse(BaseModel):
    """Schema for list of asset classes with total."""

    items: list[AssetClassResponse]
    total_target_percent: Decimal


class AccountBase(BaseModel):
    """Base schema for Account."""

    provider_name: str
    external_id: str
    name: str
    institution_name: str | None = None


class AccountCreate(AccountBase):
    """Schema for creating an Account."""

    pass


class AccountUpdate(BaseModel):
    """Schema for updating an Account."""

    name: Optional[str] = None
    is_active: Optional[bool] = None
    assigned_asset_class_id: Optional[str] = None
    account_type: Optional[AccountType] = None
    include_in_allocation: Optional[bool] = None


class AccountResponse(AccountBase):
    """Schema for Account API response."""

    id: str
    is_active: bool
    account_type: Optional[str] = None
    include_in_allocation: bool = True
    assigned_asset_class_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Sync tracking (per-account)
    last_sync_time: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    balance_date: Optional[datetime] = None

    # Asset class details (populated from relationship)
    assigned_asset_class_name: Optional[str] = None
    assigned_asset_class_color: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AccountWithValue(AccountResponse):
    """Schema for Account with calculated total value."""

    value: Decimal | None = None


class SecurityBase(BaseModel):
    """Base schema for Security."""

    ticker: str
    name: Optional[str] = None


class SecurityCreate(SecurityBase):
    """Schema for creating a Security."""

    manual_asset_class_id: Optional[str] = None


class SecurityUpdate(BaseModel):
    """Schema for updating a Security."""

    name: Optional[str] = None
    manual_asset_class_id: Optional[str] = None


class SecurityResponse(SecurityBase):
    """Schema for Security API response."""

    id: str
    manual_asset_class_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SecurityWithTypeResponse(SecurityResponse):
    """Schema for Security with asset type information."""

    asset_type_id: Optional[str] = None
    asset_type_name: Optional[str] = None
    asset_type_color: Optional[str] = None


class UnassignedResponse(BaseModel):
    """Schema for unassigned securities response."""

    count: int
    items: list[SecurityWithTypeResponse]


class AllocationTarget(BaseModel):
    """Schema for a single allocation target."""

    asset_type_id: str
    target_percent: Decimal


class AllocationTargetUpdate(BaseModel):
    """Schema for updating portfolio allocation targets."""

    allocations: list[AllocationTarget]


class AllocationTargetResponse(BaseModel):
    """Schema for allocation target response."""

    allocations: list[AllocationTarget]
    total_percent: Decimal
    is_valid: bool  # True if sums to 100


class AssetTypeHoldingResponse(BaseModel):
    """Schema for a single holding within an asset type detail view."""

    holding_id: str
    account_id: str
    account_name: str
    ticker: str
    security_name: Optional[str] = None
    market_value: Decimal


class AssetTypeHoldingsDetail(BaseModel):
    """Schema for asset type detail with its holdings."""

    asset_type_id: str
    asset_type_name: str
    asset_type_color: str
    total_value: Decimal
    holdings: list[AssetTypeHoldingResponse]


class AllocationActual(BaseModel):
    """Schema for actual allocation data."""

    asset_type_id: str
    asset_type_name: str
    asset_type_color: str
    target_percent: Decimal
    actual_percent: Decimal
    delta_percent: Decimal
    value: Decimal


class ActivityResponse(BaseModel):
    """Schema for Activity API response (excludes raw_data)."""

    id: str
    account_id: str
    provider_name: str
    external_id: str
    activity_date: datetime
    settlement_date: Optional[datetime] = None
    type: str
    description: Optional[str] = None
    ticker: Optional[str] = None
    units: Optional[Decimal] = None
    price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    fee: Optional[Decimal] = None
    is_reviewed: bool = False
    notes: Optional[str] = None
    user_modified: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActivityCreate(BaseModel):
    """Schema for creating a manual activity."""

    activity_date: datetime
    type: str
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    ticker: Optional[str] = None
    notes: Optional[str] = None


class ActivityUpdate(BaseModel):
    """Schema for updating an activity."""

    type: Optional[str] = None
    amount: Optional[Decimal] = None
    notes: Optional[str] = None
    activity_date: Optional[datetime] = None


class BulkMarkReviewedRequest(BaseModel):
    """Schema for bulk marking activities as reviewed."""

    activity_ids: list[str]


class CashFlowAccountSummary(BaseModel):
    """Per-account cash flow summary."""

    account_id: str
    account_name: str
    total_inflows: Decimal
    total_outflows: Decimal
    net_flow: Decimal
    activity_count: int
    unreviewed_count: int


class ManualAccountCreate(BaseModel):
    """Schema for creating a manual account."""

    name: str
    institution_name: Optional[str] = None


class ManualHoldingInput(BaseModel):
    """Schema for adding/updating a holding on a manual account.

    Two modes:
    - Security mode: ticker is set (quantity/price/market_value as before)
    - Other mode: description is set with market_value (ticker auto-generated)
    """

    ticker: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    acquisition_date: Optional[date] = None
    cost_basis_per_unit: Optional[Decimal] = None

    @model_validator(mode="after")
    def validate_mode_and_market_value(self) -> "ManualHoldingInput":
        """Validate input based on mode (security vs other)."""
        has_ticker = self.ticker is not None and self.ticker.strip() != ""
        has_description = self.description is not None and self.description.strip() != ""

        if has_ticker and has_description:
            raise ValueError("Provide either ticker or description, not both")
        if not has_ticker and not has_description:
            raise ValueError("Either ticker or description is required")

        if has_description:
            # Other mode: market_value is required
            if self.market_value is None:
                raise ValueError("market_value is required for description-based holdings")
        else:
            # Security mode: quantity is required and must be > 0
            if self.quantity is None or self.quantity <= 0:
                raise ValueError(
                    "quantity is required and must be greater than zero for security holdings"
                )

            # Auto-calculate market_value from quantity * price if not provided
            if self.market_value is None:
                if self.price is not None:
                    self.market_value = self.quantity * self.price
                else:
                    raise ValueError(
                        "Either market_value or price must be provided"
                    )
        return self


class HoldingBase(BaseModel):
    """Base schema for Holding."""

    account_snapshot_id: str
    security_id: str
    ticker: str
    quantity: Decimal
    snapshot_price: Decimal
    snapshot_value: Decimal


class HoldingCreate(HoldingBase):
    """Schema for creating a Holding."""

    pass


class HoldingResponse(HoldingBase):
    """Schema for Holding API response."""

    id: str
    created_at: datetime
    security_name: str | None = None
    market_price: Decimal | None = None
    market_value: Decimal | None = None

    # Cost basis fields (populated from lot data when available)
    cost_basis: Decimal | None = None
    gain_loss: Decimal | None = None
    gain_loss_percent: Decimal | None = None
    lot_coverage: Decimal | None = None
    lot_count: int | None = None
    realized_gain_loss: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


class SyncLogEntryResponse(BaseModel):
    """Schema for SyncLogEntry API response."""

    id: str
    provider_name: str
    status: str  # "success" | "failed" | "partial"
    error_messages: Optional[list[str]] = None
    accounts_synced: int = 0
    accounts_stale: int = 0
    accounts_error: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SyncSessionBase(BaseModel):
    """Base schema for SyncSession."""

    timestamp: datetime
    is_complete: bool = False
    error_message: Optional[str] = None


class SyncSessionCreate(BaseModel):
    """Schema for creating a SyncSession."""

    pass


class SyncSessionResponse(SyncSessionBase):
    """Schema for SyncSession API response."""

    id: str
    created_at: datetime
    holdings: list[HoldingResponse] = []
    sync_log: list[SyncLogEntryResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def map_sync_log_entries(cls, data):
        """Map sync_log_entries relationship to sync_log field."""
        # Handle ORM model objects
        if hasattr(data, "sync_log_entries"):
            # Convert ORM object to dict for manipulation
            obj_dict = {}
            for key in ["id", "timestamp", "is_complete", "error_message",
                        "created_at", "holdings", "sync_log_entries"]:
                if hasattr(data, key):
                    obj_dict[key] = getattr(data, key)
            obj_dict["sync_log"] = obj_dict.pop("sync_log_entries", [])
            return obj_dict
        return data
