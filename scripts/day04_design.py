"""Executable Day 4 design examples, NOT the application/domain/repository layer.

The clock, store and line IDs here are deliberately fixed synthetic fixtures.
The future API must implement validation, authorization and error mapping itself.
"""

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from boto3.dynamodb.types import TypeSerializer

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / "docs/examples/day04-fixtures.json").read_text())
STORE = "STORE#demo"
NOW = FIXTURES["reference_now"]
TODAY = date.fromisoformat(FIXTURES["reference_today"])
SERIALIZER = TypeSerializer()


def period(start: str, end: str) -> tuple[date, date]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last == date.max or not 1 <= (last - first).days + 1 <= 366:
        raise ValueError("Period must contain 1..366 inclusive dates")
    return first, last


def calculate_sale(sale_id: str, request: dict, products: dict, before=None) -> dict:
    """Reference calculation after schema validation; not an HTTP input validator."""
    if before and before["status"] != "confirmed":
        raise ValueError("Cancelled sale cannot be corrected")
    if date.fromisoformat(request["sale_date"]) > TODAY:
        raise ValueError("Future sale date")
    old_lines = {line["line_id"]: line for line in before["lines"]} if before else {}
    seen = set()
    lines = []
    for number, value in enumerate(request["lines"], 1):
        existing = value.get("line_id")
        if existing and (existing not in old_lines or existing in seen):
            raise ValueError("Unknown or duplicate line ID")
        seen.add(existing) if existing else None
        old = old_lines.get(existing)
        same_product = old and old["product_id"] == value["product_id"]
        preserve = same_product and not value.get("refresh_product_snapshot", False)
        product = products[value["product_id"]]
        if not preserve and not product["is_active"]:
            raise ValueError("Inactive product")
        price, quantity = value["unit_price_yen"], value["quantity"]
        if type(price) is not int or not 0 <= price <= 9_999_999:
            raise ValueError("Invalid integer price")
        if type(quantity) is not int or not 1 <= quantity <= 9_999:
            raise ValueError("Invalid integer quantity")
        lines.append(
            {
                "line_id": existing or str(uuid5(NAMESPACE_URL, f"{sale_id}/{number}")),
                "line_no": number,
                "product_id": product["id"],
                "product_code": old["product_code"] if preserve else product["code"],
                "product_name": old["product_name"] if preserve else product["name"],
                "unit_price_yen": price,
                "quantity": quantity,
                "line_amount_yen": price * quantity,
            }
        )
    total = sum(line["line_amount_yen"] for line in lines)
    if not 1 <= len(lines) <= 50 or total > 9_999_999_999:
        raise ValueError("Sale limits exceeded")
    return {
        "id": sale_id,
        "sale_date": request["sale_date"],
        "currency": "JPY",
        "status": "confirmed",
        "version": before["version"] + 1 if before else 1,
        "total_amount_yen": total,
        "created_at": before["created_at"] if before else NOW,
        "updated_at": NOW,
        "lines": lines,
    }


def initial_sales() -> tuple[dict, list]:
    products = {
        product["id"]: copy.deepcopy(product) for product in FIXTURES["products"]
    }
    sales = [calculate_sale(s["id"], s["request"], products) for s in FIXTURES["sales"]]
    return products, sales


def correction_request(sale: dict, sale_date=None) -> dict:
    lines = [
        {
            key: line[key]
            for key in ("line_id", "product_id", "unit_price_yen", "quantity")
        }
        for line in sale["lines"]
    ]
    lines[0]["quantity"] = 1
    return {
        "sale_date": sale_date or sale["sale_date"],
        "lines": lines,
        "reason": "架空データの訂正確認",
    }


def cancel(sale: dict) -> dict:
    if sale["status"] != "confirmed":
        raise ValueError("Already cancelled")
    result = copy.deepcopy(sale)
    result.update(status="cancelled", version=sale["version"] + 1, updated_at=NOW)
    return result


def selected_rows(sales: list, start: str, end: str, product_id=None) -> list:
    first, last = period(start, end)
    return [
        {"sale_id": sale["id"], "sale_date": sale["sale_date"], **line}
        for sale in sales
        if sale["status"] == "confirmed"
        and first <= date.fromisoformat(sale["sale_date"]) <= last
        for line in sale["lines"]
        if product_id is None or line["product_id"] == product_id
    ]


