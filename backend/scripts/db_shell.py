"""Interactive SQL shell for the portfolio database.

Opens a Python-based SQL shell that automatically handles SQLCipher
decryption when the database is encrypted.

Usage::

    cd backend
    uv run python -m scripts.db_shell
"""

import readline  # noqa: F401 — enables arrow-key history in input()
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    from config import settings
    from database import _db_file_path, _is_encrypted_db, _validate_hex_key
    from services.credential_manager import get_credential

    database_url = settings.DATABASE_URL
    db_path = _db_file_path(database_url)

    if db_path is None:
        print("ERROR: Cannot open shell for in-memory database.")
        sys.exit(1)

    if not db_path.exists():
        print(f"ERROR: Database file not found: {db_path}")
        sys.exit(1)

    encrypted = _is_encrypted_db(db_path)

    if encrypted:
        try:
            import sqlcipher3
        except ImportError:
            print("ERROR: Database is encrypted but sqlcipher3 is not installed.")
            sys.exit(1)

        key = get_credential("SQLCIPHER_KEY") or settings.SQLCIPHER_KEY
        if not key:
            print("ERROR: Database is encrypted but no SQLCIPHER_KEY found.")
            sys.exit(1)

        try:
            _validate_hex_key(key)
        except ValueError:
            print("ERROR: SQLCIPHER_KEY is not a valid 64-character hex string.")
            sys.exit(1)

        conn = sqlcipher3.connect(str(db_path))
        conn.execute(f"PRAGMA key=\"x'{key}'\"")
        print(f"Connected to encrypted database: {db_path}")
    else:
        import sqlite3

        conn = sqlite3.connect(str(db_path))
        print(f"Connected to database: {db_path}")

    print("Type SQL statements or dot-commands (.help for list). .quit to exit.\n")

    def _run_query(sql):
        """Execute a SQL query and print results."""
        cursor = conn.execute(sql)
        if cursor.description:
            headers = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            print(" | ".join(headers))
            print("-+-".join("-" * len(h) for h in headers))
            for row in rows:
                print(" | ".join(str(v) for v in row))
            print(f"({len(rows)} rows)")
        else:
            conn.commit()
            print(f"OK ({conn.total_changes} total changes)")

    def _handle_dot_command(cmd):
        """Handle sqlite3-style dot-commands. Returns False to quit."""
        parts = cmd.split(None, 1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if command in (".quit", ".exit"):
            return False
        elif command == ".tables":
            _run_query(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "ORDER BY name"
            )
        elif command == ".schema":
            if arg:
                _run_query(
                    "SELECT sql FROM sqlite_master "
                    f"WHERE name='{arg}' AND sql IS NOT NULL"
                )
            else:
                _run_query(
                    "SELECT sql FROM sqlite_master "
                    "WHERE sql IS NOT NULL ORDER BY name"
                )
        elif command == ".indexes":
            if arg:
                _run_query(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    f"AND tbl_name='{arg}' ORDER BY name"
                )
            else:
                _run_query(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "ORDER BY name"
                )
        elif command == ".count":
            if not arg:
                print("Usage: .count TABLE_NAME")
            else:
                _run_query(f"SELECT count(*) AS count FROM {arg}")
        elif command == ".help":
            print(".tables              List all tables")
            print(".schema [TABLE]      Show CREATE statements")
            print(".indexes [TABLE]     List indexes")
            print(".count TABLE         Count rows in a table")
            print(".quit                Exit the shell")
        else:
            print(f"Unknown command: {command} (try .help)")
        return True

    try:
        while True:
            try:
                sql = input("sql> ").strip()
            except EOFError:
                break

            if not sql:
                continue

            if sql.startswith("."):
                if not _handle_dot_command(sql):
                    break
                continue

            try:
                _run_query(sql)
            except Exception as e:
                print(f"ERROR: {e}")
    finally:
        conn.close()
        print("\nDisconnected.")


if __name__ == "__main__":
    main()
