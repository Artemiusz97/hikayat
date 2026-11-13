from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import db
from db import adb
import llm_client
import namegen
import scenario_data
import skill_check
from mechanics.narrative.blueprints import get_max_campaign_chapters
from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility
from mechanics.narrative.campaign_spine import (
    compile_chronicle_tapestry,
    compile_or_get_campaign_spine,
    select_chapter_storylet,
    update_campaign_ending_axes,
)
from mechanics.narrative.dossier_compiler import (
    compile_quest_dossier,
    infer_quest_family_tier,
)
from mechanics.narrative.quest_engines import (
    build_turn_in_rules,
    normalize_quest_locale,
    render_world_scar_spec,
)
from mechanics.world.world_events.engine import (
    resolve_world_scar_via_bounty,
    spawn_endless_mode_contracts,
    spawn_quest_world_scar,
)
from models.llm_schemas import DossierEnrichment

logger = logging.getLogger(__name__)

_INTERNAL_TAG_RE = re.compile(r"\[(?:ITEM_JSON|GEAR_JSON|SPELLBOOK_JSON)\][^\n]*", re.IGNORECASE)
_STAT_LEAK_RE = re.compile(r"(?:\bDC\s*\d+|\b\d+\s*(?:HP|MP)|(?<!\w)[+-]?\d+%\s*chance\b)", re.IGNORECASE)


def sanitize_dossier_prose(text: str) -> str:
    """Strips internal JSON tags and raw HP/MP/DC stat leaks from player-facing quest prose."""
    if not text:
        return ""
    cleaned = _INTERNAL_TAG_RE.sub("", str(text))
    cleaned = _STAT_LEAK_RE.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def compile_campaign_spine_at_turn_zero(
    session_id: int,
    scen_key: str = "",
    lang: str = "en",
    scenario_key: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Turn 0 hook across ALL scenarios:
    Deterministically compiles the 11-chapter `CampaignSpine` and compiles Chapter 1's
    `QuestDossier` if an active Story Quest already exists.
    """
    if not session_id:
        return {}
    sess = db.get_session(session_id) or {}
    eff_scen = str(scenario_key or scen_key or sess.get("scenario") or "fantasy")
    eff_lang = normalize_quest_locale(lang or sess.get("narration_language") or sess.get("language") or "en")

    spine = compile_or_get_campaign_spine(session_id=session_id, scen_key=eff_scen, lang=eff_lang)

    active_sq = db.get_active_story_quest(session_id)
    if active_sq and active_sq.get("quest_id"):
        sq_id = str(active_sq["quest_id"])
        is_legacy_midchapter = bool(
            not active_sq.get("has_structured_objectives")
            and str(active_sq.get("dossier_stage") or "legacy") == "legacy"
            and len(active_sq.get("sub_objectives") or []) > 0
        )
        existing_dos = db.get_quest_dossier(session_id, sq_id)
        if not is_legacy_midchapter and (not existing_dos or existing_dos.get("status_stage") != "compiled"):
            ch1_bp = (spine.get("chapters_blueprint") or {}).get("1") or {}
            feat_lt = ch1_bp.get("featured_lieutenant")
            feat_lt_name = str(feat_lt.get("name") if isinstance(feat_lt, dict) else (feat_lt or ""))
            compile_quest_dossier(
                session_id=session_id,
                quest_id=sq_id,
                tag_or_archetype=str(ch1_bp.get("engine") or active_sq.get("quest_type") or "MYSTERY_CASE"),
                title=str(active_sq.get("title") or ch1_bp.get("title_template") or "Chapter #1"),
                objective=str(active_sq.get("objective") or ""),
                family_tier="story",
                chapter=int(db.get_session_chapter(session_id) or 1),
                turn_number=0,
                target_npc=feat_lt_name,
                reward_gold=int(active_sq.get("reward_gold") or 70),
                scen_key=eff_scen,
                lang=eff_lang,
            )
    return spine


def seed_or_discover_dossier_clue(
    session_id: int,
    quest_id: str,
    clue_index: int = 0,
    source_location: str = "",
    conn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Materializes a predetermined clue from `dossier.clue_graph` into `session_clues`
    and records its integer `clue_id` back into `clue_graph` for deterministic pairing.
    """
    dossier = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not dossier:
        return None
    raw_cg = dossier.get("clue_graph")
    if isinstance(raw_cg, dict):
        cg_items = raw_cg.get("nodes") if isinstance(raw_cg.get("nodes"), (list, tuple)) else list(raw_cg.values())
    elif isinstance(raw_cg, (list, tuple)):
        cg_items = raw_cg
    else:
        cg_items = []
    clue_graph = [n for n in cg_items if isinstance(n, dict)]
    if not clue_graph or clue_index < 0 or clue_index >= len(clue_graph):
        return None

    node = dict(clue_graph[clue_index])
    if node.get("clue_id"):
        existing_c = db.get_session_clue_by_id(int(node["clue_id"]), conn=conn)
        if existing_c:
            return existing_c

    sess = db.get_session(session_id) or {}
    cur_ch = int(db.get_session_chapter(session_id) or 1)
    loc = str(source_location or (dossier.get("climax_spec") or {}).get("location") or sess.get("current_location") or "District")
    suspect_name = str(
        (dossier.get("climax_spec") or {}).get("innocent_suspect")
        if node.get("is_red_herring")
        else (dossier.get("climax_spec") or {}).get("true_culprit") or ""
    )
    cat = "testimonial" if "testimony" in str(node.get("title") or "").lower() else "physical"

    clue_id = db.add_session_clue(
        session_id=session_id,
        title=sanitize_dossier_prose(str(node.get("title") or "Investigation Lead")).strip(),
        lead_text=sanitize_dossier_prose(str(node.get("lead_text") or "Uncovered corroborating evidence.")),
        category=cat,
        source_location=loc,
        linked_npc=suspect_name,
        quest_id=quest_id,
        chapter=cur_ch,
        conn=conn,
    )
    node["clue_id"] = int(clue_id)
    clue_graph[clue_index] = node
    db.upsert_quest_dossier(session_id, quest_id, clue_graph=clue_graph, conn=conn)
    return db.get_session_clue_by_id(int(clue_id), conn=conn)


def sync_waypoints_from_dossier(
    session_id: int,
    quest_id: str,
    dossier: Dict[str, Any],
    force_replace: bool = False,
) -> List[Dict[str, Any]]:
    """
    Synchronizes `quest_waypoints` and `quests.sub_objectives_json` for a compiled `QuestDossier`
    (`1 Main Objective` on `sub_obj_id = 0` + `1–3` Typed Optionals on `sub_obj_id = 1..3`),
    while preserving legacy un-structured waypoints when no `main_stages` exist.
    """
    climax = dict((dossier or {}).get("climax_spec") or {})
    leads = list((dossier or {}).get("leads_graph") or [])
    if climax.get("main_stages") or any(isinstance(ld, dict) and ld.get("is_optional") for ld in leads):
        db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=dossier)
        return db.get_quest_waypoints(session_id, quest_id, sub_obj_id=None) or []

    existing_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id=None) or []
    from mechanics.narrative.dossier_compiler import is_safe_sanctuary_location
    has_sanctuary_wp = any(is_safe_sanctuary_location(w.get("target_location", "")) for w in existing_wps)
    if existing_wps and not force_replace and len(existing_wps) >= 2 and not has_sanctuary_wp:
        return existing_wps

    climax_loc = str(climax.get("location") or "Central District")
    waypoints: List[Dict[str, Any]] = []

    for idx, ld in enumerate(leads, start=1):
        waypoints.append(
            {
                "stage_index": idx,
                "stage_label": sanitize_dossier_prose(str(ld.get("title") or f"Investigate Lead #{idx}"))[:200],
                "target_location": str(ld.get("target_location") or climax_loc)[:200],
                "target_npc": str(ld.get("target_npc") or "")[:100],
                "completion_trigger": "skill_check",
                "status": "active",
            }
        )

    climax_unlocked = bool(climax.get("gate_type") == "open" or climax.get("is_unlocked"))
    target_culprit = str(climax.get("true_culprit") or "") if climax_unlocked else ""
    waypoints.append(
        {
            "stage_index": len(waypoints) + 1,
            "stage_label": sanitize_dossier_prose(f"Resolve final confrontation at {climax_loc}")[:200],
            "target_location": climax_loc[:200],
            "target_npc": target_culprit[:100],
            "completion_trigger": "skill_check",
            "status": "active" if climax_unlocked else "locked",
        }
    )

    if len(waypoints) < 2:
        waypoints.insert(
            0,
            {
                "stage_index": 1,
                "stage_label": f"Arrive at {climax_loc}",
                "target_location": climax_loc[:200],
                "completion_trigger": "arrival",
                "status": "active",
            },
        )
        for i, w in enumerate(waypoints, start=1):
            w["stage_index"] = i

    db.save_quest_waypoints(session_id, quest_id, waypoints, sub_obj_id=None)
    return db.get_quest_waypoints(session_id, quest_id, sub_obj_id=None) or waypoints


