"""
Pre-turn SQLite snapshot and LLM-tape crash bundle writer for deterministic turn replay.

Safe for production opt-in (`HIKAYAT_CRASH_CAPTURE=1`) as well as headless playthrough
sweeps: has no hard dependency on `tests/` and scrubs machine-local paths from `repro.json`.
"""
from __future__ import annotations

import dataclasses
import importlib
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CRASH_DIR = REPO_ROOT / "crash_reports"

_IN_CRASH_CAPTURE: ContextVar[bool] = ContextVar("_in_crash_capture", default=False)
_USER_HOME_WIN_RE = re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"':]+", re.IGNORECASE)
_USER_HOME_POSIX_RE = re.compile(r"/(?:Users|home)/[^/\s\"':]+")


def is_in_crash_capture() -> bool:
    """Return True when the current async task is already wrapped by crash capture."""
    return bool(_IN_CRASH_CAPTURE.get())


@contextmanager
def crash_capture_scope():
    """Marks the current context as actively managed by an outer crash-bundle guard."""
    token = _IN_CRASH_CAPTURE.set(True)
    try:
        yield
    finally:
        _IN_CRASH_CAPTURE.reset(token)


def sanitize_repo_paths(text: str) -> str:
    """Replace local filesystem paths in tracebacks/messages with portable tokens."""
    if not text:
        return ""
    cleaned = str(text)
    repo_str = str(REPO_ROOT)
    repo_posix = repo_str.replace("\\", "/")
    home_str = os.path.expanduser("~")
    home_posix = home_str.replace("\\", "/")
    for target, repl in (
        (repo_str, "<repo>"),
        (repo_posix, "<repo>"),
        (home_str, "<home>"),
        (home_posix, "<home>"),
    ):
        if target and len(target) > 2:
            cleaned = re.sub(re.escape(target), repl, cleaned, flags=re.IGNORECASE)
    cleaned = _USER_HOME_WIN_RE.sub("<home>", cleaned)
    cleaned = _USER_HOME_POSIX_RE.sub("<home>", cleaned)
    return cleaned


def to_json_safe(val: Any, _seen: Optional[set[int]] = None) -> Any:
    """Convert arbitrary runtime values (including dataclasses & BaseModels) into JSON-safe objects."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    if isinstance(val, Path):
        return sanitize_repo_paths(str(val))
    if _seen is None:
        _seen = set()
    val_id = id(val)
    if val_id in _seen:
        return None
    _seen.add(val_id)
    try:
        if dataclasses.is_dataclass(val) and not isinstance(val, type):
            return to_json_safe(dataclasses.asdict(val), _seen)
        if hasattr(val, "model_dump") and callable(val.model_dump) and not isinstance(val, type):
            return to_json_safe(val.model_dump(exclude_unset=False), _seen)
        if isinstance(val, dict):
            return {
                str(k): to_json_safe(v, _seen)
                for k, v in val.items()
                if not str(k).startswith("__") and str(k) != "_ctx"
            }
        if isinstance(val, (list, tuple, set, frozenset)):
            return [to_json_safe(v, _seen) for v in val]
        if hasattr(val, "__dict__") and not isinstance(val, type):
            return to_json_safe(vars(val), _seen)
        return sanitize_repo_paths(str(val))
    finally:
        _seen.discard(val_id)


def encode_rng_state(state: Optional[tuple] = None) -> List[Any]:
    """Serialize Python's `random.getstate()` tuple into a JSON-safe list."""
    raw = state if state is not None else random.getstate()
    version, inner_tuple, gauss_next = raw
    return [int(version), [int(x) for x in inner_tuple], gauss_next]


def decode_rng_state(data: Any) -> Optional[tuple]:
    """Reconstruct a valid `random.setstate(...)` tuple from JSON data."""
    if not isinstance(data, (list, tuple)) or len(data) != 3:
        return None
    version, inner_seq, gauss_next = data
    if not isinstance(inner_seq, (list, tuple)):
        return None
    return (int(version), tuple(int(x) for x in inner_seq), gauss_next)


def snapshot_sqlite_to_file(src_db_path: str | Path, dst_db_path: str | Path, *, read_only: bool = True) -> None:
    """Snapshot `src_db_path` (including live WAL pages) into `dst_db_path` without mutating source."""
    src_path = Path(src_db_path).resolve()
    dst_path = Path(dst_db_path).resolve()
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn: Optional[sqlite3.Connection] = None
    dst_conn: Optional[sqlite3.Connection] = None
    try:
        if read_only:
            base_uri = src_path.as_uri()
            try:
                src_conn = sqlite3.connect(f"{base_uri}?mode=ro", uri=True, timeout=30.0)
            except sqlite3.OperationalError:
                src_conn = sqlite3.connect(f"{base_uri}?mode=ro&immutable=1", uri=True, timeout=30.0)
        else:
            src_conn = sqlite3.connect(str(src_path), timeout=30.0)
        dst_conn = sqlite3.connect(str(dst_path), timeout=30.0)
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        if dst_conn is not None:
            try:
                dst_conn.close()
            except Exception:
                pass
        if src_conn is not None:
            try:
                src_conn.close()
            except Exception:
                pass


