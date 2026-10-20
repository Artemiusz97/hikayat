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
        is_acc = bool(parsed_action.metadata.get("is_accompanied")) if parsed_action and parsed_action.metadata else False
        from mechanics.world.mobility import ACCOMPANIED_TRAVEL_PHRASES, is_solo_travel_intent
        if not is_acc:
            if any(term in label_low for term in ACCOMPANIED_TRAVEL_PHRASES) or any(k in label_low for k in ("propose moving", "suggest moving", "quieter spot", "secluded spot", "private meeting", "speak in private", "talk in private")):
                is_acc = True
            elif current_partners and not is_solo_travel_intent(actions):
                if any(v in label_low for v in ("discuss", "talk", "speak", "chat", "convene", "confer", "meet", "continue", "carry", "walk", "escort", "guide", "lead", "help")):
                    is_acc = True
                elif re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help|accompany)\b.*\b(?:her|him|them)\b", label_low):
                    is_acc = True
                elif isinstance(a, dict) and any(dp.lower() == str(a.get("target_npc") or "").strip().lower() for dp in current_partners):
                    is_acc = True
            for dp in current_partners:
                if dp.lower() in label_low or (len(dp.split()[0]) >= 3 and dp.split()[0].lower() in label_low):
                    is_acc = True
                    break

        if parsed_action.category == IntentCategory.MOVEMENT:
            curr_loc = session.get("current_location", "")
            curr_zone = get_zone_location_name(curr_loc)
            scen_k = session.get("scenario", "default")
            action_dest = extract_movement_destination(label, session.get("id"), current_zone=curr_zone, scen_key=scen_k)
            if action_dest:
                dest_z, dest_p = action_dest
                curr_p = get_primary_location_name(curr_loc)
                if curr_p and dest_p and curr_p.lower() != dest_p.lower():
                    if not is_acc:
                        is_departing_venue = True
            elif parsed_action.metadata.get("is_room_exit"):
                if not is_acc:
                    is_departing_venue = True

        # Check for conversational exit: unified intent engine
        is_explicit_exit = parsed_action.category == IntentCategory.DIALOGUE_EXIT
        is_departure_exit = (parsed_action.category == IntentCategory.MOVEMENT and is_departing_venue and not is_acc)
        is_rendezvous_proposal = (parsed_action.category == IntentCategory.SOCIAL_INVITE and bool(parsed_action.metadata.get("is_rendezvous")))
        is_accompany_proposal = (parsed_action.category == IntentCategory.SOCIAL_INVITE and bool(parsed_action.metadata.get("is_accompany")))
        is_part_ways = (parsed_action.category == IntentCategory.SOCIAL_INVITE and parsed_action.metadata.get("invite_type") == "part_ways")

        if is_explicit_exit or is_part_ways:
            has_exited_convo = True
            new_partners = []
            if session.get("id"):
                import db
                target_npc = parsed_action.target_entity
                if not target_npc:
                    tcs = db.get_temporary_companions(session["id"])
                    matched_tcs = [
                        tc.get("name", "") for tc in tcs
                        if tc.get("name", "").lower() in label_low
                        or (len(tc.get("name", "").split()[0]) >= 3 and tc.get("name", "").split()[0].lower() in label_low)
                    ]
                    is_general = any(k in label_low for k in (
                        "everyone", "all", "both", "room", "excuse", "leave", "goodbye",
                        "farewell", "walk away", "step away", "part ways", "alone", "dismiss",
                        "wrap up", "head back"
                    ))
                    if matched_tcs and len(matched_tcs) < len(tcs) and not is_general:
                        for m_name in matched_tcs:
                            db.remove_temporary_companion(session["id"], m_name)
                    else:
                        db.clear_temporary_companions(session["id"])
                else:
                    db.remove_temporary_companion(session["id"], target_npc)
        elif is_rendezvous_proposal:
            # Player proposed an in-person rendezvous / private meeting at another venue.
            action_succeeded = bool(a.get("success", True)) if isinstance(a, dict) else True
            cand_target = parsed_action.target_entity
            if cand_target and any(p.lower() == cand_target.lower() for p in current_partners):
                target_npc = next(p for p in current_partners if p.lower() == cand_target.lower())
            elif session.get("dialogue_partner") and any(p.lower() == str(session.get("dialogue_partner")).lower() for p in current_partners):
                target_npc = session.get("dialogue_partner")
            elif current_partners:
                target_npc = current_partners[0]
            else:
                target_npc = cand_target or session.get("dialogue_partner") or ""

            if not action_succeeded:
                # Failed skill check: NPC declines the rendezvous; they do NOT leave and no appointment is booked
                has_exited_convo = False
                new_partners = current_partners
            else:
                curr_loc = session.get("current_location", "")
                curr_zone = get_zone_location_name(curr_loc)
                scen_k = session.get("scenario", "default")
                action_dest = extract_movement_destination(label, session.get("id"), current_zone=curr_zone, scen_key=scen_k, allow_proposal=True)
                dest_loc = f"{action_dest[0]} ➔ {action_dest[1]}" if action_dest else (parsed_action.metadata.get("target_location") or "")
                sess_id = session.get("id")
                if not action_dest and dest_loc and "➔" not in dest_loc and sess_id:
                    try:
                        import db
                        all_locs = db.get_session_locations(sess_id)
                        d_low = dest_loc.lower().strip()
                        for r in all_locs:
                            pn = r.get("primary_name", "")
                            zn = r.get("zone_name", "")
                            if pn and (d_low in pn.lower() or pn.lower() in d_low):
                                dest_loc = f"{zn} ➔ {pn}"
                                break
                    except Exception:
                        pass
                if sess_id and target_npc and dest_loc:
                    import db
                    cur_day = int(session.get("current_day") or 1)
                    cur_min = int(session.get("current_minute") or 480)
                    abs_min = max(0, cur_day - 1) * 1440 + cur_min
                    db.save_rendezvous_appointment(
                        session_id=sess_id,
                        npc_id=target_npc,
                        npc_name=target_npc,
                        rendezvous_location=dest_loc,
                        topic=parsed_action.metadata.get("topic", ""),
                        is_confidential=bool(parsed_action.metadata.get("is_confidential", True)),
                        created_minute=abs_min,
                        expiry_minute=abs_min + 45
                    )
                    db.clear_temporary_companions(sess_id)

                # The agreeing NPC excuses themselves to head to the destination first
                has_exited_convo = True
                new_partners = [p for p in current_partners if p.lower() != (target_npc or "").lower()]
        elif is_accompany_proposal:
            action_succeeded = bool(a.get("success", True)) if isinstance(a, dict) else True
            target_npc = parsed_action.target_entity or session.get("dialogue_partner") or (current_partners[0] if current_partners else "")
            sess_id = session.get("id")
            if action_succeeded:
                if sess_id and target_npc:
                    import db
                    db.add_temporary_companion(sess_id, target_npc, activity=parsed_action.metadata.get("invite_type", "walking_together"))
                has_exited_convo = False
                new_partners = [target_npc] if target_npc else current_partners
            else:
                has_exited_convo = False
                new_partners = current_partners
        elif is_departure_exit:
            # Player departed from the venue without an accompanied partner; old partners are left behind
            new_partners = []
            has_exited_convo = bool(current_partners)
            if session.get("id"):
                import db
                db.clear_temporary_companions(session["id"])
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
                    import namegen
                    try:
                        roster = db.get_school_roster(session["id"])
                        tgt_low = parsed_action.target_entity.lower().strip()
                        for member in roster:
                            m_name = member.get("name", "")
                            m_low = m_name.lower().strip()
                            m_first = m_low.split()[0] if m_low else ""
                            m_given = namegen.extract_first_and_last_name(m_name)[0].lower().strip()
                            if m_name and (tgt_low == m_low or tgt_low in (m_first, m_given) or f" {tgt_low} " in f" {m_low} " or m_low.startswith(tgt_low)):
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

                    "patron", "shopkeeper", "innkeeper", "headmaster", "dean", "professor", "teacher",

                    "bin", "binti", "ibn", "bint", "van", "von", "der", "den", "het", "ten", "ter", "del", "della", "degli", "das", "dos"

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
                import namegen
                try:
                    roster = db.get_school_roster(session["id"])
                    for member in roster:
                        m_name = member.get("name", "")
                        if not m_name:
                            continue
                        m_low = m_name.lower().strip()
                        m_first = m_low.split()[0] if m_low else ""
                        m_given = namegen.extract_first_and_last_name(m_name)[0].lower().strip()
                        first_cands = {fc for fc in (m_first, m_given) if len(fc) >= 3 and fc not in namegen.NAME_PARTICLES_AND_HONORIFICS}
                        if m_low in label_low or any(f" {fc} " in f" {label_low} " for fc in first_cands):
                            detected.append(m_name)
                            break
                except Exception:
                    pass

            label_low = label.lower()
            is_priv = any(k in label_low for k in (
                "private", "privately", "in private", "quieter spot", "quiet spot", "secluded spot",
                "aside", "step aside", "pull aside", "pull her aside", "pull him aside", "separate",
                "alone", "just the two of us", "between us", "whisper", "confidentially", "secretly"
            ))
            from mechanics.social.intimate_excitement import is_intimate_action_label
            is_intim = is_intimate_action_label(label) or any(k in label_low for k in (
                "lean into", "leans into", "kiss", "caress", "touch", "hold hands", "embrace", "cuddle"
            ))
            is_mv = is_departing_venue or (parsed_action and parsed_action.category == IntentCategory.MOVEMENT)
            is_single_direct = len(detected) == 1 and not any(g_kw in label_low for g_kw in (
                "both", "all", "everyone", "council", "group", "committee", "each other", "them all", "together"
            ))

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

                    if (is_priv or is_mv) and detected:
                        new_partners = list(detected)
                    elif all(_is_in_current_group(d) for d in detected):
                        new_partners = list(current_partners)
                    else:
                        new_partners = detected
                else:
                    new_partners = detected
            elif (is_priv or is_intim) and current_partners:
                resolved_target = None
                has_female_pronoun = bool(re.search(r'\b(?:her|she)\b', label_low))
                has_male_pronoun = bool(re.search(r'\b(?:him|he)\b', label_low))
                if has_female_pronoun or has_male_pronoun:
                    try:
                        import db
                        roster = db.get_school_roster(session.get("id")) if session.get("id") else []
                        for cp in current_partners:
                            cp_low = cp.lower()
                            for m in roster:
                                if m.get("name", "").lower() == cp_low:
                                    g = (m.get("gender") or "").lower()
                                    if has_female_pronoun and g == "female":
                                        resolved_target = cp
                                        break
                                    elif has_male_pronoun and g == "male":
                                        resolved_target = cp
                                        break
                            if resolved_target:
                                break
                    except Exception:
                        pass

                if not resolved_target:
                    main_dp = str(session.get("dialogue_partner") or "").strip()
                    if main_dp and any(main_dp.lower() == cp.lower() for cp in current_partners):
                        resolved_target = main_dp
                    else:
                        resolved_target = current_partners[0]

                new_partners = [resolved_target]

    return new_partners, has_exited_convo

