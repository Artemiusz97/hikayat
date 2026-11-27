from __future__ import annotations

import logging
from typing import Any, Optional

import db

_log = logging.getLogger(__name__)


def persist_anomalous_quest_containment(
    session_id: int,
    quest: dict[str, Any],
    user_id: int,
    party_user_ids: Optional[list[int]] = None,
    *,
    prevent_vault_capture: bool = False,
) -> dict[str, Any]:
    """
    Layer-3 persistence orchestrator for anomalous quest containment & Taxpayer Mandate rules.
    Evaluates pure rules via `evaluate_anomalous_quest_containment`, then idempotently persists
    Vault logs, account-wide codex progression, object-relic conversion, and `vault_logged:1`.
    """
    from mechanics.narrative.bounty import parse_anomalous_quest_board_source
    from mechanics.social.factions import get_anomalous_faction_state
    from mechanics.world.anomaly_engine import evaluate_anomalous_quest_containment
    from mechanics.world.anomalous_events import (
        handle_secured_object_anomaly_conversion,
        record_contained_anomaly_to_vault_log,
    )

    eff_quest = dict(quest) if isinstance(quest, dict) else {}
    qid = str(eff_quest.get("quest_id") or "")
    if qid:
        db_q = db.get_quest_by_id(session_id, qid)
        if db_q:
            q_notes_db = str(db_q.get("quest_notes") or "")
            if "vault_logged:1" in q_notes_db or not eff_quest.get("quest_notes"):
                eff_quest["quest_notes"] = q_notes_db
            if not eff_quest.get("anomaly_blueprint") and db_q.get("anomaly_blueprint"):
                eff_quest["anomaly_blueprint"] = db_q["anomaly_blueprint"]

    fac_st = get_anomalous_faction_state(session_id, user_id=user_id)
    src = parse_anomalous_quest_board_source(eff_quest, session_id=session_id)
    eval_res = evaluate_anomalous_quest_containment(eff_quest, fac_st, src)

    if eval_res["already_logged"]:
        return {
            "already_logged": True,
            "confiscate_gold": bool(eval_res["confiscate_gold"]),
        }

    bp = eval_res.get("blueprint")
    ent_name = str(eval_res.get("entity_name") or "Anomalous Specimen")
    uids = list(party_user_ids or [user_id])
    if user_id not in uids:
        uids.append(user_id)

    if not prevent_vault_capture:
        with db.UnitOfWork() as conn:
            try:
                with db.savepoint(conn, "sp_vault_log"):
                    record_contained_anomaly_to_vault_log(
                        session_id=session_id,
                        entity_name=ent_name,
                        category_tag=str(eval_res.get("category_tag") or "spatial_warp"),
                        subtype=str(eval_res.get("subtype") or "non_hostile_entity"),
                        location=str(eff_quest.get("client_location") or "Metropolitan Grid"),
                        containment_note=f"Logged on completion of '{eff_quest.get('title')}'.",
                        resolution_method="Bounty Containment Protocol",
                        user_id=user_id,
                        quest_id=qid,
                    )
            except Exception as exc:
                _log.warning("Vault log persistence failed for session %s quest %s: %s", session_id, qid, exc)

            if eval_res.get("codex_id"):
                try:
                    with db.savepoint(conn, "sp_codex_prog"):
                        db.record_folklore_codex_progress(
                            uids, str(eval_res["codex_id"]), stage="contained", session_id=session_id
                        )
                except Exception as exc:
                    _log.warning("Folklore codex progress failed for session %s: %s", session_id, exc)

            if eval_res.get("is_object_anomaly") and isinstance(bp, dict):
                try:
                    with db.savepoint(conn, "sp_obj_conv"):
                        handle_secured_object_anomaly_conversion(
                            session_id, user_id, bp, entity_name=ent_name
                        )
                except Exception as exc:
                    _log.warning("Object anomaly conversion failed for session %s: %s", session_id, exc)

            if qid:
                db.append_quest_note_flag_in_db(session_id, qid, "vault_logged", "1")
            if isinstance(quest, dict):
                orig_n = str(quest.get("quest_notes") or "")
                quest["quest_notes"] = f"{orig_n}|vault_logged:1" if orig_n else "vault_logged:1"

    return {
        "already_logged": False,
        "confiscate_gold": bool(eval_res["confiscate_gold"]),
    }
