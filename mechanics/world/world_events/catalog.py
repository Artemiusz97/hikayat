from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import scenario_data

CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "world_events_catalog.json"

_TAG_TO_FAMILIES: dict[str, tuple[str, ...]] = {
    "fantasy": ("fantasy",),
    "grimdark": ("dark_fantasy", "fantasy"),
    "dark_fantasy": ("dark_fantasy", "fantasy"),
    "isekai": ("isekai", "fantasy"),
    "high_school": ("modern_school",),
    "slice_of_life": ("slice_of_life", "modern_school"),
    "urban_fantasy": ("urban_fantasy",),
    "horror": ("urban_fantasy",),
    "cyberpunk": ("cyberpunk",),
    "space": ("sci_fi",),
    "sci_fi": ("sci_fi",),
    "steampunk": ("steampunk",),
    "post_apocalypse": ("post_apocalypse",),
}

_SUPPORTED_LANGS = ("en", "pl", "ms", "zh", "de")
_CATALOG_CACHE: list[dict[str, Any]] | None = None


def load_event_catalog(*, reload: bool = False) -> list[dict[str, Any]]:
    """Loads procedural world event and rumor templates from data/world_events_catalog.json."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None and not reload:
        return _CATALOG_CACHE
    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("world_events_catalog.json must contain a top-level list of templates.")
    _CATALOG_CACHE = raw
    return _CATALOG_CACHE


def _classify_minor_event_families(scen_key: str | dict | None) -> set[str]:
    """Resolves isolated minor_event genre families strictly for High School and Anomalous Incursions."""
    if not scen_key:
        return set()
    tags_set = {str(t).strip().lower() for t in scenario_data.get_scenario_tags(scen_key)}
    minor_fams: set[str] = set()
    if (
        scenario_data.is_high_school_scenario(scen_key)
        or scenario_data.is_anomalous_high_school_scenario(scen_key)
        or "high_school" in tags_set
        or "school" in tags_set
    ):
        minor_fams.add("minor_high_school")
    if (
        scenario_data.is_anomalous_incursions_scenario(scen_key)
        or "anomalous" in tags_set
        or "anomalous_incursions" in tags_set
        or ("urban_fantasy" in tags_set and "horror" in tags_set)
    ):
        minor_fams.add("minor_anomaly_bureau")
    return minor_fams


def is_minor_event_scenario_eligible(scen_key: str | dict | None) -> bool:
    """Returns True ONLY for High School and Anomalous Incursions scenarios/combinators."""
    return bool(_classify_minor_event_families(scen_key))


def resolve_genre_families(scen_key: str | None) -> set[str]:
    """Resolves canonical genre family tags for any preset or custom combinator scenario."""
    tags = scenario_data.get_scenario_tags(scen_key)
    families: set[str] = set()
    for tag in tags:
        mapped = _TAG_TO_FAMILIES.get(str(tag).strip().lower())
        if mapped:
            families.update(mapped)
    if not families:
        clean_k = str(scen_key or "fantasy").strip().lower()
        for k, fam_tuple in _TAG_TO_FAMILIES.items():
            if k in clean_k:
                families.update(fam_tuple)
    if not families:
        families.add("fantasy")
    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        families.update({"urban_fantasy", "modern_school", "slice_of_life"})
    families.update(_classify_minor_event_families(scen_key))
    return families


def get_eligible_templates(
    scen_key: str,
    entity_type: str | None = None,
    include_nsfw: bool = False,
) -> list[dict[str, Any]]:
    """Returns eligible Macro Event or Rumor templates for scen_key with strict NSFW quarantine."""
    catalog = load_event_catalog()
    families = resolve_genre_families(scen_key)
    scen_allows_nsfw = bool(include_nsfw) and scenario_data.has_tag(scen_key, "nsfw")

    eligible: list[dict[str, Any]] = []
    for tmpl in catalog:
        if entity_type and tmpl.get("entity_type") != entity_type:
            continue
        is_nsfw_tmpl = int(bool(tmpl.get("is_nsfw", 0))) == 1
        if is_nsfw_tmpl and not scen_allows_nsfw:
            continue
        tmpl_fams = set(tmpl.get("genre_families") or [])
        if tmpl_fams & families:
            eligible.append(tmpl)
    return eligible


def _interpolate_slots(text: str, slots: dict[str, str]) -> str:
    if not text:
        return ""
    safe_slots = {
        "faction": str(slots.get("faction") or "the local council"),
        "npc": str(slots.get("npc") or "an unnamed insider"),
        "zone": str(slots.get("zone") or "the central district"),
        "venue": str(slots.get("venue") or "the gathering hall"),
    }
    out = str(text)
    for k, v in safe_slots.items():
        out = out.replace("{" + k + "}", v)
    return out


def render_localized_template(
    template: dict[str, Any],
    slots: dict[str, str] | None = None,
    lang: str = "en",
    force_sfw_fallback: bool = False,
) -> dict[str, Any]:
    """Renders localized template copy in (en, pl, ms, zh, de) with live slot filling and SFW clamping."""
    norm_lang = str(lang or "en").strip().lower()[:2]
    if norm_lang not in _SUPPORTED_LANGS:
        norm_lang = "en"

    locales = template.get("locales") or {}
    loc_block = locales.get(norm_lang) or locales.get("en") or {}
    en_block = locales.get("en") or {}

    slot_map = slots or {}
    title = _interpolate_slots(str(loc_block.get("title") or en_block.get("title") or ""), slot_map)
    raw_desc = _interpolate_slots(str(loc_block.get("description") or en_block.get("description") or ""), slot_map)
    sfw_raw = str(loc_block.get("sfw_fallback") or en_block.get("sfw_fallback") or "")
    sfw_desc = _interpolate_slots(sfw_raw, slot_map) if sfw_raw else raw_desc

    is_nsfw = int(bool(template.get("is_nsfw", 0)))
    active_desc = sfw_desc if (is_nsfw and force_sfw_fallback) else raw_desc

    bounty_title = _interpolate_slots(str(loc_block.get("bounty_title") or en_block.get("bounty_title") or title), slot_map)
    bounty_obj = _interpolate_slots(str(loc_block.get("bounty_objective") or en_block.get("bounty_objective") or active_desc), slot_map)

    return {
        "template_key": str(template.get("template_key") or ""),
        "entity_type": str(template.get("entity_type") or "macro_event"),
        "event_subtype": str(template.get("event_subtype") or "crisis"),
        "is_nsfw": is_nsfw,
        "title": title,
        "description": active_desc,
        "sfw_fallback_description": sfw_desc,
        "bounty_title": bounty_title,
        "bounty_objective": bounty_obj,
        "can_spawn_bounty": bool(template.get("can_spawn_bounty", False)),
        "escalation_chance": float(template.get("escalation_chance") or 0.0),
        "default_duration_minutes": int(template.get("default_duration_minutes") or 5760),
        "modifiers": dict(template.get("modifiers") or {}),
    }
