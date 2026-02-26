"""Tests for google_sheets_service."""

from unittest.mock import MagicMock, patch

import pytest

from services.google_sheets_service import (
    GoogleSheetsError,
    copy_template_and_write,
    get_client,
)


class TestGetClient:
    """Tests for get_client()."""

    def test_missing_credentials_file(self):
        """Raises GoogleSheetsError when credentials file is not configured."""
        with patch("services.google_sheets_service.settings") as mock_settings:
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = ""
            with pytest.raises(GoogleSheetsError, match="not configured"):
                get_client()

    def test_auth_failure(self):
        """Raises GoogleSheetsError when authentication fails."""
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.gspread") as mock_gspread,
        ):
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"
            mock_gspread.service_account.side_effect = Exception("Invalid credentials")

            with pytest.raises(GoogleSheetsError, match="Failed to authenticate"):
                get_client()

    def test_success(self):
        """Returns authenticated client on success."""
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.gspread") as mock_gspread,
        ):
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"
            mock_client = MagicMock()
            mock_gspread.service_account.return_value = mock_client

            result = get_client()
            assert result is mock_client
            mock_gspread.service_account.assert_called_once_with(
                filename="/path/to/creds.json"
            )


class TestCopyTemplateAndWrite:
    """Tests for copy_template_and_write()."""

    def test_missing_spreadsheet_id(self):
        """Raises GoogleSheetsError when spreadsheet ID is not configured."""
        with patch("services.google_sheets_service.settings") as mock_settings:
            mock_settings.GOOGLE_SHEETS_SPREADSHEET_ID = ""
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"

            with pytest.raises(GoogleSheetsError, match="not configured"):
                copy_template_and_write([["A", "B", "100"]])

    def test_template_not_found(self):
        """Raises GoogleSheetsError when template tab doesn't exist."""
        import gspread.exceptions

        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
            mock_settings.GOOGLE_SHEETS_SPREADSHEET_ID = "sheet123"
            mock_settings.GOOGLE_SHEETS_TEMPLATE_TAB = "Template"
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"

            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet
            mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Template")

            with pytest.raises(GoogleSheetsError, match="Template.*not found"):
                copy_template_and_write([["A", "B", "100"]])

    def test_successful_write(self):
        """Successfully duplicates template and writes rows."""
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
            mock_settings.GOOGLE_SHEETS_SPREADSHEET_ID = "sheet123"
            mock_settings.GOOGLE_SHEETS_TEMPLATE_TAB = "Template"
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"

            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet

            mock_template_ws = MagicMock()
            mock_template_ws.id = 123
            mock_spreadsheet.worksheet.return_value = mock_template_ws

            mock_new_ws = MagicMock()
            mock_spreadsheet.duplicate_sheet.return_value = mock_new_ws

            rows = [
                ["Account A", "Stocks", "1000.00"],
                ["/", "Bonds", "500.00"],
            ]

            tab_name = copy_template_and_write(rows)

            # Tab name should be a UTC timestamp
            assert "UTC" in tab_name

            # Should have duplicated the template
            mock_spreadsheet.duplicate_sheet.assert_called_once()
            call_kwargs = mock_spreadsheet.duplicate_sheet.call_args
            assert call_kwargs[0][0] == 123  # template_ws.id

            # Should have written rows to C4:E5
            mock_new_ws.update.assert_called_once_with(
                "C4:E5",
                rows,
                value_input_option="USER_ENTERED",
            )

    def test_empty_rows(self):
        """Does not call update when rows list is empty."""
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
            mock_settings.GOOGLE_SHEETS_SPREADSHEET_ID = "sheet123"
            mock_settings.GOOGLE_SHEETS_TEMPLATE_TAB = "Template"
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"

            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet

            mock_template_ws = MagicMock()
            mock_template_ws.id = 123
            mock_spreadsheet.worksheet.return_value = mock_template_ws

            mock_new_ws = MagicMock()
            mock_spreadsheet.duplicate_sheet.return_value = mock_new_ws

            tab_name = copy_template_and_write([])

            assert "UTC" in tab_name
            mock_new_ws.update.assert_not_called()

    def test_write_failure(self):
        """Raises GoogleSheetsError when writing fails."""
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
            mock_settings.GOOGLE_SHEETS_SPREADSHEET_ID = "sheet123"
            mock_settings.GOOGLE_SHEETS_TEMPLATE_TAB = "Template"
            mock_settings.GOOGLE_SHEETS_CREDENTIALS_FILE = "/path/to/creds.json"

            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet

            mock_template_ws = MagicMock()
            mock_template_ws.id = 123
            mock_spreadsheet.worksheet.return_value = mock_template_ws

            mock_new_ws = MagicMock()
            mock_spreadsheet.duplicate_sheet.return_value = mock_new_ws
            mock_new_ws.update.side_effect = Exception("API quota exceeded")

            with pytest.raises(GoogleSheetsError, match="Failed to write"):
                copy_template_and_write([["A", "B", "100"]])
