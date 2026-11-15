"""mechanics/combat/loadouts.py

Unified combatant stat sheet generator, companion vitals calculator, and
genre/role-gated 3-slot archetype loadout builder shared across enemies,
summons, and recruited party companions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .spells import get_spell
from .types import CombatAction

ALL_STATS: List[str] = ["STR", "PER", "END", "CHA", "INT", "AGI", "LUK"]

ROLE_TIER_MULTIPLIERS: Dict[str, float] = {
    "minion": 0.75,
    "standard": 1.00,
    "companion": 1.05,
    "elite": 1.30,
    "miniboss": 1.45,
    "boss": 1.60,
}

TIER_RANK_TO_ROLE: Dict[int, str] = {
    1: "minion",
    2: "standard",
    3: "elite",
    4: "miniboss",
    5: "boss",
}

MUNDANE_COMBAT_SCENARIOS = frozenset({
    "high_school_drama",
    "highschool",
    "slice_of_life",
    "nuclear_post_apocalypse",
    "postapoc",
})

ARCHETYPE_RULES: Dict[str, Dict[str, List[str]]] = {
    "Brute": {"primary": ["STR", "END"], "forbidden": ["INT"]},
    "Skirmisher": {"primary": ["AGI", "LUK"], "forbidden": ["INT", "CHA"]},
    "Caster": {"primary": ["INT", "PER"], "forbidden": ["STR"]},
    "Stalker": {"primary": ["PER", "AGI"], "forbidden": ["CHA"]},
    "Guardian": {"primary": ["END", "STR"], "forbidden": ["AGI"]},
    "Void Swarm": {"primary": ["AGI", "LUK"], "forbidden": ["CHA", "INT"]},
    "Security Drone": {"primary": ["PER", "AGI"], "forbidden": ["CHA"]},
    "Heavy Mech": {"primary": ["END", "STR"], "forbidden": ["LUK"]},
    "Psionic Alien": {"primary": ["INT", "PER"], "forbidden": ["STR"]},
    "Chrome Cyberhound": {"primary": ["AGI", "PER"], "forbidden": ["CHA", "INT"]},
    "Heavy Borg": {"primary": ["END", "STR"], "forbidden": ["LUK"]},
    "Netrunner Spec-Op": {"primary": ["INT", "PER"], "forbidden": ["STR"]},
    "Corporate Operative": {"primary": ["PER", "LUK"], "forbidden": ["END"]},
    "Campus Bully": {"primary": ["STR", "END"], "forbidden": ["INT"]},
    "Rival Debater": {"primary": ["CHA", "INT"], "forbidden": ["STR"]},
    "Hall Monitor": {"primary": ["PER", "END"], "forbidden": ["LUK"]},
    "Gossip Monger": {"primary": ["CHA", "LUK"], "forbidden": ["STR"]},
    "Rad-Mutant": {"primary": ["STR", "END"], "forbidden": ["CHA"]},
    "Scrap-Scavenger": {"primary": ["PER", "LUK"], "forbidden": ["INT"]},
    "Toxic Abomination": {"primary": ["END", "INT"], "forbidden": ["CHA"]},
    "Feral Beast": {"primary": ["AGI", "PER"], "forbidden": ["CHA", "INT"]},
    "Cognitohazard Caster": {"primary": ["INT", "PER"], "forbidden": ["STR"]},
    "Spatial Stalker": {"primary": ["AGI", "PER"], "forbidden": ["CHA"]},
    "Bio-Horror Brute": {"primary": ["STR", "END"], "forbidden": ["CHA"]},
    "Cursed Construct": {"primary": ["END", "STR"], "forbidden": ["AGI"]},
}


def is_mundane_combat_scenario(scenario_key: str) -> bool:
    """Returns True for mundane/post-apocalyptic scenarios with no supernatural magic."""
    norm = str(scenario_key or "").strip().lower().replace("-", "_").replace(" ", "_")
    if norm in MUNDANE_COMBAT_SCENARIOS:
        return True
    return any(tok in norm for tok in ("highschool", "high_school", "slice_of_life", "postapoc", "post_apocalypse"))


def build_combatant_stat_sheet(
    level: int,
    archetype_name: Optional[str] = None,
    role_tier: str = "standard",
    custom_primary: Optional[List[str]] = None,
    custom_forbidden: Optional[List[str]] = None,
    exact_extra_points: Optional[int] = None,
) -> Dict[str, int]:
    """
    Unified stat generator for enemies, summons, and party companions.
    Uses floor 3 for companions (preserving >=21 Level 1 contract) and floor 2
    for all enemy tiers, distributing budget 55% primary / 30% secondary (END-first)
    / 15% remaining allowed stats.
    """
    rule = ARCHETYPE_RULES.get(archetype_name or "", {"primary": ["STR", "AGI"], "forbidden": []})
    primary = custom_primary if custom_primary else rule.get("primary", ["STR", "AGI"])
    forbidden = custom_forbidden if custom_forbidden else rule.get("forbidden", [])

    primary_upper = [str(s).upper() for s in primary]
    forbidden_upper = [str(s).upper() for s in forbidden]

    allowed = [s for s in ALL_STATS if s not in forbidden_upper] or list(ALL_STATS)

    tier_norm = str(role_tier or "standard").strip().lower()
    tier_mult = ROLE_TIER_MULTIPLIERS.get(tier_norm, 1.00)
    stat_floor = 3 if tier_norm == "companion" else 2
    stats: Dict[str, int] = {s: stat_floor for s in ALL_STATS}

    lvl = max(1, int(level or 1))
    if exact_extra_points is not None:
        budget = max(0, int(exact_extra_points))
    else:
        budget = max(1, int(round((4 + (lvl - 1) * 2.5) * tier_mult)))

    if budget <= 0:
        return stats

    primary_pool = [s for s in primary_upper if s in allowed] or list(allowed)
    non_primary = [s for s in allowed if s not in primary_pool]
    secondary_pool: List[str] = []
    if "END" in non_primary:
        secondary_pool.append("END")
    for s in ("AGI", "PER", "INT", "STR", "LUK", "CHA"):
        if s in non_primary and s not in secondary_pool:
            secondary_pool.append(s)
    if not secondary_pool:
        secondary_pool = list(allowed)

    remaining_pool = [s for s in non_primary if s not in secondary_pool] or non_primary or list(allowed)

    p_pts = int(round(budget * 0.55))
    s_pts = int(round(budget * 0.30))
    if p_pts + s_pts > budget:
        s_pts = max(0, budget - p_pts)
    r_pts = max(0, budget - p_pts - s_pts)

    for idx in range(p_pts):
        stats[primary_pool[idx % len(primary_pool)]] += 1
    for idx in range(s_pts):
        stats[secondary_pool[idx % len(secondary_pool)]] += 1
    for idx in range(r_pts):
        stats[remaining_pool[idx % len(remaining_pool)]] += 1

    return stats


def compute_companion_vitals(
    level: int,
    stats: Optional[Dict[str, Any]],
    is_civilian: bool = False,
) -> Tuple[int, int]:
    """Computes unified survivable (max_hp, max_mp) for allied party companions."""
    lvl = max(1, int(level or 1))
    st = stats if isinstance(stats, dict) else {}
    end_val = int(st.get("END", st.get("end", 3)) or 3)
    int_val = int(st.get("INT", st.get("int", 3)) or 3)
    max_hp = 40 + lvl * 8 + end_val * 4
    max_mp = 0 if is_civilian else (15 + lvl * 4 + int_val * 2)
    return int(max_hp), int(max_mp)


def _normalize_loadout_role(archetype: str, role: str = "") -> str:
    combined = f"{archetype} {role}".strip().lower()
    if any(k in combined for k in ("medic", "cleric", "healer", "support", "warden")):
        return "healer"
    if any(k in combined for k in ("guardian", "vanguard", "tank", "mech", "borg", "construct", "monitor")):
        return "guardian"
    if any(k in combined for k in ("brute", "mutant", "bully", "breaker")):
        return "brute"
    if any(k in combined for k in ("stalker", "assassin", "skirmisher", "beast", "hound", "swarm", "scavenger")):
        return "stalker"
    return "caster"


def _select_magic_slot3_skill(role: str, level: int, scenario_key: str) -> CombatAction:
    scen_low = str(scenario_key or "fantasy").strip().lower()
    is_anomalous = any(tok in scen_low for tok in ("anomal", "urban_anomal"))
    is_scifi = any(tok in scen_low for tok in ("cyber", "sci_fi", "scifi", "space"))

    if role == "healer":
        candidate_ids = ["cellular_resuscitate_t3_st", "mend_t3_st"] if is_anomalous else ["mend_t3_st"]
        fallback = {"id": "mend_t3_st", "name": "Mend", "discipline": "support", "damage_type": "holy", "heal_amount": 25}
    elif role == "guardian":
        candidate_ids = ["reality_anchor_ward_t3_st", "aegis_ward_t3_st"] if is_anomalous else ["aegis_ward_t3_st"]
        fallback = {
            "id": "aegis_ward_t3_st", "name": "Aegis Ward", "discipline": "support",
            "damage_type": "magical", "status_ailment": "Fortified",
        }
    elif role == "brute":
        candidate_ids = ["conjure_greatsword_t2_st", "war_cry_t3_st"] if level >= 3 else ["war_cry_t3_st"]
        fallback = {
            "id": "war_cry_t3_st", "name": "War Cry", "discipline": "support",
            "damage_type": "physical", "status_ailment": "Empowered",
        }
    elif role == "stalker":
        candidate_ids = ["corrode_armor_t3_st", "weaken_t3_st"]
        fallback = {
            "id": "corrode_armor_t3_st", "name": "Corrode Armor", "discipline": "curse",
            "damage_type": "poison", "status_ailment": "Exposed",
        }
    else:
        if is_anomalous:
            candidate_ids = ["spatial_vector_dart_t3_st", "arcane_dart_t3_st"]
        elif is_scifi:
            candidate_ids = ["resonance_cascade_t2_aoe", "arcane_dart_t3_st"]
        else:
            candidate_ids = ["firebolt_t3_st", "arcane_dart_t3_st"]
        fallback = {
            "id": "arcane_dart_t3_st", "name": "Arcane Dart", "discipline": "attack",
            "damage_type": "magical", "power_mult": 1.2,
        }

    sp: Optional[Dict[str, Any]] = None
    for cid in candidate_ids:
        sp = get_spell(cid)
        if sp:
            break
    if not sp:
        sp = dict(fallback)

    is_support = sp.get("discipline") == "support" or int(sp.get("heal_amount", 0) or 0) > 0
    is_aoe = sp.get("target_type") == "aoe"
    target_type = "ally" if is_support else ("all_enemies" if is_aoe else "single_enemy")
    mana_cost = max(6, 6 + max(0, level - 1) * 2)
    dmg_mult = float(sp.get("power_mult") or (0.0 if int(sp.get("heal_amount", 0) or 0) > 0 else 1.15))

    return {
        "id": str(sp["id"]),
        "slot": 3,
        "spell_id": str(sp["id"]),
        "name": str(sp.get("name") or sp["id"]),
        "category": "support" if is_support else "spell",
        "intent_code": "defensive" if is_support else "magic",
        "mana_cost": mana_cost,
        "cooldown": 2,
        "damage_mult": dmg_mult if not is_support else 0.0,
        "damage_type": str(sp.get("damage_type") or "magical"),
        "heal_amount": int(sp.get("heal_amount", 0) or 0),
        "status_ailment": sp.get("status_ailment"),
        "target_type": target_type,
    }


def _build_mundane_slot3_skill(role: str, level: int) -> CombatAction:
    if role in ("brute", "guardian"):
        return {
            "id": "haymaker_takedown",
            "slot": 3,
            "name": "Haymaker Takedown",
            "category": "attack",
            "intent_code": "heavy",
            "mana_cost": 0,
            "cooldown": 3,
            "damage_mult": 1.55,
            "damage_type": "physical",
            "armor_penetration": 0.20,
            "status_ailment": "Staggered [1 turn]",
            "target_type": "single_enemy",
        }
    if role == "stalker":
        return {
            "id": "dirty_trick",
            "slot": 3,
            "name": "Dirty Trick",
            "category": "attack",
            "intent_code": "ambush",
            "mana_cost": 0,
            "cooldown": 3,
            "damage_mult": 1.35,
            "damage_type": "physical",
            "armor_penetration": 0.30,
            "status_ailment": "Blinded [2 turns]",
            "target_type": "single_enemy",
        }
    if role == "healer":
        return {
            "id": "adrenaline_second_wind",
            "slot": 3,
            "name": "Adrenaline Second Wind",
            "category": "support",
            "intent_code": "defensive",
            "mana_cost": 0,
            "cooldown": 3,
            "damage_mult": 0.0,
            "damage_type": "physical",
            "heal_amount": 24 + level * 6,
            "target_type": "ally",
        }
    return {
        "id": "suppressive_volley",
        "slot": 3,
        "name": "Suppressive Volley",
        "category": "attack",
        "intent_code": "heavy",
        "mana_cost": 0,
        "cooldown": 3,
        "damage_mult": 1.40,
        "damage_type": "physical",
        "status_ailment": "Weakened [-15% ATK] [2 turns]",
        "target_type": "single_enemy",
    }


def ensure_combatant_loadout(
    entity: Dict[str, Any],
    scenario_key: str = "fantasy",
) -> List[CombatAction]:
    """
    Idempotently attaches `combat_loadout`, `skill_cooldowns`, and missing weapon/armor profiles.
    Civilians strictly receive 0 Max MP and a 2-slot 0-MP mundane kit; mundane scenarios receive
    a 3-slot 0-MP non-magical martial/grit kit; arcane/anomalous scenarios receive 2 tactical
    0-MP skills + 1 MP-consuming SPELL_REGISTRY skill in Slot 3.
    """
    if not isinstance(entity.get("skill_cooldowns"), dict):
        entity["skill_cooldowns"] = {}

    arch_name = str(entity.get("archetype") or entity.get("combat_archetype") or "Skirmisher").strip()
    if "weapon_profile" not in entity or "armor_profile" not in entity:
        try:
            from .enemies import get_enemy_armor_profile, get_enemy_weapon_profile

            if "weapon_profile" not in entity:
                entity["weapon_profile"] = get_enemy_weapon_profile(arch_name)
            if "armor_profile" not in entity:
                entity["armor_profile"] = get_enemy_armor_profile(arch_name)
        except Exception:
            entity.setdefault("weapon_profile", {"primary_type": "physical", "armor_pen": 0.0})
            entity.setdefault("armor_profile", {"base_dt": 0, "armor_class": "Unarmored"})

    is_civilian = (
        str(entity.get("anomalous_npc_tag") or "").strip().lower() == "civilian"
        or str(entity.get("entity_type") or "").strip().lower() == "civilian"
    )
    if is_civilian:
        entity["mp"] = 0
        entity["max_mp"] = 0
        existing = entity.get("combat_loadout")
        if (
            isinstance(existing, list)
            and len(existing) == 2
            and all(int(s.get("mana_cost", 0) or 0) == 0 for s in existing if isinstance(s, dict))
        ):
            return existing
        kit: List[CombatAction] = [
            {
                "id": "desperate_strike",
                "slot": 1,
                "name": "Desperate Strike",
                "category": "attack",
                "intent_code": "basic",
                "mana_cost": 0,
                "cooldown": 0,
                "damage_mult": 0.75,
                "damage_type": "physical",
                "target_type": "single_enemy",
            },
            {
                "id": "take_cover",
                "slot": 2,
                "name": "Take Cover",
                "category": "guard",
                "intent_code": "defensive",
                "mana_cost": 0,
                "cooldown": 3,
                "damage_mult": 0.0,
                "damage_type": "physical",
                "status_ailment": "Braced [+4 DT] [1 turn]",
                "target_type": "self",
            },
        ]
        entity["combat_loadout"] = kit
        return kit

    mundane = is_mundane_combat_scenario(scenario_key)
    existing = entity.get("combat_loadout")
    if isinstance(existing, list) and len(existing) == 3:
        if not mundane:
            return existing
        has_magic = any(
            int(s.get("mana_cost", 0) or 0) > 0 or str(s.get("damage_type") or "") == "magical"
            for s in existing if isinstance(s, dict)
        )
        if not has_magic:
            return existing

    role = _normalize_loadout_role(arch_name, str(entity.get("role") or ""))
    if not entity.get("archetype") and not entity.get("combat_archetype"):
        entity["archetype"] = role.capitalize()
    lvl = max(1, int(entity.get("level") or 1))
    scen_low = str(scenario_key or "fantasy").strip().lower()

    if role == "caster":
        if mundane:
            slot1: CombatAction = {
                "id": "improvised_strike",
                "slot": 1,
                "name": "Focused Strike",
                "category": "attack",
                "intent_code": "basic",
                "mana_cost": 0,
                "cooldown": 0,
                "damage_mult": 0.85,
                "damage_type": "physical",
                "target_type": "single_enemy",
            }
        else:
            is_scifi = any(t in scen_low for t in ("cyber", "sci_fi", "scifi", "space"))
            is_anom = any(t in scen_low for t in ("anomal", "urban_anomal"))
            cantrip_name = "Tech Pulse" if is_scifi else ("Resonance Bolt" if is_anom else "Arcane Cantrip")
            cantrip_dmg = "lightning" if is_scifi else ("aether" if is_anom else "magical")
            slot1 = {
                "id": "caster_cantrip",
                "slot": 1,
                "name": cantrip_name,
                "category": "attack",
                "intent_code": "basic",
                "mana_cost": 0,
                "cooldown": 0,
                "damage_mult": 0.85,
                "damage_type": cantrip_dmg,
                "uses_matk": True,
                "armor_penetration": 0.10,
                "target_type": "single_enemy",
            }
    else:
        wp = entity.get("weapon_profile") if isinstance(entity.get("weapon_profile"), dict) else {}
        slot1 = {
            "id": "weapon_strike",
            "slot": 1,
            "name": "Precision Strike" if role == "stalker" else "Weapon Strike",
            "category": "attack",
            "intent_code": "basic",
            "mana_cost": 0,
            "cooldown": 0,
            "damage_mult": 1.0,
            "damage_type": str(wp.get("primary_type") or "physical"),
            "armor_penetration": 0.15 if role == "stalker" else float(wp.get("armor_pen", 0.0) or 0.0),
            "target_type": "single_enemy",
        }

    if role == "guardian":
        slot2: CombatAction = {
            "id": "intercept_taunt",
            "slot": 2,
            "name": "Intercept Taunt",
            "category": "tactical",
            "intent_code": "defensive",
            "mana_cost": 0,
            "cooldown": 3,
            "damage_mult": 0.80,
            "damage_type": "physical",
            "status_ailment": "Taunted [2 turns]",
            "self_status": "Fortified [+4 DT] [2 turns]",
            "target_type": "single_enemy",
        }
    elif role == "brute":
        slot2 = {
            "id": "crushing_follow_through",
            "slot": 2,
            "name": "Crushing Follow-Through",
            "category": "attack",
            "intent_code": "heavy",
            "mana_cost": 0,
            "cooldown": 2,
            "damage_mult": 1.35,
            "damage_type": "physical",
            "armor_penetration": 0.15,
            "status_ailment": "Exposed [2 turns]",
            "target_type": "single_enemy",
        }
    elif role == "healer":
        slot2 = {
            "id": "field_triage",
            "slot": 2,
            "name": "Field Triage",
            "category": "support",
            "intent_code": "defensive",
            "mana_cost": 0,
            "cooldown": 3,
            "damage_mult": 0.0,
            "damage_type": "physical" if mundane else "holy",
            "heal_amount": 18 + lvl * 4,
            "target_type": "ally",
        }
    elif role == "stalker":
        slot2 = {
            "id": "armor_piercing_ambush",
            "slot": 2,
            "name": "Armor-Piercing Ambush",
            "category": "attack",
            "intent_code": "ambush",
            "mana_cost": 0,
            "cooldown": 2,
            "damage_mult": 1.30,
            "damage_type": "physical",
            "armor_penetration": 0.50,
            "status_ailment": "Bleeding [2 turns]",
            "target_type": "single_enemy",
        }
    else:
        disrupt_dmg = "physical" if mundane else ("lightning" if any(t in scen_low for t in ("cyber", "sci_fi", "scifi")) else "magical")
        slot2 = {
            "id": "suppressive_disrupt",
            "slot": 2,
            "name": "Suppressive Disrupt",
            "category": "tactical",
            "intent_code": "basic" if mundane else "magic",
            "mana_cost": 0,
            "cooldown": 2,
            "damage_mult": 0.90,
            "damage_type": disrupt_dmg,
            "status_ailment": "Demoralized [-15% ATK] [2 turns]",
            "target_type": "single_enemy",
        }

    slot3 = _build_mundane_slot3_skill(role, lvl) if mundane else _select_magic_slot3_skill(role, lvl, scenario_key)
    kit3: List[CombatAction] = [slot1, slot2, slot3]
    entity["combat_loadout"] = kit3
    return kit3


def tick_combatant_cooldowns(entity: Dict[str, Any]) -> None:
    """Decrements active skill cooldowns by 1 turn at the start of a combatant's turn."""
    cds = entity.get("skill_cooldowns")
    if not isinstance(cds, dict):
        entity["skill_cooldowns"] = {}
        return
    updated: Dict[str, int] = {}
    for key, val in cds.items():
        try:
            rem = int(val) - 1
        except (TypeError, ValueError):
            rem = 0
        if rem > 0:
            updated[str(key)] = rem
    entity["skill_cooldowns"] = updated


def reset_combatant_cooldowns(entity: Dict[str, Any]) -> None:
    """Clears all transient skill cooldowns once combat concludes."""
    if isinstance(entity, dict):
        entity["skill_cooldowns"] = {}


__all__ = [
    "ALL_STATS",
    "ARCHETYPE_RULES",
    "MUNDANE_COMBAT_SCENARIOS",
    "ROLE_TIER_MULTIPLIERS",
    "TIER_RANK_TO_ROLE",
    "build_combatant_stat_sheet",
    "compute_companion_vitals",
    "ensure_combatant_loadout",
    "is_mundane_combat_scenario",
    "reset_combatant_cooldowns",
    "tick_combatant_cooldowns",
]
