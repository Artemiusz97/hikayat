import asyncio
import db
import game_engine
from game_engine.state.core import resolve_pre_turn_vitals_and_resources
from game_engine.state.social import resolve_pre_turn_social_and_disclosures
from game_engine.state.reducers import (
    _reduce_factions,
    _reduce_entities_and_gifts,
    _reduce_media_capture,
)
from game_engine.npcs.stage_manager import compute_pre_turn_stage
from game_engine.turn.generation import (
    _fast_path_classify_ambient_action,
    extract_deterministic_recall_query,
)
from mechanics.system.memory.digest import build_deterministic_arc_digest, generate_arc_digest


def test_pillar1_and_pillar3_pre_turn_factions_promotions_and_immediate_commitments():
    """Verify that faction promotions, Friend milestone faction endorsements, direct faction actions,
    and new player promises resolve deterministically pre-turn in resolve_pre_turn_social_and_disclosures."""
    db.init_db()
    session_id = 99101
    user_id = 99101
    with db.get_conn() as conn:
        conn.execute("DELETE FROM commitments_ledger WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM factions WHERE session_id=?", (session_id,))
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'fantasy', 'Guildhall ➔ Main Hall')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Alden', 'Warrior', 'Human', 'M', 30, 30, 15, 15, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )

    char = db.get_character(user_id)
    char_id = char["id"]

    # Seed contact at 29 Affinity affiliated with 'Silver Vanguard'
    db.upsert_contact(
        session_id=session_id,
        npc_id="captain_voss",
        name="Captain Voss",
        character_id=char_id,
        delta_score=29,
        track="platonic",
        basic_info={"role": "Captain", "faction": "Silver Vanguard"},
    )
    db.upsert_faction(
        session_id=session_id,
        name="Silver Vanguard",
        delta_score=35,
        hierarchy_template="guild",
    )
    db.upsert_faction(
        session_id=session_id,
        name="Shadow Syndicate",
        delta_score=0,
        hierarchy_template="criminal",
    )

    session = {
        "id": session_id,
        "scenario": "fantasy",
        "current_location": "Guildhall ➔ Main Hall",
        "dialogue_partner": "Captain Voss",
        "dialogue_partners": ["Captain Voss"],
        "current_npcs": [{"name": "Captain Voss", "role": "Captain"}],
        "pending_promotion": {
            "faction_id": "Silver Vanguard",
            "target_rank": 1,
            "player_name": "Alden",
            "template": "guild",
        },
        "history": [],
    }
    actions = [{
        "label": "I promise to defend the northern outpost and sabotage Shadow Syndicate supply lines",
        "stat": "CHA",
        "requirement": 8,
        "check": {"succeeded": True, "tier": "success"},
    }]

    pre_soc = resolve_pre_turn_social_and_disclosures(
        session, [(char, [])], actions, new_dialogue_partners=["Captain Voss"]
    )

    # 1. Verify pending faction promotion trial succeeded pre-turn
    assert pre_soc["faction_promotion_result"] == "success"
    assert any("[MANDATORY FACTION PROMOTION COMPLETE]" in d for d in pre_soc["directives"])

    # 2. Verify Friend milestone endorsement (+5 Rep with Silver Vanguard) AND direct sabotage (-5 Rep with Shadow Syndicate)
    assert any(
        fu.get("faction_name") == "Silver Vanguard" and fu.get("delta_score") == 5
        for fu in pre_soc["faction_updates"]
    )
    assert any(
        fu.get("faction_name") == "Shadow Syndicate" and fu.get("delta_score") == -5
        for fu in pre_soc["faction_updates"]
    )

    # 3. Verify immediate commitment creation in SQLite commitments_ledger
    assert len(pre_soc["created_commitments"]) == 1
    from db.memory import get_active_commitments
    active_commits = get_active_commitments(session_id)
    assert len(active_commits) == 1
    assert active_commits[0]["target_entity"] == "Captain Voss"
    assert active_commits[0]["commitment_type"] == "promise"

    # 4. Verify _reduce_factions applies the pre-turn faction updates & promotion without duplicating endorsement
    outcome = {
        "relationship_updates": [{"npc_name": "Captain Voss", "delta_score": pre_soc["affinity_deltas"]["Captain Voss"], "_pre_turn_resolved": True}],
        "faction_updates": list(pre_soc["faction_updates"]),
        "faction_promotion_result": pre_soc["faction_promotion_result"],
    }
    _reduce_factions(session_id, session, outcome, [(char, [])], char_id)
    fac_row = db.get_faction(session_id, "Silver Vanguard")
    assert fac_row["reputation_score"] == 40  # 35 + 5 once (not 45)
    syn_row = db.get_faction(session_id, "Shadow Syndicate")
    assert syn_row["reputation_score"] == -5


