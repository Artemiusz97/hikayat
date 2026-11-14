from __future__ import annotations

import random
import re

from .loadouts import (
    ALL_STATS,
    ARCHETYPE_RULES,
    ROLE_TIER_MULTIPLIERS,
    TIER_RANK_TO_ROLE,
    build_combatant_stat_sheet,
    ensure_combatant_loadout,
)
from .enemy_profiles import (
    ANOMALOUS_FACILITY_NAME_KEYWORDS,
    ANOMALOUS_TIER2_FACILITY_IDS,
    GENERIC_ENEMY_KEYWORDS,
    SCENARIO_ENEMIES,
    SCENARIO_ENEMY_TEMPLATES,
    _resolve_enemy_scenario_key,
    get_enemy_armor_profile,
    get_enemy_weapon_profile,
    is_anomalous_danger_zone,
    should_allow_random_encounter,
)

# Scenario Archetype Stat Rules
# ARCHETYPE_RULES is canonicalized in mechanics.combat.loadouts and re-exported above.
# SCENARIO_ENEMY_TEMPLATES / GENERIC_ENEMY_KEYWORDS are canonicalized in enemy_profiles.py.

def is_generic_enemy_name(name: str) -> bool:
    """Detects if an enemy name is a generic troop/monster type rather than a unique proper-named character."""
    if not name or not isinstance(name, str):
        return True
    
    clean = re.sub(r'\s+(?:#?\d+|[A-Z])$', '', name.strip()).lower()
    words = clean.split()

    for pool in SCENARIO_ENEMIES.values():
        for item in pool:
            if clean == item[0].lower() or item[0].lower() in clean:
                return True

    if any(w in GENERIC_ENEMY_KEYWORDS for w in words):
        return True

    return False


def disambiguate_enemy_list(enemies: list) -> list:
    """Ensures unique named characters are never duplicated, while multiple generic enemies
    of the same type receive clean numbered suffixes (e.g. 'Mountain Raider #1', 'Mountain Raider #2')."""
    if not isinstance(enemies, list):
        return []

    def get_base_name(n: str) -> str:
        return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(n).strip())

    name_counts = {}
    for raw_m in enemies:
        if not isinstance(raw_m, dict) or not raw_m.get("name"):
            continue
        base = get_base_name(raw_m["name"])
        name_counts[base.lower()] = name_counts.get(base.lower(), 0) + 1

    cleaned = []
    seen_unique_names = set()
    type_indices = {}

    for raw_m in enemies:
        if not isinstance(raw_m, dict) or not raw_m.get("name"):
            continue
        m = dict(raw_m)
        raw_name = m["name"]
        base = get_base_name(raw_name)
        base_lower = base.lower()

        is_generic = is_generic_enemy_name(base)

        if not is_generic:
            if base_lower in seen_unique_names:
                continue
            seen_unique_names.add(base_lower)
            m["name"] = base
            cleaned.append(m)
        else:
            type_indices[base_lower] = type_indices.get(base_lower, 0) + 1
            if name_counts[base_lower] > 1:
                idx = type_indices[base_lower]
                m["name"] = f"{base} #{idx}"
            else:
                m["name"] = base
            cleaned.append(m)

    return cleaned


def build_enemy_stat_sheet(
    level: int,
    archetype_name: str = None,
    custom_primary: list = None,
    custom_forbidden: list = None,
    exact_extra_points: int = None,
    role_tier: str = "standard",
) -> dict:
    return build_combatant_stat_sheet(
        level=level,
        archetype_name=archetype_name,
        role_tier=role_tier,
        custom_primary=custom_primary,
        custom_forbidden=custom_forbidden,
        exact_extra_points=exact_extra_points,
    )

build_monster_stat_sheet = build_enemy_stat_sheet

def build_companion_stat_sheet(level: int, archetype_name: str = None) -> dict:
    return build_combatant_stat_sheet(
        level=level,
        archetype_name=archetype_name,
        role_tier="companion",
    )

# =====================================================================
# AFFIX ENGINE & DYNAMIC TAXONOMY (Phase 1)
# =====================================================================

