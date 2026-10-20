import asyncio
import re
import time
from fastapi import APIRouter, HTTPException

import db
from db import adb
import game_engine
import skill_check
from scenario_data import get_scenario_display_name
from mechanics.social.relationships import is_contact_eligible
from services.turn_service import TurnService
from mechanics.system.concurrency import distributed_session_lock, distributed_user_lock
from .deps import (
    logger,
    manager,
    _serializable_action,
    enrich_choices_with_odds,
    enrich_session_party_members,
    StartAdventureRequest,
    JoinAdventureRequest,
    ActionRequest,
    EndAdventureRequest,
    RetryAdventureRequest,
    RerollImageRequest,
    SaveSlotRequest,
    LoadSlotRequest,
)

router = APIRouter()


def _enrich_session_for_client(session: dict, user_id: int) -> dict:
    """Enriches session payload with odds, party vitals, combat state, formatted time, fallback flags, and categorized combat decks."""
    if not session or not isinstance(session, dict):
        return session

    session = dict(session)
    uid = user_id or session.get("host_user_id") or 0

    from mechanics.combat import is_in_combat
    from mechanics.world.locations import location_has_merchant_shop, is_school_scenario
    in_combat = bool(is_in_combat(session))
    session["is_in_combat"] = in_combat

    raw_choices = session.get("choices") or []
    char = db.get_character(uid) if uid else None
    raw_choices = game_engine.sanitize_and_diversify_choices(
        raw_choices,
        scenario=session.get("scenario", "fantasy"),
        location=session.get("current_location", ""),
        char=dict(char) if char else None,
        dialogue_partner=session.get("dialogue_partner"),
        current_npcs=session.get("current_npcs", []),
        session_id=session.get("id")
    )
    if not in_combat and session.get("id") and session.get("current_location"):
        if not any(isinstance(c, dict) and c.get("is_quest_action") for c in raw_choices):
            try:
                from mechanics.world.waypoints import tag_and_enrich_quest_choices
                raw_choices = tag_and_enrich_quest_choices(
                    raw_choices,
                    session["id"],
                    session.get("current_location", ""),
                    scen_key=session.get("scenario", "fantasy"),
                    char=dict(char) if char else None,
                    dialogue_partner=session.get("dialogue_partner"),
                    current_npcs=session.get("current_npcs", []),
                    allow_fallback=True,
                )
            except Exception:
                pass

    session["choices"] = enrich_choices_with_odds(raw_choices, uid)
    session["party_members"] = enrich_session_party_members(session)

    scen_key_check = session.get("scenario", "fantasy")
    from scenario_data import is_nsfw_scenario, get_scenario_tags, get_scenario_display_name
    session["is_nsfw"] = is_nsfw_scenario(scen_key_check)
    session["scenario_tags"] = get_scenario_tags(scen_key_check)
    session["scenario_display_name"] = get_scenario_display_name(scen_key_check)
    current_loc_check = session.get("current_location") or ""
    merchant_state = session.get("merchant") or {}
    is_school = is_school_scenario(scen_key_check)
    has_shop_loc = location_has_merchant_shop(current_loc_check, scen_key=scen_key_check)

    merchant_npc_name = None
    merchant_role_keywords = (
        "merchant", "shopkeeper", "vendor", "trader", "peddler", "blacksmith",
        "weaponsmith", "armorer", "apothecary", "alchemist", "herbalist",
        "quartermaster", "innkeeper", "barkeep", "bartender", "barista", "baker",
        "grocer", "jeweler", "tailor", "clothier", "bookseller",
    )
    for npc in (session.get("current_npcs") or []):
        if isinstance(npc, dict):
            n_role = str(npc.get("role") or npc.get("occupation") or "").lower()
            n_name = str(npc.get("name") or "").strip()
            if any(k in n_role for k in merchant_role_keywords) or any(
                k in n_name.lower() for k in ("merchant", "shopkeeper", "vendor", "trader", "blacksmith", "apothecary")
            ):
                merchant_npc_name = n_name
                break
        elif isinstance(npc, str):
            if any(k in npc.lower() for k in ("merchant", "shopkeeper", "vendor", "trader", "blacksmith", "apothecary")):
                merchant_npc_name = npc.strip()
                break

    show_merchant = False
    merchant_label = "Talk to Merchant"
    if not in_combat:
        if is_school:
            if has_shop_loc:
                show_merchant = True
                merchant_label = "Visit Shop / Café"
        else:
            if merchant_state.get("available") or merchant_state.get("active") or has_shop_loc or merchant_npc_name:
                show_merchant = True
                flavor_name = (
                    (merchant_state.get("flavor_name") if (merchant_state.get("available") or merchant_state.get("active")) else None)
                    or merchant_npc_name
                )
                if has_shop_loc and not flavor_name:
                    merchant_label = "Visit Market / Shop"
                elif flavor_name:
                    merchant_label = f"Trade with {flavor_name}"
                else:
                    merchant_label = "Talk to Merchant"

    session["merchant_available"] = show_merchant
    session["merchant_action_label"] = merchant_label

    day = int(session.get("current_day", 1) or 1)
    minute = int(session.get("current_minute", 480) or 480)
    session["formatted_time"] = f"Day {day} • {(minute // 60) % 24:02d}:{minute % 60:02d}"

    narr_lower = str(session.get("narrative") or "").lower()
    has_fallback_choice = any(
        isinstance(c, dict) and c.get("is_fallback")
        for c in (session.get("choices") or [])
    )

    # Also inspect latest history entry for fallback markers
    hist = session.get("history") or []
    last_hist_narr = ""
    last_hist_is_fallback = False
    if hist and isinstance(hist[-1], dict):
        last_hist_narr = str(
            hist[-1].get("outcome_narrative")
            or hist[-1].get("narrative")
            or ""
        ).lower()
        last_hist_is_fallback = bool(
            hist[-1].get("is_fallback")
            or hist[-1].get("_is_fallback_narrative")
        )

    fallback_keywords = (
        "threads of fate shimmer",
        "temporary fallback",
        "fallback generation",
        "llm connection failed",
        "deliberate intent",
        "carefully observe the surroundings",
    )
    has_fallback_narrative = any(
        phrase in narr_lower or phrase in last_hist_narr
        for phrase in fallback_keywords
    )
    session["is_fallback_generation"] = bool(
        session.get("is_fallback_generation")
        or last_hist_is_fallback
        or has_fallback_choice
        or has_fallback_narrative
    )

    # Heuristic truncation detection:
    # Flag turns where prose is unusually brief (< 180 chars with <= 1 sentence)
    # or ended abruptly without terminal punctuation, on turns with prior history.
    narr_clean = str(session.get("narrative") or "").strip()
    is_truncated = False
    if narr_clean and len(hist) > 0 and not session["is_fallback_generation"]:
        sentences = [s for s in re.split(r'[.!?]+', narr_clean) if s.strip()]
        if len(narr_clean) < 180 and len(sentences) <= 1:
            is_truncated = True
        elif len(narr_clean) >= 20 and narr_clean[-1] not in ('.', '!', '?', '"', "'", '”', '’'):
            is_truncated = True
    session["is_truncated_generation"] = bool(session.get("is_truncated_generation") or is_truncated)

    if in_combat and uid:
        from mechanics.narrative.choice_generator import generate_categorized_combat_actions
        from mechanics.combat.spells import get_spell

        char = db.get_character(uid)
        inv = db.get_inventory(uid) if char else []
        party = [(dict(char), inv)] if char else []
        learned_sids = db.get_learned_spells(uid) if char else []
        location = session.get("current_location") or "area"
        scen_key = session.get("scenario") or "fantasy"

        decks_by_target = {}
        first_deck = None
        enemies = session.get("nearby_enemies") or []

        for enemy in enemies:
            if not isinstance(enemy, dict):
                continue
            if int(enemy.get("hp", 1) or 0) <= 0:
                continue
            enemy_name = (enemy.get("name") or "Enemy").strip()
            raw_deck = generate_categorized_combat_actions(
                party=party,
                monster=enemy,
                location=location,
                scenario=scen_key,
            ) or {}

            magic_list = list(raw_deck.get("magic") or [])
            existing_sids = {m.get("spell_id") for m in magic_list if isinstance(m, dict) and m.get("spell_id")}
            for sid in (learned_sids or []):
                if sid not in existing_sids:
                    sp = get_spell(sid)
                    if sp:
                        mp_cost = int(sp.get("mp_cost", 6) or 0)
                        magic_list.append({
                            "label": f"{sp.get('emoji', '🔮')} {sp.get('name', sid)} ({mp_cost} MP)",
                            "stat": "INT",
                            "requirement": 5,
                            "mp_cost": mp_cost,
                            "choice_type": "combat",
                            "action_category": "magic",
                            "spell_id": sid,
                            "combat_target": enemy_name,
                        })
                        existing_sids.add(sid)

            attacks = enrich_choices_with_odds(raw_deck.get("attacks") or [], uid)
            magic = enrich_choices_with_odds(magic_list, uid)
            tactics = enrich_choices_with_odds(raw_deck.get("tactics") or [], uid)
            for lst in (attacks, magic, tactics):
                for item in lst:
                    if isinstance(item, dict) and not item.get("combat_target"):
                        item["combat_target"] = enemy_name

            raw_flee = raw_deck.get("flee")
            if isinstance(raw_flee, dict):
                flee_enriched = enrich_choices_with_odds([raw_flee], uid)[0]
            else:
                flee_enriched = raw_flee

            deck_entry = {
                "attacks": attacks,
                "spells": magic,
                "tactics": tactics,
                "flee": flee_enriched,
                "weapon_name": raw_deck.get("weapon_name", "Unarmed"),
                "target": enemy_name,
            }
            decks_by_target[enemy_name] = deck_entry
            if first_deck is None:
                first_deck = deck_entry

        session["combat_decks_by_target"] = decks_by_target
        session["combat_deck"] = first_deck
    else:
        session["combat_decks_by_target"] = {}
        session["combat_deck"] = None

    # Dynamic Clothing Status & Present NPC Enrichment
    try:
        import character_data as cd
        from mechanics.social.physical_state import compute_clothing_summary_badge, _match_actor_key, find_player_actor_key
        phys_st = db.get_session_physical_state(session.get("id")) if session.get("id") else None
        phys_actors = (phys_st.get("actors") or {}) if isinstance(phys_st, dict) else {}

        # 1. Player character clothing status
        sess_char = session.get("character") if isinstance(session.get("character"), dict) else {}
        char_dict = dict(char) if char else sess_char
        char_name = char_dict.get("name") if isinstance(char_dict, dict) else ""
        matched_p_key = find_player_actor_key(phys_actors, party=[(char_dict, [])], session_id=session.get("id")) or (_match_actor_key(char_name, phys_actors) if char_name else "")
        if matched_p_key not in phys_actors and sess_char.get("name"):
            alt_key = find_player_actor_key(phys_actors, party=[(sess_char, [])], session_id=session.get("id")) or _match_actor_key(str(sess_char["name"]), phys_actors)
            if alt_key in phys_actors:
                matched_p_key = alt_key
                char_dict = sess_char
                char_name = str(sess_char["name"])
        if char_name:
            p_act_data = phys_actors.get(matched_p_key) or {}
            p_cloth_badge = compute_clothing_summary_badge(p_act_data.get("clothing"), gender=char_dict.get("gender", "Male"))
            session["player_clothing_status"] = p_cloth_badge
            if isinstance(session.get("character"), dict):
                session["character"]["clothing_status"] = p_cloth_badge
            elif char:
                session["character"] = dict(char)
                session["character"]["clothing_status"] = p_cloth_badge

        if isinstance(session.get("party_members"), list):
            for pm in session["party_members"]:
                if isinstance(pm, dict) and pm.get("name"):
                    m_pm_key = _match_actor_key(str(pm["name"]), phys_actors)
                    pm_act_data = phys_actors.get(m_pm_key) or {}
                    pm["clothing_status"] = compute_clothing_summary_badge(
                        pm_act_data.get("clothing"),
                        gender=pm.get("gender", "Male"),
                    )

        # 2. Present NPCs & Party Companions clothing status & status effects
        raw_npcs = session.get("current_npcs") or []
        sess_id = session.get("id") or 0
        contacts_list = db.get_contacts(sess_id) or [] if sess_id else []
        contacts_by_name = {str(c.get("name", "")).strip().lower(): c for c in contacts_list if isinstance(c, dict)}
        lore_data = db.get_lorebook(sess_id) or {} if sess_id else {}
        lore_characters = {}
        if isinstance(lore_data, dict):
            for l_cat in ("characters", "npcs", "people"):
                for l_ent in (lore_data.get(l_cat) or []):
                    if isinstance(l_ent, dict):
                        l_name = str(l_ent.get("title") or l_ent.get("name") or "").strip().lower()
                        if l_name:
                            lore_characters[l_name] = l_ent

        def _enrich_npc_entry(npc_item):
            if isinstance(npc_item, str):
                n_dict = {"name": npc_item.strip()}
            elif isinstance(npc_item, dict):
                n_dict = dict(npc_item)
            else:
                return None

            n_name = str(n_dict.get("name") or "").strip()
            if not n_name:
                return None

            matched_n_key = _match_actor_key(n_name, phys_actors)
            n_act_data = phys_actors.get(matched_n_key) or {}
            c_rec = contacts_by_name.get(n_name.lower())
            if not c_rec and contacts_by_name:
                m_c_key = _match_actor_key(n_name, contacts_by_name)
                c_rec = contacts_by_name.get(m_c_key)
            if not c_rec and lore_characters:
                c_rec = lore_characters.get(n_name.lower())
                if not c_rec:
                    m_l_key = _match_actor_key(n_name, lore_characters)
                    c_rec = lore_characters.get(m_l_key)
            c_appr = (c_rec.get("appearance") or {}) if isinstance(c_rec, dict) else {}
            n_gender = (c_appr.get("gender") if isinstance(c_appr, dict) else None) or (c_rec.get("gender") if isinstance(c_rec, dict) else None) or n_dict.get("gender") or "Female"
            n_dict["clothing_status"] = compute_clothing_summary_badge(n_act_data.get("clothing"), gender=n_gender)

            # 1. Synchronize active status effects from all sources
            raw_effs = []
            if isinstance(c_rec, dict):
                c_effs = c_rec.get("status_effects")
                if isinstance(c_effs, list):
                    raw_effs.extend(c_effs)
                elif isinstance(c_effs, str) and c_effs:
                    try:
                        raw_effs.extend(json.loads(c_effs))
                    except Exception:
                        raw_effs.append(c_effs)
                b_effs = (c_rec.get("basic_info") or {}).get("status_effects")
                if isinstance(b_effs, list):
                    raw_effs.extend(b_effs)
                m_effs = (c_rec.get("metadata") or {}).get("status_effects")
                if isinstance(m_effs, list):
                    raw_effs.extend(m_effs)
            if isinstance(n_act_data, dict):
                a_effs = n_act_data.get("status_effects")
                if isinstance(a_effs, list):
                    raw_effs.extend(a_effs)
            if isinstance(n_dict.get("status_effects"), list):
                raw_effs.extend(n_dict.get("status_effects"))
            n_dict["status_effects"] = cd.sanitize_status_effects(raw_effs)

            # 2. Synchronize affinity / relationship score & track
            score = None
            if isinstance(c_rec, dict):
                score = c_rec.get("relationship_score")
                if score is None:
                    score = c_rec.get("affinity")
                if score is None and isinstance(c_rec.get("metadata"), dict):
                    score = c_rec["metadata"].get("relationship_score", c_rec["metadata"].get("affinity"))
            if score is None:
                score = n_dict.get("relationship_score", n_dict.get("affinity", 0))

            n_dict["relationship_score"] = int(score or 0)
            n_dict["affinity"] = int(score or 0)
            n_dict["track"] = (c_rec.get("track") if isinstance(c_rec, dict) else None) or n_dict.get("track", "platonic")

            # 3. Synchronize intimate excitement meter (when applicable)
            exc_actors = (phys_st.get("excitement") or {}).get("actors") or {}
            matched_exc_key = _match_actor_key(n_name, exc_actors) if exc_actors else ""
            exc_data = exc_actors.get(matched_exc_key) or {}

            partner_meter_data = None
            hist_entries = session.get("history") or []
            last_intimate = None
            for h_entry in reversed(hist_entries[-3:]):
                if isinstance(h_entry, dict) and h_entry.get("intimate_update"):
                    last_intimate = h_entry["intimate_update"]
                    break

            if isinstance(last_intimate, dict) and last_intimate.get("active"):
                p_meters = last_intimate.get("partner_meters") or []
                for pm in p_meters:
                    if isinstance(pm, dict) and _match_actor_key(n_name, {pm.get("name", ""): pm}):
                        partner_meter_data = pm
                        break
                if not partner_meter_data and last_intimate.get("partner_meter") is not None:
                    p_name = last_intimate.get("partner_name") or session.get("dialogue_partner") or ""
                    if _match_actor_key(n_name, {p_name: True}):
                        partner_meter_data = {
                            "meter": last_intimate.get("partner_meter", 0),
                            "status": last_intimate.get("act_type", ""),
                            "climaxed": last_intimate.get("simultaneous_partner_climax", False),
                        }

            exc_meter = None
            exc_status = ""
            exc_climaxed = False
            exc_active = False

            if exc_data:
                exc_meter = int(exc_data.get("meter", 0))
                exc_status = str(exc_data.get("status") or "")
                exc_climaxed = bool(exc_data.get("climaxed", False))
                exc_active = bool((phys_st.get("excitement") or {}).get("active", False) or exc_meter > 0)
            elif partner_meter_data:
                exc_meter = int(partner_meter_data.get("meter", 0))
                exc_status = str(partner_meter_data.get("status") or "")
                exc_climaxed = bool(partner_meter_data.get("climaxed", False))
                exc_active = True

            if exc_active and exc_meter is not None:
                n_dict["excitement_meter"] = exc_meter
                n_dict["excitement_status"] = exc_status
                n_dict["excitement_climaxed"] = exc_climaxed
                n_dict["excitement_active"] = True

            return n_dict

        enriched_npcs = []
        for npc in raw_npcs:
            enr = _enrich_npc_entry(npc)
            if enr:
                enriched_npcs.append(enr)
        session["current_npcs"] = enriched_npcs

        if isinstance(session.get("party_npcs"), list):
            enriched_party_npcs = []
            for p_npc in session["party_npcs"]:
                enr_p = _enrich_npc_entry(p_npc)
                if enr_p:
                    enriched_party_npcs.append(enr_p)
            session["party_npcs"] = enriched_party_npcs
    except Exception as e:
        logger.debug(f"Could not enrich clothing status for session: {e}")

    return session


