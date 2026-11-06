from __future__ import annotations
"""
Compositional 3-Axis Awakened Resonance Kit Registry for Anomalous Incursions.

Synthesizes all 9 Attributes x 4 Combat Archetypes x 4 Ability Mediums = 144 deterministic
5-skill kits ([2 Light + 2 Heavy + 1 Signature Ultimate] = 720 spell entries) directly
into in-memory SPELL_REGISTRY without bloating SQLite `procedural_spells`.
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from .registry import SPELL_REGISTRY, get_spell, register_spell

ANOMALOUS_ATTRIBUTES: Tuple[str, ...] = (
    "fire",
    "water",
    "wind",
    "earth",
    "ice",
    "electric",
    "bio",
    "physical",
    "aether",
)

COMBAT_ARCHETYPES: Tuple[str, ...] = (
    "vanguard",
    "catalyst",
    "breaker",
    "warden",
)

ABILITY_MEDIUMS: Tuple[str, ...] = (
    "direct_manifestation",
    "ordnance_imbuement",
    "somatic_overdrive",
    "autonomous_construct",
)

MEDIUM_STAT_SYNERGY: Dict[str, Tuple[str, ...]] = {
    "direct_manifestation": ("INT", "CHA"),
    "ordnance_imbuement": ("PER", "STR", "AGI"),
    "somatic_overdrive": ("STR", "AGI", "END"),
    "autonomous_construct": ("INT", "PER", "END"),
}

ATTRIBUTE_META: Dict[str, Dict[str, Any]] = {
    "fire": {
        "label": "Fire", "emoji": "🔥", "damage_type": "fire",
        "ailment": "Burned", "dot_damage": 12, "adj": "Thermokinetic", "noun": "Ignition",
    },
    "water": {
        "label": "Water", "emoji": "🌊", "damage_type": "water",
        "ailment": "Slowed", "dot_damage": 0, "adj": "Abyssal-Tide", "noun": "Riptide",
    },
    "wind": {
        "label": "Wind", "emoji": "🌪️", "damage_type": "wind",
        "ailment": "Exposed", "dot_damage": 0, "adj": "Vacuum-Shear", "noun": "Tempest",
    },
    "earth": {
        "label": "Earth", "emoji": "🪨", "damage_type": "earth",
        "ailment": "Grounded", "dot_damage": 0, "adj": "Tectonic", "noun": "Monolith",
    },
    "ice": {
        "label": "Ice", "emoji": "❄️", "damage_type": "ice",
        "ailment": "Frozen", "dot_damage": 0, "adj": "Zero-Kelvin", "noun": "Stasis",
    },
    "electric": {
        "label": "Electric", "emoji": "⚡", "damage_type": "shock",
        "ailment": "Shocked", "dot_damage": 10, "adj": "Fulminating", "noun": "Surge",
    },
    "bio": {
        "label": "Bio", "emoji": "☣️", "damage_type": "poison",
        "ailment": "Poisoned", "dot_damage": 12, "adj": "Bio-Aberrant", "noun": "Spore",
    },
    "physical": {
        "label": "Physical", "emoji": "🗡️", "damage_type": "physical",
        "ailment": "Bleeding", "dot_damage": 14, "adj": "Kinetic", "noun": "Impact",
    },
    "aether": {
        "label": "Aether", "emoji": "🌌", "damage_type": "aether",
        "ailment": "Disrupted", "dot_damage": 0, "adj": "Hume-Rift", "noun": "Singularity",
    },
}

ARCHETYPE_META: Dict[str, Dict[str, str]] = {
    "vanguard": {"label": "Vanguard", "role": "Breach Execution & Primary DPS"},
    "catalyst": {"label": "Catalyst", "role": "Mono-Attribute Harmony & Weakness Implant"},
    "breaker": {"label": "Breaker", "role": "1.6x Off-Weakness Poise Shred & Debuffs"},
    "warden": {"label": "Warden", "role": "Hume Barrier Shields, Triage & Cleanse"},
}

MEDIUM_META: Dict[str, Dict[str, str]] = {
    "direct_manifestation": {
        "label": "Direct Manifestation",
        "delivery": "ranged_spell",
        "verb": "Pulse",
        "heavy_verb": "Cataclysm",
        "ult_noun": "Convergence",
    },
    "ordnance_imbuement": {
        "label": "Ordnance Imbuement",
        "delivery": "weapon_imbue",
        "verb": "Round",
        "heavy_verb": "Barrage",
        "ult_noun": "Severance",
    },
    "somatic_overdrive": {
        "label": "Somatic Overdrive",
        "delivery": "melee_martial",
        "verb": "Palm",
        "heavy_verb": "Crusher",
        "ult_noun": "Asura Form",
    },
    "autonomous_construct": {
        "label": "Autonomous Construct",
        "delivery": "construct_command",
        "verb": "Order",
        "heavy_verb": "Protocol",
        "ult_noun": "Overlord",
    },
}

from mechanics.world.anomaly_engine import (
    _ELEMENT_ALIAS_MAP as _ATTRIBUTE_ALIASES,
    normalize_anomaly_element,
)


def normalize_anomalous_attribute(attr: Optional[str], fallback: str = "physical") -> str:
    return normalize_anomaly_element(attr, fallback=fallback)


def derive_default_3axis(
    char_class: str = "",
    faction_id: str = "",
    seed: Any = None,
) -> Tuple[str, str, str]:
    """Deterministically derives a balanced 3-axis tuple when legacy callers omit explicit choices."""
    raw = f"{faction_id}:{char_class}:{seed if seed is not None else ''}".lower()
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    cls_low = f"{char_class} {faction_id}".lower()

    if any(k in cls_low for k in ("monastic", "shrine", "exorcist", "miko")):
        attr_pool = ("aether", "wind", "water", "fire")
    elif any(k in cls_low for k in ("cult", "occult", "pact", "whisper")):
        attr_pool = ("aether", "bio", "fire", "ice")
    else:
        attr_pool = ANOMALOUS_ATTRIBUTES

    attr = attr_pool[digest[0] % len(attr_pool)]
    if any(k in cls_low for k in ("warden", "medic", "guard", "shield", "aegis")):
        arch = "warden"
    elif any(k in cls_low for k in ("breaker", "engineer", "heavy", "demolition")):
        arch = "breaker"
    elif any(k in cls_low for k in ("catalyst", "analyst", "forensic", "tactician", "support")):
        arch = "catalyst"
    elif any(k in cls_low for k in ("hunter", "marksman", "operator", "vanguard", "striker")):
        arch = "vanguard"
    else:
        arch = COMBAT_ARCHETYPES[digest[1] % len(COMBAT_ARCHETYPES)]

    if any(k in cls_low for k in ("marksman", "operator", "hunter", "gun", "blade")):
        med = "ordnance_imbuement"
    elif any(k in cls_low for k in ("monk", "brawler", "martial", "fist", "somatic")):
        med = "somatic_overdrive"
    elif any(k in cls_low for k in ("shikigami", "drone", "summon", "hound", "construct")):
        med = "autonomous_construct"
    elif any(k in cls_low for k in ("esper", "psychic", "ritual", "caster")):
        med = "direct_manifestation"
    else:
        med = ABILITY_MEDIUMS[digest[2] % len(ABILITY_MEDIUMS)]

    return attr, arch, med


def _scale_mp(base_mp: int, attr: str, slot_tier: str) -> int:
    if slot_tier == "ultimate":
        return 0
    if attr == "aether" and slot_tier == "heavy":
        return int(round(base_mp * 1.15))
    return base_mp


def _synthesize_kit_definitions(attr: str, arch: str, med: str) -> List[Dict[str, Any]]:
    am = ATTRIBUTE_META[attr]
    mm = MEDIUM_META[med]
    adj = am["adj"]
    noun = am["noun"]
    emoji = am["emoji"]
    dmg_type = am["damage_type"]
    prefix = f"awk_{attr}_{arch}_{med}"

    common = {
        "awakened_attribute": attr,
        "combat_archetype": arch,
        "ability_medium": med,
        "is_awakened_innate": True,
        "duplicate_empowered": False,
        "delivery_medium": mm["delivery"],
    }
    if med == "ordnance_imbuement":
        common["imbue_turns"] = 2
    elif med == "somatic_overdrive":
        common["somatic_buff_turns"] = 1
    elif med == "autonomous_construct":
        common["summon_decoy"] = True

    if arch == "vanguard":
        raw_slots = [
            {
                "id": f"{prefix}_l1", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{adj} Severing {mm['verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(7, attr, "light"),
                "power_mult": 1.35, "crit_bonus": 0.12, "stability_shred": 20,
                "status_ailment": am["ailment"], "dot_damage": am["dot_damage"],
                "description": f"Precision {am['label']} strike executing exposed weakpoints.",
            },
            {
                "id": f"{prefix}_l2", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{noun} Sweep {mm['verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": _scale_mp(9, attr, "light"),
                "power_mult": 1.00, "stability_shred": 20,
                "description": f"Wide-arc {am['label']} sweep hitting all hostile targets.",
            },
            {
                "id": f"{prefix}_h1", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"{adj} Breach {mm['heavy_verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(16, attr, "heavy"),
                "power_mult": 2.25, "breach_bonus_mult": 1.25, "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "status_ailment": am["ailment"], "dot_damage": am["dot_damage"] * 2,
                "description": f"High-impact {am['label']} finisher dealing +25% bonus damage to Breached targets.",
            },
            {
                "id": f"{prefix}_h2", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"Overdrive {noun} {mm['heavy_verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "chain", "mp_cost": _scale_mp(18, attr, "heavy"),
                "power_mult": 1.70, "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Multi-vector {am['label']} assault ricocheting across nearby anomalies.",
            },
            {
                "id": f"{prefix}_ult", "slot_tier": "ultimate", "tier": 1, "tier_name": "Ultimate",
                "name": f"Ultimate: {adj} {mm['ult_noun']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "is_ultimate": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": 0, "pip_cost": 3,
                "power_mult": 3.55, "crit_bonus": 0.20, "affixes": ["sundering"], "stability_shred": 50,
                "description": f"SIGNATURE ULTIMATE (3 Pips): Unleashes total {am['label']} resonance, piercing 35% defense.",
            },
        ]
    elif arch == "catalyst":
        implant_tag = f"Weakness Implant ({am['label']})"
        raw_slots = [
            {
                "id": f"{prefix}_l1", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{adj} Tracer {mm['verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(7, attr, "light"),
                "power_mult": 1.15, "stability_shred": 20,
                "weakness_implant_attr": attr, "status_ailment": implant_tag,
                "description": f"Offensive {am['label']} tagger that implants {am['label']} Weakness for 2 turns.",
            },
            {
                "id": f"{prefix}_l2", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{noun} Harmony Cadence", "emoji": emoji,
                "discipline": "support", "is_offensive": False, "damage_type": dmg_type,
                "target_type": "support", "mp_cost": _scale_mp(8, attr, "light"),
                "buff_pct": 0.25, "stat_target": "ATK", "mono_attribute_buff": attr,
                "break_efficiency_bonus": 0.25, "stability_shred": 20,
                "description": f"Amplifies {am['label']} innate skill damage and Break efficiency by +25%.",
            },
            {
                "id": f"{prefix}_h1", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"{adj} Resonance {mm['heavy_verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": _scale_mp(18, attr, "heavy"),
                "power_mult": 1.65, "stability_shred": 35,
                "weakness_implant_attr": attr, "status_ailment": implant_tag,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Detonates an {am['label']} field across all foes and implants {am['label']} Weakness.",
            },
            {
                "id": f"{prefix}_h2", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"Harmonic {noun} Array", "emoji": emoji,
                "discipline": "support", "is_offensive": False, "damage_type": dmg_type,
                "target_type": "support", "mp_cost": _scale_mp(16, attr, "heavy"),
                "buff_pct": 0.30, "stat_target": "ATK", "mono_attribute_buff": attr,
                "stability_shred": 35, "resummons_construct": med == "autonomous_construct",
                "description": f"Establishes high-gain {am['label']} resonance across aligned party operatives.",
            },
            {
                "id": f"{prefix}_ult", "slot_tier": "ultimate", "tier": 1, "tier_name": "Ultimate",
                "name": f"Ultimate: {noun} Harmonic {mm['ult_noun']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "is_ultimate": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": 0, "pip_cost": 3,
                "power_mult": 2.60, "party_buff_pct": 0.30, "weakness_implant_attr": attr, "stability_shred": 50,
                "description": f"SIGNATURE ULTIMATE (3 Pips): Sweeps all enemies with {am['label']} resonance, implants Weakness, and empowers allies.",
            },
        ]
    elif arch == "breaker":
        raw_slots = [
            {
                "id": f"{prefix}_l1", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{adj} Concussion {mm['verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(7, attr, "light"),
                "power_mult": 1.15, "off_weakness_shred_mult": 1.6, "stability_shred": 20,
                "description": f"Disruptive {am['label']} impact with 1.6x off-weakness Stability shred.",
            },
            {
                "id": f"{prefix}_l2", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{noun} Fracture Lock", "emoji": emoji,
                "discipline": "curse", "is_offensive": False, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(8, attr, "light"),
                "debuff_pct": 0.20, "stat_target": "DEF", "stability_shred": 20,
                "status_ailment": am["ailment"],
                "description": f"Weakens target defenses by 20% while eroding anomalous Stability.",
            },
            {
                "id": f"{prefix}_h1", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"{adj} Sunder {mm['heavy_verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(16, attr, "heavy"),
                "power_mult": 1.95, "off_weakness_shred_mult": 1.6, "affixes": ["sundering"], "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Crushing {am['label']} strike tearing through armor and anomalous poise.",
            },
            {
                "id": f"{prefix}_h2", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"Suppression {noun} Wave", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": _scale_mp(18, attr, "heavy"),
                "power_mult": 1.45, "debuff_pct": 0.15, "stat_target": "ATK", "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Shockwave of {am['label']} suppression shredding enemy Stability across the zone.",
            },
            {
                "id": f"{prefix}_ult", "slot_tier": "ultimate", "tier": 1, "tier_name": "Ultimate",
                "name": f"Ultimate: {adj} Collapse {mm['ult_noun']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "is_ultimate": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": 0, "pip_cost": 3,
                "power_mult": 2.85, "affixes": ["sundering"], "stability_shred": 50,
                "description": f"SIGNATURE ULTIMATE (3 Pips): Collapses hostile poise across all anomalies with massive {am['label']} force.",
            },
        ]
    else:  # warden
        raw_slots = [
            {
                "id": f"{prefix}_l1", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{adj} Aegis {mm['verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(7, attr, "light"),
                "power_mult": 1.15, "self_temp_hp_pct": 0.10, "stability_shred": 20,
                "description": f"Defensive {am['label']} strike generating a personal Hume barrier.",
            },
            {
                "id": f"{prefix}_l2", "slot_tier": "light", "tier": 3, "tier_name": "Light",
                "name": f"{noun} Hume Ward", "emoji": "🛡️",
                "discipline": "support", "is_offensive": False, "damage_type": dmg_type,
                "target_type": "support", "mp_cost": _scale_mp(8, attr, "light"),
                "heal_amount": 32, "temp_hp_shield": 28, "cleanses_debuff": True, "stability_shred": 20,
                "description": f"Restores vitality, projects a Hume shield, and cleanses one debuff.",
            },
            {
                "id": f"{prefix}_h1", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"{adj} Bastion {mm['heavy_verb']}", "emoji": emoji,
                "discipline": "attack", "is_offensive": True, "damage_type": dmg_type,
                "target_type": "single", "mp_cost": _scale_mp(16, attr, "heavy"),
                "power_mult": 1.90, "party_temp_hp_shield": 24, "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Heavy {am['label']} counter-assault reinforcing squad Hume barriers.",
            },
            {
                "id": f"{prefix}_h2", "slot_tier": "heavy", "tier": 2, "tier_name": "Heavy",
                "name": f"Sanctuary {noun} Dome", "emoji": "🛡️",
                "discipline": "support", "is_offensive": False, "damage_type": dmg_type,
                "target_type": "support", "mp_cost": _scale_mp(18, attr, "heavy"),
                "heal_amount": 55, "temp_hp_shield": 45, "cleanses_debuff": True, "stability_shred": 35,
                "resummons_construct": med == "autonomous_construct",
                "description": f"Erects a reinforced {am['label']} containment barrier and restores squad HP.",
            },
            {
                "id": f"{prefix}_ult", "slot_tier": "ultimate", "tier": 1, "tier_name": "Ultimate",
                "name": f"Ultimate: {adj} Citadel {mm['ult_noun']}", "emoji": "🛡️",
                "discipline": "attack", "is_offensive": True, "is_ultimate": True, "damage_type": dmg_type,
                "target_type": "aoe", "mp_cost": 0, "pip_cost": 3,
                "power_mult": 2.40, "party_heal_amount": 65, "party_temp_hp_shield": 60,
                "cleanses_debuff": True, "stability_shred": 50,
                "description": f"SIGNATURE ULTIMATE (3 Pips): Purges anomalies with {am['label']} shockwaves while fortifying the entire squad.",
            },
        ]

    finalized: List[Dict[str, Any]] = []
    for sp in raw_slots:
        merged = {**common, **sp}
        merged["tags"] = {
            "discipline": merged["discipline"],
            "school": "Evocation" if merged["is_offensive"] else "Abjuration",
            "element": attr,
            "target_type": merged["target_type"],
            "tier": merged["tier"],
            "delivery": mm["delivery"],
            "status_infliction": [merged["status_ailment"]] if merged.get("status_ailment") else [],
        }
        finalized.append(merged)
    return finalized


_KIT_INDEX: Dict[Tuple[str, str, str], List[str]] = {}


def ensure_awakened_kits_registered() -> None:
    if len(_KIT_INDEX) == 144:
        return
    for attr in ANOMALOUS_ATTRIBUTES:
        for arch in COMBAT_ARCHETYPES:
            for med in ABILITY_MEDIUMS:
                defs = _synthesize_kit_definitions(attr, arch, med)
                ids: List[str] = []
                for d in defs:
                    register_spell(d)
                    ids.append(d["id"])
                _KIT_INDEX[(attr, arch, med)] = ids


def build_awakened_kit_ids(attribute: str, archetype: str, medium: str) -> List[str]:
    """Returns deterministic 5 innate spell IDs [L1, L2, H1, H2, ULT] for any 3-axis combination."""
    ensure_awakened_kits_registered()
    attr = normalize_anomalous_attribute(attribute, fallback="physical")
    arch = str(archetype or "").strip().lower()
    if arch not in COMBAT_ARCHETYPES:
        arch = "vanguard"
    med = str(medium or "").strip().lower()
    if med not in ABILITY_MEDIUMS:
        med = "direct_manifestation"
    return list(_KIT_INDEX[(attr, arch, med)])


def get_awakened_basic_strike(
    attribute: str,
    medium: str,
    equipped_weapon: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Universal 0-MP Basic Strike (12 Stability shred, +1 Ult Pip) preventing 0-MP soft-locks.
    For `ordnance_imbuement`, uses the equipped weapon's native element or manifests an
    ethereal fallback weapon of the agent's locked attribute if unarmed.
    """
    locked_attr = normalize_anomalous_attribute(attribute, fallback="physical")
    med = str(medium or "").strip().lower()
    if med not in ABILITY_MEDIUMS:
        med = "direct_manifestation"

    attack_attr = locked_attr
    is_ethereal_fallback = False

    if med == "ordnance_imbuement":
        if equipped_weapon and isinstance(equipped_weapon, dict):
            meta = equipped_weapon.get("metadata") if isinstance(equipped_weapon.get("metadata"), dict) else equipped_weapon
            if meta.get("is_anomalous") and (meta.get("element") or meta.get("elem_convert_type")):
                attack_attr = normalize_anomalous_attribute(
                    meta.get("element") or meta.get("elem_convert_type"), fallback="physical"
                )
            else:
                attack_attr = "physical"
        else:
            attack_attr = locked_attr
            is_ethereal_fallback = True

    am = ATTRIBUTE_META[attack_attr]
    label_map = {
        "direct_manifestation": f"{am['label']} Bolt",
        "ordnance_imbuement": (
            f"Ethereal {am['label']} Sidearm" if is_ethereal_fallback else f"Ordnance Strike ({am['label']})"
        ),
        "somatic_overdrive": f"{am['label']} Combo Strike",
        "autonomous_construct": f"Construct {am['label']} Ping",
    }
    return {
        "id": f"awk_basic_{locked_attr}_{med}",
        "name": label_map[med],
        "emoji": am["emoji"],
        "discipline": "attack",
        "is_basic_strike": True,
        "is_offensive": True,
        "awakened_attribute": locked_attr,
        "attack_attribute": attack_attr,
        "ability_medium": med,
        "damage_type": am["damage_type"],
        "target_type": "single",
        "mp_cost": 0,
        "pip_gain": 1,
        "power_mult": 0.95,
        "stability_shred": 12,
        "is_ethereal_weapon_fallback": is_ethereal_fallback,
    }


def get_actor_spell(spell_id: str, skill_progress: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """
    Returns a per-actor shallow copy of `spell_id` with `duplicate_empowered` resolved
    from `skill_progress['empowered_granted_spells']` without mutating shared SPELL_REGISTRY.
    """
    sp = SPELL_REGISTRY.get(spell_id) or get_spell(spell_id)
    if not isinstance(sp, dict):
        return None
    empowered_set = set((skill_progress or {}).get("empowered_granted_spells") or [])
    out = dict(sp)
    out["duplicate_empowered"] = spell_id in empowered_set
    return out


ensure_awakened_kits_registered()
