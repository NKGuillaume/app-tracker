from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"
SESSION_EXPIRE_DAYS = 7


def create_session_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=SESSION_EXPIRE_DAYS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.session_secret_key, algorithm=ALGORITHM)


def decode_session_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.session_secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None
    return payload.get("sub")
