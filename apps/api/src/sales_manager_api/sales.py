"""Sale writes: calculated snapshots, atomic changes, history and first responses."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_models import MAX_VERSION
from sales_manager_api.repository import DynamoRepository, StorageConflict, Write
from sales_manager_api.sale_models import (
    MAX_AMOUNT,
    Cancellation,
    Sale,
    SaleCreate,
    SalePatch,
)


@dataclass(frozen=True)
class SaleResult:
    body: dict
    replayed: bool = False
    status: int = 201


def calculate_amounts(body: SaleCreate) -> tuple[list[int], int]:
    amounts = [line.unit_price_yen * line.quantity for line in body.lines]
    total = sum(amounts)
    if total > MAX_AMOUNT:
        raise ApplicationError(
            422,
            "AMOUNT_LIMIT_EXCEEDED",
            "売上合計は9,999,999,999円以下にしてください。",
        )
    return amounts, total


class SaleService:
    def __init__(
        self,
        repo: DynamoRepository,
        *,
        actor: str = "local-admin",
        clock=lambda: datetime.now(UTC),
    ):
        self.repo, self.actor, self.clock = repo, actor, clock

    def _product(self, product_id: str) -> dict:
        product = self.repo.get(self.repo.key("PRODUCTS", f"PRODUCT#{product_id}"))
        if product is None:
            raise ApplicationError(404, "PRODUCT_NOT_FOUND", "商品が見つかりません。")
        if not product["is_active"]:
            raise ApplicationError(
                409, "PRODUCT_INACTIVE", "無効な商品は登録できません。"
            )
        return product

    def _replay(self, key: dict, fingerprint: str) -> SaleResult | None:
        record = self.repo.get(key)
        if record is None:
            return None
        if record["request_hash"] != fingerprint:
            raise ApplicationError(
                409, "IDEMPOTENCY_CONFLICT", "要求キーを再利用できません。"
            )
        return SaleResult(
            record["response_body"], replayed=True, status=record["response_status"]
        )

    def _request(self, method: str, path: str, body: dict, request_key: str, etag=None):
        key = self.repo.key(f"REQUEST#{self.actor}", f"KEY#{request_key}")
        fingerprint = hashlib.sha256(
            json.dumps(
                [method, path, body, etag],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        return key, fingerprint

    def _now(self, sale_date: str | None = None) -> str:
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("The server clock must be timezone-aware")
        if (
            sale_date is not None
            and date.fromisoformat(sale_date)
            > now.astimezone(ZoneInfo("Asia/Tokyo")).date()
        ):
            raise ApplicationError(
                422, "FUTURE_SALE_DATE", "計上日は日本時間の本日以前にしてください。"
            )
        return now.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _current(self, sale_id: str) -> dict:
        item = self.repo.get(self.repo.key(f"SALE#{sale_id}", "CURRENT"))
        if item is None:
            raise ApplicationError(404, "SALE_NOT_FOUND", "売上が見つかりません。")
        return Sale.model_validate(
            {k: v for k, v in item.items() if k not in {"PK", "SK"}}
        ).model_dump()

    @staticmethod
    def _changeable(before: dict, etag: str):
        if etag != f'"v{before["version"]}"':
            raise ApplicationError(
                412, "VERSION_CONFLICT", "売上を再取得してください。"
            )
        if before["status"] != "confirmed":
            raise ApplicationError(
                409, "SALE_CANCELLED", "取消済みの売上は変更できません。"
            )
        if before["version"] == MAX_VERSION:
            raise ApplicationError(
                409, "VERSION_LIMIT_EXCEEDED", "この売上の版数が上限に達しています。"
            )

    def _commit_change(
        self, before, sale, operation, reason, request, fingerprint, products
    ):
        revision = {
            "sale_id": sale["id"],
            "version": sale["version"],
            "operation": operation,
            "actor_id": self.actor,
            "occurred_at": sale["updated_at"],
            "reason": reason,
            "before": before,
            "after": sale,
        }
        conditional = {"#v": "version"}, {":v": before["version"]}
        current_key = self.repo.key(f"SALE#{sale['id']}", "CURRENT")
        old_day_key = self.repo.key(f"DAY#{before['sale_date']}", f"SALE#{sale['id']}")
        new_day_key = self.repo.key(f"DAY#{sale['sale_date']}", f"SALE#{sale['id']}")
        writes = [
            Write("put", {**current_key, **sale}, "#v = :v", *conditional),
            Write(
                "put",
                {
                    **self.repo.key(
                        f"SALE#{sale['id']}", f"REV#{sale['version']:010d}"
                    ),
                    **revision,
                },
                "attribute_not_exists(PK)",
            ),
            Write(
                "put",
                {
                    **request,
                    "request_hash": fingerprint,
                    "response_status": 200,
                    "response_body": sale,
                    "response_etag": f'"v{sale["version"]}"',
                },
                "attribute_not_exists(PK)",
            ),
        ]
        if before["sale_date"] != sale["sale_date"]:
            writes.extend(
                [
                    Write("delete", old_day_key, "#v = :v", *conditional),
                    Write("put", {**new_day_key, **sale}, "attribute_not_exists(PK)"),
                ]
            )
        else:
            writes.append(
                Write("put", {**new_day_key, **sale}, "#v = :v", *conditional)
            )
        writes.extend(
            Write(
                "check",
                self.repo.key("PRODUCTS", f"PRODUCT#{product_id}"),
                "#v = :v AND #active = :active",
                {"#v": "version", "#active": "is_active"},
                {":v": product["version"], ":active": True},
            )
            for product_id, product in products.items()
        )
        try:
            self.repo.transact(writes)
        except StorageConflict:
            if replay := self._replay(request, fingerprint):
                return replay
            if self._current(sale["id"])["version"] != before["version"]:
                raise ApplicationError(
                    412, "VERSION_CONFLICT", "売上を再取得してください。"
                ) from None
            for product_id, old in products.items():
                if self._product(product_id)["version"] != old["version"]:
                    raise ApplicationError(
                        409,
                        "PRODUCT_CHANGED",
                        "商品が変更されています。再確認してください。",
                    ) from None
            raise
        return SaleResult(sale, status=200)

    def patch(
        self, sale_id: str, body: SalePatch, request_key: str, etag: str
    ) -> SaleResult:
        request, fingerprint = self._request(
            "PATCH", f"/sales/{sale_id}", body.model_dump(), request_key, etag
        )
        if replay := self._replay(request, fingerprint):
            return replay
        before = self._current(sale_id)
        self._changeable(before, etag)
        timestamp = self._now(body.sale_date)
        amounts, total = calculate_amounts(body)
        old_lines = {line["line_id"]: line for line in before["lines"]}
        seen, lines, products = set(), [], {}
        for index, value in enumerate(body.lines):
            if value.line_id is not None:
                if value.line_id not in old_lines or value.line_id in seen:
                    raise ApplicationError(
                        422, "VALIDATION_ERROR", "明細IDを確認してください。"
                    )
                seen.add(value.line_id)
            old = old_lines.get(value.line_id)
            preserve = (
                old is not None
                and old["product_id"] == value.product_id
                and not value.refresh_product_snapshot
            )
            if preserve:
                code, name = old["product_code"], old["product_name"]
            else:
                if value.product_id not in products:
                    products[value.product_id] = self._product(value.product_id)
                product = products[value.product_id]
                code, name = product["code"], product["name"]
            lines.append(
                {
                    "line_id": value.line_id or str(uuid4()),
                    "line_no": index + 1,
                    "product_id": value.product_id,
                    "product_code": code,
                    "product_name": name,
                    "unit_price_yen": value.unit_price_yen,
                    "quantity": value.quantity,
                    "line_amount_yen": amounts[index],
                }
            )
        sale = Sale.model_validate(
            {
                **before,
                "sale_date": body.sale_date,
                "lines": lines,
                "total_amount_yen": total,
                "version": before["version"] + 1,
                "updated_at": timestamp,
            }
        ).model_dump()
        return self._commit_change(
            before, sale, "corrected", body.reason, request, fingerprint, products
        )

    def cancel(
        self, sale_id: str, body: Cancellation, request_key: str, etag: str
    ) -> SaleResult:
        request, fingerprint = self._request(
            "POST", f"/sales/{sale_id}/cancel", body.model_dump(), request_key, etag
        )
        if replay := self._replay(request, fingerprint):
            return replay
        before = self._current(sale_id)
        self._changeable(before, etag)
        sale = {
            **before,
            "status": "cancelled",
            "version": before["version"] + 1,
            "updated_at": self._now(),
        }
        return self._commit_change(
            before, sale, "cancelled", body.reason, request, fingerprint, {}
        )

    def create(self, body: SaleCreate, request_key: str) -> SaleResult:
        request = self.repo.key(f"REQUEST#{self.actor}", f"KEY#{request_key}")
        fingerprint = hashlib.sha256(
            json.dumps(
                ["POST", "/sales", body.model_dump(), None],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        # A committed response survives subsequent product edits or disabling.
        if replay := self._replay(request, fingerprint):
            return replay
        now = self.clock()
        if now.tzinfo is None:
            raise ValueError("The server clock must be timezone-aware")
        if (
            date.fromisoformat(body.sale_date)
            > now.astimezone(ZoneInfo("Asia/Tokyo")).date()
        ):
            raise ApplicationError(
                422, "FUTURE_SALE_DATE", "計上日は日本時間の本日以前にしてください。"
            )
        amounts, total = calculate_amounts(body)
        products = {}
        for line in body.lines:
            if line.product_id not in products:
                products[line.product_id] = self._product(line.product_id)
        sale_id = str(uuid4())
        timestamp = now.astimezone(UTC).isoformat().replace("+00:00", "Z")
        sale = Sale.model_validate(
            {
                "id": sale_id,
                "sale_date": body.sale_date,
                "currency": "JPY",
                "status": "confirmed",
                "version": 1,
                "total_amount_yen": total,
                "created_at": timestamp,
                "updated_at": timestamp,
                "lines": [
                    {
                        **line.model_dump(),
                        "line_id": str(uuid4()),
                        "line_no": index + 1,
                        "product_code": products[line.product_id]["code"],
                        "product_name": products[line.product_id]["name"],
                        "line_amount_yen": amounts[index],
                    }
                    for index, line in enumerate(body.lines)
                ],
            }
        ).model_dump()
        revision = {
            "sale_id": sale_id,
            "version": 1,
            "operation": "created",
            "actor_id": self.actor,
            "occurred_at": timestamp,
            "reason": None,
            "before": None,
            "after": sale,
        }
        items = [
            {**self.repo.key(f"SALE#{sale_id}", "CURRENT"), **sale},
            {**self.repo.key(f"SALE#{sale_id}", "REV#0000000001"), **revision},
            {**self.repo.key(f"DAY#{body.sale_date}", f"SALE#{sale_id}"), **sale},
            {
                **request,
                "request_hash": fingerprint,
                "response_status": 201,
                "response_body": sale,
                "response_etag": '"v1"',
            },
        ]
        writes = [Write("put", item, "attribute_not_exists(PK)") for item in items]
        writes.extend(
            Write(
                "check",
                self.repo.key("PRODUCTS", f"PRODUCT#{product_id}"),
                "#v = :v AND #active = :active",
                {"#v": "version", "#active": "is_active"},
                {":v": product["version"], ":active": True},
            )
            for product_id, product in products.items()
        )
        try:
            self.repo.transact(writes)
        except StorageConflict:
            if replay := self._replay(request, fingerprint):
                return replay
            for product_id, before in products.items():
                current = self._product(product_id)
                if current["version"] != before["version"]:
                    raise ApplicationError(
                        409,
                        "PRODUCT_CHANGED",
                        "商品が変更されています。再確認してください。",
                    ) from None
            # A transient transaction conflict has no committed business result.
            raise
        return SaleResult(sale)
