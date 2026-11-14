from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, HTTPException, Query, Request
from pydantic import BaseModel
import json
import time

import db
from db import adb
import game_engine
import mechanics.social.persona
import mechanics.social.relationships
import mechanics.social.genealogy
import mechanics.narrative.bounty
from mechanics.system.concurrency import (
    distributed_adventure_lock,
    distributed_session_lock,
    distributed_user_lock,
)
from .security import (
    extract_actor_token,
    extract_verified_token_uid,
    is_strict_auth_context,
    verify_session_participant,
    verify_user_access,
)


async def _verify_missing_session_codex_auth(request: Request | None, user_id: int | str | None) -> None:
    if request is None and not is_strict_auth_context(None):
        return
    tok = extract_actor_token(request)
    if tok is not None or is_strict_auth_context(request):
        valid_uid = int(user_id) if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()) else None
        if valid_uid is not None:
            await verify_user_access(request, valid_uid)
        elif not tok or extract_verified_token_uid(tok) is None:
            raise HTTPException(status_code=401, detail="user_id and actor token are required.")
from mechanics.system.phone import (
    scenario_has_smartphone,
    get_phone_branding,
    detect_custom_message_intent,
    generate_player_chat_message,
    generate_contact_dm_reply,
    generate_gossip_feed_posts,
    scour_feed_for_rumor,
    get_social_state_summary,
    lookup_social_profile,
    discover_suggested_peer,
    resolve_social_friend_request,
    get_suggested_peers,
)
from mechanics.social.factions import (
    get_faction_tier,
    get_hierarchy,
    get_eligible_rank,
    get_rank_title,
    get_incumbent_at_rank,
    get_active_perks,
    ensure_starter_factions,
    sync_faction_rosters_with_contacts,
    generate_procedural_leadership_roster as generate_leadership_roster,
    promote_player_in_roster,
    remove_player_from_roster,
    get_promotion_trial_directive,
    get_agent_dossier_summary,
    join_or_transfer_anomalous_faction,
    infer_anomalous_faction_archetype,
    ANOMALOUS_DISTRUSTED_ARCHETYPES,
)
from mechanics.narrative.clues import evaluate_clue_deduction
from mechanics.world.locations import location_has_bounty_board, get_notice_board_label
from mechanics.combat.items import is_digital_item, parse_digital_item_metadata
from mechanics.combat.loadouts import build_combatant_stat_sheet, compute_companion_vitals, ensure_combatant_loadout
from mechanics.world.world_events.engine import build_client_world_pulse_payload
from .deps import (
    manager,
    _serializable_action,
    PhoneMessageRequest,
    CompanionPartyRequest,
    FactionHQActionRequest,
    PhoneFeedActionRequest,
    PeerPulseDiscoverRequest,
    PeerPulseFriendRequest,
    BountyGenerateRequest,
    BountyActionRequest,
    ClueDeductionRequest,
    SuspectAccusationRequest,
    QuestTurnInRequest,
    EpilogueChoiceRequest,
)

router = APIRouter()


class CancelCommitmentRequest(BaseModel):
    user_id: int | None = None
    reason: str = "player_cancelled"


def _fmt_hhmm(minute_val: int | None) -> str:
    if minute_val is None:
        return "00:00"
    m = int(minute_val) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _enrich_commitments_for_ui(session_id: int, raw_commitments: list[dict] | None, contacts: list[dict] | None = None) -> list[dict]:
    """Enriches commitment rows with friendly display names, subtype badges, and formatted time windows."""
    if not raw_commitments:
        return []
    contact_by_key: dict[str, dict] = {}
    for c in (contacts or []):
        if not isinstance(c, dict):
            continue
        c_nm = str(c.get("name") or "").strip()
        c_id = str(c.get("npc_id") or "").strip()
        if c_id:
            contact_by_key[c_id.lower()] = c
            contact_by_key[c_id.lower().replace("-", "_")] = c
        if c_nm:
            contact_by_key[c_nm.lower()] = c
            contact_by_key[c_nm.lower().replace(" ", "_").replace("-", "_")] = c

    out: list[dict] = []
    for item in raw_commitments:
        if not isinstance(item, dict):
            continue
        d = dict(item)
        d.setdefault("commitment_id", d.get("id"))
        meta = d.get("metadata")
        if not isinstance(meta, dict):
            try:
                meta = json.loads(d.get("metadata_json") or "{}")
            except Exception:
                meta = {}
        d["metadata"] = meta

        parts = d.get("participants")
        if not isinstance(parts, list):
            try:
                parts = json.loads(d.get("participants_json") or "[]")
            except Exception:
                parts = []
        d["participants"] = parts

        src = str(d.get("source_entity") or "").strip()
        tgt = str(d.get("target_entity") or "").strip()
        counterparty_key = tgt if src.lower() in ("player", "") else src
        matched_c = contact_by_key.get(counterparty_key.lower()) or contact_by_key.get(counterparty_key.lower().replace("-", "_"))

        display_name = ""
        npc_id_val = ""
        if matched_c:
            display_name = str(matched_c.get("name") or "").strip()
            npc_id_val = str(matched_c.get("npc_id") or matched_c.get("name") or "").strip()
        if not display_name:
            for p in parts:
                if isinstance(p, dict):
                    pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
                    if pk.lower() not in ("player", ""):
                        display_name = str(p.get("name") or pk).strip()
                        npc_id_val = npc_id_val or str(p.get("npc_id") or pk).strip()
                        break
        if not display_name:
            raw_lbl = str(d.get("npc_name") or counterparty_key or "Counterparty").strip()
            display_name = raw_lbl.replace("_", " ").title() if "_" in raw_lbl and raw_lbl == raw_lbl.lower() else raw_lbl
        if not npc_id_val:
            npc_id_val = str(d.get("npc_id") or counterparty_key or display_name).strip()

        d["target_display_name"] = display_name
        d.setdefault("npc_name", display_name)
        d.setdefault("npc_id", npc_id_val)

        c_type = str(d.get("commitment_type") or "promise").lower()
        subtype = str(meta.get("subtype") or meta.get("purpose") or c_type).strip().lower()
        d["subtype"] = subtype

        s_day = d.get("scheduled_day")
        e_day = d.get("end_day") if d.get("end_day") is not None else s_day
        s_min = d.get("start_minute")
        e_min = d.get("end_minute")
        if c_type == "rendezvous" and s_day is not None:
            if e_day is not None and int(e_day) > int(s_day):
                d["time_window_label"] = f"Day {s_day} {_fmt_hhmm(s_min)} – Day {e_day} {_fmt_hhmm(e_min)}"
            else:
                d["time_window_label"] = f"Day {s_day} • {_fmt_hhmm(s_min)}–{_fmt_hhmm(e_min)}"
        elif meta.get("has_deadline") and s_day is not None:
            d["time_window_label"] = f"Due Day {s_day} • {_fmt_hhmm(e_min)}"
        elif d.get("deadline_turn") is not None:
            d["time_window_label"] = f"Due by Turn #{d['deadline_turn']}"
        else:
            d["time_window_label"] = f"Day {s_day}" if s_day is not None else "Open Obligation"

        out.append(d)
    return out


@router.post("/api/party/companion")
async def manage_party_companion(req: CompanionPartyRequest, request: Request = None):
    """Recruits a high-affinity NPC into the active party (max 2 companions) or dismisses them."""
    await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_adventure_lock(req.user_id, req.session_id):
        return await _execute_manage_party_companion(req)


async def _execute_manage_party_companion(req: CompanionPartyRequest):
    session = await adb(db.get_session, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    action = (req.action or "recruit").strip().lower()
    npc_name = (req.npc_name or "").strip()
    if not npc_name:
        raise HTTPException(status_code=400, detail="npc_name is required")

    if action == "dismiss":
        removed = await adb(db.remove_session_party_npc, req.session_id, npc_name)
        if not removed:
            raise HTTPException(status_code=404, detail=f"{npc_name} is not currently in your party")
        from .adventure import _enrich_session_for_client
        updated_sess = await adb(db.get_session, req.session_id) or {}
        enriched_sess = await adb(_enrich_session_for_client, updated_sess, req.user_id)
        party_npcs = enriched_sess.get("party_npcs") if isinstance(enriched_sess, dict) else await adb(db.get_session_party_npcs, req.session_id)
        return {
            "success": True,
            "status": "dismissed",
            "action": "dismissed",
            "npc_name": npc_name,
            "message": f"{npc_name} has left your party.",
            "party_npcs": party_npcs,
        }

    # Non-combat scenario guard (pure school scenarios are non-combat, but anomalous_high_school enables tactical_combat)
    scen_key = str(session.get("scenario") or "fantasy").lower()
    import scenario_data
    is_pure_hs = scenario_data.has_tag(scen_key, "high_school") and not scenario_data.is_anomalous_incursions_scenario(scen_key)
    if not scenario_data.is_mechanic_enabled(scen_key, "tactical_combat") or scenario_data.has_tag(scen_key, "non_combat") or is_pure_hs:
        raise HTTPException(status_code=400, detail="Party companion recruitment is disabled in non-combat scenarios.")

    # Recruit flow: enforce 2-companion cap
    current_companions = await adb(db.get_session_party_npcs, req.session_id)
    if len(current_companions) >= 2:
        raise HTTPException(status_code=400, detail="Party companion limit reached (max 2 NPC companions).")

    char_row = await adb(db.get_character, req.user_id)
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, req.session_id, char_id)
    if not contacts and char_id != req.user_id:
        contacts = await adb(db.get_contacts, req.session_id, req.user_id)
    matched_contact = next(
        (dict(c) for c in contacts if (c.get("name") or "").strip().lower() == npc_name.lower() or (c.get("npc_id") or "").strip().lower() == npc_name.lower().replace(" ", "_")),
        None
    )
    if not matched_contact:
        lore_data = await adb(db.get_lorebook, req.session_id)
        if isinstance(lore_data, dict):
            matched_contact = next(
                (dict(p) for p in lore_data.get("person", []) if (p.get("name") or "").strip().lower() == npc_name.lower()),
                None
            )
        if not matched_contact:
            curr_npcs = session.get("current_npcs") or []
            matched_contact = next(
                (dict(n) for n in curr_npcs if isinstance(n, dict) and (n.get("name") or "").strip().lower() == npc_name.lower()),
                None
            )
        if not matched_contact and scenario_data.is_anomalous_incursions_scenario(scen_key):
            from mechanics.social.agent_roster import find_special_agent_by_name
            sp_agent = await adb(find_special_agent_by_name, req.session_id, npc_name, scen_key)
            if sp_agent:
                matched_contact = dict(sp_agent)
    if not matched_contact:
        raise HTTPException(status_code=404, detail=f"NPC '{npc_name}' not found in contacts, current scene, or world codex.")

    basic_info = (matched_contact or {}).get("basic_info") or {}
    role_check = str(basic_info.get("role") or basic_info.get("occupation") or matched_contact.get("role") or "").lower()
    if any(m in role_check or m in npc_name.lower() for m in ("merchant", "shopkeeper", "vendor", "apothecary", "peddler", "trader")):
        raise HTTPException(status_code=400, detail=f"{npc_name} is a merchant and cannot be recruited.")

    enemy_list = game_engine.get_active_enemies(session) or []
    if any(game_engine._get_npc_name(e).lower() == npc_name.lower() for e in enemy_list if e):
        raise HTTPException(status_code=400, detail=f"{npc_name} is currently an active enemy and cannot be recruited.")

    score = int((matched_contact or {}).get("relationship_score", 0) or 0)
    from mechanics.social.relationships import get_recruitment_cost
    char_level = max(1, int(char_row.get("level", 1) or 1)) if char_row else 1
    rec_cost = get_recruitment_cost(score, level=char_level)
    char_gold = int(char_row.get("gold", 0) or 0) if char_row else 0
    role_label = str(basic_info.get("role") or basic_info.get("occupation") or matched_contact.get("role") or "Companion")
    comp_stats = build_combatant_stat_sheet(char_level, role_label, role_tier="companion")
    comp_max_hp, comp_max_mp = compute_companion_vitals(char_level, comp_stats, is_civilian=False)
    comp_hp = comp_max_hp
    comp_mp = comp_max_mp
    extra_companion_fields = {
        "level": char_level,
        "stats": comp_stats,
    }

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import evaluate_anomalous_companion_recruitment
        eval_res = await adb(evaluate_anomalous_companion_recruitment, session, req.user_id, matched_contact, score, char_level)
        if not eval_res.get("allowed"):
            raise HTTPException(status_code=400, detail=eval_res.get("reason") or f"Cannot recruit {npc_name}.")
        rec_cost = int(eval_res.get("cost", 0) or 0)
        comp_hp = int(eval_res.get("hp", comp_max_hp) or comp_max_hp)
        comp_max_hp = int(eval_res.get("max_hp", comp_hp) or comp_hp)
        comp_mp = int(eval_res.get("mp", comp_max_mp) or comp_max_mp)
        comp_max_mp = int(eval_res.get("max_mp", comp_mp) or comp_mp)
        extra_companion_fields = {
            "anomalous_npc_tag": "special_agent",
            "is_special_agent": True,
            "agent_tier": eval_res.get("agent_tier", 1),
            "rank_title": eval_res.get("rank_title", ""),
            "agent_class": eval_res.get("agent_class", ""),
            "faction_id": eval_res.get("faction_id", ""),
            "faction_name": eval_res.get("faction_name", ""),
            "innate_abilities": eval_res.get("innate_abilities", []),
            "level": eval_res.get("level", char_level),
            "stats": eval_res.get("stats") or comp_stats,
            "weapon_profile": eval_res.get("weapon_profile", {}),
        }

    if rec_cost > 0:
        if char_gold < rec_cost:
            raise HTTPException(
                status_code=400,
                detail=f"{npc_name} requires at least Friend standing (100 affinity) to join for free, or {rec_cost} gold to recruit (you have {char_gold} gold)."
            )
        await adb(db.apply_hp_mp_delta, req.user_id, gold_delta=-rec_cost)

    npc_payload = {
        "name": (matched_contact or {}).get("name") or npc_name,
        "npc_id": (matched_contact or {}).get("npc_id") or npc_name.lower().replace(" ", "_"),
        "role": extra_companion_fields.get("agent_class") or role_label or "Companion",
        "hp": comp_hp,
        "max_hp": comp_max_hp,
        "mp": comp_mp,
        "max_mp": comp_max_mp,
        "relationship_score": score,
        **extra_companion_fields,
    }
    ensure_combatant_loadout(npc_payload, scenario_key=scen_key)
    added = await adb(db.add_session_party_npc, req.session_id, npc_payload)
    if not added:
        raise HTTPException(status_code=400, detail=f"Could not add {npc_name} to party (party full or already recruited).")

    # Recruited companions enter Party & Known Characters; only >= 100 or explicitly unlocked contacts appear in personal Contacts
    existing_in_contacts = any((c.get("name") or "").strip().lower() == npc_name.lower() for c in contacts)
    delta_to_apply = 0 if existing_in_contacts else score
    c_app = matched_contact.get("appearance") or matched_contact.get("appearance_json")
    if isinstance(c_app, str):
        try:
            import json
            c_app = json.loads(c_app)
        except Exception:
            c_app = {}
    upsert_binfo = dict(basic_info) if isinstance(basic_info, dict) and basic_info else {"role": npc_payload["role"]}
    upsert_binfo["met_in_person"] = True
    if score < 100 and not (
        upsert_binfo.get("exchanged_contact")
        or upsert_binfo.get("added_via_peerpulse")
        or upsert_binfo.get("unlocked_via_friendship")
    ):
        upsert_binfo.pop("contact_added", None)
        upsert_binfo.pop("is_contact", None)
    if extra_companion_fields.get("anomalous_npc_tag") == "special_agent":
        upsert_binfo.update({
            "anomalous_npc_tag": "special_agent",
            "is_special_agent": True,
            "agent_tier": extra_companion_fields.get("agent_tier", 1),
            "rank_title": extra_companion_fields.get("rank_title", ""),
            "agent_class": extra_companion_fields.get("agent_class", ""),
            "faction_id": extra_companion_fields.get("faction_id", ""),
            "faction": extra_companion_fields.get("faction_name", ""),
            "innate_abilities": extra_companion_fields.get("innate_abilities", []),
        })
    await adb(
        db.upsert_contact,
        session_id=req.session_id,
        character_id=char_id,
        npc_id=npc_payload["npc_id"],
        name=npc_payload["name"],
        basic_info=upsert_binfo,
        delta_score=delta_to_apply,
        track="platonic",
        race=matched_contact.get("race", "") or "",
        gender=matched_contact.get("gender", "") or "",
        appearance=c_app if isinstance(c_app, dict) else None,
    )

    from .adventure import _enrich_session_for_client
    try:
        from mechanics.world.world_events.social_hooks import handle_mid_rumor_npc_promotion
        await adb(handle_mid_rumor_npc_promotion, req.session_id, npc_name=npc_payload["name"])
    except Exception:
        pass
    updated_sess = await adb(db.get_session, req.session_id) or {}
    try:
        from game_engine.quest_turn_resolver import handle_npc_death_or_recruitment_fallout
        await adb(
            handle_npc_death_or_recruitment_fallout,
            req.session_id,
            npc_payload["name"],
            "recruited",
            str(updated_sess.get("current_location") or ""),
            int(db.infer_session_turn(updated_sess)),
        )
    except Exception:
        pass
    enriched_sess = await adb(_enrich_session_for_client, updated_sess, req.user_id)
    party_npcs = enriched_sess.get("party_npcs") if isinstance(enriched_sess, dict) else await adb(db.get_session_party_npcs, req.session_id)
    return {
        "success": True,
        "status": "recruited",
        "action": "recruited",
        "npc_name": npc_payload["name"],
        "message": f"{npc_payload['name']} joined your party!",
        "party_npcs": party_npcs,
    }


