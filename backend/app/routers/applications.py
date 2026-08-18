from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.schemas import ApplicationOut, ApplicationUpdate, PaginatedApplications

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
    if update_data.get("application_date"):
        update_data["application_date"] = update_data["application_date"].isoformat()
    # A manual correction is authoritative -- future syncs won't overwrite it (see
    # sync_pipeline._upsert_application).
    update_data["manually_edited"] = True

    result = db.table("applications").update(update_data).eq("id", application_id).execute()
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
