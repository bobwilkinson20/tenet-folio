"""Activity model - represents a transaction/activity from a provider."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class Activity(Base):
    """A transaction/activity record from a data provider.

    Activities are a continuous log (not snapshot-based like holdings),
    associated directly with accounts. Deduplication via composite
    unique constraint (provider_name, account_id, external_id).
    """

    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint(
            "provider_name", "account_id", "external_id",
            name="uix_activity_provider_account_external",
        ),
    )

    id = Column(String(36), primary_key=True, default=generate_uuid)
    account_id = Column(String(36), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    provider_name = Column(String, nullable=False)
    external_id = Column(String, nullable=False)
    activity_date = Column(DateTime, nullable=False)
    settlement_date = Column(DateTime, nullable=True)
    type = Column(String, nullable=False)  # e.g., "buy", "sell", "dividend", "transfer", etc.
    description = Column(String, nullable=True)
    ticker = Column(String, nullable=True)
    units = Column(Numeric(18, 8), nullable=True)
    price = Column(Numeric(18, 4), nullable=True)
    amount = Column(Numeric(18, 4), nullable=True)
    currency = Column(String, nullable=True)
    fee = Column(Numeric(18, 4), nullable=True)
    raw_data = Column(Text, nullable=True)  # JSON string for debugging
    is_reviewed = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)
    user_modified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account = relationship("Account", back_populates="activities")