def sync_dossier_main_stage_advance(
    session_id: int,
    quest_id: str,
    completed_stage_idx: int,
    cur_loc: str = "",
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """Atomically resolves Main Stage completion, unlocks Secret Climax (D2),
    materializes non-duplicate clue nodes, and projects into quests/waypoints."""
    def _run(c: Any) -> Dict[str, Any]:
        dos = db.get_quest_dossier(session_id, quest_id, conn=c)
        if not dos:
            return {}

        climax = dict(dos.get("climax_spec") or {})
        main_stages = [dict(s) for s in (climax.get("main_stages") or [])]
        if not main_stages:
            return {}

        gate_type = str(climax.get("gate_type") or climax.get("gate_mode") or "open").lower()
        tot_stages = len(main_stages)
        target_ms = next((m for m in main_stages if int(m.get("stage_index") or 1) == completed_stage_idx), None)
        newly_completed = bool(
            target_ms
            and not bool(target_ms.get("completed"))
            and str(target_ms.get("status") or "").lower() not in ("completed", "bypassed")
            and not bool(target_ms.get("is_climax_stage"))
        )

        # D2 Dual-Path: Unlock Climax BEFORE setting next stage status
        climax_unlocked = False
        if completed_stage_idx >= tot_stages - 1 and gate_type == "secret":
            climax["is_unlocked"] = True
            climax["secret_lair_locked"] = False
            climax_unlocked = True
            db.unlock_climax_waypoint(
                session_id, quest_id,
                str(climax.get("location") or ""),
                str(climax.get("true_culprit") or ""),
                conn=c,
            )

        # Advance stages
        for s in main_stages:
            st_idx = int(s.get("stage_index") or 1)
            if st_idx <= completed_stage_idx:
                s["status"] = "completed"
                s["completed"] = True
            elif st_idx == completed_stage_idx + 1:
                is_climax = bool(s.get("is_climax_stage") or st_idx == tot_stages)
                if not is_climax or gate_type != "secret" or bool(climax.get("is_unlocked")):
                    s["status"] = "active"
                    s["completed"] = False
                else:
                    s["status"] = "locked"
            else:
                if not s.get("completed"):
                    s["status"] = "locked"

        climax["main_stages"] = main_stages

        # Materialize clue for the completed stage without duplicate add_session_clue spam
        if completed_stage_idx >= 1:
            seed_or_discover_dossier_clue(session_id, quest_id, clue_index=completed_stage_idx - 1, source_location=cur_loc, conn=c)

        saved = db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, conn=c)
        if newly_completed and completed_stage_idx >= 1:
            try:
                from mechanics.narrative.threat_clock import decrement_threat_clock
                eff_t = int(db.get_effective_session_turn(session_id))
                decrement_threat_clock(session_id, quest_id, delta=1, turn_number=eff_t, conn=c)
                saved = db.get_quest_dossier(session_id, quest_id, conn=c) or saved
            except Exception:
                pass
        if saved:
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved, conn=c)
            res_dict = dict(saved)
            res_dict["climax_unlocked"] = climax_unlocked
            res_dict["completed_stage_idx"] = completed_stage_idx
            res_dict["next_stage_idx"] = completed_stage_idx + 1
            res_dict["total_stages"] = tot_stages
            return res_dict

        return {
            "quest_id": quest_id,
            "completed_stage_idx": completed_stage_idx,
            "next_stage_idx": completed_stage_idx + 1,
            "climax_unlocked": climax_unlocked,
            "total_stages": tot_stages,
        }

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_c:
        return _run(uow_c)


def heal_session_quests_on_load(session_id: int) -> bool:
    """Idempotently heals placeholder lieutenants, splices missing mid-stages,
    repairs Optional titles, and converts active legacy clue-eligible stages (Q2)
    without DDL changes or N+1 query storms."""
    if not session_id:
        return False
    from mechanics.narrative.campaign_spine import heal_campaign_spine_if_stale, _PLACEHOLDER_ACTOR_RE
    from mechanics.narrative.chapter_plan import build_chapter_plan_candidates, is_clue_based_quest
    from mechanics.narrative.dossier_compiler import (
        format_short_venue_display,
        get_protected_quest_cast_names,
        populate_stage_clue_sources,
    )
    from mechanics.narrative.threat_clock import build_initial_threat_clock

    spine = db.get_campaign_spine(session_id)
    active_dossiers = db.get_session_quest_dossiers(session_id, status_stage="compiled") or []
    if not spine and not active_dossiers:
        return False

    healed_spine, rename_map = (
        heal_campaign_spine_if_stale(session_id, spine, auto_commit=False)
        if spine
        else (None, {})
    )
    story_dos = next((d for d in active_dossiers if d.get("family_tier") == "story"), None)

    needs_splice = False
    needs_target_fix = False
    needs_opt_fix = False
    needs_clock_init = False
    if story_dos:
        cs_s = story_dos.get("climax_spec") or {}
        ms = cs_s.get("main_stages") or []
        climax_done = bool(cs_s.get("completed"))
        needs_splice = (len(ms) < 3 and not climax_done)
        protected_low = get_protected_quest_cast_names(session_id)
        cur_tgt = str(story_dos.get("target_npc") or cs_s.get("true_culprit") or "").strip()
        if cur_tgt.lower() in protected_low or _PLACEHOLDER_ACTOR_RE.search(cur_tgt):
            needs_target_fix = True
        climax_loc = str(cs_s.get("location") or "")
        climax_short = format_short_venue_display(climax_loc)
        for ld in (story_dos.get("leads_graph") or []):
            if ld.get("target_location") == climax_loc or (climax_short and climax_short in str(ld.get("title") or ld.get("label") or "")):
                needs_opt_fix = True
        ch_num = int(cs_s.get("chapter") or 1)
        if ch_num < 11 and not isinstance(cs_s.get("threat_clock"), dict):
            needs_clock_init = True

    # Q2: Check active stage ONLY of existing clue-eligible quests lacking >=3 clue_sources
    dossiers_needing_q2: List[Dict[str, Any]] = []
    for dos_cand in active_dossiers:
        fam_c = str(dos_cand.get("family_tier") or "")
        eng_c = str(dos_cand.get("engine") or "")
        if not is_clue_based_quest(fam_c, eng_c):
            continue
        cs_c = dos_cand.get("climax_spec") or {}
        if cs_c.get("completed"):
            continue
        for st_c in (cs_c.get("main_stages") or []):
            if (
                isinstance(st_c, dict)
                and str(st_c.get("status") or "").lower() == "active"
                and not st_c.get("completed")
                and not st_c.get("is_climax_stage")
            ):
                srcs_c = [x for x in (st_c.get("clue_sources") or []) if isinstance(x, dict)]
                if str(st_c.get("completion_trigger") or "") != "key_clue" or len(srcs_c) < 3:
                    dossiers_needing_q2.append(dos_cand)
                break

    if (
        not rename_map
        and not needs_splice
        and not needs_target_fix
        and not needs_opt_fix
        and not needs_clock_init
        and not dossiers_needing_q2
        and healed_spine == spine
    ):
        return False  # Fast early-return: 0 writes

    with db.UnitOfWork() as conn:
        if spine and healed_spine is not None and healed_spine != spine:
            db.upsert_campaign_spine(session_id, healed_spine, conn=conn)

        if rename_map:
            for old_n, new_n in rename_map.items():
                conn.execute(
                    "UPDATE quests SET title=replace(title, ?, ?), objective=replace(objective, ?, ?) "
                    "WHERE session_id=? AND (title LIKE ? OR objective LIKE ?)",
                    (old_n, new_n, old_n, new_n, session_id, f"%{old_n}%", f"%{old_n}%")
                )
                conn.execute(
                    "UPDATE quest_waypoints SET stage_label=replace(stage_label, ?, ?), target_npc=replace(target_npc, ?, ?) "
                    "WHERE session_id=? AND (stage_label LIKE ? OR target_npc LIKE ?)",
                    (old_n, new_n, old_n, new_n, session_id, f"%{old_n}%", f"%{old_n}%")
                )
                conn.execute(
                    "UPDATE session_clues SET title=replace(title, ?, ?), lead_text=replace(lead_text, ?, ?), linked_npc=replace(linked_npc, ?, ?) "
                    "WHERE session_id=? AND (title LIKE ? OR lead_text LIKE ? OR linked_npc LIKE ?)",
                    (old_n, new_n, old_n, new_n, old_n, new_n, session_id, f"%{old_n}%", f"%{old_n}%", f"%{old_n}%")
                )

        if story_dos and healed_spine is not None and (rename_map or needs_splice or needs_target_fix or needs_opt_fix):
            _heal_story_dossier_atomic(session_id, story_dos, healed_spine, rename_map, needs_splice, conn=conn)

        # Q2: Initialize missing threat_clock and convert active stage ONLY for clue-eligible dossiers
        sess_h = db.get_session(session_id) or {}
        lang_h = normalize_quest_locale(sess_h.get("narration_language") or sess_h.get("language") or "en")
        scen_h = str(sess_h.get("scenario") or "")
        q2_ids = {str(d.get("quest_id") or "") for d in dossiers_needing_q2}
        if needs_clock_init and story_dos and str(story_dos.get("quest_id") or "") not in q2_ids:
            q2_ids.add(str(story_dos.get("quest_id") or ""))
        for qid_q2 in sorted(x for x in q2_ids if x):
            fresh_q2 = db.get_quest_dossier(session_id, qid_q2, conn=conn)
            if not fresh_q2:
                continue
            clx_q2 = dict(fresh_q2.get("climax_spec") or {})
            changed_q2 = False
            if str(fresh_q2.get("family_tier") or "") == "story":
                ch_q2 = int(clx_q2.get("chapter") or sess_h.get("chapter") or 1)
                if ch_q2 < 11 and not isinstance(clx_q2.get("threat_clock"), dict):
                    clx_q2["threat_clock"] = build_initial_threat_clock(
                        chapter=ch_q2,
                        endless_mode_unlocked=bool(sess_h.get("endless_mode_unlocked")),
                    )
                    changed_q2 = True
            if is_clue_based_quest(str(fresh_q2.get("family_tier") or ""), str(fresh_q2.get("engine") or "")) and not clx_q2.get("completed"):
                ms_q2 = [dict(s) for s in (clx_q2.get("main_stages") or []) if isinstance(s, dict)]
                c_loc_q2 = str(clx_q2.get("location") or "")
                cands_q2 = build_chapter_plan_candidates(session_id, fresh_q2, climax_location=c_loc_q2)
                for idx_s, st_s in enumerate(ms_q2):
                    if str(st_s.get("status") or "").lower() == "active" and not st_s.get("completed") and not st_s.get("is_climax_stage"):
                        srcs_s = [x for x in (st_s.get("clue_sources") or []) if isinstance(x, dict)]
                        if str(st_s.get("completion_trigger") or "") != "key_clue" or len(srcs_s) < 3:
                            ms_q2[idx_s] = populate_stage_clue_sources(
                                session_id,
                                qid_q2,
                                st_s,
                                climax_loc=c_loc_q2,
                                leads_graph=list(fresh_q2.get("leads_graph") or []),
                                candidate_rooms=cands_q2.get("rooms"),
                                candidate_npcs=cands_q2.get("npcs"),
                                danger_tier=max(1, int(fresh_q2.get("danger_tier") or 1)),
                                lang=lang_h,
                                scen_key=scen_h,
                            )
                            changed_q2 = True
                        break  # Convert ONLY the active stage; leave finished & locked stages untouched
                if changed_q2:
                    clx_q2["main_stages"] = ms_q2
            if changed_q2:
                saved_q2 = db.upsert_quest_dossier(session_id, qid_q2, climax_spec=clx_q2, conn=conn)
                if saved_q2:
                    db.sync_quest_projection_from_dossier(session_id, qid_q2, dossier=saved_q2, conn=conn)

    return True


