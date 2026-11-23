from __future__ import annotations

import asyncio
from contextlib import contextmanager, nullcontext
import contextvars
import itertools
import json
import logging
import queue
import re
import sqlite3
import sys
import threading
import time
from typing import Any, Callable, Optional

from config import DB_PATH as _INITIAL_DB_PATH

_log = logging.getLogger(__name__)
_LAST_SYNCED_DB_PATH: str = str(_INITIAL_DB_PATH)


def _resolve_db_path() -> str:
    """Resolve active SQLite DB path honoring monkeypatches on either `db.core.DB_PATH` or `db.DB_PATH`."""
    core_mod = sys.modules.get("db.core")
    db_mod = sys.modules.get("db")
    core_path = getattr(core_mod, "DB_PATH", None) if core_mod is not None else None
    db_path = getattr(db_mod, "DB_PATH", None) if db_mod is not None else None
    if core_path and str(core_path) != _LAST_SYNCED_DB_PATH:
        return str(core_path)
    if db_path and str(db_path) != _LAST_SYNCED_DB_PATH:
        return str(db_path)
    return str(core_path or db_path or _LAST_SYNCED_DB_PATH)


_POOL: dict[str, queue.Queue] = {}

_POOL_LOCK = threading.Lock()

MAX_CONNECTIONS = 15

_MAINTENANCE_LOCK = threading.Lock()

_TURNS_SINCE_MAINTENANCE = 0


def _advance_maintenance_counter(interval: int, *, force: bool = False) -> bool:
    global _TURNS_SINCE_MAINTENANCE
    with _MAINTENANCE_LOCK:
        _TURNS_SINCE_MAINTENANCE += 1
        if not force and _TURNS_SINCE_MAINTENANCE < interval:
            return False
        _TURNS_SINCE_MAINTENANCE = 0
        return True

_VERIFIED_TABLE_GROUPS: set[tuple[str, str]] = set()

_VERIFIED_TABLE_GROUPS_LOCK = threading.Lock()

_uow_conn_var = contextvars.ContextVar("_uow_conn_var", default=None)

_uow_db_path_var = contextvars.ContextVar("_uow_db_path_var", default=None)

_uow_is_readonly_var: contextvars.ContextVar[bool] = contextvars.ContextVar("_uow_is_readonly_var", default=False)

_uow_strict_readonly_var: contextvars.ContextVar[bool] = contextvars.ContextVar("_uow_strict_readonly_var", default=False)

_uow_explicit_var: contextvars.ContextVar[bool] = contextvars.ContextVar("_uow_explicit_var", default=False)

_uow_added_table_groups_var: contextvars.ContextVar[Optional[set[tuple[str, str]]]] = contextvars.ContextVar(
    "_uow_added_table_groups_var", default=None
)

_uow_savepoint_seq = itertools.count(1)

_MAIN_EVENT_LOOP: Optional[asyncio.AbstractEventLoop] = None


def is_in_uow() -> bool:
    """Return True when executing inside an active explicit `UnitOfWork` or `ReadUnitOfWork` context."""
    return bool(_uow_explicit_var.get())


def is_in_readonly_uow() -> bool:
    """Return True when executing inside an active `ReadUnitOfWork` context."""
    return bool(_uow_is_readonly_var.get())

def _publish_verified_table_groups(groups: Optional[set[tuple[str, str]]]) -> None:
    """Publishes transaction-verified lazy-DDL table groups only after commit or clean read verification."""
    if not groups:
        return
    with _VERIFIED_TABLE_GROUPS_LOCK:
        _VERIFIED_TABLE_GROUPS.update(groups)

def _discard_verified_table_groups(groups: Optional[set[tuple[str, str]]]) -> None:
    """Removes uncommitted lazy-DDL cache entries when a transaction rolls back."""
    if not groups:
        return
    with _VERIFIED_TABLE_GROUPS_LOCK:
        _VERIFIED_TABLE_GROUPS.difference_update(groups)

