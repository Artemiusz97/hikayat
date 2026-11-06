from __future__ import annotations
import db
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list

MAX_SAVE_SLOTS_PER_CHAR = 6

def _rewrite_session_key_id(key_str: str, old_session_id: int | None, new_session_id: int) -> str:
    """Safely rewrites the embedded session_id segment in household_key / commitment_key without corrupting timestamps."""
    if not key_str or not old_session_id:
        return key_str or ""
    old_tok = re.escape(str(int(old_session_id)))
    return re.sub(rf"(?:(?<=^)|(?<=[:_\-])){old_tok}(?=$|[:_\-])", str(int(new_session_id)), str(key_str), count=1)


def count_character_adventure_saves(character_id: int) -> int:
    """Returns the total number of saved checkpoints for a specific character."""
    if not character_id:
        return 0
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM adventure_saves WHERE character_id = ?",
            (character_id,)
        ).fetchone()
        return row["cnt"] if row else 0

def save_adventure_slot(user_id: int, slot_name: str, overwrite: bool = False) -> dict:
    """Creates or overwrites a named checkpoint save slot for the user's active character."""
    import re
    cleaned_slot = (slot_name or "").strip()
    if not cleaned_slot or len(cleaned_slot) > 32:
        raise ValueError("Save slot name must be between 1 and 32 characters.")
    if not re.match(r"^[\w\s\-]+$", cleaned_slot, re.UNICODE):
        raise ValueError("Slot name contains invalid characters. Use letters, numbers, spaces, hyphens, or underscores.")

    char = db.get_character(user_id)
    if not char:
        raise ValueError("You don't have an active character. Create one with `/character create` first.")
    char_id = char["id"]

    session_id = db.get_active_session_id_for_user(user_id)
    if not session_id:
        raise ValueError("You are not currently in an active adventure to save.")

    with get_conn() as conn:
        sess_row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess_row or sess_row["status"] != "active":
            raise ValueError("Your current adventure session is not active.")
        sess_dict = dict(sess_row)

        existing = conn.execute(
            "SELECT id, slot_name FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char_id, cleaned_slot)
        ).fetchone()

        if existing and not overwrite:
            return {
                "status": "exists",
                "slot_name": existing["slot_name"],
                "message": f"Save slot **{existing['slot_name']}** already exists. Overwrite?"
            }

        total_saves = conn.execute(
            "SELECT COUNT(*) as cnt FROM adventure_saves WHERE character_id = ?",
            (char_id,)
        ).fetchone()["cnt"]
        if not existing and total_saves >= MAX_SAVE_SLOTS_PER_CHAR:
            raise ValueError(f"Maximum save slots reached ({MAX_SAVE_SLOTS_PER_CHAR} slots per character). Delete an older save first.")

        # Gather all child table data
        child_data = {}
        for tbl in SESSION_CHILD_TABLES:
            if tbl == "session_members":
                continue
            try:
                rows = conn.execute(f"SELECT * FROM {tbl} WHERE session_id = ?", (session_id,)).fetchall()
                cleaned_rows = []
                for r in rows:
                    rd = dict(r)
                    if tbl == "households":
                        rd["_orig_household_id"] = rd.get("id")
                    elif tbl == "contacts":
                        rd["_orig_contact_id"] = rd.get("id")
                    elif tbl == "commitments_ledger":
                        rd["_orig_commitment_id"] = rd.get("id")
                    elif tbl == "session_clues":
                        rd["_orig_clue_id"] = rd.get("id")
                    rd.pop("id", None)
                    cleaned_rows.append(rd)
                child_data[tbl] = cleaned_rows
            except Exception:
                child_data[tbl] = []

        # Gather character adventure inventory (including session-scoped quest items where character_id IS NULL)
        inv_rows = conn.execute(
            "SELECT * FROM inventory WHERE character_id = ? OR (character_id IS NULL AND user_id = ?)",
            (char_id, user_id),
        ).fetchall()
        cleaned_inv = []
        for r in inv_rows:
            rd = dict(r)
            rd.pop("id", None)
            cleaned_inv.append(rd)

        # Character adventure vitals & 3-axis resonance snapshot
        char_state = {
            "hp": char["hp"],
            "mp": char["mp"],
            "gold": char["gold"],
            "status_effects": char.get("status_effects", "[]"),
            "days_adventured": char.get("days_adventured", 1),
            "attribute": char.get("attribute"),
            "combat_archetype": char.get("combat_archetype"),
            "ability_medium": char.get("ability_medium"),
            "skill_progress": char.get("skill_progress", "{}"),
            "learned_spells": char.get("learned_spells", "[]"),
            "joined_faction_id": char.get("joined_faction_id", ""),
            "faction_rank": char.get("faction_rank", 0),
            "faction_title": char.get("faction_title", ""),
        }

        # Eagerly capture world_ending_anomaly in extra_json if scenario is anomalous incursions
        try:
            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(sess_dict.get("scenario", "")):
                extra_raw = sess_dict.get("extra_json") or "{}"
                extra_dict = json.loads(extra_raw) if isinstance(extra_raw, str) else dict(extra_raw or {})
                if "world_ending_anomaly" not in extra_dict:
                    import namegen
                    extra_dict["world_ending_anomaly"] = namegen.generate_world_ending_anomaly_profile(hash_val=int(session_id or 1))
                    sess_dict["extra_json"] = json.dumps(extra_dict)
                    conn.execute("UPDATE sessions SET extra_json = ? WHERE id = ?", (sess_dict["extra_json"], session_id))
        except Exception:
            pass

        snapshot = {
            "version": 1,
            "session": sess_dict,
            "child_tables": child_data,
            "character_state": char_state,
            "inventory": cleaned_inv
        }
        snapshot_json = json.dumps(snapshot)

        scenario = sess_dict.get("scenario", "fantasy")
        scene_title = sess_dict.get("scene_title") or "Adventure Continues"
        narrative_snippet = (sess_dict.get("narrative") or "")[:250].strip()
        current_location = sess_dict.get("current_location") or ""
        now = time.time()

        if existing:
            conn.execute(
                """UPDATE adventure_saves
                   SET slot_name = ?, scenario = ?, scene_title = ?, narrative_snippet = ?,
                       current_location = ?, saved_at = ?, snapshot_data = ?
                   WHERE id = ?""",
                (cleaned_slot, scenario, scene_title, narrative_snippet, current_location, now, snapshot_json, existing["id"])
            )
            save_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO adventure_saves (user_id, character_id, slot_name, scenario, scene_title,
                                               narrative_snippet, current_location, saved_at, snapshot_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, char_id, cleaned_slot, scenario, scene_title, narrative_snippet, current_location, now, snapshot_json)
            )
            save_id = cur.lastrowid

    return {
        "status": "saved",
        "save_id": save_id,
        "slot_name": cleaned_slot,
        "scenario": scenario,
        "scene_title": scene_title,
        "narrative_snippet": narrative_snippet,
        "current_location": current_location,
        "saved_at": now
    }

