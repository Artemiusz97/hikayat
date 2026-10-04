from __future__ import annotations
"""
Procedural Spell Generation Engine & D&D 5e Standard Tagging Framework for Hikayat.

Implements:
1. 8 D&D Schools of Magic (Evocation, Abjuration, Necromancy, Conjuration, Transmutation, Enchantment, Illusion, Divination).
2. 13 D&D Standard Damage Types (Fire, Cold, Lightning, Thunder, Acid, Poison, Radiant, Necrotic, Psychic, Force, Slashing, Piercing, Bludgeoning).
3. D&D Delivery Shapes & Targeting Geometry (Single Ray/Bolt, Cone, Sphere, Line, Cylinder, Chain, Aura, Ward).
4. D&D Status Conditions & Afflictions (Burned, Shocked, Poisoned, Frozen, Blinded, Frightened, Exposed, Slowed, Haste, Empowered, Decoy).
5. 3 Rarity Tiers with Affix Budgeting & D&D Metamagic Modifiers (Twinned, Empowered, Quickened, Vampiric, Sundering, Lingering, Cleansing).
6. Procedural Thematic Spell Naming Engine matching D&D Schools, Elements, and Forms.
7. Procedural Spellbook / Grimoire Loot Generator ([SPELLBOOK_JSON]).
8. Summoning Entity Templates for Necromancy, Druid/Beastmaster, Elemental, Celestial, and Tech Archetypes.
"""
import json
import random
from typing import Dict, Any, List, Optional, Tuple

# -----------------------------------------------------------------------------
# 1. D&D 8 SCHOOLS OF MAGIC TAXONOMY
# -----------------------------------------------------------------------------

DND_SCHOOLS: Dict[str, Dict[str, Any]] = {
    "Evocation": {
        "name": "Evocation",
        "emoji": "💥",
        "role": "damage",
        "default_damage_types": ["fire", "cold", "lightning", "thunder", "radiant", "force"],
        "power_mult_range": {3: (1.1, 1.4), 2: (1.8, 2.2), 1: (2.8, 3.5)},
        "description": "Manipulates raw magical and elemental energy to unleash destructive bursts."
    },
    "Abjuration": {
        "name": "Abjuration",
        "emoji": "🛡️",
        "role": "support",
        "default_damage_types": ["radiant", "force"],
        "buff_targets": ["DEF", "MDEF"],
        "heal_range": {3: (20, 30), 2: (40, 60), 1: (75, 110)},
        "ward_range": {3: (15, 25), 2: (30, 50), 1: (60, 90)},
        "description": "Protective magic creating wards, barriers, damage shields, and dispelling hostile hexes."
    },
    "Necromancy": {
        "name": "Necromancy",
        "emoji": "💀",
        "role": "hybrid",
        "default_damage_types": ["necrotic", "poison"],
        "power_mult_range": {3: (0.9, 1.2), 2: (1.5, 1.9), 1: (2.4, 3.0)},
        "debuff_targets": ["ATK", "DEF"],
        "summon_types": ["skeleton", "ghoul", "wraith", "bone_colossus"],
        "description": "Manipulates the energies of life and death, siphoning health, sapping strength, and raising undead minions."
    },
    "Conjuration": {
        "name": "Conjuration",
        "emoji": "🌀",
        "role": "summon",
        "default_damage_types": ["slashing", "piercing", "bludgeoning", "acid", "poison", "fire"],
        "power_mult_range": {3: (0.9, 1.2), 2: (1.5, 2.0), 1: (2.4, 3.0)},
        "summon_types": ["spirit_wolf", "dire_bear", "fire_elemental", "storm_sprite", "hydra", "seraph"],
        "description": "Transports objects, creatures, and elements from other planes into physical reality."
    },
    "Transmutation": {
        "name": "Transmutation",
        "emoji": "⏳",
        "role": "hybrid",
        "default_damage_types": ["acid", "bludgeoning", "slashing", "force"],
        "buff_targets": ["AGI", "EVA", "ATK"],
        "debuff_targets": ["AGI", "DEF"],
        "status_ailments": ["Haste", "Slowed", "Exposed"],
        "description": "Changes the physical properties of matter, speed, weight, and time flow."
    },
    "Enchantment": {
        "name": "Enchantment",
        "emoji": "🧠",
        "role": "curse",
        "default_damage_types": ["psychic"],
        "debuff_targets": ["ATK", "ACC"],
        "status_ailments": ["Confused", "Stunned", "Frightened", "Charmed"],
        "description": "Bends the minds and willpower of targets, sowing confusion, panic, and paralysis."
    },
    "Illusion": {
        "name": "Illusion",
        "emoji": "🌫️",
        "role": "support",
        "default_damage_types": ["psychic", "radiant"],
        "status_ailments": ["Blinded", "Concealed"],
        "decoy_chance": {3: 0.35, 2: 0.60, 1: 0.85},
        "description": "Deceives the senses with phantom mirror decoys, invisibility, and disorienting sensory veils."
    },
    "Divination": {
        "name": "Divination",
        "emoji": "👁️",
        "role": "support",
        "default_damage_types": ["radiant", "force"],
        "crit_bonus_range": {3: 10, 2: 20, 1: 35},
        "acc_bonus_range": {3: 10, 2: 18, 1: 25},
        "sunder_range": {3: 15, 2: 30, 1: 50},
        "description": "Glimpses future timelines to reveal enemy weaknesses, grant guaranteed precision, and critical strikes."
    }
}

# -----------------------------------------------------------------------------
# 2. D&D 13 DAMAGE TYPES & ELEMENTAL DOMAINS
# -----------------------------------------------------------------------------

