from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

import db
from db import adb
import game_engine
from mechanics.combat.loadouts import (
    build_combatant_stat_sheet,
    compute_companion_vitals,
    ensure_combatant_loadout,
)
from mechanics.system.concurrency import distributed_adventure_lock
from ..deps import CompanionPartyRequest
from ..security import verify_session_participant

router = APIRouter()


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
        from ..adventure import enrich_session_for_client

        updated_sess = await adb(db.get_session, req.session_id) or {}
        enriched_sess = await adb(enrich_session_for_client, updated_sess, req.user_id)
        party_npcs = (
            enriched_sess.get("party_npcs")
            if isinstance(enriched_sess, dict)
            else await adb(db.get_session_party_npcs, req.session_id)
        )
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

    is_pure_hs = scenario_data.has_tag(scen_key, "high_school") and not scenario_data.is_anomalous_incursions_scenario(
        scen_key
    )
    if (
        not scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        or scenario_data.has_tag(scen_key, "non_combat")
        or is_pure_hs
    ):
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
        (
            dict(c)
            for c in contacts
            if (c.get("name") or "").strip().lower() == npc_name.lower()
            or (c.get("npc_id") or "").strip().lower() == npc_name.lower().replace(" ", "_")
        ),
        None,
    )
    if not matched_contact:
        lore_data = await adb(db.get_lorebook, req.session_id)
        if isinstance(lore_data, dict):
            matched_contact = next(
                (dict(p) for p in lore_data.get("person", []) if (p.get("name") or "").strip().lower() == npc_name.lower()),
                None,
            )
        if not matched_contact:
            curr_npcs = session.get("current_npcs") or []
            matched_contact = next(
                (
                    dict(n)
                    for n in curr_npcs
                    if isinstance(n, dict) and (n.get("name") or "").strip().lower() == npc_name.lower()
                ),
                None,
            )
        if not matched_contact and scenario_data.is_anomalous_incursions_scenario(scen_key):
            from mechanics.social.agent_roster import find_special_agent_by_name

            sp_agent = await adb(find_special_agent_by_name, req.session_id, npc_name, scen_key)
            if sp_agent:
                matched_contact = dict(sp_agent)
    if not matched_contact:
        raise HTTPException(
            status_code=404,
            detail=f"NPC '{npc_name}' not found in contacts, current scene, or world codex.",
        )

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

    if rec_cost > 0 and char_gold < rec_cost:
        cost_fmt = scenario_data.format_scenario_currency(rec_cost, scen_key)
        have_fmt = scenario_data.format_scenario_currency(char_gold, scen_key)
        raise HTTPException(
            status_code=400,
            detail=(
                f"{npc_name} requires at least Friend standing (100 affinity) to join for free, "
                f"or {cost_fmt} to recruit (you have {have_fmt})."
            ),
        )

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

    if rec_cost > 0:
        try:
            await adb(db.apply_hp_mp_delta, req.user_id, gold_delta=-rec_cost)
        except Exception:
            await adb(db.remove_session_party_npc, req.session_id, npc_payload["name"])
            raise

    # Recruited companions enter Party & Known Characters; only >= 100 or explicitly unlocked contacts appear in personal Contacts
    existing_in_contacts = any((c.get("name") or "").strip().lower() == npc_name.lower() for c in contacts)
    delta_to_apply = 0 if existing_in_contacts else score
    c_app = matched_contact.get("appearance") or matched_contact.get("appearance_json")
    if isinstance(c_app, str):
        try:
            c_app = json.loads(c_app)
        except (json.JSONDecodeError, TypeError, ValueError):
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
        upsert_binfo.update(
            {
                "anomalous_npc_tag": "special_agent",
                "is_special_agent": True,
                "agent_tier": extra_companion_fields.get("agent_tier", 1),
                "rank_title": extra_companion_fields.get("rank_title", ""),
                "agent_class": extra_companion_fields.get("agent_class", ""),
                "faction_id": extra_companion_fields.get("faction_id", ""),
                "faction": extra_companion_fields.get("faction_name", ""),
                "innate_abilities": extra_companion_fields.get("innate_abilities", []),
            }
        )
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
        scenario=scen_key,
    )

    from ..adventure import enrich_session_for_client

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
    enriched_sess = await adb(enrich_session_for_client, updated_sess, req.user_id)
    party_npcs = (
        enriched_sess.get("party_npcs")
        if isinstance(enriched_sess, dict)
        else await adb(db.get_session_party_npcs, req.session_id)
    )
    return {
        "success": True,
        "status": "recruited",
        "action": "recruited",
        "npc_name": npc_payload["name"],
        "message": f"{npc_payload['name']} joined your party!",
        "party_npcs": party_npcs,
    }
