"""
scraper.py - Fetches LinkedIn posts via Serper API (Google Search).

Flow:
  1. Rotate through SEARCH_QUERIES (DAILY_QUERY_LIMIT queries per run)
  2. For each query → call Serper API with site:linkedin.com/posts filter
  3. Parse organic results → best-effort og:meta scrape for richer content
  4. Hard filters: exclusion keywords, low-quality, India context (cheap string checks)
  5. Semantic filter: cosine similarity against TARGET_CONCEPTS (replaces keyword scoring)
  6. Attach semantic score to each passing post for downstream ranking
"""
import hashlib
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

from config import (
    SERPER_API_KEY,
    SEARCH_QUERIES,
    DAILY_QUERY_LIMIT,
    SENIOR_TITLES,
    INDIA_HARD_SIGNALS,
    EVENT_HARD_SIGNALS,
    HIGH_PRIORITY_SOURCES,
    MEDIUM_PRIORITY_SOURCES,
    EXCLUDE_KEYWORDS,
    SEMANTIC_THRESHOLD,
)
from semantic_filter import is_relevant

SERPER_URL = "https://google.serper.dev/search"

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Hard filter helpers (cheap — run before semantic engine) ──────────────────────

def is_excluded(text: str) -> bool:
    """Drop posts matching any exclusion keyword."""
    lower = text.lower()
    return any(kw in lower for kw in EXCLUDE_KEYWORDS)


def is_low_quality(text: str) -> bool:
    """Drop posts that are too short or are hashtag spam."""
    words = text.split()
    if len(words) < 15:
        return True
    hashtag_ratio = text.count("#") / max(len(words), 1)
    if hashtag_ratio > 0.30:
        return True
    return False


def has_india_context(text: str) -> bool:
    """Must mention at least one India / Indian-regulator signal."""
    lower = text.lower()
    return any(kw in lower for kw in INDIA_HARD_SIGNALS)


def has_event_intent(text: str) -> bool:
    """Must mention an event-related keyword."""
    lower = text.lower()
    return any(kw in lower for kw in EVENT_HARD_SIGNALS)


# ── Utility helpers ───────────────────────────────────────────────────────────────

def make_post_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def content_hash(text: str) -> str:
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalised.encode()).hexdigest()


def classify_source_priority(company: str) -> str:
    low = company.lower()
    if any(k in low for k in HIGH_PRIORITY_SOURCES):   return "High Priority"
    if any(k in low for k in MEDIUM_PRIORITY_SOURCES): return "Medium Priority"
    return "Other"


def is_senior_leader(title: str) -> bool:
    return any(t in title.lower() for t in SENIOR_TITLES)


def extract_hashtags(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"#\w+", text)))


# ── Daily query rotation ──────────────────────────────────────────────────────────

from datetime import datetime as _dt

def get_daily_queries() -> list[str]:
    """
    Pick DAILY_QUERY_LIMIT queries for today using day-of-month as offset.
    Cycles through the full SEARCH_QUERIES list over time.
    If DAILY_QUERY_LIMIT is None, returns all queries.
    """
    if DAILY_QUERY_LIMIT is None:
        return SEARCH_QUERIES

    day   = _dt.now().day
    start = (day * DAILY_QUERY_LIMIT) % len(SEARCH_QUERIES)
    end   = start + DAILY_QUERY_LIMIT
    if end <= len(SEARCH_QUERIES):
        return SEARCH_QUERIES[start:end]
    return SEARCH_QUERIES[start:] + SEARCH_QUERIES[:end - len(SEARCH_QUERIES)]


# ── Date parsing ──────────────────────────────────────────────────────────────────

def parse_relative_date(date_str: str) -> datetime | None:
    """
    Convert Serper API relative date strings to aware UTC datetime.
    Handles: '3 hours ago', '1 day ago', 'Apr 21, 2026', '2026-04-21', ISO 8601.
    """
    if not date_str:
        return None
    now = datetime.now(timezone.utc)
    s   = date_str.strip().lower()

    m = re.search(r"(\d+)\s+hour", s)
    if m: return now - timedelta(hours=int(m.group(1)))

    m = re.search(r"(\d+)\s+min", s)
    if m: return now - timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s+day", s)
    if m: return now - timedelta(days=int(m.group(1)))

    m = re.search(r"(\d+)\s+week", s)
    if m: return now - timedelta(weeks=int(m.group(1)))

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip()[:20], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    return None


def is_within_last_24_hours(date_str: str) -> bool:
    dt = parse_relative_date(date_str)
    if dt is None:
        return True  # can't parse → include (over-include is safer)
    return dt >= datetime.now(timezone.utc) - timedelta(hours=24)


