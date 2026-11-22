from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.cursors import ProductCursors, RevisionCursors
from sales_manager_api.product_models import MAX_VERSION
from sales_manager_api.product_routes import product_service
from sales_manager_api.products import ProductService
from sales_manager_api.repository import (
    DynamoRepository,
    Page,
    StorageConflict,
    StorageError,
)
from sales_manager_api.sale_models import Cancellation, SalePatch
from sales_manager_api.sale_revisions import RevisionReader
from sales_manager_api.sale_routes import revision_reader, sale_service
from sales_manager_api.sales import SaleService
from sales_manager_api.settings import Settings

PRODUCT = "00000000-0000-4000-8000-000000000001"
TEA = "00000000-0000-4000-8000-000000000002"
CREATE = {
    "sale_date": "2026-11-01",
    "lines": [{"product_id": PRODUCT, "unit_price_yen": 550, "quantity": 2}],
}


class ChangeRepository(DynamoRepository):
    """Atomic test double for update logic; real transactions are tested separately."""

    def __init__(self):
        super().__init__(None, "sales-manager-test-changes", "demo")
        self.items = {}
        self.writes = []
        self.before_transaction = None

    def get(self, key):
        return deepcopy(self.items.get((key["PK"], key["SK"])))

    def transact(self, writes):
        self.writes = writes
        if self.before_transaction:
            callback, self.before_transaction = self.before_transaction, None
            callback()
        assert len({(w.item["PK"], w.item["SK"]) for w in writes}) == len(writes)
        for write in writes:
            current = self.get(write.item)
            if write.condition == "attribute_not_exists(PK)":
                valid = current is None
            else:
                valid = current is not None and current["version"] == write.values[":v"]
                if write.kind == "check":
                    valid = valid and current["is_active"]
            if not valid:
                raise StorageConflict("conditional failure")
        for write in writes:
            key = write.item["PK"], write.item["SK"]
            if write.kind == "put":
                self.items[key] = deepcopy(write.item)
            elif write.kind == "delete":
                self.items.pop(key, None)

    def query_page(self, pk, sk_prefix, *, limit=50, last_key=None, ascending=True):
        rows = [
            item
            for (p, s), item in sorted(self.items.items(), reverse=not ascending)
            if p == self.prefix + pk
            and s.startswith(sk_prefix)
            and (last_key is None or s > last_key["SK"])
        ]
        selected = rows[:limit]
        return Page(
            deepcopy(selected), self._key(selected[-1]) if len(rows) > limit else None
        )


def product(repo, product_id=PRODUCT, **changes):
    key = repo.key("PRODUCTS", "PRODUCT#" + product_id)
    repo.items[(key["PK"], key["SK"])] = {
        **key,
        "id": product_id,
        "code": "COFFEE" if product_id == PRODUCT else "TEA",
        "name": "コーヒー" if product_id == PRODUCT else "紅茶",
        "default_unit_price_yen": 550,
        "is_active": True,
        "version": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        **changes,
    }


@pytest.fixture
def changes_api():
    repo = ChangeRepository()
    product(repo)
    product(repo, TEA)
    service = SaleService(repo, clock=lambda: datetime(2026, 11, 8, tzinfo=UTC))
    clock = [1000]
    revisions = RevisionReader(
        repo,
        RevisionCursors(b"unit-revision-key-not-a-secret-123", clock=lambda: clock[0]),
    )
    app = create_app(Settings(APP_ENV="test"))
    app.dependency_overrides[sale_service] = lambda: service
    app.dependency_overrides[revision_reader] = lambda: revisions
    app.dependency_overrides[product_service] = lambda: ProductService(
        repo, ProductCursors(b"unit-product-key-not-a-secret-1234")
    )
    with TestClient(app) as client:
        yield client, repo, service, clock


