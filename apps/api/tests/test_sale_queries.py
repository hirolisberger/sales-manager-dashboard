from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.cursors import ProductCursors, SaleCursors
from sales_manager_api.errors import ApplicationError
from sales_manager_api.repository import DynamoRepository, Page, StorageError
from sales_manager_api.sale_queries import SaleReader, SaleSearch
from sales_manager_api.sale_routes import sale_reader
from sales_manager_api.settings import Settings

COFFEE = "00000000-0000-4000-8000-000000000001"
TEA = "00000000-0000-4000-8000-000000000002"
PARAMS = {"start_date": "2026-10-30", "end_date": "2026-11-02"}


class ReadMemoryRepository(DynamoRepository):
    """Read test double; actual Query behavior is verified against MiniStack."""

    def __init__(self, store="demo"):
        super().__init__(None, "sales-manager-test-reads", store)
        self.items, self.queries = {}, []
        self.page_cap = 100
        self.empty_first = False

    def get(self, key):
        return deepcopy(self.items.get((key["PK"], key["SK"])))

    def query_page(self, pk, sk_prefix, *, limit=50, last_key=None, ascending=True):
        self.queries.append((pk, limit, last_key, ascending))
        if self.empty_first:
            self.empty_first = False
            return Page([], self.key(pk, "SALE#ffffffff-ffff-4fff-8fff-ffffffffffff"))
        partition = self.key(pk, sk_prefix)["PK"]
        rows = [
            item
            for (p, s), item in sorted(self.items.items(), reverse=not ascending)
            if p == partition
            and s.startswith(sk_prefix)
            and (
                last_key is None
                or (s > last_key["SK"] if ascending else s < last_key["SK"])
            )
        ]
        selected = rows[: min(limit, self.page_cap)]
        return Page(
            deepcopy(selected),
            self._key(selected[-1]) if len(rows) > len(selected) else None,
        )


def seed_sale(repo, number, day, *, status="confirmed", version=1, product_id=COFFEE):
    sale_id = str(UUID(int=number))
    sale = {
        "id": sale_id,
        "sale_date": day,
        "currency": "JPY",
        "status": status,
        "version": version,
        "total_amount_yen": 1430,
        "created_at": "2026-11-02T00:00:00Z",
        "updated_at": "2026-11-02T00:00:00Z",
        "lines": [
            {
                "line_id": str(uuid4()),
                "line_no": 1,
                "product_id": product_id,
                "product_code": "COFFEE",
                "product_name": "登録時の名称",
                "unit_price_yen": 550,
                "quantity": 2,
                "line_amount_yen": 1100,
            },
            {
                "line_id": str(uuid4()),
                "line_no": 2,
                "product_id": TEA,
                "product_code": "TEA",
                "product_name": "紅茶",
                "unit_price_yen": 330,
                "quantity": 1,
                "line_amount_yen": 330,
            },
        ],
    }
    for key in [
        repo.key(f"SALE#{sale_id}", "CURRENT"),
        repo.key(f"DAY#{day}", f"SALE#{sale_id}"),
    ]:
        repo.items[(key["PK"], key["SK"])] = {**key, **deepcopy(sale)}
    return sale


@pytest.fixture
def read_api():
    repo = ReadMemoryRepository()
    clock = [1000]
    codec = SaleCursors(b"local-sale-test-key-not-a-secret!!", clock=lambda: clock[0])
    reader = SaleReader(repo, codec)
    app = create_app(Settings(APP_ENV="test"))
    app.dependency_overrides[sale_reader] = lambda: reader
    with TestClient(app) as client:
        yield client, repo, reader, clock


def test_detail_has_all_snapshot_lines_latest_version_and_etag(
    read_api, contract_validator
):
    client, repo, _, _ = read_api
    sale = seed_sale(repo, 1, "2026-10-30", status="cancelled", version=3)
    response = client.get("/sales/" + sale["id"])
    assert response.status_code == 200 and response.json() == sale
    contract_validator("Sale", response.json())
    assert response.headers["etag"] == '"v3"'
    assert "PK" not in response.json() and len(response.json()["lines"]) == 2


