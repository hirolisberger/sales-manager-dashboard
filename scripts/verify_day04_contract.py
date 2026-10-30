"""Verify the Day 4 document contract and independent business expectations."""

import copy
import csv
import io
import json
import unittest
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import yaml
from day04_design import (
    FIXTURES,
    ROOT,
    calculate_sale,
    cancel,
    check_budget,
    correction_request,
    initial_sales,
    period,
    selected_rows,
    totals,
    write_plan,
)
from jsonschema import Draft202012Validator, FormatChecker, ValidationError, validators
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource

SPEC = yaml.safe_load(
    (ROOT / "docs/contracts/openapi.yaml").read_text(encoding="utf-8")
)
SCHEMA_URI = "urn:sales-manager:day04"
REGISTRY = Registry().with_resource(
    SCHEMA_URI,
    Resource.from_contents(
        {"$schema": "https://json-schema.org/draft/2020-12/schema", **SPEC}
    ),
)
StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda _checker, instance: type(instance) is int
    ),
)


def validate(name, instance):
    StrictValidator(
        {"$ref": f"{SCHEMA_URI}#/components/schemas/{name}"},
        registry=REGISTRY,
        format_checker=FormatChecker(),
    ).validate(instance)


class ContractChecks(unittest.TestCase):
    def test_response_examples(self):
        products, sales = initial_sales()
        for product in products.values():
            validate(
                "Product",
                {
                    **product,
                    "created_at": FIXTURES["reference_now"],
                    "updated_at": FIXTURES["reference_now"],
                },
            )
        for sale in sales:
            validate("Sale", sale)
        validate(
            "Revision",
            {
                "sale_id": sales[0]["id"],
                "version": 1,
                "operation": "created",
                "actor_id": FIXTURES["ids"]["actor"],
                "occurred_at": FIXTURES["reference_now"],
                "reason": None,
                "before": None,
                "after": sales[0],
            },
        )
        validate(
            "Error",
            {
                "error": {
                    "code": "VERSION_CONFLICT",
                    "message": "再取得してください",
                    "request_id": FIXTURES["ids"]["s1"],
                    "details": [],
                }
            },
        )
        validate(
            "SalesReport",
            {
                "start_date": "2026-12-01",
                "end_date": "2026-12-01",
                "group_by": "day",
                "amount_yen": 0,
                "quantity": 0,
                "sale_count": 0,
                "rows": [
                    {
                        "bucket": "2026-12-01",
                        "amount_yen": 0,
                        "quantity": 0,
                        "sale_count": 0,
                    }
                ],
            },
        )
        validate(
            "ExportJob",
            {
                "job_id": FIXTURES["ids"]["s1"],
                "status": "queued",
                "criteria": {"start_date": "2026-12-01", "end_date": "2026-12-31"},
                "created_at": FIXTURES["reference_now"],
                "completed_at": None,
                "download_url": None,
                "expires_at": None,
                "error_code": None,
            },
        )

    def test_openapi_and_operations(self):
        validate_openapi(SPEC)
        operations = [
            op
            for path in SPEC["paths"].values()
            for method, op in path.items()
            if method in {"get", "post", "patch"}
        ]
        self.assertEqual(len(operations), 15)
        self.assertEqual(len({op["operationId"] for op in operations}), 15)
        for path, methods in SPEC["paths"].items():
            for method, op in methods.items():
                if method not in {"post", "patch"}:
                    continue
                refs = {p.get("$ref") for p in op.get("parameters", [])}
                self.assertIn("#/components/parameters/IdempotencyKey", refs, path)
                if method == "patch" or path.endswith("/cancel"):
                    self.assertIn("#/components/parameters/IfMatch", refs, path)

    def test_strict_requests(self):
        request = FIXTURES["sales"][0]["request"]
        validate("SaleCreate", request)
        invalid = []
        for field, values in {
            "unit_price_yen": [True, 1.0, "550", -1, 10_000_000],
            "quantity": [False, 1.0, "1", 0, 10_000],
        }.items():
            for value in values:
                candidate = copy.deepcopy(request)
                candidate["lines"][0][field] = value
                invalid.append(candidate)
        invalid.extend(
            [
                {**request, "lines": []},
                {**request, "lines": request["lines"][:1] * 51},
                {**request, "total_amount_yen": 1},
                {**request, "actor_id": "client"},
                {**request, "sale_date": "2026-02-30"},
            ]
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                validate("SaleCreate", candidate)
        for name, value in [
            ("ProductPatch", {}),
            ("ProductPatch", {"code": "NEW"}),
            ("Cancellation", {"reason": "  "}),
            ("Cancellation", {}),
        ]:
            with (
                self.subTest(name=name, value=value),
                self.assertRaises(ValidationError),
            ):
                validate(name, value)

    def test_snapshots_limits_and_dates(self):
        products, sales = initial_sales()
        product = products[FIXTURES["ids"]["coffee"]]
        product.update(name="新しい商品名", default_unit_price_yen=600, is_active=False)
        corrected = calculate_sale(
            sales[0]["id"], correction_request(sales[0]), products, sales[0]
        )
        self.assertEqual(corrected["lines"][0]["product_name"], "コーヒー")
        self.assertEqual(corrected["lines"][0]["unit_price_yen"], 550)
        validate("Sale", corrected)
        with self.assertRaises(ValueError):
            calculate_sale(sales[0]["id"], FIXTURES["sales"][0]["request"], products)
        for line_change in [
            {"refresh_product_snapshot": True},
            {"line_id": str(UUID(int=999))},
        ]:
            request = correction_request(sales[0])
            request["lines"][0].update(line_change)
            with self.assertRaises(ValueError):
                calculate_sale(sales[0]["id"], request, products, sales[0])
        request = correction_request(sales[0])
        request["lines"][1] = copy.deepcopy(request["lines"][0])
        with self.assertRaises(ValueError):
            calculate_sale(sales[0]["id"], request, products, sales[0])
        with self.assertRaises(ValueError):
            calculate_sale(
                sales[0]["id"],
                correction_request(sales[0], "2027-01-06"),
                products,
                sales[0],
            )
        with self.assertRaises(ValueError):
            calculate_sale(
                sales[0]["id"], correction_request(sales[0]), products, cancel(sales[0])
            )
        for start, end in [
            ("2026-12-02", "2026-12-01"),
            ("2026-01-01", "2027-01-02"),
            ("9999-12-31", "9999-12-31"),
        ]:
            with self.assertRaises(ValueError):
                period(start, end)
        self.assertEqual(
            (
                period("2024-01-01", "2024-12-31")[1]
                - period("2024-01-01", "2024-12-31")[0]
            ).days,
            365,
        )
        self.assertEqual(
            datetime.fromisoformat("2026-11-30T15:00:00+00:00")
            .astimezone(ZoneInfo("Asia/Tokyo"))
            .date()
            .isoformat(),
            "2026-12-01",
        )

    def test_day1_totals_and_csv(self):
        products, sales = initial_sales()
        expected = FIXTURES["expected"]

        def report(product_id=None):
            return totals(selected_rows(sales, "2026-12-01", "2026-12-31", product_id))

        self.assertEqual(report()["amount_yen"], expected["initial_total"])
        sales[0] = calculate_sale(
            sales[0]["id"], correction_request(sales[0]), products, sales[0]
        )
        self.assertEqual(report()["amount_yen"], expected["after_correction"])
        sales[1] = cancel(sales[1])
        self.assertEqual(report(), {"amount_yen": 1430, "quantity": 3, "sale_count": 2})
        self.assertEqual(
            report(FIXTURES["ids"]["tea"])["amount_yen"], expected["tea_total"]
        )
        rows = selected_rows(sales, "2026-12-01", "2026-12-31")
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        parsed = list(csv.DictReader(io.StringIO(output.getvalue())))
        self.assertEqual(len(parsed), expected["valid_line_count"])
        self.assertEqual(
            sum(int(row["line_amount_yen"]) for row in parsed), report()["amount_yen"]
        )
        sales[0] = calculate_sale(
            sales[0]["id"],
            correction_request(sales[0], "2027-01-01"),
            products,
            sales[0],
        )
        self.assertEqual(report()["amount_yen"], expected["after_date_move_december"])
        self.assertEqual(
            totals(selected_rows(sales, "2027-01-01", "2027-01-31"))["amount_yen"],
            expected["after_date_move_january"],
        )
        # The bounded range excludes adjacent months, including cancelled rows.
        self.assertEqual(selected_rows(sales, "2026-11-01", "2026-11-30"), [])

    def test_worst_case_transaction_budget(self):
        products, sales = initial_sales()
        product = copy.deepcopy(next(iter(products.values())))
        product.update(code="A" * 32, name="𠮷" * 100)
        expanded = {}
        lines = []
        for number in range(50):
            p = {**product, "id": str(UUID(int=1000 + number))}
            expanded[p["id"]] = p
            lines.append({"product_id": p["id"], "unit_price_yen": 1, "quantity": 1})
        sale = calculate_sale(
            sales[0]["id"], {"sale_date": "2026-12-01", "lines": lines}, expanded
        )
        validate("Sale", sale)
        guards = list(expanded.values())
        created = write_plan("fixture", sale, None, "create-max", guards)
        moved = calculate_sale(
            sale["id"], correction_request(sale, "2027-01-01"), expanded, sale
        )
        plan = write_plan("fixture", moved, sale, "move-max", guards)
        self.assertEqual(len(created), 54)
        self.assertEqual(len(plan), 55)
        print(
            "\nworst-case design budget:",
            json.dumps(check_budget(plan), sort_keys=True),
        )
        high = copy.deepcopy(FIXTURES["sales"][0]["request"])
        high["lines"] = [
            {
                "product_id": product["id"],
                "unit_price_yen": 9_999_999,
                "quantity": 9_999,
            }
        ]
        with self.assertRaises(ValueError):
            calculate_sale(sales[0]["id"], high, products)


if __name__ == "__main__":
    unittest.main(verbosity=2)
