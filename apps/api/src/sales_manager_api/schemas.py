"""Shared response shapes corresponding to the canonical OpenAPI YAML."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HealthResponse(ApiModel):
    status: Literal["ok"] = "ok"


class ErrorDetail(ApiModel):
    path: str
    code: str
    message: str


class ErrorBody(ApiModel):
    code: str
    message: str
    request_id: UUID
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(ApiModel):
    error: ErrorBody
