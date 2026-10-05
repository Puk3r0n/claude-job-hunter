---
name: job-hunt
description: Find, score and apply to jobs with the claude-job-hunter CLI — fetch vacancies from job boards, ATS boards and Telegram channels, score them against the user's master profile, generate a tailored one-page PDF resume and cover letter per job, and fill application forms in the user's browser (Teamtailor, Ashby, Workable, Getmatch, Habr Career, Yandex, LinkedIn Easy Apply) with the user's confirmation. Use when the user asks to find jobs, apply to vacancies, tailor a resume to a job, update job-site profiles, or check on applications.
---

# Job hunt

The repo contains the `jobhunt` CLI (Python). Run every command from the repo root.

## Setup check (first run)

1. `config.yaml` and `profile/master_profile.yaml` must exist. If not, copy the `*.example.yaml` files and
   build the master profile **with the user** from their real resumes: every fact, number and skill on a
   generated resume comes from this file, so ask about anything ambiguous (dates, metrics, which tools were
   used in production vs. only familiar). Never invent facts to fill gaps.
2. `pip install -r requirements.txt`; `pdflatex` (TeX Live / MacTeX) for PDFs.
3. LLM calls go through the Claude Code CLI (`claude -p`), so no API key is needed.

## Pipeline

```bash
python -m jobhunt fetch              # all sources -> rule pre-filter -> SQLite (data/jobs.db)
python -m jobhunt score --limit 50   # Claude: eligibility, monthly pay, fit 0-10
python -m jobhunt list --min-score 7
python -m jobhunt show <id>
python -m jobhunt tailor <id> [<id>...]   # or --top N; writes out/<date>_<company>_<role>/
python -m jobhunt add <url> [--location "Belgrade, Serbia"] [--lang ru]   # any job page by URL
python -m jobhunt mark <id> applied|skipped|rejected|interview|offer
python -m jobhunt digest             # markdown summary of today's good matches
```

Each output folder has the PDF, `cover_letter.txt`, `tailored.json` and `job.md` (links, what was emphasized,
gaps to prepare for, and a "check" section if a number appears that is not in the profile).

## Choosing what to apply to

- Present matches as a short table: fit, role, company, location, estimated $/month. Recommend a subset.
- Before applying, re-check the real posting: aggregators (RVC, freehire, Built In) often show closed jobs or
  wrong locations. If the posting turns out to be on-site elsewhere or closed, skip it and tell the user.
- Only apply after the user explicitly says which jobs to apply to.

## Applying in the browser

Use the Chrome browser tools. General rules:

- Prefer the company's own ATS page over aggregators; LinkedIn "Apply" usually redirects to it (read the
  `url=` parameter of the Apply link).
- The user must log in themselves (Getmatch, Habr, LinkedIn, Yandex ID). Never type passwords; never create
  accounts for the user.
- Answer screening questions only from the master profile. If a question asks for a fact that is not in the
  profile (notice period, phone, salary, experience with a tool), stop and ask the user, then add the answer to
  the profile so it is reused. Be honest about gaps rather than overstating experience.
- Tick only consents required to submit; leave marketing/newsletter/"future roles" consents unticked.
- Decline non-essential cookies first — cookie banners silently swallow clicks and keystrokes.
- After every submit, verify the confirmation text on the page, then `jobhunt mark <id> applied`.

### Platform notes

- **Teamtailor** (`<company>.teamtailor.com/jobs/<id>/applications/new`): radio/select questions, CV upload,
  cover-letter textarea. Some companies require email verification after submit — tell the user to click
  the link in their inbox.
- **Ashby** (`jobs.ashbyhq.com/<company>/<id>/application`): upload the resume *first* — the form re-renders
  after upload and can clear typed name/email. Verify field values via `input[name=_systemfield_name]` before
  submitting. Location fields are comboboxes: type, then click the suggestion (try the country name if the
  city is missing). Text fields typed into before re-render may need select-all + retype.
- **Workable** (`apply.workable.com/<company>/j/<id>/`): check for "This job is no longer available".
- **Getmatch**: one-time profile created from the uploaded PDF; afterwards the resume comes from the profile.
  The salary field defaults to the profile value — switch currency and retype. The first click on "Apply" may
  not open the modal; click again.
- **Habr Career**: "Откликнуться" submits immediately with the Habr profile (no form). Afterwards a cover
  letter can be added via "Дополнить отклик". Keep the Habr profile up to date before applying.
- **Yandex Jobs**: the form is an iframe (forms.yandex.ru) with fixed height — after a long cover letter the
  consent checkbox and submit button move below the iframe edge; scroll over the textarea to scroll the iframe.
  Resume is a profile-level file: remove the old file and upload the job-specific PDF each time.
- **LinkedIn Easy Apply**: mobile phone is required. The file input is created on click — to upload without
  the native file picker, override `HTMLInputElement.prototype.click` for `type=file` inputs to keep the
  element in the DOM, click "Upload resume", then use the file-upload tool on that input. Untick "Follow
  company". Keep volume low; LinkedIn restricts automated activity.
- Hidden or dynamically created file inputs on other sites: same `HTMLInputElement.prototype.click` trick.

## Profiles on job sites

When asked to update Habr / LinkedIn / other profiles, use only master-profile facts, show the user what will
change, keep network notifications off on LinkedIn edits, and do not delete existing entries without asking.

## Scheduling

`daily.sh` runs fetch -> score -> tailor --top 5 -> digest and shows a desktop notification. Install with
`scheduling/com.jobhunt.daily.plist.template` (macOS launchd) or `scheduling/crontab.example` (Linux).
Set `JOBHUNT_PYTHON` / `JOBHUNT_EXTRA_PATH` if `python3` or `pdflatex` are not on the default PATH.