def load_adventure_slot(user_id: int, slot_name: str) -> dict:
    """Restores an adventure save slot into a fresh active session for the character."""
    char = db.get_character(user_id)
    if not char:
        raise ValueError("You don't have an active character. Create one with `/character create` first.")
    char_id = char["id"]

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char_id, (slot_name or "").strip())
        ).fetchone()

        if not row:
            raise ValueError(f"No save slot found named '{slot_name}'. Use `/adventure saves` to view available saves.")

        snapshot = json.loads(row["snapshot_data"])
        sess_dict = snapshot["session"]
        child_data = snapshot.get("child_tables", {})
        char_state = snapshot.get("character_state", {})
        saved_inv = snapshot.get("inventory", [])

        # If user has an active session in progress, retire it
        active_sess_id = char.get("active_session_id")
        if active_sess_id:
            conn.execute("UPDATE sessions SET status='finished', updated_at=? WHERE id=?", (time.time(), active_sess_id))
            conn.execute("UPDATE characters SET active_session_id=NULL WHERE id=?", (char_id,))

        # Restore session with fresh ID, timestamp, and active status
        now = time.time()
        to = sess_dict.get("turn_order")
        if isinstance(to, str):
            try:
                to = json.loads(to)
            except Exception:
                to = [user_id]
        if not to or user_id not in to:
            to = [user_id]

        sess_data = dict(sess_dict)
        sess_data.pop("id", None)
        sess_data.setdefault("schema_epoch", 1)
        sess_data.setdefault("mode", "solo")
        sess_data.setdefault("capacity", 1)
        if "turn_count" not in sess_data or sess_data.get("turn_count") is None:
            raw_hist = sess_data.get("history_json") or "[]"
            try:
                hist_obj = json.loads(raw_hist) if isinstance(raw_hist, str) else list(raw_hist)
                if isinstance(hist_obj, list):
                    action_turns = [h for h in hist_obj if not (isinstance(h, dict) and h.get("type") == "scene")]
                    sess_data["turn_count"] = len(action_turns)
                else:
                    sess_data["turn_count"] = 0
            except Exception:
                sess_data["turn_count"] = 0
        sess_data.setdefault("last_digested_turn", 0)
        sess_data["status"] = "active"
        sess_data["created_at"] = now
        sess_data["updated_at"] = now
        sess_data["turn_order"] = json.dumps(to)

        # Filter strictly to columns present in live sessions table
        valid_session_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        sess_data = {k: v for k, v in sess_data.items() if k in valid_session_cols}

        # Make sure any dict/list fields are serialized
        for k, v in sess_data.items():
            if isinstance(v, (dict, list)):
                sess_data[k] = json.dumps(v)

        cols = list(sess_data.keys())
        placeholders = ",".join("?" * len(cols))
        col_str = ",".join(cols)
        cur = conn.execute(f"INSERT INTO sessions ({col_str}) VALUES ({placeholders})", list(sess_data.values()))
        new_session_id = cur.lastrowid

        # Register session_members
        conn.execute(
            "INSERT OR IGNORE INTO session_members (session_id, user_id, joined_at) VALUES (?, ?, ?)",
            (new_session_id, user_id, now)
        )

        # 1. Restore households first to obtain fresh autoincrement IDs and remap session keys
        household_id_map: dict[int, int] = {}
        household_surname_map: dict[str, int] = {}
        contact_id_map: dict[int, int] = {}
        commitment_id_map: dict[int, int] = {}
        clue_id_map: dict[int, int] = {}
        old_session_id = sess_dict.get("id")

        table_cols_cache: dict[str, set[str]] = {}
        def _valid_cols(t_name: str) -> set[str]:
            if t_name not in table_cols_cache:
                table_cols_cache[t_name] = {
                    r["name"] for r in conn.execute(f"PRAGMA table_info({t_name})").fetchall()
                }
            return table_cols_cache[t_name]

        hh_rows = child_data.get("households", [])
        hh_valid = _valid_cols("households")
        for r in hh_rows:
            row_dict = {k: v for k, v in dict(r).items() if not str(k).startswith("_orig_")}
            orig_hid = r.get("_orig_household_id")
            row_dict["session_id"] = new_session_id

            # Safely remap household_key if it contained the old session ID
            hh_key = row_dict.get("household_key", "")
            if old_session_id and hh_key:
                row_dict["household_key"] = _rewrite_session_key_id(hh_key, old_session_id, new_session_id)

            row_dict = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row_dict.items() if k in hh_valid and k != "id"}
            c_names = ",".join(row_dict.keys())
            qmarks = ",".join("?" * len(row_dict))
            cur = conn.execute(f"INSERT OR IGNORE INTO households ({c_names}) VALUES ({qmarks})", list(row_dict.values()))
            new_hid = cur.lastrowid
            if not new_hid:
                existing_hh = conn.execute(
                    "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
                    (new_session_id, row_dict.get("household_key"))
                ).fetchone()
                if existing_hh:
                    new_hid = existing_hh["id"]
            if orig_hid is not None and new_hid:
                try:
                    household_id_map[int(orig_hid)] = int(new_hid)
                except (TypeError, ValueError):
                    pass
            sname = str(row_dict.get("surname") or "").strip().lower()
            if sname and new_hid:
                household_surname_map[sname] = int(new_hid)

        # 2. Restore contacts next to build contact_id_map cleanly
        contact_rows = child_data.get("contacts", [])
        c_valid = _valid_cols("contacts")
        for r in contact_rows:
            orig_cid = r.get("_orig_contact_id")
            row_dict = {k: v for k, v in dict(r).items() if not str(k).startswith("_orig_")}
            row_dict["session_id"] = new_session_id
            row_dict["character_id"] = char_id
            old_hid = row_dict.get("household_id")
            if old_hid is not None:
                mapped_hid = None
                try:
                    mapped_hid = household_id_map.get(int(old_hid))
                except (TypeError, ValueError):
                    mapped_hid = None
                if mapped_hid is None:
                    import namegen
                    c_name = str(row_dict.get("name") or "").strip()
                    _, ex_last = namegen.extract_first_and_last_name(c_name)
                    c_last = namegen.normalize_base_surname(ex_last).lower() if ex_last else (c_name.split()[-1].lower() if c_name else "")
                    mapped_hid = household_surname_map.get(c_last) or (household_surname_map.get(ex_last.lower()) if ex_last else None)
                row_dict["household_id"] = mapped_hid
            # Also update embedded household_id inside relations_json if present
            if row_dict.get("household_id") and row_dict.get("relations_json"):
                try:
                    rel_obj = json.loads(row_dict["relations_json"]) if isinstance(row_dict["relations_json"], str) else dict(row_dict["relations_json"])
                    if isinstance(rel_obj, dict):
                        rel_obj["household_id"] = row_dict["household_id"]
                        row_dict["relations_json"] = json.dumps(rel_obj)
                except Exception:
                    pass
            row_dict.setdefault("household_role", "child")
            row_dict = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row_dict.items() if k in c_valid and k != "id"}
            c_names = ",".join(row_dict.keys())
            qmarks = ",".join("?" * len(row_dict))
            cur = conn.execute(f"INSERT OR IGNORE INTO contacts ({c_names}) VALUES ({qmarks})", list(row_dict.values()))
            new_cid = cur.lastrowid
            if not new_cid:
                ex_c = conn.execute(
                    "SELECT id FROM contacts WHERE session_id = ? AND character_id = ? AND npc_id = ?",
                    (new_session_id, char_id, row_dict.get("npc_id")),
                ).fetchone()
                if ex_c:
                    new_cid = ex_c["id"]
            if orig_cid is not None and new_cid:
                try:
                    contact_id_map[int(orig_cid)] = int(new_cid)
                except (TypeError, ValueError):
                    pass

        # 3. Restore remaining child tables with remapped session_id and anchored keys
        for tbl, rows in child_data.items():
            if tbl in ("households", "contacts", "phone_appointments"):
                continue
            t_valid = _valid_cols(tbl)
            if not t_valid:
                continue
            for r in rows:
                orig_cm_id = r.get("_orig_commitment_id") if tbl == "commitments_ledger" else None
                orig_cl_id = r.get("_orig_clue_id") if tbl == "session_clues" else None
                row_dict = {k: v for k, v in dict(r).items() if not str(k).startswith("_orig_")}
                row_dict["session_id"] = new_session_id
                if tbl == "commitments_ledger":
                    ck = row_dict.get("commitment_key", "")
                    if old_session_id and ck:
                        row_dict["commitment_key"] = _rewrite_session_key_id(ck, old_session_id, new_session_id)
                elif tbl == "world_events":
                    ek = row_dict.get("event_key", "")
                    if old_session_id and ek:
                        row_dict["event_key"] = _rewrite_session_key_id(ek, old_session_id, new_session_id)
                    esc_k = row_dict.get("escalation_event_key", "")
                    if old_session_id and esc_k:
                        row_dict["escalation_event_key"] = _rewrite_session_key_id(esc_k, old_session_id, new_session_id)
                    old_imp = row_dict.get("implicated_contact_id")
                    if old_imp is not None:
                        try:
                            row_dict["implicated_contact_id"] = contact_id_map.get(int(old_imp), old_imp)
                        except (TypeError, ValueError):
                            pass
                row_dict = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row_dict.items() if k in t_valid and k != "id"}
                if not row_dict:
                    continue
                c_names = ",".join(row_dict.keys())
                qmarks = ",".join("?" * len(row_dict))
                cur = conn.execute(f"INSERT OR IGNORE INTO {tbl} ({c_names}) VALUES ({qmarks})", list(row_dict.values()))
                if tbl == "commitments_ledger" and orig_cm_id is not None and cur.lastrowid:
                    try:
                        commitment_id_map[int(orig_cm_id)] = int(cur.lastrowid)
                    except (TypeError, ValueError):
                        pass
                elif tbl == "session_clues" and orig_cl_id is not None and cur.lastrowid:
                    try:
                        clue_id_map[int(orig_cl_id)] = int(cur.lastrowid)
                    except (TypeError, ValueError):
                        pass

        # Rebuild 3-column multilingual FTS5 index for restored session_digests
        from .memory import rebuild_session_digests_fts
        rebuild_session_digests_fts(conn, new_session_id)

        # Remap deduction_parents_json inside session_clues if present (D2)
        if clue_id_map:
            cl_rows = conn.execute("SELECT id, deduction_parents_json FROM session_clues WHERE session_id = ?", (new_session_id,)).fetchall()
            for cl_r in cl_rows:
                try:
                    raw_parents = json.loads(cl_r["deduction_parents_json"] or "[]")
                    if isinstance(raw_parents, list) and raw_parents:
                        remapped_parents = [clue_id_map.get(int(pid), pid) for pid in raw_parents if pid is not None]
                        conn.execute(
                            "UPDATE session_clues SET deduction_parents_json = ? WHERE id = ?",
                            (json.dumps(remapped_parents), cl_r["id"]),
                        )
                except Exception:
                    pass

        # Remap conflicting_ids inside commitments_ledger metadata_json if present
        if commitment_id_map:
            cm_rows = conn.execute("SELECT id, metadata_json FROM commitments_ledger WHERE session_id = ?", (new_session_id,)).fetchall()
            for cm_r in cm_rows:
                try:
                    cm_meta = json.loads(cm_r["metadata_json"] or "{}")
                    if isinstance(cm_meta, dict) and isinstance(cm_meta.get("conflicting_ids"), list):
                        cm_meta["conflicting_ids"] = [commitment_id_map.get(int(cid), cid) for cid in cm_meta["conflicting_ids"] if cid is not None]
                        conn.execute("UPDATE commitments_ledger SET metadata_json = ? WHERE id = ?", (json.dumps(cm_meta), cm_r["id"]))
                except Exception:
                    pass

        # Remap contact_id, clue_id, and embedded session keys inside campaign_spines & quest_dossiers
        _CONTACT_ID_FIELDS = (
            "contact_id",
            "implicated_contact_id",
            "npc_contact_id",
            "informant_id",
            "client_id",
            "target_id",
            "accomplice_id",
        )

        def _remap_nested_contact_ids(obj):
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if k in _CONTACT_ID_FIELDS and v is not None:
                        try:
                            out[k] = contact_id_map.get(int(v), v)
                        except (TypeError, ValueError):
                            out[k] = v
                    else:
                        out[k] = _remap_nested_contact_ids(v)
                return out
            if isinstance(obj, list):
                return [_remap_nested_contact_ids(x) for x in obj]
            return obj

        def _remap_nested_session_keys(obj):
            if not old_session_id or not obj:
                return obj
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if k in ("key", "lieutenant_key", "nemesis_id") and isinstance(v, str):
                        out[k] = _rewrite_session_key_id(v, old_session_id, new_session_id)
                    else:
                        out[k] = _remap_nested_session_keys(v)
                return out
            if isinstance(obj, list):
                return [_remap_nested_session_keys(x) for x in obj]
            return obj

        def _remap_nested_clue_ids(obj):
            if not clue_id_map or not obj:
                return obj
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if k == "clue_id" and v is not None:
                        try:
                            out[k] = clue_id_map.get(int(v), v)
                        except (TypeError, ValueError):
                            out[k] = v
                    elif k == "paired_with":
                        if isinstance(v, int):
                            out[k] = clue_id_map.get(v, v)
                        elif isinstance(v, str) and v.strip().isdigit():
                            out[k] = str(clue_id_map.get(int(v.strip()), int(v.strip())))
                        elif isinstance(v, list):
                            out[k] = [
                                clue_id_map.get(p, p)
                                if isinstance(p, int)
                                else str(clue_id_map.get(int(p.strip()), int(p.strip())))
                                if isinstance(p, str) and p.strip().isdigit()
                                else p
                                for p in v
                            ]
                        else:
                            out[k] = v
                    else:
                        out[k] = _remap_nested_clue_ids(v)
                return out
            if isinstance(obj, list):
                return [_remap_nested_clue_ids(x) for x in obj]
            return obj

        sp_rows = conn.execute(
            "SELECT id, lieutenants_roster_json, nemeses_json, state_events_json FROM campaign_spines WHERE session_id = ?",
            (new_session_id,),
        ).fetchall()
        for sp_r in sp_rows:
            try:
                lts = json.loads(sp_r["lieutenants_roster_json"] or "[]")
                nems = json.loads(sp_r["nemeses_json"] or "[]")
                sp_events = json.loads(sp_r["state_events_json"] or "[]")
                if isinstance(lts, list):
                    lts = _remap_nested_session_keys(_remap_nested_contact_ids(lts))
                if isinstance(nems, list):
                    nems = _remap_nested_session_keys(_remap_nested_contact_ids(nems))
                if isinstance(sp_events, list):
                    sp_events = _remap_nested_session_keys(_remap_nested_contact_ids(sp_events))
                conn.execute(
                    "UPDATE campaign_spines SET lieutenants_roster_json = ?, nemeses_json = ?, state_events_json = ? WHERE id = ?",
                    (json.dumps(lts), json.dumps(nems), json.dumps(sp_events), sp_r["id"]),
                )
            except Exception:
                pass

        qd_rows = conn.execute(
            """SELECT id, cast_bindings_json, clue_graph_json, leads_graph_json,
                      twist_spec_json, climax_spec_json, state_events_json
               FROM quest_dossiers WHERE session_id = ?""",
            (new_session_id,),
        ).fetchall()
        for qd_r in qd_rows:
            try:
                cast_b = _remap_nested_contact_ids(json.loads(qd_r["cast_bindings_json"] or "{}"))
                clue_g = _remap_nested_clue_ids(json.loads(qd_r["clue_graph_json"] or "[]"))
                leads_g = _remap_nested_clue_ids(_remap_nested_contact_ids(json.loads(qd_r["leads_graph_json"] or "[]")))
                twist_s = _remap_nested_contact_ids(json.loads(qd_r["twist_spec_json"] or "{}"))
                climax_s = _remap_nested_contact_ids(json.loads(qd_r["climax_spec_json"] or "{}"))
                qd_events = json.loads(qd_r["state_events_json"] or "[]")
                if isinstance(qd_events, list):
                    qd_events = _remap_nested_session_keys(_remap_nested_clue_ids(_remap_nested_contact_ids(qd_events)))
                conn.execute(
                    """UPDATE quest_dossiers
                       SET cast_bindings_json = ?, clue_graph_json = ?, leads_graph_json = ?,
                           twist_spec_json = ?, climax_spec_json = ?, state_events_json = ?
                       WHERE id = ?""",
                    (
                        json.dumps(cast_b),
                        json.dumps(clue_g),
                        json.dumps(leads_g),
                        json.dumps(twist_s),
                        json.dumps(climax_s),
                        json.dumps(qd_events),
                        qd_r["id"],
                    ),
                )
            except Exception:
                pass

        # Re-materialize contacts.relations_json from cloned households + social_ties
        try:
            import mechanics.social.relationship_graph as rg
            import mechanics.social.genealogy as gen
            scen_key = str(sess_dict.get("scenario") or "fantasy")
            cloned_contacts = conn.execute("SELECT * FROM contacts WHERE session_id = ?", (new_session_id,)).fetchall()
            for cr in cloned_contacts:
                cd_item = dict(cr)
                try:
                    cd_item["basic_info"] = json.loads(cd_item.get("basic_info_json") or "{}")
                except Exception:
                    cd_item["basic_info"] = {}
                try:
                    cd_item["appearance"] = json.loads(cd_item.get("appearance_json") or "{}")
                except Exception:
                    cd_item["appearance"] = {}
                try:
                    cd_item["relations"] = json.loads(cd_item.get("relations_json") or "{}")
                except Exception:
                    cd_item["relations"] = {}
                mat_rel = rg.materialize_relations(new_session_id, cd_item, conn=conn)
                if cd_item.get("household_id"):
                    hh_obj = db.get_household_by_id(cd_item["household_id"])
                    if hh_obj:
                        hh_hydrated = gen._hydrate_household_entity(hh_obj, cd_item, scen_key)
                        mat_rel["family"] = gen.build_family_tree_for_member(
                            hh_hydrated,
                            cd_item.get("name", ""),
                            scenario=scen_key,
                            member_role=cd_item.get("household_role") or "child",
                        )
                        mat_rel["household_id"] = cd_item["household_id"]
                        if hh_hydrated.get("residence_location"):
                            mat_rel["residence_location"] = hh_hydrated["residence_location"]
                conn.execute(
                    "UPDATE contacts SET relations_json = ? WHERE id = ?",
                    (json.dumps(mat_rel), cd_item["id"]),
                )
        except Exception:
            pass

        # Restore character inventory (including session-scoped quest items where character_id IS NULL)
        inv_valid = _valid_cols("inventory")
        conn.execute(
            "DELETE FROM inventory WHERE character_id = ? OR (character_id IS NULL AND user_id = ?)",
            (char_id, user_id),
        )
        for item in saved_inv:
            item_dict = dict(item)
            item_dict["character_id"] = char_id
            item_dict["user_id"] = user_id
            item_dict = {
                k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                for k, v in item_dict.items()
                if k in inv_valid and k != "id"
            }
            if not item_dict:
                continue
            c_names = ",".join(item_dict.keys())
            qmarks = ",".join("?" * len(item_dict))
            conn.execute(f"INSERT INTO inventory ({c_names}) VALUES ({qmarks})", list(item_dict.values()))

        # Restore character vitals, 3-axis resonance, spell progress, and link active_session_id
        raw_status = char_state.get("status_effects", "[]")
        status_effects_val = json.dumps(raw_status) if isinstance(raw_status, (list, dict)) else str(raw_status or "[]")
        restored_attr = char_state.get("attribute")
        restored_arch = char_state.get("combat_archetype")
        restored_med = char_state.get("ability_medium")
        raw_prog = char_state["skill_progress"] if "skill_progress" in char_state else char.get("skill_progress", "{}")
        prog_val = json.dumps(raw_prog) if isinstance(raw_prog, (list, dict)) else str(raw_prog or "{}")
        raw_spells = char_state["learned_spells"] if "learned_spells" in char_state else char.get("learned_spells", "[]")
        spells_val = json.dumps(raw_spells) if isinstance(raw_spells, (list, dict)) else str(raw_spells or "[]")
        conn.execute(
            """UPDATE characters
               SET hp = ?, mp = ?, gold = ?, status_effects = ?, days_adventured = ?,
                   attribute = ?, combat_archetype = ?, ability_medium = ?,
                   skill_progress = ?, learned_spells = ?, active_session_id = ?,
                   joined_faction_id = ?, faction_rank = ?, faction_title = ?
               WHERE id = ?""",
            (
                char_state.get("hp", char["max_hp"]),
                char_state.get("mp", char["max_mp"]),
                char_state.get("gold", char["gold"]),
                status_effects_val,
                char_state.get("days_adventured", 1),
                restored_attr,
                restored_arch,
                restored_med,
                prog_val,
                spells_val,
                new_session_id,
                char_state.get("joined_faction_id", ""),
                char_state.get("faction_rank", 0),
                char_state.get("faction_title", ""),
                char_id,
            )
        )

    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(sess_data.get("scenario", "")):
            from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells
            sync_equipped_anomalous_spells(user_id)
    except Exception:
        pass

    return db.get_session(new_session_id)

def list_adventure_saves(user_id: int) -> list[dict]:
    """Returns metadata for all save slots owned by the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, character_id, slot_name, scenario, scene_title,
                      narrative_snippet, current_location, saved_at
               FROM adventure_saves
               WHERE character_id = ?
               ORDER BY saved_at DESC""",
            (char["id"],)
        ).fetchall()
        return [dict(r) for r in rows]

def get_adventure_save_metadata(user_id: int, slot_name: str) -> dict | None:
    """Returns metadata for a specific save slot owned by the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, user_id, character_id, slot_name, scenario, scene_title,
                      narrative_snippet, current_location, saved_at
               FROM adventure_saves
               WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)""",
            (char["id"], (slot_name or "").strip())
        ).fetchone()
        return dict(row) if row else None

def delete_adventure_save(user_id: int, slot_name: str) -> bool:
    """Permanently deletes a save slot for the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return False
    with get_conn() as conn:
        res = conn.execute(
            "DELETE FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char["id"], (slot_name or "").strip())
        )
        return res.rowcount > 0

