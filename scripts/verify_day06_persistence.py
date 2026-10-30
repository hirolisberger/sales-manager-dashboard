"""Exercise the actual app repository against disposable MiniStack tables only."""

import argparse
import json
import re
from uuid import uuid4

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import (
    demo_items,
    ensure_table,
    inspect_products,
    reset_table,
    seed_demo,
)
from sales_manager_api.repository import DynamoRepository, StorageConflict, Write, call
from sales_manager_api.settings import Settings


def verify(table: str, keep: bool = False) -> dict:
    if not re.fullmatch(r"sales-manager-test-day06-[a-z0-9-]+", table):
        raise ValueError("Use a new sales-manager-test-day06-* table")
    settings = Settings(
        APP_ENV="test",
        AWS_REGION="ap-northeast-1",
        AWS_ENDPOINT_URL="http://127.0.0.1:4566",
        DYNAMODB_TABLE=table,
        STORE_ID="demo",
    )
    client = dynamodb_client(settings)
    repo = DynamoRepository(client, table, "demo")
    created, success, checks = False, False, []
    try:
        if not ensure_table(client, settings):
            raise ValueError("The verification table already exists; choose a new name")
        created = True
        assert ensure_table(client, settings) is False
        checks.append("repeatable_table_initialization")
        assert seed_demo(repo) is True and seed_demo(repo) is False
        checks.append("atomic_seed_and_repeat_without_overwrite")
        products = inspect_products(repo)
        assert [row["code"] for row in products] == ["COFFEE", "TEA"]
        assert [row["default_unit_price_yen"] for row in products] == [550, 330]
        assert all(
            type(row["version"]) is int and row["is_active"] is True for row in products
        )
        checks.append("strong_read_integer_and_boolean_roundtrip")
        page = repo.query_page("PRODUCTS", "PRODUCT#", limit=1)
        assert len(page.items) == 1 and page.last_key is not None
        next_page = repo.query_page(
            "PRODUCTS", "PRODUCT#", limit=1, last_key=page.last_key
        )
        assert [*page.items, *next_page.items] == products
        checks.append("query_paging_without_duplicate_or_missing_items")
        other = DynamoRepository(client, table, "other")
        assert inspect_products(other) == []
        checks.append("store_partition_isolation")

        first = products[0]
        fake = {**first, **repo.key("PRODUCTS", "PRODUCT#duplicate")}
        reservation = demo_items(repo)[2]
        try:
            repo.transact(
                [
                    Write("put", fake, "attribute_not_exists(PK)"),
                    Write("put", reservation, "attribute_not_exists(PK)"),
                ]
            )
        except StorageConflict:
            pass
        else:
            raise AssertionError("Duplicate code reservation was accepted")
        assert repo.get(fake) is None
        checks.append("conditional_transaction_rolls_back_all_items")

        changed = {**first, "version": 2, "default_unit_price_yen": 600}
        repo.transact([Write("put", changed, "#v = :v", {"#v": "version"}, {":v": 1})])
        assert repo.get(first) == changed
        try:
            repo.transact(
                [
                    Write("check", first, "#v = :v", {"#v": "version"}, {":v": 1}),
                    Write("put", fake, "attribute_not_exists(PK)"),
                ]
            )
        except StorageConflict:
            pass
        else:
            raise AssertionError("Stale version guard was ignored")
        assert repo.get(fake) is None and repo.get(first) == changed
        checks.append("conditional_update_and_stale_guard_rollback")
        try:
            seed_demo(repo)
        except StorageConflict:
            pass
        else:
            raise AssertionError("Edited demo data was overwritten")
        assert repo.get(first) == changed
        checks.append("seed_refuses_edited_data")

        try:
            reset_table(client, settings, "wrong-table")
        except ValueError:
            pass
        else:
            raise AssertionError("Reset did not require exact confirmation")
        assert repo.get(first) == changed
        checks.append("reset_confirmation_prevents_deletion")
        reset_table(client, settings, table)
        assert inspect_products(repo) == []
        assert all(repo.get(item) is None for item in demo_items(repo))
        assert seed_demo(repo) is True
        checks.append("reset_to_empty_and_seed_again")
        success = True
        return {
            "table": table,
            "checks": checks,
            "check_count": len(checks),
            "temporary_table_deleted": not keep,
            "retained_for_restart_check": keep,
        }
    finally:
        if created and not (keep and success):
            call(client, "delete_table", TableName=table)
            client.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
            )
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--table", default=f"sales-manager-test-day06-{uuid4().hex[:12]}"
    )
    parser.add_argument(
        "--keep-table",
        action="store_true",
        help="Retain a successful run for restart checks",
    )
    args = parser.parse_args()
    print(json.dumps(verify(args.table, args.keep_table), ensure_ascii=False, indent=2))
