"""
scraper.py - Fetches financial event signals via Serper API.

Pipeline:
  Serper search -> source inference -> hard filters -> normalized result.
"""
import hashlib
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import (
    SERPER_API_KEY,
    SERPER_RECENCY,
    SERPER_TBS_BY_RECENCY,
    SEARCH_SOURCE_QUERIES,
    DAILY_QUERY_LIMIT,
    FINANCE_DOMAIN_SIGNALS,
    EVENT_HARD_SIGNALS,
    INDIA_LOCATION_SIGNALS,
    NEGATIVE_SIGNALS,
    EXCLUDE_KEYWORDS,
    SOURCE_TYPE_LABELS,
    REGISTRATION_DOMAINS,
    COMMUNITY_EVENT_DOMAINS,
    INDUSTRY_BODY_DOMAINS,
    MEDIA_PR_DOMAINS,
    COMPANY_DOMAINS,
    INDIA_FOCUSED_DOMAINS,
)

SERPER_URL = "https://google.serper.dev/search"

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PRIMARY_SOURCE_ORDER = {
    "official_event_pages": 0,
    "registration_pages": 1,
    "industry_bodies": 2,
    "company_pages": 3,
    "linkedin_posts": 4,
    "media_pr": 5,
    "community_events": 6,
    "open_web_discovery": 7,
}


def _contains_any(text: str, signals: list[str]) -> list[str]:
    lower = text.lower()
    return [signal for signal in signals if signal in lower]


def get_finance_matches(text: str) -> list[str]:
    return _contains_any(text, FINANCE_DOMAIN_SIGNALS)


def get_event_matches(text: str) -> list[str]:
    return _contains_any(text, EVENT_HARD_SIGNALS)


def get_location_matches(text: str) -> list[str]:
    return _contains_any(text, INDIA_LOCATION_SIGNALS)


def get_negative_matches(text: str) -> list[str]:
    return _contains_any(text, NEGATIVE_SIGNALS)


def get_excluded_matches(text: str) -> list[str]:
    return _contains_any(text, EXCLUDE_KEYWORDS)


def is_low_quality(text: str, source_type: str) -> bool:
    words = text.split()
    min_words = 8 if source_type != "linkedin_posts" else 15
    if len(words) < min_words:
        return True
    hashtag_ratio = text.count("#") / max(len(words), 1)
    return source_type == "linkedin_posts" and hashtag_ratio > 0.30


def make_post_id(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


def content_hash(text: str) -> str:
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalised.encode()).hexdigest()


def extract_hashtags(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"#\w+", text)))


def get_daily_queries() -> list[dict]:
    if DAILY_QUERY_LIMIT is None:
        return SEARCH_SOURCE_QUERIES

    day = datetime.now().day
    start = (day * DAILY_QUERY_LIMIT) % len(SEARCH_SOURCE_QUERIES)
    end = start + DAILY_QUERY_LIMIT
    if end <= len(SEARCH_SOURCE_QUERIES):
        return SEARCH_SOURCE_QUERIES[start:end]
    return SEARCH_SOURCE_QUERIES[start:] + SEARCH_SOURCE_QUERIES[:end - len(SEARCH_SOURCE_QUERIES)]


def parse_relative_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    now = datetime.now(timezone.utc)
    s = date_str.strip().lower()

    for unit, delta in (
        ("hour", lambda n: timedelta(hours=n)),
        ("min", lambda n: timedelta(minutes=n)),
        ("day", lambda n: timedelta(days=n)),
        ("week", lambda n: timedelta(weeks=n)),
    ):
        m = re.search(rf"(\d+)\s+{unit}", s)
        if m:
            return now - delta(int(m.group(1)))

    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip()[:20], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def is_within_recency_window(date_str: str) -> bool:
    dt = parse_relative_date(date_str)
    if dt is None:
        return True

    days = {"day": 1, "week": 7, "month": 31}.get(SERPER_RECENCY, 1)
    return dt >= datetime.now(timezone.utc) - timedelta(days=days)


