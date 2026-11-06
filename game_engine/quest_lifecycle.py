from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import db
from db import adb
import llm_client
import scenario_data
import skill_check
from mechanics.narrative.blueprints import get_max_campaign_chapters
from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility
from mechanics.narrative.campaign_spine import compile_or_get_campaign_spine
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
_STAT_LEAK_RE = re.compile(r"\b(?:DC\s*\d+|\d+\s*(?:HP|MP)|(?:\+|\-)\d+%\s*chance)\b", re.IGNORECASE)


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
        existing_dos = db.get_quest_dossier(session_id, sq_id)
        if not existing_dos or existing_dos.get("status_stage") != "compiled":
            ch1_bp = (spine.get("chapters_blueprint") or {}).get("1") or {}
            compile_quest_dossier(
                session_id=session_id,
                quest_id=sq_id,
                tag_or_archetype=str(ch1_bp.get("engine") or active_sq.get("quest_type") or "MYSTERY_CASE"),
                title=str(active_sq.get("title") or ch1_bp.get("title_template") or "Chapter #1"),
                objective=str(active_sq.get("objective") or ""),
                family_tier="story",
                chapter=int(db.get_session_chapter(session_id) or 1),
                turn_number=0,
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
) -> Optional[Dict[str, Any]]:
    """
    Materializes a predetermined clue from `dossier.clue_graph` into `session_clues`
    and records its integer `clue_id` back into `clue_graph` for deterministic pairing.
    """
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not dossier:
        return None
    clue_graph = list(dossier.get("clue_graph") or [])
    if not clue_graph or clue_index < 0 or clue_index >= len(clue_graph):
        return None

    node = dict(clue_graph[clue_index])
    if node.get("clue_id"):
        existing_c = db.get_session_clue_by_id(int(node["clue_id"]))
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
    )
    node["clue_id"] = int(clue_id)
    clue_graph[clue_index] = node
    db.upsert_quest_dossier(session_id, quest_id, clue_graph=clue_graph)
    return db.get_session_clue_by_id(int(clue_id))


def sync_waypoints_from_dossier(
    session_id: int,
    quest_id: str,
    dossier: Dict[str, Any],
    force_replace: bool = False,
) -> List[Dict[str, Any]]:
    """
    Synchronizes `quest_waypoints` for a Stage-2 compiled side contract while preserving
    custom waypoints on legacy or Story sub-objective quests.
    """
    existing_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id=None) or []
    if existing_wps and not force_replace and len(existing_wps) >= 2:
        return existing_wps

    leads = list(dossier.get("leads_graph") or [])
    climax = dict(dossier.get("climax_spec") or {})
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


