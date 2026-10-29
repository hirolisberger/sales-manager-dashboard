"""Exercise disposable fixtures against an explicitly selected loopback endpoint."""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import boto3
import jwt
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

ROOT = Path(__file__).resolve().parents[1]
REGION = "ap-northeast-1"
DEFAULT_ENDPOINT = "http://127.0.0.1:4566"
ALLOWED_ENDPOINTS = {
    "http://127.0.0.1:4566",
    "http://localhost:4566",
    "http://127.0.0.1:4567",
    "http://localhost:4567",
}


def local_endpoint(value: str) -> str:
    """Reject omitted/remote/ambiguous URLs before constructing any AWS client."""
    endpoint = value.removesuffix("/")
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ValueError("Only explicit local endpoints on ports 4566/4567 are allowed")
    return endpoint


def local_session() -> boto3.Session:
    # These changes affect this Python process, never the user's shell or files.
    os.environ["AWS_CONFIG_FILE"] = os.devnull
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    for key in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        os.environ.pop(key, None)
    return boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="",
        region_name=REGION,
    )


def local_client(session: boto3.Session, service: str, endpoint: str):
    return session.client(
        service,
        endpoint_url=local_endpoint(endpoint),
        config=Config(
            region_name=REGION,
            proxies={},
            connect_timeout=3,
            read_timeout=5,
            retries={"mode": "standard", "total_max_attempts": 1},
            s3={"addressing_style": "path"},
        ),
    )


def verify_tokens(endpoint: str, pool_id: str, client_id: str, tokens: dict) -> None:
    # Fetch local JWKS explicitly; never follow the AWS-looking token issuer URL.
    if not pool_id.startswith(REGION + "_") or not all(
        char.isalnum() or char in "_-" for char in pool_id
    ):
        raise ValueError("Unexpected local pool ID")
    url = f"{local_endpoint(endpoint)}/{pool_id}/.well-known/jwks.json"
    with build_opener(ProxyHandler({})).open(url, timeout=5) as response:
        keys = json.load(response)["keys"]
    issuer = f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}"
    id_public_key = None
    for field, use in (("IdToken", "id"), ("AccessToken", "access")):
        token = tokens[field]
        header = jwt.get_unverified_header(token)
        jwk = next(key for key in keys if key["kid"] == header["kid"])
        public_key = jwt.PyJWK.from_dict(jwk, algorithm="RS256").key
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=client_id if use == "id" else None,
            options={
                "verify_aud": use == "id",
                "require": ["exp", "iat", "sub", "iss", "token_use"],
            },
        )
        assert claims["token_use"] == use
        if use == "id":
            id_public_key = public_key
        if use == "access":
            assert claims["client_id"] == client_id
    # Prove signature verification rejects a changed, otherwise valid payload.
    original = tokens["IdToken"].split(".")
    payload = jwt.api_jws.base64url_decode(original[1].encode())
    claims = json.loads(payload)
    claims["sub"] = "tampered-subject"
    original[1] = jwt.api_jws.base64url_encode(json.dumps(claims).encode()).decode()
    try:
        jwt.decode(".".join(original), id_public_key, algorithms=["RS256"])
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("Tampered JWT was accepted")


def compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", "--env-file", os.devnull, "-f", "compose.yaml", *args],
        cwd=ROOT,
        check=True,
        timeout=150,
    )


