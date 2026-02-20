"""Encrypt an existing unencrypted SQLite database with SQLCipher.

Usage::

    cd backend
    uv run python -m scripts.encrypt_database

The script:
1. Validates the database exists and is unencrypted
2. Gets or generates a SQLCIPHER_KEY (stored in keychain)
3. Uses SQLCipher's ``sqlcipher_export`` to create an encrypted copy
4. Verifies the encrypted copy is readable
5. Backs up the original as ``.bak`` and swaps in the encrypted version
"""

import secrets
import shutil
import sys
from pathlib import Path

# Ensure the backend directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _is_encrypted(path: Path) -> bool:
    """Check if a file is an encrypted (non-SQLite) database."""
    try:
        with open(path, "rb") as f:
            header = f.read(16)
        if len(header) == 0:
            return False
        return header != b"SQLite format 3\x00"
    except OSError:
        return False


def main() -> None:
    try:
        import sqlcipher3  # noqa: F401
    except ImportError:
        print("ERROR: sqlcipher3 is not installed.")
        print("Install it with: uv add sqlcipher3")
        sys.exit(1)

    from config import settings
    from services.credential_manager import get_credential, set_credential

    # Resolve database path
    database_url = settings.DATABASE_URL
    if not database_url.startswith("sqlite:///"):
        print(f"ERROR: Unsupported database URL: {database_url}")
        sys.exit(1)

    path_part = database_url.split("///", 1)[-1]
    if not path_part or path_part == ":memory:":
        print("ERROR: Cannot encrypt an in-memory database.")
        sys.exit(1)

    db_path = Path(path_part)
    if not db_path.exists():
        print(f"ERROR: Database file not found: {db_path}")
        sys.exit(1)

    if _is_encrypted(db_path):
        print(f"Database '{db_path}' is already encrypted.")
        sys.exit(0)

    # Get or generate key
    from database import _validate_hex_key

    key = get_credential("SQLCIPHER_KEY") or settings.SQLCIPHER_KEY
    if not key:
        key = secrets.token_hex(32)
        if set_credential("SQLCIPHER_KEY", key):
            print("Generated new SQLCipher key and stored in keychain.")
        else:
            print(
                "WARNING: Could not store key in keychain. "
                "Set SQLCIPHER_KEY environment variable manually."
            )
            print(f"Key: {key}")

    try:
        _validate_hex_key(key)
    except ValueError:
        print("ERROR: SQLCIPHER_KEY is not a valid 64-character hex string.")
        sys.exit(1)

    # Create encrypted copy using sqlcipher_export
    encrypted_path = db_path.with_suffix(".db.enc")
    if encrypted_path.exists():
        encrypted_path.unlink()

    print(f"Encrypting '{db_path}' ...")

    import sqlcipher3

    conn = sqlcipher3.connect(str(db_path))
    try:
        conn.execute(f"ATTACH DATABASE '{encrypted_path}' AS encrypted "
                     f"KEY \"x'{key}'\"")
        conn.execute("SELECT sqlcipher_export('encrypted')")
        conn.execute("DETACH DATABASE encrypted")
    finally:
        conn.close()

    # Verify the encrypted copy
    print("Verifying encrypted database ...")
    verify_conn = sqlcipher3.connect(str(encrypted_path))
    try:
        verify_conn.execute(f"PRAGMA key=\"x'{key}'\"")
        result = verify_conn.execute(
            "SELECT count(*) FROM sqlite_master"
        ).fetchone()
        table_count = result[0]
        print(f"  Verified: {table_count} tables/indexes found.")
    except Exception as e:
        print(f"ERROR: Verification failed: {e}")
        encrypted_path.unlink(missing_ok=True)
        sys.exit(1)
    finally:
        verify_conn.close()

    # Backup original and swap
    backup_path = db_path.with_suffix(".db.bak")
    print(f"Backing up original to '{backup_path}' ...")
    shutil.copy2(db_path, backup_path)

    print("Swapping encrypted database into place ...")
    shutil.move(str(encrypted_path), str(db_path))

    print("Done! Database is now encrypted with SQLCipher.")
    print("The original unencrypted backup is at: " + str(backup_path))


if __name__ == "__main__":
    main()