async def _trigger_scene_image_broadcast(
    session_id: int,
    scene_title: str = "",
    narrative: str = "",
    location: str = "",
    scenario: str = "",
    image_prompt: str | None = None,
    outcome: dict | None = None,
    action: dict | None = None,
    force: bool = False,
) -> str | None:
    """Generates a scene illustration in the background and broadcasts SCENE_IMAGE via WebSocket."""
    try:
        import image_client
        from mechanics.narrative.image_prompt_composer import compose_turn_image_prompt

        sess = await adb(db.get_session, session_id)
        if not sess:
            return None

        # Check generation mode: auto (1, "auto", "1", True) vs on_demand (2, "on_demand", "2") vs disabled (0)
        img_mode = sess.get("image_gen_enabled")
        if not force and str(img_mode).lower() not in ("1", "auto", "true"):
            return None

        # Deterministically compose Danbooru / SDXL / Illustrious prompt and target aspect ratio
        composed = compose_turn_image_prompt(sess, outcome=outcome, action=action)
        prompt = (image_prompt.strip() if image_prompt and "masterpiece" in image_prompt else composed.prompt)
        target_size = composed.size
        negative_prompt = composed.negative_prompt

        model_override = None
        if sess.get("host_user_id"):
            user_settings = await adb(db.get_settings, sess["host_user_id"])
            model_override = user_settings.get("image_model") or None

        image_url = await image_client.generate_scene_image(
            prompt,
            model=model_override,
            session_id=session_id,
            size=target_size,
            negative_prompt=negative_prompt,
        )
        if image_url:
            local_web_url = getattr(image_url, "local_url", str(image_url))
            await adb(db.update_session, session_id, scene_image_url=local_web_url)
            fresh_s = await adb(db.get_session, session_id)
            if fresh_s:
                raw_hist = list(fresh_s.get("history") or [])
                if raw_hist and isinstance(raw_hist[-1], dict):
                    raw_hist[-1]["scene_image_url"] = local_web_url
                    raw_hist[-1]["scene_image_orientation"] = composed.orientation
                    import json
                    await adb(db.update_session, session_id, history_json=json.dumps(raw_hist, default=str))

            await manager.broadcast(session_id, {
                "type": "SCENE_IMAGE",
                "session_id": session_id,
                "image_url": local_web_url,
                "orientation": composed.orientation,
            })
            return local_web_url
    except Exception as e:
        logger.warning(f"Scene image generation failed for session {session_id}: {e}")
        return None