def run_checks(endpoint: str, lifecycle: bool = False, data_only: bool = False) -> dict:
    endpoint = local_endpoint(endpoint)
    if lifecycle and endpoint != DEFAULT_ENDPOINT:
        raise ValueError("Lifecycle checks require the default project's endpoint")
    session = local_session()
    dynamodb = local_client(session, "dynamodb", endpoint)
    s3 = local_client(session, "s3", endpoint)
    cognito = local_client(session, "cognito-idp", endpoint)
    name = "day03-probe-" + uuid.uuid4().hex[:12]
    payload = b"fictional local-only sales fixture\n"
    pool_id = None
    table_created = bucket_created = False
    cleanup_errors = []
    results = {"endpoint": endpoint, "region": REGION}
    try:
        dynamodb.create_table(
            TableName=name,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table_created = True
        dynamodb.get_waiter("table_exists").wait(
            TableName=name, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
        )
        dynamodb.put_item(
            TableName=name,
            Item={"id": {"S": "fixture"}, "amount_yen": {"N": "1430"}},
        )
        s3.create_bucket(
            Bucket=name, CreateBucketConfiguration={"LocationConstraint": REGION}
        )
        bucket_created = True
        s3.put_object(Bucket=name, Key="fixture.txt", Body=payload)

        def read_data() -> None:
            item = dynamodb.get_item(
                TableName=name, Key={"id": {"S": "fixture"}}, ConsistentRead=True
            )["Item"]
            assert item["amount_yen"] == {"N": "1430"}
            body = s3.get_object(Bucket=name, Key="fixture.txt")["Body"]
            with body:
                assert body.read() == payload

        read_data()
        results["dynamodb_read_write"] = "passed"
        results["s3_read_write"] = "passed"
        if data_only:
            results["cognito_login_jwks_rs256_tamper_wrong_password"] = "not_requested"
        else:
            pool_id = cognito.create_user_pool(PoolName=name)["UserPool"]["Id"]
            client_id = cognito.create_user_pool_client(
                UserPoolId=pool_id,
                ClientName=name,
                GenerateSecret=False,
                ExplicitAuthFlows=[
                    "ALLOW_USER_PASSWORD_AUTH",
                    "ALLOW_REFRESH_TOKEN_AUTH",
                ],
            )["UserPoolClient"]["ClientId"]
            username = "local-admin"
            password = "LocalOnly-" + uuid.uuid4().hex + "!aA9"
            cognito.admin_create_user(
                UserPoolId=pool_id, Username=username, MessageAction="SUPPRESS"
            )
            cognito.admin_set_user_password(
                UserPoolId=pool_id, Username=username, Password=password, Permanent=True
            )
            tokens = cognito.initiate_auth(
                ClientId=client_id,
                AuthFlow="USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": username, "PASSWORD": password},
            )["AuthenticationResult"]
            verify_tokens(endpoint, pool_id, client_id, tokens)
            try:
                cognito.initiate_auth(
                    ClientId=client_id,
                    AuthFlow="USER_PASSWORD_AUTH",
                    AuthParameters={
                        "USERNAME": username,
                        "PASSWORD": "Wrong-Local-123!",
                    },
                )
            except ClientError as error:
                assert error.response["Error"]["Code"] == "NotAuthorizedException"
            else:
                raise AssertionError("Wrong password was accepted")
            results["cognito_login_jwks_rs256_tamper_wrong_password"] = "passed"
        if lifecycle:
            for phase in ("restart", "recreate"):
                if phase == "restart":
                    compose("restart", "aws-local")
                else:
                    compose("down")  # Keep the named volume.
                compose("up", "-d", "--wait", "--wait-timeout", "90")
                read_data()
                if data_only:
                    results[phase + "_data"] = "passed"
                else:
                    cognito.admin_get_user(UserPoolId=pool_id, Username=username)
                    verify_tokens(endpoint, pool_id, client_id, tokens)
                    results[phase + "_data_user_signing_key"] = "passed"
    finally:
        actions = []
        if pool_id:
            actions.append(lambda: cognito.delete_user_pool(UserPoolId=pool_id))
        if bucket_created:
            actions.extend(
                [
                    lambda: s3.delete_object(Bucket=name, Key="fixture.txt"),
                    lambda: s3.delete_bucket(Bucket=name),
                ]
            )
        if table_created:
            actions.append(lambda: dynamodb.delete_table(TableName=name))
        for action in actions:
            try:
                action()
            except (BotoCoreError, ClientError) as error:
                cleanup_errors.append(type(error).__name__)
        for client in (dynamodb, s3, cognito):
            client.close()
        if cleanup_errors:
            print(
                "Fixture cleanup failed: " + ", ".join(cleanup_errors), file=sys.stderr
            )
    if cleanup_errors:
        raise RuntimeError("Local fixtures could not be completely removed")
    results["fixture_cleanup"] = "passed"
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Check DynamoDB/S3 only; explicitly leave Cognito unverified",
    )
    parser.add_argument(
        "--lifecycle",
        action="store_true",
        help="Restart/recreate the project container",
    )
    args = parser.parse_args()
    try:
        results = run_checks(args.endpoint, args.lifecycle, args.data_only)
    except (
        BotoCoreError,
        ClientError,
        ValueError,
        AssertionError,
        jwt.PyJWTError,
        OSError,
        subprocess.SubprocessError,
        KeyError,
        StopIteration,
    ) as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