def _extract_author_from_title(title: str) -> str:
    m = re.match(r"^(.+?)\s+on\s+LinkedIn", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return title.split(":")[0].strip() if ":" in title else title.strip()


def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _domain_matches(domain: str, patterns: list[str]) -> bool:
    return any(pattern in domain for pattern in patterns)


def _is_india_focused_source(domain: str) -> bool:
    return (
        domain.endswith(".in")
        or domain.endswith(".co.in")
        or domain.endswith(".org.in")
        or _domain_matches(domain, INDIA_FOCUSED_DOMAINS)
    )


def _infer_source_type(domain: str, fallback: str) -> str:
    if "linkedin.com" in domain:
        return "linkedin_posts"
    if _domain_matches(domain, REGISTRATION_DOMAINS):
        return "registration_pages"
    if _domain_matches(domain, COMMUNITY_EVENT_DOMAINS):
        return "community_events"
    if _domain_matches(domain, INDUSTRY_BODY_DOMAINS):
        return "industry_bodies"
    if _domain_matches(domain, MEDIA_PR_DOMAINS):
        return "media_pr"
    if _domain_matches(domain, COMPANY_DOMAINS):
        return "company_pages"
    return fallback or "open_web_discovery"


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


def _serper_search(query_spec: dict) -> list[dict]:
    full_query = query_spec["query"]
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "q": full_query,
        "tbs": SERPER_TBS_BY_RECENCY.get(SERPER_RECENCY, "qdr:d"),
        "num": 5,
        "gl": "in",
        "hl": "en",
    }
    try:
        resp = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("organic", [])
        print(f"  [Serper] '{full_query}' -> {len(results)} results")
        return results
    except Exception as e:
        print(f"  [Serper] Search failed for '{full_query}': {e}")
        return []


def _drop_reason(
    source_type: str,
    domain: str,
    finance_kws: list[str],
    event_kws: list[str],
    location_kws: list[str],
) -> str | None:
    if not finance_kws:
        return "missing finance signal"
    if not event_kws:
        return "missing event signal"

    india_ok = bool(location_kws) or _is_india_focused_source(domain)
    lenient_sources = {"official_event_pages", "registration_pages", "industry_bodies", "company_pages"}
    if source_type in lenient_sources:
        return None if india_ok or _is_india_focused_source(domain) else "weak India relevance"

    if not india_ok:
        return "weak India relevance"
    return None


