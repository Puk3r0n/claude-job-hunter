"""Render a tailored resume (LLM JSON + master profile) to PDF via pdflatex."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import jinja2

TEMPLATES = Path(__file__).parent / "templates"

_LATEX_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "→": r"$\rightarrow$", "—": "---", "–": "--",
}
_LATEX_RE = re.compile("|".join(re.escape(k) for k in _LATEX_ESCAPES))


def tex(s: str) -> str:
    return _LATEX_RE.sub(lambda m: _LATEX_ESCAPES[m.group()], s)


def _env() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATES),
        variable_start_string="<<", variable_end_string=">>",
        block_start_string="<%", block_end_string="%>",
        trim_blocks=True, lstrip_blocks=True,
    )


LABELS = {
    "en": {"summary": "Professional Summary", "skills": "Key Skills", "familiar": "Familiar with",
           "experience": "Experience", "education": "Education \\& Certificates", "languages": "Languages",
           "stack": "Stack", "relocate": "open to relocation to"},
    "ru": {"summary": "О себе", "skills": "Ключевые навыки", "familiar": "Знаком на базовом уровне",
           "experience": "Опыт работы", "education": "Образование и курсы", "languages": "Языки",
           "stack": "Стек", "relocate": "релокация в"},
}
RU_MONTHS = {"January": "январь", "February": "февраль", "March": "март", "April": "апрель", "May": "май",
             "June": "июнь", "July": "июль", "August": "август", "September": "сентябрь", "October": "октябрь",
             "November": "ноябрь", "December": "декабрь", "Present": "наст. время"}


def _ru_dates(s: str) -> str:
    return re.sub(r"[A-Z][a-z]+", lambda m: RU_MONTHS.get(m.group(), m.group()), s)


def build_context(result: dict, profile: dict, lang: str = "en", target_location: str | None = None) -> dict:
    ru = profile.get("ru", {}) if lang == "ru" else {}
    L = LABELS[lang]
    by_company = {e["company"]: e for e in profile["experience"]}
    c = profile["contacts"]
    contacts = [c["email"], f"Telegram {c['telegram']}", c.get("linkedin"), c.get("github")]
    dates = _ru_dates if lang == "ru" else (lambda s: s)
    loc = (lambda s: ru.get("locations", {}).get(s, s))
    location = ru.get("location", profile["location"])
    if target_location:
        where = f"{tex(location)} --- {L['relocate']} {tex(loc(target_location))}"
    else:
        where = f"{tex(location)} --- {tex(ru.get('work_setup', profile['work_setup']))}"
    return {
        "L": L,
        "lang": lang,
        "babel": "english,russian" if lang == "ru" else "english",
        "name": tex(ru.get("name", profile["name"])),
        "headline": tex(result["headline"]),
        "contacts": " $\\cdot$ ".join(tex(x) for x in contacts if x) + f"\\\\ {where}",
        "summary": tex(result["summary"]),
        "skill_groups": [{"name": tex(g["name"]), "skills": tex(", ".join(g["items"]))}
                         for g in result["skill_groups"] if g["items"]],
        "familiar_with": tex(", ".join(result["familiar_with"])),
        "experience": [{
            "company": tex(e["company"]),
            "title": tex(e["title"]),
            "dates": tex(dates(by_company[e["company"]]["dates"])),
            "location": tex(loc(by_company[e["company"]]["location"])),
            "stack": tex(", ".join(by_company[e["company"]]["stack"])),
            "bullets": [tex(b) for b in e["bullets"]],
        } for e in result["experience"]],
        "education": [tex(x) for x in ru.get("education", profile["education"])],
        "languages": tex(" · ".join(ru.get("languages", profile["languages"]))).replace("·", r"$\cdot$"),
    }


def render_pdf(result: dict, profile: dict, out_dir: Path, basename: str,
               lang: str = "en", target_location: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{basename}.tex"
    tex_path.write_text(_env().get_template("resume.tex.j2").render(**build_context(result, profile, lang, target_location)))
    if not shutil.which("pdflatex"):
        raise RuntimeError("pdflatex not found; the .tex file was written to " + str(tex_path))
    proc = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                          cwd=out_dir, capture_output=True, text=True, errors="replace")
    pdf = out_dir / f"{basename}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"pdflatex failed, see {out_dir / (basename + '.log')}")
    for ext in (".aux", ".log", ".out"):
        (out_dir / f"{basename}{ext}").unlink(missing_ok=True)
    return pdf


def page_count(pdf: Path) -> int:
    from pypdf import PdfReader
    return len(PdfReader(pdf).pages)
