from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

import scenario_data
from mechanics.narrative.quest_engines import (
    load_quest_engines_catalog,
    normalize_quest_locale,
)

log = logging.getLogger(__name__)

THREAT_CLOCK_MAX_SEGMENTS = 6
THREAT_CLOCK_MINUTES_PER_TICK = 240  # 1 tick per 4 in-game hours


def is_threat_clock_eligible(
    session: Optional[dict[str, Any]],
    quest: Optional[dict[str, Any]],
    dossier: Optional[dict[str, Any]],
) -> bool:
    """Story quests in Chapters 1-10 (non-Endless, non-Ch.11+) use a 6-segment Threat Clock."""
    if not isinstance(dossier, dict):
        return False
    family = str(dossier.get("family_tier") or "").strip().lower()
    is_story = bool(
        family == "story"
        or (isinstance(quest, dict) and quest.get("is_story_quest"))
    )
    if not is_story:
        return False
    if isinstance(session, dict) and session.get("endless_mode_unlocked"):
        return False
    ch = int(
        (session or {}).get("current_chapter")
        or (session or {}).get("chapter")
        or (session or {}).get("chapter_number")
        or ((dossier.get("climax_spec") or {}).get("chapter"))
        or 1
    )
    return 1 <= ch < 11


def build_initial_threat_clock(
    *,
    chapter: int = 1,
    endless_mode_unlocked: bool = False,
) -> Dict[str, Any]:
    """Returns a fresh unengaged 0/6 Threat Clock structure for `climax_spec['threat_clock']`."""
    enabled = (1 <= int(chapter or 1) < 11) and not bool(endless_mode_unlocked)
    return {
        "enabled": enabled,
        "filled": 0,
        "max_segments": THREAT_CLOCK_MAX_SEGMENTS,
        "last_tick_minute_abs": None,
        "pending_minutes": 0,
        "crossed_thresholds": [],
        "reinforced": False,
        "world_scar_pending": False,
        "last_consequence_note": "",
        "last_consequence_event": None,
    }


def _abs_minutes(day: int, minute: int) -> int:
    return (max(1, int(day or 1)) - 1) * 1440 + max(0, int(minute or 0))


def _ensure_clock_dict(climax: Dict[str, Any], eligible: bool) -> Dict[str, Any]:
    raw = climax.get("threat_clock")
    clk = dict(raw) if isinstance(raw, dict) else build_initial_threat_clock(chapter=int(climax.get("chapter") or 1))
    clk["enabled"] = bool(eligible)
    clk["max_segments"] = int(clk.get("max_segments") or THREAT_CLOCK_MAX_SEGMENTS)
    clk["filled"] = max(0, min(clk["max_segments"], int(clk.get("filled") or 0)))
    clk["pending_minutes"] = max(0, int(clk.get("pending_minutes") or 0))
    clk["crossed_thresholds"] = [int(x) for x in (clk.get("crossed_thresholds") or []) if isinstance(x, (int, float, str)) and str(x).isdigit()]
    clk["reinforced"] = bool(clk.get("reinforced", False))
    clk["world_scar_pending"] = bool(clk.get("world_scar_pending", False))
    clk["last_consequence_event"] = raw.get("last_consequence_event") if isinstance(raw, dict) else None
    return clk


def get_threat_threshold_text(segment: int, lang: str = "en") -> Dict[str, str]:
    """Returns localized `{title, teaser, directive}` for thresholds 2, 4, 6 from `quest_engines_catalog.json`."""
    eff_lang = normalize_quest_locale(lang)
    catalog = load_quest_engines_catalog()
    thresholds = catalog.get("threat_thresholds") or {}
    entry = thresholds.get(str(segment)) or {}
    loc_entry = entry.get(eff_lang) or entry.get("en") or {}
    if isinstance(loc_entry, dict) and loc_entry:
        return {
            "title": str(loc_entry.get("title") or f"Threshold {segment}/6"),
            "teaser": str(loc_entry.get("teaser") or ""),
            "directive": str(loc_entry.get("directive") or ""),
        }
    return {"title": f"Threshold {segment}/6", "teaser": "", "directive": ""}


