"""
Company Career Page Scraper
Generic scraper for individual company career pages.
Uses smart heuristics to find job listings regardless of site structure.
"""

import hashlib
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

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
}

# Common patterns for job listing elements
TITLE_SELECTORS = [
    "h1.job-title", "h2.job-title", "h3.job-title",
    ".position-title", ".role-title", ".opening-title",
    "a.job-title", "a.position-title",
    "[data-job-title]", "[class*='job-title']", "[class*='position']",
]

CARD_SELECTORS = [
    "div.job", "div.position", "div.opening", "div.role",
    "li.job", "li.position", "li.opening",
    "tr.job", "article.job", "article.position",
    "[class*='job-card']", "[class*='job-item']", "[class*='position-item']",
]

SALARY_SELECTORS = [
    ".salary", ".compensation", ".pay", ".remuneration",
    "[class*='salary']", "[class*='compensation']",
]

LOCATION_SELECTORS = [
    ".location", ".job-location", ".office",
    "[class*='location']", "[data-location]",
]


class CompanyScraper:
    def __init__(self, config: dict):
        self.company_name = config["name"]
        self.url = config["url"]
        self.keywords = [kw.lower() for kw in config.get("keywords", [])]
        self.base_url = self._get_base_url(self.url)
        self.default_location = config.get("default_location", "See listing")

    def _get_base_url(self, url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def scrape(self) -> list[dict]:
        try:
            resp = requests.get(self.url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("[%s] Request failed: %s", self.company_name, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = self._extract_jobs(soup)

        # Filter by company-specific keywords
        if self.keywords:
            jobs = [
                j for j in jobs
                if any(kw in (j["title"] + j["location"]).lower() for kw in self.keywords)
            ]

        return jobs

    def _extract_jobs(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []

        # Strategy 1: Try known card selectors
        cards = []
        for sel in CARD_SELECTORS:
            cards = soup.select(sel)
            if len(cards) >= 2:
                break

        if cards:
            for card in cards:
                job = self._parse_card(card)
                if job:
                    jobs.append(job)
            if jobs:
                return jobs

        # Strategy 2: Find all job-like links on the page
        all_links = soup.find_all("a", href=True)
        job_links = [
            a for a in all_links
            if any(kw in (a.get("href", "") + a.get_text()).lower()
                   for kw in ["job", "career", "position", "opening", "role", "vacancy"])
            and len(a.get_text(strip=True)) > 5
        ]

        seen_links = set()
        for link_el in job_links:
            try:
                title = link_el.get_text(strip=True)
                href = link_el.get("href", "")
                full_url = urljoin(self.base_url, href)

                if full_url in seen_links or not title:
                    continue
                seen_links.add(full_url)

                # Find nearby location/salary in parent
                parent = link_el.parent
                location = self.default_location
                salary = None
                if parent:
                    loc_el = parent.select_one(", ".join(LOCATION_SELECTORS))
                    sal_el = parent.select_one(", ".join(SALARY_SELECTORS))
                    if loc_el:
                        location = loc_el.get_text(strip=True)
                    if sal_el:
                        salary = sal_el.get_text(strip=True)

                jobs.append({
                    "id": self._make_id(title, self.company_name, full_url),
                    "title": title,
                    "company": self.company_name,
                    "location": location,
                    "link": full_url,
                    "salary": salary,
                    "work_type": self._detect_work_type(title + " " + location),
                    "source": self.company_name,
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("Link parse error: %s", e)

        return jobs

    def _parse_card(self, card) -> Optional[dict]:
        # Title
        title_el = None
        for sel in TITLE_SELECTORS:
            title_el = card.select_one(sel)
            if title_el:
                break
        if not title_el:
            title_el = card.select_one("a") or card.select_one("h2") or card.select_one("h3")

        if not title_el:
            return None

        title = title_el.get_text(strip=True)
        if not title or len(title) < 3:
            return None

        # Link
        link_el = card.select_one("a[href]")
        link = ""
        if link_el:
            href = link_el.get("href", "")
            link = urljoin(self.base_url, href)

        # Location
        location = self.default_location
        for sel in LOCATION_SELECTORS:
            loc_el = card.select_one(sel)
            if loc_el:
                location = loc_el.get_text(strip=True)
                break

        # Salary
        salary = None
        for sel in SALARY_SELECTORS:
            sal_el = card.select_one(sel)
            if sal_el:
                salary = sal_el.get_text(strip=True)
                break

        return {
            "id": self._make_id(title, self.company_name, link),
            "title": title,
            "company": self.company_name,
            "location": location,
            "link": link,
            "salary": salary,
            "work_type": self._detect_work_type(title + " " + location),
            "source": self.company_name,
            "posted": "",
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _detect_work_type(self, text: str) -> str:
        text_lower = text.lower()
        if "remote" in text_lower or "work from home" in text_lower:
            return "Remote"
        if "hybrid" in text_lower:
            return "Hybrid"
        return "On-site"

    def _make_id(self, title: str, company: str, link: str) -> str:
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{link}"
        return hashlib.md5(raw.encode()).hexdigest()
