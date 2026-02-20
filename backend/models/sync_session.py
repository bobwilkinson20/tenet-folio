"""SyncSession model - represents a sync operation at a point in time."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import relationship

from database import Base
from models.utils import generate_uuid


class SyncSession(Base):
    """A sync session representing a point-in-time sync operation."""

    __tablename__ = "sync_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_complete = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    account_snapshots = relationship("AccountSnapshot", back_populates="sync_session")
    sync_log_entries = relationship("SyncLogEntry", back_populates="sync_session")

    @property
    def holdings(self):
        """All holdings across account snapshots in this sync session."""
        result = []
        for acct_snap in self.account_snapshots:
            result.extend(acct_snap.holdings)
        return result
