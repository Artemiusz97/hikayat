from __future__ import annotations
"""
Static & Compositional Entity Patron Catalog (Layer 2).

Loads `data/entity_patrons.json`, enforces scenario tag gates (`nsfw`, `gore`, `furry`),
maps Canonical Folklore Codex sapient spirits, deterministically synthesizes Pacts for
captured procedural `sapient` anomalies across 9 x 4 = 36 zero-MP templates, and registers
all Pact combat skills (`mp_cost: 0`) into in-memory `SPELL_REGISTRY`.
"""

import copy
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from localization import SUPPORTED_LOCALES


def _normalize_locale_code(lang: str | None) -> str:
    raw = str(lang or "en").strip().lower().split("-")[0].split("_")[0]
    return raw if raw in SUPPORTED_LOCALES else "en"
from mechanics.combat.spells.registry import SPELL_REGISTRY
from mechanics.world.anomaly_engine import normalize_anomaly_element
from scenario_data import (
    has_tag,
    is_anomalous_high_school_scenario,
    is_anomalous_incursions_scenario,
)

log = logging.getLogger(__name__)

PATRONS_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "entity_patrons.json"
FOLKLORE_CODEX_PATH = Path(__file__).resolve().parents[2] / "data" / "folklore_codex.json"

_PATRONS_CACHE: Optional[Dict[str, Any]] = None
_FOLKLORE_BY_ID_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_PACT_SPELLS_REGISTERED: bool = False

VALID_ARCHETYPES: Tuple[str, ...] = ("vanguard", "catalyst", "breaker", "warden")


def is_entity_contracts_scenario(scenario_or_key: Any) -> bool:
    """Returns True for Anomalous Incursions, Anomalous High School, and all 6 gore/furry/nsfw variants."""
    return bool(
        is_anomalous_incursions_scenario(scenario_or_key)
        or is_anomalous_high_school_scenario(scenario_or_key)
    )


def load_entity_patrons_catalog(*, reload: bool = False) -> Dict[str, Any]:
    """Loads and caches `data/entity_patrons.json`."""
    global _PATRONS_CACHE
    if _PATRONS_CACHE is not None and not reload:
        return _PATRONS_CACHE
    raw = json.loads(PATRONS_DATA_PATH.read_text(encoding="utf-8"))
    _PATRONS_CACHE = raw if isinstance(raw, dict) else {}
    return _PATRONS_CACHE


def _load_folklore_entries_by_id() -> Dict[str, Dict[str, Any]]:
    global _FOLKLORE_BY_ID_CACHE
    if _FOLKLORE_BY_ID_CACHE is not None:
        return _FOLKLORE_BY_ID_CACHE
    out: Dict[str, Dict[str, Any]] = {}
    if FOLKLORE_CODEX_PATH.is_file():
        try:
            data = json.loads(FOLKLORE_CODEX_PATH.read_text(encoding="utf-8"))
            for entry in data.get("entries") or []:
                if isinstance(entry, dict) and entry.get("codex_id"):
                    out[str(entry["codex_id"])] = entry
        except Exception as exc:
            log.warning("Failed loading folklore_codex.json in pacts catalog: %s", exc)
    _FOLKLORE_BY_ID_CACHE = out
    return out


def apply_patron_variant_and_locale(
    patron: Dict[str, Any],
    scenario_or_key: Any = None,
    lang: str | None = "en",
) -> Dict[str, Any]:
    """Applies `gore` / `furry` visual overrides and 5-locale (`en`, `pl`, `ms`, `zh`, `de`) strings."""
    out = copy.deepcopy(patron)
    out.setdefault("canonical_name", out.get("name", ""))
    out.setdefault("canonical_title", out.get("title", ""))

    visuals = dict(out.get("visuals") or {})
    if scenario_or_key:
        if has_tag(scenario_or_key, "gore") and visuals.get("gore_rest_override"):
            visuals["active_rest_tags"] = list(visuals["gore_rest_override"])
        elif has_tag(scenario_or_key, "furry") and visuals.get("furry_rest_override"):
            visuals["active_rest_tags"] = list(visuals["furry_rest_override"])
        else:
            visuals["active_rest_tags"] = list(visuals.get("rest_tags") or [])
    else:
        visuals["active_rest_tags"] = list(visuals.get("rest_tags") or [])
    out["visuals"] = visuals

    code = _normalize_locale_code(lang)
    loc_map = out.get("locales") or {}
    loc = loc_map.get(code) or loc_map.get("en") or {}
    if isinstance(loc, dict):
        if loc.get("name"):
            out["display_name"] = str(loc["name"])
        if loc.get("title"):
            out["display_title"] = str(loc["title"])
        if loc.get("summary"):
            out["summary"] = str(loc["summary"])
    out.setdefault("display_name", out.get("name", "Unknown Entity"))
    out.setdefault("display_title", out.get("title", "Anomalous Patron"))
    out.setdefault("summary", out.get("combat_skill", {}).get("description", ""))
    return out


