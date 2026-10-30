from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError
from sales_manager_api.bootstrap import (
    ATTRIBUTES,
    KEY_SCHEMA,
    demo_items,
    ensure_table,
    require_local,
    reset_table,
    seed_demo,
)
from sales_manager_api.data_cli import main
from sales_manager_api.repository import DynamoRepository, StorageConflict, StorageError
from sales_manager_api.settings import Settings


def description():
    return {
        "KeySchema": KEY_SCHEMA,
        "AttributeDefinitions": ATTRIBUTES,
        "BillingModeSummary": {"BillingMode": "PAY_PER_REQUEST"},
    }


def test_init_is_repeatable_without_deleting_or_writing_data():
    client = Mock()
    client.describe_table.return_value = {"Table": description()}
    assert ensure_table(client, Settings()) is False
    assert ensure_table(client, Settings()) is False
    client.create_table.assert_not_called()
    client.delete_table.assert_not_called()
    client.transact_write_items.assert_not_called()


def test_init_creates_missing_table_with_pay_per_request_schema():
    client = Mock()
    client.describe_table.side_effect = [
        ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DescribeTable"),
        {"Table": description()},
    ]
    assert ensure_table(client, Settings()) is True
    client.create_table.assert_called_once_with(
        TableName="sales-manager-local",
        BillingMode="PAY_PER_REQUEST",
        KeySchema=KEY_SCHEMA,
        AttributeDefinitions=ATTRIBUTES,
    )


@pytest.mark.parametrize(
    "change",
    [
        {"KeySchema": [{"AttributeName": "other", "KeyType": "HASH"}]},
        {"AttributeDefinitions": [{"AttributeName": "PK", "AttributeType": "N"}]},
        {"GlobalSecondaryIndexes": [{"IndexName": "other"}]},
        {"BillingModeSummary": {"BillingMode": "PROVISIONED"}},
    ],
)
def test_wrong_schema_is_rejected_without_modification(change):
    client = Mock()
    client.describe_table.return_value = {"Table": {**description(), **change}}
    with pytest.raises(StorageError):
        ensure_table(client, Settings())
    client.create_table.assert_not_called()
    client.delete_table.assert_not_called()


def test_seed_is_atomic_and_repeatable_and_never_overwrites_edits():
    repo = DynamoRepository(Mock(), "sales-manager-local", "demo")
    items = demo_items(repo)
    repo.get = Mock(return_value=None)
    repo.transact = Mock()
    assert seed_demo(repo) is True
    writes = repo.transact.call_args.args[0]
    assert len(writes) == 5
    assert [write.item for write in writes] == items
    assert all(write.condition == "attribute_not_exists(PK)" for write in writes)
    repo.transact.reset_mock()
    repo.get.side_effect = items
    assert seed_demo(repo) is False
    repo.transact.assert_not_called()
    changed = deepcopy(items)
    changed[0]["default_unit_price_yen"] = 600
    repo.get.side_effect = changed
    with pytest.raises(StorageConflict):
        seed_demo(repo)
    repo.transact.assert_not_called()
    repo.get.side_effect = [items[0], None, None, None, None]
    with pytest.raises(StorageConflict):
        seed_demo(repo)
    repo.transact.assert_not_called()


def test_identical_concurrent_seed_is_a_noop_after_conflict():
    repo = DynamoRepository(Mock(), "sales-manager-local", "demo")
    items = demo_items(repo)
    repo.get = Mock(side_effect=[*([None] * 5), *items])
    repo.transact = Mock(side_effect=StorageConflict("Concurrent seed"))
    assert seed_demo(repo) is False


@pytest.mark.parametrize(
    "settings",
    [
        Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1"),
        Settings(DYNAMODB_TABLE="sales-manager-production"),
        Settings(DYNAMODB_TABLE="unrelated-local-table"),
    ],
)
def test_management_guard_rejects_aws_and_unmanaged_tables(settings):
    with pytest.raises(ValueError):
        require_local(settings)


def test_reset_requires_exact_confirmation_before_any_sdk_call():
    client = Mock()
    with pytest.raises(ValueError):
        reset_table(client, Settings(), "wrong")
    assert client.mock_calls == []


def test_reset_recreates_only_the_selected_table():
    client = Mock()
    client.describe_table.side_effect = [
        {"Table": description()},
        ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DescribeTable"),
        {"Table": description()},
    ]
    reset_table(client, Settings(), "sales-manager-local")
    client.delete_table.assert_called_once_with(TableName="sales-manager-local")
    client.create_table.assert_called_once()


@pytest.mark.parametrize(
    "arguments,env",
    [
        (["init"], {"APP_ENV": "aws", "AWS_REGION": "ap-northeast-1"}),
        (["init"], {"DYNAMODB_TABLE": "unrelated-local-table"}),
        (["reset", "--confirm-table", "wrong"], {}),
        (["reset"], {}),
    ],
)
def test_cli_rejects_unsafe_commands_before_constructing_client(
    arguments, env, monkeypatch
):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with patch("sales_manager_api.data_cli.dynamodb_client") as create:
        with pytest.raises(SystemExit) as error:
            main(arguments)
        assert error.value.code == 2
        create.assert_not_called()


def test_data_cli_success_and_sanitized_storage_error(capsys):
    with patch("sales_manager_api.data_cli.dynamodb_client") as create:
        with patch("sales_manager_api.data_cli.ensure_table", return_value=False):
            main(["init"])
        assert '"created": false' in capsys.readouterr().out
        create.return_value.close.assert_called_once()
    with patch("sales_manager_api.data_cli.dynamodb_client") as create:
        create.return_value.describe_table.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "private-marker"}},
            "DescribeTable",
        )
        with pytest.raises(SystemExit) as error:
            main(["init"])
        assert error.value.code == 1
        assert "private-marker" not in capsys.readouterr().err
