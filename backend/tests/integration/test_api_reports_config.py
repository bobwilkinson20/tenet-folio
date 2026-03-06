"""Integration tests for reports config API endpoints."""

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from database import get_db
from main import app
from models.report_sheet_target import ReportSheetTarget


def _make_client(db):
    """Create a test client with the test database."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _cleanup_overrides():
    """Remove overrides set by _make_client."""
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


class TestCredentialStatus:
    """Tests for GET /api/reports/config/credentials."""

    def test_unconfigured(self, db):
        """Returns configured=False when no credentials set."""
        client = _make_client(db)
        try:
            with patch("api.reports_config.settings") as mock_settings:
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = ""
                response = client.get("/api/reports/config/credentials")
            assert response.status_code == 200
            data = response.json()
            assert data["configured"] is False
            assert data["service_account_email"] is None
        finally:
            _cleanup_overrides()

    def test_configured(self, db):
        """Returns configured=True with email when credentials are set."""
        creds = json.dumps({"client_email": "test@example.iam.gserviceaccount.com", "private_key": "pk"})
        client = _make_client(db)
        try:
            with patch("api.reports_config.settings") as mock_settings:
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = creds
                response = client.get("/api/reports/config/credentials")
            assert response.status_code == 200
            data = response.json()
            assert data["configured"] is True
            assert data["service_account_email"] == "test@example.iam.gserviceaccount.com"
        finally:
            _cleanup_overrides()


class TestSetCredentials:
    """Tests for POST /api/reports/config/credentials."""

    def test_invalid_json(self, db):
        """Returns 400 for invalid JSON."""
        client = _make_client(db)
        try:
            response = client.post(
                "/api/reports/config/credentials",
                json={"credentials_json": "not json"},
            )
            assert response.status_code == 400
            assert "Invalid JSON" in response.json()["detail"]
        finally:
            _cleanup_overrides()

    def test_missing_required_fields(self, db):
        """Returns 400 when required fields are missing."""
        client = _make_client(db)
        try:
            response = client.post(
                "/api/reports/config/credentials",
                json={"credentials_json": json.dumps({"client_email": "a@b.com"})},
            )
            assert response.status_code == 400
            assert "private_key" in response.json()["detail"]
        finally:
            _cleanup_overrides()

    def test_auth_failure(self, db):
        """Returns 400 when gspread authentication fails."""
        client = _make_client(db)
        try:
            creds = json.dumps({"client_email": "a@b.com", "private_key": "pk"})
            with patch("api.reports_config.gspread") as mock_gspread:
                mock_gspread.service_account_from_dict.side_effect = Exception("Auth failed")
                response = client.post(
                    "/api/reports/config/credentials",
                    json={"credentials_json": creds},
                )
            assert response.status_code == 400
            assert "authentication failed" in response.json()["detail"].lower()
        finally:
            _cleanup_overrides()

    def test_success(self, db):
        """Stores credentials and returns configured status."""
        client = _make_client(db)
        try:
            creds = json.dumps({"client_email": "a@b.com", "private_key": "pk"})
            with (
                patch("api.reports_config.gspread") as mock_gspread,
                patch("api.reports_config.set_credential", return_value=True),
                patch("api.reports_config.settings") as mock_settings,
            ):
                mock_gspread.service_account_from_dict.return_value = MagicMock()
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = ""
                response = client.post(
                    "/api/reports/config/credentials",
                    json={"credentials_json": creds},
                )
            assert response.status_code == 200
            data = response.json()
            assert data["configured"] is True
            assert data["service_account_email"] == "a@b.com"
        finally:
            _cleanup_overrides()

    def test_keychain_failure(self, db):
        """Returns 500 when keychain storage fails."""
        client = _make_client(db)
        try:
            creds = json.dumps({"client_email": "a@b.com", "private_key": "pk"})
            with (
                patch("api.reports_config.gspread") as mock_gspread,
                patch("api.reports_config.set_credential", return_value=False),
            ):
                mock_gspread.service_account_from_dict.return_value = MagicMock()
                response = client.post(
                    "/api/reports/config/credentials",
                    json={"credentials_json": creds},
                )
            assert response.status_code == 500
            assert "keychain" in response.json()["detail"].lower()
        finally:
            _cleanup_overrides()


class TestDeleteCredentials:
    """Tests for DELETE /api/reports/config/credentials."""

    def test_success(self, db):
        """Returns 204 on successful deletion."""
        client = _make_client(db)
        try:
            with (
                patch("api.reports_config.delete_credential"),
                patch("api.reports_config.settings") as mock_settings,
            ):
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = "some-creds"
                response = client.delete("/api/reports/config/credentials")
            assert response.status_code == 204
        finally:
            _cleanup_overrides()


# ---------------------------------------------------------------------------
# Report Types
# ---------------------------------------------------------------------------


class TestReportTypes:
    """Tests for GET /api/reports/config/types."""

    def test_list_types(self, db):
        """Returns all registered report types."""
        client = _make_client(db)
        try:
            response = client.get("/api/reports/config/types")
            assert response.status_code == 200
            data = response.json()
            assert len(data) >= 1
            ids = [t["id"] for t in data]
            assert "account_allocation" in ids
        finally:
            _cleanup_overrides()


# ---------------------------------------------------------------------------
# Sheet Targets
# ---------------------------------------------------------------------------


class TestListTargets:
    """Tests for GET /api/reports/config/targets."""

    def test_empty_list(self, db):
        """Returns empty list when no targets exist."""
        client = _make_client(db)
        try:
            response = client.get("/api/reports/config/targets")
            assert response.status_code == 200
            assert response.json() == []
        finally:
            _cleanup_overrides()

    def test_list_all(self, db, create_report_sheet_target):
        """Returns all targets."""
        create_report_sheet_target(display_name="Sheet A")
        create_report_sheet_target(display_name="Sheet B")
        client = _make_client(db)
        try:
            response = client.get("/api/reports/config/targets")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
        finally:
            _cleanup_overrides()

    def test_filter_by_report_type(self, db, create_report_sheet_target):
        """Filters targets by report_type query param."""
        create_report_sheet_target(report_type="account_allocation")
        create_report_sheet_target(report_type="other_type")
        client = _make_client(db)
        try:
            response = client.get("/api/reports/config/targets?report_type=account_allocation")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["report_type"] == "account_allocation"
        finally:
            _cleanup_overrides()


class TestCreateTarget:
    """Tests for POST /api/reports/config/targets."""

    def test_unknown_report_type(self, db):
        """Returns 400 for unknown report type."""
        client = _make_client(db)
        try:
            response = client.post(
                "/api/reports/config/targets",
                json={
                    "report_type": "nonexistent",
                    "spreadsheet_id": "sheet123",
                },
            )
            assert response.status_code == 400
            assert "Unknown report type" in response.json()["detail"]
        finally:
            _cleanup_overrides()

    def test_no_credentials(self, db):
        """Returns 400 when credentials are not configured."""
        client = _make_client(db)
        try:
            with patch("api.reports_config.settings") as mock_settings:
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = ""
                response = client.post(
                    "/api/reports/config/targets",
                    json={
                        "report_type": "account_allocation",
                        "spreadsheet_id": "sheet123",
                    },
                )
            assert response.status_code == 400
            assert "credentials" in response.json()["detail"].lower()
        finally:
            _cleanup_overrides()

    def test_spreadsheet_access_failure(self, db):
        """Returns 400 when spreadsheet access fails."""
        from services.google_sheets_service import GoogleSheetsError

        client = _make_client(db)
        try:
            with (
                patch("api.reports_config.settings") as mock_settings,
                patch(
                    "api.reports_config.validate_spreadsheet_access",
                    side_effect=GoogleSheetsError("Access denied"),
                ),
            ):
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = '{"key": "value"}'
                response = client.post(
                    "/api/reports/config/targets",
                    json={
                        "report_type": "account_allocation",
                        "spreadsheet_id": "sheet123",
                    },
                )
            assert response.status_code == 400
        finally:
            _cleanup_overrides()

    def test_success_with_defaults(self, db):
        """Creates target with config defaults and spreadsheet title as display name."""
        client = _make_client(db)
        try:
            with (
                patch("api.reports_config.settings") as mock_settings,
                patch(
                    "api.reports_config.validate_spreadsheet_access",
                    return_value=("My Portfolio Sheet", MagicMock()),
                ),
                patch("api.reports_config.validate_template_tab"),
            ):
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = '{"key": "value"}'
                response = client.post(
                    "/api/reports/config/targets",
                    json={
                        "report_type": "account_allocation",
                        "spreadsheet_id": "sheet123",
                    },
                )
            assert response.status_code == 201
            data = response.json()
            assert data["report_type"] == "account_allocation"
            assert data["spreadsheet_id"] == "sheet123"
            assert data["display_name"] == "My Portfolio Sheet"
            assert data["config"]["template_tab"] == "Template"
        finally:
            _cleanup_overrides()

    def test_success_with_custom_values(self, db):
        """Creates target with custom display name and config."""
        client = _make_client(db)
        try:
            with (
                patch("api.reports_config.settings") as mock_settings,
                patch(
                    "api.reports_config.validate_spreadsheet_access",
                    return_value=("My Portfolio Sheet", MagicMock()),
                ),
                patch("api.reports_config.validate_template_tab"),
            ):
                mock_settings.GOOGLE_SHEETS_CREDENTIALS = '{"key": "value"}'
                response = client.post(
                    "/api/reports/config/targets",
                    json={
                        "report_type": "account_allocation",
                        "spreadsheet_id": "sheet123",
                        "display_name": "Custom Name",
                        "config": {"template_tab": "MyTemplate"},
                    },
                )
            assert response.status_code == 201
            data = response.json()
            assert data["display_name"] == "Custom Name"
            assert data["config"]["template_tab"] == "MyTemplate"
        finally:
            _cleanup_overrides()


class TestUpdateTarget:
    """Tests for PUT /api/reports/config/targets/{id}."""

    def test_not_found(self, db):
        """Returns 404 for nonexistent target."""
        client = _make_client(db)
        try:
            response = client.put(
                "/api/reports/config/targets/nonexistent",
                json={"display_name": "New Name"},
            )
            assert response.status_code == 404
        finally:
            _cleanup_overrides()

    def test_update_display_name(self, db, create_report_sheet_target):
        """Updates display name."""
        target = create_report_sheet_target()
        client = _make_client(db)
        try:
            response = client.put(
                f"/api/reports/config/targets/{target.id}",
                json={"display_name": "Renamed Sheet"},
            )
            assert response.status_code == 200
            assert response.json()["display_name"] == "Renamed Sheet"
        finally:
            _cleanup_overrides()

    def test_update_config(self, db, create_report_sheet_target):
        """Updates config with re-validation."""
        target = create_report_sheet_target()
        client = _make_client(db)
        try:
            with patch("api.reports_config.validate_template_tab"):
                response = client.put(
                    f"/api/reports/config/targets/{target.id}",
                    json={"config": {"template_tab": "NewTemplate"}},
                )
                assert response.status_code == 200, response.json()
                assert response.json()["config"]["template_tab"] == "NewTemplate"
        finally:
            _cleanup_overrides()

    def test_update_config_missing_required_field(self, db, create_report_sheet_target):
        """Returns 400 when required config field is missing."""
        target = create_report_sheet_target()
        client = _make_client(db)
        try:
            response = client.put(
                f"/api/reports/config/targets/{target.id}",
                json={"config": {}},
            )
            assert response.status_code == 400
            assert "template_tab" in response.json()["detail"].lower()
        finally:
            _cleanup_overrides()


class TestDeleteTarget:
    """Tests for DELETE /api/reports/config/targets/{id}."""

    def test_not_found(self, db):
        """Returns 404 for nonexistent target."""
        client = _make_client(db)
        try:
            response = client.delete("/api/reports/config/targets/nonexistent")
            assert response.status_code == 404
        finally:
            _cleanup_overrides()

    def test_success(self, db, create_report_sheet_target):
        """Deletes target and returns 204."""
        target = create_report_sheet_target()
        client = _make_client(db)
        try:
            response = client.delete(f"/api/reports/config/targets/{target.id}")
            assert response.status_code == 204

            # Verify deleted
            assert db.query(ReportSheetTarget).filter(
                ReportSheetTarget.id == target.id
            ).first() is None
        finally:
            _cleanup_overrides()
