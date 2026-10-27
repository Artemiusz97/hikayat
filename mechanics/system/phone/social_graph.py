from __future__ import annotations
"""
Social graph connections, profile lookup, friend request resolution, and peer discovery for Hikayat.
"""
import json
import random
import re
import db
from skill_check import resolve_check


def _safe_get_contacts(session_id: int, character_id: int = 0, resolve_relations: bool = False) -> list[dict]:
    """Retrieves contacts, falling back gracefully if db.get_contacts is mocked without resolve_relations."""
    try:
        return db.get_contacts(session_id, character_id=character_id, resolve_relations=resolve_relations) or []
    except TypeError:
        return db.get_contacts(session_id, character_id=character_id) or []


def get_mutual_friends_and_ties(session_id: int, user_id: int, target_dict: dict) -> dict:
    """Calculates mutual contacts, shared clubs, and sibling connections with a target NPC."""
    char = db.get_character(user_id)
    contacts = _safe_get_contacts(session_id, character_id=char.get("id", 0), resolve_relations=False) if char else []
    contact_names = {c.get("name", "").strip().lower(): c for c in contacts}

    sib_name = str(target_dict.get("sibling_name", "")).strip()
    is_sibling_friend = bool(sib_name and sib_name.lower() in contact_names)

    target_club = str(target_dict.get("club", "")).strip()
    shared_club_friends = []
    if target_club and target_club.lower() != "none":
        for c in contacts:
            b = c.get("basic_info", {})
            c_club = str(b.get("club", "")).strip()
            c_desc = str(b.get("description", ""))
            if (c_club and c_club.lower() == target_club.lower()) or (target_club.lower() in c_desc.lower()):
                shared_club_friends.append(c["name"])

    mutuals = []
    if is_sibling_friend:
        mutuals.append(sib_name)
    for cf in shared_club_friends:
        if cf not in mutuals:
            mutuals.append(cf)

    # Query normalized social graph for true mutual friends
    try:
        import mechanics.social.relationship_graph as rg
        if char:
            p_key = rg.player_person_key(char.get("id", 0))
            t_key = rg.canonical_person_key(target_dict.get("name", ""))
            graph_mutuals = rg.get_mutual_friends(session_id, p_key, t_key)
            for gm in graph_mutuals:
                gm_name = gm.get("name")
                if gm_name and gm_name not in mutuals:
                    mutuals.append(gm_name)
    except Exception:
        pass

    return {
        "is_sibling_friend": is_sibling_friend,
        "sibling_name": sib_name,
        "shared_club": target_club if target_club.lower() != "none" else "",
        "shared_club_friends": shared_club_friends,
        "mutual_friends": mutuals
    }