AFFIX_REGISTRY = {
    "Volatile": {
        "type": "prefix",
        "allowed_essences": ["arcane", "alchemical", "energy", "irradiated", "cybernetic", "clockwork"],
        "forbidden_categories": ["water_elemental", "ice_beast"],
        "forbidden_weaknesses": ["fire"],
        "grants_resistances": ["fire", "explosive"],
        "grants_weaknesses": ["ice"]
    },
    "Overclocked": {
        "type": "prefix",
        "allowed_categories": ["robot", "android", "construct", "cyborg"],
        "allowed_essences": ["technological", "cybernetic", "clockwork", "steam_powered", "pneumatic"],
        "grants_resistances": ["shock"],
        "grants_weaknesses": ["acid"]
    },
    "Vampiric": {
        "type": "prefix",
        "allowed_forms": ["corporeal", "swarm"],
        "forbidden_categories": ["robot", "android", "construct", "golem"],
        "grants_resistances": ["dark", "poison"],
        "grants_weaknesses": ["holy", "fire"]
    },
    "Phasing": {
        "type": "prefix",
        "allowed_essences": ["arcane", "occult", "technological", "psionic"],
        "grants_resistances": ["physical", "slashing", "bludgeoning", "stabbing"],
        "grants_weaknesses": ["magical", "energy", "shock"]
    },
    "Corrosive": {
        "type": "prefix",
        "allowed_categories": ["mutant", "beast", "aberration", "alien"],
        "allowed_essences": ["biological", "irradiated", "alchemical"],
        "grants_resistances": ["acid", "poison"],
        "grants_weaknesses": ["fire"]
    },
    "Grounded": {
        "type": "prefix",
        "allowed_categories": ["construct", "golem", "beast", "mutant"],
        "allowed_forms": ["corporeal"],
        "grants_resistances": ["earth", "shock"],
        "grants_weaknesses": ["water"]
    },
    "Hydro-Shielded": {
        "type": "prefix",
        "allowed_categories": ["robot", "construct", "android"],
        "allowed_forms": ["corporeal"],
        "allowed_essences": ["alchemical", "steam_powered", "technological"],
        "grants_resistances": ["fire", "water"],
        "grants_weaknesses": ["shock", "ice"]
    },
    "Tempest-Wreathed": {
        "type": "prefix",
        "allowed_categories": ["beast", "humanoid", "demon"],
        "allowed_forms": ["corporeal"],
        "allowed_essences": ["arcane", "primal", "occult"],
        "grants_resistances": ["wind", "ranged"],
        "grants_weaknesses": ["earth"]
    }
}

def derive_taxonomy_weaknesses(categories: list, form: str, essence: str) -> tuple[list, list, list]:
    """Returns (resistances, weaknesses, immunities) based on taxonomy tags."""
    resistances, weaknesses, immunities = [], [], []
    
    if form in ("incorporeal", "ethereal"):
        immunities.extend(["bleed", "poison"])
        resistances.extend(["physical", "slashing", "bludgeoning", "stabbing"])
        weaknesses.extend(["magical", "energy", "holy"])
    elif form == "swarm":
        resistances.extend(["stabbing", "ballistic", "piercing"])
        weaknesses.extend(["fire", "explosive", "aoe"])
        
    for cat in categories:
        if cat in ("construct", "robot", "golem", "android"):
            immunities.extend(["poison", "bleed", "mental"])
            weaknesses.extend(["shock", "acid", "water"])
            resistances.extend(["slashing", "piercing", "stabbing", "wind"])
        elif cat in ("undead", "demon"):
            immunities.extend(["poison", "dark"])
            weaknesses.extend(["holy", "fire"])
            resistances.extend(["cold"])
        elif cat in ("beast", "mutant"):
            weaknesses.extend(["fire"])
            resistances.extend(["earth"])
        elif cat in ("plant",):
            weaknesses.extend(["fire", "slashing"])
            resistances.extend(["water", "earth", "bludgeoning"])
        elif cat in ("aquatic", "marine"):
            weaknesses.extend(["shock", "ice"])
            resistances.extend(["water", "fire"])
        elif cat == "cognitohazard":
            resistances.extend(["physical", "ballistic"])
            weaknesses.extend(["holy", "shock", "magical"])
        elif cat == "spatial_warp":
            resistances.extend(["ranged", "ballistic", "wind"])
            weaknesses.extend(["earth", "ice", "holy"])
        elif cat == "bio_aberration":
            resistances.extend(["poison", "bludgeoning"])
            weaknesses.extend(["fire", "slashing"])
        elif cat == "cursed_relic":
            immunities.extend(["poison", "bleed"])
            resistances.extend(["slashing", "piercing"])
            weaknesses.extend(["holy", "bludgeoning", "shock"])
        elif cat == "spectral_echo":
            immunities.extend(["bleed", "poison"])
            resistances.extend(["physical", "slashing"])
            weaknesses.extend(["holy", "fire", "magical"])
            
    if essence in ("technological", "cybernetic"):
        weaknesses.extend(["shock"])
    elif essence in ("irradiated", "chem_fueled"):
        resistances.extend(["poison", "acid"])
        
    return list(set(resistances)), list(set(weaknesses)), list(set(immunities))