def _fetch_open_lobbies() -> list[dict]:
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT id, mode, capacity, host_user_id, scenario, scene_title, current_location, status, created_at
               FROM sessions
               WHERE status IN ('waiting', 'active') AND (mode IN ('turn', 'sync', 'multi') OR capacity > 1)
               ORDER BY updated_at DESC LIMIT 20"""
        ).fetchall()
        lobbies = []
        for r in rows:
            sid = r["id"]
            members = db.get_session_members(sid)
            host_char = db.get_character(r["host_user_id"])
            lobbies.append({
                "id": sid,
                "mode": r["mode"],
                "capacity": r["capacity"],
                "member_count": len(members),
                "host_user_id": r["host_user_id"],
                "host_name": host_char["name"] if host_char else f"User {r['host_user_id']}",
                "scenario": r["scenario"],
                "scenario_display_name": get_scenario_display_name(r["scenario"]),
                "scene_title": r["scene_title"] or get_scenario_display_name(r["scenario"]),
                "current_location": r["current_location"] or "",
                "status": r["status"],
            })
        return lobbies


@router.get("/api/adventure/lobbies")
async def list_open_lobbies():
    """Lists open multiplayer adventure sessions available to join."""
    lobbies = await adb(_fetch_open_lobbies)
    return {"lobbies": lobbies}


@router.get("/api/adventure/active-session/{user_id}")
async def get_active_session(user_id: int):
    """Gets the active adventure session for a user."""
    session_id = await adb(db.get_active_session_id_for_user, user_id)
    if not session_id:
        return {"has_active_session": False, "session": None}

    session = await adb(db.get_session, session_id)
    if not session:
        return {"has_active_session": False, "session": None}

    session = await adb(_enrich_session_for_client, session, user_id)

    return {
        "has_active_session": True,
        "session": session
    }


@router.post("/api/adventure/start")
async def start_adventure(req: StartAdventureRequest):
    """Starts a new adventure session (Solo or Multiplayer) and generates the opening scene."""
    async with distributed_user_lock(req.user_id):
        char = await adb(db.get_character, req.user_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found. Create a character first!")

        active_id = await adb(db.get_active_session_id_for_user, req.user_id)
        if active_id:
            await adb(db.finish_session, active_id)

        mode = req.mode.lower()
        if mode == "multi":
            mode = "turn"
        if mode not in ["solo", "turn", "sync"]:
            mode = "solo"

        user_settings = await adb(db.get_user_settings, req.user_id)
        verbosity = user_settings.get("verbosity", "vivid")
        dialogue_mode = user_settings.get("dialogue_mode", "balanced")
        image_gen_enabled = user_settings.get("image_gen_enabled", 0)
        choices_style = user_settings.get("choices_style", "dropdown")
        result_display = user_settings.get("result_display", "detailed")
        show_percentages = user_settings.get("show_percentages", 1)
        language = user_settings.get("narration_language") or user_settings.get("language", "en")
        narration_language = language

        scenario_key = req.scenario or char.get("scenario", "fantasy")
        if req.tags:
            from scenario_data import resolve_scenario_or_custom_key
            scenario_key = resolve_scenario_or_custom_key(req.tags)

        await adb(db.reset_character_for_new_adventure, req.user_id, scenario_key)

        if req.char_class:
            await adb(
                db.apply_adventure_loadout,
                req.user_id,
                scenario_key,
                req.char_class,
                req.class_description,
                req.weapon_name,
                req.weapon_description,
                req.starter_loadout,
                req.starting_items
            )
        
        if req.str_val is not None:
            stats = {
                'str': req.str_val, 'per': req.per, 'end': req.end,
                'cha': req.cha, 'int': req.int_val, 'agi': req.agi, 'luk': req.luk
            }
            if hasattr(db, 'update_character_stats'):
                await adb(db.update_character_stats, req.user_id, stats)

        app_update = dict(req.appearance or {})
        if req.breast_size is not None:
            app_update["breast_size"] = req.breast_size
        if req.penis_size is not None:
            app_update["penis_size"] = req.penis_size
        if req.asset_texture is not None:
            app_update["asset_texture"] = req.asset_texture
        if app_update:
            await adb(db.update_character_appearance, char["id"], app_update)


        default_cap = 1 if mode == "solo" else max(2, req.capacity or 4)
        session_id = await adb(
            db.create_session,
            mode=mode,
            capacity=default_cap if mode != "solo" else (req.capacity or 1),
            host_user_id=req.user_id,
            scenario=scenario_key,
            verbosity=verbosity,
            dialogue_mode=dialogue_mode,
            image_gen_enabled=image_gen_enabled,
            choices_style=choices_style,
            result_display=result_display,
            show_percentages=show_percentages,
            language=language,
            narration_language=narration_language,
        )

        await adb(db.add_session_member, session_id, req.user_id)
        await adb(db.set_session_active, session_id, [req.user_id])

        char_row = await adb(db.get_character, req.user_id)
        inv = await adb(db.get_inventory, req.user_id) if char_row else []
        party = [(dict(char_row), inv)] if char_row else []
        session_row = await adb(db.get_session, session_id)
        session = dict(session_row)

        try:
            scene = await game_engine.generate_opening_scene(session, party)
            await adb(game_engine.apply_quest_update, session_id, scene)
            if isinstance(scene, dict) and "merchant_encounter" in scene:
                from mechanics.combat.merchant import apply_merchant_encounter_result
                await adb(apply_merchant_encounter_result, session_id, scene.get("merchant_encounter"))
            raw_choices, narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                scene, session=session
            )
            raw_choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_choices,
                scenario=scenario_key,
                location=scene.get("location") or "",
                char=dict(char_row) if char_row else None,
                dialogue_partner=partner_arg,
                current_npcs=npcs_arg,
                session_id=session_id,
            )
            await adb(
                db.save_session_scene,
                session_id,
                scene_title,
                narrative,
                raw_choices,
                [],
                location=scene.get("location"),
                nearby_enemies=scene.get("nearby_enemies"),
                current_npcs=npcs_arg,
                dialogue_partner=partner_arg,
                current_node_id=scene.get("current_node_id"),
            )
            char_id = char_row["id"] if char_row else 0
            enemy_names = {game_engine._get_npc_name(e).lower() for e in scene.get("nearby_enemies", []) if e}
            for npc in (npcs_arg or []):
                n_name = game_engine._get_npc_name(npc)
                if n_name and n_name.lower() not in enemy_names:
                    b_info = dict(npc.get("basic_info") or {}) if isinstance(npc, dict) else {}
                    if isinstance(npc, dict):
                        if "role" in npc and not b_info.get("role"):
                            b_info["role"] = npc.get("role", "")
                        if "description" in npc and not b_info.get("description"):
                            b_info["description"] = npc.get("description", "")
                    if not b_info.get("location"):
                        b_info["location"] = scene.get("location") or session.get("current_location", "")
                    if is_contact_eligible(name=n_name, role=b_info.get("role", ""), description=b_info.get("description", ""), scenario=scenario_key, session_id=session_id):
                        await adb(db.upsert_contact,
                            session_id=session_id,
                            character_id=char_id,
                            npc_id=n_name,
                            name=n_name,
                            basic_info=b_info,
                            delta_score=0,
                            new_traits=npc.get("traits") if isinstance(npc, dict) else None,
                            new_preferences=npc.get("preferences") if isinstance(npc, dict) else None,
                            race=npc.get("race", "") if isinstance(npc, dict) else "",
                            gender=npc.get("gender", "") if isinstance(npc, dict) else "",
                            appearance=npc.get("appearance", {}) if isinstance(npc, dict) else None,
                        )
                    else:
                        # Non-student characters are story figures only; track basic info in lorebook
                        m_val = npc.get("mannerisms", "") if isinstance(npc, dict) else ""
                        if not m_val and isinstance(b_info, dict):
                            m_val = b_info.get("mannerisms", "")
                        await adb(db.upsert_lorebook_entity,
                            session_id=session_id,
                            entity_type="person",
                            name=n_name,
                            description=b_info.get("description", "") or (npc.get("description", "") if isinstance(npc, dict) else ""),
                            traits=npc.get("traits") if isinstance(npc, dict) else [],
                            mannerisms=m_val,
                            race=npc.get("race", "") if isinstance(npc, dict) else "",
                            appearance=npc.get("appearance", {}) if isinstance(npc, dict) else {},
                            gender=npc.get("gender", "") if isinstance(npc, dict) else "",
                        )
        except Exception as e:
            logger.error(f"Error generating opening scene: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate scene: {str(e)}")

        updated_session = await adb(db.get_session, session_id)
        updated_session = await adb(_enrich_session_for_client, updated_session, req.user_id)

        await manager.broadcast(session_id, {
            "type": "NEW_SCENE",
            "session": updated_session,
            "sync_timestamp": time.time()
        })

        if updated_session.get("image_gen_enabled"):
            asyncio.create_task(
                _trigger_scene_image_broadcast(
                    session_id,
                    updated_session.get("scene_title", ""),
                    updated_session.get("narrative", ""),
                    updated_session.get("current_location", ""),
                    scenario_key,
                    image_prompt=None,
                    outcome=scene,
                )
            )

        return {"success": True, "session": updated_session}


@router.post("/api/adventure/join")
async def join_adventure(req: JoinAdventureRequest):
    """Joins an existing multiplayer adventure session by invite/session code."""
    try:
        session_id = int(str(req.join_code).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid join code. Must be numeric session ID.")

    session_row = await adb(db.get_session, session_id)
    if not session_row or session_row.get("status") != "active":
        raise HTTPException(status_code=404, detail="Active adventure session not found with that invite code.")

    char = await adb(db.get_character, req.user_id)
    if not char:
        raise HTTPException(status_code=404, detail="Character not found. Create a character first.")

    await adb(db.add_session_member, session_id, req.user_id)
    session_fresh = await adb(db.get_session, session_id)
    session = await adb(_enrich_session_for_client, dict(session_fresh), req.user_id)

    return {"success": True, "session": session}


@router.post("/api/adventure/action")
async def execute_action(req: ActionRequest):
    """Executes a player choice or custom action in an adventure session."""
    async with distributed_session_lock(req.session_id):
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        session = dict(session_row)
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session is not active")

        char = await adb(db.get_character, req.user_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        raw_db_choices = session.get("choices", []) or []
        choices = await adb(
            game_engine.sanitize_and_diversify_choices,
            raw_db_choices,
            scenario=session.get("scenario", "fantasy"),
            location=session.get("current_location", ""),
            char=dict(char) if char else None,
            dialogue_partner=session.get("dialogue_partner"),
            current_npcs=session.get("current_npcs", []),
            session_id=session.get("id"),
        )

        raw_pick = {
            "choice_index": req.choice_index,
            "custom_action_text": req.custom_action_text,
            "direct_choice": req.direct_choice,
            "combat_target": req.combat_target,
            "intent": getattr(req, "intent", None),
            "target_npc": getattr(req, "target_npc", None),
            "action": req.action if isinstance(req.action, dict) else None,
        }
        try:
            action = await TurnService.prepare_and_roll_action(
                session_id=req.session_id,
                user_id=req.user_id,
                raw_pick=raw_pick,
                session=session,
                char=dict(char),
                choices=choices,
                enforce_explicit_mp=True,
            )
        except (PermissionError, ValueError) as e:
            raise HTTPException(status_code=400, detail=str(e))

        mode = session["mode"]
        try:
            safe_action = _serializable_action(action)
            user_settings = await adb(db.get_user_settings, req.user_id)
            stream_enabled = user_settings.get("stream_narrative", 1) == 1
            stream_callback = None
            started_streaming = False
            chunk_buffer = []
            active_chunk_field = "outcome_narrative"

            async def flush_buffer():
                if chunk_buffer:
                    text = "".join(chunk_buffer)
                    chunk_buffer.clear()
                    await manager.broadcast(req.session_id, {
                        "type": "STREAM_CHUNK",
                        "text": text,
                        "field": active_chunk_field,
                    })

            if stream_enabled:
                last_flush = asyncio.get_running_loop().time()
                if mode != "sync":
                    started_streaming = True
                    await manager.broadcast(req.session_id, {
                        "type": "STREAM_START",
                        "user_id": req.user_id,
                        "action": safe_action
                    })

                async def on_token(token: str, field: str = "outcome_narrative"):
                    nonlocal last_flush, started_streaming, active_chunk_field
                    if not started_streaming:
                        started_streaming = True
                        await manager.broadcast(req.session_id, {
                            "type": "STREAM_START",
                            "user_id": req.user_id,
                            "action": safe_action
                        })

                    if field != active_chunk_field:
                        await flush_buffer()
                        active_chunk_field = field
                        last_flush = asyncio.get_running_loop().time()

                    chunk_buffer.append(token)
                    now = asyncio.get_running_loop().time()
                    if now - last_flush >= 0.025 or "\n" in token:
                        await flush_buffer()
                        last_flush = now

                on_token._accepts_field = True
                stream_callback = on_token

            heartbeat_stop = asyncio.Event()
            async def _stream_heartbeat():
                while not heartbeat_stop.is_set():
                    try:
                        await asyncio.wait_for(heartbeat_stop.wait(), timeout=4.0)
                    except asyncio.TimeoutError:
                        await manager.broadcast(req.session_id, {
                            "type": "HEARTBEAT",
                            "status": "processing"
                        })
            hb_task = asyncio.create_task(_stream_heartbeat())

            try:
                turn_response = await TurnService.resolve_action(req.session_id, req.user_id, action, mode=mode, stream_callback=stream_callback)
            finally:
                heartbeat_stop.set()
                try:
                    await hb_task
                except Exception:
                    pass

            if started_streaming:
                await flush_buffer()

            outcome = turn_response.outcome
            raw_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                outcome, session=turn_response.session
            )
            
            if outcome.get("fallback_reason") == "empty_prose":
                next_narrative = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n" + (next_narrative or "")
                
            effective_partner = (
                turn_response.session.get("dialogue_partner")
                if partner_arg is ...
                else partner_arg
            )
            effective_npcs = (
                turn_response.session.get("current_npcs", [])
                if npcs_arg is None
                else npcs_arg
            )
            if not (isinstance(outcome, dict) and outcome.get("_hybrid_choices_built") and raw_choices):
                raw_choices = await adb(
                    game_engine.sanitize_and_diversify_choices,
                    raw_choices,
                    scenario=turn_response.session.get("scenario", "fantasy"),
                    location=outcome.get("location") or turn_response.session.get("current_location", ""),
                    char=dict(char) if char else None,
                    dialogue_partner=effective_partner,
                    current_npcs=effective_npcs,
                    session_id=req.session_id,
                    departed_npcs=outcome.get("departed_characters") or outcome.get("departed_npcs"),
                )
            await adb(
                db.save_session_scene,
                req.session_id,
                scene_title,
                next_narrative,
                raw_choices,
                turn_response.session.get("history", []),
                location=outcome.get("location"),
                nearby_enemies=outcome.get("nearby_enemies"),
                current_npcs=npcs_arg,
                dialogue_partner=partner_arg,
                current_node_id=outcome.get("current_node_id"),
                focal_point=outcome.get("focal_point"),
            )

            if mode in ("turn", "multi"):
                await adb(db.advance_turn, req.session_id)
        except ValueError as e:
            if str(e) == "waiting_for_party":
                party = await adb(db.get_session_members, req.session_id)
                picks = session.get("pending_picks", {})
                await manager.broadcast(req.session_id, {
                    "type": "PICK_LOCKED",
                    "user_id": req.user_id,
                    "character_name": char["name"],
                    "locked_picks": len(picks) + 1,
                    "total": len(party),
                    "waiting_count": len(party) - len(picks) - 1
                })
                return {"status": "waiting_for_party", "locked_picks": len(picks) + 1, "total": len(party)}
            if "started_streaming" in locals() and started_streaming:
                await manager.broadcast(req.session_id, {"type": "STREAM_ERROR", "error": str(e)})
            raise
        except Exception as e:
            if "started_streaming" in locals() and started_streaming:
                await manager.broadcast(req.session_id, {"type": "STREAM_ERROR", "error": str(e)})
            snapshot = await adb(db.get_turn_snapshot, req.session_id)
            reason = snapshot.get("fallback_reason") if snapshot else None
            if reason == "models_unavailable":
                msg = "The generative models are currently overloaded or unavailable. Your action was saved. Please try again in a moment."
                raise HTTPException(status_code=503, detail=msg)
            raise HTTPException(status_code=500, detail=f"Engine failed to resolve the turn: {str(e)}")

        fresh_session = await adb(db.get_session, req.session_id)
        fresh_session = await adb(_enrich_session_for_client, fresh_session, req.user_id)

        msg_type = "STREAM_END" if started_streaming else "NEW_SCENE"
        await manager.broadcast(req.session_id, {
            "type": msg_type,
            "session": fresh_session,
            "last_action": safe_action,
            "xp_gained": turn_response.xp_gained,
            "levels_gained": turn_response.levels_gained,
            "sync_timestamp": time.time()
        })

        if fresh_session.get("image_gen_enabled"):
            asyncio.create_task(
                _trigger_scene_image_broadcast(
                    req.session_id,
                    fresh_session.get("scene_title", ""),
                    fresh_session.get("narrative", ""),
                    fresh_session.get("current_location", ""),
                    fresh_session.get("scenario", "fantasy"),
                    image_prompt=None,
                    outcome=turn_response.outcome if isinstance(turn_response.outcome, dict) else None,
                    action=action,
                )
            )

        return {
            "success": True,
            "session": fresh_session,
            "action": safe_action,
            "xp_gained": turn_response.xp_gained,
            "levels_gained": turn_response.levels_gained
        }


@router.post("/api/adventure/end")
async def end_adventure(req: EndAdventureRequest):
    """Ends/finishes an active adventure session."""
    await adb(db.finish_session, req.session_id)
    return {"success": True, "session_id": req.session_id}


@router.post("/api/adventure/retry")
async def retry_adventure_scene(req: RetryAdventureRequest):
    """Re-generates the current scene when fallback generation occurred or retry is requested."""
    async with distributed_session_lock(req.session_id):
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        session = dict(session_row)
        uid = req.user_id or session.get("host_user_id")
        members = await adb(db.get_session_members, req.session_id)
        if not members and uid:
            members = [uid]

        party = []
        for m_uid in members:
            c = await adb(db.get_character, m_uid)
            if c:
                inv = await adb(db.get_inventory, m_uid)
                party.append((dict(c), inv))

        actor_char = party[0][0] if party else {"user_id": uid or 0, "name": "Adventurer", "max_hp": 100, "per_": 5, "luk": 5}

        history = list(session.get("history") or [])
        if not history:
            # Turn 0: Opening scene retry
            # Reset stale state from previous aborted attempts so stale NPCs/enemies never bleed into fresh scene rolls
            session["current_npcs"] = []
            session["dialogue_partner"] = None
            session["nearby_enemies"] = []
            try:
                scene = await game_engine.generate_opening_scene(session, party)
                if getattr(scene, "model_dump", None):
                    scene = scene.model_dump(exclude_unset=False)
                if not isinstance(scene, dict):
                    scene = {}

                raw_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                    scene, session=session
                )
                location = scene.get("location") or session.get("current_location", "")
                raw_choices = await adb(
                    game_engine.sanitize_and_diversify_choices,
                    raw_choices,
                    scenario=session.get("scenario", "fantasy"),
                    location=location,
                    char=dict(actor_char) if actor_char else None,
                    dialogue_partner=partner_arg,
                    current_npcs=npcs_arg,
                    session_id=req.session_id,
                )
                init_node_id = await adb(db.resolve_node_id_from_location, req.session_id, location)
                await adb(
                    db.save_session_scene,
                    req.session_id,
                    scene_title,
                    next_narrative,
                    raw_choices,
                    history=[],
                    location=location,
                    nearby_enemies=scene.get("nearby_enemies", []),
                    current_npcs=npcs_arg,
                    dialogue_partner=partner_arg,
                    current_node_id=init_node_id,
                    focal_point=scene.get("focal_point", ""),
                )
                char_id = actor_char.get("id", 0) if isinstance(actor_char, dict) else 0
                enemy_names = {game_engine._get_npc_name(e).lower() for e in scene.get("nearby_enemies", []) if e}
                for npc in (npcs_arg or []):
                    n_name = game_engine._get_npc_name(npc)
                    if n_name and n_name.lower() not in enemy_names:
                        b_info = dict(npc.get("basic_info") or {}) if isinstance(npc, dict) else {}
                        if isinstance(npc, dict):
                            if "role" in npc and not b_info.get("role"):
                                b_info["role"] = npc.get("role", "")
                            if "description" in npc and not b_info.get("description"):
                                b_info["description"] = npc.get("description", "")
                        if not b_info.get("location"):
                            b_info["location"] = location
                        if is_contact_eligible(name=n_name, role=b_info.get("role", ""), description=b_info.get("description", ""), scenario=session.get("scenario", "fantasy"), session_id=req.session_id):
                            await adb(db.upsert_contact,
                                session_id=req.session_id,
                                character_id=char_id,
                                npc_id=n_name,
                                name=n_name,
                                basic_info=b_info,
                                delta_score=0,
                                new_traits=npc.get("traits") if isinstance(npc, dict) else None,
                                new_preferences=npc.get("preferences") if isinstance(npc, dict) else None,
                                race=npc.get("race", "") if isinstance(npc, dict) else "",
                                gender=npc.get("gender", "") if isinstance(npc, dict) else "",
                                appearance=npc.get("appearance", {}) if isinstance(npc, dict) else None,
                            )
                        else:
                            # Non-student characters are story figures only; track basic info in lorebook
                            m_val = npc.get("mannerisms", "") if isinstance(npc, dict) else ""
                            if not m_val and isinstance(b_info, dict):
                                m_val = b_info.get("mannerisms", "")
                            await adb(db.upsert_lorebook_entity,
                                session_id=req.session_id,
                                entity_type="person",
                                name=n_name,
                                description=b_info.get("description", "") or (npc.get("description", "") if isinstance(npc, dict) else ""),
                                traits=npc.get("traits") if isinstance(npc, dict) else [],
                                mannerisms=m_val,
                                race=npc.get("race", "") if isinstance(npc, dict) else "",
                                appearance=npc.get("appearance", {}) if isinstance(npc, dict) else {},
                                gender=npc.get("gender", "") if isinstance(npc, dict) else "",
                            )
            except Exception as e:
                logger.error(f"Error retrying opening scene: {e}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Failed to retry opening scene: {str(e)}")

            updated_session = await adb(db.get_session, req.session_id)
            enriched_session = await adb(_enrich_session_for_client, updated_session, uid)

            await manager.broadcast(req.session_id, {
                "type": "NEW_SCENE",
                "session": enriched_session,
                "sync_timestamp": time.time(),
            })
            return {"success": True, "session": enriched_session}

        try:
            turn_response = await TurnService.retry_narration(req.session_id, uid)
            outcome = turn_response.outcome
            
            raw_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                outcome, session=session
            )
            
            if outcome.get("fallback_reason") == "empty_prose":
                next_narrative = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n" + (next_narrative or "")
                
            effective_partner = (
                session.get("dialogue_partner")
                if partner_arg is ...
                else partner_arg
            )
            effective_npcs = (
                session.get("current_npcs", [])
                if npcs_arg is None
                else npcs_arg
            )
            raw_choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_choices,
                scenario=session.get("scenario", "fantasy"),
                location=outcome.get("location") or session.get("current_location", ""),
                char=dict(actor_char) if actor_char else None,
                dialogue_partner=effective_partner,
                current_npcs=effective_npcs,
                session_id=req.session_id,
                departed_npcs=outcome.get("departed_characters") or outcome.get("departed_npcs"),
            )
            
            # The history dict was already updated by retry_narration, so we just use the fresh one
            updated_history = list(turn_response.session.get("history", []))
            
            await adb(
                db.save_session_scene,
                req.session_id,
                scene_title,
                next_narrative,
                raw_choices,
                updated_history,
                location=outcome.get("location"),
                nearby_enemies=outcome.get("nearby_enemies"),
                current_npcs=npcs_arg,
                dialogue_partner=partner_arg,
                current_node_id=outcome.get("current_node_id"),
                focal_point=outcome.get("focal_point"),
            )
        except Exception as e:
            logger.error(f"Error retrying adventure scene: {e}")
            snapshot = await adb(db.get_turn_snapshot, req.session_id)
            reason = snapshot.get("fallback_reason") if snapshot else None
            if reason == "models_unavailable":
                msg = "The generative models are currently overloaded or unavailable. Please try again in a moment."
                raise HTTPException(status_code=503, detail=msg)
            raise HTTPException(status_code=500, detail=f"Failed to retry scene: {str(e)}")

        updated_session = await adb(db.get_session, req.session_id)
        enriched_session = await adb(_enrich_session_for_client, updated_session, uid)

        await manager.broadcast(req.session_id, {
            "type": "NEW_SCENE",
            "session": enriched_session,
            "sync_timestamp": time.time(),
        })

        if enriched_session.get("image_gen_enabled"):
            asyncio.create_task(
                _trigger_scene_image_broadcast(
                    req.session_id,
                    enriched_session.get("scene_title", ""),
                    enriched_session.get("narrative", ""),
                    enriched_session.get("current_location", ""),
                    enriched_session.get("scenario", "fantasy"),
                    image_prompt=None,
                    outcome=outcome if isinstance(outcome, dict) else None,
                )
            )

        return {"success": True, "session": enriched_session}


@router.post("/api/adventure/reroll_image")
async def reroll_adventure_image(req: RerollImageRequest):
    """Regenerates only the scene image for the active turn without touching the story narrative."""
    session_row = await adb(db.get_session, req.session_id)
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")
    session = dict(session_row)
    if str(session.get("image_gen_enabled") or "0").lower() in ("0", "disabled", "false"):
        raise HTTPException(status_code=400, detail="Image generation is disabled in settings")

    # Extract last history outcome if available to rebuild accurate context
    raw_hist = list(session.get("history") or [])
    last_entry = raw_hist[-1] if (raw_hist and isinstance(raw_hist[-1], dict)) else {}

    local_url = await _trigger_scene_image_broadcast(
        req.session_id,
        scene_title=session.get("scene_title", ""),
        narrative=session.get("narrative", ""),
        location=session.get("current_location", ""),
        scenario=session.get("scenario", "fantasy"),
        outcome=last_entry,
        force=True,
    )
    return {"success": True, "image_url": local_url}


# -----------------------------------------------------------------------------
# Adventure Save / Checkpoint Endpoints
# -----------------------------------------------------------------------------
@router.get("/api/saves/{user_id}")
async def list_saves(user_id: int):
    """Lists all adventure save slots for the user's active character."""
    from scenario_data import get_scenario_display_name
    saves = await adb(db.list_adventure_saves, user_id)
    enriched_saves = []
    for s in saves:
        sd = dict(s)
        if sd.get("scenario"):
            sd["scenario_display_name"] = get_scenario_display_name(sd["scenario"])
        enriched_saves.append(sd)
    return {"saves": enriched_saves}


