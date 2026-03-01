"""Tests for FRONTEND_URL and profile-aware DATABASE_URL settings."""

import os
from unittest.mock import patch

from config import Settings
from services.credential_manager import CREDENTIAL_KEYS

_ENV_VARS_TO_CLEAR = {
    "DATABASE_URL",
    "ENVIRONMENT",
    "DEBUG",
    "LOG_LEVEL",
    "FRONTEND_URL",
    *CREDENTIAL_KEYS,
}


def _clean_env():
    return {k: v for k, v in os.environ.items() if k not in _ENV_VARS_TO_CLEAR}


class TestFrontendUrlSetting:
    def test_defaults_to_localhost_5173(self):
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential", return_value=None),
        ):
            s = Settings(_env_file=None)
            assert s.FRONTEND_URL == "http://localhost:5173"

    def test_overridden_by_env_var(self):
        env = _clean_env()
        env["FRONTEND_URL"] = "http://localhost:5174"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("config.get_credential", return_value=None),
        ):
            s = Settings(_env_file=None)
            assert s.FRONTEND_URL == "http://localhost:5174"


class TestProfileDatabaseUrl:
    """Test that the model_validator rewrites DATABASE_URL for active profiles."""

    def test_no_profile_keeps_default(self):
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential", return_value=None),
            patch("config.ACTIVE_PROFILE", None),
        ):
            s = Settings(_env_file=None)
            assert s.DATABASE_URL == "sqlite:///./portfolio.db"

    def test_profile_rewrites_default(self):
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential", return_value=None),
            patch("config.ACTIVE_PROFILE", "paper"),
        ):
            s = Settings(_env_file=None)
            assert s.DATABASE_URL == "sqlite:///./portfolio-paper.db"

    def test_profile_rewrites_env_var_default(self):
        """Even when DATABASE_URL is explicitly set to the standard default
        value, the profile suffix is still applied."""
        env = _clean_env()
        env["DATABASE_URL"] = "sqlite:///./portfolio.db"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("config.get_credential", return_value=None),
            patch("config.ACTIVE_PROFILE", "paper"),
        ):
            s = Settings(_env_file=None)
            assert s.DATABASE_URL == "sqlite:///./portfolio-paper.db"

    def test_profile_leaves_custom_url_alone(self):
        """A user-specified non-default DATABASE_URL is never rewritten."""
        env = _clean_env()
        env["DATABASE_URL"] = "sqlite:///./my-custom.db"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("config.get_credential", return_value=None),
            patch("config.ACTIVE_PROFILE", "paper"),
        ):
            s = Settings(_env_file=None)
            assert s.DATABASE_URL == "sqlite:///./my-custom.db"
