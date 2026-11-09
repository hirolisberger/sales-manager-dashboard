"""Local/test-only sale registration, search, correction, cancellation and history."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.cursors import RevisionCursors, SaleCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_models import MAX_VERSION
from sales_manager_api.product_routes import single_header, uuid_text
from sales_manager_api.repository import DynamoRepository
from sales_manager_api.sale_models import Cancellation, SaleCreate, SalePatch
from sales_manager_api.sale_queries import SaleReader, SaleSearch
from sales_manager_api.sale_revisions import RevisionReader
from sales_manager_api.sales import SaleResult, SaleService

router = APIRouter(prefix="/sales")


def sale_service(request: Request):
    settings = request.app.state.settings
    if settings.app_env not in {"local", "test"}:
        raise ApplicationError(
            503, "TEMPORARILY_UNAVAILABLE", "売上APIはローカル開発でのみ利用できます。"
        )
    client = dynamodb_client(settings)
    try:
        yield SaleService(
            DynamoRepository(client, settings.dynamodb_table, settings.store_id)
        )
    finally:
        client.close()


Service = Annotated[SaleService, Depends(sale_service)]


def sale_reader(request: Request, service: Service):
    return SaleReader(service.repo, SaleCursors(request.app.state.sale_cursor_key))


Reader = Annotated[SaleReader, Depends(sale_reader)]


def revision_reader(request: Request, service: Service):
    return RevisionReader(
        service.repo, RevisionCursors(request.app.state.revision_cursor_key)
    )


Revisions = Annotated[RevisionReader, Depends(revision_reader)]


def change_headers(request: Request) -> tuple[str, str]:
    key = uuid_text(single_header(request, "Idempotency-Key"), header=True)
    etag = single_header(request, "If-Match")
    if not re.fullmatch(r'"v[1-9][0-9]{0,9}"', etag) or int(etag[2:-1]) > MAX_VERSION:
        raise ApplicationError(
            400, "INVALID_HEADER", "If-Matchの形式を確認してください。"
        )
    return key, etag


def sale_response(result: SaleResult):
    return JSONResponse(
        result.body,
        status_code=result.status,
        headers={
            "ETag": f'"v{result.body["version"]}"',
            "Idempotency-Replayed": str(result.replayed).lower(),
        },
    )


@router.get("", operation_id="listSales")
def list_sales(request: Request, reader: Reader):
    query = request.query_params
    if any(len(query.getlist(name)) != 1 for name in query):
        raise ApplicationError(
            422, "VALIDATION_ERROR", "同じ検索条件を複数指定できません。"
        )
    return reader.list(SaleSearch.parse(query), query.get("cursor"))


@router.get("/{sale_id}", operation_id="getSale")
def get_sale(sale_id: str, reader: Reader):
    sale = reader.get(uuid_text(sale_id))
    return JSONResponse(sale, headers={"ETag": f'"v{sale["version"]}"'})


@router.post("", operation_id="createSale", status_code=201)
def create_sale(request: Request, body: SaleCreate, service: Service):
    key = uuid_text(single_header(request, "Idempotency-Key"), header=True)
    result = service.create(body, key)
    return sale_response(result)


@router.patch("/{sale_id}", operation_id="patchSale")
def patch_sale(sale_id: str, request: Request, body: SalePatch, service: Service):
    sale_id = uuid_text(sale_id)
    key, etag = change_headers(request)
    return sale_response(service.patch(sale_id, body, key, etag))


@router.post("/{sale_id}/cancel", operation_id="cancelSale")
def cancel_sale(sale_id: str, request: Request, body: Cancellation, service: Service):
    sale_id = uuid_text(sale_id)
    key, etag = change_headers(request)
    return sale_response(service.cancel(sale_id, body, key, etag))


@router.get("/{sale_id}/revisions", operation_id="listSaleRevisions")
def list_sale_revisions(sale_id: str, request: Request, reader: Revisions):
    return reader.list(uuid_text(sale_id), request.query_params)
