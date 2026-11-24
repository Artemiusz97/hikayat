#!/usr/bin/env python3
"""Antigravity PreToolUse safety guard for Hikayat `run_command` executions.

Reads camelCase Antigravity hook JSON from stdin and emits a decision JSON object:
  - `deny`: hard blocks `git add -f`/`--force` on local-only gitignored paths and
    simulator invocations passing `--live-db`.
  - `force_ask`: forces explicit user approval on `git push`, `git reset --hard`,
    `git clean -fd`, or destructive file commands targeting `hikayat.db`.
  - `allow`: permits all other commands to proceed under normal policy.
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict

# Segment separator for chained shell commands (&&, ||, ;, |, newline).
CMD_START = r"(?:^|[;&|\r\n]\s*)"

GIT_FORCE_ADD_RE = re.compile(
    CMD_START + r"git\b[^\r\n;&|]*\badd\b[^\r\n;&|]*(?:\s-[A-Za-z]*f[A-Za-z]*\b|\s--force\b)[^\r\n;&|]*",
    re.IGNORECASE,
)
LOCAL_ONLY_TARGET_RE = re.compile(
    r"(?:^|[\s\"'\\/\.,])(?:tests(?:[/\\]|$|\b)|pytest\.ini\b|scripts[/\\]run_tests\.py\b|scripts[/\\]simulate_|\.desloppify(?:[/\\]|$|\b))",
    re.IGNORECASE,
)
SIM_LIVE_DB_RE = re.compile(
    r"\bsimulate_[a-z0-9_]+\.py\b[^\r\n;&|]*--live-db\b",
    re.IGNORECASE,
)
GIT_PUSH_RE = re.compile(
    CMD_START + r"git(?:\s+(?:-[Cc]\s+\S+|-[A-Za-z]+))*\s+push\b",
    re.IGNORECASE,
)
GIT_DESTRUCTIVE_RE = re.compile(
    CMD_START + r"git(?:\s+(?:-[Cc]\s+\S+|-[A-Za-z]+))*\s+(?:reset\s+--hard\b|clean\s+-[A-Za-z]*f[A-Za-z]*d|clean\s+-[A-Za-z]*d[A-Za-z]*f)",
    re.IGNORECASE,
)
LIVE_DB_DESTRUCTIVE_RE = re.compile(
    CMD_START + r"(?:rm|del|erase|Remove-Item|Clear-Content|Set-Content)\b[^\r\n;&|]*\bhikayat\.db\b",
    re.IGNORECASE,
)


def evaluate_command(cmd: str) -> Dict[str, Any]:
    text = (cmd or "").strip()
    if not text:
        return {"decision": "allow"}

    for match in GIT_FORCE_ADD_RE.finditer(text):
        segment = match.group(0)
        if LOCAL_ONLY_TARGET_RE.search(segment):
            return {
                "decision": "deny",
                "reason": (
                    "Blocked by hikayat-safety-guard: never `git add -f` local-only gitignored files "
                    "(tests/, pytest.ini, scripts/run_tests.py, scripts/simulate_*.py, .desloppify/)."
                ),
            }

    if SIM_LIVE_DB_RE.search(text):
        return {
            "decision": "deny",
            "reason": (
                "Blocked by hikayat-safety-guard: never pass `--live-db` to Hikayat fuzz simulators "
                "(live hikayat.db protection)."
            ),
        }

    if GIT_PUSH_RE.search(text):
        return {
            "decision": "force_ask",
            "reason": "Hikayat safety guard: `git push` requires explicit user confirmation.",
        }

    if GIT_DESTRUCTIVE_RE.search(text):
        return {
            "decision": "force_ask",
            "reason": "Hikayat safety guard: destructive git reset/clean requires explicit user confirmation.",
        }

    if LIVE_DB_DESTRUCTIVE_RE.search(text):
        return {
            "decision": "force_ask",
            "reason": "Hikayat safety guard: destructive operation targeting live `hikayat.db` requires confirmation.",
        }

    return {"decision": "allow"}


def main() -> int:
    raw = sys.stdin.read().strip()
    payload: Dict[str, Any] = {}
    if raw:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            print(json.dumps({"decision": "allow"}))
            return 0

    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else {}
    tool_name = str(tool_call.get("name") or "")
    if tool_name and tool_name != "run_command":
        print(json.dumps({"decision": "allow"}))
        return 0

    args = tool_call.get("args") if isinstance(tool_call.get("args"), dict) else {}
    cmd = str(args.get("CommandLine") or args.get("command") or "")
    result = evaluate_command(cmd)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
