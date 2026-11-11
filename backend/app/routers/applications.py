from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from google.auth.exceptions import RefreshError

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.schemas import ApplicationOut, ApplicationUpdate, PaginatedApplications
from app.services import gmail_client, sync_pipeline
from app.services.crypto import decrypt_token
from app.services.interview_prep import generate_interview_prep

router = APIRouter(prefix="/applications", tags=["applications"])

SORTABLE_COLUMNS = {"company", "job_title", "application_date", "status", "created_at", "updated_at"}


def _get_owned_application(db, application_id: str, user_id: str) -> dict | None:
    result = (
        db.table("applications")
        .select("*")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    return result.data if result else None


@router.get("", response_model=PaginatedApplications)
async def list_applications(
    search: str | None = None,
    status: str | None = None,
    sort: str = "-updated_at",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
) -> PaginatedApplications:
    db = get_db()
    q = db.table("applications").select("*", count="exact").eq("user_id", current_user["id"])

    if search:
        pattern = f"%{search}%"
        q = q.or_(f"company.ilike.{pattern},job_title.ilike.{pattern}")

    if status:
        q = q.eq("status", status)

    descending = sort.startswith("-")
    sort_column = sort[1:] if descending else sort
    if sort_column not in SORTABLE_COLUMNS:
        sort_column, descending = "updated_at", True
    # nullsfirst=False keeps rows with no date at the bottom for descending date
    # sorts (Postgres would otherwise put NULLs first).
    q = q.order(sort_column, desc=descending, nullsfirst=False)

    start = (page - 1) * page_size
    q = q.range(start, start + page_size - 1)

    result = q.execute()
    return PaginatedApplications(items=result.data, total=result.count or 0, page=page, page_size=page_size)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: str, current_user: dict = Depends(get_current_user)
) -> ApplicationOut:
    db = get_db()
    application = _get_owned_application(db, application_id, current_user["id"])
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return ApplicationOut(**application)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: str,
    payload: ApplicationUpdate,
    current_user: dict = Depends(get_current_user),
) -> ApplicationOut:
    db = get_db()
    if not _get_owned_application(db, application_id, current_user["id"]):
        raise HTTPException(status_code=404, detail="Application not found")

    update_data = payload.model_dump(exclude_unset=True)
    for date_field in ("application_date", "interview_deadline"):
        if update_data.get(date_field):
            update_data[date_field] = update_data[date_field].isoformat()
    # A manual correction is authoritative -- future syncs won't overwrite it (see
    # sync_pipeline._upsert_application).
    update_data["manually_edited"] = True

    result = db.table("applications").update(update_data).eq("id", application_id).execute()
    return ApplicationOut(**result.data[0])


# Plain `def`, not async: Gmail and OpenAI calls block, so FastAPI runs this in
# its threadpool instead of stalling the event loop.
@router.post("/{application_id}/interview-prep", response_model=ApplicationOut)
def interview_prep(
    application_id: str,
    regenerate: bool = False,
    current_user: dict = Depends(get_current_user),
) -> ApplicationOut:
    db = get_db()
    application = _get_owned_application(db, application_id, current_user["id"])
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if application.get("interview_prep") and not regenerate:
        return ApplicationOut(**application)

    try:
        token = decrypt_token(current_user["google_refresh_token_encrypted"])
        email = gmail_client.get_message_summary(token, application["source_email_id"])
        email["sent_date"] = sync_pipeline._internal_date_to_iso(email.get("internal_date"))
    except RefreshError:
        raise HTTPException(
            status_code=409, detail="Your Gmail sign-in expired. Sign in again to read this email."
        )
    except Exception:
        email = None  # e.g. the email was deleted; fall back to the stored snippet

    try:
        prep = generate_interview_prep(application, email)
    except Exception:
        raise HTTPException(status_code=502, detail="Couldn't generate prep tips. Try again.")

    update = {
        "interview_prep": prep.model_dump(
            mode="json", include={"what_to_expect", "prep_steps", "practice_topics", "day_of_tips"}
        ),
        "interview_prep_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    # Fill interview details the row is missing (rows from before interview
    # extraction existed), but never override what sync or the user set.
    if not application.get("manually_edited"):
        if not application.get("interview_type"):
            update["interview_type"] = prep.interview_type
        if not application.get("assessment_platform") and prep.assessment_platform:
            update["assessment_platform"] = prep.assessment_platform
        if not application.get("interview_deadline") and prep.interview_deadline:
            update["interview_deadline"] = prep.interview_deadline.isoformat()

    result = db.table("applications").update(update).eq("id", application_id).execute()
    return ApplicationOut(**result.data[0])


@router.delete("/{application_id}", status_code=204)
async def delete_application(application_id: str, current_user: dict = Depends(get_current_user)) -> Response:
    db = get_db()
    # processed_emails rows keep their idempotency record but drop the FK link,
    # otherwise the delete below violates the foreign-key constraint.
    db.table("processed_emails").update({"application_id": None}).eq(
        "user_id", current_user["id"]
    ).eq("application_id", application_id).execute()
    db.table("applications").delete().eq("id", application_id).eq("user_id", current_user["id"]).execute()
    return Response(status_code=204)
