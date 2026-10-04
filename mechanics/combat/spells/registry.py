from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple

SPELL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # PURE MAGIC (magical)
    # -------------------------------------------------------------------------
    "arcane_dart_t3_st": {
        "id": "arcane_dart_t3_st", "name": "Arcane Dart", "emoji": "🔮",
        "discipline": "attack", "damage_type": "magical", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Fires a concentrated missile of raw arcane force at a single foe."
    },
    "arcane_burst_t3_aoe": {
        "id": "arcane_burst_t3_aoe", "name": "Arcane Burst", "emoji": "✨",
        "discipline": "attack", "damage_type": "magical", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Detonates a shockwave of raw magic hitting all nearby enemies."
    },
    "arcane_lance_t2_st": {
        "id": "arcane_lance_t2_st", "name": "Arcane Lance", "emoji": "🔮",
        "discipline": "attack", "damage_type": "magical", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Conjures a high-velocity piercing spear of dense ether."
    },
    "arcane_barrage_t2_aoe": {
        "id": "arcane_barrage_t2_aoe", "name": "Arcane Barrage", "emoji": "✨",
        "discipline": "attack", "damage_type": "magical", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Unleashes a relentless storm of seeking arcane orbs across the battlefield."
    },
    "astral_beam_t1_st": {
        "id": "astral_beam_t1_st", "name": "Astral Beam", "emoji": "🌌",
        "discipline": "attack", "damage_type": "magical", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Channels a devastating beam of pure cosmic destruction into a single target."
    },
    "astral_cataclysm_t1_aoe": {
        "id": "astral_cataclysm_t1_aoe", "name": "Astral Cataclysm", "emoji": "🌌",
        "discipline": "attack", "damage_type": "magical", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Rips open the celestial void, obliterating the entire hostile formation."
    },

    # -------------------------------------------------------------------------
    # FIRE (fire)
    # -------------------------------------------------------------------------
    "firebolt_t3_st": {
        "id": "firebolt_t3_st", "name": "Firebolt", "emoji": "🔥",
        "discipline": "attack", "damage_type": "fire", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "status_ailment": "Burned", "dot_damage": 8,
        "description": "Hurls an incendiary mote of fire that may scorch the target over time."
    },
    "flame_wave_t3_aoe": {
        "id": "flame_wave_t3_aoe", "name": "Flame Wave", "emoji": "🔥",
        "discipline": "attack", "damage_type": "fire", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Sweeps a rolling wave of flames across the entire enemy rank."
    },
    "pyroblast_t2_st": {
        "id": "pyroblast_t2_st", "name": "Pyroblast", "emoji": "☄️",
        "discipline": "attack", "damage_type": "fire", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "status_ailment": "Burned", "dot_damage": 16,
        "description": "Hurls a massive molten boulder of compressed magma dealing searing damage."
    },
    "ignition_nova_t2_aoe": {
        "id": "ignition_nova_t2_aoe", "name": "Ignition Nova", "emoji": "💥",
        "discipline": "attack", "damage_type": "fire", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Triggers an expanding thermal detonation scorching all enemies."
    },
    "dragons_breath_t1_st": {
        "id": "dragons_breath_t1_st", "name": "Dragon's Breath", "emoji": "🐉",
        "discipline": "attack", "damage_type": "fire", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "status_ailment": "Burned", "dot_damage": 28,
        "description": "Channels ancient draconic wildfire that incinerates armor and flesh alike."
    },
    "hellfire_inferno_t1_aoe": {
        "id": "hellfire_inferno_t1_aoe", "name": "Hellfire Inferno", "emoji": "🌋",
        "discipline": "attack", "damage_type": "fire", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "status_ailment": "Burned", "dot_damage": 20,
        "description": "Summons a torrential inferno of brimstone and hellfire upon all hostiles."
    },

    # -------------------------------------------------------------------------
    # LIGHTNING / SHOCK (shock)
    # -------------------------------------------------------------------------
    "spark_jolt_t3_st": {
        "id": "spark_jolt_t3_st", "name": "Spark Jolt", "emoji": "⚡",
        "discipline": "attack", "damage_type": "shock", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Zaps a target with crackling high-voltage electrostatic discharge."
    },
    "chain_lightning_t3_chain": {
        "id": "chain_lightning_t3_chain", "name": "Chain Lightning", "emoji": "⚡",
        "discipline": "attack", "damage_type": "shock", "tier": 3, "tier_name": "Basic",
        "target_type": "chain", "mp_cost": 8, "power_mult": 0.9,
        "acc_mod": 10, "crit_bonus": 0.0, "max_bounces": 3, "decay_rate": 0.25,
        "description": "Fires an electric bolt that leaps from foe to foe."
    },
    "lightning_strike_t2_st": {
        "id": "lightning_strike_t2_st", "name": "Lightning Strike", "emoji": "🌩️",
        "discipline": "attack", "damage_type": "shock", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "status_ailment": "Shocked", "dot_damage": 12,
        "description": "Calls down a thunderbolt from the sky to smite a single enemy."
    },
    "thunder_surge_t2_aoe": {
        "id": "thunder_surge_t2_aoe", "name": "Thunder Surge", "emoji": "🌩️",
        "discipline": "attack", "damage_type": "shock", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Floods the combat zone with an overcharged electrical pulse."
    },
    "ion_cannon_t1_st": {
        "id": "ion_cannon_t1_st", "name": "Ion Cannon Blast", "emoji": "⚡",
        "discipline": "attack", "damage_type": "shock", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Concentrates a gigawatt plasma arc that vaporizes target defense."
    },
    "thunder_gods_wrath_t1_aoe": {
        "id": "thunder_gods_wrath_t1_aoe", "name": "Thunder God's Wrath", "emoji": "⚡",
        "discipline": "attack", "damage_type": "shock", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "status_ailment": "Shocked", "dot_damage": 22,
        "description": "Brings the wrath of the storm god, raining catastrophic lightning bolts upon all enemies."
    },

    # -------------------------------------------------------------------------
    # ICE / FROST (ice)
    # -------------------------------------------------------------------------
    "ice_shard_t3_st": {
        "id": "ice_shard_t3_st", "name": "Ice Shard", "emoji": "❄️",
        "discipline": "attack", "damage_type": "ice", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Shoots a needle-sharp icicle at high velocity."
    },
    "frost_cone_t3_aoe": {
        "id": "frost_cone_t3_aoe", "name": "Frost Cone", "emoji": "❄️",
        "discipline": "attack", "damage_type": "ice", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Blasts a wide chilling breeze that freezes all enemy ranks."
    },
    "glacial_spike_t2_st": {
        "id": "glacial_spike_t2_st", "name": "Glacial Spike", "emoji": "🧊",
        "discipline": "attack", "damage_type": "ice", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "status_ailment": "Chilled", "dot_damage": 10,
        "description": "Impales a target with a massive permafrost glacier pillar."
    },
    "blizzard_storm_t2_aoe": {
        "id": "blizzard_storm_t2_aoe", "name": "Blizzard Storm", "emoji": "🌨️",
        "discipline": "attack", "damage_type": "ice", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Summons a howling sub-zero blizzard across the entire field."
    },
    "absolute_zero_t1_st": {
        "id": "absolute_zero_t1_st", "name": "Absolute Zero Lance", "emoji": "🧊",
        "discipline": "attack", "damage_type": "ice", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "status_ailment": "Frozen", "dot_damage": 25,
        "description": "Drops local temperature to absolute zero, shattering atomic bonds in target."
    },
    "glacial_ruin_t1_aoe": {
        "id": "glacial_ruin_t1_aoe", "name": "Glacial Ruin", "emoji": "🌨️",
        "discipline": "attack", "damage_type": "ice", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "status_ailment": "Chilled", "dot_damage": 18,
        "description": "Entombs the entire battlefield in an epoch of unyielding ice."
    },

    # -------------------------------------------------------------------------
    # WATER (water)
    # -------------------------------------------------------------------------
    "water_jet_t3_st": {
        "id": "water_jet_t3_st", "name": "Water Jet", "emoji": "💧",
        "discipline": "attack", "damage_type": "water", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Fires a high-pressure jet stream of water."
    },
    "tidal_splash_t3_aoe": {
        "id": "tidal_splash_t3_aoe", "name": "Tidal Splash", "emoji": "🌊",
        "discipline": "attack", "damage_type": "water", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Creates a surging splash of water that crashes against all foes."
    },
    "hydro_surge_t2_st": {
        "id": "hydro_surge_t2_st", "name": "Hydro Surge", "emoji": "💧",
        "discipline": "attack", "damage_type": "water", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Conjures a churning vortex geyser underneath a single foe."
    },
    "tidal_wave_t2_aoe": {
        "id": "tidal_wave_t2_aoe", "name": "Tidal Wave", "emoji": "🌊",
        "discipline": "attack", "damage_type": "water", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Summons an unstoppable cresting tidal tsunami across all hostiles."
    },
    "abyssal_torrent_t1_st": {
        "id": "abyssal_torrent_t1_st", "name": "Abyssal Torrent", "emoji": "🌊",
        "discipline": "attack", "damage_type": "water", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Channels ocean trench pressures to crush a single enemy into dust."
    },
    "leviathan_maelstrom_t1_aoe": {
        "id": "leviathan_maelstrom_t1_aoe", "name": "Leviathan Maelstrom", "emoji": "🌀",
        "discipline": "attack", "damage_type": "water", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Summons a roaring leviathan whirlpool drowning all opposition."
    },

    # -------------------------------------------------------------------------
    # EARTH (earth)
    # -------------------------------------------------------------------------
    "stone_spike_t3_st": {
        "id": "stone_spike_t3_st", "name": "Stone Spike", "emoji": "🪨",
        "discipline": "attack", "damage_type": "earth", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Shoots a sharp bedrock spike from the earth directly into a target."
    },
    "tremor_shock_t3_aoe": {
        "id": "tremor_shock_t3_aoe", "name": "Tremor Shock", "emoji": "🪨",
        "discipline": "attack", "damage_type": "earth", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Ripples the ground with shockwaves, staggering all hostiles."
    },
    "boulder_crush_t2_st": {
        "id": "boulder_crush_t2_st", "name": "Boulder Crush", "emoji": "⛰️",
        "discipline": "attack", "damage_type": "earth", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Drops a massive granite boulder atop an enemy."
    },
    "earthquake_t2_aoe": {
        "id": "earthquake_t2_aoe", "name": "Earthquake Rupture", "emoji": "🌋",
        "discipline": "attack", "damage_type": "earth", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Shatters the foundation beneath all enemies with seismic fury."
    },
    "meteor_drop_t1_st": {
        "id": "meteor_drop_t1_st", "name": "Meteor Drop", "emoji": "☄️",
        "discipline": "attack", "damage_type": "earth", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Pulls a flaming planetary meteor from orbit into an enemy target."
    },
    "continental_shatter_t1_aoe": {
        "id": "continental_shatter_t1_aoe", "name": "Continental Shatter", "emoji": "🌋",
        "discipline": "attack", "damage_type": "earth", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Tears the tectonic plates apart, devastating the entire battlefield."
    },

    # -------------------------------------------------------------------------
    # WIND / AERO (wind)
    # -------------------------------------------------------------------------
    "gale_blade_t3_st": {
        "id": "gale_blade_t3_st", "name": "Gale Blade", "emoji": "💨",
        "discipline": "attack", "damage_type": "wind", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Slices a target with a pressurized crescent blade of wind."
    },
    "wind_gust_t3_aoe": {
        "id": "wind_gust_t3_aoe", "name": "Wind Gust", "emoji": "💨",
        "discipline": "attack", "damage_type": "wind", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Conjures a howling gale that buffets and damages all enemies."
    },
    "sonic_blade_t2_st": {
        "id": "sonic_blade_t2_st", "name": "Sonic Blade", "emoji": "🌪️",
        "discipline": "attack", "damage_type": "wind", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Fires a supersonic wind vortex that rends armor."
    },
    "vortex_cyclone_t2_aoe": {
        "id": "vortex_cyclone_t2_aoe", "name": "Vortex Cyclone", "emoji": "🌪️",
        "discipline": "attack", "damage_type": "wind", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Whips up a destructive whirlwind shredding all foes in its radius."
    },
    "razor_tempest_t1_st": {
        "id": "razor_tempest_t1_st", "name": "Razor Tempest", "emoji": "🌪️",
        "discipline": "attack", "damage_type": "wind", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Funnels a localized hyper-pressurized vacuum blade through a foe."
    },
    "sky_ripping_hurricane_t1_aoe": {
        "id": "sky_ripping_hurricane_t1_aoe", "name": "Sky-Ripping Hurricane", "emoji": "🌀",
        "discipline": "attack", "damage_type": "wind", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Unleashes a category-5 typhoon storm across the entire battleground."
    },

    # -------------------------------------------------------------------------
    # POISON / TOXIC (poison)
    # -------------------------------------------------------------------------
    "venom_dart_t3_st": {
        "id": "venom_dart_t3_st", "name": "Venom Dart", "emoji": "🧪",
        "discipline": "attack", "damage_type": "poison", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.1,
        "status_ailment": "Poisoned", "dot_damage": 10,
        "description": "Shoots an acidic venom quill infecting the target with lingering poison."
    },
    "toxic_miasma_t3_aoe": {
        "id": "toxic_miasma_t3_aoe", "name": "Toxic Miasma", "emoji": "🧪",
        "discipline": "attack", "damage_type": "poison", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.8,
        "status_ailment": "Poisoned", "dot_damage": 6,
        "description": "Releases a noxious cloud of poison gas across all hostiles."
    },
    "noxious_blast_t2_st": {
        "id": "noxious_blast_t2_st", "name": "Noxious Blast", "emoji": "☣️",
        "discipline": "attack", "damage_type": "poison", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 1.8,
        "status_ailment": "Poisoned", "dot_damage": 18,
        "description": "Fires a concentrated glob of corrosive acid that eats into biological matter."
    },
    "venomous_cloud_t2_aoe": {
        "id": "venomous_cloud_t2_aoe", "name": "Venomous Cloud", "emoji": "☣️",
        "discipline": "attack", "damage_type": "poison", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.3,
        "status_ailment": "Poisoned", "dot_damage": 14,
        "description": "Spreads a dense choking smog of bio-toxins over all enemies."
    },
    "deathblight_needle_t1_st": {
        "id": "deathblight_needle_t1_st", "name": "Deathblight Needle", "emoji": "☠️",
        "discipline": "attack", "damage_type": "poison", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.0,
        "status_ailment": "Poisoned", "dot_damage": 32,
        "description": "Injects an incurable necro-toxin into an enemy's vital core."
    },
    "plaguewind_t1_aoe": {
        "id": "plaguewind_t1_aoe", "name": "Plaguewind Extinction", "emoji": "☠️",
        "discipline": "attack", "damage_type": "poison", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.2,
        "status_ailment": "Poisoned", "dot_damage": 24,
        "description": "Summons the black wind of pestilence, decaying all enemy lifeforms."
    },

    # -------------------------------------------------------------------------
    # HOLY / LIGHT (holy)
    # -------------------------------------------------------------------------
    "radiant_spark_t3_st": {
        "id": "radiant_spark_t3_st", "name": "Radiant Spark", "emoji": "✨",
        "discipline": "attack", "damage_type": "holy", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Emits a beam of consecrated holy luminescence."
    },
    "holy_light_t3_aoe": {
        "id": "holy_light_t3_aoe", "name": "Holy Radiance", "emoji": "✨",
        "discipline": "attack", "damage_type": "holy", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Flashes a burst of sacred light burning all nearby enemies."
    },
    "sunburst_smite_t2_st": {
        "id": "sunburst_smite_t2_st", "name": "Sunburst Smite", "emoji": "☀️",
        "discipline": "attack", "damage_type": "holy", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Calls down a focused beam of pure solar wrath onto an enemy."
    },
    "divine_radiance_t2_aoe": {
        "id": "divine_radiance_t2_aoe", "name": "Divine Radiance", "emoji": "☀️",
        "discipline": "attack", "damage_type": "holy", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Floods the battlefield with celestial daylight scorching all darkness."
    },
    "heavens_judgement_t1_st": {
        "id": "heavens_judgement_t1_st", "name": "Heaven's Judgement", "emoji": "🌟",
        "discipline": "attack", "damage_type": "holy", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Summons a gigantic blade of holy light descending directly onto a foe."
    },
    "solar_ascension_t1_aoe": {
        "id": "solar_ascension_t1_aoe", "name": "Solar Ascension", "emoji": "🌟",
        "discipline": "attack", "damage_type": "holy", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Channels the core of the sun itself, disintegrating all enemy ranks."
    },

    # -------------------------------------------------------------------------
    # DARK / SHADOW (dark)
    # -------------------------------------------------------------------------
    "shadow_bolt_t3_st": {
        "id": "shadow_bolt_t3_st", "name": "Shadow Bolt", "emoji": "🌑",
        "discipline": "attack", "damage_type": "dark", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Hurls a bolt of condensed dark ether at a single enemy."
    },
    "shadow_veil_t3_aoe": {
        "id": "shadow_veil_t3_aoe", "name": "Shadow Veil", "emoji": "🌑",
        "discipline": "attack", "damage_type": "dark", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Envelops all enemies in a caustic cloud of darkness."
    },
    "abyssal_spike_t2_st": {
        "id": "abyssal_spike_t2_st", "name": "Abyssal Spike", "emoji": "🖤",
        "discipline": "attack", "damage_type": "dark", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Summons a jagged spike of void matter through target's shadow."
    },
    "nether_grasp_t2_aoe": {
        "id": "nether_grasp_t2_aoe", "name": "Nether Grasp", "emoji": "🖤",
        "discipline": "attack", "damage_type": "dark", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Ghostly shadow hands erupt from the ground, crushing all enemies."
    },
    "void_singularity_t1_st": {
        "id": "void_singularity_t1_st", "name": "Void Singularity", "emoji": "🕳️",
        "discipline": "attack", "damage_type": "dark", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Opens a micro black hole within a single foe, collapsing their lifeforce."
    },
    "eclipse_of_ruin_t1_aoe": {
        "id": "eclipse_of_ruin_t1_aoe", "name": "Eclipse of Ruin", "emoji": "🕳️",
        "discipline": "attack", "damage_type": "dark", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Blots out the sky with cosmic dark energy that annihilates all hostiles."
    },

    # -------------------------------------------------------------------------
    # CONJURATION / PHYSICAL (physical)
    # -------------------------------------------------------------------------
    "conjure_blade_t3_st": {
        "id": "conjure_blade_t3_st", "name": "Conjure Blade", "emoji": "🗡️",
        "discipline": "attack", "damage_type": "physical", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "power_mult": 1.2,
        "description": "Manifests a spectral steel blade that lunges forward into target."
    },
    "iron_shrapnel_t3_aoe": {
        "id": "iron_shrapnel_t3_aoe", "name": "Iron Shrapnel", "emoji": "🗡️",
        "discipline": "attack", "damage_type": "physical", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "power_mult": 0.9,
        "description": "Conjures and explodes iron caltrops and daggers over all foes."
    },
    "conjure_greatsword_t2_st": {
        "id": "conjure_greatsword_t2_st", "name": "Conjure Greatsword", "emoji": "⚔️",
        "discipline": "attack", "damage_type": "physical", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "power_mult": 2.0,
        "description": "Summons a massive phantom greatsword slamming down on a single enemy."
    },
    "blade_tempest_t2_aoe": {
        "id": "blade_tempest_t2_aoe", "name": "Blade Tempest", "emoji": "⚔️",
        "discipline": "attack", "damage_type": "physical", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 20, "power_mult": 1.5,
        "description": "Orchestrates a spinning storm of dozens of conjured steel swords."
    },
    "executioners_blade_t1_st": {
        "id": "executioners_blade_t1_st", "name": "Executioner's Guilliotine", "emoji": "🪓",
        "discipline": "attack", "damage_type": "physical", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 26, "power_mult": 3.2,
        "description": "Manifests a colossal divine guillotine delivering a lethal physical strike."
    },
    "thousand_swords_t1_aoe": {
        "id": "thousand_swords_t1_aoe", "name": "Thousand Sword Rain", "emoji": "⚔️",
        "discipline": "attack", "damage_type": "physical", "tier": 1, "tier_name": "Master",
        "target_type": "aoe", "mp_cost": 36, "power_mult": 2.4,
        "description": "Blankets the sky with a thousand ethereal blades that rain upon all enemies."
    },

    # =========================================================================
    # SUPPORT & BOON MAGIC (support)
    # =========================================================================
    "mend_t3_st": {
        "id": "mend_t3_st", "name": "Mend", "emoji": "💚",
        "discipline": "support", "damage_type": "holy", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "heal_amount": 25,
        "description": "Knits flesh and restores 25 HP to self or an ally."
    },
    "greater_heal_t2_st": {
        "id": "greater_heal_t2_st", "name": "Greater Heal", "emoji": "💚",
        "discipline": "support", "damage_type": "holy", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 14, "heal_amount": 65,
        "description": "Restores 65 HP with powerful radiant rejuvenation."
    },
    "divine_restoration_t1_st": {
        "id": "divine_restoration_t1_st", "name": "Divine Restoration", "emoji": "💖",
        "discipline": "support", "damage_type": "holy", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 24, "heal_amount": 150,
        "description": "Channels supreme celestial energy restoring 150 HP."
    },
    "clarity_t3_st": {
        "id": "clarity_t3_st", "name": "Clarity Focus", "emoji": "💙",
        "discipline": "support", "damage_type": "magical", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 0, "mp_amount": 15,
        "description": "Deep meditation restoring 15 MP over the round."
    },
    "mana_tide_t2_st": {
        "id": "mana_tide_t2_st", "name": "Mana Surge", "emoji": "💙",
        "discipline": "support", "damage_type": "magical", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 0, "mp_amount": 35,
        "description": "Taps into ambient leylines, instantly replenishing 35 MP."
    },
    "aegis_ward_t3_st": {
        "id": "aegis_ward_t3_st", "name": "Aegis Ward", "emoji": "🛡️",
        "discipline": "support", "damage_type": "magical", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "buff_pct": 0.15, "stat_target": "DEF", "duration": 2,
        "status_ailment": "Fortified",
        "description": "Raises an arcane shield boosting DEF and MDEF by +15% for 2 turns."
    },
    "diamond_shell_t2_st": {
        "id": "diamond_shell_t2_st", "name": "Diamond Shell", "emoji": "🛡️",
        "discipline": "support", "damage_type": "magical", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 12, "buff_pct": 0.25, "stat_target": "DEF", "duration": 3,
        "status_ailment": "Fortified",
        "description": "Encases target in a crystalline barrier boosting DEF and MDEF by +25% for 3 turns."
    },
    "invulnerable_bastion_t1_st": {
        "id": "invulnerable_bastion_t1_st", "name": "Invulnerable Bastion", "emoji": "🛡️",
        "discipline": "support", "damage_type": "magical", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 22, "buff_pct": 0.40, "stat_target": "DEF", "duration": 3,
        "status_ailment": "Invulnerable",
        "description": "Constructs an impenetrable divine barrier boosting DEF and MDEF by +40% for 3 turns."
    },
    "war_cry_t3_st": {
        "id": "war_cry_t3_st", "name": "War Cry", "emoji": "⚔️",
        "discipline": "support", "damage_type": "physical", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "buff_pct": 0.15, "stat_target": "ATK", "duration": 2,
        "status_ailment": "Empowered",
        "description": "Bolsters combat spirit, increasing ATK and MATK by +15% for 2 turns."
    },
    "empower_surge_t2_st": {
        "id": "empower_surge_t2_st", "name": "Empower Surge", "emoji": "⚔️",
        "discipline": "support", "damage_type": "magical", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 12, "buff_pct": 0.25, "stat_target": "ATK", "duration": 3,
        "status_ailment": "Empowered",
        "description": "Surges lifeforce into weapons, increasing ATK and MATK by +25% for 3 turns."
    },
    "overwhelming_might_t1_st": {
        "id": "overwhelming_might_t1_st", "name": "Overwhelming Might", "emoji": "💥",
        "discipline": "support", "damage_type": "magical", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 22, "buff_pct": 0.40, "stat_target": "ATK", "duration": 3,
        "status_ailment": "Empowered",
        "description": "Channels raw destructive might, boosting ATK and MATK by +40% for 3 turns."
    },
    "zephyr_step_t3_st": {
        "id": "zephyr_step_t3_st", "name": "Zephyr Step", "emoji": "💨",
        "discipline": "support", "damage_type": "wind", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "buff_pct": 0.15, "stat_target": "AGI", "duration": 2,
        "status_ailment": "Haste",
        "description": "Lightens footwork with wind currents, increasing EVA and ACC by +15% for 2 turns."
    },
    "haste_surge_t2_st": {
        "id": "haste_surge_t2_st", "name": "Haste Surge", "emoji": "💨",
        "discipline": "support", "damage_type": "wind", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 12, "buff_pct": 0.25, "stat_target": "AGI", "duration": 3,
        "status_ailment": "Haste",
        "description": "Accelerates time perception, increasing EVA and ACC by +25% for 3 turns."
    },

    # =========================================================================
    # CURSE & HEX MAGIC (curse)
    # =========================================================================
    "weaken_t3_st": {
        "id": "weaken_t3_st", "name": "Weaken Hex", "emoji": "💀",
        "discipline": "curse", "damage_type": "dark", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "debuff_pct": 0.15, "stat_target": "ATK", "duration": 2,
        "status_ailment": "Weakened",
        "description": "Curses target's muscles and ether, reducing ATK and MATK by -15% for 2 turns."
    },
    "enfeeble_t2_st": {
        "id": "enfeeble_t2_st", "name": "Enfeeblement", "emoji": "💀",
        "discipline": "curse", "damage_type": "dark", "tier": 2, "tier_name": "Advanced",
        "target_type": "single", "mp_cost": 12, "debuff_pct": 0.25, "stat_target": "ATK", "duration": 3,
        "status_ailment": "Weakened",
        "description": "Deeply saps target strength, reducing ATK and MATK by -25% for 3 turns."
    },
    "total_debilitation_t1_st": {
        "id": "total_debilitation_t1_st", "name": "Total Debilitation", "emoji": "☠️",
        "discipline": "curse", "damage_type": "dark", "tier": 1, "tier_name": "Master",
        "target_type": "single", "mp_cost": 22, "debuff_pct": 0.40, "stat_target": "ATK", "duration": 3,
        "status_ailment": "Crippled",
        "description": "Inflicts a crushing curse reducing target ATK and MATK by -40% for 3 turns."
    },
    "corrode_armor_t3_st": {
        "id": "corrode_armor_t3_st", "name": "Corrode Armor", "emoji": "🧪",
        "discipline": "curse", "damage_type": "poison", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "debuff_pct": 0.15, "stat_target": "DEF", "duration": 2,
        "status_ailment": "Exposed",
        "description": "Dissolves target armor plating, reducing DEF and MDEF by -15% for 2 turns."
    },
    "acid_nova_t2_aoe": {
        "id": "acid_nova_t2_aoe", "name": "Acid Nova", "emoji": "🧪",
        "discipline": "curse", "damage_type": "poison", "tier": 2, "tier_name": "Advanced",
        "target_type": "aoe", "mp_cost": 16, "debuff_pct": 0.25, "stat_target": "DEF", "duration": 3,
        "status_ailment": "Exposed",
        "description": "Sprays caustic acid over all foes, reducing their DEF and MDEF by -25% for 3 turns."
    },
    "slow_t3_st": {
        "id": "slow_t3_st", "name": "Entangle Slow", "emoji": "🕸️",
        "discipline": "curse", "damage_type": "earth", "tier": 3, "tier_name": "Basic",
        "target_type": "single", "mp_cost": 6, "debuff_pct": 0.15, "stat_target": "AGI", "duration": 2,
        "status_ailment": "Slowed",
        "description": "Wraps roots and ethereal chains around a foe, reducing EVA and ACC by -15% for 2 turns."
    },
    "dark_mist_t3_aoe": {
        "id": "dark_mist_t3_aoe", "name": "Blinding Mist", "emoji": "🌫️",
        "school": "Illusion", "discipline": "curse", "damage_type": "dark", "tier": 3, "tier_name": "Basic",
        "target_type": "aoe", "mp_cost": 10, "debuff_pct": 0.15, "stat_target": "ACC", "duration": 2,
        "status_ailment": "Blinded",
        "description": "Blinds all hostiles with dark fog, reducing their hit accuracy by -15% for 2 turns."
    },

    # -------------------------------------------------------------------------
    # SUMMONING SPELLS (Conjuration & Necromancy)
    # -------------------------------------------------------------------------
    "raise_skeletons_t3_st": {
        "id": "raise_skeletons_t3_st", "name": "Raise Skeletons", "emoji": "💀",
        "school": "Necromancy", "discipline": "summon", "damage_type": "necrotic", "tier": 3, "tier_name": "Basic",
        "target_type": "summon", "mp_cost": 10, "summon_template": "skeleton",
        "summon_count": 2, "summon_duration": 3, "summon_archetype": "Skirmisher",
        "description": "Animates 2 Dread Skeletons from bone shards to fight at your side for 3 turns."
    },
    "call_spirit_wolves_t3_st": {
        "id": "call_spirit_wolves_t3_st", "name": "Call Spirit Wolves", "emoji": "🐺",
        "school": "Conjuration", "discipline": "summon", "damage_type": "physical", "tier": 3, "tier_name": "Basic",
        "target_type": "summon", "mp_cost": 10, "summon_template": "spirit_wolf",
        "summon_count": 2, "summon_duration": 3, "summon_archetype": "Stalker",
        "description": "Summons 2 ethereal Spirit Wolves with high evasion to flank hostiles for 3 turns."
    },
    "conjure_flame_imps_t3_st": {
        "id": "conjure_flame_imps_t3_st", "name": "Conjure Flame Imps", "emoji": "🔥",
        "school": "Conjuration", "discipline": "summon", "damage_type": "fire", "tier": 3, "tier_name": "Basic",
        "target_type": "summon", "mp_cost": 10, "summon_template": "fire_imp",
        "summon_count": 2, "summon_duration": 3, "summon_archetype": "Skirmisher",
        "description": "Summons 2 minor Flame Imps hurling fiery projectiles for 3 turns."
    },
    "guardian_wisp_t3_st": {
        "id": "guardian_wisp_t3_st", "name": "Guardian Wisp", "emoji": "✨",
        "school": "Abjuration", "discipline": "summon", "damage_type": "radiant", "tier": 3, "tier_name": "Basic",
        "target_type": "summon", "mp_cost": 8, "summon_template": "guardian_wisp",
        "summon_count": 1, "summon_duration": 3, "summon_archetype": "Caster",
        "description": "Summons a glowing benevolent spirit wisp to protect and heal the party for 3 turns."
    },
    "deploy_micro_drones_t3_st": {
        "id": "deploy_micro_drones_t3_st", "name": "Deploy Micro-Drones", "emoji": "🤖",
        "school": "Conjuration", "discipline": "summon", "damage_type": "lightning", "tier": 3, "tier_name": "Basic",
        "target_type": "summon", "mp_cost": 10, "summon_template": "micro_drone",
        "summon_count": 2, "summon_duration": 3, "summon_archetype": "Security Drone",
        "description": "Launches 2 hovering attack drones equipped with laser pulsers for 3 turns."
    },
    "summon_ghoul_pack_t2_st": {
        "id": "summon_ghoul_pack_t2_st", "name": "Summon Ghoul Pack", "emoji": "🧟",
        "school": "Necromancy", "discipline": "summon", "damage_type": "poison", "tier": 2, "tier_name": "Advanced",
        "target_type": "summon", "mp_cost": 18, "summon_template": "ghoul",
        "summon_count": 2, "summon_duration": 4, "summon_archetype": "Brute",
        "description": "Summons 2 ravenous Flesh Ghouls that rend enemy armor for 4 turns."
    },
    "summon_dire_bear_t2_st": {
        "id": "summon_dire_bear_t2_st", "name": "Summon Dire Bear", "emoji": "🐻",
        "school": "Conjuration", "discipline": "summon", "damage_type": "physical", "tier": 2, "tier_name": "Advanced",
        "target_type": "summon", "mp_cost": 18, "summon_template": "dire_bear",
        "summon_count": 1, "summon_duration": 4, "summon_archetype": "Guardian",
        "description": "Calls forth a massive primal Dire Bear with high HP to tank enemy blows for 4 turns."
    },
    "summon_celestial_sentinel_t2_st": {
        "id": "summon_celestial_sentinel_t2_st", "name": "Celestial Sentinel", "emoji": "🛡️",
        "school": "Abjuration", "discipline": "summon", "damage_type": "radiant", "tier": 2, "tier_name": "Advanced",
        "target_type": "summon", "mp_cost": 18, "summon_template": "celestial_sentinel",
        "summon_count": 1, "summon_duration": 4, "summon_archetype": "Guardian",
        "description": "Summons a radiant winged champion with a holy shield to guard the party for 4 turns."
    },
    "awaken_bone_colossus_t1_st": {
        "id": "awaken_bone_colossus_t1_st", "name": "Awaken Bone Colossus", "emoji": "☠️",
        "school": "Necromancy", "discipline": "summon", "damage_type": "necrotic", "tier": 1, "tier_name": "Master",
        "target_type": "summon", "mp_cost": 30, "summon_template": "bone_colossus",
        "summon_count": 1, "summon_duration": 5, "summon_archetype": "Guardian",
        "description": "Assembles a towering juggernaut of calcified bone skulls to dominate the battlefield for 5 turns."
    },
    "wrath_of_nature_hydra_t1_st": {
        "id": "wrath_of_nature_hydra_t1_st", "name": "Wrath of Nature: Apex Hydra", "emoji": "🐉",
        "school": "Conjuration", "discipline": "summon", "damage_type": "poison", "tier": 1, "tier_name": "Master",
        "target_type": "summon", "mp_cost": 30, "summon_template": "hydra",
        "summon_count": 1, "summon_duration": 5, "summon_archetype": "Brute",
        "description": "Unleashes a primordial multi-headed apex hydra tearing through all hostiles for 5 turns."
    }
}



