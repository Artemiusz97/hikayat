"""
tests/test_world_and_npc_schedules.py
=====================================
Comprehensive test suite for the split World Schedule (`mechanics/world/world_schedule.py`)
and NPC Schedule (`mechanics/world/npc_schedule.py`) frameworks, High School weekday/weekend
operating hours, Truancy Gatekeeper, Abandoned School 24/7 exception, Commercial hours,
07:00 AM wake-up / 10:00 PM sleep, and Time-Aware Morning Starting Hooks.
"""
import pytest
import db
import scenario_data
from mechanics.world.world_schedule import (
    is_weekend,
    get_day_type,
    is_high_school_setting,
    get_scenario_wake_minute,
    get_scenario_sleep_minute,
    is_abandoned_school_node,
    is_campus_node_or_location,
    get_world_schedule_state,
    evaluate_world_schedule_node_access,
)
from mechanics.world.npc_schedule import (
    get_detailed_npc_time_phase,
    get_npc_schedule_node_ids,
    get_npc_scheduled_node_id,
    get_npc_schedule,
    get_npc_scheduled_location,
)
from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
from mechanics.world.locations.seeding import ensure_session_locations_seeded
from mechanics.world.locations.access_gate import (
    get_node_effective_access_info,
    evaluate_node_access_gate,
)
from mechanics.system.time_engine import format_llm_time_context
from game_engine.npcs.stage_manager import compute_pre_turn_stage


@pytest.fixture(autouse=True)
def init_test_db(tmp_path, monkeypatch):
    test_db_path = str(tmp_path / "test_world_npc_schedules.db")
    monkeypatch.setattr(db, "DB_PATH", test_db_path)
    monkeypatch.setattr(db.core, "DB_PATH", test_db_path)
    db.init_db(force=True)
    yield


def _create_hs_session(session_id: int = 500, current_day: int = 1, current_minute: int = 480):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.execute("DELETE FROM world_nodes WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM world_edges WHERE session_id=?", (session_id,))
        conn.execute(
            """INSERT INTO sessions (
                   id, mode, capacity, status, scenario, current_location, current_node_id,
                   dialogue_partner, current_day, current_minute
               )
               VALUES (?, 'solo', 1, 'active', 'high_school_drama',
                       ?, 'loc_homeroom', '', ?, ?)""",
            (session_id, "Main Academy Campus ➔ Homeroom Classroom ➔ Player's Desk", current_day, current_minute),
        )
    ensure_session_locations_seeded(session_id, "high_school_drama", char_name="Alex")
    ensure_session_spatial_graph_seeded(session_id, "high_school_drama", char_name="Alex")
    return db.get_session(session_id)


def test_weekday_vs_weekend_calendar():
    # Day 1..5 = Mon..Fri (weekday), Day 6..7 = Sat..Sun (weekend)
    for d in (1, 2, 3, 4, 5, 8, 9, 10, 11, 12):
        assert is_weekend(d) is False
        assert get_day_type(d) == "weekday"
    for d in (6, 7, 13, 14):
        assert is_weekend(d) is True
        assert get_day_type(d) == "weekend"


def test_high_school_wake_and_sleep_minutes():
    for hs_scen in ("high_school_drama", "nsfw_high_school_drama", "furry_high_school_drama", "nsfw_furry_high_school_drama"):
        assert is_high_school_setting(hs_scen) is True
        assert get_scenario_wake_minute(hs_scen) == 420   # 07:00 AM
        assert get_scenario_sleep_minute(hs_scen) == 1320 # 10:00 PM (22:00)

    # Non-school genres default to 07:30 AM (450) wake-up
    assert get_scenario_wake_minute("fantasy") == 450
    assert get_scenario_wake_minute("cyberpunk") == 450


