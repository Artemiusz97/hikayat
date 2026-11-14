"""mechanics/combat/enemy_profiles.py

Archetype armor/weapon combat profiles (including tuned schoolyard brawl DT/ATK)
and Anomalous Incursions conditional danger-zone encounter rules.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def get_enemy_armor_profile(archetype: str) -> dict:
    """Returns the default armor class, protection types, base DT, and type DT traits for an enemy archetype."""
    arch = (archetype or "").strip()
    if arch in ("Guardian", "Heavy Mech", "Heavy Borg", "Cursed Construct"):
        return {
            "armor_type": "heavy",
            "protection_types": ["physical", "ballistic"],
            "base_dt": 20,
            "type_dt": {
                "physical": 24, "slashing": 26, "stabbing": 18, "blunt": 14,
                "ballistic": 24, "rifle_round": 16, "pistol_round": 22, "high_caliber_round": 10,
                "arrow": 20, "bolt": 16, "magical": 8, "shock": 0, "fire": 6, "ice": 10,
                "earth": 12, "water": 8, "wind": 10,
            },
            "def_bonus": 18,
            "mdef_bonus": 8,
            "block_chance": 20,
        }
    elif arch in ("Brute", "Rad-Mutant", "Bio-Horror Brute"):
        return {
            "armor_type": "medium",
            "protection_types": ["physical"],
            "base_dt": 12,
            "type_dt": {
                "physical": 14, "slashing": 16, "stabbing": 10, "blunt": 8,
                "arrow": 12, "bolt": 8, "pistol_round": 6, "rifle_round": 4,
                "magical": 6, "fire": 4, "shock": 0, "ice": 6, "poison": 4,
                "earth": 6, "water": 4, "wind": 4,
            },
            "def_bonus": 12,
            "mdef_bonus": 4,
            "block_chance": 0,
        }
    elif arch in ("Campus Bully", "Hall Monitor"):
        return {
            "armor_type": "light",
            "protection_types": ["physical"],
            "base_dt": 7,
            "type_dt": {
                "physical": 8, "blunt": 7, "slashing": 8, "stabbing": 7,
                "magical": 4,
            },
            "def_bonus": 8,
            "mdef_bonus": 5,
            "block_chance": 10 if arch == "Hall Monitor" else 0,
        }
    elif arch in ("Rival Debater", "Gossip Monger"):
        return {
            "armor_type": "light",
            "protection_types": ["physical"],
            "base_dt": 4,
            "type_dt": {
                "physical": 5, "blunt": 5, "magical": 6,
            },
            "def_bonus": 5,
            "mdef_bonus": 8,
            "block_chance": 0,
        }
    elif arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op", "Cognitohazard Caster"):
        return {
            "armor_type": "magic_robe",
            "protection_types": ["magical"],
            "base_dt": 2,
            "type_dt": {
                "magical": 16, "holy": 14, "dark": 14, "fire": 12, "shock": 12, "ice": 12,
                "poison": 10, "energy": 14, "energy_cell": 14, "physical": 1,
                "earth": 12, "water": 12, "wind": 12,
            },
            "def_bonus": 4,
            "mdef_bonus": 24,
            "block_chance": 0,
        }
    elif arch in ("Security Drone", "Corporate Operative"):
        return {
            "armor_type": "kevlar",
            "protection_types": ["ballistic", "physical"],
            "base_dt": 10,
            "type_dt": {
                "ballistic": 22, "pistol_round": 24, "scatter_shot": 20, "slashing": 12,
                "rifle_round": 8, "arrow": 6, "fire": 2, "magical": 2, "shock": 4, "ice": 2,
                "earth": 3, "water": 2, "wind": 2,
            },
            "def_bonus": 14,
            "mdef_bonus": 8,
            "block_chance": 0,
        }
    elif arch in ("Skirmisher", "Stalker", "Chrome Cyberhound", "Feral Beast", "Void Swarm", "Spatial Stalker"):
        return {
            "armor_type": "light",
            "protection_types": ["physical"],
            "base_dt": 6,
            "type_dt": {
                "slashing": 8, "stabbing": 6, "ballistic": 4,
                "arrow": 8, "pistol_round": 4, "rifle_round": 2,
                "magical": 3, "fire": 2, "shock": 2, "ice": 3,
                "earth": 3, "water": 2, "wind": 3,
            },
            "def_bonus": 6,
            "mdef_bonus": 6,
            "eva_bonus": 8,
            "block_chance": 0,
        }
    return {
        "armor_type": "medium",
        "protection_types": ["physical"],
        "base_dt": 8,
        "type_dt": {
            "physical": 10, "slashing": 10, "stabbing": 8,
            "arrow": 8, "pistol_round": 4, "magical": 4,
            "earth": 4, "water": 4, "wind": 4,
        },
        "def_bonus": 8,
        "mdef_bonus": 6,
        "block_chance": 0,
    }


def get_enemy_weapon_profile(archetype: str) -> dict:
    """Returns the default weapon attack types and damage profile for an enemy archetype."""
    arch = (archetype or "").strip()
    if arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op", "Cognitohazard Caster"):
        return {
            "attack_types": ["ranged"],
            "damage_types": {"magical": 1.0},
            "matk_bonus": 15,
        }
    elif arch in ("Security Drone", "Corporate Operative", "Scrap-Scavenger"):
        return {
            "attack_types": ["ranged"],
            "damage_types": {"ballistic": 1.0},
            "atk_bonus": 14,
        }
    elif arch in ("Guardian", "Heavy Mech", "Heavy Borg", "Cursed Construct"):
        return {
            "attack_types": ["blunt", "hack"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 16,
        }
    elif arch in ("Campus Bully", "Hall Monitor"):
        return {
            "attack_types": ["blunt"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 10,
        }
    elif arch in ("Rival Debater", "Gossip Monger"):
        return {
            "attack_types": ["blunt"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 8,
        }
    elif arch in ("Skirmisher", "Stalker", "Chrome Cyberhound", "Feral Beast", "Spatial Stalker"):
        return {
            "attack_types": ["slash", "thrust"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 12,
        }
    return {
        "attack_types": ["slash", "blunt"],
        "damage_types": {"physical": 1.0},
        "atk_bonus": 10,
    }


# ---------------------------------------------------------------------------
# Anomalous Incursions Conditional Random Encounter Rules
# ---------------------------------------------------------------------------

ANOMALOUS_TIER2_FACILITY_IDS = {
    "loc_hq_containment_sector",
    "loc_platform_zero",
    "loc_inverted_skybridge",
    "loc_endless_dept_store",
    "loc_static_cinema",
    "loc_whispering_paleontology",
    "loc_weeping_crypt",
    "loc_crimson_auction_house",
    "loc_glass_mirage_estate",
    "loc_liminal_residential",
    "loc_flesh_sewer_junction",
    "loc_subterranean_bunker",
    "loc_reactor_silo_7",
    "loc_ghost_freighter",
    "loc_abyssal_drydock",
    "loc_hilltop_shrine",
    "loc_haunted_manor",
    "loc_abandoned_school_wing",
    "loc_13th_stairwell",
    "loc_fog_lighthouse",
    "loc_singing_sea_grotto",
    "loc_crooked_monolith",
    "loc_woods_staircase",
    "loc_tp_mirror_labyrinth",
    "loc_tp_midnight_carousel",
    "loc_et_weeping_statues",
    "loc_et_fox_torii_tunnel",
    "loc_ap_ghost_runway",
    "loc_ap_baggage_void",
    "loc_hosp_floor_13",
    "loc_hosp_theater_zero",
    "loc_uni_parapsych_lab",
    "loc_uni_escher_stairwell",
    "loc_ct_paper_opera",
    "loc_ct_blood_jade_vault",
    "loc_uc_ossuary_catacombs",
    "loc_uc_fault_monolith",
    "loc_bz_carnivorous_dome",
    "loc_bz_tank_nine",
    "loc_cult_sanctum_hq",
    "loc_clandestine_syndicate_hq",
    "sub_cult_threshold",
    "sub_cult_altar",
    "sub_cult_reliquary",
    "sub_cult_catacombs",
    "sub_cult_scriptorium",
    "sub_cult_sanctum",
    "sub_synd_loading",
    "sub_synd_auction",
    "sub_synd_vault",
    "sub_synd_chop_shop",
    "sub_synd_ledger",
    "sub_synd_penthouse",
}

ANOMALOUS_FACILITY_NAME_KEYWORDS = (
    "anomaly", "quarantined", "platform zero", "inverted skybridge", "endless department",
    "static cinema", "whispering paleontology", "weeping bell-tower", "weeping crypt",
    "crimson masquerade", "glass mirage", "room 404", "flesh-stitched", "reactor silo",
    "ghost freighter", "abyssal drydock", "haunted hill", "13th stairwell", "abandoned old campus",
    "fog-locked lighthouse", "singing sea grotto", "crooked monolith", "staircase in the woods",
    "hall of mirrors", "reversed calliope", "weeping statues", "fox-spirit torii",
    "ghost flight", "endless baggage", "floor 13", "operating theater 0", "parapsychology lab",
    "non-euclidean", "paper-effigy", "blood-jade", "bone-ossuary", "obsidian monolith",
    "carnivorous flora", "tank 9", "containment & quarantine sector",
)


def is_anomalous_danger_zone(
    location_name: str = "",
    location_id: str = "",
    current_minute: int = 720,
    session_id: int = 0,
    scen_key: str = "anomalous_incursions",
) -> bool:
    """
    Returns True ONLY when the player is inside one of the 40 Anomalous Tier-2 Facilities
    OR inside the Theme Park Zone (`zone_theme_park`) during its 22:00-08:00 Anomalous Shift.
    """
    loc_id_low = str(location_id or "").strip().lower()
    loc_name_low = str(location_name or "").strip().lower()

    if any(fid in loc_id_low for fid in ANOMALOUS_TIER2_FACILITY_IDS):
        return True

    if any(kw in loc_name_low for kw in ANOMALOUS_FACILITY_NAME_KEYWORDS):
        return True

    if session_id:
        try:
            import db
            nodes = db.get_session_world_nodes(session_id) or []
            for n in nodes:
                nid = str(n.get("node_id") or "").lower()
                nname = str(n.get("name") or "").lower()
                pid = str(n.get("parent_id") or "").lower()
                if (nid in ANOMALOUS_TIER2_FACILITY_IDS or pid in ANOMALOUS_TIER2_FACILITY_IDS) and nname and nname in loc_name_low:
                    return True
        except Exception:
            pass

    tod = int(current_minute or 0) % 1440
    is_anomalous_shift = (tod >= 1320 or tod < 480)
    if is_anomalous_shift:
        if any(k in loc_id_low for k in ("zone_theme_park", "loc_theme_park", "loc_tp_")):
            return True
        if any(k in loc_name_low for k in ("theme park", "amusement park", "carnival", "wonderland", "funfair", "ferris wheel", "roller coaster", "carousel", "midway")):
            return True
        if session_id:
            try:
                from mechanics.world.locations.seeds import get_session_urban_facility_name
                tp_name = get_session_urban_facility_name(session_id, "zone_seaside_beach", "loc_theme_park", "Theme Park & Amusement Resort", scen_key).lower()
                if tp_name and tp_name in loc_name_low:
                    return True
            except Exception:
                pass

    return False


def should_allow_random_encounter(
    scen_key: str,
    location_name: str = "",
    location_id: str = "",
    current_minute: int = 720,
    session_id: int = 0,
) -> Tuple[bool, float]:
    """Determines whether random encounters can occur and at what probability."""
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scen_key):
            if session_id:
                try:
                    from mechanics.world.anomalous_events import get_active_incursion_at_location
                    if get_active_incursion_at_location(
                        session_id,
                        location_str=location_name,
                        node_id=location_id,
                    ):
                        return False, 0.0
                except Exception:
                    pass
            if is_anomalous_danger_zone(
                location_name=location_name,
                location_id=location_id,
                current_minute=current_minute,
                session_id=session_id,
                scen_key=scen_key,
            ):
                return True, 0.25
            return False, 0.0
    except Exception:
        pass
    return True, 0.08


# ---------------------------------------------------------------------------
# Scenario Enemy Templates, Keywords & Key Resolution
# ---------------------------------------------------------------------------

SCENARIO_ENEMY_TEMPLATES = {
    "fantasy": [
        {"name": "Riftbound Gargoyle", "archetype": "Guardian", "category": ["construct", "demon"], "form": "corporeal", "essence": "arcane"},
        {"name": "Ward-Bound Shade Knight", "archetype": "Brute", "category": ["undead", "humanoid"], "form": "corporeal", "essence": "occult"},
        {"name": "Arcane Golem", "archetype": "Caster", "category": ["construct"], "form": "corporeal", "essence": "arcane"},
        {"name": "Corrupted Treant", "archetype": "Guardian", "category": ["plant", "aberration"], "form": "corporeal", "essence": "primal"},
        {"name": "Void Specter", "archetype": "Caster", "category": ["undead", "aberration"], "form": "incorporeal", "essence": "occult"},
        {"name": "Goblin Skirmisher", "archetype": "Skirmisher", "category": ["humanoid", "beast"], "form": "corporeal", "essence": "mundane"},
        {"name": "Orc Marauder", "archetype": "Brute", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Dark Elf Assassin", "archetype": "Stalker", "category": ["humanoid"], "form": "corporeal", "essence": "arcane"}
    ],
    "scifi": [
        {"name": "Void Parasite", "archetype": "Void Swarm", "category": ["alien", "beast"], "form": "swarm", "essence": "biological"},
        {"name": "Plasma Sentry Drone", "archetype": "Security Drone", "category": ["robot"], "form": "corporeal", "essence": "technological"},
        {"name": "Alien Swarm-Drone", "archetype": "Void Swarm", "category": ["alien", "robot"], "form": "swarm", "essence": "cybernetic"},
        {"name": "Rogue Security Mech", "archetype": "Heavy Mech", "category": ["construct", "robot"], "form": "corporeal", "essence": "technological"},
        {"name": "Xeno-Stalker", "archetype": "Security Drone", "category": ["alien"], "form": "corporeal", "essence": "biological"},
        {"name": "Cyborg Mercenary", "archetype": "Heavy Mech", "category": ["cyborg", "humanoid"], "form": "corporeal", "essence": "cybernetic"},
        {"name": "Nanite Swarm", "archetype": "Psionic Alien", "category": ["robot"], "form": "swarm", "essence": "nanotech"}
    ],
    "cyberpunk": [
        {"name": "Rogue Enforcer Drone", "archetype": "Security Drone", "category": ["robot"], "form": "corporeal", "essence": "technological"},
        {"name": "Chrome Cyberhound", "archetype": "Chrome Cyberhound", "category": ["cyborg", "beast"], "form": "corporeal", "essence": "cybernetic"},
        {"name": "Corporate Operative", "archetype": "Corporate Operative", "category": ["humanoid"], "form": "corporeal", "essence": "cybernetic"},
        {"name": "Street Samurai", "archetype": "Heavy Borg", "category": ["cyborg", "humanoid"], "form": "corporeal", "essence": "cybernetic"},
        {"name": "Netrunner Phantom", "archetype": "Netrunner Spec-Op", "category": ["humanoid"], "form": "incorporeal", "essence": "technological"},
        {"name": "Synth-Thug", "archetype": "Chrome Cyberhound", "category": ["android", "humanoid"], "form": "corporeal", "essence": "technological"},
        {"name": "Heavy Borg", "archetype": "Heavy Borg", "category": ["cyborg"], "form": "corporeal", "essence": "cybernetic"}
    ],
    "steampunk": [
        {"name": "Clockwork Automaton", "archetype": "Heavy Mech", "category": ["construct"], "form": "corporeal", "essence": "clockwork"},
        {"name": "Steam-Exo Enforcer", "archetype": "Brute", "category": ["humanoid", "cyborg"], "form": "corporeal", "essence": "steam_powered"},
        {"name": "Brass Gutter-Sniper", "archetype": "Stalker", "category": ["humanoid"], "form": "corporeal", "essence": "pneumatic"},
        {"name": "Aether Chemist", "archetype": "Caster", "category": ["humanoid"], "form": "corporeal", "essence": "alchemical"},
        {"name": "Pneumatic Smasher", "archetype": "Guardian", "category": ["construct", "robot"], "form": "corporeal", "essence": "pneumatic"},
        {"name": "Smog Specter", "archetype": "Void Swarm", "category": ["aberration"], "form": "incorporeal", "essence": "alchemical"}
    ],
    "dark_fantasy": [
        {"name": "Heresy Inquisitor", "archetype": "Guardian", "category": ["humanoid"], "form": "corporeal", "essence": "divine"},
        {"name": "Flayed Penitent", "archetype": "Skirmisher", "category": ["undead", "humanoid"], "form": "corporeal", "essence": "occult"},
        {"name": "Blood Hag", "archetype": "Caster", "category": ["humanoid", "demon"], "form": "corporeal", "essence": "occult"},
        {"name": "Grave Rotter", "archetype": "Brute", "category": ["undead"], "form": "corporeal", "essence": "occult"},
        {"name": "Flesh Abomination", "archetype": "Guardian", "category": ["aberration", "beast"], "form": "corporeal", "essence": "primal"},
        {"name": "Plague Swarm", "archetype": "Void Swarm", "category": ["beast", "insectoid"], "form": "swarm", "essence": "occult"}
    ],
    "isekai_fantasy": [
        {"name": "Demon Lord Vanguard", "archetype": "Brute", "category": ["demon", "humanoid"], "form": "corporeal", "essence": "arcane"},
        {"name": "Goblin Shaman", "archetype": "Caster", "category": ["humanoid"], "form": "corporeal", "essence": "primal"},
        {"name": "Horned Crimson Boar", "archetype": "Feral Beast", "category": ["beast"], "form": "corporeal", "essence": "mundane"},
        {"name": "Dire Slime King", "archetype": "Guardian", "category": ["aberration"], "form": "corporeal", "essence": "arcane"},
        {"name": "Cursed Marionette", "archetype": "Stalker", "category": ["construct"], "form": "corporeal", "essence": "occult"}
    ],
    "highschool": [
        {"name": "Rival Campus Debater", "archetype": "Rival Debater", "category": ["humanoid"], "form": "corporeal", "essence": "academic"},
        {"name": "Corrupted Mascot", "archetype": "Campus Bully", "category": ["humanoid", "beast"], "form": "corporeal", "essence": "athletic"},
        {"name": "Campus Bully", "archetype": "Campus Bully", "category": ["humanoid"], "form": "corporeal", "essence": "delinquent"},
        {"name": "Hall Monitor Drone", "archetype": "Hall Monitor", "category": ["robot"], "form": "corporeal", "essence": "technological"},
        {"name": "Enraged Teacher", "archetype": "Rival Debater", "category": ["humanoid"], "form": "corporeal", "essence": "bureaucratic"},
        {"name": "Possessed Gym Equipment", "archetype": "Campus Bully", "category": ["construct"], "form": "corporeal", "essence": "athletic"},
        {"name": "Gossip Monger", "archetype": "Gossip Monger", "category": ["humanoid"], "form": "corporeal", "essence": "academic"}
    ],
    "postapoc": [
        {"name": "Irradiated Mutant", "archetype": "Rad-Mutant", "category": ["mutant", "humanoid"], "form": "corporeal", "essence": "irradiated"},
        {"name": "Scrap-Metal Construct", "archetype": "Heavy Mech", "category": ["construct", "robot"], "form": "corporeal", "essence": "scrap_rigged"},
        {"name": "Feral Wastelander", "archetype": "Scrap-Scavenger", "category": ["humanoid"], "form": "corporeal", "essence": "feral"},
        {"name": "Rad-Scorpion", "archetype": "Feral Beast", "category": ["beast", "insectoid"], "form": "corporeal", "essence": "irradiated"},
        {"name": "Wasteland Raider", "archetype": "Rad-Mutant", "category": ["humanoid"], "form": "corporeal", "essence": "chem_fueled"},
        {"name": "Toxic Abomination", "archetype": "Toxic Abomination", "category": ["mutant", "aberration"], "form": "corporeal", "essence": "irradiated"},
        {"name": "Mutated Bear", "archetype": "Rad-Mutant", "category": ["beast", "mutant"], "form": "corporeal", "essence": "irradiated"}
    ],
    "slice_of_life": [
        {"name": "Back-Alley Street Thug", "archetype": "Brute", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Syndicate Debt Collector", "archetype": "Stalker", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Rowdy Nightclub Bouncer", "archetype": "Guardian", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Underpass Moto Punk", "archetype": "Skirmisher", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Billiards Hall Hustler", "archetype": "Skirmisher", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Rival Gym Brawler", "archetype": "Brute", "category": ["humanoid"], "form": "corporeal", "essence": "mundane"},
        {"name": "Stray Alley Hound", "archetype": "Feral Beast", "category": ["beast"], "form": "corporeal", "essence": "mundane"}
    ],
    "anomalous_incursions": [
        {"name": "Signal Choir Wraith", "archetype": "Cognitohazard Caster", "category": ["aberration", "incorporeal", "cognitohazard", "spectral_echo"], "form": "incorporeal", "essence": "psionic"},
        {"name": "Redacted Broadcast Phantom", "archetype": "Cognitohazard Caster", "category": ["undead", "aberration", "cognitohazard", "spectral_echo"], "form": "incorporeal", "essence": "occult"},
        {"name": "Non-Euclidean Stalker", "archetype": "Spatial Stalker", "category": ["aberration", "spatial_warp"], "form": "corporeal", "essence": "eldritch"},
        {"name": "Subway Rift Hound", "archetype": "Spatial Stalker", "category": ["aberration", "beast", "spatial_warp"], "form": "corporeal", "essence": "eldritch"},
        {"name": "Amalgamated Flesh Weaver", "archetype": "Bio-Horror Brute", "category": ["aberration", "demon", "bio_aberration"], "form": "corporeal", "essence": "biological"},
        {"name": "Parasitic Spore Swarm", "archetype": "Void Swarm", "category": ["aberration", "swarm", "bio_aberration"], "form": "swarm", "essence": "biological"},
        {"name": "Weeping Concrete Effigy", "archetype": "Cursed Construct", "category": ["construct", "cursed_relic"], "form": "corporeal", "essence": "occult"},
        {"name": "Animated Mannequin Collective", "archetype": "Cursed Construct", "category": ["construct", "undead", "cursed_relic"], "form": "corporeal", "essence": "occult"},
        {"name": "Rift-Cult Fanatic", "archetype": "Caster", "category": ["humanoid", "cognitohazard"], "form": "corporeal", "essence": "occult"},
        {"name": "Syndicate Relic Enforcer", "archetype": "Corporate Operative", "category": ["humanoid", "cursed_relic"], "form": "corporeal", "essence": "technological"}
    ]
}

SCENARIO_ENEMIES = {k: [(t["name"], t["archetype"]) for t in v] for k, v in SCENARIO_ENEMY_TEMPLATES.items()}


def _resolve_enemy_scenario_key(scenario: str) -> str:
    """Normalizes scenario names, variants, and custom combinator strings to SCENARIO_ENEMY_TEMPLATES keys."""
    scen = (scenario or "fantasy").lower().strip()
    if scen in SCENARIO_ENEMY_TEMPLATES:
        return scen
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scen):
            return "anomalous_incursions"
    except Exception:
        pass
    if any(w in scen for w in ("anomalous_incursions", "urban_anomalies", "urban_fantasy")):
        return "anomalous_incursions"
    if "slice_of_life" in scen or "slice" in scen:
        return "slice_of_life"
    if "dark_fantasy" in scen:
        return "dark_fantasy"
    if "isekai" in scen:
        return "isekai_fantasy"
    if "steampunk" in scen or "clockwork" in scen:
        return "steampunk"
    if "cyberpunk" in scen or "cyber" in scen:
        return "cyberpunk"
    if any(w in scen for w in ("sci_fi", "scifi", "space")):
        return "scifi"
    if any(w in scen for w in ("postapoc", "apocalypse", "wasteland", "nuclear")):
        return "postapoc"
    if any(w in scen for w in ("high_school", "highschool", "school", "academy")):
        return "highschool"
    return "fantasy"


GENERIC_ENEMY_KEYWORDS = {
    "raider", "skirmisher", "bandit", "soldier", "guard", "grunt", "minion", "cultist",
    "thug", "warrior", "archer", "mage", "drone", "scout", "sentry", "hound", "wolf",
    "goblin", "orc", "skeleton", "zombie", "mutant", "specter", "golem", "construct",
    "beast", "swarm", "spider", "mercenary", "trooper", "enforcer", "peasant", "brigand",
    "pirate", "scavenger", "assassin", "operative", "parasite", "shade", "knight", "crawler",
    "fiend", "ghoul", "slime", "elemental", "abomination", "creature", "monster", "cyberhound",
    "debater", "bully", "monitor", "monger", "mutated", "feral", "automaton", "inquisitor",
    "penitent", "shaman", "bouncer", "collector", "punk", "hustler", "brawler"
}
