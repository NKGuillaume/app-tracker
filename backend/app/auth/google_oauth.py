import secrets

import google.auth.transport.requests
from google.oauth2 import id_token as google_id_token
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app.config import settings

# openid+email+profile identify the user; gmail.readonly is all we need to read mail.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }


def _build_flow() -> Flow:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def get_authorization_url(state: str) -> str:
    flow = _build_flow()
    # access_type=offline + prompt=consent forces Google to issue a refresh_token,
    # which is otherwise only granted on a user's very first consent.
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> Credentials:
    flow = _build_flow()
    flow.fetch_token(code=code)
    return flow.credentials


def verify_id_token(credentials: Credentials) -> dict:
    request = google.auth.transport.requests.Request()
    return google_id_token.verify_oauth2_token(
        credentials.id_token, request, settings.google_client_id
    )


def credentials_from_refresh_token(refresh_token: str) -> Credentials:
    """Mint a live Credentials object from a stored refresh token, for background sync
    where there is no active browser session."""
    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds
