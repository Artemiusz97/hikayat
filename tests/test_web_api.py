"""
Unit & Integration Tests for Hikayat Web API and WebSockets (server.py).

Tests:
1. Auth & Meta: Guest auth, scenarios, class templates.
2. Character Lifecycle: Creation, point allocation validation (>12 points rejected), sheet inspection.
3. Adventure Lifecycle:
   - /api/adventure/start: verifies session initialization and user settings forwarding (choices_style, result_display).
   - /api/adventure/action: executes preset choice & custom actions; validates MP checks.
   - Action serialization: verifies CheckResult dataclass does not break WebSocket or REST responses.
4. Settings & Debug endpoints.
5. WebSocket session channels: Handshake, Ping/Pong, Chat broadcasting.
"""
import asyncio
import httpx
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import db
import server
from skill_check import CheckResult
from models.llm_schemas import TurnOutcome

client = TestClient(server.app)


@pytest.fixture
def web_user_and_character():
    """Creates a test user and baseline character in SQLite."""
    user_id = 99101
    with db.get_conn() as conn:
        conn.execute("DELETE FROM characters WHERE user_id=?", (user_id,))
    db.create_character(
        user_id=user_id,
        name="WebHero",
        char_class="Warrior",
        stats={"STR": 2, "PER": 1, "END": 2, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1},
        scenario="fantasy"
    )
    return user_id


@pytest.mark.api
def test_auth_and_metadata_endpoints():
    # 1. Guest Auth
    res = client.post("/api/auth/guest", json={"guest_name": "TavernBrawler"})
    assert res.status_code == 200
    data = res.json()
    assert data["is_guest"] is True
    assert data["display_name"] == "TavernBrawler"
    assert isinstance(data["user_id"], int)

    # 2. Scenarios
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    assert "fantasy" in res.json().get("scenarios", {})

    # 3. Class Templates
    res = client.get("/api/class-templates?scenario=fantasy")
    assert res.status_code == 200
    assert "classes" in res.json()
    assert "starting_weapons" in res.json()


@pytest.mark.api
def test_character_creation_and_stat_allocation():
    user_id = 99102

    # 1. Create character exceeding stat points (> 12 total points) -> 400 Bad Request
    invalid_payload = {
        "user_id": user_id,
        "name": "Overpowered",
        "char_class": "Paladin",
        "str": 10, "per": 5, "end": 5, "cha": 5, "int": 5, "agi": 5, "luk": 5
    }
    res = client.post("/api/character/create", json=invalid_payload)
    assert res.status_code == 400
    assert "Stat allocation exceeds maximum" in res.json()["detail"]

    # 2. Valid character creation (7 baseline + 3 points = 10 total)
    valid_payload = {
        "user_id": user_id,
        "name": "BalancedMage",
        "char_class": "Mage",
        "starting_weapon": "Oak Staff",
        "str": 1, "per": 1, "end": 1, "cha": 1, "int": 4, "agi": 1, "luk": 1
    }
    res = client.post("/api/character/create", json=valid_payload)
    assert res.status_code == 200
    char_data = res.json()["character"]
    assert char_data["name"] == "BalancedMage"
    assert char_data["int_"] == 4

    # 3. Fetch character sheet
    res = client.get(f"/api/character/{user_id}")
    assert res.status_code == 200
    sheet = res.json()
    assert sheet["character"]["name"] == "BalancedMage"
    assert "combat_attributes" in sheet
    assert "inventory_capacity" in sheet

    # 4. Inventory inspection
    res = client.get(f"/api/inventory/{user_id}")
    assert res.status_code == 200
    inv = res.json()
    assert any(item["name"] == "Oak Staff" for item in inv["items"])


@pytest.mark.api
def test_adventure_start_and_settings_preservation(web_user_and_character):
    user_id = web_user_and_character

    # Configure custom user preferences
    db.save_user_settings(
        user_id=user_id,
        verbosity="vivid",
        dialogue_mode="verbose",
        image_gen_enabled=0,
        choices_style="dropdown",
        result_display="brief"
    )

    mock_scene = {
        "scene_title": "The Whispering Glen",
        "narrative": "A gentle mist rolls across the quiet glade.",
        "choices": [
            {"label": "Examine the glowing rune", "stat": "INT", "requirement": 6, "mp_cost": 0},
            {"label": "Rest by the stream", "stat": "FREE", "requirement": 0, "mp_cost": 0}
        ],
        "location": "Whispering Glen",
        "nearby_enemies": [],
        "npcs_present": []
    }

    with patch("game_engine.generate_opening_scene", new_callable=AsyncMock) as mock_gen, \
         patch("game_engine.apply_quest_update"):

        mock_gen.return_value = mock_scene

        res = client.post("/api/adventure/start", json={
            "user_id": user_id,
            "scenario": "fantasy",
            "mode": "solo"
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        session = data["session"]

        # Regression Guard for Bug 2: verify user preferences were forwarded to session
        assert session["choices_style"] == "dropdown"
        assert session["result_display"] == "brief"
        assert session["verbosity"] == "vivid"

        # Verify odds enrichment
        choices = session["choices"]
        assert len(choices) == 2
        assert "success_pct" in choices[0]
        assert "stat_val" in choices[0]


@pytest.mark.api
def test_adventure_action_execution_and_serialization(web_user_and_character):
    user_id = web_user_and_character
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])

    db.save_session_scene(
        session_id=session_id,
        scene_title="Cave Entrance",
        narrative="Darkness looms ahead.",
        choices=[{"label": "Light a torch", "stat": "FREE", "requirement": 0, "mp_cost": 0}],
        history=[]
    )

    mock_outcome = {
        "scene_title": "Torchlit Cavern",
        "outcome_narrative": "The torch blazes to life, revealing ancient stalactites.",
        "next_narrative": "You hear faint dripping water deeper inside.",
        "next_choices": [{"label": "Venture deeper", "stat": "PER", "requirement": 5}],
        "character_outcomes": []
    }

    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={user_id: []}), \
         patch("game_engine.apply_quest_update"):

        mock_resolve.return_value = mock_outcome

        # Execute preset choice (choice_index = 0)
        res = client.post("/api/adventure/action", json={
            "session_id": session_id,
            "user_id": user_id,
            "choice_index": 0
        })

        # Regression Guard for Bug 1: Must be 200 OK and serialize action['check'] safely
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["action"]["label"] == "Light a torch"
        assert isinstance(data["action"]["check"], dict)
        assert data["action"]["check"]["tier"] == "success"


