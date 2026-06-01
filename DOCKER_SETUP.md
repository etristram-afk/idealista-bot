# Docker Setup for NAS

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed on NAS
- Browser session file created on Mac (see below)

### 2. Create Browser Session (One-time setup on Mac)
```bash
cd ~/idealista-bot
python3 setup_session.py
```
This creates `browser_state.json` with your logged-in session.

### 3. Copy Files to NAS
All files from `~/idealista-bot/` need to be on your NAS at: `/volume1/docker/idealista-bot/`

### 4. Build and Run
SSH into NAS and run:
```bash
cd /volume1/docker/idealista-bot
docker-compose up -d
```

### 5. Check Logs
```bash
docker logs -f idealista-bot
```

## How It Works

- **Container runs 24/7** with built-in scheduler
- **5-minute intervals** during Spanish business hours (8am-9pm Spain time)
- **30-minute intervals** during off-hours
- **Data persists** in mounted volumes (listings, logs, CSV)

## File Structure on NAS

```
/volume1/docker/idealista-bot/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── docker_entrypoint.sh
├── idealista_bot.py
├── human_behavior.py
├── google_sheets_sync.py
├── .env
├── browser_state.json          # FROM MAC
├── google_credentials.json     # FROM MAC (optional)
├── .google_sheet_id           # FROM MAC (optional)
├── listings/                   # Persistent data
├── logs/                       # Persistent data
└── listings_database.csv       # Persistent data
```

## Important Files to Copy from Mac

**Required:**
- `browser_state.json` - Your logged-in session (create with `setup_session.py`)
- `.env` - Your credentials and search URL

**Optional (for Google Sheets):**
- `google_credentials.json` - Google service account credentials
- `.google_sheet_id` - Your Google Sheet ID

## Commands

**Start:**
```bash
docker-compose up -d
```

**Stop:**
```bash
docker-compose down
```

**Restart:**
```bash
docker-compose restart
```

**View logs:**
```bash
docker logs -f idealista-bot
```

**Rebuild after code changes:**
```bash
docker-compose up -d --build
```

## Troubleshooting

### "browser_state.json not found"
Run `setup_session.py` on your Mac, then copy `browser_state.json` to NAS.

### "Permission denied" errors
Make sure the mounted volumes have correct permissions:
```bash
chmod -R 755 /volume1/docker/idealista-bot/
```

### Browser crashes
Increase memory limit in `docker-compose.yml` (currently 2GB).

### Session expires
Re-run `setup_session.py` on Mac, then copy new `browser_state.json` to NAS and restart:
```bash
docker-compose restart
```
