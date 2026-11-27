"""
mechanics/world/locations/folklore_spirit_courts.py
===================================================
Constants, Spirit Realm `extra_json` state helpers, discoverable non-exclusive
`spirit_court` factions (`faction_spirit_kitsune`, `faction_spirit_bunian`,
`faction_spirit_ghoul`), standing-unlocked Guest-Cottages (>= 70), shop price
multipliers, and friendly sparring drills for `realm_veiled_spirit_world`.
"""
from __future__ import annotations

import json
import logging
import time
from contextlib import nullcontext
from typing import Any, Dict, Mapping, Optional, Tuple

import db

log = logging.getLogger("hikayat.world.folklore_spirit_courts")

SPIRIT_REALM_ID = "realm_veiled_spirit_world"
SPIRIT_CROSSROADS_ZONE_ID = "zone_spirit_crossroads"
SPIRIT_WILDS_ZONE_ID = "zone_spirit_wilds"
SPIRIT_PEAKS_ZONE_ID = "zone_spirit_peaks"
SPIRIT_MIRE_ZONE_ID = "zone_spirit_mire"
SPIRIT_BONEYARD_ZONE_ID = "zone_spirit_boneyard"
SPIRIT_FRONTIER_ZONE_IDS: Tuple[str, ...] = (
    SPIRIT_WILDS_ZONE_ID,
    SPIRIT_PEAKS_ZONE_ID,
    SPIRIT_MIRE_ZONE_ID,
    SPIRIT_BONEYARD_ZONE_ID,
)
SPIRIT_VILLAGE_KEYS: Tuple[str, ...] = ("kitsune", "bunian", "ghoul")

WILDS_SAFE_RESCUE_NODE_ID = "sub_wilds_ward_camp"
CROSSROADS_TEA_FALLBACK_NODE_ID = "sub_crossroads_tea_hall"
CHINATOWN_SHORTCUT_SPIRIT_NODE = "sub_crossroads_mist_wharf"
CHINATOWN_SHORTCUT_HUMAN_NODE = "sub_ct_curio_stalls"
CHINATOWN_OFFERING_GOLD = 50

SPIRIT_ZONE_BY_VILLAGE: Dict[str, str] = {
    "kitsune": "zone_spirit_kitsune",
    "bunian": "zone_spirit_bunian",
    "ghoul": "zone_spirit_ghoul",
}

SPIRIT_VILLAGE_BY_ZONE: Dict[str, str] = {
    "zone_spirit_kitsune": "kitsune",
    "zone_spirit_bunian": "bunian",
    "zone_spirit_ghoul": "ghoul",
}

SPIRIT_VILLAGE_PUBLIC_FACILITIES: Dict[str, Tuple[str, ...]] = {
    "kitsune": (
        "loc_hidden_kitsune_village",
        "loc_kitsune_foxfire_onsen",
        "loc_kitsune_mask_theater",
        "loc_kitsune_scroll_archive",
        "loc_kitsune_blade_yard",
    ),
    "bunian": (
        "loc_hidden_bunian_village",
        "loc_bunian_orchid_garden",
        "loc_bunian_songket_wakaf",
        "loc_bunian_silat_gelanggang",
        "loc_bunian_canopy_observatory",
    ),
    "ghoul": (
        "loc_hidden_ghoul_village",
        "loc_ghoul_embalming_house",
        "loc_ghoul_carrion_tavern",
        "loc_ghoul_kennel_pit",
        "loc_ghoul_mausoleum_archive",
    ),
}

SPIRIT_GUEST_COTTAGE_SPEC: Dict[str, Dict[str, Any]] = {
    "kitsune": {
        "property_id": "prop_kitsune_guest_villa",
        "facility_node_id": "fac_kitsune_guest_villa",
        "entrance_node_id": "sub_kitsune_villa_engawa",
        "bedroom_node_id": "sub_kitsune_villa_sleeping_room",
        "zone_id": "zone_spirit_kitsune",
        "name": "Hinoki Shrine Guest-Villa",
        "rest_multiplier": 1.25,
        "room_ids": ("sub_kitsune_villa_engawa", "sub_kitsune_villa_sleeping_room"),
    },
    "bunian": {
        "property_id": "prop_bunian_guest_house",
        "facility_node_id": "fac_bunian_guest_house",
        "entrance_node_id": "sub_bunian_house_veranda",
        "bedroom_node_id": "sub_bunian_house_chamber",
        "zone_id": "zone_spirit_bunian",
        "name": "Kayangan Banyan Guest-House",
        "rest_multiplier": 1.25,
        "room_ids": ("sub_bunian_house_veranda", "sub_bunian_house_chamber"),
    },
    "ghoul": {
        "property_id": "prop_ghoul_guest_manor",
        "facility_node_id": "fac_ghoul_guest_manor",
        "entrance_node_id": "sub_ghoul_suite_foyer",
        "bedroom_node_id": "sub_ghoul_suite_bedroom",
        "zone_id": "zone_spirit_ghoul",
        "name": "The Cypress Mausoleum Guest-Suite",
        "rest_multiplier": 1.25,
        "room_ids": ("sub_ghoul_suite_foyer", "sub_ghoul_suite_bedroom"),
    },
}

SPIRIT_COURT_FACTIONS: Dict[str, Dict[str, str]] = {
    "kitsune": {
        "faction_id": "faction_spirit_kitsune",
        "name": "Sato-no-Inari Spirit Court",
        "hq_node_id": "loc_hidden_kitsune_village",
        "hq_location_id": "Sato-no-Inari Inner Sanctuary",
        "notes": "Autonomous Spirit Court of the Sato-no-Inari Kitsune Enclave inside The Veiled Spirit Realm.",
    },
    "bunian": {
        "faction_id": "faction_spirit_bunian",
        "name": "Kampung Kayangan Royal Court",
        "hq_node_id": "loc_hidden_bunian_village",
        "hq_location_id": "Istana & Laman Seri Cempaka",
        "notes": "Autonomous Spirit Court of Kampung Kayangan Bunian inside The Veiled Spirit Realm.",
    },
    "ghoul": {
        "faction_id": "faction_spirit_ghoul",
        "name": "Majlis al-Ghūl — Pale Ossuary Court",
        "hq_node_id": "loc_hidden_ghoul_village",
        "hq_location_id": "The Ossuary Court & Inner Crypt",
        "notes": "Autonomous Ossuary Court of the veiled Al-Ghūl necropolis inside The Veiled Spirit Realm.",
    },
}

SPIRIT_SPARRING_ROOMS: Dict[str, str] = {
    "sub_kitsune_sparring_yard": "kitsune",
    "sub_bunian_silat_courtyard": "bunian",
    "sub_ghoul_sparring_pit": "ghoul",
}

ALL_SPIRIT_GUEST_FACILITY_IDS: frozenset[str] = frozenset({
    "fac_kitsune_guest_villa",
    "fac_bunian_guest_house",
    "fac_ghoul_guest_manor",
})

ALL_SPIRIT_GUEST_PROPERTY_IDS: frozenset[str] = frozenset({
    "prop_kitsune_guest_villa",
    "prop_bunian_guest_house",
    "prop_ghoul_guest_manor",
})


def _uow_ctx(conn: Any):
    return nullcontext(conn) if conn is not None else db.UnitOfWork()


