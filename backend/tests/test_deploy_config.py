"""Step 7: hosting config stays consistent with the app and the safety rules."""

from __future__ import annotations

import py_compile

from app.config import REPO_ROOT

START = "uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT"


def test_render_blueprint_serves_real_data_on_staging():
    text = (REPO_ROOT / "render.yaml").read_text()
    assert f"startCommand: {START}" in text
    assert "healthCheckPath: /api/v1/health" in text
    assert "key: APP_ENV\n        value: dev" in text and "key: DATA_MODE\n        value: real" in text
    assert (REPO_ROOT / "data" / "processed" / "manifest.json").is_file()  # real mode needs the delivered files
    assert "value: prod" not in text  # prod + mock is refused by the app; staging must stay dev
    assert "key: LLM_API_KEY\n        sync: false" in text  # secrets never committed


def test_procfile_python_pin_and_requirements_agree():
    assert (REPO_ROOT / "Procfile").read_text().strip() == f"web: {START}"
    assert (REPO_ROOT / ".python-version").read_text().strip() == "3.11"
    pins = [line for line in (REPO_ROOT / "requirements.txt").read_text().splitlines()
            if line and not line.startswith("#")]
    assert pins and all("==" in line for line in pins)


def test_operational_scripts_compile():
    for name in ("smoke_test.py", "export_static_snapshot.py", "make_sample_report.py", "render_pdf_pages.py"):
        py_compile.compile(str(REPO_ROOT / "scripts" / name), doraise=True)


def test_env_example_has_no_secrets_and_lists_every_setting():
    text = (REPO_ROOT / ".env.example").read_text()
    for key in ("APP_NAME", "APP_ENV", "DATA_MODE", "MOCK_SCENARIO", "DATA_VERSION", "CONTRACT_VERSION", "PORT",
                "LOG_LEVEL", "ALLOWED_ORIGIN", "REPORTS_DIR", "MOCK_DIR", "PROCESSED_DIR", "MAX_BODY_BYTES",
                "LLM_API_KEY"):
        assert f"\n{key}=" in text or text.startswith(f"{key}=")
    assert "LLM_API_KEY=\n" in text
