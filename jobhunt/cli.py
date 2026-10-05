from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from . import filters
from .db import DB
from .sources import ats, boards, linkedin, ru_boards, telegram

ROOT = Path(__file__).resolve().parent.parent
app = typer.Typer(no_args_is_help=True, help="Job search: fetch -> score -> tailor -> apply")
console = Console()


def load():
    cfg_path, profile_path = ROOT / "config.yaml", ROOT / "profile" / "master_profile.yaml"
    for path, example in [(cfg_path, "config.example.yaml"), (profile_path, "profile/profile.example.yaml")]:
        if not path.exists():
            raise typer.BadParameter(f"{path.relative_to(ROOT)} not found — copy {example} and fill it in")
    cfg = yaml.safe_load(cfg_path.read_text())
    profile = yaml.safe_load(profile_path.read_text())
    bad = [s for s in profile["skills"]["production"] + profile["skills"]["familiar"] if not isinstance(s, str)]
    if bad:  # an unquoted "a: b" in a YAML list becomes a dict
        raise typer.BadParameter(f"Quote these skills in master_profile.yaml: {bad}")
    return cfg, profile, DB(ROOT / "data" / "jobs.db")


_TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f",
                     "kh","ts","ch","sh","sch","","y","","e","yu","ya"]))


def slug(s: str, n: int = 40) -> str:
    s = "".join(_TRANSLIT.get(ch, ch) for ch in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:n]


@app.command()
def fetch(only: str = typer.Option(None, help="Comma-separated sources, e.g. remotive,ats")):
    """Pull jobs from all sources, pre-filter them and store new ones."""
    cfg, _, db = load()
    wanted = set(only.split(",")) if only else None
    disabled = set(cfg.get("disabled_sources", []))
    gens = {name: fn for name, fn in boards.ALL.items()
            if (not wanted or name in wanted) and name not in disabled and name not in boards.CONFIGURED}
    if (not wanted or "getmatch" in wanted) and "getmatch" not in disabled:
        gens["getmatch"] = lambda: boards.getmatch(cfg.get("getmatch", {}).get("home_locations", []))
    if (not wanted or "linkedin" in wanted) and "linkedin" not in disabled:
        li = cfg.get("linkedin", {})
        gens["linkedin"] = lambda: boards.linkedin(li.get("regions"), li.get("keywords"))
    if not wanted or "ats" in wanted:
        gens["ats"] = lambda: ats.fetch_companies(cfg["companies"])
    if not wanted or "telegram" in wanted:
        gens["telegram"] = lambda: telegram.telegram(cfg.get("telegram_channels", []))
    for name, gen in gens.items():
        new = passed = 0
        try:
            for job in gen():
                reason = filters.prefilter(job, cfg)
                if reason is None and not job.description:
                    if job.source == "habr":
                        job.description = ru_boards.habr_description(job.url)
                    elif job.source == "linkedin":
                        job.description = linkedin.linkedin_description(job.external_id)
                if db.insert(job, filters.monthly_usd(job, cfg["fx_to_usd"]), reason):
                    new += 1
                    passed += reason is None
        except Exception as e:  # one broken source must not stop the others
            console.print(f"[red]{name}: {e}")
        console.print(f"{name}: {new} new, {passed} passed pre-filter")


@app.command()
def score(limit: int = typer.Option(50, help="Max jobs to score in this run"),
          workers: int = typer.Option(4, help="Parallel Claude calls")):
    """Score pre-filtered jobs with Claude (eligibility, pay, fit)."""
    from . import llm
    cfg, profile, db = load()
    jobs = db.by_status("new", limit=limit)
    console.print(f"Scoring {len(jobs)} jobs...")
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(llm.score_job, job, profile, cfg): job for job in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                s = fut.result()
            except llm.Refused as e:
                db.set_status(job["uid"], "rejected", reject_reason=f"refused: {e}")
                continue
            except (llm.ClaudeError, subprocess.TimeoutExpired) as e:
                console.print(f"[red]{job['uid']}: {e}")
                continue
            fields = {"fit_score": s["fit_score"], "score_json": json.dumps(s, ensure_ascii=False)}
            if s["eligibility"] == "not_eligible":
                db.set_status(job["uid"], "rejected", reject_reason="llm_eligibility", **fields)
            elif s["est_monthly_usd"] and s["est_monthly_usd"] < cfg["search"]["min_monthly_usd"]:
                db.set_status(job["uid"], "rejected", reject_reason="llm_salary", **fields)
            else:
                db.save_score(job["uid"], s)
            console.print(f"  {s['fit_score']:>2}/10 {s['eligibility']:<12} ${s['est_monthly_usd']:>6}/mo  "
                          f"{job['company'][:20]:<20} {job['title'][:60]}")


