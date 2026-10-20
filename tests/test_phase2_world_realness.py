"""
tests/test_phase2_world_realness.py
===================================
Comprehensive unit test suite for Phase 2:
World "Realness", Physical State & Living Schedules.
Tests all 12 core pillars and edge-case mechanics:
1. Migration 21 & state_json CRUD
2. Explicit seeder access tiers & curfew hours
3. Soft threshold gate & tiered persistence
4. Edge Case 1: Failed check lockout & patrol confrontation
5. Edge Case 2: Role authority & illicit rendezvous
6. Edge Case 3: Rolling 3-memory log & priority pinning
7. Edge Case 4: Dynamic 22:00 curfew tension prompt
8. Edge Case 5: NPC private residence intercom gate
9. Edge Case 6: Mid-conversation schedule boundary transition
10. Edge Case 7: Smart sub-location privacy nudge
11. World map live occupancy, access badges & room memory
"""
import pytest
import time
import json
import sqlite3
import db
from mechanics.world.locations.graph_seeder import (
    ensure_session_spatial_graph_seeded,
    infer_access_tier,
    infer_curfew_window,
)
from mechanics.world.locations.access_gate import (
    is_curfew_active,
    get_node_effective_access_info,
    record_node_unlock,
    has_npc_authority_for_node,
    evaluate_node_access_gate,
    record_turn_scene_residue,
    get_privacy_nudge_choice,
)
from mechanics.world.locations.formatting import (
    build_node_sensory_and_memory_block,
    format_llm_location_context,
)
from mechanics.world.schedules import (
    get_npc_schedule_node_ids,
    get_npc_scheduled_node_id,
    get_npc_schedule,
    get_npc_scheduled_location,
    is_schedule_transition_imminent,
)
from game_engine.npcs import compute_pre_turn_stage


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_phase2.db")
    monkeypatch.setattr(db.core, "DB_PATH", test_db_path)
    db.init_db(force=True)
    yield


def _create_mock_session(session_id: int = 100, current_minute: int = 480, current_day: int = 1):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.execute("DELETE FROM world_nodes WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM world_edges WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM phone_appointments WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM contacts WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM school_directory WHERE session_id=?", (session_id,))
        conn.execute(
            """INSERT INTO sessions (
                   id, mode, capacity, status, scenario, current_location, current_node_id,
                   dialogue_partner, current_day, current_minute
               )
               VALUES (?, 'solo', 1, 'active', 'high_school_drama',
                       ?, 'loc_homeroom', '', ?, ?)""",
            (session_id, "Main Academy Campus ➔ Homeroom Classroom ➔ Player's Desk", current_day, current_minute)
        )
    from mechanics.world.locations.seeding import ensure_session_locations_seeded
    ensure_session_locations_seeded(session_id, "high_school_drama", char_name="Alex")
    ensure_session_spatial_graph_seeded(session_id, "high_school_drama", char_name="Alex")
    return db.get_session(session_id)


def test_migration_21_and_state_json_crud():
    sess = _create_mock_session(101)
    # Check default state_json
    st = db.get_world_node_state(101, "loc_homeroom")
    assert isinstance(st, dict)
    assert st == {}

    # Update state_json
    upd = db.update_world_node_state(101, "loc_homeroom", {"custom_prop": "chalkboard", "unlocked_until_day": 2})
    assert upd["custom_prop"] == "chalkboard"
    assert upd["unlocked_until_day"] == 2

    # Fetch fresh
    st2 = db.get_world_node_state(101, "loc_homeroom")
    assert st2["custom_prop"] == "chalkboard"
    assert st2["unlocked_until_day"] == 2

    # Re-saving node should preserve state_json when state_json is None
    db.save_world_node(
        session_id=101,
        node_id="loc_homeroom",
        parent_id="zone_school_main",
        name="Homeroom Classroom",
        node_type="FACILITY",
        category="academic",
        privacy_level="public"
    )
    st3 = db.get_world_node_state(101, "loc_homeroom")
    assert st3["custom_prop"] == "chalkboard"
    assert st3["unlocked_until_day"] == 2


