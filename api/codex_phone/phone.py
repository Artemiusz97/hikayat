from __future__ import annotations

import json
import time
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request

import db
from db import adb
from mechanics.combat.items import (
    is_digital_item,
    parse_digital_item_metadata,
    update_digital_media_image,
)
from mechanics.system.concurrency import distributed_adventure_lock, distributed_session_lock
from mechanics.social.folklore_roster import has_spirit_relay_contact
from mechanics.social.origin_mode import resolve_player_age_profile
from mechanics.world.world_events.spirit_realm_events import (
    get_spirit_relay_static_note,
    is_spirit_relay_static_active,
)
from mechanics.system.phone import (
    cleanup_stale_campus_gossip_for_adult,
    detect_custom_message_intent,
    discover_suggested_peer,
    generate_contact_dm_reply,
    generate_gossip_feed_posts,
    generate_phone_media_image,
    generate_player_chat_message,
    get_phone_branding,
    get_social_state_summary,
    get_suggested_peers,
    is_media_item_in_flight,
    is_session_image_gen_enabled,
    is_stale_campus_gossip_post,
    lookup_social_profile,
    resolve_social_friend_request,
    scour_feed_for_rumor,
    spawn_phone_media_image_task,
)
from mechanics.world.world_events.engine import build_client_world_pulse_payload
from services.examine_service import invalidate_examine_cache
from ..deps import (
    PeerPulseDiscoverRequest,
    PeerPulseFriendRequest,
    PhoneFeedActionRequest,
    PhoneMediaGenerateRequest,
    PhoneMessageRequest,
    ensure_realm_comms_available,
    manager,
)
from ..security import verify_session_participant
from .common import (
    CancelCommitmentRequest,
    _enrich_commitments_for_ui,
    _get_contacts_ro,
)
from .contacts import _preload_fog_of_war_context

router = APIRouter()


