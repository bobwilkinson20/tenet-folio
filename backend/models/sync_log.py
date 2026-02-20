"""SyncLogEntry model - records per-provider results for each sync."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class SyncLogEntry(Base):
    """A log entry recording the result of syncing a single provider.

    Each sync session can have multiple log entries, one per provider that was synced.
    """

    __tablename__ = "sync_log_entries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    sync_session_id = Column(String(36), ForeignKey("sync_sessions.id"), nullable=False)
    provider_name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # "success" | "failed" | "partial"
    error_messages = Column(JSON, nullable=True)  # list[str] of provider errors
    accounts_synced = Column(Integer, default=0)
    accounts_stale = Column(Integer, default=0)
    accounts_error = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    sync_session = relationship("SyncSession", back_populates="sync_log_entries")