DND_DAMAGE_TYPES: Dict[str, Dict[str, Any]] = {
    "fire": {
        "name": "Fire", "emoji": "🔥", "ailment": "Burned", "dot": True,
        "adjectives": ["Flaming", "Blazing", "Ignited", "Molten", "Searing", "Infernal", "Cinder"]
    },
    "cold": {
        "name": "Cold", "emoji": "❄️", "ailment": "Frozen", "dot": False,
        "adjectives": ["Frost", "Glacial", "Frigid", "Chilling", "Rime", "Cryo", "Boreal"]
    },
    "lightning": {
        "name": "Lightning", "emoji": "⚡", "ailment": "Shocked", "dot": False,
        "adjectives": ["Static", "Thunder", "Shocking", "Tempest", "Galvanic", "Volt", "Storm"]
    },
    "thunder": {
        "name": "Thunder", "emoji": "🌩️", "ailment": "Stunned", "dot": False,
        "adjectives": ["Sonic", "Resonant", "Concussive", "Thunderous", "Booming", "Seismic"]
    },
    "acid": {
        "name": "Acid", "emoji": "🧪", "ailment": "Exposed", "dot": True,
        "adjectives": ["Caustic", "Corrosive", "Dissolving", "Vitriolic", "Acidic"]
    },
    "poison": {
        "name": "Poison", "emoji": "🐍", "ailment": "Poisoned", "dot": True,
        "adjectives": ["Venomous", "Toxic", "Noxious", "Pestilent", "Viper"]
    },
    "radiant": {
        "name": "Radiant", "emoji": "✨", "ailment": "Blinded", "dot": False,
        "adjectives": ["Holy", "Sacred", "Solar", "Celestial", "Luminous", "Seraphic", "Divine"]
    },
    "necrotic": {
        "name": "Necrotic", "emoji": "🌑", "ailment": "Weakened", "dot": True,
        "adjectives": ["Abyssal", "Dark", "Shadow", "Withered", "Blighted", "Dread", "Void"]
    },
    "psychic": {
        "name": "Psychic", "emoji": "🔮", "ailment": "Confused", "dot": False,
        "adjectives": ["Psionic", "Mind", "Astral", "Telepathic", "Synaptic", "Cerebral"]
    },
    "force": {
        "name": "Force", "emoji": "🌌", "ailment": "Disrupted", "dot": False,
        "adjectives": ["Arcane", "Ether", "Aether", "Kinetic", "Cosmic", "Pure"]
    },
    "slashing": {
        "name": "Slashing", "emoji": "🗡️", "ailment": "Bleeding", "dot": True,
        "adjectives": ["Razor", "Blade", "Vorpal", "Serrated", "Cleaving"]
    },
    "piercing": {
        "name": "Piercing", "emoji": "🔱", "ailment": "Exposed", "dot": False,
        "adjectives": ["Needle", "Spike", "Lance", "Impaling", "Puncturing"]
    },
    "bludgeoning": {
        "name": "Bludgeoning", "emoji": "🔨", "ailment": "Stunned", "dot": False,
        "adjectives": ["Crushing", "Heavy", "Battering", "Titan", "Impact"]
    }
}

# -----------------------------------------------------------------------------
# 3. D&D DELIVERY SHAPES & GEOMETRY
# -----------------------------------------------------------------------------

DND_SHAPES: Dict[str, Dict[str, Any]] = {
    # ── Single-Target Archetypes ──────────────────────────────────────────────
    # Standard mana (1.0x). High crit potential. acc_mod: flat % added to hit chance.
    "bolt": {
        "name": "Bolt", "target_type": "single", "acc_mod": 0, "crit_bonus": 0.05,
        "noun": "Bolt", "verb": "hurls a concentrated projectile of {element}"
    },
    "lance": {
        "name": "Lance / Ray", "target_type": "single", "acc_mod": 0, "crit_bonus": 0.15,
        "noun": "Lance", "verb": "channels a piercing laser-focused beam of {element}"
    },

    # ── Full AOE Archetypes ───────────────────────────────────────────────────
    # Hits all living enemies. -5% acc_mod; gains 35% Glancing Blast Floor on
    # failed checks (dmg * glance_floor instead of 0). Mana surcharge: 1.4x.
    "cone": {
        "name": "Cone / Wave", "target_type": "aoe", "acc_mod": -5, "crit_bonus": 0.0,
        "glance_floor": 0.35,
        "noun": "Wave", "verb": "sweeps a surging frontal cone of {element}"
    },
    "sphere": {
        "name": "Sphere / Nova", "target_type": "aoe", "acc_mod": -5, "crit_bonus": 0.10,
        "glance_floor": 0.35,
        "noun": "Nova", "verb": "detonates an explosive radial blast of {element}"
    },
    "line": {
        "name": "Line", "target_type": "aoe", "acc_mod": 0, "crit_bonus": 0.08,
        "glance_floor": 0.35,
        "noun": "Line", "verb": "shoots a piercing line of {element} cutting through enemy ranks"
    },
    "cylinder": {
        "name": "Cylinder / Column", "target_type": "aoe", "acc_mod": 0, "crit_bonus": 0.12,
        "glance_floor": 0.35,
        "noun": "Pillar", "verb": "calls down a roaring sky-smite column of {element}"
    },

    # ── Bouncing Chain Archetype ──────────────────────────────────────────────
    # Bounces to up to max_bounces targets: 100% -> 75% -> 50% damage.
    # +10 acc_mod (homing). Mana surcharge: 1.2x.
    "chain": {
        "name": "Chain / Arc", "target_type": "chain", "acc_mod": 10, "crit_bonus": 0.0,
        "max_bounces": 3, "decay_rate": 0.25,
        "noun": "Arc", "verb": "releases an arcing surge of {element} ricocheting between foes"
    },

    # ── Support / Ward / Summon Archetypes ────────────────────────────────────
    # Auto-hit (acc_mod treated as +100 in choice_generator). Mana surcharge: 1.4x.
    "aura": {
        "name": "Aura / Ward", "target_type": "support", "acc_mod": 100, "crit_bonus": 0.0,
        "noun": "Ward", "verb": "envelops the target in a protective shield of {element}"
    },
    "summon_swarm": {
        "name": "Minion Swarm", "target_type": "summon", "acc_mod": 100, "crit_bonus": 0.0,
        "noun": "Pact", "verb": "summons allied minions into the fray"
    },
    "summon_titan": {
        "name": "Titan Avatar", "target_type": "summon", "acc_mod": 100, "crit_bonus": 0.0,
        "noun": "Invocation", "verb": "summons a colossal planar champion"
    }
}


