"""Service for exporting report data to Google Sheets."""

import json
import logging
from datetime import datetime, timezone

import gspread

from config import settings

logger = logging.getLogger(__name__)


class GoogleSheetsError(Exception):
    """Error interacting with the Google Sheets API."""


class GoogleSheetsNotConfiguredError(GoogleSheetsError):
    """Google Sheets credentials not configured."""


def get_client() -> gspread.Client:
    """Authenticate and return a gspread client.

    Returns:
        Authenticated gspread.Client.

    Raises:
        GoogleSheetsNotConfiguredError: If credentials are not configured.
        GoogleSheetsError: If authentication fails.
    """
    creds_json = settings.GOOGLE_SHEETS_CREDENTIALS
    if not creds_json:
        raise GoogleSheetsNotConfiguredError(
            "Google Sheets is not configured. Add credentials in Settings > Reports."
        )

    try:
        creds_dict = json.loads(creds_json)
    except json.JSONDecodeError as e:
        raise GoogleSheetsError(f"Invalid Google Sheets credentials JSON: {e}") from e

    try:
        return gspread.service_account_from_dict(creds_dict)
    except Exception as e:
        raise GoogleSheetsError(f"Failed to authenticate with Google Sheets: {e}") from e


def copy_template_and_write(
    rows: list[list[str]],
    spreadsheet_id: str,
    template_tab: str,
) -> str:
    """Duplicate the template tab and write report rows.

    Creates a new tab named with the current UTC timestamp (e.g.,
    ``2026-02-25 14:30 UTC``), then writes *rows* into columns C:E
    starting at row 4.

    Args:
        rows: List of [account_name, asset_class_name, market_value] rows.
        spreadsheet_id: Google Sheets spreadsheet ID.
        template_tab: Name of the template tab to duplicate.

    Returns:
        The name of the newly created tab.

    Raises:
        GoogleSheetsError: If any Sheets API operation fails.
    """
    if not rows:
        raise GoogleSheetsError("No data rows provided.")

    if not spreadsheet_id:
        raise GoogleSheetsNotConfiguredError(
            "No spreadsheet ID provided."
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


def validate_spreadsheet_access(spreadsheet_id: str) -> tuple[str, gspread.Spreadsheet]:
    """Open a spreadsheet and return its title and handle.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID.

    Returns:
        Tuple of (title, spreadsheet) so callers can reuse the handle.

    Raises:
        GoogleSheetsError: If access fails.
    """
    try:
        gc = get_client()
        spreadsheet = gc.open_by_key(spreadsheet_id)
        return spreadsheet.title, spreadsheet
    except GoogleSheetsError:
        raise
    except Exception as e:
        raise GoogleSheetsError(f"Failed to access spreadsheet: {e}") from e


def validate_template_tab(
    spreadsheet_id: str,
    tab_name: str,
    spreadsheet: gspread.Spreadsheet | None = None,
) -> None:
    """Check whether a tab exists in the given spreadsheet.

    Args:
        spreadsheet_id: Google Sheets spreadsheet ID (used if *spreadsheet* is None).
        tab_name: Tab name to check.
        spreadsheet: Optional already-opened spreadsheet to avoid a second API call.

    Raises:
        GoogleSheetsError: If the spreadsheet cannot be accessed or tab not found.
    """
    try:
        if spreadsheet is None:
            gc = get_client()
            spreadsheet = gc.open_by_key(spreadsheet_id)
        spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        raise GoogleSheetsError(
            f"Template tab '{tab_name}' not found in spreadsheet."
        )
    except GoogleSheetsError:
        raise
    except Exception as e:
        raise GoogleSheetsError(f"Failed to validate template tab: {e}") from e
