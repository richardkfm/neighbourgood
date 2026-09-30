"""Reject NUL (``\\x00``) characters in user-supplied text with a 422.

PostgreSQL cannot store NUL in text columns and raises an error that would
otherwise surface as a 500. Rather than annotating every string field in every
schema, this pure-ASGI middleware checks the request once, centrally:

  - the URL path and query string (percent-decoded), and
  - JSON request bodies (every string value and object key).

Multipart uploads are not inspected (binary payloads legitimately contain NUL).
Malformed JSON is passed through untouched so FastAPI reports its usual error.
"""

import json
from urllib.parse import unquote_to_bytes

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DETAIL = "NUL (\\x00) characters are not allowed"


def _contains_nul(value) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, list):
        return any(_contains_nul(v) for v in value)
    if isinstance(value, dict):
        return any(_contains_nul(k) or _contains_nul(v) for k, v in value.items())
    return False


def _json_body_has_nul(body: bytes) -> bool:
    # Cheap pre-filter: a NUL is either a raw byte or the escape sequence \u0000.
    if b"\\u0000" not in body and b"\x00" not in body:
        return False
    try:
        return _contains_nul(json.loads(body))
    except (ValueError, RecursionError):
        return b"\x00" in body


def _reject(loc: str) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": [{"type": "value_error", "loc": [loc], "msg": _DETAIL, "input": None}]},
    )


class NulByteMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if b"\x00" in unquote_to_bytes(scope.get("query_string", b"")) or "\x00" in scope.get("path", ""):
            await _reject("query")(scope, receive, send)
            return

        content_type = ""
        for name, value in scope.get("headers", []):
            if name == b"content-type":
                content_type = value.decode("latin-1").lower()
                break

        if not content_type.startswith("application/json"):
            await self.app(scope, receive, send)
            return

        # Buffer the body, inspect it, then replay it to the application.
        chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        body = b"".join(chunks)

        if _json_body_has_nul(body):
            await _reject("body")(scope, receive, send)
            return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