@pytest.mark.parametrize(
    "sale_id,status,code",
    [("bad", 422, "VALIDATION_ERROR"), (str(UUID(int=999)), 404, "SALE_NOT_FOUND")],
)
def test_unknown_and_invalid_detail(
    read_api, contract_validator, sale_id, status, code
):
    response = read_api[0].get("/sales/" + sale_id)
    assert response.status_code == status and response.json()["error"]["code"] == code
    contract_validator("Error", response.json())
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]


@pytest.mark.parametrize("limit", [1, 2, 3, 100])
def test_multi_day_order_no_duplicates_or_missing_rows(
    read_api, contract_validator, limit
):
    client, repo, _, _ = read_api
    expected = []
    for n, day in enumerate(
        [
            "2026-10-29",
            "2026-10-30",
            "2026-11-01",
            "2026-11-01",
            "2026-11-02",
            "2026-11-03",
        ],
        1,
    ):
        sale = seed_sale(repo, n, day)
        if PARAMS["start_date"] <= day <= PARAMS["end_date"]:
            expected.append(sale)
    seen = []
    cursor = None
    for _ in range(10):
        response = client.get(
            "/sales",
            params={**PARAMS, "limit": limit, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200
        contract_validator("SalePage", response.json())
        seen.extend(row["id"] for row in response.json()["items"])
        cursor = response.json()["next_cursor"]
        if cursor is None:
            break
    else:
        pytest.fail("Pagination did not terminate")
    assert seen == [
        s["id"]
        for s in sorted(expected, key=lambda s: (s["sale_date"], s["id"]), reverse=True)
    ]
    assert len(seen) == len(set(seen)) == 4
    assert all(call[3] is False for call in repo.queries)


def test_product_filter_keeps_full_total_and_sums_only_matching_lines(
    read_api, contract_validator
):
    client, repo, _, _ = read_api
    sale = seed_sale(repo, 1, "2026-11-01", product_id=TEA)
    for product, amount, quantity in [(COFFEE, 0, 0), (TEA, 1430, 3)]:
        response = client.get("/sales", params={**PARAMS, "product_id": product})
        assert response.status_code == 200
        contract_validator("SalePage", response.json())
        if not quantity:
            assert response.json()["items"] == []
        else:
            row = response.json()["items"][0]
            assert (
                row["total_amount_yen"] == 1430
                and row["matched_amount_yen"] == amount
                and row["matched_quantity"] == quantity
            )
            assert "lines" not in row
    ordinary = seed_sale(repo, 2, "2026-11-02")
    row = client.get("/sales", params={**PARAMS, "product_id": TEA}).json()["items"][0]
    assert (
        row["id"] == ordinary["id"]
        and row["total_amount_yen"] == 1430
        and row["matched_amount_yen"] == 330
        and row["matched_quantity"] == 1
    )
    assert client.get("/sales/" + sale["id"]).json() == sale


@pytest.mark.parametrize(
    "status,count", [("all", 2), ("confirmed", 1), ("cancelled", 1)]
)
def test_status_filter_and_default_all(read_api, status, count):
    client, repo, _, _ = read_api
    seed_sale(repo, 1, "2026-11-01")
    seed_sale(repo, 2, "2026-11-01", status="cancelled")
    assert (
        len(client.get("/sales", params={**PARAMS, "status": status}).json()["items"])
        == count
    )
    assert len(client.get("/sales", params=PARAMS).json()["items"]) == 2


@pytest.mark.parametrize(
    "extra",
    [
        {"start_date": ""},
        {"start_date": "2026-1-01"},
        {"start_date": "2026-02-29"},
        {"start_date": "20261101"},
        {"start_date": "2026-W44-7"},
        {"end_date": "2026-10-01"},
        {"end_date": "9999-12-31"},
        {"limit": "0"},
        {"limit": "101"},
        {"limit": "1.0"},
        {"limit": "01"},
        {"limit": "true"},
        {"status": "Confirmed"},
        {"status": ""},
        {"product_id": "bad"},
        {"product_id": ""},
        {"unknown": "1"},
    ],
)
def test_bad_query_parameters(read_api, extra):
    response = read_api[0].get("/sales", params={**PARAMS, **extra})
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "VALIDATION_ERROR"
    )


@pytest.mark.parametrize(
    "params", [{}, {"start_date": "2026-01-01"}, {"end_date": "2026-01-01"}]
)
def test_required_dates(read_api, params):
    assert read_api[0].get("/sales", params=params).status_code == 422


@pytest.mark.parametrize(
    "name", ["start_date", "end_date", "limit", "status", "product_id", "cursor"]
)
def test_duplicate_query_rejected(read_api, name):
    params = list(PARAMS.items()) + [(name, "one"), (name, "two")]
    assert read_api[0].get("/sales", params=params).status_code == 422


def test_366_days_empty_future_and_367_days_rejected(read_api):
    client, repo, _, _ = read_api
    start = date(2028, 1, 1)
    end = start + timedelta(days=365)
    response = client.get(
        "/sales", params={"start_date": str(start), "end_date": str(end)}
    )
    assert response.status_code == 200 and response.json() == {
        "items": [],
        "next_cursor": None,
    }
    assert len(repo.queries) == 366
    response = client.get(
        "/sales",
        params={"start_date": str(start), "end_date": str(end + timedelta(days=1))},
    )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "PERIOD_TOO_LONG"
    )
    assert (
        client.get(
            "/sales", params={"start_date": "0001-01-01", "end_date": "0001-01-01"}
        ).status_code
        == 200
    )


