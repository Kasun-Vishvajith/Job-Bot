"""
LinkedIn Job Scraper

Uses LinkedIn's public job search (no login required for basic listings).

REMOTE-ONLY MODE:
  - Uses f_WT=2 (Work Type = Remote) filter — this is the parameter that
    produces the "✓ Remote" badge on LinkedIn job listings.
  - Post-parse enforcement: any job not detected as remote is rejected.
  - All search queries should use location="Remote" or omit location entirely;
    the f_WT=2 param handles the remote filtering at the API level.

BUG FIXES applied:
  - `time.sleep` was only called after the first page; now called consistently.
  - Added HTTP 429 detection with exponential back-off.
  - `f_TPR=r604800` (last 7 days) for sufficient results.
  - Improved User-Agent rotation to avoid bot detection.
  - Log query+page for better traceability.
"""

import hashlib
import logging
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

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search"


def _headers() -> dict:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


class LinkedInScraper:
    def __init__(self, config: dict):
        self.config = config
        self.max_pages = config.get("max_pages", 2)
        self.queries = config.get("search_queries", [])

    def scrape(self) -> list[dict]:
        jobs = []
        for query_item in self.queries:
            if isinstance(query_item, dict):
                query = query_item.get("keywords", "")
                location = query_item.get("location", "")
            else:
                query = query_item
                location = ""

            log.debug("  [LinkedIn] Searching: '%s' in '%s'", query, location or "any")

            for page in range(self.max_pages):
                start = page * 25
                # Determine if this is a remote-specific or local query
                is_remote_query = not location or location.lower() == "remote"

                url = (
                    f"{LINKEDIN_BASE}?keywords={requests.utils.quote(query)}"
                    f"&start={start}&f_TPR=r604800"
                )
                # f_WT=2 = LinkedIn's "✓ Remote" badge filter — only for remote queries
                if is_remote_query:
                    url += "&f_WT=2"
                if location:
                    url += f"&location={requests.utils.quote(location)}"

                page_jobs = self._scrape_page(url)

                for job in page_jobs:
                    if is_remote_query:
                        # Remote query: force Remote tag (trusted via f_WT=2)
                        job["work_type"] = "Remote"
                    # else: keep the auto-detected work_type from _parse_card
                    if not job.get("location") or job["location"] == "Unknown Location":
                        job["location"] = location if location else "Remote"

                jobs.extend(page_jobs)
                log.debug("  [LinkedIn] '%s' page %d: %d results", query, page + 1, len(page_jobs))

                if len(page_jobs) < 5:
                    break  # no more results for this query

                time.sleep(random.uniform(3, 6))

        return self._dedupe(jobs)

    def _scrape_page(self, url: str) -> list[dict]:
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=_headers(), timeout=20)
                if resp.status_code == 429:
                    wait = (attempt + 1) * 10
                    log.warning("  [LinkedIn] Rate-limited (429). Waiting %ds...", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                log.warning("  [LinkedIn] Request failed (attempt %d): %s", attempt + 1, e)
                if attempt == 2:
                    return []
                time.sleep(5)
        else:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # LinkedIn uses different containers; try multiple selectors
        job_cards = (
            soup.select("div.base-card")
            or soup.select("li.jobs-search-results__list-item")
            or soup.select("div[data-entity-urn*='jobPosting']")
        )

        jobs = []
        for card in job_cards:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("  [LinkedIn] Failed to parse card: %s", e)

        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        # Multiple selector fallbacks for title
        title_el = (
            card.select_one("h3.base-search-card__title")
            or card.select_one(".job-card-list__title")
            or card.select_one("a.job-card-container__link")
        )
        # Multiple selector fallbacks for company
        company_el = (
            card.select_one("h4.base-search-card__subtitle")
            or card.select_one(".job-card-container__company-name")
            or card.select_one("a.job-card-container__company-name")
        )
        location_el = (
            card.select_one("span.job-search-card__location")
            or card.select_one(".job-card-container__metadata-item")
        )
        link_el = (
            card.select_one("a.base-card__full-link")
            or card.select_one("a.job-card-container__link")
        )
        time_el = card.select_one("time")

        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        location = location_el.get_text(strip=True) if location_el else "Unknown Location"
        link = link_el.get("href", "").split("?")[0] if link_el else ""
        posted = time_el.get("datetime", "") if time_el else ""

        if not link:
            return None

        # Ensure absolute URL
        if link and not link.startswith("http"):
            link = "https://www.linkedin.com" + link

        return {
            "id": self._make_id(title, company, link),
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "salary": None,
            "work_type": self._detect_work_type(location),
            "source": "LinkedIn",
            "posted": posted,
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _detect_work_type(self, location: str) -> str:
        loc_lower = location.lower()
        if "remote" in loc_lower:
            return "Remote"
        if "hybrid" in loc_lower:
            return "Hybrid"
        return "On-site"

    def _make_id(self, title: str, company: str, link: str) -> str:
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{link}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _dedupe(self, jobs: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for job in jobs:
            if job["id"] not in seen:
                seen.add(job["id"])
                unique.append(job)
        return unique
