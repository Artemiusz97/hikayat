from __future__ import annotations

import json
import time
from ..core import (get_conn)

def get_recruitment_cooldown(session_id: int, npc_name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT party_recruit_cooldowns_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_recruit_cooldowns_json"]:
            return 0
        try:
            cds = json.loads(row["party_recruit_cooldowns_json"])
        except Exception:
            return 0

        clean_name = str(npc_name).strip().lower()
        entry = cds.get(clean_name)
        if not entry:
            return 0

        if isinstance(entry, (int, float)):
            return max(0, int(entry))

        if isinstance(entry, dict):
            curr_day = int(row["current_day"]) if row["current_day"] is not None else 1
            curr_min = int(row["current_minute"]) if row["current_minute"] is not None else 480
            curr_total = curr_day * 1440 + curr_min

            until_day = entry.get("until_day", curr_day + 1)
            until_total = entry.get("until_total_minute", curr_total + 1440)

            # Expired if new day has arrived (curr_day >= until_day) OR 24 in-game hours have passed
            if curr_day >= until_day or curr_total >= until_total:
                return 0

            rem_minutes = max(1, until_total - curr_total)
            return rem_minutes

        return 0

def set_recruitment_cooldown(session_id: int, npc_name: str, turns: int = None, hours: int = 24, until_next_day: bool = True):
    with get_conn() as conn:
        row = conn.execute("SELECT party_recruit_cooldowns_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        cds = {}
        curr_day = 1
        curr_min = 480
        if row:
            if row["current_day"] is not None:
                curr_day = int(row["current_day"])
            if row["current_minute"] is not None:
                curr_min = int(row["current_minute"])
            if row["party_recruit_cooldowns_json"]:
                try:
                    cds = json.loads(row["party_recruit_cooldowns_json"])
                except Exception:
                    cds = {}
        clean_name = str(npc_name).strip().lower()
        if turns is not None:
            cds[clean_name] = int(turns)
        else:
            curr_total = curr_day * 1440 + curr_min
            until_total = curr_total + (hours * 60)
            until_day = curr_day + 1 if until_next_day else curr_day
            cds[clean_name] = {
                "failed_day": curr_day,
                "failed_minute": curr_min,
                "until_day": until_day,
                "until_total_minute": until_total,
                "hours": hours,
            }
        conn.execute("UPDATE sessions SET party_recruit_cooldowns_json=?, updated_at=? WHERE id=?",
                     (json.dumps(cds), time.time(), session_id))

def decrement_recruitment_cooldowns(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT party_recruit_cooldowns_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_recruit_cooldowns_json"]:
            return
        try:
            cds = json.loads(row["party_recruit_cooldowns_json"])
        except Exception:
            return

        curr_day = int(row["current_day"]) if row["current_day"] is not None else 1
        curr_min = int(row["current_minute"]) if row["current_minute"] is not None else 480
        curr_total = curr_day * 1440 + curr_min

        new_cds = {}
        for k, v in cds.items():
            if isinstance(v, (int, float)):
                if v > 1:
                    new_cds[k] = v - 1
            elif isinstance(v, dict):
                until_day = v.get("until_day", curr_day + 1)
                until_total = v.get("until_total_minute", curr_total + 1440)
                if curr_day < until_day and curr_total < until_total:
                    new_cds[k] = v

        conn.execute("UPDATE sessions SET party_recruit_cooldowns_json=?, updated_at=? WHERE id=?",
                     (json.dumps(new_cds), time.time(), session_id))

def get_confession_cooldown(session_id: int, npc_name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT confession_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["confession_cooldowns_json"]:
            return 0
        try:
            cds = json.loads(row["confession_cooldowns_json"])
            return int(cds.get(str(npc_name).strip().lower(), 0))
        except Exception:
            return 0

def set_confession_cooldown(session_id: int, npc_name: str, turns: int = 3):
    with get_conn() as conn:
        row = conn.execute("SELECT confession_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        cds = {}
        if row and row["confession_cooldowns_json"]:
            try:
                cds = json.loads(row["confession_cooldowns_json"])
            except Exception:
                cds = {}
        cds[str(npc_name).strip().lower()] = turns
        conn.execute("UPDATE sessions SET confession_cooldowns_json=?, updated_at=? WHERE id=?",
                     (json.dumps(cds), time.time(), session_id))

def decrement_confession_cooldowns(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT confession_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["confession_cooldowns_json"]:
            return
        try:
            cds = json.loads(row["confession_cooldowns_json"])
        except Exception:
            return
        new_cds = {k: v - 1 for k, v in cds.items() if v > 1}
        conn.execute("UPDATE sessions SET confession_cooldowns_json=?, updated_at=? WHERE id=?",
                     (json.dumps(new_cds), time.time(), session_id))

def get_contact_request_cooldown(session_id: int, npc_name: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT extra_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["extra_json"]:
            return 0
        try:
            extra = json.loads(row["extra_json"])
            cds = extra.get("contact_request_cooldowns", {})
        except Exception:
            return 0

        clean_name = str(npc_name).strip().lower()
        clean_slug = clean_name.replace(" ", "_")
        entry = cds.get(clean_name) or cds.get(clean_slug)
        if not entry and clean_name:
            for k_cd, v_cd in cds.items():
                k_low = str(k_cd or "").strip().lower()
                if not k_low:
                    continue
                if (
                    (" " not in clean_name and "_" not in clean_name and (k_low.startswith(f"{clean_name} ") or k_low.startswith(f"{clean_name}_")))
                    or (" " not in k_low and "_" not in k_low and (clean_name.startswith(f"{k_low} ") or clean_slug.startswith(f"{k_low}_")))
                ):
                    entry = v_cd
                    break
        if not entry:
            return 0

        if isinstance(entry, (int, float)):
            return max(0, int(entry))

        if isinstance(entry, dict):
            curr_day = int(row["current_day"]) if row["current_day"] is not None else 1
            curr_min = int(row["current_minute"]) if row["current_minute"] is not None else 480
            curr_total = curr_day * 1440 + curr_min

            until_day = entry.get("until_day")
            if until_day is not None:
                if curr_day >= int(until_day):
                    return 0
                return max(1, entry.get("until_total_minute", curr_total + 1440) - curr_total)

            until_total = entry.get("until_total_minute", curr_total + 1440)
            if curr_total >= until_total:
                return 0

            return max(1, until_total - curr_total)

        return 0

def set_contact_request_cooldown(session_id: int, npc_name: str, hours: int = 24, until_next_day: bool = True):
    with get_conn() as conn:
        row = conn.execute("SELECT extra_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        extra = {}
        curr_day = 1
        curr_min = 480
        if row:
            if row["current_day"] is not None:
                curr_day = int(row["current_day"])
            if row["current_minute"] is not None:
                curr_min = int(row["current_minute"])
            if row["extra_json"]:
                try:
                    extra = json.loads(row["extra_json"])
                except Exception:
                    extra = {}
        cds = extra.get("contact_request_cooldowns", {})
        clean_name = str(npc_name).strip().lower()
        curr_total = curr_day * 1440 + curr_min
        until_total = curr_total + (hours * 60)
        until_day = curr_day + 1 if until_next_day else curr_day
        cd_data = {
            "failed_day": curr_day,
            "failed_minute": curr_min,
            "until_day": until_day,
            "until_total_minute": until_total,
            "hours": hours,
        }
        cds[clean_name] = cd_data
        clean_slug = clean_name.replace(" ", "_")
        if clean_slug and clean_slug != clean_name:
            cds[clean_slug] = cd_data

        extra["contact_request_cooldowns"] = cds
        conn.execute("UPDATE sessions SET extra_json=?, updated_at=? WHERE id=?",
                     (json.dumps(extra), time.time(), session_id))

def decrement_contact_request_cooldowns(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT extra_json, current_day, current_minute FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["extra_json"]:
            return
        try:
            extra = json.loads(row["extra_json"])
            cds = extra.get("contact_request_cooldowns", {})
        except Exception:
            return
        if not cds:
            return

        curr_day = int(row["current_day"]) if row["current_day"] is not None else 1
        curr_min = int(row["current_minute"]) if row["current_minute"] is not None else 480
        curr_total = curr_day * 1440 + curr_min

        new_cds = {}
        for k, v in cds.items():
            if isinstance(v, (int, float)):
                if v > 1:
                    new_cds[k] = v - 1
            elif isinstance(v, dict):
                until_day = v.get("until_day")
                if until_day is not None:
                    if curr_day < int(until_day):
                        new_cds[k] = v
                else:
                    until_total = v.get("until_total_minute", curr_total + 1440)
                    if curr_total < until_total:
                        new_cds[k] = v

        extra["contact_request_cooldowns"] = new_cds
        conn.execute("UPDATE sessions SET extra_json=?, updated_at=? WHERE id=?",
                     (json.dumps(extra), time.time(), session_id))

def get_phone_social_state(session_id: int) -> dict:
    """Returns the current phone social state dict (rumor charges, friend request cooldowns, etc.)."""
    with get_conn() as conn:
        row = conn.execute("SELECT phone_social_state_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["phone_social_state_json"]:
            return {}
        try:
            return json.loads(row["phone_social_state_json"])
        except Exception:
            return {}

def update_phone_social_state(session_id: int, state: dict):
    """Updates the phone social state dict for a session."""
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET phone_social_state_json=?, updated_at=? WHERE id=?",
                     (json.dumps(state), time.time(), session_id))
