"""Shared pytest fixtures. Tests never read the developer's .env or OS env."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings, load_settings
from app.main import create_app


def build_settings(**overrides: str) -> Settings:
    env = {"APP_ENV": "dev", "DATA_MODE": "mock", "MOCK_DIR": str(REPO_ROOT / "data" / "mock")}
    env.update(overrides)
    return load_settings(env=env, env_file=None)


@pytest.fixture
def make_settings() -> Callable[..., Settings]:
    return build_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return build_settings(REPORTS_DIR=str(tmp_path / "reports"))


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client
