from .constants import *
from mechanics.world.locations import *
from mechanics.social.persona import *
from game_engine.turn_context import TurnContext
import json
import logging
import game_engine
from models.llm_schemas import TurnOutcome, ActionClassification, OpeningScene

def _compute_dialogue_intent(session: dict, actions: list) -> tuple[list[str], bool]:
    """Extracted Phase 2A Builder for Dialogue Partner Intents."""
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.world.locations.core import extract_movement_destination, get_primary_location_name, get_zone_location_name

    current_partners = get_session_dialogue_partners(session)

    new_partners = list(current_partners)

    has_exited_convo = False



    from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext

    for a in actions:

        if isinstance(a, dict):
            label = (a.get("label") or "").strip()
            stat = a.get("stat")
        else:
            label = str(a).strip()
            stat = "NONE"

        label_low = game_engine._norm_dialogue_name(label)



        cur_pres_npcs = [game_engine._get_npc_name(n) for n in (session.get("current_npcs") or []) if n]

        ctx_action = IntentContext(

            dialogue_partner=session.get("dialogue_partner") or (current_partners[0] if current_partners else ""),

            dialogue_partners=current_partners,

            current_zone=get_zone_location_name(session.get("current_location", "")),

            present_npcs=cur_pres_npcs,

            scenario=session.get("scenario", "default")

        )

        parsed_action = classify_action_intent(label, ctx_action)



        is_departing_venue = False
        if parsed_action.category == IntentCategory.MOVEMENT:
            curr_loc = session.get("current_location", "")
            curr_zone = get_zone_location_name(curr_loc)
            scen_k = session.get("scenario", "default")
            action_dest = extract_movement_destination(label, session.get("id"), current_zone=curr_zone, scen_key=scen_k)
            if action_dest:
                dest_z, dest_p = action_dest
                curr_p = get_primary_location_name(curr_loc)
                if curr_p and dest_p and curr_p.lower() != dest_p.lower():
                    is_departing_venue = True
            elif parsed_action.metadata.get("is_room_exit"):
                # If room exit but accompanied by partner, not a venue departure
                is_acc = bool(parsed_action.metadata.get("is_accompanied"))
                for dp in current_partners:
                    if dp.lower() in label_low or (len(dp.split()[0]) >= 3 and dp.split()[0].lower() in label_low):
                        is_acc = True
                        break
                if not is_acc:
                    is_departing_venue = True

        # Check for conversational exit: unified intent engine
        is_explicit_exit = parsed_action.category == IntentCategory.DIALOGUE_EXIT
        is_departure_exit = (parsed_action.category == IntentCategory.MOVEMENT and is_departing_venue and not parsed_action.metadata.get("is_accompanied"))

        if is_explicit_exit:
            has_exited_convo = True
            new_partners = []
        elif is_departure_exit:
            # Player departed from the venue without an accompanied partner; old partners are left behind
            new_partners = []
            has_exited_convo = bool(current_partners)
            # Check if this departure action was taken specifically to meet a new NPC at the destination
            # e.g. "Travel to the Gym & Fieldhouse to meet Sofia Anderson"
            from mechanics.world.mobility import is_rendezvous_target
            if session.get("id"):
                import db
                try:
                    roster = db.get_school_roster(session["id"])
                    contacts = db.get_contacts(session["id"])
                    cand_names = [m.get("name", "") for m in roster] + [c.get("name", "") for c in contacts]
                    for cn in cand_names:
                        if cn and is_rendezvous_target(cn, actions=actions, session_id=session.get("id")):
                            new_partners = [cn]
                            break
                except Exception:
                    pass

            if not new_partners:
                for m in re.finditer(r"\bmeet\s+(?:with\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b", label):
                    cand_target = m.group(1).strip()
                    if is_rendezvous_target(cand_target, actions=actions, session_id=session.get("id")):
                        new_partners = [cand_target]
                        break
        else:

            # Check if action initiates or continues dialogue with one or more NPCs

            detected = []

            if parsed_action.target_entity and parsed_action.category in (

                IntentCategory.DIALOGUE_INIT,

                IntentCategory.SOCIAL_INVITE,

                IntentCategory.ROMANTIC_CONFESSION,

                IntentCategory.INTIMATE_ACT,

                IntentCategory.AFFECTION_TOUCH,

                IntentCategory.GIFT_OFFER,

            ):

                for npc in (session.get("current_npcs") or []):

                    n_name = game_engine._get_npc_name(npc)

                    if n_name and n_name.lower() != "none" and (n_name.lower() == parsed_action.target_entity.lower() or parsed_action.target_entity.lower() in n_name.lower()):

                        detected.append(n_name)

                        break

                if not detected and session.get("id"):
                    import db
                    try:
                        roster = db.get_school_roster(session["id"])
                        tgt_low = parsed_action.target_entity.lower().strip()
                        for member in roster:
                            m_name = member.get("name", "")
                            m_low = m_name.lower().strip()
                            m_first = m_low.split()[0] if m_low else ""
                            if m_name and (tgt_low == m_low or tgt_low == m_first or f" {tgt_low} " in f" {m_low} " or m_low.startswith(tgt_low)):
                                detected.append(m_name)
                                break
                    except Exception:
                        pass

                if not detected and parsed_action.target_entity:
                    tgt = parsed_action.target_entity.strip()
                    import namegen
                    if (
                        tgt not in ("Merchant", "Scene", "Shadows", "Surroundings", "Contact", "Phone")
                        and namegen.is_valid_entity_name(tgt)
                        and not namegen.is_collective_entity_name(tgt)
                        and not namegen.is_generic_role_name(tgt)
                    ):
                        detected.append(tgt)



            if not detected:

                title_words = {

                    "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs",

                    "druid", "scholar", "guardian", "student", "council", "president", "vice", "secretary",

                    "representative", "officer", "member", "guildmaster", "archivist", "warden", "guard",

                    "patron", "shopkeeper", "innkeeper", "headmaster", "dean", "professor", "teacher"

                }

                for npc in (session.get("current_npcs") or []):

                    n_name = game_engine._get_npc_name(npc)

                    if not n_name or n_name.lower() == "none":

                        continue

                    n_low = game_engine._norm_dialogue_name(n_name)

                    n_tokens = [t for t in n_low.split() if len(t) > 2 and t not in title_words]

                    if not n_tokens and len(n_low) > 2:

                        n_tokens = [n_low]

                    if n_low in label_low or any(t in label_low for t in n_tokens):

                        detected.append(n_name)

                    elif any(verb in label_low for verb in ["talk", "speak", "question", "ask", "inquire", "consult", "greet", "approach", "show", "address", "join", "converse", "tell", "explain", "appeal", "whisper", "confer", "discuss"]):

                        if n_low in label_low or any(t in label_low for t in n_tokens):

                            detected.append(n_name)

                

                # If addressing a collective group (e.g. "council", "committee", "board")

                if not detected and any(group_kw in label_low for group_kw in ["council", "committee", "board", "faculty", "guild", "elders", "everyone", "all of them", "both of them"]):

                    for npc in (session.get("current_npcs") or []):

                        n_role = str(npc.get("role", "") if isinstance(npc, dict) else "").lower()

                        if any(group_kw in n_role for group_kw in ["council", "committee", "board", "faculty", "guild", "elder"]):

                            n_name = game_engine._get_npc_name(npc)

                            if n_name and n_name.lower() != "none" and n_name not in detected:
                                detected.append(n_name)

            if not detected and session.get("id"):
                import db
                try:
                    roster = db.get_school_roster(session["id"])
                    for member in roster:
                        m_name = member.get("name", "")
                        if not m_name:
                            continue
                        m_low = m_name.lower().strip()
                        m_first = m_low.split()[0] if m_low else ""
                        if m_low in label_low or (len(m_first) >= 3 and f" {m_first} " in f" {label_low} "):
                            detected.append(m_name)
                            break
                except Exception:
                    pass

            if detected:
                if len(current_partners) >= 2:
                    def _is_in_current_group(det_name: str) -> bool:
                        d_low = game_engine._norm_dialogue_name(det_name)
                        d_first = d_low.split()[0] if d_low else ""
                        for cp in current_partners:
                            cp_low = game_engine._norm_dialogue_name(cp)
                            cp_first = cp_low.split()[0] if cp_low else ""
                            if d_low and cp_low and (
                                d_low == cp_low
                                or d_low in cp_low
                                or cp_low in d_low
                                or (len(d_first) >= 3 and d_first == cp_first)
                            ):
                                return True
                        return False

                    if all(_is_in_current_group(d) for d in detected):
                        new_partners = list(current_partners)
                    else:
                        new_partners = detected
                else:
                    new_partners = detected

    return new_partners, has_exited_convo

