#!/usr/bin/env python3
"""
Hikayat static bug gate.

Catches crash-class bugs (NameError / UnboundLocalError / bad attribute & call signatures)
before they reach a play session. Two analyzers:

  1. pylint, restricted to high-signal *error* checks (no style noise).
  2. `possibly-unbound-local`: a flow-sensitive definite-assignment pass written for this
     codebase. It flags a local variable read on a path where it may never have been assigned:
     e.g. assigned only inside `if not in_combat:` and read 1,400 lines later, or shadowed by a
     function-local `import db` further down. pylint does not reliably catch these in very long
     functions (it missed the `pending_folklore_ops` crash in compute_pre_turn_stage).

Findings are fingerprinted without line numbers and compared against
`scripts/static_baseline.json`, so only NEW findings fail the gate.

Usage:
    python scripts/static_check.py                    # full gate (exit 1 on new findings)
    python scripts/static_check.py --changed          # only files changed vs HEAD
    python scripts/static_check.py --staged           # only staged files in git index (pre-commit)
    python scripts/static_check.py --update-baseline  # accept current findings as the baseline
    python scripts/static_check.py --no-pylint        # custom analyzer only (~2s)
    python scripts/static_check.py path/to/file.py    # explicit files
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "scripts" / "static_baseline.json"
def _discover_script_files() -> List[str]:
    scripts_dir = ROOT / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [f"scripts/{p.name}" for p in sorted(scripts_dir.glob("*.py"))]


SCAN_TARGETS = ["api", "cogs", "db", "game_engine", "mechanics", "services", "models", "localization", "bin"]
SCAN_ROOT_FILES = [
    "bot.py",
    "character_data.py",
    "config.py",
    "image_client.py",
    "llm_client.py",
    "namegen.py",
    "scenario_data.py",
    "scenario_variants.py",
    "server.py",
    "skill_check.py",
    *_discover_script_files(),
]

# High-signal pylint checks only: each of these is a crash (or silently swallowed crash) at runtime.
PYLINT_CHECKS = [
    "undefined-variable",              # E0602  NameError
    "used-before-assignment",          # E0601  UnboundLocalError
    "possibly-used-before-assignment", # E0606  UnboundLocalError on some paths
    "no-member",                       # E1101  AttributeError on modules/classes
    "no-name-in-module",               # E0611  ImportError: cannot import name
    "unexpected-keyword-arg",          # E1123  TypeError: unexpected keyword
    "no-value-for-parameter",          # E1120  TypeError: missing argument
    "too-many-function-args",          # E1121  TypeError: too many positional args
    "function-redefined",              # E0102  later def silently replaces earlier one
]


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    check: str
    scope: str
    message: str

    @property
    def fingerprint(self) -> str:
        # Line numbers excluded so unrelated edits don't churn the baseline.
        return f"{self.path}::{self.scope}::{self.check}::{self.message}"

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.check}] {self.scope}: {self.message}"


# ---------------------------------------------------------------------------
# Analyzer 2: flow-sensitive possibly-unbound-local detection
# ---------------------------------------------------------------------------

def _is_suppressed_line(lines: List[str], lineno: int, rule_name: str) -> bool:
    """Inline opt-out: `# static-check: ignore[rule1,rule2]` or bare `# static-check: ignore`."""
    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
    if "static-check: ignore" not in line:
        return False
    m = re.search(r"static-check:\s*ignore\[([^\]]+)\]", line)
    if not m:
        return True
    rules = {r.strip() for r in m.group(1).split(",") if r.strip()}
    return rule_name in rules


_TERMINATED = None  # state sentinel: control never falls through (return/raise/break/continue)
State = Optional[Set[str]]

_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_COMP_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_NORETURN_BARE = frozenset({"exit", "quit"})
_NORETURN_ATTRS = frozenset({
    ("sys", "exit"),
    ("os", "_exit"),
    ("pytest", "fail"),
    ("pytest", "exit"),
    ("pytest", "skip"),
})


def _is_noreturn_call(expr: ast.AST) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    fn = expr.func
    if isinstance(fn, ast.Name):
        return fn.id in _NORETURN_BARE
    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
        return (fn.value.id, fn.attr) in _NORETURN_ATTRS
    return False


def _meet(states: Iterable[State]) -> State:
    live = [s for s in states if s is not _TERMINATED]
    if not live:
        return _TERMINATED
    out = set(live[0])
    for s in live[1:]:
        out &= s
    return out


def _target_names(node: ast.AST) -> Iterator[str]:
    if isinstance(node, ast.Name):
        yield node.id
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            yield from _target_names(elt)
    elif isinstance(node, ast.Starred):
        yield from _target_names(node.value)


def _import_names(node: ast.AST) -> Iterator[str]:
    for alias in node.names:  # type: ignore[attr-defined]
        if alias.name == "*":
            continue
        yield alias.asname or alias.name.split(".")[0]


def _pattern_captures(pat: ast.AST) -> Iterator[str]:
    for sub in ast.walk(pat):
        if isinstance(sub, (ast.MatchAs, ast.MatchStar)) and sub.name:
            yield sub.name
        elif isinstance(sub, ast.MatchMapping) and sub.rest:
            yield sub.rest


def _locals_probe(node: ast.AST) -> Optional[Tuple[str, bool]]:
    """Match `"name" in locals()` / `"name" not in locals()`; return (name, negated)."""
    if (
        isinstance(node, ast.Compare)
        and len(node.ops) == 1
        and isinstance(node.ops[0], (ast.In, ast.NotIn))
        and isinstance(node.left, ast.Constant)
        and isinstance(node.left.value, str)
        and isinstance(node.comparators[0], ast.Call)
        and isinstance(node.comparators[0].func, ast.Name)
        and node.comparators[0].func.id in ("locals", "vars")
        and not node.comparators[0].args
    ):
        return node.left.value, isinstance(node.ops[0], ast.NotIn)
    return None


def _locals_guarded_names(node: ast.AST) -> Set[str]:
    """Names explicitly probed with `in locals()` anywhere in an expression (author already handles absence)."""
    out: Set[str] = set()
    for sub in ast.walk(node):
        probe = _locals_probe(sub)
        if probe:
            out.add(probe[0])
    return out


def _always_iterates(iter_node: ast.AST) -> bool:
    """`range(N)` / `range(a, b)` with positive literal span: the loop body runs at least once."""
    if not (isinstance(iter_node, ast.Call) and isinstance(iter_node.func, ast.Name) and iter_node.func.id == "range"):
        return False
    args = iter_node.args
    if not args or not all(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in args):
        return False
    vals = [a.value for a in args]  # type: ignore[attr-defined]
    start, stop = (0, vals[0]) if len(vals) == 1 else (vals[0], vals[1])
    step = vals[2] if len(vals) == 3 else 1
    return len(range(start, stop, step)) > 0


class _ExprScan(ast.NodeVisitor):
    """Collects Name loads and walrus stores in evaluation scope, skipping deferred scopes."""

    def __init__(self) -> None:
        self.loads: List[ast.Name] = []
        self.walrus: Set[str] = set()
        self._comp_bound: List[Set[str]] = []

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and not any(node.id in b for b in self._comp_bound):
            self.loads.append(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.walrus.add(node.target.id)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for d in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
            self.visit(d)

    def _visit_comp(self, node: ast.AST, elts: List[ast.AST]) -> None:
        gens = node.generators  # type: ignore[attr-defined]
        self.visit(gens[0].iter)  # first iterable is evaluated in the enclosing scope
        bound: Set[str] = set()
        self._comp_bound.append(bound)
        for i, gen in enumerate(gens):
            if i:
                self.visit(gen.iter)
            bound.update(_target_names(gen.target))
            for cond in gen.ifs:
                self.visit(cond)
        for e in elts:
            self.visit(e)
        self._comp_bound.pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node, [node.elt])

    visit_SetComp = visit_ListComp  # type: ignore[assignment]
    visit_GeneratorExp = visit_ListComp  # type: ignore[assignment]

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comp(node, [node.key, node.value])

    # Nested defs/classes inside expressions do not occur; statements are handled by the walker.


def _collect_local_stores(body: List[ast.stmt]) -> Tuple[Set[str], Set[str]]:
    """Names bound anywhere in this function scope (not nested scopes), plus global/nonlocal names."""
    stores: Set[str] = set()
    declared: Set[str] = set()

    def walk(node: ast.AST) -> None:
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            declared.update(node.names)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores.add(node.name)
            for d in node.decorator_list:
                walk(d)
            if not isinstance(node, ast.ClassDef):
                for d in node.args.defaults + [d for d in node.args.kw_defaults if d is not None]:
                    walk(d)
            return
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            stores.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            stores.update(_import_names(node))
        elif isinstance(node, ast.ExceptHandler) and node.name:
            stores.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            stores.add(node.target.id)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            stores.add(node.name)
        if isinstance(node, _COMP_NODES):
            # comprehension targets are their own scope; walrus inside still binds here
            for sub in ast.walk(node):
                if isinstance(sub, ast.NamedExpr):
                    stores.add(sub.target.id)
            return
        for child in ast.iter_child_nodes(node):
            walk(child)

    for stmt in body:
        walk(stmt)
    return stores - declared, declared


class _FunctionFlow:
    def __init__(self, func: ast.AST, rel: str, qualname: str, findings: List[Finding], lines: List[str]) -> None:
        self.func = func
        self.rel = rel
        self.qualname = qualname
        self.findings = findings
        self.lines = lines
        self.locals, _ = _collect_local_stores(func.body)  # type: ignore[attr-defined]
        args = func.args  # type: ignore[attr-defined]
        self.params: Set[str] = {a.arg for a in args.posonlyargs + args.args + args.kwonlyargs}
        if args.vararg:
            self.params.add(args.vararg.arg)
        if args.kwarg:
            self.params.add(args.kwarg.arg)
        self.reported: Set[str] = set()
        self.break_stack: List[List[Set[str]]] = []
        self.nested: List[Tuple[ast.AST, str]] = []

    # -- helpers --------------------------------------------------------------
    def _check_expr(self, node: Optional[ast.AST], state: Set[str]) -> Set[str]:
        """Report unsafe loads in `node`; return walrus names it binds."""
        if node is None:
            return set()
        scan = _ExprScan()
        scan.visit(node)
        guarded = _locals_guarded_names(node)
        for name_node in scan.loads:
            nm = name_node.id
            if nm in guarded:
                continue
            if nm in self.locals and nm not in state and nm not in scan.walrus and nm not in self.reported:
                if self._suppressed(name_node.lineno):
                    continue
                self.reported.add(nm)
                self.findings.append(Finding(
                    self.rel, name_node.lineno, "possibly-unbound-local", self.qualname,
                    f"'{nm}' may be read before assignment (assigned only on some paths, or shadowed by a later local import/assignment)",
                ))
        return scan.walrus

    def run(self) -> None:
        self._block(self.func.body, set(self.params))  # type: ignore[attr-defined]

    def _suppressed(self, lineno: int) -> bool:
        """Inline opt-out for verified false positives: `# static-check: ignore[possibly-unbound-local]`."""
        return _is_suppressed_line(self.lines, lineno, "possibly-unbound-local")

    # -- statement walker -------------------------------------------------------
    def _block(self, stmts: List[ast.stmt], state: State) -> State:
        for stmt in stmts:
            if state is _TERMINATED:
                return _TERMINATED
            state = self._stmt(stmt, set(state))
        return state

    def _stmt(self, s: ast.stmt, st: Set[str]) -> State:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for d in s.decorator_list:
                st |= self._check_expr(d, st)
            if isinstance(s, ast.ClassDef):
                for b in s.bases:
                    st |= self._check_expr(b, st)
                for kw in s.keywords:
                    st |= self._check_expr(kw.value, st)
                for item in s.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.nested.append((item, f"{self.qualname}.{s.name}.{item.name}"))
            else:
                for d in s.args.defaults + [d for d in s.args.kw_defaults if d is not None]:
                    st |= self._check_expr(d, st)
                self.nested.append((s, f"{self.qualname}.{s.name}"))
            st.add(s.name)
            return st
        if isinstance(s, ast.Assign):
            st |= self._check_expr(s.value, st)
            for t in s.targets:
                self._check_target_loads(t, st)
                st.update(_target_names(t))
            return st
        if isinstance(s, ast.AnnAssign):
            if s.value is not None:
                st |= self._check_expr(s.value, st)
                st.update(_target_names(s.target))
            return st
        if isinstance(s, ast.AugAssign):
            st |= self._check_expr(s.value, st)
            st |= self._check_expr(ast.Name(id=s.target.id, ctx=ast.Load(), lineno=s.lineno, col_offset=0), st) if isinstance(s.target, ast.Name) else set()
            self._check_target_loads(s.target, st)
            st.update(_target_names(s.target))
            return st
        if isinstance(s, (ast.Expr, ast.Assert)):
            st |= self._check_expr(s.value if isinstance(s, ast.Expr) else s.test, st)
            if isinstance(s, ast.Assert):
                st |= self._check_expr(s.msg, st)
            elif _is_noreturn_call(s.value):
                return _TERMINATED
            return st
        if isinstance(s, ast.Return):
            self._check_expr(s.value, st)
            return _TERMINATED
        if isinstance(s, ast.Raise):
            self._check_expr(s.exc, st)
            self._check_expr(s.cause, st)
            return _TERMINATED
        if isinstance(s, ast.Continue):
            return _TERMINATED
        if isinstance(s, ast.Break):
            if self.break_stack:
                self.break_stack[-1].append(set(st))
            return _TERMINATED
        if isinstance(s, ast.Delete):
            for t in s.targets:
                self._check_target_loads(t, st)
                for nm in _target_names(t):
                    self._check_expr(
                        ast.Name(id=nm, ctx=ast.Load(), lineno=getattr(t, "lineno", s.lineno), col_offset=0),
                        st,
                    )
                    st.discard(nm)
            return st
        if isinstance(s, (ast.Import, ast.ImportFrom)):
            st.update(_import_names(s))
            return st
        if isinstance(s, (ast.Global, ast.Nonlocal, ast.Pass)):
            return st
        if isinstance(s, ast.If):
            st |= self._check_expr(s.test, st)
            if self._is_const(s.test, True):
                return self._block(s.body, set(st))
            if self._is_const(s.test, False):
                return self._block(s.orelse, set(st))
            body_in, else_in = set(st), set(st)
            probe = _locals_probe(s.test)
            if probe:  # `if "x" not in locals(): x = ...`  -> x is bound in the other branch
                (else_in if probe[1] else body_in).add(probe[0])
            elif isinstance(s.test, ast.BoolOp) and isinstance(s.test.op, ast.And):
                for val in s.test.values:  # `if "x" in locals() and ...:` -> x bound in body
                    p = _locals_probe(val)
                    if p and not p[1]:
                        body_in.add(p[0])
            return _meet([self._block(s.body, body_in), self._block(s.orelse, else_in)])
        if isinstance(s, (ast.For, ast.AsyncFor)):
            st |= self._check_expr(s.iter, st)
            self.break_stack.append([])
            body_res = self._block(s.body, st | set(_target_names(s.target)))
            breaks = self.break_stack.pop()
            if _always_iterates(s.iter) and body_res is not _TERMINATED:
                return _meet([self._block(s.orelse, set(body_res))] + breaks)
            return _meet([self._block(s.orelse, set(st))] + breaks)
        if isinstance(s, ast.While):
            st |= self._check_expr(s.test, st)
            self.break_stack.append([])
            self._block(s.body, set(st))
            breaks = self.break_stack.pop()
            if self._is_const(s.test, True):
                return _meet(breaks)  # infinite loop: only exits via break
            return _meet([self._block(s.orelse, set(st))] + breaks)
        if isinstance(s, (ast.With, ast.AsyncWith)):
            for item in s.items:
                st |= self._check_expr(item.context_expr, st)
                if item.optional_vars is not None:
                    st.update(_target_names(item.optional_vars))
            return self._block(s.body, st)
        if isinstance(s, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            pre = set(st)
            body_res = self._block(s.body, set(pre))
            outs: List[State] = [self._block(s.orelse, set(body_res)) if body_res is not _TERMINATED else _TERMINATED]
            for h in s.handlers:
                self._check_expr(h.type, pre)
                h_in = set(pre) | ({h.name} if h.name else set())
                h_res = self._block(h.body, h_in)
                if h_res is not _TERMINATED and h.name:
                    h_res.discard(h.name)
                outs.append(h_res)
            normal = _meet(outs)
            if s.finalbody:
                fin = self._block(s.finalbody, set(pre))
                if fin is _TERMINATED:
                    return _TERMINATED
                if normal is _TERMINATED:
                    return _TERMINATED
                return normal | (fin - pre)
            return normal
        if isinstance(s, ast.Match):
            st |= self._check_expr(s.subject, st)
            outs = []
            irrefutable = False
            for case in s.cases:
                c_in = set(st) | set(_pattern_captures(case.pattern))
                if case.guard is not None:
                    c_in |= self._check_expr(case.guard, c_in)
                outs.append(self._block(case.body, c_in))
                if case.guard is None and isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None:
                    irrefutable = True
            if not irrefutable:
                outs.append(set(st))
            return _meet(outs)
        # Unknown statement type: check all loads conservatively, keep state.
        st |= self._check_expr(s, st)
        return st

    def _check_target_loads(self, target: ast.AST, st: Set[str]) -> None:
        # subscripts/attributes on the LHS (x[i] = ..., x.a = ...) *read* their base names
        for sub in ast.walk(target):
            if isinstance(sub, (ast.Subscript, ast.Attribute)):
                self._check_expr(sub.value, st)
                if isinstance(sub, ast.Subscript):
                    self._check_expr(sub.slice, st)

    @staticmethod
    def _is_const(node: ast.AST, truthy: bool) -> bool:
        return isinstance(node, ast.Constant) and bool(node.value) is truthy


def analyze_possibly_unbound(path: Path, rel: str) -> List[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as exc:
        return [Finding(rel, getattr(exc, "lineno", 0) or 0, "syntax-error", "<module>", str(exc))]
    lines = source.splitlines()
    findings: List[Finding] = []
    queue: List[Tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    queue.append((item, f"{node.name}.{item.name}"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            queue.append((node, node.name))
    seen: Set[int] = set()
    while queue:
        fn, qual = queue.pop()
        if id(fn) in seen:
            continue
        seen.add(id(fn))
        flow = _FunctionFlow(fn, rel, qual, findings, lines)
        flow.run()
        queue.extend(flow.nested)
    return findings


# ---------------------------------------------------------------------------
# Analyzers 3–5: Bundle B DB/Async/Registry Architecture Contracts
# ---------------------------------------------------------------------------

_SYNC_DB_ASYNC_PREFIXES = ("api/", "cogs/", "services/", "game_engine/turn/", "server.py")
_ASYNC_SAFE_DB_ATTRS = frozenset({
    "adb",
    "distributed_session_lock",
    "distributed_user_lock",
})
_DEFAULT_SQLITE_CONN_NAMES = frozenset({
    "conn",
    "con",
    "db_conn",
    "uow_conn",
    "raw_conn",
    "sqlite_conn",
    "dst_conn",
    "src_conn",
})


def _extract_pure_db_helpers(db_init_path: Optional[Path] = None) -> Set[str]:
    """Parse PURE_IN_MEMORY_DB_HELPERS from db/__init__.py via AST without importing db."""
    target = db_init_path or (ROOT / "db" / "__init__.py")
    if not target.exists():
        return set()
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()

    def _strings_in_node(val: Optional[ast.AST]) -> Set[str]:
        if val is None:
            return set()
        if isinstance(val, ast.Call) and val.args:
            return _strings_in_node(val.args[0])
        if isinstance(val, (ast.Set, ast.List, ast.Tuple)):
            out: Set[str] = set()
            for elt in val.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    out.add(elt.value)
            return out
        return set()

    for stmt in tree.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "PURE_IN_MEMORY_DB_HELPERS":
            return _strings_in_node(stmt.value)
        if isinstance(stmt, ast.Assign):
            for tgt in stmt.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "PURE_IN_MEMORY_DB_HELPERS":
                    return _strings_in_node(stmt.value)
    return set()


def _discover_db_submodules(db_dir: Optional[Path] = None) -> Set[str]:
    target = db_dir or (ROOT / "db")
    if not target.is_dir():
        return set()
    subs: Set[str] = set()
    for p in target.iterdir():
        if p.name == "__init__.py" or p.name.startswith("__"):
            continue
        if p.is_file() and p.suffix == ".py":
            subs.add(p.stem)
        elif p.is_dir() and (p / "__init__.py").is_file():
            subs.add(p.name)
    return subs


_DB_SUBMODULES = _discover_db_submodules()


def _collect_db_imports(
    nodes: Iterable[ast.AST],
    *,
    db_submodules: Optional[Set[str]] = None,
) -> Tuple[Set[str], Dict[str, str]]:
    """Collect aliases of `import db[.submod]` and `from db[.submod] import fn` bindings in a block."""
    subs = _DB_SUBMODULES if db_submodules is None else db_submodules
    aliases: Set[str] = set()
    symbols: Dict[str, str] = {}
    for node in nodes:
        if isinstance(node, ast.Import):
            for al in node.names:
                if al.name == "db" or al.name.startswith("db."):
                    if al.asname:
                        aliases.add(al.asname)
                    else:
                        aliases.add(al.name)
                        aliases.add("db")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and (node.module == "db" or node.module.startswith("db."))
        ):
            for al in node.names:
                if al.name == "*":
                    continue
                bound = al.asname or al.name
                if node.module == "db" and al.name in subs:
                    aliases.add(bound)
                else:
                    symbols[bound] = al.name
    return aliases, symbols


def _collect_local_bindings(fn: ast.AST) -> Set[str]:
    """Collect parameter and direct-scope non-db bindings that shadow outer names in `fn`."""
    bound: Set[str] = set()
    args = getattr(fn, "args", None)
    if isinstance(args, ast.arguments):
        for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
            bound.add(a.arg)
        if args.vararg is not None:
            bound.add(args.vararg.arg)
        if args.kwarg is not None:
            bound.add(args.kwarg.arg)

    _SCOPE_WALLS = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )

    def _walk(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            return
        if isinstance(node, _SCOPE_WALLS):
            return
        if isinstance(node, ast.Import):
            for al in node.names:
                if not (al.name == "db" or al.name.startswith("db.")):
                    bound.add(al.asname or al.name.split(".")[0])
            return
        if isinstance(node, ast.ImportFrom):
            is_db_imp = (
                node.level == 0
                and node.module is not None
                and (node.module == "db" or node.module.startswith("db."))
            )
            if not is_db_imp:
                for al in node.names:
                    if al.name != "*":
                        bound.add(al.asname or al.name)
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and isinstance(node.name, str):
            bound.add(node.name)
        elif isinstance(node, ast.MatchAs) and isinstance(node.name, str):
            bound.add(node.name)
        elif isinstance(node, ast.MatchStar) and isinstance(node.name, str):
            bound.add(node.name)
        elif isinstance(node, ast.MatchMapping) and isinstance(node.rest, str):
            bound.add(node.rest)
        for child in ast.iter_child_nodes(node):
            _walk(child)

    for stmt in getattr(fn, "body", ()):
        _walk(stmt)
    return bound


def _dotted_attr_chain(expr: ast.AST) -> Optional[str]:
    parts: List[str] = []
    cur = expr
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def analyze_sync_db_in_async(
    path: Path,
    rel: str,
    pure_helpers: Optional[Set[str]] = None,
) -> List[Finding]:
    """Flag direct blocking db.* calls inside `async def` (offload via `await adb(...)`)."""
    norm_rel = rel.replace("\\", "/")
    if not norm_rel.startswith(_SYNC_DB_ASYNC_PREFIXES):
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = source.splitlines()
    helpers = pure_helpers if pure_helpers is not None else _extract_pure_db_helpers()
    allowed = helpers | _ASYNC_SAFE_DB_ATTRS
    findings: List[Finding] = []

    def _iter_direct_imports(body: List[ast.stmt]) -> List[ast.stmt]:
        stmts: List[ast.stmt] = []
        stack: List[ast.AST] = list(body)
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                stmts.append(node)
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            stack.extend(ast.iter_child_nodes(node))
        return stmts

    mod_aliases, mod_symbols = _collect_db_imports(_iter_direct_imports(tree.body))

    def _scan_async_fn(
        fn: ast.AsyncFunctionDef,
        qualname: str,
        parent_aliases: Set[str],
        parent_symbols: Dict[str, str],
    ) -> None:
        local_stmts = _iter_direct_imports(fn.body)
        loc_aliases, loc_symbols = _collect_db_imports(local_stmts)
        shadowed = _collect_local_bindings(fn)
        aliases = (parent_aliases - shadowed) | loc_aliases
        symbols = {k: v for k, v in parent_symbols.items() if k not in shadowed}
        symbols.update(loc_symbols)

        def _visit(node: ast.AST) -> None:
            if node is not fn:
                if isinstance(node, ast.AsyncFunctionDef):
                    _scan_async_fn(node, f"{qualname}.{node.name}", aliases, symbols)
                    return
                if isinstance(node, ast.FunctionDef):
                    for d in node.decorator_list:
                        _visit(d)
                    for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
                        _visit(d)
                    # Recurse only into nested async defs inside this sync helper, scoping any local imports to its body.
                    fn_aliases, fn_symbols = _collect_db_imports(_iter_direct_imports(node.body))
                    fn_shadowed = _collect_local_bindings(node)
                    sub_aliases = (aliases - fn_shadowed) | fn_aliases
                    sub_symbols = {k: v for k, v in symbols.items() if k not in fn_shadowed}
                    sub_symbols.update(fn_symbols)
                    for sub in node.body:
                        _scan_for_nested_async(sub, f"{qualname}.{node.name}", sub_aliases, sub_symbols)
                    return
                if isinstance(node, ast.Lambda):
                    for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
                        _visit(d)
                    return
                if isinstance(node, ast.ClassDef):
                    for sub in node.body:
                        _scan_for_nested_async(sub, f"{qualname}.{node.name}", aliases, symbols)
                    return
                if isinstance(node, ast.Call):
                    fn_name: Optional[str] = None
                    via_alias = False
                    if isinstance(node.func, ast.Attribute):
                        root_chain = _dotted_attr_chain(node.func.value)
                        if root_chain and root_chain in aliases:
                            fn_name = node.func.attr
                            via_alias = True
                    elif isinstance(node.func, ast.Name) and node.func.id in symbols:
                        fn_name = symbols[node.func.id]

                    if (
                        fn_name is not None
                        and fn_name not in allowed
                        and not _is_suppressed_line(lines, node.lineno, "sync-db-in-async")
                    ):
                        how = f"`db.{fn_name}()`" if via_alias else f"`{fn_name}()` (from `db`)"
                        findings.append(Finding(
                            norm_rel,
                            node.lineno,
                            "sync-db-in-async",
                            qualname,
                            f"blocking {how} called inside async def; offload via `await adb(...)`",
                        ))
            for child in ast.iter_child_nodes(node):
                _visit(child)

        for stmt in fn.body:
            _visit(stmt)

    def _scan_for_nested_async(
        node: ast.AST,
        scope_prefix: str,
        parent_aliases: Set[str],
        parent_symbols: Dict[str, str],
    ) -> None:
        if isinstance(node, ast.AsyncFunctionDef):
            q = f"{scope_prefix}.{node.name}" if scope_prefix else node.name
            _scan_async_fn(node, q, parent_aliases, parent_symbols)
            return
        if isinstance(node, ast.FunctionDef):
            q = f"{scope_prefix}.{node.name}" if scope_prefix else node.name
            fn_aliases, fn_symbols = _collect_db_imports(_iter_direct_imports(node.body))
            fn_shadowed = _collect_local_bindings(node)
            sub_aliases = (parent_aliases - fn_shadowed) | fn_aliases
            sub_symbols = {k: v for k, v in parent_symbols.items() if k not in fn_shadowed}
            sub_symbols.update(fn_symbols)
            for sub in node.body:
                _scan_for_nested_async(sub, q, sub_aliases, sub_symbols)
            return
        if isinstance(node, ast.ClassDef):
            q = f"{scope_prefix}.{node.name}" if scope_prefix else node.name
            for sub in node.body:
                _scan_for_nested_async(sub, q, parent_aliases, parent_symbols)
            return
        for child in ast.iter_child_nodes(node):
            _scan_for_nested_async(child, scope_prefix, parent_aliases, parent_symbols)

    for item in tree.body:
        _scan_for_nested_async(item, "", mod_aliases, mod_symbols)
    return findings


def _is_sqlite_conn_producer(expr: Optional[ast.AST]) -> bool:
    """Return True when `expr` constructs or opens a sqlite3 connection / UoW handle."""
    if expr is None:
        return False
    if isinstance(expr, ast.IfExp):
        return _is_sqlite_conn_producer(expr.body) or _is_sqlite_conn_producer(expr.orelse)
    if not isinstance(expr, ast.Call):
        return False
    f = expr.func
    name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
    if name in ("get_conn", "_get_independent_conn", "UnitOfWork", "ReadUnitOfWork"):
        return True
    if name == "connect" and isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "sqlite3":
        return True
    return False


def analyze_raw_conn_commit(path: Path, rel: str) -> List[Finding]:
    """Flag raw SQLite `conn.commit()` outside `db/core` (would release active savepoints)."""
    norm_rel = rel.replace("\\", "/")
    if norm_rel == "db/core.py" or norm_rel.startswith("db/core/"):
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    lines = source.splitlines()
    findings: List[Finding] = []

    def _is_conn_expr(expr: Optional[ast.AST], conn_vars: Set[str]) -> bool:
        if expr is None:
            return False
        if _is_sqlite_conn_producer(expr):
            return True
        if isinstance(expr, ast.Name) and expr.id in conn_vars:
            return True
        if isinstance(expr, ast.Attribute) and expr.attr in _DEFAULT_SQLITE_CONN_NAMES:
            return True
        return False

    def _collect_conn_vars(scope_node: ast.AST, seeded_conns: Set[str]) -> Set[str]:
        conn_vars = set(seeded_conns)
        scope_nodes: List[ast.AST] = []
        stack: List[ast.AST] = list(getattr(scope_node, "body", []))
        while stack:
            node = stack.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            scope_nodes.append(node)
            stack.extend(ast.iter_child_nodes(node))
        changed = True
        while changed:
            changed = False
            before = len(conn_vars)
            for node in scope_nodes:
                if isinstance(node, ast.With):
                    for item in node.items:
                        if item.optional_vars is not None and _is_conn_expr(item.context_expr, conn_vars):
                            conn_vars.update(_target_names(item.optional_vars))
                elif isinstance(node, ast.Assign) and _is_conn_expr(node.value, conn_vars):
                    for tgt in node.targets:
                        conn_vars.update(_target_names(tgt))
                elif isinstance(node, ast.AnnAssign) and _is_conn_expr(node.value, conn_vars):
                    conn_vars.update(_target_names(node.target))
            changed = len(conn_vars) > before
        return conn_vars

    def _scan_scope(node: ast.AST, qualname: str, inherited_conns: Set[str]) -> None:
        conn_vars = inherited_conns | _collect_conn_vars(node, inherited_conns)

        def _visit(cur: ast.AST) -> None:
            if cur is not node and isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sub_q = f"{qualname}.{cur.name}" if qualname != "<module>" else cur.name
                _scan_scope(cur, sub_q, conn_vars)
                return
            if cur is not node and isinstance(cur, ast.ClassDef):
                sub_q = f"{qualname}.{cur.name}" if qualname != "<module>" else cur.name
                for item in cur.body:
                    _visit_cls_item(item, sub_q)
                return
            if isinstance(cur, ast.Call) and isinstance(cur.func, ast.Attribute) and cur.func.attr == "commit":
                val = cur.func.value
                is_conn = (
                    (isinstance(val, ast.Name) and val.id in conn_vars)
                    or (isinstance(val, ast.Attribute) and val.attr in _DEFAULT_SQLITE_CONN_NAMES)
                    or _is_sqlite_conn_producer(val)
                )
                if is_conn and not _is_suppressed_line(lines, cur.lineno, "raw-conn-commit-outside-core"):
                    if isinstance(val, ast.Name):
                        target_desc = val.id
                    elif isinstance(val, ast.Attribute):
                        target_desc = ast.unparse(val) if hasattr(ast, "unparse") else f"obj.{val.attr}"
                    else:
                        target_desc = "get_conn()"
                    findings.append(Finding(
                        norm_rel,
                        cur.lineno,
                        "raw-conn-commit-outside-core",
                        qualname,
                        f"raw `{target_desc}.commit()` outside db/core.py; remove it inside UnitOfWork/savepoints or use `db.UnitOfWork()`",
                    ))
            for child in ast.iter_child_nodes(cur):
                _visit(child)

        def _visit_cls_item(item: ast.AST, cls_q: str) -> None:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _scan_scope(item, f"{cls_q}.{item.name}", conn_vars)
            elif isinstance(item, ast.ClassDef):
                for sub in item.body:
                    _visit_cls_item(sub, f"{cls_q}.{item.name}")

        for stmt in getattr(node, "body", []):
            _visit(stmt)

    _scan_scope(tree, "<module>", set(_DEFAULT_SQLITE_CONN_NAMES))
    return findings


def _extract_registered_table_names(registry_path: Path, *, include_global: bool = True) -> Set[str]:
    """Extract registered table names from SESSION_TABLE_REGISTRY, FTS5_VIRTUAL_TABLES (and optionally GLOBAL_TABLES)."""
    tree = ast.parse(registry_path.read_text(encoding="utf-8"), filename=str(registry_path))
    names: Set[str] = set()

    def _collect_from_set_var(val: Optional[ast.AST]) -> None:
        if val is None:
            return
        if isinstance(val, ast.Call) and val.args:
            _collect_from_set_var(val.args[0])
            return
        if isinstance(val, (ast.Set, ast.List, ast.Tuple)):
            for elt in val.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    names.add(elt.value.strip().lower())

    def _collect_from_registry(val: Optional[ast.AST]) -> None:
        if not isinstance(val, (ast.List, ast.Tuple)):
            return
        for elt in val.elts:
            if isinstance(elt, ast.Call):
                for kw in elt.keywords:
                    if kw.arg in ("name", "table") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        names.add(kw.value.value.strip().lower())
                if elt.args and isinstance(elt.args[0], ast.Constant) and isinstance(elt.args[0].value, str):
                    names.add(elt.args[0].value.strip().lower())

    allowed_sets = ("GLOBAL_TABLES", "FTS5_VIRTUAL_TABLES") if include_global else ("FTS5_VIRTUAL_TABLES",)
    for stmt in tree.body:
        val_node: Optional[ast.AST] = None
        target_name = ""
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target_name = stmt.target.id
            val_node = stmt.value
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            target_name = stmt.targets[0].id
            val_node = stmt.value
        if target_name in allowed_sets:
            _collect_from_set_var(val_node)
        elif target_name == "SESSION_TABLE_REGISTRY":
            _collect_from_registry(val_node)
    return names


def analyze_unregistered_session_tables(
    db_core_path: Optional[Path] = None,
    registry_path: Optional[Path] = None,
    rel: str = "db/core.py",
) -> List[Finding]:
    """Flag any SCHEMA table in db/core/schema.py (or db/core.py) with a `session_id` column missing from SESSION_TABLE_REGISTRY / FTS5_VIRTUAL_TABLES."""
    schema_pkg_p = ROOT / "db" / "core" / "schema.py"
    if db_core_path is not None:
        core_p = db_core_path
    elif schema_pkg_p.exists():
        core_p = schema_pkg_p
        rel = "db/core/schema.py"
    else:
        core_p = ROOT / "db" / "core.py"
    reg_p = registry_path or (ROOT / "db" / "registry.py")
    if not core_p.exists() or not reg_p.exists():
        return []
    try:
        core_source = core_p.read_text(encoding="utf-8")
        core_tree = ast.parse(core_source, filename=str(core_p))
        registered = _extract_registered_table_names(reg_p, include_global=False)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    schema_str: Optional[str] = None
    schema_start_line = 1
    for stmt in core_tree.body:
        val_node: Optional[ast.AST] = None
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "SCHEMA":
            val_node = stmt.value
        elif isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCHEMA" for t in stmt.targets):
            val_node = stmt.value
        if isinstance(val_node, ast.Constant) and isinstance(val_node.value, str):
            schema_str = val_node.value
            schema_start_line = getattr(val_node, "lineno", stmt.lineno) or stmt.lineno
            break
    if not schema_str:
        return []

    core_lines = core_source.splitlines()
    findings: List[Finding] = []
    create_re = re.compile(
        r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(?:USING\s+[A-Za-z0-9_]+\s*)?\(",
        re.IGNORECASE,
    )
    for m in create_re.finditer(schema_str):
        tname = m.group(1).strip().lower()
        open_idx = m.end() - 1
        depth = 0
        end_idx = len(schema_str)
        for pos in range(open_idx, len(schema_str)):
            ch = schema_str[pos]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end_idx = pos
                    break
        body = schema_str[open_idx + 1 : end_idx]
        if not re.search(r"\bsession_id\b", body, re.IGNORECASE):
            continue
        if tname in registered:
            continue
        lineno = schema_start_line + schema_str[: m.start()].count("\n")
        if _is_suppressed_line(core_lines, lineno, "unregistered-session-table"):
            continue
        findings.append(Finding(
            rel.replace("\\", "/"),
            lineno,
            "unregistered-session-table",
            "SCHEMA",
            f"table '{tname}' has a `session_id` column in SCHEMA but is missing from db/registry.py (SESSION_TABLE_REGISTRY)",
        ))
    return findings


# ---------------------------------------------------------------------------
# Analyzers 6-7: Unused imports & shadowing local imports
# ---------------------------------------------------------------------------


def _is_type_checking_if(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    if (
        isinstance(test, ast.Attribute)
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
        and test.attr == "TYPE_CHECKING"
    ):
        return True
    return False


def _extract_string_elts(expr: Optional[ast.AST]) -> Set[str]:
    out: Set[str] = set()
    if expr is None:
        return out
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        for elt in expr.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.add(elt.value)
    elif isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        out |= _extract_string_elts(expr.left)
        out |= _extract_string_elts(expr.right)
    elif isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        out.add(expr.value)
    return out


def _extract_all_exports(tree: ast.Module) -> Set[str]:
    exports: Set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets):
            exports |= _extract_string_elts(stmt.value)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "__all__":
            exports |= _extract_string_elts(stmt.value)
        elif (
            isinstance(stmt, ast.AugAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.target.id == "__all__"
            and isinstance(stmt.op, ast.Add)
        ):
            exports |= _extract_string_elts(stmt.value)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "__all__"
                and call.func.attr in ("extend", "append")
                and call.args
            ):
                exports |= _extract_string_elts(call.args[0])
    return exports


_IDENT_TOKEN_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def _collect_annotation_tokens(expr: Optional[ast.AST], out: Set[str]) -> None:
    if expr is None:
        return
    for sub in ast.walk(expr):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.update(_IDENT_TOKEN_RE.findall(sub.value))


def _collect_used_names(root_node: ast.AST) -> Set[str]:
    used: Set[str] = set()

    def _walk(node: ast.AST) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
        elif isinstance(node, ast.arg):
            _collect_annotation_tokens(node.annotation, used)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _collect_annotation_tokens(node.returns, used)
        elif isinstance(node, ast.AnnAssign):
            _collect_annotation_tokens(node.annotation, used)
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            _collect_annotation_tokens(node.value, used)
        elif isinstance(node, ast.Call):
            fn = node.func
            is_cast = (
                (isinstance(fn, ast.Name) and fn.id == "cast")
                or (
                    isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "typing"
                    and fn.attr == "cast"
                )
            )
            if is_cast:
                if node.args:
                    _collect_annotation_tokens(node.args[0], used)
                for kw in node.keywords:
                    if kw.arg == "typ":
                        _collect_annotation_tokens(kw.value, used)
        for child in ast.iter_child_nodes(node):
            _walk(child)

    _walk(root_node)
    return used


def _iter_direct_control_imports(
    stmts: Iterable[ast.stmt],
    *,
    skip_type_checking: bool = False,
) -> Iterator[ast.stmt]:
    for stmt in stmts:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            yield stmt
        elif isinstance(stmt, ast.If):
            if skip_type_checking and _is_type_checking_if(stmt):
                yield from _iter_direct_control_imports(stmt.orelse, skip_type_checking=skip_type_checking)
            else:
                yield from _iter_direct_control_imports(stmt.body, skip_type_checking=skip_type_checking)
                yield from _iter_direct_control_imports(stmt.orelse, skip_type_checking=skip_type_checking)
        elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            yield from _iter_direct_control_imports(stmt.body, skip_type_checking=skip_type_checking)
            for h in stmt.handlers:
                yield from _iter_direct_control_imports(h.body, skip_type_checking=skip_type_checking)
            yield from _iter_direct_control_imports(stmt.orelse, skip_type_checking=skip_type_checking)
            yield from _iter_direct_control_imports(stmt.finalbody, skip_type_checking=skip_type_checking)
        elif isinstance(stmt, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_direct_control_imports(stmt.body, skip_type_checking=skip_type_checking)
            yield from _iter_direct_control_imports(getattr(stmt, "orelse", ()), skip_type_checking=skip_type_checking)
        elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
            for case in stmt.cases:
                yield from _iter_direct_control_imports(case.body, skip_type_checking=skip_type_checking)


def _iter_nested_callables(stmts: Iterable[ast.stmt], prefix: str) -> Iterator[Tuple[ast.AST, str]]:
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            q = f"{prefix}.{stmt.name}" if prefix else stmt.name
            yield stmt, q
            yield from _iter_nested_callables(stmt.body, q)
        elif isinstance(stmt, ast.ClassDef):
            q = f"{prefix}.{stmt.name}" if prefix else stmt.name
            yield from _iter_nested_callables(stmt.body, q)
        elif isinstance(stmt, ast.If):
            yield from _iter_nested_callables(stmt.body, prefix)
            yield from _iter_nested_callables(stmt.orelse, prefix)
        elif isinstance(stmt, (ast.Try, getattr(ast, "TryStar", ast.Try))):
            yield from _iter_nested_callables(stmt.body, prefix)
            for h in stmt.handlers:
                yield from _iter_nested_callables(h.body, prefix)
            yield from _iter_nested_callables(stmt.orelse, prefix)
            yield from _iter_nested_callables(stmt.finalbody, prefix)
        elif isinstance(stmt, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_nested_callables(stmt.body, prefix)
            yield from _iter_nested_callables(getattr(stmt, "orelse", ()), prefix)
        elif hasattr(ast, "Match") and isinstance(stmt, ast.Match):
            for case in stmt.cases:
                yield from _iter_nested_callables(case.body, prefix)


def _bound_import_aliases(stmt: ast.stmt) -> Iterator[Tuple[str, int]]:
    if isinstance(stmt, ast.ImportFrom) and stmt.level == 0 and stmt.module == "__future__":
        return
    for alias in getattr(stmt, "names", ()):
        if alias.name == "*":
            continue
        if isinstance(stmt, ast.Import):
            bound = alias.asname or alias.name.split(".")[0]
        else:
            bound = alias.asname or alias.name
        alias_line = getattr(alias, "lineno", None) or stmt.lineno
        yield bound, alias_line


def analyze_unused_imports(path: Path, rel: str) -> List[Finding]:
    """Flag unused module-level and function-local imports (exempting __init__.py, __all__, TYPE_CHECKING, and string annotations)."""
    if path.name == "__init__.py":
        return []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    norm_rel = rel.replace("\\", "/")
    lines = source.splitlines()
    all_exports = _extract_all_exports(tree)
    module_used = _collect_used_names(tree)
    findings: List[Finding] = []

    for stmt in _iter_direct_control_imports(tree.body, skip_type_checking=True):
        for bound, alias_line in _bound_import_aliases(stmt):
            if bound in all_exports or bound in module_used:
                continue
            if _is_suppressed_line(lines, alias_line, "unused-import") or _is_suppressed_line(lines, stmt.lineno, "unused-import"):
                continue
            findings.append(Finding(
                norm_rel,
                alias_line,
                "unused-import",
                "<module>",
                f"imported name '{bound}' is unused",
            ))

    for fn, qual in _iter_nested_callables(tree.body, ""):
        fn_used = _collect_used_names(fn)
        for stmt in _iter_direct_control_imports(getattr(fn, "body", ()), skip_type_checking=True):
            for bound, alias_line in _bound_import_aliases(stmt):
                if bound in fn_used:
                    continue
                if _is_suppressed_line(lines, alias_line, "unused-import") or _is_suppressed_line(lines, stmt.lineno, "unused-import"):
                    continue
                findings.append(Finding(
                    norm_rel,
                    alias_line,
                    "unused-import",
                    qual,
                    f"local imported name '{bound}' is unused",
                ))
    return findings


def analyze_shadowing_local_imports(path: Path, rel: str) -> List[Finding]:
    """Flag function-local imports whose bound name shadows a module-level import (risks UnboundLocalError)."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    module_imported: Set[str] = set()
    for stmt in _iter_direct_control_imports(tree.body, skip_type_checking=True):
        for bound, _ in _bound_import_aliases(stmt):
            module_imported.add(bound)
    if not module_imported:
        return []

    norm_rel = rel.replace("\\", "/")
    lines = source.splitlines()
    findings: List[Finding] = []
    for fn, qual in _iter_nested_callables(tree.body, ""):
        for stmt in _iter_direct_control_imports(getattr(fn, "body", ()), skip_type_checking=True):
            for bound, alias_line in _bound_import_aliases(stmt):
                if bound not in module_imported:
                    continue
                if _is_suppressed_line(lines, alias_line, "shadowing-local-import") or _is_suppressed_line(lines, stmt.lineno, "shadowing-local-import"):
                    continue
                findings.append(Finding(
                    norm_rel,
                    alias_line,
                    "shadowing-local-import",
                    qual,
                    f"local import '{bound}' shadows module-level import of the same name (risks UnboundLocalError)",
                ))
    return findings


