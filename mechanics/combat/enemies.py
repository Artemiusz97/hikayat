import random
import re

# =====================================================================
# TAXONOMY & ENEMY SCENARIO TEMPLATES (Phase 1)
# =====================================================================

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
    ]
}

SCENARIO_ENEMIES = {k: [(t["name"], t["archetype"]) for t in v] for k, v in SCENARIO_ENEMY_TEMPLATES.items()}

# Scenario Archetype Stat Rules
ARCHETYPE_RULES = {
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
    "Feral Beast": {"primary": ["AGI", "PER"], "forbidden": ["CHA", "INT"]}
}

GENERIC_ENEMY_KEYWORDS = {
    "raider", "skirmisher", "bandit", "soldier", "guard", "grunt", "minion", "cultist",
    "thug", "warrior", "archer", "mage", "drone", "scout", "sentry", "hound", "wolf",
    "goblin", "orc", "skeleton", "zombie", "mutant", "specter", "golem", "construct",
    "beast", "swarm", "spider", "mercenary", "trooper", "enforcer", "peasant", "brigand",
    "pirate", "scavenger", "assassin", "operative", "parasite", "shade", "knight", "crawler",
    "fiend", "ghoul", "slime", "elemental", "abomination", "creature", "monster", "cyberhound",
    "debater", "bully", "monitor", "monger", "mutated", "feral", "automaton", "inquisitor", 
    "penitent", "shaman"
}

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


ALL_STATS = ["STR", "PER", "END", "CHA", "INT", "AGI", "LUK"]

def build_enemy_stat_sheet(level: int, archetype_name: str = None, custom_primary: list = None, custom_forbidden: list = None, exact_extra_points: int = None) -> dict:
    rule = ARCHETYPE_RULES.get(archetype_name, {"primary": ["STR", "AGI"], "forbidden": []})
    
    primary = custom_primary if custom_primary else rule.get("primary", ["STR", "AGI"])
    forbidden = custom_forbidden if custom_forbidden else rule.get("forbidden", [])
    
    primary_upper = [s.upper() for s in primary]
    forbidden_upper = [s.upper() for s in forbidden]
    
    allowed = [s for s in ALL_STATS if s not in forbidden_upper]
    if not allowed:
        allowed = ALL_STATS
        
    stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
    
    if exact_extra_points is not None:
        extra_points = max(0, exact_extra_points)
    else:
        extra_points = max(1, (level or 1) + random.randint(2, 5))
    
    weights = []
    for s in allowed:
        if s in primary_upper:
            weights.append(4) 
        else:
            weights.append(1) 
            
    for _ in range(extra_points):
        chosen = random.choices(allowed, weights=weights, k=1)[0]
        stats[chosen] += 1
        
    return stats

build_monster_stat_sheet = build_enemy_stat_sheet

def build_companion_stat_sheet(level: int, archetype_name: str = None) -> dict:
    rule = ARCHETYPE_RULES.get(archetype_name, {"primary": ["STR", "AGI"], "forbidden": []})
    primary = rule.get("primary", ["STR", "AGI"])
    forbidden = rule.get("forbidden", [])
    primary_upper = [s.upper() for s in primary]
    forbidden_upper = [s.upper() for s in forbidden]
    allowed = [s for s in ALL_STATS if s not in forbidden_upper]
    if not allowed: allowed = ALL_STATS
        
    stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
    extra_points = max(0, level - 1)
    
    weights = []
    for s in allowed:
        if s in primary_upper: weights.append(4)
        else: weights.append(1)
            
    for _ in range(extra_points):
        chosen = random.choices(allowed, weights=weights, k=1)[0]
        stats[chosen] += 1
        
    return stats

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
            weaknesses.extend(["shock", "acid"])
            resistances.extend(["slashing", "piercing", "stabbing"])
        elif cat in ("undead", "demon"):
            immunities.extend(["poison", "dark"])
            weaknesses.extend(["holy", "fire"])
            resistances.extend(["cold"])
        elif cat in ("beast", "mutant"):
            weaknesses.extend(["fire"])
            
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


def roll_enemy_intent(archetype: str) -> str:
    """Generates an initial or round-based telegraphed combat intent based on archetype."""
    arch = (archetype or "Brute").strip()
    intents = ["Preparing next strike", "Analyzing targets", "Shifting stance"]
    if arch in ("Stalker", "Assassin", "Dark Elf Assassin"):
        intents = ["Preparing to Ambush", "Fading into shadows", "Targeting the weak"]
    elif arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
        intents = ["Channeling a massive spell", "Drawing arcane energy", "Preparing a burst"]
    elif arch in ("Brute", "Heavy Mech", "Heavy Borg"):
        intents = ["Winding up a heavy swing", "Preparing a devastating crush", "Overcharging weapons"]
    elif arch in ("Guardian", "Corrupted Treant"):
        intents = ["Assuming a defensive posture", "Shielding allies", "Preparing a counter"]
    elif arch == "Void Swarm":
        intents = ["Preparing to swarm", "Multiplying rapidly"]
    return random.choice(intents)


