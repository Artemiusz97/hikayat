#!/usr/bin/env python3
"""One-shot read-only release and hygiene gate for Hikayat.

Runs the full Definition-of-Done verification matrix in a single command without
mutating workspace files, staging git changes, or touching live `hikayat.db`:
  1. `scripts/static_check.py` (0 new, 0 baselined in `scripts/static_baseline.json`)
  2. `scripts/package_release.py --dry-run` (0 personal path leaks)
  3. Bundled skill checkers: `check_locale_parity.py`, `check_table_wiring.py`,
     `audit_prompt_hygiene.py`, and diagnostic `audit_route_auth.py --json`
  4. Core contract tests (`HIKAYAT_STRICT=1`, unless `--skip-tests`)
  5. Git hygiene (no tracked local-only gitignored files, `web/src/` vs `web/dist/` sync)
  6. Live `hikayat.db` mtime/size guard (must remain completely untouched)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
LOCAL_ONLY_TRACKED_PREFIXES: Tuple[str, ...] = (
    "tests/",
    "pytest.ini",
    "scripts/run_tests.py",
    "scripts/simulate_",
    ".desloppify/",
)


def _db_fingerprint() -> Tuple[int, int] | None:
    db_file = REPO_ROOT / "hikayat.db"
    if not db_file.is_file():
        return None
    st = db_file.stat()
    return (st.st_size, st.st_mtime_ns)


def _run_cmd(cmd: List[str], env_extra: Dict[str, str] | None = None, timeout: int = 180) -> Dict[str, Any]:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": -1, "summary": f"Timed out after {timeout}s"}
    combined = (proc.stdout or "").strip()
    if not combined and proc.stderr:
        combined = proc.stderr.strip()
    first_lines = [ln.strip() for ln in combined.splitlines() if ln.strip()][:3]
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "summary": " | ".join(first_lines) if first_lines else f"exit={proc.returncode}",
        "stdout": proc.stdout or "",
    }


def _check_baseline_empty() -> Dict[str, Any]:
    baseline = REPO_ROOT / "scripts" / "static_baseline.json"
    if not baseline.is_file():
        return {"ok": True, "summary": "No baseline file (0 baselined)."}
    try:
        data = json.loads(baseline.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "summary": f"Unreadable baseline JSON: {exc}"}
    findings = data.get("findings", data) if isinstance(data, dict) else data
    count = len(findings) if isinstance(findings, (dict, list)) else 0
    return {"ok": count == 0, "summary": f"{count} baselined finding(s) in scripts/static_baseline.json."}


def _check_git_and_dist_hygiene() -> Dict[str, Any]:
    tracked = _run_cmd(["git", "ls-files"], timeout=30)
    tracked_lines = [ln.strip() for ln in tracked.get("stdout", "").splitlines() if ln.strip()]
    forbidden_tracked = [
        fp
        for fp in tracked_lines
        if any(fp == pref or fp.startswith(pref) for pref in LOCAL_ONLY_TRACKED_PREFIXES)
    ]

    status = _run_cmd(["git", "status", "--short"], timeout=30)
    dirty_lines = [ln for ln in status.get("stdout", "").splitlines() if ln.strip()]
    changed_web_src = any("web/src/" in ln for ln in dirty_lines)
    changed_web_dist = any("web/dist/" in ln for ln in dirty_lines)
    stale_dist = changed_web_src and not changed_web_dist

    ok = not forbidden_tracked and not stale_dist
    notes: List[str] = [f"dirty_entries={len(dirty_lines)}"]
    if forbidden_tracked:
        notes.append(f"tracked_local_only={forbidden_tracked[:5]}")
    if stale_dist:
        notes.append("web/src/ modified without web/dist/ rebuild")
    return {
        "ok": ok,
        "dirty_count": len(dirty_lines),
        "tracked_local_only": forbidden_tracked,
        "stale_web_dist": stale_dist,
        "summary": ", ".join(notes),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Hikayat's read-only release and hygiene gate.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON scorecard.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip pytest contract suite (fast static checks only).")
    parser.add_argument("--strict-auth", action="store_true", help="Fail gate if audit_route_auth.py reports findings.")
    args = parser.parse_args(argv)

    py = sys.executable
    db_before = _db_fingerprint()
    checks: Dict[str, Dict[str, Any]] = {}

    checks["static_check"] = _run_cmd([py, "scripts/static_check.py"], timeout=180)
    checks["static_baseline_zero"] = _check_baseline_empty()
    checks["package_release_dry_run"] = _run_cmd([py, "scripts/package_release.py", "--dry-run"], timeout=60)
    checks["locale_parity"] = _run_cmd(
        [py, ".agents/skills/hikayat-scenario-and-content/scripts/check_locale_parity.py"],
        timeout=60,
    )
    checks["table_wiring"] = _run_cmd(
        [py, ".agents/skills/hikayat-db-lifecycle-checklist/scripts/check_table_wiring.py"],
        timeout=60,
    )
    checks["prompt_hygiene"] = _run_cmd(
        [py, ".agents/skills/hikayat-llm-prose-and-prompts/scripts/audit_prompt_hygiene.py"],
        timeout=60,
    )

    auth_cmd = [py, ".agents/skills/hikayat-omnichannel-ui/scripts/audit_route_auth.py", "--json"]
    if args.strict_auth:
        auth_cmd.append("--strict")
    auth_res = _run_cmd(auth_cmd, timeout=60)
    auth_count = 0
    try:
        auth_data = json.loads(auth_res.get("stdout") or "{}")
        auth_count = int(auth_data.get("finding_count", 0))
    except Exception:
        pass
    checks["route_auth_audit"] = {
        "ok": auth_res["ok"] if args.strict_auth else True,
        "finding_count": auth_count,
        "summary": f"{auth_count} advisory finding(s)" + (" [strict]" if args.strict_auth else " [diagnostic]"),
    }

    if not args.skip_tests:
        checks["contract_tests"] = _run_cmd(
            [
                py,
                "scripts/run_tests.py",
                "agent",
                "tests/test_codebase_contracts.py",
                "tests/test_agent_docs_contracts.py",
                "tests/test_five_normalized_models_cutover.py",
            ],
            env_extra={"HIKAYAT_STRICT": "1"},
            timeout=240,
        )

    checks["git_and_dist_hygiene"] = _check_git_and_dist_hygiene()

    db_after = _db_fingerprint()
    db_untouched = db_before == db_after
    checks["live_db_untouched"] = {
        "ok": db_untouched,
        "summary": "hikayat.db untouched" if db_untouched else f"MODIFIED: before={db_before}, after={db_after}",
    }

    # Strip bulky stdout before output.
    compact_checks: Dict[str, Dict[str, Any]] = {
        k: {key: val for key, val in v.items() if key != "stdout"}
        for k, v in checks.items()
    }
    go = all(bool(item.get("ok")) for item in compact_checks.values())
    verdict = "GO" if go else "NO-GO"
    payload = {"verdict": verdict, "ok": go, "checks": compact_checks}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"=== Hikayat Release Gate: {verdict} ===")
        for name, item in compact_checks.items():
            mark = "PASS" if item.get("ok") else "FAIL"
            print(f"  [{mark}] {name}: {item.get('summary', '')}")

    return 0 if go else 1


if __name__ == "__main__":
    raise SystemExit(main())
