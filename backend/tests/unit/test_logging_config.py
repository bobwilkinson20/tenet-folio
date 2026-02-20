"""Tests for centralized logging configuration."""

import logging

import pytest
from pydantic import ValidationError

from logging_config import setup_logging


class TestSetupLogging:
    """Tests for setup_logging()."""

    def test_root_logger_level_default_info(self, monkeypatch):
        """Default LOG_LEVEL should set root logger to INFO."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        # Re-import settings so the monkeypatched env is picked up
        from config import Settings
        test_settings = Settings()
        monkeypatch.setattr("logging_config.settings", test_settings)

        setup_logging()

        assert logging.getLogger().level == logging.INFO

    def test_root_logger_level_from_settings(self, monkeypatch):
        """LOG_LEVEL setting should control root logger level."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        from config import Settings
        test_settings = Settings()
        monkeypatch.setattr("logging_config.settings", test_settings)

        setup_logging()

        assert logging.getLogger().level == logging.DEBUG

    def test_sqlalchemy_loggers_suppressed(self, monkeypatch):
        """SQLAlchemy loggers should be set to WARNING."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        from config import Settings
        test_settings = Settings()
        monkeypatch.setattr("logging_config.settings", test_settings)

        setup_logging()

        assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
        assert logging.getLogger("sqlalchemy.pool").level == logging.WARNING

    def test_third_party_loggers_suppressed(self, monkeypatch):
        """Noisy third-party loggers should be set to WARNING."""
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        from config import Settings
        test_settings = Settings()
        monkeypatch.setattr("logging_config.settings", test_settings)

        setup_logging()

        for name in ("httpx", "httpcore", "urllib3", "yfinance", "peewee"):
            assert logging.getLogger(name).level == logging.WARNING, (
                f"{name} logger not suppressed"
            )

    def test_invalid_log_level_rejected(self, monkeypatch):
        """Invalid LOG_LEVEL values should raise a validation error."""
        monkeypatch.setenv("LOG_LEVEL", "VERBOS")
        from config import Settings
        with pytest.raises(ValidationError, match="LOG_LEVEL"):
            Settings()

    def test_log_level_case_insensitive(self, monkeypatch):
        """LOG_LEVEL should accept lowercase values."""
        monkeypatch.setenv("LOG_LEVEL", "debug")
        from config import Settings
        test_settings = Settings()
        assert test_settings.LOG_LEVEL == "DEBUG"
