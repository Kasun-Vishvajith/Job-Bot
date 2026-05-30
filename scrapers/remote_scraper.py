"""
Remote job board scrapers.

These sources are intentionally separate from LinkedIn/Indeed because many
remote-first boards expose APIs or stable listing pages that are less likely to
block GitHub Actions runners.
"""

import hashlib
import logging
from datetime import datetime
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class RemoteJobBoardScraper:
    def __init__(self, config: dict):
        self.config = config
        self.sources = config.get("sources", [])
        self.search_terms = config.get("search_terms", [])
        self.max_results_per_source = config.get("max_results_per_source", 80)

    def scrape(self) -> list[dict]:
        jobs: list[dict] = []
        for source in self.sources:
            if not source.get("enabled", True):
                continue

            source_type = source.get("type", "").lower()
            try:
                if source_type == "remotive":
                    jobs.extend(self._scrape_remotive(source))
                elif source_type == "arbeitnow":
                    jobs.extend(self._scrape_arbeitnow(source))
                elif source_type == "remoteok":
                    jobs.extend(self._scrape_remoteok(source))
                elif source_type == "weworkremotely":
                    jobs.extend(self._scrape_weworkremotely(source))
                elif source_type == "remote_co":
                    jobs.extend(self._scrape_remote_co(source))
                else:
                    log.warning("Unknown remote job board type: %s", source_type)
            except Exception as exc:
                log.warning("[%s] remote board failed: %s", source.get("name", source_type), exc)

        return self._dedupe(jobs)

    def _scrape_remotive(self, source: dict) -> list[dict]:
        jobs = []
        for term in self.search_terms:
            url = f"https://remotive.com/api/remote-jobs?search={requests.utils.quote(term)}"
            data = self._get_json(url)
            for item in data.get("jobs", [])[: self.max_results_per_source]:
                jobs.append(
                    self._job(
                        title=item.get("title"),
                        company=item.get("company_name"),
                        location=item.get("candidate_required_location") or "Worldwide",
                        link=item.get("url"),
                        source=source["name"],
                        salary=item.get("salary"),
                        description=item.get("description", ""),
                        posted=item.get("publication_date", ""),
                    )
                )
        return jobs

    def _scrape_arbeitnow(self, source: dict) -> list[dict]:
        url = "https://www.arbeitnow.com/api/job-board-api?remote=true"
        data = self._get_json(url)
        jobs = []
        for item in data.get("data", [])[: self.max_results_per_source]:
            text = " ".join(
                str(x or "")
                for x in [item.get("title"), item.get("company_name"), item.get("description"), item.get("location")]
            ).lower()
            if self.search_terms and not any(term.lower() in text for term in self.search_terms):
                continue
            jobs.append(
                self._job(
                    title=item.get("title"),
                    company=item.get("company_name"),
                    location=item.get("location") or "Remote",
                    link=item.get("url"),
                    source=source["name"],
                    description=item.get("description", ""),
                    posted=str(item.get("created_at") or ""),
                )
            )
        return jobs

    def _scrape_remoteok(self, source: dict) -> list[dict]:
        data = self._get_json("https://remoteok.com/api")
        jobs = []
        for item in data[: self.max_results_per_source]:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            tags = " ".join(self._string_list(item.get("tags", [])))
            text = f"{item.get('position', '')} {item.get('company', '')} {tags} {item.get('description', '')}".lower()
            if self.search_terms and not any(term.lower() in text for term in self.search_terms):
                continue
            jobs.append(
                self._job(
                    title=item.get("position"),
                    company=item.get("company"),
                    location=item.get("location") or "Worldwide",
                    link=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id', '')}",
                    source=source["name"],
                    salary=self._format_remoteok_salary(item),
                    description=item.get("description", ""),
                    posted=item.get("date", ""),
                )
            )
        return jobs

    def _scrape_weworkremotely(self, source: dict) -> list[dict]:
        jobs = []
        for term in self.search_terms:
            url = f"https://weworkremotely.com/remote-jobs/search?term={requests.utils.quote(term)}"
            soup = self._get_soup(url)
            for card in soup.select("li.feature, li.new-listing-container")[: self.max_results_per_source]:
                title_el = card.select_one(".new-listing__header__title, span.title")
                company_el = card.select_one(".new-listing__company-name, span.company")
                region_el = card.select_one(".new-listing__company-headquarters, span.region")
                link_el = card.select_one("a[href*='/remote-jobs/']")
                if not title_el or not link_el:
                    continue
                jobs.append(
                    self._job(
                        title=title_el.get_text(" ", strip=True),
                        company=company_el.get_text(" ", strip=True) if company_el else "Unknown Company",
                        location=region_el.get_text(" ", strip=True) if region_el else "Worldwide",
                        link=urljoin("https://weworkremotely.com", link_el.get("href", "")),
                        source=source["name"],
                    )
                )
        return jobs

    def _scrape_remote_co(self, source: dict) -> list[dict]:
        jobs = []
        for term in self.search_terms:
            url = f"https://remote.co/remote-jobs/search/?search_keywords={requests.utils.quote(term)}"
            soup = self._get_soup(url)
            for card in soup.select("div.card, div.job_listing, li.job_listing")[: self.max_results_per_source]:
                title_el = card.select_one("a.card-title, h3 a, a[href*='remote-jobs']")
                company_el = card.select_one(".company, .m-0, p")
                location_el = card.select_one(".location, .badge, small")
                if not title_el:
                    continue
                title = title_el.get_text(" ", strip=True)
                if len(title) < 4:
                    continue
                jobs.append(
                    self._job(
                        title=title,
                        company=company_el.get_text(" ", strip=True) if company_el else "Remote.co",
                        location=location_el.get_text(" ", strip=True) if location_el else "Remote",
                        link=urljoin("https://remote.co", title_el.get("href", "")),
                        source=source["name"],
                    )
                )
        return jobs

    def _get_json(self, url: str) -> dict | list:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _get_soup(self, url: str) -> BeautifulSoup:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")

    def _job(
        self,
        title: Optional[str],
        company: Optional[str],
        location: Optional[str],
        link: Optional[str],
        source: str,
        salary: Optional[str] = None,
        description: str = "",
        posted: str = "",
    ) -> dict:
        title = (title or "Unknown Title").strip()
        company = (company or "Unknown Company").strip()
        location = (location or "Remote").strip()
        link = (link or "").strip()
        return {
            "id": self._make_id(title, company, link or location),
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "salary": salary,
            "work_type": "Remote",
            "source": source,
            "posted": posted,
            "description": BeautifulSoup(description or "", "html.parser").get_text(" ", strip=True),
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _format_remoteok_salary(self, item: dict) -> Optional[str]:
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        if not salary_min and not salary_max:
            return None
        if salary_min and salary_max:
            return f"${salary_min:,} - ${salary_max:,}"
        return f"${salary_min or salary_max:,}"

    def _make_id(self, title: str, company: str, link: str) -> str:
        raw = f"{title.lower().strip()}-{company.lower().strip()}-{link}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _dedupe(self, jobs: Iterable[dict]) -> list[dict]:
        seen = set()
        unique = []
        for job in jobs:
            if not job.get("title") or job["title"] == "Unknown Title":
                continue
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            unique.append(job)
        return unique

    def _string_list(self, values: Iterable) -> list[str]:
        return [str(value) for value in values if value is not None]
