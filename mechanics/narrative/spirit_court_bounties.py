"""
Cross-Realm Spirit Court Village HQ Commission Boards & Two-Track Ghoul Quests.

Cohesive domain module for:
- Anti-softlock HQ Board Eligibility (`is_spirit_court_bounty_board_eligible`: rep > -61 & not exiled)
- Independent Optional Commission Tracking (`is_spirit_court_quest`, max 1 active per Spirit Court,
  strictly exempt from Human Agency mandatory quotas, salary suspension & 3-bounty slot caps)
- Rotating 3 Daily Commissions per discovered Village HQ spanning all 4 Veiled frontier biomes
  (`zone_spirit_wilds`, `zone_spirit_peaks`, `zone_spirit_mire`, `zone_spirit_boneyard`) AND
  `realm_city_metro` (`target_realm_id` + `target_node_id`), loaded from Layer 1 `folklore_villages_catalog.json`
- Two-Track Ghoul Quest Board: guarantees >= 1 fast dark crime (+12..+18 rep; gore-respecting;
  -5 Kitsune/Bunian ripple + Human Agency heat on stealth failure / overt desecration) AND
  >= 1 slower grey-neutral job (+5..+6 rep; zero cross-court splash).
"""
from __future__ import annotations

from contextlib import nullcontext
import hashlib
import re
import time
from typing import Any, Mapping

import db
import scenario_data

SPIRIT_COURT_HQ_BY_VILLAGE: dict[str, str] = {
    "kitsune": "loc_hidden_kitsune_village",
    "bunian": "loc_hidden_bunian_village",
    "ghoul": "loc_hidden_ghoul_village",
}

SPIRIT_COURT_FACTION_TO_VILLAGE: dict[str, str] = {
    "faction_spirit_kitsune": "kitsune",
    "faction_spirit_bunian": "bunian",
    "faction_spirit_ghoul": "ghoul",
}

SPIRIT_COURT_VILLAGE_TO_FACTION: dict[str, str] = {v: k for k, v in SPIRIT_COURT_FACTION_TO_VILLAGE.items()}
SPIRIT_COURT_EXILE_REP_FLOOR: int = -61

_TEMPLATES_CACHE: dict[str, list[dict[str, Any]]] | None = None


def get_spirit_court_commission_templates() -> dict[str, list[dict[str, Any]]]:
    """Loads Layer 1 `spirit_court_commissions` templates from `data/folklore_villages_catalog.json`."""
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None:
        from mechanics.world.locations.folklore_veil import load_folklore_villages_catalog

        raw_cat = load_folklore_villages_catalog() or {}
        raw_comm = raw_cat.get("spirit_court_commissions") or {}
        _TEMPLATES_CACHE = {
            vk: [dict(item) for item in (raw_comm.get(vk) or ()) if isinstance(item, dict)]
            for vk in ("kitsune", "bunian", "ghoul")
        }
    return _TEMPLATES_CACHE


class _LazyTemplatesMapping(dict):
    """Backward-compatible dict view backed by `get_spirit_court_commission_templates()`."""

    def _sync(self) -> dict[str, list[dict[str, Any]]]:
        data = get_spirit_court_commission_templates()
        dict.clear(self)
        dict.update(self, data)
        return data

    def __getitem__(self, key: str) -> list[dict[str, Any]]:
        return self._sync()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._sync().get(key, default)

    def items(self):  # type: ignore[override]
        return self._sync().items()

    def values(self):  # type: ignore[override]
        return self._sync().values()

    def keys(self):  # type: ignore[override]
        return self._sync().keys()


SPIRIT_COURT_COMMISSION_TEMPLATES: dict[str, list[dict[str, Any]]] = _LazyTemplatesMapping()