def _infer_school_grade_badge(role: str, current_grade: str, scen_key: str) -> str:
    """Infers academic standing or faculty/staff badge for school characters."""
    if current_grade and str(current_grade).strip():
        return str(current_grade).strip()
    from mechanics.social.roster_tags import normalize_standing, is_school_scenario
    if not is_school_scenario(scen_key):
        return ""
    return normalize_standing(role=role, grade=current_grade, scen_key=scen_key)


@router.get("/api/lorebook/{session_id}")
async def get_lorebook(session_id: int, user_id: int | None = Query(None), request: Request = None):
    """Fetches lorebook entities grouped by category, restricting person entities to discovered characters."""
    import re
    from mechanics.social.persona import infer_contact_gender
    from mechanics.social.persona.intimacy.appearance import normalize_appearance

    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    session = raw_sess or {}
    scen_key = str(session.get("scenario") or "fantasy")
    curr_npcs = session.get("current_npcs") or []
    party_npcs = await adb(db.get_session_party_npcs, session_id) or []
    dialogue_partner = session.get("dialogue_partner") or ""

    valid_uid = user_id if isinstance(user_id, int) else (int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None)
    lookup_uid = valid_uid or session.get("host_user_id") or 0
    settings = await adb(db.get_settings, lookup_uid) if lookup_uid else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))
    phys_st = session.get("physical_state") if isinstance(session.get("physical_state"), dict) else None

    import scenario_data as _sd_lore
    if _sd_lore.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents
        await adb(prune_unmet_preseeded_special_agents, session_id)

    grouped = await adb(db.get_lorebook, session_id)
    commitments = await adb(db.get_active_commitments, session_id)
    contacts = await adb(db.get_contacts, session_id) or []
    school_roster = await adb(db.get_school_roster, session_id) or []
    dir_by_name = {str(d.get("name", "")).strip().lower(): d for d in school_roster if d.get("name")}

    contact_map = {
        (c.get("name") or "").lower().strip(): c
        for c in contacts if c.get("name")
    }

    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    player_char_name = str((char_row or {}).get("name") or session.get("character_name") or "").strip().lower()

    party_names = {
        str(p.get("name", "")).strip().lower()
        for p in (party_npcs or [])
        if isinstance(p, dict) and p.get("name")
    } | {
        str(p).strip().lower() for p in (party_npcs or []) if isinstance(p, str) and p.strip()
    }

    from mechanics.social.relationships import (
        collect_met_npc_names,
        is_npc_discovered_by_player,
        is_unlocked_contact,
    )
    met_in_story_names = collect_met_npc_names(session, party_npcs=party_npcs, player_char_name=player_char_name)
    codex_char_id = int((char_row or {}).get("id") or 0)
    codex_ui_lang = str((settings or {}).get("ui_language") or "en")
    codex_fow_ctx = await adb(_preload_fog_of_war_context, session_id, codex_char_id, party_names, codex_ui_lang)

    discovered_people_names = set()
    all_entities = []

    if isinstance(grouped, dict):
        for cat, items in grouped.items():
            for it in items:
                it_dict = dict(it)
                is_person = (cat == "person" or it_dict.get("entity_type") == "person")

                if is_person:
                    p_name = (it_dict.get("name") or "").lower().strip()
                    if p_name == player_char_name:
                        continue
                    c = contact_map.get(p_name)
                    dir_entry = dir_by_name.get(p_name)
                    score = int(it_dict.get("relationship_score", 0) or 0)
                    if c:
                        score = int(c.get("relationship_score", 0) or 0)

                    # A character is strictly discovered if met in person (scene, turn history, party), has active affinity, or is an explicit contact
                    is_discovered = is_npc_discovered_by_player(
                        p_name,
                        c,
                        met_in_story_names,
                        party_names=party_names,
                        score_override=score,
                    )

                    # Filter out unencountered background faction / directory placeholders
                    if not is_discovered:
                        continue

                    # Enrich person details
                    it_dict["relationship_score"] = score
                    if c:
                        b_info = c.get("basic_info") or {}
                        if isinstance(b_info, str):
                            try:
                                b_info = json.loads(b_info)
                            except Exception:
                                b_info = {}
                        it_dict["grade"] = it_dict.get("grade") or b_info.get("grade") or ""
                        it_dict["club"] = it_dict.get("club") or b_info.get("club") or ""
                        it_dict["mannerisms"] = it_dict.get("mannerisms") or b_info.get("mannerisms") or ""
                        it_dict["description"] = it_dict.get("description") or b_info.get("description") or ""
                        it_dict["race"] = it_dict.get("race") or c.get("race") or b_info.get("race") or "human"
                        it_dict["gender"] = it_dict.get("gender") or c.get("gender") or b_info.get("gender") or ""
                        it_dict["role"] = it_dict.get("role") or b_info.get("role") or b_info.get("occupation") or ""
                        if c.get("appearance"):
                            it_dict["appearance"] = c["appearance"]
                            it_dict["appearance_json"] = c.get("appearance_json") or json.dumps(c["appearance"])

                    if dir_entry:
                        it_dict["grade"] = it_dict.get("grade") or dir_entry.get("grade") or ""
                        it_dict["club"] = it_dict.get("club") or dir_entry.get("club") or ""
                        it_dict["mannerisms"] = it_dict.get("mannerisms") or dir_entry.get("mannerisms") or ""
                        if dir_entry.get("race"):
                            it_dict["race"] = dir_entry["race"]
                        else:
                            it_dict["race"] = it_dict.get("race") or "human"
                        if dir_entry.get("gender"):
                            it_dict["gender"] = dir_entry["gender"]
                        else:
                            it_dict["gender"] = it_dict.get("gender") or ""
                        it_dict["role"] = it_dict.get("role") or dir_entry.get("role") or ""

                    # Fallback hydration from current scene NPCs or description
                    matched_curr_npc = next((n for n in curr_npcs if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == p_name), None)
                    if matched_curr_npc:
                        c_role_val = matched_curr_npc.get("role")
                        if c_role_val and str(c_role_val).lower() != "none":
                            it_dict["role"] = it_dict.get("role") or str(c_role_val)
                        if matched_curr_npc.get("grade"):
                            it_dict["grade"] = it_dict.get("grade") or str(matched_curr_npc["grade"])
                        if matched_curr_npc.get("club"):
                            it_dict["club"] = it_dict.get("club") or str(matched_curr_npc["club"])

                    if not it_dict.get("role") or str(it_dict.get("role")).lower() == "none":
                        desc_str = str(it_dict.get("description") or "")
                        m_desc_role = re.search(r"\(([^)]+)\)", desc_str)
                        if m_desc_role:
                            extracted_role = m_desc_role.group(1).strip()
                            if extracted_role and not any(k in extracted_role.lower() for k in ("née", "nee", "formerly")):
                                it_dict["role"] = extracted_role

                    it_dict["grade"] = _infer_school_grade_badge(it_dict.get("role") or "", it_dict.get("grade") or "", scen_key)

                    # Ensure valid gender
                    raw_g = str(it_dict.get("gender") or "").strip().lower()
                    if not raw_g or raw_g in ("unknown", "none"):
                        it_dict["gender"] = infer_contact_gender({"name": it_dict.get("name"), "basic_info": it_dict}) or "female"

                    # Ensure full normalized appearance
                    app = it_dict.get("appearance")
                    if isinstance(app, str):
                        try:
                            app = json.loads(app)
                        except Exception:
                            app = {}
                    if not isinstance(app, dict):
                        app = {}

                    has_full_app = bool(
                        app.get("eye_color") and app.get("hair_color") and (app.get("stature") or app.get("physique"))
                    )
                    if not has_full_app:
                        norm_app = normalize_appearance(
                            app,
                            gender=it_dict["gender"],
                            race=it_dict.get("race", "human"),
                            scen_key=scen_key,
                            desc=it_dict.get("description", ""),
                            name=it_dict.get("name", "")
                        )
                        it_dict["appearance"] = norm_app
                        it_dict["appearance_json"] = json.dumps(norm_app)

                    # Enrich full dossier for character profile viewing
                    it_basic = it_dict.get("basic_info") or {}
                    if isinstance(it_basic, str):
                        try:
                            it_basic = json.loads(it_basic)
                        except Exception:
                            it_basic = {}
                    if not it_basic.get("role"):
                        it_basic["role"] = it_dict.get("role") or ""
                    if not it_basic.get("grade"):
                        it_basic["grade"] = it_dict.get("grade") or ""
                    if not it_basic.get("club"):
                        it_basic["club"] = it_dict.get("club") or ""
                    it_basic.setdefault("race", it_dict.get("race") or "human")
                    it_basic.setdefault("gender", it_dict["gender"])
                    it_basic.setdefault("description", it_dict.get("description") or "")
                    it_basic.setdefault("mannerisms", it_dict.get("mannerisms") or "")
                    it_dict["basic_info"] = it_basic

                    enriched_person = _enrich_contact_record(it_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st, party_names=party_names, fow_context=codex_fow_ctx)
                    it_dict.update(enriched_person)
                    it_dict["is_contact"] = bool(c is not None and is_unlocked_contact(c, party_names, met_in_story_names=met_in_story_names))
                    it_dict["is_discovered"] = True

                    discovered_people_names.add(p_name)
                    all_entities.append(it_dict)
                else:
                    # Non-person world lore entry (place, faction, artifact, world concept)
                    all_entities.append(it_dict)

        # Merge in any discovered contacts not yet in all_entities
        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            c_name_lower = c_name.lower()
            if not c_name or c_name_lower == player_char_name or c_name_lower in discovered_people_names:
                continue

            score = int(c.get("relationship_score", 0) or 0)
            is_discovered_c = is_npc_discovered_by_player(
                c_name_lower,
                c,
                met_in_story_names,
                party_names=party_names,
                score_override=score,
            )
            if not is_discovered_c:
                continue

            b_info = c.get("basic_info") or {}
            if isinstance(b_info, str):
                try:
                    b_info = json.loads(b_info)
                except Exception:
                    b_info = {}

            dir_entry_c = dir_by_name.get(c_name_lower)
            c_gender = (dir_entry_c.get("gender") if dir_entry_c else None) or c.get("gender") or b_info.get("gender") or infer_contact_gender({"name": c_name, "basic_info": b_info}) or "female"
            c_race = (dir_entry_c.get("race") if dir_entry_c else None) or c.get("race") or b_info.get("race") or "human"
            c_app = c.get("appearance")
            if isinstance(c_app, str):
                try:
                    c_app = json.loads(c_app)
                except Exception:
                    c_app = {}
            if not isinstance(c_app, dict) or not (c_app.get("eye_color") and c_app.get("hair_color")):
                c_app = normalize_appearance(c_app or {}, gender=c_gender, race=c_race, scen_key=scen_key, desc=b_info.get("description", ""), name=c_name)

            p_dict = dict(c)
            p_dict["name"] = c_name
            p_dict["role"] = b_info.get("role") or b_info.get("occupation") or (dir_entry_c.get("role") if dir_entry_c else None) or "Contact"
            p_dict["race"] = c_race
            p_dict["gender"] = c_gender
            raw_c_grade = b_info.get("grade") or (dir_entry_c.get("grade") if dir_entry_c else "") or ""
            p_dict["grade"] = _infer_school_grade_badge(p_dict["role"], raw_c_grade, scen_key)
            p_dict["club"] = b_info.get("club") or (dir_entry_c.get("club") if dir_entry_c else "") or ""
            p_dict["mannerisms"] = b_info.get("mannerisms") or (dir_entry_c.get("mannerisms") if dir_entry_c else "") or ""
            p_dict["description"] = b_info.get("description") or (dir_entry_c.get("personality_summary") if dir_entry_c else "") or ""
            p_dict["appearance"] = c_app
            p_dict["appearance_json"] = json.dumps(c_app)
            p_dict["entity_type"] = "person"
            p_dict["basic_info"] = b_info
            p_dict["relationship_score"] = score
            p_dict["is_contact"] = bool(is_unlocked_contact(c, party_names, met_in_story_names=met_in_story_names))
            p_dict["is_discovered"] = True

            enriched_p = _enrich_contact_record(p_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st, party_names=party_names, fow_context=codex_fow_ctx)
            p_dict.update(enriched_p)
            grouped.setdefault("person", []).append(p_dict)
            all_entities.append(p_dict)
            discovered_people_names.add(c_name_lower)

        # Synthesize any characters met in person who had neither lorebook nor contact entry
        for met_name_lower in met_in_story_names:
            if met_name_lower in discovered_people_names or met_name_lower == player_char_name:
                continue
            r_entry = dir_by_name.get(met_name_lower)
            matched_curr_npc = None
            for n in curr_npcs:
                if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == met_name_lower:
                    matched_curr_npc = n
                    break

            display_name = (r_entry.get("name") if r_entry else None) or (matched_curr_npc.get("name") if matched_curr_npc else met_name_lower.title())
            synth_gender = (r_entry.get("gender") if r_entry else None) or (matched_curr_npc.get("gender") if matched_curr_npc else None) or infer_contact_gender({"name": display_name, "basic_info": matched_curr_npc or {}}) or "female"
            synth_race = (r_entry.get("race") if r_entry else None) or (matched_curr_npc.get("race") if matched_curr_npc else None) or "human"
            synth_role = (r_entry.get("role") if r_entry else None) or (matched_curr_npc.get("role") if matched_curr_npc else "Acquaintance")
            raw_s_grade = (r_entry.get("grade") if r_entry else None) or (matched_curr_npc.get("grade") if matched_curr_npc else "") or ""
            synth_grade = _infer_school_grade_badge(synth_role, raw_s_grade, scen_key)
            synth_club = (r_entry.get("club") if r_entry else None) or (matched_curr_npc.get("club") if matched_curr_npc else "") or ""
            synth_desc = (r_entry.get("personality_summary") if r_entry else None) or (matched_curr_npc.get("description") if matched_curr_npc else "") or ""
            synth_app = normalize_appearance(
                (matched_curr_npc.get("appearance") if isinstance(matched_curr_npc, dict) and isinstance(matched_curr_npc.get("appearance"), dict) else {}),
                gender=synth_gender,
                race=synth_race,
                scen_key=scen_key,
                desc=synth_desc,
                name=display_name,
            )
            p_dict = {
                "name": display_name,
                "formal_title": (r_entry.get("formal_title") if r_entry else "") or "",
                "role": synth_role,
                "grade": synth_grade,
                "club": synth_club,
                "race": synth_race,
                "gender": synth_gender,
                "description": synth_desc,
                "appearance": synth_app,
                "appearance_json": json.dumps(synth_app),
                "basic_info": {
                    "role": synth_role,
                    "grade": synth_grade,
                    "club": synth_club,
                    "race": synth_race,
                    "gender": synth_gender,
                    "description": synth_desc,
                },
                "entity_type": "person",
                "relationship_score": 0,
                "is_contact": False,
                "is_discovered": True,
            }
            enriched_p = _enrich_contact_record(p_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st, party_names=party_names, fow_context=codex_fow_ctx)
            p_dict.update(enriched_p)
            p_dict["is_discovered"] = True
            grouped.setdefault("person", []).append(p_dict)
            all_entities.append(p_dict)
            discovered_people_names.add(met_name_lower)

        # Update categories["person"] to only discovered people
        grouped["person"] = [
            e for e in all_entities if e.get("entity_type") == "person"
        ]

    return {
        "categories": grouped,
        "entities": all_entities,
        "commitments": _enrich_commitments_for_ui(session_id, commitments, contacts),
        "world_pulse": await adb(build_client_world_pulse_payload, session_id),
    }