def roll_enemy_affixes(tier_rank: int, categories: list, form: str, essence: str, base_weaknesses: list) -> list:
    if tier_rank <= 2:
        return []
    
    num_affixes = 1 if tier_rank == 3 else (2 if tier_rank >= 4 else 0)
    valid_affixes = []
    
    for affix_name, affix_data in AFFIX_REGISTRY.items():
        if affix_data.get("allowed_essences") and essence not in affix_data["allowed_essences"]:
            continue
        if affix_data.get("allowed_forms") and form not in affix_data["allowed_forms"]:
            continue
        if affix_data.get("allowed_categories") and not any(c in affix_data["allowed_categories"] for c in categories):
            continue
        if affix_data.get("forbidden_categories") and any(c in affix_data["forbidden_categories"] for c in categories):
            continue
        if affix_data.get("forbidden_weaknesses") and any(w in affix_data["forbidden_weaknesses"] for w in base_weaknesses):
            continue
            
        valid_affixes.append(affix_name)
        
    if not valid_affixes:
        return []
        
    random.shuffle(valid_affixes)
    return valid_affixes[:num_affixes]

# =====================================================================
# ENCOUNTER GENERATION & TIER SCALING
# =====================================================================

def roll_encounter_difficulty() -> tuple[int, float]:
    roll = random.random()
    if roll < 0.40:
        return random.randint(-3, -2), 0.75
    elif roll < 0.95:
        return random.randint(-1, 1), 1.0
    else:
        return random.randint(3, 5), 2.25


def infer_taxonomy_from_archetype(archetype: str, scenario: str = "fantasy") -> tuple[list, str, str]:
    """Infers fallback category, form, and essence when custom enemies lack explicit templates."""
    arch = (archetype or "").strip()
    scen = (scenario or "fantasy").lower()

    if arch in ("Security Drone", "Heavy Mech", "Heavy Borg"):
        return ["construct", "robot"], "corporeal", "technological"
    if arch == "Cognitohazard Caster":
        return ["aberration", "incorporeal", "cognitohazard", "spectral_echo"], "incorporeal", "psionic"
    if arch == "Spatial Stalker":
        return ["aberration", "spatial_warp"], "corporeal", "eldritch"
    if arch == "Bio-Horror Brute":
        return ["aberration", "demon", "bio_aberration"], "corporeal", "biological"
    if arch == "Cursed Construct":
        return ["construct", "cursed_relic"], "corporeal", "occult"
    if arch in ("Netrunner Spec-Op", "Chrome Cyberhound"):
        return ["humanoid" if "Netrunner" in arch else "beast", "cybernetic"], "corporeal", "cybernetic"
    if arch in ("Corporate Operative", "Campus Bully", "Rival Debater", "Hall Monitor", "Gossip Monger", "Scrap-Scavenger"):
        return ["humanoid"], "corporeal", "mundane"
    if arch in ("Psionic Alien",):
        return ["alien"], "corporeal", "psionic"
    if arch in ("Rad-Mutant", "Toxic Abomination"):
        return ["mutant", "abomination"], "corporeal", "irradiated"
    if arch in ("Feral Beast",):
        return ["beast"], "corporeal", "mundane"
    if arch in ("Void Swarm",):
        return ["voidborn"], "swarm", "eldritch"
    if arch in ("Caster",):
        return ["humanoid"], "corporeal", "arcane"
    if arch in ("Stalker", "Skirmisher", "Guardian", "Brute"):
        if scen in ("scifi", "cyberpunk"):
            return ["humanoid"], "corporeal", "cybernetic"
        elif scen in ("steampunk",):
            return ["construct", "automaton"] if "mech" in arch.lower() else ["humanoid"], "corporeal", "clockwork"
        elif scen in ("dark_fantasy",):
            return ["undead"], "corporeal", "occult"
        else:
            return ["humanoid"], "corporeal", "mundane"

    return ["humanoid"], "corporeal", "mundane"


