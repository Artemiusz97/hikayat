"""Phase 5 Hybrid Turn Choice Slot Builder (combat override, priority buttons, 3-band dialogue, utilities)."""
from __future__ import annotations

from typing import Any

import db
import game_engine
from .ordering import (
    _append_utility_free_actions,
    _sanitize_choice_labels,
    _scale_open_exploration_choices,
    order_choices_canonically,
)
from .pipeline import clean_choices_impl
from .stems import _strip_leading_emojis, deduplicate_redundant_choices


def _to_choice_dict(item: Any, default_stat: str = "NONE", default_req: int = 0) -> dict:
    if hasattr(item, "to_dict"):
        d = item.to_dict()
    elif isinstance(item, dict):
        d = dict(item)
    else:
        d = {"label": str(item), "stat": default_stat, "requirement": default_req, "mp_cost": 0}
    d.setdefault("stat", default_stat)
    d.setdefault("requirement", default_req)
    d.setdefault("mp_cost", 0)
    d["_priority_slot"] = True
    d["_server_stamped"] = True
    return d


def _build_active_combat_override(
    *,
    active_monsters: list,
    party: list | None,
    lead_char: dict | None,
    eff_loc: str,
    scen_key: str,
    session: dict,
    new_partners: list,
    eff_npcs: list,
    session_id: int | None,
    eff_departed: list,
) -> list[dict] | None:
    """Generate 100% Python tactical combat buttons when hostile monsters are active."""
    from mechanics.narrative.choice_generator import generate_categorized_combat_actions

    cat = generate_categorized_combat_actions(
        party=party or ([(lead_char, [])] if isinstance(lead_char, dict) else []),
        monster=active_monsters[0],
        location=eff_loc or "area",
        scenario=scen_key,
        session=session,
    )
    enemy_target_name = (
        str(active_monsters[0].get("name") or "Enemy").strip()
        if isinstance(active_monsters[0], dict)
        else "Enemy"
    )
    code_choices = []
    for a in cat.get("attacks", []):
        if isinstance(a, dict):
            d = dict(a)
            d.setdefault("sub_intent", "combat_attack")
            d.setdefault("combat_target", enemy_target_name)
            d["_server_stamped"] = True
            code_choices.append(d)
    for m in cat.get("magic", []):
        if isinstance(m, dict):
            d = dict(m)
            d.setdefault("sub_intent", "combat_magic")
            d.setdefault("combat_target", enemy_target_name)
            d["_server_stamped"] = True
            code_choices.append(d)
    for t in cat.get("tactics", []):
        if isinstance(t, dict):
            d = dict(t)
            d.setdefault("sub_intent", "combat_tactic")
            d.setdefault("combat_target", enemy_target_name)
            d["_server_stamped"] = True
            code_choices.append(d)
    if isinstance(cat.get("flee"), dict):
        f_d = dict(cat["flee"])
        f_d.setdefault("sub_intent", "combat_flee")
        f_d.setdefault("combat_target", enemy_target_name)
        f_d["_server_stamped"] = True
        code_choices.append(f_d)
    if not code_choices:
        return None
    return clean_choices_impl(
        None,
        code_choices,
        scenario=scen_key,
        location=eff_loc,
        char=lead_char,
        dialogue_partner=new_partners,
        current_npcs=eff_npcs,
        session_id=session_id,
        departed_npcs=eff_departed,
    )


