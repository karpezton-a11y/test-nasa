"""Small pure-ASGI middlewares.

* BodySizeLimitMiddleware: it does not trust Content-Length alone: bodies are counted while they stream
  in (chunked uploads have no Content-Length). Bodies are small JSON requests, so the accepted body is
  buffered (at most MAX_BODY_BYTES) and replayed.
* UnhandledErrorMiddleware: turns an unexpected exception into the sanitized INTERNAL_ERROR response
  *inside* the CORS middleware, so the browser can read it (Starlette's own 500 handler runs outside
  CORS and has no CORS headers; audit LOW).
* SecurityHeadersMiddleware: adds nosniff and no-referrer to every response (audit LOW).
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import GENERIC_INTERNAL_MESSAGE, error_response

logger = logging.getLogger("trendtrace.errors")
BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})
SECURITY_HEADERS = ((b"x-content-type-options", b"nosniff"), (b"referrer-policy", b"no-referrer"))


class UnhandledErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            if started:  # part of the response was sent; nothing safe can replace it
                raise
            logger.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            await error_response("INTERNAL_ERROR", 500, GENERIC_INTERNAL_MESSAGE)(scope, receive, send)


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [header for header in SECURITY_HEADERS if header[0] not in present]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, with_headers)


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") not in BODY_METHODS:
            await self.app(scope, receive, send)
            return
        if self._declared_length_too_large(scope):
            await self._reject(scope, receive, send)
            return
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body = message.get("body", b"")
            total += len(body)
            if total > self.max_bytes:
                await self._reject(scope, receive, send)
                return
            chunks.append(body)
            if not message.get("more_body", False):
                break
        await self.app(scope, _replay(b"".join(chunks), receive), send)

    def _declared_length_too_large(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value) > self.max_bytes
                except ValueError:
                    return True
        return False

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = error_response(
            "PAYLOAD_TOO_LARGE", 413, "The request body is too large.", {"max_bytes": self.max_bytes}
        )
        await response(scope, receive, send)


def _replay(body: bytes, receive: Receive) -> Receive:
    delivered = False

    async def replay() -> Message:
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay
