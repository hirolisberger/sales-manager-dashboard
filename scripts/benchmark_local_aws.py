"""Compare cached-image startup and idle resource usage in disposable containers."""

import argparse
import json
import os
import re
import statistics
import subprocess
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from verify_local_aws import REGION, ROOT, local_session

IMAGES = {
    "ministack": "ministackorg/ministack:1.5.33@sha256:"
    "b58186186515a372798ccf0ca9975c295db219b5a811975337d6967b968e07b4",
    "localstack": "localstack/localstack:2026.8.2@sha256:"
    "3fe5b51caec82b966a34485b5b43efd68075ff8161f9b0a34091fad9abb0ff82",
}


def docker(*args: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=75,
    )
    if result.returncode:
        # Docker diagnostics may contain environment values; never print them.
        raise RuntimeError(f"Docker {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def localstack_env() -> dict:
    env = os.environ.copy()
    token = None
    for line in (ROOT / ".env.localstack").read_text().splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key.strip() == "LOCALSTACK_AUTH_TOKEN":
            token = value.strip().strip("\"'")
    if not token:
        raise ValueError("Set LOCALSTACK_AUTH_TOKEN in ignored .env.localstack")
    env["LOCALSTACK_AUTH_TOKEN"] = token
    return env


def mem_mib(value: str) -> float:
    match = re.fullmatch(r"([\d.]+)\s*([A-Za-z]+)", value.strip())
    if not match:
        raise ValueError("Unexpected Docker memory format")
    amount, unit = match.groups()
    factors = {
        "B": 1,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
    }
    return float(amount) * factors[unit] / 1024**2


def measure(kind: str, number: int, env: dict) -> dict:
    name = f"sales-manager-day03-bench-{kind}-{uuid.uuid4().hex[:10]}"
    args = [
        "create",
        "--name",
        name,
        "--no-healthcheck",
        "--cpus",
        "2",
        "--memory",
        "1g",
        "--publish",
        "127.0.0.1::4566",
        "--env",
        "SERVICES=dynamodb,s3",
        "--env",
        f"AWS_DEFAULT_REGION={REGION}",
    ]
    if kind == "ministack":
        args += [
            "--env",
            f"MINISTACK_REGION={REGION}",
            "--env",
            "LOG_LEVEL=WARNING",
            "--env",
            "PERSIST_STATE=0",
            "--env",
            "S3_PERSIST=0",
        ]
    else:
        args += [
            "--env",
            "LOCALSTACK_AUTH_TOKEN",
            "--env",
            "DEBUG=0",
            "--env",
            "LS_LOG=warn",
            "--env",
            "PERSISTENCE=0",
        ]
    args.append(IMAGES[kind])
    docker(*args, env=env)
    clients = []
    try:
        started = time.perf_counter()
        docker("start", name)
        ports = json.loads(
            docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", name)
        )["4566/tcp"]
        assert len(ports) == 1 and ports[0]["HostIp"] == "127.0.0.1"
        port = int(ports[0]["HostPort"])
        assert 1024 <= port <= 65535
        endpoint = f"http://127.0.0.1:{port}"
        opener = build_opener(ProxyHandler({}))
        health_path = (
            "/_ministack/health" if kind == "ministack" else "/_localstack/health"
        )
        deadline = started + 60
        while True:
            try:
                with opener.open(endpoint + health_path, timeout=0.5) as response:
                    if response.status == 200:
                        break
            except OSError, URLError:
                pass
            if time.perf_counter() > deadline:
                raise RuntimeError(f"{kind} HTTP readiness timed out")
            time.sleep(0.1)
        http_seconds = time.perf_counter() - started

        session = local_session()
        config = Config(
            region_name=REGION,
            proxies={},
            connect_timeout=0.5,
            read_timeout=2,
            retries={"total_max_attempts": 1},
            s3={"addressing_style": "path"},
        )
        clients = [
            session.client(service, endpoint_url=endpoint, config=config)
            for service in ("dynamodb", "s3")
        ]
        while True:
            try:
                if kind == "localstack":
                    with opener.open(endpoint + "/_localstack/info", timeout=1) as r:
                        if json.load(r).get("is_license_activated") is not True:
                            raise RuntimeError("License activation not ready")
                clients[0].list_tables()
                clients[1].list_buckets()
                break
            except BotoCoreError, ClientError, OSError, RuntimeError:
                if time.perf_counter() > deadline:
                    raise RuntimeError(f"{kind} API readiness timed out") from None
                time.sleep(0.1)
        api_seconds = time.perf_counter() - started

        # Do not compare startup activity with an already-idle process.
        time.sleep(5)
        samples = []
        for _ in range(3):
            stats = json.loads(
                docker("stats", "--no-stream", "--format", "{{json .}}", name)
            )
            samples.append(
                {
                    "memory_mib": round(mem_mib(stats["MemUsage"].split("/")[0]), 3),
                    "cpu_percent": float(stats["CPUPerc"].removesuffix("%")),
                }
            )
        result = {
            "emulator": kind,
            "trial": number,
            "http_ready_seconds": round(http_seconds, 3),
            "api_ready_seconds": round(api_seconds, 3),
            "idle_samples": samples,
            "idle_memory_mib_median": statistics.median(
                s["memory_mib"] for s in samples
            ),
            "idle_cpu_percent_median": statistics.median(
                s["cpu_percent"] for s in samples
            ),
        }
        print(json.dumps(result), flush=True)
        return result
    finally:
        for client in clients:
            client.close()
        # This unique container has no project volumes or business data.
        docker("rm", "--force", "--volumes", name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".cache/day03-benchmark.json")
    )
    args = parser.parse_args()
    env = localstack_env()
    engine = docker("version", "--format", "{{.Server.Version}}")
    images = {}
    for kind, image in IMAGES.items():
        metadata = json.loads(
            docker("image", "inspect", "--format", "{{json .}}", image)
        )
        images[kind] = {
            "reference": image,
            "architecture": metadata["Architecture"],
            "docker_inspect_size_bytes": metadata["Size"],
        }
    counts = {kind: 0 for kind in IMAGES}
    trials = []
    # Serial execution, alternating the first emulator in each pair.
    for kind in (
        "ministack",
        "localstack",
        "localstack",
        "ministack",
        "ministack",
        "localstack",
    ):
        counts[kind] += 1
        trials.append(measure(kind, counts[kind], env))
    fields = [
        "http_ready_seconds",
        "api_ready_seconds",
        "idle_memory_mib_median",
        "idle_cpu_percent_median",
    ]
    summary = {
        kind: {
            field: statistics.median(t[field] for t in trials if t["emulator"] == kind)
            for field in fields
        }
        for kind in IMAGES
    }
    output = {
        "docker_engine": engine,
        "images": images,
        "method": {
            "services": ["dynamodb", "s3"],
            "cpu_limit": 2,
            "memory_limit_mib": 1024,
            "trials_per_emulator": 3,
            "start": "Before docker start; image pull and container creation excluded",
            "http_ready": "First HTTP 200, external polling every 0.1s",
            "api_ready": (
                "License active (LocalStack), ListTables and ListBuckets succeed"
            ),
            "idle": "5s after API readiness, three docker stats --no-stream samples",
            "healthchecks": "Disabled; common external readiness checks used instead",
            "persistence": "Disabled; new container and empty data for each trial",
            "execution_order": [t["emulator"] for t in trials],
            "image_size": (
                "docker image inspect .Size; not download time or deduplicated usage"
            ),
        },
        "trials": trials,
        "summary_medians": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