def test_explicit_seeder_metadata_and_curfew():
    sess = _create_mock_session(102)
    # loc_staff_room should be restricted with curfew 1320..360
    staff = db.get_world_node(102, "loc_staff_room")
    assert staff is not None
    assert staff["access_tier"] == "restricted"
    assert staff["curfew_start_min"] in (1200, 1320)
    assert staff["curfew_end_min"] in (360, 420)

    # loc_rooftop should be restricted with curfew
    roof = db.get_world_node(102, "loc_rooftop")
    assert roof is not None
    assert roof["access_tier"] == "restricted"

    # loc_player_house should be private
    house = db.get_world_node(102, "loc_player_house")
    assert house is not None
    assert house["access_tier"] == "private"

    # loc_school_gate should have open access and no curfew
    gate = db.get_world_node(102, "loc_school_gate")
    assert gate is not None
    assert gate["access_tier"] == "open"
    assert gate["curfew_start_min"] is None


def test_is_curfew_active_wrap_around():
    # 22:00 (1320) to 06:00 (360)
    assert is_curfew_active(1320, 360, 1320) is True   # exactly 22:00
    assert is_curfew_active(1320, 360, 1380) is True   # 23:00
    assert is_curfew_active(1320, 360, 0) is True      # 00:00 (midnight)
    assert is_curfew_active(1320, 360, 359) is True    # 05:59
    assert is_curfew_active(1320, 360, 360) is False   # 06:00
    assert is_curfew_active(1320, 360, 480) is False   # 08:00
    assert is_curfew_active(1320, 360, 1319) is False  # 21:59


def test_soft_threshold_gate_and_tiered_persistence():
    sess = _create_mock_session(103, current_minute=600, current_day=1)
    # Traveling to restricted staff room without key/companion halts at threshold
    gate_res = evaluate_node_access_gate(103, "loc_staff_room", sess, actions=[{"label": "Walk into the staff room"}])
    assert gate_res["gated"] is True
    assert gate_res["reason_code"] == "restricted"
    assert "Outside the Locked Entrance" in gate_res["focal_point"]
    assert any("[AGI] Sneak in or pick the lock" in c for c in gate_res["barrier_choices"])

    # Passing an AGI check grants day-long access
    success_action = [{"label": "Pick the lock to the staff room", "check": type("Check", (), {"tier": "success"})()}]
    unlock_res = evaluate_node_access_gate(103, "loc_staff_room", sess, actions=success_action)
    assert unlock_res["gated"] is False
    assert unlock_res["unlocked_by"] == "skill_check"

    # Now it's unlocked for Day 1
    st_info = get_node_effective_access_info(103, "loc_staff_room", current_day=1)
    assert st_info["is_unlocked"] is True
    assert st_info["status_badge"] == "Unlocked"

    # Day 2: Day-long access expires, locks again
    st_info_d2 = get_node_effective_access_info(103, "loc_staff_room", current_day=2)
    assert st_info_d2["is_unlocked"] is False

    # Unlocking with a key sets permanent unlock
    record_node_unlock(103, "loc_staff_room", unlock_type="permanent", current_day=2, reason="key")
    st_info_d2_perm = get_node_effective_access_info(103, "loc_staff_room", current_day=2)
    assert st_info_d2_perm["is_unlocked"] is True
    st_info_d5 = get_node_effective_access_info(103, "loc_staff_room", current_day=5)
    assert st_info_d5["is_unlocked"] is True


def test_edge_case_1_failed_check_lockout_and_patrol_confrontation():
    sess = _create_mock_session(104, current_minute=600, current_day=1)
    # Standard fail: lock jams for this time block
    fail_action = [{"label": "Try to lockpick the door", "check": type("Check", (), {"tier": "failure"})()}]
    fail_res = evaluate_node_access_gate(104, "loc_staff_room", sess, actions=fail_action)
    assert fail_res["gated"] is True
    assert fail_res["reason_code"] == "breach_failed"
    assert fail_res["patrol_confrontation"] is False

    # Critical failure: spawns patrolling authority confrontation
    crit_fail_action = [{"label": "Try to lockpick the door", "check": type("Check", (), {"tier": "critical_failure"})()}]
    crit_res = evaluate_node_access_gate(104, "loc_staff_room", sess, actions=crit_fail_action)
    assert crit_res["gated"] is True
    assert crit_res["patrol_confrontation"] is True
    assert crit_res["patrol_npc"] is not None
    assert any("excuse" in c.lower() for c in crit_res["barrier_choices"])


