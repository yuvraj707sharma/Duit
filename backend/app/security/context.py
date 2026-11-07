"""Security Context and Server-Verified Identity Module."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import uuid


class SecurityContextError(Exception):
    """Raised when request identity cannot be verified or violates tenant boundaries."""
    pass


@dataclass(frozen=True)
class SecurityContext:
    tenant_id: str
    user_id: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    account_id: Optional[str] = None
    device_id: Optional[str] = None

    def __post_init__(self):
        if not self.tenant_id or not self.tenant_id.strip():
            raise SecurityContextError("tenant_id must be provided and non-empty")
        if not self.user_id or not self.user_id.strip():
            raise SecurityContextError("user_id must be provided and non-empty")
        if not self.request_id or not self.request_id.strip():
            raise SecurityContextError("request_id must be provided and non-empty")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "request_id": self.request_id,
            "account_id": self.account_id,
            "device_id": self.device_id,
        }
