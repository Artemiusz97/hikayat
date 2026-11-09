from __future__ import annotations
"""
Faction-aware Emergency Medical Extraction, daily mandatory dispatch/salary rollover,
starting HQ/Home location resolution, and Day-1 Anomalous Incursions session bootstrap.
"""
import hashlib
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data
from mechanics.world.anomaly_engine import (
    ANOMALOUS_9_ELEMENTS,
    NON_HOSTILE_TEMPERAMENT_TYPES,
    evaluate_taboo_interaction,
    format_anomaly_dossier_summary,
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
    parse_blueprint_from_notes,
    serialize_blueprint_note,
)
from mechanics.world.folklore_mechanics import (
    build_dialogue_trap_choices,
    build_offering_counter_rite_choice,
    consume_folklore_offering_item,
    evaluate_dialogue_trap_response,
    evaluate_omen_paradox,
    find_matching_offering_in_inventory,
    get_enemy_tether_state,
    get_public_anomaly_name,
    has_active_dialogue_trap,
    is_blueprint_disguised,
    seal_enemy_tether,
    unmask_blueprint_disguise,
)

from .generation import roll_daily_anomalous_incursions
from .inquiries import prune_expired_incursion_anomalies_from_scene


def resolve_anomalous_emergency_extraction(
    session_id: int,
    user_id: int,
    apply_vitals_to_db: bool = True,
) -> Dict[str, Any]:
    """
    Faction-Aware Emergency Medical Extraction when the player drops to 0 HP in Anomalous Incursions:
    - Public Agency (`public_agency`):
      Extracted to *Medical & Psychic Cleansing Bay (`zone_agency_hq`)* — `0G` Free.
    - Monastic Shrine Order (`monastic_order`):
      Extracted to *Temple Healing Sanctuary (`zone_eastern_temple`)* — `0G` Free.
    - Private Agencies (`private_agency_1`, `private_agency_2`) & Independent Freelancers (`freelancer`):
      Extracted to *Metropolitan Hospital (`zone_hospital`)* — `10%` of current gold, capped at max `100G`.
    - Restores Player HP & MP to 50% of Max, clears `nearby_enemies`, advances time by +120 minutes,
      and preserves active quests/bounties so the player can retry.
    """
    from mechanics.social.factions import get_anomalous_faction_state
    from mechanics.world.locations.seeds import get_session_urban_zone_name, get_session_urban_facility_name

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    char = db.get_character(user_id) or {}
    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    current_gold = max(0, int(char.get("gold", 0) or 0))
    from mechanics.social.origin_mode import is_student_operative
    from mechanics.world.world_schedule import is_campus_node_or_location
    if scenario_data.is_anomalous_high_school_scenario(scen_key) and is_student_operative(sess):
        cur_loc = str(sess.get("current_location") or "")
        cur_nid = str(sess.get("current_node_id") or "")
        cur_node = db.get_world_node(session_id, cur_nid) if cur_nid else None
        p_node = db.get_world_node(session_id, cur_node["parent_id"]) if (cur_node and cur_node.get("parent_id")) else None
        on_campus = is_campus_node_or_location(cur_node, p_node, location_str=cur_loc, session_id=session_id, scen_key=scen_key)
        if on_campus:
            dest_node_id = "loc_school_infirmary"
            dest_location = "Main Academy Campus ➔ Main Academic Building ➔ School Nurse's Infirmary"
            fee = 0
            provider_label = "Campus Nurse & Student Council First-Aid Detail"
        else:
            z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
            c_name = get_session_urban_facility_name(session_id, "zone_city_center", "loc_general_hospital", "Metropolitan General Hospital", scen_key)
            dest_node_id = "loc_hosp_emergency_triage"
            dest_location = f"{z_name} ➔ {c_name} ➔ Emergency Trauma & Ambulance Triage"
            fee = min(50, int(current_gold * 0.05))
            provider_label = "Metropolitan Paramedic Evacuation Unit (Student Subsidy)"
    elif arch == "public_agency":
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        hq_name = namegen.generate_agency_hq_name(scen_key, hash_val=int(session_id or 1))
        f_name = get_session_urban_facility_name(session_id, "zone_agency_hq", "loc_hq_medical_bay", "Medical & Psychic Cleansing Bay", scen_key)
        dest_node_id = "loc_hq_medical_bay"
        dest_location = f"{z_name} ➔ {hq_name} ➔ {f_name}"
        fee = 0
        provider_label = "Bureau Emergency Extraction Team (Taxpayer-Funded)"
    elif arch == "monastic_order":
        z_name = get_session_urban_zone_name(session_id, "zone_eastern_sanctuary", "Sacred Mountain Sanctuary & Onsen Quarter", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_eastern_sanctuary", "loc_eastern_temple", "Eastern Grand Temple & Sanctuary", scen_key)
        dest_node_id = "loc_et_main_sanctuary"
        dest_location = f"{z_name} ➔ {c_name} ➔ Main Worship Hall & Incense Courtyard"
        fee = 0
        provider_label = "Shrine Crow-Talisman Rescue Ascetics (Sacred Sanctuary)"
    else:
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_city_center", "loc_general_hospital", "Metropolitan General Hospital", scen_key)
        dest_node_id = "loc_hosp_emergency_triage"
        dest_location = f"{z_name} ➔ {c_name} ➔ Emergency Trauma & Ambulance Triage"
        fee = min(100, int(current_gold * 0.10))
        provider_label = "Metropolitan Paramedic Evacuation Unit"

    try:
        dest_node = db.get_world_node(session_id, dest_node_id)
        if dest_node:
            ancestors = db.get_node_ancestors(session_id, dest_node_id)
            chain = [a["name"] for a in reversed(ancestors)] + [dest_node["name"]]
            if chain:
                dest_location = " ➔ ".join(chain)
    except Exception:
        pass

    max_hp = max(10, int(char.get("max_hp", 20) or 20))
    max_mp = max(10, int(char.get("max_mp", 10) or 10))
    cur_hp = int(char.get("hp", 0) or 0)
    cur_mp = int(char.get("mp", 0) or 0)
    target_hp = max(1, max_hp // 2)
    target_mp = max(1, max_mp // 2)

    hp_delta = max(0, target_hp - cur_hp)
    mp_delta = max(0, target_mp - cur_mp)
    if user_id and apply_vitals_to_db:
        db.apply_hp_mp_delta(user_id, hp_delta=hp_delta, mp_delta=mp_delta, gold_delta=-fee)

    from mechanics.system.time_engine import advance_time
    t_res = advance_time(session_id, 120, party_uids=[user_id] if user_id else None)
    new_day = int(t_res.get("new_day", 1) or 1)
    new_min = int(t_res.get("new_minute", 480) or 480)

    db.update_session(
        session_id,
        current_location=dest_location,
        current_node_id=dest_node_id,
        nearby_enemies=[],
        current_npcs=[],
    )

    fee_text = "0G (covered by faction medical benefits)" if fee == 0 else f"{fee}G emergency copay"
    return {
        "extracted": True,
        "faction_archetype_key": arch,
        "destination_location": dest_location,
        "destination_node_id": dest_node_id,
        "fee_paid": fee,
        "fee_charged": fee,
        "restored_hp": target_hp,
        "restored_mp": target_mp,
        "minutes_elapsed": 120,
        "new_day": new_day,
        "new_minute": new_min,
        "provider_label": provider_label,
        "narrative": (
            f"🚨 **[EMERGENCY MEDICAL EXTRACTION]**: Critical vitals triggered your emergency transponder! "
            f"{provider_label} evacuated you from the breach zone to **{dest_location}** ({fee_text}). "
            f"After two hours of stabilization, you regain consciousness at {target_hp}/{max_hp} HP and {target_mp}/{max_mp} MP."
        ),
    }


def process_anomalous_daily_rollover(
    session_id: int,
    new_day: int,
    party_uids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Executes the daily rollover routine for Anomalous Incursions when the day advances:
    1. Audits yesterday's Mandatory Daily Bounty (-15 Rep if missed; suspends salary/rations if at 0 Rep).
    2. Pays Public Agency Daily Salary (50G-300G by Promotion Tier) if not suspended.
    3. Resets Monastic Shrine daily free claim counter (`shrine_free_claims_today = 0`).
    4. Auto-dispatches today's Mandatory Daily Bounty via Morning SMS into Active Quests.
    5. Rolls 2-3 new optional Daily Anomalous Incursions (expiring yesterday's with 0 penalty).
    """
    from mechanics.social.factions import (
        get_anomalous_faction_state,
        save_anomalous_faction_state,
        update_agent_promotion_reputation,
        get_anomalous_promotion_tier_info,
    )

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "fantasy")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return {"processed": False}

    host_uid = (party_uids[0] if party_uids else None) or sess.get("host_user_id")
    state = get_anomalous_faction_state(session_id, user_id=host_uid)
    last_rollover = int(state.get("last_rollover_day", 1) or 1)
    if int(new_day) <= last_rollover and (sess.get("daily_incursions") or sess.get("daily_breaches")):
        return {"processed": False, "state": state}

    notices: List[str] = []
    arch = str(state.get("faction_archetype_key") or "public_agency")

    # 1. Audit yesterday's Mandatory Daily Bounty (only if advancing from a previous active day)
    if int(new_day) > last_rollover and arch != "freelancer":
        if (
            not state.get("mandatory_bounty_completed_today", False)
            and not state.get("mandatory_bounty_penalized_today", False)
            and state.get("mandatory_bounty_id")
        ):
            audit_res = update_agent_promotion_reputation(
                session_id=session_id,
                delta_rep=-15,
                reason="Missed Yesterday's Mandatory Daily Dispatch",
                is_missed_mandatory=True,
                user_id=host_uid,
            )
            state = audit_res.get("state") or get_anomalous_faction_state(session_id, user_id=host_uid)
            if audit_res.get("message"):
                notices.append(audit_res["message"])

    # 2. Public Agency Daily Salary Payout (50G - 300G by Tier)
    salary_paid = 0
    days_elapsed = max(1, int(new_day) - last_rollover) if int(new_day) > last_rollover else 1
    if arch == "public_agency":
        if state.get("salary_ration_suspended", False):
            notices.append("⚠️ Public Agency Daily Salary SUSPENDED (0 Rep Disciplinary Hold — complete today's Mandatory Dispatch to restore).")
        else:
            t_info = get_anomalous_promotion_tier_info(int(state.get("promotion_rep", 0) or 0))
            salary_paid = int(t_info.get("daily_salary", 50) or 50) * days_elapsed
            target_uids = party_uids if party_uids else ([host_uid] if host_uid else [])
            for uid in target_uids:
                if uid:
                    db.apply_hp_mp_delta(uid, gold_delta=salary_paid)
            notices.append(f"💳 Direct Deposit: +{salary_paid}G Public Agency Daily Salary ({t_info['title']}).")

    from mechanics.social.origin_mode import is_student_operative, STUDENT_DAILY_ALLOWANCE_GOLD
    if scenario_data.is_anomalous_high_school_scenario(scen_key) and is_student_operative(sess):
        allowance = STUDENT_DAILY_ALLOWANCE_GOLD * days_elapsed
        target_uids = party_uids if party_uids else ([host_uid] if host_uid else [])
        for uid in target_uids:
            if uid:
                db.apply_hp_mp_delta(uid, gold_delta=allowance)
        notices.append(f"💵 Daily Parent Allowance: +{allowance}G pocket money received.")

    # 3. Reset daily counters
    state["shrine_free_claims_today"] = 0
    state["shrine_free_claimed_today"] = 0
    state["mandatory_bounty_completed_today"] = False
    state["mandatory_bounty_penalized_today"] = False
    state["last_rollover_day"] = int(new_day)

    # 4. Auto-dispatch Today's Mandatory Daily Bounty via Morning SMS (for faction members)
    mandatory_quest = None
    if arch != "freelancer":
        try:
            from mechanics.narrative.bounty import dispatch_anomalous_mandatory_daily_bounty
            fac_disp_name = state.get("joined_faction_name", "Agency")
            mandatory_quest = dispatch_anomalous_mandatory_daily_bounty(
                session_id=session_id,
                current_day=int(new_day),
                faction_archetype_key=arch,
                faction_name=fac_disp_name,
                scen_key=scen_key,
            )
            if mandatory_quest:
                state["mandatory_bounty_id"] = str(mandatory_quest.get("quest_id") or "")
                sms_msg = (
                    f"[MANDATORY DAILY DISPATCH — Day {int(new_day)}] "
                    f"{mandatory_quest.get('title')}: {mandatory_quest.get('objective')}"
                )
                notices.append(f"📱 Mandatory Daily Dispatch assigned: [{mandatory_quest.get('title')}] at {mandatory_quest.get('location')}.")
                try:
                    db.save_phone_message(session_id, f"{fac_disp_name} Dispatch", "npc", sms_msg, intent="quest_comms")
                except Exception:
                    pass
        except Exception:
            pass

    save_anomalous_faction_state(session_id, state, user_id=host_uid)

    # 5. Roll 2-3 Optional Daily Anomalous Incursions (first clearing yesterday's expired breaches out of the scene)
    try:
        prune_expired_incursion_anomalies_from_scene(
            session_id, list(sess.get("daily_incursions") or sess.get("daily_breaches") or []), session=sess
        )
    except Exception:
        pass
    inc_res = roll_daily_anomalous_incursions(session_id, int(new_day), scen_key=scen_key)
    if inc_res.get("broadcast_sms"):
        notices.append(inc_res["broadcast_sms"])
        try:
            db.save_phone_message(session_id, "Metropolitan Anomaly Watch", "npc", inc_res["broadcast_sms"], intent="quest_comms")
        except Exception:
            pass

    return {
        "processed": True,
        "day": int(new_day),
        "salary_paid": salary_paid,
        "mandatory_bounty": mandatory_quest,
        "daily_incursions": inc_res.get("incursions", []),
        "daily_breaches": inc_res.get("incursions", []),
        "notices": notices,
        "state": state,
    }


def resolve_anomalous_starting_location(
    session_id: int,
    starting_faction: str = "public_agency",
    scen_key: str = "anomalous_incursions",
    char_name: str = "",
) -> Dict[str, str]:
    """
    Resolves the exact starting world_node_id and tiered 3-level location string
    for an Anomalous Incursions session based on the player's chosen starting_faction:
      - public_agency   -> Agency HQ -> Main Lobby & Security Hub -> Reception Rotunda
      - private_agency_1 -> Tower HQ -> Atrium Concierge & Biometric Turnstiles
      - private_agency_2 -> Field Office HQ -> Brick-Front Vestibule & Security Reception
      - monastic_order  -> Eastern Grand Temple -> Main Worship Hall -> Incense Courtyard
      - freelancer      -> Suburban Residential District -> Player's House -> Living Room
    """
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from mechanics.world.locations.seeds import (
        get_session_urban_zone_name,
        get_session_urban_facility_name,
        get_session_player_house_name,
    )
    import namegen

    ensure_session_spatial_graph_seeded(session_id, scen_key, char_name=char_name)

    fac_clean = str(starting_faction or "public_agency").strip().lower()
    if fac_clean in ("private_agency", "private_1"):
        fac_clean = "private_agency_1"
    elif fac_clean == "private_2":
        fac_clean = "private_agency_2"
    elif fac_clean in ("leave", "none", "independent"):
        fac_clean = "freelancer"
    elif fac_clean in ("student_freelancer", "student", "high_school", "school"):
        fac_clean = "student_freelancer"

    if fac_clean == "private_agency_1":
        candidate_ids = ["sub_priv1_entrance", "sub_priv1_dispatch", "loc_private_hq_1"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p1_z_id = urban_core_zones[h_val % 3]
        z_name = get_session_urban_zone_name(session_id, p1_z_id, "City Center", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        p1_acr = namegen.format_org_acronym(p1_name)
        p1_hq = f"{p1_acr} Tower HQ" if p1_acr else f"{p1_name} Tower HQ"
        fallback_loc = f"{z_name} ➔ {p1_hq} ➔ Atrium Concierge & Biometric Turnstiles"
    elif fac_clean == "private_agency_2":
        candidate_ids = ["sub_priv2_entrance", "sub_priv2_dispatch", "loc_private_hq_2"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p2_z_id = urban_core_zones[(h_val + 1) % 3]
        z_name = get_session_urban_zone_name(session_id, p2_z_id, "Downtown", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=2)
        if p2_name == p1_name:
            p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val + 99, agency_index=3)
        p2_acr = namegen.format_org_acronym(p2_name)
        p2_hq = f"{p2_acr} Field Office HQ" if p2_acr else f"{p2_name} Office HQ"
        fallback_loc = f"{z_name} ➔ {p2_hq} ➔ Brick-Front Vestibule & Security Reception"
    elif fac_clean == "monastic_order":
        candidate_ids = ["loc_et_main_sanctuary"]
        z_name = get_session_urban_zone_name(session_id, "zone_eastern_sanctuary", "Sacred Mountain Sanctuary & Onsen Quarter", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_eastern_sanctuary", "loc_eastern_temple", "Eastern Grand Temple & Sanctuary", scen_key)
        fallback_loc = f"{z_name} ➔ {c_name} ➔ Main Worship Hall & Incense Courtyard"
    elif fac_clean == "freelancer":
        candidate_ids = ["sub_walkup_studio", "sub_walkup_stairwell", "fac_downtown_walkup"]
        z_name = get_session_urban_zone_name(session_id, "zone_downtown", "Downtown", scen_key)
        f_name = "Modest Rented Walk-Up Apartment"
        fallback_loc = f"{z_name} ➔ {f_name} ➔ Rented Studio Unit"
    elif fac_clean == "student_freelancer":
        from mechanics.social.origin_mode import get_session_student_grade
        from mechanics.world.locations.seeds import get_session_school_name
        grade = get_session_student_grade(db.get_session(session_id) or {})
        grade_node_map = {
            "freshman": "loc_freshman_class",
            "sophomore": "loc_sophomore_class",
            "junior": "loc_junior_class",
            "senior": "loc_senior_class",
        }
        target_class_id = grade_node_map.get(str(grade or "sophomore").lower(), "loc_sophomore_class")
        candidate_ids = [target_class_id, "loc_homeroom", "loc_main_academic", "loc_school_gate"]
        school_name = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
        fallback_loc = f"{school_name} ➔ Main Academic Building ➔ Homeroom & Classrooms"
    else:
        candidate_ids = ["loc_hq_main_lobby"]
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        hq_name = namegen.generate_agency_hq_name(scen_key, hash_val=int(session_id or 1))
        f_name = get_session_urban_facility_name(session_id, "zone_agency_hq", "loc_hq_main_lobby", "Main Lobby & Security Hub", scen_key)
        fallback_loc = f"{z_name} ➔ {hq_name} ➔ {f_name}"

    if session_id:
        try:
            db.grant_or_relocate_starter_quarters(int(session_id), fac_clean)
        except Exception:
            pass
    chosen_node_id = candidate_ids[-1]
    location_display = fallback_loc
    for cid in candidate_ids:
        node = db.get_world_node(session_id, cid)
        if node:
            chosen_node_id = cid
            ancestors = db.get_node_ancestors(session_id, cid)
            chain = [a["name"] for a in reversed(ancestors)] + [node["name"]]
            if chain:
                location_display = " ➔ ".join(chain)
            break

    return {
        "node_id": chosen_node_id,
        "location_display": location_display,
        "faction_archetype_key": fac_clean,
    }


def bootstrap_anomalous_session(
    session_id: int,
    scenario_key: str,
    user_id: int,
    starting_faction: str = "public_agency",
    char_name: str = "",
    origin_mode: str = "",
    student_grade: str = "Sophomore",
) -> Dict[str, Any]:
    """
    Shared Day-1 bootstrap for Anomalous Incursions across Web API and Discord:
    seeds 6 fixed factions, joins `starting_faction`, seeds 44 Special Agents,
    seeds World-Ending Anomaly blueprint, sets starting HQ/Home location,
    and dispatches Day 1 Mandatory Bounty + Daily Incursions + Morning SMS alerts.
    """
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        get_anomalous_faction_state,
        save_anomalous_faction_state,
    )
    from mechanics.social.origin_mode import set_session_origin


    if scenario_data.is_anomalous_high_school_scenario(scenario_key):
        eff_origin = "student" if (origin_mode == "student" or starting_faction in ("student_freelancer", "student")) else "adult"
        set_session_origin(session_id, eff_origin, student_grade)

        if eff_origin == "student":
            starting_faction = "student_freelancer"
    from mechanics.social.agent_roster import ensure_anomalous_agent_roster
    from mechanics.narrative.blueprints import ensure_world_ending_anomaly_blueprint
    from mechanics.narrative.bounty import dispatch_anomalous_mandatory_daily_bounty

    ensure_starter_factions(session_id, scenario_key)
    join_or_transfer_anomalous_faction(session_id, starting_faction, user_id=user_id)

    start_loc = resolve_anomalous_starting_location(
        session_id=session_id,
        starting_faction=starting_faction,
        scen_key=scenario_key,
        char_name=char_name,
    )
    ensure_anomalous_agent_roster(session_id, scenario_key)
    ensure_world_ending_anomaly_blueprint(session_id)
    starter_hook_id = "hook_anom_student_hub" if starting_faction == "student_freelancer" else "hook_anom_agency_hub"
    db.update_session(
        session_id,
        current_node_id=start_loc["node_id"],
        current_location=start_loc["location_display"],
        extra={
            "anomalous_starting_location": start_loc["location_display"],
            "anomalous_starting_faction": starting_faction,
            "starter_hook_id": starter_hook_id,
        },
    )

    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    f_arch = str(fac_state.get("faction_archetype_key") or "public_agency")
    mand_q = None
    if f_arch not in ("freelancer", "student_freelancer"):
        fac_disp_name = fac_state.get("joined_faction_name", "Agency")
        mand_q = dispatch_anomalous_mandatory_daily_bounty(
            session_id=session_id,
            current_day=1,
            faction_archetype_key=f_arch,
            faction_name=fac_disp_name,
            scen_key=scenario_key,
        )
        if mand_q:
            fac_state["mandatory_bounty_id"] = str(mand_q.get("quest_id") or "")
            save_anomalous_faction_state(session_id, fac_state, user_id=user_id)
            try:
                sms_msg = f"[MANDATORY DAILY DISPATCH — Day 1] {mand_q.get('title')}: {mand_q.get('objective')}"
                db.save_phone_message(session_id, f"{fac_disp_name} Dispatch", "npc", sms_msg, intent="quest_comms")
            except Exception:
                pass

    inc_res = roll_daily_anomalous_incursions(session_id, 1, scen_key=scenario_key)
    if inc_res.get("broadcast_sms"):
        try:
            db.save_phone_message(session_id, "Metropolitan Anomaly Watch", "npc", inc_res["broadcast_sms"], intent="quest_comms")
        except Exception:
            pass

    return {
        "start_location": start_loc,
        "mandatory_bounty": mand_q,
        "daily_incursions": inc_res.get("incursions", []),
        "daily_breaches": inc_res.get("incursions", []),
    }
