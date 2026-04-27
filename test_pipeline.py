"""
test_pipeline.py - Diagnostic script to verify every component before running main.py

Run: python -c "import sys; sys.stdout.reconfigure(encoding='utf-8')" && python test_pipeline.py
  or (PowerShell): $env:PYTHONIOENCODING="utf-8"; python test_pipeline.py
"""
import os
import json
import smtplib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
REPORT_TO      = os.getenv("REPORT_TO", "")

SEP  = "=" * 60
PASS = "  [PASS]"
FAIL = "  [FAIL]"
WARN = "  [WARN]"


def section(title: str):
    print(f"\n{SEP}\n  {title}\n{SEP}")


# ── 1. Environment variables ─────────────────────────────────────────────────────
section("TEST 1 -- Environment Variables (.env)")

checks = {
    "SERPER_API_KEY":           SERPER_API_KEY,
    "GEMINI_API_KEY":           GEMINI_API_KEY,
    "GEMINI_MODEL":             GEMINI_MODEL,
    "SMTP_USER":                SMTP_USER,
    "SMTP_PASSWORD":            SMTP_PASSWORD,
    "REPORT_TO":                REPORT_TO,
}
all_env_ok = True
for key, val in checks.items():
    if val and val not in ("YOUR_SERPER_API_KEY_HERE", "your_key_here"):
        masked = val[:14] + "..." if len(val) > 14 else val
        print(f"{PASS} {key} = {masked}")
    else:
        print(f"{FAIL} {key} is MISSING or still a placeholder")
        all_env_ok = False


# ── 2. Serper API (serper.dev) ───────────────────────────────────────────────────
section("TEST 2 -- Serper API Key (serper.dev)")

if not SERPER_API_KEY:
    print(f"{FAIL} SERPER_API_KEY not set in .env. Get yours at https://serper.dev")
else:
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            json={"q": "test", "num": 1},
            timeout=10,
        )
        if resp.status_code == 200:
            print(f"{PASS} Serper API key is valid")
            data = resp.json()
            print(f"         Credits : check at https://serper.dev/dashboard")
        elif resp.status_code in (401, 403):
            print(f"{FAIL} Invalid Serper API key (HTTP {resp.status_code})")
            print(f"         Get a key at: https://serper.dev")
        else:
            print(f"{WARN} Unexpected HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"{FAIL} Request failed: {e}")


# ── 3. Serper LinkedIn search (live test) ────────────────────────────────────────
section("TEST 3 -- Serper API: LinkedIn Compliance Search (Live)")

if SERPER_API_KEY:
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            json={
                "q":       "site:linkedin.com/posts compliance BFSI India",
                "tbs":     "qdr:d",
                "num":     5,
                "gl":      "in",
                "hl":      "en"
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data    = resp.json()
            organic = data.get("organic", [])
            print(f"{PASS} Search returned {len(organic)} LinkedIn results")
            for i, r in enumerate(organic[:3], 1):
                print(f"\n         Result {i}:")
                print(f"           Title   : {r.get('title', '')[:70]}")
                print(f"           URL     : {r.get('link', '')[:70]}")
                print(f"           Date    : {r.get('date', 'n/a')}")
                print(f"           Snippet : {r.get('snippet', '')[:100]}...")
        else:
            print(f"{FAIL} HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"{FAIL} Exception: {e}")
else:
    print(f"{WARN} Skipped -- SERPER_API_KEY not set")


# ── 4. Gemini API ────────────────────────────────────────────────────────────────
section(f"TEST 4 -- Google Gemini API (model: {GEMINI_MODEL})")

try:
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents='Reply with exactly the word: OK',
        config=genai_types.GenerateContentConfig(temperature=0),
    )
    print(f"{PASS} Gemini responded: '{response.text.strip()}'")
    print(f"         Model used: {GEMINI_MODEL}")
except Exception as e:
    err = str(e)
    if "429" in err or "RESOURCE_EXHAUSTED" in err:
        print(f"{WARN} Gemini quota exhausted (429). Pipeline will use rule-based fallback.")
        print(f"         Options:")
        print(f"           - Wait for daily quota reset (free tier)")
        print(f"           - Add billing at https://aistudio.google.com")
        print(f"           - Try GEMINI_MODEL=gemini-1.5-flash-8b (higher free quota)")
    else:
        print(f"{FAIL} Gemini error: {err[:200]}")


# ── 5. SMTP Email ────────────────────────────────────────────────────────────────
section("TEST 5 -- SMTP Email Connection")

try:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
    print(f"{PASS} SMTP login successful ({SMTP_USER} via {SMTP_HOST}:{SMTP_PORT})")
    print(f"         Recipients: {REPORT_TO}")
except smtplib.SMTPAuthenticationError:
    print(f"{FAIL} SMTP auth failed -- check SMTP_USER and SMTP_PASSWORD (use Gmail App Password)")
except Exception as e:
    print(f"{FAIL} SMTP failed: {e}")


# ── 6. Module imports ────────────────────────────────────────────────────────────
section("TEST 6 -- Module Imports")

try:
    from scraper      import fetch_posts
    from deduplicator import deduplicate
    from enricher     import enrich_batch
    from reporter     import generate_report, save_report, send_email_report
    print(f"{PASS} All pipeline modules imported successfully")
except Exception as e:
    print(f"{FAIL} Import error: {e}")


# ── Summary ──────────────────────────────────────────────────────────────────────
section("SUMMARY")
print("  Fix any [FAIL] items above, then run:  python main.py")
print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
