from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


def _yaml_settings() -> dict[str, Any]:
    """Load optional KuSys YAML defaults.

    Environment variables deliberately take precedence because this callable is placed after
    the environment and dotenv sources in ``settings_customise_sources``.
    """
    path = Path(os.getenv("KUSYS_CONFIG_FILE", "config/kusys.yaml"))
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    storage = raw.get("storage") or {}
    security = raw.get("security") or {}
    documents = raw.get("documents") or {}
    runtime = raw.get("runtime") or {}
    planning = raw.get("planning") or {}
    offers = raw.get("offers") or {}
    analysis = raw.get("analysis") or {}
    mappings = {
        "storage_path": storage.get("path"),
        "session_idle_minutes": security.get("session_idle_minutes"),
        "session_absolute_hours": security.get("session_absolute_hours"),
        "failed_login_threshold": security.get("failed_login_threshold"),
        "base_lock_seconds": security.get("base_lock_seconds"),
        "csrf_required": security.get("csrf_required"),
        "secure_cookies": security.get("secure_cookies"),
        "ocr_threshold_chars_per_page": documents.get("ocr_threshold_chars_per_page"),
        "max_upload_bytes": documents.get("max_upload_bytes"),
        "max_pdf_pages": documents.get("max_pdf_pages"),
        "hours_per_day_default": planning.get("hours_per_day_default"),
        "vat_percent_default": offers.get("vat_percent_default"),
        "four_eyes_default": offers.get("four_eyes_default"),
        "analysis_max_chars": analysis.get("max_chars"),
        "app_version": runtime.get("app_version"),
    }
    for key, value in mappings.items():
        if value is not None:
            result[key] = value
    return result


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KUSYS_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./kusys-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: Path = Path("./artifacts")
    master_key: str = "development-only-change-me"
    session_idle_minutes: int = 480
    session_absolute_hours: int = 24
    failed_login_threshold: int = 5
    base_lock_seconds: int = 300
    csrf_required: bool = True
    secure_cookies: bool = False
    inline_jobs: bool = True
    frontend_origin: str = "http://localhost:5173"
    ocr_threshold_chars_per_page: int = 120
    max_upload_bytes: int = 200 * 1024 * 1024
    max_pdf_pages: int = 500
    hours_per_day_default: int = 8
    vat_percent_default: float = 19.0
    four_eyes_default: bool = True
    analysis_max_chars: int = 60_000
    app_version: str = "1.0.0"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return init_settings, env_settings, dotenv_settings, _yaml_settings, file_secret_settings


@lru_cache
def get_settings() -> Settings:
    return Settings()
