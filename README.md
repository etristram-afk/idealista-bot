# idealista-bot

Monitors idealista.com for new rental listings matching your search, contacts agents automatically via the Idealista chat system, and sends you Telegram notifications with full listing details and photos.

**Trigger model**: the bot wakes up instantly when Idealista sends you a notification email (no constant polling.) This keeps request volume low and avoids bot-detection bans.

---

## ⚠ Before you run this: IP-flagging risk

Idealista's edge is protected by [DataDome](https://datadome.co/), which fingerprints every request — IP reputation, TLS/HTTP signatures, browser identity, behavior over time. **Running this bot from any IP will, sooner or later, get that IP flagged** by DataDome. Once flagged, you'll see:

- Stage 1: occasional slider CAPTCHAs (CapSolver handles these)
- Stage 2: `t=bv` responses where DataDome refuses to even offer a CAPTCHA (CapSolver explicitly cannot help — the bot now backs off automatically for 6h via its IP-burn cooldown)
- Stage 3: flat **HTTP 403** from the edge with no CAPTCHA at all — the IP is on the permanent blocklist

**A flagged IP is hard to un-flag.** DataDome does not publish appeal channels. Resetting your router for a new dynamic IP only helps if (a) your ISP actually rotates and (b) the fingerprint problem upstream of the IP is fixed. Otherwise the new IP is reflagged within minutes.

**What "any IP" means in practice:**

| Egress | Outcome |
|---|---|
| Your home / NAS IP | Flagged within days–weeks of regular use |
| Commercial VPN (ExpressVPN, NordVPN, M247 ranges, etc.) | Already pre-flagged — `403` from request one |
| Datacenter IP (DigitalOcean, AWS, etc.) | Same as above |
| Residential proxy (Spanish exit, paid) | Generally passes, but burnable per-IP if abused |
| Mobile carrier / 4G hotspot | Generally passes (CGNAT shared with real users) |

**Practical recommendations:**

