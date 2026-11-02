import logging
import socket
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import StrictInt
from sales_manager_api.app import create_app
from sales_manager_api.errors import ApplicationError
from sales_manager_api.schemas import ApiModel
from sales_manager_api.settings import Settings


class InputProbe(ApiModel):
    value: StrictInt


@pytest.fixture
def client():
    app = create_app(Settings(APP_ENV="test"))

    # These routes exist only in the test app, never in the product factory.
    @app.post("/__test__/input")
    async def input_probe(body: InputProbe):
        return {"value": body.value}

    @app.get("/__test__/failure")
    async def failure():
        raise RuntimeError("private-marker")

    @app.get("/__test__/unauthenticated")
    async def unauthenticated():
        raise HTTPException(
            401, "private-marker", headers={"WWW-Authenticate": "Bearer"}
        )

    @app.get("/__test__/conflict")
    async def conflict():
        raise ApplicationError(
            409, "IDEMPOTENCY_CONFLICT", "要求キーを確認してください。"
        )

    with TestClient(app) as result:
        yield result


def assert_error(response, status, code, contract_validator):
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    contract_validator("Error", body)
    assert body["error"]["code"] == code
    assert UUID(body["error"]["request_id"]).version == 4
    assert response.headers["x-request-id"] == body["error"]["request_id"]
    assert "private-marker" not in response.text
    return body


def test_health_contract_and_server_generated_ids(client, contract_validator):
    first = client.get("/health", headers={"X-Request-ID": "private-marker"})
    second = client.get("/health")
    assert first.status_code == second.status_code == 200
    assert first.json() == {"status": "ok"}
    contract_validator("Health", first.json())
    assert UUID(first.headers["x-request-id"]).version == 4
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


def test_health_has_no_network_dependency(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Liveness attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setenv("AWS_PROFILE", "nonexistent-personal-profile")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent/credentials")
    with TestClient(create_app(Settings())) as test_client:
        assert test_client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/missing", "/sales", "/docs", "/openapi.json"])
def test_unimplemented_routes_use_common_404(client, contract_validator, path):
    assert_error(client.get(path), 404, "NOT_FOUND", contract_validator)


def test_wrong_method_preserves_allow_header(client, contract_validator):
    result = client.post("/health")
    assert_error(result, 405, "METHOD_NOT_ALLOWED", contract_validator)
    assert "GET" in result.headers["allow"]


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_strict_input_uses_common_422(client, contract_validator, value):
    result = client.post("/__test__/input", json={"value": value})
    error = assert_error(result, 422, "VALIDATION_ERROR", contract_validator)
    assert error["error"]["details"][0]["path"] == "body.value"
    assert set(error["error"]["details"][0]) == {"path", "code", "message"}


def test_unknown_field_and_malformed_json_hide_input(client, contract_validator):
    result = client.post(
        "/__test__/input", json={"value": 1, "extra": "private-marker"}
    )
    assert_error(result, 422, "VALIDATION_ERROR", contract_validator)
    broken = client.post(
        "/__test__/input",
        content='{"value":"private-marker"',
        headers={"Content-Type": "application/json"},
    )
    error = assert_error(broken, 400, "INVALID_JSON", contract_validator)
    assert error["error"]["details"] == []


def test_known_errors_and_challenge_header(client, contract_validator):
    unauthenticated = client.get("/__test__/unauthenticated")
    assert_error(unauthenticated, 401, "UNAUTHENTICATED", contract_validator)
    assert unauthenticated.headers["www-authenticate"] == "Bearer"
    assert_error(
        client.get("/__test__/conflict"),
        409,
        "IDEMPOTENCY_CONFLICT",
        contract_validator,
    )


def test_unhandled_error_and_logs_hide_private_data(client, contract_validator, caplog):
    caplog.set_level(logging.INFO, logger="sales_manager_api.requests")
    result = client.get(
        "/__test__/failure?secret=private-marker",
        headers={"Authorization": "Bearer private-marker"},
    )
    assert_error(result, 500, "INTERNAL_ERROR", contract_validator)
    records = [
        record
        for record in caplog.records
        if record.name == "sales_manager_api.requests"
    ]
    assert records
    assert all("private-marker" not in record.getMessage() for record in records)
    assert any(
        result.headers["x-request-id"] in record.getMessage() for record in records
    )