def test_high_school_weekday_world_schedule_periods():
    # 1. 07:00–08:00 (420..479): Unrestricted morning arrival & prep
    st_arrival = get_world_schedule_state("high_school_drama", current_day=1, current_minute=450)
    assert st_arrival["period_key"] == "school_arrival_prep"
    assert st_arrival["school_open"] is True
    assert st_arrival["can_leave_campus"] is True
    assert st_arrival["is_trespassing_on_campus"] is False

    # 2. 08:00–15:00 (480..899): Class period (leaving campus forbidden, all school facilities unlocked)
    st_class = get_world_schedule_state("high_school_drama", current_day=2, current_minute=540)
    assert st_class["period_key"] == "class_hours"
    assert st_class["school_open"] is True
    assert st_class["can_leave_campus"] is False
    assert st_class["is_trespassing_on_campus"] is False

    # Lunch sub-period (12:00–13:00) still forbids leaving campus
    st_lunch = get_world_schedule_state("high_school_drama", current_day=3, current_minute=750)
    assert st_lunch["period_key"] == "class_hours_lunch"
    assert st_lunch["can_leave_campus"] is False

    # 3. 15:00–20:00 (900..1199): Extracurricular period (free to roam or leave, some facilities locked)
    st_extra = get_world_schedule_state("high_school_drama", current_day=4, current_minute=960)
    assert st_extra["period_key"] == "extracurricular_period"
    assert st_extra["school_open"] is True
    assert st_extra["can_leave_campus"] is True
    assert st_extra["is_trespassing_on_campus"] is False

    # 4. 20:00–07:00 (1200..1439 & 0..419): After-hours lockdown & trespassing
    st_night = get_world_schedule_state("high_school_drama", current_day=5, current_minute=1230)
    assert st_night["period_key"] == "after_hours_restricted"
    assert st_night["school_open"] is False
    assert st_night["is_trespassing_on_campus"] is True


def test_abandoned_school_building_always_accessible_24_7():
    # Even at 23:30 (1410) on a weekday or weekend, Abandoned School Building nodes are open & never gated
    sess = _create_hs_session(501, current_day=1, current_minute=1410)
    for nid in ("zone_abandoned_school", "loc_old_storage_3b", "loc_derelict_gym", "loc_clock_tower", "loc_old_infirmary", "sub_dark_equipment_room"):
        node = db.get_world_node(501, nid)
        assert node is not None
        assert is_abandoned_school_node(node) is True
        acc = get_node_effective_access_info(501, nid, current_day=1, current_minute=1410)
        assert acc["access_tier"] == "open"
        assert acc["curfew_active"] is False
        assert acc["schedule_locked"] is False
        gate = evaluate_node_access_gate(501, nid, sess, actions=[{"label": f"Enter {node['name']}"}])
        assert gate["gated"] is False


def test_weekday_school_hours_truancy_gatekeeper_and_late_arrival():
    # On Monday at 10:00 AM (600), student in Homeroom tries to leave for Local Café -> halted at School Main Gates
    sess = _create_hs_session(502, current_day=1, current_minute=600)
    gate = evaluate_node_access_gate(502, "loc_cafe", sess, actions=[{"label": "Ditch class and head to the Local Café"}])
    assert gate["gated"] is True
    assert gate["reason_code"] == "school_hours_lockdown"
    assert gate["node_id"] == "loc_school_gate"
    assert "School Main Gates" in gate["halt_location_override"]
    assert any("[AGI] Sneak out by climbing the side perimeter fence" in c for c in gate["barrier_choices"])
    assert any("[CHA] Convince the gatekeeper" in c for c in gate["barrier_choices"])

    # Stage manager places halted player at School Main Gates -> Outside the Locked Entrance
    stage = compute_pre_turn_stage(sess, [{"label": "Walk to the Convenience Store"}])
    assert stage["access_gate"]["gated"] is True
    assert "School Main Gates ➔ Outside the Locked Entrance" in stage["effective_location"]

    # Passing AGI fence-climb check unlocks truancy gate for the day
    succ_gate = evaluate_node_access_gate(
        502, "loc_cafe", sess,
        actions=[{"label": "[AGI] Sneak out by climbing the side perimeter fence toward Local Café", "check": {"tier": "success"}}]
    )
    assert succ_gate["gated"] is False
    assert succ_gate["unlocked_by"] == "truancy_bypass"

    # Late arrival from off-campus (Player's House -> Homeroom at 08:30 AM) is allowed with tardiness warning
    sess_late = _create_hs_session(503, current_day=1, current_minute=510)
    sess_late["current_location"] = "Residential Neighborhood ➔ Player's House ➔ Front Porch"
    sess_late["current_node_id"] = "loc_player_house"
    late_res = evaluate_node_access_gate(503, "loc_homeroom", sess_late, actions=[{"label": "Hurry to Homeroom Classroom"}])
    assert late_res["gated"] is False
    assert late_res.get("late_arrival_warning") is True
    assert "LATE ARRIVAL TO SCHOOL" in late_res.get("prompt_directive", "")


