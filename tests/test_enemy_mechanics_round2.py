import pytest
from unittest.mock import MagicMock, patch

from mechanics.combat.core import precompute_combat_turn
from mechanics.narrative.choice_generator import generate_categorized_combat_actions
from cogs.adventure.embeds import _format_tracker_entity
from game_engine.context import _describe_tracked_entity
from mechanics.combat.formulas import tick_status_timers


def test_dynamic_enemy_targeting():
    """Verify that player action targeting a specific enemy deals damage to that enemy, not enemy[0]."""
    goblin = {
        "name": "Goblin Scout",
        "level": 1,
        "hp": 50,
        "max_hp": 50,
        "tier_rank": 1,
        "stats": {"STR": 3, "AGI": 5, "INT": 2, "PER": 4, "END": 3, "CHA": 2, "LUK": 3}
    }
    orc = {
        "name": "Orc Warlord",
        "level": 3,
        "hp": 100,
        "max_hp": 100,
        "tier_rank": 4,
        "stats": {"STR": 8, "AGI": 3, "INT": 3, "PER": 4, "END": 7, "CHA": 4, "LUK": 3}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [goblin, orc],
        "turn_order": [123],
        "combat_turn": 1
    }
    party = [({"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 8, "agi_": 5, "luk": 5}, [])]
    
    # Action targeting the Orc Warlord specifically
    action = {
        "choice_type": "MELEE_SLASHING_PIERCING",
        "label": "Slash with Steel Sword",
        "target_entity": "Orc Warlord",
        "tier": "success",
        "stat": "STR",
        "requirement": 5
    }

    with patch("db.get_equipment", return_value={"Weapon": {"name": "Steel Sword", "archetype": "sword", "multiplier": 1.2}}), \
         patch("mechanics.combat.core.calculate_tactical_damage", return_value={"damage": 25, "blocked": False}):
        out = precompute_combat_turn(session, party, [action])

    # In session["nearby_enemies"], Goblin should remain undamaged at 50 HP, Orc should take 25 damage (75 HP)
    enemies_by_name = {e["name"]: e for e in session["nearby_enemies"]}
    assert enemies_by_name["Goblin Scout"]["hp"] == 50
    assert enemies_by_name["Orc Warlord"]["hp"] == 75
    assert any("Orc Warlord" in log and "25 damage" in log for log in out["combat_log"])


def test_defensive_guard_action():
    """Verify DEFENSIVE_GUARD applies defensive stance, +6 DT, +30% Block, and deals 0 weapon damage."""
    enemy = {
        "name": "Skeleton Warrior",
        "level": 1,
        "hp": 40,
        "max_hp": 40,
        "tier_rank": 2,
        "stats": {"STR": 5, "AGI": 3, "INT": 2, "PER": 3, "END": 4, "CHA": 1, "LUK": 2}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [enemy],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 5, "end_": 6, "luk": 5}
    party = [(player, [])]

    action = {
        "choice_type": "DEFENSIVE_GUARD",
        "label": "🛡️ Defensive Guard & Brace (75% • END)",
        "stat": "END",
        "tier": "success"
    }

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    # Enemy took 0 damage
    assert session["nearby_enemies"][0]["hp"] == 40
    # Player gained Defensive Guard status effect
    assert any("Defensive Guard" in s for s in player.get("status_effects", []))
    assert any("braces and assumes a defensive guard" in log for log in out["combat_log"])


def test_diplomacy_taunt_action():
    """Verify DIPLOMACY_TAUNT demoralizes the target enemy on success."""
    enemy = {
        "name": "Bandit Leader",
        "level": 2,
        "hp": 60,
        "max_hp": 60,
        "tier_rank": 3,
        "status_effects": [],
        "stats": {"STR": 6, "AGI": 4, "INT": 3, "PER": 4, "END": 5, "CHA": 3, "LUK": 2}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [enemy],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "cha": 8, "luk": 5}
    party = [(player, [])]

    action = {
        "choice_type": "DIPLOMACY_TAUNT",
        "label": "🗣️ Intimidate & Taunt",
        "stat": "CHA",
        "tier": "success"
    }

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    # Target enemy receives Demoralized status effect
    target_in_session = session["nearby_enemies"][0]
    assert any("Demoralized" in s for s in target_in_session["status_effects"])
    assert any("demoralized and suffer -15% ATK" in log for log in out["combat_log"])


def test_weakness_exploit_action():
    """Verify WEAKNESS_EXPLOIT scans and reveals weaknesses and resistances."""
    enemy = {
        "name": "Frost Golem",
        "level": 3,
        "hp": 80,
        "max_hp": 80,
        "tier_rank": 3,
        "weaknesses": ["fire", "blunt"],
        "resistances": ["cold", "piercing"],
        "immunities": ["poison"],
        "stats": {"STR": 7, "AGI": 2, "INT": 2, "PER": 3, "END": 8, "CHA": 1, "LUK": 1}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [enemy],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "per_": 7, "luk": 5}
    party = [(player, [])]

    action = {
        "choice_type": "WEAKNESS_EXPLOIT",
        "label": "👁️ Scan Weakpoint",
        "stat": "PER",
        "tier": "success"
    }

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    assert any("Weakpoint Analyzed" in s for s in player.get("status_effects", []))
    assert any("Weaknesses: fire, blunt" in log for log in out["combat_log"])
    assert any("Resistances: cold, piercing" in log for log in out["combat_log"])
    assert any("Immunities: poison" in log for log in out["combat_log"])


def test_evade_tactical_flee():
    """Verify EVADE_TACTICAL_FLEE successfully disengages, prevents counter-attacks, and clears hostiles."""
    enemy = {
        "name": "Dire Wolf",
        "level": 2,
        "hp": 50,
        "max_hp": 50,
        "tier_rank": 2,
        "stats": {"STR": 5, "AGI": 6, "INT": 2, "PER": 5, "END": 4, "CHA": 1, "LUK": 2}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [enemy],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "agi_": 8, "luk": 5}
    party = [(player, [])]

    action = {
        "choice_type": "EVADE_TACTICAL_FLEE",
        "label": "🏃 Disengage & Flee",
        "stat": "AGI",
        "tier": "success"
    }

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    assert out["fled_battle"] is True
    assert session["nearby_enemies"] == []
    assert out["total_player_damage"] == 0
    assert any("successfully disengaged and fled" in log for log in out["combat_log"])


def test_tier_reward_scaling():
    """Verify defeated enemies yield XP and Gold scaled by tier_rank."""
    minion = {
        "name": "Goblin Runt",
        "level": 1,
        "hp": 0,
        "max_hp": 20,
        "tier_rank": 1,
        "stats": {"STR": 2, "AGI": 3, "INT": 1, "PER": 2, "END": 2, "CHA": 1, "LUK": 1}
    }
    boss = {
        "name": "Dragon Overlord",
        "level": 10,
        "hp": 0,
        "max_hp": 300,
        "tier_rank": 5,
        "phase_2_triggered": True,
        "stats": {"STR": 12, "AGI": 8, "INT": 10, "PER": 8, "END": 12, "CHA": 8, "LUK": 5}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [minion, boss],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 5, "luk": 5}
    party = [(player, [])]

    action = {"choice_type": "DEFENSIVE_GUARD", "label": "Guard", "tier": "success"}
    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    # Minion yields 40 XP / 15 Gold, Boss yields 450 XP / 250 Gold -> Total: 490 XP, 265 Gold
    assert out["xp_gain"] == 40 + 450
    assert out["gold_gain"] == 15 + 250


def test_choice_generator_attaches_target_entity():
    """Verify that choice generator actions attach target_entity."""
    enemy = {"name": "Shadow Stalker", "stats": {"STR": 4, "AGI": 6, "INT": 4, "PER": 5, "END": 4, "CHA": 2, "LUK": 2}}
    char = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 6, "agi_": 6, "luk": 5}
    party = [(char, [])]

    cat = generate_categorized_combat_actions(party, enemy, "dungeon", "fantasy")
    for act in cat["attacks"]:
        assert act.get("target_entity") == "Shadow Stalker"
    for act in cat["tactics"]:
        assert act.get("target_entity") == "Shadow Stalker"


def test_ui_and_context_tier_intent_formatting():
    """Verify embeds and context serialize tier badges and intent."""
    enemy_boss = {
        "name": "Malakor",
        "level": 15,
        "hp": 400,
        "max_hp": 400,
        "tier_rank": 5,
        "intent": "Unleashing Cataclysmic Wave"
    }
    # UI embed tracker text
    embed_line = _format_tracker_entity(enemy_boss)
    assert "`[Boss]`" in embed_line
    assert "↳ ⚡ *Intent: Unleashing Cataclysmic Wave*" in embed_line

    # LLM context description
    context_desc = _describe_tracked_entity(enemy_boss)
    assert "Boss" in context_desc
    assert "intent: Unleashing Cataclysmic Wave" in context_desc


def test_between_turn_dot_casualty_purge():
    """Verify that when DoT tick drops an enemy's HP to 0 or below, it is purged from session nearby_enemies."""
    # Simulate the block from game_engine/turn.py lines 1251-1262
    living_enemy = {"name": "Orc Guard", "hp": 30, "max_hp": 50, "status_effects": []}
    poisoned_enemy = {"name": "Cave Spider", "hp": 3, "max_hp": 20, "status_effects": ["Poisoned [2 turns]"]}
    
    session = {
        "nearby_enemies": [living_enemy, poisoned_enemy],
        "nearby_monsters": [living_enemy, poisoned_enemy]
    }
    
    hostiles = session.get("nearby_enemies") or []
    surviving_hostiles = []
    for monster in hostiles:
        if isinstance(monster, dict):
            if monster.get("status_effects"):
                tick_status_timers(monster)
            if monster.get("hp", 1) > 0:
                surviving_hostiles.append(monster)
        else:
            surviving_hostiles.append(monster)
    session["nearby_enemies"] = surviving_hostiles
    session["nearby_monsters"] = surviving_hostiles

    # Cave Spider had 3 HP and takes poison damage in tick_status_timers, dropping to 0 or below
    assert len(session["nearby_enemies"]) == 1
    assert session["nearby_enemies"][0]["name"] == "Orc Guard"
