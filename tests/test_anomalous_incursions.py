import pytest
import scenario_data
from namegen import generate_agency_name, generate_agency_hq_name
from mechanics.world.locations.hierarchy import resolve_session_location_tokens
from mechanics.world.locations.seeds import get_scenario_seed_data


def test_genre_and_modifier_registration():
    genres = scenario_data.load_genres(reload=True)
    assert "urban_fantasy" in genres
    assert genres["urban_fantasy"]["category"] == "genre"
    assert "tactical_combat" in genres["urban_fantasy"]["allowed_mechanics"]
    assert "smartphone_hub" in genres["urban_fantasy"]["allowed_mechanics"]

    assert "horror" in genres
    assert genres["horror"]["category"] == "modifier"


def test_scenario_resolution_and_aliases():
    assert scenario_data.resolve_scenario_key("anomalous_incursions") == "anomalous_incursions"
    assert scenario_data.resolve_scenario_key("urban_anomalies") == "anomalous_incursions"
    assert scenario_data.resolve_scenario_key("anomalies") == "anomalous_incursions"
    assert scenario_data.resolve_scenario_key("scp") == "anomalous_incursions"
    assert scenario_data.resolve_scenario_key("control") == "anomalous_incursions"

    # Tag aliases
    assert scenario_data.resolve_tag_keys("modern") == ["urban_fantasy"]
    assert scenario_data.resolve_tag_keys("paranormal") == ["horror"]
    assert scenario_data.resolve_tag_keys("modern, paranormal") == ["urban_fantasy", "horror"]


def test_starting_hooks_diversity():
    genres = scenario_data.load_genres(reload=True)
    hooks = genres["urban_fantasy"]["starting_hooks"]
    assert len(hooks) == 6

    archetypes = [h["archetype"] for h in hooks]
    assert archetypes.count("hub_launchpad") == 2
    assert archetypes.count("in_media_res") == 2
    assert archetypes.count("delve_threshold") == 2

    # Verify get_dynamic_starting_hook works for anomalous_incursions
    for i in range(10):
        h = scenario_data.get_dynamic_starting_hook("anomalous_incursions", session_id=100 + i, char_name="Operative Vance")
        assert h["archetype"] in ("hub_launchpad", "in_media_res", "delve_threshold")
        assert h["hook_text"]


def test_procedural_agency_and_hq_tokens():
    agency1 = generate_agency_name(hash_val=101)
    agency2 = generate_agency_name(hash_val=202)
    assert agency1 != agency2

    hq1 = resolve_session_location_tokens(101, "{session_agency_hq}", "anomalous_incursions")
    hq2 = resolve_session_location_tokens(202, "{session_agency_hq}", "anomalous_incursions")
    assert hq1 != hq2
    assert "HQ" in hq1
    assert len(agency1.split()) <= 4
    assert len(agency2.split()) <= 4


def test_spatial_topology_tier1_hq():
    seed_data = get_scenario_seed_data("anomalous_incursions")
    assert "zones" in seed_data
    zones = seed_data["zones"]
    assert len(zones) == 15

    expected_zone_ids = {
        "zone_city_center",
        "zone_downtown",
        "zone_uptown",
        "zone_ultra_rich",
        "zone_low_cost_wards",
        "zone_industrial",
        "zone_city_docks",
        "zone_suburbs",
        "zone_school_campus",
        "zone_seaside_beach",
        "zone_woods_reserve",
        "zone_airport",
        "zone_university",
        "zone_chinatown",
        "zone_undercity",
    }
    assert {z["id"] for z in zones} == expected_zone_ids

    cc_zone = next((z for z in zones if z["id"] == "zone_city_center"), None)
    assert cc_zone is not None
    assert cc_zone["is_hub"] is True

    # Verify consolidated mega-complexes reside in their host districts as Tier 2 facilities
    assert any(p["id"] == "loc_general_hospital" for p in cc_zone["primary_locations"])
    uptown_zone = next(z for z in zones if z["id"] == "zone_uptown")
    assert any(p["id"] == "loc_botanical_zoo" for p in uptown_zone["primary_locations"])
    seaside_zone = next(z for z in zones if z["id"] == "zone_seaside_beach")
    assert any(p["id"] == "loc_theme_park" for p in seaside_zone["primary_locations"])
    woods_zone = next(z for z in zones if z["id"] == "zone_woods_reserve")
    assert any(p["id"] == "loc_eastern_temple" for p in woods_zone["primary_locations"])

    hq_loc = next((p for p in cc_zone["primary_locations"] if p["id"] == "loc_agency_hq"), None)
    assert hq_loc is not None
    assert hq_loc["name"] == "{session_agency_hq}"

    # Verify all 10 Tier 3 departments within the HQ Building (Main Lobby + 4 stores + 5 operational/anomalous wings)
    room_ids = {s["id"] for s in hq_loc["sub_locations"]}
    expected_facilities = {
        "loc_hq_main_lobby",
        "loc_hq_tactical_armory",
        "loc_hq_field_outfitter",
        "loc_hq_medical_bay",
        "loc_hq_canteen_cafe",
        "loc_hq_executive_dispatch",
        "loc_hq_research_division",
        "loc_hq_training_range",
        "loc_hq_agent_dormitories",
        "loc_hq_containment_sector",
    }
    assert expected_facilities == room_ids
    assert all(len(s.get("props", [])) >= 2 for s in hq_loc["sub_locations"])

    # Verify each facility across all 15 consolidated zones has >= 6 primaries, entrance rooms, and props
    for z in zones:
        assert len(z["primary_locations"]) >= 6, f"Zone {z['id']} should have at least 6 primary locations"
        for prim in z["primary_locations"]:
            sub_locs = prim["sub_locations"]
            assert any(s.get("is_entrance") == 1 for s in sub_locs), f"Missing entrance for {prim['id']}"
            assert all(len(s.get("props", [])) >= 2 for s in sub_locs), f"Missing props inside {prim['id']}"


def test_hq_merchant_stores_and_multi_tier_transit():
    import db
    from namegen import get_scenario_starter_factions
    from mechanics.world.locations.attributes import (
        location_has_merchant_shop,
        get_available_merchant_types_for_location,
    )
    from mechanics.world.locations.access_gate import get_node_effective_access_info
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from mechanics.world.mobility import calculate_route_travel_time

    # 1. Verify HQ Stores & New Zone Stores map to exact merchant archetypes
    assert location_has_merchant_shop("Aegis Bureau Headquarters ➔ Tactical Armory & Ordnance Depot", "anomalous_incursions")
    armory_types = [m["type"] for m in get_available_merchant_types_for_location("Tactical Armory & Ordnance Depot", "anomalous_incursions")]
    assert "weapon_merchant" in armory_types

    assert location_has_merchant_shop("Aegis Bureau Headquarters ➔ Field Outfitter & Tailoring Quartermaster", "anomalous_incursions")
    outfitter_types = [m["type"] for m in get_available_merchant_types_for_location("Field Outfitter & Tailoring Quartermaster", "anomalous_incursions")]
    assert "armor_merchant" in outfitter_types and "clothes_merchant" in outfitter_types

    assert location_has_merchant_shop("Aegis Bureau Headquarters ➔ Medical & Psychic Cleansing Bay", "anomalous_incursions")
    med_types = [m["type"] for m in get_available_merchant_types_for_location("Medical & Psychic Cleansing Bay", "anomalous_incursions")]
    assert "potion_merchant" in med_types

    assert location_has_merchant_shop("Aegis Bureau Headquarters ➔ Bureau Canteen & Espresso Bar", "anomalous_incursions")
    cafe_types = [m["type"] for m in get_available_merchant_types_for_location("Bureau Canteen & Espresso Bar", "anomalous_incursions")]
    assert "food_merchant" in cafe_types and "cafe_merchant" in cafe_types

    # Eastern Grand Temple Talisman Stand & Theme Park Midway
    assert location_has_merchant_shop("Mount Ryujin Eastern Grand Temple & Sanctuary ➔ Grand Torii Gate & Omikuji Talisman Stand", "anomalous_incursions")
    temple_types = [m["type"] for m in get_available_merchant_types_for_location("Grand Torii Gate & Omikuji Talisman Stand", "anomalous_incursions")]
    assert temple_types == ["gift_merchant"]

    assert location_has_merchant_shop("Starlight Wonder Theme Park & Amusement Resort ➔ Main Gate & Starlight Carnival Midway", "anomalous_incursions")
    tp_types = [m["type"] for m in get_available_merchant_types_for_location("Main Gate & Starlight Carnival Midway", "anomalous_incursions")]
    assert "food_merchant" in tp_types and "gift_merchant" in tp_types

    # Starter factions include Eastern Exorcist Order at loc_et_main_sanctuary
    factions = get_scenario_starter_factions("anomalous_incursions")
    assert any(f.get("hq_location_id") == "loc_et_main_sanctuary" and f.get("category") in ("order", "monastic_order") for f in factions)

    # 2. Verify Procedural Zone/Facility Naming, Multi-Tier Transit, and Theme Park 22:00-08:00 Anomalous Shift
    test_sid_1 = 99887766
    test_sid_2 = 99887767
    with db.get_conn() as conn:
        for sid in (test_sid_1, test_sid_2):
            conn.execute("DELETE FROM world_nodes WHERE session_id=?", (sid,))
            conn.execute("DELETE FROM world_edges WHERE session_id=?", (sid,))
    try:
        ensure_session_spatial_graph_seeded(test_sid_1, scenario_key="anomalous_incursions", char_name="Vance")
        ensure_session_spatial_graph_seeded(test_sid_2, scenario_key="anomalous_incursions", char_name="Vance")

        # Verify dynamic procedural naming across sessions for consolidated facilities (and legacy zone aliases)
        tp_z1 = db.get_world_node(test_sid_1, "loc_theme_park")["name"]
        tp_z2 = db.get_world_node(test_sid_2, "loc_theme_park")["name"]
        assert db.get_world_node(test_sid_1, "zone_theme_park")["node_id"] == "loc_theme_park"
        assert "Theme Park & Amusement Resort" in tp_z1 and tp_z1 != "Theme Park & Amusement Resort"
        assert tp_z1 != tp_z2

        et_z1 = db.get_world_node(test_sid_1, "loc_eastern_temple")["name"]
        assert db.get_world_node(test_sid_1, "zone_eastern_temple")["node_id"] == "loc_eastern_temple"
        assert "Eastern Grand Temple & Sanctuary" in et_z1 and et_z1 != "Eastern Grand Temple & Sanctuary"

        # Verify Private Agency HQs each have 10 operational/store wings & Hostile HQs each have 6 wings
        all_s1_nodes = db.get_session_world_nodes(test_sid_1)
        p1_wings = [n for n in all_s1_nodes if n.get("parent_id") == "loc_private_hq_1"]
        p2_wings = [n for n in all_s1_nodes if n.get("parent_id") == "loc_private_hq_2"]
        cult_wings = [n for n in all_s1_nodes if n.get("parent_id") == "loc_cult_sanctum_hq"]
        synd_wings = [n for n in all_s1_nodes if n.get("parent_id") == "loc_clandestine_syndicate_hq"]
        assert len(p1_wings) == 10 and len(p2_wings) == 10
        assert len(cult_wings) == 6 and len(synd_wings) == 6
        assert db.find_shortest_graph_path_minutes(test_sid_1, "sub_priv1_entrance", "sub_priv1_armory") == 3
        assert location_has_merchant_shop("Syndicate Tactical Armory & Requisition Depot", "anomalous_incursions")
        assert location_has_merchant_shop("Bespoke Ballistic Outfitter & Tailoring Atelier", "anomalous_incursions")
        assert location_has_merchant_shop("Corporate Trauma & Psychic Detox Clinic", "anomalous_incursions")
        assert location_has_merchant_shop("Skyline Executive Espresso Bar & Canteen", "anomalous_incursions")

        hq_armory_1 = db.get_world_node(test_sid_1, "loc_hq_tactical_armory")["name"]
        hq_vault_1 = db.get_world_node(test_sid_1, "loc_hq_containment_sector")["name"]
        assert ":" in hq_armory_1 and "Tactical Armory & Ordnance Depot" in hq_armory_1
        assert ":" in hq_vault_1 and "Subterranean Containment & Quarantine Sector" in hq_vault_1

        # Verify Theme Park closes at 22:00 (1320) -> Anomalous Shift until 08:00 (480)
        day_info = get_node_effective_access_info(test_sid_1, "loc_tp_main_midway", current_day=1, current_minute=840, scen_key="anomalous_incursions")
        assert day_info["curfew_active"] is False
        assert "Open" in day_info["status_badge"]

        night_10pm = get_node_effective_access_info(test_sid_1, "loc_tp_main_midway", current_day=1, current_minute=1320, scen_key="anomalous_incursions")
        assert night_10pm["curfew_active"] is True
        assert night_10pm["schedule_reason_code"] == "theme_park_anomalous_shift"
        assert "Anomalous Shift" in night_10pm["status_badge"]

        night_2am = get_node_effective_access_info(test_sid_1, "loc_tp_coaster_plaza", current_day=2, current_minute=120, scen_key="anomalous_incursions")
        assert night_2am["curfew_active"] is True
        assert night_2am["schedule_reason_code"] == "theme_park_anomalous_shift"

        reopen_8am = get_node_effective_access_info(test_sid_1, "loc_tp_main_midway", current_day=2, current_minute=480, scen_key="anomalous_incursions")
        assert reopen_8am["curfew_active"] is False

        # Verify Multi-Tier Urban Transit Graph in SQLite
        hq_lobby_to_armory = db.find_shortest_graph_path_minutes(test_sid_1, "loc_hq_main_lobby", "loc_hq_tactical_armory")
        assert hq_lobby_to_armory == 3

        cc_intra = db.find_shortest_graph_path_minutes(test_sid_1, "loc_metro_transit_terminal", "loc_sunken_plaza")
        assert cc_intra == 5

        hq_to_cc = db.find_shortest_graph_path_minutes(test_sid_1, "loc_hq_main_lobby", "loc_metro_transit_terminal")
        assert 10 <= hq_to_cc <= 15

        cc_to_tp = db.find_shortest_graph_path_minutes(test_sid_1, "loc_metro_transit_terminal", "loc_tp_main_midway")
        assert 15 <= cc_to_tp <= 25

        cc_to_temple = db.find_shortest_graph_path_minutes(test_sid_1, "loc_metro_transit_terminal", "loc_et_torii_approach")
        assert 20 <= cc_to_temple <= 30

        cc_to_woods = db.find_shortest_graph_path_minutes(test_sid_1, "loc_metro_transit_terminal", "loc_forest_trails")
        assert 30 <= cc_to_woods <= 45

        stateless_outskirts = calculate_route_travel_time(
            "City Center ➔ Central Transit Terminal",
            "Woods & Mountain Reserve ➔ Pine Forest Hiking Trails",
            scen_key="anomalous_incursions",
            session_id=0,
        )
        assert 30 <= stateless_outskirts <= 45
    finally:
        with db.get_conn() as conn:
            for sid in (test_sid_1, test_sid_2):
                conn.execute("DELETE FROM world_nodes WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM world_edges WHERE session_id=?", (sid,))


