from __future__ import annotations

import copy
import json
import logging
import sqlite3
import time
from typing import Any, Optional, Sequence

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
) -> dict | None:
    def _run(c: sqlite3.Connection) -> dict | None:
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


_TRACKED_DOSSIER_STATE_FIELDS = (
    "alert_level",
    "rescue_shield_used",
    "engaged_flag",
    "burned_approaches",
    "leads_graph",
    "clue_graph",
    "climax_spec",
    "twist_spec",
    "tangible_item",
    "outcome_tier",
)


def _merge_dedup_state_event(
    events: list[dict[str, Any]],
    turn: int,
    kind: str,
    prev: Any,
    next_: Any,
) -> list[dict[str, Any]]:
    """Insert or coalesce a `(turn, kind)` event, keeping initial `prev` and dropping no-ops."""
    t_int = int(turn)
    k_str = str(kind)
    out = [dict(e) for e in (events or []) if isinstance(e, dict)]
    for idx in range(len(out) - 1, -1, -1):
        ev = out[idx]
        if int(ev.get("turn", -1)) == t_int and str(ev.get("kind") or "") == k_str:
            orig_prev = ev.get("prev")
            if orig_prev == next_:
                del out[idx]
            else:
                out[idx] = {
                    "turn": t_int,
                    "kind": k_str,
                    "prev": orig_prev,
                    "next": copy.deepcopy(next_),
                }
            return out
    if prev != next_:
        out.append(
            {
                "turn": t_int,
                "kind": k_str,
                "prev": copy.deepcopy(prev),
                "next": copy.deepcopy(next_),
            }
        )
    return out


def _rebase_climax_snapshot(snap: Any, new_climax: Any) -> Any:
    if not isinstance(snap, dict) or not isinstance(new_climax, dict):
        return snap
    out = copy.deepcopy(snap)
    for top_key in ("main_objective_text", "title", "objective"):
        if new_climax.get(top_key):
            out[top_key] = new_climax[top_key]
    new_stages = {
        int(s.get("stage_index", idx + 1)): s
        for idx, s in enumerate(new_climax.get("main_stages") or [])
        if isinstance(s, dict)
    }
    snap_stages = out.get("main_stages")
    if isinstance(snap_stages, list):
        for idx, st in enumerate(snap_stages):
            if not isinstance(st, dict):
                continue
            s_idx = int(st.get("stage_index", idx + 1))
            src_st = new_stages.get(s_idx)
            if not src_st or st.get("completed") or str(st.get("status") or "").lower() == "completed":
                continue
            for field in (
                "stage_label",
                "label",
                "beat_contract",
                "target_location",
                "target_npc",
                "key_clue",
                "clue_sources",
            ):
                if field in src_st and src_st[field] is not None:
                    st[field] = copy.deepcopy(src_st[field])
    return out


def _rebase_clue_graph_snapshot(snap: Any, new_cg: Any) -> Any:
    if not isinstance(snap, list) or not isinstance(new_cg, list):
        return snap
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(new_cg):
        if isinstance(raw, dict):
            ck = str(raw.get("clue_key") or raw.get("clue_id") or idx)
            by_key[ck] = raw
    seen: set[str] = set()
    for idx, raw in enumerate(snap):
        if not isinstance(raw, dict):
            continue
        node = copy.deepcopy(raw)
        ck = str(node.get("clue_key") or node.get("clue_id") or idx)
        seen.add(ck)
        src = by_key.get(ck)
        if src:
            for field in (
                "title",
                "lead_text",
                "description",
                "location",
                "clue_tier",
                "corroboration_group",
                "stage_index",
                "is_optional",
                "is_red_herring",
            ):
                if field in src and src[field] is not None:
                    node[field] = copy.deepcopy(src[field])
        out.append(node)
    for idx, raw in enumerate(new_cg):
        if not isinstance(raw, dict):
            continue
        ck = str(raw.get("clue_key") or raw.get("clue_id") or idx)
        if ck not in seen:
            add_node = copy.deepcopy(raw)
            add_node["discovered"] = False
            add_node["checked"] = False
            out.append(add_node)
    return out


def _rebase_leads_graph_snapshot(snap: Any, new_lg: Any) -> Any:
    if not isinstance(snap, list) or not isinstance(new_lg, list):
        return snap
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(new_lg):
        if isinstance(raw, dict):
            lk = str(raw.get("lead_id") or raw.get("hook_id") or raw.get("id") or idx)
            by_key[lk] = raw
    seen: set[str] = set()
    for idx, raw in enumerate(snap):
        if not isinstance(raw, dict):
            continue
        lead = copy.deepcopy(raw)
        lk = str(lead.get("lead_id") or lead.get("hook_id") or lead.get("id") or idx)
        seen.add(lk)
        src = by_key.get(lk)
        if (
            src
            and not lead.get("engaged")
            and not lead.get("completed")
            and str(lead.get("status") or "").lower() not in ("completed", "resolved", "failed")
        ):
            for k, v in src.items():
                if k not in ("engaged", "completed", "status", "checked"):
                    lead[k] = copy.deepcopy(v)
        out.append(lead)
    for idx, raw in enumerate(new_lg):
        if not isinstance(raw, dict):
            continue
        lk = str(raw.get("lead_id") or raw.get("hook_id") or raw.get("id") or idx)
        if lk not in seen:
            out.append(copy.deepcopy(raw))
    return out


