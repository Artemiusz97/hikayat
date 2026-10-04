from fastapi import APIRouter, HTTPException, Query

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
        party_npcs = await adb(db.get_session_party_npcs, req.session_id)
        return {
            "success": True,
            "status": "dismissed",
            "action": "dismissed",
            "npc_name": npc_name,
            "message": f"{npc_name} has left your party.",
            "party_npcs": party_npcs,
        }

    # Recruit flow: enforce 2-companion cap & Friend+ affinity threshold (>= 15)
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
    score = int((matched_contact or {}).get("relationship_score", 0) or 0)
    if score < 15:
        raise HTTPException(
            status_code=400,
            detail=f"{npc_name} requires at least Friend standing (+15 affinity, currently {score}) to join your party."
        )

    basic_info = (matched_contact or {}).get("basic_info") or {}
    npc_payload = {
        "name": (matched_contact or {}).get("name") or npc_name,
        "npc_id": (matched_contact or {}).get("npc_id") or npc_name.lower().replace(" ", "_"),
        "role": basic_info.get("role") or basic_info.get("occupation") or "Companion",
        "hp": 45,
        "max_hp": 45,
        "mp": 25,
        "max_mp": 25,
        "relationship_score": score,
    }
    added = await adb(db.add_session_party_npc, req.session_id, npc_payload)
    if not added:
        raise HTTPException(status_code=400, detail=f"Could not add {npc_name} to party (party full or already recruited).")

    party_npcs = await adb(db.get_session_party_npcs, req.session_id)
    return {
        "success": True,
        "status": "recruited",
        "action": "recruited",
        "npc_name": npc_payload["name"],
        "message": f"{npc_payload['name']} joined your party!",
        "party_npcs": party_npcs,
    }


@router.get("/api/lorebook/{session_id}")
async def get_lorebook(session_id: int):
    """Fetches all lorebook entities (places, people, factions) grouped by category."""
    grouped = await adb(db.get_lorebook, session_id)
    commitments = await adb(db.get_active_commitments, session_id)
    all_entities = []
    if isinstance(grouped, dict):
        for cat, items in grouped.items():
            for it in items:
                all_entities.append(dict(it))
    return {
        "categories": grouped,
        "entities": all_entities,
        "commitments": [dict(c) for c in (commitments or [])],
    }