def _preload_fog_of_war_context(
    session_id: int,
    character_id: int,
    party_names: set[str] | None = None,
    lang: str = "en",
) -> dict:
    """Batch-loads dossier discoveries and kin/romance/party exemptions in O(1) queries to prevent N+1 loops."""
    import mechanics.social.relationship_graph as rg

    cid = int(character_id or 0)
    sid = int(session_id or 0)
    disc_by_npc = db.get_contact_dossier_discoveries_batch(sid, cid) if sid else {}
    ex_sets = db.get_player_fow_exemption_sets(sid) if sid else {}
    party_npc_keys = set(ex_sets.get("party_npc_keys") or set()) | {
        db.canon_social_npc_id(n) for n in (party_names or set()) if str(n).strip()
    }
    kin_npc_keys = set(ex_sets.get("kin_npc_keys") or set())
    romantic_npc_keys = set(ex_sets.get("romantic_npc_keys") or set())
    return {
        "character_id": cid,
        "lang": str(lang or "en"),
        "disc_by_npc": disc_by_npc,
        "party_npc_keys": party_npc_keys,
        "kin_npc_keys": kin_npc_keys,
        "romantic_npc_keys": romantic_npc_keys,
    }


def _enrich_contact_record(
    c_raw: dict,
    session_id: int,
    scen_key: str,
    debug_reveal_all: bool,
    phys_st: dict | None = None,
    party_names: set[str] | None = None,
    fow_context: dict | None = None,
) -> dict:
    from mechanics.social.relationships import enrich_contact_dossier
    from mechanics.social.roster_tags import resolve_character_badges
    c_in = dict(c_raw or {})
    preloaded_disc = None
    fow_lang = "en"
    party_keys = None
    kin_keys = None
    rom_keys = None
    if isinstance(fow_context, dict):
        if fow_context.get("character_id") and not c_in.get("character_id"):
            c_in["character_id"] = int(fow_context["character_id"])
        fow_lang = str(fow_context.get("lang") or "en")
        canon_nid = db.canon_social_npc_id(c_in.get("npc_id") or c_in.get("name") or "")
        disc_map = fow_context.get("disc_by_npc")
        if isinstance(disc_map, dict):
            preloaded_disc = disc_map.get(canon_nid, [])
        party_keys = fow_context.get("party_npc_keys")
        kin_keys = fow_context.get("kin_npc_keys")
        rom_keys = fow_context.get("romantic_npc_keys")
    res = enrich_contact_dossier(
        c_in,
        session_id,
        scen_key,
        debug_reveal_all=debug_reveal_all,
        phys_st=phys_st,
        preloaded_discoveries=preloaded_disc,
        lang=fow_lang,
        party_npc_keys=party_keys,
        kin_npc_keys=kin_keys,
        romantic_npc_keys=rom_keys,
    )
    if not res.get("grade"):
        b_inf = res.get("basic_info") or {}
        raw_g = b_inf.get("grade") if isinstance(b_inf, dict) else ""
        inferred = _infer_school_grade_badge(res.get("role") or "", raw_g, scen_key)
        if inferred:
            res["grade"] = inferred

    c_badges = resolve_character_badges(
        res,
        scen_key=scen_key,
        party_names=party_names,
        is_contact=True,
        is_blocked=bool(res.get("is_blocked")),
    )
    res["standing"] = c_badges.standing
    res["age_group"] = c_badges.age_group
    res["badges"] = c_badges.badges
    res["is_student"] = c_badges.is_student
    res["is_faculty"] = c_badges.is_faculty
    res["is_staff"] = c_badges.is_staff
    res["is_citizen"] = c_badges.is_citizen
    res["is_merchant"] = c_badges.is_merchant
    res["is_special_agent"] = c_badges.is_special_agent

    # Only enrolled school students belong to school clubs; regular adults/citizens have no club.
    if not res.get("is_student"):
        res["club"] = ""
        if isinstance(res.get("basic_info"), dict):
            res["basic_info"]["club"] = ""
        # Self-heal adult characters whose role was previously polluted with "Club Member"
        cur_r = str(res.get("role") or (res.get("basic_info") or {}).get("role") or "").strip()
        if cur_r.lower() in ("club member", "club officer", "club vice president", "club secretary", "club treasurer", "events coordinator"):
            desc_str = str(res.get("description") or (res.get("basic_info") or {}).get("description") or "")
            import re as _re_role
            m_p = _re_role.search(r"\(([^)]{3,45})\)", desc_str)
            healed_role = m_p.group(1).strip() if (m_p and not any(k in m_p.group(1).lower() for k in ("née", "nee", "formerly"))) else "Citizen"
            res["role"] = healed_role
            res["public_role"] = healed_role
            if isinstance(res.get("basic_info"), dict):
                res["basic_info"]["role"] = healed_role
                res["basic_info"]["public_role"] = healed_role
                res["basic_info"].pop("club_role", None)
                if res.get("is_citizen") and not res.get("is_special_agent"):
                    res["basic_info"].pop("faction", None)
                    res.pop("faction", None)

    # Faction affiliation is tracked separately from school club so student agents show both.
    res["faction_affiliation"] = _resolve_faction_affiliation(res)

    return res


def _resolve_faction_affiliation(res: dict) -> str:
    """Returns the NPC's faction/agency affiliation, never echoing the school club as a faction."""
    b_inf = res.get("basic_info") if isinstance(res.get("basic_info"), dict) else {}
    # Unawakened mundane citizens who were accidentally assigned an anomalous syndicate by legacy club RNG should not display a faction
    if res.get("is_citizen") and not res.get("is_special_agent") and str(b_inf.get("club_role") or "").lower().startswith("club "):
        return ""
    club_low = str(res.get("club") or b_inf.get("club") or "").strip().lower()
    for cand in (res.get("faction_name"), b_inf.get("faction_name"), b_inf.get("faction"), res.get("faction"), b_inf.get("affiliation"), res.get("affiliation")):
        val = str(cand or "").strip()
        if val and val.lower() not in ("none", "unaffiliated", "unknown") and val.lower() != club_low:
            return val
    return ""


