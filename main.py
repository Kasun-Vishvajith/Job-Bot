#!/usr/bin/env python3
"""
Job Alert Bot — Main Runner

BUG FIXES applied:
  - local_sites: TopJobs entry had no `enabled` key but all others did; this caused
    inconsistent skip logic. Now the enabled check uses `.get("enabled", True)` which
    already handles it, but logged a note for clarity.
  - Added Glassdoor scraper integration.
  - Added per-source timing log so slow scrapers are visible.
  - All scrapers are now wrapped in try/except with detailed exception type logging.
  - Added a startup summary log showing which sources are enabled.
  - db.save_jobs() was only called after notifier.send() succeeded; if send() raised,
    the database was never updated. Now save_jobs() always runs after filtering.
"""

import json
import os
import sys
import logging
import time
from datetime import datetime
from pathlib import Path

import yaml

from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.local_scraper import LocalSiteScraper
from scrapers.company_scraper import CompanyScraper
from scrapers.remote_scraper import RemoteJobBoardScraper
from scrapers.glassdoor_scraper import GlassdoorScraper
from utils.filter import JobFilter
from utils.ai_filter import AIFilter
from utils.database import JobDatabase
from utils.notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _scrape_timed(name: str, fn) -> list[dict]:
    """Run a scraper function, log elapsed time, and return results safely."""
    t0 = time.time()
    try:
        results = fn()
        elapsed = time.time() - t0
        log.info("  ✓ %s: %d listings in %.1fs", name, len(results), elapsed)
        return results
    except Exception as e:
        elapsed = time.time() - t0
        log.error("  ✗ %s scraper FAILED after %.1fs — %s: %s",
                  name, elapsed, type(e).__name__, e)
        return []