def _enrich_contact_record(c_raw: dict, session_id: int, scen_key: str, debug_reveal_all: bool) -> dict:
    c = dict(c_raw)
    score = int(c.get("relationship_score", 0) or 0)
    if debug_reveal_all:
        info_level = 3
    elif hasattr(mechanics.social.persona, "get_contact_info_level"):
        info_level = mechanics.social.persona.get_contact_info_level(c)
    else:
        info_level = mechanics.social.relationships.get_unlocked_info_level(score)

    skill_modifier = mechanics.social.relationships.get_relationship_modifier(score)
    dislikes = c.get("dislikes")
    if not dislikes:
        try:
            _, dislikes = mechanics.social.persona.categorize_likes_and_dislikes(
                c.get("preferences") or [], traits=c.get("unlocked_traits") or []
            )
        except Exception:
            dislikes = []

    family_tree = c.get("family_tree")
    if not family_tree:
        try:
            family_tree = mechanics.social.genealogy.get_or_generate_family_tree(session_id, c)
        except TypeError:
            family_tree = _default_get_or_generate_family_tree(session_id, c, scen_key)
        except Exception:
            family_tree = (c.get("relations") or {}).get("family") or []

    app = dict(c.get("appearance") or {})
    app["intimate_memories"] = list(c.get("intimate_memories", []))
    from mechanics.social.persona import enforce_intimacy_safeguard_invariants
    app = enforce_intimacy_safeguard_invariants(app)

    i_exp = str(app.get("intercourse_experience") or app.get("virginity_intercourse") or "virgin").strip().lower()
    had_first_time = bool(app.get("had_first_time_with_player")) and (i_exp == "non_virgin")
    past_history = c.get("past_intimate_history") or app.get("past_intimate_history") or app.get("past_intimate_entries")
    if not past_history and c.get("intimate_memories"):
        past_mems = [str(m).replace("Past History:", "").strip() for m in c.get("intimate_memories") if str(m).startswith("Past History:")]
        if past_mems:
            past_history = past_mems

    is_virgin_shared = False
    if isinstance(past_history, list) and past_history:
        is_virgin_shared = any("shared first time with you" in str(p) for p in past_history)
    elif isinstance(past_history, str):
        is_virgin_shared = "shared first time with you" in past_history

    if had_first_time:
        past_history = ["Virgin (No prior intimate history before meeting you; shared first time with you)"]
    elif not past_history or (is_virgin_shared and not had_first_time):
        try:
            name_str = str(c.get("name") or c.get("npc_id") or "npc").strip()
            import hashlib
            hash_val = int(hashlib.md5(f"{name_str}_past_history".encode("utf-8")).hexdigest(), 16)
            c_race = str(c.get("race") or app.get("race") or "")
            c_gender = str(c.get("gender") or app.get("gender") or "female")
            i_exp = str(app.get("intercourse_experience") or app.get("virginity_intercourse") or "virgin").strip().lower()
            o_exp = str(app.get("oral_experience") or app.get("virginity_oral") or "inexperienced").strip().lower()
            m_exp = str(app.get("manual_experience") or app.get("virginity_manual") or "inexperienced").strip().lower()
            open_val = str(app.get("erotic_openness") or app.get("openness") or "moderate")
            pred_i = str(app.get("predetermined_intercourse") or "").strip().lower()

            if (i_exp in ("virgin", "inexperienced", "") or pred_i == "virgin") and o_exp in ("inexperienced", "unknown", "") and m_exp in ("inexperienced", "unknown", ""):
                past_history = ["Virgin (No prior intimate history before meeting you)"]
            else:
                past_data = mechanics.social.persona.generate_past_intimate_history(
                    hash_val=hash_val,
                    race=c_race,
                    gender=c_gender,
                    scenario=scen_key,
                    openness=open_val,
                    intercourse=i_exp,
                    oral=o_exp,
                    manual=m_exp,
                )
                if past_data and past_data.get("entries"):
                    past_history = [str(e).replace("Past History:", "").strip() for e in past_data["entries"]]
                elif past_data and past_data.get("entry"):
                    past_history = [str(past_data["entry"]).replace("Past History:", "").strip()]
                else:
                    past_history = []
                # Persist generated past history as canonical memory entries so they stabilize across calls
                if past_history:
                    try:
                        import db as _db
                        sess_id = c.get("session_id", 0)
                        char_id = c.get("character_id", 0)
                        npc_id = c.get("npc_id") or name_str
                        for ph_entry in past_history:
                            mem_str = f"Past History: {ph_entry}"
                            _db.upsert_contact(
                                session_id=sess_id,
                                character_id=char_id,
                                npc_id=npc_id,
                                name=name_str,
                                new_memory=mem_str,
                            )
                    except Exception:
                        pass
        except Exception:
            past_history = []

    # Enrich appearance for Web Codex / Phone display
    intimate_unlocked = (info_level >= 3) or c.get("intimate_revealed", False) or c.get("all_revealed", False) or app.get("intimate_revealed", False)
    i_rev = intimate_unlocked or c.get("intercourse_revealed", False) or app.get("intercourse_revealed", False)
    o_rev = intimate_unlocked or c.get("oral_revealed", False) or app.get("oral_revealed", False) or i_rev
    m_rev = intimate_unlocked or c.get("manual_revealed", False) or app.get("manual_revealed", False) or i_rev

    i_state = str(app.get("intercourse_experience") or "virgin").strip().lower()
    exp_disp = ("Virgin" if i_state == "virgin" else "Non-Virgin") if i_rev else "Unknown"
    app["experience"] = exp_disp

    from mechanics.social.persona import is_valid_persona_attribute_string
    if not is_valid_persona_attribute_string(app.get("erotic_openness")):
        app["erotic_openness"] = app.get("openness") if is_valid_persona_attribute_string(app.get("openness")) else ""
    if not is_valid_persona_attribute_string(app.get("intimate_dynamic")):
        app["intimate_dynamic"] = app.get("dynamic") if is_valid_persona_attribute_string(app.get("dynamic")) else ""
    if not is_valid_persona_attribute_string(app.get("intimate_demeanor")):
        app["intimate_demeanor"] = app.get("demeanor") if is_valid_persona_attribute_string(app.get("demeanor")) else ""

    raw_g = str(c.get("gender") or app.get("gender") or "female").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    oral_state = str(app.get("oral_experience") or "unknown").strip().lower()
    oral_map = {
        "inexperienced": "Inexperienced",
        "has_done_oral": "Has Performed",
        "has_received_oral": "Has Received",
        "has_done_and_received_oral": "Has Performed & Received"
    }
    oral_disp = "Unknown"
    if o_rev and oral_state != "unknown":
        oral_disp = oral_map.get(oral_state, "Inexperienced")

    manual_state = str(app.get("manual_experience") or "unknown").strip().lower()
    man_map = {
        "inexperienced": "Inexperienced",
        "has_done_manual": "Has Given",
        "has_received_manual": "Has Received",
        "has_done_and_received_manual": "Has Given & Received"
    }
    man_disp = "Unknown"
    if m_rev and manual_state != "unknown":
        man_disp = man_map.get(manual_state, "Inexperienced")

    if is_male:
        p_size = str(app.get("penis_size") or "average").title()
        p_size_disp = p_size if intimate_unlocked else "Unknown"
        app["anatomy"] = f"Penis Size: {p_size_disp} • Intercourse: {exp_disp} • Oral: {oral_disp} • Manual: {man_disp}"
    else:
        b_size = str(app.get("breast_size") or "Modest B-Cup").title()
        b_size_disp = b_size if intimate_unlocked else "Unknown"
        app["anatomy"] = f"Breast Size: {b_size_disp} • Intercourse: {exp_disp} • Oral: {oral_disp} • Manual: {man_disp}"

    if isinstance(app.get("undergarments"), dict):
        under_d = app.get("undergarments")
        bra_str = under_d.get("bra", "")
        und_str = under_d.get("underwear", "")
        if bra_str and und_str:
            app["undergarments"] = f"Bra: {bra_str} • Underwear: {und_str}"
        elif bra_str:
            app["undergarments"] = f"Bra: {bra_str}"
        elif und_str:
            app["undergarments"] = f"Underwear: {und_str}"
    elif not app.get("undergarments") and (app.get("bra") or app.get("underwear")):
        bra_str = app.get("bra", "")
        und_str = app.get("underwear", "")
        if bra_str and und_str:
            app["undergarments"] = f"Bra: {bra_str} • Underwear: {und_str}"
        elif bra_str:
            app["undergarments"] = f"Bra: {bra_str}"
        elif und_str:
            app["undergarments"] = f"Underwear: {und_str}"

    from mechanics.social.persona import clean_attribute_list_string

    t_rev = intimate_unlocked or c.get("turn_ons_revealed", False) or app.get("turn_ons_revealed", False)
    if not t_rev:
        app["turn_ons"] = []
    else:
        t_cleaned = clean_attribute_list_string(app.get("turn_ons"))
        if t_cleaned:
            app["turn_ons"] = [t.strip() for t in t_cleaned.split(",") if t.strip() and t.strip().lower() not in ("none", "unknown")]

    s_rev = intimate_unlocked or c.get("sensitive_spots_revealed", False) or app.get("sensitive_spots_revealed", False)
    if not s_rev:
        app["erogenous_zones"] = []
        app["sensitive_spots"] = ""
    else:
        s_cleaned = clean_attribute_list_string(app.get("sensitive_spots"))
        if s_cleaned:
            app["erogenous_zones"] = [s.strip() for s in s_cleaned.split(",") if s.strip() and s.strip().lower() not in ("none", "unknown")]
        elif not app.get("erogenous_zones") and app.get("sensitive_spots"):
            app["erogenous_zones"] = list(app.get("sensitive_spots"))

    f_rev = intimate_unlocked or c.get("fetishes_revealed", False) or app.get("fetishes_revealed", False)
    if not f_rev:
        app["kinks"] = []
        app["fetishes"] = ""
    else:
        f_cleaned = clean_attribute_list_string(app.get("fetishes") or app.get("kinks"))
        if f_cleaned and f_cleaned.lower() not in ("none", "none (vanilla)", "unknown", ""):
            app["kinks"] = [f.strip() for f in f_cleaned.split(",") if f.strip() and f.strip().lower() not in ("none", "none (vanilla)", "unknown")]

    pref_rev = intimate_unlocked or c.get("act_preferences_revealed", False) or app.get("act_preferences_revealed", False)
    if not pref_rev:
        app["favorite_acts"] = []
        app["act_likes"] = ""
        app["disliked_acts"] = []
        app["act_dislikes"] = ""
    else:
        likes_cleaned = clean_attribute_list_string(app.get("act_likes") or app.get("favorite_acts"))
        if likes_cleaned and likes_cleaned.lower() not in ("none", "unknown", ""):
            app["favorite_acts"] = [l.strip() for l in likes_cleaned.split(",") if l.strip() and l.strip().lower() not in ("none", "unknown")]

        dislikes_cleaned = clean_attribute_list_string(app.get("act_dislikes") or app.get("disliked_acts"))
        if dislikes_cleaned and dislikes_cleaned.lower() not in ("none", "unknown", ""):
            app["disliked_acts"] = [d.strip() for d in dislikes_cleaned.split(",") if d.strip() and d.strip().lower() not in ("none", "unknown")]

    c["appearance"] = app
    c["info_level"] = info_level
    c["skill_modifier"] = skill_modifier
    c["dislikes"] = dislikes or []
    c["family_tree"] = family_tree if family_tree is not None else []
    if isinstance(past_history, list):
        c["past_intimate_history"] = " • ".join(past_history)
        c["past_intimate_entries"] = past_history
    else:
        c["past_intimate_history"] = str(past_history or "")
        c["past_intimate_entries"] = [str(past_history)] if past_history else []
    return c


