"""Public Telegram channels via the t.me/s/<channel> web preview — no account or API keys needed."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator

from bs4 import BeautifulSoup

from ..models import Job
from . import client, parse_dt

ROLE = re.compile(r"data engineer|data quality|analytics engineer|data analyst|dwh|etl|data platform|"
                  r"инженер данных|аналитик данных|дата[- ]инженер|data qa|bi[- ]analyst|bi[- ]developer", re.I)
VACANCY = re.compile(r"ваканс|ищем|ищу|hiring|требовани|requirements|responsibilit|обязанност|"
                     r"#job|#vacancy|зарплат|salary|вилка|откликнуть|apply", re.I)
AD = re.compile(r"\berid\b|курс|поток программы|обучени|вебинар|скидк", re.I)
LOCATION = re.compile(r"(remote|удал[её]н|релокац|relocation|локаци|location|офис|office|hybrid|гибрид|"
                      r"worldwide|гео\b|geo\b)", re.I)
EMOJI = re.compile(r"[^\w\s\-–—&/+().,:#$€₽%]+")


def _clean(line: str) -> str:
    return EMOJI.sub("", line).strip(" -–—:•")


def _parse(post, channel: str) -> Job | None:
    body = post.select_one(".tgme_widget_message_text")
    if not body:
        return None
    text = body.get_text("\n", strip=True)
    if not (ROLE.search(text) and VACANCY.search(text)) or AD.search(text):
        return None
    lines = [_clean(l) for l in text.split("\n") if _clean(l)]
    title = next((l for l in lines if ROLE.search(l) and len(l) < 120), lines[0][:120])
    company = ""
    m = re.search(r"(?:компания|company)\s*[:\-–]\s*(.+)", text, re.I)
    if m:
        company = _clean(m.group(1))[:80]
    else:  # many channels put the company on the line after a 🏢 marker
        for raw, nxt in zip(text.split("\n"), text.split("\n")[1:]):
            if "🏢" in raw and _clean(nxt):
                company = _clean(nxt)[:80]
                break
    location = next((l for l in lines if LOCATION.search(l) and len(l) < 120), "")
    links = [a["href"] for a in body.select("a[href^=http]") if "t.me" not in a["href"]]
    post_id = post.select_one(".tgme_widget_message")["data-post"]  # "<channel>/<id>"
    when = post.select_one("time[datetime]")
    return Job(
        source=f"telegram:{channel}",
        external_id=post_id,
        title=title,
        company=company or f"@{channel}",
        url=f"https://t.me/{post_id}",
        apply_url=links[0] if links else f"https://t.me/{post_id}",
        location=location,
        description=text[:15000],
        published_at=parse_dt(when["datetime"]) if when else None,
    )


def telegram(channels: list[str], pages: int = 3) -> Iterator[Job]:
    with client() as c:
        for channel in channels:
            before = None
            for _ in range(pages):
                r = c.get(f"https://t.me/s/{channel}", params={"before": before} if before else None)
                posts = BeautifulSoup(r.text, "html.parser").select(".tgme_widget_message_wrap")
                if not posts:
                    break
                for post in posts:
                    job = _parse(post, channel)
                    if job:
                        yield job
                ids = [int(p.select_one(".tgme_widget_message")["data-post"].split("/")[1]) for p in posts]
                before = min(ids)
                time.sleep(1)
