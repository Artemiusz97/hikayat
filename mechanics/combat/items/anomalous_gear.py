from __future__ import annotations
"""
Anomalous Incursions Gear & Equipment-Granted Spell Engine.

Enforces:
1. 50% Melee / 50% Ranged modern weapon archetype distribution.
2. Tier-scaled 'anomalous' tag probability:
   - 5-tier scale: T1=10%, T2=25%, T3=45%, T4=75%, T5=100%
   - 3-tier scale: Tier 3 (Standard)=20%, Tier 2 (Superior)=50%, Tier 1 (Relic)=100%
   - Private Agency HQ shop bonus: +20% chance.
3. Strict Elemental Rule:
   - ONLY items with the 'anomalous' tag receive fantasy elemental tags/conversions/resistances.
   - Non-anomalous gear is strictly physical/ballistic with realistic modern tactical naming.
4. Slot-Restricted Equipment-Granted Spells (~35% of eligible anomalous items):
   - Eligible slots: Weapon, Shield, Armor/Top, Accessory 1-4.
   - Headwear, Gloves, Shoes, Bottoms never grant spells.
5. Dynamic Equip/Unequip Spell Sync & Duplicate Stack Empowerment (+20% power when 2 items grant the same spell).
"""
import copy
import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mechanics.combat.items.envelope import serialize_item

ANOMALOUS_MELEE_ARCHETYPES: List[str] = [
    "katana", "baton", "dagger", "shortsword", "sword",
    "cleaver", "axe", "warhammer", "spear", "fist_weapon"
]

ANOMALOUS_RANGED_ARCHETYPES: List[str] = [
    "pistol", "revolver", "submachinegun", "shotgun", "rifle", "machinegun"
]

ANOMALOUS_ELEMENTS: List[str] = [
    "fire", "water", "wind", "earth", "ice", "electric", "bio", "physical", "aether"
]

PRIORITY_SPELL_GRANT_SLOTS: Tuple[str, ...] = (
    "Weapon",
    "Shield",
    "Armor",
    "Top",
    "Accessory", "Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4",
)
MAX_EQUIPPED_RELIC_SPELLS: int = 3

ELIGIBLE_SPELL_GRANT_SLOTS = set(PRIORITY_SPELL_GRANT_SLOTS)

WEARABLE_PASSIVE_SLOTS: Tuple[str, ...] = (
    "Armor", "Top", "Bottom", "Head", "Gloves", "Shoes", "Shield",
)

ELEMENT_STATUS_AILMENTS: Dict[str, str] = {
    "fire": "Burning",
    "water": "Soaked / Slowed",
    "wind": "Disoriented",
    "earth": "Staggered",
    "ice": "Chilled",
    "electric": "Shocked",
    "bio": "Poisoned",
    "physical": "Bleeding",
    "aether": "Cognito-Disrupted",
}

ELEMENT_OPPOSITE_PENALTY: Dict[str, str] = {
    "fire": "water",
    "water": "electric",
    "wind": "earth",
    "earth": "wind",
    "ice": "fire",
    "electric": "earth",
    "bio": "fire",
    "physical": "aether",
    "aether": "electric",
}

MODERN_NON_ANOMALOUS_WEAPON_NAMES: Dict[str, List[str]] = {
    "katana": ["Tactical Carbon Wakizashi", "Containment Steel Katana", "Shrine-Forged Tachi", "Modern Urban Nodachi"],
    "baton": ["Collapsible Alloy Stun-Baton", "Heavy Containment Tonfa", "Telescopic Riot Baton", "High-Impact Enforcer Rod"],
    "dagger": ["Tactical Combat Knife", "Concealed Karambit", "Containment Utility Blade", "Micro-Serrated Trench Knife"],
    "shortsword": ["Tactical Machete", "Urban Close-Quarters Shortblade", "Breaching Gladius", "Heavy Kukri Blade"],
    "sword": ["Modern Tactical Longsword", "Containment Officer Broadsword", "Tempered Steel Arming Blade", "Agency Issue Saber"],
    "cleaver": ["Heavy Butchery Cleaver", "Industrial Bone-Saw Cleaver", "Tactical Breaching Chopper"],
    "axe": ["Tactical Breaching Tomahawk", "Fire-Rescue Crash Axe", "Carbon-Shaft Combat Hatchet"],
    "warhammer": ["Heavy Demolition Sledge", "Reinforced Breaching Ram-Hammer", "Industrial Impact Maul"],
    "spear": ["Collapsible Tactical Pike", "Containment Harpoon Lance", "Carbon-Fiber Boar Spear"],
    "fist_weapon": ["Weighted Tungsten Knuckles", "Reinforced CQC Gauntlets", "Tactical Strike Cestus"],
    "pistol": ["9mm Tactical Service Pistol", "Suppressed Bureau Sidearm", "Compact Polymer Handgun", "Heavy .45 ACP Pistol"],
    "revolver": [".357 Containment Magnum", "Heavy-Frame Six-Shooter", "Custom Bureau Snub-Revolver"],
    "submachinegun": ["Compact Tactical PDW", "Suppressed 9mm Submachine Gun", "Urban Response SMG"],
    "shotgun": ["12-Gauge Tactical Combat Shotgun", "Breaching Pump-Action Shotgun", "Semi-Auto Riot Scattergun"],
    "rifle": ["Bullpup Designated Marksman Rifle", "5.56mm Tactical Containment Carbine", "Anti-Materiel Precision Rifle"],
    "machinegun": ["Squad Automatic Light Machinegun", "Heavy Suppression SAW", "Belt-Fed Containment LMG"],
}

MODERN_NON_ANOMALOUS_ARMOR_NAMES: Dict[str, List[str]] = {
    "clothes": ["Reinforced Urban Field Trenchcoat", "Concealed Weave Street Jacket", "Tailored Agency Field Coat"],
    "magic_robe": ["Lead-Lined Hazmat Field Overcoat", "Insulated Telemetry Trench", "Purified Shrine Vestment Coat"],
    "leather": ["Abrasion-Resistant Motorcycle Jacket", "Reinforced Tactical Softshell Rig", "Urban Recon Leather Harness"],
    "kevlar": ["Concealed Kevlar Ballistic Vest", "Modular Patrol Kevlar Carrier", "Low-Profile Agency Body Armor"],
    "chainmail": ["Stab-Resistant Titanium Mesh Vest", "Interlocked Alloy Slash-Guard Rig", "CQC Riot Mesh Under-Vest"],
    "lamellar": ["Segmented Ballistic Trauma Harness", "Modular Flexible Plate Vest", "Lacquered Shrine Guard Armor"],
    "ceramic": ["Level-IV Ceramic Plate Carrier", "Strike-Team Trauma Plate Rig", "Containment Breacher Chest Rig"],
    "plate": ["Heavy Breaching Tactical Carapace", "Full-Torso Riot Suppression Armor", "Armored Containment Entry Rig"],
    "composite": ["Multi-Threat Composite Trauma Suit", "Heavy EOD Containment Armor", "Reinforced Strike Carapace"],
    "power_armor": ["Powered Hydraulic Containment Exoskeleton", "Heavy Breach Servo-Rig", "Industrial Hazmat Exo-Frame"],
}

MODERN_NON_ANOMALOUS_SHIELD_NAMES: Dict[str, List[str]] = {
    "buckler": ["Forearm Ballistic Deflector", "Compact Alloy CQC Buckler", "Tactical Wrist Guard Plate"],
    "heater_shield": ["Mid-Size Ballistic Entry Shield", "Reinforced Alloy Breaching Shield", "Containment Squad Shield"],
    "tower_shield": ["Full-Body Ballistic Bunker Shield", "Rolling Heavy Breaching Wall", "Mobile Blast Barricade Shield"],
    "riot_shield": ["Polycarbonate Tactical Riot Shield", "Crowd-Control Stun Visor Shield", "Urban Response Riot Shield"],
    "energy_shield": ["Collapsible Ballistic Hard-Shield", "Lightweight Composite Deflector", "Rapid-Deploy Trauma Shield"],
}