@router.get("/api/phone/{session_id}")
async def get_phone_state(session_id: int, user_id: int = Query(...), request: Request = None):
    """Fetches smartphone OS state: scenario branding, appointments, gossip feed, contacts, social state, and digital media gallery."""
    session, eff_uid = await verify_session_participant(request, session_id, user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)
    char_row = await adb(db.get_character, canonical_id, session_id=session_id)
    if not char_row:
        char_row = await adb(db.get_character, canonical_id)
    media_owner_uid = int(char_row.get("user_id") or canonical_id) if isinstance(char_row, dict) else int(canonical_id)

    scen_key = session.get("scenario", "fantasy")
    inv = await adb(db.get_inventory, media_owner_uid)
    is_supported = True

    player_profile = resolve_player_age_profile(session, char_row)
    is_student = bool(player_profile.get("is_student"))
    branding = get_phone_branding(scen_key, session=session, is_student=is_student)
    pending_appts = await adb(db.get_phone_appointments, session_id, status="pending")
    arrived_appts = await adb(db.get_phone_appointments, session_id, status="arrived")
    appointments = (pending_appts or []) + (arrived_appts or [])
    gossip = await adb(db.get_gossip_feed, session_id, limit=15)
    if not is_student and gossip:
        gossip = [g for g in gossip if not is_stale_campus_gossip_post(g)]
    import scenario_data as _sd_phone

    if _sd_phone.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents

        await adb(prune_unmet_preseeded_special_agents, session_id)
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await _get_contacts_ro(session_id, char_id)
    if not contacts and char_id != canonical_id:
        contacts = await _get_contacts_ro(session_id, canonical_id)
    social_state = await adb(get_social_state_summary, session_id, session)

    digital_media = []
    for it in inv:
        if is_digital_item(it):
            meta = parse_digital_item_metadata(it) or {}
            img_url = str(meta.get("image_url") or "")
            img_status = str(meta.get("image_status") or ("ready" if img_url else "idle"))
            if img_status == "generating" and not is_media_item_in_flight(int(it.get("id") or 0)):
                img_status = "ready" if img_url else "idle"
            digital_media.append(
                {
                    "id": it.get("id"),
                    "name": it.get("name"),
                    "contact_name": meta.get("contact_name") or "Subject",
                    "contact_npc_id": meta.get("contact_npc_id") or "",
                    "media_type": meta.get("media_type") or "photo",
                    "caption": meta.get("caption") or it.get("effect") or "",
                    "timestamp": meta.get("timestamp"),
                    "tags": meta.get("tags") or [],
                    "image_url": img_url,
                    "image_status": img_status,
                }
            )

    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    from mechanics.social.relationships import (
        can_player_dm_contact,
        collect_met_npc_names,
        is_contact_blocked,
        is_unlocked_contact,
    )

    met_names = collect_met_npc_names(session, party_npcs=party_npcs)
    unlocked_contacts = []
    phone_fow_loaded = False
    phone_fow_ctx = None
    for c in contacts:
        if is_unlocked_contact(c, party_names, met_in_story_names=met_names) and can_player_dm_contact(
            c, party_names=party_names, scenario=str((session or {}).get("scenario") or "fantasy")
        ):
            uc_copy = dict(c)
            _uc_bi = uc_copy.get("basic_info")
            if isinstance(_uc_bi, str) and _uc_bi.strip():
                try:
                    _uc_bi = json.loads(_uc_bi)
                except Exception:
                    _uc_bi = {}
            uc_bi_dict = _uc_bi if isinstance(_uc_bi, dict) else {}
            uc_copy["spirit_relay_unlocked"] = has_spirit_relay_contact(uc_copy)
            uc_copy["folklore_village"] = str(uc_bi_dict.get("folklore_village") or "")
            uc_copy["is_blocked_contact"] = is_contact_blocked(uc_copy)
            uc_copy["can_dm"] = True
            if not uc_copy.get("debug_revealed"):
                if not phone_fow_loaded:
                    phone_fow_loaded = True
                    ph_set = await adb(db.get_settings, canonical_id) if canonical_id else {}
                    ph_dbg = bool((ph_set or {}).get("debug_reveal_all_info", 0))
                    ph_cid = int(char_id or 0)
                    phone_fow_ctx = (
                        None
                        if ph_dbg
                        else await adb(
                            _preload_fog_of_war_context,
                            session_id,
                            ph_cid,
                            party_names,
                            str((ph_set or {}).get("ui_language") or "en"),
                            None,
                            party_npcs,
                            str((session or {}).get("scenario") or "fantasy"),
                            session if isinstance(session, dict) else None,
                            char_row if isinstance(char_row, dict) else None,
                            int(canonical_id or 0),
                        )
                    )
                if isinstance(phone_fow_ctx, dict):
                    from mechanics.social.consequences import apply_fog_of_war_to_enriched_contact as _apply_ph_fow
                    from scenario_data import is_nsfw_scenario as _is_nsfw_ph

                    cn_ph = db.canon_social_npc_id(uc_copy.get("npc_id") or uc_copy.get("name") or "")
                    uc_copy = _apply_ph_fow(
                        uc_copy,
                        session_id=session_id,
                        character_id=phone_fow_ctx.get("character_id", 0),
                        preloaded_discoveries=(phone_fow_ctx.get("disc_by_npc") or {}).get(cn_ph, []),
                        lang=phone_fow_ctx.get("lang", "en"),
                        party_npc_keys=phone_fow_ctx.get("party_npc_keys"),
                        kin_npc_keys=phone_fow_ctx.get("kin_npc_keys"),
                        romantic_npc_keys=phone_fow_ctx.get("romantic_npc_keys"),
                        is_nsfw=(
                            _is_nsfw_ph(str((session or {}).get("scenario") or "fantasy"))
                            or ("nsfw" in str((session or {}).get("tags") or "").lower())
                        ),
                    )
            unlocked_contacts.append(uc_copy)

    synthetic_channels = []
    if _sd_phone.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.social.factions import get_anomalous_faction_state

            a_st = await adb(get_anomalous_faction_state, session_id, canonical_id)
            dispatch_defs = [
                ("metropolitan_anomaly_watch", "Metropolitan Anomaly Watch", "Citywide Anomaly Broadcast"),
            ]
            if a_st.get("faction_archetype_key", "freelancer") != "freelancer" and a_st.get("joined_faction_name"):
                f_disp = f"{a_st['joined_faction_name']} Dispatch"
                dispatch_defs.insert(
                    0, (f_disp.strip().lower().replace(" ", "_"), f_disp, "Mandatory Daily Dispatch")
                )
            for ch_id, ch_name, ch_role in dispatch_defs:
                msgs = await adb(db.get_phone_messages, session_id, ch_id, 1)
                if msgs:
                    synthetic_channels.append(
                        {
                            "npc_id": ch_id,
                            "name": ch_name,
                            "role": ch_role,
                            "is_dispatch_channel": True,
                            "read_only": True,
                        }
                    )
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
    suggested_peers = await adb(get_suggested_peers, session_id, canonical_id)
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

    from mechanics.world.locations.realms import check_realm_comms_available
    comms_status = await adb(check_realm_comms_available, session_id, session.get("current_node_id"))
    spirit_relay_active = bool(comms_status.get("spirit_relay_active"))
    ph_lang = str(
        (await adb(db.get_settings, canonical_id) if canonical_id else {} or {}).get("ui_language")
        or session.get("narration_language")
        or session.get("language")
        or "en"
    )
    spirit_relay_static_active = await adb(is_spirit_relay_static_active, session_id)
    spirit_relay_static_note = await adb(get_spirit_relay_static_note, session_id, ph_lang) if spirit_relay_static_active else ""

    return {
        "is_supported": is_supported,
        "scenario": scen_key,
        "comms_status": comms_status,
        "spirit_relay_active": spirit_relay_active,
        "spirit_relay_static_active": bool(spirit_relay_static_active),
        "spirit_relay_static_note": spirit_relay_static_note,
        "player_profile": player_profile,
        "image_gen_enabled": session.get("image_gen_enabled", 0),
        "branding": {
            "device_name": branding.get("device_name", "📱 Smartphone") if branding else "📱 Smartphone",
            "os_name": branding.get("os_name", "Mobile OS") if branding else "Mobile OS",
            "feed_app_name": branding.get("feed_app_name", "Feed") if branding else "Feed",
            "dm_app_name": branding.get("dm_app_name", "Messages") if branding else "Messages",
            "gallery_app_name": branding.get("gallery_app_name", "Photos") if branding else "Photos",
            "bounty_app_name": branding.get("bounty_app_name", "Bounty Board") if branding else "Bounty Board",
            "bounty_subtitle": branding.get("bounty_subtitle", "Local Tasks") if branding else "Local Tasks",
            "shop_app_name": branding.get("shop_app_name", "Online Store") if branding else "Online Store",
            "school_shop_app_name": branding.get("school_shop_app_name", "SchoolMart") if branding else "SchoolMart",
            "school_bounty_app_name": branding.get("school_bounty_app_name", "Campus Requests") if branding else "Campus Requests",
            "people_tab_label": branding.get("people_tab_label", "Network") if branding else "Network",
            "show_school_shop": bool(branding.get("show_school_shop", False)) if branding else False,
            "show_school_bounties": bool(branding.get("show_school_bounties", False)) if branding else False,
            "show_general_bounties": bool(branding.get("show_general_bounties", True)) if branding else True,
            "emoji": branding.get("emoji", "📱") if branding else "📱",
        }
        if branding
        else None,
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
    pre_session, canonical_id = await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id) or pre_session
        await ensure_realm_comms_available(session_id, session=session)
        player_char = (
            await adb(db.get_character, canonical_id, session_id=session_id)
            or await adb(db.get_character, canonical_id)
        )
        is_student = bool(resolve_player_age_profile(session, player_char).get("is_student"))

        if not is_student:
            await adb(cleanup_stale_campus_gossip_for_adult, session_id, dict(session))
        posts = await generate_gossip_feed_posts(dict(session), force_refresh=bool(req.force_refresh))
        gossip = await adb(db.get_gossip_feed, session_id, limit=15)
        if not is_student and gossip:
            gossip = [g for g in gossip if not is_stale_campus_gossip_post(g)]
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
    session, canonical_id = await verify_session_participant(request, session_id, req.user_id)

    async with distributed_session_lock(session_id):
        fresh_sess = await adb(db.get_session, session_id) or session
        await ensure_realm_comms_available(session_id, session=fresh_sess)
        res = await scour_feed_for_rumor(dict(fresh_sess), canonical_id)
    if res.get("discovered_rumor") or res.get("success"):
        try:
            invalidate_examine_cache(session_id)
        except Exception:
            pass
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
    session, canonical_id = await verify_session_participant(request, session_id, req.user_id)
    await ensure_realm_comms_available(session_id, session=session)

    query = (req.query_name or "").strip()
    if query:
        profile = await adb(lookup_social_profile, session_id, canonical_id, query)
    else:
        profile = await adb(discover_suggested_peer, session_id, canonical_id)

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
    pre_session, canonical_id = await verify_session_participant(request, session_id, req.user_id)
    req_prof = req.profile if isinstance(req.profile, dict) else {}
    target_query = str(req_prof.get("npc_id") or req_prof.get("name") or "").strip()
    if not target_query:
        raise HTTPException(status_code=400, detail="PeerPulse profile identifier required.")
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id) or pre_session
        await ensure_realm_comms_available(session_id, session=session)
        server_profile = await adb(lookup_social_profile, session_id, canonical_id, target_query)
        if not server_profile:
            raise HTTPException(status_code=404, detail=f"No PeerPulse profile found matching '{target_query}'.")

        res = await adb(resolve_social_friend_request, dict(session), canonical_id, server_profile)
        char_row = await adb(db.get_character, canonical_id, session_id=session_id)
        if not char_row:
            char_row = await adb(db.get_character, canonical_id)
        char_id = char_row.get("id", 0) if char_row else 0
        contacts = await _get_contacts_ro(session_id, char_id)
        party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    from mechanics.social.relationships import (
        can_player_dm_contact,
        collect_met_npc_names,
        is_contact_blocked,
        is_unlocked_contact,
    )

    met_names = collect_met_npc_names(session, party_npcs=party_npcs)
    unlocked_contacts = []
    phone_fow_loaded = False
    phone_fow_ctx = None
    for c in contacts:
        if is_unlocked_contact(c, party_names, met_in_story_names=met_names) and can_player_dm_contact(
            c, party_names=party_names, scenario=str((session or {}).get("scenario") or "fantasy")
        ):
            uc_copy = dict(c)
            _uc_bi = uc_copy.get("basic_info")
            if isinstance(_uc_bi, str) and _uc_bi.strip():
                try:
                    _uc_bi = json.loads(_uc_bi)
                except Exception:
                    _uc_bi = {}
            uc_bi_dict = _uc_bi if isinstance(_uc_bi, dict) else {}
            uc_copy["spirit_relay_unlocked"] = has_spirit_relay_contact(uc_copy)
            uc_copy["folklore_village"] = str(uc_bi_dict.get("folklore_village") or "")
            uc_copy["is_blocked_contact"] = is_contact_blocked(uc_copy)
            uc_copy["can_dm"] = True
            if not uc_copy.get("debug_revealed"):
                if not phone_fow_loaded:
                    phone_fow_loaded = True
                    ph_uid = int(req.user_id or 0)
                    ph_set = await adb(db.get_settings, ph_uid) if ph_uid else {}
                    ph_dbg = bool((ph_set or {}).get("debug_reveal_all_info", 0))
                    ph_cid = int(char_id or 0)
                    phone_fow_ctx = (
                        None
                        if ph_dbg
                        else await adb(
                            _preload_fog_of_war_context,
                            session_id,
                            ph_cid,
                            party_names,
                            str((ph_set or {}).get("ui_language") or "en"),
                            None,
                            party_npcs,
                            str((session or {}).get("scenario") or "fantasy"),
                            session if isinstance(session, dict) else None,
                            char_row if isinstance(char_row, dict) else None,
                            int(ph_uid or 0),
                        )
                    )
                if isinstance(phone_fow_ctx, dict):
                    from mechanics.social.consequences import apply_fog_of_war_to_enriched_contact as _apply_ph_fow
                    from scenario_data import is_nsfw_scenario as _is_nsfw_ph

                    cn_ph = db.canon_social_npc_id(uc_copy.get("npc_id") or uc_copy.get("name") or "")
                    uc_copy = _apply_ph_fow(
                        uc_copy,
                        session_id=session_id,
                        character_id=phone_fow_ctx.get("character_id", 0),
                        preloaded_discoveries=(phone_fow_ctx.get("disc_by_npc") or {}).get(cn_ph, []),
                        lang=phone_fow_ctx.get("lang", "en"),
                        party_npc_keys=phone_fow_ctx.get("party_npc_keys"),
                        kin_npc_keys=phone_fow_ctx.get("kin_npc_keys"),
                        romantic_npc_keys=phone_fow_ctx.get("romantic_npc_keys"),
                        is_nsfw=(
                            _is_nsfw_ph(str((session or {}).get("scenario") or "fantasy"))
                            or ("nsfw" in str((session or {}).get("tags") or "").lower())
                        ),
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
    await ensure_realm_comms_available(session_id, session=session)
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
    pre_sess_dm, eff_uid = await verify_session_participant(request, session_id, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)
    text = (req.message or "").strip()
    if (not text or text == "__auto__") and not req.intent:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    norm_target_id = str(npc_id or "").strip().lower().replace(" ", "_")
    if norm_target_id == "metropolitan_anomaly_watch" or norm_target_id.endswith("_dispatch"):
        raise HTTPException(
            status_code=400,
            detail="Automated dispatch channels are read-only broadcast feeds and do not accept replies.",
        )

    async with distributed_adventure_lock(canonical_id, session_id):
        session_row = await adb(db.get_session, session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        session = dict(session_row)
        comms_dm = await ensure_realm_comms_available(session_id, session=session, allow_spirit_relay=True)

        char_row = await adb(db.get_character, canonical_id, session_id=session_id)
        if not char_row:
            raise HTTPException(status_code=404, detail="Character not found")
        player_char = dict(char_row)

        contact = await adb(db.get_contact, session_id, npc_id, character_id=player_char.get("id", 0))
        if not contact:
            all_contacts = await _get_contacts_ro(session_id, int(player_char.get("id") or 0))
            for c in all_contacts:
                if c.get("npc_id") == npc_id or c.get("name", "").lower().replace(" ", "_") == npc_id.lower():
                    contact = dict(c)
                    break
        if not contact:
            wr_match = await adb(db.get_world_roster_npc, session_id, npc_id, include_legacy_rosters=False)
            if wr_match:
                wr_b = dict(wr_match.get("basic_info") or {})
                wr_b.setdefault("has_contact_info", False)
                contact = {
                    "npc_id": wr_match.get("npc_id") or npc_id,
                    "name": wr_match.get("name") or npc_id.replace("_", " ").title(),
                    "role": wr_match.get("role") or wr_b.get("role") or "",
                    "relationship_score": int(wr_match.get("affinity_score") or 0),
                    "track": "platonic",
                    "basic_info": wr_b,
                    "session_id": session_id,
                }
        if not contact:
            contact = {
                "npc_id": npc_id,
                "name": npc_id.replace("_", " ").title(),
                "relationship_score": 0,
                "track": "platonic",
                "basic_info": {},
                "session_id": session_id,
            }

        from mechanics.social.relationships import (
            can_player_dm_contact,
            is_contact_blocked,
            is_contact_eligible,
            is_promoted_family_or_cohabitant,
        )

        scen_key = str(session.get("scenario") or "")
        party_npcs_dm = await adb(db.get_session_party_npcs, session_id)
        party_names_dm = {
            str(p.get("name", "")).strip().lower()
            for p in (party_npcs_dm or [])
            if isinstance(p, dict) and p.get("name")
        }
        c_name_dm = str(contact.get("name") or "").strip().lower()
        in_party_dm = bool(c_name_dm and c_name_dm in party_names_dm)
        is_family_dm = is_promoted_family_or_cohabitant(contact)
        matching_party_dm = next(
            (
                p for p in (party_npcs_dm or [])
                if isinstance(p, dict) and str(p.get("name") or "").strip().lower() == c_name_dm
            ),
            None,
        )
        c_bi_dm = contact.get("basic_info") if isinstance(contact.get("basic_info"), dict) else {}
        is_summon_dm = bool(
            contact.get("is_summon")
            or contact.get("spirit_court")
            or c_bi_dm.get("is_summon")
            or c_bi_dm.get("spirit_court")
            or (
                matching_party_dm
                and (matching_party_dm.get("is_summon") or matching_party_dm.get("spirit_court"))
            )
        )
        if is_summon_dm or (
            (not is_family_dm and not in_party_dm)
            and not is_contact_eligible(contact, scenario=scen_key, session_id=session_id)
        ):
            raise HTTPException(
                status_code=403,
                detail=f"{contact.get('name', 'This entity')} is not eligible as a personal phone contact in this scenario.",
            )
        if isinstance(contact, dict) and (
            contact.get("is_dispatch_channel")
            or (isinstance(contact.get("basic_info"), dict) and contact["basic_info"].get("is_dispatch_channel"))
        ):
            raise HTTPException(
                status_code=400,
                detail="Automated dispatch channels are read-only broadcast feeds and do not accept replies.",
            )
        if is_contact_blocked(contact):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{contact.get('name', 'This contact')} has blocked your number due to hostility. "
                    "Reconcile with them in person first."
                ),
            )

        if isinstance(contact, dict) and (
            contact.get("deceased")
            or (isinstance(contact.get("basic_info"), dict) and contact["basic_info"].get("deceased"))
        ):
            raise HTTPException(
                status_code=400,
                detail=f"{contact.get('name', 'This contact')}'s line is disconnected — they perished during an anomaly breach.",
            )

        if not can_player_dm_contact(contact, party_names=party_names_dm, scenario=scen_key):
            raise HTTPException(
                status_code=403,
                detail="You don't have their contact info yet. Exchange phone numbers or connect on PeerPulse first.",
            )

        if not comms_dm.get("available"):
            if not has_spirit_relay_contact(contact):
                dm_realm_label = str(comms_dm.get("realm_name") or "this realm")
                raise HTTPException(
                    status_code=403,
                    detail=f"No mortal signal — only befriended Spirit Relay or met Ossuary contacts can receive messages from {dm_realm_label}.",
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
            intent=intent,
        )

        raw_ids = (reply_data.get("digital_item_ids") if isinstance(reply_data, dict) else None) or (
            [reply_data["digital_item_id"]]
            if isinstance(reply_data, dict) and reply_data.get("digital_item_id")
            else []
        )
        media_owner_uid = int(player_char.get("user_id") or canonical_id)
        if raw_ids and is_session_image_gen_enabled(session, auto_only=True):
            for d_id in raw_ids:
                await adb(
                    update_digital_media_image,
                    int(d_id),
                    media_owner_uid,
                    image_status="generating",
                )
                spawn_phone_media_image_task(
                    session_id,
                    media_owner_uid,
                    int(d_id),
                    auto_trigger=True,
                    broadcast_fn=lambda payload, _sid=session_id: manager.broadcast(_sid, payload),
                )
            if isinstance(reply_data.get("media_dropped"), dict):
                reply_data["media_dropped"]["image_status"] = "generating"

        messages = await adb(db.get_phone_messages, session_id, contact.get("npc_id", npc_id), limit=20)
        dm_lang = str(session.get("narration_language") or session.get("language") or "en")
        dm_static_active = await adb(is_spirit_relay_static_active, session_id)
        dm_static_note = await adb(get_spirit_relay_static_note, session_id, dm_lang) if dm_static_active else ""
        return {
            "success": True,
            "generated_message": text,
            "reply": reply_data,
            "messages": [dict(m) for m in messages],
            "daily_limits": reply_data.get("daily_limits"),
            "spirit_relay_static_active": bool(dm_static_active),
            "spirit_relay_static_note": dm_static_note,
        }


