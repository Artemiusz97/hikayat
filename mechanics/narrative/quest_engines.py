from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CANONICAL_QUEST_ENGINES: Tuple[str, ...] = (
    "MYSTERY_CASE",
    "HEIST_BREACH",
    "HUNT_CONTAINMENT",
    "ACQUISITION_EXCHANGE",
    "SOCIAL_BROKERAGE",
    "CRISIS_DEFENSE",
    "RIVALRY_SHOWDOWN",
    "INTIMATE_LIAISON",
)

SUPPORTED_LOCALES: Tuple[str, ...] = ("en", "pl", "ms", "zh", "de")
OPTIONAL_OBJECTIVE_ROLES: Tuple[str, ...] = ("aid", "bypass", "alternative", "threatened")

ENGINE_TO_LEGACY_BLUEPRINT: Dict[str, str] = {
    "MYSTERY_CASE": "INVESTIGATION",
    "HEIST_BREACH": "HEIST_INFILTRATION",
    "HUNT_CONTAINMENT": "NEUTRALIZATION",
    "ACQUISITION_EXCHANGE": "ACQUISITION",
    "SOCIAL_BROKERAGE": "SOCIAL_MANIPULATION",
    "CRISIS_DEFENSE": "SITE_DEFENSE_RITUAL",
    "RIVALRY_SHOWDOWN": "CONTEST_RIVALRY",
    "INTIMATE_LIAISON": "INTIMATE_ENCOUNTER",
}

LEGACY_BLUEPRINT_TO_ENGINE: Dict[str, str] = {
    "INVESTIGATION": "MYSTERY_CASE",
    "EXPLORATION_HAZARD": "MYSTERY_CASE",
    "HEIST_INFILTRATION": "HEIST_BREACH",
    "NEUTRALIZATION": "HUNT_CONTAINMENT",
    "ACQUISITION": "ACQUISITION_EXCHANGE",
    "SOCIAL_MANIPULATION": "SOCIAL_BROKERAGE",
    "SITE_DEFENSE_RITUAL": "CRISIS_DEFENSE",
    "ESCORT_RESCUE": "CRISIS_DEFENSE",
    "CONTEST_RIVALRY": "RIVALRY_SHOWDOWN",
    "INTIMATE_ENCOUNTER": "INTIMATE_LIAISON",
}

_CATALOG_CACHE: Optional[Dict[str, Any]] = None
_STORYLETS_CACHE: Optional[Dict[str, Any]] = None


def normalize_quest_locale(lang: Optional[str]) -> str:
    raw = str(lang or "en").strip().lower()
    if raw.startswith("zh"):
        return "zh"
    base = raw.split("-")[0].split("_")[0]
    return base if base in SUPPORTED_LOCALES else "en"


def load_quest_engines_catalog() -> Dict[str, Any]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    catalog_path = Path(__file__).resolve().parents[2] / "data" / "quest_engines_catalog.json"
    with catalog_path.open("r", encoding="utf-8") as fh:
        _CATALOG_CACHE = json.load(fh)
    return _CATALOG_CACHE


def load_campaign_storylets_catalog() -> Dict[str, Any]:
    global _STORYLETS_CACHE
    if _STORYLETS_CACHE is not None:
        return _STORYLETS_CACHE
    catalog_path = Path(__file__).resolve().parents[2] / "data" / "campaign_storylets_catalog.json"
    with catalog_path.open("r", encoding="utf-8") as fh:
        _STORYLETS_CACHE = json.load(fh)
    return _STORYLETS_CACHE


def get_scenario_bible_bucket(scenario_key: Optional[str]) -> str:
    scen = str(scenario_key or "fantasy").strip().lower()
    if "anomalous" in scen:
        return "anomalous_occult"
    if "high_school" in scen or "slice_of_life" in scen:
        return "school_slice_of_life"
    if any(tok in scen for tok in ("sci_fi", "scifi", "cyberpunk", "post_apoc", "nuclear")):
        return "scifi_frontier"
    return "fantasy_mythic"