def totals(rows: list) -> dict:
    return {
        "amount_yen": sum(row["line_amount_yen"] for row in rows),
        "quantity": sum(row["quantity"] for row in rows),
        "sale_count": len({row["sale_id"] for row in rows}),
    }


def wire(item: dict) -> dict:
    return {key: SERIALIZER.serialize(value) for key, value in item.items()}


def key(sale: dict, view=False) -> dict:
    if view:
        return {"PK": f"{STORE}#DAY#{sale['sale_date']}", "SK": f"SALE#{sale['id']}"}
    return {"PK": f"{STORE}#SALE#{sale['id']}", "SK": "CURRENT"}


def product_key(product_id: str) -> dict:
    return {"PK": f"{STORE}#PRODUCTS", "SK": f"PRODUCT#{product_id}"}


def request_key(request_id: str) -> dict:
    return {
        "PK": f"{STORE}#REQUEST#{FIXTURES['ids']['actor']}",
        "SK": f"KEY#{request_id}",
    }


def write_plan(
    table: str,
    sale: dict,
    before: dict | None,
    request_id: str,
    guards: list | None = None,
) -> list:
    """Low-level TransactWriteItems design experiment, with version conditions."""
    operation = (
        "created"
        if before is None
        else ("cancelled" if sale["status"] == "cancelled" else "corrected")
    )
    revision = {
        "sale_id": sale["id"],
        "version": sale["version"],
        "operation": operation,
        "actor_id": FIXTURES["ids"]["actor"],
        "occurred_at": NOW,
        "reason": None if before is None else "架空データの変更確認",
        "before": before,
        "after": sale,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            {"operation": operation, "sale": sale, "previous": before},
            sort_keys=True,
            ensure_ascii=True,
        ).encode()
    ).hexdigest()
    # This fixture fingerprint is not the future HTTP canonical request hash.
    idem = {
        **request_key(request_id),
        "fingerprint": fingerprint,
        "response_status": 201 if before is None else 200,
        "response_etag": f'"v{sale["version"]}"',
        "response_body": sale,
        "created_at": NOW,
    }

    def put(item, old_version=None):
        data = {"TableName": table, "Item": wire(item)}
        if old_version is None:
            data["ConditionExpression"] = "attribute_not_exists(PK)"
        else:
            data.update(
                ConditionExpression="#v = :v",
                ExpressionAttributeNames={"#v": "version"},
                ExpressionAttributeValues={":v": {"N": str(old_version)}},
            )
        return {"Put": data}

    old_version = before["version"] if before else None
    actions = [
        put({**key(sale), **sale}, old_version),
        put({"PK": key(sale)["PK"], "SK": f"REV#{sale['version']:010d}", **revision}),
        put(idem),
    ]
    moved = before and before["sale_date"] != sale["sale_date"]
    if moved:
        actions.append(
            {
                "Delete": {
                    "TableName": table,
                    "Key": wire(key(before, view=True)),
                    "ConditionExpression": "#v = :v",
                    "ExpressionAttributeNames": {"#v": "version"},
                    "ExpressionAttributeValues": {":v": {"N": str(old_version)}},
                }
            }
        )
    actions.append(
        put({**key(sale, view=True), **sale}, None if moved else old_version)
    )
    for product in {p["id"]: p for p in guards or []}.values():
        actions.append(
            {
                "ConditionCheck": {
                    "TableName": table,
                    "Key": wire(product_key(product["id"])),
                    "ConditionExpression": "#v = :v AND is_active = :active",
                    "ExpressionAttributeNames": {"#v": "version"},
                    "ExpressionAttributeValues": {
                        ":v": {"N": str(product["version"])},
                        ":active": {"BOOL": True},
                    },
                }
            }
        )
    check_budget(actions)
    return actions


def check_budget(actions: list) -> dict:
    # Conservative typed JSON envelope, NOT DynamoDB's exact item-size algorithm.
    items = [a["Put"]["Item"] for a in actions if "Put" in a]
    item_bytes = max(len(json.dumps(i, ensure_ascii=True).encode()) for i in items)
    transaction_bytes = len(json.dumps(actions, ensure_ascii=True).encode())
    if (
        len(actions) > 55
        or item_bytes > 256 * 1024
        or transaction_bytes > 3 * 1024 * 1024
    ):
        raise ValueError("Conservative design budget exceeded")
    return {
        "actions": len(actions),
        "max_item_bytes": item_bytes,
        "transaction_json_bytes": transaction_bytes,
    }