def create(client, body=None, key=None):
    response = client.post(
        "/sales", json=body or CREATE, headers={"Idempotency-Key": key or str(uuid4())}
    )
    assert response.status_code == 201, response.text
    return response.json()


def correction(sale, **changes):
    return {
        "sale_date": sale["sale_date"],
        "lines": [
            {
                k: line[k]
                for k in ["line_id", "product_id", "unit_price_yen", "quantity"]
            }
            for line in sale["lines"]
        ],
        "reason": "入力数量の訂正",
        **changes,
    }


def modify(client, sale, body=None, key=None, etag=None):
    return client.patch(
        "/sales/" + sale["id"],
        json=body or correction(sale),
        headers={
            "Idempotency-Key": key or str(uuid4()),
            "If-Match": etag or f'"v{sale["version"]}"',
        },
    )


def cancel(client, sale, key=None, etag=None, reason="二重入力の取消"):
    return client.post(
        "/sales/" + sale["id"] + "/cancel",
        json={"reason": reason},
        headers={
            "Idempotency-Key": key or str(uuid4()),
            "If-Match": etag or f'"v{sale["version"]}"',
        },
    )


def test_correction_move_cancel_and_revision_chain_match_yaml(
    changes_api, contract_validator
):
    client, repo, _, _ = changes_api
    first = create(client)
    body = correction(first, sale_date="2026-11-02")
    body["lines"][0]["quantity"] = 1
    response = modify(client, first, body)
    assert response.status_code == 200, response.text
    updated = response.json()
    contract_validator("Sale", updated)
    assert (
        updated["version"] == 2
        and updated["total_amount_yen"] == 550
        and updated["created_at"] == first["created_at"]
    )
    assert updated["lines"][0]["line_id"] == first["lines"][0]["line_id"]
    assert repo.get(repo.key("DAY#2026-11-01", "SALE#" + first["id"])) is None
    assert repo.get(repo.key("DAY#2026-11-02", "SALE#" + first["id"]))["version"] == 2
    assert (
        client.get(
            "/sales", params={"start_date": "2026-11-01", "end_date": "2026-11-01"}
        ).json()["items"]
        == []
    )
    response = cancel(client, updated)
    assert response.status_code == 200
    stopped = response.json()
    contract_validator("Sale", stopped)
    assert (
        stopped["status"] == "cancelled"
        and stopped["version"] == 3
        and stopped["total_amount_yen"] == 550
    )
    assert stopped["lines"] == updated["lines"] and response.headers["etag"] == '"v3"'
    assert client.get("/sales/" + first["id"]).json() == stopped
    assert (
        client.get(
            "/sales",
            params={
                "start_date": "2026-11-02",
                "end_date": "2026-11-02",
                "status": "confirmed",
            },
        ).json()["items"]
        == []
    )
    page = client.get("/sales/" + first["id"] + "/revisions")
    contract_validator("RevisionPage", page.json())
    revisions = page.json()["items"]
    assert [r["operation"] for r in revisions] == ["created", "corrected", "cancelled"]
    assert revisions[0]["before"] is None and revisions[0]["after"] == first
    assert (
        revisions[1]["before"] == first
        and revisions[1]["after"] == updated
        and revisions[1]["reason"] == body["reason"]
    )
    assert revisions[2]["before"] == updated and revisions[2]["after"] == stopped
    assert all(r["actor_id"] == "local-admin" for r in revisions)


def test_same_day_uses_one_conditional_day_put(changes_api):
    client, repo, _, _ = changes_api
    first = create(client)
    response = modify(client, first)
    assert response.status_code == 200 and response.json()["version"] == 2
    assert len(repo.writes) == 4 and not any(w.kind == "delete" for w in repo.writes)


