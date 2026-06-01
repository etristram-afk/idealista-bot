#!/usr/bin/env python3
"""
Telegram command listener for Idealista Bot.
Called by scheduler.sh before each bot run to process pending commands.

Commands:
  /status  — show bot status and last run
  /retry   — force an immediate bot run
  /solve   — open CAPTCHA browser and stream desktop via Tailscale/noVNC link
  /done    — save session and close the noVNC proxy
  /help    — show available commands
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
import requests

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
LOGS_DIR = BASE_DIR / "logs"
TRACKING_FILE = BASE_DIR / "tracked_listings.json"
CAPTCHA_ALERT_FILE = LOGS_DIR / "last_captcha_alert.txt"
FORCE_RUN_FILE = BASE_DIR / ".force_run"
LAST_UPDATE_FILE = BASE_DIR / ".last_telegram_update_id"

STALE_COMMAND_SECS = 600  # ignore commands older than 10 minutes

logging.basicConfig(level=logging.WARNING)


def load_env():
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars


def tg_api(token, method, **kwargs):
    """Call a Telegram Bot API method. Returns result list/dict or None."""
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=kwargs,
            timeout=15
        )
        if resp.ok:
            return resp.json().get("result")
        return None
    except Exception as e:
        logging.error(f"Telegram {method} error: {e}")
        return None


def send_message(token, chat_id, text, reply_markup=None):
    kwargs = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        kwargs["reply_markup"] = reply_markup
    return tg_api(token, "sendMessage", **kwargs)


def get_status():
    lines = ["*Idealista Bot Status*\n"]

    log_file = LOGS_DIR / "scheduler.log"
    if log_file.exists():
        log_lines = log_file.read_text().splitlines()
        last_run = None
        for line in reversed(log_lines):
            if "Running bot" in line:
                last_run = line.split("Running bot")[0].strip().rstrip(":")
                break
        lines.append(f"Last run: {last_run or 'unknown'}")
    else:
        lines.append("Last run: no log yet")

    if TRACKING_FILE.exists():
        try:
            tracked = json.loads(TRACKING_FILE.read_text())
            lines.append(f"Listings tracked: {len(tracked)}")
        except Exception:
            lines.append("Listings tracked: unknown")
    else:
        lines.append("Listings tracked: 0")

    if CAPTCHA_ALERT_FILE.exists():
        try:
            dt = datetime.fromisoformat(CAPTCHA_ALERT_FILE.read_text().strip())
            hours_ago = (datetime.now() - dt).total_seconds() / 3600
            if hours_ago < 24:
                lines.append(f"⚠️ Last CAPTCHA: {hours_ago:.1f}h ago")
            else:
                lines.append("✅ No recent CAPTCHA")
        except Exception:
            lines.append("✅ No recent CAPTCHA")
    else:
        lines.append("✅ No recent CAPTCHA")

    return "\n".join(lines)


def do_retry(token, chat_id):
    FORCE_RUN_FILE.touch()
    send_message(token, chat_id, "✅ Force run scheduled — bot will run within 5 minutes.")


def do_solve(token, chat_id):
    env = load_env()
    vnc_password = env.get('VNC_PASSWORD', '')  # empty = no-password VNC (Docker mode)

    # Launch the headed browser (runs until /done or 10-min timeout)
    subprocess.Popen(
        [sys.executable, str(BASE_DIR / 'setup_session.py')],
        cwd=str(BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    sys.path.insert(0, str(BASE_DIR))
    try:
        import novnc_helper
        host = novnc_helper.get_host()
        if not host:
            raise RuntimeError("No host IP available (set NOVNC_HOST or connect Tailscale)")
        time.sleep(2)  # give browser a moment to start
        url = novnc_helper.start(vnc_password, host)
        send_message(
            token, chat_id,
            f"🖥️ *CAPTCHA solver ready*\n\n"
            f"[Tap to open VNC in browser]({url})\n\n"
            "Drag the slider to solve, then send /done to save and close."
        )
    except Exception as e:
        logging.error(f"noVNC start error: {e}")
        send_message(
            token, chat_id,
            "🖥️ *Setup browser launched* — could not start noVNC proxy.\n\n"
            "Check that websockify is installed and Screen Sharing is enabled.\n\n"
            "Send /done when finished."
        )


def do_done(token, chat_id):
    (BASE_DIR / ".captcha_done").touch()

    sys.path.insert(0, str(BASE_DIR))
    try:
        import novnc_helper
        novnc_helper.stop()
    except Exception:
        pass

    send_message(token, chat_id, "✅ Done — session saved and VNC closed.")


def handle_update(update, token, chat_id):
    chat_id_str = str(chat_id)
    now_ts = time.time()

    # Handle inline button presses (callback_query)
    callback = update.get("callback_query")
    if callback:
        cb_chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
        if cb_chat_id == chat_id_str:
            data = callback.get("data", "")
            cb_id = callback.get("id", "")
            tg_api(token, "answerCallbackQuery", callback_query_id=cb_id)
            if data == "retry":
                do_retry(token, chat_id)
            elif data == "solve":
                do_solve(token, chat_id)
        return

    # Handle text commands
    message = update.get("message", {})
    text = (message.get("text") or "").strip()
    msg_chat_id = str(message.get("chat", {}).get("id", ""))
    msg_date = message.get("date", 0)

    if msg_chat_id != chat_id_str:
        return
    if not text.startswith("/"):
        return
    if now_ts - msg_date > STALE_COMMAND_SECS:
        return  # skip commands sent before this listener was running

    cmd = text.split()[0].lower().split("@")[0]  # strip @botname suffix

    if cmd == "/status":
        send_message(token, chat_id, get_status())
    elif cmd == "/retry":
        do_retry(token, chat_id)
    elif cmd == "/solve":
        do_solve(token, chat_id)
    elif cmd == "/done":
        do_done(token, chat_id)
    elif cmd == "/help":
        send_message(
            token, chat_id,
            "*Idealista Bot Commands*\n\n"
            "/status — Show bot status and last run\n"
            "/retry — Force an immediate bot run\n"
            "/solve — Open CAPTCHA browser + stream via noVNC link\n"
            "/done — Save session and close VNC\n"
            "/help — Show this message"
        )


def poll_once(token, chat_id):
    """Fetch and handle all pending Telegram updates."""
    last_update_id = 0
    if LAST_UPDATE_FILE.exists():
        try:
            last_update_id = int(LAST_UPDATE_FILE.read_text().strip())
        except Exception:
            pass

    updates = tg_api(token, "getUpdates",
                     offset=last_update_id + 1,
                     timeout=0,
                     limit=20)

    if not updates:
        return

    for update in updates:
        update_id = update.get("update_id", 0)
        handle_update(update, token, chat_id)
        if update_id > last_update_id:
            last_update_id = update_id

    LAST_UPDATE_FILE.write_text(str(last_update_id))


def main():
    env = load_env()
    token = env.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = env.get('TELEGRAM_CHAT_ID', '')

    if not (token and chat_id):
        return  # Telegram not configured, skip silently

    poll_once(token, chat_id)


if __name__ == "__main__":
    main()
