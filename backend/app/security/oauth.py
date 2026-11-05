"""Google OAuth 2.0 Flow Helper with CSRF State Storage and Narrow Scopes."""
import secrets
import time
from typing import Dict, Any, Optional, Tuple
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


class OAuthStateStore:
    """Server-side one-time-use CSRF token store for OAuth flows."""
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._states: Dict[str, Dict[str, Any]] = {}

    def create_state(self, user_id: str) -> str:
        """Generates a cryptographically random, session-bound CSRF token stored server-side."""
        now = time.time()
        # Clean expired states
        expired = [k for k, v in self._states.items() if now - v["created_at"] > self.ttl_seconds]
        for k in expired:
            self._states.pop(k, None)

        token = secrets.token_urlsafe(32)
        self._states[token] = {
            "user_id": user_id,
            "created_at": now,
            "used": False
        }
        return token

    def validate_and_consume(self, state: str) -> Optional[str]:
        """
        Validates the state token, ensures one-time usage, checks expiration,
        and invalidates/deletes it immediately upon use.
        Returns the bound user_id if valid, or None if invalid/expired/reused.
        """
        if not state or not isinstance(state, str):
            return None
        entry = self._states.pop(state, None)
        if not entry:
            return None
        if entry.get("used"):
            return None
        if time.time() - entry.get("created_at", 0) > self.ttl_seconds:
            return None
        entry["used"] = True
        return entry.get("user_id")


oauth_state_store = OAuthStateStore()


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


def generate_auth_url(user_id: str) -> Tuple[str, str]:
    """
    Generates the authorization URL with a cryptographically random CSRF state token.
    Returns (auth_url, state).
    """
    state_token = oauth_state_store.create_state(user_id=user_id)
    flow = get_oauth_flow(state=state_token)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return auth_url, state_token
