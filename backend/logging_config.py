"""Centralized logging configuration."""

import logging

from config import settings


def setup_logging() -> None:
    """Configure logging for the application.

    Sets root logger level from settings.LOG_LEVEL and suppresses
    noisy third-party loggers to WARNING.
    """
    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        level=getattr(logging, settings.LOG_LEVEL),
        force=True,
    )

    # Suppress noisy third-party loggers
    for name in (
        "sqlalchemy.engine",
        "sqlalchemy.pool",
        "httpx",
        "httpcore",
        "urllib3",
        "yfinance",
        "peewee",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
