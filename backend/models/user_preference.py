"""UserPreference model - generic key-value store for user preferences."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

from database import Base
from models.utils import generate_uuid


class UserPreference(Base):
    """A single user preference stored as a JSON-serialized value."""

    __tablename__ = "user_preferences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)  # JSON-serialized
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
