"""Tests for scripts.encrypt_database."""

import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

from scripts.encrypt_database import _is_encrypted, main


class TestIsEncrypted:
    def test_unencrypted_db(self, tmp_path):
        db_path = tmp_path / "plain.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.close()
        assert _is_encrypted(db_path) is False

    def test_encrypted_file(self, tmp_path):
        db_path = tmp_path / "encrypted.db"
        db_path.write_bytes(b"\x00" * 100)
        assert _is_encrypted(db_path) is True

    def test_empty_file(self, tmp_path):
        db_path = tmp_path / "empty.db"
        db_path.write_bytes(b"")
        assert _is_encrypted(db_path) is False

    def test_missing_file(self, tmp_path):
        db_path = tmp_path / "missing.db"
        assert _is_encrypted(db_path) is False


class TestMain:
    def test_exits_when_sqlcipher_not_installed(self):
        with (
            patch.dict(sys.modules, {"sqlcipher3": None}),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_when_db_not_found(self, tmp_path):
        mock_sqlcipher = MagicMock()
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = f"sqlite:///{tmp_path}/nonexistent.db"

        with (
            patch.dict(sys.modules, {"sqlcipher3": mock_sqlcipher}),
            patch("config.settings", mock_settings),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_when_already_encrypted(self, tmp_path):
        db_path = tmp_path / "encrypted.db"
        db_path.write_bytes(b"\x00" * 100)

        mock_sqlcipher = MagicMock()
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = f"sqlite:///{db_path}"

        with (
            patch.dict(sys.modules, {"sqlcipher3": mock_sqlcipher}),
            patch("config.settings", mock_settings),
            pytest.raises(SystemExit, match="0"),
        ):
            main()

    def test_exits_for_memory_db(self):
        mock_sqlcipher = MagicMock()
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "sqlite:///:memory:"

        with (
            patch.dict(sys.modules, {"sqlcipher3": mock_sqlcipher}),
            patch("config.settings", mock_settings),
            pytest.raises(SystemExit, match="1"),
        ):
            main()

    def test_exits_for_non_sqlite_url(self):
        mock_sqlcipher = MagicMock()
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL = "postgresql://localhost/db"

        with (
            patch.dict(sys.modules, {"sqlcipher3": mock_sqlcipher}),
            patch("config.settings", mock_settings),
            pytest.raises(SystemExit, match="1"),
        ):
            main()
