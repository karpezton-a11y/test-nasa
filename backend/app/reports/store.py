"""Saved-report files: server-generated IDs mapped to files inside REPORTS_DIR only.

IDs are ``rpt_`` + 32 hex chars (secrets.token_hex). Writes are atomic
(temp file + os.replace), so a half-written report is never downloadable.
Files survive app restarts but not a host disk wipe (decision R-5).

Clean-up (audit M1): every save deletes saved reports older than ``max_age_s`` (default 1 hour) and
keeps at most ``max_files`` (default 200, newest kept), so a loop of requests cannot fill the disk.
A deleted report downloads as REPORT_NOT_FOUND; the UI creates it again (R-5).
"""

from __future__ import annotations

import os
import re
import secrets
import logging
import tempfile
import time
from pathlib import Path

from ..errors import api_error

logger = logging.getLogger("trendtrace.reports.store")
REPORT_ID_RE = re.compile(r"^rpt_[0-9a-f]{32}$")
REPORT_MAX_AGE_S = 3600
REPORT_MAX_FILES = 200
NOT_FOUND_MESSAGE = "No report with this ID exists (reports may be removed when the server restarts)."


class ReportFileStore:
    def __init__(self, reports_dir: Path, max_age_s: float = REPORT_MAX_AGE_S,
                 max_files: int = REPORT_MAX_FILES) -> None:
        self._dir = reports_dir.resolve()
        self._max_age_s = max_age_s
        self._max_files = max_files

    @staticmethod
    def new_id() -> str:
        return f"rpt_{secrets.token_hex(16)}"

    def _path(self, report_id: str) -> Path:
        if not REPORT_ID_RE.fullmatch(report_id or ""):
            raise api_error("INVALID_REPORT_ID", "That report ID is not valid.", {"param": "report_id"})
        path = (self._dir / f"{report_id}.pdf").resolve()
        if path.parent != self._dir:
            raise api_error("INVALID_REPORT_ID", "That report ID is not valid.", {"param": "report_id"})
        return path

    def save(self, report_id: str, content: bytes) -> None:
        target = self._path(report_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".tmp-", suffix=".pdf", dir=self._dir)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._remove_old(keep=target)

    def _saved_reports(self) -> list[tuple[float, Path]]:
        """(modified time, path) of saved reports, newest first; files vanishing meanwhile are skipped."""
        found = []
        for path in self._dir.glob("rpt_*.pdf"):
            if not REPORT_ID_RE.fullmatch(path.stem):
                continue
            try:
                found.append((path.stat().st_mtime, path))
            except FileNotFoundError:
                continue
        return sorted(found, key=lambda item: item[0], reverse=True)

    def _remove_old(self, keep: Path) -> None:
        """Best effort: a failed clean-up is logged and never fails the report that was just saved."""
        cutoff = time.time() - self._max_age_s
        try:
            others = [(mtime, path) for mtime, path in self._saved_reports() if path != keep]
        except OSError:
            logger.exception("Could not scan saved reports for cleanup")
            return
        too_old = [path for mtime, path in others if mtime < cutoff]
        too_many = [path for _, path in others[max(self._max_files - 1, 0):]]
        for path in dict.fromkeys([*too_old, *too_many]):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not delete old report %s", path.name)

    def load(self, report_id: str) -> bytes:
        path = self._path(report_id)
        try:
            return path.read_bytes()
        except (FileNotFoundError, IsADirectoryError):  # never saved, cleaned up, or removed mid-download
            raise api_error("REPORT_NOT_FOUND", NOT_FOUND_MESSAGE, {"report_id": report_id}) from None
