"""AssetClass model - user-defined investment categories."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Numeric, String
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class AssetClass(Base):
    """A user-defined asset class for portfolio categorization."""

    __tablename__ = "asset_classes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False, unique=True)  # e.g., "US Equities", "Crypto"
    target_percent = Column(Numeric(5, 2), nullable=False, default=Decimal("0.00"))
    color = Column(String(7), nullable=False, default="#3B82F6")  # Hex color, e.g., "#3B82F6"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    accounts = relationship("Account", back_populates="assigned_asset_class")
    securities = relationship("Security", back_populates="manual_asset_class")