# -----------------------------------------------------------------------------
# 4. METAMAGIC MODIFIERS & AFFIX POOL
# -----------------------------------------------------------------------------

METAMAGIC_AFFIX_POOL: Dict[str, Dict[str, Any]] = {
    "vampiric": {
        "name": "Vampiric Touch", "type": "leech",
        "description": "Converts 25% of damage dealt into caster HP.",
        "tiers": (1, 2), "leech_pct": 0.25
    },
    "sundering": {
        "name": "Sundering", "type": "pierce",
        "description": "Ignores 35% of target DEF / MDEF.",
        "tiers": (1, 2, 3), "sunder_pct": 0.35
    },
    "empowered": {
        "name": "Empowered", "type": "power",
        "description": "+20% spell damage output.",
        "tiers": (1, 2), "power_bonus": 0.20
    },
    "quickened": {
        "name": "Quickened", "type": "efficiency",
        "description": "Reduces MP cost by 25% (min 1 MP saved).",
        "tiers": (1, 2, 3), "mp_reduction_pct": 0.25
    },
    "twinned": {
        "name": "Twinned", "type": "echo",
        "description": "25% chance to cast a secondary echoing strike on hit.",
        "tiers": (1, 2), "echo_chance": 0.25
    },
    "cleansing": {
        "name": "Cleansing", "type": "cleanse",
        "description": "Removes 1 negative status ailment from caster upon execution.",
        "tiers": (1, 2, 3), "cleanses": True
    },
    "lingering": {
        "name": "Lingering", "type": "duration",
        "description": "Increases status ailment duration by +1 turn.",
        "tiers": (1, 2, 3), "duration_bonus": 1
    },
    "warded": {
        "name": "Warded", "type": "barrier",
        "description": "Grants +15 temporary Ward HP when cast.",
        "tiers": (1, 2), "temp_hp": 15
    },
    "decoy": {
        "name": "Mirror Phantasm", "type": "decoy",
        "description": "Leaves behind an illusory decoy that absorbs 1 enemy attack.",
        "tiers": (1, 2), "spawns_decoy": True
    }
}

# -----------------------------------------------------------------------------
# 5. SUMMONING TEMPLATES
# -----------------------------------------------------------------------------

SUMMON_TEMPLATES: Dict[str, Dict[str, Any]] = {
    # Necromancy
    "skeleton": {
        "name": "Dread Skeleton", "archetype": "Skirmisher", "count": 2, "duration": 3,
        "hp_per_level": 5, "base_hp": 20, "attack_type": "slash", "damage_type": "necrotic",
        "description": "Skeletal warrior armed with rusty scimitars."
    },
    "ghoul": {
        "name": "Flesh Ghoul", "archetype": "Brute", "count": 2, "duration": 4,
        "hp_per_level": 7, "base_hp": 30, "attack_type": "hack", "damage_type": "poison",
        "description": "Savage undead beast that tears into enemy armor."
    },
    "bone_colossus": {
        "name": "Bone Colossus", "archetype": "Guardian", "count": 1, "duration": 5,
        "hp_per_level": 12, "base_hp": 65, "attack_type": "blunt", "damage_type": "necrotic",
        "description": "Towering juggernaut of calcified skulls with a bone shield."
    },

    # Conjuration / Druid / Nature
    "spirit_wolf": {
        "name": "Spirit Wolf", "archetype": "Stalker", "count": 2, "duration": 3,
        "hp_per_level": 5, "base_hp": 22, "attack_type": "thrust", "damage_type": "physical",
        "description": "Spectral wolf with high evasion and quick flank attacks."
    },
    "dire_bear": {
        "name": "Primal Dire Bear", "archetype": "Guardian", "count": 1, "duration": 4,
        "hp_per_level": 10, "base_hp": 55, "attack_type": "blunt", "damage_type": "physical",
        "description": "Massive armored woodland guardian that tanks enemy blows."
    },
    "hydra": {
        "name": "Apex Hydra", "archetype": "Brute", "count": 1, "duration": 5,
        "hp_per_level": 14, "base_hp": 75, "attack_type": "slash", "damage_type": "poison",
        "description": "Multi-headed planar apex beast that strikes all enemies."
    },

    # Elemental
    "fire_imp": {
        "name": "Flame Imp", "archetype": "Skirmisher", "count": 2, "duration": 3,
        "hp_per_level": 4, "base_hp": 18, "attack_type": "ranged", "damage_type": "fire",
        "description": "Mischievous fiery minion casting fire motes."
    },
    "storm_sprite": {
        "name": "Storm Sprite", "archetype": "Caster", "count": 2, "duration": 4,
        "hp_per_level": 5, "base_hp": 24, "attack_type": "ranged", "damage_type": "lightning",
        "description": "Crackling lightning sprite that jolts nearby enemies."
    },
    "fire_elemental": {
        "name": "Greater Fire Elemental", "archetype": "Brute", "count": 1, "duration": 5,
        "hp_per_level": 12, "base_hp": 65, "attack_type": "blunt", "damage_type": "fire",
        "description": "Living inferno avatar radiating intense heat."
    },

    # Celestial / Holy
    "guardian_wisp": {
        "name": "Guardian Wisp", "archetype": "Caster", "count": 1, "duration": 3,
        "hp_per_level": 4, "base_hp": 15, "attack_type": "ranged", "damage_type": "radiant",
        "description": "Benevolent orb of light that heals the party."
    },
    "celestial_sentinel": {
        "name": "Celestial Sentinel", "archetype": "Guardian", "count": 1, "duration": 4,
        "hp_per_level": 9, "base_hp": 50, "attack_type": "thrust", "damage_type": "radiant",
        "description": "Holy winged guardian with a golden kite shield."
    },
    "seraph": {
        "name": "Seraphic Valkyrie", "archetype": "Brute", "count": 1, "duration": 5,
        "hp_per_level": 12, "base_hp": 70, "attack_type": "slash", "damage_type": "radiant",
        "description": "Six-winged archon delivering righteous divine wrath."
    },

    # Sci-Fi / Cyber / Tech
    "micro_drone": {
        "name": "Attack Micro-Drone", "archetype": "Security Drone", "count": 2, "duration": 3,
        "hp_per_level": 4, "base_hp": 16, "attack_type": "ranged", "damage_type": "lightning",
        "description": "Hovering combat drone with high-frequency pulse lasers."
    },
    "combat_automaton": {
        "name": "Combat Automaton", "archetype": "Heavy Borg", "count": 1, "duration": 4,
        "hp_per_level": 8, "base_hp": 48, "attack_type": "blunt", "damage_type": "physical",
        "description": "Armored combat android equipped with ballistic shielding."
    },
    "siege_mech": {
        "name": "Siege Titan Mech", "archetype": "Heavy Mech", "count": 1, "duration": 5,
        "hp_per_level": 14, "base_hp": 80, "attack_type": "blunt", "damage_type": "thunder",
        "description": "Heavy walking walker tank equipped with kinetic cannons."
    },

    # Steampunk / Clockwork / Automata
    "clockwork_drone": {
        "name": "Clockwork Scout-Drone", "archetype": "Security Drone", "count": 2, "duration": 3,
        "hp_per_level": 4, "base_hp": 18, "attack_type": "thrust", "damage_type": "physical",
        "description": "Brass-geared ornithopter drone with needle injectors."
    },
    "steam_automaton": {
        "name": "Steam Automaton", "archetype": "Guardian", "count": 1, "duration": 4,
        "hp_per_level": 9, "base_hp": 52, "attack_type": "blunt", "damage_type": "physical",
        "description": "Heavy boiler-plated automaton venting scalding steam."
    },
    "clockwork_colossus": {
        "name": "Clockwork Colossus", "archetype": "Brute", "count": 1, "duration": 5,
        "hp_per_level": 14, "base_hp": 85, "attack_type": "blunt", "damage_type": "physical",
        "description": "Massive walking brass titan with twin hydraulic crushing fists."
    }
}

