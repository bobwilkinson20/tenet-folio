"""Tests for google_sheets_service."""

import json
from unittest.mock import MagicMock, patch

import pytest

from services.google_sheets_service import (
    GoogleSheetsError,
    GoogleSheetsNotConfiguredError,
    copy_template_and_write,
    get_client,
    validate_spreadsheet_access,
    validate_template_tab,
)


class TestGetClient:
    """Tests for get_client()."""

    def test_missing_credentials(self):
        """Raises GoogleSheetsNotConfiguredError when credentials are not configured."""
        with patch("services.google_sheets_service.settings") as mock_settings:
            mock_settings.GOOGLE_SHEETS_CREDENTIALS = ""
            with pytest.raises(GoogleSheetsNotConfiguredError, match="not configured"):
                get_client()

    def test_invalid_json(self):
        """Raises GoogleSheetsError when credentials JSON is invalid."""
        with patch("services.google_sheets_service.settings") as mock_settings:
            mock_settings.GOOGLE_SHEETS_CREDENTIALS = "not json"
            with pytest.raises(GoogleSheetsError, match="Invalid.*JSON"):
                get_client()

    def test_auth_failure(self):
        """Raises GoogleSheetsError when authentication fails."""
        creds = json.dumps({"client_email": "a@b.com", "private_key": "pk"})
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.gspread") as mock_gspread,
        ):
            mock_settings.GOOGLE_SHEETS_CREDENTIALS = creds
            mock_gspread.service_account_from_dict.side_effect = Exception("Invalid credentials")

            with pytest.raises(GoogleSheetsError, match="Failed to authenticate"):
                get_client()

    def test_success(self):
        """Returns authenticated client on success."""
        creds = json.dumps({"client_email": "a@b.com", "private_key": "pk"})
        with (
            patch("services.google_sheets_service.settings") as mock_settings,
            patch("services.google_sheets_service.gspread") as mock_gspread,
        ):
            mock_settings.GOOGLE_SHEETS_CREDENTIALS = creds
            mock_client = MagicMock()
            mock_gspread.service_account_from_dict.return_value = mock_client

            result = get_client()
            assert result is mock_client
            mock_gspread.service_account_from_dict.assert_called_once()


class TestCopyTemplateAndWrite:
    """Tests for copy_template_and_write()."""

    def test_missing_spreadsheet_id(self):
        """Raises GoogleSheetsNotConfiguredError when spreadsheet ID is empty."""
        with pytest.raises(GoogleSheetsNotConfiguredError, match="No spreadsheet ID"):
            copy_template_and_write([["A", "B", "100"]], "", "Template")

    def test_template_not_found(self):
        """Raises GoogleSheetsError when template tab doesn't exist."""
        import gspread.exceptions

        with (
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet
            mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Template")

            with pytest.raises(GoogleSheetsError, match="Template.*not found"):
                copy_template_and_write([["A", "B", "100"]], "sheet123", "Template")

    def test_successful_write(self):
        """Successfully duplicates template and writes rows."""
        with (
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
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

            tab_name = copy_template_and_write(rows, "sheet123", "Template")

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
        """Raises GoogleSheetsError when rows list is empty."""
        with pytest.raises(GoogleSheetsError, match="No data rows provided"):
            copy_template_and_write([], "sheet123", "Template")

    def test_write_failure(self):
        """Raises GoogleSheetsError when writing fails."""
        with (
            patch("services.google_sheets_service.get_client") as mock_get_client,
        ):
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
                copy_template_and_write([["A", "B", "100"]], "sheet123", "Template")


class TestValidateSpreadsheetAccess:
    """Tests for validate_spreadsheet_access()."""

    def test_success(self):
        """Returns title and spreadsheet handle on success."""
        with patch("services.google_sheets_service.get_client") as mock_get_client:
            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_spreadsheet.title = "My Sheet"
            mock_gc.open_by_key.return_value = mock_spreadsheet

            title, spreadsheet = validate_spreadsheet_access("sheet123")
            assert title == "My Sheet"
            assert spreadsheet is mock_spreadsheet
            mock_gc.open_by_key.assert_called_once_with("sheet123")

    def test_access_failure(self):
        """Raises GoogleSheetsError when spreadsheet cannot be opened."""
        with patch("services.google_sheets_service.get_client") as mock_get_client:
            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_gc.open_by_key.side_effect = Exception("Not found")

            with pytest.raises(GoogleSheetsError, match="Failed to access spreadsheet"):
                validate_spreadsheet_access("bad_id")

    def test_not_configured(self):
        """Raises GoogleSheetsNotConfiguredError when credentials missing."""
        with patch(
            "services.google_sheets_service.get_client",
            side_effect=GoogleSheetsNotConfiguredError("Not configured"),
        ):
            with pytest.raises(GoogleSheetsNotConfiguredError):
                validate_spreadsheet_access("sheet123")


class TestValidateTemplateTab:
    """Tests for validate_template_tab()."""

    def test_success_with_spreadsheet_handle(self):
        """Validates tab using provided spreadsheet handle."""
        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.return_value = MagicMock()

        # Should not raise
        validate_template_tab("sheet123", "Template", spreadsheet=mock_spreadsheet)
        mock_spreadsheet.worksheet.assert_called_once_with("Template")

    def test_success_without_handle(self):
        """Opens spreadsheet and validates tab when no handle provided."""
        with patch("services.google_sheets_service.get_client") as mock_get_client:
            mock_gc = MagicMock()
            mock_get_client.return_value = mock_gc
            mock_spreadsheet = MagicMock()
            mock_gc.open_by_key.return_value = mock_spreadsheet

            validate_template_tab("sheet123", "Template")
            mock_gc.open_by_key.assert_called_once_with("sheet123")
            mock_spreadsheet.worksheet.assert_called_once_with("Template")

    def test_tab_not_found(self):
        """Raises GoogleSheetsError when tab does not exist."""
        import gspread.exceptions

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.worksheet.side_effect = gspread.exceptions.WorksheetNotFound("Missing")

        with pytest.raises(GoogleSheetsError, match="Template.*not found"):
            validate_template_tab("sheet123", "Template", spreadsheet=mock_spreadsheet)
