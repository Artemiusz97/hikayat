from __future__ import annotations
"""
Non-lethal sparring duels and faction reinforcement logic.
"""
from typing import Optional, Dict, Any, List, Tuple
import random

# ---------------------------------------------------------------- Sparring Duel Support
def is_sparring_monster(monster: dict) -> bool:
    """Return True if this monster entry is a sparring opponent (non-lethal: yields at 0 HP)."""
    return bool(monster.get("sparring"))


def resolve_sparring_defeat(monster: dict) -> str:
    """Return the narrative directive for when a sparring opponent is 'defeated' (yields, not dies)."""
    name = monster.get("name", "your opponent")
    return (
        f"SPARRING DUEL DIRECTIVE: {name} has been defeated in the non-lethal sparring bout! "
        f"Narrate {name} stumbling back, raising their hand in concession, and formally acknowledging "
        f"the player's victory. Do NOT narrate {name}'s death — they yield, not die. "
        f"Set `faction_promotion_result` to 'success' in JSON outcome."
    )


def make_sparring_monster(incumbent_name: str, avg_level: int, scen_key: str) -> dict:
    """
    Build a sparring-flagged monster entry for a promotion trial duel.
    HP is scaled so the fight lasts 2-4 rounds. The monster does NOT award
    gold/XP and does NOT enter the loot tables.
    """
    from mechanics.combat.enemies import build_monster_stat_sheet
    level = max(1, avg_level + 1)  # Incumbent is slightly stronger
    max_hp = 30 + level * 10
    stats = build_monster_stat_sheet(level, "Duelist")
    return {
        "name": incumbent_name,
        "level": level,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": 0,
        "stats": stats,
        "status_effects": [],
        "sparring": True,       # Non-lethal flag
        "xp_multiplier": 0.0,  # No combat XP reward (promotion gives its own reward)
        "gold_drop": 0,
    }


# ---------------------------------------------------------------- Faction Patrol Reinforcements
def call_faction_reinforcements(session: dict, faction: dict, party: list) -> tuple[list[dict], str]:
    """
    Inject 1-2 scaled faction patrol NPCs into current_npcs as friendly combat allies.
    Returns (injected_npcs, narrative_note).
    Must only be called once per session (tracked via session['faction_reinforcements_used']).

    Usage:
        new_npcs, note = call_faction_reinforcements(session, faction, party)
        session['current_npcs'] = session.get('current_npcs', []) + new_npcs
        db.update_session(session_id, current_npcs=session['current_npcs'])
        db.set_faction_reinforcements_used(session_id, used=True)
    """
    from mechanics.social.factions import generate_faction_patrol
    scen_key = session.get("scenario", "fantasy")
    avg_level = max(1, int(sum(
        (char[0] if isinstance(char, (tuple, list)) else char).get("level", 1)
        for char in party
    ) / max(1, len(party))))

    patrols = generate_faction_patrol(faction, avg_level, scen_key)
    faction_name = faction.get("name", "Faction")
    count = len(patrols)
    note = (
        f"🎺 **{faction_name} Patrol Arrives!** {count} reinforcement{'s' if count > 1 else ''} "
        f"join{'s' if count == 1 else ''} your side! *(Call Reinforcements perk used — 1× per session)*"
    )
    return patrols, note