@router.get("/api/contacts/{session_id}")
async def get_contacts(session_id: int, user_id: int | None = Query(None), request: Request = None):
    """Fetches NPC contacts and relationship standings."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    session = raw_sess or {}
    scen_key = session.get("scenario", "fantasy")
    phys_st = session.get("physical_state") if isinstance(session.get("physical_state"), dict) else None
    valid_uid = user_id if isinstance(user_id, int) else (int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None)
    lookup_uid = valid_uid or session.get("host_user_id") or 0
    settings = await adb(db.get_settings, lookup_uid) if lookup_uid else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))
    from scenario_data import is_nsfw_scenario, is_anomalous_incursions_scenario
    if is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents
        await adb(prune_unmet_preseeded_special_agents, session_id)
    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    if not contacts and lookup_uid and char_id != lookup_uid:
        contacts = await adb(db.get_contacts, session_id, lookup_uid)
    from mechanics.social.relationships import collect_met_npc_names, is_unlocked_contact
    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    met_names = collect_met_npc_names(session, party_npcs=party_npcs)

    # Pre-filter unlocked contacts before expensive enrichment loop
    unlocked_raw = [c for c in (contacts or []) if is_unlocked_contact(c, party_names, met_in_story_names=met_names)]
    enriched_contacts = await adb(
        lambda: (
            lambda _fow=_preload_fog_of_war_context(session_id, char_id, party_names, str((settings or {}).get("ui_language") or "en")): [
                _enrich_contact_record(c, session_id, scen_key, debug_reveal_all, phys_st=phys_st, party_names=party_names, fow_context=_fow)
                for c in unlocked_raw
            ]
        )()
    )
    return {
        "contacts": enriched_contacts,
        "is_nsfw": is_nsfw_scenario(scen_key),
        "scenario": scen_key
    }


def _enrich_factions_list(session_id: int, user_id: int | None = None) -> dict:
    import scenario_data

    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    lookup_uid = user_id or session.get("host_user_id")
    char = db.get_character(lookup_uid) if lookup_uid else None

    try:
        ensure_starter_factions(session_id, scen_key)
        if is_anom:
            from mechanics.social.agent_roster import ensure_anomalous_agent_roster
            ensure_anomalous_agent_roster(session_id, scen_key)
        sync_faction_rosters_with_contacts(session_id)
    except Exception:
        pass

    agent_dossier = get_agent_dossier_summary(session_id, lookup_uid) if is_anom else {"is_anomalous_incursions": False}
    if is_anom and isinstance(agent_dossier, dict):
        arc_key = str(session.get("current_arc") or session.get("chapter_number") or session.get("act_number") or 1)
        cal_map = dict(session.get("telemetry_calibrations_used") or {})
        used_in_arc = int(cal_map.get(arc_key, 0) or 0)
        p_tier = int(agent_dossier.get("promotion_tier") or 0)
        agent_dossier["telemetry_calibrations_used"] = cal_map
        agent_dossier["current_arc_key"] = arc_key
        agent_dossier["can_calibrate_telemetry"] = bool(p_tier >= 4 and used_in_arc < 1)
        if lookup_uid:
            agent_dossier["character_3axis"] = db.get_character_3axis(lookup_uid)
    char = db.get_character(lookup_uid) if lookup_uid else None
    membership = {
        "joined_faction_id": (char or {}).get("joined_faction_id") or "",
        "faction_rank": int((char or {}).get("faction_rank") or 0),
        "faction_title": (char or {}).get("faction_title") or "",
    }

    raw_factions = db.get_factions(session_id)
    enriched = []
    for f in raw_factions:
        f_dict = dict(f)
        f_dict.setdefault("hq_display_name", f_dict.get("hq_location_id", ""))
        rep = int(f_dict.get("reputation_score") or 0)
        template = f_dict.get("hierarchy_template") or f_dict.get("category") or "default"
        roster = f_dict.get("leadership_roster") or []
        if not roster:
            roster = generate_leadership_roster(template, scen_key, f_dict.get("name", ""))
            db.update_faction_leadership_roster(session_id, f_dict["faction_id"], roster)
            f_dict["leadership_roster"] = roster

        f_dict["tier"] = get_faction_tier(rep)
        f_dict["hierarchy"] = get_hierarchy(template)
        f_dict["eligible_rank"] = get_eligible_rank(template, rep)
        f_dict["is_member"] = bool(
            membership["joined_faction_id"]
            and membership["joined_faction_id"].lower() == (f_dict.get("faction_id") or "").lower()
        )
        f_dict["player_rank"] = membership["faction_rank"] if f_dict["is_member"] else 0
        f_dict["player_title"] = membership["faction_title"] if f_dict["is_member"] else ""
        eff_rank = f_dict["player_rank"] or (1 if rep > 0 else 0)
        perks = get_active_perks(f_dict, eff_rank, rep)
        f_dict["active_perks"] = perks or []
        f_dict["rival_faction_ids"] = f_dict.get("rival_faction_ids") or []
        from mechanics.social.factions import is_school_club_faction, get_faction_category_tag
        f_dict["is_school_club"] = is_school_club_faction(f_dict)
        f_dict["category_tag"] = get_faction_category_tag(f_dict, scen_key)
        if is_anom:
            arch = infer_anomalous_faction_archetype(f_dict)
            f_dict["archetype_key"] = arch
            f_dict["joinable"] = arch not in ANOMALOUS_DISTRUSTED_ARCHETYPES
            f_dict["diplomatic_stance"] = "distrusted" if arch in ANOMALOUS_DISTRUSTED_ARCHETYPES else "friendly"
        enriched.append(f_dict)

    return {"factions": enriched, "membership": membership, "agent_dossier": agent_dossier}


@router.get("/api/factions/{session_id}")
async def get_factions(session_id: int, user_id: int | None = None, request: Request = None):
    """Fetches faction standings, Rank 1-4 leadership rosters, hierarchy templates, and player membership."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    return await adb(_enrich_factions_list, session_id, user_id)