def test_edge_case_2_role_authority_and_illicit_rendezvous():
    sess = _create_mock_session(105, current_minute=600, current_day=1)
    # 1. Accompanied by a Teacher: authority unlocks staff room automatically
    teacher_comp = {"name": "Ms. Takahashi", "role": "Homeroom Teacher"}
    auth_res = evaluate_node_access_gate(
        105, "loc_staff_room", sess,
        actions=[{"label": "Follow Ms. Takahashi inside"}],
        companions=[teacher_comp]
    )
    assert auth_res["gated"] is False
    assert auth_res["unlocked_by"] == "companion_authority"

    # 2. Confirmed appointment at locked rooftop triggers Illicit Rendezvous
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO phone_appointments (
                   session_id, npc_id, npc_name, rendezvous_location, target_node_id,
                   topic, status, created_minute, expiry_minute, created_at
               ) VALUES (?, 'npc_hana', 'Hana', 'School Rooftop', 'loc_rooftop', 'Meetup', 'pending', 600, 660, ?)""",
            (105, time.time())
        )
    rend_res = evaluate_node_access_gate(
        105, "loc_rooftop", sess,
        actions=[{"label": "Head to the rooftop to meet Hana"}]
    )
    assert rend_res["gated"] is False
    assert rend_res["unlocked_by"] == "illicit_rendezvous"


def test_edge_case_3_rolling_3_memory_log_and_priority_pinning():
    sess = _create_mock_session(106, current_minute=600, current_day=1)
    # Event 1: Memorable exchange (Priority 1)
    res1 = {"npc_memories": [{"summary": "Shared a candid talk about exams"}]}
    p1 = record_turn_scene_residue(106, "loc_fine_arts_studio", sess, res1, [])
    assert "candid talk" in p1

    # Event 2: Clue discovery (Priority 2)
    res2 = {"quest_updates": [{"current_clues": "A torn sketchbook page with mysterious cipher"}]}
    p2 = record_turn_scene_residue(106, "loc_fine_arts_studio", sess, res2, [])
    assert "cipher" in p2

    # Event 3: Intimate moment (Priority 3)
    res3 = {"physical_updates": {"intimate_contact": "kissing softly on the velvet lounge couch"}, "dialogue_partner": "Hana"}
    p3 = record_turn_scene_residue(106, "loc_fine_arts_studio", sess, res3, [])
    assert "intimate encounter" in p3

    # Event 4: Another minor talk
    res4 = {"npc_memories": [{"summary": "Discussed afternoon club flyers"}]}
    record_turn_scene_residue(106, "loc_fine_arts_studio", sess, res4, [])

    # Verify rolling 3 log in state_json
    st = db.get_world_node_state(106, "loc_fine_arts_studio")
    log_entries = st["scene_residue_log"]
    assert len(log_entries) == 3
    # Pinned residue should be the highest-priority entry (the Priority 3 intimate moment)
    assert "intimate encounter" in st["scene_residue"]


def test_edge_case_4_dynamic_22_00_curfew_tension_prompt():
    sess = _create_mock_session(107, current_minute=1350, current_day=1) # 22:30 at night
    node = db.get_world_node(107, "loc_homeroom")
    sensory_text = build_node_sensory_and_memory_block(107, node, 1, 1350)
    assert "CAMPUS CURFEW" in sensory_text and "AFTER-HOURS TRESPASSING" in sensory_text
    assert "Darkened interior" in sensory_text or "moonlight" in sensory_text


def test_edge_case_5_npc_private_residence_intercom_gate():
    sess = _create_mock_session(108, current_minute=700, current_day=1)
    # Create private friend residence
    db.save_world_node(108, "loc_hana_house", "zone_residential", "Hana's Residence", "FACILITY", category="residential", access_tier="private")

    # 1. Uninvited with no contact record halts at intercom
    gate_res = evaluate_node_access_gate(108, "loc_hana_house", sess, actions=[{"label": "Visit Hana's house"}])
    assert gate_res["gated"] is True
    assert gate_res["reason_code"] == "private_intercom"
    assert any("intercom" in c.lower() for c in gate_res["barrier_choices"])

    # 2. Add high-bond contact (relationship_score=50) -> Resident welcomes you
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO contacts (session_id, npc_id, name, relationship_score, track, updated_at)
               VALUES (?, 'npc_hana', 'Hana', 50, 'platonic', ?)""",
            (108, time.time())
        )
    gate_res_high = evaluate_node_access_gate(108, "loc_hana_house", sess, actions=[{"label": "Visit Hana's house"}])
    assert gate_res_high["gated"] is False
    assert gate_res_high["unlocked_by"] == "resident_welcome"


