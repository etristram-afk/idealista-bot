#!/usr/bin/env python3
"""
Google Sheets Setup Helper
Helps configure Google Sheets integration
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "google_credentials.json"
SHEET_ID_FILE = BASE_DIR / ".google_sheet_id"

def main():
    print("=" * 70)
    print("GOOGLE SHEETS SETUP")
    print("=" * 70)
    print()
    print("This will set up automatic syncing to Google Sheets.")
    print("Your listings will appear in a spreadsheet you can access from anywhere!")
    print()

    # Step 1: Get credentials
    print("STEP 1: Get Google Cloud Credentials")
    print("-" * 70)
    print()
    print("1. Go to: https://console.cloud.google.com")
    print("2. Create a new project (or select existing)")
    print("3. Enable 'Google Sheets API' and 'Google Drive API'")
    print("4. Go to 'Credentials' → 'Create Credentials' → 'Service Account'")
    print("5. Create a service account (any name)")
    print("6. Click on the service account → 'Keys' → 'Add Key' → 'JSON'")
    print("7. Download the JSON file")
    print()

    # Ask for credentials file path
    creds_path = input("Enter path to your downloaded credentials JSON file: ").strip()

    if not creds_path:
        print("❌ No path provided")
        return

    creds_path = Path(creds_path.replace('"', '').replace("'", ""))

    if not creds_path.exists():
        print(f"❌ File not found: {creds_path}")
        return

    # Copy credentials
    with open(creds_path, 'r') as f:
        creds_data = json.load(f)

    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(creds_data, f, indent=2)

    print(f"✓ Credentials saved to {CREDENTIALS_FILE}")
    print()

    # Extract service account email
    service_email = creds_data.get('client_email', 'NOT_FOUND')
    print(f"Service account email: {service_email}")
    print()

    # Step 2: Create and share sheet
    print("STEP 2: Create Google Sheet")
    print("-" * 70)
    print()
    print("1. Go to: https://sheets.google.com")
    print("2. Create a new spreadsheet")
    print("3. Name it 'Idealista Listings' (or whatever you want)")
    print(f"4. Click 'Share' and add this email with EDITOR access:")
    print()
    print(f"   {service_email}")
    print()
    print("5. Copy the spreadsheet ID from the URL")
    print("   (It's the long string between /d/ and /edit)")
    print()
    print("   Example URL:")
    print("   https://docs.google.com/spreadsheets/d/1ABC-xyz123.../edit")
    print("                                          ^^^^^^^^^^^^")
    print("                                          This is the ID")
    print()

    sheet_id = input("Enter your Google Sheet ID: ").strip()

    if not sheet_id:
        print("❌ No sheet ID provided")
        return

    # Save sheet ID
    with open(SHEET_ID_FILE, 'w') as f:
        f.write(sheet_id)

    print()
    print("=" * 70)
    print("✓ SETUP COMPLETE!")
    print("=" * 70)
    print()
    print("Your bot will now save listings to Google Sheets automatically!")
    print(f"✓ Credentials: {CREDENTIALS_FILE}")
    print(f"✓ Sheet ID: {SHEET_ID_FILE}")
    print()
    print("Next time the bot runs, listings will appear in your Google Sheet.")
    print()
    print("You can view your sheet at:")
    print(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    print()

if __name__ == "__main__":
    main()
