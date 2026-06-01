#!/usr/bin/env python3
"""
Idealista Property Search Bot
Automatically monitors idealista.com for new listings and contacts agents
"""

import argparse
import os
import json
import csv
import time
import random
import logging
import smtplib
import re
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import requests
from patchright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from human_behavior import random_delay, random_mouse_movement, random_scroll, simulate_reading
from google_sheets_sync import save_to_sheets, is_configured as sheets_configured
from captcha_solver import attempt_auto_solve

# Setup paths
BASE_DIR = Path(__file__).parent
LISTINGS_DIR = BASE_DIR / "listings"
LOGS_DIR = BASE_DIR / "logs"
TRACKING_FILE = BASE_DIR / "tracked_listings.json"
CSV_FILE = BASE_DIR / "listings_database.csv"
ENV_FILE = BASE_DIR / ".env"
STATE_FILE = BASE_DIR / "browser_state.json"

# Ensure directories exist
LISTINGS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# Setup logging
log_file = LOGS_DIR / f"bot_{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def load_env():
    """Load environment variables from .env file"""
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

def load_tracked_listings():
    """Load the list of already tracked listings"""
    if TRACKING_FILE.exists():
        with open(TRACKING_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tracked_listings(listings):
    """Save the list of tracked listings"""
    with open(TRACKING_FILE, 'w') as f:
        json.dump(listings, f, indent=2)

CAPTCHA_ALERT_FILE = LOGS_DIR / "last_captcha_alert.txt"
CAPTCHA_ALERT_COOLDOWN_HOURS = 1


def send_telegram(token, chat_id, text, reply_markup=None):
    """Send a Telegram message. Returns True on success."""
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10
        )
        return resp.ok
    except Exception as e:
        logging.error(f"Telegram send failed: {e}")
        return False


def send_telegram_photo(token, chat_id, photo_path, caption=""):
    """Send a photo via Telegram. Returns True on success."""
    try:
        with open(photo_path, 'rb') as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": ("screenshot.png", f, "image/png")},
                timeout=30
            )
        return resp.ok
    except Exception as e:
        logging.error(f"Telegram photo send failed: {e}")
        return False


def send_macos_notification(title, message):
    """Send a macOS notification via osascript."""
    try:
        subprocess.run([
            'osascript', '-e',
            f'display notification "{message}" with title "{title}" sound name "Sosumi"'
        ], timeout=5)
    except Exception as e:
        logging.debug(f"macOS notification failed: {e}")


