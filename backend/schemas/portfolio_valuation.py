"""Pydantic schemas for portfolio valuation endpoints."""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ValuePoint(BaseModel):
    """A single date/value data point."""

    date: date
    value: Decimal


class SeriesData(BaseModel):
    """A named data series with optional metadata."""

    account_name: Optional[str] = None
    asset_class_name: Optional[str] = None
    asset_class_color: Optional[str] = None
    data_points: list[ValuePoint]


class PortfolioValueHistoryResponse(BaseModel):
    """Response for portfolio value history endpoint."""

    start_date: date
    end_date: date
    data_points: Optional[list[ValuePoint]] = None
    series: Optional[dict[str, SeriesData]] = None


class AccountDHVDiagnostic(BaseModel):
    """Per-account DHV gap analysis."""

    account_id: str
    account_name: str
    expected_start: date
    expected_end: date
    expected_days: int
    actual_days: int
    missing_days: int
    missing_dates: list[str]
    partial_days: int = 0
    partial_dates: list[str] = []


class DHVDiagnosticsResponse(BaseModel):
    """Response for DHV diagnostics endpoint."""

    accounts: list[AccountDHVDiagnostic]
    total_missing_days: int
    total_partial_days: int = 0