@router.post("/api/factions/{session_id}/hq-action")
async def faction_hq_action(session_id: int, req: FactionHQActionRequest, request: Request = None):
    """Executes a Faction HQ operation: join, leave, rest, quartermaster, bounty, or promote."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_user_lock(req.user_id):
        async with distributed_session_lock(session_id):
            return await _execute_faction_hq_action(session_id, req)


async def _execute_faction_hq_action(session_id: int, req: FactionHQActionRequest):
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")

    faction = await adb(db.get_faction, session_id, req.faction_id)
    if not faction:
        raise HTTPException(status_code=404, detail=f"Faction '{req.faction_id}' not found")

    action = (req.action or "").strip().lower()
    scen_key = session.get("scenario", "fantasy")
    template = faction.get("hierarchy_template") or faction.get("category") or "default"
    rep = int(faction.get("reputation_score") or 0)
    tier = get_faction_tier(rep)
    char_id = char["id"]
    joined_fid = (char.get("joined_faction_id") or "").strip().lower()
    target_fid = (faction.get("faction_id") or "").strip().lower()

    import scenario_data
    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)

    if action in ("join", "transfer"):
        if is_anom:
            res = await adb(join_or_transfer_anomalous_faction, session_id, faction["faction_id"], req.user_id)
            if not res.get("success"):
                raise HTTPException(status_code=400, detail=res.get("error", "Cannot join this faction."))
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            return {
                "success": True,
                "action": action,
                "message": res.get("message", f"Joined {faction.get('name')}!"),
                **payload,
            }
        if joined_fid and joined_fid != target_fid:
            raise HTTPException(
                status_code=400,
                detail="You are already pledged to a faction! Leave your current faction before joining another."
            )
        rank_1_title = get_rank_title(template, 1)
        await adb(db.set_character_faction_membership, char_id, faction["faction_id"], 1, rank_1_title)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return {
            "success": True,
            "action": "join",
            "message": f"Welcome to {faction.get('name', 'the faction')}! You are now a Rank 1 {rank_1_title}.",
            **payload,
        }

    if action == "leave":
        from mechanics.social.factions import is_school_club_faction
        if is_anom:
            fallback_target = "student_freelancer" if (scenario_data.is_anomalous_high_school_scenario(scen_key) and is_school_club_faction(faction)) else "freelancer"
            res = await adb(join_or_transfer_anomalous_faction, session_id, fallback_target, req.user_id)
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            return {
                "success": True,
                "action": "leave",
                "message": res.get("message", f"You have parted ways with {faction.get('name')}."),
                **payload,
            }
        roster = faction.get("leadership_roster") or []
        if roster:
            cleaned_roster = remove_player_from_roster(roster, char["name"], template, scen_key)
            await adb(db.update_faction_leadership_roster, session_id, faction["faction_id"], cleaned_roster)
        await adb(db.set_character_faction_membership, char_id, "", 0, "")
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return {
            "success": True,
            "action": "leave",
            "message": f"You have parted ways with {faction.get('name', 'the faction')}.",
            **payload,
        }

    if action == "rest":
        from mechanics.social.factions import is_school_club_faction
        is_club = is_school_club_faction(faction)
        if is_anom and not is_club:
            from mechanics.social.factions import get_anomalous_faction_state, infer_anomalous_faction_archetype
            a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
            fac_arch = infer_anomalous_faction_archetype(faction)
            if str(a_st.get("faction_archetype_key") or "") != fac_arch:
                raise HTTPException(
                    status_code=403,
                    detail=f"Safehouse recovery quarters at {faction.get('name', 'this faction')} are restricted to enlisted operatives."
                )
        elif tier["tier_level"] < 2 and not (is_anom and is_club):
            raise HTTPException(
                status_code=400,
                detail="You need Liked standing or higher (+1 Rep) to use the faction safehouse rest."
            )
        await adb(db.apply_hp_mp_delta, req.user_id, char["max_hp"], char["max_mp"], 0)
        party_npcs_rest = await adb(db.get_session_party_npcs, session_id)
        if party_npcs_rest:
            rested_companions = []
            for p_comp in party_npcs_rest:
                if isinstance(p_comp, dict):
                    p_comp = dict(p_comp)
                    p_comp["hp"] = int(p_comp.get("max_hp", p_comp.get("hp", 100)) or 100)
                    p_comp["mp"] = int(p_comp.get("max_mp", p_comp.get("mp", 0)) or 0)
                    p_comp["status_effects"] = [
                        s for s in (p_comp.get("status_effects") or [])
                        if not any(k in str(s).lower() for k in ("incapacitated", "knocked out", "exhausted", "triage"))
                    ]
                    rested_companions.append(p_comp)
            await adb(db.set_session_party_npcs, session_id, rested_companions)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return {
            "success": True,
            "action": "rest",
            "hp": char["max_hp"],
            "mp": char["max_mp"],
            "message": f"You rest at the {faction.get('name', 'Faction')} safehouse, recovering all HP and MP safely.",
            **payload,
        }

    if action == "quartermaster":
        fac_arch = ""
        from mechanics.social.factions import is_school_club_faction
        is_club = is_school_club_faction(faction)
        if is_anom and is_club:
            from mechanics.social.factions import get_anomalous_faction_state
            a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
            joined_club = str(a_st.get("joined_club_name") or "")
            if joined_club.lower() != str(faction.get("name", "")).lower():
                raise HTTPException(
                    status_code=403,
                    detail=f"Club quartermaster equipment is reserved for active members of {faction.get('name', 'this club')}."
                )
        elif is_anom and not is_club:
            from mechanics.social.factions import (
                ANOMALOUS_DISTRUSTED_ARCHETYPES,
                get_anomalous_faction_state,
                infer_anomalous_faction_archetype,
            )
            fac_arch = infer_anomalous_faction_archetype(faction)
            if fac_arch in ANOMALOUS_DISTRUSTED_ARCHETYPES:
                raise HTTPException(
                    status_code=403,
                    detail=f"{faction.get('name', 'This group')} operates clandestinely without an official requisition quartermaster."
                )
            a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
            player_arch = str(a_st.get("faction_archetype_key") or "freelancer")
            if fac_arch in ("private_agency_1", "private_agency_2", "monastic_order") and player_arch != fac_arch:
                raise HTTPException(
                    status_code=403,
                    detail=f"{faction.get('name', 'This organization')} Quartermaster access is restricted exclusively to contracted operatives of this organization."
                )
        current_day, current_minute, _ = await adb(db.get_session_time, session_id)
        merchant = session.setdefault("merchant", {})
        faction_key = (
            f"faction_{faction['faction_id']}:monastic_daily"
            if (is_anom and fac_arch == "monastic_order")
            else f"faction_{faction['faction_id']}"
        )
        from mechanics.combat.merchant import (
            generate_faction_quartermaster_shop,
            get_or_create_merchant_catalogue,
            update_merchant_catalogue,
        )
        cat_entry, needs_restock = get_or_create_merchant_catalogue(
            merchant, faction_key, current_day, current_minute
        )
        if needs_restock:
            shop = await generate_faction_quartermaster_shop(faction, session)
            cat_entry = update_merchant_catalogue(merchant, faction_key, shop, current_day, current_minute)

        discount = 0 if is_anom else cat_entry.get("discount_pct", 0)
        merchant.update({
            "active": True,
            "active_store_key": faction_key,
            "stock": cat_entry["stock"],
            "discount_pct": discount,
            "is_faction_quartermaster": True,
            "quartermaster_faction_arch": fac_arch if is_anom else "",
            "restock_day": cat_entry.get("restock_day", current_day),
            "restock_minute": cat_entry.get("restock_minute", current_minute),
        })
        await adb(db.save_merchant_state, session_id, merchant)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return _serializable_action({
            "success": True,
            "action": "quartermaster",
            "merchant": merchant,
            "message": f"{faction.get('name', 'Faction')} Quartermaster requisition catalogue unlocked!",
            **payload,
        })

    if action == "bounty":
        from mechanics.social.factions import is_school_club_faction
        is_club = is_school_club_faction(faction)
        if is_anom and not is_club:
            from mechanics.social.factions import (
                ANOMALOUS_DISTRUSTED_ARCHETYPES,
                get_anomalous_faction_state,
                infer_anomalous_faction_archetype,
            )
            fac_arch = infer_anomalous_faction_archetype(faction)
            if fac_arch in ANOMALOUS_DISTRUSTED_ARCHETYPES:
                raise HTTPException(
                    status_code=400,
                    detail=f"{faction.get('name', 'This organization')} does not publish licensed containment contracts."
                )
            a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
            player_arch = str(a_st.get("faction_archetype_key") or "freelancer")
            if fac_arch != "public_agency" and player_arch != fac_arch:
                raise HTTPException(
                    status_code=403,
                    detail=f"Internal dispatch contracts for {faction.get('name', 'this faction')} are restricted to its enlisted operatives."
                )
        bounties = await game_engine.generate_faction_bounty_board(session, faction)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return _serializable_action({
            "success": True,
            "action": "bounty",
            "bounties": [dict(b) for b in (payload.get("available_bounties") or []) if b],
            "message": f"Generated {len(bounties or [])} faction contracts for {faction.get('name', 'Faction')}!",
            **payload,
        })

    if action in ("promote", "challenge_leader"):
        from mechanics.social.factions import is_school_club_faction
        is_club = is_school_club_faction(faction)
        if is_anom and not is_club:
            raise HTTPException(
                status_code=400,
                detail="In Anomalous Incursions, operatives cannot usurp the fixed leadership hierarchy. Advance from Tier 1 (Probationary Agent) to Tier 5 (Elite Agent) on the 5-Tier Promotion Meter (0-100 Rep) by completing Faction Bounties (+10 Rep) and Daily Mandatory Dispatches (+15 Rep)!"
            )
        if joined_fid != target_fid:
            raise HTTPException(
                status_code=400,
                detail="Join this faction first before challenging for promotion."
            )
        current_rank = int(char.get("faction_rank") or 1)
        eligible = get_eligible_rank(template, rep)
        if eligible <= current_rank:
            raise HTTPException(
                status_code=400,
                detail="You don't have enough reputation to challenge for the next rank yet."
            )

        target_rank = current_rank + 1
        new_title = get_rank_title(template, target_rank)
        roster = faction.get("leadership_roster") or []
        if not roster:
            roster = generate_leadership_roster(template, scen_key, faction.get("name", ""))
        incumbent_name = get_incumbent_at_rank(roster, target_rank)

        if not incumbent_name:
            new_roster = promote_player_in_roster(roster, char["name"], target_rank, template)
            await adb(db.update_faction_leadership_roster, session_id, faction["faction_id"], new_roster)
            await adb(db.set_character_faction_membership, char_id, faction["faction_id"], target_rank, new_title)
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            return _serializable_action({
                "success": True,
                "action": "promote",
                "auto_promoted": True,
                "target_rank": target_rank,
                "target_title": new_title,
                "message": f"Promoted to Rank {target_rank}: {new_title}!",
                **payload,
            })

        pending_promotion = {
            "faction_id": faction["faction_id"],
            "target_rank": target_rank,
            "player_name": char["name"],
            "template": template,
        }
        await adb(db.update_session, session_id, extra={"pending_promotion": pending_promotion})
        directive = get_promotion_trial_directive(
            current_rank, target_rank, incumbent_name, faction.get("name", "Faction"), template, scen_key
        )
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return {
            "success": True,
            "action": "promote",
            "auto_promoted": False,
            "incumbent_name": incumbent_name,
            "target_rank": target_rank,
            "target_title": new_title,
            "directive": directive,
            "action_prompt": f"Player initiates promotion trial:\n\n{directive}",
            "message": f"Promotion Trial triggered! You have challenged {incumbent_name} for the rank of {new_title}.",
            **payload,
        }

    if action == "calibrate":
        if not is_anom:
            raise HTTPException(
                status_code=400,
                detail="HQ Telemetry Calibration is exclusive to Anomalous Incursions scenarios.",
            )
        from mechanics.social.factions import (
            ANOMALOUS_DISTRUSTED_ARCHETYPES,
            get_anomalous_faction_state,
            infer_anomalous_faction_archetype,
        )
        from mechanics.combat.spells.awakened_kits import (
            ABILITY_MEDIUMS,
            ANOMALOUS_ATTRIBUTES,
            COMBAT_ARCHETYPES,
            normalize_anomalous_attribute,
        )
        from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells

        fac_arch = infer_anomalous_faction_archetype(faction)
        if fac_arch in ANOMALOUS_DISTRUSTED_ARCHETYPES:
            raise HTTPException(
                status_code=403,
                detail="Unlicensed clandestine/cult factions lack HQ Telemetry Calibration chambers.",
            )
        a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
        player_arch = str(a_st.get("faction_archetype_key") or "freelancer")
        eff_tier = max(int(a_st.get("promotion_tier") or 0), int(char.get("faction_rank") or 0))
        if player_arch == "freelancer" or (fac_arch and player_arch != fac_arch):
            raise HTTPException(
                status_code=403,
                detail="You must be an enlisted operative of this faction HQ to access Telemetry Calibration.",
            )
        if eff_tier < 4:
            raise HTTPException(
                status_code=403,
                detail="HQ Telemetry Calibration requires Tier 4 (Special Investigator) standing or higher.",
            )

        raw_attr = str(req.attribute or "").strip().lower()
        new_attr = normalize_anomalous_attribute(raw_attr, fallback="") if raw_attr else ""
        new_arch = str(req.combat_archetype or "").strip().lower()
        new_med = str(req.ability_medium or "").strip().lower()
        if new_attr not in ANOMALOUS_ATTRIBUTES or new_arch not in COMBAT_ARCHETYPES or new_med not in ABILITY_MEDIUMS:
            raise HTTPException(
                status_code=400,
                detail="Specify a valid Attribute (9), Combat Archetype (4), and Ability Medium (4) for calibration.",
            )

        arc_key = str(session.get("current_arc") or session.get("chapter_number") or session.get("act_number") or 1)
        cal_map = dict(session.get("telemetry_calibrations_used") or {})
        if int(cal_map.get(arc_key, 0) or 0) >= 1:
            raise HTTPException(
                status_code=400,
                detail="Telemetry Calibration has already been completed once during this campaign chapter/arc.",
            )

        cur_gold = int(char.get("gold", 0) or 0)
        if cur_gold < 500:
            raise HTTPException(
                status_code=400,
                detail=f"Telemetry Calibration requires 500G (you currently have {cur_gold}G).",
            )

        inv_items = await adb(db.get_inventory, req.user_id)
        core_item = next(
            (
                it for it in (inv_items or [])
                if not it.get("equipped")
                and any(
                    kw in str(it.get("name") or "").strip().lower()
                    for kw in ("hume core", "resonance core", "anomalous core")
                )
            ),
            None,
        )
        if not core_item:
            raise HTTPException(
                status_code=400,
                detail="Telemetry Calibration requires 1x Hume Core in your unequipped inventory.",
            )

        await adb(db.apply_hp_mp_delta, req.user_id, 0, 0, -500)
        await adb(db.remove_item, req.user_id, int(core_item["id"]))
        await adb(db.set_character_3axis, req.user_id, new_attr, new_arch, new_med)
        await adb(sync_equipped_anomalous_spells, req.user_id)

        cal_map[arc_key] = int(cal_map.get(arc_key, 0) or 0) + 1
        await adb(db.update_session, session_id, extra={"telemetry_calibrations_used": cal_map})
        learned_after = await adb(db.get_learned_spells, req.user_id)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return _serializable_action({
            "success": True,
            "action": "calibrate",
            "attribute": new_attr,
            "combat_archetype": new_arch,
            "ability_medium": new_med,
            "learned_spells": learned_after,
            "telemetry_calibrations_used": cal_map,
            "message": (
                f"HQ Telemetry Calibration complete! Re-attuned to "
                f"{new_attr.replace('_', ' ').title()} / {new_arch.replace('_', ' ').title()} / "
                f"{new_med.replace('_', ' ').title()} (-500G, -1 {core_item['name']})."
            ),
            **payload,
        })

    raise HTTPException(status_code=400, detail=f"Unsupported faction HQ action: {req.action}")


def _build_quests_payload(session_id: int, user_id: Optional[int] = None) -> dict:
    from mechanics.world.waypoints import ensure_quest_waypoints_exist, get_story_quest_climax_location
    try:
        ensure_quest_waypoints_exist(session_id)
    except Exception:
        pass
    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    eff_uid = user_id if user_id is not None else session.get("host_user_id")
    settings = (db.get_settings(eff_uid) or {}) if eff_uid else {}
    reveal_all = bool(int(settings.get("debug_reveal_all_info") or 0))

    quests = [dict(q) for q in db.get_session_quests(session_id) if q]
    from mechanics.world.locations.hierarchy import (
        resolve_session_location_tokens,
        clean_narrative_location_arrows,
        dedupe_location_stutter,
        format_clean_location_badge,
    )

    def _clean_quest_dict(q: dict) -> None:
        if q.get("title"):
            q["title"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, q["title"], scen_key))
        if q.get("objective"):
            q["objective"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, q["objective"], scen_key))
        if q.get("stage_label"):
            q["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, q["stage_label"], scen_key))
        if q.get("target_location"):
            q["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, q["target_location"], scen_key))
        if q.get("waypoints") and isinstance(q["waypoints"], list):
            for wp in q["waypoints"]:
                if isinstance(wp, dict):
                    if wp.get("stage_label"):
                        wp["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, wp["stage_label"], scen_key))
                    if wp.get("target_location"):
                        wp["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, wp["target_location"], scen_key))
        if q.get("sub_objectives"):
            for so in q["sub_objectives"]:
                if isinstance(so, dict):
                    if so.get("text"):
                        so["text"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, so["text"], scen_key))
                    if so.get("stage_label"):
                        so["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, so["stage_label"], scen_key))
                    if so.get("target_location"):
                        so["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, so["target_location"], scen_key))
                    if so.get("waypoints") and isinstance(so["waypoints"], list):
                        for wp in so["waypoints"]:
                            if isinstance(wp, dict):
                                if wp.get("stage_label"):
                                    wp["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, wp["stage_label"], scen_key))
                                if wp.get("target_location"):
                                    wp["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, wp["target_location"], scen_key))
        _saved_notes = q.get("quest_notes")
        _saved_anom_bp = q.get("anomaly_blueprint")
        _saved_anom_bp_json = q.get("anomaly_blueprint_json")
        _saved_dos = q.get("dossier")
        _redacted = game_engine.redact_quest_for_fog_of_war(session_id, q, reveal_all=reveal_all)
        q.clear()
        q.update(_redacted)
        q["fow_dossier"] = q.get("fow") or game_engine.build_fog_of_war_quest_payload(
            session_id,
            q,
            dossier=_saved_dos,
            reveal_all=reveal_all,
        )
        if reveal_all:
            if _saved_dos is not None:
                q["dossier"] = _saved_dos
            if _saved_notes is not None:
                q["quest_notes"] = _saved_notes
            if _saved_anom_bp is not None:
                q["anomaly_blueprint"] = _saved_anom_bp
            if _saved_anom_bp_json is not None:
                q["anomaly_blueprint_json"] = _saved_anom_bp_json
        else:
            q["quest_notes"] = ""
            q.pop("anomaly_blueprint_json", None)
        if isinstance(q.get("main_objective"), dict):
            mo = q["main_objective"]
            if mo.get("title"):
                mo["title"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, mo["title"], scen_key))
                mo["text"] = mo["title"]
            for ms in (mo.get("stages") or []):
                if isinstance(ms, dict):
                    if ms.get("stage_label"):
                        ms["stage_label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, ms["stage_label"], scen_key))
                        ms["text"] = ms["stage_label"]
                    if ms.get("target_location"):
                        ms["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, ms["target_location"], scen_key))
                    if ms.get("key_clue"):
                        if isinstance(ms["key_clue"], dict):
                            raw_kc = ms["key_clue"]
                            kc_t = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, str(raw_kc.get("title") or ""), scen_key))
                            kc_l = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, str(raw_kc.get("lead_text") or ""), scen_key))
                            ms["key_clue"] = f"{kc_t} — {kc_l}" if (kc_t and kc_l and kc_l.lower() != kc_t.lower()) else (kc_t or kc_l)
                            ms["key_clue_meta"] = {"title": kc_t, "lead_text": kc_l, "clue_id": str(raw_kc.get("clue_id") or "")}
                        else:
                            ms["key_clue"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, ms["key_clue"], scen_key))
                    if isinstance(ms.get("key_clue_meta"), dict):
                        if ms["key_clue_meta"].get("title"):
                            ms["key_clue_meta"]["title"] = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(ms["key_clue_meta"]["title"]), scen_key)
                            )
                        if ms["key_clue_meta"].get("lead_text"):
                            ms["key_clue_meta"]["lead_text"] = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(ms["key_clue_meta"]["lead_text"]), scen_key)
                            )
                    for src in (ms.get("clue_sources") or []):
                        if isinstance(src, dict):
                            if src.get("label"):
                                src["label"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, src["label"], scen_key))
                            if src.get("approach_hint"):
                                src["approach_hint"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, src["approach_hint"], scen_key))
                            if src.get("location") and src["location"] != "Hidden Lair":
                                resolved_src_loc = dedupe_location_stutter(resolve_session_location_tokens(session_id, src["location"], scen_key))
                                src["location"] = resolved_src_loc
                                src["location_display"] = format_clean_location_badge(resolved_src_loc, include_zone=True)
        for opt_o in (q.get("optional_objectives") or []):
            if isinstance(opt_o, dict):
                if opt_o.get("title"):
                    opt_o["title"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, opt_o["title"], scen_key))
                    opt_o["text"] = opt_o["title"]
                if opt_o.get("stakes_hint"):
                    opt_o["stakes_hint"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, opt_o["stakes_hint"], scen_key))
                if opt_o.get("target_location"):
                    opt_o["target_location"] = dedupe_location_stutter(resolve_session_location_tokens(session_id, opt_o["target_location"], scen_key))
        q_notes_raw = str(_saved_notes or q.get("quest_notes") or "")
        has_anom_bp = (
            "anomaly_bp:" in q_notes_raw
            or "anomaly_blueprint:" in q_notes_raw
            or bool(isinstance(_saved_anom_bp or q.get("anomaly_blueprint"), dict) and (_saved_anom_bp or q.get("anomaly_blueprint")))
            or str(_saved_anom_bp_json or q.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
        )
        if has_anom_bp:
            try:
                from mechanics.world.anomaly_engine import (
                    parse_blueprint_from_notes,
                    format_anomaly_dossier_summary,
                )
                from mechanics.world.folklore_mechanics import get_public_anomaly_name, is_blueprint_disguised
                parse_probe = dict(q)
                if _saved_notes is not None:
                    parse_probe["quest_notes"] = _saved_notes
                if _saved_anom_bp is not None:
                    parse_probe["anomaly_blueprint"] = _saved_anom_bp
                if _saved_anom_bp_json is not None:
                    parse_probe["anomaly_blueprint_json"] = _saved_anom_bp_json
                bp_q = parse_blueprint_from_notes(parse_probe)
                if bp_q:
                    is_rev = bool(reveal_all or "dossier_revealed:1" in q_notes_raw or bp_q.get("dossier_revealed"))
                    q["anomaly_dossier_revealed"] = is_rev
                    q["anomaly_dossier"] = format_anomaly_dossier_summary(bp_q, revealed=is_rev)
                    if is_rev:
                        q["anomaly_blueprint"] = bp_q
                    else:
                        q_disg = is_blueprint_disguised(bp_q, dossier_revealed=False)
                        q["anomaly_blueprint"] = {
                            "name": get_public_anomaly_name(bp_q, dossier_revealed=False, fallback="Unknown Anomaly"),
                            "type": "unknown" if q_disg else bp_q.get("type"),
                            "form": "" if q_disg else bp_q.get("form"),
                            "physicality": "unknown",
                            "disposition": bp_q.get("disposition"),
                            "sapience": "unknown",
                            "element": "unknown",
                            "is_disguised": q_disg,
                            "dossier_revealed": False,
                        }
            except Exception:
                pass

    for q in quests:
        _clean_quest_dict(q)
    active_sq = db.get_active_story_quest(session_id)
    if active_sq:
        active_sq = dict(active_sq)
        _clean_quest_dict(active_sq)
    if active_sq and active_sq.get("climax_ready"):
        try:
            sq_dos = db.get_quest_dossier(session_id, active_sq.get("quest_id", ""))
            climax_spec_sq = (sq_dos or {}).get("climax_spec") or {}
            is_climax_unlocked = bool(reveal_all or (str(climax_spec_sq.get("gate_type") or climax_spec_sq.get("gate_mode") or "").lower() == "open") or climax_spec_sq.get("is_unlocked"))
            _, climax_loc = get_story_quest_climax_location(session_id)
            if climax_loc and is_climax_unlocked:
                clean_climax = dedupe_location_stutter(climax_loc.replace(" -> ", " ➔ "))
                active_sq["climax_location"] = clean_climax
                active_sq["target_location"] = clean_climax
        except Exception:
            pass
    clues = [dict(c) for c in db.get_session_clues(session_id) if c]
    if clues:
        cg_by_clue_id: dict[int, dict] = {}
        cg_by_title: dict[str, dict] = {}
        for _dos_c in (db.get_session_quest_dossiers(session_id) or []):
            _d_qid = str(_dos_c.get("quest_id") or "").strip()
            for _cn in (_dos_c.get("clue_graph") or []):
                if not isinstance(_cn, dict):
                    continue
                _node_meta = {
                    "clue_tier": "corroborating"
                    if (bool(_cn.get("is_red_herring")) or str(_cn.get("clue_tier") or "").strip().lower() == "red_herring")
                    else (
                        str(_cn.get("clue_tier") or "").strip().lower()
                        if str(_cn.get("clue_tier") or "").strip().lower() in ("key_clue", "corroborating")
                        else "corroborating"
                    ),
                    "corroboration_group": str(_cn.get("corroboration_group") or _cn.get("quest_id") or _d_qid).strip(),
                }
                _raw_cid = _cn.get("clue_id")
                try:
                    if _raw_cid is not None and not isinstance(_raw_cid, bool):
                        cg_by_clue_id[int(_raw_cid)] = _node_meta
                except (TypeError, ValueError):
                    pass
                _n_title = str(_cn.get("title") or "").strip().lower()
                if _n_title:
                    cg_by_title.setdefault(f"{_d_qid}::{_n_title}", _node_meta)
                    cg_by_title.setdefault(f"::{_n_title}", _node_meta)
        for c in clues:
            try:
                _cid_int = int(c["id"]) if c.get("id") is not None else None
            except (TypeError, ValueError):
                _cid_int = None
            _c_qid = str(c.get("quest_id") or "").strip()
            _c_title = str(c.get("title") or "").strip().lower()
            _meta = (
                (cg_by_clue_id.get(_cid_int) if _cid_int is not None else None)
                or cg_by_title.get(f"{_c_qid}::{_c_title}")
                or cg_by_title.get(f"::{_c_title}")
            )
            if _meta:
                c["clue_tier"] = _meta["clue_tier"]
                if _meta["corroboration_group"]:
                    c["corroboration_group"] = _meta["corroboration_group"]
            elif c.get("clue_tier") == "red_herring":
                c["clue_tier"] = "corroborating"
    available_bounties = [q for q in quests if q.get("status") == "Available"]
    import scenario_data as _sd_qp
    if _sd_qp.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility, parse_anomalous_quest_board_source
            from mechanics.social.factions import get_anomalous_faction_state
            target_uid = user_id or (session.get("host_user_id") if session else None)
            fac_st = get_anomalous_faction_state(session_id, user_id=target_uid)
            for bq in available_bounties:
                elig = evaluate_anomalous_bounty_eligibility(session_id, target_uid, bq, session=session, fac_state=fac_st)
                bq["board_source"] = elig.get("board_source") or parse_anomalous_quest_board_source(bq, session_id=session_id)
                bq["anomalous_eligible"] = bool(elig.get("allowed", True))
                bq["anomalous_lock_reason"] = str(elig.get("reason") or "")
        except Exception:
            pass
    nb_label, nb_emoji = get_notice_board_label(scen_key)
    current_chapter = db.get_session_chapter(session_id) or 1
    campaign_end_goals = session.get("campaign_end_goals") or db.get_session_campaign_goals(session_id) or []
    chapter_digest = db.get_chapter_digest(session_id) or []

    spine = db.get_campaign_spine(session_id)
    world_scars = [
        {
            "event_key": e.get("event_key"),
            "title": e.get("title"),
            "location_name": e.get("location_name"),
            "description": e.get("description"),
            "remediation_quest_id": (e.get("metadata") or {}).get("remediation_quest_id") if isinstance(e.get("metadata"), dict) else None,
            "scar_tier": ((e.get("metadata") or {}).get("scar_tier") or "bounty") if isinstance(e.get("metadata"), dict) else "bounty",
            "remediation_type": (e.get("metadata") or {}).get("remediation_type") if isinstance(e.get("metadata"), dict) else None,
        }
        for e in (db.get_world_events(session_id, statuses=("active",)) or [])
        if (
            str(e.get("event_type") or "") == "world_scar"
            or (isinstance(e.get("metadata"), dict) and e["metadata"].get("is_world_scar"))
            or str(e.get("template_key") or "").startswith("world_scar_")
            or str(e.get("event_key") or "").startswith("scar_")
        )
    ]
    campaign_spine_summary = {
        "max_chapters": 11,
        "has_spine": spine is not None,
        "climax_status": (spine or {}).get("climax_status") or "pending",
        "epilogue_status": (spine or {}).get("epilogue_status") or "pending",
        "nemeses_count": len((spine or {}).get("nemeses") or []),
        "world_scars": world_scars,
        "campaign_game_over": bool(session.get("campaign_game_over")),
        "fallen_world": bool(session.get("fallen_world")),
        "epilogue_ready": bool(session.get("epilogue_ready")),
        "epilogue_choices": list(session.get("epilogue_choices") or []),
        "endless_mode_unlocked": bool(session.get("endless_mode_unlocked")),
        "campaign_archived": bool(session.get("campaign_archived") or session.get("chronicle_archived")),
        "is_peak_chapter": int(current_chapter) in (3, 6, 8, 9, 10),
        "chronicle_tapestry": (spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {},
        "ending_archetype": ((spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {}).get("ending_archetype") or ((spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {}).get("ending_id") or "",
    }

    # Machine tokens in quest_notes / anomaly_blueprint_json are server-only:
    # redact them after eligibility parsing so disguised folklore identities never reach clients.
    if not reveal_all:
        for q_red in list(quests) + ([active_sq] if isinstance(active_sq, dict) else []):
            if isinstance(q_red, dict):
                has_raw_anom = (
                    "anomaly_bp:" in str(q_red.get("quest_notes") or "")
                    or "anomaly_blueprint:" in str(q_red.get("quest_notes") or "")
                    or str(q_red.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
                )
                if has_raw_anom:
                    q_red["quest_notes"] = ""
                q_red.pop("anomaly_blueprint_json", None)

    return {
        "quests": quests,
        "available_bounties": available_bounties,
        "active_story_quest": active_sq,
        "clues": clues,
        "has_bounty_board": location_has_bounty_board(current_loc, scen_key=scen_key),
        "notice_board_label": nb_label,
        "notice_board_emoji": nb_emoji,
        "current_chapter": current_chapter,
        "max_chapters": 11,
        "campaign_end_goals": campaign_end_goals,
        "chapter_digest": chapter_digest,
        "campaign_spine": campaign_spine_summary,
        "debug_reveal_all": reveal_all,
    }


@router.get("/api/quests/{session_id}")
async def get_quests(session_id: int, user_id: Optional[int] = Query(None), request: Request = None):
    """Fetches active, available, and completed quests, active story quest, Fog-of-War dossiers, and Caseboard clues."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    res = await adb(_build_quests_payload, session_id, user_id)
    return _serializable_action(res)


