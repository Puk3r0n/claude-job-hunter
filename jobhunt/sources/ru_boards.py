"""Russian-language boards with remote jobs paid in foreign currency (Habr Career, Getmatch)."""
from __future__ import annotations

from collections.abc import Iterator

from bs4 import BeautifulSoup

from ..models import Job
from . import client, html_to_text, num, parse_dt

HABR_QUERIES = ["data engineer", "инженер данных", "data quality", "analytics engineer", "аналитик данных", "dwh",
                "data qa", "тестировщик dwh", "тестировщик данных"]
HABR_CURRENCY = {"rur": "RUB", "usd": "USD", "eur": "EUR"}


def habr() -> Iterator[Job]:
    with client() as c:
        for q in HABR_QUERIES:
            page, pages = 1, 1
            while page <= min(pages, 8):
                data = c.get("https://career.habr.com/api/frontend/vacancies",
                             params={"q": q, "remote": "true", "sort": "date", "type": "all", "page": page}).json()
                pages = data["meta"]["totalPages"]
                page += 1
                for v in data["list"]:
                    sal = v.get("salary") or {}
                    currency = HABR_CURRENCY.get(sal.get("currency") or "")
                    url = "https://career.habr.com" + v["href"]
                    yield Job(
                        source="habr",
                        external_id=str(v["id"]),
                        title=v["title"].strip(),
                        company=(v.get("company") or {}).get("title", ""),
                        url=url,
                        apply_url=url,
                        location="Remote",
                        remote=True,
                        salary_min=num(sal.get("from")),
                        salary_max=num(sal.get("to")),
                        salary_currency=currency,
                        salary_period="month" if currency else None,
                        salary_text=sal.get("formatted") or "",
                        published_at=parse_dt((v.get("publishedDate") or {}).get("date")),
                    )


def habr_description(url: str) -> str:
    with client() as c:
        node = BeautifulSoup(c.get(url).text, "html.parser").select_one(".vacancy-description__text")
        return node.get_text("\n", strip=True) if node else ""


def _getmatch_location(reqs: list[dict], home: list[str]) -> str:
    parts = []
    for r in reqs:
        if r.get("exclude"):
            continue
        loc = r.get("location_id") or ""
        if loc == "_cu-world":
            loc = "Worldwide"
        elif any(h.lower() in loc for h in home):
            loc = f"{loc} (home)"
        parts.append(f"{loc} ({r.get('format')})")
    return "; ".join(parts)


def getmatch(home: list[str] = ()) -> Iterator[Job]:
    """`home`: location-id substrings (e.g. "georgia") where the candidate can work on-site/hybrid."""
    with client() as c:
        offset, total = 0, 1
        while offset < total:
            data = c.get("https://getmatch.ru/api/offers", params={"pa": "all", "offset": offset, "limit": 100}).json()
            total, offset = data["meta"]["total"], offset + 100
            for o in data.get("offers", []):
                location = _getmatch_location(o.get("location_requirements") or [], home)
                # Keep only offers open worldwide or in a home location; the rest are tied to other countries.
                if "Worldwide" not in location and "(home)" not in location:
                    location = location or "Russia"
                url = "https://getmatch.ru" + o["url"]
                yield Job(
                    source="getmatch",
                    external_id=str(o["id"]),
                    title=o["position"],
                    company=(o.get("company") or {}).get("name", ""),
                    url=url,
                    apply_url=url,
                    location=location,
                    remote="remote" in location,
                    description=html_to_text(o.get("description_html") or o.get("offer_description")),
                    salary_min=num(o.get("salary_display_from")),
                    salary_max=num(o.get("salary_display_to")),
                    salary_currency=o.get("salary_currency"),
                    salary_period="month" if o.get("salary_currency") else None,
                    published_at=parse_dt(o.get("published_at")),
                    tags=[s.get("title", "") for s in o.get("skills_objects") or [] if isinstance(s, dict)],
                )