def _build_dialogue_prompt_block(session: dict, ctx, new_partners: list, party: list, actions: list) -> str:
    """Extracted Phase 2A Builder for Dialogue Partner Prompts."""
    from mechanics.world.locations.core import extract_movement_destination, get_zone_location_name, get_primary_location_name
    from mechanics.combat import is_in_combat
    import db, game_engine, scenario_data
    scen_key = session.get('scenario', 'fantasy')
    dialogue_prompt_block = ""

    if is_in_combat(session):
        pres_npcs = [
            game_engine._get_npc_name(n)
            for n in (session.get("current_npcs") or [])
            if n and game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
        ]
        if pres_npcs:
            npc_str = ", ".join(pres_npcs)
            verb = "are" if len(pres_npcs) > 1 else "is"
            return (
                f"PRESENT CHARACTERS IN COMBAT SCENE ({npc_str}):\n"
                f"- {npc_str} {verb} physically present in the scene during this enemy encounter.\n"
                f"- You MUST include {npc_str} in `npcs_present` and `present_named_characters`, and narrate how {npc_str} and the player react to the hostile enemies.\n\n"
            )
        return ""

    if new_partners:

        partner_str = ", ".join(new_partners)

        party_npcs = ctx.party_npcs if session.get("id") else []

        human_count = len(session.get("turn_order", [])) if session else 1

        _outer_scen_k = session.get("scenario", "fantasy") if session else "fantasy"
        is_nsfw = is_nsfw_scenario(_outer_scen_k)
        _outer_phys = (db.get_session_physical_state(session.get("id", 0)) if session and session.get("id") else None) or (session.get("physical_state", {}) if session else {})
        _outer_ic = str(_outer_phys.get("intimate_contact", "")).lower() if isinstance(_outer_phys, dict) else ""
        from mechanics.social.physical_state import (
            is_erotic_intimate_contact as _is_erotic_ic_outer,
            detect_intimate_disengagement as _detect_disengage_outer,
        )
        from mechanics.social.intimate_excitement import classify_intimate_act as _classify_dlg_act
        _is_disengaging_dlg = _detect_disengage_outer(actions) if actions else False
        _dlg_act_text = " ".join(
            str(a.get("label", "") if isinstance(a, dict) else a)
            for a in (actions or [])
        )
        _dlg_act_succeeded = True
        for _da in (actions or []):
            if isinstance(_da, dict):
                _dchk = _da.get("check")
                _dtier = getattr(_dchk, "tier", None) or (_dchk.get("tier") if isinstance(_dchk, dict) else None)
                if _da.get("success") is False or _dtier in ("fail", "crit_fail"):
                    _dlg_act_succeeded = False
                    break
        _in_active_erotic_dlg = bool(
            is_nsfw
            and not _is_disengaging_dlg
            and (
                _is_erotic_ic_outer(_outer_ic)
                or (
                    _dlg_act_succeeded
                    and _dlg_act_text
                    and any(
                        _classify_dlg_act(_dlg_act_text, intimate_contact_str=_outer_ic, partner_name=_dp_cand).get("act_type", "none") not in ("none", "foreplay_nongenital")
                        for _dp_cand in (new_partners or ["Partner"])
                    )
                )
            )
        )

        recruitment_prompt = ""

        if (
            not _in_active_erotic_dlg
            and scenario_data.is_mechanic_enabled(session.get("scenario", "fantasy"), "tactical_combat")
            and (human_count + len(party_npcs) < 4)
        ):

            for partner in new_partners:

                cd = db.get_recruitment_cooldown(session["id"], partner) if session.get("id") else 0

                if cd == 0 and not any(p.get("name", "").lower() == partner.lower() for p in party_npcs):

                    recruitment_prompt += f"  * 🤝 [CHA] Party Recruitment check: 'Invite {partner} to join your party as a permanent companion' (Offer this skill check choice when talking to friendly/allied NPCs to recruit them).\n"



        multi_partner_note = ""

        if len(new_partners) > 1:

            multi_partner_note = (

                f"- MULTI-CHARACTER GROUP CONVERSATION DIRECTIVE ({partner_str}):\n"

                f"  * The conversation actively involves multiple participants simultaneously.\n"

                f"  * Provide diverse choices in `next_choices`:\n"

                f"    (a) Choices addressing specific individual participants directly (e.g. addressing {new_partners[0]}'s argument vs {new_partners[1]}'s stance).\n"

                f"    (b) Choices addressing the entire group/council together.\n"

                f"    (c) Stances that mediate, compromise, or find a strategic angle between differing viewpoints.\n"

            )



        # Use canonical count_dialogue_stall_turns helper from npcs.py (single source of truth,
        # full 27-verb registry, replacing the previous 21-verb _stall_verbs inline duplicate).
        from game_engine.npcs import count_dialogue_stall_turns as _count_stall, format_dialogue_stall_directive as _fmt_stall
        _stall_count = _count_stall(session.get("history") or [])

        # Determine if any partner is a specific quest investigation target, bounty contact, or hostile confrontation
        is_quest_interrogation = False
        active_bounty_contact = None  # tuple: (partner_name, bounty_dict, active_waypoint_dict)
        has_phone_meetup = False
        contact_context_lines = []
        contacts = ctx.contacts if hasattr(ctx, "contacts") else []
        if session.get("id"):
            session_id_val = session["id"]
            partner_names_lower = [p.lower().strip() for p in new_partners]

            # Single DB round-trip for appointments (reused across bounty & quest checks below)
            appts = ctx.pending_appointments + ctx.arrived_appointments
            for appt in appts:
                a_name = appt.get("npc_name", "").lower().strip()
                if any(pn in a_name or a_name in pn for pn in partner_names_lower):
                    has_phone_meetup = True
                    break

            if not has_phone_meetup and not _in_active_erotic_dlg:
                # 1. Check for Active Bounty Contact

                active_bounties_list = [
                    q for q in db.get_session_quests(session_id_val, status="Active")
                    if not q.get("is_story_quest") and q.get("quest_type") not in ("Story Quest", "Main Quest")
                ]
                for bnt in active_bounties_list:
                    qid = bnt.get("quest_id", "")
                    bnt_wps = db.get_quest_waypoints(session_id_val, qid, sub_obj_id=None) if qid else []
                    act_wp = db.get_active_waypoint(session_id_val, qid, sub_obj_id=None) if qid else None
                    bnt_text = f"{bnt.get('title', '')} {bnt.get('objective', '')}".lower()
                    for pn in partner_names_lower:
                        pn_matched = False
                        for w in bnt_wps:
                            t_npc = str(w.get("target_npc", "")).lower().strip()
                            if t_npc and (pn in t_npc or t_npc in pn):
                                pn_matched = True
                                break
                        if pn in bnt_text:
                            pn_matched = True
                        if pn_matched:
                            active_bounty_contact = (pn, bnt, act_wp)
                            break
                    if active_bounty_contact:
                        break

                # 2. Check for Story Quest Interrogation / Investigation
                # Single DB round-trip for active waypoints
                if not active_bounty_contact:
                    active_wps = ctx.active_waypoints
                    for wp in active_wps:
                        t_npc = str(wp.get("target_npc", "")).lower().strip()
                        if t_npc and any(pn in t_npc or t_npc in pn for pn in partner_names_lower):
                            is_quest_interrogation = True
                            break
                        wp_text = f"{wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')}".lower()
                        for pn in partner_names_lower:
                            if pn in wp_text:
                                is_quest_interrogation = True
                                break
                        if is_quest_interrogation:
                            break

            for p in new_partners:

                p_low = p.lower().strip()

                matched_c = next((

                    c for c in contacts

                    if c.get("name", "").lower().strip() == p_low or

                    c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")

                ), None)

                if matched_c:

                    score = matched_c.get("relationship_score", 0)

                    track = matched_c.get("track", "platonic")

                    basic = matched_c.get("basic_info") or {}

                    role = basic.get("role", "")

                    traits = matched_c.get("unlocked_traits") or []

                    prefs = matched_c.get("preferences") or []

                    appr = matched_c.get("appearance") or {}

                    mannerisms = matched_c.get("mannerisms") or basic.get("mannerisms") or ""



                    details = []

                    if role and str(role).lower() != "none":

                        details.append(f"Role: {role}")

                    faction_k = basic.get("faction") or basic.get("faction_affiliation") or basic.get("club") or matched_c.get("faction")

                    if faction_k and str(faction_k).lower() != "none":

                        details.append(f"Faction: {faction_k}")

                    details.append(f"Affinity: {score}/100 ({track.capitalize()} Track)")

                    effective_traits = list(traits or [])

                    if not effective_traits:

                        from mechanics.combat.traits import assign_npc_traits

                        effective_traits = assign_npc_traits(seed_str=p, count=3, role=role or "", race=matched_c.get("race", ""))

                    if effective_traits:

                        details.append(f"Persona Traits: {', '.join(effective_traits)}")



                    from mechanics.social.persona import categorize_likes_and_dislikes, format_mannerisms_list

                    likes_l, dislikes_l = categorize_likes_and_dislikes(

                        prefs,

                        traits=effective_traits,

                        role=role or "",

                        race=matched_c.get("race", ""),

                        desc=basic.get("description", "")

                    )

                    from mechanics.social.relationships import get_unlocked_info_level

                    scen_k = session.get("scenario", "fantasy")

                    is_nsfw = is_nsfw_scenario(scen_k)



                    info_lvl = get_unlocked_info_level(score)

                    rev_flags = dict(matched_c.get("revealed_flags", {}))

                    if isinstance(appr, dict):

                        for k_f in (
                            "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
                            "demeanor_revealed", "dynamic_revealed", "openness_revealed",
                            "sensitive_spots_revealed", "turn_ons_revealed", "fetishes_revealed",
                            "act_preferences_revealed", "underwear_revealed", "mannerisms_revealed", "all_revealed"
                        ):

                            if appr.get(k_f):

                                rev_flags[k_f] = True



                    if likes_l:

                        details.append(f"Likes & Desires: {', '.join(likes_l)}")

                    if dislikes_l:

                        details.append(f"Dislikes & Aversions: {', '.join(dislikes_l)}")

                    details.append(f"[PREFERENCE SYNERGY: Appealing to {p}'s likes grants positive affinity (delta_score: +2 to +4); triggering {p}'s dislikes or offending them causes annoyance and negative affinity (delta_score: -1 to -4).]")





                    mannerisms_list = format_mannerisms_list(mannerisms, race=matched_c.get("race", ""), desc=basic.get("description", ""), traits=effective_traits, role=role or "")

                    if mannerisms_list:

                        details.append(f"Mannerisms & Habits: {'; '.join(mannerisms_list)}")

                    elif mannerisms:

                        details.append(f"Mannerisms & Speech Quirks: {mannerisms}")



                    distinctive = appr.get("distinctive_features")

                    if distinctive and str(distinctive).lower() not in ("none", "unknown"):

                        details.append(f"Features: {distinctive}")

                    intimate_dem = appr.get("intimate_demeanor")
                    if intimate_dem and str(intimate_dem).lower() not in ("none", "unknown"):
                        details.append(f"Intimate Demeanor: {intimate_dem}")

                    intimate_dyn = appr.get("intimate_dynamic") or appr.get("dynamic")
                    if intimate_dyn and str(intimate_dyn).lower() not in ("none", "unknown"):
                        details.append(f"Intimate Dynamic: {intimate_dyn}")

                    erotic_open = appr.get("erotic_openness") or appr.get("openness")
                    if erotic_open and str(erotic_open).lower() not in ("none", "unknown"):
                        details.append(f"Erotic Openness: {erotic_open}")



                    intimate_unlocked = (info_lvl >= 3) or rev_flags.get("intimate_revealed") or rev_flags.get("all_revealed")
                    sens_unlocked = intimate_unlocked or rev_flags.get("sensitive_spots_revealed") or appr.get("sensitive_spots_revealed")
                    turns_unlocked = intimate_unlocked or rev_flags.get("turn_ons_revealed") or appr.get("turn_ons_revealed")

                    if is_nsfw and (intimate_unlocked or sens_unlocked or turns_unlocked):

                        from mechanics.social.persona import sanitize_sensitive_spots_for_species
                        from mechanics.social.persona.intimacy.appearance import clean_attribute_list_string

                        sens = sanitize_sensitive_spots_for_species(clean_attribute_list_string(appr.get("sensitive_spots")) or "", race=matched_c.get("race", ""), distinctive_features=appr.get("distinctive_features", ""))

                        if sens_unlocked and sens and str(sens).lower() not in ("none", "unknown"):
                            details.append(f"Sensitive Spots: {sens}")

                        turns = sanitize_sensitive_spots_for_species(clean_attribute_list_string(appr.get("turn_ons")) or "", race=matched_c.get("race", ""), distinctive_features=appr.get("distinctive_features", ""))
                        if turns_unlocked and turns and str(turns).lower() not in ("none", "unknown"):
                            details.append(f"Turn-Ons: {turns}")

                        fet = clean_attribute_list_string(appr.get("fetishes"))
                        if intimate_unlocked and fet and str(fet).lower() not in ("none", "unknown", "none (vanilla)"):
                            details.append(f"Kinks: {fet}")

                        if intimate_unlocked:
                            ic_exp = appr.get("intercourse_experience")
                            or_exp = appr.get("oral_experience")
                            if ic_exp and str(ic_exp).lower() not in ("none", "unknown"):
                                details.append(f"Intercourse Experience: {ic_exp}")

                            if or_exp and str(or_exp).lower() not in ("none", "unknown"):
                                details.append(f"Oral Experience: {or_exp}")

                            man_exp = appr.get("manual_experience")
                            if man_exp and str(man_exp).lower() not in ("none", "unknown"):
                                details.append(f"Manual Experience: {man_exp}")

                        known_triggers = []
                        if turns and str(turns).lower() not in ("none", "unknown"):
                            known_triggers.append(f"turn-ons: {turns}")
                        elif sens and str(sens).lower() not in ("none", "unknown"):
                            known_triggers.append(f"sensitive spots: {sens}")

                        if known_triggers or intimate_dyn:
                            trig_str = "; ".join(known_triggers) if known_triggers else "their desires"
                            dyn_str = f", dynamic: {intimate_dyn}" if intimate_dyn else ""
                            details.append(f"INTIMATE SYNERGY: During intimate scenes, shape {p}'s dialogue and actions using their {trig_str}{dyn_str} (+2 to +4 bonus to check resolution)")



                    from mechanics.social.genealogy import build_topic_aware_npc_context

                    topic_context = build_topic_aware_npc_context(

                        matched_c,

                        actions=actions,

                        session_history=session.get("history", []),

                        scenario=session.get("scenario", "fantasy")

                    )



                    line = f"  * {p}: " + " | ".join(details)

                    if topic_context:

                        line += "\n" + topic_context

                    contact_context_lines.append(line)



        contact_info_block = ""

        if contact_context_lines:

            contact_info_block = "- KNOWN CHARACTER CONTEXT & RELATIONSHIP:\n" + "\n".join(contact_context_lines) + "\n"

        recent_phone_blocks = []
        if session.get("id"):
            session_id_val = session["id"]
            contacts = ctx.contacts
            for p in new_partners:
                p_low = p.lower().strip()
                matched_c = next((
                    c for c in contacts
                    if c.get("name", "").lower().strip() == p_low or
                    c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")
                ), None)
                if matched_c:
                    c_npc_id = matched_c.get("npc_id", p_low.replace(" ", "_"))
                    c_basic = matched_c.get("basic_info") if isinstance(matched_c.get("basic_info"), dict) else {}
                    try:
                        last_in_person_ts = float(c_basic.get("last_in_person_ts") or 0)
                    except (ValueError, TypeError):
                        last_in_person_ts = 0.0

                    # Fetch recent phone messages (up to 4)
                    raw_phone_msgs = db.get_phone_messages(session_id_val, c_npc_id, limit=4)
                    if raw_phone_msgs:
                        def _get_ts(msg_item):
                            try:
                                return float(msg_item.get("timestamp") or 0)
                            except (ValueError, TypeError):
                                return 0.0

                        # Determine fresh messages: sent after the last in-person interaction
                        fresh_msgs = [m for m in raw_phone_msgs if _get_ts(m) > last_in_person_ts]
                        # If appointment is active or fresh messages exist, present them
                        msgs_to_show = fresh_msgs if fresh_msgs else (raw_phone_msgs[-2:] if has_phone_meetup else [])

                        if msgs_to_show:
                            msg_lines = []
                            has_media_exchange = False
                            has_rendezvous_plan = False
                            for m in msgs_to_show:
                                snd = "Player" if m.get("sender") == "player" else p
                                txt = m.get("message", "")
                                if any(k in txt for k in ("[Attached Intimate", "[Attached Photo", "[Attached Video", "Video:", "Photo:")):
                                    has_media_exchange = True
                                if any(k in txt.lower() for k in ("meet", "meetup", "music room", "rendezvous", "gate", "see you")):
                                    has_rendezvous_plan = True
                                msg_lines.append(f"    • {snd}: \"{txt}\"")

                            callback_hints = []
                            if has_media_exchange:
                                callback_hints.append(
                                    f"  * EXCHANGED MEDIA CALLBACK (PROACTIVE): You and the player recently exchanged photos or videos over text. "
                                    f"Naturally react to this in your initial dialogue, greeting, or body language (e.g. blushing, playful teasing, coy smirk, or asking what they thought of it)!"
                                )
                            if has_rendezvous_plan:
                                callback_hints.append(
                                    f"  * AGREED MEETUP CONTINUITY: You two planned this meetup over text. Seamlessly connect your greeting to the plans you made in Direct Messages."
                                )

                            hint_text = "\n".join(callback_hints) + "\n" if callback_hints else ""
                            recent_phone_blocks.append(
                                f"  [RECENT MOBILE TEXTS & EXCHANGES WITH {p}]:\n"
                                + "\n".join(msg_lines) + "\n"
                                f"  * DIRECTIVE: These messages were exchanged over the phone just prior to meeting face-to-face. "
                                f"Maintain continuous conversational thread! The character naturally remembers what was discussed and should react accordingly.\n"
                                + hint_text
                            )

        recent_phone_section = "\n".join(recent_phone_blocks) + "\n" if recent_phone_blocks else ""

        trait_behavioral_blocks = []

        if session.get("id"):

            session_id_val = session["id"]

            contacts = ctx.contacts

            for p in new_partners:

                p_low = p.lower().strip()

                matched_c = next((

                    c for c in contacts

                    if c.get("name", "").lower().strip() == p_low or

                    c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")

                ), None)

                if matched_c:

                    c_traits = matched_c.get("unlocked_traits") or matched_c.get("traits") or []

                    if c_traits:

                        from mechanics.combat.traits import format_trait_behavioral_prompt

                        t_block = format_trait_behavioral_prompt(c_traits, partner_name=p)

                        if t_block:

                            trait_behavioral_blocks.append(t_block)

                    demeanor_val = str(matched_c.get("demeanor") or "").lower()
                    persona_val = str(matched_c.get("persona") or "").lower()
                    traits_all = [str(t).lower() for t in (matched_c.get("traits") or [])] + [str(t).lower() for t in (matched_c.get("unlocked_traits") or [])]
                    appr_temp = matched_c.get("appearance", {}) if isinstance(matched_c.get("appearance"), dict) else {}
                    open_temp = str(appr_temp.get("erotic_openness") or appr_temp.get("openness") or "").lower()

                    is_shameless = any(k in demeanor_val or k in persona_val or any(k in t for t in traits_all) or k in open_temp for k in ("shameless", "lewd", "provocative", "seductive", "hedonist", "nympho", "lascivious", "pervert"))
                    is_bold = any(k in demeanor_val or k in persona_val or any(k in t for t in traits_all) or k in open_temp for k in ("bold", "flirtatious", "uninhibited", "forward"))

                    if is_shameless:
                        trait_behavioral_blocks.append(
                            f"  * ⚡ SHAMELESS / LEWD SPOKEN DIALOGUE DIRECTIVE ({p}): "
                            f"{p} has an unapologetically shameless and lewd disposition. In spoken dialogue, THEY HAVE NO VERBAL FILTER! "
                            f"They freely make unsolicited sexual innuendos, playfully dirty remarks, cheeky double entendres, and provocative flirtations even during regular conversation and at early affinity. "
                            f"DO NOT sanitize their speech or force them into bashful modesty!"
                        )
                    elif is_bold:
                        trait_behavioral_blocks.append(
                            f"  * ⚡ BOLD / UNINHIBITED SPOKEN DIALOGUE DIRECTIVE ({p}): "
                            f"{p} is bold, confident, and uninhibited. In spoken dialogue, they speak their mind openly, flirt proactively, and meet romantic or suggestive topics without stammering or awkward shame."
                        )



        trait_behavioral_section = "\n".join(trait_behavioral_blocks) + "\n" if trait_behavioral_blocks else ""



        intimate_dynamic_openness_blocks = []

        if is_nsfw and session.get("id"):

            session_id_val = session["id"]

            contacts = ctx.contacts

            curr_phys = (db.get_session_physical_state(session.get("id", 0)) if session.get("id") else None) or session.get("physical_state", {})
            from mechanics.social.physical_state import is_erotic_intimate_contact, _match_actor_key
            from mechanics.social.intimate_excitement import is_in_refractory_cooldown, infer_last_act_from_state

            for p in new_partners:

                p_low = p.lower().strip()
                p_first = (p_low.split() or [""])[0]

                matched_c = next((
                    c for c in contacts
                    if c.get("name", "").lower().strip() == p_low or
                    c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")
                ), None)
                if not matched_c and len(p_first) >= 3:
                    matched_c = next((
                        c for c in contacts
                        if (c.get("name", "").lower().strip().split() or [""])[0] == p_first
                    ), None)
                if not matched_c:
                    matched_c = next((
                        n for n in (session.get("current_npcs") or [])
                        if isinstance(n, dict) and n.get("name", "").lower().strip() == p_low
                    ), None)
                if not matched_c and len(p_first) >= 3:
                    matched_c = next((
                        n for n in (session.get("current_npcs") or [])
                        if isinstance(n, dict) and (n.get("name", "").lower().strip().split() or [""])[0] == p_first
                    ), None)

                if matched_c:

                    appr_c = matched_c.get("appearance", {})

                    if isinstance(appr_c, dict):

                        info_lvl = matched_c.get("information_level", 1)
                        rev_flags = matched_c.get("revealed_flags", {}) or {}
                        intimate_unlocked = (info_lvl >= 3) or rev_flags.get("intimate_revealed") or rev_flags.get("all_revealed")

                        demeanor_val = str(matched_c.get("demeanor") or "").lower()
                        traits_all = [str(t).lower() for t in (matched_c.get("traits") or [])] + [str(t).lower() for t in (matched_c.get("unlocked_traits") or [])]
                        dyn_val = str(appr_c.get("intimate_dynamic") or appr_c.get("dynamic") or "").strip()
                        open_val = str(appr_c.get("erotic_openness") or appr_c.get("openness") or "").strip()
                        open_val_low = open_val.lower()

                        is_shameless = any(k in demeanor_val or any(k in t for t in traits_all) or k in open_val_low for k in ("shameless", "lewd", "provocative", "seductive", "hedonist", "nympho", "lascivious", "pervert"))
                        is_prude = any(k in demeanor_val or any(k in t for t in traits_all) or k in open_val_low for k in ("prude", "modest", "chaste", "prudish", "sheltered", "timid", "proper"))

                        from mechanics.social.persona.intimacy.appearance import clean_attribute_list_string as _clean_al
                        turn_ons_val = _clean_al(appr_c.get("desires_and_kinks") or appr_c.get("turn_ons") or appr_c.get("sensitive_spots") or "") or ""
                        turn_offs_val = _clean_al(appr_c.get("turn_offs") or appr_c.get("aversions") or "") or ""
                        fetish_val = _clean_al(appr_c.get("fetishes") or "") or ""
                        likes_val = _clean_al(appr_c.get("act_likes") or "") or ""
                        dislikes_val = _clean_al(appr_c.get("act_dislikes") or "") or ""

                        from mechanics.social.persona import (
                            format_demeanor_prompt_directive,
                            format_dynamic_prompt_directive, format_openness_prompt_directive,
                            format_desires_and_turn_offs_prompt_directive, format_fetish_prompt_directive,
                            format_act_preferences_prompt_directive,
                            format_body_asset_narrative_directive
                        )

                        intimate_dem = str(appr_c.get("intimate_demeanor") or "").strip()
                        if intimate_dem:
                            dm_dir = format_demeanor_prompt_directive(p, intimate_dem)
                            if dm_dir:
                                intimate_dynamic_openness_blocks.append(dm_dir)

                        if dyn_val:
                            d_dir = format_dynamic_prompt_directive(p, dyn_val)
                            if d_dir:
                                intimate_dynamic_openness_blocks.append(d_dir)

                        if open_val:
                            o_dir = format_openness_prompt_directive(p, open_val)
                            if o_dir:
                                intimate_dynamic_openness_blocks.append(o_dir)

                        # Body Asset Narrative Flavor & Insecurity/Pride Matrix
                        p_gender = str(matched_c.get("gender") or appr_c.get("gender") or "female").strip().lower()
                        is_male_npc = any(kw in p_gender for kw in ("male", "man", "boy")) and "female" not in p_gender
                        p_asset_size = str(appr_c.get("penis_size" if is_male_npc else "breast_size") or "").strip()
                        p_race = str(matched_c.get("race") or appr_c.get("race") or "human").strip()
                        p_under = appr_c.get("undergarments") if isinstance(appr_c.get("undergarments"), dict) else {}
                        p_asset_tex = str(appr_c.get("asset_texture") or "").strip()

                        lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
                        pl_gender = str(lead_char.get("gender", "male")).strip().lower()
                        is_pl_male = any(kw in pl_gender for kw in ("male", "man", "boy")) and "female" not in pl_gender
                        pl_app = lead_char.get("appearance", {}) if isinstance(lead_char.get("appearance"), dict) else {}
                        pl_asset_size = str(pl_app.get("penis_size" if is_pl_male else "breast_size") or "").strip()

                        if p_asset_size and p_asset_size.lower() not in ("none", "unknown"):
                            asset_dir = format_body_asset_narrative_directive(
                                partner_name=p,
                                gender=p_gender,
                                asset_size=p_asset_size,
                                demeanor=intimate_dem,
                                openness=open_val,
                                race=p_race,
                                undergarments=p_under,
                                player_asset=pl_asset_size,
                                player_gender=pl_gender,
                                asset_texture=p_asset_tex,
                                affinity=matched_c.get("relationship_score", 0)
                            )
                            if asset_dir:
                                intimate_dynamic_openness_blocks.append(asset_dir)

                        if intimate_unlocked or is_shameless:
                            if turn_ons_val or turn_offs_val:
                                t_dir = format_desires_and_turn_offs_prompt_directive(p, desires_val=turn_ons_val, turn_offs_val=turn_offs_val, dynamic_val=dyn_val)
                                if t_dir:
                                    intimate_dynamic_openness_blocks.append(t_dir)

                            if fetish_val:
                                f_dir = format_fetish_prompt_directive(p, fetish_val, dyn_val)
                                if f_dir:
                                    intimate_dynamic_openness_blocks.append(f_dir)

                            if likes_val or dislikes_val:
                                a_dir = format_act_preferences_prompt_directive(p, likes_val, dislikes_val, dyn_val)
                                if a_dir:
                                    intimate_dynamic_openness_blocks.append(a_dir)

                        # Situational Privacy & Alone Together Dynamic:
                        npcs_present_now = session.get("current_npcs") or []
                        dps_lower = {str(dp).lower().strip() for dp in (new_partners or [])}
                        bystanders = [
                            n_name for n in npcs_present_now
                            if (n_name := game_engine._get_npc_name(n))
                            and n_name.lower().strip() != p_low
                            and n_name.lower().strip() not in dps_lower
                            and not game_engine.is_dialogue_partner(n_name, new_partners)
                        ]
                        curr_loc = str(session.get("current_location", "")).lower()
                        is_private_room = any(k in curr_loc for k in ("bedroom", "dorm", "private room", "inn room", "quarters", "personal chamber", "bath", "onsen", "cabin", "tent"))
                        is_alone_together = len(bystanders) == 0 or is_private_room

                        if is_alone_together:
                            if is_prude:
                                privacy_dir = (
                                    f"  * [SITUATIONAL PRIVACY & MODESTY ({p})]: You and {p} are alone together (no other characters present). "
                                    f"However, {p} is naturally modest/prude: they remain bashful and flustered around direct advances, "
                                    f"treasuring gentle emotional bonding (holding hands, sincere quiet sharing) before overt physical passion."
                                )
                            else:
                                loc_name = session.get("current_location") or "the current secluded spot"
                                d_low = dyn_val.lower()
                                is_receptive = any(k in d_low for k in ("receptive", "yielding", "submissive", "surrender", "docile", "meek", "gentle"))
                                is_service = any(k in d_low for k in ("service", "pamper", "devoted", "pleasing", "worship"))
                                if is_receptive:
                                    physical_posture = (
                                        f"They welcome mutual passion wholeheartedly, melting into your touch, inviting you to take complete charge, "
                                        f"arching close, guiding your hands, whispering breathless desires, and surrendering control without bashful public hesitation!"
                                    )
                                elif is_service:
                                    physical_posture = (
                                        f"They eagerly pamper, massage, attend, and worship you with tender physical devotion, "
                                        f"freely attending to your comfort, kissing your hands, and caring for you without fear of onlookers!"
                                    )
                                else:
                                    physical_posture = (
                                        f"They can be openly passionate, affectionate, and physically forward—freely initiating touch, pulling you close, "
                                        f"leaning in for kisses, whispering intimate thoughts, sitting close, or taking physical charge without awkward hesitation or fear of being seen."
                                    )

                                privacy_dir = (
                                    f"  * [ALONE TOGETHER & OPEN PASSION ({p})]: You and {p} are ALONE TOGETHER with NO bystanders present to interrupt or judge (Location: {loc_name}). "
                                    f"If you two share romantic or mutual attraction, {p} is COMPLETELY UNCONSTRAINED by public modesty! "
                                    f"{physical_posture}"
                                )
                            intimate_dynamic_openness_blocks.append(privacy_dir)
                        else:
                            # Bystanders are present in the room
                            other_names_str = ", ".join(bystanders)
                            intimate_dynamic_openness_blocks.insert(0, f"[PRIVATE PROFILE NOTE: The intimate profile below belongs exclusively to {p}. Other characters in the scene ({other_names_str}) have NO knowledge of these details and must NEVER reference or react to them.]")
                            has_public_thrill = any(k in str(fetish_val).lower() for k in ("public", "exhibition", "voyeur", "outdoor", "thrill", "danger"))
                            if is_shameless or has_public_thrill:
                                public_dir = (
                                    f"  * [PUBLIC AUDACITY & THRILL ({p})]: Other characters ({other_names_str}) are present in the room, but {p} is Shameless / thrives on the thrill! "
                                    f"They openly drop cheeky double entendres, audacious innuendos, playful winks, or subtle physical touches just out of sight of onlookers."
                                )
                            else:
                                public_dir = (
                                    f"  * [PUBLIC DECORUM & DISCRETION ({p})]: Other characters ({other_names_str}) are present in the room. "
                                    f"Unless privately secluded, {p} maintains situational decorum in public. Direct displays of affection are subtle "
                                    f"(lingering glances, secret smiles, private hand brushes) rather than blatant public scenes."
                                )
                            intimate_dynamic_openness_blocks.append(public_dir)

                curr_ic = str(curr_phys.get("intimate_contact", "")).lower() if curr_phys else ""
                if is_nsfw and not _is_disengaging_dlg and (is_erotic_intimate_contact(curr_ic) or _in_active_erotic_dlg) and (p_low in curr_ic or (len(p_first) >= 3 and p_first in curr_ic) or " with " not in curr_ic or _in_active_erotic_dlg):
                    climax_info = curr_phys.get("climax_state", {}) if curr_phys else {}
                    excitement_data = curr_phys.get("excitement", {}) if curr_phys else {}
                    actors_exc = excitement_data.get("actors", {}) if isinstance(excitement_data, dict) else {}
                    partner_climaxes_map = climax_info.get("partner_climaxes", {}) if isinstance(climax_info, dict) else {}
                    partner_peaked = climax_info.get("partner_climaxed", False) or "partner reached climax" in curr_ic or "partner peaked" in curr_ic
                    player_peaked = climax_info.get("player_climaxed", False) and "hypersensitive ongoing" not in curr_ic
                    premature_finish = excitement_data.get("premature_finish", False) or "player reached climax spent, partner unsatisfied" in curr_ic
                    curr_act = infer_last_act_from_state(curr_phys, action_str=_dlg_act_text)
                    is_penetrative_act = curr_act in ("penetrative", "anal_give", "anal_receive")
                    act_display = "foreplay" if curr_act == "foreplay_nongenital" else curr_act.replace("_", " ")

                    p_gender = str(matched_c.get("gender") or (matched_c.get("appearance") or {}).get("gender") or "Female").lower() if matched_c else "female"
                    is_male_npc = "male" in p_gender and "female" not in p_gender
                    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
                    player_gender = str(lead_char.get("gender", "Male")).lower()
                    is_female_player = "female" in player_gender or "woman" in player_gender

                    # Include excitement gauge status in directive if active
                    lead_name = lead_char.get("name") or "Player"
                    p_val = 0
                    if excitement_data.get("active") and actors_exc:
                        p_exc_key = _match_actor_key(p, actors_exc)
                        pl_exc_key = _match_actor_key(lead_name, actors_exc)
                        p_val = actors_exc.get(p_exc_key, {}).get("meter", 0)
                        pl_val = actors_exc.get(pl_exc_key, {}).get("meter", 0)
                        gauge_str = f" [Current Excitement Gauges: {lead_name}: {pl_val}% | {p}: {p_val}%]"
                    else:
                        gauge_str = ""

                    p_clim_k = _match_actor_key(p, partner_climaxes_map) if partner_climaxes_map else ""
                    this_p_clim = bool(partner_climaxes_map.get(p_clim_k or p, False)) if partner_climaxes_map else (partner_peaked or p_val >= 100)

                    if premature_finish and not this_p_clim and p_val < 100:
                        partner_demanded = excitement_data.get("partner_demanded", True)
                        if partner_demanded:
                            intimate_dynamic_openness_blocks.append(
                                f"  * [PREMATURE PLAYER FINISH & UNSATISFIED PARTNER DEMAND ({p})]: The player character has finished, but {p} is STILL UNSATISFIED!{gauge_str} "
                                f"Penetrative intercourse ceases due to physical depletion. {p} MUST express frustration or unfulfilled desire according to their dynamic, "
                                f"assertively or teasingly demanding that the player use their fingers or tongue to bring {p} to climax before sleeping!"
                            )
                        else:
                            intimate_dynamic_openness_blocks.append(
                                f"  * [PREMATURE PLAYER FINISH & QUIET LONGING ({p})]: The player character has finished, leaving {p} unsatisfied.{gauge_str} "
                                f"Penetrative intercourse ceases. While unfulfilled, {p} does NOT forcefully demand stimulation; they show gentle flushed longing, a soft sigh, "
                                f"or tenderly kiss the player's shoulder and reassure them to rest in aftercare."
                            )
                    elif premature_finish and (this_p_clim or p_val >= 100):
                        intimate_dynamic_openness_blocks.append(
                            f"  * [SATISFIED PARTNER IN AFTERSHOCKS ({p})]: {p} has already reached climax and is resting warmly in post-orgasmic aftershocks,{gauge_str} "
                            f"watching affectionately or lending soft kisses while the player attends to any still-unsatisfied partner(s)."
                        )
                    elif this_p_clim and not player_peaked:
                        if is_male_npc:
                            act_cont_note = (
                                f"{p} has reached climax and catches his breath through aftershocks while the player continues toward her own release (using hands, mouth, or sensual friction). "
                            )
                        elif is_female_player and is_penetrative_act:
                            act_cont_note = (
                                f"Intercourse continues with the player maintaining rhythm toward her own release while {p} trembles from aftershocks. "
                            )
                        elif is_penetrative_act:
                            act_cont_note = (
                                f"Intercourse continues actively inside {p}. Narration MUST portray {p} trembling from aftershocks/contractions while the player continues their rhythm toward their own release. "
                            )
                        else:
                            act_cont_note = (
                                f"The current intimate act ({curr_act}) continues with {p} trembling from aftershocks while the player has not yet reached their own release (do NOT assume penetration unless the player explicitly transitions to it). "
                            )
                        intimate_dynamic_openness_blocks.append(
                            f"  * [INTIMATE PACING & PLAYER CLIMAX PRIMACY ({p})]: {p} reached climax in the previous beat, but the player character is STILL GOING and has not finished!{gauge_str} "
                            f"{act_cont_note}"
                            f"STRICTLY FORBIDDEN: NEVER narrate falling asleep, cuddling, or ending the session! "
                            f"STRICTLY FORBIDDEN: NEVER offer aftercare options or aftercare choices in `next_choices` until the player reaches their own climax! "
                            f"`next_choices` MUST provide active choices grounded in the current act/posture to continue, transition, or push toward the player's own climax!"
                        )
                    elif not player_peaked:
                        act_pace_note = (
                            "Intercourse continues with active rhythm and intimate contact. "
                            if is_penetrative_act
                            else f"Maintain the current intimate act ({act_display}) and postures without assuming penetrative intercourse unless the player explicitly transitions to it. "
                        )
                        intimate_dynamic_openness_blocks.append(
                            f"  * [INTIMATE ENCOUNTER PACING & PLAYER PRIMACY ({p})]: You and {p} are engaged in intimate contact ({curr_ic}).{gauge_str} "
                            f"If {p} reaches climax during this turn, their orgasm is a mid-act milestone—IT DOES NOT END THE SESSION! "
                            f"{act_pace_note}NEVER narrate premature collapse or aftercare sleep until the player reaches their own climax or chooses to stop! "
                            f"NEVER offer aftercare choices in `next_choices` until the player reaches their own climax!"
                        )

            # Check if in refractory cooldown on normal dialogue (injected once per turn)
            in_refr, refr_mins = is_in_refractory_cooldown(session, curr_phys)
            if in_refr and refr_mins > 0:
                intimate_dynamic_openness_blocks.append(
                    f"  * [REFRACTORY COOLDOWN ACTIVE]: The male player character is currently catching their breath and physically spent (~{refr_mins} in-game minutes remaining). "
                    f"Full penetrative intercourse cannot be sustained yet. Direct any physical intimacy toward non-penetrative affection (kissing, gentle caressing, pillow talk, or cuddling)."
                )

        intimate_dynamic_openness_section = "\n".join(intimate_dynamic_openness_blocks) + "\n" if intimate_dynamic_openness_blocks else ""



        # Use canonical format_dialogue_stall_directive — single prompt-level stall note injected
        # exactly once in dialogue_prompt_block (NOT in directive_note, preventing duplication).
        if active_bounty_contact and not has_phone_meetup:
            _stall_dialogue_type = "bounty"
            _stall_bounty_title = active_bounty_contact[1].get("title", "") if active_bounty_contact else ""
        elif is_quest_interrogation and not has_phone_meetup:
            _stall_dialogue_type = "quest"
            _stall_bounty_title = ""
        else:
            _stall_dialogue_type = "social"
            _stall_bounty_title = ""
        _stall_note = "" if _in_active_erotic_dlg else _fmt_stall(_stall_count, _stall_dialogue_type, partner_str, _stall_bounty_title)


        if active_bounty_contact and not has_phone_meetup:

            pn_name, bnt_q, bnt_wp = active_bounty_contact

            bnt_title = bnt_q.get("title", "Bounty Task")

            bnt_arch = bnt_q.get("quest_type", "Side Bounty")

            bnt_obj = bnt_q.get("objective", "")

            st_idx = bnt_wp.get("stage_index", 1) if bnt_wp else 1

            st_lbl = bnt_wp.get("stage_label", "Advance bounty task") if bnt_wp else "Advance bounty task"

            st_loc = bnt_wp.get("target_location", "") if bnt_wp else ""



            dialogue_prompt_block = (

                f"ACTIVE 1-ON-1 DIALOGUE MODE: BOUNTY & COMMISSION COOPERATION (Talking to: {partner_str}):\n"

                f"- Context: {partner_str} is directly tied to the active bounty '{bnt_title}' [{bnt_arch}].\n"

                f"- Overall Bounty Goal: {bnt_obj}\n"

                f"- Immediate Task (Stage {st_idx}): {st_lbl}" + (f" (Target Destination: {st_loc})\n" if st_loc else "\n") +

                f"- ⚡ TWO-WAY CONVERSATION DIRECTIVE (MANDATORY): "

                f"You MUST write BOTH the player character AND {partner_str} speaking aloud in direct quoted lines. "

                f"The player character's words MUST appear as a spoken quote, followed by {partner_str}'s reply. "

                f"Generate at least 2-3 back-and-forth spoken turns. "

                f"STRICTLY FORBIDDEN: Do NOT summarize the player character's words in third-person while only voicing {partner_str}.\n"

                f"- CHARACTER GROUNDING & MOTIVATION:\n"

                f"  * Maintain {partner_str}'s authentic personality, social standing, and emotional tone matching this archetype. (e.g. For Secret Admirer, Justin is bashful, nervous, and earnestly seeking discretion; NEVER make him a cold informant trading council records or classified intelligence!).\n"

                f"- 🎯 BOUNTY FOCUS & CONVERSATIONAL STEERING DIRECTIVE (CRITICAL):\n"

                f"  * {partner_str}'s primary focus, concern, and urgency right now is having this bounty completed.\n"

                f"  * ANTI-DISTRACTION GUARDRAIL: If the player brings up unrelated topics (such as video games, homework, unrelated campus gossip, casual banter, or stalls), {partner_str} may react briefly/in-character (e.g. 'Wait, gaming? We can talk about games later! Right now I really need your help with...', 'Look, I appreciate the chat, but if we don't deliver these notes soon someone will see us!'), but {partner_str} MUST FIRMLY STEER the conversation back to the bounty task!\n"

                f"  * NEVER let the narration get derailed into irrelevant topics or hallucinated deals that contradict the bounty objective.\n"

                f"{contact_info_block}"
                f"{recent_phone_section}"
                f"{trait_behavioral_section}"

                f"{intimate_dynamic_openness_section}"

                f"- `next_choices`: Generate 3 to 5 conversational choices reacting directly to what {partner_str} just said. You MUST include at least 1-2 choices that directly advance, accept, clarify, or commit to the bounty task (e.g. accepting the notes, agreeing to the delivery, asking for delivery instructions). Every substantive choice MUST require a skill check (`stat: 'CHA'`, `'INT'`, `'PER'`, or `'AGI'`, requirement: 5-8). Only the 1 dedicated conversational exit has `stat: 'NONE'`, `requirement: 0`.\n"
                f"{_stall_note}"
                f"{multi_partner_note}"
                f"{recruitment_prompt}"
                f"- `relationship_updates`: For eligible peer characters ({partner_str}), report affinity reactions (`delta_score`: +1 to +3 for good chat/banter/appealing to likes, +4 to +6 for great insight/support/flirtation targeting likes or turn-ons, +7 to +10 for major milestones; -1 to -4 for triggering dislikes/aversions/offending values/rudeness) and any newly revealed traits or preferences.\n"
                f"- ALWAYS include 1 dedicated conversational exit (`stat: 'NONE'`, `requirement: 0`, e.g. 'Thank {partner_str} and excuse yourself to step away').\n"
                f"- STRICTLY FORBIDDEN WHILE IN DIALOGUE: Do NOT generate greeting choices ('Greet {partner_str}') or travel choices to leave the room.\n\n"

            )

        elif is_quest_interrogation and not has_phone_meetup:

            # QUEST INVESTIGATION DIALOGUE MODE

            dialogue_prompt_block = (

                f"ACTIVE 1-ON-1 OR GROUP DIALOGUE MODE: QUEST INVESTIGATION & NEGOTIATION (Talking to: {partner_str}):\n"

                f"- The party is in direct, focused dialogue regarding an active quest or investigation with {partner_str}.\n"

                f"- The player is focused on this objective until they choose to step away.\n"

                f"- ⚡ TWO-WAY CONVERSATION DIRECTIVE (MANDATORY): "

                f"You MUST write BOTH the player character AND {partner_str} speaking aloud in direct quoted lines. "

                f"The player character's words MUST appear as a spoken quote, followed by {partner_str}'s reply. "

                f"Generate at least 2-3 back-and-forth spoken turns. "

                f"STRICTLY FORBIDDEN: Do NOT summarize the player character's words in third-person while only voicing {partner_str}.\n"

                f"{contact_info_block}"
                f"{recent_phone_section}"
                f"{trait_behavioral_section}"

                f"{intimate_dynamic_openness_section}"

                f"- `next_choices`: Generate 3 to 5 organic, distinct conversational choices reacting directly to what {partner_str} just said or proposed. Every substantive choice (pressing for evidence/clues, negotiating terms, challenging motives, strategic cooperation) MUST require a skill check (`stat: 'INT'`, `'CHA'`, or `'PER'`, requirement: 5-8). Only the 1 dedicated conversational exit has `stat: 'NONE'`, `requirement: 0`.\n"
                f"- Give distinct tactical stances (e.g. pressing for evidence/clues, negotiating terms/compromise, challenging motives, or offering strategic cooperation).\n"

                f"{_stall_note}"

                f"{multi_partner_note}"

                f"{recruitment_prompt}"

                f"- `relationship_updates`: For eligible peer characters ({partner_str}), report affinity reactions and newly revealed traits/preferences. Base affinity is +1 on check success (+2 crit), -1 on check failure (-2 crit), 0 on neutral ambient talk. Add +1 to +3 for actions resonating with their traits, preferences, or turn-ons; favorite gifts scale by rarity (+3 common to +7 relic); deduct -1 to -4 for triggering dislikes, turn-offs, prying into boundaries, or failed intimate advances (disliked gifts -3 to -5).\n"

                f"- ALWAYS include 1 dedicated conversational exit (`stat: 'NONE'`, `requirement: 0`, e.g. 'Thank {partner_str} and excuse yourself to step away').\n"

                f"- STRICTLY FORBIDDEN WHILE IN DIALOGUE: Do NOT generate greeting or conversation-initiation choices (e.g. 'Greet {partner_str}', 'Speak with {partner_str}', 'Approach {partner_str}', 'Talk to {partner_str}'). You are ALREADY talking face-to-face in active dialogue! Every choice must be a specific reply, stance, or inquiry reacting to what {partner_str} just said.\n"

                f"- STRICTLY FORBIDDEN WHILE IN DIALOGUE: Do NOT generate travel/movement choices to leave the room or interactions with unrelated NPCs outside this conversation.\n\n"

            )

        else:

            # SOCIAL & CASUAL HANGOUT DIALOGUE MODE (Default for friends, phone meetups, companions, neutral peers)
            _dlg_phys = (db.get_session_physical_state(session.get("id", 0)) if session.get("id") else None) or session.get("physical_state", {})
            _dlg_ic = str(_dlg_phys.get("intimate_contact", "")).lower() if _dlg_phys else ""
            from mechanics.social.physical_state import is_erotic_intimate_contact as _is_erotic_ic
            _in_active_erotic_dlg = bool(_in_active_erotic_dlg or (is_nsfw and not _is_disengaging_dlg and _is_erotic_ic(_dlg_ic)))
            if _in_active_erotic_dlg:

                _social_next_choices_block = (
                    f"- `next_choices`: Generate 4 context-aware intimate choices strictly grounded in the current act, postures, sensitive spots, and excitement meters in `[ACTIVE PHYSICAL & INTIMATE STATE CONTINUITY]` above (use the HYBRID CHOICE BLUEPRINTS as your situational guide). Every substantive choice MUST require a skill check (`stat: 'END'`, `'AGI'`, `'STR'`, `'CHA'`, or `'PER'`, requirement: 5-8). Include 1 dedicated pause/exit choice with `stat: 'NONE'` and `requirement: 0`. NEVER splice quest objectives, bounties, clues, or investigation props into intimate choices, and NEVER prefix intimate choices with ⭐, 🎯, or ⚡.\n"
                )
            else:
                _social_next_choices_block = (
                    f"- `next_choices`: Generate 4 to 6 diverse, rich, and character-driven conversational choices reacting naturally to what {partner_str} just said. Social and banter interactions MUST use proper skill checks (DC 5 to 8) to make roleplaying engaging. Every choice in conversation MUST require a skill check EXCEPT the dedicated exit choice:\n"
                    f"  1. 🎭 [Playful Banter / Humor]: Playfully tease or crack a witty joke (`stat: 'CHA'`, `'INT'`, or `'LUK'`, requirement: 5-8).\n"
                    f"  2. 💬 [Personal Inquiry / Getting to Know Them]: Ask insightful questions about their background/passions or read their mood (`stat: 'PER'` or `'INT'`, requirement: 5-7).\n"
                    f"  3. 💖 [Warmth / Affection / Flirtation]: Give a sincere compliment, show support, or flirt charmingly (or for Shameless/Bold partners, [Bold / Provocative Flirtation / Suggestive Teasing]) (`stat: 'CHA'`, requirement: 6-8, aligned with affinity & dynamic).\n"
                    f"  4. ☕ [Casual / Shared Atmosphere]: Casual observation, sharing refreshments, or enjoying the setting (`stat: 'PER'`, `'AGI'`, or `'CHA'`, requirement: 5-7).\n"
                    f"  5. 🎲 [Fun Activity / Shared Experience / Transition]: Propose trying food/drinks, playing a light game, moving to a new cozy spot, or enjoying the immediate activity together (`stat: 'CHA'`, `'AGI'`, or `'LUK'`, requirement: 5-8).\n"
                    f"  6. 🚪 [Dedicated Exit]: The ONLY action with `stat: 'NONE'` and `requirement: 0` is the 1 dedicated conversational exit (e.g. 'Thank {partner_str} and excuse yourself to step away'). Every other conversational choice MUST require a skill check (DC 5-8)!\n"
                )

            dialogue_prompt_block = (

                f"ACTIVE 1-ON-1 OR GROUP DIALOGUE MODE: SOCIAL HANGOUT & INTERACTION (Talking to: {partner_str}):\n"

                f"- The party is hanging out in face-to-face dialogue with {partner_str}.\n"

                f"- ⚡ TWO-WAY CONVERSATION DIRECTIVE (MANDATORY — APPLIES TO ALL DIALOGUE MODES EXCEPT 'off' AND 'minimal'): "

                f"You MUST write BOTH the player character AND {partner_str} speaking aloud in direct quoted lines. "

                f"The player character's action/inquiry MUST appear as a spoken quote (e.g. [Player Name]: \"...\"), "

                f"followed by {partner_str}'s spoken reply. Generate at least 2-3 back-and-forth spoken turns between them. "

                f"STRICTLY FORBIDDEN: Do NOT write only {partner_str}'s single quote while summarizing the player character's words in third-person narration. Both sides must speak.\n"

                f"- TONE & ATMOSPHERE: This is a lively, character-driven social/personal hangout (NOT a high-stakes investigation, council conspiracy, or melodramatic soliloquy).\n"

                f"- DO NOT DEFAULT TO SCHEMING, CONSPIRACIES, OR COUNCIL/LOGISTICS POLITICS unless the player explicitly chooses to steer the conversation there.\n"

                f"- CHARACTER VOICE & ANTI-CLICHÉ RULES:\n"

                f"  * Write {partner_str}'s dialogue strictly in their unique character voice, speech mannerisms, and personality traits.\n"

                f"  * CANON FACTUAL & LINEAGE GROUNDING: When discussing family, siblings, upbringing, past relationships, friends, or shared memories with the player, you MUST strictly adhere to the recorded facts above. DO NOT invent non-existent siblings (e.g. do not invent brothers if the character only has sisters) or contradict established codex data.\n"

                f"  * DIRECT CONVERSATION & ZERO COMPARISONS: Speak directly to the player about what is happening right now in front of you. NEVER compare the player to third parties, hypothetical people, or generic baselines (e.g. NEVER say 'Most guys would be too nervous...', 'You're not like other men...', 'Anyone else would have...'). Focus strictly on your immediate thoughts, personal reactions, playful humor, and physical presence.\n"

                f"  * STRICTLY BANNED: Do NOT write generic protagonist-flattery tropes (e.g. 'You're different from the others', 'Most people just see the title/rules', 'You have a way of saying what people need to hear', 'It's... refreshing', 'You're an interesting one').\n"

                f"  * CONCRETE CONVERSATION: Have {partner_str} react with concrete, relatable anecdotes, everyday humor, physical quirks, playful teasing, and genuine conversational flow rather than psychoanalyzing the protagonist.\n"

                f"  * PACED INTIMACY: PACED INTIMACY & SPOKEN LEWDNESS EXCEPTION: Early/mid-tier conversations (Affinity < 40) stay grounded in fun banter, shared activities, club/school stories, and lighthearted opinions. Deep vulnerable emotional confessions are reserved strictly for high-affinity milestones (50+). EXCEPTION FOR SHAMELESS & BOLD CHARACTERS: Characters with Shameless, Lewd, or Provocative dispositions have NO verbal filter—they freely use dirty humor, cheeky sexual innuendos, and double entendres even at low affinity and in casual conversation.\n"

                f"  * ROMANTIC & INTIMATE BEHAVIORAL DIVERSITY: In romantic, flirtatious, or intimate encounters, {partner_str} MUST express their defined Intimate Demeanor and authentic personality. STRICTLY BANNED: Do NOT default to generic anime stuttering ('I-I...', 'w-what...'), helpless bashfulness, or timid fidgeting. Confident, athletic, or teasing characters remain proactive, bold, physical, and vocal.\n"

                f"  * INTIMATE PACING & PLAYER CLIMAX PRIMACY: During intimate encounters, {partner_str} reaching climax/orgasm NEVER ends the session while the player is still unspent. Maintain the current physical act and postures (do NOT hallucinate penetration if engaged in oral, manual, or foreplay) while {partner_str} shivers from aftershocks. NEVER narrate collapsing together or aftercare sleep until the player reaches their own climax or chooses to stop. NEVER offer aftercare choices in next_choices until the player reaches climax. Next choices MUST include active options grounded in the current act/posture to continue, transition, or reach the player's release!\n"

                f"  * ROMANTIC INVOLVEMENT & CONFESSION DISABLER: If {partner_str} is ALREADY romantically involved / in a relationship with the player (e.g. In a Relationship, Dating, Lover, or Romantic Track), NEVER generate confession choices or relationship proposals (e.g. NEVER generate 'Confess your feelings...', 'Ask to be your girlfriend/boyfriend', or 'Ask to pursue a relationship'). They are already together! Generate romantic, affectionate, playful, or intimate choices fitting their established bond.\n"

                f"  * ANATOMICAL & SPECIES ACCURACY: When generating physical actions, touch, or intimate choices, strictly respect the character's biological species anatomy and known turn-ons. For beastfolk / furry characters (foxes, cats, wolves, rabbits, etc.), they possess animal ears at the crown of their head, a tail, and fur — NEVER mention human earlobes! Focus on their actual species traits (e.g. soft fox ear base, sensitive tail, neck fur, or defined turn-ons).\n"

                f"{contact_info_block}"
                f"{recent_phone_section}"
                f"{trait_behavioral_section}"

                f"{intimate_dynamic_openness_section}"

                f"{_social_next_choices_block}"

                f"- CONVERSATIONAL TONE & ANTI-CONFRONTATION GUARD (CRITICAL):\n"

                f"  * Keep tone natural, relaxed, and authentic. Do NOT turn casual hangouts or dates into a debate club, battle of words, or psychological trial of composure!\n"

                f"  * In social dialogues, `INT` choices represent witty perspectives, insightful opinions, or shared interests (NOT 'analyzing motives/patterns for weaknesses').\n"

                f"  * In social dialogues, `PER` choices represent attentive listening, empathy, or noticing their comfort/smile (NOT 'reading micro-expressions for tells or deceit').\n"

                f"  * In social dialogues, `CHA` choices represent warmth, charm, humor, or genuine personal sharing (NOT 'negotiating contractual terms').\n"

                f"{_stall_note}"

                f"{multi_partner_note}"

                f"{recruitment_prompt}"

                f"- `relationship_updates`: For eligible peer characters ({partner_str}), report affinity reactions and newly revealed traits/preferences. Base affinity is +1 on check success (+2 crit), -1 on check failure (-2 crit), 0 on neutral ambient talk. Add +1 to +3 for actions resonating with their traits, preferences, or turn-ons; favorite gifts scale by rarity (+3 common to +7 relic); deduct -1 to -4 for triggering dislikes, turn-offs, prying into boundaries, or failed intimate advances (disliked gifts -3 to -5). (In high school scenarios, faculty, parents, and store clerks do not receive relationship updates).\n"

                f"- STRICTLY FORBIDDEN WHILE IN DIALOGUE: Do NOT generate greeting or conversation-initiation choices (e.g. 'Greet {partner_str}', 'Speak with {partner_str}', 'Approach {partner_str}', 'Talk to {partner_str}'). You are ALREADY talking face-to-face in active dialogue! Every choice must be a specific reply, stance, or inquiry reacting to what {partner_str} just said.\n"

                f"- STRICTLY FORBIDDEN WHILE IN DIALOGUE: Do NOT generate travel/movement choices to leave the room or interactions with unrelated NPCs outside this conversation.\n\n"

            )

    else:

        # Check if the player is traveling away from the current primary location / zone

        is_traveling_away = False

        traveling_comp_names = set()

        left_behind_patron_names = set()

        if not is_in_combat(session):

            for a in actions:

                a_dest = extract_movement_destination(a.get("label", ""), session["id"], current_zone=get_zone_location_name(session.get("current_location", "")), scen_key=scen_key)

                if a_dest:

                    d_z, d_p = a_dest

                    c_loc = session.get("current_location", "")

                    o_p = get_primary_location_name(c_loc)

                    o_z = get_zone_location_name(c_loc)

                    if (d_p and o_p and d_p.lower() != o_p.lower()) or (d_z and o_z and d_z.lower() != o_z.lower()):

                        is_traveling_away = True

                        t_comps, l_patrons = game_engine.classify_scene_npcs(session, actions, old_primary=o_p, dest_primary=d_p)

                        for tc in t_comps:

                            if tc.get("name"):

                                traveling_comp_names.add(str(tc["name"]).strip().lower())

                        for lp in l_patrons:

                            if lp.get("name"):

                                left_behind_patron_names.add(str(lp["name"]).strip().lower())

                        break



        active_room_npcs = []

        for n in (session.get("current_npcs") or []):

            if not n:

                continue

            if isinstance(n, dict) and any(s in str(n.get("status_effects", "")).lower() for s in ["unconscious", "fallen", "dead", "defeated"]):

                continue

            n_name = game_engine._get_npc_name(n)

            if not n_name or n_name.lower() == "none":

                continue

            n_low = n_name.lower()

            if is_traveling_away:

                # When moving away, patrons stay behind; only companions travel with the party

                if n_low in left_behind_patron_names or (traveling_comp_names and n_low not in traveling_comp_names) or not traveling_comp_names:

                    continue

            active_room_npcs.append(n_name)



        if active_room_npcs:

            npc_str = ", ".join(active_room_npcs)

            dialogue_prompt_block = (

                f"OPEN ROOM / HUB EXPLORATION MODE (Active Characters Present: {npc_str}):\n"

                f"- The party is exploring the open room / hub (NOT locked in a conversation).\n"

                f"- `next_choices` MUST include balanced options to interact with or speak to the distinct characters present ({npc_str}), alongside room investigation, resting, or travel.\n"

                f"- Basic dialogue initiation choices with present NPCs MUST be Free Actions (`stat: 'NONE'`, `requirement: 0`, e.g. 'Speak with {active_room_npcs[0]}').\n"

                f"- Do NOT generate multiple redundant travel choices to the same destination; keep travel to 1-2 distinct options so NPC interactions remain accessible.\n\n"

            )



    movement_dest_str = ""

    for a in actions:

        _ad = extract_movement_destination(a.get("label", ""), session["id"], current_zone=get_zone_location_name(session.get("current_location", "")), scen_key=scen_key)

        if _ad:

            movement_dest_str = _ad

            break



    from mechanics.system.memory.budget import DynamicTokenBudget
    budget = DynamicTokenBudget.from_session(session, party, actions)

    trimmed_dialogue = budget.trim(dialogue_prompt_block, "dialogue")

    from mechanics.system.time_engine import (

        format_llm_time_context,

        calculate_action_time_cost,

        advance_time,

        apply_sleep_rest,

        is_sleep_action

    )
    return dialogue_prompt_block

