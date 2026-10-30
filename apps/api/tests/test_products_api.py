from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.cursors import ProductCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.product_models import MAX_VERSION
from sales_manager_api.product_routes import product_service
from sales_manager_api.products import ProductService
from sales_manager_api.repository import (
    DynamoRepository,
    Page,
    StorageConflict,
    StorageError,
)
from sales_manager_api.settings import Settings

BODY = {"code": "COFFEE", "name": "コーヒー", "default_unit_price_yen": 550}


class MemoryRepository(DynamoRepository):
    """A test double for service/HTTP tests, not proof of DynamoDB semantics."""

    def __init__(self):
        super().__init__(None, "sales-manager-test-unit", "demo")
        self.items = {}
        self.before_transaction = None

    def get(self, key):
        return deepcopy(self.items.get((key["PK"], key["SK"])))

    def query_page(self, pk, sk_prefix, *, limit=50, last_key=None, ascending=True):
        partition = self.key(pk, sk_prefix)["PK"]
        rows = [
            item
            for (p, s), item in sorted(self.items.items())
            if p == partition
            and s.startswith(sk_prefix)
            and (last_key is None or s > last_key["SK"])
        ]
        selected = rows[:limit]
        return Page(
            deepcopy(selected), self._key(selected[-1]) if len(rows) > limit else None
        )

    def transact(self, writes):
        if self.before_transaction:
            callback, self.before_transaction = self.before_transaction, None
            callback()
        for write in writes:
            current = self.get(write.item)
            if write.condition == "attribute_not_exists(PK)":
                if current is not None:
                    raise StorageConflict("Conditional failure")
            elif current is None or current["version"] != write.values[":v"]:
                raise StorageConflict("Conditional failure")
        for write in writes:
            self.items[(write.item["PK"], write.item["SK"])] = deepcopy(write.item)


@pytest.fixture
def product_api():
    repo = MemoryRepository()
    service = ProductService(
        repo,
        ProductCursors(b"test-only-key-not-a-real-secret!!"),
        clock=lambda: datetime(2026, 10, 30, tzinfo=UTC),
    )
    app = create_app(Settings(APP_ENV="test"))
    app.dependency_overrides[product_service] = lambda: service
    with TestClient(app) as client:
        yield client, repo, service


