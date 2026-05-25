"""
main.py - Pipeline orchestrator + daily scheduler.
(Unicode-safe version for Windows)

Usage:
    python main.py              # full run (fetch → enrich → dedup → save → email)
    python main.py --dry-run    # skips SMTP; prints HTML path for local preview
    python main.py --schedule   # runs immediately, then daily at SCHEDULE_TIME
"""
import argparse
import os
import schedule
import time
import sys
from datetime import datetime, timezone

from scraper       import fetch_posts
from deduplicator  import deduplicate
from enricher      import enrich_batch
from reporter      import generate_report, save_report, send_email_report
from config        import SCHEDULE_TIME

def run_pipeline(dry_run: bool = False) -> None:
    """Execute the full intelligence pipeline end-to-end.

    Args:
        dry_run: When True, the HTML report is saved to disk for local
                 preview but SMTP is skipped entirely.  Use this to QA
                 the template without spending API credits or sending mail.
    """
    start = datetime.now(timezone.utc)
    mode  = "DRY RUN (no email)" if dry_run else "LIVE"
    print("\n" + "=" * 60)
    print(f"  Financial Services Event Intelligence Pipeline  [{mode}]")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)

    # ── Step 1: Fetch ────────────────────────────────────────────────────────────
    print("\n[Step 1/5] Fetching open-web event signals...")
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

    # ── Step 4: Generate + Save report (ALWAYS runs) ─────────────────────────────
    print("\n[Step 4/5] Generating premium reports...")
    report = generate_report(fresh_posts)
    html_content, json_report = save_report(report)

    # Locate the most recently written HTML file so we can print its path.
    reports_dir = os.path.join(os.path.dirname(__file__), "data", "reports")
    html_files  = sorted(
        (f for f in os.listdir(reports_dir) if f.endswith(".html")),
        reverse=True,
    )
    if html_files:
        html_path = os.path.join(reports_dir, html_files[0])
        print(f"[Step 4/5] Report saved  →  {html_path}")
        print(f"[Step 4/5] Open in browser to preview before sending.")
    else:
        print(f"[Step 4/5] Reports saved to {reports_dir}")

    # ── Step 5: Send email (skipped in dry-run mode) ──────────────────────────────
    if dry_run:
        print("\n[Step 5/5] DRY RUN — SMTP skipped. Open the HTML path above to review.")
    else:
        print("\n[Step 5/5] Sending email report...")
        send_email_report(html_content, json_report)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    print(f"\n{'=' * 60}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"  Events processed: {len(fresh_posts)}")
    print(f"{'=' * 60}\n")

def main():
    parser = argparse.ArgumentParser(
        description="Financial Services Event Intelligence Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py              # full run\n"
            "  python main.py --dry-run    # save HTML, skip SMTP\n"
            "  python main.py --schedule   # run now + daily scheduler\n"
        ),
    )
    parser.add_argument("--schedule", action="store_true", help="Run daily at SCHEDULE_TIME")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Save HTML report locally but skip SMTP (free, instant preview)",
    )
    args = parser.parse_args()

    if args.schedule:
        print(f"[Scheduler] Daily run at {SCHEDULE_TIME} (IST).")
        run_pipeline(dry_run=args.dry_run)
        schedule.every().day.at(SCHEDULE_TIME).do(run_pipeline, dry_run=args.dry_run)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run_pipeline(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