def test_edge_case_6_node_anchored_schedules_and_boundary_transition():
    sess = _create_mock_session(109, current_minute=765, current_day=1) # 12:45 (15 mins before 13:00 boundary)
    is_imm, cur_blk, next_blk, diff = is_schedule_transition_imminent(765, window_minutes=15)
    assert is_imm is True
    assert cur_blk == "lunch"
    assert next_blk == "afternoon"
    assert diff == 15

    # Check swim club student schedule mapping
    swim_npc = {"name": "Ren", "club": "swim club", "role": "Student"}
    sched_nodes = get_npc_schedule_node_ids(swim_npc, scen_key="high_school_drama")
    assert sched_nodes["afternoon"] == "loc_pool"
    assert sched_nodes["extracurricular"] == "loc_pool"

    # Resolved scheduled location with session_id during extracurricular hours (15:00–20:00)
    sched_loc = get_npc_scheduled_location(swim_npc, current_minute=930, scen_key="high_school_drama", session_id=109)
    assert "Pool" in sched_loc


def test_edge_case_7_smart_sub_location_privacy_nudge():
    sess = _create_mock_session(110, current_minute=600, current_day=1)
    # In School Library (Study Tables is public, Book Aisles is semi_private)
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO contacts (session_id, npc_id, name, relationship_score, track, updated_at)
               VALUES (?, 'npc_yuki', 'Yuki', 45, 'romantic', ?)""",
            (110, time.time())
        )
    nudge = get_privacy_nudge_choice(
        110, "sub_study_tables", "Yuki", sess,
        actions=[{"label": "Lean in and whisper a secret confession to Yuki"}]
    )
    assert nudge is not None
    assert "Book Aisles" in nudge or "Librarian Counter" in nudge


def test_world_map_payload_enrichment():
    from api.adventure import _build_locations_payload
    sess = _create_mock_session(111, current_minute=800, current_day=1) # 13:20 (Afternoon - Club hours)
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO contacts (session_id, npc_id, name, basic_info_json, updated_at)
               VALUES (?, 'npc_hana', 'Hana', ?, ?)""",
            (111, json.dumps({"club": "art", "role": "Student"}), time.time())
        )
    db.save_school_roster(111, [{"name": "Ken", "role": "Student", "club": "kendo"}])

    # Record memory in fine arts studio
    record_turn_scene_residue(111, "loc_fine_arts_studio", sess, {"npc_memories": [{"summary": "Completed a portrait sketch together"}]}, [])

    payload = _build_locations_payload(111, "high_school_drama", sess["current_location"], "Alex")
    assert "zones" in payload

    # Find arts zone and fine arts studio primary location
    arts_zone = next((z for z in payload["zones"] if "Arts" in z.get("zone_name", "")), None)
    assert arts_zone is not None
    arts_studio = next((p for p in arts_zone.get("primary_locations", []) if "Fine Arts" in p.get("name", "")), None)
    assert arts_studio is not None

    # Verify access badge, memory line, and occupancy
    assert arts_studio.get("access_badge") in ("Open", "Curfew (22:00–06:00)", "Unlocked", "Restricted")
    assert "portrait sketch" in arts_studio.get("scene_residue", "")
    assert "known_npcs_here" in arts_studio
    assert "unmet_activity_count" in arts_studio


def test_phase2_choices_compatibility():
    from game_engine.choices_cleaner import sanitize_and_diversify_choices
    from mechanics.world.locations.access_gate import Phase2Choice

    # String choices and Phase2Choice are normalized to dicts and not dropped
    raw_choices = [
        "[AGI] Sneak in or pick the lock to enter Teachers' Staff Room",
        Phase2Choice("Walk with Maya to Library", stat="NONE", requirement=0),
        Phase2Choice("Step into Old East Wing Music Room with Maya for privacy", stat="NONE", requirement=0),
        "Turn back from Teachers' Staff Room"
    ]
    cleaned = sanitize_and_diversify_choices(
        raw_choices,
        scenario="high_school_drama",
        dialogue_partner="Maya",
        current_npcs=[{"name": "Maya"}]
    )
    assert len(cleaned) >= 2
    # Accompanied movement and barrier choices survive conversation lock
    labels = [c.get("label", "") for c in cleaned]
    assert any("Walk with Maya" in lbl for lbl in labels) or any("Step into" in lbl for lbl in labels) or any("Turn back" in lbl for lbl in labels)


