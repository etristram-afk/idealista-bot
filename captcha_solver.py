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


def _extract_datadome_captcha_url(page) -> str | None:
    try:
        html = page.content()
        match = re.search(r'https://geo\.captcha-delivery\.com/captcha/\?[^"\'>\s]+', html)
        if not match:
            return None
        url = match.group(0)
        if "t=bv" in url:
            logging.warning("DataDome returned t=bv (IP flagged) — solver cannot help")
            return None
        return url
    except Exception as e:
        logging.debug(f"Error extracting DataDome URL: {e}")
        return None


def _solve_via_capsolver(api_key: str, captcha_url: str, user_agent: str, timeout: int = 120) -> str | None:
    try:
        resp = requests.post(
            f"{CAPSOLVER_ENDPOINT}/createTask",
            json={"clientKey": api_key, "task": {"type": "DatadomeSliderTask", "captchaUrl": captcha_url, "userAgent": user_agent}},
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

    logging.info(f"CapSolver task submitted: {task_id}")
    deadline = time.time() + timeout
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
        if status == "ready":
            raw = result.get("solution", {}).get("cookie", "")
            if raw.startswith("datadome="):
                value = raw.split(";")[0].replace("datadome=", "").strip()
                logging.info("CapSolver: DataDome cookie obtained")
                return value
            logging.error(f"Unexpected cookie format from CapSolver: {raw!r}")
            return None
        elif status == "failed" or result.get("errorId"):
            logging.error(f"CapSolver solve failed: {result}")
            return None
        logging.debug(f"CapSolver status: {status}")

    logging.error("CapSolver timed out")
    return None


def attempt_auto_solve(page, api_key: str) -> bool:
    """
    Detect DataDome challenge on the current page, solve it via CapSolver,
    inject the cookie, and reload. Returns True if the challenge is cleared.
    """
    captcha_url = _extract_datadome_captcha_url(page)
    if not captcha_url:
        logging.info("No DataDome captcha URL found — cannot auto-solve")
        return False

    logging.info(f"DataDome challenge detected, submitting to CapSolver...")
    try:
        user_agent = page.evaluate("navigator.userAgent")
    except Exception:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

    cookie_value = _solve_via_capsolver(api_key, captcha_url, user_agent)
    if not cookie_value:
        return False

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
        return False

    # Reload and verify the challenge is gone
    try:
        page.reload(wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
    except Exception as e:
        logging.warning(f"Reload after cookie injection failed: {e}")

    if _extract_datadome_captcha_url(page):
        logging.warning("DataDome challenge still present after cookie injection")
        return False

    logging.info("DataDome challenge cleared successfully")
    return True