def _parse_json_dict(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def _load_extra_json(conn: Any, session_id: int) -> Dict[str, Any]:
    row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
    if not row:
        return {}
    return _parse_json_dict(row["extra_json"] if hasattr(row, "keys") else row[0])


def _save_extra_json(conn: Any, session_id: int, extra: Mapping[str, Any]) -> None:
    conn.execute(
        "UPDATE sessions SET extra_json = ? WHERE id = ?",
        (json.dumps(dict(extra), default=str), int(session_id)),
    )


def get_spirit_realm_state(session_id: int, conn: Any = None) -> Dict[str, Any]:
    """Reads `sessions.extra_json['spirit_realm_state']` safely."""
    if not session_id:
        return {}
    if conn is not None:
        ex = _load_extra_json(conn, session_id)
        srs = ex.get("spirit_realm_state")
    else:
        sess = db.get_session(int(session_id)) or {}
        srs = sess.get("spirit_realm_state")
        if not isinstance(srs, dict):
            ex = _parse_json_dict(sess.get("extra_json") or sess.get("extra"))
            srs = ex.get("spirit_realm_state")
    return dict(srs) if isinstance(srs, dict) else {}


def _mutate_spirit_realm_state(
    conn: Any,
    session_id: int,
    mutator: Any,
) -> Dict[str, Any]:
    ex = _load_extra_json(conn, session_id)
    srs = dict(ex.get("spirit_realm_state") or {}) if isinstance(ex.get("spirit_realm_state"), dict) else {}
    mutator(srs)
    ex["spirit_realm_state"] = srs
    _save_extra_json(conn, session_id, ex)
    return srs


def _resolve_turn_num(conn: Any, session_id: int, turn_number: Optional[int]) -> int:
    if turn_number is not None:
        return int(turn_number)
    row = conn.execute("SELECT turn_count FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
    tc = int((row["turn_count"] if hasattr(row, "keys") else row[0]) or 0) if row else 0
    return max(1, tc)


def _get_court_rep_sql(conn: Any, session_id: int, village_key: str) -> int:
    spec = SPIRIT_COURT_FACTIONS.get(village_key)
    if not spec:
        return 0
    row = conn.execute(
        "SELECT reputation_score FROM factions WHERE session_id = ? AND faction_id = ?",
        (int(session_id), spec["faction_id"]),
    ).fetchone()
    return int(row["reputation_score"] or 0) if row else 0


def compute_spirit_court_starting_rep(session_id: int, village_key: str = "kitsune") -> int:
    """
    Computes diplomatic starting reputation upon first discovering a Spirit Court:
    - For Kitsune & Bunian:
      - Syndicate / Occult Cult -> -15 (Distrusted)
      - Eastern Exorcist Order  -> +10 (Respected)
      - Public/Private Agency / Freelancer / Student -> 0 (Neutral)
    - For Ghoul (`Majlis al-Ghūl`):
      - Always negative (never Hostile):
      - Syndicate / Occult Cult -> -15 (Distrusted)
      - Agency / Freelancer / Student -> -25 (Distrusted)
      - Eastern Exorcist Order -> -35 (Adversary)
    """
    vk = str(village_key or "").strip().lower()
    if not session_id:
        return -25 if vk == "ghoul" else 0
    try:
        from mechanics.social.factions import get_anomalous_faction_state
        st = get_anomalous_faction_state(int(session_id)) or {}
        arch = str(st.get("faction_archetype_key") or "").strip().lower()
    except Exception:
        arch = ""
    if vk == "ghoul":
        if arch in ("clandestine_faction", "clandestine_syndicate", "syndicate", "cult_faction", "occult_cult", "cult"):
            return -15
        if arch in ("monastic_order", "exorcist_order", "eastern_exorcist_order"):
            return -35
        return -25
    if arch in ("clandestine_faction", "clandestine_syndicate", "syndicate", "cult_faction", "occult_cult", "cult"):
        return -15
    if arch in ("monastic_order", "exorcist_order", "eastern_exorcist_order"):
        return 10
    return 0


_COURT_LEADERSHIP_SLOT_DEFS: Dict[str, Tuple[Tuple[Tuple[str, ...], int, str], ...]] = {
    "kitsune": (
        (("folklore_kitsune_sovereign", "folklore_kitsune_sovereign_twin"), 4, "Sovereign"),
        (("folklore_kitsune_elder",), 3, "Shrine Elder"),
        (("folklore_kitsune_guardian", "folklore_kitsune_warden"), 2, "Sanctuary Sentinel"),
    ),
    "bunian": (
        (("folklore_bunian_royal_heir", "folklore_bunian_royal_heir_twin"), 4, "Royal Heir"),
        (("folklore_bunian_elder",), 3, "Court Elder"),
        (("folklore_bunian_guardian", "folklore_bunian_warden"), 2, "Sanctuary Sentinel"),
    ),
    "ghoul": (
        (("folklore_ghoul_heir", "folklore_ghoul_heir_twin"), 4, "Ossuary Heir"),
        (("folklore_ghoul_elder",), 3, "Council Arbiter"),
        (("folklore_ghoul_pit_champion",), 2, "Ash-Pit Sentinel"),
    ),
}


def build_spirit_court_leadership_roster(
    session_id: int,
    village_key: str,
    *,
    conn: Any = None,
) -> list[Dict[str, Any]]:
    """
    Populates Spirit Court `leadership_roster` with the enclave's actual live
    Sovereign/Heir, Elder, and Sentinel from `contacts` / deterministic village roster
    so codex adapters never invent random human leaders.
    """
    vk = str(village_key or "").strip().lower()
    slots = _COURT_LEADERSHIP_SLOT_DEFS.get(vk)
    if not session_id or not slots:
        return []

    contact_rows: Dict[str, Dict[str, Any]] = {}
    with _uow_ctx(conn) as c:
        rows = c.execute(
            "SELECT npc_id, name, basic_info_json FROM contacts WHERE session_id = ?",
            (int(session_id),),
        ).fetchall()
        for r in rows:
            nid = str(r["npc_id"] or "").strip().lower()
            if nid:
                contact_rows[nid] = dict(r)

    roster_cache: list[Dict[str, Any]] | None = None

    def _get_roster_entries() -> list[Dict[str, Any]]:
        nonlocal roster_cache
        if roster_cache is None:
            try:
                from mechanics.social.folklore_roster import ensure_folklore_villager_roster
                sess_obj: Dict[str, Any] | None = None
                with _uow_ctx(conn) as c_sess:
                    s_row = c_sess.execute(
                        "SELECT id, scenario, host_user_id, extra_json FROM sessions WHERE id = ?",
                        (int(session_id),),
                    ).fetchone()
                    if s_row:
                        extra_d = _parse_json_dict(s_row["extra_json"])
                        sess_obj = {
                            "id": int(s_row["id"]),
                            "scenario": s_row["scenario"],
                            "host_user_id": s_row["host_user_id"],
                            "world_seed": extra_d.get("world_seed"),
                            "extra": extra_d,
                            "folklore_villager_roster": extra_d.get("folklore_villager_roster"),
                            "folklore_roster_pc_bucket": extra_d.get("folklore_roster_pc_bucket"),
                        }
                roster_cache = list(
                    ensure_folklore_villager_roster(
                        int(session_id),
                        session=sess_obj,
                        persist_db=False,
                        read_only=bool(sess_obj is not None),
                    )
                    or []
                )
            except Exception:
                roster_cache = []
        return roster_cache

    leadership: list[Dict[str, Any]] = []
    for cand_ids, rank_num, default_title in slots:
        matched_name = ""
        matched_npc_id = cand_ids[0]
        matched_title = default_title
        for cid in cand_ids:
            c_rec = contact_rows.get(cid.lower())
            if c_rec and str(c_rec.get("name") or "").strip():
                matched_name = str(c_rec["name"]).strip()
                matched_npc_id = cid
                bi = _parse_json_dict(c_rec.get("basic_info_json"))
                matched_title = str(bi.get("rank_title") or bi.get("role") or default_title).strip()
                break
        if not matched_name:
            try:
                from mechanics.social.folklore_roster import _match_villager_entry
                r_entries = _get_roster_entries()
                for cid in cand_ids:
                    r_spec = _match_villager_entry(r_entries, cid)
                    if r_spec and str(r_spec.get("name") or "").strip():
                        matched_name = str(r_spec["name"]).strip()
                        matched_npc_id = str(r_spec.get("npc_id") or cid)
                        matched_title = str(r_spec.get("rank_title") or r_spec.get("role") or default_title).strip()
                        break
            except Exception:
                pass
        if matched_name:
            leadership.append({
                "rank": rank_num,
                "title": matched_title,
                "name": matched_name,
                "npc_id": matched_npc_id,
                "is_player": False,
                "is_vacant": False,
            })
    return leadership


def build_spirit_court_diplomacy(
    session_id: int,
    village_key: str,
    *,
    conn: Any = None,
) -> tuple[list[str], list[str]]:
    """
    Returns `(allied_faction_ids, rival_faction_ids)`:
    - Kitsune <-> Bunian allied
    - Kitsune & Bunian <-> Ghoul, Clandestine Syndicate, Occult Cult rivals
    - Ghoul <-> Kitsune, Bunian, Clandestine Syndicate, Occult Cult rivals
    """
    vk = str(village_key or "").strip().lower()
    synd_cult_ids: list[str] = []
    if session_id:
        with _uow_ctx(conn) as c:
            rows = c.execute(
                """SELECT faction_id FROM factions
                   WHERE session_id = ?
                     AND LOWER(COALESCE(category, '')) IN ('clandestine_faction', 'cult_faction')
                   ORDER BY id ASC""",
                (int(session_id),),
            ).fetchall()
            for r in rows:
                fid = str(r["faction_id"] or "").strip()
                if fid and fid not in synd_cult_ids:
                    synd_cult_ids.append(fid)
    for fallback_id in ("clandestine_faction", "cult_faction"):
        if not any(fallback_id in x.lower() for x in synd_cult_ids):
            synd_cult_ids.append(fallback_id)

    if vk == "kitsune":
        return ["faction_spirit_bunian"], ["faction_spirit_ghoul", *synd_cult_ids]
    if vk == "bunian":
        return ["faction_spirit_kitsune"], ["faction_spirit_ghoul", *synd_cult_ids]
    if vk == "ghoul":
        return [], ["faction_spirit_kitsune", "faction_spirit_bunian", *synd_cult_ids]
    return [], list(synd_cult_ids)


def sync_spirit_court_leadership_and_diplomacy(
    session_id: int,
    village_key: str,
    *,
    conn: Any = None,
) -> Dict[str, Any]:
    """Hydrates `leadership_roster_json`, `allied_faction_ids_json`, and `rival_faction_ids_json` on a court row."""
    vk = str(village_key or "").strip().lower()
    spec = SPIRIT_COURT_FACTIONS.get(vk)
    if not session_id or not spec:
        return {}
    with _uow_ctx(conn) as c:
        row = c.execute(
            "SELECT * FROM factions WHERE session_id = ? AND faction_id = ?",
            (int(session_id), spec["faction_id"]),
        ).fetchone()
        if not row:
            return {}
        roster = build_spirit_court_leadership_roster(int(session_id), vk, conn=c)
        allied, rivals = build_spirit_court_diplomacy(int(session_id), vk, conn=c)
        c.execute(
            """UPDATE factions
               SET leadership_roster_json = ?,
                   allied_faction_ids_json = ?,
                   rival_faction_ids_json = ?,
                   updated_at = ?
               WHERE session_id = ? AND faction_id = ?""",
            (
                json.dumps(roster),
                json.dumps(allied),
                json.dumps(rivals),
                time.time(),
                int(session_id),
                spec["faction_id"],
            ),
        )
        updated = c.execute(
            "SELECT * FROM factions WHERE session_id = ? AND faction_id = ?",
            (int(session_id), spec["faction_id"]),
        ).fetchone()
        return db._parse_faction_row(dict(updated)) if updated else {}


def ensure_spirit_court_faction_discovered(
    session_id: int,
    village_key: str,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Lazy-registers `faction_spirit_kitsune`, `faction_spirit_bunian`, or `faction_spirit_ghoul`
    with procedural session naming, live enclave leadership roster, and court diplomacy upon
    first village discovery. Never called at Turn 0; always non-joinable (`category='spirit_court'`).
    """
    spec = SPIRIT_COURT_FACTIONS.get(village_key)
    if not session_id or not spec:
        return None
    from .folklore_spirit_naming import ensure_session_spirit_procedural_names

    with _uow_ctx(conn) as c:
        proc_names = ensure_session_spirit_procedural_names(int(session_id), persist_db=True, conn=c, sync_world_nodes=True)
        proc_entry = proc_names.get(village_key) or {}
        eff_court_name = str(proc_entry.get("court_name") or spec["name"])

        existing = c.execute(
            "SELECT * FROM factions WHERE session_id = ? AND faction_id = ?",
            (int(session_id), spec["faction_id"]),
        ).fetchone()
        if existing:
            if eff_court_name and existing["name"] != eff_court_name:
                c.execute(
                    "UPDATE factions SET name = ? WHERE session_id = ? AND faction_id = ?",
                    (eff_court_name, int(session_id), spec["faction_id"]),
                )
            existing_r_raw = str(existing["leadership_roster_json"] or "").strip()
            existing_a_raw = str(existing["allied_faction_ids_json"] or "").strip()
            existing_v_raw = str(existing["rival_faction_ids_json"] or "").strip()
            if existing_r_raw in ("", "[]") or existing_a_raw in ("", "[]") or existing_v_raw in ("", "[]"):
                return sync_spirit_court_leadership_and_diplomacy(int(session_id), village_key, conn=c)
            refreshed = c.execute(
                "SELECT * FROM factions WHERE session_id = ? AND faction_id = ?",
                (int(session_id), spec["faction_id"]),
            ).fetchone()
            return db._parse_faction_row(dict(refreshed))

        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        start_rep = compute_spirit_court_starting_rep(int(session_id), village_key=village_key)
        leadership = build_spirit_court_leadership_roster(int(session_id), village_key, conn=c)
        allied, rivals = build_spirit_court_diplomacy(int(session_id), village_key, conn=c)
        now = time.time()
        c.execute(
            """INSERT OR IGNORE INTO factions (
                   session_id, faction_id, name, reputation_score, perks_json, notes,
                   category, hq_location_id, hq_node_id, hierarchy_template,
                   leadership_roster_json, rival_faction_ids_json, allied_faction_ids_json,
                   created_at, updated_at
               ) VALUES (?, ?, ?, ?, '{}', ?, 'spirit_court', ?, ?, 'spirit_court', ?, ?, ?, ?, ?)""",
            (
                int(session_id),
                spec["faction_id"],
                eff_court_name,
                start_rep,
                spec["notes"],
                spec["hq_location_id"],
                spec["hq_node_id"],
                json.dumps(leadership),
                json.dumps(rivals),
                json.dumps(allied),
                now,
                now,
            ),
        )

        def _rec(srs: Dict[str, Any]) -> None:
            courts = dict(srs.get("spirit_courts") or {})
            if village_key not in courts:
                courts[village_key] = {
                    "faction_id": spec["faction_id"],
                    "discovered_turn": eff_turn,
                    "starting_rep": start_rep,
                    "court_name": eff_court_name,
                }
            srs["spirit_courts"] = courts

        _mutate_spirit_realm_state(c, session_id, _rec)
        created = c.execute(
            "SELECT * FROM factions WHERE session_id = ? AND faction_id = ?",
            (int(session_id), spec["faction_id"]),
        ).fetchone()
        return db._parse_faction_row(dict(created)) if created else None


def adjust_spirit_court_reputation(
    session_id: int,
    village_key: str,
    delta: int,
    *,
    reason: str = "",
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """Adjusts a Spirit Court faction's reputation score [-100, 100], logs rollback delta, and checks Guest-Cottage unlock."""
    spec = SPIRIT_COURT_FACTIONS.get(village_key)
    if not session_id or not spec:
        return {"ok": False}
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        fac = ensure_spirit_court_faction_discovered(int(session_id), village_key, turn_number=eff_turn, conn=c)
        old_rep = int((fac or {}).get("reputation_score") or 0)
        eff_delta = int(delta or 0)
        event_rep_bonus = 0
        if eff_delta > 0 and not str(reason or "").startswith(("sparring_drill_", "rollback")):
            from mechanics.world.world_events.spirit_realm_events import get_spirit_event_rep_bonus
            event_rep_bonus = get_spirit_event_rep_bonus(int(session_id), village_key)
            eff_delta += event_rep_bonus
        new_rep = max(-100, min(100, old_rep + eff_delta))
        applied_delta = new_rep - old_rep
        if applied_delta != 0:
            c.execute(
                "UPDATE factions SET reputation_score = ?, updated_at = ? WHERE session_id = ? AND faction_id = ?",
                (new_rep, time.time(), int(session_id), spec["faction_id"]),
            )

            def _log(srs: Dict[str, Any]) -> None:
                ledger = list(srs.get("rep_ledger") or [])
                ledger.append({
                    "turn": eff_turn,
                    "village_key": village_key,
                    "prev_score": old_rep,
                    "delta": applied_delta,
                    "reason": str(reason or ""),
                })
                srs["rep_ledger"] = ledger[-60:]

            _mutate_spirit_realm_state(c, session_id, _log)
        cottage = maybe_grant_spirit_guest_cottage(int(session_id), village_key, turn_number=eff_turn, conn=c)
        return {
            "ok": True,
            "faction_id": spec["faction_id"],
            "old_rep": old_rep,
            "new_rep": new_rep,
            "delta": applied_delta,
            "event_rep_bonus": event_rep_bonus,
            "guest_cottage": cottage,
        }


def is_ghoul_council_distrusted(session_id: int) -> bool:
    """Returns True while Ghoul Court Council reputation is < 0 (Distrusted)."""
    if not session_id:
        return True
    spec = SPIRIT_COURT_FACTIONS["ghoul"]
    fac_row = db.get_faction(int(session_id), spec["faction_id"])
    if fac_row is None:
        return compute_spirit_court_starting_rep(int(session_id), village_key="ghoul") < 0
    return int(fac_row.get("reputation_score") or 0) < 0


def get_effective_village_standing(
    session_id: int,
    village_key: str,
    *,
    court_only: bool = False,
) -> int:
    """
    Computes effective standing for a Spirit Village:
    - Kitsune & Bunian: `max(court_rep, max_villager_affinity)`
    - Ghoul: Personal NPC affinity (including the Heir's +10 opening fascination)
      is strictly decoupled from Ghoul Council reputation, so Ghoul Court standing
      governs Distrusted gates, shop discounts, and Guest-Suite unlock independently.
    """
    spec = SPIRIT_COURT_FACTIONS.get(village_key)
    if not session_id or not spec:
        return 0
    fac_row = db.get_faction(int(session_id), spec["faction_id"])
    has_court = fac_row is not None
    court_rep = int((fac_row or {}).get("reputation_score") or 0)
    if village_key == "ghoul":
        return court_rep if has_court else compute_spirit_court_starting_rep(int(session_id), village_key="ghoul")
    if court_only:
        return court_rep if has_court else 0

    max_aff: Optional[int] = None
    for c in (db.get_contacts(int(session_id), resolve_relations=False, ensure_scene=False) or []):
        if not isinstance(c, Mapping):
            continue
        bi = _parse_json_dict(c.get("basic_info"))
        race = str(c.get("race") or bi.get("race") or "").lower()
        fv = str(bi.get("folklore_village") or "").strip().lower()
        is_match = (fv == village_key) or (
            village_key == "kitsune" and "kitsune" in race
        ) or (
            village_key == "bunian" and ("bunian" in race or "orang_bunian" in race)
        )
        if not is_match:
            continue
        aff = int(c.get("relationship_score") or 0)
        if max_aff is None or aff > max_aff:
            max_aff = aff

    if has_court and max_aff is not None:
        return max(court_rep, max_aff)
    if has_court:
        return court_rep
    return max_aff if max_aff is not None else 0


def get_spirit_court_discount_multiplier(session_id: int, village_key: str) -> float:
    """Returns standard gold shop price multiplier from `get_effective_village_standing` (1.15x markup < -10)."""
    standing = get_effective_village_standing(session_id, village_key)
    if standing >= 70:
        return 0.85
    if standing >= 50:
        return 0.90
    if standing >= 20:
        return 0.95
    if standing < -10:
        return 1.15
    return 1.0


def maybe_grant_spirit_guest_cottage(
    session_id: int,
    village_key: str,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Grants the permanent court Guest-Cottage deed (`prop_kitsune_guest_villa`,
    `prop_bunian_guest_house`, or `prop_ghoul_guest_manor`, `price_paid=0`,
    `rest_multiplier=1.25`) in `player_properties` and unhides the facility at standing >= 70.
    """
    spec = SPIRIT_GUEST_COTTAGE_SPEC.get(village_key)
    if not session_id or not spec:
        return None
    if get_effective_village_standing(int(session_id), village_key) < 70:
        return None

    with _uow_ctx(conn) as c:
        existing = c.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), spec["property_id"]),
        ).fetchone()
        if existing:
            return None

        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        s_row = c.execute(
            "SELECT current_day, character_id, host_user_id FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchone()
        c_day = int((s_row["current_day"] if s_row else 1) or 1)
        buyer_cid = int(s_row["character_id"] or 0) if (s_row and s_row["character_id"]) else None
        now = time.time()

        c.execute(
            """INSERT INTO player_properties (
                   session_id, property_id, facility_node_id, zone_id, tier,
                   price_paid, is_primary, is_starter, spare_keys_json,
                   purchased_turn, purchased_day, buyer_character_id, created_at, updated_at
               ) VALUES (?, ?, ?, ?, 0, 0, 0, 0, '{}', ?, ?, ?, ?, ?)""",
            (
                int(session_id),
                spec["property_id"],
                spec["facility_node_id"],
                spec["zone_id"],
                eff_turn,
                c_day,
                buyer_cid,
                now,
                now,
            ),
        )
        for nid in (spec["facility_node_id"], *spec["room_ids"]):
            r = c.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (int(session_id), nid),
            ).fetchone()
            if r:
                st = _parse_json_dict(r["state_json"])
                if not st.get("discovered") or not int(st.get("discovered_turn") or 0):
                    st["discovered_turn"] = eff_turn
                st["is_hidden"] = False
                st["discovered"] = True
                st["unlocked_permanent"] = True
                st["unlocked_turn"] = eff_turn
                st["deed_owned"] = True
                st["granted_by_standing"] = True
                c.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(st), int(session_id), nid),
                )

        def _stamp(srs: Dict[str, Any]) -> None:
            cottages = dict(srs.get("granted_cottages") or {})
            cottages[village_key] = eff_turn
            srs["granted_cottages"] = cottages

        _mutate_spirit_realm_state(c, session_id, _stamp)
        return {
            "granted": True,
            "village_key": village_key,
            "property_id": spec["property_id"],
            "facility_node_id": spec["facility_node_id"],
            "name": spec["name"],
            "rest_multiplier": spec["rest_multiplier"],
            "turn_number": eff_turn,
        }


def resolve_spirit_sparring_drill(
    session_id: int,
    node_id: str,
    *,
    stat: str = "AGI",
    user_id: Optional[int] = None,
    turn_number: Optional[int] = None,
    roll_override: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Deterministic sparring drill at `sub_kitsune_sparring_yard`, `sub_bunian_silat_courtyard`,
    or `sub_ghoul_sparring_pit`. Sanctuary Pact exempt; zero HP death risk; grants XP,
    +3 Spirit Court rep/affinity, and temporary buff.
    """
    village_key = SPIRIT_SPARRING_ROOMS.get(str(node_id or "").strip(), "")
    if not session_id or not village_key:
        return {"ok": False, "reason": "not_sparring_arena"}

    stat_u = str(stat or "AGI").strip().upper()
    if stat_u not in ("AGI", "STR", "PER"):
        stat_u = "STR" if village_key == "ghoul" else "AGI"

    from mechanics.world.world_events.spirit_realm_events import get_spirit_event_sparring_bonuses

    sess = db.get_session(int(session_id)) or {}
    eff_uid = int(user_id or sess.get("host_user_id") or 0)
    char = db.get_character(eff_uid, session_id=int(session_id)) if eff_uid else None
    stat_val = int((char or {}).get(stat_u.lower(), (char or {}).get("agi", 5)) or 5)
    roll_val = int(roll_override) if roll_override is not None else min(20, stat_val + 6)
    succeeded = roll_val >= 11
    ev_bonus_xp, ev_bonus_rep = get_spirit_event_sparring_bonuses(int(session_id), village_key)
    xp_award = (25 if succeeded else 15) + ev_bonus_xp
    rep_award = 3 + ev_bonus_rep
    buff_name = (
        "Fox-Step Focus"
        if village_key == "kitsune"
        else ("Silat Wind-Stance" if village_key == "bunian" else "Ossuary Pack Reflex")
    )

    with db.UnitOfWork() as conn:
        eff_turn = _resolve_turn_num(conn, session_id, turn_number)
        if eff_uid and char and int(char.get("id") or 0) > 0:
            db.add_xp(eff_uid, xp_award, session_id=int(session_id), character_id=int(char["id"]))
        rep_res = adjust_spirit_court_reputation(
            int(session_id),
            village_key,
            rep_award,
            reason=f"sparring_drill_{stat_u.lower()}",
            turn_number=eff_turn,
            conn=conn,
        )
        mentor_candidates = (
            ("folklore_kitsune_guardian", "folklore_kitsune_blade_instructor", "folklore_kitsune_warden")
            if village_key == "kitsune"
            else (
                ("folklore_bunian_guardian", "folklore_bunian_silat_master", "folklore_bunian_warden")
                if village_key == "bunian"
                else ("folklore_ghoul_pit_champion", "folklore_ghoul_elder")
            )
        )
        c_row = None
        for mentor_key in mentor_candidates:
            c_row = conn.execute(
                "SELECT id, name, relationship_score FROM contacts WHERE session_id = ? AND npc_id = ? LIMIT 1",
                (int(session_id), mentor_key),
            ).fetchone()
            if c_row:
                break
        if not c_row:
            race_pat = "%kitsune%" if village_key == "kitsune" else ("%bunian%" if village_key == "bunian" else "%ghoul%")
            c_row = conn.execute(
                "SELECT id, name, relationship_score FROM contacts WHERE session_id = ? AND LOWER(COALESCE(basic_info_json, '')) LIKE ? ORDER BY id ASC LIMIT 1",
                (int(session_id), race_pat),
            ).fetchone()
        mentor_name = ""
        if c_row:
            mentor_name = str(c_row["name"] or "")
            new_aff = min(100, int(c_row["relationship_score"] or 0) + 3)
            conn.execute("UPDATE contacts SET relationship_score = ? WHERE id = ?", (new_aff, int(c_row["id"])))

        def _buff(srs: Dict[str, Any]) -> None:
            srs["active_sparring_buff"] = {
                "name": buff_name,
                "village_key": village_key,
                "stat": stat_u,
                "expires_turn": eff_turn + 6,
                "granted_turn": eff_turn,
            }

        _mutate_spirit_realm_state(conn, session_id, _buff)

    return {
        "ok": True,
        "village_key": village_key,
        "stat": stat_u,
        "succeeded": succeeded,
        "xp_gained": xp_award,
        "rep_gained": int(rep_res.get("delta") or rep_award),
        "event_bonus_xp": ev_bonus_xp,
        "event_bonus_rep": ev_bonus_rep,
        "affinity_gained": 3 if mentor_name else 0,
        "mentor_name": mentor_name,
        "buff_name": buff_name,
        "hp_damage": 0,
        "new_court_rep": rep_res.get("new_rep", 0),
    }


__all__ = [
    "SPIRIT_REALM_ID",
    "SPIRIT_CROSSROADS_ZONE_ID",
    "SPIRIT_WILDS_ZONE_ID",
    "SPIRIT_PEAKS_ZONE_ID",
    "SPIRIT_MIRE_ZONE_ID",
    "SPIRIT_BONEYARD_ZONE_ID",
    "SPIRIT_FRONTIER_ZONE_IDS",
    "SPIRIT_VILLAGE_KEYS",
    "WILDS_SAFE_RESCUE_NODE_ID",
    "CROSSROADS_TEA_FALLBACK_NODE_ID",
    "CHINATOWN_SHORTCUT_SPIRIT_NODE",
    "CHINATOWN_SHORTCUT_HUMAN_NODE",
    "CHINATOWN_OFFERING_GOLD",
    "SPIRIT_ZONE_BY_VILLAGE",
    "SPIRIT_VILLAGE_BY_ZONE",
    "SPIRIT_VILLAGE_PUBLIC_FACILITIES",
    "SPIRIT_GUEST_COTTAGE_SPEC",
    "SPIRIT_COURT_FACTIONS",
    "SPIRIT_SPARRING_ROOMS",
    "ALL_SPIRIT_GUEST_FACILITY_IDS",
    "ALL_SPIRIT_GUEST_PROPERTY_IDS",
    "get_spirit_realm_state",
    "compute_spirit_court_starting_rep",
    "ensure_spirit_court_faction_discovered",
    "build_spirit_court_leadership_roster",
    "build_spirit_court_diplomacy",
    "sync_spirit_court_leadership_and_diplomacy",
    "adjust_spirit_court_reputation",
    "is_ghoul_council_distrusted",
    "get_effective_village_standing",
    "get_spirit_court_discount_multiplier",
    "maybe_grant_spirit_guest_cottage",
    "resolve_spirit_sparring_drill",
]
