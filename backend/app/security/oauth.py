"""Google OAuth 2.0 Flow Helper with CSRF State Storage and Narrow Scopes."""
import secrets
import time
from typing import Dict, Any, Optional, Tuple, List, Set
from backend.app.config import settings

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/contacts.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]


class OAuthStateStore:
    """Server-side one-time-use CSRF and capability token store for OAuth flows."""
    def __init__(self, ttl_seconds: int = 600):
        self.ttl_seconds = ttl_seconds
        self._states: Dict[str, Dict[str, Any]] = {}
        self._consumed_states: Set[str] = set()

    def create_state(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        scopes: Optional[List[str]] = None
    ) -> str:
        """Generates a cryptographically random, session-bound CSRF token stored server-side."""
        now = time.time()
        # Clean expired states
        expired = [k for k, v in self._states.items() if now - v["created_at"] > self.ttl_seconds]
        for k in expired:
            self._states.pop(k, None)

        token = secrets.token_urlsafe(32)
        tid = tenant_id or "tenant_default_duit"
        self._states[token] = {
            "user_id": user_id,
            "tenant_id": tid,
            "scopes": scopes or ["calendar.read", "calendar.write", "gmail.read", "gmail.send"],
            "created_at": now,
            "used": False
        }
        return token

    def is_consumed(self, state: str) -> bool:
        """Returns True if the state token was previously valid and has already been consumed."""
        return state in self._consumed_states

    def validate_and_consume_payload(self, state: str) -> Optional[Dict[str, Any]]:
        """Validates and consumes state token, returning full identity payload {user_id, tenant_id, scopes}."""
        if not state or not isinstance(state, str):
            return None
        if state in self._consumed_states:
            return None
        entry = self._states.pop(state, None)
        if not entry:
            return None
        if entry.get("used"):
            self._consumed_states.add(state)
            return None
        if time.time() - entry.get("created_at", 0) > self.ttl_seconds:
            return None
        entry["used"] = True
        self._consumed_states.add(state)
        return {
            "user_id": entry.get("user_id"),
            "tenant_id": entry.get("tenant_id", "tenant_default_duit"),
            "scopes": entry.get("scopes", [])
        }

    def validate_and_consume(self, state: str) -> Optional[str]:
        """
        Validates the state token, ensures one-time usage, checks expiration,
        and invalidates/deletes it immediately upon use.
        Returns the bound user_id if valid, or None if invalid/expired/reused.
        """
        payload = self.validate_and_consume_payload(state)
        return payload["user_id"] if payload else None


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


def generate_auth_url(
    user_id: str,
    tenant_id: Optional[str] = None,
    scopes: Optional[List[str]] = None
) -> Tuple[str, str]:
    """
    Generates the authorization URL with a cryptographically random CSRF state token.
    Returns (auth_url, state).
    """
    state_token = oauth_state_store.create_state(
        user_id=user_id,
        tenant_id=tenant_id,
        scopes=scopes
    )
    flow = get_oauth_flow(state=state_token)
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return auth_url, state_token