def test_scenario_variants():
    scenarios = scenario_data.load_scenarios(reload=True)
    
    # Base
    base = scenarios["anomalous_incursions"]
    assert base["tags"] == ["urban_fantasy", "horror"]
    assert "grade" not in base["tone_guidelines"].lower()

    # NSFW + Gore
    unrated = scenarios["nsfw_gore_anomalous_incursions"]
    assert set(unrated["tags"]) == {"urban_fantasy", "horror", "nsfw", "gore"}
    assert scenario_data.is_nsfw_scenario("nsfw_gore_anomalous_incursions")
    assert scenario_data.is_gore_scenario("nsfw_gore_anomalous_incursions")

    # Furry
    furry = scenarios["furry_anomalous_incursions"]
    assert set(furry["tags"]) == {"urban_fantasy", "horror", "furry"}
    assert scenario_data.has_tag("furry_anomalous_incursions", "furry")

    # Furry + NSFW + Gore
    feral_carnage = scenarios["nsfw_furry_gore_anomalous_incursions"]
    assert set(feral_carnage["tags"]) == {"urban_fantasy", "horror", "furry", "nsfw", "gore"}
    assert scenario_data.is_nsfw_scenario("nsfw_furry_gore_anomalous_incursions")
    assert scenario_data.is_gore_scenario("nsfw_furry_gore_anomalous_incursions")
    assert scenario_data.has_tag("nsfw_furry_gore_anomalous_incursions", "furry")


def test_factions_promotion_meter_and_44_special_agents():
    import db
    from mechanics.social.factions import (
        ensure_starter_factions,
        get_anomalous_faction_state,
        join_or_transfer_anomalous_faction,
        update_agent_promotion_reputation,
        infer_anomalous_faction_archetype,
    )
    from mechanics.social.agent_roster import (
        ensure_anomalous_agent_roster,
        evaluate_anomalous_companion_recruitment,
    )
    from mechanics.world.locations.access_gate import get_node_effective_access_info
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded

    test_uid = 99112201
    char = db.create_character(
        user_id=test_uid,
        name="Agent Kurosawa",
        char_class="Anomaly Investigator",
        gender="Female",
        race="Human",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        factions = ensure_starter_factions(sid, "anomalous_incursions")
        assert len(factions) == 6
        archetypes = {infer_anomalous_faction_archetype(f) for f in factions}
        assert archetypes == {
            "public_agency",
            "private_agency_1",
            "private_agency_2",
            "monastic_order",
            "cult_faction",
            "clandestine_faction",
        }

        # Cult and Clandestine Syndicate cannot be joined
        res_cult = join_or_transfer_anomalous_faction(sid, "cult_faction", user_id=test_uid)
        assert res_cult["success"] is False

        # Join Public Agency -> Tier 1 (0 Rep)
        res_pub = join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        assert res_pub["success"] is True
        state = get_anomalous_faction_state(sid, user_id=test_uid)
        assert state["faction_archetype_key"] == "public_agency"
        assert state["promotion_tier"] == 1
        assert state["promotion_rep"] == 0

        # Probationary Floor (0 Rep): missing mandatory bounty suspends salary without expulsion
        miss_res = update_agent_promotion_reputation(sid, -15, is_missed_mandatory=True, user_id=test_uid)
        assert miss_res["new_rep"] == 0
        assert miss_res["salary_ration_suspended"] is True

        # Completing mandatory bounty clears suspension and grants Rep -> promotes across tiers
        comp_res = update_agent_promotion_reputation(sid, 25, is_mandatory_completion=True, user_id=test_uid)
        assert comp_res["new_rep"] == 25
        assert comp_res["new_tier"] == 2
        assert comp_res["salary_ration_suspended"] is False

        # Check Tiered HQ Access Gates: Public Agency member accesses Bureau Vault, blocked from Private #1 Inner Armory & Cult Sanctum
        ensure_session_spatial_graph_seeded(sid, scenario_key="anomalous_incursions", char_name="Agent Kurosawa")
        pub_vault = get_node_effective_access_info(sid, "loc_hq_containment_sector", scen_key="anomalous_incursions")
        assert pub_vault["access_tier"] == "open"
        priv1_shell = get_node_effective_access_info(sid, "loc_private_hq_1", scen_key="anomalous_incursions")
        assert priv1_shell["access_tier"] == "open"
        priv1_lobby = get_node_effective_access_info(sid, "sub_priv1_dispatch", scen_key="anomalous_incursions")
        assert priv1_lobby["access_tier"] == "open"
        priv1_inner = get_node_effective_access_info(sid, "sub_priv1_armory", scen_key="anomalous_incursions")
        assert priv1_inner["access_tier"] == "restricted"
        priv1_vault = get_node_effective_access_info(sid, "sub_priv1_vault", scen_key="anomalous_incursions")
        assert priv1_vault["access_tier"] == "restricted"
        cult_hq = get_node_effective_access_info(sid, "loc_cult_sanctum_hq", scen_key="anomalous_incursions")
        assert cult_hq["access_tier"] == "restricted"
        cult_altar = get_node_effective_access_info(sid, "sub_cult_altar", scen_key="anomalous_incursions")
        assert cult_altar["access_tier"] == "restricted"

        update_agent_promotion_reputation(sid, 65, user_id=test_uid)  # 90 Rep -> Tier 5 Elite Agent
        assert get_anomalous_faction_state(sid, user_id=test_uid)["promotion_tier"] == 5

        # Seed 44 Special Agents & verify recruitment rules
        roster = ensure_anomalous_agent_roster(sid, "anomalous_incursions")
        assert len(roster) == 44
        for ag in roster:
            assert len(ag["innate_abilities"]) == 5

        # Reset to Tier 2 (25 Rep) to test colleague vs senior vs distrusted recruitment
        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        update_agent_promotion_reputation(sid, 25, user_id=test_uid)
        sess_dict = db.get_session(sid)

        t1_colleague = next(a for a in roster if a["faction_id"] == "public_agency" and a["agent_tier"] == 1)
        rec_t1 = evaluate_anomalous_companion_recruitment(sess_dict, test_uid, {"name": t1_colleague["name"]}, affinity_score=0)
        assert rec_t1["allowed"] is True and rec_t1["cost"] == 0

        t5_director = next(a for a in roster if a["faction_id"] == "public_agency" and a["agent_tier"] == 5)
        rec_t5_low = evaluate_anomalous_companion_recruitment(sess_dict, test_uid, {"name": t5_director["name"]}, affinity_score=20)
        assert rec_t5_low["allowed"] is False
        rec_t5_friend = evaluate_anomalous_companion_recruitment(sess_dict, test_uid, {"name": t5_director["name"]}, affinity_score=100)
        assert rec_t5_friend["allowed"] is True and rec_t5_friend["cost"] == 0

        cult_agent = next(a for a in roster if a["faction_id"] == "cult_faction")
        rec_cult_low = evaluate_anomalous_companion_recruitment(sess_dict, test_uid, {"name": cult_agent["name"]}, affinity_score=100)
        assert rec_cult_low["allowed"] is False
        rec_cult_defector = evaluate_anomalous_companion_recruitment(sess_dict, test_uid, {"name": cult_agent["name"]}, affinity_score=150)
        assert rec_cult_defector["allowed"] is True
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


def test_anomalous_gear_spells_and_faction_starter_loadouts():
    import character_data as cd
    import db
    from mechanics.combat.items.anomalous_gear import (
        apply_anomalous_incursions_gear_rules,
        ANOMALOUS_ELEMENTS,
        sync_equipped_anomalous_spells,
    )
    from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon
    from mechanics.combat.spells.kits import calculate_spell_damage
    from mechanics.combat.spells.registry import get_spell

    # 1. Non-anomalous weapon has zero fantasy elemental tags; Anomalous weapon gets elemental tag + optional spell
    base_w = gen_weapon("anomalous_incursions", "Weapon", tier=3, name="Bureau Issue Service Pistol")
    non_anom = apply_anomalous_incursions_gear_rules(
        dict(base_w), "anomalous_incursions", slot="Weapon", tier=3, force_anomalous=False
    )
    assert non_anom["metadata"]["is_anomalous"] is False
    assert "anomalous" not in non_anom["metadata"].get("tags", [])
    assert non_anom["metadata"].get("damage_type") in (None, "physical")

    anom_w = apply_anomalous_incursions_gear_rules(
        gen_weapon("anomalous_incursions", "Weapon", tier=1, name="Carbon-Steel Tactical Katana"),
        "anomalous_incursions",
        slot="Weapon",
        tier=1,
        force_anomalous=True,
        force_granted_spell=True,
    )
    assert anom_w["metadata"]["is_anomalous"] is True
    assert anom_w["metadata"]["element"] in ANOMALOUS_ELEMENTS
    assert anom_w["name"].startswith("[Anomalous]")
    assert isinstance(anom_w["metadata"].get("granted_spell"), dict)
    granted_id = anom_w["metadata"]["granted_spell_id"]

    # Non-eligible slots (Head, Gloves, Shoes, Bottom) never grant spells even when forced
    from mechanics.combat.items.shoes import generate_random_equipment as generate_random_shoes
    anom_shoes = apply_anomalous_incursions_gear_rules(
        generate_random_shoes("anomalous_incursions", "Shoes", tier=1),
        "anomalous_incursions",
        slot="Shoes",
        tier=1,
        force_anomalous=True,
        force_granted_spell=True,
    )
    assert anom_shoes["metadata"]["is_anomalous"] is True
    assert "granted_spell" not in anom_shoes["metadata"]

    # 2. Equip / Unequip & Duplicate +20% Empowerment
    test_uid = 99112202
    char = db.create_character(
        user_id=test_uid,
        name="Operative Lin",
        char_class="Pact Contractor",
        gender="Male",
        race="Wolf Beastfolk",
        scenario="furry_anomalous_incursions",
    )
    try:
        # Faction starter loadouts theme distinctly & support Tail-Slotted for furry variant
        monastic_loadout = cd.generate_starter_equipment_loadout(
            scenario="furry_anomalous_incursions",
            char_class="Pact Contractor",
            gender="Male",
            race="Wolf Beastfolk",
            weapon_name="Carbon-Steel Tactical Katana",
            starting_faction="monastic_order",
        )
        assert any(k in monastic_loadout["Top"]["name"] for k in ("Haori", "Kosode", "Gi"))
        assert "Tail-Slotted" in monastic_loadout["Bottom"]["name"]

        priv_loadout = cd.generate_starter_equipment_loadout(
            scenario="anomalous_incursions",
            char_class="Occult Marksman",
            gender="Female",
            race="Human",
            weapon_name="Suppressed Scout Carbine",
            starting_faction="private_agency_1",
        )
        assert any(k in priv_loadout["Top"]["name"] for k in ("Corporate", "Operator", "Executive"))

        start_items = cd.get_starting_items("anomalous_incursions", "Anomaly Investigator", starting_faction="monastic_order")
        item_names = [it[0] for it in start_items]
        assert any("Medkit" in n for n in item_names)
        assert any("Purging Salt" in n for n in item_names)

        db.apply_adventure_loadout(
            user_id=test_uid,
            scenario="furry_anomalous_incursions",
            char_class="Pact Contractor",
            gear_map=monastic_loadout,
            starting_items=start_items,
        )
        base_spells = db.get_learned_spells(test_uid)
        assert len(base_spells) >= 5  # 5 innate abilities (+ any rolled starter granted spells)

        # Equip anomalous weapon with granted_id -> spell dynamically added
        wid = db.add_item(test_uid, anom_w["name"], "Weapon", anom_w["effect"], 1, force=True)
        db.equip_item(test_uid, wid, "Weapon")
        assert granted_id in db.get_learned_spells(test_uid)

        # Equip second item granting the EXACT same spell_id -> duplicate_empowered (+20% damage)
        from mechanics.combat.items.accessories import generate_random_equipment as generate_random_accessory
        acc_dup = generate_random_accessory("anomalous_incursions", "Accessory 1", tier=2)
        acc_dup["metadata"]["is_anomalous"] = True
        acc_dup["metadata"]["granted_spell"] = anom_w["metadata"]["granted_spell"]
        acc_dup["metadata"]["granted_spell_id"] = granted_id
        from mechanics.combat.items.envelope import serialize_item
        acc_dup["effect"] = serialize_item(acc_dup["metadata"])
        aid = db.add_item(test_uid, acc_dup["name"], "Accessory", acc_dup["effect"], 1, force=True)
        db.equip_item(test_uid, aid, "Accessory 1")

        sp_empowered = dict(get_spell(granted_id))
        assert sp_empowered.get("duplicate_empowered") is True
        sp_normal = dict(sp_empowered, duplicate_empowered=False)
        dmg_norm = calculate_spell_damage(100, sp_normal, defender_attrs={"innate_magic_dr": 0.0, "gear_dr": {}, "innate_magic_dt": 0})
        dmg_emp = calculate_spell_damage(100, sp_empowered, defender_attrs={"innate_magic_dr": 0.0, "gear_dr": {}, "innate_magic_dt": 0})
        if dmg_norm > 5:
            assert dmg_emp > dmg_norm

        # Unequip both -> granted spell removed while 5 innate spells remain intact!
        db.unequip_slot(test_uid, "Weapon")
        db.unequip_slot(test_uid, "Accessory 1")
        sync_res = sync_equipped_anomalous_spells(test_uid)
        if granted_id not in db.get_skill_progress(db.get_character(test_uid)).get("innate_spells", []):
            assert granted_id not in sync_res["learned_spells"]
        assert len(sync_res["learned_spells"]) >= 5
    finally:
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_story_arc_bounties_confiscation_merchants_and_extraction():
    import db
    from game_engine.quests import (
        create_contextual_story_quest_data,
        apply_quest_update,
    )
    from mechanics.narrative.blueprints import (
        get_max_campaign_chapters,
        ensure_world_ending_anomaly_blueprint,
    )
    from mechanics.narrative.bounty import (
        generate_faction_bounty_board,
        evaluate_anomalous_bounty_eligibility,
        dispatch_anomalous_mandatory_daily_bounty,
        should_confiscate_anomalous_combat_loot,
    )
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        infer_anomalous_faction_archetype,
        get_anomalous_faction_state,
    )
    from mechanics.combat.merchant import get_anomalous_shop_faction_context
    from mechanics.combat.enemies import should_allow_random_encounter
    from mechanics.world.anomalous_events import (
        resolve_anomalous_emergency_extraction,
        resolve_anomalous_starting_location,
        roll_daily_anomalous_incursions,
        resolve_non_hostile_incursion_action,
    )

    test_uid = 99112203
    char = db.create_character(
        user_id=test_uid,
        name="Agent Sato",
        char_class="Public Safety Field Hunter",
        gender="Male",
        race="Human",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        # 1. Starting Location resolver maps each faction to its canonical world_node_id
        loc_pub = resolve_anomalous_starting_location(sid, "public_agency", "anomalous_incursions", "Agent Sato")
        assert loc_pub["node_id"] in ("sub_hq_reception_rotunda", "sub_hq_lobby_checkpoint", "loc_hq_main_lobby")
        loc_mon = resolve_anomalous_starting_location(sid, "monastic_order", "anomalous_incursions", "Agent Sato")
        assert loc_mon["node_id"] in ("sub_et_incense_courtyard", "sub_et_deity_altar", "loc_et_main_sanctuary")
        loc_free = resolve_anomalous_starting_location(sid, "freelancer", "anomalous_incursions", "Agent Sato")
        assert loc_free["node_id"] in ("sub_player_living_room", "sub_player_front_porch", "loc_player_house")

        # 2. 11-Chapter Story Arc & Chapter 11 Epilogue Flag
        assert get_max_campaign_chapters("anomalous_incursions") == 11
        cataclysm = ensure_world_ending_anomaly_blueprint(sid)
        assert cataclysm.get("name") and cataclysm.get("foreshadow_sign")

        sess = db.get_session(sid)
        ch1 = create_contextual_story_quest_data(sid, sess, chapter_num=1)
        assert ch1.get("title") and ch1.get("sub_objectives")
        ch10 = create_contextual_story_quest_data(sid, sess, chapter_num=10)
        assert cataclysm["name"] in ch10["title"] or cataclysm["name"] in ch10["objective"]
        ch11 = create_contextual_story_quest_data(sid, sess, chapter_num=11)
        db.set_session_chapter(sid, 11)
        done_subs = [dict(so, completed=True) for so in (ch11.get("sub_objectives") or [])]
        db.upsert_quest(
            session_id=sid,
            quest_id="SQ-CH11",
            quest_type="Story Quest",
            title=ch11["title"],
            objective=ch11["objective"],
            reward_xp=500,
            reward_gold=300,
            is_story_quest=True,
            sub_objectives=done_subs,
        )
        apply_quest_update(sid, {"quest_id": "SQ-CH11", "status": "Completed"}, party_user_ids=[test_uid])
        updated_sess = db.get_session(sid)
        assert updated_sess.get("epilogue_ready") is True
        assert any("Endless Containment Mode" in (c.get("label", "") if isinstance(c, dict) else str(c)) for c in (updated_sess.get("epilogue_choices") or []))

        # 3. Faction Bounty Eligibility Matrix & Taxpayer Confiscation
        factions = ensure_starter_factions(sid, "anomalous_incursions")
        fac_by_arch = {infer_anomalous_faction_archetype(f): f for f in factions}
        sess_cur = db.get_session(sid)

        # Cult & Clandestine boards have 0 bounties
        assert await generate_faction_bounty_board(sess_cur, fac_by_arch["cult_faction"]) == []
        assert await generate_faction_bounty_board(sess_cur, fac_by_arch["clandestine_faction"]) == []

        pub_bounties = await generate_faction_bounty_board(sess_cur, fac_by_arch["public_agency"])
        priv1_bounties = await generate_faction_bounty_board(sess_cur, fac_by_arch["private_agency_1"])
        priv2_bounties = await generate_faction_bounty_board(sess_cur, fac_by_arch["private_agency_2"])
        mon_bounties = await generate_faction_bounty_board(sess_cur, fac_by_arch["monastic_order"])
        assert len(pub_bounties) >= 1 and len(priv1_bounties) >= 1 and len(mon_bounties) >= 1

        # Public Agency member: allowed Public & Freelance, blocked from Private & Monastic
        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, pub_bounties[0])["allowed"] is True
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, priv1_bounties[0])["allowed"] is False
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, mon_bounties[0])["allowed"] is False

        # Public Agency Taxpayer Mandate: 0G & 0 Item on Public Bounty claim + Combat Loot Confiscation
        db.apply_hp_mp_delta(test_uid, gold_delta=200)
        gold_before = db.get_character(test_uid)["gold"]
        mand_q = dispatch_anomalous_mandatory_daily_bounty(sid, 1, "public_agency", "Public Agency", "anomalous_incursions")
        mand_db = db.get_quest_by_id(sid, mand_q["quest_id"])
        assert mand_db and "mandatory_daily:1" in mand_db["quest_notes"]
        assert should_confiscate_anomalous_combat_loot(sid, db.get_session(sid), user_id=test_uid) is True
        db.update_quest_status(sid, mand_q["quest_id"], "Completed")
        claim_res = db.claim_quest_reward(sid, mand_q["quest_id"], [test_uid])
        assert claim_res["gold"] == 0
        assert not claim_res.get("item")
        assert db.get_character(test_uid)["gold"] == gold_before
        assert get_anomalous_faction_state(sid, user_id=test_uid)["promotion_rep"] >= 10

        # Private Agency #1 member: allowed Private #1 & Public contract work, blocked from Rival Private #2 & Monastic
        join_or_transfer_anomalous_faction(sid, "private_agency_1", user_id=test_uid)
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, priv1_bounties[0])["allowed"] is True
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, pub_bounties[0])["allowed"] is True
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, priv2_bounties[0])["allowed"] is False
        assert evaluate_anomalous_bounty_eligibility(sid, test_uid, mon_bounties[0])["allowed"] is False
        assert should_confiscate_anomalous_combat_loot(sid, db.get_session(sid), user_id=test_uid) is False

        # 4. Merchant Rules: Private Agency blocked for Freelancer; Public 50% discount for Public member; Monastic 0G daily rations
        join_or_transfer_anomalous_faction(sid, "freelancer", user_id=test_uid)
        m_priv_blocked = get_anomalous_shop_faction_context(db.get_session(sid), f"{fac_by_arch['private_agency_1']['name']} Regional Tower HQ", user_id=test_uid)
        assert m_priv_blocked["allowed"] is False
        m_pub_full = get_anomalous_shop_faction_context(db.get_session(sid), "Aegis Bureau Headquarters ➔ Tactical Armory & Ordnance Depot", user_id=test_uid)
        assert m_pub_full["allowed"] is True and m_pub_full["price_multiplier"] == 1.0

        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        m_pub_half = get_anomalous_shop_faction_context(db.get_session(sid), "Aegis Bureau Headquarters ➔ Tactical Armory & Ordnance Depot", user_id=test_uid)
        assert m_pub_half["allowed"] is True and m_pub_half["price_multiplier"] == 0.50

        join_or_transfer_anomalous_faction(sid, "monastic_order", user_id=test_uid)
        m_mon_free = get_anomalous_shop_faction_context(db.get_session(sid), "Eastern Grand Temple ➔ Grand Torii Gate & Omikuji Talisman Stand", user_id=test_uid)
        assert m_mon_free["allowed"] is True and m_mon_free["is_monastic_free_ration"] is True and m_mon_free["price_multiplier"] == 0.0

        # 5. Conditional Random Encounters: 0% in normal city, active (25%) ONLY in Anomalous Locations & Theme Park 22:00-08:00
        assert should_allow_random_encounter("anomalous_incursions", "City Center ➔ Sunken Plaza Galleria", "loc_sunken_plaza", current_minute=720, session_id=sid) == (False, 0.0)
        assert should_allow_random_encounter("anomalous_incursions", "Theme Park ➔ Main Midway", "loc_tp_main_midway", current_minute=720, session_id=sid) == (False, 0.0)
        assert should_allow_random_encounter("anomalous_incursions", "Theme Park ➔ Main Midway", "loc_tp_main_midway", current_minute=1380, session_id=sid) == (True, 0.25)
        assert should_allow_random_encounter("anomalous_incursions", "Hospital ➔ Floor 13", "loc_hosp_floor_13", current_minute=720, session_id=sid) == (True, 0.25)

        # 6. Daily Incursions & Emergency Medical Extraction (0G Monastic vs 10% capped 100G Freelancer)
        inc_roll = roll_daily_anomalous_incursions(sid, 1, scen_key="anomalous_incursions")
        assert 2 <= len(inc_roll["incursions"]) <= 3
        non_hostile = next((inc for inc in inc_roll["incursions"] if inc.get("subtype") != "hostile_breach"), None)
        if non_hostile:
            pac_res = resolve_non_hostile_incursion_action(sid, test_uid, non_hostile["incursion_id"], action_type="pacify", force_roll=18)
            assert pac_res["success"] is True

        db.update_character_fields(test_uid, hp=0, gold=2500)
        ext_mon = resolve_anomalous_emergency_extraction(sid, test_uid, apply_vitals_to_db=True)
        assert ext_mon["fee_charged"] == 0
        assert db.get_character(test_uid)["hp"] > 0

        join_or_transfer_anomalous_faction(sid, "freelancer", user_id=test_uid)
        db.update_character_fields(test_uid, hp=0, gold=2500)
        ext_free = resolve_anomalous_emergency_extraction(sid, test_uid, apply_vitals_to_db=True)
        assert ext_free["fee_charged"] == 100  # 10% of 2500G capped at 100G!
        assert db.get_character(test_uid)["gold"] == 2400
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


