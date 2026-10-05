"""Cheap rule-based pre-filters, applied before any LLM call."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .models import Job

SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
CODES = ["USD", "EUR", "GBP", "CHF", "PLN", "AED", "CAD", "AUD"]

# Location strings that usually mean "open to candidates abroad". Extend via config `search.open_location_markers`.
OPEN_MARKERS = ["worldwide", "anywhere", "global", "emea", "europe", "cet", "international", "any location",
                "multiple locations"]
REMOTE_ONLY = re.compile(r"^\W*(fully\s+)?remote\W*$", re.I)


def title_ok(job: Job, include: list[str], exclude: list[str]) -> bool:
    t = job.title.lower()
    return any(k in t for k in include) and not any(re.search(rf"\b{re.escape(k)}\b", t) for k in exclude)


def location_ok(job: Job, extra_markers: list[str] = ()) -> bool:
    loc = job.location.strip().lower()
    if not loc or REMOTE_ONLY.match(loc):
        return True
    return any(m in loc for m in [*OPEN_MARKERS, *(m.lower() for m in extra_markers)])


def fresh(job: Job, max_age_days: int) -> bool:
    if not job.published_at:
        return True
    return job.published_at >= datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _parse_amount(s: str) -> float:
    s = s.lower().replace(",", "").replace(" ", "")
    mult = 1000 if s.endswith("k") else 1
    return float(s.rstrip("k")) * mult


def parse_salary_text(text: str) -> tuple[float | None, float | None, str | None, str | None]:
    """'$90k - $120k', '€80K – €100K', '$40/hr' -> (min, max, currency, period)."""
    if not text:
        return None, None, None, None
    currency = next((c for sym, c in SYMBOLS.items() if sym in text), None)
    currency = currency or next((c for c in CODES if c in text.upper()), None)
    amounts = [_parse_amount(m) for m in re.findall(r"\d[\d,\s]*(?:\.\d+)?\s?[kK]?", text) if m.strip()]
    amounts = [a for a in amounts if a >= 10]
    if not amounts:
        return None, None, currency, None
    lo, hi = min(amounts), max(amounts)
    low = text.lower()
    if re.search(r"/\s?h|hour|hr\b", low):
        period = "hour"
    elif re.search(r"/\s?mo|month", low):
        period = "month"
    elif re.search(r"/\s?y|year|annual|yr\b", low):
        period = "year"
    else:
        period = "hour" if hi < 500 else "month" if hi < 20000 else "year"
    return lo, hi, currency, period


def monthly_usd(job: Job, fx: dict[str, float]) -> tuple[float | None, float | None]:
    lo, hi, cur, period = job.salary_min, job.salary_max, job.salary_currency, job.salary_period
    if lo is None and hi is None and job.salary_text:
        lo, hi, cur2, period = parse_salary_text(job.salary_text)
        cur = cur or cur2
    if lo is None and hi is None:
        return None, None
    rate = fx.get((cur or "USD").upper())
    if rate is None:
        return None, None
    factor = {"year": 1 / 12, "month": 1, "hour": 160}.get(period or "year", 1 / 12)
    conv = lambda v: round(v * rate * factor) if v else None
    return conv(lo), conv(hi or lo)


def prefilter(job: Job, cfg: dict) -> str | None:
    """Returns a rejection reason, or None if the job should go to LLM scoring."""
    s = cfg["search"]
    if not title_ok(job, s["title_include"], s["title_exclude"]):
        return "title"
    if not fresh(job, s["max_age_days"]):
        return "stale"
    if not location_ok(job, s.get("open_location_markers", [])):
        return "location"
    if (job.salary_currency or "").upper() in s.get("reject_currencies", []):
        return "currency"
    if not job.salary_currency and re.search(r"₽|руб", job.salary_text, re.I):
        return "currency"
    _, hi = monthly_usd(job, cfg["fx_to_usd"])
    if hi is not None and hi < s["min_monthly_usd"]:
        return "salary"
    return None
