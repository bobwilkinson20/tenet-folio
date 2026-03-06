"""Reports API endpoints."""

import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models.report_sheet_target import ReportSheetTarget
from schemas.report import GoogleSheetsReportResponse
from services.google_sheets_service import GoogleSheetsError, GoogleSheetsNotConfiguredError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


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
    target_id: str = Query(..., description="Sheet target ID"),
    allocation_only: bool = Query(False),
    db: Session = Depends(get_db),
    generate_rows: Callable = Depends(get_report_row_generator),
    write_to_sheets: Callable = Depends(get_sheets_writer),
):
    """Generate a portfolio allocation report in Google Sheets.

    Creates a new tab from the template with timestamped name and populates
    it with account/asset-class market value rows.

    Args:
        target_id: ID of the ReportSheetTarget to write to.
        allocation_only: If True, include only allocation-flagged accounts.

    Returns:
        GoogleSheetsReportResponse with tab name and row count.

    Raises:
        HTTPException:
            - 400: No portfolio data available
            - 404: Sheet target not found
            - 500: Unexpected error generating report data
            - 502: Google Sheets API error
            - 503: Google Sheets not configured
    """
    # Look up the sheet target
    target = db.query(ReportSheetTarget).filter(ReportSheetTarget.id == target_id).first()
    if target is None:
        raise HTTPException(status_code=404, detail="Sheet target not found.")

    spreadsheet_id = target.spreadsheet_id
    template_tab = target.config_dict.get("template_tab", "Template")

    try:
        rows = generate_rows(db, allocation_only=allocation_only)
    except Exception:
        logger.error("Failed to generate report rows", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate report data.")

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No portfolio data available to generate a report.",
        )

    try:
        tab_name = write_to_sheets(rows, spreadsheet_id, template_tab)
    except GoogleSheetsNotConfiguredError:
        raise HTTPException(
            status_code=503,
            detail="Google Sheets is not configured. Add credentials in Settings > Reports.",
        )
    except GoogleSheetsError:
        logger.error("Google Sheets API error", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="Failed to write report to Google Sheets.",
        )

    return GoogleSheetsReportResponse(tab_name=tab_name, rows_written=len(rows))
