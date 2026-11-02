from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.cursors import ProductCursors
from sales_manager_api.product_routes import product_service
from sales_manager_api.products import ProductService
from sales_manager_api.repository import DynamoRepository, StorageConflict, StorageError
from sales_manager_api.sale_models import SaleCreate
from sales_manager_api.sale_routes import sale_service
from sales_manager_api.sales import SaleService
from sales_manager_api.settings import Settings

PRODUCT_ID = "00000000-0000-4000-8000-000000000001"
BODY = {
    "sale_date": "2026-11-01",
    "lines": [{"product_id": PRODUCT_ID, "unit_price_yen": 550, "quantity": 2}],
}


class SaleMemoryRepository(DynamoRepository):
    """Atomic test double; actual DynamoDB semantics are checked separately."""

    def __init__(self, store="demo"):
        super().__init__(None, "sales-manager-test-unit", store)
        self.items, self.writes = {}, []
        self.before_transaction = None

    def get(self, key):
        return deepcopy(self.items.get((key["PK"], key["SK"])))

    def transact(self, writes):
        self.writes = writes
        if self.before_transaction:
            callback, self.before_transaction = self.before_transaction, None
            callback()
        for write in writes:
            current = self.get(write.item)
            if write.condition == "attribute_not_exists(PK)":
                valid = current is None
            else:
                valid = current is not None and current["version"] == write.values[":v"]
                if write.kind == "check":
                    valid = valid and current["is_active"]
            if not valid:
                raise StorageConflict("test conditional failure")
        for write in writes:
            if write.kind == "put":
                self.items[(write.item["PK"], write.item["SK"])] = deepcopy(write.item)


def put_product(repo, product_id=PRODUCT_ID, **changes):
    key = repo.key("PRODUCTS", f"PRODUCT#{product_id}")
    item = {
        **key,
        "id": product_id,
        "code": "COFFEE",
        "name": "コーヒー",
        "default_unit_price_yen": 600,
        "is_active": True,
        "version": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        **changes,
    }
    repo.items[(key["PK"], key["SK"])] = item


@pytest.fixture
def sales_api():
    repo = SaleMemoryRepository()
    put_product(repo)
    service = SaleService(repo, clock=lambda: datetime(2026, 11, 2, tzinfo=UTC))
    app = create_app(Settings(APP_ENV="test"))
    app.dependency_overrides[sale_service] = lambda: service
    app.dependency_overrides[product_service] = lambda: ProductService(
        repo, ProductCursors(b"test-only-key-not-a-real-secret!!")
    )
    with TestClient(app) as client:
        yield client, repo, service


