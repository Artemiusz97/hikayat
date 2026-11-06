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


def sync_equipped_anomalous_spells(user_id: int) -> Dict[str, Any]:
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

    set_active_empowered_spells_context(empowered_ids)
    progress["equipped_granted_spells"] = active_relic_ids
    progress["empowered_granted_spells"] = empowered_ids
    db.set_skill_progress(user_id, progress)
    db.set_learned_spells(user_id, updated_spells)

    return {
        "active_granted_spells": active_relic_ids,
        "empowered_spells": empowered_ids,
        "learned_spells": updated_spells,
    }


ANOMALOUS_FACTION_CLASSES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "public_agency": {
        "Public Safety Field Hunter": {
            "description": "High-mobility tactical operative trained in close-quarters anomaly interception, rapid breaching, and lethal entity suppression.",
            "starting_items": [
                ["Field Trauma Kit", "Consumable", "Rapid-application coagulant and adrenaline injector.", 1],
                ["Flashbang Grenade", "Consumable", "High-intensity disorienting charge.", 1],
            ],
            "starter_gear": {
                "Head": ["Tactical Balaclava & Comms", "Fire-retardant headwear with radio earpiece.", 1],
                "Weapon": ["Tactical Suppression Shotgun", "Short-barreled pump-action shotgun loaded with heavy slug rounds.", 2],
                "Armor": ["Standard-Issue Containment Plate Carrier", "Modular bureau chest rig with lead-lined evidence pouches.", 3],
                "Top": ["Reinforced Bureau Combat Shirt", "Durable dark tactical utility wear.", 1],
                "Bottom": ["Reinforced Cargo Trousers", "Ripstop tactical trousers with knee-pad inserts.", 2],
                "Gloves": ["Tactical Grip Gloves", "Non-slip leather gloves with carbon-fiber knuckle guards.", 1],
                "Shoes": ["Bureau Rapid-Response Field Boots", "Matte-black tactical boots built for subway tunnels and wet concrete.", 1],
                "Shield": None,
            },
        },
        "Bureau Forensic Investigator": {
            "description": "Specialized forensics agent using electronic resonance scanners and occult analysis to track, catalogue, and contain spatial distortions.",
            "starting_items": [
                ["Sub-Harmonic Resonance Scanner", "Tool", "Handheld sensor registering spatial distortions and abnormal frequencies.", 2],
                ["Sealed Evidence Canisters", "Tool", "Lead-lined canisters for hazardous anomalous residues.", 1],
            ],
            "starter_gear": {
                "Head": ["Spectral Optical Visor", "Tactical polarized glasses detecting unnatural luminescence and light bends.", 1],
                "Weapon": ["Bureau Issue Service Pistol", "Standard 9mm duty pistol with precision barrel rifling.", 2],
                "Armor": ["Concealed Bureau Kevlar Vest", "Taxpayer-funded low-profile ballistic vest worn beneath agency attire.", 2],
                "Top": ["Dark Trenchcoat & Tie", "Professional bureau field suit with occult-dampening lining.", 2],
                "Bottom": ["Tailored Field Slacks", "Reinforced charcoal slacks suited for active investigation.", 1],
                "Gloves": ["Nitrile-Lined Leather Gloves", "Insulated gloves preventing contact contamination.", 1],
                "Shoes": ["Polished Field Oxfords", "Reinforced rubber-soled leather shoes.", 1],
                "Shield": None,
            },
        },
        "Quarantine Containment Engineer": {
            "description": "Heavy hazmat and containment specialist equipped with spatial anchoring tools, suppression foam, and reality barrier emitters.",
            "starting_items": [
                ["Emergency Ward Pylon", "Tool", "Deployable tripod emitter establishing a temporary spatial stability zone.", 2],
                ["Pressurized Suppression Foam", "Consumable", "Aerosol canister spraying fast-hardening anomalous barrier foam.", 1],
            ],
            "starter_gear": {
                "Head": ["Hazmat Respirator Helmet", "Full-face positive pressure respirator with filtered air intake.", 2],
                "Weapon": ["Arc-Discharge Stun Baton", "Heavy telescoping baton delivering pulsed electromagnetic shock.", 2],
                "Armor": ["Insulated Hazmat Exosuit", "Heavy hermetically sealed hazard containment suit.", 4],
                "Top": ["Rubberized Utility Overalls", "Chemical and tear-resistant protective workwear.", 2],
                "Bottom": ["Reinforced Hazmat Trousers", "Heavy insulated overalls with radiation-reflective layering.", 2],
                "Gloves": ["Heavy Insulated Gauntlets", "Thick rubber-and-kevlar gloves protecting against energy discharge.", 2],
                "Shoes": ["Hazard Chemical Boots", "Heavy vulcanized rubber boots with puncture-proof soles.", 2],
                "Shield": None,
            },
        },
        "Occult Precision Marksman": {
            "description": "Precision suppression marksman neutralizing anomalous vectors from overwatch perches with talisman-inscribed ballistic ammunition.",
            "starting_items": [
                ["Runic Precision Monocular", "Tool", "Compact spotter scope revealing ethereal silhouettes through smoke and walls.", 2],
                ["Consecrated Silver Magazine", "Consumable", "Extended magazine packed with silver-cored ammunition.", 2],
            ],
            "starter_gear": {
                "Head": ["Tactical Ballistic Cap", "Low-profile cap with integrated comms clip.", 1],
                "Weapon": ["Suppressed Scout Carbine", "Compact semi-automatic rifle equipped with a specialized sound and flash suppressor.", 3],
                "Armor": ["Modular Plate Carrier", "Lightweight ballistic vest allowing unrestricted arm movement.", 2],
                "Top": ["Weather-Resistant Windbreaker", "Dark matte windbreaker masking thermal signature.", 1],
                "Bottom": ["Weatherproof Utility Trousers", "Water-repellent combat trousers with zippered pockets.", 1],
                "Gloves": ["Shooter Grip Gloves", "Precision shooting gloves with tactile index finger pads.", 1],
                "Shoes": ["All-Terrain Field Boots", "Silent tread boots providing stable footing on damp concrete.", 1],
                "Shield": None,
            },
        },
        "Bureau Aegis Esper": {
            "description": "Regulated psychic liaison channeling sanctioned mental barriers and kinetic disruption fields under strict containment oversight.",
            "starting_items": [
                ["Cognitive Stabilizer Ampoule", "Consumable", "Fast-acting neuro-sedative dampening psychological terror.", 1],
                ["Bureau Mental Dampener Ring", "Tool", "Electromagnetic ring providing resistance to mental incursions.", 2],
            ],
            "starter_gear": {
                "Head": ["Polarized Cognito-Filter Glasses", "Bureau-issue anti-memetic eyewear filtering anomalous visual noise.", 1],
                "Weapon": ["Kinetic Force Baton", "Reinforced alloy baton weighted with kinetic force-damping coils.", 2],
                "Armor": ["Bureau Ballistic Trench Under-Rig", "Reinforced weave harness designed for rapid urban containment.", 2],
                "Top": ["Bureau Field Inspector Blazer", "Structured dark blazer bearing a concealed municipal clearance pin.", 1],
                "Bottom": ["Tailored Charcoal Bureau Slacks", "Reinforced wool-blend agency slacks tailored for active pursuit.", 1],
                "Gloves": ["Tactile Trigger-Guard Gauntlets", "Precision contractor gloves engineered for recoil control.", 1],
                "Shoes": ["Polished Steel-Toe Agency Oxfords", "Dress oxfords concealing puncture-resistant soles and ankle support.", 1],
                "Shield": None,
            },
        },
    },
    "private_agency_1": {
        "Corporate Strike Operator": {
            "description": "Elite conglomerate assault operative clad in proprietary composite armor, clearing high-rise breach floors with serialized in-house smart carbines.",
            "starting_items": [
                ["Proprietary Combat Stim-Injector", "Consumable", "In-house R&D synthetic adrenaline restoring stamina and pain tolerance.", 1],
                ["Corporate Shaped Breaching Charge", "Consumable", "Cleanroom-engineered directional charge designed to breach sealed vaults.", 1],
            ],
            "starter_gear": {
                "Head": ["Proprietary Mk.III AR Telemetry Visor", "In-house corporate R&D heads-up visor streaming live skyscraper threat telemetry.", 1],
                "Weapon": ["In-House Mk.IV Smart Carbine", "Proprietary gas-piston smart rifle developed in corporate R&D labs with HUD target-lock.", 3],
                "Armor": ["In-House R&D Composite Plate Rig", "Proprietary corporate ceramic-polymer chest rig engineered in the conglomerate's cleanrooms.", 3],
                "Top": ["In-House Matte-Carbon Operator Shirt", "Proprietary breathable ballistic-shoulder combat shirt issued exclusively to conglomerate staff.", 1],
                "Bottom": ["Proprietary Operator Cargo Trousers", "Articulated corporate R&D ripstop trousers with integrated magnetic holster mounts.", 2],
                "Gloves": ["In-House Smart-Link Operator Gloves", "Proprietary synthetic gloves syncing weapon grip sensors to corporate HUDs.", 1],
                "Shoes": ["Proprietary Shock-Damped Assault Boots", "Lightweight in-house composite boots built for high-rise corporate deployments.", 1],
                "Shield": None,
            },
        },
        "In-House R&D Prototype Tester": {
            "description": "Corporate weapons-division specialist field-testing unreleased directed-pulse shotguns, cleanroom stasis emitters, and patented exo-weave gear.",
            "starting_items": [
                ["Patented Stasis Capacitor Cell", "Tool", "Proprietary R&D power cell overcharging experimental corporate equipment.", 2],
                ["In-House Resonance Null-Grenade", "Consumable", "Corporate prototype pulse charge collapsing localized anomalous fields.", 1],
            ],
            "starter_gear": {
                "Head": ["Corporate R&D Ballistic Half-Mask", "Sleek proprietary matte-carbon respirator developed in-house for tower breaches.", 1],
                "Weapon": ["Corporate Prototype Pulse Shotgun", "Experimental directed-energy scattergun built in-house by conglomerate ordnance engineers.", 3],
                "Armor": ["Proprietary Corporate Exo-Weave Vest", "Serialized conglomerate tactical vest with magnetic smart-mag caddies.", 3],
                "Top": ["Corporate R&D Tactical Techwear Coat", "Asymmetric matte-black corporate shell bearing embossed conglomerate R&D serials.", 2],
                "Bottom": ["Proprietary Operator Cargo Trousers", "Articulated corporate R&D ripstop trousers with integrated magnetic holster mounts.", 2],
                "Gloves": ["Corporate Carbon-Knuckle Gauntlets", "Serialized R&D contractor gloves engineered for zero-slip recoil control.", 1],
                "Shoes": ["Corporate Silent-Tread Tech High-Tops", "Custom R&D urban striders with sound-deadening polymer soles.", 1],
                "Shield": None,
            },
        },
        "Executive Containment Specialist": {
            "description": "High-clearance corporate bio-containment agent deploying bespoke ballisticweave tailoring and proprietary monomolecular blades to secure high-margin assets.",
            "starting_items": [
                ["Corporate Cryo-Specimen Capsule", "Tool", "Patented cleanroom containment cylinder for high-value anomalous cores.", 2],
                ["Proprietary Optical Cloak Clip", "Tool", "In-house micro-refraction badge bending light across executive attire.", 2],
            ],
            "starter_gear": {
                "Head": ["In-House Carbon-Weave Comms Headset", "Serialized corporate headset with encrypted satellite R&D uplink.", 1],
                "Weapon": ["Proprietary R&D Monomolecular Katana", "Laser-honed alloy katana forged in corporate cleanrooms to shear anomalous chitin.", 2],
                "Armor": ["Executive Ballisticweave Tech-Duster", "Bespoke corporate longcoat woven in-house with flexible aramid-nanotube panels.", 3],
                "Top": ["Executive Security Tailored Blazer", "Bespoke high-collar corporate suit jacket engineered in-house for concealed carry.", 2],
                "Bottom": ["Corporate Aramid-Stitched Executive Slacks", "Tailored conglomerate combat slacks woven from proprietary slash-proof fibers.", 1],
                "Gloves": ["In-House Smart-Link Operator Gloves", "Proprietary synthetic gloves syncing weapon grip sensors to corporate HUDs.", 1],
                "Shoes": ["Corporate Silent-Tread Tech High-Tops", "Custom R&D urban striders with sound-deadening polymer soles.", 1],
                "Shield": None,
            },
        },
        "Proprietary Telemetry Marksman": {
            "description": "Skyscraper overwatch sharpshooter linked to corporate satellite telemetry, neutralizing high-threat entities with in-house gauss precision rifles.",
            "starting_items": [
                ["Corporate Telemetry Uplink Beacon", "Tool", "Proprietary micro-dart feeding live target vectors to the conglomerate satellite grid.", 2],
                ["In-House Sub-Zero Sabot Magazine", "Consumable", "Patented corporate cryo-jacketed rounds chilling anomalies on impact.", 1],
            ],
            "starter_gear": {
                "Head": ["Proprietary Mk.III AR Telemetry Visor", "In-house corporate R&D heads-up visor streaming live skyscraper threat telemetry.", 1],
                "Weapon": ["Corporate R&D Gauss Precision Rifle", "Long-range electromagnetic coil-assisted marksman rifle engineered in-house.", 3],
                "Armor": ["In-House R&D Composite Plate Rig", "Proprietary corporate ceramic-polymer chest rig engineered in the conglomerate's cleanrooms.", 3],
                "Top": ["In-House Matte-Carbon Operator Shirt", "Proprietary breathable ballistic-shoulder combat shirt issued exclusively to conglomerate staff.", 1],
                "Bottom": ["Corporate Aramid-Stitched Executive Slacks", "Tailored conglomerate combat slacks woven from proprietary slash-proof fibers.", 1],
                "Gloves": ["Corporate Carbon-Knuckle Gauntlets", "Serialized R&D contractor gloves engineered for zero-slip recoil control.", 1],
                "Shoes": ["Proprietary Shock-Damped Assault Boots", "Lightweight in-house composite boots built for high-rise corporate deployments.", 1],
                "Shield": None,
            },
        },
        "Corporate Aegis Heavy Vanguard": {
            "description": "Heavily funded corporate frontline tank wearing proprietary exo-weave armor and crushing breach swarms with kinetic R&D hammers and alloy shields.",
            "starting_items": [
                ["In-House Nanite Plate Sealant", "Consumable", "Patented corporate aerosol rapidly bonding micro-fractures in composite armor.", 2],
                ["Corporate Acoustic Stun Charge", "Consumable", "Serialized high-decibel flash-concussion canister.", 1],
            ],
            "starter_gear": {
                "Head": ["Corporate R&D Ballistic Half-Mask", "Sleek proprietary matte-carbon respirator developed in-house for tower breaches.", 1],
                "Weapon": ["In-House Kinetic Breaching Sledgehammer", "Proprietary corporate maul fitted with internal piezo-kinetic impact amplifiers.", 3],
                "Armor": ["Proprietary Corporate Exo-Weave Vest", "Serialized conglomerate tactical vest with magnetic smart-mag caddies.", 4],
                "Top": ["Corporate R&D Tactical Techwear Coat", "Asymmetric matte-black corporate shell bearing embossed conglomerate R&D serials.", 2],
                "Bottom": ["Proprietary Operator Cargo Trousers", "Articulated corporate R&D ripstop trousers with integrated magnetic holster mounts.", 2],
                "Gloves": ["Corporate Carbon-Knuckle Gauntlets", "Serialized R&D contractor gloves engineered for zero-slip recoil control.", 1],
                "Shoes": ["Proprietary Shock-Damped Assault Boots", "Lightweight in-house composite boots built for high-rise corporate deployments.", 1],
                "Shield": ["In-House Alloy Breaching Shield", "Proprietary ballistic entry barrier fabricated in the corporation's metallurgy division.", 2],
            },
        },
    },
    "private_agency_2": {
        "Contract Trouble-Shooter": {
            "description": "Working-stiff local agency contractor making rent with a dependable pawn-shop carbine, mismatched surplus Kevlar, and off-the-shelf hardware.",
            "starting_items": [
                ["Hardware-Store Halogen Flashlight", "Tool", "Heavy D-cell aluminum work light taped with a red cellophane filter.", 1],
                ["Bulk-Box Road Flare & Rock Salt", "Consumable", "Cheap highway flare stuffed with coarse salt to rattle minor entities.", 1],
            ],
            "starter_gear": {
                "Head": ["Secondhand Two-Way Radio Headset", "Discount commercial walkie-talkie headset bought in bulk from an electronics liquidator.", 1],
                "Weapon": ["Pawn-Shop Semi-Auto Carbine", "Scuffed civilian sporting carbine fitted with an aftermarket flashlight mount.", 2],
                "Armor": ["Mismatched Surplus Kevlar Vest", "Retired security-firm ballistic vest with mismatched Velcro pouches from three different vendors.", 2],
                "Top": ["Off-the-Rack Utility Windbreaker", "Plain commercial nylon windbreaker with a small iron-on local agency patch.", 1],
                "Bottom": ["Hardware-Store Reinforced Cargo Pants", "Durable off-the-shelf workwear trousers stuffed with spare batteries, receipts, and chalk.", 1],
                "Gloves": ["Hardware-Store Impact Work Gloves", "Bright-stitched mechanic's grip gloves picked up on sale down the street.", 1],
                "Shoes": ["Discount Steel-Toe Work Boots", "Practical warehouse safety boots with oil-resistant rubber soles.", 1],
                "Shield": None,
            },
        },
        "Surplus Ordnance Breacher": {
            "description": "Pragmatic point-man clearing cramped commercial basements in discount plate carriers with a secondhand riot shotgun and crowbar.",
            "starting_items": [
                ["Hardware-Store Prybar & Bolt Cutters", "Tool", "Well-oiled steel entry tools bought off the shelf for rusted cellar padlocks.", 1],
                ["Surplus Riot Smoke Canister", "Consumable", "Aging municipal-auction smoke grenade that still pops reliably enough.", 1],
            ],
            "starter_gear": {
                "Head": ["Surplus Riot Bump-Helmet", "Scuffed municipal auction helmet with a handwritten agency asset sticker on the back.", 1],
                "Weapon": ["Secondhand Riot Pump-Shotgun", "Retired police-turn-in 12-gauge pump shotgun with a scratched wooden stock.", 2],
                "Armor": ["Discount Commercial Plate Carrier", "Budget mail-order nylon carrier fitted with heavy steel aftermarket trauma plates.", 3],
                "Top": ["Worn Commercial Canvas Work Jacket", "Sturdy hardware-store duck-canvas jacket smelling faintly of gun oil and burnt drip coffee.", 2],
                "Bottom": ["Hardware-Store Reinforced Cargo Pants", "Durable off-the-shelf workwear trousers stuffed with spare batteries, receipts, and chalk.", 1],
                "Gloves": ["Duct-Taped Surplus Leather Gloves", "Broken-in military surplus gloves reinforced across the knuckles with silver gaffer tape.", 1],
                "Shoes": ["Broken-In Surplus Patrol Boots", "Resoled police-surplus leather boots kept watertight with cheap shoe grease.", 1],
                "Shield": None,
            },
        },
        "Storefront Case Investigator": {
            "description": "Shoe-leather paranormal detective working out of a commercial walk-up office with a police trade-in revolver, Polaroid camera, and mail-order EMF meter.",
            "starting_items": [
                ["Mail-Order Third-Party EMF Meter", "Tool", "Plastic hobbyist ghost-hunting meter rewired at the office bench to track real rifts.", 1],
                ["Thrift-Shop Instant Film Camera", "Tool", "Clunky analog camera that catches spectral silhouettes digital phone sensors miss.", 1],
            ],
            "starter_gear": {
                "Head": ["Off-the-Shelf Clip-On Polarized Glasses", "Drugstore polarized clip-ons taped over safety frames to cut anomalous glare.", 1],
                "Weapon": ["Police Trade-In .38 Service Revolver", "Reliable six-shot surplus service revolver with worn checkered grip panels.", 2],
                "Armor": ["Patched Mall-Security Soft-Armor", "Secondhand Kevlar under-vest neatly stitched and duct-taped at the office patching corner.", 2],
                "Top": ["Thrifted Wrinkled Office Trenchcoat", "Sensible department-store raincoat worn over a short-sleeved button-down shirt.", 1],
                "Bottom": ["Scuffed Office Slacks with Knee Pads", "Ordinary commercial dress slacks paired with strap-on hardware-store knee pads.", 1],
                "Gloves": ["Duct-Taped Surplus Leather Gloves", "Broken-in military surplus gloves reinforced across the knuckles with silver gaffer tape.", 1],
                "Shoes": ["Broken-In Surplus Patrol Boots", "Resoled police-surplus leather boots kept watertight with cheap shoe grease.", 1],
                "Shield": None,
            },
        },
        "Aftermarket Ward Tinkerer": {
            "description": "Resourceful small-agency tech cobbling working containment rigs out of used oscilloscopes, car batteries, and whatever third-party parts are on sale.",
            "starting_items": [
                ["Solder-Patched Grounding Coil", "Tool", "Homemade copper-pipe grounding rod wired to a scooter battery.", 2],
                ["Mason-Jar Salt & Iron Shrapnel Pop", "Consumable", "Improvised back-room flash-ward taped together from hardware supplies.", 1],
            ],
            "starter_gear": {
                "Head": ["Off-the-Shelf Clip-On Polarized Glasses", "Drugstore polarized clip-ons taped over safety frames to cut anomalous glare.", 1],
                "Weapon": ["Surplus Imported 9mm Submachinegun", "Boxy cold-war surplus SMG sourced through a licensed third-party broker.", 2],
                "Armor": ["Mismatched Surplus Kevlar Vest", "Retired security-firm ballistic vest with mismatched Velcro pouches from three different vendors.", 2],
                "Top": ["Worn Commercial Canvas Work Jacket", "Sturdy hardware-store duck-canvas jacket smelling faintly of gun oil and burnt drip coffee.", 2],
                "Bottom": ["Hardware-Store Reinforced Cargo Pants", "Durable off-the-shelf workwear trousers stuffed with spare batteries, receipts, and chalk.", 1],
                "Gloves": ["Hardware-Store Impact Work Gloves", "Bright-stitched mechanic's grip gloves picked up on sale down the street.", 1],
                "Shoes": ["Discount Steel-Toe Work Boots", "Practical warehouse safety boots with oil-resistant rubber soles.", 1],
                "Shield": None,
            },
        },
        "Hired-Gun Perimeter Guard": {
            "description": "Steady small-agency muscle holding the line in patched surplus armor with a scratched polycarbonate riot shield and hardware-store sledgehammer.",
            "starting_items": [
                ["Roll of Heavy Silver Duct Tape", "Tool", "Fixes cracked riot visors, torn vest straps, and loose cellar door seals in seconds.", 1],
                ["Pharmacy Cold-Pack & Smelling Salts", "Consumable", "Over-the-counter ammonia snap-caps to shake off psychic grogginess.", 1],
            ],
            "starter_gear": {
                "Head": ["Surplus Riot Bump-Helmet", "Scuffed municipal auction helmet with a handwritten agency asset sticker on the back.", 1],
                "Weapon": ["Hardware-Modified Breaching Sledgehammer", "Fiberglass-handled demolition hammer welded with iron ward-washers in the cellar.", 2],
                "Armor": ["Discount Commercial Plate Carrier", "Budget mail-order nylon carrier fitted with heavy steel aftermarket trauma plates.", 3],
                "Top": ["Off-the-Rack Utility Windbreaker", "Plain commercial nylon windbreaker with a small iron-on local agency patch.", 1],
                "Bottom": ["Scuffed Office Slacks with Knee Pads", "Ordinary commercial dress slacks paired with strap-on hardware-store knee pads.", 1],
                "Gloves": ["Hardware-Store Impact Work Gloves", "Bright-stitched mechanic's grip gloves picked up on sale down the street.", 1],
                "Shoes": ["Discount Steel-Toe Work Boots", "Practical warehouse safety boots with oil-resistant rubber soles.", 1],
                "Shield": ["Scratched Surplus Polycarbonate Shield", "Retired crowd-control riot shield with the previous department's stenciling painted over.", 2],
            },
        },
    },
    "monastic_order": {
        "Shrine Exorcist Ascetic": {
            "description": "Consecrated warrior-monk wielding sanctified polearms and spirit-binding seals to banish and cleanse incursions.",
            "starting_items": [
                ["Consecrated Salt Pouch", "Consumable", "Blessed sea salt scattering spiritual corruption and staggering entities.", 1],
                ["Purification Paper Talisman (Ofuda)", "Tool", "Inscribed paper seal disrupting anomalous energy fields.", 2],
            ],
            "starter_gear": {
                "Head": ["Braided Shimenawa Headband", "Sacred hemp headband consecrated with mountain shrine incense.", 1],
                "Weapon": ["Purifying Shrine Naginata", "Curved polearm blade folded from sanctified steel and dipped in shrine waters.", 3],
                "Armor": ["Ofuda-Lined Lacquered Do-Maru Vest", "Traditional lamellar chest protector woven with warding talismans.", 3],
                "Top": ["Consecrated Indigo Shrine Haori", "Flowing exorcist coat embroidered with silver bell-flower crests.", 2],
                "Bottom": ["Pleated Exorcist Hakama", "Divided indigo shrine hakama pleated for swift footwork.", 2],
                "Gloves": ["Cinnabar-Inscribed Binding Wraps", "Consecrated linen hand-wraps inked with spirit-sealing glyphs.", 1],
                "Shoes": ["Reinforced Rubber-Soled Tabi Boots", "Modernized split-toe exorcist boots built for silent urban footing.", 1],
                "Shield": None,
            },
        },
        "Temple Kagura Ritualist": {
            "description": "Divine maiden or ritual officiant wielding consecrated yumi bows and sacred suzu bells to disperse corruption from afar.",
            "starting_items": [
                ["Sacred Kagura Bell", "Tool", "Bronze bell whose chimes calm spiritual agitation and reveal invisibles.", 2],
                ["Blessed Spring Water Flask", "Consumable", "Purified water restoring mental lucidity and physical vitality.", 1],
            ],
            "starter_gear": {
                "Head": ["Consecrated Silk Brow-Wrap", "Indigo cloth band inscribed with protective Sanskrit-inspired wards.", 1],
                "Weapon": ["Sacred Ritual Yumi Bow", "Asymmetric lacquered bamboo longbow shooting arrows blessed with holy cedar smoke.", 2],
                "Armor": ["Sacred Hemp & Silk Ward Breastplate", "Lightweight ceremonial armor hardened against spiritual miasma.", 2],
                "Top": ["Cinnabar-Trimmed Exorcist Kosode", "Traditional wide-sleeved robe consecrated for purification rites.", 2],
                "Bottom": ["Pleated Exorcist Hakama", "Divided indigo shrine hakama pleated for swift footwork.", 2],
                "Gloves": ["Sanctified Silk Ritual Bracers", "Armored forearm guards stitched with braided red ward-cord.", 1],
                "Shoes": ["Sanctified Mountain Waraji Striders", "Weatherproof woven footwear blessed at the Grand Temple torii.", 1],
                "Shield": None,
            },
        },
        "Consecrated Blade Warden": {
            "description": "Master of traditional swordsmanship trained to slice through ethereal phantoms with tamahagane blades soaked in sacred oils.",
            "starting_items": [
                ["Whetstone of Holy Dew", "Consumable", "Ceremonial whetstone coating weapons in phantom-cleaving light.", 1],
                ["Incense Smokebomb", "Consumable", "Purifying herbal smoke cloud masking movement and blinding fiends.", 1],
            ],
            "starter_gear": {
                "Head": ["Lacquered Crow-Tengu Half-Visor", "Traditional carved half-mask worn by nocturnal shrine exorcists.", 1],
                "Weapon": ["Consecrated Steel Katana", "Curved tamahagane blade etched with protective purification chants.", 2],
                "Armor": ["Prayer-Bead Reinforced Chest Wrap", "Layered exorcist chest binding anchored by blessed iron rings.", 2],
                "Top": ["Warded Monastic Sleeveless Gi", "Agile ascetic martial tunic allowing unrestricted talisman casting.", 1],
                "Bottom": ["Bound Shinobi-Cut Shrine Trousers", "Ankle-wrapped monastic trousers suited for rooftop pursuit.", 1],
                "Gloves": ["Cinnabar-Inscribed Binding Wraps", "Consecrated linen hand-wraps inked with spirit-sealing glyphs.", 1],
                "Shoes": ["Reinforced Rubber-Soled Tabi Boots", "Modernized split-toe exorcist boots built for silent urban footing.", 1],
                "Shield": None,
            },
        },
        "Crow-Feather Ascetic Warder": {
            "description": "Mystical ascetic who communes with crow spirits and mountain deities, channeling curse-breaking rosaries and wind incantations.",
            "starting_items": [
                ["Crow-Bone Divination Set", "Tool", "Runed avian bones pointing toward focal points of spiritual disturbance.", 2],
                ["Binding Spirit Rosary", "Consumable", "108-bead wooden rosary snaring malicious phantoms.", 1],
            ],
            "starter_gear": {
                "Head": ["Lacquered Crow-Tengu Half-Visor", "Traditional carved half-mask worn by nocturnal shrine exorcists.", 1],
                "Weapon": ["Crow-Feather Exorcism Staff", "Shakujo ringed staff adorned with midnight corvid feathers.", 2],
                "Armor": ["Ofuda-Lined Lacquered Do-Maru Vest", "Traditional lamellar chest protector woven with warding talismans.", 3],
                "Top": ["Consecrated Indigo Shrine Haori", "Flowing exorcist coat embroidered with silver bell-flower crests.", 2],
                "Bottom": ["Bound Shinobi-Cut Shrine Trousers", "Ankle-wrapped monastic trousers suited for rooftop pursuit.", 1],
                "Gloves": ["Sanctified Silk Ritual Bracers", "Armored forearm guards stitched with braided red ward-cord.", 1],
                "Shoes": ["Sanctified Mountain Waraji Striders", "Weatherproof woven footwear blessed at the Grand Temple torii.", 1],
                "Shield": None,
            },
        },
        "Talisman Seal Scribe": {
            "description": "Temple scholar specializing in ancient script, entity binding barriers, and portable barrier arrays.",
            "starting_items": [
                ["Cinnabar Calligraphy Ink & Brush", "Tool", "Ceremonial tools for painting wards upon stone, steel, or skin.", 2],
                ["Grand Warding Seal Slip", "Consumable", "Large parchment sealing doorway portals against entity passage.", 1],
            ],
            "starter_gear": {
                "Head": ["Braided Shimenawa Headband", "Sacred hemp headband consecrated with mountain shrine incense.", 1],
                "Weapon": ["Cinnabar-Etched Wakizashi", "Short sword with cinnabar lacquer channels channeling spiritual energy.", 2],
                "Armor": ["Sacred Hemp & Silk Ward Breastplate", "Lightweight ceremonial armor hardened against spiritual miasma.", 2],
                "Top": ["Cinnabar-Trimmed Exorcist Kosode", "Traditional wide-sleeved robe consecrated for purification rites.", 2],
                "Bottom": ["Pleated Exorcist Hakama", "Divided indigo shrine hakama pleated for swift footwork.", 2],
                "Gloves": ["Cinnabar-Inscribed Binding Wraps", "Consecrated linen hand-wraps inked with spirit-sealing glyphs.", 1],
                "Shoes": ["Reinforced Rubber-Soled Tabi Boots", "Modernized split-toe exorcist boots built for silent urban footing.", 1],
                "Shield": None,
            },
        },
    },
    "freelancer": {
        "Underground Occult Broker": {
            "description": "Streetwise informant and grey-market dealer packing a concealed heavy revolver and brass knuckles for close encounters.",
            "starting_items": [
                ["Encrypted Burner Phone", "Tool", "Untraceable cellular device connected to the black market bounty net.", 1],
                ["Street Trauma Patch", "Consumable", "Cheap coagulant compress stopping acute arterial bleeding.", 1],
            ],
            "starter_gear": {
                "Head": ["Tinted Night-Runner Shades", "Scratch-resistant urban sunglasses hiding bloodshot late-shift eyes.", 1],
                "Weapon": ["Concealed Snub-Nose Revolver", "Heavy .38 Special snub-nose revolver concealed in a quick-draw holster.", 2],
                "Armor": ["Surplus Concealed Soft-Armor Vest", "Modified surplus Kevlar vest worn discreetly under street clothes.", 2],
                "Top": ["Distressed Leather Moto-Jacket", "Scuffed biker jacket with reinforced elbows and hidden seams.", 2],
                "Bottom": ["Kevlar-Stitched Dark Raw Denim", "Heavy-duty street jeans reinforced at the knees and seams.", 1],
                "Gloves": ["Fingerless Padded Moto-Gloves", "Scuffed leather street gloves offering grip without losing touch.", 1],
                "Shoes": ["Worn Lug-Sole Urban Combat Boots", "Dependable waterproof street boots with steel shanks.", 1],
                "Shield": None,
            },
        },
        "Rogue Bounty Stalker": {
            "description": "Rugged tracker scouring abandoned subway lines and back alleys with a modified hunting rifle and survival blade.",
            "starting_items": [
                ["High-Intensity Flare", "Consumable", "Blinding chemical torch driving off photophobic entities.", 1],
                ["Makeshift Entity Snare", "Tool", "Reinforced steel-cable trap immobilizing quadrupeds and crawlers.", 2],
            ],
            "starter_gear": {
                "Head": ["Low-Profile Black Cap & Earbuds", "Unassuming streetwear cap paired with bone-conduction scanner audio.", 1],
                "Weapon": ["Lever-Action Hunting Rifle", "Rugged .30-30 lever rifle modified with a shortened barrel and fiber-optic sights.", 3],
                "Armor": ["Street-Modded Trauma Plate Rig", "Custom duct-taped ceramic plate carrier cobbled from salvage.", 2],
                "Top": ["Reinforced Heavy Canvas Duster", "Rugged street coat lined with makeshift slash-resistant panels.", 2],
                "Bottom": ["Reinforced Ripstop Streetwear Cargo Pants", "Multi-pocket urban cargo pants holding spare mags and batteries.", 1],
                "Gloves": ["Taped Street-Brawler Wraps", "Pragmatic athletic tape and leather palm guards.", 1],
                "Shoes": ["Worn Lug-Sole Urban Combat Boots", "Dependable waterproof street boots with steel shanks.", 1],
                "Shield": None,
            },
        },
        "Street Alchemist & Tinkerer": {
            "description": "Crafty urban drifter cobbling anomalous scraps into volatile improvised concoctions and sawed-off firearms.",
            "starting_items": [
                ["Improvised Phosphor Flask", "Consumable", "Mason jar of volatile incendiary gel burning with blinding white heat.", 1],
                ["Copper Grounding Wire Roll", "Tool", "Flexible grounding coil deflecting electrical and psychic arc feedback.", 1],
            ],
            "starter_gear": {
                "Head": ["Ribbed Urban Beanie & Mic Clip", "Comfortable knit beanie concealing a throat-mic transceiver.", 1],
                "Weapon": ["Sawed-Off Street Scattergun", "Double-barreled 12-gauge shotgun cut down for devastating close-quarters blast.", 2],
                "Armor": ["Street-Modded Trauma Plate Rig", "Custom duct-taped ceramic plate carrier cobbled from salvage.", 2],
                "Top": ["Urban Concealed-Carry Street Hoodie", "Heavyweight charcoal hoodie with hidden interior draw-pockets.", 1],
                "Bottom": ["Reinforced Ripstop Streetwear Cargo Pants", "Multi-pocket urban cargo pants holding spare mags and batteries.", 1],
                "Gloves": ["Taped Street-Brawler Wraps", "Pragmatic athletic tape and leather palm guards.", 1],
                "Shoes": ["Custom High-Traction Street Runners", "Broken-in athletic sneakers built for sprinting across alleys.", 1],
                "Shield": None,
            },
        },
        "Grid Runner & Signal Jacker": {
            "description": "Urban scrapper hacking containment frequencies and running contraband with compact submachine guns and signal scramblers.",
            "starting_items": [
                ["Backdoor Scanner Dongle", "Tool", "Hacked RF receiver intercepting municipal agency breach dispatches.", 2],
                ["Flash Grenade", "Consumable", "High-intensity disorienting charge.", 1],
            ],
            "starter_gear": {
                "Head": ["Tinted Night-Runner Shades", "Scratch-resistant urban sunglasses hiding bloodshot late-shift eyes.", 1],
                "Weapon": ["Scrapped Compact SMG", "Modified 9mm machine pistol with a high-capacity drum magazine.", 2],
                "Armor": ["Surplus Concealed Soft-Armor Vest", "Modified surplus Kevlar vest worn discreetly under street clothes.", 2],
                "Top": ["Weatherproof Midnight Windbreaker", "Reflective-piped urban shell jacket built for neon rain.", 1],
                "Bottom": ["Kevlar-Stitched Dark Raw Denim", "Heavy-duty street jeans reinforced at the knees and seams.", 1],
                "Gloves": ["Fingerless Padded Moto-Gloves", "Scuffed leather street gloves offering grip without losing touch.", 1],
                "Shoes": ["Custom High-Traction Street Runners", "Broken-in athletic sneakers built for sprinting across alleys.", 1],
                "Shield": None,
            },
        },
        "Back-Alley Blade Drifter": {
            "description": "Silent melee mercenary armed with a wicked combat machete and improvised occult wards etched into scrap metal.",
            "starting_items": [
                ["Smuggled Occult Curio", "Tool", "Strange petrified anomalous eyeball detecting nearby illusions.", 2],
                ["Styptic Powder Canister", "Consumable", "Antiseptic powder preventing septic shock from entity claw lacerations.", 1],
            ],
            "starter_gear": {
                "Head": ["Low-Profile Black Cap & Earbuds", "Unassuming streetwear cap paired with bone-conduction scanner audio.", 1],
                "Weapon": ["Scuffed Trench Machete", "Heavy steel clearing blade etched with defensive glyphs.", 2],
                "Armor": ["Street-Modded Trauma Plate Rig", "Custom duct-taped ceramic plate carrier cobbled from salvage.", 2],
                "Top": ["Distressed Leather Moto-Jacket", "Scuffed biker jacket with reinforced elbows and hidden seams.", 2],
                "Bottom": ["Reinforced Ripstop Streetwear Cargo Pants", "Multi-pocket urban cargo pants holding spare mags and batteries.", 1],
                "Gloves": ["Taped Street-Brawler Wraps", "Pragmatic athletic tape and leather palm guards.", 1],
                "Shoes": ["Worn Lug-Sole Urban Combat Boots", "Dependable waterproof street boots with steel shanks.", 1],
                "Shield": None,
            },
        },
    },
    "student_freelancer": {
        "Honor Roll Student": {
            "description": "Diligent, top-ranking student who balances exam prep by day with clinical after-hours anomaly containment.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Pocket Resonance Calculator", "Tool", "Modified graphing calculator plotting local Hume fluctuations.", 1],
            ],
            "starter_gear": {
                "Head": ["Anti-Glare Reading Glasses & Earbud", "Unassuming study frames concealing a bone-conduction anomaly alert receiver.", 1],
                "Weapon": ["Suppressed 9mm Service Pistol", "Compact 9mm tactical sidearm carried inside a false-bottom leather schoolbag.", 2],
                "Armor": ["Kevlar-Weave Academy Sweater Vest", "Neat school sweater vest lined with lightweight ballistic aramid panels.", 2],
                "Top": ["Tailored Academy Blazer & Crisp Shirt", "Standard high school uniform blazer with a reinforced interior draw-pocket.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "Regulation school uniform bottom stitched with ripstop lining.", 1],
                "Gloves": ["Thin Leather Study & Grip Gloves", "Supple dark gloves that leave no fingerprints on brass casings or chalk.", 1],
                "Shoes": ["Reinforced Uniform Loafers", "Polished school loafers fitted with non-slip tactical rubber soles.", 1],
                "Shield": None,
            },
        },
        "Athletic Regular": {
            "description": "Energetic, physically conditioned student with sharp reflexes who excels in gym class and close-quarters skirmishes alike.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Electrolyte Sports Bottle", "Consumable", "High-electrolyte recovery drink kept in a mesh duffle pocket.", 1],
            ],
            "starter_gear": {
                "Head": ["Moisture-Wicking Sweatband & Clip Mic", "Simple athletic headband hiding a sub-vocal transceiver.", 1],
                "Weapon": ["Live-Steel Wakizashi Blade", "Razor-sharp forged steel short sword carried inside a long canvas sports duffle.", 2],
                "Armor": ["Impact-Woven Varsity Chest Guard", "Low-profile padded trauma liner worn beneath a school track top.", 2],
                "Top": ["Reinforced School Track Jacket", "Zip-up academy athletics jacket with slash-resistant sleeve panels.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "Regulation school uniform bottom tailored for high-speed sprinting.", 1],
                "Gloves": ["Taped Athletic Grip Wraps", "Breathable wrist and palm tape offering firm blade and baton control.", 1],
                "Shoes": ["High-Traction Court Sneakers", "Cushioned school athletic shoes built for rooftop leaps and alley sprints.", 1],
                "Shield": None,
            },
        },
        "Quiet Bookworm": {
            "description": "Soft-spoken library regular who reads arcane folklore texts behind stacked novels and channels high-resonance wards.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Annotated Folklore Notebook", "Tool", "Margin-scribbled notebook cataloging local urban legends and entity taboos.", 1],
            ],
            "starter_gear": {
                "Head": ["Braided Bookmark Hair-Clip & Ward", "Discreet silver hair-clip etched with a cognitive grounding sigil.", 1],
                "Weapon": ["Consecrated Silver Athame", "Lethal ritual silver dagger tucked inside a hollowed-out hardcover reference tome.", 2],
                "Armor": ["Ward-Stitched Academy Cardigan", "Oversized knit school cardigan woven with spirit-dampening silver thread.", 2],
                "Top": ["Tailored Academy Blazer & Crisp Shirt", "Tidy school uniform shirt with paper talismans slipped inside the cuff.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "Regulation school uniform bottom with a hidden charm pocket.", 1],
                "Gloves": ["Archivist Cotton & Silk Gloves", "Soft library handling gloves treated with purifying salt resin.", 1],
                "Shoes": ["Reinforced Uniform Loafers", "Quiet-soled school loafers that barely make a sound on corridor tile.", 1],
                "Shield": None,
            },
        },
        "Back-Row Rebel": {
            "description": "Streetwise, tough-as-nails truant who naps by the classroom window and brawls on the front lines when rifts open.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Battered Zippo & Ward Chalk", "Tool", "Heavy brass lighter and salt-chalk sticks for marking containment lines.", 1],
            ],
            "starter_gear": {
                "Head": ["Unbuttoned Collar & Ear-Cuff Comms", "Clip-on gunmetal ear-cuff wired to a police-band anomaly scanner.", 1],
                "Weapon": ["Sawed-Off Street Scattergun", "Break-action 12-gauge scattergun slung inside a padded canvas guitar gig-bag.", 2],
                "Armor": ["Chain-Lined Sukajan Under-Vest", "Concealed slash-proof mesh vest worn beneath an open uniform.", 2],
                "Top": ["Unbuttoned Uniform & Street Jacket", "Scuffed jacket worn loosely over an untucked school shirt.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "Cuffed school uniform trousers reinforced at the knees.", 1],
                "Gloves": ["Weighted Knuckle Street Gloves", "Fingerless leather gloves with hardened carbon knuckle inserts.", 1],
                "Shoes": ["Scuffed High-Top School Boots", "Heavy lug-sole boots that kick through rusted padlocks and drywall.", 1],
                "Shield": None,
            },
        },
        "After-School Tinkerer": {
            "description": "Resourceful hands-on student whose backpack is packed with custom electronics, resonance sensors, and modified hardware.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Custom EMF & Hume Multimeter", "Tool", "Hand-soldered pocket detector wired from spare science-lab parts.", 1],
            ],
            "starter_gear": {
                "Head": ["Flip-Down Magnifier & Telemetry Goggles", "Workshop safety goggles modified with an infrared anomaly overlay.", 1],
                "Weapon": ["Modified Gauss Coil-Carbine", "Overclocked electromagnetic flechette carbine carried in a drafting tube case.", 2],
                "Armor": ["Insulated Maker-Lab Apron Rig", "Rubberized workshop vest lined with capacitor shielding and ceramic plates.", 2],
                "Top": ["Utility Lab Coat Over School Uniform", "Singed white lab coat worn over rolled-sleeve academy attire.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "School uniform bottom clipped with a soldering multi-tool.", 1],
                "Gloves": ["Insulated High-Voltage Work Gloves", "Dielectric workshop gloves protecting against arc discharge.", 1],
                "Shoes": ["Rubber-Soled Workshop Sneakers", "Static-grounded sneakers ideal for wet floors and live wiring.", 1],
                "Shield": None,
            },
        },
        "Class Sharpshooter": {
            "description": "Cool-headed, eagle-eyed student with steady nerves who never misses a mark from across the courtyard or alley.",
            "starting_items": [
                ["Public Agency Freelance Permit", "Tool", "Laminated student freelance permit tucked inside your school ID holder.", 1],
                ["Laser Rangefinder Monocular", "Tool", "Compact pocket optic calibrated for urban rooftop sightlines.", 1],
            ],
            "starter_gear": {
                "Head": ["Polarized Clip-On Visor & Earpiece", "Tinted glare-cutting lens paired with a wind-sensor earpiece.", 1],
                "Weapon": ["Folding Takedown Marksman Carbine", "Precision semi-automatic rifle packed inside a hard-shell instrument case.", 2],
                "Armor": ["Padded Recoil-Braced Uniform Vest", "Structured school vest with a reinforced shoulder recoil pad and kevlar weave.", 2],
                "Top": ["Tailored Academy Blazer & Crisp Shirt", "Clean-cut academy blazer tailored for unrestricted shoulder draw.", 1],
                "Bottom": ["Pleated Academy Skirt / Tailored Academy Slacks", "Regulation school uniform bottom with hidden magazine loops.", 1],
                "Gloves": ["Padded Two-Finger Marksman Gloves", "Precision shooting gloves keeping the trigger finger steady in cold rain.", 1],
                "Shoes": ["Reinforced Uniform Loafers", "Balanced low-heel school shoes providing rock-solid firing stance.", 1],
                "Shield": None,
            },
        },
    },
}

