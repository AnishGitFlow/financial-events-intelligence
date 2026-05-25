"""
enricher.py - Optimised AI enrichment using Google Gemini with rule-based fallback.

Token-saving pipeline:
  1. Prefer cleaner source types for optional Gemini enrichment
  2. Only top TOP_POSTS_FOR_LLM posts are eligible for Gemini
  3. Post content is truncated to MAX_CHARS_FOR_LLM before the Gemini call
  4. Minimal JSON prompt is used
  5. 5-second delay between Gemini calls to respect free-tier rate limits
  6. All other posts fall back to fast rule-based enrichment
"""
import json
import re
import time
import requests
from bs4 import BeautifulSoup
import dateparser

from config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    TOP_POSTS_FOR_LLM, MAX_CHARS_FOR_LLM,
    EVENT_NORMALIZATION_MAPPINGS,
)

# ── Gemini client (optional) ────────────────────────────────────────────────────
try:
    from google import genai
    from google.genai import types as genai_types
    _client = (
        genai.Client(api_key=GEMINI_API_KEY)
        if GEMINI_API_KEY and GEMINI_API_KEY not in ("", "your_gemini_api_key_here")
        else None
    )
except Exception:
    _client = None
    genai_types = None

# Fail-fast quota flag: set to True on first 429 / RESOURCE_EXHAUSTED error.
# All subsequent posts in the same run immediately fall back to rule-based.
_gemini_quota_exhausted: bool = False

# ── Constants ────────────────────────────────────────────────────────────────────
EVENT_TYPES = ["Conference", "Summit", "Webinar", "Workshop", "Meetup", "Other"]

# ── Minimal Gemini prompt (keeps token usage extremely low) ──────────────────────
_GEMINI_PROMPT = """\
Extract event intelligence from this search result or post in India's financial sector.
Return ONLY valid JSON, no markdown. Never hallucinate missing information.
Use "Not specified" for missing fields.

{{
  "event_name": "<name of event or 'Not specified'>",
  "event_type": "<one of: {event_types}>",
  "event_dates": "<dates or 'Not specified'>",
  "location": "<city/venue or 'Online/Virtual' or 'Not specified'>",
  "organiser": "<organising company or 'Not specified'>",
  "target_audience": "<who should attend or 'Not specified'>",
  "official_link": "<registration/event URL or 'Not specified'>",
  "description": "<2-3 lines factual summary>"
}}

CONTENT:
{content}"""


# ── Gemini enrichment ────────────────────────────────────────────────────────────

def _gemini_enrich(content: str) -> dict | None:
    """Call Gemini with a truncated post and minimal prompt. Returns None on failure."""
    global _gemini_quota_exhausted

    if not _client or _gemini_quota_exhausted:
        return None

    clean_text = content[:MAX_CHARS_FOR_LLM]
    prompt = _GEMINI_PROMPT.format(
        event_types=", ".join(EVENT_TYPES),
        content=clean_text,
    )
    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(temperature=0.1),
        )
        text = response.text.strip()
        # Strip code fences if present
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"```$", "", text).strip()
        data = json.loads(text)
        # Validate expected keys
        required = {"event_name", "event_type", "event_dates", "location", "organiser", "description"}
        if required.issubset(data.keys()):
            return data
    except Exception as e:
        err = str(e)
        # Detect hard quota signals and fail-fast for the rest of this run
        quota_signals = (
            "429", "RESOURCE_EXHAUSTED", "daily quota",
            "request limit 0", "input token limit 0",
        )
        if any(sig in err for sig in quota_signals):
            _gemini_quota_exhausted = True
            print(
                "[Enricher] Gemini unavailable: quota exhausted. "
                "Falling back to rule-based enrichment for remaining posts."
            )
        else:
            print(f"  [Enricher] Gemini failed: {e}")
    return None


# ── Extraction Helpers ────────────────────────────────────────────────────────────

def extract_external_links(content: str) -> list[str]:
    links = re.findall(r'(https?://[^\s]+)', content)
    external = []
    for link in links:
        link = link.strip('.,)"\'')
        if "linkedin.com" not in link:
            external.append(link)
    
    event_platforms = ["eventbrite", "hubilo", "airmeet", "townscript", "10times", "lu.ma", "cvent", "allevents", "meraevents", "explara"]
    def score_link(l):
        return sum(1 for p in event_platforms if p in l.lower())
    
    return sorted(external, key=score_link, reverse=True)

