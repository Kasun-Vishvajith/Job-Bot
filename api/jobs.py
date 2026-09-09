"""Authenticated Vercel endpoint for the private dashboard job data."""

import json
import os
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        database_url = (
            os.environ.get("DATABASE_URL")
            or os.environ.get("JOB_BOT_POSTGRES_URL")
            or ""
        ).strip()
        if not database_url:
            self._json(503, {"error": "Private database is not configured"})
            return

        try:
            import psycopg

            with psycopg.connect(database_url, connect_timeout=10) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS job_bot_state (
                           id SMALLINT PRIMARY KEY CHECK (id = 1),
                           payload JSONB NOT NULL,
                           updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                       )"""
                )
                row = conn.execute(
                    "SELECT payload FROM job_bot_state WHERE id = 1"
                ).fetchone()
                conn.commit()

            payload = row[0] if row else {"seen_jobs": {}, "last_updated": ""}
            # Rejected-job history is needed by the collector, never the browser.
            public_payload = {
                "seen_jobs": payload.get("seen_jobs", {}),
                "last_updated": payload.get("last_updated", ""),
            }
            self._json(200, public_payload)
        except Exception:
            self._json(500, {"error": "Unable to load job data"})

    def _json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