def _build_dialogue_prompt_block(session: dict, ctx, new_partners: list, party: list, actions: list) -> str:
    """Extracted Phase 2A Builder for Dialogue Partner Prompts."""
    from mechanics.world.locations.core import extract_movement_destination, get_zone_location_name, get_primary_location_name
    from mechanics.combat import is_in_combat
    import db, game_engine, scenario_data
    scen_key = session.get('scenario', 'fantasy')
    dialogue_prompt_block = ""

    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
    if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
        lead_char = actions[0]["char"]
    if not lead_char and session.get("host_user_id"):
        try:
            lead_char = db.get_character(session.get("host_user_id")) or {}
        except Exception:
            pass
    pl_name = str(lead_char.get("name") or "you").strip()
    pl_gender = str(lead_char.get("gender", "male")).strip().lower()
    is_pl_male = any(kw in pl_gender for kw in ("male", "man", "boy")) and "female" not in pl_gender
    pl_pronoun = "he/him" if is_pl_male else "she/her"
    pl_target_attraction = "a GIRL / WOMAN / FEMALE PARTNER" if is_pl_male else "a GUY / MAN / MALE PARTNER"

    # 0a. Check active rendezvous agreement and departure in player actions
    from mechanics.narrative.intent import RENDEZVOUS_PROPOSAL_RE
    for a in (actions or []):
        lbl = (a.get("label", "") if isinstance(a, dict) else str(a)).lower()
        if RENDEZVOUS_PROPOSAL_RE.search(lbl):
            dialogue_prompt_block += (
                "RENDEZVOUS AGREEMENT & DEPARTURE:\n"
                "- The character agrees to the proposed meeting venue and excuses themselves to head there first.\n"
                "- Narrate them agreeing and exiting the room (e.g. 'I will go ahead so we do not draw attention. Meet me there.').\n"
                "- The player remains at the current location for this turn.\n\n"
            )
            break

    # 0b. Check active confidential topic embargoes
    if session.get("id"):
        try:
            from mechanics.world.waypoints import check_location_matches_waypoint
            curr_l = session.get("current_location", "")
            active_appts = db.get_active_rendezvous_appointments(session["id"])
            for appt in active_appts:
                if appt.get("is_confidential") and appt.get("topic"):
                    appt_loc = appt.get("rendezvous_location", "")
                    if not (check_location_matches_waypoint(curr_l, appt_loc) or check_location_matches_waypoint(appt_loc, curr_l)):
                        dialogue_prompt_block += (
                            f"CONFIDENTIAL TOPIC EMBARGO ({appt.get('npc_name')}):\n"
                            f"- {appt.get('npc_name')} and the player agreed to discuss \"{appt.get('topic')}\" strictly in private at {appt_loc}.\n"
                            f"- Under NO circumstances should \"{appt.get('topic')}\" be discussed in this current public setting.\n"
                            f"- If the player attempts to discuss it here, {appt.get('npc_name')} must refuse: 'Keep your voice down. We agreed to talk at {appt_loc}.'\n\n"
                        )
        except Exception:
            pass

    # 0c. Check active temporary walking companions
    if session.get("id"):
        try:
            tcs = db.get_temporary_companions(session["id"])
            if tcs:
                tc_names = ", ".join(tc.get("name", "") for tc in tcs if tc.get("name"))
                if tc_names:
                    dialogue_prompt_block += (
                        f"ACCOMPANYING HANGOUT COMPANION(S) ({tc_names}):\n"
                        f"- {tc_names} is currently walking and hanging out alongside the player.\n"
                        f"- They should participate naturally in conversations and ambient observations.\n\n"
                    )
        except Exception:
            pass

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

        _scen_name = session.get("scenario", "fantasy")
        _is_combat_scen = (
            scenario_data.is_mechanic_enabled(_scen_name, "tactical_combat")
            and not scenario_data.is_non_combat_scenario(_scen_name)
            and not scenario_data.has_tag(_scen_name, "non_combat")
            and not scenario_data.has_tag(_scen_name, "high_school")
        )

        recruitment_prompt = ""
        if not _is_combat_scen:
            recruitment_prompt = "  * PARTY RECRUITMENT DISABLED: This is a non-combat / civilian scenario. NEVER generate party recruitment, mercenary hire, or companion joining choices.\n"
        elif not _in_active_erotic_dlg and (human_count + len(party_npcs) < 4):
            enemy_list = game_engine.get_active_enemies(session) or []
            enemy_names = {game_engine._get_npc_name(e).lower() for e in enemy_list if e}
            lore_people = db.get_lorebook(session["id"]).get("person", []) if session.get("id") else []
            for partner in new_partners:
                if not partner or partner.lower() in enemy_names:
                    continue
                lore_ent = next((p for p in lore_people if p.get("name", "").lower() == partner.lower()), {})
                t_role = str(lore_ent.get("role") or lore_ent.get("occupation") or lore_ent.get("description") or "").lower()
                if any(m in t_role for m in ("merchant", "shopkeeper", "vendor", "apothecary", "peddler", "trader")):
                    continue
                cd = db.get_recruitment_cooldown(session["id"], partner) if session.get("id") else 0
                if cd == 0 and not any(p.get("name", "").lower() == partner.lower() for p in party_npcs):
                    recruitment_prompt += f"  * 🤝 [CHA] Party Recruitment check: 'Invite {partner} to join your party as a permanent companion' (Offer this skill check choice when talking to friendly/allied NPCs to recruit them).\n"
                elif cd > 0:
                    recruitment_prompt += f"  * Note: {partner} declined a party recruitment invitation earlier and cannot be invited again today (on cooldown until next day/tomorrow). NEVER offer a recruitment choice for {partner}.\n"

        contact_exchange_prompt = ""
        from mechanics.system.phone import scenario_has_smartphone
        if scenario_has_smartphone(_scen_name) and not _in_active_erotic_dlg:
            from mechanics.social.relationships import is_contact_eligible, is_unlocked_contact, calculate_contact_exchange_dc
            party_names_lower = {str(p.get("name", "")).strip().lower() for p in party_npcs}
            lore_people = db.get_lorebook(session["id"]).get("person", []) if session.get("id") else []
            for partner in new_partners:
                if not partner:
                    continue
                lore_ent = next((p for p in lore_people if p.get("name", "").lower() == partner.lower()), {})
                t_role = str(lore_ent.get("role") or lore_ent.get("occupation") or "").lower()
                t_desc = str(lore_ent.get("description") or "").lower()
                if not is_contact_eligible(name=partner, role=t_role, description=t_desc, scenario=_scen_name):
                    continue
                existing_c = db.get_contact(session["id"], partner) if session.get("id") else None
                if is_unlocked_contact(existing_c, party_names_lower) or partner.lower() in party_names_lower:
                    continue
                cd = db.get_contact_request_cooldown(session["id"], partner) if session.get("id") else 0
                if cd == 0:
                    dc = calculate_contact_exchange_dc(existing_c or lore_ent, scenario=_scen_name)
                    contact_exchange_prompt += f"  * 📱 [CHA] Smartphone Contact Request check (DC {dc}): 'Ask for {partner}\\'s Phone Number / Contact Info' (Difficult social check to exchange numbers and add them to your phone contacts bypassing friend affinity requirement).\n"
                elif cd > 0:
                    contact_exchange_prompt += f"  * Note: {partner} declined to share their contact info earlier and cannot be asked again today (on cooldown until tomorrow). NEVER offer a contact request choice for {partner}.\n"

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



        # Use canonical compute_scene_beat_linger_turns helper from npcs
        from game_engine.npcs import (
            compute_scene_beat_linger_turns as _compute_linger,
            format_organic_npc_initiative_directive as _fmt_initiative,
            format_ring2_attentive_peer_cues as _fmt_ring2,
        )
        _stall_count = _compute_linger(session.get("history") or [], session=session, active_partners=new_partners)

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
                    stg_npcs = (session.get("pre_turn_stage_npcs") or []) + (session.get("current_npcs") or [])
                    matched_c = next((
                        n for n in stg_npcs
                        if isinstance(n, dict) and n.get("name", "").lower().strip() == p_low
                    ), None)
                    if not matched_c and len(p_first) >= 3:
                        matched_c = next((
                            n for n in stg_npcs
                            if isinstance(n, dict) and (n.get("name", "").lower().strip().split() or [""])[0] == p_first
                        ), None)

                if matched_c:
                    from mechanics.social.persona.actor_card import build_actor_direction_card
                    from mechanics.social.genealogy import build_topic_aware_npc_context

                    # Merge contact with lorebook entity if available
                    merged_npc = dict(matched_c)
                    if session.get("id"):
                        try:
                            lore_ent = db.get_lorebook_entity(session["id"], p)
                            if lore_ent:
                                for lk, lv in lore_ent.items():
                                    if lv and not merged_npc.get(lk):
                                        merged_npc[lk] = lv
                        except Exception:
                            pass

                    # Overlay living scene stage state (micro_blocking, composure_state, attention_ring, stage_role)
                    stage_source = None
                    for stg in (session.get("pre_turn_stage_npcs") or []):
                        if isinstance(stg, dict):
                            s_nm = game_engine._get_npc_name(stg).lower().strip()
                            if s_nm == p_low or (len(p_first) >= 3 and (s_nm.split() or [""])[0] == p_first):
                                stage_source = stg
                                break
                    if not stage_source and isinstance(session.get("scene_stage_state"), dict):
                        st_dict = session["scene_stage_state"].get(p_low) or (session["scene_stage_state"].get(p_first) if len(p_first) >= 3 else None)
                        if isinstance(st_dict, dict):
                            stage_source = st_dict
                    if stage_source:
                        for sk in ("micro_blocking", "composure_state", "composure_ttl", "stage_role", "attention_ring"):
                            if stage_source.get(sk) is not None:
                                merged_npc[sk] = stage_source[sk]

                    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
                    if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
                        lead_char = actions[0]["char"]

                    npcs_present_now = session.get("pre_turn_stage_npcs") or session.get("current_npcs") or []
                    dps_lower = {str(dp).lower().strip() for dp in (new_partners or [])}
                    bystanders = [
                        n_name for n in npcs_present_now
                        if (n_name := game_engine._get_npc_name(n))
                        and n_name.lower().strip() not in dps_lower
                        and not game_engine.is_dialogue_partner(n_name, new_partners)
                    ]

                    card_text = build_actor_direction_card(
                        session=session,
                        npc=merged_npc,
                        context=ctx,
                        active_partners=new_partners,
                        actions=actions,
                        in_active_erotic=_in_active_erotic_dlg,
                        player_char=lead_char,
                        bystander_names=bystanders,
                    )

                    topic_context = build_topic_aware_npc_context(
                        matched_c,
                        actions=actions,
                        session_history=session.get("history", []),
                        scenario=session.get("scenario", "fantasy")
                    )

                    if topic_context:
                        card_text += "\n" + topic_context

                    contact_context_lines.append(card_text)



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
        trait_behavioral_section = ""



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
                    if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
                        lead_char = actions[0]["char"]
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
                        from mechanics.social.intimate_excitement import roll_partner_demand
                        partner_demanded = roll_partner_demand(matched_c) if matched_c else excitement_data.get("partner_demanded", True)
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
                curr_ic_dlg = str(curr_phys.get("intimate_contact", "")).lower() if curr_phys else ""
                exc_dlg = (curr_phys.get("excitement") or {}) if curr_phys else {}
                pl_climaxed_dlg = bool((curr_phys.get("climax_state") or {}).get("player_climaxed")) if curr_phys else False
                pl_in_refr_dlg = bool(exc_dlg.get("player_in_refractory")) if exc_dlg.get("player_in_refractory") is not None else ("ongoing for player" not in curr_ic_dlg or pl_climaxed_dlg)
                if pl_in_refr_dlg:
                    lead_c_dlg = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else {})
                    if not lead_c_dlg and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
                        lead_c_dlg = actions[0]["char"]
                    pl_gen_dlg = str(lead_c_dlg.get("gender", "Male")).lower() if isinstance(lead_c_dlg, dict) else "male"
                    if "female" in pl_gen_dlg or "woman" in pl_gen_dlg:
                        intimate_dynamic_openness_blocks.append(
                            f"  * [POST-CLIMAX RECOVERY / AFTERCARE ACTIVE]: Both partners are resting in post-climax recovery (~{refr_mins} in-game minutes remaining). "
                            f"Full penetrative intercourse cannot be sustained yet. Direct any physical intimacy toward tender aftercare (kissing, gentle caressing, pillow talk, or cuddling)."
                        )
                    else:
                        intimate_dynamic_openness_blocks.append(
                            f"  * [REFRACTORY COOLDOWN ACTIVE]: The male player character is currently catching their breath and physically spent (~{refr_mins} in-game minutes remaining). "
                            f"Full penetrative intercourse cannot be sustained yet. Direct any physical intimacy toward non-penetrative affection (kissing, gentle caressing, manual/oral attention, pillow talk, or cuddling)."
                        )
                elif not _in_active_erotic_dlg:
                    refr_partners_dlg = exc_dlg.get("refractory_partners") if isinstance(exc_dlg.get("refractory_partners"), dict) else {}
                    for p in partners_list:
                        matched_rp = _match_actor_key(p, refr_partners_dlg) if refr_partners_dlg else ""
                        if matched_rp and refr_partners_dlg.get(matched_rp):
                            intimate_dynamic_openness_blocks.append(
                                f"  * [PARTNER POST-CLIMAX RECOVERY ({p})]: {p} recently reached climax and is resting in post-climax recovery (~{refr_mins} in-game minutes remaining). "
                                f"Acknowledge their satisfied, recovering state naturally in dialogue or gentle affection."
                            )

        intimate_dynamic_openness_section = "\n".join(intimate_dynamic_openness_blocks) + "\n" if intimate_dynamic_openness_blocks else ""



        # Use canonical format_organic_npc_initiative_directive — single prompt-level initiative note injected
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

        _partner_stage_npc = None
        _all_stage = (session.get("pre_turn_stage_npcs") or []) + (session.get("current_npcs") or [])
        if new_partners:
            _p_first_low = new_partners[0].lower().strip()
            _partner_stage_npc = next((
                n for n in _all_stage
                if isinstance(n, dict) and (n.get("name", "").lower().strip() == _p_first_low or (n.get("name", "").lower().strip().split() or [""])[0] == _p_first_low.split()[0])
            ), None)
        if not _partner_stage_npc:
            _partner_stage_npc = {"name": partner_str}

        from mechanics.world.schedules import get_time_block_key
        _dlg_cur_loc = session.get("current_location", "")
        _dlg_cur_min = int(session.get("current_minute", 480) or 480)
        _dlg_scen_key = session.get("scenario", "fantasy")
        _dlg_time_slot = session.get("time_slot") or get_time_block_key(_dlg_cur_min)
        _stall_note = "" if _in_active_erotic_dlg else _fmt_initiative(
            linger_turns=_stall_count,
            npc=_partner_stage_npc,
            current_location=_dlg_cur_loc,
            time_slot=_dlg_time_slot,
            dialogue_type=_stall_dialogue_type,
            bounty_title=_stall_bounty_title,
            current_minute=_dlg_cur_min,
            scen_key=_dlg_scen_key,
        )

        ring2_peer_section = _fmt_ring2(session.get("pre_turn_stage_npcs") or session.get("current_npcs") or [], active_partners=new_partners)



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
                f"{ring2_peer_section}"
                f"{_stall_note}"
                f"{multi_partner_note}"
                f"{recruitment_prompt}"
                f"{contact_exchange_prompt}"
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
                f"{ring2_peer_section}"
                f"{_stall_note}"

                f"{multi_partner_note}"
                f"{recruitment_prompt}"
                f"{contact_exchange_prompt}"
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

                f"  * CANON INTIMACY, DATING & VIRGINITY INTEGRITY: When an NPC is asked about their romantic history, dating experience, sexual experience, past suitors, virginity, turn-ons, or turn-offs, their dialogue must strictly reflect their canon profile! A virgin character with no past relationship history (empty ex_partners) must NEVER claim to have had past boyfriends, past suitors, foreplay encounters, or 'plenty of practice balancing partners on their schedule'. When asked about turn-ons and turn-offs, they must truthfully state their canon preferences rather than inventing unlisted desires or aversions.\n"
                f"  * PROTAGONIST GENDER & ATTRACTION ALIGNMENT (CRITICAL): The player character ({pl_name}) is canonically {pl_gender.upper()} ({pl_pronoun}). When female NPCs banter or flirt with a male player ({pl_name}), they MUST address him as a man and ask what he is looking for in a girl/woman/partner. NEVER invert attraction or mistakenly ask a male player 'what are you looking for in a guy?'!\n"
                f"  * INFORMATION GATING & NARRATOR BOUNDARIES: Third-person narration must NEVER describe unrevealed intimate anatomy, underwear, or hidden erogenous spots before they have been revealed through player action or intimacy progression. NPCs who are modest or guarded must refuse or deflect intrusive intimate probing unless the player succeeds on a difficult check.\n"

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
                f"{ring2_peer_section}"
                f"{_stall_note}"

                f"{multi_partner_note}"
                f"{recruitment_prompt}"
                f"{contact_exchange_prompt}"
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

        for n in (session.get("pre_turn_stage_npcs") or session.get("current_npcs") or []):

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



    return dialogue_prompt_block

