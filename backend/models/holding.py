"""Holding model - links account snapshot and security."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class Holding(Base):
    """A holding record within an account snapshot."""

    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint(
            "account_snapshot_id", "security_id",
            name="uix_holding_snapshot_security",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_snapshot_id = Column(
        String(36), ForeignKey("account_snapshots.id"), nullable=False, index=True
    )
    security_id = Column(
        String(36), ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ticker = Column(String, nullable=False)  # Kept for convenience/fallback
    quantity = Column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    snapshot_price = Column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    snapshot_value = Column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account_snapshot = relationship("AccountSnapshot", back_populates="holdings")
    security = relationship("Security", back_populates="holdings")