def test_preserved_inactive_product_and_explicit_refresh(changes_api):
    client, repo, _, _ = changes_api
    first = create(client)
    product(
        repo, name="新しい名称", default_unit_price_yen=600, version=2, is_active=False
    )
    changed = modify(client, first)
    assert (
        changed.status_code == 200
        and changed.json()["lines"][0]["product_name"] == "コーヒー"
    )
    before = deepcopy(repo.items)
    body = correction(changed.json())
    body["lines"][0]["refresh_product_snapshot"] = True
    assert (
        modify(client, changed.json(), body).json()["error"]["code"]
        == "PRODUCT_INACTIVE"
    )
    body["lines"][0].pop("line_id")
    assert modify(client, changed.json(), body).status_code == 409
    assert repo.items == before
    product(repo, name="新しい名称", default_unit_price_yen=600, version=3)
    body = correction(changed.json())
    body["lines"][0]["refresh_product_snapshot"] = True
    refreshed = modify(client, changed.json(), body).json()
    assert (
        refreshed["lines"][0]["product_name"] == "新しい名称"
        and refreshed["lines"][0]["unit_price_yen"] == 550
    )


def test_line_reorder_remove_add_and_product_replacement(changes_api):
    client, _, _, _ = changes_api
    first = create(
        client,
        {
            **CREATE,
            "lines": CREATE["lines"]
            + [{**CREATE["lines"][0], "product_id": TEA, "unit_price_yen": 330}],
        },
    )
    body = correction(first)
    body["lines"].reverse()
    second = modify(client, first, body).json()
    assert [x["line_id"] for x in second["lines"]] == list(
        reversed([x["line_id"] for x in first["lines"]])
    )
    assert [x["line_no"] for x in second["lines"]] == [1, 2]
    body = correction(second)
    body["lines"] = body["lines"][:1] + [CREATE["lines"][0]]
    third = modify(client, second, body).json()
    assert third["lines"][1]["line_id"] not in {x["line_id"] for x in first["lines"]}
    body = correction(third)
    body["lines"][0]["product_id"] = PRODUCT
    fourth = modify(client, third, body).json()
    assert (
        fourth["lines"][0]["line_id"] == third["lines"][0]["line_id"]
        and fourth["lines"][0]["product_name"] == "コーヒー"
    )


@pytest.mark.parametrize("reason", ["", "  ", "x" * 501, None, 1, True])
@pytest.mark.parametrize("action", ["patch", "cancel"])
def test_reason_validation_no_write(changes_api, reason, action):
    client, repo, _, _ = changes_api
    first = create(client)
    before = deepcopy(repo.items)
    response = (
        modify(client, first, correction(first, reason=reason))
        if action == "patch"
        else cancel(client, first, reason=reason)
    )
    assert response.status_code == 422 and repo.items == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("line_id", None),
        ("line_id", "bad"),
        ("line_id", True),
        ("refresh_product_snapshot", "true"),
        ("refresh_product_snapshot", 1),
        ("refresh_product_snapshot", None),
        ("quantity", 1.0),
        ("quantity", 0),
        ("quantity", True),
        ("unit_price_yen", "550"),
        ("unit_price_yen", -1),
        ("product_name", "untrusted"),
        ("line_amount_yen", 1),
    ],
)
def test_patch_line_validation(changes_api, field, value):
    client, repo, _, _ = changes_api
    first = create(client)
    before = deepcopy(repo.items)
    body = correction(first)
    body["lines"][0][field] = value
    assert modify(client, first, body).status_code == 422 and repo.items == before


@pytest.mark.parametrize(
    "kind",
    [
        "unknown",
        "duplicate",
        "empty",
        "too_many",
        "future",
        "bad_date",
        "partial",
        "server_field",
        "amount_over",
    ],
)
def test_invalid_patch_shapes_and_business_bounds(changes_api, kind):
    client, repo, _, _ = changes_api
    first = create(client)
    before = deepcopy(repo.items)
    body = correction(first)
    if kind == "unknown":
        body["lines"][0]["line_id"] = str(uuid4())
    elif kind == "duplicate":
        body["lines"] *= 2
    elif kind == "empty":
        body["lines"] = []
    elif kind == "too_many":
        body["lines"] = [CREATE["lines"][0]] * 51
    elif kind == "future":
        body["sale_date"] = "2026-11-09"
    elif kind == "bad_date":
        body["sale_date"] = "2026-02-30"
    elif kind == "partial":
        body = {"reason": "partial"}
    elif kind == "server_field":
        body["actor_id"] = "untrusted"
    elif kind == "amount_over":
        body["lines"][0].update(unit_price_yen=9999999, quantity=9999)
    response = modify(client, first, body)
    assert response.status_code == 422 and repo.items == before