def test_extracurricular_weekend_and_after_hours_facility_locks():
    # 1. Extracurricular Period (15:00–20:00 Mon–Fri): Discreet Empty Classroom stays open until 20:00; Rooftop is locked; Sports & Club HQs are open
    sess_extra = _create_hs_session(504, current_day=1, current_minute=960) # 16:00 Monday
    acc_empty = get_node_effective_access_info(504, "loc_empty_class", current_day=1, current_minute=960)
    assert acc_empty["schedule_locked"] is False
    acc_roof = get_node_effective_access_info(504, "loc_rooftop", current_day=1, current_minute=960)
    assert acc_roof["schedule_locked"] is True
    assert acc_roof["status_badge"] == "Locked (After-School)"
    gate_roof = evaluate_node_access_gate(504, "loc_rooftop", sess_extra, actions=[{"label": "Enter School Rooftop"}])
    assert gate_roof["gated"] is True

    acc_aud = get_node_effective_access_info(504, "loc_auditorium_stage", current_day=1, current_minute=960)
    assert acc_aud["schedule_locked"] is False
    acc_gym = get_node_effective_access_info(504, "loc_gymnasium", current_day=1, current_minute=960)
    assert acc_gym["schedule_locked"] is False

    # 2. Weekend Daytime (Saturday 11:00 AM = Day 6, min 660):
    # Main Academic Wing (Homeroom, Library) & Cafeteria are locked; Sports & Club HQs remain open
    sess_wknd = _create_hs_session(505, current_day=6, current_minute=660)
    for locked_nid in ("loc_homeroom", "loc_library", "loc_cafeteria"):
        gate_w = evaluate_node_access_gate(505, locked_nid, sess_wknd, actions=[{"label": "Try the door"}])
        assert gate_w["gated"] is True
        assert gate_w["reason_code"] == "weekend_closed"

    for open_nid in ("loc_gymnasium", "loc_sports_field", "loc_pool", "loc_auditorium_stage", "loc_fine_arts_studio", "loc_old_storage_3b"):
        gate_o = evaluate_node_access_gate(505, open_nid, sess_wknd, actions=[{"label": "Head inside"}])
        assert gate_o["gated"] is False

    # 3. After-Hours (20:30 = min 1230): Entire campus (even Gymnasium & Courtyard) is locked & trespassing
    sess_night = _create_hs_session(506, current_day=1, current_minute=1230)
    for night_nid in ("loc_homeroom", "loc_gymnasium", "loc_auditorium_stage"):
        gate_n = evaluate_node_access_gate(506, night_nid, sess_night, actions=[{"label": "Walk onto campus"}])
        assert gate_n["gated"] is True
        assert gate_n["is_trespassing"] is True
        assert "TRESPASSING" in gate_n["prompt_directive"]


def test_commercial_hours_08_00_to_22_00_and_24_7_convenience_store():
    # At 23:00 (1380): Café, Arcade, Karaoke are closed (open 08:00–22:00 daily), but Convenience Store is open 24/7
    sess_late = _create_hs_session(507, current_day=6, current_minute=1380)
    for closed_shop in ("loc_cafe", "loc_arcade", "loc_karaoke"):
        gate_shop = evaluate_node_access_gate(507, closed_shop, sess_late, actions=[{"label": "Visit venue"}])
        assert gate_shop["gated"] is True
        assert gate_shop["reason_code"] == "commercial_closed"

    gate_conv = evaluate_node_access_gate(507, "loc_convenience_store", sess_late, actions=[{"label": "Visit Convenience Store"}])
    assert gate_conv["gated"] is False

    # At 14:00 (840): Café, Arcade, Karaoke are open
    sess_day = _create_hs_session(508, current_day=6, current_minute=840)
    for open_shop in ("loc_cafe", "loc_arcade", "loc_karaoke", "loc_convenience_store"):
        gate_open = evaluate_node_access_gate(508, open_shop, sess_day, actions=[{"label": "Visit venue"}])
        assert gate_open["gated"] is False


