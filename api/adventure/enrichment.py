from __future__ import annotations

import json
import re
import db
import game_engine
import scenario_data
import character_data as cd
from typing import Any
from db import adb
from scenario_data import get_scenario_display_name
from mechanics.combat.loadouts import ensure_combatant_loadout
from mechanics.narrative.campaign_spine import PLACEHOLDER_ACTOR_RE
from mechanics.narrative.dossier_compiler import resolve_quest_npc_fallback_gender
from mechanics.social.races import roll_scenario_npc_race
from mechanics.world import resolve_scene_merchant_ui_state
from ..deps import (
    enrich_choices_with_odds,
    enrich_session_party_members,
    logger,
    manager,
)
from .in_flight import (
    _LAST_TURN_ERRORS,
    _get_active_in_flight_turn,
)

_UNNAMED_ACTOR_TOKENS: frozenset[str] = frozenset(
    {
        "stranger", "crowd", "passerby", "bystander", "unknown", "someone", "figure",
        "somebody", "pedestrian", "onlooker", "shadow", "voice", "unnamed", "anonymous",
        "man", "woman", "boy", "girl", "person",
    }
)


def _is_unnamed_or_generic_actor(name: str, npc_dict: dict[str, Any]) -> bool:
    clean = str(name or "").strip()
    if not clean or PLACEHOLDER_ACTOR_RE.search(clean):
        return True
    if bool(
        npc_dict.get("is_monster")
        or npc_dict.get("is_enemy")
        or npc_dict.get("is_anomalous_entity")
        or npc_dict.get("npc_type") == "anomaly"
        or npc_dict.get("social_role_type") == "anomaly"
        or npc_dict.get("anomalous_npc_tag") == "anomaly_entity"
    ):
        return True
    low = clean.lower()
    if low.startswith(("a ", "an ", "the ", "unnamed ", "unknown ")):
        return True
    words = set(re.sub(r"[^a-z]+", " ", low).split())
    return bool(words & _UNNAMED_ACTOR_TOKENS)


def _sanitize_enemy_telegraph_view(e_view: dict) -> None:
    """Strips internal raw interrupt HP thresholds while keeping qualitative stagger_pct."""
    tel = e_view.get("telegraphed_skill")
    if isinstance(tel, dict) and tel:
        if "stagger_pct" not in e_view or e_view.get("stagger_pct") is None:
            thr = max(1, int(tel.get("interrupt_threshold", 1) or 1))
            acc = max(0, int(tel.get("accumulated_interrupt_damage", 0) or 0))
            e_view["stagger_pct"] = max(0, min(100, int(round((acc / float(thr)) * 100))))
        else:
            e_view["stagger_pct"] = max(0, min(100, int(e_view.get("stagger_pct", 0) or 0)))
        sanitized_tel = dict(tel)
        sanitized_tel.pop("interrupt_threshold", None)
        sanitized_tel.pop("accumulated_interrupt_damage", None)
        e_view["telegraphed_skill"] = sanitized_tel


def heal_session_before_projection(
    session: dict | None,
    session_id: int | None = None,
) -> list | None:
    """Explicitly runs idempotent session self-healing writes (agent roster & starter quarters) outside ReadUnitOfWork."""
    if not session or not isinstance(session, dict):
        return None
    sid_val = int(session_id if session_id is not None else (session.get("id") or 0))
    if sid_val <= 0:
        return None

    pre_agent_roster = None
    if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
        raw_r = session.get("anomalous_agent_roster")
        if not isinstance(raw_r, list) or not raw_r:
            try:
                from mechanics.social.agent_roster import ensure_anomalous_agent_roster
                pre_agent_roster = ensure_anomalous_agent_roster(sid_val, str(session.get("scenario") or ""))
                if isinstance(pre_agent_roster, list):
                    session["anomalous_agent_roster"] = pre_agent_roster
            except Exception:
                pre_agent_roster = []
    try:
        from mechanics.world.locations import is_anomalous_realty_scenario
        if is_anomalous_realty_scenario(str(session.get("scenario") or "")):
            if not any(p.get("is_starter") for p in db.get_player_properties(sid_val)):
                db.grant_or_relocate_starter_quarters(sid_val)
    except Exception:
        pass
    return pre_agent_roster


def _flush_projection_pending_writes(session_id: int, pending_writes: dict[str, Any]) -> None:
    if session_id <= 0 or not pending_writes:
        return
    try:
        with db.UnitOfWork():
            if "choices" in pending_writes:
                db.update_session(session_id, choices=pending_writes["choices"])
            if "merchant" in pending_writes:
                db.save_merchant_state(session_id, pending_writes["merchant"])
    except Exception:
        pass


def enrich_session_for_client(
    session: dict,
    user_id: int,
    ui_lang: str | None = None,
    *,
    read_only: bool = False,
    preloaded_settings: dict | None = None,
    preloaded_char: dict | None = None,
    preloaded_inv: list | None = None,
    pre_agent_roster: list | None = None,
    pre_healed: bool = False,
) -> dict:
    """Enriches session payload under a single ReadUnitOfWork (pure when read_only=True)."""
    if not session or not isinstance(session, dict):
        return session

    sid_val = int(session.get("id") or 0)
    eff_agent_roster = pre_agent_roster
    if not read_only and sid_val > 0 and not pre_healed:
        healed_roster = heal_session_before_projection(session, sid_val)
        if eff_agent_roster is None:
            eff_agent_roster = healed_roster

    pending_writes: dict[str, Any] | None = None if read_only else {}
    with db.ReadUnitOfWork():
        enriched = _enrich_session_for_client_body(
            session,
            user_id,
            ui_lang=ui_lang,
            read_only=read_only,
            pre_agent_roster=eff_agent_roster,
            pending_writes=pending_writes,
            preloaded_settings=preloaded_settings,
            preloaded_char=preloaded_char,
            preloaded_inv=preloaded_inv,
        )

    if not read_only and sid_val > 0 and pending_writes:
        _flush_projection_pending_writes(sid_val, pending_writes)
    return enriched


