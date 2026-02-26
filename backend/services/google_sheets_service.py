"""Service for exporting report data to Google Sheets."""

import logging
from datetime import datetime, timezone

import gspread

from config import settings

logger = logging.getLogger(__name__)


class GoogleSheetsError(Exception):
    """Error interacting with the Google Sheets API."""


class GoogleSheetsNotConfiguredError(GoogleSheetsError):
    """Google Sheets credentials or spreadsheet ID not configured."""


def get_client() -> gspread.Client:
    """Authenticate and return a gspread client.

    Returns:
        Authenticated gspread.Client.

    Raises:
        GoogleSheetsError: If credentials file is missing or authentication fails.
    """
    creds_file = settings.GOOGLE_SHEETS_CREDENTIALS_FILE
    if not creds_file:
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_CREDENTIALS_FILE."
        )

    try:
        return gspread.service_account(filename=creds_file)
    except Exception as e:
        raise GoogleSheetsError(f"Failed to authenticate with Google Sheets: {e}") from e


def copy_template_and_write(rows: list[list[str]]) -> str:
    """Duplicate the template tab and write report rows.

    Creates a new tab named with the current UTC timestamp (e.g.,
    ``2026-02-25 14:30 UTC``), then writes *rows* into columns C:E
    starting at row 4.

    Args:
        rows: List of [account_name, asset_class_name, market_value] rows.

    Returns:
        The name of the newly created tab.

    Raises:
        GoogleSheetsError: If any Sheets API operation fails.
    """
    if not rows:
        raise GoogleSheetsError("No data rows provided.")

    spreadsheet_id = settings.GOOGLE_SHEETS_SPREADSHEET_ID
    template_tab = settings.GOOGLE_SHEETS_TEMPLATE_TAB

    if not spreadsheet_id:
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured. Set GOOGLE_SHEETS_SPREADSHEET_ID."
        )

    try:
        gc = get_client()
        spreadsheet = gc.open_by_key(spreadsheet_id)
    except GoogleSheetsError:
        raise
    except Exception as e:
        raise GoogleSheetsError(f"Failed to open spreadsheet: {e}") from e

    # Find template worksheet
    try:
        template_ws = spreadsheet.worksheet(template_tab)
    except gspread.exceptions.WorksheetNotFound:
        raise GoogleSheetsError(
            f"Template tab '{template_tab}' not found in spreadsheet."
        )

    # Create timestamped copy
    now = datetime.now(timezone.utc)
    tab_name = now.strftime("%Y-%m-%d %H:%M UTC")

    try:
        new_ws = spreadsheet.duplicate_sheet(
            template_ws.id,
            new_sheet_name=tab_name,
        )
    except Exception as e:
        raise GoogleSheetsError(f"Failed to duplicate template tab: {e}") from e

    # Template rows 1-3 are headers; data starts at row 4 in columns C:E
    # (C=account, D=asset class, E=market value)
    start_row = 4
    end_row = start_row + len(rows) - 1
    cell_range = f"C{start_row}:E{end_row}"

    try:
        new_ws.update(cell_range, rows, value_input_option="USER_ENTERED")
    except Exception as e:
        raise GoogleSheetsError(f"Failed to write data to sheet: {e}") from e

    logger.info(
        "Created Google Sheets tab '%s' with %d rows",
        tab_name,
        len(rows),
    )

    return tab_name
