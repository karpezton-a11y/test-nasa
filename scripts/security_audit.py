#!/usr/bin/env python
"""Scan source and reachable Git-history blobs without printing secret values.

Heuristic check, not a provider validation or vulnerability database scan.
Run: python scripts/security_audit.py
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "provider_key": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "key_assignment": re.compile(r"(?im)^\s*(?:LLM_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|GITHUB_TOKEN)\s*=\s*[\"']?([A-Za-z0-9_-]{20,})"),
}
EXCLUDE = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "snapshot", "htmlcov", "__MACOSX"}


def scan_bytes(content: bytes, location: str) -> list[dict]:
    text = content.decode("utf-8", errors="replace")
    return [{"location": location, "kind": kind} for kind, pattern in PATTERNS.items() if pattern.search(text)]


def _git(*args, **kwargs):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, **kwargs)


def run() -> dict:
    findings = []
    history_blobs = 0
    if (ROOT / ".git").exists():
        names = _git("ls-files", "-co", "--exclude-standard", "-z").stdout.decode().split("\0")
        files = sorted(set(n for n in names if n and (ROOT / n).is_file()))
        listed = _git("rev-list", "--objects", "--all").stdout.decode().splitlines()
        objects = {line.split(" ", 1)[0]: line.split(" ", 1)[1] if " " in line else "(commit/tree)" for line in listed}
        # cat-file's length-delimited batch format prevents blob contents from
        # being interpreted as commands. Never echo data or matched tokens.
        batch = _git("cat-file", "--batch", input=("\n".join(objects) + "\n").encode()).stdout
        offset = 0
        for _ in objects:
            end = batch.index(b"\n", offset)
            oid, kind, size = batch[offset:end].decode().split()
            start, length = end + 1, int(size)
            body = batch[start:start + length]
            offset = start + length + 1
            if kind == "blob":
                history_blobs += 1
                findings += scan_bytes(body, f"git:{oid[:12]}:{objects[oid]}")
        history = "reachable branches/tags scanned"
    else:
        files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()
                 and not set(p.relative_to(ROOT).parts) & EXCLUDE
                 and (not p.name.startswith(".env") or p.name == ".env.example")
                 and (p.relative_to(ROOT).parts[:2] != ("data", "raw") or p.name == "provenance.csv")]
        history = "unavailable (.git not included)"
    for name in files:
        findings += scan_bytes((ROOT / name).read_bytes(), name)
    pins = [line for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", pin) for pin in pins):
        findings.append({"location": "requirements.txt", "kind": "unpinned_direct_dependency"})
    if (ROOT / ".python-version").read_text().strip() != "3.11":
        findings.append({"location": ".python-version", "kind": "python_pin_mismatch"})
    return {"source_files_scanned": len(files), "history_blobs_scanned": history_blobs,
            "history": history, "findings": findings}


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2))
    raise SystemExit(bool(report["findings"]))
