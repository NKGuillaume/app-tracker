"""Shared helpers for the measurement scripts. Run scripts from `backend/`:
    python -m scripts.resume_metrics --email you@example.com
"""

import sys
from pathlib import Path
from typing import Any

EVAL_DIR = Path(__file__).resolve().parent.parent / "eval"


def load_user(email: str) -> dict[str, Any]:
    # Imported lazily so `score` (pure CSV math) works without any keys set.
    from app.db import get_db

    result = get_db().table("users").select("*").eq("email", email).maybe_single().execute()
    if not result or not result.data:
        sys.exit(f"No user with email {email!r}. Log in through the app once first.")
    user = result.data
    if not user.get("google_refresh_token_encrypted"):
        sys.exit("That user has no stored Gmail refresh token. Log in through the app again.")
    return user


def pct(part: float, whole: float) -> str:
    if not whole:
        return "n/a (denominator is 0)"
    return f"{part:g}/{whole:g} = {100 * part / whole:.1f}%"
