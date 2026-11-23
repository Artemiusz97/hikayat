from __future__ import annotations

import json
import re
import sqlite3
import time

def _migrate_narrative_pacing_values_v58(conn: sqlite3.Connection) -> None:
    """Safely backfills narrative_pacing='concise' from legacy verbosity values when both columns exist."""
    for tbl in ("user_settings", "sessions"):
        cols = {
            (r["name"] if isinstance(r, sqlite3.Row) else r[1])
            for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()
        }
        if "verbosity" in cols and "narrative_pacing" in cols:
            conn.execute(
                f"UPDATE {tbl} SET narrative_pacing = 'concise', verbosity = 'normal' "
                "WHERE LOWER(COALESCE(verbosity, '')) IN ('concise', 'direct')"
            )

def _ensure_living_world_indexes_v55(conn: sqlite3.Connection) -> None:
    """Ensures Migration 55 covering indexes exist whenever target tables are present."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='social_ties' LIMIT 1").fetchone():
        conn.execute("CREATE INDEX IF NOT EXISTS idx_social_ties_sess_status ON social_ties(session_id, status)")
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_roster' LIMIT 1").fetchone():
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_world_roster_sess_nodes "
            "ON world_roster(session_id, staff_status, home_node_id, workplace_node_id, hangout_node_id)"
        )

def _migrate_zone_split_and_hidden_villages_v49(conn: sqlite3.Connection) -> int:
    """Idempotently splits `zone_eastern_sanctuary` from `zone_woods_reserve` and seeds hidden folklore villages on existing saves."""
    from mechanics.world.locations.folklore_veil import backfill_zone_split_and_hidden_villages_v49
    return backfill_zone_split_and_hidden_villages_v49(conn)

def _migrate_anomalous_locations_integrity_v57(conn: sqlite3.Connection) -> int:
    """Idempotently repairs misparented nodes, edges, renamed rooms, and access drift."""
    from mechanics.world.anomalous_sites.lifecycle import backfill_anomalous_locations_integrity_v57
    return backfill_anomalous_locations_integrity_v57(conn)

def _migrate_outlaw_factions_v60(conn: sqlite3.Connection) -> int:
    """Idempotently backfills 10-wing Occult Cult & Clandestine Syndicate HQs and starter safehouses."""
    from mechanics.world.anomalous_sites.lifecycle import backfill_outlaw_faction_hqs_and_residences_v60
    return backfill_outlaw_faction_hqs_and_residences_v60(conn)

def _migrate_dynamic_social_overhaul_v50(conn: sqlite3.Connection) -> int:
    """Idempotently backfills contact_dossier_discoveries for kin, companions, romantic partners, and pre-v50 saves."""
    from ..social_pacing import backfill_exempt_and_legacy_contact_discoveries
    return backfill_exempt_and_legacy_contact_discoveries(conn, is_legacy_migration=True)

def _migrate_main_quest_bounty_overhaul_v51(conn: sqlite3.Connection) -> int:
    """Ensures v51 campaign_spines columns exist and strips legacy Story Quest deadlines while leaving mid-chapter quests intact."""
    cols = {
        (r["name"] if isinstance(r, sqlite3.Row) else r[1])
        for r in conn.execute("PRAGMA table_info(campaign_spines)").fetchall()
    }
    added = 0
    for col_name in ("hidden_bible_json", "ending_axes_json", "chronicle_tapestry_json"):
        if col_name not in cols:
            conn.execute(f"ALTER TABLE campaign_spines ADD COLUMN {col_name} TEXT NOT NULL DEFAULT '{{}}'")
            added += 1
    conn.execute(
        """UPDATE quests
           SET deadline_day = NULL, deadline_minute = NULL
           WHERE (is_story_quest = 1 OR LOWER(quest_type) IN ('story quest', 'main quest') OR quest_id LIKE 'SQ-%')
             AND (deadline_day IS NOT NULL OR deadline_minute IS NOT NULL)"""
    )
    conn.execute(
        """UPDATE quests
           SET is_story_quest = 1
           WHERE (is_story_quest = 0 OR is_story_quest IS NULL)
             AND (LOWER(quest_type) IN ('story quest', 'main quest') OR quest_id LIKE 'SQ-%')"""
    )
    return added

def _migrate_combat_evolution_v53(conn: sqlite3.Connection) -> int:
    """Idempotently normalizes status effects across characters, sessions, contacts,
    and adventure saves to StatusEffectInstance schemas, and ensures combat threat
    and telegraph columns are initialized."""
    from mechanics.combat.status_effects import normalize_status_effect

    count = 0

    # 1. Characters: normalize status_effects JSON
    try:
        char_rows = conn.execute("SELECT id, status_effects FROM characters").fetchall()
        for r in char_rows:
            cid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
            raw_eff = r["status_effects"] if isinstance(r, sqlite3.Row) else r[1]
            if not raw_eff:
                continue
            try:
                parsed = json.loads(raw_eff) if isinstance(raw_eff, str) else raw_eff
                if isinstance(parsed, list) and any(isinstance(x, str) for x in parsed):
                    norm = [normalize_status_effect(x) for x in parsed]
                    conn.execute("UPDATE characters SET status_effects = ? WHERE id = ?", (json.dumps(norm), cid))
                    count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[migration 53] Warning normalizing characters: {e}")

    # 2. Sessions: normalize enemies and companions
    try:
        sess_rows = conn.execute(
            "SELECT id, nearby_enemies_json, party_npcs_json, temporary_companions_json FROM sessions"
        ).fetchall()
        for r in sess_rows:
            sid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
            enemies_raw = r["nearby_enemies_json"] if isinstance(r, sqlite3.Row) else r[1]
            party_raw = r["party_npcs_json"] if isinstance(r, sqlite3.Row) else r[2]
            temp_raw = r["temporary_companions_json"] if isinstance(r, sqlite3.Row) else r[3]

            updated_fields = {}
            for col_name, raw_val in [
                ("nearby_enemies_json", enemies_raw),
                ("party_npcs_json", party_raw),
                ("temporary_companions_json", temp_raw),
            ]:
                if not raw_val:
                    continue
                try:
                    entities = json.loads(raw_val) if isinstance(raw_val, str) else raw_val
                    if isinstance(entities, list):
                        changed = False
                        for entity in entities:
                            if isinstance(entity, dict) and "status_effects" in entity:
                                cur = entity["status_effects"]
                                if isinstance(cur, list) and any(isinstance(x, str) for x in cur):
                                    entity["status_effects"] = [normalize_status_effect(x) for x in cur]
                                    changed = True
                        if changed:
                            updated_fields[col_name] = json.dumps(entities)
                except Exception:
                    pass

            if updated_fields:
                sets = ", ".join(f"{k} = ?" for k in updated_fields.keys())
                conn.execute(f"UPDATE sessions SET {sets} WHERE id = ?", (*updated_fields.values(), sid))
                count += 1
    except Exception as e:
        print(f"[migration 53] Warning normalizing sessions: {e}")

    # 3. Contacts: normalize basic_info_json['status_effects']
    try:
        contact_rows = conn.execute("SELECT id, basic_info_json FROM contacts").fetchall()
        for r in contact_rows:
            cid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
            raw_b = r["basic_info_json"] if isinstance(r, sqlite3.Row) else r[1]
            if not raw_b:
                continue
            try:
                b_info = json.loads(raw_b) if isinstance(raw_b, str) else raw_b
                if isinstance(b_info, dict) and "status_effects" in b_info:
                    effs = b_info["status_effects"]
                    if isinstance(effs, list) and any(isinstance(x, str) for x in effs):
                        b_info["status_effects"] = [normalize_status_effect(x) for x in effs]
                        conn.execute("UPDATE contacts SET basic_info_json = ? WHERE id = ?", (json.dumps(b_info), cid))
                        count += 1
            except Exception:
                pass
    except Exception as e:
        print(f"[migration 53] Warning normalizing contacts: {e}")

    # 4. Adventure saves: normalize snapshot_data JSON
    try:
        has_saves = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='adventure_saves'").fetchone()
        if has_saves:
            save_rows = conn.execute("SELECT id, snapshot_data FROM adventure_saves").fetchall()
            for r in save_rows:
                sv_id = r["id"] if isinstance(r, sqlite3.Row) else r[0]
                snap_str = r["snapshot_data"] if isinstance(r, sqlite3.Row) else r[1]
                if not snap_str:
                    continue
                try:
                    snap = json.loads(snap_str) if isinstance(snap_str, str) else snap_str
                    if isinstance(snap, dict):
                        changed = False
                        # Normalize characters in snapshot (supports list under "characters",
                        # keyed dict {uid: char_dict}, or flat character dict under "character_state")
                        char_containers = []
                        if isinstance(snap.get("characters"), list):
                            char_containers.extend(snap["characters"])
                        cs_val = snap.get("character_state")
                        if isinstance(cs_val, dict):
                            if "status_effects" in cs_val:
                                char_containers.append(cs_val)
                            else:
                                char_containers.extend(
                                    v for v in cs_val.values() if isinstance(v, dict)
                                )
                        for ch in char_containers:
                            if isinstance(ch, dict) and "status_effects" in ch:
                                raw_cur = ch["status_effects"]
                                if isinstance(raw_cur, str):
                                    if raw_cur.strip():
                                        try:
                                            parsed_cur = json.loads(raw_cur)
                                        except Exception:
                                            parsed_cur = None
                                        if isinstance(parsed_cur, list) and any(isinstance(x, str) for x in parsed_cur):
                                            ch["status_effects"] = json.dumps(
                                                [normalize_status_effect(x) for x in parsed_cur]
                                            )
                                            changed = True
                                elif isinstance(raw_cur, list) and any(isinstance(x, str) for x in raw_cur):
                                    ch["status_effects"] = [normalize_status_effect(x) for x in raw_cur]
                                    changed = True
                        # Normalize session in snapshot
                        sess = snap.get("session")
                        if isinstance(sess, dict):
                            if "combat_threat_ledger_json" not in sess:
                                sess["combat_threat_ledger_json"] = "{}"
                                changed = True
                            if "combat_boss_telegraph_json" not in sess:
                                sess["combat_boss_telegraph_json"] = "{}"
                                changed = True
                            for k in ("nearby_enemies_json", "party_npcs_json", "temporary_companions_json"):
                                if k in sess:
                                    raw_ent = sess[k]
                                    if isinstance(raw_ent, str):
                                        if not raw_ent.strip():
                                            continue
                                        try:
                                            ents = json.loads(raw_ent)
                                        except Exception:
                                            continue
                                    else:
                                        ents = raw_ent
                                    if isinstance(ents, list):
                                        sub_changed = False
                                        for ent in ents:
                                            if isinstance(ent, dict) and "status_effects" in ent:
                                                cur = ent["status_effects"]
                                                if isinstance(cur, list) and any(isinstance(x, str) for x in cur):
                                                    ent["status_effects"] = [normalize_status_effect(x) for x in cur]
                                                    sub_changed = True
                                        if sub_changed:
                                            sess[k] = json.dumps(ents)
                                            changed = True
                        # Normalize child_tables.contacts[*].basic_info_json['status_effects']
                        child_tbls = snap.get("child_tables")
                        if isinstance(child_tbls, dict):
                            saved_contacts = child_tbls.get("contacts")
                            if isinstance(saved_contacts, list):
                                for ct in saved_contacts:
                                    if not isinstance(ct, dict):
                                        continue
                                    raw_cb = ct.get("basic_info_json")
                                    if isinstance(raw_cb, str):
                                        if not raw_cb.strip():
                                            continue
                                        try:
                                            cb_info = json.loads(raw_cb)
                                        except Exception:
                                            continue
                                        if isinstance(cb_info, dict) and "status_effects" in cb_info:
                                            ceffs = cb_info["status_effects"]
                                            if isinstance(ceffs, list) and any(isinstance(x, str) for x in ceffs):
                                                cb_info["status_effects"] = [normalize_status_effect(x) for x in ceffs]
                                                ct["basic_info_json"] = json.dumps(cb_info)
                                                changed = True
                                    elif isinstance(raw_cb, dict) and "status_effects" in raw_cb:
                                        ceffs = raw_cb["status_effects"]
                                        if isinstance(ceffs, list) and any(isinstance(x, str) for x in ceffs):
                                            raw_cb["status_effects"] = [normalize_status_effect(x) for x in ceffs]
                                            changed = True
                        if changed:
                            conn.execute("UPDATE adventure_saves SET snapshot_data = ? WHERE id = ?", (json.dumps(snap), sv_id))
                            count += 1
                except Exception:
                    pass
    except Exception as e:
        print(f"[migration 53] Warning normalizing adventure_saves: {e}")

    return count

def _backfill_session_anomaly_records_v45(conn: sqlite3.Connection) -> None:
    """Idempotently backfills `session_anomaly_records` from legacy `sessions.extra_json` and `quests.anomaly_blueprint_json` from `quest_notes`."""
    from ..dossiers import SESSION_ANOMALY_KEY_TO_RECORD_TYPE, sync_session_anomaly_records_from_extra

    now = time.time()
    s_rows = conn.execute("SELECT id, extra_json FROM sessions WHERE extra_json IS NOT NULL AND extra_json != ''").fetchall()
    for r in s_rows:
        sid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
        raw_extra = (r["extra_json"] if isinstance(r, sqlite3.Row) else r[1]) or "{}"
        try:
            extra = json.loads(raw_extra) if isinstance(raw_extra, str) else dict(raw_extra or {})
        except Exception:
            continue
        if not isinstance(extra, dict):
            continue
        anom_patch = {k: extra[k] for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE if k in extra}
        if anom_patch:
            sync_session_anomaly_records_from_extra(sid, anom_patch, conn=conn)
            for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE:
                extra.pop(k, None)
            conn.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(extra, default=str), now, sid),
            )

    try:
        from mechanics.world.anomaly_engine import parse_blueprint_from_notes
    except Exception:
        parse_blueprint_from_notes = None

    if parse_blueprint_from_notes is not None:
        q_rows = conn.execute(
            """SELECT id, quest_notes, anomaly_blueprint_json
               FROM quests
               WHERE quest_notes LIKE '%anomaly_bp:%' OR quest_notes LIKE '%anomaly_blueprint:%'"""
        ).fetchall()
        for qr in q_rows:
            qid_pk = qr["id"] if isinstance(qr, sqlite3.Row) else qr[0]
            q_notes = (qr["quest_notes"] if isinstance(qr, sqlite3.Row) else qr[1]) or ""
            existing_bp_json = (qr["anomaly_blueprint_json"] if isinstance(qr, sqlite3.Row) else qr[2]) or ""
            if existing_bp_json.strip() not in ("", "{}"):
                continue
            bp = parse_blueprint_from_notes(q_notes)
            if isinstance(bp, dict) and bp:
                conn.execute(
                    "UPDATE quests SET anomaly_blueprint_json = ? WHERE id = ?",
                    (json.dumps(bp, separators=(",", ":"), ensure_ascii=True), qid_pk),
                )

def _backfill_campaign_spines_from_legacy_sessions(conn: sqlite3.Connection) -> None:
    """Seeds campaign_spines rows from legacy sessions.extra_json['world_ending_anomaly'] while preserving dossier_stage='legacy' on existing quests."""
    now = time.time()
    rows = conn.execute("SELECT id, scenario, extra_json FROM sessions").fetchall()
    for r in rows:
        sid = r["id"] if isinstance(r, sqlite3.Row) else r[0]
        scenario = (r["scenario"] if isinstance(r, sqlite3.Row) else r[1]) or "fantasy"
        raw_extra = (r["extra_json"] if isinstance(r, sqlite3.Row) else r[2]) or "{}"
        try:
            extra = json.loads(raw_extra) if isinstance(raw_extra, str) else dict(raw_extra or {})
        except Exception:
            extra = {}
        anomaly = extra.get("world_ending_anomaly") or extra.get("campaign_spine")
        if not isinstance(anomaly, dict) or not anomaly:
            continue
        mastermind = {
            "name": anomaly.get("entity_name") or anomaly.get("mastermind_name") or anomaly.get("title") or "Hidden Architect",
            "archetype": anomaly.get("archetype") or "calamity",
            "goal": anomaly.get("catastrophe_summary") or anomaly.get("goal") or "",
            "legacy_source": True,
        }
        chapters = anomaly.get("chapters") if isinstance(anomaly.get("chapters"), dict) else {}
        conn.execute(
            """INSERT OR IGNORE INTO campaign_spines (
                session_id, scenario, mastermind_profile_json, lieutenants_roster_json,
                chapters_blueprint_json, nemeses_json, climax_status, epilogue_status,
                state_events_json, created_at, updated_at
            ) VALUES (?, ?, ?, '[]', ?, '[]', 'pending', 'pending', '[]', ?, ?)""",
            (int(sid), str(scenario), json.dumps(mastermind), json.dumps(chapters), now, now),
        )

def _strip_legacy_session_fk_constraints(conn: sqlite3.Connection) -> None:
    """Removes legacy FOREIGN KEY(session_id) REFERENCES sessions(id) from normalized child tables
    so synthetic session_ids in unit tests and simulations match all other SESSION_CHILD_TABLES."""
    from .connection import is_in_uow

    if is_in_uow():
        raise RuntimeError(
            "Cannot run _strip_legacy_session_fk_constraints inside an active UnitOfWork or ReadUnitOfWork."
        )
    target_ddls = {
        "households": (
            """CREATE TABLE households__new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                household_key       TEXT NOT NULL,
                surname             TEXT NOT NULL,
                father_json         TEXT NOT NULL DEFAULT '{}',
                mother_json         TEXT NOT NULL DEFAULT '{}',
                narrative_siblings_json TEXT NOT NULL DEFAULT '[]',
                residence_location  TEXT DEFAULT '',
                created_at          REAL,
                updated_at          REAL,
                UNIQUE(session_id, household_key)
            )""",
            ["CREATE INDEX IF NOT EXISTS idx_households_session_surname ON households(session_id, surname)"],
        ),
        "intimate_events": (
            """CREATE TABLE intimate_events__new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                character_id        TEXT NOT NULL,
                partner_id          TEXT,
                partner_name        TEXT NOT NULL,
                partner_role        TEXT,
                turn_number         INTEGER DEFAULT 0,
                event_origin        TEXT DEFAULT 'past_history',
                act_type            TEXT NOT NULL,
                direction           TEXT NOT NULL,
                is_physical         BOOLEAN DEFAULT 1,
                count               INTEGER DEFAULT 1,
                climax_count        INTEGER DEFAULT 0,
                is_secret_affair    BOOLEAN DEFAULT 0,
                narrative_summary   TEXT,
                created_at          REAL
            )""",
            [
                "CREATE INDEX IF NOT EXISTS idx_intimate_events_char ON intimate_events(session_id, character_id, is_physical)",
                "CREATE INDEX IF NOT EXISTS idx_intimate_events_session_turn ON intimate_events(session_id, turn_number)",
            ],
        ),
        "commitments_ledger": (
            """CREATE TABLE commitments_ledger__new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                commitment_key      TEXT NOT NULL DEFAULT '',
                commitment_type     TEXT NOT NULL,
                source_entity       TEXT NOT NULL,
                target_entity       TEXT NOT NULL,
                participants_json   TEXT NOT NULL DEFAULT '[]',
                target_location     TEXT DEFAULT '',
                target_node_id      TEXT DEFAULT '',
                scheduled_day       INTEGER DEFAULT 1,
                end_day             INTEGER DEFAULT NULL,
                start_minute        INTEGER DEFAULT 0,
                end_minute          INTEGER DEFAULT 1439,
                deadline_turn       INTEGER DEFAULT NULL,
                status              TEXT DEFAULT 'active',
                origin              TEXT DEFAULT 'in_person',
                is_confidential     INTEGER DEFAULT 0,
                title               TEXT DEFAULT '',
                description         TEXT NOT NULL,
                metadata_json       TEXT DEFAULT '{}',
                turn_created        INTEGER NOT NULL DEFAULT 0,
                created_at          REAL DEFAULT 0,
                updated_at          REAL NOT NULL DEFAULT 0
            )""",
            [
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_commitments_session_key ON commitments_ledger(session_id, commitment_key) WHERE commitment_key != ''",
                "CREATE INDEX IF NOT EXISTS idx_commitments_session ON commitments_ledger(session_id, status)",
                "CREATE INDEX IF NOT EXISTS idx_commitments_time ON commitments_ledger(session_id, scheduled_day, start_minute, end_minute)",
                "CREATE INDEX IF NOT EXISTS idx_commitments_node ON commitments_ledger(session_id, target_node_id, status)",
            ],
        ),
        "actor_physical_states": (
            """CREATE TABLE actor_physical_states__new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                actor_name          TEXT NOT NULL,
                canonical_key       TEXT NOT NULL,
                actor_type          TEXT DEFAULT 'npc',
                posture             TEXT DEFAULT 'standing',
                posture_qualifier   TEXT DEFAULT '',
                relative_target     TEXT DEFAULT '',
                relative_relation   TEXT DEFAULT '',
                holding             TEXT DEFAULT 'Empty hands',
                stance              TEXT DEFAULT 'Neutral',
                tether_type         TEXT DEFAULT 'none',
                tether_partner      TEXT DEFAULT '',
                composure           TEXT DEFAULT 'composed',
                is_wet              INTEGER DEFAULT 0,
                is_bloodied         INTEGER DEFAULT 0,
                climax_count        INTEGER DEFAULT 0,
                in_refractory       INTEGER DEFAULT 0,
                canonical_outfit_json TEXT DEFAULT '{}',
                active_outfit_preset TEXT DEFAULT '',
                wardrobe_meta_json  TEXT DEFAULT '{}',
                created_at          REAL NOT NULL,
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, canonical_key)
            )""",
            ["CREATE INDEX IF NOT EXISTS idx_actor_phys_lookup ON actor_physical_states(session_id, canonical_key)"],
        ),
        "actor_garments": (
            """CREATE TABLE actor_garments__new (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                actor_key           TEXT NOT NULL,
                slot                TEXT NOT NULL,
                state               TEXT DEFAULT 'worn',
                item_name           TEXT DEFAULT '',
                layer_depth         INTEGER DEFAULT 2,
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, actor_key, slot)
            )""",
            ["CREATE INDEX IF NOT EXISTS idx_actor_garments_actor ON actor_garments(session_id, actor_key)"],
        ),
    }
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('households', 'intimate_events', 'commitments_ledger', 'actor_physical_states', 'actor_garments')"
    ).fetchall()
    to_rebuild = [r["name"] for r in rows if r["sql"] and "references sessions" in r["sql"].lower()]
    if not to_rebuild:
        return
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        for tbl in to_rebuild:
            ddl, idx_sqls = target_ddls[tbl]
            conn.execute(f"DROP TABLE IF EXISTS {tbl}__new")
            conn.execute(ddl)
            old_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({tbl})").fetchall()}
            new_cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tbl}__new)").fetchall() if r[1] in old_cols]
            col_list = ", ".join(new_cols)
            conn.execute(f"INSERT INTO {tbl}__new ({col_list}) SELECT {col_list} FROM {tbl}")
            conn.execute(f"DROP TABLE {tbl}")
            conn.execute(f"ALTER TABLE {tbl}__new RENAME TO {tbl}")
            for idx_sql in idx_sqls:
                conn.execute(idx_sql)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")

def _is_legacy_player_key_val(val: str) -> bool:
    v = str(val or "").strip().lower()
    return v in ("player", "you") or v.startswith("player:") or v.startswith("player_")

def _migrate_clean_cutover_v30(conn: sqlite3.Connection) -> None:
    """One-time startup normalization retiring runtime legacy shims and key aliases."""

    # 1. Backfill any remaining phone_appointments into commitments_ledger
    _migrate_phone_appointments_to_commitments(conn)

    # 2. Backfill commitments_ledger.end_day & deduplicate commitment_key before unique index
    conn.execute(
        """UPDATE commitments_ledger
           SET end_day = CASE WHEN end_minute < start_minute THEN scheduled_day + 1 ELSE scheduled_day END
           WHERE end_day IS NULL"""
    )
    conn.execute(
        """DELETE FROM commitments_ledger
           WHERE commitment_key != ''
             AND id NOT IN (
                 SELECT MAX(id) FROM commitments_ledger
                 WHERE commitment_key != ''
                 GROUP BY session_id, commitment_key
             )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_commitments_session_key "
        "ON commitments_ledger(session_id, commitment_key) WHERE commitment_key != ''"
    )

    # 3. Canonicalize player keys in commitments_ledger
    conn.execute(
        "UPDATE commitments_ledger SET source_entity = 'player' "
        "WHERE LOWER(source_entity) IN ('you') OR LOWER(source_entity) LIKE 'player:%' OR LOWER(source_entity) LIKE 'player_%'"
    )
    conn.execute(
        "UPDATE commitments_ledger SET target_entity = 'player' "
        "WHERE LOWER(target_entity) IN ('you') OR LOWER(target_entity) LIKE 'player:%' OR LOWER(target_entity) LIKE 'player_%'"
    )

    # 4. Canonicalize player keys in social_persons (merge player:* / player_* into 'player')
    sp_rows = conn.execute(
        "SELECT id, session_id, person_key, display_name FROM social_persons "
        "WHERE LOWER(person_key) IN ('player', 'you') OR LOWER(person_key) LIKE 'player:%' OR LOWER(person_key) LIKE 'player_%'"
    ).fetchall()
    by_sess: dict[int, list[dict]] = {}
    for r in sp_rows:
        by_sess.setdefault(int(r["session_id"]), []).append(dict(r))
    now = time.time()
    for sid, plist in by_sess.items():
        best_display = "Player"
        for item in plist:
            dn = str(item.get("display_name") or "").strip()
            if dn and not _is_legacy_player_key_val(dn):
                best_display = dn
                break
        if best_display == "Player":
            char_row = conn.execute(
                "SELECT c.name FROM characters c JOIN sessions s ON (s.character_id = c.id OR c.active_session_id = s.id) WHERE s.id = ? LIMIT 1",
                (sid,),
            ).fetchone()
            if char_row and char_row["name"]:
                best_display = str(char_row["name"]).strip()
        conn.execute(
            "DELETE FROM social_persons WHERE session_id = ? AND person_key != 'player' "
            "AND (LOWER(person_key) IN ('you') OR LOWER(person_key) LIKE 'player:%' OR LOWER(person_key) LIKE 'player_%')",
            (sid,),
        )
        conn.execute(
            """INSERT INTO social_persons (session_id, person_key, display_name, origin, created_at, updated_at)
               VALUES (?, 'player', ?, 'player', ?, ?)
               ON CONFLICT(session_id, person_key) DO UPDATE SET display_name = excluded.display_name, updated_at = excluded.updated_at""",
            (sid, best_display, now, now),
        )

    # 5. Canonicalize player keys in social_ties (rewrite & deduplicate active ties)
    tie_rows = conn.execute(
        "SELECT * FROM social_ties "
        "WHERE LOWER(person_a_key) IN ('you') OR LOWER(person_a_key) LIKE 'player:%' OR LOWER(person_a_key) LIKE 'player_%' "
        "   OR LOWER(person_b_key) IN ('you') OR LOWER(person_b_key) LIKE 'player:%' OR LOWER(person_b_key) LIKE 'player_%'"
    ).fetchall()
    for tr in tie_rows:
        td = dict(tr)
        tid = td["id"]
        sid = td["session_id"]
        ak = "player" if _is_legacy_player_key_val(td["person_a_key"]) else td["person_a_key"]
        bk = "player" if _is_legacy_player_key_val(td["person_b_key"]) else td["person_b_key"]
        if ak == bk:
            conn.execute("DELETE FROM social_ties WHERE id = ?", (tid,))
            continue
        if not td.get("is_directed") and ak > bk:
            ak, bk = bk, ak
        if td.get("status") == "active":
            dup = conn.execute(
                "SELECT id FROM social_ties WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active' AND id != ?",
                (sid, ak, bk, td["tie_type"], tid),
            ).fetchone()
            if dup:
                conn.execute("DELETE FROM social_ties WHERE id = ?", (tid,))
                continue
        conn.execute(
            "UPDATE social_ties SET person_a_key = ?, person_b_key = ? WHERE id = ?",
            (ak, bk, tid),
        )

    # 6. Canonicalize intimate_events player & numeric contact IDs
    conn.execute(
        "UPDATE intimate_events SET partner_id = 'player' "
        "WHERE partner_id IN ('0', 'you') OR LOWER(partner_id) LIKE 'player:%' OR LOWER(partner_id) LIKE 'player_%'"
    )
    ie_rows = conn.execute("SELECT id, session_id, character_id, partner_id FROM intimate_events").fetchall()
    for ier in ie_rows:
        cid_str = str(ier["character_id"] or "")
        pid_str = str(ier["partner_id"] or "")
        new_cid = cid_str
        new_pid = pid_str
        if cid_str.isdigit():
            crow = conn.execute("SELECT npc_id FROM contacts WHERE session_id = ? AND id = ?", (ier["session_id"], int(cid_str))).fetchone()
            if crow and crow["npc_id"]:
                new_cid = crow["npc_id"]
        if pid_str.isdigit() and pid_str != "0":
            prow = conn.execute("SELECT npc_id FROM contacts WHERE session_id = ? AND id = ?", (ier["session_id"], int(pid_str))).fetchone()
            if prow and prow["npc_id"]:
                new_pid = prow["npc_id"]
        if new_cid != cid_str or new_pid != pid_str:
            conn.execute("UPDATE intimate_events SET character_id = ?, partner_id = ? WHERE id = ?", (new_cid, new_pid, ier["id"]))

    # 7. Populate contacts.household_role accurately using full name matching
    hh_contacts = conn.execute(
        "SELECT c.id, c.name, h.father_json, h.mother_json FROM contacts c JOIN households h ON c.household_id = h.id"
    ).fetchall()
    for hc in hh_contacts:
        cname = re.sub(r"\s*\(née\s+[^)]+\)", "", str(hc["name"] or ""), flags=re.IGNORECASE).strip().lower()
        role_val = "child"
        try:
            f_obj = json.loads(hc["father_json"] or "{}")
            m_obj = json.loads(hc["mother_json"] or "{}")
            fname = re.sub(r"\s*\(née\s+[^)]+\)", "", str(f_obj.get("name") or ""), flags=re.IGNORECASE).strip().lower()
            mname = re.sub(r"\s*\(née\s+[^)]+\)", "", str(m_obj.get("name") or ""), flags=re.IGNORECASE).strip().lower()
            if fname and cname == fname:
                role_val = "father"
            elif mname and cname == mname:
                role_val = "mother"
        except Exception:
            pass
        conn.execute("UPDATE contacts SET household_role = ? WHERE id = ?", (role_val, hc["id"]))

    # 8. Migrate any remaining actor state from sessions.physical_state_json into actor_physical_states/actor_garments
    # and strip legacy "actors" key from sessions.physical_state_json (keeping only room-level scene metadata)
    try:
        import mechanics.social.physical_state as ps
        sess_rows = conn.execute(
            "SELECT id, physical_state_json FROM sessions WHERE physical_state_json IS NOT NULL AND physical_state_json != '' AND physical_state_json != '{}'"
        ).fetchall()
        for sr in sess_rows:
            sid = int(sr["id"])
            try:
                p_data = json.loads(sr["physical_state_json"])
            except Exception:
                continue
            if not isinstance(p_data, dict):
                continue
            if p_data.get("actors"):
                cnt_r = conn.execute("SELECT COUNT(*) FROM actor_physical_states WHERE session_id = ?", (sid,)).fetchone()
                if not cnt_r or cnt_r[0] == 0:
                    ps.sync_state_dict_to_db(sid, p_data, conn=conn)
                scene_meta = {k: v for k, v in p_data.items() if k != "actors"}
                conn.execute(
                    "UPDATE sessions SET physical_state_json = ? WHERE id = ?",
                    (json.dumps(scene_meta), sid),
                )
    except Exception:
        pass

def _migrate_self_heal_main_area_and_roster_drift_v32(conn: sqlite3.Connection) -> None:
    """Self-heals legacy 'Main Area' location strings and drifted roster NPC gender/race across existing campaigns."""
    from mechanics.world.locations.hierarchy import (
        format_tiered_location_string,
        parse_tiered_location,
        resolve_default_sublocation,
    )

    # 1. Self-heal "Main Area" in sessions.current_location
    try:
        sess_rows = conn.execute("SELECT id, current_location FROM sessions WHERE current_location LIKE '%Main Area%'").fetchall()
        for sr in sess_rows:
            t1, t2, t3 = parse_tiered_location(sr["current_location"], session_id=sr["id"])
            new_loc = format_tiered_location_string(t1, t2, t3)
            if new_loc and new_loc != sr["current_location"]:
                conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", (new_loc, sr["id"]))
    except Exception:
        pass

    # 2. Self-heal "Main Area" in session_locations
    try:
        loc_rows = conn.execute(
            "SELECT id, session_id, zone_name, primary_name, sub_name FROM session_locations WHERE lower(sub_name) = 'main area'"
        ).fetchall()
        for lr in loc_rows:
            new_sub = resolve_default_sublocation(lr["primary_name"] or "", lr["zone_name"] or "", session_id=lr["session_id"])
            if new_sub and new_sub.strip().lower() != "main area":
                conn.execute(
                    "UPDATE session_locations SET sub_name = ? WHERE id = ?",
                    (new_sub, lr["id"]),
                )
    except Exception:
        pass

    # 3. Self-heal "Main Area" in world_nodes
    try:
        wn_rows = conn.execute(
            "SELECT id, session_id, parent_id, name FROM world_nodes WHERE lower(name) = 'main area'"
        ).fetchall()
        for wn in wn_rows:
            parent_name = ""
            if wn["parent_id"]:
                pr = conn.execute(
                    "SELECT name FROM world_nodes WHERE session_id = ? AND node_id = ?",
                    (wn["session_id"], wn["parent_id"]),
                ).fetchone()
                if pr:
                    parent_name = pr["name"] or ""
            new_name = resolve_default_sublocation(parent_name or "Facility", session_id=wn["session_id"])
            if new_name and new_name.strip().lower() != "main area":
                conn.execute("UPDATE world_nodes SET name = ? WHERE id = ?", (new_name, wn["id"]))
    except Exception:
        pass

    # 4. Self-heal drifted contacts & lorebook gender/race against canonical school_directory & anomalous_agent_roster
    try:
        sd_rows = conn.execute("SELECT session_id, name, gender, race FROM school_directory").fetchall()
        for sd in sd_rows:
            if not sd["name"]:
                continue
            sid = sd["session_id"]
            n_low = str(sd["name"]).strip().lower()
            c_gen = str(sd["gender"] or "").strip().lower()
            c_race = str(sd["race"] or "").strip()
            if c_gen and c_race:
                conn.execute(
                    "UPDATE contacts SET gender = ?, race = ? WHERE session_id = ? AND lower(name) = ?",
                    (c_gen, c_race, sid, n_low),
                )
                conn.execute(
                    "UPDATE lorebook SET gender = ?, race = ? WHERE session_id = ? AND lower(name) = ? AND lower(entity_type) = 'person'",
                    (c_gen, c_race, sid, n_low),
                )
    except Exception:
        pass

    try:
        s_rows = conn.execute(
            "SELECT id, extra_json FROM sessions WHERE extra_json LIKE '%anomalous_agent_roster%'"
        ).fetchall()
        for s_row in s_rows:
            sid = s_row["id"]
            try:
                extra_obj = json.loads(s_row["extra_json"] or "{}")
            except Exception:
                continue
            roster_entries = extra_obj.get("anomalous_agent_roster") if isinstance(extra_obj, dict) else None
            if not isinstance(roster_entries, list):
                continue
            for ar in roster_entries:
                if not isinstance(ar, dict) or not ar.get("name"):
                    continue
                n_low = str(ar["name"]).strip().lower()
                c_gen = str(ar.get("gender") or "").strip().lower()
                c_race = str(ar.get("race") or "").strip()
                if c_gen and c_race:
                    conn.execute(
                        "UPDATE contacts SET gender = ?, race = ? WHERE session_id = ? AND lower(name) = ?",
                        (c_gen, c_race, sid, n_low),
                    )
                    conn.execute(
                        "UPDATE lorebook SET gender = ?, race = ? WHERE session_id = ? AND lower(name) = ? AND lower(entity_type) = 'person'",
                        (c_gen, c_race, sid, n_low),
                    )
    except Exception:
        pass