_enrich_session_for_client = enrich_session_for_client


def _enrich_session_for_client_body(
    session: dict,
    user_id: int,
    ui_lang: str | None = None,
    *,
    read_only: bool = False,
    pre_agent_roster: list | None = None,
    pending_writes: dict[str, Any] | None = None,
    preloaded_settings: dict | None = None,
    preloaded_char: dict | None = None,
    preloaded_inv: list | None = None,
) -> dict:
    """Enriches session payload with odds, party vitals, combat state, formatted time, fallback flags, and categorized combat decks."""
    if not session or not isinstance(session, dict):
        return session

    session = dict(session)
    session.pop("prompt_epoch", None)
    uid = user_id or session.get("host_user_id") or 0

    from mechanics.combat import is_in_combat
    from mechanics.world.locations import location_has_faction_hq
    in_combat = bool(is_in_combat(session))
    session["is_in_combat"] = in_combat

    raw_choices = session.get("choices") or []
    user_settings = (
        dict(preloaded_settings)
        if preloaded_settings is not None
        else (db.get_settings(uid) if uid else {})
    )
    char = (
        dict(preloaded_char)
        if preloaded_char is not None
        else (db.get_character(uid, session_id=session.get("id"), settings=user_settings) if uid else None)
    )
    if preloaded_settings is None and char and char.get("user_id") and int(char["user_id"]) != int(uid):
        user_settings = db.get_settings(char["user_id"])
    char_inv = (
        [dict(it) if isinstance(it, dict) else it for it in preloaded_inv]
        if preloaded_inv is not None
        else ((db.get_inventory(uid, char=char) or []) if (uid and char) else [])
    )
    if not raw_choices or any(not isinstance(c, dict) for c in raw_choices):
        raw_choices = game_engine.sanitize_and_diversify_choices(
            raw_choices,
            scenario=scenario_data.resolve_scenario_key(session.get("scenario")),
            location=session.get("current_location", ""),
            char={**char, "_preloaded_inventory": char_inv} if char else None,
            dialogue_partner=session.get("dialogue_partner"),
            current_npcs=session.get("current_npcs", []),
            session_id=session.get("id")
        )
    else:
        raw_choices = [dict(c) for c in raw_choices if isinstance(c, dict)]

    from mechanics.social.conversation_choices import (
        ensure_active_dialogue_exit_choice,
        has_dialogue_exit_choice,
    )
    had_exit = has_dialogue_exit_choice(raw_choices)
    if not had_exit:
        healed_choices = ensure_active_dialogue_exit_choice(raw_choices, session=session)
        if has_dialogue_exit_choice(healed_choices):
            if not read_only and session.get("id") and isinstance(pending_writes, dict):
                pending_writes["choices"] = healed_choices
            raw_choices = healed_choices

    session["choices"] = enrich_choices_with_odds(
        raw_choices,
        uid,
        session=session,
        char=char,
        user_settings=user_settings,
        inv=char_inv,
    )
    session["party_members"] = enrich_session_party_members(
        session,
        preloaded_chars={int(uid): char} if (uid and char) else None,
    )

    from mechanics.stealth import project_stealth_state_for_user, get_alert_badge_data
    st_client = project_stealth_state_for_user(session, uid)
    session["stealth_state"] = st_client
    session["stealth_badge"] = get_alert_badge_data(
        st_client.get("detection_meter", 0),
        is_hidden=st_client.get("is_hidden", False),
    )

    scen_key_check = scenario_data.resolve_scenario_key(session.get("scenario"))
    from scenario_data import is_nsfw_scenario, get_scenario_tags
    from mechanics.system.phone import scenario_has_smartphone
    session["is_nsfw"] = is_nsfw_scenario(scen_key_check)
    session["scenario_tags"] = get_scenario_tags(scen_key_check)
    session["scenario_display_name"] = get_scenario_display_name(scen_key_check)
    session["smartphone_available"] = bool(scenario_has_smartphone(scen_key_check))
    current_loc_check = str(session.get("current_location") or "")
    from mechanics.system.time_engine import get_location_sleep_context
    session["sleep_context"] = get_location_sleep_context(
        current_loc_check,
        props=session.get("physical_state", {}).get("props") if isinstance(session.get("physical_state"), dict) else None,
        scenario=scen_key_check,
        session_id=session.get("id"),
    )
    sid_int = int(session.get("id") or 0)
    merchant_state = session.get("merchant") or {}
    if isinstance(merchant_state, dict) and merchant_state.get("is_faction_quartermaster") and sid_int > 0:
        at_faction_hq = bool(
            location_has_faction_hq(current_loc_check, session_id=sid_int)
            or db.get_faction_by_hq(sid_int, current_loc_check)
        )
        if not at_faction_hq:
            cleaned_merch = dict(merchant_state)
            cleaned_merch["is_faction_quartermaster"] = False
            cleaned_merch["active"] = False
            session["merchant"] = cleaned_merch
            if not read_only and isinstance(pending_writes, dict):
                pending_writes["merchant"] = cleaned_merch

    merch_ui = resolve_scene_merchant_ui_state(
        session,
        session_id=sid_int,
        in_combat=in_combat,
    )
    staff_keeper_name = str(((merch_ui.get("staff_npc") or {}).get("name")) or "").strip()

    session["merchant_available"] = bool(merch_ui["available"])
    session["merchant_action_label"] = str(merch_ui["action_label"])
    session["shop_closed_visible"] = bool(merch_ui["shop_closed_visible"])
    session["shop_closed_reason"] = str(merch_ui["shop_closed_reason"])
    session["shop_closed_message"] = str(merch_ui["shop_closed_message"])
    session["staff_keeper"] = staff_keeper_name

    day = int(session.get("current_day", 1) or 1)
    minute = int(session.get("current_minute", 480) or 480)
    try:
        from mechanics.system.time_engine import get_day_of_week, get_time_of_day_phase
        from mechanics.world.world_schedule import is_weekend
        day_name = get_day_of_week(day)
        phase_name, _, _ = get_time_of_day_phase(minute)
        weekend_flag = bool(is_weekend(day))
    except Exception:
        _days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        _didx = max(0, day - 1) % 7
        day_name = _days[_didx]
        phase_name = "Day"
        weekend_flag = _didx in (5, 6)
    session["day_name"] = day_name
    session["is_weekend"] = weekend_flag
    session["time_of_day"] = phase_name
    session["formatted_time"] = f"{day_name} • {(minute // 60) % 24:02d}:{minute % 60:02d}"
    try:
        from mechanics.stealth import is_stealth_context_warranted
        session["stealth_available"] = bool(is_stealth_context_warranted(session))
    except Exception:
        session["stealth_available"] = True

    narr_lower = str(session.get("narrative") or "").lower()

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

    non_exit_choices = [
        c for c in (session.get("choices") or [])
        if isinstance(c, dict)
        and not c.get("_pinned_dialogue_exit")
        and c.get("intent") != "dialogue_exit"
    ]
    all_choices_fallback_on_empty_narr = bool(
        not narr_lower
        and not last_hist_narr
        and non_exit_choices
        and all(
            c.get("is_fallback") and not c.get("_deterministic_supplement")
            for c in non_exit_choices
        )
    )

    fallback_keywords = (
        "threads of fate shimmer",
        "temporary fallback",
        "fallback generation",
        "llm connection failed",
        "deliberate intent",
        "carefully observe the surroundings",
        "the atmosphere settles around",
    )
    has_fallback_narrative = any(
        phrase in narr_lower or phrase in last_hist_narr
        for phrase in fallback_keywords
    )
    session["is_fallback_generation"] = bool(
        session.get("is_fallback_generation")
        or last_hist_is_fallback
        or all_choices_fallback_on_empty_narr
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

    scen_key_hud = scenario_data.resolve_scenario_key(session.get("scenario"))
    is_anom_hud = scenario_data.is_anomalous_incursions_scenario(scen_key_hud)
    if is_anom_hud:
        from mechanics.combat.awakened_resonance import init_enemy_stability_profile, get_actor_resonance_pips
        session["ult_pips"] = get_actor_resonance_pips(session, uid)
        session["max_ult_pips"] = 3
        if uid and session.get("id"):
            try:
                from mechanics.pacts import get_pact_slot_capacity, get_available_patrons_for_context
                _act_pacts = db.get_player_active_pacts(int(session["id"]), int(uid))
                _avail_p = get_available_patrons_for_context(session, char or {}, int(uid), persist_db=False)
                session["contracts_hud"] = {
                    "enabled": True,
                    "slot_used": len(_act_pacts),
                    "slot_capacity": get_pact_slot_capacity(char or {}),
                    "has_breach": any(int(r.get("breach_stage") or 0) > 0 or int(r.get("unpaid_blood_debt") or 0) > 0 for r in _act_pacts),
                    "available_count": len(_avail_p.get("patrons") or []),
                }
            except Exception:
                pass
        session["player_3axis"] = (
            {
                "attribute": char.get("attribute") or None,
                "combat_archetype": char.get("combat_archetype") or None,
                "ability_medium": char.get("ability_medium") or None,
            }
            if char
            else ({"attribute": None, "combat_archetype": None, "ability_medium": None} if uid else None)
        )

        # Sanitize enemy HUD view without mutating DB hidden_weakness
        sanitized_enemies = []
        for raw_e in (session.get("nearby_enemies") or []):
            if not isinstance(raw_e, dict):
                sanitized_enemies.append(raw_e)
                continue
            e_view = dict(raw_e)
            if int(e_view.get("hp", 1) or 0) > 0 and e_view.get("max_stability") is None:
                init_enemy_stability_profile(e_view)
            base_weak_src = (
                e_view.get("revealed_weaknesses")
                if isinstance(e_view.get("revealed_weaknesses"), list)
                else (e_view.get("weaknesses") or [])
            )
            disp_weak = [str(w) for w in base_weak_src if w]
            hid_w = e_view.get("hidden_weakness")
            if hid_w and str(hid_w) != "?":
                is_hid_rev = bool(
                    e_view.get("hidden_weakness_revealed")
                    or (
                        isinstance(e_view.get("revealed_weaknesses"), list)
                        and str(hid_w) in [str(x) for x in e_view.get("revealed_weaknesses")]
                    )
                )
                if is_hid_rev:
                    if str(hid_w) not in disp_weak:
                        disp_weak.append(str(hid_w))
                else:
                    disp_weak = [w for w in disp_weak if w != str(hid_w)]
                    disp_weak.append("?")
                    e_view["weaknesses"] = [str(w) for w in (e_view.get("weaknesses") or []) if str(w) != str(hid_w)]
                    e_view["hidden_weakness"] = "?"
            e_view["display_weaknesses"] = disp_weak
            e_view["is_breached"] = bool(e_view.get("is_breached"))
            e_view["breached_turns_left"] = int(e_view.get("breached_turns_left", 0) or 0)
            from mechanics.world.folklore_mechanics import get_enemy_tether_state
            ts = get_enemy_tether_state(e_view)
            if ts:
                is_sealed = bool(ts.get("sealed") or e_view.get("tether_sealed"))
                e_view["tether_sealed"] = is_sealed
                bp_rev = bool((e_view.get("anomaly_blueprint") or {}).get("dossier_revealed"))
                if (
                    e_view.get("dossier_revealed")
                    or bp_rev
                    or e_view.get("tether_reformed_once")
                    or ts.get("reformed_once")
                    or is_sealed
                ):
                    e_view["tether_vessel_name"] = str(ts.get("vessel_name") or "")
            _sanitize_enemy_telegraph_view(e_view)
            sanitized_enemies.append(e_view)
        session["nearby_enemies"] = sanitized_enemies

        # Active Construct status pill
        construct_info = None
        for cand_npc in list(session.get("current_npcs") or []) + list(session.get("party_npcs") or []) + list(session.get("_active_constructs") or []):
            if isinstance(cand_npc, dict) and cand_npc.get("is_summon") and int(cand_npc.get("hp", 0) or 0) > 0:
                q_act = cand_npc.get("queued_windup") or cand_npc.get("queued_construct_action")
                construct_info = {
                    "name": str(cand_npc.get("name") or "Construct"),
                    "hp": int(cand_npc.get("hp", 0) or 0),
                    "max_hp": max(1, int(cand_npc.get("max_hp", 1) or 1)),
                    "windup_skill": (q_act.get("skill_name") or q_act.get("name")) if isinstance(q_act, dict) else None,
                }
                break
        session["construct_status"] = construct_info
    elif isinstance(session.get("nearby_enemies"), list):
        sanitized_enemies = []
        for raw_e in session["nearby_enemies"]:
            if not isinstance(raw_e, dict):
                sanitized_enemies.append(raw_e)
                continue
            e_view = dict(raw_e)
            _sanitize_enemy_telegraph_view(e_view)
            sanitized_enemies.append(e_view)
        session["nearby_enemies"] = sanitized_enemies

    if isinstance(session.get("combat_boss_telegraph"), dict):
        scrubbed_bt: dict = {}
        for bt_k, bt_v in session["combat_boss_telegraph"].items():
            if isinstance(bt_v, dict):
                bt_copy = dict(bt_v)
                if "stagger_pct" not in bt_copy or bt_copy.get("stagger_pct") is None:
                    thr = max(1, int(bt_copy.get("interrupt_threshold", 1) or 1))
                    acc = max(0, int(bt_copy.get("accumulated_interrupt_damage", 0) or 0))
                    bt_copy["stagger_pct"] = max(0, min(100, int(round((acc / float(thr)) * 100))))
                else:
                    bt_copy["stagger_pct"] = max(0, min(100, int(bt_copy.get("stagger_pct", 0) or 0)))
                bt_copy.pop("interrupt_threshold", None)
                bt_copy.pop("accumulated_interrupt_damage", None)
                scrubbed_bt[bt_k] = bt_copy
            else:
                scrubbed_bt[bt_k] = bt_v
        session["combat_boss_telegraph"] = scrubbed_bt

    if in_combat and uid:
        from mechanics.narrative.choice_generator import generate_categorized_combat_actions
        from mechanics.combat.spells import get_spell
        from mechanics.combat.spells.awakened_kits import get_actor_spell

        inv = char_inv if char else []
        party = [(dict(char), inv)] if char else []
        learned_sids = db.get_learned_spells(uid, char=char) if char else []
        skill_prog_hud = db.get_skill_progress(char) if char else {}
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
            from mechanics.stealth import is_actor_combat_vanished
            if party and party[0] and is_actor_combat_vanished(session, uid):
                party[0][0]["combat_vanished"] = True
            raw_deck = generate_categorized_combat_actions(
                party=party,
                monster=enemy,
                location=location,
                scenario=scen_key,
                session=session,
            ) or {}

            magic_list = list(raw_deck.get("magic") or [])
            existing_sids = {m.get("spell_id") for m in magic_list if isinstance(m, dict) and m.get("spell_id")}
            ult_pips_now = int(session.get("ult_pips", 0) or 0)
            for sid in (learned_sids or []):
                if sid not in existing_sids:
                    sp = get_actor_spell(sid, skill_prog_hud) or get_spell(sid)
                    if sp:
                        is_ult_sp = bool(sp.get("is_ultimate") or sp.get("slot_tier") == "ultimate")
                        mp_cost = 0 if (is_ult_sp and is_anom_hud) else int(sp.get("mp_cost", 6) or 0)
                        pip_cost = 3 if (is_ult_sp and is_anom_hud) else 0
                        can_aff = (ult_pips_now >= pip_cost) if (is_ult_sp and is_anom_hud) else (int((char or {}).get("mp", 0) or 0) >= mp_cost)
                        cost_txt = f"{ult_pips_now}/3 Pips • 0 MP" if (is_ult_sp and is_anom_hud) else f"{mp_cost} MP"
                        magic_list.append({
                            "label": f"{sp.get('emoji', '🔮')} {sp.get('name', sid)} ({cost_txt})",
                            "stat": "INT",
                            "requirement": 5,
                            "mp_cost": mp_cost,
                            "pip_cost": pip_cost,
                            "is_ultimate": is_ult_sp,
                            "can_afford": can_aff,
                            "choice_type": "combat",
                            "action_category": "magic",
                            "spell_id": sid,
                            "combat_target": enemy_name,
                        })
                        existing_sids.add(sid)

            attacks = enrich_choices_with_odds(
                raw_deck.get("attacks") or [],
                uid,
                session=session,
                char=char,
                user_settings=user_settings,
                inv=char_inv,
            )
            magic = enrich_choices_with_odds(
                magic_list,
                uid,
                session=session,
                char=char,
                user_settings=user_settings,
                inv=char_inv,
            )
            tactics = enrich_choices_with_odds(
                raw_deck.get("tactics") or [],
                uid,
                session=session,
                char=char,
                user_settings=user_settings,
                inv=char_inv,
            )
            for lst in (attacks, magic, tactics):
                for item in lst:
                    if isinstance(item, dict) and not item.get("combat_target"):
                        item["combat_target"] = enemy_name

            raw_flee = raw_deck.get("flee")
            if isinstance(raw_flee, dict):
                flee_enriched = enrich_choices_with_odds(
                    [raw_flee],
                    uid,
                    session=session,
                    char=char,
                    user_settings=user_settings,
                    inv=char_inv,
                )[0]
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
            e_id = enemy.get("id") or enemy.get("enemy_id")
            if e_id is not None:
                decks_by_target[str(e_id)] = deck_entry
            if first_deck is None:
                first_deck = deck_entry

        session["combat_decks_by_target"] = decks_by_target
        session["combat_deck"] = first_deck
        session["combat_actions"] = first_deck
    else:
        session["combat_decks_by_target"] = {}
        session["combat_deck"] = None
        session["combat_actions"] = None

    # Dynamic Clothing Status & Present NPC Enrichment
    try:
        from mechanics.social.physical_state import compute_clothing_summary_badge, match_actor_key, find_player_actor_key
        phys_st = db.get_session_physical_state(session.get("id")) if session.get("id") else None
        phys_actors = (phys_st.get("actors") or {}) if isinstance(phys_st, dict) else {}

        # 1. Player character clothing status
        sess_char = session.get("character") if isinstance(session.get("character"), dict) else {}
        char_dict = dict(char) if char else sess_char
        char_name = char_dict.get("name") if isinstance(char_dict, dict) else ""
        matched_p_key = find_player_actor_key(phys_actors, party=[(char_dict, [])], session_id=session.get("id")) or (match_actor_key(char_name, phys_actors) if char_name else "")
        if matched_p_key not in phys_actors and sess_char.get("name"):
            alt_key = find_player_actor_key(phys_actors, party=[(sess_char, [])], session_id=session.get("id")) or match_actor_key(str(sess_char["name"]), phys_actors)
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
                    m_pm_key = match_actor_key(str(pm["name"]), phys_actors)
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
        world_roster_by_name: dict[str, dict] = {}
        if sess_id and (raw_npcs or session.get("party_npcs")):
            try:
                wr_rows = db.get_world_roster(sess_id, include_legacy_rosters=False) or []
                world_roster_by_name = {
                    str(w.get("name") or "").strip().lower(): w
                    for w in wr_rows
                    if isinstance(w, dict) and w.get("name")
                }
            except Exception:
                world_roster_by_name = {}
        lore_data = db.get_lorebook(sess_id) or {} if sess_id else {}
        lore_characters = {}
        if isinstance(lore_data, dict):
            for l_cat in ("characters", "npcs", "people"):
                for l_ent in (lore_data.get(l_cat) or []):
                    if isinstance(l_ent, dict):
                        l_name = str(l_ent.get("title") or l_ent.get("name") or "").strip().lower()
                        if l_name:
                            lore_characters[l_name] = l_ent

        is_anom_sess = scenario_data.is_anomalous_incursions_scenario(session.get("scenario", ""))
        agent_roster_names = None
        agent_roster_by_name: dict[str, dict] = {}
        if is_anom_sess:
            raw_roster = session.get("anomalous_agent_roster")
            if not isinstance(raw_roster, list) or not raw_roster:
                if pre_agent_roster is not None:
                    raw_roster = pre_agent_roster
                elif not read_only and sess_id:
                    try:
                        from mechanics.social.agent_roster import ensure_anomalous_agent_roster
                        raw_roster = ensure_anomalous_agent_roster(sess_id, str(session.get("scenario") or ""))
                    except Exception:
                        raw_roster = []
                else:
                    raw_roster = []
            agent_roster_names = {
                str(r.get("name") or "").strip().lower()
                for r in raw_roster
                if isinstance(r, dict) and r.get("name")
            }
            agent_roster_by_name = {
                str(r.get("name") or "").strip().lower(): r
                for r in raw_roster
                if isinstance(r, dict) and r.get("name")
            }

        from mechanics.social.roster_tags import derive_age_group as _derive_age_group

        legacy_roster_by_name: dict[str, dict] | None = None
        quest_cast_by_name: dict[str, dict[str, Any]] | None = None

        def _clean_demo_str(val: Any) -> str:
            s = str(val or "").strip()
            if not s or s.lower() in ("unknown", "none", "null", "n/a"):
                return ""
            return s

        def _age_group_from_numeric_age(val: Any) -> str:
            try:
                if val is None or isinstance(val, bool):
                    return ""
                num_str = str(val).strip()
                if not num_str:
                    return ""
                age_val = int(float(num_str))
            except (TypeError, ValueError):
                return ""
            if age_val <= 0:
                return ""
            if age_val < 13:
                return "child"
            if age_val <= 19:
                return "teen"
            if age_val <= 25:
                return "young_adult"
            if age_val <= 59:
                return "adult"
            return "elder"

        def _pick_demo_field(
            sources: list[dict | None],
            keys: tuple[str, ...],
            *,
            check_appearance: bool = False,
        ) -> str:
            for src in sources:
                if not isinstance(src, dict):
                    continue
                for k in keys:
                    v = _clean_demo_str(src.get(k))
                    if v:
                        return v
                bi = src.get("basic_info")
                if isinstance(bi, dict):
                    for k in keys:
                        v = _clean_demo_str(bi.get(k))
                        if v:
                            return v
                if check_appearance:
                    app = src.get("appearance")
                    if isinstance(app, dict):
                        for k in keys:
                            v = _clean_demo_str(app.get(k))
                            if v:
                                return v
            return ""

        def _enrich_npc_entry(npc_item):
            nonlocal legacy_roster_by_name, quest_cast_by_name
            if isinstance(npc_item, str):
                n_dict = {"name": npc_item.strip()}
            elif isinstance(npc_item, dict):
                n_dict = dict(npc_item)
            else:
                return None

            n_name = str(n_dict.get("name") or "").strip()
            if not n_name:
                return None

            matched_n_key = match_actor_key(n_name, phys_actors)
            n_act_data = phys_actors.get(matched_n_key) or {}
            matched_contact = contacts_by_name.get(n_name.lower())
            if not matched_contact and contacts_by_name:
                m_c_key = match_actor_key(n_name, contacts_by_name)
                matched_contact = contacts_by_name.get(m_c_key)
            matched_lore = lore_characters.get(n_name.lower()) if lore_characters else None
            if not matched_lore and lore_characters:
                m_l_key = match_actor_key(n_name, lore_characters)
                matched_lore = lore_characters.get(m_l_key)
            matched_wr = world_roster_by_name.get(n_name.lower()) if world_roster_by_name else None
            if isinstance(matched_wr, dict):
                for _wk in ("origin", "tier_status", "role", "gender", "race"):
                    if not n_dict.get(_wk) and matched_wr.get(_wk):
                        n_dict[_wk] = matched_wr.get(_wk)
                for _wbk in ("is_unique_proprietor", "met_in_person"):
                    if _wbk not in n_dict and _wbk in matched_wr:
                        n_dict[_wbk] = matched_wr.get(_wbk)
                if isinstance(matched_wr.get("basic_info"), dict):
                    _cur_bi = n_dict.get("basic_info") if isinstance(n_dict.get("basic_info"), dict) else {}
                    n_dict["basic_info"] = {**matched_wr["basic_info"], **_cur_bi}
            matched_agent = agent_roster_by_name.get(n_name.lower()) if agent_roster_by_name else None
            if not matched_agent and agent_roster_by_name:
                m_a_key = match_actor_key(n_name, agent_roster_by_name)
                matched_agent = agent_roster_by_name.get(m_a_key)
            c_rec = matched_contact or matched_lore
            demo_sources: list[dict | None] = [n_dict, c_rec, matched_wr, matched_agent]
            resolved_gender = _pick_demo_field(demo_sources, ("gender",), check_appearance=True)
            resolved_race = _pick_demo_field(demo_sources, ("race",), check_appearance=True)
            resolved_age_group = _pick_demo_field(demo_sources, ("age_group",), check_appearance=False)
            if sess_id and (not resolved_gender or not resolved_race or not resolved_age_group):
                if legacy_roster_by_name is None:
                    try:
                        legacy_rows = db.get_world_roster(sess_id, include_legacy_rosters=True) or []
                        legacy_roster_by_name = {
                            str(w.get("name") or "").strip().lower(): w
                            for w in legacy_rows
                            if isinstance(w, dict) and w.get("name")
                        }
                    except Exception:
                        legacy_roster_by_name = {}
                matched_legacy = None
                if legacy_roster_by_name:
                    matched_legacy = legacy_roster_by_name.get(n_name.lower())
                    if not matched_legacy:
                        m_leg_key = match_actor_key(n_name, legacy_roster_by_name)
                        matched_legacy = legacy_roster_by_name.get(m_leg_key)
                if isinstance(matched_legacy, dict):
                    demo_sources.append(matched_legacy)
                    if not resolved_gender:
                        resolved_gender = _pick_demo_field([matched_legacy], ("gender",), check_appearance=True)
                    if not resolved_race:
                        resolved_race = _pick_demo_field([matched_legacy], ("race",), check_appearance=True)
                    if not resolved_age_group:
                        resolved_age_group = _pick_demo_field([matched_legacy], ("age_group",), check_appearance=False)

            if (not resolved_gender or not resolved_race) and not _is_unnamed_or_generic_actor(n_name, n_dict):
                matched_qcast = None
                if sess_id:
                    if quest_cast_by_name is None:
                        quest_cast_by_name = {}
                        try:
                            for dos_q in (db.get_session_quest_dossiers(sess_id, status_stage="compiled") or []):
                                if not isinstance(dos_q, dict):
                                    continue
                                cb_q = dos_q.get("cast_bindings") or {}
                                if not isinstance(cb_q, dict):
                                    continue
                                for slot_q, bind_q in cb_q.items():
                                    if not isinstance(bind_q, dict):
                                        continue
                                    bq_name = str(bind_q.get("name") or "").strip()
                                    if bq_name and bq_name.lower() not in quest_cast_by_name:
                                        quest_cast_by_name[bq_name.lower()] = {
                                            **bind_q,
                                            "slot": str(slot_q or "").strip(),
                                        }
                        except Exception:
                            quest_cast_by_name = {}
                    matched_qcast = quest_cast_by_name.get(n_name.lower())
                if isinstance(matched_qcast, dict):
                    if not resolved_gender:
                        resolved_gender = _clean_demo_str(matched_qcast.get("gender")).lower()
                    if not resolved_race:
                        resolved_race = _clean_demo_str(matched_qcast.get("race"))
                    if not resolved_age_group:
                        resolved_age_group = _clean_demo_str(matched_qcast.get("age_group"))
                    if not n_dict.get("role"):
                        slot_q = str(matched_qcast.get("slot") or "").strip().lower()
                        fallback_q_role = {
                            "client": "Quest Patron",
                            "informant": "Informant",
                            "target": "Quest Target",
                            "accomplice": "Suspect Associate",
                        }.get(slot_q, "Quest Contact")
                        n_dict["role"] = str(matched_qcast.get("role") or fallback_q_role)
                alpha_words = [tok for tok in n_name.split() if any(ch.isalpha() for ch in tok)]
                if matched_qcast is not None or len(alpha_words) >= 2:
                    if not resolved_gender:
                        resolved_gender = resolve_quest_npc_fallback_gender(n_name, session_id=int(sess_id or 0))
                    if not resolved_race:
                        resolved_race = roll_scenario_npc_race(
                            str(session.get("scenario") or "fantasy"),
                            seed=f"quest_wp:{int(sess_id or 0)}:{n_name.lower()}",
                        )

            clothing_gender = resolved_gender or "Female"
            n_dict["clothing_status"] = compute_clothing_summary_badge(n_act_data.get("clothing"), gender=clothing_gender)

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
                comp_val = str(n_act_data.get("composure") or "").strip().lower()
                if comp_val and comp_val != "composed":
                    raw_effs.append(comp_val.capitalize())
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
                score = n_dict.get(
                    "relationship_score",
                    n_dict.get(
                        "affinity",
                        n_dict.get("affinity_score", (matched_wr or {}).get("affinity_score", 0)),
                    ),
                )

            n_dict["relationship_score"] = int(score or 0)
            n_dict["affinity"] = int(score or 0)
            n_dict["track"] = (c_rec.get("track") if isinstance(c_rec, dict) else None) or n_dict.get("track", "platonic")

            # 3. Synchronize intimate excitement meter (when applicable)
            exc_actors = (phys_st.get("excitement") or {}).get("actors") or {}
            matched_exc_key = match_actor_key(n_name, exc_actors) if exc_actors else ""
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
                    if isinstance(pm, dict) and match_actor_key(n_name, {pm.get("name", ""): pm}):
                        partner_meter_data = pm
                        break
                if not partner_meter_data and last_intimate.get("partner_meter") is not None:
                    p_name = last_intimate.get("partner_name") or session.get("dialogue_partner") or ""
                    if match_actor_key(n_name, {p_name: True}):
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

            if is_anom_sess:
                try:
                    from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
                    anom_source = dict(c_rec) if isinstance(c_rec, dict) else {}
                    anom_source.update(n_dict)
                    t_tag = classify_anomalous_npc_tag(
                        anom_source,
                        session_id=sess_id,
                        scen_key=str(session.get("scenario") or ""),
                        contact_record=matched_contact,
                        lore_record=matched_lore,
                        agent_roster_names=agent_roster_names,
                    )
                    n_dict["anomalous_npc_tag"] = t_tag
                    n_dict["anomalous_tag_label"] = "Special Agent" if t_tag == "special_agent" else "Civilian"
                    n_dict["is_special_agent"] = (t_tag == "special_agent")
                    if isinstance(c_rec, dict) and (c_rec.get("basic_info") or {}).get("deceased"):
                        n_dict["deceased"] = True
                except Exception:
                    pass

            if resolved_gender:
                n_dict["gender"] = resolved_gender
            if resolved_race:
                n_dict["race"] = resolved_race

            is_anom_entity = bool(
                n_dict.get("is_anomalous_entity")
                or n_dict.get("npc_type") == "anomaly"
                or n_dict.get("social_role_type") == "anomaly"
                or n_dict.get("anomalous_npc_tag") == "anomaly_entity"
            )
            if not is_anom_entity:
                final_age_group = ""
                if resolved_age_group:
                    final_age_group = resolved_age_group.lower().replace("-", "_").replace(" ", "_")
                else:
                    raw_age = _pick_demo_field(demo_sources, ("age",), check_appearance=True)
                    if raw_age:
                        final_age_group = _age_group_from_numeric_age(raw_age)
                if not final_age_group:
                    eff_origin = _pick_demo_field([n_dict, matched_wr], ("origin",)).lower()
                    eff_shift = _pick_demo_field(demo_sources, ("shift_profile",)).lower()
                    eff_grade = _pick_demo_field(demo_sources, ("grade", "standing"))
                    eff_grade_low = eff_grade.lower()
                    is_student_grade = any(
                        sg in eff_grade_low
                        for sg in ("freshman", "sophomore", "junior", "senior", "student", "youth peer")
                    ) and not eff_grade_low.startswith("tier ")
                    if (
                        eff_origin in ("venue_seed", "replacement_hire", "district_merchant", "civic_staff", "roaming_merchant")
                        and eff_shift != "student"
                        and not is_student_grade
                    ):
                        final_age_group = "adult"
                    else:
                        eff_role = _pick_demo_field(demo_sources, ("role",))
                        eff_occ = _pick_demo_field(demo_sources, ("occupation",))
                        role_probe = (
                            f"{eff_role} {eff_occ}".strip()
                            if (eff_role and eff_occ and eff_occ.lower() not in eff_role.lower())
                            else (eff_role or eff_occ)
                        )
                        eff_srt = _pick_demo_field(demo_sources, ("social_role_type",))
                        is_fam = False
                        for _fsrc in demo_sources:
                            if not isinstance(_fsrc, dict):
                                continue
                            _fbi = _fsrc.get("basic_info") if isinstance(_fsrc.get("basic_info"), dict) else {}
                            if (
                                _fsrc.get("is_adult_family")
                                or _fbi.get("is_adult_family")
                                or _fsrc.get("household_role") in ("father", "mother", "guardian")
                            ):
                                is_fam = True
                                break
                        final_age_group = _derive_age_group(
                            grade=eff_grade,
                            role=role_probe,
                            social_role_type=eff_srt,
                            scen_key=str(session.get("scenario") or ""),
                            is_family=is_fam,
                        )
                if final_age_group:
                    n_dict["age_group"] = final_age_group

            # F1 Server-Side Fog-of-War: never serialize internal/unrevealed telltale tags or hidden secrets
            n_dict.pop("telltale_tag", None)
            n_dict.pop("cover_tag", None)
            if not bool(n_dict.get("telltale_revealed")):
                n_dict.pop("visible_tell_text", None)
            if not bool(n_dict.get("hidden_secret_revealed")):
                for _hk in ("hidden_secret", "hidden_secret_telltale", "hidden_awakened", "secret_faction"):
                    n_dict.pop(_hk, None)
                if isinstance(n_dict.get("basic_info"), dict):
                    _bi_clean = dict(n_dict["basic_info"])
                    if not bool(_bi_clean.get("hidden_secret_revealed")):
                        for _hk in ("hidden_secret", "hidden_secret_telltale", "hidden_awakened", "secret_faction"):
                            _bi_clean.pop(_hk, None)
                    n_dict["basic_info"] = _bi_clean

            # Omnichannel Spotlight vs Bystander UI classification
            _adv_origin = str(n_dict.get("origin") or (c_rec.get("origin") if isinstance(c_rec, dict) else "") or "").strip().lower()
            _adv_tier = str(n_dict.get("tier_status") or "").strip().lower()
            _adv_dps = {
                str(x).strip().lower()
                for x in ([session.get("dialogue_partner")] + list(session.get("dialogue_partners") or []))
                if x
            }
            _is_background_roster = (
                _adv_tier == "seeded"
                or _adv_origin in ("roaming_citizen", "district_merchant", "civic_staff", "campus_seed", "roaming_merchant")
            )
            n_dict["is_spotlight"] = bool(
                matched_contact
                or n_name.lower() in _adv_dps
                or n_dict.get("presence_tier") in (1, 2, 3)
                or n_dict.get("met_in_person")
                or int(n_dict.get("affinity") or 0) != 0
                or n_dict.get("is_unique_proprietor")
                or n_dict.get("is_hostile")
                or n_dict.get("is_anomalous_entity")
                or not _is_background_roster
            )

            return n_dict

        enriched_npcs = []
        for npc in raw_npcs:
            enr = _enrich_npc_entry(npc)
            if enr:
                enriched_npcs.append(enr)
        session["current_npcs"] = enriched_npcs

        if isinstance(session.get("party_npcs"), list):
            enriched_party_npcs = []
            _party_scen = str(session.get("scenario") or "fantasy")
            for p_npc in session["party_npcs"]:
                enr_p = _enrich_npc_entry(p_npc)
                if enr_p:
                    ensure_combatant_loadout(enr_p, scenario_key=_party_scen)
                    enriched_party_npcs.append(enr_p)
            session["party_npcs"] = enriched_party_npcs
    except Exception as e:
        logger.debug(f"Could not enrich clothing status for session: {e}")

    # Active Dialogue Mood Enrichment (qualitative only; paused during combat or erotic scenes)
    session["active_dialogue_mood"] = None
    try:
        from mechanics.social.physical_state import is_session_in_erotic_dialogue as _adv_is_erotic
        _adv_erotic = _adv_is_erotic(session)
        if not in_combat and not _adv_erotic and session.get("id"):
            from mechanics.social import locales as _soc_locales
            from mechanics.social import pacing as _soc_pacing
            _ui_lg = str(ui_lang or (user_settings or {}).get("ui_language") or session.get("language") or "en")
            _raw_dps = session.get("dialogue_partners")
            if isinstance(_raw_dps, list) and _raw_dps:
                _dp_names = [str(p).strip() for p in _raw_dps if str(p).strip() and str(p).strip().lower() != "none"]
            else:
                _single_dp = str(session.get("dialogue_partner") or "").strip()
                _dp_names = [_single_dp] if _single_dp and _single_dp.lower() != "none" else []
            if _dp_names:
                _mood_by_low: dict[str, dict] = {}
                for _dp_nm in _dp_names:
                    _comp = _soc_pacing.sync_and_get_composure(
                        int(session["id"]),
                        _dp_nm,
                        current_day=day,
                        current_minute=minute,
                        persist_db=(not read_only),
                    )
                    _m_key, _ = _soc_pacing.derive_mood_and_dc_mod(
                        int(_comp.get("current_composure", 100)),
                        int(_comp.get("max_composure", 100)),
                        str(_comp.get("composure_state") or "composed"),
                        clear_the_air_required=bool(int(_comp.get("clear_the_air_required") or 0) == 1),
                    )
                    _m_obj = {
                        "npc_name": _dp_nm,
                        "mood_key": _m_key,
                        "mood_label": _soc_locales.get_mood_label(_m_key, lang=_ui_lg),
                    }
                    _mood_by_low[_dp_nm.lower()] = _m_obj
                    if session["active_dialogue_mood"] is None:
                        session["active_dialogue_mood"] = _m_obj
                for _list_k in ("current_npcs", "party_npcs"):
                    if isinstance(session.get(_list_k), list):
                        for _npc_item in session[_list_k]:
                            if isinstance(_npc_item, dict):
                                _nm_l = str(_npc_item.get("name") or "").strip().lower()
                                if _nm_l in _mood_by_low:
                                    _npc_item["dialogue_mood"] = _mood_by_low[_nm_l]
    except Exception as _e_mood:
        logger.debug(f"Could not enrich active_dialogue_mood for session: {_e_mood}")

    if session.get("id"):
        try:
            from mechanics.world.world_events.engine import build_client_world_pulse_payload
            session["world_pulse"] = build_client_world_pulse_payload(int(session["id"]))
        except Exception as e_wp:
            logger.debug(f"Could not enrich world_pulse for session: {e_wp}")
        try:
            from mechanics.world.locations import is_anomalous_realty_scenario, build_realty_payload
            if is_anomalous_realty_scenario(str(session.get("scenario") or "")):
                session["realty"] = build_realty_payload(int(session["id"]), user_id, persist_db=False)
        except Exception as e_rl:
            logger.debug(f"Could not enrich realty for session: {e_rl}")

        # B7 Epistemic Fog-of-War HUD (strictly excludes player_aware == 0 secrets/hops)
        try:
            session["epistemic_hud"] = db.build_player_fog_of_war_summary(int(session["id"]))
        except Exception as e_ep:
            logger.debug(f"Could not enrich epistemic_hud for session: {e_ep}")

    active_turn = _get_active_in_flight_turn(sid_int)
    if active_turn:
        session["in_flight_turn"] = {
            "turn_id": active_turn.get("turn_id"),
            "user_id": active_turn.get("user_id"),
            "status": active_turn.get("status", "resolving"),
            "action": active_turn.get("action"),
            "started_at": active_turn.get("started_at"),
        }
        session["last_turn_error"] = None
    else:
        session["in_flight_turn"] = None
        session["last_turn_error"] = _LAST_TURN_ERRORS.get(sid_int) if sid_int else None

    cs_raw = session.get("crowd_state")
    if isinstance(cs_raw, dict):
        session["crowd_state"] = {
            "density": str(cs_raw.get("density") or "empty"),
            "flavor": str(cs_raw.get("flavor") or ""),
            "overflow_count": int(cs_raw.get("overflow_count") or 0),
        }

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
