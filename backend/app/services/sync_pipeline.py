"""Orchestrates a sync run: fetch candidate messages, skip already-processed ones,
run the heuristic filter, hand survivors to the LLM extractor, and persist results.

Shared by manual sync (Phase B) and the Pub/Sub webhook (Phase C) -- both just
supply a different list of message ids and call `_process_message_ids`.
"""

import time
from datetime import datetime, timezone
from typing import Any

from app.db import get_db
from app.services import gmail_client, heuristics
from app.services.crypto import decrypt_token
from app.services.email_extraction import classify_and_extract

# Bounded by date AND by a job-application search (ATS senders + subject keywords,
# including internship terms) so the 300-message budget is spent on relevant mail
# rather than the newest 300 messages of any kind.
MANUAL_SYNC_WINDOW = "newer_than:90d"
MANUAL_SYNC_QUERY = f"{MANUAL_SYNC_WINDOW} {heuristics.gmail_search_query()}"
MAX_MANUAL_SYNC_MESSAGES = 300


def _internal_date_to_iso(internal_date_ms: str | None) -> str | None:
    if not internal_date_ms:
        return None
    return datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc).date().isoformat()


def _already_processed(db: Any, user_id: str, message_id: str) -> bool:
    result = (
        db.table("processed_emails")
        .select("gmail_message_id")
        .eq("user_id", user_id)
        .eq("gmail_message_id", message_id)
        .maybe_single()
        .execute()
    )
    return bool(result and result.data)


def _mark_processed(
    db: Any, user_id: str, message_id: str, classification: str, application_id: str | None = None
) -> None:
    db.table("processed_emails").upsert(
        {
            "user_id": user_id,
            "gmail_message_id": message_id,
            "classification": classification,
            "application_id": application_id,
        }
    ).execute()