CANONICAL_INTENT_CODES = {
    "heavy": [
        "winding up a heavy swing", "preparing a devastating crush",
        "overcharging weapons", "lashing out with mutated tendrils",
        "heavy", "crush", "overcharging", "tendrils"
    ],
    "magic": [
        "channeling a massive spell", "drawing arcane energy",
        "preparing a burst", "broadcasting a cognitohazardous frequency",
        "spell", "arcane", "burst", "cognitohazardous", "channeling", "magic"
    ],
    "ambush": [
        "preparing to ambush", "fading into shadows", "targeting the weak",
        "folding spatial vectors for a blink-strike", "ambush", "shadows",
        "blink-strike", "spatial vectors"
    ],
    "defensive": [
        "assuming a defensive posture", "shielding allies", "preparing a counter",
        "hardening its cursed exterior", "defensive", "shielding", "counter",
        "hardening", "analyzing targets", "shifting stance"
    ],
    "swarm": [
        "preparing to swarm", "multiplying rapidly", "swarm", "multiplying"
    ],
    "basic": [
        "preparing next strike", "basic strike", "attacking"
    ]
}


def get_intent_code(intent_label: str) -> str:
    """Deterministically extracts canonical intent_code token from an intent label."""
    if not intent_label:
        return "basic"
    lbl = str(intent_label).lower().strip()
    for code, keywords in CANONICAL_INTENT_CODES.items():
        if any(kw in lbl for kw in keywords):
            return code
    return "basic"


def roll_enemy_intent(archetype: str) -> str:
    """Generates an initial or round-based telegraphed combat intent based on archetype."""
    arch = (archetype or "Brute").strip()
    intents = ["Preparing next strike", "Analyzing targets", "Shifting stance"]
    if arch in ("Stalker", "Assassin", "Dark Elf Assassin", "Spatial Stalker"):
        intents = ["Preparing to Ambush", "Fading into shadows", "Targeting the weak", "Folding spatial vectors for a blink-strike"]
    elif arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op", "Cognitohazard Caster"):
        intents = ["Channeling a massive spell", "Drawing arcane energy", "Preparing a burst", "Broadcasting a cognitohazardous frequency"]
    elif arch in ("Brute", "Heavy Mech", "Heavy Borg", "Bio-Horror Brute"):
        intents = ["Winding up a heavy swing", "Preparing a devastating crush", "Overcharging weapons", "Lashing out with mutated tendrils"]
    elif arch in ("Guardian", "Corrupted Treant", "Cursed Construct"):
        intents = ["Assuming a defensive posture", "Shielding allies", "Preparing a counter", "Hardening its cursed exterior"]
    elif arch == "Void Swarm":
        intents = ["Preparing to swarm", "Multiplying rapidly"]
    return random.choice(intents)