def format_threat_consequence(
    event: Optional[Dict[str, Any]],
    lang: str = "en",
) -> str:
    """Renders a structured threat consequence event into localized display text."""
    if not isinstance(event, dict):
        return ""
    ev_type = str(event.get("type") or "").strip()
    if not ev_type:
        return ""
    param = str(event.get("param") or "").strip()
    eff_lang = normalize_quest_locale(lang)
    catalog = load_quest_engines_catalog()
    consequences = (catalog.get("threat_thresholds") or {}).get("consequences") or {}
    loc_dict = consequences.get(eff_lang) or consequences.get("en") or {}
    template = str(loc_dict.get(ev_type) or "")
    if template:
        if "{param}" in template:
            if param:
                return template.replace("{param}", param)
            return (
                template.replace(" ({param})", "")
                .replace("（{param}）", "")
                .replace(": {param}", "")
                .replace("：{param}", "")
                .replace("{param}", "")
                .strip()
            )
        return template
    fallbacks = {
        "lead_cold": f"Lead gone cold ({param})" if param else "Lead gone cold",
        "threatened_lost": f"Threatened objective lost: {param}" if param else "Threatened objective lost",
        "alert_up": f"Opposition Alert +1 ({param})" if param else "Opposition Alert +1",
        "reinforced": "Climax reinforced with enemy vanguard",
    }
    return fallbacks.get(ev_type, "")


def get_threat_clock_view(
    dossier: Optional[Dict[str, Any]],
    session: Optional[Dict[str, Any]] = None,
    quest: Optional[Dict[str, Any]] = None,
    lang: str = "en",
) -> Optional[Dict[str, Any]]:
    """Builds a UI-safe read projection of the active chapter Threat Clock."""
    if not isinstance(dossier, dict):
        return None
    if not is_threat_clock_eligible(session, quest, dossier):
        return None
    climax = dossier.get("climax_spec") or {}
    clk = _ensure_clock_dict(climax, True)
    filled = int(clk["filled"])
    max_seg = int(clk["max_segments"])
    qid_str = str((quest or {}).get("quest_id") or dossier.get("quest_id") or "")
    next_th = 2 if filled < 2 else (4 if filled < 4 else (6 if filled < 6 else 6))
    next_info = get_threat_threshold_text(next_th, lang=lang)
    return {
        "enabled": True,
        "engaged": bool(dossier.get("engaged_flag")),
        "paused": _is_in_climax_combat(session, qid_str, climax),
        "filled": filled,
        "max_segments": max_seg,
        "next_threshold": next_th,
        "next_threshold_label": next_info.get("title", ""),
        "next_threshold_teaser": next_info.get("teaser", ""),
        "reinforced": bool(clk.get("reinforced")),
        "world_scar_pending": bool(clk.get("world_scar_pending")),
        "last_consequence_note": str(clk.get("last_consequence_note") or ""),
        "last_consequence_event": clk.get("last_consequence_event"),
    }


def _is_in_climax_combat(session: Optional[dict[str, Any]], quest_id: str, climax: dict[str, Any]) -> bool:
    """Q7: Clock pauses during climax boss combat."""
    if not isinstance(session, dict):
        return False
    active_enc = session.get("_active_quest_encounter") or {}
    if isinstance(active_enc, dict) and active_enc.get("quest_id") == quest_id and active_enc.get("is_climax_boss"):
        if session.get("nearby_enemies"):
            return True
    enemies = session.get("nearby_enemies") or []
    if isinstance(enemies, list):
        for en in enemies:
            if isinstance(en, dict) and en.get("linked_quest_id") == quest_id:
                ms = climax.get("main_stages") or []
                climax_stage = next((s for s in ms if isinstance(s, dict) and s.get("is_climax_stage")), None)
                if climax_stage and str(climax_stage.get("status") or "").lower() == "active":
                    return True
    return False