# ---------------------------------------------------------------------------
# Analyzer 1: pylint (error subset)
# ---------------------------------------------------------------------------

_PYLINT_LINE = re.compile(r"^(?P<path>[^:]+):(?P<line>\d+): \[(?P<code>[A-Z]\d+)\((?P<sym>[^)]+)\), (?P<obj>[^\]]*)\] (?P<msg>.*)$")


def run_pylint(targets: List[str]) -> List[Finding]:
    if not targets:
        return []
    cmd = [
        sys.executable, "-m", "pylint", "-j", "0", "--disable=all",
        f"--enable={','.join(PYLINT_CHECKS)}", "--output-format=parseable",
        "--score=n", "--persistent=n", *targets,
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode & 32:  # pylint usage error
        print(proc.stdout[-2000:], proc.stderr[-2000:], sep="\n")
        raise SystemExit("pylint failed to run (usage error)")
    out: List[Finding] = []
    for raw in proc.stdout.splitlines():
        m = _PYLINT_LINE.match(raw.strip())
        if m:
            out.append(Finding(m["path"].replace("\\", "/"), int(m["line"]), m["sym"], m["obj"] or "<module>", m["msg"]))
    return out


# ---------------------------------------------------------------------------
# Target selection, baseline, CLI
# ---------------------------------------------------------------------------

def _all_targets() -> List[Path]:
    files: List[Path] = []
    for d in SCAN_TARGETS:
        files.extend(p for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)
    files.extend(ROOT / f for f in SCAN_ROOT_FILES if (ROOT / f).exists())
    return sorted(files)


def _filter_scoped_py(names: Set[str]) -> List[Path]:
    scoped = {str(p.relative_to(ROOT)).replace("\\", "/") for p in _all_targets()}
    return sorted(ROOT / n for n in names if n.endswith(".py") and n in scoped and (ROOT / n).exists())


def _changed_targets() -> List[Path]:
    proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        proc = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"], cwd=ROOT, capture_output=True, text=True)
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True)
    names = set(proc.stdout.splitlines()) | set(untracked.stdout.splitlines())
    return _filter_scoped_py(names)