def test_pillar2_pre_turn_gift_media_and_prop_pickup():
    """Verify Gift Offer, Smartphone Media Capture, and Scene Prop pickup resolve pre-turn
    and do not double-execute in post-turn reducers."""
    db.init_db()
    session_id = 99102
    user_id = 99102
    with db.get_conn() as conn:
        conn.execute("DELETE FROM inventory WHERE user_id=?", (user_id,))
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'high_school', 'Campus ➔ Courtyard')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Ren', 'Student', 'Human', 'M', 30, 30, 15, 15, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )

    db.add_item(user_id, "Strawberry Tart", "Consumable", "Sweet pastry", 1)
    char = db.get_character(user_id)
    inv = db.get_inventory(user_id)

    session = {
        "id": session_id,
        "scenario": "high_school",
        "current_location": "Campus ➔ Courtyard",
        "dialogue_partner": "Elena Vance",
        "current_npcs": [{"name": "Elena Vance", "role": "Classmate"}],
        "physical_state": {"props": {"Brass Pocketwatch": "Resting on the bench"}, "dropped_items": []},
    }

    # A. Gift offer + prop pickup
    actions_gift = [
        {"user_id": user_id, "label": "Give the Strawberry Tart to Elena Vance", "stat": "CHA", "check": {"succeeded": True, "tier": "success"}},
        {"user_id": user_id, "label": "Pick up the Brass Pocketwatch from the bench", "stat": "FREE", "check": {"succeeded": True, "tier": "success"}},
    ]
    pre_v = resolve_pre_turn_vitals_and_resources(session, [(char, inv)], actions_gift)
    assert len(pre_v["gifted_items"]) == 1
    assert pre_v["gifted_items"][0]["item_name"] == "Strawberry Tart"
    assert "Brass Pocketwatch" in pre_v["loot_items_rolled"]

    # B. Smartphone media capture
    actions_photo = [
        {"user_id": user_id, "label": "Take a photo of Elena Vance by the cherry blossoms", "stat": "PER", "check": {"succeeded": True, "tier": "success"}},
    ]
    pre_v_photo = resolve_pre_turn_vitals_and_resources(session, [(char, inv)], actions_photo)
    assert len(pre_v_photo["media_captured"]) == 1
    assert pre_v_photo["media_captured"][0]["subject"] == "Elena Vance"

    outcome = {
        "outcome_narrative": "Ren snaps a vivid photo of Elena Vance smiling under the blossoms.",
        "_pre_turn_gifted": pre_v["gifted_items"],
        "_pre_turn_media_captured": pre_v_photo["media_captured"],
    }
    items_gained_by_user = {}
    _reduce_entities_and_gifts(session_id, session, outcome, [(char, inv)], actions_gift, False, "high_school")
    _reduce_media_capture(session_id, session, [(char, inv)], outcome, actions_photo, "high_school", items_gained_by_user)

    # Strawberry Tart consumed once, Photo added once
    rem_inv = db.get_inventory(user_id)
    assert not any(it["name"] == "Strawberry Tart" for it in rem_inv)
    assert any("Photo: Elena Vance" in s for s in items_gained_by_user.get(user_id, []))


