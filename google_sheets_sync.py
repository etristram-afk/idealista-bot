"""
Google Sheets Integration
Saves listing data to Google Sheets instead of local CSV
"""

import json
import logging
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False

BASE_DIR = Path(__file__).parent
CREDENTIALS_FILE = BASE_DIR / "google_credentials.json"
SHEET_ID_FILE = BASE_DIR / ".google_sheet_id"

def is_configured():
    """Check if Google Sheets is configured"""
    return SHEETS_AVAILABLE and CREDENTIALS_FILE.exists() and SHEET_ID_FILE.exists()

def get_sheet():
    """Get or create Google Sheet connection"""
    if not is_configured():
        return None

    try:
        # Read sheet ID
        with open(SHEET_ID_FILE, 'r') as f:
            sheet_id = f.read().strip()

        # Authenticate
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_file(str(CREDENTIALS_FILE), scopes=scopes)
        client = gspread.authorize(creds)

        # Open sheet
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.sheet1

        return worksheet
    except Exception as e:
        logging.error(f"Error connecting to Google Sheets: {e}")
        return None

def save_to_sheets(listing_data):
    """Save listing data to Google Sheets"""
    if not is_configured():
        logging.debug("Google Sheets not configured, skipping")
        return False

    try:
        worksheet = get_sheet()
        if not worksheet:
            return False

        # Check if headers exist
        try:
            headers = worksheet.row_values(1)
            if not headers:
                # Add headers
                worksheet.append_row([
                    'Date Found',
                    'Listing ID',
                    'Title',
                    'Price',
                    'Location',
                    'Phone',
                    'URL',
                    'Snapshot Folder',
                    'Description'
                ])
        except:
            # Add headers
            worksheet.append_row([
                'Date Found',
                'Listing ID',
                'Title',
                'Price',
                'Location',
                'Phone',
                'URL',
                'Snapshot Folder',
                'Description'
            ])

        # Add listing data
        row = [
            listing_data.get('date_found', ''),
            listing_data.get('listing_id', ''),
            listing_data.get('title', ''),
            listing_data.get('price', ''),
            listing_data.get('location', ''),
            listing_data.get('phone', ''),
            listing_data.get('url', ''),
            listing_data.get('snapshot_folder', ''),
            listing_data.get('description', '')
        ]

        worksheet.append_row(row)
        logging.info("Saved to Google Sheets successfully")
        return True

    except Exception as e:
        logging.error(f"Error saving to Google Sheets: {e}")
        return False
