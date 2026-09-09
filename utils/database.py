"""Private job state with a PostgreSQL backend and local JSON fallback."""

import json
import hashlib
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

log = logging.getLogger(__name__)

# Keep job IDs in the database for this many days before expiring
RETENTION_DAYS = 60


class JobDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.database_url = (
            os.environ.get("DATABASE_URL")
            or os.environ.get("JOB_BOT_POSTGRES_URL")
            or ""
        ).strip()
        if not self.database_url:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()
        self.last_dedupe_stats = {"new": 0, "updated": 0, "unchanged": 0}

    def _load(self) -> dict:
        if self.database_url:
            try:
                with self._connect() as conn:
                    self._ensure_table(conn)
                    row = conn.execute(
                        "SELECT payload FROM job_bot_state WHERE id = 1"
                    ).fetchone()
                    return row[0] if row else {"seen_jobs": {}, "ignored_jobs": {}, "last_updated": ""}
            except Exception as exc:
                raise RuntimeError("Could not load the private PostgreSQL job database") from exc
        if self.db_path.exists():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                log.warning("Could not load database, starting fresh: %s", e)
        return {"seen_jobs": {}, "ignored_jobs": {}, "last_updated": ""}

    def _save(self):
        self.data["last_updated"] = datetime.utcnow().isoformat()
        if self.database_url:
            try:
                with self._connect() as conn:
                    self._ensure_table(conn)
                    conn.execute(
                        """INSERT INTO job_bot_state (id, payload, updated_at)
                           VALUES (1, %s::jsonb, NOW())
                           ON CONFLICT (id) DO UPDATE
                           SET payload = EXCLUDED.payload, updated_at = NOW()""",
                        (json.dumps(self.data),),
                    )
                    conn.commit()
                return
            except Exception as exc:
                raise RuntimeError("Could not save the private PostgreSQL job database") from exc

        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
            
        # Also write a JS file for local browser access without a server
        js_path = self.db_path.with_suffix(".js")
        with open(js_path, "w", encoding="utf-8") as f:
            f.write("const SEEN_JOBS_DATA = ")
            json.dump(self.data, f, indent=2)
            f.write(";\n")

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is set but psycopg is not installed") from exc
        return psycopg.connect(self.database_url, connect_timeout=15)

    @staticmethod
    def _ensure_table(conn):
        conn.execute(
            """CREATE TABLE IF NOT EXISTS job_bot_state (
                   id SMALLINT PRIMARY KEY CHECK (id = 1),
                   payload JSONB NOT NULL,
                   updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
               )"""
        )

    def get_new_jobs(self, jobs: list[dict]) -> list[dict]:
        """Apply deterministic duplicate/change detection before any AI call."""
        seen = self.data.get("seen_jobs", {})
        ignored = self.data.get("ignored_jobs", {})
        prior_records = self._prior_records(seen, ignored)
        by_url, by_role, by_id = self._build_indexes(prior_records)
        accepted = []
        stats = {"new": 0, "updated": 0, "unchanged": 0}

        for original in jobs:
            job = dict(original)
            job_id = job.get("id", "")
            job.setdefault("application_deadline", self._extract_deadline(job.get("description", "")))
            stable_url = self._stable_url(job.get("link", ""))
            role_key = self._role_key(job)
            previous = by_id.get(job_id) or by_url.get(stable_url) or by_role.get(role_key)

            if previous:
                previous_id, previous_job = previous
                # Multiple sources in the same scrape may describe one vacancy
                # with different completeness. Merge them into one candidate;
                # an update is only created relative to a persisted earlier run.
                if any(previous_job is candidate for candidate in accepted):
                    for field in (
                        "title", "company", "location", "salary",
                        "application_deadline", "employment_type", "link", "description",
                    ):
                        if job.get(field) and not previous_job.get(field):
                            previous_job[field] = job[field]
                    stats["unchanged"] += 1
                    continue
                changes = self._meaningful_changes(previous_job, job)
                if not changes:
                    stats["unchanged"] += 1
                    continue
                job["is_updated"] = True
                job["supersedes_id"] = previous_id
                job["changed_fields"] = list(changes)
                job["change_summary"] = self._change_summary(changes)
                job["id"] = self._version_id(previous_id, job)
                stats["updated"] += 1
            else:
                job["is_updated"] = False
                job["changed_fields"] = []
                job["change_summary"] = ""
                stats["new"] += 1

            accepted.append(job)
            current = (job["id"], job)
            by_id[job["id"]] = current
            if stable_url:
                by_url[stable_url] = current
            if role_key:
                by_role[role_key] = current

        self.last_dedupe_stats = stats
        log.info(
            "Non-AI duplicate gate: %d new, %d changed, %d unchanged duplicates",
            stats["new"], stats["updated"], stats["unchanged"],
        )
        return accepted

    def save_ignored(self, jobs: list[dict]):
        """Remember AI-rejected jobs without exposing them on the dashboard."""
        now = datetime.utcnow()
        cutoff = now - timedelta(days=RETENTION_DAYS)
        ignored = self.data.get("ignored_jobs", {})
        for job in jobs:
            if job.get("id"):
                ignored[job["id"]] = {
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "location": job.get("location", ""),
                    "salary": job.get("salary", ""),
                    "salary_status": job.get("salary_status", "not_mentioned"),
                    "application_deadline": job.get("application_deadline", ""),
                    "link": job.get("link", ""),
                    "seen_at": now.isoformat(),
                }
        self.data["ignored_jobs"] = {
            job_id: record for job_id, record in ignored.items()
            if self._record_date(record, now) > cutoff
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
                    "salary_status": job.get("salary_status", "not_mentioned"),
                    "application_deadline": job.get("application_deadline", ""),
                    "is_updated": bool(job.get("is_updated")),
                    "supersedes_id": job.get("supersedes_id", ""),
                    "changed_fields": job.get("changed_fields", []),
                    "change_summary": job.get("change_summary", ""),
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

    def _prior_records(self, seen: dict, ignored: dict) -> list[tuple[str, dict]]:
        records = [(job_id, record) for job_id, record in seen.items() if isinstance(record, dict)]
        records.extend(
            (job_id, record) for job_id, record in ignored.items() if isinstance(record, dict)
        )
        return sorted(records, key=lambda pair: pair[1].get("seen_at", ""))

    def _build_indexes(self, records):
        by_url, by_role, by_id = {}, {}, {}
        for job_id, record in records:
            pair = (job_id, record)
            by_id[job_id] = pair
            stable_url = self._stable_url(record.get("link", ""))
            role_key = self._role_key(record)
            if stable_url:
                by_url[stable_url] = pair
            if role_key:
                by_role[role_key] = pair
        return by_url, by_role, by_id

    def _meaningful_changes(self, previous: dict, current: dict) -> dict:
        fields = ("title", "application_deadline", "salary", "location")
        changes = {}
        for field in fields:
            old = self._normalize(previous.get(field, ""))
            new = self._normalize(current.get(field, ""))
            # Missing data is not a change; newly discovered data is.
            if new and old != new:
                changes[field] = (previous.get(field, ""), current.get(field, ""))
        return changes

    def _change_summary(self, changes: dict) -> str:
        labels = {
            "title": "position",
            "application_deadline": "application deadline",
            "salary": "salary",
            "location": "location",
        }
        return "Updated " + ", ".join(labels[field] for field in changes)

    def _version_id(self, previous_id: str, job: dict) -> str:
        values = "|".join(self._normalize(job.get(field, "")) for field in (
            "title", "application_deadline", "salary", "location"
        ))
        return hashlib.sha256(f"{previous_id}|{values}".encode()).hexdigest()[:32]

    def _role_key(self, job: dict) -> str:
        company = self._normalize(job.get("company", ""))
        title = self._normalize(job.get("title", ""))
        if not company or company in {"unknown", "unknown company"} or not title:
            return ""
        return f"{company}|{title}"

    def _stable_url(self, url: str) -> str:
        if not url:
            return ""
        try:
            parts = urlsplit(url.strip())
            path = re.sub(r"/(?:apply)/?$", "", parts.path.rstrip("/"), flags=re.IGNORECASE)
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))
        except ValueError:
            return url.strip().lower()

    def _normalize(self, value) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    def _extract_deadline(self, description: str) -> str:
        match = re.search(
            r"(?:application deadline|closing date|apply by)\s*[:\-]?\s*([^.;\n]{4,40})",
            description or "",
            re.IGNORECASE,
        )
        return match.group(1).strip() if match else ""

    def _record_date(self, record, default: datetime) -> datetime:
        value = record.get("seen_at", "") if isinstance(record, dict) else str(record or "")
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return default

    def stats(self) -> dict:
        return {
            "total_tracked": len(self.data.get("seen_jobs", {})),
            "last_updated": self.data.get("last_updated", "never"),
        }
