import pytest
import copy
from mechanics.combat.core import precompute_combat_turn, reconcile_combat_results
from game_engine.turn import resolve_turn
import asyncio

# --- MOCKS ---

@pytest.fixture
def mock_db(mocker):
    mocker.patch("db.get_equipment", return_value={"Weapon": {"name": "Test Sword", "attack": 10}})
    mocker.patch("db.set_status_effects", return_value=None)
    mocker.patch("db.get_session_party_npcs", return_value=[])
    mocker.patch("db.set_session_party_npcs", return_value=None)
    mocker.patch("game_engine.turn.game_engine.call_llm_json", new_callable=mocker.AsyncMock, return_value={"character_outcomes": [{"name": "TestHero", "hp_change": 0, "mp_change": 0, "xp_change": 0, "gold_change": 0}]})
    return mocker

@pytest.fixture
def session_fixture():
    return {
        "id": 1,
        "scenario": "cyberpunk",
        "current_location": "Alleyway",
        "nearby_enemies": [],
        "history": []
    }

@pytest.fixture
def party_fixture():
    return [({
        "name": "TestHero",
        "user_id": 1,
        "hp": 100,
        "max_hp": 100,
        "stats": {"STR": 5, "AGI": 5, "END": 5, "INT": 5, "PER": 5},
        "level": 1
    }, [])]

# --- TESTS ---

def test_flee_vs_yield_separation(session_fixture, party_fixture, mock_db):
    """Test that fleeing enemies populate fled_enemies instead of yielded_enemies, preventing sparring results."""
    enemy = {
        "name": "Fleeing Bandit",
        "hp": 20, "max_hp": 20,
        "stats": {"END": -20, "CHA": -20},
        "status_effects": ["Demoralized [2 turns]"],
        "tier_rank": 1
    }
    session = copy.deepcopy(session_fixture)
    session["nearby_enemies"] = [enemy]
    
    actions = [{"char": party_fixture[0][0], "label": "Attack", "tier": "success", "damage": 5}]
    
    precomputed = precompute_combat_turn(session, party_fixture, actions)
    
    assert "Fleeing Bandit" in precomputed.get("fled_enemies", [])
    assert "Fleeing Bandit" not in precomputed.get("yielded_enemies", [])
    assert "Fleeing Bandit" not in precomputed.get("dead_enemies", [])
    assert any("Fled" in line for line in precomputed["directive"].split("\n"))

def test_loot_choice_only_on_dead(session_fixture, party_fixture, mock_db):
    """Test that reconcile_combat_results only injects the FREE Loot choice if there are dead enemies."""
    session = copy.deepcopy(session_fixture)
    session["nearby_enemies"] = []
    llm_outcome = {
        "choices": [{"label": "Talk", "stat": "CHA"}],
        "next_choices": [{"label": "Talk", "stat": "CHA"}],
    }
    precomputed = {"fled_enemies": ["Bandit"], "dead_enemies": []}
    res = reconcile_combat_results(session, llm_outcome, precomputed)
    assert not any("loot" in str(c.get("label", "")).lower() for c in res.get("choices", []))
    assert "Encounter Survived" in res.get("_combat_resolved_notice", "")
    
    llm_outcome_2 = copy.deepcopy(llm_outcome)
    precomputed_2 = {"dead_enemies": ["Bandit"]}
    res_2 = reconcile_combat_results(session, llm_outcome_2, precomputed_2)
    assert any("loot" in str(c.get("label", "")).lower() for c in res_2.get("choices", []))
    assert "Victory" in res_2.get("_combat_resolved_notice", "")

def test_status_effects_and_elite_affixes(session_fixture, party_fixture, mock_db):
    """Test Phase 3 modifier logic for Enraged, Weakened, Overclocked, and Phasing."""
    enemy = {
        "name": "Boss",
        "hp": 100, "max_hp": 100,
        "stats": {"STR": 10}, 
        "intent": "Attacking Hero!",
        "status_effects": ["Enraged [2 turns]", "Weakened [1 turn]"],
        "affixes": ["Overclocked", "Phasing"],
        "archetype": "Brute"
    }
    session = copy.deepcopy(session_fixture)
    session["nearby_enemies"] = [enemy]
    actions = [{"char": party_fixture[0][0], "label": "Wait", "tier": "success", "damage": 0}]
    precomputed = precompute_combat_turn(session, party_fixture, actions)
    log = "\n".join(precomputed["combat_log"])
    assert "attacked **TestHero**" in log

@pytest.mark.asyncio
async def test_dot_kill_deletion_bug(session_fixture, party_fixture, mock_db):
    """Test that if an enemy drops to 0 HP due to a DoT at the end of the turn, it grants XP and Gold."""
    enemy = {
        "name": "Poisoned Minion",
        "hp": 2, "max_hp": 20,
        "stats": {"END": 10},
        "status_effects": ["Poisoned [2 turns]"],
        "tier_rank": 1,
        "xp_multiplier": 1.0
    }
    session = copy.deepcopy(session_fixture)
    session["nearby_enemies"] = [enemy]
    class MockCheck:
        tier = "success"
        chance = 100
    actions = [{"char": party_fixture[0][0], "label": "Wait", "choice_type": "DEFENSIVE_GUARD", "tier": "success", "mp_spent": 0, "check": MockCheck()}]
    result = await resolve_turn(session, party_fixture, actions)
    
    assert "Poisoned Minion" in result.get("dead_enemies", [])
    assert result.get("nearby_enemies", []) == []
    outcomes = result.get("character_outcomes", [])
    hero_outcome = next((o for o in outcomes if o.get("name") == "TestHero"), None)
    assert hero_outcome is not None
    assert hero_outcome.get("xp_change", 0) >= 40
    assert hero_outcome.get("gold_change", 0) >= 15
    assert "succumbed to their wounds" in result.get("_combat_resolved_notice", "")

