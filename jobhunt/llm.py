"""Claude calls via the Claude Code CLI in headless mode (uses the Claude Code subscription, no API key)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import yaml


class Refused(Exception):
    pass


class ClaudeError(Exception):
    pass


def _call(model: str, effort: str, system: str, user: str, schema: dict, timeout: int = 600) -> dict:
    if not shutil.which("claude"):
        raise ClaudeError("Claude Code CLI not found in PATH")
    cmd = [
        "claude", "-p",
        "--model", model,
        "--effort", effort,
        "--system-prompt", system,          # replaces Claude Code's own prompt: keeps each call ~1-5k tokens
        "--json-schema", json.dumps(schema),
        "--output-format", "json",
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--disable-slash-commands",
        "--no-session-persistence",
    ]
    proc = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=timeout)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeError((proc.stderr or proc.stdout)[:500])
    if out.get("is_error") or out.get("subtype") != "success":
        raise ClaudeError(str(out.get("result") or out)[:500])
    if out.get("stop_reason") == "refusal":
        raise Refused(str(out.get("result"))[:300])
    if not isinstance(out.get("structured_output"), dict):
        raise ClaudeError("no structured_output in response")
    return out["structured_output"]


def _profile_text(profile: dict) -> str:
    return yaml.safe_dump(profile, allow_unicode=True, sort_keys=False)


def _job_text(job) -> str:
    salary = job["salary_text"] or "not published"
    text = (f"Title: {job['title']}\nCompany: {job['company']}\nLocation: {job['location'] or 'not specified'}\n"
            f"Salary: {salary}\nURL: {job['url']}\n")
    if job["target_location"]:
        text += (f"Candidate applies for: {job['target_location']}. The candidate is willing to relocate there, "
                 f"so treat this office as an acceptable location.\n")
    if job["lang"] == "ru":
        text += ("Output language: write the summary, skill group names, bullets and cover letter in Russian "
                 "(keep technology names in English). Address the cover letter to the hiring team in Russian, "
                 "and avoid gendered verb forms about the candidate (use present tense or nouns).\n")
    return text + f"\nDescription:\n{job['description'][:30000]}"


# ---------------------------------------------------------------- scoring

SCORE_SYSTEM = """You screen job postings for one specific candidate. The candidate's profile (YAML) follows.

Judge three things:
1. Eligibility. Use the `eligibility` section of the profile: where the candidate lives, their citizenship, legal \
entity and the arrangements they can and cannot work under. A posting that requires residence or work authorization \
the candidate does not have is not_eligible. Apply every rule in `eligibility.rules`. If the posting excludes the \
candidate's citizenship or country, flag it.
2. Pay. The floor is {min_usd} USD per month gross. If the salary is published, convert it. If not, estimate a \
realistic monthly USD figure for this role, seniority and company for a contractor in the candidate's region.
3. Fit. 10 = the candidate's experience covers nearly all core requirements; 7 = solid match with minor gaps; 4 = major gaps \
(e.g. a core tool they never used, or far more years required); 0 = different profession. The candidate has \
{years} years of experience.

Write `summary_ru` in {ui_language}, one or two sentences, for the candidate.