@router.post("/api/saves/save")
async def save_slot(req: SaveSlotRequest):
    """Creates or overwrites a named adventure checkpoint save slot."""
    try:
        res = await adb(db.save_adventure_slot, req.user_id, req.slot_name, overwrite=req.overwrite)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/saves/load")
async def load_slot(req: LoadSlotRequest):
    """Restores a named adventure save slot into a fresh active session."""
    try:
        res = await adb(db.load_adventure_slot, req.user_id, req.slot_name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    session_id = res.get("id") or res.get("session_id")
    updated_session = await adb(db.get_session, session_id) if session_id else res
    if updated_session:
        updated_session = await adb(_enrich_session_for_client, updated_session, req.user_id)
        await manager.broadcast(session_id, {
            "type": "NEW_SCENE",
            "session": updated_session,
            "sync_timestamp": time.time()
        })

    return {
        "success": True,
        "loaded": res,
        "session": updated_session
    }


@router.delete("/api/saves/{user_id}/{slot_name}")
async def delete_save(user_id: int, slot_name: str):
    """Deletes a named adventure save slot."""
    deleted = await adb(db.delete_adventure_save, user_id, slot_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Save slot not found")
    return {"success": True}


# -----------------------------------------------------------------------------
# World Map & Fast-Travel Discovery Endpoint
# -----------------------------------------------------------------------------
def _build_locations_payload(session_id: int, scen_key: str, current_loc: str, char_name: str) -> dict:
    from mechanics.world.locations import (
        process_llm_location_update,
        get_zone_summary_tree,
        sanitize_location_target,
        parse_tiered_location,
    )
    from mechanics.world.waypoints import ensure_quest_waypoints_exist
    try:
        ensure_quest_waypoints_exist(session_id)
    except Exception:
        pass

    active_wps = db.get_all_session_active_waypoints(session_id)
    for wp in active_wps:
        target_loc = (wp.get("target_location") or "").strip()
        if target_loc:
            clean_target = sanitize_location_target(target_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            process_llm_location_update(session_id, clean_target, scen_key, char_name=char_name)

    # Seed any active phone appointment rendezvous destinations
    appts = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
    for appt in appts:
        appt_loc = (appt.get("rendezvous_location") or "").strip()
        if appt_loc:
            clean_appt_loc = sanitize_location_target(appt_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            process_llm_location_update(session_id, clean_appt_loc, scen_key, char_name=char_name)

    if current_loc:
        process_llm_location_update(session_id, current_loc, scen_key, char_name=char_name)

    zones_summary = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    curr_z, curr_p, curr_sub = (
        parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)
        if current_loc else ("", "", "")
    )

    session = db.get_session(session_id)
    curr_node_id = session.get("current_node_id") if session else None
    curr_node = db.get_world_node(session_id, curr_node_id) if (session_id and curr_node_id) else None
    all_nodes = db.get_session_world_nodes(session_id) if session_id else []
    outgoing_edges = db.get_outgoing_edges(session_id, curr_node_id) if (session_id and curr_node_id) else []
    adjacent_node_ids = {e["to_node_id"] for e in outgoing_edges}
    player_at_transit_hub = db.is_node_or_parent_transit_hub(session_id, curr_node_id) if (session_id and curr_node_id) else False

    from mechanics.world.schedules import get_npc_scheduled_node_id
    from mechanics.world.locations.access_gate import get_node_effective_access_info

    curr_day, curr_min, _ = db.get_session_time(session_id)
    contacts = db.get_contacts(session_id) or []
    roster = db.get_school_roster(session_id) if hasattr(db, "get_school_roster") else []

    occupancy_by_node: dict[str, dict] = {}
    def _get_occ_entry(nid: str):
        if nid not in occupancy_by_node:
            occupancy_by_node[nid] = {"known_npcs": [], "unmet_count": 0}
        return occupancy_by_node[nid]

    for appt in appts:
        tgt = appt.get("target_node_id")
        if not tgt and appt.get("rendezvous_location"):
            tgt = db.resolve_node_id_from_location(session_id, appt["rendezvous_location"], prefer_facility=True)
        if tgt:
            tgt_node = next((n for n in all_nodes if n["node_id"] == tgt), None)
            fac_id = tgt_node.get("parent_id") if (tgt_node and tgt_node.get("node_type") == "ROOM") else tgt
            if fac_id:
                occ = _get_occ_entry(fac_id)
                a_nm = appt.get("npc_name", "")
                if a_nm and not any(kn["name"].lower() == a_nm.lower() for kn in occ["known_npcs"]):
                    occ["known_npcs"].append({"name": a_nm, "status": "Rendezvous"})

    contact_names_lower = set()
    for c in contacts:
        c_nm = (c.get("name") or "").strip()
        if not c_nm:
            continue
        contact_names_lower.add(c_nm.lower())
        sched_nid = get_npc_scheduled_node_id(c, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
        if sched_nid:
            s_node = next((n for n in all_nodes if n["node_id"] == sched_nid), None)
            fac_id = s_node.get("parent_id") if (s_node and s_node.get("node_type") == "ROOM") else sched_nid
            if fac_id:
                occ = _get_occ_entry(fac_id)
                if not any(kn["name"].lower() == c_nm.lower() for kn in occ["known_npcs"]):
                    occ["known_npcs"].append({"name": c_nm, "status": "Routine"})

    for r in roster:
        r_nm = (r.get("name") or "").strip()
        if not r_nm or r_nm.lower() in contact_names_lower:
            continue
        sched_nid = get_npc_scheduled_node_id(r, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
        if sched_nid:
            s_node = next((n for n in all_nodes if n["node_id"] == sched_nid), None)
            fac_id = s_node.get("parent_id") if (s_node and s_node.get("node_type") == "ROOM") else sched_nid
            if fac_id:
                occ = _get_occ_entry(fac_id)
                occ["unmet_count"] += 1

    enriched_zones = []
    active_quest_destinations = []
    for z in zones_summary:
        z_copy = dict(z)
        z_name = z_copy.get("zone_name", "")
        is_same_zone = bool(curr_z and curr_z.lower() == z_name.lower())
        primaries = []
        for p in z_copy.get("primary_locations", []):
            p_copy = dict(p)
            p_copy["is_current_place"] = bool(
                is_same_zone and curr_p and curr_p.lower() == (p_copy.get("name") or "").lower()
            )

            p_node_id = db.resolve_node_id_from_location(session_id, f"{z_name} ➔ {p_copy.get('name', '')}", prefer_facility=True)
            node = next((n for n in all_nodes if n["node_id"] == p_node_id), None) if p_node_id else None
            is_transit_hub = db.is_node_or_parent_transit_hub(session_id, p_node_id) if p_node_id else False
            is_adjacent = bool(
                p_node_id and (
                    p_node_id in adjacent_node_ids or
                    any(n.get("parent_id") == p_node_id and n["node_id"] in adjacent_node_ids for n in all_nodes)
                )
            )
            can_travel = bool(p_copy["is_current_place"] or is_adjacent or (player_at_transit_hub and is_transit_hub) or not all_nodes)

            if is_adjacent:
                p_copy["travel_tag"] = "Adjacent Path"
            elif player_at_transit_hub and is_transit_hub:
                p_copy["travel_tag"] = "Transit Hub Fast-Travel"
            elif is_same_zone:
                p_copy["travel_tag"] = "Local Walk"
            else:
                p_copy["travel_tag"] = "Inter-Zone Travel"

            access_info = get_node_effective_access_info(session_id, p_node_id, current_day=curr_day, current_minute=curr_min, scen_key=scen_key) if p_node_id else {}
            occ_data = occupancy_by_node.get(p_node_id, {"known_npcs": [], "unmet_count": 0}) if p_node_id else {"known_npcs": [], "unmet_count": 0}

            p_copy["node_id"] = p_node_id or ""
            p_copy["is_transit_hub"] = is_transit_hub
            p_copy["is_adjacent"] = is_adjacent
            p_copy["can_travel"] = can_travel
            p_copy["access_tier"] = access_info.get("access_tier", "open")
            p_copy["access_badge"] = access_info.get("status_badge", "Open")
            p_copy["is_curfew_active"] = access_info.get("curfew_active", False)
            p_copy["schedule_locked"] = access_info.get("schedule_locked", False)
            p_copy["is_trespassing"] = access_info.get("is_trespassing", False)
            p_copy["is_unlocked"] = access_info.get("is_unlocked", False)
            p_copy["scene_residue"] = access_info.get("scene_residue", "")
            p_copy["known_npcs_here"] = occ_data["known_npcs"][:3]
            p_copy["unmet_activity_count"] = occ_data["unmet_count"]

            primaries.append(p_copy)
            for qm in (p_copy.get("quest_markers") or []):
                active_quest_destinations.append({
                    "zone_name": z_name,
                    "place_name": p_copy.get("name", ""),
                    "value": p_copy.get("value") or f"{z_name} ➔ {p_copy.get('name', '')}",
                    "marker": qm,
                    "quest_tag": p_copy.get("quest_tag", ""),
                    "is_current_place": p_copy["is_current_place"],
                    "is_transit_hub": is_transit_hub,
                    "can_travel": can_travel,
                })
        primaries.sort(
            key=lambda item: (
                0 if item.get("is_current_place") else 1,
                0 if (item.get("quest_markers") or item.get("quest_tag")) else 1,
                (item.get("name") or "").lower(),
            )
        )
        z_copy["primary_locations"] = primaries
        enriched_zones.append(z_copy)

    enriched_zones.sort(
        key=lambda item: (
            0 if item.get("is_current") else 1,
            0 if (item.get("quest_count", 0) > 0 or any("Quest" in t or "Climax" in t or "Bounty" in t or "Meetup" in t for t in (item.get("active_tags") or []))) else 1,
            (item.get("zone_name") or "").lower(),
        )
    )

    return {
        "session_id": session_id,
        "scenario": scen_key,
        "current_location": current_loc,
        "current_node_id": curr_node_id or "",
        "current_node": curr_node,
        "player_at_transit_hub": player_at_transit_hub,
        "outgoing_edges": outgoing_edges,
        "current_zone": curr_z,
        "current_primary": curr_p,
        "current_sub": curr_sub,
        "zones": enriched_zones,
        "active_quest_destinations": active_quest_destinations,
    }


@router.get("/api/locations/{session_id}")
async def get_world_map_locations(session_id: int, user_id: int | None = None):
    """Returns the 3-tiered discovered World Map hierarchy (Zones -> Primary Locations -> Sub-Areas) with travel tags and quest badges."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    lookup_uid = user_id or session.get("host_user_id")
    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    char_name = char_row.get("name", "") if char_row else ""

    payload = await adb(_build_locations_payload, session_id, scen_key, current_loc, char_name)
    return payload