# -----------------------------------------------------------------------------
# 6. THEMATIC & GENRE-SPECIFIC NAMING ENGINE
# -----------------------------------------------------------------------------

THEMATIC_PREFIXES = {
    1: ["Cataclysmic", "Mythic", "Archon's", "Ancient", "Supreme", "God-King's", "Cosmic", "Apocalyptic"],
    2: ["Greater", "Empowered", "Arcane", "Runic", "Adept's", "Fierce", "Radiant", "Dread"],
    3: ["Lesser", "Novice", "Basic", "Minor", "Focused", "Swift", "Casting", "Sparking"]
}

THEMATIC_SUFFIXES = [
    "of Ruin", "of Mastery", "of the Abyss", "of the Heavens", "of Storms",
    "of the Phoenix", "of the Archmage", "of the Wyrm", "of Annihilation", "of Eternity"
]

SCENARIO_SPELL_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "prefixes": {
            1: ["Cataclysmic", "Mythic", "Archon's", "Ancient", "Supreme", "God-King's", "Cosmic", "Apocalyptic"],
            2: ["Greater", "Empowered", "Arcane", "Runic", "Adept's", "Fierce", "Radiant", "Dread"],
            3: ["Lesser", "Novice", "Basic", "Minor", "Focused", "Swift", "Casting", "Sparking"]
        },
        "suffixes": {
            1: ["of Ruin", "of Mastery", "of the Abyss", "of the Heavens", "of Storms", "of the Phoenix", "of the Archmage", "of the Wyrm", "of Annihilation", "of Eternity"],
            2: ["of the Adept", "of Sparks", "of Frost", "of Warding", "of Swiftness"]
        },
        "elem_adjectives": {},
        "shape_nouns": {}
    },
    "steampunk": {
        "prefixes": {
            1: ["Pneumatic Apex", "Aether-Forged", "Tesla's Masterwork", "Grand Alchemical", "High-Pressure", "Dreadnought's", "Clockwork Sovereign's"],
            2: ["Pressurized", "Galvanic", "Clockwork", "Alchemical", "Boiler-Forged", "Voltaic", "Steam-Driven", "Vapor-Cooled", "Gilded-Gear"],
            3: ["Piston", "Rivet", "Copper", "Brass", "Vapor", "Spring-Loaded", "Sprocket", "Gauge-Tuned"]
        },
        "suffixes": {
            1: ["of the High Boiler", "of Clockwork Ruin", "of Galvanic Induction", "of the Brass Core", "of Aetheric Resonance", "of Endless Pressure"],
            2: ["of the Automaton", "of the Piston", "of Steam Exhaust", "of Copper Coils", "of Valve Rupture"]
        },
        "elem_adjectives": {
            "lightning": ["Galvanic", "Tesla", "Arc-Charged", "Voltaic", "Electrified", "Induction"],
            "fire": ["Boiler-Flame", "Superheated", "Pressurized-Ignition", "Furnace", "Combustion"],
            "cold": ["Cryo-Condenser", "Refrigerant", "Pneumatic-Chill", "Frigid-Vapor", "Vapor-Frosted"],
            "acid": ["Vitriolic", "Caustic Slag", "Alchemical Acid", "Caustic-Reagent", "Acid-Steam"],
            "force": ["Pneumatic Shock", "Steam-Pressure", "Kinetic Piston", "Aetheric Shock", "Hydraulic"],
            "thunder": ["Steam-Burst", "Boiler-Rupture", "Concussive Piston", "Whistle-Screech", "Percussive"],
            "poison": ["Noxious Smog", "Toxic Fumes", "Soot-Vapor", "Sulfuric Gas", "Smokestack"],
            "radiant": ["Aether-Luminescent", "Phosphor", "Galvanic Glare", "Incandescent", "Arc-Lamp"],
            "necrotic": ["Rust-Blight", "Decay-Engine", "Entropic Decay", "Corrosion", "Slag-Rot"],
            "psychic": ["Phrenic", "Mesmeric", "Aether-Resonant", "Galvanic Neural", "Clockwork-Mind"],
            "magical": ["Aetheric", "Ether-Charged", "Alkahest", "Ley-Vapor", "Philosopher's"],
            "slashing": ["Serrated-Gear", "Clockwork-Bladed", "Razor-Piston"],
            "piercing": ["Pneumatic-Needle", "Rivet-Piercing", "High-Pressure"],
            "bludgeoning": ["Hydraulic-Hammer", "Piston-Crush", "Brass-Mallet"]
        },
        "shape_nouns": {
            "bolt": ["Dart", "Needle", "Rivet Slug", "Discharge", "Piston Bolt"],
            "lance": ["Pneumatic Harpoon", "Spike Injector", "Aether Lance", "Hydraulic Ram"],
            "cone": ["Steam Vent", "Exhaust Steam Flue", "Pressure Spout", "Vapor Steam Spray"],
            "sphere": ["Boiler Bomb", "Pressure Sphere", "Condenser Orb", "Vapor Globe"],
            "line": ["Pressurized Stream", "Steam Jet", "Piston Axis", "Galvanic Tracer"],
            "cylinder": ["Geyser Column", "Chimney Vent", "Pressure Flue", "Furnace Pillar"],
            "chain": ["Tesla Arc", "Conduction Chain", "Galvanic Ricochet", "Coil Leap"],
            "aura": ["Vapor Ward", "Aetheric Barrier", "Pressure Shield", "Brass Aegis"],
            "summon_swarm": ["Clockwork Swarm", "Automaton Deploy", "Scrap-Drone Matrix"],
            "summon_titan": ["Steam Dreadnought", "Clockwork Colossus", "Boiler Titan"]
        }
    },
    "cyberpunk": {
        "prefixes": {
            1: ["Orbital", "Singularity", "Black-ICE", "Quantum", "Zero-Day", "Tachyon", "Nanite Apex", "Hyper-Threaded"],
            2: ["Overclocked", "Synaptic", "High-Frequency", "Sub-Zero", "Smart-Linked", "Bio-Digital", "Neural", "Pulse"],
            3: ["Protocol", "Subroutine", "Low-Latency", "Vector", "Micro", "Field-Tested", "Digital", "Buffer"]
        },
        "suffixes": {
            1: ["Daemon v2.0", "of Orbital Strike", "of System Overload", "Kernel Panic", "of Neural Meltdown", "Execution Loop", "of Total Wipe"],
            2: ["Protocol", "Routine", "Vector", "of Overdrive", "Bypass", "Overflow", "Subroutine"]
        },
        "elem_adjectives": {
            "lightning": ["EMP", "Overvoltage", "Static-Pulse", "Arc-Circuit", "High-Voltage", "Grid-Surge"],
            "fire": ["Plasma", "Thermobaric", "Laser-Thermal", "Superheated Core", "Incendiary"],
            "cold": ["Liquid Nitrogen", "Cryo-Stasis", "Sub-Zero", "Endothermic", "Absolute-Chilled"],
            "acid": ["Nanite Acid", "Caustic Solvent", "Corrosive Slag", "Degrading Bio-Gel"],
            "force": ["Kinetic Rail", "Graviton", "Mass-Driver", "Shockwave", "Repulsor"],
            "thunder": ["Sonic Pulse", "Concussive Shock", "Frequency Blast", "Audio-Stun", "Resonance"],
            "poison": ["Neurotoxin", "Synthetic Venom", "Biohazard", "Viral Payload", "Synaptic Toxin"],
            "radiant": ["Photon", "Ultraviolet", "Hard-Light", "Ionizing Laser", "Tachyon-Beam"],
            "necrotic": ["System-Rot", "Data-Corruption", "Bio-Necrotic", "Nanite Decomposition"],
            "psychic": ["Neural-Hack", "Synaptic Shock", "Cortex-Spike", "Mind-Tap", "Memory-Burn"],
            "magical": ["Quantum-Phase", "Digital-Ether", "Zero-Point", "Holographic", "Sub-Atomic"],
            "slashing": ["Monowire", "High-Frequency Blade", "Laser-Edge"],
            "piercing": ["Flechette", "Armor-Piercing Sabot", "Needlegun"],
            "bludgeoning": ["Kinetic Impactor", "Grav-Hammer", "Hydraulic Fist"]
        },
        "shape_nouns": {
            "bolt": ["Spike", "Packet", "Pulse Round", "Dart", "Bit-Burst"],
            "lance": ["Particle Beam", "Rail Penetrator", "Laser Lance", "Linear Accelerator"],
            "cone": ["Discharge Fan", "Wavefront Spray", "Emitter Sweep", "Cone Array"],
            "sphere": ["Payload Blast", "Matrix Sphere", "Plasma Detonation", "Cluster Bomb"],
            "line": ["Laser Trace", "Linear Sweep", "Vector Beam", "Rail Line"],
            "cylinder": ["Orbital Smite", "Drop Column", "Pillar Wave", "Ion Pillar"],
            "chain": ["Network Relay", "Daemon Cascade", "Synaptic Leap", "Chain Bus Relay"],
            "aura": ["Firewall", "Nanite Aegis", "Defense Grid", "Shield Matrix"],
            "summon_swarm": ["Micro-Drone Swarm", "Nanite Cloud", "Combat Bot Matrix"],
            "summon_titan": ["Siege Mech Walker", "Titan Android", "Heavy Combat Exo"]
        }
    },
    "dark_fantasy": {
        "prefixes": {
            1: ["Apocalyptic", "Irradiated", "Cataclysmic", "God-Corpse", "Abyssal", "Doomsday", "Extinction-Grade", "Blood-Lord's"],
            2: ["Blighted", "Ash-Forged", "Sanguine", "Gamma", "Mutagenic", "Dread", "Rotting", "Wasteland", "Cursed"],
            3: ["Foul", "Scrap-Fed", "Tainted", "Grim", "Squalid", "Corrupted", "Vile", "Grave"]
        },
        "suffixes": {
            1: ["of the Wasteland", "of the Rot", "of Blood Pacts", "of Nuclear Winter", "of the Desolate Void", "of the Grave", "of Eternal Pestilence"],
            2: ["of Ruin", "of Blight", "of the Ash", "of Fallout", "of Sickness", "of Decay"]
        },
        "elem_adjectives": {
            "necrotic": ["Grave-Rot", "Putrid", "Bone-Chilling", "Sanguine", "Vampiric", "Corpse-Fed", "Decaying"],
            "poison": ["Rad-Poison", "Contagion", "Mutagenic", "Venomous Sludge", "Blighted", "Festering"],
            "dark": ["Void-Touched", "Abyssal", "Shadow-Veiled", "Dread", "Nether", "Stygian"],
            "fire": ["Ash-Flame", "Atomic", "Hellfire", "Irradiated-Fire", "Brimstone", "Pyre"],
            "cold": ["Nuclear-Winter", "Graveyard Chill", "Black-Frost", "Marrow-Cold", "Boreal Doom"],
            "lightning": ["Gamma-Pulse", "Irradiated-Arc", "Storm-Blight", "Fulgurite", "Sickly-Static"],
            "acid": ["Caustic Slag", "Vat-Acid", "Rad-Leach", "Marrow-Melt", "Corrosive Bile"],
            "force": ["Shockwave", "Concussive Rubble", "Kinetic Fallout", "Grave-Force"],
            "thunder": ["Sonic Rupture", "Screaming Void", "Rumbling Shock", "Doom-Echo"],
            "radiant": ["Baleful Glow", "Cherenkov Radiation", "Eerie Luminescence", "Holy Censure"],
            "psychic": ["Madness", "Mind-Rot", "Whispering Dread", "Psychotic Surge", "Hysteria"],
            "magical": ["Eldritch", "Forbidden", "Nether-Warped", "Abyssal", "Blood-Sorcery"],
            "slashing": ["Rust-Cleaver", "Serrated-Bone", "Barbed-Wire"],
            "piercing": ["Bone-Spike", "Rad-Needle", "Rusty-Spike"],
            "bludgeoning": ["Crushed-Skull", "Rubble-Club", "Heavy-Lead"]
        },
        "shape_nouns": {
            "bolt": ["Spike", "Shard", "Siphon", "Needle", "Dart", "Putrid Dart"],
            "lance": ["Bone Spear", "Rupture Lance", "Rad-Spike", "Corpse Lance"],
            "cone": ["Miasma", "Fallout Spray", "Blight Cloud", "Vomit Wave"],
            "sphere": ["Rad-Burst", "Plague Sphere", "Corpse Detonation", "Blight Orb"],
            "line": ["Contagion Streak", "Blight Fissure", "Ash Line", "Rupture Path"],
            "cylinder": ["Mushroom Pillar", "Fallout Column", "Grave Chimney", "Blight Geyser"],
            "chain": ["Contagion Chain", "Sanguine Siphon", "Curse Ricochet", "Spore Leap"],
            "aura": ["Shroud of Flies", "Bone Ward", "Rad-Shield", "Carrion Veil"],
            "summon_swarm": ["Carrion Swarm", "Ghoul Pack", "Rad-Roach Cluster"],
            "summon_titan": ["Bone Colossus", "Flesh Titan", "Mutant Behemoth"]
        }
    }
}

