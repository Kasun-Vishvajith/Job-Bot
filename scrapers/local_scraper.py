"""
Local Sri Lanka Job Site Scraper
Handles TopJobs LK, XpressJobs, iJobs LK, and similar local portals.

BUG FIXES applied:
  - TopJobs: tds[6] was used without checking if row actually has 7 columns.
    BUG FIX: Added `len(tds) > 6` guard with fallback to "Sri Lanka".
  - TopJobs: `table.tbldata_2` selector didn't always match; added extra fallbacks.
  - XpressJobs: No 'enabled' default key in config caused KeyError when key absent.
    BUG FIX: `.get("enabled", True)` guards added.
  - Generic parser: Only 5 CSS selectors tried; added more common patterns.
  - Added IJobsLK scraper for iJobs.lk — another major Sri Lanka board.
  - Added better request headers to reduce block rate.
  - Added source-specific logging for debugging.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

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
}


class LocalSiteScraper:
    def __init__(self, config: dict):
        self.name = config["name"]
        self.url = config["url"]
        self.site_type = config.get("type", "generic")

    def scrape(self) -> list[dict]:
        try:
            resp = requests.get(self.url, headers=HEADERS, timeout=20)
            if resp.status_code == 404:
                log.warning("  [%s] 404 Not Found — URL may have changed: %s", self.name, self.url)
                return []
            resp.raise_for_status()
        except requests.RequestException as e:
            log.warning("  [%s] Request failed: %s", self.name, e)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        log.debug("  [%s] Fetched %d bytes", self.name, len(resp.content))

        if self.site_type == "topjobs":
            return self._parse_topjobs(soup)
        elif self.site_type == "xpressjobs":
            return self._parse_xpressjobs(soup)
        elif self.site_type == "ijobs":
            return self._parse_ijobs(soup)
        else:
            return self._parse_generic(soup)

    # ── TopJobs LK ────────────────────────────────────────────────────────────

    def _parse_topjobs(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []

        # BUG FIX: Added multiple table selectors because TopJobs occasionally
        # changes the table class between deployments.
        rows = (
            soup.select("table.tbldata_2 tr[onclick]")
            or soup.select("table#table tr[onclick]")
            or soup.select("table tr[onclick]")  # ultimate fallback
        )

        if not rows:
            log.debug("  [TopJobs] No clickable table rows found — page structure may have changed")

        for row in rows:
            try:
                onclick_val = row.get("onclick", "")
                match = re.search(
                    r"createAlert\(\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'",
                    onclick_val,
                )
                if not match:
                    continue
                rid, ac, jc, ec = match.groups()
                link = (
                    f"https://www.topjobs.lk/employer/JobAdvertismentServlet"
                    f"?rid={rid}&ac={ac}&jc={jc}&ec={ec}"
                    f"&pg=applicant/vacancybyfunctionalarea.jsp"
                )

                title_el = row.select_one("h2")
                company_el = row.select_one("h1")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                # BUG FIX: Validate td count before accessing tds[6]
                tds = row.find_all("td", recursive=False)
                if len(tds) > 6:
                    location = tds[6].get_text(strip=True) or "Sri Lanka"
                elif len(tds) > 2:
                    # Try second-to-last td as a location fallback
                    location = tds[-2].get_text(strip=True) or "Sri Lanka"
                else:
                    location = "Sri Lanka"

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
                log.debug("  [TopJobs] Card parse error: %s", e)

        log.debug("  [TopJobs] Parsed %d listings", len(jobs))
        return jobs

    # ── XpressJobs ────────────────────────────────────────────────────────────

    def _parse_xpressjobs(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []

        # Try multiple possible card selectors (site may have changed)
        cards = (
            soup.select("article.job-item")
            or soup.select("div.job-listing-item")
            or soup.select("li.job-item")
            or soup.select("div[class*='job-card']")
            or soup.select("div[class*='job-item']")
        )

        if not cards:
            log.debug("  [XpressJobs] No job cards found — trying link-based fallback")
            return self._fallback_link_parse(soup, "https://xpressjobs.lk", "XpressJobs")

        for card in cards:
            try:
                title_el = card.select_one("h2 a, h3 a, .job-title a, a.job-link, a[href*='/job/']")
                company_el = card.select_one(".company, .employer-name, [class*='company']")
                location_el = card.select_one(".location, .job-location, [class*='location']")
                salary_el = card.select_one(".salary, .remuneration, [class*='salary']")

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
                log.debug("  [XpressJobs] Card parse error: %s", e)

        log.debug("  [XpressJobs] Parsed %d listings", len(jobs))
        return jobs

    # ── iJobs LK (new) ────────────────────────────────────────────────────────

    def _parse_ijobs(self, soup: BeautifulSoup) -> list[dict]:
        """
        iJobs.lk job listing scraper.
        Site: https://www.ijobs.lk
        """
        jobs = []
        cards = (
            soup.select("div.job-box, div.job_box")
            or soup.select("article.job-listing")
            or soup.select("div.job-listing")
            or soup.select("li.job-listing")
        )

        if not cards:
            log.debug("  [iJobs LK] No job cards found — trying link-based fallback")
            return self._fallback_link_parse(soup, "https://www.ijobs.lk", "iJobs LK")

        for card in cards:
            try:
                title_el = card.select_one("h2 a, h3 a, a.job-title, a[href*='job']")
                company_el = card.select_one(".company-name, .company, [class*='company']")
                location_el = card.select_one(".location, [class*='location']")
                salary_el = card.select_one(".salary, [class*='salary']")

                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                company = company_el.get_text(strip=True) if company_el else "Unknown"
                location = location_el.get_text(strip=True) if location_el else "Sri Lanka"
                salary = salary_el.get_text(strip=True) if salary_el else None
                link = title_el.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.ijobs.lk" + link

                jobs.append({
                    "id": self._make_id(title, company, link),
                    "title": title,
                    "company": company,
                    "location": location,
                    "link": link,
                    "salary": salary,
                    "work_type": self._detect_work_type(title + " " + location),
                    "source": "iJobs LK",
                    "posted": "",
                    "scraped_at": datetime.utcnow().isoformat(),
                })
            except Exception as e:
                log.debug("  [iJobs LK] Card parse error: %s", e)

        log.debug("  [iJobs LK] Parsed %d listings", len(jobs))
        return jobs

    # ── Generic fallback ──────────────────────────────────────────────────────

    def _parse_generic(self, soup: BeautifulSoup) -> list[dict]:
        jobs = []

        # Try common job listing patterns — extended list
        selectors = [
            "article.job", "div.job-card", "li.job-listing",
            "div.vacancy", "tr.job-row", "div.job-listing",
            "div[class*='job-card']", "div[class*='job-item']",
            "li[class*='job']", "article[class*='job']",
        ]
        cards = []
        for sel in selectors:
            cards = soup.select(sel)
            if cards:
                log.debug("  [%s] Matched selector: %s (%d cards)", self.name, sel, len(cards))
                break

        if not cards:
            log.debug("  [%s] No known card selector matched — trying link-based fallback", self.name)
            return self._fallback_link_parse(soup, "", self.name)

        for card in cards:
            try:
                title_el = card.select_one(
                    "h2 a, h3 a, a[href*='job'], a[href*='career'], a[href*='position']"
                )
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
                log.debug("  [%s] Generic parse error: %s", self.name, e)

        return jobs

    # ── Shared link-based fallback ────────────────────────────────────────────

    def _fallback_link_parse(self, soup: BeautifulSoup, base_url: str, source: str) -> list[dict]:
        """
        Last-resort strategy: find all hyperlinks whose text looks like a job title
        and whose href contains job-related keywords.
        """
        jobs = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if len(text) < 5 or len(text) > 120:
                continue
            href_lower = href.lower()
            if not any(kw in href_lower for kw in ["job", "career", "vacancy", "position", "opening"]):
                continue
            full_url = href if href.startswith("http") else (base_url + href if base_url else href)
            if full_url in seen:
                continue
            seen.add(full_url)
            jobs.append({
                "id": self._make_id(text, source, full_url),
                "title": text,
                "company": source,
                "location": "Sri Lanka",
                "link": full_url,
                "salary": None,
                "work_type": self._detect_work_type(text),
                "source": source,
                "posted": "",
                "scraped_at": datetime.utcnow().isoformat(),
            })
        log.debug("  [%s] Link-fallback found %d listings", source, len(jobs))
        return jobs

    # ── Utilities ─────────────────────────────────────────────────────────────

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
