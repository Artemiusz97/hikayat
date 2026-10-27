from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel
import json

import db
from db import adb
import game_engine
import mechanics.social.persona
import mechanics.social.relationships
import mechanics.social.genealogy
import mechanics.narrative.bounty
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

if not hasattr(game_engine, "generate_faction_bounty_board"):
    game_engine.generate_faction_bounty_board = mechanics.narrative.bounty.generate_faction_bounty_board


def _default_get_or_generate_family_tree(session_id: int, contact: dict, scenario: str = "fantasy"):
    rel = (contact.get("relations") or {}) if isinstance(contact, dict) else {}
    if not rel.get("family"):
        try:
            rel = mechanics.social.genealogy.ensure_contact_relations(
                contact, session_id=session_id, scenario=scenario
            ) or {}
        except Exception:
            rel = {}
    return rel.get("family") or []


if not hasattr(mechanics.social.genealogy, "get_or_generate_family_tree"):
    mechanics.social.genealogy.get_or_generate_family_tree = _default_get_or_generate_family_tree
from .deps import (
    PhoneMessageRequest,
    CompanionPartyRequest,
    FactionHQActionRequest,
    PhoneFeedActionRequest,
    PeerPulseDiscoverRequest,
    PeerPulseFriendRequest,
    BountyGenerateRequest,
    BountyActionRequest,
    ClueDeductionRequest,
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
async def manage_party_companion(req: CompanionPartyRequest):
    """Recruits a high-affinity NPC into the active party (max 2 companions) or dismisses them."""
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

    # Non-combat scenario guard
    scen_key = str(session.get("scenario") or "fantasy").lower()
    import scenario_data
    if not scenario_data.is_mechanic_enabled(scen_key, "tactical_combat") or scenario_data.has_tag(scen_key, "non_combat") or scenario_data.has_tag(scen_key, "high_school"):
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
    extra_companion_fields = {}

    comp_hp = 45
    comp_max_hp = 45
    comp_mp = 25
    comp_max_mp = 25

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import evaluate_anomalous_companion_recruitment
        eval_res = await adb(evaluate_anomalous_companion_recruitment, session, req.user_id, matched_contact, score, char_level)
        if not eval_res.get("allowed"):
            raise HTTPException(status_code=400, detail=eval_res.get("reason") or f"Cannot recruit {npc_name}.")
        rec_cost = int(eval_res.get("cost", 0) or 0)
        comp_hp = int(eval_res.get("hp", 130) or 130)
        comp_max_hp = int(eval_res.get("max_hp", comp_hp) or comp_hp)
        comp_mp = int(eval_res.get("mp", 60) or 60)
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
            "stats": eval_res.get("stats", {}),
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
        "role": extra_companion_fields.get("agent_class") or basic_info.get("role") or basic_info.get("occupation") or matched_contact.get("role") or "Companion",
        "hp": comp_hp,
        "max_hp": comp_max_hp,
        "mp": comp_mp,
        "max_mp": comp_max_mp,
        "relationship_score": score,
        **extra_companion_fields,
    }
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
    updated_sess = await adb(db.get_session, req.session_id) or {}
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


