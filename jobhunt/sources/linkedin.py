"""LinkedIn public (guest) job search — no login, low request volume."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator

from bs4 import BeautifulSoup

from ..models import Job
from . import client, parse_dt

SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
KEYWORDS = ["data engineer", "data quality engineer", "analytics engineer", "data analyst",
            "data qa engineer", "etl tester", "data validation engineer", "data governance"]
# Default regions; override with config `linkedin.regions` ([{label, location, geoId, remote_only}]).
REGIONS = [
    {"label": "EMEA remote", "location": "EMEA", "geoId": "91000007", "remote_only": True},
    {"label": "Europe remote", "location": "Europe", "geoId": "100506914", "remote_only": True},
]
PAGES = 2  # 10 results per page


def linkedin(regions: list[dict] | None = None, keywords: list[str] | None = None) -> Iterator[Job]:
    """Guest job search. Note: automated access may violate LinkedIn's terms — keep volumes low."""
    with client() as c:
        for kw in keywords or KEYWORDS:
            for region in regions or REGIONS:
                label = region["label"]
                params = {"location": region["location"], "geoId": region["geoId"]}
                if region.get("remote_only"):
                    params["f_WT"] = "2"
                for page in range(PAGES):
                    r = c.get(SEARCH, params={"keywords": kw, "start": page * 10, "f_TPR": "r2592000", **params})
                    if r.status_code == 429:
                        time.sleep(10)
                        continue
                    cards = BeautifulSoup(r.text, "html.parser").select("li")
                    if not cards:
                        break
                    for card in cards:
                        link = card.select_one("a.base-card__full-link")
                        if not link:
                            continue
                        url = link["href"].split("?")[0]
                        job_id = re.search(r"(\d+)/?$", url)
                        text = lambda sel: (card.select_one(sel).get_text(strip=True) if card.select_one(sel) else "")
                        location = text(".job-search-card__location")
                        if params.get("f_WT") == "2":
                            location = f"{location} (remote, {label})"
                        when = card.select_one("time")
                        yield Job(
                            source="linkedin",
                            external_id=job_id.group(1) if job_id else url,
                            title=text(".base-search-card__title"),
                            company=text(".base-search-card__subtitle"),
                            url=url,
                            apply_url=url,
                            location=location,
                            remote=params.get("f_WT") == "2",
                            salary_text=text(".job-search-card__salary-info"),
                            published_at=parse_dt(when.get("datetime")) if when else None,
                        )
                    time.sleep(1.5)


def linkedin_description(job_id: str) -> str:
    with client() as c:
        r = c.get(DETAIL.format(job_id))
        node = BeautifulSoup(r.text, "html.parser").select_one(".show-more-less-html__markup")
        return node.get_text("\n", strip=True) if node else ""
