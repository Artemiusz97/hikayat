from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

import db
from db import adb
import game_engine
from mechanics.social.factions import (
    ANOMALOUS_OUTLAW_ARCHETYPES,
    ensure_starter_factions,
    generate_procedural_leadership_roster as generate_leadership_roster,
    get_active_perks,
    get_agent_dossier_summary,
    get_anomalous_promotion_tiers_for_archetype,
    get_eligible_rank,
    get_faction_tier,
    get_hierarchy,
    get_incumbent_at_rank,
    get_promotion_trial_directive,
    get_rank_title,
    infer_anomalous_faction_archetype,
    is_nsfw_salon_faction,
    join_or_transfer_anomalous_faction,
    promote_player_in_roster,
    remove_player_from_roster,
    sync_faction_rosters_with_contacts,
    validate_club_quartermaster_hours,
    validate_faction_hq_action_access,
    validate_major_club_subroom_action,
)
from mechanics.system.concurrency import distributed_session_lock, distributed_user_lock
from mechanics.world.locations import reveal_hidden_club_facility
from ..deps import FactionHQActionRequest, serializable_action
from ..security import verify_session_participant
from .common import _verify_missing_session_codex_auth

router = APIRouter()


def _enrich_factions_list(session_id: int, user_id: int | None = None) -> dict:
    import scenario_data

    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    lookup_uid = user_id or session.get("host_user_id")

    try:
        ensure_starter_factions(session_id, scen_key)
        if is_anom:
            from mechanics.social.agent_roster import ensure_anomalous_agent_roster

            ensure_anomalous_agent_roster(session_id, scen_key)
        sync_faction_rosters_with_contacts(session_id)
    except Exception:
        pass

    agent_dossier = (
        get_agent_dossier_summary(session_id, lookup_uid) if is_anom else {"is_anomalous_incursions": False}
    )
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
        sal_susp = bool(f_dict["is_member"] and (agent_dossier or {}).get("salary_ration_suspended"))
        perks = get_active_perks(f_dict, eff_rank, rep, salary_suspended=sal_susp)
        f_dict["active_perks"] = perks or []
        f_dict["rival_faction_ids"] = f_dict.get("rival_faction_ids") or []
        from mechanics.social.factions import get_faction_category_tag, is_school_club_faction

        f_dict["is_school_club"] = is_school_club_faction(f_dict)
        f_dict["category_tag"] = get_faction_category_tag(f_dict, scen_key)
        if is_anom:
            arch = infer_anomalous_faction_archetype(f_dict)
            is_outlaw = arch in ANOMALOUS_OUTLAW_ARCHETYPES
            f_dict["archetype_key"] = arch
            f_dict["joinable"] = True
            f_dict["is_outlaw"] = is_outlaw
            f_dict["diplomatic_stance"] = "outlaw" if is_outlaw else "friendly"
            f_dict["promotion_tiers"] = get_anomalous_promotion_tiers_for_archetype(arch)
            if not f_dict["is_school_club"]:
                player_arch = str((agent_dossier or {}).get("faction_archetype_key") or "freelancer").strip().lower()
                player_outlaw = player_arch in ANOMALOUS_OUTLAW_ARCHETYPES
                f_dict["quartermaster_eligible"] = (
                    (not player_outlaw) if arch == "public_agency" else (player_arch == arch)
                )
                f_dict["bounty_board_eligible"] = (
                    (not player_outlaw) if arch == "public_agency" else (player_arch == arch)
                )
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
    char_id = char["id"]
    joined_fid = (char.get("joined_faction_id") or "").strip().lower()
    target_fid = (faction.get("faction_id") or "").strip().lower()

    import scenario_data

    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    current_loc_str = str(session.get("current_location") or "")
    subroom_err = await adb(validate_major_club_subroom_action, session_id, faction, action, current_loc_str, scen_key)
    if subroom_err:
        raise HTTPException(status_code=400, detail=subroom_err)

    if action in ("join", "transfer"):
        if is_anom:
            res = await adb(join_or_transfer_anomalous_faction, session_id, faction["faction_id"], req.user_id)
            if not res.get("success"):
                raise HTTPException(status_code=400, detail=res.get("error", "Cannot join this faction."))
            if is_nsfw_salon_faction(faction):
                await adb(reveal_hidden_club_facility, session_id, "loc_nsfw_club_facility", int(session.get("turn_count") or 0))
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            updated_sess = await adb(db.get_session, session_id) or {}
            return {
                "success": True,
                "action": action,
                "message": res.get("message", f"Joined {faction.get('name')}!"),
                "session_sync": {
                    "current_location": updated_sess.get("current_location"),
                    "current_node_id": updated_sess.get("current_node_id"),
                    "party_npcs": updated_sess.get("party_npcs") or [],
                },
                **payload,
            }
        if joined_fid and joined_fid != target_fid:
            raise HTTPException(
                status_code=400,
                detail="You are already pledged to a faction! Leave your current faction before joining another.",
            )
        rank_1_title = get_rank_title(template, 1)
        await adb(db.set_character_faction_membership, char_id, faction["faction_id"], 1, rank_1_title)
        if is_nsfw_salon_faction(faction):
            await adb(reveal_hidden_club_facility, session_id, "loc_nsfw_club_facility", int(session.get("turn_count") or 0))
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
            fallback_target = (
                "student_freelancer"
                if (scenario_data.is_anomalous_high_school_scenario(scen_key) and is_school_club_faction(faction))
                else "freelancer"
            )
            res = await adb(join_or_transfer_anomalous_faction, session_id, fallback_target, req.user_id)
            if not res.get("success"):
                raise HTTPException(status_code=400, detail=res.get("error", "Cannot leave this faction."))
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            updated_sess = await adb(db.get_session, session_id) or {}
            return {
                "success": True,
                "action": "leave",
                "message": res.get("message", f"You have parted ways with {faction.get('name')}."),
                "session_sync": {
                    "current_location": updated_sess.get("current_location"),
                    "current_node_id": updated_sess.get("current_node_id"),
                    "party_npcs": updated_sess.get("party_npcs") or [],
                },
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
        hq_ok, hq_err, hq_code = await adb(
            validate_faction_hq_action_access, session_id, req.user_id, faction, "rest", session
        )
        if not hq_ok:
            raise HTTPException(status_code=hq_code, detail=hq_err)
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
                        s
                        for s in (p_comp.get("status_effects") or [])
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
        fac_arch = infer_anomalous_faction_archetype(faction) if is_anom else ""
        hq_ok, hq_err, hq_code = await adb(
            validate_faction_hq_action_access, session_id, req.user_id, faction, "quartermaster", session
        )
        if not hq_ok:
            raise HTTPException(status_code=hq_code, detail=hq_err)
        current_day, current_minute, _ = await adb(db.get_session_time, session_id)
        hours_err = validate_club_quartermaster_hours(faction, current_minute)
        if hours_err:
            raise HTTPException(status_code=403, detail=hours_err)
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
        merchant.update(
            {
                "active": True,
                "active_store_key": faction_key,
                "stock": cat_entry["stock"],
                "discount_pct": discount,
                "is_faction_quartermaster": True,
                "quartermaster_faction_arch": fac_arch if is_anom else "",
                "restock_day": cat_entry.get("restock_day", current_day),
                "restock_minute": cat_entry.get("restock_minute", current_minute),
            }
        )
        await adb(db.save_merchant_state, session_id, merchant)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return serializable_action(
            {
                "success": True,
                "action": "quartermaster",
                "merchant": merchant,
                "message": f"{faction.get('name', 'Faction')} Quartermaster requisition catalogue unlocked!",
                **payload,
            }
        )

    if action == "bounty":
        hq_ok, hq_err, hq_code = await adb(
            validate_faction_hq_action_access, session_id, req.user_id, faction, "bounty", session
        )
        if not hq_ok:
            raise HTTPException(status_code=hq_code, detail=hq_err)
        bounties = await game_engine.generate_faction_bounty_board(session, faction)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return serializable_action(
            {
                "success": True,
                "action": "bounty",
                "bounties": [dict(b) for b in (payload.get("available_bounties") or []) if b],
                "message": f"Generated {len(bounties or [])} faction contracts for {faction.get('name', 'Faction')}!",
                **payload,
            }
        )

    if action in ("promote", "challenge_leader"):
        from mechanics.social.factions import is_school_club_faction

        is_club = is_school_club_faction(faction)
        if is_anom and not is_club:
            raise HTTPException(
                status_code=400,
                detail=(
                    "In Anomalous Incursions, operatives cannot usurp the fixed leadership hierarchy. "
                    "Advance from Tier 1 (Probationary Agent) to Tier 5 (Elite Agent) on the 5-Tier Promotion Meter "
                    "(0-100 Rep) by completing Faction Bounties (+10 Rep) and Daily Mandatory Dispatches (+15 Rep)!"
                ),
            )
        if joined_fid != target_fid:
            raise HTTPException(
                status_code=400,
                detail="Join this faction first before challenging for promotion.",
            )
        current_rank = int(char.get("faction_rank") or 1)
        eligible = get_eligible_rank(template, rep)
        if eligible <= current_rank:
            raise HTTPException(
                status_code=400,
                detail="You don't have enough reputation to challenge for the next rank yet.",
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
            return serializable_action(
                {
                    "success": True,
                    "action": "promote",
                    "auto_promoted": True,
                    "target_rank": target_rank,
                    "target_title": new_title,
                    "message": f"Promoted to Rank {target_rank}: {new_title}!",
                    **payload,
                }
            )

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
        from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells
        from mechanics.combat.spells.awakened_kits import (
            ABILITY_MEDIUMS,
            ANOMALOUS_ATTRIBUTES,
            COMBAT_ARCHETYPES,
            normalize_anomalous_attribute,
        )
        from mechanics.social.factions import get_anomalous_faction_state

        fac_arch = infer_anomalous_faction_archetype(faction)
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
                detail="HQ Telemetry Calibration requires Tier 4 standing or higher.",
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
        cost_fmt = scenario_data.format_scenario_currency(500, scen_key)
        cur_fmt = scenario_data.format_scenario_currency(cur_gold, scen_key)
        if cur_gold < 500:
            raise HTTPException(
                status_code=400,
                detail=f"Telemetry Calibration requires {cost_fmt} (you currently have {cur_fmt}).",
            )

        inv_items = await adb(db.get_inventory, req.user_id)
        core_item = next(
            (
                it
                for it in (inv_items or [])
                if not it.get("equipped")
                and not it.get("is_quest_locked")
                and not it.get("is_pact_locked")
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

        removed = await adb(db.remove_item, req.user_id, int(core_item["id"]))
        if not removed:
            raise HTTPException(
                status_code=400,
                detail="Could not consume Hume Core (item locked or no longer available).",
            )

        gold_deducted = False
        try:
            await adb(db.apply_hp_mp_delta, req.user_id, 0, 0, -500)
            gold_deducted = True
            await adb(db.set_character_3axis, req.user_id, new_attr, new_arch, new_med)
            await adb(sync_equipped_anomalous_spells, req.user_id)
        except Exception:
            if gold_deducted:
                try:
                    await adb(db.apply_hp_mp_delta, req.user_id, 0, 0, 500)
                except Exception:
                    pass
            try:
                await adb(
                    db.add_item,
                    req.user_id,
                    core_item["name"],
                    core_item.get("item_type") or "Material",
                    core_item.get("effect") or "",
                    int(core_item.get("slot_cost", 1) or 1),
                    True,
                )
            except Exception:
                pass
            raise

        cal_map[arc_key] = int(cal_map.get(arc_key, 0) or 0) + 1
        await adb(db.update_session, session_id, extra={"telemetry_calibrations_used": cal_map})
        learned_after = await adb(db.get_learned_spells, req.user_id)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return serializable_action(
            {
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
                    f"{new_med.replace('_', ' ').title()} (-{cost_fmt}, -1 {core_item['name']})."
                ),
                **payload,
            }
        )

    raise HTTPException(status_code=400, detail=f"Unsupported faction HQ action: {req.action}")