def create(client, body=None, key=None):
    return client.post(
        "/products",
        json=BODY if body is None else body,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


def patch_product(client, product, body, key=None, etag=None):
    return client.patch(
        f"/products/{product['id']}",
        json=body,
        headers={
            "Idempotency-Key": key or str(uuid4()),
            "If-Match": etag or f'"v{product["version"]}"',
        },
    )


def assert_error(response, status, code, validate):
    assert response.status_code == status, response.text
    validate("Error", response.json())
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_product_lifecycle_matches_yaml_and_preserves_code_and_created_at(
    product_api, contract_validator
):
    client, repo, _ = product_api
    created = create(client)
    assert created.status_code == 201
    contract_validator("Product", created.json())
    assert created.headers["etag"] == '"v1"'
    assert created.headers["idempotency-replayed"] == "false"
    original = created.json()
    detail = client.get(f"/products/{original['id']}")
    assert detail.json() == original and detail.headers["etag"] == '"v1"'
    edited = patch_product(
        client, original, {"name": "更新後", "default_unit_price_yen": 600}
    )
    assert edited.status_code == 200
    contract_validator("Product", edited.json())
    assert edited.json()["version"] == 2 and edited.headers["etag"] == '"v2"'
    assert edited.json()["code"] == "COFFEE"
    assert edited.json()["created_at"] == original["created_at"]
    disabled = patch_product(client, edited.json(), {"is_active": False})
    assert disabled.status_code == 200 and disabled.json()["is_active"] is False
    page = client.get("/products?is_active=false")
    contract_validator("ProductPage", page.json())
    assert [p["id"] for p in page.json()["items"]] == [original["id"]]
    assert client.get("/products?is_active=true").json()["items"] == []
    assert len(client.get("/products").json()["items"]) == 1
    assert create(client).status_code == 409  # Reservation survives disabling.
    assert client.delete(f"/products/{original['id']}").status_code == 405
    assert client.get(f"/products/{original['id']}").json()["version"] == 3
    reactivated = patch_product(client, disabled.json(), {"is_active": True})
    assert reactivated.status_code == 200 and reactivated.json()["is_active"] is True
    assert (
        repo.get(repo.key("PRODUCT_CODES", "CODE#COFFEE"))["product_id"]
        == original["id"]
    )


def test_first_create_and_patch_responses_survive_later_updates(
    product_api, contract_validator
):
    client, _, _ = product_api
    create_key, patch_key = str(uuid4()), str(uuid4())
    original = create(client, key=create_key)
    first_patch = patch_product(
        client, original.json(), {"is_active": False}, key=patch_key
    )
    later = patch_product(client, first_patch.json(), {"name": "後の変更"})
    assert later.status_code == 200
    replay_create = create(client, key=create_key)
    assert replay_create.status_code == 201 and replay_create.json() == original.json()
    assert (
        replay_create.headers["etag"] == '"v1"'
        and replay_create.headers["idempotency-replayed"] == "true"
    )
    replay_patch = patch_product(
        client, original.json(), {"is_active": False}, key=patch_key
    )
    assert (
        replay_patch.json() == first_patch.json()
        and replay_patch.headers["etag"] == '"v2"'
    )
    assert replay_patch.headers["idempotency-replayed"] == "true"
    assert client.get(f"/products/{original.json()['id']}").json() == later.json()
    assert_error(
        create(client, {**BODY, "name": "別内容"}, create_key),
        409,
        "IDEMPOTENCY_CONFLICT",
        contract_validator,
    )
    assert_error(
        patch_product(client, first_patch.json(), {"is_active": False}, key=patch_key),
        409,
        "IDEMPOTENCY_CONFLICT",
        contract_validator,
    )


def test_not_found_version_conflict_and_version_limit(product_api, contract_validator):
    client, repo, _ = product_api
    assert_error(
        client.get(f"/products/{uuid4()}"), 404, "PRODUCT_NOT_FOUND", contract_validator
    )
    assert_error(
        client.get("/products/not-a-uuid"), 422, "VALIDATION_ERROR", contract_validator
    )
    product = create(client).json()
    assert_error(
        patch_product(client, product, {"name": "old"}, etag='"v2"'),
        412,
        "VERSION_CONFLICT",
        contract_validator,
    )
    item_key = repo.key("PRODUCTS", f"PRODUCT#{product['id']}")
    repo.items[(item_key["PK"], item_key["SK"])]["version"] = MAX_VERSION
    assert_error(
        patch_product(client, {**product, "version": MAX_VERSION}, {"name": "max"}),
        409,
        "VERSION_LIMIT_EXCEEDED",
        contract_validator,
    )


@pytest.mark.parametrize(
    "headers,status,code",
    [
        ({}, 400, "INVALID_HEADER"),
        ({"Idempotency-Key": "bad"}, 400, "INVALID_HEADER"),
        ({"Idempotency-Key": str(uuid4())}, 428, "PRECONDITION_REQUIRED"),
        ({"Idempotency-Key": str(uuid4()), "If-Match": "*"}, 400, "INVALID_HEADER"),
        (
            {"Idempotency-Key": str(uuid4()), "If-Match": 'W/"v1"'},
            400,
            "INVALID_HEADER",
        ),
        (
            {"Idempotency-Key": str(uuid4()), "If-Match": '"v2147483648"'},
            400,
            "INVALID_HEADER",
        ),
    ],
)
def test_required_and_strict_headers(
    product_api, contract_validator, headers, status, code
):
    client, _, _ = product_api
    product = create(client).json()
    response = client.patch(
        f"/products/{product['id']}", json={"name": "changed"}, headers=headers
    )
    assert_error(response, status, code, contract_validator)
    assert client.get(f"/products/{product['id']}").json()["version"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=1.0",
        "limit=true",
        "is_active=1",
        "is_active=False",
        "store_id=other",
        "limit=1&limit=2",
    ],
)
def test_query_validation(product_api, contract_validator, query):
    assert_error(
        product_api[0].get("/products?" + query),
        422,
        "VALIDATION_ERROR",
        contract_validator,
    )


def test_duplicate_headers_and_malformed_json(product_api, contract_validator):
    client, repo, _ = product_api
    key = str(uuid4())
    assert_error(
        client.post(
            "/products",
            json=BODY,
            headers=[("Idempotency-Key", key), ("Idempotency-Key", key)],
        ),
        400,
        "INVALID_HEADER",
        contract_validator,
    )
    assert_error(
        client.post(
            "/products",
            content='{"name":',
            headers={"Content-Type": "application/json", "Idempotency-Key": key},
        ),
        400,
        "INVALID_JSON",
        contract_validator,
    )
    assert not repo.items


