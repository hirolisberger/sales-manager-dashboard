"""Signed, expiring continuations with resource-specific state validation."""

import base64
import hashlib
import hmac
import json
import re
import time
from datetime import date
from uuid import UUID

from sales_manager_api.errors import ApplicationError


class SignedCursors:
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
                or not self.valid_state(payload["key"], scope)
            ):
                raise ValueError
            return payload["key"]
        except ValueError, KeyError, TypeError, UnicodeError:
            raise ApplicationError(
                400, "INVALID_CURSOR", "一覧を最初から取得してください。"
            ) from None

    def valid_state(self, state: dict, scope: dict) -> bool:
        raise NotImplementedError


class ProductCursors(SignedCursors):
    def valid_state(self, state: dict, scope: dict) -> bool:
        return (
            type(state) is dict
            and set(state) == {"PK", "SK"}
            and all(type(value) is str for value in state.values())
        )


class SaleCursors(SignedCursors):
    def valid_state(self, state: dict, scope: dict) -> bool:
        if type(state) is not dict or set(state) != {"day", "last_key"}:
            return False
        day = state["day"]
        if type(day) is not str or date.fromisoformat(day).isoformat() != day:
            return False
        if not scope["start_date"] <= day <= scope["end_date"]:
            return False
        key = state["last_key"]
        if key is None:
            return True
        if (
            type(key) is not dict
            or set(key) != {"PK", "SK"}
            or any(type(value) is not str for value in key.values())
            or key["PK"] != scope["store"] + "DAY#" + day
            or not key["SK"].startswith("SALE#")
        ):
            return False
        return str(UUID(key["SK"][5:])) == key["SK"][5:]
