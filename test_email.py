#!/usr/bin/env python3
"""Send a practice email to verify email notification setup."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

ENV_FILE = Path(__file__).parent / ".env"

def load_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    return env

def main():
    env = load_env()
    gmail_user = env.get('IDEALISTA_EMAIL')
    gmail_password = env.get('GMAIL_APP_PASSWORD', '').replace(' ', '')
    notify_email = env.get('NOTIFY_EMAIL', gmail_user)
    contact_message = env.get('CONTACT_MESSAGE', '(no message configured)')

    if not gmail_password:
        print("ERROR: GMAIL_APP_PASSWORD not set in .env")
        return

    subject = "Test: New Idealista listing — Piso en Eixample — 2.200 €/mes"
    snapshot_folder = Path(__file__).parent / "listings" / "TEST123"
    photos_url = f"file://{snapshot_folder}/photos"

    body = f"""NEW LISTING FOUND
{'=' * 50}
Title:     Piso en Eixample — TEST
Price:     2.200 €/mes
Location:  Eixample, Barcelona
Bedrooms:  3
Garage:    No
URL:       https://www.idealista.com/inmueble/TEST123/
Photos:    {photos_url}
Found at:  2026-05-04T10:30:00

MESSAGE SENT TO AGENT
{'=' * 50}
{contact_message}

Agent contacted: yes
"""

    msg = MIMEMultipart()
    msg['From'] = gmail_user
    msg['To'] = notify_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    print(f"Sending practice email to {notify_email}...")
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(gmail_user, gmail_password)
            server.send_message(msg)
        print("Practice email sent successfully! Check your inbox.")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    main()
