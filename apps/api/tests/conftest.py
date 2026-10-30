from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    for name in (
        "APP_ENV",
        "LOG_LEVEL",
        "AWS_REGION",
        "AWS_ENDPOINT_URL",
        "DYNAMODB_TABLE",
        "STORE_ID",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def contract_validator():
    root = Path(__file__).resolve().parents[3]
    contract = yaml.safe_load((root / "docs/contracts/openapi.yaml").read_text())

    def validate(name, body):
        Draft202012Validator(
            {
                "components": contract["components"],
                "$ref": f"#/components/schemas/{name}",
            },
            format_checker=FormatChecker(),
        ).validate(body)

    return validate
