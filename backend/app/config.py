"""Environment-based configuration (shared seam with Member 1).

Values come from real environment variables first, then from the repository's
``.env`` file (python-dotenv, never overriding the real environment), then
from the development defaults below. Paths are resolved relative to the
repository root, not the current working directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]

APP_ENVS = ("dev", "prod")
DATA_MODES = ("mock", "real")
MOCK_SCENARIOS = ("normal", "sparse", "short")
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

DEFAULTS: dict[str, str] = {
    "APP_NAME": "TrendTrace",
    "APP_ENV": "dev",
    "DATA_MODE": "mock",
    "DATA_VERSION": "",
    "CONTRACT_VERSION": "1.0",
    "PORT": "8000",
    "LOG_LEVEL": "INFO",
    "ALLOWED_ORIGIN": "http://localhost:5173",
    "REPORTS_DIR": "reports",
    "MOCK_DIR": "data/mock",
    "MOCK_SCENARIO": "normal",
    "PROCESSED_DIR": "data/processed",
    "MAX_BODY_BYTES": "65536",
    "LLM_API_KEY": "",
    "LLM_PROVIDER": "",
    "LLM_MODEL": "",
}


class ConfigError(ValueError):
    """Raised when configuration values are invalid."""


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    data_mode: str
    data_version_pin: str
    contract_version: str
    port: int
    log_level: str
    allowed_origin: str
    reports_dir: Path
    mock_dir: Path
    mock_scenario: str
    processed_dir: Path
    max_body_bytes: int
    llm_api_key_set: bool
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: str = field(default="", repr=False)

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


def _resolve_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ConfigError(f"{name} must be one of {allowed}, got {value!r}")
    return value


def _positive_int(name: str, value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc
    if number <= 0:
        raise ConfigError(f"{name} must be positive, got {number}")
    return number


def _origin(raw: str) -> str:
    """One browser origin, exactly as the browser sends it: scheme://host[:port], nothing else.

    A trailing "/", a path or a comma-separated list never matches the browser's Origin header, so the
    frontend would be blocked silently; refuse it at startup instead (audit LOW).
    """
    origin = raw.strip()
    try:
        parts = urlsplit(origin)
        is_plain_origin = (parts.scheme in ("http", "https") and bool(parts.hostname)
                           and f"{parts.scheme}://{parts.netloc}" == origin
                           and parts.username is None and parts.password is None
                           and not parts.path and not parts.query and not parts.fragment
                           and not any(c.isspace() or c in "*," for c in origin))
        if parts.port is not None and not 1 <= parts.port <= 65535:
            is_plain_origin = False
    except ValueError:
        is_plain_origin = False
    if not is_plain_origin:
        raise ConfigError("ALLOWED_ORIGIN must be one explicit HTTP(S) origin without a path or wildcard")
    return origin


def _merged_env(env: Mapping[str, str] | None, env_file: Path | None) -> dict[str, str]:
    if env is not None:
        return {**DEFAULTS, **{k: v for k, v in env.items() if v is not None}}
    file_values: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        file_values = {k: v for k, v in dotenv_values(env_file).items() if v is not None}
    return {**DEFAULTS, **file_values, **os.environ}


def load_settings(
    env: Mapping[str, str] | None = None,
    env_file: Path | None = REPO_ROOT / ".env",
) -> Settings:
    """Build validated settings. Pass ``env`` in tests to avoid reading the OS env."""
    raw = _merged_env(env, env_file)
    origin = _origin(raw["ALLOWED_ORIGIN"])
    port = _positive_int("PORT", raw["PORT"])
    if port > 65535:
        raise ConfigError("PORT must be between 1 and 65535")
    return Settings(
        app_name=raw["APP_NAME"].strip() or DEFAULTS["APP_NAME"],
        app_env=_choice("APP_ENV", raw["APP_ENV"].strip().lower(), APP_ENVS),
        data_mode=_choice("DATA_MODE", raw["DATA_MODE"].strip().lower(), DATA_MODES),
        data_version_pin=raw["DATA_VERSION"].strip(),
        contract_version=raw["CONTRACT_VERSION"].strip() or "1.0",
        port=port,
        log_level=_choice("LOG_LEVEL", raw["LOG_LEVEL"].strip().upper(), LOG_LEVELS),
        allowed_origin=origin,
        reports_dir=_resolve_path(raw["REPORTS_DIR"]),
        mock_dir=_resolve_path(raw["MOCK_DIR"]),
        mock_scenario=_choice("MOCK_SCENARIO", raw["MOCK_SCENARIO"].strip().lower(), MOCK_SCENARIOS),
        processed_dir=_resolve_path(raw["PROCESSED_DIR"]),
        max_body_bytes=_positive_int("MAX_BODY_BYTES", raw["MAX_BODY_BYTES"]),
        llm_api_key_set=bool(raw.get("LLM_API_KEY", "").strip()),
        llm_provider=raw.get("LLM_PROVIDER", "").strip().lower(),
        llm_model=raw.get("LLM_MODEL", "").strip(),
        llm_api_key=raw.get("LLM_API_KEY", "").strip(),
    )


def check_startup_rules(settings: Settings) -> None:
    """Hard safety rules checked before the app serves requests.

    [RULE] The app refuses to start with APP_ENV=prod and DATA_MODE=mock.
    """
    if settings.is_prod and settings.data_mode == "mock":
        raise ConfigError("Refusing to start: APP_ENV=prod with DATA_MODE=mock is not allowed")
