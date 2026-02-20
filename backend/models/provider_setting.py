"""ProviderSetting model - per-provider enabled/disabled toggle."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from database import Base
from models.utils import generate_uuid


class ProviderSetting(Base):
    """Stores per-provider settings (currently just is_enabled toggle)."""

    __tablename__ = "provider_settings"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    provider_name = Column(String, unique=True, index=True, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
