"""Local-only, explicit data initialization; never runs at API startup."""

import argparse
import json
from pathlib import Path

from botocore.exceptions import BotoCoreError

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import (
    ensure_table,
    inspect_products,
    require_local,
    reset_table,
    seed_demo,
)
from sales_manager_api.repository import DynamoRepository, StorageError
from sales_manager_api.settings import ConfigurationError, load_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Manage local demo data only")
    parser.add_argument("--env-file", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "seed", "inspect"):
        commands.add_parser(name)
    reset = commands.add_parser("reset")
    reset.add_argument("--confirm-table", required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env_file)
        require_local(settings)
        if args.command == "reset" and args.confirm_table != settings.dynamodb_table:
            raise ValueError("--confirm-tableに対象テーブル名を指定してください。")
    except (ConfigurationError, ValueError) as exc:
        parser.error(str(exc))
    client = None
    try:
        client = dynamodb_client(settings)
        repo = DynamoRepository(client, settings.dynamodb_table, settings.store_id)
        result = {"table": settings.dynamodb_table, "store": settings.store_id}
        match args.command:
            case "init":
                result["created"] = ensure_table(client, settings)
            case "seed":
                result["seeded"] = seed_demo(repo)
            case "inspect":
                products = inspect_products(repo)
                result.update(
                    product_count=len(products),
                    products=[
                        {
                            key: row[key]
                            for key in (
                                "id",
                                "code",
                                "name",
                                "default_unit_price_yen",
                                "version",
                            )
                        }
                        for row in products
                    ],
                )
            case "reset":
                reset_table(client, settings, args.confirm_table)
                result["reset"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except StorageError as exc:
        parser.exit(1, f"{exc}\n")
    except BotoCoreError:
        parser.exit(1, "保存先のクライアントを作成できません。\n")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
