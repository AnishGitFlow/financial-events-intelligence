"""
deduplicator.py - Persistent de-duplication layer.

Maintains a JSON history log at data/history.json that stores:
  - post URL hash (post ID)  → prevents reprocessing same post
  - content hash             → detects reposts with different URLs

On each run:
  1. Load history
  2. For each new post: check if ID or content_hash already seen
  3. Tag posts as is_duplicate or is_repost
  4. Save updated history (only non-duplicates are written back)
"""
import json
import os
from datetime import datetime, timedelta, timezone

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "data", "history.json")
HISTORY_TTL_DAYS = 30  # entries older than this are pruned automatically


def _load_history() -> dict:
    """Load the history log; returns empty structure if missing or corrupt."""
    if not os.path.exists(HISTORY_FILE):
        return {"events": {}}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("events", {})
            return data
    except (json.JSONDecodeError, OSError):
        return {"events": {}}


def _save_history(history: dict) -> None:
    """Persist history to disk, pruning entries older than TTL."""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=HISTORY_TTL_DAYS)).isoformat()

    history["events"] = {
        k: v for k, v in history.get("events", {}).items()
        if v.get("seen_at", "") >= cutoff
    }

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def _compute_completeness(post: dict) -> float:
    score = 0.0
    fields = ["event_name", "event_type", "event_dates", "location", "organiser", "target_audience", "official_link", "description"]
    for f in fields:
        val = post.get(f)
        if val and val != "Not specified":
            score += 1.0
            if f == "official_link" and "http" in val:
                score += 2.0
            if f == "description":
                score += len(val) / 100.0
    return score


def _source_rank(post: dict) -> int:
    ranks = {
        "official_event_pages": 0,
        "registration_pages": 1,
        "industry_bodies": 2,
        "company_pages": 3,
        "linkedin_posts": 4,
        "media_pr": 5,
        "community_events": 6,
        "open_web_discovery": 7,
    }
    return ranks.get(post.get("source_type"), 9)


def _merge_sources(primary: dict, secondary: dict) -> dict:
    sources_by_url = {}
    for post in (primary, secondary):
        for source in post.get("supporting_sources") or []:
            url = source.get("url")
            if url:
                sources_by_url[url] = source
        url = post.get("post_url")
        if url:
            sources_by_url.setdefault(url, {
                "source_type": post.get("source_type", ""),
                "source_domain": post.get("source_domain", ""),
                "url": url,
                "title": post.get("title", ""),
                "query": post.get("pipeline_trace", {}).get("query", ""),
            })

    primary["supporting_sources"] = list(sources_by_url.values())
    primary["supporting_source_count"] = max(0, len(primary["supporting_sources"]) - 1)

    for field in ("event_name", "event_type", "event_dates", "location", "organiser", "target_audience", "official_link", "description"):
        current = primary.get(field)
        candidate = secondary.get(field)
        if (not current or current == "Not specified") and candidate and candidate != "Not specified":
            primary[field] = candidate

    if _source_rank(secondary) < _source_rank(primary):
        for field in ("post_url", "url", "source_type", "source_domain"):
            if secondary.get(field):
                primary[field] = secondary[field]
        if secondary.get("official_link") and secondary.get("official_link") != "Not specified":
            primary["official_link"] = secondary["official_link"]

    return primary


def deduplicate(posts: list[dict]) -> list[dict]:
    """
    Tag and filter posts using the persistent history log at the EVENT level.

    Rules:
      - Match by event_name + event_dates.
      - Keep the most complete version.
    """
    history = _load_history()
    now_str = datetime.now(timezone.utc).isoformat()

    fresh_posts: list[dict] = []
    events_in_batch = {}

    for post in posts:
        name = str(post.get("event_name", "")).strip().lower()
        dates = str(post.get("event_dates", "")).strip().lower()

        if not name or name == "not specified":
            org = str(post.get("organiser", "")).strip().lower()
            evt_type = str(post.get("event_type", "")).strip().lower()
            if org and org != "not specified" and evt_type and evt_type != "other":
                event_key = f"fb|{org}|{evt_type}|{dates}"
            else:
                fresh_posts.append(post)
                continue
        else:
            event_key = f"{name}|{dates}"
        score = _compute_completeness(post)
        post["_completeness"] = score

        if event_key not in events_in_batch:
            events_in_batch[event_key] = post
        else:
            current = events_in_batch[event_key]
            if score > current["_completeness"] or _source_rank(post) < _source_rank(current):
                current["is_duplicate"] = True
                merged = _merge_sources(post, current)
                merged["_completeness"] = max(score, current["_completeness"])
                events_in_batch[event_key] = merged
            else:
                post["is_duplicate"] = True
                events_in_batch[event_key] = _merge_sources(current, post)

    for event_key, post in events_in_batch.items():
        score = post["_completeness"]
        
        if event_key in history.get("events", {}):
            past_score = history["events"][event_key].get("completeness", 0)
            if score > past_score:
                print(f"  [Dedup] Found more complete version of event: {event_key}")
                history["events"][event_key] = {"completeness": score, "seen_at": now_str}
                fresh_posts.append(post)
            else:
                print(f"  [Dedup] Skipping duplicate event (less/equal complete): {event_key}")
                post["is_duplicate"] = True
        else:
            history.setdefault("events", {})[event_key] = {"completeness": score, "seen_at": now_str}
            fresh_posts.append(post)

    _save_history(history)
    print(f"[Dedup] {len(fresh_posts)} posts passed deduplication ({len(posts) - len(fresh_posts)} dropped).")
    return fresh_posts
