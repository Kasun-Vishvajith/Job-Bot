"""
Gemini AI Job Filter
Evaluates and scores job suitability for the candidate using Gemini 2.5 Flash.

BUG FIXES applied:
  - Timeout of 30s is too short when evaluating many jobs; raised to 90s.
  - Large job batches (>20) caused Gemini to hit token limits or time out;
    added auto-chunking so jobs are evaluated in batches of 20.
  - If Gemini returns text that isn't valid JSON (despite responseMimeType),
    we now attempt to strip markdown code fences before parsing.
  - suitability_score comparison used `>=` but score could be a float from
    the schema; added explicit int() cast.
  - Added total retry (up to 2x) on transient API failures.
  - Log the model name being used at startup for traceability.
"""

import json
import logging
import os
import time
from typing import List, Dict

import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent?key={api_key}"
)

# Max jobs per Gemini call — avoid token-limit errors
BATCH_SIZE = 20


class AIFilter:
    def __init__(self, profile_cfg: dict, ai_cfg: dict):
        self.profile_cfg = profile_cfg
        self.enabled = ai_cfg.get("enabled", True)
        self.min_score = ai_cfg.get("min_suitability_score", 70)
        self.model = ai_cfg.get("model", "gemini-2.5-flash")
        self.api_key = os.environ.get("GEMINI_API_KEY", "")

    def filter(self, jobs: List[Dict]) -> List[Dict]:
        if not self.enabled:
            log.info("AI Filtering disabled by configuration.")
            return jobs

        if not self.api_key:
            log.warning(
                "GEMINI_API_KEY missing from environment. "
                "Skipping AI suitability filter."
            )
            for job in jobs:
                job.setdefault("suitability_score", None)
                job.setdefault("suitability_reason", "")
            return jobs

        if not jobs:
            return []

        log.info(
            "Running Gemini AI suitability filter on %d jobs (model=%s)...",
            len(jobs), self.model,
        )

        # BUG FIX: Chunk jobs to avoid token-limit / timeout errors
        all_evaluations: Dict[str, Dict] = {}
        for i in range(0, len(jobs), BATCH_SIZE):
            chunk = jobs[i: i + BATCH_SIZE]
            chunk_evals = self._evaluate_jobs(chunk)
            all_evaluations.update(chunk_evals)
            if i + BATCH_SIZE < len(jobs):
                time.sleep(1)  # brief pause between batches

        matched_jobs = []
        for job in jobs:
            job_id = job.get("id")
            evaluation = all_evaluations.get(job_id)

            if evaluation:
                job["ai_evaluated"] = True
                # BUG FIX: Cast to int in case Gemini returns a float
                raw_score = evaluation.get("suitability_score", 50)
                job["suitability_score"] = int(raw_score) if raw_score is not None else 50
                job["suitability_reason"] = evaluation.get("reason", "")

                extracted_sal = str(evaluation.get("extracted_salary", "")).strip()
                salary_found = bool(evaluation.get("salary_found"))
                if salary_found and extracted_sal and extracted_sal.lower() not in ("not mentioned", "none"):
                    job["salary"] = extracted_sal
                    job["salary_status"] = "listed"
                elif job.get("salary"):
                    job["salary_status"] = "listed"
                else:
                    job["salary"] = ""
                    job["salary_status"] = "not_mentioned"
            else:
                # Gemini is an enrichment/ranking layer. A timeout, quota issue,
                # or malformed response must not discard a job that already
                # passed the deterministic eligibility filters.
                job["ai_evaluated"] = False
                job["suitability_score"] = None
                job["suitability_reason"] = "AI review unavailable; deterministic filters passed."
                job.setdefault("salary_status", "listed" if job.get("salary") else "not_mentioned")
                matched_jobs.append(job)
                continue

            if job["suitability_score"] >= self.min_score:
                matched_jobs.append(job)
            else:
                log.info(
                    "AI REJECTED '%s' @ %s (Score: %d) — %s",
                    job.get("title"),
                    job.get("company"),
                    job["suitability_score"],
                    job.get("suitability_reason"),
                )

        log.info("AI matched %d/%d jobs.", len(matched_jobs), len(jobs))
        return matched_jobs

    def _evaluate_jobs(self, jobs: List[Dict]) -> Dict[str, Dict]:
        candidate_summary = (
            f"Name: {self.profile_cfg.get('name', 'Candidate')}\n"
            f"Experience: {self.profile_cfg.get('experience_summary', '')}\n"
            f"Skills: {', '.join(self.profile_cfg.get('keywords', []))}\n"
            f"Must-have keywords: {', '.join(self.profile_cfg.get('must_have_keywords', []))}\n"
            f"Exclude keywords: {', '.join(self.profile_cfg.get('exclude_keywords', []))}"
        )

        job_list_str = ""
        for i, job in enumerate(jobs):
            desc = job.get("description", "")
            # Compensation often appears near the end of a listing. Keep enough
            # source text for extraction while preserving bounded batch sizes.
            desc_snippet = desc[:1500] + "..." if len(desc) > 1500 else desc
            job_list_str += (
                f"\n--- Job #{i+1} ---\n"
                f"ID: {job.get('id')}\n"
                f"Title: {job.get('title')}\n"
                f"Company: {job.get('company')}\n"
                f"Location: {job.get('location')} ({job.get('work_type')})\n"
                f"Posted: {job.get('posted', 'Unknown')}\n"
                f"Snippet: {desc_snippet}\n"
            )

        prompt = f"""You are an expert technical recruiter evaluating jobs for a candidate.

Candidate Profile:
{candidate_summary}

Jobs to Evaluate:
{job_list_str}

Evaluation Instructions:
1. Candidate level is early-career. Approve permanent junior, associate, graduate, new-grad, or entry-level roles accepting 0-3 years of experience. Reject internships, temporary roles, and contracts.
2. Geolocation constraint:
   - Approve fully remote roles from ANY country in the world.
   - Approve hybrid, office-flex, and on-site roles only when they are located in Colombo, Sri Lanka, or clearly open to Sri Lanka-based candidates.
   - Reject hybrid, office-flex, or on-site roles outside Sri Lanka.
   - If a role is remote but restricted to a country/region where Sri Lanka-based candidates are not eligible, give it a score BELOW 50.
3. Salary extraction must be evidence-based. Extract compensation only when a numeric amount or range and currency are explicitly present in the supplied listing. Preserve its pay period (hourly/monthly/yearly) when stated. Never estimate salary from the title, employer, location, or market knowledge. Set `salary_found` to false and `extracted_salary` to "Not mentioned" when explicit evidence is absent.

Scoring Scale:
- 90-100: Exceptional match (AI/ML, automation, data science/engineering, DevOps/cloud/platform, or automotive software/data role at 0-3 years that is fully remote worldwide or based in Sri Lanka).
- 70-89: Good match (a closely related permanent graduate, junior, associate, or early-career technical role with an eligible location).
- 50-69: Weak match (general developer, QA, or IT support with some data/analytics exposure).
- Below 50: Poor match, senior role, invalid location (e.g. onsite/hybrid job outside Sri Lanka), or roles requiring 3+ years experience.

Provide the score, a brief 1-sentence reasoning explanation, and the extracted salary. Use the specific Job IDs provided."""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "evaluations": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "id": {"type": "STRING"},
                                    "suitability_score": {"type": "INTEGER"},
                                    "reason": {"type": "STRING"},
                                    "salary_found": {"type": "BOOLEAN"},
                                    "extracted_salary": {"type": "STRING"},
                                },
                                "required": ["id", "suitability_score", "reason", "salary_found", "extracted_salary"],
                            },
                        }
                    },
                    "required": ["evaluations"],
                },
            },
        }

        url = GEMINI_API_URL.format(model=self.model, api_key=self.api_key)

        # BUG FIX: Added retry logic (up to 2 retries) for transient failures
        for attempt in range(3):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    # BUG FIX: Timeout raised from 30s to 90s for large batches
                    timeout=90,
                )
                resp.raise_for_status()

                data = resp.json()
                text_response = data["candidates"][0]["content"]["parts"][0]["text"]

                # BUG FIX: Strip markdown code fences if Gemini wraps JSON in them
                text_response = text_response.strip()
                if text_response.startswith("```"):
                    text_response = text_response.lstrip("`").lstrip("json").strip()
                    if text_response.endswith("```"):
                        text_response = text_response[: text_response.rfind("```")].strip()

                eval_data = json.loads(text_response)
                eval_map = {}
                for item in eval_data.get("evaluations", []):
                    eval_map[item["id"]] = item
                return eval_map

            except requests.exceptions.Timeout:
                log.warning("  [AI] Gemini request timed out (attempt %d/3)", attempt + 1)
                if attempt < 2:
                    time.sleep(5)
            except Exception as e:
                log.error("  [AI] Failed to query Gemini or parse response (attempt %d/3): %s", attempt + 1, e)
                if attempt < 2:
                    time.sleep(3)

        return {}
