#!/usr/bin/env python3
"""Charles Schwab API setup script.

This script walks you through the OAuth flow to create a token file
for the Charles Schwab API using schwab-py.

Usage:
    1. Register at https://developer.schwab.com/ and create an app
    2. Wait for the app status to change from "Approved - Pending" to
       "Ready for Use" (this requires manual approval by Schwab)
    3. Run this script and follow the prompts
    4. Add the resulting env vars to your .env file
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from schwab.auth import client_from_manual_flow


def _get_setting(key: str) -> str:
    """Look up a setting from env vars, .env file, or keychain."""
    value = os.environ.get(key)
    if value:
        return value
    try:
        from services.credential_manager import get_credential

        return get_credential(key) or ""
    except ImportError:
        return ""


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


def get_default_token_path() -> str:
    """Return the default token file path.

    Returns:
        Absolute path to ``backend/.schwab_token.json``.
    """
    return str(Path(__file__).parent.parent / ".schwab_token.json")


def run_oauth_flow(
    app_key: str,
    app_secret: str,
    callback_url: str,
    token_path: str,
):
    """Run the schwab-py manual OAuth flow.

    Prints a URL for the user to open in a browser.  After authorizing,
    the user pastes the redirect URL back into the terminal.  The token
    is saved to *token_path*.

    Args:
        app_key: Schwab application key.
        app_secret: Schwab application secret.
        callback_url: OAuth callback URL (must match app config exactly).
        token_path: Where to write the token JSON file.

    Returns:
        An authenticated schwab-py client.
    """
    return client_from_manual_flow(
        api_key=app_key,
        app_secret=app_secret,
        callback_url=callback_url,
        token_path=token_path,
    )


def validate_client(client) -> list[dict]:
    """Validate the client by fetching account numbers.

    Args:
        client: An authenticated schwab-py client.

    Returns:
        List of account-number dicts from the API.

    Raises:
        Exception: If the API call fails or returns a non-200 status.
    """
    resp = client.get_account_numbers()
    if resp.status_code != 200:
        raise Exception(
            f"Account numbers request failed with status {resp.status_code}: "
            f"{resp.text}"
        )
    return resp.json()


def main():
    """Prompt for credentials and run the OAuth setup flow."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    print("Charles Schwab API Setup")
    print("=" * 50)
    print()
    print("This script will walk you through the OAuth flow to create a")
    print("token file for the Charles Schwab API.")
    print()

    # Check for stored credentials
    stored_key = _get_setting("SCHWAB_APP_KEY")
    stored_secret = _get_setting("SCHWAB_APP_SECRET")
    stored_callback = _get_setting("SCHWAB_CALLBACK_URL")
    stored_token_path = _get_setting("SCHWAB_TOKEN_PATH")

    if stored_key and stored_secret:
        print(f"Found stored credentials (App Key: {stored_key[:8]}...)")
        use_stored = input("Use stored App Key and App Secret? [Y/n] ").strip().lower()
        if use_stored in ("", "y", "yes"):
            app_key = stored_key
            app_secret = stored_secret
        else:
            app_key = input("Enter your App Key: ").strip()
            if not app_key:
                print("Error: No App Key provided")
                sys.exit(1)
            app_secret = input("Enter your App Secret: ").strip()
            if not app_secret:
                print("Error: No App Secret provided")
                sys.exit(1)
    else:
        print("Prerequisites:")
        print("  1. Register at https://developer.schwab.com/")
        print("  2. Create an app with an OAuth callback URL")
        print("  3. Wait for the app status to change to 'Ready for Use'")
        print("     (Schwab manually reviews new apps — this can take a few days)")
        print("  4. Note your App Key and App Secret from the app dashboard")
        print()

        app_key = input("Enter your App Key: ").strip()
        if not app_key:
            print("Error: No App Key provided")
            sys.exit(1)

        app_secret = input("Enter your App Secret: ").strip()
        if not app_secret:
            print("Error: No App Secret provided")
            sys.exit(1)

    default_callback = stored_callback or "https://127.0.0.1"
    callback_url = input(
        f"Enter Callback URL (default: {default_callback}): "
    ).strip()
    if not callback_url:
        callback_url = default_callback

    default_token_path = stored_token_path or get_default_token_path()
    token_path = input(
        f"Enter token file path (default: {default_token_path}): "
    ).strip()
    if not token_path:
        token_path = default_token_path

    print()
    print("Starting OAuth flow...")
    print("Follow the instructions below to authorize your app.")
    print()

    try:
        client = run_oauth_flow(app_key, app_secret, callback_url, token_path)
    except Exception as e:
        print(f"Error during OAuth flow: {e}")
        print()
        print("Common issues:")
        print("  - App status is still 'Approved - Pending' (not yet ready)")
        print("  - Callback URL doesn't match your app configuration exactly")
        print("  - Redirect URL was pasted incorrectly")
        print("  - App Key or App Secret is wrong")
        print("  - Network connectivity issue")
        sys.exit(1)

    print()
    print("Validating token by fetching account numbers...")

    try:
        accounts = validate_client(client)
    except Exception as e:
        print(f"Error validating token: {e}")
        sys.exit(1)

    print()
    print(f"Success! Found {len(accounts)} account(s):")
    for acct in accounts:
        print(f"  - Account {acct.get('accountNumber', 'unknown')}")

    print()
    print("Add the following to your .env file:")
    print()
    print(f"SCHWAB_APP_KEY={app_key}")
    print(f"SCHWAB_APP_SECRET={app_secret}")
    if callback_url != default_callback:
        print(f"SCHWAB_CALLBACK_URL={callback_url}")
    print(f"SCHWAB_TOKEN_PATH={token_path}")

    print()
    print("IMPORTANT: Schwab refresh tokens expire after ~7 days. You will")
    print("need to re-authenticate periodically by running:")
    print("  python scripts/refresh_schwab_token.py")

    # Set restrictive permissions on token file
    token_file = Path(token_path)
    if token_file.exists():
        token_file.chmod(0o600)
        print(f"\n  Set {token_path} permissions to 0600")

    print()
    print("Keep your token file and credentials secure — they provide")
    print("access to your Charles Schwab account data.")

    creds = {
        "SCHWAB_APP_KEY": app_key,
        "SCHWAB_APP_SECRET": app_secret,
        "SCHWAB_CALLBACK_URL": callback_url,
    }
    _offer_keychain_store(creds)


if __name__ == "__main__":
    main()
