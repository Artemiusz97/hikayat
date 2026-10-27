from __future__ import annotations
"""
Integration & unit tests for the High School Town Roster, Civic/Commercial Schedules,
and Student Part-Time Shifts (`mechanics/social/town_roster.py`).
"""
import asyncio
from typing import Any, Dict, List

import pytest

import db
from mechanics.combat import merchant
from mechanics.narrative import bounty
from mechanics.social import relationships, school_roster, town_roster
from mechanics.system.phone import social_graph
from mechanics.world import npc_schedule, world_schedule
from mechanics.world.locations import graph_seeder


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect both db.DB_PATH and db.core.DB_PATH to an isolated temporary SQLite file."""
    test_db = str(tmp_path / "test_town_roster.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    yield test_db


def _create_hs_session(user_id: int = 770011) -> Dict[str, Any]:
    db.create_character(
        user_id,
        name="Ren Amamiya",
        char_class="Honor Student",
        gender="Male",
        scenario="high_school_drama",
        race="human",
    )
    sid = db.create_session(
        user_id,
        "solo",
        1,
        "vivid",
        "individual",
        False,
        scenario="high_school_drama",
    )
    graph_seeder.ensure_session_spatial_graph_seeded(
        sid, scenario_key="high_school_drama", char_name="Ren Amamiya"
    )
    return db.get_session(sid)


@pytest.mark.unit
def test_retroactive_50_to_88_backfill_and_transit_plaza_seeding():
    """Existing 50-character High School saves backfill cleanly to 94 (SFW) and seed loc_city_square."""
    session = _create_hs_session(770012)
    sid = int(session["id"])

    # 1. Fresh spatial seed includes City Square from locations_seed.json
    fresh_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sid)}
    assert "loc_city_square" in fresh_nodes
    assert "sub_bus_shelter" in fresh_nodes
    assert "sub_koban_police_box" in fresh_nodes
    assert "sub_shopping_crosswalk" in fresh_nodes
    assert "sub_square_fountain" in fresh_nodes
    assert "sub_square_underpass" in fresh_nodes

    # 24/7 operating status for City Square / Koban
    op_status = world_schedule.evaluate_world_schedule_node_access(
        fresh_nodes["sub_koban_police_box"],
        fresh_nodes["loc_city_square"],
        scen_key="high_school_drama",
        current_day=1,
        current_minute=180,  # 03:00 AM
    )
    assert op_status["schedule_locked"] is False
    assert op_status["force_open"] is True
    assert op_status.get("badge_override") == "Open (24/7)"

    # 2. Simulate a legacy save: remove loc_city_square + sub-rooms and store only 50 campus NPCs without part-time tags
    with db.get_conn() as conn:
        conn.execute(
            "DELETE FROM world_nodes WHERE session_id=? AND node_id IN ('loc_city_square','sub_bus_shelter','sub_koban_police_box','sub_shopping_crosswalk','sub_square_fountain','sub_square_underpass')",
            (sid,),
        )
        conn.execute(
            "DELETE FROM world_edges WHERE session_id=? AND (from_node_id IN ('loc_city_square','sub_bus_shelter','sub_koban_police_box','sub_shopping_crosswalk','sub_square_fountain','sub_square_underpass') OR to_node_id IN ('loc_city_square','sub_bus_shelter','sub_koban_police_box','sub_shopping_crosswalk','sub_square_fountain','sub_square_underpass'))",
            (sid,),
        )
        conn.execute("DELETE FROM school_directory WHERE session_id=?", (sid,))
        conn.commit()

    full_preview = school_roster.generate_campus_directory(sid, scen_key="high_school_drama")
    legacy_50: List[Dict[str, Any]] = []
    for entry in full_preview:
        if entry["grade"] in ("Citizen", "Youth Peer"):
            continue
        cloned = dict(entry)
        # Strip Part-Time tag to mimic pre-expansion save row
        cloned["personality_summary"] = cloned["personality_summary"].split(" Part-Time:")[0].strip()
        legacy_50.append(cloned)
        if len(legacy_50) == 50:
            break
    assert len(legacy_50) == 50
    original_names = {c["name"] for c in legacy_50}
    db.save_school_roster(sid, legacy_50)
    assert len(db.get_school_roster(sid)) == 50

    # 3. Trigger ensure_school_directory_exists -> should backfill to 94 + re-seed loc_city_square
    upgraded = school_roster.ensure_school_directory_exists(session)
    assert len(upgraded) == 94
    upgraded_names = {c["name"] for c in upgraded}
    assert original_names.issubset(upgraded_names)

    citizens = [c for c in upgraded if c["grade"] == "Citizen"]
    youth_peers = [c for c in upgraded if c["grade"] == "Youth Peer"]
    part_timers = [c for c in upgraded if "Part-Time:" in c.get("personality_summary", "")]
    assert len(citizens) == 26
    assert len(youth_peers) == 4
    assert len(part_timers) == 6

    backfilled_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sid)}
    assert "loc_city_square" in backfilled_nodes
    assert backfilled_nodes["sub_bus_shelter"]["node_type"] == "ROOM"
    travel_mins = db.find_shortest_graph_path_minutes(sid, "sub_bus_shelter", "sub_cafe_patio")
    assert travel_mins is not None and travel_mins <= 6


@pytest.mark.unit
def test_town_commercial_civic_and_nocturnal_routines():
    """Verify day/night clerk handoffs, police patrols, bus drivers, commuters, and campus night watch."""
    session = _create_hs_session(770013)
    sid = int(session["id"])
    roster = school_roster.ensure_school_directory_exists(session)
    by_role = {c["role"]: c for c in roster}

    konbini_day = by_role["Convenience Store Day Manager"]
    konbini_night = by_role["Convenience Store Night-Shift Clerk"]
    koban_day = by_role["Neighborhood Kōban Police Constable"]
    koban_night = by_role["Night-Beat Patrol Officer"]
    bus_driver = by_role["Municipal Route Bus Driver"]
    salaryman = by_role["Overworked Corporate Office Worker"]
    night_guard = by_role["Campus Night-Watch Security Officer"]
    chef = by_role["Cafeteria Head Chef"]
    custodian = by_role["Campus Custodian & Groundskeeper"]

    # Nocturnal classification for High School night-shift roles
    assert npc_schedule.is_npc_nocturnal_or_night_shift(konbini_night, scen_key="high_school_drama", current_day=1) is True
    assert npc_schedule.is_npc_nocturnal_or_night_shift(koban_night, scen_key="high_school_drama", current_day=1) is True
    assert npc_schedule.is_npc_nocturnal_or_night_shift(night_guard, scen_key="high_school_drama", current_day=1) is True
    assert npc_schedule.is_npc_nocturnal_or_night_shift(konbini_day, scen_key="high_school_drama", current_day=1) is False

    # 1. Konbini Day vs 21:30 Night Clerk Handoff
    assert npc_schedule.get_npc_scheduled_node_id(konbini_day, current_minute=600, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_convenience_store"
    assert npc_schedule.get_npc_scheduled_node_id(konbini_night, current_minute=600, scen_key="high_school_drama", current_day=1, session_id=sid) != "loc_convenience_store"
    assert npc_schedule.get_npc_scheduled_node_id(konbini_night, current_minute=1295, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_convenience_store"
    assert npc_schedule.get_npc_scheduled_node_id(konbini_night, current_minute=150, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_convenience_store"

    # Ambient query at Convenience Store at 02:30 AM surfaces the Night-Shift Clerk!
    fmt = town_roster.get_town_format_kwargs(sid, "high_school_drama")
    konbini_loc = f"{fmt['commercial_name']} ➔ Convenience Store ➔ Storefront & Checkout Counter"
    night_ambient = school_roster.get_facility_ambient_characters(
        sid, konbini_loc, current_day=1, current_minute=150
    )
    assert any(c["name"] == konbini_night["name"] for c in night_ambient)

    # 2. Koban Constable morning crosswalk (07:30) -> school gate dismissal check (15:15), Night-Beat Officer curfew patrol (23:30)
    assert npc_schedule.get_npc_scheduled_node_id(koban_day, current_minute=450, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_city_square"
    assert npc_schedule.get_npc_scheduled_node_id(koban_day, current_minute=915, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_school_gate"
    night_beats = {
        npc_schedule.get_npc_scheduled_node_id(
            koban_night, current_minute=1410, scen_key="high_school_drama", current_day=d, session_id=sid
        )
        for d in (1, 2, 3)
    }
    assert night_beats == {"loc_city_square", "loc_local_park", "loc_coastal_pier"}

    # 3. Bus Driver at City Square during morning rush; Salaryman out of town at 10:30 AM & eating late udon at Konbini at 22:30
    assert npc_schedule.get_npc_scheduled_node_id(bus_driver, current_minute=465, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_city_square"
    assert npc_schedule.get_npc_scheduled_node_id(salaryman, current_minute=450, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_city_square"
    assert npc_schedule.get_npc_scheduled_node_id(salaryman, current_minute=630, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_downtown_office_away"
    assert npc_schedule.get_npc_scheduled_node_id(salaryman, current_minute=1350, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_convenience_store"

    # 4. Campus Night-Watch Security Officer patrols locked halls at 01:00 AM and clocks off to residence at 07:30 AM
    assert npc_schedule.get_npc_scheduled_node_id(night_guard, current_minute=60, scen_key="high_school_drama", current_day=1, session_id=sid) in ("loc_school_hallway", "loc_courtyard", "loc_school_gate")
    assert npc_schedule.get_npc_scheduled_node_id(night_guard, current_minute=450, scen_key="high_school_drama", current_day=1, session_id=sid).endswith("_residence")

    # 5. New Campus Support Staff stations (Cafeteria Chef & Custodian/Groundskeeper)
    assert npc_schedule.get_npc_scheduled_node_id(chef, current_minute=600, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_cafeteria"
    assert npc_schedule.get_npc_scheduled_node_id(custodian, current_minute=960, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_greenhouse"


@pytest.mark.unit
def test_student_part_time_shifts_curfew_cutoff_and_conflict_yield():
    """6 campus students work alternating weekday/weekend shifts, clock out by 21:30, and yield to party/appointments."""
    session = _create_hs_session(770014)
    sid = int(session["id"])
    roster = school_roster.ensure_school_directory_exists(session)
    fmt = town_roster.get_town_format_kwargs(sid, "high_school_drama")

    barista_student = next(c for c in roster if c["role"] == "Part-Time Barista & Baker")
    delinquent_student = next(c for c in roster if c["role"] == "Rebellious Delinquent")

    # 1. Monday (day=1): Barista is in school at 10:00 (600), working loc_cafe at 18:30 (1110) and 20:30 (1230), off at 21:15 (1275)
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 600, session_id=sid) is None
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1110, session_id=sid) is not None
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1230, session_id=sid) is not None
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1275, session_id=sid) is None
    # Off on Tuesday (day=2), working Saturday afternoon (day=6, 14:00 = 840)
    assert town_roster.is_student_on_part_time_shift(barista_student, 2, 1110, session_id=sid) is None
    assert town_roster.is_student_on_part_time_shift(barista_student, 6, 840, session_id=sid) is not None

    # Ambient query at Cafe at 20:30 Monday (phase == 'night' on campus!) still surfaces on-shift Barista student!
    cafe_loc = f"{fmt['commercial_name']} ➔ {fmt['cafe_name']} ➔ Main Espresso & Seating Lounge"
    cafe_evening = school_roster.get_facility_ambient_characters(
        sid, cafe_loc, limit=3, current_day=1, current_minute=1230
    )
    assert any(c["name"] == barista_student["name"] for c in cafe_evening)

    # 2. Delinquent Konbini Cashier works Tue/Thu until 21:30 (1290) and strictly clocks out at 21:30 before 22:00 curfew
    assert town_roster.is_student_on_part_time_shift(delinquent_student, 2, 1275, session_id=sid) is not None
    assert town_roster.is_student_on_part_time_shift(delinquent_student, 2, 1290, session_id=sid) is None

    # 3. Conflict Yield A: Adding student to active party_npcs suspends part-time shift
    db.set_session_party_npcs(sid, [{"name": barista_student["name"], "role": barista_student["role"]}])
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1110, session_id=sid) is None
    db.set_session_party_npcs(sid, [])
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1110, session_id=sid) is not None

    # 4. Conflict Yield B: Active player meetup in commitments_ledger suspends part-time shift during appointment window
    saved = db.save_phone_appointment(
        session_id=sid,
        npc_id=barista_student["npc_id"],
        npc_name=barista_student["name"],
        rendezvous_location=f"{fmt['residential_name']} ➔ {fmt['park_name']} ➔ Duck Pond & Timber Footbridge",
        topic="Study hangout",
        created_minute=1080,  # Day 1, 18:00
        expiry_minute=1170,   # Day 1, 19:30
    )
    assert saved is True
    assert town_roster.is_student_on_part_time_shift(barista_student, 1, 1110, session_id=sid) is None


@pytest.mark.unit
def test_contact_eligibility_peerpulse_and_hydration_boundaries():
    """20 Adult Citizens stay Lorebook-only; 4 Youth Peers + 6 Student Part-Timers are full Smartphone/PeerPulse contacts."""
    user_id = 770015
    session = _create_hs_session(user_id)
    sid = int(session["id"])
    roster = school_roster.ensure_school_directory_exists(session)

    citizens = [c for c in roster if c["grade"] == "Citizen"]
    youth_peers = [c for c in roster if c["grade"] == "Youth Peer"]
    assert len(citizens) == 26
    assert len(youth_peers) == 4

    # 1. Every Adult Citizen is excluded from Contacts & PeerPulse
    for cit in citizens:
        assert relationships.is_contact_eligible(
            name=cit["name"],
            role=cit["role"],
            description=cit["personality_summary"],
            scenario="high_school_drama",
            session_id=sid,
        ) is False
        prof = social_graph.lookup_social_profile(sid, user_id, cit["name"])
        assert prof is not None
        assert prof["is_eligible"] is False

    # Hydrate an Adult Citizen -> Lorebook populated with civilian workwear, Contacts row NOT created
    sample_citizen = citizens[0]
    assert school_roster.hydrate_school_character(sid, sample_citizen) is True
    assert db.get_contact(sid, sample_citizen["npc_id"]) is None
    lore_person = db.get_lorebook_entity(sid, sample_citizen["name"])
    assert lore_person is not None
    assert "[TownArchetype:" not in lore_person["description"]
    assert "school uniform" not in str(lore_person.get("appearance", {}).get("outfit_style", "")).lower()

    # 2. Every Out-of-School Youth Peer is Contact & PeerPulse eligible!
    for yp in youth_peers:
        assert relationships.is_contact_eligible(
            name=yp["name"],
            role=yp["role"],
            description=yp["personality_summary"],
            scenario="high_school_drama",
            session_id=sid,
        ) is True
        prof = social_graph.lookup_social_profile(sid, user_id, yp["name"])
        assert prof is not None
        assert prof["is_eligible"] is True

    sample_yp = youth_peers[0]
    assert school_roster.hydrate_school_character(sid, sample_yp) is True
    yp_contact = db.get_contact(sid, sample_yp["npc_id"])
    assert yp_contact is not None
    assert yp_contact["name"] == sample_yp["name"]
    assert "[TownArchetype:" not in yp_contact["basic_info"].get("description", "")

    # 3. Suggested peers feed never leaks Adult Citizens or Faculty
    suggested = social_graph.get_suggested_peers(sid, user_id, limit=25)
    for sp in suggested:
        assert sp.get("grade") not in ("Faculty", "Citizen")


@pytest.mark.unit
def test_merchant_shop_clerk_binding_and_classmate_hookup_discount():
    """Physical shops bind to the active on-shift Student Part-Timer (with 10% hookup at >=40 affinity) or Night Clerk."""
    user_id = 770016
    session = _create_hs_session(user_id)
    sid = int(session["id"])
    char = db.get_character(user_id)
    roster = school_roster.ensure_school_directory_exists(session)
    fmt = town_roster.get_town_format_kwargs(sid, "high_school_drama")

    barista_student = next(c for c in roster if c["role"] == "Part-Time Barista & Baker")
    konbini_night = next(c for c in roster if c["role"] == "Convenience Store Night-Shift Clerk")

    # 1. Monday 18:30 (1110) at Cafe -> Student Part-Timer is on shift at standard 1.0x price (affinity < 40)
    cafe_loc = f"{fmt['commercial_name']} ➔ {fmt['cafe_name']} ➔ Main Espresso & Seating Lounge"
    db.update_session(sid, current_day=1, current_minute=1110, current_location=cafe_loc)
    sess_now = db.get_session(sid)

    shop_base = asyncio.run(
        merchant.generate_merchant_shop(
            party=[(char, user_id)],
            merchant_name="",
            merchant_description="",
            session=sess_now,
            is_phone_shop=False,
            merchant_type="cafe_merchant",
        )
    )
    assert shop_base["merchant_name"] == barista_student["name"]
    assert shop_base["is_student_part_timer"] is True
    assert "pricing_badge" not in shop_base

    # 2. Raise affinity with classmate to 55 (>= 40) -> unlocks "10% Classmate Hookup"!
    school_roster.hydrate_school_character(sid, barista_student)
    db.upsert_contact(
        sid,
        barista_student["npc_id"],
        character_id=char["id"],
        name=barista_student["name"],
        delta_score=55,
    )
    clerk_info = town_roster.get_active_shop_clerk_for_location(
        session_id=sid, location_str=cafe_loc, merchant_type="cafe_merchant", user_id=user_id
    )
    assert clerk_info is not None
    assert clerk_info["price_multiplier"] == 0.90
    assert clerk_info["pricing_badge"] == "10% Classmate Hookup"

    shop_discounted = asyncio.run(
        merchant.generate_merchant_shop(
            party=[(char, user_id)],
            merchant_name="",
            merchant_description="",
            session=sess_now,
            is_phone_shop=False,
            merchant_type="cafe_merchant",
        )
    )
    assert shop_discounted["merchant_name"] == barista_student["name"]
    assert shop_discounted.get("pricing_badge") == "10% Classmate Hookup"
    assert "friend hookup" in shop_discounted["intro_narrative"].lower()

    # 3. Tuesday 22:15 (1335) at Convenience Store -> Delinquent clocked out at 21:30; Night-Shift Clerk is behind register!
    konbini_loc = f"{fmt['commercial_name']} ➔ Convenience Store ➔ Storefront & Checkout Counter"
    db.update_session(sid, current_day=2, current_minute=1335, current_location=konbini_loc)
    sess_late = db.get_session(sid)

    shop_night = asyncio.run(
        merchant.generate_merchant_shop(
            party=[(char, user_id)],
            merchant_name="",
            merchant_description="",
            session=sess_late,
            is_phone_shop=False,
            merchant_type="general_merchant",
        )
    )
    assert shop_night["merchant_name"] == konbini_night["name"]
    assert shop_night["is_student_part_timer"] is False
    assert "pricing_badge" not in shop_night


@pytest.mark.unit
def test_bounty_client_routing_campus_vs_town_errands():
    """Campus favors route to Campus Students/Faculty; off-campus Town Errands route to Citizen/Youth Peer."""
    session = _create_hs_session(770017)
    sid = int(session["id"])
    roster = school_roster.ensure_school_directory_exists(session)
    grade_by_name = {c["name"]: c["grade"] for c in roster}
    fmt = town_roster.get_town_format_kwargs(sid, "high_school_drama")

    # 1. Campus Library request -> Campus Student or Faculty
    campus_client, _ = bounty.resolve_or_seed_bounty_client(
        sid,
        session=session,
        raw_bounty={
            "title": "Missing Reference Ledger",
            "description": "Help locate misplaced club records inside the school library.",
            "client_location": f"{fmt['school_name']} ➔ School Library ➔ Reference Stacks",
        },
        index=1,
    )
    assert campus_client in grade_by_name
    assert grade_by_name[campus_client] not in ("Citizen", "Youth Peer")

    # 2. Off-campus Commuter Station / Delivery errand -> Town Citizen or Youth Peer
    town_client, _ = bounty.resolve_or_seed_bounty_client(
        sid,
        session=session,
        raw_bounty={
            "title": "Urgent Commuter Station Parcel",
            "description": "Deliver an express parcel from the station kiosk to the convenience store.",
            "client_location": f"{fmt['commercial_name']} ➔ Commuter Station & Civic Plaza ➔ Pedestrian Crosswalk & Station Kiosk",
        },
        index=2,
    )
    assert town_client in grade_by_name
    assert grade_by_name[town_client] in ("Citizen", "Youth Peer")
