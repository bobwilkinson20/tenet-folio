"""DailyHoldingValue model - stores computed market value per holding per day."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class DailyHoldingValue(Base):
    """Computed market value for a single holding on a single calendar day.

    Built by combining holdings from sync snapshots with daily market close
    prices. Enables time-series portfolio valuation without requiring daily syncs.
    """

    __tablename__ = "daily_holding_values"
    __table_args__ = (
        UniqueConstraint(
            "valuation_date", "account_id", "security_id",
            name="uix_daily_holding_value",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    valuation_date = Column(Date, nullable=False, index=True)
    account_id = Column(
        String(36), ForeignKey("accounts.id"), nullable=False, index=True
    )
    account_snapshot_id = Column(
        String(36), ForeignKey("account_snapshots.id"), nullable=False, index=True
    )
    security_id = Column(
        String(36), ForeignKey("securities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ticker = Column(String, nullable=False)  # Kept for convenience/fallback
    quantity = Column(Numeric(18, 8), nullable=False, default=Decimal("0"))
    close_price = Column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    market_value = Column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account = relationship("Account")
    account_snapshot = relationship("AccountSnapshot", back_populates="daily_holding_values")
    security = relationship("Security")