@router.get("/api/contacts/{session_id}")
async def get_contacts(session_id: int, user_id: int | None = Query(None)):
    """Fetches NPC contacts and relationship standings."""
    session = await adb(db.get_session, session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    lookup_uid = user_id or session.get("host_user_id") or 0
    settings = await adb(db.get_settings, lookup_uid) if lookup_uid else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))
    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    if not contacts and lookup_uid and char_id != lookup_uid:
        contacts = await adb(db.get_contacts, session_id, lookup_uid)
    enriched_contacts = await adb(
        lambda: [_enrich_contact_record(c, session_id, scen_key, debug_reveal_all) for c in contacts]
    )
    return {"contacts": enriched_contacts}


def _enrich_factions_list(session_id: int, user_id: int | None = None) -> dict:
    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    lookup_uid = user_id or session.get("host_user_id")
    char = db.get_character(lookup_uid) if lookup_uid else None
    membership = {
        "joined_faction_id": (char or {}).get("joined_faction_id") or "",
        "faction_rank": int((char or {}).get("faction_rank") or 0),
        "faction_title": (char or {}).get("faction_title") or "",
    }

    try:
        ensure_starter_factions(session_id, scen_key)
        sync_faction_rosters_with_contacts(session_id)
    except Exception:
        pass

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
        enriched.append(f_dict)

    return {"factions": enriched, "membership": membership}


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

    if action == "join":
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
        if tier["tier_level"] < 2:
            raise HTTPException(
                status_code=400,
                detail="You need Liked standing or higher (+1 Rep) to use the faction safehouse rest."
            )
        await adb(db.apply_hp_mp_delta, req.user_id, char["max_hp"], char["max_mp"], 0)
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
        current_day, current_minute, _ = await adb(db.get_session_time, session_id)
        merchant = session.setdefault("merchant", {})
        faction_key = f"faction_{faction['faction_id']}"
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

        discount = cat_entry.get("discount_pct", 0)
        merchant.update({
            "active": True,
            "active_store_key": faction_key,
            "stock": cat_entry["stock"],
            "discount_pct": discount,
            "is_faction_quartermaster": True,
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
        bounties = await game_engine.generate_faction_bounty_board(session, faction)
        payload = await adb(_enrich_factions_list, session_id, req.user_id)
        return {
            "success": True,
            "action": "bounty",
            "bounties": [dict(b) for b in (bounties or []) if b],
            "message": f"Generated {len(bounties or [])} faction contracts for {faction.get('name', 'Faction')}!",
            **payload,
        }

    if action == "promote":
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
    active_sq = db.get_active_story_quest(session_id)
    if active_sq and active_sq.get("climax_ready"):
        try:
            _, climax_loc = get_story_quest_climax_location(session_id)
            if climax_loc:
                clean_climax = climax_loc.replace(" -> ", " ➔ ")
                active_sq["climax_location"] = clean_climax
                active_sq["target_location"] = clean_climax
        except Exception:
            pass
    clues = [dict(c) for c in db.get_session_clues(session_id) if c]
    available_bounties = [q for q in quests if q.get("status") == "Available"]
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

    action = (req.action or "accept").strip().lower()
    if action == "accept":
        new_status = "Active"
        msg = f"Accepted contract: {quest.get('title', 'Bounty')}!"
    elif action == "abandon":
        new_status = "Abandoned"
        msg = f"Abandoned contract: {quest.get('title', 'Bounty')}."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid bounty action: {req.action}")

    await adb(db.update_quest_status, session_id, req.quest_id, new_status)
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

    scen_key = session.get("scenario", "fantasy")
    is_valid, title, detail_text = evaluate_clue_deduction(clue_a, clue_b, scen_key=scen_key)

    xp_awarded = 0
    if is_valid:
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
    has_phone = scenario_has_smartphone(scen_key)
    inv = await adb(db.get_inventory, user_id)
    has_phone_item = any("phone" in (i.get("name") or "").lower() or "cyberdeck" in (i.get("name") or "").lower() for i in inv)
    is_supported = has_phone or has_phone_item

    branding = get_phone_branding(scen_key) if is_supported else None
    appointments = await adb(db.get_phone_appointments, session_id, status="pending")
    gossip = await adb(db.get_gossip_feed, session_id, limit=15) if is_supported else []
    char_row = await adb(db.get_character, user_id)
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    if not contacts and char_id != user_id:
        contacts = await adb(db.get_contacts, session_id, user_id)
    social_state = await adb(get_social_state_summary, session_id, session) if is_supported else {"charges": 3, "turn_count": 0, "state": {}}

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

    return {
        "is_supported": is_supported,
        "scenario": scen_key,
        "branding": {
            "device_name": branding.get("device_name", "📱 Smartphone") if branding else "📱 Smartphone",
            "os_name": branding.get("os_name", "Mobile OS") if branding else "Mobile OS",
            "feed_app_name": branding.get("feed_app_name", "Feed") if branding else "Feed",
            "dm_app_name": branding.get("dm_app_name", "Messages") if branding else "Messages",
            "gallery_app_name": branding.get("gallery_app_name", "Photos") if branding else "Photos",
            "emoji": branding.get("emoji", "📱") if branding else "📱",
        } if branding else None,
        "appointments": [dict(a) for a in appointments],
        "gossip_feed": [dict(g) for g in gossip],
        "media_gallery": digital_media,
        "contacts": [dict(c) for c in contacts],
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
    return {
        **res,
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
    return {
        "success": True,
        **res,
        "profile": req.profile,
        "contacts": [dict(c) for c in contacts],
    }


@router.get("/api/phone/{session_id}/messages/{npc_id}")
async def get_npc_messages(session_id: int, npc_id: str):
    """Fetches direct message chat history with a specific NPC contact."""
    messages = await adb(db.get_phone_messages, session_id, npc_id, limit=20)
    return {"messages": [dict(m) for m in messages]}


@router.post("/api/phone/{session_id}/messages/{npc_id}")
async def send_npc_message(session_id: int, npc_id: str, req: PhoneMessageRequest):
    """Sends a text message to an NPC contact and generates an immediate contextual reply."""
    text = (req.message or "").strip()
    if (not text or text == "__auto__") and not req.intent:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

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
        "messages": [dict(m) for m in messages]
    }

