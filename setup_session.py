#!/usr/bin/env python3
"""
Setup Script - Manual Login to Save Session
Launches Chrome directly (not via Playwright) so it renders on Xvfb/VNC.
Run this once to log in manually and save your session.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "browser_state.json"
DONE_FILE = BASE_DIR / ".captcha_done"
MAX_WAIT_SECS = 600  # 10 minutes

CHROME = "/ms-playwright/chromium-1223/chrome-linux64/chrome"
USER_DATA = "/tmp/chrome_setup_profile"
CDP_PORT = 9223  # separate port so it doesn't conflict with bot

def get_cookies_via_cdp():
    """Pull all cookies from the running Chrome via CDP."""
    try:
        tabs = requests.get(f"http://localhost:{CDP_PORT}/json", timeout=5).json()
        ws_url = None
        for tab in tabs:
            if tab.get("type") == "page":
                ws_url = tab.get("webSocketDebuggerUrl")
                break
        if not ws_url:
            return []

        import websocket, threading

        cookies = []
        done = threading.Event()

        def on_message(ws, msg):
            data = json.loads(msg)
            if data.get("id") == 1:
                cookies.extend(data.get("result", {}).get("cookies", []))
                done.set()

        ws = websocket.WebSocketApp(ws_url, on_message=on_message)
        t = threading.Thread(target=ws.run_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
        done.wait(timeout=10)
        ws.close()
        return cookies
    except Exception as e:
        print(f"CDP cookie extraction failed: {e}")
        return []


def main():
    print("=" * 60)
    print("IDEALISTA SESSION SETUP")
    print("=" * 60)
    print()
    print("A browser will open. Please:")
    print("1. Log in to idealista.com")
    print("2. Solve ANY slider CAPTCHA (drag right)")
    print("3. Navigate to your saved search")
    print("4. Make sure listings are visible")
    print("5. Send /done from Telegram (or wait — times out in 10 min)")
    print()

    env = {**os.environ, "DISPLAY": ":99"}

    proc = subprocess.Popen([
        CHROME,
        f"--remote-debugging-port={CDP_PORT}",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--start-maximized",
        f"--user-data-dir={USER_DATA}",
        "https://www.idealista.com",
    ], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for Chrome to start
    for _ in range(20):
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    print()
    print("Browser opened. Log in, then send /done from Telegram.")
    print(f"Auto-saves after {MAX_WAIT_SECS // 60} minutes if you don't.")
    print()

    DONE_FILE.unlink(missing_ok=True)
    for _ in range(MAX_WAIT_SECS):
        if DONE_FILE.exists():
            DONE_FILE.unlink(missing_ok=True)
            print("Done signal received.")
            break
        time.sleep(1)

    print("Extracting cookies...")
    cookies = get_cookies_via_cdp()

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    if not cookies:
        print("WARNING: No cookies extracted — session may be empty.")

    # Save in Playwright storage_state format
    state = {"cookies": cookies, "origins": []}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

    idealista_cookies = [c for c in cookies if "idealista" in c.get("domain", "")]
    print()
    print(f"✓ Session saved — {len(idealista_cookies)} idealista cookies")
    print(f"✓ Session file: {STATE_FILE}")
    print()
    print("You can now run the bot with: python3 idealista_bot.py")
    print()


if __name__ == "__main__":
    main()