def test_high_school_npc_schedules_weekday_and_weekend():
    theater_student = {"name": "Sora Aoi", "role": "Student", "club": "Theater Club"}
    jock_student = {"name": "Riku Kurosawa", "role": "Student", "club": "Basketball Team", "unlocked_traits": ["Athletic"]}

    # Weekday phases:
    # 07:30 (450) -> commute to school
    assert get_detailed_npc_time_phase(450, current_day=1, scen_key="high_school_drama") == "commute"
    commute_node = get_npc_scheduled_node_id(theater_student, current_minute=450, scen_key="high_school_drama", current_day=1)
    assert commute_node in ("loc_school_gate", "loc_entrance_foyer", "loc_courtyard", "loc_homeroom")

    # 10:00 (600) & 13:30 (810) -> class periods on campus
    assert get_detailed_npc_time_phase(600, current_day=1, scen_key="high_school_drama") == "morning"
    assert get_detailed_npc_time_phase(810, current_day=1, scen_key="high_school_drama") == "class_afternoon"
    assert get_npc_scheduled_node_id(theater_student, current_minute=600, scen_key="high_school_drama", current_day=1) == "loc_homeroom"

    # 16:00 (960) -> extracurricular period (15:00–20:00): Theater club at Auditorium, Basketball jock at Gymnasium
    assert get_detailed_npc_time_phase(960, current_day=1, scen_key="high_school_drama") == "extracurricular"
    assert get_npc_scheduled_node_id(theater_student, current_minute=960, scen_key="high_school_drama", current_day=1) == "loc_auditorium_stage"
    assert get_npc_scheduled_node_id(jock_student, current_minute=960, scen_key="high_school_drama", current_day=1) == "loc_gymnasium"

    # 20:30 (1230) -> Night (20:00–07:00): everyone returns home
    assert get_detailed_npc_time_phase(1230, current_day=1, scen_key="high_school_drama") == "night"
    assert get_npc_scheduled_node_id(theater_student, current_minute=1230, scen_key="high_school_drama", current_day=1) == "loc_sora_aoi_house"

    # Weekend (Day 6 = Saturday, Day 7 = Sunday): students roam world or do optional club/sport training
    wknd_d6 = get_npc_scheduled_node_id(theater_student, current_minute=840, scen_key="high_school_drama", current_day=6)
    wknd_d7 = get_npc_scheduled_node_id(theater_student, current_minute=840, scen_key="high_school_drama", current_day=7)
    # Across Saturday and Sunday, one day trains at club/sport and one day roams off-campus
    assert "loc_auditorium_stage" in (wknd_d6, wknd_d7)
    assert any(n != "loc_auditorium_stage" for n in (wknd_d6, wknd_d7))


def test_time_aware_morning_starting_hooks_for_high_school():
    genres = scenario_data.load_genres(reload=True)
    hs_hooks = genres["high_school"]["starting_hooks"]
    assert len(hs_hooks) >= 6

    valid_morning_minutes = {420, 450, 465, 480} # 07:00, 07:30, 07:45, 08:00 AM
    seen_minutes = set()
    for h in hs_hooks:
        assert h.get("starting_minute") in valid_morning_minutes
        seen_minutes.add(h["starting_minute"])
        assert any(t in h["hook"] for t in ("07:00 AM", "07:30 AM", "07:45 AM", "08:00 AM"))
    assert seen_minutes == valid_morning_minutes

    # Test get_dynamic_starting_hook across all 4 High School scenarios
    for hs_key in ("high_school_drama", "nsfw_high_school_drama", "furry_high_school_drama", "nsfw_furry_high_school_drama"):
        hook_info = scenario_data.get_dynamic_starting_hook(hs_key, session_id=509, char_name="Alex")
        assert hook_info["starting_minute"] in valid_morning_minutes
        assert "{session_" not in hook_info["suggested_location"]


