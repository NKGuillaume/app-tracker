from typing import Any

from fastapi import APIRouter, Depends

from app.auth.deps import get_current_user
from app.db import get_db
from app.services import sync_pipeline

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/manual")
async def manual_sync(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    # Synchronous for v1 -- expected email volume per user is small enough that this
    # completes well within a normal request timeout. Revisit with BackgroundTasks +
    # polling if that stops being true.
    stats = sync_pipeline.run_manual_sync(current_user)
    return {"status": "completed", **stats}


@router.get("/status")
async def sync_status(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    db = get_db()
    result = (
        db.table("sync_state")
        .select("last_manual_sync_at")
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    return {"last_manual_sync_at": result.data.get("last_manual_sync_at") if result.data else None}
