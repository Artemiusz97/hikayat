from mechanics.combat import is_in_combat, reconcile_combat_results, get_combat_prompt_and_schema
from skill_check import CheckResult

def test_is_in_combat():
    # True case: allowed mechanic and monsters present
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [{"name": "Goblin", "hp": 100}]
    }
    # Mocking scenario_data.is_mechanic_enabled is omitted here for brevity; assuming fantasy has it enabled since we added it.
    
    assert is_in_combat(session) == True
    
    # False case: no monsters
    session["nearby_enemies"] = []
    assert is_in_combat(session) == False

def test_reconcile_combat_results_victory():
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [{"name": "Goblin", "hp": 30}]
    }
    
    actions = [
        {"char": {"name": "Hero"}, "tier": "crit_success", "check": CheckResult(50, 99.0, "crit_success", "Critical Success", True)}
    ]
    
    # Hero does 45 dmg, which kills the Goblin (30 hp)
    outcome = reconcile_combat_results(session, {}, actions)
    
    assert len(session["nearby_enemies"]) == 0
    assert "_combat_resolved_notice" in outcome
    assert "Victory!" in outcome["_combat_resolved_notice"]
    assert "next_choices" in outcome
    assert len(outcome["next_choices"]) == 4

def test_reconcile_combat_results_damage_taken():
    session = {
        "scenario": "fantasy",
        "nearby_enemies": [{"name": "Dragon", "hp": 1000}]
    }
    
    actions = [
        {"char": {"name": "Hero"}, "tier": "crit_fail", "check": CheckResult(10, 1.0, "crit_fail", "Critical Failure", False)}
    ]
    
    # Hero takes 25 damage, dragon takes 0
    outcome = reconcile_combat_results(session, {}, actions)
    
    assert session["nearby_enemies"][0]["hp"] == 1000
    assert len(outcome["character_outcomes"]) == 1
    assert outcome["character_outcomes"][0]["hp_change"] == -25