def test_cursor_cross_date_state_and_all_scope_changes_rejected(read_api):
    client, repo, reader, _ = read_api
    seed_sale(repo, 1, "2026-11-02")
    seed_sale(repo, 2, "2026-10-30")
    first = client.get("/sales", params={**PARAMS, "limit": 1}).json()
    cursor = first["next_cursor"]
    search = SaleSearch.parse({**PARAMS, "limit": "1"})
    state = reader.cursors.decode(cursor, reader.scope(search))
    assert state == {"day": "2026-11-01", "last_key": None}
    for changes in [
        {"limit": 2},
        {"status": "confirmed"},
        {"product_id": COFFEE},
        {"start_date": "2026-10-29"},
        {"end_date": "2026-11-03"},
        {"cursor": cursor + "x"},
    ]:
        response = client.get(
            "/sales", params={**PARAMS, "limit": 1, "cursor": cursor, **changes}
        )
        assert (
            response.status_code == 400
            and response.json()["error"]["code"] == "INVALID_CURSOR"
        )
    assert client.get("/sales", params={**PARAMS, "cursor": ""}).status_code == 400


def test_cursor_expiry_restart_resource_and_store_boundaries(read_api):
    _, repo, reader, clock = read_api
    search = SaleSearch.parse(PARAMS)
    scope = reader.scope(search)
    state = {"day": PARAMS["end_date"], "last_key": None}
    token = reader.cursors.encode(scope, state)
    for changes in [{"store": "STORE#other#"}, {"resource": "products"}]:
        with pytest.raises(ApplicationError):
            reader.cursors.decode(token, {**scope, **changes})
    with pytest.raises(ApplicationError):
        SaleCursors(b"different-key-for-restart-testing!!", clock=lambda: 1000).decode(
            token, scope
        )
    product_token = ProductCursors(reader.cursors.key, clock=lambda: 1000).encode(
        {"resource": "products"}, repo.key("PRODUCTS", "PRODUCT#x")
    )
    with pytest.raises(ApplicationError):
        reader.cursors.decode(product_token, scope)
    clock[0] = 1900
    with pytest.raises(ApplicationError):
        reader.cursors.decode(token, scope)


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"day": "2026-11-01", "last_key": {}, "extra": True},
        {"day": True, "last_key": None},
        {"day": "2026-11-09", "last_key": None},
        {"day": "2026-1-01", "last_key": None},
        {"day": "2026-11-01", "last_key": []},
        {
            "day": "2026-11-01",
            "last_key": {
                "PK": "STORE#other#DAY#2026-11-01",
                "SK": "SALE#" + str(UUID(int=1)),
            },
        },
        {
            "day": "2026-11-01",
            "last_key": {
                "PK": "STORE#demo#DAY#2026-11-02",
                "SK": "SALE#" + str(UUID(int=1)),
            },
        },
        {
            "day": "2026-11-01",
            "last_key": {"PK": "STORE#demo#DAY#2026-11-01", "SK": "PRODUCT#x"},
        },
        {
            "day": "2026-11-01",
            "last_key": {"PK": "STORE#demo#DAY#2026-11-01", "SK": "SALE#bad"},
        },
    ],
)
def test_signed_but_malformed_cursor_state_rejected(read_api, state):
    client, _, reader, _ = read_api
    scope = reader.scope(SaleSearch.parse(PARAMS))
    token = reader.cursors.encode(scope, state)
    response = client.get("/sales", params={**PARAMS, "cursor": token})
    assert (
        response.status_code == 400
        and response.json()["error"]["code"] == "INVALID_CURSOR"
    )


