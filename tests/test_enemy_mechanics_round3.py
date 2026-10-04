import pytest
from unittest.mock import MagicMock, patch

from mechanics.combat.core import precompute_combat_turn, reconcile_combat_results, _get_entity_stat
from mechanics.combat.formulas import calculate_tactical_damage
from mechanics.narrative.choice_generator import generate_categorized_combat_actions
from cogs.adventure.views import ChoiceView


def test_get_entity_stat_helper():
    """Verify _get_entity_stat extracts stats correctly from players and NPC companions."""
    player = {"user_id": 123, "name": "Hero", "str_": 9, "luk": 4, "agi_": 7}
    npc = {"name": "Valerie", "stats": {"STR": 3, "LUK": 8, "AGI": 5}}

    assert _get_entity_stat(player, "STR") == 9
    assert _get_entity_stat(player, "LUK") == 4
    assert _get_entity_stat(player, "AGI") == 7

    assert _get_entity_stat(npc, "STR") == 3
    assert _get_entity_stat(npc, "LUK") == 8
    assert _get_entity_stat(npc, "AGI") == 5


def test_archetype_targeting_brute_and_caster():
    """Verify Brute targets highest STR ally and Caster targets lowest LUK ally."""
    # Player 1: Tank (STR 10, LUK 6)
    # Companion 2: Unlucky Mage (STR 2, LUK 1)
    player = {"user_id": 101, "name": "Gorg Tank", "hp": 100, "max_hp": 100, "str_": 10, "luk": 6}
    companion = {"name": "Lydia Caster", "hp": 50, "max_hp": 50, "stats": {"STR": 2, "LUK": 1, "INT": 8, "END": 3}}

    brute = {
        "name": "Hill Giant",
        "archetype": "Brute",
        "level": 3,
        "hp": 80,
        "max_hp": 80,
        "stats": {"STR": 8, "END": 7, "AGI": 2, "INT": 2, "PER": 3, "CHA": 1, "LUK": 2}
    }

    session = {
        "scenario": "fantasy",
        "nearby_enemies": [brute],
        "current_npcs": [companion],
        "turn_order": [101],
        "combat_turn": 1
    }
    party = [(player, [])]
    action = {"choice_type": "DEFENSIVE_GUARD", "label": "Guard", "tier": "success"}

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    # Brute should target Gorg Tank (STR 10 > STR 2)
    assert any("Hill Giant" in log and "Gorg Tank" in log for log in out["combat_log"])

    # Now test Caster targeting: should target Lydia Caster (LUK 1 < LUK 6)
    caster = {
        "name": "Eldritch Sorcerer",
        "archetype": "Caster",
        "level": 3,
        "hp": 60,
        "max_hp": 60,
        "stats": {"INT": 8, "PER": 6, "STR": 2, "END": 3, "AGI": 4, "CHA": 2, "LUK": 3}
    }
    session["nearby_enemies"] = [caster]
    player["hp"] = 100
    companion["hp"] = 50

    with patch("db.get_equipment", return_value={}):
        out_caster = precompute_combat_turn(session, party, [action])

    assert any("Eldritch Sorcerer" in log and "Lydia Caster" in log for log in out_caster["combat_log"])


def test_enemy_atk_damage_scaling_and_demoralized():
    """Verify higher enemy ATK increases incoming damage and Demoralized debuff reduces it."""
    defender_attrs = {"base_dt": 0, "type_dt": {}, "gear_dr": {}}
    target_max_hp = 100
    armor_meta = {"base_dt": 0, "type_dt": {}}
    weapon_meta = {"damage_types": {"physical": 1.0}}

    # Standard ATK = 20
    atk_std = {"atk": 20, "matk": 20}
    # Low ATK / Demoralized = 10
    atk_low = {"atk": 10, "matk": 10}
    # High ATK = 30
    atk_high = {"atk": 30, "matk": 30}

    with patch("random.uniform", return_value=0.15):
        res_std = calculate_tactical_damage(
            attacker_attrs=atk_std, defender_attrs=defender_attrs,
            weapon_meta=weapon_meta, armor_meta=armor_meta, tier="success",
            attacker_level=1, defender_max_hp=target_max_hp, is_enemy_attacker=True
        )
        res_low = calculate_tactical_damage(
            attacker_attrs=atk_low, defender_attrs=defender_attrs,
            weapon_meta=weapon_meta, armor_meta=armor_meta, tier="success",
            attacker_level=1, defender_max_hp=target_max_hp, is_enemy_attacker=True
        )
        res_high = calculate_tactical_damage(
            attacker_attrs=atk_high, defender_attrs=defender_attrs,
            weapon_meta=weapon_meta, armor_meta=armor_meta, tier="success",
            attacker_level=1, defender_max_hp=target_max_hp, is_enemy_attacker=True
        )

    # Low ATK (or Demoralized) must deal strictly less damage than Standard ATK, and High ATK must deal more
    assert res_low["damage"] < res_std["damage"]
    assert res_std["damage"] < res_high["damage"]