ANOMALOUS_FACTION_WEAPONS: Dict[str, List[str]] = {
    "public_agency": [
        "Bureau Issue Service Pistol",
        "Tactical Suppression Shotgun",
        "Suppressed Scout Carbine",
        "Arc-Discharge Stun Baton",
        "Kinetic Force Baton",
        "Standard-Issue Bureau SMG",
    ],
    "private_agency_1": [
        "In-House Mk.IV Smart Carbine",
        "Proprietary R&D Monomolecular Katana",
        "Corporate R&D Gauss Precision Rifle",
        "In-House Kinetic Breaching Sledgehammer",
        "Proprietary Caseless Smart-PDW",
        "Corporate Prototype Pulse Shotgun",
    ],
    "private_agency_2": [
        "Police Trade-In .38 Service Revolver",
        "Secondhand Riot Pump-Shotgun",
        "Surplus Imported 9mm Submachinegun",
        "Pawn-Shop Semi-Auto Carbine",
        "Mail-Order Heavy Clearing Machete",
        "Hardware-Modified Breaching Sledgehammer",
    ],
    "monastic_order": [
        "Purifying Shrine Naginata",
        "Sacred Ritual Yumi Bow",
        "Consecrated Steel Katana",
        "Crow-Feather Exorcism Staff",
        "Cinnabar-Etched Wakizashi",
        "Temple Exorcism Vajra",
    ],
    "freelancer": [
        "Concealed Snub-Nose Revolver",
        "Lever-Action Hunting Rifle",
        "Sawed-Off Street Scattergun",
        "Scrapped Compact SMG",
        "Scuffed Trench Machete",
        "Lead-Weighted Trench Blackjack",
    ],
    "student_freelancer": [
        "Suppressed 9mm Service Pistol",
        "Live-Steel Wakizashi Blade",
        "Consecrated Silver Athame",
        "Sawed-Off Street Scattergun",
        "Modified Gauss Coil-Carbine",
        "Folding Takedown Marksman Carbine",
    ],
}

