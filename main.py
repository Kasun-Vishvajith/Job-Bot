#!/usr/bin/env python3
"""
Job Alert Bot — Main Runner
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
from scrapers.remote_scraper import RemoteJobBoardScraper
from utils.filter import JobFilter
from utils.ai_filter import AIFilter
from utils.database import JobDatabase
from utils.notifier import Notifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run():
    log.info("=" * 60)
    log.info("Job Alert Bot starting — %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("=" * 60)

    config = load_config()
    db = JobDatabase(Path(__file__).parent / "data" / "seen_jobs.json")
    job_filter = JobFilter(config["profile"], config["filtering"])
    ai_filter = AIFilter(config["profile"], config.get("ai_filtering", {}))
    notifier = Notifier(config["notifications"])

    all_jobs: list[dict] = []

    # Dedicated worldwide remote boards and APIs.
    if config["job_sites"].get("remote_job_boards", {}).get("enabled"):
        log.info("Scraping worldwide remote job boards...")
        try:
            scraper = RemoteJobBoardScraper(config["job_sites"]["remote_job_boards"])
            jobs = scraper.scrape()
            log.info("  Remote boards: found %d raw listings", len(jobs))
            if jobs:
                log.info(
                    "  Remote board sample: %s @ %s (%s)",
                    jobs[0].get("title"),
                    jobs[0].get("company"),
                    jobs[0].get("source"),
                )
            all_jobs.extend(jobs)
        except Exception as e:
            log.error("  Remote job board scraper failed: %s", e)

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    if config["job_sites"]["linkedin"]["enabled"]:
        log.info("Scraping LinkedIn...")
        try:
            scraper = LinkedInScraper(config["job_sites"]["linkedin"])
            jobs = scraper.scrape()
            log.info("  LinkedIn: found %d raw listings", len(jobs))
            if jobs:
                log.info("  LinkedIn sample: %s @ %s (%s)",
                    jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("location"))
            all_jobs.extend(jobs)
        except Exception as e:
            log.error("  LinkedIn scraper failed: %s", e)

    # ── Indeed ────────────────────────────────────────────────────────────────
    if config["job_sites"]["indeed"]["enabled"]:
        log.info("Scraping Indeed...")
        try:
            scraper = IndeedScraper(config["job_sites"]["indeed"])
            jobs = scraper.scrape()
            log.info("  Indeed: found %d raw listings", len(jobs))
            if jobs:
                log.info("  Indeed sample: %s @ %s (%s)",
                    jobs[0].get("title"), jobs[0].get("company"), jobs[0].get("location"))
            all_jobs.extend(jobs)
        except Exception as e:
            log.error("  Indeed scraper failed: %s", e)

    # ── Local LK Sites ────────────────────────────────────────────────────────
    if config["job_sites"]["local_sites"]["enabled"]:
        log.info("Scraping local Sri Lanka sites...")
        for site_cfg in config["job_sites"]["local_sites"]["sites"]:
            if not site_cfg.get("enabled", True):
                log.info("  %s: disabled (skipping)", site_cfg["name"])
                continue
            try:
                scraper = LocalSiteScraper(site_cfg)
                jobs = scraper.scrape()
                log.info("  %s: found %d raw listings", site_cfg["name"], len(jobs))
                if jobs:
                    log.info("  %s sample: %s @ %s",
                        site_cfg["name"], jobs[0].get("title"), jobs[0].get("company"))
                all_jobs.extend(jobs)
            except Exception as e:
                log.error("  %s scraper failed: %s", site_cfg["name"], e)

    # ── Company Pages ─────────────────────────────────────────────────────────
    if config["job_sites"]["company_pages"]["enabled"]:
        log.info("Scraping company career pages...")
        for page_cfg in config["job_sites"]["company_pages"]["pages"]:
            if not page_cfg.get("enabled", True):
                log.info("  %s: disabled (skipping)", page_cfg["name"])
                continue
            try:
                scraper = CompanyScraper(page_cfg)
                jobs = scraper.scrape()
                log.info("  %s: found %d raw listings", page_cfg["name"], len(jobs))
                all_jobs.extend(jobs)
            except Exception as e:
                log.error("  %s scraper failed: %s", page_cfg["name"], e)

    log.info("-" * 60)
    log.info("TOTAL raw jobs scraped: %d", len(all_jobs))

    # ── Filter ────────────────────────────────────────────────────────────────
    matched_jobs = job_filter.filter(all_jobs)
    log.info("Jobs matching profile after keyword filter: %d", len(matched_jobs))

    # ── Show filter breakdown if 0 matched ───────────────────────────────────
    if len(all_jobs) > 0 and len(matched_jobs) == 0:
        log.warning("Filter rejected ALL jobs. Showing why for first 5 raw jobs:")
        for job in all_jobs[:5]:
            text = " ".join([
                job.get("title",""), job.get("company",""),
                job.get("location",""), job.get("description",""),
                job.get("work_type","")
            ]).lower()
            must_kws   = config["profile"].get("must_have_keywords", [])
            must_found = [k for k in must_kws if k.lower() in text]
            prof_kws   = config["profile"].get("keywords", [])
            prof_found = [k for k in prof_kws if k.lower() in text]
            excl_kws   = config["profile"].get("exclude_keywords", [])
            excl_found = [k for k in excl_kws if k.lower() in text]
            log.warning(
                "  '%s' | must_have=%s | profile_kws=%s | excluded=%s | location='%s' | work_type='%s'",
                job.get("title"), must_found, prof_found, excl_found,
                job.get("location"), job.get("work_type")
            )

    if len(all_jobs) == 0:
        log.warning("All scrapers returned 0 jobs. Possible causes:")
        log.warning("  1. Sites are blocking the scraper (most likely)")
        log.warning("  2. No jobs listed matching the search queries")
        log.warning("  3. HTML structure of site has changed")

    # ── AI Filter ─────────────────────────────────────────────────────────────
    matched_jobs = ai_filter.filter(matched_jobs)
    log.info("Jobs matching profile after AI filter: %d", len(matched_jobs))

    # ── Deduplicate ───────────────────────────────────────────────────────────
    new_jobs = db.get_new_jobs(matched_jobs)
    log.info("NEW jobs (not seen before): %d", len(new_jobs))

    if not new_jobs:
        log.info("No new matching jobs found. No notification sent.")
        return

    new_jobs.sort(key=lambda j: (not j.get("salary"), j.get("title", "")))

    # ── Notify ────────────────────────────────────────────────────────────────
    log.info("Sending notifications for %d new jobs...", len(new_jobs))
    notifier.send(new_jobs, config["profile"]["name"])

    db.save_jobs(new_jobs)
    log.info("Done! Database updated.")


if __name__ == "__main__":
    run()