def lookup_social_profile(session_id: int, user_id: int, query_name: str) -> dict | None:
    """Looks up a character's faux social media profile across directory, contacts, and lorebook."""
    if not query_name or not session_id:
        return None
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    char = db.get_character(user_id)
    q = str(query_name).strip().lower().replace("@", "")

    target_rec = None
    # 1. School directory lookup
    roster = db.get_school_roster(session_id)
    # Exact match first
    for r in roster:
        r_name = str(r.get("name", "")).lower()
        r_id = str(r.get("npc_id", "")).lower()
        if q == r_name or q == r_id:
            target_rec = dict(r)
            break
    # Substring match if no exact match
    if not target_rec:
        for r in roster:
            r_name = str(r.get("name", "")).lower()
            r_id = str(r.get("npc_id", "")).lower()
            if q in r_name or q in r_id:
                target_rec = dict(r)
                break

    # 2. Existing contacts lookup
    if not target_rec:
        contacts = _safe_get_contacts(session_id, character_id=char.get("id", 0), resolve_relations=False) if char else []
        for c in contacts:
            c_name = str(c.get("name", "")).lower()
            c_id = str(c.get("npc_id", "")).lower()
            if q == c_name or q in c_name or q == c_id:
                b = c.get("basic_info", {})
                target_rec = {
                    "session_id": session_id,
                    "name": c["name"],
                    "npc_id": c["npc_id"],
                    "role": b.get("role", "Contact"),
                    "grade": b.get("grade", "Student"),
                    "club": b.get("club", ""),
                    "clique": b.get("clique", ""),
                    "primary_facility": b.get("location", ""),
                    "sibling_name": b.get("sibling_name", ""),
                    "personality_summary": b.get("description", ""),
                    "is_hydrated": 1
                }
                break

    # 3. Current NPCs lookup
    if not target_rec and session:
        for n in (session.get("current_npcs") or []):
            if isinstance(n, dict):
                n_name = str(n.get("name", "")).lower()
                if q == n_name or q in n_name:
                    target_rec = {
                        "session_id": session_id,
                        "name": n.get("name"),
                        "npc_id": str(n.get("name", "")).lower().replace(" ", "_"),
                        "role": n.get("role", "Local Resident"),
                        "grade": "Contemporary",
                        "club": "",
                        "clique": "",
                        "primary_facility": session.get("current_location", ""),
                        "sibling_name": "",
                        "personality_summary": n.get("description", ""),
                        "is_hydrated": 0
                    }
                    break

    # 4. Lorebook lookup
    if not target_rec:
        lore = db.get_lorebook_entity(session_id, query_name)
        if lore:
            target_rec = {
                "session_id": session_id,
                "name": lore["name"],
                "npc_id": lore["name"].lower().replace(" ", "_"),
                "role": lore.get("motivation") or "Resident",
                "grade": "Contemporary",
                "club": "",
                "clique": "",
                "primary_facility": "",
                "sibling_name": "",
                "personality_summary": lore.get("description", ""),
                "is_hydrated": 0
            }

    # 5. Sibling Web & Family Tree lookup from existing contacts
    if not target_rec:
        from mechanics.social.school_roster import generate_sibling_student_peer
        all_contacts = db.get_contacts(session_id)
        for c in all_contacts:
            c_name = c.get("name", "")
            b = c.get("basic_info", {})
            sib_name = b.get("sibling_name") or ""
            # Check basic_info sibling_name
            if sib_name:
                sib_clean = sib_name.strip()
                if q == sib_clean.lower() or q in sib_clean.lower() or sib_clean.lower() in q:
                    target_rec = generate_sibling_student_peer(session_id, sib_clean, known_contact=c, scen_key=scen_key)
                    db.save_school_roster(session_id, [target_rec])
                    break

            # Check family relations tree
            relations = c.get("relations") or {}
            family = relations.get("family", [])
            for fam in family:
                fam_name = fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}".strip()
                fam_first = fam.get("first_name", "")
                relation_type = fam.get("relation", "")
                if not fam_name:
                    continue
                if q == fam_name.lower() or q in fam_name.lower() or fam_name.lower() in q or (fam_first and q == fam_first.lower()):
                    is_student_relative = any(k in relation_type.lower() for k in ("sister", "brother", "sibling", "twin", "cousin")) or fam.get("occupation", "").lower() in ("student", "high school student", "")
                    if is_student_relative:
                        target_rec = generate_sibling_student_peer(session_id, fam_name, known_contact=c, scen_key=scen_key)
                        db.save_school_roster(session_id, [target_rec])
                        break
            if target_rec:
                break

    if not target_rec:
        return None

    name = target_rec["name"]
    role = target_rec.get("role", "Student")
    desc = target_rec.get("personality_summary", "")

    # Check eligibility (faculty/staff/adult citizens cannot be contacts in high school scenarios)
    from mechanics import relationships
    grade_val = target_rec.get("grade", "")
    grade_low = str(grade_val).strip().lower()
    if grade_low in ("faculty", "citizen"):
        is_eligible = False
    elif grade_low in ("freshman", "sophomore", "junior", "senior", "youth peer", "grade 9", "grade 10", "grade 11", "grade 12"):
        is_eligible = True
    else:
        is_eligible = relationships.is_contact_eligible(
            name=name, role=role, description=desc, scenario=scen_key, session_id=session_id
        )

    contact_npc_id = str(target_rec.get("npc_id") or name).strip().lower().replace(" ", "_").replace(".", "")
    existing_contact = db.get_contact(session_id, contact_npc_id, character_id=char.get("id", 0)) if char else None

    # Determine whether they are already an unlocked friend in smartphone Line/DMs
    from mechanics.social.relationships import is_unlocked_contact
    party_npcs = db.get_session_party_npcs(session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    is_connected = bool(existing_contact and is_unlocked_contact(existing_contact, party_names))

    # Check cooldown (keyed strictly by npc_id or exact canonical full name to prevent shared-surname / honorific collisions)
    state = db.get_phone_social_state(session_id) or {}
    cds = state.get("friend_request_cooldowns", {})
    clean_full = name.lower().strip()
    entry = cds.get(contact_npc_id) or cds.get(clean_full)

    s_row = db.get_session(session_id) if session_id else None
    curr_day = int((session.get("current_day") if session else None) or (s_row.get("current_day") if s_row else 1) or 1)
    turn_count = len(session.get("history", [])) if session else 0

    on_cooldown = False
    turns_left = 0
    if entry:
        if isinstance(entry, dict):
            until_day = entry.get("until_day")
            if until_day is not None:
                on_cooldown = curr_day < int(until_day)
            else:
                on_cooldown = turn_count < entry.get("expire_turn", 0)
            turns_left = 5 if on_cooldown else 0
        elif isinstance(entry, (int, float)):
            turns_left = max(0, int(entry) - turn_count)
            on_cooldown = turns_left > 0

    ties = get_mutual_friends_and_ties(session_id, user_id, target_rec)

    import namegen
    first_h, last_h = namegen.extract_first_and_last_name(name)
    raw_handle_core = f"{first_h}_{last_h}" if (first_h and last_h) else (first_h or last_h or name)
    slug_core = re.sub(r"[^a-z0-9_]", "", raw_handle_core.lower().replace(" ", "_").replace("-", "_"))
    slug_core = re.sub(r"_+", "_", slug_core).strip("_")[:16]
    clean_handle = "@" + (slug_core or "student")
    if "president" in role.lower():
        clean_handle += "_sc"
    elif "captain" in role.lower():
        clean_handle += "_lead"
    elif "delinquent" in role.lower() or "rebel" in role.lower():
        clean_handle += "_x"

    return {
        "raw_record": target_rec,
        "name": name,
        "handle": clean_handle,
        "role": role,
        "grade": target_rec.get("grade", "Student"),
        "club": target_rec.get("club") or "None",
        "clique": target_rec.get("clique") or "General",
        "facility": target_rec.get("primary_facility") or "Campus Area",
        "personality": desc,
        "is_eligible": is_eligible,
        "is_faculty": not is_eligible,
        "is_already_contact": is_connected,
        "cooldown_turns_left": turns_left,
        "on_cooldown": on_cooldown,
        "npc_id": contact_npc_id,
        "mutual_friends": ties["mutual_friends"],
        "is_sibling_friend": ties["is_sibling_friend"],
        "sibling_name": ties["sibling_name"],
        "shared_club": ties["shared_club"]
    }


def resolve_social_friend_request(session: dict, user_id: int, profile: dict) -> dict:
    """Resolves sending a friend request with dynamic skill check modifiers."""
    session_id = session["id"]
    char = db.get_character(user_id)
    npc_id = profile["npc_id"]
    name = profile["name"]

    if profile.get("is_faculty") or not profile.get("is_eligible"):
        return {
            "accepted": False,
            "error": "restricted",
            "message": "🔒 **Account Restricted:** Faculty, staff, and adult town accounts cannot be added to student friend circles under Academy digital policy."
        }

    if profile.get("is_already_contact"):
        return {
            "accepted": True,
            "already_friend": True,
            "message": f"👥 **{name}** is already in your Contacts!"
        }

    # Check cooldown (keyed strictly by npc_id or exact canonical full name)
    state = db.get_phone_social_state(session_id) or {}
    cds = state.setdefault("friend_request_cooldowns", {})
    entry = cds.get(npc_id) or cds.get(name.lower().strip())

    s_row = db.get_session(session_id) if session_id else None
    curr_day = int((session.get("current_day") if session else None) or (s_row.get("current_day") if s_row else 1) or 1)
    turn_count = len(session.get("history", [])) if session else 0

    on_cooldown = False
    if entry:
        if isinstance(entry, dict):
            until_day = entry.get("until_day")
            if until_day is not None:
                on_cooldown = curr_day < int(until_day)
            else:
                on_cooldown = turn_count < entry.get("expire_turn", 0)
        elif isinstance(entry, (int, float)):
            on_cooldown = turn_count < int(entry)

    if on_cooldown or profile.get("cooldown_turns_left", 0) > 0:
        return {
            "accepted": False,
            "on_cooldown": True,
            "turns_left": profile.get("cooldown_turns_left", 5),
            "message": f"⏳ **Recent Request Pending/Declined:** {name} hasn't responded. You can try sending another request tomorrow."
        }

    # Dynamic Modifier Calculation
    cha_val = char.get("cha", 10) if char else 10
    bonus = 0
    mod_reasons = []

    if profile.get("is_sibling_friend"):
        bonus += 4
        mod_reasons.append(f"+4 (Friend of Sibling {profile.get('sibling_name')})")

    if profile.get("shared_club") and profile.get("shared_club") != "None":
        bonus += 2
        mod_reasons.append(f"+2 (Shared Club: {profile['shared_club']})")

    mutual_count = len(profile.get("mutual_friends", []))
    if mutual_count > 0:
        mut_bonus = min(4, mutual_count * 2)
        bonus += mut_bonus
        mod_reasons.append(f"+{mut_bonus} ({mutual_count} Mutual Friend{'s' if mutual_count > 1 else ''})")

    if bonus == 0:
        bonus -= 2
        mod_reasons.append("-2 (Total Stranger)")

    # Base DC = 11. Effective DC = 11 - bonus
    effective_dc = max(4, 11 - bonus)
    from skill_check import resolve_check
    luk_val = char.get("luk", 3) if char else 3
    check_res = resolve_check(cha_val, effective_dc, luck=luk_val)
    check = {
        "stat": "CHA",
        "chance": check_res.chance,
        "tier": check_res.tier,
        "tier_label": check_res.tier_label,
        "succeeded": check_res.succeeded
    }

    turn_count = len(session.get("history", []))
    state = db.get_phone_social_state(session_id) or {}
    cds = state.setdefault("friend_request_cooldowns", {})

    if check["succeeded"]:
        # Hydrate contact and unlock in smartphone
        scen_key = session.get("scenario", "fantasy")
        if "school" in scen_key or "high_school" in scen_key:
            from mechanics.social.school_roster import hydrate_school_character
            hydrate_school_character(session_id, profile.get("raw_record") or profile)
            c = db.get_contact(session_id, npc_id)
            if c:
                b_info = c.get("basic_info") or {}
                if isinstance(b_info, str):
                    try:
                        b_info = json.loads(b_info)
                    except Exception:
                        b_info = {}
                b_info["contact_added"] = True
                b_info["is_contact"] = True
                b_info["added_via_peerpulse"] = True
                db.upsert_contact(
                    session_id=session_id,
                    npc_id=npc_id,
                    name=name,
                    character_id=char.get("id", 0) if char else 0,
                    basic_info=b_info,
                )
        else:
            db.upsert_contact(
                session_id=session_id,
                npc_id=npc_id,
                name=name,
                character_id=char.get("id", 0) if char else 0,
                delta_score=5,
                basic_info={
                    "role": profile.get("role", "Contact"),
                    "description": profile.get("personality", ""),
                    "contact_added": True,
                    "is_contact": True,
                    "added_via_peerpulse": True,
                },
                track="platonic"
            )
        profile["is_already_contact"] = True
        return {
            "accepted": True,
            "check": check,
            "bonus": bonus,
            "mod_reasons": mod_reasons,
            "message": f"✅ **Friend Request Accepted!**\n**{name}** added you back! You can now message them via Direct Messages."
        }
    else:
        # Day-based cooldown: strictly once per day per character, cannot add again until the next day
        until_day = curr_day + 1
        cd_data = {
            "failed_day": curr_day,
            "until_day": until_day,
            "expire_turn": turn_count + 5,
        }
        cds[npc_id] = cd_data
        clean_name = name.lower().strip()
        if clean_name and clean_name != npc_id:
            cds[clean_name] = cd_data

        db.update_phone_social_state(session_id, state)
        profile["cooldown_turns_left"] = 5
        profile["on_cooldown"] = True
        return {
            "accepted": False,
            "check": check,
            "bonus": bonus,
            "mod_reasons": mod_reasons,
            "turns_cooldown": 5,
            "cooldown_until_day": until_day,
            "on_cooldown": True,
            "message": f"❌ **Request Left on Delivered:**\n**{name}** didn't accept your friend request. You can send another request tomorrow."
        }


def discover_suggested_peer(session_id: int, user_id: int) -> dict:
    """Discovers an un-contacted student peer or dynamically generates a new one."""
    char = db.get_character(user_id)
    contacts = _safe_get_contacts(session_id, character_id=char.get("id", 0), resolve_relations=False) if char else []
    contact_ids = {c["npc_id"].lower() for c in contacts}

    roster = db.get_school_roster(session_id)
    eligible_uncontacted = [
        r for r in roster
        if str(r.get("grade", "")).strip().lower() not in ("faculty", "citizen")
        and r["npc_id"].lower() not in contact_ids
    ]

    chosen = None
    if eligible_uncontacted:
        session = db.get_session(session_id)
        cur_loc = session.get("current_location", "") if session else ""
        local_peers = [p for p in eligible_uncontacted if p.get("primary_facility", "") in cur_loc or cur_loc in p.get("primary_facility", "")]
        if local_peers:
            chosen = random.choice(local_peers)
        else:
            chosen = random.choice(eligible_uncontacted)
    else:
        from mechanics.social.school_roster import generate_dynamic_student_peer
        session = db.get_session(session_id)
        scen_key = session.get("scenario", "high_school_drama") if session else "high_school_drama"
        chosen = generate_dynamic_student_peer(session_id, scen_key=scen_key)

    return lookup_social_profile(session_id, user_id, chosen["name"])


def get_suggested_peers(session_id: int, user_id: int, limit: int = 12) -> list[dict]:
    """
    Returns a prioritized list of suggested peer profiles for the PeerPulse social graph app.
    
    Priority order:
    1. Known student/peers from the current scene & session history who are NOT yet unlocked contacts
       (e.g. classmates in Homeroom like Henry Sterling, Diana Yamada, Kayo Yamamoto, Raphaël Ito).
    2. Other students who share sibling bonds or club affiliations with known contacts.
    3. Other eligible student peers from the school directory.
    
    Excludes:
    - Faculty, staff, and adult authority figures (who cannot be added to student friend circles).
    - Characters who are already unlocked contacts (relationship_score >= 100 or contact_added).
    """
    session = db.get_session(session_id) or {}
    char = db.get_character(user_id)
    char_name = str(char.get("name", "")).strip().lower() if char else ""
    party_npcs = db.get_session_party_npcs(session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}

    contacts = _safe_get_contacts(session_id, character_id=char.get("id", 0), resolve_relations=False) if char else []
    from mechanics.social.relationships import is_unlocked_contact
    unlocked_contact_names = {c["name"].lower().strip() for c in contacts if is_unlocked_contact(c, party_names)}

    seen_names = set(unlocked_contact_names)
    if char_name:
        seen_names.add(char_name)

    suggested_names = []

    # 1. Known peers in current scene
    for n in (session.get("current_npcs") or []):
        name = n.get("name") if isinstance(n, dict) else str(n)
        clean_n = str(name or "").strip()
        if clean_n and clean_n.lower() not in seen_names:
            suggested_names.append(clean_n)
            seen_names.add(clean_n.lower())

    # 2. Known peers in turn history (witnesses, dialogue partners)
    for h in reversed(session.get("history") or []):
        if not isinstance(h, dict):
            continue
        for w in (h.get("witnessed_by") or []):
            if w and isinstance(w, str):
                cw = w.strip()
                if cw and cw.lower() not in seen_names:
                    suggested_names.append(cw)
                    seen_names.add(cw.lower())
        dp = h.get("dialogue_partner")
        if dp and isinstance(dp, str):
            cdp = dp.strip()
            if cdp and cdp.lower() not in seen_names:
                suggested_names.append(cdp)
                seen_names.add(cdp.lower())

    # 3. Known peers in contacts table who are not yet unlocked
    for c in contacts:
        name = str(c.get("name") or "").strip()
        if name and name.lower() not in seen_names:
            suggested_names.append(name)
            seen_names.add(name.lower())

    # 4. Fill remaining slots with school directory students
    roster = db.get_school_roster(session_id) or []
    for r in roster:
        if len(suggested_names) >= limit:
            break
        r_name = str(r.get("name") or "").strip()
        grade = str(r.get("grade", "")).strip().lower()
        if r_name and r_name.lower() not in seen_names and grade not in ("faculty", "citizen"):
            suggested_names.append(r_name)
            seen_names.add(r_name.lower())

    # Convert names into full PeerPulse social profiles
    profiles = []
    for name in suggested_names:
        prof = lookup_social_profile(session_id, user_id, name)
        if prof and prof.get("is_eligible") and not prof.get("is_faculty"):
            if not prof.get("is_already_contact"):
                profiles.append(prof)
        if len(profiles) >= limit:
            break

    return profiles


def evaluate_pre_turn_witness_detection(
    session: dict,
    actions: list,
    player_name: str = "Player",
    target_npc: str = "",
    location_str: str = "",
) -> dict:
    """
    Deterministic pre-turn witness detection & procedural gossip propagation.
    Checks if a romantic, intimate, or illicit action occurs in a semi-public/public node,
    identifies witnesses or rolls public passerby chance, and queues a 0ms gossip post.
    """
    from mechanics.system.phone.gossip_feed import queue_witness_gossip_post

    action_str = ""
    if actions:
        fa = actions[0]
        action_str = str(fa.get("label") or fa.get("action") or "") if isinstance(fa, dict) else str(fa or "")
    act_low = action_str.lower()

    is_illicit = any(kw in act_low for kw in ("steal", "pick lock", "pickpocket", "sabotage", "trespass", "break in", "pry open", "sneak into", "plant evidence"))
    is_romantic_or_intimate = any(kw in act_low for kw in (
        "kiss", "caress", "undress", "touch", "embrace", "cuddle", "grope", "stroke",
        "intimate", "thrust", "penetrat", "oral", "handjob", "blowjob", "sex", "make out",
        "strip", "fingering", "fondle"
    ))

    session_id = session.get("id") or 0
    loc_display = str(location_str or session.get("current_location", "")).strip()
    curr_node_id = str(session.get("current_node_id") or "").strip()

    p_gender = str(session.get("lead_character_gender") or "").strip()
    if not p_gender and session.get("host_user_id") and hasattr(db, "get_character"):
        try:
            c_host = db.get_character(session["host_user_id"])
            if c_host and c_host.get("gender"):
                p_gender = str(c_host["gender"])
        except Exception:
            pass

    # Check for Public Indecency / Exposure (Invariant 4)
    from mechanics.social.physical_state import (
        check_venue_indecency_exposure,
        find_player_actor_key,
        is_private_intimate_venue,
        is_discreet_venue,
    )
    is_undressing_or_showering_only = (
        not is_illicit
        and (not is_romantic_or_intimate or any(w in act_low for w in ("undress", "strip", "shower", "wash", "change")))
        and not target_npc
    )
    if is_private_intimate_venue(
        loc_display,
        curr_node_id,
        session_id=session_id,
        player_gender=p_gender,
        is_undressing_or_showering_only=is_undressing_or_showering_only,
    ):
        return {"witness_spotted": False, "private": True}

    phys_st = session.get("physical_state") or (db.get_session_physical_state(session_id) if session_id else {})
    is_public_exposure = False
    exposure_type = "none"
    if phys_st and isinstance(phys_st, dict):
        actors_map = phys_st.get("actors") or {}
        p_key = find_player_actor_key(actors_map, session_id=session_id)
        if p_key and p_key in actors_map:
            p_cloth = actors_map[p_key].get("clothing") or {}
            exp_info = check_venue_indecency_exposure(p_cloth, loc_display, gender=p_gender or "female")
            if exp_info.get("requires_reaction"):
                is_public_exposure = True
                exposure_type = exp_info.get("exposure_type", "exposed")

    if not is_illicit and not is_romantic_or_intimate and not is_public_exposure:
        return {"witness_spotted": False}

    # Cover / Concealment check (0% behind stall / curtain / hidden prop)
    focal_point = str(session.get("focal_point") or "").lower()
    if any(cover in focal_point for cover in ("behind", "under", "hidden", "private", "curtain", "bleacher", "stall", "secluded", "alcove", "closet")):
        return {"witness_spotted": False, "covered": True}

    loc_low = loc_display.lower()
    if any(k in loc_low for k in ("bedroom", "private bath", "dorm room", "personal quarters", "safehouse")):
        return {"witness_spotted": False, "private": True}

    # Candidate witness extraction
    stage_npcs = session.get("pre_turn_stage_npcs") or session.get("current_stage_npcs") or session.get("current_npcs") or []
    candidate_witnesses = []
    for n in stage_npcs:
        n_name = (n.get("name") if isinstance(n, dict) else str(n)).strip()
        is_partner_in_act = (n_name.lower() == target_npc.lower()) and not is_public_exposure
        if n_name and not is_partner_in_act and n_name.lower() != player_name.lower():
            candidate_witnesses.append(n_name)

    if is_public_exposure:
        event_kind = "scandal" if exposure_type in ("fully_naked", "bottomless") else "indecency"
    elif is_romantic_or_intimate:
        event_kind = "intimate"
        if session_id and target_npc:
            try:
                import mechanics.social.relationship_graph as rg
                prim_partner = rg.get_current_partner(session_id, "player")
                tgt_canon = rg.canonical_person_key(target_npc)
                if prim_partner and prim_partner.get("person_key") and prim_partner.get("person_key") != tgt_canon:
                    event_kind = "secret_affair"
            except Exception:
                pass
    else:
        event_kind = "illicit"

    is_discreet_spot = is_discreet_venue(loc_display, curr_node_id, session_id=session_id)
    witness_name = None
    if candidate_witnesses:
        witness_name = candidate_witnesses[0]
    elif is_public_exposure:
        witness_name = "Shocked Bystander"
    elif is_discreet_spot:
        # 8% passerby thrill risk in secluded `is_discreet` spots
        if random.random() < 0.08:
            witness_name = "Passerby Student"
    elif any(k in loc_low for k in (
        "hallway", "corridor", "courtyard", "cafeteria", "plaza", "city square",
        "street", "quad", "library", "park", "campus", "classroom", "beach", "pier", "lookout",
    )):
        # 35% passerby chance in open public areas
        if random.random() < 0.35:
            witness_name = "Passerby Student"

    if not witness_name:
        return {"witness_spotted": False}

    post = queue_witness_gossip_post(
        session_id=session_id,
        witness_name=witness_name,
        player_name=player_name,
        partner_name=target_npc or "Someone",
        location_display=loc_display,
        event_kind=event_kind,
    )

    affair_confrontation_triggered = False
    if event_kind == "secret_affair" and session_id:
        try:
            import mechanics.social.relationship_graph as rg
            prim_partner = rg.get_current_partner(session_id, "player")
            if prim_partner and prim_partner.get("person_key"):
                prim_key = str(prim_partner["person_key"])
                prim_disp = str(prim_partner.get("display_name") or prim_key.replace("_", " ").title()).strip()
                prim_npc_id = rg.resolve_npc_id_for_person(session_id, prim_key) or prim_key
                soc_state = db.get_phone_social_state(session_id) or {}
                leak_counts = dict(soc_state.get("affair_leak_counts") or {})
                new_leaks = int(leak_counts.get(prim_key, 0)) + 1
                leak_counts[prim_key] = new_leaks
                soc_state["affair_leak_counts"] = leak_counts
                db.update_phone_social_state(session_id, soc_state)
                if new_leaks >= 2 and not (soc_state.get("affair_confronted") or {}).get(prim_key):
                    confronted_map = dict(soc_state.get("affair_confronted") or {})
                    confronted_map[prim_key] = True
                    soc_state["affair_confronted"] = confronted_map
                    db.update_phone_social_state(session_id, soc_state)
                    affair_confrontation_triggered = True
                    db.update_relationship_score(session_id, prim_npc_id, -25)
                    rg.adjust_closeness(session_id, "player", prim_key, delta=-25)
                    if hasattr(db, "save_phone_message"):
                        db.save_phone_message(
                            session_id=session_id,
                            contact_npc_id=prim_npc_id,
                            sender="npc",
                            message=f"People keep sending me posts about you and {target_npc or 'someone else'}. What is going on between you two?! We need to talk.",
                            intent="confrontation",
                        )
                    if hasattr(db, "add_npc_memory"):
                        db.add_npc_memory(
                            session_id=session_id,
                            npc_name=prim_disp,
                            turn_index=len(session.get("history") or []) + 1,
                            memory_fact=f"Saw multiple #SecretAffair rumors linking {player_name} and {target_npc} and sent an angry confrontation message.",
                            importance=5,
                            emotional_tone="angry",
                            open_thread="affair_suspicion_confrontation",
                        )
        except Exception:
            pass

    directive = (
        f"[STAGE DIRECTION: PUBLIC INDECENCY]: {player_name} is visibly {exposure_type} at {loc_display or 'the scene'}! {witness_name} and nearby bystanders are startled and scandalized."
        if is_public_exposure
        else f"[STAGE DIRECTION — WITNESS REACTION]: {witness_name} spotted the interaction at {loc_display or 'the scene'}! Briefly note their startled glance or reaction."
    )

    return {
        "witness_spotted": True,
        "witness_name": witness_name,
        "event_kind": event_kind,
        "affair_confrontation_triggered": affair_confrontation_triggered,
        "post": post,
        "directive": directive,
    }

