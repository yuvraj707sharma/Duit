"""OpenTelemetry-Compatible Distributed Tracing Context for DUIT.

Tracks distributed trace identifiers across conversation, execution, and control planes:
- trace_id
- request_id
- tenant_id
- user_id
- account_id
- device_id
- provider_message_id
- execution_id
"""
import uuid
import contextvars
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


_current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_current_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
_current_tenant_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("tenant_id", default=None)
_current_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("user_id", default=None)
_current_account_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("account_id", default=None)
_current_device_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("device_id", default=None)
_current_provider_msg_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("provider_msg_id", default=None)
_current_execution_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("execution_id", default=None)


def get_trace_context() -> Dict[str, Any]:
    """Returns the active distributed trace context dictionary."""
    return {
        "trace_id": _current_trace_id.get(),
        "request_id": _current_request_id.get(),
        "tenant_id": _current_tenant_id.get(),
        "user_id": _current_user_id.get(),
        "account_id": _current_account_id.get(),
        "device_id": _current_device_id.get(),
        "provider_message_id": _current_provider_msg_id.get(),
        "execution_id": _current_execution_id.get()
    }


def set_trace_context(
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user_id: Optional[str] = None,
    account_id: Optional[str] = None,
    device_id: Optional[str] = None,
    provider_message_id: Optional[str] = None,
    execution_id: Optional[str] = None
) -> None:
    """Sets active trace context attributes."""
    if trace_id:
        _current_trace_id.set(trace_id)
    if request_id:
        _current_request_id.set(request_id)
    if tenant_id is not None:
        _current_tenant_id.set(tenant_id)
    if user_id is not None:
        _current_user_id.set(user_id)
    if account_id is not None:
        _current_account_id.set(account_id)
    if device_id is not None:
        _current_device_id.set(device_id)
    if provider_message_id is not None:
        _current_provider_msg_id.set(provider_message_id)
    if execution_id is not None:
        _current_execution_id.set(execution_id)


class OpenTelemetryTracingMiddleware(BaseHTTPMiddleware):
    """Propagates and injects W3C Trace Context and DUIT distributed identifiers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        request_id = request.headers.get("x-request-id") or f"req-{uuid.uuid4().hex[:12]}"
        tenant_id = request.headers.get("x-tenant-id")
        user_id = request.headers.get("x-user-id")
        account_id = request.headers.get("x-account-id")
        device_id = request.headers.get("x-device-id")
        provider_msg_id = request.headers.get("x-provider-message-id")
        execution_id = request.headers.get("x-execution-id")

        _current_trace_id.set(trace_id)
        _current_request_id.set(request_id)
        _current_tenant_id.set(tenant_id)
        _current_user_id.set(user_id)
        _current_account_id.set(account_id)
        _current_device_id.set(device_id)
        _current_provider_msg_id.set(provider_msg_id)
        _current_execution_id.set(execution_id)

        response = await call_next(request)

        # Propagate identifiers in response headers
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Request-Id"] = request_id
        return response

