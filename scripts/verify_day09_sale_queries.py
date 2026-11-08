"""Sale search/detail against MiniStack, confined to a fresh temporary table."""

import json
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sales_manager_api.app import create_app
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import ensure_table
from sales_manager_api.repository import DynamoRepository, Write, call
from sales_manager_api.settings import Settings


def verify():
    table = "sales-manager-test-day09-" + uuid4().hex[:12]
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
        end = today - timedelta(days=1)
        start = end - timedelta(days=3)
        params = {"start_date": str(start), "end_date": str(end)}
        app = create_app(settings)
        with TestClient(app) as client:

            def post(path, body):
                response = client.post(
                    path, json=body, headers={"Idempotency-Key": str(uuid4())}
                )
                assert response.status_code == 201, response.text
                return response.json()

            coffee, tea = [
                post(
                    "/products",
                    {"code": code, "name": name, "default_unit_price_yen": price},
                )
                for code, name, price in [
                    ("COFFEE", "コーヒー", 550),
                    ("TEA", "紅茶", 330),
                ]
            ]

            def sale(day, product=coffee):
                lines = [
                    {
                        "product_id": product["id"],
                        "unit_price_yen": product["default_unit_price_yen"],
                        "quantity": 2,
                    }
                ]
                if product == coffee:
                    lines.append(
                        {"product_id": tea["id"], "unit_price_yen": 330, "quantity": 1}
                    )
                return post("/sales", {"sale_date": str(day), "lines": lines})

            sales = [
                sale(start),
                sale(start + timedelta(days=1), tea),
                sale(end),
                sale(end),
            ]
            sale(start - timedelta(days=1))
            sale(today)
            response = client.get("/sales", params=params)
            assert response.status_code == 200, response.text
            expected = sorted(
                sales, key=lambda item: (item["sale_date"], item["id"]), reverse=True
            )
            assert [row["id"] for row in response.json()["items"]] == [
                s["id"] for s in expected
            ]
            assert response.json()["next_cursor"] is None
            checks.append("inclusive_period_bounds_and_descending_day_uuid_order")

            for limit in [1, 2, 3]:
                ids = []
                cursor = None
                for _ in range(20):
                    page = client.get(
                        "/sales",
                        params={
                            **params,
                            "limit": limit,
                            **({"cursor": cursor} if cursor else {}),
                        },
                    )
                    assert page.status_code == 200, page.text
                    ids.extend(row["id"] for row in page.json()["items"])
                    cursor = page.json()["next_cursor"]
                    if cursor is None:
                        break
                else:
                    raise AssertionError("Pagination failed to terminate")
                assert (
                    ids == [s["id"] for s in expected]
                    and len(ids) == len(set(ids)) == 4
                )
            checks.append("all_limits_cross_dates_without_duplicates_or_missing_sales")

            filtered = client.get(
                "/sales", params={**params, "product_id": tea["id"]}
            ).json()["items"]
            assert len(filtered) == 4
            for row in filtered:
                assert "lines" not in row
                assert row["matched_amount_yen"] == (
                    660 if row["id"] == sales[1]["id"] else 330
                )
                assert row["total_amount_yen"] == (
                    660 if row["id"] == sales[1]["id"] else 1430
                )
            assert (
                client.get(
                    "/sales", params={**params, "product_id": str(uuid4())}
                ).json()["items"]
                == []
            )
            checks.append("matched_line_amounts_quantities_and_unknown_product_empty")

            original = sales[0]
            detail = client.get("/sales/" + original["id"])
            assert (
                detail.status_code == 200
                and detail.json() == original
                and detail.headers["etag"] == '"v1"'
            )
            edited = client.patch(
                "/products/" + coffee["id"],
                json={"name": "改名後", "is_active": False},
                headers={"Idempotency-Key": str(uuid4()), "If-Match": '"v1"'},
            )
            assert edited.status_code == 200
            assert client.get("/sales/" + original["id"]).json() == original
            assert (
                len(
                    client.get(
                        "/sales", params={**params, "product_id": coffee["id"]}
                    ).json()["items"]
                )
                == 3
            )
            checks.append("detail_all_lines_etag_and_snapshots_survive_master_changes")

            # Artificial cancelled fixture; cancellation API is implemented in Day 10.
            cancelled = {**original, "status": "cancelled", "version": 2}
            repo.transact(
                [
                    Write(
                        "put",
                        {**key, **cancelled},
                        "#v = :v",
                        {"#v": "version"},
                        {":v": 1},
                    )
                    for key in [
                        repo.key("SALE#" + original["id"], "CURRENT"),
                        repo.key(
                            "DAY#" + original["sale_date"], "SALE#" + original["id"]
                        ),
                    ]
                ]
            )
            for status, count in [("all", 4), ("confirmed", 3), ("cancelled", 1)]:
                assert (
                    len(
                        client.get(
                            "/sales", params={**params, "status": status}
                        ).json()["items"]
                    )
                    == count
                )
            assert client.get("/sales/" + original["id"]).headers["etag"] == '"v2"'
            checks.append(
                "synthetic_cancelled_fixture_status_filter_and_current_detail"
            )

            token = client.get("/sales", params={**params, "limit": 1}).json()[
                "next_cursor"
            ]
            for changes in [
                {"limit": 2},
                {"status": "confirmed"},
                {"product_id": tea["id"]},
                {"end_date": str(today)},
                {"cursor": token + "x"},
            ]:
                rejected = client.get(
                    "/sales", params={**params, "limit": 1, "cursor": token, **changes}
                )
                assert (
                    rejected.status_code == 400
                    and rejected.json()["error"]["code"] == "INVALID_CURSOR"
                )
            checks.append("signed_cursor_rejects_tampering_and_changed_conditions")

            invalid = [
                {},
                {"start_date": str(start)},
                {**params, "limit": "1.0"},
                {**params, "end_date": str(start - timedelta(days=1))},
                {**params, "end_date": "9999-12-31"},
                {**params, "unknown": "value"},
            ]
            for query in invalid:
                assert client.get("/sales", params=query).status_code == 422
            assert client.get("/sales/not-a-uuid").status_code == 422
            assert (
                client.get("/sales/" + str(uuid4())).json()["error"]["code"]
                == "SALE_NOT_FOUND"
            )
            checks.append("invalid_periods_queries_and_missing_detail")

            future_start = today + timedelta(days=1)
            empty = client.get(
                "/sales",
                params={
                    "start_date": str(future_start),
                    "end_date": str(future_start + timedelta(days=365)),
                },
            )
            assert empty.status_code == 200 and empty.json() == {
                "items": [],
                "next_cursor": None,
            }
            too_long = client.get(
                "/sales",
                params={
                    "start_date": str(future_start),
                    "end_date": str(future_start + timedelta(days=366)),
                },
            )
            assert too_long.json()["error"]["code"] == "PERIOD_TOO_LONG"
            checks.append("empty_future_366_days_allowed_and_367_days_rejected")

        with TestClient(create_app(settings)) as restarted:
            assert (
                restarted.get(
                    "/sales", params={**params, "limit": 1, "cursor": token}
                ).status_code
                == 400
            )
            assert (
                restarted.get("/sales/" + original["id"]).json()["status"]
                == "cancelled"
            )
        checks.append("api_recreation_invalidates_cursor_but_preserves_stored_sales")
        with TestClient(
            create_app(settings.model_copy(update={"store_id": "other-store"}))
        ) as other:
            assert other.get("/sales", params=params).json()["items"] == []
            assert other.get("/sales/" + original["id"]).status_code == 404
        checks.append("cross_store_list_and_detail_isolation")
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
