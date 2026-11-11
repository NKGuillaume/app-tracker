"""One-time cleanup: link existing rejections/offers to the open application they
belong to when the company is written differently ("OKC Thunder" vs "Oklahoma
City Thunder"). New syncs handle this as emails arrive; this fixes rows saved
before that, whose emails are already marked processed.

Only cross-name cases go to the AI. Rows whose company the deterministic rules
already recognize are left to the sync's merge pass, so a vague same-company
match is never guessed here.

    python -m scripts.reconcile_outcomes --email you@example.com            # preview
    python -m scripts.reconcile_outcomes --email you@example.com --apply    # write
"""

import argparse

from app.db import get_db
from app.services.email_extraction import match_application
from app.services.matching import companies_match, is_known_company, title_words
from app.services.sync_pipeline import _ROW_FIELDS, _is_open, OUTCOME_STATUSES
from scripts.common import load_user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: preview)")
    args = parser.parse_args()

    user = load_user(args.email)
    db = get_db()
    rows = (
        db.table("applications").select(_ROW_FIELDS).eq("user_id", user["id"])
        .order("updated_at", desc=True).execute().data or []
    )
    open_rows = [r for r in rows if _is_open(r) and is_known_company(r.get("company"))]
    outcomes = [r for r in rows if r.get("status") in OUTCOME_STATUSES and is_known_company(r.get("company"))]

    changes = []
    for outcome in outcomes:
        # Same-name companies are the merge pass's job; only differently named
        # companies are offered here, most title overlap first.
        out_words = title_words(outcome.get("job_title"), outcome["company"])
        taken = {c[1]["id"] for c in changes}
        candidates = sorted(
            (o for o in open_rows
             if o["id"] not in taken and not companies_match(outcome["company"], o["company"])),
            key=lambda o: len(out_words & title_words(o.get("job_title"), o["company"])),
            reverse=True,
        )[:40]
        if not candidates:
            continue
        chosen = match_application(outcome["company"], outcome.get("job_title"), outcome["status"], candidates)
        target = next((o for o in candidates if o["id"] == chosen), None)
        if target:
            changes.append((outcome, target))

    if not changes:
        print("Nothing to reconcile.")
        return

    for outcome, target in changes:
        print(f"{target['status']:9} {target['company']} | {target.get('job_title') or '-'}")
        print(f"   -> {outcome['status']} (from: {outcome['company']} | {outcome.get('job_title') or '-'})")

    if not args.apply:
        print(f"\nPreview only. Re-run with --apply to update {len(changes)} application(s).")
        return

    for outcome, target in changes:
        patch = {"status": outcome["status"], "updated_at": outcome["updated_at"]}
        if not target.get("job_title") and outcome.get("job_title"):
            patch["job_title"] = outcome["job_title"]
        db.table("applications").update(patch).eq("id", target["id"]).execute()
        # Keep the rejection email linked to the surviving row, then drop the duplicate.
        db.table("processed_emails").update({"application_id": target["id"]}).eq(
            "user_id", user["id"]
        ).eq("application_id", outcome["id"]).execute()
        db.table("applications").delete().eq("id", outcome["id"]).execute()
    print(f"\nUpdated {len(changes)} application(s).")


if __name__ == "__main__":
    main()