@app.command("list")
def list_jobs(status: str = "scored", min_score: int = 0, limit: int = 40):
    """Show jobs by status, best first."""
    _, _, db = load()
    order = "fit_score desc" if status in ("scored", "tailored", "applied") else "published_at desc"
    t = Table(show_lines=False)
    for col in ("id", "score", "elig.", "$/mo", "company", "title", "location"):
        t.add_column(col)
    for j in db.by_status(status, order=order, limit=limit):
        s = json.loads(j["score_json"]) if j["score_json"] else {}
        if (j["fit_score"] or 0) < min_score:
            continue
        pay = s.get("est_monthly_usd") or j["monthly_usd_max"] or ""
        basis = "" if not s else ("" if s.get("salary_basis") == "published" else "~")
        t.add_row(j["uid"], str(j["fit_score"] or ""), s.get("eligibility", ""), f"{basis}{pay}",
                  j["company"][:22], j["title"][:50], (j["location"] or "")[:30])
    console.print(t)


@app.command()
def show(uid: str):
    """Show one job with its score breakdown."""
    _, _, db = load()
    j = db.get(uid)
    if not j:
        raise typer.BadParameter(f"no job {uid}")
    console.print(f"[bold]{j['title']}[/] — {j['company']}\n{j['url']}\nApply: {j['apply_url']}\n"
                  f"Location: {j['location']}\nSalary: {j['salary_text'] or '—'}\nStatus: {j['status']} {j['reject_reason'] or ''}")
    if j["score_json"]:
        console.print_json(j["score_json"])


@app.command()
def tailor(uids: list[str] = typer.Argument(None), top: int = typer.Option(0, help="Tailor the N best scored jobs")):
    """Generate a tailored PDF resume + cover letter for jobs."""
    from . import llm, render
    cfg, profile, db = load()
    rows = [db.get(u) for u in uids or []]
    if top:
        rows += db.conn.execute(
            """select * from jobs where status='scored' and fit_score >= ?
               and json_extract(score_json, '$.eligibility') in ('eligible', 'likely')
               order by fit_score desc limit ?""", (cfg["scoring"]["min_fit_score"], top)).fetchall()
    for job in filter(None, rows):
        console.print(f"Tailoring: {job['company']} — {job['title']}")
        try:
            result = llm.tailor(job, profile, cfg)
        except (llm.ClaudeError, llm.Refused, subprocess.TimeoutExpired) as e:
            console.print(f"[red]  {e}")
            continue
        out = ROOT / "out" / f"{date.today()}_{slug(job['company'], 20)}_{slug(job['title'])}"
        out.mkdir(parents=True, exist_ok=True)
        (out / "tailored.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        pdf = render.render_pdf(result, profile, out, f"{profile['name'].replace(' ', '_')}_{slug(job['company'], 20)}",
                                lang=job["lang"] or "en", target_location=job["target_location"])
        (out / "cover_letter.txt").write_text(result["cover_letter"])
        warnings = []
        if (pages := render.page_count(pdf)) and pages > 1:
            warnings.append(f"Резюме заняло {pages} страницы — сократи буллеты в tailored.json и перегенерируй.")
        if bad := llm.unsupported_numbers(result, profile, job["description"]):
            warnings.append(f"Числа, которых нет в профиле: {', '.join(bad)} — проверь, не выдумка ли.")
        score = json.loads(job["score_json"]) if job["score_json"] else {}
        (out / "job.md").write_text(
            f"# {job['title']} — {job['company']}\n\n"
            f"- Вакансия: {job['url']}\n- Отклик: {job['apply_url']}\n- Локация: {job['location']}\n"
            f"- Зарплата: {job['salary_text'] or '—'} (оценка: ${score.get('est_monthly_usd', '?')}/мес)\n"
            f"- Fit: {job['fit_score']}/10, {score.get('eligibility', '')}: {score.get('eligibility_reason', '')}\n\n"
            f"## Что подчёркнуто\n{result['tailoring_notes_ru']}\n\n"
            + (f"## ⚠️ Проверить\n" + "\n".join(f"- {w}" for w in warnings) + "\n\n" if warnings else "")
            + f"## Описание\n{job['description']}\n")
        db.set_status(job["uid"], "tailored", output_dir=str(out))
        console.print(f"  -> {out}")
        for w in warnings:
            console.print(f"  [yellow]! {w}")