def _deterministic_ratio(seed_key: str) -> float:
    digest = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 10000) / 10000.0


def resolve_quest_engine(
    tag_or_archetype: str,
    objective: str = "",
    is_nsfw_scenario: bool = False,
) -> Dict[str, Any]:
    """
    Maps any of the 55+ genre/NSFW quest tags or blueprints into one of the 8 canonical
    Quest Engines, preserving hybrid NSFW routing flags (`uses_nsfw_routing = True`).
    """
    catalog = load_quest_engines_catalog()
    tag_map: Dict[str, str] = catalog.get("tag_to_engine") or {}
    hybrid_nsfw: List[str] = [str(k).lower() for k in (catalog.get("hybrid_nsfw_keywords") or [])]

    raw_tag = str(tag_or_archetype or "").strip()
    tag_upper = raw_tag.upper().replace(" ", "_")
    tag_low = raw_tag.lower()
    obj_low = str(objective or "").lower()
    combined_low = f"{tag_low} {obj_low}".strip()

    chosen_engine = ""
    if tag_upper in CANONICAL_QUEST_ENGINES:
        chosen_engine = tag_upper
    elif tag_upper in LEGACY_BLUEPRINT_TO_ENGINE:
        chosen_engine = LEGACY_BLUEPRINT_TO_ENGINE[tag_upper]
    else:
        # Longest keyword match first so compound tags like 'aphrodisiac run' or 'captive rescue' win over short roots
        for kw in sorted(tag_map.keys(), key=len, reverse=True):
            if kw in tag_low:
                chosen_engine = tag_map[kw]
                break

    if not chosen_engine:
        # Verb fallback from objective text
        if any(w in obj_low for w in ("seduc", "intimate", "tryst", "paramour", "passion", "rendezvous")):
            chosen_engine = "INTIMATE_LIAISON"
        elif any(w in obj_low for w in ("deliver", "gather", "collect", "fetch", "retrieve", "harvest", "craft", "brew")):
            chosen_engine = "ACQUISITION_EXCHANGE"
        elif any(w in obj_low for w in ("assassinate", "slay", "hunt", "eliminate", "exterminate", "execute")):
            chosen_engine = "HUNT_CONTAINMENT"
        elif any(w in obj_low for w in ("infiltrate", "breach", "steal", "hack", "heist", "sabotage", "slip into")):
            chosen_engine = "HEIST_BREACH"
        elif any(w in obj_low for w in ("defend", "protect", "escort", "rescue", "ritual", "seal", "evacuate", "fortify")):
            chosen_engine = "CRISIS_DEFENSE"
        elif any(w in obj_low for w in ("duel", "showdown", "tournament", "challenge", "arena")):
            chosen_engine = "RIVALRY_SHOWDOWN"
        elif any(w in obj_low for w in ("persuade", "negotiate", "broker", "diplomacy", "gossip", "campaign", "election", "matchmak")):
            chosen_engine = "SOCIAL_BROKERAGE"
        else:
            chosen_engine = "MYSTERY_CASE"

    engine_meta = (catalog.get("engines") or {}).get(chosen_engine) or {}
    legacy_bp = str(engine_meta.get("legacy_blueprint") or ENGINE_TO_LEGACY_BLUEPRINT.get(chosen_engine, "INVESTIGATION"))
    if chosen_engine == "CRISIS_DEFENSE" and any(w in combined_low for w in ("rescue", "escort", "captive", "missing", "spirited")):
        legacy_bp = "ESCORT_RESCUE"
    elif chosen_engine == "MYSTERY_CASE" and any(w in combined_low for w in ("archaeology", "dungeon", "derelict", "toxic", "mapping", "triangulation", "dare")):
        legacy_bp = "EXPLORATION_HAZARD"

    is_hybrid_nsfw = any(h_kw in combined_low for h_kw in hybrid_nsfw)
    uses_nsfw_routing = bool(
        chosen_engine == "INTIMATE_LIAISON"
        or is_hybrid_nsfw
        or is_nsfw_scenario
        or bool(engine_meta.get("uses_nsfw_routing"))
    )

    is_elim_strict = bool(
        engine_meta.get("is_elimination_strict")
        or any(w in combined_low for w in ("assassination", "eliminate", "extermination", "slay", "termination"))
    )

    climax_gate_mode = str(engine_meta.get("climax_gate_mode") or "open")
    if any(w in combined_low for w in ("unknown culprit", "hidden lair", "secret mastermind", "uncover who", "mole", "murder")):
        climax_gate_mode = "secret"

    return {
        "engine": chosen_engine,
        "legacy_blueprint": legacy_bp,
        "uses_nsfw_routing": uses_nsfw_routing,
        "is_hybrid_nsfw": is_hybrid_nsfw,
        "is_elimination_strict": is_elim_strict,
        "climax_gate_mode": climax_gate_mode,
        "turn_in_default": str(engine_meta.get("turn_in_default") or "in_field"),
    }


