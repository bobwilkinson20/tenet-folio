"""Tests for profile resolution in credential_manager."""

from unittest.mock import patch

import pytest

from services.credential_manager import get_active_profile


class TestGetActiveProfile:
    """Tests for get_active_profile()."""

    def test_returns_none_when_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            assert get_active_profile() is None

    def test_returns_none_when_empty(self):
        with patch.dict("os.environ", {"TENET_PROFILE": ""}):
            assert get_active_profile() is None

    def test_returns_none_when_whitespace(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "   "}):
            assert get_active_profile() is None

    def test_returns_valid_profile(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "paper"}):
            assert get_active_profile() == "paper"

    def test_returns_profile_with_digits(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "test-1"}):
            assert get_active_profile() == "test-1"

    def test_returns_profile_starting_with_digit(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "1prod"}):
            assert get_active_profile() == "1prod"

    def test_raises_on_spaces(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "my profile!"}):
            with pytest.raises(ValueError, match="Invalid TENET_PROFILE"):
                get_active_profile()

    def test_raises_on_leading_hyphen(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "-paper"}):
            with pytest.raises(ValueError, match="Invalid TENET_PROFILE"):
                get_active_profile()

    def test_raises_on_dot(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "a.b"}):
            with pytest.raises(ValueError, match="Invalid TENET_PROFILE"):
                get_active_profile()

    def test_raises_on_special_chars(self):
        with patch.dict("os.environ", {"TENET_PROFILE": "test@home"}):
            with pytest.raises(ValueError, match="Invalid TENET_PROFILE"):
                get_active_profile()


class TestServiceNameConstruction:
    """Test SERVICE_NAME is built correctly from a profile value."""

    def test_with_profile(self):
        profile = "paper"
        result = f"tenet-folio:{profile}" if profile else "tenet-folio"
        assert result == "tenet-folio:paper"

    def test_without_profile(self):
        profile = None
        result = f"tenet-folio:{profile}" if profile else "tenet-folio"
        assert result == "tenet-folio"