def _read_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("PRAGMA schema_version").fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0

@contextmanager
def savepoint(conn: sqlite3.Connection, name: str = "sp_nested", *, rollback_always: bool = False):
    """Wraps a SQLite sub-operation in a named SAVEPOINT and rolls back pending lazy-DDL cache keys on revert."""
    clean_name = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "sp_nested")).strip("_") or "sp_nested"
    if clean_name[0].isdigit():
        clean_name = f"sp_{clean_name}"
    pending = _uow_added_table_groups_var.get() if conn is _uow_conn_var.get() else None
    pending_before = set(pending) if pending is not None else None
    conn.execute(f"SAVEPOINT {clean_name}")
    try:
        yield conn
        if rollback_always:
            try:
                conn.execute(f"ROLLBACK TO SAVEPOINT {clean_name}")
                conn.execute(f"RELEASE SAVEPOINT {clean_name}")
            except sqlite3.Error:
                pass
            if pending is not None and pending_before is not None:
                pending.intersection_update(pending_before)
        else:
            conn.execute(f"RELEASE SAVEPOINT {clean_name}")
    except BaseException:
        try:
            conn.execute(f"ROLLBACK TO SAVEPOINT {clean_name}")
        except sqlite3.Error:
            pass
        try:
            conn.execute(f"RELEASE SAVEPOINT {clean_name}")
        except sqlite3.Error:
            pass
        if pending is not None and pending_before is not None:
            pending.intersection_update(pending_before)
        raise

def ensure_table_group_once(
    conn: sqlite3.Connection,
    group_name: str,
    check_and_create_fn: Callable[[sqlite3.Connection], None],
) -> None:
    """Runs lazy DDL guard at most once per active db_path (publishing to shared cache only after commit)."""
    uow_conn = _uow_conn_var.get()
    if uow_conn is not None and conn is uow_conn:
        active_db_path = _uow_db_path_var.get()
        if active_db_path:
            key = (str(active_db_path), str(group_name))
            with _VERIFIED_TABLE_GROUPS_LOCK:
                if key in _VERIFIED_TABLE_GROUPS:
                    return
            pending = _uow_added_table_groups_var.get()
            if pending is not None and key in pending:
                return
            check_and_create_fn(conn)
            if pending is not None:
                pending.add(key)
            elif not conn.in_transaction:
                with _VERIFIED_TABLE_GROUPS_LOCK:
                    _VERIFIED_TABLE_GROUPS.add(key)
            return
    check_and_create_fn(conn)

def _acquire_pooled_conn(db_path: str) -> tuple[queue.Queue, sqlite3.Connection]:
    with _POOL_LOCK:
        if db_path not in _POOL:
            _POOL[db_path] = queue.Queue(maxsize=MAX_CONNECTIONS)
        pool = _POOL[db_path]
    try:
        conn = pool.get_nowait()
    except queue.Empty:
        conn = _create_new_connection(db_path)
    return pool, conn

def _release_pooled_conn(pool: queue.Queue, conn: sqlite3.Connection) -> None:
    try:
        pool.put_nowait(conn)
    except queue.Full:
        conn.close()

def close_all_connections():
    """Drains all connection pools. Vital for test teardown on Windows."""
    global _TURNS_SINCE_MAINTENANCE
    drained: list[list[sqlite3.Connection]] = []
    with _POOL_LOCK:
        for _path, q in _POOL.items():
            conns: list[sqlite3.Connection] = []
            while not q.empty():
                try:
                    conns.append(q.get_nowait())
                except queue.Empty:
                    break
            if conns:
                drained.append(conns)
        _POOL.clear()
    with _MAINTENANCE_LOCK:
        _TURNS_SINCE_MAINTENANCE = 0
    with _VERIFIED_TABLE_GROUPS_LOCK:
        _VERIFIED_TABLE_GROUPS.clear()

    for conns in drained:
        optimized_path = False
        for conn in conns:
            if not optimized_path:
                try:
                    if not conn.in_transaction:
                        optimized_path = True
                        conn.execute("PRAGMA optimize")
                except sqlite3.Error:
                    pass
            try:
                conn.close()
            except sqlite3.Error:
                pass

