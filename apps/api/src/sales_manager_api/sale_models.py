"""Strict sale inputs, current snapshots and revisions; integer tax-inclusive yen."""

import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from sales_manager_api.product_models import MAX_VERSION, Code, Name, Price
from sales_manager_api.schemas import ApiModel

MAX_AMOUNT = 9_999_999_999
Quantity = Annotated[int, Field(ge=1, le=9_999)]
Amount = Annotated[int, Field(ge=0, le=MAX_AMOUNT)]
Reason = Annotated[str, Field(min_length=1, max_length=500, pattern=r"\S")]


class SaleCreateLine(ApiModel):
    product_id: str = Field(json_schema_extra={"format": "uuid"})
    unit_price_yen: Price
    quantity: Quantity

    @field_validator("product_id")
    @classmethod
    def canonical_uuid(cls, value: str) -> str:
        parsed = UUID(value)
        if str(parsed) != value.lower():
            raise ValueError("A canonical UUID is required")
        return str(parsed)


class SaleCreate(ApiModel):
    sale_date: str = Field(json_schema_extra={"format": "date"})
    lines: list[SaleCreateLine] = Field(min_length=1, max_length=50)

    @field_validator("sale_date")
    @classmethod
    def calendar_date(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("A YYYY-MM-DD date is required")
        date.fromisoformat(value)
        return value


class SaleLine(SaleCreateLine):
    line_id: str = Field(json_schema_extra={"format": "uuid"})
    line_no: int = Field(ge=1, le=50)
    product_code: Code
    product_name: Name
    line_amount_yen: Amount


class SalePatchLine(SaleCreateLine):
    line_id: str | None = Field(default=None, json_schema_extra={"format": "uuid"})
    refresh_product_snapshot: bool = False

    @field_validator("line_id")
    @classmethod
    def supplied_line_uuid(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("An explicit null line ID is not allowed")
        return cls.canonical_uuid(value)


class SalePatch(SaleCreate):
    lines: list[SalePatchLine] = Field(min_length=1, max_length=50)
    reason: Reason


class Cancellation(ApiModel):
    reason: Reason


class SaleHead(ApiModel):
    id: str = Field(json_schema_extra={"format": "uuid"})
    sale_date: str = Field(json_schema_extra={"format": "date"})
    currency: Literal["JPY"]
    status: Literal["confirmed", "cancelled"]
    version: int = Field(ge=1, le=MAX_VERSION)
    total_amount_yen: Amount
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    updated_at: str = Field(json_schema_extra={"format": "date-time"})


class Sale(SaleHead):
    lines: list[SaleLine] = Field(min_length=1, max_length=50)


class SaleSummary(SaleHead):
    matched_amount_yen: Amount
    matched_quantity: int = Field(ge=1)


class SalePage(ApiModel):
    items: list[SaleSummary] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=4096)


class Revision(ApiModel):
    sale_id: str = Field(json_schema_extra={"format": "uuid"})
    version: int = Field(ge=1, le=MAX_VERSION)
    operation: Literal["created", "corrected", "cancelled"]
    actor_id: str = Field(min_length=1, max_length=128)
    occurred_at: str = Field(json_schema_extra={"format": "date-time"})
    reason: str | None = Field(max_length=500)
    before: Sale | None
    after: Sale


class RevisionPage(ApiModel):
    items: list[Revision] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=4096)