def load_optional_strict_mode() -> Any:
    """Return `tests.strict_mode` if local test infrastructure is present, else None."""
    if "tests.strict_mode" in sys.modules:
        return sys.modules["tests.strict_mode"]
    if not (REPO_ROOT / "tests" / "strict_mode.py").is_file():
        return None
    try:
        return importlib.import_module("tests.strict_mode")
    except Exception:
        return None


def _slugify(val: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(val or "unknown")).strip("_")
    return (cleaned[:40] or "unknown").lower()


def serialize_strict_hits(hits: Iterable[Any]) -> List[Dict[str, Any]]:
    """Convert `strict_mode.Hit` objects or dicts into JSON-safe dictionaries."""
    out: List[Dict[str, Any]] = []
    for h in hits or []:
        if isinstance(h, dict):
            out.append(to_json_safe(h))
        else:
            out.append({
                "exc_type": str(getattr(h, "exc_type", "")),
                "message": sanitize_repo_paths(str(getattr(h, "message", ""))),
                "raise_site": str(getattr(h, "raise_site", "")),
                "handler_site": str(getattr(h, "handler_site", "")),
            })
    return out


def write_crash_bundle(
    *,
    bundle_root: Path | str | None = None,
    scenario: str = "fantasy",
    session_id: int = 0,
    user_id: int = 0,
    turn_number: int = 0,
    seed: Optional[int] = None,
    stage: str = "resolve_action",
    mode: str = "solo",
    raw_pick: Optional[Dict[str, Any]] = None,
    action: Optional[Dict[str, Any]] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    rng_state_json: Any = None,
    llm_tape: Optional[List[Dict[str, Any]]] = None,
    strict_hits: Optional[Iterable[Any]] = None,
    exc: Optional[BaseException] = None,
    error_summary: str = "",
    oracle_failures: Optional[List[str]] = None,
    pre_turn_db_source: str | Path,
) -> Path:
    """Persist `pre_turn.db` and `repro.json` under `crash_reports/<bundle_id>/`."""
    root = Path(bundle_root) if bundle_root else DEFAULT_CRASH_DIR
    root.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    scen_slug = _slugify(scenario)
    seed_part = f"seed{seed}" if seed is not None else f"sid{int(session_id or 0)}"
    base_name = f"{stamp}_{scen_slug}_{seed_part}_turn{int(turn_number or 0)}"
    bundle_dir = root / base_name
    suffix = 1
    while bundle_dir.exists():
        suffix += 1
        bundle_dir = root / f"{base_name}_{suffix}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    dst_db = bundle_dir / "pre_turn.db"
    src_path = Path(pre_turn_db_source)
    if src_path.is_file() and not Path(str(src_path) + "-wal").is_file():
        shutil.copy2(src_path, dst_db)
    else:
        snapshot_sqlite_to_file(src_path, dst_db, read_only=True)

    tb_str = ""
    if exc is not None:
        tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    serialized_hits = serialize_strict_hits(strict_hits or [])

    repro_payload: Dict[str, Any] = {
        "bundle_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario": str(scenario or "fantasy"),
        "session_id": int(session_id or 0),
        "user_id": int(user_id or 0),
        "turn_number": int(turn_number or 0),
        "seed": seed,
        "rng_state": rng_state_json,
        "stage": str(stage or "resolve_action"),
        "mode": str(mode or "solo"),
        "raw_pick": to_json_safe(raw_pick) if raw_pick is not None else None,
        "action": to_json_safe(action) if action is not None else None,
        "actions": to_json_safe(actions) if actions is not None else None,
        "llm_tape": to_json_safe(list(llm_tape or [])),
        "strict_hits": serialized_hits,
        "oracle_failures": [sanitize_repo_paths(str(f)) for f in (oracle_failures or [])],
        "error_type": type(exc).__name__ if exc is not None else ("StrictModeError" if serialized_hits else "OracleError"),
        "error_message": sanitize_repo_paths(str(exc) if exc is not None else error_summary),
        "traceback": sanitize_repo_paths(tb_str),
    }

    repro_path = bundle_dir / "repro.json"
    with open(repro_path, "w", encoding="utf-8") as fp:
        json.dump(repro_payload, fp, indent=2, ensure_ascii=False)
    return bundle_dir
