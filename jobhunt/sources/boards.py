"""Remote job boards with public JSON APIs."""
from __future__ import annotations

from collections.abc import Iterator

from ..models import Job
from . import client, html_to_text, num, parse_dt

QUERIES = ["data engineer", "data quality", "analytics engineer", "data analyst", "data qa", "etl test"]


def remotive() -> Iterator[Job]:
    with client() as c:
        for q in QUERIES:
            for j in c.get("https://remotive.com/api/remote-jobs", params={"search": q}).json().get("jobs", []):
                yield Job(
                    source="remotive",
                    external_id=str(j["id"]),
                    title=j["title"],
                    company=j["company_name"].strip(),
                    url=j["url"],
                    apply_url=j["url"],
                    location=j.get("candidate_required_location") or "",
                    remote=True,
                    description=html_to_text(j.get("description")),
                    salary_text=j.get("salary") or "",
                    published_at=parse_dt(j.get("publication_date")),
                    tags=list(j.get("tags") or []),
                )


def remoteok() -> Iterator[Job]:
    with client() as c:
        for tag in ["data", "data-engineer", "analytics"]:
            items = c.get("https://remoteok.com/api", params={"tag": tag}).json()
            for j in items[1:]:  # first element is the legal notice
                yield Job(
                    source="remoteok",
                    external_id=str(j["id"]),
                    title=j.get("position", ""),
                    company=j.get("company", ""),
                    url=j.get("url", ""),
                    apply_url=j.get("apply_url") or j.get("url", ""),
                    location=j.get("location") or "",
                    remote=True,
                    description=html_to_text(j.get("description")),
                    salary_min=num(j.get("salary_min")),
                    salary_max=num(j.get("salary_max")),
                    salary_currency="USD" if num(j.get("salary_min")) else None,
                    salary_period="year" if num(j.get("salary_min")) else None,
                    published_at=parse_dt(j.get("date")),
                    tags=list(j.get("tags") or []),
                )


def himalayas() -> Iterator[Job]:
    period = {"annual": "year", "monthly": "month", "hourly": "hour"}
    with client() as c:
        for q in QUERIES:
            for page in range(1, 4):
                data = c.get("https://himalayas.app/jobs/api/search", params={"q": q, "page": page}).json()
                jobs = data.get("jobs", [])
                if not jobs:
                    break
                for j in jobs:
                    restrictions = j.get("locationRestrictions") or []
                    yield Job(
                        source="himalayas",
                        external_id=j["guid"],
                        title=j["title"],
                        company=j.get("companyName", ""),
                        url=j["guid"],
                        apply_url=j.get("applicationLink") or j["guid"],
                        location=", ".join(restrictions) if restrictions else "Worldwide",
                        remote=True,
                        description=html_to_text(j.get("description")),
                        salary_min=num(j.get("minSalary")),
                        salary_max=num(j.get("maxSalary")),
                        salary_currency=j.get("currency") or None,
                        salary_period=period.get(j.get("salaryPeriod") or "", None),
                        published_at=parse_dt(j.get("pubDate")),
                        tags=list(j.get("categories") or []),
                    )


def jobicy() -> Iterator[Job]:
    with client() as c:
        for tag in ["data engineer", "data analyst", "analytics engineer", "data quality"]:
            data = c.get("https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": tag}).json()
            for j in data.get("jobs", []):
                yield Job(
                    source="jobicy",
                    external_id=str(j["id"]),
                    title=j.get("jobTitle", ""),
                    company=j.get("companyName", ""),
                    url=j.get("url", ""),
                    apply_url=j.get("url", ""),
                    location=j.get("jobGeo") or "",
                    remote=True,
                    description=html_to_text(j.get("jobDescription")),
                    salary_min=num(j.get("annualSalaryMin")),
                    salary_max=num(j.get("annualSalaryMax")),
                    salary_currency=j.get("salaryCurrency") or None,
                    salary_period="year" if num(j.get("annualSalaryMin")) else None,
                    published_at=parse_dt(j.get("pubDate")),
                )


from .linkedin import linkedin  # noqa: E402
from .ru_boards import getmatch, habr  # noqa: E402

ALL = {"remotive": remotive, "remoteok": remoteok, "himalayas": himalayas, "jobicy": jobicy,
       "habr": habr, "getmatch": getmatch, "linkedin": linkedin}
# Sources that read their parameters from config.yaml (see cli.fetch).
CONFIGURED = {"getmatch", "linkedin"}
