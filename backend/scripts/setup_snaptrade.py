#!/usr/bin/env python3
"""
Setup script to register a SnapTrade user and manage brokerage connections.

Usage:
    1. Get API credentials from https://snaptrade.com
    2. Set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY in .env
    3. Run: python -m scripts.setup_snaptrade register
    4. Add the generated SNAPTRADE_USER_SECRET to .env
    5. Run: python -m scripts.setup_snaptrade connect
    6. Open the URL in browser to connect your brokerage(s)
    7. Run: python -m scripts.setup_snaptrade list  (to see connections)
    8. Run: python -m scripts.setup_snaptrade disconnect --authorization-id <id>
"""

import argparse
import os
import sys

# Add backend to path so we can import from there
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from snaptrade_client import SnapTrade


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


def get_client() -> SnapTrade:
    """Create SnapTrade client from environment variables or keychain."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    client_id = _get_setting("SNAPTRADE_CLIENT_ID")
    consumer_key = _get_setting("SNAPTRADE_CONSUMER_KEY")

    if not client_id or not consumer_key:
        print("Error: SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY must be set in backend/.env or keychain")
        sys.exit(1)

    return SnapTrade(consumer_key=consumer_key, client_id=client_id)


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


def register_user(user_id: str = "portfolio-user"):
    """Register a new SnapTrade user and print the user secret."""
    client = get_client()

    print(f"Registering user: {user_id}")
    try:
        response = client.authentication.register_snap_trade_user(
            user_id=user_id,
        )
        # Response body is a dict-like object with userId and userSecret
        user_secret = response.body.get("userSecret") or response.body.get("user_secret")
        if not user_secret:
            print(f"Unexpected response format: {response.body}")
            sys.exit(1)
        print("\n" + "=" * 60)
        print("SUCCESS! Add this to your backend/.env file:")
        print("=" * 60)
        print(f"SNAPTRADE_USER_ID={user_id}")
        print(f"SNAPTRADE_USER_SECRET={user_secret}")
        print("=" * 60 + "\n")
        _offer_keychain_store(
            {"SNAPTRADE_USER_ID": user_id, "SNAPTRADE_USER_SECRET": user_secret}
        )
    except Exception as e:
        print(f"Error registering user: {e}")
        sys.exit(1)


def delete_user(user_id: str = "portfolio-user"):
    """Delete an existing SnapTrade user."""
    client = get_client()

    print(f"Deleting user: {user_id}")
    try:
        client.authentication.delete_snap_trade_user(
            user_id=user_id,
        )
        print("\n" + "=" * 60)
        print(f"SUCCESS! User '{user_id}' has been deleted.")
        print("You can now run 'register' to create a new user.")
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"Error deleting user: {e}")
        sys.exit(1)


def reset_user_secret(user_id: str = "portfolio-user"):
    """Rotate the user secret without deleting the user or connections."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    user_secret = _get_setting("SNAPTRADE_USER_SECRET")
    if not user_secret:
        print("Error: SNAPTRADE_USER_SECRET must be set to rotate it.")
        print("Run 'python -m scripts.setup_snaptrade register' first.")
        sys.exit(1)

    client = get_client()

    print(f"Rotating secret for user: {user_id}")
    print("This preserves all existing brokerage connections.")
    print()

    try:
        response = client.authentication.reset_snap_trade_user_secret(
            user_id=user_id,
            user_secret=user_secret,
        )
        new_secret = response.body.get("userSecret") or response.body.get("user_secret")
        if not new_secret:
            print(f"Unexpected response format: {response.body}")
            sys.exit(1)
        print("=" * 60)
        print("SUCCESS! Update your backend/.env file with:")
        print("=" * 60)
        print(f"SNAPTRADE_USER_SECRET={new_secret}")
        print("=" * 60)
        print()
        print("IMPORTANT: Save this secret immediately. If lost, you will")
        print("need to delete and re-register the user (losing connections).")
        _offer_keychain_store(
            {"SNAPTRADE_USER_ID": user_id, "SNAPTRADE_USER_SECRET": new_secret}
        )
    except Exception as e:
        print(f"Error rotating secret: {e}")
        sys.exit(1)