@router.get("/api/lorebook/{session_id}")
async def get_lorebook(session_id: int, user_id: int | None = Query(None)):
    """Fetches lorebook entities grouped by category, restricting person entities to discovered characters."""
    import re
    from mechanics.social.persona import infer_contact_gender
    from mechanics.social.persona.intimacy.appearance import normalize_appearance

    session = await adb(db.get_session, session_id) or {}
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
                        it_dict["race"] = it_dict.get("race") or dir_entry.get("race") or "human"
                        it_dict["gender"] = it_dict.get("gender") or dir_entry.get("gender") or ""
                        it_dict["role"] = it_dict.get("role") or dir_entry.get("role") or ""

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
                        # Persist back into DB so it heals permanently
                        try:
                            await adb(
                                db.upsert_lorebook_entity,
                                session_id=session_id,
                                entity_type="person",
                                name=it_dict["name"],
                                gender=it_dict["gender"],
                                race=it_dict.get("race", "human"),
                                appearance=norm_app
                            )
                        except Exception:
                            pass

                    # Enrich full dossier for character profile viewing
                    it_basic = it_dict.get("basic_info") or {}
                    if isinstance(it_basic, str):
                        try:
                            it_basic = json.loads(it_basic)
                        except Exception:
                            it_basic = {}
                    it_basic.setdefault("role", it_dict.get("role") or "")
                    it_basic.setdefault("grade", it_dict.get("grade") or "")
                    it_basic.setdefault("club", it_dict.get("club") or "")
                    it_basic.setdefault("race", it_dict.get("race") or "human")
                    it_basic.setdefault("gender", it_dict["gender"])
                    it_basic.setdefault("description", it_dict.get("description") or "")
                    it_basic.setdefault("mannerisms", it_dict.get("mannerisms") or "")
                    it_dict["basic_info"] = it_basic

                    enriched_person = _enrich_contact_record(it_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st)
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

            c_gender = c.get("gender") or b_info.get("gender") or infer_contact_gender({"name": c_name, "basic_info": b_info}) or "female"
            c_race = c.get("race") or b_info.get("race") or "human"
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
            p_dict["role"] = b_info.get("role") or b_info.get("occupation") or "Contact"
            p_dict["race"] = c_race
            p_dict["gender"] = c_gender
            p_dict["grade"] = b_info.get("grade") or ""
            p_dict["club"] = b_info.get("club") or ""
            p_dict["mannerisms"] = b_info.get("mannerisms") or ""
            p_dict["description"] = b_info.get("description") or ""
            p_dict["appearance"] = c_app
            p_dict["appearance_json"] = json.dumps(c_app)
            p_dict["entity_type"] = "person"
            p_dict["basic_info"] = b_info
            p_dict["relationship_score"] = score
            p_dict["is_contact"] = bool(is_unlocked_contact(c, party_names, met_in_story_names=met_in_story_names))
            p_dict["is_discovered"] = True

            enriched_p = _enrich_contact_record(p_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st)
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
            p_dict = {
                "name": display_name,
                "formal_title": (r_entry.get("formal_title") if r_entry else "") or "",
                "role": (r_entry.get("role") if r_entry else None) or (matched_curr_npc.get("role") if matched_curr_npc else "Acquaintance"),
                "grade": (r_entry.get("grade") if r_entry else "") or "",
                "club": (r_entry.get("club") if r_entry else "") or "",
                "race": (r_entry.get("race") if r_entry else "") or "human",
                "gender": (r_entry.get("gender") if r_entry else "") or "female",
                "entity_type": "person",
                "relationship_score": 0,
                "is_contact": False,
            }
            enriched_p = _enrich_contact_record(p_dict, session_id, scen_key, debug_reveal_all, phys_st=phys_st)
            p_dict.update(enriched_p)
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
    }


def _enrich_contact_record(c_raw: dict, session_id: int, scen_key: str, debug_reveal_all: bool, phys_st: dict | None = None) -> dict:
    from mechanics.social.relationships import enrich_contact_dossier
    return enrich_contact_dossier(c_raw, session_id, scen_key, debug_reveal_all=debug_reveal_all, phys_st=phys_st)