MODERN_NON_ANOMALOUS_ACCESSORY_NAMES: Dict[str, List[str]] = {
    "ring": ["Tungsten Agency Signet Ring", "Micro-Transponder Band", "Titanium Field Ring"],
    "amulet": ["Encrypted Clearance Dog-Tags", "Lead-Cased Dosimeter Lanyard", "Braided Paracord ID Medallion"],
    "talisman": ["Calibrated Hume-Meter Clip", "Woven Shrine Omamori Pouch", "Acoustic Frequency Dampener Tag"],
    "bracelet": ["Tactical Chronometer Wristband", "Paracord Survival Wrist-Cuff", "Biometric Vitals Band"],
    "pocket_watch": ["Precision Quartz Field Chronometer", "Stop-Clock Pocket Timer", "Calibrated Transit Watch"],
    "cravat_pin": ["Silver Bureau Lapel Pin", "Enamel Taskforce Tie-Clip", "Subtle Comms Collar Pin"],
    "chatelaine": ["Tactical Carabiner Utility Clip", "Multi-Tool Belt Lanyard", "Quick-Release Mag Retainer"],
    "monocle": ["Clip-On Polarized Tactical Lens", "Ballistic Rangefinder Monocular", "Night-Optic Clip Lens"],
    "choker": ["Throat-Mic Tactical Collar", "Kevlar Neck-Guard Band", "Sub-Vocal Transceiver Band"],
    "belt_buckle": ["Heavy-Duty Rigger Belt Clasp", "Quick-Release Cobra Buckle", "Utility Duty Belt Plate"],
    "neural_jack_plug": ["Encrypted Bone-Conduction Earpiece", "Field Telemetry Earplug", "Noise-Canceling Comms Bud"],
    "holo_badge": ["RFID Security Clearance Badge", "Holographic Bureau Credentials", "Press & Inspector Lanyard"],
    "data_cuff": ["Ruggedized Wrist GPS Terminal", "Field Diagnostics Forearm Cuff", "Tactical Smart-Chronograph"],
}

MODERN_NON_ANOMALOUS_HEAD_NAMES: List[str] = [
    "Ballistic FAST Helmet", "Polarized Tactical Eyewear", "Encrypted Comms Headset", "Low-Profile Recon Cap", "Respirator Half-Mask"
]
MODERN_NON_ANOMALOUS_GLOVES_NAMES: List[str] = [
    "Hard-Knuckle Tactical Gloves", "Kevlar Slash-Resistant Gloves", "Nitrile Forensics Field Gloves", "Padded Marksman Gloves"
]
MODERN_NON_ANOMALOUS_SHOES_NAMES: List[str] = [
    "Steel-Toe Combat Boots", "Side-Zip Tactical Patrol Boots", "Reinforced Urban Trail Sneakers", "All-Weather Breaching Boots"
]

MODERN_NON_ANOMALOUS_PREFIXES: Dict[int, List[str]] = {
    3: ["Standard-Issue", "Field", "Tactical", "Mil-Spec", "Reinforced", "Urban", "Bureau-Grade"],
    2: ["Custom-Calibrated", "Precision", "Heavy-Duty", "Spec-Ops", "Containment-Spec", "Vanguard"],
    1: ["Directorate-Issue", "Masterwork Tactical", "Prototype", "Sovereign-Spec", "Elite Taskforce"],
}

MODERN_NON_ANOMALOUS_SUFFIXES: Dict[int, List[str]] = {
    2: ["Mk.II", "of the Field Agent", "of Urban Response", "of Precision", "of the Vanguard"],
    1: ["Mk.V", "of the Special Division", "of Zero-Tolerance", "of Supreme Containment"],
}

ANOMALOUS_ELEMENT_AFFIXES: Dict[str, Dict[str, List[str]]] = {
    "fire": {
        "prefixes": ["Thermokinetic", "Pyro-Resonant", "Cremation-Sealed", "Ignition-Warped"],
        "suffixes": ["of the Red Ember Anomaly", "of Thermokinetic Purge", "of Searing Resonance"],
    },
    "ice": {
        "prefixes": ["Zero-Kelvin", "Cryo-Anomalous", "Endothermic", "Hoarfrost-Sealed"],
        "suffixes": ["of Absolute Stasis", "of the Frozen Rift", "of Endothermic Lock"],
    },
    "shock": {
        "prefixes": ["Fulminating", "Grid-Warped", "Electro-Anomalous", "Static-Bound"],
        "suffixes": ["of High-Voltage Rupture", "of the Dead-Channel Surge", "of Fulmination"],
    },
    "poison": {
        "prefixes": ["Bio-Aberrant", "Miasma-Laced", "Contagion-Warped", "Venom-Resonant"],
        "suffixes": ["of Cellular Decay", "of the Toxic Spore", "of Bio-Contagion"],
    },
    "holy": {
        "prefixes": ["Ofuda-Consecrated", "Shrine-Relic", "Astral-Sanctified", "Purifying"],
        "suffixes": ["of the Grand Shrine Seal", "of Sacred Exorcism", "of Astral Cleansing"],
    },
    "dark": {
        "prefixes": ["Void-Touched", "Abyssal-Warped", "Non-Euclidean", "Eclipse-Bound"],
        "suffixes": ["of the Hollow Eclipse", "of Event Horizon", "of Abyssal Entropy"],
    },
    "earth": {
        "prefixes": ["Graviton-Weighted", "Lithic-Warped", "Tectonic-Sealed", "Obsidian-Bound"],
        "suffixes": ["of Crushing Gravity", "of the Monolith", "of Seismic Containment"],
    },
    "water": {
        "prefixes": ["Abyssal-Tide", "Hydro-Anomalous", "Deep-Current", "Submerged-Relic"],
        "suffixes": ["of Trench Pressure", "of the Drowned Ward", "of Purification Tides"],
    },
    "wind": {
        "prefixes": ["Vacuum-Shearing", "Kamaitachi-Bound", "Aero-Anomalous", "Vortex-Edged"],
        "suffixes": ["of Atmospheric Shear", "of the Howling Rift", "of Supersonic Gale"],
    },
    "electric": {
        "prefixes": ["Fulminating", "Grid-Warped", "Electro-Anomalous", "Static-Bound"],
        "suffixes": ["of High-Voltage Rupture", "of the Dead-Channel Surge", "of Fulmination"],
    },
    "bio": {
        "prefixes": ["Bio-Aberrant", "Miasma-Laced", "Contagion-Warped", "Spore-Resonant"],
        "suffixes": ["of Cellular Decay", "of the Toxic Spore", "of Bio-Contagion"],
    },
    "physical": {
        "prefixes": ["Kinetic-Amplified", "Hyper-Dense", "Impact-Warped", "Monomolecular"],
        "suffixes": ["of Crushing Vector", "of Trauma Rupture", "of Kinetic Severance"],
    },
    "aether": {
        "prefixes": ["Hume-Warped", "Rift-Consecrated", "Non-Euclidean", "Astral-Sealed"],
        "suffixes": ["of Event Horizon", "of the Hume Singularity", "of Spatial Entropy"],
    },
}


def is_anomalous_scenario(scenario: str) -> bool:
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scenario):
            return True
    except Exception:
        pass
    scen = str(scenario or "").lower().strip()
    return any(k in scen for k in ("anomalous_incursions", "urban_anomalies"))


def choose_anomalous_weapon_archetype() -> str:
    """Strictly 50% Melee / 50% Ranged modern weapon archetype selection."""
    if random.random() < 0.50:
        return random.choice(ANOMALOUS_MELEE_ARCHETYPES)
    return random.choice(ANOMALOUS_RANGED_ARCHETYPES)


def roll_is_anomalous_gear(
    tier: int = 3,
    tier_5_scale: Optional[int] = None,
    private_agency_bonus: bool = False,
) -> bool:
    """
    Rolls whether a piece of gear in Anomalous Incursions receives the 'anomalous' tag.
    Supports both 5-tier scale (T1: 10%, T2: 25%, T3: 45%, T4: 75%, T5: 100%)
    and Hikayat's 3-tier scale (Tier 3 Standard: 20%, Tier 2 Superior: 50%, Tier 1 Relic: 100%).
    """
    if tier_5_scale is not None and tier_5_scale in (1, 2, 3, 4, 5):
        chance_map_5 = {1: 0.10, 2: 0.25, 3: 0.45, 4: 0.75, 5: 1.00}
        chance = chance_map_5[tier_5_scale]
    else:
        chance_map_3 = {3: 0.20, 2: 0.50, 1: 1.00}
        chance = chance_map_3.get(int(tier or 3), 0.20)
    if private_agency_bonus:
        chance = min(1.0, chance + 0.20)
    return random.random() < chance