def mark_chapter_clock_engaged(
    session_id: int,
    quest_id: str,
    current_day: Optional[int] = None,
    current_minute: Optional[int] = None,
    eff_turn: Optional[int] = None,
    conn: Any = None,
) -> bool:
    """E1: Sets `engaged_flag = 1` and initializes `last_tick_minute_abs` to now without backlog ticks."""
    import db

    if not session_id or not quest_id:
        return False
    if conn is None:
        with db.UnitOfWork() as uow_conn:
            return mark_chapter_clock_engaged(
                session_id,
                quest_id,
                current_day=current_day,
                current_minute=current_minute,
                eff_turn=eff_turn,
                conn=uow_conn,
            )
    sess = db.get_session(session_id) or {}
    dossier = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not dossier:
        return False
    q = db.get_minimal_story_quest(session_id, quest_id, conn=conn)
    if current_day is None or current_minute is None:
        current_day, current_minute, _ = db.get_session_time(session_id)
    abs_now = _abs_minutes(current_day, current_minute)
    eligible = is_threat_clock_eligible(sess, q, dossier)
    climax = copy.deepcopy(dossier.get("climax_spec") or {})
    clk = _ensure_clock_dict(climax, eligible)
    changed = False
    turn_num = int(eff_turn if eff_turn is not None else db.get_effective_session_turn(session_id, sess=sess, conn=conn))

    if int(dossier.get("engaged_flag") or 0) == 0:
        db.append_dossier_state_event(session_id, quest_id, turn_num, "engaged_flag", 0, 1, conn=conn)
        changed = True
    if clk.get("last_tick_minute_abs") is None:
        prev_c = copy.deepcopy(climax)
        clk["last_tick_minute_abs"] = abs_now
        clk["pending_minutes"] = 0
        climax["threat_clock"] = clk
        db.append_dossier_state_event(session_id, quest_id, turn_num, "climax_spec", prev_c, climax, conn=conn)
        changed = True
    else:
        climax["threat_clock"] = clk

    if changed:
        db.upsert_quest_dossier(
            session_id,
            quest_id,
            engaged_flag=1,
            climax_spec=climax,
            conn=conn,
        )
    return changed


