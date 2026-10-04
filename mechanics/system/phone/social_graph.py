from __future__ import annotations
"""
Social graph connections, profile lookup, friend request resolution, and peer discovery for Hikayat.
"""
import random
import db
from skill_check import resolve_check


def get_mutual_friends_and_ties(session_id: int, user_id: int, target_dict: dict) -> dict:
    """Calculates mutual contacts, shared clubs, and sibling connections with a target NPC."""
    char = db.get_character(user_id)
    contacts = db.get_contacts(session_id, character_id=char.get("id", 0)) if char else []
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
        contacts = db.get_contacts(session_id, character_id=char.get("id", 0)) if char else []
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

    # Check eligibility (faculty/staff/adults cannot be contacts in high school scenarios)
    from mechanics import relationships
    grade_val = target_rec.get("grade", "")
    if str(grade_val).strip().lower() == "faculty":
        is_eligible = False
    elif str(grade_val).strip().lower() in ("freshman", "sophomore", "junior", "senior", "grade 9", "grade 10", "grade 11", "grade 12"):
        is_eligible = True
    else:
        is_eligible = relationships.is_contact_eligible(
            name=name, role=role, description=desc, scenario=scen_key, session_id=session_id
        )

    contact_npc_id = str(target_rec.get("npc_id") or name).strip().lower().replace(" ", "_").replace(".", "")
    existing_contact = db.get_contact(session_id, contact_npc_id, character_id=char.get("id", 0)) if char else None

    # Check cooldown
    state = db.get_phone_social_state(session_id) or {}
    cds = state.get("friend_request_cooldowns", {})
    expire_turn = cds.get(contact_npc_id, 0)
    turn_count = len(session.get("history", [])) if session else 0
    turns_left = max(0, expire_turn - turn_count)

    ties = get_mutual_friends_and_ties(session_id, user_id, target_rec)

    clean_handle = "@" + name.lower().replace(" ", "_").replace(".", "").replace("'", "")[:14]
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
        "is_already_contact": bool(existing_contact),
        "cooldown_turns_left": turns_left,
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
            "message": f"🔒 **Account Restricted:** Faculty and staff accounts cannot be added to student friend circles under Academy digital policy."
        }

    if profile.get("is_already_contact"):
        return {
            "accepted": True,
            "already_friend": True,
            "message": f"👥 **{name}** is already in your Contacts!"
        }

    if profile.get("cooldown_turns_left", 0) > 0:
        return {
            "accepted": False,
            "on_cooldown": True,
            "turns_left": profile["cooldown_turns_left"],
            "message": f"⏳ **Recent Request Pending/Declined:** {name} hasn't responded. You can try sending another request in **{profile['cooldown_turns_left']} turn(s)**."
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
        # Hydrate contact
        scen_key = session.get("scenario", "fantasy")
        if "school" in scen_key or "high_school" in scen_key:
            from mechanics.social.school_roster import hydrate_school_character
            hydrate_school_character(session_id, profile["raw_record"])
        else:
            db.upsert_contact(
                session_id=session_id,
                npc_id=npc_id,
                name=name,
                character_id=char.get("id", 0) if char else 0,
                delta_score=5,
                basic_info={
                    "role": profile.get("role", "Contact"),
                    "description": profile.get("personality", "")
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
        # Set 5-turn cooldown
        cds[npc_id] = turn_count + 5
        db.update_phone_social_state(session_id, state)
        profile["cooldown_turns_left"] = 5
        return {
            "accepted": False,
            "check": check,
            "bonus": bonus,
            "mod_reasons": mod_reasons,
            "turns_cooldown": 5,
            "message": f"❌ **Request Left on Delivered:**\n**{name}** didn't accept your friend request. You can send another request in 5 turns."
        }


def discover_suggested_peer(session_id: int, user_id: int) -> dict:
    """Discovers an un-contacted student peer or dynamically generates a new one."""
    char = db.get_character(user_id)
    contacts = db.get_contacts(session_id, character_id=char.get("id", 0)) if char else []
    contact_ids = {c["npc_id"].lower() for c in contacts}

    roster = db.get_school_roster(session_id)
    eligible_uncontacted = [
        r for r in roster
        if r.get("grade") != "Faculty" and r["npc_id"].lower() not in contact_ids
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