def _strip_elemental_properties(metadata: Dict[str, Any]) -> None:
    """Strips all fantasy elemental conversions, resistances, and tags from non-anomalous gear."""
    stat_mods = metadata.get("stat_modifiers")
    if isinstance(stat_mods, dict):
        keys_to_remove = [
            k for k in stat_mods
            if k.endswith("_convert")
            or k.endswith("_atk")
            or (k.endswith("_res") and k not in ("physical_res", "ballistic_res", "explosive_res"))
            or k in ("magic_dt", "omni_res", "armor_penetration")
        ]
        for k in keys_to_remove:
            stat_mods.pop(k, None)

    for top_k in (
        "element", "elem_convert_type", "elem_convert_pct", "granted_spell", "granted_spell_id",
        "omni_res", "holy_res", "dark_res", "shock_res", "energy_res", "poison_res", "ice_res",
        "fire_res", "earth_res", "water_res", "wind_res", "electric_res", "bio_res", "aether_res",
        "magic_dt", "anomalous_passives", "is_cursed_relic", "cursed_drawback",
    ):
        metadata.pop(top_k, None)
    metadata["is_anomalous"] = False

    # Keep only realistic kinetic/ballistic/explosive type_dt entries
    keep_dt = {
        "physical", "ballistic", "explosive", "slashing", "stabbing", "blunt",
        "pistol_round", "rifle_round", "scatter_shot", "high_caliber_round", "arrow", "bolt",
    }
    if isinstance(metadata.get("type_dt"), dict):
        metadata["type_dt"] = {
            k: v for k, v in metadata["type_dt"].items() if k in keep_dt
        }

    # Reset weapon damage types to strictly physical or ballistic
    if metadata.get("item_type") == "Weapon":
        arch = str(metadata.get("archetype") or "").lower()
        is_ranged = arch in ANOMALOUS_RANGED_ARCHETYPES or "ranged" in (metadata.get("attack_types") or [])
        base_dmg_key = "ballistic" if is_ranged else "physical"
        metadata["damage_types"] = {base_dmg_key: 1.0}
        profiles = metadata.get("attack_profiles")
        if isinstance(profiles, dict):
            for p_k, p_v in profiles.items():
                if isinstance(p_v, dict):
                    p_v["damage_type"] = base_dmg_key

    # Clean protection_types on Armor
    if "protection_types" in metadata and isinstance(metadata["protection_types"], list):
        metadata["protection_types"] = [
            p for p in metadata["protection_types"]
            if p in ("physical", "ballistic", "explosive", "slashing", "stabbing", "blunt")
        ] or ["physical", "ballistic"]

    # Clean tags
    tags = metadata.get("tags")
    if isinstance(tags, dict):
        if "special_traits" in tags and isinstance(tags["special_traits"], list):
            tags["special_traits"] = [
                t for t in tags["special_traits"]
                if t != "elemental" and not str(t).startswith("elem_") and t != "anomalous"
            ]
        if "damage_types" in tags and isinstance(tags["damage_types"], list):
            tags["damage_types"] = [
                t for t in tags["damage_types"]
                if t in ("physical", "ballistic", "explosive")
            ] or ["physical"]
        if "protection_types" in tags and isinstance(tags["protection_types"], list):
            tags["protection_types"] = [
                p for p in tags["protection_types"]
                if p in ("physical", "ballistic", "explosive", "slashing", "stabbing", "blunt")
            ] or ["physical", "ballistic"]
        if "stat_bonuses" in tags and isinstance(tags["stat_bonuses"], list):
            tags["stat_bonuses"] = [
                b for b in tags["stat_bonuses"]
                if not (
                    str(b).endswith("_convert")
                    or str(b).endswith("_atk")
                    or (str(b).endswith("_res") and str(b) not in ("physical_res", "ballistic_res", "explosive_res"))
                    or str(b) in ("magic_dt", "omni_res", "armor_penetration")
                )
            ]
    elif isinstance(tags, list):
        metadata["tags"] = [
            t for t in tags
            if t != "elemental" and not str(t).startswith("elem_") and t != "anomalous"
            and t not in ANOMALOUS_ELEMENTS
        ]


def _roll_wearable_passives_and_curses(
    metadata: Dict[str, Any],
    slot: str,
    tier: int,
    elem: str,
    force_cursed: Optional[bool] = None,
) -> None:
    """
    Rolls 1-2 Anomalous Passive Traits (`elemental_amp`, `turn_regen`/`combat_buff`, `on_hit_debuff`)
    and a ~25% Cursed/Volatile Relic trade-off on Tier 1-2 Anomalous Wearables
    (`Armor`, `Top`, `Bottom`, `Head`, `Gloves`, `Shoes`, `Shield`).
    """
    stat_mods = metadata.setdefault("stat_modifiers", {})
    is_cursed = (
        bool(force_cursed)
        if force_cursed is not None
        else (tier in (1, 2) and random.random() < 0.25)
    )
    curse_mult = 1.5 if is_cursed else 1.0

    base_amp = 0.10 if tier == 3 else (0.18 if tier == 2 else 0.25)
    amp_pct = round(base_amp * curse_mult, 2)
    trait_amp = {
        "category": "elemental_amp",
        "element": elem,
        "amp_pct": amp_pct,
        "tier": tier,
        "label": f"+{int(round(amp_pct * 100))}% {elem.title()} Damage Amplification",
    }

    base_regen = 0.02 if tier == 3 else (0.03 if tier == 2 else 0.04)
    regen_pct = round(base_regen * curse_mult, 3)
    buff_val = int(round((6 if tier == 3 else (10 if tier == 2 else 14)) * curse_mult))
    if slot in ("Armor", "Top", "Head"):
        trait_buff = {
            "category": "turn_regen",
            "regen_type": "hp_mp",
            "regen_pct": regen_pct,
            "tier": tier,
            "label": f"Regenerates {int(round(regen_pct * 100))}% Max HP/MP per turn",
        }
    else:
        buff_name = "Phase-Step Ward" if slot in ("Shoes", "Bottom") else "Tactical Resonance Ward"
        stat_target = "EVA" if slot in ("Shoes", "Bottom") else "ACC"
        trait_buff = {
            "category": "combat_buff",
            "buff_name": buff_name,
            "stat_target": stat_target,
            "bonus_val": buff_val,
            "tier": tier,
            "label": f"{buff_name} (+{buff_val}% {stat_target})",
        }

    ailment = ELEMENT_STATUS_AILMENTS.get(elem, "Staggered")
    base_proc = 0.15 if tier == 3 else (0.22 if tier == 2 else 0.30)
    proc_chance = min(0.45, round(base_proc * curse_mult, 2))
    trait_debuff = {
        "category": "on_hit_debuff",
        "element": elem,
        "ailment": ailment,
        "proc_chance": proc_chance,
        "tier": tier,
        "label": f"{int(round(proc_chance * 100))}% chance to inflict {ailment} on hit/retaliation",
    }

    candidate_traits = [trait_amp, trait_buff, trait_debuff]
    num_traits = 1 if tier == 3 else 2
    chosen_traits = random.sample(candidate_traits, num_traits)
    metadata["anomalous_passives"] = chosen_traits

    if is_cursed:
        opp_elem = ELEMENT_OPPOSITE_PENALTY.get(elem, "aether")
        pen_pct = 20 if tier == 2 else 25
        hp_drain = 2 if tier == 2 else 3
        metadata["is_cursed_relic"] = True
        metadata["cursed_drawback"] = {
            "element": opp_elem,
            "res_penalty_pct": pen_pct,
            "hp_drain_per_turn": hp_drain,
            "label": f"Cursed Relic: -{pen_pct}% {opp_elem.title()} Res & -{hp_drain} HP/turn",
        }
        metadata["anomalous_curse"] = metadata["cursed_drawback"]
        stat_mods[f"{opp_elem}_res"] = stat_mods.get(f"{opp_elem}_res", 0) - pen_pct
    else:
        metadata["is_cursed_relic"] = False
        metadata.pop("cursed_drawback", None)
        metadata.pop("anomalous_curse", None)