def _heal_story_dossier_atomic(session_id: int, dos: dict, spine: dict, rename_map: dict, needs_splice: bool, conn=None):
    from mechanics.narrative.dossier_compiler import format_short_venue_display, get_protected_quest_cast_names
    from mechanics.narrative.campaign_spine import _PLACEHOLDER_ACTOR_RE
    qid = str(dos["quest_id"])
    climax = dict(dos.get("climax_spec") or {})
    leads = [dict(l) for l in (dos.get("leads_graph") or [])]
    cast = dict(dos.get("cast_bindings") or {})
    main_stages = [dict(s) for s in (climax.get("main_stages") or [])]

    # 1. Hot-swap protected or placeholder target
    protected_low = get_protected_quest_cast_names(session_id)
    cur_tgt = str(climax.get("true_culprit") or climax.get("target_npc") or dos.get("target_npc") or "")
    if cur_tgt.lower() in protected_low or _PLACEHOLDER_ACTOR_RE.search(cur_tgt):
        cur_ch = int(dos.get("chapter") or 1)
        feat_lt = (spine.get("chapters_blueprint") or {}).get(str(cur_ch), {}).get("featured_lieutenant")
        lt_name = str(feat_lt.get("name") if isinstance(feat_lt, dict) else (feat_lt or ""))
        if not lt_name or lt_name.lower() in protected_low or _PLACEHOLDER_ACTOR_RE.search(lt_name):
            active_lts = [lt for lt in (spine.get("lieutenants_roster") or []) if lt.get("status") == "active" and lt.get("name") and lt["name"].lower() not in protected_low and not _PLACEHOLDER_ACTOR_RE.search(lt["name"])]
            lt_name = active_lts[0]["name"] if active_lts else "Hostile Commander"
        climax["true_culprit"] = lt_name
        climax["target_npc"] = lt_name
        dos["target_npc"] = lt_name
        if "target" in cast and isinstance(cast["target"], dict):
            cast["target"]["name"] = lt_name

    # Apply rename_map to cast
    for r_k, r_v in cast.items():
        if isinstance(r_v, dict) and r_v.get("name") in rename_map:
            r_v["name"] = rename_map[r_v["name"]]

    # 2. Smart Splice (D1): Insert missing stages so Story Quests always have 3 main stages
    if needs_splice and len(main_stages) < 3:
        st1 = dict(main_stages[0]) if main_stages else {"stage_index": 1, "status": "active", "completed": False}
        st1["is_climax_stage"] = False
        if len(main_stages) >= 2:
            old_climax = dict(main_stages[1])
        else:
            old_climax = {
                "stage_index": 3,
                "stage_label": f"Confront {climax.get('true_culprit', 'the Mastermind')}",
                "target_location": str(climax.get("location") or ""),
                "target_npc": str(climax.get("true_culprit") or ""),
                "completion_trigger": "combat",
                "status": "locked",
                "completed": False,
                "is_climax_stage": True,
            }
        st1_done = bool(st1.get("completed") or str(st1.get("status") or "") in ("completed", "bypassed"))
        climax_loc = str(old_climax.get("target_location") or climax.get("location") or "")
        st1_loc = str(st1.get("target_location") or "")

        def _run_splice_db(c_db):
            node = c_db.execute(
                "SELECT name FROM world_nodes WHERE session_id=? AND node_type='ROOM' AND name NOT IN (?, ?) LIMIT 1",
                (session_id, st1_loc, climax_loc)
            ).fetchone()
            mid_val = str(node["name"] if node and isinstance(node, dict) else (node[0] if node else (leads[0].get("target_location") if leads else f"Relay Sub-Node of {format_short_venue_display(climax_loc)}")))
            c_db.execute("DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND stage_index >= 2", (session_id, qid))
            return mid_val

        if conn is not None:
            mid_loc = _run_splice_db(conn)
        else:
            with db.UnitOfWork() as uow_c:
                mid_loc = _run_splice_db(uow_c)

        new_st2 = {
            "stage_index": 2,
            "stage_label": f"Infiltrate supply relay at {format_short_venue_display(mid_loc)}",
            "label": f"Infiltrate supply relay at {format_short_venue_display(mid_loc)}",
            "target_location": mid_loc,
            "target_npc": "",
            "completion_trigger": "action",
            "approaches": ["STR", "INT", "CHA"],
            "status": "active" if st1_done else "locked",
            "completed": False,
            "is_climax_stage": False,
            "beat_contract": {
                "player_verb": f"Breach relay at {format_short_venue_display(mid_loc)}",
                "reveal": f"Telemetry logs pinpoint headquarters at {format_short_venue_display(climax_loc)}",
                "handover": "Relay access cipher",
                "next_pointer": format_short_venue_display(climax_loc),
                "is_dialogue_beat": False,
            }
        }
        old_climax["stage_index"] = 3
        old_climax["status"] = "locked"
        old_climax["completed"] = False
        if old_climax.get("target_npc") and cur_tgt in rename_map:
            old_climax["target_npc"] = rename_map[cur_tgt]
        elif old_climax.get("target_npc") and old_climax["target_npc"].lower() in protected_low:
            old_climax["target_npc"] = climax.get("true_culprit")
        climax["main_stages"] = [st1, new_st2, old_climax]
        climax["main_stage_count"] = 3
        if str(climax.get("gate_type") or "").lower() == "secret":
            climax["is_unlocked"] = False

    # 3. Repair Optionals that leaked climax_loc
    climax_loc = str(climax.get("location") or "")
    climax_short = format_short_venue_display(climax_loc)
    for ld in leads:
        lead_loc = str(ld.get("target_location") or "")
        if lead_loc == climax_loc or not lead_loc:
            lead_loc = str(ld.get("lead_loc") or "District Forward Post")
            if lead_loc == climax_loc:
                lead_loc = "District Forward Post"
            ld["target_location"] = lead_loc
        lead_short = format_short_venue_display(lead_loc)
        for k in ("title", "label"):
            if k in ld and ld[k]:
                t = str(ld[k])
                if climax_loc and climax_loc in t:
                    t = t.replace(climax_loc, lead_short)
                if climax_short and climax_short in t:
                    t = t.replace(climax_short, lead_short)
                ld[k] = t

    saved = db.upsert_quest_dossier(session_id, qid, climax_spec=climax, leads_graph=leads, cast_bindings=cast, conn=conn)
    if saved:
        db.sync_quest_projection_from_dossier(session_id, qid, dossier=saved, conn=conn)