def test_pillar4_pure_deterministic_tier2_digest():
    """Verify build_deterministic_arc_digest and generate_arc_digest produce [EVENT], [RESOURCE],
    and [HOOK] bullets from structured turn history dicts with zero LLM calls."""
    db.init_db()
    session_id = 99103
    with db.get_conn() as conn:
        conn.execute("DELETE FROM session_digests WHERE session_id=?", (session_id,))
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location, chapter_digest_json) "
            "VALUES (?, 99103, 'active', 'single', 1, 'fantasy', 'Sunfall Citadel', '[]')",
            (session_id,),
        )

    structured_history = [
        {
            "character_name": "Alden",
            "label": "Search the smugglers' crate",
            "location": "Docklands ➔ Warehouse 4",
            "outcome_narrative": "Alden pried open the damp crate and uncovered a ciphered manifest.",
            "items_gained": ["Ciphered Manifest"],
            "character_outcomes": [{"name": "Alden", "gold_change": 45, "items_lost": []}],
            "relationship_updates": [{"npc_name": "Elena", "delta_score": 5}],
            "quest_updates": [{"title": "Harbor Conspiracy", "status": "Active", "current_clues": "The manifest points to Pier 9 at midnight."}],
        }
    ]

    digest_dict = build_deterministic_arc_digest(structured_history)
    assert len(digest_dict["key_events"]) == 1
    assert "Warehouse 4" in digest_dict["key_events"][0]
    assert "Gained: Ciphered Manifest" in digest_dict["mechanical_summary"]
    assert "Gold: +45" in digest_dict["mechanical_summary"]
    assert "Affinity (Elena): +5" in digest_dict["mechanical_summary"]
    assert any("Pier 9" in h for h in digest_dict["active_hooks"])

    bullets, _ = asyncio.run(generate_arc_digest(session_id, structured_history, turn_start=0))
    assert any(b.startswith("[RESOURCE] Gained: Ciphered Manifest") for b in bullets)
    assert any(b.startswith("[HOOK] Harbor Conspiracy:") for b in bullets)


def test_pillar5_6_8_expanded_fast_path_role_spawning_and_active_recall():
    """Verify expanded fast-path classification (dialogue, loot search, combat attack),
    deterministic active recall detection, and pre-turn canonical role spawning on freeform approach."""
    db.init_db()
    session_id = 99104
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location, chapter_digest_json) "
            "VALUES (?, 99104, 'active', 'single', 1, 'fantasy', 'Silverhaven ➔ Tavern ➔ Main Area', '[]')",
            (session_id,),
        )

    # Seed a digest bullet so active_recall_search finds it
    from db.memory import append_chapter_digest
    append_chapter_digest(session_id, 0, 1, ["The bartender mentioned the crimson key is hidden beneath the old mill."])

    session = {
        "id": session_id,
        "scenario": "fantasy",
        "current_location": "Silverhaven ➔ Tavern ➔ Main Area",
        "current_npcs": [],
    }

    # 1. Fast-path DIALOGUE_INIT + deterministic role extraction + deterministic memory recall
    res_dlg = _fast_path_classify_ambient_action(
        "Talk to the bartender and recall the crimson key",
        session=session,
    )
    assert res_dlg is not None
    assert res_dlg["fast_path"] is True
    assert res_dlg["action_category"] == "dialogue"
    assert res_dlg["spawns_npc_role"] == "bartender"
    assert res_dlg.get("is_memory_recall") is True
    assert any("crimson key" in r for r in res_dlg.get("_active_recall", []))

    # 2. Fast-path LOOT_SEARCH
    res_loot = _fast_path_classify_ambient_action("Search the wooden chest for loot", session=session)
    assert res_loot is not None
    assert res_loot["fast_path"] is True
    assert res_loot["triggers_loot_roll"] is True
    assert res_loot["stat"] == "PER"

    # 3. Fast-path COMBAT_ATTACK
    res_atk = _fast_path_classify_ambient_action("Attack Goblin Scout with my sword", session=session)
    assert res_atk is not None
    assert res_atk["fast_path"] is True
    assert res_atk["action_category"] == "combat_attack"
    assert res_atk["combat_target"] == "Goblin Scout"

    # 4. Pre-turn canonical role spawning in compute_pre_turn_stage even without explicit spawns_npc_role
    stage_res = compute_pre_turn_stage(
        session,
        actions=[{"label": "Approach the bartender for rumors"}],
    )
    assert len(stage_res["spawned_role_npcs"]) == 1
    assert stage_res["spawned_role_npcs"][0]["role"] == "Bartender"
    assert any("CANONICAL ROLE ENCOUNTER" in d for d in stage_res["stage_directives"])


