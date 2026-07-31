from typing import Any

from fastapi import Cookie, HTTPException, status

from app.auth.session import decode_session_token
from app.db import get_db

SESSION_COOKIE_NAME = "session"


async def get_current_user(
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = decode_session_token(session)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    db = get_db()
    result = db.table("users").select("*").eq("id", user_id).maybe_single().execute()
    if not result or not result.data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return result.data