def _create_new_connection(db_path: str):
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")
    conn.execute("PRAGMA wal_autocheckpoint = 1000")
    conn.execute("PRAGMA journal_size_limit = 67108864")
    return conn

@contextmanager
def _get_independent_conn(db_path: str = None):
    """Acquires an independent pooled connection that commits immediately, bypassing active contextvars."""
    if db_path is None:
        db_path = _resolve_db_path()
    pool, conn = _acquire_pooled_conn(db_path)
    ind_added_groups: set[tuple[str, str]] = set()
    token = _uow_conn_var.set(conn)
    path_token = _uow_db_path_var.set(db_path)
    ro_token = _uow_is_readonly_var.set(False)
    strict_token = _uow_strict_readonly_var.set(False)
    exp_token = _uow_explicit_var.set(False)
    added_token = _uow_added_table_groups_var.set(ind_added_groups)
    committed = False
    try:
        yield conn
        conn.commit()
        committed = True
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if committed:
            _publish_verified_table_groups(ind_added_groups)
        _uow_added_table_groups_var.reset(added_token)
        _uow_explicit_var.reset(exp_token)
        _uow_strict_readonly_var.reset(strict_token)
        _uow_is_readonly_var.reset(ro_token)
        _uow_db_path_var.reset(path_token)
        _uow_conn_var.reset(token)
        _release_pooled_conn(pool, conn)

@contextmanager
def UnitOfWork(db_path: str = None):
    """Context manager that begins a write transaction (`BEGIN IMMEDIATE`) and yields the connection."""
    if db_path is None:
        db_path = _resolve_db_path()

    existing_conn = _uow_conn_var.get()
    if existing_conn is not None and _uow_db_path_var.get() == db_path:
        if _uow_strict_readonly_var.get():
            raise RuntimeError(
                f"Cannot nest UnitOfWork inside ReadUnitOfWork(strict_readonly=True) on {db_path}"
            )
        if _uow_is_readonly_var.get():
            raise RuntimeError(
                f"Cannot nest UnitOfWork inside active ReadUnitOfWork on {db_path}"
            )
        if not existing_conn.in_transaction:
            existing_conn.execute("BEGIN IMMEDIATE")
        nested_exp_token = _uow_explicit_var.set(True)
        try:
            with savepoint(existing_conn, f"_uow_sp_{next(_uow_savepoint_seq)}"):
                yield existing_conn
        finally:
            _uow_explicit_var.reset(nested_exp_token)
        return

    pool, conn = _acquire_pooled_conn(db_path)

    added_groups: set[tuple[str, str]] = set()
    token = _uow_conn_var.set(conn)
    path_token = _uow_db_path_var.set(db_path)
    ro_token = _uow_is_readonly_var.set(False)
    strict_token = _uow_strict_readonly_var.set(False)
    exp_token = _uow_explicit_var.set(True)
    added_token = _uow_added_table_groups_var.set(added_groups)
    committed = False
    try:
        # Execute BEGIN IMMEDIATE inside try so lock/busy failures always release the pooled conn.
        if not conn.in_transaction:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
        committed = True
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if committed:
            _publish_verified_table_groups(added_groups)
        _uow_added_table_groups_var.reset(added_token)
        _uow_explicit_var.reset(exp_token)
        _uow_strict_readonly_var.reset(strict_token)
        _uow_is_readonly_var.reset(ro_token)
        _uow_db_path_var.reset(path_token)
        _uow_conn_var.reset(token)
        _release_pooled_conn(pool, conn)