def _migrate_phone_appointments_to_commitments(conn: sqlite3.Connection) -> int:
    """Migrates existing phone_appointments rows into the unified commitments_ledger table."""
    cursor = conn.cursor()
    tbl = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='phone_appointments'").fetchone()
    if not tbl:
        return 0
    cols = {r[1] for r in cursor.execute("PRAGMA table_info(commitments_ledger)").fetchall()}
    has_end_day = "end_day" in cols
    rows = cursor.execute("SELECT * FROM phone_appointments").fetchall()
    migrated = 0
    now = time.time()
    for row in rows:
        d = dict(row)
        sess_id = d.get("session_id")
        npc_id = d.get("npc_id", "")
        npc_name = d.get("npc_name", "") or npc_id
        loc = d.get("rendezvous_location", "")
        node_id = d.get("target_node_id", "") or ""
        created_min = d.get("created_minute", 0) or 0
        expiry_min = d.get("expiry_minute", 0) or (created_min + 45 if created_min else 1439)
        created_at = d.get("created_at") or now
        status = d.get("status", "pending")
        if status in ("stood_up", "missed"):
            status = "flaked"

        c_key = f"rendezvous_{sess_id}_{npc_id}_{int(created_at)}"
        existing = cursor.execute(
            "SELECT id FROM commitments_ledger WHERE session_id=? AND commitment_key=?",
            (sess_id, c_key)
        ).fetchone()
        if existing:
            continue

        participants = [
            {"person_key": "player", "role": "organizer", "status": "active"},
            {"person_key": npc_id, "npc_id": npc_id, "name": npc_name, "role": "participant", "status": status}
        ]
        meta = {
            "reminder_sent": bool(d.get("reminder_sent", 0)),
            "legacy_phone_appt_id": d.get("id"),
        }
        day = (created_min // 1440) + 1 if created_min > 0 else 1
        end_day = (expiry_min // 1440) + 1 if expiry_min > 0 else day
        start_m = created_min % 1440 if created_min > 0 else 0
        end_m = expiry_min % 1440 if expiry_min > 0 else 1439
        if end_m < start_m and end_day <= day:
            end_day = day + 1
        title = f"Meetup with {npc_name}"
        desc = d.get("topic") or f"Rendezvous at {loc}"

        if has_end_day:
            cursor.execute(
                """INSERT INTO commitments_ledger (
                    session_id, commitment_key, commitment_type, source_entity, target_entity,
                    participants_json, target_location, target_node_id, scheduled_day, end_day,
                    start_minute, end_minute, deadline_turn, status, origin,
                    is_confidential, title, description, metadata_json, turn_created,
                    created_at, updated_at
                ) VALUES (?, ?, 'rendezvous', 'player', ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    sess_id, c_key, npc_id, json.dumps(participants), loc, node_id,
                    day, end_day, start_m, end_m, status, d.get("origin") or "phone_dm",
                    d.get("is_confidential", 0), title, desc, json.dumps(meta),
                    created_at, created_at
                )
            )
        else:
            cursor.execute(
                """INSERT INTO commitments_ledger (
                    session_id, commitment_key, commitment_type, source_entity, target_entity,
                    participants_json, target_location, target_node_id, scheduled_day,
                    start_minute, end_minute, deadline_turn, status, origin,
                    is_confidential, title, description, metadata_json, turn_created,
                    created_at, updated_at
                ) VALUES (?, ?, 'rendezvous', 'player', ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    sess_id, c_key, npc_id, json.dumps(participants), loc, node_id,
                    day, start_m, end_m, status, d.get("origin") or "phone_dm",
                    d.get("is_confidential", 0), title, desc, json.dumps(meta),
                    created_at, created_at
                )
            )
        migrated += 1
    return migrated

def _migrate_contacts_intimacy_profiles(conn: sqlite3.Connection) -> int:
    """
    Migrates existing contacts:
    1. Extracts intimacy attributes from appearance_json into intimate_profile_json.
    2. Backfills pre-game backstory rows into intimate_events table.
    3. Backfills gameplay milestone rows into intimate_events table from intimate_memories_json.
    4. Computes deterministic tracks and caches them in intimate_profile_json['tracks'].
    5. Cleans up appearance_json so it only contains physical traits.
    """
    import hashlib
    from mechanics.social.persona.intimacy.ledger import (
        record_intimate_event,
        compute_intimate_tracks_from_ledger,
    )
    from mechanics.social.persona.intimacy.generation import (
        generate_past_intimate_history,
        persist_generated_past_history
    )
    from mechanics.social.persona.intimacy.formatting import is_romantic_milestone_str

    rows = conn.execute("SELECT * FROM contacts").fetchall()
    migrated_count = 0

    for r in rows:
        d = dict(r)
        sess_id = d["session_id"]
        char_ref = str(d.get("npc_id") or d["id"])
        c_name = d.get("name") or "Unknown"
        c_gender = d.get("gender") or ""
        c_race = d.get("race") or "human"

        try:
            app = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            app = {}

        try:
            prof = json.loads(d.get("intimate_profile_json") or "{}")
        except Exception:
            prof = {}

        try:
            mems = json.loads(d.get("intimate_memories_json") or "[]")
        except Exception:
            mems = []

        intimate_keys = (
            "sensitive_spots", "turn_ons", "turn_offs", "fetishes", "desires_and_kinks",
            "combined_turn_ons", "act_likes", "act_dislikes", "favorite_acts", "disliked_acts",
            "intimate_demeanor", "intimate_dynamic", "erotic_openness", "undergarments",
            "bra", "underwear", "predetermined_intercourse", "had_first_time_with_player",
            "intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
            "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
            "anal_revealed", "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed",
            "fetishes_revealed", "act_preferences_revealed", "underwear_revealed",
            "demeanor_revealed", "dynamic_revealed", "openness_revealed", "all_revealed"
        )

        # Read experience & openness before modifying app
        cur_i = prof.get("intercourse_experience") or app.get("intercourse_experience") or "virgin"
        cur_o = prof.get("oral_experience") or app.get("oral_experience") or "inexperienced"
        cur_m = prof.get("manual_experience") or app.get("manual_experience") or "inexperienced"
        cur_a = prof.get("anal_experience") or app.get("anal_experience") or "inexperienced"
        openness = prof.get("erotic_openness") or app.get("erotic_openness") or "moderate"

        for k in intimate_keys:
            if k in app and k not in prof:
                prof[k] = app[k]

        disc_flags = prof.get("disclosure_flags", {})
        for k in intimate_keys:
            if k.endswith("_revealed"):
                disc_flags[k] = bool(prof.get(k, False))
        prof["disclosure_flags"] = disc_flags

        if "undergarments" not in prof or not isinstance(prof.get("undergarments"), dict):
            if prof.get("bra") or prof.get("underwear"):
                prof["undergarments"] = {
                    "bra": prof.get("bra", ""),
                    "underwear": prof.get("underwear", "")
                }

        # Gather any legacy past history memories
        past_memories = [m for m in mems if isinstance(m, str) and m.strip().startswith("Past History:")]
        if not past_memories and app.get("past_intimate_history"):
            past_memories.append(str(app.get("past_intimate_history")))
        if isinstance(app.get("past_intimate_entries"), list):
            for pe in app["past_intimate_entries"]:
                if pe and pe not in past_memories:
                    past_memories.append(str(pe))

        # Clean physical appearance dict
        for k in intimate_keys:
            app.pop(k, None)
        for k in ("intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                  "past_intimate_history", "past_intimate_entries", "intimate_memories"):
            app.pop(k, None)

        # Check existing events
        ev_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM intimate_events WHERE session_id = ? AND character_id = ?",
            (sess_id, char_ref)
        ).fetchone()
        has_events = ev_count and ev_count["cnt"] > 0

        if not has_events:
            events_created = 0
            if past_memories:
                from mechanics.social.persona.intimacy.ledger import parse_past_history_entry_to_events
                for pm in past_memories:
                    parsed_evs = parse_past_history_entry_to_events(pm, char_gender=c_gender)
                    for pev in parsed_evs:
                        record_intimate_event(
                            session_id=sess_id,
                            character_id=char_ref,
                            partner_name=pev.get("partner_name", "Past Partner"),
                            act_type=pev.get("act_type", "intercourse"),
                            direction=pev.get("direction", "mutual"),
                            partner_id=None,
                            partner_role=pev.get("partner_role", "Former Classmate"),
                            turn_number=0,
                            event_origin="past_history",
                            is_physical=bool(pev.get("is_physical", True)),
                            count=pev.get("count", 1),
                            climax_count=0,
                            is_secret_affair=bool(pev.get("is_secret_affair", False)),
                            narrative_summary=pm,
                            character_gender=c_gender,
                            conn=conn
                        )
                        events_created += 1

            seed_str = f"{c_name}_{c_race}_{sess_id}".encode("utf-8")
            h_val = int(hashlib.md5(seed_str).hexdigest(), 16)

            if events_created == 0 and (cur_i == "non_virgin" or cur_o != "inexperienced" or cur_m != "inexperienced" or cur_a != "inexperienced"):
                past_hist = generate_past_intimate_history(
                    hash_val=h_val,
                    race=c_race,
                    gender=c_gender,
                    openness=openness,
                    intercourse=cur_i,
                    oral=cur_o,
                    manual=cur_m,
                    anal=cur_a
                )
                if past_hist:
                    persist_generated_past_history(
                        session_id=sess_id,
                        character_id=char_ref,
                        history_dict=past_hist,
                        character_gender=c_gender,
                        conn=conn
                    )

            # Backfill any gameplay milestone memories
            for m in mems:
                m_str = str(m).strip() if m else ""
                if not m_str or m_str.startswith("Past History:"):
                    continue
                if is_romantic_milestone_str(m_str):
                    low = m_str.lower()
                    act = "kiss"
                    dirn = "mutual"
                    if "intercourse" in low or "intimate night" in low:
                        act = "intercourse"
                    elif "oral" in low:
                        act = "oral"
                        dirn = "receive" if "received" in low else ("give" if "provided" in low or "performed" in low else "mutual")
                    elif "manual" in low or "handjob" in low or "fingered" in low:
                        act = "manual"
                        dirn = "receive" if "received" in low else ("give" if "stimulated" in low or "gave" in low else "mutual")
                    elif "anal" in low:
                        act = "anal"
                        dirn = "receive" if "received" in low else "give"
                    elif "confess" in low:
                        act = "confession"
                    elif "date" in low:
                        act = "date"

                    record_intimate_event(
                        session_id=sess_id,
                        character_id=char_ref,
                        partner_name="Player",
                        act_type=act,
                        direction=dirn,
                        partner_id="player",
                        partner_role="Player",
                        turn_number=1,
                        event_origin="gameplay",
                        is_physical=(act in ("intercourse", "oral", "manual", "anal", "kiss")),
                        narrative_summary=m_str,
                        character_gender=c_gender,
                        partner_gender="unknown",
                        conn=conn
                    )

        ev_rows = conn.execute(
            "SELECT * FROM intimate_events WHERE session_id = ? AND character_id = ? AND is_physical = 1",
            (sess_id, char_ref)
        ).fetchall()
        tracks = compute_intimate_tracks_from_ledger([dict(er) for er in ev_rows])
        prof["tracks"] = tracks

        conn.execute(
            """UPDATE contacts
               SET appearance_json = ?, intimate_profile_json = ?
               WHERE id = ?""",
            (json.dumps(app), json.dumps(prof), d["id"])
        )
        migrated_count += 1

    return migrated_count
