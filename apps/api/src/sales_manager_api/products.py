"""Product operations with persistent first-response replay and version guards."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sales_manager_api.cursors import ProductCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_models import (
    MAX_VERSION,
    Product,
    ProductCreate,
    ProductPatch,
)
from sales_manager_api.repository import DynamoRepository, StorageConflict, Write


@dataclass(frozen=True)
class ProductResult:
    body: dict
    status: int
    etag: str
    replayed: bool = False


class ProductService:
    def __init__(
        self,
        repo: DynamoRepository,
        cursors: ProductCursors,
        actor: str = "local-admin",
        clock=lambda: datetime.now(UTC),
    ):
        self.repo, self.cursors, self.actor, self.clock = repo, cursors, actor, clock

    def _product_key(self, product_id: str):
        return self.repo.key("PRODUCTS", f"PRODUCT#{product_id}")

    @staticmethod
    def public(item: dict) -> dict:
        return Product.model_validate(
            {k: v for k, v in item.items() if k not in {"PK", "SK"}}
        ).model_dump(mode="json")

    def get(self, product_id: str) -> dict:
        item = self.repo.get(self._product_key(product_id))
        if item is None:
            raise ApplicationError(404, "PRODUCT_NOT_FOUND", "商品が見つかりません。")
        return self.public(item)

    def list(self, limit: int, is_active: bool | None, cursor: str | None) -> dict:
        scope = {
            "store": self.repo.prefix,
            "resource": "products",
            "is_active": is_active,
            "limit": limit,
            "order": "id_asc",
        }
        key = self.cursors.decode(cursor, scope) if cursor is not None else None
        if key is not None:
            if key["PK"] != self.repo.key("PRODUCTS", "PRODUCT#")["PK"] or not key[
                "SK"
            ].startswith("PRODUCT#"):
                raise ApplicationError(
                    400, "INVALID_CURSOR", "一覧を最初から取得してください。"
                )
        rows, scanned = [], 0
        # Consume only as many underlying rows as remaining result slots. This
        # never advances the cursor past an unreturned matching product.
        while True:
            page = self.repo.query_page(
                "PRODUCTS", "PRODUCT#", limit=limit - len(rows), last_key=key
            )
            scanned += 1
            rows.extend(
                self.public(item)
                for item in page.items
                if is_active is None or item["is_active"] is is_active
            )
            key = page.last_key
            if key is None or len(rows) == limit:
                return {
                    "items": rows,
                    "next_cursor": self.cursors.encode(scope, key) if key else None,
                }
            if scanned >= 100:
                raise ApplicationError(
                    503, "QUERY_BUDGET_EXCEEDED", "検索条件を見直してください。"
                )

    def _request(
        self, request_key: str, method: str, path: str, body: dict, etag: str | None
    ):
        key = self.repo.key(f"REQUEST#{self.actor}", f"KEY#{request_key}")
        payload = json.dumps(
            [method, path, body, etag],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return key, hashlib.sha256(payload.encode()).hexdigest()

    def _replay(self, key: dict, fingerprint: str) -> ProductResult | None:
        saved = self.repo.get(key)
        if saved is None:
            return None
        if saved["request_hash"] != fingerprint:
            raise ApplicationError(
                409, "IDEMPOTENCY_CONFLICT", "要求キーを再利用できません。"
            )
        return ProductResult(
            saved["response_body"],
            saved["response_status"],
            saved["response_etag"],
            True,
        )

    def _record(self, key: dict, fingerprint: str, product: dict, status: int) -> Write:
        return Write(
            "put",
            {
                **key,
                "request_hash": fingerprint,
                "response_status": status,
                "response_body": product,
                "response_etag": f'"v{product["version"]}"',
            },
            "attribute_not_exists(PK)",
        )

    def create(self, body: ProductCreate, request_key: str) -> ProductResult:
        key, fingerprint = self._request(
            request_key, "POST", "/products", body.model_dump(), None
        )
        if replay := self._replay(key, fingerprint):
            return replay
        product_id = str(uuid4())
        now = self.clock().isoformat().replace("+00:00", "Z")
        product = {
            "id": product_id,
            **body.model_dump(),
            "is_active": True,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        code_key = self.repo.key("PRODUCT_CODES", f"CODE#{body.code}")
        try:
            self.repo.transact(
                [
                    Write(
                        "put",
                        {**self._product_key(product_id), **product},
                        "attribute_not_exists(PK)",
                    ),
                    Write(
                        "put",
                        {**code_key, "product_id": product_id},
                        "attribute_not_exists(PK)",
                    ),
                    self._record(key, fingerprint, product, 201),
                ]
            )
        except StorageConflict:
            if replay := self._replay(key, fingerprint):
                return replay
            if self.repo.get(code_key) is not None:
                raise ApplicationError(
                    409, "PRODUCT_CODE_CONFLICT", "商品コードが既に使われています。"
                ) from None
            raise
        return ProductResult(product, 201, '"v1"')

    def patch(
        self, product_id: str, body: ProductPatch, request_key: str, etag: str
    ) -> ProductResult:
        changes = body.model_dump(exclude_unset=True)
        key, fingerprint = self._request(
            request_key, "PATCH", f"/products/{product_id}", changes, etag
        )
        # Replay first, even if this resource has been updated since success.
        if replay := self._replay(key, fingerprint):
            return replay
        before = self.get(product_id)
        if etag != f'"v{before["version"]}"':
            raise ApplicationError(
                412, "VERSION_CONFLICT", "商品を再取得してください。"
            )
        if before["version"] == MAX_VERSION:
            raise ApplicationError(
                409, "VERSION_LIMIT_EXCEEDED", "この商品の版数が上限に達しています。"
            )
        product = {
            **before,
            **changes,
            "version": before["version"] + 1,
            "updated_at": self.clock().isoformat().replace("+00:00", "Z"),
        }
        try:
            self.repo.transact(
                [
                    Write(
                        "put",
                        {**self._product_key(product_id), **product},
                        "#v = :v",
                        {"#v": "version"},
                        {":v": before["version"]},
                    ),
                    self._record(key, fingerprint, product, 200),
                ]
            )
        except StorageConflict:
            if replay := self._replay(key, fingerprint):
                return replay
            if self.get(product_id)["version"] != before["version"]:
                raise ApplicationError(
                    412, "VERSION_CONFLICT", "商品を再取得してください。"
                ) from None
            raise
        return ProductResult(product, 200, f'"v{product["version"]}"')