def get_localized_engine_label(engine: str, lang: str = "en") -> str:
    catalog = load_quest_engines_catalog()
    loc = normalize_quest_locale(lang)
    labels = ((catalog.get("engines") or {}).get(engine) or {}).get("labels") or {}
    return str(labels.get(loc) or labels.get("en") or engine.replace("_", " ").title())


def render_offline_pitch_stub(
    engine: str,
    slots: Dict[str, Any],
    lang: str = "en",
) -> Tuple[str, str]:
    catalog = load_quest_engines_catalog()
    loc = normalize_quest_locale(lang)
    eng_cfg = (catalog.get("engines") or {}).get(engine) or {}
    pt = (eng_cfg.get("pitch_templates") or {}).get(loc) or (eng_cfg.get("pitch_templates") or {}).get("en") or {}
    safe_slots = {
        "client": str(slots.get("client") or "Local Patron"),
        "target": str(slots.get("target") or "the target"),
        "informant": str(slots.get("informant") or "a local contact"),
        "venue": str(slots.get("venue") or "the district"),
        "zone": str(slots.get("zone") or "Central Ward"),
    }
    title = str(pt.get("title") or "Contract at {venue}").format(**safe_slots)
    pitch = str(pt.get("pitch") or "{client} posted an urgent contract at {venue}.").format(**safe_slots)
    return title, pitch


def build_engine_lead_approaches(
    stats_list: List[str],
    danger_tier: int = 1,
    allow_curfew_stealth: bool = True,
) -> List[Dict[str, Any]]:
    base_dc = max(4, min(16, 5 + int(danger_tier or 1) * 2))
    approaches: List[Dict[str, Any]] = []
    for st in stats_list:
        code = str(st or "PER").upper()
        if code == "BRIBE":
            approaches.append(
                {
                    "approach_id": "bribe",
                    "stat": "CHA",
                    "requirement": max(3, base_dc - 2),
                    "gold_cost": 15 * max(1, int(danger_tier or 1)),
                    "label": "Grease palms with discreet coin",
                }
            )
        elif code == "ITEM":
            approaches.append(
                {
                    "approach_id": "item_utility",
                    "stat": "ITEM",
                    "requirement": 0,
                    "label": "Leverage specialized gear or consumable",
                }
            )
        else:
            approaches.append(
                {
                    "approach_id": f"stat_{code.lower()}",
                    "stat": code,
                    "requirement": base_dc,
                    "label": f"Apply {code} approach",
                }
            )
    if allow_curfew_stealth and not any(a["stat"] == "AGI" for a in approaches):
        approaches.append(
            {
                "approach_id": "after_hours_stealth",
                "stat": "AGI",
                "requirement": base_dc,
                "after_hours_pivot": True,
                "label": "Slip in after hours under cover of curfew",
            }
        )
    return approaches


