#!/usr/bin/env python3
"""
Gmail listener — watches for Idealista notification emails via IMAP IDLE
and triggers the bot immediately for the specific new listings.
"""

import email
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from imapclient import IMAPClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / '.env'

IMAP_HOST = 'imap.gmail.com'
IDEALISTA_SENDER = 'idealista.com'
LISTING_URL_RE = re.compile(r'https://www\.idealista\.com/inmueble/(\d+)/?')


def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                env[k.strip()] = v.strip()
    env.update(os.environ)
    return env


def get_body(msg):
    body = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct in ('text/html', 'text/plain'):
                try:
                    body.append(part.get_payload(decode=True).decode('utf-8', errors='replace'))
                except Exception:
                    pass
    else:
        try:
            body.append(msg.get_payload(decode=True).decode('utf-8', errors='replace'))
        except Exception:
            pass
    return '\n'.join(body)


def extract_urls(body):
    ids = list(dict.fromkeys(LISTING_URL_RE.findall(body)))  # deduplicate, preserve order
    return [f'https://www.idealista.com/inmueble/{lid}/' for lid in ids]


BOT_SCRIPT = Path(__file__).parent / 'idealista_bot.py'


def trigger_bot(urls):
    logging.info(f"Triggering bot for {len(urls)} listing(s): {urls}")
    subprocess.run(
        ['python3', str(BOT_SCRIPT), '--urls'] + urls,
        cwd=str(BASE_DIR),
    )


def check_new_emails(client):
    msgs = client.search(['UNSEEN', 'FROM', IDEALISTA_SENDER])
    if not msgs:
        return
    logging.info(f"Found {len(msgs)} new Idealista email(s)")
    for uid in msgs:
        try:
            data = client.fetch([uid], ['RFC822'])
            raw = data[uid][b'RFC822']
            msg = email.message_from_bytes(raw)
            body = get_body(msg)
            urls = extract_urls(body)
            if urls:
                trigger_bot(urls)
            else:
                logging.info("Idealista email had no listing URLs (may be a digest/promo)")
            client.add_flags([uid], ['\\Seen'])
        except Exception as e:
            logging.error(f"Error processing email uid {uid}: {e}")


def mark_existing_as_seen(client):
    """Mark all current unread Idealista emails as seen — we only want future ones."""
    msgs = client.search(['UNSEEN', 'FROM', IDEALISTA_SENDER])
    if msgs:
        client.add_flags(msgs, ['\\Seen'])
        logging.info(f"Marked {len(msgs)} existing Idealista email(s) as seen — watching for new ones")


def monitor(gmail_user, gmail_password):
    logging.info(f"Email listener starting — watching {gmail_user}")
    while True:
        try:
            with IMAPClient(IMAP_HOST, ssl=True) as client:
                client.login(gmail_user, gmail_password)
                client.select_folder('INBOX')
                logging.info("Connected to Gmail IMAP")

                # Mark existing unread emails as seen; only trigger on new arrivals
                mark_existing_as_seen(client)

                while True:
                    client.idle()
                    # Re-IDLE before Gmail's 29-min limit; 270s keeps us well inside
                    responses = client.idle_check(timeout=270)
                    client.idle_done()

                    if responses:
                        check_new_emails(client)

        except Exception as e:
            logging.error(f"IMAP connection error: {e} — reconnecting in 60s")
            time.sleep(60)


def main():
    env = load_env()
    gmail_user = env.get('GMAIL_USER') or env.get('NOTIFY_EMAIL') or env.get('IDEALISTA_EMAIL', '')
    gmail_password = env.get('GMAIL_APP_PASSWORD', '')

    if not gmail_user or not gmail_password:
        logging.error("GMAIL_APP_PASSWORD must be set in .env — email listener exiting")
        return

    monitor(gmail_user, gmail_password)


if __name__ == '__main__':
    main()
