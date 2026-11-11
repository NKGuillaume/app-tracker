"""Thin wrapper around the Gmail API for the operations the sync pipeline needs.

Every function takes a plaintext (already-decrypted) refresh token and mints a
short-lived service client from it — there is no persistent connection, so this
is safe to call from request handlers, background tasks, or the scheduler.
"""

import base64
import time
from typing import Any

from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from app.auth.google_oauth import credentials_from_refresh_token


def _service(refresh_token: str) -> Resource:
    credentials = credentials_from_refresh_token(refresh_token)
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def list_candidate_message_ids(refresh_token: str, query: str, max_results: int = 200) -> list[str]:
    """List message ids matching a Gmail search query. Used for manual sync, where
    `query` is a bounded search (e.g. `newer_than:90d`) rather than every message."""
    service = _service(refresh_token)
    message_ids: list[str] = []
    page_token = None

    while len(message_ids) < max_results:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=query,
                pageToken=page_token,
                maxResults=min(100, max_results - len(message_ids)),
            )
            .execute()
        )
        message_ids.extend(m["id"] for m in response.get("messages", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return message_ids


def count_messages(refresh_token: str, query: str, cap: int = 20_000) -> int | None:
    """Exact number of messages matching `query`, by paging through ids only
    (500 per call, no message bodies). Gmail's resultSizeEstimate is too rough to
    report -- on a real inbox it said ~201 where 300+ matched a narrower search.
    Only used for metrics, so a failure returns None instead of failing the sync."""
    try:
        service = _service(refresh_token)
        total = 0
        page_token = None
        while total < cap:
            for delay in (*_RETRY_DELAYS, None):
                try:
                    response = (
                        service.users()
                        .messages()
                        .list(userId="me", q=query, pageToken=page_token, maxResults=500)
                        .execute()
                    )
                    break
                except HttpError as exc:
                    if delay is None or exc.resp.status not in (403, 429):
                        raise
                    time.sleep(delay)
            total += len(response.get("messages", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return total
    except Exception:
        return None


def history_list(refresh_token: str, start_history_id: str) -> list[str]:
    """Return message ids added since start_history_id. Used for webhook-triggered
    incremental sync."""
    service = _service(refresh_token)
    message_ids: list[str] = []
    page_token = None

    while True:
        response = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            )
            .execute()
        )
        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                message_ids.append(added["message"]["id"])
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return message_ids


def get_current_history_id(refresh_token: str) -> str:
    service = _service(refresh_token)
    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]


def watch(refresh_token: str, topic_name: str) -> dict[str, Any]:
    """Register (or renew) Gmail push notifications. Expires after ~7 days per the
    Gmail API — callers are responsible for renewal (see /sync/renew-watch)."""
    service = _service(refresh_token)
    return (
        service.users()
        .watch(userId="me", body={"topicName": topic_name, "labelIds": ["INBOX"]})
        .execute()
    )


def _decode_body_data(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")


def _extract_body_text(payload: dict) -> str:
    body = payload.get("body", {})
    if payload.get("mimeType") == "text/plain" and body.get("data"):
        return _decode_body_data(body["data"])

    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return _decode_body_data(part["body"]["data"])

    for part in payload.get("parts", []) or []:
        text = _extract_body_text(part)
        if text:
            return text

    if body.get("data"):
        return _decode_body_data(body["data"])

    return ""


# Cap on body text handed to the LLM extractor — a snippet is plenty for
# classification/extraction and keeps prompt size (and cost) predictable regardless
# of email length.
_MAX_BODY_CHARS = 4000


def _summarize(message: dict) -> dict[str, Any]:
    """Reduce a raw Gmail message to the fields heuristics/the extractor need."""
    headers = {
        h["name"].lower(): h["value"] for h in message.get("payload", {}).get("headers", [])
    }
    body_text = _extract_body_text(message.get("payload", {}))

    return {
        "id": message["id"],
        "thread_id": message["threadId"],
        "subject": headers.get("subject", ""),
        "sender": headers.get("from", ""),
        "snippet": message.get("snippet", ""),
        "body_text": body_text[:_MAX_BODY_CHARS],
        "internal_date": message.get("internalDate"),
    }


def get_message_summary(refresh_token: str, message_id: str) -> dict[str, Any]:
    """Fetch one message. For many messages use get_message_summaries, which
    shares one login and batches requests."""
    service = _service(refresh_token)
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()
    return _summarize(message)


# Gmail batch requests: each messages.get costs 5 quota units against a
# 250 units/user/second limit. 20 per batch every 0.5s is ~200 units/s.
_BATCH_SIZE = 20
_BATCH_INTERVAL = 0.5
# Quota is also enforced per minute, so retries must be able to outlast that window.
_RETRY_DELAYS = (5.0, 15.0, 30.0, 60.0)


def get_message_summaries(refresh_token: str, message_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch many messages with one OAuth refresh and batched HTTP requests
    (20 messages per round trip). Returns {message_id: summary}. Messages that
    still fail after retries (e.g. deleted since listing) are left out."""
    service = _service(refresh_token)
    summaries: dict[str, dict[str, Any]] = {}
    pending = list(message_ids)

    for attempt in range(len(_RETRY_DELAYS) + 1):
        failed: list[str] = []
        for i in range(0, len(pending), _BATCH_SIZE):
            chunk = pending[i : i + _BATCH_SIZE]

            def on_response(request_id: str, response: Any, exception: Exception | None) -> None:
                if exception is not None:
                    failed.append(request_id)
                else:
                    summaries[request_id] = _summarize(response)

            batch = service.new_batch_http_request(callback=on_response)
            for message_id in chunk:
                batch.add(
                    service.users().messages().get(userId="me", id=message_id, format="full"),
                    request_id=message_id,
                )
            batch.execute()
            time.sleep(_BATCH_INTERVAL)

        if not failed or attempt == len(_RETRY_DELAYS):
            break
        # Usually per-user rate limiting (429); back off and retry only the failures.
        time.sleep(_RETRY_DELAYS[attempt])
        pending = failed

    return summaries
