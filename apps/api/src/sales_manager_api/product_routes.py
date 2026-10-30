"""Local product HTTP routes; authentication is introduced in Day 19."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.cursors import ProductCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_models import (
    MAX_VERSION,
    ProductCreate,
    ProductPage,
    ProductPatch,
)
from sales_manager_api.products import ProductResult, ProductService
from sales_manager_api.repository import DynamoRepository

router = APIRouter(prefix="/products")


def product_service(request: Request):
    settings = request.app.state.settings
    if settings.app_env not in {"local", "test"}:
        raise ApplicationError(
            503, "TEMPORARILY_UNAVAILABLE", "商品APIはローカル開発でのみ利用できます。"
        )
    client = dynamodb_client(settings)
    try:
        yield ProductService(
            DynamoRepository(client, settings.dynamodb_table, settings.store_id),
            ProductCursors(request.app.state.product_cursor_key),
        )
    finally:
        client.close()


Service = Annotated[ProductService, Depends(product_service)]


def uuid_text(value: str, *, header: bool = False) -> str:
    try:
        parsed = UUID(value)
        if str(parsed) != value.lower():
            raise ValueError
        return str(parsed)
    except ValueError:
        raise ApplicationError(
            400 if header else 422,
            "INVALID_HEADER" if header else "VALIDATION_ERROR",
            "UUIDの形式を確認してください。",
        ) from None


def single_header(request: Request, name: str) -> str:
    values = request.headers.getlist(name)
    if not values:
        if name == "If-Match":
            raise ApplicationError(
                428, "PRECONDITION_REQUIRED", "If-Matchを指定してください。"
            )
        raise ApplicationError(
            400, "INVALID_HEADER", "Idempotency-Keyを指定してください。"
        )
    if len(values) != 1:
        raise ApplicationError(
            400, "INVALID_HEADER", "同じヘッダーを複数指定できません。"
        )
    return values[0]


def result_response(result: ProductResult):
    return JSONResponse(
        result.body,
        status_code=result.status,
        headers={
            "ETag": result.etag,
            "Idempotency-Replayed": str(result.replayed).lower(),
        },
    )


@router.get("", operation_id="listProducts")
def list_products(request: Request, service: Service):
    query = request.query_params
    if set(query) - {"limit", "cursor", "is_active"} or any(
        len(query.getlist(k)) != 1 for k in query
    ):
        raise ApplicationError(422, "VALIDATION_ERROR", "検索条件を確認してください。")
    limit = query.get("limit", "50")
    if not re.fullmatch(r"[1-9][0-9]{0,2}", limit) or not 1 <= int(limit) <= 100:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "limitは1〜100で指定してください。"
        )
    active = query.get("is_active")
    if active not in {None, "true", "false"}:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "is_activeはtrue/falseで指定してください。"
        )
    return ProductPage.model_validate(
        service.list(
            int(limit),
            None if active is None else active == "true",
            query.get("cursor"),
        )
    )


@router.post("", operation_id="createProduct", status_code=201)
def create_product(request: Request, body: ProductCreate, service: Service):
    key = uuid_text(single_header(request, "Idempotency-Key"), header=True)
    return result_response(service.create(body, key))


@router.get("/{product_id}", operation_id="getProduct")
def get_product(product_id: str, service: Service):
    product = service.get(uuid_text(product_id))
    return JSONResponse(product, headers={"ETag": f'"v{product["version"]}"'})


@router.patch("/{product_id}", operation_id="patchProduct")
def patch_product(
    product_id: str, request: Request, body: ProductPatch, service: Service
):
    product_id = uuid_text(product_id)
    key = uuid_text(single_header(request, "Idempotency-Key"), header=True)
    etag = single_header(request, "If-Match")
    if not re.fullmatch(r'"v[1-9][0-9]{0,9}"', etag) or int(etag[2:-1]) > MAX_VERSION:
        raise ApplicationError(
            400, "INVALID_HEADER", "If-Matchの形式を確認してください。"
        )
    return result_response(service.patch(product_id, body, key, etag))
