from __future__ import annotations
from typing import Any
import json
import re
import random
import game_engine
from game_engine.core import *
from game_engine.core import _get_npc_name, _norm_dialogue_name

from .dialogue_tracking import (
    DIALOGUE_STALL_VERBS,
    count_dialogue_stall_turns,
    format_dialogue_stall_directive,
    build_scene_escalation_and_consequence_directives,
    get_session_dialogue_partners,
    is_dialogue_partner,
    is_npc_invited_in_action,
)
from .presence import (
    sync_hostile_entities,
    classify_scene_npcs,
    is_mentioned_only_in_absence_or_memory,
    reset_departed_guest_locations,
    _distribute_fallback_locations,
)


def _build_canonical_name_resolver(
    session: dict | None,
    old_npcs: list,
    candidates: list,
    known_contacts: list,
) -> tuple[dict[str, str], dict[str, str]]:
    """
    Builds mappings to canonicalize single-token/partial NPC names into their canonical full names.
    Returns (first_name_to_canonical, full_name_canonical_case).
    """
    first_to_canon: dict[str, str] = {}
    full_canon_case: dict[str, str] = {}
    full_names: set[str] = set()

    def _register_full_name(raw: any):
        if not raw or not isinstance(raw, str):
            return
        name_clean = raw.strip()
        parts = name_clean.split()
        if len(parts) >= 2:
            full_names.add(name_clean)
            full_canon_case[name_clean.lower()] = name_clean

    # 1. Collect from known contacts
    for c in (known_contacts or []):
        if isinstance(c, dict):
            _register_full_name(c.get("name"))

    # 2. Collect from school roster
    if session and session.get("id"):
        try:
            roster = db.get_school_roster(session["id"])
            for m in (roster or []):
                if isinstance(m, dict):
                    _register_full_name(m.get("name"))
        except Exception:
            pass

    # 3. Collect from old_npcs
    for on in (old_npcs or []):
        nm = game_engine._get_npc_name(on) if on else ""
        _register_full_name(nm)

    # 4. Collect from candidates
    for cand in (candidates or []):
        nm = cand.get("name") if isinstance(cand, dict) else (cand if isinstance(cand, str) else "")
        _register_full_name(nm)

    # Map given names, surnames, and formal titles to unique full names (excluding standalone honorifics/particles)
    import namegen
    first_groups: dict[str, list[str]] = {}
    for fn in full_names:
        fn_low = fn.strip().lower()
        given_first, surname_str = namegen.extract_first_and_last_name(fn)
        cand_toks = set(namegen.get_unique_person_tokens(fn, min_len=2)) - {fn_low}
        for extra in (given_first.strip().lower(), surname_str.strip().lower()):
            extra_c = extra.strip(".,'\"()[]{}")
            if extra_c and extra_c not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                cand_toks.add(extra_c)
        for tok in cand_toks:
            tok_clean = tok.strip()
            if tok_clean and tok_clean.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                grp = first_groups.setdefault(tok_clean, [])
                if fn not in grp:
                    grp.append(fn)

    for first, group in first_groups.items():
        if len(group) == 1:
            first_to_canon[first] = group[0]
        else:
            contact_names = {c.get("name", "").strip().lower() for c in (known_contacts or []) if isinstance(c, dict)}
            old_names = {game_engine._get_npc_name(on).strip().lower() for on in (old_npcs or []) if on}
            preferred = [g for g in group if g.lower() in contact_names or g.lower() in old_names]
            if len(preferred) == 1:
                first_to_canon[first] = preferred[0]

    return first_to_canon, full_canon_case