def generate_scenario_enemy(scenario: str, location: str, chapter: int, custom_name: str = None,
                            custom_archetype: str = None, custom_primary: list = None, custom_forbidden: list = None,
                            exact_tier: int = None, exact_extra_points: int = None,
                            exact_level: int = None,
                            language: str = "en") -> dict:
    scenario_lower = _resolve_enemy_scenario_key(scenario)
    
    template = None
    if custom_name:
        name = custom_name
        arch_name = custom_archetype or "Brute"
        # Try to find a matching template by name to extract category/form/essence
        for pool in SCENARIO_ENEMY_TEMPLATES.values():
            for t in pool:
                if t["name"].lower() == name.lower():
                    template = t
                    break
            if template: break
    else:
        pool = SCENARIO_ENEMY_TEMPLATES.get(scenario_lower, SCENARIO_ENEMY_TEMPLATES["fantasy"])
        template = random.choice(pool)
        name, arch_name = template["name"], template["archetype"]
        if scenario_lower == "anomalous_incursions":
            try:
                import namegen
                anom_tags = [c for c in (template.get("category") or []) if c in ("cognitohazard", "spatial_warp", "bio_aberration", "cursed_relic", "spectral_echo")]
                cat_tag = anom_tags[0] if anom_tags else "spatial_warp"
                name = namegen.generate_anomalous_entity_name(category_tag=cat_tag)
            except Exception:
                pass
        
    if custom_archetype:
        arch_name = custom_archetype

    if template:
        category = template["category"]
        form = template["form"]
        essence = template["essence"]
    else:
        category, form, essence = infer_taxonomy_from_archetype(arch_name, scenario_lower)

    if exact_level is not None:
        level = max(1, int(exact_level))
    else:
        level = max(1, chapter + random.randint(0, 1))
    
    if exact_tier is not None:
        tier_rank = exact_tier
    else:
        roll = random.random()
        if roll < 0.05:
            tier_rank = 4 # Miniboss
        elif roll < 0.20:
            tier_rank = 3 # Elite
        elif roll < 0.60:
            tier_rank = 2 # Standard
        else:
            tier_rank = 1 # Minion

    # Map rank to semantic tier
    semantic_tiers = {1: "minion", 2: "standard", 3: "elite", 4: "miniboss", 5: "boss"}
    tier_type = semantic_tiers.get(tier_rank, "standard")

    if tier_rank >= 5:
        max_hp = 150 + (level * 25)
    elif tier_rank == 4:
        max_hp = 100 + (level * 20)
    elif tier_rank == 3:
        max_hp = 65 + (level * 15)
    elif tier_rank == 2:
        max_hp = 35 + (level * 8)
    else:
        max_hp = 25 + (level * 5)
        
    variance = random.uniform(0.9, 1.1)
    max_hp = int(max_hp * variance)
    if scenario_lower == "highschool":
        max_hp = int(max_hp * 1.55)
    max_mp = 10 + (level * 3)
    
    role_tier = TIER_RANK_TO_ROLE.get(int(tier_rank or 2), "standard")
    stat_sheet = build_enemy_stat_sheet(level, arch_name, custom_primary, custom_forbidden, exact_extra_points=exact_extra_points, role_tier=role_tier)

    base_res, base_weak, base_imm = derive_taxonomy_weaknesses(category, form, essence)
    
    affixes = roll_enemy_affixes(tier_rank, category, form, essence, base_weak)
    
    for afx in affixes:
        afx_data = AFFIX_REGISTRY[afx]
        base_res.extend(afx_data.get("grants_resistances", []))
        base_weak.extend(afx_data.get("grants_weaknesses", []))
        # Remove conflicting weaknesses if granted resistance
        base_weak = [w for w in base_weak if w not in base_res]

    from localization import translate_affix
    display_affix = translate_affix(affixes[0], language) if affixes else ""
    final_name = f"{display_affix} {name}" if display_affix else name
    initial_intent = roll_enemy_intent(arch_name) if tier_rank >= 3 else None
    initial_intent_code = get_intent_code(initial_intent) if initial_intent else None

    enemy_dict = {
        "name": final_name,
        "base_name": name,
        "level": level,
        "tier": tier_type,
        "tier_rank": tier_rank,
        "archetype": arch_name,
        "category": category,
        "form": form,
        "essence": essence,
        "affixes": affixes,
        "intent": initial_intent,
        "intent_code": initial_intent_code,
        "weapon_profile": get_enemy_weapon_profile(arch_name),
        "armor_profile": get_enemy_armor_profile(arch_name),
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": max_mp,
        "max_mp": max_mp,
        "stats": stat_sheet,
        "status_effects": [],
        "resistances": list(set(base_res)),
        "weaknesses": list(set(base_weak)),
        "immunities": list(set(base_imm))
    }

    if scenario_lower == "anomalous_incursions":
        name_low = str(custom_name or name or "").lower()
        is_human_op = (
            any(k in name_low for k in ("cult", "syndicate", "operative", "hunter", "mercenary", "enforcer", "zealot", "smuggler"))
            or (arch_name in ("Corporate Operative",) and "aberration" not in (category or []))
        )
        if is_human_op:
            from mechanics.world.anomaly_engine import ANOMALOUS_ELEMENTS
            elem_pick = random.choice(list(ANOMALOUS_ELEMENTS))
            enemy_dict["is_human_operative"] = True
            enemy_dict["physicality"] = "corporeal"
            enemy_dict["sapience"] = "sapient"
            enemy_dict["equipped_anomalous_element"] = elem_pick
            enemy_dict["element"] = elem_pick
        else:
            try:
                from mechanics.world.anomaly_engine import (
                    generate_anomaly_blueprint,
                    instantiate_enemy_from_blueprint,
                )
                pool_names = {str(t.get("name", "")).lower() for t in SCENARIO_ENEMY_TEMPLATES.get("anomalous_incursions", [])}
                preserve_custom = bool(custom_name and str(custom_name).strip().lower() not in pool_names)
                bp = generate_anomaly_blueprint(
                    location_str=str(location or ""),
                    disposition="hostile",
                    tier_rank=tier_rank,
                    scen_key=str(scenario or "anomalous_incursions"),
                    force_procedural=preserve_custom,
                    # Unique per-encounter seed: a static seed cloned the same anomaly in every room forever
                    seed_key=f"wild:{tier_rank}:{final_name}:{random.getrandbits(32)}",
                )
                if preserve_custom:
                    bp["name"] = final_name
                    bp["canonical_name"] = final_name
                    bp["entity_name"] = final_name
                    bp["codex_id"] = ""
                    bp["is_canonical_folklore"] = False
                enemy_dict = instantiate_enemy_from_blueprint(bp, level=level, tier_rank=tier_rank, base_enemy=enemy_dict)
            except Exception:
                pass

    ensure_combatant_loadout(enemy_dict, scenario_key=scenario_lower)
    return enemy_dict

