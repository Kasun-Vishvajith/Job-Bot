# Job Alert Bot

Automatically searches for technical early-career jobs and sends email plus Telegram alerts for new matches. The default configuration is tuned for worldwide remote, permanent roles requiring 0-3 years of experience, with an emphasis on AI/ML, automation, data, DevOps/cloud/platform, and automotive software/data engineering.

The bot runs once daily on GitHub Actions, so you do not need to keep a server online.

## What It Searches

- Broad remote feeds: Remotive, Arbeitnow, RemoteOK, Jobicy, and Himalayas
- Public ATS feeds: selected Greenhouse and Lever employers, including mobility/automotive companies
- Optional HTML/large-board/local scrapers remain available but are disabled by default to conserve Actions minutes

The strongest worldwide remote search path is the `remote_job_boards` section. LinkedIn, Indeed, TopJobs LK, XpressJobs, and generic company pages remain configurable for manual experiments, but are disabled in the Actions-efficient default profile.

## Current Target Profile

The included `config.yaml` is focused on:

- Fully remote jobs from anywhere in the world
- Hybrid and on-site jobs in Colombo/Sri Lanka
- Data science, data analyst, machine learning, AI, analytics, BI, Python data, and related roles
- Permanent graduate, new-grad, junior, associate, entry-level, early-career, or explicit 0-3 year roles
- Filtering out senior, lead, staff, principal, head, director, VP, and roles asking for high experience

Hybrid and on-site jobs are accepted only when they match the configured Sri Lanka location rules.

## Setup

1. Fork or clone the repo.

```bash
git clone https://github.com/YOUR_USERNAME/job-alert-bot.git
cd job-alert-bot
```

2. Install dependencies locally if you want to test it.

```bash
pip install -r requirements.txt
python main.py
```

3. Edit `config.yaml`.

Important sections:

- `profile.keywords`: data skills and target roles
- `profile.must_have_keywords`: internship, junior, graduate, and 0-year indicators
- `profile.work_types`: controls `remote`, `hybrid`, and `on-site` acceptance
- `job_sites.remote_job_boards.search_terms`: the main worldwide remote search queries
- `job_sites.linkedin.search_queries` and `job_sites.indeed.search_queries`: remote plus Colombo/Sri Lanka queries
- `filtering.enforce_entry_level` and `max_years_experience`: keep matching within 0-3 years
- `filtering.permanent_only`: rejects internships, temporary, seasonal, and contract roles when those types are explicit
- `ai_filtering.min_suitability_score`: raise or lower how selective Gemini should be

## GitHub Secrets

Add these in your GitHub repository under Settings -> Secrets and variables -> Actions:

| Secret Name | Purpose |
|---|---|
| `GMAIL_SENDER` | Gmail account used to send alerts |
| `GMAIL_RECIPIENT` | Email address that receives alerts |
| `GMAIL_APP_PASSWORD` | Gmail app password, not your normal Gmail password |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID |
| `GEMINI_API_KEY` | Optional but recommended Gemini API key |

If `GEMINI_API_KEY` is missing, the bot still runs and uses the normal keyword filter only.

## GitHub Actions

The workflow in `.github/workflows/job_alert.yml` runs once per day at 12:00 AM Sri Lanka time and has a 15-minute hard timeout. API feeds are intentionally fetched once per run and filtered locally.

You can also run it manually from the Actions tab with `Run workflow`.

After each successful run, the workflow commits `data/seen_jobs.json` so the same job is not sent again.

## Project Structure

```text
job-alert-bot/
├── main.py
├── config.yaml
├── requirements.txt
├── .github/workflows/job_alert.yml
├── scrapers/
│   ├── remote_scraper.py
│   ├── linkedin_scraper.py
│   ├── indeed_scraper.py
│   ├── local_scraper.py
│   └── company_scraper.py
├── utils/
│   ├── filter.py
│   ├── ai_filter.py
│   ├── database.py
│   └── notifier.py
└── data/seen_jobs.json
```

## How Filtering Works

1. Scrapers collect raw jobs from all enabled sources.
2. `utils/filter.py` keeps jobs that match data-related keywords.
3. If `filtering.enforce_entry_level` is true, the job must mention an early-career signal or an explicit experience requirement no higher than the configured three years.
4. `profile.work_types` controls remote/hybrid/on-site acceptance. Remote roles are accepted worldwide; hybrid and on-site roles must match the Sri Lanka location rules.
5. `utils/ai_filter.py` optionally asks Gemini to score each job and reject weak matches, senior roles, hybrid/on-site roles outside Sri Lanka, or region-restricted remote roles.
6. `utils/database.py` removes jobs already seen in previous runs.
7. `utils/notifier.py` sends alerts.

## Adding More Remote Searches

Add terms under `job_sites.remote_job_boards.search_terms`:

```yaml
job_sites:
  remote_job_boards:
    search_terms:
      - "data science intern"
      - "junior data analyst"
      - "entry level machine learning"
      - "graduate AI analyst"
```

The API-first sources use `match_keywords` for broad local filtering; `search_terms` are retained for optional HTML scrapers.

## Adding Company Pages

Add pages under `job_sites.company_pages.pages`:

```yaml
- name: "Example Company"
  url: "https://example.com/careers"
  type: "generic"
  keywords: ["data", "analytics", "machine learning", "intern", "junior"]
```

Generic career-page scraping is best-effort. Some company sites render jobs with JavaScript or block automated requests, so dedicated remote job boards usually give better results.

## Troubleshooting

No alerts:

- Check the latest GitHub Actions log.
- Confirm at least one source returned jobs.
- Make sure Gmail and Telegram secrets are set correctly.
- Lower `ai_filtering.min_suitability_score` if Gemini is rejecting too much.

Too many irrelevant alerts:

- Remove `hybrid` and `on-site` from `profile.work_types` if you want worldwide remote-only results.
- Keep `filtering.enforce_entry_level: true`.
- Add senior terms to `profile.exclude_keywords`.
- Raise `ai_filtering.min_suitability_score`.

Scraper returns 0 jobs:

- LinkedIn and Indeed may block GitHub Actions traffic.
- Remote-board APIs can change or temporarily rate-limit requests.
- One failing source does not stop the bot; it logs the error and continues with the others.

## Notes

- The default search is intentionally broad across remote boards to maximize discovery.
- The entry-level filter is intentionally strict so internships and 0-year roles are prioritized.
- `data/seen_jobs.json` is the duplicate-prevention database and is automatically updated by GitHub Actions.
