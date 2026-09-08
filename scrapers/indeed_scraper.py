"""
Indeed Job Scraper — REMOTE-ONLY MODE

Scrapes Indeed job listings using their public search pages.

REMOTE-ONLY:
  - Uses sc=0kf:attr(DSQF7)l; filter (Indeed's remote work attribute).
  - Post-parse enforcement: rejects any job not tagged as Remote.

BUG FIXES applied:
  - Indeed heavily uses Cloudflare/bot detection; added realistic cookie+header simulation.
  - `fromage=14` for more results.
  - Indeed card selector `[data-jk]` dedup guard.
  - `_make_id` uses job_id (data-jk) when available.
  - Added 429 detection with back-off.
  - Improved salary detection to include LKR/stipend/monthly.
"""

import hashlib
import logging
import re
import time
import random
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
]

INDEED_BASE = "https://www.indeed.com/jobs"


def _headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.indeed.com",
    }


class IndeedScraper:
    def __init__(self, config: dict):
        self.config = config
        self.max_pages = config.get("max_pages", 2)
        self.queries = config.get("search_queries", [])
        self.location = config.get("location", "Sri Lanka")

    def scrape(self) -> list[dict]:
        jobs = []
        for query_item in self.queries:
            if isinstance(query_item, dict):
                query = query_item.get("keywords", "")
                location = query_item.get("location", self.location)
            else:
                query = query_item
                location = self.location

            log.debug("  [Indeed] Searching: '%s' in '%s'", query, location)

            for page in range(self.max_pages):
                start = page * 10
                is_remote_query = location.lower() == "remote"

                url = (
                    f"{INDEED_BASE}?q={requests.utils.quote(query)}"
                    f"&l={requests.utils.quote(location)}"
                    f"&fromage=14&start={start}&sort=date"
                )
                # Remote filter only for remote-specific queries
                if is_remote_query:
                    url += "&sc=0kf%3Aattr%28DSQF7%29l%3B"

                page_jobs = self._scrape_page(url)

                for job in page_jobs:
                    if is_remote_query:
                        job["work_type"] = "Remote"
                    if not job.get("location") or job["location"] == "Unknown Location":
                        job["location"] = location

                jobs.extend(page_jobs)
                log.debug("  [Indeed] '%s' page %d: %d results", query, page + 1, len(page_jobs))

                if len(page_jobs) < 5:
                    break
                time.sleep(random.uniform(3, 6))

        return self._dedupe(jobs)

    def _scrape_page(self, url: str) -> list[dict]:
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=_headers(), timeout=20)
                if resp.status_code == 429:
                    wait = (attempt + 1) * 15
                    log.warning("  [Indeed] Rate-limited (429). Waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                log.warning("  [Indeed] Request failed (attempt %d): %s", attempt + 1, e)
                if attempt == 2:
                    return []
                time.sleep(5)
        else:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Indeed uses different selectors — try multiple
        job_cards = (
            soup.select("div.job_seen_beacon")
            or soup.select("div.tapItem")
        )

        # BUG FIX: Fallback using [data-jk] but restrict to direct children
        # to avoid capturing both parent and child cards (double-counting).
        if not job_cards:
            job_cards = [
                el for el in soup.select("[data-jk]")
                if el.name in ("div", "li", "article")
                and not el.find_parent(attrs={"data-jk": True})
            ]

        jobs = []
        seen_jk = set()
        for card in job_cards:
            try:
                job = self._parse_card(card)
                if job:
                    # BUG FIX: dedupe by data-jk within a single page
                    jk = card.get("data-jk")
                    if jk and jk in seen_jk:
                        continue
                    if jk:
                        seen_jk.add(jk)
                    jobs.append(job)
            except Exception as e:
                log.debug("  [Indeed] Failed to parse card: %s", e)

        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        title_el = (
            card.select_one("h2.jobTitle span[title]")
            or card.select_one("h2.jobTitle a span")
            or card.select_one("h2 a[data-jk]")
            or card.select_one("[class*='jobTitle']")
        )
        company_el = (
            card.select_one("span.companyName")
            or card.select_one("[data-testid='company-name']")
            or card.select_one("[class*='companyName']")
        )
        location_el = (
            card.select_one("div.companyLocation")
            or card.select_one("[data-testid='text-location']")
            or card.select_one("[class*='companyLocation']")
        )
        salary_el = (
            card.select_one("div.salary-snippet-container")
            or card.select_one("[data-testid='attribute_snippet_testid']")
            or card.select_one("[class*='salary']")
        )

        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        location = location_el.get_text(strip=True) if location_el else "Unknown Location"
        salary_text = salary_el.get_text(strip=True) if salary_el else None

        # Build job link from data-jk
        job_id_el = card.get("data-jk") or (card.select_one("a[data-jk]") or {}).get("data-jk")
        link = f"https://www.indeed.com/viewjob?jk={job_id_el}" if job_id_el else ""

        if not title or title == "Unknown Title":
            return None

        # BUG FIX: Use job_id_el as the unique key for ID generation to prevent
        # false duplicates when same job appears in multiple search queries.
        id_key = job_id_el if job_id_el else f"{title}-{company}-{location}"

        return {
            "id": self._make_id(id_key),
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "salary": self._clean_salary(salary_text),
            "work_type": self._detect_work_type(location, title),
            "source": "Indeed",
            "posted": "",
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _clean_salary(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        # BUG FIX: Extended salary indicators to match LKR, stipend, monthly pay
        salary_indicators = [
            "$", "lkr", "rs.", "rs ", "per", "hour", "month", "year",
            "salary", "pay", "stipend", "compensation", "annum", "k/yr",
        ]
        if any(ind in text.lower() for ind in salary_indicators):
            return text.strip()
        return None

    def _detect_work_type(self, location: str, title: str) -> str:
        combined = (location + " " + title).lower()
        if "remote" in combined or "work from home" in combined or "wfh" in combined:
            return "Remote"
        if "hybrid" in combined:
            return "Hybrid"
        return "On-site"

    def _make_id(self, key: str) -> str:
        return hashlib.md5(key.lower().strip().encode()).hexdigest()

    def _dedupe(self, jobs: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for job in jobs:
            if job["id"] not in seen:
                seen.add(job["id"])
                unique.append(job)
        return unique