1. **Use a residential proxy from day one.** This bot now supports one via `PROXY_SERVER` / `PROXY_USERNAME` / `PROXY_PASSWORD` in `.env` — see [Environment variables](#environment-variables-reference). Spanish exit is correct for idealista.es. Providers worth pricing: IPRoyal (~$1.75/GB), Smartproxy (~$7/GB, $80/mo min), Bright Data (premium). The bot's traffic is tiny (a few hundred KB per listing) so even premium providers cost single-digit dollars/month for personal use.
2. **Keep the trigger model.** The email-listener pattern in this repo is intentionally low-volume. Don't switch back to polling — it 10–100×s your request count and accelerates flagging.
3. **Don't share residential-proxy credentials.** Most providers price per GB; abuse will get your account suspended.
4. **If you're flagged, stop hammering.** Each retry from a burned IP makes the flag stickier. The bot's IP-burn cooldown enforces this automatically, but you should also resist manually `/retry`-ing during the cooldown window.

If you don't want to set up a residential proxy, this bot will still run — it just won't survive contact with DataDome for very long. Plan accordingly.

---

## How it works

1. **Email listener** watches your Gmail inbox via IMAP IDLE
2. When Idealista sends a notification email, the listener extracts the listing URLs and triggers the bot immediately
3. The bot opens a stealth Chromium browser (via [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)), navigates to each new listing, snapshots it, and sends a contact message through the Idealista chat system
4. You get a Telegram message with price, location, photos, and a link
5. A once-daily fallback scan at 9am catches anything that slipped through

---

## Requirements

- A server or NAS running Docker
- Chrome to run the one-time session setup
- An [idealista.com](https://www.idealista.com) account with email alerts enabled for your saved search with custom filters
- A Telegram bot token ([create one with @BotFather](https://t.me/botfather))
- A Gmail account that receives Idealista alerts, with a [Gmail App Password](https://myaccount.google.com/apppasswords)
- A [CapSolver](https://www.capsolver.com) API key — highly recommended (~$2.50/1000 CAPTCHA solves, rarely needed with the email-trigger model)

---

## Option A: Run directly on computer (simpler)

No server required. The bot runs on your own machine while it's on.

### 1. Install dependencies

```bash
git clone https://github.com/etristram-afk/idealista-bot.git
cd idealista-bot
pip3 install -r requirements.txt
patchright install chromium
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see [Environment variables](#environment-variables-reference) below).

### 3. Create a browser session

```bash
python3 setup_session_mac.py
```

Chrome will open to idealista.com. Log in, navigate to your saved search so listings are visible, then press **Enter**. The script saves your session cookies locally. You won't need to repeat this unless the session expires (usually weeks/months).

Leave `NAS_USER`/`NAS_HOST` at their placeholder values — the script will skip the NAS copy and save locally instead.

### 4. Run the email listener

This is the main process — keep it running in the background:

```bash
python3 email_listener.py
```

It connects to Gmail via IMAP IDLE and triggers the bot the moment an Idealista notification email arrives. The bot fires `idealista_bot.py` automatically with the new listing URLs.

To keep it running after you close the terminal, use a tool like [screen](https://www.gnu.org/software/screen/) or [tmux](https://github.com/tmux/tmux):

```bash
screen -S idealista
python3 email_listener.py
# Ctrl+A, D to detach; `screen -r idealista` to reattach
```

Or on Mac you can run it as a background process and have it auto-start at login using a LaunchAgent (see Apple's documentation).

### 5. Optional: daily fallback scan

Run once a day as a safety net in case an email was missed:

```bash
python3 idealista_bot.py
```

Set this up as a daily cron job:

```bash
# Run at 9am every day
0 9 * * * cd /path/to/idealista-bot && python3 idealista_bot.py
```

---

## Option B: Docker on a server (always-on)

### 1. Configure

On your server:

```bash
git clone https://github.com/etristram-afk/idealista-bot.git
cd idealista-bot
cp .env.example .env
# edit .env with your values
```

### 2. Enable Idealista email alerts

Log into idealista.com → go to your saved search → enable email notifications. The bot only runs when these emails arrive, so this step is essential.

### 3. Create a browser session (run once from computer)

```bash
pip3 install requests websocket-client
```

Edit the three lines at the top of `setup_session_mac.py` to point at your server:

```python
NAS_USER = "your_server_username"
NAS_HOST = "192.168.1.x"          # IP of your server on the local network
NAS_PATH = "/path/to/idealista-bot/browser_state.json"
```

Then run it:

```bash
python3 setup_session_mac.py
```

Chrome opens, you log in, press Enter, and your session is SSH-copied directly to the server.

### 4. Deploy with Docker

On your server/NAS:

```bash
# Copy the project to your server, then:
docker-compose up -d --build
```

The container starts three background processes:
- **Email listener** — IMAP IDLE connection to Gmail
- **Telegram listener** — handles `/done` command for manual CAPTCHA solving
- **Daily fallback scheduler** — one scan per day at 9am (Spain time)

### 5. Verify it's working

```bash
docker logs idealista-bot -f
```

You should see:
```
Email listener starting — watching your@gmail.com
Connected to Gmail IMAP
```

Send yourself a test by triggering an Idealista alert (or wait for the next one). Within seconds of the email arriving, the bot will fire.

---

## Refreshing the session

Sessions expire after weeks/months. Refresh by running `setup_session_mac.py` again from your Mac — it remembers your Chrome profile so you won't need to log in again.

---

## Environment variables reference

| Variable | Required | Description |
|---|---|---|
| `IDEALISTA_EMAIL` | Yes | Your idealista.com login email |
| `IDEALISTA_PASSWORD` | Yes | Your idealista.com password |
| `SEARCH_URL` | Yes | The full URL of your saved idealista search |
| `CONTACT_MESSAGE` | Yes | Message sent to agents (in Spanish) |
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your Telegram user/chat ID (from @userinfobot) |
| `NOTIFY_EMAIL` | Yes | Gmail address that receives Idealista alerts |
| `GMAIL_APP_PASSWORD` | Yes | Gmail App Password (not your regular password) |
| `CAPSOLVER_API_KEY` | Recommended | For automatic CAPTCHA solving. Sign up at [capsolver.com](https://capsolver.com) — with the email-trigger model, solves are rare so a small balance goes a long way. |

---

## Google Sheets integration (optional)

The bot can sync listings to a Google Sheet for easy browsing on any device. See [GOOGLE_SHEETS_SETUP.md](GOOGLE_SHEETS_SETUP.md) for instructions.

---

## Troubleshooting

**Bot gets blocked by Idealista**
- This happens if the bot makes too many requests too quickly (e.g. you had periodic polling enabled)
- Stop the container, wait 24–48 hours, restart
- Make sure your CapSolver key is set — it auto-resolves DataDome CAPTCHAs before they escalate

**Session expired / bot can't log in**
- Run `setup_session_mac.py` again from your Mac

**Email listener not triggering**
- Check that Idealista email alerts are enabled for your search
- Verify `NOTIFY_EMAIL` matches the inbox receiving Idealista emails
- Check `GMAIL_APP_PASSWORD` is a proper App Password (16 chars, spaces allowed)

**No Telegram messages**
- Make sure you've sent at least one message to your bot first (Telegram requires this to open the chat)
