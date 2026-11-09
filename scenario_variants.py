"""Scenario family / variant grouping.

Preset scenarios form families through their `base_scenario` chain
(e.g. `nsfw_furry_gore_anomalous_high_school` -> `nsfw_gore_anomalous_high_school`
-> `anomalous_high_school`). Delivery adapters (web wizard, Discord) list only
family roots in their primary picker and offer the variants in a second step.
"""
from __future__ import annotations

from typing import Any

from scenario_data import (
    get_localized_genres,
    load_scenarios,
    localize_scenario_entry,
    normalize_locale_code,
)

_STANDARD_LABELS = {
    "en": "Standard",
    "pl": "Standardowy",
    "ms": "Standard",
    "zh": "标准",
    "de": "Standard",
}

_HIDDEN_VARIANT_TAGS = {"non_combat", "non-combat"}


def _is_listable(key: str) -> bool:
    return not str(key).startswith("custom_combinator_")


def get_scenario_family_root(key: str | None) -> str:
    """Return the top-most `base_scenario` ancestor of `key` (itself when it has none)."""
    scenarios = load_scenarios()
    curr = str(key or "").strip()
    if curr not in scenarios:
        return curr
    visited = {curr}
    while True:
        base = scenarios.get(curr, {}).get("base_scenario")
        if base and base in scenarios and base not in visited:
            visited.add(base)
            curr = base
        else:
            return curr


def get_variant_label(key: str, lang: str | None = None) -> str:
    """Short label for a scenario within its family (e.g. 'Feral Carnage', 'Standard')."""
    code = normalize_locale_code(lang)
    raw = load_scenarios().get(key, {})
    loc = (raw.get("locales") or {}).get(code) or {}
    explicit = loc.get("variant_label") or raw.get("variant_label")
    if explicit:
        return str(explicit)
    if get_scenario_family_root(key) == key:
        return _STANDARD_LABELS.get(code, _STANDARD_LABELS["en"])
    entry = localize_scenario_entry(raw, code)
    display = str(entry.get("display_name") or entry.get("name") or key)
    if ": " in display:
        return display.split(": ", 1)[1].strip() or display
    return display


def get_variant_tags(key: str) -> list[str]:
    """Tags a variant adds on top of its family root (e.g. ['furry', 'nsfw'])."""
    scenarios = load_scenarios()
    root_tags = set(scenarios.get(get_scenario_family_root(key), {}).get("tags") or [])
    return [t for t in (scenarios.get(key, {}).get("tags") or [])
            if t not in root_tags and t not in _HIDDEN_VARIANT_TAGS]


def get_family_variants(root_key: str, lang: str | None = None) -> list[dict[str, Any]]:
    """Ordered variants of a family (root first, then scenarios.json order)."""
    code = normalize_locale_code(lang)
    scenarios = load_scenarios()
    root = get_scenario_family_root(root_key)
    genres = get_localized_genres(code)
    keys = [k for k in scenarios if _is_listable(k) and get_scenario_family_root(k) == root]
    keys.sort(key=lambda k: 0 if k == root else 1)
    out: list[dict[str, Any]] = []
    for k in keys:
        entry = localize_scenario_entry(scenarios[k], code)
        tags = scenarios[k].get("tags") or []
        extra = get_variant_tags(k)
        out.append({
            "key": k,
            "variant_label": get_variant_label(k, code),
            "variant_tags": extra,
            "variant_tag_labels": [genres.get(t, {}).get("name", t.replace("_", " ").title()) for t in extra],
            "emoji": scenarios[k].get("emoji", ""),
            "description": entry.get("description", ""),
            "is_root": k == root,
            "is_nsfw": "nsfw" in tags or "gore" in tags,
        })
    return out


def get_family_root_keys() -> list[str]:
    """Listable scenario keys that are family roots, in scenarios.json order."""
    return [k for k in load_scenarios() if _is_listable(k) and get_scenario_family_root(k) == k]


def family_has_variants(key: str | None) -> bool:
    root = get_scenario_family_root(key)
    return sum(1 for k in load_scenarios() if _is_listable(k) and get_scenario_family_root(k) == root) > 1
