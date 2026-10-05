from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    apply_url: str = ""
    location: str = ""
    remote: bool | None = None
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None  # year | month | hour
    salary_text: str = ""
    published_at: datetime | None = None
    tags: list[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        return hashlib.sha1(f"{self.source}:{self.external_id}".encode()).hexdigest()[:12]

    @property
    def dedup_key(self) -> str:
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        return f"{norm(self.company)}|{norm(self.title)}"
