#!/usr/bin/env python3
"""Google Sheets report export setup script.

This script validates a Google service account credentials file and verifies
access to the target spreadsheet and template tab.

Usage:
    1. Create a service account in Google Cloud Console
    2. Download the JSON key file
    3. Share the target spreadsheet with the service account email
    4. Run this script and follow the prompts
    5. Add the resulting env vars to your .env file
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_credentials_file(path: str) -> dict:
    """Validate service account JSON has required fields.

    Args:
        path: Path to the service account JSON key file.

    Returns:
        Parsed JSON data.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON is invalid or missing required fields.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {resolved}")

    with open(resolved) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in credentials file: {e}") from e

    if "client_email" not in data:
        raise ValueError("Credentials file missing required field: 'client_email'")
    if "private_key" not in data:
        raise ValueError("Credentials file missing required field: 'private_key'")

    return data


def validate_spreadsheet_access(creds_path: str, spreadsheet_id: str):
    """Authenticate with gspread and verify spreadsheet access.

    Args:
        creds_path: Path to the service account JSON key file.
        spreadsheet_id: Google Sheets spreadsheet ID.

    Returns:
        gspread.Spreadsheet instance.

    Raises:
        Exception: If authentication or spreadsheet access fails.
    """
    import gspread

    gc = gspread.service_account(filename=creds_path)
    return gc.open_by_key(spreadsheet_id)


def main():
    """Prompt for configuration and validate access."""
    print("Google Sheets Report Export Setup")
    print("=" * 50)
    print()
    print("This script will validate your Google Sheets configuration.")
    print()
    print("Prerequisites:")
    print("  1. Create a service account in Google Cloud Console")
    print("  2. Enable the Google Sheets API for the project")
    print("  3. Download the service account JSON key file")
    print("  4. Share the target spreadsheet with the service account email")
    print()

    # Step 1: Credentials file
    creds_path = input("Enter path to service account JSON key file: ").strip()
    if not creds_path:
        print("Error: No file path provided")
        sys.exit(1)

    print()
    print("Validating credentials file...")

    try:
        creds_data = validate_credentials_file(creds_path)
        resolved_path = str(Path(creds_path).expanduser().resolve())
        print(f"  Found service account: {creds_data['client_email']}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Step 2: Spreadsheet ID
    print()
    spreadsheet_id = input("Enter spreadsheet ID (from the URL): ").strip()
    if not spreadsheet_id:
        print("Error: No spreadsheet ID provided")
        sys.exit(1)

    print()
    print("Validating spreadsheet access...")

    try:
        spreadsheet = validate_spreadsheet_access(resolved_path, spreadsheet_id)
        print(f"  Successfully opened: {spreadsheet.title}")
    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Common issues:")
        print(f"  - Spreadsheet not shared with {creds_data['client_email']}")
        print("  - Google Sheets API not enabled for the project")
        print("  - Invalid spreadsheet ID")
        sys.exit(1)

    # Step 3: Template tab name
    print()
    template_tab = input("Enter template tab name [Template]: ").strip() or "Template"

    print()
    print("Validating template tab...")

    try:
        spreadsheet.worksheet(template_tab)
        print(f"  Found template tab: {template_tab}")
    except Exception:
        print(f"Error: Tab '{template_tab}' not found in spreadsheet")
        print()
        available = [ws.title for ws in spreadsheet.worksheets()]
        print(f"  Available tabs: {', '.join(available)}")
        sys.exit(1)

    # Set restrictive permissions on key file
    key_path = Path(resolved_path)
    if key_path.exists():
        key_path.chmod(0o600)
        print(f"\n  Set {resolved_path} permissions to 0600")

    # Print results
    print()
    print("Success! Add the following to your .env file:")
    print()
    print(f"GOOGLE_SHEETS_CREDENTIALS_FILE={resolved_path}")
    print(f"GOOGLE_SHEETS_SPREADSHEET_ID={spreadsheet_id}")
    if template_tab != "Template":
        print(f"GOOGLE_SHEETS_TEMPLATE_TAB={template_tab}")
    print()
    print("Keep the service account credentials file secure.")


if __name__ == "__main__":
    main()
