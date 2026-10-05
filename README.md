# claude-job-hunter

Job search on autopilot with Claude Code: collect vacancies from a dozen sources, score each one against
your real experience, generate a tailored one-page resume and cover letter per job, and let Claude fill
the application forms in your browser — with you confirming what gets sent.

```
fetch  → 10+ sources → rule pre-filter (title, freshness, location, currency, salary) → SQLite
score  → Claude: can you actually be hired there (location, work authorization), monthly pay, fit 0–10
tailor → Claude picks facts from your master profile → one-page PDF (LaTeX) + cover letter
apply  → Claude Code skill drives the browser: Teamtailor, Ashby, Workable, Getmatch, Habr, LinkedIn Easy Apply…
```

## Why

- **No invented experience.** Every resume is assembled from `profile/master_profile.yaml`. Skills are
  constrained to your lists by a JSON schema, "familiar" tools never appear as production experience, and any
  number that is not in your profile or the posting is flagged for review.
- **Eligibility first.** Most "remote" jobs are tied to one country. Scoring checks the posting against your
  residence, citizenship and legal entity, so you only see jobs you can actually get.
- **No API key.** LLM calls go through the Claude Code CLI (`claude -p`) on your Claude subscription, with
  structured JSON output and a minimal system prompt (~1–5k tokens per call).

## Sources

| Source | How |
|---|---|
| Remotive, RemoteOK, Himalayas, Jobicy | public JSON APIs |
| Company boards on Greenhouse, Lever, Ashby | public ATS APIs — list your companies in `config.yaml` |
| Getmatch, Habr Career | Russian-language boards; remote / foreign-currency offers only |
| Telegram channels | public `t.me/s/<channel>` previews, no account needed |
| LinkedIn | guest search — **disabled by default**, see below |
| Any job page | `python -m jobhunt add <url>` |

## Setup

```bash
git clone https://github.com/<you>/claude-job-hunter && cd claude-job-hunter
pip install -r requirements.txt          # plus pdflatex: MacTeX / TeX Live
cp config.example.yaml config.yaml
cp profile/profile.example.yaml profile/master_profile.yaml   # fill with YOUR facts
```

Requires [Claude Code](https://claude.com/claude-code) (`claude` on PATH). Your config, profile, generated
resumes and the job database are git-ignored.

The easiest way to build the master profile: open Claude Code in the repo, attach your current resumes and
ask it to fill `profile/master_profile.yaml` — the bundled skill tells it to ask about anything ambiguous
instead of guessing.

## Usage

```bash
python -m jobhunt fetch                 # collect + pre-filter
python -m jobhunt score --limit 50      # Claude scoring
python -m jobhunt list --min-score 7
python -m jobhunt tailor <id>           # or --top 5
python -m jobhunt mark <id> applied
python -m jobhunt digest                # markdown summary of today's matches
python -m jobhunt run                   # fetch → score → tailor --top 5
```

Each `out/<date>_<company>_<role>/` folder contains the PDF, `cover_letter.txt`, `tailored.json` (edit and
re-render if needed) and `job.md` with links, what was emphasized and the gaps to prepare for.

### Applying with Claude Code

The repo ships a Claude Code skill in `.claude/skills/job-hunt/`. Open Claude Code in the repo with the
[Chrome extension](https://claude.com/chrome) connected and say e.g. *"find new data engineer jobs and apply
to the best ones"*. Claude runs the CLI, shows you a shortlist, and after your go-ahead fills each form with the
tailored PDF and cover letter. It asks you for anything not in your profile (notice period, phone, salary),
never types passwords, and verifies the confirmation page after each submit.
The skill includes field-by-field notes for each ATS (re-rendering forms, iframes, hidden file inputs, cookie
banners that swallow clicks).

To use the skill outside this repo, copy the folder to `~/.claude/skills/job-hunt/`.

### Daily run

`daily.sh` runs the pipeline and shows a desktop notification with the number of new matches.
macOS: `scheduling/com.jobhunt.daily.plist.template`; Linux: `scheduling/crontab.example`.

## Responsible use

- Apply only to jobs you actually want; the scoring step exists to keep volume low and quality high.
- Respect each site's terms. LinkedIn's User Agreement prohibits automated access, so the LinkedIn source is
  disabled by default (`disabled_sources` in `config.yaml`); enabling it is at your own risk. Keep any
  browser automation on LinkedIn to a handful of applications per day.
- Review generated resumes before they go out — you will be interviewed on everything in them.

## Русский

Инструмент для поиска работы с Claude Code. Он собирает вакансии из 10+ источников, включая Telegram-каналы,
Habr Career и Getmatch, и оценивает каждую: подходит ли вакансия по локации и праву на работу, какая
зарплата и насколько совпадает опыт. Под каждую подходящую вакансию он генерирует резюме на одну страницу
и сопроводительное письмо. Факты берутся только из вашего мастер-профиля. Через skill Claude Code
заполняет формы откликов в браузере, а вы подтверждаете отправку. Резюме можно делать на русском:
`python -m jobhunt add <url> --lang ru`.

## License

MIT
