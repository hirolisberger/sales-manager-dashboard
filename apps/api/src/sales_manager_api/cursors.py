"""Signed, expiring product continuations. Not a cross-page snapshot."""

import base64
import hashlib
import hmac
import json
import re
import time

from sales_manager_api.errors import ApplicationError


class ProductCursors:
    def __init__(self, key: bytes, clock=time.time):
        if len(key) < 32:
            raise ValueError("A cursor key requires at least 32 bytes")
        self.key, self.clock = key, clock

    def encode(self, scope: dict, last_key: dict) -> str:
        payload = json.dumps(
            {"v": 1, "scope": scope, "key": last_key, "exp": int(self.clock()) + 900},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        body = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        signature = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
        return f"{body}.{signature}"

    def decode(self, token: str, scope: dict) -> dict:
        try:
            if not 1 <= len(token) <= 4096:
                raise ValueError
            body, signature = token.split(".")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", body) or not re.fullmatch(
                r"[0-9a-f]{64}", signature
            ):
                raise ValueError
            expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(
                base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
            )
            now = self.clock()
            if (
                type(payload) is not dict
                or type(payload["v"]) is not int
                or payload["v"] != 1
                or payload["scope"] != scope
                or type(payload["exp"]) is not int
                or not now < payload["exp"] <= now + 900
                or type(payload["key"]) is not dict
                or set(payload["key"]) != {"PK", "SK"}
                or any(type(value) is not str for value in payload["key"].values())
            ):
                raise ValueError
            return payload["key"]
        except ValueError, KeyError, TypeError, UnicodeError:
            raise ApplicationError(
                400, "INVALID_CURSOR", "一覧を最初から取得してください。"
            ) from None
