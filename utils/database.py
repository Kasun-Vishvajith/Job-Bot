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

    def get_new_jobs(self, jobs: list[dict]) -> list[dict]:
        """Return only jobs whose IDs haven't been seen before."""
        seen = self.data.get("seen_jobs", {})
        new_jobs = []
        for job in jobs:
            job_id = job.get("id")
            if job_id and job_id not in seen:
                new_jobs.append(job)
        return new_jobs

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