def roll_dossier_twist_spec(
    seed_key: str,
    engine: str,
    slots: Dict[str, Any],
    lang: str = "en",
    twist_probability: float = 0.70,
) -> Dict[str, Any]:
    """
    Deterministically rolls ~70% Twist / ~30% Plays Straight for Bounties & Quests.
    Supports early discovery, side-switching (`twist_resolution`), and `2x` hush-money blackmail.
    """
    if engine == "INTIMATE_LIAISON":
        # Intimate liaisons focus on chemistry/discretion rather than double-cross assassination twists
        twist_probability = min(twist_probability, 0.35)

    roll = _deterministic_ratio(f"twist:{seed_key}:{engine}")
    has_twist = roll < twist_probability
    if not has_twist:
        return {
            "has_twist": False,
            "twist_type": "plays_straight",
            "is_discovered": False,
            "side_switch_available": False,
            "blackmail_available": False,
            "blackmail_multiplier": 1.0,
            "summary": "",
        }

    catalog = load_quest_engines_catalog()
    twists_cfg: Dict[str, Any] = catalog.get("twists") or {}
    twist_keys = list(twists_cfg.keys()) or ["client_culprit"]
    idx = int(_deterministic_ratio(f"twist_kind:{seed_key}") * len(twist_keys)) % len(twist_keys)
    t_kind = twist_keys[idx]

    loc = normalize_quest_locale(lang)
    tmpl = (twists_cfg.get(t_kind) or {}).get(loc) or (twists_cfg.get(t_kind) or {}).get("en") or ""
    safe_slots = {
        "client": str(slots.get("client") or "the client"),
        "target": str(slots.get("target") or "the target"),
        "informant": str(slots.get("informant") or "the informant"),
        "accomplice": str(slots.get("accomplice") or "a hidden broker"),
    }
    summary = str(tmpl).format(**safe_slots) if tmpl else ""

    return {
        "has_twist": True,
        "twist_type": t_kind,
        "is_discovered": False,
        "side_switch_available": t_kind in ("client_culprit", "framed_target", "double_agent"),
        "blackmail_available": t_kind in ("client_culprit", "cursed_payload", "double_agent"),
        "blackmail_multiplier": 2.0,
        "hush_money_claimed": False,
        "sided_with_twist": False,
        "summary": summary,
    }


def build_turn_in_rules(
    engine: str,
    has_physical_macguffin: bool = False,
    requires_prisoner_handoff: bool = False,
    twist_spec: Optional[Dict[str, Any]] = None,
    advance_haggled: bool = False,
) -> Dict[str, Any]:
    """
    Context-Smart Turn-In (Decision 17):
    Requires `direct_client` return ONLY when physical item delivery, live prisoner handoff,
    fee haggle/blackmail, or a Client Twist confrontation applies; otherwise resolves `in_field`.
    """
    t_spec = twist_spec or {}
    client_twist = bool(t_spec.get("has_twist") and t_spec.get("twist_type") == "client_culprit")
    needs_direct = bool(
        has_physical_macguffin
        or requires_prisoner_handoff
        or advance_haggled
        or client_twist
        or engine == "ACQUISITION_EXCHANGE"
    )
    return {
        "mode": "direct_client" if needs_direct else "in_field",
        "requires_item_delivery": bool(has_physical_macguffin),
        "requires_prisoner_handoff": bool(requires_prisoner_handoff),
        "allows_blackmail_hush_money": bool(t_spec.get("blackmail_available")),
        "allows_macguffin_keep_or_fence": bool(has_physical_macguffin),
    }


