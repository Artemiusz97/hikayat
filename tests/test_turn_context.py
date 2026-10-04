import pytest
from game_engine.turn_context import TurnContext
from collections import namedtuple

# Mock DB module to track call counts
class MockDB:
    def __init__(self):
        self.call_counts = {
            "get_contacts": 0,
            "get_session_party_npcs": 0,
            "get_session_quests": 0
        }
        self.contacts = [{"id": 1, "name": "Elena"}]
        self.party = [{"id": 2, "name": "Justin"}]
        self.quests = [{"id": 3, "title": "Bounty", "status": "active", "quest_type": "bounty"}]

    def get_contacts(self, session_id):
        self.call_counts["get_contacts"] += 1
        return self.contacts

    def get_session_party_npcs(self, session_id):
        self.call_counts["get_session_party_npcs"] += 1
        return self.party

    def get_session_quests(self, session_id):
        self.call_counts["get_session_quests"] += 1
        return self.quests

@pytest.fixture
def mock_db(monkeypatch):
    mock = MockDB()
    monkeypatch.setattr("game_engine.turn_context.db.get_contacts", mock.get_contacts)
    monkeypatch.setattr("game_engine.turn_context.db.get_session_party_npcs", mock.get_session_party_npcs)
    monkeypatch.setattr("game_engine.turn_context.db.get_session_quests", mock.get_session_quests)
    return mock

def test_turn_context_caches_db_calls(mock_db):
    session = {"id": 999}
    ctx = TurnContext(999, session)
    
    # Call multiple times
    _ = ctx.contacts
    _ = ctx.contacts
    _ = ctx.contacts
    
    assert mock_db.call_counts["get_contacts"] == 1
    
    _ = ctx.party_npcs
    _ = ctx.party_npcs
    
    assert mock_db.call_counts["get_session_party_npcs"] == 1

def test_turn_context_set_dialogue_partners():
    session = {}
    ctx = TurnContext(999, session)
    
    ctx.set_dialogue_partners(["Justin", "Elena", "Justin"])
    
    assert session["dialogue_partners"] == ["Justin", "Elena"]
    assert session["dialogue_partner"] == "Justin"
    
    ctx.set_dialogue_partners([])
    assert session["dialogue_partners"] == []
    assert session["dialogue_partner"] == ""

def test_turn_context_add_active_enemy():
    session = {"nearby_enemies": '[{"name": "Goblin"}]'}
    ctx = TurnContext(999, session)
    
    ctx.add_active_enemy({"name": "Orc"})
    
    assert isinstance(session["nearby_enemies"], list)
    assert len(session["nearby_enemies"]) == 2
    assert session["nearby_enemies"][1]["name"] == "Orc"
    
    ctx.clear_active_enemies()
    assert session["nearby_enemies"] == []