def _staged_targets() -> List[Path]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT, capture_output=True, text=True,
    )
    return _filter_scoped_py(set(proc.stdout.splitlines()))


def _load_baseline() -> Dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {k: int(v) for k, v in data.get("findings", {}).items()}


def _counts(findings: List[Finding]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in findings:
        out[f.fingerprint] = out.get(f.fingerprint, 0) + 1
    return out


_HOOK_MARKER = "# installed-by: scripts/static_check.py"


def _install_hook() -> int:
    proc = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        print("static_check: not a git repository; hook not installed.")
        return 1
    hook = (ROOT / proc.stdout.strip() / "pre-commit").resolve()
    if hook.exists() and _HOOK_MARKER not in hook.read_text(encoding="utf-8", errors="replace"):
        print(f"static_check: {hook} already exists and was not created by this script; leaving it untouched.")
        print("Add this line to it manually:  python scripts/static_check.py --staged || exit 1")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        f"{_HOOK_MARKER}\n"
        "# Blocks commits that introduce NameError/UnboundLocalError/bad-import/bad-call bugs.\n"
        "# Bypass once (not recommended): git commit --no-verify\n"
        "python scripts/static_check.py --staged || {\n"
        "  echo \"\"; echo \"Commit blocked by scripts/static_check.py (see findings above).\"; exit 1;\n"
        "}\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        os.chmod(hook, 0o755)
    except OSError:
        pass
    print(f"static_check: pre-commit hook installed at {hook}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="explicit files to check (default: whole engine)")
    ap.add_argument("--changed", action="store_true", help="only files changed vs HEAD")
    ap.add_argument("--staged", action="store_true", help="only staged files in git index (for pre-commit)")
    ap.add_argument("--update-baseline", action="store_true", help="accept all current findings")
    ap.add_argument("--no-pylint", action="store_true", help="skip pylint (custom analyzer only)")
    ap.add_argument("--all", action="store_true", help="print baselined findings too")
    ap.add_argument("--install-hook", action="store_true", help="install a git pre-commit hook running --staged")
    args = ap.parse_args(argv)

    if args.install_hook:
        return _install_hook()

    if args.update_baseline and (args.files or args.changed or args.staged or args.no_pylint):
        raise SystemExit("--update-baseline requires a full scan (no file filters, pylint enabled).")

    if args.files:
        targets = [Path(f).resolve() for f in args.files]
    elif args.staged:
        targets = _staged_targets()
    elif args.changed:
        targets = _changed_targets()
    else:
        targets = _all_targets()
    if not targets:
        print("static_check: no Python files to check.")
        return 0
    rels = [str(p.relative_to(ROOT)).replace("\\", "/") if p.is_relative_to(ROOT) else str(p) for p in targets]

    findings: List[Finding] = []
    pure_helpers = _extract_pure_db_helpers()
    for p, rel in zip(targets, rels):
        findings.extend(analyze_possibly_unbound(p, rel))
        findings.extend(analyze_sync_db_in_async(p, rel, pure_helpers=pure_helpers))
        findings.extend(analyze_raw_conn_commit(p, rel))
        findings.extend(analyze_unused_imports(p, rel))
        findings.extend(analyze_shadowing_local_imports(p, rel))
    if any(r.replace("\\", "/") in ("db/core.py", "db/core/schema.py", "db/registry.py") for r in rels):
        findings.extend(analyze_unregistered_session_tables())
    if not args.no_pylint:
        findings.extend(run_pylint(rels))
    findings.sort(key=lambda f: (f.path, f.line, f.check))

    if args.update_baseline:
        if args.files or args.changed or args.staged:
            raise SystemExit("--update-baseline requires a full scan (no file filters).")
        payload = {
            "_comment": "Accepted pre-existing findings. Fingerprints omit line numbers. Shrink this file; never grow it casually.",
            "findings": dict(sorted(_counts(findings).items())),
        }
        BASELINE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"static_check: baseline updated with {len(findings)} finding(s) -> {BASELINE_PATH.relative_to(ROOT)}")
        return 0

    budget = _load_baseline()
    new: List[Finding] = []
    for f in findings:
        if budget.get(f.fingerprint, 0) > 0:
            budget[f.fingerprint] -= 1
            if args.all:
                print("  (baselined) " + f.render())
        else:
            new.append(f)

    scope = "staged files" if args.staged else ("changed files" if args.changed else f"{len(targets)} file(s)")
    if new:
        print(f"static_check: {len(new)} NEW finding(s) in {scope}:\n")
        for f in new:
            print("  " + f.render())
        print("\nFix them. Only for verified false positives, suppress inline with")
        print("`# pylint: disable=<check>` (pylint checks) or `# static-check: ignore[<rule>]`.")
        return 1
    print(f"static_check: OK - 0 new findings in {scope} ({len(findings)} baselined).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
