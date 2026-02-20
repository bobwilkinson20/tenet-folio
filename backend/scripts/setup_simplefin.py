#!/usr/bin/env python3
"""SimpleFIN setup script.

This script exchanges a SimpleFIN setup token for an access URL.

Usage:
    1. Go to https://beta-bridge.simplefin.org/ and create an account
    2. Create an "app connection" to generate a setup token
    3. Run this script and paste the setup token when prompted
    4. Add the resulting SIMPLEFIN_ACCESS_URL to your .env file

The setup token can only be used once - it's exchanged for a permanent
access URL that you'll use for all future API calls.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from simplefin import SimpleFINClient


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


def main():
    """Exchange setup token for access URL."""
    print("SimpleFIN Setup")
    print("=" * 50)
    print()
    print("This script will exchange your SimpleFIN setup token")
    print("for a permanent access URL.")
    print()
    print("To get a setup token:")
    print("  1. Go to https://beta-bridge.simplefin.org/")
    print("  2. Create an account or log in")
    print("  3. Click 'New Connection' to create an app connection")
    print("  4. Connect your financial institutions")
    print("  5. Copy the setup token (base64-encoded string)")
    print()

    setup_token = input("Paste your setup token: ").strip()

    if not setup_token:
        print("Error: No setup token provided")
        sys.exit(1)

    print()
    print("Exchanging setup token for access URL...")

    try:
        access_url = SimpleFINClient.get_access_url(setup_token)
        print()
        print("Success! Add the following to your .env file:")
        print()
        print(f"SIMPLEFIN_ACCESS_URL={access_url}")
        print()
        print("Note: The setup token has now been consumed and cannot be reused.")
        print("Keep your access URL secure - it provides read-only access to your accounts.")
        _offer_keychain_store({"SIMPLEFIN_ACCESS_URL": access_url})

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  - Setup token was already used (tokens are single-use)")
        print("  - Setup token is invalid or expired")
        print("  - Network connectivity issues")
        sys.exit(1)


if __name__ == "__main__":
    main()