@router.post("/api/quests/{session_id}/bounties/generate")
async def generate_session_bounties(session_id: int, req: BountyGenerateRequest, request: Request = None):
    """Generates or refreshes the Bounty Board contracts for the session."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    async with distributed_session_lock(session_id):
        if req.faction_id:
            factions = await adb(db.get_factions, session_id)
            target_f = next((f for f in (factions or []) if f.get("faction_id") == req.faction_id), None)
            if target_f:
                bounties = await game_engine.generate_faction_bounty_board(session, target_f, force_refresh=req.force_refresh)
            else:
                bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)
        else:
            bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)

    payload = await adb(_build_quests_payload, session_id, req.user_id)
    resp_bounties = bounties if req.faction_id and bounties else (payload.get("available_bounties") or [])
    return _serializable_action({
        "success": True,
        "bounties": [dict(b) for b in resp_bounties if b],
        **payload,
    })


@router.post("/api/quests/{session_id}/bounties/action")
async def bounty_contract_action(session_id: int, req: BountyActionRequest, request: Request = None):
    """Accepts an available bounty (compiling Stage-2 QuestDossier + optional CHA advance) or abandons/forfeits an active bounty."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)
    quest = await adb(db.get_quest_by_id, session_id, req.quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Bounty contract not found")
    scen_key = str(session.get("scenario") or "fantasy")
    action = (req.action or "accept").strip().lower()

    import scenario_data
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        notes = str(quest.get("quest_notes") or "")
        if action == "accept":
            from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility
            elig = await adb(evaluate_anomalous_bounty_eligibility, session_id, req.user_id, quest)
            if not elig.get("allowed", True):
                raise HTTPException(status_code=400, detail=elig.get("reason") or "Faction rules prohibit accepting this bounty.")
        elif action == "abandon":
            if "mandatory_daily:1" in notes or str(quest.get("quest_id") or "").upper().startswith("MAND-"):
                raise HTTPException(
                    status_code=400,
                    detail="Mandatory Daily Dispatches cannot be abandoned! Complete it before 24:00 to avoid a -15 Reputation penalty."
                )

    advance_result = None
    forfeit_details = None
    if action == "accept":
        # accept_bounty_contract_async manages its own distributed_session_lock internally
        acc_res = await game_engine.accept_bounty_contract_async(
            session_id=session_id,
            quest_id=req.quest_id,
            user_id=req.user_id,
            haggle_advance=bool(req.haggle_advance),
            enrich_llm=False,
        )
        if not acc_res.get("success"):
            raise HTTPException(
                status_code=int(acc_res.get("status_code") or 400),
                detail=acc_res.get("reason") or "Cannot accept this contract.",
            )
        new_status = "Active"
        advance_result = acc_res.get("advance_result")
        adv_note = (
            f" (+{advance_result['advance_gold']}G upfront advance secured!)"
            if isinstance(advance_result, dict) and advance_result.get("succeeded")
            else ""
        )
        msg = f"Accepted contract: {quest.get('title', 'Bounty')}!{adv_note}"
    elif action == "abandon":
        async with distributed_session_lock(session_id):
            forfeit_res = await adb(
                game_engine.forfeit_side_bounty,
                session_id,
                req.quest_id,
                [req.user_id] if req.user_id is not None else None,
                req.user_id,
            )
            if not forfeit_res.get("success"):
                raise HTTPException(
                    status_code=int(forfeit_res.get("status_code") or 400),
                    detail=forfeit_res.get("reason") or "Cannot abandon this contract.",
                )
            new_status = str(forfeit_res.get("status") or "Abandoned")
            forfeit_details = _serializable_action(forfeit_res)
            if new_status == "Failed":
                msg = f"Forfeited engaged contract '{quest.get('title', 'Bounty')}' — marked Failed with regional fallout!"
            else:
                msg = f"Abandoned contract: {quest.get('title', 'Bounty')}."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid bounty action: {req.action}")

    payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({
        "success": True,
        "quest_id": req.quest_id,
        "status": new_status,
        "message": msg,
        "advance_result": advance_result,
        "forfeit_details": forfeit_details,
        **payload,
    })


@router.post("/api/quests/{session_id}/clues/deduce")
async def deduce_caseboard_clues(session_id: int, req: ClueDeductionRequest, request: Request = None):
    """Deterministically cross-references two evidence clues via QuestDossier clue_graph / Logic Caseboard (zero RNG!)."""
    await verify_session_participant(request, session_id, req.user_id)
    is_single = req.clue_b_id is None or int(req.clue_a_id) == int(req.clue_b_id)

    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        clue_a = await adb(db.get_session_clue_by_id, req.clue_a_id)
        if not clue_a:
            raise HTTPException(status_code=404, detail="Selected evidence record could not be found.")
        if clue_a.get("is_consumed"):
            raise HTTPException(status_code=400, detail="The selected lead has already been consumed.")

        if is_single:
            pair_key = f"single:{int(req.clue_a_id)}"
            eff_clue_b_id = None
        else:
            clue_b = await adb(db.get_session_clue_by_id, req.clue_b_id)
            if not clue_b:
                raise HTTPException(status_code=404, detail="Secondary evidence record could not be found.")
            if clue_b.get("is_consumed"):
                raise HTTPException(status_code=400, detail="Secondary lead has already been consumed.")
            pair_key = f"{min(int(req.clue_a_id), int(req.clue_b_id))}:{max(int(req.clue_a_id), int(req.clue_b_id))}"
            eff_clue_b_id = req.clue_b_id

        cur_turn = int(db.infer_session_turn(session))
        attempts_map = dict(session.get("deduction_attempts_turn") or {})
        if attempts_map.get(pair_key) == cur_turn:
            raise HTTPException(
                status_code=400,
                detail="You already attempted to connect this lead or pair this turn. Advance the story or try another lead!",
            )

        ded_res = await adb(game_engine.resolve_caseboard_deduction, session_id, req.clue_a_id, eff_clue_b_id, req.user_id)
        attempts_map[pair_key] = cur_turn
        await adb(db.update_session, session_id, extra={"deduction_attempts_turn": attempts_map})

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({
        "success": True,
        "is_valid": bool(ded_res.get("is_valid")),
        "is_red_herring": bool(ded_res.get("is_red_herring")),
        "partial_corroboration": bool(ded_res.get("partial_corroboration")),
        "shortcut_unlocked": bool(ded_res.get("shortcut_unlocked")),
        "threat_clock_paused": bool(ded_res.get("threat_clock_paused")),
        "title": ded_res.get("title") or "",
        "detail_text": ded_res.get("detail_text") or "",
        "xp_awarded": int(ded_res.get("xp_awarded") or 0),
        "climax_unlocked": bool(ded_res.get("climax_unlocked")),
        "twist_revealed": bool(ded_res.get("twist_revealed")),
        **payload,
    })


@router.post("/api/quests/{session_id}/caseboard/accuse")
async def accuse_caseboard_suspect(session_id: int, req: SuspectAccusationRequest, request: Request = None):
    """Resolves a Private Confrontation vs. Formal Public Accusation against a Caseboard suspect."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_suspect_accusation,
            session_id,
            req.quest_id,
            req.suspect_name,
            req.mode,
            req.user_id,
        )
        if not res.get("success"):
            raise HTTPException(
                status_code=int(res.get("status_code") or 400),
                detail=res.get("reason") or "Could not resolve suspect accusation.",
            )

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({**res, **payload})


@router.post("/api/quests/{session_id}/turn-in")
async def resolve_contract_turn_in(session_id: int, req: QuestTurnInRequest, request: Request = None):
    """Resolves Contract Turn-In, Side-Switching, `2x` Twist Blackmail, or Tangible MacGuffin Keep/Destroy/Fence."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_quest_turn_in_or_betrayal,
            session_id,
            req.quest_id,
            req.user_id,
            req.disposition,
            None,
            str(session.get("current_location") or ""),
        )
        if not res.get("success"):
            raise HTTPException(
                status_code=int(res.get("status_code") or 400),
                detail=res.get("reason") or "Could not resolve contract turn-in.",
            )

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({**res, **payload})