def process_scene_npcs(result: dict, session: dict, new_loc: str, old_loc: str, actions: list = None, staged_npcs: list = None, party: list = None) -> list[dict]:

    """

    Manages the lifecycle of NPCs present in the scene:

    1. Removes out-of-zone hallucinated NPCs while exempting rendezvous targets and active mobile campus peers.

    2. Strictly excludes active enemies (nearby_enemies) and hostile new_entities from npcs_present.

    3. Handles zone/room transition persistence for companions and grounds ambient patrons.

    4. Supports natural narrative guest departures via npc_departures and narrative prose analysis.

    5. Synchronizes canonical contact locations upon arrival.

    """

    dest_zone = get_zone_location_name(new_loc)

    scen_key = session.get("scenario", "fantasy") if session else "fantasy"

    sess_id = session.get("id") if session else None



    from mechanics.world.mobility import (

        is_campus_co_located,

        is_character_mobile,

        is_rendezvous_target,

        has_active_physical_presence,

        has_narrative_continuity_bridge,

        is_dialogue_partner,

        is_social_third_place,

        sync_contact_locations

    )



    # Collect human player names (all active and inactive characters owned by session members) to strictly exclude from current_npcs
    import namegen
    player_names = set()

    def _add_player_name(raw_pn: Any) -> None:
        if not raw_pn:
            return
        pn_str = str(raw_pn).strip()
        pn_low = pn_str.lower()
        if not pn_low:
            return
        player_names.add(pn_low)
        p_given = namegen.get_given_name(pn_str).strip().lower()
        if len(p_given) >= 3 and p_given not in namegen.NAME_PARTICLES_AND_HONORIFICS:
            player_names.add(p_given)

    if party:
        for p_elem in party:
            p_char = p_elem[0] if isinstance(p_elem, (list, tuple)) and p_elem else p_elem
            if isinstance(p_char, dict) and p_char.get("name"):
                _add_player_name(p_char["name"])

    if actions:
        for a in actions:
            if isinstance(a, dict):
                c_data = a.get("char")
                if isinstance(c_data, dict) and c_data.get("name"):
                    _add_player_name(c_data["name"])

    if session:
        for k in ("player_name", "character_name", "char_name"):
            if session.get(k):
                _add_player_name(session[k])
        if session.get("party") and isinstance(session["party"], list):
            for p_elem in session["party"]:
                p_char = p_elem[0] if isinstance(p_elem, (list, tuple)) and p_elem else p_elem
                if isinstance(p_char, dict) and p_char.get("name"):
                    _add_player_name(p_char["name"])
        if session.get("turn_order"):
            for uid in session["turn_order"]:
                try:
                    with db.get_conn() as conn:
                        c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()
                        for cr in c_rows:
                            if cr["name"]:
                                _add_player_name(cr["name"])
                except Exception:
                    pass
        if session.get("id"):
            try:
                with db.get_conn() as conn:
                    c_rows = conn.execute("SELECT name FROM characters WHERE session_id = ?", (session["id"],)).fetchall()
                    for cr in c_rows:
                        if cr["name"]:
                            _add_player_name(cr["name"])
            except Exception:
                pass



    # Load formal party NPC names (permanent party companions who are protected from guest departure)

    formal_party_names = set()
    for comp_list_key in ("party_npcs", "temporary_companions"):
        for comp in (session.get(comp_list_key) or []):
            p_name = (comp.get("name") if isinstance(comp, dict) else str(comp)).strip().lower()
            if p_name:
                formal_party_names.add(p_name)

    if session.get("id"):

        try:

            for p in (db.get_session_party_npcs(session["id"]) or []) + (db.get_temporary_companions(session["id"]) or []):

                p_name = str(p.get("name", "") if isinstance(p, dict) else p).strip().lower()

                if p_name:

                    formal_party_names.add(p_name)

        except Exception:

            pass



    old_npcs = list(session.get("current_npcs") or [])

    known_contacts = db.get_contacts(session["id"]) if session.get("id") else []



    # Consolidate affirmative departures from:

    # 1. LLM npc_departures field

    # 2. entity_audit.departed_characters

    # 3. Narrative & action extraction (e.g. "watches Sofia depart", "Sofia leaves", dismissal action)

    full_narr = (

        str(result.get("outcome_narrative", "")) + " " +

        str(result.get("next_narrative", "")) + " " +

        str(result.get("narrative", "")) + " " +

        str(result.get("scene_text", ""))

    )

    llm_departures = result.get("npc_departures") or []

    if isinstance(llm_departures, str):

        llm_departures = [llm_departures]



    audit_departures = (result.get("entity_audit") or {}).get("departed_characters") or []

    if isinstance(audit_departures, str):

        audit_departures = [audit_departures]

    cast_ev_departures = [
        str(ev.get("npc") or ev.get("name") or "").strip()
        for ev in (result.get("cast_events") or [])
        if isinstance(ev, dict) and str(ev.get("type") or "").lower() == "depart"
    ]
    action_departures = []
    for a in (actions or []):
        if isinstance(a, dict):
            d_val = a.get("dismisses_npc")
            if isinstance(d_val, str) and d_val.strip() and d_val.strip().lower() not in ("true", "false", "0", "1"):
                action_departures.append(d_val.strip())
            elif d_val and a.get("target_npc"):
                action_departures.append(str(a["target_npc"]).strip())
            else:
                a_lbl = str(a.get("label") or "").strip()
                a_lbl_low = a_lbl.lower()
                if a_lbl_low and any(
                    kw in a_lbl_low
                    for kw in ("head home", "go home", "send away", "dismiss", "ask ", "tell ")
                ) and any(
                    kw in a_lbl_low
                    for kw in ("head home", "go home", "leave", "send away", "dismiss", "head out", "depart")
                ):
                    for on in old_npcs:
                        on_nm = game_engine._get_npc_name(on).strip()
                        on_low = on_nm.lower()
                        on_first = (on_low.split() or [""])[0]
                        if on_nm and (
                            matches_keyword_boundary(a_lbl_low, on_low)
                            or (len(on_first) >= 3 and matches_keyword_boundary(a_lbl_low, on_first))
                        ):
                            action_departures.append(on_nm)

    validated_departures = [d for d in (cast_ev_departures + action_departures) if d]
    from mechanics.world.mobility import has_active_physical_presence
    for raw_d in list(llm_departures) + list(audit_departures):
        d_cand_name = str(raw_d.get("name") if isinstance(raw_d, dict) else (raw_d or "")).strip()
        d_cand_low = d_cand_name.lower()
        if not d_cand_low or d_cand_low in player_names or d_cand_low in formal_party_names:
            continue
        is_active = has_active_physical_presence(d_cand_name, result, narrative_text=full_narr, ignore_departures=True)
        if not is_active and len(d_cand_low.split()) > 1:
            for cand_var in (d_cand_low.split()[-1], " ".join(d_cand_low.split()[1:])):
                if len(cand_var) >= 3 and has_active_physical_presence(cand_var, result, narrative_text=full_narr, ignore_departures=True):
                    is_active = True
                    break
        if is_active:
            continue
        validated_departures.append(d_cand_name)

    raw_res_npcs = result.get("npcs_present") or []
    if isinstance(raw_res_npcs, str):
        raw_res_npcs = [{"name": raw_res_npcs}]
    scene_peer_pool = list(old_npcs or []) + list(raw_res_npcs) + list(staged_npcs or []) + list(known_contacts or [])

    departure_names = set()
    for d in validated_departures:
        if isinstance(d, dict):
            d_nm = str(d.get("name") or "").strip().lower()
        else:
            d_nm = str(d or "").strip().lower()
        if d_nm and d_nm not in player_names and d_nm not in formal_party_names:
            departure_names.add(d_nm)
            departure_names |= namegen.get_unique_person_tokens(d_nm, peer_names=scene_peer_pool)

    # Identify active rendezvous appointment targets at this location
    appointment_targets = set()
    if sess_id:
        try:
            from mechanics.system.commitments_engine import (
                get_active_rendezvous_at_node,
                get_active_commitments,
                fulfill_commitment,
                _canon_key,
            )
            curr_node = session.get("current_node_id") if session else ""
            s_day = session.get("current_day") if session else None
            s_min = session.get("current_minute") if session else None

            appts_here = []
            seen_cids = set()
            if curr_node:
                for r in get_active_rendezvous_at_node(sess_id, curr_node, current_day=s_day, current_minute=s_min):
                    if r.get("id") not in seen_cids:
                        seen_cids.add(r.get("id"))
                        appts_here.append(r)
            if new_loc:
                for r in get_active_rendezvous_at_node(sess_id, new_loc, current_day=s_day, current_minute=s_min):
                    if r.get("id") not in seen_cids:
                        seen_cids.add(r.get("id"))
                        appts_here.append(r)

            contact_name_by_key = {}
            for kc in known_contacts:
                kc_nm = str(kc.get("name") or "").strip()
                if kc_nm:
                    for kk in (kc.get("npc_id"), kc_nm, _canon_key(kc_nm)):
                        if kk:
                            contact_name_by_key[str(kk).strip().lower()] = kc_nm

            for appt in appts_here:
                p_names = []
                for p in (appt.get("participants") or []):
                    pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
                    if pk.lower() == "player":
                        continue
                    p_nm = contact_name_by_key.get(pk.lower()) or str(p.get("name") or pk.replace("_", " ")).strip()
                    if p_nm:
                        p_names.append(p_nm)
                if not p_names:
                    tgt = str(appt.get("target_entity") or "").strip()
                    if tgt and tgt.lower() not in ("player", "group"):
                        p_names.append(contact_name_by_key.get(tgt.lower()) or tgt.replace("_", " "))
                for p_nm in p_names:
                    a_name = p_nm.strip().lower()
                    if a_name:
                        appointment_targets.add(a_name)
                        appointment_targets |= namegen.get_unique_person_tokens(p_nm, peer_names=scene_peer_pool)
        except Exception:
            pass

    # When the player is in an active private appointment/rendezvous:
    # Any old patrons who are not part of the appointment, formal party, or explicitly invited
    # are treated as departed to maintain privacy and prevent companion bleed.
    if appointment_targets:
        for on in old_npcs:
            on_name = game_engine._get_npc_name(on).strip().lower()
            on_toks = namegen.get_unique_person_tokens(on_name, peer_names=scene_peer_pool) if on_name else set()
            if on_name and not ({on_name} | on_toks) & appointment_targets and on_name not in formal_party_names:
                if not is_npc_invited_in_action(on_name, actions):
                    departure_names.add(on_name)
                    departure_names |= on_toks

    # Mark departing NPCs' rendezvous commitments as fulfilled
    if sess_id and departure_names:
        try:
            from mechanics.system.commitments_engine import get_active_commitments, fulfill_commitment, _canon_key
            dep_canon = {_canon_key(d) for d in departure_names if d}
            active_appts = get_active_commitments(sess_id, commitment_type="rendezvous", limit=20)
            for appt in active_appts:
                if appt.get("status") not in ("arrived", "in_progress", "pending", "approaching"):
                    continue
                matched_dep = False
                tgt = str(appt.get("target_entity") or "").strip().lower()
                if tgt and (tgt in departure_names or tgt in dep_canon or tgt.replace("_", " ") in departure_names):
                    matched_dep = True
                for p in (appt.get("participants") or []):
                    pk = str(p.get("person_key") or p.get("npc_id") or "").strip().lower()
                    pn = str(p.get("name") or "").strip().lower()
                    if pk == "player":
                        continue
                    pn_toks = namegen.get_unique_person_tokens(pn, peer_names=scene_peer_pool) if pn else set()
                    if (pk and (pk in departure_names or pk in dep_canon)) or (pn and (pn in departure_names or bool(pn_toks & departure_names))):
                        matched_dep = True
                        break
                if matched_dep and appt.get("id"):
                    fulfill_commitment(sess_id, appt["id"], notes="NPC departed after rendezvous")
        except Exception:
            pass

    remote_npc_names = set()
    for c in known_contacts:
        c_name = str(c.get("name") or c.get("npc_id") or "").lower().strip()
        c_loc = c.get("location") or (c.get("basic_info") or {}).get("location") or ""
        if c_loc and c_name:
            c_zone = get_zone_location_name(c_loc)
            if c_zone and dest_zone and c_zone.lower() != dest_zone.lower():
                # 0. Formal party member or explicitly invited in player action
                c_toks = namegen.get_unique_person_tokens(c_name, peer_names=scene_peer_pool)
                if c_name in formal_party_names or bool(c_toks & formal_party_names):
                    continue
                if is_character_mobile(c_name, c, scen_key):
                    if is_npc_invited_in_action(c_name, actions) or any(is_npc_invited_in_action(t, actions) for t in c_toks):
                        continue
                # 1. Is this NPC the intended target of travel or an active quest waypoint / appointment?
                if is_rendezvous_target(c_name, actions=actions, session_id=sess_id, new_loc=new_loc):
                    continue
                # 2. Campus Quad Mobility for Mobile Characters
                if is_character_mobile(c_name, c, scen_key):
                    has_bridge = is_campus_co_located(c_zone, dest_zone, scen_key) or has_narrative_continuity_bridge(c_name, session=session, actions=actions, new_loc=new_loc)
                    if has_bridge and has_active_physical_presence(c_name, result, full_narr):
                        continue
                remote_npc_names.add(c_name)

    new_npcs = list(result.get("npcs_present") or [])
    if isinstance(new_npcs, str):
        new_npcs = [{"name": new_npcs}]

    # Stage NPCs (patrol NPC from access gate, room bystanders from schedules, etc.)
    staged_names = set()
    if staged_npcs:
        for sn in staged_npcs:
            if isinstance(sn, dict) and sn.get("name"):
                s_name = game_engine._get_npc_name(sn).strip()
                s_low = s_name.lower()
                staged_names.add(s_low)
                staged_names |= namegen.get_unique_person_tokens(s_name, peer_names=scene_peer_pool)
                if not any(game_engine._get_npc_name(np).strip().lower() == s_low for np in new_npcs):
                    new_npcs.append(dict(sn))

    # In a private appointment/rendezvous, filter out hallucinated/ambient entities from initial new_npcs
    if appointment_targets:
        filtered_initial = []
        for np in new_npcs:
            np_name = game_engine._get_npc_name(np).strip().lower()
            np_toks = namegen.get_unique_person_tokens(np_name, peer_names=scene_peer_pool) if np_name else set()
            if (np_name in appointment_targets or bool(np_toks & appointment_targets) or
                np_name in formal_party_names or is_npc_invited_in_action(np_name, actions)):
                filtered_initial.append(np)
            else:
                departure_names.add(np_name)
                departure_names |= np_toks
        new_npcs = filtered_initial

    # 1. Incorporate entity_audit present/speaking characters if provided by model
    entity_audit = result.get("entity_audit") or {}
    if isinstance(entity_audit, dict):
        audit_present = entity_audit.get("present_named_characters") or []
        if isinstance(audit_present, list):
            for a_name in audit_present:
                if isinstance(a_name, str) and a_name.strip():
                    a_clean = a_name.strip().lower()
                    a_toks = namegen.get_unique_person_tokens(a_name, peer_names=scene_peer_pool)
                    if appointment_targets and not ({a_clean} | a_toks) & appointment_targets and a_clean not in formal_party_names and not is_npc_invited_in_action(a_name, actions):
                        continue
                    if a_clean not in player_names and a_clean not in departure_names and not bool(a_toks & departure_names):
                        new_npcs.append({"name": a_name.strip()})

        audit_speaking = entity_audit.get("speaking_characters") or []
        if isinstance(audit_speaking, list):
            for a_name in audit_speaking:
                if isinstance(a_name, str) and a_name.strip():
                    a_clean = a_name.strip().lower()
                    a_toks = namegen.get_unique_person_tokens(a_name, peer_names=scene_peer_pool)
                    if appointment_targets and not ({a_clean} | a_toks) & appointment_targets and a_clean not in formal_party_names and not is_npc_invited_in_action(a_name, actions):
                        continue
                    if a_clean not in player_names and a_clean not in departure_names and not bool(a_toks & departure_names):
                        new_npcs.append({"name": a_name.strip()})

    # 1b. Incorporate actor_poses present in scene
    actor_poses = result.get("actor_poses") or {}
    if isinstance(actor_poses, dict):
        for raw_act in actor_poses.keys():
            act_name = str(raw_act or "").strip()
            if not act_name:
                continue
            act_clean = act_name.lower()
            act_toks = namegen.get_unique_person_tokens(act_name, peer_names=scene_peer_pool)
            if act_clean in player_names or act_clean in departure_names or bool(act_toks & departure_names):
                continue
            if appointment_targets and not ({act_clean} | act_toks) & appointment_targets and act_clean not in formal_party_names and not is_npc_invited_in_action(act_name, actions):
                continue
            already = False
            for existing in new_npcs:
                e_nm = game_engine._get_npc_name(existing).strip().lower()
                if e_nm == act_clean or (len(act_clean) > 3 and act_clean in e_nm) or (len(e_nm) > 3 and e_nm in act_clean):
                    already = True
                    break
            if already:
                continue

            matched_c = None
            if sess_id:
                try:
                    roster = db.get_school_roster(sess_id) or []
                    contacts = db.get_contacts(sess_id) or []
                    for cand in contacts + roster:
                        c_nm = str(cand.get("name") or "").strip().lower()
                        c_role = str(cand.get("role") or (cand.get("basic_info") or {}).get("role") or "").lower()
                        c_club = str(cand.get("club") or (cand.get("basic_info") or {}).get("club") or "").lower()
                        if c_nm and (c_nm == act_clean or c_nm in act_clean or act_clean in c_nm):
                            matched_c = cand
                            break
                        clean_toks = set(re.findall(r'[a-z]{3,}', act_clean)) - {"the", "and", "unnamed", "representative", "student"}
                        if clean_toks and any(t in c_role or t in c_club for t in clean_toks if t not in ("rep", "club")):
                            matched_c = cand
                            break
                except Exception:
                    matched_c = None

            if matched_c:
                mc_name_low = str(matched_c.get("name") or "").strip().lower()
                mc_loc = str(
                    matched_c.get("location")
                    or (matched_c.get("basic_info") or {}).get("location")
                    or matched_c.get("primary_facility")
                    or ""
                ).strip().lower()
                was_old = any(game_engine._get_npc_name(on).strip().lower() == mc_name_low for on in old_npcs)
                is_loc_match = bool(mc_loc and new_loc and (mc_loc == new_loc.lower() or new_loc.lower() in mc_loc or mc_loc in new_loc.lower()))
                if not (was_old or mc_name_low in staged_names or mc_name_low in formal_party_names or mc_name_low in appointment_targets or is_loc_match):
                    continue
                new_npcs.append({
                    "name": matched_c["name"],
                    "role": matched_c.get("role") or (matched_c.get("basic_info") or {}).get("role") or "",
                    "grade": matched_c.get("grade", ""),
                    "club": matched_c.get("club", ""),
                    "clique": matched_c.get("clique", ""),
                    "race": matched_c.get("race", ""),
                    "gender": matched_c.get("gender", ""),
                    "status_effects": ["Present"],
                })
            else:
                import namegen
                if not namegen.is_collective_entity_name(act_name):
                    try:
                        from game_engine.npcs.stage_manager import _spawn_canonical_role_npc_pre_turn
                        sp_npc = _spawn_canonical_role_npc_pre_turn(session, act_name, new_loc)
                        if sp_npc and sp_npc.get("name"):
                            new_npcs.append(sp_npc)
                    except Exception:
                        new_npcs.append({"name": act_name, "status_effects": ["Present"]})

    active_enemies = game_engine.get_active_enemies(result) or game_engine.get_active_enemies(session)

    enemy_names = {

        game_engine._get_npc_name(e).lower()

        for e in active_enemies if e

    }



    _NPC_METADATA_KEYS = (

        "name", "role", "occupation", "description", "disposition",

        "faction", "club", "club_role", "grade", "clique", "location",

        "race", "gender", "age", "traits", "preferences",

        "mannerisms", "motivation", "appearance"

    )

    new_entity_npcs = []

    for e in (result.get("new_entities") or []):

        if (

            isinstance(e, dict)

            and str(e.get("type") or "person").lower() in ("person", "npc")

            and e.get("name")

            and str(e.get("disposition", "")).lower() != "hostile"

            and str(e.get("type", "")).lower() not in ("enemy", "monster", "hostile", "creature", "boss")

            and str(e.get("name", "")).strip().lower() not in enemy_names

            and str(e.get("name", "")).strip().lower() not in player_names

            and str(e.get("name", "")).strip().lower() not in departure_names

        ):

            ent_npc = {}

            for k in _NPC_METADATA_KEYS:

                val = e.get(k)

                if val not in (None, "", [], {}):

                    ent_npc[k] = val

            ent_npc.setdefault("description", "")

            ent_npc.setdefault("appearance", "")

            new_entity_npcs.append(ent_npc)



    first_to_canon, full_canon_case = _build_canonical_name_resolver(
        session, old_npcs, (new_npcs + new_entity_npcs), known_contacts
    )

    def _resolve_canonical_name(raw_name: any) -> str:
        if not raw_name or not isinstance(raw_name, str):
            return raw_name or ""
        s = raw_name.strip()
        low = s.lower()
        if low in full_canon_case:
            return full_canon_case[low]
        parts = s.split()
        if len(parts) == 1 and low in first_to_canon:
            return first_to_canon[low]
        return s

    seen_names: dict[str, dict] = {}

    combined_new_npcs = []

    old_npc_names = {
        game_engine._get_npc_name(on).strip().lower()
        for on in (old_npcs or [])
        if game_engine._get_npc_name(on)
    }

    for n in (new_npcs + new_entity_npcs):

        if isinstance(n, dict):

            raw_name = str(n.get("name") or "").strip()

            canon_name = _resolve_canonical_name(raw_name)

            name_clean = canon_name.strip().lower()

            first_name = (name_clean.split() or [""])[0]

            is_comp = (name_clean in formal_party_names) or bool(n.get("is_permanent_party"))

            if name_clean in player_names or name_clean in departure_names:

                continue

            if not is_comp and (name_clean in remote_npc_names or name_clean in enemy_names):

                continue

            if not name_clean:

                continue

            import namegen
            if not namegen.is_valid_entity_name(name_clean) or namegen.is_collective_entity_name(name_clean):

                continue

            given_name = namegen.extract_first_and_last_name(canon_name)[0].lower().strip()
            first_cands = {fc for fc in (first_name, given_name) if len(fc) >= 3 and fc not in namegen.NAME_PARTICLES_AND_HONORIFICS}

            # Phantom Entity Guard: If this is a newly introduced NPC (not previously present, not in formal party,
            # not an appointment target, not active dialogue partner, and not explicitly invited in actions):
            # Verify they actually appear in the narrative prose (full_narr) or have active physical presence!
            is_target = is_rendezvous_target(name_clean, actions=actions, session_id=sess_id, new_loc=new_loc)
            is_dp = is_dialogue_partner(name_clean, session=session)
            was_already_present = name_clean in old_npc_names or bool(first_cands & old_npc_names)
            is_invited = is_npc_invited_in_action(name_clean, actions or [])
            is_staged = name_clean in staged_names or bool(first_cands & staged_names)

            if full_narr and len(full_narr) >= 15 and not was_already_present and not is_comp and not is_target and not is_dp and not is_invited and not is_staged:
                narr_check = full_narr.lower()
                in_prose = (
                    name_clean in narr_check
                    or any(f" {fc} " in f" {narr_check} " or f" {fc}" in f" {narr_check} " or f"—{fc}" in narr_check or f"-{fc}" in narr_check for fc in first_cands)
                )
                if not in_prose and not has_active_physical_presence(name_clean, result, narrative_text=full_narr):
                    continue

            if name_clean not in seen_names:

                n_copy = dict(n)

                n_copy["name"] = canon_name

                seen_names[name_clean] = n_copy

                combined_new_npcs.append(n_copy)

            else:

                existing_n = seen_names[name_clean]

                for k, v in n.items():

                    if v not in (None, "", [], {}) and existing_n.get(k) in (None, "", [], {}):

                        existing_n[k] = v

        elif isinstance(n, str) and n.strip():

            raw_name = n.strip()

            canon_name = _resolve_canonical_name(raw_name)

            name_clean = canon_name.strip().lower()

            first_name = (name_clean.split() or [""])[0]

            if name_clean in player_names or name_clean in departure_names or name_clean in remote_npc_names or name_clean in enemy_names:

                continue

            import namegen
            if not namegen.is_valid_entity_name(name_clean) or namegen.is_collective_entity_name(name_clean):

                continue

            given_name = namegen.extract_first_and_last_name(canon_name)[0].lower().strip()
            first_cands = {fc for fc in (first_name, given_name) if len(fc) >= 3 and fc not in namegen.NAME_PARTICLES_AND_HONORIFICS}

            is_comp = (name_clean in formal_party_names)
            is_target = is_rendezvous_target(name_clean, actions=actions, session_id=sess_id, new_loc=new_loc)
            is_dp = is_dialogue_partner(name_clean, session=session)
            was_already_present = name_clean in old_npc_names or bool(first_cands & old_npc_names)
            is_invited = is_npc_invited_in_action(name_clean, actions or [])
            is_staged = name_clean in staged_names or bool(first_cands & staged_names)

            if full_narr and len(full_narr) >= 15 and not was_already_present and not is_comp and not is_target and not is_dp and not is_invited and not is_staged:
                narr_check = full_narr.lower()
                in_prose = (
                    name_clean in narr_check
                    or any(f" {fc} " in f" {narr_check} " or f" {fc}" in f" {narr_check} " or f"—{fc}" in narr_check or f"-{fc}" in narr_check for fc in first_cands)
                )
                if not in_prose and not has_active_physical_presence(name_clean, result, narrative_text=full_narr):
                    continue

            if name_clean and name_clean not in seen_names:

                n_copy = {"name": canon_name}

                seen_names[name_clean] = n_copy

                combined_new_npcs.append(n_copy)



    left_behind_names = set()

    if new_loc != old_loc:
        # Complete or abandon any phone appointments / rendezvous that were 'arrived' at old_loc when moving away
        if sess_id:
            try:
                from mechanics.world.waypoints import check_location_matches_waypoint
                from mechanics.system.commitments_engine import get_active_commitments, abandon_rendezvous, fulfill_commitment
                narr_text = f"{result.get('outcome_narrative', '')} {result.get('next_narrative', '')}".lower()
                action_text = " ".join(str(a.get("label", "")) for a in (actions or []) if isinstance(a, dict)).lower()
                full_dep_text = f"{narr_text} {action_text}"
                farewell_kws = ("bye", "goodbye", "farewell", "see you", "part ways", "walk away together", "excuse", "depart gracefully", "said goodbye", "until next time", "said our goodbyes", "signals her exit", "signals his exit", "take care", "leave the rooftop and head downstairs to class")
                has_farewell = any(kw in full_dep_text for kw in farewell_kws)

                active_rendezvous = get_active_commitments(sess_id, commitment_type="rendezvous", limit=20)
                arrived_appts = [c for c in active_rendezvous if c.get("status") in ("arrived", "in_progress")]

                for appt in arrived_appts:
                    appt_loc = appt.get("target_location") or ""
                    if appt_loc and check_location_matches_waypoint(old_loc, appt_loc) and not check_location_matches_waypoint(new_loc, appt_loc):
                        cid = appt.get("id") or appt.get("commitment_key")
                        if not cid:
                            continue
                        if not has_farewell:
                            abandon_rendezvous(sess_id, cid, reason="walked out mid-meeting")
                        else:
                            fulfill_commitment(sess_id, cid, notes="Departed gracefully after meeting")
            except Exception:
                pass



        old_zone = get_zone_location_name(old_loc)
        new_zone = get_zone_location_name(new_loc)
        old_primary = get_primary_location_name(old_loc)
        new_primary = get_primary_location_name(new_loc)

        old_node_id = (session.get("previous_node_id") if session and session.get("previous_node_id") else None) or (db.resolve_node_id_from_location(sess_id, old_loc) if sess_id and old_loc else None) or (session.get("current_node_id") if session else None)
        new_node_id = (db.resolve_node_id_from_location(sess_id, new_loc) if sess_id and new_loc else None) or result.get("current_node_id")
        graph_same_venue = False
        if sess_id and old_node_id and new_node_id and not (old_primary and new_primary and old_primary.lower() != new_primary.lower()):
            if old_node_id == new_node_id:
                graph_same_venue = True
            else:
                old_node = db.get_world_node(sess_id, old_node_id)
                new_node = db.get_world_node(sess_id, new_node_id)
                if old_node and new_node:
                    p_id = old_node.get("parent_id")
                    if p_id and p_id == new_node.get("parent_id") and (getattr(db.get_world_node(sess_id, p_id), "get", lambda *a: "")("node_type", "").upper() != "ZONE" if db.get_world_node(sess_id, p_id) else True):
                        graph_same_venue = True
                    elif (db.is_descendant_of(sess_id, new_node_id, old_node_id) or db.is_descendant_of(sess_id, old_node_id, new_node_id)) and old_node.get("node_type", "").upper() != "ZONE" and new_node.get("node_type", "").upper() != "ZONE":
                        graph_same_venue = True

        is_same_venue = graph_same_venue or bool(
            old_primary
            and new_primary
            and old_primary.lower() == new_primary.lower()
            and (
                old_zone.lower() == new_zone.lower()
                or is_campus_co_located(old_zone, new_zone, scen_key)
            )
        )



        newly_recruited = set()

        for r in (result.get("relationship_updates") or []):

            if isinstance(r, dict):

                r_name = str(r.get("npc_name") or r.get("name") or "").lower().strip()

                r_disp = str(r.get("disposition") or "").lower()

                if r_name and (r_disp in ("companion", "ally", "friendly") or r.get("affinity", 0) >= 30):

                    newly_recruited.add(r_name)



        if not is_same_venue and (new_zone != old_zone or new_primary != old_primary):

            traveling_companions, left_behind_patrons = game_engine.classify_scene_npcs(

                session, actions=actions or [], old_primary=old_primary, dest_primary=new_primary,

                result=result, full_narr=full_narr, new_loc=new_loc

            )

            left_behind_names = {str(p.get("name", "")).lower().strip() for p in left_behind_patrons if p.get("name")}



            # Update location for already-known contacts who stayed behind at old_loc (never create brand-new unengaged contacts)

            if session.get("id") and old_loc:

                for p in left_behind_patrons:

                    p_name = str(p.get("name") or "").strip()

                    if not p_name or p_name.lower() == "none":

                        continue

                    p_low = p_name.lower()

                    existing_c = next(

                        (

                            c for c in known_contacts

                            if str(c.get("name", "")).strip().lower() == p_low

                            or str(c.get("npc_id", "")).strip().lower() == p_low.replace(" ", "_")

                        ),

                        None,

                    )

                    if existing_c:

                        basic = dict(existing_c.get("basic_info") or {})

                        if not basic.get("location"):

                            basic["location"] = old_loc

                            db.upsert_contact(

                                session["id"],

                                character_id=existing_c.get("character_id", 0),

                                npc_id=existing_c.get("npc_id") or p_low.replace(" ", "_"),

                                name=existing_c.get("name") or p_name,

                                basic_info=basic,

                                track=existing_c.get("track", "platonic"),

                            )



            carried_old_npcs = list(traveling_companions)



            # Filter left_behind_names out of combined_new_npcs (preventing LLM hallucinated reintroduction of tavern/room patrons)

            dest_narr = (

                str(result.get("next_narrative") or "") + " " +

                str(result.get("narrative") or "") + " " +

                str(result.get("scene_text") or "")

            ).strip()

            filtered_combined_new = []

            for n in combined_new_npcs:

                n_clean = game_engine._get_npc_name(n).lower().strip()
                n_first = (n_clean.split() or [""])[0]

                is_left_behind = (
                    n_clean in left_behind_names
                    or (len(n_first) >= 3 and any(
                        lbn == n_clean or (len(lbn.split()[0]) >= 3 and lbn.split()[0] == n_first)
                        for lbn in left_behind_names
                    ))
                )

                is_staged_dest = n_clean in staged_names or (len(n_first) >= 3 and n_first in staged_names)
                if is_left_behind and n_clean not in newly_recruited and not is_staged_dest:
                    continue

                filtered_combined_new.append(n)

            combined_new_npcs = filtered_combined_new

        else:
            if old_loc and new_loc and old_loc.lower() != new_loc.lower():
                # Sub-location / room transition within the same venue:
                # Do NOT carry over ambient bystanders or uninvited dialogue partners from old_loc.
                # Only carry over party members, invited NPCs, or NPCs with verified continuity/presence.
                dest_narr = (
                    str(result.get("next_narrative") or "") + " " +
                    str(result.get("narrative") or "") + " " +
                    str(result.get("scene_text") or "")
                ).strip()
                carried_old_npcs = []
                for npc in old_npcs:
                    n_nm = game_engine._get_npc_name(npc)
                    if not n_nm or n_nm.lower() in departure_names:
                        continue
                    is_invited = is_npc_invited_in_action(n_nm, actions or [])
                    is_party = any(n_nm.lower() == (p[0].get("name", "").lower() if isinstance(p, (tuple, list)) else "") for p in (session.get("party") or [])) if session else False
                    has_bridge = has_narrative_continuity_bridge(n_nm, session=session, actions=actions, new_loc=new_loc)
                    if is_invited or is_party or (has_bridge and has_active_physical_presence(n_nm, result, dest_narr or full_narr)):
                        carried_old_npcs.append(npc)
            else:
                carried_old_npcs = [
                    npc for npc in old_npcs
                    if game_engine._get_npc_name(npc).lower() not in departure_names
                ]



        # Filter left_behind_names out of next_choices (preventing dialogue choices targeting patrons left behind)

        if left_behind_names and "next_choices" in result and isinstance(result["next_choices"], list):

            effective_left = {lbn for lbn in left_behind_names if lbn not in newly_recruited}

            sanitized_choices = []

            for c in result["next_choices"]:

                lbl = str(c.get("label", "") if isinstance(c, dict) else c).lower()

                is_targeting_left_behind = False

                for lbn in effective_left:

                    first_lbn = lbn.split()[0] if lbn else ""

                    if lbn in lbl or (len(first_lbn) >= 3 and (f" {first_lbn} " in f" {lbl} " or f" {first_lbn}" in f" {lbl}")):

                        is_travel_back = any(tv in lbl for tv in ("return to ", "travel back", "head back", "journey back"))

                        if not is_travel_back:

                            is_targeting_left_behind = True

                            break

                if not is_targeting_left_behind:

                    sanitized_choices.append(c)

            result["next_choices"] = sanitized_choices



        final_npcs = []

        final_by_name: dict[str, dict] = {}

        for n in (carried_old_npcs + combined_new_npcs):

            raw_name = game_engine._get_npc_name(n)

            canon_name = _resolve_canonical_name(raw_name)

            name_clean = canon_name.lower().strip()

            import namegen
            if (
                name_clean
                and name_clean != "none"
                and name_clean not in player_names
                and name_clean not in enemy_names
                and name_clean not in departure_names
                and namegen.is_valid_entity_name(name_clean)
                and not namegen.is_collective_entity_name(name_clean)
            ):
                # Known-NPC Spatial Whitelist Gate:
                # When moving locations, previous-room patrons or known contacts/roster NPCs cannot enter the scene
                # unless explicitly invited, party member/temporary companion, destination staged occupant, or appointment target.
                if old_loc and new_loc and old_loc.lower() != new_loc.lower():
                    carried_old_names = {
                        game_engine._get_npc_name(cn).strip().lower()
                        for cn in carried_old_npcs
                        if game_engine._get_npc_name(cn)
                    }
                    roster_by_name: dict[str, dict] = {}
                    if session.get("id"):
                        try:
                            for r_npc in (db.get_anomalous_agent_roster(session["id"]) or []) + (db.get_school_roster(session["id"]) or []):
                                if isinstance(r_npc, dict) and r_npc.get("name"):
                                    roster_by_name[str(r_npc["name"]).strip().lower()] = r_npc
                        except Exception:
                            pass
                    matched_kc = next(
                        (c for c in known_contacts if str(c.get("name") or c.get("npc_id") or "").strip().lower() == name_clean),
                        None,
                    )
                    matched_roster = roster_by_name.get(name_clean)
                    was_in_old = any(game_engine._get_npc_name(on).strip().lower() == name_clean for on in old_npcs)
                    is_old_or_contact = (
                        was_in_old
                        or matched_kc is not None
                        or matched_roster is not None
                        or name_clean in left_behind_names
                    )
                    if is_old_or_contact:
                        has_mobile_dest_presence = False
                        if not was_in_old and name_clean not in left_behind_names and has_active_physical_presence(canon_name, result, full_narr):
                            npc_rec = matched_kc or matched_roster
                            kc_loc = (
                                str((matched_kc.get("basic_info") or {}).get("location") or matched_kc.get("location") or "")
                                if isinstance(matched_kc, dict)
                                else (
                                    str(matched_roster.get("primary_facility") or matched_roster.get("secondary_facility") or matched_roster.get("location") or "")
                                    if isinstance(matched_roster, dict)
                                    else ""
                                )
                            )
                            from mechanics.world.waypoints import check_location_matches_waypoint
                            is_stationed_here = bool(
                                kc_loc
                                and new_loc
                                and (check_location_matches_waypoint(new_loc, kc_loc) or check_location_matches_waypoint(kc_loc, new_loc))
                            )
                            kc_zone = get_zone_location_name(kc_loc) if kc_loc else ""
                            if is_stationed_here or (
                                is_character_mobile(canon_name, npc_rec, scen_key)
                                and (
                                    (kc_zone and dest_zone and is_campus_co_located(kc_zone, dest_zone, scen_key))
                                    or has_narrative_continuity_bridge(canon_name, session=session, actions=actions, new_loc=new_loc)
                                )
                            ):
                                has_mobile_dest_presence = True

                        is_permitted = (
                            name_clean in carried_old_names
                            or name_clean in formal_party_names
                            or is_npc_invited_in_action(canon_name, actions)
                            or is_rendezvous_target(name_clean, actions=actions, session_id=sess_id, new_loc=new_loc)
                            or name_clean in staged_names
                            or (len(name_clean.split()[0]) >= 3 and name_clean.split()[0] in staged_names)
                            or name_clean in appointment_targets
                            or name_clean in newly_recruited
                            or has_mobile_dest_presence
                        )
                        if not is_permitted:
                            continue

                if name_clean not in final_by_name:

                    n_dict = dict(n) if isinstance(n, dict) else {"name": canon_name}

                    n_dict["name"] = canon_name

                    final_by_name[name_clean] = n_dict

                    final_npcs.append(n_dict)

                elif isinstance(n, dict):

                    ex_n = final_by_name[name_clean]

                    for k, v in n.items():

                        if v not in (None, "", [], {}) and ex_n.get(k) in (None, "", [], {}):

                            ex_n[k] = v

    else:

        retained_old = [

            npc for npc in old_npcs

            if (game_engine._get_npc_name(npc).lower() not in departure_names)

            and ((isinstance(npc, dict) and ((game_engine._get_npc_name(npc).lower() in formal_party_names) or npc.get("is_permanent_party"))) or

                (game_engine._get_npc_name(npc).lower() not in remote_npc_names))

            and game_engine._get_npc_name(npc).lower() not in enemy_names

            and game_engine._get_npc_name(npc).lower() not in player_names

        ]

        final_npcs = []

        final_by_name = {}

        for n in (retained_old + combined_new_npcs):

            raw_name = game_engine._get_npc_name(n)

            canon_name = _resolve_canonical_name(raw_name)

            name_clean = canon_name.lower().strip()

            import namegen
            if (
                name_clean
                and name_clean != "none"
                and name_clean not in player_names
                and name_clean not in enemy_names
                and name_clean not in departure_names
                and namegen.is_valid_entity_name(name_clean)
                and not namegen.is_collective_entity_name(name_clean)
            ):
                # Known-NPC Spatial Whitelist Gate:
                # When moving locations, previous-room patrons or known contacts/roster NPCs cannot enter the scene
                # unless explicitly invited, party member/temporary companion, destination staged occupant, or appointment target.
                if old_loc and new_loc and old_loc.lower() != new_loc.lower():
                    carried_old_names = {
                        game_engine._get_npc_name(cn).strip().lower()
                        for cn in retained_old
                        if game_engine._get_npc_name(cn)
                    }
                    roster_by_name: dict[str, dict] = {}
                    if session.get("id"):
                        try:
                            for r_npc in (db.get_anomalous_agent_roster(session["id"]) or []) + (db.get_school_roster(session["id"]) or []):
                                if isinstance(r_npc, dict) and r_npc.get("name"):
                                    roster_by_name[str(r_npc["name"]).strip().lower()] = r_npc
                        except Exception:
                            pass
                    matched_kc = next(
                        (c for c in known_contacts if str(c.get("name") or c.get("npc_id") or "").strip().lower() == name_clean),
                        None,
                    )
                    matched_roster = roster_by_name.get(name_clean)
                    was_in_old = any(game_engine._get_npc_name(on).strip().lower() == name_clean for on in old_npcs)
                    is_old_or_contact = (
                        was_in_old
                        or matched_kc is not None
                        or matched_roster is not None
                        or name_clean in left_behind_names
                    )
                    if is_old_or_contact:
                        has_mobile_dest_presence = False
                        if not was_in_old and name_clean not in left_behind_names and has_active_physical_presence(canon_name, result, full_narr):
                            npc_rec = matched_kc or matched_roster
                            kc_loc = (
                                str((matched_kc.get("basic_info") or {}).get("location") or matched_kc.get("location") or "")
                                if isinstance(matched_kc, dict)
                                else (
                                    str(matched_roster.get("primary_facility") or matched_roster.get("secondary_facility") or matched_roster.get("location") or "")
                                    if isinstance(matched_roster, dict)
                                    else ""
                                )
                            )
                            from mechanics.world.waypoints import check_location_matches_waypoint
                            is_stationed_here = bool(
                                kc_loc
                                and new_loc
                                and (check_location_matches_waypoint(new_loc, kc_loc) or check_location_matches_waypoint(kc_loc, new_loc))
                            )
                            kc_zone = get_zone_location_name(kc_loc) if kc_loc else ""
                            if is_stationed_here or (
                                is_character_mobile(canon_name, npc_rec, scen_key)
                                and (
                                    (kc_zone and dest_zone and is_campus_co_located(kc_zone, dest_zone, scen_key))
                                    or has_narrative_continuity_bridge(canon_name, session=session, actions=actions, new_loc=new_loc)
                                )
                            ):
                                has_mobile_dest_presence = True

                        is_permitted = (
                            name_clean in carried_old_names
                            or name_clean in formal_party_names
                            or is_npc_invited_in_action(canon_name, actions)
                            or is_rendezvous_target(name_clean, actions=actions, session_id=sess_id, new_loc=new_loc)
                            or name_clean in staged_names
                            or (len(name_clean.split()[0]) >= 3 and name_clean.split()[0] in staged_names)
                            or name_clean in appointment_targets
                            or name_clean in newly_recruited
                            or has_mobile_dest_presence
                        )
                        if not is_permitted:
                            continue

                if name_clean not in final_by_name:

                    n_dict = dict(n) if isinstance(n, dict) else {"name": canon_name}

                    n_dict["name"] = canon_name

                    final_by_name[name_clean] = n_dict

                    final_npcs.append(n_dict)

                elif isinstance(n, dict):

                    ex_n = final_by_name[name_clean]

                    for k, v in n.items():

                        if v not in (None, "", [], {}) and ex_n.get(k) in (None, "", [], {}):

                            ex_n[k] = v



    # Deterministic Meetup & Quest Rendezvous Presence Injection:

    # If the player is at the rendezvous location of an active phone appointment, quest waypoint, or travel action, ensure the NPC is present

    if session.get("id") and new_loc:

        try:

            from mechanics.world.waypoints import check_location_matches_waypoint

            present_clean_names = {game_engine._get_npc_name(x).lower() for x in final_npcs}



            # 1. Active rendezvous commitments within window
            from mechanics.system.commitments_engine import get_active_rendezvous_at_node, _canon_key
            s_day = session.get("current_day")
            s_min = session.get("current_minute")
            window_appts = get_active_rendezvous_at_node(session["id"], new_loc, current_day=s_day, current_minute=s_min)

            contact_map_by_key = {}
            for kc in known_contacts:
                kc_nm = str(kc.get("name") or "").strip()
                if kc_nm:
                    for kk in (kc.get("npc_id"), kc_nm, _canon_key(kc_nm)):
                        if kk:
                            contact_map_by_key[str(kk).strip().lower()] = kc

            for appt in window_appts:
                appt_status = appt.get("status")
                candidate_names = []
                for p in (appt.get("participants") or []):
                    pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
                    if pk.lower() == "player":
                        continue
                    kc = contact_map_by_key.get(pk.lower())
                    nm = kc.get("name") if kc else (p.get("name") or pk.replace("_", " ").title())
                    if nm:
                        candidate_names.append(str(nm).strip())
                if not candidate_names:
                    tgt = str(appt.get("target_entity") or "").strip()
                    if tgt and tgt.lower() not in ("player", "group"):
                        kc = contact_map_by_key.get(tgt.lower())
                        candidate_names.append(kc.get("name") if kc else tgt.replace("_", " ").title())

                for appt_npc in candidate_names:
                    appt_clean = appt_npc.strip().lower()
                    if appt_status in ("arrived", "in_progress"):
                        was_present = any(game_engine._get_npc_name(x).lower() == appt_clean for x in old_npcs) or is_dialogue_partner(appt_npc, session=session)
                        if not was_present:
                            continue
                    if appt_clean not in present_clean_names and appt_clean not in player_names and appt_clean not in enemy_names and appt_clean not in departure_names:
                        c_data = contact_map_by_key.get(appt_clean) or contact_map_by_key.get(_canon_key(appt_npc))
                        role = (c_data.get("basic_info") or {}).get("role", "Contact") if c_data else "Contact"
                        disp = (c_data.get("basic_info") or {}).get("disposition", "friendly") if c_data else "friendly"
                        final_npcs.append({"name": appt_npc, "role": role, "disposition": disp})
                        present_clean_names.add(appt_clean)



            # 2. Active Quest Waypoints, Travel-to-Meet Actions, and Narrative Continuity Meetups

            for c in known_contacts:

                c_nm = str(c.get("name") or "").strip()

                if not c_nm:

                    continue

                c_clean = c_nm.lower()

                if c_clean in present_clean_names or c_clean in player_names or c_clean in enemy_names or c_clean in departure_names:

                    continue

                is_rendez = is_rendezvous_target(c_nm, actions=actions, session_id=session["id"], new_loc=new_loc)

                if c_clean in left_behind_names and not is_rendez:

                    continue

                has_bridge = has_narrative_continuity_bridge(c_nm, session=session, actions=actions, new_loc=new_loc)

                is_mobile = is_character_mobile(c_nm, c, scen_key)



                if is_rendez:

                    is_travel = any(is_movement_action(a.get("label", "") if isinstance(a, dict) else str(a)) for a in (actions or []))

                    if new_loc == old_loc and not is_travel:
                        continue

                    role = (c.get("basic_info") or {}).get("role", "Contact") or "Contact"

                    disp = (c.get("basic_info") or {}).get("disposition", "friendly") or "friendly"

                    final_npcs.append({"name": c_nm, "role": role, "disposition": disp})

                    present_clean_names.add(c_clean)

        except Exception:

            pass



    # Post-injection departure filtering

    if departure_names:

        final_npcs = [

            n for n in final_npcs

            if game_engine._get_npc_name(n).lower() not in departure_names

        ]



    # Reset locations in DB for visiting guests who departed from a player's residence/room

    if session.get("id") and departure_names and new_loc:

        game_engine.reset_departed_guest_locations(departure_names, session["id"], new_loc)



    # Synchronize canonical contact locations for all physically present NPCs

    if session.get("id") and new_loc and final_npcs:

        sync_contact_locations(final_npcs, new_loc, session["id"])

        try:
            from mechanics.social.school_roster import hydrate_school_character
            from mechanics.social.genealogy import maybe_promote_scene_parent

            dir_roster = db.get_school_roster(session["id"])
            dir_map = {str(d.get("name", "")).strip().lower(): d for d in dir_roster} if dir_roster else {}
            for fn in final_npcs:
                raw_fn_nm = game_engine._get_npc_name(fn)
                fn_nm = raw_fn_nm.lower()
                if fn_nm in dir_map:
                    hydrate_school_character(session["id"], dir_map[fn_nm])
                if raw_fn_nm:
                    maybe_promote_scene_parent(session["id"], raw_fn_nm, location=new_loc)
        except Exception:
            pass

    try:
        from game_engine.npcs.stage_manager import resolve_post_turn_stage_delta
        excluded_for_stage = set()
        if enemy_names:
            excluded_for_stage.update(enemy_names)
        if remote_npc_names:
            excluded_for_stage.update(remote_npc_names)
        if departure_names:
            excluded_for_stage.update(departure_names)
        if left_behind_names:
            excluded_for_stage.update(left_behind_names)

        final_npcs = resolve_post_turn_stage_delta(
            session=session,
            raw_npcs_present=final_npcs,
            narrative=full_narr,
            actions=actions or [],
            location_changed=(new_loc != old_loc),
            new_loc=new_loc,
            contacts=known_contacts,
            scenario_key=scen_key,
            excluded_names=excluded_for_stage,
            skip_prose_departures=True,
        )
    except Exception:
        pass

    try:
        from game_engine.npcs.stage_manager import update_stage_blocking_and_composure_post_turn
        rel_deltas = {}
        for ru in (result.get("relationship_updates") or []):
            if isinstance(ru, dict) and ru.get("name"):
                rel_deltas[ru["name"].strip().lower()] = int(ru.get("delta_score") or ru.get("delta") or 0)
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=actions or [],
            narrative=full_narr.lower(),
            rel_deltas=rel_deltas,
        )
    except Exception:
        pass

    if old_loc and new_loc and old_loc.lower() != new_loc.lower() and isinstance(result, dict):
        surviving_names_low = {game_engine._get_npc_name(fn).strip().lower() for fn in final_npcs if game_engine._get_npc_name(fn)}
        if isinstance(result.get("dialogue_partners"), list):
            result["dialogue_partners"] = [
                dp for dp in result["dialogue_partners"]
                if str(dp).strip().lower() in surviving_names_low
            ]
        if result.get("dialogue_partner"):
            dp_str = str(result["dialogue_partner"]).strip().lower()
            if dp_str not in surviving_names_low:
                result["dialogue_partner"] = result["dialogue_partners"][0] if result.get("dialogue_partners") else None

    return final_npcs



