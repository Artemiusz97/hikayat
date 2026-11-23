from __future__ import annotations

import asyncio
import json
import character_data as cd
import db
from db import adb
import game_engine
import scenario_data
from mechanics.combat.merchant import apply_merchant_encounter_result
from typing import Any, Callable, Dict, List, Optional
from .models import _get_turn_service, log, logger

async def start_adventure(
    user_id: int,
    *,
    character_id: Optional[int] = None,
    scenario: Optional[str] = None,
    tags: Optional[Any] = None,
    mode: str = "solo",
    capacity: Optional[int] = None,
    slot: Optional[int] = 1,
    char_class: Optional[str] = None,
    class_description: Optional[str] = None,
    weapon_name: Optional[str] = None,
    weapon_description: Optional[str] = None,
    starter_loadout: Optional[Dict[str, Any]] = None,
    starter_loadout_builder: Optional[Callable[..., Any]] = None,
    starting_faction: Optional[str] = None,
    origin_mode: Optional[str] = None,
    student_grade: Optional[str] = None,
    attribute: Optional[str] = None,
    combat_archetype: Optional[str] = None,
    ability_medium: Optional[str] = None,
    stats_override: Optional[Dict[str, Optional[int]]] = None,
    appearance: Optional[Dict[str, Any]] = None,
    breast_size: Optional[str] = None,
    penis_size: Optional[str] = None,
    asset_texture: Optional[str] = None,
    schedule_chapter_plan: bool = True,
) -> Dict[str, Any]:
    """Shared headless new-adventure embarkation pipeline used by HTTP API and playthrough sweeps."""
    canonical_id = await adb(db.resolve_canonical_user_id, user_id)
    char = None
    if character_id is not None:
        char = await adb(db.get_character_by_id, int(character_id))
        if not char:
            raise LookupError("Character not found. Create a character first!")
        if int(char.get("user_id") or 0) != int(canonical_id):
            raise PermissionError("Forbidden: character belongs to another user.")
        if not char.get("is_active"):
            switched = await adb(db.switch_character, canonical_id, int(char["id"]))
            if switched:
                char = switched
    if not char:
        char = await adb(db.get_character, canonical_id)
    if not char:
        raise LookupError("Character not found. Create a character first!")

    pre_embark_snap = await adb(db.snapshot_embark_rollback_state, char["id"])
    prev_active_sid = char.get("active_session_id")
    target_slot = slot if slot and 1 <= int(slot) <= 6 else 1
    existing_in_slot = await adb(db.get_character_session_in_slot, char["id"], target_slot)

    eff_mode = (mode or "solo").lower()
    if eff_mode == "multi":
        eff_mode = "turn"
    if eff_mode not in ["solo", "turn", "sync"]:
        eff_mode = "solo"

    user_settings = await adb(db.get_user_settings, canonical_id)
    verbosity = user_settings.get("verbosity", "vivid")
    narrative_pacing = user_settings.get("narrative_pacing", "balanced")
    dialogue_mode = user_settings.get("dialogue_mode", "adaptive")
    image_gen_enabled = user_settings.get("image_gen_enabled", 0)
    choices_style = user_settings.get("choices_style", "dropdown")
    result_display = user_settings.get("result_display", "detailed")
    show_percentages = user_settings.get("show_percentages", 1)
    language = user_settings.get("narration_language") or user_settings.get("language", "en")
    narration_language = language

    raw_scen = scenario or (char.get("scenario") if isinstance(char, dict) else None)
    scenario_key = scenario_data.resolve_scenario_key(raw_scen)
    if tags:
        from scenario_data import resolve_scenario_or_custom_key
        scenario_key = resolve_scenario_or_custom_key(tags)

    session_id: Optional[int] = None
    try:
        await adb(db.reset_character_for_new_adventure, canonical_id, scenario_key, False)

        is_anomalous_scen = scenario_data.is_anomalous_incursions_scenario(scenario_key)
        is_anom_hs = scenario_data.is_anomalous_high_school_scenario(scenario_key)
        char_app = char.get("appearance") or {}
        if isinstance(char_app, str):
            try:
                char_app = json.loads(char_app)
            except Exception:
                char_app = {}
        eff_origin = (origin_mode or char_app.get("origin_mode") or "").lower()
        eff_student_grade = student_grade or char_app.get("student_grade") or "Sophomore"
        if is_anom_hs and (eff_origin == "student" or (starting_faction or "").strip() in ("student_freelancer", "student")):
            chosen_starting_faction = "student_freelancer"
        else:
            chosen_starting_faction = (starting_faction or "public_agency").strip() if is_anomalous_scen else ""

        if is_anomalous_scen:
            scen_templates = await adb(cd.get_class_templates, scenario_key, chosen_starting_faction) or {}
        else:
            scen_templates = await adb(cd.get_class_templates, scenario_key) or {}
        safe_default_class = (
            (next(iter(scen_templates.keys())) if scen_templates else "Public Safety Field Hunter")
            if is_anomalous_scen
            else (
                "Student"
                if scenario_data.is_school_scenario(scenario_key)
                else (next(iter(scen_templates.keys())) if scen_templates else "Adventurer")
            )
        )
        existing_char_class = char.get("char_class")
        if char_class:
            eff_char_class = char_class
        elif not class_description and (not existing_char_class or existing_char_class not in scen_templates):
            eff_char_class = safe_default_class
        else:
            eff_char_class = existing_char_class or safe_default_class

        if eff_char_class:
            if isinstance(starter_loadout, dict) and len(starter_loadout) > 0 and callable(starter_loadout_builder):
                eff_loadout = await adb(
                    starter_loadout_builder,
                    starter_loadout,
                    scenario_key,
                    eff_char_class,
                    char.get("gender", "Male"),
                    char.get("race", "Human"),
                    chosen_starting_faction,
                )
            else:
                eff_loadout = None
            if not eff_loadout:
                eff_loadout = await adb(
                    cd.generate_starter_equipment_loadout,
                    scenario_key,
                    eff_char_class,
                    char.get("gender", "Male"),
                    char.get("race", "Human"),
                    weapon_name or "",
                    3,
                    chosen_starting_faction,
                )
            eff_starting_items = await adb(
                cd.get_starting_items,
                scenario_key,
                eff_char_class,
                chosen_starting_faction,
            )
            await adb(
                db.apply_adventure_loadout,
                canonical_id,
                scenario_key,
                eff_char_class,
                class_description or "",
                weapon_name or "",
                weapon_description or "",
                eff_loadout,
                eff_starting_items,
                attribute,
                combat_archetype,
                ability_medium,
            )

        if (
            stats_override
            and any(v is not None for v in stats_override.values())
            and str(user_settings.get("debug_stat_mode") or "off").lower() == "off"
        ):
            raw_stats_row = await adb(db.get_raw_character_stats, char["id"])
            raw_defaults = {
                "str": int(raw_stats_row.get("str_") or cd.BASE_STAT_VALUE),
                "per": int(raw_stats_row.get("per_") or cd.BASE_STAT_VALUE),
                "end": int(raw_stats_row.get("end_") or cd.BASE_STAT_VALUE),
                "cha": int(raw_stats_row.get("cha") or cd.BASE_STAT_VALUE),
                "int": int(raw_stats_row.get("int_") or cd.BASE_STAT_VALUE),
                "agi": int(raw_stats_row.get("agi") or cd.BASE_STAT_VALUE),
                "luk": int(raw_stats_row.get("luk") or cd.BASE_STAT_VALUE),
            }
            stats = {
                k: int(stats_override[k]) if stats_override.get(k) is not None else raw_defaults[k]
                for k in ("str", "per", "end", "cha", "int", "agi", "luk")
            }
            for sv in stats.values():
                if sv < cd.BASE_STAT_VALUE or sv > cd.MAX_STAT_VALUE:
                    raise ValueError(
                        f"Each stat must be between {cd.BASE_STAT_VALUE} and {cd.MAX_STAT_VALUE}."
                    )
            base_budget = len(cd.STATS) * cd.BASE_STAT_VALUE + cd.POINT_BUY_POOL
            allowed_budget = max(base_budget, sum(raw_defaults.values()))
            if sum(stats.values()) > allowed_budget:
                raise ValueError("Stat allocation exceeds maximum allowed points!")
            if hasattr(db, "update_character_stats"):
                await adb(db.update_character_stats, canonical_id, stats)

        app_update = dict(appearance or {})
        if scenario_data.is_nsfw_scenario(scenario_key):
            if breast_size is not None:
                app_update["breast_size"] = breast_size
            if penis_size is not None:
                app_update["penis_size"] = penis_size
            if asset_texture is not None:
                app_update["asset_texture"] = asset_texture
        else:
            for anatomy_key in ("breast_size", "penis_size", "asset_texture"):
                app_update.pop(anatomy_key, None)
        if app_update:
            await adb(db.update_character_appearance, char["id"], app_update)

        default_cap = 1 if eff_mode == "solo" else max(2, capacity or 4)
        session_id = await adb(
            db.create_session,
            mode=eff_mode,
            capacity=default_cap if eff_mode != "solo" else (capacity or 1),
            host_user_id=canonical_id,
            scenario=scenario_key,
            verbosity=verbosity,
            dialogue_mode=dialogue_mode,
            image_gen_enabled=image_gen_enabled,
            choices_style=choices_style,
            result_display=result_display,
            show_percentages=show_percentages,
            language=language,
            narration_language=narration_language,
            character_id=char["id"],
            slot=target_slot,
            narrative_pacing=narrative_pacing,
            show_enemy_hp=int(user_settings.get("show_enemy_hp", 1)),
            show_enemy_intent=int(user_settings.get("show_enemy_intent", 1)),
        )

        await adb(db.add_session_member, session_id, canonical_id)
        await adb(db.set_session_active, session_id, [canonical_id])

        if is_anomalous_scen:
            from mechanics.world.anomalous_events import bootstrap_anomalous_session
            await adb(
                bootstrap_anomalous_session,
                session_id,
                scenario_key,
                canonical_id,
                chosen_starting_faction,
                char.get("name", ""),
                eff_origin,
                eff_student_grade,
            )

        char_row = await adb(db.get_character, canonical_id, settings=user_settings)
        inv = await adb(db.get_inventory, canonical_id, char=char_row) if char_row else []
        party = [(dict(char_row), inv)] if char_row else []
        session_row = await adb(db.get_session, session_id)
        session = dict(session_row)

        from mechanics.social.factions import ensure_session_factions_seeded
        await adb(ensure_session_factions_seeded, session_id, scenario_key)
        from mechanics.world.world_forge.seeder import forge_world_state
        await forge_world_state(session, party)

        async def _run_eager_ch1_plan(sq_qid: str) -> Any:
            try:
                from mechanics.narrative.chapter_plan import compile_or_apply_eager_quest_plan
                return await compile_or_apply_eager_quest_plan(
                    session_id, sq_qid, timeout_seconds=25.0, defer_apply=True
                )
            except Exception as _bg_plan_err:
                log.debug("Ch.1 eager ChapterPlan skipped: %s", _bg_plan_err)
                return None

        if schedule_chapter_plan:
            sq_ch1 = await adb(game_engine.ensure_story_quest_exists, session)
            sq_qid = str((sq_ch1 or {}).get("quest_id") or "")
            if sq_qid:
                eager_task = asyncio.create_task(_run_eager_ch1_plan(sq_qid))
                try:
                    scene = await game_engine.generate_opening_scene(session, party)
                    eager_plan = await eager_task
                finally:
                    if not eager_task.done():
                        eager_task.cancel()
                        await asyncio.gather(eager_task, return_exceptions=True)
                if eager_plan:
                    try:
                        from mechanics.narrative.chapter_plan import apply_chapter_plan_to_dossier
                        await adb(apply_chapter_plan_to_dossier, session_id, sq_qid, eager_plan)
                    except Exception as _apply_plan_err:
                        log.debug("Ch.1 eager ChapterPlan apply skipped: %s", _apply_plan_err)
            else:
                scene = await game_engine.generate_opening_scene(session, party)
        else:
            scene = await game_engine.generate_opening_scene(session, party)
        committed = await _get_turn_service().commit_opening_scene(
            session_id,
            session,
            party,
            scene,
            char_row=char_row,
            scenario_key=scenario_key,
        )
        scene = committed["scene"]
        if existing_in_slot:
            await adb(
                db.finalize_overwritten_slot_session,
                existing_in_slot["id"],
                session_id,
                canonical_id,
            )
    except Exception as e:
        log.error("Error generating opening scene: %s", e)
        try:
            if session_id is not None:
                await adb(db.delete_session, session_id)
            if pre_embark_snap is not None:
                await adb(db.restore_embark_rollback_state, pre_embark_snap)
            if prev_active_sid:
                prev_sess = await adb(db.get_session, prev_active_sid)
                if prev_sess and prev_sess.get("status") in ("active", "waiting"):
                    await adb(db.set_character_active_session, char["id"], prev_active_sid)
        except Exception as cleanup_err:
            logger.warning("Failed pruning aborted Turn-0 session %s: %s", session_id, cleanup_err)
        if isinstance(e, (ValueError, LookupError, PermissionError)):
            raise
        raise RuntimeError(f"Failed to generate scene: {str(e)}") from e

    updated_session = await adb(db.get_session, session_id)
    return {
        "session_id": session_id,
        "session": updated_session,
        "scene": scene,
        "character": char_row,
        "canonical_user_id": canonical_id,
        "scenario_key": scenario_key,
    }


