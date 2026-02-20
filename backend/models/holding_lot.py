"""HoldingLot model - persistent ledger record for each acquisition event."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class HoldingLot(Base):
    """A lot representing an acquisition of a security in an account.

    Unlike holdings (snapshot-based), lots persist across syncs and track
    the full lifecycle of a position from acquisition through disposal.
    """

    __tablename__ = "holding_lots"
    __table_args__ = (
        CheckConstraint("cost_basis_per_unit >= 0", name="ck_holding_lot_cost_basis_non_negative"),
        CheckConstraint("original_quantity > 0", name="ck_holding_lot_original_quantity_positive"),
        CheckConstraint("current_quantity >= 0", name="ck_holding_lot_current_quantity_non_negative"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False, index=True)
    security_id = Column(String(36), ForeignKey("securities.id"), nullable=False, index=True)
    ticker = Column(String, nullable=False)
    acquisition_date = Column(Date, nullable=True)
    cost_basis_per_unit = Column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    original_quantity = Column(Numeric(18, 8), nullable=False)
    current_quantity = Column(Numeric(18, 8), nullable=False)
    is_closed = Column(Boolean, default=False, index=True)
    source = Column(String, nullable=False)  # "activity" / "inferred" / "initial" / "manual"
    activity_id = Column(String(36), ForeignKey("activities.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    account = relationship("Account", back_populates="holding_lots")
    security = relationship("Security", back_populates="holding_lots")
    activity = relationship("Activity")
    disposals = relationship("LotDisposal", back_populates="holding_lot", cascade="all, delete-orphan")
