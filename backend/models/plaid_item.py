"""PlaidItem model - stores Plaid access tokens per linked institution."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from database import Base
from models.utils import generate_uuid


class PlaidItem(Base):
    """A Plaid Item representing a linked financial institution.

    Each institution linked via Plaid Link gets its own access_token,
    stored here for use during sync operations.
    """

    __tablename__ = "plaid_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    item_id = Column(String, unique=True, index=True, nullable=False)
    access_token = Column(String, nullable=False)
    institution_id = Column(String, nullable=True)
    institution_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
