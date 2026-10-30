"""Assign server request IDs and record only fixed request metadata."""

import logging
from uuid import uuid4

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from sales_manager_api.errors import error_response

logger = logging.getLogger("sales_manager_api.requests")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4()
        scope.setdefault("state", {})["request_id"] = request_id
        started = False
        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal started, status
            if message["type"] == "http.response.start":
                started = True
                status = message["status"]
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", str(request_id).encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            # No exception message, traceback, body, headers, path or query in logs.
            logger.error(
                "request_failed request_id=%s error_type=%s",
                request_id,
                type(exc).__name__,
            )
            if started:
                # A started/streaming response cannot be replaced by JSON.
                raise RuntimeError("Response processing failed after headers") from None
            response = error_response(
                Request(scope), 500, "INTERNAL_ERROR", "処理に失敗しました。"
            )
            await response(scope, receive, send_with_request_id)

        logger.info(
            "request_finished request_id=%s method=%s status=%s",
            request_id,
            scope["method"],
            status,
        )