def _collect_priority_engine_buttons(
    *,
    raw_choices: list | None,
    cleaned: list[dict],
    stage_info: dict,
    schedule_transition_choice: Any,
    schedule_stay_choice: Any,
    new_partners: list,
    session_id: int | None,
    eff_node_id: Any,
    session: dict,
    actions: list | None,
    in_active_dialogue_turn: bool,
    scen_key: str,
    party: list | None,
) -> tuple[list[dict], list[dict], bool]:
    """Assemble priority buttons (Access Gate, Schedule, Privacy Nudge, Caseboard Deduce, Smartphone Contact)."""
    from mechanics.narrative.clues import evaluate_clue_deduction
    from mechanics.social.relationships import (
        calculate_contact_exchange_dc,
        can_player_dm_contact,
        is_contact_eligible,
    )
    from mechanics.system.phone import scenario_has_smartphone
    from mechanics.world.locations.access_gate import get_privacy_nudge_choice

    priority_buttons: list[dict] = []
    for rc in raw_choices or []:
        if isinstance(rc, dict) and rc.get("_priority_slot") and len(priority_buttons) < 2:
            d_rc = dict(rc)
            d_rc["_server_stamped"] = True
            priority_buttons.append(d_rc)

    active_gate = stage_info.get("access_gate", {}) if isinstance(stage_info, dict) else {}
    has_access_barrier = bool(active_gate.get("gated") and active_gate.get("barrier_choices"))
    if has_access_barrier:
        for bc in active_gate["barrier_choices"][:2]:
            bc_dict = _to_choice_dict(bc)
            bc_dict["_access_barrier"] = True
            priority_buttons.append(bc_dict)
    else:
        if schedule_transition_choice is not None:
            priority_buttons.append(_to_choice_dict(schedule_transition_choice, "NONE", 0))
        if schedule_stay_choice is not None and len(priority_buttons) < 2:
            priority_buttons.append(_to_choice_dict(schedule_stay_choice, "CHA", 11))
        if new_partners and session_id and eff_node_id:
            try:
                priv_choice = get_privacy_nudge_choice(
                    session_id, eff_node_id, new_partners[0], session, actions=actions
                )
                if priv_choice:
                    ch_stat = getattr(priv_choice, "stat", "CHA") or "CHA"
                    ch_req = int(getattr(priv_choice, "requirement", 8) or 8)
                    priv_dict = _to_choice_dict(priv_choice, ch_stat, ch_req)
                    priv_dict["_priority_slot"] = False
                    priv_dict["_band"] = 2
                    priv_dict["_privacy_nudge"] = True
                    priv_dict["is_privacy_nudge"] = True
                    if in_active_dialogue_turn:
                        priority_buttons.append(priv_dict)
                    else:
                        cleaned.append(priv_dict)
            except Exception:
                pass

    # 4b. Caseboard Deductive Synthesis Choice
    if session_id and not in_active_dialogue_turn and len(priority_buttons) < 2:
        try:
            attempted_deduce_this_turn = any(
                isinstance(a, dict) and str(a.get("sub_intent") or "").lower() == "deduce_clues"
                for a in (actions or [])
            )
            if not attempted_deduce_this_turn:
                open_clues = [
                    c
                    for c in (db.get_session_clues(session_id, is_verified=0) or [])
                    if isinstance(c, dict)
                    and not c.get("is_consumed")
                    and c.get("category") != "deduction"
                ]
                if len(open_clues) >= 2:
                    found_pair = None
                    for i in range(len(open_clues)):
                        for j in range(i + 1, len(open_clues)):
                            ca, cb = open_clues[i], open_clues[j]
                            is_valid, _, _ = evaluate_clue_deduction(ca, cb, scen_key=scen_key)
                            if is_valid:
                                found_pair = (ca, cb)
                                break
                        if found_pair:
                            break
                    if found_pair:
                        ca, cb = found_pair
                        t_a = str(ca.get("title") or "Lead A")[:35]
                        t_b = str(cb.get("title") or "Lead B")[:35]
                        priority_buttons.append(
                            {
                                "label": f"🧩 [Synthesize Leads] Cross-reference '{t_a}' & '{t_b}'",
                                "stat": "INT",
                                "requirement": 6,
                                "mp_cost": 0,
                                "intent": "investigate_clue",
                                "sub_intent": "deduce_clues",
                                "clue_pair_ids": [ca["id"], cb["id"]],
                                "_priority_slot": True,
                                "_server_stamped": True,
                            }
                        )
        except Exception:
            pass

    # Smartphone Contact Request Priority Button
    if scenario_has_smartphone(scen_key) and in_active_dialogue_turn:
        try:
            party_names_lower = {
                str(p[0].get("name", "")).strip().lower()
                if isinstance(p, (tuple, list))
                else str(p.get("name", "")).strip().lower()
                for p in (party or [])
                if p
            }
            lore_people = db.get_lorebook(session_id).get("person", []) if session_id else []
            for partner in new_partners:
                if not partner:
                    continue
                p_lower = partner.lower().strip()
                p_first = p_lower.split()[0] if p_lower else ""

                existing_c = db.get_contact(session_id, partner) if session_id else None
                b_info_c = (
                    (existing_c.get("basic_info") or {})
                    if isinstance(existing_c, dict) and isinstance(existing_c.get("basic_info"), dict)
                    else {}
                )
                lore_ent = next(
                    (p for p in lore_people if p.get("name", "").lower() == p_lower), {}
                )
                t_role = str(
                    lore_ent.get("role")
                    or lore_ent.get("occupation")
                    or b_info_c.get("role")
                    or b_info_c.get("occupation")
                    or ""
                ).lower()
                t_desc = str(
                    lore_ent.get("description") or b_info_c.get("description") or ""
                ).lower()
                t_grade = str(lore_ent.get("grade") or b_info_c.get("grade") or "")
                t_srt = str(
                    lore_ent.get("social_role_type") or b_info_c.get("social_role_type") or ""
                )
                if not is_contact_eligible(
                    name=partner,
                    role=t_role,
                    grade=t_grade,
                    description=t_desc,
                    scenario=scen_key,
                    social_role_type=t_srt,
                    session_id=session_id,
                ):
                    continue
                if (
                    can_player_dm_contact(existing_c, party_names_lower, scenario=scen_key)
                    or p_lower in party_names_lower
                ):
                    continue

                attempted_this_turn = False
                attempt_failed = False
                for a in actions or []:
                    if not isinstance(a, dict):
                        continue
                    a_lbl = str(a.get("label") or a.get("text") or "").lower()
                    a_intent = str(a.get("intent") or "").lower()
                    t_npc = str(a.get("target_npc") or "").lower().strip()
                    is_contact_act = a_intent == "phone_contact_exchange" or any(
                        kw in a_lbl for kw in ("phone number", "contact info", "line id")
                    )
                    if is_contact_act:
                        matches = (
                            (
                                t_npc
                                and (
                                    t_npc in p_lower
                                    or p_lower in t_npc
                                    or (p_first and t_npc in p_first)
                                )
                            )
                            or (p_lower in a_lbl or (p_first and p_first in a_lbl))
                            or (not t_npc and len(new_partners) == 1)
                        )
                        if matches:
                            attempted_this_turn = True
                            chk = a.get("check")
                            tier = getattr(chk, "tier", None) or (
                                chk.get("tier") if isinstance(chk, dict) else None
                            )
                            if tier in ("fail", "crit_fail"):
                                attempt_failed = True
                            break

                if attempted_this_turn:
                    if attempt_failed and session_id:
                        db.set_contact_request_cooldown(
                            session_id, partner, hours=24, until_next_day=True
                        )
                    cleaned = [
                        c
                        for c in cleaned
                        if not (
                            any(
                                kw in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                for kw in ("phone number", "contact info", "line id")
                            )
                            and (
                                p_lower
                                in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                or (
                                    p_first
                                    and p_first
                                    in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                )
                                or len(new_partners) == 1
                            )
                        )
                    ]
                    continue

                cd = db.get_contact_request_cooldown(session_id, partner) if session_id else 0
                if cd > 0:
                    cleaned = [
                        c
                        for c in cleaned
                        if not (
                            any(
                                kw in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                for kw in ("phone number", "contact info", "line id")
                            )
                            and (
                                p_lower
                                in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                or (
                                    p_first
                                    and p_first
                                    in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                                )
                                or len(new_partners) == 1
                            )
                        )
                    ]
                else:
                    already_has = any(
                        any(
                            kw in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                            for kw in ("phone number", "contact info", "line id")
                        )
                        and (
                            p_lower
                            in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                            or (
                                p_first
                                and p_first
                                in str(c.get("label", "") if isinstance(c, dict) else c).lower()
                            )
                        )
                        for c in (priority_buttons + cleaned)
                    )
                    if not already_has:
                        wr_ent = (
                            db.get_world_roster_npc(
                                session_id, partner, include_legacy_rosters=False
                            )
                            if (not existing_c and session_id)
                            else None
                        )
                        dc = calculate_contact_exchange_dc(
                            existing_c or wr_ent or lore_ent, scenario=scen_key
                        )
                        priority_buttons.append(
                            {
                                "label": f"📱 Ask for {partner}'s Phone Number / Contact Info",
                                "stat": "CHA",
                                "requirement": dc,
                                "mp_cost": 0,
                                "intent": "phone_contact_exchange",
                                "target_npc": partner,
                                "_priority_slot": True,
                            }
                        )
        except Exception:
            pass

    return priority_buttons, cleaned, has_access_barrier