def is_patron_allowed_in_scenario(patron: Dict[str, Any], scenario_or_key: Any) -> bool:
    """Checks `required_tags` (e.g. `["nsfw"]`) strictly against active scenario tags."""
    req_tags = [str(t).strip().lower() for t in (patron.get("required_tags") or []) if t]
    if not req_tags:
        return True
    if not scenario_or_key:
        return False
    return all(has_tag(scenario_or_key, tag) for tag in req_tags)


def get_bespoke_patrons(
    scenario_or_key: Any = None,
    lang: str | None = "en",
    *,
    include_gated: bool = False,
) -> List[Dict[str, Any]]:
    """Returns the bespoke Patrons permitted by `scenario_or_key` (15 SFW/gore/furry + 3 `nsfw`-gated)."""
    cat = load_entity_patrons_catalog()
    result: List[Dict[str, Any]] = []
    for entry in cat.get("bespoke_patrons") or []:
        if not isinstance(entry, dict):
            continue
        if not include_gated and scenario_or_key is not None and not is_patron_allowed_in_scenario(entry, scenario_or_key):
            continue
        if not include_gated and scenario_or_key is None and entry.get("required_tags"):
            continue
        enriched = apply_patron_variant_and_locale(entry, scenario_or_key=scenario_or_key, lang=lang)
        enriched["source_pool"] = "bespoke"
        result.append(enriched)
    return result


