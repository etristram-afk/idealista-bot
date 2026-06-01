#!/usr/bin/env python3
"""
Mac Setup Script - opens Chrome locally, saves session, copies to NAS.
Run from your Mac: python3 setup_session_mac.py
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
STATE_FILE = BASE_DIR / "browser_state.json"
CDP_PORT = 9223
USER_DATA = "/tmp/idealista_setup_profile"

CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

# ── Edit these to match your NAS/server ─────────────────────────────────────
NAS_USER = "your_nas_username"
NAS_HOST = "192.168.1.x"           # local IP of your NAS
NAS_PATH = "/volume1/docker/idealista-bot/browser_state.json"
# ─────────────────────────────────────────────────────────────────────────────


def find_chrome():
    for path in CHROME_PATHS:
        if Path(path).exists():
            return path
    sys.exit("Chrome not found. Install Google Chrome and try again.")


def wait_for_cdp():
    for _ in range(30):
        try:
            requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


LOG_FILE = Path("/tmp/idealista_setup_debug.log")

def log(msg):
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def get_cookies_via_cdp():
    import websocket

    LOG_FILE.unlink(missing_ok=True)
    log("--- CDP extraction start ---")

    def try_ws(ws_url, label):
        log(f"Connecting to {label}: {ws_url}")
        ws = websocket.create_connection(ws_url, timeout=10)
        try:
            ws.send(json.dumps({"id": 1, "method": "Network.getAllCookies"}))
            log("Sent Network.getAllCookies, waiting for response...")
            for i in range(30):
                raw = ws.recv()
                response = json.loads(raw)
                log(f"  msg {i}: id={response.get('id')} method={response.get('method')} error={response.get('error')}")
                if response.get("id") == 1:
                    if "error" in response:
                        log(f"CDP error: {response['error']}")
                        return []
                    cookies = response.get("result", {}).get("cookies", [])
                    log(f"  Got {len(cookies)} cookies")
                    return cookies
            log("Timed out waiting for response")
            return []
        finally:
            ws.close()

    # Try browser target first
    try:
        version = requests.get(f"http://localhost:{CDP_PORT}/json/version", timeout=5).json()
        log(f"Version: {version.get('Browser')} wsUrl={version.get('webSocketDebuggerUrl','none')[:80]}")
        ws_url = version.get("webSocketDebuggerUrl")
        if ws_url:
            cookies = try_ws(ws_url, "browser")
            if cookies:
                return cookies
    except Exception as e:
        log(f"Browser target failed: {e}")

    # Fall back to first page target
    try:
        tabs = requests.get(f"http://localhost:{CDP_PORT}/json", timeout=5).json()
        log(f"Tabs: {[(t.get('type'), t.get('url','')[:60]) for t in tabs]}")
        ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"), None)
        if ws_url:
            return try_ws(ws_url, "page")
        log("No page tab found")
    except Exception as e:
        log(f"Page target failed: {e}")

    return []


def copy_to_nas():
    placeholder = "192.168.1.x"
    if not NAS_HOST or NAS_HOST == placeholder:
        print("NAS not configured — session saved locally only.")
        print(f"Session file: {STATE_FILE}")
        return
    print(f"Copying session to NAS ({NAS_HOST})...")
    result = subprocess.run(
        ["ssh", f"{NAS_USER}@{NAS_HOST}",
         f"cat > {NAS_PATH}"],
        input=STATE_FILE.read_bytes(),
        capture_output=True,
    )
    if result.returncode == 0:
        print(f"✓ Copied to NAS: {NAS_PATH}")
    else:
        print(f"✗ Copy to NAS failed: {result.stderr.decode()}")
        print(f"  Copy manually: scp {STATE_FILE} {NAS_USER}@{NAS_HOST}:{NAS_PATH}")


def main():
    chrome = find_chrome()

    print("=" * 60)
    print("IDEALISTA SESSION SETUP (Mac)")
    print("=" * 60)
    print()
    print("Chrome will open. Please:")
    print("1. Log in to idealista.com")
    print("2. Solve any CAPTCHA if shown")
    print("3. Navigate to your saved search")
    print("4. Make sure listings are visible")
    print("5. Press Enter here to save and close")
    print()

    # Kill any leftover Chrome on this port
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"], capture_output=True)
    time.sleep(1)

    proc = subprocess.Popen([
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={USER_DATA}",
        "https://www.idealista.com",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not wait_for_cdp():
        print("Chrome didn't start in time.")
        sys.exit(1)

    print("Chrome is open. Log in, then press Enter here when ready...")
    input()

    print("Saving session...")
    cookies = get_cookies_via_cdp()

    subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"], capture_output=True)
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    for cookie in cookies:
        if "partitionKey" in cookie and not isinstance(cookie["partitionKey"], str):
            del cookie["partitionKey"]

    state = {"cookies": cookies, "origins": []}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

    idealista_cookies = [c for c in cookies if "idealista" in c.get("domain", "")]
    print(f"✓ {len(idealista_cookies)} idealista cookies saved to {STATE_FILE}")

    copy_to_nas()

    print()
    print("Done! The NAS bot will use this session on its next run.")


if __name__ == "__main__":
    main()