def test_paging_filters_and_cursor_scopes(product_api, contract_validator):
    client, _, _ = product_api
    for n in range(5):
        product = create(client, {**BODY, "code": f"P{n}"}).json()
        if n % 2:
            patch_product(client, product, {"is_active": False})
    ids, cursor = [], None
    while True:
        response = client.get(
            "/products",
            params={
                "limit": 1,
                "is_active": "true",
                **({"cursor": cursor} if cursor else {}),
            },
        )
        contract_validator("ProductPage", response.json())
        ids.extend(item["id"] for item in response.json()["items"])
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
    assert len(ids) == len(set(ids)) == 3 and ids == sorted(ids)
    cursor = client.get("/products?limit=1").json()["next_cursor"]
    for params in [
        {"limit": 2, "cursor": cursor},
        {"limit": 1, "is_active": "true", "cursor": cursor},
        {"limit": 1, "cursor": cursor + "x"},
        {"cursor": ""},
    ]:
        assert_error(
            client.get("/products", params=params),
            400,
            "INVALID_CURSOR",
            contract_validator,
        )


def test_cursor_expiry_restart_and_cross_store():
    now = [1000]
    codec = ProductCursors(b"first-local-key-for-unit-test-only", clock=lambda: now[0])
    scope = {"store": "demo"}
    token = codec.encode(scope, {"PK": "STORE#demo#PRODUCTS", "SK": "PRODUCT#x"})
    assert codec.decode(token, scope)["SK"] == "PRODUCT#x"
    for other in [
        ProductCursors(b"second-local-key-for-unit-testing", clock=lambda: now[0])
    ]:
        with pytest.raises(ApplicationError):
            other.decode(token, scope)
    with pytest.raises(ApplicationError):
        codec.decode(token, {"store": "other"})
    now[0] = 1900
    with pytest.raises(ApplicationError):
        codec.decode(token, scope)


def test_filter_reads_past_nonmatching_products(product_api):
    client, repo, _ = product_api
    ids = []
    for i in range(4):
        ids.append(create(client, {**BODY, "code": f"GAP{i}"}).json()["id"])
    for product_id in sorted(ids)[:-1]:
        item_key = repo.key("PRODUCTS", f"PRODUCT#{product_id}")
        repo.items[(item_key["PK"], item_key["SK"])]["is_active"] = False
    response = client.get("/products?limit=1&is_active=true")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [max(ids)]
    assert response.json()["next_cursor"] is None


def test_empty_underlying_page_does_not_end_list(product_api):
    client, repo, service = product_api
    product = create(client).json()
    key = service._product_key(product["id"])
    with patch.object(
        repo,
        "query_page",
        side_effect=[Page([], key), Page([{**key, **product}], None)],
    ):
        response = client.get("/products?limit=1")
    assert response.status_code == 200 and response.json()["items"] == [product]


def test_read_budget_never_returns_partial_success(product_api, contract_validator):
    client, repo, _ = product_api
    with patch.object(
        repo, "query_page", return_value=Page([], repo.key("PRODUCTS", "PRODUCT#x"))
    ):
        response = client.get("/products?is_active=true")
    assert_error(response, 503, "QUERY_BUDGET_EXCEEDED", contract_validator)
    assert "items" not in response.json()


def test_concurrent_update_and_identical_request_winner(
    product_api, contract_validator
):
    client, repo, service = product_api
    original = create(client).json()
    item_key = service._product_key(original["id"])

    def other_writer():
        repo.items[(item_key["PK"], item_key["SK"])]["version"] = 2

    repo.before_transaction = other_writer
    assert_error(
        patch_product(client, original, {"name": "stale"}),
        412,
        "VERSION_CONFLICT",
        contract_validator,
    )
    key = str(uuid4())
    body = {**BODY, "code": "WINNER"}

    def identical_writer():
        assert create(client, body, key).status_code == 201

    repo.before_transaction = identical_writer
    response = create(client, body, key)
    assert (
        response.status_code == 201
        and response.headers["idempotency-replayed"] == "true"
    )
    assert len([r for r in repo.items.values() if r.get("code") == "WINNER"]) == 1


def test_storage_error_and_aws_guard_do_not_leak_values(
    product_api, contract_validator
):
    client, repo, _ = product_api
    with patch.object(repo, "get", side_effect=StorageError("private-marker")):
        result = client.get(f"/products/{uuid4()}")
    assert_error(result, 503, "TEMPORARILY_UNAVAILABLE", contract_validator)
    assert result.headers["retry-after"] == "1" and "private-marker" not in result.text
    with patch("sales_manager_api.product_routes.dynamodb_client") as create_client:
        with TestClient(
            create_app(Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1"))
        ) as aws_client:
            result = aws_client.get("/products")
            assert_error(result, 503, "TEMPORARILY_UNAVAILABLE", contract_validator)
            assert aws_client.get("/health").status_code == 200
        create_client.assert_not_called()
