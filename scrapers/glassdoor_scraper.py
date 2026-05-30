"""
Glassdoor Job Scraper
Scrapes Glassdoor job listings via their public job search page.
Glassdoor uses JavaScript-rendered content; this scraper targets the
server-side rendered fragments and embedded JSON data.
"""

import hashlib
import json
import logging
import re
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
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.glassdoor.com",
}

GLASSDOOR_BASE = "https://www.glassdoor.com/Job/jobs.htm"


class GlassdoorScraper:
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

            log.info("  [Glassdoor] Searching: '%s' in '%s'", query, location or "any")
            for page in range(self.max_pages):
                params = {
                    "sc.keyword": query,
                    "locT": "N",
                    "locId": "1",
                    "jobType": "",
                    "fromAge": "7",
                    "p": page + 1,
                }
                if location:
                    params["sc.location"] = location

                url = GLASSDOOR_BASE + "?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())
                page_jobs = self._scrape_page(url, location)
                jobs.extend(page_jobs)
                log.debug("  [Glassdoor] Page %d: %d listings", page + 1, len(page_jobs))
                if len(page_jobs) < 5:
                    break
                time.sleep(random.uniform(2, 4))

        return self._dedupe(jobs)

    def _scrape_page(self, url: str, location: str) -> list[dict]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("  [Glassdoor] Request failed: %s", e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find embedded JSON data (Glassdoor embeds job data in script tags)
        jobs = self._extract_from_json(soup)
        if jobs:
            return jobs

        # Fallback: parse HTML cards
        return self._extract_from_html(soup, location)

    def _extract_from_json(self, soup: BeautifulSoup) -> list[dict]:
        """Attempt to extract job data from embedded __NEXT_DATA__ or Apollo JSON."""
        jobs = []
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "")
                # Look for job list arrays
                raw = json.dumps(data)
                if "jobTitle" in raw or "jobListings" in raw:
                    listings = self._dig_listings(data)
                    for item in listings:
                        job = self._parse_json_listing(item)
                        if job:
                            jobs.append(job)
                if jobs:
                    return jobs
            except Exception:
                continue
        return jobs

    def _dig_listings(self, obj, depth=0) -> list:
        """Recursively search for job listing arrays inside a nested dict/list."""
        if depth > 8:
            return []
        results = []
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and "jobTitle" in item:
                    results.append(item)
                else:
                    results.extend(self._dig_listings(item, depth + 1))
        elif isinstance(obj, dict):
            for v in obj.values():
                results.extend(self._dig_listings(v, depth + 1))
        return results

    def _parse_json_listing(self, item: dict) -> Optional[dict]:
        title = item.get("jobTitle") or item.get("title", "")
        company = item.get("employerName") or item.get("company", "")
        location = item.get("location") or item.get("locationName", "Remote")
        link = item.get("jobViewUrl") or item.get("url", "")
        salary = item.get("salaryText") or item.get("estimatedSalaryRange", None)
        posted = item.get("listedDate") or item.get("postingDateText", "")

        if not title or not company:
            return None

        if link and not link.startswith("http"):
            link = "https://www.glassdoor.com" + link

        return {
            "id": self._make_id(title, company, link),
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "salary": str(salary) if salary else None,
            "work_type": self._detect_work_type(location + " " + title),
            "source": "Glassdoor",
            "posted": str(posted),
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _extract_from_html(self, soup: BeautifulSoup, location: str) -> list[dict]:
        """Fallback HTML parser for Glassdoor job cards."""
        jobs = []
        # Glassdoor uses various class names; try them all
        cards = (
            soup.select("li[data-test='jobListing']")
            or soup.select("article.job-listing")
            or soup.select("li.react-job-listing")
            or soup.select("div[data-id]")
        )
        for card in cards:
            try:
                title_el = (
                    card.select_one("[data-test='job-link']")
                    or card.select_one("a.jobLink")
                    or card.select_one("a[class*='job-title']")
                )
                company_el = (
                    card.select_one("[data-test='employer-name']")
                    or card.select_one("div.employer-name")
                )
                location_el = (
                    card.select_one("[data-test='emp-location']")
                    or card.select_one("span.location")
                )
                salary_el = card.select_one("[data-test='detailSalary'], .salary-estimate")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown Company"
                loc = location_el.get_text(strip=True) if location_el else (location or "Unknown Location")
                salary = salary_el.get_text(strip=True) if salary_el else None

                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.glassdoor.com" + href

                if not title or len(title) < 3:
                    continue

                jobs.append({
                    "id": self._make_id(title, company, href),
                    "title": title,
                    "company": company,
                    "location": loc,
                    "link": href,
                    "salary": salary,
                    "work_type": self._detect_work_type(loc + " " + title),
                    "source": "Glassdoor",
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("  [Glassdoor] Card parse error: %s", e)
        return jobs

    def _detect_work_type(self, text: str) -> str:
        t = text.lower()
        if "remote" in t or "work from home" in t or "wfh" in t:
            return "Remote"
        if "hybrid" in t:
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