@pytest.mark.parametrize(
    "etag", ["v1", 'W/"v1"', "*", '"v0"', '"v2147483648"', '"v1", "v2"', ""]
)
def test_malformed_preconditions(changes_api, etag):
    client, repo, _, _ = changes_api
    first = create(client)
    before = deepcopy(repo.items)
    response = client.patch(
        "/sales/" + first["id"],
        json=correction(first),
        headers={"Idempotency-Key": str(uuid4()), "If-Match": etag},
    )
    assert response.status_code == 400 and repo.items == before


def test_missing_duplicate_headers_stale_and_unknown_sale(changes_api):
    client, _, _, _ = changes_api
    first = create(client)
    path = "/sales/" + first["id"]
    assert (
        client.patch(
            path, json=correction(first), headers={"Idempotency-Key": str(uuid4())}
        ).status_code
        == 428
    )
    assert (
        client.patch(
            path, json=correction(first), headers={"If-Match": '"v1"'}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            path,
            json=correction(first),
            headers=[
                ("Idempotency-Key", str(uuid4())),
                ("If-Match", '"v1"'),
                ("If-Match", '"v1"'),
            ],
        ).status_code
        == 400
    )
    assert modify(client, first).status_code == 200
    assert (
        modify(client, first).status_code == 412
        and cancel(client, first).status_code == 412
    )
    missing = {**first, "id": str(uuid4())}
    assert (
        modify(client, missing).status_code == 404
        and cancel(client, missing).status_code == 404
    )


@pytest.mark.parametrize("action", ["patch", "cancel"])
def test_cancelled_is_terminal_and_max_version_rejected(changes_api, action):
    client, repo, _, _ = changes_api
    first = create(client)
    stopped = cancel(client, first).json()
    before = deepcopy(repo.items)
    response = modify(client, stopped) if action == "patch" else cancel(client, stopped)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "SALE_CANCELLED"
        and repo.items == before
    )
    key = repo.key("SALE#" + first["id"], "CURRENT")
    repo.items[(key["PK"], key["SK"])].update(status="confirmed", version=MAX_VERSION)
    maximum = {**first, "version": MAX_VERSION}
    response = modify(client, maximum) if action == "patch" else cancel(client, maximum)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "VERSION_LIMIT_EXCEEDED"
    )


def test_original_create_patch_cancel_replays_after_later_changes(changes_api):
    client, repo, _, _ = changes_api
    create_key, patch_key, cancel_key = [str(uuid4()) for _ in range(3)]
    first = create(client, key=create_key)
    body = correction(first)
    response = modify(client, first, body, patch_key)
    second = response.json()
    stopped = cancel(client, second, cancel_key).json()
    before = deepcopy(repo.items)
    assert create(client, key=create_key) == first
    replay = modify(client, first, body, patch_key)
    assert (
        replay.status_code == 200
        and replay.json() == second
        and replay.headers["etag"] == '"v2"'
        and replay.headers["idempotency-replayed"] == "true"
    )
    replay = cancel(client, second, cancel_key)
    assert replay.json() == stopped and replay.headers["idempotency-replayed"] == "true"
    assert repo.items == before
    assert (
        modify(client, first, {**body, "reason": "changed"}, patch_key).status_code
        == 409
    )
    assert modify(client, second, body, patch_key).status_code == 409
    assert cancel(client, second, patch_key).status_code == 409


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_patch_has_one_version_or_replays(changes_api, same_key):
    client, repo, service, _ = changes_api
    first = create(client)
    body = correction(first)
    key = str(uuid4())
    inner_key = key if same_key else str(uuid4())
    repo.before_transaction = lambda: service.patch(
        first["id"], SalePatch.model_validate(body), inner_key, '"v1"'
    )
    response = modify(client, first, body, key)
    assert response.status_code == (200 if same_key else 412)
    if same_key:
        assert response.headers["idempotency-replayed"] == "true"
    assert service._current(first["id"])["version"] == 2
    assert len(client.get("/sales/" + first["id"] + "/revisions").json()["items"]) == 2