def _inject_anomalous_properties(
    metadata: Dict[str, Any],
    slot: str,
    tier: int,
    element: Optional[str] = None,
    force_granted_spell: Optional[bool] = None,
    force_cursed: Optional[bool] = None,
) -> None:
    """
    Infuses an item with the 'anomalous' tag and one of the 9 canonical elements (`ANOMALOUS_ELEMENTS`):
    - Weapons & Accessories (`Weapon`, `Accessory 1..4`): Exclusive slots for temporary active abilities
      (`granted_spell`) with tier-scaled grant rates (T3: 50%, T2: 75%, T1: 100%).
    - Wearables (`Armor`, `Top`, `Bottom`, `Head`, `Gloves`, `Shoes`, `Shield`): Never grant active spells;
      instead receive base Elemental Res/DT + 1-2 Anomalous Passive Traits + ~25% Cursed Relic trade-off on T1-T2.
    """
    elem = element if element in ANOMALOUS_ELEMENTS else random.choice(ANOMALOUS_ELEMENTS)
    metadata["is_anomalous"] = True
    metadata["element"] = elem
    metadata["anomalous_element"] = elem

    tags = metadata.get("tags")
    if isinstance(tags, dict):
        traits = tags.setdefault("special_traits", [])
        for t in ("anomalous", "elemental", f"elem_{elem}", elem):
            if t not in traits:
                traits.append(t)
    elif isinstance(tags, list):
        for t in ("anomalous", "elemental", f"elem_{elem}", elem):
            if t not in tags:
                tags.append(t)
    else:
        metadata["tags"] = ["anomalous", "elemental", f"elem_{elem}", elem]

    stat_mods = metadata.setdefault("stat_modifiers", {})
    item_type = str(metadata.get("item_type") or slot or "Weapon")
    check_slot = str(slot or metadata.get("slot") or item_type)

    is_weapon_slot = (item_type == "Weapon" or check_slot == "Weapon")
    is_accessory_slot = (
        check_slot == "Accessory"
        or check_slot.startswith("Accessory")
        or item_type == "Accessory"
    )
    is_eligible_spell_slot = is_weapon_slot or is_accessory_slot

    if is_weapon_slot:
        arch = str(metadata.get("archetype") or "").lower()
        is_ranged = arch in ANOMALOUS_RANGED_ARCHETYPES or "ranged" in (metadata.get("attack_types") or [])
        base_dmg_key = "ballistic" if is_ranged else "physical"
        conv_pct = 0.50 if tier == 1 else (0.40 if tier == 2 else 0.30)
        metadata["elem_convert_type"] = elem
        metadata["elem_convert_pct"] = conv_pct
        metadata["damage_types"] = {base_dmg_key: round(1.0 - conv_pct, 2), elem: conv_pct}
        stat_mods[f"{elem}_convert"] = conv_pct
        profiles = metadata.get("attack_profiles")
        if isinstance(profiles, dict):
            for p_k, p_v in profiles.items():
                if isinstance(p_v, dict):
                    p_v["damage_type"] = elem
        metadata.pop("anomalous_passives", None)
        metadata.pop("is_cursed_relic", None)
        metadata.pop("cursed_drawback", None)
    else:
        res_bonus = 35 if tier == 1 else (25 if tier == 2 else 15)
        dt_bonus = 16 if tier == 1 else (10 if tier == 2 else 6)
        stat_mods[f"{elem}_res"] = max(stat_mods.get(f"{elem}_res", 0), res_bonus)
        if elem == "electric":
            stat_mods["shock_res"] = max(stat_mods.get("shock_res", 0), res_bonus)
        elif elem == "bio":
            stat_mods["poison_res"] = max(stat_mods.get("poison_res", 0), res_bonus)
        type_dt = metadata.setdefault("type_dt", {})
        if isinstance(type_dt, dict):
            type_dt[elem] = type_dt.get(elem, 0) + dt_bonus
        prots = metadata.setdefault("protection_types", ["physical"])
        if isinstance(prots, list) and elem not in prots:
            prots.append(elem)

        if not is_accessory_slot:
            # Wearable slot: roll Anomalous Passive Traits & Curses, and never grant active spells
            metadata.pop("granted_spell", None)
            metadata.pop("granted_spell_id", None)
            _roll_wearable_passives_and_curses(
                metadata=metadata,
                slot=check_slot,
                tier=tier,
                elem=elem,
                force_cursed=force_cursed,
            )

    if is_eligible_spell_slot:
        grant_chance_by_tier = {1: 1.00, 2: 0.75, 3: 0.50}
        tier_chance = grant_chance_by_tier.get(int(tier or 3), 0.50)
        should_grant = (
            force_granted_spell
            if force_granted_spell is not None
            else (random.random() < tier_chance)
        )
        if should_grant:
            from mechanics.combat.spells.procedural import generate_procedural_spell
            from mechanics.combat.spells.registry import register_spell

            slot_role = "weapon" if is_weapon_slot else "accessory"
            proc_spell = generate_procedural_spell(
                scenario="anomalous_incursions",
                tier=tier if tier in (1, 2, 3) else 3,
                element=elem,
                slot_role=slot_role,
            )
            proc_spell["is_equipment_granted"] = True
            proc_spell["source_element"] = elem
            register_spell(proc_spell)
            metadata["granted_spell"] = proc_spell
            metadata["granted_spell_id"] = proc_spell["id"]
        else:
            metadata.pop("granted_spell", None)
            metadata.pop("granted_spell_id", None)


