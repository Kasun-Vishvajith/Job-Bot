# Job Alert Bot

Automatically searches for technical early-career jobs and sends email plus Telegram alerts for new matches. The default configuration is tuned for worldwide remote, permanent roles requiring 0-3 years of experience, with an emphasis on AI/ML, automation, data, DevOps/cloud/platform, and automotive software/data engineering.

The bot runs twice daily on GitHub Actions, so you do not need to keep a server online.

## What It Searches

- Broad remote feeds: Remotive, Arbeitnow, RemoteOK, Jobicy, Himalayas, and We Work Remotely RSS
- Sri Lankan sources: ITPro.lk official category RSS, TopJobs, XpressJobs, and iJobs
- Public ATS feeds: selected Greenhouse and Lever employers, including mobility/automotive companies
- Direct employer pages: WSO2, IFS, Sysco LABS, 99x, Rootcode, LSEG, and Virtusa
- Secondary discovery pages include Wellfound, YC Jobs, Working Nomads, Real Work From Anywhere, Remote.com, DataScienceJobs, AIJobs, Jobspresso, Arc, Turing, and Toptal

LinkedIn public search is enabled on a best-effort basis for both Sri Lanka-eligible remote roles and Sri Lankan roles of all work types. Indeed and Glassdoor remain disabled because hosted runners are commonly blocked.

## Current Target Profile

The included `config.yaml` is focused on:

- International remote jobs that explicitly include worldwide, Sri Lanka, Asia, or APAC eligibility
- Remote, hybrid, and on-site jobs throughout Sri Lanka
- Data science, data analyst, machine learning, AI, analytics, BI, Python data, and related roles
- Permanent graduate, new-grad, junior, associate, entry-level, early-career, or explicit 0-3 year roles
- A final-year data science profile with three months of software engineering and data science internship experience
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
- `profile.must_have_keywords`: junior, graduate, entry-level, and 0-3 year indicators
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

The workflow runs at 12:00 AM and 12:00 PM Sri Lanka time with a 45-minute safety timeout. API and RSS feeds are fetched once per run; HTML discovery pages are also fetched only once each.

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
4. International remote roles must explicitly include worldwide, Sri Lanka, Asia, or APAC eligibility. Sri Lankan remote, hybrid, and on-site roles are accepted.
5. `utils/database.py` applies a deterministic, non-AI duplicate gate before Gemini. It matches exact IDs, normalized listing URLs, and normalized company-plus-position identities, including duplicates returned by different sources in the same run.
6. An existing vacancy is reconsidered only when its position, application deadline, salary, or location gains or changes information. The new record is marked as an updated listing and linked to the record it supersedes.
7. `utils/ai_filter.py` optionally asks Gemini to score only the remaining new or updated jobs and reject weak matches, senior roles, hybrid/on-site roles outside Sri Lanka, or region-restricted remote roles.
8. `utils/notifier.py` sends alerts and labels changed listings in the dashboard, email, and Telegram output.

## Adding More Remote Searches

Add terms under `job_sites.remote_job_boards.search_terms`:

```yaml
job_sites:
  remote_job_boards:
    search_terms:
      - "AI engineer"
      - "junior data engineer"
      - "entry level machine learning engineer"
      - "graduate DevOps engineer"
```

The API-first sources use `match_keywords` for broad local filtering; `search_terms` are retained for optional HTML scrapers.

## Adding Company Pages

Add pages under `job_sites.company_pages.pages`:

```yaml
- name: "Example Company"
  url: "https://example.com/careers"
  type: "generic"
  keywords: ["data", "analytics", "machine learning", "AI", "DevOps", "junior"]
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
- The early-career filter is intentionally strict: permanent 0-3 year roles are prioritized and internships are rejected.
- `data/seen_jobs.json` is the duplicate and listing-version database and is automatically updated by GitHub Actions.
