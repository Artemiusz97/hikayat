from __future__ import annotations

import copy
import json
import logging
import asyncio
import os
import random
import re
import tempfile
import time
from typing import Dict, List, Any, Optional, Tuple, Callable
import httpx
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, ConfigDict, Field
import character_data as cd
import db
from db import adb
import game_engine
import llm_client
import scenario_data
from character_data import XP_REWARDS
from mechanics.combat.merchant import apply_merchant_encounter_result
from mechanics.social.relationships import is_contact_eligible
from services import crash_capture

log = logging.getLogger(__name__)
logger = log


def _is_llm_unavailable_exception(exc: BaseException) -> bool:
    """Return True only when an exception originates from upstream LLM/network unavailability."""
    if isinstance(exc, (OpenAIAPIError, httpx.HTTPError, TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, RuntimeError) and "all llm candidate models in fallback chain failed" in str(exc).lower():
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_llm_unavailable_exception(cause)
    return False


_BACKGROUND_TASKS: set[asyncio.Task] = set()


class TurnResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    success: bool
    session: Dict[str, Any]
    outcome: Dict[str, Any]          # Always a dict — outcome is coerced before storing here
    action: Dict[str, Any]
    actions: List[Dict[str, Any]] = []
    items_gained_by_user: Dict[Any, List[str]]   # {user_id: [item_name, ...]}
    xp_gained: int
    levels_gained: List[int]
    xp_by_user: Dict[Any, int] = {}
    levels_by_user: Dict[Any, List[int]] = {}
    new_char: Dict[str, Any]
    scene_persisted: bool = False
    scene_title: str = ""
    next_narrative: str = ""
    cleaned_choices: List[Dict[str, Any]] = Field(default_factory=list)


class TurnService:
    @staticmethod
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

        prev_active_sid = char.get("active_session_id")
        target_slot = slot if slot and 1 <= int(slot) <= 6 else 1
        existing_in_slot = await adb(db.get_character_session_in_slot, char["id"], target_slot)
        if existing_in_slot:
            if prev_active_sid == existing_in_slot["id"]:
                prev_active_sid = None
            await adb(db.finish_session, existing_in_slot["id"])

        eff_mode = (mode or "solo").lower()
        if eff_mode == "multi":
            eff_mode = "turn"
        if eff_mode not in ["solo", "turn", "sync"]:
            eff_mode = "solo"

        user_settings = await adb(db.get_user_settings, canonical_id)
        verbosity = user_settings.get("verbosity", "vivid")
        dialogue_mode = user_settings.get("dialogue_mode", "balanced")
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
            def _fetch_raw_char_stats(cid: int) -> dict:
                with db.get_conn() as conn:
                    r = conn.execute(
                        "SELECT str_, per_, end_, cha, int_, agi, luk FROM characters WHERE id=?",
                        (int(cid),),
                    ).fetchone()
                    return dict(r) if r else {}

            raw_stats_row = await adb(_fetch_raw_char_stats, char["id"])
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

        try:
            scene = await game_engine.generate_opening_scene(session, party)
            await adb(game_engine.apply_quest_update, session_id, scene)
            if isinstance(scene, dict) and "merchant_encounter" in scene:
                await adb(apply_merchant_encounter_result, session_id, scene.get("merchant_encounter"))
            raw_choices, narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
                scene, session=session
            )
            _open_partners = (
                [partner_arg]
                if isinstance(partner_arg, str) and partner_arg.strip()
                else (list(partner_arg) if isinstance(partner_arg, list) else [])
            )
            raw_choices = await adb(
                game_engine.build_hybrid_turn_choices,
                raw_choices,
                session=session,
                party=party,
                result={
                    **(scene if isinstance(scene, dict) else {}),
                    "location": scene.get("location") or session.get("current_location") or "",
                    "npcs_present": npcs_arg,
                    "dialogue_partners": _open_partners,
                },
            )
            await adb(
                db.save_session_scene,
                session_id,
                scene_title,
                narrative,
                raw_choices,
                [],
                location=scene.get("location") or session.get("current_location"),
                nearby_enemies=scene.get("nearby_enemies"),
                current_npcs=npcs_arg,
                dialogue_partner=partner_arg,
                current_node_id=scene.get("current_node_id") or session.get("current_node_id"),
            )
            if schedule_chapter_plan:
                try:
                    sq_ch1 = await adb(db.get_active_story_quest, session_id)
                    if sq_ch1 and sq_ch1.get("quest_id"):
                        from mechanics.narrative.chapter_plan import schedule_background_chapter_plan
                        schedule_background_chapter_plan(session_id, str(sq_ch1["quest_id"]))
                except Exception as _bg_plan_err:
                    log.debug("Ch.1 background ChapterPlan schedule skipped: %s", _bg_plan_err)
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
                    b_info["met_in_person"] = True
                    if is_contact_eligible(
                        name=n_name,
                        role=b_info.get("role", ""),
                        description=b_info.get("description", ""),
                        scenario=scenario_key,
                        session_id=session_id,
                    ):
                        await adb(
                            db.upsert_contact,
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
                        m_val = npc.get("mannerisms", "") if isinstance(npc, dict) else ""
                        if not m_val and isinstance(b_info, dict):
                            m_val = b_info.get("mannerisms", "")
                        await adb(
                            db.upsert_lorebook_entity,
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
            log.error("Error generating opening scene: %s", e)
            try:
                await adb(db.delete_session, session_id)
                if prev_active_sid:
                    prev_sess = await adb(db.get_session, prev_active_sid)
                    if prev_sess and prev_sess.get("status") in ("active", "waiting"):
                        await adb(db.set_character_active_session, char["id"], prev_active_sid)
            except Exception as cleanup_err:
                logger.warning("Failed pruning aborted Turn-0 session %s: %s", session_id, cleanup_err)
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

    @staticmethod
    async def _finalize_and_save_scene(
        session_id: int,
        session_obj: Dict[str, Any],
        outcome: Dict[str, Any],
        lead_char: Optional[Dict[str, Any]],
        history: List[Dict[str, Any]],
        mode: Optional[str] = None,
        is_retry: bool = False,
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Single source of truth for extracting, sanitizing, and persisting post-turn scene state."""
        sess_dict = session_obj if isinstance(session_obj, dict) else {}
        raw_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
            outcome, session=sess_dict
        )
        if isinstance(outcome, dict) and outcome.get("fallback_reason") == "empty_prose":
            warn_prefix = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n"
            if not str(next_narrative or "").startswith("⚠️ *The engine struggled"):
                next_narrative = warn_prefix + (next_narrative or "")

        effective_partner = sess_dict.get("dialogue_partner") if partner_arg is ... else partner_arg
        effective_npcs = sess_dict.get("current_npcs", []) if npcs_arg is None else npcs_arg

        if isinstance(outcome, dict) and outcome.get("_hybrid_choices_built") and raw_choices:
            cleaned_choices = list(raw_choices)
        else:
            cleaned_choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_choices,
                scenario=sess_dict.get("scenario", "fantasy"),
                location=(outcome.get("location") if isinstance(outcome, dict) else None) or sess_dict.get("current_location", ""),
                char=dict(lead_char) if isinstance(lead_char, dict) else None,
                dialogue_partner=effective_partner,
                current_npcs=effective_npcs,
                session_id=session_id,
                departed_npcs=(
                    outcome.get("departed_characters") or outcome.get("departed_npcs")
                    if isinstance(outcome, dict)
                    else None
                ),
            )
            cleaned_choices = list(cleaned_choices or [])

        if isinstance(outcome, dict):
            outcome["next_narrative"] = next_narrative
            outcome["scene_title"] = scene_title

        if is_retry or mode == "sync":
            await adb(db.clear_pending_picks, session_id)
        elif mode in ("turn", "multi"):
            await adb(db.advance_turn, session_id)

        await adb(
            db.save_session_scene,
            session_id,
            scene_title,
            next_narrative,
            cleaned_choices,
            list(history or []),
            location=outcome.get("location") if isinstance(outcome, dict) else None,
            nearby_enemies=outcome.get("nearby_enemies") if isinstance(outcome, dict) else None,
            current_npcs=npcs_arg,
            dialogue_partner=partner_arg,
            current_node_id=outcome.get("current_node_id") if isinstance(outcome, dict) else None,
            focal_point=outcome.get("focal_point") if isinstance(outcome, dict) else None,
            combat_threat_ledger=outcome.get("combat_threat_ledger") if isinstance(outcome, dict) else None,
            combat_boss_telegraph=outcome.get("combat_boss_telegraph") if isinstance(outcome, dict) else None,
        )
        return scene_title, next_narrative, cleaned_choices

    @staticmethod
    async def _reconcile_client_direct_choice(
        session_id: int,
        user_id: int,
        session: Optional[Dict[str, Any]],
        char: Dict[str, Any],
        choices: Optional[List[Dict[str, Any]]],
        raw_dc: Dict[str, Any],
        combat_target: Optional[str],
        is_stealth_req: bool,
    ) -> Dict[str, Any]:
        """
        Reconcile an untrusted HTTP client `direct_choice` dict against authoritative
        server choices, tactical combat decks, spell registry, or world-map nodes.
        """
        cleaned = dict(raw_dc)
        raw_lbl = str(cleaned.get("label") or cleaned.get("text") or "").strip()
        raw_id = str(cleaned.get("id") or "").strip()

        # 1. Exact match against server-persisted session choices
        if isinstance(choices, list):
            for sc in choices:
                if not isinstance(sc, dict) and not hasattr(sc, "get"):
                    continue
                sc_id = str(sc.get("id") or "").strip()
                sc_lbl = str(sc.get("label") or sc.get("text") or "").strip()
                if (raw_id and sc_id and raw_id == sc_id) or (raw_lbl and sc_lbl and raw_lbl == sc_lbl):
                    return dict(sc)

        # Strip client mechanical overrides & privileged quest/spoofing keys
        for _strip_k in (
            "stat",
            "requirement",
            "hit_chance",
            "is_basic_strike",
            "free_pass",
            "_mp_already_deducted",
            "_gold_already_deducted",
            "quest_id",
            "sub_obj_id",
            "stage_index",
            "is_quest_action",
            "is_climax_action",
            "is_story_quest",
            "_python_verified_quest",
            "triggers_loot_roll",
            "breakthrough_leveraged",
            "_server_stamped",
            "clue_pair_ids",
            "approach",
            "is_anomaly_inquiry",
            "topic_id",
            "category",
            "is_covert_ability",
            "is_direct_reply",
            "_seed_reconciled",
            "_pact_cast_meta",
            "pact_hp_cost",
            "pact_credit_cost",
            "is_lethal_overdraw",
            "appraisal_state",
        ):
            cleaned.pop(_strip_k, None)

        _combat_tactic_ok = (
            isinstance(session, dict)
            and bool(session.get("nearby_enemies"))
            and str(cleaned.get("incursion_action") or "").strip().lower()
            in {
                "subdue",
                "combat_persuade",
                "sever_tether",
                "folklore_offering_rite",
                "exploit_taboo",
                "invoke_patron_authority",
                "accept_boss_pact_surrender",
            }
        )
        if not _combat_tactic_ok:
            for _inc_k in ("incursion_action", "incursion_id", "breach_id"):
                cleaned.pop(_inc_k, None)

        inventory = await adb(db.get_inventory, user_id) or []

        # 2. Match against server-generated Tactical Combat Deck when enemies are present
        enemies = (session.get("nearby_enemies") if isinstance(session, dict) else None) or []
        active_enemies = [e for e in enemies if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
        if active_enemies:
            try:
                from mechanics.narrative.choice_generator import generate_categorized_combat_actions
                target_e = None
                if combat_target:
                    target_e = next(
                        (e for e in active_enemies if str(e.get("name") or "").strip().lower() == str(combat_target).strip().lower() or (e.get("id") is not None and str(e.get("id")) == str(combat_target))),
                        None,
                    )
                cand_enemies = [target_e] if target_e else active_enemies
                party_arg = [(dict(char), list(inventory))]
                for enem in cand_enemies:
                    deck = generate_categorized_combat_actions(
                        party=party_arg,
                        monster=enem,
                        location=(session.get("current_location") if isinstance(session, dict) else None) or "area",
                        scenario=(session.get("scenario") if isinstance(session, dict) else None) or "fantasy",
                        session=session,
                    ) or {}
                    deck_cards: List[Dict[str, Any]] = []
                    for k_list in ("attacks", "magic", "tactics"):
                        deck_cards.extend([c for c in (deck.get(k_list) or []) if isinstance(c, dict)])
                    if isinstance(deck.get("flee"), dict):
                        deck_cards.append(deck["flee"])
                    for dc_card in deck_cards:
                        dc_lbl = str(dc_card.get("label") or dc_card.get("text") or "").strip()
                        if (
                            (raw_lbl and dc_lbl and raw_lbl == dc_lbl)
                            or (cleaned.get("spell_id") and dc_card.get("spell_id") == cleaned.get("spell_id"))
                            or (cleaned.get("incursion_action") and dc_card.get("incursion_action") == cleaned.get("incursion_action"))
                        ):
                            matched_card = dict(dc_card)
                            if combat_target and not matched_card.get("combat_target"):
                                matched_card["combat_target"] = combat_target
                            return matched_card
            except Exception as _deck_err:
                log.debug("Combat deck reconciliation skipped: %s", _deck_err)

        # 3. Authoritative Spell Registry lookup when `spell_id` is supplied
        spell_id = str(cleaned.get("spell_id") or "").strip()
        if spell_id:
            if spell_id.startswith("pact_"):
                if not session_id:
                    cleaned.pop("spell_id", None)
                    sp_def = None
                else:
                    try:
                        from mechanics.pacts import build_pact_spell_def, build_pact_spell_id, get_patron_by_id
                        active_pacts_rec = await adb(db.get_player_active_pacts, int(session_id), int(user_id))
                        scen_rec = str((session or {}).get("scenario") or "anomalous_incursions")
                        cont_rec = list((session or {}).get("contained_anomalies_log") or []) if isinstance(session, dict) else []
                        sp_def = None
                        for p_row_rec in (active_pacts_rec or []):
                            pat_rec = get_patron_by_id(str(p_row_rec.get("patron_id") or ""), scenario_or_key=scen_rec, contained_records=cont_rec)
                            if pat_rec and build_pact_spell_id(pat_rec, int(p_row_rec.get("tier") or 1)) == spell_id:
                                sp_def = build_pact_spell_def(pat_rec, int(p_row_rec.get("tier") or 1))
                                cleaned["is_pact_skill"] = True
                                cleaned["contract_key"] = p_row_rec.get("contract_key", "")
                                cleaned["patron_id"] = pat_rec["patron_id"]
                                break
                    except Exception:
                        sp_def = None
            else:
                sp_def = None
                try:
                    from mechanics.combat.spells.registry import get_spell
                    from mechanics.combat.spells.awakened_kits import get_actor_spell
                    skill_prog = await adb(db.get_skill_progress, char)
                    sp_def = get_actor_spell(spell_id, skill_prog) or get_spell(spell_id)
                except Exception:
                    sp_def = None
            if isinstance(sp_def, dict):
                sp_stat = str(sp_def.get("stat") or "INT").upper()
                if sp_stat not in db.STAT_COLUMN:
                    sp_stat = "INT"
                cleaned["stat"] = sp_stat
                cleaned["requirement"] = max(5, int(sp_def.get("requirement", 5) or 5))
                cleaned["mp_cost"] = int(sp_def.get("mp_cost", 0) or 0)
                cleaned["is_basic_strike"] = spell_id.startswith("awk_basic_")
                cleaned["action_category"] = cleaned.get("action_category") or "magic"
                cleaned["label"] = raw_lbl or str(sp_def.get("name") or spell_id)
                return cleaned
            cleaned.pop("spell_id", None)

        # 3b. Authoritative Realty Property Deed Purchase Reconciliation
        if not active_enemies and session_id and (
            str(cleaned.get("intent") or "").strip().lower() == "property_purchase"
            or cleaned.get("property_id")
        ):
            from mechanics.world.locations.realty_catalog import resolve_realty_entry, find_realty_by_node_id
            prop_id_req = str(cleaned.get("property_id") or "").strip()
            cat_entry = resolve_realty_entry(prop_id_req, session_or_id=session or session_id) if prop_id_req else None
            if not cat_entry and cleaned.get("target_node_id"):
                cat_entry = find_realty_by_node_id(str(cleaned["target_node_id"]), session_or_id=session or session_id)
            if cat_entry:
                cleaned["stat"] = "FREE"
                cleaned["requirement"] = 0
                cleaned["mp_cost"] = 0
                cleaned["intent"] = "property_purchase"
                cleaned["action_category"] = "movement"
                cleaned["property_id"] = cat_entry["property_id"]
                cleaned["price"] = int(cat_entry["price"])
                cleaned["target_node_id"] = cat_entry["bedroom_node_id"]
                cleaned["target_location"] = f"{cat_entry['zone_name']} ➔ {cat_entry['name']} ➔ {cat_entry['bedroom_name']}"
                cleaned["label"] = f"[For Sale — {cat_entry['price']}g] Purchase {cat_entry['name']} Deed"
                return cleaned
            cleaned.pop("property_id", None)
            cleaned.pop("price", None)

        # 4. Verified World Node Fast-Travel
        if cleaned.get("target_node_id") and session_id:
            cand_nid = str(cleaned["target_node_id"])
            wn_row = await adb(db.get_world_node, session_id, cand_nid)
            if wn_row and not active_enemies:
                cleaned["stat"] = "FREE"
                cleaned["requirement"] = 0
                cleaned["mp_cost"] = 0
                cleaned["intent"] = cleaned.get("intent") or "fast_travel"
                cleaned["action_category"] = cleaned.get("action_category") or "movement"
                cleaned["label"] = raw_lbl or f"Travel to {wn_row.get('name', cand_nid)}"
                return cleaned
            cleaned.pop("target_node_id", None)

        # 5. Verified Inventory Item Use (ownership validated strictly below at stat == 'ITEM')
        if str(raw_dc.get("stat") or "").upper() == "ITEM" or cleaned.get("item_name"):
            cleaned["stat"] = "ITEM"
            cleaned["requirement"] = 0
            cleaned["mp_cost"] = 0
            cleaned["label"] = raw_lbl or f"Use {cleaned.get('item_name', 'item')}"
            return cleaned

        # 6. Verified Non-Combat Wait/Rest or Present-NPC Dialogue Initiation
        raw_intent = str(cleaned.get("intent") or "").strip().lower()
        if not active_enemies and raw_intent in ("wait_time", "rest_sleep"):
            cleaned["stat"] = "NONE"
            cleaned["requirement"] = 0
            cleaned["mp_cost"] = 0
            cleaned["label"] = raw_lbl or "Wait"
            return cleaned
        if not active_enemies and (raw_intent == "dialogue_init" or raw_dc.get("_npc_speak_choice")):
            t_npc = str(cleaned.get("target_npc") or "").strip().lower()
            curr_npcs = (session.get("current_npcs") if isinstance(session, dict) else None) or []
            npc_present = any(
                t_npc and t_npc == str(game_engine._get_npc_name(n) or "").strip().lower()
                for n in curr_npcs
            )
            if npc_present:
                cleaned["stat"] = "NONE"
                cleaned["requirement"] = 0
                cleaned["mp_cost"] = 0
                cleaned["label"] = raw_lbl or f"Speak with {cleaned.get('target_npc')}"
                return cleaned

        if not active_enemies and isinstance(session, dict) and isinstance(session.get("_dealt_social_seeds"), list):
            cand_tid = str(raw_dc.get("topic_id") or "").strip()
            if cand_tid:
                matched_seed = next(
                    (
                        s for s in session["_dealt_social_seeds"]
                        if isinstance(s, dict) and str(s.get("topic_id") or "").strip() == cand_tid
                    ),
                    None,
                )
                if matched_seed:
                    s_stat = str(matched_seed.get("stat") or "CHA").upper()
                    cleaned["stat"] = s_stat if s_stat in db.STAT_COLUMN else "CHA"
                    cleaned["requirement"] = max(3, min(12, int(matched_seed.get("dc") or 6)))
                    cleaned["mp_cost"] = max(0, int(matched_seed.get("mp_cost") or 0))
                    cleaned["topic_id"] = cand_tid
                    cleaned["category"] = str(matched_seed.get("category") or cleaned.get("category") or "")
                    cleaned["target_npc"] = str(matched_seed.get("target_npc") or cleaned.get("target_npc") or "")
                    cleaned["is_covert_ability"] = bool(matched_seed.get("is_covert_ability"))
                    cleaned["is_direct_reply"] = bool(matched_seed.get("is_direct_reply"))
                    cleaned["_seed_reconciled"] = True
                    cleaned["label"] = raw_lbl or "Speak"
                    return cleaned

        # 7. UI Tactical/Stealth/Dialogue Fallback Cards & Unmatched Payloads -> Deterministic Rolled Check (DC >= 6, NEVER FREE/NONE)
        act_cat_hint = str(cleaned.get("action_category") or "").strip().lower()
        choice_type_hint = str(cleaned.get("choice_type") or "").strip().lower()
        raw_stat_hint = str(raw_dc.get("stat") or "").strip().upper()
        try:
            raw_req_val = int(raw_dc.get("requirement", 0) or 0)
        except (TypeError, ValueError):
            raw_req_val = 0
        enforced_req = max(6, min(20, raw_req_val))

        inferred_stat = ""
        try:
            from mechanics.narrative.intent import IntentCategory, classify_action_intent
            parsed_intent = classify_action_intent(raw_lbl or "Act")
            p_cat = getattr(parsed_intent, "category", None)
            if p_cat in (
                IntentCategory.AFFECTION_TOUCH,
                IntentCategory.ROMANTIC_CONFESSION,
                IntentCategory.SOCIAL_INVITE,
                IntentCategory.PARTY_RECRUIT,
            ):
                inferred_stat = "CHA"
            elif p_cat == IntentCategory.STEALTH_COVERT:
                inferred_stat = "INT" if getattr(parsed_intent, "sub_target", "") == "lockpick" else "AGI"
            elif p_cat == IntentCategory.INVESTIGATE_CLUE:
                inferred_stat = "PER"
        except Exception:
            inferred_stat = ""

        if is_stealth_req or act_cat_hint == "stealth":
            c_stat = "AGI"
        elif active_enemies or act_cat_hint in ("attack", "tactic", "combat_attack"):
            c_stat = raw_stat_hint if raw_stat_hint in db.STAT_COLUMN else "STR"
        elif inferred_stat in db.STAT_COLUMN:
            c_stat = inferred_stat
        elif choice_type_hint in ("dialogue", "social", "intimate", "romance"):
            c_stat = "CHA"
        elif raw_stat_hint in db.STAT_COLUMN:
            c_stat = raw_stat_hint
        else:
            c_stat = "PER"

        cleaned.update({
            "stat": c_stat,
            "requirement": enforced_req,
            "mp_cost": max(0, int(cleaned.get("mp_cost", 0) or 0)),
            "action_category": cleaned.get("action_category") or ("dialogue" if c_stat == "CHA" else "custom"),
            "intent": cleaned.get("intent") or "general_action",
            "label": raw_lbl or "Action",
        })
        return cleaned

    @staticmethod
    async def prepare_and_roll_action(
        session_id: int,
        user_id: int,
        raw_pick: Dict[str, Any],
        session: Optional[Dict[str, Any]] = None,
        char: Optional[Dict[str, Any]] = None,
        choices: Optional[List[Dict[str, Any]]] = None,
        enforce_explicit_mp: bool = True,
    ) -> Dict[str, Any]:
        """
        Single source of truth for pre-turn action classification, MP/Item/Gold deduction,
        NPC trait & intimate DC modifiers, and deterministic skill check rolling across Web and Discord.
        """
        import random
        import skill_check
        from mechanics.narrative.intent import classify_action_intent
        from mechanics.world.mobility import get_session_dialogue_partners
        from mechanics.combat.traits import get_combined_dc_modifiers
        from mechanics.social.persona import calculate_intimate_action_dc_modifier

        # Idempotency guard: if raw_pick is already a resolved action with a CheckResult, return it directly
        if (
            isinstance(raw_pick, dict)
            and not raw_pick.get("_untrusted_client_pick")
            and raw_pick.get("check") is not None
            and raw_pick.get("char")
        ):
            chk = raw_pick["check"]
            if isinstance(chk, dict):
                raw_pick = dict(raw_pick)
                raw_pick["check"] = skill_check.CheckResult(
                    chance=int(chk.get("chance") if chk.get("chance") is not None else 100),
                    roll=float(chk.get("roll") if chk.get("roll") is not None else 100.0),
                    tier=str(chk.get("tier") or "success"),
                    tier_label=str(chk.get("tier_label") or "Success"),
                    succeeded=bool(chk.get("succeeded", True)),
                    requirement=int(chk.get("requirement", raw_pick.get("requirement", 0)) or 0),
                )
            return raw_pick

        _caller_supplied_session = session is not None
        if session is None:
            sess_row = await adb(db.get_session, session_id)
            if not sess_row:
                raise ValueError(f"Session {session_id} not found")
            session = dict(sess_row)

        if char is None:
            char_row = await adb(db.get_character, user_id)
            if not char_row:
                raise LookupError("Character not found")
            char = dict(char_row)
        else:
            char = dict(char)

        if isinstance(session, dict) and session.get("id") and "_world_events_snapshot" not in session:
            try:
                session["_world_events_snapshot"] = await adb(db.get_world_events_snapshot, int(session["id"]))
            except Exception:
                session["_world_events_snapshot"] = {}

        # Normalize payload fields from Web or Discord
        choice_index = raw_pick.get("choice_index")
        custom_text = raw_pick.get("custom_action_text") or raw_pick.get("custom_text")
        direct_choice = raw_pick.get("direct_choice")
        combat_target = raw_pick.get("combat_target")
        req_intent = raw_pick.get("intent")
        req_target_npc = raw_pick.get("target_npc") or raw_pick.get("target_name")
        req_skip_minutes = raw_pick.get("skip_minutes")
        req_sleep_mode = raw_pick.get("sleep_mode")
        is_item_action = bool(raw_pick.get("is_item_action") or raw_pick.get("stat") == "ITEM")
        is_stealth_req = bool(
            raw_pick.get("is_stealth")
            or (raw_pick.get("stance") == "stealth")
            or (isinstance(raw_pick.get("action"), dict) and (raw_pick["action"].get("is_stealth") or raw_pick["action"].get("stance") == "stealth"))
        )

        if isinstance(raw_pick.get("action"), dict):
            nested = raw_pick["action"]
            if choice_index is None and "choice_index" in nested:
                choice_index = nested.get("choice_index")
            if not custom_text:
                custom_text = nested.get("custom_action_text") or nested.get("custom_text")
            if direct_choice is None and isinstance(nested.get("direct_choice"), dict):
                direct_choice = nested.get("direct_choice")
            if not combat_target and nested.get("combat_target"):
                combat_target = nested.get("combat_target")
            if not req_intent and nested.get("intent"):
                req_intent = nested.get("intent")
            if req_skip_minutes is None and nested.get("skip_minutes") is not None:
                req_skip_minutes = nested.get("skip_minutes")
            if not req_sleep_mode and nested.get("sleep_mode"):
                req_sleep_mode = nested.get("sleep_mode")

        user_settings = await adb(db.get_settings, user_id) or {}
        check_mode = user_settings.get("debug_check_mode", "off")
        dialogue_mode = user_settings.get("dialogue_mode", "balanced")

        chosen: Dict[str, Any] = {}
        classification: Dict[str, Any] = {}
        is_custom = False
        is_standalone_direct_choice = False
        action_type = "choice"

        if choices is None and isinstance(session, dict):
            choices = session.get("choices") or []

        if is_item_action and not direct_choice and choice_index is None:
            chosen = {
                "stat": "ITEM",
                "requirement": 0,
                "mp_cost": 0,
                "label": custom_text or f"Use {raw_pick.get('item_name', 'item')}",
                "action_category": "item",
                "intent": "general_action",
                "sub_intent": "use_item",
                "item_name": raw_pick.get("item_name", ""),
                "item": raw_pick.get("item"),
                "item_consumed": raw_pick.get("item_consumed", True),
            }
        elif choice_index is not None and isinstance(choices, list) and 0 <= choice_index < len(choices):
            chosen = dict(choices[choice_index])
        elif isinstance(direct_choice, dict) and direct_choice:
            is_standalone_direct_choice = True
            if raw_pick.get("_untrusted_client_pick"):
                chosen = await TurnService._reconcile_client_direct_choice(
                    session_id=session_id,
                    user_id=user_id,
                    session=session,
                    char=char,
                    choices=choices,
                    raw_dc=direct_choice,
                    combat_target=combat_target,
                    is_stealth_req=is_stealth_req,
                )
            else:
                chosen = dict(direct_choice)
                # Strip privileged server-only spoofing keys on un-indexed client direct_choice payloads
                for _priv_k in (
                    "quest_id",
                    "sub_obj_id",
                    "stage_index",
                    "is_quest_action",
                    "is_climax_action",
                    "is_story_quest",
                    "_python_verified_quest",
                    "triggers_loot_roll",
                    "breakthrough_leveraged",
                    "_server_stamped",
                    "clue_pair_ids",
                    "approach",
                    "is_anomaly_inquiry",
                ):
                    chosen.pop(_priv_k, None)
                _combat_tactic_ok = (
                    isinstance(session, dict)
                    and bool(session.get("nearby_enemies"))
                    and str(chosen.get("incursion_action") or "").strip().lower()
                    in {"subdue", "combat_persuade", "sever_tether", "folklore_offering_rite", "exploit_taboo"}
                )
                if not _combat_tactic_ok:
                    for _inc_k in ("incursion_action", "incursion_id", "breach_id"):
                        chosen.pop(_inc_k, None)
                if chosen.get("spell_id"):
                    try:
                        from mechanics.combat.spells.registry import get_spell
                        sp_def = get_spell(str(chosen["spell_id"]))
                        if isinstance(sp_def, dict) and sp_def.get("mp_cost") is not None:
                            chosen["mp_cost"] = int(sp_def["mp_cost"])
                    except Exception:
                        pass
                if chosen.get("target_node_id") and session_id:
                    cand_nid = str(chosen["target_node_id"])
                    wn_row = await adb(db.get_world_node, session_id, cand_nid)
                    if not wn_row:
                        chosen.pop("target_node_id", None)
        elif choice_index is not None:
            if not enforce_explicit_mp and isinstance(choices, list) and choices:
                chosen = dict(choices[0])
            elif not enforce_explicit_mp:
                chosen = {"stat": "PER", "requirement": 6, "mp_cost": 0, "label": "Proceed forward"}
            else:
                raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")
        elif custom_text:
            is_custom = True
            action_type = "custom"
            if (
                not (isinstance(session, dict) and session.get("nearby_enemies"))
                and (req_skip_minutes is not None or req_sleep_mode in ("sleep", "nap", "wait") or req_intent in ("wait_time", "rest_sleep"))
            ):
                classification = {
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "action_category": "rest" if req_sleep_mode in ("sleep", "nap") or req_intent == "rest_sleep" else "wait",
                    "intent": req_intent or ("rest_sleep" if req_sleep_mode in ("sleep", "nap") else "wait_time"),
                }
                chosen = dict(classification)
                chosen["label"] = custom_text
                chosen["text"] = custom_text
            else:
                inventory = await adb(db.get_inventory, user_id)
                classification = await game_engine.classify_custom_action(session, char, inventory, custom_text)
                if not isinstance(classification, dict):
                    classification = dict(classification) if hasattr(classification, "items") else {}
                chosen = dict(classification)
                if not classification.get("fast_path") and not classification.get("_verified_ambient_intent"):
                    if str(chosen.get("stat") or "").upper() not in db.STAT_COLUMN:
                        chosen["stat"] = "PER"
                    _in_dlg_custom = bool(isinstance(session, dict) and get_session_dialogue_partners(session))
                    chosen["requirement"] = (
                        max(3, min(12, int(chosen.get("requirement", 5) or 5)))
                        if _in_dlg_custom
                        else max(6, int(chosen.get("requirement", 6) or 6))
                    )
                chosen["label"] = custom_text
                chosen["text"] = custom_text
        else:
            raise ValueError("Must provide choice_index, direct_choice, or custom_action_text")

        if (
            not is_custom
            and not chosen.get("_seed_reconciled")
            and chosen.get("topic_id")
            and isinstance(session, dict)
            and isinstance(session.get("_dealt_social_seeds"), list)
        ):
            _tid_match = next(
                (
                    s for s in session["_dealt_social_seeds"]
                    if isinstance(s, dict) and str(s.get("topic_id") or "").strip() == str(chosen.get("topic_id") or "").strip()
                ),
                None,
            )
            if _tid_match:
                _s_st = str(_tid_match.get("stat") or chosen.get("stat") or "CHA").upper()
                chosen["stat"] = _s_st if _s_st in db.STAT_COLUMN else "CHA"
                chosen["requirement"] = max(3, min(12, int(_tid_match.get("dc") or chosen.get("requirement") or 6)))
                chosen["mp_cost"] = max(0, int(_tid_match.get("mp_cost") or 0))
                chosen["category"] = str(_tid_match.get("category") or chosen.get("category") or "")
                chosen["target_npc"] = str(_tid_match.get("target_npc") or chosen.get("target_npc") or "")
                chosen["is_covert_ability"] = bool(_tid_match.get("is_covert_ability"))
                chosen["is_direct_reply"] = bool(_tid_match.get("is_direct_reply"))
                chosen["_seed_reconciled"] = True

        stat = str(chosen.get("stat", "STR") or "STR").upper()
        req_val = int(chosen.get("requirement", 5 if not is_custom else 6) or 0)
        mp_cost = int(chosen.get("mp_cost", 0) or 0)
        mp_spent = mp_cost
        label_text = str(chosen.get("label") or chosen.get("text") or custom_text or "Action")
        if session_id and str(chosen.get("intent") or req_intent or "").strip().lower() == "property_purchase":
            from mechanics.world.locations.realty_catalog import resolve_realty_entry, find_realty_by_node_id
            _prop_id_cand = str(chosen.get("property_id") or raw_pick.get("property_id") or "").strip()
            _cat_prop = resolve_realty_entry(_prop_id_cand, session_or_id=session or session_id) if _prop_id_cand else None
            if not _cat_prop and chosen.get("target_node_id"):
                _cat_prop = find_realty_by_node_id(str(chosen["target_node_id"]), session_or_id=session or session_id)
            if not _cat_prop:
                raise ValueError("Invalid or unavailable property deed.")
            _avail_g = int((char or {}).get("gold") or 0)
            if _avail_g < int(_cat_prop["price"]):
                raise ValueError(f"Insufficient gold to purchase {_cat_prop['name']} ({_cat_prop['price']}g required, {_avail_g}g available).")
            stat = "FREE"
            req_val = 0
            mp_cost = 0
            mp_spent = 0
            chosen["stat"] = "FREE"
            chosen["requirement"] = 0
            chosen["mp_cost"] = 0
            chosen["intent"] = "property_purchase"
            chosen["property_id"] = _cat_prop["property_id"]
            chosen["price"] = int(_cat_prop["price"])
            chosen["target_node_id"] = _cat_prop["bedroom_node_id"]
            chosen["target_location"] = f"{_cat_prop['zone_name']} ➔ {_cat_prop['name']} ➔ {_cat_prop['bedroom_name']}"
            label_text = f"[For Sale — {_cat_prop['price']}g] Purchase {_cat_prop['name']} Deed"

        # ── Invariant 12 (A4): Restraint Hard-Gate on Travel / Movement ──────
        if session_id:
            try:
                from mechanics.world.locations.movement import is_movement_action
                from mechanics.social.physical_state import find_player_actor_key, can_actor_travel_or_dual_wield
                act_intent_low = str(chosen.get("intent") or req_intent or "").lower()
                is_break_attempt = act_intent_low in ("break_free", "companion_free") or any(
                    w in label_text.lower() for w in ("break free", "struggle", "slip out", "untie", "cut bonds", "cut my bonds")
                )
                if not is_break_attempt and (act_intent_low in ("movement", "travel", "fast_travel") or is_movement_action(label_text)):
                    phys_now = await adb(db.get_session_physical_state, session_id)
                    if phys_now and isinstance(phys_now.get("actors"), dict):
                        pk_now = find_player_actor_key(phys_now["actors"], party=[char], session_id=session_id)
                        p_actor_now = phys_now["actors"].get(pk_now) if pk_now else None
                        if p_actor_now:
                            can_move, move_reason = can_actor_travel_or_dual_wield(p_actor_now)
                            if not can_move:
                                raise ValueError(move_reason)
            except ValueError:
                raise
            except Exception:
                pass

        # ── Awakened Resonance 3-Pip Ultimate Gate, 0-MP Basic Strike & Entity Contracts ─
        chosen_spell_id = str(chosen.get("spell_id") or "").strip()
        if chosen_spell_id.startswith("awk_basic_") or (chosen.get("is_basic_strike") and not chosen_spell_id):
            mp_cost = 0
            mp_spent = 0
        elif chosen_spell_id.startswith("pact_") and isinstance(session, dict):
            mp_cost = 0
            mp_spent = 0
            sid_pact = int(session.get("id") or 0)
            if sid_pact and user_id:
                from mechanics.pacts import build_pact_spell_id, compute_pact_cast_costs, get_patron_by_id
                active_pacts_pr = list(char.get("active_pacts") or [])
                if not active_pacts_pr:
                    active_pacts_pr = await adb(db.get_player_active_pacts, sid_pact, int(user_id))
                scen_pr = str(session.get("scenario") or "anomalous_incursions")
                cont_pr = list(session.get("contained_anomalies_log") or [])
                matched_p_row = None
                matched_pat = None
                for _pr_row in (active_pacts_pr or []):
                    _pat_cand = get_patron_by_id(str(_pr_row.get("patron_id") or ""), scenario_or_key=scen_pr, contained_records=cont_pr)
                    if _pat_cand and build_pact_spell_id(_pat_cand, int(_pr_row.get("tier") or 1)) == chosen_spell_id:
                        matched_p_row = _pr_row
                        matched_pat = _pat_cand
                        break
                if not matched_p_row or not matched_pat:
                    if not is_custom and enforce_explicit_mp:
                        raise PermissionError("You do not hold an active Entity Contract for that invocation!")
                else:
                    cost_info = compute_pact_cast_costs(char, matched_p_row, matched_pat)
                    if not cost_info["can_invoke"] and not is_custom and enforce_explicit_mp:
                        raise PermissionError(cost_info["blocked_reason"] or "Cannot invoke this Entity Contract right now!")
                    chosen["is_pact_skill"] = True
                    chosen["is_lethal_overdraw"] = bool(cost_info["is_lethal_overdraw"])
                    chosen["_pact_cast_meta"] = {
                        **cost_info,
                        "contract_key": matched_p_row["contract_key"],
                        "patron_id": matched_p_row["patron_id"],
                        "patron_name": matched_pat["canonical_name"],
                    }
        elif chosen_spell_id and isinstance(session, dict):
            import scenario_data as _ts_sd
            if _ts_sd.is_anomalous_incursions_scenario(session.get("scenario", "")):
                from mechanics.combat.spells.registry import get_spell as _ts_get_spell
                from mechanics.combat.awakened_resonance import get_starting_encounter_pips
                _ts_sp = _ts_get_spell(chosen_spell_id)
                if isinstance(_ts_sp, dict) and _ts_sp.get("is_ultimate") and int(_ts_sp.get("pip_cost", 0) or 0) > 0:
                    mp_cost = 0
                    mp_spent = 0
                    req_pips = int(_ts_sp.get("pip_cost", 3))
                    pips_map = session.get("player_resonance_pips") if isinstance(session.get("player_resonance_pips"), dict) else {}
                    uid_key = str(user_id)
                    cur_pips = int(pips_map[uid_key]) if uid_key in pips_map else get_starting_encounter_pips(int(char.get("level", 1) or 1))
                    if cur_pips < req_pips and not is_custom and enforce_explicit_mp:
                        raise PermissionError(f"Not enough Resonance Pips for Signature Ultimate ({cur_pips}/{req_pips} Pips)!")

        # ── MP Validation & Improvisation Rule (staged for atomic commit) ─────
        if mp_cost > 0:
            if char.get("mp", 0) < mp_cost:
                if not is_custom and enforce_explicit_mp:
                    raise PermissionError("Not enough MP for this action!")
                # Freeform custom text (or Discord fallback): improvise with 0 MP and +2 DC penalty
                label_text += " (couldn't afford the full effort, improvised instead)"
                mp_spent = 0
                if stat not in ("NONE", "FREE", "ITEM"):
                    req_val += 2

        # ── Gold Spending / Bribe Clamping Rule (staged for atomic commit) ───
        requested_gold = int(
            chosen.get("gold_spent")
            or chosen.get("gold_cost")
            or classification.get("gold_spent")
            or 0
        )
        avail_gold = max(0, int(char.get("gold", 0) or 0))
        actual_gold_spent = 0
        gold_shortfall_note = ""
        if requested_gold > 0 and requested_gold > avail_gold:
            req_val += 3
            gold_shortfall_note = (
                f"[SYSTEM NOTE: Player attempted to spend/offer {requested_gold} gold, "
                f"but only had {avail_gold} gold available (+3 DC penalty applied).]"
            )

        # ── Item Validation & Staged Consumption Rule ────────────────────────
        target_item_name = raw_pick.get("item_name") or chosen.get("item_name") or ""
        target_item_obj = raw_pick.get("item") or chosen.get("item")
        item_was_consumed = bool(chosen.get("item_consumed", False))

        if stat == "ITEM":
            inventory = await adb(db.get_inventory, user_id)
            if not target_item_name and not target_item_obj:
                label_lower = label_text.lower()
                for inv_item in (inventory or []):
                    iname = inv_item.get("name", "")
                    if iname and iname.lower() in label_lower:
                        target_item_name = iname
                        target_item_obj = inv_item
                        break
            if not target_item_name and isinstance(target_item_obj, dict):
                target_item_name = target_item_obj.get("name", "")
            if target_item_name:
                verified_inv_item = next(
                    (i for i in (inventory or []) if i.get("name", "").lower() == target_item_name.lower()),
                    None,
                )
                if verified_inv_item is not None:
                    target_item_obj = verified_inv_item
                elif is_standalone_direct_choice and enforce_explicit_mp:
                    raise PermissionError(f"Item '{target_item_name}' is not in your inventory!")
            if target_item_name and chosen.get("item_consumed", True) and target_item_obj is not None:
                item_was_consumed = True

        # ── Dialogue & Persona DC Modifiers ──────────────────────────────────
        act_cat = str(chosen.get("action_category") or ("custom" if is_custom else "")).strip()
        if (
            chosen.get("choice_type") == "dialogue"
            or act_cat in ("dialogue", "romantic_confession", "social_invite", "party_recruit", "affection", "disclosure_inquiry")
        ):
            if dialogue_mode == "casual":
                req_val = max(1, req_val - 2)
            elif dialogue_mode == "challenging":
                req_val += 2

        sess_dp = get_session_dialogue_partners(session) if isinstance(session, dict) else []
        explicit_target = (
            combat_target
            or req_target_npc
            or chosen.get("target_npc")
            or (classification.get("target_npc") if is_custom else None)
        )
        if not explicit_target:
            import namegen
            act_lbl = label_text.lower()
            named_dps = [
                dp for dp in sess_dp
                if dp and (
                    dp.lower() in act_lbl
                    or any(
                        re.search(rf"\b{re.escape(tok)}\b", act_lbl)
                        for tok in namegen.get_unique_person_tokens(dp, peer_names=sess_dp, min_len=2)
                    )
                )
            ]
            if len(named_dps) == 1:
                explicit_target = named_dps[0]

        target_candidates = [explicit_target] if explicit_target else list(sess_dp)
        if target_candidates and isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM"):
            is_romantic_attempt = (
                act_cat in ("romantic_confession", "affection", "intimate_act")
                or any(
                    kw in label_text.lower()
                    for kw in ("confess", "kiss", "flirt", "seduc", "intimate", "make out", "ask out", "romantic")
                )
            )
            for dp_name in target_candidates:
                if dp_name:
                    c_rec = await adb(db.get_contact, session["id"], str(dp_name).lower().replace(" ", "_"), char.get("id", 0))
                    if c_rec:
                        c_traits = c_rec.get("unlocked_traits") or c_rec.get("traits") or []
                        t_mods = get_combined_dc_modifiers(c_traits)
                        req_val += t_mods.get(stat, 0)
                        app_rec = c_rec.get("appearance", {})
                        if isinstance(app_rec, dict):
                            req_val += calculate_intimate_action_dc_modifier(label_text, app_rec)
                    if is_romantic_attempt:
                        try:
                            from mechanics.social import relationship_graph as rg
                            curr_p = await adb(rg.get_current_partner, session["id"], rg.canonical_person_key(dp_name))
                            if curr_p and not rg.is_player_person_key(curr_p.get("person_key")):
                                req_val += 3
                        except Exception:
                            pass

        if isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM") and target_candidates:
            _primary_dp = str(target_candidates[0] or "").strip()
            if _primary_dp and (
                sess_dp
                or act_cat in ("dialogue", "romantic_confession", "social_invite", "affection", "disclosure_inquiry")
                or is_custom
            ):
                try:
                    from mechanics.social import pacing as _ts_pacing
                    from mechanics.social.conversation_choices import _infer_social_category_from_choice
                    _cur_day_ts = int(session.get("current_day") or 1)
                    _cur_min_ts = int(session.get("current_minute") or 480)
                    _comp_ts = await adb(
                        lambda: _ts_pacing.sync_and_get_composure(
                            int(session["id"]),
                            _primary_dp,
                            current_day=_cur_day_ts,
                            current_minute=_cur_min_ts,
                            scenario=str(session.get("scenario") or "fantasy"),
                        )
                    )
                    _, _mood_dc_mod = _ts_pacing.derive_mood_and_dc_mod(
                        int(_comp_ts.get("current_composure", 100)),
                        int(_comp_ts.get("max_composure", 100)),
                        str(_comp_ts.get("composure_state") or "composed"),
                        clear_the_air_required=bool(int(_comp_ts.get("clear_the_air_required") or 0) == 1),
                    )
                    if is_custom or not chosen.get("_seed_reconciled"):
                        req_val += int(_mood_dc_mod or 0)
                        if (
                            int(_comp_ts.get("current_composure", 100)) <= 0
                            and _ts_pacing.is_composure_locked_out(_comp_ts, _cur_day_ts, _cur_min_ts)
                            and str(_comp_ts.get("composure_state") or "") == "cold_shoulder"
                        ):
                            req_val += 3

                    if is_custom:
                        _lbl_c = label_text.lower()
                        _inf_cat = str(chosen.get("category") or "").strip().lower() or _infer_social_category_from_choice({"label": label_text})
                        chosen["category"] = _inf_cat
                        if any(w in _lbl_c for w in ("insult", "mock", "humiliate", "belittle", "sneer", "pathetic", "worthless", "trash")):
                            chosen["is_cruel"] = True
                        if mp_cost > 0 and any(w in _lbl_c for w in ("charm", "mind", "telepath", "hypno", "compel", "glamour", "suggest")):
                            chosen["is_covert_ability"] = True

                        _cid_ts = int((char or {}).get("id") or 0)
                        _t_map = await adb(
                            db.get_social_topic_states,
                            int(session["id"]),
                            _cid_ts,
                            _primary_dp,
                        )
                        _kw_map = {
                            "work_calling": ("work", "job", "duty", "duties", "club", "career", "calling", "profession"),
                            "passions_likes": ("like", "likes", "hobby", "hobbies", "passion", "favorite", "enjoy"),
                            "pet_peeves": ("dislike", "dislikes", "hate", "annoy", "pet peeve"),
                            "daily_routine": ("schedule", "routine", "usual", "hang out", "where do you"),
                            "family_roots": ("family", "hometown", "parents", "sibling", "brother", "sister", "childhood"),
                        }
                        _matched_locked_tid = ""
                        for _tid_cand, _tr in (_t_map or {}).items():
                            if _ts_pacing.is_topic_available(
                                int(session["id"]),
                                _cid_ts,
                                _primary_dp,
                                _tid_cand,
                                current_day=_cur_day_ts,
                                current_minute=_cur_min_ts,
                                preloaded_states=_t_map,
                            ):
                                continue
                            _slug = _tid_cand.split(":", 1)[1] if ":" in _tid_cand else _tid_cand
                            if (
                                (chosen.get("topic_id") and str(chosen["topic_id"]) == _tid_cand)
                                or (_slug in _kw_map and any(kw in _lbl_c for kw in _kw_map[_slug]))
                                or (_tid_cand.startswith(f"{_inf_cat}:") and str(_tr.get("last_outcome") or "") in ("fail", "crit_fail"))
                            ):
                                _matched_locked_tid = _tid_cand
                                break
                        if _matched_locked_tid:
                            chosen["_topic_locked_attempt"] = True
                            chosen["topic_id"] = _matched_locked_tid
                            req_val += 2
                        elif not chosen.get("topic_id"):
                            chosen["topic_id"] = f"{_inf_cat}:custom_chat"
                        req_val = max(3, min(15, req_val))
                except Exception as _soc_m_err:
                    log.debug("Social custom metering skipped: %s", _soc_m_err)

        if isinstance(session, dict) and session.get("id") and stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
            try:
                from mechanics.world.world_events.modifiers import (
                    compute_event_dc_modifier,
                    compute_rumor_defensive_dc,
                )
                _we_snap_dc = session.get("_world_events_snapshot")
                req_val += compute_event_dc_modifier(
                    _we_snap_dc,
                    stat=stat,
                    location_node_id=str(session.get("current_node_id") or ""),
                    is_stealth=is_stealth_req,
                )
                if stat == "CHA" and target_candidates:
                    req_val += compute_rumor_defensive_dc(_we_snap_dc, target=target_candidates)
            except Exception as _we_dc_err:
                log.debug("World event DC modifier skipped: %s", _we_dc_err)
            try:
                import scenario_data as _ts_pact_sd
                if (
                    not bool(session.get("nearby_enemies"))
                    and _ts_pact_sd.is_anomalous_incursions_scenario(session.get("scenario", ""))
                    and user_id
                ):
                    from mechanics.pacts import compute_pact_field_dc_modifier
                    _pacts_dc = list(char.get("active_pacts") or [])
                    if not _pacts_dc:
                        _pacts_dc = await adb(db.get_player_active_pacts, int(session["id"]), int(user_id))
                    if _pacts_dc:
                        req_val += compute_pact_field_dc_modifier(
                            _pacts_dc,
                            stat,
                            action_category=act_cat,
                            label_text=label_text,
                            scenario_or_key=session.get("scenario"),
                        )
            except Exception as _pact_dc_err:
                log.debug("Pact field DC modifier skipped: %s", _pact_dc_err)

        if isinstance(chosen, dict) and (chosen.get("intent") == "break_the_news" or chosen.get("_is_break_the_news")):
            try:
                from mechanics.world.world_events.social_hooks import record_break_the_news_gossip
                _btn_npc = str(explicit_target or (target_candidates[0] if target_candidates else "")).strip()
                if _btn_npc and isinstance(session, dict) and session.get("id"):
                    await adb(
                        record_break_the_news_gossip,
                        int(session["id"]),
                        int(session.get("current_day") or 1),
                        _btn_npc,
                        str(chosen.get("event_key") or ""),
                    )
            except Exception as _btn_err:
                log.debug("record_break_the_news_gossip skipped: %s", _btn_err)

        if stat not in ("NONE", "FREE", "ITEM") and req_val > 0:
            req_val = max(1, req_val)

        # ── Urgent Schedule Departure Hurry & Stage 2 Custom Auto-Fail ───────
        stage2_custom_auto_fail = False
        if target_candidates and isinstance(session, dict):
            from mechanics.social.conversation_choices import get_npc_departure_states, is_convince_stay_action
            from mechanics.narrative.intent import is_conversational_exit
            dep_states = get_npc_departure_states(session)
            if dep_states:
                for dp_name in target_candidates:
                    if not dp_name:
                        continue
                    dp_st = dep_states.get(re.sub(r"\s+", " ", str(dp_name).strip().lower()))
                    if not dp_st:
                        continue
                    stg = str(dp_st.get("stage") or "")
                    if stg == "stage_2_ultimatum" and is_custom:
                        stage2_custom_auto_fail = True
                        if stat in ("NONE", "FREE", ""):
                            stat = "CHA"
                        req_val = max(12, req_val)
                        break
                    elif stg == "stage_1_warning" and is_custom and not is_conversational_exit(label_text):
                        if is_convince_stay_action(label_text):
                            stat = "CHA"
                            req_val = max(6, req_val or 9)
                        elif stat in ("NONE", "FREE", "") or req_val <= 0:
                            stat = "CHA"
                            req_val = 9
                        elif stat != "ITEM":
                            req_val = min(15, max(7, req_val + 3))
                        break

        # ── Roll Skill Check ─────────────────────────────────────────────────
        stat_col = db.STAT_COLUMN.get(stat, "str_" if not is_custom else "agi_")
        hit_chance = chosen.get("hit_chance")
        if stage2_custom_auto_fail:
            res = skill_check.CheckResult(
                chance=0, roll=100.0, tier="fail", tier_label="Failed", succeeded=False, requirement=req_val
            )
            rate = 0
        elif stat == "ITEM":
            res = skill_check.CheckResult(
                chance=100, roll=100.0, tier="success", tier_label="Item Used", succeeded=True, requirement=req_val
            )
            rate = 100
        elif hit_chance is not None:
            rate = int(hit_chance)
            roll = round(random.uniform(0, 100), 1)
            if check_mode == "always_crit_success":
                tier, succeeded = "crit_success", True
            elif check_mode == "always_success":
                tier, succeeded = "success", True
            elif check_mode == "always_fail":
                tier, succeeded = "fail", False
            elif check_mode == "always_crit_fail":
                tier, succeeded = "crit_fail", False
            else:
                succeeded = roll <= rate
                crit_s_thresh = max(1, rate // 5)
                if succeeded and roll <= crit_s_thresh:
                    tier = "crit_success"
                elif succeeded:
                    tier = "success"
                elif roll >= 95:
                    tier = "crit_fail"
                else:
                    tier = "fail"
            res = skill_check.CheckResult(
                chance=rate,
                roll=roll,
                tier=tier,
                tier_label=tier.replace("_", " ").title(),
                succeeded=succeeded,
                requirement=req_val,
            )
        elif stat in ("NONE", "FREE") or req_val <= 0:
            res = skill_check.CheckResult(
                chance=100, roll=100.0, tier="success", tier_label="Success", succeeded=True, requirement=req_val
            )
            rate = 100
        else:
            stat_val = char.get(stat_col, 5)
            luk_val = char.get("luk", 3)
            rate = skill_check.success_chance(stat_val, req_val, check_mode=check_mode)
            res = skill_check.resolve_check(stat_val, req_val, luk_val, check_mode=check_mode)

        # ── Intent & Category Normalization ──────────────────────────────────
        act_intent = req_intent or chosen.get("intent") or (classification.get("intent") if is_custom else None)
        act_target = req_target_npc or chosen.get("target_npc") or (classification.get("target_npc") if is_custom else None)
        act_sub_intent = chosen.get("sub_intent") or (classification.get("sub_intent") if is_custom else "") or ""
        act_ends_dialogue = bool(chosen.get("ends_dialogue") or (classification.get("ends_dialogue") if is_custom else False))

        intent_source = "choice_tag" if (not is_custom and chosen.get("intent")) else ("utility_llm" if is_custom else "fallback")
        if not act_cat or act_cat == "custom" or not act_intent:
            if not act_intent:
                logger.warning("[TurnService] Action missing structured intent; falling back to regex classifier for '%s'", label_text)
                intent_source = "regex_fallback"
            parsed_i = classify_action_intent(label_text)
            if not act_cat or act_cat == "custom":
                act_cat = classification.get("action_category") or parsed_i.category.value
            if not act_intent:
                act_intent = parsed_i.category.value
            if not act_target and parsed_i.target_entity:
                act_target = parsed_i.target_entity
            if not act_sub_intent and parsed_i.sub_target:
                act_sub_intent = parsed_i.sub_target

        if act_intent == "dialogue_exit":
            act_ends_dialogue = True

        resolved_intent = {
            "intent": act_intent,
            "sub_intent": act_sub_intent,
            "target_npc": act_target or "",
            "ends_dialogue": act_ends_dialogue,
            "source": intent_source,
        }

        # ── Stealth Stance & Covert Action Resolution ─────────────────────────
        from mechanics.combat import is_in_combat as _ts_is_in_combat
        from mechanics.stealth import (
            get_session_stealth_state,
            is_actor_hidden,
            toggle_stealth_stance,
            break_stealth,
            apply_stealth_decay_turn,
            resolve_distraction_action,
            resolve_stealth_action,
            resolve_scene_environment_context,
        )

        st_state = get_session_stealth_state(session)
        prev_stealth_state = json.loads(json.dumps(st_state, default=str)) if isinstance(st_state, dict) else {}
        in_combat_now = bool(isinstance(session, dict) and _ts_is_in_combat(session))
        is_covert_intent = bool(act_intent == "stealth_covert" or act_cat == "stealth")
        actor_hidden_before = is_actor_hidden(session, user_id)
        effective_stealth = bool(
            is_stealth_req
            or is_covert_intent
            or (actor_hidden_before and raw_pick.get("stance") != "normal")
        )

        lbl_low = label_text.lower()
        stealth_outcome = None

        if not in_combat_now and isinstance(session, dict):
            # Assemble party + active companions for accurate companion noise math
            stealth_party = [(dict(char), [])]
            for comp_list_key in ("party_npcs", "temporary_companions"):
                for comp in (session.get(comp_list_key) or []):
                    if isinstance(comp, dict):
                        stealth_party.append((comp, []))
            actor_inventory: list | None = None
            if session.get("id"):
                try:
                    party_chars = await adb(db.get_session_characters, session["id"])
                    inv_by_cid = (
                        await adb(db.get_inventories_for_characters, party_chars)
                        if party_chars
                        else {}
                    )
                    for m_char in (party_chars or []):
                        if not isinstance(m_char, dict):
                            continue
                        m_cid = int(m_char["id"]) if m_char.get("id") is not None else -1
                        m_inv = inv_by_cid.get(m_cid, [])
                        if m_char.get("user_id") == user_id:
                            actor_inventory = m_inv
                        else:
                            stealth_party.append((dict(m_char), m_inv))
                except Exception:
                    pass

            if actor_inventory is None:
                actor_inventory = await adb(db.get_inventory, user_id, char)
            env_ctx = resolve_scene_environment_context(session)
            curr_min_st = session.get("current_minute", 480)
            base_req = int(chosen.get("requirement", req_val) or req_val) if not is_custom else int(classification.get("requirement", req_val) or req_val)
            dc_mod_stealth = max(0, int(req_val) - base_req)

            is_distraction_action = bool(
                is_covert_intent
                and any(k in lbl_low for k in ("distract", "diversion", "throw stone", "throw a stone", "small stone", "pebble", "noise distraction", "divert attention"))
            )
            is_freeze_blend_action = bool(
                effective_stealth
                and any(k in lbl_low for k in ("freeze & blend", "hold motionless", "hold still", "stay still in shadow"))
            )

            if is_distraction_action:
                if not is_actor_hidden(session, user_id) and is_stealth_req:
                    toggle_stealth_stance(session, True, user_id=user_id)
                stealth_outcome = resolve_distraction_action(
                    session=session,
                    actor_char=char,
                    equipped_items=actor_inventory,
                    current_minute=curr_min_st,
                    party=stealth_party,
                    environment=env_ctx,
                    check_mode=check_mode,
                    user_id=user_id,
                )
                res = stealth_outcome["check"]
                rate = res.chance
                effective_stealth = is_actor_hidden(session, user_id) or bool(is_stealth_req or is_covert_intent)
            elif is_freeze_blend_action:
                toggle_stealth_stance(session, True, user_id=user_id)
                apply_stealth_decay_turn(session, is_waiting_still=True)
            elif effective_stealth:
                is_loud_magic = bool(
                    (chosen.get("spell_id") or act_cat == "magic")
                    and not any(k in lbl_low for k in ("silent", "shadow", "stealth", "invisib", "muffle", "veil"))
                )
                if act_intent in ("rest_sleep", "dialogue_init"):
                    break_stealth(session, reason=act_intent, user_id=user_id)
                    effective_stealth = False
                elif is_loud_magic:
                    break_stealth(session, reason="unsuppressed_magic", user_id=user_id)
                    effective_stealth = False
                else:
                    if not is_actor_hidden(session, user_id):
                        toggle_stealth_stance(session, True, user_id=user_id)
                    is_covert_check = bool(
                        is_covert_intent
                        or any(w in lbl_low for w in ("sneak", "creep", "infiltrate", "pickpocket", "shadow step", "silent takedown", "slip past", "lockpick", "pick the lock"))
                        or (stat == "AGI" and not any(w in lbl_low for w in ("flee", "sprint", "dodge", "chase")))
                    )
                    if is_covert_check:
                        stealth_outcome = resolve_stealth_action(
                            session=session,
                            actor_char=char,
                            action_data={
                                "label": label_text,
                                "action_type": chosen.get("choice_type", "stealth"),
                                "custom_action_text": label_text,
                                "target_npc": act_target,
                            },
                            target_entity={"name": act_target} if act_target else None,
                            party=stealth_party,
                            equipped_items=actor_inventory,
                            current_minute=curr_min_st,
                            environment=env_ctx,
                            check_mode=check_mode,
                            dc_modifier=dc_mod_stealth,
                            user_id=user_id,
                        )
                        res = stealth_outcome["check"]
                        rate = res.chance
                        effective_stealth = is_actor_hidden(session, user_id)
                    else:
                        apply_stealth_decay_turn(session, is_waiting_still=("wait" in lbl_low))
            if not _caller_supplied_session and session.get("id") and session.get("stealth_state") != prev_stealth_state:
                await adb(db.update_session, session["id"], stealth_state=session["stealth_state"])

        # D7: Deduct gold_spent only on succeeded checks OR gamble forfeitures (staged for atomic commit)
        if requested_gold > 0:
            should_spend_gold = bool(res.succeeded or str(act_sub_intent or "").lower() == "gamble")
            actual_gold_spent = min(requested_gold, avail_gold) if should_spend_gold else 0

        act_dismisses_npc = str(
            chosen.get("dismisses_npc")
            or (classification.get("dismisses_npc") if is_custom else "")
            or ""
        ).strip()
        raw_skip = req_skip_minutes if req_skip_minutes is not None else (
            chosen.get("skip_minutes") if chosen.get("skip_minutes") is not None else chosen.get("wait_minutes")
        )
        action = dict(chosen) if not is_custom else {}
        action.update({
            "is_non_lethal": bool(session.get("non_lethal_mode") or action.get("is_non_lethal") or (isinstance(chosen, dict) and chosen.get("is_non_lethal"))),
            "user_id": user_id,
            "character_name": char.get("name", "Player"),
            "char": dict(char),
            "stat": stat,
            "requirement": req_val,
            "mp_cost": mp_cost,
            "mp_spent": mp_spent,
            "_mp_already_deducted": False,
            "gold_spent": actual_gold_spent,
            "_requested_gold": requested_gold,
            "_gold_already_deducted": False,
            "_gold_shortfall_note": gold_shortfall_note,
            "rate": rate,
            "check": res,
            "label": label_text,
            "success": res.succeeded,
            "tier": res.tier,
            "crit": res.tier in ("crit_success", "crit_fail"),
            "roll": res.roll,
            "text": label_text,
            "type": action_type,
            "choice_type": chosen.get("choice_type") or "",
            "action_category": act_cat,
            "intent": act_intent,
            "sub_intent": act_sub_intent,
            "target_npc": act_target or "",
            "ends_dialogue": act_ends_dialogue,
            "dismisses_npc": act_dismisses_npc,
            "_stage2_custom_auto_fail": stage2_custom_auto_fail,
            "resolved_intent": resolved_intent,
            "spell_id": chosen.get("spell_id") or "",
            "combat_target": combat_target or chosen.get("combat_target") or (classification.get("combat_target") if is_custom else None),
            "combat_tactical_archetype": chosen.get("combat_tactical_archetype") or (classification.get("combat_tactical_archetype", "") if is_custom else "") or "",
            "target_node_id": chosen.get("target_node_id") or "",
            "target_location": chosen.get("target_location") or (classification.get("target_location", "") if is_custom else "") or "",
            "spawns_npc_role": chosen.get("spawns_npc_role") or (classification.get("spawns_npc_role", "") if is_custom else "") or "",
            "triggers_loot_roll": bool(chosen.get("triggers_loot_roll") or (classification.get("triggers_loot_roll", False) if is_custom else False)),
            "is_quest_action": bool(chosen.get("is_quest_action", False)),
            "is_story_quest": bool(chosen.get("is_story_quest", False)),
            "is_climax_action": bool(chosen.get("is_climax_action", False)),
            "rush_climax": bool(chosen.get("rush_climax", False)),
            "off_hours_fallback": bool(chosen.get("off_hours_fallback", False)),
            "clue_source_id": str(chosen.get("clue_source_id") or ""),
            "is_bonus_clue": bool(chosen.get("is_bonus_clue", False)),
            "breakthrough_leveraged": bool(chosen.get("breakthrough_leveraged", False)),
            "clue_pair_ids": list(chosen.get("clue_pair_ids") or []),
            "quest_id": chosen.get("quest_id") or "",
            "sub_obj_id": chosen.get("sub_obj_id"),
            "stage_index": chosen.get("stage_index"),
            "contract_type": chosen.get("contract_type") or "",
            "item_name": target_item_name,
            "item": target_item_obj,
            "item_consumed": item_was_consumed,
            "_item_already_removed": False,
            "active_recall": classification.get("_active_recall") if is_custom else chosen.get("_active_recall"),
            "is_stealth": effective_stealth,
            "stance": "stealth" if effective_stealth else "normal",
            "stealth_state": session.get("stealth_state") if isinstance(session, dict) else None,
            "_prev_stealth_state": prev_stealth_state,
            "stealth_outcome": stealth_outcome,
            "skip_minutes": int(raw_skip) if raw_skip not in (None, "") else 0,
            "sleep_mode": str(req_sleep_mode or chosen.get("sleep_mode") or ""),
            "property_id": str(chosen.get("property_id") or ""),
            "price": int(chosen.get("price") or 0) if chosen.get("price") else 0,
            "topic_id": str(chosen.get("topic_id") or ""),
            "category": str(chosen.get("category") or ""),
            "is_covert_ability": bool(chosen.get("is_covert_ability")),
            "is_direct_reply": bool(chosen.get("is_direct_reply")),
            "is_cruel": bool(chosen.get("is_cruel")),
            "_topic_locked_attempt": bool(chosen.get("_topic_locked_attempt")),
        })
        if not action.get("active_recall") and isinstance(session, dict) and session.get("id") and label_text:
            from game_engine.turn.generation import extract_deterministic_recall_query
            recall_q = extract_deterministic_recall_query(label_text, session_id=session["id"])
            if recall_q:
                from db.memory import active_recall_search
                recall_hits = await adb(active_recall_search, session["id"], recall_q)
                if recall_hits:
                    action["active_recall"] = recall_hits
        return action

    @staticmethod
    async def resolve_action(
        session_id: int,
        user_id: int,
        action: Dict[str, Any],
        mode: str = "solo",
        stream_callback=None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnResponse:
        """
        Unifies the turn resolution process across Discord and Web API using non-blocking DB access.
        """
        if os.environ.get("HIKAYAT_CRASH_CAPTURE", "").strip() == "1" and not crash_capture.is_in_crash_capture():
            return await TurnService._resolve_action_with_crash_capture(
                session_id=session_id,
                user_id=user_id,
                action=action,
                mode=mode,
                stream_callback=stream_callback,
                actions=actions,
            )
        return await TurnService._resolve_action_inner(
            session_id=session_id,
            user_id=user_id,
            action=action,
            mode=mode,
            stream_callback=stream_callback,
            actions=actions,
        )

    @staticmethod
    async def _resolve_action_with_crash_capture(
        *,
        session_id: int,
        user_id: int,
        action: Dict[str, Any],
        mode: str = "solo",
        stream_callback=None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnResponse:
        """Captures pre-turn SQLite snapshot and LLM tape when `HIKAYAT_CRASH_CAPTURE=1`."""
        sess_meta = await adb(db.get_session, session_id) or {}
        scenario_val = str(sess_meta.get("scenario") or "fantasy")
        turn_num = int(sess_meta.get("turn_count") or 0) + 1
        action_copy = copy.deepcopy(action)
        actions_copy = copy.deepcopy(actions) if actions is not None else None
        rng_state_json = crash_capture.encode_rng_state(random.getstate())

        tf = tempfile.NamedTemporaryFile(prefix="hikayat_preturn_", suffix=".db", delete=False)
        pre_db_path = tf.name
        tf.close()
        try:
            await adb(crash_capture.snapshot_sqlite_to_file, db.DB_PATH, pre_db_path, read_only=True)
        except Exception as snap_err:
            log.warning("Crash-capture pre-turn snapshot failed: %s", snap_err)

        strict_mod = crash_capture.load_optional_strict_mode()
        strict_ctx = (
            strict_mod.capture()
            if (strict_mod is not None and callable(getattr(strict_mod, "level", None)) and strict_mod.level() > 0)
            else None
        )
        bundle_dir_env = os.environ.get("HIKAYAT_CRASH_DIR", "").strip() or None

        try:
            with crash_capture.crash_capture_scope(), llm_client.record_llm_tape() as tape:
                if strict_ctx is not None:
                    with strict_ctx as hits:
                        try:
                            resp = await TurnService._resolve_action_inner(
                                session_id=session_id,
                                user_id=user_id,
                                action=action,
                                mode=mode,
                                stream_callback=stream_callback,
                                actions=actions,
                            )
                        except BaseException as exc:
                            if not (isinstance(exc, ValueError) and str(exc) == "waiting_for_party"):
                                try:
                                    crash_capture.write_crash_bundle(
                                        bundle_root=bundle_dir_env,
                                        scenario=scenario_val,
                                        session_id=session_id,
                                        user_id=user_id,
                                        turn_number=turn_num,
                                        seed=None,
                                        stage="resolve_action",
                                        mode=mode,
                                        action=action_copy,
                                        actions=actions_copy,
                                        rng_state_json=rng_state_json,
                                        llm_tape=tape,
                                        strict_hits=list(hits),
                                        exc=exc,
                                        pre_turn_db_source=pre_db_path,
                                    )
                                except Exception as write_err:
                                    log.warning("Failed writing crash bundle: %s", write_err)
                            raise
                        if hits:
                            try:
                                crash_capture.write_crash_bundle(
                                    bundle_root=bundle_dir_env,
                                    scenario=scenario_val,
                                    session_id=session_id,
                                    user_id=user_id,
                                    turn_number=turn_num,
                                    seed=None,
                                    stage="resolve_action",
                                    mode=mode,
                                    action=action_copy,
                                    actions=actions_copy,
                                    rng_state_json=rng_state_json,
                                    llm_tape=tape,
                                    strict_hits=list(hits),
                                    exc=None,
                                    error_summary=f"Swallowed strict-mode error(s): {len(hits)}",
                                    pre_turn_db_source=pre_db_path,
                                )
                            except Exception as write_err:
                                log.warning("Failed writing strict-mode crash bundle: %s", write_err)
                        return resp
                else:
                    try:
                        return await TurnService._resolve_action_inner(
                            session_id=session_id,
                            user_id=user_id,
                            action=action,
                            mode=mode,
                            stream_callback=stream_callback,
                            actions=actions,
                        )
                    except BaseException as exc:
                        if not (isinstance(exc, ValueError) and str(exc) == "waiting_for_party"):
                            try:
                                crash_capture.write_crash_bundle(
                                    bundle_root=bundle_dir_env,
                                    scenario=scenario_val,
                                    session_id=session_id,
                                    user_id=user_id,
                                    turn_number=turn_num,
                                    seed=None,
                                    stage="resolve_action",
                                    mode=mode,
                                    action=action_copy,
                                    actions=actions_copy,
                                    rng_state_json=rng_state_json,
                                    llm_tape=tape,
                                    strict_hits=[],
                                    exc=exc,
                                    pre_turn_db_source=pre_db_path,
                                )
                            except Exception as write_err:
                                log.warning("Failed writing crash bundle: %s", write_err)
                        raise
        finally:
            if os.path.exists(pre_db_path):
                try:
                    os.unlink(pre_db_path)
                except OSError:
                    pass

    @staticmethod
    async def _resolve_action_inner(
        session_id: int,
        user_id: int,
        action: Dict[str, Any],
        mode: str = "solo",
        stream_callback=None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> TurnResponse:
        """
        Unifies the turn resolution process across Discord and Web API using non-blocking DB access.
        """
        session = await adb(db.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        members = await adb(db.get_session_members, session_id)
        party = []
        for uid in members:
            c = await adb(db.get_character, uid)
            if c:
                inv = await adb(db.get_inventory, uid)
                party.append((dict(c), inv))

        import dataclasses
        from skill_check import CheckResult as _SkillCheckResult

        def _json_pick_default(obj: Any) -> Any:
            if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                return dataclasses.asdict(obj)
            return str(obj)

        def _rehydrate_check_obj(c_val: Any, fallback_req: int = 10) -> Any:
            if isinstance(c_val, dict):
                return _SkillCheckResult(
                    chance=int(c_val.get("chance") or 0),
                    roll=float(c_val.get("roll") or 0.0),
                    tier=str(c_val.get("tier") or "fail"),
                    tier_label=str(c_val.get("tier_label") or "Action"),
                    succeeded=bool(c_val.get("succeeded", False)),
                    requirement=int(c_val.get("requirement") if c_val.get("requirement") is not None else fallback_req),
                )
            return c_val

        def _rehydrate_action_dict(act_obj: Any) -> Any:
            if not isinstance(act_obj, dict):
                return act_obj
            if isinstance(act_obj.get("check"), dict):
                act_obj["check"] = _rehydrate_check_obj(act_obj["check"], int(act_obj.get("requirement") or 10))
            st_out = act_obj.get("stealth_outcome")
            if isinstance(st_out, dict) and isinstance(st_out.get("check"), dict):
                st_out["check"] = _rehydrate_check_obj(st_out["check"], int(act_obj.get("requirement") or 10))
            return act_obj

        sync_picks_rollback_json: Optional[str] = None
        if actions is not None:
            actions = [_rehydrate_action_dict(a) for a in list(actions)]
            if actions and not action:
                action = actions[0]
            mp_already_spent = {
                (a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)): a.get("mp_spent", 0)
                for a in actions
                if isinstance(a, dict) and a.get("_mp_already_deducted")
            }
            if mode == "sync":
                sync_picks_rollback_json = json.dumps(session.get("pending_picks") or {}, default=_json_pick_default)
                await adb(db.update_session, session_id, pending_picks_json="{}")
        elif mode == "sync" and len(party) > 1:
            picks = session.get("pending_picks", {})
            picks[str(user_id)] = action
            serialized_picks = json.dumps(picks, default=_json_pick_default)
            await adb(db.update_session, session_id, pending_picks_json=serialized_picks)

            if len(picks) < len(party):
                raise ValueError("waiting_for_party")

            # Everyone locked in
            sync_picks_rollback_json = serialized_picks
            actions = [_rehydrate_action_dict(a) for a in picks.values()]
            mp_already_spent = {
                (a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)): a.get("mp_spent", 0)
                for a in actions
                if a.get("_mp_already_deducted")
            }
            await adb(db.update_session, session_id, pending_picks_json="{}")
        else:
            actions = [_rehydrate_action_dict(action)]
            mp_already_spent = (
                {user_id: action.get("mp_spent", 0)}
                if action.get("_mp_already_deducted")
                else {}
            )

        # Serialize action helper
        def _serialize_action(a):
            c = a.get("check")
            check_dict = None
            if c:
                check_dict = {
                    "chance": getattr(c, "chance", a.get("rate")),
                    "roll": getattr(c, "roll", None),
                    "tier": getattr(c, "tier", a.get("tier", "fail")),
                    "tier_label": getattr(c, "tier_label", "Action"),
                    "succeeded": getattr(c, "succeeded", False)
                }
            return {
                "user_id": a.get("user_id", a.get("char", {}).get("user_id", 0)),
                "label": a.get("label", ""),
                "stat": a.get("stat", ""),
                "requirement": getattr(c, "requirement", a.get("requirement", 0)),
                "mp_spent": a.get("mp_spent", 0),
                "gold_spent": a.get("gold_spent", 0),
                "check": check_dict,
                "item_name": a.get("item_name"),
                "intent": a.get("intent"),
                "property_id": a.get("property_id") or "",
                "price": a.get("price") or 0,
                "sub_intent": a.get("sub_intent"),
                "ends_dialogue": a.get("ends_dialogue", False),
                "dismisses_npc": a.get("dismisses_npc", ""),
                "target_name": a.get("target_name") or a.get("target_npc") or a.get("combat_target"),
                "target_npc": a.get("target_npc") or a.get("target_name") or a.get("combat_target"),
                "combat_target": a.get("combat_target") or a.get("target_npc") or a.get("target_name"),
                "target_node_id": a.get("target_node_id") or "",
                "target_location": a.get("target_location") or "",
                "spell_id": a.get("spell_id"),
                "is_pact_skill": bool(a.get("is_pact_skill", False)),
                "is_lethal_overdraw": bool(a.get("is_lethal_overdraw", False)),
                "_pact_cast_meta": dict(a["_pact_cast_meta"]) if isinstance(a.get("_pact_cast_meta"), dict) else None,
                "incursion_action": a.get("incursion_action") or "",
                "quest_id": a.get("quest_id"),
                "sub_obj_id": a.get("sub_obj_id"),
                "stage_index": a.get("stage_index"),
                "is_quest_action": bool(a.get("is_quest_action", False)),
                "is_climax_action": bool(a.get("is_climax_action", False)),
                "is_story_quest": bool(a.get("is_story_quest", False)),
                "contract_type": a.get("contract_type") or "",
                "breakthrough_leveraged": bool(a.get("breakthrough_leveraged", False)),
                "clue_pair_ids": list(a.get("clue_pair_ids") or []),
                "active_recall": a.get("active_recall"),
                "is_stealth": a.get("is_stealth", False),
                "stance": a.get("stance", "normal"),
                "stealth_state": a.get("stealth_state"),
                "stealth_outcome": {
                    k: (v.__dict__ if hasattr(v, "__dict__") and not isinstance(v, dict) else v)
                    for k, v in a["stealth_outcome"].items()
                } if isinstance(a.get("stealth_outcome"), dict) else None,
            }

        import uuid
        turn_id = str(uuid.uuid4())
        import copy
        prev_st_rollback = None
        for a in actions:
            if isinstance(a, dict) and isinstance(a.get("_prev_stealth_state"), dict) and prev_st_rollback is None:
                prev_st_rollback = a.get("_prev_stealth_state")
            if isinstance(a, dict) and isinstance(a.get("stealth_state"), dict):
                session["stealth_state"] = copy.deepcopy(a["stealth_state"])
        # Compute 1-based monotonic gameplay turn number before snapshot & resolve_turn
        _hist_actions_cnt = sum(
            1 for _h in (session.get("history") or [])
            if not (isinstance(_h, dict) and _h.get("type") == "scene")
        )
        pre_turn_count_val = int(session.get("turn_count") or 0)
        target_turn = max(pre_turn_count_val, _hist_actions_cnt) + 1
        _property_gold_refunds: List[Tuple[int, int, Optional[int]]] = []
        for _pa in actions:
            if isinstance(_pa, dict) and str(_pa.get("intent") or "").strip().lower() == "property_purchase":
                _p_uid = int(_pa.get("user_id") or (_pa.get("char") or {}).get("user_id") or user_id)
                _p_id = str(_pa.get("property_id") or "").strip()
                if not _p_id and _pa.get("target_node_id"):
                    from mechanics.world.locations.realty_catalog import find_realty_by_node_id
                    _c_fb = find_realty_by_node_id(str(_pa["target_node_id"]), session_or_id=session or session_id)
                    if _c_fb:
                        _p_id = _c_fb["property_id"]
                if _p_id:
                    _buy_res = await adb(db.atomic_purchase_property, session_id, _p_uid, _p_id, turn_number=target_turn)
                    if _buy_res.get("ok"):
                        _paid = int(_buy_res.get("price_paid") or 0)
                        _p_cid = int(_buy_res.get("character_id") or (_pa.get("char") or {}).get("id") or 0) or None
                        _pa["gold_spent"] = 0
                        _pa["_gold_already_deducted"] = True
                        if _paid > 0:
                            _property_gold_refunds.append((_p_uid, _paid, _p_cid))
                        _updated_gold = _buy_res.get("new_gold")
                        if _updated_gold is None:
                            _updated_gold = _buy_res.get("gold")
                        for _idx_m, (_pc, _pinv) in enumerate(party):
                            if int(_pc.get("user_id") or 0) == _p_uid:
                                if _updated_gold is not None:
                                    _pc["gold"] = int(_updated_gold)
                                party[_idx_m] = (_pc, _pinv)
                    else:
                        _pa["target_node_id"] = ""
                        _pa["target_location"] = ""
                        _pa["label"] = f"Inspect the realty listing outside ({_buy_res.get('message') or _buy_res.get('reason') or 'purchase declined'})"
        pre_turn_daily_incursions_snapshot = copy.deepcopy(
            session.get("daily_incursions") if "daily_incursions" in session else session.get("daily_breaches")
        )
        # Snapshot every tracked key unconditionally (None when absent) so a hard failure on the FIRST turn
        # that creates one of these keys clears it on rollback instead of committing partial anomaly state.
        pre_turn_anomaly_extra_snapshot = {
            _ek: copy.deepcopy(session.get(_ek))
            for _ek in (
                "anomaly_field_log",
                "retired_folklore_ids",
                "folklore_cooldowns",
                "contained_anomalies_log",
                "anomalous_vault_log",
                "anomalous_vault_requisitions",
                "anomalous_faction_state",
                "last_school_hours_incident_day",
                "dialogue_partners",
                "folklore_villager_roster",
                "folklore_roster_pc_bucket",
                "folklore_free_tokens_granted",
                "leyline_spirit_passage_unlocked",
                "leyline_unlocked_turn",
                "leyline_unlock_reason",
            )
        }
        pre_turn_dialogue_partner = session.get("dialogue_partner")

        pre_turn_char_status_effects: Dict[int, list] = {}
        for _p_entry in (party or []):
            _p_char = _p_entry[0] if isinstance(_p_entry, (tuple, list)) and _p_entry else _p_entry
            if isinstance(_p_char, dict) and _p_char.get("user_id"):
                try:
                    pre_turn_char_status_effects[int(_p_char["user_id"])] = copy.deepcopy(
                        list(_p_char.get("status_effects") or [])
                    )
                except Exception:
                    pass

        snapshot = {
            "turn_id": turn_id,
            "status": "pending",
            "target_turn": target_turn,
            "fallback_reason": None,
            "retry_attempts": 0,
            "mode": mode,
            "actions": [_serialize_action(a) for a in actions],
            "pre_turn": {
                "pre_turn_count": pre_turn_count_val,
                "location": session.get("current_location", ""),
                "current_node_id": session.get("current_node_id", ""),
                "focal_point": session.get("focal_point", ""),
                "narrative": session.get("narrative", ""),
                "scene_title": session.get("scene_title", ""),
                "npcs": copy.deepcopy(list(session.get("current_npcs") or [])),
                "party_npcs": copy.deepcopy(list(session.get("party_npcs") or [])),
                "enemies": copy.deepcopy(list(session.get("nearby_enemies") or [])),
                "combat_threat_ledger": copy.deepcopy(session.get("combat_threat_ledger") or {}),
                "combat_boss_telegraph": copy.deepcopy(session.get("combat_boss_telegraph") or {}),
                "char_status_effects": {str(k): copy.deepcopy(v) for k, v in pre_turn_char_status_effects.items()},
                "daily_incursions": copy.deepcopy(pre_turn_daily_incursions_snapshot),
                "stealth_state": prev_st_rollback,
                "player_resonance_pips": (
                    copy.deepcopy(session["player_resonance_pips"])
                    if isinstance(session.get("player_resonance_pips"), dict)
                    else int(session.get("player_resonance_pips") or 0)
                ),
                "telemetry_calibrations_used": copy.deepcopy(session.get("telemetry_calibrations_used") or {}),
                "event_pity_counter": float(session.get("event_pity_counter") or 0.0),
                "rumor_pity_counter": float(session.get("rumor_pity_counter") or 0.0),
                "minor_event_pity_counter": float(session.get("minor_event_pity_counter") or 0.0),
            },
            "applied": {}
        }
        await adb(db.set_turn_snapshot, session_id, snapshot)

        if isinstance(session, dict):
            session["_target_turn"] = target_turn
            try:
                session["_world_events_snapshot"] = await adb(db.get_world_events_snapshot, session_id)
            except Exception:
                session["_world_events_snapshot"] = {}

        pre_turn_nearby_enemies_snapshot = copy.deepcopy(list(session.get("nearby_enemies") or []))
        pre_turn_had_threat_ledger = isinstance(session, dict) and "combat_threat_ledger" in session
        pre_turn_had_boss_telegraph = isinstance(session, dict) and "combat_boss_telegraph" in session

        async def _rollback_turn_failure(err: BaseException) -> None:
            if isinstance(session, dict):
                session.pop("_target_turn", None)
                session.pop("_pre_turn_quest_res", None)
                session["nearby_enemies"] = copy.deepcopy(pre_turn_nearby_enemies_snapshot)
                session["current_npcs"] = copy.deepcopy(snapshot["pre_turn"]["npcs"])
                if pre_turn_had_threat_ledger:
                    session["combat_threat_ledger"] = copy.deepcopy(snapshot["pre_turn"]["combat_threat_ledger"])
                else:
                    session.pop("combat_threat_ledger", None)
                if pre_turn_had_boss_telegraph:
                    session["combat_boss_telegraph"] = copy.deepcopy(snapshot["pre_turn"]["combat_boss_telegraph"])
                else:
                    session.pop("combat_boss_telegraph", None)
            try:
                await adb(db.rollback_session_normalized_state_after_turn, session_id, pre_turn_count_val)
            except Exception as _rb_norm_err:
                log.warning("Normalized state rollback failed for session %s: %s", session_id, _rb_norm_err)
            try:
                rollback_kwargs: Dict[str, Any] = {
                    "nearby_enemies": pre_turn_nearby_enemies_snapshot,
                    "current_npcs": snapshot["pre_turn"]["npcs"],
                    "dialogue_partner": pre_turn_dialogue_partner,
                    "combat_threat_ledger": copy.deepcopy(snapshot["pre_turn"]["combat_threat_ledger"]),
                    "combat_boss_telegraph": copy.deepcopy(snapshot["pre_turn"]["combat_boss_telegraph"]),
                }
                if "party_npcs" in snapshot["pre_turn"]:
                    rollback_kwargs["party_npcs"] = snapshot["pre_turn"]["party_npcs"]
                    try:
                        await adb(db.set_session_party_npcs, session_id, snapshot["pre_turn"]["party_npcs"])
                        if isinstance(session, dict):
                            session["party_npcs"] = copy.deepcopy(snapshot["pre_turn"]["party_npcs"])
                    except Exception as _rb_comp_err:
                        log.warning("party_npcs rollback failed for session %s: %s", session_id, _rb_comp_err)
                for _rb_uid, _rb_effs in pre_turn_char_status_effects.items():
                    try:
                        await adb(db.set_status_effects, int(_rb_uid), copy.deepcopy(_rb_effs))
                    except Exception as _rb_st_err:
                        log.warning("status_effects rollback failed for user %s: %s", _rb_uid, _rb_st_err)
                    for _p_entry in (party or []):
                        _p_char = _p_entry[0] if isinstance(_p_entry, (tuple, list)) and _p_entry else _p_entry
                        if isinstance(_p_char, dict) and _p_char.get("user_id") and int(_p_char["user_id"]) == int(_rb_uid):
                            _p_char["status_effects"] = copy.deepcopy(_rb_effs)
                if prev_st_rollback is not None:
                    rollback_kwargs["stealth_state"] = prev_st_rollback
                if sync_picks_rollback_json is not None:
                    rollback_kwargs["pending_picks_json"] = sync_picks_rollback_json
                extra_restore: Dict[str, Any] = dict(pre_turn_anomaly_extra_snapshot)
                extra_restore["player_resonance_pips"] = copy.deepcopy(snapshot["pre_turn"]["player_resonance_pips"])
                extra_restore["telemetry_calibrations_used"] = copy.deepcopy(snapshot["pre_turn"]["telemetry_calibrations_used"])
                if pre_turn_daily_incursions_snapshot is not None:
                    extra_restore["daily_incursions"] = pre_turn_daily_incursions_snapshot
                    extra_restore["daily_breaches"] = pre_turn_daily_incursions_snapshot
                if extra_restore:
                    rollback_kwargs["extra"] = extra_restore
                await adb(db.update_session, session_id, **rollback_kwargs)
            except Exception:
                pass
            if isinstance(err, Exception):
                log.error("Hard failure during turn execution for session %s: %s", session_id, err, exc_info=True)
            snapshot["status"] = "failed_hard"
            if _is_llm_unavailable_exception(err):
                snapshot["fallback_reason"] = "models_unavailable"
            else:
                snapshot["fallback_reason"] = "engine_error"
                snapshot["error"] = f"{type(err).__name__}: {err}"
            await adb(db.set_turn_snapshot, session_id, snapshot)

        # Resolve the turn with the LLM — resolve_turn now always returns a dict
        try:
            await adb(db.snapshot_session_physical_state_for_turn, session_id, pre_turn_count_val)
            await adb(db.snapshot_session_social_state_for_turn, session_id, pre_turn_count_val)
            await adb(db.save_contract_turn_snapshot, session_id, pre_turn_count_val)
        except Exception as _ps_pre_err:
            log.warning("Pre-turn physical/social snapshot failed (non-fatal): %s", _ps_pre_err)
        try:
            outcome = await game_engine.resolve_turn(session, party, actions, stream_callback=stream_callback)
            if isinstance(outcome, dict) and isinstance(session, dict) and "stealth_state" not in outcome:
                outcome["stealth_state"] = session.get("stealth_state")
        except BaseException as e:
            try:
                await asyncio.shield(_rollback_turn_failure(e))
            except asyncio.CancelledError:
                pass
            raise e

        if isinstance(outcome, dict):
            outcome["_target_turn"] = target_turn

        # Apply mechanics (includes quest & waypoint updates via _reduce_quests_and_waypoints)
        try:
            items_gained = await adb(game_engine.apply_outcome, session_id, party, outcome, mp_already_spent, actions=actions)
        except BaseException as e:
            try:
                await asyncio.shield(_rollback_turn_failure(e))
            except asyncio.CancelledError:
                pass
            raise e
        finally:
            if isinstance(outcome, dict):
                outcome.pop("_target_turn", None)
            if isinstance(session, dict):
                session.pop("_target_turn", None)
        if not isinstance(items_gained, dict):
            items_gained = {}
        try:
            await adb(db.snapshot_session_physical_state_for_turn, session_id, target_turn)
            await adb(db.snapshot_session_social_state_for_turn, session_id, target_turn)
            await adb(db.save_contract_turn_snapshot, session_id, target_turn, overwrite=True)
        except Exception as _ps_post_err:
            log.warning("Post-turn physical/social snapshot failed (non-fatal): %s", _ps_post_err)

        # Post-turn World Event & Rumor Resolution + Mid-Rumor Companion/Romance Loyalty Promotion
        if isinstance(outcome, dict):
            try:
                from mechanics.world.world_events import handle_mid_rumor_npc_promotion, on_quest_or_bounty_completed
                _completed_qids = set()
                for _qu in (outcome.get("quest_updates") or []):
                    if isinstance(_qu, dict) and str(_qu.get("status") or "").strip().lower() == "completed" and _qu.get("quest_id"):
                        _qid = str(_qu["quest_id"])
                        _completed_qids.add(_qid)
                        await adb(
                            on_quest_or_bounty_completed,
                            session_id,
                            _qid,
                            quest_type=str(_qu.get("quest_type") or "bounty"),
                            is_story_quest=bool(_qu.get("is_story_quest")),
                        )
                for _rn in (outcome.get("_quest_reward_notices") or []):
                    if isinstance(_rn, dict) and _rn.get("claimed") and _rn.get("quest_id"):
                        _qid = str(_rn["quest_id"])
                        if _qid not in _completed_qids:
                            _completed_qids.add(_qid)
                            await adb(
                                on_quest_or_bounty_completed,
                                session_id,
                                _qid,
                                quest_type=str(_rn.get("quest_type") or "bounty"),
                                is_story_quest=bool(_rn.get("is_story_quest")),
                            )

                _fk_scen_key = str((session or {}).get("scenario") or "fantasy")
                _is_fk_scen = bool(
                    scenario_data.is_anomalous_incursions_scenario(_fk_scen_key)
                    or scenario_data.is_anomalous_high_school_scenario(_fk_scen_key)
                    or "urban_anomalies" in _fk_scen_key.lower()
                )
                for _ru in (outcome.get("relationship_updates") or []):
                    if isinstance(_ru, dict) and _ru.get("name"):
                        _trk = str(_ru.get("track") or "").strip().lower()
                        _new_sc = int(_ru.get("new_score") if _ru.get("new_score") is not None else (_ru.get("score") or 0))
                        if _trk in ("romantic", "romance", "lover", "spouse") or _new_sc >= 70:
                            await adb(handle_mid_rumor_npc_promotion, session_id, npc_name=str(_ru["name"]))
                        if _is_fk_scen and (_trk in ("romantic", "romance", "lover", "spouse", "friend") or _new_sc >= 30):
                            from mechanics.social.folklore_roster import (
                                befriend_folklore_villager,
                                get_folklore_villager_spec,
                                shift_kitsune_form,
                            )
                            _fk_spec = await adb(
                                get_folklore_villager_spec,
                                session_id,
                                str(_ru["name"]),
                                session=session,
                                persist_db=False,
                            )
                            if _fk_spec:
                                await adb(
                                    befriend_folklore_villager,
                                    session_id,
                                    str(_ru["name"]),
                                    turn_number=target_turn,
                                )
                                if (
                                    _new_sc >= 45
                                    and str(_fk_spec.get("folklore_village") or "") == "kitsune"
                                    and str(_fk_spec.get("race") or "") == "kitsune:myobu_fox"
                                ):
                                    await adb(
                                        shift_kitsune_form,
                                        session_id,
                                        str(_ru["name"]),
                                        "kitsune:humanoid",
                                        turn_number=target_turn,
                                        shift_reason="bond_affinity",
                                    )
            except Exception as _we_post_err:
                log.warning("World event post-turn hooks failed (non-fatal): %s", _we_post_err)

            # Campaign Epilogue Choice, Zero-Plot-Armor NPC Fallout, Combat & Partner-Verified Intimate Hooks
            try:
                await adb(
                    game_engine.resolve_post_turn_dossier_hooks,
                    session_id,
                    session,
                    outcome,
                    actions,
                    user_id,
                )
            except Exception as _qd_post_err:
                log.warning("Quest dossier post-turn hooks failed (non-fatal): %s", _qd_post_err)
            try:
                await adb(db.snapshot_session_physical_state_for_turn, session_id, target_turn)
            except Exception as _ps_post_hook_err:
                log.warning("Post-hook physical snapshot refresh failed (non-fatal): %s", _ps_post_hook_err)

            # Surface Threat Clock ticks & directives if time/sleep advanced during the turn
            tc_tick = (
                (outcome.get("_sleep_info") or {}).get("threat_clock_tick")
                or (outcome.get("_time_info") or {}).get("threat_clock_tick")
                or outcome.get("threat_clock_tick")
            )
            if isinstance(tc_tick, dict) and tc_tick.get("ticked"):
                outcome["threat_clock_tick"] = tc_tick
                tc_dirs = [str(d) for d in (tc_tick.get("directives") or []) if d]
                if tc_dirs:
                    existing_qd = list(outcome.get("quest_directives") or [])
                    outcome["quest_directives"] = existing_qd + tc_dirs

            # Option C Mid-Chapter Stage 2 Prewarm Hook (fires when Stage 1 completes -> Ch.N+1 AI ChapterPlan in background)
            cur_ch = int(await adb(db.get_session_chapter, session_id) or 1)
            if cur_ch < 11:
                next_ch = cur_ch + 1
                if session.get("_last_prewarmed_chapter") != next_ch:
                    active_sq = await adb(db.get_active_story_quest, session_id)
                    if active_sq:
                        sq_dos = await adb(db.get_quest_dossier, session_id, str(active_sq.get("quest_id") or ""))
                        climax_sp = (sq_dos or {}).get("climax_spec") or {}
                        m_stages = climax_sp.get("main_stages") or []
                        stage2_active = any(
                            (int(ms.get("stage_index") or 0) >= 2 and ms.get("status") in ("active", "completed"))
                            for ms in m_stages
                        ) or any(
                            bool(int(so.get("completed_stages") or 0) >= 1 or int(so.get("stage_index") or 1) >= 2)
                            for so in (active_sq.get("sub_objectives") or [])
                            if isinstance(so, dict)
                        )
                        if stage2_active:
                            session["_last_prewarmed_chapter"] = next_ch
                            try:
                                await adb(db.update_session, session_id, extra={"_last_prewarmed_chapter": next_ch})
                            except Exception:
                                pass
                            from game_engine.quest_lifecycle import prewarm_chapter_ahead
                            pw_task = asyncio.create_task(
                                prewarm_chapter_ahead(
                                    session_id=session_id,
                                    current_chapter=cur_ch,
                                    target_chapter=next_ch,
                                )
                            )
                            _BACKGROUND_TASKS.add(pw_task)
                            pw_task.add_done_callback(_BACKGROUND_TASKS.discard)

        # Re-tag quest choices now that arrival/skill_check waypoint progression has unlocked next stages
        from mechanics.social.physical_state import is_erotic_intimate_contact as _ts_is_erotic
        _ts_phys = (outcome.get("_physical_state") if isinstance(outcome, dict) else None) or {}
        _ts_ic_str = str(_ts_phys.get("intimate_contact", "") if isinstance(_ts_phys, dict) else "")
        _ts_in_intimate = _ts_is_erotic(_ts_ic_str) or ("aftercare" in _ts_ic_str.lower())
        # Only re-tag quest choices if a waypoint stage unlocked during apply_outcome
        if (
            isinstance(outcome, dict)
            and outcome.get("_waypoint_notices")
            and not _ts_in_intimate
            and not (game_engine.get_active_enemies(session) or game_engine.get_active_enemies(outcome))
        ):
            try:
                from mechanics.world.waypoints import tag_and_enrich_quest_choices
                lead_char = party[0][0] if party and party[0] else None
                raw_c = list(outcome.get("next_choices") or outcome.get("choices") or [])

                eff_loc = outcome.get("location") or session.get("current_location", "")
                eff_dp = outcome.get("dialogue_partners") if "dialogue_partners" in outcome else outcome.get("dialogue_partner", ...)
                eff_npcs = outcome.get("npcs_present")
                enriched_c = await adb(
                    tag_and_enrich_quest_choices,
                    raw_c,
                    session_id,
                    eff_loc,
                    scen_key=session.get("scenario", "fantasy"),
                    char=lead_char,
                    dialogue_partner=eff_dp,
                    current_npcs=eff_npcs,
                )

                # Prune enriched choices that target already completed waypoint stages
                from game_engine import prune_completed_stage_choices
                enriched_c = prune_completed_stage_choices(enriched_c, outcome.get("_waypoint_notices") or [])
                if enriched_c:
                    free_actions = [c for c in raw_c if isinstance(c, dict) and c.get("stat") == "FREE"]
                    filler_budget = 3
                    filler_used = 0
                    final_c = []
                    for ec in enriched_c:
                        if not isinstance(ec, dict):
                            continue
                        is_ess = bool(
                            ec.get("is_quest_action")
                            or ec.get("is_climax_action")
                            or ec.get("_priority_slot")
                            or ec.get("_npc_speak_choice")
                            or str(ec.get("label") or "").lower().startswith(("speak with ", "talk to ", "talk with "))
                        )
                        if is_ess:
                            final_c.append(ec)
                        elif filler_used < filler_budget:
                            filler_used += 1
                            final_c.append(ec)
                    for fa in free_actions:
                        if not any(fc.get("label") == fa.get("label") for fc in final_c if isinstance(fc, dict)):
                            final_c.append(fa)
                    outcome["next_choices"] = final_c
                    outcome["choices"] = final_c
            except Exception as e:
                log.warning("tag_and_enrich_quest_choices post-update failed (non-fatal): %s", e)

        # Apply merchant encounter state deterministically (clears stale availability when omitted)
        if isinstance(outcome, dict):
            try:
                await adb(apply_merchant_encounter_result, session_id, outcome.get("merchant_encounter"))
            except Exception as e:
                log.warning("apply_merchant_encounter_result failed (non-fatal): %s", e)

        # Calculate XP across all acting party members
        xp_gained = 0
        levels_gained: List[int] = []
        xp_by_user: Dict[Any, int] = {}
        levels_by_user: Dict[Any, List[int]] = {}
        char = await adb(db.get_character, user_id)

        deduction_xp_bonus = int(outcome.get("_deduction_xp_bonus") or 0) if isinstance(outcome, dict) else 0
        for a in actions:
            uid = a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)
            char_for_xp = await adb(db.get_character, uid)
            if not char_for_xp:
                continue

            # Base XP from skill check tier
            check = a.get("check")
            if isinstance(check, dict):
                check_tier = check.get("tier", "fail")
            elif hasattr(check, "tier"):
                check_tier = check.tier
            else:
                check_tier = a.get("tier", "fail")
            base_xp = XP_REWARDS.get(check_tier, 0)

            # Bonus XP strictly from deterministic combat/DoT (_auth_combat_xp) + clue deduction
            bonus_xp = deduction_xp_bonus
            auth_xp_map = (outcome.get("_auth_combat_xp") if isinstance(outcome, dict) else None) or {}
            if isinstance(auth_xp_map, dict):
                bonus_xp += max(0, int(auth_xp_map.get(char_for_xp["name"].lower(), 0) or 0))

            total_xp = base_xp + bonus_xp
            lvls = await adb(db.add_xp, uid, total_xp)
            xp_by_user[uid] = total_xp
            levels_by_user[uid] = list(lvls or [])

            if uid == user_id:
                xp_gained = total_xp
                levels_gained = list(lvls or [])

        # Build history entry
        outcome_only_nar = str(outcome.get("outcome_narrative") or "").strip()
        next_only_nar = str(outcome.get("next_narrative") or outcome.get("narrative") or "").strip()
        outcome_nar = outcome_only_nar or next_only_nar
        next_scene_title = str(outcome.get("scene_title") or session.get("scene_title") or "").strip()
        check = action.get("check")
        tier_label = check.tier_label if hasattr(check, "tier_label") else action.get("tier", "action")
        label = action.get("label", "Action")

        char_name = char["name"] if char else "Hero"
        
        # Determine witnesses
        witnesses = [char_name]
        npcs_present = outcome.get("npcs_present") or []
        for npc in npcs_present:
            n_name = game_engine._get_npc_name(npc)
            if n_name and n_name.lower() != "none" and n_name not in witnesses:
                witnesses.append(n_name)
        
        history_entry = {
            "type": "action",
            "character_name": char_name,
            "label": label,
            "tier": check.tier if hasattr(check, "tier") else action.get("tier", "action"),
            "tier_label": tier_label,
            "stat": action.get("stat"),
            "roll": check.roll if hasattr(check, "roll") else action.get("roll"),
            "chance": check.chance if hasattr(check, "chance") else action.get("rate"),
            "requirement": action.get("requirement"),
            "success": check.succeeded if hasattr(check, "succeeded") else action.get("success", False),
            "narrative": outcome_nar,
            "outcome_narrative": outcome_only_nar,
            "next_narrative": next_only_nar,
            "scene_title": next_scene_title,
            "location": outcome.get("location") or session.get("current_location") or "",
            "items_gained": items_gained.get(user_id, []),
            "xp_gained": xp_gained,
            "levels_gained": levels_gained,
            "mp_spent": action.get("mp_spent", 0),
            "character_outcomes": outcome.get("character_outcomes") or [],
            "relationship_updates": outcome.get("relationship_updates") or [],
            "social_feedback_pills": list(outcome.get("social_feedback_pills") or []),
            "active_dialogue_mood": outcome.get("active_dialogue_mood"),
            "faction_updates": outcome.get("faction_updates") or [],
            "quest_updates": outcome.get("quest_updates") or [],
            "witnessed_by": witnesses,
            "is_fallback": bool(outcome.get("_is_fallback_narrative") or outcome.get("is_fallback")),
        }
        combat_log = outcome.get("combat_log") or outcome.get("_combat_log")
        if combat_log:
            history_entry["combat_log"] = combat_log
        if outcome.get("_enemy_attack_notice"):
            history_entry["enemy_attack_notice"] = outcome["_enemy_attack_notice"]
        if outcome.get("intimate_update"):
            history_entry["intimate_update"] = outcome["intimate_update"]
        if outcome.get("_refractory_recovered_notice"):
            history_entry["_refractory_recovered_notice"] = outcome["_refractory_recovered_notice"]
        if outcome.get("threat_clock_tick"):
            history_entry["threat_clock_tick"] = outcome["threat_clock_tick"]

        raw_hist = list(session.get("history") or [])
        if not raw_hist and session.get("narrative"):
            raw_hist.append({
                "type": "scene",
                "scene_title": session.get("scene_title") or "Beginning",
                "narrative": session.get("narrative") or "",
                "next_narrative": session.get("narrative") or "",
                "location": session.get("current_location") or "",
                "scene_image_url": session.get("scene_image_url"),
            })

        has_dialogue = bool(outcome.get("dialogue_partners") or outcome.get("dialogue_partner"))
        dyn_limit = 12 if has_dialogue else 4
        new_hist = game_engine.push_history(raw_hist, history_entry, limit=dyn_limit)
        await adb(
            db.update_session,
            session_id,
            history_json=json.dumps(new_hist, default=str),
            turn_count=target_turn,
        )
        from mechanics.world.world_events import build_client_world_pulse_payload as _build_wp_payload

        fresh_session = await adb(db.get_session, session_id)
        new_char = await adb(db.get_character, user_id)

        if isinstance(fresh_session, dict):
            fresh_session["world_pulse"] = await adb(_build_wp_payload, session_id)
        if user_id not in items_gained:
            items_gained[user_id] = []

        snapshot["status"] = "completed"
        snapshot["applied"] = {
            "character_outcomes": outcome.get("character_outcomes", []),
            "items_gained": items_gained,
            "xp_gained": dict(xp_by_user),
            "location": outcome.get("location", ""),
            "current_node_id": outcome.get("current_node_id") or fresh_session.get("current_node_id", ""),
            "focal_point": outcome.get("focal_point") or fresh_session.get("focal_point", ""),
            "npcs_present": (
                outcome.get("npcs_present")
                if outcome.get("npcs_present") is not None
                else list((fresh_session or {}).get("current_npcs") or [])
            ),
            "nearby_enemies": (
                outcome.get("nearby_enemies")
                if outcome.get("nearby_enemies") is not None
                else list((fresh_session or {}).get("nearby_enemies") or [])
            ),
            "deceased_characters": outcome.get("deceased_characters", []),
            "dead_enemies": outcome.get("dead_enemies", []),
            "time_info": outcome.get("_time_info", {}),
            "sleep_info": outcome.get("_sleep_info"),
            "quest_updates": outcome.get("quest_updates", []),
            "relationship_updates": outcome.get("relationship_updates", []),
            "social_feedback_pills": list(outcome.get("social_feedback_pills") or []),
            "active_dialogue_mood": outcome.get("active_dialogue_mood"),
            "dialogue_partner": (
                outcome.get("dialogue_partner")
                if "dialogue_partner" in outcome
                else (fresh_session or {}).get("dialogue_partner")
            ),
            "dialogue_partners": outcome.get("dialogue_partners", []),
            "cast_state": outcome.get("_staged_cast_state") or fresh_session.get("cast_state"),
            "intimate_update": outcome.get("intimate_update"),
            "_physical_state": outcome.get("_physical_state"),
            "_refractory_recovered_notice": outcome.get("_refractory_recovered_notice"),
            "event_pity_counter": float((fresh_session or {}).get("event_pity_counter") or 0.0),
            "rumor_pity_counter": float((fresh_session or {}).get("rumor_pity_counter") or 0.0),
            "minor_event_pity_counter": float((fresh_session or {}).get("minor_event_pity_counter") or 0.0),
        }

        await adb(db.set_turn_snapshot, session_id, snapshot)

        async def _run_finalize_memory_after_prose(final_hist: list, final_outcome: dict) -> None:
            try:
                from mechanics.system.memory.digest import is_arc_boundary_event
                _arc_boundary = is_arc_boundary_event(
                    session if isinstance(session, dict) else {},
                    actions,
                    final_outcome if isinstance(final_outcome, dict) else {},
                )
                _present_npc_names = [
                    n_nm for npc in ((final_outcome or {}).get("npcs_present") or outcome.get("npcs_present") or [])
                    for n_nm in [game_engine._get_npc_name(npc)]
                    if n_nm and n_nm.lower() != "none"
                ]
                _active_qids = [
                    str(qu.get("quest_id") or qu.get("title") or "").strip()
                    for qu in ((final_outcome or {}).get("quest_updates") or outcome.get("quest_updates") or [])
                    if isinstance(qu, dict) and (qu.get("quest_id") or qu.get("title"))
                ]
                await adb(
                    db.finalize_turn_memory,
                    session_id,
                    target_turn,
                    final_hist,
                    _present_npc_names,
                    str((final_outcome or {}).get("location") or outcome.get("location") or session.get("current_location") or ""),
                    _active_qids,
                    _arc_boundary,
                )
            except Exception as _mem_err:
                log.warning("Post-turn finalize_turn_memory failed for session %s: %s", session_id, _mem_err)

        lead_char_for_scene = dict(new_char) if new_char else (dict(party[0][0]) if party and party[0] else None)

        if outcome.get("_is_fallback_narrative"):
            log.info(f"Auto-recovery triggered for session {session_id} due to empty prose.")
            try:
                recovered_response = await TurnService.retry_narration(session_id, user_id, stream_callback=stream_callback)
                if mode in ("turn", "multi"):
                    await adb(db.advance_turn, session_id)
                recovered_hist = list((recovered_response.session or {}).get("history") or new_hist)
                await _run_finalize_memory_after_prose(recovered_hist, recovered_response.outcome)
                refreshed_sess = await adb(db.get_session, session_id)
                if isinstance(refreshed_sess, dict):
                    refreshed_sess["world_pulse"] = await adb(_build_wp_payload, session_id)
                    try:
                        from mechanics.world.locations import is_anomalous_realty_scenario, build_realty_payload
                        if is_anomalous_realty_scenario(str(refreshed_sess.get("scenario") or "")):
                            refreshed_sess["realty"] = await adb(build_realty_payload, session_id, user_id)
                    except Exception:
                        pass
                    recovered_response.session = refreshed_sess
                recovered_response.actions = actions
                recovered_response.items_gained_by_user = items_gained
                recovered_response.xp_gained = xp_gained
                recovered_response.levels_gained = levels_gained
                recovered_response.xp_by_user = xp_by_user
                recovered_response.levels_by_user = levels_by_user
                return recovered_response
            except Exception as e:
                log.warning("Auto-recovery narration pass failed: %s", e)
                snapshot["fallback_reason"] = "empty_prose"
                await adb(db.set_turn_snapshot, session_id, snapshot)
                outcome["fallback_reason"] = "empty_prose"

        scene_title, next_narrative, cleaned_choices = await TurnService._finalize_and_save_scene(
            session_id=session_id,
            session_obj=fresh_session,
            outcome=outcome,
            lead_char=lead_char_for_scene,
            history=new_hist,
            mode=mode,
            is_retry=False,
        )

        await _run_finalize_memory_after_prose(new_hist, outcome)
        refreshed_base_sess = await adb(db.get_session, session_id)
        if isinstance(refreshed_base_sess, dict):
            refreshed_base_sess["world_pulse"] = fresh_session.get("world_pulse") if isinstance(fresh_session, dict) else None
            try:
                from mechanics.world.locations import is_anomalous_realty_scenario, build_realty_payload
                if is_anomalous_realty_scenario(str(refreshed_base_sess.get("scenario") or "")):
                    refreshed_base_sess["realty"] = await adb(build_realty_payload, session_id, user_id)
            except Exception:
                pass
        else:
            refreshed_base_sess = fresh_session

        return TurnResponse(
            success=True,
            session=refreshed_base_sess,
            outcome=outcome,
            action=action,
            actions=actions,
            items_gained_by_user=items_gained,
            xp_gained=xp_gained,
            levels_gained=levels_gained,
            xp_by_user=xp_by_user,
            levels_by_user=levels_by_user,
            new_char=new_char,
            scene_persisted=True,
            scene_title=scene_title,
            next_narrative=next_narrative,
            cleaned_choices=cleaned_choices,
        )

    @staticmethod
    async def retry_narration(session_id: int, user_id: int, stream_callback=None) -> TurnResponse:
        """Runs the lightweight narration pass for a retry, updating only prose and choices while freezing cast & spatial state (D13)."""
        session = await adb(db.get_session, session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        try:
            await adb(game_engine.heal_session_quests_on_load, session_id)
        except Exception as _heal_err:
            log.debug("heal_session_quests_on_load failed (non-fatal): %s", _heal_err)
            
        snapshot = await adb(db.get_turn_snapshot, session_id)
        if not snapshot or snapshot.get("status") != "completed":
            raise ValueError("No completed snapshot available to retry")
            
        attempt = snapshot.get("retry_attempts", 0) + 1
        
        from game_engine.turn.narration import run_narration_pass
        
        # Narration pass (cast_events on retry output are strictly ignored per D13)
        new_outcome = await run_narration_pass(session, snapshot, attempt=attempt, stream_callback=stream_callback)
        if isinstance(new_outcome, dict):
            new_outcome.pop("cast_events", None)
        
        # 1. Update the DB history directly like resolve_action does
        raw_hist = list(session.get("history") or [])
        if raw_hist and isinstance(raw_hist[-1], dict) and raw_hist[-1].get("type") == "action":
            last_entry = dict(raw_hist[-1])
            new_outcome_narr = (new_outcome.get("outcome_narrative") or "").strip()
            new_next_narr = (new_outcome.get("next_narrative") or "").strip()

            # Check if previous outcome_narrative was an emergency fallback
            prev_outcome = str(last_entry.get("outcome_narrative") or "")
            is_prev_fallback = (
                bool(last_entry.get("is_fallback") or last_entry.get("_is_fallback_narrative"))
                or any(ph in prev_outcome.lower() for ph in (
                    "deliberate intent",
                    "carefully observe",
                    "temporary fallback",
                    "threads of fate shimmer",
                    "fallback generation",
                ))
            )

            if new_outcome_narr:
                last_entry["outcome_narrative"] = new_outcome_narr
                last_entry["narrative"] = new_outcome_narr
                last_entry.pop("is_fallback", None)
                last_entry.pop("_is_fallback_narrative", None)
            elif is_prev_fallback:
                last_entry["outcome_narrative"] = ""
                last_entry["narrative"] = new_next_narr or ""
                last_entry.pop("is_fallback", None)
                last_entry.pop("_is_fallback_narrative", None)

            if new_next_narr:
                last_entry["next_narrative"] = new_next_narr
            if new_outcome.get("scene_title"):
                last_entry["scene_title"] = new_outcome["scene_title"]
            raw_hist[-1] = last_entry
            await adb(db.update_session, session_id, history_json=json.dumps(raw_hist, default=str))
            try:
                await adb(db.resync_latest_digest_turn, session_id, raw_hist)
            except Exception as _resync_err:
                log.warning("resync_latest_digest_turn during retry_narration failed (non-fatal): %s", _resync_err)

        # Update snapshot attempts
        snapshot["retry_attempts"] = attempt
        snapshot["fallback_reason"] = None
        await adb(db.set_turn_snapshot, session_id, snapshot)
        
        fresh_session = await adb(db.get_session, session_id)
        new_char = await adb(db.get_character, user_id)
        
        if isinstance(fresh_session, dict):
            from mechanics.world.world_events.engine import build_client_world_pulse_payload as _build_wp_retry
            fresh_session["world_pulse"] = await adb(_build_wp_retry, session_id)
        # D13: Preserve frozen mechanical, spatial & cast state from snapshot["applied"]
        applied_state = dict(snapshot.get("applied", {}))
        merged_outcome = dict(applied_state)
        for k in ("outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"):
            if k in new_outcome:
                merged_outcome[k] = new_outcome[k]
        # Guarantee frozen cast & spatial fields cannot drift on retry
        for frozen_k in ("location", "current_node_id", "focal_point", "npcs_present", "dialogue_partner", "dialogue_partners"):
            if frozen_k in applied_state:
                merged_outcome[frozen_k] = applied_state[frozen_k]

        raw_retry_choices = merged_outcome.get("next_choices") or merged_outcome.get("choices") or []
        if raw_retry_choices and hasattr(game_engine, "build_hybrid_turn_choices"):
            try:
                retry_party = [(dict(new_char), [])] if isinstance(new_char, dict) and new_char else None
                rebuilt_choices = await adb(
                    game_engine.build_hybrid_turn_choices,
                    raw_retry_choices,
                    session=fresh_session,
                    party=retry_party,
                    result=merged_outcome,
                )
                if rebuilt_choices:
                    merged_outcome["next_choices"] = rebuilt_choices
                    merged_outcome["choices"] = rebuilt_choices
                    merged_outcome["_hybrid_choices_built"] = True
            except Exception as e:
                log.warning("build_hybrid_turn_choices during retry_narration failed (non-fatal): %s", e)

        retry_hist = list((fresh_session or {}).get("history") or raw_hist)
        scene_title, next_narrative, cleaned_choices = await TurnService._finalize_and_save_scene(
            session_id=session_id,
            session_obj=fresh_session,
            outcome=merged_outcome,
            lead_char=dict(new_char) if new_char else None,
            history=retry_hist,
            mode=snapshot.get("mode"),
            is_retry=True,
        )
        saved_retry_session = await adb(db.get_session, session_id)
        if isinstance(saved_retry_session, dict):
            saved_retry_session["world_pulse"] = fresh_session.get("world_pulse") if isinstance(fresh_session, dict) else None
        else:
            saved_retry_session = fresh_session

        action = snapshot.get("actions", [{}])[0]
        return TurnResponse(
            success=True,
            session=saved_retry_session,
            outcome=merged_outcome,
            action=action,
            items_gained_by_user={},
            xp_gained=0,
            levels_gained=[],
            new_char=new_char,
            scene_persisted=True,
            scene_title=scene_title,
            next_narrative=next_narrative,
            cleaned_choices=cleaned_choices,
        )