def _sanitize_outcome_person_names(outcome: dict, session_id: int, scen_key: str):

    """Detect if any person entity in outcome was named with a generic role title

    or a partial-role alias (e.g. 'President Sarah'), and replace it with the

    authentic canonical name (linking to matching faction leader if applicable)."""

    from namegen import is_generic_role_name, generate_person_name, is_valid_entity_name

    if not isinstance(outcome, dict):

        return



    # Build faction leader maps:

    #   faction_leader_map: role_title.lower() → canonical full name

    #   faction_name_tokens: individual name token.lower() → canonical full name

    #     (catches "President Sarah" when the roster has "Denise Yamada" as president)

    faction_leader_map = {}

    faction_name_tokens = {}  # e.g. {"denise": "Denise Yamada", "yamada": "Denise Yamada"}

    faction_title_words = set()

    try:

        factions = db.get_factions(session_id)

        for f in factions:

            roster = f.get("leadership_roster") or []

            for r in roster:

                if r.get("title") and r.get("name"):

                    title_clean = r["title"].lower().strip()

                    faction_leader_map[title_clean] = r["name"]

                    for w in title_clean.split():

                        if w not in {"the", "a", "an", "of", "and", "&"}:

                            faction_title_words.add(w)

                    # Also index individual name tokens for partial-alias matching

                    for token in r["name"].strip().split():

                        if len(token) > 2:

                            faction_name_tokens[token.lower()] = r["name"]

    except Exception:

        pass



    def _resolve_name(raw_name: str, gender: str = "") -> str | None:

        """Return canonical faction name if raw_name is a generic role or partial-role alias,

        else return None (meaning: keep the name as-is)."""

        if not raw_name:

            return None

        lower = raw_name.lower().strip()

        # Exact role title match (e.g. "Student Council President")

        if is_generic_role_name(raw_name) and lower in faction_leader_map:

            return faction_leader_map[lower]



        tokens = lower.split()

        has_role_word = any(is_generic_role_name(t) or t in faction_title_words for t in tokens)



        if is_generic_role_name(raw_name) or has_role_word or not is_valid_entity_name(raw_name):

            # 1. Check if any token is a known name token

            for tok in tokens:

                if tok in faction_name_tokens:

                    return faction_name_tokens[tok]

            # 2. Match against faction_leader_map by title word overlap

            best_match = None

            best_score = 0.0

            for title, name in faction_leader_map.items():

                title_words = set(title.split())

                matched_words = [t for t in tokens if t in title_words]

                if matched_words:

                    score = float(len(matched_words))

                    # Specificity adjustments: penalize if key qualifiers mismatch

                    for qual in ["vice", "secretary", "representative", "treasurer", "president"]:

                        if qual in title_words and qual not in tokens:

                            score -= 0.5

                    if score > best_score:

                        best_score = score

                        best_match = name

            if best_match and best_score > 0:

                return best_match

            # Fallback: generate a fresh name if it was a generic role or invalid entity name

            if is_generic_role_name(raw_name) or not is_valid_entity_name(raw_name):

                return generate_person_name(scen_key, gender=gender)

        return None



    replacements = {}



    # 1. Scan new_entities

    for entity in outcome.get("new_entities", []) or []:

        if not isinstance(entity, dict):

            continue

        ent_type = str(entity.get("type", "person")).lower()

        ent_name = str(entity.get("name", "")).strip()

        if ent_type == "person" and ent_name:

            new_name = _resolve_name(ent_name, gender=entity.get("gender", ""))

            if new_name and new_name != ent_name:

                replacements[ent_name] = new_name

                entity["name"] = new_name

                desc = entity.get("description", "")

                if ent_name.lower() not in desc.lower():

                    entity["description"] = f"{ent_name} — {desc}".strip(" —")



    # 2. Scan npcs_present

    npcs_pres = outcome.get("npcs_present")

    if isinstance(npcs_pres, list):

        for idx, npc in enumerate(npcs_pres):

            if isinstance(npc, dict):

                npc_name = str(npc.get("name", "")).strip()

                if npc_name:

                    new_name = _resolve_name(npc_name) or replacements.get(npc_name)

                    if new_name and new_name != npc_name:

                        replacements[npc_name] = new_name

                        npc["name"] = new_name

            elif isinstance(npc, str) and npc.strip():

                npc_name = npc.strip()

                new_name = _resolve_name(npc_name) or replacements.get(npc_name)

                if new_name and new_name != npc_name:

                    replacements[npc_name] = new_name

                    npcs_pres[idx] = new_name



    # 3. Scan relationship_updates

    for ru in outcome.get("relationship_updates", []) or []:

        if not isinstance(ru, dict):

            continue

        for key in ("npc_name", "name"):

            ru_name = str(ru.get(key, "")).strip()

            if ru_name:

                new_name = _resolve_name(ru_name) or replacements.get(ru_name)

                if new_name and new_name != ru_name:

                    replacements[ru_name] = new_name

                    ru[key] = new_name



    # 4. Scan character_outcomes

    for co in outcome.get("character_outcomes", []) or []:

        if not isinstance(co, dict):

            continue

        co_name = str(co.get("name", "")).strip()

        if co_name in replacements:

            co["name"] = replacements[co_name]



    # 5. Scan entity_audit & npc_departures

    entity_audit = outcome.get("entity_audit")

    if isinstance(entity_audit, dict):

        for audit_key in ("present_named_characters", "speaking_characters", "departed_characters"):

            arr = entity_audit.get(audit_key)

            if isinstance(arr, list):

                for idx, raw_nm in enumerate(arr):

                    if isinstance(raw_nm, str) and raw_nm.strip():

                        nm_str = raw_nm.strip()

                        new_name = _resolve_name(nm_str) or replacements.get(nm_str)

                        if new_name and new_name != nm_str:

                            replacements[nm_str] = new_name

                            arr[idx] = new_name



    deps = outcome.get("npc_departures")

    if isinstance(deps, list):

        for idx, d_item in enumerate(deps):

            if isinstance(d_item, str) and d_item.strip():

                nm_str = d_item.strip()

                new_name = _resolve_name(nm_str) or replacements.get(nm_str)

                if new_name and new_name != nm_str:

                    replacements[nm_str] = new_name

                    deps[idx] = new_name

            elif isinstance(d_item, dict) and d_item.get("name"):

                nm_str = str(d_item.get("name", "")).strip()

                new_name = _resolve_name(nm_str) or replacements.get(nm_str)

                if new_name and new_name != nm_str:

                    replacements[nm_str] = new_name

                    d_item["name"] = new_name