def scrape_event_page(url: str) -> dict:
    try:
        resp = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            title = soup.title.string if soup.title else ""
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            desc = meta_desc['content'] if meta_desc else ""
            return {"title": title.strip(), "description": desc.strip()}
    except Exception:
        pass
    return {}

def extract_event_name(content: str, scraped_title: str = "") -> str:
    if scraped_title:
        return scraped_title

    patterns = [
        r"(?i)(?:Join us for|Announcing the|Register now for|Excited to host|Inviting you to|Upcoming webinar:)\s+([A-Z][^.!?\n]+(?:\s+[A-Z][^.!?\n]+)*)",
        r"(?i)(?:Save the date for)\s+([A-Z][^.!?\n]+(?:\s+[A-Z][^.!?\n]+)*)"
    ]
    for p in patterns:
        m = re.search(p, content)
        if m:
            title = m.group(1).strip()
            if len(title) > 5:
                return title

    m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Conference|Summit|Webinar|Workshop|Meetup|Conclave))", content)
    if m:
        return m.group(1).strip()

    sentences = content.split('\n')
    for s in sentences:
        s = s.strip()
        if 10 < len(s) < 80:
            return s

    return "Not specified"

def normalize_date(date_text: str) -> str:
    if not date_text or date_text == "Not specified":
        return "Not specified"
    parsed = dateparser.parse(date_text, settings={'STRICT_PARSING': False})
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return date_text

def normalize_event_type(text: str) -> str:
    low = text.lower()
    for k, v in EVENT_NORMALIZATION_MAPPINGS.items():
        if k in low:
            return v
    return "Other"

# Known city signals: order matters (first match wins).
_CITY_SIGNALS: list[tuple[str, str]] = [
    ("virtual",    "Online/Virtual"), ("online",    "Online/Virtual"),
    ("zoom",       "Online/Virtual"), ("teams",     "Online/Virtual"),
    ("webcast",    "Online/Virtual"),
    ("mumbai",     "Mumbai"),         ("bombay",    "Mumbai"),
    ("delhi",      "Delhi NCR"),      ("ncr",       "Delhi NCR"),
    ("bengaluru",  "Bengaluru"),      ("bangalore", "Bengaluru"),
    ("chennai",    "Chennai"),
    ("hyderabad",  "Hyderabad"),
    ("pune",       "Pune"),
    ("kolkata",    "Kolkata"),
]


def normalize_location(text: str) -> str:
    """
    Map a location string to a canonical city name or sentinel.

    Contract:
      - Always returns one of the known city strings, "Online/Virtual",
        or "Not specified".
      - NEVER returns arbitrary freeform text.

    Do NOT pass full post bodies here — only pass a field that is already
    expected to contain a location (e.g. Gemini's ``location`` output).
    """
    if not text or text.strip().lower() in ("", "not specified"):
        return "Not specified"
    low = text.lower()
    for signal, canonical in _CITY_SIGNALS:
        if signal in low:
            return canonical
    # No known city found — return the sentinel, never the raw input.
    return "Not specified"

# ── Rule-based fallback ──────────────────────────────────────────────────────────

def _rule_based_enrich(content: str) -> dict:
    low = content.lower()

    event_type = normalize_event_type(low)

    # Extract location: scan for known cities/virtual signals only.
    # Do NOT pass the full content to normalize_location — its fallback
    # returns the input string verbatim, which would corrupt the location badge.
    _LOCATION_SIGNALS = [
        ("virtual", "Online/Virtual"), ("online", "Online/Virtual"),
        ("zoom", "Online/Virtual"), ("webcast", "Online/Virtual"),
        ("mumbai", "Mumbai"), ("bombay", "Mumbai"),
        ("delhi", "Delhi NCR"), (" ncr", "Delhi NCR"),
        ("bengaluru", "Bengaluru"), ("bangalore", "Bengaluru"),
        ("chennai", "Chennai"), ("hyderabad", "Hyderabad"),
        ("pune", "Pune"), ("kolkata", "Kolkata"),
    ]
    location = "Not specified"
    for signal, city in _LOCATION_SIGNALS:
        if signal in low:
            location = city
            break

    external_links = extract_external_links(content)
    official_link = external_links[0] if external_links else "Not specified"

    scraped_meta = {}
    if official_link != "Not specified":
        scraped_meta = scrape_event_page(official_link)

    event_name = extract_event_name(content, scraped_meta.get("title", ""))

    description = scraped_meta.get("description", "")
    if not description:
        sentences = re.split(r"(?<=[.!?])\s+", content.strip())
        description = " ".join(sentences[:3])
        if len(description) > 300:
            description = description[:297] + "..."

    event_dates = "Not specified"
    date_match = re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}(?:th|st|nd|rd)?(?:, \d{4})?\b', content, re.IGNORECASE)
    if not date_match:
        date_match = re.search(r'\b(?:\d{1,2}(?:th|st|nd|rd)? (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*)\b', content, re.IGNORECASE)
    
    if date_match:
        event_dates = normalize_date(date_match.group(0))

    return {
        "event_name": event_name,
        "event_type": event_type,
        "event_dates": event_dates,
        "location": location,
        "organiser": "Not specified",
        "target_audience": "Not specified",
        "official_link": official_link,
        "description": description,
    }


