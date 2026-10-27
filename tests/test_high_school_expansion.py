from __future__ import annotations
"""
End-to-end verification suite for the High School & NSFW High School World, Social,
Economy & Schedule Expansion across SFW and NSFW variants (`high_school_drama`,
`nsfw_high_school_drama`, `nsfw_furry_high_school_drama`).
"""
import asyncio
from typing import Any, Dict, List

import pytest

import db
import scenario_data
from game_engine.state.social import _resolve_player_social_impression_bonus
from mechanics.combat import merchant
from mechanics.combat.items import clothing
from mechanics.combat.items.consumables.usage import evaluate_gift_reaction
from mechanics.social import (
    discreet_encounters,
    factions,
    physical_state,
    relationship_graph as rg,
    school_roster,
    town_roster,
)
from mechanics.system.phone import dm_grounding, social_graph
from mechanics.world import npc_schedule, world_schedule
from mechanics.world.locations import access_gate, attributes, graph_seeder


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect both db.DB_PATH and db.core.DB_PATH so live hikayat.db is never touched."""
    test_db = str(tmp_path / "test_hs_expansion.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    yield test_db


def _seed_hs_session(
    user_id: int,
    scen_key: str = "high_school_drama",
    gender: str = "Male",
    gold: int = 150,
) -> Dict[str, Any]:
    db.create_character(
        user_id,
        name="Kaito Tachibana" if gender.lower() == "male" else "Aoi Tachibana",
        char_class="Honor Student",
        gender=gender,
        gold=gold,
        scenario=scen_key,
        race="human",
    )
    sid = db.create_session(
        user_id,
        "solo",
        1,
        "vivid",
        "individual",
        False,
        scenario=scen_key,
    )
    graph_seeder.ensure_session_spatial_graph_seeded(
        sid, scenario_key=scen_key, char_name="Kaito Tachibana"
    )
    sess = db.get_session(sid)
    school_roster.ensure_school_directory_exists(sess)
    return db.get_session(sid)


@pytest.mark.unit
def test_unified_seed_nsfw_filtering_renames_aliases_and_21_discreet_spots():
    """Verify SFW vs NSFW venue filtering, Downtown & Recreational Park renames, legacy aliases, and 21 is_discreet spots."""
    sfw_sess = _seed_hs_session(880001, scen_key="high_school_drama")
    nsfw_sess = _seed_hs_session(880002, scen_key="nsfw_high_school_drama")
    furry_nsfw_sess = _seed_hs_session(880003, scen_key="nsfw_furry_high_school_drama")

    sfw_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(int(sfw_sess["id"]))}
    nsfw_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(int(nsfw_sess["id"]))}
    furry_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(int(furry_nsfw_sess["id"]))}

    # 1. Explicit NSFW venues filtered out in SFW, present in NSFW & NSFW Furry
    for adult_id in ("loc_nightclub", "loc_adult_store", "loc_love_hotel", "loc_nsfw_faction_hq"):
        assert adult_id not in sfw_nodes
        assert adult_id in nsfw_nodes
        assert adult_id in furry_nodes

    # 2. Downtown, City Square, and 6 new SFW retail venues present in both SFW & NSFW
    assert "zone_downtown" in sfw_nodes
    assert "Downtown" in sfw_nodes["zone_downtown"]["name"]
    assert "Commercial District" not in sfw_nodes["zone_downtown"]["name"]
    assert "loc_city_square" in sfw_nodes
    for shop_id in (
        "loc_restaurant",
        "loc_clothing_store",
        "loc_brand_clothing_store",
        "loc_accessories_store",
        "loc_gift_store",
        "loc_night_market",
    ):
        assert shop_id in sfw_nodes
        assert shop_id in nsfw_nodes

    # 3. Recreational Park rename & zero mountain references
    assert "zone_recreational_park" in sfw_nodes
    assert "Recreational Park" in sfw_nodes["zone_recreational_park"]["name"]
    assert "Mountain" not in sfw_nodes["zone_recreational_park"]["name"]
    for park_fac in ("loc_campsite", "loc_park_lake", "loc_hilltop_lookout", "loc_sakura_grove", "loc_park_shrine", "loc_picnic_pavilions"):
        assert park_fac in sfw_nodes
    for nid, n_obj in sfw_nodes.items():
        if n_obj.get("parent_id") == "zone_recreational_park" or nid == "zone_recreational_park":
            assert "mountain" not in str(n_obj.get("name") or "").lower()

    # 4. Legacy node ID aliases resolve seamlessly
    sid_sfw = int(sfw_sess["id"])
    assert db.get_world_node(sid_sfw, "zone_commercial")["node_id"] == "zone_downtown"
    assert db.get_world_node(sid_sfw, "loc_transit_plaza")["node_id"] == "loc_city_square"
    assert db.get_world_node(sid_sfw, "zone_mountain_park")["node_id"] == "zone_recreational_park"
    assert db.get_world_node(sid_sfw, "loc_summit_lookout")["node_id"] == "loc_hilltop_lookout"

    # 5. Exactly 21 `is_discreet` spots seeded in world_nodes
    discreet_ids = [
        nid for nid in nsfw_nodes
        if db.get_world_node_state(int(nsfw_sess["id"]), nid).get("is_discreet")
    ]
    assert len(discreet_ids) == 21
    assert "loc_empty_class" in discreet_ids
    assert "loc_behind_gym_sheds" in discreet_ids
    assert "sub_square_underpass" in discreet_ids
    assert "sub_park_thicket" in discreet_ids


@pytest.mark.unit
def test_grade_classrooms_rotating_teachers_infirmary_pass_and_discreet_locks():
    """Verify 5 exclusive grade classrooms, rotating subject teachers, lecture intrusion, and Infirmary Sick Pass."""
    sess = _seed_hs_session(880004, scen_key="high_school_drama")
    sid = int(sess["id"])
    roster = db.get_school_roster(sid)

    # 1. During Monday morning lecture (09:30 = 570), each grade classroom holds exclusively its own grade + 1 rotating teacher
    expected_grade_by_cls = {
        "loc_homeroom": "Junior",
        "loc_freshman_class": "Freshman",
        "loc_sophomore_class": "Sophomore",
        "loc_junior_class": "Junior",
        "loc_senior_class": "Senior",
    }
    for cls_id, exp_grade in expected_grade_by_cls.items():
        students_here = [
            r for r in roster
            if r["grade"] not in ("Faculty", "Citizen", "Youth Peer")
            and npc_schedule.get_npc_scheduled_node_id(r, current_minute=570, scen_key="high_school_drama", current_day=1, session_id=sid) == cls_id
        ]
        assert len(students_here) >= 7
        assert all(s["grade"] == exp_grade for s in students_here)

    # Rotating subject teachers cover all 5 classrooms during lecture hours
    rotating_cls = set()
    for f_row in roster:
        if f_row["grade"] == "Faculty":
            c_target = npc_schedule.get_rotating_classroom_for_teacher(f_row["role"], current_day=1, phase="morning")
            if c_target:
                rotating_cls.add(c_target)
    assert rotating_cls == set(expected_grade_by_cls.keys())

    # Entering Freshman Classroom during active lecture triggers teacher confrontation
    intrusion = discreet_encounters.evaluate_classroom_lecture_intrusion(
        sid, "high_school_drama", "loc_freshman_class", current_day=1, current_minute=570
    )
    assert intrusion is not None
    assert intrusion["event_type"] == "classroom_intrusion"
    assert len(intrusion["choices"]) == 3
    # During lunch (12:30 = 750), classroom entry is frictionless
    assert discreet_encounters.evaluate_classroom_lecture_intrusion(
        sid, "high_school_drama", "loc_freshman_class", current_day=1, current_minute=750
    ) is None

    # 2. School Nurse stays in `loc_school_infirmary` 08:00–17:00; infirmary locks at 17:00; discreet rooms stay open until 20:00
    nurse = next(r for r in roster if "nurse" in r["role"].lower())
    assert npc_schedule.get_npc_scheduled_node_id(nurse, current_minute=600, scen_key="high_school_drama", current_day=1, session_id=sid) == "loc_school_infirmary"

    nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sid)}
    inf_1730 = world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_school_infirmary"], nodes["bld_school_academic"], scen_key="high_school_drama", current_day=1, current_minute=1050
    )
    assert inf_1730["schedule_locked"] is True

    empty_cls_1830 = world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_empty_class"], nodes["bld_school_academic"], scen_key="high_school_drama", current_day=1, current_minute=1110
    )
    assert empty_cls_1830["schedule_locked"] is False

    # 3. Infirmary Sick Pass legally bypasses 08:00–15:00 campus gate truancy lockdown
    db.update_session(sid, current_day=1, current_minute=600, current_node_id="loc_homeroom", current_location="Main Academic Building ➔ Homeroom Classroom")
    sess_mid = db.get_session(sid)
    gate_before = access_gate.evaluate_node_access_gate(sid, "loc_cafe", sess_mid, actions=[], party=[])
    assert gate_before["gated"] is True
    assert gate_before["reason_code"] == "school_hours_lockdown"

    discreet_encounters.grant_infirmary_sick_pass(sess_mid, current_day=1)
    gate_after = access_gate.evaluate_node_access_gate(sid, "loc_cafe", sess_mid, actions=[], party=[])
    assert gate_after["gated"] is False


@pytest.mark.unit
def test_gendered_restrooms_shower_staging_refresh_and_confrontation_scandal():
    """Verify shower wet/towel staging, player shower composure refresh, teasing nuance, and failed confrontation scandal."""
    sess = _seed_hs_session(880005, scen_key="nsfw_high_school_drama", gender="Male")
    sid = int(sess["id"])
    char = db.get_character(880005)

    # 1. Own-gender shower room refreshes player physical state back to composed
    init_st = physical_state.init_default_physical_state(sid, [(char, [])], "nsfw_high_school_drama")
    init_st["actors"][char["name"]]["composure"] = "disheveled"
    init_st["actors"][char["name"]]["is_bloodied"] = 1
    db.update_session_physical_state(sid, init_st)
    ref_res = physical_state.apply_player_shower_refresh(
        sid,
        party=[(char, [])],
        action_text="wash up and freshen up in the warm showers",
        location_str="School Grounds & Athletics ➔ Men's Locker & Shower Room",
        node_id="loc_male_shower_room",
        player_gender="Male",
    )
    assert ref_res["refreshed"] is True
    p_after = db.get_session_physical_state(sid)["actors"][char["name"]]
    assert p_after["composure"] == "composed"
    assert p_after["is_bloodied"] == 0

    # 2. Opposite-gender shower room at 16:00 (960) stages scheduled female athletes with `is_wet` & triggers confrontation
    factions.ensure_starter_factions(sid, "nsfw_high_school_drama")
    ev = discreet_encounters.evaluate_gendered_room_hazard(
        sess,
        [(char, [])],
        fac_id="loc_female_shower_room",
        node_id="loc_female_shower_room",
        location_str="School Grounds & Athletics ➔ Women's Locker & Shower Room",
        current_day=1,
        current_minute=960,
        rng_roll_override=0.01,
    )
    assert ev is not None
    assert ev["event_type"] in ("gendered_room_confrontation", "gendered_room_teasing")

    # Force a standard confrontation failure and verify ejection + Student Council rep drop + Gossip Feed post
    st = sess.setdefault("phone_social_state", {})
    st["pending_gendered_confrontation"] = {
        "witness_name": "Mina Sato",
        "witness_npc_id": "mina_sato",
        "facility_kind": "restroom",
        "facility_id": "loc_female_restroom",
        "location_display": "Main Academic Building ➔ Girls' Restroom",
    }
    db.upsert_contact(sid, "mina_sato", "Mina Sato", character_id=char["id"], delta_score=20)
    fail_res = discreet_encounters.resolve_gendered_room_confrontation(
        sess,
        [(char, [])],
        {"witness_name": "Mina Sato", "witness_npc_id": "mina_sato", "facility_kind": "restroom"},
        succeeded=False,
    )
    assert fail_res["ejected"] is True
    assert fail_res["override_node_id"] == "loc_school_hallway"
    assert fail_res["scandal_posted"] is True

    feed = db.get_gossip_feed(sid, limit=5)
    assert any(p.get("tag") == "#CampusScandal" for p in feed)
    sc = next(f for f in db.get_factions(sid) if "council" in f["name"].lower() or f.get("category") == "council")
    assert sc["reputation_score"] <= -10


@pytest.mark.unit
def test_downtown_economy_love_hotel_fees_clothing_cap_and_wearable_gifting():
    """Verify venue operating hours, narrowed Cafe/ChronoStore, Love Hotel $40/$80 + partner waiver, +1 CHA cap, and wearable gifting."""
    sess = _seed_hs_session(880006, scen_key="nsfw_high_school_drama", gold=100)
    sid = int(sess["id"])
    char = db.get_character(880006)
    nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sid)}

    # 1. Night Market strictly 18:00–22:00; Nightclub 18:00–02:00; Adult Store 12:00–00:00; Love Hotel 24/7
    assert world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_night_market"], nodes["zone_downtown"], scen_key="nsfw_high_school_drama", current_day=1, current_minute=900
    )["schedule_locked"] is True
    assert world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_night_market"], nodes["zone_downtown"], scen_key="nsfw_high_school_drama", current_day=1, current_minute=1140
    )["schedule_locked"] is False
    assert world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_nightclub"], nodes["zone_downtown"], scen_key="nsfw_high_school_drama", current_day=1, current_minute=60  # 01:00 AM
    )["schedule_locked"] is False
    assert world_schedule.evaluate_world_schedule_node_access(
        nodes["loc_love_hotel"], nodes["zone_downtown"], scen_key="nsfw_high_school_drama", current_day=1, current_minute=240  # 04:00 AM
    )["force_open"] is True

    # 2. Specific Downtown venue merchant resolution (before generic Downtown hub_stores)
    def _mtypes(loc_s: str) -> List[str]:
        return [m["type"] for m in attributes.get_available_merchant_types_for_location(loc_s, "nsfw_high_school_drama")]

    assert "restaurant_merchant" in _mtypes("Downtown ➔ Family Bistro & Diner")
    assert "brand_clothes_merchant" in _mtypes("Downtown ➔ Luxury Designer Boutique")
    assert "accessories_merchant" in _mtypes("Downtown ➔ Charm & Accessories Shop")
    assert "gift_merchant" in _mtypes("Downtown ➔ Curio & Gift Shop")
    assert "night_market_merchant" in _mtypes("Downtown ➔ Lantern Night Market & Bazaar")
    assert "nightclub_merchant" in _mtypes("Downtown ➔ Neon Pulse Nightclub")
    assert "adult_store_merchant" in _mtypes("Downtown ➔ Velvet Curtain Adult Boutique")
    assert _mtypes("Downtown ➔ Mirage Boutique Love Hotel") == []

    # ChronoStore narrowed to basic snacks/drinks/study essentials (no luxury Tier 1 fashion or Lingerie)
    online_shop = asyncio.run(
        merchant.generate_merchant_shop([(char, 880006)], "", "", session=sess, is_phone_shop=True)
    )
    assert len(online_shop["stock"]) >= 2
    for it in online_shop["stock"]:
        assert str(it.get("item_type") or "").lower() not in ("lingerie", "weapon", "armor")
        assert int(it.get("tier") or 3) >= 2

    # 3. Strict +1 CHA ceiling across all civilian clothing + Tier 2 (+2) & Tier 1 (+4) social affinity impression
    for tier_num, exp_aff in ((3, 0), (2, 2), (1, 4)):
        garment = clothing.generate_random_clothing("nsfw_high_school_drama", slot="Top", tier=tier_num)
        assert int((garment["metadata"].get("social_modifiers") or {}).get("cha", 0)) <= 1
        assert int(garment["metadata"].get("social_affinity_bonus") or 0) == exp_aff

    t1_coat = clothing.generate_random_clothing("nsfw_high_school_drama", slot="Top", tier=1, archetype="blazer")
    t1_coat["equipped"] = True
    sess_lh = dict(sess, current_node_id="sub_love_hotel_jacuzzi", current_location="Downtown ➔ Mirage Boutique Love Hotel ➔ Rooftop Jacuzzi Suite")
    imp_bonus, imp_reason = _resolve_player_social_impression_bonus(sess_lh, [(char, [t1_coat])])
    assert imp_bonus == 7  # +4 Tier 1 fashion + +3 Rooftop Jacuzzi Suite
    assert "Rooftop Jacuzzi Suite" in imp_reason

    # 4. Love Hotel $40 Mirrored Suite payment + $0 Partner-Invited Waiver on $80 Jacuzzi Suite
    db.update_session(sid, current_day=6, current_minute=1200, current_node_id="sub_love_hotel_lobby", current_location="Downtown ➔ Mirage Boutique Love Hotel ➔ Automated Touchscreen Check-In Lobby")
    sess_sat = db.get_session(sid)
    lh_res = access_gate.evaluate_node_access_gate(sid, "sub_love_hotel_mirrored", sess_sat, actions=[], party=[(char, [])])
    assert lh_res["gated"] is False
    assert lh_res["suite_fee_paid"] == 40
    assert db.get_character(880006)["gold"] == 60

    # Partner-invited waiver ($0) on $80 Rooftop Jacuzzi Suite even though player only has $60 left!
    sess_sat["partner_treating_love_hotel"] = True
    lh_waived = access_gate.evaluate_node_access_gate(sid, "sub_love_hotel_jacuzzi", sess_sat, actions=[], party=[(db.get_character(880006), [])])
    assert lh_waived["gated"] is False
    assert lh_waived["suite_fee_paid"] == 0
    assert db.get_character(880006)["gold"] == 60

    # 5. Wearable Gifting equips Top / Accessory / Lingerie on recipient NPC in `physical_state.py`
    silk_top = clothing.generate_random_clothing("nsfw_high_school_drama", slot="Top", tier=1, archetype="blouse")
    db.add_item(880006, silk_top["name"], item_type=silk_top["item_type"], effect=silk_top["effect"])
    db.upsert_contact(sid, "elena_vance", "Elena Vance", character_id=char["id"], delta_score=50)
    st_gift = physical_state.init_default_physical_state(sid, [(char, [])], "nsfw_high_school_drama")
    st_gift["actors"]["Elena Vance"] = {"actor_type": "npc", "posture": "Standing", "clothing": {"top": "School Blouse"}}
    db.update_session_physical_state(sid, st_gift)

    ok_gift, gift_msg, gift_delta = evaluate_gift_reaction(880006, silk_top, "Elena Vance", session=sess)
    assert ok_gift is True
    assert gift_delta >= 5
    assert "wears" in gift_msg
    elena_c = db.get_contact(sid, "elena_vance", char["id"])
    assert elena_c["basic_info"]["gifted_wardrobe"]["Top"] == silk_top["name"]
    assert db.get_session_physical_state(sid)["actors"]["Elena Vance"]["clothing"]["top"] == silk_top["name"]


@pytest.mark.unit
def test_tiered_witness_privacy_0_8_35(monkeypatch):
    """Verify 0% witness risk in private suites, 8% in is_discreet spots, and 35% in open public rooms."""
    sess = _seed_hs_session(880007, scen_key="nsfw_high_school_drama")
    sid = int(sess["id"])

    # 1. Love Hotel Suite (`is_private_intimate_venue`) -> 0% witness detection even on roll 0.001
    monkeypatch.setattr(social_graph.random, "random", lambda: 0.001)
    sess_priv = dict(
        sess,
        current_node_id="sub_love_hotel_mirrored",
        current_location="Downtown ➔ Mirage Boutique Love Hotel ➔ Mirrored Velvet Suite",
        dialogue_partners=["Sora"],
    )
    priv_w = social_graph.evaluate_pre_turn_witness_detection(
        sess_priv, [{"label": "Kiss Sora passionately and undress"}], target_npc="Sora"
    )
    assert priv_w["witness_spotted"] is False

    # 2. Discreet spot (`loc_empty_class`, 8% threshold) -> safe at 0.12, witnessed at 0.04
    sess_disc = dict(
        sess,
        current_node_id="loc_empty_class",
        current_location="Main Academic Building ➔ Empty Classroom",
        dialogue_partners=["Sora"],
    )
    monkeypatch.setattr(social_graph.random, "random", lambda: 0.12)
    disc_safe = social_graph.evaluate_pre_turn_witness_detection(
        sess_disc, [{"label": "Make out intensely with Sora"}], target_npc="Sora"
    )
    assert disc_safe["witness_spotted"] is False

    monkeypatch.setattr(social_graph.random, "random", lambda: 0.04)
    disc_caught = social_graph.evaluate_pre_turn_witness_detection(
        sess_disc, [{"label": "Make out intensely with Sora"}], target_npc="Sora"
    )
    assert disc_caught["witness_spotted"] is True

    # 3. Open public room (`loc_courtyard`, 35% threshold) -> witnessed at 0.20
    monkeypatch.setattr(social_graph.random, "random", lambda: 0.20)
    sess_pub = dict(
        sess,
        current_node_id="loc_courtyard",
        current_location="Student Commons & Central Plaza ➔ Central Courtyard",
        dialogue_partners=["Sora"],
    )
    pub_caught = social_graph.evaluate_pre_turn_witness_detection(
        sess_pub, [{"label": "Make out intensely with Sora"}], target_npc="Sora"
    )
    assert pub_caught["witness_spotted"] is True


@pytest.mark.unit
def test_canonical_couples_discreet_affair_breakup_and_bold_meetup_bias():
    """Verify 5 canonical peer couples, discreet affair discovery, breakup + gossip post on exposure, and ~65% bold discreet meetup bias."""
    sess = _seed_hs_session(880008, scen_key="nsfw_high_school_drama")
    sid = int(sess["id"])
    char = db.get_character(880008)

    # 1. Exactly 5 canonical `TIETYPE_DATING` peer couples seeded (~87% of peers stay single)
    couples = rg.get_canonical_peer_couples(sid, active_only=True)
    assert len(couples) == 5
    # Hydrating & seeding social graph for one coupled student preserves their canonical peer partner while still seeding friends/rivals
    roster = db.get_school_roster(sid)
    coupled_student = next(r for r in roster if rg.canonical_person_key(r["name"]) == couples[0]["person_a_key"])
    school_roster.hydrate_school_character(sid, coupled_student)
    hydrated_contact = db.get_contact(sid, coupled_student["npc_id"])
    rg.seed_contact_social_graph(hydrated_contact, sid, scenario="nsfw_high_school_drama")
    after_partner = rg.get_current_partner(sid, couples[0]["person_a_key"])
    assert after_partner is not None
    assert after_partner["person_key"] == couples[0]["person_b_key"]
    assert len(rg.get_ties(sid, couples[0]["person_a_key"], types=rg.PLATONIC_TYPES)) >= 1

    # 2. Trigger NSFW discreet Secret Affair encounter (roll < 0.15, affair_roll < 0.25)
    aff_ev = discreet_encounters.evaluate_discreet_couple_encounter(
        sess,
        [(char, [])],
        node_id="loc_behind_gym_sheds",
        fac_id="loc_behind_gym_sheds",
        location_str="School Grounds & Athletics ➔ Behind Gym Storage Sheds",
        current_day=2,
        current_minute=990,
        rng_roll_override=0.05,
        affair_roll_override=0.10,
    )
    assert aff_ev is not None
    assert aff_ev["is_affair"] is True
    assert len(aff_ev["choices"]) == 4
    cheater_key = aff_ev["actor_a_key"]
    lover_key = aff_ev["actor_b_key"]
    betrayed_key = aff_ev["betrayed_key"]
    assert any(a["person_key"] == lover_key for a in rg.get_secret_affairs(sid, cheater_key))

    # Expose the affair -> breaks canonical `TIETYPE_DATING` tie and posts `#BreakupBombshell` rumor!
    exp_res = discreet_encounters.resolve_discreet_couple_action(
        sess, [(char, [])], "affair_expose", succeeded=True
    )
    assert exp_res["affair_exposed"] is True
    assert rg.get_current_partner(sid, cheater_key) is None
    exes = rg.get_ex_partners(sid, betrayed_key)
    assert any(ex["person_key"] == cheater_key for ex in exes)
    feed = db.get_gossip_feed(sid, limit=5)
    assert any(p.get("tag") == "#BreakupBombshell" for p in feed)

    # 3. Bold / uninhibited NPC meetup choices weight ~65% toward `is_discreet` / NSFW evening venues
    bold_contact = {
        "name": "Rina Kurokawa",
        "appearance": {"erotic_openness": "bold_uninhibited"},
        "traits": ["Bold", "Flirtatious"],
    }
    discreet_hits = 0
    trials = 40
    for idx in range(trials):
        picked = dm_grounding.select_npc_preferred_meetup_venue(
            sid,
            bold_contact,
            "nsfw_high_school_drama",
            current_day=6,
            current_minute=1140,
            seed_salt=f"sample_{idx}",
        )
        assert picked != ""
        if physical_state.is_discreet_venue(picked, session_id=sid) or any(
            k in picked.lower() for k in ("love hotel", "neon pulse nightclub")
        ):
            discreet_hits += 1
    assert 18 <= discreet_hits <= 34  # ~65% target band


@pytest.mark.unit
def test_nsfw_faction_salon_roster_gatherings_invited_guests_and_proprietors():
    """Verify 6 starter factions in NSFW High School, 5 dedicated Salon members, gathering schedule + 1-2 guests, and 101 roster."""
    sess = _seed_hs_session(880009, scen_key="nsfw_high_school_drama")
    sid = int(sess["id"])
    roster = db.get_school_roster(sid)

    # 1. Roster totals: 101 in NSFW (69 Campus + 28 Adult Citizens + 4 Youth Peers), strictly 6 student part-timers
    assert len(roster) == 101
    salon_members = [r for r in roster if r.get("clique") == "Hedonists"]
    assert len(salon_members) == 5
    part_timers = [r for r in roster if "Part-Time:" in r.get("personality_summary", "")]
    assert len(part_timers) == 6

    # 2. Starter factions: 6 in NSFW High School (keeps Varsity Athletic Directorate + NSFW Secret Society)
    seeded_factions = factions.ensure_starter_factions(sid, "nsfw_high_school_drama")
    assert len(seeded_factions) == 6
    assert any(f.get("category") == "nsfw_club" and "velvet basement salon" in str(f.get("hq_location_id") or "").lower() for f in seeded_factions)
    assert any("athletic" in f["name"].lower() or "varsity" in f["name"].lower() for f in seeded_factions)

    # 3. Speakeasy gate blocks uninvited outsiders at `loc_nsfw_faction_hq` (even though inside Abandoned Old Campus Building!)
    db.update_session(sid, current_day=1, current_minute=1020, current_node_id="loc_old_storage", current_location="Abandoned Old Campus Building ➔ Old Storage Room 3-B")
    sess_now = db.get_session(sid)
    blocked = access_gate.evaluate_node_access_gate(sid, "loc_nsfw_faction_hq", sess_now, actions=[], party=[])
    assert blocked["gated"] is True
    assert blocked["reason_code"] == "speakeasy_restricted"

    # Invited / member flag unlocks entry cleanly
    sess_now["nsfw_faction_member"] = True
    allowed = access_gate.evaluate_node_access_gate(sid, "loc_nsfw_faction_hq", sess_now, actions=[], party=[])
    assert allowed["gated"] is False

    # 4. During Weekday Gathering (17:00 = 1020), all 5 Salon members + 1–2 invited guests from other clubs gather at `loc_nsfw_faction_hq`
    gathered = [
        r for r in roster
        if npc_schedule.get_npc_scheduled_node_id(r, current_minute=1020, scen_key="nsfw_high_school_drama", current_day=1, session_id=sid) == "loc_nsfw_faction_hq"
    ]
    gathered_salon = [r for r in gathered if r.get("clique") == "Hedonists"]
    gathered_guests = [r for r in gathered if r.get("clique") != "Hedonists"]
    assert len(gathered_salon) == 5
    assert 1 <= len(gathered_guests) <= 2
