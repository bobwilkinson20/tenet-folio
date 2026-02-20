"""Tests for scripts.migrate_env_to_keychain."""

from unittest.mock import patch

import pytest

from scripts.migrate_env_to_keychain import _clean_env_file, migrate


@pytest.fixture
def env_file(tmp_path):
    """Create a temporary .env file with sample content."""
    p = tmp_path / ".env"
    p.write_text(
        "# Database config\n"
        "DATABASE_URL=sqlite:///./portfolio.db\n"
        "ENVIRONMENT=development\n"
        "\n"
        "# SnapTrade\n"
        "SNAPTRADE_CLIENT_ID=my-client-id\n"
        "SNAPTRADE_CONSUMER_KEY=my-consumer-key\n"
        "SNAPTRADE_USER_ID=my-user\n"
        "SNAPTRADE_USER_SECRET=\n"
        "\n"
        "# SimpleFIN\n"
        "SIMPLEFIN_ACCESS_URL=https://example.com/access\n"
    )
    return p


class TestMigrate:
    def test_migrates_non_empty_credentials(self, env_file, capsys):
        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True) as mock_set,
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(env_file)

        # Should store 4 non-empty credential values
        stored_keys = {call.args[0] for call in mock_set.call_args_list}
        assert "SNAPTRADE_CLIENT_ID" in stored_keys
        assert "SNAPTRADE_CONSUMER_KEY" in stored_keys
        assert "SNAPTRADE_USER_ID" in stored_keys
        assert "SIMPLEFIN_ACCESS_URL" in stored_keys
        # SNAPTRADE_USER_SECRET is empty so should NOT be stored
        assert "SNAPTRADE_USER_SECRET" not in stored_keys

        output = capsys.readouterr().out
        assert "Stored in keychain (4)" in output

    def test_skips_empty_values(self, env_file, capsys):
        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True),
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(env_file)

        output = capsys.readouterr().out
        assert "SNAPTRADE_USER_SECRET" in output
        assert "Skipped (empty/missing in .env)" in output

    def test_skips_already_stored(self, env_file, capsys):
        def fake_get(key):
            if key == "SNAPTRADE_CLIENT_ID":
                return "my-client-id"
            return None

        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True) as mock_set,
            patch("scripts.migrate_env_to_keychain.get_credential", side_effect=fake_get),
        ):
            migrate(env_file)

        stored_keys = {call.args[0] for call in mock_set.call_args_list}
        assert "SNAPTRADE_CLIENT_ID" not in stored_keys

        output = capsys.readouterr().out
        assert "Already in keychain" in output
        assert "SNAPTRADE_CLIENT_ID" in output

    def test_reports_failures(self, env_file, capsys):
        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=False),
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(env_file)

        output = capsys.readouterr().out
        assert "Failed" in output

    def test_exits_when_env_file_missing(self, tmp_path):
        missing = tmp_path / ".env"
        with pytest.raises(SystemExit):
            migrate(missing)

    def test_skips_non_credential_keys(self, env_file):
        """DATABASE_URL and ENVIRONMENT should never be stored."""
        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True) as mock_set,
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(env_file)

        stored_keys = {call.args[0] for call in mock_set.call_args_list}
        assert "DATABASE_URL" not in stored_keys
        assert "ENVIRONMENT" not in stored_keys


class TestCleanEnvFile:
    def test_removes_migrated_keys(self, env_file):
        _clean_env_file(env_file, ["SNAPTRADE_CLIENT_ID", "SIMPLEFIN_ACCESS_URL"])
        content = env_file.read_text()

        assert "SNAPTRADE_CLIENT_ID" not in content
        assert "SIMPLEFIN_ACCESS_URL" not in content
        # Non-credential lines preserved
        assert "DATABASE_URL" in content
        assert "ENVIRONMENT" in content
        # Comments preserved
        assert "# Database config" in content
        # Other credentials preserved
        assert "SNAPTRADE_CONSUMER_KEY" in content

    def test_preserves_comments_and_blank_lines(self, env_file):
        _clean_env_file(env_file, ["SNAPTRADE_CLIENT_ID"])
        content = env_file.read_text()
        assert "# SnapTrade" in content
        assert "# Database config" in content

    def test_clean_flag_triggers_file_rewrite(self, env_file, capsys):
        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True),
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(env_file, clean=True)

        content = env_file.read_text()
        # Migrated credentials should be removed
        assert "SNAPTRADE_CLIENT_ID=" not in content
        assert "SIMPLEFIN_ACCESS_URL=" not in content
        # Non-credentials preserved
        assert "DATABASE_URL=" in content

        output = capsys.readouterr().out
        assert "Removed" in output

    def test_clean_no_op_when_nothing_migrated(self, tmp_path, capsys):
        p = tmp_path / ".env"
        p.write_text("DATABASE_URL=sqlite:///./portfolio.db\n")

        with (
            patch("scripts.migrate_env_to_keychain.set_credential", return_value=True),
            patch("scripts.migrate_env_to_keychain.get_credential", return_value=None),
        ):
            migrate(p, clean=True)

        output = capsys.readouterr().out
        assert "Nothing to clean" in output