def normalize_scenario_key(scenario: str) -> str:
    """Normalizes scenario string to canonical genre key for spell flavor resolution."""
    scen = str(scenario or "fantasy").lower().strip()
    if any(w in scen for w in ("steampunk", "clockwork", "victorian")):
        return "steampunk"
    elif any(w in scen for w in ("scifi", "sci_fi", "space", "cyber", "hacker", "tech")):
        return "cyberpunk"
    elif any(w in scen for w in ("dark_fantasy", "nuclear_post_apocalypse", "postapoc", "wasteland", "grimdark")):
        return "dark_fantasy"
    return "fantasy"

def generate_spell_name(
    school: str,
    element: str,
    shape: str,
    tier: int,
    affixes: List[str],
    scenario: str = "fantasy"
) -> str:
    """Generates an evocative, aesthetic D&D-themed spell name tailored to the scenario."""
    scen_key = normalize_scenario_key(scenario)
    affix_data = SCENARIO_SPELL_AFFIXES.get(scen_key, SCENARIO_SPELL_AFFIXES["fantasy"])

    if element:
        elem_lower = str(element).lower().strip()
        if elem_lower in ("dark", "shadow"):
            element = "necrotic"
        elif elem_lower in ("magical", "arcane"):
            element = "force"
        elif elem_lower in ("earth", "stone"):
            element = "bludgeoning"
        elif elem_lower in ("wind", "gale", "air"):
            element = "slashing"
        elif elem_lower in ("water", "hydro"):
            element = "cold"

    elem_info = DND_DAMAGE_TYPES.get(element, DND_DAMAGE_TYPES["force"])
    shape_info = DND_SHAPES.get(shape, DND_SHAPES["bolt"])

    # Resolve elemental adjective (genre-specific or default D&D)
    elem_adj_pool = affix_data.get("elem_adjectives", {}).get(element)
    if not elem_adj_pool:
        elem_adj_pool = elem_info.get("adjectives", ["Arcane"])
    elem_adj = random.choice(elem_adj_pool)

    # Resolve shape noun (genre-specific or default D&D)
    shape_noun_pool = affix_data.get("shape_nouns", {}).get(shape)
    if not shape_noun_pool:
        shape_noun = shape_info.get("noun", "Bolt")
    elif isinstance(shape_noun_pool, list):
        shape_noun = random.choice(shape_noun_pool)
    else:
        shape_noun = str(shape_noun_pool)

    prefixes = affix_data.get("prefixes", THEMATIC_PREFIXES)
    suffixes = affix_data.get("suffixes", {1: THEMATIC_SUFFIXES, 2: []})

    if tier == 3:
        return f"{elem_adj} {shape_noun}"
    elif tier == 2:
        p_list = prefixes.get(2) or THEMATIC_PREFIXES[2]
        prefix = random.choice(p_list)
        return f"{prefix} {elem_adj} {shape_noun}"
    else:  # Tier 1
        p_list = prefixes.get(1) or THEMATIC_PREFIXES[1]
        prefix = random.choice(p_list)
        s_list = suffixes.get(1) or THEMATIC_SUFFIXES
        suffix = random.choice(s_list)
        return f"{prefix} {elem_adj} {shape_noun} {suffix}"

