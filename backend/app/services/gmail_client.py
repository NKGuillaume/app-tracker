"""Thin wrapper around the Gmail API for the operations the sync pipeline needs.

Every function takes a plaintext (already-decrypted) refresh token and mints a
short-lived service client from it — there is no persistent connection, so this
is safe to call from request handlers, background tasks, or the scheduler.
"""

import base64
from typing import Any

from googleapiclient.discovery import Resource, build

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


def count_messages_estimate(refresh_token: str, query: str) -> int:
    """Gmail's own estimate of how many messages match `query` (one cheap call,
    no paging). Approximate by Google's definition -- label it as such."""
    service = _service(refresh_token)
    response = service.users().messages().list(userId="me", q=query, maxResults=1).execute()
    return int(response.get("resultSizeEstimate", 0))


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


def get_message_summary(refresh_token: str, message_id: str) -> dict[str, Any]:
    """Fetch a message and reduce it to the fields heuristics/the extractor actually need."""
    service = _service(refresh_token)
    message = service.users().messages().get(userId="me", id=message_id, format="full").execute()

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