@router.post("/api/quests/{session_id}/epilogue")
async def resolve_campaign_epilogue_choice(session_id: int, req: EpilogueChoiceRequest, request: Request = None):
    """Resolves Chapter 11 Universal Epilogue choice: 'archive' vs 'endless'."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_epilogue_choice,
            session_id,
            req.choice_id,
            [req.user_id] if req.user_id is not None else None,
        )
        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({"success": True, **res, **payload})


@router.get("/api/phone/{session_id}")
async def get_phone_state(session_id: int, user_id: int = Query(...), request: Request = None):
    """Fetches smartphone OS state: scenario branding, appointments, gossip feed, contacts, social state, and digital media gallery."""
    session, _ = await verify_session_participant(request, session_id, user_id)

    scen_key = session.get("scenario", "fantasy")
    inv = await adb(db.get_inventory, user_id)
    is_supported = True

    branding = get_phone_branding(scen_key)
    pending_appts = await adb(db.get_phone_appointments, session_id, status="pending")
    arrived_appts = await adb(db.get_phone_appointments, session_id, status="arrived")
    appointments = (pending_appts or []) + (arrived_appts or [])
    gossip = await adb(db.get_gossip_feed, session_id, limit=15)
    import scenario_data as _sd_phone
    if _sd_phone.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents
        await adb(prune_unmet_preseeded_special_agents, session_id)
    char_row = await adb(db.get_character, user_id)
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    if not contacts and char_id != user_id:
        contacts = await adb(db.get_contacts, session_id, user_id)
    social_state = await adb(get_social_state_summary, session_id, session)

    digital_media = []
    for it in inv:
        if is_digital_item(it):
            meta = parse_digital_item_metadata(it) or {}
            digital_media.append({
                "id": it.get("id"),
                "name": it.get("name"),
                "contact_name": meta.get("contact_name") or "Subject",
                "media_type": meta.get("media_type") or "photo",
                "caption": meta.get("caption") or it.get("effect") or "",
                "timestamp": meta.get("timestamp"),
                "tags": meta.get("tags") or []
            })

    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    from mechanics.social.relationships import collect_met_npc_names, is_contact_blocked, is_unlocked_contact
    met_names = collect_met_npc_names(session, party_npcs=party_npcs)
    unlocked_contacts = []
    for c in contacts:
        if is_unlocked_contact(c, party_names, met_in_story_names=met_names):
            uc_copy = dict(c)
            uc_copy["is_blocked_contact"] = is_contact_blocked(uc_copy)
            if not uc_copy.get("debug_revealed"):
                if "_phone_fow_ctx" not in locals():
                    _ph_uid = locals().get("user_id") or (getattr(locals().get("req"), "user_id", 0) if "req" in locals() else 0)
                    _ph_set = await adb(db.get_settings, _ph_uid) if _ph_uid else {}
                    _ph_dbg = bool((_ph_set or {}).get("debug_reveal_all_info", 0))
                    _ph_cid = int(locals().get("char_id") or ((await adb(db.get_character, _ph_uid)) or {}).get("id", 0) if _ph_uid else 0)
                    _phone_fow_ctx = None if _ph_dbg else await adb(_preload_fog_of_war_context, session_id, _ph_cid, party_names, str((_ph_set or {}).get("ui_language") or "en"))
                if isinstance(_phone_fow_ctx, dict):
                    from mechanics.social.consequences import apply_fog_of_war_to_enriched_contact as _apply_ph_fow
                    _cn_ph = db.canon_social_npc_id(uc_copy.get("npc_id") or uc_copy.get("name") or "")
                    uc_copy = _apply_ph_fow(
                        uc_copy,
                        session_id=session_id,
                        character_id=_phone_fow_ctx.get("character_id", 0),
                        preloaded_discoveries=(_phone_fow_ctx.get("disc_by_npc") or {}).get(_cn_ph, []),
                        lang=_phone_fow_ctx.get("lang", "en"),
                        party_npc_keys=_phone_fow_ctx.get("party_npc_keys"),
                        kin_npc_keys=_phone_fow_ctx.get("kin_npc_keys"),
                        romantic_npc_keys=_phone_fow_ctx.get("romantic_npc_keys"),
                    )
            unlocked_contacts.append(uc_copy)

    synthetic_channels = []
    if _sd_phone.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.social.factions import get_anomalous_faction_state
            a_st = await adb(get_anomalous_faction_state, session_id, user_id)
            dispatch_defs = [
                ("metropolitan_anomaly_watch", "Metropolitan Anomaly Watch", "Citywide Anomaly Broadcast"),
            ]
            if a_st.get("faction_archetype_key", "freelancer") != "freelancer" and a_st.get("joined_faction_name"):
                f_disp = f"{a_st['joined_faction_name']} Dispatch"
                dispatch_defs.insert(0, (f_disp.strip().lower().replace(" ", "_"), f_disp, "Mandatory Daily Dispatch"))
            for ch_id, ch_name, ch_role in dispatch_defs:
                msgs = await adb(db.get_phone_messages, session_id, ch_id, 1)
                if msgs:
                    synthetic_channels.append({
                        "npc_id": ch_id,
                        "name": ch_name,
                        "role": ch_role,
                        "is_dispatch_channel": True,
                        "read_only": True,
                    })
            from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
            for uc in unlocked_contacts:
                if isinstance(uc, dict) and not uc.get("is_dispatch_channel"):
                    t_uc = classify_anomalous_npc_tag(uc, session_id=session_id, scen_key=scen_key)
                    uc["anomalous_npc_tag"] = t_uc
                    uc["anomalous_tag_label"] = "Special Agent" if t_uc == "special_agent" else "Civilian"
                    if (uc.get("basic_info") or {}).get("deceased"):
                        uc["deceased"] = True
        except Exception:
            pass
    suggested_peers = await adb(get_suggested_peers, session_id, user_id)
    if _sd_phone.is_anomalous_incursions_scenario(scen_key) and isinstance(suggested_peers, list):
        try:
            from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
            for sp_p in suggested_peers:
                if isinstance(sp_p, dict):
                    t_sp = classify_anomalous_npc_tag(sp_p, session_id=session_id, scen_key=scen_key)
                    sp_p["anomalous_npc_tag"] = t_sp
                    sp_p["anomalous_tag_label"] = "Special Agent" if t_sp == "special_agent" else "Civilian"
        except Exception:
            pass
    active_commitments = await adb(db.get_active_commitments, session_id)
    enriched_commitments = _enrich_commitments_for_ui(session_id, active_commitments, contacts)
    enriched_appointments = _enrich_commitments_for_ui(session_id, appointments, contacts)

    return {
        "is_supported": is_supported,
        "scenario": scen_key,
        "branding": {
            "device_name": branding.get("device_name", "📱 Smartphone") if branding else "📱 Smartphone",
            "os_name": branding.get("os_name", "Mobile OS") if branding else "Mobile OS",
            "feed_app_name": branding.get("feed_app_name", "Feed") if branding else "Feed",
            "dm_app_name": branding.get("dm_app_name", "Messages") if branding else "Messages",
            "gallery_app_name": branding.get("gallery_app_name", "Photos") if branding else "Photos",
            "bounty_app_name": branding.get("bounty_app_name", "Campus Requests") if branding else "Campus Requests",
            "bounty_subtitle": branding.get("bounty_subtitle", "Student Bulletin") if branding else "Student Bulletin",
            "shop_app_name": branding.get("shop_app_name", "E-Shop") if branding else "E-Shop",
            "emoji": branding.get("emoji", "📱") if branding else "📱",
        } if branding else None,
        "appointments": enriched_appointments,
        "commitments": enriched_commitments,
        "gossip_feed": [dict(g) for g in gossip],
        "media_gallery": digital_media,
        "contacts": unlocked_contacts,
        "dispatch_channels": synthetic_channels,
        "suggested_peers": suggested_peers,
        "social_state": social_state,
    }


@router.post("/api/phone/{session_id}/feed/refresh")
async def refresh_phone_feed(session_id: int, req: PhoneFeedActionRequest, request: Request = None):
    """Generates fresh in-universe social media timeline posts."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    posts = await generate_gossip_feed_posts(dict(session), force_refresh=bool(req.force_refresh))
    gossip = await adb(db.get_gossip_feed, session_id, limit=15)
    social_state = await adb(get_social_state_summary, session_id, session)
    return {
        "success": True,
        "posts": posts,
        "gossip_feed": [dict(g) for g in gossip],
        "social_state": social_state,
    }