def render_world_scar_spec(
    engine: str,
    venue_name: str,
    lang: str = "en",
) -> Dict[str, Any]:
    catalog = load_quest_engines_catalog()
    scars = catalog.get("world_scars") or {}
    if engine in ("INTIMATE_LIAISON", "SOCIAL_BROKERAGE"):
        scar_key = "gossip_scandal"
    elif engine in ("HEIST_BREACH", "MYSTERY_CASE", "ACQUISITION_EXCHANGE"):
        scar_key = "security_crackdown"
    else:
        scar_key = "unchecked_threat"

    cfg = scars.get(scar_key) or {}
    loc = normalize_quest_locale(lang)
    loc_block = cfg.get(loc) or cfg.get("en") or {}
    safe_venue = str(venue_name or "the district")
    return {
        "scar_type": scar_key,
        "title": str(loc_block.get("title") or "Regional Fallout").format(venue=safe_venue),
        "description": str(loc_block.get("description") or f"Unresolved fallout lingers around {safe_venue}.").format(venue=safe_venue),
        "remediation_title": str(loc_block.get("remediation_title") or f"Stabilize {safe_venue}").format(venue=safe_venue),
        "modifiers": dict(cfg.get("modifiers") or {"dc_modifiers": {"CHA": 1}}),
    }


def render_optional_objective_template(
    role: str,
    slots: Dict[str, Any],
    lang: str = "en",
    seed_idx: int = 0,
    **kwargs: Any,
) -> Dict[str, str]:
    storylets = load_campaign_storylets_catalog()
    loc = normalize_quest_locale(lang)
    norm_role = str(role or "aid").strip().lower()
    if norm_role not in OPTIONAL_OBJECTIVE_ROLES:
        norm_role = "aid"
    opt_cfg = (storylets.get("optional_templates") or {}).get(norm_role) or {}
    badge_map = opt_cfg.get("badge") or {}
    label_map = opt_cfg.get("labels") or {}
    hint_map = opt_cfg.get("stakes_hint") or {}

    safe_slots = {
        "client": str(slots.get("client") or "Local Patron"),
        "target": str(slots.get("target") or "the target"),
        "informant": str(slots.get("informant") or slots.get("ally") or "a local contact"),
        "accomplice": str(slots.get("accomplice") or slots.get("faction") or "a rival envoy"),
        "venue": str(slots.get("venue") or "the district"),
        "zone": str(slots.get("zone") or "Central Ward"),
    }
    raw_badge = str(badge_map.get(loc) or badge_map.get("en") or f"Optional — {norm_role.title()}")
    lbl_val = label_map.get(loc) or label_map.get("en") or "Pursue tactical optional lead near {venue}"
    if isinstance(lbl_val, list) and lbl_val:
        raw_label = str(lbl_val[int(seed_idx or 0) % len(lbl_val)])
    else:
        raw_label = str(lbl_val)
    raw_hint = str(hint_map.get(loc) or hint_map.get("en") or "Provides an optional tactical angle on the Main Objective.")
    return {
        "role": norm_role,
        "badge": raw_badge,
        "label": raw_label.format(**safe_slots),
        "stakes_hint": raw_hint.format(**safe_slots),
    }


def render_liberation_op_spec(
    venue_name: str,
    lang: str = "en",
    is_peak_resistance: bool = False,
) -> Dict[str, str]:
    catalog = load_quest_engines_catalog()
    loc = normalize_quest_locale(lang)
    lib_cfg = (catalog.get("liberation_ops") or {}).get("peak_resistance" if is_peak_resistance else "buildup") or {}
    loc_block = lib_cfg.get(loc) or lib_cfg.get("en") or {}
    safe_venue = str(venue_name or "the occupied ward")
    return {
        "title": str(loc_block.get("title") or f"Liberation Op: Reclaim {safe_venue}").format(venue=safe_venue),
        "objective": str(
            loc_block.get("objective")
            or f"Break entrenched enemy checkpoints and liberate {safe_venue} from occupation fallout."
        ).format(venue=safe_venue),
    }