def generate_connect_url():
    """Generate a URL to connect a brokerage account."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    user_id = _get_setting("SNAPTRADE_USER_ID")
    user_secret = _get_setting("SNAPTRADE_USER_SECRET")

    if not user_id or not user_secret:
        print("Error: SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET must be set.")
        print("Run 'python scripts/setup_snaptrade.py register' first.")
        sys.exit(1)

    client = get_client()

    print(f"Generating connection URL for user: {user_id}")
    try:
        response = client.authentication.login_snap_trade_user(
            user_id=user_id,
            user_secret=user_secret,
        )
        # Response body contains redirectURI or redirect_uri
        redirect_uri = (
            response.body.get("redirectURI")
            or response.body.get("redirect_uri")
            or response.body.get("loginRedirectURI")
        )
        if not redirect_uri:
            print(f"Unexpected response format: {response.body}")
            sys.exit(1)
        print("\n" + "=" * 60)
        print("Open this URL in your browser to connect a brokerage:")
        print("=" * 60)
        print(redirect_uri)
        print("=" * 60 + "\n")
    except Exception as e:
        print(f"Error generating connect URL: {e}")
        sys.exit(1)


def _get_attr(obj, key, default="Unknown"):
    """Get attribute from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def list_connections():
    """List all brokerage connections with their accounts."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    user_id = _get_setting("SNAPTRADE_USER_ID")
    user_secret = _get_setting("SNAPTRADE_USER_SECRET")

    if not user_id or not user_secret:
        print("Error: SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET must be set.")
        sys.exit(1)

    client = get_client()

    print(f"Fetching connections for user: {user_id}")
    try:
        # Fetch connections (brokerage authorizations)
        auth_response = client.connections.list_brokerage_authorizations(
            user_id=user_id,
            user_secret=user_secret,
        )
        authorizations = auth_response if isinstance(auth_response, list) else auth_response.body

        # Fetch accounts to group under connections
        acct_response = client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret,
        )
        accounts = acct_response if isinstance(acct_response, list) else acct_response.body

        # Build mapping: authorization ID -> list of accounts
        # Note: account.brokerage_authorization is a UUID string, not a nested object
        accounts_by_auth = {}
        for account in accounts:
            auth_id = str(_get_attr(account, "brokerage_authorization", None) or "")
            accounts_by_auth.setdefault(auth_id or None, []).append(account)

        print("\n" + "=" * 60)
        print(f"Found {len(authorizations)} connection(s):")
        print("=" * 60)

        for auth in authorizations:
            auth_id = str(_get_attr(auth, "id"))
            auth_type = _get_attr(auth, "type", "Unknown")

            # Brokerage name may be nested under a brokerage object
            brokerage_obj = _get_attr(auth, "brokerage", None)
            if brokerage_obj:
                brokerage_name = _get_attr(brokerage_obj, "name", "Unknown")
            else:
                brokerage_name = "Unknown"

            # Connection name (SnapTrade calls this "name" on the authorization)
            conn_name = _get_attr(auth, "name", brokerage_name)

            print(f"\n  Connection: {conn_name} ({brokerage_name})")
            print(f"  Auth ID:    {auth_id}")
            print(f"  Status:     {auth_type}")

            # Show accounts under this connection
            conn_accounts = accounts_by_auth.get(auth_id, [])
            if conn_accounts:
                print("  Accounts:")
                for account in conn_accounts:
                    acc_name = _get_attr(account, "name", "Unknown")
                    acc_id = _get_attr(account, "id", "Unknown")
                    print(f"    - {acc_name} (ID: {acc_id})")
            else:
                print("  Accounts:   (none)")

        # Show any orphaned accounts (no matching authorization)
        orphaned = accounts_by_auth.get(None, [])
        if orphaned:
            print("\n  Accounts with no connection:")
            for account in orphaned:
                acc_name = _get_attr(account, "name", "Unknown")
                acc_id = _get_attr(account, "id", "Unknown")
                print(f"    - {acc_name} (ID: {acc_id})")

        print("\n" + "=" * 60 + "\n")
    except Exception as e:
        import traceback
        print(f"Error listing connections: {e}")
        traceback.print_exc()
        sys.exit(1)


def disconnect_authorization(authorization_id: str):
    """Disconnect a specific brokerage connection by authorization ID."""
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    user_id = _get_setting("SNAPTRADE_USER_ID")
    user_secret = _get_setting("SNAPTRADE_USER_SECRET")

    if not user_id or not user_secret:
        print("Error: SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET must be set.")
        sys.exit(1)

    client = get_client()

    # Look up the connection details for confirmation
    try:
        auth_response = client.connections.list_brokerage_authorizations(
            user_id=user_id,
            user_secret=user_secret,
        )
        authorizations = auth_response if isinstance(auth_response, list) else auth_response.body

        target = None
        for auth in authorizations:
            if _get_attr(auth, "id") == authorization_id:
                target = auth
                break

        if target is None:
            print(f"Error: No connection found with authorization ID: {authorization_id}")
            print("Run 'python -m scripts.setup_snaptrade list' to see available connections.")
            sys.exit(1)

        # Get brokerage name
        brokerage_obj = _get_attr(target, "brokerage", None)
        brokerage_name = _get_attr(brokerage_obj, "name", "Unknown") if brokerage_obj else "Unknown"
        conn_name = _get_attr(target, "name", brokerage_name)

        # Fetch accounts to show what will be removed
        acct_response = client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret,
        )
        accounts = acct_response if isinstance(acct_response, list) else acct_response.body
        affected_accounts = []
        for account in accounts:
            acct_auth_id = str(_get_attr(account, "brokerage_authorization", "") or "")
            if acct_auth_id == authorization_id:
                affected_accounts.append(account)

        # Show what will be disconnected and prompt for confirmation
        print("\n" + "=" * 60)
        print("The following connection will be removed:")
        print("=" * 60)
        print(f"  Connection: {conn_name} ({brokerage_name})")
        print(f"  Auth ID:    {authorization_id}")
        if affected_accounts:
            print("  Accounts that will be removed:")
            for account in affected_accounts:
                acc_name = _get_attr(account, "name", "Unknown")
                acc_id = _get_attr(account, "id", "Unknown")
                print(f"    - {acc_name} (ID: {acc_id})")
        else:
            print("  Accounts:   (none)")
        print("=" * 60)

        confirm = input("\nContinue? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    except Exception as e:
        import traceback
        print(f"Error looking up connection: {e}")
        traceback.print_exc()
        sys.exit(1)

    # Perform the disconnection
    try:
        client.connections.remove_brokerage_authorization(
            authorization_id=authorization_id,
            user_id=user_id,
            user_secret=user_secret,
        )
        print(f"\nSUCCESS! Disconnected '{conn_name}' ({brokerage_name}).")
    except Exception as e:
        print(f"Error disconnecting: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="SnapTrade setup utility")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Register command
    register_parser = subparsers.add_parser("register", help="Register a new SnapTrade user")
    register_parser.add_argument(
        "--user-id",
        default="portfolio-user",
        help="User ID for the SnapTrade user (default: portfolio-user)",
    )

    # Reset secret command (rotates secret, preserves connections)
    reset_parser = subparsers.add_parser("reset-secret", help="Rotate user secret (preserves connections)")
    reset_parser.add_argument(
        "--user-id",
        default="portfolio-user",
        help="User ID for the SnapTrade user (default: portfolio-user)",
    )

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an existing SnapTrade user")
    delete_parser.add_argument(
        "--user-id",
        default="portfolio-user",
        help="User ID for the SnapTrade user (default: portfolio-user)",
    )

    # Connect command
    subparsers.add_parser("connect", help="Generate URL to connect a brokerage")

    # List command
    subparsers.add_parser("list", help="List connections and accounts")

    # Disconnect command
    disconnect_parser = subparsers.add_parser(
        "disconnect", help="Disconnect a brokerage connection"
    )
    disconnect_parser.add_argument(
        "--authorization-id",
        required=True,
        help="Authorization ID of the connection to remove (from 'list' output)",
    )

    args = parser.parse_args()

    if args.command == "register":
        register_user(args.user_id)
    elif args.command == "reset-secret":
        reset_user_secret(args.user_id)
    elif args.command == "delete":
        delete_user(args.user_id)
    elif args.command == "connect":
        generate_connect_url()
    elif args.command == "list":
        list_connections()
    elif args.command == "disconnect":
        disconnect_authorization(args.authorization_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