def test_audit_gear_stripping_empowerment_cleanup_and_no_spellbooks():
    import json
    import db
    import character_data as cd
    from mechanics.combat.items.armors import generate_random_equipment as gen_armor
    from mechanics.combat.items.shields import generate_random_equipment as gen_shield
    from mechanics.combat.items.accessories import generate_random_equipment as gen_accessory
    from mechanics.combat.items.anomalous_gear import (
        apply_anomalous_incursions_gear_rules,
        sync_equipped_anomalous_spells,
    )
    from mechanics.combat.spells import (
        get_spell,
        generate_procedural_spell,
        generate_procedural_spellbook_item,
    )
    from mechanics.combat.equipment import generate_spellbook_item
    from mechanics.combat.items.consumables.usage import apply_item_to_target
    from mechanics.combat.items.envelope import serialize_item

    # 1. Non-anomalous Armor / Shield / Accessory have modern urban names and zero elemental leak
    fantasy_banned = ("magic robe", "grimoire", "aegis", "amulet", "arcane", "dragonscale", "mithril")
    for gen_fn, slot in ((gen_armor, "Armor"), (gen_shield, "Shield"), (gen_accessory, "Accessory 1")):
        raw = gen_fn("anomalous_incursions", slot, tier=2)
        clean = apply_anomalous_incursions_gear_rules(raw, "anomalous_incursions", slot=slot, tier=2, force_anomalous=False)
        assert clean["metadata"].get("is_anomalous") is False
        low_name = clean["name"].lower()
        assert not any(fb in low_name for fb in fantasy_banned), f"Fantasy name leaked: {clean['name']}"
        meta = clean["metadata"]
        for k in list(meta.keys()):
            if k.endswith("_atk") or k.endswith("_res"):
                assert meta[k] in (0, 0.0, None), f"Elemental stat {k}={meta[k]} leaked on non-anomalous {slot}"
        assert not meta.get("omni_res")
        assert not meta.get("magic_dt")
        for dt_k in (meta.get("type_dt") or {}):
            assert dt_k in (
                "slash", "slashing", "stabbing", "pierce", "piercing", "blunt", "bludgeoning",
                "ballistic", "kinetic", "physical", "explosive", "sonic",
                "pistol_round", "rifle_round", "scatter_shot", "high_caliber_round", "arrow", "bolt",
            )

    # 2. Shock / Ice / Holy elements map cleanly into procedural spell generation
    for elem, expected in (("shock", "lightning"), ("ice", "cold"), ("holy", "radiant")):
        sp = generate_procedural_spell(scenario="anomalous_incursions", tier=2, element=elem)
        assert sp["damage_type"] == expected

    # 3. Spellbook generators return scenario potions in Anomalous Incursions; spellbook consumption blocked even with session=None
    sb1 = generate_procedural_spellbook_item(scenario="anomalous_incursions", tier=2)
    sb2 = generate_spellbook_item(scenario="anomalous_incursions", tier=2)
    assert sb1.get("item_type") != "Spellbook" and "Spellbook" not in sb1["name"]
    assert sb2.get("item_type") != "Spellbook" and "Spellbook" not in sb2["name"]

    test_uid = 99112204
    char = db.create_character(
        user_id=test_uid,
        name="Operative Kurosawa",
        char_class="Anomaly Investigator",
        gender="Female",
        race="Human",
        scenario="anomalous_incursions",
    )
    try:
        fake_sb = {
            "id": 999999,
            "name": "Spellbook: Void Lance",
            "item_type": "Spellbook",
            "effect": "[SPELLBOOK_JSON]" + json.dumps({"spell_id": "fireball"}),
        }
        ok_sb, msg_sb = apply_item_to_target(test_uid, fake_sb, "self", "self", session=None)
        assert ok_sb is False
        assert "Innate Ability Restriction" in msg_sb

        # 4. Duplicate empowerment on an INNATE ability resets cleanly on db.remove_item & never leaks duplicate_empowered=True to DB
        loadout = cd.generate_starter_equipment_loadout(
            scenario="anomalous_incursions",
            char_class="Anomaly Investigator",
            gender="Female",
            race="Human",
            weapon_name="Service 9mm Sidearm",
            starting_faction="public_agency",
        )
        db.apply_adventure_loadout(
            user_id=test_uid,
            scenario="anomalous_incursions",
            char_class="Anomaly Investigator",
            gear_map=loadout,
        )
        sp_prog = db.get_skill_progress(db.get_character(test_uid))
        innate_ids = list(sp_prog.get("innate_spells") or [])
        assert len(innate_ids) == 5
        target_innate_id = innate_ids[0]
        target_innate_def = dict(get_spell(target_innate_id))
        target_innate_def["duplicate_empowered"] = False

        acc_emp = apply_anomalous_incursions_gear_rules(
            gen_accessory("anomalous_incursions", "Accessory 1", tier=1),
            "anomalous_incursions",
            slot="Accessory 1",
            tier=1,
            force_anomalous=True,
        )
        acc_emp["metadata"]["granted_spell"] = target_innate_def
        acc_emp["metadata"]["granted_spell_id"] = target_innate_id
        acc_emp["effect"] = serialize_item(acc_emp["metadata"])

        aid = db.add_item(test_uid, acc_emp["name"], "Accessory", acc_emp["effect"], 1, force=True)
        db.equip_item(test_uid, aid, "Accessory 1")

        sp_live = get_spell(target_innate_id)
        assert sp_live.get("duplicate_empowered") is True
        sp_prog_after = db.get_skill_progress(db.get_character(test_uid))
        assert target_innate_id in (sp_prog_after.get("empowered_granted_spells") or [])

        # Persisted procedural_spells row must NOT store duplicate_empowered=True
        db_proc = db.get_procedural_spell(target_innate_id)
        if db_proc:
            assert not db_proc.get("duplicate_empowered")

        # Directly removing equipped item via db.remove_item revokes empowerment while preserving the innate spell
        db.remove_item(test_uid, aid)
        assert target_innate_id in db.get_learned_spells(test_uid)
        assert not get_spell(target_innate_id).get("duplicate_empowered")
        sp_prog_clean = db.get_skill_progress(db.get_character(test_uid))
        assert target_innate_id not in (sp_prog_clean.get("empowered_granted_spells") or [])
    finally:
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_audit_live_incursions_non_lethal_subdue_and_extraction_reducers():
    import db
    from mechanics.world.anomalous_events import (
        bootstrap_anomalous_session,
        get_active_incursion_at_location,
        record_contained_anomaly_to_vault_log,
    )
    from mechanics.combat.enemies import should_allow_random_encounter
    from mechanics.combat.core import precompute_combat_turn, reconcile_combat_results
    from game_engine.state.reducers import _reduce_vitals_and_inventory
    from mechanics.social.factions import (
        join_or_transfer_anomalous_faction,
        get_anomalous_faction_state,
    )

    test_uid = 99112205
    char = db.create_character(
        user_id=test_uid,
        name="Operative Ren",
        char_class="Field Containment Specialist",
        gender="Male",
        race="Human",
        scenario="anomalous_incursions",
        stats={"STR": 6, "PER": 2, "END": 4, "CHA": 2, "INT": 2, "AGI": 4, "LUK": 2},
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        # 1. bootstrap_anomalous_session sets HQ location, Mandatory Bounty, Incursions, and Phone SMS messages
        boot = bootstrap_anomalous_session(
            session_id=sid,
            scenario_key="anomalous_incursions",
            user_id=test_uid,
            starting_faction="private_agency_2",
            char_name="Operative Ren",
        )
        fac_st = get_anomalous_faction_state(sid, user_id=test_uid)
        assert fac_st["faction_archetype_key"] == "private_agency_2"
        assert boot["mandatory_bounty"] and boot["mandatory_bounty"]["quest_id"].startswith("MAND-")
        assert 2 <= len(boot.get("daily_incursions") or []) <= 3

        watch_msgs = db.get_phone_messages(sid, "Metropolitan Anomaly Watch")
        disp_msgs = db.get_phone_messages(sid, f"{fac_st['joined_faction_name']} Dispatch")
        assert len(watch_msgs) >= 1 and "ANOMALY ALERT" in watch_msgs[-1]["message"].upper()
        assert len(disp_msgs) >= 1 and "MANDATORY DAILY DISPATCH" in disp_msgs[-1]["message"].upper()

        # 2. Active incursion lookup & suppression of duplicate random encounters at incursion node
        inc0 = boot["daily_incursions"][0]
        matched_inc = get_active_incursion_at_location(sid, location_str=inc0["location"], node_id=inc0.get("node_id", ""))
        assert matched_inc and matched_inc["incursion_id"] == inc0["incursion_id"]
        allow_re, prob_re = should_allow_random_encounter(
            "anomalous_incursions",
            inc0["location"],
            inc0.get("node_id", ""),
            current_minute=1380,
            session_id=sid,
        )
        assert (allow_re, prob_re) == (False, 0.0)

        # 3. requires_non_lethal_subdue: <= 35% HP unlocks 🛡️ Subdue & Contain (+ 🗣️ Persuade / Calm), while lethal damage kills at 0 HP!
        subdue_enemy = {
            "name": "Weeping Porcelain Mannequin",
            "hp": 30,
            "max_hp": 100,
            "str": 2,
            "agi": 1,
            "end": 1,
            "xp_value": 45,
            "gold_value": 60,
            "requires_non_lethal_subdue": True,
            "subdue_threshold_pct": 0.35,
            "category_tag": "haunting",
            "incursion_id": inc0["incursion_id"],
        }
        sess_sub = db.get_session(sid)
        sess_sub["nearby_enemies"] = [dict(subdue_enemy)]
        party = [(db.get_character(test_uid), {})]
        pre = precompute_combat_turn(
            session=sess_sub,
            party=party,
            actions=[{"user_id": test_uid, "char": db.get_character(test_uid), "label": "Attempt to feint", "tier": "fail"}],
        )
        surviving = [e for e in pre["surviving_enemies"] if e["name"] == "Weeping Porcelain Mannequin"]
        assert len(surviving) == 1 and surviving[0]["hp"] == 30
        outcome_sub = {"narrative": "The entity wavers within capture range!", "next_choices": [{"label": "Keep pressing", "stat": "STR", "requirement": 5}]}
        reconcile_combat_results(sess_sub, outcome_sub, pre, party=party)
        choice_labels_sub = [str(ch.get("label", "")) for ch in (outcome_sub.get("choices") or []) if isinstance(ch, dict)]
        assert any("Subdue & Contain" in lbl for lbl in choice_labels_sub)
        assert any("Persuade / Calm" in lbl for lbl in choice_labels_sub)

        vault_entry = record_contained_anomaly_to_vault_log(
            session_id=sid,
            entity_name="Weeping Porcelain Mannequin",
            category_tag="haunting",
            subtype="non_hostile_entity",
            location=inc0["location"],
            resolution_method="Subdued Non-Lethally & Contained",
            user_id=test_uid,
        )
        assert vault_entry["entity_name"] == "Weeping Porcelain Mannequin"
        assert any(v["entity_name"] == "Weeping Porcelain Mannequin" for v in (db.get_session(sid).get("contained_anomalies_log") or []))

        # 4. Combat gold (_combat_gold) is credited by reducers for Private Agency, and 0 HP Extraction copay (_authorized_gold_spend) deducts cleanly
        db.update_character_fields(test_uid, hp=50, gold=500)
        sess_win = db.get_session(sid)
        sess_win["nearby_enemies"] = []
        outcome_win = {"narrative": "Target neutralized.", "choices": [{"label": "Continue", "stat": "AGI", "requirement": 5}]}
        win_pre = {
            "dead_enemies": ["Rift Hound"],
            "dead_enemy_dicts": [{"name": "Rift Hound", "gold_value": 55, "xp_value": 30}],
            "xp_gain": 30,
            "gold_gain": 55,
            "player_damage_by_name": {"Operative Ren": 0},
            "player_damage_taken": 0,
            "acting_char_name": "Operative Ren",
            "combat_log": [],
        }
        reconcile_combat_results(sess_win, outcome_win, win_pre, party=[(db.get_character(test_uid), {})])
        assert outcome_win.get("_combat_gold") == 55
        _reduce_vitals_and_inventory(
            session_id=sid,
            session=sess_win,
            party=[(db.get_character(test_uid), {})],
            outcome=outcome_win,
            mp_already_spent={},
            scen_key="anomalous_incursions",
            is_combat=True,
            items_gained_by_user={},
            actions=[],
        )
        assert db.get_character(test_uid)["gold"] == 555

        # Now test 0 HP Emergency Extraction for Freelancer through reconcile_combat_results + _reduce_vitals_and_inventory
        join_or_transfer_anomalous_faction(sid, "freelancer", user_id=test_uid)
        db.update_character_fields(test_uid, hp=10, gold=500)
        sess_ko = db.get_session(sid)
        sess_ko["nearby_enemies"] = [{"name": "Abyssal Stalker", "hp": 80, "max_hp": 80}]
        outcome_ko = {"narrative": "Overwhelmed.", "choices": []}
        ko_pre = {
            "dead_enemies": [],
            "dead_enemy_dicts": [],
            "xp_gain": 0,
            "gold_gain": 0,
            "player_damage_by_name": {"Operative Ren": 25},
            "player_damage_taken": 25,
            "acting_char_name": "Operative Ren",
            "combat_log": [],
        }
        reconcile_combat_results(sess_ko, outcome_ko, ko_pre, party=[(db.get_character(test_uid), {})])
        assert outcome_ko.get("_anomalous_extracted") is True
        assert outcome_ko.get("_authorized_gold_spend") == 50
        _reduce_vitals_and_inventory(
            session_id=sid,
            session=sess_ko,
            party=[(db.get_character(test_uid), {})],
            outcome=outcome_ko,
            mp_already_spent={},
            scen_key="anomalous_incursions",
            is_combat=True,
            items_gained_by_user={},
            actions=[],
        )
        after_ko = db.get_character(test_uid)
        assert after_ko["hp"] > 0
        assert after_ko["gold"] == 450  # 10% of 500G = 50G Hospital copay cleanly deducted
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_audit_bounty_isolation_shrine_cap_world_gates_and_faction_lock():
    import db
    from mechanics.narrative.bounty import (
        generate_bounty_board,
        generate_faction_bounty_board,
        replenish_daily_bounties_deterministic,
    )
    from mechanics.combat.merchant import (
        generate_merchant_shop,
        evaluate_items_for_sale,
    )
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        infer_anomalous_faction_archetype,
    )
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from mechanics.world.locations.access_gate import evaluate_node_access_gate
    from mechanics.world.world_schedule import resolve_genre_schedule_key
    from game_engine.state.reducers import _reduce_factions

    assert resolve_genre_schedule_key("anomalous_incursions") == "urban_fantasy"

    test_uid = 99112206
    char = db.create_character(
        user_id=test_uid,
        name="Initiate Miko",
        char_class="Shrine Exorcist",
        gender="Female",
        race="Human",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        ensure_session_spatial_graph_seeded(sid, "anomalous_incursions")
        factions = ensure_starter_factions(sid, "anomalous_incursions")
        fac_by_arch = {infer_anomalous_faction_archetype(f): f for f in factions}

        # 1. Generate HQ faction bounties first, then verify Smartphone Freelance App board excludes FBNT- / faction: rows
        await generate_faction_bounty_board(db.get_session(sid), fac_by_arch["public_agency"])
        general_board = await generate_bounty_board(db.get_session(sid), force_refresh=True)
        assert len(general_board) >= 1
        for bq in general_board:
            assert not str(bq.get("quest_id", "")).startswith("FBNT-")
            assert "faction:" not in str(bq.get("quest_notes", "")).lower()

        rep_board = replenish_daily_bounties_deterministic(sid)
        for bq in rep_board:
            assert not str(bq.get("quest_id", "")).startswith("FBNT-")

        # 2. Monastic Shrine daily sacred items have quantity=1, 0G effective grant price, and 0G resale value
        from mechanics.combat.merchant import get_anomalous_shop_faction_context
        join_or_transfer_anomalous_faction(sid, "monastic_order", user_id=test_uid)
        sess_mon = db.get_session(sid)
        sess_mon["current_location"] = "Eastern Grand Temple ➔ Grand Torii Gate & Omikuji Talisman Stand"
        shrine_shop = await generate_merchant_shop(
            party=[(db.get_character(test_uid), {})],
            merchant_name="Shrine Talisman Maiden",
            merchant_description="Guardian of consecrated relics",
            session=sess_mon,
            merchant_type="general_merchant",
        )
        assert 1 <= len(shrine_shop["stock"]) <= 3
        shrine_ctx = get_anomalous_shop_faction_context(sess_mon, sess_mon["current_location"], user_id=test_uid)
        assert shrine_ctx["is_monastic_free_ration"] is True and shrine_ctx["price_multiplier"] == 0.0
        assert all(it.get("quantity") == 1 for it in shrine_shop["stock"])

        shrine_item = {
            "name": shrine_shop["stock"][0]["name"],
            "item_type": shrine_shop["stock"][0]["item_type"],
            "effect": shrine_shop["stock"][0].get("effect", ""),
            "shrine_sacred_grant": True,
        }
        sale_prices = await evaluate_items_for_sale([shrine_item])
        assert sale_prices[shrine_item["name"]] == 0

        # 3. _reduce_factions blocks hallucinated 7th factions in Anomalous Incursions
        _reduce_factions(
            session_id=sid,
            session=db.get_session(sid),
            outcome={
                "faction_updates": [
                    {"faction_name": "Seventh Hallucinated Order", "reputation_delta": 25, "promote_rank": True}
                ]
            },
            party=[(db.get_character(test_uid), {})],
            first_char_id=char["id"],
        )
        all_facs = db.get_factions(sid)
        assert len(all_facs) == 6
        assert not any("Hallucinated" in f["name"] for f in all_facs)

        # 4. HQ Parapsychology Lab has NO 20:00-07:00 school curfew for Public Agency members at 23:00 (minute 1380)
        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        sess_night = db.get_session(sid)
        sess_night["current_minute"] = 1380  # 23:00
        gate_lab = evaluate_node_access_gate(
            sid,
            "loc_hq_research_division",
            sess_night,
            actions=[{"label": "Enter Research Division"}],
            party=[(db.get_character(test_uid), {})],
        )
        assert gate_lab.get("gated") is False

        # 5. Access gate word-boundary check on restricted sector: "Brass Keychain" & "Whiskey" do NOT unlock, while "Security Keycard" DOES
        join_or_transfer_anomalous_faction(sid, "freelancer", user_id=test_uid)
        sess_lock = db.get_session(sid)
        sess_lock["current_minute"] = 720
        gate_false_key = evaluate_node_access_gate(
            sid,
            "loc_hq_containment_sector",
            sess_lock,
            actions=[{"label": "Walk inside"}],
            party=[({"inventory": [{"name": "Brass Keychain"}, {"name": "Aged Whiskey"}]}, {})],
        )
        assert gate_false_key.get("gated") is True

        gate_real_key = evaluate_node_access_gate(
            sid,
            "loc_hq_containment_sector",
            sess_lock,
            actions=[{"label": "Walk inside"}],
            party=[({"inventory": [{"name": "Bureau Security Keycard"}]}, {})],
        )
        assert gate_real_key.get("gated") is False
        assert gate_real_key.get("unlocked_by") == "key"
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_non_hostile_entity_narrative_and_combat_containment_end_to_end():
    """
    Verifies the complete Non-Hostile Anomalous Entity Containment design:
      1. Out-of-Combat 4-Approach Choices (Persuade [CHA], Calm [PER], Outwit [INT], Use Environment [AGI])
         on both 'Secure Non-Hostile Anomalous Entity' Bounties and Daily Non-Hostile Incursions.
      2. Temperament-Driven Repeated Failure Escalation (2/2 Strikes):
         - 'timid' -> Escapes! Hard-fails Side/Mandatory Bounties; forfeits Daily Incursion rewards.
         - 'volatile' -> Turns Hostile! Spawns into combat without failing the bounty yet.
      3. In-Combat Non-Lethal Containment:
         - '🗣️ Persuade / Calm' available at ANY HP > 0; calms & contains on success.
         - '🛡️ Subdue & Contain' unlocks ONLY at <= 35% HP; captures & contains cleanly.
      4. Lethal Kill (0 HP — no 1 HP clamp!) & Consequences:
         - Mandatory Daily Bounty: Hard-fails, deducts -15 Promotion Rep immediately, and does NOT double-penalize at midnight rollover.
         - Story Quest Sub-Objective: Fails-forward via 'dire_cost' (-5 HP backlash, NOT logged to Vault).
         - Daily Non-Hostile Incursion: Marks killed_lethally=True, 0G/0 XP, suppresses loot choice, NOT logged to Vault.
    """
    import db
    from mechanics.world.anomalous_events import (
        build_non_hostile_narrative_choices,
        resolve_non_hostile_incursion_action,
        resolve_anomalous_combat_containment,
        process_anomalous_daily_rollover,
    )
    from mechanics.world.waypoints.choices import generate_quest_action_choices, tag_and_enrich_quest_choices
    from mechanics.narrative.choice_generator import generate_categorized_combat_actions
    from mechanics.combat import precompute_combat_turn, reconcile_combat_results
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        get_anomalous_faction_state,
        save_anomalous_faction_state,
    )
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from game_engine.quests import handle_failed_quest_skill_check, apply_quest_approach_effects

    test_uid = 99112207
    char = db.create_character(
        user_id=test_uid,
        name="Agent Kurosawa",
        char_class="Field Investigator",
        gender="Male",
        race="Human",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        ensure_session_spatial_graph_seeded(sid, "anomalous_incursions")
        ensure_starter_factions(sid, "anomalous_incursions")
        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        target_loc = "City Center ➔ Sunken Plaza Galleria ➔ Fountain Atrium"
        db.update_session(sid, current_location=target_loc)

        # --- PART 1: Out-of-Combat 4-Approach Choices & Clean Narrative Containment ---
        db.upsert_quest(
            session_id=sid,
            quest_id="BNT-NH-PACIFY",
            quest_type="Secure Non-Hostile Anomalous Entity",
            title="Live Capture: Mirror-Glass Stray Hound",
            objective="Contain 'Mirror-Glass Stray Hound' alive at Sunken Plaza Galleria.",
            status="Active",
            reward_xp=140,
            reward_gold=80,
            quest_notes="board_source:freelance_app|non_hostile_temperament:timid|entity_name:Mirror-Glass Stray Hound",
            client_npc="Dispatcher Mei",
            client_location=target_loc,
        )
        db.save_quest_waypoints(
            sid,
            "BNT-NH-PACIFY",
            [
                {"stage_index": 1, "stage_label": "Arrive at Sunken Plaza", "target_location": target_loc, "completion_trigger": "arrival", "status": "completed"},
                {"stage_index": 2, "stage_label": "Encounter and contain non-hostile entity 'Mirror-Glass Stray Hound' alive", "target_location": target_loc, "completion_trigger": "skill_check", "status": "active"},
            ],
        )

        q_choices = generate_quest_action_choices(sid, target_loc, scen_key="anomalous_incursions", char=db.get_character(test_uid))
        assert len(q_choices) == 4
        approaches_set = {c["approach"] for c in q_choices}
        stats_set = {c["stat"] for c in q_choices}
        assert approaches_set == {"nh_persuade", "nh_calm", "nh_outwit", "nh_environment"}
        assert stats_set == {"CHA", "PER", "INT", "AGI"}

        enriched = tag_and_enrich_quest_choices(
            [{"label": "Look around the plaza", "stat": "PER", "requirement": 4}],
            session_id=sid,
            current_location=target_loc,
            scen_key="anomalous_incursions",
            char=db.get_character(test_uid),
        )
        enriched_apps = {c.get("approach") for c in enriched if c.get("quest_id") == "BNT-NH-PACIFY"}
        assert enriched_apps == {"nh_persuade", "nh_calm", "nh_outwit", "nh_environment"}

        q_nh = db.get_quest_by_id(sid, "BNT-NH-PACIFY")
        wp_nh = db.get_active_waypoint(sid, "BNT-NH-PACIFY")
        eff_res = apply_quest_approach_effects(
            session_id=sid,
            quest=q_nh,
            waypoint=wp_nh,
            approach="nh_calm",
            gold_cost=0,
            party_user_ids=[test_uid],
            session=db.get_session(sid),
        )
        assert eff_res.get("entity_contained") is True
        db.update_quest_status(sid, "BNT-NH-PACIFY", "Completed")
        db.claim_quest_reward(sid, "BNT-NH-PACIFY", [test_uid])
        vault_logs = [
            v for v in (db.get_session(sid).get("contained_anomalies_log") or [])
            if v.get("quest_id") == "BNT-NH-PACIFY"
        ]
        assert len(vault_logs) == 1, "Vault log must record the contained entity exactly once (deduplicated on claim)!"
        assert vault_logs[0]["entity_name"] == "Mirror-Glass Stray Hound"

        # --- PART 2: Timid Bounty Repeated Failures -> Strike 1 Warning -> Strike 2 Entity Escapes & Hard-Fails ---
        db.upsert_quest(
            session_id=sid,
            quest_id="BNT-NH-TIMID",
            quest_type="Secure Non-Hostile Anomalous Entity",
            title="Live Capture: Origami Crane Swarm",
            objective="Contain 'Origami Crane Swarm' alive.",
            status="Active",
            reward_xp=130,
            reward_gold=70,
            quest_notes="board_source:freelance_app|non_hostile_temperament:timid|entity_name:Origami Crane Swarm",
            client_npc="Archivist Ren",
        )
        db.save_quest_waypoints(
            sid,
            "BNT-NH-TIMID",
            [
                {"stage_index": 1, "stage_label": "Arrive at site", "target_location": target_loc, "completion_trigger": "arrival", "status": "completed"},
                {"stage_index": 2, "stage_label": "Encounter and contain non-hostile entity 'Origami Crane Swarm' alive", "target_location": target_loc, "completion_trigger": "skill_check", "status": "active"},
            ],
        )
        q_timid = db.get_quest_by_id(sid, "BNT-NH-TIMID")
        wp_timid = db.get_active_waypoint(sid, "BNT-NH-TIMID")
        s1_timid = handle_failed_quest_skill_check(sid, q_timid, wp_timid, "fail", [test_uid], session=db.get_session(sid))
        assert s1_timid["failed"] is False and s1_timid["temperament"] == "timid"
        assert "escape" in s1_timid["directive"].lower()
        assert db.get_quest_by_id(sid, "BNT-NH-TIMID")["status"] == "Active"

        s2_timid = handle_failed_quest_skill_check(sid, q_timid, wp_timid, "fail", [test_uid], session=db.get_session(sid))
        assert s2_timid["failed"] is True and s2_timid.get("escaped") is True
        q_timid_after = db.get_quest_by_id(sid, "BNT-NH-TIMID")
        assert q_timid_after["status"] == "Failed"
        assert "Escaped" in q_timid_after["progress"]
        assert not db.get_session(sid).get("pending_retaliation")

        # --- PART 3: Volatile Bounty -> Turns Hostile at 2/2 Strikes -> In-Combat Persuade/Calm Succeeds ---
        db.upsert_quest(
            session_id=sid,
            quest_id="BNT-NH-VOLATILE",
            quest_type="Secure Non-Hostile Anomalous Entity",
            title="Live Capture: Static-Cloaked Stag",
            objective="Contain 'Static-Cloaked Stag' alive.",
            status="Active",
            reward_xp=150,
            reward_gold=90,
            quest_notes="board_source:freelance_app|non_hostile_temperament:volatile|entity_name:Static-Cloaked Stag",
        )
        db.save_quest_waypoints(
            sid,
            "BNT-NH-VOLATILE",
            [
                {"stage_index": 1, "stage_label": "Arrive at site", "target_location": target_loc, "completion_trigger": "arrival", "status": "completed"},
                {"stage_index": 2, "stage_label": "Encounter and contain non-hostile entity 'Static-Cloaked Stag' alive", "target_location": target_loc, "completion_trigger": "skill_check", "status": "active"},
            ],
        )
        q_vol = db.get_quest_by_id(sid, "BNT-NH-VOLATILE")
        wp_vol = db.get_active_waypoint(sid, "BNT-NH-VOLATILE")
        s1_vol = handle_failed_quest_skill_check(sid, q_vol, wp_vol, "fail", [test_uid], session=db.get_session(sid))
        assert s1_vol["failed"] is False and s1_vol["temperament"] == "volatile"

        sess_vol = db.get_session(sid)
        s2_vol = handle_failed_quest_skill_check(sid, q_vol, wp_vol, "fail", [test_uid], session=sess_vol)
        assert s2_vol["failed"] is False and s2_vol["agitated"] is True and s2_vol["combat_started"] is True
        assert db.get_quest_by_id(sid, "BNT-NH-VOLATILE")["status"] == "Active"
        enemies_now = db.get_session(sid).get("nearby_enemies") or []
        assert len(enemies_now) == 1
        stag_enemy = enemies_now[0]
        assert stag_enemy["name"] == "Static-Cloaked Stag"
        assert stag_enemy["requires_non_lethal_subdue"] is True
        assert stag_enemy["linked_quest_id"] == "BNT-NH-VOLATILE"

        # At 100% HP: Persuade/Calm IS in categorized tactics, Subdue & Contain is NOT yet unlocked
        cat_full = generate_categorized_combat_actions([(db.get_character(test_uid), [])], stag_enemy, location=target_loc, scenario="anomalous_incursions")
        tactic_lbls_full = [t["label"] for t in cat_full["tactics"]]
        assert any("Persuade / Calm Static-Cloaked Stag" in l for l in tactic_lbls_full)
        assert not any("Subdue & Contain" in l for l in tactic_lbls_full)

        # Premature subdue above 35% HP refuses to capture and keeps combat active
        premature = resolve_anomalous_combat_containment(sid, test_uid, action_type="subdue", quest_id="BNT-NH-VOLATILE", party_user_ids=[test_uid])
        assert premature["success"] is False and premature.get("combat_continues") is True

        # Successful In-Combat Persuade / Calm at full HP calms & contains the Stag, clears combat, and completes the bounty!
        persuade_win = resolve_anomalous_combat_containment(
            sid, test_uid, action_type="combat_persuade", quest_id="BNT-NH-VOLATILE", force_roll=19, party_user_ids=[test_uid]
        )
        assert persuade_win["success"] is True and persuade_win["subdued"] is True
        assert (db.get_session(sid).get("nearby_enemies") or []) == []
        assert db.get_quest_by_id(sid, "BNT-NH-VOLATILE")["status"] == "Completed"
        assert any(v["entity_name"] == "Static-Cloaked Stag" for v in (db.get_session(sid).get("contained_anomalies_log") or []))

        # --- PART 4: Lethal Combat Kill (0 HP) on Mandatory Daily Bounty -> Hard-Fail + -15 Rep (No Midnight Double-Penalty) ---
        fac_st = get_anomalous_faction_state(sid, user_id=test_uid)
        fac_st["promotion_rep"] = 40
        fac_st["mandatory_bounty_id"] = "MAND-NH-KILL"
        fac_st["mandatory_bounty_completed_today"] = False
        fac_st["mandatory_bounty_penalized_today"] = False
        fac_st["last_rollover_day"] = 1
        save_anomalous_faction_state(sid, fac_st, user_id=test_uid)

        db.upsert_quest(
            session_id=sid,
            quest_id="MAND-NH-KILL",
            quest_type="Secure Non-Hostile Anomalous Entity",
            title="[Mandatory] Live Capture: Bell-Chime Moth",
            objective="Contain 'Bell-Chime Moth' alive before 24:00.",
            status="Active",
            reward_xp=160,
            reward_gold=75,
            quest_notes="mandatory_daily:1|faction:public_agency|board_source:public_agency|rep_reward:15|non_hostile_temperament:volatile|entity_name:Bell-Chime Moth",
        )
        db.save_quest_waypoints(
            sid,
            "MAND-NH-KILL",
            [{"stage_index": 1, "stage_label": "Contain 'Bell-Chime Moth' alive", "target_location": target_loc, "completion_trigger": "skill_check", "status": "active"}],
        )
        moth_enemy = {
            "name": "Bell-Chime Moth",
            "hp": 5,
            "max_hp": 60,
            "str": 2,
            "agi": 1,
            "end": 1,
            "requires_non_lethal_subdue": True,
            "subdue_threshold_pct": 0.35,
            "linked_quest_id": "MAND-NH-KILL",
        }
        sess_kill = db.get_session(sid)
        sess_kill["nearby_enemies"] = [moth_enemy]
        party_k = [(db.get_character(test_uid), {})]
        pre_kill = precompute_combat_turn(
            session=sess_kill,
            party=party_k,
            actions=[{"user_id": test_uid, "char": db.get_character(test_uid), "label": "Slash Bell-Chime Moth", "tier": "crit_success"}],
        )
        assert pre_kill["surviving_enemies"] == [], "Lethal combat attack MUST kill at 0 HP without any 1 HP clamp!"
        assert "Bell-Chime Moth" in pre_kill["dead_enemies"]
        assert pre_kill["gold_gain"] == 0 and pre_kill["xp_gain"] == 0

        out_kill = {"narrative": "The moth shatters.", "next_choices": []}
        reconcile_combat_results(sess_kill, out_kill, pre_kill, party=party_k)
        assert not out_kill.get("_combat_gold")
        assert not any("loot" in str(c.get("label", "")).lower() for c in (out_kill.get("choices") or []) if isinstance(c, dict))
        assert db.get_quest_by_id(sid, "MAND-NH-KILL")["status"] == "Failed"
        fac_after_kill = get_anomalous_faction_state(sid, user_id=test_uid)
        assert fac_after_kill["promotion_rep"] == 25  # 40 - 15 = 25
        assert fac_after_kill["mandatory_bounty_penalized_today"] is True

        # Midnight rollover to Day 2 must NOT deduct -15 a second time!
        rollover_res = process_anomalous_daily_rollover(sid, new_day=2, party_uids=[test_uid])
        assert rollover_res["processed"] is True
        assert get_anomalous_faction_state(sid, user_id=test_uid)["promotion_rep"] == 25

        # --- PART 5: Story Quest Sub-Objective Lethal Kill -> Dire Cost Fail-Forward (-5 HP, NOT Failed, NOT Vault Logged) ---
        db.update_character_fields(test_uid, hp=25, max_hp=30)
        db.upsert_quest(
            session_id=sid,
            quest_id="SQ-CH3-NH",
            quest_type="Secure Non-Hostile Anomalous Entity",
            title="Chapter 3: Echoes in the Atrium",
            objective="Investigate and contain the sentient echo.",
            status="Active",
            is_story_quest=True,
            sub_objectives=[{"id": 1, "text": "Contain Non-Hostile Entity: Lantern-Light Child", "completed": False}],
            quest_notes="non_hostile_temperament:volatile|entity_name:Lantern-Light Child",
        )
        db.save_quest_waypoints(
            sid,
            "SQ-CH3-NH",
            [{"stage_index": 1, "stage_label": "Contain 'Lantern-Light Child' alive", "target_location": target_loc, "completion_trigger": "skill_check", "status": "active"}],
            sub_obj_id=1,
        )
        sq_enemy = {
            "name": "Lantern-Light Child",
            "hp": 4,
            "max_hp": 50,
            "str": 2,
            "agi": 1,
            "end": 1,
            "requires_non_lethal_subdue": True,
            "linked_quest_id": "SQ-CH3-NH",
            "linked_sub_obj_id": 1,
            "is_story_quest": True,
        }
        sess_sq = db.get_session(sid)
        sess_sq["nearby_enemies"] = [sq_enemy]
        pre_sq = precompute_combat_turn(
            session=sess_sq,
            party=[(db.get_character(test_uid), {})],
            actions=[{"user_id": test_uid, "char": db.get_character(test_uid), "label": "Strike Lantern-Light Child", "tier": "success"}],
        )
        out_sq = {"narrative": "Backlash erupts.", "next_choices": []}
        reconcile_combat_results(sess_sq, out_sq, pre_sq, party=[(db.get_character(test_uid), {})])
        sq_after = db.get_quest_by_id(sid, "SQ-CH3-NH")
        assert sq_after["status"] == "Active"  # Story Quest never hard-fails!
        assert sq_after["sub_objectives"][0]["completed"] is True
        assert sq_after["sub_objectives"][0]["resolution_approach"] == "dire_cost"
        assert db.get_character(test_uid)["hp"] == 20  # 25 - 5 = 20 HP backlash
        assert not any(v["entity_name"] == "Lantern-Light Child" for v in (db.get_session(sid).get("contained_anomalies_log") or []))

        # --- PART 6: Daily Non-Hostile Incursions (4 Choices, Timid Escape, Volatile Agitation + <= 35% Subdue) ---
        inc_choices = build_non_hostile_narrative_choices("Subway Ticket-Gate Sprite", mode="incursion", incursion_id="inc_test_1")
        assert len(inc_choices) == 4
        assert {c["incursion_action"] for c in inc_choices} == {"persuade", "calm", "outwit", "environment"}

        custom_incs = [
            {
                "incursion_id": "inc_timid_1",
                "day": 2,
                "subtype": "non_hostile_entity",
                "temperament": "timid",
                "category_tag": "spatial_warp",
                "entity_name": "Subway Ticket-Gate Sprite",
                "description": "Timid sprite",
                "preferred_stat": "AGI",
                "location": target_loc,
                "node_id": "",
                "resolved": False,
                "agitated": False,
                "escaped": False,
                "strikes": 0,
                "max_strikes": 2,
                "reward_gold": 120,
                "reward_xp": 85,
            },
            {
                "incursion_id": "inc_vol_1",
                "day": 2,
                "subtype": "non_hostile_entity",
                "temperament": "volatile",
                "category_tag": "haunting",
                "entity_name": "Weeping Porcelain Mannequin",
                "description": "Volatile mannequin",
                "preferred_stat": "CHA",
                "location": target_loc,
                "node_id": "",
                "resolved": False,
                "agitated": False,
                "escaped": False,
                "strikes": 0,
                "max_strikes": 2,
                "reward_gold": 125,
                "reward_xp": 90,
            },
        ]
        db.update_session(sid, nearby_enemies=[], extra={"daily_incursions": custom_incs})
        gold_pre_inc = db.get_character(test_uid)["gold"]

        # Timid Incursion: 2 failed rolls (roll=3 -> +1 strike each) -> escapes with 0G!
        t_r1 = resolve_non_hostile_incursion_action(sid, test_uid, "inc_timid_1", action_type="persuade", force_roll=3)
        assert t_r1["resolved"] is False and t_r1["strikes"] == 1
        t_r2 = resolve_non_hostile_incursion_action(sid, test_uid, "inc_timid_1", action_type="calm", force_roll=3)
        assert t_r2["resolved"] is True and t_r2["escaped"] is True
        assert db.get_character(test_uid)["gold"] == gold_pre_inc
        assert not any(v["entity_name"] == "Subway Ticket-Gate Sprite" for v in (db.get_session(sid).get("contained_anomalies_log") or []))

        # Volatile Incursion: 2 failed rolls -> agitates into combat -> weaken to <= 35% HP -> Subdue & Contain awards full rewards!
        v_r1 = resolve_non_hostile_incursion_action(sid, test_uid, "inc_vol_1", action_type="outwit", force_roll=3)
        assert v_r1["resolved"] is False and v_r1["strikes"] == 1
        v_r2 = resolve_non_hostile_incursion_action(sid, test_uid, "inc_vol_1", action_type="environment", force_roll=3)
        assert v_r2["agitated"] is True and v_r2["combat_started"] is True
        inc_enemies = db.get_session(sid).get("nearby_enemies") or []
        assert len(inc_enemies) == 1
        inc_enemies[0]["hp"] = max(1, int(inc_enemies[0]["max_hp"] * 0.30))
        db.update_session(sid, nearby_enemies=inc_enemies)

        sub_win = resolve_non_hostile_incursion_action(sid, test_uid, "inc_vol_1", action_type="subdue")
        assert sub_win["success"] is True and sub_win["subdued"] is True
        assert db.get_character(test_uid)["gold"] == gold_pre_inc + 125
        assert (db.get_session(sid).get("nearby_enemies") or []) == []
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_faction_themed_classes_weapons_and_loadouts_end_to_end():
    """
    Verifies that every Anomalous Incursions faction has distinct class presets,
    distinct starting weapons, and distinct starter gear & consumables both in
    templates and during dynamic equipment generation / rerolls.
    """
    import character_data as cd
    import db
    from api.auth_characters import get_class_templates, preview_character_gear, PreviewGearRequest, create_character, CharacterCreateRequest

    factions = ["public_agency", "private_agency_1", "private_agency_2", "monastic_order", "freelancer"]
    seen_classes = set()
    seen_weapons = set()

    # 1. Verify get_class_templates & get_starting_weapons per faction
    for fac in factions:
        cls_dict = cd.get_class_templates("anomalous_incursions", starting_faction=fac)
        wpn_list = cd.get_starting_weapons("anomalous_incursions", starting_faction=fac)

        assert len(cls_dict) == 5, f"Faction {fac} must have 5 classes, got {len(cls_dict)}"
        assert len(wpn_list) == 6, f"Faction {fac} must have 6 starting weapons, got {len(wpn_list)}"

        # Verify classes and weapons are distinct across factions
        fac_class_names = set(cls_dict.keys())
        assert len(fac_class_names.intersection(seen_classes)) == 0, f"Overlapping classes found for {fac}: {fac_class_names.intersection(seen_classes)}"
        seen_classes.update(fac_class_names)

        fac_wpn_names = set(wpn_list)
        assert len(fac_wpn_names.intersection(seen_weapons)) == 0, f"Overlapping weapons found for {fac}: {fac_wpn_names.intersection(seen_weapons)}"
        seen_weapons.update(fac_wpn_names)

    assert len(seen_classes) == 25, f"Expected 25 unique faction classes, got {len(seen_classes)}"
    assert len(seen_weapons) == 30, f"Expected 30 unique faction starting weapons, got {len(seen_weapons)}"

    # 2. Verify API /api/class-templates returns faction_classes and faction_starting_weapons
    api_res = await get_class_templates(scenario="anomalous_incursions", starting_faction="monastic_order")
    assert api_res["is_anomalous_incursions"] is True
    assert "Shrine Exorcist Ascetic" in api_res["classes"]
    assert "Purifying Shrine Naginata" in api_res["starting_weapons"]
    assert len(api_res["faction_classes"]) == 5
    assert len(api_res["faction_starting_weapons"]) == 5

    # 3. Verify Preview Gear & Equipment Reroll for each faction
    test_cases = [
        ("public_agency", "Bureau Forensic Investigator", "Bureau Issue Service Pistol", ("bureau", "agency")),
        ("private_agency_1", "Corporate PMC Breacher", "Apex Custom Assault Carbine", ("corporate", "operator", "executive")),
        ("private_agency_2", "Cyber-Occult Technologist", "Arc-Discharge Coil Rifle", ("hazard", "hazmat", "vanguard", "nanite", "composite", "cyber", "flux")),
        ("monastic_order", "Shrine Exorcist Ascetic", "Purifying Shrine Naginata", ("haori", "kosode", "shrine", "monastic", "do-maru", "hemp")),
        ("freelancer", "Underground Occult Broker", "Concealed Snub-Nose Revolver", ("leather", "hoodie", "windbreaker", "duster", "soft-armor", "plate")),
    ]

    for idx, (fac, cls_name, wpn_name, expected_top_keyword) in enumerate(test_cases):
        req = PreviewGearRequest(
            char_class=cls_name,
            scenario="anomalous_incursions",
            starting_weapon=wpn_name,
            starting_faction=fac,
            force_dynamic=True,
            gender="Female",
            race="Human",
        )
        prev = await preview_character_gear(req)
        assert prev["success"] is True
        loadout = prev["loadout"]
        items = prev["starting_items"]

        # Weapon verified
        assert loadout.get("Weapon") is not None
        assert wpn_name in loadout["Weapon"]["name"]

        # Thematic top / armor verified
        top_name = loadout.get("Top", {}).get("name", "").lower()
        armor_name = loadout.get("Armor", {}).get("name", "").lower()
        assert any(k in top_name or k in armor_name for k in expected_top_keyword), (
            f"Expected one of {expected_top_keyword} in {fac} gear, got Top={top_name}, Armor={armor_name}"
        )

        # Faction consumables & class tools verified
        item_names = [it["name"] for it in items]
        assert any("Medkit" in n for n in item_names)
        assert len(items) >= 3

        # 4. Verify SQLite creation & equipping
        create_uid = 999800000 + idx
        c_req = CharacterCreateRequest(
            user_id=create_uid,
            name=f"Operative_{fac}",
            gender="Female",
            race="Human",
            class_name=cls_name,
            scenario="anomalous_incursions",
            starting_faction=fac,
            starting_weapon=wpn_name,
            str_val=2, per=2, end=2, cha=1, int_val=2, agi=2, luk=1
        )
        c_res = await create_character(c_req)
        assert c_res["success"] is True
        char_obj = db.get_character(create_uid)
        assert char_obj["char_class"] == cls_name
        equipped = db.get_equipment(create_uid)
        assert equipped.get("Weapon") is not None
        assert wpn_name in equipped["Weapon"]["name"]
        db.delete_character(create_uid, char_obj["id"])


def test_phase_b_agent_roster_resolution_eta_badges_and_genre_transit():
    """
    Phase B regression guard:
    1. All 44 Special Agents' primary_facility and secondary_facility resolve cleanly to seeded world nodes.
    2. get_zone_summary_tree populates real travel_minutes & travel_tag ETAs on zones, primaries, and rooms.
    3. Genre-weighted cross-zone travel times scale realistically (Fantasy overland trek > Urban local transit).
    4. All retired legacy aliases in db/world.py have zero overlap with active node IDs.
    """
    import db
    from db.world import _LEGACY_NODE_ID_ALIASES
    from mechanics.social.agent_roster import ensure_anomalous_agent_roster
    from mechanics.world.locations import ensure_session_locations_seeded, get_zone_summary_tree
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from mechanics.world.mobility import calculate_route_travel_time

    test_uid = 999809999
    char = db.create_character(
        user_id=test_uid,
        name="Agent PhaseB",
        gender="Female",
        race="Human",
        char_class="Anomaly Investigator",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    sid_fantasy = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="fantasy",
        character_id=char["id"],
    )
    try:
        ensure_session_locations_seeded(sid, "anomalous_incursions", char_name="Agent PhaseB")
        ensure_session_spatial_graph_seeded(sid, scenario_key="anomalous_incursions", char_name="Agent PhaseB")

        # 1. Verify all 44 Special Agents' primary_facility & secondary_facility resolve cleanly
        roster = ensure_anomalous_agent_roster(sid, "anomalous_incursions")
        assert len(roster) == 44
        for ag in roster:
            p_fac = ag.get("primary_facility") or ""
            s_fac = ag.get("secondary_facility") or ""
            p_nid = db.resolve_node_id_from_location(sid, p_fac)
            s_nid = db.resolve_node_id_from_location(sid, s_fac)
            assert p_nid is not None, f"Agent {ag['name']} primary_facility failed to resolve: {p_fac}"
            assert s_nid is not None, f"Agent {ag['name']} secondary_facility failed to resolve: {s_fac}"

        # 2. Verify get_zone_summary_tree surfaces real ETA travel_minutes & travel_tag
        hq_lobby_node = db.get_world_node(sid, "loc_hq_main_lobby")
        hq_fac_node = db.get_world_node(sid, "loc_agency_hq")
        hq_zone_node = db.get_world_node(sid, "zone_city_center")
        curr_loc_str = f"{hq_zone_node['name']} ➔ {hq_fac_node['name']} ➔ {hq_lobby_node['name']}"
        db.update_session(sid, current_location=curr_loc_str, current_node_id="loc_hq_main_lobby")

        tree = get_zone_summary_tree(
            sid,
            scen_key="anomalous_incursions",
            char_name="Agent PhaseB",
            current_loc=curr_loc_str,
        )
        assert len(tree) == 15
        cc_zone = next(z for z in tree if z["zone_name"] == hq_zone_node["name"])
        assert cc_zone["travel_tag"] == "Here"
        hq_entry = next(p for p in cc_zone["primary_locations"] if p["node_id"] == "loc_agency_hq")
        lobby_sub = next(s for s in hq_entry["sub_location_details"] if s["node_id"] == "loc_hq_main_lobby")
        armory_sub = next(s for s in hq_entry["sub_location_details"] if s["node_id"] == "loc_hq_tactical_armory")
        assert lobby_sub["travel_minutes"] == 0
        assert lobby_sub["travel_tag"] == "Here"
        assert armory_sub["travel_minutes"] == 3
        assert armory_sub["travel_tag"] == "~3m walk"
        assert len(lobby_sub["props"]) >= 3

        remote_zones = [z for z in tree if z["zone_name"] != hq_zone_node["name"]]
        assert all(isinstance(z.get("travel_minutes"), int) and z["travel_minutes"] >= 10 for z in remote_zones)
        assert all(z.get("travel_tag", "").startswith("~") for z in remote_zones)

        # 3. Verify Fantasy seeded cross-zone travel is calibrated overland trek (>= 60m), > urban transit
        ensure_session_locations_seeded(sid_fantasy, "fantasy", char_name="Agent PhaseB")
        ensure_session_spatial_graph_seeded(sid_fantasy, scenario_key="fantasy", char_name="Agent PhaseB")
        fant_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sid_fantasy)}
        cap_name = fant_nodes["zone_capital_city"]["name"]
        plains_name = fant_nodes["zone_central_plains"]["name"]
        fantasy_trek_mins = calculate_route_travel_time(
            f"{cap_name} ➔ Adventurer's Guild Hall",
            f"{plains_name} ➔ Wayside Coaching Inn",
            scen_key="fantasy",
            session_id=sid_fantasy,
        )
        urban_transit_mins = db.find_shortest_graph_path_minutes(
            sid, "loc_metro_transit_terminal", "loc_tp_main_midway"
        )
        assert fantasy_trek_mins >= 55
        assert urban_transit_mins is not None and urban_transit_mins <= 25
        assert fantasy_trek_mins > urban_transit_mins

        # 4. Verify active nodes take priority and no unintended alias collisions exist
        active_anom_ids = {n["node_id"] for n in db.get_session_world_nodes(sid)}
        active_fant_ids = set(fant_nodes.keys())
        assert db.get_world_node(sid, "sub_club_corridor")["node_id"] == "sub_club_corridor"
        assert db.get_world_node(sid, "loc_summit_lookout")["node_id"] == "loc_summit_lookout"
        assert not ((set(_LEGACY_NODE_ID_ALIASES.keys()) - {"sub_club_corridor", "loc_summit_lookout"}) & active_anom_ids)
        assert not (set(_LEGACY_NODE_ID_ALIASES.keys()) & active_fant_ids)
    finally:
        db.delete_session(sid)
        db.delete_session(sid_fantasy)
        db.delete_character(test_uid, char["id"])


