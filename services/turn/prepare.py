from __future__ import annotations

import json
import random
import re
import db
from db import adb
import game_engine
import scenario_data
from typing import Any, Dict, List, Optional
from .models import _get_turn_service, log, logger

async def _reconcile_client_direct_choice(
    session_id: int,
    user_id: int,
    session: Optional[Dict[str, Any]],
    char: Dict[str, Any],
    choices: Optional[List[Dict[str, Any]]],
    raw_dc: Dict[str, Any],
    combat_target: Optional[str],
    is_stealth_req: bool,
    req_intent: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Reconcile an untrusted HTTP client `direct_choice` dict against authoritative
    server choices, tactical combat decks, spell registry, or world-map nodes.
    """
    cleaned = dict(raw_dc)
    raw_lbl = str(cleaned.get("label") or cleaned.get("text") or "").strip()
    raw_id = str(cleaned.get("id") or "").strip()

    # 1. Exact match against server-persisted session choices
    if isinstance(choices, list):
        for sc in choices:
            if not isinstance(sc, dict) and not hasattr(sc, "get"):
                continue
            sc_id = str(sc.get("id") or "").strip()
            sc_lbl = str(sc.get("label") or sc.get("text") or "").strip()
            if (raw_id and sc_id and raw_id == sc_id) or (raw_lbl and sc_lbl and raw_lbl == sc_lbl):
                return dict(sc)

    # Strip client mechanical overrides & privileged quest/spoofing keys
    for _strip_k in (
        "stat",
        "requirement",
        "hit_chance",
        "is_basic_strike",
        "free_pass",
        "_mp_already_deducted",
        "_gold_already_deducted",
        "quest_id",
        "sub_obj_id",
        "stage_index",
        "is_quest_action",
        "is_climax_action",
        "is_story_quest",
        "_python_verified_quest",
        "triggers_loot_roll",
        "breakthrough_leveraged",
        "_server_stamped",
        "clue_pair_ids",
        "approach",
        "is_anomaly_inquiry",
        "topic_id",
        "category",
        "is_covert_ability",
        "is_direct_reply",
        "_seed_reconciled",
        "_pact_cast_meta",
        "pact_hp_cost",
        "pact_credit_cost",
        "is_lethal_overdraw",
        "appraisal_state",
        "_epistemic_verified",
        "hush_gold_override",
        "effective_dc_mod",
        "telltale_revealed",
        "_activity_reconciled",
    ):
        cleaned.pop(_strip_k, None)

    _combat_tactic_ok = (
        isinstance(session, dict)
        and bool(session.get("nearby_enemies"))
        and str(cleaned.get("incursion_action") or "").strip().lower()
        in {
            "subdue",
            "combat_persuade",
            "sever_tether",
            "folklore_offering_rite",
            "exploit_taboo",
            "invoke_patron_authority",
            "accept_boss_pact_surrender",
        }
    )
    if not _combat_tactic_ok:
        for _inc_k in ("incursion_action", "incursion_id", "breach_id"):
            cleaned.pop(_inc_k, None)

    _site_act_ok = (
        isinstance(session, dict)
        and not session.get("nearby_enemies")
        and str(cleaned.get("intent") or "").strip().lower() == "anomalous_site_action"
        and str(cleaned.get("site_action") or "").strip().lower() in {"puzzle_step", "harvest", "overdraw"}
        and bool(cleaned.get("site_id"))
    )
    if not _site_act_ok:
        for _sk_k in ("site_action", "site_id", "step_index", "use_ward", "ward_item_name"):
            cleaned.pop(_sk_k, None)

    inventory = await adb(db.get_inventory, user_id) or []

    # 2. Match against server-generated Tactical Combat Deck when enemies are present
    enemies = (session.get("nearby_enemies") if isinstance(session, dict) else None) or []
    active_enemies = [e for e in enemies if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
    if active_enemies:
        try:
            from mechanics.narrative.choice_generator import generate_categorized_combat_actions
            target_e = None
            if combat_target:
                target_e = next(
                    (e for e in active_enemies if str(e.get("name") or "").strip().lower() == str(combat_target).strip().lower() or (e.get("id") is not None and str(e.get("id")) == str(combat_target))),
                    None,
                )
            cand_enemies = [target_e] if target_e else active_enemies
            party_arg = [(dict(char), list(inventory))]
            for enem in cand_enemies:
                deck = generate_categorized_combat_actions(
                    party=party_arg,
                    monster=enem,
                    location=(session.get("current_location") if isinstance(session, dict) else None) or "area",
                    scenario=(session.get("scenario") if isinstance(session, dict) else None) or "fantasy",
                    session=session,
                ) or {}
                deck_cards: List[Dict[str, Any]] = []
                for k_list in ("attacks", "magic", "tactics"):
                    deck_cards.extend([c for c in (deck.get(k_list) or []) if isinstance(c, dict)])
                if isinstance(deck.get("flee"), dict):
                    deck_cards.append(deck["flee"])
                _dc_intent = str(cleaned.get("intent") or req_intent or "").strip().lower()
                _dc_ctype = str(cleaned.get("choice_type") or "").strip().upper()
                for dc_card in deck_cards:
                    dc_lbl = str(dc_card.get("label") or dc_card.get("text") or "").strip()
                    dc_ctype = str(dc_card.get("choice_type") or "").strip().upper()
                    dc_stance = str(dc_card.get("stance") or "").strip().lower()
                    dc_cat = str(dc_card.get("action_category") or "").strip().lower()
                    if (
                        (raw_lbl and dc_lbl and raw_lbl == dc_lbl)
                        or (cleaned.get("spell_id") and dc_card.get("spell_id") == cleaned.get("spell_id"))
                        or (cleaned.get("incursion_action") and dc_card.get("incursion_action") == cleaned.get("incursion_action"))
                        or ((_dc_intent == "stealth_hide" or _dc_ctype == "STEALTH_VANISH") and dc_ctype == "STEALTH_VANISH")
                        or (_dc_intent == "stealth_backstab" and dc_stance == "stealth" and dc_cat == "attack")
                    ):
                        matched_card = dict(dc_card)
                        if combat_target and not matched_card.get("combat_target"):
                            matched_card["combat_target"] = combat_target
                        return matched_card
        except Exception as _deck_err:
            log.debug("Combat deck reconciliation skipped: %s", _deck_err)

    # 3. Authoritative Spell Registry lookup when `spell_id` is supplied
    spell_id = str(cleaned.get("spell_id") or "").strip()
    if spell_id:
        if spell_id.startswith("pact_"):
            if not session_id:
                cleaned.pop("spell_id", None)
                sp_def = None
            else:
                try:
                    from mechanics.pacts import build_pact_spell_def, build_pact_spell_id, get_patron_by_id
                    active_pacts_rec = await adb(db.get_player_active_pacts, int(session_id), int(user_id))
                    scen_rec = str((session or {}).get("scenario") or "anomalous_incursions")
                    cont_rec = list((session or {}).get("contained_anomalies_log") or []) if isinstance(session, dict) else []
                    sp_def = None
                    for p_row_rec in (active_pacts_rec or []):
                        pat_rec = get_patron_by_id(str(p_row_rec.get("patron_id") or ""), scenario_or_key=scen_rec, contained_records=cont_rec)
                        if pat_rec and build_pact_spell_id(pat_rec, int(p_row_rec.get("tier") or 1)) == spell_id:
                            sp_def = build_pact_spell_def(pat_rec, int(p_row_rec.get("tier") or 1))
                            cleaned["is_pact_skill"] = True
                            cleaned["contract_key"] = p_row_rec.get("contract_key", "")
                            cleaned["patron_id"] = pat_rec["patron_id"]
                            break
                except Exception:
                    sp_def = None
        else:
            sp_def = None
            try:
                from mechanics.combat.spells.registry import get_spell
                from mechanics.combat.spells.awakened_kits import get_actor_spell
                skill_prog = await adb(db.get_skill_progress, char)
                sp_def = get_actor_spell(spell_id, skill_prog) or get_spell(spell_id)
            except Exception:
                sp_def = None
        if isinstance(sp_def, dict):
            sp_stat = str(sp_def.get("stat") or "INT").upper()
            if sp_stat not in db.STAT_COLUMN:
                sp_stat = "INT"
            cleaned["stat"] = sp_stat
            cleaned["requirement"] = max(5, int(sp_def.get("requirement", 5) or 5))
            cleaned["mp_cost"] = int(sp_def.get("mp_cost", 0) or 0)
            cleaned["is_basic_strike"] = spell_id.startswith("awk_basic_")
            cleaned["action_category"] = cleaned.get("action_category") or "magic"
            cleaned["label"] = raw_lbl or str(sp_def.get("name") or spell_id)
            return cleaned
        cleaned.pop("spell_id", None)

    # 3b. Authoritative Realty Property Deed Purchase Reconciliation
    if not active_enemies and session_id and (
        str(cleaned.get("intent") or "").strip().lower() == "property_purchase"
        or cleaned.get("property_id")
    ):
        from mechanics.world.locations.realty_catalog import resolve_realty_entry, find_realty_by_node_id
        prop_id_req = str(cleaned.get("property_id") or "").strip()
        cat_entry = resolve_realty_entry(prop_id_req, session_or_id=session or session_id) if prop_id_req else None
        if not cat_entry and cleaned.get("target_node_id"):
            cat_entry = find_realty_by_node_id(str(cleaned["target_node_id"]), session_or_id=session or session_id)
        if cat_entry:
            cleaned["stat"] = "FREE"
            cleaned["requirement"] = 0
            cleaned["mp_cost"] = 0
            cleaned["intent"] = "property_purchase"
            cleaned["action_category"] = "movement"
            cleaned["property_id"] = cat_entry["property_id"]
            cleaned["price"] = int(cat_entry["price"])
            cleaned["target_node_id"] = cat_entry["bedroom_node_id"]
            cleaned["target_location"] = f"{cat_entry['zone_name']} ➔ {cat_entry['name']} ➔ {cat_entry['bedroom_name']}"
            cleaned["label"] = f"[For Sale — {cat_entry['price']}g] Purchase {cat_entry['name']} Deed"
            return cleaned
        cleaned.pop("property_id", None)
        cleaned.pop("price", None)

    # 4. Verified World Node Fast-Travel
    if cleaned.get("target_node_id") and session_id:
        cand_nid = str(cleaned["target_node_id"])
        wn_row = await adb(db.get_world_node, session_id, cand_nid)
        if wn_row and not active_enemies:
            cleaned["stat"] = "FREE"
            cleaned["requirement"] = 0
            cleaned["mp_cost"] = 0
            cleaned["intent"] = cleaned.get("intent") or "fast_travel"
            cleaned["action_category"] = cleaned.get("action_category") or "movement"
            cleaned["label"] = raw_lbl or f"Travel to {wn_row.get('name', cand_nid)}"
            return cleaned
        cleaned.pop("target_node_id", None)

    # 5. Verified Inventory Item Use (ownership validated strictly below at stat == 'ITEM')
    if str(raw_dc.get("stat") or "").upper() == "ITEM" or cleaned.get("item_name"):
        cleaned["stat"] = "ITEM"
        cleaned["requirement"] = 0
        cleaned["mp_cost"] = 0
        cleaned["label"] = raw_lbl or f"Use {cleaned.get('item_name', 'item')}"
        return cleaned

    # 6. Verified Non-Combat Wait/Rest or Present-NPC Dialogue Initiation
    raw_intent = str(cleaned.get("intent") or req_intent or "").strip().lower()
    if not active_enemies and raw_intent in ("wait_time", "rest_sleep"):
        cleaned["stat"] = "NONE"
        cleaned["requirement"] = 0
        cleaned["mp_cost"] = 0
        cleaned["label"] = raw_lbl or "Wait"
        return cleaned
    if not active_enemies and (raw_intent == "dialogue_init" or raw_dc.get("_npc_speak_choice")):
        t_npc = str(cleaned.get("target_npc") or "").strip().lower()
        curr_npcs = (session.get("current_npcs") if isinstance(session, dict) else None) or []
        npc_present = any(
            t_npc and t_npc == str(game_engine._get_npc_name(n) or "").strip().lower()
            for n in curr_npcs
        )
        if npc_present:
            cleaned["stat"] = "NONE"
            cleaned["requirement"] = 0
            cleaned["mp_cost"] = 0
            cleaned["label"] = raw_lbl or f"Speak with {cleaned.get('target_npc')}"
            return cleaned
    if (
        not active_enemies
        and isinstance(session, dict)
        and (
            raw_intent == "dialogue_exit"
            or bool(raw_dc.get("ends_dialogue"))
            or bool(raw_dc.get("_pinned_dialogue_exit"))
        )
    ):
        from mechanics.social.conversation_choices import build_pinned_leave_choice
        from mechanics.world.mobility import get_session_dialogue_partners
        active_dps = get_session_dialogue_partners(session)
        if active_dps:
            exit_card = build_pinned_leave_choice(active_dps)
            if raw_lbl:
                exit_card["label"] = raw_lbl
            return exit_card

    if not active_enemies and isinstance(session, dict) and isinstance(session.get("_dealt_social_seeds"), list):
        cand_tid = str(raw_dc.get("topic_id") or "").strip()
        if cand_tid:
            matched_seed = next(
                (
                    s for s in session["_dealt_social_seeds"]
                    if isinstance(s, dict) and str(s.get("topic_id") or "").strip() == cand_tid
                ),
                None,
            )
            if matched_seed:
                s_stat = str(matched_seed.get("stat") or "CHA").upper()
                cleaned["stat"] = s_stat if s_stat in db.STAT_COLUMN else "CHA"
                cleaned["requirement"] = max(3, min(12, int(matched_seed.get("dc") or 6)))
                cleaned["mp_cost"] = max(0, int(matched_seed.get("mp_cost") or 0))
                cleaned["topic_id"] = cand_tid
                cleaned["category"] = str(matched_seed.get("category") or cleaned.get("category") or "")
                cleaned["target_npc"] = str(matched_seed.get("target_npc") or cleaned.get("target_npc") or "")
                cleaned["is_covert_ability"] = bool(matched_seed.get("is_covert_ability"))
                cleaned["is_direct_reply"] = bool(matched_seed.get("is_direct_reply"))
                cleaned["_seed_reconciled"] = True
                cleaned["label"] = raw_lbl or "Speak"
                return cleaned

    # 6B. Server-side Join Activity seed reconciliation (F6.1)
    cand_act_key = str(raw_dc.get("activity_key") or "").strip().lower()
    if not active_enemies and (raw_intent == "join_activity" or cand_act_key):
        stage_pool: List[Dict[str, Any]] = []
        if isinstance(session, dict):
            for src_k in ("pre_turn_stage_npcs", "current_npcs"):
                for _sn in (session.get(src_k) or []):
                    if isinstance(_sn, dict):
                        stage_pool.append(_sn)
        cand_tgt_low = str(raw_dc.get("target_npc") or cleaned.get("target_npc") or "").strip().lower()
        matched_npc = None
        matched_act_seed = None
        for _sn in stage_pool:
            _jseed = _sn.get("join_activity_seed")
            if not isinstance(_jseed, dict):
                continue
            _sn_keys = {
                str(_sn.get("name") or "").strip().lower(),
                str(_sn.get("npc_id") or "").strip().lower(),
                str(_sn.get("person_key") or "").strip().lower(),
            }
            _sk = str(_jseed.get("activity_key") or "").strip().lower()
            if (cand_tgt_low and cand_tgt_low in _sn_keys) or (cand_act_key and cand_act_key == _sk):
                matched_npc = _sn
                matched_act_seed = _jseed
                break
        if matched_act_seed is not None and matched_npc is not None:
            from mechanics.social.activity_tags import get_activity_situational_dc_mod
            _a_stat = str(matched_act_seed.get("stat") or "CHA").strip().upper()
            _a_dc = max(5, min(8, int(matched_act_seed.get("dc") or 6)))
            _a_dc = max(5, min(8, _a_dc + get_activity_situational_dc_mod(matched_npc, "join_activity", raw_lbl)))
            cleaned["stat"] = _a_stat if _a_stat in db.STAT_COLUMN else "CHA"
            cleaned["requirement"] = _a_dc
            cleaned["mp_cost"] = 0
            cleaned["intent"] = "join_activity"
            cleaned["action_category"] = "social"
            cleaned["target_npc"] = str(matched_npc.get("name") or raw_dc.get("target_npc") or "")
            cleaned["activity_key"] = str(matched_act_seed.get("activity_key") or cand_act_key)
            cleaned["_activity_reconciled"] = True
            cleaned["label"] = raw_lbl or f"Join {cleaned['target_npc']} ({cleaned['activity_key']})"
            return cleaned

    # 6C. Server-side Epistemic Containment & Hush Bribe verification (D-6 / B16)
    _CONTAINMENT_SUB_INTENTS = {
        "hush_bribe",
        "threaten_silence",
        "confide",
        "deny",
        "present_proof",
        "destroy_proof",
        "discretion_request",
        "use_leverage",
        "warn_target",
    }
    cand_sub_intent = str(raw_dc.get("sub_intent") or cleaned.get("sub_intent") or "").strip().lower()
    if not active_enemies and (raw_intent == "epistemic_containment" or cand_sub_intent in _CONTAINMENT_SUB_INTENTS):
        eff_sub = cand_sub_intent if cand_sub_intent in _CONTAINMENT_SUB_INTENTS else "discretion_request"
        cand_fkey = str(raw_dc.get("fact_key") or cleaned.get("fact_key") or "").strip()
        cand_tgt = str(raw_dc.get("target_npc") or cleaned.get("target_npc") or "").strip()
        cand_tgt_k = cand_tgt.lower().replace(" ", "_")

        def _load_epistemic_containment_bundle() -> tuple[Any, bool, int]:
            if not (session_id and cand_fkey):
                return None, False, 0
            with db.ReadUnitOfWork():
                f_row = db.get_epistemic_fact(session_id, cand_fkey)
                t_rows = (
                    db.get_epistemic_knowledge_rows(session_id, fact_key=cand_fkey, holder_actor_key=cand_tgt_k)
                    if (f_row and cand_tgt_k)
                    else []
                )
                t_know = t_rows[0] if t_rows else None
                forged_hid = bool(
                    eff_sub in ("hush_bribe", "threaten_silence", "discretion_request", "deny")
                    and isinstance(t_know, dict)
                    and int(t_know.get("player_aware") or 0) == 0
                )
                ex_dc = 0
                if (
                    f_row
                    and not forged_hid
                    and eff_sub in ("hush_bribe", "threaten_silence", "discretion_request")
                    and cand_tgt_k
                ):
                    subj_k = str(f_row.get("subject_actor_key") or "").strip().lower().replace(" ", "_")
                    if subj_k:
                        from mechanics.social import relationship_graph as _rg_ep
                        from mechanics.social.epistemic_engine import _is_kin_roommate_or_best_friend
                        _ties = _rg_ep.get_ties(session_id, cand_tgt_k) if session_id else []
                        _contacts = db.get_contacts(session_id) if session_id else []
                        if _is_kin_roommate_or_best_friend(
                            subj_k, cand_tgt_k, social_ties=_ties, contacts=_contacts
                        ):
                            ex_dc = 2
                return f_row, forged_hid, ex_dc

        fact_row, _forged_hidden, _pre_extra_dc = await adb(_load_epistemic_containment_bundle)
        if not fact_row or _forged_hidden:
            for _ek in (
                "intent",
                "sub_intent",
                "fact_key",
                "target_npc",
                "hush_gold",
                "hush_gold_override",
                "effective_dc_mod",
                "_epistemic_verified",
            ):
                cleaned.pop(_ek, None)
        else:
            severity_val = int((fact_row or {}).get("severity") or 1)
            extra_dc = _pre_extra_dc
            req_gold = 0
            if eff_sub == "hush_bribe":
                req_gold = max(25, 25 * max(1, severity_val))
                client_gold = int(raw_dc.get("hush_gold") or 0)
                if client_gold > req_gold:
                    req_gold = client_gold
                char_gold = int((char or {}).get("gold") or 0)
                if char_gold < req_gold:
                    raise ValueError(f"Insufficient gold for hush bribe ({char_gold}g < {req_gold}g)")
            if eff_sub == "threaten_silence":
                e_stat, base_dc = "STR", 7
            elif eff_sub in ("present_proof", "destroy_proof"):
                e_stat, base_dc = "INT", 6
            else:
                e_stat, base_dc = "CHA", 6 + (1 if eff_sub == "use_leverage" else 0)
            cleaned.update({
                "stat": e_stat,
                "requirement": max(5, min(14, base_dc + extra_dc)),
                "mp_cost": 0,
                "intent": "epistemic_containment",
                "sub_intent": eff_sub,
                "fact_key": cand_fkey,
                "target_npc": cand_tgt,
                "hush_gold": req_gold,
                "effective_dc_mod": extra_dc,
                "_epistemic_verified": True,
                "action_category": "social",
                "label": raw_lbl or f"{eff_sub.replace('_', ' ').title()}",
            })
            return cleaned

    # 6D. Server-side Anomalous Site Puzzle / Harvest Reconciliation
    if (
        not active_enemies
        and session_id
        and raw_intent == "anomalous_site_action"
        and str(cleaned.get("site_action") or "").strip().lower() in ("puzzle_step", "harvest", "overdraw")
        and cleaned.get("site_id")
    ):
        try:
            from mechanics.world.anomalous_sites import build_site_harvest_choices, build_site_puzzle_choices
            _cur_day_s = int((session or {}).get("current_day", 1) or 1)
            _cur_min_s = int((session or {}).get("current_minute", 720) or 720)
            _cur_loc_s = str((session or {}).get("current_location") or "")
            _cur_nid_s = str((session or {}).get("current_node_id") or "")
            _cur_scen_s = str((session or {}).get("scenario") or "anomalous_incursions")

            def _build_site_reconcile_cards() -> list:
                return (
                    build_site_puzzle_choices(
                        int(session_id),
                        location_str=_cur_loc_s,
                        node_id=_cur_nid_s,
                        scen_key=_cur_scen_s,
                        current_day=_cur_day_s,
                        current_minute=_cur_min_s,
                        inventory=inventory,
                        session=session,
                    )
                    + build_site_harvest_choices(
                        int(session_id),
                        location_str=_cur_loc_s,
                        node_id=_cur_nid_s,
                        scen_key=_cur_scen_s,
                        current_day=_cur_day_s,
                    )
                )

            _cand_cards_s = await adb(_build_site_reconcile_cards)
            _req_sa = str(cleaned.get("site_action") or "").strip().lower()
            _req_sid = str(cleaned.get("site_id") or "").strip().lower()
            _req_ward = bool(cleaned.get("use_ward"))
            _matched_s = next(
                (
                    c for c in _cand_cards_s
                    if str(c.get("site_action") or "").lower() == _req_sa
                    and str(c.get("site_id") or "").lower() == _req_sid
                    and (_req_sa != "puzzle_step" or bool(c.get("use_ward")) == _req_ward)
                ),
                None,
            )
            if _matched_s:
                cleaned.update(_matched_s)
                return cleaned
        except Exception:
            pass
        for _sk_k in ("site_action", "site_id", "step_index", "use_ward", "ward_item_name"):
            cleaned.pop(_sk_k, None)

    # 6E. Verified Examine Ground Item / Pickable Prop Pickup Reconciliation
    pickup_cand_raw = str(cleaned.get("pickup_item_name") or "").strip()
    if pickup_cand_raw:
        matched_pickup_raw = None
        matched_pickup_display = None
        try:
            from mechanics.narrative.examine import _PICKABLE_PROP_KEYWORDS, _strip_item_tags

            phys_pick = (
                (session.get("physical_state") if isinstance(session, dict) else None)
                or (await adb(db.get_session_physical_state, session_id) if session_id else None)
                or {}
            )
            pickup_cand_clean_low = _strip_item_tags(pickup_cand_raw).lower()
            pickup_cand_raw_low = pickup_cand_raw.lower()

            for d_item in (phys_pick.get("dropped_items") or [] if isinstance(phys_pick, dict) else []):
                raw_d = str(d_item.get("name") or "").strip() if isinstance(d_item, dict) else str(d_item or "").strip()
                if not raw_d:
                    continue
                clean_d = _strip_item_tags(raw_d)
                if raw_d.lower() == pickup_cand_raw_low or (clean_d and clean_d.lower() == pickup_cand_clean_low):
                    matched_pickup_raw = raw_d
                    matched_pickup_display = clean_d or raw_d
                    break

            if not matched_pickup_raw and isinstance(phys_pick, dict) and isinstance(phys_pick.get("props"), dict):
                for pk, pv in phys_pick["props"].items():
                    raw_pk = str(pk or "").strip()
                    if not raw_pk:
                        continue
                    pv_low = str(pv or "").strip().lower()
                    if not any(kw in pv_low for kw in _PICKABLE_PROP_KEYWORDS):
                        continue
                    clean_pk = _strip_item_tags(raw_pk)
                    if raw_pk.lower() == pickup_cand_raw_low or (clean_pk and clean_pk.lower() == pickup_cand_clean_low):
                        matched_pickup_raw = raw_pk
                        matched_pickup_display = clean_pk or raw_pk
                        break
        except Exception:
            matched_pickup_raw = None

        if matched_pickup_raw:
            cleaned.update({
                "label": raw_lbl or f"Pick up {matched_pickup_display}",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "general_action",
                "sub_intent": "pickup_item",
                "pickup_item_name": matched_pickup_raw,
                "_server_stamped": True,
            })
            return cleaned
        cleaned.pop("pickup_item_name", None)

    # 7. UI Tactical/Stealth/Dialogue Fallback Cards & Unmatched Payloads -> Deterministic Rolled Check (DC >= 6, NEVER FREE/NONE)
    act_cat_hint = str(cleaned.get("action_category") or "").strip().lower()
    choice_type_hint = str(cleaned.get("choice_type") or "").strip().lower()
    raw_stat_hint = str(raw_dc.get("stat") or "").strip().upper()
    try:
        raw_req_val = int(raw_dc.get("requirement", 0) or 0)
    except (TypeError, ValueError):
        raw_req_val = 0
    enforced_req = max(6, min(20, raw_req_val))
    if not active_enemies and isinstance(session, dict):
        _tgt_act_low = str(cleaned.get("target_npc") or raw_dc.get("target_npc") or "").strip().lower()
        _act_npcs = list(session.get("pre_turn_stage_npcs") or session.get("current_npcs") or [])
        _matched_act_npc = next(
            (
                _an for _an in _act_npcs
                if isinstance(_an, dict) and _tgt_act_low and _tgt_act_low in {
                    str(_an.get("name") or "").strip().lower(),
                    str(_an.get("npc_id") or "").strip().lower(),
                    str(_an.get("person_key") or "").strip().lower(),
                }
            ),
            None,
        )
        if _matched_act_npc is not None:
            from mechanics.social.activity_tags import get_activity_situational_dc_mod
            enforced_req = max(
                4,
                min(20, enforced_req + get_activity_situational_dc_mod(_matched_act_npc, str(cleaned.get("intent") or raw_intent or ""), raw_lbl)),
            )

    inferred_stat = ""
    try:
        from mechanics.narrative.intent import IntentCategory, classify_action_intent
        parsed_intent = classify_action_intent(raw_lbl or "Act")
        p_cat = getattr(parsed_intent, "category", None)
        if p_cat in (
            IntentCategory.AFFECTION_TOUCH,
            IntentCategory.ROMANTIC_CONFESSION,
            IntentCategory.SOCIAL_INVITE,
            IntentCategory.PARTY_RECRUIT,
        ):
            inferred_stat = "CHA"
        elif p_cat == IntentCategory.STEALTH_COVERT:
            inferred_stat = "INT" if getattr(parsed_intent, "sub_target", "") == "lockpick" else "AGI"
        elif p_cat == IntentCategory.INVESTIGATE_CLUE:
            inferred_stat = "PER"
    except Exception:
        inferred_stat = ""

    if is_stealth_req or act_cat_hint == "stealth":
        c_stat = "AGI"
    elif active_enemies or act_cat_hint in ("attack", "tactic", "combat_attack"):
        c_stat = raw_stat_hint if raw_stat_hint in db.STAT_COLUMN else "STR"
    elif inferred_stat in db.STAT_COLUMN:
        c_stat = inferred_stat
    elif choice_type_hint in ("dialogue", "social", "intimate", "romance"):
        c_stat = "CHA"
    elif raw_stat_hint in db.STAT_COLUMN:
        c_stat = raw_stat_hint
    else:
        c_stat = "PER"

    cleaned.update({
        "stat": c_stat,
        "requirement": enforced_req,
        "mp_cost": max(0, int(cleaned.get("mp_cost", 0) or 0)),
        "action_category": cleaned.get("action_category") or ("dialogue" if c_stat == "CHA" else "custom"),
        "intent": cleaned.get("intent") or "general_action",
        "label": raw_lbl or "Action",
    })
    return cleaned


async def prepare_and_roll_action(
    session_id: int,
    user_id: int,
    raw_pick: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    char: Optional[Dict[str, Any]] = None,
    choices: Optional[List[Dict[str, Any]]] = None,
    enforce_explicit_mp: bool = True,
) -> Dict[str, Any]:
    """
    Single source of truth for pre-turn action classification, MP/Item/Gold deduction,
    NPC trait & intimate DC modifiers, and deterministic skill check rolling across Web and Discord.
    """
    import skill_check
    from mechanics.narrative.intent import classify_action_intent
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.combat.traits import get_combined_dc_modifiers
    from mechanics.social.persona import calculate_intimate_action_dc_modifier

    # Idempotency guard: if raw_pick is already a resolved action with a CheckResult, return it directly
    if (
        isinstance(raw_pick, dict)
        and not raw_pick.get("_untrusted_client_pick")
        and raw_pick.get("check") is not None
        and raw_pick.get("char")
    ):
        chk = raw_pick["check"]
        if isinstance(chk, dict):
            raw_pick = dict(raw_pick)
            raw_pick["check"] = skill_check.CheckResult(
                chance=int(chk.get("chance") if chk.get("chance") is not None else 100),
                roll=float(chk.get("roll") if chk.get("roll") is not None else 100.0),
                tier=str(chk.get("tier") or "success"),
                tier_label=str(chk.get("tier_label") or "Success"),
                succeeded=bool(chk.get("succeeded", True)),
                requirement=int(chk.get("requirement", raw_pick.get("requirement", 0)) or 0),
            )
        return raw_pick

    _caller_supplied_session = session is not None
    _pre_bundle = await adb(
        db.preload_prepare_action_bundle,
        session_id,
        user_id,
        session=session,
        char=char,
    )
    if session is None:
        if not _pre_bundle.get("session"):
            raise ValueError(f"Session {session_id} not found")
        session = dict(_pre_bundle["session"])

    if not _pre_bundle.get("char"):
        raise LookupError("Character not found")
    char = dict(_pre_bundle["char"])

    if isinstance(session, dict) and session.get("id") and "_world_events_snapshot" not in session:
        we_snap_val = _pre_bundle.get("world_events_snapshot")
        session["_world_events_snapshot"] = we_snap_val if we_snap_val is not None else {}

    # Normalize payload fields from Web or Discord
    choice_index = raw_pick.get("choice_index")
    custom_text = raw_pick.get("custom_action_text") or raw_pick.get("custom_text")
    direct_choice = raw_pick.get("direct_choice")
    combat_target = raw_pick.get("combat_target")
    req_intent = raw_pick.get("intent")
    req_target_npc = raw_pick.get("target_npc") or raw_pick.get("target_name")
    req_skip_minutes = raw_pick.get("skip_minutes")
    req_sleep_mode = raw_pick.get("sleep_mode")
    req_item_id = raw_pick.get("item_id")
    req_target_type = raw_pick.get("target_type")
    req_target_name = raw_pick.get("target_name") or raw_pick.get("target_npc")
    req_target_user_id = raw_pick.get("target_user_id")
    is_item_action = bool(raw_pick.get("is_item_action") or raw_pick.get("stat") == "ITEM")
    is_stealth_req = bool(
        raw_pick.get("is_stealth")
        or (raw_pick.get("stance") == "stealth")
        or (isinstance(raw_pick.get("action"), dict) and (raw_pick["action"].get("is_stealth") or raw_pick["action"].get("stance") == "stealth"))
    )

    if isinstance(raw_pick.get("action"), dict):
        nested = raw_pick["action"]
        if choice_index is None and "choice_index" in nested:
            choice_index = nested.get("choice_index")
        if not custom_text:
            custom_text = nested.get("custom_action_text") or nested.get("custom_text")
        if direct_choice is None and isinstance(nested.get("direct_choice"), dict):
            direct_choice = nested.get("direct_choice")
        if not combat_target and nested.get("combat_target"):
            combat_target = nested.get("combat_target")
        if not req_intent and nested.get("intent"):
            req_intent = nested.get("intent")
        if not req_target_npc and (nested.get("target_npc") or nested.get("target_name")):
            req_target_npc = nested.get("target_npc") or nested.get("target_name")
        if req_skip_minutes is None and nested.get("skip_minutes") is not None:
            req_skip_minutes = nested.get("skip_minutes")
        if not req_sleep_mode and nested.get("sleep_mode"):
            req_sleep_mode = nested.get("sleep_mode")
        if req_item_id is None and nested.get("item_id") is not None:
            req_item_id = nested.get("item_id")
        if not req_target_type and nested.get("target_type"):
            req_target_type = nested.get("target_type")
        if not req_target_name and (nested.get("target_name") or nested.get("target_npc")):
            req_target_name = nested.get("target_name") or nested.get("target_npc")
        if req_target_user_id is None and nested.get("target_user_id") is not None:
            req_target_user_id = nested.get("target_user_id")

    user_settings = _pre_bundle.get("settings") or {}
    check_mode = user_settings.get("debug_check_mode", "off")
    preloaded_inventory: Optional[List[Dict[str, Any]]] = _pre_bundle.get("inventory")

    chosen: Dict[str, Any] = {}
    classification: Dict[str, Any] = {}
    inventory: Optional[List[Dict[str, Any]]] = preloaded_inventory
    is_custom = False
    is_standalone_direct_choice = False
    action_type = "choice"

    if choices is None and isinstance(session, dict):
        choices = session.get("choices") or []
    if isinstance(choices, list) and choices and isinstance(session, dict):
        from mechanics.social.conversation_choices import (
            ensure_active_dialogue_exit_choice,
            has_dialogue_exit_choice,
        )
        if not has_dialogue_exit_choice(choices):
            choices = await adb(ensure_active_dialogue_exit_choice, choices, session=session)

    if (req_intent in ("use_item", "gift_offer") or req_item_id is not None) and not direct_choice and choice_index is None:
        from mechanics.combat import is_in_combat as _early_is_combat
        from mechanics.combat.items.consumables import (
            classify_consumable_usage_mode,
            is_hostile_or_covert_consumable,
        )
        from mechanics.stealth import is_actor_hidden as _early_is_hidden

        if inventory is None:
            inventory = await adb(db.get_inventory, user_id)
        matched_db_item = None
        if req_item_id is not None:
            try:
                req_iid_int = int(req_item_id)
                matched_db_item = next(
                    (dict(it) for it in (inventory or []) if isinstance(it, dict) and int(it.get("id") or 0) == req_iid_int),
                    None,
                )
            except (TypeError, ValueError):
                matched_db_item = None
        if matched_db_item is None:
            cand_item_nm = str(
                raw_pick.get("item_name")
                or (raw_pick["action"].get("item_name") if isinstance(raw_pick.get("action"), dict) else "")
                or ""
            ).strip().lower()
            if cand_item_nm:
                matched_db_item = next(
                    (dict(it) for it in (inventory or []) if isinstance(it, dict) and str(it.get("name") or "").strip().lower() == cand_item_nm),
                    None,
                )
        if matched_db_item is None:
            raise ValueError("Item not found in your inventory.")

        eff_target_type = str(req_target_type or "self").strip().lower()
        eff_target_name = str(req_target_name or req_target_npc or combat_target or "self").strip()
        eff_target_uid: Optional[int] = None
        if req_target_user_id is not None:
            try:
                eff_target_uid = int(req_target_user_id)
            except (TypeError, ValueError):
                eff_target_uid = None
        in_combat_early = bool(isinstance(session, dict) and _early_is_combat(session))

        if req_intent == "gift_offer":
            if in_combat_early:
                raise ValueError("Cannot give gifts during combat.")
            if bool(matched_db_item.get("equipped")):
                raise ValueError("Unequip the item before giving it away.")
            if bool(matched_db_item.get("is_pact_locked")):
                raise ValueError("Pact-bound items cannot be given away.")
            if eff_target_type == "player" and eff_target_uid is not None:
                if int(eff_target_uid) == int(user_id):
                    raise ValueError("Cannot transfer an item to yourself.")
                if session_id:
                    allowed_uids = set(await adb(db.get_session_participant_user_ids, int(session_id)) or [])
                    if allowed_uids and int(eff_target_uid) not in allowed_uids:
                        raise ValueError("Selected recipient is not in this session.")
                slot_cost = int(matched_db_item["slot_cost"]) if matched_db_item.get("slot_cost") is not None else 1
                if slot_cost > 0:
                    can_fit = await adb(
                        db.can_add_item,
                        int(eff_target_uid),
                        slot_cost=slot_cost,
                        name=str(matched_db_item.get("name") or ""),
                        item_type=str(matched_db_item.get("item_type") or "Misc"),
                        effect=str(matched_db_item.get("effect") or ""),
                    )
                    if not can_fit:
                        raise ValueError(f"{eff_target_name or 'Recipient'}'s backpack is full.")
            chosen = {
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "label": custom_text or f"Give {matched_db_item['name']} to {eff_target_name}",
                "action_category": "gift_offer",
                "intent": "gift_offer",
                "sub_intent": "gift_offer",
                "item_id": matched_db_item.get("id"),
                "item_name": matched_db_item.get("name", ""),
                "item": dict(matched_db_item),
                "target_type": eff_target_type or "npc",
                "target_npc": eff_target_name,
                "target_name": eff_target_name,
                "target_user_id": eff_target_uid,
                "item_consumed": False,
            }
        else:
            use_stat = "ITEM"
            use_dc = 0
            use_sub_intent = "use_item"
            use_is_stealth = is_stealth_req
            if eff_target_type in ("npc", "contact") and not in_combat_early:
                hostile_cov = is_hostile_or_covert_consumable(matched_db_item)
                if hostile_cov:
                    it_low_ts = f"{matched_db_item.get('name', '')} {matched_db_item.get('effect', '')}".lower()
                    is_aphrodisiac = any(k in it_low_ts for k in ("aphrodisiac", "love potion")) and not any(
                        k in it_low_ts for k in ("poison", "sleep", "sedative", "paralyz", "toxin", "venom")
                    )
                    if is_aphrodisiac and session_id:
                        npc_contact = await adb(db.get_contact, int(session_id), eff_target_name.lower().replace(" ", "_"), int(char.get("id", 0) or 0))
                        c_score = int((npc_contact or {}).get("relationship_score") or 0)
                        if c_score >= 60:
                            hostile_cov = False
                if hostile_cov:
                    if is_stealth_req or (isinstance(session, dict) and _early_is_hidden(session, user_id)):
                        use_stat = "AGI"
                        use_dc = 8
                        use_sub_intent = "covert_dose"
                        use_is_stealth = True
                    elif (
                        classify_consumable_usage_mode(matched_db_item) in ("hybrid", "narrative")
                        and str(matched_db_item.get("item_type") or "").strip().lower() in ("drink", "food", "potion", "consumable")
                    ):
                        use_stat = "CHA"
                        use_dc = 9
                        use_sub_intent = "persuade_consume"
                    else:
                        use_stat = "AGI"
                        use_dc = 9
                        use_sub_intent = "force_consume"
            chosen = {
                "stat": use_stat,
                "requirement": use_dc,
                "mp_cost": 0,
                "label": custom_text or f"Use {matched_db_item['name']}",
                "action_category": "item",
                "intent": "use_item",
                "sub_intent": use_sub_intent,
                "item_id": matched_db_item.get("id"),
                "item_name": matched_db_item.get("name", ""),
                "item": dict(matched_db_item),
                "target_type": eff_target_type,
                "target_npc": eff_target_name if eff_target_type != "self" else "",
                "target_name": eff_target_name,
                "target_user_id": eff_target_uid,
                "combat_target": combat_target or (eff_target_name if eff_target_type in ("enemy", "monster") else None),
                "item_consumed": False,
                "is_stealth": use_is_stealth,
            }
            if use_is_stealth:
                is_stealth_req = True
    elif is_item_action and not direct_choice and choice_index is None:
        chosen = {
            "stat": "ITEM",
            "requirement": 0,
            "mp_cost": 0,
            "label": custom_text or f"Use {raw_pick.get('item_name', 'item')}",
            "action_category": "item",
            "intent": "general_action",
            "sub_intent": "use_item",
            "item_name": raw_pick.get("item_name", ""),
            "item": raw_pick.get("item"),
            "item_consumed": raw_pick.get("item_consumed", True),
        }
    elif choice_index is not None and isinstance(choices, list) and 0 <= choice_index < len(choices):
        chosen = dict(choices[choice_index])
    elif isinstance(direct_choice, dict) and direct_choice:
        is_standalone_direct_choice = True
        if raw_pick.get("_untrusted_client_pick"):
            chosen = await _get_turn_service()._reconcile_client_direct_choice(
                session_id=session_id,
                user_id=user_id,
                session=session,
                char=char,
                choices=choices,
                raw_dc=direct_choice,
                combat_target=combat_target,
                is_stealth_req=is_stealth_req,
                req_intent=req_intent,
            )
        else:
            chosen = dict(direct_choice)
            # Strip privileged server-only spoofing keys on un-indexed client direct_choice payloads
            for _priv_k in (
                "_epistemic_verified",
                "hush_gold_override",
                "effective_dc_mod",
                "telltale_revealed",
                "_activity_reconciled",
                "quest_id",
                "sub_obj_id",
                "stage_index",
                "is_quest_action",
                "is_climax_action",
                "is_story_quest",
                "_python_verified_quest",
                "triggers_loot_roll",
                "breakthrough_leveraged",
                "_server_stamped",
                "clue_pair_ids",
                "approach",
                "is_anomaly_inquiry",
            ):
                chosen.pop(_priv_k, None)
            _combat_tactic_ok = (
                isinstance(session, dict)
                and bool(session.get("nearby_enemies"))
                and str(chosen.get("incursion_action") or "").strip().lower()
                in {"subdue", "combat_persuade", "sever_tether", "folklore_offering_rite", "exploit_taboo"}
            )
            if not _combat_tactic_ok:
                for _inc_k in ("incursion_action", "incursion_id", "breach_id"):
                    chosen.pop(_inc_k, None)
            _site_act_ok_t = (
                isinstance(session, dict)
                and not session.get("nearby_enemies")
                and str(chosen.get("intent") or "").strip().lower() == "anomalous_site_action"
                and str(chosen.get("site_action") or "").strip().lower() in {"puzzle_step", "harvest", "overdraw"}
                and bool(chosen.get("site_id"))
            )
            if not _site_act_ok_t:
                for _sk_k in ("site_action", "site_id", "step_index", "use_ward", "ward_item_name"):
                    chosen.pop(_sk_k, None)
            if chosen.get("spell_id"):
                try:
                    from mechanics.combat.spells.registry import get_spell
                    sp_def = get_spell(str(chosen["spell_id"]))
                    if isinstance(sp_def, dict) and sp_def.get("mp_cost") is not None:
                        chosen["mp_cost"] = int(sp_def["mp_cost"])
                except Exception:
                    pass
            if chosen.get("target_node_id") and session_id:
                cand_nid = str(chosen["target_node_id"])
                wn_row = await adb(db.get_world_node, session_id, cand_nid)
                if not wn_row:
                    chosen.pop("target_node_id", None)
    elif choice_index is not None:
        if not enforce_explicit_mp and isinstance(choices, list) and choices:
            chosen = dict(choices[0])
        elif not enforce_explicit_mp:
            chosen = {"stat": "PER", "requirement": 6, "mp_cost": 0, "label": "Proceed forward"}
        else:
            raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")
    elif custom_text:
        is_custom = True
        action_type = "custom"
        if (
            not (isinstance(session, dict) and session.get("nearby_enemies"))
            and (req_skip_minutes is not None or req_sleep_mode in ("sleep", "nap", "wait") or req_intent in ("wait_time", "rest_sleep"))
        ):
            classification = {
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "action_category": "rest" if req_sleep_mode in ("sleep", "nap") or req_intent == "rest_sleep" else "wait",
                "intent": req_intent or ("rest_sleep" if req_sleep_mode in ("sleep", "nap") else "wait_time"),
            }
            chosen = dict(classification)
            chosen["label"] = custom_text
            chosen["text"] = custom_text
        else:
            if inventory is None:
                inventory = await adb(db.get_inventory, user_id)
            _matched_site_free = None
            if (
                isinstance(session, dict)
                and session.get("id")
                and scenario_data.is_anomalous_incursions_scenario(session.get("scenario", ""))
                and not game_engine.get_active_enemies(session)
            ):
                try:
                    from mechanics.world.anomalous_sites import match_freeform_puzzle_action
                    _matched_site_free = await adb(
                        match_freeform_puzzle_action,
                        int(session["id"]),
                        custom_text,
                        location_str=str(session.get("current_location") or ""),
                        node_id=str(session.get("current_node_id") or ""),
                        scen_key=str(session.get("scenario") or "anomalous_incursions"),
                        current_day=int(session.get("current_day", 1) or 1),
                        current_minute=int(session.get("current_minute", 720) or 720),
                        inventory=inventory,
                        session=session,
                    )
                except Exception:
                    _matched_site_free = None
            if _matched_site_free:
                classification = dict(_matched_site_free)
                chosen = dict(_matched_site_free)
            else:
                classification = await game_engine.classify_custom_action(session, char, inventory, custom_text)
                if not isinstance(classification, dict):
                    classification = dict(classification) if hasattr(classification, "items") else {}
                chosen = dict(classification)
            if not classification.get("fast_path") and not classification.get("_verified_ambient_intent"):
                if str(chosen.get("stat") or "").upper() not in db.STAT_COLUMN:
                    chosen["stat"] = "PER"
                _in_dlg_custom = bool(isinstance(session, dict) and get_session_dialogue_partners(session))
                chosen["requirement"] = (
                    max(3, min(12, int(chosen.get("requirement", 5) or 5)))
                    if _in_dlg_custom
                    else max(6, int(chosen.get("requirement", 6) or 6))
                )
            chosen["label"] = custom_text
            chosen["text"] = custom_text
            if is_custom and session_id:
                _t_qid = str(classification.get("targets_quest_id") or "").strip()
                if _t_qid:
                    try:
                        _q_chk = await adb(db.get_quest_by_id, session_id, _t_qid)
                    except Exception:
                        _q_chk = None
                    if isinstance(_q_chk, dict) and str(_q_chk.get("status") or "").lower() == "active":
                        chosen["quest_id"] = _t_qid
                        chosen["is_quest_action"] = True
                        chosen["_python_verified_quest"] = True
                        chosen["is_story_quest"] = bool(_q_chk.get("is_story_quest"))
                        if classification.get("targets_sub_obj_id") is not None:
                            try:
                                chosen["sub_obj_id"] = int(classification["targets_sub_obj_id"])
                            except (TypeError, ValueError):
                                pass
                        _q_app = str(classification.get("quest_approach") or "").strip().upper()
                        if _q_app:
                            chosen["quest_approach"] = _q_app
                            if not chosen.get("approach"):
                                chosen["approach"] = _q_app
    else:
        raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")

    if (
        not is_custom
        and not chosen.get("_seed_reconciled")
        and chosen.get("topic_id")
        and isinstance(session, dict)
        and isinstance(session.get("_dealt_social_seeds"), list)
    ):
        _tid_match = next(
            (
                s for s in session["_dealt_social_seeds"]
                if isinstance(s, dict) and str(s.get("topic_id") or "").strip() == str(chosen.get("topic_id") or "").strip()
            ),
            None,
        )
        if _tid_match:
            _s_st = str(_tid_match.get("stat") or chosen.get("stat") or "CHA").upper()
            chosen["stat"] = _s_st if _s_st in db.STAT_COLUMN else "CHA"
            chosen["requirement"] = max(3, min(12, int(_tid_match.get("dc") or chosen.get("requirement") or 6)))
            chosen["mp_cost"] = max(0, int(_tid_match.get("mp_cost") or 0))
            chosen["category"] = str(_tid_match.get("category") or chosen.get("category") or "")
            chosen["target_npc"] = str(_tid_match.get("target_npc") or chosen.get("target_npc") or "")
            chosen["is_covert_ability"] = bool(_tid_match.get("is_covert_ability"))
            chosen["is_direct_reply"] = bool(_tid_match.get("is_direct_reply"))
            chosen["_seed_reconciled"] = True

    stat = str(chosen.get("stat", "STR") or "STR").upper()
    req_val = int(chosen.get("requirement", 5 if not is_custom else 6) or 0)
    mp_cost = int(chosen.get("mp_cost", 0) or 0)
    mp_spent = mp_cost
    label_text = str(chosen.get("label") or chosen.get("text") or custom_text or "Action")
    if session_id and str(chosen.get("intent") or req_intent or "").strip().lower() == "property_purchase":
        from mechanics.world.locations.realty_catalog import resolve_realty_entry, find_realty_by_node_id
        _prop_id_cand = str(chosen.get("property_id") or raw_pick.get("property_id") or "").strip()
        _cat_prop = resolve_realty_entry(_prop_id_cand, session_or_id=session or session_id) if _prop_id_cand else None
        if not _cat_prop and chosen.get("target_node_id"):
            _cat_prop = find_realty_by_node_id(str(chosen["target_node_id"]), session_or_id=session or session_id)
        if not _cat_prop:
            raise ValueError("Invalid or unavailable property deed.")
        _avail_g = int((char or {}).get("gold") or 0)
        if _avail_g < int(_cat_prop["price"]):
            raise ValueError(f"Insufficient gold to purchase {_cat_prop['name']} ({_cat_prop['price']}g required, {_avail_g}g available).")
        stat = "FREE"
        req_val = 0
        mp_cost = 0
        mp_spent = 0
        chosen["stat"] = "FREE"
        chosen["requirement"] = 0
        chosen["mp_cost"] = 0
        chosen["intent"] = "property_purchase"
        chosen["property_id"] = _cat_prop["property_id"]
        chosen["price"] = int(_cat_prop["price"])
        chosen["target_node_id"] = _cat_prop["bedroom_node_id"]
        chosen["target_location"] = f"{_cat_prop['zone_name']} ➔ {_cat_prop['name']} ➔ {_cat_prop['bedroom_name']}"
        label_text = f"[For Sale — {_cat_prop['price']}g] Purchase {_cat_prop['name']} Deed"

    # ── Invariant 12 (A4): Restraint Hard-Gate on Travel / Movement ──────
    if session_id:
        try:
            from mechanics.world.locations.movement import is_movement_action
            from mechanics.social.physical_state import find_player_actor_key, can_actor_travel_or_dual_wield
            act_intent_low = str(chosen.get("intent") or req_intent or "").lower()
            is_break_attempt = act_intent_low in ("break_free", "companion_free") or any(
                w in label_text.lower() for w in ("break free", "struggle", "slip out", "untie", "cut bonds", "cut my bonds")
            )
            if not is_break_attempt and (act_intent_low in ("movement", "travel", "fast_travel") or is_movement_action(label_text)):
                phys_now = await adb(db.get_session_physical_state, session_id)
                if phys_now and isinstance(phys_now.get("actors"), dict):
                    pk_now = find_player_actor_key(phys_now["actors"], party=[char], session_id=session_id)
                    p_actor_now = phys_now["actors"].get(pk_now) if pk_now else None
                    if p_actor_now:
                        can_move, move_reason = can_actor_travel_or_dual_wield(p_actor_now)
                        if not can_move:
                            raise ValueError(move_reason)
        except ValueError:
            raise
        except Exception:
            pass

    _sleep_mode_chk = str(req_sleep_mode or chosen.get("sleep_mode") or "").strip().lower()
    _sleep_int_chk = str(chosen.get("intent") or req_intent or "").strip().lower()
    if _sleep_mode_chk in ("sleep", "nap") or _sleep_int_chk == "rest_sleep":
        from mechanics.world.anomalous_sites.domain_rules import is_sleep_blocked_in_anomalous_zone
        _blocked_slp, _slp_reason = is_sleep_blocked_in_anomalous_zone(
            session_id=int(session_id or 0),
            location_name=str(session.get("current_location") or "") if isinstance(session, dict) else "",
            node_id=str(session.get("current_node_id") or "") if isinstance(session, dict) else "",
            current_minute=int(session.get("current_minute", 720) or 720) if isinstance(session, dict) else 720,
            scen_key=str(session.get("scenario") or "") if isinstance(session, dict) else "",
        )
        if _blocked_slp:
            raise ValueError(_slp_reason or "You cannot sleep or nap inside an active anomalous quarantine zone!")

    # ── Awakened Resonance 3-Pip Ultimate Gate, 0-MP Basic Strike & Entity Contracts ─
    chosen_spell_id = str(chosen.get("spell_id") or "").strip()
    if chosen_spell_id.startswith("awk_basic_") or (chosen.get("is_basic_strike") and not chosen_spell_id):
        mp_cost = 0
        mp_spent = 0
    elif chosen_spell_id.startswith("pact_") and isinstance(session, dict):
        mp_cost = 0
        mp_spent = 0
        sid_pact = int(session.get("id") or 0)
        if sid_pact and user_id:
            from mechanics.pacts import build_pact_spell_id, compute_pact_cast_costs, get_patron_by_id
            active_pacts_pr = list(char.get("active_pacts") or [])
            if not active_pacts_pr:
                active_pacts_pr = await adb(db.get_player_active_pacts, sid_pact, int(user_id))
            scen_pr = str(session.get("scenario") or "anomalous_incursions")
            cont_pr = list(session.get("contained_anomalies_log") or [])
            matched_p_row = None
            matched_pat = None
            for _pr_row in (active_pacts_pr or []):
                _pat_cand = get_patron_by_id(str(_pr_row.get("patron_id") or ""), scenario_or_key=scen_pr, contained_records=cont_pr)
                if _pat_cand and build_pact_spell_id(_pat_cand, int(_pr_row.get("tier") or 1)) == chosen_spell_id:
                    matched_p_row = _pr_row
                    matched_pat = _pat_cand
                    break
            if not matched_p_row or not matched_pat:
                if not is_custom and enforce_explicit_mp:
                    raise PermissionError("You do not hold an active Entity Contract for that invocation!")
            else:
                cost_info = compute_pact_cast_costs(char, matched_p_row, matched_pat)
                if not cost_info["can_invoke"] and not is_custom and enforce_explicit_mp:
                    raise PermissionError(cost_info["blocked_reason"] or "Cannot invoke this Entity Contract right now!")
                chosen["is_pact_skill"] = True
                chosen["is_lethal_overdraw"] = bool(cost_info["is_lethal_overdraw"])
                chosen["_pact_cast_meta"] = {
                    **cost_info,
                    "contract_key": matched_p_row["contract_key"],
                    "patron_id": matched_p_row["patron_id"],
                    "patron_name": matched_pat["canonical_name"],
                }
    elif chosen_spell_id and isinstance(session, dict):
        import scenario_data as _ts_sd
        if _ts_sd.is_anomalous_incursions_scenario(session.get("scenario", "")):
            from mechanics.combat.spells.registry import get_spell as _ts_get_spell
            from mechanics.combat.awakened_resonance import get_starting_encounter_pips
            _ts_sp = _ts_get_spell(chosen_spell_id)
            if isinstance(_ts_sp, dict) and _ts_sp.get("is_ultimate") and int(_ts_sp.get("pip_cost", 0) or 0) > 0:
                mp_cost = 0
                mp_spent = 0
                req_pips = int(_ts_sp.get("pip_cost", 3))
                pips_map = session.get("player_resonance_pips") if isinstance(session.get("player_resonance_pips"), dict) else {}
                uid_key = str(user_id)
                cur_pips = int(pips_map[uid_key]) if uid_key in pips_map else get_starting_encounter_pips(int(char.get("level", 1) or 1))
                if cur_pips < req_pips and not is_custom and enforce_explicit_mp:
                    raise PermissionError(f"Not enough Resonance Pips for Signature Ultimate ({cur_pips}/{req_pips} Pips)!")

    # ── MP Validation & Improvisation Rule (staged for atomic commit) ─────
    if mp_cost > 0:
        if char.get("mp", 0) < mp_cost:
            if not is_custom and enforce_explicit_mp:
                raise PermissionError("Not enough MP for this action!")
            # Freeform custom text (or Discord fallback): improvise with 0 MP and +2 DC penalty
            label_text += " (couldn't afford the full effort, improvised instead)"
            mp_spent = 0
            if stat not in ("NONE", "FREE", "ITEM"):
                req_val += 2

    # ── Gold Spending / Bribe Clamping Rule (staged for atomic commit) ───
    requested_gold = int(
        chosen.get("gold_spent")
        or chosen.get("gold_cost")
        or classification.get("gold_spent")
        or 0
    )
    avail_gold = max(0, int(char.get("gold", 0) or 0))
    actual_gold_spent = 0
    gold_shortfall_note = ""
    if requested_gold > 0 and requested_gold > avail_gold:
        req_val += 3
        gold_shortfall_note = (
            f"[SYSTEM NOTE: Player attempted to spend/offer {requested_gold} gold, "
            f"but only had {avail_gold} gold available (+3 DC penalty applied).]"
        )

    # ── Item Validation & Staged Consumption Rule ────────────────────────
    target_item_name = raw_pick.get("item_name") or chosen.get("item_name") or ""
    target_item_obj = raw_pick.get("item") or chosen.get("item")
    item_was_consumed = bool(chosen.get("item_consumed", False))

    if stat == "ITEM":
        if inventory is None:
            inventory = await adb(db.get_inventory, user_id)
        if not target_item_name and not target_item_obj:
            label_lower = label_text.lower()
            for inv_item in (inventory or []):
                iname = inv_item.get("name", "")
                if iname and iname.lower() in label_lower:
                    target_item_name = iname
                    target_item_obj = inv_item
                    break
        if not target_item_name and isinstance(target_item_obj, dict):
            target_item_name = target_item_obj.get("name", "")
        if target_item_name:
            verified_inv_item = next(
                (i for i in (inventory or []) if i.get("name", "").lower() == target_item_name.lower()),
                None,
            )
            if verified_inv_item is not None:
                target_item_obj = verified_inv_item
            elif is_standalone_direct_choice and enforce_explicit_mp:
                raise PermissionError(f"Item '{target_item_name}' is not in your inventory!")
        if target_item_name and chosen.get("item_consumed", True) and target_item_obj is not None:
            from mechanics.combat import is_in_combat as _item_is_combat
            if not (isinstance(session, dict) and _item_is_combat(session)):
                item_was_consumed = True

    # ── Persona DC Modifiers ─────────────────────────────────────────
    act_cat = str(chosen.get("action_category") or ("custom" if is_custom else "")).strip()

    sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
    explicit_target = (
        combat_target
        or req_target_npc
        or chosen.get("target_npc")
        or (classification.get("target_npc") if is_custom else None)
    )
    if not explicit_target:
        import namegen
        act_lbl = label_text.lower()
        named_dps = [
            dp for dp in sess_dp
            if dp and (
                dp.lower() in act_lbl
                or any(
                    re.search(rf"\b{re.escape(tok)}\b", act_lbl)
                    for tok in namegen.get_unique_person_tokens(dp, peer_names=sess_dp, min_len=2)
                )
            )
        ]
        if len(named_dps) == 1:
            explicit_target = named_dps[0]

    target_candidates = [explicit_target] if explicit_target else list(sess_dp)
    if target_candidates and isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM"):
        is_romantic_attempt = (
            act_cat in ("romantic_confession", "affection", "intimate_act")
            or any(
                kw in label_text.lower()
                for kw in ("confess", "kiss", "flirt", "seduc", "intimate", "make out", "ask out", "romantic")
            )
        )
        for dp_name in target_candidates:
            if dp_name:
                c_rec = await adb(db.get_contact, session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                if c_rec:
                    c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                    t_mods = get_combined_dc_modifiers(c_traits)
                    req_val += t_mods.get(stat, 0)
                    app_rec = c_rec.get("appearance", {})
                    if isinstance(app_rec, dict):
                        req_val += calculate_intimate_action_dc_modifier(label_text, app_rec)
                if is_romantic_attempt:
                    try:
                        from mechanics.social import relationship_graph as rg
                        curr_p = await adb(rg.get_current_partner, session["id"], rg.canonical_person_key(dp_name))
                        if curr_p and not rg.is_player_person_key(curr_p.get("person_key")):
                            req_val += 3
                    except Exception:
                        pass

    if isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM") and target_candidates:
        _primary_dp = str(target_candidates[0] or "").strip()
        if _primary_dp and (
            sess_dp
            or act_cat in ("dialogue", "romantic_confession", "social_invite", "affection", "disclosure_inquiry")
            or is_custom
        ):
            try:
                from mechanics.social import pacing as _ts_pacing
                from mechanics.social.conversation_choices import _infer_social_category_from_choice
                _cur_day_ts = int(session.get("current_day") or 1)
                _cur_min_ts = int(session.get("current_minute") or 480)
                _comp_ts = await adb(
                    lambda: _ts_pacing.sync_and_get_composure(
                        int(session["id"]),
                        _primary_dp,
                        current_day=_cur_day_ts,
                        current_minute=_cur_min_ts,
                        scenario=str(session.get("scenario") or "fantasy"),
                    )
                )
                _, _mood_dc_mod = _ts_pacing.derive_mood_and_dc_mod(
                    int(_comp_ts.get("current_composure", 100)),
                    int(_comp_ts.get("max_composure", 100)),
                    str(_comp_ts.get("composure_state") or "composed"),
                    clear_the_air_required=bool(int(_comp_ts.get("clear_the_air_required") or 0) == 1),
                )
                if is_custom or not chosen.get("_seed_reconciled"):
                    req_val += int(_mood_dc_mod or 0)
                    if (
                        int(_comp_ts.get("current_composure", 100)) <= 0
                        and _ts_pacing.is_composure_locked_out(_comp_ts, _cur_day_ts, _cur_min_ts)
                        and str(_comp_ts.get("composure_state") or "") == "cold_shoulder"
                    ):
                        req_val += 3

                if is_custom:
                    _lbl_c = label_text.lower()
                    _inf_cat = str(chosen.get("category") or "").strip().lower() or _infer_social_category_from_choice({"label": label_text})
                    chosen["category"] = _inf_cat
                    if any(w in _lbl_c for w in ("insult", "mock", "humiliate", "belittle", "sneer", "pathetic", "worthless", "trash")):
                        chosen["is_cruel"] = True
                    if mp_cost > 0 and any(w in _lbl_c for w in ("charm", "mind", "telepath", "hypno", "compel", "glamour", "suggest")):
                        chosen["is_covert_ability"] = True

                    _cid_ts = int((char or {}).get("id") or 0)
                    _t_map = await adb(
                        db.get_social_topic_states,
                        int(session["id"]),
                        _cid_ts,
                        _primary_dp,
                    )
                    _kw_map = {
                        "work_calling": ("work", "job", "duty", "duties", "club", "career", "calling", "profession"),
                        "passions_likes": ("like", "likes", "hobby", "hobbies", "passion", "favorite", "enjoy"),
                        "pet_peeves": ("dislike", "dislikes", "hate", "annoy", "pet peeve"),
                        "daily_routine": ("schedule", "routine", "usual", "hang out", "where do you"),
                        "family_roots": ("family", "hometown", "parents", "sibling", "brother", "sister", "childhood"),
                    }
                    _matched_locked_tid = ""
                    for _tid_cand, _tr in (_t_map or {}).items():
                        if _ts_pacing.is_topic_available(
                            int(session["id"]),
                            _cid_ts,
                            _primary_dp,
                            _tid_cand,
                            current_day=_cur_day_ts,
                            current_minute=_cur_min_ts,
                            preloaded_states=_t_map,
                        ):
                            continue
                        _slug = _tid_cand.split(":", 1)[1] if ":" in _tid_cand else _tid_cand
                        if (
                            (chosen.get("topic_id") and str(chosen["topic_id"]) == _tid_cand)
                            or (_slug in _kw_map and any(kw in _lbl_c for kw in _kw_map[_slug]))
                            or (_tid_cand.startswith(f"{_inf_cat}:") and str(_tr.get("last_outcome") or "") in ("fail", "crit_fail"))
                        ):
                            _matched_locked_tid = _tid_cand
                            break
                    if _matched_locked_tid:
                        chosen["_topic_locked_attempt"] = True
                        chosen["topic_id"] = _matched_locked_tid
                        req_val += 2
                    elif not chosen.get("topic_id"):
                        chosen["topic_id"] = f"{_inf_cat}:custom_chat"
                    req_val = max(3, min(15, req_val))
            except Exception as _soc_m_err:
                log.debug("Social custom metering skipped: %s", _soc_m_err)

    _domain_stat_bonus = 0
    if isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
        try:
            from mechanics.world.world_events.modifiers import (
                compute_event_dc_modifier,
                compute_rumor_defensive_dc,
            )
            _we_snap_dc = session.get("_world_events_snapshot")
            req_val += compute_event_dc_modifier(
                _we_snap_dc,
                stat=stat,
                location_node_id=str(session.get("current_node_id") or ""),
                is_stealth=is_stealth_req,
            )
            if stat == "CHA" and target_candidates:
                req_val += compute_rumor_defensive_dc(_we_snap_dc, target=target_candidates)
        except Exception as _we_dc_err:
            log.debug("World event DC modifier skipped: %s", _we_dc_err)
        try:
            import scenario_data as _ts_pact_sd
            if (
                not bool(session.get("nearby_enemies"))
                and _ts_pact_sd.is_anomalous_incursions_scenario(session.get("scenario", ""))
                and user_id
            ):
                from mechanics.pacts import compute_pact_field_dc_modifier
                _pacts_dc = list(char.get("active_pacts") or [])
                if not _pacts_dc:
                    _pacts_dc = await adb(db.get_player_active_pacts, int(session["id"]), int(user_id))
                if _pacts_dc:
                    req_val += compute_pact_field_dc_modifier(
                        _pacts_dc,
                        stat,
                        action_category=act_cat,
                        label_text=label_text,
                        scenario_or_key=session.get("scenario"),
                    )
        except Exception as _pact_dc_err:
            log.debug("Pact field DC modifier skipped: %s", _pact_dc_err)
        try:
            import scenario_data as _ts_dom_sd
            if _ts_dom_sd.is_anomalous_incursions_scenario(session.get("scenario", "")):
                from mechanics.world.anomalous_sites import compute_domain_skill_check_modifiers
                _dom_chk = await adb(
                    compute_domain_skill_check_modifiers,
                    int(session["id"]),
                    session,
                    int(user_id or 0),
                    char,
                    stat,
                    inventory,
                )
                req_val += int(_dom_chk.get("dc_penalty") or 0)
                _domain_stat_bonus = int(_dom_chk.get("stat_bonus") or 0)
        except Exception as _dom_dc_err:
            log.debug("Anomalous domain DC modifier skipped: %s", _dom_dc_err)

    if isinstance(chosen, dict) and (chosen.get("intent") == "break_the_news" or chosen.get("_is_break_the_news")):
        try:
            from mechanics.world.world_events.social_hooks import record_break_the_news_gossip
            _btn_npc = str(explicit_target or (target_candidates[0] if target_candidates else "")).strip()
            if _btn_npc and isinstance(session, dict) and session.get("id"):
                await adb(
                    record_break_the_news_gossip,
                    int(session["id"]),
                    int(session.get("current_day") or 1),
                    _btn_npc,
                    str(chosen.get("event_key") or ""),
                )
        except Exception as _btn_err:
            log.debug("record_break_the_news_gossip skipped: %s", _btn_err)

    if stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
        req_val = max(1, req_val)

    # ── Urgent Schedule Departure Hurry & Stage 2 Custom Auto-Fail ───────
    stage2_custom_auto_fail = False
    if target_candidates and isinstance(session, dict):
        from mechanics.social.conversation_choices import get_npc_departure_states, is_convince_stay_action
        from mechanics.narrative.intent import is_conversational_exit
        dep_states = get_npc_departure_states(session)
        if dep_states:
            for dp_name in target_candidates:
                if not dp_name:
                    continue
                dp_st = dep_states.get(re.sub(r"\s+", " ", str(dp_name).strip().lower()))
                if not dp_st:
                    continue
                stg = str(dp_st.get("stage") or "")
                if stg == "stage_2_ultimatum" and is_custom:
                    stage2_custom_auto_fail = True
                    if stat in ("NONE", "FREE", ""):
                        stat = "CHA"
                    req_val = max(12, req_val)
                    break
                elif stg == "stage_1_warning" and is_custom and not is_conversational_exit(label_text):
                    if is_convince_stay_action(label_text):
                        stat = "CHA"
                        req_val = max(6, req_val or 9)
                    elif stat in ("NONE", "FREE", "") or req_val <= 0:
                        stat = "CHA"
                        req_val = 9
                    elif stat != "ITEM":
                        req_val = min(15, max(7, req_val + 3))
                    break

    # ── Roll Skill Check ─────────────────────────────────────────────────
    stat_col = db.STAT_COLUMN.get(stat, "str_" if not is_custom else "agi_")
    hit_chance = chosen.get("hit_chance")
    if stage2_custom_auto_fail:
        res = skill_check.CheckResult(
            chance=0, roll=100.0, tier="fail", tier_label="Failed", succeeded=False, requirement=req_val
        )
        rate = 0
    elif stat == "ITEM":
        res = skill_check.CheckResult(
            chance=100, roll=100.0, tier="success", tier_label="Item Used", succeeded=True, requirement=req_val
        )
        rate = 100
    elif hit_chance is not None:
        rate = int(hit_chance)
        roll = round(random.uniform(0, 100), 1)
        if check_mode == "always_crit_success":
            tier, succeeded = "crit_success", True
        elif check_mode == "always_success":
            tier, succeeded = "success", True
        elif check_mode == "always_fail":
            tier, succeeded = "fail", False
        elif check_mode == "always_crit_fail":
            tier, succeeded = "crit_fail", False
        else:
            succeeded = roll <= rate
            crit_s_thresh = max(1, rate // 5)
            if succeeded and roll <= crit_s_thresh:
                tier = "crit_success"
            elif succeeded:
                tier = "success"
            elif roll >= 95:
                tier = "crit_fail"
            else:
                tier = "fail"
        res = skill_check.CheckResult(
            chance=rate,
            roll=roll,
            tier=tier,
            tier_label=tier.replace("_", " ").title(),
            succeeded=succeeded,
            requirement=req_val,
        )
    elif stat in ("NONE", "FREE") or req_val <= 0:
        res = skill_check.CheckResult(
            chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True, requirement=req_val
        )
        rate = 100
    else:
        stat_val = max(1, int(char.get(stat_col, 5) or 5) + _domain_stat_bonus)
        luk_val = char.get("luk", 3)
        rate = skill_check.success_chance(stat_val, req_val, check_mode=check_mode)
        res = skill_check.resolve_check(stat_val, req_val, luk_val, check_mode=check_mode)

    # ── Intent & Category Normalization ──────────────────────────────────
    act_intent = req_intent or chosen.get("intent") or (classification.get("intent") if is_custom else None)
    act_target = req_target_npc or chosen.get("target_npc") or (classification.get("target_npc") if is_custom else None)
    act_sub_intent = chosen.get("sub_intent") or (classification.get("sub_intent") if is_custom else "") or ""
    act_ends_dialogue = bool(chosen.get("ends_dialogue") or (classification.get("ends_dialogue") if is_custom else False))

    intent_source = "choice_tag" if (not is_custom and chosen.get("intent")) else ("utility_llm" if is_custom else "fallback")
    if not act_cat or act_cat == "custom" or not act_intent:
        if not act_intent:
            logger.warning("[TurnService] Action missing structured intent; falling back to regex classifier for '%s'", label_text)
            intent_source = "regex_fallback"
        parsed_i = classify_action_intent(label_text)
        if not act_cat or act_cat == "custom":
            act_cat = classification.get("action_category") or parsed_i.category.value
        if not act_intent:
            act_intent = parsed_i.category.value
        if not act_target and parsed_i.target_entity:
            act_target = parsed_i.target_entity
        if not act_sub_intent and parsed_i.sub_target:
            act_sub_intent = parsed_i.sub_target

    if act_intent == "dialogue_exit":
        act_ends_dialogue = True

    resolved_intent = {
        "intent": act_intent,
        "sub_intent": act_sub_intent,
        "target_npc": act_target or "",
        "ends_dialogue": act_ends_dialogue,
        "source": intent_source,
    }

    # ── Stealth Stance & Covert Action Resolution ─────────────────────────
    from mechanics.combat import is_in_combat as _ts_is_in_combat
    from mechanics.stealth import (
        get_session_stealth_state,
        is_actor_hidden,
        toggle_stealth_stance,
        break_stealth,
        apply_stealth_decay_turn,
        resolve_distraction_action,
        resolve_stealth_action,
        resolve_scene_environment_context,
    )

    st_state = get_session_stealth_state(session)
    prev_stealth_state = json.loads(json.dumps(st_state, default=str)) if isinstance(st_state, dict) else {}
    in_combat_now = bool(isinstance(session, dict) and _ts_is_in_combat(session))
    is_covert_intent = bool(act_intent == "stealth_covert" or act_cat == "stealth")
    actor_hidden_before = is_actor_hidden(session, user_id)
    effective_stealth = bool(
        is_stealth_req
        or is_covert_intent
        or (actor_hidden_before and raw_pick.get("stance") != "normal")
    )

    lbl_low = label_text.lower()
    stealth_outcome = None

    if not in_combat_now and isinstance(session, dict):
        # Assemble party + active companions for accurate companion noise math
        stealth_party = [(dict(char), [])]
        for comp_list_key in ("party_npcs", "temporary_companions"):
            for comp in (session.get(comp_list_key) or []):
                if isinstance(comp, dict):
                    stealth_party.append((comp, []))
        actor_inventory: list | None = None
        if session.get("id"):
            try:
                party_chars = await adb(db.get_session_characters, session["id"])
                inv_by_cid = (
                    await adb(db.get_inventories_for_characters, party_chars)
                    if party_chars
                    else {}
                )
                for m_char in (party_chars or []):
                    if not isinstance(m_char, dict):
                        continue
                    m_cid = int(m_char["id"]) if m_char.get("id") is not None else -1
                    m_inv = inv_by_cid.get(m_cid, [])
                    if m_char.get("user_id") == user_id:
                        actor_inventory = m_inv
                    else:
                        stealth_party.append((dict(m_char), m_inv))
            except Exception:
                pass

        if actor_inventory is None:
            actor_inventory = list(preloaded_inventory) if preloaded_inventory is not None else await adb(db.get_inventory, user_id, char)
        env_ctx = resolve_scene_environment_context(session)
        curr_min_st = session.get("current_minute", 480)
        base_req = int(chosen.get("requirement", req_val) or req_val) if not is_custom else int(classification.get("requirement", req_val) or req_val)
        dc_mod_stealth = max(0, int(req_val) - base_req)

        is_distraction_action = bool(
            chosen.get("sub_intent") == "stealth_distract"
            or raw_pick.get("sub_intent") == "stealth_distract"
            or (
                is_covert_intent
                and any(k in lbl_low for k in ("distract", "diversion", "throw stone", "throw a stone", "small stone", "pebble", "noise distraction", "divert attention", "decoy"))
            )
        )
        is_freeze_blend_action = bool(
            effective_stealth
            and any(k in lbl_low for k in ("freeze & blend", "hold motionless", "hold still", "stay still in shadow"))
        )

        if is_distraction_action:
            if not is_actor_hidden(session, user_id) and is_stealth_req:
                toggle_stealth_stance(session, True, user_id=user_id)
            stealth_outcome = resolve_distraction_action(
                session=session,
                actor_char=char,
                equipped_items=actor_inventory,
                current_minute=curr_min_st,
                party=stealth_party,
                environment=env_ctx,
                check_mode=check_mode,
                user_id=user_id,
            )
            res = stealth_outcome["check"]
            rate = res.chance
            effective_stealth = is_actor_hidden(session, user_id) or bool(is_stealth_req or is_covert_intent)
        elif is_freeze_blend_action:
            toggle_stealth_stance(session, True, user_id=user_id)
            apply_stealth_decay_turn(session, is_waiting_still=True)
        elif effective_stealth:
            is_loud_magic = bool(
                (chosen.get("spell_id") or act_cat == "magic")
                and not any(k in lbl_low for k in ("silent", "shadow", "stealth", "invisib", "muffle", "veil"))
            )
            if act_intent in ("rest_sleep", "dialogue_init"):
                break_stealth(session, reason=act_intent, user_id=user_id)
                effective_stealth = False
            elif is_loud_magic:
                break_stealth(session, reason="unsuppressed_magic", user_id=user_id)
                effective_stealth = False
            else:
                if not is_actor_hidden(session, user_id):
                    toggle_stealth_stance(session, True, user_id=user_id)
                is_covert_check = bool(
                    is_covert_intent
                    or any(w in lbl_low for w in ("sneak", "creep", "infiltrate", "pickpocket", "shadow step", "silent takedown", "slip past", "lockpick", "pick the lock"))
                    or (stat == "AGI" and not any(w in lbl_low for w in ("flee", "sprint", "dodge", "chase")))
                )
                if is_covert_check:
                    stealth_outcome = resolve_stealth_action(
                        session=session,
                        actor_char=char,
                        action_data={
                            "label": label_text,
                            "action_type": chosen.get("choice_type", "stealth"),
                            "custom_action_text": label_text,
                            "target_npc": act_target,
                        },
                        target_entity={"name": act_target} if act_target else None,
                        party=stealth_party,
                        equipped_items=actor_inventory,
                        current_minute=curr_min_st,
                        environment=env_ctx,
                        check_mode=check_mode,
                        dc_modifier=dc_mod_stealth,
                        user_id=user_id,
                    )
                    res = stealth_outcome["check"]
                    rate = res.chance
                    effective_stealth = is_actor_hidden(session, user_id)
                else:
                    apply_stealth_decay_turn(session, is_waiting_still=("wait" in lbl_low))
        if not _caller_supplied_session and session.get("id") and session.get("stealth_state") != prev_stealth_state:
            await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])

    # D7: Deduct gold_spent only on succeeded checks OR gamble forfeitures (staged for atomic commit)
    if requested_gold > 0:
        should_spend_gold = bool(res.succeeded or str(act_sub_intent or "").lower() == "gamble")
        actual_gold_spent = min(requested_gold, avail_gold) if should_spend_gold else 0

    act_dismisses_npc = str(
        chosen.get("dismisses_npc")
        or (classification.get("dismisses_npc") if is_custom else "")
        or ""
    ).strip()
    raw_skip = req_skip_minutes if req_skip_minutes is not None else (
        chosen.get("skip_minutes") if chosen.get("skip_minutes") is not None else chosen.get("wait_minutes")
    )
    action = dict(chosen) if not is_custom else {}
    action.update({
        "is_non_lethal": bool(session.get("non_lethal_mode") or action.get("is_non_lethal") or (isinstance(chosen, dict) and chosen.get("is_non_lethal"))),
        "user_id": user_id,
        "character_name": char.get("name", "Player"),
        "char": dict(char),
        "stat": stat,
        "requirement": req_val,
        "mp_cost": mp_cost,
        "mp_spent": mp_spent,
        "_mp_already_deducted": False,
        "gold_spent": actual_gold_spent,
        "_requested_gold": requested_gold,
        "_gold_already_deducted": False,
        "_gold_shortfall_note": gold_shortfall_note,
        "rate": rate,
        "check": res,
        "label": label_text,
        "success": res.succeeded,
        "tier": res.tier,
        "crit": res.tier in ("crit_success", "crit_fail"),
        "roll": res.roll,
        "text": label_text,
        "type": action_type,
        "choice_type": chosen.get("choice_type") or "",
        "action_category": act_cat,
        "intent": act_intent,
        "sub_intent": act_sub_intent,
        "target_npc": act_target or "",
        "ends_dialogue": act_ends_dialogue,
        "_quest_dialogue_handoff": bool(chosen.get("_quest_dialogue_handoff", False)),
        "dismisses_npc": act_dismisses_npc,
        "_stage2_custom_auto_fail": stage2_custom_auto_fail,
        "resolved_intent": resolved_intent,
        "spell_id": chosen.get("spell_id") or "",
        "combat_target": combat_target or chosen.get("combat_target") or (classification.get("combat_target") if is_custom else None),
        "combat_tactical_archetype": chosen.get("combat_tactical_archetype") or (classification.get("combat_tactical_archetype", "") if is_custom else "") or "",
        "target_node_id": chosen.get("target_node_id") or "",
        "target_location": chosen.get("target_location") or (classification.get("target_location", "") if is_custom else "") or "",
        "spawns_npc_role": chosen.get("spawns_npc_role") or (classification.get("spawns_npc_role", "") if is_custom else "") or "",
        "triggers_loot_roll": bool(chosen.get("triggers_loot_roll") or (classification.get("triggers_loot_roll", False) if is_custom else False)),
        "is_quest_action": bool(chosen.get("is_quest_action", False)),
        "is_story_quest": bool(chosen.get("is_story_quest", False)),
        "is_climax_action": bool(chosen.get("is_climax_action", False)),
        "_python_verified_quest": bool(chosen.get("_python_verified_quest", False)),
        "quest_approach": str(chosen.get("quest_approach") or ""),
        "approach": str(chosen.get("approach") or ""),
        "rush_climax": bool(chosen.get("rush_climax", False)),
        "off_hours_fallback": bool(chosen.get("off_hours_fallback", False)),
        "clue_source_id": str(chosen.get("clue_source_id") or ""),
        "is_bonus_clue": bool(chosen.get("is_bonus_clue", False)),
        "breakthrough_leveraged": bool(chosen.get("breakthrough_leveraged", False)),
        "clue_pair_ids": list(chosen.get("clue_pair_ids") or []),
        "quest_id": chosen.get("quest_id") or "",
        "sub_obj_id": chosen.get("sub_obj_id"),
        "stage_index": chosen.get("stage_index"),
        "contract_type": chosen.get("contract_type") or "",
        "item_id": chosen.get("item_id") or req_item_id,
        "item_name": target_item_name,
        "item": target_item_obj,
        "target_type": chosen.get("target_type") or req_target_type or "",
        "target_name": chosen.get("target_name") or req_target_name or act_target or "",
        "target_user_id": chosen.get("target_user_id") if chosen.get("target_user_id") is not None else req_target_user_id,
        "pickup_item_name": chosen.get("pickup_item_name") or "",
        "item_consumed": item_was_consumed,
        "_item_already_removed": False,
        "active_recall": classification.get("_active_recall") if is_custom else chosen.get("_active_recall"),
        "is_stealth": effective_stealth,
        "stance": "stealth" if effective_stealth else "normal",
        "stealth_state": session.get("stealth_state") if isinstance(session, dict) else None,
        "_prev_stealth_state": prev_stealth_state,
        "stealth_outcome": stealth_outcome,
        "skip_minutes": int(raw_skip) if raw_skip not in (None, "") else 0,
        "sleep_mode": str(req_sleep_mode or chosen.get("sleep_mode") or ""),
        "property_id": str(chosen.get("property_id") or ""),
        "price": int(chosen.get("price") or 0) if chosen.get("price") else 0,
        "topic_id": str(chosen.get("topic_id") or ""),
        "category": str(chosen.get("category") or ""),
        "is_covert_ability": bool(chosen.get("is_covert_ability")),
        "is_direct_reply": bool(chosen.get("is_direct_reply")),
        "is_cruel": bool(chosen.get("is_cruel")),
        "_topic_locked_attempt": bool(chosen.get("_topic_locked_attempt")),
        "site_action": str(chosen.get("site_action") or ""),
        "site_id": str(chosen.get("site_id") or ""),
        "step_index": chosen.get("step_index"),
        "use_ward": bool(chosen.get("use_ward")),
        "ward_item_name": str(chosen.get("ward_item_name") or ""),
    })
    if not action.get("active_recall") and isinstance(session, dict) and session.get("id") and label_text:
        from game_engine.turn.generation import extract_deterministic_recall_query
        from db.memory import active_recall_search
        _rc_sid = session["id"]

        def _run_direct_choice_recall():
            rq = extract_deterministic_recall_query(label_text, session_id=_rc_sid)
            return active_recall_search(_rc_sid, rq) if rq else None

        recall_hits = await adb(_run_direct_choice_recall)
        if recall_hits:
            action["active_recall"] = recall_hits
    return action
