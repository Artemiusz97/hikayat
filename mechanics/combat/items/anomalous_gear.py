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
from typing import Any, Dict, List, Optional

from mechanics.combat.items.envelope import serialize_item

ANOMALOUS_MELEE_ARCHETYPES: List[str] = [
    "katana", "baton", "dagger", "shortsword", "sword",
    "cleaver", "axe", "warhammer", "spear", "fist_weapon"
]

ANOMALOUS_RANGED_ARCHETYPES: List[str] = [
    "pistol", "revolver", "submachinegun", "shotgun", "rifle", "machinegun"
]

ANOMALOUS_ELEMENTS: List[str] = [
    "fire", "ice", "shock", "poison", "holy", "dark", "earth", "water", "wind"
]

ELIGIBLE_SPELL_GRANT_SLOTS = {
    "Weapon", "Shield", "Offhand", "Armor", "Top",
    "Accessory", "Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"
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
        "fire_res", "magic_dt",
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


def _inject_anomalous_properties(
    metadata: Dict[str, Any],
    slot: str,
    tier: int,
    element: Optional[str] = None,
    force_granted_spell: Optional[bool] = None,
) -> None:
    """Infuses an item with the 'anomalous' tag, a fantasy elemental tag, and a 35% chance for a slot-restricted spell."""
    elem = element if element in ANOMALOUS_ELEMENTS else random.choice(ANOMALOUS_ELEMENTS)
    metadata["is_anomalous"] = True
    metadata["element"] = elem

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

    if item_type == "Weapon" or slot == "Weapon":
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
    else:
        res_bonus = 35 if tier == 1 else (25 if tier == 2 else 15)
        dt_bonus = 16 if tier == 1 else (10 if tier == 2 else 6)
        stat_mods[f"{elem}_res"] = max(stat_mods.get(f"{elem}_res", 0), res_bonus)
        type_dt = metadata.setdefault("type_dt", {})
        if isinstance(type_dt, dict):
            type_dt[elem] = type_dt.get(elem, 0) + dt_bonus
        prots = metadata.setdefault("protection_types", ["physical"])
        if isinstance(prots, list) and elem not in prots:
            prots.append(elem)

    # Slot-Restricted Equipment-Granted Spell (~35% chance on eligible slots)
    check_slot = str(slot or metadata.get("slot") or item_type)
    is_eligible_slot = (
        check_slot in ELIGIBLE_SPELL_GRANT_SLOTS
        or check_slot.startswith("Accessory")
        or item_type in ("Weapon", "Shield", "Armor", "Accessory")
    ) and check_slot not in ("Head", "Gloves", "Shoes", "Bottom")

    should_grant = force_granted_spell if force_granted_spell is not None else (is_eligible_slot and random.random() < 0.35)
    if is_eligible_slot and should_grant:
        from mechanics.combat.spells.procedural import generate_procedural_spell
        from mechanics.combat.spells.registry import register_spell

        proc_spell = generate_procedural_spell(
            scenario="anomalous_incursions",
            tier=tier if tier in (1, 2, 3) else 3,
            element=elem,
        )
        proc_spell["is_equipment_granted"] = True
        proc_spell["source_element"] = elem
        register_spell(proc_spell)
        metadata["granted_spell"] = proc_spell
        metadata["granted_spell_id"] = proc_spell["id"]


def apply_anomalous_incursions_gear_rules(
    item: Dict[str, Any],
    scenario: str,
    slot: str = "Weapon",
    tier: int = 3,
    tier_5_scale: Optional[int] = None,
    private_agency_bonus: bool = False,
    force_anomalous: Optional[bool] = None,
    force_granted_spell: Optional[bool] = None,
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
        elem = metadata.get("element")
        if elem not in ANOMALOUS_ELEMENTS:
            elem = random.choice(ANOMALOUS_ELEMENTS)
        _inject_anomalous_properties(
            metadata,
            slot=actual_slot,
            tier=item_tier,
            element=elem,
            force_granted_spell=force_granted_spell,
        )
        affix_info = ANOMALOUS_ELEMENT_AFFIXES.get(elem, ANOMALOUS_ELEMENT_AFFIXES["dark"])
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

    # Append granted spell description if present
    granted_sp = metadata.get("granted_spell")
    if isinstance(granted_sp, dict) and granted_sp.get("name"):
        sp_badge = f"✨ Grants Ability (While Equipped): {granted_sp['name']} ({granted_sp.get('mp_cost', 10)} MP)"
        metadata["description"] = sp_badge
        item["description"] = sp_badge

    # Re-serialize effect string
    raw_eff = str(item.get("effect") or "")
    if raw_eff.startswith("[GEAR_JSON]"):
        item["effect"] = f"[GEAR_JSON]{json.dumps(metadata)}"
    else:
        item["effect"] = serialize_item(metadata)
    item["metadata"] = metadata
    return item


def sync_equipped_anomalous_spells(user_id: int) -> Dict[str, Any]:
    """
    Synchronizes equipment-granted spells with the character's active learned_spells list.
    - Equipping an anomalous item with `granted_spell` adds the spell to `learned_spells`.
    - Unequipping removes the spell if no other equipped item grants it (and it wasn't innate).
    - If 2+ equipped items grant the exact same `spell_id`, sets `duplicate_empowered = True` (+20% power).
    """
    import db
    from mechanics.combat.equipment import parse_equipment_metadata
    from mechanics.combat.spells.registry import get_spell, register_spell, SPELL_REGISTRY

    char = db.get_character(user_id)
    if not char:
        return {"active_granted_spells": [], "empowered_spells": []}

    equipment = db.get_equipment(user_id) or {}
    progress = db.get_skill_progress(char)
    prev_granted_only: List[str] = list(progress.get("equipped_granted_spells") or [])
    prev_empowered: List[str] = list(progress.get("empowered_granted_spells") or [])
    innate_spells: List[str] = list(progress.get("innate_spells") or [])

    current_spells = list(db.get_learned_spells(user_id) or [])
    if not innate_spells:
        # Any spell currently learned that wasn't previously tracked as equipment-only is innate
        innate_spells = [s for s in current_spells if s not in prev_granted_only]
        progress["innate_spells"] = innate_spells

    grant_counts: Dict[str, int] = {}
    grant_defs: Dict[str, Dict[str, Any]] = {}

    for slot, eq_item in equipment.items():
        if not eq_item or not isinstance(eq_item, dict):
            continue
        if slot in ("Head", "Gloves", "Shoes", "Bottom"):
            continue
        meta = parse_equipment_metadata(eq_item) or {}
        g_spell = meta.get("granted_spell")
        g_id = meta.get("granted_spell_id") or (g_spell.get("id") if isinstance(g_spell, dict) else None)
        if g_id:
            grant_counts[g_id] = grant_counts.get(g_id, 0) + 1
            if isinstance(g_spell, dict):
                grant_defs[g_id] = g_spell

    # Base spells = current spells minus any previous equipment-only spells that are no longer granted
    updated_spells: List[str] = [
        s for s in current_spells
        if s not in prev_granted_only or s in innate_spells or s in grant_counts
    ]

    empowered_ids: List[str] = []
    new_granted_only: List[str] = []

    for g_id, count in grant_counts.items():
        sp_def = grant_defs.get(g_id) or get_spell(g_id)
        is_dup = count >= 2 or (count >= 1 and g_id in innate_spells)
        if isinstance(sp_def, dict):
            # Persist clean definition (duplicate_empowered=False) to DB, keep per-sync runtime flag in memory
            sp_clean = copy.deepcopy(sp_def)
            sp_clean["duplicate_empowered"] = False
            register_spell(sp_clean)
            sp_mem = copy.deepcopy(sp_def)
            sp_mem["duplicate_empowered"] = bool(is_dup)
            SPELL_REGISTRY[g_id] = sp_mem
        if is_dup:
            empowered_ids.append(g_id)
        if g_id not in updated_spells:
            updated_spells.append(g_id)
        if g_id not in innate_spells:
            new_granted_only.append(g_id)

    # Clear duplicate_empowered on any previously granted or innate spell that is no longer duplicate-empowered
    for old_id in (set(prev_granted_only) | set(prev_empowered) | set(innate_spells)):
        if old_id not in empowered_ids:
            sp_def = get_spell(old_id)
            if isinstance(sp_def, dict) and sp_def.get("duplicate_empowered"):
                sp_copy = copy.deepcopy(sp_def)
                sp_copy["duplicate_empowered"] = False
                SPELL_REGISTRY[old_id] = sp_copy

    progress["equipped_granted_spells"] = new_granted_only
    progress["empowered_granted_spells"] = empowered_ids
    db.set_skill_progress(user_id, progress)
    db.set_learned_spells(user_id, updated_spells)

    return {
        "active_granted_spells": list(grant_counts.keys()),
        "empowered_spells": empowered_ids,
        "learned_spells": updated_spells,
    }


ANOMALOUS_FACTION_CLASSES: Dict[str, Dict[str, Dict[str, Any]]] = {'public_agency': {'Public Safety Field Hunter': {'description': 'High-mobility tactical operative trained in close-quarters anomaly interception, rapid breaching, and lethal entity suppression.', 'starting_items': [['Field Trauma Kit', 'Consumable', 'Rapid-application coagulant and adrenaline injector.', 1], ['Flashbang Grenade', 'Consumable', 'High-intensity disorienting charge.', 1]], 'starter_gear': {'Head': ['Tactical Balaclava & Comms', 'Fire-retardant headwear with radio earpiece.', 1], 'Weapon': ['Tactical Suppression Shotgun', 'Short-barreled pump-action shotgun loaded with heavy slug rounds.', 2], 'Armor': ['Standard-Issue Containment Plate Carrier', 'Modular bureau chest rig with lead-lined evidence pouches.', 3], 'Top': ['Reinforced Bureau Combat Shirt', 'Durable dark tactical utility wear.', 1], 'Bottom': ['Reinforced Cargo Trousers', 'Ripstop tactical trousers with knee-pad inserts.', 2], 'Gloves': ['Tactical Grip Gloves', 'Non-slip leather gloves with carbon-fiber knuckle guards.', 1], 'Shoes': ['Bureau Rapid-Response Field Boots', 'Matte-black tactical boots built for subway tunnels and wet concrete.', 1], 'Shield': None}}, 'Bureau Forensic Investigator': {'description': 'Specialized forensics agent using electronic resonance scanners and occult analysis to track, catalogue, and contain spatial distortions.', 'starting_items': [['Sub-Harmonic Resonance Scanner', 'Tool', 'Handheld sensor registering spatial distortions and abnormal frequencies.', 2], ['Sealed Evidence Canisters', 'Tool', 'Lead-lined canisters for hazardous anomalous residues.', 1]], 'starter_gear': {'Head': ['Spectral Optical Visor', 'Tactical polarized glasses detecting unnatural luminescence and light bends.', 1], 'Weapon': ['Bureau Issue Service Pistol', 'Standard 9mm duty pistol with precision barrel rifling.', 2], 'Armor': ['Concealed Bureau Kevlar Vest', 'Taxpayer-funded low-profile ballistic vest worn beneath agency attire.', 2], 'Top': ['Dark Trenchcoat & Tie', 'Professional bureau field suit with occult-dampening lining.', 2], 'Bottom': ['Tailored Field Slacks', 'Reinforced charcoal slacks suited for active investigation.', 1], 'Gloves': ['Nitrile-Lined Leather Gloves', 'Insulated gloves preventing contact contamination.', 1], 'Shoes': ['Polished Field Oxfords', 'Reinforced rubber-soled leather shoes.', 1], 'Shield': None}}, 'Quarantine Containment Engineer': {'description': 'Heavy hazmat and containment specialist equipped with spatial anchoring tools, suppression foam, and reality barrier emitters.', 'starting_items': [['Emergency Ward Pylon', 'Tool', 'Deployable tripod emitter establishing a temporary spatial stability zone.', 2], ['Pressurized Suppression Foam', 'Consumable', 'Aerosol canister spraying fast-hardening anomalous barrier foam.', 1]], 'starter_gear': {'Head': ['Hazmat Respirator Helmet', 'Full-face positive pressure respirator with filtered air intake.', 2], 'Weapon': ['Arc-Discharge Stun Baton', 'Heavy telescoping baton delivering pulsed electromagnetic shock.', 2], 'Armor': ['Insulated Hazmat Exosuit', 'Heavy hermetically sealed hazard containment suit.', 4], 'Top': ['Rubberized Utility Overalls', 'Chemical and tear-resistant protective workwear.', 2], 'Bottom': ['Reinforced Hazmat Trousers', 'Heavy insulated overalls with radiation-reflective layering.', 2], 'Gloves': ['Heavy Insulated Gauntlets', 'Thick rubber-and-kevlar gloves protecting against energy discharge.', 2], 'Shoes': ['Hazard Chemical Boots', 'Heavy vulcanized rubber boots with puncture-proof soles.', 2], 'Shield': None}}, 'Occult Precision Marksman': {'description': 'Precision suppression marksman neutralizing anomalous vectors from overwatch perches with talisman-inscribed ballistic ammunition.', 'starting_items': [['Runic Precision Monocular', 'Tool', 'Compact spotter scope revealing ethereal silhouettes through smoke and walls.', 2], ['Consecrated Silver Magazine', 'Consumable', 'Extended magazine packed with silver-cored ammunition.', 2]], 'starter_gear': {'Head': ['Tactical Ballistic Cap', 'Low-profile cap with integrated comms clip.', 1], 'Weapon': ['Suppressed Scout Carbine', 'Compact semi-automatic rifle equipped with a specialized sound and flash suppressor.', 3], 'Armor': ['Modular Plate Carrier', 'Lightweight ballistic vest allowing unrestricted arm movement.', 2], 'Top': ['Weather-Resistant Windbreaker', 'Dark matte windbreaker masking thermal signature.', 1], 'Bottom': ['Weatherproof Utility Trousers', 'Water-repellent combat trousers with zippered pockets.', 1], 'Gloves': ['Shooter Grip Gloves', 'Precision shooting gloves with tactile index finger pads.', 1], 'Shoes': ['All-Terrain Field Boots', 'Silent tread boots providing stable footing on damp concrete.', 1], 'Shield': None}}, 'Bureau Aegis Esper': {'description': 'Regulated psychic liaison channeling sanctioned mental barriers and kinetic disruption fields under strict containment oversight.', 'starting_items': [['Cognitive Stabilizer Ampoule', 'Consumable', 'Fast-acting neuro-sedative dampening psychological terror.', 1], ['Bureau Mental Dampener Ring', 'Tool', 'Electromagnetic ring providing resistance to mental incursions.', 2]], 'starter_gear': {'Head': ['Polarized Cognito-Filter Glasses', 'Bureau-issue anti-memetic eyewear filtering anomalous visual noise.', 1], 'Weapon': ['Kinetic Force Baton', 'Reinforced alloy baton weighted with kinetic force-damping coils.', 2], 'Armor': ['Bureau Ballistic Trench Under-Rig', 'Reinforced weave harness designed for rapid urban containment.', 2], 'Top': ['Bureau Field Inspector Blazer', 'Structured dark blazer bearing a concealed municipal clearance pin.', 1], 'Bottom': ['Tailored Charcoal Bureau Slacks', 'Reinforced wool-blend agency slacks tailored for active pursuit.', 1], 'Gloves': ['Tactile Trigger-Guard Gauntlets', 'Precision contractor gloves engineered for recoil control.', 1], 'Shoes': ['Polished Steel-Toe Agency Oxfords', 'Dress oxfords concealing puncture-resistant soles and ankle support.', 1], 'Shield': None}}}, 'private_agency_1': {'Corporate PMC Breacher': {'description': 'High-threat assault specialist clad in composite exo-carapace, dominating room clearances with high-caliber kinetic firepower.', 'starting_items': [['Adrenaline Surge Injector', 'Consumable', 'Military-grade stimulant restoring stamina and pain tolerance.', 1], ['High-Yield Breaching Charge', 'Consumable', 'Directional explosive designed to shatter fortified barriers.', 1]], 'starter_gear': {'Head': ['AR Telemetry Tactical Visor', 'High-spec corporate HUD visor displaying live threat telemetry.', 1], 'Weapon': ['Apex Custom Assault Carbine', 'Gas-piston military carbine customized with carbon handguards and compensator.', 3], 'Armor': ['High-Spec Composite Plate Rig', 'Lightweight corporate ceramic armor engineered for elite contractors.', 3], 'Top': ['Matte-Carbon Operator Combat Shirt', 'Breathable ballistic-shoulder combat top bearing agency insignia.', 1], 'Bottom': ['Reinforced Operator Cargo Trousers', 'Articulated ripstop techwear pants with magnetic holster mounts.', 2], 'Gloves': ['Carbon-Knuckle Operator Gloves', 'High-grip synthetic gloves with reinforced carbon-fiber knuckles.', 1], 'Shoes': ['Silent-Tread Corporate Assault Boots', 'Lightweight composite boots built for vertical tower breaches.', 1], 'Shield': None}}, 'Black-Ops Wetwork Operative': {'description': 'Clandestine elimination asset specializing in stealth infiltration, silent takedowns, and monomolecular edged combat.', 'starting_items': [['Optical Camouflage Cloak Clip', 'Tool', 'Micro-projector bending light across the torso for brief concealment.', 2], ['Micro-Wire Garrote', 'Tool', 'High-tensile wire for silent physical entity restraint.', 1]], 'starter_gear': {'Head': ['Ballistic Operator Half-Mask', 'Sleek matte-carbon lower faceplate with particulate filtration.', 1], 'Weapon': ['Monomolecular Combat Blade', 'Razor-edged combat dagger slicing through anomalous carapaces with zero resistance.', 2], 'Armor': ['Executive Ballistic Tech-Duster', 'Armored designer longcoat lined with flexible aramid panels.', 3], 'Top': ['Corporate Tactical Techwear Coat', 'Asymmetric matte-black techwear shell with waterproof seams.', 2], 'Bottom': ['Aramid-Stitched Tactical Slacks', 'Sleek corporate combat trousers built for high-speed mobility.', 1], 'Gloves': ['Carbon-Knuckle Operator Gloves', 'High-grip synthetic gloves with reinforced carbon-fiber knuckles.', 1], 'Shoes': ['Shock-Absorbing Tactical High-Tops', 'Custom corporate urban striders with silent rubber treads.', 1], 'Shield': None}}, 'Heavy Asset Juggernaut': {'description': 'Armored frontline suppression tank fielding reinforced shields and high-impact kinetic sledgehammers to crush anomaly swarms.', 'starting_items': [['Emergency Armor Plate Siphon', 'Tool', 'Rapid hydraulic clamp repairing shattered ballistic plates.', 2], ['Concussion Stun Grenade', 'Consumable', 'High-decibel acoustic disorientation charge.', 1]], 'starter_gear': {'Head': ['Ballistic Operator Half-Mask', 'Sleek matte-carbon lower faceplate with particulate filtration.', 1], 'Weapon': ['Reinforced Breaching Sledgehammer', 'Industrial drop-forged hammer capable of crushing hardened chitin.', 3], 'Armor': ['Corporate Exo-Weave Tactical Vest', 'Premium private-sector chest rig with quick-release mag caddies.', 4], 'Top': ['Corporate Tactical Techwear Coat', 'Asymmetric matte-black techwear shell with waterproof seams.', 2], 'Bottom': ['Reinforced Operator Cargo Trousers', 'Articulated ripstop techwear pants with magnetic holster mounts.', 2], 'Gloves': ['Carbon-Knuckle Operator Gloves', 'High-grip synthetic gloves with reinforced carbon-fiber knuckles.', 1], 'Shoes': ['Silent-Tread Corporate Assault Boots', 'Lightweight composite boots built for vertical tower breaches.', 1], 'Shield': ['Reinforced Alloy Breaching Shield', 'Heavy ballistic barrier absorbing heavy kinetic impacts.', 2]}}, 'Corporate Recon Marksman': {'description': 'Electronic-warfare sniper utilizing digitized HUD ballistic telemetry and long-range anti-materiel systems.', 'starting_items': [['Targeting Uplink Dart', 'Tool', 'Beacon establishing predictive ballistic tracking on anomalous targets.', 2], ['Cryo-Tracer Ammunition', 'Consumable', 'Specialized rounds chilling targets upon penetration.', 1]], 'starter_gear': {'Head': ['AR Telemetry Tactical Visor', 'High-spec corporate HUD visor displaying live threat telemetry.', 1], 'Weapon': ['Anti-Materiel Precision Rifle', 'Heavy bolt-action .50 BMG rifle engineered for structural anomaly neutralizations.', 3], 'Armor': ['High-Spec Composite Plate Rig', 'Lightweight corporate ceramic armor engineered for elite contractors.', 3], 'Top': ['Matte-Carbon Operator Combat Shirt', 'Breathable ballistic-shoulder combat top bearing agency insignia.', 1], 'Bottom': ['Aramid-Stitched Tactical Slacks', 'Sleek corporate combat trousers built for high-speed mobility.', 1], 'Gloves': ['Tactile Trigger-Guard Gauntlets', 'Precision contractor gloves engineered for recoil control.', 1], 'Shoes': ['Silent-Tread Corporate Assault Boots', 'Lightweight composite boots built for vertical tower breaches.', 1], 'Shield': None}}, 'Executive Security Escort': {'description': 'High-stakes close protection detail trained in rapid threat neutralization, tactical sidearms, and corporate VIP evacuation.', 'starting_items': [['Emergency Med-Patch', 'Consumable', 'Quick-clot trauma adhesive sealing gunshot wounds.', 1], ['Flashbang Grenade', 'Consumable', 'High-intensity disorienting charge.', 1]], 'starter_gear': {'Head': ['Carbon-Weave Comms Headset', 'Noise-canceling private contractor headset with encrypted uplink.', 1], 'Weapon': ['Apex Tactical PDW', 'Compact 4.6mm submachine gun with high rate of fire and low recoil.', 2], 'Armor': ['Executive Ballistic Tech-Duster', 'Armored designer longcoat lined with flexible aramid panels.', 3], 'Top': ['Executive Security Tailored Jacket', 'Bespoke high-collar corporate jacket cut for concealed carry.', 2], 'Bottom': ['Aramid-Stitched Tactical Slacks', 'Sleek corporate combat trousers built for high-speed mobility.', 1], 'Gloves': ['Tactile Trigger-Guard Gauntlets', 'Precision contractor gloves engineered for recoil control.', 1], 'Shoes': ['Shock-Absorbing Tactical High-Tops', 'Custom corporate urban striders with silent rubber treads.', 1], 'Shield': None}}}, 'private_agency_2': {'Cyber-Occult Technologist': {'description': 'Avant-garde researcher weaponizing experimental arc-emitter coils and electromagnetic resonance fields against non-Euclidean threats.', 'starting_items': [['Prototype Flux Battery', 'Tool', 'High-capacity capacitor overcharging energy-based gear.', 2], ['Resonance Scrambler Grenade', 'Consumable', 'Pulsed EMP disabling electronic entity manifestations.', 1]], 'starter_gear': {'Head': ['Clip-On Polarized Tactical Lens', 'Compact polarized eyewear with sub-optical spectrum filters.', 1], 'Weapon': ['Arc-Discharge Coil Rifle', 'Experimental energy carbine launching concentrated ion pulses.', 3], 'Armor': ['Multi-Threat Composite Trauma Suit', 'Advanced multi-layered composite body armor engineered for hazardous anomalies.', 3], 'Top': ['Lead-Lined Hazmat Field Overcoat', 'Heavy protective duster tailored with radiation-resistant lead weave.', 2], 'Bottom': ['Aramid-Stitched Tactical Slacks', 'Flexible synthetic trousers reinforced with impact-dispersing weave.', 1], 'Gloves': ['Heavy Insulated Gauntlets', 'Thick rubber-and-kevlar gloves protecting against energy discharge.', 2], 'Shoes': ['Silent-Tread Corporate Assault Boots', 'Lightweight composite boots built for vertical tower breaches.', 1], 'Shield': None}}, 'Bio-Anomaly Harvester': {'description': 'Ruthless corporate extraction agent wielding pneumatic harvest needles and cryogenic containment capsules to capture living tissue samples.', 'starting_items': [['Cryogenic Specimen Canister', 'Tool', 'Hermetic liquid nitrogen capsule for tissue preservation.', 2], ['Cellular Regeneration Syringe', 'Consumable', 'Synthesized bio-growth compound closing flesh lacerations.', 1]], 'starter_gear': {'Head': ['Hazmat Respirator Helmet', 'Full-face positive pressure respirator with filtered air intake.', 2], 'Weapon': ['Cryo-Siphon Needlegun', 'Pneumatic needle injector firing flash-freezing tranquilizer flechettes.', 2], 'Armor': ['Multi-Threat Composite Trauma Suit', 'Advanced multi-layered composite body armor engineered for hazardous anomalies.', 3], 'Top': ['Lead-Lined Hazmat Field Overcoat', 'Heavy protective duster tailored with radiation-resistant lead weave.', 2], 'Bottom': ['Reinforced Hazmat Trousers', 'Heavy insulated overalls with radiation-reflective layering.', 2], 'Gloves': ['Nitrile-Lined Leather Gloves', 'Insulated gloves preventing contact contamination.', 1], 'Shoes': ['Hazard Chemical Boots', 'Heavy vulcanized rubber boots with puncture-proof soles.', 2], 'Shield': None}}, 'Nanite Aegis Vanguard': {'description': 'Kinetic security specialist deploying prototype magnetic-barrier shields and high-frequency vibro-blades.', 'starting_items': [['Nanite Armor Repair Gel', 'Consumable', 'Aerosolized nanites reforming damaged ceramic armor matrixes.', 1], ['Kinetic Dispersal Pylon', 'Tool', 'Deployable emitter grounding concussive kinetic blasts.', 2]], 'starter_gear': {'Head': ['AR Telemetry Tactical Visor', 'High-spec corporate HUD visor displaying live threat telemetry.', 1], 'Weapon': ['High-Frequency Vibro-Katana', 'Oscillating alloy blade slicing matter on a molecular scale.', 2], 'Armor': ['High-Spec Composite Plate Rig', 'Lightweight corporate ceramic armor engineered for elite contractors.', 3], 'Top': ['Corporate Tactical Techwear Coat', 'Asymmetric matte-black techwear shell with waterproof seams.', 2], 'Bottom': ['Reinforced Operator Cargo Trousers', 'Articulated ripstop techwear pants with magnetic holster mounts.', 2], 'Gloves': ['Carbon-Knuckle Operator Gloves', 'High-grip synthetic gloves with reinforced carbon-fiber knuckles.', 1], 'Shoes': ['Shock-Absorbing Tactical High-Tops', 'Custom corporate urban striders with silent rubber treads.', 1], 'Shield': ['Lightweight Composite Deflector', 'Kinetic energy dissipation shield for close-quarters parrying.', 2]}}, 'Experimental Prototype Specialist': {'description': 'Volatile field tester evaluating unreleased corporate weaponry, particle throwers, and reality-shearing experimental gear.', 'starting_items': [['Overcharged Power Cell', 'Consumable', 'Unstable cell providing temporary double-damage output.', 1], ['Reality Stabilization Tether', 'Tool', 'Pylon tether pinning dimensional anomalies to local Euclidean coordinates.', 2]], 'starter_gear': {'Head': ['Spectral Optical Visor', 'Tactical polarized glasses detecting unnatural luminescence and light bends.', 1], 'Weapon': ['Experimental Plasma Scatterer', 'Heavy directed-energy shotgun discharging superheated plasma bursts.', 3], 'Armor': ['Level-IV Ceramic Plate Carrier', 'Modular tactical rig holding hardened ceramic trauma plates.', 3], 'Top': ['Matte-Carbon Operator Combat Shirt', 'Breathable ballistic-shoulder combat top bearing agency insignia.', 1], 'Bottom': ['Reinforced Operator Cargo Trousers', 'Articulated ripstop techwear pants with magnetic holster mounts.', 2], 'Gloves': ['Tactile Trigger-Guard Gauntlets', 'Precision contractor gloves engineered for recoil control.', 1], 'Shoes': ['Silent-Tread Corporate Assault Boots', 'Lightweight composite boots built for vertical tower breaches.', 1], 'Shield': None}}, 'Neural System Hacker': {'description': 'Electronic and psychic infiltrator who hijacks entity resonance signatures, security grids, and drone uplinks.', 'starting_items': [['Exploitation Deck Dongle', 'Tool', 'Infiltration terminal accessing sealed containment doors and networks.', 2], ['EMP Pulse Mine', 'Consumable', 'Magnetic proximity mine disrupting entity shielding.', 1]], 'starter_gear': {'Head': ['AR Telemetry Tactical Visor', 'High-spec corporate HUD visor displaying live threat telemetry.', 1], 'Weapon': ['Vanguard Suppressed Flechette Pistol', 'High-velocity silenced pistol firing micro-darts tipped with neuro-toxin.', 2], 'Armor': ['Concealed Kevlar Ballistic Vest', 'Low-profile Kevlar undergarment vest.', 2], 'Top': ['Corporate Tactical Techwear Coat', 'Asymmetric matte-black techwear shell with waterproof seams.', 2], 'Bottom': ['Aramid-Stitched Tactical Slacks', 'Sleek corporate combat trousers built for high-speed mobility.', 1], 'Gloves': ['Tactile Trigger-Guard Gauntlets', 'Precision contractor gloves engineered for recoil control.', 1], 'Shoes': ['Shock-Absorbing Tactical High-Tops', 'Custom corporate urban striders with silent rubber treads.', 1], 'Shield': None}}}, 'monastic_order': {'Shrine Exorcist Ascetic': {'description': 'Consecrated warrior-monk wielding sanctified polearms and spirit-binding seals to banish and cleanse incursions.', 'starting_items': [['Consecrated Salt Pouch', 'Consumable', 'Blessed sea salt scattering spiritual corruption and staggering entities.', 1], ['Purification Paper Talisman (Ofuda)', 'Tool', 'Inscribed paper seal disrupting anomalous energy fields.', 2]], 'starter_gear': {'Head': ['Braided Shimenawa Headband', 'Sacred hemp headband consecrated with mountain shrine incense.', 1], 'Weapon': ['Purifying Shrine Naginata', 'Curved polearm blade folded from sanctified steel and dipped in shrine waters.', 3], 'Armor': ['Ofuda-Lined Lacquered Do-Maru Vest', 'Traditional lamellar chest protector woven with warding talismans.', 3], 'Top': ['Consecrated Indigo Shrine Haori', 'Flowing exorcist coat embroidered with silver bell-flower crests.', 2], 'Bottom': ['Pleated Exorcist Hakama', 'Divided indigo shrine hakama pleated for swift footwork.', 2], 'Gloves': ['Cinnabar-Inscribed Binding Wraps', 'Consecrated linen hand-wraps inked with spirit-sealing glyphs.', 1], 'Shoes': ['Reinforced Rubber-Soled Tabi Boots', 'Modernized split-toe exorcist boots built for silent urban footing.', 1], 'Shield': None}}, 'Temple Kagura Ritualist': {'description': 'Divine maiden or ritual officiant wielding consecrated yumi bows and sacred suzu bells to disperse corruption from afar.', 'starting_items': [['Sacred Kagura Bell', 'Tool', 'Bronze bell whose chimes calm spiritual agitation and reveal invisibles.', 2], ['Blessed Spring Water Flask', 'Consumable', 'Purified water restoring mental lucidity and physical vitality.', 1]], 'starter_gear': {'Head': ['Consecrated Silk Brow-Wrap', 'Indigo cloth band inscribed with protective Sanskrit-inspired wards.', 1], 'Weapon': ['Sacred Ritual Yumi Bow', 'Asymmetric lacquered bamboo longbow shooting arrows blessed with holy cedar smoke.', 2], 'Armor': ['Sacred Hemp & Silk Ward Breastplate', 'Lightweight ceremonial armor hardened against spiritual miasma.', 2], 'Top': ['Cinnabar-Trimmed Exorcist Kosode', 'Traditional wide-sleeved robe consecrated for purification rites.', 2], 'Bottom': ['Pleated Exorcist Hakama', 'Divided indigo shrine hakama pleated for swift footwork.', 2], 'Gloves': ['Sanctified Silk Ritual Bracers', 'Armored forearm guards stitched with braided red ward-cord.', 1], 'Shoes': ['Sanctified Mountain Waraji Striders', 'Weatherproof woven footwear blessed at the Grand Temple torii.', 1], 'Shield': None}}, 'Consecrated Blade Warden': {'description': 'Master of traditional swordsmanship trained to slice through ethereal phantoms with tamahagane blades soaked in sacred oils.', 'starting_items': [['Whetstone of Holy Dew', 'Consumable', 'Ceremonial whetstone coating weapons in phantom-cleaving light.', 1], ['Incense Smokebomb', 'Consumable', 'Purifying herbal smoke cloud masking movement and blinding fiends.', 1]], 'starter_gear': {'Head': ['Lacquered Crow-Tengu Half-Visor', 'Traditional carved half-mask worn by nocturnal shrine exorcists.', 1], 'Weapon': ['Consecrated Steel Katana', 'Curved tamahagane blade etched with protective purification chants.', 2], 'Armor': ['Prayer-Bead Reinforced Chest Wrap', 'Layered exorcist chest binding anchored by blessed iron rings.', 2], 'Top': ['Warded Monastic Sleeveless Gi', 'Agile ascetic martial tunic allowing unrestricted talisman casting.', 1], 'Bottom': ['Bound Shinobi-Cut Shrine Trousers', 'Ankle-wrapped monastic trousers suited for rooftop pursuit.', 1], 'Gloves': ['Cinnabar-Inscribed Binding Wraps', 'Consecrated linen hand-wraps inked with spirit-sealing glyphs.', 1], 'Shoes': ['Reinforced Rubber-Soled Tabi Boots', 'Modernized split-toe exorcist boots built for silent urban footing.', 1], 'Shield': None}}, 'Crow-Feather Ascetic Warder': {'description': 'Mystical ascetic who communes with crow spirits and mountain deities, channeling curse-breaking rosaries and wind incantations.', 'starting_items': [['Crow-Bone Divination Set', 'Tool', 'Runed avian bones pointing toward focal points of spiritual disturbance.', 2], ['Binding Spirit Rosary', 'Consumable', '108-bead wooden rosary snaring malicious phantoms.', 1]], 'starter_gear': {'Head': ['Lacquered Crow-Tengu Half-Visor', 'Traditional carved half-mask worn by nocturnal shrine exorcists.', 1], 'Weapon': ['Crow-Feather Exorcism Staff', 'Shakujo ringed staff adorned with midnight corvid feathers.', 2], 'Armor': ['Ofuda-Lined Lacquered Do-Maru Vest', 'Traditional lamellar chest protector woven with warding talismans.', 3], 'Top': ['Consecrated Indigo Shrine Haori', 'Flowing exorcist coat embroidered with silver bell-flower crests.', 2], 'Bottom': ['Bound Shinobi-Cut Shrine Trousers', 'Ankle-wrapped monastic trousers suited for rooftop pursuit.', 1], 'Gloves': ['Sanctified Silk Ritual Bracers', 'Armored forearm guards stitched with braided red ward-cord.', 1], 'Shoes': ['Sanctified Mountain Waraji Striders', 'Weatherproof woven footwear blessed at the Grand Temple torii.', 1], 'Shield': None}}, 'Talisman Seal Scribe': {'description': 'Temple scholar specializing in ancient script, entity binding barriers, and portable barrier arrays.', 'starting_items': [['Cinnabar Calligraphy Ink & Brush', 'Tool', 'Ceremonial tools for painting wards upon stone, steel, or skin.', 2], ['Grand Warding Seal Slip', 'Consumable', 'Large parchment sealing doorway portals against entity passage.', 1]], 'starter_gear': {'Head': ['Braided Shimenawa Headband', 'Sacred hemp headband consecrated with mountain shrine incense.', 1], 'Weapon': ['Cinnabar-Etched Wakizashi', 'Short sword with cinnabar lacquer channels channeling spiritual energy.', 2], 'Armor': ['Sacred Hemp & Silk Ward Breastplate', 'Lightweight ceremonial armor hardened against spiritual miasma.', 2], 'Top': ['Cinnabar-Trimmed Exorcist Kosode', 'Traditional wide-sleeved robe consecrated for purification rites.', 2], 'Bottom': ['Pleated Exorcist Hakama', 'Divided indigo shrine hakama pleated for swift footwork.', 2], 'Gloves': ['Cinnabar-Inscribed Binding Wraps', 'Consecrated linen hand-wraps inked with spirit-sealing glyphs.', 1], 'Shoes': ['Reinforced Rubber-Soled Tabi Boots', 'Modernized split-toe exorcist boots built for silent urban footing.', 1], 'Shield': None}}}, 'freelancer': {'Underground Occult Broker': {'description': 'Streetwise informant and grey-market dealer packing a concealed heavy revolver and brass knuckles for close encounters.', 'starting_items': [['Encrypted Burner Phone', 'Tool', 'Untraceable cellular device connected to the black market bounty net.', 1], ['Street Trauma Patch', 'Consumable', 'Cheap coagulant compress stopping acute arterial bleeding.', 1]], 'starter_gear': {'Head': ['Tinted Night-Runner Shades', 'Scratch-resistant urban sunglasses hiding bloodshot late-shift eyes.', 1], 'Weapon': ['Concealed Snub-Nose Revolver', 'Heavy .38 Special snub-nose revolver concealed in a quick-draw holster.', 2], 'Armor': ['Surplus Concealed Soft-Armor Vest', 'Modified surplus Kevlar vest worn discreetly under street clothes.', 2], 'Top': ['Distressed Leather Moto-Jacket', 'Scuffed biker jacket with reinforced elbows and hidden seams.', 2], 'Bottom': ['Kevlar-Stitched Dark Raw Denim', 'Heavy-duty street jeans reinforced at the knees and seams.', 1], 'Gloves': ['Fingerless Padded Moto-Gloves', 'Scuffed leather street gloves offering grip without losing touch.', 1], 'Shoes': ['Worn Lug-Sole Urban Combat Boots', 'Dependable waterproof street boots with steel shanks.', 1], 'Shield': None}}, 'Rogue Bounty Stalker': {'description': 'Rugged tracker scouring abandoned subway lines and back alleys with a modified hunting rifle and survival blade.', 'starting_items': [['High-Intensity Flare', 'Consumable', 'Blinding chemical torch driving off photophobic entities.', 1], ['Makeshift Entity Snare', 'Tool', 'Reinforced steel-cable trap immobilizing quadrupeds and crawlers.', 2]], 'starter_gear': {'Head': ['Low-Profile Black Cap & Earbuds', 'Unassuming streetwear cap paired with bone-conduction scanner audio.', 1], 'Weapon': ['Lever-Action Hunting Rifle', 'Rugged .30-30 lever rifle modified with a shortened barrel and fiber-optic sights.', 3], 'Armor': ['Street-Modded Trauma Plate Rig', 'Custom duct-taped ceramic plate carrier cobbled from salvage.', 2], 'Top': ['Reinforced Heavy Canvas Duster', 'Rugged street coat lined with makeshift slash-resistant panels.', 2], 'Bottom': ['Reinforced Ripstop Streetwear Cargo Pants', 'Multi-pocket urban cargo pants holding spare mags and batteries.', 1], 'Gloves': ['Taped Street-Brawler Wraps', 'Pragmatic athletic tape and leather palm guards.', 1], 'Shoes': ['Worn Lug-Sole Urban Combat Boots', 'Dependable waterproof street boots with steel shanks.', 1], 'Shield': None}}, 'Street Alchemist & Tinkerer': {'description': 'Crafty urban drifter cobbling anomalous scraps into volatile improvised concoctions and sawed-off firearms.', 'starting_items': [['Improvised Phosphor Flask', 'Consumable', 'Mason jar of volatile incendiary gel burning with blinding white heat.', 1], ['Copper Grounding Wire Roll', 'Tool', 'Flexible grounding coil deflecting electrical and psychic arc feedback.', 1]], 'starter_gear': {'Head': ['Ribbed Urban Beanie & Mic Clip', 'Comfortable knit beanie concealing a throat-mic transceiver.', 1], 'Weapon': ['Sawed-Off Street Scattergun', 'Double-barreled 12-gauge shotgun cut down for devastating close-quarters blast.', 2], 'Armor': ['Street-Modded Trauma Plate Rig', 'Custom duct-taped ceramic plate carrier cobbled from salvage.', 2], 'Top': ['Urban Concealed-Carry Street Hoodie', 'Heavyweight charcoal hoodie with hidden interior draw-pockets.', 1], 'Bottom': ['Reinforced Ripstop Streetwear Cargo Pants', 'Multi-pocket urban cargo pants holding spare mags and batteries.', 1], 'Gloves': ['Taped Street-Brawler Wraps', 'Pragmatic athletic tape and leather palm guards.', 1], 'Shoes': ['Custom High-Traction Street Runners', 'Broken-in athletic sneakers built for sprinting across alleys.', 1], 'Shield': None}}, 'Grid Runner & Signal Jacker': {'description': 'Urban scrapper hacking containment frequencies and running contraband with compact submachine guns and signal scramblers.', 'starting_items': [['Backdoor Scanner Dongle', 'Tool', 'Hacked RF receiver intercepting municipal agency breach dispatches.', 2], ['Flash Grenade', 'Consumable', 'High-intensity disorienting charge.', 1]], 'starter_gear': {'Head': ['Tinted Night-Runner Shades', 'Scratch-resistant urban sunglasses hiding bloodshot late-shift eyes.', 1], 'Weapon': ['Scrapped Compact SMG', 'Modified 9mm machine pistol with a high-capacity drum magazine.', 2], 'Armor': ['Surplus Concealed Soft-Armor Vest', 'Modified surplus Kevlar vest worn discreetly under street clothes.', 2], 'Top': ['Weatherproof Midnight Windbreaker', 'Reflective-piped urban shell jacket built for neon rain.', 1], 'Bottom': ['Kevlar-Stitched Dark Raw Denim', 'Heavy-duty street jeans reinforced at the knees and seams.', 1], 'Gloves': ['Fingerless Padded Moto-Gloves', 'Scuffed leather street gloves offering grip without losing touch.', 1], 'Shoes': ['Custom High-Traction Street Runners', 'Broken-in athletic sneakers built for sprinting across alleys.', 1], 'Shield': None}}, 'Back-Alley Blade Drifter': {'description': 'Silent melee mercenary armed with a wicked combat machete and improvised occult wards etched into scrap metal.', 'starting_items': [['Smuggled Occult Curio', 'Tool', 'Strange petrified anomalous eyeball detecting nearby illusions.', 2], ['Styptic Powder Canister', 'Consumable', 'Antiseptic powder preventing septic shock from entity claw lacerations.', 1]], 'starter_gear': {'Head': ['Low-Profile Black Cap & Earbuds', 'Unassuming streetwear cap paired with bone-conduction scanner audio.', 1], 'Weapon': ['Scuffed Trench Machete', 'Heavy steel clearing blade etched with defensive glyphs.', 2], 'Armor': ['Street-Modded Trauma Plate Rig', 'Custom duct-taped ceramic plate carrier cobbled from salvage.', 2], 'Top': ['Distressed Leather Moto-Jacket', 'Scuffed biker jacket with reinforced elbows and hidden seams.', 2], 'Bottom': ['Reinforced Ripstop Streetwear Cargo Pants', 'Multi-pocket urban cargo pants holding spare mags and batteries.', 1], 'Gloves': ['Taped Street-Brawler Wraps', 'Pragmatic athletic tape and leather palm guards.', 1], 'Shoes': ['Worn Lug-Sole Urban Combat Boots', 'Dependable waterproof street boots with steel shanks.', 1], 'Shield': None}}}}

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
        "Apex Custom Assault Carbine",
        "Monomolecular Combat Blade",
        "Anti-Materiel Precision Rifle",
        "Reinforced Breaching Sledgehammer",
        "Apex Tactical PDW",
        "Heavy 12-Gauge Breaching Shotgun",
    ],
    "private_agency_2": [
        "Arc-Discharge Coil Rifle",
        "Cryo-Siphon Needlegun",
        "High-Frequency Vibro-Katana",
        "Experimental Plasma Scatterer",
        "Vanguard Suppressed Flechette Pistol",
        "Kinetic Impact Maul",
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
            ("AR Telemetry Tactical Visor", "High-spec corporate HUD visor displaying live threat telemetry."),
            ("Carbon-Weave Comms Headset", "Noise-canceling private contractor headset with encrypted uplink."),
            ("Ballistic Operator Half-Mask", "Sleek matte-carbon lower faceplate with particulate filtration."),
        ],
        "Armor": [
            ("High-Spec Composite Plate Rig", "Lightweight corporate ceramic armor engineered for elite contractors."),
            ("Executive Ballistic Tech-Duster", "Armored designer longcoat lined with flexible aramid panels."),
            ("Corporate Exo-Weave Tactical Vest", "Premium private-sector chest rig with quick-release mag caddies."),
        ],
        "Top": [
            ("Corporate Tactical Techwear Coat", "Asymmetric matte-black techwear shell with waterproof seams."),
            ("Matte-Carbon Operator Combat Shirt", "Breathable ballistic-shoulder combat top bearing agency insignia."),
            ("Executive Security Tailored Jacket", "Bespoke high-collar corporate jacket cut for concealed carry."),
        ],
        "Bottom": [
            ("Reinforced Operator Cargo Trousers", "Articulated ripstop techwear pants with magnetic holster mounts."),
            ("Aramid-Stitched Tactical Slacks", "Sleek corporate combat trousers built for high-speed mobility."),
        ],
        "Gloves": [
            ("Carbon-Knuckle Operator Gloves", "High-grip synthetic gloves with reinforced carbon-fiber knuckles."),
            ("Tactile Trigger-Guard Gauntlets", "Precision contractor gloves engineered for recoil control."),
        ],
        "Shoes": [
            ("Shock-Absorbing Tactical High-Tops", "Custom corporate urban striders with silent rubber treads."),
            ("Silent-Tread Corporate Assault Boots", "Lightweight composite boots built for vertical tower breaches."),
        ],
        "Accessory 1": [
            ("Private Contractor Biometric Dogtag", "Encrypted corporate transponder logging verified bounty kills."),
            ("Executive Escrow Commlink", "High-bandwidth contractor terminal linked to private armory brokers."),
        ],
    },
    "private_agency_2": {
        "Head": [
            ("Clip-On Polarized Tactical Lens", "Compact polarized eyewear with sub-optical spectrum filters."),
            ("Pressurized Bio-Optic Mask", "Full-seal breathing apparatus with integrated chromatic lenses."),
            ("Neural Interface Headband", "Bio-feedback sensor strip reading spatial cognitive fluctuations."),
            ("Integrated Blast HUD Helmet", "Hardened composite helmet projecting tactical resonance readouts."),
        ],
        "Armor": [
            ("Multi-Threat Composite Trauma Suit", "Advanced multi-layered composite body armor engineered for hazardous anomalies."),
            ("Lead-Lined Bio-Polymer Vest", "Hermetically shielded chest rig impervious to corrosive fluids and ionizing radiation."),
            ("Nanite-Hardened Chest Rig", "Reactive vest laced with microscopic nanite fibers that harden on impact."),
            ("Experimental Flux Deflector Rig", "Prototype electromagnetic harness deflecting kinetic and arcane energy."),
        ],
        "Top": [
            ("Lead-Lined Hazmat Field Overcoat", "Heavy protective duster tailored with radiation-resistant lead weave."),
            ("Vanguard Composite Armored Tunic", "Reinforced high-collar corporate lab tunic with ballistic weave."),
            ("Hazard Test-Pilot Jumpsuit", "Sealed fire-retardant flight suit suited for high-energy prototype testing."),
            ("Asymmetric Cyber-Runner Jacket", "Waterproof techwear shell equipped with conductive power relays."),
        ],
        "Bottom": [
            ("Aramid-Stitched Tactical Slacks", "Flexible synthetic trousers reinforced with impact-dispersing weave."),
            ("Reinforced Hazmat Trousers", "Heavy insulated overalls with radiation-reflective layering."),
            ("Reinforced Flex-Plate Trousers", "Articulated combat trousers fitted with flexible ceramic plating."),
            ("Insulated Nanite-Weave Trousers", "Conductive trousers grounded to discharge volatile spatial static."),
        ],
        "Gloves": [
            ("Heavy Insulated Gauntlets", "Thick rubber-and-kevlar gloves protecting against energy discharge."),
            ("Nitrile-Lined Leather Gloves", "Insulated gloves preventing contact contamination."),
            ("Conductive Alloy Gloves", "Flexible metal-mesh gloves designed to handle live energy coils."),
            ("Tactile Hacking Gloves", "Ultra-thin capacitive gloves suited for high-speed terminal overrides."),
        ],
        "Shoes": [
            ("Silent-Tread Corporate Assault Boots", "Lightweight composite boots built for vertical tower breaches."),
            ("Hazard Chemical Boots", "Heavy vulcanized rubber boots with puncture-proof soles."),
            ("Mag-Lev Utility Boots", "Shock-absorbing laboratory boots with magnetic traction soles."),
            ("Shock-Dispersal Boots", "Reinforced boots dampening seismic and concussive shockwaves."),
        ],
        "Accessory 1": [
            ("Encrypted Corporate Transponder", "High-frequency micro-transmitter linked to Syndicate telemetry."),
            ("Lead-Cased Dosimeter Lanyard", "Hermetic dosimeter pendant measuring ambient Hume level spikes."),
            ("Field Diagnostics Forearm Cuff", "Wrist-mounted terminal displaying live entity biological vitals."),
            ("RFID Security Clearance Badge", "High-tier holographic security pass granting access to Syndicate labs."),
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
}


def normalize_anomalous_starting_faction(starting_faction: Optional[str]) -> str:
    fac = str(starting_faction or "public_agency").strip().lower()
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

    norm_fac = normalize_anomalous_starting_faction(starting_faction)
    outfit_key = norm_fac
    pool_map = ANOMALOUS_FACTION_STARTER_OUTFITS.get(outfit_key, ANOMALOUS_FACTION_STARTER_OUTFITS["public_agency"])

    is_male = str(gender or "").strip().lower() == "male"
    is_female = str(gender or "").strip().lower() == "female"
    has_tail = is_tailed_race(race)

    # Theme / verify starting Weapon for faction
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
                cls_info = ANOMALOUS_FACTION_CLASSES.get(norm_fac, {}).get(char_class or "")
                if cls_info and cls_info.get("starter_gear", {}).get("Weapon"):
                    target_weapon_name = cls_info["starter_gear"]["Weapon"][0]
                else:
                    target_weapon_name = fac_weapons[0]
                    
        if target_weapon_name and (target_weapon_name not in w_name or "is_anomalous" not in w_meta):
            from mechanics.combat.items.weapons import generate_random_equipment as _gen_w
            w_tier = int(w_meta.get("tier") or 3)
            loadout["Weapon"] = _gen_w(scenario=scenario, slot="Weapon", tier=w_tier, name=target_weapon_name)
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
        if isinstance(granted_sp, dict) and granted_sp.get("name"):
            final_desc = f"{flavor_desc} • ✨ Grants Ability (While Equipped): {granted_sp['name']} ({granted_sp.get('mp_cost', 10)} MP)"
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
    medkit["name"] = "Field-Issue Trauma Medkit"
    stabilizer = generate_procedural_potion(tier=3, effect_tags=["mana_restore"], genre="anomalous_incursions")
    stabilizer["name"] = (
        "Shrine-Blessed Spirit-Calming Incense"
        if norm_fac == "monastic_order"
        else "Containment-Grade Cognitive Stabilizer Ampoule"
    )

    items: List[Tuple[str, str, str, int]] = [
        (medkit["name"], medkit["item_type"], medkit["effect"], 1),
        (stabilizer["name"], stabilizer["item_type"], stabilizer["effect"], 1),
    ]

    if norm_fac == "monastic_order":
        salt = generate_procedural_potion(tier=3, effect_tags=["cleanse_all"], genre="anomalous_incursions")
        salt["name"] = "Sacred Purging Salt Pouch"
        items.append((salt["name"], salt["item_type"], salt["effect"], 1))
    elif norm_fac in ("private_agency_1", "private_agency_2"):
        booster = generate_procedural_potion(tier=3, effect_tags=["attack_buff"], genre="anomalous_incursions")
        booster["name"] = "Corporate Combat Adrenaline Autoinjector"
        items.append((booster["name"], booster["item_type"], booster["effect"], 1))
    elif norm_fac == "public_agency":
        purge = generate_procedural_potion(tier=3, effect_tags=["cleanse_all"], genre="anomalous_incursions")
        purge["name"] = "Class-A Amnestic & Cognito Purge"
        items.append((purge["name"], purge["item_type"], purge["effect"], 1))
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
