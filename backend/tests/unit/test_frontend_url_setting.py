"""Tests for FRONTEND_URL setting."""

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