@pytest.mark.api
def test_settings_and_debug_endpoints(web_user_and_character):
    user_id = web_user_and_character

    # 1. Update settings
    res = client.post(f"/api/settings/{user_id}", json={
        "user_id": user_id,
        "verbosity": "concise",
        "dialogue_mode": "terse",
        "image_gen_enabled": 1,
        "choices_style": "dropdown",
        "result_display": "brief"
    })
    assert res.status_code == 200
    saved = res.json()["settings"]
    assert saved["verbosity"] == "concise"

    # 1b. Update settings when user has an active session
    sess_id = db.create_session(user_id, "solo", 1, "vivid", "balanced", False)
    res_sess = client.post(f"/api/settings/{user_id}", json={
        "user_id": user_id,
        "image_gen_enabled": 1,
        "show_percentages": 1,
    })
    assert res_sess.status_code == 200
    sess = db.get_session(sess_id)
    assert sess["image_gen_enabled"] == 1
    assert sess["show_percentages"] == 1

    # 2. Debug settings & HP manipulation
    res = client.post(f"/api/debug/{user_id}", json={
        "debug_stat_mode": "on",
        "debug_check_mode": "always_crit",
        "action": "hp_to_1"
    })
    assert res.status_code == 200
    dbg = res.json()
    assert dbg["debug_check_mode"] == "always_crit"
    assert dbg["hp"] == 1