def run():
    log.info("=" * 65)
    log.info("Job Alert Bot starting — %s (UTC)", datetime.utcnow().strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 65)

    config = load_config()
    db = JobDatabase(Path(__file__).parent / "data" / "seen_jobs.json")
    job_filter = JobFilter(config["profile"], config["filtering"])
    ai_filter = AIFilter(config["profile"], config.get("ai_filtering", {}))
    notifier = Notifier(config["notifications"])

    job_sites = config["job_sites"]
    all_jobs: list[dict] = []

    # ── Print enabled-sources summary ─────────────────────────────────────────
    enabled = []
    if job_sites.get("remote_job_boards", {}).get("enabled"):
        enabled.append("Remote Boards")
    if job_sites.get("linkedin", {}).get("enabled"):
        enabled.append("LinkedIn")
    if job_sites.get("indeed", {}).get("enabled"):
        enabled.append("Indeed")
    if job_sites.get("glassdoor", {}).get("enabled"):
        enabled.append("Glassdoor")
    if job_sites.get("local_sites", {}).get("enabled"):
        enabled.append("Local LK Sites")
    if job_sites.get("company_pages", {}).get("enabled"):
        enabled.append("Company Pages")
    log.info("Enabled sources: %s", ", ".join(enabled) if enabled else "NONE")
    log.info("-" * 65)

    # ── Worldwide remote job boards (APIs — most reliable) ────────────────────
    if job_sites.get("remote_job_boards", {}).get("enabled"):
        log.info("[1/6] Scraping worldwide remote job boards...")
        scraper = RemoteJobBoardScraper(job_sites["remote_job_boards"])
        jobs = _scrape_timed("Remote Boards", scraper.scrape)
        if jobs:
            log.info("  Sample: '%s' @ %s via %s",
                     jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("source"))
        all_jobs.extend(jobs)

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    if job_sites.get("linkedin", {}).get("enabled"):
        log.info("[2/6] Scraping LinkedIn...")
        scraper = LinkedInScraper(job_sites["linkedin"])
        jobs = _scrape_timed("LinkedIn", scraper.scrape)
        if jobs:
            log.info("  Sample: '%s' @ %s (%s)",
                     jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("location"))
        all_jobs.extend(jobs)

    # ── Indeed ────────────────────────────────────────────────────────────────
    if job_sites.get("indeed", {}).get("enabled"):
        log.info("[3/6] Scraping Indeed...")
        scraper = IndeedScraper(job_sites["indeed"])
        jobs = _scrape_timed("Indeed", scraper.scrape)
        if jobs:
            log.info("  Sample: '%s' @ %s (%s)",
                     jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("location"))
        all_jobs.extend(jobs)

    # ── Glassdoor ─────────────────────────────────────────────────────────────
    if job_sites.get("glassdoor", {}).get("enabled"):
        log.info("[4/6] Scraping Glassdoor...")
        scraper = GlassdoorScraper(job_sites["glassdoor"])
        jobs = _scrape_timed("Glassdoor", scraper.scrape)
        if jobs:
            log.info("  Sample: '%s' @ %s (%s)",
                     jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("location"))
        all_jobs.extend(jobs)

    # ── Local Sri Lanka Sites ─────────────────────────────────────────────────
    if job_sites.get("local_sites", {}).get("enabled"):
        log.info("[5/6] Scraping local Sri Lanka sites...")
        for site_cfg in job_sites["local_sites"].get("sites", []):
            # BUG FIX: TopJobs entry had no 'enabled' key; default to True
            if not site_cfg.get("enabled", True):
                log.info("  %s: disabled (skipping)", site_cfg["name"])
                continue
            scraper = LocalSiteScraper(site_cfg)
            jobs = _scrape_timed(site_cfg["name"], scraper.scrape)
            if jobs:
                log.info("  %s sample: '%s' @ %s",
                         site_cfg["name"], jobs[0].get("title"), jobs[0].get("company"))
            all_jobs.extend(jobs)

    # ── Company Career Pages ──────────────────────────────────────────────────
    if job_sites.get("company_pages", {}).get("enabled"):
        log.info("[6/6] Scraping company career pages...")
        for page_cfg in job_sites["company_pages"].get("pages", []):
            if not page_cfg.get("enabled", True):
                log.info("  %s: disabled (skipping)", page_cfg["name"])
                continue
            scraper = CompanyScraper(page_cfg)
            jobs = _scrape_timed(page_cfg["name"], scraper.scrape)
            all_jobs.extend(jobs)

    log.info("=" * 65)
    log.info("TOTAL raw listings scraped: %d", len(all_jobs))
    log.info("=" * 65)

    # ── Keyword Filter ────────────────────────────────────────────────────────
    matched_jobs = job_filter.filter(all_jobs)
    log.info("After keyword filter: %d/%d jobs matched", len(matched_jobs), len(all_jobs))

    # ── Debug: Why did filter reject everything? ───────────────────────────────
    if len(all_jobs) > 0 and len(matched_jobs) == 0:
        log.warning("⚠ Filter rejected ALL %d jobs. Breakdown for first 5:", len(all_jobs))
        for job in all_jobs[:5]:
            text = " ".join([
                job.get("title", ""), job.get("company", ""),
                job.get("location", ""), job.get("description", ""),
                job.get("work_type", "")
            ]).lower()
            must_kws = config["profile"].get("must_have_keywords", [])
            must_found = [k for k in must_kws if k.lower() in text]
            prof_kws = config["profile"].get("keywords", [])
            prof_found = [k for k in prof_kws if k.lower() in text]
            excl_kws = config["profile"].get("exclude_keywords", [])
            excl_found = [k for k in excl_kws if k.lower() in text]
            log.warning(
                "  '%s' | must=%s | profile=%s | excluded=%s | loc='%s' | type='%s'",
                job.get("title"), must_found, prof_found[:3], excl_found,
                job.get("location"), job.get("work_type"),
            )

    if len(all_jobs) == 0:
        log.warning("⚠ All scrapers returned 0 jobs. Possible causes:")
        log.warning("  1. Sites are blocking GitHub Actions IP (most likely)")
        log.warning("  2. No jobs listed matching the search queries")
        log.warning("  3. HTML structure of the site has changed")
        log.warning("  4. Rate-limited — wait a few hours and try again")

    # Deduplicate before calling Gemini so repeat daily runs do not spend API
    # time scoring jobs that are already on the dashboard or already rejected.
    candidates = db.get_new_jobs(matched_jobs)
    ai_limit = config.get("ai_filtering", {}).get("max_jobs_per_run", 60)
    candidates = candidates[:ai_limit]
    log.info("NEW candidates for AI review: %d", len(candidates))

    # ── AI Suitability Filter ─────────────────────────────────────────────────
    new_jobs = ai_filter.filter(candidates)
    accepted_ids = {job.get("id") for job in new_jobs}
    rejected_jobs = [job for job in candidates if job.get("id") not in accepted_ids]
    if rejected_jobs and ai_filter.enabled and ai_filter.api_key:
        db.save_ignored(rejected_jobs)
    log.info("After AI filter: %d jobs remain", len(new_jobs))

    if not new_jobs:
        log.info("No new matching jobs found this cycle. No notification sent.")
        return

    # Sort: jobs with salary first, then alphabetically by title
    new_jobs.sort(key=lambda j: (not j.get("salary"), j.get("title", "").lower()))

    # ── Notify ────────────────────────────────────────────────────────────────
    log.info("Sending notifications for %d new jobs...", len(new_jobs))
    try:
        notifier.send(new_jobs, config["profile"]["name"])
    except Exception as e:
        log.error("Notification failed: %s: %s", type(e).__name__, e)

    # BUG FIX: Save database regardless of whether notification succeeded.
    # Previously if notifier.send() raised, we'd never mark jobs as seen,
    # causing the same jobs to be re-notified every run.
    db.save_jobs(new_jobs)
    log.info("✓ Database updated. Done!")


if __name__ == "__main__":
    run()
