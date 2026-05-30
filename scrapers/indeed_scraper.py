"""
Indeed Job Scraper
Scrapes Indeed job listings using their public search pages.
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
    "Referer": "https://www.indeed.com",
}

INDEED_BASE = "https://www.indeed.com/jobs"


class IndeedScraper:
    def __init__(self, config: dict):
        self.config = config
        self.max_pages = config.get("max_pages", 2)
        self.queries = config.get("search_queries", [])
        self.location = config.get("location", "Sri Lanka")

    def scrape(self) -> list[dict]:
        jobs = []
        for query in self.queries:
            for page in range(self.max_pages):
                start = page * 10
                url = (
                    f"{INDEED_BASE}?q={requests.utils.quote(query)}"
                    f"&l={requests.utils.quote(self.location)}"
                    f"&fromage=7&start={start}"
                )
                page_jobs = self._scrape_page(url)
                jobs.extend(page_jobs)
                if len(page_jobs) < 5:
                    break
                time.sleep(random.uniform(3, 5))
        return self._dedupe(jobs)

    def _scrape_page(self, url: str) -> list[dict]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("Indeed request failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Indeed uses different selectors — try multiple
        job_cards = (
            soup.select("div.job_seen_beacon")
            or soup.select("div.tapItem")
            or soup.select("[data-jk]")
        )

        jobs = []
        for card in job_cards:
            try:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("Failed to parse Indeed card: %s", e)

        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        title_el = card.select_one("h2.jobTitle span[title], h2.jobTitle a span")
        company_el = card.select_one("span.companyName, [data-testid='company-name']")
        location_el = card.select_one("div.companyLocation, [data-testid='text-location']")
        salary_el = card.select_one("div.salary-snippet-container, [data-testid='attribute_snippet_testid']")

        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else "Unknown Company"
        location = location_el.get_text(strip=True) if location_el else "Unknown Location"
        salary_text = salary_el.get_text(strip=True) if salary_el else None

        # Build job link
        job_id_el = card.get("data-jk") or (card.select_one("a[data-jk]") or {}).get("data-jk")
        link = f"https://www.indeed.com/viewjob?jk={job_id_el}" if job_id_el else ""

        if not title or title == "Unknown Title":
            return None

        return {
            "id": self._make_id(title, company, location),
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
        # Filter out non-salary snippets
        salary_indicators = ["$", "lkr", "rs.", "per", "hour", "month", "year", "salary", "pay"]
        if any(ind in text.lower() for ind in salary_indicators):
            return text.strip()
        return None

    def _detect_work_type(self, location: str, title: str) -> str:
        combined = (location + " " + title).lower()
        if "remote" in combined:
            return "Remote"
        if "hybrid" in combined:
            return "Hybrid"
        return "On-site"

    def _make_id(self, title: str, company: str, location: str) -> str:
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{location.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _dedupe(self, jobs: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for job in jobs:
            if job["id"] not in seen:
                seen.add(job["id"])
                unique.append(job)
        return unique
