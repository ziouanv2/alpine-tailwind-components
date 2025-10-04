from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

ProviderLiteral = Literal["google", "bing"]


class APISettings(BaseModel):
    provider: ProviderLiteral = Field(default="google")
    google_api_key: Optional[str] = None
    google_cx: Optional[str] = None
    bing_subscription_key: Optional[str] = None

    @validator("google_api_key", "google_cx", pre=True, always=True)
    def _default_google_fields(cls, v: Optional[str], values: Dict[str, Any], field):
        if v:
            return v
        env_value = os.getenv(field.name.upper())
        return env_value

    @validator("bing_subscription_key", pre=True, always=True)
    def _default_bing_field(cls, v: Optional[str], values: Dict[str, Any], field):
        if v:
            return v
        return os.getenv(field.name.upper())

    @validator("provider")
    def _validate_provider(cls, v: str) -> str:
        if v not in {"google", "bing"}:
            raise ValueError("provider must be either 'google' or 'bing'")
        return v

    def require_credentials(self) -> None:
        if self.provider == "google":
            if not self.google_api_key or not self.google_cx:
                raise ValueError(
                    "Google Custom Search requires GOOGLE_API_KEY and GOOGLE_CX environment variables"
                )
        elif self.provider == "bing":
            if not self.bing_subscription_key:
                raise ValueError("Bing Web Search requires BING_SUBSCRIPTION_KEY environment variable")


class SearchSettings(BaseModel):
    input_file: Path
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_results_per_keyword: int = 10
    per_site_delay: float = 3.0
    global_rate_limit_qps: float = 1.0
    jitter_seconds: float = 0.5
    user_agent: str = "ResearchCollector/1.0 (+https://example.com/contact)"

    @validator("allowed_domains", "blocked_domains", pre=True)
    def _none_if_empty(cls, v: Optional[List[str]]):
        if v in (None, "", []):
            return None
        return v


class BrowserSettings(BaseModel):
    headless: bool = True
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    timeout_ms: int = 30000
    scroll_step: int = 300
    max_scroll_steps: int = 50
    proxy: Optional[str] = None


class OutputSettings(BaseModel):
    output_format: Literal["jsonl", "csv"] = "jsonl"
    output_path: Optional[Path] = None
    create_timestamp_directory: bool = True


class LoggingSettings(BaseModel):
    level: str = "INFO"


class AppConfig(BaseModel):
    api: APISettings
    search: SearchSettings
    browser: BrowserSettings = BrowserSettings()
    output: OutputSettings = OutputSettings()
    logging: LoggingSettings = LoggingSettings()


@dataclass
class LoadedConfig:
    config: AppConfig
    source_path: Path


def _merge_dict(target: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            target[key] = _merge_dict(target[key], value)
        else:
            target[key] = value
    return target


def load_config(config_path: Path, cli_overrides: Optional[Dict[str, Any]] = None) -> LoadedConfig:
    load_dotenv()
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}

    cli_overrides = cli_overrides or {}
    merged = _merge_dict(raw_config, cli_overrides)

    if "input_file" in merged and "search" not in merged:
        # Backwards compatibility for direct input_file definition at top-level
        merged.setdefault("search", {})["input_file"] = merged.pop("input_file")

    config = AppConfig.parse_obj(merged)
    config.api.require_credentials()

    return LoadedConfig(config=config, source_path=config_path)


__all__ = ["AppConfig", "APISettings", "SearchSettings", "BrowserSettings", "OutputSettings", "LoggingSettings", "load_config", "LoadedConfig"]