generate_scenario_monster = generate_scenario_enemy


def generate_balanced_encounter(party_members: list, scenario: str, location: str, chapter: int, language: str = "en") -> tuple[list, float]:
    if not party_members:
        party_members = [{"level": 1, "str_": 2, "per_": 2, "end_": 2, "cha": 1, "int_": 2, "agi": 2, "luk": 1}]

    total_party_additional_stats = 0
    for p in party_members:
        p_obj = p[0] if isinstance(p, (tuple, list)) else p
        if isinstance(p_obj, dict):
            for s in ALL_STATS:
                k = f"{s.lower()}_" if s in ("STR", "PER", "END", "INT") else s.lower()
                val = int(p_obj.get(k, 1))
                total_party_additional_stats += max(0, val - 1)

    if total_party_additional_stats <= 0:
        avg_lvl = max(1, sum(p.get("level", 1) for p in party_members if isinstance(p, dict)) // max(1, len(party_members)))
        total_party_additional_stats = (5 + (avg_lvl - 1)) * max(1, len(party_members))

    level_modifier, xp_multiplier = roll_encounter_difficulty()
    deviation = max(-4, min(4, random.randint(-2, 2) + level_modifier))
    target_enemy_stat_budget = max(3, total_party_additional_stats + deviation)

    party_size = len(party_members)
    roll = random.random()
    if party_size == 1:
        if roll < 0.35: count = 1
        elif roll < 0.70: count = 2
        elif roll < 0.90: count = 3
        else: count = 4
    elif party_size == 2:
        if roll < 0.20: count = 1
        elif roll < 0.60: count = 2
        elif roll < 0.90: count = 3
        else: count = 4
    else:
        if roll < 0.15: count = 2
        elif roll < 0.60: count = 3
        else: count = 4

    if count == 1:
        stat_allocations = [target_enemy_stat_budget]
    elif count == 2:
        split_1 = max(1, int(target_enemy_stat_budget * random.uniform(0.45, 0.55)))
        split_2 = max(1, target_enemy_stat_budget - split_1)
        stat_allocations = [split_1, split_2]
    elif count == 3:
        leader_pts = max(1, int(target_enemy_stat_budget * random.uniform(0.38, 0.46)))
        rem = max(2, target_enemy_stat_budget - leader_pts)
        m1 = max(1, rem // 2)
        m2 = max(1, rem - m1)
        stat_allocations = [leader_pts, m1, m2]
    else:
        leader_pts = max(1, int(target_enemy_stat_budget * random.uniform(0.30, 0.40)))
        rem = max(3, target_enemy_stat_budget - leader_pts)
        p1 = max(1, rem // 3)
        p2 = max(1, rem // 3)
        p3 = max(1, rem - p1 - p2)
        stat_allocations = [leader_pts, p1, p2, p3]

    scenario_lower = _resolve_enemy_scenario_key(scenario)
    pool = SCENARIO_ENEMY_TEMPLATES.get(scenario_lower, SCENARIO_ENEMY_TEMPLATES["fantasy"])
    enemies = []

    for i, extra_pts in enumerate(stat_allocations):
        template = random.choice(pool)
        
        base_name = template["name"]
        arch_name = template["archetype"]
        category = template["category"]
        form = template["form"]
        essence = template["essence"]

        if extra_pts <= 3: enemy_level = 1
        else: enemy_level = max(1, extra_pts - 3)

        if count == 1: tier_rank = 3
        elif count == 2: tier_rank = 2
        elif count >= 3 and i == 0: tier_rank = 3
        else: tier_rank = 1
        
        # Override tier rank if high stat allocation pushes it to miniboss
        if tier_rank == 3 and extra_pts > 15:
            tier_rank = 4

        e_obj = generate_scenario_enemy(
            scenario=scenario_lower, location=location, chapter=chapter,
            custom_name=base_name, custom_archetype=arch_name,
            exact_tier=tier_rank, exact_extra_points=extra_pts,
            exact_level=enemy_level,
            language=language
        )
        if scenario_lower == "anomalous_incursions" and not e_obj.get("anomaly_blueprint") and not e_obj.get("is_human_operative"):
            try:
                import namegen
                anom_tags = [c for c in (category or []) if c in ("cognitohazard", "spatial_warp", "bio_aberration", "cursed_relic", "spectral_echo")]
                cat_tag = anom_tags[0] if anom_tags else "spatial_warp"
                e_obj["name"] = namegen.generate_anomalous_entity_name(category_tag=cat_tag)
            except Exception:
                pass
        
        # Fix name disambiguation 
        final_base = e_obj["name"]
        idx = 1
        while any(m["name"] == final_base for m in enemies):
            idx += 1
            final_base = f"{e_obj['name']} #{idx}"
        e_obj["name"] = final_base
        
        e_obj["xp_multiplier"] = xp_multiplier
        enemies.append(e_obj)

    return enemies, xp_multiplier


def resolve_party_member_actions(companions: list, enemies: list) -> str:
    if not companions: return ""
    instructions = []
    for comp in companions:
        name = comp.get("name", "Companion")
        arch = comp.get("archetype", "Companion")
        instructions.append(f"- {name} ({arch}): Automatically takes an appropriate tactical action to assist the player (e.g. attacking, defending, or supporting).")
    return "\n".join(instructions)



