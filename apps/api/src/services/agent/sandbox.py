"""Session-scoped file workspace management for agent uploads."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import UUID


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_SESSION_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT_SEC = 30
MAX_TIMEOUT_SEC = 120
DEFAULT_MEM_BYTES = 256 * 1024 * 1024
DEFAULT_TTL_SEC = 3600

ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".csv", ".txt", ".json", ".xml", ".xlsx"}
BLOCKED_UPLOAD_EXTENSIONS = {
    ".exe",
    ".dll",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".pyc",
    ".zip",
    ".tar",
    ".gz",
    ".rar",
    ".7z",
}


def _validate_session_id(session_id: str) -> str:
    try:
        UUID(session_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid session_id") from exc
    return session_id


def _sanitize_filename(filename: str) -> str:
    safe = os.path.basename((filename or "").strip())
    safe = safe.replace("\\", "_").replace("/", "_")
    if not safe or safe in {".", ".."}:
        raise ValueError("Invalid filename")
    if len(safe) > 255:
        base, ext = os.path.splitext(safe)
        safe = f"{base[:200]}{ext[:20]}"
    return safe


def _safe_join(directory: Path, filename: str) -> Path:
    safe_name = _sanitize_filename(filename)
    target = (directory / safe_name).resolve()
    base = directory.resolve()
    if not str(target).startswith(str(base) + os.sep):
        raise ValueError("Invalid filename path")
    return target


def _list_files_with_sizes(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        return []
    files: list[dict[str, Any]] = []
    for p in sorted(directory.iterdir(), key=lambda item: item.name):
        if p.is_file():
            files.append({"filename": p.name, "size_bytes": p.stat().st_size})
    return files


class SandboxManager:
    """Manage per-session file workspace for uploaded files."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        ttl_sec: int = DEFAULT_TTL_SEC,
        memory_bytes: int = DEFAULT_MEM_BYTES,
    ) -> None:
        base = Path(root_dir) if root_dir is not None else Path(tempfile.gettempdir()) / "bimatlas-sandbox"
        self.root_dir = base
        self.ttl_sec = ttl_sec
        self.memory_bytes = memory_bytes
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _session_root(self, session_id: str) -> Path:
        sid = _validate_session_id(session_id)
        return self.root_dir / sid

    def _ensure_session_dirs(self, session_id: str) -> dict[str, Path]:
        root = self._session_root(session_id)
        uploads = root / "uploads"
        for p in (root, uploads):
            p.mkdir(parents=True, exist_ok=True)
        now = time.time()
        os.utime(root, (now, now))
        return {"root": root, "uploads": uploads}

    def cleanup_expired_sessions(self) -> int:
        if not self.root_dir.exists():
            return 0
        now = time.time()
        removed = 0
        for child in self.root_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                age = now - child.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > self.ttl_sec:
                self._delete_tree(child)
                removed += 1
        return removed

    def _delete_tree(self, path: Path) -> None:
        if not path.exists():
            return
        for p in sorted(path.rglob("*"), reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    p.rmdir()
            except Exception:
                continue
        try:
            path.rmdir()
        except Exception:
            pass

    def _session_total_bytes(self, root: Path) -> int:
        total = 0
        for p in root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def save_upload(self, session_id: str, filename: str, content: bytes) -> dict[str, Any]:
        self.cleanup_expired_sessions()
        dirs = self._ensure_session_dirs(session_id)
        root, uploads = dirs["root"], dirs["uploads"]
        safe_name = _sanitize_filename(filename)
        ext = Path(safe_name).suffix.lower()
        if ext in BLOCKED_UPLOAD_EXTENSIONS:
            raise ValueError(f"Blocked file type: {ext}")
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            allowed = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            raise ValueError(f"Unsupported file type: {ext}. Allowed: {allowed}")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError(f"File too large: max {MAX_FILE_BYTES} bytes")
        existing_total = self._session_total_bytes(root)
        if existing_total + len(content) > MAX_SESSION_BYTES:
            raise ValueError(f"Session storage quota exceeded: max {MAX_SESSION_BYTES} bytes")

        target = _safe_join(uploads, safe_name)
        target.write_bytes(content)
        return {"filename": safe_name, "size_bytes": target.stat().st_size}

    def list_uploads(self, session_id: str) -> list[dict[str, Any]]:
        self.cleanup_expired_sessions()
        uploads = self._session_root(session_id) / "uploads"
        return _list_files_with_sizes(uploads)

    def read_upload(self, session_id: str, filename: str) -> bytes:
        self.cleanup_expired_sessions()
        uploads = self._session_root(session_id) / "uploads"
        target = _safe_join(uploads, filename)
        if not target.exists():
            raise FileNotFoundError(filename)
        return target.read_bytes()

    def cleanup_session(self, session_id: str) -> None:
        self._delete_tree(self._session_root(session_id))


sandbox_manager = SandboxManager()