def test_internal_empty_page_and_small_pages_do_not_drop_rows(read_api):
    client, repo, _, _ = read_api
    for i in range(1, 6):
        seed_sale(repo, i, "2026-11-01")
    repo.empty_first = True
    repo.page_cap = 1
    response = client.get("/sales", params={**PARAMS, "limit": 3})
    assert response.status_code == 200 and len(response.json()["items"]) == 3
    token = response.json()["next_cursor"]
    rest = client.get("/sales", params={**PARAMS, "limit": 3, "cursor": token})
    ids = [row["id"] for row in response.json()["items"] + rest.json()["items"]]
    assert len(ids) == len(set(ids)) == 5 and ids == sorted(ids, reverse=True)


def test_nonmatching_status_and_products_do_not_end_page_early(read_api):
    client, repo, _, _ = read_api
    seed_sale(repo, 1, "2026-10-30")
    seed_sale(repo, 2, "2026-11-01", status="cancelled")
    seed_sale(repo, 3, "2026-11-02", product_id=TEA)
    response = client.get(
        "/sales",
        params={**PARAMS, "status": "confirmed", "product_id": COFFEE, "limit": 1},
    )
    assert response.status_code == 200 and response.json()["items"][0]["id"] == str(
        UUID(int=1)
    )


def test_budget_exhaustion_returns_503_instead_of_partial_success(read_api):
    client, repo, _, _ = read_api
    seed_sale(repo, 1, "2026-11-02")
    with patch("sales_manager_api.sale_queries.QUERY_BUDGET", 2):
        response = client.get("/sales", params=PARAMS)
    assert response.status_code == 503 and response.headers["retry-after"] == "1"
    assert response.json()["error"]["code"] == "QUERY_BUDGET_EXCEEDED"
    assert "items" not in response.json()


def test_store_separation_and_storage_errors_do_not_leak(read_api):
    client, repo, reader, _ = read_api
    other = ReadMemoryRepository("other")
    sale = seed_sale(other, 1, "2026-11-01")
    repo.items.update(other.items)
    assert client.get("/sales/" + sale["id"]).status_code == 404
    assert client.get("/sales", params=PARAMS).json()["items"] == []
    with patch.object(
        repo, "query_page", side_effect=StorageError("private-sdk-detail")
    ):
        response = client.get("/sales", params=PARAMS)
    assert response.status_code == 503 and "private-sdk-detail" not in response.text


def test_insertion_between_pages_is_not_a_snapshot(read_api):
    client, repo, _, _ = read_api
    seed_sale(repo, 2, "2026-11-01")
    seed_sale(repo, 1, "2026-11-01")
    params = {"start_date": "2026-11-01", "end_date": "2026-11-01", "limit": 1}
    first = client.get("/sales", params=params).json()
    seed_sale(repo, 3, "2026-11-01")
    second = client.get(
        "/sales", params={**params, "cursor": first["next_cursor"]}
    ).json()
    assert first["items"][0]["id"] == str(UUID(int=2)) and second["items"][0][
        "id"
    ] == str(UUID(int=1))
    fresh = client.get("/sales", params={**params, "limit": 100}).json()
    assert len(fresh["items"]) == 3
