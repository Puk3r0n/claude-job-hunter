from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .models import Job

SCHEMA = """
create table if not exists jobs (
    uid text primary key,
    source text, external_id text, dedup_key text,
    title text, company text, url text, apply_url text, location text,
    description text, salary_text text,
    monthly_usd_min real, monthly_usd_max real,
    published_at text, fetched_at text default (datetime('now')),
    status text default 'new',      -- new | rejected | scored | tailored | applied | skipped
    reject_reason text,
    fit_score real, score_json text,
    output_dir text,
    target_location text,   -- where the candidate applies to work, e.g. 'Belgrade, Serbia (relocation)'
    lang text default 'en'  -- resume language: en | ru
);
create index if not exists jobs_dedup on jobs(dedup_key);
create index if not exists jobs_status on jobs(status);
"""


class DB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("pragma table_info(jobs)")}
        for col, ddl in [("target_location", "text"), ("lang", "text default 'en'")]:
            if col not in cols:
                self.conn.execute(f"alter table jobs add column {col} {ddl}")

    def insert(self, job: Job, monthly: tuple, reject_reason: str | None) -> bool:
        """Insert a job unless the same posting (or same company+title) is already stored."""
        if self.conn.execute("select 1 from jobs where uid=? or dedup_key=?", (job.uid, job.dedup_key)).fetchone():
            return False
        d = asdict(job)
        salary = job.salary_text or (
            f"{job.salary_min or ''}-{job.salary_max or ''} {job.salary_currency or ''}/{job.salary_period or ''}"
            if job.salary_min or job.salary_max else "")
        self.conn.execute(
            """insert into jobs (uid, source, external_id, dedup_key, title, company, url, apply_url, location,
               description, salary_text, monthly_usd_min, monthly_usd_max, published_at, status, reject_reason)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (job.uid, d["source"], d["external_id"], job.dedup_key, d["title"], d["company"], d["url"],
             d["apply_url"], d["location"], d["description"], salary, monthly[0], monthly[1],
             job.published_at.isoformat() if job.published_at else None,
             "rejected" if reject_reason else "new", reject_reason),
        )
        self.conn.commit()
        return True

    def set_fields(self, uid: str, **fields) -> None:
        sets = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"update jobs set {sets} where uid=?", (*fields.values(), uid))
        self.conn.commit()

    def get(self, uid: str) -> sqlite3.Row | None:
        return self.conn.execute("select * from jobs where uid=?", (uid,)).fetchone()

    def by_status(self, status: str, order: str = "published_at desc", limit: int = 1000) -> list[sqlite3.Row]:
        return self.conn.execute(f"select * from jobs where status=? order by {order} limit ?", (status, limit)).fetchall()

    def save_score(self, uid: str, score: dict) -> None:
        self.conn.execute("update jobs set status='scored', fit_score=?, score_json=? where uid=?",
                          (score["fit_score"], json.dumps(score, ensure_ascii=False), uid))
        self.conn.commit()

    def set_status(self, uid: str, status: str, **fields) -> None:
        sets = ", ".join(["status=?"] + [f"{k}=?" for k in fields])
        self.conn.execute(f"update jobs set {sets} where uid=?", (status, *fields.values(), uid))
        self.conn.commit()

    def counts(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "select status, coalesce(reject_reason,'') reason, count(*) n from jobs group by 1,2 order by 3 desc"
        ).fetchall()