def generate_scenario_enemy(scenario: str, location: str, chapter: int, custom_name: str = None,
                            custom_archetype: str = None, custom_primary: list = None, custom_forbidden: list = None,
                            exact_tier: int = None, exact_extra_points: int = None) -> dict:
    scenario_lower = scenario.lower() if scenario else "fantasy"
    
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
        
    if custom_archetype:
        arch_name = custom_archetype

    if template:
        category = template["category"]
        form = template["form"]
        essence = template["essence"]
    else:
        category, form, essence = infer_taxonomy_from_archetype(arch_name, scenario_lower)

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
    max_mp = 10 + (level * 3)
    
    stat_sheet = build_enemy_stat_sheet(level, arch_name, custom_primary, custom_forbidden, exact_extra_points=exact_extra_points)

    base_res, base_weak, base_imm = derive_taxonomy_weaknesses(category, form, essence)
    
    affixes = roll_enemy_affixes(tier_rank, category, form, essence, base_weak)
    
    for afx in affixes:
        afx_data = AFFIX_REGISTRY[afx]
        base_res.extend(afx_data.get("grants_resistances", []))
        base_weak.extend(afx_data.get("grants_weaknesses", []))
        # Remove conflicting weaknesses if granted resistance
        base_weak = [w for w in base_weak if w not in base_res]

    final_name = f"{affixes[0]} {name}" if affixes else name
    initial_intent = roll_enemy_intent(arch_name) if tier_rank >= 3 else None

    return {
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

generate_scenario_monster = generate_scenario_enemy


def generate_balanced_encounter(party_members: list, scenario: str, location: str, chapter: int) -> tuple[list, float]:
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

    scenario_lower = scenario.lower() if scenario else "fantasy"
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
            exact_tier=tier_rank, exact_extra_points=extra_pts
        )
        
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


def get_enemy_armor_profile(archetype: str) -> dict:
    """Returns the default armor class, protection types, base DT, and type DT traits for an enemy archetype."""
    arch = (archetype or "").strip()
    if arch in ("Guardian", "Heavy Mech", "Heavy Borg"):
        return {
            "armor_type": "heavy",
            "protection_types": ["physical", "ballistic"],
            "base_dt": 20,
            "type_dt": {
                "physical": 24, "slashing": 26, "stabbing": 18, "blunt": 14,
                "ballistic": 24, "rifle_round": 16, "pistol_round": 22, "high_caliber_round": 10,
                "arrow": 20, "bolt": 16, "magical": 8, "shock": 0, "fire": 6, "ice": 10
            },
            "def_bonus": 18,
            "mdef_bonus": 8,
            "block_chance": 20
        }
    elif arch in ("Brute", "Rad-Mutant", "Campus Bully"):
        return {
            "armor_type": "medium",
            "protection_types": ["physical"],
            "base_dt": 12,
            "type_dt": {
                "physical": 14, "slashing": 16, "stabbing": 10, "blunt": 8,
                "arrow": 12, "bolt": 8, "pistol_round": 6, "rifle_round": 4,
                "magical": 6, "fire": 4, "shock": 0, "ice": 6, "poison": 4
            },
            "def_bonus": 12,
            "mdef_bonus": 4,
            "block_chance": 0
        }
    elif arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
        return {
            "armor_type": "magic_robe",
            "protection_types": ["magical"],
            "base_dt": 2,
            "type_dt": {
                "magical": 16, "holy": 14, "dark": 14, "fire": 12, "shock": 12, "ice": 12,
                "poison": 10, "energy": 14, "energy_cell": 14, "physical": 1
            },
            "def_bonus": 4,
            "mdef_bonus": 24,
            "block_chance": 0
        }
    elif arch in ("Security Drone", "Corporate Operative", "Hall Monitor"):
        return {
            "armor_type": "kevlar",
            "protection_types": ["ballistic", "physical"],
            "base_dt": 10,
            "type_dt": {
                "ballistic": 22, "pistol_round": 24, "scatter_shot": 20, "slashing": 12,
                "rifle_round": 8, "arrow": 6, "fire": 2, "magical": 2, "shock": 4, "ice": 2
            },
            "def_bonus": 14,
            "mdef_bonus": 8,
            "block_chance": 0
        }
    elif arch in ("Skirmisher", "Stalker", "Chrome Cyberhound", "Feral Beast", "Void Swarm"):
        return {
            "armor_type": "light",
            "protection_types": ["physical"],
            "base_dt": 6,
            "type_dt": {
                "slashing": 8, "stabbing": 6, "ballistic": 4,
                "arrow": 8, "pistol_round": 4, "rifle_round": 2,
                "magical": 3, "fire": 2, "shock": 2, "ice": 3
            },
            "def_bonus": 6,
            "mdef_bonus": 6,
            "eva_bonus": 8,
            "block_chance": 0
        }
    return {
        "armor_type": "medium",
        "protection_types": ["physical"],
        "base_dt": 8,
        "type_dt": {
            "physical": 10, "slashing": 10, "stabbing": 8,
            "arrow": 8, "pistol_round": 4, "magical": 4
        },
        "def_bonus": 8,
        "mdef_bonus": 6,
        "block_chance": 0
    }


def get_enemy_weapon_profile(archetype: str) -> dict:
    """Returns the default weapon attack types and damage profile for an enemy archetype."""
    arch = (archetype or "").strip()
    if arch in ("Caster", "Psionic Alien", "Netrunner Spec-Op"):
        return {
            "attack_types": ["ranged"],
            "damage_types": {"magical": 1.0},
            "matk_bonus": 15
        }
    elif arch in ("Security Drone", "Corporate Operative", "Scrap-Scavenger"):
        return {
            "attack_types": ["ranged"],
            "damage_types": {"ballistic": 1.0},
            "atk_bonus": 14
        }
    elif arch in ("Guardian", "Heavy Mech", "Heavy Borg"):
        return {
            "attack_types": ["blunt", "hack"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 16
        }
    elif arch in ("Skirmisher", "Stalker", "Chrome Cyberhound", "Feral Beast"):
        return {
            "attack_types": ["slash", "thrust"],
            "damage_types": {"physical": 1.0},
            "atk_bonus": 12
        }
    return {
        "attack_types": ["slash", "blunt"],
        "damage_types": {"physical": 1.0},
        "atk_bonus": 10
    }


