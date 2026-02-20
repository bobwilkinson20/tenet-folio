"""LotDisposal model - records a quantity reduction from a lot."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class LotDisposal(Base):
    """Records a quantity reduction from a holding lot (sell event).

    A single sell can create multiple disposals across lots (e.g., FIFO
    across two lots). Disposals from the same sell event share a
    disposal_group_id.
    """

    __tablename__ = "lot_disposals"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_lot_disposal_quantity_positive"),
        CheckConstraint("proceeds_per_unit >= 0", name="ck_lot_disposal_proceeds_non_negative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    holding_lot_id = Column(String(36), ForeignKey("holding_lots.id"), nullable=False, index=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    security_id = Column(String(36), ForeignKey("securities.id"), nullable=False, index=True)
    disposal_date = Column(Date, nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    proceeds_per_unit = Column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    source = Column(String, nullable=False)  # "activity" / "inferred" / "initial" / "manual"
    activity_id = Column(String(36), ForeignKey("activities.id"), nullable=True)
    disposal_group_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    holding_lot = relationship("HoldingLot", back_populates="disposals")
    account = relationship("Account")
    security = relationship("Security")
    activity = relationship("Activity")
