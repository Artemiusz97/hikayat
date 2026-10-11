#!/usr/bin/env python3
"""
Accelerated Test Runner for Hikayat.
Optimizes execution time and token consumption for developers and AI agents.

Usage:
    python scripts/run_tests.py quick    # Fast unit & contract tests (< 3s)
    python scripts/run_tests.py changed  # Tests for uncommitted/changed files (pytest-picked)
    python scripts/run_tests.py impact   # Only tests affected by changed bytecode (pytest-testmon)
    python scripts/run_tests.py failed   # Re-run last failed tests, stop on 1st error (--lf -x)
    python scripts/run_tests.py full     # Parallel full suite with worker DB isolation (-n auto)
    python scripts/run_tests.py agent    # Token-minimal runner for AI coding assistants (< 200 tokens)
    python scripts/run_tests.py custom [pytest-args...]
"""
import sys
import subprocess
import argparse
import re
import os

MODES = {
    "quick": ["-m", "unit or contract", "-q", "--tb=short"],
    "changed": ["--picked", "-q", "--tb=short"],
    "impact": ["--testmon", "-q", "--tb=short"],
    "failed": ["--lf", "-x", "-q", "--tb=short"],
    "full": ["-n", "auto", "--dist=loadscope", "-q", "--tb=short", "--maxfail=2"],
    "agent": ["-q", "--tb=short", "--maxfail=1", "--no-header"],
}


def main():
    parser = argparse.ArgumentParser(
        description="Hikayat Accelerated Test Runner (Time & Token Optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        choices=list(MODES.keys()) + ["custom"],
        default="quick",
        nargs="?",
        help="Execution preset: quick, changed, impact, failed, full, agent, custom (default: quick)",
    )

    # Allow passing flags directly (e.g. -k, -v, paths) without failing on unknown args
    raw_args = sys.argv[1:]
    if not raw_args:
        mode = "quick"
        extra_args = []
    elif raw_args[0] in ("-h", "--help"):
        parser.print_help()
        sys.exit(0)
    elif raw_args[0] in MODES or raw_args[0] == "custom":
        mode = raw_args[0]
        extra_args = raw_args[1:]
    else:
        # Default to quick if first argument is a pytest flag or path
        mode = "quick"
        extra_args = raw_args

    cmd = [sys.executable, "-m", "pytest"]
    if mode in MODES:
        cmd.extend(MODES[mode])
    cmd.extend(extra_args)

    if mode == "agent":
        # Ultra-compact runner for LLM / AI context windows:
        # Intercepts stdout and prints only the final pass count or exact failure trace,
        # slashing token usage by 95%+.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output, _ = proc.communicate()

        if proc.returncode == 0:
            match = re.search(r"(\d+\s+passed[^\r\n]*)", output)
            if match:
                print(f"PASSED: {match.group(1)}")
            else:
                print("PASSED: All targeted tests passed successfully.")
        elif proc.returncode == 5:
            print("NO TESTS RUN: No tests matched the specified pattern, marker, or path.")
        else:
            lines = output.splitlines()
            # Filter out progress dots, spinner lines, and node bring-up logs
            clean_lines = [
                line for line in lines
                if not line.startswith(".")
                and not line.startswith("bringing up nodes")
                and not line.startswith("scheduling tests")
            ]
            summary = "\n".join(clean_lines[:100]) if clean_lines else output.strip()
            print(f"FAILED (Exit Code {proc.returncode}):\n{summary}")
        sys.exit(proc.returncode)
    else:
        # Standard interactive execution
        sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
