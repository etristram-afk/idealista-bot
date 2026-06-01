# Google Sheets Setup Guide

This guide will help you sync your listings to Google Sheets so you can view them from anywhere (no Microsoft subscription needed!).

## Quick Setup (5 minutes)

### Step 1: Create Google Cloud Project

1. Go to https://console.cloud.google.com
2. Click "Select a project" → "New Project"
3. Name it "Idealista Bot" (or whatever you want)
4. Click "Create"

### Step 2: Enable APIs

1. In your new project, go to "APIs & Services" → "Library"
2. Search for "Google Sheets API" → Click it → Enable
3. Search for "Google Drive API" → Click it → Enable

### Step 3: Create Service Account

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "Service Account"
3. Name it "idealista-bot" (or anything)
4. Click "Create and Continue"
5. Skip the optional steps, click "Done"

### Step 4: Download Credentials

1. Click on the service account you just created
2. Go to "Keys" tab
3. Click "Add Key" → "Create new key"
4. Choose "JSON"
5. Click "Create" → A JSON file will download
6. **SAVE THIS FILE SOMEWHERE SAFE**

### Step 5: Create Google Sheet

1. Go to https://sheets.google.com
2. Create a new spreadsheet
3. Name it "Idealista Listings"
4. Click "Share" button (top right)
5. **IMPORTANT**: Paste the email from your JSON file (looks like: `idealista-bot@...iam.gserviceaccount.com`)
6. Give it "Editor" access
7. Click "Share" or "Send"
8. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/1Abc123XyZ.../edit
                                          ^^^^^^^^^^^
                                          This is your Sheet ID
   ```

### Step 6: Run Setup Script

Open Terminal and run:

```bash
cd ~/idealista-bot
python3 setup_google_sheets.py
```

Follow the prompts:
1. Enter the path to your downloaded JSON file
2. Enter your Google Sheet ID

That's it! 🎉

## What Happens Next

- The bot will automatically save all new listings to both:
  - Local CSV: `~/idealista-bot/listings_database.csv`
  - Google Sheets: Your online spreadsheet

- You can view your listings from:
  - Your Mac: Open the CSV
  - Any device: Open the Google Sheet URL
  - Your phone: Google Sheets app

## Viewing Your Google Sheet

Your listings are at:
```
https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
```

Bookmark this URL for easy access!

## Troubleshooting

### "Permission denied" error
- Make sure you shared the sheet with the service account email
- The email is in the JSON file: `client_email` field

### "Invalid credentials" error
- Make sure you downloaded the JSON file correctly
- Re-run `python3 setup_google_sheets.py` with the correct file

### Not seeing new listings?
- Check `~/idealista-bot/logs/bot_*.log` for errors
- Make sure the bot is running: `launchctl list | grep idealista`

## Security Note

Your `google_credentials.json` file gives access to write to your Google Sheets. Keep it private! It's already in `.gitignore` so it won't be shared accidentally.