for spell_id, spell in SPELL_REGISTRY.items():
    if "tags" not in spell:
        spell["tags"] = {
            "discipline": spell.get("discipline", "attack"),
            "school": spell.get("school", "Evocation"),
            "element": spell.get("damage_type", "magical"),
            "target_type": spell.get("target_type", "single"),
            "tier": spell.get("tier", 3),
            "delivery": "ranged_projectile" if spell.get("target_type") == "single" else "ranged_aoe",
            "status_infliction": [spell["status_ailment"]] if spell.get("status_ailment") else []
        }

    # Inject streamlined targeting metadata for spells that don't yet have it
    tt = spell.get("target_type", "single")
    if "acc_mod" not in spell:
        if tt == "chain":
            spell["acc_mod"] = 10
        elif tt == "aoe":
            spell["acc_mod"] = -5
        elif tt in ("support", "summon"):
            spell["acc_mod"] = 100
        else:
            spell["acc_mod"] = 0
    if "crit_bonus" not in spell:
        spell["crit_bonus"] = 0.0
    if tt == "aoe" and "glance_floor" not in spell:
        spell["glance_floor"] = 0.35
    if tt == "chain":
        if "max_bounces" not in spell:
            spell["max_bounces"] = 3
        if "decay_rate" not in spell:
            spell["decay_rate"] = 0.25


