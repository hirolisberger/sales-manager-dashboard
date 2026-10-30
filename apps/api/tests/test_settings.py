import os

import pytest
from pydantic import ValidationError
from sales_manager_api.settings import ConfigurationError, Settings, load_settings


def test_default_and_explicit_dotenv_priority(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("APP_ENV=aws\n")
    monkeypatch.chdir(tmp_path)
    defaults = load_settings()
    assert defaults.app_env == "local"
    assert defaults.endpoint_url == "http://127.0.0.1:4566"
    selected = tmp_path / "chosen.env"
    selected.write_text("APP_ENV=test\nLOG_LEVEL=WARNING\nAWS_REGION=us-east-1\n")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    before = dict(os.environ)
    result = load_settings(selected)
    assert result.app_env == "test"
    assert result.log_level == "ERROR"
    assert result.aws_region == "us-east-1"
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:4566",
        "http://localhost:4566/",
    ],
)
def test_local_endpoints(endpoint):
    result = Settings(AWS_ENDPOINT_URL=endpoint)
    assert result.endpoint_url == endpoint.removesuffix("/")


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "https://dynamodb.ap-northeast-1.amazonaws.com",
        "http://0.0.0.0:4566",
        "http://127.0.0.1:4566.evil.invalid",
        "http://user:password@localhost:4566",
        "http://localhost:4566/path",
        "http://localhost:4566?x=1",
        "http://localhost:4566#fragment",
        "http://localhost:4566//",
        "http://localhost:4567",
        "https://localhost:4566",
    ],
)
def test_local_rejects_ambiguous_or_remote_endpoints(endpoint):
    with pytest.raises(ValidationError):
        Settings(AWS_ENDPOINT_URL=endpoint)


def test_aws_requires_region_and_forbids_endpoint_overrides():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="aws")
    for endpoint in ["", "http://localhost:4566", "https://example.invalid"]:
        with pytest.raises(ValidationError):
            Settings(
                APP_ENV="aws", AWS_REGION="ap-northeast-1", AWS_ENDPOINT_URL=endpoint
            )
    settings = Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1")
    assert settings.endpoint_url is None


@pytest.mark.parametrize(
    "values",
    [
        {"APP_ENV": "production-typo"},
        {"LOG_LEVEL": "trace"},
        {"AWS_REGION": ""},
        {"AWS_REGION": "ap northeast 1"},
    ],
)
def test_invalid_settings(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_missing_or_unknown_dotenv_is_a_sanitized_error(tmp_path):
    with pytest.raises(ConfigurationError):
        load_settings(tmp_path / "missing.env")
    path = tmp_path / "wrong.env"
    path.write_text("UNEXPECTED_TOKEN=private-marker\n")
    with pytest.raises(ConfigurationError) as error:
        load_settings(path)
    assert "private-marker" not in str(error.value)
    assert "UNEXPECTED_TOKEN" not in str(error.value)


@pytest.mark.parametrize(
    "values",
    [
        {"DYNAMODB_TABLE": ""},
        {"DYNAMODB_TABLE": "x"},
        {"DYNAMODB_TABLE": "table/invalid"},
        {"STORE_ID": "other#store"},
        {"STORE_ID": ""},
        {"STORE_ID": "x" * 33},
    ],
)
def test_invalid_storage_settings(values):
    with pytest.raises(ValidationError):
        Settings(**values)