class TestAuditFixesRegression:
    def test_school_facilities_open_during_weekday_school_hours(self):
        from mechanics.world.world_schedule import evaluate_world_schedule_node_access
        lib_node = {"node_id": "loc_library", "name": "School Library", "node_type": "FACILITY", "category": "academic", "access_tier": "open"}
        empty_node = {"node_id": "loc_empty_class", "name": "Empty Classroom 3-C", "node_type": "ROOM", "category": "academic", "access_tier": "open"}
        rooftop_node = {"node_id": "loc_rooftop", "name": "School Rooftop", "node_type": "FACILITY", "category": "academic", "access_tier": "restricted"}
        parent_node = {"node_id": "zone_school", "name": "Main Academy Campus", "node_type": "ZONE", "category": "academic"}

        # 07:30 AM (arrival prep) - Library is force open
        res_0730 = evaluate_world_schedule_node_access(lib_node, parent_node, scen_key="high_school_drama", current_day=1, current_minute=450)
        assert res_0730["force_open"] is True
        assert res_0730["schedule_locked"] is False

        # 10:00 AM (class hours) - Library and empty class are force open
        res_1000 = evaluate_world_schedule_node_access(lib_node, parent_node, scen_key="high_school_drama", current_day=1, current_minute=600)
        assert res_1000["force_open"] is True
        assert res_1000["schedule_locked"] is False

        # 10:00 AM - Rooftop is inner restricted (preserves restricted tier for illicit rendezvous)
        res_roof = evaluate_world_schedule_node_access(rooftop_node, parent_node, scen_key="high_school_drama", current_day=1, current_minute=600)
        assert res_roof["force_open"] is False

        # 16:00 (extracurriculars) - Discreet Empty Classroom stays open until 20:00; Rooftop is locked
        res_1600 = evaluate_world_schedule_node_access(empty_node, parent_node, scen_key="high_school_drama", current_day=1, current_minute=960)
        assert res_1600["schedule_locked"] is False
        res_roof_1600 = evaluate_world_schedule_node_access(rooftop_node, parent_node, scen_key="high_school_drama", current_day=1, current_minute=960)
        assert res_roof_1600["schedule_locked"] is True
        assert res_roof_1600["force_open"] is False

    def test_imminent_transition_day_aware(self):
        from mechanics.world.npc_schedule import is_schedule_transition_imminent

        # 14:50 (890 min) on Monday (Day 1) - 10 mins before 15:00 extracurriculars
        imm_wd, cur_b, next_b, diff = is_schedule_transition_imminent(890, window_minutes=15, current_day=1, scen_key="high_school_drama")
        assert imm_wd is True
        assert next_b == "extracurricular"
        assert diff == 10

        # 14:50 (890 min) on Saturday (Day 6) - No extracurricular transition on weekends!
        imm_we, cur_we, next_we, diff_we = is_schedule_transition_imminent(890, window_minutes=15, current_day=6, scen_key="high_school_drama")
        assert next_we != "extracurricular"

    def test_is_sleep_time_scenario_aware(self):
        from mechanics.system.time_engine import is_sleep_time

        # 06:30 AM (390 min)
        # High School: wake-up is 07:00 AM (420), so 06:30 is still sleep time
        assert is_sleep_time(390, scen_key="high_school_drama") is True
        # Fantasy / Default: wake-up is 06:00 AM (360), so 06:30 is daytime
        assert is_sleep_time(390, scen_key="fantasy") is False

    def test_sensory_block_campus_after_hours(self):
        from mechanics.world.locations.formatting import build_node_sensory_and_memory_block
        curr_node = {"node_id": "loc_homeroom", "name": "Homeroom 2-B", "node_type": "ROOM", "category": "academic", "is_enclosed": 1}

        # 06:30 AM on Monday (Day 1): still after-hours on campus (20:00-07:00)
        block_0630 = build_node_sensory_and_memory_block(9999, curr_node, current_day=1, current_minute=390)
        assert "after-hours stillness" in block_0630.lower()
        assert "AFTER-HOURS TRESPASSING" in block_0630

        # 08:30 AM on Monday (Day 1): school open
        block_0830 = build_node_sensory_and_memory_block(9999, curr_node, current_day=1, current_minute=510)
        assert "morning sunlight" in block_0830.lower()
        assert "AFTER-HOURS TRESPASSING" not in block_0830

    def test_apply_sleep_rest_morning_exhaustion_advances_day(self):
        from mechanics.system.time_engine import apply_sleep_rest
        sess = _create_hs_session(520, current_day=1, current_minute=480) # 08:00 AM
        char = db.get_character(1)
        uid = char["user_id"] if char else 1

        # Sleeping at 08:00 AM (past 07:00 AM wake time) must advance to tomorrow morning (Day 2, 07:00 AM)
        info = apply_sleep_rest(520, [uid], scen_key="high_school_drama")
        day_after, min_after, _ = db.get_session_time(520)
        assert day_after == 2
        assert min_after == 420 # 07:00 AM

        # Sleeping at 02:00 AM (120 min, before 07:00 AM wake time) wakes at 07:00 AM on the SAME day
        db.update_session_time(520, current_day=2, current_minute=120)
        info_early = apply_sleep_rest(520, [uid], scen_key="high_school_drama")
        day_early, min_early, _ = db.get_session_time(520)
        assert day_early == 2
        assert min_early == 420

    def test_turn2_return_to_campus_grounds_retreat(self):
        sess = _create_hs_session(521, current_day=1, current_minute=600)
        # 1. First trigger truancy halt at school gate
        halt_res = evaluate_node_access_gate(
            521, "loc_cafe", sess,
            actions=[{"label": "Head to the cafe"}]
        )
        assert halt_res["gated"] is True
        assert halt_res["reason_code"] == "school_hours_lockdown"

        # Verify pending target was stored on loc_school_gate
        gate_state = db.get_world_node_state(521, "loc_school_gate")
        assert gate_state.get("pending_truancy_target_node_id") == "loc_cafe"

        # 2. Turn 2: Player chooses "Return to campus grounds"
        ret_res = evaluate_node_access_gate(
            521, "loc_school_gate", sess,
            actions=[{"label": "Return to campus grounds"}]
        )
        assert ret_res["gated"] is False
        assert ret_res["returned_to_campus"] is True

        # Verify pending truancy target was cleared
        gate_state_cleared = db.get_world_node_state(521, "loc_school_gate")
        assert gate_state_cleared.get("pending_truancy_target_node_id") == ""

    def test_abandoned_ruined_hallway_unrestricted_24_7(self):
        from mechanics.world.world_schedule import is_abandoned_school_node, evaluate_world_schedule_node_access
        hallway_node = {
            "node_id": "loc_ruined_hallway",
            "name": "Overgrown Hallway Wing",
            "node_type": "FACILITY",
            "category": "academic",
            "parent_id": "zone_abandoned_school"
        }
        parent = {"node_id": "zone_abandoned_school", "name": "Abandoned Old Campus Building", "node_type": "ZONE", "category": "academic"}

        # At 23:00 (1380, after-hours lockdown for main campus)
        assert is_abandoned_school_node(hallway_node, parent) is True
        access = evaluate_world_schedule_node_access(hallway_node, parent, scen_key="high_school_drama", current_day=1, current_minute=1380)
        assert access["schedule_locked"] is False
        assert access["force_open"] is True
        assert access["is_trespassing"] is False

    def test_opening_scene_initial_node_id_resolution(self):
        _create_hs_session(522, current_day=1, current_minute=420)
        # Hook 1: Bedroom
        bed_node = db.resolve_node_id_from_location(522, "Residential Neighborhood ➔ Alex's House ➔ Your Bedroom")
        assert bed_node == "sub_player_bedroom"

        # Hook 2: Front gate
        gate_node = db.resolve_node_id_from_location(522, "Main Academy Campus ➔ Main Campus Building ➔ School Main Gates")
        assert gate_node == "loc_school_gate"

        # Hook 3: Homeroom desk
        desk_node = db.resolve_node_id_from_location(522, "Main Academy Campus ➔ Main Campus Building ➔ Homeroom Classroom")
        assert desk_node == "loc_homeroom"

    def test_discord_embed_lock_indicator_formatting(self):
        from mechanics.world.locations.formatting import get_zone_summary_tree
        from cogs.adventure.embeds import build_zone_places_embed
        # Create session at 23:00 (1380, after-hours lockdown)
        _create_hs_session(523, current_day=1, current_minute=1380)
        zones = get_zone_summary_tree(523, "high_school_drama")
        comm_zone = next((z for z in zones if "commercial" in z["zone_name"].lower() or "shopping" in z["zone_name"].lower()), zones[0])
        embed = build_zone_places_embed(523, comm_zone["zone_name"], "high_school_drama")
        field_text = "\n".join(f.value for f in embed.fields)
        # Commercial shops are closed at 23:00 and format with lock icon
        assert "🔒 Closed (22:00–08:00)" in field_text or "🔒" in field_text

    def test_npc_messaging_time_injection(self):
        from mechanics.world.world_schedule import get_world_schedule_state
        from mechanics.system.time_engine import format_time_header
        # Verify time header and world schedule period label format cleanly for messaging prompt
        time_str = format_time_header(1, 480)
        sched = get_world_schedule_state("high_school_drama", current_day=1, current_minute=480)
        hint = f"- Current In-Game Time & Schedule: {time_str} [{sched.get('period_label', '')}]."
        assert "08:00" in hint
        assert "Active Class Hours" in hint

    def test_non_school_genre_academic_node_sensory_isolation(self):
        from mechanics.world.locations.formatting import build_node_sensory_and_memory_block
        arcane_academy = {"node_id": "loc_arcane_academy", "name": "Grand Arcane Library", "category": "academic", "is_enclosed": 1}
        # In Fantasy at 22:00 (1320), high school campus lockdown & trespassing must NOT trigger
        fantasy_block = build_node_sensory_and_memory_block(523, arcane_academy, current_day=1, current_minute=1320, scen_key="fantasy")
        assert "AFTER-HOURS TRESPASSING" not in fantasy_block
        assert "CAMPUS CURFEW" not in fantasy_block
        assert "students and teachers have returned home" not in fantasy_block


