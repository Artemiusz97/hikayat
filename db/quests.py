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

_TRANSIENT_SUB_OBJ_KEYS = {
    "waypoints",
    "active_waypoint",
    "stage_label",
    "stage_index",
    "total_stages",
    "completed_stages",
}

def _normalize_loc_arrow(loc: str) -> str:
    if not loc:
        return ""
    return re.sub(r"\s*->\s*", " ➔ ", str(loc).strip())

def _clean_sub_objectives_for_storage(sub_objectives: list | str | None) -> str:
    if isinstance(sub_objectives, list):
        cleaned = []
        for so in sub_objectives:
            if isinstance(so, dict):
                cleaned.append({k: v for k, v in so.items() if k not in _TRANSIENT_SUB_OBJ_KEYS})
            else:
                cleaned.append(so)
        return json.dumps(cleaned)
    return sub_objectives or "[]"

def upsert_quest(session_id: int, quest_id: str, quest_type: str, title: str,
                 objective: str, progress: str = "", current_clues: str = "",
                 status: str = "Active", reward_xp: int = 100, reward_gold: int = 25,
                 reward_stat_points: int = 0, reward_item: str = "",
                 is_story_quest: int = 0, clues_required: int = 3,
                 quest_notes: str = None, sub_objectives: list | str = None,
                 blueprint_id: str = None, client_npc: str = None,
                 client_location: str = None, required_item: str = None,
                 required_item_count: int = None, strikes: int = None,
                 max_strikes: int = None, deadline_day: int = None,
                 deadline_minute: int = None, resolution_approach: str = None) -> dict:
    now = time.time()
    sub_obj_str = _clean_sub_objectives_for_storage(sub_objectives)
    if blueprint_id is None:
        try:
            from mechanics.narrative.blueprints import get_blueprint_for_archetype
            blueprint_id = get_blueprint_for_archetype(quest_type, objective)
        except Exception:
            blueprint_id = ""

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, reward_claimed FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE quests SET
                   quest_type=?, title=?, objective=?, progress=?, current_clues=?,
                   status=?, reward_xp=?, reward_gold=?, reward_stat_points=?, reward_item=?,
                   is_story_quest=?, clues_required=?,
                   quest_notes=COALESCE(?, quest_notes),
                   sub_objectives_json=CASE WHEN ? != '[]' THEN ? ELSE sub_objectives_json END,
                   blueprint_id=COALESCE(?, blueprint_id),
                   client_npc=COALESCE(?, client_npc),
                   client_location=COALESCE(?, client_location),
                   required_item=COALESCE(?, required_item),
                   required_item_count=COALESCE(?, required_item_count),
                   strikes=COALESCE(?, strikes),
                   max_strikes=COALESCE(?, max_strikes),
                   deadline_day=COALESCE(?, deadline_day),
                   deadline_minute=COALESCE(?, deadline_minute),
                   resolution_approach=COALESCE(?, resolution_approach),
                   updated_at=?
                   WHERE id=?""",
                (quest_type or "Main Quest", title, objective, progress or "", current_clues or "",
                 status or "Active", reward_xp, reward_gold, reward_stat_points, reward_item or "",
                 is_story_quest, clues_required,
                 quest_notes, sub_obj_str, sub_obj_str,
                 blueprint_id, client_npc, client_location, required_item, required_item_count,
                 strikes, max_strikes, deadline_day, deadline_minute, resolution_approach,
                 now, existing["id"])
            )
        else:
            conn.execute(
                """INSERT INTO quests
                   (session_id, quest_id, quest_type, title, objective, progress, current_clues,
                    status, reward_xp, reward_gold, reward_stat_points, reward_item,
                    is_story_quest, clues_required, reward_claimed, quest_notes,
                    sub_objectives_json, blueprint_id, client_npc, client_location,
                    required_item, required_item_count, strikes, max_strikes,
                    deadline_day, deadline_minute, resolution_approach, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, quest_id, quest_type or "Main Quest", title, objective, progress or "",
                 current_clues or "", status or "Active", reward_xp, reward_gold, reward_stat_points,
                 reward_item or "", is_story_quest, clues_required, quest_notes or "",
                 sub_obj_str, blueprint_id or "", client_npc or "", client_location or "",
                 required_item or "", int(required_item_count if required_item_count is not None else 1),
                 int(strikes or 0), int(max_strikes if max_strikes is not None else 2),
                 deadline_day, deadline_minute, resolution_approach or "", now, now)
            )

    return get_quest_by_id(session_id, quest_id)