def test_cancel_wins_race_without_leaving_correction(changes_api):
    client, repo, service, _ = changes_api
    first = create(client)
    repo.before_transaction = lambda: service.cancel(
        first["id"], Cancellation(reason="concurrent"), str(uuid4()), '"v1"'
    )
    assert modify(client, first).status_code == 412
    assert service._current(first["id"])["status"] == "cancelled"
    assert len(client.get("/sales/" + first["id"] + "/revisions").json()["items"]) == 2


@pytest.mark.parametrize("inactive", [False, True])
def test_snapshot_product_race_rejects_entire_change(changes_api, inactive):
    client, repo, _, _ = changes_api
    first = create(client)
    body = correction(first, sale_date="2026-11-02")
    body["lines"][0]["refresh_product_snapshot"] = True
    repo.before_transaction = lambda: product(
        repo, version=2, name="同時改名", is_active=not inactive
    )
    response = modify(client, first, body)
    assert response.status_code == 409 and response.json()["error"]["code"] == (
        "PRODUCT_INACTIVE" if inactive else "PRODUCT_CHANGED"
    )
    assert client.get("/sales/" + first["id"]).json() == first
    assert repo.get(repo.key("DAY#2026-11-02", "SALE#" + first["id"])) is None
    assert len(client.get("/sales/" + first["id"] + "/revisions").json()["items"]) == 1


def test_missing_day_reference_fails_closed_and_storage_is_redacted(changes_api):
    client, repo, _, _ = changes_api
    first = create(client)
    day = repo.key("DAY#" + first["sale_date"], "SALE#" + first["id"])
    repo.items.pop((day["PK"], day["SK"]))
    response = modify(client, first)
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    assert client.get("/sales/" + first["id"]).json() == first
    with patch.object(repo, "transact", side_effect=StorageError("private-sdk")):
        response = cancel(client, first)
        assert response.status_code == 503 and "private-sdk" not in response.text


@pytest.mark.parametrize("limit", [1, 2, 3, 100])
def test_history_version_order_and_pagination(changes_api, contract_validator, limit):
    client, _, _, _ = changes_api
    sale = create(client)
    for _ in range(11):
        sale = modify(client, sale).json()
    versions = []
    cursor = None
    for _ in range(20):
        response = client.get(
            "/sales/" + sale["id"] + "/revisions",
            params={"limit": limit, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200
        contract_validator("RevisionPage", response.json())
        versions.extend(r["version"] for r in response.json()["items"])
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
    assert versions == list(range(1, 13))


def test_history_cursor_scope_expiry_and_validation(changes_api):
    client, _, _, clock = changes_api
    first = create(client)
    assert modify(client, first).status_code == 200
    other = create(client)
    path = "/sales/" + first["id"] + "/revisions"
    token = client.get(path, params={"limit": 1}).json()["next_cursor"]
    assert client.get(path, params={"limit": 2, "cursor": token}).status_code == 400
    assert (
        client.get(
            "/sales/" + other["id"] + "/revisions", params={"limit": 1, "cursor": token}
        ).status_code
        == 400
    )
    assert (
        client.get(path, params={"limit": 1, "cursor": token + "x"}).status_code == 400
    )
    clock[0] = 1900
    assert client.get(path, params={"limit": 1, "cursor": token}).status_code == 400
    assert client.get("/sales/" + str(uuid4()) + "/revisions").status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=1.0",
        "limit=01",
        "limit=1&limit=2",
        "unknown=x",
        "cursor=x&cursor=y",
    ],
)
def test_history_bad_query(changes_api, query):
    client, _, _, _ = changes_api
    sale = create(client)
    assert client.get("/sales/" + sale["id"] + "/revisions?" + query).status_code == 422