@router.post("/api/phone/{session_id}/feed/scour")
async def scour_phone_feed(session_id: int, req: PhoneFeedActionRequest, request: Request = None):
    """Consumes 1 rumor charge (max 3) to roll a PER/INT check for a verified story clue."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    async with distributed_session_lock(session_id):
        res = await scour_feed_for_rumor(dict(session), req.user_id)
    social_state = await adb(get_social_state_summary, session_id, session)
    gossip = res.get("gossip_feed")
    if not gossip:
        gossip = [dict(g) for g in (await adb(db.get_gossip_feed, session_id, limit=20))]
    resp = {
        **res,
        "gossip_feed": [dict(g) for g in gossip],
        "social_state": social_state,
    }
    if res.get("discovered_rumor"):
        world_pulse = res.get("world_pulse") or await adb(build_client_world_pulse_payload, session_id)
        resp["world_pulse"] = world_pulse
        await manager.broadcast(
            session_id,
            {
                "type": "WORLD_PULSE_SYNC",
                "session_id": int(session_id),
                "world_pulse": world_pulse,
                "sync_timestamp": time.time(),
            },
        )
    return resp


@router.post("/api/phone/{session_id}/peerpulse/discover")
async def discover_peerpulse_profile(session_id: int, req: PeerPulseDiscoverRequest, request: Request = None):
    """Looks up a specific peer profile by name/handle or discovers a suggested uncontacted peer."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    query = (req.query_name or "").strip()
    if query:
        profile = await adb(lookup_social_profile, session_id, req.user_id, query)
    else:
        profile = await adb(discover_suggested_peer, session_id, req.user_id)

    if not profile:
        raise HTTPException(status_code=404, detail=f"No PeerPulse profile found matching '{query}'.")

    import scenario_data as _sd_disc
    scen_disc = session.get("scenario", "")
    if isinstance(profile, dict) and _sd_disc.is_anomalous_incursions_scenario(scen_disc):
        try:
            from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
            t_p = classify_anomalous_npc_tag(profile, session_id=session_id, scen_key=scen_disc)
            profile = dict(profile)
            profile["anomalous_npc_tag"] = t_p
            profile["anomalous_tag_label"] = "Special Agent" if t_p == "special_agent" else "Civilian"
        except Exception:
            pass

    return {
        "success": True,
        "profile": profile,
    }


@router.post("/api/phone/{session_id}/peerpulse/friend-request")
async def send_peerpulse_friend_request(session_id: int, req: PeerPulseFriendRequest, request: Request = None):
    """Resolves a PeerPulse friend request using CHA + mutual friend / shared club / sibling bonuses."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    res = await adb(resolve_social_friend_request, dict(session), req.user_id, dict(req.profile))
    char_row = await adb(db.get_character, req.user_id)
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    from mechanics.social.relationships import collect_met_npc_names, is_contact_blocked, is_unlocked_contact
    met_names = collect_met_npc_names(session, party_npcs=party_npcs)
    unlocked_contacts = []
    for c in contacts:
        if is_unlocked_contact(c, party_names, met_in_story_names=met_names):
            uc_copy = dict(c)
            uc_copy["is_blocked_contact"] = is_contact_blocked(uc_copy)
            if not uc_copy.get("debug_revealed"):
                if "_phone_fow_ctx" not in locals():
                    _ph_uid = locals().get("user_id") or (getattr(locals().get("req"), "user_id", 0) if "req" in locals() else 0)
                    _ph_set = await adb(db.get_settings, _ph_uid) if _ph_uid else {}
                    _ph_dbg = bool((_ph_set or {}).get("debug_reveal_all_info", 0))
                    _ph_cid = int(locals().get("char_id") or ((await adb(db.get_character, _ph_uid)) or {}).get("id", 0) if _ph_uid else 0)
                    _phone_fow_ctx = None if _ph_dbg else await adb(_preload_fog_of_war_context, session_id, _ph_cid, party_names, str((_ph_set or {}).get("ui_language") or "en"))
                if isinstance(_phone_fow_ctx, dict):
                    from mechanics.social.consequences import apply_fog_of_war_to_enriched_contact as _apply_ph_fow
                    _cn_ph = db.canon_social_npc_id(uc_copy.get("npc_id") or uc_copy.get("name") or "")
                    uc_copy = _apply_ph_fow(
                        uc_copy,
                        session_id=session_id,
                        character_id=_phone_fow_ctx.get("character_id", 0),
                        preloaded_discoveries=(_phone_fow_ctx.get("disc_by_npc") or {}).get(_cn_ph, []),
                        lang=_phone_fow_ctx.get("lang", "en"),
                        party_npc_keys=_phone_fow_ctx.get("party_npc_keys"),
                        kin_npc_keys=_phone_fow_ctx.get("kin_npc_keys"),
                        romantic_npc_keys=_phone_fow_ctx.get("romantic_npc_keys"),
                    )
            unlocked_contacts.append(uc_copy)
    return {
        "success": True,
        **res,
        "profile": req.profile,
        "contacts": unlocked_contacts,
    }


@router.get("/api/phone/{session_id}/peerpulse/suggestions")
async def get_peerpulse_suggestions(session_id: int, user_id: int = Query(...), request: Request = None):
    """Fetches suggested student peers for PeerPulse Graph."""
    session, _ = await verify_session_participant(request, session_id, user_id)
    suggestions = await adb(get_suggested_peers, session_id, user_id)
    import scenario_data as _sd_sugg
    scen_sugg = session.get("scenario", "")
    if _sd_sugg.is_anomalous_incursions_scenario(scen_sugg):
        try:
            from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
            for sp_p in (suggestions or []):
                if isinstance(sp_p, dict):
                    t_sp = classify_anomalous_npc_tag(sp_p, session_id=session_id, scen_key=scen_sugg)
                    sp_p["anomalous_npc_tag"] = t_sp
                    sp_p["anomalous_tag_label"] = "Special Agent" if t_sp == "special_agent" else "Civilian"
        except Exception:
            pass
    return {
        "success": True,
        "suggested_peers": suggestions,
    }


@router.get("/api/phone/{session_id}/messages/{npc_id}")
async def get_npc_messages(session_id: int, npc_id: str, user_id: Optional[int] = Query(None), request: Request = None):
    """Fetches direct message chat history with a specific NPC contact."""
    await verify_session_participant(request, session_id, user_id)
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    messages = await adb(db.get_phone_messages, session_id, clean_npc_id, limit=20)
    current_day, _, _ = await adb(db.get_session_time, session_id)
    daily_limits = await adb(db.get_phone_daily_limits, session_id, clean_npc_id, current_day)
    return {
        "messages": [dict(m) for m in messages],
        "daily_limits": daily_limits,
    }


@router.post("/api/phone/{session_id}/messages/{npc_id}")
async def send_npc_message(session_id: int, npc_id: str, req: PhoneMessageRequest, request: Request = None):
    """Sends a text message to an NPC contact and generates an immediate contextual reply."""
    _, eff_uid = await verify_session_participant(request, session_id, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)
    text = (req.message or "").strip()
    if (not text or text == "__auto__") and not req.intent:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    norm_target_id = str(npc_id or "").strip().lower().replace(" ", "_")
    if norm_target_id == "metropolitan_anomaly_watch" or norm_target_id.endswith("_dispatch"):
        raise HTTPException(
            status_code=400,
            detail="Automated dispatch channels are read-only broadcast feeds and do not accept replies."
        )

    async with distributed_adventure_lock(canonical_id, session_id):
        session_row = await adb(db.get_session, session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        session = dict(session_row)

        char_row = await adb(db.get_character, canonical_id, session_id=session_id)
        if not char_row:
            raise HTTPException(status_code=404, detail="Character not found")
        player_char = dict(char_row)

        contact = await adb(db.get_contact, session_id, npc_id, character_id=player_char.get("id", 0))
        if not contact:
            # Try matching against all contacts in session
            all_contacts = await adb(db.get_contacts, session_id, canonical_id)
            for c in all_contacts:
                if c.get("npc_id") == npc_id or c.get("name", "").lower().replace(" ", "_") == npc_id.lower():
                    contact = dict(c)
                    break
        if not contact:
            contact = {
                "npc_id": npc_id,
                "name": npc_id.replace("_", " ").title(),
                "relationship_score": 0,
                "track": "platonic",
                "basic_info": {}
            }

        from mechanics.social.relationships import is_contact_blocked, is_contact_eligible
        scen_key = str(session.get("scenario") or "")
        if not is_contact_eligible(contact, scenario=scen_key, session_id=session_id):
            raise HTTPException(
                status_code=403,
                detail=f"{contact.get('name', 'This entity')} is not eligible as a personal phone contact in this scenario."
            )
        if isinstance(contact, dict) and (
            contact.get("is_dispatch_channel")
            or (isinstance(contact.get("basic_info"), dict) and contact["basic_info"].get("is_dispatch_channel"))
        ):
            raise HTTPException(
                status_code=400,
                detail="Automated dispatch channels are read-only broadcast feeds and do not accept replies."
            )
        if is_contact_blocked(contact):
            raise HTTPException(
                status_code=400,
                detail=f"{contact.get('name', 'This contact')} has blocked your number due to hostility. Reconcile with them in person first."
            )

        if isinstance(contact, dict) and (
            contact.get("deceased")
            or (isinstance(contact.get("basic_info"), dict) and contact["basic_info"].get("deceased"))
        ):
            raise HTTPException(
                status_code=400,
                detail=f"{contact.get('name', 'This contact')}'s line is disconnected — they perished during an anomaly breach."
            )

        if not text or text == "__auto__":
            text = await generate_player_chat_message(session, dict(contact), player_char, req.intent)
            if not text:
                raise HTTPException(status_code=400, detail="Message cannot be empty")

        intent = req.intent or detect_custom_message_intent(text)
        reply_data = await generate_contact_dm_reply(
            session=session,
            contact=dict(contact),
            player_char=player_char,
            user_message=text,
            intent=intent
        )

        messages = await adb(db.get_phone_messages, session_id, contact.get("npc_id", npc_id), limit=20)
        return {
            "success": True,
            "generated_message": text,
            "reply": reply_data,
            "messages": [dict(m) for m in messages],
            "daily_limits": reply_data.get("daily_limits"),
        }


@router.post("/api/commitments/{session_id}/{commitment_id}/cancel")
async def cancel_session_commitment(
    session_id: int,
    commitment_id: int,
    req: CancelCommitmentRequest | None = Body(default=None),
    request: Request = None,
):
    """Cancels an active rendezvous or commitment in commitments_ledger without flake penalty."""
    from mechanics.system import commitments_engine

    session, _ = await verify_session_participant(request, session_id, req.user_id if req else None)

    reason = (req.reason if req and req.reason else "player_cancelled").strip()
    cancelled = await adb(
        commitments_engine.cancel_commitment,
        session_id,
        commitment_id,
        reason=reason,
        cancelled_by="player",
    )
    if not cancelled:
        raise HTTPException(status_code=404, detail="Commitment not found or already resolved")

    contacts = await adb(db.get_contacts, session_id) or []
    active_commitments = await adb(db.get_active_commitments, session_id)
    pending_appts = await adb(db.get_phone_appointments, session_id, status="pending")
    arrived_appts = await adb(db.get_phone_appointments, session_id, status="arrived")
    appointments = (pending_appts or []) + (arrived_appts or [])

    return {
        "success": True,
        "cancelled_id": commitment_id,
        "commitments": _enrich_commitments_for_ui(session_id, active_commitments, contacts),
        "appointments": _enrich_commitments_for_ui(session_id, appointments, contacts),
    }


from .encyclopedia import get_codex_encyclopedia  # noqa: F401



