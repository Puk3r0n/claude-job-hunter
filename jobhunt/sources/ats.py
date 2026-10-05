"""Company career boards on public ATS APIs (Greenhouse, Lever, Ashby)."""
from __future__ import annotations

from collections.abc import Iterator

import httpx

from ..models import Job
from . import client, html_to_text, num, parse_dt


def greenhouse(slug: str, c: httpx.Client) -> Iterator[Job]:
    r = c.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
              params={"content": "true", "pay_transparency": "true"})
    if r.status_code != 200:
        return
    for j in r.json().get("jobs", []):
        pay = (j.get("pay_input_ranges") or [{}])[0]
        loc = (j.get("location") or {}).get("name", "")
        yield Job(
            source=f"greenhouse:{slug}",
            external_id=str(j["id"]),
            title=j["title"],
            company=j.get("company_name") or slug,
            url=j["absolute_url"],
            apply_url=j["absolute_url"],
            location=loc,
            remote="remote" in loc.lower(),
            description=html_to_text(j.get("content")),
            salary_min=(num(pay.get("min_cents")) or 0) / 100 or None,
            salary_max=(num(pay.get("max_cents")) or 0) / 100 or None,
            salary_currency=pay.get("currency_type"),
            salary_period="year" if pay else None,
            published_at=parse_dt(j.get("first_published") or j.get("updated_at")),
        )


def lever(slug: str, c: httpx.Client) -> Iterator[Job]:
    r = c.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    if r.status_code != 200:
        return
    intervals = {"per-year-salary": "year", "per-month-salary": "month", "per-hour-wage": "hour"}
    for j in r.json():
        cats = j.get("categories") or {}
        sal = j.get("salaryRange") or {}
        desc = "\n".join(filter(None, [
            j.get("descriptionPlain"),
            *[f"{l.get('text')}\n{html_to_text(l.get('content'))}" for l in j.get("lists") or []],
            j.get("additionalPlain"),
        ]))
        yield Job(
            source=f"lever:{slug}",
            external_id=j["id"],
            title=j["text"],
            company=slug,
            url=j["hostedUrl"],
            apply_url=j.get("applyUrl") or j["hostedUrl"],
            location=", ".join(cats.get("allLocations") or [cats.get("location") or ""]),
            remote=(j.get("workplaceType") == "remote"),
            description=desc,
            salary_min=num(sal.get("min")),
            salary_max=num(sal.get("max")),
            salary_currency=sal.get("currency"),
            salary_period=intervals.get(sal.get("interval") or ""),
            published_at=parse_dt(j.get("createdAt")),
        )


def ashby(slug: str, c: httpx.Client) -> Iterator[Job]:
    r = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
    if r.status_code != 200:
        return
    for j in r.json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        comp = j.get("compensation") or {}
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        yield Job(
            source=f"ashby:{slug}",
            external_id=j["id"],
            title=j["title"],
            company=slug,
            url=j["jobUrl"],
            apply_url=j.get("applyUrl") or j["jobUrl"],
            location=", ".join(filter(None, locs)),
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            description=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml")),
            salary_text=comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary") or "",
            published_at=parse_dt(j.get("publishedAt")),
        )


def fetch_companies(companies: dict[str, list[str]]) -> Iterator[Job]:
    fns = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
    with client() as c:
        for kind, slugs in companies.items():
            for slug in slugs:
                try:
                    yield from fns[kind](slug, c)
                except (httpx.HTTPError, ValueError) as e:
                    print(f"  ! {kind}:{slug}: {e}")
