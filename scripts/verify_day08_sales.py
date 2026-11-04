"""Sale registration against MiniStack, isolated in a newly created temporary table."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import ensure_table
from sales_manager_api.repository import DynamoRepository, call
from sales_manager_api.sale_routes import sale_service
from sales_manager_api.sales import SaleService
from sales_manager_api.settings import Settings


def verify() -> dict:
    table = f"sales-manager-test-day08-{uuid4().hex[:12]}"
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
        today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        app = create_app(settings)
        with TestClient(app) as client:

            def post(path, body, key=None):
                return client.post(
                    path,
                    json=body,
                    headers={"Idempotency-Key": key or str(uuid4())},
                )

            def product(code, name="コーヒー"):
                response = post(
                    "/products",
                    {
                        "code": code,
                        "name": name,
                        "default_unit_price_yen": 600,
                    },
                )
                assert response.status_code == 201, response.text
                return response.json()

            def edit(item, changes):
                response = client.patch(
                    f"/products/{item['id']}",
                    json=changes,
                    headers={
                        "Idempotency-Key": str(uuid4()),
                        "If-Match": f'"v{item["version"]}"',
                    },
                )
                assert response.status_code == 200, response.text
                return response.json()

            def snapshot_keys():
                keys, extra = set(), {}
                while True:
                    page = call(
                        sdk,
                        "scan",
                        TableName=table,
                        ConsistentRead=True,
                        ProjectionExpression="PK, SK",
                        **extra,
                    )
                    keys.update(
                        (item["PK"]["S"], item["SK"]["S"]) for item in page["Items"]
                    )
                    if not page.get("LastEvaluatedKey"):
                        return keys
                    extra = {"ExclusiveStartKey": page["LastEvaluatedKey"]}

            coffee, tea = product("COFFEE"), product("TEA", "紅茶")
            body = {
                "sale_date": today.isoformat(),
                "lines": [
                    {"product_id": coffee["id"], "unit_price_yen": 550, "quantity": 2},
                    {"product_id": tea["id"], "unit_price_yen": 330, "quantity": 1},
                ],
            }
            key = str(uuid4())
            before = snapshot_keys()
            response = post("/sales", body, key)
            assert response.status_code == 201, response.text
            sale = response.json()
            assert sale["total_amount_yen"] == 1430 and sale["version"] == 1
            assert response.headers["etag"] == '"v1"'
            assert response.headers["idempotency-replayed"] == "false"
            assert len(snapshot_keys() - before) == 4
            current = repo.get(repo.key(f"SALE#{sale['id']}", "CURRENT"))
            daily = repo.get(repo.key(f"DAY#{today.isoformat()}", f"SALE#{sale['id']}"))
            revision = repo.get(repo.key(f"SALE#{sale['id']}", "REV#0000000001"))
            assert {k: v for k, v in current.items() if k not in {"PK", "SK"}} == sale
            assert {k: v for k, v in daily.items() if k not in {"PK", "SK"}} == sale
            assert revision["after"] == sale and revision["before"] is None
            assert revision["actor_id"] == "local-admin"
            record = repo.get(repo.key("REQUEST#local-admin", f"KEY#{key}"))
            assert record["response_body"] == sale
            checks.append(
                "integer_amount_snapshots_current_day_revision_and_response_atomic"
            )

            coffee = edit(
                coffee,
                {"name": "改名後", "default_unit_price_yen": 999, "is_active": False},
            )
            before = snapshot_keys()
            repeated = post("/sales", body, key)
            assert repeated.status_code == 201 and repeated.json() == sale
            assert repeated.headers["idempotency-replayed"] == "true"
            assert snapshot_keys() == before
            assert (
                post(
                    "/sales",
                    {**body, "sale_date": (today - timedelta(days=1)).isoformat()},
                    key,
                ).status_code
                == 409
            )
            assert post("/sales", body).json()["error"]["code"] == "PRODUCT_INACTIVE"
            assert repo.get(repo.key(f"SALE#{sale['id']}", "CURRENT")) == current
            checks.append(
                "replay_survives_master_changes_and_original_snapshot_is_immutable"
            )

            valid = {**body, "lines": [body["lines"][1]]}
            before = snapshot_keys()
            future = post(
                "/sales",
                {**valid, "sale_date": (today + timedelta(days=1)).isoformat()},
            )
            assert (
                future.status_code == 422
                and future.json()["error"]["code"] == "FUTURE_SALE_DATE"
            )
            invalid_cases = [
                {**valid, "lines": []},
                {**valid, "total_amount_yen": 1},
                {**valid, "lines": [{**valid["lines"][0], "quantity": True}]},
                {**valid, "lines": [{**valid["lines"][0], "unit_price_yen": 1.0}]},
                {**valid, "lines": [{**valid["lines"][0], "product_id": str(uuid4())}]},
            ]
            for invalid in invalid_cases:
                assert post("/sales", invalid).status_code in {404, 422}
            assert snapshot_keys() == before
            checks.append("invalid_future_missing_product_no_partial_writes")

            boundary = {
                **valid,
                "lines": [
                    {
                        "product_id": tea["id"],
                        "unit_price_yen": 1000000,
                        "quantity": 9999,
                    },
                    {"product_id": tea["id"], "unit_price_yen": 999999, "quantity": 1},
                ],
            }
            exact = post("/sales", boundary)
            assert (
                exact.status_code == 201
                and exact.json()["total_amount_yen"] == 9999999999
            )
            before = snapshot_keys()
            boundary["lines"][1]["unit_price_yen"] += 1
            over = post("/sales", boundary)
            assert (
                over.status_code == 422
                and over.json()["error"]["code"] == "AMOUNT_LIMIT_EXCEEDED"
            )
            assert snapshot_keys() == before
            checks.append("exact_total_limit_and_one_yen_over")

            for changes, expected in [
                ({"name": "競合後"}, "PRODUCT_CHANGED"),
                ({"is_active": False}, "PRODUCT_INACTIVE"),
            ]:
                item = product("RACE-" + uuid4().hex[:8].upper())
                race_body = {
                    **valid,
                    "lines": [{**valid["lines"][0], "product_id": item["id"]}],
                }
                service = SaleService(repo)
                original = repo.transact

                def racing_write(writes):
                    edit(item, changes)
                    return original(writes)

                app.dependency_overrides[sale_service] = lambda: service
                before = snapshot_keys()
                with patch.object(repo, "transact", side_effect=racing_write):
                    failed = post("/sales", race_body)
                app.dependency_overrides.clear()
                assert (
                    failed.status_code == 409
                    and failed.json()["error"]["code"] == expected
                )
                # Only the product PATCH response record may have been added.
                added = snapshot_keys() - before
                assert len(added) == 1 and next(iter(added))[0].endswith(
                    "REQUEST#local-admin"
                )
            checks.append(
                "real_product_condition_checks_reject_updates_and_disabling_atomically"
            )

            before = snapshot_keys()
            same_key = str(uuid4())
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(
                    pool.map(lambda _: post("/sales", valid, same_key), range(2))
                )
            # A transaction in flight may yield a sanitized, retryable 503.
            for index, result in enumerate(responses):
                if result.status_code == 503:
                    assert result.headers["retry-after"] == "1"
                    responses[index] = post("/sales", valid, same_key)
            assert all(r.status_code == 201 for r in responses), [
                r.text for r in responses
            ]
            assert responses[0].json() == responses[1].json()
            assert len(snapshot_keys() - before) == 4
            checks.append("concurrent_same_request_commits_exactly_one_sale")

            before = snapshot_keys()
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: post("/sales", valid), range(2)))
            assert all(r.status_code == 201 for r in responses), [
                r.text for r in responses
            ]
            assert responses[0].json()["id"] != responses[1].json()["id"]
            assert len(snapshot_keys() - before) == 8
            checks.append("distinct_request_keys_create_distinct_sales")

            maximum_lines = []
            for i in range(50):
                item = product(f"MAX{i:02d}", "🌸" * 100)
                maximum_lines.append(
                    {"product_id": item["id"], "unit_price_yen": 0, "quantity": 9999}
                )
            maximum = post("/sales", {**valid, "lines": maximum_lines})
            assert maximum.status_code == 201, maximum.text
            assert (
                len(maximum.json()["lines"]) == 50
                and maximum.json()["total_amount_yen"] == 0
            )
            checks.append("fifty_distinct_unicode_products_54_transaction_actions")

            before = snapshot_keys()
            # The injected clock isolates JST midnight without changing machine time.
            boundary_service = SaleService(
                repo, clock=lambda: datetime(2026, 11, 1, 14, 59, 59, tzinfo=UTC)
            )
            app.dependency_overrides[sale_service] = lambda: boundary_service
            midnight_body = {**valid, "sale_date": "2026-11-02"}
            assert post("/sales", midnight_body).status_code == 422
            boundary_service.clock = lambda: datetime(2026, 11, 1, 15, tzinfo=UTC)
            assert post("/sales", midnight_body).status_code == 201
            app.dependency_overrides.clear()
            assert len(snapshot_keys() - before) == 4
            checks.append("jst_midnight_with_fixed_test_clock")

        with TestClient(create_app(settings)) as restarted:
            replay = restarted.post(
                "/sales", json=body, headers={"Idempotency-Key": key}
            )
            assert replay.status_code == 201 and replay.json() == sale
            assert replay.headers["idempotency-replayed"] == "true"
        checks.append("first_response_survives_api_app_recreation")
        return {
            "backend": "MiniStack",
            "check_count": len(checks),
            "checks": checks,
            "temporary_table_deleted": True,
        }
    finally:
        if created:
            call(sdk, "delete_table", TableName=table)
            sdk.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 15}
            )
        sdk.close()


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