def build_hybrid_turn_choices(
    raw_choices: list,
    session: dict,
    party: list = None,
    result: dict = None,
    actions: list = None,
    stage_info: dict = None,
    schedule_transition_choice: Any = None,
    schedule_stay_choice: Any = None,
) -> list[dict]:
    """Single-pass deterministic Hybrid Choice Slot Builder (Phase 5)."""
    from mechanics.social.conversation_choices import (
        enforce_conversation_choice_bands,
        pin_dialogue_exit_last,
    )
    from mechanics.social.physical_state import (
        _match_actor_key,
        detect_intimate_disengagement,
        is_erotic_intimate_contact,
    )
    from mechanics.world.waypoints import tag_and_enrich_quest_choices

    session = session if isinstance(session, dict) else {}
    result = result if isinstance(result, dict) else {}
    stage_info = stage_info if isinstance(stage_info, dict) else {}
    session_id = session.get("id")
    scen_key = session.get("scenario", "fantasy")

    lead_char = None
    if party and isinstance(party, list) and party[0]:
        lead_char = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
    elif (
        actions
        and isinstance(actions, list)
        and isinstance(actions[0], dict)
        and isinstance(actions[0].get("char"), dict)
    ):
        lead_char = actions[0]["char"]

    eff_loc = (
        result.get("location")
        or stage_info.get("effective_location")
        or session.get("current_location", "")
    )
    eff_node_id = (
        result.get("current_node_id")
        or stage_info.get("effective_node_id")
        or session.get("current_node_id")
    )
    eff_npcs = (
        result.get("npcs_present")
        if result.get("npcs_present") is not None
        else (stage_info.get("stage_npcs") or session.get("current_npcs") or [])
    )
    new_partners = (
        result.get("dialogue_partners")
        if result.get("dialogue_partners") is not None
        else (
            stage_info.get("new_partners")
            if stage_info.get("new_partners") is not None
            else (session.get("dialogue_partners") or [])
        )
    )
    if isinstance(new_partners, str):
        new_partners = [new_partners] if new_partners.strip() else []
    eff_departed = (
        result.get("departed_characters")
        or result.get("npc_departures")
        or stage_info.get("schedule_departed_npcs")
        or []
    )

    # 1. Active Combat Override
    active_monsters = game_engine.get_active_enemies(result) or game_engine.get_active_enemies(
        session
    )
    if active_monsters:
        combat_override = _build_active_combat_override(
            active_monsters=active_monsters,
            party=party,
            lead_char=lead_char,
            eff_loc=eff_loc,
            scen_key=scen_key,
            session=session,
            new_partners=new_partners,
            eff_npcs=eff_npcs,
            session_id=session_id,
            eff_departed=eff_departed,
        )
        if combat_override:
            return combat_override

    # 2. Check Physical State for Intimacy, Clothing Redress, and Tether Restraints
    phys = (
        result.get("_physical_state")
        or session.get("_physical_state")
        or (db.get_session_physical_state(session_id) if session_id else None)
        or session.get("physical_state")
        or {}
    )
    result["_physical_state"] = phys
    actors = phys.get("actors", {}) if isinstance(phys, dict) else {}
    ic_str = str(phys.get("intimate_contact", "") if isinstance(phys, dict) else "")
    in_active_intimate_turn = bool(
        not detect_intimate_disengagement(actions or [])
        and (is_erotic_intimate_contact(ic_str) or "aftercare" in ic_str.lower())
    )
    in_active_dialogue_turn = bool(new_partners)

    # 2a. Grappled / Restrained Override
    carrying_tether = None
    if not in_active_intimate_turn and isinstance(lead_char, dict) and lead_char.get("name"):
        m_key = _match_actor_key(lead_char["name"], actors)
        if m_key in actors:
            lead_phys = actors[m_key]
            tether = str(lead_phys.get("tether", "")).strip()
            if tether and tether.lower() not in ("none", "false", ""):
                if any(w in tether.lower() for w in ("carry", "holding", "carrying")):
                    carrying_tether = tether
                else:
                    return [
                        {
                            "label": f"Struggle with all your might to break free from: {tether}",
                            "stat": "STR",
                            "requirement": 14,
                            "mp_cost": 0,
                        },
                        {
                            "label": f"Attempt a swift maneuver to slip out of: {tether}",
                            "stat": "AGI",
                            "requirement": 14,
                            "mp_cost": 0,
                        },
                    ]

    # 3. Single-pass clean & enrich of raw LLM choices
    cleaned = clean_choices_impl(
        None,
        raw_choices or [],
        scenario=scen_key,
        location=eff_loc,
        char=lead_char,
        dialogue_partner=new_partners,
        current_npcs=eff_npcs,
        session_id=session_id,
        departed_npcs=eff_departed,
    )

    if in_active_intimate_turn:
        intimate_out = _sanitize_choice_labels(cleaned[:5])
        for _ic in intimate_out:
            if isinstance(_ic, dict):
                _ic["_intimate_scene_choice"] = True
        return intimate_out

    # 3b. Guarantee Quest / Story Climax Action Choices when at an active waypoint
    _adv_qids_raw: list[str] = []
    if isinstance(result, dict):
        _adv_qids_raw.extend(
            str(q).strip() for q in (result.get("_quests_advanced_this_turn") or []) if q
        )
    if isinstance(session, dict):
        _adv_qids_raw.extend(
            str(q).strip() for q in (session.get("_just_advanced_quest_ids") or []) if q
        )
        if isinstance(session.get("extra"), dict):
            _adv_qids_raw.extend(
                str(q).strip()
                for q in (session["extra"].get("_just_advanced_quest_ids") or [])
                if q
            )
    _adv_qids_turn = list(dict.fromkeys(_adv_qids_raw))
    _need_dialogue_handoff = bool(
        in_active_dialogue_turn
        and _adv_qids_turn
        and not any(isinstance(c, dict) and c.get("_quest_dialogue_handoff") for c in cleaned)
    )
    if (
        session_id
        and eff_loc
        and (
            not any(isinstance(c, dict) and c.get("is_quest_action") for c in cleaned)
            or not any(
                isinstance(c, dict)
                and c.get("is_quest_action")
                and c.get("is_story_quest")
                and not c.get("is_premature_climax")
                for c in cleaned
            )
            or _need_dialogue_handoff
        )
    ):
        try:
            tagged_fb = tag_and_enrich_quest_choices(
                cleaned,
                session_id,
                eff_loc,
                scen_key=scen_key,
                char=lead_char,
                dialogue_partner=new_partners,
                current_npcs=eff_npcs,
                allow_fallback=True,
                just_advanced_quest_ids=_adv_qids_turn,
            )
            if tagged_fb:
                for tc in tagged_fb:
                    if isinstance(tc, dict) and tc.get("label"):
                        tc["label"] = _strip_leading_emojis(tc["label"])[:190]
                cleaned = deduplicate_redundant_choices(tagged_fb)
        except Exception:
            pass

    # 4. Priority Engine Buttons
    priority_buttons, cleaned, has_access_barrier = _collect_priority_engine_buttons(
        raw_choices=raw_choices,
        cleaned=cleaned,
        stage_info=stage_info,
        schedule_transition_choice=schedule_transition_choice,
        schedule_stay_choice=schedule_stay_choice,
        new_partners=new_partners,
        session_id=session_id,
        eff_node_id=eff_node_id,
        session=session,
        actions=actions,
        in_active_dialogue_turn=in_active_dialogue_turn,
        scen_key=scen_key,
        party=party,
    )

    # 4c. Active Non-Intimate Conversation -> 3-Band Architecture
    if in_active_dialogue_turn and not in_active_intimate_turn and not has_access_barrier:
        sess_for_bands = dict(session)
        if eff_loc:
            sess_for_bands["current_location"] = eff_loc
        if eff_node_id:
            sess_for_bands["current_node_id"] = eff_node_id
        merged_choices = enforce_conversation_choice_bands(
            cleaned_choices=cleaned,
            session=sess_for_bands,
            partners=new_partners,
            party=party,
            current_npcs=eff_npcs,
            priority_buttons=priority_buttons,
            actions=actions,
        )
    else:
        seen_labels = set()
        merged_choices = []
        for pc in priority_buttons:
            if len(merged_choices) >= 2:
                break
            lbl_k = str(pc.get("label", "")).strip().lower()
            if lbl_k and lbl_k not in seen_labels:
                seen_labels.add(lbl_k)
                pc["_priority_slot"] = True
                pc["_server_stamped"] = True
                merged_choices.append(pc)

        for cc in cleaned:
            if not isinstance(cc, dict):
                continue
            lbl_k = str(cc.get("label", "")).strip().lower()
            if not lbl_k or lbl_k in seen_labels:
                continue
            if carrying_tether and any(w in lbl_k for w in ("attack", "strike")):
                continue
            seen_labels.add(lbl_k)
            merged_choices.append(cc)

        merged_choices = deduplicate_redundant_choices(
            merged_choices,
            ignore_names=list(new_partners or [])
            + [game_engine._get_npc_name(n) for n in (eff_npcs or []) if n],
        )
        merged_choices = _scale_open_exploration_choices(merged_choices, eff_npcs)

    # 5. Utility Free Actions
    merged_choices = _append_utility_free_actions(
        merged_choices,
        party=party,
        actors=actors,
        carrying_tether=carrying_tether,
        in_active_intimate_turn=in_active_intimate_turn,
        phys=phys,
    )

    if in_active_dialogue_turn and not in_active_intimate_turn and not has_access_barrier:
        merged_choices = pin_dialogue_exit_last(merged_choices, new_partners, max_total=8)

    merged_choices = order_choices_canonically(
        merged_choices,
        in_dialogue=in_active_dialogue_turn,
    )
    return _sanitize_choice_labels(merged_choices)