class TestScheduleAndAgentRosterIntegration:
    def test_high_school_sport_specialization_faculty_stations_and_midnight_staging(self):
        from mechanics.social.school_roster import get_facility_ambient_characters

        sess = _create_hs_session(530, current_day=1, current_minute=600)  # Monday 10:00 AM

        # 1. Athletic Directorate sports resolve to specific venues via role/primary_facility
        swim_capt = {
            "name": "Mina Sato",
            "role": "Varsity Swim Captain",
            "club": "Athletic Directorate",
            "primary_facility": "Main Academy Campus ➔ School Grounds & Athletics ➔ Swimming Pool Facility",
        }
        kendo_lead = {
            "name": "Kenji Mori",
            "role": "Martial Arts Club Lead",
            "club": "Athletic Directorate",
            "primary_facility": "Main Academy Campus ➔ School Grounds & Athletics ➔ Martial Arts Dojo",
        }
        track_ace = {
            "name": "Hana Takahashi",
            "role": "Track Sprinter",
            "club": "Athletic Directorate",
            "primary_facility": "Main Academy Campus ➔ School Grounds & Athletics ➔ Athletic Field",
        }
        assert get_npc_scheduled_node_id(swim_capt, current_minute=960, scen_key="high_school_drama", current_day=1) == "loc_pool"
        assert get_npc_scheduled_node_id(kendo_lead, current_minute=960, scen_key="high_school_drama", current_day=1) == "loc_martial_arts_dojo"
        assert get_npc_scheduled_node_id(track_ace, current_minute=960, scen_key="high_school_drama", current_day=1) == "loc_sports_field"

        # 2. Subject teachers teach in their subject rooms during morning/afternoon class periods
        chem_teacher = {"name": "Dr. Arata", "role": "Chemistry Teacher", "club": "Faculty"}
        pe_coach = {"name": "Coach Daiki", "role": "Athletics Coach", "club": "Faculty"}
        assert get_npc_scheduled_node_id(chem_teacher, current_minute=600, scen_key="high_school_drama", current_day=1) == "loc_science_lab"
        assert get_npc_scheduled_node_id(pe_coach, current_minute=810, scen_key="high_school_drama", current_day=1) == "loc_gymnasium"

        # 3. Empty Classroom and Abandoned School never spawn straggler students during active class hours
        for check_min in (540, 600, 810, 840):
            assert get_facility_ambient_characters(
                530, "Main Academy Campus ➔ Main Campus Building ➔ Empty Classroom 3-C",
                limit=2, current_day=1, current_minute=check_min,
            ) == []
            assert get_facility_ambient_characters(
                530, "Main Academy Campus ➔ Abandoned Old Campus Building ➔ Derelict Gymnasium",
                limit=2, current_day=1, current_minute=check_min,
            ) == []

        # 4. Midnight campus movement (e.g. unlocked via keycard) never stages ghost daytime residents
        from mechanics.world.locations.access_gate import record_node_unlock
        record_node_unlock(530, "loc_science_lab", unlock_type="day", current_day=1, reason="key")
        sess["current_minute"] = 1380  # 23:00
        sess["current_location"] = "Main Academy Campus ➔ Main Campus Building ➔ School Hallway"
        sess["current_node_id"] = "loc_school_hallway"
        db.update_session(530, current_minute=1380, current_location=sess["current_location"], current_node_id="loc_school_hallway")
        stage = compute_pre_turn_stage(sess, [{"label": "Enter Chemistry & Science Lab"}])
        assert stage["stage_npcs"] == []

    def test_anomalous_incursions_special_agent_roster_and_theme_park_shift(self):
        from mechanics.world.anomalous_events import bootstrap_anomalous_session
        from mechanics.social.agent_roster import (
            ensure_anomalous_agent_roster,
            get_anomalous_facility_ambient_agents,
        )
        from mechanics.world.schedules import is_npc_nocturnal_or_night_shift
        from mechanics.world.waypoints.matching import get_waypoint_npc_schedule_info
        from mechanics.world.locations.formatting import build_node_sensory_and_memory_block
        from game_engine.context import _scene_context_text

        sid = db.create_session(1, "solo", 1, "standard", "immersive", False, channel_id=2001, scenario="anomalous_incursions")
        bootstrap_anomalous_session(sid, "anomalous_incursions", 2001, "public_agency", "Operative Kira")
        roster = ensure_anomalous_agent_roster(sid, "anomalous_incursions")
        assert len(roster) == 44

        session_node_ids = {n["node_id"] for n in db.get_session_world_nodes(sid)}

        # 1. Zero {session_school} leaks & Private Agency #2 strictly maps to sub_priv2_*
        for ag in roster:
            assert "{session_" not in ag["primary_facility"]
            assert "{session_" not in ag["secondary_facility"]
            assert ag["primary_node_id"] in session_node_ids
            assert ag["secondary_node_id"] in session_node_ids
            if ag["faction_id"] == "private_agency_2":
                assert ag["primary_node_id"].startswith("sub_priv2_")

            # Verify no agent ever falls back to medieval Fantasy schedule nodes/strings
            sched_map = get_npc_schedule(ag, scen_key="anomalous_incursions", session_id=sid, current_day=1)
            for loc_val in sched_map.values():
                assert "Adventurer's Guild" not in loc_val
                assert "Tavern Inn" not in loc_val

        # 2. Cult & Syndicate operatives are nocturnal and remain On-Duty for night waypoints
        cult_agents = [a for a in roster if a["faction_id"] == "cult_faction"]
        veiled_acolyte = next(a for a in cult_agents if "veiled acolyte" in a["role"].lower())
        assert is_npc_nocturnal_or_night_shift(veiled_acolyte, scen_key="anomalous_incursions", current_day=1) is True
        # At 23:00 (1380), Veiled Acolyte converges on Theme Park Hall of Mirrors Anomaly!
        assert get_npc_scheduled_node_id(veiled_acolyte, current_minute=1380, scen_key="anomalous_incursions", current_day=1) == "loc_tp_mirror_labyrinth"

        db.upsert_contact(
            session_id=sid,
            character_id=0,
            npc_id=veiled_acolyte["npc_id"],
            name=veiled_acolyte["name"],
            delta_score=0,
            basic_info={"role": veiled_acolyte["role"], "faction_id": "cult_faction", "secondary_node_id": "loc_tp_mirror_labyrinth"},
        )
        db.update_session(sid, current_minute=1380, current_day=1)
        wp_night = get_waypoint_npc_schedule_info(
            sid,
            {
                "target_npc": veiled_acolyte["name"],
                "target_location": veiled_acolyte["primary_facility"],
                "follow_npc_schedule": True,
            },
        )
        assert wp_night["is_off_duty"] is False
        assert wp_night["status_label"] == "On-Duty"
        assert "Hall of Mirrors" in wp_night["effective_location"]

        # 3. Context injection surfaces on-shift Special Agents at HQ & Theme Park Night Shift
        hq_exec_loc = roster[0]["primary_facility"]
        db.update_session(sid, current_minute=540, current_day=1, current_location=hq_exec_loc, current_node_id="loc_hq_executive_dispatch")
        sess_day = db.get_session(sid)
        amb_hq = get_anomalous_facility_ambient_agents(sid, hq_exec_loc, limit=2, current_day=1, current_minute=540)
        assert len(amb_hq) >= 1
        ctx_text = _scene_context_text(sid, hq_exec_loc, [])
        assert "Metropolitan Operatives & Ambient Special Agents" in ctx_text

        # 4. Theme Park 21:45 Closing Warning vs 22:30 Anomalous Shift access & sensory block
        tp_node = db.get_world_node(sid, "loc_tp_main_midway")
        pre_shift_state = get_world_schedule_state("anomalous_incursions", current_day=1, current_minute=1305)
        assert "22:00 closing announcements" in pre_shift_state["narrative_directive"]
        pre_sensory = build_node_sensory_and_memory_block(sid, tp_node, current_day=1, current_minute=1305, scen_key="anomalous_incursions")
        assert "THEME PARK CLOSING WARNING" in pre_sensory

        shift_sensory = build_node_sensory_and_memory_block(sid, tp_node, current_day=1, current_minute=1350, scen_key="anomalous_incursions")
        assert "THEME PARK ANOMALOUS SHIFT (22:00–08:00)" in shift_sensory
        assert "calliope" in shift_sensory.lower()

        db.update_session(sid, current_minute=1350, current_day=1)
        sess_night = db.get_session(sid)
        tp_gate = evaluate_node_access_gate(sid, "loc_tp_main_midway", sess_night, actions=[{"label": "Investigate Theme Park"}])
        assert tp_gate["gated"] is False
        assert tp_gate.get("anomalous_shift_active") is True



