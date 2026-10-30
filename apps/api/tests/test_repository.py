from decimal import Decimal
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.repository import (
    MAX_ITEM_BYTES,
    MAX_TRANSACTION_BYTES,
    DynamoRepository,
    StorageConflict,
    StorageError,
    Write,
    plain,
    wire,
)
from sales_manager_api.settings import Settings


@pytest.fixture
def storage():
    client = dynamodb_client(Settings(APP_ENV="test"))
    with Stubber(client) as stub:
        yield DynamoRepository(client, "sales-manager-test-unit", "demo"), stub
        stub.assert_no_pending_responses()
    client.close()


def test_read_write_integer_bool_and_nested_values(storage):
    repo, stub = storage
    item = {
        **repo.key("PRODUCTS", "PRODUCT#1"),
        "amount": 550,
        "active": True,
        "nested": [{"value": 2}, None],
    }
    request = {
        "TransactItems": [
            {
                "Put": {
                    "TableName": repo.table,
                    "Item": wire(item),
                    "ConditionExpression": "attribute_not_exists(PK)",
                }
            }
        ]
    }
    stub.add_response("transact_write_items", {}, request)
    repo.transact([Write("put", item, "attribute_not_exists(PK)")])
    expected = {
        "TableName": repo.table,
        "Key": wire(repo._key(item)),
        "ConsistentRead": True,
    }
    stub.add_response("get_item", {"Item": wire(item)}, expected)
    result = repo.get(item)
    assert result == item and type(result["amount"]) is int
    assert result["active"] is True
    stub.add_response("get_item", {}, expected)
    assert repo.get(item) is None


@pytest.mark.parametrize("value", [1.5, Decimal("1"), {1, 2}, b"bytes", {1: "bad"}])
def test_non_json_or_fractional_values_fail_before_network(storage, value):
    repo, _ = storage
    with pytest.raises(ValueError):
        repo.transact(
            [
                Write(
                    "put",
                    {**repo.key("P", "S"), "value": value},
                    "attribute_not_exists(PK)",
                )
            ]
        )


def test_fractional_stored_number_is_not_silently_truncated():
    with pytest.raises(StorageError):
        plain({"price": {"N": "1.5"}})


def test_query_continuation_empty_page_and_order(storage):
    repo, stub = storage
    key = repo.key("PRODUCTS", "PRODUCT#1")
    request = {
        "TableName": repo.table,
        "KeyConditionExpression": "PK = :pk AND begins_with(SK, :prefix)",
        "ExpressionAttributeValues": wire({":pk": key["PK"], ":prefix": "PRODUCT#"}),
        "ConsistentRead": True,
        "Limit": 1,
        "ScanIndexForward": False,
    }
    stub.add_response("query", {"Items": [], "LastEvaluatedKey": wire(key)}, request)
    page = repo.query_page("PRODUCTS", "PRODUCT#", limit=1, ascending=False)
    assert page.items == [] and page.last_key == key
    stub.add_response(
        "query", {"Items": [wire(key)]}, {**request, "ExclusiveStartKey": wire(key)}
    )
    assert repo.query_page(
        "PRODUCTS", "PRODUCT#", limit=1, ascending=False, last_key=page.last_key
    ).items == [key]


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_invalid_query_limit(storage, limit):
    with pytest.raises(ValueError):
        storage[0].query_page("PRODUCTS", "PRODUCT#", limit=limit)


@pytest.mark.parametrize(
    "cursor",
    [
        {"PK": "STORE#other#PRODUCTS", "SK": "PRODUCT#1"},
        {"PK": "STORE#demo#OTHER", "SK": "PRODUCT#1"},
        {"PK": "STORE#demo#PRODUCTS", "SK": "CODE#1"},
    ],
)
def test_cross_store_or_query_cursor_is_rejected(storage, cursor):
    with pytest.raises(ValueError):
        storage[0].query_page("PRODUCTS", "PRODUCT#", last_key=cursor)


def test_guards_reject_duplicate_count_item_and_transaction_size(storage, monkeypatch):
    repo, _ = storage
    item = repo.key("P", "S")
    write = Write("put", item, "attribute_not_exists(PK)")
    for writes in ([], [write] * 56, [write, write], [Write("put", item, "")]):
        with pytest.raises(ValueError):
            repo.transact(writes)
    with pytest.raises(ValueError):
        repo.transact(
            [
                Write(
                    "put",
                    {**item, "text": "x" * MAX_ITEM_BYTES},
                    "attribute_not_exists(PK)",
                )
            ]
        )
    assert MAX_TRANSACTION_BYTES == 3 * 1024 * 1024
    monkeypatch.setattr("sales_manager_api.repository.MAX_TRANSACTION_BYTES", 1)
    with pytest.raises(ValueError):
        repo.transact([write])
    with pytest.raises(ValueError):
        repo.get({"PK": "STORE#other#P", "SK": "S"})


def test_conditional_delete_and_check_wire_request(storage):
    repo, stub = storage
    first, second = repo.key("P", "1"), repo.key("P", "2")
    common = {
        "TableName": repo.table,
        "ConditionExpression": "#v = :v",
        "ExpressionAttributeNames": {"#v": "version"},
        "ExpressionAttributeValues": wire({":v": 1}),
    }
    stub.add_response(
        "transact_write_items",
        {},
        {
            "TransactItems": [
                {"Delete": {**common, "Key": wire(first)}},
                {"ConditionCheck": {**common, "Key": wire(second)}},
            ]
        },
    )
    repo.transact(
        [
            Write("delete", first, "#v = :v", {"#v": "version"}, {":v": 1}),
            Write("check", second, "#v = :v", {"#v": "version"}, {":v": 1}),
        ]
    )


@pytest.mark.parametrize(
    "code,reasons,expected",
    [
        (
            "TransactionCanceledException",
            [{"Code": "ConditionalCheckFailed"}],
            StorageConflict,
        ),
        (
            "TransactionCanceledException",
            [{"Code": "ProvisionedThroughputExceeded"}],
            StorageError,
        ),
        ("TransactionCanceledException", [], StorageError),
        ("AccessDeniedException", [], StorageError),
    ],
)
def test_sdk_errors_are_classified_without_exposing_values(code, reasons, expected):
    client = Mock()
    client.transact_write_items.side_effect = ClientError(
        {
            "Error": {"Code": code, "Message": "private-marker"},
            "CancellationReasons": reasons,
        },
        "TransactWriteItems",
    )
    repo = DynamoRepository(client, "sales-manager-test-unit", "demo")
    with pytest.raises(expected) as error:
        repo.transact([Write("put", repo.key("P", "S"), "attribute_not_exists(PK)")])
    assert type(error.value) is expected
    assert "private-marker" not in str(error.value)
    assert error.value.__suppress_context__


def test_connection_failure_is_sanitized():
    client = Mock()
    client.get_item.side_effect = EndpointConnectionError(endpoint_url="private-marker")
    with pytest.raises(StorageError) as error:
        DynamoRepository(client, "sales-manager-test-unit", "demo").get(
            {"PK": "STORE#demo#P", "SK": "S"}
        )
    assert "private-marker" not in str(error.value)
