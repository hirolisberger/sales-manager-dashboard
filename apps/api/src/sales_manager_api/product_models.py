"""Strict product request/response shapes matching the canonical API YAML."""

import re
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from sales_manager_api.schemas import ApiModel

MAX_VERSION = 2_147_483_647
Price = Annotated[int, Field(ge=0, le=9_999_999)]
Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
Code = Annotated[str, Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,31}$")]


class ProductCreate(ApiModel):
    code: Code
    name: Name
    default_unit_price_yen: Price

    @field_validator("code")
    @classmethod
    def complete_code(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{0,31}", value):
            raise ValueError("Invalid product code")
        return value


class ProductPatch(ApiModel):
    name: Name | None = None
    default_unit_price_yen: Price | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def provided_fields_are_non_null(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set
        ):
            raise ValueError("At least one non-null update field is required")
        return self


class Product(ProductCreate):
    id: str = Field(json_schema_extra={"format": "uuid"})
    is_active: bool
    version: int = Field(ge=1, le=MAX_VERSION)
    created_at: str = Field(json_schema_extra={"format": "date-time"})
    updated_at: str = Field(json_schema_extra={"format": "date-time"})


class ProductPage(ApiModel):
    items: list[Product] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, max_length=4096)
