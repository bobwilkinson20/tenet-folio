"""Database setup and session management."""

import logging
import re
import secrets
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def _sqlcipher_available() -> bool:
    """Return True if the ``sqlcipher3`` package is importable."""
    try:
        import sqlcipher3  # noqa: F401

        return True
    except ImportError:
        return False


def _db_file_path(database_url: str) -> Path | None:
    """Extract the filesystem path from a ``sqlite:///`` URL.

    Returns ``None`` for in-memory databases (``:memory:`` or empty path).
    """
    if not database_url.startswith("sqlite"):
        return None
    # sqlite:///./portfolio.db  ->  ./portfolio.db
    # sqlite:///:memory:        ->  :memory:
    path_part = database_url.split("///", 1)[-1]
    if not path_part or path_part == ":memory:":
        return None
    return Path(path_part)


def _is_encrypted_db(path: Path) -> bool:
    """Check whether a database file is encrypted.

    An unencrypted SQLite file starts with the 16-byte magic header
    ``SQLite format 3\\0``. If the first bytes differ (or the file is
    empty), it is assumed to be encrypted.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        if len(header) == 0:
            return False  # empty file, not encrypted
        return header != b"SQLite format 3\x00"
    except OSError:
        return False


def _resolve_sqlcipher_key(database_url: str) -> str | None:
    """Determine the SQLCipher key to use, implementing the activation logic.

    Returns the hex key string if SQLCipher should be used, or ``None``
    to fall back to plain SQLite.

    Raises ``RuntimeError`` if an encrypted DB exists but no key is available.
    """
    configured_key = settings.SQLCIPHER_KEY

    if configured_key:
        _validate_hex_key(configured_key)
        logger.info("SQLCipher key found — using encrypted database")
        return configured_key

    # No key configured
    db_path = _db_file_path(database_url)

    if db_path is None:
        # In-memory database — no encryption
        return None

    if not db_path.exists():
        # Fresh install: auto-generate key and store in keychain
        key = secrets.token_hex(32)
        from services.credential_manager import set_credential

        if set_credential("SQLCIPHER_KEY", key):
            logger.info(
                "Generated new SQLCipher key and stored in keychain — "
                "new database will be encrypted"
            )
            return key
        else:
            logger.warning(
                "Could not store SQLCipher key in keychain — "
                "creating unencrypted database"
            )
            return None

    # DB file exists but no key
    if _is_encrypted_db(db_path):
        raise RuntimeError(
            f"Database file '{db_path}' is encrypted but no SQLCIPHER_KEY "
            "is configured. Add the key to macOS Keychain or set the "
            "SQLCIPHER_KEY environment variable."
        )

    # Unencrypted legacy DB, no key — backward compatibility
    logger.info(
        "Existing unencrypted database detected. Run "
        "'python -m scripts.encrypt_database' to encrypt it."
    )
    return None


_HEX_KEY_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_hex_key(key: str) -> str:
    """Validate that a key is a 64-char lowercase hex string (256-bit).

    Returns the validated key, or raises ``ValueError``.
    """
    if not _HEX_KEY_RE.match(key):
        raise ValueError(
            "Invalid SQLCipher key format — expected 64 hex characters"
        )
    return key


def _attach_pragma_key(engine, raw_hex_key: str) -> None:
    """Register a ``connect`` event listener that issues ``PRAGMA key``."""
    _validate_hex_key(raw_hex_key)

    @event.listens_for(engine, "connect")
    def _set_key(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute(f"PRAGMA key=\"x'{raw_hex_key}'\"")
        cursor.close()


@lru_cache
def get_engine():
    """Get or create the database engine (cached).

    When ``sqlcipher3`` is installed and a key is resolved, the engine
    uses the ``sqlcipher3.dbapi2`` DBAPI module and issues ``PRAGMA key``
    on every connection.  Otherwise, the standard ``sqlite3`` module is
    used (current behavior).
    """
    connect_args = {}
    database_url = settings.DATABASE_URL

    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    use_sqlcipher = _sqlcipher_available()
    key = None

    if use_sqlcipher and database_url.startswith("sqlite"):
        key = _resolve_sqlcipher_key(database_url)

    if key:
        import sqlcipher3

        engine = create_engine(
            database_url,
            connect_args=connect_args,
            echo=False,
            module=sqlcipher3.dbapi2,
        )
        _attach_pragma_key(engine, key)
        logger.info("Database engine created with SQLCipher encryption")
    else:
        engine = create_engine(
            database_url,
            connect_args=connect_args,
            echo=False,
        )

    return engine


def get_session_local():
    """Get a sessionmaker bound to the engine."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db():
    """Dependency that provides a database session.

    Transaction conventions:
    - Default: services ``flush()``, API layer ``commit()``
    - Exceptions that commit internally:
      - ``ManualHoldingsService``: uses ``BEGIN IMMEDIATE`` for write locking
      - ``SyncService.trigger_sync()``: multi-step pipeline with own commit
      - ``PreferenceService.set()``: ``IntegrityError`` retry with rollback
    """
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