@router.get("/api/contacts/{session_id}")
async def get_contacts(session_id: int, user_id: int | None = Query(None)):
    """Fetches NPC contacts and relationship standings."""
    session = await adb(db.get_session, session_id) or {}
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
    enriched_contacts = await adb(
        lambda: [_enrich_contact_record(c, session_id, scen_key, debug_reveal_all, phys_st=phys_st) for c in contacts]
    )
    from mechanics.social.relationships import collect_met_npc_names, is_unlocked_contact
    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    met_names = collect_met_npc_names(session, party_npcs=party_npcs)
    unlocked_contacts = [c for c in enriched_contacts if is_unlocked_contact(c, party_names, met_in_story_names=met_names)]
    return {
        "contacts": unlocked_contacts,
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
        if is_anom:
            arch = infer_anomalous_faction_archetype(f_dict)
            f_dict["archetype_key"] = arch
            f_dict["joinable"] = arch not in ANOMALOUS_DISTRUSTED_ARCHETYPES
            f_dict["diplomatic_stance"] = "distrusted" if arch in ANOMALOUS_DISTRUSTED_ARCHETYPES else "friendly"
        enriched.append(f_dict)

    return {"factions": enriched, "membership": membership, "agent_dossier": agent_dossier}


@router.get("/api/factions/{session_id}")
async def get_factions(session_id: int, user_id: int | None = None):
    """Fetches faction standings, Rank 1-4 leadership rosters, hierarchy templates, and player membership."""
    return await adb(_enrich_factions_list, session_id, user_id)


@router.post("/api/factions/{session_id}/hq-action")
async def faction_hq_action(session_id: int, req: FactionHQActionRequest):
    """Executes a Faction HQ operation: join, leave, rest, quartermaster, bounty, or promote."""
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
        if is_anom:
            res = await adb(join_or_transfer_anomalous_faction, session_id, "freelancer", req.user_id)
            payload = await adb(_enrich_factions_list, session_id, req.user_id)
            return {
                "success": True,
                "action": "leave",
                "message": res.get("message", f"You have parted ways with {faction.get('name')} and are now an Independent Freelancer."),
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
        if is_anom:
            from mechanics.social.factions import get_anomalous_faction_state, infer_anomalous_faction_archetype
            a_st = await adb(get_anomalous_faction_state, session_id, req.user_id)
            fac_arch = infer_anomalous_faction_archetype(faction)
            if str(a_st.get("faction_archetype_key") or "") != fac_arch:
                raise HTTPException(
                    status_code=403,
                    detail=f"Safehouse recovery quarters at {faction.get('name', 'this faction')} are restricted to enlisted operatives."
                )
        elif tier["tier_level"] < 2:
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
        if is_anom:
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
            if fac_arch in ("private_agency_1", "private_agency_2") and player_arch != fac_arch:
                raise HTTPException(
                    status_code=403,
                    detail=f"{faction.get('name', 'Private Syndicate')} Quartermaster access is restricted exclusively to contracted operatives of this agency."
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
        return {
            "success": True,
            "action": "quartermaster",
            "merchant": merchant,
            "message": f"{faction.get('name', 'Faction')} Quartermaster requisition catalogue unlocked!",
            **payload,
        }

    if action == "bounty":
        if is_anom:
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
        return {
            "success": True,
            "action": "bounty",
            "bounties": [dict(b) for b in (bounties or []) if b],
            "message": f"Generated {len(bounties or [])} faction contracts for {faction.get('name', 'Faction')}!",
            **payload,
        }

    if action in ("promote", "challenge_leader"):
        if is_anom:
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
            return {
                "success": True,
                "action": "promote",
                "auto_promoted": True,
                "target_rank": target_rank,
                "target_title": new_title,
                "message": f"Promoted to Rank {target_rank}: {new_title}!",
                **payload,
            }

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

    raise HTTPException(status_code=400, detail=f"Unsupported faction HQ action: {req.action}")


def _build_quests_payload(session_id: int) -> dict:
    from mechanics.world.waypoints import ensure_quest_waypoints_exist, get_story_quest_climax_location
    try:
        ensure_quest_waypoints_exist(session_id)
    except Exception:
        pass
    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    quests = [dict(q) for q in db.get_session_quests(session_id) if q]
    from mechanics.world.locations.hierarchy import (
        resolve_session_location_tokens,
        clean_narrative_location_arrows,
        dedupe_location_stutter,
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

    for q in quests:
        _clean_quest_dict(q)
    active_sq = db.get_active_story_quest(session_id)
    if active_sq:
        active_sq = dict(active_sq)
        _clean_quest_dict(active_sq)
    if active_sq and active_sq.get("climax_ready"):
        try:
            _, climax_loc = get_story_quest_climax_location(session_id)
            if climax_loc:
                clean_climax = dedupe_location_stutter(climax_loc.replace(" -> ", " ➔ "))
                active_sq["climax_location"] = clean_climax
                active_sq["target_location"] = clean_climax
        except Exception:
            pass
    clues = [dict(c) for c in db.get_session_clues(session_id) if c]
    available_bounties = [q for q in quests if q.get("status") == "Available"]
    import scenario_data as _sd_qp
    if _sd_qp.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility, parse_anomalous_quest_board_source
            host_uid = session.get("host_user_id") if session else None
            for bq in available_bounties:
                elig = evaluate_anomalous_bounty_eligibility(session_id, host_uid, bq)
                bq["board_source"] = parse_anomalous_quest_board_source(bq, session_id=session_id)
                bq["anomalous_eligible"] = bool(elig.get("allowed", True))
                bq["anomalous_lock_reason"] = str(elig.get("reason") or "")
        except Exception:
            pass
    nb_label, nb_emoji = get_notice_board_label(scen_key)
    current_chapter = db.get_session_chapter(session_id) or 1
    campaign_end_goals = session.get("campaign_end_goals") or db.get_session_campaign_goals(session_id) or []
    chapter_digest = db.get_chapter_digest(session_id) or []
    return {
        "quests": quests,
        "available_bounties": available_bounties,
        "active_story_quest": active_sq,
        "clues": clues,
        "has_bounty_board": location_has_bounty_board(current_loc, scen_key=scen_key),
        "notice_board_label": nb_label,
        "notice_board_emoji": nb_emoji,
        "current_chapter": current_chapter,
        "campaign_end_goals": campaign_end_goals,
        "chapter_digest": chapter_digest,
    }


@router.get("/api/quests/{session_id}")
async def get_quests(session_id: int):
    """Fetches active, available, and completed quests, active story quest, and detective caseboard clues."""
    return await adb(_build_quests_payload, session_id)


@router.post("/api/quests/{session_id}/bounties/generate")
async def generate_session_bounties(session_id: int, req: BountyGenerateRequest):
    """Generates or refreshes the Bounty Board contracts for the session."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if req.faction_id:
        factions = await adb(db.get_factions, session_id)
        target_f = next((f for f in (factions or []) if f.get("faction_id") == req.faction_id), None)
        if target_f:
            bounties = await game_engine.generate_faction_bounty_board(session, target_f, force_refresh=req.force_refresh)
        else:
            bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)
    else:
        bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)

    payload = await adb(_build_quests_payload, session_id)
    return {
        "success": True,
        "bounties": [dict(b) for b in (bounties or []) if b],
        **payload,
    }


@router.post("/api/quests/{session_id}/bounties/action")
async def bounty_contract_action(session_id: int, req: BountyActionRequest):
    """Accepts an available bounty or abandons an active bounty."""
    quest = await adb(db.get_quest_by_id, session_id, req.quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Bounty contract not found")

    session = await adb(db.get_session, session_id) or {}
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

    if action == "accept":
        can_take = await adb(game_engine.can_accept_side_bounty, session_id, quest)
        if not can_take:
            raise HTTPException(
                status_code=400,
                detail="Maximum 3 active side bounties reached! Complete or abandon one first.",
            )
        new_status = "Active"
        msg = f"Accepted contract: {quest.get('title', 'Bounty')}!"
        await adb(db.update_quest_status, session_id, req.quest_id, new_status)
    elif action == "abandon":
        forfeit_res = await adb(game_engine.forfeit_side_bounty, session_id, req.quest_id, [req.user_id])
        if not forfeit_res.get("success"):
            raise HTTPException(status_code=400, detail=forfeit_res.get("reason") or "Cannot abandon this contract.")
        new_status = "Abandoned"
        msg = f"Abandoned contract: {quest.get('title', 'Bounty')}."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid bounty action: {req.action}")

    payload = await adb(_build_quests_payload, session_id)
    return {
        "success": True,
        "quest_id": req.quest_id,
        "status": new_status,
        "message": msg,
        **payload,
    }


@router.post("/api/quests/{session_id}/clues/deduce")
async def deduce_caseboard_clues(session_id: int, req: ClueDeductionRequest):
    """Cross-references two evidence clues to synthesize a Breakthrough deduction and award +50 XP."""
    if req.clue_a_id == req.clue_b_id:
        raise HTTPException(status_code=400, detail="Select two distinct pieces of evidence to deduce a connection.")

    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    clue_a = await adb(db.get_session_clue_by_id, req.clue_a_id)
    clue_b = await adb(db.get_session_clue_by_id, req.clue_b_id)
    if not clue_a or not clue_b:
        raise HTTPException(status_code=404, detail="One or both selected evidence records could not be found.")
    if clue_a.get("is_consumed") or clue_b.get("is_consumed"):
        raise HTTPException(status_code=400, detail="One or both selected leads have already been consumed.")

    # D18 Anti-spam cooldown: max 1 attempt per pair per turn
    pair_key = f"{min(int(req.clue_a_id), int(req.clue_b_id))}:{max(int(req.clue_a_id), int(req.clue_b_id))}"
    cur_turn = len(session.get("history") or [])
    attempts_map = dict(session.get("deduction_attempts_turn") or {})
    if attempts_map.get(pair_key) == cur_turn:
        raise HTTPException(
            status_code=400,
            detail="You already attempted to connect this pair of leads this turn. Advance the story or try another lead!",
        )

    scen_key = session.get("scenario", "fantasy")
    is_valid, title, detail_text = evaluate_clue_deduction(clue_a, clue_b, scen_key=scen_key)

    xp_awarded = 0
    if is_valid:
        attempts_map[pair_key] = cur_turn
        await adb(db.update_session, session_id, extra={"deduction_attempts_turn": attempts_map})
        char_row = await adb(db.get_character, req.user_id) if req.user_id else {}
        import random
        cats = {clue_a.get("category", "physical"), clue_b.get("category", "physical")}
        if "deduction" in cats or "digital" in cats or "document" in cats:
            stat_key = "int_"
            stat_name = "INT"
        elif "testimonial" in cats:
            stat_key = "cha"
            stat_name = "CHA"
        else:
            stat_key = "per_"
            stat_name = "PER"
            
        stat_val = char_row.get(stat_key, 5) if char_row else 5
        success_rate = max(10, min(100, 20 + (stat_val * 10)))
        
        roll = random.randint(1, 100)
        if roll > success_rate:
            is_valid = False
            title = "Deduction Failed"
            detail_text = f"You tried to connect the evidence, but couldn't quite see the full picture. (Rolled {roll} vs {success_rate}% {stat_name})"
        else:
            def _apply_deduction():
                cur_ch = db.get_session_chapter(session_id) or 1
                db.synthesize_deduction_clue(
                    session_id, [req.clue_a_id, req.clue_b_id], title, detail_text, chapter=cur_ch
                )
                members = db.get_session_members(session_id)
                for uid in members:
                    try:
                        db.add_xp(uid, 50)
                    except Exception:
                        pass
            await adb(_apply_deduction)
            xp_awarded = 50

    payload = await adb(_build_quests_payload, session_id)
    return {
        "success": True,
        "is_valid": is_valid,
        "title": title,
        "detail_text": detail_text,
        "xp_awarded": xp_awarded,
        **payload,
    }


@router.get("/api/phone/{session_id}")
async def get_phone_state(session_id: int, user_id: int = Query(...)):
    """Fetches smartphone OS state: scenario branding, appointments, gossip feed, contacts, social state, and digital media gallery."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
async def refresh_phone_feed(session_id: int, req: PhoneFeedActionRequest):
    """Generates fresh in-universe social media timeline posts."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
async def scour_phone_feed(session_id: int, req: PhoneFeedActionRequest):
    """Consumes 1 rumor charge (max 3) to roll a PER/INT check for a verified story clue."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    res = await scour_feed_for_rumor(dict(session), req.user_id)
    social_state = await adb(get_social_state_summary, session_id, session)
    gossip = res.get("gossip_feed")
    if not gossip:
        gossip = [dict(g) for g in (await adb(db.get_gossip_feed, session_id, limit=20))]
    return {
        **res,
        "gossip_feed": [dict(g) for g in gossip],
        "social_state": social_state,
    }


@router.post("/api/phone/{session_id}/peerpulse/discover")
async def discover_peerpulse_profile(session_id: int, req: PeerPulseDiscoverRequest):
    """Looks up a specific peer profile by name/handle or discovers a suggested uncontacted peer."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
async def send_peerpulse_friend_request(session_id: int, req: PeerPulseFriendRequest):
    """Resolves a PeerPulse friend request using CHA + mutual friend / shared club / sibling bonuses."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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
            unlocked_contacts.append(uc_copy)
    return {
        "success": True,
        **res,
        "profile": req.profile,
        "contacts": unlocked_contacts,
    }


@router.get("/api/phone/{session_id}/peerpulse/suggestions")
async def get_peerpulse_suggestions(session_id: int, user_id: int = Query(...)):
    """Fetches suggested student peers for PeerPulse Graph."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
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
async def get_npc_messages(session_id: int, npc_id: str):
    """Fetches direct message chat history with a specific NPC contact."""
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    messages = await adb(db.get_phone_messages, session_id, clean_npc_id, limit=20)
    current_day, _, _ = await adb(db.get_session_time, session_id)
    daily_limits = await adb(db.get_phone_daily_limits, session_id, clean_npc_id, current_day)
    return {
        "messages": [dict(m) for m in messages],
        "daily_limits": daily_limits,
    }


@router.post("/api/phone/{session_id}/messages/{npc_id}")
async def send_npc_message(session_id: int, npc_id: str, req: PhoneMessageRequest):
    """Sends a text message to an NPC contact and generates an immediate contextual reply."""
    text = (req.message or "").strip()
    if (not text or text == "__auto__") and not req.intent:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    norm_target_id = str(npc_id or "").strip().lower().replace(" ", "_")
    if norm_target_id == "metropolitan_anomaly_watch" or norm_target_id.endswith("_dispatch"):
        raise HTTPException(
            status_code=400,
            detail="Automated dispatch channels are read-only broadcast feeds and do not accept replies."
        )

    session_row = await adb(db.get_session, session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")
    session = dict(session_row)

    char_row = await adb(db.get_character, req.user_id)
    if not char_row:
        raise HTTPException(status_code=404, detail="Character not found")
    player_char = dict(char_row)

    contact = await adb(db.get_contact, session_id, npc_id, character_id=player_char.get("id", 0))
    if not contact:
        # Try matching against all contacts in session
        all_contacts = await adb(db.get_contacts, session_id, req.user_id)
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

    from mechanics.social.relationships import is_contact_blocked
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
            detail=f"{contact.get('name', 'This contact')}'s line is disconnected — they perished during an anomalous incursion."
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
):
    """Cancels an active rendezvous or commitment in commitments_ledger without flake penalty."""
    from mechanics.system import commitments_engine

    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

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