def upsert_quest_dossier(
    session_id: int,
    quest_id_or_dict: str | dict = "",
    engine: Optional[str] = None,
    family_tier: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    *,
    auto_state_events: bool = True,
    turn_number: Optional[int] = None,
    is_baseline_enrichment: bool = False,
    sync_projection: bool = False,
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
        state_events_raw = _pick("state_events", "state_events_json", existing.get("state_events", []))
        state_events = (
            list(state_events_raw)
            if isinstance(state_events_raw, (list, tuple))
            else _deserialize_json_field(state_events_raw, [])
        )
        outcome_tier = str(_pick("outcome_tier", "", existing.get("outcome_tier", "")) or "")
        if isinstance(clue_graph, (list, tuple, dict)):
            clue_graph = normalize_clue_graph_nodes(clue_graph, str(qid))

        explicit_state_events = (
            ("state_events" in kwargs and kwargs["state_events"] is not None)
            or ("state_events_json" in kwargs and kwargs["state_events_json"] is not None)
            or ("state_events" in src and src["state_events"] is not None)
            or ("state_events_json" in src and src["state_events_json"] is not None)
        )
        if existing:
            if is_baseline_enrichment:
                rebased_events: list[dict[str, Any]] = []
                for ev in state_events:
                    if not isinstance(ev, dict):
                        continue
                    ev_copy = dict(ev)
                    ek = str(ev_copy.get("kind") or "")
                    if ek == "climax_spec":
                        ev_copy["prev"] = _rebase_climax_snapshot(ev_copy.get("prev"), climax_spec)
                        ev_copy["next"] = _rebase_climax_snapshot(ev_copy.get("next"), climax_spec)
                    elif ek == "clue_graph":
                        ev_copy["prev"] = _rebase_clue_graph_snapshot(ev_copy.get("prev"), clue_graph)
                        ev_copy["next"] = _rebase_clue_graph_snapshot(ev_copy.get("next"), clue_graph)
                    elif ek == "leads_graph":
                        ev_copy["prev"] = _rebase_leads_graph_snapshot(ev_copy.get("prev"), leads_graph)
                        ev_copy["next"] = _rebase_leads_graph_snapshot(ev_copy.get("next"), leads_graph)
                    rebased_events.append(ev_copy)
                state_events = rebased_events
            elif (
                auto_state_events
                and not explicit_state_events
                and str(existing.get("status_stage") or "") == "compiled"
                and status_stage == "compiled"
            ):
                eff_turn = (
                    int(turn_number)
                    if turn_number is not None
                    else int(get_effective_session_turn(session_id, conn=c))
                )
                new_values = {
                    "alert_level": alert_level,
                    "rescue_shield_used": rescue_shield_used,
                    "engaged_flag": engaged_flag,
                    "burned_approaches": burned_approaches,
                    "leads_graph": leads_graph,
                    "clue_graph": clue_graph,
                    "climax_spec": climax_spec,
                    "twist_spec": twist_spec,
                    "tangible_item": tangible_item,
                    "outcome_tier": outcome_tier,
                }
                for fk in _TRACKED_DOSSIER_STATE_FIELDS:
                    old_v = existing.get(fk)
                    new_v = new_values[fk]
                    if fk in ("alert_level", "rescue_shield_used", "engaged_flag"):
                        old_v = int(old_v or 0)
                    elif fk == "outcome_tier":
                        old_v = str(old_v or "")
                    if old_v == new_v:
                        continue
                    if turn_number is None:
                        same_kind = [
                            e for e in state_events if isinstance(e, dict) and str(e.get("kind") or "") == fk
                        ]
                        last_turn_val = same_kind[-1].get("turn") if same_kind else None
                        if (
                            same_kind
                            and int(last_turn_val if last_turn_val is not None else -1) == eff_turn
                            and same_kind[-1].get("prev") == old_v
                            and same_kind[-1].get("next") == new_v
                        ):
                            continue
                    state_events = _merge_dedup_state_event(state_events, eff_turn, fk, old_v, new_v)

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
        saved = get_quest_dossier(session_id, str(qid), conn=c)
        if sync_projection and saved is not None:
            from .quests import sync_quest_projection_from_dossier

            sync_quest_projection_from_dossier(session_id, str(qid), dossier=saved, conn=c)
        return saved

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

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT state_events_json FROM quest_dossiers WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        if not row:
            return
        events = _deserialize_json_field(row["state_events_json"], [])
        events = _merge_dedup_state_event(events, int(turn), kind, prev, next_)
        c.execute(
            "UPDATE quest_dossiers SET state_events_json = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
            (json.dumps(events), now, session_id, quest_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def append_spine_state_event(
    session_id: int,
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
            "SELECT state_events_json FROM campaign_spines WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        events = _deserialize_json_field(row["state_events_json"], [])
        events.append(event_entry)
        c.execute(
            "UPDATE campaign_spines SET state_events_json = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(events), now, session_id),
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

            fam = str(d.get("family_tier") or "bounty").lower()
            climax_cur = d.get("climax_spec") or {}
            pitch_cur = d.get("pitch_stub") or {}
            chap_num = int(
                climax_cur.get("chapter")
                or pitch_cur.get("chapter")
                or 1
            )
            is_ch1_story = fam == "story" and chap_num <= 1

            if compiled_turn > t_num and not is_ch1_story:
                if fam in ("rumor", "minor", "dispatch", "story"):
                    c.execute("DELETE FROM quest_dossiers WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM session_clues WHERE session_id = ? AND quest_id = ?", (session_id, qid))
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
                        "UPDATE quests SET status = 'Available', dossier_stage = 'pitch', sub_objectives_json = '[]', updated_at = ? WHERE session_id = ? AND quest_id = ?",
                        (now, session_id, qid),
                    )
                    c.execute(
                        "DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ? AND (stage_index >= 2 OR sub_obj_id > 0)",
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
                    raw_cg_r = d.get("clue_graph")
                    if isinstance(raw_cg_r, dict):
                        cg_items_r = raw_cg_r.get("nodes") if isinstance(raw_cg_r.get("nodes"), (list, tuple)) else list(raw_cg_r.values())
                        clue_graph = [n for n in cg_items_r if isinstance(n, dict)]
                    elif isinstance(raw_cg_r, (list, tuple)):
                        clue_graph = list(raw_cg_r)
                    else:
                        clue_graph = []
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
                        elif k == "clue_graph":
                            clue_graph = list(prev_val or [])
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
                               climax_spec_json = ?, tangible_item_json = ?, clue_graph_json = ?,
                               outcome_tier = ?, state_events_json = ?, updated_at = ?
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
                            json.dumps(clue_graph),
                            outcome_tier,
                            json.dumps(surviving_events),
                            now,
                            session_id,
                            qid,
                        ),
                    )
                    from .quests import sync_quest_projection_from_dossier

                    sync_quest_projection_from_dossier(session_id, qid, conn=c, is_rollback=True)
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
                chapters_bp = dict(s.get("chapters_blueprint") or {})
                ending_axes = dict(s.get("ending_axes") or {})
                chronicle_tapestry = dict(s.get("chronicle_tapestry") or {})
                mastermind_profile = dict(s.get("mastermind_profile") or {})
                for ev in reversed(future_s_events):
                    k = str(ev.get("kind") or "")
                    prev_val = ev.get("prev")
                    if k == "climax_status":
                        climax_status = str(prev_val or "pending")
                    elif k == "epilogue_status":
                        epilogue_status = str(prev_val or "pending")
                    elif k == "lieutenants_roster" and isinstance(prev_val, list):
                        lieutenants = list(prev_val)
                    elif k == "chapters_blueprint" and isinstance(prev_val, dict):
                        chapters_bp = dict(prev_val)
                    elif k == "ending_axes" and isinstance(prev_val, dict):
                        ending_axes = dict(prev_val)
                    elif k == "chronicle_tapestry" and isinstance(prev_val, dict):
                        chronicle_tapestry = dict(prev_val)
                    elif k == "mastermind_profile" and isinstance(prev_val, dict):
                        mastermind_profile = dict(prev_val)

                c.execute(
                    """UPDATE campaign_spines
                       SET mastermind_profile_json = ?, nemeses_json = ?, lieutenants_roster_json = ?, chapters_blueprint_json = ?,
                           ending_axes_json = ?, chronicle_tapestry_json = ?,
                           climax_status = ?, epilogue_status = ?, state_events_json = ?, updated_at = ?
                       WHERE session_id = ?""",
                    (
                        json.dumps(mastermind_profile),
                        json.dumps(surviving_nemeses),
                        json.dumps(lieutenants),
                        json.dumps(chapters_bp),
                        json.dumps(ending_axes),
                        json.dumps(chronicle_tapestry),
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


def get_users_folklore_codex_batch(
    user_ids: Sequence[int],
    conn: Optional[sqlite3.Connection] = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    """Returns account-wide Folklore Encyclopedia unlock rows for multiple users in a single `WHERE user_id IN (...)` query."""
    uniq_uids: list[int] = []
    seen_u: set[int] = set()
    for u in (user_ids or ()):
        try:
            uid_val = int(u)
        except (TypeError, ValueError):
            continue
        if uid_val > 0 and uid_val not in seen_u:
            seen_u.add(uid_val)
            uniq_uids.append(uid_val)
    if not uniq_uids:
        return {}

    def _run(c: sqlite3.Connection) -> dict[int, dict[str, dict[str, Any]]]:
        out: dict[int, dict[str, dict[str, Any]]] = {uid: {} for uid in uniq_uids}
        placeholders = ",".join("?" for _ in uniq_uids)
        rows = c.execute(
            f"SELECT * FROM user_folklore_codex WHERE user_id IN ({placeholders})",
            tuple(uniq_uids),
        ).fetchall()
        for r in rows:
            uid_r = int(r["user_id"] or 0)
            cid = str(r["codex_id"] or "").strip()
            if uid_r in out and cid:
                out[uid_r][cid] = dict(r)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def record_folklore_codex_progress(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    stage: str = "sighted",
    session_id: Optional[int] = None,
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """
    Monotonically advances account-wide Folklore Encyclopedia progress (`sighted` -> `verified` -> `contained`)
    for one or more `user_ids`. Persists permanently across playthroughs and rollbacks, while recording
    first-sighting session/turn provenance so rewound future sightings in the same session do not leak `-1` clue bonuses.
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

    def _resolve_uid_session_turn(c: sqlite3.Connection, uid: int) -> tuple[Optional[int], int]:
        sid_val = int(session_id) if session_id else None
        if not sid_val:
            ch_row = c.execute(
                "SELECT active_session_id FROM characters WHERE user_id = ? AND is_active = 1 LIMIT 1",
                (uid,),
            ).fetchone()
            if ch_row and ch_row["active_session_id"]:
                sid_val = int(ch_row["active_session_id"])
        if turn_number is not None:
            return sid_val, int(turn_number)
        if sid_val:
            s_row = c.execute(
                "SELECT turn_count, last_turn_snapshot_json FROM sessions WHERE id = ?",
                (sid_val,),
            ).fetchone()
            if s_row:
                return sid_val, _effective_session_turn(s_row)
        return sid_val, 0

    def _stamp_session_sighting_meta(
        c: sqlite3.Connection,
        sid_val: Optional[int],
        uid: int,
        first_t: int,
        verified_t: Optional[int],
    ) -> None:
        if not sid_val:
            return
        s_row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid_val,)).fetchone()
        if not s_row:
            return
        extra = _deserialize_json_field(s_row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}
        fs_map = dict(extra.get("_codex_first_sightings") or {})
        key = f"{uid}:{cid}"
        prev = dict(fs_map.get(key) or {})
        entry: dict[str, Any] = {
            "first_turn": int(prev["first_turn"]) if prev.get("first_turn") is not None else int(first_t),
        }
        if prev.get("verified_turn") is not None:
            entry["verified_turn"] = int(prev["verified_turn"])
        elif verified_t is not None:
            entry["verified_turn"] = int(verified_t)
        fs_map[key] = entry
        extra["_codex_first_sightings"] = fs_map
        c.execute(
            "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(extra), now, sid_val),
        )

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        col_names = {r["name"] for r in c.execute("PRAGMA table_info(user_folklore_codex)").fetchall()}
        has_prov_cols = "first_session_id" in col_names and "first_turn" in col_names
        final_stage = norm_stage
        for uid in dict.fromkeys(uid_list):
            existing = c.execute(
                "SELECT * FROM user_folklore_codex WHERE user_id = ? AND codex_id = ?",
                (uid, cid),
            ).fetchone()
            sid_eff, t_eff = _resolve_uid_session_turn(c, uid)
            if not existing:
                t_sight = 1
                t_cont = 1 if norm_stage == "contained" else 0
                if has_prov_cols:
                    c.execute(
                        """INSERT INTO user_folklore_codex (
                            user_id, codex_id, unlock_stage, times_sighted, times_contained,
                            first_discovered_at, updated_at, first_session_id, first_turn
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uid, cid, norm_stage, t_sight, t_cont, now, now, sid_eff, t_eff),
                    )
                else:
                    c.execute(
                        """INSERT INTO user_folklore_codex (
                            user_id, codex_id, unlock_stage, times_sighted, times_contained,
                            first_discovered_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (uid, cid, norm_stage, t_sight, t_cont, now, now),
                    )
                _stamp_session_sighting_meta(
                    c,
                    sid_eff,
                    uid,
                    first_t=t_eff,
                    verified_t=t_eff if target_rank >= 2 else None,
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
                if t_sight <= 1 and cur_rank < 2 and target_rank >= 2:
                    _stamp_session_sighting_meta(
                        c,
                        sid_eff,
                        uid,
                        first_t=int(existing["first_turn"]) if (has_prov_cols and existing["first_turn"] is not None) else t_eff,
                        verified_t=t_eff,
                    )
        return {"updated": True, "codex_id": cid, "stage": final_stage}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def user_has_folklore_recognition(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    session_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Returns True if any user in `user_ids` has already reached `verified` or `contained`
    for `codex_id` in their account-wide Folklore Encyclopedia (granting -1 Stage 1 clue recognition),
    excluding single-sighting unlocks whose first discovery occurred on a later rewound turn of the same session.
    """
    cid = str(codex_id or "").strip()
    if isinstance(user_ids, int):
        uid_list = [user_ids] if user_ids > 0 else []
    else:
        uid_list = [int(u) for u in (user_ids or []) if u and int(u) > 0]
    if not cid or not uid_list:
        return False

    def _run(c: sqlite3.Connection) -> bool:
        uniq_uids = list(dict.fromkeys(uid_list))
        placeholders = ",".join("?" for _ in uniq_uids)
        rows = c.execute(
            f"SELECT * FROM user_folklore_codex WHERE user_id IN ({placeholders}) AND codex_id = ?",
            (*uniq_uids, cid),
        ).fetchall()
        for r in rows:
            uid = int(r["user_id"] or 0)
            st = str(r["unlock_stage"] or "").strip().lower()
            if _FOLKLORE_STAGE_RANK.get(st, 0) < 2:
                continue
            t_sight = int(r["times_sighted"] or 0)
            if t_sight > 1:
                return True

            # Single-sighting check: gate bonus if first sighted/verified on a later rewound turn of this session
            check_sid = int(session_id) if session_id else None
            if not check_sid:
                ch_row = c.execute(
                    "SELECT active_session_id FROM characters WHERE user_id = ? AND is_active = 1 LIMIT 1",
                    (uid,),
                ).fetchone()
                if ch_row and ch_row["active_session_id"]:
                    check_sid = int(ch_row["active_session_id"])

            if check_sid:
                s_row = c.execute(
                    "SELECT turn_count, last_turn_snapshot_json, extra_json FROM sessions WHERE id = ?",
                    (check_sid,),
                ).fetchone()
                if s_row:
                    cur_t = _effective_session_turn(s_row)
                    s_extra = _deserialize_json_field(s_row["extra_json"], {})
                    origin_sids: set[int] = {int(check_sid)}
                    if isinstance(s_extra, dict):
                        for _osid in (s_extra.get("_origin_session_ids") or []):
                            try:
                                origin_sids.add(int(_osid))
                            except (TypeError, ValueError):
                                pass
                    r_keys = set(r.keys())
                    if "first_session_id" in r_keys and "first_turn" in r_keys:
                        f_sid = r["first_session_id"]
                        f_turn = r["first_turn"]
                        if f_sid is not None and int(f_sid) in origin_sids and f_turn is not None and int(f_turn) > cur_t:
                            continue
                    if isinstance(s_extra, dict):
                        fs_meta = (s_extra.get("_codex_first_sightings") or {}).get(f"{uid}:{cid}")
                        if isinstance(fs_meta, dict):
                            if fs_meta.get("first_turn") is not None and int(fs_meta["first_turn"]) > cur_t:
                                continue
                            if fs_meta.get("verified_turn") is not None and int(fs_meta["verified_turn"]) > cur_t:
                                continue
                        rw_turns = s_extra.get("_rewound_codex_first_turns") or {}
                        if cid in rw_turns and int(rw_turns[cid] or 0) > cur_t:
                            continue
                        rel_fl_rows = []
                        try:
                            rel_fl_rows = c.execute(
                                "SELECT stage FROM session_anomaly_records WHERE session_id = ? AND record_type = 'field_log' AND codex_id = ?",
                                (check_sid, cid),
                            ).fetchall()
                        except sqlite3.OperationalError:
                            rel_fl_rows = []
                        if rel_fl_rows:
                            max_fl_rank = max(
                                (_FOLKLORE_STAGE_RANK.get(str(rr["stage"] or "sighted").strip().lower(), 0) for rr in rel_fl_rows),
                                default=0,
                            )
                            if max_fl_rank < 2 and (
                                ("first_session_id" in r_keys and r["first_session_id"] is not None and int(r["first_session_id"]) in origin_sids)
                                or isinstance(fs_meta, dict)
                            ):
                                continue
                            return True
                        matching_leg_fl = [
                            fl_it for fl_it in (s_extra.get("anomaly_field_log") or [])
                            if isinstance(fl_it, dict) and str(fl_it.get("codex_id") or "") == cid
                        ]
                        if matching_leg_fl:
                            max_leg_rank = max(
                                (_FOLKLORE_STAGE_RANK.get(str(fl_it.get("stage") or "sighted").strip().lower(), 0) for fl_it in matching_leg_fl),
                                default=0,
                            )
                            if max_leg_rank < 2 and (
                                ("first_session_id" in r_keys and r["first_session_id"] is not None and int(r["first_session_id"]) in origin_sids)
                                or isinstance(fs_meta, dict)
                            ):
                                continue
                        return True
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


SESSION_ANOMALY_KEY_TO_RECORD_TYPE: dict[str, str] = {
    "anomaly_field_log": "field_log",
    "anomalous_vault_requisitions": "vault_requisition",
    "anomalous_vault_log": "vault_log",
    "contained_anomalies_log": "contained_log",
}
_RECORD_TYPE_TO_SESSION_ANOMALY_KEY: dict[str, str] = {
    v: k for k, v in SESSION_ANOMALY_KEY_TO_RECORD_TYPE.items()
}


def _extract_anomaly_record_columns(record_type: str, item: dict[str, Any]) -> tuple[str, str, str, int, int, str]:
    """Derives `(entity_key, codex_id, stage, first_turn, turn_updated, payload_json)` for a `session_anomaly_records` row."""
    if record_type == "field_log":
        entity_key = str(item.get("blueprint_id") or item.get("codex_id") or item.get("name") or "").strip()
    else:
        entity_key = str(
            item.get("blueprint_id")
            or item.get("requisition_id")
            or item.get("item_id")
            or item.get("codex_id")
            or item.get("name")
            or ""
        ).strip()
    codex_id = str(item.get("codex_id") or "").strip()
    default_stage = "contained" if record_type == "contained_log" else "sighted"
    stage = str(item.get("stage") or item.get("status") or default_stage).strip().lower() or default_stage
    first_turn = 0
    for tk in ("first_turn", "turn_captured", "turn"):
        if item.get(tk) is not None:
            try:
                first_turn = int(item[tk])
                break
            except (TypeError, ValueError):
                continue
    turn_updated = first_turn
    if item.get("turn_updated") is not None:
        try:
            turn_updated = int(item["turn_updated"])
        except (TypeError, ValueError):
            turn_updated = first_turn
    payload_json = json.dumps(item, default=str)
    return entity_key, codex_id, stage, first_turn, turn_updated, payload_json


def get_session_anomaly_records(
    session_id: int,
    record_type: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """Returns deserialized `payload_json` dicts for `session_id` (optionally filtered by `record_type`) ordered by insertion."""
    if not session_id:
        return []

    def _run(c: sqlite3.Connection) -> list[dict[str, Any]]:
        try:
            if record_type:
                rows = c.execute(
                    "SELECT payload_json FROM session_anomaly_records WHERE session_id = ? AND record_type = ? ORDER BY id ASC",
                    (int(session_id), str(record_type)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT payload_json FROM session_anomaly_records WHERE session_id = ? ORDER BY id ASC",
                    (int(session_id),),
                ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return []
            raise
        out: list[dict[str, Any]] = []
        for r in rows:
            parsed = _deserialize_json_field(r["payload_json"], None)
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def hydrate_session_anomaly_records(
    session_id: int,
    session_dict: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Hydrates `anomaly_field_log`, `anomalous_vault_requisitions`, `anomalous_vault_log`, and `contained_anomalies_log` onto `session_dict`."""
    if not session_id or not isinstance(session_dict, dict):
        return session_dict

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        try:
            rows = c.execute(
                "SELECT record_type, payload_json FROM session_anomaly_records WHERE session_id = ? ORDER BY id ASC",
                (int(session_id),),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return session_dict
            raise
        by_type: dict[str, list[dict[str, Any]]] = {rt: [] for rt in _RECORD_TYPE_TO_SESSION_ANOMALY_KEY}
        for r in rows:
            rt = str(r["record_type"] or "")
            if rt in by_type:
                parsed = _deserialize_json_field(r["payload_json"], None)
                if isinstance(parsed, dict):
                    by_type[rt].append(parsed)
        for extra_key, rt in SESSION_ANOMALY_KEY_TO_RECORD_TYPE.items():
            if by_type[rt]:
                session_dict[extra_key] = by_type[rt]
            elif extra_key in session_dict and not isinstance(session_dict[extra_key], list):
                session_dict.pop(extra_key, None)
        return session_dict

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def sync_session_anomaly_records_from_extra(
    session_id: int,
    extra_update: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Synchronizes any of the 4 session anomaly keys passed in `extra_update` into `session_anomaly_records`."""
    if not session_id or not isinstance(extra_update, dict):
        return False
    present_keys = [k for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE if k in extra_update]
    if not present_keys:
        return False

    now = time.time()

    def _run(c: sqlite3.Connection) -> bool:
        try:
            c.execute("SELECT 1 FROM session_anomaly_records LIMIT 1").fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return False
            raise

        for extra_key in present_keys:
            rtype = SESSION_ANOMALY_KEY_TO_RECORD_TYPE[extra_key]
            val = extra_update.get(extra_key)
            c.execute(
                "DELETE FROM session_anomaly_records WHERE session_id = ? AND record_type = ?",
                (int(session_id), rtype),
            )
            if not isinstance(val, list) or not val:
                continue
            items_to_insert: list[dict[str, Any]] = [dict(it) for it in val if isinstance(it, dict)]
            if rtype == "field_log":
                deduped_fl: list[dict[str, Any]] = []
                idx_by_key: dict[str, int] = {}
                for it in items_to_insert:
                    ek, *_ = _extract_anomaly_record_columns(rtype, it)
                    if ek and ek in idx_by_key:
                        deduped_fl[idx_by_key[ek]] = it
                    else:
                        if ek:
                            idx_by_key[ek] = len(deduped_fl)
                        deduped_fl.append(it)
                items_to_insert = deduped_fl
            for it in items_to_insert:
                ek, cid, stg, f_turn, t_upd, p_json = _extract_anomaly_record_columns(rtype, it)
                c.execute(
                    """INSERT INTO session_anomaly_records (
                        session_id, record_type, entity_key, codex_id, stage,
                        first_turn, turn_updated, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (int(session_id), rtype, ek, cid, stg, f_turn, t_upd, p_json, now, now),
                )
        return True

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


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
    Records or advances a session-scoped Field Log entry in `session_anomaly_records`
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
        now = time.time()
        t_cur = _effective_session_turn(row, turn_number)
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}

        # Migrate any unmigrated legacy extra_json anomaly lists on first touch
        legacy_keys_present = [k for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE if k in extra]
        if legacy_keys_present:
            patch_to_sync: dict[str, Any] = {}
            for k in legacy_keys_present:
                rtype_k = SESSION_ANOMALY_KEY_TO_RECORD_TYPE[k]
                if isinstance(extra.get(k), list) and extra[k]:
                    existing_cnt = c.execute(
                        "SELECT COUNT(*) FROM session_anomaly_records WHERE session_id = ? AND record_type = ?",
                        (int(session_id), rtype_k),
                    ).fetchone()[0]
                    if not existing_cnt:
                        patch_to_sync[k] = extra[k]
                extra.pop(k, None)
            if patch_to_sync:
                sync_session_anomaly_records_from_extra(int(session_id), patch_to_sync, conn=c)
            c.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(extra, default=str), now, session_id),
            )

        codex_id = str(blueprint.get("codex_id") or "").strip()
        existing_row = c.execute(
            """SELECT id, entity_key, payload_json FROM session_anomaly_records
               WHERE session_id = ? AND record_type = 'field_log'
                 AND (
                     entity_key = ?
                     OR (codex_id != '' AND codex_id = ? AND (? = codex_id OR entity_key = codex_id))
                 )
               ORDER BY CASE WHEN entity_key = ? THEN 0 ELSE 1 END, id DESC
               LIMIT 1""",
            (int(session_id), bp_id, codex_id, bp_id, bp_id),
        ).fetchone()
        is_disguised = bool((blueprint.get("disguise_state") or {}).get("is_disguised")) and norm_stage == "sighted"
        pub_name = (
            str((blueprint.get("disguise_state") or {}).get("disguise_alias") or blueprint.get("name") or "Unknown Anomaly")
            if is_disguised
            else str(blueprint.get("canonical_name") or blueprint.get("name") or blueprint.get("entity_name") or "Unknown Anomaly")
        )

        if existing_row is None:
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
            c.execute(
                """INSERT INTO session_anomaly_records (
                    session_id, record_type, entity_key, codex_id, stage,
                    first_turn, turn_updated, payload_json, created_at, updated_at
                ) VALUES (?, 'field_log', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(session_id),
                    bp_id,
                    codex_id,
                    norm_stage,
                    t_cur,
                    t_cur,
                    json.dumps(entry, default=str),
                    now,
                    now,
                ),
            )
        else:
            entry = dict(_deserialize_json_field(existing_row["payload_json"], {}) or {})
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
            if codex_id and not entry.get("codex_id"):
                entry["codex_id"] = codex_id
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
            c.execute(
                """UPDATE session_anomaly_records
                   SET codex_id = ?, stage = ?, turn_updated = ?, payload_json = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    str(entry.get("codex_id") or codex_id),
                    eff_stage,
                    t_cur,
                    json.dumps(entry, default=str),
                    now,
                    existing_row["id"],
                ),
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
        if not row:
            return {"field_log_reverted": 0}
        extra = _deserialize_json_field(row["extra_json"], {}) if row["extra_json"] else {}
        if not isinstance(extra, dict):
            extra = {}

        changed = 0
        extra_changed = False
        now = time.time()

        # 1. Roll back normalized `session_anomaly_records` rows (`first_turn > t_num` delete + `stage_history` rewind)
        try:
            rec_rows = c.execute(
                """SELECT id, record_type, codex_id, stage, first_turn, turn_updated, payload_json
                   FROM session_anomaly_records
                   WHERE session_id = ?
                   ORDER BY id ASC""",
                (int(session_id),),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e).lower():
                raise
            rec_rows = []

        for rr in rec_rows:
            rec_id = rr["id"]
            rtype = str(rr["record_type"] or "")
            cid_r = str(rr["codex_id"] or "").strip()
            f_turn_r = int(rr["first_turn"] or 0)
            payload = _deserialize_json_field(rr["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            if not f_turn_r:
                for tk in ("first_turn", "turn_captured", "turn"):
                    if payload.get(tk) is not None:
                        try:
                            f_turn_r = int(payload[tk])
                            break
                        except (TypeError, ValueError):
                            continue

            if f_turn_r > t_num:
                eff_cid = cid_r or str(payload.get("codex_id") or "").strip()
                if eff_cid:
                    rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                    if rtype == "field_log":
                        rw_map[eff_cid] = f_turn_r
                    else:
                        rw_map.setdefault(eff_cid, f_turn_r)
                    extra["_rewound_codex_first_turns"] = rw_map
                    extra_changed = True
                c.execute("DELETE FROM session_anomaly_records WHERE id = ?", (rec_id,))
                changed += 1
                continue

            if rtype == "field_log":
                raw_hist = payload.get("stage_history") or []
                hist = [
                    h for h in raw_hist
                    if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num
                ]
                if hist and (len(hist) != len(raw_hist) or int(rr["turn_updated"] or 0) > t_num):
                    upd = dict(payload)
                    last_h = hist[-1]
                    restored_stage = str(last_h.get("stage", upd.get("stage", "sighted")))
                    restored_name = str(last_h.get("name", upd.get("name", "")))
                    restored_disg = (
                        bool(last_h.get("is_disguised", False))
                        if "is_disguised" in last_h
                        else bool(upd.get("is_disguised") and restored_stage == "sighted")
                    )
                    restored_turn = int(last_h.get("turn", f_turn_r))
                    upd["stage"] = restored_stage
                    upd["status"] = restored_stage
                    upd["name"] = restored_name
                    upd["public_name"] = str(last_h.get("public_name", restored_name))
                    upd["is_disguised"] = restored_disg
                    upd["turn_updated"] = restored_turn
                    upd["stage_history"] = hist
                    c.execute(
                        """UPDATE session_anomaly_records
                           SET stage = ?, turn_updated = ?, payload_json = ?, updated_at = ?
                           WHERE id = ?""",
                        (restored_stage, restored_turn, json.dumps(upd, default=str), now, rec_id),
                    )
                    changed += 1

        # 2. Legacy `extra_json` fallback (plus `retired_folklore_ids`, `folklore_cooldowns`, `daily_incursions`, `anomalous_faction_state`)
        if "anomaly_field_log" in extra and isinstance(extra["anomaly_field_log"], list):
            new_log = []
            for item in extra["anomaly_field_log"]:
                if not isinstance(item, dict):
                    continue
                if int(item.get("first_turn", 0)) > t_num:
                    if item.get("codex_id"):
                        rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                        rw_map[str(item["codex_id"])] = int(item.get("first_turn", 0))
                        extra["_rewound_codex_first_turns"] = rw_map
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

        def _entry_turn_stamp(v: dict[str, Any]) -> Optional[int]:
            for tk in ("first_turn", "turn_captured", "turn"):
                if v.get(tk) is not None:
                    try:
                        return int(v[tk])
                    except (TypeError, ValueError):
                        continue
            return None

        for v_key in ("contained_anomalies_log", "anomalous_vault_log", "anomalous_vault_requisitions"):
            if v_key in extra and isinstance(extra[v_key], list):
                orig_v = extra[v_key]
                surv_v = []
                for v in orig_v:
                    if isinstance(v, dict):
                        v_turn = _entry_turn_stamp(v)
                        if v_turn is not None and v_turn > t_num:
                            if v.get("codex_id"):
                                rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                                rw_map.setdefault(str(v["codex_id"]), v_turn)
                                extra["_rewound_codex_first_turns"] = rw_map
                            continue
                    surv_v.append(v)
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

        if changed > 0 or extra_changed:
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
    from .quests import append_quest_note_flag_in_db, get_quest_by_id

    eff_quest = dict(quest) if isinstance(quest, dict) else {}
    qid = str(eff_quest.get("quest_id") or "")
    if qid:
        db_q = get_quest_by_id(session_id, qid)
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
        try:
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
        except Exception:
            pass

        if eval_res.get("codex_id"):
            try:
                record_folklore_codex_progress(uids, str(eval_res["codex_id"]), stage="contained", session_id=session_id)
            except Exception:
                pass

        if eval_res.get("is_object_anomaly") and isinstance(bp, dict):
            try:
                handle_secured_object_anomaly_conversion(session_id, user_id, bp, entity_name=ent_name)
            except Exception:
                pass

        try:
            if qid:
                append_quest_note_flag_in_db(session_id, qid, "vault_logged", "1")
            if isinstance(quest, dict):
                orig_n = str(quest.get("quest_notes") or "")
                quest["quest_notes"] = f"{orig_n}|vault_logged:1" if orig_n else "vault_logged:1"
        except Exception:
            pass

    return {
        "already_logged": False,
        "confiscate_gold": bool(eval_res["confiscate_gold"]),
    }

