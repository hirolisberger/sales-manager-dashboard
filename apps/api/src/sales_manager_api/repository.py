"""Store-scoped DynamoDB primitives, independent of HTTP and business rules."""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError

Item = dict[str, Any]
SERIALIZER = TypeSerializer()
DESERIALIZER = TypeDeserializer()
MAX_ITEM_BYTES = 256 * 1024
MAX_TRANSACTION_BYTES = 3 * 1024 * 1024


class StorageError(RuntimeError):
    """Sanitized storage failure; do not expose SDK responses or item values."""


class StorageConflict(StorageError):
    """A conditional write or concurrent transaction was rejected."""


def _validate(value):
    if value is None or type(value) in {str, int, bool}:
        return
    if type(value) is list:
        for entry in value:
            _validate(entry)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for entry in value.values():
            _validate(entry)
        return
    raise ValueError("Storage accepts JSON values with integer numbers only")


def wire(item: Item) -> dict:
    _validate(item)
    return {key: SERIALIZER.serialize(value) for key, value in item.items()}


def _plain(value):
    if isinstance(value, Decimal):
        if not value.is_finite() or value != value.to_integral_value():
            raise StorageError("保存データの数値形式を確認してください。")
        return int(value)
    if isinstance(value, list):
        return [_plain(entry) for entry in value]
    if isinstance(value, dict):
        return {key: _plain(entry) for key, entry in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise StorageError("保存データの形式を確認してください。")


def plain(item: dict) -> Item:
    return {key: _plain(DESERIALIZER.deserialize(value)) for key, value in item.items()}


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode())


def call(client, operation: str, **kwargs):
    try:
        return getattr(client, operation)(**kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        conflicts = {"ConditionalCheckFailedException", "TransactionConflictException"}
        if code == "TransactionCanceledException":
            reasons = exc.response.get("CancellationReasons", [])
            codes = {reason.get("Code") for reason in reasons} - {None, "None"}
            if codes and codes <= {"ConditionalCheckFailed", "TransactionConflict"}:
                raise StorageConflict(
                    "保存条件が一致しません。再読込してください。"
                ) from None
        if code in conflicts:
            raise StorageConflict(
                "保存条件が一致しません。再読込してください。"
            ) from None
        raise StorageError("保存先への操作に失敗しました。") from None
    except BotoCoreError:
        raise StorageError("保存先へ接続できません。") from None


@dataclass(frozen=True)
class Write:
    kind: Literal["put", "delete", "check"]
    item: Item
    condition: str
    names: dict[str, str] | None = None
    values: Item | None = None


@dataclass(frozen=True)
class Page:
    items: list[Item]
    last_key: Item | None


class DynamoRepository:
    def __init__(self, client, table: str, store_id: str):
        self.client = client
        self.table = table
        self.prefix = f"STORE#{store_id}#"

    def key(self, pk: str, sk: str) -> Item:
        result = {"PK": self.prefix + pk, "SK": sk}
        self._key(result)
        return result

    def _key(self, item: Item) -> Item:
        pk, sk = item.get("PK"), item.get("SK")
        if (
            type(pk) is not str
            or not pk.startswith(self.prefix)
            or len(pk) <= len(self.prefix)
            or len(pk.encode()) > 2048
            or type(sk) is not str
            or not sk
            or len(sk.encode()) > 1024
        ):
            raise ValueError("Invalid or out-of-store item key")
        return {"PK": pk, "SK": sk}

    def get(self, key: Item) -> Item | None:
        response = call(
            self.client,
            "get_item",
            TableName=self.table,
            Key=wire(self._key(key)),
            ConsistentRead=True,
        )
        return plain(response["Item"]) if "Item" in response else None

    def query_page(
        self,
        pk: str,
        sk_prefix: str,
        *,
        limit: int = 50,
        last_key: Item | None = None,
        ascending: bool = True,
    ) -> Page:
        key = self.key(pk, sk_prefix)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Query limit must be an integer from 1 to 100")
        arguments = {
            "TableName": self.table,
            "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
            "ExpressionAttributeValues": wire({":pk": key["PK"], ":prefix": sk_prefix}),
            "ConsistentRead": True,
            "Limit": limit,
            "ScanIndexForward": ascending,
        }
        if last_key is not None:
            cursor = self._key(last_key)
            if cursor["PK"] != key["PK"] or not cursor["SK"].startswith(sk_prefix):
                raise ValueError("Continuation key does not match the query")
            arguments["ExclusiveStartKey"] = wire(cursor)
        response = call(self.client, "query", **arguments)
        return Page(
            [plain(item) for item in response.get("Items", [])],
            plain(response["LastEvaluatedKey"])
            if response.get("LastEvaluatedKey")
            else None,
        )

    def transact(self, writes: list[Write]) -> None:
        if not 1 <= len(writes) <= 55:
            raise ValueError("A transaction requires 1 to 55 actions")
        actions, seen = [], set()
        for write in writes:
            key = self._key(write.item)
            target = (key["PK"], key["SK"])
            if target in seen:
                raise ValueError("Duplicate item in transaction")
            seen.add(target)
            if write.kind not in {"put", "delete", "check"} or not write.condition:
                raise ValueError("Each write requires a supported kind and condition")
            value = wire(write.item if write.kind == "put" else key)
            if _size(value) > MAX_ITEM_BYTES:
                raise ValueError("Item exceeds the conservative 256 KiB guard")
            operation = {"put": "Put", "delete": "Delete", "check": "ConditionCheck"}[
                write.kind
            ]
            parameters = {
                "TableName": self.table,
                "ConditionExpression": write.condition,
            }
            parameters["Item" if write.kind == "put" else "Key"] = value
            if write.names:
                parameters["ExpressionAttributeNames"] = dict(write.names)
            if write.values:
                parameters["ExpressionAttributeValues"] = wire(write.values)
            actions.append({operation: parameters})
        if _size(actions) > MAX_TRANSACTION_BYTES:
            raise ValueError("Transaction exceeds the conservative 3 MiB guard")
        call(self.client, "transact_write_items", TransactItems=actions)
