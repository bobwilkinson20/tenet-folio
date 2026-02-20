"""Account model - represents a linked brokerage account."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class Account(Base):
    """A linked brokerage account from a data provider.

    Accounts can come from multiple providers (SnapTrade, SimpleFIN, etc.).
    The combination of provider_name + external_id uniquely identifies an account.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider_name", "external_id", name="uix_provider_external_id"
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider_name = Column(String, nullable=False)  # e.g., "SnapTrade", "SimpleFIN"
    external_id = Column(String, nullable=False)  # Provider's account ID (unique per provider)
    name = Column(String, nullable=False)
    name_user_edited = Column(Boolean, default=False)  # True if user has customized the name
    institution_name = Column(String, nullable=True)  # Financial institution (e.g., "Vanguard")
    is_active = Column(Boolean, default=True)
    account_type = Column(String, nullable=True)
    include_in_allocation = Column(Boolean, default=True, nullable=False)
    assigned_asset_class_id = Column(
        String(36), ForeignKey("asset_classes.id"), nullable=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Sync tracking (per-account)
    last_sync_time = Column(DateTime, nullable=True)
    last_sync_status = Column(String, nullable=True)  # "success" | "failed" | "syncing"
    last_sync_error = Column(String, nullable=True)
    balance_date = Column(DateTime, nullable=True)  # Provider-reported balance date

    # Relationships
    assigned_asset_class = relationship("AssetClass", back_populates="accounts")
    account_snapshots = relationship("AccountSnapshot", back_populates="account")
    activities = relationship("Activity", back_populates="account")
    holding_lots = relationship("HoldingLot", back_populates="account")
