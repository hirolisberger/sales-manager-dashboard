import os
import socket
import subprocess

import botocore.configloader
import botocore.credentials
import pytest
from sales_manager_api.aws import dynamodb_client
from sales_manager_api.settings import Settings


@pytest.mark.parametrize("mode", ["local", "test"])
def test_local_client_ignores_personal_settings_and_does_not_change_environment(
    monkeypatch, tmp_path, mode
):
    private = tmp_path / "personal.ini"
    private.write_text("this is intentionally invalid private configuration")
    for key, value in {
        "AWS_PROFILE": "nonexistent-private-profile",
        "AWS_DEFAULT_PROFILE": "nonexistent-default",
        "AWS_CONFIG_FILE": str(private),
        "AWS_SHARED_CREDENTIALS_FILE": str(private),
        "AWS_ACCESS_KEY_ID": "private-marker",
        "AWS_SECRET_ACCESS_KEY": "private-marker",
        "AWS_SESSION_TOKEN": "private-marker",
        "AWS_ENDPOINT_URL_DYNAMODB": "https://example.invalid",
        "HTTPS_PROXY": "http://example.invalid:9999",
        "AWS_USE_FIPS_ENDPOINT": "true",
        "AWS_USE_DUALSTACK_ENDPOINT": "true",
    }.items():
        monkeypatch.setenv(key, value)

    def forbidden(*args, **kwargs):
        raise AssertionError("Local client accessed credentials or network")

    original = botocore.configloader.raw_config_parse

    def guarded_parse(path, *args, **kwargs):
        assert path == os.devnull
        return original(path, *args, **kwargs)

    monkeypatch.setattr(botocore.configloader, "raw_config_parse", guarded_parse)
    monkeypatch.setattr(
        botocore.credentials.CredentialResolver, "load_credentials", forbidden
    )
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    before = dict(os.environ)
    client = dynamodb_client(Settings(APP_ENV=mode))
    try:
        assert client.meta.endpoint_url == "http://127.0.0.1:4566"
        assert client.meta.config.proxies == {}
        credentials = client._request_signer._credentials
        assert credentials.access_key == credentials.secret_key == "test"
        assert not credentials.token
        assert dict(os.environ) == before
    finally:
        client.close()


def test_aws_client_uses_standard_endpoint_without_network(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "example-only")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "example-only")
    monkeypatch.setenv("AWS_ENDPOINT_URL_DYNAMODB", "http://example.invalid")
    monkeypatch.setenv("AWS_CONFIG_FILE", os.devnull)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", os.devnull)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.delenv("AWS_DEFAULT_PROFILE", raising=False)
    monkeypatch.setattr(
        socket.socket, "connect", lambda *_: pytest.fail("Network used")
    )
    client = dynamodb_client(Settings(APP_ENV="aws", AWS_REGION="ap-northeast-1"))
    try:
        assert (
            client.meta.endpoint_url == "https://dynamodb.ap-northeast-1.amazonaws.com"
        )
        assert client._request_signer._credentials.access_key == "example-only"
    finally:
        client.close()
