"""
Daily Job Alert Script — Azure Administrator & QA Web Tester
Uses JSearch API (via RapidAPI) — much more reliable than Indeed Scraper.
Runs every day at 9:00 AM Eastern Time and emails results to rishabhkukreja4@gmail.com.

SETUP (one time only):
  1. pip3 install requests schedule pytz
  2. Subscribe to JSearch (FREE) at:
     https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
  3. Fill in your details in the 3 lines below (RAPIDAPI_KEY, GMAIL_ADDRESS, GMAIL_APP_PASS)

USAGE:
  python3 daily_job_alert.py
  Keep the Terminal window open — it will email you every day at 9 AM Eastern.
"""

import smtplib
import requests
import schedule
import time
import argparse
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pytz

# ─────────────────────────────────────────────────────────────────────────────
#  FILL IN YOUR DETAILS HERE  ↓↓↓
# ─────────────────────────────────────────────────────────────────────────────

import os
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS", "")       # 16-char app password from myaccount.google.com/apppasswords

# ─────────────────────────────────────────────────────────────────────────────
#  YOUR JOB PREFERENCES (already set to match what you want)
# ─────────────────────────────────────────────────────────────────────────────

RECIPIENT_EMAIL = "rishabhkukreja4@gmail.com"

SEARCH_QUERIES = [
    "Azure Administrator Canada",
    "Azure Cloud Administrator Ontario",
    "QA Web Tester Canada",
    "Quality Assurance Tester Ontario",
    "QA Engineer entry level Canada",
]

MAX_JOBS     = 10
DAYS_OLD_MAX = 7


# ─────────────────────────────────────────────────────────────────────────────
#  JSearch API  (free tier: 200 requests/month — plenty for daily use)
# ─────────────────────────────────────────────────────────────────────────────

def search_jobs(query: str) -> list[dict]:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key":  RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    params = {
        "query":            query,
        "page":             "1",
        "num_pages":        "1",
        "date_posted":      "week",
        "remote_jobs_only": "false",
        "employment_types": "FULLTIME,INTERN,PARTTIME",
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except Exception as e:
        print(f"  [!] Search error for '{query}': {e}")
        return []


def is_canada_job(job: dict) -> bool:
    """Keep only jobs in Canada (Ontario, Quebec, or Remote)."""
    country   = (job.get("job_country") or "").upper()
    state     = (job.get("job_state") or "").upper()
    city      = (job.get("job_city") or "").upper()
    is_remote = job.get("job_is_remote", False)

    if country and "CA" not in country and "CANADA" not in country:
        return False

    if is_remote:
        return True

    ontario_keys = {"ON", "ONTARIO", "TORONTO", "OTTAWA", "HAMILTON", "LONDON",
                    "MISSISSAUGA", "BRAMPTON", "KITCHENER", "WINDSOR"}
    quebec_keys  = {"QC", "QUEBEC", "MONTREAL", "LAVAL", "GATINEAU", "SHERBROOKE"}

    for key in ontario_keys | quebec_keys:
        if key in state or key in city:
            return True

    return False


def collect_all_jobs() -> list[dict]:
    seen_ids = set()
    all_jobs = []

    for query in SEARCH_QUERIES:
        print(f"  Searching: '{query}'")
        results = search_jobs(query)

        for job in results:
            job_id = job.get("job_id", "")
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            if not is_canada_job(job):
                continue

            city      = job.get("job_city") or ""
            state     = job.get("job_state") or ""
            is_remote = job.get("job_is_remote", False)
            if is_remote:
                location = f"Remote — {city}, {state}".strip(" —,") if city else "Remote, Canada"
            else:
                location = f"{city}, {state}".strip(", ") or "Canada"

            min_sal = job.get("job_min_salary")
            max_sal = job.get("job_max_salary")
            period  = (job.get("job_salary_period") or "").lower()
            if min_sal and max_sal:
                if period == "hourly":
                    min_sal = int(min_sal * 2080)
                    max_sal = int(max_sal * 2080)
                salary = f"CAD ${int(min_sal):,} – ${int(max_sal):,}"
            else:
                salary = "Not listed"

            emp_types = job.get("job_employment_type") or "Full-time"

            posted_ms = job.get("job_posted_at_timestamp")
            if posted_ms:
                posted_dt = datetime.fromtimestamp(posted_ms)
                days_ago  = (datetime.now() - posted_dt).days
                posted    = "Today" if days_ago == 0 else f"{days_ago} day{'s' if days_ago!=1 else ''} ago"
            else:
                posted = "Recently"

            title_lower = (job.get("job_title") or "").lower()
            category = "azure" if "azure" in title_lower or "cloud" in title_lower else "qa"

            all_jobs.append({
                "title":    job.get("job_title", "N/A"),
                "company":  job.get("employer_name", "N/A"),
                "location": location,
                "salary":   salary,
                "type":     emp_types.replace("_", " ").title(),
                "posted":   posted,
                "url":      job.get("job_apply_link") or job.get("job_google_link") or "https://ca.indeed.com",
                "category": category,
            })

            if len(all_jobs) >= MAX_JOBS * 2:
                break

        if len(all_jobs) >= MAX_JOBS * 2:
            break

        time.sleep(1)

    return all_jobs[:MAX_JOBS]