async def enrich_dossier_with_utility_llm(
    session_id: int,
    quest_id: str,
    dossier: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bounded (`timeout=4.0`, `retries=0`, `use_utility=True`) flavor enrichment pass.
    Routes NSFW / hybrid quests to `NSFW_LLM_UTILITY_MODEL` via `is_nsfw=uses_nsfw_routing`.
    Polishes Main + Optional flavor notes and `stakes_hint` prose while never mutating deterministic topology.
    Falls back instantaneously to the deterministic 5-locale `QuestDossier` on timeout/offline.
    """
    dos = dossier or await adb(db.get_quest_dossier, session_id, quest_id)
    if not dos:
        return {}

    sess = await adb(db.get_session, session_id) or {}
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    uses_nsfw = bool((dos.get("contract_economy") or {}).get("uses_nsfw_routing"))
    stub = dict(dos.get("pitch_stub") or {})
    leads = [dict(l) for l in (dos.get("leads_graph") or [])]
    climax = dict(dos.get("climax_spec") or {})
    twist = dict(dos.get("twist_spec") or {})

    opt_roles = [str(l.get("role") or "aid") for l in leads]
    sys_prompt = (
        "You enrich tabletop RPG quest dossiers with vivid, context-aware flavor prose. "
        "NEVER include raw HP/MP/DC numbers or internal JSON tags ([ITEM_JSON], [GEAR_JSON], [SPELLBOOK_JSON]). "
        f"Respond strictly in JSON matching the schema in language '{lang}'."
    )
    usr_prompt = (
        f"Engine: {dos.get('engine')}\n"
        f"Title: {stub.get('title')}\n"
        f"Pitch: {stub.get('public_pitch')}\n"
        f"Main Stages: {len(climax.get('main_stages') or [])}\n"
        f"Optional Roles ({len(leads)}): {', '.join(opt_roles)}\n"
        f"Has Twist: {twist.get('has_twist')} ({twist.get('twist_type')})"
    )
    try:
        enriched = await llm_client.call_llm_json(
            sys_prompt,
            usr_prompt,
            temperature=0.5,
            max_tokens=600,
            retries=0,
            is_nsfw=uses_nsfw,
            use_utility=True,
            timeout=4.0,
            response_model=DossierEnrichment,
        )
        if enriched:
            p_txt = sanitize_dossier_prose(enriched.get("public_pitch") or enriched.get("objective_flavor") or "")
            if p_txt:
                stub["public_pitch"] = p_txt
            m_labels = list(enriched.get("main_stage_labels") or [])
            main_stages = [dict(ms) for ms in (climax.get("main_stages") or [])]
            for idx, m_lbl in enumerate(m_labels):
                if idx < len(main_stages) and m_lbl:
                    clean_m = sanitize_dossier_prose(str(m_lbl))
                    if clean_m:
                        main_stages[idx]["stage_label"] = clean_m[:180]
                        main_stages[idx]["label"] = clean_m[:180]
            if main_stages:
                climax["main_stages"] = main_stages
            l_descs = list(enriched.get("lead_descriptions") or enriched.get("lead_titles") or [])
            for idx, desc in enumerate(l_descs):
                if idx < len(leads) and desc:
                    clean_d = sanitize_dossier_prose(str(desc))
                    if clean_d:
                        leads[idx]["flavor_note"] = clean_d
            s_hints = list(enriched.get("stakes_hints") or [])
            for idx, sh in enumerate(s_hints):
                if idx < len(leads) and sh:
                    clean_sh = sanitize_dossier_prose(str(sh))
                    if clean_sh:
                        leads[idx]["stakes_hint"] = clean_sh[:160]
            t_txt = sanitize_dossier_prose(enriched.get("twist_summary") or "")
            if twist.get("has_twist") and t_txt:
                twist["summary"] = t_txt
            saved = await adb(
                db.upsert_quest_dossier,
                session_id,
                quest_id,
                pitch_stub=stub,
                leads_graph=leads,
                climax_spec=climax,
                twist_spec=twist,
            )
            if saved and (climax.get("main_stages") or any(l.get("is_optional") for l in leads)):
                await adb(db.sync_quest_projection_from_dossier, session_id, quest_id, saved)
            return saved or dos
    except Exception as exc:
        logger.debug("Utility LLM dossier enrichment skipped/fell back for %s: %s", quest_id, exc)
    return dos


def accept_bounty_contract(
    session_id: int,
    quest_id: str,
    user_id: Optional[int] = None,
    haggle_advance: bool = False,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Stage-1 -> Stage-2 Bounty Transition (`Available -> Active`, `pitch -> compiled`):
    - Enforces 3-bounty cap & Anomalous faction eligibility.
    - Compiles full hidden `QuestDossier` deterministically (`<20ms`).
    - Spawns tangible locked MacGuffin hook if applicable & syncs waypoints.
    - Optionally resolves upfront `CHA` Gold advance (`haggle_advance=True`).
    """
    quest = db.get_quest_by_id(session_id, quest_id)
    if not quest:
        return {"success": False, "status_code": 404, "reason": "Bounty contract not found."}
    if quest.get("status") not in ("Available", "Active"):
        return {"success": False, "status_code": 400, "reason": "Contract is no longer available."}

    sess = db.get_session(session_id) or {"id": session_id}
    scen_key = str(sess.get("scenario") or "fantasy")
    eff_uid = int(user_id) if user_id is not None else int(sess.get("host_user_id") or 0)

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        elig = evaluate_anomalous_bounty_eligibility(session_id, eff_uid or None, quest)
        if not elig.get("allowed", True):
            return {
                "success": False,
                "status_code": 400,
                "reason": elig.get("reason") or "Faction rules prohibit accepting this bounty.",
            }

    from game_engine.quests import can_accept_side_bounty
    if quest.get("status") == "Available" and not can_accept_side_bounty(session_id, quest):
        return {
            "success": False,
            "status_code": 400,
            "reason": "Maximum 3 active side bounties reached! Complete or abandon one first.",
        }

    was_pitch = str(quest.get("dossier_stage") or "") == "pitch"
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    cur_ch = int(db.get_session_chapter(session_id) or 1)

    db.update_quest_status(session_id, quest_id, "Active")

    fam_tier = infer_quest_family_tier(
        quest_id=quest_id,
        quest_type=str(quest.get("quest_type") or ""),
        is_story_quest=bool(quest.get("is_story_quest")),
        quest_notes=str(quest.get("quest_notes") or ""),
    )
    dossier = compile_quest_dossier(
        session_id=session_id,
        quest_id=quest_id,
        tag_or_archetype=str(quest.get("engine") or quest.get("quest_type") or quest.get("blueprint_id") or "Investigation"),
        title=str(quest.get("title") or ""),
        objective=str(quest.get("objective") or ""),
        family_tier=fam_tier,
        chapter=cur_ch,
        turn_number=eff_turn,
        client_npc=str(quest.get("client_npc") or ""),
        preferred_location=str(quest.get("client_location") or sess.get("current_location") or ""),
        required_item=str(quest.get("required_item") or ""),
        reward_gold=int(quest.get("reward_gold") or 50),
        scen_key=scen_key,
    )

    sync_waypoints_from_dossier(session_id, quest_id, dossier, force_replace=False)

    advance_result: Optional[Dict[str, Any]] = None
    if haggle_advance and eff_uid:
        econ = dict(dossier.get("contract_economy") or {})
        if not econ.get("advance_taken"):
            char = db.get_character(eff_uid) or {}
            cha_val = int(char.get("cha", 5) or 5)
            chk = skill_check.resolve_check(stat_name="CHA", stat_value=cha_val, requirement=6)
            if chk.succeeded:
                base_gold = int(econ.get("base_gold") or quest.get("reward_gold") or 50)
                adv_gold = max(10, int(round(base_gold * (0.35 if chk.tier == "crit_success" else 0.25))))
                db.apply_hp_mp_delta(eff_uid, gold_delta=adv_gold)
                econ["advance_taken"] = True
                econ["upfront_advance_gold"] = adv_gold
                t_rules = build_turn_in_rules(
                    engine=str(dossier.get("engine") or "MYSTERY_CASE"),
                    has_physical_macguffin=bool((dossier.get("tangible_item") or {}).get("has_item")),
                    requires_prisoner_handoff=bool((dossier.get("turn_in_rules") or {}).get("requires_prisoner_handoff")),
                    twist_spec=dossier.get("twist_spec"),
                    advance_haggled=True,
                )
                dossier = db.upsert_quest_dossier(
                    session_id,
                    quest_id,
                    contract_economy=econ,
                    turn_in_rules=t_rules,
                    engaged_flag=1,
                ) or dossier
                advance_result = {
                    "succeeded": True,
                    "advance_gold": adv_gold,
                    "tier": chk.tier,
                    "roll": chk.roll,
                    "chance": chk.chance,
                }
            else:
                advance_result = {
                    "succeeded": False,
                    "advance_gold": 0,
                    "tier": chk.tier,
                    "roll": chk.roll,
                    "chance": chk.chance,
                }

    return {
        "success": True,
        "quest_id": quest_id,
        "status": "Active",
        "dossier": dossier,
        "advance_result": advance_result,
        "message": f"Accepted contract: {quest.get('title', 'Bounty')}!",
    }


async def accept_bounty_contract_async(
    session_id: int,
    quest_id: str,
    user_id: Optional[int] = None,
    haggle_advance: bool = False,
    enrich_llm: bool = False,
) -> Dict[str, Any]:
    """Async lock-safe Stage-2 bounty compiler for REST/WebSocket/Discord adapters."""
    from mechanics.system.concurrency import distributed_adventure_lock

    eff_uid = user_id if (user_id and user_id > 0) else None
    async with distributed_adventure_lock(eff_uid, session_id):
        res = await adb(
            accept_bounty_contract,
            session_id,
            quest_id,
            user_id,
            haggle_advance,
            None,
        )
        if res.get("success"):
            dos_b = res.get("dossier") or {}
            from mechanics.narrative.chapter_plan import is_clue_based_quest, schedule_background_chapter_plan
            if is_clue_based_quest(str(dos_b.get("family_tier") or ""), str(dos_b.get("engine") or "")):
                schedule_background_chapter_plan(session_id, quest_id)
            elif enrich_llm:
                enriched_dos = await enrich_dossier_with_utility_llm(session_id, quest_id, dos_b)
                res["dossier"] = enriched_dos
        return res


def forfeit_side_bounty(
    session_id: int,
    quest_id: str,
    party_user_ids: Optional[List[int]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Abandons/forfeits an active side bounty with Commitment Point-of-No-Return & Host Guard:
    - Co-op Host Guard: only `host_user_id` may abandon/forfeit when `mode in ('turn', 'sync')` or `len(members) > 1`.
    - Unengaged (`engaged_flag == 0`) AND `>24h` (`>1440` mins) remaining -> `-5` client affinity, `status='Abandoned'`, zero `WorldScar`.
    - Engaged (`engaged_flag == 1`) OR `<=24h` remaining -> `status='Failed'` + `apply_quest_failure_consequences` + `WorldScar`.
    """
    q = db.get_quest_by_id(session_id, quest_id)
    if not q or q.get("is_story_quest"):
        return {"success": False, "status_code": 400, "reason": "Cannot forfeit story quest"}

    q_notes = str(q.get("quest_notes") or "")
    if str(quest_id).upper().startswith("MAND-") or "mandatory_daily:1" in q_notes:
        return {"success": False, "status_code": 400, "reason": "Mandatory Daily Dispatches cannot be abandoned."}

    sess = db.get_session(session_id) or {}
    members = db.get_session_members(session_id) or []
    is_coop = str(sess.get("mode") or "solo").lower() in ("turn", "sync") or len(members) > 1
    actor_uid = user_id if user_id is not None else (party_user_ids[0] if party_user_ids and len(party_user_ids) == 1 else None)
    host_uid = sess.get("host_user_id")
    if is_coop and actor_uid is not None and host_uid is not None and int(actor_uid) != int(host_uid):
        return {
            "success": False,
            "status_code": 403,
            "reason": "Only the session host can abandon or forfeit active contracts in co-op.",
        }

    dossier = db.get_quest_dossier(session_id, quest_id)
    engaged = bool(dossier and int(dossier.get("engaged_flag") or 0) == 1)

    d_day = q.get("deadline_day")
    d_min = int(q.get("deadline_minute") or 0)
    if d_day is not None:
        cur_day, cur_min, _ = db.get_session_time(session_id)
        mins_remaining = (int(d_day) - int(cur_day)) * 1440 + (d_min - int(cur_min))
    else:
        mins_remaining = 999999

    eff_turn = db.infer_session_turn(sess)
    prev_status = str(q.get("status") or "Active")

    if not engaged and mins_remaining > 1440:
        now = time.time()
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET status='Abandoned', updated_at=? WHERE session_id=? AND quest_id=?",
                (now, session_id, quest_id),
            )
            conn.execute(
                "UPDATE quest_waypoints SET status='abandoned', updated_at=? WHERE session_id=? AND quest_id=?",
                (now, session_id, quest_id),
            )
        if dossier:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Abandoned")
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "abandoned")
            db.upsert_quest_dossier(session_id, quest_id, outcome_tier="abandoned")

        client_npc = q.get("client_npc") or ""
        if client_npc:
            try:
                db.update_relationship_score(session_id, client_npc, delta_score=-5)
            except Exception:
                pass
        return {
            "success": True,
            "status": "Abandoned",
            "forfeit_mode": "clean_abandon",
            "world_scar_spawned": False,
        }

    # Commitment Point-of-No-Return crossed -> Contract Failure + WorldScar!
    from game_engine.quests import apply_quest_failure_consequences

    uids = list(party_user_ids or ([int(actor_uid)] if actor_uid is not None else members))
    fail_res = apply_quest_failure_consequences(
        session_id,
        q,
        uids,
        reason="forfeited_after_commitment",
        session=sess,
    )
    engine = str((dossier or {}).get("engine") or q.get("engine") or "MYSTERY_CASE")
    venue = str(
        ((dossier or {}).get("climax_spec") or {}).get("location")
        or q.get("client_location")
        or sess.get("current_location")
        or "District"
    )
    scar_spec = (
        (((dossier or {}).get("outcomes_matrix") or {}).get("failure") or {}).get("world_scar")
        or render_world_scar_spec(engine=engine, venue_name=venue)
    )
    scar_ev = spawn_quest_world_scar(
        session_id=session_id,
        source_quest_id=quest_id,
        scar_spec=scar_spec,
        location_name=venue,
        turn_number=eff_turn,
    )
    if dossier:
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Failed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "failure")
        db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")

    return {
        "success": True,
        "status": "Failed",
        "forfeit_mode": "engaged_failure",
        "world_scar_spawned": True,
        "world_scar": scar_ev,
        "failure_details": fail_res,
    }


def build_universal_epilogue_choices(scen_key: str, ending_id: str = "") -> List[Dict[str, Any]]:
    if ending_id == "fallen_world":
        endless_label = "♾️ Continue in Fallen-World Resistance Mode"
    elif scenario_data.is_anomalous_incursions_scenario(scen_key):
        endless_label = "♾️ Continue in Endless Containment Mode"
    else:
        endless_label = "♾️ Continue in Endless Sandbox Mode"
    return [
        {
            "label": "🏁 Conclude Campaign (Archive Chronicle)",
            "stat": "FREE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "epilogue_conclude_campaign",
        },
        {
            "label": endless_label,
            "stat": "FREE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "epilogue_endless_mode",
        },
    ]


def evaluate_skipped_threatened_optionals(
    session_id: int,
    quest_id: str,
    dossier: Optional[Dict[str, Any]] = None,
    turn_number: Optional[int] = None,
    lang: str = "en",
) -> List[Dict[str, Any]]:
    """
    Evaluates skipped Optionals upon quest/chapter resolution:
    - Standard `aid` / `bypass` / `alternative` Optionals carry ZERO world/ally fallout when skipped.
    - Selectively flagged `role == 'threatened'` Optionals spawn targeted fallout (`WorldScar` + collateral toll).
    - Enforces **Fair Inner-Circle Jeopardy**: party/romances/family NEVER suffer off-screen permadeath;
      permanent loss triggers ONLY when an explicit on-screen rescue beat (`on_screen_triage_presented` or `failed`)
      was abandoned or failed on-screen.
    """
    dos = dossier or (db.get_quest_dossier(session_id, quest_id) if session_id and quest_id else None)
    if not dos:
        return []

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    prev_leads = [dict(l) for l in (dos.get("leads_graph") or [])]
    leads = [dict(l) for l in prev_leads]
    is_story = str(dos.get("family_tier") or "") == "story"
    ch_num = int((dos.get("climax_spec") or {}).get("chapter") or dos.get("chapter") or db.get_session_chapter(session_id) or 1)
    fallout_events: List[Dict[str, Any]] = []
    mutated = False

    for idx, ld in enumerate(leads):
        role = str(ld.get("role") or "").strip().lower()
        st = str(ld.get("status") or "active").strip().lower()
        if role != "threatened":
            continue
        if st in ("completed", "skipped_fallout"):
            continue

        mutated = True
        was_failed_on_screen = st == "failed" or bool(ld.get("on_screen_triage_presented"))
        ld["status"] = "failed" if st == "failed" else "skipped_fallout"
        leads[idx] = ld

        venue = str(ld.get("target_location") or (dos.get("climax_spec") or {}).get("location") or sess.get("current_location") or "District")
        ally_name = str(ld.get("target_npc") or ld.get("implicated_ally_npc") or "").strip()
        is_inner_circle = bool(
            ld.get("fair_jeopardy_on_screen_only")
            or ld.get("is_inner_circle_rescue")
            or ld.get("implicated_ally_npc")
        )

        scar_tier = "peak" if (is_story and ch_num in (3, 6, 8, 9, 10)) else ("buildup" if is_story else "bounty")
        scar_spec = render_world_scar_spec(
            engine=str(dos.get("engine") or "CRISIS_DEFENSE"),
            venue_name=venue,
            lang=lang,
        )
        scar_spec["scar_tier"] = scar_tier
        scar_spec["chapter_number"] = ch_num
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=f"{quest_id}_OPT{idx + 1}",
            scar_spec=scar_spec,
            location_name=venue,
            turn_number=eff_turn,
            scar_tier=scar_tier,
        )

        inner_circle_lost = False
        if ally_name:
            if is_inner_circle:
                if was_failed_on_screen:
                    inner_circle_lost = True
                    update_campaign_ending_axes(
                        session_id,
                        collateral_delta=1,
                        inner_circle_loss=ally_name,
                        turn_number=eff_turn,
                    )
                else:
                    # Fair Jeopardy Invariant: ZERO off-screen permadeath for inner-circle allies!
                    try:
                        db.update_relationship_score(session_id, ally_name, delta_score=-10)
                    except Exception:
                        pass
                    if is_story:
                        update_campaign_ending_axes(session_id, collateral_delta=1, turn_number=eff_turn)
            else:
                try:
                    db.update_relationship_score(session_id, ally_name, delta_score=-15)
                except Exception:
                    pass
                if is_story:
                    update_campaign_ending_axes(session_id, collateral_delta=1, turn_number=eff_turn)
        elif is_story:
            update_campaign_ending_axes(session_id, collateral_delta=1, turn_number=eff_turn)

        fallout_events.append(
            {
                "optional_id": ld.get("optional_id") or ld.get("lead_id"),
                "target_npc": ally_name,
                "target_location": venue,
                "inner_circle_lost": inner_circle_lost,
                "world_scar": scar_ev,
            }
        )

    if mutated:
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "leads_graph", prev_leads, leads)
        saved = db.upsert_quest_dossier(session_id, quest_id, leads_graph=leads)
        if saved:
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved)

    return fallout_events


def hot_swap_dossier_entities(
    session_id: int,
    dossier: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Live Entity Continuity & Hot-Swap Patching (Option C):
    Audits cast_bindings of a prewarmed dossier against live SQLite contacts/world state.
    If a bound NPC (target, client, informant) died or became unavailable during Chapter N,
    hot-swaps them with their designated role successor or dead-drop cipher fallback
    without invalidating prewarmed stage structures or narrative flavor.
    """
    if not dossier or not isinstance(dossier, dict):
        return dossier

    qid = str(dossier.get("quest_id") or "")
    cast = dict(dossier.get("cast_bindings") or {})
    climax = dict(dossier.get("climax_spec") or {})
    leads = [dict(l) for l in (dossier.get("leads_graph") or [])]
    mutated = False

    contacts = db.get_contacts(session_id) if session_id else []
    contacts_by_name = {str(c.get("name") or "").lower(): c for c in contacts if isinstance(c, dict)}
    contacts_by_id = {int(c.get("id")): c for c in contacts if isinstance(c, dict) and c.get("id") is not None}

    spine = db.get_campaign_spine(session_id) if session_id else {}
    lts = [lt for lt in (spine.get("lieutenants_roster") or []) if isinstance(lt, dict)]
    dead_lts = {
        str(lt.get("name") or "").strip().lower()
        for lt in lts
        if str(lt.get("status") or "").lower() in ("dead", "slain", "recruited", "executed")
    }

    def _is_npc_dead_or_hostile(cid: Any, name: str) -> bool:
        n_low = str(name or "").strip().lower()
        if n_low in dead_lts:
            return True
        c = None
        if cid is not None:
            try:
                c = contacts_by_id.get(int(cid))
            except (ValueError, TypeError):
                pass
        if not c and n_low:
            c = contacts_by_name.get(n_low)
        if not c:
            return False
        b_info = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
        if str(c.get("status") or "").lower() == "dead" or str(b_info.get("status") or "").lower() == "dead":
            return True
        if c.get("is_alive") is False or b_info.get("is_alive") is False:
            return True
        if c.get("health") is not None and int(c.get("health", 1) or 0) <= 0:
            return True
        return False

    # 1. Target hot-swap
    tgt = dict(cast.get("target") or {})
    tgt_name = str(tgt.get("name") or climax.get("target_npc") or "")
    tgt_cid = tgt.get("contact_id")
    if tgt_name and _is_npc_dead_or_hostile(tgt_cid, tgt_name):
        spine = db.get_campaign_spine(session_id) if session_id else {}
        lts = [lt for lt in (spine.get("lieutenants_roster") or []) if isinstance(lt, dict)]
        alive_lts = [
            str(lt.get("name"))
            for lt in lts
            if lt.get("name") and not _is_npc_dead_or_hostile(None, str(lt.get("name")))
        ]
        if alive_lts:
            succ_name = alive_lts[0]
        else:
            scen = str((db.get_session(session_id) or {}).get("scenario") or "fantasy")
            succ_name = namegen.generate_npc_name(scenario=scen)

        tgt["name"] = succ_name
        tgt["status"] = "alive"
        tgt["successor_of"] = tgt_name
        cast["target"] = tgt
        climax["target_npc"] = succ_name
        if isinstance(climax.get("boss_sheet"), dict):
            climax["boss_sheet"]["name"] = succ_name
        for ms in (climax.get("main_stages") or []):
            if isinstance(ms, dict):
                if ms.get("target_npc") == tgt_name:
                    ms["target_npc"] = succ_name
                if tgt_name in str(ms.get("label") or ""):
                    ms["label"] = str(ms["label"]).replace(tgt_name, succ_name)
        mutated = True

    # 2. Informant hot-swap
    inf = dict(cast.get("informant") or {})
    inf_name = str(inf.get("name") or "")
    inf_cid = inf.get("contact_id")
    if inf_name and _is_npc_dead_or_hostile(inf_cid, inf_name):
        inf["status"] = "dead"
        inf["fallback_on_death"] = "lootable_cipher_or_room_search"
        cast["informant"] = inf
        for l in leads:
            if l.get("informant_npc") == inf_name or inf_name in str(l.get("flavor_note") or ""):
                l["informant_npc"] = ""
                l["fallback_cipher"] = True
                l["flavor_note"] = f"Recover {inf_name}'s hidden cipher drop or encrypted field journal."
        mutated = True

    # 3. Client hot-swap
    cli = dict(cast.get("client") or {})
    cli_name = str(cli.get("name") or "")
    cli_cid = cli.get("contact_id")
    if cli_name and _is_npc_dead_or_hostile(cli_cid, cli_name):
        cli["status"] = "dead"
        cli["fallback_on_death"] = "contract_void_or_successor"
        scen = str((db.get_session(session_id) or {}).get("scenario") or "fantasy")
        succ_cli = namegen.generate_npc_name(scenario=scen)
        cli["name"] = succ_cli
        cli["successor_of"] = cli_name
        cast["client"] = cli
        mutated = True

    if mutated and qid:
        dossier["cast_bindings"] = cast
        dossier["climax_spec"] = climax
        dossier["leads_graph"] = leads
        db.upsert_quest_dossier(
            session_id,
            qid,
            cast_bindings=cast,
            climax_spec=climax,
            leads_graph=leads,
        )

    return dossier


_IN_FLIGHT_PREWARMS: set[tuple[int, int]] = set()


async def prewarm_chapter_ahead(
    session_id: int,
    current_chapter: int,
    target_chapter: int,
) -> Optional[str]:
    """
    Asynchronous JIT Chapter N+1 Prewarming Worker (Option C):
    Compiles the target chapter's Storylet + QuestDossier with status_stage='prewarmed'
    during Chapter N, and asynchronously enriches it via the utility LLM.
    Guarantees 0ms chapter transition without blocking the player's current turn.
    """
    from mechanics.system.concurrency import acquire_background_session_lock

    pw_key = (int(session_id), int(target_chapter))
    if not session_id or pw_key in _IN_FLIGHT_PREWARMS:
        return None
    _IN_FLIGHT_PREWARMS.add(pw_key)
    try:
        existing = await adb(db.get_prewarmed_quest_dossier, session_id, target_chapter)
        if existing and existing.get("quest_id"):
            return str(existing["quest_id"])

        sess = await adb(db.get_session, session_id) or {"id": session_id}
        scen_key = str(sess.get("scenario") or "fantasy")
        lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
        eff_turn = db.infer_session_turn(sess)

        spine = await adb(compile_or_get_campaign_spine, session_id, scen_key=scen_key, lang=lang)
        from mechanics.narrative.dossier_compiler import select_deconflicted_climax_location
        cand_venue, _ = await adb(
            select_deconflicted_climax_location,
            session_id,
            "",
            family_tier="story",
            objective_hint=f"Chapter {target_chapter}",
            scen_key=scen_key,
        )
        storylet = await adb(select_chapter_storylet, session_id, target_chapter, spine=spine, lang=lang, venue_name=cand_venue)
        ch_bp = (spine.get("chapters_blueprint") or {}).get(str(target_chapter)) or {}

        pre_sq_id = f"SQ-PRE-{uuid.uuid4().hex[:8].upper()}"
        pre_title = sanitize_dossier_prose(str(storylet.get("title") or ch_bp.get("title_template") or f"Chapter #{target_chapter}"))
        pre_engine = str(storylet.get("engine") or ch_bp.get("engine") or "MYSTERY_CASE")
        pre_obj = sanitize_dossier_prose(
            str(storylet.get("objective") or ch_bp.get("pacing_directive") or "A new chapter unfolds...")
        )

        feat_lt = str(storylet.get("featured_lieutenant") or ch_bp.get("featured_lieutenant") or "")
        mm_name = str((spine.get("mastermind_profile") or {}).get("name") or "")
        target_for_ch = mm_name if target_chapter == 10 else feat_lt

        # Serialize initial prewarm write against active turns / parallel prewarms
        async with acquire_background_session_lock(session_id) as locked:
            if not locked:
                return None
            existing_now = await adb(db.get_prewarmed_quest_dossier, session_id, target_chapter)
            if existing_now and existing_now.get("quest_id"):
                return str(existing_now["quest_id"])
            if int(await adb(db.get_session_chapter, session_id) or 1) >= int(target_chapter):
                return None
            pre_dossier = await adb(
                compile_quest_dossier,
                session_id=session_id,
                quest_id=pre_sq_id,
                tag_or_archetype=pre_engine,
                title=pre_title,
                objective=pre_obj,
                family_tier="story",
                chapter=target_chapter,
                turn_number=eff_turn,
                target_npc=target_for_ch,
                reward_gold=60 + (target_chapter * 10),
                scen_key=scen_key,
                lang=lang,
                status_stage="prewarmed",
            )

        # Write strict validated AI ChapterPlan with 30s timeout & 1 repair retry (unlocked during LLM call)
        try:
            from mechanics.narrative.chapter_plan import (
                apply_chapter_plan_to_dossier,
                generate_chapter_plan_with_resilience,
            )
            plan = await generate_chapter_plan_with_resilience(session_id, pre_sq_id, pre_dossier, timeout_seconds=30.0)
            if plan:
                async with acquire_background_session_lock(session_id) as locked_apply:
                    if locked_apply:
                        cur = await adb(db.get_quest_dossier, session_id, pre_sq_id)
                        if cur and str(cur.get("status_stage") or "") == "prewarmed":
                            await adb(apply_chapter_plan_to_dossier, session_id, pre_sq_id, plan)
        except Exception as _plan_err:
            logger.debug("Prewarmed chapter AI ChapterPlan skipped (non-fatal): %s", _plan_err)

        return pre_sq_id
    except Exception as exc:
        logger.warning("prewarm_chapter_ahead failed (non-fatal): %s", exc)
        return None
    finally:
        _IN_FLIGHT_PREWARMS.discard(pw_key)


def resolve_chapter_transition(
    session_id: int,
    quest: Dict[str, Any],
    status: str = "Completed",
    reason: str = "",
    party_user_ids: Optional[List[int]] = None,
    outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Universal 11-Chapter Triple-Peak Campaign Spine Progression & Finale State Machine:
    - Ch. 1–9 (`Completed` OR fail-forward `Failed`): evaluates skipped `threatened` Optionals
      (zero penalty on standard `aid`/`bypass`/`alternative` Optionals), stacks Two-Tier `WorldScar`
      on failure, advances to `cur_ch + 1`, and deterministically compiles the next Storylet + `QuestDossier`
      with `deadline_day = None`.
    - Ch. 10 Grand Climax:
      * Combat OR non-combat defeat (`status == 'Failed'`) -> **Playable Fallen-World `Ch. 11`**
        (`climax_status = 'fallen_world'`, `epilogue_status = 'ch11_fallen_active'`), NEVER abrupt Hard Game Over!
      * Victory -> advances to **Ending-Specific Playable Epilogue `Ch. 11`** (`climax_status = 'victory'`).
    - Ch. 11 Completion: compiles 4-Slide **Chronicle Tapestry** (`World`, `Factions`, `Bonds`, `Earned Title`)
      and unlocks `[Archive Chronicle]` vs. **Stateful Endless Mode** (including Fallen-World Resistance).
    """
    sess = db.get_session(session_id) or {"id": session_id}
    scen_key = str(sess.get("scenario") or "fantasy")
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    eff_turn = db.infer_session_turn(sess)
    cur_ch = int(db.get_session_chapter(session_id) or 1)
    max_ch = get_max_campaign_chapters(scen_key)

    spine = compile_or_get_campaign_spine(session_id, scen_key=scen_key, lang=lang)
    mm_name = str((spine.get("mastermind_profile") or {}).get("name") or "")
    qid = str(quest.get("quest_id") or "")
    dossier = db.get_quest_dossier(session_id, qid) if qid else None
    quest_ch = int((dossier or {}).get("chapter") or quest.get("chapter") or 0)

    # Idempotency guard: prevent duplicate chapter transitions in the same turn or for an already-advanced chapter
    if qid and sess.get("_last_transition_quest_id") == qid and int(sess.get("_last_transition_turn") or -1) == eff_turn:
        return {"chapter": cur_ch, "already_transitioned": True}
    if quest_ch > 0 and cur_ch > quest_ch:
        return {"chapter": cur_ch, "already_transitioned": True}

    # Evaluate selectively threatened Optionals (standard Optionals have zero skip penalty)
    threatened_fallout: List[Dict[str, Any]] = []
    if qid and dossier and cur_ch <= 10:
        threatened_fallout = evaluate_skipped_threatened_optionals(
            session_id=session_id,
            quest_id=qid,
            dossier=dossier,
            turn_number=eff_turn,
            lang=lang,
        )

    # Update deterministic campaign goals floor
    goals = db.get_session_campaign_goals(session_id)
    if goals and status == "Completed":
        new_floor = min(100, int((cur_ch / max(1, max_ch)) * 100))
        for g in goals:
            g["progress_pct"] = max(int(g.get("progress_pct", 0) or 0), new_floor)
            if cur_ch >= max_ch or g["progress_pct"] >= 100:
                g["progress_pct"] = 100
                g["status"] = "Completed"
        db.update_session_campaign_goals(session_id, goals)

    climax_spec = (dossier or {}).get("climax_spec") or {}

    # 1. Chapter 11 Completion -> 4-Slide Chronicle Tapestry + Post-Epilogue Choice (Archive vs. Endless Mode)
    if cur_ch >= 11 and not sess.get("endless_mode_unlocked"):
        if qid:
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE quests SET status = ?, updated_at = ? WHERE session_id = ? AND quest_id = ? AND status = 'Active'",
                    ("Failed" if status == "Failed" else "Completed", time.time(), session_id, qid),
                )
        tapestry = compile_chronicle_tapestry(session_id=session_id, lang=lang, turn_number=eff_turn)
        ending_id = str(tapestry.get("ending_id") or "")
        epilogue_choices = build_universal_epilogue_choices(scen_key, ending_id=ending_id)
        fresh_spine = db.get_campaign_spine(session_id) or spine
        spine_events = list(fresh_spine.get("state_events") or [])
        spine_events.append(
            {
                "turn": eff_turn,
                "kind": "epilogue_status",
                "prev": fresh_spine.get("epilogue_status", "pending"),
                "next": "awaiting_choice",
            }
        )
        db.upsert_campaign_spine(
            session_id,
            scen_key,
            epilogue_status="awaiting_choice",
            chronicle_tapestry=tapestry,
            state_events=spine_events,
        )
        db.update_session(
            session_id,
            extra={
                "epilogue_ready": True,
                "epilogue_choices": epilogue_choices,
                "chronicle_tapestry": tapestry,
                "_last_transition_quest_id": qid,
                "_last_transition_turn": eff_turn,
            },
        )
        if isinstance(outcome, dict):
            outcome["epilogue_ready"] = True
            outcome["epilogue_choices"] = epilogue_choices
            outcome["chronicle_tapestry"] = tapestry
        return {
            "chapter": cur_ch,
            "epilogue_ready": True,
            "epilogue_choices": epilogue_choices,
            "chronicle_tapestry": tapestry,
            "directive": (
                f"[MANDATORY CAMPAIGN EPILOGUE RESOLUTION — {tapestry.get('ending_title', 'Chronicle Complete')}]: "
                "Playable Epilogue Chapter 11 completed! Present the 4-Slide Chronicle Tapestry and the choice "
                "between [Archive Chronicle] and [Endless Mode]."
            ),
        }

    # 2. Chapters 1-10 Advance (Completed OR Fail-Forward, including Playable Fallen-World Ch. 11 on Ch. 10 Defeat!)
    world_scar_ev: Optional[Dict[str, Any]] = None
    is_ch10_fallen = bool(cur_ch == 10 and status == "Failed")
    threat_clk = dict(climax_spec.get("threat_clock") or {})
    clock_scar_pending = bool(threat_clk.get("world_scar_pending"))
    if status == "Failed" or clock_scar_pending:
        eng = str((dossier or {}).get("engine") or quest.get("engine") or "CRISIS_DEFENSE")
        venue = str(climax_spec.get("location") or sess.get("current_location") or "Central District")
        scar_tier = "peak" if cur_ch in (3, 6, 8, 9, 10) else "buildup"
        scar_spec = dict(
            (((dossier or {}).get("outcomes_matrix") or {}).get("failure") or {}).get("world_scar")
            or render_world_scar_spec(engine=eng, venue_name=venue, lang=lang)
        )
        scar_spec["scar_tier"] = scar_tier
        scar_spec["chapter_number"] = cur_ch
        if clock_scar_pending and status != "Failed":
            scar_spec["threat_clock_overrun"] = True
        if status == "Failed" and cur_ch in (8, 9, 10):
            scar_spec["lockdown"] = True
        world_scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=qid or f"CH{cur_ch}",
            scar_spec=scar_spec,
            location_name=venue,
            turn_number=eff_turn,
            scar_tier=scar_tier,
        )
    if status == "Failed":
        update_campaign_ending_axes(
            session_id=session_id,
            collateral_delta=2 if cur_ch in (3, 6, 8, 9, 10) else 1,
            ch10_defeated=is_ch10_fallen or None,
            turn_number=eff_turn,
        )

    if cur_ch == 10:
        fresh_spine = db.get_campaign_spine(session_id) or spine
        spine_events = list(fresh_spine.get("state_events") or [])
        new_climax_st = "fallen_world" if is_ch10_fallen else "victory"
        new_epilogue_st = "ch11_fallen_active" if is_ch10_fallen else "ch11_active"
        spine_events.append(
            {"turn": eff_turn, "kind": "climax_status", "prev": fresh_spine.get("climax_status", "pending"), "next": new_climax_st}
        )
        spine_events.append(
            {"turn": eff_turn, "kind": "epilogue_status", "prev": fresh_spine.get("epilogue_status", "pending"), "next": new_epilogue_st}
        )
        spine = db.upsert_campaign_spine(
            session_id,
            scen_key,
            climax_status=new_climax_st,
            epilogue_status=new_epilogue_st,
            state_events=spine_events,
        ) or fresh_spine
        if is_ch10_fallen:
            db.update_session(
                session_id,
                extra={
                    "campaign_game_over": False,
                    "fallen_world": True,
                    "epilogue_ready": False,
                },
            )
            if isinstance(outcome, dict):
                outcome["campaign_game_over"] = False
                outcome["fallen_world"] = True

    # Ensure the resolved story quest row is no longer 'Active' before inserting the next chapter's quest
    if qid:
        final_q_status = "Failed" if status == "Failed" else "Completed"
        with db.get_conn() as conn:
            cur_row = conn.execute(
                "SELECT status FROM quests WHERE session_id = ? AND quest_id = ?",
                (session_id, qid),
            ).fetchone()
            if cur_row and str(cur_row["status"]) == "Active":
                conn.execute(
                    "UPDATE quests SET status = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                    (final_q_status, time.time(), session_id, qid),
                )
        db.append_dossier_state_event(session_id, qid, eff_turn, "quest_status", "Active", final_q_status)

    if cur_ch >= 11 and sess.get("endless_mode_unlocked"):
        db.set_session_chapter(session_id, 11)
        return {
            "chapter": 11,
            "endless_mode": True,
            "message": "Campaign chronicle concluded! Endless Mode active.",
        }

    next_ch = cur_ch + 1
    db.set_session_chapter(session_id, next_ch)
    db.update_session(
        session_id,
        extra={"_last_transition_quest_id": qid, "_last_transition_turn": eff_turn},
    )

    # Option C Fast-Path: Consume prewarmed dossier if available
    prewarmed = db.get_prewarmed_quest_dossier(session_id, next_ch)
    if prewarmed and prewarmed.get("quest_id"):
        pre_qid = str(prewarmed["quest_id"])
        patched_dossier = hot_swap_dossier_entities(session_id, prewarmed)
        db.promote_prewarmed_dossier(session_id, pre_qid)

        stub = dict(patched_dossier.get("pitch_stub") or {})
        next_sq_id = pre_qid
        next_title = sanitize_dossier_prose(str(stub.get("title") or f"Chapter #{next_ch}"))
        next_engine = str(patched_dossier.get("engine") or "MYSTERY_CASE")
        next_obj = sanitize_dossier_prose(str(stub.get("public_pitch") or "A new chapter unfolds..."))

        next_quest = db.upsert_quest(
            session_id=session_id,
            quest_id=next_sq_id,
            quest_type="Story Quest",
            title=next_title,
            objective=next_obj,
            progress="0/1 Main Objective",
            current_clues="",
            status="Active",
            reward_xp=250 + (next_ch * 30),
            reward_gold=60 + (next_ch * 10),
            is_story_quest=1,
            clues_required=1,
            sub_objectives=[],
            deadline_day=None,
            deadline_minute=None,
            engine=next_engine,
            dossier_stage="compiled",
        )
        db.sync_quest_projection_from_dossier(session_id, next_sq_id, dossier=patched_dossier)
        next_dossier = patched_dossier
        refreshed_next_quest = db.get_quest_by_id(session_id, next_sq_id) or next_quest
    else:
        spine_for_next = db.get_campaign_spine(session_id) or spine
        from mechanics.narrative.dossier_compiler import select_deconflicted_climax_location
        cand_venue, _ = select_deconflicted_climax_location(
            session_id, "", family_tier="story", objective_hint=f"Chapter {next_ch}", scen_key=scen_key
        )
        storylet = select_chapter_storylet(session_id, next_ch, spine=spine_for_next, lang=lang, venue_name=cand_venue)
        ch_bp = (spine_for_next.get("chapters_blueprint") or {}).get(str(next_ch)) or {}

        next_sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"
        next_title = sanitize_dossier_prose(str(storylet.get("title") or ch_bp.get("title_template") or f"Chapter #{next_ch}"))
        next_engine = str(storylet.get("engine") or ch_bp.get("engine") or "MYSTERY_CASE")
        next_obj = sanitize_dossier_prose(
            str(storylet.get("objective") or ch_bp.get("pacing_directive") or "A new chapter unfolds...")
        )

        next_quest = db.upsert_quest(
            session_id=session_id,
            quest_id=next_sq_id,
            quest_type="Story Quest",
            title=next_title,
            objective=next_obj,
            progress="0/1 Main Objective",
            current_clues="",
            status="Active",
            reward_xp=250 + (next_ch * 30),
            reward_gold=60 + (next_ch * 10),
            is_story_quest=1,
            clues_required=1,
            sub_objectives=[],
            deadline_day=None,
            deadline_minute=None,
            engine=next_engine,
            dossier_stage="compiled",
        )

        feat_lt = str(storylet.get("featured_lieutenant") or ch_bp.get("featured_lieutenant") or "")
        mm_name = str((spine_for_next.get("mastermind_profile") or {}).get("name") or "")
        target_for_ch = mm_name if next_ch == 10 else feat_lt

        next_dossier = compile_quest_dossier(
            session_id=session_id,
            quest_id=next_sq_id,
            tag_or_archetype=next_engine,
            title=next_title,
            objective=next_obj,
            family_tier="story",
            chapter=next_ch,
            turn_number=eff_turn,
            target_npc=target_for_ch,
            reward_gold=60 + (next_ch * 10),
            scen_key=scen_key,
            lang=lang,
        )
        refreshed_next_quest = db.get_quest_by_id(session_id, next_sq_id) or next_quest

    res_payload: Dict[str, Any] = {
        "chapter": next_ch,
        "previous_chapter": cur_ch,
        "next_quest_id": next_sq_id,
        "next_quest": refreshed_next_quest,
        "next_dossier": next_dossier,
        "fail_forward": bool(status == "Failed"),
        "hard_game_over": False,
        "fallen_world": is_ch10_fallen,
        "threatened_fallout": threatened_fallout,
        "world_scar": world_scar_ev,
    }
    if is_ch10_fallen:
        mm_display = mm_name or "the Mastermind"
        res_payload["directive"] = (
            f"[MANDATORY PLAYABLE FALLEN-WORLD EPILOGUE (CHAPTER 11)]: {mm_display} prevailed in Chapter 10! "
            "Instead of an abrupt Game Over, advance into Chapter 11 in a Fallen World where the party survives "
            "to salvage their inner circle and seed an underground resistance."
        )
    if outcome is not None and isinstance(outcome, dict):
        outcome["chapter_transition"] = res_payload
    return res_payload


def resolve_epilogue_choice(
    session_id: int,
    intent: str,
    party_user_ids: Any = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Handles post-Chapter-11 `[Archive Chronicle]` vs `[Endless Sandbox Mode]` player selection."""
    sess = db.get_session(session_id) or {"id": session_id}
    scen_key = str(sess.get("scenario") or "fantasy")
    spine = compile_or_get_campaign_spine(session_id, scen_key=scen_key)
    events = list(spine.get("state_events") or [])
    norm_intent = str(intent or "").strip().lower()
    t_num = (
        int(party_user_ids)
        if isinstance(party_user_ids, int)
        else int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    )

    if norm_intent in ("epilogue_conclude_campaign", "archive", "conclude", "archive_chronicle"):
        events.append({"turn": t_num, "kind": "epilogue_status", "prev": spine.get("epilogue_status", "awaiting_choice"), "next": "archived"})
        db.upsert_campaign_spine(session_id, scen_key, epilogue_status="archived", state_events=events)
        db.update_session(
            session_id,
            extra={
                "epilogue_ready": False,
                "chronicle_archived": True,
                "campaign_archived": True,
                "campaign_concluded": True,
            },
        )
        return {
            "mode": "archived",
            "chronicle_archived": True,
            "campaign_archived": True,
            "directive": "[CAMPAIGN CHRONICLE ARCHIVED]: Deliver a resonant closing reflection sealing this legend in the Hall of Chronicles.",
        }

    events.append({"turn": t_num, "kind": "epilogue_status", "prev": spine.get("epilogue_status", "awaiting_choice"), "next": "endless_sandbox"})
    db.upsert_campaign_spine(session_id, scen_key, epilogue_status="endless_sandbox", state_events=events)
    db.update_session(
        session_id,
        extra={
            "epilogue_ready": False,
            "endless_mode_unlocked": True,
        },
    )
    spawned = spawn_endless_mode_contracts(session_id=session_id, turn_number=t_num)
    return {
        "mode": "endless_sandbox",
        "endless_mode_unlocked": True,
        "spawned_contracts": spawned,
        "directive": (
            "[ENDLESS SANDBOX MODE UNLOCKED]: The main campaign arc has concluded, opening open-world Nemesis Hunts, "
            "Remediation Bounties, Companion Loyalty milestones, and Faction Mini-Arcs!"
        ),
    }


def complete_remediation_bounty_if_linked(
    session_id: int,
    quest_id: str,
    turn_number: Optional[int] = None,
) -> List[str]:
    """Lifts any persistent `WorldScar` linked to a completed Remediation Bounty."""
    return resolve_world_scar_via_bounty(session_id=session_id, quest_id=quest_id, turn_number=turn_number)
