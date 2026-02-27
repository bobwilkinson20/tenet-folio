"""Integration tests for reports API endpoints."""

from fastapi.testclient import TestClient

from api.reports import get_report_row_generator, get_sheets_writer
from database import get_db
from main import app
from services.google_sheets_service import GoogleSheetsError, GoogleSheetsNotConfiguredError


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
    rows = [
        ["Account A", "Stocks", "1000.00"],
        ["/", "Bonds", "500.00"],
    ]

    def mock_generate_rows(db_session, **kwargs):
        return rows

    def mock_write(r):
        return "2026-02-25 14:30 UTC"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 200
        data = response.json()
        assert data["tab_name"] == "2026-02-25 14:30 UTC"
        assert data["rows_written"] == 2
    finally:
        _cleanup_overrides()


def test_400_no_data(db):
    """Returns 400 when no portfolio data is available."""

    def mock_generate_rows(db_session, **kwargs):
        return []

    def mock_write(r):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 400
        assert "no portfolio data" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_502_sheets_api_error(db):
    """Returns 502 when Google Sheets API fails."""

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "B", "100"]]

    def mock_write(r):
        raise GoogleSheetsError("API quota exceeded")

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 502
        assert "failed to write" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_503_not_configured(db):
    """Returns 503 when Google Sheets is not configured."""

    def mock_generate_rows(db_session, **kwargs):
        return [["A", "B", "100"]]

    def mock_write(r):
        raise GoogleSheetsNotConfiguredError("Google Sheets is not configured. Set GOOGLE_SHEETS_CREDENTIALS_FILE.")

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_500_generate_failure(db):
    """Returns 500 when row generation fails unexpectedly."""

    def mock_generate_rows(db_session, **kwargs):
        raise RuntimeError("Unexpected DB error")

    def mock_write(r):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 500
        assert "failed to generate" in response.json()["detail"].lower()
    finally:
        _cleanup_overrides()


def test_allocation_only_passed_to_generator(db):
    """allocation_only query param is forwarded to the row generator."""
    received_kwargs = {}

    def mock_generate_rows(db_session, **kwargs):
        received_kwargs.update(kwargs)
        return [["A", "Stocks", "100"]]

    def mock_write(r):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets?allocation_only=true")
        assert response.status_code == 200
        assert received_kwargs.get("allocation_only") is True
    finally:
        _cleanup_overrides()


def test_allocation_only_defaults_false(db):
    """allocation_only defaults to False when not provided."""
    received_kwargs = {}

    def mock_generate_rows(db_session, **kwargs):
        received_kwargs.update(kwargs)
        return [["A", "Stocks", "100"]]

    def mock_write(r):
        return "tab"

    client = _make_client(db, mock_generate_rows, mock_write)
    try:
        response = client.post("/api/reports/google-sheets")
        assert response.status_code == 200
        assert received_kwargs.get("allocation_only") is False
    finally:
        _cleanup_overrides()
