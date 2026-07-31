"""Orchestrates a sync run: fetch candidate messages, skip already-processed ones,
run the heuristic filter, hand survivors to the LLM extractor, and persist results.

Shared by manual sync (Phase B) and the Pub/Sub webhook (Phase C) -- both just
supply a different list of message ids and call `_process_message_ids`.
"""

from datetime import datetime, timezone
from typing import Any

from app.db import get_db
from app.services import gmail_client, heuristics
from app.services.crypto import decrypt_token
from app.services.email_extraction import classify_and_extract

MANUAL_SYNC_QUERY = "newer_than:90d"
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
    return bool(result.data)


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


def _upsert_application(db: Any, user_id: str, message_summary: dict, extraction: Any) -> tuple[str, bool]:
    thread_id = message_summary["thread_id"]
    existing = (
        db.table("applications")
        .select("id, manually_edited")
        .eq("user_id", user_id)
        .eq("gmail_thread_id", thread_id)
        .maybe_single()
        .execute()
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

    if existing.data:
        application_id = existing.data["id"]
        # A manual correction wins over anything a later sync would infer -- record
        # the new email happened (processed_emails), but don't clobber the user's edit.
        if not existing.data.get("manually_edited"):
            db.table("applications").update(row).eq("id", application_id).execute()
        return application_id, False

    inserted = db.table("applications").insert(row).execute()
    return inserted.data[0]["id"], True


def _process_message_ids(db: Any, user: dict, refresh_token: str, message_ids: list[str]) -> dict[str, int]:
    stats = {"scanned": 0, "skipped": 0, "new_applications": 0, "updated_applications": 0}

    for message_id in message_ids:
        stats["scanned"] += 1

        if _already_processed(db, user["id"], message_id):
            stats["skipped"] += 1
            continue

        summary = gmail_client.get_message_summary(refresh_token, message_id)

        if not heuristics.is_candidate_email(summary["subject"], summary["sender"]):
            _mark_processed(db, user["id"], message_id, "not_job_application")
            continue

        extraction = classify_and_extract(summary["subject"], summary["sender"], summary["body_text"])

        if not extraction.is_job_application_email:
            _mark_processed(db, user["id"], message_id, "not_job_application")
            continue

        application_id, was_new = _upsert_application(db, user["id"], summary, extraction)
        _mark_processed(db, user["id"], message_id, "job_application", application_id)

        if was_new:
            stats["new_applications"] += 1
        else:
            stats["updated_applications"] += 1

    return stats


def run_manual_sync(user: dict) -> dict[str, int]:
    db = get_db()
    refresh_token = decrypt_token(user["google_refresh_token_encrypted"])

    message_ids = gmail_client.list_candidate_message_ids(
        refresh_token, MANUAL_SYNC_QUERY, MAX_MANUAL_SYNC_MESSAGES
    )
    stats = _process_message_ids(db, user, refresh_token, message_ids)

    current_history_id = gmail_client.get_current_history_id(refresh_token)
    db.table("sync_state").upsert(
        {
            "user_id": user["id"],
            "last_history_id": current_history_id,
            "last_manual_sync_at": datetime.now(timezone.utc).isoformat(),
        }
    ).execute()

    return stats


def run_webhook_sync(user: dict, start_history_id: str) -> dict[str, int]:
    db = get_db()
    refresh_token = decrypt_token(user["google_refresh_token_encrypted"])

    message_ids = gmail_client.history_list(refresh_token, start_history_id)
    stats = _process_message_ids(db, user, refresh_token, message_ids)

    current_history_id = gmail_client.get_current_history_id(refresh_token)
    db.table("sync_state").upsert(
        {"user_id": user["id"], "last_history_id": current_history_id}
    ).execute()

    return stats
