"""Product HTTP handlers + actual MiniStack, using only a fresh temporary table."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import ensure_table
from sales_manager_api.repository import DynamoRepository, call
from sales_manager_api.settings import Settings


def verify() -> dict:
    table = f"sales-manager-test-day07-{uuid4().hex[:12]}"
    settings = Settings(
        APP_ENV="test",
        AWS_REGION="ap-northeast-1",
        AWS_ENDPOINT_URL="http://127.0.0.1:4566",
        DYNAMODB_TABLE=table,
        STORE_ID="demo",
    )
    sdk = dynamodb_client(settings)
    created, checks = False, []
    try:
        if not ensure_table(sdk, settings):
            raise RuntimeError("Unexpected existing verification table")
        created = True
        repo = DynamoRepository(sdk, table, "demo")
        with TestClient(create_app(settings)) as client:
            body = {"code": "COFFEE", "name": "コーヒー", "default_unit_price_yen": 550}
            key = str(uuid4())

            def post(data, request_key=None):
                return client.post(
                    "/products",
                    json=data,
                    headers={"Idempotency-Key": request_key or str(uuid4())},
                )

            first = post(body, key)
            assert first.status_code == 201, first.text
            product = first.json()
            path = f"/products/{product['id']}"
            assert client.get(path).json() == product
            checks.append("create_detail_etag_and_durable_product")
            assert post(body).status_code == 409
            assert len(client.get("/products").json()["items"]) == 1
            checks.append("code_reservation_conflict_without_partial_save")
            for value in [True, 550.0, "550", -1]:
                assert (
                    post(
                        {**body, "code": "BAD", "default_unit_price_yen": value}
                    ).status_code
                    == 422
                )
            assert client.get("/products/not-a-uuid").status_code == 422
            assert client.get(f"/products/{uuid4()}").status_code == 404
            checks.append("invalid_input_and_unknown_product")
            patch_key = str(uuid4())

            def patch(data, etag, request_key=None):
                return client.patch(
                    path,
                    json=data,
                    headers={
                        "Idempotency-Key": request_key or str(uuid4()),
                        "If-Match": etag,
                    },
                )

            edited = patch(
                {"name": "更新後", "default_unit_price_yen": 600}, '"v1"', patch_key
            )
            assert edited.status_code == 200 and edited.headers["etag"] == '"v2"'
            disabled = patch({"is_active": False}, '"v2"')
            assert disabled.status_code == 200 and disabled.json()["version"] == 3
            assert client.get("/products?is_active=true").json()["items"] == []
            assert len(client.get("/products?is_active=false").json()["items"]) == 1
            assert post(body).status_code == 409
            checks.append("update_disable_filter_and_reserved_code_retention")
            repeated = post(body, key)
            assert (
                repeated.status_code == 201
                and repeated.json() == product
                and repeated.headers["idempotency-replayed"] == "true"
            )
            repeated = patch(
                {"name": "更新後", "default_unit_price_yen": 600}, '"v1"', patch_key
            )
            assert (
                repeated.json() == edited.json() and repeated.headers["etag"] == '"v2"'
            )
            assert client.get(path).json() == disabled.json()
            assert post({**body, "name": "異なる要求"}, key).status_code == 409
            checks.append("original_response_replay_after_later_changes")
            assert patch({"name": "stale"}, '"v1"').status_code == 412
            assert (
                client.patch(
                    path,
                    json={"name": "no precondition"},
                    headers={"Idempotency-Key": str(uuid4())},
                ).status_code
                == 428
            )
            assert client.get(path).json()["version"] == 3
            checks.append("stale_and_missing_precondition_no_mutation")
            for i in range(4):
                assert post({**body, "code": f"PAGE{i}"}).status_code == 201
            ids, cursor = [], None
            while True:
                page = client.get(
                    "/products",
                    params={
                        "limit": 1,
                        "is_active": "true",
                        **({"cursor": cursor} if cursor else {}),
                    },
                )
                assert page.status_code == 200, page.text
                ids.extend(row["id"] for row in page.json()["items"])
                cursor = page.json()["next_cursor"]
                if cursor is None:
                    break
            assert len(ids) == len(set(ids)) == 4 and ids == sorted(ids)
            cursor = client.get("/products?limit=1").json()["next_cursor"]
            assert (
                client.get(
                    "/products", params={"limit": 2, "cursor": cursor}
                ).status_code
                == 400
            )
            assert (
                client.get(
                    "/products", params={"limit": 1, "cursor": cursor + "x"}
                ).status_code
                == 400
            )
            checks.append("filtered_paging_and_cursor_rejection")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(lambda _: post({**body, "code": "CONCURRENT"}), range(2))
                )
            assert sorted(r.status_code for r in results) == [201, 409], [
                r.text for r in results
            ]
            checks.append("concurrent_same_code_only_one_product")
            same_key = str(uuid4())
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda _: post({**body, "code": "SAME_REQUEST"}, same_key),
                        range(2),
                    )
                )
            assert all(r.status_code == 201 for r in results), [r.text for r in results]
            assert results[0].json() == results[1].json()
            assert any(r.headers["idempotency-replayed"] == "true" for r in results)
            checks.append("concurrent_identical_request_replays_one_commit")
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(
                    pool.map(
                        lambda i: patch({"name": f"同時更新{i}"}, '"v3"'), range(2)
                    )
                )
            assert sorted(r.status_code for r in results) == [200, 412], [
                r.text for r in results
            ]
            assert client.get(path).json()["version"] == 4
            checks.append("concurrent_version_guard_and_atomic_request_record")
            reservation = repo.get(repo.key("PRODUCT_CODES", "CODE#COFFEE"))
            assert reservation["product_id"] == product["id"]
            original = repo.get(repo.key("REQUEST#local-admin", f"KEY#{key}"))
            assert (
                original["response_body"] == product
                and original["response_etag"] == '"v1"'
            )
            checks.append("strong_read_of_saved_first_response_and_reservation")
        with TestClient(
            create_app(
                Settings(
                    APP_ENV="test",
                    DYNAMODB_TABLE=table + "-missing",
                    AWS_ENDPOINT_URL="http://127.0.0.1:4566",
                    AWS_REGION="ap-northeast-1",
                )
            )
        ) as missing:
            response = missing.get("/products")
            assert (
                response.status_code == 503 and response.headers["retry-after"] == "1"
            )
            assert response.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"
        checks.append("missing_table_returns_safe_503")
    finally:
        if created:
            call(sdk, "delete_table", TableName=table)
            sdk.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
            )
        sdk.close()
    return {
        "check_count": len(checks),
        "checks": checks,
        "temporary_table_deleted": True,
        "http_transport": "TestClient in process",
        "database": "actual MiniStack",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
