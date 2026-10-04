from __future__ import annotations
import random
import re
from typing import Dict, Any, List, Optional, Tuple

from .registry import get_spell

def _matches_theme(words: tuple[str, ...], text: str) -> bool:
    """Matches keywords against text, enforcing word boundaries for short words (<=3 chars)."""
    for w in words:
        if len(w) <= 3:
            if re.search(rf"\b{re.escape(w)}\b", text):
                return True
        else:
            if w in text:
                return True
    return False

def get_starter_spells(
    scenario: str = "fantasy",
    char_class: str = "",
    int_stat: int = 5,
    class_description: str = ""
) -> List[str]:
    """
    Returns an INT-scaled, thematically tailored starter package of spells.
    
    INT Scaling Rules:
    - Tier 3 Spells: base 3 + (INT // 2) (Capped at 7).
    - Tier 2 Spells: max(0, (INT - 3) // 2) (Requires INT >= 5, grants 1-3 advanced spells).
    - Tier 1 Spells: 1 if INT >= 10, else 0 (Preserved for dungeon/grimoire discovery).
    
    Thematic Heuristics:
    Matches custom class names & descriptions (e.g. Necromancer -> Dark/Summon, Frost -> Ice, Druid -> Nature/Summon).
    """
    scen = str(scenario or "fantasy").lower()
    cls_text = f"{str(char_class or '')} {str(class_description or '')}".lower()
    int_val = max(1, int(int_stat or 5))

    # Calculate spell budget
    t3_count = min(7, max(3, 3 + (int_val // 2)))
    t2_count = max(0, (int_val - 3) // 2)
    t1_count = 1 if int_val >= 10 else 0

    # Categorized candidate pools
    theme_t3: List[str] = []
    theme_t2: List[str] = []
    theme_t1: List[str] = []

    # 1. Necromancy / Shadow / Death
    if _matches_theme(("necro", "death", "shadow", "undead", "blood", "lich", "warlock", "dark"), cls_text):
        theme_t3 = ["shadow_bolt_t3_st", "venom_dart_t3_st", "raise_skeletons_t3_st", "weaken_t3_st", "dark_mist_t3_aoe", "arcane_dart_t3_st", "mend_t3_st"]
        theme_t2 = ["nether_grasp_t2_aoe", "summon_ghoul_pack_t2_st", "enfeeble_t2_st", "acid_nova_t2_aoe", "abyssal_spike_t2_st"]
        theme_t1 = ["awaken_bone_colossus_t1_st", "total_debilitation_t1_st", "void_singularity_t1_st"]

    # 2. Druid / Nature / Beastmaster / Shaman
    elif _matches_theme(("druid", "nature", "beast", "shaman", "ranger", "hunter", "wild", "wolf"), cls_text):
        theme_t3 = ["call_spirit_wolves_t3_st", "stone_spike_t3_st", "gale_blade_t3_st", "mend_t3_st", "slow_t3_st", "water_jet_t3_st", "spark_jolt_t3_st"]
        theme_t2 = ["summon_dire_bear_t2_st", "boulder_crush_t2_st", "thunder_surge_t2_aoe", "greater_heal_t2_st"]
        theme_t1 = ["wrath_of_nature_hydra_t1_st", "continental_shatter_t1_aoe"]

    # 3. Holy / Cleric / Paladin / Radiant / Inquisitor
    elif _matches_theme(("cleric", "priest", "paladin", "holy", "radiant", "templar", "inquisitor", "angel"), cls_text):
        theme_t3 = ["radiant_spark_t3_st", "holy_light_t3_aoe", "guardian_wisp_t3_st", "mend_t3_st", "aegis_ward_t3_st", "conjure_blade_t3_st", "clarity_t3_st"]
        theme_t2 = ["sunburst_smite_t2_st", "summon_celestial_sentinel_t2_st", "greater_heal_t2_st", "empower_surge_t2_st"]
        theme_t1 = ["heavens_judgement_t1_st", "solar_ascension_t1_aoe", "divine_restoration_t1_st"]

    # 4. Pyromancer / Fire
    elif _matches_theme(("pyro", "fire", "flame", "cinder", "blaze", "magma", "ember"), cls_text):
        theme_t3 = ["firebolt_t3_st", "flame_wave_t3_aoe", "conjure_flame_imps_t3_st", "mend_t3_st", "weaken_t3_st", "arcane_dart_t3_st", "spark_jolt_t3_st"]
        theme_t2 = ["pyroblast_t2_st", "ignition_nova_t2_aoe", "empower_surge_t2_st"]
        theme_t1 = ["dragons_breath_t1_st", "hellfire_inferno_t1_aoe"]

    # 5. Cryomancer / Frost / Ice
    elif _matches_theme(("cryo", "frost", "ice", "glacial", "winter", "cold", "blizzard"), cls_text):
        theme_t3 = ["ice_shard_t3_st", "frost_cone_t3_aoe", "slow_t3_st", "mend_t3_st", "aegis_ward_t3_st", "arcane_dart_t3_st", "water_jet_t3_st"]
        theme_t2 = ["blizzard_storm_t2_aoe", "glacial_spike_t2_st", "diamond_shell_t2_st"]
        theme_t1 = ["absolute_zero_t1_st", "glacial_ruin_t1_aoe"]

    # 6. Steampunk / Clockwork / Aether / Alchemical
    elif _matches_theme(("steampunk", "clockwork", "victorian"), scen) or _matches_theme(("steam", "clockwork", "alchemist", "inventor", "mechanic", "machinist", "tinkerer", "artificer", "aether"), cls_text):
        theme_t3 = ["spark_jolt_t3_st", "chain_lightning_t3_chain", "corrode_armor_t3_st", "iron_shrapnel_t3_aoe", "deploy_micro_drones_t3_st", "aegis_ward_t3_st", "clarity_t3_st"]
        theme_t2 = ["thunder_surge_t2_aoe", "acid_nova_t2_aoe", "lightning_strike_t2_st", "blade_tempest_t2_aoe", "haste_surge_t2_st"]
        theme_t1 = ["ion_cannon_t1_st", "thousand_swords_t1_aoe", "thunder_gods_wrath_t1_aoe"]

    # 7. Tech / Sci-Fi / Cyber / Hacker / Drone
    elif _matches_theme(("scifi", "space", "cyber"), scen) or _matches_theme(("scifi", "space", "cyber", "hacker", "tech", "drone", "engineer", "cyborg", "netrunner"), cls_text):
        theme_t3 = ["spark_jolt_t3_st", "chain_lightning_t3_chain", "deploy_micro_drones_t3_st", "corrode_armor_t3_st", "clarity_t3_st", "iron_shrapnel_t3_aoe", "weaken_t3_st"]
        theme_t2 = ["lightning_strike_t2_st", "thunder_surge_t2_aoe", "acid_nova_t2_aoe", "haste_surge_t2_st"]
        theme_t1 = ["ion_cannon_t1_st", "thunder_gods_wrath_t1_aoe", "void_singularity_t1_st"]

    # 8. Dark Fantasy / Nuclear Post-Apocalypse / Wasteland / Grimdark
    elif _matches_theme(("dark_fantasy", "nuclear_post_apocalypse", "postapoc", "wasteland", "grimdark"), scen) or _matches_theme(("rad", "mutant", "scavenger", "blight", "corrupted", "apocalypse", "raider", "wastelander"), cls_text):
        theme_t3 = ["venom_dart_t3_st", "toxic_miasma_t3_aoe", "shadow_bolt_t3_st", "raise_skeletons_t3_st", "corrode_armor_t3_st", "weaken_t3_st", "dark_mist_t3_aoe"]
        theme_t2 = ["noxious_blast_t2_st", "venomous_cloud_t2_aoe", "summon_ghoul_pack_t2_st", "acid_nova_t2_aoe", "enfeeble_t2_st"]
        theme_t1 = ["deathblight_needle_t1_st", "plaguewind_t1_aoe", "total_debilitation_t1_st", "awaken_bone_colossus_t1_st"]

    # 9. Rogue / Assassin / Shadowblade
    elif _matches_theme(("rogue", "assassin", "thief", "ninja", "blade", "stalker"), cls_text):
        theme_t3 = ["venom_dart_t3_st", "iron_shrapnel_t3_aoe", "shadow_bolt_t3_st", "zephyr_step_t3_st", "corrode_armor_t3_st", "mend_t3_st", "arcane_dart_t3_st"]
        theme_t2 = ["nether_grasp_t2_aoe", "acid_nova_t2_aoe", "haste_surge_t2_st"]
        theme_t1 = ["total_debilitation_t1_st", "astral_beam_t1_st"]

    # 10. Standard Mage / Wizard / Sorcerer / Default
    else:
        theme_t3 = ["firebolt_t3_st", "flame_wave_t3_aoe", "arcane_dart_t3_st", "mend_t3_st", "weaken_t3_st", "spark_jolt_t3_st", "conjure_flame_imps_t3_st"]
        theme_t2 = ["arcane_lance_t2_st", "pyroblast_t2_st", "lightning_strike_t2_st", "greater_heal_t2_st"]
        theme_t1 = ["astral_cataclysm_t1_aoe", "dragons_breath_t1_st"]

    # Assemble spells matching exact budget
    selected: List[str] = []
    
    # Add Tier 3 spells
    for sp_id in theme_t3:
        if sp_id not in selected and len([s for s in selected if get_spell(s) and get_spell(s).get("tier") == 3]) < t3_count:
            selected.append(sp_id)

    # Add Tier 2 spells
    for sp_id in theme_t2:
        if sp_id not in selected and len([s for s in selected if get_spell(s) and get_spell(s).get("tier") == 2]) < t2_count:
            selected.append(sp_id)

    # Add Tier 1 spells
    if t1_count > 0:
        for sp_id in theme_t1:
            if sp_id not in selected:
                selected.append(sp_id)
                break

    # Fallback to ensure at least 3 starter spells if candidate pool was small
    fallback_pool = ["firebolt_t3_st", "arcane_burst_t3_aoe", "conjure_blade_t3_st", "mend_t3_st", "weaken_t3_st"]
    for sp_id in fallback_pool:
        if len(selected) < t3_count and sp_id not in selected:
            selected.append(sp_id)

    return selected


def calculate_spell_damage(
    caster_matk: int,
    spell: Dict[str, Any],
    affinity_multiplier: float = 1.0,
    defender_attrs: Optional[Dict[str, Any]] = None,
    armor_type_dt: Optional[Dict[str, Any]] = None,
    armor_base_dt: int = 0,
    sunder_pct: float = 0.0
) -> int:
    """
    Computes outgoing spell damage using the Unified FNV DR → DT → Floor pipeline.

    Raw = MATK * spell.power_mult * affinity_multiplier (TYPE_AFFINITIES matchup)

    Step 1 — Damage Resistance (DR%):
        gear_dr from *_res affixes + innate_magic_dr (INT * 1.5%, cap 85%).
        sunder_pct reduces effective DR.
        damage_after_dr = raw * (1.0 - min(0.85, total_dr * (1.0 - sunder_pct)))

    Step 2 — Damage Threshold (DT, flat):
        type_dt[damage_type] from armor + innate_magic_dt (INT // 3 + Level // 5).
        sunder_pct reduces effective DT.
        penetrating = damage_after_dr - (effective_dt * (1.0 - sunder_pct))

    Step 3 — 20% Bleed-Through Floor:
        final_net = max(raw * 0.20, penetrating)
    """
    power_mult = spell.get("power_mult", 1.0)
    damage_type = spell.get("damage_type", "magical")
    raw_damage = max(1.0, float(caster_matk) * power_mult * affinity_multiplier)

    # Check taxonomy immunities, resistances, and weaknesses
    if defender_attrs:
        from mechanics.combat.formulas import matches_damage_type
        target_immunities = defender_attrs.get("immunities", [])
        target_resistances = defender_attrs.get("resistances", [])
        target_weaknesses = defender_attrs.get("weaknesses", [])

        if matches_damage_type(target_immunities, damage_type):
            return 0
        if matches_damage_type(target_resistances, damage_type):
            raw_damage *= 0.5
        if matches_damage_type(target_weaknesses, damage_type):
            raw_damage *= 1.5

    # Check for sundering affix in spell metadata if not explicitly passed
    if sunder_pct <= 0.0 and "sundering" in spell.get("affixes", []):
        sunder_pct = 0.35

    # ── Unified FNV DR → DT → Floor ──────────────────────────────────────────
    # Step 1: DR
    innate_magic_dr = defender_attrs.get("innate_magic_dr", 0.0)
    gear_dr = defender_attrs.get("gear_dr", {})
    ch_gear_dr = gear_dr.get(damage_type, 0.0)
    # omni_res already folded into gear_dr in attributes.py
    total_dr = min(0.85, (ch_gear_dr + innate_magic_dr) * (1.0 - sunder_pct))
    damage_after_dr = raw_damage * (1.0 - total_dr)

    # Step 2: DT
    innate_magic_dt = defender_attrs.get("innate_magic_dt", 0)
    type_dt = armor_type_dt or {}
    gear_dt = type_dt.get(damage_type, armor_base_dt)
    effective_dt = (gear_dt + innate_magic_dt) * (1.0 - sunder_pct)
    penetrating = damage_after_dr - effective_dt

    # Step 3: Floor
    floor_damage = raw_damage * 0.20
    return max(1, int(round(max(floor_damage, penetrating))))



def format_spell_choice_label(spell: Dict[str, Any], hit_chance: int, player_mp: int) -> str:
    """Formats an aesthetic, informative label for Discord combat buttons."""
    emoji = spell.get("emoji", "🔮")
    name = spell.get("name", "Spell")
    mp_cost = spell.get("mp_cost", 0)
    discipline = spell.get("discipline", "attack")
    target_type = spell.get("target_type", "single")
    crit_bonus = spell.get("crit_bonus", 0.0)

    if discipline == "attack":
        if target_type == "chain":
            return f"{emoji} {name} ({hit_chance}% • {mp_cost} MP • Chain)"
        elif target_type == "aoe":
            return f"{emoji} {name} ({hit_chance}% • {mp_cost} MP • AOE)"
        elif crit_bonus >= 0.12:
            crit_pct = int(crit_bonus * 100)
            return f"{emoji} {name} ({hit_chance}% • {mp_cost} MP • +{crit_pct}% Crit)"
        else:
            return f"{emoji} {name} ({hit_chance}% • {mp_cost} MP • ST)"
    elif discipline == "support":
        if "heal_amount" in spell:
            return f"{emoji} {name} (+{spell['heal_amount']} HP • {mp_cost} MP)"
        elif "mp_amount" in spell:
            return f"{emoji} {name} (+{spell['mp_amount']} MP • Free)"
        else:
            buff_pct = int(spell.get("buff_pct", 0.15) * 100)
            return f"{emoji} {name} (+{buff_pct}% {spell.get('stat_target', 'DEF')} • {mp_cost} MP)"
    elif discipline == "summon":
        count = spell.get("summon_count", 1)
        dur = spell.get("summon_duration", 3)
        return f"{emoji} {name} ({count}x • {dur}t • {mp_cost} MP)"
    else:  # Curse / hybrid debuff
        debuff_pct = int(spell.get("debuff_pct", 0.15) * 100)
        scope = "Chain" if target_type == "chain" else ("AOE" if target_type == "aoe" else "ST")
        return f"{emoji} {name} (-{debuff_pct}% {spell.get('stat_target', 'ATK')} • {mp_cost} MP • {scope})"

