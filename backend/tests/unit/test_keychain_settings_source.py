"""Tests for KeychainSettingsSource integration in config.py."""

import os
from unittest.mock import patch

from config import KeychainSettingsSource, Settings
from services.credential_manager import CREDENTIAL_KEYS

# Environment variables that would interfere with Settings defaults if
# set in the test runner's shell.  We clear them for isolation.
_ENV_VARS_TO_CLEAR = {
    "DATABASE_URL",
    "ENVIRONMENT",
    "DEBUG",
    "LOG_LEVEL",
    *CREDENTIAL_KEYS,
}


def _clean_env():
    """Return a dict suitable for ``os.environ`` patching that removes
    any variables the Settings class reads."""
    return {k: v for k, v in os.environ.items() if k not in _ENV_VARS_TO_CLEAR}


class TestKeychainSettingsSource:
    """Test the KeychainSettingsSource pydantic-settings source."""

    def test_keychain_value_overrides_default(self):
        """A credential in keychain should override the empty-string default."""
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.side_effect = lambda key: (
                "keychain-value" if key == "SNAPTRADE_CLIENT_ID" else None
            )
            s = Settings(_env_file=None)
            assert s.SNAPTRADE_CLIENT_ID == "keychain-value"

    def test_init_value_overrides_keychain(self):
        """An explicit init value should override keychain."""
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.return_value = "keychain-value"
            s = Settings(
                _env_file=None,
                SNAPTRADE_CLIENT_ID="init-value",
            )
            assert s.SNAPTRADE_CLIENT_ID == "init-value"

    def test_non_credential_fields_skip_keychain(self):
        """Fields not in CREDENTIAL_KEYS should not hit keychain."""
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.return_value = "should-not-be-used"
            s = Settings(_env_file=None)
            # DATABASE_URL should still be the default, not the mock value
            assert s.DATABASE_URL == "sqlite:///./portfolio.db"
            # Verify get_credential was never called with non-credential keys
            called_keys = [call.args[0] for call in mock_get.call_args_list]
            assert "DATABASE_URL" not in called_keys
            assert "ENVIRONMENT" not in called_keys
            assert "DEBUG" not in called_keys
            assert "LOG_LEVEL" not in called_keys

    def test_env_fallback_when_keychain_empty(self):
        """When keychain returns None, the .env/default chain still works."""
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential", return_value=None),
        ):
            s = Settings(_env_file=None)
            assert s.SNAPTRADE_CLIENT_ID == ""
            assert s.SIMPLEFIN_ACCESS_URL == ""

    def test_pem_secret_from_keychain_passes_validator(self):
        """A PEM secret with real newlines from keychain should pass
        the normalize_pem_newlines validator unchanged."""
        real_pem = "-----BEGIN EC PRIVATE KEY-----\nMIGkAg...\n-----END EC PRIVATE KEY-----\n"
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.side_effect = lambda key: (
                real_pem if key == "COINBASE_API_SECRET" else None
            )
            s = Settings(_env_file=None)
            assert s.COINBASE_API_SECRET == real_pem

    def test_source_returns_multiple_credentials(self):
        """Multiple credentials from keychain are all loaded."""
        creds = {
            "SNAPTRADE_CLIENT_ID": "cid",
            "SNAPTRADE_CONSUMER_KEY": "ckey",
            "SIMPLEFIN_ACCESS_URL": "https://example.com",
        }
        with (
            patch.dict(os.environ, _clean_env(), clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.side_effect = lambda key: creds.get(key)
            s = Settings(_env_file=None)
            assert s.SNAPTRADE_CLIENT_ID == "cid"
            assert s.SNAPTRADE_CONSUMER_KEY == "ckey"
            assert s.SIMPLEFIN_ACCESS_URL == "https://example.com"
            assert s.IBKR_FLEX_TOKEN == ""

    def test_source_is_in_priority_chain(self):
        """KeychainSettingsSource appears in the customised source tuple."""
        sources = Settings.settings_customise_sources(
            Settings,
            init_settings=object(),
            env_settings=object(),
            dotenv_settings=object(),
            file_secret_settings=object(),
        )
        source_types = [type(s) for s in sources]
        assert KeychainSettingsSource in source_types
        keychain_idx = source_types.index(KeychainSettingsSource)
        assert keychain_idx == 1

    def test_keychain_overrides_env_var(self):
        """Keychain has higher priority than env vars in the source chain."""
        env = _clean_env()
        env["SNAPTRADE_CLIENT_ID"] = "from-env"
        with (
            patch.dict(os.environ, env, clear=True),
            patch("config.get_credential") as mock_get,
        ):
            mock_get.side_effect = lambda key: (
                "from-keychain" if key == "SNAPTRADE_CLIENT_ID" else None
            )
            s = Settings(_env_file=None)
            assert s.SNAPTRADE_CLIENT_ID == "from-keychain"
