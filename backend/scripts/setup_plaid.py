#!/usr/bin/env python3
"""Plaid API setup script.

This script validates Plaid API credentials by attempting to create a sandbox
link token. Institution linking happens via the browser (Plaid Link UI), not
through this CLI script.

Usage:
    1. Sign up at https://dashboard.plaid.com/
    2. Get your client_id and secret from the Keys page
    3. Run this script and follow the prompts
    4. Add the resulting env vars to your .env file
    5. Link institutions via the Settings > Providers page in the browser
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from plaid import Environment
from plaid.api.plaid_api import PlaidApi
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products


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


def validate_credentials(client_id: str, secret: str, env: str) -> None:
    """Validate Plaid credentials by creating a test link token.

    Args:
        client_id: Plaid client_id.
        secret: Plaid secret.
        env: Environment name (sandbox or production).

    Raises:
        Exception: If the API call fails.
    """
    env_map = {
        "sandbox": Environment.Sandbox,
        "production": Environment.Production,
    }
    host = env_map.get(env.lower(), Environment.Sandbox)

    configuration = Configuration(
        host=host,
        api_key={"clientId": client_id, "secret": secret},
    )
    api_client = ApiClient(configuration)
    api = PlaidApi(api_client)

    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id="setup-test"),
        client_name="TenetFolio",
        products=[Products("investments")],
        country_codes=[CountryCode("US")],
        language="en",
    )
    response = api.link_token_create(request)
    assert response["link_token"], "No link_token in response"


def main():
    """Prompt for credentials and validate them."""
    print("Plaid API Setup")
    print("=" * 50)
    print()
    print("This script will validate your Plaid API credentials.")
    print()
    print("To get Plaid API credentials:")
    print("  1. Sign up at https://dashboard.plaid.com/")
    print("  2. Go to Developers > Keys")
    print("  3. Copy your client_id and secret")
    print()

    client_id = input("Enter your Plaid client_id: ").strip()
    if not client_id:
        print("Error: No client_id provided")
        sys.exit(1)

    secret = input("Enter your Plaid secret: ").strip()
    if not secret:
        print("Error: No secret provided")
        sys.exit(1)

    print()
    print("Choose environment:")
    print("  1. sandbox (for testing with fake data)")
    print("  2. production (for live use)")
    env_choice = input("Enter choice (1 or 2) [1]: ").strip() or "1"
    env_map_choice = {"1": "sandbox", "2": "production"}
    env = env_map_choice.get(env_choice, "sandbox")

    print()
    print(f"Validating credentials against {env} environment...")

    try:
        validate_credentials(client_id, secret, env)
    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print("  - Incorrect client_id or secret")
        print("  - Wrong environment selected")
        print("  - Network connectivity issue")
        sys.exit(1)

    print()
    print("Success! Add the following to your .env file:")
    print()
    print(f"PLAID_CLIENT_ID={client_id}")
    print(f"PLAID_SECRET={secret}")
    print(f"PLAID_ENVIRONMENT={env}")
    print()
    print("Note: Institution linking happens via the browser. Go to")
    print("Settings > Providers in the web UI to link institutions.")

    _offer_keychain_store({
        "PLAID_CLIENT_ID": client_id,
        "PLAID_SECRET": secret,
    })

    print()
    print("Keep these credentials secure - they provide access to")
    print("financial data via the Plaid API.")


if __name__ == "__main__":
    main()
