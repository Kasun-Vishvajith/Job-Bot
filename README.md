# Job Alert Bot

Automatically searches for data science related jobs and sends email plus Telegram alerts for new matches. The default configuration is tuned for worldwide remote roles plus hybrid and on-site roles in Colombo/Sri Lanka, focused on internships, graduate roles, junior roles, and 0-1 year experience roles.

The bot is designed to run on GitHub Actions every 3 hours, so you do not need to keep a server online.

## What It Searches

- Remote-first job boards: Remotive, Arbeitnow, RemoteOK, We Work Remotely, and Remote.co
- Large job boards: LinkedIn and Indeed
- Local Sri Lanka sites: TopJobs LK and XpressJobs
- Company career pages listed in `config.yaml`

The strongest worldwide remote search path is the `remote_job_boards` section. LinkedIn, Indeed, TopJobs LK, XpressJobs, and company pages are also used to find Colombo/Sri Lanka hybrid and on-site roles.

## Current Target Profile

The included `config.yaml` is focused on:

- Fully remote jobs from anywhere in the world
- Hybrid and on-site jobs in Colombo/Sri Lanka
- Data science, data analyst, machine learning, AI, analytics, BI, Python data, and related roles
- Internship, trainee, placement, student, graduate, new grad, junior, associate, entry-level, no-experience, or 0-year roles
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
- `filtering.enforce_entry_level`: set to `true` to keep internship/entry-level matching strict
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

The workflow in `.github/workflows/job_alert.yml` runs 8 times per day:

- 12:00 AM, 3:00 AM, 6:00 AM, 9:00 AM, 12:00 PM, 3:00 PM, 6:00 PM, and 9:00 PM Sri Lanka time

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
3. If `filtering.enforce_entry_level` is true, the job must mention an entry-level signal such as intern, internship, trainee, junior, graduate, new grad, no experience, or 0 years.
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

Short, specific search phrases usually work best.

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