def _parse_notes_kv(notes: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_part in re.split(r"[|\n]+", str(notes or "")):
        part = raw_part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            parsed[k.strip().lower()] = v.strip()
    return parsed


def is_spirit_court_quest(quest: Mapping[str, Any] | None) -> bool:
    """Returns True if `quest` originated from one of the 3 autonomous Spirit Court HQ boards."""
    if not isinstance(quest, Mapping):
        return False
    if str(quest.get("board_source") or "").strip().lower() == "spirit_court":
        return True
    qid_up = str(quest.get("quest_id") or "").strip().upper()
    if qid_up.startswith(("SPC-", "EVT-SPC-")):
        return True
    if str(quest.get("faction_id") or "").strip().lower() in SPIRIT_COURT_FACTION_TO_VILLAGE:
        return True
    kv = _parse_notes_kv(str(quest.get("quest_notes") or ""))
    return (
        kv.get("board_source") == "spirit_court"
        or kv.get("spirit_court") in SPIRIT_COURT_VILLAGE_TO_FACTION
        or kv.get("faction", "").lower() in SPIRIT_COURT_FACTION_TO_VILLAGE
    )


def get_spirit_court_village_key_for_quest(quest: Mapping[str, Any] | None) -> str:
    """Extracts `'kitsune'`, `'bunian'`, or `'ghoul'` from a Spirit Court quest dict."""
    if not isinstance(quest, Mapping):
        return ""
    vk = str(quest.get("village_key") or "").strip().lower()
    if vk in SPIRIT_COURT_VILLAGE_TO_FACTION:
        return vk
    fid = str(quest.get("faction_id") or "").strip().lower()
    if fid in SPIRIT_COURT_FACTION_TO_VILLAGE:
        return SPIRIT_COURT_FACTION_TO_VILLAGE[fid]
    kv = _parse_notes_kv(str(quest.get("quest_notes") or ""))
    vk_note = kv.get("spirit_court", "").lower()
    if vk_note in SPIRIT_COURT_VILLAGE_TO_FACTION:
        return vk_note
    return SPIRIT_COURT_FACTION_TO_VILLAGE.get(kv.get("faction", "").lower(), "")


def is_spirit_court_bounty_board_eligible(
    session_id: int,
    village_key: str,
    reputation_score: int | None = None,
) -> bool:
    """Anti-softlock gate: board open whenever `reputation_score > -61` and not exiled/atonement-locked."""
    vk = str(village_key or "").strip().lower()
    fid = SPIRIT_COURT_VILLAGE_TO_FACTION.get(vk)
    if not session_id or not fid:
        return False

    if reputation_score is None:
        fac_row = db.get_faction(int(session_id), fid)
        if fac_row is not None:
            rep = int(fac_row.get("reputation_score") or 0)
        else:
            from mechanics.world.locations.folklore_spirit_courts import compute_spirit_court_starting_rep
            rep = compute_spirit_court_starting_rep(int(session_id), village_key=vk)
    else:
        rep = int(reputation_score)

    if rep <= SPIRIT_COURT_EXILE_REP_FLOOR:
        return False
    try:
        from mechanics.world.locations.folklore_veil import get_village_veil_status
        v_st = get_village_veil_status(int(session_id), vk) or {}
        if v_st.get("atonement_required") or v_st.get("veil_atonement_required"):
            return False
    except Exception:
        pass
    return True


def get_active_spirit_court_commissions(
    session_id: int,
    village_key: str | None = None,
) -> list[dict[str, Any]]:
    """Lists active Spirit Court commissions (`status in ('Active', 'In Progress')`)."""
    if not session_id:
        return []
    target_vk = str(village_key or "").strip().lower()
    out: list[dict[str, Any]] = []
    for q in (db.get_session_quests(int(session_id)) or []):
        if not isinstance(q, Mapping):
            continue
        if str(q.get("status") or "").strip().lower() not in ("active", "in progress"):
            continue
        if not is_spirit_court_quest(q):
            continue
        if target_vk and get_spirit_court_village_key_for_quest(q) != target_vk:
            continue
        out.append(dict(q))
    return out


def can_accept_spirit_court_commission(
    session_id: int,
    quest_or_vk: Mapping[str, Any] | str,
) -> tuple[bool, str]:
    """Enforces anti-exile eligibility and max 1 active commission per Spirit Court simultaneously."""
    if isinstance(quest_or_vk, Mapping):
        vk = get_spirit_court_village_key_for_quest(quest_or_vk)
        q_id = str(quest_or_vk.get("quest_id") or "")
    else:
        vk = str(quest_or_vk or "").strip().lower()
        q_id = ""
    if vk not in SPIRIT_COURT_VILLAGE_TO_FACTION:
        return False, "Unknown Spirit Court commission source."
    if not is_spirit_court_bounty_board_eligible(session_id, vk):
        return False, "This Spirit Court has sealed its commission board to you until exile atonement is completed."
    active_for_court = [
        q for q in get_active_spirit_court_commissions(session_id, village_key=vk)
        if not q_id or str(q.get("quest_id") or "") != q_id
    ]
    if active_for_court:
        return False, (
            f"You already hold an active commission for this Spirit Court ('{active_for_court[0].get('title', 'Active Task')}'). "
            "Complete or abandon it before taking another."
        )
    return True, "Authorized optional Spirit Court commission."


def _select_daily_commission_templates(
    session_id: int,
    village_key: str,
    day_num: int,
    world_seed: str = "",
) -> list[dict[str, Any]]:
    pool = list(get_spirit_court_commission_templates().get(village_key) or [])
    if not pool:
        return []

    def _det_score(tpl: dict[str, Any]) -> int:
        mat = f"{world_seed}:{session_id}:{village_key}:{day_num}:{tpl['template_id']}"
        return int(hashlib.sha256(mat.encode("utf-8")).hexdigest()[:12], 16)

    if village_key == "ghoul":
        dark_pool = sorted([t for t in pool if t.get("track") == "dark_crime"], key=_det_score)
        grey_pool = sorted([t for t in pool if t.get("track") == "grey_neutral"], key=_det_score)
        chosen = [p[0] for p in (dark_pool, grey_pool) if p]
    else:
        city_pool = sorted([t for t in pool if t.get("target_realm_id") == "realm_city_metro"], key=_det_score)
        frontier_pool = sorted([t for t in pool if t.get("target_realm_id") == "realm_veiled_spirit_world"], key=_det_score)
        chosen = [p[0] for p in (city_pool, frontier_pool) if p]

    remaining = sorted([t for t in pool if t not in chosen], key=_det_score)
    while remaining and len(chosen) < 3:
        chosen.append(remaining.pop(0))
    return chosen[:3]


def _resolve_court_display_and_rep(session_id: int, village_key: str) -> tuple[str, int]:
    from mechanics.world.locations.folklore_spirit_courts import (
        SPIRIT_COURT_FACTIONS,
        ensure_spirit_court_faction_discovered,
    )
    fac = db.get_faction(int(session_id), SPIRIT_COURT_VILLAGE_TO_FACTION[village_key])
    if fac is None:
        fac = ensure_spirit_court_faction_discovered(int(session_id), village_key)
    spec = SPIRIT_COURT_FACTIONS.get(village_key) or {}
    return str((fac or {}).get("name") or spec.get("name") or village_key.title()), int((fac or {}).get("reputation_score") or 0)


def _build_commission_entry(
    *,
    session_id: int,
    village_key: str,
    faction_id: str,
    court_name: str,
    hq_node_id: str,
    qid: str,
    tpl: Mapping[str, Any],
    is_gore: bool,
    turn_number: int | None = None,
) -> dict[str, Any]:
    track = str(tpl.get("track") or "standard")
    rep_reward = int(tpl.get("rep_reward") or 8)
    eff_obj = str(tpl["gore_objective"]) if (is_gore and tpl.get("gore_objective")) else str(tpl["objective"])
    note_parts = [
        f"faction:{faction_id}", "board_source:spirit_court", f"spirit_court:{village_key}",
        "optional_spirit_court:1", f"target_realm_id:{tpl['target_realm_id']}",
        f"target_node_id:{tpl['target_node_id']}", f"rep_reward:{rep_reward}",
        f"ghoul_track:{track}", f"template_id:{tpl['template_id']}", f"hq_node_id:{hq_node_id}",
    ]
    if turn_number is not None and int(turn_number) > 0:
        note_parts.append(f"created_turn:{int(turn_number)}")
    if tpl.get("sub_target_node_id"):
        note_parts.append(f"sub_target_node_id:{tpl['sub_target_node_id']}")
    if track == "dark_crime":
        note_parts.extend(("ripple_on_exposure:kitsune,bunian", "agency_heat_on_exposure:1"))
    else:
        note_parts.append("zero_cross_court_splash:1")

    return {
        "quest_id": qid, "session_id": int(session_id), "title": str(tpl["title"]),
        "quest_type": str(tpl.get("quest_type") or "Side Quest"), "status": "Available",
        "is_story_quest": 0, "is_mandatory": 0, "board_source": "spirit_court",
        "village_key": village_key, "faction_id": faction_id, "faction_name": court_name,
        "client_npc": f"{court_name} Herald", "client_location": str(tpl["location_label"]),
        "objective": eff_obj, "required_item": str(tpl.get("required_item") or ""),
        "reward_xp": int(tpl.get("xp_reward") or 80), "reward_gold": int(tpl.get("gold_reward") or 140),
        "reward_item": "", "faction_rep_reward": rep_reward,
        "target_realm_id": str(tpl["target_realm_id"]), "target_node_id": str(tpl["target_node_id"]),
        "ghoul_track": track, "quest_notes": " | ".join(note_parts),
    }


def _annotate_commission_list(quests: list[dict[str, Any]], village_key: str, court_name: str) -> list[dict[str, Any]]:
    fid = SPIRIT_COURT_VILLAGE_TO_FACTION.get(village_key, "")
    annotated: list[dict[str, Any]] = []
    for raw in quests:
        q = dict(raw)
        kv = _parse_notes_kv(str(q.get("quest_notes") or ""))
        q.setdefault("board_source", "spirit_court")
        q.setdefault("village_key", village_key)
        q.setdefault("faction_id", fid)
        q.setdefault("faction_name", court_name)
        q.setdefault("is_mandatory", 0)
        q["target_realm_id"] = str(q.get("target_realm_id") or kv.get("target_realm_id") or "")
        q["target_node_id"] = str(q.get("target_node_id") or kv.get("target_node_id") or "")
        q["ghoul_track"] = str(q.get("ghoul_track") or kv.get("ghoul_track") or "standard")
        if "rep_reward" in kv and not q.get("faction_rep_reward"):
            try:
                q["faction_rep_reward"] = int(kv["rep_reward"])
            except ValueError:
                pass
        annotated.append(q)
    return annotated


def generate_spirit_court_commission_board(
    session_id: int,
    village_key: str,
    *,
    current_day: int | None = None,
    scenario: str = "",
    force_refresh: bool = False,
    persist_db: bool = True,
) -> list[dict[str, Any]]:
    """Rotates 3 daily optional commissions for a Spirit Court HQ without touching Human Agency quotas."""
    vk = str(village_key or "").strip().lower()
    fid = SPIRIT_COURT_VILLAGE_TO_FACTION.get(vk)
    if not session_id or not fid:
        return []

    sess = db.get_session(int(session_id)) or {}
    day_num = max(1, int(current_day if current_day is not None else (sess.get("current_day") or 1)))
    is_gore = bool(scenario_data.is_gore_scenario(str(scenario or sess.get("scenario") or "anomalous_incursions")))
    world_seed = str(sess.get("world_seed") or sess.get("rng_seed") or session_id)
    court_name, court_rep = _resolve_court_display_and_rep(int(session_id), vk)
    if not is_spirit_court_bounty_board_eligible(int(session_id), vk, court_rep):
        return []

    prefix_today = f"SPC-{vk[:3].upper()}-D{day_num}-"
    eff_turn = int(db.get_effective_session_turn(int(session_id)))
    all_sess_quests = db.get_session_quests(int(session_id)) or []
    crisis_today = [
        dict(q) for q in all_sess_quests
        if str(q.get("status") or "") == "Available"
        and str(q.get("quest_id") or "").upper().startswith("EVT-SPC-")
        and get_spirit_court_village_key_for_quest(q) == vk
    ]
    if not force_refresh:
        existing_today = [
            dict(q) for q in all_sess_quests
            if str(q.get("status") or "") == "Available" and str(q.get("quest_id") or "").upper().startswith(prefix_today)
        ]
        if existing_today:
            return _annotate_commission_list(crisis_today + existing_today, vk, court_name)

    selected = _select_daily_commission_templates(int(session_id), vk, day_num, world_seed=world_seed)
    built = [
        _build_commission_entry(
            session_id=int(session_id), village_key=vk, faction_id=fid, court_name=court_name,
            hq_node_id=SPIRIT_COURT_HQ_BY_VILLAGE[vk], qid=f"{prefix_today}{idx:02d}", tpl=tpl, is_gore=is_gore,
            turn_number=eff_turn,
        )
        for idx, tpl in enumerate(selected, start=1)
    ]

    if persist_db and built:
        with db.UnitOfWork() as conn:
            stale_rows = conn.execute(
                "SELECT quest_id FROM quests WHERE session_id=? AND status='Available' AND quest_notes LIKE ? AND UPPER(quest_id) NOT LIKE 'EVT-SPC-%'",
                (int(session_id), f"%spirit_court:{vk}%"),
            ).fetchall()
            stale_qids = [r["quest_id"] for r in stale_rows if r and r["quest_id"]]
            if stale_qids:
                ph = ",".join("?" for _ in stale_qids)
                conn.execute(f"DELETE FROM quest_waypoints WHERE session_id=? AND quest_id IN ({ph})", [int(session_id)] + stale_qids)
                conn.execute(f"DELETE FROM quest_dossiers WHERE session_id=? AND quest_id IN ({ph})", [int(session_id)] + stale_qids)
                conn.execute(f"DELETE FROM quests WHERE session_id=? AND quest_id IN ({ph})", [int(session_id)] + stale_qids)
            for entry in built:
                db.upsert_quest(
                    session_id=int(session_id), quest_id=entry["quest_id"], quest_type=entry["quest_type"],
                    title=entry["title"], objective=entry["objective"], status="Available",
                    reward_xp=entry["reward_xp"], reward_gold=entry["reward_gold"], reward_item=entry["reward_item"],
                    is_story_quest=0, quest_notes=entry["quest_notes"], client_npc=entry["client_npc"],
                    client_location=entry["client_location"], required_item=entry["required_item"],
                )
    return _annotate_commission_list(crisis_today + built, vk, court_name)


def record_spirit_court_commission_accepted(
    session_id: int,
    quest_id: str,
    *,
    turn_number: int | None = None,
    conn: Any = None,
) -> None:
    """Stamps `accepted_spirit_commissions[quest_id] = turn` into `spirit_realm_state` for rollback parity."""
    from mechanics.world.locations.folklore_spirit_courts import (
        _mutate_spirit_realm_state,
        _resolve_turn_num,
        _uow_ctx,
    )
    if not session_id or not quest_id:
        return
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)

        def _stamp_acc(srs: dict[str, Any]) -> None:
            acc = dict(srs.get("accepted_spirit_commissions") or {})
            acc[str(quest_id)] = eff_turn
            srs["accepted_spirit_commissions"] = acc

        _mutate_spirit_realm_state(c, int(session_id), _stamp_acc)


