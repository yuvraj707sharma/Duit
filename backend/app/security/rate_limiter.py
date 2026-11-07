"""Multi-Dimension Rate Limiter for DUIT.

Enforces sliding-window rate limits across:
- Client IP
- Authenticated User (tenant_id:user_id)
- WhatsApp Account (whatsapp_account_id)
- Desktop Device (device_id)
"""
import time
import threading
from typing import Dict, List, Optional, Tuple
from fastapi import Request, HTTPException


class RateLimiter:
    """Thread-safe sliding-window rate limiter."""

    def __init__(
        self,
        default_ip_limit: int = 120,
        default_user_limit: int = 60,
        default_account_limit: int = 60,
        default_device_limit: int = 60,
        window_seconds: int = 60
    ):
        self.default_ip_limit = default_ip_limit
        self.default_user_limit = default_user_limit
        self.default_account_limit = default_account_limit
        self.default_device_limit = default_device_limit
        self.window_seconds = window_seconds

        self._buckets: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def check(
        self,
        dimension: str,
        identifier: str,
        limit: Optional[int] = None
    ) -> Tuple[bool, int, int]:
        """Checks rate limit for a specific dimension and identifier.

        Returns (is_allowed, remaining_requests, retry_after_seconds).
        """
        if not identifier:
            return True, 999, 0

        max_allowed = limit
        if max_allowed is None:
            if dimension == "ip":
                max_allowed = self.default_ip_limit
            elif dimension == "user":
                max_allowed = self.default_user_limit
            elif dimension == "account":
                max_allowed = self.default_account_limit
            elif dimension == "device":
                max_allowed = self.default_device_limit
            else:
                max_allowed = 60

        key = f"{dimension}:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds

        with self._lock:
            history = self._buckets.get(key, [])
            # Prune timestamps outside current sliding window
            history = [ts for ts in history if ts > window_start]

            if len(history) >= max_allowed:
                oldest = history[0]
                retry_after = max(1, int(oldest + self.window_seconds - now) + 1)
                self._buckets[key] = history
                return False, 0, retry_after

            history.append(now)
            self._buckets[key] = history
            remaining = max_allowed - len(history)
            return True, remaining, 0

    def enforce(
        self,
        client_ip: Optional[str] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        device_id: Optional[str] = None
    ) -> None:
        """Enforces limits across all applicable dimensions.

        Raises HTTPException(status_code=429) if any limit is breached.
        """
        # 1. IP Dimension
        if client_ip:
            allowed, _, retry_after = self.check("ip", client_ip)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="IP rate limit exceeded. Please slow down.",
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Scope": "ip"}
                )

        # 2. User Dimension
        if user_id:
            user_key = f"{tenant_id}:{user_id}" if tenant_id else user_id
            allowed, _, retry_after = self.check("user", user_key)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="User rate limit exceeded. Please wait before making more requests.",
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Scope": "user"}
                )

        # 3. Account Dimension
        if account_id:
            allowed, _, retry_after = self.check("account", account_id)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="WhatsApp account rate limit exceeded.",
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Scope": "account"}
                )

        # 4. Device Dimension
        if device_id:
            allowed, _, retry_after = self.check("device", device_id)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Device rate limit exceeded.",
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Scope": "device"}
                )

    def reset(self) -> None:
        """Clears all in-memory rate limit buckets (useful for tests)."""
        with self._lock:
            self._buckets.clear()

    def cleanup(self) -> int:
        """Prunes all expired timestamps and empty buckets."""
        now = time.time()
        window_start = now - self.window_seconds
        pruned_count = 0
        with self._lock:
            keys_to_delete = []
            for k, timestamps in self._buckets.items():
                valid = [ts for ts in timestamps if ts > window_start]
                if not valid:
                    keys_to_delete.append(k)
                else:
                    self._buckets[k] = valid
            for k in keys_to_delete:
                del self._buckets[k]
                pruned_count += 1
        return pruned_count


# Global rate limiter instance
rate_limiter = RateLimiter()


def extract_client_ip(request: Request) -> str:
    """Extracts client IP considering trusted forwarded headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"
