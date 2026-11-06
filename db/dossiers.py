from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Optional

from .core import get_conn

_log = logging.getLogger(__name__)


def _deserialize_json_field(val: Any, default: Any) -> Any:
    if val is None or val == "":
        return default
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


def _json_str(val: Any, default_str: str = "{}") -> str:
    if val is None:
        return default_str
    if isinstance(val, str):
        stripped = val.strip()
        return stripped if stripped else default_str
    try:
        return json.dumps(val)
    except Exception:
        return default_str


def _enrich_spine_dict(row: sqlite3.Row | dict | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["mastermind_profile"] = _deserialize_json_field(d.get("mastermind_profile_json"), {})
    d["mastermind"] = d["mastermind_profile"]
    d["lieutenants_roster"] = _deserialize_json_field(d.get("lieutenants_roster_json"), [])
    d["lieutenants"] = d["lieutenants_roster"]
    d["chapters_blueprint"] = _deserialize_json_field(d.get("chapters_blueprint_json"), {})
    d["chapters"] = d["chapters_blueprint"]
    d["nemeses"] = _deserialize_json_field(d.get("nemeses_json"), [])
    d["state_events"] = _deserialize_json_field(d.get("state_events_json"), [])
    return d


def _enrich_dossier_dict(row: sqlite3.Row | dict | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["pitch_stub"] = _deserialize_json_field(d.get("pitch_stub_json"), {})
    d["pitch_card"] = d["pitch_stub"]
    d["cast_bindings"] = _deserialize_json_field(d.get("cast_bindings_json"), {})
    d["leads_graph"] = _deserialize_json_field(d.get("leads_graph_json"), [])
    d["clue_graph"] = _deserialize_json_field(d.get("clue_graph_json"), [])
    d["climax_spec"] = _deserialize_json_field(d.get("climax_spec_json"), {})
    d["twist_spec"] = _deserialize_json_field(d.get("twist_spec_json"), {})
    d["tangible_item"] = _deserialize_json_field(d.get("tangible_item_json"), {})
    d["contract_economy"] = _deserialize_json_field(d.get("contract_economy_json"), {})
    d["turn_in_rules"] = _deserialize_json_field(d.get("turn_in_rules_json"), {})
    d["outcomes_matrix"] = _deserialize_json_field(d.get("outcomes_matrix_json"), {})
    d["burned_approaches"] = _deserialize_json_field(d.get("burned_approaches_json"), {})
    d["state_events"] = _deserialize_json_field(d.get("state_events_json"), [])
    d["danger_tier"] = int(d.get("danger_tier") or 1)
    d["alert_level"] = int(d.get("alert_level") or 0)
    d["max_alert"] = int(d.get("max_alert") or 4)
    d["rescue_shield_used"] = int(d.get("rescue_shield_used") or 0)
    d["engaged_flag"] = int(d.get("engaged_flag") or 0)
    d["compiled_at_turn"] = int(d.get("compiled_at_turn") or 0)
    return d


def get_campaign_spine(session_id: int, conn: Optional[sqlite3.Connection] = None) -> dict | None:
    def _run(c: sqlite3.Connection) -> dict | None:
        row = c.execute("SELECT * FROM campaign_spines WHERE session_id = ?", (session_id,)).fetchone()
        return _enrich_spine_dict(row)

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_campaign_spine(
    session_id: int,
    scenario_or_dict: str | dict = "",
    conn: Optional[sqlite3.Connection] = None,
    **kwargs: Any,
) -> dict | None:
    now = time.time()
    src = dict(scenario_or_dict) if isinstance(scenario_or_dict, dict) else {}

    def _pick(key: str, json_key: str, alt_key: str = "", default: Any = None) -> Any:
        for k in (key, json_key, alt_key):
            if not k:
                continue
            if k in kwargs and kwargs[k] is not None:
                return kwargs[k]
            if k in src and src[k] is not None:
                return src[k]
        return default

    def _run(c: sqlite3.Connection) -> dict | None:
        existing = get_campaign_spine(session_id, conn=c) or {}
        scenario = (
            (scenario_or_dict if isinstance(scenario_or_dict, str) and scenario_or_dict else None)
            or kwargs.get("scenario")
            or src.get("scenario")
            or existing.get("scenario")
            or "fantasy"
        )
        mastermind = _pick("mastermind_profile", "mastermind_profile_json", "mastermind", existing.get("mastermind_profile", {}))
        lieutenants = _pick("lieutenants_roster", "lieutenants_roster_json", "lieutenants", existing.get("lieutenants_roster", []))
        blueprints = _pick("chapters_blueprint", "chapters_blueprint_json", "chapters", existing.get("chapters_blueprint", {}))
        nemeses = _pick("nemeses", "nemeses_json", "", existing.get("nemeses", []))
        climax_status = str(_pick("climax_status", "", "", existing.get("climax_status", "pending")) or "pending")
        epilogue_status = str(_pick("epilogue_status", "", "", existing.get("epilogue_status", "pending")) or "pending")
        state_events = _pick("state_events", "state_events_json", "", existing.get("state_events", []))

        c.execute(
            """INSERT INTO campaign_spines (
                session_id, scenario, mastermind_profile_json, lieutenants_roster_json,
                chapters_blueprint_json, nemeses_json, climax_status, epilogue_status,
                state_events_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                scenario = excluded.scenario,
                mastermind_profile_json = excluded.mastermind_profile_json,
                lieutenants_roster_json = excluded.lieutenants_roster_json,
                chapters_blueprint_json = excluded.chapters_blueprint_json,
                nemeses_json = excluded.nemeses_json,
                climax_status = excluded.climax_status,
                epilogue_status = excluded.epilogue_status,
                state_events_json = excluded.state_events_json,
                updated_at = excluded.updated_at""",
            (
                session_id,
                str(scenario),
                _json_str(mastermind, "{}"),
                _json_str(lieutenants, "[]"),
                _json_str(blueprints, "{}"),
                _json_str(nemeses, "[]"),
                climax_status,
                epilogue_status,
                _json_str(state_events, "[]"),
                now,
                now,
            ),
        )
        return get_campaign_spine(session_id, conn=c)

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_quest_dossier(
    session_id: int,
    quest_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> dict | None:
    def _run(c: sqlite3.Connection) -> dict | None:
        row = c.execute(
            "SELECT * FROM quest_dossiers WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        return _enrich_dossier_dict(row)

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_session_quest_dossiers(
    session_id: int,
    status_stage: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict]:
    def _run(c: sqlite3.Connection) -> list[dict]:
        if status_stage:
            rows = c.execute(
                "SELECT * FROM quest_dossiers WHERE session_id = ? AND status_stage = ? ORDER BY id ASC",
                (session_id, status_stage),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM quest_dossiers WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        return [d for r in rows if (d := _enrich_dossier_dict(r)) is not None]

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_quest_dossier(
    session_id: int,
    quest_id_or_dict: str | dict = "",
    engine: Optional[str] = None,
    family_tier: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    **kwargs: Any,
) -> dict | None:
    now = time.time()
    src = dict(quest_id_or_dict) if isinstance(quest_id_or_dict, dict) else {}
    qid = (
        (quest_id_or_dict if isinstance(quest_id_or_dict, str) and quest_id_or_dict else None)
        or kwargs.get("quest_id")
        or src.get("quest_id")
        or ""
    )
    if not qid:
        raise ValueError("upsert_quest_dossier requires a non-empty quest_id")

    def _pick(key: str, json_key: str = "", default: Any = None) -> Any:
        for k in (key, json_key):
            if not k:
                continue
            if k in kwargs and kwargs[k] is not None:
                return kwargs[k]
            if k in src and src[k] is not None:
                return src[k]
        return default

    def _run(c: sqlite3.Connection) -> dict | None:
        existing = get_quest_dossier(session_id, str(qid), conn=c) or {}
        eff_engine = str(engine or _pick("engine", "", existing.get("engine") or "MYSTERY_CASE"))
        eff_family = str(family_tier or _pick("family_tier", "", existing.get("family_tier") or "bounty"))
        danger_tier = int(_pick("danger_tier", "", existing.get("danger_tier", 1)) or 1)
        status_stage = str(_pick("status_stage", "", existing.get("status_stage", "pitch")) or "pitch")
        compiled_at_turn = int(_pick("compiled_at_turn", "", existing.get("compiled_at_turn", 0)) or 0)
        pitch_stub = (
            kwargs["pitch_card"]
            if "pitch_card" in kwargs and kwargs["pitch_card"] is not None
            else (
                src["pitch_card"]
                if "pitch_card" in src and src["pitch_card"] is not None
                else _pick("pitch_stub", "pitch_stub_json", existing.get("pitch_stub", {}))
            )
        )
        cast_bindings = _pick("cast_bindings", "cast_bindings_json", existing.get("cast_bindings", {}))
        leads_graph = _pick("leads_graph", "leads_graph_json", existing.get("leads_graph", []))
        clue_graph = _pick("clue_graph", "clue_graph_json", existing.get("clue_graph", []))
        climax_spec = _pick("climax_spec", "climax_spec_json", existing.get("climax_spec", {}))
        twist_spec = _pick("twist_spec", "twist_spec_json", existing.get("twist_spec", {}))
        tangible_item = _pick("tangible_item", "tangible_item_json", existing.get("tangible_item", {}))
        contract_economy = _pick("contract_economy", "contract_economy_json", existing.get("contract_economy", {}))
        turn_in_rules = _pick("turn_in_rules", "turn_in_rules_json", existing.get("turn_in_rules", {}))
        outcomes_matrix = _pick("outcomes_matrix", "outcomes_matrix_json", existing.get("outcomes_matrix", {}))
        alert_level = int(_pick("alert_level", "", existing.get("alert_level", 0)) or 0)
        max_alert = int(_pick("max_alert", "", existing.get("max_alert", 4)) or 4)
        rescue_shield_used = int(bool(_pick("rescue_shield_used", "", existing.get("rescue_shield_used", 0))))
        engaged_flag = int(bool(_pick("engaged_flag", "", existing.get("engaged_flag", 0))))
        burned_approaches = _pick("burned_approaches", "burned_approaches_json", existing.get("burned_approaches", {}))
        state_events = _pick("state_events", "state_events_json", existing.get("state_events", []))
        outcome_tier = str(_pick("outcome_tier", "", existing.get("outcome_tier", "")) or "")

        c.execute(
            """INSERT INTO quest_dossiers (
                session_id, quest_id, engine, family_tier, danger_tier, status_stage,
                compiled_at_turn, pitch_stub_json, cast_bindings_json, leads_graph_json,
                clue_graph_json, climax_spec_json, twist_spec_json, tangible_item_json,
                contract_economy_json, turn_in_rules_json, outcomes_matrix_json,
                alert_level, max_alert, rescue_shield_used, engaged_flag,
                burned_approaches_json, state_events_json, outcome_tier, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, quest_id) DO UPDATE SET
                engine = excluded.engine,
                family_tier = excluded.family_tier,
                danger_tier = excluded.danger_tier,
                status_stage = excluded.status_stage,
                compiled_at_turn = excluded.compiled_at_turn,
                pitch_stub_json = excluded.pitch_stub_json,
                cast_bindings_json = excluded.cast_bindings_json,
                leads_graph_json = excluded.leads_graph_json,
                clue_graph_json = excluded.clue_graph_json,
                climax_spec_json = excluded.climax_spec_json,
                twist_spec_json = excluded.twist_spec_json,
                tangible_item_json = excluded.tangible_item_json,
                contract_economy_json = excluded.contract_economy_json,
                turn_in_rules_json = excluded.turn_in_rules_json,
                outcomes_matrix_json = excluded.outcomes_matrix_json,
                alert_level = excluded.alert_level,
                max_alert = excluded.max_alert,
                rescue_shield_used = excluded.rescue_shield_used,
                engaged_flag = excluded.engaged_flag,
                burned_approaches_json = excluded.burned_approaches_json,
                state_events_json = excluded.state_events_json,
                outcome_tier = excluded.outcome_tier,
                updated_at = excluded.updated_at""",
            (
                session_id,
                str(qid),
                eff_engine,
                eff_family,
                danger_tier,
                status_stage,
                compiled_at_turn,
                _json_str(pitch_stub, "{}"),
                _json_str(cast_bindings, "{}"),
                _json_str(leads_graph, "[]"),
                _json_str(clue_graph, "[]"),
                _json_str(climax_spec, "{}"),
                _json_str(twist_spec, "{}"),
                _json_str(tangible_item, "{}"),
                _json_str(contract_economy, "{}"),
                _json_str(turn_in_rules, "{}"),
                _json_str(outcomes_matrix, "{}"),
                alert_level,
                max_alert,
                rescue_shield_used,
                engaged_flag,
                _json_str(burned_approaches, "{}"),
                _json_str(state_events, "[]"),
                outcome_tier,
                now,
                now,
            ),
        )
        return get_quest_dossier(session_id, str(qid), conn=c)

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def append_dossier_state_event(
    session_id: int,
    quest_id: str,
    turn: int,
    kind: str,
    prev: Any,
    next_: Any,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    now = time.time()
    event_entry = {"turn": int(turn), "kind": kind, "prev": prev, "next": next_}

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT state_events_json FROM quest_dossiers WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        if not row:
            return
        events = _deserialize_json_field(row["state_events_json"], [])
        events.append(event_entry)
        c.execute(
            "UPDATE quest_dossiers SET state_events_json = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
            (json.dumps(events), now, session_id, quest_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_quest_dossiers_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, int]:
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        dossiers_rolled = 0
        spines_rolled = 0

        d_rows = c.execute("SELECT * FROM quest_dossiers WHERE session_id = ?", (session_id,)).fetchall()
        for dr in d_rows:
            d = _enrich_dossier_dict(dr)
            if not d:
                continue
            qid = d["quest_id"]
            compiled_turn = int(d.get("compiled_at_turn") or 0)

            if compiled_turn > t_num:
                fam = str(d.get("family_tier") or "bounty").lower()
                if fam in ("rumor", "minor", "dispatch", "story"):
                    c.execute("DELETE FROM quest_dossiers WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    dossiers_rolled += 1
                else:
                    c.execute(
                        """UPDATE quest_dossiers
                           SET status_stage = 'pitch', compiled_at_turn = 0, alert_level = 0, rescue_shield_used = 0,
                               engaged_flag = 0, cast_bindings_json = '{}', leads_graph_json = '[]',
                               clue_graph_json = '[]', climax_spec_json = '{}', twist_spec_json = '{}',
                               tangible_item_json = '{}', contract_economy_json = '{}', turn_in_rules_json = '{}',
                               outcomes_matrix_json = '{}', burned_approaches_json = '{}', state_events_json = '[]',
                               outcome_tier = '', updated_at = ?
                           WHERE session_id = ? AND quest_id = ?""",
                        (now, session_id, qid),
                    )
                    c.execute(
                        "UPDATE quests SET status = 'Available', dossier_stage = 'pitch', updated_at = ? WHERE session_id = ? AND quest_id = ?",
                        (now, session_id, qid),
                    )
                    c.execute(
                        "DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ? AND stage_index >= 2",
                        (session_id, qid),
                    )
                    dossiers_rolled += 1
            else:
                events = list(d.get("state_events") or [])
                future_events = [e for e in events if int(e.get("turn", 0)) > t_num]
                surviving_events = [e for e in events if int(e.get("turn", 0)) <= t_num]
                if future_events:
                    alert_level = d["alert_level"]
                    rescue_shield = d["rescue_shield_used"]
                    engaged_flag = d["engaged_flag"]
                    burned_approaches = dict(d["burned_approaches"] or {})
                    leads_graph = list(d["leads_graph"] or [])
                    twist_spec = dict(d["twist_spec"] or {})
                    climax_spec = dict(d["climax_spec"] or {})
                    tangible_item = dict(d["tangible_item"] or {})
                    outcome_tier = str(d.get("outcome_tier") or "")

                    for ev in reversed(future_events):
                        k = str(ev.get("kind") or "")
                        prev_val = ev.get("prev")
                        if k in ("alert_level", "alert_bump"):
                            alert_level = int(prev_val or 0)
                        elif k == "rescue_shield_used":
                            rescue_shield = int(prev_val or 0)
                        elif k == "engaged_flag":
                            engaged_flag = int(prev_val or 0)
                        elif k == "burned_approaches":
                            burned_approaches = dict(prev_val or {})
                        elif k == "leads_graph":
                            leads_graph = list(prev_val or [])
                        elif k == "twist_spec":
                            twist_spec = dict(prev_val or {})
                        elif k == "climax_spec":
                            climax_spec = dict(prev_val or {})
                        elif k == "tangible_item":
                            tangible_item = dict(prev_val or {})
                        elif k == "outcome_tier":
                            outcome_tier = str(prev_val or "")
                        elif k == "quest_status" and prev_val:
                            c.execute(
                                "UPDATE quests SET status = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                (str(prev_val), now, session_id, qid),
                            )

                    c.execute(
                        """UPDATE quest_dossiers
                           SET alert_level = ?, rescue_shield_used = ?, engaged_flag = ?,
                               burned_approaches_json = ?, leads_graph_json = ?, twist_spec_json = ?,
                               climax_spec_json = ?, tangible_item_json = ?, outcome_tier = ?, state_events_json = ?, updated_at = ?
                           WHERE session_id = ? AND quest_id = ?""",
                        (
                            alert_level,
                            rescue_shield,
                            engaged_flag,
                            json.dumps(burned_approaches),
                            json.dumps(leads_graph),
                            json.dumps(twist_spec),
                            json.dumps(climax_spec),
                            json.dumps(tangible_item),
                            outcome_tier,
                            json.dumps(surviving_events),
                            now,
                            session_id,
                            qid,
                        ),
                    )
                    dossiers_rolled += 1

        s_row = c.execute("SELECT * FROM campaign_spines WHERE session_id = ?", (session_id,)).fetchone()
        if s_row:
            s = _enrich_spine_dict(s_row) or {}
            nemeses = list(s.get("nemeses") or [])
            surviving_nemeses = [n for n in nemeses if int(n.get("spawned_at_turn", 0)) <= t_num]

            spine_events = list(s.get("state_events") or [])
            future_s_events = [e for e in spine_events if int(e.get("turn", 0)) > t_num]
            surviving_s_events = [e for e in spine_events if int(e.get("turn", 0)) <= t_num]

            if len(surviving_nemeses) != len(nemeses) or future_s_events:
                climax_status = str(s.get("climax_status") or "pending")
                epilogue_status = str(s.get("epilogue_status") or "pending")
                lieutenants = list(s.get("lieutenants_roster") or [])
                for ev in reversed(future_s_events):
                    k = str(ev.get("kind") or "")
                    prev_val = ev.get("prev")
                    if k == "climax_status":
                        climax_status = str(prev_val or "pending")
                    elif k == "epilogue_status":
                        epilogue_status = str(prev_val or "pending")
                    elif k == "lieutenants_roster" and isinstance(prev_val, list):
                        lieutenants = list(prev_val)

                c.execute(
                    """UPDATE campaign_spines
                       SET nemeses_json = ?, lieutenants_roster_json = ?, climax_status = ?,
                           epilogue_status = ?, state_events_json = ?, updated_at = ?
                       WHERE session_id = ?""",
                    (
                        json.dumps(surviving_nemeses),
                        json.dumps(lieutenants),
                        climax_status,
                        epilogue_status,
                        json.dumps(surviving_s_events),
                        now,
                        session_id,
                    ),
                )
                spines_rolled += 1

        return {"dossiers_rolled_back": dossiers_rolled, "spines_rolled_back": spines_rolled}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


_FOLKLORE_STAGE_RANK = {
    "undiscovered": 0,
    "sighted": 1,
    "verified": 2,
    "contained": 3,
}


def get_session_participant_user_ids(
    session_id: int,
    extra_user_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[int]:
    """Returns deduplicated positive integer user_ids for the session host and active party members."""
    def _run(c: sqlite3.Connection) -> list[int]:
        uids: list[int] = []
        if extra_user_id and int(extra_user_id) > 0:
            uids.append(int(extra_user_id))
        if session_id:
            s_row = c.execute("SELECT host_user_id, turn_order FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if s_row and s_row["host_user_id"] and int(s_row["host_user_id"]) > 0:
                h_uid = int(s_row["host_user_id"])
                if h_uid not in uids:
                    uids.append(h_uid)
            # Co-op party members registered only via turn_order also receive account-wide codex credit
            raw_to = s_row["turn_order"] if s_row else None
            try:
                to_list = json.loads(raw_to) if isinstance(raw_to, str) and raw_to.strip() else (raw_to or [])
            except (TypeError, ValueError):
                to_list = []
            for t_uid in (to_list if isinstance(to_list, list) else []):
                try:
                    t_int = int(t_uid)
                except (TypeError, ValueError):
                    continue
                if t_int > 0 and t_int not in uids:
                    uids.append(t_int)
            try:
                m_rows = c.execute("SELECT user_id FROM session_members WHERE session_id = ?", (session_id,)).fetchall()
                for mr in m_rows:
                    m_uid = int(mr["user_id"] or 0)
                    if m_uid > 0 and m_uid not in uids:
                        uids.append(m_uid)
            except sqlite3.Error as exc:
                _log.debug("session_members lookup skipped for session %s: %s", session_id, exc)
        return uids

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_user_folklore_codex(
    user_id: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, dict[str, Any]]:
    """Returns account-wide Folklore Encyclopedia unlock rows keyed by `codex_id`."""
    if not user_id or int(user_id) <= 0:
        return {}

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        rows = c.execute(
            "SELECT * FROM user_folklore_codex WHERE user_id = ?",
            (int(user_id),),
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            cid = str(r["codex_id"] or "").strip()
            if cid:
                out[cid] = dict(r)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def record_folklore_codex_progress(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    stage: str = "sighted",
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """
    Monotonically advances account-wide Folklore Encyclopedia progress (`sighted` -> `verified` -> `contained`)
    for one or more `user_ids`. Persists permanently across playthroughs and rollbacks.
    """
    cid = str(codex_id or "").strip()
    norm_stage = str(stage or "sighted").strip().lower()
    if norm_stage not in ("sighted", "verified", "contained"):
        norm_stage = "sighted"
    if isinstance(user_ids, int):
        uid_list = [user_ids] if user_ids > 0 else []
    else:
        uid_list = [int(u) for u in (user_ids or []) if u and int(u) > 0]
    if not cid or not uid_list:
        return {"updated": False, "codex_id": cid, "stage": norm_stage}

    now = time.time()
    target_rank = _FOLKLORE_STAGE_RANK[norm_stage]

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        final_stage = norm_stage
        for uid in dict.fromkeys(uid_list):
            existing = c.execute(
                "SELECT * FROM user_folklore_codex WHERE user_id = ? AND codex_id = ?",
                (uid, cid),
            ).fetchone()
            if not existing:
                t_sight = 1
                t_cont = 1 if norm_stage == "contained" else 0
                c.execute(
                    """INSERT INTO user_folklore_codex (
                        user_id, codex_id, unlock_stage, times_sighted, times_contained,
                        first_discovered_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (uid, cid, norm_stage, t_sight, t_cont, now, now),
                )
            else:
                cur_stage = str(existing["unlock_stage"] or "sighted").strip().lower()
                cur_rank = _FOLKLORE_STAGE_RANK.get(cur_stage, 1)
                eff_stage = norm_stage if target_rank > cur_rank else cur_stage
                final_stage = eff_stage
                t_sight = int(existing["times_sighted"] or 1) + (1 if norm_stage == "sighted" else 0)
                t_cont = int(existing["times_contained"] or 0) + (1 if norm_stage == "contained" else 0)
                c.execute(
                    """UPDATE user_folklore_codex
                       SET unlock_stage = ?, times_sighted = ?, times_contained = ?, updated_at = ?
                       WHERE user_id = ? AND codex_id = ?""",
                    (eff_stage, t_sight, t_cont, now, uid, cid),
                )
        return {"updated": True, "codex_id": cid, "stage": final_stage}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def user_has_folklore_recognition(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Returns True if any user in `user_ids` has already reached `verified` or `contained`
    for `codex_id` in their account-wide Folklore Encyclopedia (granting -1 Stage 1 clue recognition).
    """
    cid = str(codex_id or "").strip()
    if isinstance(user_ids, int):
        uid_list = [user_ids] if user_ids > 0 else []
    else:
        uid_list = [int(u) for u in (user_ids or []) if u and int(u) > 0]
    if not cid or not uid_list:
        return False

    def _run(c: sqlite3.Connection) -> bool:
        uid_set = set(uid_list)
        rows = c.execute(
            "SELECT user_id, unlock_stage FROM user_folklore_codex WHERE codex_id = ?",
            (cid,),
        ).fetchall()
        for r in rows:
            if int(r["user_id"] or 0) not in uid_set:
                continue
            st = str(r["unlock_stage"] or "").strip().lower()
            if _FOLKLORE_STAGE_RANK.get(st, 0) >= 2:
                return True
        return False

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def _effective_session_turn(row: sqlite3.Row | dict[str, Any], explicit_turn: Optional[int] = None) -> int:
    """Resolves the active 1-based turn number, honoring an in-flight `pending` turn snapshot when mid-turn."""
    if explicit_turn is not None:
        return int(explicit_turn)
    raw_snap = row["last_turn_snapshot_json"] if "last_turn_snapshot_json" in row.keys() else None
    if raw_snap:
        snap = _deserialize_json_field(raw_snap, {})
        if isinstance(snap, dict) and snap.get("status") == "pending" and snap.get("target_turn") is not None:
            return int(snap["target_turn"])
    return int(row["turn_count"] or 0)


def record_session_anomaly_field_log(
    session_id: int,
    blueprint: dict[str, Any],
    stage: str = "sighted",
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
    *,
    location: str = "",
    resolution_method: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Records or advances a session-scoped Field Log entry inside `sessions.extra_json['anomaly_field_log']`
    with turn-stamped `stage_history` so mid-session turn rollbacks revert cleanly.
    """
    if not session_id or not isinstance(blueprint, dict):
        return {}
    norm_stage = str(stage or "sighted").strip().lower()
    if norm_stage not in ("sighted", "verified", "contained"):
        norm_stage = "sighted"
    bp_id = str(blueprint.get("blueprint_id") or blueprint.get("codex_id") or blueprint.get("name") or "").strip()
    if not bp_id:
        return {}

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        row = c.execute(
            "SELECT turn_count, extra_json, last_turn_snapshot_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return {}
        t_cur = _effective_session_turn(row, turn_number)
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}
        f_log = list(extra.get("anomaly_field_log") or [])
        existing_idx = next(
            (i for i, item in enumerate(f_log) if isinstance(item, dict) and item.get("blueprint_id") == bp_id),
            None,
        )
        codex_id = str(blueprint.get("codex_id") or "").strip()
        is_disguised = bool((blueprint.get("disguise_state") or {}).get("is_disguised")) and norm_stage == "sighted"
        pub_name = (
            str((blueprint.get("disguise_state") or {}).get("disguise_alias") or blueprint.get("name") or "Unknown Anomaly")
            if is_disguised
            else str(blueprint.get("canonical_name") or blueprint.get("name") or blueprint.get("entity_name") or "Unknown Anomaly")
        )

        if existing_idx is None:
            entry = {
                "blueprint_id": bp_id,
                "codex_id": codex_id,
                "is_canonical_folklore": bool(blueprint.get("is_canonical_folklore") or codex_id),
                "name": pub_name,
                "true_name": str(blueprint.get("canonical_name") or blueprint.get("name") or pub_name),
                "type": str(blueprint.get("type") or "entity"),
                "form": str(blueprint.get("form") or ""),
                "form_label": str(blueprint.get("form_label") or "Manifestation"),
                "tradition": str(blueprint.get("folklore_tradition") or "Procedural Anomaly"),
                "primary_element": str(blueprint.get("primary_element") or "aether"),
                "sensory_omen": str(blueprint.get("sensory_omen") or ""),
                "taboo_rule": str(blueprint.get("taboo_rule") or ""),
                "containment_protocol": str(blueprint.get("containment_protocol") or ""),
                "weaknesses": list(blueprint.get("weaknesses") or []),
                "resistances": list(blueprint.get("resistances") or []),
                "stage": norm_stage,
                "status": norm_stage,
                "is_disguised": is_disguised,
                "public_name": pub_name,
                "location": str(location or ""),
                "resolution_method": str(resolution_method or ""),
                "first_turn": t_cur,
                "turn_updated": t_cur,
                "stage_history": [
                    {
                        "turn": t_cur,
                        "stage": norm_stage,
                        "name": pub_name,
                        "public_name": pub_name,
                        "is_disguised": is_disguised,
                    }
                ],
            }
            f_log.append(entry)
        else:
            entry = dict(f_log[existing_idx])
            cur_rank = _FOLKLORE_STAGE_RANK.get(str(entry.get("stage") or "sighted"), 1)
            new_rank = _FOLKLORE_STAGE_RANK.get(norm_stage, 1)
            eff_stage = norm_stage if new_rank >= cur_rank else str(entry.get("stage") or "sighted")
            still_disguised = is_disguised and eff_stage == "sighted"
            if eff_stage in ("verified", "contained") or not still_disguised:
                entry["name"] = str(entry.get("true_name") or pub_name)
            entry["is_disguised"] = still_disguised
            entry["public_name"] = pub_name if still_disguised else entry["name"]
            entry["stage"] = eff_stage
            entry["status"] = eff_stage
            if location:
                entry["location"] = str(location)
            if resolution_method:
                entry["resolution_method"] = str(resolution_method)
            entry["turn_updated"] = t_cur
            hist = list(entry.get("stage_history") or [])
            hist.append(
                {
                    "turn": t_cur,
                    "stage": eff_stage,
                    "name": entry["name"],
                    "public_name": entry["public_name"],
                    "is_disguised": still_disguised,
                }
            )
            entry["stage_history"] = hist[-12:]
            f_log[existing_idx] = entry

        extra["anomaly_field_log"] = f_log
        c.execute(
            "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(extra), time.time(), session_id),
        )
        return entry

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def retire_or_cooldown_folklore_in_session(
    session_id: int,
    codex_id: str,
    uniqueness: str = "species",
    current_day: int = 1,
    cooldown_days: int = 4,
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Marks a `singular` Canonical Folklore entry as retired for the remainder of the session,
    or places a `species` entry onto a multi-day spawn cooldown in `sessions.extra_json`.
    """
    cid = str(codex_id or "").strip()
    if not session_id or not cid:
        return

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT turn_count, current_day, extra_json, last_turn_snapshot_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        t_cur = _effective_session_turn(row, turn_number)
        eff_day = int(current_day or row["current_day"] or 1)
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}

        if str(uniqueness or "species").strip().lower() == "singular":
            retired = list(extra.get("retired_folklore_ids") or [])
            if not any((isinstance(r, dict) and r.get("codex_id") == cid) or r == cid for r in retired):
                retired.append({"codex_id": cid, "turn_set": t_cur})
            extra["retired_folklore_ids"] = retired
        else:
            cooldowns = dict(extra.get("folklore_cooldowns") or {})
            prev_cd = cooldowns.get(cid) if isinstance(cooldowns.get(cid), dict) else {}
            prev_hist = list(prev_cd.get("history") or [])
            if prev_cd and "available_day" in prev_cd and not prev_hist:
                prev_hist.append(
                    {
                        "available_day": int(prev_cd["available_day"]),
                        "turn_set": int(prev_cd.get("turn_set", 0)),
                    }
                )
            new_avail = eff_day + max(1, int(cooldown_days or 4))
            prev_hist.append({"available_day": new_avail, "turn_set": t_cur})
            cooldowns[cid] = {
                "available_day": new_avail,
                "turn_set": t_cur,
                "history": prev_hist[-8:],
            }
            extra["folklore_cooldowns"] = cooldowns

        c.execute(
            "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(extra), time.time(), session_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_session_anomaly_logs_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, int]:
    """
    Reverts session-scoped `anomaly_field_log`, `retired_folklore_ids`, and `folklore_cooldowns`
    in `sessions.extra_json` for turns strictly greater than `turn_number`.
    Account-wide `user_folklore_codex` rows remain permanently unlocked.
    """
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row or not row["extra_json"]:
            return {"field_log_reverted": 0}
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            return {"field_log_reverted": 0}

        changed = 0
        if "anomaly_field_log" in extra and isinstance(extra["anomaly_field_log"], list):
            new_log = []
            for item in extra["anomaly_field_log"]:
                if not isinstance(item, dict):
                    continue
                if int(item.get("first_turn", 0)) > t_num:
                    changed += 1
                    continue
                hist = [h for h in (item.get("stage_history") or []) if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num]
                if hist:
                    upd = dict(item)
                    last_h = hist[-1]
                    restored_stage = last_h.get("stage", upd.get("stage", "sighted"))
                    restored_name = last_h.get("name", upd.get("name", ""))
                    restored_disg = bool(last_h.get("is_disguised", False)) if "is_disguised" in last_h else bool(upd.get("is_disguised") and restored_stage == "sighted")
                    if (
                        upd.get("stage") != restored_stage
                        or upd.get("status") != restored_stage
                        or upd.get("name") != restored_name
                        or bool(upd.get("is_disguised")) != restored_disg
                    ):
                        changed += 1
                    upd["stage"] = restored_stage
                    upd["status"] = restored_stage
                    upd["name"] = restored_name
                    upd["public_name"] = last_h.get("public_name", restored_name)
                    upd["is_disguised"] = restored_disg
                    upd["turn_updated"] = int(last_h.get("turn", upd.get("first_turn", 0)))
                    upd["stage_history"] = hist
                    new_log.append(upd)
                else:
                    new_log.append(item)
            extra["anomaly_field_log"] = new_log

        if "retired_folklore_ids" in extra and isinstance(extra["retired_folklore_ids"], list):
            orig_ret = extra["retired_folklore_ids"]
            surv_ret = [
                r for r in orig_ret
                if not (isinstance(r, dict) and int(r.get("turn_set", 0)) > t_num)
            ]
            if len(surv_ret) != len(orig_ret):
                changed += 1
                extra["retired_folklore_ids"] = surv_ret

        if "folklore_cooldowns" in extra and isinstance(extra["folklore_cooldowns"], dict):
            orig_cd = extra["folklore_cooldowns"]
            surv_cd: dict[str, Any] = {}
            cd_changed = False
            for k, v in orig_cd.items():
                if not isinstance(v, dict):
                    surv_cd[k] = v
                    continue
                cd_hist = [
                    h for h in (v.get("history") or [])
                    if isinstance(h, dict) and int(h.get("turn_set", 0)) <= t_num
                ]
                if v.get("history"):
                    if not cd_hist:
                        cd_changed = True
                        continue
                    last_cd = cd_hist[-1]
                    if int(v.get("turn_set", 0)) != int(last_cd.get("turn_set", 0)) or int(v.get("available_day", 0)) != int(last_cd.get("available_day", 0)):
                        cd_changed = True
                    surv_cd[k] = {
                        "available_day": int(last_cd["available_day"]),
                        "turn_set": int(last_cd["turn_set"]),
                        "history": cd_hist,
                    }
                elif int(v.get("turn_set", 0)) > t_num:
                    cd_changed = True
                else:
                    surv_cd[k] = v
            if cd_changed or len(surv_cd) != len(orig_cd):
                changed += 1
                extra["folklore_cooldowns"] = surv_cd

        for v_key in ("contained_anomalies_log", "anomalous_vault_log", "anomalous_vault_requisitions"):
            if v_key in extra and isinstance(extra[v_key], list):
                orig_v = extra[v_key]
                surv_v = [
                    v for v in orig_v
                    if not (isinstance(v, dict) and v.get("turn_captured") is not None and int(v.get("turn_captured", 0)) > t_num)
                ]
                if len(surv_v) != len(orig_v):
                    changed += 1
                    extra[v_key] = surv_v

        # Revert daily_incursions / daily_breaches resolved or spawned after t_num
        for inc_key in ("daily_incursions", "daily_breaches"):
            if inc_key in extra and isinstance(extra[inc_key], list):
                orig_len = len(extra[inc_key])
                # Purge dynamic incidents spawned on turns after t_num
                inc_list = [
                    inc for inc in extra[inc_key]
                    if not (isinstance(inc, dict) and inc.get("spawn_turn") and int(inc.get("spawn_turn", 0)) > t_num)
                ]
                if len(inc_list) != orig_len:
                    changed += 1
                for inc in inc_list:
                    if not isinstance(inc, dict):
                        continue
                    if inc.get("resolved") and int(inc.get("resolved_at_turn", 0)) > t_num:
                        inc["resolved"] = False
                        inc["agitated"] = False
                        inc.pop("resolved_at_turn", None)
                        inc.pop("killed_lethally", None)
                        inc.pop("dispersed_unsealed", None)
                        inc.pop("escaped", None)
                        changed += 1
                    if inc.get("dossier_revealed") and int(inc.get("revealed_at_turn", 0)) > t_num:
                        inc["dossier_revealed"] = False
                        inc.pop("revealed_at_turn", None)
                        if inc.get("original_entity_name"):
                            inc["entity_name"] = inc["original_entity_name"]
                            inc.pop("original_entity_name", None)
                        if isinstance(inc.get("anomaly_blueprint"), dict):
                            inc["anomaly_blueprint"]["dossier_revealed"] = False
                        changed += 1
                extra[inc_key] = inc_list

        # Revert anomalous_faction_state promotion rep changes after t_num
        if "anomalous_faction_state" in extra and isinstance(extra["anomalous_faction_state"], dict):
            afs = extra["anomalous_faction_state"]
            rep_hist = afs.get("rep_history")
            if isinstance(rep_hist, list) and rep_hist:
                surviving = [h for h in rep_hist if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num]
                if len(surviving) != len(rep_hist):
                    if surviving:
                        last_h = surviving[-1]
                        afs["promotion_rep"] = int(last_h.get("new_rep", 0) or 0)
                    else:
                        first_h = rep_hist[0]
                        afs["promotion_rep"] = int(first_h.get("old_rep", 0) or 0)
                    afs["rep_history"] = surviving
                    from mechanics.social.factions import get_anomalous_promotion_tier_info
                    t_info = get_anomalous_promotion_tier_info(afs["promotion_rep"])
                    if afs.get("faction_archetype_key") != "freelancer":
                        afs["promotion_tier"] = t_info["tier"]
                        afs["promotion_title"] = t_info["title"]
                    changed += 1

        if changed > 0:
            c.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(extra), time.time(), session_id),
            )
            if "anomalous_faction_state" in extra and isinstance(extra["anomalous_faction_state"], dict):
                afs = extra["anomalous_faction_state"]
                c.execute(
                    "UPDATE characters SET faction_rank = ?, faction_title = ? WHERE active_session_id = ?",
                    (int(afs.get("promotion_tier", 0) or 0), str(afs.get("promotion_title") or ""), session_id),
                )
        return {"field_log_reverted": changed}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)