def _enrich_quest_dict(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["strikes"] = int(d.get("strikes") or 0)
    d["max_strikes"] = int(d.get("max_strikes") or 2)
    d["resolution_approach"] = str(d.get("resolution_approach") or "")
    if d.get("sub_objectives_json"):
        try:
            raw_sos = json.loads(d["sub_objectives_json"])
            d["sub_objectives"] = [dict(so) if isinstance(so, dict) else so for so in (raw_sos or [])]
        except Exception:
            d["sub_objectives"] = []
    else:
        d["sub_objectives"] = []

    session_id = d.get("session_id")
    quest_id = d.get("quest_id")
    all_wps = []
    if session_id and quest_id:
        try:
            with get_conn() as conn:
                wp_rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=? AND quest_id=?
                       ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                    (session_id, quest_id)
                ).fetchall()
                for wr in wp_rows:
                    w_dict = dict(wr)
                    try:
                        appr_raw = w_dict.get("approaches_json") or "[]"
                        w_dict["approaches"] = json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
                    except Exception:
                        w_dict["approaches"] = []
                    if w_dict.get("target_location"):
                        w_dict["target_location"] = _normalize_loc_arrow(w_dict["target_location"])
                    w_dict["static_target_location"] = w_dict.get("target_location", "")
                    if w_dict.get("follow_npc_schedule") and w_dict.get("target_npc"):
                        try:
                            from mechanics.world.waypoints.matching import resolve_effective_waypoint_location
                            eff_loc = resolve_effective_waypoint_location(session_id, w_dict)
                            if eff_loc:
                                norm_eff = _normalize_loc_arrow(eff_loc)
                                w_dict["live_scheduled_location"] = norm_eff
                                w_dict["effective_location"] = norm_eff
                                w_dict["target_location"] = norm_eff
                        except Exception:
                            pass
                    if not w_dict.get("effective_location"):
                        w_dict["effective_location"] = w_dict.get("target_location", "")
                    all_wps.append(w_dict)
        except Exception:
            all_wps = []

    if d["sub_objectives"]:
        for idx, so in enumerate(d["sub_objectives"]):
            if not isinstance(so, dict):
                continue
            so_id = so.get("id", idx + 1)
            so_wps = [
                w for w in all_wps
                if w.get("sub_obj_id") is not None and _safe_int_db(w.get("sub_obj_id"), -1) == _safe_int_db(so_id, -2)
            ]
            if so_wps:
                active_wp = next((w for w in so_wps if w.get("status") == "active"), None)
                if not active_wp and not so.get("completed"):
                    active_wp = next((w for w in so_wps if w.get("status") == "locked"), so_wps[0])
                elif not active_wp and so.get("completed"):
                    active_wp = so_wps[-1]
                so["waypoints"] = so_wps
                so["active_waypoint"] = active_wp
                so["target_location"] = (active_wp.get("target_location") or "") if active_wp else _normalize_loc_arrow(so.get("target_location") or "")
                so["target_npc"] = (active_wp.get("target_npc") or "") if active_wp else (so.get("target_npc") or "")
                so["stage_label"] = (active_wp.get("stage_label") or "") if active_wp else ""
                so["stage_index"] = int(active_wp.get("stage_index", 1) or 1) if active_wp else 1
                so["total_stages"] = len(so_wps)
                so["completed_stages"] = sum(1 for w in so_wps if w.get("status") == "completed")
            elif so.get("target_location"):
                so["target_location"] = _normalize_loc_arrow(so["target_location"])

        all_so_done = all(isinstance(so, dict) and bool(so.get("completed")) for so in d["sub_objectives"])
        if all_so_done and d.get("status") == "Active":
            d["climax_ready"] = True

        active_so_wps = [
            so["active_waypoint"]
            for so in d["sub_objectives"]
            if isinstance(so, dict) and not so.get("completed") and so.get("active_waypoint")
        ]
        if all_wps:
            d["waypoints"] = all_wps
            d["active_waypoints"] = active_so_wps
            if active_so_wps:
                d["active_waypoint"] = active_so_wps[0]
                if not d.get("target_location"):
                    d["target_location"] = active_so_wps[0].get("target_location", "")
                if not d.get("target_npc"):
                    d["target_npc"] = active_so_wps[0].get("target_npc", "")
                if not d.get("stage_label"):
                    d["stage_label"] = active_so_wps[0].get("stage_label", "")
    elif all_wps:
        quest_wps = [w for w in all_wps if w.get("sub_obj_id") is None] or all_wps
        d["waypoints"] = quest_wps
        active_wp = next((w for w in quest_wps if w.get("status") == "active"), None)
        if not active_wp and d.get("status") != "Completed":
            active_wp = next((w for w in quest_wps if w.get("status") == "locked"), quest_wps[0])
        elif not active_wp and quest_wps:
            active_wp = quest_wps[-1]
        d["active_waypoint"] = active_wp
        d["active_waypoints"] = [active_wp] if active_wp and active_wp.get("status") == "active" else []
        if active_wp:
            d["target_location"] = active_wp.get("target_location") or _normalize_loc_arrow(d.get("target_location") or "")
            d["target_npc"] = active_wp.get("target_npc") or ""
            d["stage_label"] = active_wp.get("stage_label") or ""
        d["stages"] = [
            {
                "stage_index": int(w.get("stage_index", i + 1) or (i + 1)),
                "stage_label": w.get("stage_label", ""),
                "text": w.get("stage_label", ""),
                "target_location": w.get("target_location", ""),
                "target_npc": w.get("target_npc", ""),
                "completion_trigger": w.get("completion_trigger", "arrival"),
                "resource_target": int(w.get("resource_target", 0) or 0),
                "resource_collected": int(w.get("resource_collected", 0) or 0),
                "status": w.get("status", "locked"),
                "completed": w.get("status") == "completed",
            }
            for i, w in enumerate(quest_wps)
        ]

    return d