@pytest.mark.api
def test_websocket_connection_and_chat(web_user_and_character):
    user_id = web_user_and_character
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])

    with client.websocket_connect(f"/ws/session/{session_id}?user_id={user_id}") as ws:
        # Initial presence broadcast upon connecting
        initial_msg = ws.receive_json()
        assert initial_msg["type"] == "PRESENCE_UPDATE"
        assert initial_msg["session_id"] == session_id

        # Send PING
        ws.send_json({"type": "PING"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "PONG"

        # Send CHAT
        ws.send_json({"type": "CHAT", "sender": "Hero", "message": "Ready to roll!"})
        chat_msg = ws.receive_json()
        assert chat_msg["type"] == "CHAT_MESSAGE"
        assert chat_msg["message"] == "Ready to roll!"


def test_websocket_probe_on_static_route_closes_gracefully():
    """Verify that automated websocket probes to static/root paths are rejected cleanly without 500 AssertionError."""
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises((WebSocketDisconnect, Exception)) as excinfo:
        with client.websocket_connect("/"):
            pass
    # Must not raise an unhandled AssertionError
    assert not isinstance(excinfo.value, AssertionError)


@pytest.mark.api
@pytest.mark.asyncio
async def test_concurrent_actions_trigger_409_conflict(web_user_and_character):
    """
    Stress test verifying that simultaneous action requests for the same session
    are gated by `get_session_lock` so that duplicate turns are never executed.
    One request must succeed (200 OK) and colliding requests must receive 409 Conflict.
    """
    user_id = web_user_and_character
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])

    db.save_session_scene(
        session_id=session_id,
        scene_title="Crossroads",
        narrative="The path splits in two.",
        choices=[{"label": "Take the left path", "stat": "FREE", "requirement": 0, "mp_cost": 0}],
        history=[]
    )

    # Simulate an async turn resolution that takes 150ms
    async def slow_turn_resolution(*args, **kwargs):
        await asyncio.sleep(0.15)
        return {
            "scene_title": "Left Path",
            "outcome_narrative": "You follow the left path quietly.",
            "next_narrative": "A shimmering pond appears ahead.",
            "choices": [],
            "character_outcomes": []
        }

    with patch("game_engine.resolve_turn", side_effect=slow_turn_resolution), \
         patch("game_engine.apply_outcome", return_value={user_id: []}), \
         patch("game_engine.apply_quest_update"):

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as ac:
            action_payload = {
                "session_id": session_id,
                "user_id": user_id,
                "choice_index": 0
            }

            # Fire 2 collision requests simultaneously
            req1 = ac.post("/api/adventure/action", json=action_payload)
            req2 = ac.post("/api/adventure/action", json=action_payload)
            res1, res2 = await asyncio.gather(req1, req2)

            status_codes = {res1.status_code, res2.status_code}
            assert status_codes == {200, 409}, f"Expected {200, 409} but got {[res1.status_code, res2.status_code]}"

            # Verify the 409 response has the explicit concurrency conflict message
            conflict_res = res1 if res1.status_code == 409 else res2
            assert "Turn resolution currently in progress for this session" in conflict_res.json()["detail"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_concurrent_adventure_start_triggers_409_conflict(web_user_and_character):
    """
    Stress test verifying that simultaneous adventure start requests for the same user
    are gated by `get_user_lock`. One succeeds (200) and colliding requests receive 409 Conflict.
    """
    user_id = web_user_and_character

    async def slow_scene_gen(*args, **kwargs):
        await asyncio.sleep(0.15)
        return {
            "scene_title": "Beginning",
            "narrative": "The dawn breaks.",
            "choices": [],
            "location": "Camp",
            "nearby_enemies": [],
            "npcs_present": []
        }

    with patch("game_engine.generate_opening_scene", side_effect=slow_scene_gen), \
         patch("game_engine.apply_quest_update"):

        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as ac:
            start_payload = {
                "user_id": user_id,
                "scenario": "fantasy",
                "mode": "solo"
            }

            # Fire 2 collision requests simultaneously
            req1 = ac.post("/api/adventure/start", json=start_payload)
            req2 = ac.post("/api/adventure/start", json=start_payload)
            res1, res2 = await asyncio.gather(req1, req2)

            status_codes = {res1.status_code, res2.status_code}
            assert status_codes == {200, 409}, f"Expected {200, 409} but got {[res1.status_code, res2.status_code]}"

            conflict_res = res1 if res1.status_code == 409 else res2
            assert "Adventure start already in progress for this user" in conflict_res.json()["detail"]


@pytest.mark.api
def test_inventory_and_party_endpoints():
    """
    Verifies Phase 3A API endpoints:
    1. /api/inventory/{user_id} returns items, capacity, used_slots, gold, and equipment.
    2. /api/inventory/equip, /api/inventory/unequip, and /api/inventory/drop.
    3. /api/adventure/active-session/{user_id} enriches party_members.
    """
    user_id = 99105
    db.delete_character(user_id)
    db.create_character(
        user_id=user_id,
        name="InventoryHero",
        char_class="Warrior",
        stats={"STR": 2, "PER": 1, "END": 2, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1},
        scenario="fantasy"
    )

    # 1. Fetch inventory
    res = client.get(f"/api/inventory/{user_id}")
    assert res.status_code == 200
    inv = res.json()
    assert "used_slots" in inv
    assert "capacity" in inv
    assert "gold" in inv
    assert "equipment" in inv

    # 2. Add an item, equip it, unequip it, drop it
    item_id = db.add_item(user_id, "Iron Buckler", "Shield", "Defense +2", slot_cost=1)
    assert item_id is not None

    # Equip into Shield slot
    eq_res = client.post("/api/inventory/equip", json={
        "user_id": user_id,
        "item_id": item_id,
        "slot": "Shield"
    })
    assert eq_res.status_code == 200
    assert eq_res.json()["success"] is True

    # Unequip Shield slot
    uneq_res = client.post("/api/inventory/unequip", json={
        "user_id": user_id,
        "slot": "Shield"
    })
    assert uneq_res.status_code == 200
    assert uneq_res.json()["success"] is True

    # Drop item
    drop_res = client.post("/api/inventory/drop", json={
        "user_id": user_id,
        "item_id": item_id
    })
    assert drop_res.status_code == 200
    assert drop_res.json()["success"] is True

    # 3. Test active session party enrichment
    mock_scene = {
        "scene_title": "Beginning",
        "narrative": "A peaceful clearing.",
        "choices": [],
        "location": "Clearing",
        "nearby_enemies": [],
        "npcs_present": []
    }
    with patch("game_engine.generate_opening_scene", new_callable=AsyncMock) as mock_gen, \
         patch("game_engine.apply_quest_update"):
        mock_gen.return_value = mock_scene
        start_res = client.post("/api/adventure/start", json={
            "user_id": user_id,
            "scenario": "fantasy",
            "mode": "solo"
        })
        assert start_res.status_code == 200
        session_data = start_res.json()["session"]
        assert "party_members" in session_data
        assert len(session_data["party_members"]) >= 1
        assert session_data["party_members"][0]["user_id"] == user_id
        assert "hp" in session_data["party_members"][0]
        assert "status_effects" in session_data["party_members"][0]


@pytest.mark.api
def test_codex_and_quest_endpoints():
    """
    Verifies Phase 3B Codex and Quest API endpoints:
    1. /api/lorebook/{session_id} returns categories and entities.
    2. /api/quests/{session_id} returns quests, active_story_quest, and clues.
    3. /api/contacts/{session_id} returns NPC contacts.
    4. /api/factions/{session_id} returns faction standings.
    """
    session_id = 99201
    user_id = 99106

    # Setup lorebook entity
    db.upsert_lorebook_entity(
        session_id=session_id,
        entity_type="place",
        name="Ancient Shrine",
        description="A forgotten stone shrine surrounded by purple mist.",
        disposition="neutral"
    )

    # Setup quest
    db.upsert_quest(
        session_id=session_id,
        quest_id="quest_shrine_01",
        quest_type="story",
        title="Secrets of the Shrine",
        objective="Investigate the whispering stone.",
        status="Active",
        sub_objectives=[{"id": 1, "text": "Reach the shrine", "completed": True}],
        current_clues="Faint magical resonance."
    )

    # 1. Lorebook endpoint
    res_lb = client.get(f"/api/lorebook/{session_id}")
    assert res_lb.status_code == 200
    lb_data = res_lb.json()
    assert "categories" in lb_data
    assert "entities" in lb_data
    assert any(e["name"] == "Ancient Shrine" for e in lb_data["entities"])

    # 2. Quests endpoint
    res_q = client.get(f"/api/quests/{session_id}")
    assert res_q.status_code == 200
    q_data = res_q.json()
    assert "quests" in q_data
    assert "active_story_quest" in q_data
    assert any(q["quest_id"] == "quest_shrine_01" for q in q_data["quests"])

    # 3. Contacts endpoint
    res_c = client.get(f"/api/contacts/{session_id}?user_id={user_id}")
    assert res_c.status_code == 200
    assert "contacts" in res_c.json()

    # 4. Factions endpoint
    res_f = client.get(f"/api/factions/{session_id}")
    assert res_f.status_code == 200
    assert "factions" in res_f.json()


@pytest.mark.api
def test_smartphone_os_endpoints():
    """
    Verifies Phase 3C Smartphone OS API endpoints:
    1. /api/phone/{session_id}?user_id={user_id} returns branding, appointments, gossip_feed, and media_gallery.
    2. /api/phone/{session_id}/messages/{npc_id} returns DM chat history.
    """
    user_id = 99107
    db.delete_character(user_id)
    db.create_character(
        user_id=user_id,
        name="SmartphoneHero",
        char_class="Student",
        scenario="high_school_drama"
    )
    session_id = db.create_session(
        mode="solo",
        capacity=1,
        host_user_id=user_id,
        scenario="high_school_drama",
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False
    )
    db.add_session_member(session_id, user_id)

    # Save a phone appointment
    db.save_phone_appointment(
        session_id=session_id,
        npc_id="maya_anderson",
        npc_name="Maya Anderson",
        rendezvous_location="Library Courtyard"
    )

    # Save a phone message
    db.save_phone_message(
        session_id=session_id,
        contact_npc_id="maya_anderson",
        sender="Maya Anderson",
        message="Hey! Meet me at the library courtyard after class.",
        intent="meetup"
    )

    # Add a digital media item to player's inventory
    from mechanics.combat.items import create_digital_media_item
    create_digital_media_item(
        user_id=user_id,
        contact_name="Maya Anderson",
        media_type="photo",
        caption="Selfie with Maya studying by the window.",
        subject="Library",
        tags=["selfie", "maya"]
    )

    # 1. Fetch phone state
    res = client.get(f"/api/phone/{session_id}?user_id={user_id}")
    assert res.status_code == 200
    pdata = res.json()
    assert pdata["is_supported"] is True
    assert pdata["scenario"] == "high_school_drama"
    assert "branding" in pdata
    assert pdata["branding"]["device_name"] is not None

    # Check appointments
    assert len(pdata["appointments"]) >= 1
    assert any(a["npc_name"] == "Maya Anderson" for a in pdata["appointments"])

    # Check media gallery
    assert len(pdata["media_gallery"]) >= 1
    assert any(m["contact_name"] == "Maya Anderson" for m in pdata["media_gallery"])

    # 2. Fetch NPC messages
    res_msg = client.get(f"/api/phone/{session_id}/messages/maya_anderson")
    assert res_msg.status_code == 200
    msg_data = res_msg.json()
    assert "messages" in msg_data
    assert len(msg_data["messages"]) >= 1
    assert any("library courtyard" in m["message"].lower() for m in msg_data["messages"])


@pytest.mark.api
def test_wave3_merchant_use_saves_and_two_way_phone():
    """
    Verifies Wave 3 endpoints:
    1. Versioned schema_migrations table populated by init_db().
    2. /api/inventory/use for consumables and spellbooks.
    3. /api/merchant/{session_id}, /api/merchant/buy, /api/merchant/sell.
    4. /api/phone/{session_id}/messages/{npc_id} POST (2-way NPC texting).
    5. /api/saves/save, /api/saves/{user_id}, /api/saves/load, and DELETE /api/saves/{user_id}/{slot_name}.
    """
    # 1. Verify schema_migrations table has applied migrations
    with db.get_conn() as conn:
        rows = conn.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
    assert len(rows) >= 3
    assert rows[0]["version"] == 1

    # Setup character & active session
    user_id = 99108
    db.delete_character(user_id)
    char = db.create_character(
        user_id=user_id,
        name="WaveThreeHero",
        char_class="Mage",
        stats={"STR": 2, "PER": 1, "END": 2, "CHA": 5, "INT": 4, "AGI": 1, "LUK": 1},
        scenario="fantasy"
    )
    session_id = db.create_session(
        mode="solo",
        capacity=1,
        host_user_id=user_id,
        scenario="fantasy",
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.save_session_scene(
        session_id,
        "Market Square",
        "You stand in the bustling market square.",
        [{"label": "Browse stalls", "stat": "PER", "requirement": 4}],
        [],
        location="Capital ➔ Market Square"
    )

    # 2. Consumable item use (/api/inventory/use)
    db.apply_hp_mp_delta(user_id, hp_delta=-5)
    hp_before = db.get_character(user_id)["hp"]
    potion_id = db.add_item(user_id, "Healing Draught", item_type="Potion", effect="Restores 10 HP", slot_cost=1)
    res_use = client.post("/api/inventory/use", json={
        "user_id": user_id,
        "item_id": potion_id,
        "session_id": session_id
    })
    assert res_use.status_code == 200
    assert res_use.json()["success"] is True
    assert db.get_character(user_id)["hp"] > hp_before

    # 3. Merchant Shop (/api/merchant/{session_id}, /api/merchant/buy, /api/merchant/sell)
    db.apply_hp_mp_delta(user_id, gold_delta=200)
    db.save_merchant_state(session_id, {
        "available": True,
        "flavor_name": "Garrick the Smith",
        "flavor_description": "Fine steel and travel supplies.",
        "stock": [
            {"name": "Silver Dagger", "item_type": "Weapon", "description": "Finely balanced.", "price": 30, "quantity": 2, "tier": 3}
        ],
        "rumors": [{"text": "Goblin scouts were spotted near the old bridge.", "revealed": False}]
    })
    res_shop = client.get(f"/api/merchant/{session_id}?user_id={user_id}")
    assert res_shop.status_code == 200
    shop_data = res_shop.json()
    assert shop_data["merchant_name"] == "Garrick the Smith"
    assert shop_data["discount_pct"] > 0  # CHA 5 grants discount
    assert len(shop_data["stock"]) == 1

    # Buy Silver Dagger
    res_buy = client.post("/api/merchant/buy", json={
        "session_id": session_id,
        "user_id": user_id,
        "item_name": "Silver Dagger"
    })
    assert res_buy.status_code == 200
    buy_data = res_buy.json()
    assert buy_data["success"] is True
    assert buy_data["item_name"] == "Silver Dagger"
    bought_item_id = buy_data["item_id"]

    # Sell Silver Dagger back
    res_sell = client.post("/api/merchant/sell", json={
        "session_id": session_id,
        "user_id": user_id,
        "item_id": bought_item_id
    })
    assert res_sell.status_code == 200
    assert res_sell.json()["success"] is True
    assert res_sell.json()["gold_earned"] > 0

    # 4. Two-Way Smartphone Texting (POST /api/phone/{session_id}/messages/{npc_id})
    db.upsert_contact(
        session_id=session_id,
        character_id=char["id"],
        npc_id="lyra_vance",
        name="Lyra Vance",
        delta_score=15,
        basic_info={"role": "Guild Scout"},
        track="platonic"
    )
    with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_phone_llm:
        mock_phone_llm.return_value = {
            "reply_text": "I'm heading to the tavern now, see you soon!",
            "affinity_delta": 2,
            "rendezvous_location": ""
        }
        res_dm = client.post(f"/api/phone/{session_id}/messages/lyra_vance", json={
            "user_id": user_id,
            "message": "Hey Lyra, how is the patrol going?",
            "intent": "chat"
        })
        assert res_dm.status_code == 200
        dm_json = res_dm.json()
        assert dm_json["success"] is True
        assert any("tavern" in m["message"].lower() for m in dm_json["messages"])

    # 5. Adventure Save / Load / Delete Checkpoints
    res_save = client.post("/api/saves/save", json={
        "user_id": user_id,
        "slot_name": "Market Checkpoint",
        "overwrite": True
    })
    assert res_save.status_code == 200
    assert res_save.json()["status"] == "saved"

    res_list = client.get(f"/api/saves/{user_id}")
    assert res_list.status_code == 200
    assert any(s["slot_name"] == "Market Checkpoint" for s in res_list.json()["saves"])

    res_load = client.post("/api/saves/load", json={
        "user_id": user_id,
        "slot_name": "Market Checkpoint"
    })
    assert res_load.status_code == 200
    assert res_load.json()["success"] is True
    assert res_load.json()["session"]["scene_title"] == "Market Square"

    res_del = client.delete(f"/api/saves/{user_id}/Market%20Checkpoint")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True


@pytest.mark.api
def test_wave4_circuit_breaker_companions_phone_shop_and_lobbies():
    """
    Verifies Wave 4 Modernization (Phases 11, 12, and 13):
    1. Phase 11 package exports: game_engine.choices_cleaner, game_engine.npcs, mechanics.combat.items.consumables.
    2. Phase 12 LLM circuit breaker & telemetry endpoint (/api/settings/debug/telemetry).
    3. Phase 13B Companion recruitment & dismissal (/api/party/companion).
    4. Phase 13C Phone Delivery Shop (/api/merchant/{session_id}?is_phone_shop=true and /api/merchant/buy).
    5. Phase 13D Open Multiplayer Lobbies (/api/adventure/lobbies).
    """
    # 1. Phase 11 Package Exports Check
    from game_engine import clean_choices_impl, sanitize_and_diversify_choices
    from game_engine.npcs import process_scene_npcs, extract_speaking_npcs_from_narrative
    from mechanics.combat.items.consumables import apply_item_to_target, parse_consumable_metadata
    assert callable(clean_choices_impl)
    assert callable(sanitize_and_diversify_choices)
    assert callable(process_scene_npcs)
    assert callable(extract_speaking_npcs_from_narrative)
    assert callable(apply_item_to_target)
    assert callable(parse_consumable_metadata)

    # 2. Phase 12 Circuit Breaker & Telemetry Check
    import llm_client
    llm_client.reset_circuit_breakers()
    assert llm_client.is_model_healthy("broken-model-x") is True
    llm_client.trip_model_circuit("broken-model-x", cooldown_sec=30.0)
    assert llm_client.is_model_healthy("broken-model-x") is False
    ordered = llm_client._prioritize_healthy_candidates([
        (None, "broken-model-x"),
        (None, "healthy-model-y"),
    ])
    assert ordered[0][1] == "healthy-model-y"
    llm_client.reset_circuit_breakers()

    llm_client.record_llm_telemetry("healthy-model-y", latency_ms=145.0, success=True)
    res_tel = client.get("/api/settings/debug/telemetry")
    assert res_tel.status_code == 200
    tel_data = res_tel.json()["telemetry"]
    assert tel_data["total_calls"] >= 1
    assert any(c["model"] == "healthy-model-y" for c in tel_data["recent_calls"])

    # 3. Phase 13B Companion Recruit / Dismiss
    user_id = 99109
    db.delete_character(user_id)
    char = db.create_character(
        user_id=user_id,
        name="WaveFourHero",
        char_class="Rogue",
        stats={"STR": 2, "PER": 3, "END": 2, "CHA": 4, "INT": 2, "AGI": 3, "LUK": 2},
        scenario="cyberpunk"
    )
    session_id = db.create_session(
        mode="turn",
        capacity=4,
        host_user_id=user_id,
        scenario="cyberpunk",
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.save_session_scene(
        session_id,
        "Neon Alley",
        "Rain slicks the neon-lit pavement.",
        [{"label": "Scan the alley", "stat": "PER", "requirement": 4}],
        [],
        location="Downtown ➔ Neon Alley"
    )

    # Add friendly NPC contact (affinity 25 >= 15)
    db.upsert_contact(
        session_id=session_id,
        character_id=char["id"],
        npc_id="kira_vex",
        name="Kira Vex",
        delta_score=25,
        basic_info={"role": "Shadow Runner", "level": 3},
        track="platonic"
    )

    res_recruit = client.post("/api/party/companion", json={
        "user_id": user_id,
        "session_id": session_id,
        "npc_name": "Kira Vex",
        "action": "recruit"
    })
    assert res_recruit.status_code == 200
    rec_data = res_recruit.json()
    assert rec_data["status"] == "recruited"
    assert any(p["name"] == "Kira Vex" for p in rec_data["party_npcs"])

    res_dismiss = client.post("/api/party/companion", json={
        "user_id": user_id,
        "session_id": session_id,
        "npc_name": "Kira Vex",
        "action": "dismiss"
    })
    assert res_dismiss.status_code == 200
    dis_data = res_dismiss.json()
    assert dis_data["status"] == "dismissed"
    assert not any(p["name"] == "Kira Vex" for p in dis_data["party_npcs"])

    # 4. Phase 13C Phone E-Shop Delivery
    db.apply_hp_mp_delta(user_id, gold_delta=500)
    with patch("api.inventory_merchant.generate_merchant_shop", new_callable=AsyncMock) as mock_gen_shop:
        mock_gen_shop.return_value = {
            "intro_narrative": "Drone courier standing by.",
            "stock": [
                {"name": "Synth-Coffee Pack", "item_type": "Drink", "description": "Restores 10 MP.", "price": 25, "quantity": 2, "tier": 2}
            ],
            "rumors": [],
        }
        res_pshop = client.get(f"/api/merchant/{session_id}?user_id={user_id}&is_phone_shop=true")
    assert res_pshop.status_code == 200
    pshop_data = res_pshop.json()
    assert pshop_data["is_phone_shop"] is True
    assert len(pshop_data["inventory"]) > 0
    first_delivery_item = pshop_data["inventory"][0]["name"]

    res_pbuy = client.post("/api/merchant/buy", json={
        "user_id": user_id,
        "session_id": session_id,
        "item_name": first_delivery_item,
        "is_phone_shop": True
    })
    assert res_pbuy.status_code == 200
    assert res_pbuy.json()["success"] is True
    assert res_pbuy.json()["item_name"] == first_delivery_item

    # 5. Phase 13D Open Multiplayer Lobbies
    res_lobbies = client.get("/api/adventure/lobbies")
    assert res_lobbies.status_code == 200
    lobbies_list = res_lobbies.json()["lobbies"]
    assert any(l["id"] == session_id for l in lobbies_list)


@pytest.mark.api
def test_wave5_character_studio_merchant_haggle_and_telemetry():
    """Tests Wave 5 (Phases 14-16): Character Creation Studio, Merchant Haggling & Rumor Caseboard, and Debug Telemetry."""
    user_id = 99505

    # 1. Phase 14: Scenarios & Class Templates Studio Metadata
    res_scen = client.get("/api/scenarios")
    assert res_scen.status_code == 200
    scen_payload = res_scen.json()
    assert "scenarios" in scen_payload
    assert isinstance(scen_payload.get("scenario_list"), list)
    assert len(scen_payload["scenario_list"]) > 0

    res_tpl = client.get("/api/class-templates?scenario=cyberpunk")
    assert res_tpl.status_code == 200
    tpl_data = res_tpl.json()
    assert "classes" in tpl_data
    assert "race_options" in tpl_data
    assert "stat_names" in tpl_data
    assert tpl_data.get("max_total_points") == 12

    # Create character via Studio payload (with class_name alias and 2 unspent points -> 10 total)
    res_create = client.post("/api/character/create", json={
        "user_id": user_id,
        "name": "Valerie V",
        "class_name": "Netrunner",
        "class_description": "Elite neural hacker.",
        "gender": "Female",
        "race": "Cyborg",
        "scenario": "cyberpunk",
        "starting_weapon": "Monowire Whip",
        "str": 1, "per": 2, "end": 1, "cha": 2, "int": 2, "agi": 1, "luk": 1
    })
    assert res_create.status_code == 200
    created_char = res_create.json()["character"]
    assert created_char["name"] == "Valerie V"
    assert created_char["char_class"] == "Netrunner"
    assert created_char["pending_stat_points"] == 2

    # 2. Phase 16B: Debug Sandbox & Telemetry Inspector
    res_dbg = client.post(f"/api/debug/{user_id}", json={
        "debug_check_mode": "pass",
        "debug_stat_mode": "max",
        "action": "hp_to_1"
    })
    assert res_dbg.status_code == 200
    assert res_dbg.json()["debug_check_mode"] == "pass"
    assert res_dbg.json()["hp"] == 1

    res_heal = client.post(f"/api/debug/{user_id}", json={"action": "full_heal"})
    assert res_heal.status_code == 200
    assert res_heal.json()["hp"] == res_heal.json()["max_hp"]

    res_get_dbg = client.get(f"/api/debug/{user_id}")
    assert res_get_dbg.status_code == 200
    assert "telemetry" in res_get_dbg.json()

    # 3. Phase 15C: Specialist Stores, Charisma Haggling & Rumor Investigation
    session_id = db.create_session(
        mode="turn",
        capacity=1,
        host_user_id=user_id,
        scenario="fantasy",
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.save_merchant_state(session_id, {
        "available": True,
        "flavor_name": "Garrick's Bazaar",
        "merchant_type": "general_merchant",
        "stock": [
            {"name": "Steel Longsword", "item_type": "Weapon", "description": "Balanced blade.", "price": 100, "quantity": 2, "tier": 2}
        ],
        "rumors": [
            {"text": "A hidden vault lies beneath the clocktower.", "revealed": False}
        ],
        "haggle_attempts": 0,
        "discount_pct": 0,
    })

    res_shop = client.get(f"/api/merchant/{session_id}?user_id={user_id}")
    assert res_shop.status_code == 200
    shop_data = res_shop.json()
    assert shop_data["haggle_attempts_left"] == 3
    assert isinstance(shop_data.get("available_stores"), list)
    assert len(shop_data["available_stores"]) > 1

    # Haggle (guaranteed pass because debug_check_mode == "pass")
    res_haggle = client.post("/api/merchant/haggle", json={
        "session_id": session_id,
        "user_id": user_id
    })
    assert res_haggle.status_code == 200
    haggle_data = res_haggle.json()
    assert haggle_data["haggle_succeeded"] is True
    assert haggle_data["haggle_attempts"] == 1
    assert haggle_data["haggle_attempts_left"] == 2
    assert haggle_data["haggle_discount_pct"] == 10

    # Investigate Rumor #0 -> reveals and logs to Clue Caseboard
    res_rumor = client.post("/api/merchant/rumor", json={
        "session_id": session_id,
        "user_id": user_id,
        "rumor_index": 0
    })
    assert res_rumor.status_code == 200
    rumor_data = res_rumor.json()
    assert rumor_data["rumor_succeeded"] is True
    assert "clocktower" in rumor_data["rumor_text"]
    assert rumor_data["rumors"][0]["revealed"] is True


@pytest.mark.api
def test_character_studio_custom_scenario_and_preview_gear():
    """Tests multi-tag custom scenario class/weapon merging, equipment preview regeneration, and starter_loadout persistence."""
    user_id = 99506
    db.delete_character(user_id)

    # 1. Multi-tag custom scenario class templates merge classes from both steampunk and cyberpunk
    res_tpl = client.get("/api/class-templates?scenario=custom&tags=steampunk,cyberpunk")
    assert res_tpl.status_code == 200
    tpl_data = res_tpl.json()
    assert "classes" in tpl_data
    assert "all_classes" in tpl_data
    assert len(tpl_data["all_classes"]) >= len(tpl_data["classes"])
    source_scenarios = {v.get("source_scenario") for v in tpl_data["classes"].values() if isinstance(v, dict)}
    assert "steampunk" in source_scenarios
    assert "cyberpunk" in source_scenarios

    # 2. Preview / Regenerate starter equipment
    res_prev = client.post("/api/character/preview-gear", json={
        "char_class": "Paladin",
        "scenario": "custom",
        "tags": ["fantasy", "steampunk"],
        "gender": "Female",
        "race": "Human",
        "starting_weapon": "Radiant Longsword",
        "force_dynamic": True,
    })
    assert res_prev.status_code == 200
    prev_data = res_prev.json()
    assert prev_data["success"] is True
    assert isinstance(prev_data["loadout"], dict)
    assert len(prev_data["loadout"]) > 0

    # 3. Create character with explicit starter_loadout and custom scenario tags
    custom_loadout = {
        "Head": {"name": "Aether Brass Goggles", "description": "Precision brass lenses.", "slot_cost": 1, "item_type": "Head"},
        "Top": {"name": "Clockwork Trenchcoat", "description": "Reinforced leather coat.", "slot_cost": 1, "item_type": "Top"},
    }
    res_create = client.post("/api/character/create", json={
        "user_id": user_id,
        "name": "Artemis Gearwright",
        "class_name": "Steam Engineer",
        "gender": "Male",
        "race": "Human",
        "scenario": "custom",
        "tags": ["steampunk", "cyberpunk"],
        "starting_weapon": "Aether Musket",
        "starter_loadout": custom_loadout,
        "str": 3, "per": 1, "end": 3, "cha": 1, "int": 1, "agi": 2, "luk": 1
    })
    assert res_create.status_code == 200
    create_json = res_create.json()
    assert create_json["success"] is True
    assert "custom_combinator_" in create_json["resolved_scenario"]

    res_sheet = client.get(f"/api/character/{user_id}")
    assert res_sheet.status_code == 200
    eq = res_sheet.json()["equipment"]
    assert eq["Head"]["name"] == "Aether Brass Goggles"
    assert eq["Top"]["name"] == "Clockwork Trenchcoat"
    assert eq["Weapon"]["name"] == "Aether Musket"

    # 4. Verify enrich_choices_with_odds and _enrich_session_for_client provide Discord-matching icons & merchant_available
    from api.deps import enrich_choices_with_odds
    from api.adventure import _enrich_session_for_client

    sample_choices = [
        {"label": "Inspect the ancient runes carefully", "stat": "PER", "requirement": 6},
        {"label": "Inquire about the missing caravan", "stat": "INT", "requirement": 5},
        {"label": "Thank Volo Bloodhunter, excuse yourself, and look around the room", "stat": "NONE", "requirement": 0},
        {"label": "Search the ruins for the key", "stat": "AGI", "requirement": 6, "is_story_quest": True, "quest_id": "SQ-1"},
    ]
    enriched_choices = enrich_choices_with_odds(sample_choices, user_id)
    assert enriched_choices[0]["skill_emoji"] == "👁️"
    assert enriched_choices[0]["emoji"] == "👁️"
    assert enriched_choices[1]["quest_icon"] == "💬"
    assert enriched_choices[1]["skill_emoji"] == "🧠"
    assert enriched_choices[1]["emoji"] == "💬 🧠"
    assert enriched_choices[2]["skill_emoji"] == "🚪"
    assert enriched_choices[2]["emoji"] == "🚪"
    assert enriched_choices[3]["quest_icon"] == "⭐"
    assert enriched_choices[3]["skill_emoji"] == "🏹"
    assert enriched_choices[3]["emoji"] == "⭐ 🏹"

    mock_session = {
        "id": 0,
        "host_user_id": user_id,
        "scenario": "fantasy",
        "current_location": "Capital City ➔ Grand Bazaar",
        "choices": sample_choices,
        "merchant": {"available": False},
    }
    enriched_sess = _enrich_session_for_client(mock_session, user_id)
    assert enriched_sess["merchant_available"] is True
    assert enriched_sess["merchant_action_label"] == "Visit Market / Shop"


@pytest.mark.api
@pytest.mark.asyncio
async def test_streaming_extractor_and_full_history_preservation():
    """
    Verifies:
    1. StreamingNarrativeExtractor extracts both `outcome_narrative` and `next_narrative` chunks in real-time.
    2. Turn resolution preserves the opening scene (`type: "scene"`) in `session.history` and records both
       `outcome_narrative` and `next_narrative` on action history entries so previous narrations never disappear.
    """
    from llm_client import StreamingNarrativeExtractor

    collected_by_field = {"outcome_narrative": "", "next_narrative": ""}

    async def on_token(tok: str, field: str = "outcome_narrative"):
        collected_by_field[field] = collected_by_field.get(field, "") + tok

    on_token._accepts_field = True
    extractor = StreamingNarrativeExtractor(on_token)

    sample_json_stream = (
        '{"scene_title": "Guild Hall Confrontation", '
        '"outcome_narrative": "Alice steps forward.\\nSansa sets her teacup down.", '
        '"next_narrative": "The hall falls silent as Volo watches.", '
        '"next_choices": []}'
    )
    # Feed in small 5-char chunks to simulate token streaming
    for i in range(0, len(sample_json_stream), 5):
        await extractor.process_chunk(sample_json_stream[i:i + 5])

    assert collected_by_field["outcome_narrative"] == "Alice steps forward.\nSansa sets her teacup down."
    assert collected_by_field["next_narrative"] == "The hall falls silent as Volo watches."

    # Verify history preservation across turns via /api/adventure/action
    user_id = 99125
    db.delete_character(user_id)
    db.create_character(
        user_id=user_id,
        name="StreamHero",
        char_class="Warrior",
        stats={"STR": 2, "PER": 1, "END": 2, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1},
        scenario="fantasy"
    )
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.save_session_scene(
        session_id=session_id,
        scene_title="Opening Guild Hall",
        narrative="The morning sun filters into the Adventurers' Guild Hall.",
        choices=[{"label": "Confront Sansa", "stat": "CHA", "requirement": 6, "mp_cost": 0}],
        history=[]
    )

    mock_outcome = {
        "scene_title": "A Writ Made Before Its Crime",
        "outcome_narrative": "Alice confronts Sansa before the notice board.",
        "next_narrative": "Sansa holds aloft a sealed writ as the room goes quiet.",
        "next_choices": [{"label": "Demand answers", "stat": "INT", "requirement": 6}],
        "character_outcomes": [{"name": "WebHero", "hp_change": 0, "mp_change": 0, "gold_change": -5, "items_gained": [], "items_lost": [], "status_effects": []}]
    }

    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={user_id: []}), \
         patch("game_engine.apply_quest_update"):
        mock_resolve.return_value = mock_outcome

        res = client.post("/api/adventure/action", json={
            "session_id": session_id,
            "user_id": user_id,
            "choice_index": 0
        })
        assert res.status_code == 200
        sess = res.json()["session"]
        hist = sess["history"]
        assert len(hist) == 2
        assert hist[0]["type"] == "scene"
        assert hist[0]["scene_title"] == "Opening Guild Hall"
        assert "Adventurers' Guild Hall" in hist[0]["next_narrative"]
        assert hist[1]["type"] == "action"
        assert hist[1]["outcome_narrative"] == "Alice confronts Sansa before the notice board."
        assert hist[1]["next_narrative"] == "Sansa holds aloft a sealed writ as the room goes quiet."
        assert hist[1]["character_outcomes"][0]["gold_change"] == -5


@pytest.mark.api
def test_retry_adventure_scene_with_none_rewards(web_user_and_character):
    user_id = web_user_and_character
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.save_session_scene(
        session_id=session_id,
        scene_title="Fallback Scene",
        narrative="The atmosphere settles around the area as the immediate action resolves.",
        choices=[{"label": "Proceed", "is_fallback": True}],
        history=[{
            "type": "action",
            "label": "Study Brann's marks",
            "stat": "INT",
            "requirement": None,
            "mp_spent": None,
            "roll": None,
            "chance": None,
            "tier": "crit_success",
            "tier_label": "Critical Success",
            "success": True,
            "outcome_narrative": "Alice acts with deliberate intent.",
            "next_narrative": "The atmosphere settles around the area as the immediate action resolves."
        }]
    )

    from models.llm_schemas import TurnOutcome
    outcome_model = TurnOutcome(
        scene_title="The Signal That Never Came",
        outcome_narrative="Alice deciphers the hidden switchback marks along the cliffside.",
        next_narrative="Brann nods grimly as the true smuggling path becomes clear.",
        next_choices=[{"label": "Follow the ridge path", "stat": "AGI", "requirement": 5}],
        quest_updates=[{
            "quest_id": "SQ-TESTRETRY",
            "title": "The Smuggler's Signal",
            "quest_type": "Story Quest",
            "objective": "Trace the hidden route.",
            "reward_xp": None,
            "reward_gold": None,
        }]
    )
    dumped_outcome = outcome_model.model_dump(exclude_unset=False)

    from services.turn_service import TurnResponse, TurnService
    mock_response = TurnResponse(
        success=True,
        session={"scene_title": "The Signal That Never Came", "narrative": "Brann nods grimly as the true smuggling path becomes clear.", "history": [{"type": "action", "outcome_narrative": "Alice deciphers the hidden switchback marks along the cliffside."}]},
        outcome=dumped_outcome,
        action={"char": {"name": "Alice"}, "stat": "AGI", "check": {"chance": 100, "tier_label": "Success", "tier": "success"}},
        items_gained_by_user={},
        xp_gained=0,
        levels_gained=[],
        new_char={}
    )

    with patch.object(TurnService, "retry_narration", new=AsyncMock(return_value=mock_response)) as mock_resolve:
        res = client.post("/api/adventure/retry", json={
            "session_id": session_id,
            "user_id": user_id
        })
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["session"]["scene_title"] == "The Signal That Never Came"
        assert "Brann nods grimly" in data["session"]["narrative"]
        assert "deciphers the hidden switchback" in data["session"]["history"][-1]["outcome_narrative"]


def test_adventure_action_applies_intimate_action_dc_modifier(web_user_and_character):
    """Verifies that execute_action in api/adventure.py calculates intimate action DC modifiers."""
    user_id = web_user_and_character
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    with db.get_conn() as conn:
        conn.execute("UPDATE sessions SET dialogue_partner='Sylvia' WHERE id=?", (session_id,))
    
    char = db.get_character(user_id)
    db.upsert_contact(
        session_id=session_id,
        character_id=char["id"],
        npc_id="sylvia",
        name="Sylvia",
        appearance={
            "turn_ons": "nape of neck (physical), whispered praise",
            "erotic_openness": "shameless"
        }
    )

    action_payload = {
        "session_id": session_id,
        "user_id": user_id,
        "direct_choice": {
            "label": "Gently kiss and caress the nape of her neck in the moonlight",
            "stat": "CHA",
            "requirement": 10,
            "choice_type": "dialogue"
        }
    }
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = {
            "scene_title": "Garden Whispers",
            "outcome_narrative": "She shivers as your lips touch her nape.",
            "next_narrative": "Her breath catches against your cheek.",
            "next_choices": [{"label": "Continue holding her close", "stat": "CHA", "requirement": 5}],
            "relationship_updates": []
        }
        res = client.post("/api/adventure/action", json=action_payload)
        assert res.status_code == 200
        data = res.json()
        c_rec = db.get_contact(session_id, "sylvia", char["id"])
        from mechanics.combat.traits import get_combined_dc_modifiers
        from mechanics.social.persona import calculate_intimate_action_dc_modifier
        t_mods = get_combined_dc_modifiers(c_rec.get("unlocked_traits") or [])
        int_mod = calculate_intimate_action_dc_modifier("Gently kiss and caress the nape of her neck in the moonlight", c_rec["appearance"])
        assert int_mod == -5
        expected_req = max(1, 10 + t_mods.get("CHA", 0) + int_mod)
        resolved_action = data["action"]
        assert resolved_action["requirement"] == expected_req