@contextmanager
def ReadUnitOfWork(db_path: str | None = None, *, strict_readonly: bool = False):
    """Context manager pinning a pooled connection for consistent WAL reads (`BEGIN DEFERRED`) without taking a write lock."""
    if db_path is None:
        db_path = _resolve_db_path()

    existing_conn = _uow_conn_var.get()
    if existing_conn is not None and _uow_db_path_var.get() == db_path:
        if not strict_readonly or _uow_strict_readonly_var.get():
            nested_exp_token = _uow_explicit_var.set(True)
            try:
                yield existing_conn
            finally:
                _uow_explicit_var.reset(nested_exp_token)
            return
        parent_kind = "ReadUnitOfWork" if _uow_is_readonly_var.get() else "UnitOfWork"
        raise RuntimeError(
            f"Cannot nest ReadUnitOfWork(strict_readonly=True) inside active {parent_kind} on {db_path}"
        )

    pool, conn = _acquire_pooled_conn(db_path)
    before_changes = conn.total_changes
    # Read PRAGMA schema_version before BEGIN DEFERRED when writable so no WAL read snapshot
    # is pinned prematurely before a caller's lazy write.
    before_schema_version: Optional[int] = None if strict_readonly else _read_schema_version(conn)
    added_groups: set[tuple[str, str]] = set()
    query_only_enabled = False
    token = _uow_conn_var.set(conn)
    path_token = _uow_db_path_var.set(db_path)
    ro_token = _uow_is_readonly_var.set(True)
    strict_token = _uow_strict_readonly_var.set(bool(strict_readonly))
    exp_token = _uow_explicit_var.set(True)
    added_token = _uow_added_table_groups_var.set(added_groups)
    succeeded = False
    try:
        if strict_readonly:
            conn.execute("PRAGMA query_only = ON")
            query_only_enabled = True
        if not conn.in_transaction:
            conn.execute("BEGIN DEFERRED")
        yield conn
        # SQLite total_changes counts DML only; PRAGMA schema_version catches lazy DDL (CREATE TABLE/INDEX).
        if not strict_readonly and (
            conn.total_changes > before_changes
            or (before_schema_version is not None and _read_schema_version(conn) != before_schema_version)
        ):
            conn.commit()
        elif conn.in_transaction:
            conn.rollback()
        succeeded = True
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if succeeded:
            _publish_verified_table_groups(added_groups)
        _uow_added_table_groups_var.reset(added_token)
        _uow_explicit_var.reset(exp_token)
        _uow_strict_readonly_var.reset(strict_token)
        _uow_is_readonly_var.reset(ro_token)
        _uow_db_path_var.reset(path_token)
        _uow_conn_var.reset(token)
        release_to_pool = True
        if query_only_enabled:
            try:
                conn.execute("PRAGMA query_only = OFF")
            except sqlite3.Error:
                release_to_pool = False
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
        if release_to_pool:
            _release_pooled_conn(pool, conn)

@contextmanager
def get_conn():
    """Returns the active context connection if inside one, else acquires a pooled connection and binds it to context."""
    db_path = _resolve_db_path()
    existing_conn = _uow_conn_var.get()
    if existing_conn is not None and _uow_db_path_var.get() == db_path:
        yield existing_conn
    else:
        pool, conn = _acquire_pooled_conn(db_path)

        added_groups: set[tuple[str, str]] = set()
        token = _uow_conn_var.set(conn)
        path_token = _uow_db_path_var.set(db_path)
        ro_token = _uow_is_readonly_var.set(False)
        strict_token = _uow_strict_readonly_var.set(False)
        added_token = _uow_added_table_groups_var.set(added_groups)
        committed = False
        try:
            yield conn
            conn.commit()
            committed = True
        except BaseException:
            if conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if committed:
                _publish_verified_table_groups(added_groups)
            _uow_added_table_groups_var.reset(added_token)
            _uow_strict_readonly_var.reset(strict_token)
            _uow_is_readonly_var.reset(ro_token)
            _uow_db_path_var.reset(path_token)
            _uow_conn_var.reset(token)
            _release_pooled_conn(pool, conn)

def _conn_ctx(conn: sqlite3.Connection | None):
    return nullcontext(conn) if conn is not None else get_conn()

