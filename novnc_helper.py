"""Manages a websockify/noVNC proxy for remote CAPTCHA solving."""

import os
import signal
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent
PID_FILE = BASE_DIR / ".novnc_pid"
NOVNC_PORT = 6080
VNC_PORT = 5900

# noVNC static files: Docker image clones to /novnc; Mac install goes to ~/novnc
_NOVNC_PATHS = [Path("/novnc"), Path.home() / "novnc"]

_TAILSCALE_PATHS = [
    "/usr/local/bin/tailscale",
    "/usr/bin/tailscale",
    "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
]


def get_host() -> str | None:
    """Return the host IP to advertise in the noVNC URL.
    Prefers NOVNC_HOST env var (set in docker-compose), then falls back to Tailscale."""
    host = os.environ.get("NOVNC_HOST", "").strip()
    if host:
        return host
    for path in _TAILSCALE_PATHS:
        if not Path(path).exists():
            continue
        try:
            result = subprocess.run(
                [path, "ip", "--4"],
                capture_output=True, text=True, timeout=5,
            )
            ip = result.stdout.strip()
            if ip:
                return ip
        except Exception:
            continue
    return None


def _novnc_path() -> Path | None:
    for p in _NOVNC_PATHS:
        if p.exists():
            return p
    return None


def start(vnc_password: str, host: str) -> str:
    """Start websockify proxy. Returns the noVNC URL to send the user."""
    stop()

    novnc = _novnc_path()
    cmd = [
        "python3", "-m", "websockify",
        "--web", str(novnc) if novnc else ".",
        str(NOVNC_PORT),
        f"localhost:{VNC_PORT}",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PID_FILE.write_text(str(proc.pid))

    params = f"host={host}&port={NOVNC_PORT}&autoconnect=true&resize=scale"
    if vnc_password:
        params += f"&password={vnc_password}"
    return f"http://{host}:{NOVNC_PORT}/vnc.html?{params}"


def stop():
    """Kill the websockify process if running."""
    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, ValueError, OSError):
        pass
    PID_FILE.unlink(missing_ok=True)
