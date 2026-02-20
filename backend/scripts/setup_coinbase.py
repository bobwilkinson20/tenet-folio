#!/usr/bin/env python3
"""Coinbase Advanced Trade API setup script.

This script validates Coinbase CDP API credentials by attempting a test API call.

Usage:
    1. Create a CDP API key at https://portal.cdp.coinbase.com/projects/api-keys
    2. IMPORTANT: Select ECDSA in Advanced Settings (not Ed25519)
    3. Download the JSON key file or copy the key and secret
    4. Run this script and follow the prompts
    5. Add the resulting env vars to your .env file
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from coinbase.rest import RESTClient


def _offer_keychain_store(credentials: dict[str, str]) -> None:
    """Prompt the user to store credentials in macOS Keychain."""
    try:
        from services.credential_manager import set_credential
    except ImportError:
        return

    answer = input("\nStore these credentials in macOS Keychain? [Y/n] ").strip().lower()
    if answer in ("", "y", "yes"):
        for key, value in credentials.items():
            if set_credential(key, value):
                print(f"  Stored {key} in keychain")
            else:
                print(f"  Failed to store {key}")
    else:
        print("  Skipped keychain storage.")


def validate_with_key_file(key_file_path: str) -> dict:
    """Validate credentials using a CDP API key JSON file.

    Reads the JSON file directly (rather than passing key_file to the
    library) so we can accept both ``"name"`` and ``"id"`` as the API
    key field.  Coinbase has shipped key files with both field names.

    Args:
        key_file_path: Path to the CDP API key JSON file.

    Returns:
        Dict with 'api_key' and 'api_secret' extracted from the file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is invalid or missing required fields.
        Exception: If the API call fails.
    """
    path = Path(key_file_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in key file: {e}") from e

    # Accept both "name" (library convention) and "id" (some CDP downloads)
    api_key = data.get("name") or data.get("id")
    if not api_key:
        raise ValueError(
            "Key file missing required field: 'name' (or 'id')"
        )
    if "privateKey" not in data:
        raise ValueError("Key file missing required field: 'privateKey'")

    api_secret = data["privateKey"]

    # Pass credentials directly — avoids the library's assumption that
    # the JSON uses a "name" field.
    client = RESTClient(api_key=api_key, api_secret=api_secret)
    client.get_accounts(limit=1)

    return {"api_key": api_key, "api_secret": api_secret}


def validate_with_api_key(api_key: str, api_secret: str) -> None:
    """Validate credentials using an inline API key and secret.

    Args:
        api_key: CDP API key (organizations/{org_id}/apiKeys/{key_id}).
        api_secret: ECDSA private key in PEM format.

    Raises:
        Exception: If the API call fails.
    """
    client = RESTClient(api_key=api_key, api_secret=api_secret)
    client.get_accounts(limit=1)


def format_secret_for_env(secret: str) -> str:
    """Escape a PEM secret for use in a .env file.

    Replaces real newlines with literal ``\\n`` so the value can be stored
    as a single double-quoted line in a .env file.

    Args:
        secret: PEM private key string (may contain real newlines).

    Returns:
        Escaped string suitable for .env file.
    """
    return secret.replace("\n", "\\n")


def main():
    """Prompt for credentials and validate them."""
    print("Coinbase Advanced Trade API Setup")
    print("=" * 50)
    print()
    print("This script will validate your Coinbase CDP API credentials.")
    print()
    print("To create CDP API credentials:")
    print("  1. Go to https://portal.cdp.coinbase.com/projects/api-keys")
    print("  2. Click 'Create API Key'")
    print("  3. IMPORTANT: Under Advanced Settings, select 'ECDSA' as the")
    print("     key algorithm. The default Ed25519 is NOT compatible with")
    print("     the Advanced Trade API SDK.")
    print("  4. Grant 'View' permission (read-only is sufficient)")
    print("  5. Download the JSON key file or copy the key and secret")
    print()
    print("Choose an authentication method:")
    print("  1. JSON key file (recommended)")
    print("  2. Manual API key and secret entry")
    print()

    method = input("Enter method (1 or 2): ").strip()

    if method == "1":
        key_file_path = input("Enter path to CDP API key JSON file: ").strip()
        if not key_file_path:
            print("Error: No file path provided")
            sys.exit(1)

        print()
        print("Validating credentials...")

        try:
            credentials = validate_with_key_file(key_file_path)
            resolved_path = str(Path(key_file_path).expanduser().resolve())

            print()
            print("Success! Add the following to your .env file:")
            print()
            print(f"COINBASE_KEY_FILE={resolved_path}")
            print()
            print("Alternatively, you can use inline credentials instead:")
            print()
            print(f"COINBASE_API_KEY={credentials['api_key']}")
            escaped = format_secret_for_env(credentials["api_secret"])
            print(f'COINBASE_API_SECRET="{escaped}"')

            # Set restrictive permissions on key file
            key_path = Path(resolved_path)
            if key_path.exists():
                key_path.chmod(0o600)
                print(f"\n  Set {resolved_path} permissions to 0600")

            _offer_keychain_store(
                {
                    "COINBASE_API_KEY": credentials["api_key"],
                    "COINBASE_API_SECRET": credentials["api_secret"],
                }
            )

        except Exception as e:
            print(f"Error: {e}")
            print()
            print("Common issues:")
            print("  - Key uses Ed25519 algorithm instead of ECDSA. Recreate")
            print("    the key and select ECDSA in Advanced Settings.")
            print("  - API key has been revoked or deleted")
            print("  - Key file is corrupted or incomplete")
            print("  - Insufficient permissions (need 'View' for Advanced Trade)")
            print("  - Network connectivity issue")
            sys.exit(1)

    elif method == "2":
        api_key = input("Enter your CDP API key: ").strip()
        if not api_key:
            print("Error: No API key provided")
            sys.exit(1)

        print("Enter your API secret (PEM private key).")
        print("Paste the entire key, then press Enter twice to finish:")
        lines = []
        while True:
            line = input()
            if line == "" and lines and lines[-1] == "":
                lines.pop()  # Remove trailing blank line
                break
            lines.append(line)
        api_secret = "\n".join(lines)

        if not api_secret.strip():
            print("Error: No API secret provided")
            sys.exit(1)

        print()
        print("Validating credentials...")

        try:
            validate_with_api_key(api_key, api_secret)

            print()
            print("Success! Add the following to your .env file:")
            print()
            print(f"COINBASE_API_KEY={api_key}")
            escaped = format_secret_for_env(api_secret)
            print(f'COINBASE_API_SECRET="{escaped}"')

            _offer_keychain_store(
                {"COINBASE_API_KEY": api_key, "COINBASE_API_SECRET": api_secret}
            )

        except Exception as e:
            print(f"Error: {e}")
            print()
            print("Common issues:")
            print("  - Key uses Ed25519 algorithm instead of ECDSA. Recreate")
            print("    the key and select ECDSA in Advanced Settings.")
            print("  - API key has been revoked or deleted")
            print("  - API secret is malformed (must be a valid ECDSA PEM key)")
            print("  - Insufficient permissions (need 'View' for Advanced Trade)")
            print("  - Network connectivity issue")
            sys.exit(1)

    else:
        print("Error: Invalid method. Please enter 1 or 2.")
        sys.exit(1)

    print()
    print("Keep these credentials secure - they provide access to your")
    print("Coinbase account data via the Advanced Trade API.")


if __name__ == "__main__":
    main()