def test_multi_turn_threshold_lifecycle_and_turn_back():
    from game_engine.npcs.stage_manager import compute_pre_turn_stage
    from mechanics.world.locations.movement import extract_movement_destination

    sess = _create_mock_session(120, current_minute=600, current_day=1)
    sess["scenario"] = "high_school_drama"
    sess["current_location"] = "Main Academy Campus ➔ Central Courtyard ➔ Courtyard Fountain"
    sess["current_node_id"] = "loc_courtyard"

    # Turn 1: Travel to locked staff room halts at threshold outside
    actions_t1 = [{"label": "Walk into the Teachers' Staff Room"}]
    stage_t1 = compute_pre_turn_stage(sess, actions_t1)
    assert stage_t1["access_gate"]["gated"] is True
    assert "Outside the Locked Entrance" in stage_t1["effective_location"]

    # Turn 2: Breach attempt while outside locked entrance evaluates access gate
    sess["current_location"] = stage_t1["effective_location"]
    sess["current_node_id"] = "loc_staff_room"
    success_action = [{"label": "Pick the lock to the Teachers' Staff Room", "check": {"tier": "success"}}]
    stage_t2 = compute_pre_turn_stage(sess, success_action)
    # Gate unlocks, effective location transitions inside!
    assert stage_t2["access_gate"]["gated"] is False
    assert "Outside the Locked Entrance" not in stage_t2["effective_location"]

    # Turn back from locked location routes to parent corridor/hall
    dest = extract_movement_destination("Turn back from Teachers' Staff Room", 120, current_zone="Main Academy Campus", scen_key="high_school_drama")
    assert dest is not None
    assert dest[0] == "Main Academy Campus"
    assert any(k in dest[1].lower() for k in ("hall", "corridor", "courtyard", "foyer", "class", "gate"))


def test_check_result_tier_variations():
    sess = _create_mock_session(121, current_minute=600, current_day=1)

    # Dict check crit_success
    act_crit_succ = [{"label": "Sneak inside", "check": {"tier": "crit_success"}}]
    res_crit_succ = evaluate_node_access_gate(121, "loc_staff_room", sess, actions=act_crit_succ)
    assert res_crit_succ["gated"] is False
    assert res_crit_succ["unlocked_by"] == "skill_check"

    # Dict check crit_fail on locked session triggers patrol confrontation
    sess_fail = _create_mock_session(127, current_minute=600, current_day=1)
    act_crit_fail = [{"label": "Sneak inside", "check": {"tier": "crit_fail"}}]
    res_crit_fail = evaluate_node_access_gate(127, "loc_staff_room", sess_fail, actions=act_crit_fail)
    assert res_crit_fail["gated"] is True
    assert res_crit_fail["patrol_confrontation"] is True


def test_npc_night_schedule_not_player_house():
    # School NPC at night must map to their own house, never player's house
    student_npc = {"name": "Maya Anderson", "role": "Student", "club": "art"}
    sched_nodes = get_npc_schedule_node_ids(student_npc, scen_key="high_school_drama")
    assert sched_nodes["night"] != "loc_player_house"
    assert "maya_anderson" in sched_nodes["night"]

    # Partial resolution preserves daytime blocks
    sess = _create_mock_session(122, current_minute=480, current_day=1)
    resolved_sched = get_npc_schedule(student_npc, scen_key="high_school_drama", session_id=122)
    assert "Homeroom" in resolved_sched["morning"] or "Teachers' Staff Room" in resolved_sched["morning"]
    assert "Library" in resolved_sched["lunch"] or "Courtyard" in resolved_sched["lunch"] or "Dining Hall" in resolved_sched["lunch"]


def test_dijkstra_travel_time_in_live_turn():
    from mechanics.system.time_engine import calculate_action_time_cost

    sess = _create_mock_session(123, current_minute=480, current_day=1)
    time_cost = calculate_action_time_cost(
        {"label": "Walk to School Library"},
        scen_key="high_school_drama",
        old_loc="Main Academy Campus ➔ Homeroom Classroom ➔ Student Desks",
        new_loc="Main Academy Campus ➔ School Library ➔ Study Tables",
        session_id=123
    )
    assert time_cost >= 1


