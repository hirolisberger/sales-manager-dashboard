"""Sale correction/cancellation/history against an isolated real MiniStack table."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from sales_manager_api.app import create_app
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import ensure_table
from sales_manager_api.errors import ApplicationError
from sales_manager_api.repository import DynamoRepository, StorageError, Write, call
from sales_manager_api.sale_models import SalePatch
from sales_manager_api.sales import SaleService
from sales_manager_api.settings import Settings


def verify():
    table = "sales-manager-test-day10-" + uuid4().hex[:12]
    settings = Settings(
        APP_ENV="test",
        AWS_REGION="ap-northeast-1",
        AWS_ENDPOINT_URL="http://127.0.0.1:4566",
        DYNAMODB_TABLE=table,
        STORE_ID="demo",
    )
    sdk, created, checks = dynamodb_client(settings), False, []
    schema = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1] / "docs/contracts/openapi.yaml"
        ).read_text()
    )

    def validate(name, body):
        Draft202012Validator(
            {
                "components": schema["components"],
                "$ref": "#/components/schemas/" + name,
            },
            format_checker=FormatChecker(),
        ).validate(body)

    try:
        assert ensure_table(sdk, settings), "Unexpected existing verification table"
        created = True
        repo = DynamoRepository(sdk, table, "demo")
        day = datetime.now(ZoneInfo("Asia/Tokyo")).date() - timedelta(days=1)
        old_day = day - timedelta(days=1)
        app = create_app(settings)
        with TestClient(app) as client:

            def post(path, body, key=None):
                result = client.post(
                    path, json=body, headers={"Idempotency-Key": key or str(uuid4())}
                )
                assert result.status_code == 201, result.text
                return result.json()

            def change(sale, body=None, *, cancel=False, key=None):
                headers = {
                    "Idempotency-Key": key or str(uuid4()),
                    "If-Match": f'"v{sale["version"]}"',
                }
                path = "/sales/" + sale["id"] + ("/cancel" if cancel else "")
                return client.request(
                    "POST" if cancel else "PATCH", path, json=body, headers=headers
                )

            def patch_body(sale, **updates):
                return {
                    "sale_date": sale["sale_date"],
                    "reason": "数量と計上日を訂正",
                    "lines": [
                        {
                            k: line[k]
                            for k in [
                                "line_id",
                                "product_id",
                                "unit_price_yen",
                                "quantity",
                            ]
                        }
                        for line in sale["lines"]
                    ],
                    **updates,
                }

            product = post(
                "/products",
                {"code": "COFFEE", "name": "コーヒー", "default_unit_price_yen": 550},
            )

            def new_sale(key=None):
                return post(
                    "/sales",
                    {
                        "sale_date": str(day),
                        "lines": [
                            {
                                "product_id": product["id"],
                                "unit_price_yen": 550,
                                "quantity": 2,
                            }
                        ],
                    },
                    key,
                )

            create_key = str(uuid4())
            first = new_sale(create_key)
            body = patch_body(first, sale_date=str(old_day))
            body["lines"][0]["quantity"] = 1
            patch_key = str(uuid4())
            result = change(first, body, key=patch_key)
            assert result.status_code == 200, result.text
            second = result.json()
            validate("Sale", second)
            assert second["version"] == 2 and second["total_amount_yen"] == 550
            assert second["created_at"] == first["created_at"]
            assert repo.get(repo.key("DAY#" + str(day), "SALE#" + first["id"])) is None
            assert (
                repo.get(repo.key("DAY#" + str(old_day), "SALE#" + first["id"]))[
                    "version"
                ]
                == 2
            )
            assert (
                client.get(
                    "/sales", params={"start_date": str(day), "end_date": str(day)}
                ).json()["items"]
                == []
            )
            checks.append(
                "correction_atomically_moves_day_copy_and_recalculates_amount"
            )

            cancel_key = str(uuid4())
            result = change(
                second, {"reason": "二重入力の取消"}, cancel=True, key=cancel_key
            )
            assert result.status_code == 200 and result.headers["etag"] == '"v3"', (
                result.text
            )
            stopped = result.json()
            assert (
                stopped["status"] == "cancelled" and stopped["lines"] == second["lines"]
            )
            assert stopped["total_amount_yen"] == 550
            for status, count in [("confirmed", 0), ("cancelled", 1), ("all", 1)]:
                page = client.get(
                    "/sales",
                    params={
                        "start_date": str(old_day),
                        "end_date": str(old_day),
                        "status": status,
                    },
                ).json()
                assert len(page["items"]) == count
            assert change(stopped, patch_body(stopped)).status_code == 409
            assert change(second, {"reason": "再取消"}, cancel=True).status_code == 412
            checks.append(
                "cancellation_preserves_amount_excludes_confirmed_and_is_terminal"
            )

            page = client.get("/sales/" + first["id"] + "/revisions").json()
            validate("RevisionPage", page)
            assert [r["operation"] for r in page["items"]] == [
                "created",
                "corrected",
                "cancelled",
            ]
            assert [r["after"] for r in page["items"]] == [first, second, stopped]
            assert [r["before"] for r in page["items"]] == [None, first, second]
            assert all(r["actor_id"] == "local-admin" for r in page["items"])
            assert page["items"][1]["reason"] == body["reason"]
            checks.append(
                "immutable_before_after_reason_actor_and_yaml_response_shapes"
            )

            for replay, expected, status in [
                (
                    client.post(
                        "/sales",
                        json={
                            "sale_date": str(day),
                            "lines": [
                                {
                                    "product_id": product["id"],
                                    "unit_price_yen": 550,
                                    "quantity": 2,
                                }
                            ],
                        },
                        headers={"Idempotency-Key": create_key},
                    ),
                    first,
                    201,
                ),
                (change(first, body, key=patch_key), second, 200),
                (
                    change(
                        second,
                        {"reason": "二重入力の取消"},
                        cancel=True,
                        key=cancel_key,
                    ),
                    stopped,
                    200,
                ),
            ]:
                assert replay.status_code == status and replay.json() == expected
                assert replay.headers["idempotency-replayed"] == "true"
                assert replay.headers["etag"] == f'"v{expected["version"]}"'
            assert (
                change(first, {**body, "reason": "別の理由"}, key=patch_key).status_code
                == 409
            )
            assert (
                len(client.get("/sales/" + first["id"] + "/revisions").json()["items"])
                == 3
            )
            checks.append(
                "replays_keep_original_status_etag_body_even_after_cancellation"
            )

            other_sale = new_sale()
            response = client.patch(
                "/products/" + product["id"],
                json={"name": "改名後", "is_active": False},
                headers={"Idempotency-Key": str(uuid4()), "If-Match": '"v1"'},
            )
            assert response.status_code == 200
            result = change(other_sale, patch_body(other_sale))
            assert (
                result.status_code == 200
                and result.json()["lines"][0]["product_name"] == "コーヒー"
            )
            current = result.json()
            refresh = patch_body(current)
            refresh["lines"][0]["refresh_product_snapshot"] = True
            assert change(current, refresh).status_code == 409
            response = client.patch(
                "/products/" + product["id"],
                json={"is_active": True, "default_unit_price_yen": 999},
                headers={"Idempotency-Key": str(uuid4()), "If-Match": '"v2"'},
            )
            assert response.status_code == 200
            result = change(current, refresh)
            assert result.status_code == 200
            assert result.json()["lines"][0]["product_name"] == "改名後"
            assert result.json()["lines"][0]["unit_price_yen"] == 550
            checks.append(
                "inactive_snapshot_preserved_refresh_requires_active_actual_price_preserved"
            )

            cursor = None
            versions = []
            token = None
            for _ in range(10):
                page = client.get(
                    "/sales/" + first["id"] + "/revisions",
                    params={"limit": 1, **({"cursor": cursor} if cursor else {})},
                ).json()
                versions.extend(r["version"] for r in page["items"])
                cursor = page["next_cursor"]
                token = token or cursor
                if cursor is None:
                    break
            assert versions == [1, 2, 3] and cursor is None
            history_path = "/sales/" + first["id"] + "/revisions"
            for path, params in [
                (history_path, {"limit": 2, "cursor": token}),
                (history_path, {"limit": 1, "cursor": token + "x"}),
                (
                    "/sales/" + other_sale["id"] + "/revisions",
                    {"limit": 1, "cursor": token},
                ),
            ]:
                assert client.get(path, params=params).status_code == 400
            checks.append("history_pagination_and_signed_sale_limit_scopes")

            with TestClient(create_app(settings)) as restarted:
                assert (
                    restarted.get(history_path).json()["items"]
                    == client.get(history_path).json()["items"]
                )
                assert (
                    restarted.get(
                        history_path, params={"limit": 1, "cursor": token}
                    ).status_code
                    == 400
                )
            with TestClient(
                create_app(settings.model_copy(update={"store_id": "other"}))
            ) as other:
                assert other.get(history_path).status_code == 404
                assert change(stopped, {"reason": "x"}, cancel=True).status_code == 409
                assert (
                    other.patch(
                        "/sales/" + first["id"],
                        json=body,
                        headers={"Idempotency-Key": str(uuid4()), "If-Match": '"v1"'},
                    ).status_code
                    == 404
                )
            checks.append(
                "api_recreation_preserves_history_invalidates_cursor_and_store_isolation"
            )

            # Missing day copy must fail atomically, without a partial new CURRENT/REV.
            broken = new_sale()
            repo.transact(
                [
                    Write(
                        "delete",
                        repo.key("DAY#" + str(day), "SALE#" + broken["id"]),
                        "attribute_exists(PK)",
                    )
                ]
            )
            result = change(broken, patch_body(broken, sale_date=str(old_day)))
            assert result.status_code == 503 and result.headers["retry-after"] == "1"
            assert client.get("/sales/" + broken["id"]).json() == broken
            assert (
                len(client.get("/sales/" + broken["id"] + "/revisions").json()["items"])
                == 1
            )
            assert (
                repo.get(repo.key("DAY#" + str(old_day), "SALE#" + broken["id"]))
                is None
            )
            checks.append(
                "conditional_failure_rolls_back_current_history_request_and_day_move"
            )

            # Interleave a real product write after reading the master.
            racing = new_sale()
            service = SaleService(repo)
            original_transact = repo.transact

            def product_race(writes):
                repo.transact = original_transact
                response = client.patch(
                    "/products/" + product["id"],
                    json={"name": "競合後"},
                    headers={"Idempotency-Key": str(uuid4()), "If-Match": '"v3"'},
                )
                assert response.status_code == 200
                original_transact(writes)

            repo.transact = product_race
            refresh = patch_body(racing, sale_date=str(old_day))
            refresh["lines"][0]["refresh_product_snapshot"] = True
            try:
                service.patch(
                    racing["id"],
                    SalePatch.model_validate(refresh),
                    str(uuid4()),
                    '"v1"',
                )
                raise AssertionError("Product race accepted")
            except ApplicationError as error:
                assert error.code == "PRODUCT_CHANGED"
            assert client.get("/sales/" + racing["id"]).json() == racing
            checks.append("real_product_version_condition_rejects_snapshot_race")

            # Two writers read the same version and enter real transactions together.
            for same_key in [False, True]:
                racing = new_sale()
                barrier = Barrier(2, timeout=15)
                common_key = str(uuid4())
                body = SalePatch.model_validate(patch_body(racing))

                def writer():
                    local_sdk = dynamodb_client(settings)
                    try:
                        local_repo = DynamoRepository(local_sdk, table, "demo")
                        transact = local_repo.transact

                        def synchronized(writes):
                            barrier.wait()
                            transact(writes)

                        local_repo.transact = synchronized
                        key = common_key if same_key else str(uuid4())
                        service = SaleService(local_repo)
                        try:
                            result = service.patch(racing["id"], body, key, '"v1"')
                            return result.status, result.replayed
                        except ApplicationError, StorageError:
                            # A transient DB conflict may precede the winning commit.
                            local_repo.transact = transact
                            try:
                                result = service.patch(racing["id"], body, key, '"v1"')
                                return result.status, result.replayed
                            except ApplicationError as retry_error:
                                return retry_error.status_code, False
                    finally:
                        local_sdk.close()

                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(writer) for _ in range(2)]
                    results = [future.result() for future in futures]
                assert sorted(status for status, _ in results) == (
                    [200, 200] if same_key else [200, 412]
                ), results
                if same_key:
                    assert sorted(replayed for _, replayed in results) == [False, True]
                assert (
                    len(
                        client.get("/sales/" + racing["id"] + "/revisions").json()[
                            "items"
                        ]
                    )
                    == 2
                )
            checks.append(
                "concurrent_transactions_one_revision_different_key_412_same_key_replay"
            )

            # Worst case: date move + 50 distinct refreshed/new product guards = 55.
            products = [
                post(
                    "/products",
                    {
                        "code": f"P{i:02d}",
                        "name": "架空商品" * 25,
                        "default_unit_price_yen": 1,
                    },
                )
                for i in range(50)
            ]
            large = new_sale()
            large_body = {
                "sale_date": str(old_day),
                "reason": "50種類の商品へ訂正",
                "lines": [
                    {"product_id": p["id"], "unit_price_yen": 1, "quantity": 1}
                    for p in products
                ],
            }
            result = change(large, large_body)
            assert result.status_code == 200, result.text
            assert (
                len(result.json()["lines"]) == 50
                and result.json()["total_amount_yen"] == 50
            )
            assert (
                len(client.get("/sales/" + large["id"] + "/revisions").json()["items"])
                == 2
            )
            checks.append(
                "maximum_50_distinct_products_date_move_55_transaction_actions"
            )

            valid = new_sale()
            for invalid in [
                patch_body(valid, reason=" "),
                patch_body(valid, sale_date=str(day + timedelta(days=2))),
                patch_body(valid, lines=[]),
            ]:
                assert change(valid, invalid).status_code == 422
            assert (
                client.patch(
                    "/sales/" + valid["id"],
                    json=patch_body(valid),
                    headers={"Idempotency-Key": str(uuid4())},
                ).status_code
                == 428
            )
            assert client.get("/sales/" + valid["id"]).json() == valid
            checks.append(
                "invalid_reason_future_empty_lines_and_missing_precondition_do_not_write"
            )
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
