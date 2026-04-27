"""
enricher.py - Optimised AI enrichment using Google Gemini with rule-based fallback.

Token-saving pipeline:
  1. Sort posts by signal score (highest first)
  2. Only top TOP_POSTS_FOR_LLM posts are eligible for Gemini
  3. Each post must score >= MIN_SIGNAL_SCORE to reach Gemini
  4. Post content is truncated to MAX_CHARS_FOR_LLM before the Gemini call
  5. Minimal JSON prompt is used (< 50 tokens of instructions)
  6. 5-second delay between Gemini calls to respect free-tier rate limits
  7. All other posts fall back to fast rule-based enrichment
"""
import json
import re
import time
import requests
from bs4 import BeautifulSoup
import dateparser

from config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    TOP_POSTS_FOR_LLM, MAX_CHARS_FOR_LLM, SEMANTIC_THRESHOLD,
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

# ── Constants ────────────────────────────────────────────────────────────────────
EVENT_TYPES = ["Conference", "Summit", "Webinar", "Workshop", "Meetup", "Other"]

# ── Minimal Gemini prompt (keeps token usage extremely low) ──────────────────────
_GEMINI_PROMPT = """\
Extract event intelligence from this LinkedIn post in India's financial sector.
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

POST:
{content}"""


# ── Gemini enrichment ────────────────────────────────────────────────────────────

def _gemini_enrich(content: str) -> dict | None:
    """Call Gemini with a truncated post and minimal prompt. Returns None on failure."""
    if not _client:
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
    
    event_platforms = ["eventbrite", "hubilo", "airmeet", "townscript", "10times", "lu.ma", "cvent"]
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

def normalize_location(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("virtual", "online", "zoom", "teams", "webcast")):
        return "Online/Virtual"
    elif "mumbai" in low or "bombay" in low: return "Mumbai"
    elif "delhi" in low or "ncr" in low: return "Delhi NCR"
    elif "bengaluru" in low or "bangalore" in low: return "Bengaluru"
    elif "chennai" in low: return "Chennai"
    return text if text and text != "Not specified" else "Not specified"

# ── Rule-based fallback ──────────────────────────────────────────────────────────

def _rule_based_enrich(content: str) -> dict:
    low = content.lower()

    event_type = normalize_event_type(low)
    location = normalize_location(low)

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
    data = None
    if use_gemini:
        data = _gemini_enrich(content)
        
    if not data:
        data = _rule_based_enrich(content)
    else:
        # Normalize Gemini output
        data["event_type"] = normalize_event_type(data.get("event_type", ""))
        data["location"] = normalize_location(data.get("location", ""))
        if data.get("event_dates") and data.get("event_dates") != "Not specified":
            data["event_dates"] = normalize_date(data.get("event_dates", ""))
        if not data.get("official_link") or data.get("official_link") == "Not specified":
            external_links = extract_external_links(content)
            if external_links:
                data["official_link"] = external_links[0]
                
    data["source_name"] = post.get("author_name", "Unknown")
    return {**post, **data}


def enrich_batch(posts: list[dict]) -> list[dict]:
    """
    Token-optimised batch enrichment:
      1. Sort by signal score (desc)
      2. Top TOP_POSTS_FOR_LLM posts scoring >= MIN_SIGNAL_SCORE go to Gemini
         (with 5-second rate-limit delay between calls)
      3. All remaining posts are rule-based only
    """
    if not posts:
        return []

    # Sort highest-signal posts first
    sorted_posts = sorted(posts, key=lambda p: p.get("score", 0), reverse=True)

    # Posts with semantic score >= SEMANTIC_THRESHOLD qualify for Gemini
    # (score is 0.0–1.0 from the embedding model)
    gemini_candidates = [
        p for p in sorted_posts
        if p.get("score", 0.0) >= SEMANTIC_THRESHOLD
    ][:TOP_POSTS_FOR_LLM]

    gemini_ids = {p["id"] for p in gemini_candidates}

    gemini_count  = len(gemini_candidates)
    fallback_count = len(posts) - gemini_count

    print(f"[Enricher] {gemini_count} posts → Gemini  |  {fallback_count} posts → rule-based")
    if gemini_count == 0:
        print(f"[Enricher] No posts met SEMANTIC_THRESHOLD={SEMANTIC_THRESHOLD}. All rule-based.")

    enriched: list[dict] = []
    gemini_call_n = 0

    for post in sorted_posts:
        use_gemini = post["id"] in gemini_ids

        try:
            name = post.get("author_name", "Unknown")
            tag  = "Gemini" if use_gemini else "rule"
            score = post.get("score", 0)
            print(f"  [Enricher] [{tag}] score={score}  {name}")
        except UnicodeEncodeError:
            print(f"  [Enricher] [{'Gemini' if use_gemini else 'rule'}] [Non-ASCII Name]")

        if use_gemini:
            gemini_call_n += 1
            if gemini_call_n > 1:
                # Rate-limit: 5-second pause between Gemini calls
                print(f"  [Enricher] Sleeping 5s (rate limit)...")
                time.sleep(5)

        enriched.append(enrich_post(post, use_gemini=use_gemini))

    return enriched
