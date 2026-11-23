from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

import db
from db import adb
import game_engine
from mechanics.social.factions import (
    resolve_board_club_faction_for_location,
    validate_faction_hq_action_access,
)
from mechanics.system.concurrency import distributed_session_lock
from mechanics.world.locations import get_notice_board_label, location_has_bounty_board
from ..deps import (
    BountyActionRequest,
    BountyGenerateRequest,
    ClueDeductionRequest,
    EpilogueChoiceRequest,
    QuestTurnInRequest,
    SuspectAccusationRequest,
    _serializable_action,
)
from ..security import verify_session_participant
from .common import _verify_missing_session_codex_auth

router = APIRouter()


def _build_quests_payload(session_id: int, user_id: Optional[int] = None) -> dict:
    from mechanics.world.waypoints import ensure_quest_waypoints_exist, get_story_quest_climax_location

    try:
        ensure_quest_waypoints_exist(session_id)
    except Exception:
        pass
    session = db.get_session(session_id) or {}
    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    eff_uid = user_id if user_id is not None else session.get("host_user_id")
    settings = (db.get_settings(eff_uid) or {}) if eff_uid else {}
    reveal_all = bool(int(settings.get("debug_reveal_all_info") or 0))

    quests = [dict(q) for q in db.get_session_quests(session_id) if q]
    import scenario_data as _sd_qp

    is_anom_qp = _sd_qp.is_anomalous_incursions_scenario(scen_key)
    target_uid_qp = eff_uid
    fac_st_qp = None
    is_synd_wiretap_qp = False
    evaluate_anomalous_bounty_eligibility = None
    parse_anomalous_quest_board_source = None
    if is_anom_qp:
        from mechanics.narrative.bounty import (
            evaluate_anomalous_bounty_eligibility,
            parse_anomalous_quest_board_source,
        )
        from mechanics.social.factions import get_anomalous_faction_state

        fac_st_qp = get_anomalous_faction_state(session_id, user_id=target_uid_qp)
        is_synd_wiretap_qp = (
            str((fac_st_qp or {}).get("faction_archetype_key") or "").strip().lower() == "clandestine_faction"
        )
    from mechanics.world.locations.hierarchy import (
        clean_narrative_location_arrows,
        dedupe_location_stutter,
        format_clean_location_badge,
        resolve_session_location_tokens,
    )

    def _clean_quest_dict(q: dict) -> None:
        if q.get("title"):
            q["title"] = clean_narrative_location_arrows(resolve_session_location_tokens(session_id, q["title"], scen_key))
        if q.get("objective"):
            q["objective"] = clean_narrative_location_arrows(
                resolve_session_location_tokens(session_id, q["objective"], scen_key)
            )
        if q.get("stage_label"):
            q["stage_label"] = clean_narrative_location_arrows(
                resolve_session_location_tokens(session_id, q["stage_label"], scen_key)
            )
        if q.get("target_location"):
            q["target_location"] = dedupe_location_stutter(
                resolve_session_location_tokens(session_id, q["target_location"], scen_key)
            )
        if q.get("waypoints") and isinstance(q["waypoints"], list):
            for wp in q["waypoints"]:
                if isinstance(wp, dict):
                    if wp.get("stage_label"):
                        wp["stage_label"] = clean_narrative_location_arrows(
                            resolve_session_location_tokens(session_id, wp["stage_label"], scen_key)
                        )
                    if wp.get("target_location"):
                        wp["target_location"] = dedupe_location_stutter(
                            resolve_session_location_tokens(session_id, wp["target_location"], scen_key)
                        )
        if q.get("sub_objectives"):
            for so in q["sub_objectives"]:
                if isinstance(so, dict):
                    if so.get("text"):
                        so["text"] = clean_narrative_location_arrows(
                            resolve_session_location_tokens(session_id, so["text"], scen_key)
                        )
                    if so.get("stage_label"):
                        so["stage_label"] = clean_narrative_location_arrows(
                            resolve_session_location_tokens(session_id, so["stage_label"], scen_key)
                        )
                    if so.get("target_location"):
                        so["target_location"] = dedupe_location_stutter(
                            resolve_session_location_tokens(session_id, so["target_location"], scen_key)
                        )
                    if so.get("waypoints") and isinstance(so["waypoints"], list):
                        for wp in so["waypoints"]:
                            if isinstance(wp, dict):
                                if wp.get("stage_label"):
                                    wp["stage_label"] = clean_narrative_location_arrows(
                                        resolve_session_location_tokens(session_id, wp["stage_label"], scen_key)
                                    )
                                if wp.get("target_location"):
                                    wp["target_location"] = dedupe_location_stutter(
                                        resolve_session_location_tokens(session_id, wp["target_location"], scen_key)
                                    )
        _saved_notes = q.get("quest_notes")
        _saved_anom_bp = q.get("anomaly_blueprint")
        _saved_anom_bp_json = q.get("anomaly_blueprint_json")
        _saved_dos = q.get("dossier")
        _redacted = game_engine.redact_quest_for_fog_of_war(session_id, q, reveal_all=reveal_all)
        q.clear()
        q.update(_redacted)
        q["fow_dossier"] = q.get("fow") or game_engine.build_fog_of_war_quest_payload(
            session_id,
            q,
            dossier=_saved_dos,
            reveal_all=reveal_all,
        )
        if reveal_all:
            if _saved_dos is not None:
                q["dossier"] = _saved_dos
            if _saved_notes is not None:
                q["quest_notes"] = _saved_notes
            if _saved_anom_bp is not None:
                q["anomaly_blueprint"] = _saved_anom_bp
            if _saved_anom_bp_json is not None:
                q["anomaly_blueprint_json"] = _saved_anom_bp_json
        else:
            q["quest_notes"] = ""
            q.pop("anomaly_blueprint_json", None)
        if isinstance(q.get("main_objective"), dict):
            mo = q["main_objective"]
            if mo.get("title"):
                mo["title"] = clean_narrative_location_arrows(
                    resolve_session_location_tokens(session_id, mo["title"], scen_key)
                )
                mo["text"] = mo["title"]
            for ms in (mo.get("stages") or []):
                if isinstance(ms, dict):
                    if ms.get("stage_label"):
                        ms["stage_label"] = clean_narrative_location_arrows(
                            resolve_session_location_tokens(session_id, ms["stage_label"], scen_key)
                        )
                        ms["text"] = ms["stage_label"]
                    if ms.get("target_location"):
                        ms["target_location"] = dedupe_location_stutter(
                            resolve_session_location_tokens(session_id, ms["target_location"], scen_key)
                        )
                    if ms.get("key_clue"):
                        if isinstance(ms["key_clue"], dict):
                            raw_kc = ms["key_clue"]
                            kc_t = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(raw_kc.get("title") or ""), scen_key)
                            )
                            kc_l = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(raw_kc.get("lead_text") or ""), scen_key)
                            )
                            ms["key_clue"] = (
                                f"{kc_t} — {kc_l}"
                                if (kc_t and kc_l and kc_l.lower() != kc_t.lower())
                                else (kc_t or kc_l)
                            )
                            ms["key_clue_meta"] = {
                                "title": kc_t,
                                "lead_text": kc_l,
                                "clue_id": str(raw_kc.get("clue_id") or ""),
                            }
                        else:
                            ms["key_clue"] = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, ms["key_clue"], scen_key)
                            )
                    if isinstance(ms.get("key_clue_meta"), dict):
                        if ms["key_clue_meta"].get("title"):
                            ms["key_clue_meta"]["title"] = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(ms["key_clue_meta"]["title"]), scen_key)
                            )
                        if ms["key_clue_meta"].get("lead_text"):
                            ms["key_clue_meta"]["lead_text"] = clean_narrative_location_arrows(
                                resolve_session_location_tokens(session_id, str(ms["key_clue_meta"]["lead_text"]), scen_key)
                            )
                    for src in (ms.get("clue_sources") or []):
                        if isinstance(src, dict):
                            if src.get("label"):
                                src["label"] = clean_narrative_location_arrows(
                                    resolve_session_location_tokens(session_id, src["label"], scen_key)
                                )
                            if src.get("approach_hint"):
                                src["approach_hint"] = clean_narrative_location_arrows(
                                    resolve_session_location_tokens(session_id, src["approach_hint"], scen_key)
                                )
                            if src.get("location") and src["location"] != "Hidden Lair":
                                resolved_src_loc = dedupe_location_stutter(
                                    resolve_session_location_tokens(session_id, src["location"], scen_key)
                                )
                                src["location"] = resolved_src_loc
                                src["location_display"] = format_clean_location_badge(resolved_src_loc, include_zone=True)
        for opt_o in (q.get("optional_objectives") or []):
            if isinstance(opt_o, dict):
                if opt_o.get("title"):
                    opt_o["title"] = clean_narrative_location_arrows(
                        resolve_session_location_tokens(session_id, opt_o["title"], scen_key)
                    )
                    opt_o["text"] = opt_o["title"]
                if opt_o.get("stakes_hint"):
                    opt_o["stakes_hint"] = clean_narrative_location_arrows(
                        resolve_session_location_tokens(session_id, opt_o["stakes_hint"], scen_key)
                    )
                if opt_o.get("target_location"):
                    opt_o["target_location"] = dedupe_location_stutter(
                        resolve_session_location_tokens(session_id, opt_o["target_location"], scen_key)
                    )
        q_notes_raw = str(_saved_notes or q.get("quest_notes") or "")
        if is_anom_qp and q.get("status") == "Available":
            try:
                elig_probe = dict(q)
                if _saved_notes is not None:
                    elig_probe["quest_notes"] = _saved_notes
                elig = evaluate_anomalous_bounty_eligibility(
                    session_id,
                    target_uid_qp,
                    elig_probe,
                    session=session,
                    fac_state=fac_st_qp,
                )
                q["board_source"] = elig.get("board_source") or parse_anomalous_quest_board_source(
                    elig_probe, session_id=session_id
                )
                q["anomalous_eligible"] = bool(elig.get("allowed", True))
                q["anomalous_lock_reason"] = str(elig.get("reason") or "")
            except Exception:
                pass
        has_anom_bp = (
            "anomaly_bp:" in q_notes_raw
            or "anomaly_blueprint:" in q_notes_raw
            or bool(
                isinstance(_saved_anom_bp or q.get("anomaly_blueprint"), dict)
                and (_saved_anom_bp or q.get("anomaly_blueprint"))
            )
            or str(_saved_anom_bp_json or q.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
        )
        if has_anom_bp:
            try:
                from mechanics.world.anomaly_engine import (
                    format_anomaly_dossier_summary,
                    parse_blueprint_from_notes,
                )
                from mechanics.world.folklore_mechanics import (
                    get_public_anomaly_name,
                    is_blueprint_disguised,
                    unmask_blueprint_disguise,
                )

                parse_probe = dict(q)
                if _saved_notes is not None:
                    parse_probe["quest_notes"] = _saved_notes
                if _saved_anom_bp is not None:
                    parse_probe["anomaly_blueprint"] = _saved_anom_bp
                if _saved_anom_bp_json is not None:
                    parse_probe["anomaly_blueprint_json"] = _saved_anom_bp_json
                bp_q = parse_blueprint_from_notes(parse_probe)
                if bp_q:
                    b_src_q = ""
                    if is_anom_qp:
                        b_src_q = str(
                            q.get("board_source")
                            or parse_anomalous_quest_board_source(parse_probe, session_id=session_id)
                        ).strip().lower()
                    wiretap_live = bool(
                        is_synd_wiretap_qp
                        and q.get("status") == "Available"
                        and b_src_q in ("clandestine_faction", "freelance_app")
                    )
                    if wiretap_live:
                        bp_q, _ = unmask_blueprint_disguise(bp_q)
                    is_rev = bool(
                        reveal_all
                        or wiretap_live
                        or "dossier_revealed:1" in q_notes_raw
                        or bp_q.get("dossier_revealed")
                    )
                    q["anomaly_dossier_revealed"] = is_rev
                    q["anomaly_dossier"] = format_anomaly_dossier_summary(bp_q, revealed=is_rev)
                    if is_rev:
                        q["anomaly_blueprint"] = bp_q
                    else:
                        q_disg = is_blueprint_disguised(bp_q, dossier_revealed=False)
                        q["anomaly_blueprint"] = {
                            "name": get_public_anomaly_name(bp_q, dossier_revealed=False, fallback="Unknown Anomaly"),
                            "type": "unknown" if q_disg else bp_q.get("type"),
                            "form": "" if q_disg else bp_q.get("form"),
                            "physicality": "unknown",
                            "disposition": bp_q.get("disposition"),
                            "sapience": "unknown",
                            "element": "unknown",
                            "is_disguised": q_disg,
                            "dossier_revealed": False,
                        }
            except Exception:
                pass

    for q in quests:
        _clean_quest_dict(q)
    active_sq = db.get_active_story_quest(session_id)
    if active_sq:
        active_sq = dict(active_sq)
        _clean_quest_dict(active_sq)
    if active_sq and active_sq.get("climax_ready"):
        try:
            sq_dos = db.get_quest_dossier(session_id, active_sq.get("quest_id", ""))
            climax_spec_sq = (sq_dos or {}).get("climax_spec") or {}
            is_climax_unlocked = bool(
                reveal_all
                or (str(climax_spec_sq.get("gate_type") or climax_spec_sq.get("gate_mode") or "").lower() == "open")
                or climax_spec_sq.get("is_unlocked")
            )
            _, climax_loc = get_story_quest_climax_location(session_id)
            if climax_loc and is_climax_unlocked:
                clean_climax = dedupe_location_stutter(
                    resolve_session_location_tokens(session_id, climax_loc, scen_key).replace(" -> ", " ➔ ")
                )
                active_sq["climax_location"] = clean_climax
                active_sq["target_location"] = clean_climax
        except Exception:
            pass
    clues = [dict(c) for c in db.get_session_clues(session_id) if c]
    if clues:
        cg_by_clue_id: dict[int, dict] = {}
        cg_by_title: dict[str, dict] = {}
        for _dos_c in (db.get_session_quest_dossiers(session_id) or []):
            _d_qid = str(_dos_c.get("quest_id") or "").strip()
            for _cn in (_dos_c.get("clue_graph") or []):
                if not isinstance(_cn, dict):
                    continue
                _node_meta = {
                    "clue_tier": "corroborating"
                    if (bool(_cn.get("is_red_herring")) or str(_cn.get("clue_tier") or "").strip().lower() == "red_herring")
                    else (
                        str(_cn.get("clue_tier") or "").strip().lower()
                        if str(_cn.get("clue_tier") or "").strip().lower() in ("key_clue", "corroborating")
                        else "corroborating"
                    ),
                    "corroboration_group": str(_cn.get("corroboration_group") or _cn.get("quest_id") or _d_qid).strip(),
                }
                _raw_cid = _cn.get("clue_id")
                try:
                    if _raw_cid is not None and not isinstance(_raw_cid, bool):
                        cg_by_clue_id[int(_raw_cid)] = _node_meta
                except (TypeError, ValueError):
                    pass
                _n_title = str(_cn.get("title") or "").strip().lower()
                if _n_title:
                    cg_by_title.setdefault(f"{_d_qid}::{_n_title}", _node_meta)
                    cg_by_title.setdefault(f"::{_n_title}", _node_meta)
        for c in clues:
            try:
                _cid_int = int(c["id"]) if c.get("id") is not None else None
            except (TypeError, ValueError):
                _cid_int = None
            _c_qid = str(c.get("quest_id") or "").strip()
            _c_title = str(c.get("title") or "").strip().lower()
            _meta = (
                (cg_by_clue_id.get(_cid_int) if _cid_int is not None else None)
                or cg_by_title.get(f"{_c_qid}::{_c_title}")
                or cg_by_title.get(f"::{_c_title}")
            )
            if _meta:
                c["clue_tier"] = _meta["clue_tier"]
                if _meta["corroboration_group"]:
                    c["corroboration_group"] = _meta["corroboration_group"]
            elif c.get("clue_tier") == "red_herring":
                c["clue_tier"] = "corroborating"
    available_bounties = [q for q in quests if q.get("status") == "Available"]
    nb_label, nb_emoji = get_notice_board_label(scen_key)
    current_chapter = db.get_session_chapter(session_id) or 1
    campaign_end_goals = session.get("campaign_end_goals") or db.get_session_campaign_goals(session_id) or []
    chapter_digest = db.get_chapter_digest(session_id) or []

    spine = db.get_campaign_spine(session_id)
    world_scars = [
        {
            "event_key": e.get("event_key"),
            "title": e.get("title"),
            "location_name": e.get("location_name"),
            "description": e.get("description"),
            "remediation_quest_id": (e.get("metadata") or {}).get("remediation_quest_id")
            if isinstance(e.get("metadata"), dict)
            else None,
            "scar_tier": ((e.get("metadata") or {}).get("scar_tier") or "bounty")
            if isinstance(e.get("metadata"), dict)
            else "bounty",
            "remediation_type": (e.get("metadata") or {}).get("remediation_type")
            if isinstance(e.get("metadata"), dict)
            else None,
        }
        for e in (db.get_world_events(session_id, statuses=("active",)) or [])
        if (
            str(e.get("event_type") or "") == "world_scar"
            or (isinstance(e.get("metadata"), dict) and e["metadata"].get("is_world_scar"))
            or str(e.get("template_key") or "").startswith("world_scar_")
            or str(e.get("event_key") or "").startswith("scar_")
        )
    ]
    campaign_spine_summary = {
        "max_chapters": 11,
        "has_spine": spine is not None,
        "climax_status": (spine or {}).get("climax_status") or "pending",
        "epilogue_status": (spine or {}).get("epilogue_status") or "pending",
        "nemeses_count": len((spine or {}).get("nemeses") or []),
        "world_scars": world_scars,
        "campaign_game_over": bool(session.get("campaign_game_over")),
        "fallen_world": bool(session.get("fallen_world")),
        "epilogue_ready": bool(session.get("epilogue_ready")),
        "epilogue_choices": list(session.get("epilogue_choices") or []),
        "endless_mode_unlocked": bool(session.get("endless_mode_unlocked")),
        "campaign_archived": bool(session.get("campaign_archived") or session.get("chronicle_archived")),
        "is_peak_chapter": int(current_chapter) in (3, 6, 8, 9, 10),
        "chronicle_tapestry": (spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {},
        "ending_archetype": (
            ((spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {}).get("ending_archetype")
            or ((spine or {}).get("chronicle_tapestry") or session.get("chronicle_tapestry") or {}).get("ending_id")
            or ""
        ),
    }

    if not reveal_all:
        for q_red in list(quests) + ([active_sq] if isinstance(active_sq, dict) else []):
            if isinstance(q_red, dict):
                has_raw_anom = (
                    "anomaly_bp:" in str(q_red.get("quest_notes") or "")
                    or "anomaly_blueprint:" in str(q_red.get("quest_notes") or "")
                    or str(q_red.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
                )
                if has_raw_anom:
                    q_red["quest_notes"] = ""
                q_red.pop("anomaly_blueprint_json", None)

    return {
        "quests": quests,
        "available_bounties": available_bounties,
        "active_story_quest": active_sq,
        "clues": clues,
        "has_bounty_board": location_has_bounty_board(current_loc, scen_key=scen_key),
        "notice_board_label": nb_label,
        "notice_board_emoji": nb_emoji,
        "current_chapter": current_chapter,
        "max_chapters": 11,
        "campaign_end_goals": campaign_end_goals,
        "chapter_digest": chapter_digest,
        "campaign_spine": campaign_spine_summary,
        "debug_reveal_all": reveal_all,
    }


@router.get("/api/quests/{session_id}")
async def get_quests(session_id: int, user_id: Optional[int] = Query(None), request: Request = None):
    """Fetches active, available, and completed quests, active story quest, Fog-of-War dossiers, and Caseboard clues."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    res = await adb(_build_quests_payload, session_id, user_id)
    return _serializable_action(res)


@router.post("/api/quests/{session_id}/bounties/generate")
async def generate_session_bounties(session_id: int, req: BountyGenerateRequest, request: Request = None):
    """Generates or refreshes the Bounty Board contracts for the session."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)

    scoped_club_faction = None
    async with distributed_session_lock(session_id):
        if req.faction_id:
            factions = await adb(db.get_factions, session_id)
            target_f = next((f for f in (factions or []) if f.get("faction_id") == req.faction_id), None)
            if target_f:
                hq_ok, hq_err, hq_code = await adb(
                    validate_faction_hq_action_access, session_id, req.user_id, target_f, "bounty", session
                )
                if not hq_ok:
                    raise HTTPException(status_code=hq_code, detail=hq_err)
                bounties = await game_engine.generate_faction_bounty_board(
                    session, target_f, force_refresh=req.force_refresh
                )
            else:
                bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)
        else:
            scoped_club_faction = await adb(
                resolve_board_club_faction_for_location,
                session_id,
                str(session.get("current_location") or ""),
                str(session.get("scenario") or ""),
            )
            if scoped_club_faction:
                bounties = await game_engine.generate_faction_bounty_board(
                    session, scoped_club_faction, force_refresh=req.force_refresh
                )
            else:
                bounties = await game_engine.generate_bounty_board(session, force_refresh=req.force_refresh)

    payload = await adb(_build_quests_payload, session_id, req.user_id)
    resp_bounties = (
        bounties if (req.faction_id or scoped_club_faction) and bounties else (payload.get("available_bounties") or [])
    )
    return _serializable_action(
        {
            "success": True,
            "bounties": [dict(b) for b in resp_bounties if b],
            **payload,
        }
    )


@router.post("/api/quests/{session_id}/bounties/action")
async def bounty_contract_action(session_id: int, req: BountyActionRequest, request: Request = None):
    """Accepts an available bounty (compiling Stage-2 QuestDossier + optional CHA advance) or abandons/forfeits an active bounty."""
    session, _ = await verify_session_participant(request, session_id, req.user_id)
    quest = await adb(db.get_quest_by_id, session_id, req.quest_id)
    if not quest:
        raise HTTPException(status_code=404, detail="Bounty contract not found")
    scen_key = str(session.get("scenario") or "fantasy")
    action = (req.action or "accept").strip().lower()

    import scenario_data

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        notes = str(quest.get("quest_notes") or "")
        if action == "accept":
            from mechanics.narrative.bounty import evaluate_anomalous_bounty_eligibility

            elig = await adb(evaluate_anomalous_bounty_eligibility, session_id, req.user_id, quest)
            if not elig.get("allowed", True):
                raise HTTPException(
                    status_code=400,
                    detail=elig.get("reason") or "Faction rules prohibit accepting this bounty.",
                )
        elif action == "abandon":
            if "mandatory_daily:1" in notes or str(quest.get("quest_id") or "").upper().startswith("MAND-"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Mandatory Daily Dispatches cannot be abandoned! "
                        "Complete it before 24:00 to avoid a -15 Reputation penalty."
                    ),
                )

    advance_result = None
    forfeit_details = None
    if action == "accept":
        acc_res = await game_engine.accept_bounty_contract_async(
            session_id=session_id,
            quest_id=req.quest_id,
            user_id=req.user_id,
            haggle_advance=bool(req.haggle_advance),
            enrich_llm=False,
        )
        if not acc_res.get("success"):
            raise HTTPException(
                status_code=int(acc_res.get("status_code") or 400),
                detail=acc_res.get("reason") or "Cannot accept this contract.",
            )
        new_status = "Active"
        advance_result = acc_res.get("advance_result")
        adv_note = (
            f" (+{advance_result['advance_gold']}G upfront advance secured!)"
            if isinstance(advance_result, dict) and advance_result.get("succeeded")
            else ""
        )
        msg = f"Accepted contract: {quest.get('title', 'Bounty')}!{adv_note}"
    elif action == "abandon":
        async with distributed_session_lock(session_id):
            forfeit_res = await adb(
                game_engine.forfeit_side_bounty,
                session_id,
                req.quest_id,
                [req.user_id] if req.user_id is not None else None,
                req.user_id,
            )
            if not forfeit_res.get("success"):
                raise HTTPException(
                    status_code=int(forfeit_res.get("status_code") or 400),
                    detail=forfeit_res.get("reason") or "Cannot abandon this contract.",
                )
            new_status = str(forfeit_res.get("status") or "Abandoned")
            forfeit_details = _serializable_action(forfeit_res)
            if new_status == "Failed":
                msg = f"Forfeited engaged contract '{quest.get('title', 'Bounty')}' — marked Failed with regional fallout!"
            else:
                msg = f"Abandoned contract: {quest.get('title', 'Bounty')}."
    else:
        raise HTTPException(status_code=400, detail=f"Invalid bounty action: {req.action}")

    payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action(
        {
            "success": True,
            "quest_id": req.quest_id,
            "status": new_status,
            "message": msg,
            "advance_result": advance_result,
            "forfeit_details": forfeit_details,
            **payload,
        }
    )


@router.post("/api/quests/{session_id}/clues/deduce")
async def deduce_caseboard_clues(session_id: int, req: ClueDeductionRequest, request: Request = None):
    """Deterministically cross-references two evidence clues via QuestDossier clue_graph / Logic Caseboard (zero RNG!)."""
    await verify_session_participant(request, session_id, req.user_id)
    is_single = req.clue_b_id is None or int(req.clue_a_id) == int(req.clue_b_id)

    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        clue_a = await adb(db.get_session_clue_by_id, req.clue_a_id)
        if not clue_a:
            raise HTTPException(status_code=404, detail="Selected evidence record could not be found.")
        if clue_a.get("is_consumed"):
            raise HTTPException(status_code=400, detail="The selected lead has already been consumed.")

        if is_single:
            pair_key = f"single:{int(req.clue_a_id)}"
            eff_clue_b_id = None
        else:
            clue_b = await adb(db.get_session_clue_by_id, req.clue_b_id)
            if not clue_b:
                raise HTTPException(status_code=404, detail="Secondary evidence record could not be found.")
            if clue_b.get("is_consumed"):
                raise HTTPException(status_code=400, detail="Secondary lead has already been consumed.")
            pair_key = f"{min(int(req.clue_a_id), int(req.clue_b_id))}:{max(int(req.clue_a_id), int(req.clue_b_id))}"
            eff_clue_b_id = req.clue_b_id

        cur_turn = int(db.infer_session_turn(session))
        attempts_map = dict(session.get("deduction_attempts_turn") or {})
        if attempts_map.get(pair_key) == cur_turn:
            raise HTTPException(
                status_code=400,
                detail="You already attempted to connect this lead or pair this turn. Advance the story or try another lead!",
            )

        ded_res = await adb(
            game_engine.resolve_caseboard_deduction, session_id, req.clue_a_id, eff_clue_b_id, req.user_id
        )
        attempts_map[pair_key] = cur_turn
        await adb(db.update_session, session_id, extra={"deduction_attempts_turn": attempts_map})

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action(
        {
            "success": True,
            "is_valid": bool(ded_res.get("is_valid")),
            "is_red_herring": bool(ded_res.get("is_red_herring")),
            "partial_corroboration": bool(ded_res.get("partial_corroboration")),
            "shortcut_unlocked": bool(ded_res.get("shortcut_unlocked")),
            "threat_clock_paused": bool(ded_res.get("threat_clock_paused")),
            "title": ded_res.get("title") or "",
            "detail_text": ded_res.get("detail_text") or "",
            "xp_awarded": int(ded_res.get("xp_awarded") or 0),
            "climax_unlocked": bool(ded_res.get("climax_unlocked")),
            "twist_revealed": bool(ded_res.get("twist_revealed")),
            **payload,
        }
    )


@router.post("/api/quests/{session_id}/caseboard/accuse")
async def accuse_caseboard_suspect(session_id: int, req: SuspectAccusationRequest, request: Request = None):
    """Resolves a Private Confrontation vs. Formal Public Accusation against a Caseboard suspect."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_suspect_accusation,
            session_id,
            req.quest_id,
            req.suspect_name,
            req.mode,
            req.user_id,
        )
        if not res.get("success"):
            raise HTTPException(
                status_code=int(res.get("status_code") or 400),
                detail=res.get("reason") or "Could not resolve suspect accusation.",
            )

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({**res, **payload})


@router.post("/api/quests/{session_id}/turn-in")
async def resolve_contract_turn_in(session_id: int, req: QuestTurnInRequest, request: Request = None):
    """Resolves Contract Turn-In, Side-Switching, `2x` Twist Blackmail, or Tangible MacGuffin Keep/Destroy/Fence."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_quest_turn_in_or_betrayal,
            session_id,
            req.quest_id,
            req.user_id,
            req.disposition,
            None,
            str(session.get("current_location") or ""),
        )
        if not res.get("success"):
            raise HTTPException(
                status_code=int(res.get("status_code") or 400),
                detail=res.get("reason") or "Could not resolve contract turn-in.",
            )

        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({**res, **payload})


@router.post("/api/quests/{session_id}/epilogue")
async def resolve_campaign_epilogue_choice(session_id: int, req: EpilogueChoiceRequest, request: Request = None):
    """Resolves Chapter 11 Universal Epilogue choice: 'archive' vs 'endless'."""
    await verify_session_participant(request, session_id, req.user_id)
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        res = await adb(
            game_engine.resolve_epilogue_choice,
            session_id,
            req.choice_id,
            [req.user_id] if req.user_id is not None else None,
        )
        payload = await adb(_build_quests_payload, session_id, req.user_id)
    return _serializable_action({"success": True, **res, **payload})