# -----------------------------------------------------------------------------
# 7. PROCEDURAL SPELL GENERATOR
# -----------------------------------------------------------------------------

def generate_procedural_spell(
    scenario: str = "fantasy",
    tier: int = 3,
    school: Optional[str] = None,
    element: Optional[str] = None,
    shape: Optional[str] = None,
    custom_theme: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synthesizes a unique procedural spell adhering to the 6 D&D dimensions.
    Returns a complete, balanced spell definition.
    """
    tier = max(1, min(3, tier))
    tier_names = {3: "Basic", 2: "Advanced", 1: "Master"}
    tier_name = tier_names[tier]

    # 1. School selection
    if not school or school not in DND_SCHOOLS:
        school = random.choice(list(DND_SCHOOLS.keys()))
    school_info = DND_SCHOOLS[school]

    # 2. Element selection (with canonical alias resolution)
    if element:
        elem_lower = str(element).lower().strip()
        if elem_lower in ("dark", "shadow"):
            element = "necrotic"
        elif elem_lower in ("magical", "arcane"):
            element = "force"
        elif elem_lower in ("earth", "stone"):
            element = "bludgeoning"
        elif elem_lower in ("wind", "gale", "air"):
            element = "slashing"
        elif elem_lower in ("water", "hydro"):
            element = "cold"
    if not element or element not in DND_DAMAGE_TYPES:
        element = random.choice(school_info["default_damage_types"])
    elem_info = DND_DAMAGE_TYPES[element]

    # 3. Shape / Delivery Form selection
    if not shape or shape not in DND_SHAPES:
        if school_info["role"] == "summon":
            shape = "summon_titan" if tier == 1 else "summon_swarm"
        elif school_info["role"] == "support":
            shape = "aura"
        else:
            candidates = ["bolt", "lance", "cone", "sphere", "line", "chain"]
            shape = random.choice(candidates)
    shape_info = DND_SHAPES[shape]

    # 4. Metamagic & Affix Budgeting
    num_affixes = 1 if tier == 3 else (random.randint(2, 3) if tier == 2 else random.randint(3, 5))
    available_affix_keys = [k for k, v in METAMAGIC_AFFIX_POOL.items() if tier in v["tiers"]]
    chosen_affix_keys = random.sample(available_affix_keys, min(num_affixes, len(available_affix_keys)))
    rolled_affixes = [METAMAGIC_AFFIX_POOL[k] for k in chosen_affix_keys]

    # 5. MP Cost & Multipliers
    # chain: 1.2x surcharge | aoe/summon: 1.4x surcharge | single/support: 1.0x
    base_mp = 6 if tier == 3 else (14 if tier == 2 else 26)
    target_type = shape_info["target_type"]
    if target_type == "chain":
        base_mp = int(round(base_mp * 1.2))
    elif target_type in ("aoe", "summon"):
        base_mp = int(round(base_mp * 1.4))

    # Apply Quickened MP reduction if rolled
    for af in rolled_affixes:
        if af["type"] == "efficiency":
            base_mp = max(3, int(round(base_mp * (1.0 - af["mp_reduction_pct"]))))

    # 6. Power scaling / Heals / Buffs / Summons
    scen_key = normalize_scenario_key(scenario)
    spell_id = f"proc_{school.lower()}_{element}_{shape}_t{tier}_{random.randint(1000, 9999)}"
    name = generate_spell_name(school, element, shape, tier, chosen_affix_keys, scenario=scenario)

    # Status condition
    status_ailment = elem_info.get("ailment") if random.random() < (0.4 if tier == 3 else 0.75) else None
    duration = 2 if tier == 3 else 3
    for af in rolled_affixes:
        if af["type"] == "duration":
            duration += af["duration_bonus"]

    # Map school role to canonical discipline: "damage" -> "attack"
    canonical_discipline = "attack" if school_info["role"] in ("damage", "hybrid") else school_info["role"]

    spell_def: Dict[str, Any] = {
        "id": spell_id,
        "name": name,
        "emoji": school_info["emoji"],
        "school": school,
        "discipline": canonical_discipline,
        "damage_type": element,
        "target_type": shape_info["target_type"],
        "tier": tier,
        "tier_name": tier_name,
        "mp_cost": base_mp,
        "shape": shape,
        "acc_mod": shape_info.get("acc_mod", 0),
        "crit_bonus": shape_info.get("crit_bonus", 0.0),
        "affixes": chosen_affix_keys,
        "tags": [school, elem_info["name"], shape_info["name"], tier_name] + [af["name"] for af in rolled_affixes]
    }

    # Chain: inject bounce metadata
    if shape_info["target_type"] == "chain":
        spell_def["max_bounces"] = shape_info.get("max_bounces", 3)
        spell_def["decay_rate"] = shape_info.get("decay_rate", 0.25)

    # AOE: inject glancing blast floor
    if shape_info["target_type"] == "aoe":
        spell_def["glance_floor"] = shape_info.get("glance_floor", 0.35)


    # Discipline specific calculations
    if school_info["role"] in ("damage", "hybrid"):
        min_p, max_p = school_info.get("power_mult_range", {3: (1.0, 1.2), 2: (1.6, 2.0), 1: (2.5, 3.2)}).get(tier, (1.0, 1.2))
        power = round(random.uniform(min_p, max_p), 2)
        for af in rolled_affixes:
            if af["type"] == "power":
                power = round(power * (1.0 + af["power_bonus"]), 2)
        spell_def["power_mult"] = power

        if status_ailment:
            spell_def["status_ailment"] = status_ailment
            spell_def["duration"] = duration
            if elem_info.get("dot"):
                spell_def["dot_damage"] = int(round(8 * tier * (1.5 if tier == 1 else 1.0)))

    elif school_info["role"] == "support":
        if school == "Abjuration":
            heal_min, heal_max = school_info.get("heal_range", {3: (20, 30)}).get(tier, (20, 30))
            spell_def["heal_amount"] = random.randint(heal_min, heal_max)
        else:
            spell_def["buff_pct"] = 0.15 if tier == 3 else (0.25 if tier == 2 else 0.40)
            spell_def["stat_target"] = random.choice(school_info.get("buff_targets", ["DEF"]))
            spell_def["duration"] = duration

    elif school_info["role"] == "curse":
        spell_def["debuff_pct"] = 0.15 if tier == 3 else (0.25 if tier == 2 else 0.40)
        spell_def["stat_target"] = random.choice(school_info.get("debuff_targets", ["ATK"]))
        spell_def["duration"] = duration
        if status_ailment:
            spell_def["status_ailment"] = status_ailment

    elif school_info["role"] == "summon":
        if scen_key == "steampunk":
            summon_candidates = ["clockwork_drone", "steam_automaton", "clockwork_colossus"]
        elif scen_key == "cyberpunk":
            summon_candidates = ["micro_drone", "combat_automaton", "siege_mech"]
        elif scen_key == "dark_fantasy":
            summon_candidates = ["skeleton", "ghoul", "bone_colossus"]
        else:
            summon_candidates = school_info.get("summon_types", ["spirit_wolf"])
        summon_key = random.choice(summon_candidates)
        template = SUMMON_TEMPLATES.get(summon_key, SUMMON_TEMPLATES["spirit_wolf"])
        spell_def["summon_template"] = summon_key
        spell_def["summon_count"] = template.get("count", 1)
        spell_def["summon_duration"] = template.get("duration", 3)
        spell_def["summon_archetype"] = template.get("archetype", "Brute")

    # Generate rich description
    genre_descriptor = {
        "steampunk": f"{school_info['name']} mechanism (Aether/Clockwork).",
        "cyberpunk": f"{school_info['name']} protocol (Digital/Cyberdeck).",
        "dark_fantasy": f"{school_info['name']} hex (Grimdark/Wasteland).",
        "fantasy": f"{school_info['name']} spell."
    }.get(scen_key, f"{school_info['name']} spell.")

    spell_def["description"] = (
        f"{genre_descriptor} {shape_info['verb'].format(element=elem_info['name'])}. "
        f"Tier {tier} ({tier_name}) • {base_mp} MP."
    )
    if "heal_amount" in spell_def:
        spell_def["description"] += f" Restores +{spell_def['heal_amount']} HP."
    if "buff_pct" in spell_def:
        spell_def["description"] += f" Grants +{int(spell_def['buff_pct']*100)}% {spell_def.get('stat_target', 'DEF')} for {duration} turns."
    if "debuff_pct" in spell_def:
        spell_def["description"] += f" Inflicts -{int(spell_def['debuff_pct']*100)}% {spell_def.get('stat_target', 'ATK')} for {duration} turns."
    if "summon_template" in spell_def:
        spell_def["description"] += f" Summons {spell_def['summon_count']} {SUMMON_TEMPLATES.get(spell_def['summon_template'], {}).get('name', 'Summon')}(s) for {spell_def['summon_duration']} turns."

    return spell_def

# -----------------------------------------------------------------------------
# 8. PROCEDURAL SPELLBOOK ITEM GENERATOR
# -----------------------------------------------------------------------------

def generate_procedural_spellbook_item(
    scenario: str = "fantasy",
    tier: int = 3,
    school: Optional[str] = None
) -> Dict[str, Any]:
    """Generates an inventory item spellbook / grimoire teaching a procedurally generated spell."""
    spell = generate_procedural_spell(scenario=scenario, tier=tier, school=school)
    
    scen_key = normalize_scenario_key(scenario)
    if scen_key == "steampunk":
        tier_prefix = "Master Plan" if tier == 1 else ("Blueprint" if tier == 2 else "Schematic")
    elif scen_key == "cyberpunk":
        tier_prefix = "Black-ICE Drive" if tier == 1 else ("Datapad" if tier == 2 else "Data Shard")
    elif scen_key == "dark_fantasy":
        tier_prefix = "Forbidden Grimoire" if tier == 1 else ("Blighted Tome" if tier == 2 else "Foul Parchment")
    else:
        tier_prefix = "Grimoire" if tier == 1 else ("Tome" if tier == 2 else "Spellbook")

    name = f"{tier_prefix}: {spell['name']}"
    
    metadata = {
        "item_type": "Spellbook",
        "spell_id": spell["id"],
        "spell_name": spell["name"],
        "school": spell["school"],
        "discipline": spell["discipline"],
        "tier": tier,
        "damage_type": spell["damage_type"],
        "spell_data": spell,
        "is_spellbook": True,
        "tags": spell["tags"]
    }
    
    effect_str = f"[SPELLBOOK_JSON]{json.dumps(metadata)}"
    return {
        "name": name,
        "item_type": "Spellbook",
        "slot": None,
        "effect": effect_str,
        "metadata": metadata,
        "slot_cost": 1
    }
