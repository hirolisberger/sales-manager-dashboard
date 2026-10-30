"""Explicit configuration loading with local/AWS storage boundaries."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_ENDPOINTS = {"http://127.0.0.1:4566", "http://localhost:4566"}
DEFAULT_LOCAL_ENDPOINT = "http://127.0.0.1:4566"


class ConfigurationError(ValueError):
    """A public startup error that never includes configuration values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_env: Literal["local", "test", "aws"] = Field(
        default="local", validation_alias="APP_ENV"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    aws_region: str = Field(
        default="ap-northeast-1",
        validation_alias="AWS_REGION",
        pattern=r"^[a-z]{2}(?:-[a-z]+)+-[1-9][0-9]*$",
    )
    aws_endpoint_url: str | None = Field(
        default=None, validation_alias="AWS_ENDPOINT_URL"
    )
    dynamodb_table: str = Field(
        default="sales-manager-local",
        validation_alias="DYNAMODB_TABLE",
        pattern=r"^[A-Za-z0-9_.-]{3,255}$",
    )
    store_id: str = Field(
        default="demo", validation_alias="STORE_ID", pattern=r"^[a-z0-9-]{1,32}$"
    )

    @model_validator(mode="after")
    def check_environment_boundary(self) -> Self:
        if self.app_env == "aws":
            if "aws_region" not in self.model_fields_set:
                raise ValueError("AWS_REGION is required in aws mode")
            if self.aws_endpoint_url is not None:
                raise ValueError("Endpoint overrides are forbidden in aws mode")
        elif self.aws_endpoint_url is not None:
            if self.aws_endpoint_url.removesuffix("/") not in LOCAL_ENDPOINTS:
                raise ValueError("Local mode requires an explicit loopback endpoint")
        return self

    @property
    def endpoint_url(self) -> str | None:
        if self.app_env == "aws":
            return None
        if self.aws_endpoint_url is None:
            return DEFAULT_LOCAL_ENDPOINT
        return self.aws_endpoint_url.removesuffix("/")


def load_settings(env_file: Path | None = None) -> Settings:
    """OS environment overrides the explicitly chosen dotenv; no implicit file."""
    try:
        if env_file is not None and not env_file.is_file():
            raise OSError("Missing settings file")
        return Settings(_env_file=env_file)
    except ValueError, OSError:
        raise ConfigurationError(
            "設定を読み込めません。指定ファイルとAPP_ENV・LOG_LEVEL・"
            "AWS_REGION・AWS_ENDPOINT_URL・DYNAMODB_TABLE・STORE_IDを確認してください。"
        ) from None
