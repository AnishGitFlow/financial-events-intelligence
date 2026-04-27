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
            if score > events_in_batch[event_key]["_completeness"]:
                events_in_batch[event_key]["is_duplicate"] = True
                events_in_batch[event_key] = post
            else:
                post["is_duplicate"] = True

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
