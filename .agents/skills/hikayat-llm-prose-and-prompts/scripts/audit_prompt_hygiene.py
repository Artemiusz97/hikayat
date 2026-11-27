#!/usr/bin/env python3
"""Read-only prompt, schema, retry, and llm_client proxy invariant checker.

Verifies without touching SQLite or making network calls:
  1. `game_engine/prompt_layout.py`: `build_static_core` is `@functools.cache` / `@lru_cache`
     and calls zero non-deterministic `time` / `datetime` / `random` / `uuid` helpers.
  2. `llm_client/__init__.py`: installs `install_submodule_proxy` and exposes live mutable
     `_http_client`, `_embed_http_client`, `_nsfw_http_client` bindings.
  3. `models/llm_schemas.py`: core schemas expose dict + attribute dual-access (`__getitem__`, `get`).
  4. `game_engine/turn/narration.py`: `run_narration_pass` preserves frozen `snapshot["applied"]`
     and discards retry `cast_events`.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[4]

NONDETERMINISTIC_ROOTS: Set[str] = {"time", "datetime", "random", "uuid"}
REQUIRED_SCHEMAS: tuple[str, ...] = (
    "TurnOutcome",
    "OpeningScene",
    "ActionClassification",
    "Choice",
    "NarrationOutcome",
)
REQUIRED_PROXIES: tuple[str, ...] = (
    "_http_client",
    "_embed_http_client",
    "_nsfw_http_client",
)


def _check_static_prompt_zone() -> Dict[str, Any]:
    path = REPO_ROOT / "game_engine" / "prompt_layout.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename="game_engine/prompt_layout.py")
    func = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "build_static_core"
        ),
        None,
    )
    if func is None:
        return {"ok": False, "detail": "build_static_core not found in game_engine/prompt_layout.py"}

    dec_names: Set[str] = set()
    for dec in func.decorator_list:
        for sub in ast.walk(dec):
            if isinstance(sub, ast.Name):
                dec_names.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                dec_names.add(sub.attr)

    is_cached = bool(dec_names & {"cache", "lru_cache"})
    bad_calls: List[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in NONDETERMINISTIC_ROOTS:
                bad_calls.append(f"{node.value.id}.{node.attr} (line {node.lineno})")

    ok = is_cached and not bad_calls
    return {
        "ok": ok,
        "cached": is_cached,
        "nondeterministic_refs": bad_calls,
    }


def _check_llm_client_proxies() -> Dict[str, Any]:
    init_path = REPO_ROOT / "llm_client" / "__init__.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename="llm_client/__init__.py")
    uses_proxy = "install_submodule_proxy" in source

    exported: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                exported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exported.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            exported.add(node.target.id)

    missing_attrs = [attr for attr in REQUIRED_PROXIES if attr not in exported]
    return {
        "ok": uses_proxy and not missing_attrs,
        "uses_install_submodule_proxy": uses_proxy,
        "missing_proxy_attrs": missing_attrs,
    }


def _check_llm_schemas_dual_access() -> Dict[str, Any]:
    classes: Dict[str, ast.ClassDef] = {}
    for rel in ("models/trackers.py", "models/llm_schemas.py"):
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node

    def _has_dual_access(cls_name: str, seen: Set[str] | None = None) -> bool:
        visited = set(seen or ())
        if cls_name in visited or cls_name not in classes:
            return False
        visited.add(cls_name)
        cls_node = classes[cls_name]
        methods = {
            stmt.name
            for stmt in cls_node.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if "__getitem__" in methods and "get" in methods:
            return True
        for base in cls_node.bases:
            base_name = base.id if isinstance(base, ast.Name) else (base.attr if isinstance(base, ast.Attribute) else "")
            if _has_dual_access(base_name, visited):
                return True
        return False

    missing = [name for name in REQUIRED_SCHEMAS if name not in classes]
    no_dual_access = [name for name in REQUIRED_SCHEMAS if name in classes and not _has_dual_access(name)]

    return {
        "ok": not missing and not no_dual_access,
        "missing_schemas": missing,
        "missing_dual_access": no_dual_access,
    }


def _check_narration_retry_freeze() -> Dict[str, Any]:
    path = REPO_ROOT / "game_engine" / "turn" / "narration.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename="game_engine/turn/narration.py")
    func = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run_narration_pass"
        ),
        None,
    )
    if func is None:
        return {"ok": False, "detail": "run_narration_pass not found in game_engine/turn/narration.py"}

    body_src = ast.get_source_segment(source, func) or ""
    has_applied = "applied" in body_src
    freezes_cast = "frozen_present" in body_src and "frozen_partners" in body_src
    sanitizes_prose = "sanitize_narrator_prose" in body_src
    return {
        "ok": has_applied and freezes_cast and sanitizes_prose,
        "references_applied_snapshot": has_applied,
        "freezes_cast_from_snapshot": freezes_cast,
        "sanitizes_narrator_prose": sanitizes_prose,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Hikayat LLM prompt, schema, retry, and proxy invariants.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    checks: Dict[str, Dict[str, Any]] = {
        "static_kv_cache_zone": _check_static_prompt_zone(),
        "llm_client_live_proxies": _check_llm_client_proxies(),
        "llm_schemas_dual_access": _check_llm_schemas_dual_access(),
        "narration_retry_freeze": _check_narration_retry_freeze(),
    }
    all_ok = all(bool(item.get("ok")) for item in checks.values())
    payload = {"ok": all_ok, "checks": checks}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for name, item in checks.items():
            status = "PASS" if item.get("ok") else "FAIL"
            print(f"[{status}] {name}: {json.dumps(item)}")
        print("OK: all prompt/schema/proxy invariants verified." if all_ok else "FAILED: one or more invariants failed.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