def _extract_author_from_title(title: str) -> str:
    m = re.match(r"^(.+?)\s+on\s+LinkedIn", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return title.split(":")[0].strip() if ":" in title else title.strip()


# ── Best-effort LinkedIn page scrape ─────────────────────────────────────────────

def _scrape_linkedin_meta(url: str) -> dict:
    result = {}
    try:
        resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code != 200:
            return result
        soup = BeautifulSoup(resp.text, "lxml")

        for sel in ['meta[property="og:description"]', 'meta[name="description"]']:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                result["content"] = tag["content"].strip()
                break

        og_title = soup.select_one('meta[property="og:title"]')
        if og_title and og_title.get("content"):
            result["author_name"] = _extract_author_from_title(og_title["content"])

        for sel in ['meta[property="article:published_time"]', 'meta[property="og:updated_time"]']:
            tag = soup.select_one(sel)
            if tag and tag.get("content"):
                result["scraped_date"] = tag["content"]
                break

    except Exception:
        pass

    return result


# ── Serper API search ─────────────────────────────────────────────────────────────

def _serper_search(query: str) -> list[dict]:
    full_query = f'site:linkedin.com/posts {query}'
    headers = {
        'X-API-KEY': SERPER_API_KEY,
        'Content-Type': 'application/json'
    }
    payload = {
        "q": full_query,
        "tbs": "qdr:d",
        "num": 5,
        "gl": "in",
        "hl": "en"
    }
    try:
        resp = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("organic", [])
        print(f"  [Serper] '{query}' → {len(results)} results")
        return results
    except Exception as e:
        print(f"  [Serper] Search failed for '{query}': {e}")
        return []


def _parse_serper_result(result: dict) -> dict | None:
    """
    Convert a single Serper API organic result to a canonical post dict.
    Returns None if the post fails any filter.
    """
    post_url = result.get("link", "")

    if "linkedin.com" not in post_url or "/posts/" not in post_url:
        return None

    post_url    = re.sub(r"\?.*$", "", post_url)
    title_raw   = result.get("title", "")
    snippet     = result.get("snippet", "")
    date_str    = result.get("date", "")
    author_name = _extract_author_from_title(title_raw) if title_raw else "Unknown"

    meta         = _scrape_linkedin_meta(post_url)
    content      = meta.get("content") or snippet or ""
    author_name  = meta.get("author_name") or author_name
    scraped_date = meta.get("scraped_date", "")
    effective_date = scraped_date or date_str

    # ── Hard filters (cheap, no model needed) ────────────────────────────────────
    if not content.strip():
        return None
    if is_excluded(content):
        return None
    if is_low_quality(content):
        return None
    if not has_india_context(content):
        return None

    if effective_date and not is_within_last_24_hours(effective_date):
        return None

    # ── Semantic filter (replaces all keyword scoring) ────────────────────────────
    passes, sem_score, matched_concept = is_relevant(content)
    
    if has_event_intent(content):
        sem_score = min(1.0, sem_score + 0.15)
        if sem_score >= SEMANTIC_THRESHOLD:
            passes = True

    if not passes:
        print(f"  [Scraper] Dropped (score={sem_score:.2f}): {author_name}")
        return None

    print(f"  [Scraper] ✓ Kept (score={sem_score:.2f}, concept='{matched_concept}'): {author_name}")

    # Format post date
    dt = parse_relative_date(effective_date)
    post_date = (
        dt.strftime("%Y-%m-%d %H:%M UTC")
        if dt else
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )

    return {
        "id":                   make_post_id(post_url),
        "content_hash":         content_hash(content),
        "author_name":          author_name,
        "title":                "",
        "company":              "",
        "source_priority":      classify_source_priority(author_name),
        "is_senior":            False,
        "content":              content,
        "post_url":             post_url,
        "post_date":            post_date,
        "score":                sem_score,          # semantic similarity (0.0–1.0)
        "matched_concept":      matched_concept,    # which signal category matched
        "likes":                0,
        "comments":             0,
        "hashtags":             extract_hashtags(content),
        "category":             "",
        "tone":                 "",
        "regulators_mentioned": [],
        "summary":              "",
        "is_repost":            False,
        "is_duplicate":         False,
        "source":               "serper",
    }


# ── Public entry point ────────────────────────────────────────────────────────────

def fetch_posts() -> list[dict]:
    """
    Run today's rotated queries via Serper API.
    Each surviving post has a 'score' (semantic similarity) and 'matched_concept'.
    """
    if not SERPER_API_KEY:
        print("[Scraper] SERPER_API_KEY not set — cannot fetch posts.")
        return []

    queries   = get_daily_queries()
    all_posts: list[dict] = []
    seen_ids:  set[str]   = set()

    print(f"[Scraper] Running {len(queries)}/{len(SEARCH_QUERIES)} queries today (daily rotation).")

    for i, query in enumerate(queries, 1):
        print(f"\n[Scraper] Query {i}/{len(queries)}: '{query}'")
        for result in _serper_search(query):
            post = _parse_serper_result(result)
            if post and post["id"] not in seen_ids:
                seen_ids.add(post["id"])
                all_posts.append(post)

    print(f"\n[Scraper] {len(all_posts)} posts passed all filters.")
    return all_posts
