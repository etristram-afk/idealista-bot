#!/usr/bin/env python3
"""
DataDome CAPTCHA auto-solver via CapSolver API.
Integrates with an existing Patchright/Playwright browser context.
"""

import logging
import re
import time

import requests

CAPSOLVER_ENDPOINT = "https://api.capsolver.com"


def _extract_datadome_captcha_url(page, attempts: int = 3, delay: float = 1.0) -> tuple[str | None, bool]:
    """
    Look for a DataDome captcha URL in the current page HTML.

    DataDome's challenge iframe is sometimes injected after initial load, so we
    retry a few times with a short delay before giving up.

    Returns (url, burned):
      - url:    the captcha-delivery URL if found and solvable, else None.
      - burned: True if a t=bv ("IP flagged") URL was seen — solver cannot help
                and the caller should back off rather than retry.
    """
    burned = False
    for attempt in range(1, attempts + 1):
        try:
            html = page.content()
            match = re.search(r'https://geo\.captcha-delivery\.com/captcha/\?[^"\'>\s]+', html)
            if match:
                url = match.group(0)
                if "t=bv" in url:
                    logging.warning("DataDome returned t=bv (IP flagged) — solver cannot help")
                    return None, True
                logging.info(f"DataDome captcha URL found on attempt {attempt}/{attempts}")
                return url, False
        except Exception as e:
            logging.debug(f"Error extracting DataDome URL (attempt {attempt}): {e}")
        if attempt < attempts:
            time.sleep(delay)
    logging.info(f"No DataDome captcha URL found after {attempts} attempt(s)")
    return None, burned


def _solve_via_capsolver(api_key: str, captcha_url: str, user_agent: str, timeout: int = 120, proxy: str | None = None) -> str | None:
    # When a proxy is set, CapSolver solves *through* it so the DataDome cookie
    # is bound to the same IP the browser uses. Without this the cookie would
    # be tied to CapSolver's IP and reject when our (proxied) browser presents it.
    task = {"type": "DatadomeSliderTask", "captchaUrl": captcha_url, "userAgent": user_agent}
    if proxy:
        task["proxy"] = proxy
        logging.info(f"CapSolver createTask: type=DatadomeSliderTask ua={user_agent[:80]!r} proxy=set")
    else:
        logging.info(f"CapSolver createTask: type=DatadomeSliderTask ua={user_agent[:80]!r} proxy=none")
    try:
        resp = requests.post(
            f"{CAPSOLVER_ENDPOINT}/createTask",
            json={"clientKey": api_key, "task": task},
            timeout=30,
        )
        data = resp.json()
    except Exception as e:
        logging.error(f"CapSolver createTask error: {e}")
        return None

    task_id = data.get("taskId")
    if not task_id:
        logging.error(f"CapSolver task creation failed: {data}")
        return None

    logging.info(f"CapSolver task submitted: taskId={task_id}")
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        time.sleep(4)
        try:
            result = requests.post(
                f"{CAPSOLVER_ENDPOINT}/getTaskResult",
                json={"clientKey": api_key, "taskId": task_id},
                timeout=30,
            ).json()
        except Exception as e:
            logging.warning(f"CapSolver poll error: {e}")
            continue

        status = result.get("status")
        if status != last_status:
            logging.info(f"CapSolver taskId={task_id} status: {last_status} -> {status}")
            last_status = status
        if status == "ready":
            raw = result.get("solution", {}).get("cookie", "")
            if raw.startswith("datadome="):
                value = raw.split(";")[0].replace("datadome=", "").strip()
                logging.info(f"CapSolver taskId={task_id}: DataDome cookie obtained ({len(value)} chars)")
                return value
            logging.error(f"Unexpected cookie format from CapSolver: {raw!r}")
            return None
        elif status == "failed" or result.get("errorId"):
            logging.error(f"CapSolver solve failed (taskId={task_id}): {result}")
            return None

    logging.error(f"CapSolver timed out (taskId={task_id})")
    return None


def attempt_auto_solve(page, api_key: str, proxy: str | None = None) -> tuple[bool, bool]:
    """
    Detect DataDome challenge on the current page, solve it via CapSolver,
    inject the cookie, and reload.

    Args:
      proxy: optional proxy URL in the form scheme://[user:pass@]host:port.
        Passed to CapSolver so the solve happens through the same egress
        IP the browser is using — required when the browser itself is proxied,
        otherwise DataDome will reject the resulting cookie as IP-mismatched.

    Returns (solved, burned):
      - solved: True if the challenge is cleared after cookie injection.
      - burned: True if DataDome served a t=bv (IP burn) URL — solver cannot
                help; caller should back off rather than immediately retry.
    """
    logging.info("CapSolver auto-solve invoked")
    captcha_url, burned = _extract_datadome_captcha_url(page)
    if burned:
        logging.warning("CapSolver auto-solve aborted: IP burn (t=bv)")
        return False, True
    if not captcha_url:
        logging.info("CapSolver auto-solve aborted: no captcha URL on page")
        return False, False

    logging.info(f"DataDome challenge URL: {captcha_url[:120]}...")
    try:
        user_agent = page.evaluate("navigator.userAgent")
        logging.info(f"Browser UA for CapSolver: {user_agent[:120]}")
    except Exception as e:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        logging.warning(f"Could not read navigator.userAgent ({e}); falling back to default UA")

    cookie_value = _solve_via_capsolver(api_key, captcha_url, user_agent, proxy=proxy)
    if not cookie_value:
        logging.warning("CapSolver did not return a cookie")
        return False, False

    # Inject the datadome cookie into the browser context
    try:
        from urllib.parse import urlparse
        hostname = urlparse(page.url).hostname or "www.idealista.com"
        base_domain = ".".join(hostname.split(".")[-2:])
        page.context.add_cookies([{
            "name": "datadome",
            "value": cookie_value,
            "domain": f".{base_domain}",
            "path": "/",
            "secure": True,
            "sameSite": "Lax",
        }])
        logging.info(f"Injected datadome cookie for .{base_domain}")
    except Exception as e:
        logging.error(f"Failed to inject cookie: {e}")
        return False, False

    # Reload and verify the challenge is gone
    try:
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        logging.info("Page reloaded after cookie injection")
    except Exception as e:
        logging.warning(f"Reload after cookie injection failed: {e}")

    post_url, post_burned = _extract_datadome_captcha_url(page, attempts=2, delay=1.0)
    if post_burned:
        logging.warning("DataDome challenge still present after reload (now t=bv burn)")
        return False, True
    if post_url:
        logging.warning("DataDome challenge still present after cookie injection")
        return False, False

    logging.info("DataDome challenge cleared successfully")
    return True, False