async def enrich_dossier_with_utility_llm(
    session_id: int,
    quest_id: str,
    dossier: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Bounded (`timeout=4.0`, `retries=0`, `use_utility=True`) flavor enrichment pass.
    Routes NSFW / hybrid quests to `NSFW_LLM_UTILITY_MODEL` via `is_nsfw=uses_nsfw_routing`.
    Falls back instantaneously to the deterministic 5-locale `QuestDossier` on timeout/offline.
    """
    dos = dossier or db.get_quest_dossier(session_id, quest_id)
    if not dos:
        return {}

    sess = await adb(db.get_session, session_id) or {}
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    uses_nsfw = bool((dos.get("contract_economy") or {}).get("uses_nsfw_routing"))
    stub = dict(dos.get("pitch_stub") or {})
    leads = [dict(l) for l in (dos.get("leads_graph") or [])]
    twist = dict(dos.get("twist_spec") or {})

    sys_prompt = (
        "You enrich tabletop RPG quest dossiers with vivid, context-aware flavor prose. "
        "NEVER include raw HP/MP/DC numbers or internal JSON tags ([ITEM_JSON], [GEAR_JSON]). "
        f"Respond strictly in JSON matching the schema in language '{lang}'."
    )
    usr_prompt = (
        f"Engine: {dos.get('engine')}\n"
        f"Title: {stub.get('title')}\n"
        f"Pitch: {stub.get('public_pitch')}\n"
        f"Lead Count: {len(leads)}\n"
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
            p_txt = sanitize_dossier_prose(enriched.get("public_pitch") or "")
            if p_txt:
                stub["public_pitch"] = p_txt
            l_descs = list(enriched.get("lead_descriptions") or [])
            for idx, desc in enumerate(l_descs):
                if idx < len(leads) and desc:
                    clean_d = sanitize_dossier_prose(str(desc))
                    if clean_d:
                        leads[idx]["flavor_note"] = clean_d
            t_txt = sanitize_dossier_prose(enriched.get("twist_summary") or "")
            if twist.get("has_twist") and t_txt:
                twist["summary"] = t_txt
            saved = await adb(
                db.upsert_quest_dossier,
                session_id,
                quest_id,
                pitch_stub=stub,
                leads_graph=leads,
                twist_spec=twist,
            )
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
        tag_or_archetype=str(quest.get("quest_type") or quest.get("engine") or quest.get("blueprint_id") or "Investigation"),
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
    from mechanics.system.concurrency import distributed_session_lock

    async with distributed_session_lock(session_id):
        res = await adb(
            accept_bounty_contract,
            session_id,
            quest_id,
            user_id,
            haggle_advance,
            None,
        )
        if res.get("success") and enrich_llm:
            enriched_dos = await enrich_dossier_with_utility_llm(session_id, quest_id, res.get("dossier"))
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


def build_universal_epilogue_choices(scen_key: str) -> List[Dict[str, Any]]:
    endless_label = (
        "♾️ Continue in Endless Containment Mode"
        if scenario_data.is_anomalous_incursions_scenario(scen_key)
        else "♾️ Continue in Endless Sandbox Mode"
    )
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


def resolve_chapter_transition(
    session_id: int,
    quest: Dict[str, Any],
    status: str = "Completed",
    reason: str = "",
    party_user_ids: Optional[List[int]] = None,
    outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Universal 11-Chapter Campaign Spine Progression & Finale State Machine (Decision 6):
    - Ch.1-9 (`Completed` OR fail-forward `Failed`): stacks `WorldScar` on failure, advances to `cur_ch + 1`,
      and synchronously compiles Chapter `next_ch` Story Quest + `QuestDossier` (zero `asyncio.create_task` races!).
    - Ch.10 Climax:
      * Final Bossfight wipe (0 HP) or flee (`EVADE_TACTICAL_FLEE`) -> **Hard Game Over** + Fallen-World archive.
      * Victory or non-boss fail-forward -> advances to **Chapter 11 (Universal Playable Epilogue)** across ALL scenarios.
    - Ch.11 Completion: unlocks `[Archive Chronicle]` vs `[Endless Sandbox Mode]`.
    """
    sess = db.get_session(session_id) or {"id": session_id}
    scen_key = str(sess.get("scenario") or "fantasy")
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    eff_turn = db.infer_session_turn(sess)
    cur_ch = int(db.get_session_chapter(session_id) or 1)
    max_ch = get_max_campaign_chapters(scen_key)

    spine = compile_or_get_campaign_spine(session_id, scen_key=scen_key, lang=lang)
    qid = str(quest.get("quest_id") or "")
    dossier = db.get_quest_dossier(session_id, qid) if qid else None
    quest_ch = int((dossier or {}).get("chapter") or quest.get("chapter") or 0)

    # Idempotency guard: prevent duplicate chapter transitions in the same turn or for an already-advanced chapter
    if qid and sess.get("_last_transition_quest_id") == qid and int(sess.get("_last_transition_turn") or -1) == eff_turn:
        return {"chapter": cur_ch, "already_transitioned": True}
    if quest_ch > 0 and cur_ch > quest_ch:
        return {"chapter": cur_ch, "already_transitioned": True}

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

    # 1. Chapter 10 Final Bossfight Wipe/Flee -> Hard Game Over
    climax_spec = (dossier or {}).get("climax_spec") or {}
    is_ch10_boss = bool(
        cur_ch == 10
        and not scenario_data.is_non_combat_scenario(scen_key)
        and (
            climax_spec.get("is_final_chapter_boss")
            or climax_spec.get("boss_sheet") is not None
            or reason in ("boss_wipe", "boss_fled", "EVADE_TACTICAL_FLEE", "party_wipe")
        )
    )
    if cur_ch == 10 and status == "Failed" and is_ch10_boss:
        spine_events = list(spine.get("state_events") or [])
        spine_events.append({"turn": eff_turn, "kind": "climax_status", "prev": spine.get("climax_status", "pending"), "next": "hard_game_over"})
        spine_events.append({"turn": eff_turn, "kind": "epilogue_status", "prev": spine.get("epilogue_status", "pending"), "next": "fallen_world_archived"})
        db.upsert_campaign_spine(
            session_id,
            scen_key,
            climax_status="hard_game_over",
            epilogue_status="fallen_world_archived",
            state_events=spine_events,
        )
        mm_name = (spine.get("mastermind_profile") or {}).get("name", "the Mastermind")
        fallen_dir = (
            f"[MANDATORY CAMPAIGN FINALE — HARD GAME OVER & FALLEN WORLD]: The party fell or fled before {mm_name} "
            f"in Chapter 10! Narrate the tragic Fallen-World aftermath as {mm_name}'s design overtakes the realm and archive the chronicle."
        )
        db.update_session(
            session_id,
            extra={
                "campaign_game_over": True,
                "fallen_world": True,
                "chronicle_archived": True,
                "epilogue_ready": False,
            },
        )
        if isinstance(outcome, dict):
            outcome["campaign_game_over"] = True
            outcome["fallen_world"] = True
        return {
            "chapter": 10,
            "hard_game_over": True,
            "fallen_world": True,
            "directive": fallen_dir,
        }

    # 2. Chapter 11 Completion -> Post-Epilogue Choice (Archive vs. Endless Sandbox)
    if cur_ch >= 11 and not sess.get("endless_mode_unlocked"):
        epilogue_choices = build_universal_epilogue_choices(scen_key)
        spine_events = list(spine.get("state_events") or [])
        spine_events.append({"turn": eff_turn, "kind": "epilogue_status", "prev": spine.get("epilogue_status", "pending"), "next": "awaiting_choice"})
        db.upsert_campaign_spine(
            session_id,
            scen_key,
            epilogue_status="awaiting_choice",
            state_events=spine_events,
        )
        db.update_session(session_id, extra={"epilogue_ready": True, "epilogue_choices": epilogue_choices})
        if isinstance(outcome, dict):
            outcome["epilogue_ready"] = True
            outcome["epilogue_choices"] = epilogue_choices
        return {
            "chapter": cur_ch,
            "epilogue_ready": True,
            "epilogue_choices": epilogue_choices,
            "directive": (
                "[MANDATORY CAMPAIGN EPILOGUE RESOLUTION]: Playable Epilogue Chapter 11 completed! "
                "Present the choice between [Archive Chronicle] and [Endless Sandbox Mode]."
            ),
        }

    # 3. Chapters 1-10 Advance (Completed OR Fail-Forward)
    world_scar_ev: Optional[Dict[str, Any]] = None
    if status == "Failed":
        eng = str((dossier or {}).get("engine") or quest.get("engine") or "CRISIS_DEFENSE")
        venue = str(climax_spec.get("location") or sess.get("current_location") or "Central District")
        scar_spec = (
            (((dossier or {}).get("outcomes_matrix") or {}).get("failure") or {}).get("world_scar")
            or render_world_scar_spec(engine=eng, venue_name=venue, lang=lang)
        )
        world_scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=qid or f"CH{cur_ch}",
            scar_spec=scar_spec,
            location_name=venue,
            turn_number=eff_turn,
        )

    if cur_ch == 10:
        spine_events = list(spine.get("state_events") or [])
        spine_events.append({"turn": eff_turn, "kind": "climax_status", "prev": spine.get("climax_status", "pending"), "next": "victory"})
        spine_events.append({"turn": eff_turn, "kind": "epilogue_status", "prev": spine.get("epilogue_status", "pending"), "next": "ch11_active"})
        db.upsert_campaign_spine(
            session_id,
            scen_key,
            climax_status="victory",
            epilogue_status="ch11_active",
            state_events=spine_events,
        )

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

    next_ch = cur_ch + 1
    db.set_session_chapter(session_id, next_ch)
    db.update_session(
        session_id,
        extra={"_last_transition_quest_id": qid, "_last_transition_turn": eff_turn},
    )

    from game_engine.quests import create_contextual_story_quest_data

    next_sq_id = f"SQ-{uuid.uuid4().hex[:8].upper()}"
    ch_bp = (spine.get("chapters_blueprint") or {}).get(str(next_ch)) or {}
    fallback_data = create_contextual_story_quest_data(session_id, sess, chapter_num=next_ch)
    next_subs = fallback_data.get("sub_objectives") or []
    next_wps = fallback_data.get("sub_waypoints") or {}

    next_title = str(ch_bp.get("title_template") or fallback_data.get("title") or f"Chapter #{next_ch}")
    next_engine = str(ch_bp.get("engine") or fallback_data.get("archetype") or "MYSTERY_CASE")
    next_obj = sanitize_dossier_prose(
        str(fallback_data.get("objective") or ch_bp.get("pacing_directive") or "A new chapter unfolds...")
    )

    next_quest = db.upsert_quest(
        session_id=session_id,
        quest_id=next_sq_id,
        quest_type=str(fallback_data.get("archetype") or "Story Quest"),
        title=next_title,
        objective=next_obj,
        progress=f"0/{len(next_subs)} Cleared" if next_subs else f"Quest #{next_ch}",
        current_clues="",
        status="Active",
        reward_xp=250 + (next_ch * 30),
        reward_gold=60 + (next_ch * 10),
        is_story_quest=1,
        clues_required=len(next_subs),
        sub_objectives=next_subs,
        engine=next_engine,
        dossier_stage="compiled",
    )
    for so in next_subs:
        so_id = so.get("id")
        wps = next_wps.get(so_id) or []
        if wps:
            db.save_quest_waypoints(session_id=session_id, quest_id=next_sq_id, waypoints=wps, sub_obj_id=so_id)

    feat_lt = str(ch_bp.get("featured_lieutenant") or "")
    mm_name = str((spine.get("mastermind_profile") or {}).get("name") or "")
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

    return {
        "chapter": next_ch,
        "previous_chapter": cur_ch,
        "next_quest_id": next_sq_id,
        "next_quest": next_quest,
        "next_dossier": next_dossier,
        "fail_forward": bool(status == "Failed"),
        "world_scar": world_scar_ev,
    }


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
