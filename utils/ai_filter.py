"""
Gemini AI Job Filter
Evaluates and scores job suitability for the candidate using Gemini 2.5 Flash.
"""

import json
import logging
import os
from typing import List, Dict

import requests

log = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"


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
            log.warning("GEMINI_API_KEY missing from environment. Skipping AI suitability filter.")
            # Set default values so we don't break downstream rendering
            for job in jobs:
                job["suitability_score"] = None
                job["suitability_reason"] = ""
            return jobs

        if not jobs:
            return []

        log.info("Running Gemini AI suitability filter on %d jobs...", len(jobs))
        evaluations = self._evaluate_jobs(jobs)

        matched_jobs = []
        for job in jobs:
            job_id = job.get("id")
            evaluation = evaluations.get(job_id)

            if evaluation:
                job["suitability_score"] = evaluation.get("suitability_score", 50)
                job["suitability_reason"] = evaluation.get("reason", "")
            else:
                # Default fallback if AI failed to score a specific job
                job["suitability_score"] = 50
                job["suitability_reason"] = "Could not parse suitability."

            # Filter by minimum threshold score
            if job["suitability_score"] >= self.min_score:
                matched_jobs.append(job)
            else:
                log.info(
                    "AI REJECTED '%s' @ %s (Score: %d) — Reason: %s",
                    job.get("title"),
                    job.get("company"),
                    job["suitability_score"],
                    job["suitability_reason"],
                )

        log.info("AI matched %d/%d jobs after refinement.", len(matched_jobs), len(jobs))
        return matched_jobs

    def _evaluate_jobs(self, jobs: List[Dict]) -> Dict[str, Dict]:
        # Formulate a simplified summary of the candidate's profile
        candidate_summary = (
            f"Name: {self.profile_cfg.get('name', 'Candidate')}\n"
            f"Skills: {', '.join(self.profile_cfg.get('keywords', []))}\n"
            f"Must-have keywords: {', '.join(self.profile_cfg.get('must_have_keywords', []))}\n"
            f"Exclude keywords: {', '.join(self.profile_cfg.get('exclude_keywords', []))}"
        )

        # Build list of jobs with minimal info to reduce tokens
        job_list_str = ""
        for i, job in enumerate(jobs):
            # Try to grab the first 300 characters of description to stay compact
            desc = job.get("description", "")
            desc_snippet = desc[:300] + "..." if len(desc) > 300 else desc
            
            job_list_str += (
                f"\n--- Job #{i+1} ---\n"
                f"ID: {job.get('id')}\n"
                f"Title: {job.get('title')}\n"
                f"Company: {job.get('company')}\n"
                f"Location: {job.get('location')} ({job.get('work_type')})\n"
                f"Snippet: {desc_snippet}\n"
            )

        prompt = f"""You are an expert technical recruiter. Evaluate the following jobs and rate their suitability (0 to 100) for the candidate profile.

Candidate Profile:
{candidate_summary}

Jobs to Evaluate:
{job_list_str}

Evaluation Guidelines:
- 90-100: Outstanding match (explicitly data science/ML intern/trainee role matching skills).
- 70-89: Good match (related fields like data analyst, business analyst, python developer intern).
- 50-69: Weak match (general developer, QA, or IT support with some data/analytics exposure).
- Below 50: Mismatch or Senior Role (contains excluded keywords, or unrelated field like Sales/Marketing).

Provide a score (integer 0-100) and a brief 1-sentence explanation for the score. Use the specific Job IDs provided."""

        # Setup structured JSON schema output
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
                                },
                                "required": ["id", "suitability_score", "reason"],
                            },
                        }
                    },
                    "required": ["evaluations"],
                },
            },
        }

        url = GEMINI_API_URL.format(model=self.model, api_key=self.api_key)
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            resp.raise_for_status()
            
            data = resp.json()
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]
            eval_data = json.loads(text_response)
            
            # Map by job ID for easy lookup
            eval_map = {}
            for item in eval_data.get("evaluations", []):
                eval_map[item["id"]] = item
            return eval_map

        except Exception as e:
            log.error("Failed to query Gemini API or parse response: %s", e)
            return {}
