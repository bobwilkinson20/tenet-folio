"""Reports API endpoints."""

import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.google_sheets_service import GoogleSheetsError, GoogleSheetsNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GoogleSheetsReportResponse(BaseModel):
    tab_name: str
    rows_written: int


def get_report_row_generator() -> Callable:
    """Get the report row generator function."""
    from services.report_service import generate_account_asset_class_rows
    return generate_account_asset_class_rows


def get_sheets_writer() -> Callable:
    """Get the sheets writer function."""
    from services.google_sheets_service import copy_template_and_write
    return copy_template_and_write


@router.post("/google-sheets", response_model=GoogleSheetsReportResponse)
def generate_google_sheets_report(
    db: Session = Depends(get_db),
    generate_rows: Callable = Depends(get_report_row_generator),
    write_to_sheets: Callable = Depends(get_sheets_writer),
):
    """Generate a portfolio allocation report in Google Sheets.

    Creates a new tab from the template with timestamped name and populates
    it with account/asset-class market value rows.

    Returns:
        GoogleSheetsReportResponse with tab name and row count.

    Raises:
        HTTPException:
            - 400: No portfolio data available
            - 500: Unexpected error generating report data
            - 502: Google Sheets API error
            - 503: Google Sheets not configured
    """
    try:
        rows = generate_rows(db)
    except Exception:
        logger.error("Failed to generate report rows", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report data.")

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No portfolio data available to generate a report.",
        )

    try:
        tab_name = write_to_sheets(rows)
    except GoogleSheetsNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Google Sheets is not configured. Run setup_google_sheets.py first.",
        )
    except GoogleSheetsError:
        logger.error("Google Sheets API error", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to write report to Google Sheets.",
        )

    return GoogleSheetsReportResponse(tab_name=tab_name, rows_written=len(rows))
