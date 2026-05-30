"""
LinkedIn Job Scraper
Uses LinkedIn's public job search (no login required for basic listings).
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search"


class LinkedInScraper:
    def __init__(self, config: dict):
        self.config = config
        self.max_pages = config.get("max_pages", 2)
        self.queries = config.get("search_queries", [])

    def scrape(self) -> list[dict]:
        jobs = []
        for query in self.queries:
            for page in range(self.max_pages):
                start = page * 25
                url = (
                    f"{LINKEDIN_BASE}?keywords={requests.utils.quote(query)}"
                    f"&start={start}&f_TPR=r86400"  # last 24hr filter
                )
                page_jobs = self._scrape_page(url)
                jobs.extend(page_jobs)
                if len(page_jobs) < 5:
                    break  # no more results
                time.sleep(random.uniform(2, 4))
        return self._dedupe(jobs)

    def _scrape_page(self, url: str) -> list[dict]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("LinkedIn request failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        job_cards = soup.select("div.base-card")
        jobs = []

        for card in job_cards:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("Failed to parse card: %s", e)

        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle")
        location_el = card.select_one("span.job-search-card__location")
        link_el = card.select_one("a.base-card__full-link")
        time_el = card.select_one("time")

        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        location = location_el.get_text(strip=True) if location_el else "Unknown Location"
        link = link_el.get("href", "").split("?")[0] if link_el else ""
        posted = time_el.get("datetime", "") if time_el else ""

        if not link:
            return None

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
