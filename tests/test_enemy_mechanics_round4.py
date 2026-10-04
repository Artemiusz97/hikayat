import pytest
from mechanics.combat.core import precompute_combat_turn
from mechanics.combat.enemies import generate_scenario_enemy

def get_base_session_and_party():
    party = [
        ({
            "name": "Hero",
            "level": 10,
            "hp": 100,
            "max_hp": 100,
            "mp": 50,
            "max_mp": 50,
            "str_": 5, "agi": 5, "int_": 5, "luk": 5, "end_": 5, "per_": 5, "cha": 5,
            "status_effects": []
        }, [])
    ]
    session = {
        "id": 1,
        "scenario": "fantasy",
        "current_location": "Dungeon",
        "nearby_enemies": [],
        "nearby_monsters": [],
        "current_npcs": []
    }
    return session, party

def test_crowd_control_inaction():
    session, party = get_base_session_and_party()
    
    enemy = generate_scenario_enemy("fantasy", "Dungeon", 10, exact_tier=2)
    enemy["hp"] = 100
    enemy["max_hp"] = 100
    enemy["status_effects"] = ["Staggered [1 turn]"]
    enemy["stats"]["STR"] = 99  # Ensure it would deal damage if it attacks
    enemy["intent"] = "Preparing next strike"
    
    session["nearby_enemies"] = [enemy]
    
    # Hero takes a simple action that does nothing
    actions = [
        {"label": "Wait", "choice_type": "DEFENSIVE_GUARD", "stat": "NONE", "mp_spent": 0}
    ]
    
    result = precompute_combat_turn(session, party, actions)
    
    # Check that Hero took no damage
    hero = next((co for co in result.get("character_outcomes", []) if co["name"] == "Hero"), None)
    if hero:
        assert hero.get("hp_change", 0) == 0, "Staggered enemy should not deal damage"
    
    # Check combat log for stun message
    log = "\n".join(result["combat_log"])
    assert "cannot act this turn" in log.lower(), "Should log that enemy cannot act"
    
def test_item_boss_phase_2_intercept():
    session, party = get_base_session_and_party()
    
    # Create a Boss at 55% HP
    boss = generate_scenario_enemy("fantasy", "Dungeon", 10, exact_tier=5)
    boss["max_hp"] = 1000
    boss["hp"] = 550
    boss["name"] = "Big Boss"
    boss["affixes"] = []  # Clear random affixes like Vampiric which skew HP tests
    session["nearby_enemies"] = [boss]
    
    # Hero throws a bomb that deals exactly 200 damage (reducing HP to 350)
    # The intercept should heal 200 (20% of max_hp) and transition
    actions = [
        {
            "label": "Throw Bomb",
            "stat": "ITEM",
            "item": {"name": "Mega Bomb", "effect": "Deals 200 damage", "damage": 200}
        }
    ]
    
    result = precompute_combat_turn(session, party, actions)
    
    # Find boss in the updated enemies
    surviving = session["nearby_enemies"]
    assert len(surviving) == 1
    updated_boss = surviving[0]
    
    # Should have entered Phase 2 Enrage
    assert updated_boss.get("phase_2_triggered") is True
    assert any("Enraged" in str(s) for s in updated_boss.get("status_effects", []))
    
    # Boss HP should be 550 - 200 = 350 -> phase transition at < 500
    # max(500, 350) + 200 = 700
    assert updated_boss["hp"] == 700
    
def test_enemy_mp_depletion():
    session, party = get_base_session_and_party()
    
    enemy = generate_scenario_enemy("fantasy", "Dungeon", 10, custom_archetype="Caster", exact_tier=3)
    enemy["hp"] = 100
    enemy["max_hp"] = 100
    enemy["mp"] = 0  # No mana
    enemy["intent"] = "Channeling a massive spell"
    session["nearby_enemies"] = [enemy]
    
    actions = [
        {"label": "Defend", "stat": "END", "action_category": "guard"}
    ]
    
    result = precompute_combat_turn(session, party, actions)
    
    log = "\n".join(result["combat_log"])
    assert "out of mana" in log.lower(), "Enemy should fizzle spell when out of MP"
    
def test_low_morale_routing():
    session, party = get_base_session_and_party()
    
    # Create a minion Skirmisher at 10% HP
    enemy = generate_scenario_enemy("fantasy", "Dungeon", 1, custom_archetype="Skirmisher", exact_tier=1)
    enemy["max_hp"] = 100
    enemy["hp"] = 10
    # Force low morale stats so it fails check
    enemy["stats"]["END"] = -100 
    enemy["stats"]["CHA"] = -100
    
    session["nearby_enemies"] = [enemy]
    
    actions = [
        {"label": "Defend", "stat": "END", "action_category": "guard"}
    ]
    
    result = precompute_combat_turn(session, party, actions)
    
    # Combat should resolve with enemy yielding
    log = "\n".join(result["combat_log"])
    assert "morale broke" in log.lower(), "Skirmisher should flee due to low HP and low morale"
    
    # Enemy should not be in nearby_enemies anymore because it fled and yielded
    surviving = session["nearby_enemies"]
    assert len(surviving) == 0, "Yielded enemy should be removed from combat"
