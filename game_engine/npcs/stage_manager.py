"""Pre-turn stage management: Authoritative spatial and NPC presence resolution before LLM generation."""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import json
import logging
import re

import db
from mechanics.combat import is_in_combat
from game_engine.npcs.presence import classify_scene_npcs
from game_engine.core import _get_npc_name
from mechanics.world.locations import (
    extract_movement_destination,
    get_primary_location_name,
    get_zone_location_name,
    parse_tiered_location,
    is_location_engine_enabled,
)
from mechanics.world.mobility import (
    is_solo_travel_intent,
    ACCOMPANIED_TRAVEL_PHRASES,
    is_rendezvous_target,
    get_session_dialogue_partners,
    is_dialogue_partner,
)
from mechanics.narrative.intent import (
    classify_action_intent,
    IntentCategory,
    IntentContext,
)
from mechanics.social.persona.actor_card import derive_initial_micro_blocking
from mechanics.world.schedules import get_time_block_key

log = logging.getLogger(__name__)


def _spawn_canonical_role_npc_pre_turn(
    session: dict,
    role_title: str,
    effective_location: str,
) -> dict:
    """
    Instantly generates a canonical named NPC in 0ms for an unseeded role interaction
    (e.g. ActionCommand.spawns_npc_role == 'barista') and registers them in contacts.
    """
    import namegen
    from mechanics.social.persona import (
        infer_contact_gender,
        split_traits_and_preferences,
        normalize_appearance,
    )

    scen_key = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"
    sess_id = session.get("id") if isinstance(session, dict) else None
    clean_role = str(role_title or "Local Resident").strip().title()

    # Check if an existing facility/school roster NPC or contact already matches this role
    matched_seed_char = None
    if sess_id:
        try:
            fac_chars = db.get_school_characters_by_facility(sess_id, effective_location, limit=10) if hasattr(db, "get_school_characters_by_facility") else []
            roster_chars = db.get_school_roster(sess_id) if hasattr(db, "get_school_roster") else []
            all_contacts = db.get_contacts(sess_id) or []
            eff_low = str(effective_location or "").lower()
            local_contacts = [
                c for c in all_contacts
                if isinstance(c, dict) and eff_low and str((c.get("basic_info") or {}).get("location") or c.get("location") or "").lower() in eff_low
            ]
            for c in local_contacts + (fac_chars or []) + all_contacts + (roster_chars or []):
                if not isinstance(c, dict) or not c.get("name"):
                    continue
                c_role = str(c.get("role") or (c.get("basic_info") or {}).get("role") or "").lower()
                c_club = str(c.get("club") or (c.get("basic_info") or {}).get("club") or "").lower()
                role_toks = set(re.findall(r'[a-z]{3,}', clean_role.lower())) - {"the", "and", "for"}
                is_match = clean_role.lower() in c_role or (c_role and c_role in clean_role.lower())
                if not is_match and role_toks:
                    if any(t in c_role or t in c_club for t in role_toks if t not in ("rep", "club", "student", "member", "representative")):
                        is_match = True
                if is_match:
                    if c.get("appearance") and isinstance(c.get("appearance"), dict):
                        return {
                            "name": c["name"],
                            "role": c.get("role") or (c.get("basic_info") or {}).get("role") or clean_role,
                            "gender": c.get("gender") or (c.get("basic_info") or {}).get("gender") or "female",
                            "appearance": c.get("appearance") or {},
                            "traits": c.get("traits") or [],
                            "unlocked_traits": c.get("unlocked_traits") or (c.get("traits") or [])[:2],
                            "basic_info": c.get("basic_info") or {"role": clean_role, "location": effective_location},
                            "status_effects": ["Present"],
                            "stage_role": "active_partner",
                            "attention_ring": "ring_1_primary",
                        }
                    matched_seed_char = c
                    break
        except Exception:
            pass

    if matched_seed_char:
        npc_name = str(matched_seed_char.get("name") or "").strip() or namegen.generate_person_name(scenario=scen_key)
        clean_role = str(matched_seed_char.get("role") or (matched_seed_char.get("basic_info") or {}).get("role") or clean_role).strip()
        gender = str(matched_seed_char.get("gender") or "").strip().lower() or infer_contact_gender({"name": npc_name, "basic_info": {"role": clean_role}}) or "female"
        race_val = str(matched_seed_char.get("race") or "human").strip() or "human"
    else:
        role_words = set(re.findall(r"[a-z]+", clean_role.lower()))
        role_gender_hint = ""
        if role_words & {
            "waitress", "actress", "hostess", "priestess", "headmistress", "mistress",
            "barmaid", "maid", "queen", "princess", "lady", "madam", "madame",
            "sister", "mother", "matron", "girl", "woman", "heroine",
        }:
            role_gender_hint = "female"
        elif role_words & {
            "waiter", "host", "priest", "headmaster", "master", "barman",
            "king", "prince", "lord", "sir", "father", "brother", "boy", "man", "gentleman",
        }:
            role_gender_hint = "male"
        npc_name = namegen.generate_person_name(scenario=scen_key, gender=role_gender_hint)
        gender = role_gender_hint or infer_contact_gender({"name": npc_name, "basic_info": {"role": clean_role}}) or "female"
        from mechanics.social.races import normalize_race
        race_val = normalize_race("", scen_key, seed=f"{sess_id or 0}:{npc_name.lower()}") or "human"

    traits, prefs = split_traits_and_preferences(
        [],
        [],
        role=clean_role,
        race=race_val,
        seed_str=f"{npc_name}_{clean_role}_{effective_location}",
    )
    app_dict = normalize_appearance(
        {},
        gender=gender,
        race=race_val,
        desc=f"{npc_name} ({clean_role})",
        scen_key=scen_key,
        traits=traits,
        role=clean_role,
    )
    demeanor = str(app_dict.get("intimate_demeanor") or "attentive")

    npc_dict = {
        "name": npc_name,
        "role": clean_role,
        "gender": gender,
        "demeanor": demeanor,
        "traits": traits,
        "unlocked_traits": traits[:2],
        "preferences": prefs,
        "appearance": app_dict,
        "location": effective_location,
        "status_effects": ["Present"],
        "stage_role": "active_partner",
        "attention_ring": "ring_1_primary",
        "basic_info": {
            "role": clean_role,
            "gender": gender,
            "location": effective_location,
            "met_in_person": True,
        },
    }

    if sess_id:
        try:
            slug_id = re.sub(r"[^a-z0-9]+", "_", npc_name.lower()).strip("_")
            db.upsert_contact(
                sess_id,
                slug_id,
                npc_name,
                delta_score=0,
                track="platonic",
                new_traits=npc_dict["unlocked_traits"],
                new_preferences=prefs[:2],
                basic_info=npc_dict["basic_info"],
                gender=gender,
                appearance=app_dict,
            )
            db.upsert_lorebook_entity(
                session_id=sess_id,
                entity_type="person",
                name=npc_name,
                description=f"{npc_name} ({clean_role}) encountered at {effective_location}.",
                disposition="neutral",
                gender=gender,
                appearance=app_dict,
                traits=npc_dict["unlocked_traits"],
            )
        except Exception:
            pass

    return npc_dict