@router.post("/api/phone/{session_id}/media/{item_id}/generate")
async def generate_phone_media(
    session_id: int,
    item_id: int,
    req: PhoneMediaGenerateRequest,
    request: Request = None,
):
    """Generates or regenerates an AI portrait image for a digital media item in Photo Vault."""
    session, eff_uid = await verify_session_participant(request, session_id, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)
    if not is_session_image_gen_enabled(session, auto_only=False):
        raise HTTPException(status_code=400, detail="Image generation is disabled for this session.")

    char_row = await adb(db.get_character, canonical_id, session_id=session_id)
    media_owner_uid = int(char_row.get("user_id") or canonical_id) if isinstance(char_row, dict) else int(canonical_id)

    res = await generate_phone_media_image(
        session_id,
        media_owner_uid,
        item_id,
        auto_trigger=False,
        force_regenerate=bool(req.force_regenerate),
        broadcast_fn=lambda payload: manager.broadcast(session_id, payload),
    )
    if res.get("reason") in ("session_not_found", "media_not_found"):
        raise HTTPException(status_code=404, detail=res.get("error") or "Media item not found.")
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("error") or "Image generation failed.")
    return {"success": True, "media": res.get("media")}


@router.post("/api/commitments/{session_id}/{commitment_id}/cancel")
async def cancel_session_commitment(
    session_id: int,
    commitment_id: int,
    req: CancelCommitmentRequest | None = Body(default=None),
    request: Request = None,
):
    """Cancels an active rendezvous or commitment in commitments_ledger without flake penalty."""
    from mechanics.system import commitments_engine

    pre_session, _ = await verify_session_participant(request, session_id, req.user_id if req else None)
    reason = (req.reason if req and req.reason else "player_cancelled").strip()
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id) or pre_session
        await ensure_realm_comms_available(session_id, session=session)

        cancelled = await adb(
            commitments_engine.cancel_commitment,
            session_id,
            commitment_id,
            reason=reason,
            cancelled_by="player",
        )
        if not cancelled:
            raise HTTPException(status_code=404, detail="Commitment not found or already resolved")

        contacts = await _get_contacts_ro(session_id)
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