ANOMALOUS_FACTION_STARTER_OUTFITS: Dict[str, Dict[str, List[Tuple[str, str]]]] = {
    "public_agency": {
        "Head": [
            ("Polarized Cognito-Filter Glasses", "Bureau-issue anti-memetic eyewear filtering anomalous visual noise."),
            ("Bureau Tactical Comms Earpiece", "Encrypted municipal dispatch receiver clipped over the ear."),
            ("Field Investigator Spectral Visor", "Low-profile polarized lenses revealing faint spatial distortions."),
        ],
        "Armor": [
            ("Concealed Bureau Kevlar Vest", "Taxpayer-funded low-profile ballistic vest worn beneath agency attire."),
            ("Standard-Issue Containment Plate Carrier", "Modular bureau chest rig with lead-lined evidence pouches."),
            ("Bureau Ballistic Trench Under-Rig", "Reinforced weave harness designed for rapid urban containment."),
        ],
        "Top": [
            ("Tailored Black Bureau Suit & Tie", "Crisp black agency suit jacket with an interior shoulder holster."),
            ("Charcoal Agency Trenchcoat & Dress Shirt", "Weatherproof bureau trenchcoat with occult-dampening stitching."),
            ("Bureau Field Inspector Blazer", "Structured dark blazer bearing a concealed municipal clearance pin."),
        ],
        "Bottom": [
            ("Tailored Charcoal Bureau Slacks", "Reinforced wool-blend agency slacks tailored for active pursuit."),
            ("Tailored Bureau Pencil Skirt / Tailored Field Slacks", "Sharp official agency attire reinforced with ripstop lining."),
        ],
        "Gloves": [
            ("Nitrile-Lined Black Leather Gloves", "Insulated field gloves preventing anomalous contact contamination."),
            ("Bureau Forensics Grip Gloves", "Tactile leather gloves suited for handling firearms and evidence canisters."),
        ],
        "Shoes": [
            ("Polished Steel-Toe Agency Oxfords", "Dress oxfords concealing puncture-resistant soles and ankle support."),
            ("Bureau Rapid-Response Field Boots", "Matte-black tactical boots built for subway tunnels and wet concrete."),
        ],
        "Accessory 1": [
            ("Encrypted Bureau Clearance Badge", "Holographic municipal containment ID granting Tier-1 HQ access."),
            ("Sub-Harmonic Resonance Pager", "Pocket detector that chimes softly near active spatial fractures."),
        ],
    },
    "private_agency_1": {
        "Head": [
            ("Proprietary Mk.III AR Telemetry Visor", "In-house corporate R&D heads-up visor streaming live skyscraper threat telemetry."),
            ("In-House Carbon-Weave Comms Headset", "Serialized corporate headset with encrypted satellite R&D uplink."),
            ("Corporate R&D Ballistic Half-Mask", "Sleek proprietary matte-carbon respirator developed in-house for tower breaches."),
        ],
        "Armor": [
            ("In-House R&D Composite Plate Rig", "Proprietary corporate ceramic-polymer chest rig engineered in the conglomerate's cleanrooms."),
            ("Executive Ballisticweave Tech-Duster", "Bespoke corporate longcoat woven in-house with flexible aramid-nanotube panels."),
            ("Proprietary Corporate Exo-Weave Vest", "Serialized conglomerate tactical vest with magnetic smart-mag caddies."),
        ],
        "Top": [
            ("Corporate R&D Tactical Techwear Coat", "Asymmetric matte-black corporate shell bearing embossed conglomerate R&D serials."),
            ("In-House Matte-Carbon Operator Shirt", "Proprietary breathable ballistic-shoulder combat shirt issued exclusively to conglomerate staff."),
            ("Executive Security Tailored Blazer", "Bespoke high-collar corporate suit jacket engineered in-house for concealed carry."),
        ],
        "Bottom": [
            ("Proprietary Operator Cargo Trousers", "Articulated corporate R&D ripstop trousers with integrated magnetic holster mounts."),
            ("Corporate Aramid-Stitched Executive Slacks", "Tailored conglomerate combat slacks woven from proprietary slash-proof fibers."),
        ],
        "Gloves": [
            ("In-House Smart-Link Operator Gloves", "Proprietary synthetic gloves syncing weapon grip sensors to corporate HUDs."),
            ("Corporate Carbon-Knuckle Gauntlets", "Serialized R&D contractor gloves engineered for zero-slip recoil control."),
        ],
        "Shoes": [
            ("Corporate Silent-Tread Tech High-Tops", "Custom R&D urban striders with sound-deadening polymer soles."),
            ("Proprietary Shock-Damped Assault Boots", "Lightweight in-house composite boots built for high-rise corporate deployments."),
        ],
        "Accessory 1": [
            ("Corporate R&D Biometric Clearance Tag", "Encrypted conglomerate ID chip unlocking skyscraper R&D vaults and prototype racks."),
            ("Proprietary Executive Telemetry Uplink", "Wrist-mounted corporate R&D terminal logging commission bounties in real time."),
        ],
    },
    "private_agency_2": {
        "Head": [
            ("Off-the-Shelf Clip-On Polarized Glasses", "Drugstore polarized clip-ons taped over safety frames to cut anomalous glare."),
            ("Surplus Riot Bump-Helmet", "Scuffed municipal auction helmet with a handwritten agency asset sticker on the back."),
            ("Secondhand Two-Way Radio Headset", "Discount commercial walkie-talkie headset bought in bulk from an electronics liquidator."),
        ],
        "Armor": [
            ("Mismatched Surplus Kevlar Vest", "Retired security-firm ballistic vest with mismatched Velcro pouches from three different vendors."),
            ("Discount Commercial Plate Carrier", "Budget mail-order nylon carrier fitted with heavy steel aftermarket trauma plates."),
            ("Patched Mall-Security Soft-Armor", "Secondhand Kevlar under-vest neatly stitched and duct-taped at the office patching corner."),
        ],
        "Top": [
            ("Off-the-Rack Utility Windbreaker", "Plain commercial nylon windbreaker with a small iron-on local agency patch."),
            ("Worn Commercial Canvas Work Jacket", "Sturdy hardware-store duck-canvas jacket smelling faintly of gun oil and burnt drip coffee."),
            ("Thrifted Wrinkled Office Trenchcoat", "Sensible department-store raincoat worn over a short-sleeved button-down shirt."),
        ],
        "Bottom": [
            ("Hardware-Store Reinforced Cargo Pants", "Durable off-the-shelf workwear trousers stuffed with spare batteries, receipts, and chalk."),
            ("Scuffed Office Slacks with Knee Pads", "Ordinary commercial dress slacks paired with strap-on hardware-store knee pads."),
        ],
        "Gloves": [
            ("Hardware-Store Impact Work Gloves", "Bright-stitched mechanic's grip gloves picked up on sale down the street."),
            ("Duct-Taped Surplus Leather Gloves", "Broken-in military surplus gloves reinforced across the knuckles with silver gaffer tape."),
        ],
        "Shoes": [
            ("Discount Steel-Toe Work Boots", "Practical warehouse safety boots with oil-resistant rubber soles."),
            ("Broken-In Surplus Patrol Boots", "Resoled police-surplus leather boots kept watertight with cheap shoe grease."),
        ],
        "Accessory 1": [
            ("Laminated Small-Agency Contractor ID", "Self-laminated paper badge on a beaded chain unlocking the office's back-room gun cage."),
            ("Mail-Order Third-Party EMF Meter", "Chunky plastic hobbyist ghost-meter rewired to buzz near genuine spatial rifts."),
        ],
    },
    "monastic_order": {
        "Head": [
            ("Braided Shimenawa Headband", "Sacred hemp headband consecrated with mountain shrine incense."),
            ("Lacquered Crow-Tengu Half-Visor", "Traditional carved half-mask worn by nocturnal shrine exorcists."),
            ("Consecrated Silk Brow-Wrap", "Indigo cloth band inscribed with protective Sanskrit-inspired wards."),
        ],
        "Armor": [
            ("Ofuda-Lined Lacquered Do-Maru Vest", "Traditional lamellar chest protector woven with warding talismans."),
            ("Sacred Hemp & Silk Ward Breastplate", "Lightweight ceremonial armor hardened against spiritual miasma."),
            ("Prayer-Bead Reinforced Chest Wrap", "Layered exorcist chest binding anchored by blessed iron rings."),
        ],
        "Top": [
            ("Consecrated Indigo Shrine Haori", "Flowing exorcist coat embroidered with silver bell-flower crests."),
            ("Cinnabar-Trimmed Exorcist Kosode", "Traditional wide-sleeved robe consecrated for purification rites."),
            ("Warded Monastic Sleeveless Gi", "Agile ascetic martial tunic allowing unrestricted talisman casting."),
        ],
        "Bottom": [
            ("Pleated Exorcist Hakama", "Divided indigo shrine hakama pleated for swift footwork."),
            ("Bound Shinobi-Cut Shrine Trousers", "Ankle-wrapped monastic trousers suited for rooftop pursuit."),
        ],
        "Gloves": [
            ("Cinnabar-Inscribed Binding Wraps", "Consecrated linen hand-wraps inked with spirit-sealing glyphs."),
            ("Sanctified Silk Ritual Bracers", "armored forearm guards stitched with braided red ward-cord."),
        ],
        "Shoes": [
            ("Reinforced Rubber-Soled Tabi Boots", "Modernized split-toe exorcist boots built for silent urban footing."),
            ("Sanctified Mountain Waraji Striders", "Weatherproof woven footwear blessed at the Grand Temple torii."),
        ],
        "Accessory 1": [
            ("Sacred Cypress Prayer Beads", "108 carved cypress beads that warm in the presence of malice."),
            ("Cinnabar Bell & Ofuda Pouch", "Waist pouch carrying consecrated paper seals and a bronze kagura bell."),
        ],
    },
    "freelancer": {
        "Head": [
            ("Low-Profile Black Cap & Earbuds", "Unassuming streetwear cap paired with bone-conduction scanner audio."),
            ("Tinted Night-Runner Shades", "Scratch-resistant urban sunglasses hiding bloodshot late-shift eyes."),
            ("Ribbed Urban Beanie & Mic Clip", "Comfortable knit beanie concealing a throat-mic transceiver."),
        ],
        "Armor": [
            ("Surplus Concealed Soft-Armor Vest", "Modified surplus Kevlar vest worn discreetly under street clothes."),
            ("Street-Modded Trauma Plate Rig", "Custom duct-taped ceramic plate carrier cobbled from salvage."),
            ("Reinforced Heavy Canvas Duster", "Rugged street coat lined with makeshift slash-resistant panels."),
        ],
        "Top": [
            ("Urban Concealed-Carry Street Hoodie", "Heavyweight charcoal hoodie with hidden interior draw-pockets."),
            ("Weatherproof Midnight Windbreaker", "Reflective-piped urban shell jacket built for neon rain."),
            ("Distressed Leather Moto-Jacket", "Scuffed biker jacket with reinforced elbows and hidden seams."),
        ],
        "Bottom": [
            ("Reinforced Ripstop Streetwear Cargo Pants", "Multi-pocket urban cargo pants holding spare mags and batteries."),
            ("Kevlar-Stitched Dark Raw Denim", "Heavy-duty street jeans reinforced at the knees and seams."),
        ],
        "Gloves": [
            ("Fingerless Padded Moto-Gloves", "Scuffed leather street gloves offering grip without losing touch."),
            ("Taped Street-Brawler Wraps", "Pragmatic athletic tape and leather palm guards."),
        ],
        "Shoes": [
            ("Custom High-Traction Street Runners", "Broken-in athletic sneakers built for sprinting across alleys."),
            ("Worn Lug-Sole Urban Combat Boots", "Dependable waterproof street boots with steel shanks."),
        ],
        "Accessory 1": [
            ("Burner Smartphone & Bounty Dongle", "Jailbroken handset pre-loaded with the Freelance Containment App."),
            ("Custom Brass Grounding Charm", "Pocket talisman traded from a back-alley curio broker."),
        ],
    },
    "student_freelancer": {
        "Head": [
            ("Anti-Glare Reading Glasses & Earbud", "Unassuming study frames concealing a bone-conduction anomaly alert receiver."),
            ("Moisture-Wicking Sweatband & Clip Mic", "Simple athletic headband hiding a sub-vocal transceiver."),
            ("Polarized Clip-On Visor & Earpiece", "Tinted glare-cutting lens paired with a wind-sensor earpiece."),
        ],
        "Armor": [
            ("Kevlar-Weave Academy Sweater Vest", "Neat school sweater vest lined with lightweight ballistic aramid panels."),
            ("Ward-Stitched Academy Cardigan", "Oversized knit school cardigan woven with spirit-dampening silver thread."),
            ("Impact-Woven Varsity Chest Guard", "Low-profile padded trauma liner worn beneath a school uniform top."),
        ],
        "Top": [
            ("Tailored Academy Blazer & Crisp Shirt", "Standard high school uniform blazer with a reinforced interior draw-pocket."),
            ("Reinforced School Track Jacket", "Zip-up academy athletics jacket with slash-resistant sleeve panels."),
            ("Unbuttoned Uniform & Street Jacket", "Scuffed street jacket worn loosely over an untucked school shirt."),
        ],
        "Bottom": [
            ("Pleated Academy Skirt / Tailored Academy Slacks", "Regulation school uniform bottom stitched with ripstop lining."),
            ("Pleated Uniform Skirt / Cuffed Uniform Trousers", "Durable academy uniform bottom with concealed utility pockets."),
        ],
        "Gloves": [
            ("Thin Leather Study & Grip Gloves", "Supple dark gloves that leave no fingerprints on brass casings or chalk."),
            ("Taped Athletic Grip Wraps", "Breathable wrist and palm tape offering firm weapon control."),
        ],
        "Shoes": [
            ("Reinforced Uniform Loafers", "Polished school loafers fitted with non-slip tactical rubber soles."),
            ("High-Traction Court Sneakers", "Cushioned school athletic shoes built for rooftop leaps and alley sprints."),
        ],
        "Accessory 1": [
            ("Student ID & Freelance Permit Lanyard", "Academy student ID holder concealing a laminated Public Agency freelance permit."),
            ("Clip-On Campus & Hume Pager", "Pocket keychain charm that vibrates quietly when an anomaly rift opens nearby."),
        ],
    },
}


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


def infer_anomalous_faction_from_class(char_class: Optional[str]) -> Optional[str]:
    """Returns the canonical faction archetype key if `char_class` belongs to one of the 5 Anomalous factions."""
    if not char_class:
        return None
    target = str(char_class).strip().lower()
    for fac_key, cls_map in ANOMALOUS_FACTION_CLASSES.items():
        for cls_name in cls_map:
            if cls_name.lower() == target:
                return fac_key
    return None


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
        medkit["name"] = "Proprietary R&D Nano-Trauma Medkit"
        stabilizer["name"] = "In-House Cognitive Stabilizer Ampoule"
    elif norm_fac == "private_agency_2":
        medkit["name"] = "Pharmacy-Bought Field Medkit"
        stabilizer["name"] = "Generic Off-Brand Focus Ampoule"
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
        booster["name"] = "Corporate Mk.II Combat Stim-Injector"
        items.append((booster["name"], booster["item_type"], booster["effect"], 1))
    elif norm_fac == "private_agency_2":
        booster = generate_procedural_potion(tier=3, effect_tags=["attack_buff"], genre="anomalous_incursions")
        booster["name"] = "Bulk-Pack Caffeine & Painkiller Shot"
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