def synthesize_folklore_patron(
    codex_id_or_entry: str | Dict[str, Any],
    *,
    scenario_or_key: Any = None,
    lang: str | None = "en",
) -> Optional[Dict[str, Any]]:
    """Builds a Patron profile for a sapient (or Saka familiar) Folklore Codex entity."""
    cat = load_entity_patrons_catalog()
    folklore_profiles = cat.get("folklore_patrons") or {}
    codex_by_id = _load_folklore_entries_by_id()

    if isinstance(codex_id_or_entry, dict):
        codex_entry = codex_id_or_entry
        cid = str(codex_entry.get("codex_id") or "").strip()
    else:
        raw_id = str(codex_id_or_entry or "").strip()
        if raw_id.startswith("folk_patron_"):
            for k, prof in folklore_profiles.items():
                if str(prof.get("patron_id")) == raw_id:
                    raw_id = k
                    break
            else:
                raw_id = "folk_" + raw_id[len("folk_patron_"):]
        cid = raw_id
        codex_entry = codex_by_id.get(cid) or {}

    if cid in folklore_profiles:
        prof = copy.deepcopy(folklore_profiles[cid])
        prof.setdefault("regulated", True)
        prof.setdefault("source_pool", "folklore")
        prof.setdefault("required_tags", [])
        prof.setdefault("appraisal", {
            "favored_min_stats": {prof.get("synergy_stat", "INT"): 6},
            "favored_quote": "You know the old rites. Let us bind the covenant properly.",
            "neutral_quote": "Honor the offering and taboo, mortal, and my strength is yours.",
            "disdained_quote": "Ignorant of tradition. Your tribute will be steeper.",
        })
        return apply_patron_variant_and_locale(prof, scenario_or_key=scenario_or_key, lang=lang)

    if not codex_entry:
        return None
    sapience = str(codex_entry.get("sapience") or "").strip().lower()
    if sapience != "sapient" and cid != "folk_toyol":
        return None

    elem = normalize_anomaly_element(codex_entry.get("primary_element"), fallback="aether")
    c_prof = codex_entry.get("combat_profile") or {}
    arch = str(c_prof.get("archetype") or "catalyst").strip().lower()
    if arch not in VALID_ARCHETYPES:
        arch = "catalyst"

    proc_templates = cat.get("procedural_skill_templates") or {}
    tpl = proc_templates.get(f"{elem}_{arch}") or next(iter(proc_templates.values()))
    form_key = str(codex_entry.get("form") or "default").strip().lower()
    util_tpl = (cat.get("procedural_form_utilities") or {}).get(form_key) or (cat.get("procedural_form_utilities") or {}).get("default", {})
    taboo_obj = codex_entry.get("taboo") if isinstance(codex_entry.get("taboo"), dict) else {}
    taboo_id = str(taboo_obj.get("id") or f"taboo_{cid}")
    taboo_desc = str(taboo_obj.get("rule_text") or taboo_obj.get("hint") or "Never violate the spirit's ancient taboo.")

    canon_name = str(codex_entry.get("canonical_name") or cid.replace("folk_", "").replace("_", " ").title())
    subtitle = str(codex_entry.get("subtitle") or "Bound Folklore Entity")
    skill_copy = copy.deepcopy(tpl["combat_skill"])
    skill_copy["base_id"] = f"pact_{cid}"
    skill_copy["name"] = f"{canon_name}'s {skill_copy['name'].split()[-1]}"

    synthesized = {
        "patron_id": f"folk_patron_{cid.replace('folk_', '')}",
        "codex_id": cid,
        "source_pool": "folklore",
        "regulated": True,
        "name": canon_name,
        "title": subtitle,
        "element": elem,
        "synergy_stat": tpl.get("synergy_stat", "INT"),
        "required_tags": [],
        "appraisal": {
            "favored_min_stats": {tpl.get("synergy_stat", "INT"): 6},
            "favored_quote": f"{canon_name} inclines its head toward your resonant aura.",
            "neutral_quote": f"{canon_name} weighs your pulse and names its terms.",
            "disdained_quote": f"{canon_name} curls its lip, demanding a heavier toll.",
        },
        "combat_skill": skill_copy,
        "field_utility": {
            "id": f"util_{cid}",
            "name": util_tpl.get("name", "Folklore Omen"),
            "dc_modifiers": dict(util_tpl.get("dc_modifiers") or {"PER": -1}),
            "travel_time_mult": util_tpl.get("travel_time_mult", 1.0),
            "summary": util_tpl.get("summary", "-1 PER/INT DC on anomalous investigations."),
        },
        "costs": {
            "cost_model": "folklore_vow",
            "tier_max_hp_lock_pct": [0.05, 0.08, 0.12],
            "tier_stat_locks": [{}, {}, {}],
            "hp_pct_per_cast": list(tpl.get("hp_pct_per_cast") or [0.09, 0.10, 0.11]),
            "tithe": {"interval_days": 4, "item_keywords": ["incense", "food", "tea", "charm"], "credit_fallback": 50, "label": f"{canon_name} Ritual Offering"},
            "taboo_id": taboo_id,
            "taboo_desc": taboo_desc,
        },
        "bound_gear": None,
        "visuals": {
            "rest_tell_prose": f"a subtle {elem}-tinted spirit mark tied to {canon_name}",
            "rest_tags": [f"{elem} spirit mark", "occult talisman"],
            "cast_tags": [f"spectral {elem} aura", "folklore apparition"],
        },
        "locales": {
            "en": {"name": canon_name, "title": subtitle, "summary": f"Folklore covenant with {canon_name}: {skill_copy['name']} & {util_tpl.get('name', 'Omen Sense')}."},
        },
    }
    return apply_patron_variant_and_locale(synthesized, scenario_or_key=scenario_or_key, lang=lang)