def _parse_serper_result(result: dict, query_spec: dict) -> dict | None:
    post_url = re.sub(r"\?.*$", "", result.get("link", ""))
    if not post_url:
        return None

    title_raw = result.get("title", "").strip()
    snippet = result.get("snippet", "").strip()
    date_str = result.get("date", "")
    domain = _domain_from_url(post_url)
    source_type = _infer_source_type(domain, query_spec.get("source_type", "open_web_discovery"))
    query = query_spec["query"]
    query_mode = query_spec.get("query_mode", "open_web_discovery")

    is_linkedin_post = "linkedin.com" in domain and "/posts/" in post_url
    if source_type == "linkedin_posts" and not is_linkedin_post:
        print(f"  [Scraper] Dropped (unrelated domain/topic): {domain or post_url}")
        return None

    source_name = _extract_author_from_title(title_raw) if title_raw else domain or "Unknown"
    content_parts = [title_raw, snippet]
    scraped_date = ""

    if is_linkedin_post:
        meta = _scrape_linkedin_meta(post_url)
        if meta.get("content"):
            content_parts = [title_raw, meta["content"]]
        source_name = meta.get("author_name") or source_name
        scraped_date = meta.get("scraped_date", "")

    content = " ".join(part for part in content_parts if part).strip()
    effective_date = scraped_date or date_str

    if not content:
        print(f"  [Scraper] Dropped (empty content): {source_name}")
        return None

    excluded_kws = get_excluded_matches(content)
    if excluded_kws:
        print(f"  [Scraper] Dropped (absolute exclusion: {excluded_kws[:2]}): {source_name}")
        return None

    if is_low_quality(content, source_type):
        print(f"  [Scraper] Dropped (low quality): {source_name}")
        return None

    finance_kws = get_finance_matches(content)
    event_kws = get_event_matches(content)
    location_kws = get_location_matches(content)
    negative_kws = get_negative_matches(content)

    hard_negative = [k for k in negative_kws if k in (
        "us sec", "sec filing", "finra", "mifid", "european union", "us regulation"
    )]
    if hard_negative:
        print(f"  [Scraper] Dropped (unrelated domain/topic: {hard_negative[:2]}): {source_name}")
        return None
    if negative_kws and not (finance_kws and event_kws and location_kws):
        print(f"  [Scraper] Dropped (unrelated domain/topic: {negative_kws[:2]}): {source_name}")
        return None

    reason = _drop_reason(source_type, domain, finance_kws, event_kws, location_kws)
    if reason:
        print(f"  [Scraper] Dropped ({reason}): {source_name}")
        return None

    if effective_date and not is_within_recency_window(effective_date):
        return None

    print(
        f"  [Scraper] Kept [{SOURCE_TYPE_LABELS.get(source_type, source_type)} | "
        f"{domain or 'unknown domain'}]: {source_name}"
    )

    dt = parse_relative_date(effective_date)
    post_date = (
        dt.strftime("%Y-%m-%d %H:%M UTC")
        if dt else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )

    source_record = {
        "source_type": source_type,
        "source_domain": domain,
        "url": post_url,
        "title": title_raw,
        "query": query,
    }

    pipeline_trace = {
        "query": query,
        "serper_full_query": query,
        "query_mode": query_mode,
        "source_type": source_type,
        "source_domain": domain,
        "hard_filters": {
            "finance_keywords_matched": finance_kws,
            "event_keywords_matched": event_kws,
            "location_keywords_matched": location_kws,
            "negative_keywords_found": negative_kws,
            "exclusion_keywords_found": excluded_kws,
        },
    }

    return {
        "id": make_post_id(post_url),
        "content_hash": content_hash(content),
        "source_type": source_type,
        "source_domain": domain,
        "source_name": domain or source_name,
        "author_name": source_name,
        "title": title_raw,
        "content": content,
        "snippet": snippet,
        "post_url": post_url,
        "url": post_url,
        "post_date": post_date,
        "query": query,
        "serper_full_query": query,
        "supporting_sources": [source_record],
        "likes": 0,
        "comments": 0,
        "hashtags": extract_hashtags(content),
        "is_repost": False,
        "is_duplicate": False,
        "source": "serper",
        "pipeline_trace": pipeline_trace,
    }


def fetch_posts() -> list[dict]:
    if not SERPER_API_KEY:
        print("[Scraper] SERPER_API_KEY not set - cannot fetch posts.")
        return []

    queries = get_daily_queries()
    all_posts: list[dict] = []
    seen_ids: set[str] = set()
    breakdown = Counter()

    print(f"[Scraper] Running {len(queries)}/{len(SEARCH_SOURCE_QUERIES)} source-aware queries today.")

    for i, query_spec in enumerate(queries, 1):
        query = query_spec["query"]
        source_label = SOURCE_TYPE_LABELS.get(query_spec.get("source_type"), query_spec.get("source_type"))
        mode = query_spec.get("query_mode", "open_web_discovery")
        print(f"\n[Scraper] Query {i}/{len(queries)} [{source_label} | {mode}]: '{query}'")

        for result in _serper_search(query_spec):
            post = _parse_serper_result(result, query_spec=query_spec)
            if not post:
                continue
            if post["id"] in seen_ids:
                print(f"  [Scraper] Dropped (duplicate): {post.get('author_name', post['id'])}")
                continue
            seen_ids.add(post["id"])
            all_posts.append(post)
            breakdown[post["source_type"]] += 1

    print("\n[Scraper] Source breakdown:")
    for source_type in SOURCE_TYPE_LABELS:
        print(f"  - {SOURCE_TYPE_LABELS[source_type]}: {breakdown.get(source_type, 0)} kept")

    print(f"\n[Scraper] {len(all_posts)} results passed all filters.")
    return all_posts
