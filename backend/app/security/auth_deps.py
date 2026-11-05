"""Centralized Authentication & Authorization Dependencies."""
import hmac
from typing import Optional
from dataclasses import dataclass
from fastapi import Header, HTTPException, Request
from backend.app.config import settings


@dataclass
class AuthenticatedUser:
    user_id: str
    is_admin: bool = False


async def get_optional_current_user(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret"),
    x_admin_token: Optional[str] = Header(None, alias="x-admin-token"),
    authorization: Optional[str] = Header(None, alias="authorization")
) -> Optional[AuthenticatedUser]:
    """Extracts authenticated user if credentials are valid, otherwise returns None without raising 401."""
    # Check for admin token
    if x_admin_token:
        expected_secret = settings.SECRET_KEY or settings.GATEWAY_SHARED_SECRET
        if expected_secret and hmac.compare_digest(x_admin_token.strip(), expected_secret.strip()):
            user_id = x_user_id.strip() if x_user_id else "admin"
            return AuthenticatedUser(user_id=user_id, is_admin=True)

    # Check gateway-authenticated user proxying
    if x_gateway_secret:
        expected_gw = settings.GATEWAY_SHARED_SECRET
        if expected_gw and hmac.compare_digest(x_gateway_secret.strip(), expected_gw.strip()):
            if x_user_id and x_user_id.strip():
                return AuthenticatedUser(user_id=x_user_id.strip(), is_admin=False)

    # Check Authorization: Bearer token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        expected = settings.SECRET_KEY or settings.GATEWAY_SHARED_SECRET
        if expected and hmac.compare_digest(token, expected):
            user_id = x_user_id.strip() if x_user_id else "authenticated_user"
            return AuthenticatedUser(user_id=user_id, is_admin=True)

    # In development mode, allow x-user-id if explicitly provided
    if not settings.is_production and x_user_id and x_user_id.strip():
        clean_user = x_user_id.strip()
        is_admin_user = clean_user.lower() == "admin"
        return AuthenticatedUser(user_id=clean_user, is_admin=is_admin_user)

    return None


async def get_current_user(
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_gateway_secret: Optional[str] = Header(None, alias="x-gateway-secret"),
    x_admin_token: Optional[str] = Header(None, alias="x-admin-token"),
    authorization: Optional[str] = Header(None, alias="authorization")
) -> AuthenticatedUser:
    """
    Centralized authentication dependency.
    Requires verified identity from gateway, admin token, or authenticated user header.
    Rejects unauthenticated requests with 401 Unauthorized.
    """
    user = await get_optional_current_user(
        request=request,
        x_user_id=x_user_id,
        x_gateway_secret=x_gateway_secret,
        x_admin_token=x_admin_token,
        authorization=authorization
    )
    if user:
        return user

    # In dev mode, return default user only if not in production and x_user_id was omitted
    if not settings.is_production and not x_user_id:
        return AuthenticatedUser(user_id="default_user", is_admin=True)

    raise HTTPException(status_code=401, detail="Authentication required")


def require_user_access(target_user_id: str, current_user: AuthenticatedUser) -> None:
    """Enforces that a user can only access their own resources unless admin."""
    if current_user.is_admin:
        return
    if current_user.user_id.strip().lstrip("+") != target_user_id.strip().lstrip("+"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: cannot access another user's resources"
        )