# ─────────────────────────────────────────────────────────────────────────────
#  Email Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_email_html(jobs: list[dict]) -> str:
    today = datetime.now(pytz.timezone("US/Eastern")).strftime("%A, %B %d, %Y")

    rows = ""
    for i, j in enumerate(jobs, 1):
        bg          = "#f9f9f9" if i % 2 else "#ffffff"
        badge_color = "#0057d9" if j["category"] == "azure" else "#7b3fb8"
        badge_label = "Azure" if j["category"] == "azure" else "QA"
        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:12px 10px;">
            <span style="background:{badge_color};color:#fff;font-size:10px;padding:2px 8px;
              border-radius:4px;margin-right:6px;">{badge_label}</span>
            <strong style="color:#1a1a1a;">{j['title']}</strong>
          </td>
          <td style="padding:12px 10px;color:#444;">{j['company']}</td>
          <td style="padding:12px 10px;color:#444;">{j['location']}</td>
          <td style="padding:12px 10px;color:#2a7a2a;font-weight:600;">{j['salary']}</td>
          <td style="padding:12px 10px;color:#444;">{j['type']}</td>
          <td style="padding:12px 10px;color:#888;font-size:12px;">{j['posted']}</td>
          <td style="padding:12px 10px;">
            <a href="{j['url']}" style="background:#0057d9;color:#fff;padding:6px 14px;
               border-radius:6px;text-decoration:none;font-size:13px;font-weight:500;">Apply</a>
          </td>
        </tr>"""

    no_jobs_msg = ""
    if not jobs:
        no_jobs_msg = """
        <div style="padding:24px;text-align:center;color:#888;font-style:italic;">
          No new matching jobs found today. Check back tomorrow!
        </div>"""

    table_html = "" if not jobs else f"""
      <p style="font-size:14px;color:#555;margin-bottom:16px;">
        Found <strong>{len(jobs)}</strong> matching job{"s" if len(jobs)!=1 else ""} today:
      </p>
      <div style="overflow-x:auto;">
      <table style="width:100%;border-collapse:collapse;font-size:14px;min-width:640px;">
        <thead>
          <tr style="background:#0057d9;color:#fff;">
            <th style="padding:10px;text-align:left;">Job Title</th>
            <th style="padding:10px;text-align:left;">Company</th>
            <th style="padding:10px;text-align:left;">Location</th>
            <th style="padding:10px;text-align:left;">Salary (CAD)</th>
            <th style="padding:10px;text-align:left;">Type</th>
            <th style="padding:10px;text-align:left;">Posted</th>
            <th style="padding:10px;text-align:left;">Link</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      </div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:Arial,sans-serif;color:#1a1a1a;background:#f4f4f4;margin:0;padding:20px;">
  <div style="max-width:900px;margin:auto;background:#fff;border-radius:10px;overflow:hidden;">

    <div style="background:#0057d9;padding:28px 32px;">
      <h1 style="color:#fff;margin:0;font-size:22px;">Daily Job Alert</h1>
      <p style="color:#ccdcff;margin:6px 0 0;font-size:14px;">{today} · 9:00 AM Eastern</p>
    </div>

    <div style="padding:16px 32px;background:#f0f5ff;border-bottom:1px solid #dde6ff;">
      <p style="margin:0;font-size:13px;color:#2c3e50;">
        Roles: Azure Administrator, QA Web Tester &nbsp;·&nbsp;
        Locations: Ontario, Quebec, Remote Canada &nbsp;·&nbsp;
        Salary: CAD $40K–$100K &nbsp;·&nbsp;
        Posted: Last 7 days
      </p>
    </div>

    <div style="padding:24px 32px;">
      {no_jobs_msg}
      {table_html}
    </div>

    <div style="padding:14px 32px;background:#f9f9f9;border-top:1px solid #eee;font-size:12px;color:#aaa;">
      Sent automatically by your Daily Job Alert script. To stop, close the Terminal window.
    </div>
  </div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
#  Email Sender
# ─────────────────────────────────────────────────────────────────────────────

def send_email(jobs: list[dict]):
    today   = datetime.now(pytz.timezone("US/Eastern")).strftime("%b %d, %Y")
    subject = f"[Job Alert] {len(jobs)} new opening{'s' if len(jobs)!=1 else ''} — Azure/QA · {today}"

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(build_email_html(jobs), "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
        print(f"  Email sent to {RECIPIENT_EMAIL}  ({len(jobs)} jobs found)")
    except Exception as e:
        print(f"  Email failed: {e}")
        print("  --> Double-check your GMAIL_ADDRESS and GMAIL_APP_PASS at the top of the file.")


# ─────────────────────────────────────────────────────────────────────────────
#  Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_daily_alert():
    et  = pytz.timezone("US/Eastern")
    now = datetime.now(et).strftime("%Y-%m-%d %H:%M ET")
    print(f"\n{'='*60}")
    print(f"  Running daily job alert -- {now}")
    print(f"{'='*60}")
    jobs = collect_all_jobs()
    print(f"\n  Total jobs collected: {len(jobs)}")
    send_email(jobs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once then exit (use for cron)")
    args = parser.parse_args()

    if args.once:
        run_daily_alert()
    else:
        print("Daily Job Alert started!")
        print("Runs every day at 9:00 AM Eastern Time.")
        print("Press Ctrl+C to stop.\n")

        run_daily_alert()   # Run immediately as a test

        schedule.every().day.at("09:00").do(run_daily_alert)

        while True:
            schedule.run_pending()
            time.sleep(60)