def send_captcha_alert(reason, page_url, screenshot_path, env):
    """Send captcha/block alert via Telegram (or email fallback), rate-limited to once per cooldown period."""
    try:
        now = datetime.now()
        send_macos_notification(
            "Idealista Bot — CAPTCHA",
            "Bot is blocked. Run setup_session.py to fix."
        )
        if CAPTCHA_ALERT_FILE.exists():
            last_sent = datetime.fromisoformat(CAPTCHA_ALERT_FILE.read_text().strip())
            hours_since = (now - last_sent).total_seconds() / 3600
            if hours_since < CAPTCHA_ALERT_COOLDOWN_HOURS:
                logging.info(f"Captcha alert suppressed (sent {hours_since:.1f}h ago, cooldown {CAPTCHA_ALERT_COOLDOWN_HOURS}h)")
                return False

        is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == '1'
        if is_docker:
            fix_instructions = "VNC to 192.168.1.152:5900 → open terminal → cd /app && python3 setup_session.py"
        else:
            fix_instructions = "cd /Users/edward/dev/idealista-bot && .venv/bin/python setup_session.py"

        telegram_token = env.get('TELEGRAM_BOT_TOKEN', '')
        telegram_chat_id = env.get('TELEGRAM_CHAT_ID', '')

        if telegram_token and telegram_chat_id:
            text = (
                f"🚨 Idealista bot blocked — captcha detected\n\n"
                f"Reason: {reason}\n"
                f"Time: {now.strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Tap a button below or type /help for commands."
            )
            inline_keyboard = {
                "inline_keyboard": [[
                    {"text": "🔄 Retry now", "callback_data": "retry"},
                    {"text": "🖥️ Solve CAPTCHA", "callback_data": "solve"}
                ]]
            }
            success = send_telegram(telegram_token, telegram_chat_id, text,
                                    reply_markup=inline_keyboard)
            if screenshot_path and Path(screenshot_path).exists():
                send_telegram_photo(telegram_token, telegram_chat_id,
                                    screenshot_path, caption="Screenshot at time of block")
            if success:
                CAPTCHA_ALERT_FILE.write_text(now.isoformat())
                logging.info("Captcha alert sent via Telegram")
                return True
            logging.warning("Telegram alert failed, falling back to email")

        # Email fallback
        gmail_user = env.get('IDEALISTA_EMAIL', '')
        gmail_password = env.get('GMAIL_APP_PASSWORD', '')
        notify_email = env.get('NOTIFY_EMAIL', gmail_user)
        if not (gmail_user and gmail_password):
            logging.warning("No Telegram or email credentials configured — captcha alert not sent")
            return False

        body = (
            f"IDEALISTA BOT BLOCKED — ACTION REQUIRED\n"
            f"{'=' * 50}\n"
            f"Reason:     {reason}\n"
            f"URL:        {page_url}\n"
            f"Time:       {now.isoformat()}\n"
            f"Screenshot: {screenshot_path}\n\n"
            f"Fix: {fix_instructions}\n\n"
            f"Bot resumes automatically after session refresh."
        )
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = notify_email
        msg['Subject'] = "[Idealista Bot] CAPTCHA detected — session refresh needed"
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        CAPTCHA_ALERT_FILE.write_text(now.isoformat())
        logging.info("Captcha alert sent via email")
        return True

    except Exception as e:
        logging.error(f"Failed to send captcha alert: {e}")
        return False


def send_email_notification(listing_data, contact_message, gmail_user, gmail_password, notify_email):
    """Send email summary of a new listing"""
    try:
        garage = listing_data.get('garage', 'Unknown')
        bedrooms = listing_data.get('bedrooms', 'Unknown')
        contacted = listing_data.get('contacted', 'no')

        subject = f"New Idealista listing: {listing_data.get('title', 'Unknown')} — {listing_data.get('price', '?')}"

        snapshot_folder = listing_data.get('snapshot_folder', '')
        photos_url = f"file://{snapshot_folder}/photos" if snapshot_folder else 'N/A'

        contact_section_header = "MESSAGE SENT TO AGENT" if contacted == 'yes' else "CONTACT MESSAGE (NOT SENT)"

        body = f"""NEW LISTING FOUND
{'=' * 50}
Title:     {listing_data.get('title', 'N/A')}
Price:     {listing_data.get('price', 'N/A')}
Location:  {listing_data.get('location', 'N/A')}
Bedrooms:  {bedrooms}
Garage:    {garage}
URL:       {listing_data.get('url', 'N/A')}
Photos:    {photos_url}
Found at:  {listing_data.get('date_found', 'N/A')}

{contact_section_header}
{'=' * 50}
{contact_message}

Agent contacted: {contacted}
"""

        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = notify_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)

        logging.info(f"Email notification sent for listing {listing_data.get('listing_id')}")
        return True

    except Exception as e:
        logging.error(f"Failed to send email notification: {e}")
        return False


def save_to_csv(listing_data):
    """Append listing data to CSV file and Google Sheets if configured"""
    # Save to local CSV (always)
    file_exists = CSV_FILE.exists()
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'date_found', 'listing_id', 'title', 'price', 'location',
            'phone', 'url', 'snapshot_folder', 'description', 'contacted',
            'bedrooms', 'garage'
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow(listing_data)

    # Also save to Google Sheets if configured
    if sheets_configured():
        save_to_sheets(listing_data)

