"""Orchestrates a sync run: fetch candidate messages, skip already-processed ones,
run the heuristic filter, hand survivors to the LLM extractor, and persist results.

Shared by manual sync (Phase B) and the Pub/Sub webhook (Phase C) -- both just
supply a different list of message ids and call `_process_message_ids`.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from app.db import get_db
from app.services import gmail_client, heuristics
from app.services.crypto import decrypt_token
from app.services.email_extraction import classify_and_extract, match_application
from app.services.matching import is_known_company, same_application, title_within

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


_ROW_FIELDS = (
    "id, company, job_title, status, manually_edited, application_date, updated_at, "
    "interview_type, assessment_platform, interview_deadline, team"
)

# Hiring only moves forward: applied -> interview -> a final outcome. Emails can
# be processed out of order (a later sync can reach an older confirmation that an
# earlier sync's message cap skipped), so a status never moves backwards.
STATUS_RANK = {"unknown": 0, "applied": 1, "interview": 2, "rejected": 3, "offer": 3, "withdrawn": 3}
OUTCOME_STATUSES = {"rejected", "offer", "withdrawn"}
# Status emails worth an AI matching call when no rule finds their application.
_AI_MATCH_STATUSES = {"interview", "rejected", "offer"}
_AI_MATCH_LIMIT = 40


def _rank(status: str | None) -> int:
    return STATUS_RANK.get(status or "unknown", 0)


def _is_open(row: dict) -> bool:
    return _rank(row.get("status")) < 3


def _prefer(rows: list[dict]) -> dict:
    """Open applications first, then the most recently updated."""
    return max(rows, key=lambda r: (_is_open(r), r.get("updated_at") or ""))


def _rows_match(a: dict, b: dict) -> bool:
    return same_application(a.get("company"), a.get("job_title"), b.get("company"), b.get("job_title"))


def _has_conflict(rows: list[dict]) -> bool:
    """True if `rows` hold at least two different applications."""
    return any(not _rows_match(a, b) for i, a in enumerate(rows) for b in rows[i + 1:])


def _find_existing_application(
    db: Any, user_id: str, thread_id: str, company: str | None, job_title: str | None,
    status: str | None = None,
) -> dict | None:
    """Match an incoming email to an existing application row.

    1. Same Gmail thread.
    2. Same company and role, compared after normalizing (see services/matching):
       "Humana, Inc." == "Humana", "129778 Software Developer Intern 2027" ==
       "Software Developer Intern 2027". Open applications win over closed ones.
    3. A rejection/offer naming no recognizable role closes the company's only
       open application.
    4. Status emails that still match nothing, or match several different roles,
       ask the AI to pick among the candidates ("OKC Thunder" vs "Oklahoma City
       Thunder"). The answer is validated against the candidate list.
    """
    result = (
        db.table("applications")
        .select(_ROW_FIELDS)
        .eq("user_id", user_id)
        .eq("gmail_thread_id", thread_id)
        .maybe_single()
        .execute()
    )
    if result and result.data:
        return result.data

    # Never merge on an unidentified company -- that would lump unrelated rows.
    if not is_known_company(company):
        return None

    result = (
        db.table("applications")
        .select(_ROW_FIELDS)
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    rows = (result.data or []) if result else []
    incoming = {"company": company, "job_title": job_title}

    matches = [r for r in rows if _rows_match(incoming, r)]
    if matches and not _has_conflict(matches):
        return _prefer(matches)

    if not matches and status in OUTCOME_STATUSES:
        same_company = [
            r for r in rows if _is_open(r) and same_application(company, None, r.get("company"), None)
        ]
        if len(same_company) == 1:
            return same_company[0]

    if status not in _AI_MATCH_STATUSES:
        # Ambiguous "applied" emails: the most likely open match, else a new row.
        return _prefer(matches) if matches else None

    candidates = matches or [r for r in rows if _is_open(r) and is_known_company(r.get("company"))]
    candidates = candidates[:_AI_MATCH_LIMIT]
    if not candidates:
        return None
    try:
        chosen = match_application(company, job_title, status, candidates)
    except Exception:
        chosen = None  # matching is best effort; a new row is the safe fallback
    return next((r for r in candidates if r["id"] == chosen), None)


def _interview_fields(extraction: Any) -> dict:
    """Interview details from an interview-stage email, non-null values only.
    Emails at any other stage contribute nothing, so a later rejection keeps the
    record of what the interview was; a later interview email (e.g. OA, then a
    phone screen) moves the row on to the newer step."""
    if extraction.status != "interview":
        return {}
    fields = {
        "interview_type": extraction.interview_type,
        "assessment_platform": extraction.assessment_platform,
        "interview_deadline": (
            extraction.interview_deadline.isoformat() if extraction.interview_deadline else None
        ),
        "team": extraction.team,
    }
    return {k: v for k, v in fields.items() if v is not None}


def _upsert_application(db: Any, user_id: str, message_summary: dict, extraction: Any) -> tuple[str, bool]:
    thread_id = message_summary["thread_id"]
    existing = _find_existing_application(
        db, user_id, thread_id, extraction.company, extraction.job_title, extraction.status
    )

    email_date = _internal_date_to_iso(message_summary.get("internal_date"))
    application_date = (
        extraction.application_date.isoformat() if extraction.application_date else email_date
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
        now = datetime.now(timezone.utc).isoformat()
        # An email sent before the application was made belongs to an earlier
        # application cycle; it must not close this one.
        stale = bool(
            email_date and existing.get("application_date")
            and email_date < existing["application_date"]
        )
        advances = not stale and _rank(extraction.status) >= _rank(existing.get("status"))

        if existing.get("manually_edited"):
            # The user's corrections stand, except that a final outcome (rejected,
            # offer) still updates the status -- otherwise editing an interview's
            # type would mean its rejection never shows up.
            if (
                advances
                and extraction.status in OUTCOME_STATUSES
                and extraction.status != existing.get("status")
            ):
                db.table("applications").update(
                    {"status": extraction.status, "updated_at": now}
                ).eq("id", application_id).execute()
            return application_id, False

        update_row = dict(row)
        update_row["updated_at"] = now
        if not advances:
            update_row.pop("status")
        # The application date marks when they applied; a later status email
        # must not shift it forward.
        if existing.get("application_date"):
            update_row.pop("application_date")
        # Don't erase a known role because a follow-up email omitted it.
        if not extraction.job_title and existing.get("job_title"):
            update_row.pop("job_title")
        update_row.update(_interview_fields(extraction))
        db.table("applications").update(update_row).eq("id", application_id).execute()
        return application_id, False

    row.update(_interview_fields(extraction))
    inserted = db.table("applications").insert(row).execute()
    return inserted.data[0]["id"], True


_DONATED_FIELDS = ("job_title", "interview_type", "assessment_platform", "interview_deadline", "team")


def _merge_duplicate_applications(db: Any, user_id: str) -> int:
    """Collapse rows that describe the same application into one. Duplicates can
    predate the current matching rules, so this runs on every sync (idempotent --
    once merged, there is nothing left to match). No AI here: only rows the
    deterministic rules agree on are merged.

    A row whose role is too vague to place -- it matches two rows that are
    different applications (e.g. "Software Engineer Intern - Redmond" vs two
    distinct Redmond postings) -- is left alone rather than guessed.

    Survivor: manually edited rows first, then most recently updated. It takes
    the furthest status in the group (a rejection beats an "applied" email that
    was processed later), fields it lacks, and the earliest application date.
    Donors' processed_emails links are re-pointed before deletion.
    Returns the number of rows removed.
    """
    result = (
        db.table("applications")
        .select(_ROW_FIELDS)
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    rows = (result.data or []) if result else []
    # Stable sort: manual edits float to the front, updated_at desc preserved within.
    rows.sort(key=lambda r: not r.get("manually_edited"))
    rows = [r for r in rows if is_known_company(r.get("company"))]

    def vaguer(a: dict, b: dict) -> bool:
        return title_within(a.get("job_title"), b.get("job_title"), a.get("company"), b.get("company"))

    ambiguous: set[str] = set()
    for row in rows:
        broader = [o for o in rows if o is not row and _rows_match(row, o) and vaguer(row, o)]
        if _has_conflict(broader):
            ambiguous.add(row["id"])

    groups: list[list[dict]] = []
    for row in rows:
        if row["id"] in ambiguous:
            continue
        hits = [g for g in groups if any(_rows_match(row, member) for member in g)]
        if len(hits) == 1:
            hits[0].append(row)
        else:
            groups.append([row])

    removed = 0
    for group in groups:
        if len(group) < 2:
            continue
        survivor, donors = group[0], group[1:]
        patch: dict = {}

        best = max(group, key=lambda r: _rank(r.get("status")))
        if _rank(best.get("status")) > _rank(survivor.get("status")) and (
            not survivor.get("manually_edited") or best.get("status") in OUTCOME_STATUSES
        ):
            patch["status"] = best["status"]

        for field in _DONATED_FIELDS:
            if not survivor.get(field):
                value = next((d[field] for d in donors if d.get(field)), None)
                if value:
                    patch[field] = value

        # The earliest email marks when they actually applied -- but never move a
        # date the user set by hand.
        dates = [r["application_date"] for r in group if r.get("application_date")]
        if dates and not survivor.get("manually_edited"):
            earliest = min(dates)
            if earliest != survivor.get("application_date"):
                patch["application_date"] = earliest

        if patch:
            db.table("applications").update(patch).eq("id", survivor["id"]).execute()

        for donor in donors:
            # processed_emails references the row by FK; re-point before deleting.
            db.table("processed_emails").update({"application_id": survivor["id"]}).eq(
                "user_id", user_id
            ).eq("application_id", donor["id"]).execute()
            db.table("applications").delete().eq("id", donor["id"]).execute()
            removed += 1

    return removed


# OpenAI calls are network-bound, so a small thread pool overlaps them. Kept
# modest to stay clear of per-minute rate limits.
LLM_CONCURRENCY = 8
_DB_IN_CHUNK = 100


def _processed_ids(db: Any, user_id: str, message_ids: list[str]) -> set[str]:
    """One query per 100 ids instead of one per message."""
    seen: set[str] = set()
    for i in range(0, len(message_ids), _DB_IN_CHUNK):
        chunk = message_ids[i : i + _DB_IN_CHUNK]
        result = (
            db.table("processed_emails")
            .select("gmail_message_id")
            .eq("user_id", user_id)
            .in_("gmail_message_id", chunk)
            .execute()
        )
        seen.update(r["gmail_message_id"] for r in (result.data or []) if result)
    return seen


def _mark_processed_bulk(db: Any, user_id: str, message_ids: list[str], classification: str) -> None:
    if not message_ids:
        return
    rows = [
        {"user_id": user_id, "gmail_message_id": m, "classification": classification}
        for m in message_ids
    ]
    for i in range(0, len(rows), 500):
        db.table("processed_emails").upsert(rows[i : i + 500]).execute()


def _safe_extract(summary: dict) -> Any:
    """One failed OpenAI call (timeout, rate limit) must not sink the whole sync.
    None means "try again next sync": the email is not marked processed."""
    try:
        return classify_and_extract(
            summary["subject"],
            summary["sender"],
            summary["body_text"],
            _internal_date_to_iso(summary.get("internal_date")),
        )
    except Exception:
        return None


def _process_message_ids(
    db: Any, user: dict, refresh_token: str, message_ids: list[str], persist: bool = True
) -> dict[str, int]:
    """With persist=False nothing is read from or written to the database: every
    message is treated as unseen and no rows change. Used to measure a full sync
    on an account that has already been synced.

    Network work is batched: one "already processed?" query per 100 ids, Gmail
    fetches 20 per HTTP round trip on a single login, OpenAI calls run
    LLM_CONCURRENCY at a time. Results are still applied oldest-first, one at a
    time, so the newest email decides an application's status.
    """
    # scanned = skipped + fetch_failed + heuristic_filtered + llm_calls, and
    # llm_calls = llm_rejected + llm_errors + job_emails. The extra counters exist
    # so the cost saving of the keyword pre-filter can be measured, not guessed.
    stats = {
        "scanned": len(message_ids),
        "skipped": 0,
        "fetch_failed": 0,
        "heuristic_filtered": 0,
        "llm_calls": 0,
        "llm_rejected": 0,
        "llm_errors": 0,
        "job_emails": 0,
        "rejections": 0,
        "new_applications": 0,
        "updated_applications": 0,
    }
    user_id = user["id"]

    seen = _processed_ids(db, user_id, message_ids) if persist else set()
    new_ids = [m for m in dict.fromkeys(message_ids) if m not in seen]
    stats["skipped"] = len(message_ids) - len(new_ids)

    summaries = gmail_client.get_message_summaries(refresh_token, new_ids)
    # Not marked processed, so the next sync retries them.
    stats["fetch_failed"] = len(new_ids) - len(summaries)

    candidates: list[dict] = []
    filtered_out: list[str] = []
    for message_id in new_ids:
        summary = summaries.get(message_id)
        if summary is None:
            continue
        if heuristics.is_candidate_email(summary["subject"], summary["sender"]):
            candidates.append(summary)
        else:
            filtered_out.append(message_id)
    stats["heuristic_filtered"] = len(filtered_out)
    if persist:
        _mark_processed_bulk(db, user_id, filtered_out, "not_job_application")

    # Gmail lists newest-first. Apply oldest-first instead, so when several emails
    # concern the same application the most recent one lands last and its status
    # is what the row ends up with.
    candidates.sort(key=lambda s: int(s.get("internal_date") or 0))

    with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as pool:
        extractions = list(pool.map(_safe_extract, candidates))  # map keeps input order
    stats["llm_calls"] = len(candidates)

    rejected: list[str] = []
    for summary, extraction in zip(candidates, extractions):
        if extraction is None:
            stats["llm_errors"] += 1
            continue
        if not extraction.is_job_application_email:
            rejected.append(summary["id"])
            continue

        stats["job_emails"] += 1
        if extraction.status == "rejected":
            stats["rejections"] += 1
        if not persist:
            continue

        application_id, was_new = _upsert_application(db, user_id, summary, extraction)
        _mark_processed(db, user_id, summary["id"], "job_application", application_id)

        if was_new:
            stats["new_applications"] += 1
        else:
            stats["updated_applications"] += 1

    stats["llm_rejected"] = len(rejected)
    if persist:
        _mark_processed_bulk(db, user_id, rejected, "not_job_application")

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
    # what it matched against everything in the same 90-day window.
    stats["gmail_matched"] = len(message_ids)
    stats["mailbox_90d"] = gmail_client.count_messages(
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


def measure_full_sync(user: dict) -> dict[str, Any]:
    """Dry run of a manual sync over the whole 90-day window: same Gmail query,
    keyword filter and OpenAI calls, but no database reads or writes. Timing
    therefore excludes DB round trips."""
    started = time.perf_counter()
    refresh_token = decrypt_token(user["google_refresh_token_encrypted"])
    message_ids = gmail_client.list_candidate_message_ids(
        refresh_token, MANUAL_SYNC_QUERY, MAX_MANUAL_SYNC_MESSAGES
    )
    stats: dict[str, Any] = _process_message_ids(
        None, user, refresh_token, message_ids, persist=False
    )
    stats["gmail_matched"] = len(message_ids)
    stats["mailbox_90d"] = gmail_client.count_messages(
        refresh_token, MANUAL_SYNC_WINDOW
    )
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
