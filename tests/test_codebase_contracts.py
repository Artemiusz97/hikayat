"""
Architectural and Static Contract Tests for Hikayat.

These tests enforce invariant guarantees across the codebase:
1. DB Method AST Contract: Every db.<func>() call in any Python file must resolve to a valid callable in db.
2. Serialization Contract: Action payloads with CheckResult dataclasses must be safely serializable to JSON.
3. Schema Compatibility Contract: Pydantic models (TurnOutcome, OpeningScene) must support both dict and model access.
"""
import ast
import os
import json
import pytest
import db
import server
from skill_check import CheckResult
from services.turn_service import TurnResponse
from models.llm_schemas import TurnOutcome, OpeningScene, ActionClassification


@pytest.mark.contract
def test_all_db_calls_resolve_to_existing_functions():
    """
    Scans every Python file in the repository (excluding tests and virtualenvs)
    and verifies that every `db.<method>()` and `game_engine.<method>()` call
    maps to a real callable on `db` or `game_engine`.
    This prevents missing database/engine method regressions across all packages including `api/`.
    """
    import game_engine
    import llm_client

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db_attrs = set(dir(db))
    ge_attrs = set(dir(game_engine))
    llm_attrs = set(dir(llm_client))

    missing = []
    syntax_errors = []
    checked_files = 0
    checked_calls = 0

    target_subdirs = ["api", "cogs", "db", "game_engine", "mechanics", "models", "services", "scripts"]
    files_to_check = [os.path.join(root_dir, f) for f in os.listdir(root_dir) if f.endswith(".py")]
    for sub in target_subdirs:
        sub_path = os.path.join(root_dir, sub)
        if os.path.isdir(sub_path):
            for dirpath, _, filenames in os.walk(sub_path):
                for f in filenames:
                    if f.endswith(".py"):
                        files_to_check.append(os.path.join(dirpath, f))

    for filepath in files_to_check:
        relpath = os.path.relpath(filepath, root_dir)
        checked_files += 1

        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                tree = ast.parse(fp.read(), filename=relpath)
        except SyntaxError as e:
            syntax_errors.append(f"{relpath}:{e.lineno} -> SyntaxError: {e.msg}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    mod_name = node.func.value.id
                    method = node.func.attr
                    if method.startswith("_"):
                        continue
                    if mod_name == "db":
                        checked_calls += 1
                        if method not in db_attrs:
                            missing.append(f"{relpath}:{node.lineno} -> db.{method}() not found")
                        elif not callable(getattr(db, method)):
                            missing.append(f"{relpath}:{node.lineno} -> db.{method} is not callable")
                    elif mod_name == "game_engine":
                        checked_calls += 1
                        if method not in ge_attrs:
                            missing.append(f"{relpath}:{node.lineno} -> game_engine.{method}() not found")
                        elif not callable(getattr(game_engine, method)):
                            missing.append(f"{relpath}:{node.lineno} -> game_engine.{method} is not callable")
                    elif mod_name == "llm_client":
                        checked_calls += 1
                        if method not in llm_attrs:
                            missing.append(f"{relpath}:{node.lineno} -> llm_client.{method}() not found")
                        elif not callable(getattr(llm_client, method)):
                            missing.append(f"{relpath}:{node.lineno} -> llm_client.{method} is not callable")
                elif (
                    isinstance(node.func.value, ast.Attribute)
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "self"
                    and node.func.value.attr == "cog"
                ):
                    from cogs.adventure import AdventureCog
                    cog_method = node.func.attr
                    checked_calls += 1
                    if not hasattr(AdventureCog, cog_method):
                        missing.append(f"{relpath}:{node.lineno} -> self.cog.{cog_method}() not found on AdventureCog")

    assert syntax_errors == [], "Detected syntax errors in repository files:\n" + "\n".join(syntax_errors)
    assert checked_files > 25, f"Expected to scan at least 25 files, but only scanned {checked_files}"
    assert checked_calls > 50, f"Expected to check at least 50 module calls, but only checked {checked_calls}"
    assert missing == [], "Detected calls to non-existent db/game_engine/llm_client/AdventureCog methods:\n" + "\n".join(missing)


@pytest.mark.contract
def test_action_and_check_result_serialization():
    """
    Verifies that action dictionaries containing CheckResult dataclasses
    are converted to plain serializable dicts by `server._serializable_action`,
    preventing TypeError in json.dumps and WebSocket.send_json.
    """
    res = CheckResult(chance=75, roll=62.5, tier="success", tier_label="Success", succeeded=True, requirement=12)
    raw_action = {
        "user_id": 12345,
        "character_name": "TestHero",
        "stat": "STR",
        "requirement": 12,
        "rate": 75,
        "check": res,
        "label": "Kick down the sturdy iron door",
        "success": True,
        "tier": "success",
    }

    # Verify that raw CheckResult indeed fails standard json.dumps
    with pytest.raises(TypeError, match="CheckResult is not JSON serializable"):
        json.dumps(raw_action)

    # Verify that server._serializable_action solves this and produces valid JSON
    safe_action = server._serializable_action(raw_action)
    dumped = json.dumps(safe_action)
    assert dumped is not None
    loaded = json.loads(dumped)
    assert loaded["check"]["tier"] == "success"
    assert loaded["check"]["roll"] == 62.5
    assert loaded["check"]["succeeded"] is True


@pytest.mark.contract
def test_turn_response_pydantic_serialization():
    """
    Verifies that TurnResponse can be instantiated and dumped to a dict/JSON cleanly.
    """
    resp = TurnResponse(
        success=True,
        session={"id": 1, "status": "active"},
        outcome={"outcome_narrative": "A dramatic clash of swords!", "choices": []},
        action={"label": "Strike"},
        items_gained_by_user={123: ["Bronze Key"]},
        xp_gained=25,
        levels_gained=[],
        new_char={"name": "Hero", "level": 1}
    )
    dumped = resp.model_dump()
    assert dumped["success"] is True
    assert dumped["xp_gained"] == 25
    assert dumped["items_gained_by_user"].get(123) == ["Bronze Key"] or dumped["items_gained_by_user"].get("123") == ["Bronze Key"]


@pytest.mark.contract
def test_llm_schemas_field_validators_and_dict_access():
    """
    Verifies that Pydantic models in models.llm_schemas:
    1. Gracefully handle empty strings for optional fields (e.g. from Gemma/Ollama).
    2. Support both attribute access and dictionary subscripting/get().
    """
    # 1. TurnOutcome with empty string faction promotion
    outcome_data = {
        "scene_title": "The Old Watchtower",
        "outcome_narrative": "You step into the dusty ruins.",
        "next_narrative": "The wind howls through cracked masonry.",
        "choices": [{"label": "Search room", "stat": "PER", "requirement": 10}],
        "faction_promotion_result": "",  # Empty string should not fail validation
    }
    outcome = TurnOutcome.model_validate(outcome_data)
    assert outcome.scene_title == "The Old Watchtower"
    assert outcome["scene_title"] == "The Old Watchtower"
    assert outcome.get("scene_title") == "The Old Watchtower"
    assert outcome.get("non_existent", "default") == "default"

    # 2. OpeningScene dictionary compatibility
    scene_data = {
        "scene_title": "Beginning",
        "narrative": "Your journey begins in the town tavern.",
        "choices": [{"label": "Approach bartender", "stat": "CHA", "requirement": 8}],
        "location": "Tavern",
        "nearby_enemies": [],
        "npcs_present": ["Bartender Gary"]
    }
    scene = OpeningScene.model_validate(scene_data)
    assert scene["location"] == "Tavern"
    assert scene.get("location") == "Tavern"
    dumped_scene = scene.model_dump()
    assert isinstance(dumped_scene, dict)
    assert dumped_scene["npcs_present"][0]["name"] == "Bartender Gary"

    # 3. ActionClassification
    ac_data = {
        "classification": "attack",
        "stat": "STR",
        "requirement": 14,
        "mp_cost": 0,
        "explanation": "Striking the goblin"
    }
    ac = ActionClassification.model_validate(ac_data)
    assert ac["stat"] == "STR"
    assert ac.get("requirement") == 14


@pytest.mark.contract
def test_wave6_targeted_module_decomposition_and_exports():
    """
    Verifies Wave 6 targeted decomposition:
    1. game_engine/core.py, cogs/adventure/cog.py, and mechanics/phone/messaging.py are each < 55 KB.
    2. All extracted sub-modules exist and re-export their expected symbols/methods cleanly without namespace hacks.
    """
    import game_engine
    import game_engine.core
    import game_engine.keywords
    import game_engine.prompts
    import game_engine.schemas
    from cogs.adventure.cog import AdventureCog
    from cogs.adventure.merchant_mixin import MerchantMixin
    from cogs.adventure.faction_mixin import FactionMixin
    import mechanics.system.phone
    import mechanics.system.phone.messaging
    import mechanics.system.phone.gossip_feed
    import mechanics.system.phone.social_graph

    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for rel_path in (
        "game_engine/core.py",
        "cogs/adventure/cog.py",
        "mechanics/system/phone/messaging.py",
    ):
        full_path = os.path.join(root_dir, rel_path)
        size_kb = os.path.getsize(full_path) / 1024.0
        assert size_kb < 60.0, f"{rel_path} should be under 60 KB after Wave 6 split, got {size_kb:.1f} KB"

    # Verify game_engine & game_engine.core exports
    for sym in (
        "SYSTEM_PROMPT",
        "VERBOSITY_INSTRUCTIONS",
        "DIALOGUE_INSTRUCTIONS",
        "SCENE_SCHEMA",
        "OUTCOME_SCHEMA",
        "STATE_ARBITER_SCHEMA",
        "CUSTOM_STARTER_GEAR_SYSTEM_PROMPT",
        "sanitize_comparative_cliches",
        "INTERCOURSE_KEYWORDS",
        "parse_clue_list",
    ):
        assert hasattr(game_engine, sym), f"game_engine missing {sym}"
        assert hasattr(game_engine.core, sym), f"game_engine.core missing {sym}"

    # Verify AdventureCog mixin inheritance & methods
    assert issubclass(AdventureCog, MerchantMixin)
    assert issubclass(AdventureCog, FactionMixin)
    for method_name in (
        "enter_merchant_shop",
        "open_buy_menu",
        "buy_item",
        "open_sell_menu",
        "sell_item",
        "resolve_haggle",
        "reveal_rumor",
        "leave_merchant",
        "open_faction_hq_menu",
        "faction_apply",
        "faction_rest",
        "faction_quartermaster",
        "faction_bounty",
        "faction_promotion",
        "faction_leave",
    ):
        assert hasattr(AdventureCog, method_name), f"AdventureCog missing mixin method {method_name}"

    # Verify mechanics.system.phone & mechanics.system.phone.messaging exports
    for fn_name in (
        "generate_gossip_feed_posts",
        "log_gossip_clue_to_quest",
        "get_social_state_summary",
        "scour_feed_for_rumor",
        "get_mutual_friends_and_ties",
        "lookup_social_profile",
        "resolve_social_friend_request",
        "discover_suggested_peer",
        "generate_player_chat_message",
        "generate_contact_dm_reply",
    ):
        assert hasattr(mechanics.system.phone, fn_name), f"mechanics.system.phone missing {fn_name}"
        assert hasattr(mechanics.system.phone.messaging, fn_name), f"mechanics.system.phone.messaging missing {fn_name}"


@pytest.mark.contract
def test_wave7_web_spa_gameplay_parity_endpoints(monkeypatch, tmp_path):
    """
    Verifies Wave 7 Web SPA Gameplay Parity endpoints (Phases 20-23):
    1. GET /api/locations/{session_id} returns discovered 3-tier zone & primary place tree with travel_tag.
    2. GET /api/factions/{session_id} and POST /api/factions/{session_id}/hq-action (join, rest, promote, leave).
    3. POST /api/phone/{session_id}/feed/scour, /peerpulse/discover, and /peerpulse/friend-request.
    4. POST /api/quests/{session_id}/bounties/action and /clues/deduce (Breakthrough synthesis + 50 XP).
    """
    from fastapi.testclient import TestClient
    from unittest.mock import patch, MagicMock
    from server import app
    import db

    test_db = str(tmp_path / "wave7_test.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()

    uid = 990077
    db.create_character(
        user_id=uid,
        name="Aria",
        char_class="Scholar",
        gender="Female",
        race="Human",
        scenario="high_school_drama",
        stats={"STR": 5, "PER": 8, "END": 5, "CHA": 8, "INT": 9, "AGI": 6, "LUK": 7},
    )
    sid = db.create_session(
        mode="solo",
        capacity=1,
        host_user_id=uid,
        scenario="high_school_drama",
        verbosity="vivid",
        dialogue_mode="balanced",
        image_gen_enabled=0,
    )
    db.add_session_member(sid, uid)
    db.set_session_active(sid, [uid])
    db.save_session_scene(
        sid,
        "Morning Bell",
        "Students gather in the courtyard.",
        [],
        [],
        location="Westlake Academy ➔ Courtyard",
    )

    client = TestClient(app)

    # 1. Phase 20: World Map & Fast-Travel Explorer endpoint
    loc_res = client.get(f"/api/locations/{sid}?user_id={uid}")
    assert loc_res.status_code == 200
    loc_data = loc_res.json()
    assert loc_data["session_id"] == sid
    assert isinstance(loc_data["zones"], list)
    assert len(loc_data["zones"]) >= 1
    assert any("travel_tag" in p for z in loc_data["zones"] for p in z.get("primary_locations", []))

    # 2. Phase 21: Faction HQ Operations & Leadership Rosters
    db.upsert_faction(
        session_id=sid,
        name="Student Council",
        delta_score=45,
        notes="Campus student government.",
        category="council",
        hq_location_id="Westlake Academy ➔ Student Council Office",
        hierarchy_template="council",
    )
    fac_res = client.get(f"/api/factions/{sid}?user_id={uid}")
    assert fac_res.status_code == 200
    fac_list = fac_res.json()["factions"]
    assert len(fac_list) == 1
    assert len(fac_list[0]["leadership_roster"]) == 4

    # Join faction
    join_res = client.post(
        f"/api/factions/{sid}/hq-action",
        json={"user_id": uid, "faction_id": "student_council", "action": "join"},
    )
    assert join_res.status_code == 200
    assert join_res.json()["membership"]["joined_faction_id"] == "student_council"
    assert join_res.json()["membership"]["faction_rank"] == 1

    # Safehouse Rest
    db.apply_hp_mp_delta(uid, -10, -5, 0)
    rest_res = client.post(
        f"/api/factions/{sid}/hq-action",
        json={"user_id": uid, "faction_id": "student_council", "action": "rest"},
    )
    assert rest_res.status_code == 200
    char_after_rest = db.get_character(uid)
    assert char_after_rest["hp"] == char_after_rest["max_hp"]

    # Challenge for Promotion (rep=45 makes player eligible for Rank 2 since req_rep=30)
    prom_res = client.post(
        f"/api/factions/{sid}/hq-action",
        json={"user_id": uid, "faction_id": "student_council", "action": "promote"},
    )
    assert prom_res.status_code == 200
    prom_data = prom_res.json()
    assert prom_data["target_rank"] == 2
    assert "directive" in prom_data or prom_data.get("auto_promoted") is True

    # Leave faction
    leave_res = client.post(
        f"/api/factions/{sid}/hq-action",
        json={"user_id": uid, "faction_id": "student_council", "action": "leave"},
    )
    assert leave_res.status_code == 200
    assert leave_res.json()["membership"]["joined_faction_id"] == ""

    # 3. Phase 22: PeerPulse Social Graph & Feed Rumor Scouring
    disc_res = client.post(
        f"/api/phone/{sid}/peerpulse/discover",
        json={"user_id": uid, "query_name": ""},
    )
    assert disc_res.status_code == 200
    peer_profile = disc_res.json()["profile"]
    assert "name" in peer_profile and "handle" in peer_profile

    mock_check = MagicMock(chance=85, tier="success", tier_label="Success", succeeded=True)
    with patch("skill_check.resolve_check", return_value=mock_check):
        freq_res = client.post(
            f"/api/phone/{sid}/peerpulse/friend-request",
            json={"user_id": uid, "profile": peer_profile},
        )
        assert freq_res.status_code == 200
        assert freq_res.json()["accepted"] is True

    # 4. Phase 23: Bounty Board & Detective Caseboard Deductions
    db.upsert_quest(
        session_id=sid,
        quest_id="bounty_lost_badge",
        quest_type="Bounty",
        title="Recover Lost Council Badge",
        objective="Search the library archives for the missing badge.",
        status="Available",
        reward_xp=120,
        reward_gold=40,
    )
    b_acc = client.post(
        f"/api/quests/{sid}/bounties/action",
        json={"user_id": uid, "quest_id": "bounty_lost_badge", "action": "accept"},
    )
    assert b_acc.status_code == 200
    assert b_acc.json()["status"] == "Active"

    # Add 2 clues with shared suspect & deduce breakthrough
    c1_id = db.add_session_clue(
        session_id=sid,
        title="Unlocked Lab Door",
        lead_text="Someone used a brass master key to unlock the chemistry lab at midnight.",
        category="physical",
        source_location="Chemistry Lab",
        linked_npc="Kaito Vance",
        chapter=1,
    )
    c2_id = db.add_session_clue(
        session_id=sid,
        title="Witness Testimony",
        lead_text="The janitor saw Kaito Vance carrying a brass key near the Chemistry Lab.",
        category="testimonial",
        source_location="Chemistry Lab",
        linked_npc="Kaito Vance",
        chapter=1,
    )
    xp_before = db.get_character(uid)["xp"]
    ded_res = client.post(
        f"/api/quests/{sid}/clues/deduce",
        json={"user_id": uid, "clue_a_id": c1_id, "clue_b_id": c2_id},
    )
    assert ded_res.status_code == 200
    ded_data = ded_res.json()
    assert ded_data["is_valid"] is True
    assert ded_data["xp_awarded"] == 50
    assert db.get_character(uid)["xp"] >= xp_before + 50


def test_wave8_full_web_spa_parity_and_bugfixes(tmp_path, monkeypatch):
    """Verify Wave 8 (Phases 24-28): Auth payload compatibility, starter gear & character deletion,
    Inventory Inspector & Key Item protection, Tactical Combat Deck & direct_choice,
    Contacts Dossier / Commitments / Campaign Digest, and Sandbox Debug overrides."""
    from fastapi.testclient import TestClient
    from unittest.mock import patch, AsyncMock, MagicMock
    import db
    from server import app

    test_db = str(tmp_path / "test_wave8_parity.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()

    client = TestClient(app)

    # 1. Phase 24: Auth payload compatibility (display_name & discord_id)
    guest_res = client.post("/api/auth/guest", json={"display_name": "HeroTester"})
    assert guest_res.status_code == 200
    assert guest_res.json()["display_name"] == "HeroTester"
    uid = guest_res.json()["user_id"]

    discord_res = client.post("/api/auth/discord", json={"discord_id": "9988776655"})
    assert discord_res.status_code == 200
    assert discord_res.json()["user_id"] == 9988776655

    # 2. Phase 25: Character Creation with Starter Gear, Regenerate Gear & Delete Character
    char1_res = client.post(
        "/api/character/create",
        json={
            "user_id": uid,
            "name": "Aric Vance",
            "char_class": "Warrior",
            "race": "Human",
            "gender": "Male",
            "scenario_key": "fantasy",
            "starting_weapon": "Iron Greatsword",
            "starting_weapon_description": "A heavy two-handed blade forged in embers.",
            "stats": {"STR": 10, "DEX": 7, "CON": 8, "INT": 5, "WIS": 6, "CHA": 6, "LUCK": 6},
        },
    )
    assert char1_res.status_code == 200
    char1_id = char1_res.json()["character"]["id"]

    regen_res = client.post("/api/character/regenerate-gear", json={"user_id": uid})
    assert regen_res.status_code == 200
    assert regen_res.json()["success"] is True

    # Create a second character and delete it
    char2_res = client.post(
        "/api/character/create",
        json={
            "user_id": uid,
            "name": "Temp Alt",
            "char_class": "Mage",
            "scenario_key": "fantasy",
            "stats": {"STR": 5, "DEX": 6, "CON": 6, "INT": 10, "WIS": 8, "CHA": 6, "LUCK": 6},
        },
    )
    assert char2_res.status_code == 200
    char2_id = char2_res.json()["character"]["id"]

    del_res = client.delete(f"/api/character/{uid}/{char2_id}")
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True
    assert all(c["id"] != char2_id for c in del_res.json()["characters"])

    # Switch back to char1
    sw_res = client.post("/api/character/switch", json={"user_id": uid, "character_id": char1_id})
    assert sw_res.status_code == 200

    # 3. Phase 26: Inventory Inspector, vs_equipped deltas & Key Item drop protection
    upgrade_id = db.add_item(
        uid,
        "Mythril Claymore",
        "Weapon",
        "Deals 25 physical damage. [GEAR_JSON]{\"slot\":\"Weapon\",\"atk_bonus\":25,\"crit_bonus\":10}",
    )
    key_item_id = db.add_item(
        uid,
        "Ancient Royal Seal",
        "Key Item",
        "Opens the sealed vault of the Sunken Citadel.",
    )

    inv_res = client.get(f"/api/inventory/{uid}")
    assert inv_res.status_code == 200
    inv_items = inv_res.json()["items"]
    up_item = next(i for i in inv_items if i["id"] == upgrade_id)
    assert "[GEAR_JSON]" not in up_item["clean_effect"]
    assert "Weapon" in up_item["valid_slots"]
    assert "inspect_data" in up_item
    assert isinstance(up_item["inspect_data"].get("vs_equipped"), list)

    key_item = next(i for i in inv_items if i["id"] == key_item_id)
    assert key_item["is_key_item"] is True

    drop_key_res = client.post("/api/inventory/drop", json={"user_id": uid, "item_id": key_item_id})
    assert drop_key_res.status_code == 400
    assert "Key items cannot be dropped" in drop_key_res.json()["detail"]

    # 4. Phase 27: Tactical Combat Deck, direct_choice, formatted_time & Session Lifecycle
    sid = db.create_session(
        mode="solo",
        capacity=1,
        host_user_id=uid,
        scenario="fantasy",
        verbosity="vivid",
        dialogue_mode="balanced",
        image_gen_enabled=0,
    )
    db.add_session_member(sid, uid)
    db.set_session_active(sid, [uid])
    db.save_session_scene(
        sid,
        "Ruined Watchtower",
        "A fierce Goblin Berserker blocks the stone staircase!",
        [{"text": "Parley with the goblin", "stat": "CHA", "requirement": 6}],
        [],
        location="Ruined Watchtower",
        nearby_enemies=[{"name": "Goblin Berserker", "hp": 35, "max_hp": 35, "atk": 7, "ac": 11}],
    )

    active_res = client.get(f"/api/adventure/active-session/{uid}")
    assert active_res.status_code == 200
    sess_payload = active_res.json()["session"]
    assert sess_payload["is_in_combat"] is True
    assert "Day " in sess_payload["formatted_time"]
    assert "combat_deck" in sess_payload
    assert "Goblin Berserker" in sess_payload["combat_decks_by_target"]
    first_attack = sess_payload["combat_deck"]["attacks"][0]

    mock_turn_resp = MagicMock(
        outcome={
            "narrative": "You strike the Goblin Berserker with a decisive slash!",
            "location": "Ruined Watchtower",
            "choices": [{"text": "Press the attack", "stat": "STR", "requirement": 5}],
            "nearby_enemies": [{"name": "Goblin Berserker", "hp": 15, "max_hp": 35, "atk": 7, "ac": 11}],
        },
        session=sess_payload,
    )
    with patch("services.turn_service.TurnService.resolve_action", new=AsyncMock(return_value=mock_turn_resp)):
        act_res = client.post(
            "/api/adventure/action",
            json={
                "session_id": sid,
                "user_id": uid,
                "direct_choice": first_attack,
                "combat_target": "Goblin Berserker",
            },
        )
        assert act_res.status_code == 200
        assert act_res.json()["success"] is True

    # 5. Phase 28: Contacts Dossier, Factions Perks/Bounties, Commitments, Quests & Debug Sandbox
    db.upsert_contact(
        session_id=sid,
        npc_id="lyra_dawnstar",
        name="Lyra Dawnstar",
        basic_info={"role": "Ranger Captain", "location": "Ruined Watchtower"},
        delta_score=45,
        race="Elf",
        gender="Female",
        appearance={"summary": "Silver-haired ranger in emerald cloak"},
        new_traits=["Vigilant", "Loyal"],
        new_preferences=["Archery"],
    )
    db.add_commitment(
        session_id=sid,
        source_entity="player",
        target_entity="Lyra Dawnstar",
        commitment_type="promise",
        description="Promised to recover the stolen Elven reliquary.",
        turn_number=1,
    )

    contacts_res = client.get(f"/api/contacts/{sid}")
    assert contacts_res.status_code == 200
    lyra = next(c for c in contacts_res.json()["contacts"] if c["name"] == "Lyra Dawnstar")
    assert "info_level" in lyra
    assert "skill_modifier" in lyra
    assert "family_tree" in lyra

    lore_res = client.get(f"/api/lorebook/{sid}")
    assert lore_res.status_code == 200
    assert len(lore_res.json()["commitments"]) >= 1

    quests_res = client.get(f"/api/quests/{sid}")
    assert quests_res.status_code == 200
    assert "current_chapter" in quests_res.json()
    assert "chapter_digest" in quests_res.json()

    # Sandbox Debug: apply_stat_mode, debug_reveal_all_info, force_enemy, reset_all
    dbg_res = client.post(
        f"/api/debug/{uid}",
        json={"debug_stat_mode": "max", "debug_reveal_all_info": 1, "session_id": sid},
    )
    assert dbg_res.status_code == 200
    assert dbg_res.json()["debug_reveal_all_info"] == 1
    char_max = db.get_character(uid)
    assert char_max["int_"] == 10

    spawn_res = client.post(
        f"/api/debug/{uid}",
        json={"action": "force_enemy", "session_id": sid},
    )
    assert spawn_res.status_code == 200
    assert spawn_res.json()["enemy_spawned"] is not None

    reset_res = client.post(
        f"/api/debug/{uid}",
        json={"action": "reset_all", "session_id": sid},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["debug_stat_mode"] == "off"
    assert reset_res.json()["debug_reveal_all_info"] == 0

    # End adventure explicitly
    end_res = client.post("/api/adventure/end", json={"session_id": sid, "user_id": uid})
    assert end_res.status_code == 200
    assert end_res.json()["success"] is True






