"""Tests for SecurityService."""

from models import Security
from services.security_service import SecurityService


class TestEnsureExists:
    """Tests for SecurityService.ensure_exists."""

    def test_creates_security_when_missing(self, db):
        """Creates a new Security record when the ticker doesn't exist."""
        security = SecurityService.ensure_exists(db, "AAPL", "Apple Inc.")
        assert security.ticker == "AAPL"
        assert security.name == "Apple Inc."
        assert db.query(Security).count() == 1

    def test_uses_ticker_as_name_when_name_not_provided(self, db):
        """Falls back to ticker for name when no name is given."""
        security = SecurityService.ensure_exists(db, "AAPL")
        assert security.name == "AAPL"

    def test_returns_existing_security(self, db):
        """Returns the existing record without creating a duplicate."""
        existing = Security(ticker="AAPL", name="Apple Inc.")
        db.add(existing)
        db.flush()

        security = SecurityService.ensure_exists(db, "AAPL")
        assert security.id == existing.id
        assert db.query(Security).count() == 1

    def test_fills_missing_name_by_default(self, db):
        """When update_name=False, fills in a missing name."""
        existing = Security(ticker="AAPL", name=None)
        db.add(existing)
        db.flush()

        security = SecurityService.ensure_exists(db, "AAPL", "Apple Inc.")
        assert security.name == "Apple Inc."

    def test_does_not_overwrite_existing_name_by_default(self, db):
        """When update_name=False, preserves an existing name."""
        existing = Security(ticker="AAPL", name="Old Name")
        db.add(existing)
        db.flush()

        security = SecurityService.ensure_exists(db, "AAPL", "New Name")
        assert security.name == "Old Name"

    def test_overwrites_name_when_update_name_true(self, db):
        """When update_name=True, overwrites the existing name."""
        existing = Security(ticker="_MAN:abc123", name="Old Description")
        db.add(existing)
        db.flush()

        security = SecurityService.ensure_exists(
            db, "_MAN:abc123", "New Description", update_name=True
        )
        assert security.name == "New Description"

    def test_does_not_overwrite_when_name_is_none(self, db):
        """Even with update_name=True, a None name doesn't clear existing."""
        existing = Security(ticker="AAPL", name="Apple Inc.")
        db.add(existing)
        db.flush()

        security = SecurityService.ensure_exists(
            db, "AAPL", None, update_name=True
        )
        assert security.name == "Apple Inc."