async def commit_opening_scene(
    session_id: int,
    session: Dict[str, Any],
    party: List[Any],
    scene: Any,
    *,
    char_row: Optional[Dict[str, Any]] = None,
    scenario_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Single source of truth for persisting a Turn-0 opening scene (embark and retry)."""
    if getattr(scene, "model_dump", None):
        scene = scene.model_dump(exclude_unset=False)
    if not isinstance(scene, dict):
        scene = {}

    sess_dict = session if isinstance(session, dict) else {}
    eff_scenario = str(scenario_key or sess_dict.get("scenario") or "fantasy")

    await adb(game_engine.apply_quest_update, session_id, scene)

    raw_choices, narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
        scene, session=sess_dict
    )
    location = scene.get("location") or sess_dict.get("current_location") or ""
    _open_partners = (
        [partner_arg]
        if isinstance(partner_arg, str) and partner_arg.strip()
        else (list(partner_arg) if isinstance(partner_arg, list) else [])
    )
    raw_choices = await adb(
        game_engine.build_hybrid_turn_choices,
        raw_choices,
        session=sess_dict,
        party=party,
        result={
            **scene,
            "location": location,
            "npcs_present": npcs_arg,
            "dialogue_partners": _open_partners,
        },
    )
    init_node_id = scene.get("current_node_id")
    if not init_node_id and location:
        init_node_id = await adb(db.resolve_node_id_from_location, session_id, location)
    if not init_node_id:
        init_node_id = sess_dict.get("current_node_id")

    await adb(
        db.save_session_scene,
        session_id,
        scene_title,
        narrative,
        raw_choices,
        [],
        location=location,
        nearby_enemies=scene.get("nearby_enemies", []),
        current_npcs=npcs_arg,
        dialogue_partner=partner_arg,
        current_node_id=init_node_id,
        focal_point=scene.get("focal_point", ""),
    )

    lead_char = char_row if isinstance(char_row, dict) else (party[0][0] if party and isinstance(party[0][0], dict) else {})
    char_id = int(lead_char.get("id") or 0) if isinstance(lead_char, dict) else 0
    enemy_names = {
        game_engine._get_npc_name(e).lower()
        for e in (scene.get("nearby_enemies") or [])
        if e
    }
    open_party_names: set[str] = set()
    for sc_p in (sess_dict.get("party") or []):
        sp_obj = sc_p[0] if isinstance(sc_p, (list, tuple)) and sc_p else sc_p
        if isinstance(sp_obj, dict) and sp_obj.get("name") and not sp_obj.get("user_id"):
            open_party_names.add(str(sp_obj["name"]).strip().lower())
    if isinstance(lead_char, dict) and lead_char.get("name"):
        open_party_names.discard(str(lead_char["name"]).strip().lower())

    await adb(
        db.batch_commit_opening_npcs,
        session_id,
        char_id,
        npcs_arg or [],
        location=location,
        scenario_key=eff_scenario,
        enemy_names=enemy_names,
        open_party_names=open_party_names,
        narrative=narrative,
    )
    merchant = None
    if "merchant_encounter" in scene:
        merchant = await adb(apply_merchant_encounter_result, session_id, scene.get("merchant_encounter"))
    return {
        "scene": scene,
        "scene_title": scene_title,
        "narrative": narrative,
        "choices": raw_choices,
        "npcs": npcs_arg,
        "dialogue_partner": partner_arg,
        "location": location,
        "current_node_id": init_node_id,
        "merchant": merchant,
    }
