"""
Job Database
Stores seen job IDs in a JSON file to prevent duplicate notifications.
Designed to work with GitHub Actions (committed back to the repo).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

# Keep job IDs in the database for this many days before expiring
RETENTION_DAYS = 60


class JobDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict:
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Could not load database, starting fresh: %s", e)
        return {"seen_jobs": {}, "last_updated": ""}

    def _save(self):
        self.data["last_updated"] = datetime.utcnow().isoformat()
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
            
        # Also write a JS file for local browser access without a server
        js_path = self.db_path.with_suffix(".js")
        with open(js_path, "w", encoding="utf-8") as f:
            f.write("const SEEN_JOBS_DATA = ")
            json.dump(self.data, f, indent=2)
            f.write(";\n")

    def get_new_jobs(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs whose IDs haven't been seen before."""
        seen = self.data.get("seen_jobs", {})
        ignored = self.data.get("ignored_jobs", {})
        new_jobs = []
        for job in jobs:
            job_id = job.get("id")
            if job_id and job_id not in seen and job_id not in ignored:
                new_jobs.append(job)
        return new_jobs

    def save_ignored(self, jobs: list[dict]):
        """Remember AI-rejected jobs without exposing them on the dashboard."""
        now = datetime.utcnow()
        cutoff = now - timedelta(days=RETENTION_DAYS)
        ignored = self.data.get("ignored_jobs", {})
        for job in jobs:
            if job.get("id"):
                ignored[job["id"]] = now.isoformat()
        self.data["ignored_jobs"] = {
            job_id: seen_at for job_id, seen_at in ignored.items()
            if datetime.fromisoformat(seen_at) > cutoff
        }
        self._save()

    def save_jobs(self, jobs: list[dict]):
        """Add new job IDs to the database and prune old ones."""
        seen = self.data.get("seen_jobs", {})
        now = datetime.utcnow()

        # Add new jobs
        for job in jobs:
            job_id = job.get("id")
            if job_id:
                seen[job_id] = {
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "source": job.get("source", ""),
                    "location": job.get("location", ""),
                    "work_type": job.get("work_type", ""),
                    "employment_type": job.get("employment_type", ""),
                    "link": job.get("link", ""),
                    "salary": job.get("salary", ""),
                    # Full job descriptions can contain recruiter contact details
                    # and copyrighted text. Keep them in memory for filtering, but
                    # do not publish them in the dashboard database.
                    "description": "",
                    "seen_at": now.isoformat(),
                }

        # Prune expired entries
        cutoff = now - timedelta(days=RETENTION_DAYS)
        seen = {
            k: v for k, v in seen.items()
            if datetime.fromisoformat(v.get("seen_at", now.isoformat())) > cutoff
        }

        self.data["seen_jobs"] = seen
        self._save()
        log.info("Database saved. Total tracked jobs: %d", len(seen))

    def stats(self) -> dict:
        return {
            "total_tracked": len(self.data.get("seen_jobs", {})),
            "last_updated": self.data.get("last_updated", "never"),
        }
