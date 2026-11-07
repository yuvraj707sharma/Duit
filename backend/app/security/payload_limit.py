"""Request Payload Size Limiter Middleware for DUIT.

Guards the application against oversized requests, unbounded memory buffering,
and denial-of-service attempts by rejecting bodies larger than a configured threshold.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


DEFAULT_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 Megabytes


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int = DEFAULT_MAX_BODY_BYTES):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        # 1. Quick check via Content-Length header
        content_length_str = request.headers.get("content-length")
        if content_length_str:
            try:
                content_length = int(content_length_str)
                if content_length > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": "Payload Too Large",
                            "message": f"Request body exceeds maximum allowed size of {self.max_bytes} bytes",
                            "max_bytes": self.max_bytes
                        }
                    )
            except ValueError:
                pass

        # 2. Guard chunked / streaming bodies by wrapping receive
        bytes_received = 0
        original_receive = request.receive

        async def limited_receive():
            nonlocal bytes_received
            message = await original_receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                bytes_received += len(body)
                if bytes_received > self.max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Request body exceeds maximum allowed size of {self.max_bytes} bytes"
                    )
            return message

        request._receive = limited_receive

        try:
            return await call_next(request)
        except Exception as exc:
            from fastapi import HTTPException
            if isinstance(exc, HTTPException) and exc.status_code == 413:
                return JSONResponse(
                    status_code=413,
                    content={
                        "error": "Payload Too Large",
                        "message": str(exc.detail),
                        "max_bytes": self.max_bytes
                    }
                )
            raise exc
