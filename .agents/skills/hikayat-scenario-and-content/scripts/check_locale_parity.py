#!/usr/bin/env python3
"""Read-only 5-language localization parity checker for Hikayat.

Verifies key and placeholder parity across:
  1. Frontend i18next JSON bundles (`web/src/locales/{en,pl,ms,zh,de}.json`)
  2. Backend Python localization tables (`localization/{en,pl,ms,zh,de}.py`)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import localization  # noqa: E402

PLACEHOLDER_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}|\{([A-Za-z0-9_]+)\}")
PY_DICT_ATTRS: Tuple[str, ...] = (
    "ENEMY_AFFIXES",
    "ITEM_ICON_KEYWORDS",
    "REALTY_LABELS",
    "FOLKLORE_SANCTUARY_LABELS",
    "QUEST_UI_LABELS",
    "PACT_UI_LABELS",
    "ANOMALOUS_SITE_UI_LABELS",
)
PY_PLACEHOLDER_DICTS: Tuple[str, ...] = (
    "REALTY_LABELS",
    "QUEST_UI_LABELS",
    "PACT_UI_LABELS",
    "ANOMALOUS_SITE_UI_LABELS",
)
PY_NONEMPTY_SEQ_ATTRS: Tuple[str, ...] = (
    "TWO_HANDED_KEYWORDS",
    "TWO_HANDED_ARCHETYPES",
    "DIALOGUE_EXIT_PHRASES",
    "DIALOGUE_INIT_PREFIXES",
    "MOVEMENT_PREFIXES",
)


def _extract_placeholders(text: Any) -> Set[str]:
    if not isinstance(text, str):
        return set()
    return {m[0] or m[1] for m in PLACEHOLDER_RE.findall(text) if (m[0] or m[1])}


def _flatten_json(obj: Any, prefix: str = "") -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    if isinstance(obj, dict):
        for key, value in obj.items():
            full_key = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                flat.update(_flatten_json(value, full_key))
            else:
                flat[full_key] = value
    return flat


def _check_json_locales() -> Dict[str, Any]:
    locales_dir = REPO_ROOT / "web" / "src" / "locales"
    loaded: Dict[str, Dict[str, Any]] = {}
    for lang in localization.SUPPORTED_LOCALES:
        path = locales_dir / f"{lang}.json"
        if not path.is_file():
            return {"error": f"Missing locale JSON file: {path.relative_to(REPO_ROOT).as_posix()}", "issues": 1}
        loaded[lang] = _flatten_json(json.loads(path.read_text(encoding="utf-8")))

    base = loaded["en"]
    base_keys = set(base.keys())
    per_locale: Dict[str, Dict[str, List[str]]] = {}
    issue_count = 0

    for lang in localization.SUPPORTED_LOCALES:
        if lang == "en":
            continue
        cur = loaded[lang]
        cur_keys = set(cur.keys())
        missing = sorted(base_keys - cur_keys)
        extra = sorted(cur_keys - base_keys)
        placeholder_mismatches: List[str] = []
        for key in sorted(base_keys & cur_keys):
            expected_ph = _extract_placeholders(base[key])
            actual_ph = _extract_placeholders(cur[key])
            if expected_ph != actual_ph:
                placeholder_mismatches.append(
                    f"{key} (en={sorted(expected_ph)}, {lang}={sorted(actual_ph)})"
                )
        issue_count += len(missing) + len(extra) + len(placeholder_mismatches)
        per_locale[lang] = {
            "missing_keys": missing,
            "extra_keys": extra,
            "placeholder_mismatches": placeholder_mismatches,
        }

    return {
        "total_en_keys": len(base_keys),
        "per_locale": per_locale,
        "issues": issue_count,
    }


def _check_python_locales() -> Dict[str, Any]:
    dict_diffs: Dict[str, Dict[str, Dict[str, List[str]]]] = {}
    seq_missing: Dict[str, List[str]] = {}
    issue_count = 0
    en_mod = localization.LOCALES["en"]

    for attr in PY_DICT_ATTRS:
        base_dict = getattr(en_mod, attr, {}) or {}
        base_keys = set(base_dict.keys())
        attr_report: Dict[str, Dict[str, List[str]]] = {}
        for lang in localization.SUPPORTED_LOCALES:
            if lang == "en":
                continue
            cur_dict = getattr(localization.LOCALES[lang], attr, {}) or {}
            cur_keys = set(cur_dict.keys())
            missing = sorted(base_keys - cur_keys)
            extra = sorted(cur_keys - base_keys)
            ph_mismatches: List[str] = []
            if attr in PY_PLACEHOLDER_DICTS:
                for key in sorted(base_keys & cur_keys):
                    expected_ph = _extract_placeholders(base_dict[key])
                    actual_ph = _extract_placeholders(cur_dict[key])
                    if expected_ph != actual_ph:
                        ph_mismatches.append(
                            f"{key} (en={sorted(expected_ph)}, {lang}={sorted(actual_ph)})"
                        )
            if missing or extra or ph_mismatches:
                issue_count += len(missing) + len(extra) + len(ph_mismatches)
                attr_report[lang] = {
                    "missing_keys": missing,
                    "extra_keys": extra,
                    "placeholder_mismatches": ph_mismatches,
                }
        if attr_report:
            dict_diffs[attr] = attr_report

    for lang in localization.SUPPORTED_LOCALES:
        mod = localization.LOCALES[lang]
        empty_attrs = [attr for attr in PY_NONEMPTY_SEQ_ATTRS if not getattr(mod, attr, None)]
        if empty_attrs:
            issue_count += len(empty_attrs)
            seq_missing[lang] = empty_attrs

    return {
        "dict_diffs": dict_diffs,
        "empty_sequences": seq_missing,
        "issues": issue_count,
    }


T_CALL_RE = re.compile(r"(?<![A-Za-z0-9_$.])t\(\s*['\"]([A-Za-z0-9_]+(?:\.[A-Za-z0-9_\-]+)+)['\"]")
PLURAL_SUFFIXES: Tuple[str, ...] = ("_one", "_other", "_zero", "_few", "_many")


def _check_frontend_usage(en_keys: Set[str]) -> Dict[str, Any]:
    src_root = REPO_ROOT / "web" / "src"
    if not src_root.is_dir():
        return {"files_scanned": 0, "keys_checked": 0, "missing_in_en": [], "issues": 0}

    key_prefixes: Set[str] = set()
    for key in en_keys:
        parts = key.split(".")
        for idx in range(1, len(parts)):
            key_prefixes.add(".".join(parts[:idx]))

    files = sorted(p for p in src_root.rglob("*") if p.is_file() and p.suffix in {".js", ".jsx"})
    seen_keys: Set[str] = set()
    missing_refs: List[str] = []

    for path in files:
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for key in T_CALL_RE.findall(line):
                seen_keys.add(key)
                if key in en_keys or key in key_prefixes:
                    continue
                if any(f"{key}{suf}" in en_keys for suf in PLURAL_SUFFIXES):
                    continue
                missing_refs.append(f"{rel}:{line_no} -> {key}")

    return {
        "files_scanned": len(files),
        "keys_checked": len(seen_keys),
        "missing_in_en": sorted(set(missing_refs)),
        "issues": len(set(missing_refs)),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check 5-language JSON and Python locale parity.")
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    parser.add_argument(
        "--check-usage",
        action="store_true",
        help="Also scan web/src/**/*.{js,jsx} for static t('...') keys missing from en.json.",
    )
    args = parser.parse_args(argv)

    json_report = _check_json_locales()
    py_report = _check_python_locales()
    usage_report: Dict[str, Any] = {}
    if args.check_usage:
        en_path = REPO_ROOT / "web" / "src" / "locales" / "en.json"
        en_keys = set(_flatten_json(json.loads(en_path.read_text(encoding="utf-8"))).keys()) if en_path.is_file() else set()
        usage_report = _check_frontend_usage(en_keys)

    total_issues = (
        int(json_report.get("issues", 0))
        + int(py_report.get("issues", 0))
        + int(usage_report.get("issues", 0))
    )
    payload: Dict[str, Any] = {
        "ok": total_issues == 0,
        "total_issues": total_issues,
        "locales": list(localization.SUPPORTED_LOCALES),
        "frontend_json": json_report,
        "backend_python": py_report,
    }
    if args.check_usage:
        payload["frontend_usage"] = usage_report

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(
            f"Locale parity across {len(localization.SUPPORTED_LOCALES)} languages "
            f"({', '.join(localization.SUPPORTED_LOCALES)}): "
            f"{json_report.get('total_en_keys', 0)} JSON keys checked."
        )
        if args.check_usage:
            print(
                f"Frontend usage scan: {usage_report.get('files_scanned', 0)} file(s), "
                f"{usage_report.get('keys_checked', 0)} unique t(...) key(s), "
                f"{usage_report.get('issues', 0)} missing in en.json."
            )
        if total_issues == 0:
            print("OK: 0 key/placeholder/sequence mismatches in web/src/locales/*.json and localization/*.py.")
        else:
            print(f"FOUND {total_issues} parity issue(s):")
            print(json.dumps(payload, indent=2, ensure_ascii=False))

    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
