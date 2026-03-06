"""ReportSheetTarget model - registered Google Sheets destinations for reports."""

import json
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String, Text

from database import Base
from models.utils import generate_uuid


class ReportSheetTarget(Base):
    """A registered Google Sheets destination for a specific report type."""

    __tablename__ = "report_sheet_targets"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    report_type = Column(String, nullable=False)
    spreadsheet_id = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    config = Column(Text, default="{}")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_report_sheet_targets_report_type", "report_type"),
    )

    @property
    def config_dict(self) -> dict:
        """Parse the JSON config column into a Python dict."""
        if not self.config:
            return {}
        return json.loads(self.config)

    @config_dict.setter
    def config_dict(self, value: dict) -> None:
        """Serialize a Python dict into the JSON config column."""
        self.config = json.dumps(value)