def test_phase6_part2_checkup_edge_cases():
    """Verify edge-case guards added during Phase 6 (Part 2) checkup:
    1. Promotion trial setup turn does not auto-succeed, and failed trial clears pending_promotion.
    2. Scene prop pickup removes the prop from physical_state so it cannot be infinitely duplicated,
       and _gold_already_deducted prevents double gold deduction.
    3. extract_deterministic_recall_query matches active commitments when session_id is passed.
    """
    db.init_db()
    session_id = 99105
    user_id = 99105
    with db.get_conn() as conn:
        conn.execute("DELETE FROM commitments_ledger WHERE session_id=?", (session_id,))
        conn.execute(
            "INSERT OR REPLACE INTO sessions (id, host_user_id, status, mode, capacity, scenario, current_location) "
            "VALUES (?, ?, 'active', 'single', 1, 'fantasy', 'Guildhall ➔ Arena')",
            (session_id, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO characters (user_id, name, char_class, race, gender, hp, max_hp, mp, max_mp, gold, str_, agi, end_, int_, per_, cha, luk, active_session_id) "
            "VALUES (?, 'Alden', 'Warrior', 'Human', 'M', 30, 30, 15, 15, 100, 6, 6, 6, 6, 6, 6, 5, ?)",
            (user_id, session_id),
        )
    char = db.get_character(user_id)
    char_id = char["id"]

    # 1. Setup turn for promotion trial must NOT prematurely resolve faction_promotion_result
    session = {
        "id": session_id,
        "scenario": "fantasy",
        "current_location": "Guildhall ➔ Arena",
        "pending_promotion": {
            "faction_id": "Silver Vanguard",
            "target_rank": 1,
            "player_name": "Alden",
            "template": "guild",
        },
    }
    setup_action = [{
        "label": "Player initiates promotion trial:\n\n[FACTION PROMOTION TRIAL DIRECTIVE]: Present the trial.",
        "stat": "NONE",
    }]
    pre_setup = resolve_pre_turn_social_and_disclosures(session, [(char, [])], setup_action)
    assert pre_setup["faction_promotion_result"] == ""

    # Failed trial must resolve to 'failed' and clear pending_promotion in _reduce_factions
    fail_action = [{
        "label": "Attempt the grandmaster's tactical examination",
        "stat": "INT",
        "requirement": 12,
        "check": {"succeeded": False, "tier": "fail"},
    }]
    pre_fail = resolve_pre_turn_social_and_disclosures(session, [(char, [])], fail_action)
    assert pre_fail["faction_promotion_result"] == "failed"
    _reduce_factions(session_id, session, {"faction_promotion_result": "failed"}, [(char, [])], char_id)
    assert session.get("pending_promotion") is None

    # 2. Prop removal on pickup & _gold_already_deducted guard
    session["physical_state"] = {"props": {"Ancient Signet Ring": "On the stone pedestal"}, "dropped_items": []}
    pickup_and_gold_actions = [
        {"user_id": user_id, "label": "Take the Ancient Signet Ring from the pedestal", "stat": "FREE", "check": {"succeeded": True, "tier": "success"}},
        {"user_id": user_id, "label": "Pay 25 gold to the ferryman", "stat": "NONE", "gold_spent": 25, "_gold_already_deducted": True, "check": {"succeeded": True, "tier": "success"}},
    ]
    pre_v = resolve_pre_turn_vitals_and_resources(session, [(char, [])], pickup_and_gold_actions)
    assert "Ancient Signet Ring" in pre_v["loot_items_rolled"]
    assert "Ancient Signet Ring" not in session["physical_state"]["props"]
    # Second pickup attempt for the same prop must not duplicate it
    pre_v2 = resolve_pre_turn_vitals_and_resources(session, [(char, [])], pickup_and_gold_actions[:1])
    assert "Ancient Signet Ring" not in pre_v2["loot_items_rolled"]
    # Gold delta in character_outcomes must be 0 when _gold_already_deducted is True, while still emitting stage directive
    assert any("spent 25 Gold" in d for d in pre_v["stage_directives"])
    assert all(co.get("gold_change", 0) == 0 for co in pre_v["character_outcomes"])

    # 3. Commitment-based deterministic recall query
    from db.memory import add_commitment
    add_commitment(session_id, "Player", "Captain Voss", "promise", "Player promised to defend the northern outpost", turn_number=1)
    q = extract_deterministic_recall_query("Talk to Captain Voss about the northern outpost", session_id=session_id)
    assert "Captain Voss" in q and "northern outpost" in q