def synthesize_procedural_sapient_patron(
    anomaly_record: Dict[str, Any],
    *,
    scenario_or_key: Any = None,
    lang: str | None = "en",
) -> Optional[Dict[str, Any]]:
    """Deterministically synthesizes a Patron from a captured procedural `sapient` anomaly."""
    if not isinstance(anomaly_record, dict):
        return None
    if anomaly_record.get("codex_id"):
        return synthesize_folklore_patron(str(anomaly_record["codex_id"]), scenario_or_key=scenario_or_key, lang=lang)

    sapience = str(
        anomaly_record.get("sapience")
        or (anomaly_record.get("classification") or {}).get("sapience")
        or "sapient"
    ).strip().lower()
    if sapience and sapience not in ("sapient",):
        return None

    cat = load_entity_patrons_catalog()
    elem = normalize_anomaly_element(
        anomaly_record.get("primary_element") or anomaly_record.get("element") or anomaly_record.get("attribute"),
        fallback="aether",
    )
    c_prof = anomaly_record.get("combat_profile") if isinstance(anomaly_record.get("combat_profile"), dict) else {}
    arch = str(anomaly_record.get("archetype") or c_prof.get("archetype") or "").strip().lower()
    raw_seed = str(
        anomaly_record.get("anomaly_id")
        or anomaly_record.get("id")
        or anomaly_record.get("name")
        or anomaly_record.get("entity_name")
        or "proc_sapient"
    )
    digest = hashlib.sha256(f"{elem}:{raw_seed}".encode("utf-8")).digest()
    if arch not in VALID_ARCHETYPES:
        arch = VALID_ARCHETYPES[digest[0] % len(VALID_ARCHETYPES)]

    tpl_map = cat.get("procedural_skill_templates") or {}
    tpl = tpl_map.get(f"{elem}_{arch}") or next(iter(tpl_map.values()))
    form_key = str(
        anomaly_record.get("form")
        or (anomaly_record.get("classification") or {}).get("form")
        or "default"
    ).strip().lower()
    util_tpl = (cat.get("procedural_form_utilities") or {}).get(form_key) or (cat.get("procedural_form_utilities") or {}).get("default", {})

    taboo_obj = anomaly_record.get("taboo") if isinstance(anomaly_record.get("taboo"), dict) else {}
    taboo_id = str(anomaly_record.get("taboo_id") or taboo_obj.get("id") or f"proc_taboo_{digest[:3].hex()}")
    taboo_desc = str(
        anomaly_record.get("taboo_desc")
        or taboo_obj.get("rule_text")
        or taboo_obj.get("hint")
        or "Never breach the entity's containment clause."
    )
    threat_tier = max(1, min(5, int(anomaly_record.get("threat_tier") or anomaly_record.get("tier") or 2)))
    hp_scale = 1.0 + max(0, threat_tier - 2) * 0.08
    base_hp_casts = [round(min(0.24, c * hp_scale), 3) for c in (tpl.get("hp_pct_per_cast") or [0.09, 0.10, 0.11])]

    stable_slug = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:10]
    patron_id = str(anomaly_record.get("patron_id") or f"proc_patron_{elem}_{arch}_{stable_slug}")
    entity_name = str(anomaly_record.get("name") or anomaly_record.get("entity_name") or f"Contained {elem.title()} Entity")
    title = str(anomaly_record.get("subtitle") or f"Contained Tier-{threat_tier} {elem.title()} {arch.title()}")

    skill_copy = copy.deepcopy(tpl["combat_skill"])
    # Reuse the 36 shared template spell IDs in SPELL_REGISTRY so procedural pacts never bloat memory!
    skill_copy["base_id"] = f"pact_proc_{elem}_{arch}"

    synthesized = {
        "patron_id": patron_id,
        "source_pool": "procedural",
        "regulated": True,
        "name": entity_name,
        "title": title,
        "element": elem,
        "archetype": arch,
        "synergy_stat": tpl.get("synergy_stat", "INT"),
        "required_tags": [],
        "appraisal": {
            "favored_min_stats": {tpl.get("synergy_stat", "INT"): 6},
            "favored_quote": "Through the containment glass, the anomaly mirrors your stance in eerie harmony.",
            "neutral_quote": "The contained intelligence accepts a measured exchange of vitality.",
            "disdained_quote": "Its resonance grates against yours, demanding extra blood per invocation.",
        },
        "combat_skill": skill_copy,
        "field_utility": {
            "id": f"util_proc_{elem}_{arch}",
            "name": util_tpl.get("name", "Anomalous Omen Sense"),
            "dc_modifiers": dict(util_tpl.get("dc_modifiers") or {"PER": -1}),
            "travel_time_mult": util_tpl.get("travel_time_mult", 1.0),
            "summary": util_tpl.get("summary", "-1 PER/INT DC on anomalous checks."),
        },
        "costs": {
            "cost_model": "procedural_containment_lease",
            "tier_max_hp_lock_pct": [0.05, 0.08, 0.12],
            "tier_stat_locks": [{}, {}, {}],
            "hp_pct_per_cast": base_hp_casts,
            "tithe": None,
            "taboo_id": taboo_id,
            "taboo_desc": taboo_desc,
        },
        "bound_gear": None,
        "visuals": {
            "rest_tell_prose": f"a faint {elem} containment brand pulsing softly at the wrist",
            "rest_tags": [f"glowing {elem} sigil", "containment cuff mark"],
            "cast_tags": [f"{elem} energy manifestation", "eldritch silhouette"],
        },
        "locales": {
            "en": {"name": entity_name, "title": title, "summary": f"Synthesized zero-MP {elem} {arch} pact ({skill_copy['name']})."},
        },
    }
    return apply_patron_variant_and_locale(synthesized, scenario_or_key=scenario_or_key, lang=lang)


