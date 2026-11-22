"""Next.js -> real Python API -> MiniStack, using a disposable table and ports."""

import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
from uuid import uuid4

from sales_manager_api.aws import dynamodb_client
from sales_manager_api.bootstrap import ensure_table
from sales_manager_api.repository import call
from sales_manager_api.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
HTTP = build_opener(ProxyHandler({}))


def port():
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        return bound.getsockname()[1]


def request(url):
    try:
        with HTTP.open(url, timeout=15) as response:
            return response.status, response.read().decode()
    except HTTPError as error:
        return error.code, error.read().decode()


def wait_server(process, url):
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("Verification server exited; inspect .cache/day11-live")
        try:
            if request(url)[0] == 200:
                return
        except URLError, TimeoutError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Verification server startup timed out")


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def verify():
    out = ROOT / ".cache/day11-live"
    out.mkdir(parents=True, exist_ok=True)
    node = ROOT / ".tools/node-v24.22.2-darwin-arm64/bin/node"
    if not node.exists():
        import shutil

        node = Path(shutil.which("node") or "")
    if not node.is_file():
        raise RuntimeError("Node.js 24 is required")
    table = "sales-manager-test-day11-" + uuid4().hex[:12]
    settings = Settings(
        APP_ENV="test",
        DYNAMODB_TABLE=table,
        STORE_ID="demo",
        AWS_REGION="ap-northeast-1",
        AWS_ENDPOINT_URL="http://127.0.0.1:4566",
    )
    sdk = dynamodb_client(settings)
    created, api, web = False, None, None
    api_port, web_port = port(), port()
    api_url, web_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    env = {
        **os.environ,
        "APP_ENV": "test",
        "DYNAMODB_TABLE": table,
        "STORE_ID": "demo",
        "AWS_REGION": "ap-northeast-1",
        "AWS_ENDPOINT_URL": "http://127.0.0.1:4566",
        "API_BASE_URL": api_url,
    }
    checks = []
    try:
        assert ensure_table(sdk, settings), "Unexpected existing verification table"
        created = True
        with (
            (out / "api.log").open("w") as api_log,
            (out / "next.log").open("w") as web_log,
        ):
            api = subprocess.Popen(
                [
                    str(ROOT / "apps/api/.venv/bin/sales-manager-api"),
                    "--env-file",
                    "apps/api/.env.example",
                    "--port",
                    str(api_port),
                ],
                cwd=ROOT,
                env=env,
                stdout=api_log,
                stderr=subprocess.STDOUT,
            )
            wait_server(api, api_url + "/health")
            web = subprocess.Popen(
                [
                    str(node),
                    "node_modules/next/dist/bin/next",
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=ROOT / "apps/web",
                env=env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
            )
            wait_server(web, web_url + "/connection")
            code, html = request(web_url + "/")
            assert code == 200 and "商品はまだ登録されていません" in html
            checks.append("production_empty_real_table")
            from urllib.request import Request

            command_doc = (ROOT / "docs/DAY11_COMMANDS.md").read_text()
            section = command_doc.split("## 5.")[1].split("## 6.")[0]
            fence = chr(96) * 3
            blocks = re.findall(fence + r"sh\n(.*?)\n" + fence, section, re.S)
            assert len(blocks) == 1
            command = (
                blocks[0]
                .replace("http://127.0.0.1:8000", api_url)
                .replace(".cache/day11-", ".cache/day11-live-doc-")
            )
            commands = subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", command],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            (out / "document-command-output.txt").write_text(
                commands.stdout + commands.stderr
            )
            assert (
                commands.returncode == 0 and commands.stdout.splitlines() == ["201"] * 3
            )
            products = [
                json.loads(
                    (ROOT / f".cache/day11-live-doc-product{number}.json").read_text()
                )
                for number in [1, 2, 3]
            ]
            for number in [4]:
                body = {
                    "code": f"REVIEW11-{number}",
                    "name": f"確認用商品{number}",
                    "default_unit_price_yen": 550,
                }
                req = Request(
                    api_url + "/products",
                    data=json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "Idempotency-Key": str(uuid4()),
                    },
                    method="POST",
                )
                with HTTP.open(req, timeout=10) as response:
                    assert response.status == 201
                    products.append(json.loads(response.read()))
            code, html = request(web_url + "/")
            expected = sorted(products, key=lambda p: p["id"])[:3]
            assert code == 200 and all(p["name"] in html for p in expected)
            assert html.split("<tbody>")[1].split("</tbody>")[0].count("<tr") == 3
            assert "ほかにも有効な商品が登録されています" in html
            checks.append("real_products_three_rows_and_more_indicator")
            first = expected[0]
            req = Request(
                api_url + "/products/" + first["id"],
                data=json.dumps(
                    {"name": "更新を確認した商品", "default_unit_price_yen": 600}
                ).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(uuid4()),
                    "If-Match": '"v1"',
                },
                method="PATCH",
            )
            with HTTP.open(req, timeout=10) as response:
                assert response.status == 200
            _, html = request(web_url + "/")
            assert "更新を確認した商品" in html and "600" in html
            assert first["name"] not in html
            checks.append("fresh_server_render_after_master_update")
            req = Request(
                api_url + "/products/" + first["id"],
                data=b'{"is_active":false}',
                headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": str(uuid4()),
                    "If-Match": '"v2"',
                },
                method="PATCH",
            )
            with HTTP.open(req, timeout=10) as response:
                assert response.status == 200
            _, html = request(web_url + "/")
            assert "更新を確認した商品" not in html
            checks.append("inactive_products_excluded")
            assert "APIに接続できました" in request(web_url + "/connection")[1]
            checks.append("real_python_health_connection")
            call(sdk, "delete_table", TableName=table)
            sdk.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
            )
            created = False
            assert "データを取得できませんでした" in request(web_url + "/")[1]
            assert "APIに接続できました" in request(web_url + "/connection")[1]
            checks.append("storage_failure_differs_from_health_liveness")
            stop(api)
            assert "データを取得できませんでした" in request(web_url + "/connection")[1]
            checks.append("stopped_python_api_safe_feedback")
            assert request(web_url + "/no-such-page")[0] == 404
            checks.append("production_unknown_page_404")
            stop(web)
            web = subprocess.Popen(
                [
                    str(node),
                    "node_modules/next/dist/bin/next",
                    "dev",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                ],
                cwd=ROOT / "apps/web",
                env=env,
                stdout=web_log,
                stderr=subprocess.STDOUT,
            )
            wait_server(web, web_url + "/connection")
            assert "データを取得できませんでした" in request(web_url + "/")[1]
            checks.append("development_server_common_shell_and_safe_failure")
        return {
            "check_count": len(checks),
            "checks": checks,
            "backend": "real Python API + MiniStack",
            "temporary_table_deleted": True,
            "only_dedicated_servers": True,
            "document_shell_blocks_executed": 1,
        }
    finally:
        stop(web)
        stop(api)
        if created:
            call(sdk, "delete_table", TableName=table)
            sdk.get_waiter("table_not_exists").wait(
                TableName=table, WaiterConfig={"Delay": 1, "MaxAttempts": 20}
            )
        sdk.close()


if __name__ == "__main__":
    result = verify()
    (ROOT / ".cache/day11-live/result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
