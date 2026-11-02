"""Sale registration: server-calculated snapshots and atomic first-response storage."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sales_manager_api.errors import ApplicationError
from sales_manager_api.repository import DynamoRepository, StorageConflict, Write
from sales_manager_api.sale_models import MAX_AMOUNT, Sale, SaleCreate


@dataclass(frozen=True)
class SaleResult:
    body: dict
    replayed: bool = False


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
        return SaleResult(record["response_body"], replayed=True)

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
