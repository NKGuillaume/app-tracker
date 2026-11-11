"""Run one real manual sync for a user and print the resume numbers it produces.

    python -m scripts.resume_metrics --email you@example.com

Only the FIRST sync for an account gives meaningful filter/timing numbers:
later runs skip mail that was already processed.
"""

import argparse
import json
from collections import Counter

from app.db import get_db
from app.services import sync_pipeline
from scripts.common import EVAL_DIR, load_user, pct


def _count_rows(table: str, user_id: str, column: str) -> Counter:
    rows = get_db().table(table).select(column).eq("user_id", user_id).execute().data or []
    return Counter(r[column] for r in rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Email of a user who has logged in")
    parser.add_argument("--dry-run", action="store_true",
                        help="Measure a full sync without touching the database "
                             "(for accounts that were already synced)")
    args = parser.parse_args()

    user = load_user(args.email)
    if args.dry_run:
        print("Dry-run sync over the 90-day window (calls Gmail and OpenAI, writes nothing)...")
        stats = sync_pipeline.measure_full_sync(user)
        stats["merged_duplicates"] = "n/a (dry run)"
    else:
        print("Running manual sync (this calls Gmail and OpenAI)...")
        stats = sync_pipeline.run_manual_sync(user)

    statuses = _count_rows("applications", user["id"], "status")
    classifications = _count_rows("processed_emails", user["id"], "classification")
    total_apps = sum(statuses.values())

    mailbox = stats["mailbox_90d"]
    matched = stats["gmail_matched"]
    llm = stats["llm_calls"]

    print("\n=== Raw sync stats ===")
    print(json.dumps(stats, indent=2))

    print("\n=== Resume numbers ===")
    print("1. Filtering before OpenAI")
    print(f"   Emails in last 90 days:                  {mailbox if mailbox is not None else 'unavailable'}")
    print(f"   Matched the Gmail search query:          {matched}")
    print(f"   Dropped by local keyword filter:          {pct(stats['heuristic_filtered'], matched)}")
    print(f"   Sent to OpenAI:                           {llm}")
    if mailbox:
        print(f"   => AI calls avoided vs. classifying everything: {pct(mailbox - llm, mailbox)}")
    if stats.get("fetch_failed"):
        print(f"   ({stats['fetch_failed']} emails could not be fetched from Gmail and were left out)")
    if stats.get("llm_errors"):
        print(f"   ({stats['llm_errors']} OpenAI calls failed and were left out)")
    if matched >= sync_pipeline.MAX_MANUAL_SYNC_MESSAGES:
        print(f"   (note: hit the {sync_pipeline.MAX_MANUAL_SYNC_MESSAGES}-message cap)")

    print("2. Accuracy: run scripts.eval_extraction (export, label, score)")

    print("3. Deduplication (from the database)")
    linked = classifications.get("job_application", 0)
    print(f"   {linked} application emails -> {total_apps} applications")
    print(f"   merged_duplicates this run: {stats['merged_duplicates']}")

    print("4. Volume")
    print(f"   {total_apps} applications tracked across {sum(classifications.values())} emails processed")
    print(f"   By status: {dict(statuses)}")

    print("5. Sync time")
    print(f"   {stats['duration_seconds']}s for {stats['scanned']} emails "
          f"({llm} OpenAI calls)" + (", excluding DB writes" if args.dry_run else ""))

    if stats["skipped"]:
        print(f"\nWARNING: {stats['skipped']} emails were already processed by an earlier "
              "sync, so filter and timing numbers above undercount. Use the first run.")

    EVAL_DIR.mkdir(exist_ok=True)
    out = EVAL_DIR / "metrics.json"
    out.write_text(json.dumps({"sync": stats, "statuses": statuses,
                               "processed_emails": classifications}, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
