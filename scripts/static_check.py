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
    python scripts/static_check.py --changed          # only files changed vs HEAD (fast pre-commit)
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
SCAN_TARGETS = ["api", "cogs", "db", "game_engine", "mechanics", "services", "models"]
SCAN_ROOT_FILES = ["server.py", "llm_client.py", "character_data.py", "scenario_data.py", "catalog.py"]

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

_TERMINATED = None  # state sentinel: control never falls through (return/raise/break/continue)
State = Optional[Set[str]]

_SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_COMP_NODES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


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
        line = self.lines[lineno - 1] if 0 < lineno <= len(self.lines) else ""
        return "static-check: ignore" in line and ("possibly-unbound-local" in line or "ignore]" not in line)

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
            if not isinstance(s, ast.ClassDef):
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


def _changed_targets() -> List[Path]:
    proc = subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True)
    names = set(proc.stdout.split()) | set(untracked.stdout.split())
    scoped = {str(p.relative_to(ROOT)).replace("\\", "/") for p in _all_targets()}
    return sorted(ROOT / n for n in names if n.endswith(".py") and n in scoped and (ROOT / n).exists())


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
        print("Add this line to it manually:  python scripts/static_check.py --changed || exit 1")
        return 1
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(
        "#!/bin/sh\n"
        f"{_HOOK_MARKER}\n"
        "# Blocks commits that introduce NameError/UnboundLocalError/bad-import/bad-call bugs.\n"
        "# Bypass once (not recommended): git commit --no-verify\n"
        "python scripts/static_check.py --changed || {\n"
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
    ap.add_argument("--update-baseline", action="store_true", help="accept all current findings")
    ap.add_argument("--no-pylint", action="store_true", help="skip pylint (custom analyzer only)")
    ap.add_argument("--all", action="store_true", help="print baselined findings too")
    ap.add_argument("--install-hook", action="store_true", help="install a git pre-commit hook running --changed")
    args = ap.parse_args(argv)

    if args.install_hook:
        return _install_hook()

    if args.update_baseline and (args.files or args.changed or args.no_pylint):
        raise SystemExit("--update-baseline requires a full scan (no file filters, pylint enabled).")

    if args.files:
        targets = [Path(f).resolve() for f in args.files]
    elif args.changed:
        targets = _changed_targets()
    else:
        targets = _all_targets()
    if not targets:
        print("static_check: no Python files to check.")
        return 0
    rels = [str(p.relative_to(ROOT)).replace("\\", "/") if p.is_relative_to(ROOT) else str(p) for p in targets]

    findings: List[Finding] = []
    for p, rel in zip(targets, rels):
        findings.extend(analyze_possibly_unbound(p, rel))
    if not args.no_pylint:
        findings.extend(run_pylint(rels))
    findings.sort(key=lambda f: (f.path, f.line, f.check))

    if args.update_baseline:
        if args.files or args.changed:
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

    scope = "changed files" if args.changed else f"{len(targets)} file(s)"
    if new:
        print(f"static_check: {len(new)} NEW finding(s) in {scope}:\n")
        for f in new:
            print("  " + f.render())
        print("\nFix them. Only for verified false positives, suppress inline with")
        print("`# pylint: disable=<check>` (pylint checks) or `# static-check: ignore[possibly-unbound-local]`.")
        return 1
    print(f"static_check: OK - 0 new findings in {scope} ({len(findings)} baselined).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
