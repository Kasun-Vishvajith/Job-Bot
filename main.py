#!/usr/bin/env python3
"""
Job Alert Bot — Main Runner
Scrapes job sites, filters by profile, detects new listings,
and sends email + Telegram notifications.
"""

import json
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import yaml

from scrapers.linkedin_scraper import LinkedInScraper
from scrapers.indeed_scraper import IndeedScraper
from scrapers.local_scraper import LocalSiteScraper
from scrapers.company_scraper import CompanyScraper
from utils.filter import JobFilter
from utils.database import JobDatabase
from utils.notifier import Notifier

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def run():
    log.info("=" * 60)
    log.info("Job Alert Bot starting — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 60)

    config = load_config()
    db = JobDatabase(Path(__file__).parent / "data" / "seen_jobs.json")
    job_filter = JobFilter(config["profile"], config["filtering"])
    notifier = Notifier(config["notifications"])

    all_jobs: list[dict] = []

    # ── Scrape LinkedIn ────────────────────────────────────────────────────────
    if config["job_sites"]["linkedin"]["enabled"]:
        log.info("Scraping LinkedIn...")
        try:
            scraper = LinkedInScraper(config["job_sites"]["linkedin"])
            jobs = scraper.scrape()
            log.info("  LinkedIn: found %d raw listings", len(jobs))
            all_jobs.extend(jobs)
        except Exception as e:
            log.error("  LinkedIn scraper failed: %s", e)

    # ── Scrape Indeed ─────────────────────────────────────────────────────────
    if config["job_sites"]["indeed"]["enabled"]:
        log.info("Scraping Indeed...")
        try:
            scraper = IndeedScraper(config["job_sites"]["indeed"])
            jobs = scraper.scrape()
            log.info("  Indeed: found %d raw listings", len(jobs))
            all_jobs.extend(jobs)
        except Exception as e:
            log.error("  Indeed scraper failed: %s", e)

    # ── Scrape Local LK Sites ─────────────────────────────────────────────────
    if config["job_sites"]["local_sites"]["enabled"]:
        log.info("Scraping local Sri Lanka sites...")
        for site_cfg in config["job_sites"]["local_sites"]["sites"]:
            try:
                scraper = LocalSiteScraper(site_cfg)
                jobs = scraper.scrape()
                log.info("  %s: found %d raw listings", site_cfg["name"], len(jobs))
                all_jobs.extend(jobs)
            except Exception as e:
                log.error("  %s scraper failed: %s", site_cfg["name"], e)

    # ── Scrape Company Pages ──────────────────────────────────────────────────
    if config["job_sites"]["company_pages"]["enabled"]:
        log.info("Scraping company career pages...")
        for page_cfg in config["job_sites"]["company_pages"]["pages"]:
            try:
                scraper = CompanyScraper(page_cfg)
                jobs = scraper.scrape()
                log.info("  %s: found %d raw listings", page_cfg["name"], len(jobs))
                all_jobs.extend(jobs)
            except Exception as e:
                log.error("  %s scraper failed: %s", page_cfg["name"], e)

    log.info("Total raw jobs scraped: %d", len(all_jobs))

    # ── Filter by profile ─────────────────────────────────────────────────────
    matched_jobs = job_filter.filter(all_jobs)
    log.info("Jobs matching your profile: %d", len(matched_jobs))

    # ── Deduplicate — only keep genuinely new listings ─────────────────────────
    new_jobs = db.get_new_jobs(matched_jobs)
    log.info("NEW jobs not seen before: %d", len(new_jobs))

    if not new_jobs:
        log.info("No new matching jobs found. No notification sent.")
        return

    # ── Sort: jobs with salary listed first ───────────────────────────────────
    new_jobs.sort(key=lambda j: (not j.get("salary"), j.get("title", "")))

    # ── Send notifications ────────────────────────────────────────────────────
    log.info("Sending notifications for %d new jobs...", len(new_jobs))
    notifier.send(new_jobs, config["profile"]["name"])

    # ── Save to database ──────────────────────────────────────────────────────
    db.save_jobs(new_jobs)
    log.info("Database updated. All done!")


if __name__ == "__main__":
    run()
