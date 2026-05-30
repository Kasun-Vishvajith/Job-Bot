"""
Notifier
Sends job alerts via Email (Gmail SMTP) and Telegram Bot.
Reads credentials from environment variables (GitHub Secrets).
"""

import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

log = logging.getLogger(__name__)

WORK_TYPE_EMOJI = {
    "Remote": "🏠",
    "Hybrid": "🔀",
    "On-site": "🏢",
}

SOURCE_EMOJI = {
    "LinkedIn": "💼",
    "Indeed": "🔍",
    "TopJobs LK": "🇱🇰",
    "XpressJobs": "🇱🇰",
}


class Notifier:
    def __init__(self, config: dict):
        self.email_cfg = config.get("email", {})
        self.telegram_cfg = config.get("telegram", {})

    def send(self, jobs: list[dict], recipient_name: str = ""):
        if self.email_cfg.get("enabled"):
            self._send_email(jobs, recipient_name)
        if self.telegram_cfg.get("enabled"):
            self._send_telegram(jobs)

    # ── Email ─────────────────────────────────────────────────────────────────

    def _send_email(self, jobs: list[dict], recipient_name: str):
        sender = os.environ.get("GMAIL_SENDER") or self.email_cfg.get("sender", "")
        recipient = os.environ.get("GMAIL_RECIPIENT") or self.email_cfg.get("recipient", "")
        password = os.environ.get("GMAIL_APP_PASSWORD", "")

        if not all([sender, recipient, password]):
            log.warning("Email credentials missing. Skipping email.")
            return

        now = datetime.utcnow().strftime("%b %d, %Y at %H:%M UTC")
        count = len(jobs)
        subject = f"🚀 {count} New Job{'s' if count > 1 else ''} Found — {now}"

        html_body = self._build_html_email(jobs, recipient_name, now)
        text_body = self._build_text_email(jobs, now)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Job Alert Bot <{sender}>"
        msg["To"] = recipient
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
            log.info("Email sent to %s", recipient)
        except Exception as e:
            log.error("Failed to send email: %s", e)

    def _build_html_email(self, jobs: list[dict], name: str, timestamp: str) -> str:
        cards_html = ""
        for job in jobs:
            work_emoji = WORK_TYPE_EMOJI.get(job.get("work_type", ""), "📍")
            source_emoji = SOURCE_EMOJI.get(job.get("source", ""), "🔗")
            keywords_html = ""
            for kw in job.get("matched_keywords", [])[:5]:
                keywords_html += f'<span style="background:#e8f4fd;color:#1a73e8;padding:2px 8px;border-radius:12px;font-size:11px;margin:2px;display:inline-block;">{kw}</span>'

            salary_section = ""
            if job.get("salary"):
                salary_section = f"""
                <div style="margin:8px 0;padding:6px 10px;background:#f0fdf4;border-left:3px solid #22c55e;border-radius:4px;">
                    <strong style="color:#16a34a;">💰 {job['salary']}</strong>
                </div>"""

            suitability_section = ""
            if job.get("suitability_score") is not None:
                score = job["suitability_score"]
                reason = job.get("suitability_reason", "")
                if score >= 90:
                    badge_style = "background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;"
                elif score >= 70:
                    badge_style = "background:#fef9c3;color:#854d0e;border:1px solid #fef08a;"
                else:
                    badge_style = "background:#f3f4f6;color:#374151;border:1px solid #e5e7eb;"
                suitability_section = f"""
                <div style="margin:8px 0;padding:10px 12px;background:#f9fafb;border-left:3px solid #6366f1;border-radius:4px;font-size:13px;">
                    <span style="font-weight:600;display:inline-block;padding:2px 6px;border-radius:4px;font-size:11px;margin-right:6px;{badge_style}">⭐ {score}% Suitability</span>
                    <span style="color:#4b5563;font-style:italic;">"{reason}"</span>
                </div>"""

            link = job.get("link", "#")
            link_btn = f'<a href="{link}" style="display:inline-block;background:#1a73e8;color:white;padding:8px 18px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;">View Job →</a>' if link and link != "#" else ""

            posted = f'<span style="color:#9ca3af;font-size:11px;">📅 {job["posted"]}</span>' if job.get("posted") else ""

            cards_html += f"""
            <div style="background:white;border:1px solid #e5e7eb;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
                    <div style="font-size:11px;color:#6b7280;">{source_emoji} {job.get('source','')}</div>
                    {posted}
                </div>
                <h3 style="margin:4px 0 6px;color:#111827;font-size:17px;font-weight:700;">{job.get('title','')}</h3>
                <div style="color:#374151;font-size:14px;margin-bottom:4px;">🏢 {job.get('company','')}</div>
                <div style="color:#6b7280;font-size:13px;margin-bottom:10px;">{work_emoji} {job.get('work_type','')} &nbsp;·&nbsp; 📍 {job.get('location','')}</div>
                {salary_section}
                {suitability_section}
                <div style="margin:10px 0;">{keywords_html}</div>
                <div style="margin-top:12px;">{link_btn}</div>
            </div>"""

        greeting = f"Hi {name}," if name else "Hi,"

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);border-radius:16px;padding:28px 28px 24px;margin-bottom:20px;text-align:center;">
    <div style="font-size:36px;margin-bottom:8px;">🚀</div>
    <h1 style="color:white;margin:0;font-size:22px;font-weight:700;">{len(jobs)} New Job Alert{'s' if len(jobs)>1 else ''}</h1>
    <p style="color:rgba(255,255,255,0.8);margin:6px 0 0;font-size:13px;">{timestamp}</p>
  </div>

  <!-- Greeting -->
  <p style="color:#374151;font-size:15px;margin:0 0 20px;">{greeting} Here are the new job listings matching your profile:</p>

  <!-- Job Cards -->
  {cards_html}

  <!-- Footer -->
  <div style="text-align:center;padding:20px 0;color:#9ca3af;font-size:12px;">
    <p style="margin:0;">Sent by your Job Alert Bot · Runs every 3 hours</p>
    <p style="margin:4px 0 0;">Edit <code>config.yaml</code> to update your preferences</p>
  </div>