def test_read_budget_and_aws_guard(changes_api):
    client, repo, _, _ = changes_api
    sale = create(client)
    key = repo.key("SALE#" + sale["id"], "REV#0000000001")
    with (
        patch.object(repo, "query_page", return_value=Page([], key)),
        patch("sales_manager_api.sale_revisions.REVISION_QUERY_BUDGET", 2),
    ):
        response = client.get("/sales/" + sale["id"] + "/revisions")
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "QUERY_BUDGET_EXCEEDED"
        )
    with patch("sales_manager_api.sale_routes.dynamodb_client") as sdk:
        with TestClient(
            create_app(Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1"))
        ) as aws:
            assert modify(aws, sale).status_code == 503
            assert cancel(aws, sale).status_code == 503
            assert aws.get("/sales/" + sale["id"] + "/revisions").status_code == 503
            assert aws.get("/health").status_code == 200
        sdk.assert_not_called()


@pytest.mark.parametrize(
    "bad_key",
    [
        None,
        {},
        {"PK": "other", "SK": "REV#0000000001"},
        {"SK": "CURRENT"},
        {"SK": "REV#1"},
        {"SK": "REV#0000000000"},
        {"SK": "REV#2147483648"},
        {"SK": 1},
    ],
)
def test_signed_history_cursor_rejects_invalid_database_keys(changes_api, bad_key):
    client, repo, _, _ = changes_api
    first = create(client)
    reader = client.app.dependency_overrides[revision_reader]()
    scope = {
        "store": repo.prefix,
        "resource": "sale_revisions",
        "sale_id": first["id"],
        "limit": 1,
        "order": "version_asc",
    }
    key = repo.key("SALE#" + first["id"], "REV#0000000001")
    state = {**key, **bad_key} if bad_key else bad_key
    token = reader.cursors.encode(scope, state)
    response = client.get(
        "/sales/" + first["id"] + "/revisions", params={"limit": 1, "cursor": token}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


def test_history_fills_a_page_from_smaller_database_pages(changes_api):
    client, repo, _, _ = changes_api
    first = create(client)
    second = modify(client, first).json()
    assert cancel(client, second).status_code == 200
    keys = [repo.key("SALE#" + first["id"], f"REV#{v:010d}") for v in [1, 2, 3]]
    pages = [
        Page([repo.get(key)], key if i < 2 else None) for i, key in enumerate(keys)
    ]
    with patch.object(repo, "query_page", side_effect=pages) as query:
        page = client.get("/sales/" + first["id"] + "/revisions", params={"limit": 3})
    assert [r["version"] for r in page.json()["items"]] == [1, 2, 3]
    assert page.json()["next_cursor"] is None
    assert [call.kwargs["limit"] for call in query.call_args_list] == [3, 2, 1]


def test_preserved_missing_product_can_be_corrected_and_cancelled(changes_api):
    client, repo, _, _ = changes_api
    first = create(client)
    key = repo.key("PRODUCTS", "PRODUCT#" + PRODUCT)
    repo.items.pop((key["PK"], key["SK"]))
    result = modify(client, first)
    assert result.status_code == 200
    second = result.json()
    body = correction(second)
    body["lines"][0]["refresh_product_snapshot"] = True
    assert modify(client, second, body).status_code == 404
    assert cancel(client, second).status_code == 200
