"""Tests for the report types registry."""

from services.report_types import get_report_type, list_report_types


class TestGetReportType:
    """Tests for get_report_type()."""

    def test_known_type(self):
        """Returns config for a known report type."""
        rt = get_report_type("account_allocation")
        assert rt is not None
        assert rt.id == "account_allocation"
        assert rt.display_name == "Account Allocation"
        assert len(rt.config_fields) > 0

    def test_unknown_type(self):
        """Returns None for an unknown report type."""
        assert get_report_type("nonexistent") is None

    def test_config_fields_have_required_keys(self):
        """Each config field has key, label, and required."""
        rt = get_report_type("account_allocation")
        assert rt is not None
        for field in rt.config_fields:
            assert "key" in field
            assert "label" in field
            assert "required" in field


class TestListReportTypes:
    """Tests for list_report_types()."""

    def test_returns_all_types(self):
        """Returns a non-empty list of all registered types."""
        types = list_report_types()
        assert len(types) >= 1
        ids = [t.id for t in types]
        assert "account_allocation" in ids

    def test_returns_list(self):
        """Returns a list, not a dict or other iterable."""
        types = list_report_types()
        assert isinstance(types, list)
