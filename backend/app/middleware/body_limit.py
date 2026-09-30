"""Request body size limit.

JSON and other bodies are capped at ``settings.max_request_body_bytes`` (1 MB).
``multipart/form-data`` (image uploads) gets the image limit plus room for the
multipart framing; the upload handlers still enforce the 5 MB image limit on
the file itself. Oversized requests are answered with 413 before the body
reaches a handler: a too-large ``Content-Length`` is refused up front, and a
body without one (chunked) is counted as it streams in.
"""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Multipart boundaries, part headers and small form fields around the file
_MULTIPART_OVERHEAD = 64 * 1024


class _BodyTooLarge(HTTPException):
    """Raised from ``receive``; FastAPI re-raises HTTPExceptions from body parsing,
    so the handler answers 413 (instead of a generic 400) with the usual middleware."""

    def __init__(self, limit: int) -> None:
        super().__init__(status_code=413, detail=f"Request body too large (limit {limit} bytes)")


def _limit_for(content_type: str) -> int:
    if content_type.lower().startswith("multipart/form-data"):
        return settings.max_image_size + _MULTIPART_OVERHEAD
    return settings.max_request_body_bytes


async def _send_413(send: Send, limit: int) -> None:
    body = b'{"detail":"Request body too large (limit %d bytes)"}' % limit
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        limit = _limit_for(headers.get(b"content-type", b"").decode("latin-1"))

        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    await _send_413(send, limit)
                    return
            except ValueError:
                pass

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _BodyTooLarge(limit)
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await _send_413(send, limit)