def post(client, body=None, key=None):
    return client.post(
        "/sales",
        json=BODY if body is None else body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


def test_create_matches_yaml_and_saves_all_four_records(sales_api, contract_validator):
    client, repo, _ = sales_api
    key = str(uuid4())
    response = post(client, key=key)
    assert response.status_code == 201, response.text
    sale = response.json()
    contract_validator("Sale", sale)
    assert response.headers["etag"] == '"v1"'
    assert response.headers["idempotency-replayed"] == "false"
    assert sale["total_amount_yen"] == 1100
    assert sale["status"] == "confirmed" and sale["currency"] == "JPY"
    assert sale["lines"][0]["product_name"] == "コーヒー"
    assert sale["lines"][0]["unit_price_yen"] == 550  # Actual, not master price 600.
    current = repo.get(repo.key(f"SALE#{sale['id']}", "CURRENT"))
    day = repo.get(repo.key("DAY#2026-11-01", f"SALE#{sale['id']}"))
    assert {k: v for k, v in current.items() if k not in {"PK", "SK"}} == sale
    assert {k: v for k, v in day.items() if k not in {"PK", "SK"}} == sale
    revision = repo.get(repo.key(f"SALE#{sale['id']}", "REV#0000000001"))
    contract_validator(
        "Revision", {k: v for k, v in revision.items() if k not in {"PK", "SK"}}
    )
    assert revision["before"] is None and revision["reason"] is None
    assert revision["operation"] == "created" and revision["actor_id"] == "local-admin"
    assert revision["after"] == sale
    record = repo.get(repo.key("REQUEST#local-admin", f"KEY#{key}"))
    assert record["response_body"] == sale and record["response_status"] == 201
    assert len(repo.writes) == 5 and len(repo.items) == 5


@pytest.mark.parametrize("field", ["unit_price_yen", "quantity"])
@pytest.mark.parametrize("value", [True, False, 1.0, "1", -1, None])
def test_strict_line_numbers_no_write(sales_api, field, value):
    client, repo, _ = sales_api
    body = deepcopy(BODY)
    body["lines"][0][field] = value
    before = deepcopy(repo.items)
    assert post(client, body).status_code == 422
    assert repo.items == before and not repo.writes


@pytest.mark.parametrize(
    "field,value", [("quantity", 0), ("quantity", 10000), ("unit_price_yen", 10000000)]
)
def test_input_bounds(sales_api, field, value):
    body = deepcopy(BODY)
    body["lines"][0][field] = value
    assert post(sales_api[0], body).status_code == 422


@pytest.mark.parametrize(
    "day",
    [
        "2026-02-29",
        "2026-02-30",
        "2026-1-01",
        "20261101",
        "2026-W44-7",
        "2026-11-01T00:00:00Z",
        "2026-11-01\n",
        True,
        None,
    ],
)
def test_invalid_calendar_dates(sales_api, day):
    assert post(sales_api[0], {**BODY, "sale_date": day}).status_code == 422


@pytest.mark.parametrize("count", [0, 51])
def test_line_count_bounds(sales_api, count):
    assert (
        post(sales_api[0], {**BODY, "lines": BODY["lines"] * count}).status_code == 422
    )


@pytest.mark.parametrize(
    "field", ["total_amount_yen", "actor_id", "store_id", "status", "version", "id"]
)
def test_server_fields_are_not_accepted(sales_api, field):
    assert post(sales_api[0], {**BODY, field: "untrusted"}).status_code == 422


@pytest.mark.parametrize(
    "field", ["line_id", "line_amount_yen", "product_name", "refresh_product_snapshot"]
)
def test_client_snapshots_and_unknown_line_fields_rejected(sales_api, field):
    body = deepcopy(BODY)
    body["lines"][0][field] = "untrusted"
    assert post(sales_api[0], body).status_code == 422


@pytest.mark.parametrize(
    "product_id", ["not-a-uuid", "00000000000040008000000000000001", 1, None]
)
def test_malformed_product_id(sales_api, product_id):
    body = deepcopy(BODY)
    body["lines"][0]["product_id"] = product_id
    assert post(sales_api[0], body).status_code == 422


def test_amount_limit_exact_and_one_yen_over(sales_api):
    client, repo, _ = sales_api
    lines = [
        {"product_id": PRODUCT_ID, "unit_price_yen": 1000000, "quantity": 9999},
        {"product_id": PRODUCT_ID, "unit_price_yen": 999999, "quantity": 1},
    ]
    response = post(client, {**BODY, "lines": lines})
    assert (
        response.status_code == 201
        and response.json()["total_amount_yen"] == 9999999999
    )
    before = deepcopy(repo.items)
    lines[1]["unit_price_yen"] += 1
    over = post(client, {**BODY, "lines": lines})
    assert (
        over.status_code == 422
        and over.json()["error"]["code"] == "AMOUNT_LIMIT_EXCEEDED"
    )
    assert repo.items == before


def test_fifty_repeated_lines_are_independent_and_check_product_once(sales_api):
    response = post(
        sales_api[0],
        {
            **BODY,
            "lines": [{**BODY["lines"][0], "unit_price_yen": 0, "quantity": 9999}] * 50,
        },
    )
    assert response.status_code == 201 and response.json()["total_amount_yen"] == 0
    lines = response.json()["lines"]
    assert [line["line_no"] for line in lines] == list(range(1, 51))
    assert len({line["line_id"] for line in lines}) == 50
    assert len(sales_api[1].writes) == 5


@pytest.mark.parametrize(
    "instant,expected",
    [("2026-11-01T14:59:59+00:00", 422), ("2026-11-01T15:00:00+00:00", 201)],
)
def test_jst_midnight_not_utc_or_machine_date(sales_api, instant, expected):
    client, _, service = sales_api
    service.clock = lambda: datetime.fromisoformat(instant)
    response = post(client, {**BODY, "sale_date": "2026-11-02"})
    assert response.status_code == expected
    if expected == 422:
        assert response.json()["error"]["code"] == "FUTURE_SALE_DATE"
    else:
        assert response.json()["created_at"] == "2026-11-01T15:00:00Z"


def test_past_leap_day_is_allowed(sales_api):
    assert post(sales_api[0], {**BODY, "sale_date": "2024-02-29"}).status_code == 201


@pytest.mark.parametrize("inactive", [False, True])
def test_missing_or_inactive_product_no_partial_save(sales_api, inactive):
    client, repo, _ = sales_api
    missing = str(uuid4())
    if inactive:
        put_product(repo, missing, code="DISABLED", is_active=False)
    body = {
        **BODY,
        "lines": BODY["lines"] + [{**BODY["lines"][0], "product_id": missing}],
    }
    before = deepcopy(repo.items)
    response = post(client, body)
    assert response.status_code == (409 if inactive else 404)
    assert response.json()["error"]["code"] == (
        "PRODUCT_INACTIVE" if inactive else "PRODUCT_NOT_FOUND"
    )
    assert repo.items == before


def test_replay_after_product_changes_and_cross_resource_key_conflict(sales_api):
    client, repo, _ = sales_api
    key = str(uuid4())
    first = post(client, key=key)
    put_product(
        repo, name="変更後", default_unit_price_yen=999, version=2, is_active=False
    )
    before = deepcopy(repo.items)
    replay = post(client, key=key)
    assert replay.status_code == 201 and replay.json() == first.json()
    assert (
        replay.headers["idempotency-replayed"] == "true"
        and replay.headers["etag"] == '"v1"'
    )
    assert repo.items == before
    conflict = post(client, {**BODY, "sale_date": "2026-10-31"}, key)
    assert (
        conflict.status_code == 409
        and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    )
    other_resource = client.post(
        "/products",
        json={"code": "OTHER", "name": "別商品", "default_unit_price_yen": 1},
        headers={"Idempotency-Key": key},
    )
    assert other_resource.status_code == 409


@pytest.mark.parametrize(
    "change,code,status",
    [
        ({"is_active": False, "version": 2}, "PRODUCT_INACTIVE", 409),
        ({"name": "改名", "version": 2}, "PRODUCT_CHANGED", 409),
        (None, "PRODUCT_NOT_FOUND", 404),
    ],
)
def test_product_race_rejects_entire_transaction(sales_api, change, code, status):
    client, repo, _ = sales_api

    def concurrent_change():
        if change is None:
            repo.items.clear()
        else:
            put_product(repo, **change)

    repo.before_transaction = concurrent_change
    response = post(client)
    assert response.status_code == status and response.json()["error"]["code"] == code
    assert not any(
        "#SALE#" in pk or "#DAY#" in pk or "#REQUEST#" in pk for pk, _ in repo.items
    )


def test_same_key_race_returns_first_commit_and_unknown_conflict_is_retryable(
    sales_api,
):
    client, repo, service = sales_api
    key = str(uuid4())
    committed = []
    repo.before_transaction = lambda: committed.append(
        service.create(SaleCreate.model_validate(BODY), key).body
    )
    response = post(client, key=key)
    assert response.status_code == 201 and response.json() == committed[0]
    assert response.headers["idempotency-replayed"] == "true" and len(repo.items) == 5
    with patch.object(
        repo, "transact", side_effect=StorageConflict("internal conflict")
    ):
        response = post(client)
        assert response.status_code == 503 and response.headers["retry-after"] == "1"
        assert "internal conflict" not in response.text


def test_store_and_actor_isolate_idempotency_records(sales_api):
    _, repo, service = sales_api
    key = str(uuid4())
    body = SaleCreate.model_validate(BODY)
    first = service.create(body, key)
    other_actor = SaleService(repo, actor="another-admin", clock=service.clock).create(
        body, key
    )
    other_repo = SaleMemoryRepository("other-store")
    put_product(other_repo)
    other_store = SaleService(other_repo, clock=service.clock).create(body, key)
    assert len({r.body["id"] for r in [first, other_actor, other_store]}) == 3


def test_header_json_errors_and_storage_redaction(sales_api, contract_validator):
    client, repo, _ = sales_api
    for headers in [
        {},
        {"Idempotency-Key": "bad"},
        [("Idempotency-Key", str(uuid4())), ("Idempotency-Key", str(uuid4()))],
    ]:
        response = client.post("/sales", json=BODY, headers=headers)
        assert response.status_code == 400
        contract_validator("Error", response.json())
        assert (
            response.json()["error"]["request_id"] == response.headers["x-request-id"]
        )
    assert (
        client.post(
            "/sales", content="{", headers={"Content-Type": "application/json"}
        ).status_code
        == 400
    )
    with patch.object(
        repo, "transact", side_effect=StorageError("private SDK response")
    ):
        response = post(client)
        assert (
            response.status_code == 503 and "private SDK response" not in response.text
        )
        assert response.headers["retry-after"] == "1"


def test_aws_guard_runs_before_sdk_creation_and_read_api_not_yet_implemented():
    with patch("sales_manager_api.sale_routes.dynamodb_client") as sdk:
        with TestClient(
            create_app(Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1"))
        ) as client:
            response = post(client)
            assert (
                response.status_code == 503 and response.headers["retry-after"] == "1"
            )
            assert client.get("/health").status_code == 200
            assert client.get("/sales").status_code == 405
            assert client.get(f"/sales/{uuid4()}").status_code == 404
        sdk.assert_not_called()
