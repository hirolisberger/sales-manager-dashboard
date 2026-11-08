"""Strongly consistent sale reads, filtered summaries and date-spanning pagination."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sales_manager_api.cursors import SaleCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.repository import DynamoRepository
from sales_manager_api.sale_models import Sale, SalePage, SaleSummary

QUERY_BUDGET = 1000


@dataclass(frozen=True)
class SaleSearch:
    start: date
    end: date
    product_id: str | None
    status: str
    limit: int

    @classmethod
    def parse(cls, query: Mapping[str, str]):
        try:
            if set(query) - {
                "start_date",
                "end_date",
                "product_id",
                "status",
                "limit",
                "cursor",
            }:
                raise ValueError
            dates = []
            for name in ["start_date", "end_date"]:
                value = query[name]
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                    raise ValueError
                dates.append(date.fromisoformat(value))
            start, end = dates
            if start > end or end == date.max:
                raise ValueError
            limit = query.get("limit", "50")
            if (
                not re.fullmatch(r"[1-9][0-9]{0,2}", limit)
                or not 1 <= int(limit) <= 100
            ):
                raise ValueError
            status = query.get("status", "all")
            if status not in {"all", "confirmed", "cancelled"}:
                raise ValueError
            product = query.get("product_id")
            if product is not None:
                normalized = str(UUID(product))
                if normalized != product.lower():
                    raise ValueError
                product = normalized
        except ValueError, KeyError, TypeError:
            raise ApplicationError(
                422, "VALIDATION_ERROR", "検索条件を確認してください。"
            ) from None
        if (end - start).days + 1 > 366:
            raise ApplicationError(
                422, "PERIOD_TOO_LONG", "期間は366日以内にしてください。"
            )
        return cls(start, end, product, status, int(limit))


class SaleReader:
    def __init__(self, repo: DynamoRepository, cursors: SaleCursors):
        self.repo, self.cursors = repo, cursors

    @staticmethod
    def public(item: dict) -> dict:
        return Sale.model_validate(
            {k: v for k, v in item.items() if k not in {"PK", "SK"}}
        ).model_dump()

    def get(self, sale_id: str) -> dict:
        item = self.repo.get(self.repo.key(f"SALE#{sale_id}", "CURRENT"))
        if item is None:
            raise ApplicationError(404, "SALE_NOT_FOUND", "売上が見つかりません。")
        return self.public(item)

    def scope(self, search: SaleSearch) -> dict:
        return {
            "store": self.repo.prefix,
            "resource": "sales",
            "start_date": search.start.isoformat(),
            "end_date": search.end.isoformat(),
            "product_id": search.product_id,
            "status": search.status,
            "limit": search.limit,
            "order": "sale_date_desc_id_desc",
        }

    def list(self, search: SaleSearch, cursor: str | None = None) -> dict:
        scope = self.scope(search)
        state = (
            self.cursors.decode(cursor, scope)
            if cursor is not None
            else {"day": search.end.isoformat(), "last_key": None}
        )
        day, key = date.fromisoformat(state["day"]), state["last_key"]
        rows, queries = [], 0
        while True:
            if queries >= QUERY_BUDGET:
                raise ApplicationError(
                    503, "QUERY_BUDGET_EXCEEDED", "検索条件を見直してください。"
                )
            page = self.repo.query_page(
                "DAY#" + day.isoformat(),
                "SALE#",
                limit=search.limit - len(rows),
                last_key=key,
                ascending=False,
            )
            queries += 1
            for item in page.items:
                sale = self.public(item)
                if search.status != "all" and sale["status"] != search.status:
                    continue
                lines = [
                    line
                    for line in sale["lines"]
                    if search.product_id is None
                    or line["product_id"] == search.product_id
                ]
                if not lines:
                    continue
                summary = {k: v for k, v in sale.items() if k != "lines"}
                rows.append(
                    SaleSummary.model_validate(
                        {
                            **summary,
                            "matched_amount_yen": sum(
                                line["line_amount_yen"] for line in lines
                            ),
                            "matched_quantity": sum(line["quantity"] for line in lines),
                        }
                    ).model_dump()
                )
            key = page.last_key
            if key is None:
                if day == search.start:
                    return SalePage(items=rows, next_cursor=None).model_dump()
                day -= timedelta(days=1)
            if len(rows) == search.limit:
                return SalePage(
                    items=rows,
                    next_cursor=self.cursors.encode(
                        scope, {"day": day.isoformat(), "last_key": key}
                    ),
                ).model_dump()
