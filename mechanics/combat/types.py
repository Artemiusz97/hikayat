"""mechanics/combat/types.py

Canonical TypedDict data contracts and helper accessors for Hikayat's Phase 2 Unified Combatant Architecture.
Maintains 100% JSON safety across WebSockets, Discord bot embeds, and SQLite session blobs without OOP hierarchy.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, TypedDict, Union


class StatusEffectInstance(TypedDict, total=False):
    """First-class structured status effect instance with intensity stacking and duration tracking."""
    name: str                                                 # e.g., "Poisoned", "Staggered", "Bleeding", "Taunted"
    category: Literal["combat", "social", "intimate", "hazard"]
    duration_type: Literal["turns", "minutes", "permanent"]
    remaining_duration: int                                   # Turns (combat) or minutes (social/intimate); -1 for permanent
    max_duration: int
    duration: int                                             # Alias for remaining_duration (backward-compatibility for React UI)
    intensity_stacks: int                                     # Capped at 3 (+50% per stack -> 1.0x, 1.5x, 2.0x)
    potency: float                                            # Base magnitude (DoT damage or modifier %)
    source: str                                               # e.g., "player", "enemy:wyrm", "spell:ignite"
    metadata: Dict[str, Any]                                  # Stagger vulnerability, boss telegraph cancel tag


class CombatThreatLedger(TypedDict, total=False):
    """Dynamic threat and aggro score tracking matrix per enemy with sticky taunt support."""
    threat_matrix: Dict[str, Dict[str, float]]                # enemy_id -> {actor_id: threat_score}
    sticky_taunts: Dict[str, Dict[str, Any]]                  # enemy_id -> {"target_id": str, "remaining_turns": int}


class BossTelegraphState(TypedDict, total=False):
    """Telegraphed supreme boss move state with interrupt and stagger tracking."""
    enemy_id: str
    skill_name: str
    telegraphed_label: str
    target_id: Optional[str]
    target_name: Optional[str]
    turns_remaining: int
    interrupt_threshold: int
    accumulated_interrupt_damage: int
    damage_mult: float
    status_ailment: Optional[str]
    intent_code: str


class CombatAction(TypedDict, total=False):
    """Structured representation of a combat move, spell, or action intent."""
    id: str
    name: str
    category: str                     # "attack", "spell", "guard", "flee", "item"
    intent_code: str                  # "heavy", "magic", "ambush", "defensive", "swarm", "basic", "struggle"
    telegraphed_label: str            # Narrative flavor, e.g. "Winding up a heavy swing"
    mana_cost: int
    damage_mult: float
    damage_type: str                  # "physical", "magical", "ballistic", "thermal", etc.
    armor_penetration: float
    status_ailment: Optional[str]
    target_type: str                  # "single_enemy", "all_enemies", "self", "ally", "splash_frontline"


class CombatantState(TypedDict, total=False):
    """Canonical TypedDict schema for all combat participants (Player, Companions, Summons, Enemies)."""
    id: str                           # "player:<uid>", "npc:<id>", "enemy:<key>"
    name: str
    entity_type: str                  # "player" | "companion" | "construct" | "special_agent" | "civilian" | "enemy"
    team: str                         # "ally" | "enemy"
    level: int
    tier_rank: int                    # 1: Minion, 2: Standard, 3: Elite, 4: Miniboss, 5: Boss
    hp: int
    max_hp: int
    temp_hp: int
    mp: int
    max_mp: int
    stats: Dict[str, int]             # Canonical: STR, PER, END, CHA, INT, AGI, LUK
    attribute: str                    # 9-attribute wheel (physical, aether, thermal, etc.)
    combat_archetype: str             # vanguard, skirmisher, brute, caster, etc.
    weapon_profile: Dict[str, Any]    # atk_bonus, matk_bonus, damage_types, attack_types
    armor_profile: Dict[str, Any]     # base_dt, type_dt, block_chance, def_bonus, mdef_bonus
    active_intent: Optional[CombatAction]
    known_actions: List[CombatAction]
    status_effects: List[Any]
    stability: int
    max_stability: int
    is_breached: bool
    requires_non_lethal_subdue: bool
    subdue_threshold_pct: float
    is_autonomous_construct: bool
    is_summon: bool
    metadata: Dict[str, Any]


def get_combatant_stat(combatant: Optional[Dict[str, Any]], stat_name: str, default: int = 3) -> int:
    """Safely extracts a stat value from a combatant dict across flat, nested, and alias conventions.
    
    Supports:
      - Canonical nested uppercase: combatant["stats"]["STR"]
      - Nested lowercase: combatant["stats"]["str"]
      - Flat lowercase / alias: combatant["str_"], combatant["str"], combatant["STR"]
    """
    if not isinstance(combatant, dict):
        return default

    stat_upper = str(stat_name).upper().strip()
    stat_lower = stat_upper.lower()

    # 1. Check nested stats dict first (canonical structure)
    stats_dict = combatant.get("stats")
    if isinstance(stats_dict, dict):
        if stat_upper in stats_dict:
            try:
                return int(stats_dict[stat_upper])
            except (ValueError, TypeError):
                pass
        if stat_lower in stats_dict:
            try:
                return int(stats_dict[stat_lower])
            except (ValueError, TypeError):
                pass

    # 2. Check flat keys on root dict
    stat_aliases = [
        stat_upper,
        stat_lower,
        f"{stat_lower}_",
        f"base_{stat_lower}",
    ]
    for k in stat_aliases:
        if k in combatant and combatant[k] is not None:
            try:
                return int(combatant[k])
            except (ValueError, TypeError):
                pass

    return default