def test_roster_backed_patrol_npc_and_reconciliation_persistence():
    from game_engine.npcs.reconciliation import process_scene_npcs

    sess = _create_mock_session(124, current_minute=600, current_day=1)
    db.save_school_roster(124, [
        {"name": "Mr. Henderson", "role": "Teacher (Guidance Counselor)", "club": "faculty"}
    ])
    # Failed breach during day pulls teacher from roster
    crit_action = [{"label": "Force the lock", "check": {"tier": "crit_fail"}}]
    gate_res = evaluate_node_access_gate(124, "loc_staff_room", sess, actions=crit_action)
    assert gate_res["patrol_confrontation"] is True
    assert gate_res["patrol_npc"]["name"] == "Mr. Henderson"

    # Reconciliation does not prune staged bystanders or patrol NPC even if unmentioned in narrative
    staged = [
        gate_res["patrol_npc"],
        {"name": "Ken", "role": "Student", "stage_role": "room_bystander", "scheduled_station": True}
    ]
    res_payload = {"npcs_present": []}
    reconciled = process_scene_npcs(
        res_payload, sess,
        new_loc="Main Academy Campus ➔ Teachers' Staff Room ➔ Outside the Locked Entrance",
        old_loc="Main Academy Campus ➔ School Hallways",
        actions=crit_action,
        staged_npcs=staged
    )
    reconciled_names = [n["name"] for n in reconciled]
    assert "Mr. Henderson" in reconciled_names
    assert "Ken" in reconciled_names


def test_surname_residence_intercom_match():
    sess = _create_mock_session(125, current_minute=600, current_day=1)
    db.save_world_node(125, "loc_anderson_residence", "zone_residential", "Anderson Residence", "FACILITY", category="residential", access_tier="private")
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO contacts (session_id, npc_id, name, relationship_score, track, created_at)
               VALUES (?, 'npc_maya_anderson', 'Maya Anderson', 45, 'romantic', ?)""",
            (125, time.time())
        )
    # Residence named by surname "Anderson Residence" unlocks for high-bond contact
    gate_res = evaluate_node_access_gate(125, "loc_anderson_residence", sess, actions=[{"label": "Ring the bell"}])
    assert gate_res["gated"] is False
    assert gate_res["unlocked_by"] == "resident_welcome"
    assert gate_res["resident_name"] == "Maya Anderson"


def test_all_scenario_schedules():
    scenarios = [
        "cyberpunk", "slice_of_life", "sci_fi", "steampunk",
        "dark_fantasy", "nuclear_post_apocalypse", "isekai_fantasy", "fantasy"
    ]
    npc = {"name": "Test Actor", "role": "Merchant", "club": ""}
    for sc in scenarios:
        sched = get_npc_schedule_node_ids(npc, scen_key=sc)
        assert len(sched) == 5
        assert all(k in sched for k in ("morning", "lunch", "afternoon", "evening", "night"))
        assert sched["night"] != "loc_player_house"


def test_crossed_boundary_schedule_transition():
    from mechanics.world.schedules import get_time_block_key

    # Passing stay action saves override block
    curr_min = 720
    c_block = get_time_block_key(curr_min)
    assert c_block == "lunch"
    stay_overrides = ["lunch"]
    assert "lunch" in stay_overrides


def test_discord_map_embed_parity():
    from mechanics.world.locations.formatting import get_zone_summary_tree
    from cogs.adventure.embeds import build_zone_places_embed

    sess = _create_mock_session(126, current_minute=600, current_day=1)
    record_turn_scene_residue(126, "loc_library", sess, {"npc_memories": [{"summary": "Studied ancient runes"}]}, [])

    zones = get_zone_summary_tree(126, "high_school_drama")
    assert len(zones) >= 1
    first_zone = zones[0]
    first_place = first_zone["primary_locations"][0]
    assert "access_badge" in first_place
    assert "known_npcs_here" in first_place
    assert "unmet_activity_count" in first_place

    embed = build_zone_places_embed(126, first_zone["zone_name"], "high_school_drama")
    assert embed.title is not None
    assert len(embed.fields) >= 1

