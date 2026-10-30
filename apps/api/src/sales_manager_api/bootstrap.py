"""Explicit, local-only table management and synthetic seed data."""

import re

from botocore.exceptions import BotoCoreError, ClientError

from sales_manager_api.repository import (
    DynamoRepository,
    StorageConflict,
    StorageError,
    Write,
    call,
)
from sales_manager_api.settings import Settings

KEY_SCHEMA = [
    {"AttributeName": "PK", "KeyType": "HASH"},
    {"AttributeName": "SK", "KeyType": "RANGE"},
]
ATTRIBUTES = [{"AttributeName": name, "AttributeType": "S"} for name in ("PK", "SK")]


def require_local(settings: Settings) -> None:
    if settings.app_env not in {"local", "test"} or not re.fullmatch(
        r"sales-manager-(?:local|test)(?:-[a-z0-9-]+)?", settings.dynamodb_table
    ):
        raise ValueError("管理CLIはlocal/testモードの専用テーブルだけを操作できます。")


def _describe(client, table: str):
    try:
        return client.describe_table(TableName=table)["Table"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            return None
        raise StorageError("テーブル構成を取得できません。") from None
    except BotoCoreError:
        raise StorageError("保存先へ接続できません。") from None


def _check_schema(description):
    def normalized(rows):
        return sorted(rows, key=lambda row: row["AttributeName"])

    if (
        normalized(description["KeySchema"]) != normalized(KEY_SCHEMA)
        or normalized(description["AttributeDefinitions"]) != normalized(ATTRIBUTES)
        or description.get("GlobalSecondaryIndexes")
        or description.get("LocalSecondaryIndexes")
        or description.get("BillingModeSummary", {}).get("BillingMode")
        != "PAY_PER_REQUEST"
    ):
        raise StorageError("既存テーブルの構成が異なるため、変更を中止しました。")


def _wait(client, name: str, table: str):
    try:
        client.get_waiter(name).wait(
            TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
        )
    except BotoCoreError:
        raise StorageError("テーブルの状態待ちが完了しませんでした。") from None


def ensure_table(client, settings: Settings) -> bool:
    require_local(settings)
    description = _describe(client, settings.dynamodb_table)
    created = False
    if description is None:
        try:
            client.create_table(
                TableName=settings.dynamodb_table,
                BillingMode="PAY_PER_REQUEST",
                KeySchema=KEY_SCHEMA,
                AttributeDefinitions=ATTRIBUTES,
            )
            created = True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceInUseException":
                raise StorageError("テーブルを作成できません。") from None
        except BotoCoreError:
            raise StorageError("保存先へ接続できません。") from None
    _wait(client, "table_exists", settings.dynamodb_table)
    _check_schema(_describe(client, settings.dynamodb_table))
    return created


def reset_table(client, settings: Settings, confirmation: str) -> None:
    require_local(settings)
    if confirmation != settings.dynamodb_table:
        raise ValueError("--confirm-tableに対象テーブル名を指定してください。")
    existing = _describe(client, settings.dynamodb_table)
    if existing is not None:
        _check_schema(existing)
        call(client, "delete_table", TableName=settings.dynamodb_table)
        _wait(client, "table_not_exists", settings.dynamodb_table)
    ensure_table(client, settings)


def demo_items(repo: DynamoRepository) -> list[dict]:
    """Trusted fixed fixtures, not user input or product-registration logic."""
    products = []
    for suffix, code, name, price in [
        (1, "COFFEE", "コーヒー", 550),
        (2, "TEA", "紅茶", 330),
    ]:
        product_id = f"00000000-0000-4000-8000-{suffix:012d}"
        products.append(
            {
                **repo.key("PRODUCTS", f"PRODUCT#{product_id}"),
                "id": product_id,
                "code": code,
                "name": name,
                "default_unit_price_yen": price,
                "is_active": True,
                "version": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        )
    reservations = [
        {
            **repo.key("PRODUCT_CODES", f"CODE#{product['code']}"),
            "product_id": product["id"],
        }
        for product in products
    ]
    return [
        *products,
        *reservations,
        {**repo.key("SEED", "day06-v1"), "dataset": "day06-v1"},
    ]


def seed_demo(repo: DynamoRepository) -> bool:
    expected = demo_items(repo)
    existing = [repo.get(item) for item in expected]
    if existing == expected:
        return False
    if any(item is not None for item in existing):
        raise StorageConflict("初期データが変更済みか一部存在します。上書きしません。")
    try:
        repo.transact(
            [Write("put", item, "attribute_not_exists(PK)") for item in expected]
        )
    except StorageConflict:
        # Another identical seed may have committed between our reads and write.
        if [repo.get(item) for item in expected] == expected:
            return False
        raise
    return True


def inspect_products(repo: DynamoRepository) -> list[dict]:
    rows, cursor = [], None
    while True:
        page = repo.query_page("PRODUCTS", "PRODUCT#", last_key=cursor)
        rows.extend(page.items)
        if page.last_key is None:
            return rows
        cursor = page.last_key
