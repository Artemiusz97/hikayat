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
    extract_speaking_npcs_from_narrative,
    is_npc_invited_in_action,
)
from .presence import (
    sync_hostile_entities,
    classify_scene_npcs,
    extract_departed_npcs_from_narrative,
    is_mentioned_only_in_absence_or_memory,
    reset_departed_guest_locations,
    _distribute_fallback_locations,
)


def process_scene_npcs(result: dict, session: dict, new_loc: str, old_loc: str, actions: list = None) -> list[dict]:

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

    player_names = set()

    if session.get("turn_order"):

        for uid in session["turn_order"]:

            try:

                with db.get_conn() as conn:

                    c_rows = conn.execute("SELECT name FROM characters WHERE user_id = ?", (uid,)).fetchall()

                    for cr in c_rows:

                        if cr["name"]:

                            p_name = str(cr["name"]).strip().lower()

                            player_names.add(p_name)

                            p_first = (p_name.split() or [""])[0]

                            if len(p_first) >= 3:

                                player_names.add(p_first)

            except Exception:

                pass



    # Load formal party NPC names (permanent party companions who are protected from guest departure)

    formal_party_names = set()

    if session.get("id"):

        try:

            for p in db.get_session_party_npcs(session["id"]):

                p_name = str(p.get("name", "")).strip().lower()

                if p_name:

                    formal_party_names.add(p_name)

        except Exception:

            pass



    old_npcs = session.get("current_npcs") or []

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



    candidate_depart_npcs = list(old_npcs) + list(result.get("npcs_present") or []) + list(known_contacts)

    narr_departures = game_engine.extract_departed_npcs_from_narrative(full_narr, candidate_depart_npcs, actions=actions)



    all_raw_departures = list(llm_departures) + list(audit_departures) + list(narr_departures)

    departure_names = set()

    for d in all_raw_departures:

        if isinstance(d, dict):

            d_nm = str(d.get("name") or "").strip().lower()

        else:

            d_nm = str(d or "").strip().lower()

        if d_nm and d_nm not in player_names and d_nm not in formal_party_names:

            departure_names.add(d_nm)

            d_first = (d_nm.split() or [""])[0]

            if len(d_first) >= 3:

                departure_names.add(d_first)



    # Mark departing NPCs' phone appointments as completed

    if sess_id and departure_names:

        try:

            active_appts = db.get_phone_appointments(sess_id, status="arrived") + db.get_phone_appointments(sess_id, status="pending")

            for appt in active_appts:

                a_name = str(appt.get("npc_name", "")).strip().lower()

                a_id = str(appt.get("npc_id", "")).strip().lower()

                if a_name in departure_names or a_id in departure_names or any(d in a_name for d in departure_names):

                    db.update_phone_appointment_status(sess_id, appt.get("npc_id", ""), "completed")

        except Exception:

            pass



    remote_npc_names = set()

    for c in known_contacts:

        c_name = str(c.get("name") or c.get("npc_id") or "").lower().strip()

        c_loc = c.get("location") or (c.get("basic_info") or {}).get("location") or ""

        if c_loc and c_name:

            c_zone = get_zone_location_name(c_loc)

            if c_zone and dest_zone and c_zone.lower() != dest_zone.lower():

                # Check exemptions:

                # 1. Is this NPC the intended target of travel or an active quest waypoint / appointment?

                if is_rendezvous_target(c_name, actions=actions, session_id=sess_id, new_loc=new_loc):

                    continue

                # 2. Campus Quad Mobility & Narrative Continuity for Mobile Characters

                if is_character_mobile(c_name, c, scen_key):

                    has_bridge = is_campus_co_located(c_zone, dest_zone, scen_key) or has_narrative_continuity_bridge(c_name, session=session, actions=actions, new_loc=new_loc)

                    if has_bridge and has_active_physical_presence(c_name, result, full_narr):

                        continue

                remote_npc_names.add(c_name)



    new_npcs = list(result.get("npcs_present") or [])

    if isinstance(new_npcs, str):

        new_npcs = [{"name": new_npcs}]



    # 1. Incorporate entity_audit present/speaking characters if provided by model

    entity_audit = result.get("entity_audit") or {}

    if isinstance(entity_audit, dict):

        audit_present = entity_audit.get("present_named_characters") or []

        if isinstance(audit_present, list):

            for a_name in audit_present:

                if isinstance(a_name, str) and a_name.strip():

                    a_clean = a_name.strip().lower()

                    if a_clean not in player_names and a_clean not in departure_names:

                        new_npcs.append({"name": a_name.strip()})

        audit_speaking = entity_audit.get("speaking_characters") or []

        if isinstance(audit_speaking, list):

            for a_name in audit_speaking:

                if isinstance(a_name, str) and a_name.strip():

                    a_clean = a_name.strip().lower()

                    if a_clean not in player_names and a_clean not in departure_names:

                        new_npcs.append({"name": a_name.strip()})



    # 2. Prose-to-Entity Scanner: Scan generated narrative prose for mentioned faction members & local contacts

    narr_prose = full_narr.lower()



    if session.get("id") and narr_prose.strip():

        # A. Faction Roster Scanner

        try:

            sess_factions = db.get_factions(session["id"])

            for f in sess_factions:

                for member in f.get("leadership_roster", []):

                    m_name = member.get("name", "").strip()

                    if not m_name or member.get("is_player"):

                        continue

                    m_lower = m_name.lower()

                    if m_lower in player_names or m_lower in departure_names:

                        continue

                    first_name = m_lower.split()[0] if len(m_lower.split()) > 1 else ""

                    if first_name and first_name in departure_names:

                        continue

                    # Check if mentioned only in absence/memory

                    if game_engine.is_mentioned_only_in_absence_or_memory(m_name, narr_prose):

                        continue

                    # Match full name or distinct first name (min 3 chars)

                    if m_lower in narr_prose or (first_name and len(first_name) >= 3 and (f" {first_name}" in narr_prose or f"—{first_name}" in narr_prose or f"-{first_name}" in narr_prose or narr_prose.startswith(first_name))):

                        from mechanics.world.mobility import is_mentioned_only_in_dialogue, has_active_physical_presence

                        if is_mentioned_only_in_dialogue(m_name, narr_prose):

                            continue

                        if not has_active_physical_presence(m_name, result, narrative_text=narr_prose):

                            continue

                        new_npcs.append({"name": m_name, "role": member.get("title", "")})

        except Exception:

            pass



        # B. Local Contacts Scanner (only for contacts in the same zone, co-located campus realm, or rendezvous target)

        try:

            sess_contacts = db.get_contacts(session["id"])

            for c in sess_contacts:

                c_name = str(c.get("name") or "").strip()

                if not c_name:

                    continue

                c_lower = c_name.lower()

                if c_lower in player_names or c_lower in departure_names:

                    continue

                first_name = c_lower.split()[0] if len(c_lower.split()) > 1 else ""

                if first_name and first_name in departure_names:

                    continue

                # Check if mentioned only in absence/memory

                if game_engine.is_mentioned_only_in_absence_or_memory(c_name, narr_prose):

                    continue



                c_loc = c.get("location") or (c.get("basic_info") or {}).get("location") or ""

                c_zone = get_zone_location_name(c_loc) if c_loc else ""



                is_zone_match = bool(c_zone and dest_zone and (c_zone.lower() == dest_zone.lower() or is_campus_co_located(c_zone, dest_zone, scen_key)))

                is_target = is_rendezvous_target(c_name, actions=actions, session_id=sess_id, new_loc=new_loc)

                has_bridge = has_narrative_continuity_bridge(c_name, session=session, actions=actions, new_loc=new_loc)

                if not is_zone_match and not is_target and not (has_bridge and is_character_mobile(c_name, c, scen_key)):

                    continue

                if c_lower in narr_prose or (first_name and len(first_name) >= 4 and f" {first_name}" in narr_prose):

                    from mechanics.world.mobility import is_mentioned_only_in_dialogue, has_active_physical_presence

                    if is_mentioned_only_in_dialogue(c_name, narr_prose):

                        continue

                    if not has_active_physical_presence(c_name, result, narrative_text=narr_prose):

                        continue

                    c_binfo = c.get("basic_info") or {}

                    new_npcs.append({

                        "name": c_name,

                        "role": c_binfo.get("role", ""),

                        "description": c_binfo.get("description", ""),

                        "faction": c_binfo.get("faction", ""),

                        "club": c_binfo.get("club", ""),

                        "club_role": c_binfo.get("club_role", ""),

                        "grade": c_binfo.get("grade", ""),

                    })

        except Exception:

            pass



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



    seen_names: dict[str, dict] = {}

    combined_new_npcs = []

    for n in (new_npcs + new_entity_npcs):

        if isinstance(n, dict):

            name_clean = str(n.get("name") or "").strip().lower()

            is_comp = (name_clean in formal_party_names) or bool(n.get("is_permanent_party"))

            if name_clean in player_names or name_clean in departure_names:

                continue

            if not is_comp and (name_clean in remote_npc_names or name_clean in enemy_names):

                continue

            if not name_clean:

                continue

            if name_clean not in seen_names:

                n_copy = dict(n)

                seen_names[name_clean] = n_copy

                combined_new_npcs.append(n_copy)

            else:

                existing_n = seen_names[name_clean]

                for k, v in n.items():

                    if v not in (None, "", [], {}) and existing_n.get(k) in (None, "", [], {}):

                        existing_n[k] = v

        elif isinstance(n, str) and n.strip():

            name_clean = n.strip().lower()

            if name_clean in player_names or name_clean in departure_names or name_clean in remote_npc_names or name_clean in enemy_names:

                continue

            if name_clean and name_clean not in seen_names:

                n_copy = {"name": n.strip()}

                seen_names[name_clean] = n_copy

                combined_new_npcs.append(n_copy)



    left_behind_names = set()

    if new_loc != old_loc:

        # Complete any phone appointments that were 'arrived' at old_loc when moving away

        if sess_id:

            try:

                from mechanics.world.waypoints import check_location_matches_waypoint

                for appt in db.get_phone_appointments(sess_id, status="arrived"):

                    appt_loc = appt.get("rendezvous_location", "")

                    if appt_loc and check_location_matches_waypoint(old_loc, appt_loc) and not check_location_matches_waypoint(new_loc, appt_loc):

                        db.update_phone_appointment_status(sess_id, appt.get("npc_id", ""), "completed")

            except Exception:

                pass



        old_zone = get_zone_location_name(old_loc)

        new_zone = get_zone_location_name(new_loc)

        old_primary = get_primary_location_name(old_loc)

        new_primary = get_primary_location_name(new_loc)

        is_same_venue = bool(

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

                n_clean = game_engine._get_npc_name(n).lower()

                if n_clean in left_behind_names and n_clean not in newly_recruited:

                    # Defense-in-depth: Do not filter if the NPC has a narrative continuity bridge AND active physical presence at destination

                    if has_narrative_continuity_bridge(n_clean, session=session, actions=actions, new_loc=new_loc):

                        if has_active_physical_presence(n_clean, result, dest_narr or full_narr):

                            filtered_combined_new.append(n)

                            continue

                    continue

                filtered_combined_new.append(n)

            combined_new_npcs = filtered_combined_new

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

            name_clean = game_engine._get_npc_name(n).lower()

            if name_clean and name_clean != "none" and name_clean not in player_names and name_clean not in enemy_names and name_clean not in departure_names:

                if name_clean not in final_by_name:

                    n_dict = dict(n) if isinstance(n, dict) else {"name": game_engine._get_npc_name(n)}

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

            name_clean = game_engine._get_npc_name(n).lower()

            if name_clean and name_clean != "none" and name_clean not in player_names and name_clean not in enemy_names and name_clean not in departure_names:

                if name_clean not in final_by_name:

                    n_dict = dict(n) if isinstance(n, dict) else {"name": game_engine._get_npc_name(n)}

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



            # 1. Phone appointments

            pending_appts = db.get_phone_appointments(session["id"], status="pending")

            # Only include 'arrived' appointments if the NPC was already actively in old_npcs or dialogue_partner

            arrived_appts = [

                a for a in db.get_phone_appointments(session["id"], status="arrived")

                if any(game_engine._get_npc_name(x).lower() == a.get("npc_name", "").strip().lower() for x in old_npcs)

                or is_dialogue_partner(a.get("npc_name", ""), session=session)

            ]

            for appt in (pending_appts + arrived_appts):

                appt_loc = appt.get("rendezvous_location", "")

                appt_npc = appt.get("npc_name", "")

                if appt_loc and appt_npc and check_location_matches_waypoint(new_loc, appt_loc):

                    appt_clean = appt_npc.strip().lower()

                    if appt_clean not in present_clean_names and appt_clean not in player_names and appt_clean not in enemy_names and appt_clean not in departure_names:

                        c_data = next((c for c in known_contacts if str(c.get("name", "")).strip().lower() == appt_clean), None)

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

                        full_scene_nar = (str(result.get("outcome_narrative") or "") + "\n" + str(result.get("next_narrative") or result.get("narrative") or "")).strip()

                        if not has_active_physical_presence(c_nm, result, narrative_text=full_scene_nar):

                            continue

                    role = (c.get("basic_info") or {}).get("role", "Contact") or "Contact"

                    disp = (c.get("basic_info") or {}).get("disposition", "friendly") or "friendly"

                    final_npcs.append({"name": c_nm, "role": role, "disposition": disp})

                    present_clean_names.add(c_clean)

                elif has_bridge and is_mobile:

                    full_scene_nar = (str(result.get("outcome_narrative") or "") + "\n" + str(result.get("next_narrative") or result.get("narrative") or result.get("scene_text") or "")).strip()

                    if has_active_physical_presence(c_nm, result, narrative_text=full_scene_nar):

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

            dir_roster = db.get_school_roster(session["id"])

            if dir_roster:

                dir_map = {str(d.get("name", "")).strip().lower(): d for d in dir_roster}

                for fn in final_npcs:

                    fn_nm = game_engine._get_npc_name(fn).lower()

                    if fn_nm in dir_map:

                        hydrate_school_character(session["id"], dir_map[fn_nm])

        except Exception:

            pass



    return final_npcs



def _sanitize_outcome_person_names(outcome: dict, session_id: int, scen_key: str):

    """Detect if any person entity in outcome was named with a generic role title

    or a partial-role alias (e.g. 'President Sarah'), and replace it with the

    authentic canonical name (linking to matching faction leader if applicable)."""

    from namegen import is_generic_role_name, generate_person_name

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



        if is_generic_role_name(raw_name) or has_role_word:

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

            # Fallback: generate a fresh name if it was a generic role

            if is_generic_role_name(raw_name):

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

