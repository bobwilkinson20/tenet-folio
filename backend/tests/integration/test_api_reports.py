"""Integration tests for reports API endpoints."""

from fastapi.testclient import TestClient

from api.reports import get_report_row_generator, get_sheets_writer
from database import get_db
from main import app
from models.report_sheet_target import ReportSheetTarget
from services.google_sheets_service import GoogleSheetsError, GoogleSheetsNotConfiguredError


def _create_target(db, report_type="account_allocation", spreadsheet_id="sheet123",
                   display_name="Test Sheet", config=None):
    """Helper to create a ReportSheetTarget directly in the DB."""
    target = ReportSheetTarget(
        report_type=report_type,
        spreadsheet_id=spreadsheet_id,
        display_name=display_name,
    )
    target.config_dict = config or {"template_tab": "Template"}
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def _make_client(db, generate_rows=None, write_to_sheets=None):
    """Create a test client with optional dependency overrides."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    if generate_rows is not None:
        app.dependency_overrides[get_report_row_generator] = lambda: generate_rows

    if write_to_sheets is not None:
        app.dependency_overrides[get_sheets_writer] = lambda: write_to_sheets

    return TestClient(app)


def _cleanup_overrides():
    """Remove only the overrides set by _make_client."""
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_report_row_generator, None)
    app.dependency_overrides.pop(get_sheets_writer, None)


def test_200_success(db):
    """Successful report returns 200 with tab name and row count."""
    target = _create_target(db)
    rows = [
        ["Account A", "Stocks", "1000.00"],
        ["/", "Bonds", "500.00"],
    ]

    def mock_generate_rows(db_session, **kwargs):
        return rows

    def mock_write(r, spreadsheet_id, template_tab):
        return "2026-02-25 14:30 UTC"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["tab_name"] == "2026-02-25 14:30 UTC"
        assert data["rows_written"] == 2
    finally:
        _cleanup_overrides()


def test_404_missing_target(db):
    """Returns 404 when target_id does not exist."""
    rows = [["A", "B", "100"]]

    def mock_generate_rows(db_session, **kwargs):
        return rows

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets?target_id=nonexistent")
        assert response.status_code == 404
        assert "target not found" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_422_missing_target_id(db):
    """Returns 422 when target_id is not provided."""

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "B", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 422
    finally:
        _cleanup_overrides()


def test_400_no_data(db):
    """Returns 400 when no portfolio data is available."""
    target = _create_target(db)

    def mock_generate_rows(db_session, **kwargs):
        return []

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 400
        assert "no portfolio data" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_502_sheets_api_error(db):
    """Returns 502 when Google Sheets API fails."""
    target = _create_target(db)

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "B", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        raise GoogleSheetsError("API quota exceeded")

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 502
        assert "failed to write" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_503_not_configured(db):
    """Returns 503 when Google Sheets is not configured."""
    target = _create_target(db)

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "B", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        raise GoogleSheetsNotConfiguredError("Not configured")

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_500_generate_failure(db):
    """Returns 500 when row generation fails unexpectedly."""
    target = _create_target(db)

    def mock_generate_rows(db_session, **kwargs):
        raise RuntimeError("Unexpected DB error")

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 500
        assert "failed to generate" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_allocation_only_passed_to_generator(db):
    """allocation_only query param is forwarded to the row generator."""
    target = _create_target(db)
    received_kwargs = {}

    def mock_generate_rows(db_session, **kwargs):
        received_kwargs.update(kwargs)
        return [["A", "Stocks", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(
            f"/api/reports/google-sheets?target_id={target.id}&allocation_only=true"
        )
        assert response.status_code == 200
        assert received_kwargs.get("allocation_only") is True
    finally:
        _cleanup_overrides()


def test_allocation_only_defaults_false(db):
    """allocation_only defaults to False when not provided."""
    target = _create_target(db)
    received_kwargs = {}

    def mock_generate_rows(db_session, **kwargs):
        received_kwargs.update(kwargs)
        return [["A", "Stocks", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 200
        assert received_kwargs.get("allocation_only") is False
    finally:
        _cleanup_overrides()


def test_target_config_used_for_template_tab(db):
    """Template tab from target config is passed to the writer."""
    target = _create_target(db, config={"template_tab": "CustomTemplate"})
    received_args = {}

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "Stocks", "100"]]

    def mock_write(r, spreadsheet_id, template_tab):
        received_args["spreadsheet_id"] = spreadsheet_id
        received_args["template_tab"] = template_tab
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post(f"/api/reports/google-sheets?target_id={target.id}")
        assert response.status_code == 200
        assert received_args["spreadsheet_id"] == "sheet123"
        assert received_args["template_tab"] == "CustomTemplate"
    finally:
        _cleanup_overrides()