def _find_existing_application(
    db: Any, user_id: str, thread_id: str, company: str | None, job_title: str | None
) -> dict | None:
    """Match an incoming email to an existing application row.

    Same Gmail thread wins first. Otherwise fall back to same company + same role,
    so a status update that arrives in a brand-new thread updates the existing row
    instead of creating a duplicate. A missing role on either side still matches,
    because follow-up emails often omit the job title.
    """
    fields = "id, manually_edited, job_title, application_date"
    result = (
        db.table("applications")
        .select(fields)
        .eq("user_id", user_id)
        .eq("gmail_thread_id", thread_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data

    # Never merge on an unidentified company -- that would lump unrelated rows.
    if not company or company == "Unknown":
        return None

    result = (
        db.table("applications")
        .select(fields)
        .eq("user_id", user_id)
        .ilike("company", company)
        .order("updated_at", desc=True)
        .execute()
    )
    incoming_title = (job_title or "").strip().lower()
    for row in (result.data or []) if result else []:
        existing_title = (row.get("job_title") or "").strip().lower()
        if not incoming_title or not existing_title or incoming_title == existing_title:
            return row
    return None


def _upsert_application(db: Any, user_id: str, message_summary: dict, extraction: Any) -> tuple[str, bool]:
    thread_id = message_summary["thread_id"]
    existing = _find_existing_application(
        db, user_id, thread_id, extraction.company, extraction.job_title
    )

    application_date = extraction.application_date.isoformat() if extraction.application_date else (
        _internal_date_to_iso(message_summary.get("internal_date"))
    )

    row = {
        "user_id": user_id,
        "company": extraction.company or "Unknown",
        "job_title": extraction.job_title,
        "application_date": application_date,
        "status": extraction.status,
        "source_email_id": message_summary["id"],
        "gmail_thread_id": thread_id,
        "raw_snippet": message_summary.get("snippet"),
        "confidence": extraction.confidence,
    }

    if existing:
        application_id = existing["id"]
        # A manual correction wins over anything a later sync would infer -- record
        # the new email happened (processed_emails), but don't clobber the user's edit.
        if not existing.get("manually_edited"):
            update_row = dict(row)
            update_row["updated_at"] = datetime.now(timezone.utc).isoformat()
            # The application date marks when they applied; a later status email
            # must not shift it forward.
            if existing.get("application_date"):
                update_row.pop("application_date")
            # Don't erase a known role because a follow-up email omitted it.
            if not extraction.job_title and existing.get("job_title"):
                update_row.pop("job_title")
            db.table("applications").update(update_row).eq("id", application_id).execute()
        return application_id, False

    inserted = db.table("applications").insert(row).execute()
    return inserted.data[0]["id"], True


def _merge_duplicate_applications(db: Any, user_id: str) -> int:
    """Collapse rows that describe the same company + role into the single most
    recent one. Duplicates can predate company-level matching, so this runs on
    every sync (idempotent -- once merged, there is nothing left to match).

    Survivor preference: manually edited rows first, then most recently updated.
    Older rows donate their processed_emails links (re-pointed before deletion),
    a job title the survivor lacks, and an earlier application date.
    Returns the number of rows removed.
    """
    result = (
        db.table("applications")
        .select("id, company, job_title, application_date, manually_edited, updated_at")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    rows = (result.data or []) if result else []
    # Stable sort: manual edits float to the front, updated_at desc preserved within.
    rows.sort(key=lambda r: not r.get("manually_edited"))

    kept: list[dict] = []
    removed = 0
    for row in rows:
        company = (row.get("company") or "").strip().lower()
        title = (row.get("job_title") or "").strip().lower()

        survivor = None
        if company and company != "unknown":
            for candidate in kept:
                if candidate["_company"] != company:
                    continue
                # Same matching rule as _find_existing_application: a missing
                # title on either side still counts as the same application.
                if not title or not candidate["_title"] or title == candidate["_title"]:
                    survivor = candidate
                    break

        if survivor is None:
            row["_company"] = company
            row["_title"] = title
            kept.append(row)
            continue

        patch: dict = {}
        if row.get("job_title") and not survivor.get("job_title"):
            patch["job_title"] = row["job_title"]
            survivor["_title"] = title
        row_date = row.get("application_date")
        kept_date = survivor.get("application_date")
        # The earliest email marks when they actually applied -- but never move a
        # date the user set by hand.
        if row_date and (
            not kept_date or (row_date < kept_date and not survivor.get("manually_edited"))
        ):
            patch["application_date"] = row_date
        if patch:
            survivor.update(patch)
            db.table("applications").update(patch).eq("id", survivor["id"]).execute()

        # processed_emails references the row by FK; re-point before deleting.
        db.table("processed_emails").update({"application_id": survivor["id"]}).eq(
            "user_id", user_id
        ).eq("application_id", row["id"]).execute()
        db.table("applications").delete().eq("id", row["id"]).execute()
        removed += 1

    return removed


def _process_message_ids(db: Any, user: dict, refresh_token: str, message_ids: list[str]) -> dict[str, int]:
    # scanned = skipped + heuristic_filtered + llm_calls, and
    # llm_calls = llm_rejected + job_emails. The extra counters exist so the
    # cost saving of the keyword pre-filter can be measured, not guessed.
    stats = {
        "scanned": 0,
        "skipped": 0,
        "heuristic_filtered": 0,
        "llm_calls": 0,
        "llm_rejected": 0,
        "job_emails": 0,
        "new_applications": 0,
        "updated_applications": 0,
    }

    candidates: list[dict] = []
    for message_id in message_ids:
        stats["scanned"] += 1

        if _already_processed(db, user["id"], message_id):
            stats["skipped"] += 1
            continue

        summary = gmail_client.get_message_summary(refresh_token, message_id)

        if not heuristics.is_candidate_email(summary["subject"], summary["sender"]):
            _mark_processed(db, user["id"], message_id, "not_job_application")
            stats["heuristic_filtered"] += 1
            continue

        candidates.append(summary)

    # Gmail lists newest-first. Apply oldest-first instead, so when several emails
    # concern the same application the most recent one lands last and its status
    # is what the row ends up with.
    candidates.sort(key=lambda s: int(s.get("internal_date") or 0))

    for summary in candidates:
        extraction = classify_and_extract(summary["subject"], summary["sender"], summary["body_text"])
        stats["llm_calls"] += 1

        if not extraction.is_job_application_email:
            _mark_processed(db, user["id"], summary["id"], "not_job_application")
            stats["llm_rejected"] += 1
            continue

        stats["job_emails"] += 1

        application_id, was_new = _upsert_application(db, user["id"], summary, extraction)
        _mark_processed(db, user["id"], summary["id"], "job_application", application_id)

        if was_new:
            stats["new_applications"] += 1
        else:
            stats["updated_applications"] += 1

    return stats


def run_manual_sync(user: dict) -> dict[str, Any]:
    started = time.perf_counter()
    db = get_db()
    refresh_token = decrypt_token(user["google_refresh_token_encrypted"])

    message_ids = gmail_client.list_candidate_message_ids(
        refresh_token, MANUAL_SYNC_QUERY, MAX_MANUAL_SYNC_MESSAGES
    )
    stats: dict[str, Any] = _process_message_ids(db, user, refresh_token, message_ids)
    # Stage 1 of filtering happens server-side in the Gmail search query; compare
    # what it matched against everything in the same 90-day window. Gmail only
    # gives an estimate for the latter, so it is reported as one.
    stats["gmail_matched"] = len(message_ids)
    stats["mailbox_90d_estimate"] = gmail_client.count_messages_estimate(
        refresh_token, MANUAL_SYNC_WINDOW
    )
    stats["merged_duplicates"] = _merge_duplicate_applications(db, user["id"])

    current_history_id = gmail_client.get_current_history_id(refresh_token)
    db.table("sync_state").upsert(
        {
            "user_id": user["id"],
            "last_history_id": current_history_id,
            "last_manual_sync_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    stats["duration_seconds"] = round(time.perf_counter() - started, 2)
    return stats


def run_webhook_sync(user: dict, start_history_id: str) -> dict[str, int]:
    db = get_db()
    refresh_token = decrypt_token(user["google_refresh_token_encrypted"])

    message_ids = gmail_client.history_list(refresh_token, start_history_id)
    stats = _process_message_ids(db, user, refresh_token, message_ids)
    stats["merged_duplicates"] = _merge_duplicate_applications(db, user["id"])

    current_history_id = gmail_client.get_current_history_id(refresh_token)
    db.table("sync_state").upsert(
        {"user_id": user["id"], "last_history_id": current_history_id}
    ).execute()

    return stats
