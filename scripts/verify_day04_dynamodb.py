"""Day 4 access-pattern experiment against MiniStack only; deletes its own table."""

import copy
import json
from uuid import uuid4

from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from day04_design import (
    FIXTURES,
    STORE,
    calculate_sale,
    cancel,
    correction_request,
    initial_sales,
    key,
    product_key,
    request_key,
    selected_rows,
    totals,
    wire,
    write_plan,
)
from verify_local_aws import DEFAULT_ENDPOINT, local_client, local_session

DESERIALIZER = TypeDeserializer()


def plain(item):
    return {name: DESERIALIZER.deserialize(value) for name, value in item.items()}


def verify():
    client = local_client(local_session(), "dynamodb", DEFAULT_ENDPOINT)
    table = f"day04-design-{uuid4().hex[:12]}"
    created = False
    checks = []

    def get(item_key):
        response = client.get_item(
            TableName=table, Key=wire(item_key), ConsistentRead=True
        )
        return plain(response["Item"]) if "Item" in response else None

    def transact(actions):
        client.transact_write_items(TransactItems=actions)

    def rejected(actions):
        try:
            transact(actions)
        except ClientError as exc:
            assert exc.response["Error"]["Code"] == "TransactionCanceledException"
        else:
            raise AssertionError("A conditional transaction unexpectedly succeeded")

    def query_day(day, confirmed_only=False):
        arguments = {
            "TableName": table,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
            "ExpressionAttributeValues": wire(
                {":pk": f"{STORE}#DAY#{day}", ":prefix": "SALE#"}
            ),
            "ConsistentRead": True,
            "ScanIndexForward": False,
            "Limit": 1,
        }
        if confirmed_only:
            arguments.update(
                FilterExpression="#state = :state",
                ExpressionAttributeNames={"#state": "status"},
            )
            arguments["ExpressionAttributeValues"][":state"] = {"S": "confirmed"}
        rows, empty_continuations = [], 0
        while True:
            response = client.query(**arguments)
            rows.extend(plain(item) for item in response["Items"])
            continuation = response.get("LastEvaluatedKey")
            if not continuation:
                return rows, empty_continuations
            if not response["Items"]:
                empty_continuations += 1
            arguments["ExclusiveStartKey"] = continuation

    try:
        client.create_table(
            TableName=table,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK")
            ],
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
        )
        created = True
        client.get_waiter("table_exists").wait(
            TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 15}
        )
        products, sales = initial_sales()
        for product in products.values():
            code_key = {"PK": f"{STORE}#PRODUCT_CODES", "SK": f"CODE#{product['code']}"}
            transact(
                [
                    {
                        "Put": {
                            "TableName": table,
                            "Item": wire({**product_key(product["id"]), **product}),
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                    {
                        "Put": {
                            "TableName": table,
                            "Item": wire({**code_key, "product_id": product["id"]}),
                            "ConditionExpression": "attribute_not_exists(PK)",
                        }
                    },
                ]
            )
        first = next(iter(products.values()))
        fake_id = str(uuid4())
        rejected(
            [
                {
                    "Put": {
                        "TableName": table,
                        "Item": wire(
                            {**product_key(fake_id), **{**first, "id": fake_id}}
                        ),
                    }
                },
                {
                    "Put": {
                        "TableName": table,
                        "Item": wire(
                            {
                                "PK": f"{STORE}#PRODUCT_CODES",
                                "SK": f"CODE#{first['code']}",
                            }
                        ),
                        "ConditionExpression": "attribute_not_exists(PK)",
                    }
                },
            ]
        )
        assert get(product_key(fake_id)) is None
        checks.append("product_code_uniqueness_and_rollback")

        initial = copy.deepcopy(sales)
        for number, sale in enumerate(sales):
            guards = [products[line["product_id"]] for line in sale["lines"]]
            transact(write_plan(table, sale, None, f"create-{number}", guards))
        checks.append("atomic_create_with_product_guards")

        # Master changes must not rewrite historical snapshots, even if disabled.
        first.update(
            name="変更後の商品名",
            default_unit_price_yen=600,
            is_active=False,
            version=2,
        )
        client.put_item(
            TableName=table, Item=wire({**product_key(first["id"]), **first})
        )
        sales[0] = calculate_sale(
            sales[0]["id"], correction_request(sales[0]), products, sales[0]
        )
        transact(write_plan(table, sales[0], initial[0], "correct-s1"))
        assert sales[0]["lines"][0]["product_name"] == "コーヒー"
        before_cancel = sales[1]
        sales[1] = cancel(before_cancel)
        transact(write_plan(table, sales[1], before_cancel, "cancel-s2"))
        stored = query_day("2026-12-01", True)
        assert len(stored[0]) == 1 and stored[1] >= 1
        december = stored[0] + query_day("2026-12-02", True)[0]
        rows = selected_rows(december, "2026-12-01", "2026-12-31")
        assert totals(rows) == {"amount_yen": 1430, "quantity": 3, "sale_count": 2}
        tea_rows = selected_rows(
            december, "2026-12-01", "2026-12-31", FIXTURES["ids"]["tea"]
        )
        assert totals(tea_rows)["amount_yen"] == 330 and len(rows) == 3
        checks.extend(
            [
                "preserved_snapshots_and_cancelled_exclusion",
                "empty_filtered_page_continues",
                "strong_queries_totals_and_line_selection",
            ]
        )

        # Persistent request record preserves the FIRST response after later edits.
        original_response = get(request_key("create-0"))
        assert original_response["response_body"]["total_amount_yen"] == 1430
        assert original_response["response_etag"] == '"v1"'
        assert get(key(sales[0]))["total_amount_yen"] == 880
        duplicate = calculate_sale(
            str(uuid4()),
            FIXTURES["sales"][0]["request"],
            {p["id"]: p for p in FIXTURES["products"]},
        )
        rejected(write_plan(table, duplicate, None, "create-0"))
        assert get(key(duplicate)) is None and get(key(duplicate, True)) is None
        assert get({"PK": key(duplicate)["PK"], "SK": "REV#0000000001"}) is None
        assert get(request_key("create-0")) == original_response
        checks.append("durable_original_response_and_duplicate_rollback")

        # A product that changed between read and commit must abort all sale writes.
        stale_products = {p["id"]: p for p in FIXTURES["products"]}
        stale_sale = calculate_sale(
            str(uuid4()), FIXTURES["sales"][0]["request"], stale_products
        )
        rejected(
            write_plan(
                table, stale_sale, None, "stale-product", [stale_products[first["id"]]]
            )
        )
        assert (
            get(key(stale_sale)) is None and get(request_key("stale-product")) is None
        )
        assert get(key(stale_sale, True)) is None
        assert get({"PK": key(stale_sale)["PK"], "SK": "REV#0000000001"}) is None
        checks.append("product_version_and_active_guard_rollback")

        moved = calculate_sale(
            sales[0]["id"],
            correction_request(sales[0], "2027-01-01"),
            products,
            sales[0],
        )
        transact(write_plan(table, moved, sales[0], "move-s1"))
        assert get(key(sales[0], True)) is None
        assert get(key(moved, True))["total_amount_yen"] == 880
        dec = query_day("2026-12-01", True)[0] + query_day("2026-12-02", True)[0]
        assert (
            totals(selected_rows(dec, "2026-12-01", "2026-12-31"))["amount_yen"] == 550
        )
        assert (
            totals(
                selected_rows(
                    query_day("2027-01-01", True)[0], "2027-01-01", "2027-01-31"
                )
            )["amount_yen"]
            == 880
        )
        checks.append("atomic_date_move_between_months")

        stale = copy.deepcopy(sales[0])
        stale.update(version=3, total_amount_yen=999)
        rejected(write_plan(table, stale, sales[0], "stale-version"))
        assert get(key(moved))["sale_date"] == "2027-01-01"
        assert (
            get(key(stale, True)) is None and get(request_key("stale-version")) is None
        )
        history = client.query(
            TableName=table,
            ConsistentRead=True,
            KeyConditionExpression="PK = :pk AND begins_with(SK, :prefix)",
            ExpressionAttributeValues=wire(
                {":pk": key(moved)["PK"], ":prefix": "REV#"}
            ),
        )["Items"]
        assert [int(plain(item)["version"]) for item in history] == [1, 2, 3]
        assert plain(history[-1])["after"]["sale_date"] == "2027-01-01"
        assert plain(history[-1])["after"]["total_amount_yen"] == 880
        assert get(key(moved))["total_amount_yen"] == 880
        checks.append("stale_sale_version_rollback_and_immutable_history")

        # Exercise the largest planned action count with 50 DISTINCT product guards.
        expanded = {}
        lines = []
        for _ in range(50):
            product = {
                "id": str(uuid4()),
                "code": "A" * 32,
                "name": "𠮷" * 100,
                "default_unit_price_yen": 1,
                "is_active": True,
                "version": 1,
            }
            expanded[product["id"]] = product
            client.put_item(
                TableName=table, Item=wire({**product_key(product["id"]), **product})
            )
            lines.append(
                {"product_id": product["id"], "unit_price_yen": 1, "quantity": 1}
            )
        large = calculate_sale(
            str(uuid4()), {"sale_date": "2026-12-03", "lines": lines}, expanded
        )
        guards = list(expanded.values())
        create_actions = write_plan(table, large, None, "large-create", guards)
        assert len(create_actions) == 54
        transact(create_actions)
        request = correction_request(large, "2027-01-02")
        for line in request["lines"]:
            line["refresh_product_snapshot"] = True
        large_moved = calculate_sale(large["id"], request, expanded, large)
        move_actions = write_plan(table, large_moved, large, "large-move", guards)
        assert len(move_actions) == 55
        transact(move_actions)
        assert get(key(large, True)) is None
        assert len(get(key(large_moved))["lines"]) == 50
        checks.append("fifty_distinct_products_54_and_55_action_transactions")
    finally:
        if created:
            client.delete_table(TableName=table)
            client.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 15}
            )
    return {
        "endpoint": DEFAULT_ENDPOINT,
        "checks": checks,
        "check_count": len(checks),
        "temporary_table_deleted": created,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