def _apply_threshold_consequences(
    session_id: int,
    dossier: Dict[str, Any],
    quest: Optional[Dict[str, Any]],
    sess: Dict[str, Any],
    climax: Dict[str, Any],
    clk: Dict[str, Any],
    eff_turn: int,
    conn: Any = None,
    prev_climax: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Applies Q9/E5 threshold escalation when filled crosses 2, 4, or 6."""
    import db

    qid = str(dossier.get("quest_id") or "")
    lang = normalize_quest_locale(sess.get("language") or "en")
    filled = int(clk.get("filled") or 0)
    crossed = list(clk.get("crossed_thresholds") or [])
    directives: List[str] = []
    notes: List[str] = []
    events: List[Dict[str, Any]] = []

    leads = [dict(l) for l in (dossier.get("leads_graph") or []) if isinstance(l, dict)]
    leads_changed = False
    new_alert = int(dossier.get("alert_level") or 0)
    alert_changed = False
    sync_needed = False

    if filled >= 2 and 2 not in crossed:
        crossed.append(2)
        th2 = get_threat_threshold_text(2, lang=lang)
        if th2.get("directive"):
            directives.append(th2["directive"])
        notes.append(th2.get("title") or "2/6 Closing Window")

    if filled >= 4 and 4 not in crossed:
        crossed.append(4)
        th4 = get_threat_threshold_text(4, lang=lang)
        # E5 Anti-Lockout: never chill the last open clue source!
        stages = [dict(s) for s in (climax.get("main_stages") or []) if isinstance(s, dict)]
        chilled = False
        for s_idx, st in enumerate(stages):
            if str(st.get("status") or "").lower() != "active" or st.get("is_climax_stage"):
                continue
            sources = [dict(src) for src in (st.get("clue_sources") or []) if isinstance(src, dict)]
            open_indices = [i for i, src in enumerate(sources) if str(src.get("status") or "open").lower() == "open"]
            if len(open_indices) >= 2:
                # Prefer burning a secondary open source so the primary or remaining source stays open
                victim_i = open_indices[-1]
                sources[victim_i]["status"] = "cold"
                st["clue_sources"] = sources
                stages[s_idx] = st
                climax["main_stages"] = stages
                chilled = True
                sync_needed = True
                src_loc = sources[victim_i].get("location") or ""
                from mechanics.world.locations.hierarchy import get_clean_leaf_location
                clean_leaf = get_clean_leaf_location(src_loc, default="source")
                events.append({"type": "lead_cold", "param": clean_leaf, "threshold": 4})
                notes.append(f"Lead gone cold ({clean_leaf})")
            break

        if not chilled:
            # Fallback 1: lose one active threatened Optional
            for li, ld in enumerate(leads):
                if (
                    ld.get("is_optional")
                    and str(ld.get("role") or "").lower() == "threatened"
                    and str(ld.get("status") or "active").lower() == "active"
                ):
                    ld["status"] = "failed"
                    ld["failed"] = True
                    leads[li] = ld
                    leads_changed = True
                    sync_needed = True
                    opt_title = str(ld.get("label") or ld.get("title") or "Optional")
                    events.append({"type": "threatened_lost", "param": opt_title, "threshold": 4})
                    notes.append(f"Threatened objective lost: {opt_title}")
                    chilled = True
                    break

        if not chilled:
            # Fallback 2: +1 alert_level
            max_alert = int(dossier.get("max_alert") or 3)
            if new_alert < max_alert:
                new_alert += 1
                alert_changed = True
                events.append({"type": "alert_up", "param": f"{new_alert}/{max_alert}", "threshold": 4})
                notes.append(f"Opposition Alert +1 ({new_alert}/{max_alert})")

        if th4.get("directive"):
            directives.append(th4["directive"])

    if filled >= 6 and 6 not in crossed:
        crossed.append(6)
        th6 = get_threat_threshold_text(6, lang=lang)
        clk["world_scar_pending"] = True
        climax["escalated"] = True
        scen_key = str(sess.get("scenario") or "fantasy")
        is_combat_capable = (
            not scenario_data.is_non_combat_scenario(scen_key)
            and str(dossier.get("engine") or "").upper() != "INTIMATE_LIAISON"
        )
        if is_combat_capable:
            clk["reinforced"] = True
            reinf_name = ""
            reinf = [dict(r) for r in (climax.get("reinforcements") or []) if isinstance(r, dict)]
            if not any(r.get("from_threat_clock") for r in reinf):
                climax_loc = str(climax.get("target_location") or climax.get("location") or "")
                chapter_num = int(
                    sess.get("current_chapter")
                    or sess.get("chapter")
                    or sess.get("chapter_number")
                    or climax.get("chapter")
                    or 1
                )
                try:
                    from mechanics.combat.enemies import generate_scenario_enemy
                    reinf_foe = generate_scenario_enemy(
                        scenario=scen_key,
                        location=climax_loc,
                        chapter=chapter_num,
                        language=lang,
                        exact_tier=2,
                    )
                except Exception as exc:
                    log.warning("generate_scenario_enemy failed in threat_clock: %s", exc)
                    reinf_foe = {
                        "name": "Clockwork Vanguard Detail" if "fantasy" not in scen_key else "Reinforced Sentinel Guard",
                        "hp": 40,
                        "max_hp": 40,
                    }
                reinf_foe["from_threat_clock"] = True
                reinf_foe["tier_label"] = "Threat Clock Reinforcement"
                reinf_name = str(reinf_foe.get("name") or "")
                reinf.append(reinf_foe)
                climax["reinforcements"] = reinf
            events.append({"type": "reinforced", "param": reinf_name, "threshold": 6})
            notes.append(th6.get("title") or "6/6 Climax Reinforced")
            if th6.get("directive"):
                directives.append(th6["directive"])
        else:
            events.append({"type": "alert_up", "param": "Climax Escalation", "threshold": 6})
            notes.append("6/6 Maximum Escalation")

    clk["crossed_thresholds"] = sorted(set(crossed))
    if events:
        clk["last_consequence_event"] = events[-1]
        formatted_note = format_threat_consequence(events[-1], lang=lang)
        if formatted_note:
            clk["last_consequence_note"] = formatted_note[:160]
    elif notes:
        clk["last_consequence_note"] = "; ".join(notes)[:160]
    climax["threat_clock"] = clk

    if prev_climax is not None:
        db.append_dossier_state_event(session_id, qid, eff_turn, "climax_spec", prev_climax, climax, conn=conn)
    if leads_changed:
        db.append_dossier_state_event(session_id, qid, eff_turn, "leads_graph", list(dossier.get("leads_graph") or []), leads, conn=conn)
    if alert_changed:
        db.append_dossier_state_event(session_id, qid, eff_turn, "alert_level", int(dossier.get("alert_level") or 0), new_alert, conn=conn)

    saved = db.upsert_quest_dossier(
        session_id,
        qid,
        alert_level=new_alert if alert_changed else None,
        leads_graph=leads if leads_changed else None,
        climax_spec=climax,
        conn=conn,
    )
    if sync_needed and saved:
        try:
            db.sync_quest_projection_from_dossier(session_id, qid, dossier=saved, conn=conn)
        except Exception as exc:
            log.warning("sync_quest_projection_from_dossier failed inside threat_clock for %s: %s", qid, exc)

    return {"directives": directives, "notes": notes, "clock": clk}


def tick_threat_clock(
    session_id: int,
    new_day: int,
    new_minute: int,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Advances the active chapter's 6-segment Threat Clock (1 tick per 240 in-game minutes).
    Respects Q7 (story Ch.1-10, non-endless, pauses during climax combat) and E1 (0 ticks until engaged_flag=1).
    """
    import db

    if not session_id:
        return {"ticked": False, "ticks_added": 0, "directives": []}
    if conn is None:
        with db.UnitOfWork() as uow_conn:
            return tick_threat_clock(
                session_id,
                new_day,
                new_minute,
                turn_number=turn_number,
                conn=uow_conn,
            )
    sess = db.get_session(session_id) or {}
    sq = db.get_minimal_story_quest(session_id, None, conn=conn)
    if not sq:
        return {"ticked": False, "ticks_added": 0, "directives": []}
    qid = str(sq.get("quest_id") or "")
    dossier = db.get_quest_dossier(session_id, qid, conn=conn)
    if not dossier or not is_threat_clock_eligible(sess, sq, dossier):
        return {"ticked": False, "ticks_added": 0, "directives": []}

    climax = copy.deepcopy(dossier.get("climax_spec") or {})
    if _is_in_climax_combat(sess, qid, climax):
        return {"ticked": False, "ticks_added": 0, "paused_climax_combat": True, "directives": []}

    # E1: never tick before chapter engagement
    if int(dossier.get("engaged_flag") or 0) == 0:
        return {"ticked": False, "ticks_added": 0, "unengaged": True, "directives": []}

    prev_climax = copy.deepcopy(dossier.get("climax_spec") or {})
    clk = _ensure_clock_dict(climax, True)
    abs_now = _abs_minutes(new_day, new_minute)
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id, sess=sess, conn=conn))

    last_abs = clk.get("last_tick_minute_abs")
    if last_abs is None:
        clk["last_tick_minute_abs"] = abs_now
        clk["pending_minutes"] = 0
        climax["threat_clock"] = clk
        db.append_dossier_state_event(session_id, qid, eff_turn, "climax_spec", prev_climax, climax, conn=conn)
        db.upsert_quest_dossier(session_id, qid, climax_spec=climax, conn=conn)
        return {"ticked": False, "ticks_added": 0, "initialized": True, "clock": clk, "directives": []}

    delta = max(0, abs_now - int(last_abs))
    if delta <= 0:
        return {"ticked": False, "ticks_added": 0, "clock": clk, "directives": []}

    total_acc = int(clk.get("pending_minutes") or 0) + delta
    ticks = total_acc // THREAT_CLOCK_MINUTES_PER_TICK
    rem = total_acc % THREAT_CLOCK_MINUTES_PER_TICK
    old_filled = int(clk["filled"])
    new_filled = min(int(clk["max_segments"]), old_filled + ticks)

    clk["last_tick_minute_abs"] = abs_now
    clk["pending_minutes"] = rem
    clk["filled"] = new_filled
    climax["threat_clock"] = clk

    cons_res = _apply_threshold_consequences(
        session_id=session_id,
        dossier=dossier,
        quest=sq,
        sess=sess,
        climax=climax,
        clk=clk,
        eff_turn=eff_turn,
        conn=conn,
        prev_climax=prev_climax,
    )
    return {
        "ticked": new_filled > old_filled,
        "ticks_added": max(0, new_filled - old_filled),
        "filled": new_filled,
        "max_segments": clk["max_segments"],
        "clock": cons_res.get("clock") or clk,
        "directives": cons_res.get("directives") or [],
        "notes": cons_res.get("notes") or [],
    }


def decrement_threat_clock(
    session_id: int,
    quest_id: str,
    delta: int = 1,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Optional[Dict[str, Any]]:
    """Q8: Completing a main stage takes back 1 Threat Clock tick (`max(0, filled - 1)`)."""
    import db

    if not session_id or not quest_id:
        return None
    if conn is None:
        with db.UnitOfWork() as uow_conn:
            return decrement_threat_clock(
                session_id,
                quest_id,
                delta=delta,
                turn_number=turn_number,
                conn=uow_conn,
            )
    sess = db.get_session(session_id) or {}
    q = db.get_minimal_story_quest(session_id, quest_id, conn=conn)
    dossier = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not dossier or not is_threat_clock_eligible(sess, q, dossier):
        return None
    prev_climax = copy.deepcopy(dossier.get("climax_spec") or {})
    climax = copy.deepcopy(prev_climax)
    clk = _ensure_clock_dict(climax, True)
    old_filled = int(clk["filled"])
    new_filled = max(0, old_filled - max(1, int(delta or 1)))
    if new_filled == old_filled:
        return clk
    clk["filled"] = new_filled
    climax["threat_clock"] = clk
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id, sess=sess, conn=conn))
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax, conn=conn)
    db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, conn=conn)
    return clk