@pytest.mark.unit
def test_anomalous_npc_tag_classification_permanence_and_combat_profiles():
    """
    Verifies Special Agent vs. Civilian permanent tag classification, vitals, innate ability kits,
    and mundane weapon loadouts across pre-seeded roster agents, emergent operatives, and civilians.
    """
    import db
    from mechanics.social.agent_roster import ensure_anomalous_agent_roster
    from mechanics.social.anomalous_npc_tags import (
        TAG_SPECIAL_AGENT,
        TAG_CIVILIAN,
        CIVILIAN_BASE_HP,
        CIVILIAN_BASE_MP,
        classify_anomalous_npc_tag,
        hydrate_anomalous_npc_profile,
    )

    test_uid = 999810001
    char = db.create_character(
        user_id=test_uid,
        name="Agent TagTest",
        gender="Female",
        race="Human",
        char_class="Public Safety Field Hunter",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        # 1. All 44 pre-seeded roster agents classify as special_agent with Tier vitals & 5 abilities
        roster = ensure_anomalous_agent_roster(sid, "anomalous_incursions")
        assert len(roster) == 44
        for ag in roster:
            assert ag.get("anomalous_npc_tag") == TAG_SPECIAL_AGENT
            prof = hydrate_anomalous_npc_profile({"name": ag["name"]}, session_id=sid, scen_key="anomalous_incursions")
            assert prof["anomalous_npc_tag"] == TAG_SPECIAL_AGENT
            assert prof["is_special_agent"] is True
            assert prof["max_hp"] >= 130 and prof["max_mp"] >= 60
            assert len(prof["innate_abilities"]) == 5
            assert sum(1 for d in prof["innate_ability_details"] if d.get("is_ultimate")) == 1

        # 2. Emergent narrative operatives classify as special_agent & receive deterministic Tier + 5 abilities
        for emergent_role in (
            "Freelance Anomaly Hunter",
            "Rogue Exorcist",
            "Containment Specialist",
            "Cult Ritualist",
            "Awakened Syndicate Enforcer",
        ):
            em_npc = {"name": f"Kael {emergent_role.split()[0]}", "role": emergent_role}
            assert classify_anomalous_npc_tag(em_npc, session_id=sid, scen_key="anomalous_incursions") == TAG_SPECIAL_AGENT
            em_prof = hydrate_anomalous_npc_profile(em_npc, session_id=sid, scen_key="anomalous_incursions")
            assert em_prof["is_special_agent"] is True
            assert em_prof["max_hp"] >= 130 and em_prof["max_mp"] >= 60
            assert len(em_prof["innate_abilities"]) == 5

        # 3. Mundane roles (including police, security guards, HQ clerks/quartermasters, thugs, citizens) -> civilian (100 HP / 0 MP)
        mundane_cases = [
            ("Officer Kenji", "Metropolitan Police Officer", "Service Pistol"),
            ("Guard Malik", "Mall Security Guard", "Tactical Baton"),
            ("Quartermaster Lin", "Bureau Armory Quartermaster", "Depot Sidearm"),
            ("Razor Vinnie", "Back-Alley Street Thug", "Concealed Switchblade"),
            ("Mina Takahashi", "Convenience Store Clerk", ""),
        ]
        for m_name, m_role, expected_wpn_sub in mundane_cases:
            m_npc = {"name": m_name, "role": m_role}
            assert classify_anomalous_npc_tag(m_npc, session_id=sid, scen_key="anomalous_incursions") == TAG_CIVILIAN
            m_prof = hydrate_anomalous_npc_profile(m_npc, session_id=sid, scen_key="anomalous_incursions")
            assert m_prof["is_special_agent"] is False
            assert m_prof["can_recruit_companion"] is False
            assert m_prof["max_hp"] == CIVILIAN_BASE_HP == 100
            assert m_prof["max_mp"] == CIVILIAN_BASE_MP == 0
            assert m_prof["mp"] == 0
            assert m_prof["innate_abilities"] == []
            if expected_wpn_sub:
                assert expected_wpn_sub in m_prof["weapon_profile"]["name"]

        # 4. Strict Tag Permanence: once persisted as civilian in contacts, tag NEVER flips to special_agent
        db.upsert_contact(
            session_id=sid,
            npc_id="mina_takahashi",
            name="Mina Takahashi",
            delta_score=50,
            basic_info={"role": "Convenience Store Clerk", "anomalous_npc_tag": "civilian"},
            character_id=char["id"],
        )
        mutated_probe = {"name": "Mina Takahashi", "role": "Freelance Anomaly Hunter"}
        assert classify_anomalous_npc_tag(mutated_probe, session_id=sid, scen_key="anomalous_incursions") == TAG_CIVILIAN
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_anomalous_civilian_vs_special_agent_contacts_recruitment_and_dossiers():
    """
    Verifies:
    - Civilians ARE eligible as Contacts, stamped in Codex/Phone, and hard-blocked from party recruitment
      across API, narrative reducer, pre-turn stage direction, and choices_cleaner.
    - Special Agents obey Faction Rank/Affinity + Freelancer Cash/Friend rules, unlock combat dossiers
      for same-faction colleagues & 100+ Friends, preserve Tier vitals on post-combat XP level-up,
      and recover on Safehouse rest.
    """
    import db
    from fastapi import HTTPException
    from api.codex_phone import manage_party_companion, faction_hq_action, get_phone_state
    from api.deps import CompanionPartyRequest, FactionHQActionRequest
    from mechanics.social.agent_roster import (
        ensure_anomalous_agent_roster,
        evaluate_anomalous_companion_recruitment,
    )
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        update_agent_promotion_reputation,
    )
    from mechanics.social.relationships import (
        is_contact_eligible,
        enrich_contact_dossier,
    )
    from game_engine.choices_cleaner import sanitize_and_diversify_choices
    from game_engine.state.social import (
        _reduce_social_and_milestones,
        resolve_pre_turn_social_and_disclosures,
    )
    from mechanics.combat.core import reconcile_combat_results

    test_uid = 999810002
    char = db.create_character(
        user_id=test_uid,
        name="Agent RecruitTest",
        gender="Male",
        race="Human",
        char_class="Public Safety Field Hunter",
        scenario="anomalous_incursions",
    )
    db.update_character_fields(test_uid, gold=1200)
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        factions = ensure_starter_factions(sid, "anomalous_incursions")
        roster = ensure_anomalous_agent_roster(sid, "anomalous_incursions")
        join_or_transfer_anomalous_faction(sid, "public_agency", user_id=test_uid)
        update_agent_promotion_reputation(sid, 25, user_id=test_uid)  # Tier 2

        # 1. Civilian Contact Eligibility == True, but Party Recruitment == Hard-Blocked everywhere
        civ_entity = {"name": "Detective Haru", "role": "Police Detective"}
        assert is_contact_eligible(name="Detective Haru", role="Police Detective", scenario="anomalous_incursions", session_id=sid) is True

        db.upsert_contact(
            session_id=sid,
            npc_id="detective_haru",
            name="Detective Haru",
            delta_score=220,  # Confidant! Still cannot join field party!
            basic_info={"role": "Police Detective", "anomalous_npc_tag": "civilian"},
            character_id=char["id"],
        )
        sess = db.get_session(sid)
        eval_civ = evaluate_anomalous_companion_recruitment(sess, test_uid, civ_entity, affinity_score=220)
        assert eval_civ["allowed"] is False
        assert eval_civ.get("is_civilian_blocked") is True

        # API /api/party/companion hard-blocks civilian recruitment
        with pytest.raises(HTTPException) as exc_info:
            await manage_party_companion(
                CompanionPartyRequest(
                    user_id=test_uid,
                    session_id=sid,
                    npc_name="Detective Haru",
                    action="recruit",
                )
            )
        assert exc_info.value.status_code == 400
        assert "Civilian" in exc_info.value.detail or "mana" in exc_info.value.detail.lower()

        # Narrative PARTY_RECRUIT reducer blocks civilian
        sess_mut = dict(db.get_session(sid))
        sess_mut["id"] = sid
        sess_mut["active_dialogue_partner"] = "Detective Haru"
        sess_mut["current_npcs"] = [{"name": "Detective Haru", "role": "Police Detective", "anomalous_npc_tag": "civilian"}]
        actions_probe = [{"user_id": test_uid, "action": "Ask Detective Haru to join my party for the anomaly raid", "intent": "party_recruit"}]
        out_civ = {
            "party_companion_joined": {"name": "Detective Haru", "role": "Police Detective"},
            "relationship_updates": [],
        }
        _reduce_social_and_milestones(
            sid,
            sess_mut,
            [dict(char)],
            out_civ,
            actions_probe,
            "anomalous_incursions",
            {},
            char["id"],
            char["name"],
        )
        assert all(p.get("name") != "Detective Haru" for p in db.get_session_party_npcs(sid))

        # Pre-turn custom action attempting to recruit Civilian injects stage direction
        pre_res = resolve_pre_turn_social_and_disclosures(
            sess_mut,
            party=[dict(char)],
            actions=actions_probe,
            new_dialogue_partners=["Detective Haru"],
            persist_db=False,
        )
        assert any("CIVILIAN RECRUITMENT BLOCKED" in n for n in (pre_res.get("directives") or []))

        # choices_cleaner strips LLM party_recruit for Civilian & suppresses auto-injected Invite choice
        raw_choices = [
            {"label": "Invite Detective Haru to join your party", "intent": "party_recruit", "stat": "CHA", "dc": 10},
            {"label": "Review witness statements with Detective Haru", "intent": "social_dialogue", "stat": "PER", "dc": 11},
            {"label": "Inspect the cordoned alley", "intent": "investigate", "stat": "PER", "dc": 12},
            {"label": "Check containment scanner", "intent": "utility", "stat": "INT", "dc": 10},
        ]
        cleaned_civ = sanitize_and_diversify_choices(
            raw_choices,
            scenario="anomalous_incursions",
            location="Precinct Alley",
            char=dict(char),
            dialogue_partner="Detective Haru",
            current_npcs=sess_mut["current_npcs"],
            session_id=sid,
        )
        for ch in cleaned_civ:
            lbl = (ch.get("label") if isinstance(ch, dict) else str(ch)).lower()
            assert "join your party" not in lbl and ch.get("intent") != "party_recruit"

        # 2. Emergent Freelancer Special Agent: cash retainer at 0 affinity OR free at 100+ Friend!
        freelancer_agent = {"name": "Sora Kurogane", "role": "Freelance Anomaly Hunter"}
        eval_free_cash = evaluate_anomalous_companion_recruitment(sess, test_uid, freelancer_agent, affinity_score=0)
        assert eval_free_cash["allowed"] is True
        assert eval_free_cash["cost"] > 0
        assert eval_free_cash["max_hp"] >= 130 and eval_free_cash["max_mp"] >= 60
        assert len(eval_free_cash["innate_abilities"]) == 5

        eval_free_friend = evaluate_anomalous_companion_recruitment(sess, test_uid, freelancer_agent, affinity_score=105)
        assert eval_free_friend["allowed"] is True
        assert eval_free_friend["cost"] == 0

        # 3. Same-faction colleague unlocks Operative Combat Dossier even below 100 affinity, & API recruit hydrates Tier vitals
        t2_colleague = next(a for a in roster if a["faction_id"] == "public_agency" and a["agent_tier"] == 2)
        all_char_contacts = db.get_contacts(sid, char["id"])
        col_contact = next(
            (c for c in all_char_contacts if c.get("name") == t2_colleague["name"]),
            {"name": t2_colleague["name"], "relationship_score": 20, "basic_info": {"role": t2_colleague["agent_class"]}},
        )
        enriched_col = enrich_contact_dossier(dict(col_contact), sid, "anomalous_incursions")
        assert enriched_col["anomalous_npc_tag"] == "special_agent"
        assert enriched_col["same_faction_colleague"] is True
        assert enriched_col["combat_max_hp"] == 165 and enriched_col["combat_max_mp"] == 85
        assert len(enriched_col["innate_ability_details"]) == 5

        rec_resp = await manage_party_companion(
            CompanionPartyRequest(
                user_id=test_uid,
                session_id=sid,
                npc_name=t2_colleague["name"],
                action="recruit",
            )
        )
        assert rec_resp["success"] is True
        p_comp = next(p for p in rec_resp["party_npcs"] if p["name"] == t2_colleague["name"])
        assert p_comp["anomalous_npc_tag"] == "special_agent"
        assert p_comp["max_hp"] >= 165 and p_comp["max_mp"] >= 85
        assert len(p_comp["innate_abilities"]) == 5

        # Phone state exposes tags for both Special Agents and Civilians
        phone_st = await get_phone_state(sid, user_id=test_uid)
        haru_phone = next(c for c in phone_st["contacts"] if c["name"] == "Detective Haru")
        assert haru_phone["anomalous_npc_tag"] == "civilian"

        # 4. Post-combat XP level-up preserves Special Agent Tier-scaled vitals (never overwrites to 15 + lvl*3!)
        sess_after = dict(db.get_session(sid))
        sess_after["id"] = sid
        sess_after["nearby_enemies"] = []
        reconcile_combat_results(
            sess_after,
            {"nearby_enemies": []},
            {"xp_gain": 600, "gold_gain": 50, "dead_enemies": ["Rift Hound"], "combat_log": []},
            party=[(dict(char), None)],
        )
        leveled_comp = next(p for p in db.get_session_party_npcs(sid) if p["name"] == t2_colleague["name"])
        assert leveled_comp["max_hp"] >= 165
        assert leveled_comp["max_mp"] >= 85

        # Damage & incapacitate companion, then Safehouse Rest restores full HP/MP & clears Incapacitated
        leveled_comp["hp"] = 0
        leveled_comp["mp"] = 5
        leveled_comp["status_effects"] = ["Incapacitated"]
        db.set_session_party_npcs(sid, [leveled_comp])
        pub_fac = next(f for f in factions if "public" in str(f.get("faction_id", "")).lower() or f.get("name"))
        from mechanics.social.factions import infer_anomalous_faction_archetype
        pub_fac = next(f for f in factions if infer_anomalous_faction_archetype(f) == "public_agency")
        await faction_hq_action(sid, FactionHQActionRequest(user_id=test_uid, faction_id=pub_fac["faction_id"], action="rest"))
        rested_comp = next(p for p in db.get_session_party_npcs(sid) if p["name"] == t2_colleague["name"])
        assert rested_comp["hp"] == rested_comp["max_hp"]
        assert rested_comp["mp"] == rested_comp["max_mp"]
        assert "Incapacitated" not in (rested_comp.get("status_effects") or [])
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


