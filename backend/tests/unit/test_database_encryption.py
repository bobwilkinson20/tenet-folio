"""Tests for SQLCipher database encryption in database.py."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from database import (
    _db_file_path,
    _is_encrypted_db,
    _resolve_sqlcipher_key,
    _sqlcipher_available,
    _validate_hex_key,
)


# ---------------------------------------------------------------------------
# _sqlcipher_available
# ---------------------------------------------------------------------------


class TestSqlcipherAvailable:
    def test_returns_true_when_installed(self):
        mock_mod = MagicMock()
        with patch.dict(sys.modules, {"sqlcipher3": mock_mod}):
            assert _sqlcipher_available() is True

    def test_returns_false_when_not_installed(self):
        with patch.dict(sys.modules, {"sqlcipher3": None}):
            assert _sqlcipher_available() is False


# ---------------------------------------------------------------------------
# _db_file_path
# ---------------------------------------------------------------------------


class TestDbFilePath:
    def test_sqlite_relative_path(self):
        result = _db_file_path("sqlite:///./portfolio.db")
        assert result == Path("./portfolio.db")

    def test_sqlite_absolute_path(self):
        result = _db_file_path("sqlite:////tmp/test.db")
        assert result == Path("/tmp/test.db")

    def test_memory_db_returns_none(self):
        assert _db_file_path("sqlite:///:memory:") is None

    def test_non_sqlite_returns_none(self):
        assert _db_file_path("postgresql://localhost/mydb") is None

    def test_empty_path_returns_none(self):
        assert _db_file_path("sqlite:///") is None


# ---------------------------------------------------------------------------
# _is_encrypted_db
# ---------------------------------------------------------------------------


class TestIsEncryptedDb:
    def test_unencrypted_db(self, tmp_path):
        db_path = tmp_path / "plain.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        assert _is_encrypted_db(db_path) is False

    def test_encrypted_db(self, tmp_path):
        db_path = tmp_path / "encrypted.db"
        # Write non-SQLite header bytes to simulate encrypted file
        db_path.write_bytes(b"\x00" * 100)
        assert _is_encrypted_db(db_path) is True

    def test_empty_file(self, tmp_path):
        db_path = tmp_path / "empty.db"
        db_path.write_bytes(b"")
        assert _is_encrypted_db(db_path) is False

    def test_missing_file(self, tmp_path):
        db_path = tmp_path / "nonexistent.db"
        assert _is_encrypted_db(db_path) is False


# ---------------------------------------------------------------------------
# _validate_hex_key
# ---------------------------------------------------------------------------


class TestValidateHexKey:
    def test_accepts_valid_key(self):
        key = "a" * 64
        assert _validate_hex_key(key) == key

    def test_accepts_mixed_hex(self):
        key = "0123456789abcdef" * 4
        assert _validate_hex_key(key) == key

    def test_rejects_too_short(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("abcd")

    def test_rejects_too_long(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("a" * 65)

    def test_rejects_non_hex(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("g" * 64)

    def test_rejects_uppercase(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("A" * 64)

    def test_rejects_injection_attempt(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("' OR 1=1 --")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="64 hex characters"):
            _validate_hex_key("")


# ---------------------------------------------------------------------------
# _resolve_sqlcipher_key
# ---------------------------------------------------------------------------

VALID_KEY = "a" * 64


class TestResolveSqlcipherKey:
    def test_returns_configured_key(self):
        """When SQLCIPHER_KEY is set in settings, return it."""
        with patch("database.settings") as mock_settings:
            mock_settings.SQLCIPHER_KEY = VALID_KEY
            result = _resolve_sqlcipher_key("sqlite:///./portfolio.db")
        assert result == VALID_KEY

    def test_rejects_invalid_configured_key(self):
        """When SQLCIPHER_KEY is set but invalid, raise ValueError."""
        with patch("database.settings") as mock_settings:
            mock_settings.SQLCIPHER_KEY = "not-a-hex-key"
            with pytest.raises(ValueError, match="64 hex characters"):
                _resolve_sqlcipher_key("sqlite:///./portfolio.db")

    def test_memory_db_returns_none(self):
        """In-memory databases should never use encryption."""
        with patch("database.settings") as mock_settings:
            mock_settings.SQLCIPHER_KEY = ""
            result = _resolve_sqlcipher_key("sqlite:///:memory:")
        assert result is None

    def test_fresh_install_autogenerates_key(self, tmp_path):
        """When no DB exists and no key, auto-generate and store."""
        db_path = tmp_path / "new.db"
        url = f"sqlite:///{db_path}"
        with (
            patch("database.settings") as mock_settings,
            patch("services.credential_manager.set_credential", return_value=True) as mock_set,
        ):
            mock_settings.SQLCIPHER_KEY = ""
            result = _resolve_sqlcipher_key(url)

        assert result is not None
        assert len(result) == 64  # 32 bytes hex = 64 chars
        mock_set.assert_called_once_with("SQLCIPHER_KEY", result)

    def test_fresh_install_no_keychain_returns_none(self, tmp_path):
        """When no DB and keychain storage fails, return None."""
        db_path = tmp_path / "new.db"
        url = f"sqlite:///{db_path}"
        with (
            patch("database.settings") as mock_settings,
            patch("services.credential_manager.set_credential", return_value=False),
        ):
            mock_settings.SQLCIPHER_KEY = ""
            result = _resolve_sqlcipher_key(url)

        assert result is None

    def test_unencrypted_legacy_db_returns_none(self, tmp_path):
        """Existing unencrypted DB with no key → backward compat."""
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()

        url = f"sqlite:///{db_path}"
        with patch("database.settings") as mock_settings:
            mock_settings.SQLCIPHER_KEY = ""
            result = _resolve_sqlcipher_key(url)

        assert result is None

    def test_encrypted_db_no_key_raises(self, tmp_path):
        """Encrypted DB with no key → RuntimeError."""
        db_path = tmp_path / "encrypted.db"
        db_path.write_bytes(b"\x00" * 100)  # non-SQLite header

        url = f"sqlite:///{db_path}"
        with patch("database.settings") as mock_settings:
            mock_settings.SQLCIPHER_KEY = ""
            with pytest.raises(RuntimeError, match="encrypted but no SQLCIPHER_KEY"):
                _resolve_sqlcipher_key(url)


# ---------------------------------------------------------------------------
# get_engine (integration-level, no actual sqlcipher3 needed)
# ---------------------------------------------------------------------------


class TestGetEngine:
    def test_plain_engine_without_sqlcipher(self):
        """Without sqlcipher3, get_engine returns a plain SQLite engine."""
        from database import get_engine

        get_engine.cache_clear()
        try:
            with (
                patch("database._sqlcipher_available", return_value=False),
                patch("database.settings") as mock_settings,
            ):
                mock_settings.DATABASE_URL = "sqlite:///:memory:"
                engine = get_engine()
            assert engine is not None
            assert str(engine.url).startswith("sqlite")
        finally:
            get_engine.cache_clear()

    def test_plain_engine_with_no_key(self):
        """With sqlcipher3 available but no key, returns plain engine."""
        from database import get_engine

        get_engine.cache_clear()
        try:
            with (
                patch("database._sqlcipher_available", return_value=True),
                patch("database._resolve_sqlcipher_key", return_value=None),
                patch("database.settings") as mock_settings,
            ):
                mock_settings.DATABASE_URL = "sqlite:///:memory:"
                engine = get_engine()
            assert engine is not None
            assert str(engine.url).startswith("sqlite")
        finally:
            get_engine.cache_clear()