@app.command()
def add(urls: list[str], location: str = typer.Option(None, help="Where you apply to work, e.g. 'Belgrade, Serbia'"),
        lang: str = typer.Option("en", help="Resume language: en | ru"),
        company: str = typer.Option(None, help="Company name (default: taken from the page)")):
    """Add jobs by URL (any site that renders text server-side) and score them."""
    from bs4 import BeautifulSoup
    from .models import Job
    from .sources import client
    cfg, profile, db = load()
    with client() as c:
        for url in urls:
            soup = BeautifulSoup(c.get(url).text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            h1 = soup.find("h1")
            title = h1.get_text(" ", strip=True) if h1 else (soup.title.string or url).strip()
            text = soup.get_text("\n", strip=True)
            start = text.find(title)
            job = Job(source="manual", external_id=url, title=title,
                      company=company or (soup.find("meta", property="og:site_name") or {}).get("content", "") or url.split("/")[2],
                      url=url, apply_url=url, location=location or "", description=text[max(start, 0):][:15000])
            if not db.insert(job, (None, None), None):
                console.print(f"[yellow]already in DB: {title}")
            db.set_fields(job.uid, target_location=location, lang=lang)
            console.print(f"added {job.uid}: {title}")
    score(limit=50, workers=4)


@app.command()
def mark(uid: str, status: str = typer.Argument(..., help="applied | skipped | interview | offer | rejected")):
    """Record what happened with a job."""
    _, _, db = load()
    db.set_status(uid, status)


@app.command()
def stats():
    """Counts by status and rejection reason."""
    _, _, db = load()
    for r in db.counts():
        console.print(f"{r['status']:<10} {r['reason']:<18} {r['n']}")


@app.command()
def run(score_limit: int = 50, top: int = 5):
    """Daily pipeline: fetch, score, tailor the best N."""
    fetch(only=None)
    score(limit=score_limit, workers=4)
    tailor(uids=None, top=top)


@app.command()
def digest(days: int = 1, min_score: int = 6):
    """Write a Markdown digest of jobs scored in the last N days that are worth applying to."""
    cfg, _, db = load()
    rows = db.conn.execute(
        """select * from jobs where status in ('scored', 'tailored')
           and fetched_at >= datetime('now', ?) and fit_score >= ?
           and json_extract(score_json, '$.eligibility') in ('eligible', 'likely')
           order by fit_score desc""", (f"-{days} days", min_score)).fetchall()
    lines = [f"# Вакансии за {date.today()}", "",
             f"Новых подходящих: **{len(rows)}** (fit ≥ {min_score}, eligibility: eligible/likely)", ""]
    for j in rows:
        s = json.loads(j["score_json"])
        ready = f" — резюме готово: `{j['output_dir']}`" if j["output_dir"] else ""
        lines += [f"## {int(j['fit_score'])}/10 · {j['title']} — {j['company']}",
                  f"- {j['location']} · ~${s.get('est_monthly_usd')}/мес ({s.get('salary_basis')})",
                  f"- {s.get('summary_ru')}",
                  f"- {j['url']}{ready}",
                  f"- id: `{j['uid']}`", ""]
    path = ROOT / "out" / f"digest-{date.today()}.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(lines))
    console.print(f"{len(rows)} jobs -> {path}")
    return len(rows), path
