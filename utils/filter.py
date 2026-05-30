"""
Job Filter
Matches scraped jobs against the user's profile keywords and preferences.

Rules:
  1. MUST-HAVE keywords — job is rejected if none appear anywhere in the listing
  2. Exclusion keywords  — job is rejected if any appear
  3. Profile keywords    — at least min_keyword_matches must be present
  4. Location rule:
       remote  → accepted from anywhere in the world
       hybrid / on-site → must be in Colombo / Sri Lanka only
"""

import logging
import re

log = logging.getLogger(__name__)

# ── Work type detection ────────────────────────────────────────────────────────
WORK_TYPE_PATTERNS = {
    "remote": [
        "remote", "work from home", "wfh", "fully remote",
        "anywhere", "worldwide", "work anywhere", "location independent",
        "virtual", "telecommute", "home based", "home-based",
    ],
    "hybrid": [
        "hybrid", "partially remote", "flexible location",
        "hybrid remote", "remote / on-site", "on-site / remote",
    ],
    "on-site": [
        "on-site", "onsite", "in-person", "in person", "on site",
        "office based", "office-based",
    ],
}

# For hybrid/on-site jobs: location must contain one of these
COLOMBO_INDICATORS = [
    "colombo", "sri lanka", ", lk", "(lk)", "srilanka", "western province",
]

# Default must-have keywords (overridable from config)
DEFAULT_MUST_HAVE = ["intern", "internship", "trainee", "placement"]
DEFAULT_ENTRY_LEVEL = [
    "intern",
    "internship",
    "trainee",
    "placement",
    "entry level",
    "entry-level",
    "junior",
    "associate",
    "graduate",
    "new grad",
    "student",
    "apprentice",
    "0 years",
    "zero years",
    "no experience",
]


class JobFilter:
    def __init__(self, profile: dict, filtering: dict):
        self.keywords         = [kw.lower() for kw in profile.get("keywords", [])]
        self.exclude_keywords = [kw.lower() for kw in profile.get("exclude_keywords", [])]
        self.must_have        = [kw.lower() for kw in profile.get("must_have_keywords", DEFAULT_MUST_HAVE)]
        self.min_matches      = filtering.get("min_keyword_matches", 1)
        self.strict_filtering = filtering.get("strict_keyword_filtering", True)
        self.allowed_work_types = {
            wt.lower() for wt in profile.get("work_types", ["remote", "hybrid", "on-site"])
        }
        self.remote_worldwide = profile.get("location_rules", {}).get("remote_worldwide", True)
        self.allowed_locations = [
            loc.lower() for loc in profile.get("location_rules", {}).get("onsite_allowed_cities", COLOMBO_INDICATORS)
        ]
        self.enforce_entry_level = filtering.get("enforce_entry_level", False)
        self.entry_level_keywords = [
            kw.lower() for kw in filtering.get("entry_level_keywords", DEFAULT_ENTRY_LEVEL)
        ]
        self.max_years_experience = filtering.get("max_years_experience", 1)

    def filter(self, jobs: list[dict]) -> list[dict]:
        matched = []
        for job in jobs:
            result, reason = self._check(job)
            if result:
                job["matched_keywords"] = self._get_matches(job)
                # Ensure work_type is always correctly set on the job object and capitalized
                detected_wt = self._detect_work_type(self._job_text(job), job.get("location", ""))
                job["work_type"] = "Remote" if detected_wt == "remote" else ("Hybrid" if detected_wt == "hybrid" else "On-site")
                matched.append(job)
            else:
                log.debug("SKIP '%s' @ %s — %s", job.get("title"), job.get("company"), reason)
        return matched

    def _check(self, job: dict) -> tuple[bool, str]:
        text     = self._job_text(job)
        location = job.get("location", "").lower()

        # ── 1. Must-have keywords (intern/internship MUST appear) ─────────────
        if self.strict_filtering and self.must_have:
            if not any(kw in text for kw in self.must_have):
                return False, f"missing must-have keyword (need one of: {self.must_have})"

        if self.enforce_entry_level and not self._is_entry_level(text):
            return False, "not an internship, entry-level, graduate, or 0-year role"

        # ── 2. Exclusion check ────────────────────────────────────────────────
        for excl in self.exclude_keywords:
            if excl in text:
                return False, f"excluded keyword found: '{excl}'"

        # ── 3. Profile keyword match ──────────────────────────────────────────
        matches = sum(1 for kw in self.keywords if kw in text)
        if matches < self.min_matches:
            return False, f"only {matches}/{self.min_matches} keyword matches"

        # ── 4. Location rule ──────────────────────────────────────────────────
        work_type = self._detect_work_type(text, location)

        if work_type not in self.allowed_work_types:
            return False, f"{work_type} role is not enabled in profile.work_types"

        if work_type == "remote":
            return (True, "ok") if self.remote_worldwide else (False, "remote worldwide disabled")

        # hybrid or on-site → must be Colombo / Sri Lanka
        is_colombo = any(ind in location for ind in self.allowed_locations)
        if not is_colombo:
            return False, f"{work_type} role not in Colombo (location: '{job.get('location')}')"

        return True, "ok"

    def _detect_work_type(self, text: str, location: str = "") -> str:
        """
        Detect work type from the full job text + location string.
        Checks remote first — if any remote signal exists, it's remote.
        """
        combined = (text + " " + location).lower()

        # Remote takes priority — even if location field says a city,
        # if the description mentions remote/wfh it counts as remote
        for alias in WORK_TYPE_PATTERNS["remote"]:
            if alias in combined:
                return "remote"

        for alias in WORK_TYPE_PATTERNS["hybrid"]:
            if alias in combined:
                return "hybrid"

        for alias in WORK_TYPE_PATTERNS["on-site"]:
            if alias in combined:
                return "on-site"

        return "on-site"  # default if nothing detected

    def _is_entry_level(self, text: str) -> bool:
        if any(kw in text for kw in self.entry_level_keywords):
            return True

        years = [
            int(match.group(1))
            for match in re.finditer(r"(\d+)\s*\+?\s*(?:years?|yrs?)\b", text)
        ]
        if years:
            return min(years) <= self.max_years_experience

        return False

    def _get_matches(self, job: dict) -> list[str]:
        text = self._job_text(job)
        return [kw for kw in self.keywords if kw in text]

    def _job_text(self, job: dict) -> str:
        parts = [
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("description", ""),
            job.get("work_type", ""),
        ]
        return " ".join(parts).lower()
