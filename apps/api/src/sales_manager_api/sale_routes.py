"""Local/test-only sale registration, period search and current sale detail."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.responses import JSONResponse

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.cursors import SaleCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_routes import single_header, uuid_text
from sales_manager_api.repository import DynamoRepository
from sales_manager_api.sale_models import SaleCreate
from sales_manager_api.sale_queries import SaleReader, SaleSearch
from sales_manager_api.sales import SaleService

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
    return JSONResponse(
        result.body,
        status_code=201,
        headers={"ETag": '"v1"', "Idempotency-Replayed": str(result.replayed).lower()},
    )
