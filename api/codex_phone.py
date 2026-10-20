from fastapi import APIRouter, HTTPException, Query
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
        "role": basic_info.get("role") or basic_info.get("occupation") or matched_contact.get("role") or "Companion",
        "hp": 45,
        "max_hp": 45,
        "mp": 25,
        "max_mp": 25,
        "relationship_score": score,
    }
    added = await adb(db.add_session_party_npc, req.session_id, npc_payload)
    if not added:
        raise HTTPException(status_code=400, detail=f"Could not add {npc_name} to party (party full or already recruited).")

    # Per contact rule 1b: Recruited party members automatically enter Contacts list
    existing_in_contacts = any((c.get("name") or "").strip().lower() == npc_name.lower() for c in contacts)
    delta_to_apply = 0 if existing_in_contacts else score
    c_app = matched_contact.get("appearance") or matched_contact.get("appearance_json")
    if isinstance(c_app, str):
        try:
            import json
            c_app = json.loads(c_app)
        except Exception:
            c_app = {}
    await adb(
        db.upsert_contact,
        session_id=req.session_id,
        character_id=char_id,
        npc_id=npc_payload["npc_id"],
        name=npc_payload["name"],
        basic_info=basic_info if basic_info else {"role": npc_payload["role"]},
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

    # Only include NPCs encountered in person (current scene, turn history)
    met_in_story_names = set(party_names)
    for n in curr_npcs:
        if isinstance(n, dict) and n.get("name"):
            met_in_story_names.add(str(n["name"]).lower().strip())
        elif isinstance(n, str) and n.strip():
            met_in_story_names.add(str(n).lower().strip())
    if dialogue_partner:
        met_in_story_names.add(str(dialogue_partner).lower().strip())
    for dp_item in (session.get("dialogue_partners") or []):
        if dp_item:
            met_in_story_names.add(str(dp_item).lower().strip())

    # Include all NPCs encountered across session turn history (witnesses, dialogue partners, present NPCs)
    for h in (session.get("history") or []):
        if not isinstance(h, dict):
            continue
        for w in (h.get("witnessed_by") or []):
            if isinstance(w, str) and w.strip():
                met_in_story_names.add(w.strip().lower())
        hist_dp = h.get("dialogue_partner")
        if hist_dp and isinstance(hist_dp, str) and hist_dp.strip():
            met_in_story_names.add(hist_dp.strip().lower())
        for ru in (h.get("relationship_updates") or []):
            if isinstance(ru, dict) and ru.get("npc_name"):
                met_in_story_names.add(str(ru["npc_name"]).strip().lower())
        for n in (h.get("current_npcs") or h.get("present_npcs") or []):
            if isinstance(n, dict) and n.get("name"):
                met_in_story_names.add(str(n["name"]).strip().lower())
            elif isinstance(n, str) and n.strip():
                met_in_story_names.add(str(n).strip().lower())

    if player_char_name:
        met_in_story_names.discard(player_char_name)

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

                    # A character is strictly discovered if met in person (including past turns via last_in_person_ts or story lore), has active affinity, or is an unlocked contact
                    from mechanics.social.relationships import is_unlocked_contact
                    has_last_in_person = bool(c and (c.get("last_in_person_ts") or (c.get("basic_info") or {}).get("last_in_person_ts")))
                    is_custom_story_lore = bool(
                        not it_dict.get("faction")
                        and (
                            it_dict.get("mannerisms")
                            or it_dict.get("motivation")
                            or (isinstance(it_dict.get("appearance"), dict) and it_dict["appearance"].get("distinctive_features"))
                        )
                    )
                    is_discovered = bool(
                        debug_reveal_all
                        or p_name in met_in_story_names
                        or score != 0
                        or (c is not None and is_unlocked_contact(c, party_names))
                        or has_last_in_person
                        or is_custom_story_lore
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
                    it_dict["is_contact"] = bool(c is not None)

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
            from mechanics.social.relationships import is_unlocked_contact
            is_discovered_c = bool(
                debug_reveal_all
                or c_name_lower in met_in_story_names
                or score != 0
                or is_unlocked_contact(c, party_names)
                or bool(c.get("last_in_person_ts") or (c.get("basic_info") or {}).get("last_in_person_ts"))
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
            p_dict["is_contact"] = True

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
        "commitments": [dict(c) for c in (commitments or [])],
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
    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await adb(db.get_contacts, session_id, char_id)
    if not contacts and lookup_uid and char_id != lookup_uid:
        contacts = await adb(db.get_contacts, session_id, lookup_uid)
    enriched_contacts = await adb(
        lambda: [_enrich_contact_record(c, session_id, scen_key, debug_reveal_all, phys_st=phys_st) for c in contacts]
    )
    from scenario_data import is_nsfw_scenario
    from mechanics.social.relationships import is_unlocked_contact
    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    unlocked_contacts = [c for c in enriched_contacts if is_unlocked_contact(c, party_names)]
    return {
        "contacts": unlocked_contacts,
        "is_nsfw": is_nsfw_scenario(scen_key),
        "scenario": scen_key
    }


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
    inv = await adb(db.get_inventory, user_id)
    is_supported = True

    branding = get_phone_branding(scen_key)
    pending_appts = await adb(db.get_phone_appointments, session_id, status="pending")
    arrived_appts = await adb(db.get_phone_appointments, session_id, status="arrived")
    appointments = (pending_appts or []) + (arrived_appts or [])
    gossip = await adb(db.get_gossip_feed, session_id, limit=15)
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
    from mechanics.social.relationships import is_unlocked_contact
    unlocked_contacts = [dict(c) for c in contacts if is_unlocked_contact(c, party_names)]
    suggested_peers = await adb(get_suggested_peers, session_id, user_id)

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
        "appointments": [dict(a) for a in appointments],
        "gossip_feed": [dict(g) for g in gossip],
        "media_gallery": digital_media,
        "contacts": unlocked_contacts,
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


@router.get("/api/phone/{session_id}/peerpulse/suggestions")
async def get_peerpulse_suggestions(session_id: int, user_id: int = Query(...)):
    """Fetches suggested student peers for PeerPulse Graph."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    suggestions = await adb(get_suggested_peers, session_id, user_id)
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
        "messages": [dict(m) for m in messages],
        "daily_limits": reply_data.get("daily_limits"),
    }

