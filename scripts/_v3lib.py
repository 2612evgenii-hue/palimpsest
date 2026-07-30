"""Palimpsest v3 runtime helpers.

The module is intentionally stdlib-only.  Every state mutation goes through an
advisory lock and an atomic replace so parallel readers never observe a
half-written JSON file.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

try:  # macOS/Linux in Codex; the fallback keeps the scripts importable elsewhere.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str | Path) -> str:
    p = Path(path)
    return sha256_bytes(p.read_bytes())


def digest_files(paths: list[str | Path]) -> str:
    """Hash names and contents in caller-provided order."""
    h = hashlib.sha256()
    for raw in paths:
        p = Path(raw).resolve()
        h.update(str(p).encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def atomic_write_text(path: str | Path, text: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{p.name}.", suffix=".tmp", dir=p.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    finally:
        if tmp.exists():
            tmp.unlink()


def atomic_write_json(path: str | Path, value: object) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_json(path: str | Path) -> dict:
    p = Path(path)
    value = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{p}: JSON root must be an object")
    return value


@contextmanager
def locked_json(path: str | Path, *, must_exist: bool = True) -> Iterator[dict]:
    """Load, exclusively lock, yield, then atomically persist a JSON object."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.with_name(p.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if must_exist and not p.exists():
                raise FileNotFoundError(p)
            value = load_json(p) if p.exists() else {}
            yield value
            atomic_write_json(p, value)
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


@contextmanager
def advisory_lock(path: str | Path) -> Iterator[None]:
    """Serialize arbitrary file updates that cannot use ``locked_json``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lock_path = p.with_name(p.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def resolve_existing(path: str | Path) -> Path:
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise FileNotFoundError(p)
    return p


def safe_relative(path: str | Path, base: str | Path) -> str:
    p = Path(path).resolve()
    b = Path(base).resolve()
    try:
        return str(p.relative_to(b))
    except ValueError:
        return str(p)


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for item in value.split(","):
        clean = item.strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