# ── Public API ───────────────────────────────────────────────────────────────────

def enrich_post(post: dict, use_gemini: bool = False) -> dict:
    """
    Enrich a single post.
    If use_gemini=True, attempt Gemini first; fall back to rule-based on failure.
    If use_gemini=False, use rule-based only (no API call).
    """
    content = post.get("content", "")
    gemini_data = None
    if use_gemini:
        gemini_data = _gemini_enrich(content)

    gemini_succeeded = gemini_data is not None

    if gemini_succeeded:
        data = gemini_data
        # Normalize Gemini output
        data["event_type"] = normalize_event_type(data.get("event_type", ""))
        data["location"] = normalize_location(data.get("location", ""))
        if data.get("event_dates") and data.get("event_dates") != "Not specified":
            data["event_dates"] = normalize_date(data.get("event_dates", ""))
        if not data.get("official_link") or data.get("official_link") == "Not specified":
            external_links = extract_external_links(content)
            if external_links:
                data["official_link"] = external_links[0]
    else:
        data = _rule_based_enrich(content)

    if (
        data.get("official_link") in (None, "", "Not specified")
        and post.get("source_type") != "linkedin_posts"
        and post.get("post_url")
    ):
        data["official_link"] = post["post_url"]

    data["source_name"] = post.get("source_domain") or post.get("author_name", "Unknown")
    enriched_post = {**post, **data}

    # Stamp enrichment method into the pipeline trace
    trace = enriched_post.get("pipeline_trace")
    if isinstance(trace, dict):
        trace["enrichment_method"] = "gemini" if gemini_succeeded else "rule-based"

    return enriched_post


def enrich_batch(posts: list[dict]) -> list[dict]:
    """
    Token-optimised batch enrichment:
      1. Sort by source preference.
      2. Top TOP_POSTS_FOR_LLM posts go to Gemini with a 5-second delay.
      3. All remaining posts are rule-based only.
      4. If Gemini returns a quota error on any call, _gemini_quota_exhausted is
         set to True and ALL remaining posts in this run fall back immediately
         without sleeping.
    """
    global _gemini_quota_exhausted

    if not posts:
        return []

    source_rank = {
        "official_event_pages": 0,
        "registration_pages": 1,
        "industry_bodies": 2,
        "company_pages": 3,
        "linkedin_posts": 4,
        "media_pr": 5,
        "community_events": 6,
        "open_web_discovery": 7,
    }
    sorted_posts = sorted(posts, key=lambda p: source_rank.get(p.get("source_type"), 9))
    gemini_candidates = sorted_posts[:TOP_POSTS_FOR_LLM]

    gemini_ids = {p["id"] for p in gemini_candidates}

    gemini_count  = len(gemini_candidates)
    fallback_count = len(posts) - gemini_count

    print(f"[Enricher] {gemini_count} posts → Gemini  |  {fallback_count} posts → rule-based")
    enriched: list[dict] = []
    gemini_call_n = 0

    for post in sorted_posts:
        use_gemini = post["id"] in gemini_ids and not _gemini_quota_exhausted

        try:
            name = post.get("author_name", "Unknown")
            tag  = "Gemini" if use_gemini else "rule"
            source_type = post.get("source_type", "unknown")
            print(f"  [Enricher] [{tag}] source={source_type}  {name}")
        except UnicodeEncodeError:
            print(f"  [Enricher] [{'Gemini' if use_gemini else 'rule'}] [Non-ASCII Name]")

        if use_gemini:
            gemini_call_n += 1
            if gemini_call_n > 1 and not _gemini_quota_exhausted:
                # Rate-limit: 5-second pause between Gemini calls
                print(f"  [Enricher] Sleeping 5s (rate limit)...")
                time.sleep(5)

        enriched.append(enrich_post(post, use_gemini=use_gemini))

    return enriched