@pytest.mark.asyncio
async def test_anomalous_combat_abilities_forced_civilians_and_permadeath():
    """
    Verifies combat mechanics for Special Agents vs. Civilians:
    - Friendly Special Agent companion spends MP to cast innate abilities & is Knocked Out (not killed) at 0 HP.
    - Rival Special Agent enemy spawns with Tier HP/MP + abilities and spends MP on hostile abilities.
    - Civilian forced to fight has 100 HP / 0 MP, uses mundane weapon (chip damage vs supernatural anomaly,
      full damage vs mundane human), never casts magic, while ordinary uncornered bystanders take cover.
    - Friendly Civilian dropped to 0 HP by a hostile supernatural Anomalous Entity suffers Permadeath
      (marked deceased in contacts & lorebook, removed from current_npcs, blocked in presence & DMs).
    """
    import random
    import db
    from fastapi import HTTPException
    from api.codex_phone import send_npc_message
    from api.deps import PhoneMessageRequest
    from mechanics.social.anomalous_npc_tags import (
        build_anomalous_human_combatant_enemy,
        hydrate_anomalous_npc_profile,
        is_civilian_forced_to_fight_as_ally,
        resolve_anomalous_ally_combat_action,
        resolve_hostile_special_agent_ability_modifier,
        apply_civilian_permadeath,
    )
    from mechanics.combat.core import precompute_combat_turn
    from game_engine.npcs.presence import classify_scene_npcs

    test_uid = 999810003
    char = db.create_character(
        user_id=test_uid,
        name="Agent CombatTest",
        gender="Female",
        race="Human",
        char_class="Anomaly Investigator",
        scenario="anomalous_incursions",
    )
    sid = db.create_session(
        host_user_id=test_uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )
    try:
        # 1. Civilian forced-to-fight filter: armed cop & active dialogue partner fight; random bystander takes cover
        cop_npc = {"name": "Officer Takeda", "role": "Patrol Police Officer", "anomalous_npc_tag": "civilian"}
        bystander_npc = {"name": "Commuter Yui", "role": "Office Commuter", "anomalous_npc_tag": "civilian"}
        partner_npc = {"name": "Renji Sato", "role": "Barista", "anomalous_npc_tag": "civilian"}

        assert is_civilian_forced_to_fight_as_ally(cop_npc, {"enemies": [{"name": "Rift Ghoul"}]}) is True
        assert is_civilian_forced_to_fight_as_ally(bystander_npc, {"enemies": [{"name": "Rift Ghoul"}]}) is False
        assert is_civilian_forced_to_fight_as_ally(
            partner_npc,
            {"active_dialogue_partner": "Renji Sato", "enemies": [{"name": "Rift Ghoul"}]},
        ) is True

        # 2. Civilian mundane weapon damage: ~0.42x chip vs supernatural Anomaly, 1.0x vs mundane human thug
        supernatural_enemy = {"name": "Hollow Mirror-Stalker", "hp": 120, "max_hp": 120, "enemy_type": "aberration"}
        human_thug = build_anomalous_human_combatant_enemy({"name": "Street Thug", "role": "Back-Alley Thug"}, session_id=sid)
        assert human_thug["max_hp"] == 100 and human_thug["max_mp"] == 0
        assert human_thug["anomalous_npc_tag"] == "civilian"

        civ_combatant = dict(cop_npc, hp=100, max_hp=100, mp=0, max_mp=0)
        anom_target = dict(supernatural_enemy)
        human_target = dict(human_thug)
        log_anom: list[str] = []
        log_human: list[str] = []

        def _apply_dmg(t_dict, amt):
            t_dict["hp"] = max(0, int(t_dict.get("hp", 100)) - int(amt))

        resolve_anomalous_ally_combat_action(
            civ_combatant,
            [anom_target],
            [{"user_id": test_uid, "hp": 80, "max_hp": 100}],
            [],
            _apply_dmg,
            log_anom,
            rng=random.Random(2),
        )
        resolve_anomalous_ally_combat_action(
            civ_combatant,
            [human_target],
            [{"user_id": test_uid, "hp": 80, "max_hp": 100}],
            [],
            _apply_dmg,
            log_human,
            rng=random.Random(2),
        )
        dmg_vs_anom = 120 - anom_target["hp"]
        dmg_vs_human = 100 - human_target["hp"]
        assert civ_combatant["mp"] == 0
        assert dmg_vs_anom > 0 and dmg_vs_human > 0
        assert dmg_vs_anom < dmg_vs_human
        assert any("chip damage" in line for line in log_anom)

        # 3. Rival Special Agent enemy has Tier HP/MP + abilities & spends MP in hostile combat
        rival_agent = build_anomalous_human_combatant_enemy(
            {"name": "Enforcer Vex", "role": "Cult Ritualist"},
            session_id=sid,
            scen_key="anomalous_incursions",
        )
        assert rival_agent["anomalous_npc_tag"] == "special_agent"
        assert rival_agent["max_hp"] >= 130 and rival_agent["max_mp"] >= 60
        assert len(rival_agent["innate_abilities"]) == 5
        rival_agent["hp"] = int(rival_agent["max_hp"] * 0.50)  # <= 55% HP triggers Signature Ultimate!
        mp_before = rival_agent["mp"]
        rival_log: list[str] = []
        mod = resolve_hostile_special_agent_ability_modifier(rival_agent, rival_log, rng=random.Random(1))
        assert mod is not None and mod.get("is_ultimate") is True
        assert rival_agent["mp"] < mp_before

        # 4. Full precompute_combat_turn:
        #    - Party Special Agent casts innate ability (spending MP)
        #    - Officer Takeda (Civilian at 1 HP) gets hit to 0 HP by supernatural Hollow Mirror-Stalker -> PERMADEATH!
        #    - Party Special Agent NEVER suffers permadeath
        db.upsert_contact(
            session_id=sid,
            npc_id="officer_takeda",
            name="Officer Takeda",
            delta_score=65,
            basic_info={"role": "Patrol Police Officer", "anomalous_npc_tag": "civilian"},
            character_id=char["id"],
        )
        db.upsert_lorebook_entity(
            session_id=sid,
            entity_type="person",
            name="Officer Takeda",
            description="Veteran precinct patrolman.",
            disposition="friendly",
        )

        ren_prof = hydrate_anomalous_npc_profile(
            {"name": "Agent Ren", "role": "Containment Specialist"},
            session_id=sid,
            scen_key="anomalous_incursions",
            player_level=2,
            is_party_companion=True,
        )
        from mechanics.combat.spells.registry import get_spell
        non_heal_abilities = [
            ab for ab in ren_prof["innate_abilities"]
            if int((get_spell(ab) or {}).get("heal_amount", 0) or 0) == 0
        ]
        companion_agent = {
            "name": "Agent Ren",
            "role": "Containment Specialist",
            "char_class": ren_prof["agent_class"],
            "anomalous_npc_tag": "special_agent",
            "is_special_agent": True,
            "agent_tier": ren_prof["agent_tier"],
            "level": 2,
            "hp": int(ren_prof["max_hp"] * 0.48),  # <= 50% HP triggers Signature Ultimate deterministically
            "max_hp": ren_prof["max_hp"],
            "mp": ren_prof["max_mp"],
            "max_mp": ren_prof["max_mp"],
            "innate_abilities": non_heal_abilities,
            "status_effects": [],
        }
        db.set_session_party_npcs(sid, [companion_agent])
        enemy_stalker = {
            "name": "Hollow Mirror-Stalker",
            "archetype": "Stalker",
            "hp": 420,
            "max_hp": 420,
            "level": 4,
            "tier_rank": 3,
            "enemy_type": "aberration",
            "is_anomalous_entity": True,
            "affixes": ["Overclocked", "Phasing"],
            "stats": {"STR": 9, "PER": 10, "END": 6, "CHA": 1, "INT": 6, "AGI": 10, "LUK": 8},
        }
        sess_combat = dict(db.get_session(sid))
        sess_combat["id"] = sid
        sess_combat["scenario"] = "anomalous_incursions"
        sess_combat["party_npcs"] = db.get_session_party_npcs(sid)
        sess_combat["current_npcs"] = [dict(cop_npc, hp=1, max_hp=100, mp=0, max_mp=0)]
        sess_combat["nearby_enemies"] = [enemy_stalker]
        actions = [{
            "user_id": test_uid,
            "name": "Agent CombatTest",
            "char": dict(char),
            "action": "Strike the Hollow Mirror-Stalker",
            "label": "Strike the Hollow Mirror-Stalker",
            "intent": "COMBAT_MELEE",
            "combat_target": "Hollow Mirror-Stalker",
            "tier": "success",
        }]
        random.seed(3)
        pre_res = precompute_combat_turn(sess_combat, [(dict(char), None)], actions)
        combat_log_str = "\n".join(pre_res.get("combat_log") or [])
        assert "Agent Ren" in combat_log_str
        updated_party = db.get_session_party_npcs(sid)
        assert updated_party[0]["mp"] < ren_prof["max_mp"]  # Spent MP on innate ability!

        # Verify Civilian Permadeath triggered on Officer Takeda!
        takeda_contact = db.get_contact(sid, "officer_takeda", character_id=char["id"])
        assert takeda_contact is not None
        assert takeda_contact["basic_info"].get("deceased") is True
        assert "permanently killed" in combat_log_str
        assert all(n.get("name") != "Officer Takeda" for n in (sess_combat.get("current_npcs") or []))

        takeda_lore = db.get_lorebook_entity(sid, "Officer Takeda")
        assert takeda_lore is not None
        assert takeda_lore["disposition"] == "dead"
        assert "[DECEASED:" in (takeda_lore["description"] or "")

        # Deceased civilian cannot be resurrected into current_npcs by LLM presence updates
        present_after, _ = classify_scene_npcs(
            sess_combat,
            result={"npcs_present": [{"name": "Officer Takeda", "role": "Patrol Police Officer"}]},
            full_narr="Officer Takeda stands near the squad car.",
        )
        assert all(n.get("name") != "Officer Takeda" for n in present_after)

        # Deceased civilian's phone DM line is disconnected
        with pytest.raises(HTTPException) as dm_exc:
            await send_npc_message(
                sid,
                "officer_takeda",
                PhoneMessageRequest(user_id=test_uid, message="Takeda, are you there?", intent="chat"),
            )
        assert dm_exc.value.status_code == 400
        assert "perished" in dm_exc.value.detail.lower() or "disconnected" in dm_exc.value.detail.lower()

        # Verify Special Agent NEVER suffers permadeath even if apply_civilian_permadeath is called directly
        no_death = apply_civilian_permadeath(sid, sess_combat, companion_agent, killer_name="Hollow Mirror-Stalker")
        assert no_death["permadeath"] is False
    finally:
        db.delete_session(sid)
        db.delete_character(test_uid, char["id"])


