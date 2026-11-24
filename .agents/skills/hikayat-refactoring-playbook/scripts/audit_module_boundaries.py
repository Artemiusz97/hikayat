#!/usr/bin/env python3
"""Read-only AST auditor for module size, inbound re-export callers, and layer boundaries.

Usage:
  python .agents/skills/hikayat-refactoring-playbook/scripts/audit_module_boundaries.py
  python .agents/skills/hikayat-refactoring-playbook/scripts/audit_module_boundaries.py game_engine/state/reducers.py
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
SKIP_DIRS: Set[str] = {
    ".git",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "__pycache__",
    "dist",
    "releases",
    "tests",
    ".desloppify",
    ".agents",
    "data",
    "localization",
    "archives",
    "backups",
}
DB_FORBIDDEN_ROOTS: Set[str] = {"services", "api", "cogs"}
MECH_FORBIDDEN_ROOTS: Set[str] = {"discord", "fastapi", "cogs", "api"}
MECH_LEGACY_ALLOWLIST: Set[str] = {
    "mechanics/combat/merchant.py",
    "mechanics/social/factions.py",
    "mechanics/system/concurrency.py",
    "mechanics/system/phone/embeds.py",
    "mechanics/system/phone/views.py",
    "mechanics/system/save_system.py",
}


def _iter_repo_files(exts: Tuple[str, ...]) -> List[Path]:
    found: List[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in exts:
            continue
        rel_parts = path.relative_to(REPO_ROOT).parts
        if SKIP_DIRS.intersection(rel_parts):
            continue
        found.append(path)
    return found


def _module_name_for(rel_posix: str) -> str:
    if rel_posix.endswith("/__init__.py"):
        return rel_posix[: -len("/__init__.py")].replace("/", ".")
    if rel_posix.endswith(".py"):
        return rel_posix[:-3].replace("/", ".")
    return rel_posix.rstrip("/").replace("/", ".")


def _check_layer_imports(py_path: Path) -> List[str]:
    rel = py_path.relative_to(REPO_ROOT).as_posix()
    source = py_path.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return [f"{rel}:{exc.lineno}: SyntaxError: {exc.msg}"]

    violations: List[str] = []
    is_db = rel.startswith("db/")
    is_mech = rel.startswith("mechanics/")
    if not (is_db or is_mech):
        return violations

    for node in ast.walk(tree):
        imported: List[str] = []
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported = [node.module]
        for mod in imported:
            top = mod.split(".", 1)[0]
            if is_db and top in DB_FORBIDDEN_ROOTS:
                if rel == "db/__init__.py" and mod == "services.anomalous_containment_service":
                    continue
                violations.append(f"{rel}:{node.lineno} imports {mod} (db -> {top} forbidden)")
            elif is_mech and top in MECH_FORBIDDEN_ROOTS and rel not in MECH_LEGACY_ALLOWLIST:
                violations.append(f"{rel}:{node.lineno} imports {mod} (mechanics -> {top} forbidden)")
    return violations


def _analyze_target(target_rel: str) -> Dict[str, Any]:
    target = (REPO_ROOT / target_rel).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Target not found: {target_rel}")
    rel = target.relative_to(REPO_ROOT).as_posix()
    mod_name = _module_name_for(rel)
    pkg_prefix = mod_name + "."

    py_targets = [target] if target.is_file() else sorted(target.rglob("*.py"))
    total_lines = 0
    top_defs: List[str] = []
    layer_violations: List[str] = []

    for py_path in py_targets:
        text = py_path.read_text(encoding="utf-8", errors="ignore")
        total_lines += len(text.splitlines())
        layer_violations.extend(_check_layer_imports(py_path))
        if py_path.suffix == ".py":
            tree = ast.parse(text, filename=py_path.relative_to(REPO_ROOT).as_posix())
            for stmt in tree.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    top_defs.append(stmt.name)

    inbound_from_symbols: Set[str] = set()
    inbound_attr_refs: Set[str] = set()
    caller_files: Set[str] = set()
    scan_files = _iter_repo_files((".py",))
    if (REPO_ROOT / "tests").is_dir():
        scan_files.extend(sorted((REPO_ROOT / "tests").rglob("*.py")))

    short_alias = mod_name.rsplit(".", 1)[-1]
    for scan_path in scan_files:
        if scan_path.resolve() in {p.resolve() for p in py_targets}:
            continue
        scan_rel = scan_path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(scan_path.read_text(encoding="utf-8", errors="ignore"), filename=scan_rel)
        except SyntaxError:
            continue

        bound_aliases: Set[str] = set()
        scan_mod = _module_name_for(scan_rel)
        scan_pkg_parts = scan_mod.split(".") if scan_rel.endswith("/__init__.py") else scan_mod.split(".")[:-1]

        def _resolve_import_from(imp: ast.ImportFrom) -> str:
            if imp.level == 0:
                return imp.module or ""
            up = imp.level - 1
            if up > len(scan_pkg_parts):
                return ""
            base = scan_pkg_parts[: len(scan_pkg_parts) - up] if up > 0 else list(scan_pkg_parts)
            if imp.module:
                base.extend(imp.module.split("."))
            return ".".join(base)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == mod_name or alias.name.startswith(pkg_prefix):
                        caller_files.add(scan_rel)
                        bound_aliases.add(alias.asname or alias.name.split(".")[-1])
            elif isinstance(node, ast.ImportFrom):
                resolved_mod = _resolve_import_from(node)
                if not resolved_mod:
                    continue
                if resolved_mod == mod_name or resolved_mod.startswith(pkg_prefix):
                    caller_files.add(scan_rel)
                    for alias in node.names:
                        inbound_from_symbols.add(alias.name)
                elif "." in mod_name:
                    parent_mod, child_name = mod_name.rsplit(".", 1)
                    if resolved_mod == parent_mod:
                        for alias in node.names:
                            if alias.name == child_name:
                                caller_files.add(scan_rel)
                                bound_aliases.add(alias.asname or alias.name)

        if bound_aliases or short_alias in bound_aliases:
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                    if node.value.id in bound_aliases:
                        inbound_attr_refs.add(node.attr)

    return {
        "target": rel,
        "module_name": mod_name,
        "lines": total_lines,
        "top_level_defs": len(top_defs),
        "caller_file_count": len(caller_files),
        "caller_files": sorted(caller_files),
        "reexport_manifest": sorted(inbound_from_symbols | inbound_attr_refs),
        "layer_violations": layer_violations,
    }


def _analyze_repo(min_lines: int, top_n: int) -> Dict[str, Any]:
    files = _iter_repo_files((".py", ".js", ".jsx"))
    large_files: List[Tuple[int, str]] = []
    over_800 = 0
    over_1500 = 0
    layer_violations: List[str] = []

    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if lines >= 800:
            over_800 += 1
        if lines >= 1500:
            over_1500 += 1
        if lines >= min_lines:
            large_files.append((lines, rel))
        if path.suffix == ".py":
            layer_violations.extend(_check_layer_imports(path))

    large_files.sort(key=lambda item: (-item[0], item[1]))
    return {
        "files_scanned": len(files),
        "over_800_lines": over_800,
        "over_1500_lines": over_1500,
        "top_large_modules": [{"lines": ln, "file": fp} for ln, fp in large_files[:top_n]],
        "layer_violations": layer_violations,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit large logic modules, inbound re-export manifests, and 4-layer imports."
    )
    parser.add_argument("target", nargs="?", help="Optional file or package path to inspect inbound callers.")
    parser.add_argument("--min-lines", type=int, default=800, help="Line threshold for repo-wide listing (default: 800).")
    parser.add_argument("--top", type=int, default=20, help="Max large modules to print (default: 20).")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    target_report: Dict[str, Any] = {}
    repo_report: Dict[str, Any] = {}
    if args.target:
        try:
            target_report = _analyze_target(args.target)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        violations = target_report["layer_violations"]
        payload: Any = target_report
    else:
        repo_report = _analyze_repo(args.min_lines, args.top)
        violations = repo_report["layer_violations"]
        payload = repo_report

    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.target:
        print(
            f"Target: {target_report['target']} ({target_report['lines']} lines, "
            f"{target_report['top_level_defs']} top-level defs)"
        )
        print(
            f"Inbound callers: {target_report['caller_file_count']} file(s), "
            f"{len(target_report['reexport_manifest'])} referenced symbol(s)."
        )
        if target_report["reexport_manifest"]:
            print("Re-export manifest:")
            for sym in target_report["reexport_manifest"]:
                print(f"  - {sym}")
        if violations:
            print("Layer violations:")
            for v in violations:
                print(f"  ! {v}")
        else:
            print("Layer boundaries: OK (0 violations).")
    else:
        print(
            f"Scanned {repo_report['files_scanned']} logic file(s): "
            f"{repo_report['over_800_lines']} >=800L, {repo_report['over_1500_lines']} >=1500L, "
            f"{len(violations)} layer violation(s)."
        )
        for entry in repo_report["top_large_modules"]:
            print(f"  {entry['lines']:5d}L  {entry['file']}")
        for v in violations:
            print(f"  [LAYER VIOLATION] {v}")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
