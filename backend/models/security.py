"""Security model - master ticker list."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class Security(Base):
    """A security/ticker in the master list."""

    __tablename__ = "securities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    ticker = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=True)  # Company/fund name
    manual_asset_class_id = Column(
        String(36), ForeignKey("asset_classes.id"), nullable=True
    )
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    manual_asset_class = relationship("AssetClass", back_populates="securities")
    holdings = relationship("Holding", back_populates="security")
    holding_lots = relationship("HoldingLot", back_populates="security")