def get_active_story_quest(session_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM quests
               WHERE session_id=? AND (is_story_quest=1 OR LOWER(quest_type) IN ('story quest', 'main quest'))
               AND LOWER(status)='active'
               ORDER BY (CASE WHEN sub_objectives_json IS NOT NULL AND sub_objectives_json != '[]' AND sub_objectives_json != '' THEN 1 ELSE 0 END) DESC, updated_at DESC""",
            (session_id,)
        ).fetchone()
    return _enrich_quest_dict(row)

def get_session_quests(session_id: int, status: str = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? AND LOWER(status)=LOWER(?) ORDER BY updated_at DESC",
                (session_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? ORDER BY updated_at DESC",
                (session_id,)
            ).fetchall()
    return [_enrich_quest_dict(r) for r in rows if r]

get_quests = get_session_quests

def get_quest_by_id(session_id: int, quest_id: str) -> dict | None:

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
    return _enrich_quest_dict(row)

def update_session_campaign_goals(session_id: int, goals: list):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET campaign_end_goals_json=?, updated_at=? WHERE id=?",
            (json.dumps(goals), time.time(), session_id)
        )

def get_session_campaign_goals(session_id: int) -> list:
    session = db.get_session(session_id)
    if not session or not session.get("campaign_end_goals_json"):
        return []
    try:
        val = json.loads(session["campaign_end_goals_json"])
        return val if isinstance(val, list) else []
    except Exception:
        return []

def set_session_chapter(session_id: int, chapter: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET current_chapter=?, updated_at=? WHERE id=?",
            (chapter, time.time(), session_id)
        )

update_session_chapter = set_session_chapter

def get_session_chapter(session_id: int) -> int:
    session = db.get_session(session_id)
    if not session:
        return 1
    return session.get("current_chapter", 1) or 1

def update_quest_status(session_id: int, quest_id: str, status: str):
    now = time.time()
    with get_conn() as conn:
        if status == "Active":
            row = conn.execute(
                "SELECT deadline_day, is_story_quest FROM quests WHERE session_id=? AND quest_id=?",
                (session_id, quest_id)
            ).fetchone()
            if row and row["deadline_day"] is not None and not row["is_story_quest"]:
                s_row = conn.execute("SELECT current_day FROM sessions WHERE id=?", (session_id,)).fetchone()
                curr_day = int(s_row["current_day"] or 1) if s_row else 1
                min_deadline = curr_day + 5
                if int(row["deadline_day"]) < min_deadline:
                    conn.execute(
                        "UPDATE quests SET deadline_day=? WHERE session_id=? AND quest_id=?",
                        (min_deadline, session_id, quest_id)
                    )
        conn.execute(
            "UPDATE quests SET status=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (status, now, session_id, quest_id)
        )

def append_quest_note_flag_in_db(session_id: int, quest_id: str, flag_key: str, flag_val: str = "1") -> str:
    """Appends or updates a flag in the quest's quest_notes field in SQLite."""
    from mechanics.narrative.blueprints import append_quest_note_flag
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT quest_notes FROM quests WHERE session_id=? AND quest_id=?", (session_id, quest_id)).fetchone()
        cur_notes = row["quest_notes"] if row else ""
        new_notes = append_quest_note_flag(cur_notes, flag_key, flag_val)
        conn.execute("UPDATE quests SET quest_notes=?, updated_at=? WHERE session_id=? AND quest_id=?", (new_notes, now, session_id, quest_id))
        return new_notes

def claim_quest_reward(session_id: int, quest_id: str, party_user_ids: list[int]) -> dict:
    quest = get_quest_by_id(session_id, quest_id)
    if not quest or quest.get("reward_claimed"):
        return {"already_claimed": True}

    try:
        from game_engine.quests import consume_quest_delivery_item_if_needed
        consume_quest_delivery_item_if_needed(session_id, quest, party_user_ids)
    except Exception:
        pass

    rxp = quest.get("reward_xp", 100)
    rgold = quest.get("reward_gold", 25)
    ritem = quest.get("reward_item") or ""
    notes = str(quest.get("quest_notes") or "")
    is_story_q = bool(quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest"))

    # Anomalous Incursions: Faction Reward Confiscation, 5-Tier Promotion Meter & Vault Log
    anom_promotion_result = None
    anom_reward_note = ""
    scen_key = "fantasy"
    try:
        import scenario_data
        sess_row = db.get_session(session_id) or {}
        scen_key = str(sess_row.get("scenario") or "fantasy")
        if scenario_data.is_anomalous_incursions_scenario(scen_key):
            from mechanics.social.factions import get_anomalous_faction_state, update_agent_promotion_reputation
            from mechanics.narrative.bounty import parse_anomalous_quest_board_source
            lead_uid = party_user_ids[0] if party_user_ids else sess_row.get("host_user_id")
            fac_st = get_anomalous_faction_state(session_id, user_id=lead_uid)
            player_arch = str(fac_st.get("faction_archetype_key") or "public_agency")
            board_src = parse_anomalous_quest_board_source(quest, session_id=session_id)
            is_mandatory = ("mandatory_daily:1" in notes) or str(quest_id or "").upper().startswith("MAND-")

            # 1. Reward & Loot Confiscation Rules
            if player_arch == "public_agency" and (board_src == "public_agency" or is_story_q or is_mandatory):
                rgold = 0
                ritem = ""
                anom_reward_note = "Taxpayer Mandate: 0G / 0 Loot (salaried Public Agency duty)."
            elif player_arch == "monastic_order" and (board_src == "monastic_order" or is_mandatory):
                rgold = 0
                anom_reward_note = "Sacred Shrine Duty: 0G bounty fee (recovered relics/spoils retained)."

            # 2. 5-Tier Agent Promotion Meter Progression
            if player_arch != "freelancer":
                earns_promo_rep = (
                    is_mandatory
                    or (board_src == player_arch)
                    or is_story_q
                )
                if earns_promo_rep:
                    rep_delta = 15 if (is_mandatory or is_story_q) else 10
                    anom_promotion_result = update_agent_promotion_reputation(
                        session_id=session_id,
                        delta_rep=rep_delta,
                        reason=f"Completed '{quest.get('title', 'Mission')}'",
                        is_mandatory_completion=is_mandatory,
                        user_id=lead_uid,
                    )

            # 3. Record Non-Hostile Entity / Altered Relic Containment to Vault Log (unless failed-forward via dire_cost)
            q_type_low = str(quest.get("quest_type") or "").lower()
            res_app_low = str(quest.get("resolution_approach") or "").lower()
            if res_app_low != "dire_cost" and any(k in q_type_low for k in ("non-hostile", "non_hostile", "altered item", "cursed relic", "relic_retrieval")):
                from mechanics.world.anomalous_events import record_contained_anomaly_to_vault_log, extract_non_hostile_entity_name
                is_nh_type = "non-hostile" in q_type_low or "non_hostile" in q_type_low
                ent_disp = (
                    extract_non_hostile_entity_name(quest)
                    if is_nh_type
                    else str(quest.get("required_item") or quest.get("title") or "Anomalous Specimen")
                )
                record_contained_anomaly_to_vault_log(
                    session_id=session_id,
                    entity_name=ent_disp,
                    category_tag="cursed_relic" if ("relic" in q_type_low or "item" in q_type_low) else "spatial_warp",
                    subtype="non_hostile_entity" if is_nh_type else "environmental_phenomenon",
                    location=str(quest.get("client_location") or sess_row.get("current_location") or "Metropolitan Grid"),
                    containment_note=f"Secured and logged upon completion of '{quest.get('title', 'Containment Operation')}'.",
                    resolution_method="Bounty Containment Protocol",
                    user_id=lead_uid,
                    quest_id=str(quest_id or ""),
                )
    except Exception:
        pass

    levels_gained_by_user = {}
    for uid in party_user_ids:
        lvl_ups = db.add_xp(uid, rxp)
        if lvl_ups:
            levels_gained_by_user[uid] = lvl_ups

        db.apply_hp_mp_delta(uid, 0, 0, rgold)

        if ritem:
            import scenario_data as _sd_q
            if _sd_q.is_anomalous_incursions_scenario(scen_key):
                try:
                    from mechanics.combat.items.consumables.generators import generate_procedural_potion
                    r_lower = str(ritem).lower()
                    eff_tags = ["mana_restore"] if any(w in r_lower for w in ("stabilizer", "incense", "ampoule", "focus", "spirit")) else ["healing"]
                    pot = generate_procedural_potion(tier=2, effect_tags=eff_tags, genre="anomalous_incursions")
                    db.add_item(uid, ritem, pot.get("item_type", "Potion"), pot.get("effect", "Restores HP"), 1)
                except Exception:
                    db.add_item(uid, ritem, "Potion", "Restores 35 HP", 1)
            else:
                db.add_item(uid, ritem, "Quest", "Quest Reward", 1)

    # Client Affinity Boost: +8 for personal commissions, +5 for standard quests
    client_affinity_gain = 0
    client_npc = quest.get("client_npc") or ""
    notes = str(quest.get("quest_notes") or "")
    if client_npc:
        client_affinity_gain = 8 if (quest_id.startswith("COMM-") or "commission:1" in notes) else 5
        try:
            db.update_relationship_score(session_id, client_npc, delta_score=client_affinity_gain)
        except Exception:
            pass

    # Sponsoring Faction Rep Gain & Rival Faction Reputation Ripple (-5)
    faction_rep_gained = 0
    rival_rep_deltas = {}
    if "faction:" in notes or "rival_faction:" in notes:
        try:
            parts = [p.strip() for p in re.split(r'[|\n]+', notes) if p.strip()]
            faction_id = ""
            riv_ids = []
            for p in parts:
                if p.startswith("faction:"):
                    faction_id = p.split(":", 1)[1].strip()
                elif p.startswith("rep_reward:"):
                    faction_rep_gained = int(p.split(":", 1)[1].strip())
                elif p.startswith("rival_faction:"):
                    r_val = p.split(":", 1)[1].strip()
                    if r_val and r_val not in riv_ids:
                        riv_ids.append(r_val)
            if faction_id:
                if faction_rep_gained <= 0:
                    faction_rep_gained = 10
                db.upsert_faction(session_id, faction_id, delta_score=faction_rep_gained, notes="Faction bounty completed")
                try:
                    s_fac = db.get_faction(session_id, faction_id)
                    if s_fac and s_fac.get("rival_faction_ids"):
                        for r in s_fac["rival_faction_ids"]:
                            if r and str(r).strip() not in riv_ids:
                                riv_ids.append(str(r).strip())
                except Exception:
                    pass

            for rid in riv_ids:
                if rid and rid != faction_id:
                    try:
                        db.upsert_faction(session_id, rid, delta_score=-5, notes=f"Rival operation '{quest.get('title')}' completed")
                        rival_rep_deltas[rid] = -5
                    except Exception:
                        pass
        except Exception:
            pass


    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET reward_claimed=1, status='Completed', updated_at=? WHERE session_id=? AND quest_id=?",
            (time.time(), session_id, quest_id)
        )

    return {
        "claimed": True,
        "title": quest["title"],
        "quest_type": quest["quest_type"],
        "is_story_quest": bool(quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest")),
        "xp": rxp,
        "gold": rgold,
        "item": ritem,
        "levels_gained": levels_gained_by_user,
        "_item_granted_in_db": bool(ritem),
        "client_affinity_gained": client_affinity_gain,
        "faction_rep_gained": faction_rep_gained,
        "rival_rep_deltas": rival_rep_deltas,
        "anomalous_promotion": anom_promotion_result,
        "anomalous_reward_note": anom_reward_note,
    }

def add_session_clue(
    session_id: int,
    title: str,
    lead_text: str,
    category: str = "physical",
    source_location: str = "",
    linked_npc: str = "",
    quest_id: str = "",
    chapter: int = 1,
    is_verified: int = 0,
    deduction_parents: list = None
) -> int:
    """Inserts a new structured evidence record into session_clues with deduplication check."""
    if not title or not lead_text:
        return 0
    clean_title = title.strip()[:100]
    clean_lead = lead_text.strip()
    clean_cat = category.strip().lower() if category else "physical"
    if clean_cat not in ("physical", "testimonial", "digital", "document", "deduction"):
        clean_cat = "physical"
    parents_json = json.dumps(deduction_parents) if isinstance(deduction_parents, list) else "[]"
    now = time.time()

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
            (session_id,)
        ).fetchall()
        t_clean_low = clean_title.lower()
        l_clean_low = clean_lead.lower()
        for r in rows:
            r_title_low = str(r["title"]).lower()
            r_lead_low = str(r["lead_text"]).lower()
            if r_title_low == t_clean_low or r_lead_low == l_clean_low:
                return r["id"]
            if l_clean_low in r_lead_low or r_lead_low in l_clean_low:
                return r["id"]

        cur = conn.execute(
            """INSERT INTO session_clues
               (session_id, quest_id, chapter, title, lead_text, category, source_location, linked_npc, is_verified, deduction_parents_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, quest_id or "", chapter or 1, clean_title, clean_lead, clean_cat, source_location or "", linked_npc or "", int(is_verified), parents_json, now, now)
        )
        new_id = cur.lastrowid

        # D12 Smart Tiered 20-Clue Caseboard Cap:
        # Cap active unconsumed leads at 20 by auto-archiving (is_consumed=1) oldest completed-chapter
        # or circumstantial/side-bounty clues first; NEVER evict active Story Quest clues or Breakthroughs.
        try:
            all_rows = conn.execute(
                "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
            consumed_by_parent: set[int] = set()
            for r in all_rows:
                try:
                    for pid in (json.loads(r["deduction_parents_json"] or "[]") or []):
                        consumed_by_parent.add(int(pid))
                except Exception:
                    pass

            active_unconsumed = []
            for r in all_rows:
                rd = dict(r)
                if rd.get("category") == "deduction":
                    continue
                if bool(rd.get("is_consumed")) or rd["id"] in consumed_by_parent:
                    continue
                active_unconsumed.append(rd)

            if len(active_unconsumed) > 20:
                sq_rows = conn.execute(
                    "SELECT quest_id FROM quests WHERE session_id=? AND status='Active' AND is_story_quest=1",
                    (session_id,),
                ).fetchall()
                active_sq_ids = {str(sr["quest_id"]) for sr in sq_rows if sr["quest_id"]}
                cur_ch_val = int(chapter or 1)
                evictable = [
                    rd for rd in active_unconsumed
                    if rd["id"] != new_id
                    and rd.get("category") != "deduction"
                    and str(rd.get("quest_id") or "") not in active_sq_ids
                ]
                evictable.sort(
                    key=lambda rd: (
                        0 if int(rd.get("chapter") or 1) < cur_ch_val else (1 if not rd.get("quest_id") else 2),
                        float(rd.get("created_at") or 0.0),
                        int(rd["id"]),
                    )
                )
                overflow = len(active_unconsumed) - 20
                for target_rd in evictable[:overflow]:
                    conn.execute(
                        "UPDATE session_clues SET is_consumed=1, updated_at=? WHERE id=?",
                        (now, target_rd["id"]),
                    )
        except sqlite3.OperationalError:
            pass

        return new_id

def get_session_clues(
    session_id: int,
    chapter: int = None,
    linked_npc: str = None,
    category: str = None,
    is_verified: int = None
) -> list[dict]:
    """Retrieves evidence records from session_clues with optional filters."""
    query = "SELECT * FROM session_clues WHERE session_id=?"
    params = [session_id]
    if chapter is not None:
        query += " AND chapter=?"
        params.append(chapter)
    if linked_npc:
        query += " AND (LOWER(linked_npc)=? OR LOWER(linked_npc) LIKE ?)"
        params.extend([linked_npc.strip().lower(), f"%{linked_npc.strip().lower()}%"])
    if category:
        query += " AND category=?"
        params.append(category.strip().lower())
    if is_verified is not None:
        query += " AND is_verified=?"
        params.append(int(is_verified))
    query += " ORDER BY is_verified DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        consumed_ids = set()
        for r in rows:
            try:
                parents = json.loads(r["deduction_parents_json"] or "[]")
                consumed_ids.update(parents)
            except Exception:
                pass

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
            except Exception:
                d["deduction_parents"] = []
            d["is_consumed"] = bool(d.get("is_consumed")) or (d["id"] in consumed_ids)
            results.append(d)
        return results

def get_session_clue_by_id(clue_id: int) -> dict | None:
    """Fetches a single evidence record by ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM session_clues WHERE id=?", (clue_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
        except Exception:
            d["deduction_parents"] = []
            
        # Check if this clue was consumed by any other deduction
        consumed = False
        all_parents_rows = conn.execute("SELECT deduction_parents_json FROM session_clues WHERE session_id=?", (d["session_id"],)).fetchall()
        for pr in all_parents_rows:
            try:
                p_list = json.loads(pr[0] or "[]")
                if d["id"] in p_list:
                    consumed = True
                    break
            except Exception:
                pass
        d["is_consumed"] = bool(d.get("is_consumed")) or consumed
        return d

def verify_session_clue(clue_id: int) -> bool:
    """Marks an evidence record as verified."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE session_clues SET is_verified=1, updated_at=? WHERE id=?", (time.time(), clue_id))
        return cur.rowcount > 0

def delete_session_clue(clue_id: int) -> bool:
    """Deletes an evidence record by ID."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM session_clues WHERE id=?", (clue_id,))
        return cur.rowcount > 0

def apply_caseboard_breakthrough_to_quests(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str
) -> dict:
    """
    Checks active quests and sub-objectives against a synthesized Caseboard deduction.
    Auto-advances intermediate Stage 1 scouting/investigation to Stage 2 Confrontation,
    and tags the quest with 'caseboard_breakthrough:1' to unlock Breakthrough Leverage.
    """
    matched_qids = []
    advanced_qids = []

    parent_clues = []
    for pid in clue_ids:
        cl = get_session_clue_by_id(pid)
        if cl:
            parent_clues.append(cl)

    parent_qids = {str(c.get("quest_id")).strip() for c in parent_clues if c.get("quest_id")}
    parent_npcs = {str(c.get("linked_npc")).strip().lower() for c in parent_clues if c.get("linked_npc")}

    combined_text = f"{title} {lead_text}".lower()
    text_words = set(re.findall(r'\b[a-z]{4,}\b', combined_text)) - {
        "this", "that", "with", "from", "have", "been", "were", "what", "some", "discovered", "evidence"
    }

    active_quests = get_session_quests(session_id, status="Active") or []
    for q in active_quests:
        qid = q.get("quest_id", "")
        if not qid:
            continue
        all_wps = get_quest_waypoints(session_id, qid, None) or []
        active_wp = get_active_waypoint(session_id, qid, None)

        is_match = False
        if qid in parent_qids:
            is_match = True
        elif parent_npcs and any(str(w.get("target_npc", "")).strip().lower() in parent_npcs for w in all_wps):
            is_match = True
        elif parent_npcs and (str(q.get("client_npc", "")).strip().lower() in parent_npcs or str(q.get("target_npc", "")).strip().lower() in parent_npcs):
            is_match = True
        elif q.get("blueprint_id") in ("INVESTIGATION", "SOCIAL_MANIPULATION") or q.get("is_story_quest"):
            q_text = f"{q.get('title', '')} {q.get('objective', '')}".lower()
            q_words = set(re.findall(r'\b[a-z]{4,}\b', q_text))
            if len(text_words & q_words) >= 1:
                is_match = True

        if is_match:
            matched_qids.append(qid)
            append_quest_note_flag_in_db(session_id, qid, "caseboard_breakthrough", "1")

            # Auto-advance Stage 1 scouting/investigation to Stage 2 Confrontation
            if active_wp and int(active_wp.get("stage_index", 1)) == 1 and len(all_wps) >= 2:
                advance_waypoint(session_id, qid, 1, None)
                advanced_qids.append(qid)

            # Check sub-objectives if story quest
            sub_objs = q.get("sub_objectives") or []
            if isinstance(sub_objs, list) and sub_objs:
                for so in sub_objs:
                    if not isinstance(so, dict) or so.get("completed"):
                        continue
                    so_id = so.get("id")
                    if not so_id:
                        continue
                    so_wp = get_active_waypoint(session_id, qid, so_id)
                    so_all_wps = get_quest_waypoints(session_id, qid, so_id) or []
                    if so_wp and int(so_wp.get("stage_index", 1)) == 1 and len(so_all_wps) >= 2:
                        advance_waypoint(session_id, qid, 1, so_id)
                        if qid not in advanced_qids:
                            advanced_qids.append(qid)

    return {"matched_quest_ids": matched_qids, "advanced_quest_ids": advanced_qids}

def synthesize_deduction_clue(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str,
    chapter: int = 1
) -> int:
    """Creates a verified deduction breakthrough linking parent clues and applying quest breakthrough shortcuts."""
    inherited_npc = ""
    inherited_qid = ""
    for pid in clue_ids:
        cl = get_session_clue_by_id(pid)
        if cl:
            if not inherited_npc and cl.get("linked_npc"):
                inherited_npc = str(cl["linked_npc"]).strip()
            if not inherited_qid and cl.get("quest_id"):
                inherited_qid = str(cl["quest_id"]).strip()

    cid = add_session_clue(
        session_id=session_id,
        title=title,
        lead_text=lead_text,
        category="deduction",
        source_location="Mind Palace / Caseboard",
        linked_npc=inherited_npc,
        quest_id=inherited_qid,
        chapter=chapter,
        is_verified=1,
        deduction_parents=clue_ids
    )
    for parent_id in clue_ids:
        verify_session_clue(parent_id)
        try:
            with get_conn() as conn:
                conn.execute("UPDATE session_clues SET is_consumed=1, updated_at=? WHERE id=?", (time.time(), parent_id))
        except sqlite3.OperationalError:
            pass

    apply_caseboard_breakthrough_to_quests(session_id, clue_ids, title, lead_text)
    return cid

def save_quest_waypoints(session_id: int, quest_id: str, waypoints: list, sub_obj_id: int | None = None):
    """Bulk upsert waypoints for a quest or sub-objective.
    Stage 1 starts as 'active', all others start as 'locked'.
    sub_obj_id=None means the waypoints belong to the whole quest (bounties).
    sub_obj_id=N means they belong to Story Quest sub-objective N.
    """
    if not waypoints:
        return
    now = time.time()
    with get_conn() as conn:
        # Clear existing waypoints for this quest+sub_obj combo first
        if sub_obj_id is None:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            )
        else:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, sub_obj_id)
            )
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, dict):
                continue
            stage_idx = int(wp.get("stage_index", i + 1))
            status = wp.get("status") if wp.get("status") in ("active", "locked", "completed", "failed") else ("active" if stage_idx == 1 else "locked")
            target_loc = str(wp.get("target_location", ""))[:200]
            target_node = str(wp.get("target_node_id", "") or "").strip()
            if not target_node and target_loc:
                try:
                    target_node = db.resolve_node_id_from_location(session_id, target_loc) or ""
                except Exception:
                    target_node = ""
            follow_sched = int(bool(wp.get("follow_npc_schedule", 1 if wp.get("target_npc") else 0)))
            req_item = str(wp.get("required_item", "") or "")[:100]
            phases_val = wp.get("valid_time_phases") or wp.get("valid_time_phases_json") or []
            phases_str = json.dumps(phases_val) if isinstance(phases_val, list) else str(phases_val or "[]")
            appr_val = wp.get("approaches") or wp.get("approaches_json") or []
            appr_str = json.dumps(appr_val) if isinstance(appr_val, list) else str(appr_val or "[]")
            conn.execute(
                """INSERT OR REPLACE INTO quest_waypoints
                   (session_id, quest_id, sub_obj_id, stage_index, stage_label,
                    target_location, target_node_id, target_npc, completion_trigger,
                    resource_target, resource_collected, status,
                    follow_npc_schedule, required_item, valid_time_phases_json, approaches_json,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, quest_id, sub_obj_id, stage_idx,
                    str(wp.get("stage_label", ""))[:200],
                    target_loc,
                    target_node,
                    str(wp.get("target_npc", "") or "")[:100],
                    str(wp.get("completion_trigger", "arrival")),
                    int(wp.get("resource_target", 0)),
                    0,  # resource_collected always starts at 0
                    status,
                    follow_sched,
                    req_item,
                    phases_str,
                    appr_str,
                    now, now
                )
            )

def _hydrate_waypoint_row(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    try:
        vp_raw = d.get("valid_time_phases_json") or "[]"
        d["valid_time_phases"] = json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
    except Exception:
        d["valid_time_phases"] = []
    try:
        ap_raw = d.get("approaches_json") or "[]"
        d["approaches"] = json.loads(ap_raw) if isinstance(ap_raw, str) else (ap_raw or [])
    except Exception:
        d["approaches"] = []
    return d

def get_active_waypoint(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> dict | None:
    """Returns the first 'active' waypoint for this quest/sub-objective, or None."""
    with get_conn() as conn:
        if sub_obj_id is None:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, sub_obj_id)
            ).fetchone()
        return _hydrate_waypoint_row(row)

def get_quest_waypoints(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> list[dict]:
    """Returns all waypoints for this quest/sub-objective ordered by stage_index ASC."""
    with get_conn() as conn:
        if sub_obj_id is None:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL
                   ORDER BY stage_index ASC""",
                (session_id, quest_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=?
                   ORDER BY stage_index ASC""",
                (session_id, quest_id, sub_obj_id)
            ).fetchall()
        return [_hydrate_waypoint_row(r) for r in rows if r]

def advance_waypoint(session_id: int, quest_id: str, stage_index: int, sub_obj_id: int | None = None) -> dict | None:
    """Marks the given stage as 'completed', unlocks the next 'locked' stage to 'active'.
    Returns the newly-unlocked waypoint dict, or None if no more stages remain (quest chain done).
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (now, session_id, quest_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                    (now, session_id, quest_id, next_row["stage_index"])
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='completed'",
                (session_id, quest_id)
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} Milestones", now, session_id, quest_id)
                )
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (now, session_id, quest_id, sub_obj_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, sub_obj_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                    (now, session_id, quest_id, sub_obj_id, next_row["stage_index"])
                )
        return dict(next_row) if next_row else None

def update_waypoint_resource_progress(session_id: int, quest_id: str, stage_index: int, delta: int, sub_obj_id: int | None = None) -> dict:
    """Increment resource_collected for a gathering waypoint.
    Returns {collected, target, complete} after update.
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (delta, now, session_id, quest_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (session_id, quest_id, stage_index)
            ).fetchone()
        else:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (delta, now, session_id, quest_id, sub_obj_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (session_id, quest_id, sub_obj_id, stage_index)
            ).fetchone()
        if row:
            collected = row["resource_collected"]
            target = row["resource_target"]
            return {"collected": collected, "target": target, "complete": target > 0 and collected >= target}
        return {"collected": 0, "target": 0, "complete": False}

def get_all_session_active_waypoints(session_id: int) -> list[dict]:
    """Returns all 'active' waypoints across all quests in a session.
    Used by the location UI to show quest markers on the travel menu.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT qw.*, q.title as quest_title, q.quest_type, q.is_story_quest, q.sub_objectives_json,
                      q.blueprint_id, q.client_npc, q.client_location,
                      q.required_item as quest_required_item, q.required_item_count,
                      q.reward_gold, q.strikes, q.max_strikes, q.resolution_approach, q.quest_notes,
                      q.deadline_day, q.deadline_minute
               FROM quest_waypoints qw
               JOIN quests q ON qw.session_id = q.session_id AND qw.quest_id = q.quest_id
               WHERE qw.session_id=? AND qw.status='active' AND q.status='Active'
               ORDER BY qw.quest_id, qw.sub_obj_id, qw.stage_index""",
            (session_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                vp_raw = d.get("valid_time_phases_json") or "[]"
                d["valid_time_phases"] = json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
            except Exception:
                d["valid_time_phases"] = []
            try:
                appr_raw = d.get("approaches_json") or "[]"
                d["approaches"] = json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
            except Exception:
                d["approaches"] = []
            if d.get("target_location"):
                d["target_location"] = _normalize_loc_arrow(d["target_location"])
            d["static_target_location"] = d.get("target_location", "")
            if d.get("follow_npc_schedule") and d.get("target_npc"):
                try:
                    from mechanics.world.waypoints.matching import resolve_effective_waypoint_location
                    eff_loc = resolve_effective_waypoint_location(session_id, d)
                    if eff_loc:
                        d["live_scheduled_location"] = _normalize_loc_arrow(eff_loc)
                        d["target_location"] = _normalize_loc_arrow(eff_loc)
                except Exception:
                    pass
            so_json = d.get("sub_objectives_json")
            sub_id = d.get("sub_obj_id")
            if so_json and sub_id is not None:
                try:
                    sos = json.loads(so_json) if isinstance(so_json, str) else so_json
                    if isinstance(sos, list):
                        if any(isinstance(s, dict) and int(s.get("id", -1)) == int(sub_id) and s.get("completed") for s in sos):
                            continue
                except Exception:
                    pass
            result.append(d)
        return result

def mark_sub_objective_completed_in_quest(session_id: int, quest_id: str, sub_obj_id: int):
    """Directly marks a Story Quest sub-objective as completed=True in sub_objectives_json.
    Called by the waypoint engine when all waypoint stages for that sub-obj are done.
    This is deterministic Python — no LLM JSON required.
    """
    quest = get_quest_by_id(session_id, quest_id)
    if not quest:
        return
    sub_objs = quest.get("sub_objectives") or []
    changed = False
    for so in sub_objs:
        if isinstance(so, dict) and int(so.get("id", -1)) == int(sub_obj_id):
            if not so.get("completed"):
                so["completed"] = True
                changed = True
            break
    if changed:
        now = time.time()
        with get_conn() as conn:
            conn.execute(
                "UPDATE quests SET sub_objectives_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (_clean_sub_objectives_for_storage(sub_objs), now, session_id, quest_id)
            )
            # Unlock stage 1 of the next sub-objective (sub_obj_id + 1)
            conn.execute(
                "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=1 AND status='locked'",
                (now, session_id, quest_id, int(sub_obj_id) + 1)
            )


# -----------------------------------------------------------------------------
# Phase 2 Strike Counter, Resolution Approach & Failure CRUD
# -----------------------------------------------------------------------------

def increment_quest_strikes(session_id: int, quest_id: str, delta: int = 1) -> dict:
    """Atomically increments strikes on a quest up to max_strikes (default 2).
    Updates quest.progress with a warning note if not yet failed.
    Returns: {strikes, max_strikes, failed: bool, quest: dict}
    """
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strikes, max_strikes, progress, title FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        if not row:
            return {"strikes": 0, "max_strikes": 2, "failed": False, "quest": None}

        curr_strikes = int(row["strikes"] or 0)
        max_s = int(row["max_strikes"] or 2)
        new_strikes = min(max_s, curr_strikes + max(1, delta))
        failed = new_strikes >= max_s

        prog = str(row["progress"] or "")
        if not failed:
            alert_tag = f"[⚠️ {new_strikes}/{max_s} Strikes: Target Alerted]"
            if "[⚠️" in prog:
                prog = re.sub(r'\[⚠️ \d+/\d+ Strikes: Target Alerted\]', alert_tag, prog)
            else:
                prog = f"{prog} {alert_tag}".strip()

        conn.execute(
            "UPDATE quests SET strikes=?, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (new_strikes, prog, now, session_id, quest_id)
        )

    updated_q = get_quest_by_id(session_id, quest_id)
    return {
        "strikes": new_strikes,
        "max_strikes": max_s,
        "failed": failed,
        "quest": updated_q,
    }


def reset_quest_strikes(session_id: int, quest_id: str) -> None:
    """Resets strikes to 0 for a quest (used on story quest fail-forward)."""
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT progress FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        clean_prog = ""
        if row and row["progress"]:
            clean_prog = re.sub(r'\s*\[⚠️ \d+/\d+ Strikes: Target Alerted\]', '', str(row["progress"])).strip()
        conn.execute(
            "UPDATE quests SET strikes=0, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (clean_prog, now, session_id, quest_id)
        )


def set_quest_resolution_approach(session_id: int, quest_id: str, resolution_approach: str) -> dict | None:
    """Updates the resolution_approach on a quest."""
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET resolution_approach=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (str(resolution_approach or ""), now, session_id, quest_id)
        )
    return get_quest_by_id(session_id, quest_id)


def fail_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    resolution_approach: str = "failed_strikes",
    progress_note: str = "Failed",
) -> dict | None:
    """
    Deterministically marks a quest as 'Failed' and sets all non-completed waypoints to 'failed'.
    """
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """UPDATE quests
               SET status='Failed', resolution_approach=?, progress=?, updated_at=?
               WHERE session_id=? AND quest_id=?""",
            (str(resolution_approach or "failed_strikes"), str(progress_note or "Failed"), now, session_id, quest_id)
        )
        conn.execute(
            """UPDATE quest_waypoints
               SET status='failed', updated_at=?
               WHERE session_id=? AND quest_id=? AND status IN ('active', 'locked')""",
            (now, session_id, quest_id)
        )
    return get_quest_by_id(session_id, quest_id)


def expire_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    progress_note: str = "Failed (Contract Expired — Claimed by Rival)"
) -> dict | None:
    """Marks a timed quest as Failed due to deadline expiration (`expired_deadline`)."""
    return fail_quest_and_waypoints(
        session_id=session_id,
        quest_id=quest_id,
        resolution_approach="expired_deadline",
        progress_note=progress_note,
    )