def compute_pre_turn_stage(
    session: dict,
    actions: list,
    party: list = None,
    ctx: any = None,
    persist_db: bool = True,
    stage_clock_cb: Optional[Any] = None,
) -> dict:
    """
    Deterministically computes the active stage roster, effective location,
    and dialogue partner intents BEFORE Pass 1 / State Arbiter prompts are constructed.

    Returns a dict with:
      - is_movement (bool)
      - effective_location (str)
      - movement_dest_str (str)
      - old_location (str)
      - traveling_companions (list[dict])
      - left_behind_patrons (list[dict])
      - stage_npcs (list[dict])
      - new_partners (list[str])
      - has_exited_convo (bool)
      - target_resident_name (str | None)
      - target_station_sub (str | None)
    """
    if not isinstance(session, dict):
        return {
            "is_movement": False,
            "effective_location": "",
            "movement_dest_str": "",
            "old_location": "",
            "traveling_companions": [],
            "left_behind_patrons": [],
            "stage_npcs": [],
            "new_partners": [],
            "has_exited_convo": False,
            "target_resident_name": None,
            "target_station_sub": None,
        }

    sess_id = session.get("id")
    scen_key = session.get("scenario", "fantasy")
    raw_curr = session.get("current_location", "")
    if sess_id and not session.get("current_node_id") and is_location_engine_enabled(scen_key):
        resolved_nid = db.resolve_node_id_from_location(sess_id, raw_curr) if raw_curr else None
        if resolved_nid:
            session["current_node_id"] = resolved_nid
        elif not raw_curr:
            try:
                from mechanics.world.locations.graph_seeder import migrate_session_to_spatial_graph
                mig_res = migrate_session_to_spatial_graph(sess_id)
                if mig_res and mig_res.get("current_node_id"):
                    session["current_node_id"] = mig_res["current_node_id"]
            except Exception:
                pass
    old_primary = get_primary_location_name(raw_curr)
    parsed_z = get_zone_location_name(raw_curr) if raw_curr else ""

    is_movement = False
    movement_dest_str = ""
    effective_location = raw_curr
    focal_point: Optional[str] = session.get("focal_point") or None
    stage_directives: list[str] = []
    schedule_departed_npcs: list[str] = []
    spawned_role_npcs: list[dict] = []
    traveling_companions: list[dict] = []
    left_behind_patrons: list[dict] = []
    target_resident_name: Optional[str] = None
    target_station_sub: Optional[str] = None
    facility_residents: list[dict] = []
    has_confidential_rendezvous: bool = False
    rendezvous_participant_names: set[str] = set()

    def _check_rendezvous_for_stage(target_loc: str, target_nid: Optional[str] = None):
        nonlocal has_confidential_rendezvous, rendezvous_participant_names, has_exited_convo
        if not sess_id or not target_loc:
            return
        try:
            from mechanics.system.commitments_engine import get_active_rendezvous_at_node, _canon_key

            s_day = session.get("current_day") if isinstance(session, dict) else None
            s_min = session.get("current_minute") if isinstance(session, dict) else None

            appts = []
            seen_ids = set()
            if target_nid:
                for r in get_active_rendezvous_at_node(sess_id, target_nid, current_day=s_day, current_minute=s_min):
                    rid = r.get("id") or id(r)
                    if rid not in seen_ids:
                        seen_ids.add(rid)
                        appts.append(r)
            for r in get_active_rendezvous_at_node(sess_id, target_loc, current_day=s_day, current_minute=s_min):
                rid = r.get("id") or id(r)
                if rid not in seen_ids:
                    seen_ids.add(rid)
                    appts.append(r)

            if not appts and s_min is None:
                eff_day = int(s_day or 1)
                for loc_probe in ([target_nid, target_loc] if target_nid else [target_loc]):
                    for r in get_active_rendezvous_at_node(sess_id, loc_probe, current_day=s_day, current_minute=s_min, enforce_window=False):
                        if int(r.get("scheduled_day") or 1) == eff_day and r.get("origin") in ("dialogue", "phone", "in_person"):
                            rid = r.get("id") or id(r)
                            if rid not in seen_ids:
                                seen_ids.add(rid)
                                appts.append(r)

            if not appts:
                return

            contact_display_map: dict[str, str] = {}
            if hasattr(db, "get_contacts"):
                try:
                    for c in (db.get_contacts(sess_id) or []):
                        c_nm = str(c.get("name") or "").strip()
                        if not c_nm:
                            continue
                        for k in (c.get("npc_id"), c_nm, _canon_key(c_nm)):
                            if k:
                                contact_display_map[str(k).strip().lower()] = c_nm
                except Exception:
                    pass

            for appt in appts:
                is_conf = bool(appt.get("is_confidential") or (appt.get("metadata") or {}).get("is_romantic"))
                if is_conf:
                    has_confidential_rendezvous = True

                parts = appt.get("participants") or []
                if not parts and appt.get("participants_json"):
                    try:
                        import json as _json
                        parts = _json.loads(appt["participants_json"])
                    except Exception:
                        parts = []

                spawned_any = False
                if parts:
                    for p in parts:
                        p_role = p.get("role", "")
                        p_key = str(p.get("person_key") or p.get("npc_id") or "").strip()
                        if p_role == "organizer" and p_key.lower() == "player":
                            continue
                        if p_key.lower() == "player":
                            continue
                        raw_name = str(p.get("name") or p_key or "").strip()
                        p_name = (
                            contact_display_map.get(p_key.lower())
                            or contact_display_map.get(_canon_key(raw_name))
                            or contact_display_map.get(raw_name.lower())
                            or (raw_name.replace("_", " ").title() if "_" in raw_name else raw_name)
                        )
                        if p_name:
                            rendezvous_participant_names.add(p_name.strip().lower())
                            if p_key:
                                rendezvous_participant_names.add(p_key.lower())
                            _add_stage_npc({"name": p_name, "role": "Rendezvous Partner", "status_effects": ["Present"]})
                            if p_name not in new_partners:
                                new_partners.append(p_name)
                            spawned_any = True

                # Fallback for single NPC rendezvous
                if not spawned_any:
                    raw_npc = str(appt.get("npc_name") or appt.get("target_entity") or "").strip()
                    if raw_npc and raw_npc.lower() not in ("group", "player"):
                        npc_name = (
                            contact_display_map.get(raw_npc.lower())
                            or contact_display_map.get(_canon_key(raw_npc))
                            or (raw_npc.replace("_", " ").title() if "_" in raw_npc else raw_npc)
                        )
                        rendezvous_participant_names.add(npc_name.strip().lower())
                        rendezvous_participant_names.add(raw_npc.lower())
                        _add_stage_npc({"name": npc_name, "role": "Rendezvous Partner", "status_effects": ["Present"]})
                        if npc_name not in new_partners:
                            new_partners.append(npc_name)
                has_exited_convo = False
        except Exception:
            pass

    # Check combat retreat / flee (A7, A12)
    unlocked_edges: list = []
    unlocked_nodes: list = []
    consumed_key_items: list = []
    blocked_invalid_exit = False
    party_cohesion_deferred = False

    is_flee = any(
        (isinstance(a, dict) and (a.get("sub_intent") == "combat_flee" or a.get("intent") == "combat_flee"))
        for a in (actions or [])
    )
    if is_flee and sess_id:
        from mechanics.world.locations.pathfinding import resolve_flee_destination
        curr_nid = session.get("current_node_id") or db.resolve_node_id_from_location(sess_id, raw_curr)
        prev_nid = session.get("previous_node_id") or (session.get("extra") or {}).get("previous_node_id")
        flee_nid, flee_loc = resolve_flee_destination(sess_id, curr_nid, prev_nid)
        if flee_nid and flee_loc:
            is_movement = True
            effective_location = flee_loc
            effective_node_id = flee_nid
            movement_dest_str = flee_loc
            session["current_node_id"] = flee_nid
            stage_directives.append(f"[STAGE DIRECTION — COMBAT RETREAT]: Fled combat back to {flee_loc}.")

    # Check movement intent across actions (only when not in active combat)
    if not is_movement and not is_in_combat(session) and actions:
        from mechanics.world.locations.movement import is_movement_action, resolve_hybrid_sublocation_or_focal_point

        _ALLOWED_FREEFORM_MOVE_INTENTS = (
            "", "general_action", "movement", "travel", "fast_travel", "move",
            "social_invite", "accompanied_travel", "dialogue_init", "investigate_clue",
        )

        # Multiplayer Co-op Local-First Priority (D15):
        # Only execute party movement when no teammate is performing a non-movement local room action.
        if len(actions) > 1:
            move_reqs = 0
            local_reqs = 0
            for a_chk in actions:
                a_lbl_chk = a_chk.get("label", "") if isinstance(a_chk, dict) else str(a_chk)
                a_int_chk = str(a_chk.get("intent") or "").strip().lower() if isinstance(a_chk, dict) else ""
                is_a_move = bool(
                    (isinstance(a_chk, dict) and (a_chk.get("target_node_id") or a_chk.get("target_location")))
                    or (a_int_chk in _ALLOWED_FREEFORM_MOVE_INTENTS and is_movement_action(a_lbl_chk))
                )
                if is_a_move:
                    move_reqs += 1
                else:
                    local_reqs += 1
            if move_reqs > 0 and local_reqs > 0:
                party_cohesion_deferred = True
                session["travel_minutes_elapsed"] = 0
                stage_directives.append(
                    "[STAGE DIRECTION — PARTY COHESION]: Party movement deferred because a teammate is acting locally in the current room."
                )

        target_nid = None
        target_loc_candidate = None
        move_action_lbl = ""
        move_action_intent = ""
        if not party_cohesion_deferred:
            for a in actions:
                if not isinstance(a, dict):
                    a_lbl = str(a)
                    if is_movement_action(a_lbl) and not move_action_lbl:
                        move_action_lbl = a_lbl
                    continue
                a_lbl = str(a.get("label") or "")
                a_int = str(a.get("intent") or "").strip().lower()
                if a.get("target_node_id"):
                    target_nid = a["target_node_id"]
                    move_action_lbl = a_lbl
                    move_action_intent = a_int or "movement"
                    break
                if a.get("target_location"):
                    target_loc_candidate = a["target_location"]
                    move_action_lbl = a_lbl
                    move_action_intent = a_int or "movement"
                    break
                if a_int in _ALLOWED_FREEFORM_MOVE_INTENTS and is_movement_action(a_lbl) and not move_action_lbl:
                    move_action_lbl = a_lbl
                    move_action_intent = a_int

        if not target_nid and target_loc_candidate and sess_id:
            target_nid = db.resolve_node_id_from_location(sess_id, target_loc_candidate)

        curr_nid = session.get("current_node_id") or (db.resolve_node_id_from_location(sess_id, raw_curr) if sess_id else None)

        # Freeform text matching (A10) — strictly gated on movement intent + word boundaries
        if not party_cohesion_deferred and not target_nid and sess_id and curr_nid:
            from mechanics.world.locations.pathfinding import (
                match_freeform_spatial_destination,
                resolve_unmatched_movement_destination,
            )
            for a in actions:
                lbl = a.get("label", "") if isinstance(a, dict) else str(a)
                a_int = str(a.get("intent") or "").strip().lower() if isinstance(a, dict) else ""
                if a_int not in _ALLOWED_FREEFORM_MOVE_INTENTS:
                    continue
                matched_nid = match_freeform_spatial_destination(sess_id, curr_nid, lbl, intent=a_int)
                if matched_nid:
                    target_nid = matched_nid
                    break

            # If still not matched and action is "Follow <NPC>" / "Go with <NPC>" / quest action, check NPC's relocated/rendezvous/scheduled node or quest waypoint
            if not target_nid:
                for a in actions:
                    lbl = a.get("label", "") if isinstance(a, dict) else str(a)
                    lbl_low = lbl.lower()
                    # 1. Quest waypoint target_location fallback if moving for a quest
                    if isinstance(a, dict) and (a.get("is_quest_action") or a.get("quest_id")) and is_movement_action(lbl):
                        try:
                            from mechanics.world.waypoints.matching import resolve_effective_waypoint_location
                            for wp in db.get_all_session_active_waypoints(sess_id):
                                if wp.get("quest_id") == a.get("quest_id") and (a.get("sub_obj_id") is None or wp.get("sub_obj_id") == a.get("sub_obj_id")):
                                    wp_loc = resolve_effective_waypoint_location(sess_id, wp) or wp.get("target_location", "")
                                    if wp_loc:
                                        wp_nid = db.resolve_node_id_from_location(sess_id, wp_loc)
                                        if wp_nid and wp_nid != curr_nid:
                                            target_nid = wp_nid
                                            break
                        except Exception:
                            pass
                    if target_nid:
                        break
                    # 2. Accompanied "Follow <NPC>" / "Go with <NPC>" destination lookup
                    if any(k in lbl_low for k in ("follow ", "go with ", "walk with ", "accompany ", "join ")):
                        cand_npc = (a.get("target_npc") if isinstance(a, dict) else "") or session.get("dialogue_partner") or ""
                        if not cand_npc:
                            m_f = re.search(r"\b(?:follow|go with|walk with|accompany|join)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", lbl)
                            if m_f:
                                cand_npc = m_f.group(1).strip()
                        if cand_npc:
                            reloc_map = (session.get("extra") or {}).get("npc_relocated_overrides") or {}
                            for rk, rv in reloc_map.items():
                                if cand_npc.lower() in rk.lower() or rk.lower() in cand_npc.lower():
                                    r_loc = rv.get("location") if isinstance(rv, dict) else str(rv)
                                    r_nid = db.resolve_node_id_from_location(sess_id, r_loc) if r_loc else None
                                    if r_nid and r_nid != curr_nid:
                                        target_nid = r_nid
                                        break
                            if not target_nid:
                                try:
                                    from mechanics.world.npc_schedule import get_npc_scheduled_node_id
                                    s_nid = get_npc_scheduled_node_id(
                                        sess_id, cand_npc,
                                        current_day=int(session.get("current_day") or 1),
                                        current_minute=int(session.get("current_minute") or 480),
                                        scen_key=scen_key,
                                    )
                                    if s_nid and s_nid != curr_nid:
                                        target_nid = s_nid
                                except Exception:
                                    pass
                    if target_nid:
                        break

            # Open-World vs. Campus Freeform Unmatched Destination Resolution (D10)
            if not target_nid and (target_loc_candidate or move_action_lbl):
                cand_lbl = move_action_lbl or (actions[0].get("label", "") if isinstance(actions[0], dict) else str(actions[0]))
                # Check micro-positioning / hybrid sub-location first so local room props aren't flagged as invalid exits
                hybrid_probe = resolve_hybrid_sublocation_or_focal_point(sess_id, raw_curr, curr_nid, cand_lbl, scen_key=scen_key)
                is_threshold_turn_back = any(k in cand_lbl.lower() for k in ("turn back", "step away", "step back", "return to campus"))
                if not hybrid_probe.get("matched") and not is_threshold_turn_back:
                    unmatched_res = resolve_unmatched_movement_destination(
                        sess_id,
                        curr_nid,
                        target_location_str=target_loc_candidate or "",
                        action_text=cand_lbl,
                        scen_key=scen_key,
                    )
                    if unmatched_res.get("blocked"):
                        blocked_invalid_exit = True
                        session["travel_minutes_elapsed"] = 0
                        if unmatched_res.get("directive"):
                            stage_directives.append(unmatched_res["directive"])
                    elif unmatched_res.get("spawned_node_id"):
                        target_nid = unmatched_res["spawned_node_id"]
                        if unmatched_res.get("directive"):
                            stage_directives.append(unmatched_res["directive"])

        if not party_cohesion_deferred and target_nid and sess_id:
            from mechanics.world.locations.pathfinding import find_spatial_path, evaluate_spatial_route
            if not curr_nid or target_nid == curr_nid:
                route = [target_nid]
            else:
                route = find_spatial_path(sess_id, curr_nid, target_nid)

            if not route:
                dest_node = db.get_world_node(sess_id, target_nid)
                if dest_node and dest_node.get("is_hidden") == 1:
                    stage_directives.append("[STAGE DIRECTION — ACCESS BLOCKED]: Location is hidden or undiscovered.")
                    blocked_invalid_exit = True
                    session["travel_minutes_elapsed"] = 0
            else:
                dest_node = db.get_world_node(sess_id, target_nid)
                dest_primary = (dest_node.get("name") if dest_node else "") or ""
                t_comps, l_patrons = classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=dest_primary)
                traveling_companions = list(t_comps or [])
                existing_comp_names = {_get_npc_name(c).lower() for c in traveling_companions if _get_npc_name(c)}
                for tc in (session.get("temporary_companions") or []):
                    tc_name = _get_npc_name(tc)
                    if tc_name and tc_name.lower() not in existing_comp_names:
                        traveling_companions.append(tc)
                        existing_comp_names.add(tc_name.lower())
                for pn in (session.get("party_npcs") or []):
                    pn_name = _get_npc_name(pn)
                    if pn_name and pn_name.lower() not in existing_comp_names:
                        traveling_companions.append(pn)
                        existing_comp_names.add(pn_name.lower())
                left_behind_patrons = l_patrons or []

                route_res = evaluate_spatial_route(
                    sess_id, route, session,
                    party=party, actions=actions,
                    traveling_companions=traveling_companions,
                    persist_db=persist_db,
                )
                is_movement = True
                effective_location = route_res["effective_location"]
                effective_node_id = route_res["effective_node_id"]
                movement_dest_str = effective_location
                if route_res.get("focal_point"):
                    focal_point = route_res["focal_point"]
                    session["focal_point"] = focal_point
                if curr_nid:
                    session["previous_node_id"] = curr_nid
                    if "extra" not in session or not isinstance(session["extra"], dict):
                        session["extra"] = {}
                    session["extra"]["previous_node_id"] = curr_nid
                session["current_node_id"] = effective_node_id
                session["travel_minutes_elapsed"] = route_res["travel_minutes"]
                traveling_companions = route_res["traveling_companions"]
                stage_directives.extend(route_res["stage_directives"])
                unlocked_edges = list(route_res.get("unlocked_edges") or [])
                unlocked_nodes = list(route_res.get("unlocked_nodes") or [])
                consumed_key_items = list(route_res.get("consumed_key_items") or [])
                access_gate_info = route_res.get("access_gate") or {"gated": route_res["gated"], "barrier_node_id": route_res["barrier_node_id"]}

        # Hydrated fallback ONLY when session does not yet have a spatial graph node
        if not party_cohesion_deferred and not blocked_invalid_exit and not is_movement and not curr_nid:
            for a in actions:
                label = a.get("label", "") if isinstance(a, dict) else str(a)
                action_dest = extract_movement_destination(label, sess_id, current_zone=parsed_z, scen_key=scen_key)
                if action_dest:
                    dest_z, dest_p = action_dest
                    movement_dest_str = f"{dest_z} ➔ {dest_p}"
                    is_crit_fail = bool(a.get("check") and getattr(a["check"], "tier", "") == "crit_fail") if isinstance(a, dict) else False

                    if not is_crit_fail:
                        is_movement = True
                        # Classify companions traveling vs left behind
                        t_comps, l_patrons = classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=dest_p)
                        traveling_companions = t_comps or []
                        left_behind_patrons = l_patrons or []

                        # Scan facility residents for target station
                        lbl_lower = (label or "").lower()
                        facility_residents = []
                        if sess_id:
                            try:
                                facility_residents = db.get_school_characters_by_facility(sess_id, f"{dest_z} ➔ {dest_p}", limit=6)
                            except Exception:
                                facility_residents = []

                        for fr in facility_residents:
                            fr_nm = (fr.get("name") or "").strip().lower()
                            if fr_nm and (fr_nm in lbl_lower or (len(fr_nm.split()) > 1 and fr_nm.split()[0] in lbl_lower)):
                                fr_fac = fr.get("primary_facility") or ""
                                if fr_fac:
                                    _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=sess_id)
                                    if fr_s and fr_s not in ("Main Area", ""):
                                        target_station_sub = fr_s
                                        target_resident_name = fr.get("name")
                                        break

                        # Check quest sub-objectives if target station not found
                        if not target_station_sub and sess_id:
                            try:
                                with db.get_conn() as _c_conn:
                                    q_rows = _c_conn.execute(
                                        "SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'",
                                        (sess_id,)
                                    ).fetchall()
                                    for qr in q_rows:
                                        sub_objs = json.loads(qr["sub_objectives_json"] or "[]")
                                        for so in sub_objs:
                                            if not so.get("completed"):
                                                 t_loc = so.get("target_location", "")
                                                 t_npc = (so.get("target_npc") or "").strip().lower()
                                                 if t_loc:
                                                     qz, qp, qs = parse_tiered_location(t_loc, scen_key, session_id=sess_id)
                                                     if qp.lower() == dest_p.lower() and qs and qs not in ("Main Area", ""):
                                                         if not t_npc or (t_npc in lbl_lower or (len(t_npc.split()) > 1 and t_npc.split()[0] in lbl_lower)):
                                                             target_station_sub = qs
                                                             target_resident_name = so.get("target_npc")
                                                             break
                                        if target_station_sub:
                                            break
                            except Exception:
                                pass

                        from mechanics.world.locations.hierarchy import resolve_default_sublocation
                        loc_prompt_target = target_station_sub or resolve_default_sublocation(dest_p, dest_z, session_id=sess_id, scenario_key=scen_key)
                        effective_location = f"{dest_z} ➔ {dest_p} ➔ {loc_prompt_target}"
                    break

        # If not moving between primary facilities, evaluate hybrid sublocation or tactical focal point
        if not party_cohesion_deferred and not blocked_invalid_exit and not is_movement and actions:
            act_lbl = actions[0].get("label", "") if isinstance(actions[0], dict) else str(actions[0])
            c_node = session.get("current_node_id") or (db.resolve_node_id_from_location(sess_id, raw_curr) if sess_id else None)
            hybrid_res = resolve_hybrid_sublocation_or_focal_point(sess_id, raw_curr, c_node, act_lbl, scen_key=scen_key)
            if hybrid_res.get("matched"):
                if hybrid_res.get("kind") == "focal_point":
                    focal_point = hybrid_res["focal_point"]
                    session["focal_point"] = focal_point
                    stage_directives.append(f"[STAGE DIRECTION — MICRO-POSITIONING]: Player moved to focal position '{focal_point}' within {effective_location}.")
                elif hybrid_res.get("kind") == "architectural_room":
                    is_movement = True
                    effective_location = hybrid_res["location"]
                    movement_dest_str = effective_location
                    pz, pp, _ = parse_tiered_location(effective_location, scen_key, session_id=sess_id)
                    t_comps, l_patrons = classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=pp)
                    traveling_companions = t_comps or []
                    left_behind_patrons = l_patrons or []
                    stage_directives.append(f"[STAGE DIRECTION — ARCHITECTURAL EXPLORATION]: Entered inner chamber {effective_location}.")

        # Immediate Forced Eviction when ANY stealth/covert check fails inside a restricted, private, or curfew-locked area (Issue 11)
        if not party_cohesion_deferred and sess_id and actions and not is_movement:
            try:
                from mechanics.stealth import (
                    break_stealth,
                    is_strict_trespass_or_restricted_stealth_zone,
                    record_failed_stealth_lockout,
                )
                from mechanics.world.locations.access_gate import get_node_effective_access_info
                from mechanics.world.locations.pathfinding import resolve_safe_open_eviction_destination

                lead_act = actions[0] if isinstance(actions[0], dict) else {}
                chk_obj = lead_act.get("check")
                chk_tier = str(
                    (chk_obj.get("tier") if isinstance(chk_obj, dict) else getattr(chk_obj, "tier", ""))
                    if chk_obj is not None
                    else lead_act.get("tier", "")
                ).lower()
                chk_failed = chk_tier in ("fail", "failure", "crit_fail", "critical_failure") or (
                    chk_obj is not None
                    and not bool(chk_obj.get("succeeded", True) if isinstance(chk_obj, dict) else getattr(chk_obj, "succeeded", True))
                )
                act_lbl_low = str(lead_act.get("label") or lead_act.get("text") or "").lower()
                is_covert_attempt = bool(
                    lead_act.get("is_stealth")
                    or lead_act.get("stance") == "stealth"
                    or str(lead_act.get("intent") or "").lower() in ("stealth_covert", "stealth")
                    or str(lead_act.get("action_category") or "").lower() == "stealth"
                    or str(lead_act.get("approach") or "").lower() == "stealth_guile"
                    or any(
                        w in act_lbl_low
                        for w in (
                            "sneak", "infiltrate", "lockpick", "pick the lock", "slip past",
                            "creep", "[stealth", "[diversion", "shadow step", "careful bypass",
                        )
                    )
                )
                if chk_failed and is_covert_attempt:
                    c_nid = str(session.get("current_node_id") or db.resolve_node_id_from_location(sess_id, raw_curr) or "").strip()
                    c_day = int(session.get("current_day", 1) or 1)
                    c_min = int(session.get("current_minute", 480) or 480)
                    record_failed_stealth_lockout(session, node_id=c_nid, label=str(lead_act.get("label") or ""))
                    acc_here = (
                        get_node_effective_access_info(sess_id, c_nid, current_day=c_day, current_minute=c_min, scen_key=scen_key)
                        if c_nid
                        else {}
                    )
                    in_restricted_or_curfew = bool(
                        acc_here.get("access_tier") in ("restricted", "private", "locked")
                        or acc_here.get("curfew_active")
                        or acc_here.get("is_trespassing")
                        or acc_here.get("schedule_locked")
                        or is_strict_trespass_or_restricted_stealth_zone(session, lead_act)
                    )
                    if in_restricted_or_curfew:
                        evict_nid, evict_loc = resolve_safe_open_eviction_destination(
                            sess_id,
                            c_nid,
                            current_day=c_day,
                            current_minute=c_min,
                            scen_key=scen_key,
                            current_location=raw_curr,
                            previous_node_id=session.get("previous_node_id"),
                        )
                        if evict_loc and evict_loc != raw_curr:
                            is_movement = True
                            effective_location = evict_loc
                            effective_node_id = evict_nid or c_nid
                            movement_dest_str = evict_loc
                            session["current_node_id"] = effective_node_id
                            session["current_location"] = evict_loc
                            session["travel_minutes_elapsed"] = int(session.get("travel_minutes_elapsed") or 0) + 10
                            break_stealth(session, reason="evicted_from_restricted_area", break_all=True)
                            stage_directives.append(
                                f"[MANDATORY OUTCOME — STEALTH FAILURE & IMMEDIATE EVICTION]: "
                                f"The player failed their stealth check ('{lead_act.get('label', 'stealth attempt')}') inside {raw_curr}. "
                                f"They were immediately spotted by security/authority and forcibly escorted out to '{evict_loc}'. "
                                f"Place the end of the turn at '{evict_loc}'."
                            )
            except Exception:
                pass

    # Advance staged clock AFTER Phase 4 Spatial/Dijkstra so schedule checks use post-travel clock (D3)
    if callable(stage_clock_cb):
        stage_clock_cb(
            is_movement=is_movement,
            effective_location=effective_location,
            travel_minutes=session.get("travel_minutes_elapsed"),
            blocked_invalid_exit=blocked_invalid_exit,
        )

    # Compute dialogue intent
    from game_engine.turn.dialogue import _compute_dialogue_intent
    new_partners, has_exited_convo = _compute_dialogue_intent(session, actions)

    # Compute stage_npcs
    stage_npcs: list[dict] = []
    seen_stage_names = set()
    access_gate_info = access_gate_info if ('access_gate_info' in locals() and access_gate_info and access_gate_info.get("gated")) else {"gated": False}

    def _add_stage_npc(npc_dict: dict):
        if not isinstance(npc_dict, dict):
            return
        nm = _get_npc_name(npc_dict)
        if not nm:
            return
        nm_low = nm.strip().lower()
        if nm_low not in seen_stage_names:
            seen_stage_names.add(nm_low)
            stage_npcs.append(dict(npc_dict))

    if is_movement:
        # 1. Traveling companions
        for c in traveling_companions:
            _add_stage_npc(c)

        if not ('effective_node_id' in locals() and effective_node_id):
            effective_node_id = db.resolve_node_id_from_location(sess_id, effective_location) if (sess_id and effective_location) else None

        if access_gate_info.get("patrol_npc"):
            _add_stage_npc(access_gate_info["patrol_npc"])
            patrol_nm = access_gate_info["patrol_npc"].get("name")
            if patrol_nm and patrol_nm not in new_partners:
                new_partners.append(patrol_nm)

        # 2. Check for active/pending phone appointments / commitments at arrival destination
        if not access_gate_info.get("gated"):
            _check_rendezvous_for_stage(effective_location, effective_node_id)

        # 3. Add target resident or schedule-verified facility occupants stationed there
        curr_stage_min = int(session.get("current_minute", 480) or 480)
        curr_stage_day = int(session.get("current_day", 1) or 1)
        scheduled_residents = []
        if not access_gate_info.get("gated") and sess_id and effective_location:
            try:
                from mechanics.world.mobility import is_campus_scenario
                if is_campus_scenario(scen_key):
                    from mechanics.social.school_roster import get_facility_ambient_characters
                    scheduled_residents = get_facility_ambient_characters(
                        sess_id,
                        effective_location,
                        limit=3,
                        current_day=curr_stage_day,
                        current_minute=curr_stage_min,
                        active_npc_names=seen_stage_names,
                    )
                elif scenario_data.is_anomalous_incursions_scenario(scen_key):
                    from mechanics.social.agent_roster import get_anomalous_facility_ambient_agents
                    scheduled_residents = get_anomalous_facility_ambient_agents(
                        sess_id,
                        effective_location,
                        limit=3,
                        current_day=curr_stage_day,
                        current_minute=curr_stage_min,
                        active_npc_names=seen_stage_names,
                    )
                elif 420 <= (curr_stage_min % 1440) < 1200:
                    scheduled_residents = list(facility_residents or [])
            except Exception:
                scheduled_residents = list(facility_residents or []) if (420 <= (curr_stage_min % 1440) < 1200) else []

        if target_resident_name and not access_gate_info.get("gated"):
            sched_res_names = {str(r.get("name") or "").strip().lower() for r in scheduled_residents}
            # Never auto-stage a campus/HQ resident who is off-duty at night unless verified by schedule
            if target_resident_name.strip().lower() in sched_res_names or (420 <= (curr_stage_min % 1440) < 1200):
                _add_stage_npc({"name": target_resident_name, "role": "Resident", "status_effects": ["Present"]})

        if not access_gate_info.get("gated") and scheduled_residents:
            fac_added = 0
            for fr in scheduled_residents:
                if len(stage_npcs) >= 4 or fac_added >= 3:
                    break
                fr_nm = fr.get("name")
                if not fr_nm or fr_nm.strip().lower() in seen_stage_names:
                    continue
                _add_stage_npc({
                    "name": fr_nm,
                    "role": fr.get("role") or "Faculty",
                    "status_effects": ["Present"],
                    "stage_role": "room_bystander",
                    "attention_ring": "ring_3_bystander",
                    "facility_resident": True
                })
                fac_added += 1

        # 4. Add explicitly relocated schedule-departed NPCs + scheduled NPCs at arrival destination
        if effective_location and not access_gate_info.get("gated"):
            try:
                from mechanics.world.schedules import get_time_block_key
                from mechanics.world.waypoints import check_location_matches_waypoint
                curr_min_rel = int(session.get("current_minute", 480) or 480)
                curr_day_rel = int(session.get("current_day", 1) or 1)
                curr_blk_rel = get_time_block_key(curr_min_rel)
                rel_overrides = session.get("npc_relocated_overrides")
                if not isinstance(rel_overrides, dict) and isinstance(session.get("extra"), dict):
                    rel_overrides = session["extra"].get("npc_relocated_overrides")
                if isinstance(rel_overrides, dict):
                    for _, r_rec in rel_overrides.items():
                        if not isinstance(r_rec, dict):
                            continue
                        r_nm = str(r_rec.get("name") or "").strip()
                        r_loc = str(r_rec.get("location") or "").strip()
                        r_nid = str(r_rec.get("node_id") or "").strip()
                        if not r_nm or r_nm.lower() in seen_stage_names:
                            continue
                        if int(r_rec.get("day") or curr_day_rel) != curr_day_rel:
                            continue
                        dep_min = int(r_rec.get("minute") if r_rec.get("minute") is not None else curr_min_rel)
                        same_blk = (not r_rec.get("block")) or (str(r_rec.get("block")) == curr_blk_rel)
                        if not same_blk and not (0 <= (curr_min_rel - dep_min) <= 180):
                            continue
                        rel_match = False
                        if r_nid and effective_node_id and sess_id:
                            rel_match = (
                                r_nid == effective_node_id
                                or db.is_descendant_of(sess_id, effective_node_id, r_nid)
                                or db.is_descendant_of(sess_id, r_nid, effective_node_id)
                            )
                        if not rel_match and r_loc:
                            rel_match = check_location_matches_waypoint(
                                effective_location, r_loc, session_id=sess_id, current_node_id=effective_node_id
                            ) or (r_loc.split("➔")[-1].strip().lower() in effective_location.lower())
                        if rel_match:
                            _add_stage_npc({
                                "name": r_nm,
                                "role": "Resident",
                                "status_effects": ["Present"],
                                "stage_role": "room_bystander",
                                "attention_ring": "ring_3_bystander",
                                "scheduled_station": True,
                            })
            except Exception:
                pass

        if len(stage_npcs) < 4 and sess_id and effective_location and not access_gate_info.get("gated"):
            try:
                from mechanics.world.schedules import get_npc_scheduled_node_id, get_npc_scheduled_location
                from mechanics.world.waypoints import check_location_matches_waypoint
                curr_min = int(session.get("current_minute", 480) or 480)
                curr_day = int(session.get("current_day", 1) or 1)
                contacts = db.get_contacts(sess_id) or []
                roster = db.get_school_roster(sess_id) if hasattr(db, "get_school_roster") else []
                # Known contacts prioritized first, then roster
                seen_cand_names = set()
                combined_cands = []
                for c in contacts + roster:
                    c_nm = (c.get("name") or "").strip()
                    if c_nm and c_nm.lower() not in seen_cand_names:
                        seen_cand_names.add(c_nm.lower())
                        combined_cands.append(c)

                scheduled_added = 0
                for cand in combined_cands[:25]:
                    if scheduled_added >= 2:
                        break
                    cand_name = cand.get("name")
                    if not cand_name or cand_name.lower() in seen_stage_names:
                        continue
                    sched_node = get_npc_scheduled_node_id(cand, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                    is_match = False
                    if sched_node and effective_node_id:
                        is_match = (
                            sched_node == effective_node_id
                            or db.is_descendant_of(sess_id, effective_node_id, sched_node)
                            or db.is_descendant_of(sess_id, sched_node, effective_node_id)
                        )
                    elif not sched_node or not effective_node_id:
                        sched_loc = get_npc_scheduled_location(cand, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                        if sched_loc:
                            is_match = check_location_matches_waypoint(
                                effective_location, sched_loc,
                                session_id=sess_id, current_node_id=effective_node_id
                            )
                    if is_match:
                        _add_stage_npc({
                            "name": cand_name,
                            "role": cand.get("role") or (cand.get("basic_info") or {}).get("role") or "Student",
                            "status_effects": ["Present"],
                            "stage_role": "room_bystander",
                            "attention_ring": "ring_3_bystander",
                            "scheduled_station": True
                        })
                        scheduled_added += 1
            except Exception:
                pass
    else:
        # Same location: start with current_npcs
        old_npcs = session.get("current_npcs") or []
        curr_min = int(session.get("current_minute", 480) or 480)
        curr_day = int(session.get("current_day", 1) or 1)
        prev_min = session.get("_prev_turn_minute")
        prev_day = session.get("_prev_turn_day")
        curr_node_id_val = session.get("current_node_id") or (db.resolve_node_id_from_location(sess_id, raw_curr) if sess_id else None)
        bound_info = {"crossed": False}

        if prev_min is not None and prev_min != curr_min:
            from mechanics.world.schedules import detect_schedule_boundary_crossed
            bound_info = detect_schedule_boundary_crossed(prev_day or curr_day, prev_min, curr_day, curr_min, scen_key=scen_key)
            if bound_info.get("crossed"):
                trans_lbl = bound_info.get("transition_label") or "Schedule Transition"
                stage_directives.append(
                    f"[STAGE DIRECTION — SCHEDULE TRANSITION ({trans_lbl})]: Time block shifted to {bound_info.get('new_phase')}. "
                    f"Ambient room occupants transition to their scheduled locations."
                )
                partner_names_lower = {p.strip().lower() for p in new_partners}
                for n in list(old_npcs):
                    n_nm = _get_npc_name(n)
                    if not n_nm or n_nm.strip().lower() in partner_names_lower:
                        continue
                    from mechanics.world.npc_schedule import get_npc_scheduled_node_id
                    n_target_nid = get_npc_scheduled_node_id(n, current_minute=curr_min, current_day=curr_day, scen_key=scen_key)
                    if n_target_nid and curr_node_id_val and n_target_nid != curr_node_id_val:
                        schedule_departed_npcs.append(n_nm)

        for n in old_npcs:
            if not isinstance(n, dict):
                continue
            nm = _get_npc_name(n)
            if not nm or nm in schedule_departed_npcs:
                continue
            # If the player explicitly exited dialogue or dismissed them
            if has_exited_convo and nm.strip().lower() in [p.lower() for p in get_session_dialogue_partners(session)]:
                # Conversational exit does not necessarily physically remove them, but they are no longer active dialogue partner
                pass
            _add_stage_npc(n)

        # Traveling/temporary companions and party members who are with the player
        for comp in (session.get("temporary_companions") or []) + (party or session.get("party") or []):
            if isinstance(comp, dict) and comp.get("name"):
                c_name = comp.get("name")
                if c_name.strip().lower() not in seen_stage_names:
                    _add_stage_npc({
                        "name": c_name,
                        "role": comp.get("role") or "Companion",
                        "status_effects": ["Present"],
                        "stage_role": "party_companion",
                        "attention_ring": "ring_2_attentive_peer"
                    })

        # Check for active/pending appointments / commitments at current location
        _check_rendezvous_for_stage(effective_location, curr_node_id_val)

        # If schedule crossed, introduce newly scheduled arrivals at this location
        if prev_min is not None and prev_min != curr_min and bound_info.get("crossed") and sess_id and curr_node_id_val:
            try:
                from mechanics.world.npc_schedule import get_npc_scheduled_node_id
                contacts = db.get_contacts(sess_id) or []
                roster = db.get_school_roster(sess_id) if hasattr(db, "get_school_roster") else []
                newly_added = 0
                for cand in contacts + roster:
                    if newly_added >= 2:
                        break
                    cand_nm = cand.get("name")
                    if not cand_nm or cand_nm.lower() in seen_stage_names:
                        continue
                    sched_n = get_npc_scheduled_node_id(cand, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                    if sched_n == curr_node_id_val or (db.is_descendant_of(sess_id, curr_node_id_val, sched_n) or db.is_descendant_of(sess_id, sched_n, curr_node_id_val)):
                        _add_stage_npc({
                            "name": cand_nm,
                            "role": cand.get("role") or (cand.get("basic_info") or {}).get("role") or "Student",
                            "status_effects": ["Present"],
                            "stage_role": "room_bystander",
                            "attention_ring": "ring_3_bystander",
                            "scheduled_station": True,
                        })
                        newly_added += 1
            except Exception:
                pass

        # Multi-Turn Threshold Evaluation (Turn 2 breach / intercom / sneak / truancy attempt)
        curr_loc = session.get("current_location", "")
        action_str = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or [])).lower()
        is_threshold_turn = (
            "outside the locked entrance" in curr_loc.lower()
            or any(w in action_str for w in (
                "sneak in", "sneak out", "pick the lock", "pick lock", "climb", "scale", "fence",
                "ring the intercom", "talk your way", "convince the gatekeeper", "excuse", "slip away", "return to campus"
            ))
        )
        if is_threshold_turn and sess_id:
            curr_node_id = session.get("current_node_id") or db.resolve_node_id_from_location(sess_id, curr_loc)
            if curr_node_id:
                try:
                    from mechanics.world.locations.access_gate import evaluate_node_access_gate
                    access_gate_info = evaluate_node_access_gate(
                        sess_id, curr_node_id, session,
                        actions=actions, party=party, companions=session.get("temporary_companions", [])
                    )
                    if access_gate_info.get("patrol_npc"):
                        _add_stage_npc(access_gate_info["patrol_npc"])
                        patrol_nm = access_gate_info["patrol_npc"].get("name")
                        if patrol_nm and patrol_nm not in new_partners:
                            new_partners.append(patrol_nm)
                    elif not access_gate_info.get("gated"):
                        if access_gate_info.get("returned_to_campus"):
                            from mechanics.world.locations.seeds import get_session_school_name
                            school_zone = get_session_school_name(sess_id, scen_key) or "Main Academy Campus"
                            curr_node_id = "loc_courtyard"
                            session["current_node_id"] = curr_node_id
                            effective_location = f"{school_zone} ➔ Central Courtyard ➔ Main Area"
                            focal_point = None
                        elif access_gate_info.get("resolved_target_node_id"):
                            curr_node_id = access_gate_info["resolved_target_node_id"]
                            session["current_node_id"] = curr_node_id
                            res_node = db.get_world_node(sess_id, curr_node_id)
                            if res_node:
                                p_node = db.get_world_node(sess_id, res_node["parent_id"]) if res_node.get("parent_id") else None
                                z_node = db.get_world_node(sess_id, p_node["parent_id"]) if (p_node and p_node.get("parent_id")) else p_node
                                zn = z_node["name"] if z_node else "Commercial District"
                                pn = p_node["name"] if (p_node and res_node.get("node_type") == "ROOM") else res_node["name"]
                                sn = res_node["name"] if res_node.get("node_type") == "ROOM" else "Main Area"
                                effective_location = f"{zn} ➔ {pn} ➔ {sn}"
                            focal_point = None
                        else:
                            # Unlocked! Clear threshold sub-location and move inside!
                            from mechanics.world.locations.pathfinding import format_node_hierarchy
                            node_loc = format_node_hierarchy(sess_id, curr_node_id) if curr_node_id else ""
                            if node_loc and "➔" in node_loc:
                                effective_location = node_loc
                            else:
                                sep = "➔" if "➔" in curr_loc else "->"
                                parts = [p.strip() for p in curr_loc.split(sep) if p.strip()]
                                pz = parts[0] if len(parts) >= 1 else "Main Academy Campus"
                                pp = parts[1] if len(parts) >= 2 else (parts[0] if parts else "Main Area")
                                effective_location = f"{pz} ➔ {pp} ➔ Main Area"
                            focal_point = None
                    else:
                        if access_gate_info.get("halt_location_override"):
                            effective_location = access_gate_info["halt_location_override"]
                        if access_gate_info.get("node_id"):
                            curr_node_id = access_gate_info["node_id"]
                            session["current_node_id"] = curr_node_id
                        focal_point = access_gate_info.get("focal_point") or "Outside the Locked Entrance"
                except Exception:
                    pass

    # Hydrate stage_npcs with known contact data before Ring 1/2/3 classification and micro-blocking
    known_contacts = []
    if ctx and hasattr(ctx, "contacts") and ctx.contacts:
        known_contacts = ctx.contacts
    elif sess_id:
        try:
            known_contacts = db.get_contacts(sess_id) or []
        except Exception:
            known_contacts = []

    contacts_by_low = {
        str(c.get("name") or "").strip().lower(): c
        for c in (known_contacts or [])
        if isinstance(c, dict) and c.get("name")
    }

    import namegen
    contact_peer_names = list(contacts_by_low.keys())
    contact_tokens_map = {
        k: namegen.get_unique_person_tokens(k, peer_names=contact_peer_names)
        for k in contact_peer_names
    }
    for npc in stage_npcs:
        nm = _get_npc_name(npc)
        if not nm:
            continue
        nm_low = nm.strip().lower()
        c_match = contacts_by_low.get(nm_low)
        if not c_match:
            npc_toks = namegen.get_unique_person_tokens(nm, peer_names=stage_npcs) - {nm_low}
            if npc_toks:
                matches = [c for k, c in contacts_by_low.items() if npc_toks & contact_tokens_map.get(k, set())]
                if len(matches) == 1:
                    c_match = matches[0]
        if c_match:
            for fld in (
                "relationship_score", "track", "relations", "unlocked_traits",
                "preferences", "basic_info", "club", "emotional_tone",
                "open_thread", "traits", "demeanor"
            ):
                if npc.get(fld) is None and c_match.get(fld) is not None:
                    npc[fld] = c_match[fld]
            if not npc.get("role") and isinstance(c_match.get("basic_info"), dict) and c_match["basic_info"].get("role"):
                npc["role"] = c_match["basic_info"]["role"]

    # Ensure stage_role and attention_ring tag on all stage_npcs
    partner_set = {p.strip().lower() for p in new_partners}
    for npc in stage_npcs:
        nm = _get_npc_name(npc).strip().lower()
        if nm in partner_set:
            npc["stage_role"] = "active_partner"
            npc["attention_ring"] = "ring_1_primary"
        else:
            s_role = npc.get("stage_role", "room_bystander")
            npc["stage_role"] = s_role
            if s_role == "party_companion":
                npc["attention_ring"] = "ring_2_attentive_peer"
            else:
                track = str(npc.get("track", "platonic")).lower()
                score = npc.get("relationship_score", 0)
                rom_info = npc.get("relations", {}).get("romance", {}) if isinstance(npc.get("relations"), dict) else {}
                has_romantic = (track == "romantic") or (score >= 50) or bool(rom_info.get("crush_on_player"))
                has_rivalry = bool(npc.get("relations", {}).get("rival") or npc.get("relations", {}).get("is_rival")) if isinstance(npc.get("relations"), dict) else False
                is_quest = bool(npc.get("is_quest_target") or npc.get("role") in ("Rendezvous Partner", "Quest Target"))
                traits_l = [str(t).lower() for t in (npc.get("traits") or npc.get("unlocked_traits") or [])]
                dem_l = str(npc.get("demeanor") or "").lower()
                has_attentive_trait = any(k in dem_l or any(k in t for t in traits_l) for k in ("bold", "shameless", "nosy", "curious", "flirtatious", "extrovert", "jealous", "protective"))

                if has_romantic or has_rivalry or is_quest or has_attentive_trait:
                    npc["attention_ring"] = "ring_2_attentive_peer"
                else:
                    npc["attention_ring"] = "ring_3_bystander"

    # Synchronize micro-blocking and in-scene composure momentum with session["scene_stage_state"]
    from mechanics.world.schedules import get_time_block_key
    from mechanics.social.persona.actor_card import derive_initial_micro_blocking

    curr_min = int(session.get("current_minute", 480) or 480)
    time_block = session.get("time_slot") or get_time_block_key(curr_min)
    scene_stage_state = session.setdefault("scene_stage_state", {})

    if is_movement:
        traveling_names = {_get_npc_name(c).strip().lower() for c in traveling_companions if _get_npc_name(c)}
        pruned_state = {}
        for k_nm, v_state in scene_stage_state.items():
            if k_nm in traveling_names:
                if isinstance(v_state, dict) and "micro_blocking" in v_state:
                    v_state["micro_blocking"]["proximity"] = "side_by_side"
                pruned_state[k_nm] = v_state
        session["scene_stage_state"] = pruned_state
        scene_stage_state = pruned_state
        if sess_id:
            try:
                db.update_session(sess_id, extra={"scene_stage_state": pruned_state})
            except Exception:
                pass

    for npc in stage_npcs:
        nm = _get_npc_name(npc)
        if not nm:
            continue
        nm_low = nm.strip().lower()
        s_role = npc.get("stage_role", "room_bystander")

        if nm_low not in scene_stage_state:
            initial_blocking = derive_initial_micro_blocking(
                npc,
                current_location=effective_location,
                time_slot=time_block,
                stage_role=s_role,
            )
            scene_stage_state[nm_low] = {
                "micro_blocking": initial_blocking,
                "composure_state": "composed",
                "composure_ttl": 0,
            }
        else:
            st = scene_stage_state[nm_low]
            if npc.get("stage_role") == "active_partner" and isinstance(st.get("micro_blocking"), dict):
                if st["micro_blocking"].get("proximity") == "across_room":
                    st["micro_blocking"]["proximity"] = "conversational_distance"
                if st["micro_blocking"].get("prop_focus") == "absorbed":
                    st["micro_blocking"]["prop_focus"] = "paused_attentive"

        npc["micro_blocking"] = dict(scene_stage_state[nm_low].get("micro_blocking") or {})
        npc["composure_state"] = scene_stage_state[nm_low].get("composure_state", "composed")

    # 5. Pre-Turn Canonical Role Spawning (ActionCommand.spawns_npc_role + fallback role-noun detection)
    _CANONICAL_ROLE_KEYWORDS = (
        "guard", "watchman", "sentry", "soldier", "knight", "patrol",
        "bartender", "barkeep", "innkeeper", "barista", "waiter", "waitress", "server", "maid", "butler",
        "merchant", "shopkeeper", "vendor", "trader", "clerk", "cashier", "receptionist",
        "blacksmith", "armorer", "alchemist", "apothecary",
        "healer", "nurse", "doctor", "librarian", "archivist", "scholar",
        "teacher", "professor", "instructor", "student", "classmate", "upperclassman", "senpai",
        "janitor", "caretaker", "priest", "monk", "nun", "guildmaster", "captain", "officer", "detective",
        "rep", "representative", "club rep", "member", "director", "lead", "president", "aide", "editor",
        "monitor", "runner", "painter", "council", "organizer", "host", "usher", "actor", "actress",
    )
    from game_engine.turn.generation import _SPAWN_ROLE_RE
    for a in (actions or []):
        role_req = str(a.get("spawns_npc_role") or "").strip() if isinstance(a, dict) else ""
        if not role_req:
            lbl_str = str(a.get("label", "") if isinstance(a, dict) else a).strip()
            m_role = _SPAWN_ROLE_RE.search(lbl_str)
            if m_role:
                cand_r = m_role.group(1).strip()
                if any(rk in cand_r.lower() for rk in _CANONICAL_ROLE_KEYWORDS):
                    role_req = cand_r
        if role_req:
            already_has_role = any(
                role_req.lower() in str(n.get("role", "")).lower()
                or role_req.lower() in _get_npc_name(n).lower()
                for n in stage_npcs
            )
            if not already_has_role:
                sp_npc = _spawn_canonical_role_npc_pre_turn(session, role_req, effective_location)
                _add_stage_npc(sp_npc)
                if sp_npc["name"] not in new_partners:
                    new_partners.append(sp_npc["name"])
                spawned_role_npcs.append(sp_npc)
                stage_directives.append(
                    f"[STAGE DIRECTION — CANONICAL ROLE ENCOUNTER]: The {sp_npc['role']} approached by the player is {sp_npc['name']}. "
                    f"Use their exact canonical name '{sp_npc['name']}' in narrative."
                )

    # 6. Deterministic Scene Tension Timer & Escalation Spawning
    from game_engine.npcs.dialogue_tracking import evaluate_and_tick_scene_tension_timer
    tension_res = evaluate_and_tick_scene_tension_timer(
        session, actions=actions, is_movement=is_movement, access_gated=bool(access_gate_info.get("gated"))
    )
    if tension_res.get("spawned_patrol_npc"):
        _add_stage_npc(tension_res["spawned_patrol_npc"])
        p_nm = tension_res["spawned_patrol_npc"].get("name")
        if p_nm and p_nm not in new_partners:
            new_partners.append(p_nm)
    if tension_res.get("spawned_hostile_enemy"):
        curr_hostiles = session.setdefault("nearby_enemies", [])
        if not any(_get_npc_name(m).lower() == tension_res["spawned_hostile_enemy"].get("name", "").lower() for m in curr_hostiles if isinstance(m, dict)):
            curr_hostiles.append(tension_res["spawned_hostile_enemy"])
    if tension_res.get("stage_direction"):
        stage_directives.append(tension_res["stage_direction"])

    # Invariant 4: Stage Isolation for confidential / romantic 1-on-1 dates
    if has_confidential_rendezvous and rendezvous_participant_names:
        from game_engine.npcs.dialogue_tracking import is_npc_invited_in_action
        filtered_stage = []
        isolated_any = False
        for snpc in stage_npcs:
            s_name = (snpc.get("name") or "").strip().lower()
            if s_name in rendezvous_participant_names or is_npc_invited_in_action(s_name, actions):
                filtered_stage.append(snpc)
            elif snpc.get("role") == "Rendezvous Partner":
                filtered_stage.append(snpc)
            else:
                seen_stage_names.discard(s_name)
                isolated_any = True
        stage_npcs = filtered_stage
        if isolated_any:
            stage_directives.append(
                "[STAGE DIRECTION — PRIVATE RENDEZVOUS]: Confidential 1-on-1 meetup. Party companions step aside and wait in the outer antechamber."
            )

    resolved_node_id = (
        effective_node_id if (is_movement and 'effective_node_id' in locals() and effective_node_id)
        else (session.get("current_node_id") or (db.resolve_node_id_from_location(sess_id, effective_location) if sess_id else None))
    )

    ret_stage = {
        "is_movement": is_movement,
        "effective_location": effective_location,
        "effective_node_id": resolved_node_id,
        "focal_point": focal_point,
        "movement_dest_str": movement_dest_str,
        "old_location": raw_curr,
        "traveling_companions": traveling_companions,
        "left_behind_patrons": left_behind_patrons,
        "stage_npcs": stage_npcs,
        "new_partners": new_partners,
        "has_exited_convo": has_exited_convo,
        "target_resident_name": target_resident_name,
        "target_station_sub": target_station_sub,
        "access_gate": access_gate_info,
        "schedule_departed_npcs": schedule_departed_npcs,
        "spawned_role_npcs": spawned_role_npcs,
        "stage_directives": stage_directives,
        "unlocked_edges": unlocked_edges,
        "unlocked_nodes": unlocked_nodes,
        "consumed_key_items": consumed_key_items,
        "blocked_invalid_exit": blocked_invalid_exit,
        "party_cohesion_deferred": party_cohesion_deferred,
    }
    if isinstance(session, dict):
        session["pre_turn_stage_npcs"] = list(stage_npcs)
    return ret_stage


def update_stage_blocking_and_composure_post_turn(
    session: dict,
    actions: list,
    narrative: str,
    rel_deltas: dict = None,
) -> dict:
    """
    Deterministically evolves everyday micro-blocking (proximity, prop focus)
    and in-scene composure momentum (composed, flustered, warm_softened, prickly_defensive, intrigued)
    based on the player's turn actions, relationship score deltas, and generated narrative.
    """
    if not isinstance(session, dict):
        return {}

    scene_stage_state = session.setdefault("scene_stage_state", {})
    if not scene_stage_state:
        return scene_stage_state

    act_text = " ".join(str(a.get("label", "") if isinstance(a, dict) else a).lower() for a in (actions or []))
    nar_low = str(narrative or "").lower()
    combined_text = f"{act_text} {nar_low}"
    rel_deltas = rel_deltas or {}

    # Proximity cue keywords
    touch_kws = ("touch", "caress", "hold hand", "kiss", "embrace", "pull close", "wrap arms", "cuddle", "stroke", "undress")
    approach_kws = ("approach", "step closer", "walk over", "sit next", "sit beside", "close distance", "lean in", "join at the table", "take a seat", "sit with")
    retreat_kws = ("step back", "back away", "retreat", "leave distance", "walk away", "excuse yourself and leave", "pull away")

    # Composure cue keywords
    flirt_kws = ("flirt", "tease", "wink", "compliment appearance", "whisper warmly", "lean close", "boldly suggest")
    insult_kws = ("insult", "threaten", "demand", "mock", "caught in a lie", "lie", "deceive", "scoff")
    warm_kws = ("thank", "praise", "comfort", "reassure", "help", "gift", "agree", "encourage")
    probe_kws = ("investigate", "interrogate", "pry", "question motives", "press for truth", "curious about")
    suspicious_kws = ("snoop", "sneak", "stealth", "lockpick", "pick lock", "eavesdrop", "rummage", "search desk", "pocket", "caught snooping")
    suspicious_nar_cues = ("suspicious", "narrows their eyes", "narrowed their eyes", "what are you doing", "hiding something", "caught you", "caught in the act")

    any_check_failed = any(
        (a.get("check") and hasattr(a["check"], "succeeded") and not a["check"].succeeded)
        or a.get("success") is False
        for a in (actions or [])
        if isinstance(a, dict)
    )

    import namegen
    for npc_name_k, state in scene_stage_state.items():
        if not isinstance(state, dict):
            continue

        mb = state.setdefault("micro_blocking", {})
        cur_prox = mb.get("proximity", "conversational_distance")
        npc_name_norm = npc_name_k.replace("_", " ").strip()
        npc_first = (npc_name_norm.split() or [""])[0]
        npc_given = namegen.extract_first_and_last_name(npc_name_norm)[0].lower().strip()
        npc_tokens = {t for t in (npc_first, npc_given) if len(t) >= 3 and t not in namegen.NAME_PARTICLES_AND_HONORIFICS}

        def _name_in(text: str) -> bool:
            return npc_name_k in text or npc_name_norm in text or any(f" {tok}" in f" {text}" for tok in npc_tokens)

        # 1. Proximity Evolution
        is_touch = (
            any(kw in combined_text and _name_in(combined_text) for kw in touch_kws)
            or (_name_in(act_text) and any(kw in act_text for kw in touch_kws))
            or (_name_in(combined_text) and "hold" in combined_text and "hand" in combined_text)
            or (_name_in(combined_text) and "take" in combined_text and "hand" in combined_text)
        )
        if is_touch:
            mb["proximity"] = "personal_space"
            mb["prop_focus"] = "set_aside"
        elif any(kw in combined_text and _name_in(combined_text) for kw in approach_kws) or (_name_in(act_text) and any(kw in act_text for kw in approach_kws)):
            if cur_prox == "across_room":
                mb["proximity"] = "conversational_distance"
            elif cur_prox == "conversational_distance":
                mb["proximity"] = "side_by_side"
            if mb.get("prop_focus") == "absorbed":
                mb["prop_focus"] = "paused_attentive"
        elif any(kw in combined_text and _name_in(combined_text) for kw in retreat_kws) or (_name_in(act_text) and any(kw in act_text for kw in retreat_kws)):
            mb["proximity"] = "across_room"
            mb["prop_focus"] = "absorbed"

        # 2. Composure Momentum Evolution
        cur_comp = state.get("composure_state", "composed")
        cur_ttl = state.get("composure_ttl", 0)

        r_delta = (
            rel_deltas.get(npc_name_k)
            or rel_deltas.get(npc_name_norm)
            or rel_deltas.get(npc_first)
            or 0
        )
        has_new_trigger = False

        if r_delta >= 3 or (_name_in(act_text) and any(kw in act_text for kw in warm_kws)):
            state["composure_state"] = "warm_softened"
            state["composure_ttl"] = 2
            has_new_trigger = True
        elif (_name_in(act_text) and any(kw in act_text for kw in suspicious_kws) and any_check_failed) or (any(kw in combined_text for kw in suspicious_nar_cues) and _name_in(combined_text)):
            state["composure_state"] = "suspicious"
            state["composure_ttl"] = 2
            has_new_trigger = True
        elif r_delta <= -2 or (_name_in(act_text) and any(kw in act_text for kw in insult_kws)):
            state["composure_state"] = "prickly_defensive"
            state["composure_ttl"] = 3
            has_new_trigger = True
        elif _name_in(act_text) and any(kw in act_text for kw in flirt_kws):
            state["composure_state"] = "flustered"
            state["composure_ttl"] = 3
            has_new_trigger = True
        elif _name_in(act_text) and any(kw in act_text for kw in probe_kws):
            state["composure_state"] = "intrigued"
            state["composure_ttl"] = 2
            has_new_trigger = True

        if not has_new_trigger and cur_ttl > 0:
            new_ttl = cur_ttl - 1
            state["composure_ttl"] = new_ttl
            if new_ttl <= 0:
                state["composure_state"] = "composed"

    if session.get("id"):
        try:
            import db
            db.update_session(session["id"], extra={"scene_stage_state": scene_stage_state})
        except Exception:
            pass

    return scene_stage_state


def format_ring2_attentive_peer_cues(stage_npcs: list, active_partners: list = None) -> str:
    """
    Generates a compact prompt directive for Ring 2 peers (attentive in-room peers)
    allowing physical side-reactions or a brief 1-line reactive quip without hijacking the conversation.
    """
    if not stage_npcs:
        return ""

    ring2_peers = [
        n for n in stage_npcs
        if isinstance(n, dict) and n.get("attention_ring") == "ring_2_attentive_peer"
    ]
    if not ring2_peers:
        return ""

    partner_names = ", ".join(active_partners) if active_partners else "the player"
    peer_descriptions = []
    for p in ring2_peers:
        p_name = _get_npc_name(p)
        if not p_name:
            continue
        reason = "attentive companion" if p.get("stage_role") == "party_companion" else "observing from nearby"
        if str(p.get("track", "")).lower() == "romantic" or p.get("relationship_score", 0) >= 50:
            reason = "romantic interest / observant"
        elif p.get("role") in ("Rendezvous Partner", "Quest Target"):
            reason = "relevant to active plans"
        peer_descriptions.append(f"{p_name} ({reason})")

    peers_str = ", ".join(peer_descriptions)
    return (
        f"[RING 2: ATTENTIVE IN-ROOM PEERS ({peers_str})]:\n"
        f"- These characters are present in the room and closely observing the interaction with {partner_names}.\n"
        f"- PHYSICAL & AMBIENT SIDE-REACTIONS: When conversation topics touch their interests, loyalties, or relationships, they may react naturally with subtle body language (e.g. pausing, glancing over, smirking, a brief blush, or shifting posture).\n"
        f"- REACTIVE 1-LINER HOOK: An attentive peer may drop at most a brief 1-line reaction or quip, but MUST NEVER hijack the primary dialogue from {partner_names}.\n"
        f"- `next_choices` may include 1 optional choice to acknowledge or address an attentive peer if they react.\n\n"
    )


def resolve_post_turn_stage_delta(
    session: dict,
    raw_npcs_present: list,
    narrative: str,
    actions: list = None,
    location_changed: bool = False,
    new_loc: str = "",
    contacts: list = None,
    scenario_key: str = "",
    excluded_names: set = None,
    skip_prose_departures: bool = False,
) -> list:
    """
    Resolves the post-turn physical stage roster by applying stateful deltas:
    1. Uses session["pre_turn_stage_npcs"] as the baseline roster when not location_changed.
       If pre_turn_stage_npcs is absent or empty, falls back to raw_npcs_present.
    2. Removes NPCs in excluded_names (e.g. departed, left behind, or remote).
    3. Validates any newly reported NPC in raw_npcs_present not in baseline:
       - Rejects mentions only in absence/memory (is_mentioned_only_in_absence_or_memory)
       - Rejects stationary role-locked NPCs belonging to another room (is_character_mobile == False)
       - Accepts genuine walk-ins or explicitly approached/summoned characters.
    """
    actions = actions or []
    scenario_key = scenario_key or (session.get("scenario", "fantasy") if session else "fantasy")

    import namegen

    # Baseline selection
    # 1. Baseline determination
    pre_turn = session.get("pre_turn_stage_npcs") if session else None
    if not location_changed:
        if pre_turn and isinstance(pre_turn, list) and len(pre_turn) > 0:
            baseline = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in pre_turn]
        else:
            baseline = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (raw_npcs_present or [])]
    else:
        # Location changed: raw_npcs_present represents the arrival stage roster
        baseline = [dict(n) if isinstance(n, dict) else {"name": str(n)} for n in (raw_npcs_present or [])]

    all_stage_peer_names = [
        _get_npc_name(x) for x in list(baseline) + list(raw_npcs_present or []) if _get_npc_name(x)
    ]

    # Normalize excluded names (e.g. left behind, remote, departed)
    clean_excluded = set()
    for ex in (excluded_names or set()):
        if ex:
            ex_s = str(ex).strip().lower()
            if ex_s:
                clean_excluded.add(ex_s)
                if " " in ex_s:
                    clean_excluded |= namegen.get_unique_person_tokens(ex_s, peer_names=all_stage_peer_names)

    # Collect nearby enemies to prevent hostile enemies from being staged as social bystanders
    enemy_names = set()
    if session and session.get("nearby_enemies"):
        for e in session["nearby_enemies"]:
            en = (_get_npc_name(e) if isinstance(e, dict) else (e if isinstance(e, str) else "")).strip().lower()
            if en:
                enemy_names.add(en)
                enemy_names |= namegen.get_unique_person_tokens(en, peer_names=all_stage_peer_names)

    # Collect player character names to prevent players being treated as staged NPCs
    player_names = set()
    if session and session.get("turn_order"):
        for uid in session["turn_order"]:
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            pn = str(cr["name"]).strip().lower()
                            player_names.add(pn)
                            p_given = namegen.get_given_name(cr["name"]).strip().lower()
                            if len(p_given) >= 3 and p_given not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                                player_names.add(p_given)
            except Exception:
                pass

    from game_engine.npcs.presence import is_mentioned_only_in_absence_or_memory
    from game_engine.npcs.dialogue_tracking import is_npc_invited_in_action
    from mechanics.world.mobility import (
        is_character_mobile,
        has_active_physical_presence,
        is_dialogue_partner,
        is_rendezvous_target,
    )

    # 2. Structured Departures (dismisses_npc action tag; cast_events departures applied by CastPlanner)
    from game_engine.matching import matches_keyword_boundary
    departed_names = set()
    raw_present_low = {_get_npc_name(rn).strip().lower() for rn in (raw_npcs_present or []) if _get_npc_name(rn)}
    for a_dep in (actions or []):
        if isinstance(a_dep, dict):
            raw_d_val = a_dep.get("dismisses_npc")
            d_nm = ""
            if isinstance(raw_d_val, str) and raw_d_val.strip() and raw_d_val.strip().lower() not in ("true", "false", "0", "1"):
                d_nm = raw_d_val.strip().lower()
            elif raw_d_val and a_dep.get("target_npc"):
                d_nm = str(a_dep["target_npc"]).strip().lower()
            else:
                a_lbl_low = str(a_dep.get("label") or "").strip().lower()
                if a_lbl_low and any(kw in a_lbl_low for kw in ("goodbye", "farewell", "head home", "go home", "dismiss", "send away")):
                    for b_n in baseline:
                        b_nm = _get_npc_name(b_n).strip().lower()
                        b_toks = namegen.get_unique_person_tokens(b_nm, peer_names=baseline)
                        if b_nm and b_nm not in raw_present_low and any(
                            matches_keyword_boundary(a_lbl_low, tok) for tok in b_toks if len(tok) >= 2
                        ):
                            d_nm = b_nm
                            break
            if d_nm:
                departed_names.add(d_nm)
                departed_names |= namegen.get_unique_person_tokens(d_nm, peer_names=all_stage_peer_names)

    # Retain non-departed baseline NPCs
    retained_stage = []
    retained_names_lower = set()
    retained_token_owner: dict[str, dict] = {}
    for n in baseline:
        n_name = _get_npc_name(n)
        if not n_name:
            continue
        n_low = n_name.strip().lower()
        if n_low in player_names:
            continue
        n_toks = namegen.get_unique_person_tokens(n_name, peer_names=all_stage_peer_names)
        if n_low in departed_names or bool(n_toks & departed_names):
            continue
        if n_low in enemy_names or bool(n_toks & enemy_names):
            continue
        if n_low in clean_excluded or bool(n_toks & clean_excluded):
            continue
        retained_stage.append(n)
        retained_names_lower.add(n_low)
        for tok in n_toks:
            retained_names_lower.add(tok)
            retained_token_owner.setdefault(tok, n)

    # 3. Inspect newcomers in raw_npcs_present (for walk-ins when not location_changed)
    if contacts is None and session and session.get("id"):
        try:
            contacts = db.get_contacts(session["id"])
        except Exception:
            contacts = []
    contacts = contacts or []
    contacts_map = {str(c.get("name", "")).strip().lower(): c for c in contacts if isinstance(c, dict) and c.get("name")}

    for cand in (raw_npcs_present or []):
        cand_name = _get_npc_name(cand)
        if not cand_name:
            continue
        c_low = cand_name.strip().lower()
        if c_low in player_names:
            continue
        c_toks = namegen.get_unique_person_tokens(cand_name, peer_names=all_stage_peer_names)
        if c_low in enemy_names or bool(c_toks & enemy_names):
            continue
        if c_low in clean_excluded or bool(c_toks & clean_excluded):
            continue

        # If already retained in stage, merge attributes if cand has extra info
        matched_retained_toks = ({c_low} | c_toks) & retained_names_lower
        if matched_retained_toks:
            existing = retained_token_owner.get(c_low)
            if existing is None:
                for m_tok in matched_retained_toks:
                    if m_tok in retained_token_owner:
                        existing = retained_token_owner[m_tok]
                        break
            if existing and isinstance(existing, dict) and isinstance(cand, dict):
                for k, v in cand.items():
                    if v not in (None, "", [], {}) and existing.get(k) in (None, "", [], {}):
                        existing[k] = v
            continue

        # If departed this turn, do not re-add
        if c_low in departed_names or bool(c_toks & departed_names):
            continue

        # Check absence/memory
        if narrative and is_mentioned_only_in_absence_or_memory(cand_name, narrative):
            continue

        # Check mobility & role locks
        matched_contact = contacts_map.get(c_low)
        if not matched_contact and c_toks:
            contact_keys_list = list(contacts_map.keys())
            c_matches = [
                c for k, c in contacts_map.items()
                if c_toks & namegen.get_unique_person_tokens(k, peer_names=contact_keys_list, min_len=2)
            ]
            if len(c_matches) == 1:
                matched_contact = c_matches[0]

        if matched_contact:
            if not is_character_mobile(cand_name, matched_contact, scen_key=scenario_key):
                c_loc = matched_contact.get("location") or (matched_contact.get("basic_info") or {}).get("location") or ""
                if c_loc and new_loc and c_loc.lower().strip() != new_loc.lower().strip():
                    continue

        eff_ts = (session.get("time_slot") or get_time_block_key(int(session.get("current_minute", 480) or 480))) if session else "morning"
        cand_dict = dict(cand) if isinstance(cand, dict) else {"name": cand_name}
        cand_dict["name"] = cand_name
        merged_cand = dict(matched_contact) if matched_contact else dict(cand_dict)
        for k, v in cand_dict.items():
            merged_cand[k] = v
        if "micro_blocking" not in cand_dict:
            cand_dict["micro_blocking"] = derive_initial_micro_blocking(
                npc=merged_cand,
                current_location=new_loc or (session.get("current_location", "") if session else ""),
                time_slot=eff_ts,
                stage_role=cand_dict.get("stage_role", "room_bystander"),
            )
        retained_stage.append(cand_dict)
        retained_names_lower.add(c_low)
        for tok in c_toks:
            retained_names_lower.add(tok)
            retained_token_owner.setdefault(tok, cand_dict)

    # 4. Ensure all retained NPCs have micro_blocking initialized
    for n in retained_stage:
        if isinstance(n, dict) and "micro_blocking" not in n:
            n_name = _get_npc_name(n)
            n_low = n_name.lower().strip()
            matched_contact = contacts_map.get(n_low)
            merged_n = dict(matched_contact) if matched_contact else dict(n)
            for k, v in n.items():
                merged_n[k] = v
            eff_ts = (session.get("time_slot") or get_time_block_key(int(session.get("current_minute", 480) or 480))) if session else "morning"
            n["micro_blocking"] = derive_initial_micro_blocking(
                npc=merged_n,
                current_location=new_loc or (session.get("current_location", "") if session else ""),
                time_slot=eff_ts,
                stage_role=n.get("stage_role", "room_bystander"),
            )

    # Update session pre_turn_stage_npcs so subsequent operations/turns have fresh state
    if session is not None and isinstance(session, dict):
        session["pre_turn_stage_npcs"] = retained_stage

    return retained_stage

