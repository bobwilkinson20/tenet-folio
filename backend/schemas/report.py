"""Pydantic schemas for reports and report configuration."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReportTypeResponse(BaseModel):
    """A registered report type with its configuration fields."""

    id: str
    display_name: str
    description: str
    config_fields: list[dict]


class ReportSheetTargetResponse(BaseModel):
    """A registered Google Sheets destination for a report type."""

    id: str
    report_type: str
    spreadsheet_id: str
    display_name: str
    config: dict
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportSheetTargetCreateRequest(BaseModel):
    """Request to register a new sheet target."""

    report_type: str
    spreadsheet_id: str
    display_name: str = ""
    config: dict = {}


class ReportSheetTargetUpdateRequest(BaseModel):
    """Request to update an existing sheet target."""

    display_name: Optional[str] = None
    config: Optional[dict] = None


class GoogleSheetsCredentialStatus(BaseModel):
    """Status of Google Sheets credential configuration."""

    configured: bool
    service_account_email: Optional[str] = None


class GoogleSheetsCredentialSetRequest(BaseModel):
    """Request to store Google Sheets service account credentials."""

    credentials_json: str


class GoogleSheetsReportResponse(BaseModel):
    """Response from generating a Google Sheets report."""

    tab_name: str
    rows_written: int
