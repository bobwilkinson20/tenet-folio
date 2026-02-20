"""AccountSnapshot model - records an account's participation in a sync session."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class AccountSnapshot(Base):
    """Records that an account was synced as part of a sync session.

    This ensures liquidated accounts (zero holdings) still have a record
    in the sync session, preventing stale data from being shown.
    """

    __tablename__ = "account_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "sync_session_id", name="uix_account_sync_session"),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False)
    sync_session_id = Column(String(36), ForeignKey("sync_sessions.id"), nullable=False)
    status = Column(String, nullable=False)  # "success" | "failed"
    total_value = Column(Numeric(18, 4), nullable=False, default=0)
    balance_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account = relationship("Account", back_populates="account_snapshots")
    sync_session = relationship("SyncSession", back_populates="account_snapshots")
    holdings = relationship("Holding", back_populates="account_snapshot")
    daily_holding_values = relationship("DailyHoldingValue", back_populates="account_snapshot")
