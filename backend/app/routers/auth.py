from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

from app.auth import google_oauth
from app.auth.deps import SESSION_COOKIE_NAME, get_current_user
from app.auth.session import SESSION_EXPIRE_DAYS, create_session_token
from app.config import settings
from app.db import get_db
from app.models.schemas import UserOut
from app.services.crypto import encrypt_token

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE_NAME = "oauth_state"
CODE_VERIFIER_COOKIE_NAME = "oauth_code_verifier"


@router.get("/login")
async def login() -> RedirectResponse:
    state = google_oauth.generate_state()
    code_verifier = google_oauth.generate_code_verifier()
    auth_url = google_oauth.get_authorization_url(state, code_verifier)

    response = RedirectResponse(auth_url)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=600,
    )
    response.set_cookie(
        CODE_VERIFIER_COOKIE_NAME,
        code_verifier,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=600,
    )
    return response


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None, alias=STATE_COOKIE_NAME),
    oauth_code_verifier: str | None = Cookie(default=None, alias=CODE_VERIFIER_COOKIE_NAME),
) -> RedirectResponse:
    if not oauth_state or oauth_state != state:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")
    if not oauth_code_verifier:
        raise HTTPException(status_code=400, detail="Missing PKCE code verifier")

    credentials = google_oauth.exchange_code_for_tokens(code, oauth_code_verifier)
    claims = google_oauth.verify_id_token(credentials)

    google_sub = claims["sub"]
    email = claims["email"]

    db = get_db()
    existing = db.table("users").select("*").eq("google_sub", google_sub).maybe_single().execute()

    user_data = {
        "google_sub": google_sub,
        "email": email,
        "name": claims.get("name"),
        "avatar_url": claims.get("picture"),
    }
    # Google only issues a refresh_token on first consent (or a forced re-consent via
    # prompt=consent, which /auth/login always sets) — never overwrite a previously
    # stored token with nothing on a call that didn't return one.
    if credentials.refresh_token:
        user_data["google_refresh_token_encrypted"] = encrypt_token(credentials.refresh_token)
        user_data["google_token_scope"] = " ".join(credentials.scopes or [])

    if existing and existing.data:
        user_id = existing.data["id"]
        db.table("users").update(user_data).eq("id", user_id).execute()
    else:
        if "google_refresh_token_encrypted" not in user_data:
            raise HTTPException(
                status_code=500,
                detail="Google did not return a refresh token on first consent",
            )
        inserted = db.table("users").insert(user_data).execute()
        user_id = inserted.data[0]["id"]

    session_token = create_session_token(user_id)

    response = RedirectResponse(f"{settings.frontend_origin}/auth/callback")
    response.delete_cookie(STATE_COOKIE_NAME)
    response.delete_cookie(CODE_VERIFIER_COOKIE_NAME)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        httponly=True,
        secure=settings.cookies_secure,
        samesite="lax",
        max_age=SESSION_EXPIRE_DAYS * 24 * 3600,
    )
    return response


@router.post("/logout", status_code=204)
async def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/me", response_model=UserOut)
async def me(current_user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**current_user)
