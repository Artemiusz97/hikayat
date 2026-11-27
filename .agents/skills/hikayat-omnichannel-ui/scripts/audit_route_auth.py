#!/usr/bin/env python3
"""Read-only AST auditor for FastAPI route auth boundaries and docstring order.

Scans `api/` handlers via Python AST without importing FastAPI or opening databases.
Flags:
  - `missing-session-auth`: session-scoped route without `verify_session_participant`
  - `missing-user-auth`: user-scoped route without `verify_user_access` / `is_strict_auth_context`
  - `weak-debug-gate`: `/api/debug` or `/debug/` route gating via `is_share_mode_active`
    without `is_strict_auth_context`
  - `displaced-docstring`: guard statements placed before a top-level string docstring
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parents[4]
HTTP_METHODS: Set[str] = {"get", "post", "put", "patch", "delete", "websocket"}


def _is_str_expr(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _extract_route_decorator(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str, Set[str]] | None:
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call):
            continue
        attr = dec.func
        if not isinstance(attr, ast.Attribute) or attr.attr not in HTTP_METHODS:
            continue
        target_name = getattr(attr.value, "id", "")
        if target_name not in {"router", "app"}:
            continue
        route_path = ""
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            route_path = dec.args[0].value
        dep_names: Set[str] = set()
        for sub in ast.walk(dec):
            if isinstance(sub, ast.Name):
                dep_names.add(sub.id)
            elif isinstance(sub, ast.Attribute):
                dep_names.add(sub.attr)
        return (attr.attr.upper(), route_path, dep_names)
    return None


def _collect_symbol_refs(func: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[Set[str], bool]:
    refs: Set[str] = set()
    reads_payload_session_id = False
    for node in ast.walk(func):
        if isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.Attribute):
            refs.add(node.attr)
            if (
                node.attr == "session_id"
                and isinstance(node.value, ast.Name)
                and node.value.id in {"req", "body", "payload"}
            ):
                reads_payload_session_id = True
    return refs, reads_payload_session_id


def audit_path(target_rel: str) -> Dict[str, Any]:
    target = (REPO_ROOT / target_rel).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Path not found: {target_rel}")
    py_files = [target] if target.is_file() else sorted(target.rglob("*.py"))

    findings: List[Dict[str, Any]] = []
    routes_scanned = 0

    for py_path in py_files:
        if "__pycache__" in py_path.parts:
            continue
        rel = py_path.relative_to(REPO_ROOT).as_posix()
        source = py_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=rel)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route_info = _extract_route_decorator(node)
            if route_info is None:
                continue
            routes_scanned += 1
            method, route_path, dep_names = route_info
            refs, reads_payload_sid = _collect_symbol_refs(node)
            all_refs = refs | dep_names

            has_session_auth = "verify_session_participant" in all_refs
            has_user_auth = "verify_user_access" in all_refs
            has_strict_auth = "is_strict_auth_context" in all_refs
            has_share_mode = "is_share_mode_active" in all_refs

            if (
                ("{session_id}" in route_path or reads_payload_sid)
                and not has_session_auth
                and "/api/debug" not in route_path
            ):
                findings.append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "function": node.name,
                        "route": f"{method} {route_path}",
                        "check": "missing-session-auth",
                        "detail": "Session-scoped handler does not call verify_session_participant.",
                    }
                )

            if "{user_id}" in route_path and not (has_user_auth or has_strict_auth or has_session_auth):
                findings.append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "function": node.name,
                        "route": f"{method} {route_path}",
                        "check": "missing-user-auth",
                        "detail": "User-scoped handler does not call verify_user_access or is_strict_auth_context.",
                    }
                )

            if ("/api/debug" in route_path or "/debug/" in route_path) and has_share_mode and not has_strict_auth:
                findings.append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "function": node.name,
                        "route": f"{method} {route_path}",
                        "check": "weak-debug-gate",
                        "detail": "Debug route gates on is_share_mode_active() without is_strict_auth_context(request).",
                    }
                )

            if len(node.body) > 1 and not _is_str_expr(node.body[0]):
                displaced = next((stmt for stmt in node.body[1:4] if _is_str_expr(stmt)), None)
                if displaced is not None:
                    findings.append(
                        {
                            "file": rel,
                            "line": displaced.lineno,
                            "function": node.name,
                            "route": f"{method} {route_path}",
                            "check": "displaced-docstring",
                            "detail": "String literal docstring appears after guard statement (__doc__ is None).",
                        }
                    )

    return {
        "files_scanned": len(py_files),
        "routes_scanned": routes_scanned,
        "finding_count": len(findings),
        "findings": findings,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit FastAPI route auth boundaries and docstring order.")
    parser.add_argument("--path", default="api", help="Relative file or directory to scan (default: api).")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any findings are reported.")
    args = parser.parse_args(argv)

    try:
        report = audit_path(args.path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Scanned {report['files_scanned']} file(s), {report['routes_scanned']} route handler(s): "
            f"{report['finding_count']} finding(s)."
        )
        for item in report["findings"]:
            print(
                f"  [{item['check']}] {item['file']}:{item['line']} "
                f"({item['route']} -> {item['function']}): {item['detail']}"
            )

    if args.strict and report["finding_count"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
