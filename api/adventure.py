import asyncio
import time
from fastapi import APIRouter, HTTPException

import db
from db import adb
import game_engine
import skill_check
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
    has_fallback_narrative = any(
        phrase in narr_lower
        for phrase in (
            "threads of fate shimmer",
            "temporary fallback",
            "fallback generation",
            "llm connection failed",
        )
    )
    session["is_fallback_generation"] = bool(
        session.get("is_fallback_generation") or has_fallback_choice or has_fallback_narrative
    )

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

    return session


async def _trigger_scene_image_broadcast(
    session_id: int,
    scene_title: str,
    narrative: str,
    location: str,
    scenario: str,
    image_prompt: str | None = None,
):
    """Generates a scene illustration in the background and broadcasts SCENE_IMAGE via WebSocket."""
    try:
        import image_client
        prompt = (image_prompt or "").strip()
        if not prompt:
            prompt = f"{scenario} RPG scene illustration. Location: {location or scene_title}. {(narrative or '')[:450]}"
        model_override = None
        sess = await adb(db.get_session, session_id)
        if sess and sess.get("host_user_id"):
            user_settings = await adb(db.get_settings, sess["host_user_id"])
            model_override = user_settings.get("image_model") or None
        image_url = await image_client.generate_scene_image(prompt, model=model_override)
        if image_url:
            await manager.broadcast(session_id, {
                "type": "SCENE_IMAGE",
                "session_id": session_id,
                "image_url": image_url,
            })
    except Exception as e:
        logger.warning(f"Scene image generation failed for session {session_id}: {e}")


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
                "scene_title": r["scene_title"] or "New Adventure",
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
            raw_choices = scene.get("choices") or scene.get("next_choices") or []
            raw_choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_choices,
                scenario=scenario_key,
                location=scene.get("location") or "",
                char=dict(char_row) if char_row else None,
                dialogue_partner=None,
                current_npcs=scene.get("npcs_present", []),
                session_id=session_id,
            )
            await adb(
                db.save_session_scene,
                session_id,
                scene.get("scene_title", "Beginning"),
                scene.get("narrative", ""),
                raw_choices,
                [],
                location=scene.get("location"),
                nearby_enemies=scene.get("nearby_enemies"),
                current_npcs=scene.get("npcs_present", [])
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

        # Normalize top-level or nested action payload from frontend
        choice_index = req.choice_index
        custom_action_text = req.custom_action_text
        direct_choice = req.direct_choice
        combat_target = req.combat_target
        intent = getattr(req, "intent", None)
        target_npc = getattr(req, "target_npc", None)
        if isinstance(req.action, dict):
            if choice_index is None and "choice_index" in req.action:
                choice_index = req.action.get("choice_index")
            if not custom_action_text:
                custom_action_text = req.action.get("custom_action_text") or req.action.get("custom_text")
            if direct_choice is None and isinstance(req.action.get("direct_choice"), dict):
                direct_choice = req.action.get("direct_choice")
            if not combat_target and req.action.get("combat_target"):
                combat_target = req.action.get("combat_target")

        action = None
        if isinstance(direct_choice, dict) and direct_choice:
            chosen = dict(direct_choice)
            stat = str(chosen.get("stat", "STR") or "STR").upper()
            req_val = int(chosen.get("requirement", 5) or 0)
            mp_cost = int(chosen.get("mp_cost", 0) or 0)

            if mp_cost > 0:
                if char["mp"] < mp_cost:
                    raise HTTPException(status_code=400, detail="Not enough MP for this action!")
                await adb(db.apply_hp_mp_delta, req.user_id, mp_delta=-mp_cost)

            user_settings = await adb(db.get_settings, req.user_id)
            check_mode = user_settings.get("debug_check_mode", "off")
            stat_col = db.STAT_COLUMN.get(stat, "str_")
            hit_chance = chosen.get("hit_chance")
            if chosen.get("choice_type") == "dialogue" or chosen.get("action_category") == "dialogue":
                dialogue_mode = user_settings.get("dialogue_mode", "balanced")
                if dialogue_mode == "casual":
                    req_val = max(1, req_val - 2)
                elif dialogue_mode == "challenging":
                    req_val += 2

            from mechanics.world.mobility import get_session_dialogue_partners
            sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
            target_candidates = list(sess_dp)
            if chosen.get("target_npc") and str(chosen["target_npc"]).strip() and chosen["target_npc"] not in target_candidates:
                target_candidates.append(chosen["target_npc"])
            if target_candidates and isinstance(session, dict) and session.get("id"):
                from mechanics.combat.traits import get_combined_dc_modifiers
                from mechanics.social.persona import calculate_intimate_action_dc_modifier
                for dp_name in target_candidates:
                    if dp_name:
                        c_rec = await adb(db.get_contact, session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                        if c_rec:
                            c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                            t_mods = get_combined_dc_modifiers(c_traits)
                            req_val += t_mods.get(stat, 0)
                            app_rec = c_rec.get("appearance", {})
                            if isinstance(app_rec, dict):
                                req_val += calculate_intimate_action_dc_modifier(chosen.get("label") or chosen.get("text") or "", app_rec)
            req_val = max(1, req_val)
            if hit_chance is not None:
                import random
                rate = hit_chance
                roll = random.uniform(0, 100)
                succeeded = roll <= rate
                tier = "success" if succeeded else "fail"
                if roll > 90 and succeeded: tier = "crit_success"
                if roll < 10 and not succeeded: tier = "crit_fail"
                res = skill_check.CheckResult(chance=rate, roll=roll, tier=tier, tier_label=tier.replace('_', ' ').title(), succeeded=succeeded, requirement=req_val)
            elif stat in ("NONE", "FREE") or req_val <= 0:
                res = skill_check.CheckResult(chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True)
                rate = 100
            else:
                rate = skill_check.success_chance(char[stat_col], req_val, check_mode=check_mode)
                res = skill_check.resolve_check(char[stat_col], req_val, char["luk"], check_mode=check_mode)

            label_text = chosen.get("label") or chosen.get("text") or "Action"
            action = dict(chosen)
            action.update({
                "user_id": req.user_id,
                "character_name": char["name"],
                "char": dict(char),
                "stat": stat,
                "requirement": req_val,
                "mp_cost": mp_cost,
                "mp_spent": mp_cost,
                "rate": rate,
                "check": res,
                "label": label_text,
                "success": res.succeeded,
                "tier": res.tier,
                "crit": res.tier in ("crit_success", "crit_fail"),
                "roll": res.roll,
                "text": label_text,
                "choice_type": chosen.get("choice_type", ""),
                "action_category": chosen.get("action_category", ""),
                "spell_id": chosen.get("spell_id", ""),
                "combat_target": combat_target or chosen.get("combat_target"),
                "is_quest_action": bool(chosen.get("is_quest_action")),
                "is_climax_action": bool(chosen.get("is_climax_action")),
                "quest_id": chosen.get("quest_id", ""),
                "sub_obj_id": chosen.get("sub_obj_id"),
                "stage_index": chosen.get("stage_index"),
                "contract_type": chosen.get("contract_type", ""),
                "item_name": chosen.get("item_name", ""),
                "item": chosen.get("item"),
                "item_consumed": chosen.get("item_consumed", False),
                "intent": intent or chosen.get("intent"),
                "target_npc": target_npc or chosen.get("target_npc"),
            })
        elif choice_index is not None and 0 <= choice_index < len(choices):
            chosen = choices[choice_index]
            stat = str(chosen.get("stat", "STR") or "STR").upper()
            req_val = int(chosen.get("requirement", 5) or 0)
            mp_cost = int(chosen.get("mp_cost", 0) or 0)

            if mp_cost > 0:
                if char["mp"] < mp_cost:
                    raise HTTPException(status_code=400, detail="Not enough MP for this action!")
                await adb(db.apply_hp_mp_delta, req.user_id, mp_delta=-mp_cost)

            user_settings = await adb(db.get_settings, req.user_id)
            check_mode = user_settings.get("debug_check_mode", "off")
            stat_col = db.STAT_COLUMN.get(stat, "str_")
            hit_chance = chosen.get("hit_chance")
            if chosen.get("choice_type") == "dialogue" or chosen.get("action_category") == "dialogue":
                dialogue_mode = user_settings.get("dialogue_mode", "balanced")
                if dialogue_mode == "casual":
                    req_val = max(1, req_val - 2)
                elif dialogue_mode == "challenging":
                    req_val += 2

            from mechanics.world.mobility import get_session_dialogue_partners
            sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
            target_candidates = list(sess_dp)
            if chosen.get("target_npc") and str(chosen["target_npc"]).strip() and chosen["target_npc"] not in target_candidates:
                target_candidates.append(chosen["target_npc"])
            if target_candidates and isinstance(session, dict) and session.get("id"):
                from mechanics.combat.traits import get_combined_dc_modifiers
                from mechanics.social.persona import calculate_intimate_action_dc_modifier
                for dp_name in target_candidates:
                    if dp_name:
                        c_rec = await adb(db.get_contact, session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                        if c_rec:
                            c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                            t_mods = get_combined_dc_modifiers(c_traits)
                            req_val += t_mods.get(stat, 0)
                            app_rec = c_rec.get("appearance", {})
                            if isinstance(app_rec, dict):
                                req_val += calculate_intimate_action_dc_modifier(chosen.get("label") or chosen.get("text") or "", app_rec)
            req_val = max(1, req_val)
            if hit_chance is not None:
                import random
                rate = hit_chance
                roll = random.uniform(0, 100)
                succeeded = roll <= rate
                tier = "success" if succeeded else "fail"
                if roll > 90 and succeeded: tier = "crit_success"
                if roll < 10 and not succeeded: tier = "crit_fail"
                res = skill_check.CheckResult(chance=rate, roll=roll, tier=tier, tier_label=tier.replace('_', ' ').title(), succeeded=succeeded, requirement=req_val)
            elif stat in ("NONE", "FREE") or req_val <= 0:
                res = skill_check.CheckResult(chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True)
                rate = 100
            else:
                rate = skill_check.success_chance(char[stat_col], req_val, check_mode=check_mode)
                res = skill_check.resolve_check(char[stat_col], req_val, char["luk"], check_mode=check_mode)

            action = {
                "user_id": req.user_id,
                "character_name": char["name"],
                "char": dict(char),
                "stat": stat,
                "requirement": req_val,
                "mp_cost": mp_cost,
                "mp_spent": mp_cost,
                "rate": rate,
                "check": res,
                "label": chosen.get("label", ""),
                "success": res.succeeded,
                "tier": res.tier,
                "crit": res.tier in ("crit_success", "crit_fail"),
                "roll": res.roll,
                "text": chosen.get("label", ""),
                "choice_type": chosen.get("choice_type", ""),
                "action_category": chosen.get("action_category", ""),
                "spell_id": chosen.get("spell_id", ""),
                "combat_target": combat_target or chosen.get("combat_target"),
                "is_quest_action": bool(chosen.get("is_quest_action")),
                "is_climax_action": bool(chosen.get("is_climax_action")),
                "quest_id": chosen.get("quest_id", ""),
                "sub_obj_id": chosen.get("sub_obj_id"),
                "stage_index": chosen.get("stage_index"),
                "contract_type": chosen.get("contract_type", ""),
                "item_name": chosen.get("item_name", ""),
                "item": chosen.get("item"),
                "item_consumed": chosen.get("item_consumed", False),
                "intent": intent or chosen.get("intent"),
                "target_npc": target_npc or chosen.get("target_npc"),
            }
        elif custom_action_text:
            inventory = await adb(db.get_inventory, req.user_id)
            classification = await game_engine.classify_custom_action(session, char, inventory, custom_action_text)
            stat = classification["stat"]
            req_val = classification["requirement"]
            mp_cost = classification.get("mp_cost", 0)

            if mp_cost > 0:
                if char["mp"] < mp_cost:
                    raise HTTPException(status_code=400, detail="Not enough MP for this action!")
                await adb(db.apply_hp_mp_delta, req.user_id, mp_delta=-mp_cost)

            user_settings = await adb(db.get_settings, req.user_id)
            check_mode = user_settings.get("debug_check_mode", "off")
            stat_col = db.STAT_COLUMN.get(stat, "str_")
            hit_chance = classification.get("hit_chance") if isinstance(classification, dict) else None
            if isinstance(classification, dict) and classification.get("action_category") in ("dialogue", "romantic_confession", "social_invite", "party_recruit", "affection"):
                dialogue_mode = user_settings.get("dialogue_mode", "balanced")
                if dialogue_mode == "casual":
                    req_val = max(1, req_val - 2)
                elif dialogue_mode == "challenging":
                    req_val += 2
            if hit_chance is not None:
                import random
                rate = hit_chance
                roll = random.uniform(0, 100)
                succeeded = roll <= rate
                tier = "success" if succeeded else "fail"
                if roll > 90 and succeeded: tier = "crit_success"
                if roll < 10 and not succeeded: tier = "crit_fail"
                res = skill_check.CheckResult(chance=rate, roll=roll, tier=tier, tier_label=tier.replace('_', ' ').title(), succeeded=succeeded, requirement=req_val)
            elif stat in ("NONE", "FREE") or req_val <= 0:
                res = skill_check.CheckResult(chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True)
                rate = 100
            else:
                rate = skill_check.success_chance(char[stat_col], req_val, check_mode=check_mode)
                res = skill_check.resolve_check(char[stat_col], req_val, char["luk"], check_mode=check_mode)

            action = {
                "user_id": req.user_id,
                "character_name": char["name"],
                "char": dict(char),
                "stat": stat,
                "requirement": req_val,
                "mp_cost": mp_cost,
                "mp_spent": mp_cost,
                "rate": rate,
                "check": res,
                "label": custom_action_text,
                "success": res.succeeded,
                "tier": res.tier,
                "crit": res.tier in ("crit_success", "crit_fail"),
                "roll": res.roll,
                "text": custom_action_text,
                "type": "custom",
                "combat_target": combat_target,
                "active_recall": classification.get("_active_recall") if isinstance(classification, dict) else None,
                "is_quest_action": False,
                "is_climax_action": False,
                "quest_id": "",
                "sub_obj_id": None,
                "stage_index": None,
                "contract_type": "",
                "item_name": "",
                "item": None,
                "item_consumed": False,
            }
        else:
            raise HTTPException(status_code=400, detail="Must provide choice_index, direct_choice, or custom_action_text")

        if combat_target and not action.get("combat_target"):
            action["combat_target"] = combat_target

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

            turn_response = await TurnService.resolve_action(req.session_id, req.user_id, action, mode=mode, stream_callback=stream_callback)

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
            raw_choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_choices,
                scenario=turn_response.session.get("scenario", "fantasy"),
                location=outcome.get("location") or turn_response.session.get("current_location", ""),
                char=dict(char) if char else None,
                dialogue_partner=effective_partner,
                current_npcs=effective_npcs,
                session_id=req.session_id,
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
                dialogue_partner=partner_arg
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

        return {"success": True, "session": enriched_session}


# -----------------------------------------------------------------------------
# Adventure Save / Checkpoint Endpoints
# -----------------------------------------------------------------------------
@router.get("/api/saves/{user_id}")
async def list_saves(user_id: int):
    """Lists all adventure save slots for the user's active character."""
    saves = await adb(db.list_adventure_saves, user_id)
    return {"saves": [dict(s) for s in saves]}


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
    if current_loc:
        process_llm_location_update(session_id, current_loc, scen_key, char_name=char_name)

    zones_summary = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    curr_z, curr_p, curr_sub = (
        parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)
        if current_loc else ("", "", "")
    )

    enriched_zones = []
    active_quest_destinations = []
    for z in zones_summary:
        z_copy = dict(z)
        z_name = z_copy.get("zone_name", "")
        is_same_zone = bool(curr_z and curr_z.lower() == z_name.lower())
        primaries = []
        for p in z_copy.get("primary_locations", []):
            p_copy = dict(p)
            p_copy["travel_tag"] = "Instant Local" if is_same_zone else "Inter-Zone Travel"
            p_copy["is_current_place"] = bool(
                is_same_zone and curr_p and curr_p.lower() == (p_copy.get("name") or "").lower()
            )
            primaries.append(p_copy)
            for qm in (p_copy.get("quest_markers") or []):
                active_quest_destinations.append({
                    "zone_name": z_name,
                    "place_name": p_copy.get("name", ""),
                    "value": p_copy.get("value") or f"{z_name} ➔ {p_copy.get('name', '')}",
                    "marker": qm,
                    "quest_tag": p_copy.get("quest_tag", ""),
                    "is_current_place": p_copy["is_current_place"],
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

