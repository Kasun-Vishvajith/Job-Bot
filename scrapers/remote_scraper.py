"""
Remote job board scrapers.

These sources are intentionally separate from LinkedIn/Indeed because many
remote-first boards expose APIs or stable listing pages that are less likely to
block GitHub Actions runners.

BUG FIXES applied:
  - _scrape_remoteok: data[0] is a metadata dict, must be skipped — now skipped.
  - _scrape_remote_co: selector `div.card` matches too broadly; refined selectors.
  - _format_remoteok_salary: salary_min/max may be str/int; added safe int cast.
  - _get_json: no error handling; added detailed logging + raise.
  - Added User-Agent rotation to reduce block probability.
  - Added time.sleep between search-term iterations to avoid rate limits.
  - Added new sources: Jobicy, HiringCafe, Greenhouse (public jobs API).
"""

import hashlib
import logging
import time
import random
import re
from datetime import datetime
from typing import Iterable, Optional
from urllib.parse import quote, urljoin

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


def _headers() -> dict:
    """Return headers with a randomly chosen User-Agent."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


class RemoteJobBoardScraper:
    def __init__(self, config: dict):
        self.config = config
        self.sources = config.get("sources", [])
        self.search_terms = config.get("search_terms", [])
        self.max_results_per_source = config.get("max_results_per_source", 80)
        self.request_timeout = config.get("request_timeout_seconds", 15)
        self.match_keywords = [
            value.lower() for value in config.get("match_keywords", []) if value
        ]

    def scrape(self) -> list[dict]:
        jobs: list[dict] = []
        for source in self.sources:
            if not source.get("enabled", True):
                continue

            source_type = source.get("type", "").lower()
            name = source.get("name", source_type)
            try:
                if source_type == "remotive":
                    fetched = self._scrape_remotive(source)
                elif source_type == "arbeitnow":
                    fetched = self._scrape_arbeitnow(source)
                elif source_type == "remoteok":
                    fetched = self._scrape_remoteok(source)
                elif source_type == "weworkremotely":
                    fetched = self._scrape_weworkremotely(source)
                elif source_type == "remote_co":
                    fetched = self._scrape_remote_co(source)
                elif source_type == "jobicy":
                    fetched = self._scrape_jobicy(source)
                elif source_type == "hiringcafe":
                    fetched = self._scrape_hiringcafe(source)
                elif source_type == "greenhouse":
                    fetched = self._scrape_greenhouse(source)
                elif source_type == "lever":
                    fetched = self._scrape_lever(source)
                elif source_type == "ashby":
                    fetched = self._scrape_ashby(source)
                elif source_type == "rss":
                    fetched = self._scrape_rss(source)
                elif source_type == "theirstack":
                    fetched = self._scrape_theirstack(source)
                elif source_type == "himalayas":
                    fetched = self._scrape_himalayas(source)
                elif source_type == "justremote":
                    fetched = self._scrape_justremote(source)
                elif source_type == "dailyremote":
                    fetched = self._scrape_dailyremote(source)
                else:
                    log.warning("Unknown remote job board type: %s", source_type)
                    continue

                log.info("  [%s] fetched %d listings", name, len(fetched))
                jobs.extend(fetched)

            except Exception as exc:
                log.warning("  [%s] remote board failed: %s", name, exc)

        return self._dedupe(jobs)

    # ── Remotive ──────────────────────────────────────────────────────────────

    def _scrape_remotive(self, source: dict) -> list[dict]:
        """
        Remotive API: https://remotive.com/api/remote-jobs?search=<term>
        Returns JSON with {"jobs": [...]}
        """
        jobs = []
        data = self._get_json(
            f"https://remotive.com/api/remote-jobs?limit={self.max_results_per_source}"
        )
        for item in data.get("jobs", [])[: self.max_results_per_source]:
            if self._matches(item.get("title"), item.get("description")):
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

    # ── Arbeitnow ─────────────────────────────────────────────────────────────

    def _scrape_arbeitnow(self, source: dict) -> list[dict]:
        """
        Arbeitnow API: https://www.arbeitnow.com/api/job-board-api?remote=true
        Free public JSON API, no auth required.
        """
        url = "https://www.arbeitnow.com/api/job-board-api?remote=true"
        try:
            data = self._get_json(url)
        except Exception as e:
            log.warning("  [Arbeitnow] API call failed: %s", e)
            return []

        jobs = []
        for item in data.get("data", [])[: self.max_results_per_source]:
            text = " ".join(
                str(x or "")
                for x in [
                    item.get("title"),
                    item.get("company_name"),
                    item.get("description"),
                    item.get("location"),
                ]
            ).lower()
            if not self._matches(text):
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

    # ── RemoteOK ──────────────────────────────────────────────────────────────

    def _scrape_remoteok(self, source: dict) -> list[dict]:
        """
        RemoteOK API: https://remoteok.com/api
        Returns a JSON array. IMPORTANT: index 0 is a metadata/legal object,
        NOT a job. Skip it. Each real job has a "position" key.
        BUG FIX: Previous version didn't skip index 0, causing KeyError noise.
        """
        try:
            data = self._get_json("https://remoteok.com/api")
        except Exception as e:
            log.warning("  [RemoteOK] API call failed: %s", e)
            return []

        jobs = []
        # Skip index 0 — it is always the legal/meta object, not a job listing
        for item in data[1:][: self.max_results_per_source]:
            if not isinstance(item, dict) or not item.get("position"):
                continue
            tags = " ".join(self._string_list(item.get("tags", [])))
            text = (
                f"{item.get('position', '')} {item.get('company', '')} "
                f"{tags} {item.get('description', '')}"
            ).lower()
            if not self._matches(text):
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

    # ── We Work Remotely ──────────────────────────────────────────────────────

    def _scrape_weworkremotely(self, source: dict) -> list[dict]:
        """
        We Work Remotely search: https://weworkremotely.com/remote-jobs/search?term=<query>
        BUG FIX: Adds 1s delay between terms to avoid 429 rate-limiting.
        """
        jobs = []
        for i, term in enumerate(self.search_terms):
            if i > 0:
                time.sleep(random.uniform(1.0, 2.0))
            url = f"https://weworkremotely.com/remote-jobs/search?term={requests.utils.quote(term)}"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [WWR] Failed for term '%s': %s", term, e)
                continue

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

    # ── Remote.co ─────────────────────────────────────────────────────────────

    def _scrape_remote_co(self, source: dict) -> list[dict]:
        """
        Remote.co job search.
        BUG FIX: 'div.card' was matching non-job cards. Refined to target
        specific job listing selectors only.
        """
        jobs = []
        for i, term in enumerate(self.search_terms):
            if i > 0:
                time.sleep(random.uniform(1.0, 2.0))
            url = f"https://remote.co/remote-jobs/search/?search_keywords={requests.utils.quote(term)}"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [Remote.co] Failed for term '%s': %s", term, e)
                continue

            # BUG FIX: More specific selectors — avoid pulling in navigation cards
            cards = (
                soup.select("div.job_listing")
                or soup.select("li.job_listing")
                or soup.select("article[class*='job']")
                or soup.select("div[class*='job-card']")
            )

            for card in cards[: self.max_results_per_source]:
                # BUG FIX: avoid selecting company name as title (was caused by
                # `card.select_one(".m-0, p")` grabbing wrong element)
                title_el = card.select_one("a.card-title, h3 a, .position-title a, a[href*='remote-jobs']")
                company_el = card.select_one(".company_name, .company, strong.company")
                location_el = card.select_one(".location, .badge, .job_location")
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

    # ── Jobicy ────────────────────────────────────────────────────────────────

    def _scrape_jobicy(self, source: dict) -> list[dict]:
        """
        Jobicy API: https://jobicy.com/api/v2/remote-jobs?count=50&tag=<term>
        Free JSON API for remote jobs. No auth needed.
        """
        jobs = []
        data = self._get_json(
            f"https://jobicy.com/api/v2/remote-jobs?count={min(self.max_results_per_source, 200)}"
        )
        for item in data.get("jobs", [])[: self.max_results_per_source]:
            if self._matches(item.get("jobTitle"), item.get("jobDescription"), item.get("jobIndustry")):
                jobs.append(
                    self._job(
                        title=item.get("jobTitle"),
                        company=item.get("companyName"),
                        location=item.get("jobGeo") or "Worldwide",
                        link=item.get("url"),
                        source=source["name"],
                        salary=self._format_jobicy_salary(item),
                        description=item.get("jobDescription", ""),
                        posted=item.get("pubDate", ""),
                        employment_type=", ".join(self._string_list(item.get("jobType", []))),
                    )
                )
        return jobs

    # ── HiringCafe ────────────────────────────────────────────────────────────

    def _scrape_hiringcafe(self, source: dict) -> list[dict]:
        """
        HiringCafe: https://hiringcafe.com
        Scrapes their public search endpoint for remote jobs.
        """
        jobs = []
        for term in self.search_terms:
            url = f"https://hiring.cafe/?q={requests.utils.quote(term)}&remote=true"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [HiringCafe] Failed for term '%s': %s", term, e)
                continue

            cards = soup.select("div.job-card, article.job, li[class*='job']")[: self.max_results_per_source]
            for card in cards:
                title_el = card.select_one("h2 a, h3 a, a[class*='title']")
                company_el = card.select_one(".company, .employer, [class*='company']")
                location_el = card.select_one(".location, [class*='location']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://hiring.cafe" + href
                jobs.append(
                    self._job(
                        title=title,
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location=location_el.get_text(strip=True) if location_el else "Remote",
                        link=href,
                        source=source["name"],
                    )
                )
            time.sleep(random.uniform(0.5, 1.0))
        return jobs

    # ── Greenhouse public jobs board ──────────────────────────────────────────

    def _scrape_greenhouse(self, source: dict) -> list[dict]:
        """
        Greenhouse-hosted job boards for specific companies.
        Greenhouse exposes a public JSON API:
          GET https://boards-api.greenhouse.io/v1/boards/<company>/jobs?content=true
        Companies are listed in source["companies"] config key.
        """
        jobs = []
        companies = source.get("companies", [])
        if not companies:
            log.warning("  [Greenhouse] No companies configured — set source.companies in config.yaml")
            return []

        for company_slug in companies:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true"
            try:
                data = self._get_json(url)
            except Exception as e:
                log.warning("  [Greenhouse:%s] API call failed: %s", company_slug, e)
                continue

            for item in data.get("jobs", []):
                title = item.get("title", "")
                location = (item.get("location") or {}).get("name", "Remote")
                link = item.get("absolute_url", "")
                content = item.get("content", "")

                # Only include if job text matches any search term
                text = f"{title} {location} {content}".lower()
                if not self._matches(text):
                    continue

                jobs.append(
                    self._job(
                        title=title,
                        company=company_slug.replace("-", " ").title(),
                        location=location,
                        link=link,
                        source=source["name"],
                        description=content,
                        posted=item.get("updated_at", ""),
                        work_type=self._detect_work_type(location, content),
                    )
                )
        return jobs

    # ── Lever public postings API ────────────────────────────────────────────

    def _scrape_lever(self, source: dict) -> list[dict]:
        """Fetch each configured company once and filter its public postings locally."""
        jobs = []
        for company_slug in source.get("companies", []):
            url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
            try:
                data = self._get_json(url)
            except Exception as exc:
                log.warning("  [Lever:%s] API call failed: %s", company_slug, exc)
                continue
            if not isinstance(data, list):
                continue
            for item in data:
                categories = item.get("categories") or {}
                location = categories.get("location") or "Unknown"
                description = " ".join(
                    str(item.get(key) or "")
                    for key in ("descriptionPlain", "additionalPlain", "requirementsPlain")
                )
                if not self._matches(item.get("text"), categories, description):
                    continue
                jobs.append(self._job(
                    title=item.get("text"),
                    company=company_slug.replace("-", " ").title(),
                    location=location,
                    link=item.get("hostedUrl") or item.get("applyUrl"),
                    source=source["name"],
                    description=description,
                    posted=str(item.get("createdAt") or ""),
                    employment_type=categories.get("commitment") or "",
                    work_type=self._detect_work_type(location, description),
                ))
        return jobs

    # ── Ashby public job boards ─────────────────────────────────────────────

    def _scrape_ashby(self, source: dict) -> list[dict]:
        """Fetch configured employers through Ashby's public posting API."""
        jobs = []
        for company_slug in source.get("companies", []):
            encoded_slug = quote(company_slug, safe="")
            url = (
                "https://api.ashbyhq.com/posting-api/job-board/"
                f"{encoded_slug}?includeCompensation=true"
            )
            try:
                data = self._get_json(url)
            except Exception as exc:
                log.warning("  [Ashby:%s] API call failed: %s", company_slug, exc)
                continue

            for item in data.get("jobs", [])[: self.max_results_per_source]:
                title = item.get("title", "")
                location = item.get("location") or "Remote"
                description = item.get("descriptionPlain") or item.get("descriptionHtml") or ""
                if not self._matches(title, location, description):
                    continue
                jobs.append(self._job(
                    title=title,
                    company=company_slug.replace("-", " ").title(),
                    location=location,
                    link=item.get("jobUrl") or item.get("applyUrl"),
                    source=source["name"],
                    salary=self._format_ashby_salary(item.get("compensation")),
                    description=description,
                    posted=item.get("publishedAt", ""),
                    employment_type=item.get("employmentType", ""),
                    work_type="Remote" if item.get("isRemote") else self._detect_work_type(location, description),
                ))
        return jobs

    @staticmethod
    def _format_ashby_salary(compensation) -> Optional[str]:
        if not compensation:
            return None
        if isinstance(compensation, str):
            return compensation.strip() or None
        if isinstance(compensation, dict):
            for key in (
                "compensationTierSummary",
                "scrapeableCompensationSalarySummary",
                "summary",
                "description",
            ):
                if compensation.get(key):
                    return str(compensation[key]).strip()
        return None

    # ── RSS feeds ────────────────────────────────────────────────────────────

    def _scrape_rss(self, source: dict) -> list[dict]:
        """Read official RSS feeds with one request per configured category."""
        jobs = []
        for feed_url in source.get("feeds", []):
            try:
                soup = self._get_soup(feed_url, parser="xml")
            except Exception as exc:
                log.warning("  [RSS:%s] failed: %s", feed_url, exc)
                continue
            for item in soup.select("item"):
                title = self._rss_text(item, "title")
                description = self._rss_text(item, "description")
                categories = " ".join(el.get_text(" ", strip=True) for el in item.select("category"))
                if not self._matches(title, description, categories):
                    continue
                location = (
                    self._rss_text(item, "region")
                    or self._rss_text(item, "location")
                    or source.get("default_location", "Remote")
                )
                company = (
                    self._rss_text(item, "company")
                    or self._rss_text(item, "creator")
                    or source.get("default_company", source["name"])
                )
                jobs.append(self._job(
                    title=title,
                    company=company,
                    location=location,
                    link=self._rss_text(item, "link") or self._rss_text(item, "guid"),
                    source=source["name"],
                    salary=self._extract_salary(f"{title} {description}"),
                    description=description,
                    posted=self._rss_text(item, "pubDate") or self._rss_text(item, "date"),
                    employment_type=source.get("employment_type", "Full-time"),
                    work_type=source.get("work_type") or self._detect_work_type(location, description),
                ))
                if len(jobs) >= self.max_results_per_source:
                    return jobs
        return jobs

    # ── TheirStack (free tier) ────────────────────────────────────────────────

    def _scrape_theirstack(self, source: dict) -> list[dict]:
        """
        TheirStack: https://theirstack.com/en/jobs
        Simple HTML scraping of their public job listing pages.
        """
        jobs = []
        for term in self.search_terms:
            url = f"https://theirstack.com/en/jobs?search={requests.utils.quote(term)}&remote=true"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [TheirStack] Failed for term '%s': %s", term, e)
                continue

            for card in soup.select("div[class*='job-card'], li[class*='job'], article[class*='job']")[: self.max_results_per_source]:
                title_el = card.select_one("h2 a, h3 a, a[class*='title']")
                company_el = card.select_one("[class*='company'], [class*='employer']")
                location_el = card.select_one("[class*='location'], [class*='place']")
                if not title_el:
                    continue
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://theirstack.com" + href
                jobs.append(
                    self._job(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location=location_el.get_text(strip=True) if location_el else "Remote",
                        link=href,
                        source=source["name"],
                    )
                )
            time.sleep(random.uniform(0.5, 1.0))
        return jobs

    # ── Himalayas.app ──────────────────────────────────────────────────────────

    def _scrape_himalayas(self, source: dict) -> list[dict]:
        """
        Himalayas.app — 100% remote job board with a free JSON API.
        GET https://himalayas.app/jobs/api?limit=50&offset=0&q=<term>
        """
        jobs = []
        for term in self.search_terms:
            url = f"https://himalayas.app/jobs/api?limit=50&offset=0&q={requests.utils.quote(term)}"
            try:
                data = self._get_json(url)
            except Exception as e:
                log.warning("  [Himalayas] Failed for term '%s': %s", term, e)
                continue

            for item in data.get("jobs", [])[: self.max_results_per_source]:
                jobs.append(
                    self._job(
                        title=item.get("title"),
                        company=item.get("companyName") or item.get("company_name"),
                        location=item.get("location") or "Worldwide",
                        link=item.get("applicationLink") or item.get("url") or
                             f"https://himalayas.app/jobs/{item.get('slug', '')}",
                        source=source["name"],
                        salary=self._format_himalayas_salary(item),
                        description=item.get("description", ""),
                        posted=item.get("pubDate") or item.get("publishedAt", ""),
                    )
                )
            time.sleep(random.uniform(0.5, 1.0))
        return jobs

    def _format_himalayas_salary(self, item: dict):
        try:
            smin = int(item.get("salaryCurrencyMin") or item.get("minSalary") or 0)
            smax = int(item.get("salaryCurrencyMax") or item.get("maxSalary") or 0)
        except (ValueError, TypeError):
            return None
        if not smin and not smax:
            return None
        if smin and smax:
            return f"${smin:,} - ${smax:,}"
        return f"${smin or smax:,}"

    # ── JustRemote ─────────────────────────────────────────────────────────────

    def _scrape_justremote(self, source: dict) -> list[dict]:
        """
        JustRemote — 100% remote job board.
        Scrapes public search page: https://justremote.co/remote-jobs?search=<term>
        """
        jobs = []
        for i, term in enumerate(self.search_terms):
            if i > 0:
                time.sleep(random.uniform(1.0, 2.0))
            url = f"https://justremote.co/remote-jobs?search={requests.utils.quote(term)}"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [JustRemote] Failed for term '%s': %s", term, e)
                continue

            cards = soup.select(
                "div.job-card, div[class*='JobCard'], "
                "article[class*='job'], li[class*='job-listing']"
            )[: self.max_results_per_source]
            for card in cards:
                title_el = card.select_one("h3 a, h2 a, a[class*='title'], a[class*='job-link']")
                company_el = card.select_one(
                    "[class*='company'], [class*='employer'], span.company-name"
                )
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://justremote.co" + href
                jobs.append(
                    self._job(
                        title=title,
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location="Remote",
                        link=href,
                        source=source["name"],
                    )
                )
        return jobs

    # ── DailyRemote ────────────────────────────────────────────────────────────

    def _scrape_dailyremote(self, source: dict) -> list[dict]:
        """
        DailyRemote — 100% remote job board.
        Scrapes public search page: https://dailyremote.com/remote-jobs?search=<term>
        """
        jobs = []
        for i, term in enumerate(self.search_terms):
            if i > 0:
                time.sleep(random.uniform(1.0, 2.0))
            url = f"https://dailyremote.com/remote-jobs?search={requests.utils.quote(term)}"
            try:
                soup = self._get_soup(url)
            except Exception as e:
                log.warning("  [DailyRemote] Failed for term '%s': %s", term, e)
                continue

            cards = soup.select(
                "div.job-board-list, div[class*='job-item'], "
                "article[class*='job'], li[class*='job']"
            )[: self.max_results_per_source]
            for card in cards:
                title_el = card.select_one("h2 a, h3 a, a[class*='title'], a[class*='job-link']")
                company_el = card.select_one(
                    "[class*='company'], [class*='employer'], span.company"
                )
                location_el = card.select_one("[class*='location']")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://dailyremote.com" + href
                jobs.append(
                    self._job(
                        title=title,
                        company=company_el.get_text(strip=True) if company_el else "Unknown",
                        location=location_el.get_text(strip=True) if location_el else "Remote",
                        link=href,
                        source=source["name"],
                    )
                )
        return jobs

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _get_json(self, url: str) -> dict | list:
        """
        BUG FIX: Previous version had no error message on failure.
        Now logs the URL and response status on failure for easier debugging.
        """
        resp = requests.get(url, headers=_headers(), timeout=self.request_timeout)
        if resp.status_code != 200:
            log.warning("  HTTP %d for %s", resp.status_code, url)
        resp.raise_for_status()
        return resp.json()

    def _get_soup(self, url: str, parser: str = "html.parser") -> BeautifulSoup:
        resp = requests.get(url, headers=_headers(), timeout=self.request_timeout)
        if resp.status_code != 200:
            log.warning("  HTTP %d for %s", resp.status_code, url)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, parser)

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
        employment_type: str = "",
        work_type: str = "Remote",
    ) -> dict:
        title = (title or "Unknown Title").strip()
        company = (company or "Unknown Company").strip()
        location = (location or "Remote").strip()
        link = (link or "").strip()
        # Strip HTML from description
        description_text = BeautifulSoup(description or "", "html.parser").get_text(" ", strip=True)
        return {
            "id": self._make_id(title, company, link or location),
            "title": title,
            "company": company,
            "location": location,
            "link": link,
            "salary": str(salary) if salary else None,
            "work_type": work_type,
            "employment_type": employment_type,
            "source": source,
            "posted": posted,
            "description": description_text,
            "scraped_at": datetime.utcnow().isoformat(),
        }

    def _format_remoteok_salary(self, item: dict) -> Optional[str]:
        """
        BUG FIX: salary_min/max can be strings like "60000" or None.
        Added safe conversion to int to avoid format errors.
        """
        try:
            salary_min = int(item.get("salary_min") or 0)
            salary_max = int(item.get("salary_max") or 0)
        except (ValueError, TypeError):
            return None
        if not salary_min and not salary_max:
            return None
        if salary_min and salary_max:
            return f"${salary_min:,} - ${salary_max:,}"
        return f"${salary_min or salary_max:,}"

    def _format_jobicy_salary(self, item: dict) -> Optional[str]:
        salary_min = item.get("salaryMin") or item.get("annualSalaryMin")
        salary_max = item.get("salaryMax") or item.get("annualSalaryMax")
        if salary_min is None and salary_max is None:
            return None
        currency = item.get("salaryCurrency") or "USD"
        period = item.get("salaryPeriod") or "year"
        values = [value for value in (salary_min, salary_max) if value is not None]
        formatted = " - ".join(f"{currency} {value:,}" for value in values)
        return f"{formatted} / {period}"

    def _matches(self, *values) -> bool:
        """Cheap broad prefilter; the stricter candidate filter runs afterwards."""
        if not self.match_keywords:
            return True
        text = " ".join(str(value or "") for value in values).lower()
        return any(keyword in text for keyword in self.match_keywords)

    def _detect_work_type(self, location: str, description: str = "") -> str:
        text = f"{location} {description}".lower()
        if any(term in text for term in ("remote", "anywhere", "distributed", "work from home")):
            return "Remote"
        if "hybrid" in text:
            return "Hybrid"
        return "On-site"

    def _rss_text(self, item, name: str) -> str:
        element = item.find(name)
        return element.get_text(" ", strip=True) if element else ""

    def _extract_salary(self, text: str) -> Optional[str]:
        match = re.search(
            r"(?:USD|LKR|EUR|GBP|\$|£|€)\s?[\d,.]+(?:\s*(?:-|–|to)\s*(?:USD|LKR|EUR|GBP|\$|£|€)?\s?[\d,.]+)?(?:\s*(?:/|per)\s*(?:hour|month|year|annum))?",
            text or "",
            re.IGNORECASE,
        )
        return match.group(0).strip() if match else None

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
