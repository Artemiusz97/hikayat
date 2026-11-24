#!/usr/bin/env python3
"""Read-only SQLite table lifecycle wiring checker for Hikayat.

Inspects `db/core/schema.py`, `db/core/migrations.py`, `db/registry.py`,
`db/saves.py`, and `db/sessions.py` without calling `db.init_db()` or opening SQLite.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db import registry as db_registry  # noqa: E402
from db.core import migrations as db_migrations  # noqa: E402
from db.core import schema as db_schema  # noqa: E402

CREATE_TABLE_RE = re.compile(
    r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


def _extract_schema_tables() -> Set[str]:
    ddl = f"{db_schema.SCHEMA}\n{db_schema.CREATE_SESSION_LOCKS_TABLE}"
    return {m.group(1) for m in CREATE_TABLE_RE.finditer(ddl)}


def _extract_save_hook_registries() -> Dict[str, Set[str]]:
    import db.saves as db_saves  # noqa: E402

    return {
        "row_transform_hook": set(getattr(db_saves, "_ROW_TRANSFORM_HOOKS", {}).keys()),
        "post_load_hook": set(getattr(db_saves, "_POST_LOAD_HOOKS", {}).keys()),
        "post_inventory_hook": set(getattr(db_saves, "_POST_INVENTORY_HOOKS", {}).keys()),
    }


def _handler_resolves(dotted_path: str) -> bool:
    if "." not in dotted_path:
        return False
    mod_name, attr_name = dotted_path.rsplit(".", 1)
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return False
    return callable(getattr(mod, attr_name, None))


def _check_all() -> Dict[str, Any]:
    schema_tables = _extract_schema_tables()
    specs = {spec.name: spec for spec in db_registry.SESSION_TABLE_REGISTRY}
    registered_all = set(specs.keys()) | set(db_registry.GLOBAL_TABLES) | set(db_registry.FTS5_VIRTUAL_TABLES)

    unregistered = sorted(schema_tables - registered_all)
    missing_non_optional = sorted(
        spec.name
        for spec in db_registry.SESSION_TABLE_REGISTRY
        if not spec.optional_table and spec.name not in schema_tables
    )

    hook_registries = _extract_save_hook_registries()
    broken_hooks: List[str] = []
    for spec in db_registry.SESSION_TABLE_REGISTRY:
        for field_name, valid_names in hook_registries.items():
            hook_val = getattr(spec, field_name)
            if hook_val and hook_val not in valid_names:
                broken_hooks.append(f"{spec.name}.{field_name}={hook_val}")
        if spec.rollback_handler and not _handler_resolves(spec.rollback_handler):
            broken_hooks.append(f"{spec.name}.rollback_handler={spec.rollback_handler}")

    ok = not (unregistered or missing_non_optional or broken_hooks)
    return {
        "ok": ok,
        "schema_table_count": len(schema_tables),
        "session_registry_count": len(specs),
        "global_table_count": len(db_registry.GLOBAL_TABLES),
        "unregistered_schema_tables": unregistered,
        "missing_non_optional_tables": missing_non_optional,
        "broken_hooks": sorted(broken_hooks),
    }


def _check_single_table(table: str) -> Dict[str, Any]:
    schema_tables = _extract_schema_tables()
    in_schema = table in schema_tables
    migrations_hits = [
        version
        for version, _name, stmts in db_migrations.SCHEMA_MIGRATIONS
        if any(re.search(rf"\b{re.escape(table)}\b", stmt) for stmt in stmts)
    ]

    spec = db_registry.SESSION_TABLE_MAP.get(table)
    in_global = table in db_registry.GLOBAL_TABLES
    in_fts = table in db_registry.FTS5_VIRTUAL_TABLES
    in_registry = bool(spec is not None or in_global or in_fts)

    saves_text = (REPO_ROOT / "db" / "saves.py").read_text(encoding="utf-8", errors="ignore")
    sessions_text = (REPO_ROOT / "db" / "sessions.py").read_text(encoding="utf-8", errors="ignore")

    hook_registries = _extract_save_hook_registries()
    save_hooks_ok = True
    rollback_handler_ok = True
    if spec is not None:
        for field_name, valid_names in hook_registries.items():
            hook_val = getattr(spec, field_name)
            if hook_val and hook_val not in valid_names:
                save_hooks_ok = False
        if spec.rollback_handler:
            rollback_handler_ok = _handler_resolves(spec.rollback_handler)

    return {
        "table": table,
        "in_schema": in_schema,
        "migration_versions": migrations_hits,
        "in_registry": in_registry,
        "registry_kind": (
            "session_child"
            if spec is not None
            else ("global" if in_global else ("fts5_virtual" if in_fts else "unregistered"))
        ),
        "save_slot_eligible": bool(spec.include_in_save_slot) if spec is not None else False,
        "save_hooks_ok": save_hooks_ok,
        "mentioned_in_saves_py": bool(re.search(rf"\b{re.escape(table)}\b", saves_text)),
        "rollback_mode": spec.rollback_mode if spec is not None else ("global" if in_global else "unknown"),
        "rollback_handler": spec.rollback_handler if spec is not None else None,
        "rollback_handler_ok": rollback_handler_ok,
        "mentioned_in_sessions_py": bool(re.search(rf"\b{re.escape(table)}\b", sessions_text)),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check SQLite table registration, migration, save, and rollback wiring.")
    parser.add_argument("table", nargs="?", help="Optional table name to inspect.")
    parser.add_argument("--all", action="store_true", help="Run global wiring verification across all schema tables.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument(
        "--require-registered",
        action="store_true",
        help="When inspecting a single table, exit 1 if missing from SCHEMA or db/registry.py.",
    )
    args = parser.parse_args(argv)
    report: Dict[str, Any] = {}
    global_report: Dict[str, Any] = {}

    if args.table and not args.all:
        report = _check_single_table(args.table)
        exit_ok = True
        if args.require_registered and not (
            report["in_schema"]
            and report["in_registry"]
            and report["save_hooks_ok"]
            and report["rollback_handler_ok"]
        ):
            exit_ok = False
        payload: Any = report
    else:
        global_report = _check_all()
        exit_ok = bool(global_report["ok"])
        payload = global_report

    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.table and not args.all:
        print(f"Table wiring report for '{report['table']}':")
        print(f"  1. db/core/schema.py:     in_schema={report['in_schema']}")
        print(f"  2. db/core/migrations.py: versions={report['migration_versions']}")
        print(
            f"  3. db/registry.py:        in_registry={report['in_registry']} "
            f"(kind={report['registry_kind']})"
        )
        print(
            f"  4. db/saves.py:           save_slot_eligible={report['save_slot_eligible']}, "
            f"save_hooks_ok={report['save_hooks_ok']}, text_refs={report['mentioned_in_saves_py']}"
        )
        print(
            f"  5. rollback:              mode={report['rollback_mode']}, "
            f"handler={report['rollback_handler']} (ok={report['rollback_handler_ok']}), "
            f"sessions_py_refs={report['mentioned_in_sessions_py']}"
        )
    else:
        assert global_report is not None
        print(
            f"Checked {global_report['schema_table_count']} SCHEMA table(s), "
            f"{global_report['session_registry_count']} SessionTableSpec entries, "
            f"{global_report['global_table_count']} GLOBAL_TABLES."
        )
        if global_report["ok"]:
            print("OK: all schema tables, save hooks, and rollback handlers resolve cleanly.")
        else:
            print(json.dumps(global_report, indent=2))

    return 0 if exit_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
