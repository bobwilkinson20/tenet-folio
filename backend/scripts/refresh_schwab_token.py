#!/usr/bin/env python3
"""Refresh Charles Schwab OAuth token.

Schwab refresh tokens expire after ~7 days.  Run this script to
re-authenticate without re-entering your App Key and App Secret
(they are read from your .env / environment).

Usage:
    python scripts/refresh_schwab_token.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from scripts.setup_schwab import (
    get_default_token_path,
    run_oauth_flow,
    validate_client,
)


def _secure_token_file(token_path: str) -> None:
    """Set restrictive permissions on the token file."""
    p = Path(token_path)
    if p.exists():
        p.chmod(0o600)


def main():
    """Re-run the OAuth flow using credentials from settings."""
    print("Charles Schwab Token Refresh")
    print("=" * 50)
    print()

    app_key = settings.SCHWAB_APP_KEY
    app_secret = settings.SCHWAB_APP_SECRET
    callback_url = settings.SCHWAB_CALLBACK_URL
    token_path = settings.SCHWAB_TOKEN_PATH or get_default_token_path()

    if not app_key or not app_secret:
        print("Error: SCHWAB_APP_KEY and SCHWAB_APP_SECRET must be set in")
        print("your .env file. Run setup_schwab.py first to configure them.")
        sys.exit(1)

    print(f"Using App Key: {app_key[:8]}...")
    print(f"Using Callback URL: {callback_url}")
    print(f"Token path: {token_path}")
    print()
    print("Starting OAuth flow...")
    print("Follow the instructions below to re-authorize your app.")
    print()

    try:
        client = run_oauth_flow(app_key, app_secret, callback_url, token_path)
    except Exception as e:
        print(f"Error during OAuth flow: {e}")
        print()
        print("Common issues:")
        print("  - App status is no longer 'Ready for Use'")
        print("  - Callback URL doesn't match your app configuration exactly")
        print("  - Redirect URL was pasted incorrectly")
        print("  - Network connectivity issue")
        sys.exit(1)

    print()
    print("Validating refreshed token...")

    try:
        accounts = validate_client(client)
    except Exception as e:
        print(f"Error validating token: {e}")
        sys.exit(1)

    _secure_token_file(token_path)

    print()
    print(
        f"Success! Token refreshed. Found {len(accounts)} account(s)."
    )
    print(f"Token saved to: {token_path}")


if __name__ == "__main__":
    main()
