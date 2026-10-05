"""Google OAuth 2.0 Flow Helper with narrow Gmail & Calendar scopes."""
from typing import Dict, Any, Optional
from backend.app.config import settings

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]


def get_oauth_flow(state: Optional[str] = None):
    """Creates a Google OAuth Flow with strict narrow scopes."""
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        raise RuntimeError("google_auth_oauthlib is required for live Google OAuth flow")
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID or "mock_client_id",
            "client_secret": settings.GOOGLE_CLIENT_SECRET or "mock_client_secret",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_REDIRECT_URI]
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        state=state
    )
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow


def generate_auth_url(user_id: str) -> str:
    """Generates the authorization URL with state encoded."""
    flow = get_oauth_flow(state=user_id)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return auth_url
