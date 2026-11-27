"""
mechanics/world/locations/folklore_spirit_naming.py
===================================================
Deterministic per-session procedural naming for the 3 Veiled Spirit Realm courts
and enclave zones (`kitsune`, `bunian`, `ghoul`), persisted inside
`sessions.extra_json['spirit_realm_state']['procedural_names']` and synced onto
`world_nodes.name`, `session_locations.zone_name`, and `factions.name` without
mutating internal node IDs or facility/room names.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional

import db

PROCEDURAL_SPIRIT_COURT_POOLS: Dict[str, tuple[tuple[str, str], ...]] = {
    "kitsune": (
        ("Shirakawa Inari Myōbu Court", "Sato-no-Inari — Crimson Foxfire Enclave"),
        ("Fushimi Byakko Shrine-Court", "Sato-no-Inari — Silver Cedar Shrine-Vale"),
        ("Kurama Tenko Sovereign Court", "Sato-no-Inari — Lantern Torii Hollow"),
        ("Kasuga Kitsunebi Court", "Sato-no-Inari — Moonlit Myōbu Enclave"),
        ("Tōka Kugitsune Shrine-Conclave", "Sato-no-Inari — Amber Torii Cloister"),
        ("Atago Shinku Myōbu Court", "Sato-no-Inari — Whispering Maple Sanctuary"),
        ("Kifune Hoshi-Inari Court", "Sato-no-Inari — Star-Water Shrine Village"),
        ("Hiei Byakko Lantern-Court", "Sato-no-Inari — Frosted Camellia Enclave"),
    ),
    "bunian": (
        ("Kesultanan Seri Kayangan", "Kampung Kayangan — Cempaka Mist Domain"),
        ("Istana Puteri Ledang", "Kampung Kayangan — Gilded Songket Enclave"),
        ("Majlis Diraja Inderapura", "Kampung Kayangan — Veiled Banyan Court"),
        ("Kerajaan Cempaka Ghaib", "Kampung Kayangan — Silver Monsoon Sanctum"),
        ("Balairung Seri Taming", "Kampung Kayangan — Luminous Orchid Kingdom"),
        ("Mahkamah Embun Nusantara", "Kampung Kayangan — Royal Keris & Dew Vale"),
        ("Istana Seri Nilam", "Kampung Kayangan — Indigo Canopy Village"),
        ("Keraton Bayu Kayangan", "Kampung Kayangan — Floating Mist Pavilion"),
    ),
    "ghoul": (
        ("Majlis al-Ghūl", "The Pale Ossuary — Cypress & Slate Necropolis"),
        ("Dar al-Kafan", "The Pale Ossuary — Ashen Columbarium Ward"),
        ("Al-Qabr Covenant", "The Pale Ossuary — Black-Marble Barrow Court"),
        ("Bayt al-Barzakh", "The Pale Ossuary — Twilight Myrrh Enclave"),
        ("Diwan al-Jana'iz", "The Pale Ossuary — Shrouded Catacomb Precinct"),
        ("Majlis al-Ramad", "The Pale Ossuary — Cold-Lantern Marble City"),
        ("Dar al-Nawah", "The Pale Ossuary — Weeping Cypress Sanctum"),
        ("Al-Maqbara Synod", "The Pale Ossuary — Sunken Vaults & Cloister"),
    ),
}

_ZONE_ID_BY_VILLAGE: Dict[str, str] = {
    "kitsune": "zone_spirit_kitsune",
    "bunian": "zone_spirit_bunian",
    "ghoul": "zone_spirit_ghoul",
}

_FACTION_ID_BY_VILLAGE: Dict[str, str] = {
    "kitsune": "faction_spirit_kitsune",
    "bunian": "faction_spirit_bunian",
    "ghoul": "faction_spirit_ghoul",
}


def generate_procedural_spirit_names(session_id: int) -> Dict[str, Dict[str, str]]:
    """Deterministically picks per-session Court Faction Name + Enclave Zone Title for all 3 enclaves."""
    sid = int(session_id or 0)
    out: Dict[str, Dict[str, str]] = {}
    for v_key, pool in PROCEDURAL_SPIRIT_COURT_POOLS.items():
        digest = hashlib.md5(f"hikayat_spirit_naming:{sid}:{v_key}".encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(pool)
        court_name, zone_title = pool[idx]
        out[v_key] = {
            "court_name": court_name,
            "zone_title": zone_title,
            "zone_id": _ZONE_ID_BY_VILLAGE[v_key],
            "faction_id": _FACTION_ID_BY_VILLAGE[v_key],
        }
    return out


def _sync_procedural_names_to_db(
    session_id: int,
    names_map: Dict[str, Dict[str, str]],
    *,
    conn: Any = None,
) -> None:
    """Writes zone titles onto enclave `world_nodes` & `session_locations` and court names onto `factions`."""
    sid = int(session_id or 0)
    if sid <= 0:
        return

    def _apply(c: Any) -> None:
        for v_key, entry in names_map.items():
            z_id = _ZONE_ID_BY_VILLAGE.get(v_key)
            f_id = _FACTION_ID_BY_VILLAGE.get(v_key)
            z_title = str(entry.get("zone_title") or "").strip()
            c_name = str(entry.get("court_name") or "").strip()
            if z_id and z_title:
                c.execute(
                    "UPDATE world_nodes SET name = ? WHERE session_id = ? AND node_id = ? AND node_type = 'ZONE'",
                    (z_title, sid, z_id),
                )
                child_facs = c.execute(
                    "SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id = ? AND node_type = 'FACILITY'",
                    (sid, z_id),
                ).fetchall()
                fac_ids = [str(r["node_id"]) for r in child_facs if r and r["node_id"]]
                if fac_ids:
                    placeholders = ", ".join("?" for _ in fac_ids)
                    c.execute(
                        f"UPDATE session_locations SET zone_name = ? WHERE session_id = ? AND location_id IN ({placeholders})",
                        (z_title, sid, *fac_ids),
                    )
                    room_rows = c.execute(
                        f"SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id IN ({placeholders}) AND node_type = 'ROOM'",
                        (sid, *fac_ids),
                    ).fetchall()
                    room_ids = [str(r["node_id"]) for r in room_rows if r and r["node_id"]]
                    if room_ids:
                        r_ph = ", ".join("?" for _ in room_ids)
                        c.execute(
                            f"UPDATE session_locations SET zone_name = ? WHERE session_id = ? AND location_id IN ({r_ph})",
                            (z_title, sid, *room_ids),
                        )
            if f_id and c_name:
                c.execute(
                    "UPDATE factions SET name = ? WHERE session_id = ? AND faction_id = ?",
                    (c_name, sid, f_id),
                )

    if conn is not None:
        _apply(conn)
    elif not db.is_in_readonly_uow():
        with db.UnitOfWork() as uow_conn:
            _apply(uow_conn)


def ensure_session_spirit_procedural_names(
    session_id: int,
    *,
    persist_db: bool = True,
    conn: Any = None,
    sync_world_nodes: bool = True,
    preserve_discovered_names: bool = False,
    naming_seed_session_id: int | None = None,
) -> Dict[str, Dict[str, str]]:
    """
    Loads or initializes per-session procedural Court & Enclave Zone names inside
    `sessions.extra_json['spirit_realm_state']['procedural_names']`.
    Preserves any already-populated entries verbatim while backfilling missing keys;
    when `preserve_discovered_names=True`, captures already-discovered pre-v64 zone/court names.
    """
    sid = int(session_id or 0)
    seed_sid = int(naming_seed_session_id) if naming_seed_session_id else sid
    generated = generate_procedural_spirit_names(seed_sid)
    if sid <= 0:
        return generated

    sess: Dict[str, Any] = {}
    if conn is not None:
        s_row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        if s_row:
            sess = {"extra_json": s_row["extra_json"] if hasattr(s_row, "keys") else s_row[0]}
    else:
        sess = db.get_session(sid) or {}
    raw_extra = sess.get("extra")
    if not isinstance(raw_extra, dict) and isinstance(sess.get("extra_json"), str) and sess["extra_json"].strip():
        try:
            raw_extra = json.loads(sess["extra_json"])
        except Exception:
            raw_extra = {}
    extra_dict = dict(raw_extra) if isinstance(raw_extra, dict) else {}
    sr_state = dict(extra_dict.get("spirit_realm_state") or sess.get("spirit_realm_state") or {})
    existing_raw = sr_state.get("procedural_names")
    existing = dict(existing_raw) if isinstance(existing_raw, dict) else {}

    def _capture_live_names(v_k: str, gen_e: Dict[str, str]) -> Optional[Dict[str, str]]:
        z_id = _ZONE_ID_BY_VILLAGE.get(v_k, "")
        f_id = _FACTION_ID_BY_VILLAGE.get(v_k, "")
        c_obj = conn
        if c_obj is not None:
            z_row = c_obj.execute(
                "SELECT name, state_json FROM world_nodes WHERE session_id = ? AND node_id = ? AND node_type = 'ZONE'",
                (sid, z_id),
            ).fetchone()
            f_row = c_obj.execute(
                "SELECT name FROM factions WHERE session_id = ? AND faction_id = ?",
                (sid, f_id),
            ).fetchone()
        else:
            with db.get_conn() as ro_c:
                z_row = ro_c.execute(
                    "SELECT name, state_json FROM world_nodes WHERE session_id = ? AND node_id = ? AND node_type = 'ZONE'",
                    (sid, z_id),
                ).fetchone()
                f_row = ro_c.execute(
                    "SELECT name FROM factions WHERE session_id = ? AND faction_id = ?",
                    (sid, f_id),
                ).fetchone()
        cur_f_name = str((f_row["name"] if f_row else "") or "").strip()
        cur_z_name = str((z_row["name"] if z_row else "") or "").strip()
        z_disc = False
        if z_row and z_row["state_json"]:
            try:
                z_st = json.loads(z_row["state_json"] or "{}")
                z_disc = bool(isinstance(z_st, dict) and (not z_st.get("is_hidden", True) or z_st.get("discovered")))
            except Exception:
                z_disc = False
        if cur_f_name or z_disc:
            return {
                "court_name": cur_f_name or gen_e["court_name"],
                "zone_title": (cur_z_name if z_disc and cur_z_name else gen_e["zone_title"]),
                "zone_id": z_id,
                "faction_id": f_id,
            }
        return None

    merged: Dict[str, Dict[str, str]] = {}
    changed = not isinstance(existing_raw, dict)
    for v_key, gen_entry in generated.items():
        cur_entry = existing.get(v_key)
        if isinstance(cur_entry, dict) and cur_entry.get("court_name") and cur_entry.get("zone_title"):
            merged[v_key] = {
                "court_name": str(cur_entry["court_name"]),
                "zone_title": str(cur_entry["zone_title"]),
                "zone_id": str(cur_entry.get("zone_id") or gen_entry["zone_id"]),
                "faction_id": str(cur_entry.get("faction_id") or gen_entry["faction_id"]),
            }
        else:
            captured = _capture_live_names(v_key, gen_entry) if preserve_discovered_names else None
            merged[v_key] = captured if captured else dict(gen_entry)
            changed = True

    if persist_db and not db.is_in_readonly_uow():
        if changed:
            sr_state["procedural_names"] = merged
            extra_dict["spirit_realm_state"] = sr_state
            if conn is not None:
                conn.execute(
                    "UPDATE sessions SET extra_json = ? WHERE id = ?",
                    (json.dumps(extra_dict), sid),
                )
            else:
                db.update_session(sid, extra={"spirit_realm_state": sr_state})
        if sync_world_nodes:
            _sync_procedural_names_to_db(sid, merged, conn=conn)
    return merged


def get_spirit_court_procedural_name(session_id: int, village_key: str) -> str:
    """Returns the procedural Court Faction Name for `village_key` in this session."""
    v_low = str(village_key or "").strip().lower()
    names = ensure_session_spirit_procedural_names(session_id, persist_db=False, sync_world_nodes=False)
    entry = names.get(v_low)
    if entry and entry.get("court_name"):
        return str(entry["court_name"])
    return f"The {v_low.title()} Spirit Court"


def get_spirit_enclave_zone_title(session_id: int, village_key: str) -> str:
    """Returns the procedural Enclave Zone Title for `village_key` in this session."""
    v_low = str(village_key or "").strip().lower()
    names = ensure_session_spirit_procedural_names(session_id, persist_db=False, sync_world_nodes=False)
    entry = names.get(v_low)
    if entry and entry.get("zone_title"):
        return str(entry["zone_title"])
    return f"Veiled {v_low.title()} Enclave"


__all__ = [
    "PROCEDURAL_SPIRIT_COURT_POOLS",
    "ensure_session_spirit_procedural_names",
    "generate_procedural_spirit_names",
    "get_spirit_court_procedural_name",
    "get_spirit_enclave_zone_title",
]