class IdealistaBot:
    def __init__(self, email, password, search_url, message, env=None):
        self.email = email
        self.password = password
        self.search_url = search_url
        self.message = message
        self.env = env or {}
        self.tracked = load_tracked_listings()
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        except Exception:
            pass

    def start_browser(self, playwright):
        """Start browser and create context"""
        logging.info("Starting browser...")

        # Check if we have a saved session
        if not STATE_FILE.exists():
            logging.error(f"No saved session found at {STATE_FILE}")
            logging.error("Please run: python3 setup_session.py")
            raise Exception("No saved session - run setup_session.py first")

        # Patchright patches Chromium at the CDP level — headless mode is safe and faster.
        self.browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

        import json as _json
        with open(STATE_FILE) as _f:
            _state = _json.load(_f)

        self.context = self.browser.new_context(
            storage_state=_state,
            viewport={'width': 1280, 'height': 900},
            locale='es-ES',
            timezone_id='Europe/Madrid',
            permissions=['geolocation'],
        )
        self.page = self.context.new_page()

        logging.info("Loaded saved session with stealth mode")

    def login(self):
        """Login to idealista.com"""
        try:
            logging.info("Navigating to idealista.com...")
            self.page.goto("https://www.idealista.com", wait_until="networkidle")
            time.sleep(2)

            # Look for login button
            logging.info("Looking for login button...")
            login_selectors = [
                'a[href*="login"]',
                'button:has-text("Entrar")',
                'a:has-text("Entrar")',
                '.icon-user'
            ]

            login_clicked = False
            for selector in login_selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    logging.info(f"Clicked login button: {selector}")
                    login_clicked = True
                    break
                except:
                    continue

            if not login_clicked:
                logging.warning("Could not find login button, trying direct navigation")
                self.page.goto("https://www.idealista.com/login", wait_until="networkidle")

            time.sleep(2)

            # Fill in credentials
            logging.info("Filling in credentials...")
            email_selectors = ['input[type="email"]', 'input[name="email"]', '#email']
            for selector in email_selectors:
                try:
                    self.page.fill(selector, self.email, timeout=3000)
                    logging.info(f"Filled email with selector: {selector}")
                    break
                except:
                    continue

            password_selectors = ['input[type="password"]', 'input[name="password"]', '#password']
            for selector in password_selectors:
                try:
                    self.page.fill(selector, self.password, timeout=3000)
                    logging.info(f"Filled password with selector: {selector}")
                    break
                except:
                    continue

            # Submit login form
            logging.info("Submitting login form...")
            submit_selectors = [
                'button[type="submit"]',
                'button:has-text("Entrar")',
                'input[type="submit"]'
            ]
            for selector in submit_selectors:
                try:
                    self.page.click(selector, timeout=3000)
                    logging.info(f"Clicked submit button: {selector}")
                    break
                except:
                    continue

            time.sleep(5)

            # Check if login was successful
            if "login" not in self.page.url.lower():
                logging.info("Login successful!")
                return True
            else:
                logging.error("Login may have failed - still on login page")
                return False

        except Exception as e:
            logging.error(f"Error during login: {e}")
            return False

    def dismiss_cookie_consent(self):
        """Dismiss cookie consent popup if present, preferring reject."""
        try:
            for text in ["Rechazar", "Rechazar todo", "Aceptar y continuar"]:
                btn = self.page.query_selector(f'button:has-text("{text}")')
                if btn:
                    btn.click()
                    logging.info(f"Dismissed cookie consent popup ({text})")
                    random_delay(1, 2)
                    return
        except Exception as e:
            logging.debug(f"Cookie consent dismissal: {e}")

    def detect_captcha_or_block(self):
        """Check if current page is showing a captcha or access block. Returns (blocked, reason)."""
        try:
            url = self.page.url.lower()
            title = self.page.title().lower()

            if any(x in url for x in ['captcha', 'challenge', 'blocked', 'verificacion', 'captcha-delivery']):
                return True, f"Suspicious redirect URL: {self.page.url}"

            if any(x in title for x in ['just a moment', 'attention required', 'acceso denegado',
                                         'verificación', 'captcha', 'challenge', 'error 403', 'forbidden',
                                         'verificación del dispositivo']):
                return True, f"Block/captcha page title: '{self.page.title()}'"

            # Check raw HTML — more reliable than inner_text for JS-rendered CAPTCHAs
            try:
                html = self.page.content().lower()
                if "var dd={'rt':'c'" in html:
                    return True, "Cloudflare Bot Management challenge detected"
                captcha_html_phrases = [
                    'desliza hacia la derecha', 'desliza el control',
                    'verificación de seguridad', 'prueba que eres humano',
                    'challenge-form', 'cf-challenge',
                    'please complete the security check', 'acceso restringido',
                    'you have been blocked', 'your access to this site has been limited',
                    'muchas peticiones', 'demasiadas peticiones',
                    'para asegurar tu acceso', 'recibiendo muchas peticiones',
                    'captcha-delivery.com', 'geo.captcha-delivery.com',
                    'verificación del dispositivo', 'verificacion del dispositivo',
                    'el contenido solicitado estará disponible después de la verificación',
                    'datadome',
                ]
                for phrase in captcha_html_phrases:
                    if phrase in html:
                        return True, f"Captcha/block phrase in HTML: '{phrase}'"
            except Exception as e:
                logging.warning(f"CAPTCHA HTML check failed: {e}")

            # Fallback: inner_text
            try:
                body_text = self.page.inner_text('body').lower()
                captcha_phrases = [
                    'verificación de seguridad', 'prueba que eres humano',
                    'desliza el control', 'desliza hacia la derecha',
                    'challenge-form', 'cf-challenge',
                    'please complete the security check', 'acceso restringido',
                    'you have been blocked', 'your access to this site has been limited',
                    'muchas peticiones', 'demasiadas peticiones',
                    'para asegurar tu acceso', 'recibiendo muchas peticiones',
                    'verificación del dispositivo', 'verificacion del dispositivo',
                    'el contenido solicitado estará disponible después de la verificación',
                ]
                for phrase in captcha_phrases:
                    if phrase in body_text:
                        return True, f"Captcha/block phrase detected: '{phrase}'"
            except Exception as e:
                logging.warning(f"CAPTCHA body text check failed (exception): {e}")

            return False, None

        except Exception as e:
            logging.debug(f"Error during captcha detection: {e}")
            return False, None

    def get_listings_from_search(self):
        """Get all listing URLs from search page"""
        try:
            logging.info(f"Navigating to search URL...")
            self.page.goto(self.search_url, wait_until="networkidle")

            self.dismiss_cookie_consent()

            # Simulate human-like behavior
            random_delay(2, 4)
            random_mouse_movement(self.page)
            random_delay(1, 2)
            random_scroll(self.page)
            simulate_reading(self.page, 2, 4)

            # Take a screenshot for debugging
            screenshot_path = LOGS_DIR / f"search_page_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            self.page.screenshot(path=str(screenshot_path))
            logging.info(f"Screenshot saved: {screenshot_path}")

            # Check for captcha or access block before trying to scrape
            blocked, reason = self.detect_captcha_or_block()
            if blocked:
                logging.error(f"CAPTCHA/BLOCK DETECTED: {reason}")
                capsolver_key = self.env.get('CAPSOLVER_API_KEY', '')
                if capsolver_key:
                    logging.info("Attempting DataDome auto-solve via CapSolver...")
                    if attempt_auto_solve(self.page, capsolver_key):
                        logging.info("Auto-solve succeeded — retrying scrape")
                        blocked, reason = self.detect_captcha_or_block()
                if blocked:
                    send_captcha_alert(reason, self.page.url, screenshot_path, self.env)
                    return []

            # Find all listing links
            listing_selectors = [
                'article.item a.item-link',
                'a[href*="/inmueble/"]',
                '.item-info-container a'
            ]

            listings = []
            for selector in listing_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    if elements:
                        for elem in elements:
                            href = elem.get_attribute('href')
                            if href and '/inmueble/' in href:
                                full_url = href if href.startswith('http') else f"https://www.idealista.com{href}"
                                listing_id = full_url.split('/')[-2] if '/' in full_url else full_url.split('/')[-1]
                                listings.append({
                                    'url': full_url,
                                    'id': listing_id
                                })
                        break
                except Exception as e:
                    logging.debug(f"Selector {selector} failed: {e}")
                    continue

            # Remove duplicates
            seen = set()
            unique_listings = []
            for listing in listings:
                if listing['id'] not in seen:
                    seen.add(listing['id'])
                    unique_listings.append(listing)

            logging.info(f"Found {len(unique_listings)} listings on search page")

            # If we found zero listings and the page loaded quickly, run a second CAPTCHA check
            # because the CAPTCHA page has no /inmueble/ links either
            if len(unique_listings) == 0:
                blocked2, reason2 = self.detect_captcha_or_block()
                if blocked2:
                    logging.error(f"CAPTCHA/BLOCK DETECTED (zero-listings check): {reason2}")
                    send_captcha_alert(reason2, self.page.url, screenshot_path, self.env)

            return unique_listings

        except Exception as e:
            logging.error(f"Error getting listings from search: {e}")
            return []

    def process_listing(self, listing_url, listing_id):
        """Process a single listing - snapshot, extract info, contact agent"""
        try:
            logging.info(f"Processing listing {listing_id}...")

            # Create snapshot directory
            snapshot_dir = LISTINGS_DIR / listing_id
            snapshot_dir.mkdir(exist_ok=True)
            photos_dir = snapshot_dir / "photos"
            photos_dir.mkdir(exist_ok=True)

            # Navigate to listing with human-like delay
            random_delay(1, 3)
            self.page.goto(listing_url, wait_until="networkidle")

            # Check for CAPTCHA/block before doing anything else
            blocked, reason = self.detect_captcha_or_block()
            if blocked:
                logging.error(f"CAPTCHA/BLOCK on listing page {listing_id}: {reason}")
                screenshot_path = snapshot_dir / "captcha_block.png"
                self.page.screenshot(path=str(screenshot_path))
                send_captcha_alert(reason, listing_url, str(screenshot_path), self.env)
                return False  # Don't mark as tracked — next run will retry

            # Dismiss cookie banner on listing pages too
            self.dismiss_cookie_consent()

            # Simulate human viewing the page
            random_delay(2, 4)
            random_mouse_movement(self.page)
            random_scroll(self.page)
            simulate_reading(self.page, 3, 6)

            # Extract listing details
            listing_data = {
                'date_found': datetime.now().isoformat(),
                'listing_id': listing_id,
                'url': listing_url,
                'snapshot_folder': str(snapshot_dir),
                'title': '',
                'price': '',
                'location': '',
                'phone': '',
                'description': '',
                'contacted': 'no',
                'bedrooms': '',
                'garage': 'No'
            }

            # Get title
            try:
                title_elem = self.page.query_selector('h1, .main-info__title')
                if title_elem:
                    listing_data['title'] = title_elem.inner_text().strip()
            except:
                pass

            # Get price
            try:
                price_elem = self.page.query_selector('.info-data-price, .price')
                if price_elem:
                    listing_data['price'] = price_elem.inner_text().strip()
            except:
                pass

            # Get location
            try:
                location_elem = self.page.query_selector('.main-info__title-minor, .location')
                if location_elem:
                    listing_data['location'] = location_elem.inner_text().strip()
            except:
                pass

            # Get description
            try:
                desc_elem = self.page.query_selector('.comment, .description')
                if desc_elem:
                    listing_data['description'] = desc_elem.inner_text().strip()
            except:
                pass

            # Get bedrooms
            try:
                page_text = self.page.inner_text('body')
                bedroom_match = re.search(r'(\d+)\s*habitacion', page_text, re.IGNORECASE)
                if bedroom_match:
                    listing_data['bedrooms'] = bedroom_match.group(1)
                else:
                    # Try feature list items
                    feature_elems = self.page.query_selector_all('.details-property_features li, .info-features span, .feature-list li')
                    for elem in feature_elems:
                        text = elem.inner_text().strip()
                        m = re.search(r'(\d+)\s*hab', text, re.IGNORECASE)
                        if m:
                            listing_data['bedrooms'] = m.group(1)
                            break
            except Exception as e:
                logging.debug(f"Could not extract bedrooms: {e}")

            # Detect garage
            try:
                page_text_lower = self.page.inner_text('body').lower()
                if any(word in page_text_lower for word in ['garaje', 'garage', 'parking incluido', 'plaza de parking']):
                    listing_data['garage'] = 'Yes'
            except Exception as e:
                logging.debug(f"Could not detect garage: {e}")

            # Extract phone number (only via tel: links — broad selectors return entire page text)
            try:
                phone_elem = self.page.query_selector('a[href^="tel:"]')
                if phone_elem:
                    href = phone_elem.get_attribute('href') or ''
                    phone = href.replace('tel:', '').strip()
                    if re.search(r'\d{6,}', phone):
                        listing_data['phone'] = phone
                        logging.info(f"Found phone: {phone}")
                    else:
                        # Fallback: get text but only if it looks like a phone number
                        text = (phone_elem.inner_text() or '').strip()
                        if re.search(r'\d{6,}', text):
                            listing_data['phone'] = text
                            logging.info(f"Found phone: {text}")
                if not listing_data['phone']:
                    logging.info("No phone number available for this listing")
            except Exception as e:
                logging.debug(f"Could not extract phone: {e}")

            # Save page HTML
            html_content = self.page.content()
            with open(snapshot_dir / "listing.html", 'w', encoding='utf-8') as f:
                f.write(html_content)

            # Save listing details as JSON
            with open(snapshot_dir / "details.json", 'w', encoding='utf-8') as f:
                json.dump(listing_data, f, indent=2, ensure_ascii=False)

            # Download photos
            try:
                # Scroll through page to trigger lazy-loaded images
                for _ in range(3):
                    random_scroll(self.page)
                    random_delay(0.5, 1)

                # Multiple strategies to find photos
                photo_urls = set()

                # Strategy 1: Find all img tags
                all_imgs = self.page.query_selector_all('img')
                logging.info(f"Found {len(all_imgs)} total img tags")

                for img in all_imgs:
                    # Try multiple attributes where URLs might be
                    for attr in ['src', 'data-src', 'data-lazy-src', 'data-original']:
                        src = img.get_attribute(attr)
                        if src:
                            # Filter for actual photo URLs
                            if any(x in src.lower() for x in ['idealista.com', 'img.', 'image', 'photo', '/fotos/', '.jpg', '.jpeg', '.png', '.webp']):
                                # Convert to full URL if relative
                                if src.startswith('//'):
                                    src = 'https:' + src
                                elif src.startswith('/'):
                                    src = 'https://www.idealista.com' + src

                                # Only add if it looks like a real photo (has reasonable size)
                                if len(src) > 20:
                                    photo_urls.add(src)

                # Strategy 2: Check for picture elements
                pictures = self.page.query_selector_all('picture source')
                for source in pictures:
                    srcset = source.get_attribute('srcset')
                    if srcset:
                        # srcset can have multiple URLs, take the first
                        url = srcset.split(',')[0].split(' ')[0]
                        if url and len(url) > 20:
                            if url.startswith('//'):
                                url = 'https:' + url
                            photo_urls.add(url)

                logging.info(f"Found {len(photo_urls)} photos to download")

                for idx, photo_url in enumerate(photo_urls, 1):
                    try:
                        response = requests.get(photo_url, timeout=10)
                        if response.status_code == 200:
                            ext = photo_url.split('.')[-1].split('?')[0]
                            if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                                ext = 'jpg'
                            photo_path = photos_dir / f"photo_{idx}.{ext}"
                            with open(photo_path, 'wb') as f:
                                f.write(response.content)
                            logging.info(f"Downloaded photo {idx}/{len(photo_urls)}")
                    except Exception as e:
                        logging.warning(f"Failed to download photo {idx}: {e}")

            except Exception as e:
                logging.error(f"Error downloading photos: {e}")

            # Contact the agent
            contacted = self.contact_agent()
            listing_data['contacted'] = 'yes' if contacted else 'failed'
            if contacted:
                logging.info(f"Successfully contacted agent for listing {listing_id}")
            else:
                logging.warning(f"Could not contact agent for listing {listing_id}")

            # Save to CSV
            save_to_csv(listing_data)

            # Send email notification
            gmail_password = self.env.get('GMAIL_APP_PASSWORD', '')
            notify_email = self.env.get('NOTIFY_EMAIL', self.email)
            if gmail_password:
                send_email_notification(listing_data, self.message, self.email, gmail_password, notify_email)
            else:
                logging.warning("GMAIL_APP_PASSWORD not set in .env — skipping email notification")

            # Mark as processed
            self.tracked[listing_id] = {
                'date': datetime.now().isoformat(),
                'url': listing_url,
                'snapshot': str(snapshot_dir),
                'contacted': listing_data['contacted']
            }
            save_tracked_listings(self.tracked)

            logging.info(f"Successfully processed listing {listing_id}")
            return True

        except Exception as e:
            logging.error(f"Error processing listing {listing_id}: {e}")
            return False

    def contact_agent(self):
        """Click contact button and send message"""
        try:
            logging.info("Attempting to contact agent...")

            # Scroll to contact section with human-like behavior
            random_scroll(self.page)
            random_delay(1, 2)

            # Idealista chat flow:
            # 1. "button.contact-fake" (sticky Chat button) opens the contact form
            # 2. "button.button-chat" (submit) becomes enabled after the form opens
            random_mouse_movement(self.page)
            random_delay(0.5, 1.5)

            # Step 1: open the contact form via the sticky Chat trigger
            opened = False
            try:
                trigger = self.page.query_selector('button.contact-fake')
                if trigger:
                    trigger.scroll_into_view_if_needed()
                    random_delay(0.5, 1)
                    trigger.click()
                    logging.info("Clicked Chat trigger button")
                    opened = True
                    random_delay(1, 2)
            except Exception as e:
                logging.debug(f"Could not click Chat trigger: {e}")

            if not opened:
                logging.warning("Could not open contact form — Chat trigger button not found")
                return False

            # Step 2: wait for the submit button to become enabled (JS enables it after form opens)
            try:
                self.page.wait_for_selector('button.button-chat:not([disabled])', timeout=8000)
            except Exception:
                btn = self.page.query_selector('button.button-chat')
                if btn and btn.get_attribute('disabled') is not None:
                    logging.warning("Contact button stayed disabled — account may need a tenant profile (perfil de inquilino)")
                    return False

            # Fill the message textarea — Idealista uses name="contact-message"
            try:
                textarea = self.page.query_selector('textarea[name="contact-message"]')
                if textarea:
                    current_text = textarea.input_value()
                    if not current_text or len(current_text) < 10:
                        random_delay(0.5, 1)
                        textarea.click()
                        textarea.fill('')
                        textarea.type(self.message, delay=random.randint(50, 150))
                        logging.info("Filled message textarea")
                    else:
                        logging.info("Message already present, using existing message")
                else:
                    logging.warning("Could not find message textarea")
            except Exception as e:
                logging.debug(f"Could not fill message: {e}")

            random_delay(1, 2)

            # Step 3: click the now-enabled submit button (button.button-chat)
            try:
                random_mouse_movement(self.page)
                random_delay(1, 2)
                submit_btn = self.page.query_selector('button.button-chat:not([disabled])')
                if not submit_btn:
                    logging.warning("Submit button not found or still disabled after filling form")
                    return False
                submit_btn.scroll_into_view_if_needed()
                submit_btn.click()
                logging.info("Clicked submit (Contactar por chat)")
                random_delay(3, 5)
            except Exception as e:
                logging.warning(f"Could not click submit button: {e}")
                return False

            # Verify message was sent
            success_selectors = [
                '*:has-text("Mensaje enviado")',
                '*:has-text("Tu mensaje ha sido enviado")',
                '*:has-text("mensaje enviado")',
                '*:has-text("Contactar de nuevo")',
                '.success-message',
            ]
            for success_sel in success_selectors:
                try:
                    self.page.wait_for_selector(success_sel, timeout=5000)
                    logging.info(f"Message send confirmed: {success_sel}")
                    return True
                except:
                    continue

            logging.warning("Submit clicked but no confirmation found — message may not have sent")
            return False

        except Exception as e:
            logging.error(f"Error contacting agent: {e}")
            return False

    def run_from_urls(self, urls):
        """Process specific listing URLs directly (email-triggered, no search page needed)."""
        logging.info("=" * 60)
        logging.info(f"IDEALISTA BOT — EMAIL TRIGGERED ({len(urls)} listings)")
        logging.info("=" * 60)

        with sync_playwright() as playwright:
            self.start_browser(playwright)

            new_count = 0
            for url in urls:
                match = re.search(r'/inmueble/(\d+)/', url)
                if not match:
                    logging.warning(f"Could not extract listing ID from URL: {url}")
                    continue
                listing_id = match.group(1)

                if listing_id in self.tracked:
                    logging.info(f"Already tracked: {listing_id}")
                    continue

                logging.info(f"NEW LISTING FROM EMAIL: {listing_id}")
                self.process_listing(url, listing_id)
                new_count += 1
                random_delay(5, 15)

            logging.info(f"Processed {new_count} new listings")
            logging.info("=" * 60)
            self.context.storage_state(path=str(STATE_FILE))

    def run(self):
        """Main bot execution — full search page scrape (scheduled fallback)."""
        logging.info("=" * 60)
        logging.info("IDEALISTA BOT STARTING")
        logging.info("=" * 60)

        with sync_playwright() as playwright:
            self.start_browser(playwright)

            # No need to login - we're using saved session

            # Get listings
            listings = self.get_listings_from_search()

            if not listings:
                logging.warning("No listings found")
                return

            # Process new listings
            new_count = 0
            for listing in listings:
                if listing['id'] not in self.tracked:
                    logging.info(f"NEW LISTING FOUND: {listing['id']}")
                    self.process_listing(listing['url'], listing['id'])
                    new_count += 1
                    # Random delay between listings to appear more human
                    random_delay(5, 15)
                else:
                    logging.debug(f"Already tracked: {listing['id']}")

            logging.info(f"Processed {new_count} new listings")
            logging.info("=" * 60)

            # Persist cookies/session so trust tokens survive across runs
            self.context.storage_state(path=str(STATE_FILE))
            logging.info("Session state saved")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--urls', nargs='+', help='Specific listing URLs to process (email-triggered)')
    args = parser.parse_args()

    env = load_env()

    idealista_email = env.get('IDEALISTA_EMAIL')
    password = env.get('IDEALISTA_PASSWORD')
    search_url = env.get('SEARCH_URL')
    message = env.get('CONTACT_MESSAGE')

    if not all([idealista_email, password, search_url, message]):
        logging.error("Missing required environment variables in .env file")
        return

    with IdealistaBot(idealista_email, password, search_url, message, env=env) as bot:
        if args.urls:
            bot.run_from_urls(args.urls)
        else:
            bot.run()

if __name__ == "__main__":
    main()
