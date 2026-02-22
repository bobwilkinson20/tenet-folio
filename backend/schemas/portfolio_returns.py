"""Pydantic schemas for portfolio returns API responses."""

from datetime import date

from pydantic import BaseModel


class PeriodReturn(BaseModel):
    """Return calculation for a single time period."""

    period: str  # "1D", "1M", "QTD", etc.
    irr: str | None  # Decimal as string, e.g. "0.0523" (5.23%)
    start_date: date
    end_date: date
    has_sufficient_data: bool


class ScopeReturnsResponse(BaseModel):
    """Returns for a single scope (portfolio or account)."""

    scope_id: str  # "portfolio" or account UUID
    scope_name: str
    periods: list[PeriodReturn]
    chained_from: list[str] = []


class PortfolioReturnsResponse(BaseModel):
    """Top-level response combining portfolio and account returns."""

    portfolio: ScopeReturnsResponse | None
    accounts: list[ScopeReturnsResponse]