def get_patron_by_id(
    patron_id: str,
    *,
    scenario_or_key: Any = None,
    lang: str | None = "en",
    contained_records: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Resolves any Bespoke, Folklore Codex, or Contained Procedural Patron by ID."""
    pid = str(patron_id or "").strip()
    if not pid:
        return None
    cat = load_entity_patrons_catalog()
    for entry in cat.get("bespoke_patrons") or []:
        if str(entry.get("patron_id")) == pid:
            p = apply_patron_variant_and_locale(entry, scenario_or_key=scenario_or_key, lang=lang)
            p["source_pool"] = "bespoke"
            return p

    if pid.startswith(("folk_patron_", "folk_")):
        return synthesize_folklore_patron(pid, scenario_or_key=scenario_or_key, lang=lang)

    if contained_records:
        for rec in contained_records:
            if not isinstance(rec, dict):
                continue
            cand = synthesize_procedural_sapient_patron(rec, scenario_or_key=scenario_or_key, lang=lang)
            if cand and cand.get("patron_id") == pid:
                return cand

    if pid.startswith("proc_patron_"):
        parts = pid.split("_")
        if len(parts) >= 5:
            elem, arch = parts[2], parts[3]
            return synthesize_procedural_sapient_patron(
                {"patron_id": pid, "primary_element": elem, "archetype": arch, "sapience": "sapient"},
                scenario_or_key=scenario_or_key,
                lang=lang,
            )
    return None


def build_pact_spell_id(patron_or_base_id: Dict[str, Any] | str, tier: int = 1) -> str:
    """Returns the canonical in-memory `SPELL_REGISTRY` ID for a Patron's combat skill at Tier 1..3."""
    clamped_tier = max(1, min(3, int(tier or 1)))
    if isinstance(patron_or_base_id, dict):
        c_skill = patron_or_base_id.get("combat_skill") or {}
        base_id = str(c_skill.get("base_id") or f"pact_{patron_or_base_id.get('patron_id', 'unknown')}")
    else:
        base_id = str(patron_or_base_id or "pact_unknown")
    if base_id.endswith(("_t1", "_t2", "_t3")):
        base_id = base_id[:-3]
    return f"{base_id}_t{clamped_tier}"


def build_pact_spell_def(patron: Dict[str, Any], tier: int = 1) -> Dict[str, Any]:
    """Constructs a `SPELL_REGISTRY`-compatible `mp_cost: 0` spell dictionary for Tier 1..3."""
    t_idx = max(0, min(2, int(tier or 1) - 1))
    clamped_tier = t_idx + 1
    c_skill = patron.get("combat_skill") or {}
    mults = list(c_skill.get("power_mult_tiers") or [1.5, 1.9, 2.4])
    power_mult = float(mults[min(t_idx, len(mults) - 1)])

    target_type = str(c_skill.get("target_type") or "single")
    if clamped_tier >= 2 and c_skill.get("tier2_target_type"):
        target_type = str(c_skill["tier2_target_type"])

    tier_labels = {1: "Pact I", 2: "Pact II", 3: "Pact III"}
    spell_id = build_pact_spell_id(patron, clamped_tier)
    roman = ("I", "II", "III")[t_idx]

    spell_def: Dict[str, Any] = {
        "id": spell_id,
        "base_pact_skill_id": str(c_skill.get("base_id") or spell_id[:-3]),
        "patron_id": str(patron.get("patron_id") or ""),
        "name": f"{c_skill.get('name', 'Pact Invocation')} ({roman})",
        "emoji": str(c_skill.get("emoji") or "🩸"),
        "discipline": str(c_skill.get("discipline") or "attack"),
        "damage_type": str(c_skill.get("damage_type") or "aether"),
        "element": str(patron.get("element") or "aether"),
        "tier": 4 - clamped_tier,  # Hikayat SPELL_REGISTRY uses 3=Basic, 2=Advanced, 1=Master
        "pact_tier": clamped_tier,
        "tier_name": tier_labels[clamped_tier],
        "target_type": target_type,
        "mp_cost": 0,
        "is_pact_skill": True,
        "synergy_stat": str(patron.get("synergy_stat") or "INT"),
        "power_mult": power_mult,
        "poise_shred_mult": float(c_skill.get("poise_shred_mult") or 1.0),
        "pierces_dt": bool(c_skill.get("pierces_dt", False)),
        "strips_shields": bool(c_skill.get("strips_shields", False)),
        "unavoidable": bool(c_skill.get("unavoidable", False)),
        "enters_stealth": bool(c_skill.get("enters_stealth", False)),
        "grants_evade_counter": bool(c_skill.get("grants_evade_counter", False)),
        "cleanses_party": bool(c_skill.get("cleanses_party", False)),
        "steals_credits": bool(c_skill.get("steals_credits", False)),
        "grants_temp_hp_pct": float(c_skill.get("grants_temp_hp_pct") or 0.0),
        "heal_self_pct": float(
            c_skill.get("heal_self_pct")
            or (c_skill.get("heal_self_pct_tier3") if clamped_tier >= 3 else 0.0)
            or 0.0
        ),
        "heals_party_pct": float(c_skill.get("heals_party_pct") or 0.0),
        "lifesteal_pct": float(
            c_skill.get("lifesteal_pct") or c_skill.get("lifesteal_vs_bleeding_pct") or 0.0
        ),
        "execute_threshold": float(c_skill.get("tier3_execute_threshold") or 0.0) if clamped_tier >= 3 else 0.0,
        "crit_bonus": float(c_skill.get("crit_bonus") or 0.0),
        "description": str(c_skill.get("description") or "Zero-MP Entity Contract invocation."),
    }
    if c_skill.get("status_ailment"):
        spell_def["status_ailment"] = str(c_skill["status_ailment"])
    if c_skill.get("secondary_ailment"):
        spell_def["secondary_ailment"] = str(c_skill["secondary_ailment"])
    if c_skill.get("self_status_ailment"):
        spell_def["self_status_ailment"] = str(c_skill["self_status_ailment"])
    if c_skill.get("dot_damage"):
        spell_def["dot_damage"] = int(c_skill["dot_damage"])
    return spell_def


def ensure_pact_spells_registered() -> int:
    """Idempotently populates `SPELL_REGISTRY` with all Bespoke, Folklore, and 36 Procedural Pact skills."""
    global _PACT_SPELLS_REGISTERED
    if _PACT_SPELLS_REGISTERED:
        return 0
    cat = load_entity_patrons_catalog()
    count = 0

    for entry in cat.get("bespoke_patrons") or []:
        for t in (1, 2, 3):
            sp = build_pact_spell_def(entry, tier=t)
            SPELL_REGISTRY[sp["id"]] = sp
            count += 1

    for _cid, prof in (cat.get("folklore_patrons") or {}).items():
        for t in (1, 2, 3):
            sp = build_pact_spell_def(prof, tier=t)
            SPELL_REGISTRY[sp["id"]] = sp
            count += 1

    for cid, entry in _load_folklore_entries_by_id().items():
        if cid in (cat.get("folklore_patrons") or {}):
            continue
        synth = synthesize_folklore_patron(entry)
        if synth:
            for t in (1, 2, 3):
                sp = build_pact_spell_def(synth, tier=t)
                SPELL_REGISTRY[sp["id"]] = sp
                count += 1

    for _tpl_key, tpl in (cat.get("procedural_skill_templates") or {}).items():
        dummy_patron = {
            "patron_id": f"proc_{_tpl_key}",
            "element": tpl["element"],
            "synergy_stat": tpl["synergy_stat"],
            "combat_skill": tpl["combat_skill"],
        }
        for t in (1, 2, 3):
            sp = build_pact_spell_def(dummy_patron, tier=t)
            SPELL_REGISTRY[sp["id"]] = sp
            count += 1

    _PACT_SPELLS_REGISTERED = True
    return count