</div>
</body>
</html>"""

    def _build_text_email(self, jobs: list[dict], timestamp: str) -> str:
        lines = [f"JOB ALERT — {len(jobs)} new listing(s) found at {timestamp}", "=" * 60]
        for i, job in enumerate(jobs, 1):
            lines.append(f"\n[{i}] {job.get('title', 'Unknown')}")
            lines.append(f"    Company  : {job.get('company', '')}")
            lines.append(f"    Location : {job.get('location', '')} ({job.get('work_type', '')})")
            lines.append(f"    Source   : {job.get('source', '')}")
            if job.get("salary"):
                lines.append(f"    Salary   : {job['salary']}")
            if job.get("matched_keywords"):
                lines.append(f"    Keywords : {', '.join(job['matched_keywords'])}")
            if job.get("link"):
                lines.append(f"    Link     : {job['link']}")
        lines.append("\n" + "=" * 60)
        lines.append("Edit config.yaml to update your job search preferences.")
        return "\n".join(lines)

    # ── Telegram ─────────────────────────────────────────────────────────────

    def _send_telegram(self, jobs: list[dict]):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if not token or not chat_id:
            log.warning("Telegram credentials missing. Skipping Telegram.")
            return

        # Send one Telegram message per job (keeps it readable)
        for job in jobs:
            text = self._format_telegram_message(job)
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                resp = requests.post(url, json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": False,
                }, timeout=10)
                resp.raise_for_status()
            except Exception as e:
                log.error("Telegram send failed: %s", e)

        # Also send a summary if more than 3 jobs
        if len(jobs) > 3:
            summary = f"📊 *Summary:* {len(jobs)} new jobs found this cycle. Check your email for the full formatted list!"
            try:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, json={
                    "chat_id": chat_id,
                    "text": summary,
                    "parse_mode": "Markdown",
                }, timeout=10)
            except Exception as e:
                log.error("Telegram summary send failed: %s", e)

    def _format_telegram_message(self, job: dict) -> str:
        # Normalise work_type display — capitalise correctly
        raw_wt = job.get("work_type", "on-site").lower()
        if "remote" in raw_wt:
            display_wt = "Remote"
        elif "hybrid" in raw_wt:
            display_wt = "Hybrid"
        else:
            display_wt = "On-site"
        job["work_type"] = display_wt   # keep consistent for downstream use
        work_emoji = WORK_TYPE_EMOJI.get(display_wt, "📍")
        source_emoji = SOURCE_EMOJI.get(job.get("source", ""), "🔗")

        lines = [
            f"🆕 *New Job Found!*",
            f"",
            f"*{job.get('title', 'Unknown Title')}*",
            f"🏢 {job.get('company', 'Unknown Company')}",
            f"{work_emoji} {job.get('work_type', '')} · 📍 {job.get('location', '')}",
            f"{source_emoji} via {job.get('source', '')}",
        ]

        if job.get("salary"):
            lines.append(f"💰 {job['salary']}")

        if job.get("matched_keywords"):
            kw_str = " · ".join(f"`{kw}`" for kw in job["matched_keywords"][:4])
            lines.append(f"🏷 {kw_str}")

        if job.get("suitability_score") is not None:
            score = job["suitability_score"]
            reason = job.get("suitability_reason", "")
            lines.append(f"⭐ *AI Match:* `{score}%` \n_\"{reason}\"_")

        if job.get("link"):
            lines.append(f"")
            lines.append(f"[View Job →]({job['link']})")

        return "\n".join(lines)
