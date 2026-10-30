"""Construct explicit clients; local mode never uses personal AWS credentials."""

import os

import boto3
from botocore.config import Config
from botocore.session import Session as CoreSession

from sales_manager_api.settings import Settings


def dynamodb_client(settings: Settings):
    local = settings.app_env in {"local", "test"}
    options = {
        "region_name": settings.aws_region,
        "ignore_configured_endpoint_urls": True,
        "use_fips_endpoint": False,
        "use_dualstack_endpoint": False,
        "account_id_endpoint_mode": "disabled",
        "connect_timeout": 2,
        "read_timeout": 5,
        "retries": {"mode": "standard", "total_max_attempts": 1},
    }
    if local:
        core = CoreSession()
        # Per-session overrides, including None for profile; no os.environ edits.
        # ConfigValueStore is pinned/tested together with botocore.
        config = core.get_component("config_store")
        config.set_config_variable("profile", None)
        config.set_config_variable("config_file", os.devnull)
        config.set_config_variable("credentials_file", os.devnull)
        core.set_credentials("test", "test", "")
        session = boto3.Session(botocore_session=core, region_name=settings.aws_region)
        options["proxies"] = {}
    else:
        # Real AWS uses the standard credential chain (e.g. an execution role).
        # No real AWS connection is made by the local management CLI.
        session = boto3.Session(region_name=settings.aws_region)
    return session.client(
        "dynamodb", endpoint_url=settings.endpoint_url, config=Config(**options)
    )
