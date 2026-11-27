"""Campaign spine, quest dossier profile readers, and participant/turn resolution."""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from typing import Any, Optional

from ..core import get_conn

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
    d["hidden_bible"] = _deserialize_json_field(d.get("hidden_bible_json"), {})
    d["ending_axes"] = _deserialize_json_field(d.get("ending_axes_json"), {})
    d["chronicle_tapestry"] = _deserialize_json_field(d.get("chronicle_tapestry_json"), {})
    d["state_events"] = _deserialize_json_field(d.get("state_events_json"), [])
    return d


def normalize_clue_graph_nodes(clue_graph: Any, quest_id: str = "") -> list[dict[str, Any]]:
    """Ensure every clue_graph node carries normalized `corroboration_group` and `clue_tier` metadata."""
    if isinstance(clue_graph, dict):
        raw_nodes = (
            clue_graph.get("nodes")
            if isinstance(clue_graph.get("nodes"), (list, tuple))
            else list(clue_graph.values())
        )
    elif isinstance(clue_graph, (list, tuple)):
        raw_nodes = list(clue_graph)
    else:
        return []

    out: list[dict[str, Any]] = []
    q_str = str(quest_id or "")
    for item in raw_nodes:
        if not isinstance(item, dict):
            continue
        node = dict(item)
        if not str(node.get("corroboration_group") or "").strip():
            node["corroboration_group"] = str(node.get("quest_id") or q_str)
        existing_tier = str(node.get("clue_tier") or "").strip().lower()
        if bool(node.get("is_red_herring")):
            node["clue_tier"] = "red_herring"
        elif existing_tier in ("red_herring", "key_clue", "corroborating"):
            node["clue_tier"] = existing_tier
        else:
            ck = str(node.get("clue_key") or node.get("key_clue_id") or "").upper()
            is_opt_or_bonus = (
                bool(node.get("is_optional"))
                or bool(node.get("is_bonus"))
                or "BONUS" in ck
                or "_CLUE_" in ck
                or "_OPTIONAL" in ck
            )
            if ("-KC-" in ck or ck.startswith("KC-") or bool(node.get("is_key_clue"))) and not is_opt_or_bonus:
                node["clue_tier"] = "key_clue"
            else:
                node["clue_tier"] = "corroborating"
        out.append(node)
    return out


def _enrich_dossier_dict(row: sqlite3.Row | dict | None) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["pitch_stub"] = _deserialize_json_field(d.get("pitch_stub_json"), {})
    d["pitch_card"] = d["pitch_stub"]
    d["cast_bindings"] = _deserialize_json_field(d.get("cast_bindings_json"), {})
    d["leads_graph"] = _deserialize_json_field(d.get("leads_graph_json"), [])
    d["clue_graph"] = normalize_clue_graph_nodes(
        _deserialize_json_field(d.get("clue_graph_json"), []),
        str(d.get("quest_id") or ""),
    )
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
        hidden_bible = _pick("hidden_bible", "hidden_bible_json", "", existing.get("hidden_bible", {}))
        ending_axes = _pick("ending_axes", "ending_axes_json", "", existing.get("ending_axes", {}))
        chronicle_tapestry = _pick("chronicle_tapestry", "chronicle_tapestry_json", "", existing.get("chronicle_tapestry", {}))
        climax_status = str(_pick("climax_status", "", "", existing.get("climax_status", "pending")) or "pending")
        epilogue_status = str(_pick("epilogue_status", "", "", existing.get("epilogue_status", "pending")) or "pending")
        state_events = _pick("state_events", "state_events_json", "", existing.get("state_events", []))

        c.execute(
            """INSERT INTO campaign_spines (
                session_id, scenario, mastermind_profile_json, lieutenants_roster_json,
                chapters_blueprint_json, nemeses_json, hidden_bible_json, ending_axes_json,
                chronicle_tapestry_json, climax_status, epilogue_status,
                state_events_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                scenario = excluded.scenario,
                mastermind_profile_json = excluded.mastermind_profile_json,
                lieutenants_roster_json = excluded.lieutenants_roster_json,
                chapters_blueprint_json = excluded.chapters_blueprint_json,
                nemeses_json = excluded.nemeses_json,
                hidden_bible_json = excluded.hidden_bible_json,
                ending_axes_json = excluded.ending_axes_json,
                chronicle_tapestry_json = excluded.chronicle_tapestry_json,
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
                _json_str(hidden_bible, "{}"),
                _json_str(ending_axes, "{}"),
                _json_str(chronicle_tapestry, "{}"),
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


def get_prewarmed_quest_dossier(
    session_id: int,
    chapter: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict | None:
    def _run(c: sqlite3.Connection) -> dict | None:
        rows = c.execute(
            "SELECT * FROM quest_dossiers WHERE session_id = ? AND status_stage = 'prewarmed' ORDER BY id DESC",
            (session_id,),
        ).fetchall()
        for r in rows:
            dos = _enrich_dossier_dict(r)
            if dos and int(dos.get("chapter") or (dos.get("climax_spec") or {}).get("chapter") or 0) == chapter:
                return dos
        return None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def promote_prewarmed_dossier(
    session_id: int,
    quest_id: str,
    conn: Optional[sqlite3.Connection] = None,
    turn_number: Optional[int] = None,
) -> dict | None:
    def _run(c: sqlite3.Connection) -> dict | None:
        if turn_number is not None:
            c.execute(
                "UPDATE quest_dossiers SET status_stage = 'compiled', compiled_at_turn = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                (int(turn_number), time.time(), session_id, quest_id),
            )
        else:
            c.execute(
                "UPDATE quest_dossiers SET status_stage = 'compiled', updated_at = ? WHERE session_id = ? AND quest_id = ?",
                (time.time(), session_id, quest_id),
            )
        row = c.execute(
            "SELECT * FROM quest_dossiers WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        return _enrich_dossier_dict(row)

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


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


def get_effective_session_turn(
    session_id: Optional[int],
    sess: Optional[dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Public repository helper returning the effective turn number for `session_id` (or `sess`)."""
    if isinstance(sess, dict) and sess.get("_target_turn") is not None:
        return int(sess["_target_turn"])
    if session_id:
        def _run(c: sqlite3.Connection) -> Optional[int]:
            row = c.execute(
                "SELECT turn_count, last_turn_snapshot_json FROM sessions WHERE id = ?",
                (int(session_id),),
            ).fetchone()
            return _effective_session_turn(row, None) if row else None

        try:
            res = _run(conn) if conn is not None else None
            if res is None and conn is None:
                with get_conn() as c:
                    res = _run(c)
            if res is not None:
                return res
        except Exception:
            pass
    return int((sess or {}).get("turn_count", 0) or 0)