def register_spell(spell_def: Dict[str, Any]) -> None:
    if "id" in spell_def:
        # Guarantee streamlined targeting metadata exists
        tt = spell_def.get("target_type", "single")
        if "acc_mod" not in spell_def:
            if tt == "chain":
                spell_def["acc_mod"] = 10
            elif tt == "aoe":
                spell_def["acc_mod"] = -5
            elif tt in ("support", "summon"):
                spell_def["acc_mod"] = 100
            else:
                spell_def["acc_mod"] = 0
        if "crit_bonus" not in spell_def:
            spell_def["crit_bonus"] = 0.0
        if tt == "aoe" and "glance_floor" not in spell_def:
            spell_def["glance_floor"] = 0.35
        if tt == "chain":
            if "max_bounces" not in spell_def:
                spell_def["max_bounces"] = 3
            if "decay_rate" not in spell_def:
                spell_def["decay_rate"] = 0.25

        SPELL_REGISTRY[spell_def["id"]] = spell_def

        # Persist procedural spells into SQLite so they survive bot restarts
        if str(spell_def["id"]).startswith("proc_"):
            try:
                import db
                db.save_procedural_spell(spell_def)
            except Exception:
                pass

def get_spell(spell_id: str) -> Optional[Dict[str, Any]]:
    if not spell_id:
        return None
    if spell_id in SPELL_REGISTRY:
        return SPELL_REGISTRY[spell_id]
    
    # Lazy fallback: attempt to re-hydrate from database
    try:
        import db
        proc_spell = db.get_procedural_spell(spell_id)
        if proc_spell:
            register_spell(proc_spell)
            return proc_spell
    except Exception:
        pass
    return None

def get_all_spells() -> Dict[str, Dict[str, Any]]:
    return SPELL_REGISTRY

def load_all_procedural_spells() -> int:
    """Loads all saved procedural spells from database into memory."""
    try:
        import db
        saved_spells = db.get_all_procedural_spells()
        for sp in saved_spells:
            register_spell(sp)
        return len(saved_spells)
    except Exception:
        return 0

