"""
Local Sri Lanka Job Site Scraper
Handles TopJobs LK, XpressJobs, and similar local portals.
"""

import hashlib
import logging
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
}


class LocalSiteScraper:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.url = config["url"]
        self.site_type = config.get("type", "generic")

    def scrape(self) -> list[dict]:
        try:
            resp = requests.get(self.url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("[%s] Request failed: %s", self.name, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        if self.site_type == "topjobs":
            return self._parse_topjobs(soup)
        elif self.site_type == "xpressjobs":
            return self._parse_xpressjobs(soup)
        else:
            return self._parse_generic(soup)

    # ── TopJobs LK ────────────────────────────────────────────────────────────
    def _parse_topjobs(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []
        cards = soup.select("table.job-listing tr, div.vacancy-item, li.vacancy")

        for card in cards:
            try:
                title_el = card.select_one("a.jobtitle, a[href*='vacancy'], .job-title")
                company_el = card.select_one(".company-name, .employer")
                location_el = card.select_one(".location, .city")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = location_el.get_text(strip=True) if location_el else "Sri Lanka"
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.topjobs.lk" + link

                jobs.append({
                    "id": self._make_id(title, company, link),
                    "title": title,
                    "company": company,
                    "location": location or "Sri Lanka",
                    "link": link,
                    "salary": None,
                    "work_type": self._detect_work_type(title + " " + location),
                    "source": "TopJobs LK",
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("TopJobs card parse error: %s", e)

        return jobs

    # ── XpressJobs ────────────────────────────────────────────────────────────
    def _parse_xpressjobs(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []
        cards = soup.select("article.job-item, div.job-listing-item, li.job-item")

        for card in cards:
            try:
                title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link")
                company_el = card.select_one(".company, .employer-name")
                location_el = card.select_one(".location, .job-location")
                salary_el = card.select_one(".salary, .remuneration")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = location_el.get_text(strip=True) if location_el else "Sri Lanka"
                salary = salary_el.get_text(strip=True) if salary_el else None
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://xpressjobs.lk" + link

                jobs.append({
                    "id": self._make_id(title, company, link),
                    "title": title,
                    "company": company,
                    "location": location,
                    "link": link,
                    "salary": salary,
                    "work_type": self._detect_work_type(title + " " + location),
                    "source": "XpressJobs",
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("XpressJobs card parse error: %s", e)

        return jobs

    # ── Generic fallback ──────────────────────────────────────────────────────
    def _parse_generic(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []
        # Try common job listing patterns
        selectors = [
            "article.job", "div.job-card", "li.job-listing",
            "div.vacancy", "tr.job-row",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                break

        for card in cards:
            try:
                title_el = card.select_one("h2 a, h3 a, a[href*='job'], a[href*='career']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                link = title_el.get("href", "")

                jobs.append({
                    "id": self._make_id(title, self.name, link),
                    "title": title,
                    "company": self.name,
                    "location": "Sri Lanka",
                    "link": link,
                    "salary": None,
                    "work_type": self._detect_work_type(title),
                    "source": self.name,
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("Generic parse error: %s", e)

        return jobs

    def _detect_work_type(self, text: str) -> str:
        text_lower = text.lower()
        if "remote" in text_lower or "work from home" in text_lower or "wfh" in text_lower:
            return "Remote"
        if "hybrid" in text_lower:
            return "Hybrid"
        return "On-site"

    def _make_id(self, title: str, company: str, link: str) -> str:
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{link}"
        return hashlib.md5(raw.encode()).hexdigest()