def test_anomalous_tension_timer_never_spawns_random_enemies_and_handles_gated_patrol():
    from game_engine.npcs.dialogue_tracking import (
        evaluate_and_tick_scene_tension_timer,
        build_scene_escalation_and_consequence_directives,
    )

    session = {
        "scenario": "anomalous_incursions",
        "current_location": "Rustwater Docks ➔ Old Rail Yard ➔ Signal Box",
        "scene_tension_timer": 2,
        "current_npcs": [],
        "nearby_enemies": [],
        "history": [
            {"outcome_narrative": "Alarms blare across the breach perimeter as ward-lines hum."},
            {"outcome_narrative": "The spatial breach intensifies near the signal box."},
        ],
    }

    # 1. Open exploration in anomalous_incursions: never ticks or spawns a random hostile enemy
    res_open = evaluate_and_tick_scene_tension_timer(session, actions=[], is_movement=False, access_gated=False)
    assert res_open["expired"] is False
    assert res_open["spawned_hostile_enemy"] is None
    assert res_open["spawned_patrol_npc"] is None
    assert session["scene_tension_timer"] == 0

    # 2. Ticking-clock directive is suppressed when nearby_enemies is empty in anomalous_incursions
    esc_dir = build_scene_escalation_and_consequence_directives(session, party=[], actions=[])
    assert "MANDATORY SCENE ESCALATION & TICKING CLOCK DIRECTIVE" not in esc_dir

    # 3. Restricted gate trespassing (access_gated=True) spawns a non-combat Security Guard NPC, never a monster
    session["scene_tension_timer"] = 1
    res_gated = evaluate_and_tick_scene_tension_timer(
        session,
        actions=[{"label": "Force the locked security gate", "success": False}],
        is_movement=False,
        access_gated=True,
    )
    assert res_gated["expired"] is True
    assert res_gated["spawned_hostile_enemy"] is None
    assert res_gated["spawned_patrol_npc"] is not None
    assert res_gated["spawned_patrol_npc"]["role"] == "Security Guard"


