#!/usr/bin/env python3
"""Migrate provider credentials from .env to macOS Keychain.

Reads the backend ``.env`` file, stores each non-empty credential in the
system keychain via ``keyring``, and prints a summary.  Supports a
``--clean`` flag that removes migrated keys from ``.env`` (preserves
non-secret config lines and comments).

Usage:
    python -m scripts.migrate_env_to_keychain           # migrate only
    python -m scripts.migrate_env_to_keychain --clean    # migrate & remove from .env
"""

import argparse
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import dotenv_values

from services.credential_manager import CREDENTIAL_KEYS, get_credential, set_credential


def migrate(env_path: Path, *, clean: bool = False) -> None:
    """Read ``.env`` and store credentials in keychain.

    Args:
        env_path: Path to the ``.env`` file.
        clean: If ``True``, rewrite the ``.env`` file without the
            migrated credential lines.
    """
    if not env_path.exists():
        print(f"No .env file found at {env_path}")
        sys.exit(1)

    values = dotenv_values(env_path)

    migrated: list[str] = []
    skipped_empty: list[str] = []
    skipped_exists: list[str] = []
    failed: list[str] = []

    for key in sorted(CREDENTIAL_KEYS):
        value = values.get(key)
        if not value:
            skipped_empty.append(key)
            continue

        # Check if already stored in keychain with the same value
        existing = get_credential(key)
        if existing == value:
            skipped_exists.append(key)
            continue

        if set_credential(key, value):
            migrated.append(key)
        else:
            failed.append(key)

    # Print summary
    print()
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)

    if migrated:
        print(f"\n  Stored in keychain ({len(migrated)}):")
        for key in migrated:
            print(f"    + {key}")

    if skipped_exists:
        print(f"\n  Already in keychain ({len(skipped_exists)}):")
        for key in skipped_exists:
            print(f"    = {key}")

    if skipped_empty:
        print(f"\n  Skipped (empty/missing in .env) ({len(skipped_empty)}):")
        for key in skipped_empty:
            print(f"    - {key}")

    if failed:
        print(f"\n  Failed ({len(failed)}):")
        for key in failed:
            print(f"    ! {key}")

    print()

    if clean and (migrated or skipped_exists):
        _clean_env_file(env_path, migrated + skipped_exists)
    elif clean:
        print("Nothing to clean from .env.")


def _clean_env_file(env_path: Path, keys_to_remove: list[str]) -> None:
    """Remove credential lines from .env, preserving everything else."""
    lines = env_path.read_text().splitlines(keepends=True)
    pattern = re.compile(
        r"^(" + "|".join(re.escape(k) for k in keys_to_remove) + r")\s*="
    )

    cleaned = [line for line in lines if not pattern.match(line)]

    env_path.write_text("".join(cleaned))
    print(f"Removed {len(keys_to_remove)} credential(s) from {env_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate provider credentials from .env to macOS Keychain"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove migrated credentials from .env after storing in keychain",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(__file__).parent.parent / ".env",
        help="Path to .env file (default: backend/.env)",
    )

    args = parser.parse_args()
    migrate(args.env_file, clean=args.clean)


if __name__ == "__main__":
    main()
