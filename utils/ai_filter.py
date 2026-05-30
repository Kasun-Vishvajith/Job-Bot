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
                
                # Check for Gemini-extracted salary info
                extracted_sal = evaluation.get("extracted_salary", "Not mentioned")
                if extracted_sal and extracted_sal.lower() != "not mentioned":
                    job["salary"] = extracted_sal
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

        prompt = f"""You are an expert technical recruiter evaluating jobs for a candidate.

Candidate Profile:
{candidate_summary}

Jobs to Evaluate:
{job_list_str}

Evaluation Instructions:
1. Candidate level is undergraduate/entry-level. Look for: intern, internship, trainee, placement, junior, associate, graduate, new grad, student-friendly roles, or roles explicitly accepting 0-1 years of experience.
2. Geolocation constraint:
   - Approve fully remote roles from ANY country in the world.
   - Approve hybrid, office-flex, and on-site roles only when they are located in Colombo, Sri Lanka, or clearly open to Sri Lanka-based candidates.
   - Reject hybrid, office-flex, or on-site roles outside Sri Lanka.
   - If a role is remote but restricted to a country/region where Sri Lanka-based candidates are not eligible, give it a score BELOW 50.
3. Salary Extraction: Search the job snippet/text for any mention of salary, hourly rate, stipend, payout, or compensation. If found, write it under `extracted_salary`. If not mentioned, write "Not mentioned".

Scoring Scale:
- 90-100: Exceptional match (data science, ML, AI, analytics, or BI intern/trainee/junior/0-year role that is fully remote worldwide or based in Colombo/Sri Lanka).
- 70-89: Good match (related fields like data analyst intern, python data intern, graduate analyst, or junior BI role that is remote worldwide or hybrid/on-site in Colombo/Sri Lanka).
- 50-69: Weak match (general developer, QA, or IT support with some data/analytics exposure).
- Below 50: Poor match, senior role, invalid location (e.g. onsite/hybrid job outside Sri Lanka), or roles requiring 3+ years experience.

Provide the score, a brief 1-sentence reasoning explanation, and the extracted salary. Use the specific Job IDs provided."""

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
                                    "extracted_salary": {"type": "STRING"},
                                },
                                "required": ["id", "suitability_score", "reason", "extracted_salary"],
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

