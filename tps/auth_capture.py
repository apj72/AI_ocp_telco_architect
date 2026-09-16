from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse


def parse_sharepoint_url(url: str) -> dict:
    """Extract base_url, path, domain, name from a full SharePoint URL."""
    parsed = urlparse(url)
    domain = parsed.netloc

    # Try ?id= query param first (deep links)
    qs = parse_qs(parsed.query)
    id_param = unquote(qs.get("id", [""])[0])

    if id_param:
        if "Shared Documents" in id_param:
            before, _, after = id_param.partition("Shared Documents")
            site_path = before.rstrip("/")
            doc_path = "Shared Documents" + ("/" + after.strip("/") if after.strip("/") else "")
        else:
            site_path = id_param.rstrip("/")
            doc_path = ""
    else:
        raw_path = unquote(parsed.path)
        clean = raw_path.split("/Forms/")[0].split("/_layouts/")[0]
        if "Shared Documents" in clean:
            before, _, after = clean.partition("Shared Documents")
            site_path = before.rstrip("/")
            doc_path = "Shared Documents" + ("/" + after.strip("/") if after.strip("/") else "")
        else:
            site_path = clean.rstrip("/")
            doc_path = ""

    base_url = f"{parsed.scheme}://{domain}{site_path}"
    name_parts = site_path.rstrip("/").split("/")
    name = name_parts[-1].replace("--", "-").strip("-") if name_parts else domain

    return {"base_url": base_url, "path": doc_path, "domain": domain, "name": name}


def capture_sharepoint_cookies(url: str, timeout_s: int = 300) -> dict:
    """Open visible browser to url, wait for SSO login, extract cookies.

    Returns {"cookies": str, "expires_at": str}.
    Raises RuntimeError on timeout or if Playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    domain = urlparse(url).netloc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url)

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            cookies = context.cookies()
            names = {c["name"] for c in cookies if domain in c.get("domain", "")}
            if names & {"FedAuth", "rtFa"}:
                break
            page.wait_for_timeout(1000)
        else:
            browser.close()
            raise RuntimeError("Timeout waiting for SSO login")

        all_cookies = context.cookies()
        sp_cookies = [
            c for c in all_cookies
            if domain in c.get("domain", "") or ".sharepoint.com" in c.get("domain", "")
        ]
        browser.close()

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in sp_cookies)

    # Estimate expiry from shortest-lived cookie, default 8h
    min_expiry = None
    for c in sp_cookies:
        if c.get("expires", -1) > 0:
            exp = datetime.fromtimestamp(c["expires"], tz=timezone.utc)
            if min_expiry is None or exp < min_expiry:
                min_expiry = exp
    if min_expiry is None:
        min_expiry = datetime.now(timezone.utc) + timedelta(hours=8)

    return {
        "cookies": cookie_str,
        "expires_at": min_expiry.isoformat(timespec="seconds"),
    }
