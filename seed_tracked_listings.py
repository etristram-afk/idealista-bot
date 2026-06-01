#!/usr/bin/env python3
"""
One-time seed script: marks all currently-visible search results as already
seen so the bot won't message them when auto-contact is first enabled.
Run once, then start the bot normally.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).parent
TRACKING_FILE = BASE_DIR / "tracked_listings.json"
STATE_FILE = BASE_DIR / "browser_state.json"
ENV_FILE = BASE_DIR / ".env"


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    return env


def load_tracked():
    if TRACKING_FILE.exists():
        with open(TRACKING_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_tracked(listings):
    with open(TRACKING_FILE, 'w') as f:
        json.dump(listings, f, indent=2)


def main():
    env = load_env()
    search_url = env.get('SEARCH_URL')
    if not search_url:
        print("ERROR: SEARCH_URL not set in .env")
        return

    if not STATE_FILE.exists():
        print("ERROR: No saved browser session. Run python3 setup_session.py first.")
        return

    tracked = load_tracked()
    print(f"Currently tracked: {len(tracked)} listings")

    with sync_playwright() as p:
        browser = p.webkit.launch(headless=False)
        context = browser.new_context(
            storage_state=str(STATE_FILE),
            viewport={'width': 1920, 'height': 1080},
            locale='es-ES',
            timezone_id='Europe/Madrid',
        )
        page = context.new_page()

        print("Loading search page...")
        page.goto(search_url, wait_until="networkidle")
        time.sleep(3)

        # Collect all listing IDs visible on the page
        elements = page.query_selector_all('a[href*="/inmueble/"]')
        seen_ids = set()
        for elem in elements:
            href = elem.get_attribute('href') or ''
            if '/inmueble/' in href:
                listing_id = href.rstrip('/').split('/')[-1]
                if listing_id.isdigit():
                    seen_ids.add(listing_id)

        print(f"Found {len(seen_ids)} listings on search page")

        new_count = 0
        for listing_id in seen_ids:
            if listing_id not in tracked:
                tracked[listing_id] = {
                    'date': datetime.now().isoformat(),
                    'url': f"https://www.idealista.com/inmueble/{listing_id}/",
                    'contacted': 'skipped_seed',
                }
                new_count += 1
                print(f"  Seeded: {listing_id}")
            else:
                print(f"  Already tracked: {listing_id}")

        save_tracked(tracked)
        context.close()
        browser.close()

    print(f"\nDone. Seeded {new_count} new listing(s). Total tracked: {len(tracked)}")
    print("The bot will now only message listings that appear after this point.")


if __name__ == "__main__":
    main()
