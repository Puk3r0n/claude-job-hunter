from __future__ import annotations

import html
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; jobhunt personal job search)"}


def client() -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=30, follow_redirects=True)


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    # Greenhouse returns HTML that is itself entity-escaped.
    if "&lt;" in raw:
        raw = html.unescape(raw)
    return BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)


def parse_dt(value) -> datetime | None:
    if value in (None, "", "None"):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            ts = float(value)
            if ts > 1e11:  # milliseconds
                ts /= 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def num(value) -> float | None:
    try:
        f = float(value)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None
