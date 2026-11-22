"""Strongly consistent, store-scoped chronological sale revision reads."""

import re

from sales_manager_api.cursors import RevisionCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.repository import DynamoRepository
from sales_manager_api.sale_models import Revision, RevisionPage

REVISION_QUERY_BUDGET = 100


class RevisionReader:
    def __init__(self, repo: DynamoRepository, cursors: RevisionCursors):
        self.repo, self.cursors = repo, cursors

    def list(self, sale_id: str, query) -> dict:
        if set(query) - {"limit", "cursor"} or any(
            len(query.getlist(k)) != 1 for k in query
        ):
            raise ApplicationError(
                422, "VALIDATION_ERROR", "履歴の検索条件を確認してください。"
            )
        limit = query.get("limit", "50")
        if not re.fullmatch(r"[1-9][0-9]{0,2}", limit) or not 1 <= int(limit) <= 100:
            raise ApplicationError(
                422, "VALIDATION_ERROR", "limitは1〜100で指定してください。"
            )
        limit = int(limit)
        if self.repo.get(self.repo.key(f"SALE#{sale_id}", "CURRENT")) is None:
            raise ApplicationError(404, "SALE_NOT_FOUND", "売上が見つかりません。")
        scope = {
            "store": self.repo.prefix,
            "resource": "sale_revisions",
            "sale_id": sale_id,
            "limit": limit,
            "order": "version_asc",
        }
        token = query.get("cursor")
        key = self.cursors.decode(token, scope) if token is not None else None
        rows = []
        for _ in range(REVISION_QUERY_BUDGET):
            page = self.repo.query_page(
                f"SALE#{sale_id}", "REV#", limit=limit - len(rows), last_key=key
            )
            rows.extend(
                Revision.model_validate(
                    {k: v for k, v in item.items() if k not in {"PK", "SK"}}
                )
                for item in page.items
            )
            key = page.last_key
            if key is None or len(rows) == limit:
                return RevisionPage(
                    items=rows,
                    next_cursor=self.cursors.encode(scope, key) if key else None,
                ).model_dump()
        raise ApplicationError(
            503, "QUERY_BUDGET_EXCEEDED", "履歴の検索条件を見直してください。"
        )
