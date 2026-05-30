# 🚀 Job Alert Bot

Automatically scrapes job listings every 3 hours and sends you beautiful email + Telegram alerts for new positions matching your profile. Built to run free on GitHub Actions — no server needed.

---

## What It Does

- Scrapes **LinkedIn**, **Indeed**, **TopJobs LK**, **XpressJobs**, and any **company career pages** you add
- Filters jobs by **your keywords** (data science, undergraduate, etc.)
- Detects **only new listings** — never notifies you about the same job twice
- Sends a **beautiful HTML email** + **instant Telegram message** for each new match
- Highlights **salary/payout** when listed
- Shows **work type**: Remote 🏠 / Hybrid 🔀 / On-site 🏢
- Runs automatically **8 times a day** (every 3 hours, LKT time)

---

## Setup Guide

### Step 1 — Fork or Clone This Repo

```bash
git clone https://github.com/YOUR_USERNAME/job-alert-bot.git
cd job-alert-bot
```

Push it to your own GitHub repository.

---

### Step 2 — Edit `config.yaml`

Open `config.yaml` and customize:

- **Your name** (used in email greeting)
- **Keywords** (add/remove skills, levels, etc.)
- **Exclude keywords** (filter out senior roles)
- **Job sites** (toggle on/off, add company URLs)
- **Your email address**

---

### Step 3 — Set Up Gmail App Password

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already done
3. Search for **"App passwords"** in the search bar
4. Create a new app password → select **Mail** → **Other** → name it "Job Bot"
5. Copy the 16-character password shown

---

### Step 4 — Set Up Telegram Bot (optional but recommended)

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts → copy your **Bot Token**
3. Start a chat with your new bot (search its name)
4. Get your **Chat ID**: visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` after sending any message to your bot
5. Look for `"chat":{"id": 123456789}` — that number is your Chat ID

---

### Step 5 — Add GitHub Secrets

In your GitHub repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these 5 secrets:

| Secret Name | Value |
|---|---|
| `GMAIL_SENDER` | your-gmail@gmail.com |
| `GMAIL_RECIPIENT` | email to receive alerts (can be same) |
| `GMAIL_APP_PASSWORD` | the 16-char app password from Step 3 |
| `TELEGRAM_BOT_TOKEN` | your bot token from Step 4 |
| `TELEGRAM_CHAT_ID` | your chat ID from Step 4 |

---

### Step 6 — Enable GitHub Actions

1. Go to your repo → **Actions** tab
2. Click **"I understand my workflows, go ahead and enable them"**
3. The bot will now run automatically on schedule!

To test immediately: Actions → **Job Alert Bot** → **Run workflow**

---

## Customizing Your Profile

Edit `config.yaml` — it's designed to be simple:

```yaml
profile:
  keywords:
    - "data science"        # add any skill
    - "machine learning"
    - "your new keyword"    # ← just add a line like this

  exclude_keywords:
    - "10+ years"           # blocks senior roles
    - "C-level"

company_pages:
  pages:
    - name: "Dialog"
      url: "https://www.dialog.lk/en/career-opportunities"
      type: "generic"
      keywords: ["data", "analytics", "tech"]
```

---

## Adding More Job Sites

In `config.yaml` under `company_pages.pages`:

```yaml
- name: "Hsenid"
  url: "https://hsenidmobile.com/careers/"
  type: "generic"
  keywords: ["data", "developer", "intern"]

- name: "Axiata Digital"
  url: "https://careers.axiatadigital.com"
  type: "generic"
  keywords: ["data", "analytics", "AI"]
```

---

## Project Structure

```
job-alert-bot/
├── main.py                    # Main runner
├── config.yaml                # YOUR configuration file
├── requirements.txt
├── .github/
│   └── workflows/
│       └── job_alert.yml      # GitHub Actions schedule
├── scrapers/
│   ├── linkedin_scraper.py    # LinkedIn scraper
│   ├── indeed_scraper.py      # Indeed scraper
│   ├── local_scraper.py       # TopJobs LK, XpressJobs
│   └── company_scraper.py     # Generic company page scraper
├── utils/
│   ├── filter.py              # Profile keyword matching
│   ├── database.py            # Deduplication (seen jobs)
│   └── notifier.py            # Email + Telegram sender
└── data/
    └── seen_jobs.json         # Auto-updated job database
```

---

## Email Preview

Each alert email includes beautiful job cards with:
- Job title, company, location
- Work type badge (Remote / Hybrid / On-site)
- Salary (if listed) highlighted in green
- Matched keywords as tags
- One-click **View Job** button

---

## Troubleshooting

**No emails received?**
- Check GitHub Actions logs (Actions tab → latest run)
- Verify Gmail App Password is correct (not your regular password)
- Make sure 2FA is enabled on your Google account

**Too many/few results?**
- Add more specific keywords to `exclude_keywords` to filter out irrelevant jobs
- Increase `min_keyword_matches` to 2 for stricter filtering

**A site not loading?**
- Some sites block scrapers. Check the logs for error messages.
- You can disable any scraper with `enabled: false` in `config.yaml`

---

## Notes

- LinkedIn and Indeed may occasionally block scrapers — this is normal. The bot retries gracefully.
- The database (`data/seen_jobs.json`) is committed back to your repo after each run automatically.
- Job IDs older than 60 days are cleaned up automatically.
- Running on GitHub Actions free tier: 2,000 minutes/month — this bot uses ~2 min/day.
