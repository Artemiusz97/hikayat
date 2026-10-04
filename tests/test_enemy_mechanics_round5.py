import pytest
from mechanics.combat.core import precompute_combat_turn
from mechanics.combat.enemies import generate_scenario_enemy
from mechanics.social.attributes import calculate_combat_attributes

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
            "status_effects": [],
            "base_dt": 0
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

def test_fleeing_enemy_loot_exploit():
    session, party = get_base_session_and_party()
    
    # Create an enemy that fled
    enemy = generate_scenario_enemy("fantasy", "Dungeon", 1, custom_name="Cowardly Goblin")
    # Setting HP to 0 and adding to yielded enemies was the scenario that caused the bug
    enemy["hp"] = 0
    enemy["max_hp"] = 100
    
    # We simulate the state just before Phase 4 reward calculation
    # by letting the turn run but injecting the yielded state early or simulating a flee.
    # Wait, we can just trigger a flee.
    enemy["tier_rank"] = 1
    enemy["archetype"] = "Coward"
    enemy["status_effects"] = ["Demoralized [2 turns]"]
    enemy["stats"] = {"END": -100, "CHA": -100} # force flee
    
    session["nearby_enemies"] = [enemy]
    actions = [{"label": "Wait", "stat": "NONE"}]
    
    result = precompute_combat_turn(session, party, actions)
    
    # Validate the enemy didn't grant XP and didn't generate loot
    assert result.get("xp_gained", 0) == 0, "Fled enemies should not grant XP"
    
    # Check post-combat choices
    choices = result.get("choices", [])
    has_loot_choice = any("loot" in str(c.get("label", "")).lower() for c in choices)
    assert not has_loot_choice, "Fled enemies should not generate a loot choice"


def test_swarm_intent_mechanics():
    session, party = get_base_session_and_party()
    
    # Test "Multiplying rapidly"
    swarm1 = generate_scenario_enemy("fantasy", "Dungeon", 1, custom_archetype="Void Swarm")
    swarm1["intent"] = "Multiplying rapidly"
    swarm1["hp"] = 50
    swarm1["max_hp"] = 100
    session["nearby_enemies"] = [swarm1]
    
    actions = [{"label": "Defend", "stat": "END", "action_category": "guard"}]
    result = precompute_combat_turn(session, party, actions)
    
    # Should have healed 20% of max_hp (20)
    surviving = session["nearby_enemies"]
    assert len(surviving) == 1
    assert surviving[0]["hp"] >= 70, "Swarm should heal 20 HP when multiplying"
    
    log = "\n".join(result["combat_log"])
    assert "multiplies rapidly" in log.lower()

    # Test "Preparing to swarm"
    swarm2 = generate_scenario_enemy("fantasy", "Dungeon", 1, custom_archetype="Void Swarm")
    swarm2["intent"] = "Preparing to swarm"
    swarm2["hp"] = 50
    swarm2["max_hp"] = 100
    session["nearby_enemies"] = [swarm2]
    
    actions = [{"label": "Defend", "stat": "END", "action_category": "guard"}]
    result = precompute_combat_turn(session, party, actions)
    
    # Should inflict Swarmed debuff on Hero
    hero = party[0][0]
    assert any("Swarmed" in str(s) for s in hero.get("status_effects", [])), "Swarm should inflict Swarmed status"


def test_affix_passives():
    session, party = get_base_session_and_party()
    
    # Vampiric and Corrosive
    enemy1 = generate_scenario_enemy("fantasy", "Dungeon", 10)
    enemy1["affixes"] = ["Vampiric", "Corrosive"]
    enemy1["hp"] = 50
    enemy1["max_hp"] = 100
    enemy1["stats"]["STR"] = 99  # Ensure it hits and deals damage
    enemy1["intent"] = "Preparing next strike"
    session["nearby_enemies"] = [enemy1]
    
    actions = [{"label": "Defend", "stat": "END", "action_category": "guard"}]
    result = precompute_combat_turn(session, party, actions)
    
    # Check Vampiric heal
    surviving = session["nearby_enemies"]
    assert surviving[0]["hp"] > 50, "Vampiric enemy should heal when dealing damage"
    
    # Check Corrosive debuff on Hero
    hero = party[0][0]
    assert any("Corroded Armor" in str(s) for s in hero.get("status_effects", [])), "Corrosive enemy should inflict Corroded Armor"
    
    # Volatile Death
    enemy2 = generate_scenario_enemy("fantasy", "Dungeon", 10)
    enemy2["affixes"] = ["Volatile"]
    enemy2["hp"] = 10  # low HP to kill
    session["nearby_enemies"] = [enemy2]
    actions = [
        {"label": "Punch", "stat": "STR", "item_consumed": False, "weapon_name": "Fists"}
    ]
    # Make hero one-shot it
    hero["str_"] = 999
    
    result = precompute_combat_turn(session, party, actions)
    log = "\n".join(result["combat_log"])
    
    assert "violently detonated" in log.lower(), "Volatile enemy should explode on death"
    
def test_miss_vs_absorbed_log(mocker):
    session, party = get_base_session_and_party()
    hero = party[0][0]
    hero["user_id"] = "mock_user"
    
    # Equip armor with high DT
    shield = {"name": "Aegis", "item_type": "Armor", "slot": "Armor", "base_dt": 100, "equipped": True}
    mocker.patch("mechanics.combat.core.db.get_equipment", return_value={"Armor": shield})
    
    # Force the block check (which is block_chance = 30) to succeed, but don't force a crit (e.g. 20)
    mocker.patch("mechanics.combat.core.random.randint", return_value=20)
    mocker.patch("mechanics.combat.formulas.random.randint", return_value=20)
    party[0] = (hero, [shield])
    
    enemy = generate_scenario_enemy("fantasy", "Dungeon", 1, custom_archetype="Peasant")
    enemy["stats"] = {"STR": 1, "AGI": 1, "INT": 1} # very low damage
    enemy["level"] = 1
    enemy["affixes"] = []
    enemy["intent"] = "Preparing next strike"
    session["nearby_enemies"] = [enemy]
    
    actions = [{"label": "Defend", "stat": "END", "action_category": "guard"}]
    result = precompute_combat_turn(session, party, actions)
    
    log = "\n".join(result["combat_log"])
    assert "completely absorbed by their armor" in log.lower() or "blocked" in log.lower()
    assert "attack missed" not in log.lower()