def apply_anomalous_incursions_gear_rules(
    item: Dict[str, Any],
    scenario: str,
    slot: str = "Weapon",
    tier: int = 3,
    tier_5_scale: Optional[int] = None,
    private_agency_bonus: bool = False,
    force_anomalous: Optional[bool] = None,
    force_granted_spell: Optional[bool] = None,
    force_cursed: Optional[bool] = None,
    element: Optional[str] = None,
    rng_seed: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Applies Anomalous Incursions gear rules to a generated equipment item dict.
    No-op if scenario is not Anomalous Incursions.
    """
    if not item or not isinstance(item, dict) or not is_anomalous_scenario(scenario):
        return item

    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return item

    item_tier = int(metadata.get("tier") or tier or 3)
    actual_slot = str(item.get("slot") or metadata.get("slot") or slot or "Weapon")
    item_type = str(item.get("item_type") or metadata.get("item_type") or "Weapon")

    is_anom = (
        force_anomalous
        if force_anomalous is not None
        else roll_is_anomalous_gear(tier=item_tier, tier_5_scale=tier_5_scale, private_agency_bonus=private_agency_bonus)
    )

    arch = str(metadata.get("archetype") or "").lower()
    if item_type == "Weapon" and arch in MODERN_NON_ANOMALOUS_WEAPON_NAMES:
        base_name = random.choice(MODERN_NON_ANOMALOUS_WEAPON_NAMES[arch])
    elif (item_type == "Shield" or actual_slot == "Shield") and arch in MODERN_NON_ANOMALOUS_SHIELD_NAMES:
        base_name = random.choice(MODERN_NON_ANOMALOUS_SHIELD_NAMES[arch])
    elif (item_type == "Armor" or actual_slot in ("Armor", "Top")) and arch in MODERN_NON_ANOMALOUS_ARMOR_NAMES:
        base_name = random.choice(MODERN_NON_ANOMALOUS_ARMOR_NAMES[arch])
    elif (item_type == "Accessory" or actual_slot.startswith("Accessory")) and arch in MODERN_NON_ANOMALOUS_ACCESSORY_NAMES:
        base_name = random.choice(MODERN_NON_ANOMALOUS_ACCESSORY_NAMES[arch])
    elif actual_slot == "Head":
        base_name = random.choice(MODERN_NON_ANOMALOUS_HEAD_NAMES)
    elif actual_slot == "Gloves":
        base_name = random.choice(MODERN_NON_ANOMALOUS_GLOVES_NAMES)
    elif actual_slot == "Shoes":
        base_name = random.choice(MODERN_NON_ANOMALOUS_SHOES_NAMES)
    else:
        # Clean any medieval/fantasy prefix from base_name if needed
        base_name = str(metadata.get("name") or item.get("name") or arch.replace("_", " ").title())
        for old_p in ("Iron ", "Steel ", "Runic ", "Mithril ", "Dragon-Forged ", "Sunfire ", "Apprentice's ", "Woven ", "Enchanted "):
            if base_name.startswith(old_p):
                base_name = base_name[len(old_p):]

    if is_anom:
        elem = element or metadata.get("element")
        if elem not in ANOMALOUS_ELEMENTS:
            elem = random.choice(ANOMALOUS_ELEMENTS)
        _inject_anomalous_properties(
            metadata,
            slot=actual_slot,
            tier=item_tier,
            element=elem,
            force_granted_spell=force_granted_spell,
            force_cursed=force_cursed,
        )
        affix_info = ANOMALOUS_ELEMENT_AFFIXES.get(elem, ANOMALOUS_ELEMENT_AFFIXES["aether"])
        prefix = random.choice(affix_info["prefixes"])
        suffix = random.choice(affix_info["suffixes"])
        if item_tier == 3:
            new_name = f"[Anomalous] {prefix} {base_name}"
        else:
            new_name = f"[Anomalous] {prefix} {base_name} {suffix}"
    else:
        _strip_elemental_properties(metadata)
        p_pool = MODERN_NON_ANOMALOUS_PREFIXES.get(item_tier, MODERN_NON_ANOMALOUS_PREFIXES[3])
        prefix = random.choice(p_pool)
        if item_tier == 3:
            new_name = f"{prefix} {base_name}"
        else:
            s_pool = MODERN_NON_ANOMALOUS_SUFFIXES.get(item_tier, MODERN_NON_ANOMALOUS_SUFFIXES[2])
            suffix = random.choice(s_pool)
            new_name = f"{prefix} {base_name} {suffix}"

    metadata["name"] = new_name
    item["name"] = new_name

    # Append granted spell or wearable passive/curse description if present
    granted_sp = metadata.get("granted_spell")
    passives = metadata.get("anomalous_passives")
    cursed_db = metadata.get("cursed_drawback")
    if isinstance(granted_sp, dict) and granted_sp.get("name"):
        sp_badge = f"✨ Grants Ability (While Equipped): {granted_sp['name']} ({granted_sp.get('mp_cost', 10)} MP)"
        metadata["description"] = sp_badge
        item["description"] = sp_badge
    elif isinstance(passives, list) and passives:
        p_labels = [str(p.get("label") or "") for p in passives if isinstance(p, dict) and p.get("label")]
        badge_txt = "🛡️ Anomalous Passives: " + " • ".join(p_labels)
        if isinstance(cursed_db, dict) and cursed_db.get("label"):
            badge_txt += f" • ⚠️ {cursed_db['label']}"
        metadata["description"] = badge_txt
        item["description"] = badge_txt

    # Re-serialize effect string
    raw_eff = str(item.get("effect") or "")
    if raw_eff.startswith("[GEAR_JSON]"):
        item["effect"] = f"[GEAR_JSON]{json.dumps(metadata)}"
    else:
        item["effect"] = serialize_item(metadata)
    item["metadata"] = metadata
    return item


def aggregate_equipped_anomalous_passives(equipment_or_uid: Any) -> Dict[str, Any]:
    """
    Aggregates all equipped `[Anomalous]` wearable passives and cursed relic trade-offs
    across all wearable slots (`Armor`, `Top`, `Bottom`, `Head`, `Gloves`, `Shoes`, `Shield`),
    enforcing strict multi-slot stacking caps:
    - Elemental Resistance (`elemental_res_pct`): Additive per element, hard-capped at 75% (min -50% with curses).
    - Elemental Amplification (`elemental_amp`): Additive per element, hard-capped at +60% (0.60).
    - On-Hit / Reactive Debuff Procs (`on_hit_debuffs`): Additive per ailment, hard-capped at 45% (0.45).
    - Per-Turn Regeneration (`turn_regen_pct`): Additive, hard-capped at 8% Max HP / Max MP per turn (0.08).
    - Named Combat Buffs (`named_buffs`): Only the highest-tier instance of the same `buff_name` applies.
    - Cursed Drawbacks (`cursed_hp_drain_per_turn`, `cursed_res_penalties`): Always stack additively.
    """
    import db
    from mechanics.combat.equipment import parse_equipment_metadata

    if isinstance(equipment_or_uid, int):
        eq_map = db.get_equipment(equipment_or_uid) or {}
        items = [v for v in eq_map.values() if isinstance(v, dict)]
    elif isinstance(equipment_or_uid, dict):
        items = [v for v in equipment_or_uid.values() if isinstance(v, dict)]
    elif isinstance(equipment_or_uid, list):
        items = [v for v in equipment_or_uid if isinstance(v, dict)]
    else:
        items = []

    raw_res: Dict[str, int] = {e: 0 for e in ANOMALOUS_ELEMENTS}
    raw_amp: Dict[str, float] = {e: 0.0 for e in ANOMALOUS_ELEMENTS}
    raw_debuffs: Dict[str, Dict[str, Any]] = {}
    raw_regen_pct: float = 0.0
    named_buffs: Dict[str, Dict[str, Any]] = {}
    cursed_hp_drain: int = 0
    cursed_res_penalties: Dict[str, int] = {}
    cursed_count: int = 0

    for itm in items:
        meta = parse_equipment_metadata(itm) or {}
        if not meta.get("is_anomalous"):
            continue
        stat_mods = meta.get("stat_modifiers") if isinstance(meta.get("stat_modifiers"), dict) else {}
        for elem in ANOMALOUS_ELEMENTS:
            r_val = int(stat_mods.get(f"{elem}_res", 0) or 0)
            if r_val > 0:
                raw_res[elem] += r_val

        for p in (meta.get("anomalous_passives") or []):
            if not isinstance(p, dict):
                continue
            cat = str(p.get("category") or "")
            if cat == "elemental_amp":
                el = str(p.get("element") or meta.get("element") or "aether")
                if el in raw_amp:
                    raw_amp[el] = round(raw_amp[el] + float(p.get("amp_pct", 0.0) or 0.0), 3)
            elif cat == "turn_regen":
                raw_regen_pct = round(raw_regen_pct + float(p.get("regen_pct", 0.0) or 0.0), 4)
            elif cat == "combat_buff":
                b_name = str(p.get("buff_name") or "Anomalous Ward")
                b_val = int(p.get("bonus_val", 0) or 0)
                prev = named_buffs.get(b_name)
                if not prev or b_val > int(prev.get("bonus_val", 0) or 0):
                    named_buffs[b_name] = dict(p)
            elif cat == "on_hit_debuff":
                ail = str(p.get("ailment") or "Staggered")
                chance = float(p.get("proc_chance", 0.0) or 0.0)
                if ail not in raw_debuffs:
                    raw_debuffs[ail] = {
                        "ailment": ail,
                        "status": ail,
                        "element": str(p.get("element") or meta.get("element") or "aether"),
                        "proc_chance": min(0.45, round(chance, 3)),
                        "chance": min(0.45, round(chance, 3)),
                    }
                else:
                    new_ch = min(0.45, round(raw_debuffs[ail]["proc_chance"] + chance, 3))
                    raw_debuffs[ail]["proc_chance"] = new_ch
                    raw_debuffs[ail]["chance"] = new_ch

        if meta.get("is_cursed_relic") and isinstance(meta.get("cursed_drawback"), dict):
            cursed_count += 1
            cdb = meta["cursed_drawback"]
            cursed_hp_drain += int(cdb.get("hp_drain_per_turn", 0) or 0)
            c_el = str(cdb.get("element") or "")
            c_pen = int(cdb.get("res_penalty_pct", 0) or 0)
            if c_el and c_pen > 0:
                cursed_res_penalties[c_el] = cursed_res_penalties.get(c_el, 0) + c_pen

    # Apply caps: 75% Elemental Res (minus additive curse penalties), +60% Elemental Amp, 8% Turn Regen
    capped_res: Dict[str, int] = {}
    for elem in ANOMALOUS_ELEMENTS:
        base_capped = min(75, raw_res.get(elem, 0))
        net_res = base_capped - cursed_res_penalties.get(elem, 0)
        if net_res != 0:
            capped_res[elem] = max(-50, min(75, net_res))

    capped_amp: Dict[str, float] = {
        elem: min(0.60, round(val, 2))
        for elem, val in raw_amp.items()
        if val > 0
    }
    capped_regen_pct = min(0.08, round(raw_regen_pct, 3))

    bonus_eva = sum(int(b.get("bonus_val", 0)) for b in named_buffs.values() if b.get("stat_target") == "EVA")
    bonus_acc = sum(int(b.get("bonus_val", 0)) for b in named_buffs.values() if b.get("stat_target") == "ACC")

    return {
        "elemental_res_pct": capped_res,
        "elemental_res": {k: round(v / 100.0, 2) for k, v in capped_res.items()},
        "elemental_amp": capped_amp,
        "on_hit_debuffs": list(raw_debuffs.values()),
        "turn_regen_pct": capped_regen_pct,
        "named_buffs": named_buffs,
        "bonus_eva": bonus_eva,
        "bonus_acc": bonus_acc,
        "cursed_relic_count": cursed_count,
        "cursed_hp_drain_per_turn": cursed_hp_drain,
        "cursed_res_penalties": cursed_res_penalties,
    }


def convert_object_anomaly_to_gear(
    blueprint: Dict[str, Any],
    tier: int = 2,
    scenario: str = "anomalous_incursions",
) -> Dict[str, Any]:
    """
    Converts a secured or neutralized Anomalous Object (`type == "object"`) into a usable
    `[Anomalous]` Weapon, Accessory, or Wearable matching the object's form and primary element.
    Canonical Folklore Codex objects (`codex_id` / `relic_gear_profile`) always convert into
    100% deterministic relics (identical slot, stats, element, and granted spell at equal tier).
    """
    from mechanics.combat.items import generate_random_equipment

    bp_dict = blueprint if isinstance(blueprint, dict) else {}
    relic_profile = bp_dict.get("relic_gear_profile") if isinstance(bp_dict.get("relic_gear_profile"), dict) else {}
    codex_id = str(bp_dict.get("codex_id") or "").strip()

    form = str(bp_dict.get("form") or "impossible_weapon_relic")
    elem = str(relic_profile.get("element") or bp_dict.get("primary_element") or bp_dict.get("element") or "aether")
    if elem not in ANOMALOUS_ELEMENTS:
        elem = "aether"
    bp_tier = bp_dict.get("tier_rank") or bp_dict.get("tier")
    item_tier = max(1, min(3, int(bp_tier or tier or 2)))

    bp_name_low = str(bp_dict.get("name") or "").lower()
    if relic_profile.get("slot"):
        target_slot = str(relic_profile["slot"])
    elif form in ("impossible_weapon_relic", "cursed_weapon", "weapon"):
        target_slot = "Weapon"
    elif form in (
        "possessed_media_device",
        "sealed_apothecary_vessel",
        "endless_book_scroll",
        "clockwork_astrolabe",
    ):
        target_slot = "Accessory 1"
    elif form == "cursed_garment_mask":
        target_slot = (
            "Armor"
            if any(k in bp_name_low for k in ("coat", "robe", "cloak", "kimono", "jacket"))
            else "Head"
        )
    elif form == "anomalous_vending_kiosk":
        target_slot = "Shield"
    elif form in ("haunted_furniture", "architectural_fixture"):
        target_slot = "Shield" if "mirror" in bp_name_low else "Armor"
    elif form == "cursed_vehicle":
        target_slot = "Shoes"
    else:
        target_slot = "Accessory 1"

    weapon_arch = str(relic_profile.get("weapon_archetype") or "").strip() or None
    force_cursed: Optional[bool] = (
        bool(relic_profile["is_cursed"])
        if "is_cursed" in relic_profile
        else (False if codex_id else None)
    )

    saved_rng_state = random.getstate() if codex_id else None
    try:
        if codex_id:
            random.seed(f"folklore_relic:{codex_id}:{item_tier}:{scenario}")
        base_eq = generate_random_equipment(
            scenario=scenario,
            slot=target_slot,
            tier=item_tier,
            archetype=weapon_arch if target_slot == "Weapon" else None,
        )
        anom_eq = apply_anomalous_incursions_gear_rules(
            base_eq,
            scenario=scenario,
            slot=target_slot,
            tier=item_tier,
            force_anomalous=True,
            force_granted_spell=True if target_slot in ("Weapon", "Accessory 1") else False,
            force_cursed=force_cursed,
            element=elem,
        )
    finally:
        if saved_rng_state is not None:
            random.setstate(saved_rng_state)

    bp_name = str(
        relic_profile.get("display_name")
        or bp_dict.get("canonical_name")
        or bp_dict.get("name")
        or "Anomalous Relic"
    ).strip()
    if bp_name.lower().startswith("the "):
        bp_name = bp_name[4:].strip()
    # Truncate the base name BEFORE wrapping so the "(Element Relic)" suffix is never cut mid-parenthesis
    relic_suffix = f" ({elem.title()} Relic)"
    max_bp_len = max(8, 65 - len("[Anomalous] ") - len(relic_suffix))
    if len(bp_name) > max_bp_len:
        bp_name = bp_name[:max_bp_len].rstrip(" -,'")
    custom_name = f"[Anomalous] {bp_name}{relic_suffix}"
    anom_eq["name"] = custom_name
    meta = anom_eq.get("metadata")
    if isinstance(meta, dict):
        meta["name"] = custom_name
        meta["origin_blueprint_id"] = bp_dict.get("blueprint_id", "")
        meta["origin_anomaly_type"] = bp_dict.get("type", "object")
        meta["origin_anomaly_form"] = form
        if codex_id:
            meta["codex_id"] = codex_id
            meta["is_canonical_folklore_relic"] = True
        anom_eq["effect"] = serialize_item(meta)
        anom_eq["metadata"] = meta
    return anom_eq


def sync_equipped_anomalous_spells(user_id: int, *, raise_on_error: bool = False) -> Dict[str, Any]:
    """
    Synchronizes equipment-granted spells with the character's active learned_spells list.
    - Iterates strictly in priority slot order (Weapon > Shield > Armor/Top > Accessory 1..4).
    - Caps active non-innate Relic bonus skills at MAX_EQUIPPED_RELIC_SPELLS (3) to fit 8-slot UI decks.
    - Preserves duplicate +20% empowerment across all eligible slots without mutating shared SPELL_REGISTRY.
    """
    import db
    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.spells.registry import (
        SPELL_REGISTRY,
        get_spell,
        register_spell,
        set_active_empowered_spells_context,
    )

    char = db.get_character(user_id)
    if not char:
        return {"active_granted_spells": [], "empowered_spells": []}

    equipment = db.get_equipment(user_id) or {}
    progress = db.get_skill_progress(char)
    prev_granted_only: List[str] = list(progress.get("equipped_granted_spells") or [])
    innate_spells: List[str] = list(progress.get("innate_spells") or [])

    from scenario_data import is_anomalous_incursions_scenario
    scen_val = str(char.get("scenario") or "")
    has_anom_relic = any(
        isinstance(eq_v, dict) and (
            (parse_equipment_metadata(eq_v) or {}).get("granted_spell_id")
            or (parse_equipment_metadata(eq_v) or {}).get("granted_spell")
        )
        for eq_v in equipment.values()
    )
    is_anom_char = (
        is_anomalous_incursions_scenario(scen_val)
        or bool(char.get("attribute") or char.get("combat_archetype") or char.get("ability_medium"))
        or bool(prev_granted_only)
        or any(str(s).startswith(("awk_", "anom_")) for s in innate_spells)
        or has_anom_relic
    )
    if not is_anom_char:
        sess_id = char.get("active_session_id")
        sess_obj = db.get_session(sess_id) if sess_id else None
        if not sess_obj or not is_anomalous_incursions_scenario(str(sess_obj.get("scenario") or "")):
            set_active_empowered_spells_context([])
            return {"active_granted_spells": [], "empowered_spells": []}

    current_spells = list(db.get_learned_spells(user_id) or [])
    if not innate_spells:
        innate_spells = [s for s in current_spells if s not in prev_granted_only]
        progress["innate_spells"] = innate_spells

    ordered_slots: List[str] = [s for s in PRIORITY_SPELL_GRANT_SLOTS if s in equipment]
    for extra_slot in sorted(equipment.keys()):
        if extra_slot not in ordered_slots:
            ordered_slots.append(extra_slot)

    ordered_grant_ids: List[str] = []
    grant_counts: Dict[str, int] = {}
    grant_defs: Dict[str, Dict[str, Any]] = {}

    for slot in ordered_slots:
        eq_item = equipment.get(slot)
        if not eq_item or not isinstance(eq_item, dict):
            continue
        if slot in ("Head", "Gloves", "Shoes", "Bottom"):
            continue
        meta = parse_equipment_metadata(eq_item) or {}
        g_spell = meta.get("granted_spell")
        g_id = meta.get("granted_spell_id") or (g_spell.get("id") if isinstance(g_spell, dict) else None)
        if g_id:
            if g_id not in grant_counts:
                ordered_grant_ids.append(g_id)
            grant_counts[g_id] = grant_counts.get(g_id, 0) + 1
            if isinstance(g_spell, dict):
                grant_defs[g_id] = g_spell

    active_relic_ids: List[str] = []
    for g_id in ordered_grant_ids:
        if g_id in innate_spells:
            continue
        if len(active_relic_ids) < MAX_EQUIPPED_RELIC_SPELLS:
            active_relic_ids.append(g_id)

    # Ensure clean base definitions in SPELL_REGISTRY (never mutating duplicate_empowered globally)
    for g_id in ordered_grant_ids:
        sp_def = grant_defs.get(g_id) or SPELL_REGISTRY.get(g_id) or get_spell(g_id)
        if isinstance(sp_def, dict):
            sp_clean = copy.deepcopy(sp_def)
            sp_clean["duplicate_empowered"] = False
            register_spell(sp_clean)

    empowered_ids: List[str] = []
    for g_id in ordered_grant_ids:
        count = grant_counts.get(g_id, 0)
        is_active = (g_id in active_relic_ids) or (g_id in innate_spells)
        is_dup = count >= 2 or (count >= 1 and g_id in innate_spells)
        if is_active and is_dup:
            empowered_ids.append(g_id)

    updated_spells: List[str] = [
        s for s in current_spells
        if s not in prev_granted_only or s in innate_spells
    ]
    for g_id in active_relic_ids:
        if g_id not in updated_spells:
            updated_spells.append(g_id)

    progress["equipped_granted_spells"] = active_relic_ids
    progress["empowered_granted_spells"] = empowered_ids
    db.set_skill_progress(user_id, progress)
    db.set_learned_spells(user_id, updated_spells)
    set_active_empowered_spells_context(empowered_ids)

    return {
        "active_granted_spells": active_relic_ids,
        "empowered_spells": empowered_ids,
        "learned_spells": updated_spells,
    }


_STARTER_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "anomalous_starter_classes.json"


@lru_cache(maxsize=1)
def load_anomalous_starter_classes_catalog() -> Dict[str, Any]:
    """Loads the static Layer-1 Anomalous Incursions starter classes, weapons, and outfit catalogs from JSON."""
    raw = json.loads(_STARTER_CATALOG_PATH.read_text(encoding="utf-8"))
    raw_outfits = raw.get("faction_starter_outfits") or {}
    parsed_outfits: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
        fac: {
            slot: [(str(pair[0]), str(pair[1])) for pair in pairs if isinstance(pair, (list, tuple)) and len(pair) >= 2]
            for slot, pairs in slot_map.items()
            if isinstance(pairs, list)
        }
        for fac, slot_map in raw_outfits.items()
        if isinstance(slot_map, dict)
    }
    return {
        "faction_classes": raw.get("faction_classes") or {},
        "faction_weapons": raw.get("faction_weapons") or {},
        "faction_starter_outfits": parsed_outfits,
    }


def load_anomalous_starter_classes() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Returns a deep copy of the 6-faction Anomalous Incursions starter class catalog."""
    return copy.deepcopy(load_anomalous_starter_classes_catalog()["faction_classes"])


ANOMALOUS_FACTION_CLASSES: Dict[str, Dict[str, Dict[str, Any]]] = copy.deepcopy(load_anomalous_starter_classes_catalog()["faction_classes"])
ANOMALOUS_FACTION_WEAPONS: Dict[str, List[str]] = copy.deepcopy(load_anomalous_starter_classes_catalog()["faction_weapons"])
ANOMALOUS_FACTION_STARTER_OUTFITS: Dict[str, Dict[str, List[Tuple[str, str]]]] = copy.deepcopy(load_anomalous_starter_classes_catalog()["faction_starter_outfits"])

def normalize_anomalous_starting_faction(starting_faction: Optional[str]) -> str:
    fac = str(starting_faction or "public_agency").strip().lower()
    if fac in ("student_freelancer", "student", "student_operative", "high_school_student"):
        return "student_freelancer"
    if fac in ("private_agency", "private_agency_1", "private_1"):
        return "private_agency_1"
    if fac in ("private_agency_2", "private_2"):
        return "private_agency_2"
    if fac in ("monastic_order", "monastic", "shrine", "exorcist"):
        return "monastic_order"
    if fac in ("freelancer", "independent", "none", "leave"):
        return "freelancer"
    return "public_agency"


def apply_anomalous_faction_starter_theme(
    loadout: Dict[str, Any],
    scenario: str,
    starting_faction: Optional[str] = "public_agency",
    gender: str = "Male",
    race: str = "Human",
    char_class: Optional[str] = None,
    starting_weapon: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Themes non-weapon starter equipment in Anomalous Incursions to match the player's
    selected Starting Faction Affiliation (Public Agency, Private Agency, Monastic Order, or Freelancer),
    while preserving procedural GEAR_JSON stats, [Anomalous] elemental affixes, granted spells, and tail slots.
    """
    if not loadout or not isinstance(loadout, dict) or not is_anomalous_scenario(scenario):
        return loadout

    from character_data import is_tailed_race

    norm_fac = normalize_anomalous_starting_faction(
        starting_faction or infer_anomalous_faction_from_class(char_class) or "public_agency"
    )
    outfit_key = norm_fac
    pool_map = ANOMALOUS_FACTION_STARTER_OUTFITS.get(outfit_key, ANOMALOUS_FACTION_STARTER_OUTFITS["public_agency"])

    is_male = str(gender or "").strip().lower() == "male"
    is_female = str(gender or "").strip().lower() == "female"
    has_tail = is_tailed_race(race)

    # Theme / verify starting Weapon for faction (including random faction weapon rerolls when starting_weapon is omitted)
    w_item = loadout.get("Weapon")
    if isinstance(w_item, dict):
        w_meta = w_item.get("metadata") if isinstance(w_item.get("metadata"), dict) else {}
        w_name = str(w_item.get("name") or "")
        fac_weapons = ANOMALOUS_FACTION_WEAPONS.get(norm_fac, ANOMALOUS_FACTION_WEAPONS["public_agency"])
        
        target_weapon_name = None
        if starting_weapon and starting_weapon.strip():
            target_weapon_name = starting_weapon.strip()
        else:
            clean_curr = w_name.replace("[Anomalous]", "").strip()
            is_matching = any(fw in clean_curr for fw in fac_weapons)
            if not is_matching:
                target_weapon_name = random.choice(fac_weapons)
                    
        if target_weapon_name and (target_weapon_name not in w_name or "is_anomalous" not in w_meta):
            from mechanics.combat.items.weapons import generate_random_equipment as _gen_w
            w_tier = int(w_meta.get("tier") or 3)
            orig_desc = str(w_item.get("description") or w_item.get("desc") or "")
            new_w = _gen_w(scenario=scenario, slot="Weapon", tier=w_tier, name=target_weapon_name)
            if orig_desc and any(c in orig_desc.lower() for c in ("bag", "duffle", "case", "tome", "tube", "sleeve", "hollow", "conceal")):
                if "description" in new_w and new_w["description"]:
                    new_w["description"] = f"{new_w['description']} ({orig_desc})"
                else:
                    new_w["desc"] = f"{new_w.get('desc', '')} ({orig_desc})".strip()
            loadout["Weapon"] = new_w
        elif "is_anomalous" not in w_meta:
            loadout["Weapon"] = apply_anomalous_incursions_gear_rules(
                w_item,
                scenario=scenario,
                slot="Weapon",
                tier=int(w_meta.get("tier") or 3),
            )

    for slot, item in list(loadout.items()):
        if not isinstance(item, dict) or slot == "Weapon":
            continue
        meta_pre = item.get("metadata")
        if isinstance(meta_pre, dict) and "is_anomalous" not in meta_pre:
            item = apply_anomalous_incursions_gear_rules(
                item,
                scenario=scenario,
                slot=slot,
                tier=int(meta_pre.get("tier") or 3),
            )
            loadout[slot] = item
        slot_lookup = "Accessory 1" if slot.startswith("Accessory") and slot not in pool_map else slot
        choices = pool_map.get(slot_lookup)
        if not choices:
            continue

        raw_name, flavor_desc = random.choice(choices)
        if " / " in raw_name:
            parts = [p.strip() for p in raw_name.split(" / ")]
            if len(parts) == 2:
                raw_name = parts[0] if is_female and not is_male else parts[1]

        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        is_anom = bool(meta.get("is_anomalous"))
        elem = str(meta.get("element") or "")

        if is_anom and elem in ANOMALOUS_ELEMENT_AFFIXES:
            affix_info = ANOMALOUS_ELEMENT_AFFIXES[elem]
            prefix = random.choice(affix_info["prefixes"])
            final_name = f"[Anomalous] {prefix} {raw_name}"
        else:
            final_name = raw_name

        if has_tail and slot in ("Bottom", "Armor") and "tail" not in final_name.lower():
            final_name = f"Tail-Slotted {final_name}"
            if meta:
                flags = meta.setdefault("social_flags", [])
                if "tail_slotted" not in flags:
                    flags.append("tail_slotted")

        granted_sp = meta.get("granted_spell") if meta else None
        passives = meta.get("anomalous_passives") if meta else None
        cursed_db = meta.get("cursed_drawback") if meta else None
        if isinstance(granted_sp, dict) and granted_sp.get("name"):
            final_desc = f"{flavor_desc} • ✨ Grants Ability (While Equipped): {granted_sp['name']} ({granted_sp.get('mp_cost', 10)} MP)"
        elif isinstance(passives, list) and passives:
            p_labels = [str(p.get("label") or "") for p in passives if isinstance(p, dict) and p.get("label")]
            badge_txt = "🛡️ Anomalous Passives: " + " • ".join(p_labels)
            if isinstance(cursed_db, dict) and cursed_db.get("label"):
                badge_txt += f" • ⚠️ {cursed_db['label']}"
            final_desc = f"{flavor_desc} • {badge_txt}"
        else:
            final_desc = flavor_desc

        item["name"] = final_name
        item["description"] = final_desc
        if meta:
            meta["name"] = final_name
            meta["description"] = final_desc
            raw_eff = str(item.get("effect") or "")
            if raw_eff.startswith("[GEAR_JSON]"):
                item["effect"] = f"[GEAR_JSON]{json.dumps(meta)}"
            else:
                item["effect"] = serialize_item(meta)
            item["metadata"] = meta

    return loadout


_LEGACY_ANOMALOUS_CLASS_FACTIONS: Dict[str, str] = {
    "corporate strike operator": "private_agency_1",
    "in-house r&d prototype tester": "private_agency_1",
    "executive containment specialist": "private_agency_1",
    "proprietary telemetry marksman": "private_agency_1",
    "corporate aegis heavy vanguard": "private_agency_1",
    "contract trouble-shooter": "private_agency_2",
    "surplus ordnance breacher": "private_agency_2",
    "storefront case investigator": "private_agency_2",
    "aftermarket ward tinkerer": "private_agency_2",
    "hired-gun perimeter guard": "private_agency_2",
}


def infer_anomalous_faction_from_class(char_class: Optional[str]) -> Optional[str]:
    """Returns the canonical faction archetype key if `char_class` belongs to one of the 5 Anomalous factions."""
    if not char_class:
        return None
    target = str(char_class).strip().lower()
    for fac_key, cls_map in ANOMALOUS_FACTION_CLASSES.items():
        for cls_name in cls_map:
            if cls_name.lower() == target:
                return fac_key
    return _LEGACY_ANOMALOUS_CLASS_FACTIONS.get(target)


def get_anomalous_faction_starting_items(
    scenario: str = "anomalous_incursions",
    starting_faction: Optional[str] = "public_agency",
) -> List[Tuple[str, str, str, int]]:
    """
    Generates usable serialized Anomalous Incursions starting consumables
    (Trauma Medkit, Cognitive Stabilizer Ampoule, plus a faction-specific tactical ration).
    """
    from mechanics.combat.items.consumables.generators import generate_procedural_potion

    norm_fac = normalize_anomalous_starting_faction(starting_faction)
    medkit = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="anomalous_incursions")
    stabilizer = generate_procedural_potion(tier=3, effect_tags=["mana_restore"], genre="anomalous_incursions")

    if norm_fac == "private_agency_1":
        medkit["name"] = "VitaSeal Nano-Trauma Auto-Injector"
        stabilizer["name"] = "NeuroCalm Cognitive Ampoule"
    elif norm_fac == "private_agency_2":
        medkit["name"] = "Compact Trauma First-Aid Kit"
        stabilizer["name"] = "Concentrated Neural Focus Ampoule"
    elif norm_fac == "monastic_order":
        medkit["name"] = "Field-Issue Trauma Medkit"
        stabilizer["name"] = "Shrine-Blessed Spirit-Calming Incense"
    elif norm_fac == "student_freelancer":
        medkit["name"] = "Concealed First-Aid Pouch"
        stabilizer["name"] = "Resonance Suppressant Lozenge"
    else:
        medkit["name"] = "Field-Issue Trauma Medkit"
        stabilizer["name"] = "Containment-Grade Cognitive Stabilizer Ampoule"

    items: List[Tuple[str, str, str, int]] = [
        (medkit["name"], medkit["item_type"], medkit["effect"], 1),
        (stabilizer["name"], stabilizer["item_type"], stabilizer["effect"], 1),
    ]

    if norm_fac == "monastic_order":
        salt = generate_procedural_potion(tier=3, effect_tags=["cleanse_all"], genre="anomalous_incursions")
        salt["name"] = "Sacred Purging Salt Pouch"
        items.append((salt["name"], salt["item_type"], salt["effect"], 1))
    elif norm_fac == "private_agency_1":
        booster = generate_procedural_potion(tier=3, effect_tags=["attack_buff"], genre="anomalous_incursions")
        booster["name"] = "VX-II Adrenal Stim-Injector"
        items.append((booster["name"], booster["item_type"], booster["effect"], 1))
    elif norm_fac == "private_agency_2":
        booster = generate_procedural_potion(tier=3, effect_tags=["attack_buff"], genre="anomalous_incursions")
        booster["name"] = "High-Potency Adrenal Recovery Shot"
        items.append((booster["name"], booster["item_type"], booster["effect"], 1))
    elif norm_fac == "public_agency":
        purge = generate_procedural_potion(tier=3, effect_tags=["cleanse_all"], genre="anomalous_incursions")
        purge["name"] = "Class-A Amnestic & Cognito Purge"
        items.append((purge["name"], purge["item_type"], purge["effect"], 1))
    elif norm_fac == "student_freelancer":
        melon = generate_procedural_potion(tier=3, effect_tags=["defense_buff"], genre="anomalous_incursions")
        melon["name"] = "Cafeteria Melon Bread Ration"
        items.append((melon["name"], melon["item_type"], melon["effect"], 1))
    else:
        patch = generate_procedural_potion(tier=3, effect_tags=["defense_buff"], genre="anomalous_incursions")
        patch["name"] = "Street-Grade Hume-Stabilizer Patch"
        items.append((patch["name"], patch["item_type"], patch["effect"], 1))

    return items

def get_anomalous_faction_classes(starting_faction: Optional[str] = "public_agency") -> Dict[str, Dict[str, Any]]:
    norm_fac = normalize_anomalous_starting_faction(starting_faction)
    return copy.deepcopy(ANOMALOUS_FACTION_CLASSES.get(norm_fac, ANOMALOUS_FACTION_CLASSES["public_agency"]))


def get_all_anomalous_faction_classes() -> Dict[str, Dict[str, Any]]:
    all_classes: Dict[str, Dict[str, Any]] = {}
    for f_classes in ANOMALOUS_FACTION_CLASSES.values():
        all_classes.update(copy.deepcopy(f_classes))
    return all_classes


def get_anomalous_faction_weapons(starting_faction: Optional[str] = "public_agency") -> List[str]:
    norm_fac = normalize_anomalous_starting_faction(starting_faction)
    return list(ANOMALOUS_FACTION_WEAPONS.get(norm_fac, ANOMALOUS_FACTION_WEAPONS["public_agency"]))