def test_telegraphed_intent_execution_heavy_swing():
    """Verify that an enemy telegraphing a heavy swing deals +35% damage and staggers an unguarded player."""
    boss = {
        "name": "Iron Golem",
        "archetype": "Brute",
        "level": 5,
        "hp": 150,
        "max_hp": 150,
        "tier_rank": 5,
        "intent": "Winding up a heavy swing",
        "stats": {"STR": 10, "END": 10, "AGI": 2, "INT": 2, "PER": 3, "CHA": 1, "LUK": 2}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [boss],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 5, "luk": 5}
    party = [(player, [])]

    # Player takes a regular attack action without defensive guard
    action = {"choice_type": "MELEE_ATTACK", "label": "Slash", "tier": "success"}

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    # Should mention telegraphed heavy strike in log
    assert any("Telegraphed Heavy Strike" in log for log in out["combat_log"])
    # Player should be inflicted with Staggered
    assert any("Staggered" in s for s in player.get("status_effects", []))


def test_telegraphed_intent_defensive_posture():
    """Verify that an enemy telegraphing a defensive posture gains DT and Block."""
    guardian = {
        "name": "Shield Warden",
        "archetype": "Guardian",
        "level": 3,
        "hp": 80,
        "max_hp": 80,
        "tier_rank": 3,
        "intent": "Assuming a defensive posture",
        "stats": {"STR": 5, "END": 8, "AGI": 2, "INT": 2, "PER": 4, "CHA": 2, "LUK": 2}
    }
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [guardian],
        "turn_order": [123],
        "combat_turn": 1
    }
    player = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 5, "luk": 5}
    party = [(player, [])]
    action = {"choice_type": "MELEE_ATTACK", "label": "Attack", "tier": "success"}

    with patch("db.get_equipment", return_value={}):
        out = precompute_combat_turn(session, party, [action])

    assert any("holds their defensive posture" in log for log in out["combat_log"])


def test_multi_enemy_counter_attack_attribution():
    """Verify reconcile_combat_results formats notice with all contributing attackers."""
    session = {
        "nearby_enemies": [{"name": "Goblin 1", "hp": 30}, {"name": "Goblin 2", "hp": 30}],
        "current_npcs": []
    }

    # Case 1: Single attacker
    precomputed_single = {
        "acting_char_name": "Hero",
        "player_damage_taken": 14,
        "attackers_against_player": ["Goblin 1"]
    }
    res_single = reconcile_combat_results(session, {}, precomputed_single)
    assert "Goblin 1 Counter-Attack:" in res_single["_enemy_attack_notice"]
    assert "14 damage" in res_single["_enemy_attack_notice"]

    # Case 2: Multiple attackers
    precomputed_multi = {
        "acting_char_name": "Hero",
        "player_damage_taken": 28,
        "attackers_against_player": ["Goblin 1", "Goblin 2"]
    }
    res_multi = reconcile_combat_results(session, {}, precomputed_multi)
    assert "Enemy Counter-Attacks (Goblin 1, Goblin 2):" in res_multi["_enemy_attack_notice"]
    assert "28 total damage" in res_multi["_enemy_attack_notice"]


def test_multi_enemy_target_switcher_ui():
    """Verify ChoiceView tracks active target and updates categorized actions."""
    cog = MagicMock()
    session = {
        "id": 999,
        "scenario": "fantasy",
        "nearby_enemies": [
            {"name": "Minion Dog", "hp": 20, "max_hp": 20, "stats": {"STR": 2, "AGI": 4, "END": 2}},
            {"name": "Orc Captain", "hp": 80, "max_hp": 80, "stats": {"STR": 8, "AGI": 3, "END": 7}}
        ],
        "turn_order": [123],
        "combat_turn": 1
    }
    actor_char = {"user_id": 123, "name": "Hero", "hp": 100, "max_hp": 100, "str_": 5}

    with patch("db.get_session", return_value=session), \
         patch("db.get_inventory", return_value=[]), \
         patch("db.get_settings", return_value={}):
        view = ChoiceView(cog, 999, 123, choices=[], actor_char=actor_char)

    # Initial target should be Minion Dog (index 0)
    assert view.target_idx == 0
    assert view.hostiles[0]["name"] == "Minion Dog"
    assert view.categorized["attacks"][0]["target_entity"] == "Minion Dog"

    # Cycle to target index 1 (Orc Captain)
    view.target_idx = 1
    monster = view.hostiles[view.target_idx]
    view.categorized = generate_categorized_combat_actions([(actor_char, [])], monster, "area", "fantasy")

    assert view.categorized["attacks"][0]["target_entity"] == "Orc Captain"
