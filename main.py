"""
main.py - Pipeline orchestrator + daily scheduler.
(Unicode-safe version for Windows)
"""
import argparse
import schedule
import time
import sys
from datetime import datetime, timezone

from scraper       import fetch_posts
from deduplicator  import deduplicate
from enricher      import enrich_batch
from reporter      import generate_report, save_report, send_email_report
from config        import SCHEDULE_TIME

def run_pipeline() -> None:
    """Execute the full intelligence pipeline end-to-end."""
    start = datetime.now(timezone.utc)
    print("\n" + "=" * 60)
    print(f"  Financial Services Event Intelligence Pipeline")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # ── Step 1: Fetch ────────────────────────────────────────────────────────────
    print("\n[Step 1/5] Fetching LinkedIn posts...")
    raw_posts = fetch_posts()
    if not raw_posts:
        print("[Step 1/5] No posts fetched. Check API keys.")
        return

    print(f"[Step 1/5] Success: Fetched {len(raw_posts)} raw posts.")

    # ── Step 2: Enrich ───────────────────────────────────────────────────────────
    print(f"\n[Step 2/5] Enriching {len(raw_posts)} posts with analysis...")
    enriched_posts = enrich_batch(raw_posts)
    print(f"[Step 2/5] Success: Enrichment complete.")

    # ── Step 3: De-duplicate ─────────────────────────────────────────────────────
    print("\n[Step 3/5] De-duplicating against history...")
    fresh_posts = deduplicate(enriched_posts)
    if not fresh_posts:
        print("[Step 3/5] No new events after deduplication.")
        return

    print(f"[Step 3/5] Success: {len(fresh_posts)} unique events found.")

    # ── Step 4: Generate report ──────────────────────────────────────────────────
    print("\n[Step 4/5] Generating premium reports...")
    report = generate_report(fresh_posts)
    html_content, json_report = save_report(report)
    print(f"[Step 4/5] Success: Reports saved.")

    # ── Step 5: Send email ───────────────────────────────────────────────────────
    print("\n[Step 5/5] Sending email report...")
    send_email_report(html_content, json_report)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"  Events processed: {len(fresh_posts)}")
    print(f"{'=' * 60}\n")

def main():
    parser = argparse.ArgumentParser(description="Financial Services Event Monitor")
    parser.add_argument("--schedule", action="store_true", help="Run daily")
    args = parser.parse_args()

    if args.schedule:
        print(f"[Scheduler] Daily run at {SCHEDULE_TIME} (IST).")
        run_pipeline()
        schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run_pipeline()

if __name__ == "__main__":
    main()
