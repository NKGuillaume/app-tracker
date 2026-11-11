"""Classify existing interview-stage applications that predate interview
extraction (interview_type is null). Re-reads each row's source email and fills
only the interview fields; manually edited rows are left alone.

    python -m scripts.backfill_interviews --email you@example.com
"""

import argparse
from concurrent.futures import ThreadPoolExecutor

from app.db import get_db
from app.services import gmail_client
from app.services.crypto import decrypt_token
from app.services.email_extraction import classify_and_extract
from app.services.sync_pipeline import _interview_fields, _internal_date_to_iso
from scripts.common import load_user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    user = load_user(args.email)
    db = get_db()
    rows = (
        db.table("applications")
        .select("id, company, job_title, source_email_id, manually_edited")
        .eq("user_id", user["id"])
        .eq("status", "interview")
        .is_("interview_type", "null")
        .execute()
        .data
        or []
    )
    rows = [r for r in rows if not r["manually_edited"]]
    if not rows:
        print("Nothing to backfill.")
        return

    token = decrypt_token(user["google_refresh_token_encrypted"])
    emails = gmail_client.get_message_summaries(token, [r["source_email_id"] for r in rows])

    def extract(row: dict):
        email = emails.get(row["source_email_id"])
        if email is None:
            return None
        return classify_and_extract(
            email["subject"], email["sender"], email["body_text"],
            _internal_date_to_iso(email.get("internal_date")),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(extract, rows))

    for row, extraction in zip(rows, results):
        label = f"{row['company']} / {row['job_title'] or '-'}"
        if extraction is None:
            print(f"  skipped  {label}: source email not found")
            continue
        fields = _interview_fields(extraction)
        if extraction.status == "interview" and not fields.get("interview_type"):
            fields["interview_type"] = "other"
        if not fields:
            # The email reads as another stage now; don't guess an interview type.
            print(f"  skipped  {label}: email reads as '{extraction.status}', not an interview")
            continue
        db.table("applications").update(fields).eq("id", row["id"]).execute()
        print(f"  updated  {label}: {fields}")


if __name__ == "__main__":
    main()