<profile>
{profile}
</profile>"""


def score_schema(profile: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "fit_score": {"type": "integer", "description": "0-10"},
            "eligibility": {"type": "string", "enum": ["eligible", "likely", "unclear", "not_eligible"]},
            "eligibility_reason": {"type": "string"},
            "est_monthly_usd": {"type": "integer", "description": "Monthly gross USD; published or estimated"},
            "salary_basis": {"type": "string", "enum": ["published", "estimated"]},
            "seniority_match": {"type": "string", "enum": ["under", "match", "over"]},
            "best_headline": {"type": "string", "enum": profile["headline_options"]},
            "matched": {"type": "array", "items": {"type": "string"}},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "summary_ru": {"type": "string"},
        },
        "required": ["fit_score", "eligibility", "eligibility_reason", "est_monthly_usd", "salary_basis",
                     "seniority_match", "best_headline", "matched", "gaps", "summary_ru"],
        "additionalProperties": False,
    }


def score_job(job, profile: dict, cfg: dict) -> dict:
    system = SCORE_SYSTEM.format(min_usd=cfg["search"]["min_monthly_usd"], profile=_profile_text(profile),
                                 years=profile.get("years_of_experience", "several"),
                                 ui_language=cfg.get("ui_language", "English"))
    sc = cfg["scoring"]
    return _call(sc["model"], sc["effort"], system, _job_text(job), score_schema(profile))


# ---------------------------------------------------------------- tailoring

TAILOR_SYSTEM = """You tailor a one-page resume and a cover letter for one candidate to one job posting.

Hard rules — the candidate will be interviewed on everything you write:
- Use only facts from the profile below. Rephrase, merge, reorder and select facts to match the posting, but never \
add a technology, metric, number, team size, responsibility or achievement that is not in the profile.
- Skills come only from `skills.production`; `skills.familiar` items may appear only in `familiar_with`.
- Mirror the posting's vocabulary where it truthfully describes their work, so ATS keyword matching works.
- Lead with the facts most relevant to this posting. Put the results listed in `highlights` early when relevant.
- Most recent role: 5-7 bullets; older roles: 2-3 bullets. Include roles marked `optional: true` only when the \
posting makes them relevant.
- Bullets start with a strong past/present-tense verb, one line each where possible (max ~25 words).
- Summary: 3 sentences, no clichés ("passionate", "results-driven"), and do not define the candidate by an employer's industry.
- Cover letter: English, 120-180 words, plain and specific: why this company/role, two concrete matching \
achievements, availability ({availability}). No flattery, no placeholders, sign with the candidate's name.
- The candidate's English level is {english}; match the cover letter's language to that level.

<profile>
{profile}
</profile>"""


def tailor_schema(profile: dict) -> dict:
    exp = profile["experience"]
    return {
        "type": "object",
        "properties": {
            "headline": {"type": "string", "enum": profile["headline_options"]},
            "summary": {"type": "string"},
            "skill_groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "items": {"type": "array", "items": {"type": "string", "enum": profile["skills"]["production"]}},
                    },
                    "required": ["name", "items"],
                    "additionalProperties": False,
                },
            },
            "familiar_with": {"type": "array", "items": {"type": "string", "enum": profile["skills"]["familiar"]}},
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string", "enum": [e["company"] for e in exp]},
                        "title": {"type": "string", "enum": sorted({t for e in exp for t in e["title_options"]})},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["company", "title", "bullets"],
                    "additionalProperties": False,
                },
            },
            "cover_letter": {"type": "string"},
            "tailoring_notes_ru": {"type": "string", "description": "What was emphasized and which gaps remain, in Russian"},
        },
        "required": ["headline", "summary", "skill_groups", "familiar_with", "experience", "cover_letter",
                     "tailoring_notes_ru"],
        "additionalProperties": False,
    }


def tailor(job, profile: dict, cfg: dict) -> dict:
    system = TAILOR_SYSTEM.format(profile=_profile_text(profile), availability=profile.get("work_setup", ""),
                                  english=profile.get("english_level", "not specified"))
    tc = cfg["tailoring"]
    return _call(tc["model"], tc["effort"], system, _job_text(job), tailor_schema(profile))


def unsupported_numbers(result: dict, profile: dict, job_description: str = "") -> list[str]:
    """Numbers in generated text that appear neither in the profile nor in the posting — a guard against invented metrics."""
    known = set(re.findall(r"\d+", _profile_text(profile) + job_description))
    text = " ".join([result["summary"], result["cover_letter"], *[b for e in result["experience"] for b in e["bullets"]]])
    return sorted({n for n in re.findall(r"\d+", text) if n not in known})
