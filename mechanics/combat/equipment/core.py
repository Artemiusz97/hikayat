from __future__ import annotations
"""
Procedural equipment generation, card formatting, spellbook generation, and item enrichment.
"""
import json
import random
import re
from typing import Dict, Any, List, Optional, Tuple

from .tables import *
from .metadata import *

def generate_random_equipment(
    scenario: str = "fantasy",
    slot: str = "Weapon",
    tier: Optional[int] = None
) -> Dict[str, Any]:
    """
    Generates a procedurally generated item with balanced stats, tags,
    attack/protection types, and scenario-themed naming.
    For non-combat scenarios (e.g. High School / Slice of Life), generates
    purely cosmetic items with 0 combat stats.
    """
    from scenario_data import is_non_combat_scenario
    is_non_combat = is_non_combat_scenario(scenario)
    item_tier = tier if tier in (1, 2, 3) else roll_tier()

    if is_non_combat:
        if slot == "Weapon":
            arch_key = random.choice(list(NON_COMBAT_WEAPON_ARCHETYPES.keys()))
            base_data = NON_COMBAT_WEAPON_ARCHETYPES[arch_key]
            item_type = "Weapon"
        elif slot == "Shield":
            arch_key = random.choice(list(NON_COMBAT_SHIELD_ARCHETYPES.keys()))
            base_data = NON_COMBAT_SHIELD_ARCHETYPES[arch_key]
            item_type = "Shield"
        elif slot in ("Top", "Bottom", "Gloves", "Shoes"):
            arch_key = random.choice(list(NON_COMBAT_ARMOR_ARCHETYPES.keys()))
            base_data = NON_COMBAT_ARMOR_ARCHETYPES[arch_key]
            item_type = "Armor"
        else:
            arch_key = random.choice(list(NON_COMBAT_ACCESSORY_ARCHETYPES.keys()))
            base_data = NON_COMBAT_ACCESSORY_ARCHETYPES[arch_key]
            item_type = "Accessory"

        scen_lower = scenario.lower() if scenario else "high_school"
        if scen_lower in SCENARIO_AFFIXES:
            affixes = SCENARIO_AFFIXES[scen_lower]
        elif "high_school" in scen_lower:
            affixes = SCENARIO_AFFIXES["high_school"]
        elif "slice_of_life" in scen_lower:
            affixes = SCENARIO_AFFIXES["slice_of_life"]
        else:
            affixes = SCENARIO_AFFIXES["non_combat"]

        base_name = base_data.get("name", arch_key.replace("_", " ").title())
        if item_tier == 3:
            prefix = random.choice(affixes["prefixes_t3"])
            name = f"{prefix} {base_name}"
        elif item_tier == 2:
            prefix = random.choice(affixes["prefixes_t2"])
            suffix = random.choice(affixes["suffixes_t2"])
            name = f"{prefix} {base_name} {suffix}"
        else:
            prefix = random.choice(affixes["prefixes_t1"])
            suffix = random.choice(affixes["suffixes_t1"])
            name = f"{prefix} {base_name} {suffix}"

        metadata: Dict[str, Any] = {
            "name": name,
            "tier": item_tier,
            "tier_name": TIER_NAMES[item_tier],
            "slot": slot,
            "item_type": item_type,
            "archetype": arch_key,
            "stat_modifiers": {},
            "is_cosmetic": True,
            "tags": ["Cosmetic", "Non-Combat"]
        }
        if item_type == "Armor":
            metadata["armor_type"] = base_data.get("armor_type", "clothing")
            metadata["protection_types"] = list(base_data.get("protection_types", ["style"]))
        elif item_type == "Weapon":
            metadata["mass"] = base_data.get("mass", "light")
            metadata["handedness"] = base_data.get("handedness", "1H")
            metadata["attack_types"] = list(base_data.get("attack_types", ["utility"]))
        elif item_type == "Shield":
            metadata["mass"] = base_data.get("mass", "light")
            metadata["handedness"] = "1H"
            metadata["block_chance"] = 0

        return {
            "name": name,
            "item_type": item_type,
            "slot": slot,
            "effect": build_equipment_effect_str(metadata),
            "metadata": metadata,
            "slot_cost": 1
        }

    scen_key = scenario.lower() if scenario.lower() in SCENARIO_AFFIXES else "fantasy"
    scen_affixes = SCENARIO_AFFIXES[scen_key]

    if slot == "Weapon":
        archetype = random.choice(list(WEAPON_ARCHETYPES.keys()))
        base_data = WEAPON_ARCHETYPES[archetype]
        item_type = "Weapon"
    elif slot == "Shield":
        archetype = random.choice(list(SHIELD_ARCHETYPES.keys()))
        base_data = SHIELD_ARCHETYPES[archetype]
        item_type = "Shield"
    elif slot in ("Top", "Bottom", "Gloves", "Shoes"):
        archetype = random.choice(list(ARMOR_ARCHETYPES.keys()))
        base_data = ARMOR_ARCHETYPES[archetype]
        item_type = "Armor"
    else:  # Accessories
        archetype = random.choice(list(ACCESSORY_ARCHETYPES.keys()))
        base_data = ACCESSORY_ARCHETYPES[archetype]
        item_type = "Accessory"

    # Tier stat scaling multipliers
    tier_mult = 1.0 if item_tier == 3 else (1.4 if item_tier == 2 else 2.0)
    stat_mods: Dict[str, Any] = {}

    # 1. Inherent Base Archetype Stats (Main attributes)
    for k, v in base_data.items():
        if k.startswith("base_"):
            stat_name = k.replace("base_", "")
            val = int(round(v * tier_mult))
            if val != 0:
                stat_mods[stat_name] = val

    # Slot-specific baseline utility buffs
    if slot == "Shoes":
        stat_mods["eva"] = stat_mods.get("eva", 0) + (4 * (4 - item_tier))
    elif slot == "Gloves":
        stat_mods["acc"] = stat_mods.get("acc", 0) + (4 * (4 - item_tier))
        stat_mods["macc"] = stat_mods.get("macc", 0) + (4 * (4 - item_tier))

    # 2. Roll Dynamic Random Bonus Attributes (1 for T3, 2-3 for T2, 3-5 for T1)
    num_random_attrs = 1 if item_tier == 3 else (random.randint(2, 3) if item_tier == 2 else random.randint(3, 5))
    
    # Filter candidate affixes based on equipment type
    candidate_affix_keys = list(RANDOM_AFFIX_POOL.keys())
    if item_type == "Weapon":
        # Weight towards offensive and elemental attack affixes
        candidates = [k for k in candidate_affix_keys if RANDOM_AFFIX_POOL[k]["type"] in ("offensive", "vitals")]
    elif item_type == "Armor":
        # Weight towards defensive, resistance, and vitals affixes
        candidates = [k for k in candidate_affix_keys if RANDOM_AFFIX_POOL[k]["type"] in ("defensive", "resistance", "vitals") and k != "block_chance"]
    elif item_type == "Shield":
        candidates = [k for k in candidate_affix_keys if RANDOM_AFFIX_POOL[k]["type"] in ("defensive", "resistance", "vitals")]
    else:  # Accessory
        candidates = [k for k in candidate_affix_keys if k != "block_chance"]

    # Exclude omni_res on Tier 3
    if item_tier == 3 and "omni_res" in candidates:
        candidates.remove("omni_res")

    selected_affix_keys = random.sample(candidates, min(num_random_attrs, len(candidates)))
    rolled_themes = []

    for a_key in selected_affix_keys:
        a_def = RANDOM_AFFIX_POOL[a_key]
        range_key = f"t{item_tier}_range"
        min_v, max_v = a_def.get(range_key, (1, 5))
        if max_v > 0:
            rolled_val = random.randint(min_v, max_v)
            if a_key in ("atk_pct", "matk_pct"):
                stat_mods[a_key] = round(stat_mods.get(a_key, 0.0) + (rolled_val / 100.0), 2)
            elif a_key.endswith("_convert"):
                stat_mods[a_key] = round(rolled_val / 100.0, 2)
            else:
                stat_mods[a_key] = stat_mods.get(a_key, 0) + rolled_val
            rolled_themes.extend(a_def.get("themes", []))

    # Add masterwork percentage scaling modifiers for Tier 2 and Tier 1 items
    if item_tier == 2:
        stat_mods["atk_pct"] = round(stat_mods.get("atk_pct", 0.0) + 0.08, 2)
        stat_mods["matk_pct"] = round(stat_mods.get("matk_pct", 0.0) + 0.08, 2)
        stat_mods["def_pct"] = round(stat_mods.get("def_pct", 0.0) + 0.08, 2)
    elif item_tier == 1:
        stat_mods["atk_pct"] = round(stat_mods.get("atk_pct", 0.0) + 0.15, 2)
        stat_mods["matk_pct"] = round(stat_mods.get("matk_pct", 0.0) + 0.15, 2)
        stat_mods["def_pct"] = round(stat_mods.get("def_pct", 0.0) + 0.15, 2)
        stat_mods["crit"] = stat_mods.get("crit", 0) + 8

    # 3. Attribute-Linked Procedural Naming Engine
    dominant_theme = random.choice(rolled_themes) if rolled_themes else "arcane"
    theme_dict = THEME_VOCABULARY.get(dominant_theme, THEME_VOCABULARY["arcane"])

    base_name = archetype.replace("_", " ").title()
    prefix_pool = theme_dict.get(f"prefixes_t{item_tier}") or scen_affixes.get(f"prefixes_t{item_tier}") or ["Fine"]
    suffix_pool = theme_dict.get(f"suffixes_t{item_tier}") or scen_affixes.get(f"suffixes_t{item_tier}") or ["of Power"]

    if item_tier == 3:
        prefix = random.choice(prefix_pool)
        name = f"{prefix} {base_name}"
    elif item_tier == 2:
        prefix = random.choice(prefix_pool)
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
    else:  # Tier 1 Legendary
        prefix = random.choice(prefix_pool)
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"

    metadata = {
        "name": name,
        "tier": item_tier,
        "tier_name": TIER_NAMES[item_tier],
        "slot": slot,
        "item_type": item_type,
        "archetype": archetype,
        "stat_modifiers": stat_mods,
        "tags": []
    }

    if item_type == "Weapon":
        metadata["mass"] = base_data.get("mass", "medium")
        metadata["handedness"] = base_data.get("handedness", "1H")
        metadata["multiplier"] = base_data.get("multiplier", 1.0)
        metadata["crit_bonus"] = base_data.get("crit_bonus", 0)
        metadata["attack_types"] = list(base_data.get("attack_types", ["slash"]))
        metadata["attack_profiles"] = dict(base_data.get("attack_profiles", {}))
        if "projectile_type" in base_data:
            metadata["projectile_type"] = base_data["projectile_type"]
            metadata["tags"].append(base_data["projectile_type"])
        dmg = dict(base_data.get("default_damage", {"physical": 1.0}))
        
        # Check for rolled elemental conversion
        has_conv = False
        for a_key, conv_pct in stat_mods.items():
            if a_key.endswith("_convert"):
                elem = a_key.split("_")[0]
                metadata["elem_convert_type"] = elem
                metadata["elem_convert_pct"] = conv_pct
                dmg = {"physical": round(max(0.0, 1.0 - conv_pct), 2), elem: conv_pct}
                metadata["tags"].append(f"elem_{elem}")
                has_conv = True
                break
        if not has_conv:
            if item_tier <= 2 and scen_key == "fantasy":
                metadata["elem_convert_type"] = "fire"
                metadata["elem_convert_pct"] = 0.30
                dmg = {"physical": 0.70, "fire": 0.30}
                metadata["tags"].append("elem_fire")
            elif item_tier <= 2 and scen_key in ("scifi", "cyberpunk"):
                metadata["elem_convert_type"] = "energy"
                metadata["elem_convert_pct"] = 0.50
                dmg = {"energy": 0.50, "plasma": 0.50}
                metadata["tags"].append("elem_energy")
        metadata["damage_types"] = dmg
        if metadata["handedness"] == "2H":
            metadata["tags"].append("Two-Handed")
        elif metadata["handedness"] == "Versatile":
            metadata["tags"].append("Versatile")
    elif item_type == "Shield":
        tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
        base_dt = int(round(base_data.get("base_dt", base_data.get("dt_contribution", 6)) * tier_mult))
        type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
        # Tier bonus
        if item_tier == 2:
            base_dt += 2
        elif item_tier == 1:
            base_dt += 4
        if "dt_bonus" in stat_mods:
            base_dt += stat_mods["dt_bonus"]

        metadata["mass"] = base_data.get("mass", "medium")
        metadata["handedness"] = base_data.get("handedness", "1H")
        metadata["base_dt"] = base_dt
        metadata["dt_contribution"] = base_dt
        metadata["type_dt"] = type_dt
        metadata["block_chance"] = base_data.get("block_chance", 20) + (5 if item_tier == 2 else (10 if item_tier == 1 else 0)) + stat_mods.get("block_chance", 0)
        metadata["tags"].append("Shield")
    elif item_type == "Armor":
        tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
        base_dt = int(round(base_data.get("base_dt", 0) * tier_mult))
        type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
        # Tier bonus for Armors
        if item_tier == 2:
            base_dt += 2
        elif item_tier == 1:
            base_dt += 5
            stat_mods["omni_res"] = stat_mods.get("omni_res", 0) + 8

        if "dt_bonus" in stat_mods:
            base_dt += stat_mods["dt_bonus"]
        if "magic_dt" in stat_mods:
            type_dt["magical"] = type_dt.get("magical", base_dt) + stat_mods["magic_dt"]

        if "ballistic_weave" in stat_mods:
            type_dt["pistol_round"] = type_dt.get("pistol_round", base_dt) + stat_mods["ballistic_weave"]
            type_dt["scatter_shot"] = type_dt.get("scatter_shot", base_dt) + stat_mods["ballistic_weave"]
        if "ceramic_insert" in stat_mods:
            type_dt["rifle_round"] = type_dt.get("rifle_round", base_dt) + stat_mods["ceramic_insert"]
            type_dt["high_caliber_round"] = type_dt.get("high_caliber_round", base_dt) + stat_mods["ceramic_insert"]
        if "anti_puncture" in stat_mods:
            type_dt["arrow"] = type_dt.get("arrow", base_dt) + stat_mods["anti_puncture"]
            type_dt["bolt"] = type_dt.get("bolt", base_dt) + stat_mods["anti_puncture"]
        if "ablative_coating" in stat_mods:
            type_dt["energy_cell"] = type_dt.get("energy_cell", base_dt) + stat_mods["ablative_coating"]
            type_dt["energy"] = type_dt.get("energy", base_dt) + stat_mods["ablative_coating"]

        metadata["armor_type"] = base_data.get("armor_type", "light")
        metadata["base_dt"] = base_dt
        metadata["type_dt"] = type_dt
        prots = list(base_data.get("protection_types", ["physical"]))
        # Dynamically append rolled elemental protection tags
        if "fire_res" in stat_mods and "fire" not in prots:
            prots.append("fire")
        if "shock_res" in stat_mods and "shock" not in prots:
            prots.append("shock")
        if "ice_res" in stat_mods and "ice" not in prots:
            prots.append("ice")
        if "poison_res" in stat_mods and "poison" not in prots:
            prots.append("poison")
        if "holy_res" in stat_mods and "holy" not in prots:
            prots.append("holy")
        if "dark_res" in stat_mods and "dark" not in prots:
            prots.append("dark")
        if "omni_res" in stat_mods and "all elements" not in prots:
            prots.append("all elements")
        metadata["protection_types"] = prots
        metadata["tags"].append(f"{metadata['armor_type'].title()} Armor")
    elif item_type == "Accessory":
        tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
        base_dt = int(round(base_data.get("base_dt", 0) * tier_mult))
        type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
        if "dt_bonus" in stat_mods:
            base_dt += stat_mods["dt_bonus"]
        if "magic_dt" in stat_mods:
            type_dt["magical"] = type_dt.get("magical", 0) + stat_mods["magic_dt"]
        metadata["base_dt"] = base_dt
        metadata["type_dt"] = type_dt
        metadata["tags"].append("Accessory")

    return {
        "name": name,
        "item_type": item_type,
        "slot": slot,
        "effect": build_equipment_effect_str(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }


def format_equipment_card(metadata: Dict[str, Any]) -> str:
    """Generates an aesthetic, formatted text card for /inventory inspect."""
    tier = metadata.get("tier", 3)
    tier_emoji = TIER_EMOJIS.get(tier, "⚪")
    tier_name = metadata.get("tier_name", TIER_NAMES.get(tier, "Standard"))
    name = metadata.get("name", "Equipment")
    slot = metadata.get("slot", "Item")
    archetype = metadata.get("archetype", "gear").replace("_", " ").title()

    lines = [f"{tier_emoji} **{name}** ({tier_name})", f"**Slot:** {slot} • **Archetype:** {archetype}"]

    if "handedness" in metadata:
        mass = metadata.get("mass", "medium").title()
        hand = metadata.get("handedness", "1H")
        lines.append(f"**Mass:** {mass} • **Handedness:** {hand}")

    if "projectile_type" in metadata:
        lines.append(f"**Ammo/Projectile:** {metadata['projectile_type'].replace('_', ' ').title()}")

    if "attack_types" in metadata:
        profiles = metadata.get("attack_profiles", {})
        if profiles and len(profiles) > 1:
            prof_parts = [
                f"{atype.title()}: {p['multiplier']}x ({p['damage_type'].title()})"
                for atype, p in profiles.items()
            ]
            lines.append(f"**Attack Modes:** {' • '.join(prof_parts)}")
        else:
            mult = metadata.get("multiplier", 1.0)
            atk_types = ", ".join(t.title() for t in metadata["attack_types"])
            lines.append(f"**Attack Modes:** {mult}x ({atk_types})")

    if "protection_types" in metadata:
        prot_types = ", ".join(t.title() for t in metadata["protection_types"])
        arm_type = metadata.get("armor_type", "light").title()
        base_dt = metadata.get("base_dt", 0)
        lines.append(f"**Armor Class:** {arm_type} (Base DT: {base_dt}) • **Protects:** {prot_types}")

    if "block_chance" in metadata and metadata.get("block_chance", 0) > 0:
        lines.append(f"**Block Chance:** {metadata['block_chance']}%")

    stats = metadata.get("stat_modifiers", {})
    stat_parts = []
    
    # Core Vitals & Combat Multiplier Stats
    if "atk_pct" in stats:
        stat_parts.append(f"⚔️ ATK +{int(round(stats['atk_pct']*100))}%")
    elif "atk" in stats:
        pct = f" (+{int(stats['atk_pct']*100)}%)" if "atk_pct" in stats else ""
        sign = "+" if stats["atk"] >= 0 else ""
        stat_parts.append(f"⚔️ ATK {sign}{stats['atk']}{pct}")
    if "matk_pct" in stats:
        stat_parts.append(f"🔮 MATK +{int(round(stats['matk_pct']*100))}%")
    elif "matk" in stats:
        pct = f" (+{int(stats['matk_pct']*100)}%)" if "matk_pct" in stats else ""
        sign = "+" if stats["matk"] >= 0 else ""
        stat_parts.append(f"🔮 MATK {sign}{stats['matk']}{pct}")
    if "def" in stats:
        pct = f" (+{int(stats['def_pct']*100)}%)" if "def_pct" in stats else ""
        sign = "+" if stats["def"] >= 0 else ""
        stat_parts.append(f"🛡️ DEF {sign}{stats['def']}{pct}")
    if "mdef" in stats:
        pct = f" (+{int(stats['mdef_pct']*100)}%)" if "mdef_pct" in stats else ""
        sign = "+" if stats["mdef"] >= 0 else ""
        stat_parts.append(f"✨ MDEF {sign}{stats['mdef']}{pct}")
    if "acc" in stats:
        sign = "+" if stats["acc"] >= 0 else ""
        stat_parts.append(f"🎯 ACC {sign}{stats['acc']}%")
    if "macc" in stats:
        sign = "+" if stats["macc"] >= 0 else ""
        stat_parts.append(f"💫 MACC {sign}{stats['macc']}%")
    if "eva" in stats:
        sign = "+" if stats["eva"] >= 0 else ""
        stat_parts.append(f"💨 EVA {sign}{stats['eva']}%")
    if "crit" in stats:
        sign = "+" if stats["crit"] >= 0 else ""
        stat_parts.append(f"🌟 CRIT {sign}{stats['crit']}%")

    # Elemental Flat Attack Bonuses
    elem_icons = {"fire": "🔥", "shock": "⚡", "ice": "❄️", "poison": "🧪", "holy": "✨", "dark": "🌑"}
    for elem, icon in elem_icons.items():
        atk_key = f"{elem}_atk"
        if atk_key in stats and stats[atk_key] > 0:
            stat_parts.append(f"{icon} {elem.title()} ATK +{stats[atk_key]}")

    # Elemental Conversion
    for elem in ("fire", "shock", "ice", "poison", "holy", "dark"):
        conv_key = f"{elem}_convert"
        if conv_key in stats:
            stat_parts.append(f"✨ {elem.title()} Conversion +{int(round(stats[conv_key]*100))}%")

    # DT & Armor Affixes
    if "dt_bonus" in stats:
        stat_parts.append(f"🛡️ Hardened Plating +{stats['dt_bonus']} DT")
    elif metadata.get("base_dt", 0) > 0 and metadata.get("item_type") in ("Shield", "Accessory"):
        stat_parts.append(f"🛡️ DT +{metadata['base_dt']}")
    if "magic_dt" in stats:
        stat_parts.append(f"🔮 Arcane Warding +{stats['magic_dt']} Magic DT")

    # Ballistic / Projectile Armor Affixes
    if "ballistic_weave" in stats:
        stat_parts.append(f"🛡️ Ballistic Weave +{stats['ballistic_weave']} DT")
    if "ceramic_insert" in stats:
        stat_parts.append(f"🪨 Ceramic Plating +{stats['ceramic_insert']} DT")
    if "anti_puncture" in stats:
        stat_parts.append(f"🗡️ Anti-Puncture +{stats['anti_puncture']} DT")
    if "ablative_coating" in stats:
        stat_parts.append(f"✨ Ablative Coating +{stats['ablative_coating']} DT")

    # Resistances (Damage Resistance DR%)
    if "physical_res" in stats:
        stat_parts.append(f"🪨 Kinetic Dampening +{stats['physical_res']}% Physical DR")
    if "energy_res" in stats:
        stat_parts.append(f"⚡ Energy Dissipation +{stats['energy_res']}% Energy DR")
    if "fire_res" in stats:
        stat_parts.append(f"🔥 Fire Res +{stats['fire_res']}%")
    if "shock_res" in stats:
        stat_parts.append(f"⚡ Shock Res +{stats['shock_res']}%")
    if "ice_res" in stats:
        stat_parts.append(f"❄️ Ice Res +{stats['ice_res']}%")
    if "poison_res" in stats:
        stat_parts.append(f"🧪 Poison Res +{stats['poison_res']}%")
    if "holy_res" in stats:
        stat_parts.append(f"✨ Holy Res +{stats['holy_res']}%")
    if "dark_res" in stats:
        stat_parts.append(f"🌑 Dark Res +{stats['dark_res']}%")
    if "omni_res" in stats:
        stat_parts.append(f"🌈 Omni-Res +{stats['omni_res']}%")

    # Vitals & Regeneration
    if "max_hp" in stats:
        stat_parts.append(f"❤️ Max HP +{stats['max_hp']}")
    if "max_mp" in stats:
        stat_parts.append(f"💙 Max MP +{stats['max_mp']}")
    if "hp_regen" in stats:
        stat_parts.append(f"💚 HP Regen +{stats['hp_regen']}/rnd")
    if "mp_regen" in stats:
        stat_parts.append(f"💙 MP Regen +{stats['mp_regen']}/rnd")

    if metadata.get("is_cosmetic") or not stats:
        lines.append("🎨 **Type:** Cosmetic & Narrative Flair *(No combat stats in slice-of-life / non-combat scenarios)*")
    elif stat_parts:
        lines.append("**Stats:** " + " | ".join(stat_parts))

    if metadata.get("handedness") == "2H":
        lines.append("⚠️ *Two-Handed: Cannot be used with a shield.*")
    elif metadata.get("handedness") == "Versatile":
        lines.append("🔄 *Versatile: +15% Damage Multiplier & +4% Crit when two-handed (no shield).*")

    return "\n".join(lines)


def generate_spellbook_item(spell_id: Optional[str] = None, scenario: str = "fantasy", tier: int = 3) -> dict:
    """Generates a consumable spellbook / grimoire item that teaches a specific or procedurally generated spell."""
    from mechanics.combat.spells import get_spell, register_spell
    if not spell_id:
        from mechanics.combat.spells import generate_procedural_spellbook_item
        item = generate_procedural_spellbook_item(scenario=scenario, tier=tier)
        # Register spell in active registry
        if "spell_data" in item.get("metadata", {}):
            register_spell(item["metadata"]["spell_data"])
        return item

    spell = get_spell(spell_id)
    if not spell:
        spell = {
            "id": spell_id, "name": "Ancient Spell", "tier": tier,
            "discipline": "attack", "damage_type": "magical"
        }

    tier = spell.get("tier", tier)
    tier_prefix = "Grimoire" if tier == 1 else ("Tome" if tier == 2 else "Spellbook")
    name = f"{tier_prefix}: {spell['name']}"
    slot_cost = 1

    metadata = {
        "item_type": "Spellbook",
        "spell_id": spell_id,
        "spell_name": spell["name"],
        "discipline": spell.get("discipline", "attack"),
        "school": spell.get("school", "Evocation"),
        "tier": tier,
        "damage_type": spell.get("damage_type", "magical"),
        "is_spellbook": True,
        "tags": spell.get("tags", [spell.get("school", "Evocation"), f"Tier {tier}"])
    }

    effect_str = f"[SPELLBOOK_JSON]{json.dumps(metadata)}"
    return {
        "name": name,
        "item_type": "Spellbook",
        "slot": None,
        "effect": effect_str,
        "metadata": metadata,
        "slot_cost": slot_cost
    }


def enrich_equipment_item(item: dict, scenario: str = "fantasy") -> dict:
    """
    Enriches a merchant or plain equipment item dict with serialized [ITEM_JSON] metadata,
    appropriate archetype stats, multipliers, type DT, tags, and affixes if missing.
    Returns the enriched item dict.
    """
    if not item or not isinstance(item, dict):
        return item

    # If it already has [ITEM_JSON], [GEAR_JSON], or [SPELLBOOK_JSON], ensure metadata is set and return
    effect_raw = str(item.get("effect") or "")
    if effect_raw.startswith("[ITEM_JSON]") or effect_raw.startswith("[GEAR_JSON]") or effect_raw.startswith("[SPELLBOOK_JSON]"):
        if "metadata" not in item:
            item["metadata"] = parse_equipment_metadata(item)
        return item

    from mechanics.combat.items import serialize_item, parse_item_tier

    # 1. Determine tier
    tier = item.get("tier")
    if not tier or tier not in (1, 2, 3):
        tier = parse_item_tier(item)
    item["tier"] = tier

    # 2. Determine slot and item_type
    slot = item.get("slot")
    item_type = item.get("item_type", "Item")
    name = str(item.get("name", "")).strip()
    name_lower = name.lower()
    desc_lower = str(item.get("description", "")).lower()

    if not slot:
        itype_low = item_type.lower()
        if itype_low in ("weapon",):
            slot = "Weapon"
        elif itype_low in ("shield",):
            slot = "Shield"
        elif itype_low in ("armor", "cuirass", "plate", "body_armor"):
            slot = "Armor"
        elif itype_low in ("head", "headwear", "helmet"):
            slot = "Head"
        elif itype_low in ("gloves", "handwear", "gauntlets"):
            slot = "Gloves"
        elif itype_low in ("shoes", "footwear", "boots"):
            slot = "Shoes"
        elif itype_low in ("top",):
            slot = "Top"
        elif itype_low in ("bottom",):
            slot = "Bottom"
        elif itype_low in ("clothing",):
            if any(w in name_lower or w in desc_lower for w in ["pants", "trouser", "skirt", "short", "jeans", "slack"]):
                slot = "Bottom"
            else:
                slot = "Top"
        elif itype_low in ("accessory", "ring", "amulet", "necklace", "talisman", "trinket"):
            slot = "Accessory 1"
        else:
            # Heuristics based on name keywords
            if any(w in name_lower for w in ["shield", "buckler", "aegis", "bulwark"]):
                slot = "Shield"
                item_type = "Shield"
            elif any(w in name_lower for w in ["helmet", "helm", "hood", "visor", "circlet", "cap", "hat", "mask"]):
                slot = "Head"
                item_type = "Head"
            elif any(w in name_lower for w in ["glove", "gauntlet", "mitt", "wraps"]):
                slot = "Gloves"
                item_type = "Gloves"
            elif any(w in name_lower for w in ["boot", "shoe", "greaves", "sneaker", "sandal"]):
                slot = "Shoes"
                item_type = "Shoes"
            elif any(w in name_lower for w in ["pants", "trouser", "skirt", "shorts", "jeans"]):
                slot = "Bottom"
                item_type = "Clothing"
            elif any(w in name_lower for w in ["shirt", "blouse", "robe", "tunic", "jacket", "hoodie", "sweater"]):
                slot = "Top"
                item_type = "Clothing"
            elif any(w in name_lower for w in ["plate", "cuirass", "mail", "kevlar", "hauberk", "power armor", "combat armor", "vest"]):
                slot = "Armor"
                item_type = "Armor"
            elif any(w in name_lower for w in ["ring", "amulet", "pendant", "necklace", "charm", "talisman", "bracelet", "earring"]):
                slot = "Accessory 1"
                item_type = "Accessory"
            else:
                slot = "Weapon"
                item_type = "Weapon"

    item["slot"] = slot
    item["item_type"] = item_type

    # Parse metadata using parse_equipment_metadata
    metadata = parse_equipment_metadata(item)
    metadata["name"] = name
    metadata["tier"] = tier
    metadata["tier_name"] = TIER_NAMES.get(tier, "Standard")
    metadata["slot"] = slot
    metadata["item_type"] = item_type

    effect_str = serialize_item(metadata)
    item["effect"] = effect_str
    item["metadata"] = metadata
    return item