def resolve_spirit_court_quest_claim_effects(
    session_id: int,
    quest: Mapping[str, Any],
    *,
    faction_id: str,
    rep_reward: int,
    notes: str = "",
    dossier: Mapping[str, Any] | None = None,
    conn: Any = None,
    stealth_failed: bool | None = None,
    overt_desecration: bool | None = None,
) -> dict[str, Any]:
    """
    Atomically applies Spirit Court rep via `adjust_spirit_court_reputation(..., conn=conn)`
    and handles Two-Track Ghoul ripples (zero cross-court splash on grey-neutral; -5 Kitsune/Bunian
    + -5 Human Agency heat when a Ghoul dark crime is exposed).
    """
    from mechanics.world.locations.folklore_spirit_courts import (
        _mutate_spirit_realm_state,
        _resolve_turn_num,
        adjust_spirit_court_reputation,
    )

    vk = SPIRIT_COURT_FACTION_TO_VILLAGE.get(str(faction_id or "").strip().lower(), "") or get_spirit_court_village_key_for_quest(quest)
    eff_rep = int(rep_reward or 10)
    kv = _parse_notes_kv(notes or str(quest.get("quest_notes") or ""))
    track = str(quest.get("ghoul_track") or kv.get("ghoul_track") or "standard").strip().lower()

    gained_rep = eff_rep
    if vk:
        rep_res = adjust_spirit_court_reputation(
            int(session_id), vk, eff_rep,
            reason=f"Completed '{quest.get('title', 'Spirit Court Commission')}'", conn=conn,
        )
        gained_rep = int(rep_res.get("delta") or 0)

    rival_rep_deltas: dict[str, int] = {}
    agency_heat_delta = 0
    exposed = False
    if vk == "ghoul" and track == "dark_crime":
        tier_str = str((dossier or {}).get("outcome_tier") or quest.get("resolution_approach") or "").strip().lower()
        notes_low = str(notes or quest.get("quest_notes") or "").lower()
        clean_stealthed = ("clean_stealth:1" in notes_low or "stealth_clean:1" in notes_low)
        exposed_by_flag = bool(
            overt_desecration or stealth_failed
            or "overt_desecration:1" in notes_low or "stealth_failed:1" in notes_low or "stealth_blown:1" in notes_low
            or tier_str in ("messy_success", "compromised", "overt", "exposed", "stealth_failed", "dire_cost")
        )
        exposed = exposed_by_flag and not (clean_stealthed and overt_desecration is not True and stealth_failed is not True)
        if exposed:
            ctx_cm = nullcontext(conn) if conn is not None else db.UnitOfWork()
            with ctx_cm as c_rip:
                for r_vk in ("kitsune", "bunian"):
                    r_fid = SPIRIT_COURT_VILLAGE_TO_FACTION[r_vk]
                    if c_rip.execute("SELECT 1 FROM factions WHERE session_id = ? AND faction_id = ?", (int(session_id), r_fid)).fetchone():
                        adjust_spirit_court_reputation(
                            int(session_id), r_vk, -5,
                            reason=f"Exposed Ghoul dark crime '{quest.get('title', '')}'", conn=c_rip,
                        )
                        rival_rep_deltas[r_fid] = -5
                pa_row = c_rip.execute(
                    "SELECT faction_id, reputation_score FROM factions WHERE session_id = ? AND LOWER(COALESCE(category, '')) = 'public_agency' LIMIT 1",
                    (int(session_id),),
                ).fetchone()
                if pa_row:
                    pa_fid = str(pa_row["faction_id"])
                    old_pa = int(pa_row["reputation_score"] or 0)
                    new_pa = max(-100, old_pa - 5)
                    applied_pa_delta = new_pa - old_pa
                    c_rip.execute(
                        "UPDATE factions SET reputation_score = ?, updated_at = ? WHERE session_id = ? AND faction_id = ?",
                        (new_pa, time.time(), int(session_id), pa_fid),
                    )
                    if applied_pa_delta != 0:
                        eff_turn = _resolve_turn_num(c_rip, int(session_id), None)

                        def _log_pa_heat(srs: dict[str, Any]) -> None:
                            hl = list(srs.get("agency_heat_ledger") or [])
                            hl.append({
                                "turn": eff_turn,
                                "faction_id": pa_fid,
                                "prev_score": old_pa,
                                "delta": applied_pa_delta,
                            })
                            srs["agency_heat_ledger"] = hl[-64:]

                        _mutate_spirit_realm_state(c_rip, int(session_id), _log_pa_heat)
                    rival_rep_deltas[pa_fid] = applied_pa_delta
                    agency_heat_delta = applied_pa_delta

    return {
        "village_key": vk, "faction_rep_gained": gained_rep, "rival_rep_deltas": rival_rep_deltas,
        "agency_heat_delta": agency_heat_delta, "ghoul_track": track, "exposed": exposed,
    }


__all__ = [
    "SPIRIT_COURT_HQ_BY_VILLAGE", "SPIRIT_COURT_FACTION_TO_VILLAGE", "SPIRIT_COURT_VILLAGE_TO_FACTION",
    "SPIRIT_COURT_EXILE_REP_FLOOR", "SPIRIT_COURT_COMMISSION_TEMPLATES", "get_spirit_court_commission_templates",
    "is_spirit_court_quest", "get_spirit_court_village_key_for_quest", "is_spirit_court_bounty_board_eligible",
    "get_active_spirit_court_commissions", "can_accept_spirit_court_commission",
    "generate_spirit_court_commission_board", "record_spirit_court_commission_accepted", "resolve_spirit_court_quest_claim_effects",
]