def _opt_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None

def _restore_session_table_rows(
    conn: sqlite3.Connection,
    table_name: str,
    session_id: int,
    rows_or_json: Any,
) -> int:
    """Replace a session's rows in `table_name` from a JSON string or list of row dicts."""
    if isinstance(rows_or_json, str):
        try:
            items = json.loads(rows_or_json or "[]")
        except Exception:
            items = []
    else:
        items = rows_or_json
    valid_cols = {
        r["name"] if isinstance(r, sqlite3.Row) else r[1]
        for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    sid = int(session_id)
    conn.execute(f"DELETE FROM {table_name} WHERE session_id = ?", (sid,))
    restored = 0
    for item in (items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        row_dict = {
            k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in item.items()
            if k in valid_cols and k not in ("id", "session_id")
        }
        if not row_dict:
            continue
        row_dict["session_id"] = sid
        cols_sql = ",".join(row_dict.keys())
        qmarks = ",".join("?" * len(row_dict))
        conn.execute(f"INSERT INTO {table_name} ({cols_sql}) VALUES ({qmarks})", list(row_dict.values()))
        restored += 1
    return restored

def get_main_event_loop() -> Optional[asyncio.AbstractEventLoop]:
    """Returns the last active main asyncio event loop if still running."""
    loop = _MAIN_EVENT_LOOP
    if loop is not None and not loop.is_closed() and loop.is_running():
        return loop
    return None

async def adb(fn, /, *args, **kwargs):
    """Async wrapper for any synchronous ``db.*`` function.

    Offloads the blocking SQLite call to the default thread-pool executor so
    the asyncio event loop (and Discord gateway heartbeat) are never stalled.

    Usage inside an ``async def`` Discord handler::

        char = await adb(db.get_character, user_id)
        session = await adb(db.get_session, session_id)
    """
    global _MAIN_EVENT_LOOP
    try:
        _MAIN_EVENT_LOOP = asyncio.get_running_loop()
    except RuntimeError:
        pass
    return await asyncio.to_thread(fn, *args, **kwargs)

def acquire_distributed_lock(lock_key: str, owner_id: str, timeout_seconds: int = 210) -> bool:
    """Attempts to acquire a database-backed distributed lock.
    Returns True if successfully acquired (or already held by this owner), False if locked by someone else.
    """
    now = time.time()
    with _get_independent_conn() as conn:
        # Clear expired locks safely inside the transaction
        conn.execute("DELETE FROM session_locks WHERE locked_at < ?", (now - timeout_seconds,))
        
        try:
            conn.execute(
                "INSERT INTO session_locks (lock_key, locked_at, locked_by) VALUES (?, ?, ?)",
                (lock_key, now, owner_id)
            )
            return True
        except sqlite3.IntegrityError:
            # Check if we already own it
            row = conn.execute("SELECT locked_by FROM session_locks WHERE lock_key=?", (lock_key,)).fetchone()
            if row and row["locked_by"] == owner_id:
                # Refresh it
                conn.execute("UPDATE session_locks SET locked_at=? WHERE lock_key=?", (now, lock_key))
                return True
            return False

def release_distributed_lock(lock_key: str, owner_id: str):
    """Releases a database-backed distributed lock if we own it."""
    with _get_independent_conn() as conn:
        conn.execute("DELETE FROM session_locks WHERE lock_key=? AND locked_by=?", (lock_key, owner_id))

def set_db_path(new_path: str):
    """Dynamically switches the active SQLite database path and resets connection pools."""
    global _LAST_SYNCED_DB_PATH
    import config
    close_all_connections()
    _LAST_SYNCED_DB_PATH = str(new_path)
    db_mod = sys.modules.get("db")
    if db_mod is not None:
        db_mod.DB_PATH = new_path
    core_mod = sys.modules.get("db.core")
    if core_mod is not None:
        core_mod.DB_PATH = new_path
    config.DB_PATH = new_path