def test_reconcile_implied_hostile_encounter_for_incursions_and_phantom_guard():
    from game_engine.npcs.presence import reconcile_implied_hostile_encounter

    # 1. No active incursion or quest at location -> never spawns a phantom enemy even if prose mentions an attack
    empty_sess = {
        "scenario": "anomalous_incursions",
        "current_location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
        "current_node_id": "loc_metro_transit_terminal",
        "nearby_enemies": [],
        "daily_incursions": [],
    }
    res_phantom = {
        "outcome_narrative": "A shadowy distortion lunges at you from the turnstiles!",
        "next_narrative": "The air crackles with static.",
        "nearby_enemies": [],
    }
    reconcile_implied_hostile_encounter(res_phantom, empty_sess, actions=[{"label": "Inspect the turnstiles"}])
    assert empty_sess["nearby_enemies"] == []
    assert res_phantom["nearby_enemies"] == []

    # 2. Active hostile_breach incursion at location + attack prose -> auto-spawns the hostile breach target
    hostile_sess = {
        "scenario": "anomalous_incursions",
        "current_location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
        "current_node_id": "loc_metro_transit_terminal",
        "nearby_enemies": [],
        "daily_incursions": [
            {
                "incursion_id": "inc_test_hostile",
                "subtype": "hostile_breach",
                "entity_name": "Rift-Bound Hound",
                "category_tag": "spatial_warp",
                "node_id": "loc_metro_transit_terminal",
                "facility_name": "Obelisk Central Transit Terminal",
                "location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
                "resolved": False,
            }
        ],
    }
    res_hostile = {
        "outcome_narrative": "The Rift-Bound Hound lunges at you from the spatial tear!",
        "next_narrative": "It bares crystalline fangs on the platform.",
        "nearby_enemies": [],
    }
    reconcile_implied_hostile_encounter(res_hostile, hostile_sess, actions=[{"label": "Approach the distortion"}])
    assert len(hostile_sess["nearby_enemies"]) == 1
    assert "Rift-Bound Hound" in hostile_sess["nearby_enemies"][0]["name"]
    assert hostile_sess["nearby_enemies"][0]["incursion_id"] == "inc_test_hostile"
    assert hostile_sess["daily_incursions"][0]["agitated"] is True

    # 3. Active non_hostile_entity incursion at location + non-attack action -> preserves peaceful containment (no auto-spawn)
    nh_sess = {
        "scenario": "anomalous_incursions",
        "current_location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
        "current_node_id": "loc_metro_transit_terminal",
        "nearby_enemies": [],
        "daily_incursions": [
            {
                "incursion_id": "inc_test_nh",
                "subtype": "non_hostile_entity",
                "temperament": "volatile",
                "strikes": 0,
                "max_strikes": 2,
                "entity_name": "Mirror-Glass Stray Hound",
                "category_tag": "spatial_warp",
                "node_id": "loc_metro_transit_terminal",
                "facility_name": "Obelisk Central Transit Terminal",
                "location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
                "resolved": False,
            }
        ],
    }
    res_nh_peaceful = {
        "outcome_narrative": "The Mirror-Glass Stray Hound lunges toward the reflection in panic.",
        "next_narrative": "It whines softly near the glass.",
        "nearby_enemies": [],
    }
    reconcile_implied_hostile_encounter(res_nh_peaceful, nh_sess, actions=[{"label": "Observe the hound carefully"}])
    assert nh_sess["nearby_enemies"] == []

    # 4. Active non_hostile_entity incursion + explicit player attack action -> spawns agitated non-lethal subdue entity
    reconcile_implied_hostile_encounter(res_nh_peaceful, nh_sess, actions=[{"label": "Attack the Mirror-Glass Stray Hound", "intent": "attack"}])
    assert len(nh_sess["nearby_enemies"]) == 1
    assert nh_sess["nearby_enemies"][0]["name"] == "Mirror-Glass Stray Hound"
    assert nh_sess["nearby_enemies"][0]["requires_non_lethal_subdue"] is True




