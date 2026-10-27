import db
import asyncio
import json
import time
import hashlib
import random
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list

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

def _is_empty_info_val(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip().lower() in ("", "none", "unknown", "null", "n/a")
    if isinstance(val, (list, dict, tuple, set)):
        return len(val) == 0
    return False


def _merge_basic_info_safely(existing_info: dict | None, incoming_info: dict | None) -> dict:
    """Non-destructively merges incoming basic_info into existing_info without allowing
    empty strings or placeholder values ('', 'None', 'Unknown') to overwrite populated fields.
    """
    merged = {}
    if isinstance(existing_info, dict):
        for k, v in existing_info.items():
            if not _is_empty_info_val(v):
                merged[k] = v.strip() if isinstance(v, str) else v
    if isinstance(incoming_info, dict):
        for k, v in incoming_info.items():
            if not _is_empty_info_val(v):
                merged[k] = v.strip() if isinstance(v, str) else v
    return merged


_LEADING_ROLE_STOPWORDS = {
    "the", "a", "an", "our", "their", "his", "her", "this", "that",
    "current", "acting", "former", "new", "newly", "appointed", "elected",
    "composed", "strict", "stern", "charismatic", "popular", "renowned",
    "veteran", "ambitious", "diligent", "aloof", "cold", "warm", "friendly",
    "local", "campus", "academy", "school", "high", "student_body"
}

_POSITION_TITLES_PATTERN = (
    r"Vice[\s\-]President|President|Co[\s\-]Captain|Vice[\s\-]Captain|Captain|"
    r"Treasurer|Secretary|Chairman|Chairwoman|Chair|Representative|Prefect|"
    r"Leader|Head|Founder|Manager|Commander|Chief|Director|Officer"
)


def _clean_org_name(raw_org: str) -> str:
    if not raw_org:
        return ""
    tokens = [t for t in raw_org.strip().split() if t]
    while tokens and tokens[0].lower().strip(",.'\"") in _LEADING_ROLE_STOPWORDS:
        tokens.pop(0)
    cleaned = " ".join(tokens).strip(" ,.-'\"")
    if len(cleaned) < 3 or cleaned.lower() in _LEADING_ROLE_STOPWORDS:
        return ""
    return cleaned


def _extract_role_and_affiliation_from_text(
    name: str,
    char_text: str = "",
    scene_narrative: str = "",
    scenario: str = ""
) -> dict:
    """Deterministically extracts role, faction, club, club_role, grade, and narrative
    description for an NPC from their character description/role text and/or scene narration.
    """
    out: dict = {}
    name_clean = (name or "").strip()
    if not name_clean:
        return out

    extracted_role_phrases: list[str] = []
    if char_text and isinstance(char_text, str) and char_text.strip():
        extracted_role_phrases.append(char_text.strip())

    # Search scene_narrative for clauses specifically anchored to this NPC's name
    if scene_narrative and isinstance(scene_narrative, str) and name_clean.lower() in scene_narrative.lower():
        # 1. Appositive after name: "Denise Yamada, the Student Council President, is..."
        m_app = re.search(
            rf"\b{re.escape(name_clean)}\s*,\s*(?:the\s+|a\s+|an\s+)?([^,\.\;\n\"“”]{{3,70}}?)(?:,|\s+is\b|\s+was\b|\s+who\b|\s+stands\b|\s+sits\b|\.|$)",
            scene_narrative,
            flags=re.IGNORECASE
        )
        if m_app:
            cand = m_app.group(1).strip(" ,.-")
            if cand and not any( cand.lower().startswith(v) for v in ("looking ", "smiling", "holding ", "wearing ", "standing ", "sitting ", "walking ", "stepping ", "adjusting ", "leaning ") ):
                extracted_role_phrases.append(cand)
                if "role" not in out and len(cand.split()) <= 7:
                    # Title-case role cleanly if it has institutional keywords
                    out["role"] = cand[0].upper() + cand[1:] if cand else cand

        # 2. Title before name: "Student Council President Denise Yamada"
        m_pre = re.search(
            rf"\b((?:[A-Z][A-Za-z\'\-]+\s+){{0,4}}(?:{_POSITION_TITLES_PATTERN}))\s+{re.escape(name_clean)}\b",
            scene_narrative
        )
        if m_pre:
            cand_pre = _clean_org_name(m_pre.group(1)) or m_pre.group(1).strip()
            if cand_pre:
                extracted_role_phrases.append(cand_pre)
                if "role" not in out:
                    out["role"] = cand_pre

        # 3. Copula after name: "Denise Yamada is the Student Council President"
        m_cop = re.search(
            rf"\b{re.escape(name_clean)}\s+is\s+(?:the\s+|a\s+|an\s+)?([^,\.\;\n\"“”]{{3,65}}?)(?:,|\s+who\b|\s+and\b|\.|$)",
            scene_narrative,
            flags=re.IGNORECASE
        )
        if m_cop:
            cand_cop = m_cop.group(1).strip(" ,.-")
            if cand_cop and any(k in cand_cop.lower() for k in ("president", "captain", "leader", "treasurer", "secretary", "prefect", "council", "club", "committee", "student", "rep", "member", "commander", "chief", "officer", "director")):
                extracted_role_phrases.append(cand_cop)
                if "role" not in out and len(cand_cop.split()) <= 7:
                    out["role"] = cand_cop[0].upper() + cand_cop[1:]

        # 4. Extract a clean narrative description from the introductory sentence(s) if missing
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', scene_narrative) if s.strip()]
        for idx, sent in enumerate(sentences):
            if sent.startswith(('"', '“', "'")):
                continue
            s_low = sent.lower()
            name_low = name_clean.lower()
            if name_low in s_low:
                # Guard against stealing sentences where this entity is merely an object of perception/action
                # (e.g. "Artemiusz steps past... spotting a cluster of students near the window seats")
                is_object_of_action = any(
                    re.search(rf"\b{verb}\s+(?:[a-z0-9_\-]+\s+){{0,3}}{re.escape(name_low)}\b", s_low)
                    for verb in (
                        "spotting", "spotted", "noticing", "noticed", "seeing", "sees", "saw",
                        "greeting", "greeted", "greets", "approaching", "approached", "approaches",
                        "looking at", "looks at", "looked at", "glancing at", "glances at", "glanced at",
                        "cluster of", "group of", "crowd of", "walks toward", "walked toward",
                        "talking to", "talks to", "talked to", "speaking with", "speaks with", "spoke with",
                        "asking", "asks", "asked", "telling", "tells", "told"
                    )
                )
                if is_object_of_action:
                    continue
                # If another named entity/subject is performing an action on this character, skip
                if not sent.lower().startswith(name_low) and re.match(r"^[A-Z][a-z]+\s+[a-z]+(?:s|ed|ing)\b", sent):
                    continue
                # Also ensure the sentence actually centers on the character,
                # rather than starting with a third-person pronoun (He/She) referring to a prior actor
                if re.match(r"^(He|She|They)\b", sent) and not sent.lower().startswith(name_low):
                    continue
                desc_parts = [sent]
                if idx + 1 < len(sentences):
                    next_s = sentences[idx + 1]
                    if not next_s.startswith(('"', '“', "'")) and re.match(r"^(She|He|They)\s+(is|are|has|have|wears|carries|stands|commands|exudes)\b", next_s):
                        desc_parts.append(next_s)
                cand_desc = " ".join(desc_parts).strip()
                if len(cand_desc) > 220:
                    cand_desc = sent[:220].strip()
                if cand_desc:
                    out["description"] = cand_desc
                break

    combined_text = " | ".join(extracted_role_phrases)
    if not combined_text:
        return out

    is_school = "school" in (scenario or "").lower() or "academy" in combined_text.lower()

    # Pattern A: "<Organization> <Position>" (e.g., "Student Council President", "Kendo Club Captain")
    m_org_pos = re.search(
        rf"\b([A-Z][A-Za-z0-9\'\-]*(?:\s+(?!Vice\b|Co\b)[A-Z&][A-Za-z0-9\'\-]*){{0,4}})\s+({_POSITION_TITLES_PATTERN})\b",
        combined_text
    )
    if m_org_pos:
        org_clean = _clean_org_name(m_org_pos.group(1))
        pos_clean = m_org_pos.group(2).strip()
        if org_clean:
            full_title = f"{org_clean} {pos_clean}".strip()
            out["role"] = full_title
            out["faction"] = org_clean
            out["club_role"] = pos_clean
            if is_school or any(w in org_clean.lower() for w in ("council", "club", "committee", "team", "squad", "society", "union", "band", "choir")):
                out["club"] = org_clean

    # Pattern B: "<Position> of (the) <Organization>" (e.g., "President of the Student Council")
    if "faction" not in out:
        m_pos_org = re.search(
            rf"\b({_POSITION_TITLES_PATTERN})\s+of\s+(?:the\s+)?([A-Z][A-Za-z0-9\'\-]*(?:\s+[A-Z&][A-Za-z0-9\'\-]*){{0,4}})\b",
            combined_text,
            flags=re.IGNORECASE
        )
        if m_pos_org:
            pos_clean = m_pos_org.group(1).strip()
            pos_clean = " ".join(w.capitalize() for w in pos_clean.split())
            org_clean = _clean_org_name(m_pos_org.group(2))
            if org_clean:
                out["role"] = f"{org_clean} {pos_clean}".strip()
                out["faction"] = org_clean
                out["club_role"] = pos_clean
                if is_school or any(w in org_clean.lower() for w in ("council", "club", "committee", "team", "squad", "society", "union", "band", "choir")):
                    out["club"] = org_clean

    # Pattern C: Explicit Organization / Club mention even without a leadership rank
    if "faction" not in out:
        m_org_only = re.search(
            r"\b([A-Z][A-Za-z0-9\'\-]*(?:\s+[A-Z&][A-Za-z0-9\'\-]*){0,3}\s+(?:Council|Club|Committee|Team|Squad|Society|Union|Guild|Order|Syndicate|Faction))\b",
            combined_text
        )
        if m_org_only:
            org_clean = _clean_org_name(m_org_only.group(1))
            if org_clean:
                out["faction"] = org_clean
                if is_school or any(w in org_clean.lower() for w in ("council", "club", "committee", "team", "squad", "society", "union")):
                    out["club"] = org_clean

    # Grade / Standing extraction
    m_grade = re.search(r"\b(Freshman|Sophomore|Junior|Senior)\b", combined_text, flags=re.IGNORECASE)
    if m_grade:
        out["grade"] = m_grade.group(1).capitalize()
    else:
        m_year = re.search(r"\b(1st|2nd|3rd|First|Second|Third)[\s\-]+Year\b", combined_text, flags=re.IGNORECASE)
        if m_year:
            yr_tok = m_year.group(1).lower()
            if yr_tok in ("1st", "first"):
                out["grade"] = "Freshman"
            elif yr_tok in ("2nd", "second"):
                out["grade"] = "Sophomore"
            elif yr_tok in ("3rd", "third"):
                out["grade"] = "Senior"

    if is_school and "grade" not in out:
        c_role = out.get("club_role", "")
        if c_role in ("President", "Captain", "Commander", "Head", "Chairman", "Chairwoman", "Leader", "Founder"):
            out["grade"] = "Senior"
        elif c_role in ("Vice President", "Vice-President", "Co-Captain", "Vice-Captain", "Treasurer", "Secretary"):
            out["grade"] = "Junior"

    return out


def _enrich_contact_basic_info(
    conn,
    session_id: int,
    name: str,
    basic_info: dict | None,
    scenario: str = "",
    narrative_text: str = ""
) -> dict:
    """Hydrates missing contact basic_info fields (role, faction, club, club_role, grade,
    clique, description, mannerisms, motivation) by cross-referencing school_directory,
    factions, lorebook, and session narrative text.
    """
    info = _merge_basic_info_safely({}, basic_info)
    name_clean = (name or "").strip()
    if not session_id or not name_clean:
        return info

    npc_slug = name_clean.lower().replace(" ", "_")
    name_low = name_clean.lower()

    # 1. Cross-reference school_directory
    try:
        sd_row = conn.execute(
            """SELECT role, grade, club, clique, primary_facility, secondary_facility, personality_summary, race
               FROM school_directory
               WHERE session_id=? AND (lower(name)=? OR npc_id=?)
               LIMIT 1""",
            (session_id, name_low, npc_slug)
        ).fetchone()
        if not sd_row and " " not in name_clean:
            cand_rows = conn.execute(
                """SELECT role, grade, club, clique, primary_facility, secondary_facility, personality_summary, race
                   FROM school_directory
                   WHERE session_id=? AND (lower(name) LIKE ? OR lower(name) LIKE ? OR npc_id LIKE ? OR npc_id LIKE ?)
                   LIMIT 2""",
                (session_id, f"{name_low} %", f"% {name_low}", f"{npc_slug}_%", f"%_{npc_slug}")
            ).fetchall()
            if len(cand_rows) == 1:
                sd_row = cand_rows[0]
        if sd_row:
            if _is_empty_info_val(info.get("role")) and not _is_empty_info_val(sd_row["role"]):
                info["role"] = sd_row["role"].strip()
            if _is_empty_info_val(info.get("grade")) and not _is_empty_info_val(sd_row["grade"]):
                info["grade"] = sd_row["grade"].strip()
            if not _is_empty_info_val(sd_row["club"]):
                club_val = sd_row["club"].strip()
                if _is_empty_info_val(info.get("club")):
                    info["club"] = club_val
                if _is_empty_info_val(info.get("faction")):
                    info["faction"] = club_val
            if _is_empty_info_val(info.get("clique")) and not _is_empty_info_val(sd_row["clique"]):
                info["clique"] = sd_row["clique"].strip()
            if _is_empty_info_val(info.get("primary_facility")) and not _is_empty_info_val(sd_row["primary_facility"]):
                info["primary_facility"] = sd_row["primary_facility"].strip()
            if _is_empty_info_val(info.get("secondary_facility")) and not _is_empty_info_val(sd_row["secondary_facility"]):
                info["secondary_facility"] = sd_row["secondary_facility"].strip()
            if _is_empty_info_val(info.get("description")) and not _is_empty_info_val(sd_row["personality_summary"]):
                info["description"] = sd_row["personality_summary"].strip()
            if _is_empty_info_val(info.get("race")) and not _is_empty_info_val(sd_row["race"]):
                info["race"] = sd_row["race"].strip()
    except Exception:
        pass

    # 2. Cross-reference factions leadership_roster_json
    try:
        fac_rows = conn.execute(
            "SELECT name, leadership_roster_json FROM factions WHERE session_id=?",
            (session_id,)
        ).fetchall()
        for fr in fac_rows:
            fac_name = (fr["name"] or "").strip()
            roster = json.loads(fr["leadership_roster_json"] or "[]")
            if not isinstance(roster, list):
                continue
            for member in roster:
                if not isinstance(member, dict):
                    continue
                m_name = str(member.get("name") or "").strip()
                if m_name and m_name.lower() == name_low:
                    m_title = str(member.get("title") or "").strip()
                    m_desc = str(member.get("description") or "").strip()
                    if fac_name and _is_empty_info_val(info.get("faction")):
                        info["faction"] = fac_name
                    if fac_name and _is_empty_info_val(info.get("club")) and (
                        "school" in (scenario or "").lower()
                        or any(w in fac_name.lower() for w in ("council", "club", "committee", "team", "squad", "society", "union"))
                    ):
                        info["club"] = fac_name
                    if m_title and _is_empty_info_val(info.get("club_role")):
                        info["club_role"] = m_title
                    if m_title and _is_empty_info_val(info.get("role")):
                        if fac_name and fac_name.lower() not in m_title.lower():
                            info["role"] = f"{fac_name} {m_title}".strip()
                        else:
                            info["role"] = m_title
                    if m_desc and _is_empty_info_val(info.get("description")):
                        info["description"] = m_desc
                    break
    except Exception:
        pass

    # 3. Cross-reference lorebook
    lb_row = None
    try:
        lb_row = conn.execute(
            """SELECT id, description, faction, motivation, mannerisms, race
               FROM lorebook
               WHERE session_id=? AND lower(name)=? AND lower(entity_type) IN ('person', 'npc', 'character')
               LIMIT 1""",
            (session_id, name_low)
        ).fetchone()
        if lb_row:
            if _is_empty_info_val(info.get("description")) and not _is_empty_info_val(lb_row["description"]):
                info["description"] = lb_row["description"].strip()
            if _is_empty_info_val(info.get("faction")) and not _is_empty_info_val(lb_row["faction"]):
                info["faction"] = lb_row["faction"].strip()
            if _is_empty_info_val(info.get("motivation")) and not _is_empty_info_val(lb_row["motivation"]):
                info["motivation"] = lb_row["motivation"].strip()
            if _is_empty_info_val(info.get("mannerisms")) and not _is_empty_info_val(lb_row["mannerisms"]):
                info["mannerisms"] = lb_row["mannerisms"].strip()
            if _is_empty_info_val(info.get("race")) and lb_row["race"] and str(lb_row["race"]).strip().lower() not in ("", "unknown"):
                info["race"] = lb_row["race"].strip()
    except Exception:
        pass

    # 4. Extract role/affiliation/grade/description from existing fields & session narrative
    needs_narrative = (
        _is_empty_info_val(info.get("role"))
        or _is_empty_info_val(info.get("faction"))
        or _is_empty_info_val(info.get("description"))
        or _is_empty_info_val(info.get("race"))
        or ("school" in (scenario or "").lower() and _is_empty_info_val(info.get("grade")))
    )
    scene_narr = narrative_text or ""
    if needs_narrative and not scene_narr:
        try:
            s_row = conn.execute("SELECT narrative, scenario FROM sessions WHERE id=?", (session_id,)).fetchone()
            if s_row:
                scene_narr = s_row["narrative"] or ""
                if not scenario and s_row["scenario"]:
                    scenario = s_row["scenario"]
        except Exception:
            pass

    char_blob = " | ".join(
        str(info.get(k)) for k in ("role", "occupation", "description", "faction", "club", "race")
        if not _is_empty_info_val(info.get(k))
    )
    inferred = _extract_role_and_affiliation_from_text(
        name=name_clean,
        char_text=char_blob,
        scene_narrative=scene_narr,
        scenario=scenario
    )
    if inferred:
        info = _merge_basic_info_safely(inferred, info)

    # 4b. Extract race from character text and narrative if still missing
    if _is_empty_info_val(info.get("race")):
        from mechanics.social.races import extract_race_from_text
        inferred_race = extract_race_from_text(
            text=f"{char_blob} | {scene_narr}",
            scen_key=scenario,
            name=name_clean
        )
        if inferred_race:
            info["race"] = inferred_race

    # 4c. Tight Role & Faction coupling:
    # If affiliated, ensure a role (e.g. club_role or Member). If unaffiliated, role is None.
    has_faction = not _is_empty_info_val(info.get("faction")) or not _is_empty_info_val(info.get("club"))
    if has_faction:
        if _is_empty_info_val(info.get("role")) or str(info.get("role")).strip().lower() in ("none", "unaffiliated", "unknown"):
            info["role"] = info.get("club_role") or "Member"
    else:
        if str(info.get("role", "")).strip().lower() in ("none", "unaffiliated", "member", ""):
            info["role"] = "None"

    # 4d. Student Character Grade and Club Hydration (High School / Academy Scenarios):
    is_school = "school" in (scenario or "").lower() or "academy" in (scenario or "").lower()
    if is_school:
        role_lower = str(info.get("role") or "").lower()
        faculty_keywords = (
            "teacher", "faculty", "professor", "instructor", "principal", "vice-principal",
            "headmaster", "dean", "counselor", "nurse", "librarian", "custodian", "janitor",
            "coach", "athletic director", "advisor", "parent", "father", "mother", "detective", "police", "officer", "vendor"
        )
        grade_lower = str(info.get("grade") or "").strip().lower()
        is_faculty_or_adult = (
            any(kw in role_lower for kw in faculty_keywords)
            or grade_lower in ("faculty", "adult")
            or bool(info.get("is_adult_family"))
        )

        if not is_faculty_or_adult:
            # 1. Apply Grade if missing:
            # Seed pseudo-random generator stably based on character name and session
            # so each newly generated character gets a varied grade (Freshman/Sophomore/Junior/Senior)
            # but it NEVER changes arbitrarily on future turns or reconciliations.
            if _is_empty_info_val(info.get("grade")):
                h_val = int(hashlib.md5(f"grade_{session_id}_{name_clean.lower()}".encode("utf-8")).hexdigest()[:8], 16)
                grade_rng = random.Random(h_val)
                assigned_grade = grade_rng.choice(["Freshman", "Sophomore", "Junior", "Senior"])
                info["grade"] = assigned_grade

            # 2. Club membership: ensure ~75% of students are part of a club
            # (either from pre-generated session club factions or newly generated ambient clubs)
            curr_club = info.get("club") or info.get("faction")
            if _is_empty_info_val(curr_club) or str(curr_club).strip().lower() in ("none", "unaffiliated", "unknown", ""):
                c_val = int(hashlib.md5(f"club_{session_id}_{name_clean.lower()}".encode("utf-8")).hexdigest()[:8], 16)
                club_rng = random.Random(c_val)
                # 75% rate
                if club_rng.random() < 0.75:
                    try:
                        fac_rows = conn.execute(
                            "SELECT name FROM factions WHERE session_id=?",
                            (session_id,)
                        ).fetchall()
                        candidate_factions = [
                            fr["name"].strip() for fr in fac_rows
                            if fr["name"] and not any(kw in fr["name"].lower() for kw in ("faculty", "staff", "board", "administration"))
                        ]
                    except Exception:
                        candidate_factions = []

                    ambient_clubs = [
                        "Science & Robotics Club", "Fine Arts Guild", "Athletic Directorate",
                        "Drama Club", "Occult & Mystery Club", "Photography Club", "Kendo Club",
                        "Tea Ceremony Club", "Literary Society", "Broadcasting Club", "Astronomy Club",
                        "Cooking & Culinary Arts Club", "Gaming & Esports Club", "Light Music Club"
                    ]

                    # 70% chance to join an existing session faction if available, 30% for ambient club
                    if candidate_factions and club_rng.random() < 0.70:
                        chosen_club = club_rng.choice(candidate_factions)
                    else:
                        chosen_club = club_rng.choice(ambient_clubs)

                    info["club"] = chosen_club
                    info["faction"] = chosen_club

                    char_grade = info.get("grade", "Freshman")
                    if char_grade in ("Junior", "Senior") and club_rng.random() < 0.25:
                        chosen_role = club_rng.choice([
                            "Club Vice President", "Club Secretary", "Club Treasurer", "Club Officer", "Events Coordinator"
                        ])
                    else:
                        chosen_role = "Club Member"

                    info["club_role"] = chosen_role
                    info["role"] = chosen_role
    else:
        # Other genres (Fantasy, Sci-Fi, Cyberpunk, etc.):
        # Ensure standing matches the faction's established hierarchy if affiliated
        has_fac = not _is_empty_info_val(info.get("faction")) or not _is_empty_info_val(info.get("club"))
        if has_fac:
            if _is_empty_info_val(info.get("standing")):
                cur_role = info.get("role") or info.get("club_role") or "Member"
                if cur_role.lower() not in ("none", "unaffiliated", "unknown", ""):
                    info["standing"] = cur_role
                else:
                    info["standing"] = "Member"

    # 5. Backfill lorebook if lorebook row exists with empty description/faction
    if lb_row and (not _is_empty_info_val(info.get("description")) or not _is_empty_info_val(info.get("faction"))):
        try:
            lb_desc = info.get("description") or lb_row["description"] or ""
            lb_fac = info.get("faction") or info.get("club") or lb_row["faction"] or ""
            if (lb_desc and _is_empty_info_val(lb_row["description"])) or (lb_fac and _is_empty_info_val(lb_row["faction"])):
                conn.execute(
                    "UPDATE lorebook SET description=COALESCE(NULLIF(?, ''), description), faction=COALESCE(NULLIF(?, ''), faction) WHERE id=?",
                    (lb_desc, lb_fac, lb_row["id"])
                )
        except Exception:
            pass

    return info


def upsert_contact(session_id: int, npc_id: str, name: str, character_id: int = 0,
                   basic_info: dict = None, delta_score: int = 0, track: str = None,
                   new_traits: list = None, new_preferences: list = None, race: str = "", gender: str = "", appearance: dict = None,
                   new_memory: str = None, new_general_memory: str = None, narrative_text: str = "",
                   open_thread: str = "", emotional_tone: str = "", intimate_profile: dict = None,
                   household_role: str | None = None) -> dict:
    import mechanics.social.persona as persona
    import namegen

    if isinstance(npc_id, (int, float)) and isinstance(character_id, str):
        character_id, npc_id, name = int(npc_id), str(name or ""), character_id
    elif isinstance(npc_id, (int, float)):
        npc_id = str(npc_id)

    # Reject invalid / corrupted entity names from LLM reasoning leaks or collective groups
    if not namegen.is_valid_entity_name(name) and not namegen.is_valid_entity_name(npc_id) and \
       not namegen.is_generic_role_name(name) and not namegen.is_generic_role_name(npc_id):
        return {}
    if namegen.is_collective_entity_name(name) or namegen.is_collective_entity_name(npc_id):
        return {}

    # Code-level guarantee: named characters/contacts must have a proper personal name
    raw_identifier = name or npc_id or ""
    if namegen.is_generic_role_name(name) or namegen.is_generic_role_name(npc_id) or \
       not namegen.is_valid_entity_name(name) or not namegen.is_valid_entity_name(npc_id):
        role_title = str(name if (namegen.is_generic_role_name(name) or not namegen.is_valid_entity_name(name)) else npc_id)
        matched_name = None
        with get_conn() as conn:
            fac_rows = conn.execute("SELECT leadership_roster_json FROM factions WHERE session_id=?", (session_id,)).fetchall()
            for fr in fac_rows:
                try:
                    r_list = json.loads(fr["leadership_roster_json"] or "[]")
                    for r in r_list:
                        if r.get("title", "").lower() == role_title.lower() or role_title.lower() in r.get("title", "").lower():
                            matched_name = r.get("name")
                            break
                except Exception:
                    pass
                if matched_name:
                    break

        if not matched_name:
            # Ambient generic roles (e.g. "Town Guard", "Merchant", "Villager") without explicit faction leadership cannot be contacts
            return {}

        clean_name = matched_name
        if basic_info is None or not isinstance(basic_info, dict):
            basic_info = {}
        basic_info["role"] = role_title
        if role_title.lower() not in basic_info.get("description", "").lower():
            basic_info["description"] = f"{role_title} — {basic_info.get('description', '')}".strip(" —")

        name = clean_name
        npc_id = clean_name.lower().replace(" ", "_")
    else:
        npc_id = (npc_id or name or "").strip().lower().replace(" ", "_")
        name = (name or "").strip()

    if not npc_id or not name:
        return {}

    sess = db.get_session(session_id)
    scen = sess.get("scenario", "fantasy") if sess else "fantasy"
    import mechanics.social.relationships as relationships
    n_role = (basic_info.get("role") if isinstance(basic_info, dict) else "") or ""
    n_desc = (basic_info.get("description") if isinstance(basic_info, dict) else "") or ""
    is_promoted_adult_family = (
        str(household_role or "").strip().lower() in ("father", "mother")
        or bool(isinstance(basic_info, dict) and basic_info.get("is_adult_family"))
    )
    if not is_promoted_adult_family and not relationships.is_contact_eligible(name=name, role=n_role, description=n_desc, scenario=scen, session_id=session_id):
        return {}

    now = time.time()
    if hasattr(appearance, "model_dump"):
        appearance = appearance.model_dump(exclude_none=True)
    app_json = json.dumps(appearance) if isinstance(appearance, dict) else (appearance or "{}")

    # Clean basic info description if present
    if basic_info and isinstance(basic_info, dict):
        basic_info = dict(basic_info)
        if basic_info.get("description"):
            basic_info["description"] = persona.sanitize_npc_description(basic_info["description"], appearance if isinstance(appearance, dict) else None)

    with get_conn() as conn:
        if character_id:
            existing = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? AND (character_id=? OR character_id=0) AND (npc_id=? OR lower(name)=?)",
                (session_id, character_id, npc_id, name.lower())).fetchone()
            if not existing:
                existing = conn.execute(
                    """SELECT * FROM contacts WHERE session_id=? AND (character_id=? OR character_id=0)
                       AND (npc_id LIKE ? OR lower(name) LIKE ? OR ? LIKE (lower(name) || '%'))
                       ORDER BY id ASC LIMIT 1""",
                    (session_id, character_id, f"{npc_id}_%", f"{name.lower()} %", name.lower())).fetchone()
        else:
            existing = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? AND (npc_id=? OR lower(name)=?)",
                (session_id, npc_id, name.lower())).fetchone()
            if not existing:
                existing = conn.execute(
                    """SELECT * FROM contacts WHERE session_id=?
                       AND (npc_id LIKE ? OR lower(name) LIKE ? OR ? LIKE (lower(name) || '%'))
                       ORDER BY id ASC LIMIT 1""",
                    (session_id, f"{npc_id}_%", f"{name.lower()} %", name.lower())).fetchone()

        if existing:
            final_name = existing["name"] if (len(existing["name"].split()) > len(name.split()) and name.lower() in existing["name"].lower()) else name
            final_npc_id = existing["npc_id"]
            existing_dict = dict(existing)
            existing_gender = existing_dict.get("gender")
            if existing_gender and str(existing_gender).strip().lower() not in ("", "unknown"):
                cur_gender = existing_gender
            else:
                cur_gender = gender if gender else ""
            current_score = relationships.clamp_score(existing["relationship_score"] + delta_score)

            raw_cur_info = json.loads(existing["basic_info_json"] or "{}")
            cur_info = _merge_basic_info_safely(raw_cur_info, basic_info)
            if current_score >= 100:
                cur_info["unlocked_via_friendship"] = True
            if race and not _is_empty_info_val(race):
                cur_info["race"] = race
            cur_info = _enrich_contact_basic_info(
                conn, session_id, final_name, cur_info,
                scenario=scen, narrative_text=narrative_text
            )

            existing_dict = dict(existing)
            existing_race = existing_dict.get("race")
            from mechanics.social.races import extract_race_from_text, normalize_race
            inferred_race = race or cur_info.get("race") or extract_race_from_text(narrative_text, scen_key=scen, name=final_name)
            
            # 1. Prefer explicitly known non-empty, non-human existing race
            if existing_race and str(existing_race).strip().lower() not in ("", "unknown", "human"):
                cur_race = existing_race
            # 2. Next, prefer inferred/passed specific non-human race (upgrading if existing was placeholder human)
            elif inferred_race and str(inferred_race).strip().lower() not in ("", "unknown", "human"):
                cur_race = normalize_race(inferred_race, scen_key=scen, seed=final_name)
            # 3. If existing is confirmed human, keep it
            elif existing_race and str(existing_race).strip().lower() not in ("", "unknown"):
                cur_race = existing_race
            # 4. If inferred is explicitly human
            elif inferred_race and str(inferred_race).strip().lower() not in ("", "unknown"):
                cur_race = normalize_race(inferred_race, scen_key=scen, seed=final_name)
            # 5. Otherwise, fallback to empty to avoid locking default "human" (unless random beastfolk was assigned)
            else:
                fallback_race = normalize_race("", scen_key=scen, seed=final_name)
                cur_race = fallback_race if fallback_race != "human" else ""

            cur_raw_traits = json.loads(existing_dict.get("unlocked_traits_json") or "[]")
            cur_raw_prefs = json.loads(existing_dict.get("preferences_json") or "[]")
            cur_memories = json.loads(existing_dict.get("intimate_memories_json") or "[]")
            if not isinstance(cur_memories, list):
                cur_memories = []
            cur_recent_memories = json.loads(existing_dict.get("rel_history_json") or "[]")
            if not isinstance(cur_recent_memories, list):
                cur_recent_memories = []

            if existing_dict.get("appearance_json"):
                try:
                    old_app = json.loads(existing_dict.get("appearance_json") or "{}")
                    if isinstance(old_app.get("intimate_memories"), list):
                        for m in old_app["intimate_memories"]:
                            m_str = str(m).strip() if m else ""
                            if m_str and m_str not in cur_memories:
                                cur_memories.append(m_str)
                    if isinstance(old_app.get("recent_memories"), list):
                        for rm in old_app["recent_memories"]:
                            rm_str = str(rm).strip() if rm else ""
                            if rm_str and rm_str not in cur_recent_memories:
                                cur_recent_memories.append(rm_str)
                except Exception:
                    pass

            if appearance and isinstance(appearance, dict):
                if isinstance(appearance.get("intimate_memories"), list):
                    for m in appearance["intimate_memories"]:
                        m_str = str(m).strip() if m else ""
                        if m_str and m_str not in cur_memories:
                            cur_memories.append(m_str)
                if isinstance(appearance.get("recent_memories"), list):
                    for rm in appearance["recent_memories"]:
                        rm_str = str(rm).strip() if rm else ""
                        if rm_str and rm_str not in cur_recent_memories:
                            cur_recent_memories.append(rm_str)

            # Ensure any non-romantic memories are also present in cur_recent_memories
            from mechanics.social.persona import is_romantic_milestone_str
            for m in cur_memories:
                m_str = str(m).strip() if m else ""
                if not m_str or m_str.startswith("Past History:") or is_romantic_milestone_str(m_str):
                    continue
                if m_str not in cur_recent_memories:
                    cur_recent_memories.append(m_str)

            merged_traits_in = cur_raw_traits + (new_traits or [])
            merged_prefs_in = cur_raw_prefs + (new_preferences or [])
            clean_traits, clean_prefs = persona.split_traits_and_preferences(
                merged_traits_in,
                merged_prefs_in,
                role=cur_info.get("role", ""),
                race=cur_race,
                seed_str=f"{final_name}_{cur_info.get('description', '')}"
            )
            
            pending_past_history_str = None
            if new_memory and isinstance(new_memory, str) and new_memory.strip():
                m_str = new_memory.strip()
                if m_str.startswith("Past History:") or is_romantic_milestone_str(m_str):
                    if m_str not in cur_memories:
                        cur_memories.append(m_str)
                        if len(cur_memories) > 100:
                            cur_memories = cur_memories[-100:]
                    if m_str.startswith("Past History:"):
                        pending_past_history_str = m_str
                else:
                    if m_str not in cur_recent_memories:
                        cur_recent_memories.append(m_str)
                        if len(cur_recent_memories) > 50:
                            cur_recent_memories = cur_recent_memories[-50:]

            if new_general_memory and isinstance(new_general_memory, str) and new_general_memory.strip():
                gm_str = new_general_memory.strip()
                if gm_str not in cur_recent_memories:
                    cur_recent_memories.append(gm_str)
                    if len(cur_recent_memories) > 50:
                        cur_recent_memories = cur_recent_memories[-50:]

            existing_track = existing_dict.get("track") or "platonic"
            if track is not None and str(track).strip():
                cur_track = str(track).strip().lower()
            else:
                cur_track = existing_track

            existing_gender = existing_dict.get("gender")
            if existing_gender and str(existing_gender).strip().lower() not in ("", "unknown"):
                cur_gender = existing_gender
            else:
                cur_gender = gender if gender else ""

            cur_app = json.loads(existing_dict.get("appearance_json") or "{}")
            try:
                _prev_prof = json.loads(existing_dict.get("intimate_profile_json") or "{}")
                if isinstance(_prev_prof, dict):
                    if _prev_prof.get("predetermined_intercourse") and not cur_app.get("predetermined_intercourse"):
                        cur_app["predetermined_intercourse"] = _prev_prof["predetermined_intercourse"]
                    if _prev_prof.get("had_first_time_with_player") and not cur_app.get("had_first_time_with_player"):
                        cur_app["had_first_time_with_player"] = _prev_prof["had_first_time_with_player"]
                    tracks = _prev_prof.get("tracks") or {}
                    for trk_name in ("intercourse", "oral", "manual", "anal"):
                        exp_key = f"{trk_name}_experience"
                        if tracks.get(trk_name) and not cur_app.get(exp_key):
                            cur_app[exp_key] = tracks[trk_name]
            except Exception:
                pass
            from mechanics.social.persona.intimacy.appearance import extract_appearance_from_text
            extracted_app = extract_appearance_from_text(f"{cur_info.get('description', '')} {narrative_text}", name=final_name)
            if extracted_app:
                cur_app = persona.merge_appearance_safely(cur_app, extracted_app)

            cur_app["intimate_memories"] = list(cur_memories)
            cur_app["recent_memories"] = list(cur_recent_memories)
            cur_app["rel_history"] = list(cur_recent_memories)
            if appearance and isinstance(appearance, dict):
                cur_app = persona.merge_appearance_safely(cur_app, appearance)
            cur_app["intimate_memories"] = list(cur_memories)
            cur_app["recent_memories"] = list(cur_recent_memories)
            cur_app["rel_history"] = list(cur_recent_memories)
            cur_app = persona.enforce_intimacy_safeguard_invariants(cur_app)

            if not cur_gender:
                try:
                    cur_gender = persona.infer_contact_gender({"name": final_name, "basic_info": cur_info, "appearance": cur_app}) or ""
                except Exception:
                    pass

            if pending_past_history_str:
                try:
                    from mechanics.social.persona.intimacy.ledger import parse_past_history_entry_to_events, record_intimate_event
                    for pev in parse_past_history_entry_to_events(pending_past_history_str, char_gender=cur_gender):
                        record_intimate_event(
                            session_id=session_id,
                            character_id=final_npc_id,
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
                            narrative_summary=pending_past_history_str,
                            character_gender=cur_gender,
                            conn=conn
                        )
                except Exception:
                    pass

            cur_open_thread = open_thread or existing_dict.get("open_thread", "")
            cur_emotional_tone = emotional_tone or existing_dict.get("emotional_tone", "")
            cur_hh_id = existing_dict.get("household_id")
            cur_hh_role = str(household_role or existing_dict.get("household_role") or "child").strip().lower()

            fresh_prof_row = conn.execute("SELECT intimate_profile_json FROM contacts WHERE id=?", (existing["id"],)).fetchone()
            try:
                cur_prof = json.loads((fresh_prof_row["intimate_profile_json"] if fresh_prof_row else existing_dict.get("intimate_profile_json")) or "{}")
            except Exception:
                cur_prof = {}
            if intimate_profile and isinstance(intimate_profile, dict):
                for ip_k, ip_v in intimate_profile.items():
                    if ip_k == "disclosure_flags" and isinstance(ip_v, dict):
                        cur_prof.setdefault("disclosure_flags", {}).update(ip_v)
                    elif ip_k == "tracks" and isinstance(ip_v, dict):
                        cur_prof.setdefault("tracks", {}).update(ip_v)
                    else:
                        cur_prof[ip_k] = ip_v

            # Move any intimate keys that arrived in cur_app into cur_prof
            _intimate_keys = (
                "sensitive_spots", "turn_ons", "turn_offs", "fetishes", "desires_and_kinks",
                "act_likes", "act_dislikes", "intimate_demeanor", "intimate_dynamic", "erotic_openness",
                "undergarments", "bra", "underwear", "predetermined_intercourse", "had_first_time_with_player"
            )
            for k in _intimate_keys:
                if k in cur_app and k not in cur_prof:
                    cur_prof[k] = cur_app[k]
                elif k == "had_first_time_with_player" and cur_app.get(k):
                    cur_prof[k] = cur_app[k]
                cur_app.pop(k, None)

            if "tracks" not in cur_prof or not isinstance(cur_prof["tracks"], dict):
                cur_prof["tracks"] = {}

            from mechanics.social.persona.intimacy.logic import (
                merge_intercourse_states,
                merge_oral_states,
                merge_manual_states,
                merge_anal_states
            )
            from mechanics.social.persona.intimacy.ledger import normalize_gender

            in_intercourse = cur_app.get("intercourse_experience") or (intimate_profile.get("tracks", {}).get("intercourse") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_intercourse and in_intercourse not in ("", "unknown"):
                cur_prof["tracks"]["intercourse"] = merge_intercourse_states(cur_prof["tracks"].get("intercourse", "virgin"), in_intercourse)

            in_oral = cur_app.get("oral_experience") or (intimate_profile.get("tracks", {}).get("oral") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_oral and in_oral not in ("", "unknown"):
                cur_prof["tracks"]["oral"] = merge_oral_states(cur_prof["tracks"].get("oral", "inexperienced"), in_oral)

            in_manual = cur_app.get("manual_experience") or (intimate_profile.get("tracks", {}).get("manual") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_manual and in_manual not in ("", "unknown"):
                cur_prof["tracks"]["manual"] = merge_manual_states(cur_prof["tracks"].get("manual", "inexperienced"), in_manual)

            in_anal = cur_app.get("anal_experience") or (intimate_profile.get("tracks", {}).get("anal") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_anal and in_anal not in ("", "unknown"):
                merged_a = merge_anal_states(cur_prof["tracks"].get("anal", "inexperienced"), in_anal)
                if normalize_gender(cur_gender) == "female" and merged_a in ("has_done_anal", "has_done_and_received_anal"):
                    merged_a = "has_received_anal"
                cur_prof["tracks"]["anal"] = merged_a

            cur_prof["tracks"].setdefault("intercourse", "virgin")
            cur_prof["tracks"].setdefault("oral", "inexperienced")
            cur_prof["tracks"].setdefault("manual", "inexperienced")
            cur_prof["tracks"].setdefault("anal", "inexperienced")

            # Deterministically seed named backstory partners once if non-baseline tracks exist with empty past_history
            from mechanics.social.persona.intimacy.ledger import get_intimate_events, compute_intimate_tracks_from_ledger
            existing_evs = get_intimate_events(session_id, final_npc_id, origin="past_history", conn=conn)
            has_non_baseline = any(
                cur_prof["tracks"].get(act) not in ("virgin", "inexperienced", "unknown", "", None)
                for act in ("intercourse", "oral", "manual", "anal")
            )
            if has_non_baseline and not existing_evs and not cur_prof.get("had_first_time_with_player"):
                from mechanics.social.persona.intimacy.generation import generate_past_intimate_history, persist_generated_past_history
                h_seed = int(hashlib.md5(f"{final_name}_{cur_race or 'human'}_{session_id}".encode("utf-8")).hexdigest(), 16)
                past_hist = generate_past_intimate_history(
                    hash_val=h_seed,
                    race=cur_race or "human",
                    gender=cur_gender or "female",
                    scenario=scen,
                    openness=str(cur_prof.get("erotic_openness") or "moderate"),
                    intercourse=cur_prof["tracks"].get("intercourse", "virgin"),
                    oral=cur_prof["tracks"].get("oral", "inexperienced"),
                    manual=cur_prof["tracks"].get("manual", "inexperienced"),
                    anal=cur_prof["tracks"].get("anal", "inexperienced"),
                )
                if past_hist:
                    persist_generated_past_history(
                        session_id=session_id,
                        character_id=final_npc_id,
                        history_dict=past_hist,
                        character_gender=cur_gender,
                        conn=conn
                    )
                    for ph_entry in (past_hist.get("entries") or []):
                        if ph_entry and ph_entry not in cur_memories:
                            cur_memories.append(ph_entry)

            # Deterministically synchronize from intimate_events ledger
            char_events = get_intimate_events(session_id, final_npc_id, physical_only=True, conn=conn)
            if char_events:
                ledger_tracks = compute_intimate_tracks_from_ledger(char_events)
                cur_prof["tracks"]["intercourse"] = merge_intercourse_states(
                    cur_prof["tracks"].get("intercourse", "virgin"),
                    ledger_tracks.get("intercourse", "virgin"),
                )
                cur_prof["tracks"]["oral"] = merge_oral_states(
                    cur_prof["tracks"].get("oral", "inexperienced"),
                    ledger_tracks.get("oral", "inexperienced"),
                )
                cur_prof["tracks"]["manual"] = merge_manual_states(
                    cur_prof["tracks"].get("manual", "inexperienced"),
                    ledger_tracks.get("manual", "inexperienced"),
                )
                merged_ledger_anal = merge_anal_states(
                    cur_prof["tracks"].get("anal", "inexperienced"),
                    ledger_tracks.get("anal", "inexperienced"),
                )
                if normalize_gender(cur_gender) == "female" and merged_ledger_anal in ("has_done_anal", "has_done_and_received_anal"):
                    merged_ledger_anal = "has_received_anal"
                cur_prof["tracks"]["anal"] = merged_ledger_anal

            # Pop experience tracks from cur_app so appearance_json stays purely physical
            for k in ("intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                      "past_intimate_history", "past_intimate_entries"):
                cur_app.pop(k, None)

            # Build backward-compatible appearance dictionary for return
            ret_app = dict(cur_app)
            ret_app["intercourse_experience"] = cur_prof["tracks"]["intercourse"]
            ret_app["oral_experience"] = cur_prof["tracks"]["oral"]
            ret_app["manual_experience"] = cur_prof["tracks"]["manual"]
            ret_app["anal_experience"] = cur_prof["tracks"]["anal"]
            ret_app["predetermined_intercourse"] = cur_prof.get("predetermined_intercourse") or cur_prof["tracks"]["intercourse"]
            disc = cur_prof.get("disclosure_flags", {})
            for dfk, dfv in disc.items():
                ret_app[dfk] = dfv
            for dfk in ("intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed"):
                if cur_prof.get(dfk):
                    ret_app[dfk] = cur_prof[dfk]
            if cur_prof.get("had_first_time_with_player"):
                ret_app["had_first_time_with_player"] = cur_prof["had_first_time_with_player"]

            conn.execute(
                """UPDATE contacts SET name=?, basic_info_json=?, relationship_score=?,
                                       track=?, unlocked_traits_json=?, preferences_json=?, race=?, gender=?, appearance_json=?, intimate_memories_json=?, rel_history_json=?,
                                       emotional_tone=?, open_thread=?, intimate_profile_json=?, household_role=?, updated_at=?
                    WHERE id=?""",
                (final_name, json.dumps(cur_info), current_score, cur_track, json.dumps(clean_traits), json.dumps(clean_prefs), cur_race, cur_gender, json.dumps(cur_app), json.dumps(cur_memories), json.dumps(cur_recent_memories), cur_emotional_tone, cur_open_thread, json.dumps(cur_prof), cur_hh_role, now, existing["id"])
            )
            if session_id and (cur_track == "romantic" or (track is not None and str(track).strip().lower() == "platonic" and existing_track == "romantic")):
                _sync_contact_track_to_social_graph(
                    conn, session_id, final_npc_id, final_name, cur_track,
                    score=current_score, gender=cur_gender, character_id=character_id,
                )
            return {
                "id": existing["id"],
                "session_id": session_id,
                "character_id": character_id,
                "npc_id": final_npc_id,
                "name": final_name,
                "basic_info": cur_info,
                "relationship_score": current_score,
                "track": cur_track,
                "unlocked_traits": clean_traits,
                "preferences": clean_prefs,
                "race": cur_race,
                "gender": cur_gender,
                "appearance": ret_app,
                "intimate_memories": cur_memories,
                "recent_memories": cur_recent_memories,
                "rel_history": cur_recent_memories,
                "intimate_profile": cur_prof,
                "emotional_tone": cur_emotional_tone,
                "open_thread": cur_open_thread,
                "household_id": cur_hh_id,
                "household_role": cur_hh_role,
                "updated_at": now
            }
        else:
            final_npc_id = str(npc_id or name.lower().replace(" ", "_")).strip()
            initial_score = relationships.clamp_score(delta_score)
            info = _merge_basic_info_safely({}, basic_info)
            if initial_score >= 100:
                info["unlocked_via_friendship"] = True
            if race and not _is_empty_info_val(race):
                info["race"] = race
            info = _enrich_contact_basic_info(
                conn, session_id, name, info,
                scenario=scen, narrative_text=narrative_text
            )
            from mechanics.social.races import extract_race_from_text, normalize_race
            inferred_race = race or info.get("race") or extract_race_from_text(narrative_text, scen_key=scen, name=name)
            
            if inferred_race and str(inferred_race).strip().lower() not in ("", "unknown"):
                cur_race = normalize_race(inferred_race, scen_key=scen, seed=name)
            else:
                fallback_race = normalize_race("", scen_key=scen, seed=name)
                cur_race = fallback_race if fallback_race != "human" else ""
            clean_traits, clean_prefs = persona.split_traits_and_preferences(
                new_traits or [],
                new_preferences or [],
                role=info.get("role", ""),
                race=cur_race,
                seed_str=f"{name}_{info.get('description', '')}"
            )
            cur_track = track if (track and str(track).strip()) else "platonic"
            cur_gender = gender or ""
            app_dict = dict(appearance) if isinstance(appearance, dict) else {}
            cur_memories = []
            cur_recent_memories = []
            if isinstance(app_dict.get("intimate_memories"), list):
                for m in app_dict["intimate_memories"]:
                    m_str = str(m).strip() if m else ""
                    if m_str and m_str not in cur_memories:
                        cur_memories.append(m_str)
            if isinstance(app_dict.get("recent_memories"), list):
                for rm in app_dict["recent_memories"]:
                    rm_str = str(rm).strip() if rm else ""
                    if rm_str and rm_str not in cur_recent_memories:
                        cur_recent_memories.append(rm_str)

            from mechanics.social.persona import is_romantic_milestone_str
            for m in cur_memories:
                m_str = str(m).strip() if m else ""
                if not m_str or m_str.startswith("Past History:") or is_romantic_milestone_str(m_str):
                    continue
                if m_str not in cur_recent_memories:
                    cur_recent_memories.append(m_str)

            pending_past_history_str = None
            if new_memory and isinstance(new_memory, str) and new_memory.strip():
                m_str = new_memory.strip()
                if m_str.startswith("Past History:") or is_romantic_milestone_str(m_str):
                    if m_str not in cur_memories:
                        cur_memories.append(m_str)
                        if len(cur_memories) > 100:
                            cur_memories = cur_memories[-100:]
                    if m_str.startswith("Past History:"):
                        pending_past_history_str = m_str
                else:
                    if m_str not in cur_recent_memories:
                        cur_recent_memories.append(m_str)
                        if len(cur_recent_memories) > 50:
                            cur_recent_memories = cur_recent_memories[-50:]

            if new_general_memory and isinstance(new_general_memory, str) and new_general_memory.strip():
                gm_str = new_general_memory.strip()
                if gm_str not in cur_recent_memories:
                    cur_recent_memories.append(gm_str)
                    if len(cur_recent_memories) > 50:
                        cur_recent_memories = cur_recent_memories[-50:]

            from mechanics.social.persona.intimacy.appearance import extract_appearance_from_text
            extracted_app = extract_appearance_from_text(f"{info.get('description', '')} {narrative_text}", name=name)
            if extracted_app:
                app_dict = persona.merge_appearance_safely(app_dict, extracted_app)
            app_dict["intimate_memories"] = list(cur_memories)
            app_dict["recent_memories"] = list(cur_recent_memories)
            app_dict["rel_history"] = list(cur_recent_memories)
            app_dict = persona.enforce_intimacy_safeguard_invariants(app_dict)
            if not cur_gender:
                try:
                    cur_gender = persona.infer_contact_gender({"name": name, "basic_info": info, "appearance": app_dict}) or ""
                except Exception:
                    pass

            cur_open_thread = open_thread or ""
            cur_emotional_tone = emotional_tone or ""
            cur_hh_role = str(household_role or "child").strip().lower()

            prof_dict = dict(intimate_profile or {})
            _intimate_keys = (
                "sensitive_spots", "turn_ons", "turn_offs", "fetishes", "desires_and_kinks",
                "act_likes", "act_dislikes", "intimate_demeanor", "intimate_dynamic", "erotic_openness",
                "undergarments", "bra", "underwear", "predetermined_intercourse", "had_first_time_with_player"
            )
            for k in _intimate_keys:
                if k in app_dict and k not in prof_dict:
                    prof_dict[k] = app_dict[k]
                elif k == "had_first_time_with_player" and app_dict.get(k):
                    prof_dict[k] = app_dict[k]
                app_dict.pop(k, None)

            if "tracks" not in prof_dict or not isinstance(prof_dict["tracks"], dict):
                prof_dict["tracks"] = {}

            from mechanics.social.persona.intimacy.logic import (
                merge_intercourse_states,
                merge_oral_states,
                merge_manual_states,
                merge_anal_states
            )
            from mechanics.social.persona.intimacy.ledger import normalize_gender

            in_intercourse = app_dict.get("intercourse_experience") or (intimate_profile.get("tracks", {}).get("intercourse") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_intercourse and in_intercourse not in ("", "unknown"):
                prof_dict["tracks"]["intercourse"] = merge_intercourse_states(prof_dict["tracks"].get("intercourse", "virgin"), in_intercourse)

            in_oral = app_dict.get("oral_experience") or (intimate_profile.get("tracks", {}).get("oral") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_oral and in_oral not in ("", "unknown"):
                prof_dict["tracks"]["oral"] = merge_oral_states(prof_dict["tracks"].get("oral", "inexperienced"), in_oral)

            in_manual = app_dict.get("manual_experience") or (intimate_profile.get("tracks", {}).get("manual") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_manual and in_manual not in ("", "unknown"):
                prof_dict["tracks"]["manual"] = merge_manual_states(prof_dict["tracks"].get("manual", "inexperienced"), in_manual)

            in_anal = app_dict.get("anal_experience") or (intimate_profile.get("tracks", {}).get("anal") if intimate_profile and isinstance(intimate_profile, dict) else None)
            if in_anal and in_anal not in ("", "unknown"):
                merged_a = merge_anal_states(prof_dict["tracks"].get("anal", "inexperienced"), in_anal)
                if normalize_gender(cur_gender) == "female" and merged_a in ("has_done_anal", "has_done_and_received_anal"):
                    merged_a = "has_received_anal"
                prof_dict["tracks"]["anal"] = merged_a

            prof_dict["tracks"].setdefault("intercourse", "virgin")
            prof_dict["tracks"].setdefault("oral", "inexperienced")
            prof_dict["tracks"].setdefault("manual", "inexperienced")
            prof_dict["tracks"].setdefault("anal", "inexperienced")

            # Pop experience tracks from app_dict so appearance_json stays purely physical
            for k in ("intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                      "past_intimate_history", "past_intimate_entries"):
                app_dict.pop(k, None)

            cursor = conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, basic_info_json,
                                          relationship_score, track, unlocked_traits_json, preferences_json, race, gender, appearance_json, intimate_memories_json, rel_history_json, emotional_tone, open_thread, intimate_profile_json, household_role, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, character_id, final_npc_id, name, json.dumps(info), initial_score,
                 cur_track, json.dumps(clean_traits), json.dumps(clean_prefs), cur_race, cur_gender, json.dumps(app_dict), json.dumps(cur_memories), json.dumps(cur_recent_memories), cur_emotional_tone, cur_open_thread, json.dumps(prof_dict), cur_hh_role, now, now)
            )
            new_row_id = cursor.lastrowid
            if session_id and cur_track == "romantic":
                _sync_contact_track_to_social_graph(
                    conn, session_id, final_npc_id, name, cur_track,
                    score=initial_score, gender=cur_gender, character_id=character_id,
                )

            if pending_past_history_str:
                try:
                    from mechanics.social.persona.intimacy.ledger import parse_past_history_entry_to_events, record_intimate_event
                    for pev in parse_past_history_entry_to_events(pending_past_history_str, char_gender=cur_gender):
                        record_intimate_event(
                            session_id=session_id,
                            character_id=final_npc_id,
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
                            narrative_summary=pending_past_history_str,
                            character_gender=cur_gender,
                            conn=conn
                        )
                except Exception:
                    pass

            # Deterministically seed named backstory partners once if non-baseline tracks exist with empty past_history
            from mechanics.social.persona.intimacy.ledger import get_intimate_events, compute_intimate_tracks_from_ledger
            existing_evs = get_intimate_events(session_id, final_npc_id, origin="past_history", conn=conn)
            has_non_baseline = any(
                prof_dict["tracks"].get(act) not in ("virgin", "inexperienced", "unknown", "", None)
                for act in ("intercourse", "oral", "manual", "anal")
            )
            if has_non_baseline and not existing_evs and not prof_dict.get("had_first_time_with_player"):
                from mechanics.social.persona.intimacy.generation import generate_past_intimate_history, persist_generated_past_history
                h_seed = int(hashlib.md5(f"{name}_{cur_race or 'human'}_{session_id}".encode("utf-8")).hexdigest(), 16)
                past_hist = generate_past_intimate_history(
                    hash_val=h_seed,
                    race=cur_race or "human",
                    gender=cur_gender or "female",
                    scenario=scen,
                    openness=str(prof_dict.get("erotic_openness") or "moderate"),
                    intercourse=prof_dict["tracks"].get("intercourse", "virgin"),
                    oral=prof_dict["tracks"].get("oral", "inexperienced"),
                    manual=prof_dict["tracks"].get("manual", "inexperienced"),
                    anal=prof_dict["tracks"].get("anal", "inexperienced"),
                )
                if past_hist:
                    persist_generated_past_history(
                        session_id=session_id,
                        character_id=final_npc_id,
                        history_dict=past_hist,
                        character_gender=cur_gender,
                        conn=conn
                    )
                    for ph_entry in (past_hist.get("entries") or []):
                        if ph_entry and ph_entry not in cur_memories:
                            cur_memories.append(ph_entry)

            # Deterministically synchronize from intimate_events ledger
            char_events = get_intimate_events(session_id, final_npc_id, physical_only=True, conn=conn)
            if char_events:
                ledger_tracks = compute_intimate_tracks_from_ledger(char_events)
                prof_dict["tracks"]["intercourse"] = merge_intercourse_states(
                    prof_dict["tracks"].get("intercourse", "virgin"),
                    ledger_tracks.get("intercourse", "virgin"),
                )
                prof_dict["tracks"]["oral"] = merge_oral_states(
                    prof_dict["tracks"].get("oral", "inexperienced"),
                    ledger_tracks.get("oral", "inexperienced"),
                )
                prof_dict["tracks"]["manual"] = merge_manual_states(
                    prof_dict["tracks"].get("manual", "inexperienced"),
                    ledger_tracks.get("manual", "inexperienced"),
                )
                merged_ledger_anal = merge_anal_states(
                    prof_dict["tracks"].get("anal", "inexperienced"),
                    ledger_tracks.get("anal", "inexperienced"),
                )
                if normalize_gender(cur_gender) == "female" and merged_ledger_anal in ("has_done_anal", "has_done_and_received_anal"):
                    merged_ledger_anal = "has_received_anal"
                prof_dict["tracks"]["anal"] = merged_ledger_anal
                app_dict["intimate_memories"] = list(cur_memories)
                conn.execute(
                    "UPDATE contacts SET appearance_json=?, intimate_memories_json=?, intimate_profile_json=? WHERE id=?",
                    (json.dumps(app_dict), json.dumps(cur_memories), json.dumps(prof_dict), new_row_id)
                )

            # Build backward-compatible appearance dictionary for return
            ret_app = dict(app_dict)
            ret_app["intercourse_experience"] = prof_dict["tracks"]["intercourse"]
            ret_app["oral_experience"] = prof_dict["tracks"]["oral"]
            ret_app["manual_experience"] = prof_dict["tracks"]["manual"]
            ret_app["anal_experience"] = prof_dict["tracks"]["anal"]
            ret_app["predetermined_intercourse"] = prof_dict.get("predetermined_intercourse") or prof_dict["tracks"]["intercourse"]
            disc = prof_dict.get("disclosure_flags", {})
            for dfk, dfv in disc.items():
                ret_app[dfk] = dfv
            for dfk in ("intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed"):
                if prof_dict.get(dfk):
                    ret_app[dfk] = prof_dict[dfk]
            if prof_dict.get("had_first_time_with_player"):
                ret_app["had_first_time_with_player"] = prof_dict["had_first_time_with_player"]

            return {
                "id": new_row_id,
                "session_id": session_id,
                "character_id": character_id,
                "npc_id": final_npc_id,
                "name": name,
                "basic_info": info,
                "relationship_score": initial_score,
                "track": cur_track,
                "unlocked_traits": clean_traits,
                "preferences": clean_prefs,
                "race": cur_race,
                "gender": cur_gender,
                "appearance": ret_app,
                "intimate_memories": cur_memories,
                "recent_memories": cur_recent_memories,
                "rel_history": cur_recent_memories,
                "intimate_profile": prof_dict,
                "emotional_tone": cur_emotional_tone,
                "open_thread": cur_open_thread,
                "household_id": None,
                "household_role": cur_hh_role,
                "created_at": now,
                "updated_at": now
            }

def ensure_scene_npcs_in_contacts(session_id: int, character_id: int = 0):
    """Ensure all non-hostile present scene NPCs are registered as contacts in this session."""
    sess = db.get_session(session_id)
    if not sess:
        return
    current_npcs = sess.get("current_npcs") or []
    if not current_npcs:
        return

    scen_key = sess.get("scenario", "fantasy")
    import scenario_data
    if not (scenario_data.is_mechanic_enabled(scen_key, "contact_list") or scenario_data.is_mechanic_enabled(scen_key, "relationship_meter")):
        return

    import game_engine
    present_lower_names = {
        game_engine._get_npc_name(npc).lower()
        for npc in current_npcs
        if game_engine._get_npc_name(npc)
    }
    with get_conn() as conn:
        existing_rows = conn.execute(
            "SELECT id, npc_id, name, basic_info_json FROM contacts WHERE session_id=?",
            (session_id,),
        ).fetchall()
        existing_names = {str(r["name"]).strip().lower() for r in existing_rows if r["name"]}
        existing_ids = {str(r["npc_id"]).strip().lower() for r in existing_rows if r["npc_id"]}
        for r in existing_rows:
            r_name = str(r["name"] or "").strip().lower()
            r_id = str(r["npc_id"] or "").strip().lower()
            if r_name in present_lower_names or r_id in present_lower_names:
                try:
                    b_existing = json.loads(r["basic_info_json"] or "{}")
                    if isinstance(b_existing, dict) and (not b_existing.get("met_in_person") or b_existing.get("offscreen_ripple_only")):
                        b_existing["met_in_person"] = True
                        b_existing.pop("offscreen_ripple_only", None)
                        conn.execute(
                            "UPDATE contacts SET basic_info_json=? WHERE id=?",
                            (json.dumps(b_existing), r["id"]),
                        )
                except Exception:
                    pass

    unadded = []
    for npc in current_npcs:
        n_name = game_engine._get_npc_name(npc)
        if n_name and (n_name.lower() not in existing_names and n_name.lower() not in existing_ids):
            unadded.append(npc)

    if not unadded:
        return

    enemies = sess.get("nearby_enemies", [])
    enemy_names = {game_engine._get_npc_name(e).lower() for e in enemies if e}

    party_char_names = set()
    if character_id:
        c = db.get_character_by_id(character_id) or db.get_character(character_id)
        if c and c.get("name"):
            party_char_names.add(str(c["name"]).strip().lower())
    for uid in (sess.get("turn_order") or []):
        tc = db.get_character(uid)
        if tc and tc.get("name"):
            party_char_names.add(str(tc["name"]).strip().lower())

    import namegen
    from mechanics.world.mobility import get_session_dialogue_partners
    dialogue_partners = {p.lower() for p in get_session_dialogue_partners(sess)}

    scene_narrative = str(sess.get("narrative") or "")
    for npc in unadded:
        n_name = game_engine._get_npc_name(npc)
        if not n_name or n_name.lower() in enemy_names or n_name.lower() in party_char_names:
            continue

        # A1: If an NPC parent from an existing household appears in-scene, promote them to a Contact
        try:
            import mechanics.social.genealogy as genealogy
            promoted_parent = genealogy.maybe_promote_scene_parent(session_id, n_name)
            if promoted_parent:
                continue
        except Exception:
            pass

        n_role = (npc.get("role") if isinstance(npc, dict) else "") or ""
        n_desc = (npc.get("description") if isinstance(npc, dict) else "") or ""

        # Check Peer / Role Eligibility (e.g. students vs teachers/parents/clerks in high school)
        import mechanics.social.relationships as relationships
        if not relationships.is_contact_eligible(name=n_name, role=n_role, description=n_desc, scenario=scen_key):
            continue

        # Do not auto-add pure generic ambient crowd (e.g. "Drunken Patron", "Town Guard") unless spoken to or friendly
        disp = str(npc.get("disposition", "")).lower() if isinstance(npc, dict) else ""
        is_dialogue = (n_name.lower() in dialogue_partners) or any(dp in n_name.lower() or n_name.lower() in dp for dp in dialogue_partners)
        if namegen.is_generic_role_name(n_name) and not is_dialogue and disp not in ("friendly", "companion", "ally"):
            continue

        b_info = {"met_in_person": True}
        if isinstance(npc, dict):
            for k in ("role", "occupation", "description", "faction", "club", "club_role", "grade", "clique", "age", "mannerisms", "motivation", "disposition"):
                val = npc.get(k)
                if not _is_empty_info_val(val):
                    b_info[k] = val

        upsert_contact(
            session_id=session_id,
            character_id=character_id,
            npc_id=n_name,
            name=n_name,
            basic_info=b_info if b_info else None,
            delta_score=0,
            track=None,
            new_traits=npc.get("traits") if isinstance(npc, dict) else None,
            new_preferences=npc.get("preferences") if isinstance(npc, dict) else None,
            race=npc.get("race", "") if isinstance(npc, dict) else "",
            gender=npc.get("gender", "") if isinstance(npc, dict) else "",
            appearance=npc.get("appearance", {}) if isinstance(npc, dict) else None,
            narrative_text=scene_narrative
        )

def get_contacts(session_id: int, character_id: int = 0, resolve_relations: bool = True, ensure_scene: bool = True) -> list[dict]:
    import mechanics.social.persona as persona
    import namegen

    # Guard against recursive relation resolution
    if session_id in _active_resolving_contacts:
        resolve_relations = False
        ensure_scene = False

    if ensure_scene:
        ensure_scene_npcs_in_contacts(session_id, character_id)

    with get_conn() as conn:
        if character_id:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? AND (character_id=? OR character_id=0) ORDER BY relationship_score DESC, updated_at DESC",
                (session_id, character_id)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? ORDER BY relationship_score DESC, updated_at DESC",
                (session_id,)).fetchall()

        scen_key = "fantasy"
        scene_narrative = ""
        try:
            s_row = conn.execute("SELECT scenario, narrative FROM sessions WHERE id=?", (session_id,)).fetchone()
            if s_row:
                scen_key = s_row["scenario"] or "fantasy"
                scene_narrative = s_row["narrative"] or ""
        except Exception:
            pass

        # Batch-load all intimate_events and households for this session in 2 queries (eliminating N+1 queries)
        events_by_char: dict[str, list[dict]] = {}
        try:
            ev_rows = conn.execute(
                "SELECT * FROM intimate_events WHERE session_id = ? ORDER BY turn_number ASC, id ASC",
                (session_id,)
            ).fetchall()
            for er in ev_rows:
                ed = dict(er)
                ed["is_physical"] = bool(ed.get("is_physical", 1))
                ed["is_secret_affair"] = bool(ed.get("is_secret_affair", 0))
                ck = str(ed.get("character_id") or "").strip().lower()
                if ck:
                    events_by_char.setdefault(ck, []).append(ed)
        except Exception:
            events_by_char = {}

        households_by_id: dict[int, dict] = {}
        if resolve_relations:
            try:
                hh_rows = conn.execute("SELECT * FROM households WHERE session_id = ?", (session_id,)).fetchall()
                for hr in hh_rows:
                    parsed_hh = _parse_household_row(hr)
                    households_by_id[int(parsed_hh["id"])] = parsed_hh
            except Exception:
                households_by_id = {}

        contacts = []
        seen_keys = set()
        for r in rows:
            d = dict(r)
            c_name = str(d.get("name") or "").strip()
            c_nid = str(d.get("npc_id") or "").strip()
            if not c_name or len(c_name) > 80 or len(c_nid) > 80:
                continue
            if not namegen.is_valid_entity_name(c_name):
                continue
            c_key = c_name.lower()
            if c_key in seen_keys:
                continue
            seen_keys.add(c_key)
            try:
                raw_info = json.loads(d.get("basic_info_json") or "{}")
            except Exception:
                raw_info = {}
            enriched_info = _enrich_contact_basic_info(
                conn, session_id, c_name, raw_info,
                scenario=scen_key, narrative_text=scene_narrative
            )
            if enriched_info != raw_info and d.get("id"):
                try:
                    conn.execute(
                        "UPDATE contacts SET basic_info_json=? WHERE id=?",
                        (json.dumps(enriched_info), d["id"])
                    )
                except Exception:
                    pass
            d["basic_info"] = enriched_info
            try:
                raw_traits = json.loads(d.get("unlocked_traits_json") or "[]")
            except Exception:
                raw_traits = []
            try:
                raw_prefs = json.loads(d.get("preferences_json") or "[]")
            except Exception:
                raw_prefs = []
            try:
                col_mem = json.loads(d.get("intimate_memories_json") or "[]")
                if not isinstance(col_mem, list):
                    col_mem = []
            except Exception:
                col_mem = []

            clean_traits, clean_prefs = persona.split_traits_and_preferences(
                raw_traits,
                raw_prefs,
                role=enriched_info.get("role", ""),
                race=d.get("race") or enriched_info.get("race") or "",
                seed_str=f"{c_name}_{enriched_info.get('description', '')}"
            )
            d["unlocked_traits"] = clean_traits
            d["preferences"] = clean_prefs

            try:
                d["appearance"] = json.loads(d.get("appearance_json") or "{}")
            except Exception:
                d["appearance"] = {}

            app_mem = d["appearance"].get("intimate_memories") if isinstance(d.get("appearance"), dict) else []
            if not isinstance(app_mem, list):
                app_mem = []

            combined_mem = list(col_mem)
            for m in app_mem:
                m_clean = str(m).strip() if m else ""
                if m_clean and m_clean not in combined_mem:
                    combined_mem.append(m_clean)

            try:
                rel_hist = json.loads(d.get("rel_history_json") or "[]")
                if not isinstance(rel_hist, list):
                    rel_hist = []
            except Exception:
                rel_hist = []

            # Auto-partition combined_mem into genuine romantic vs general interaction memories
            clean_intimate = []
            for m in combined_mem:
                m_clean = str(m).strip() if m else ""
                if not m_clean:
                    continue
                if m_clean.startswith("Past History:") or persona.is_romantic_milestone_str(m_clean):
                    clean_intimate.append(m_clean)
                else:
                    if m_clean not in rel_hist:
                        rel_hist.append(m_clean)

            d["intimate_memories"] = combined_mem
            d["shared_romantic_milestones"] = clean_intimate
            d["recent_memories"] = rel_hist
            d["rel_history"] = rel_hist

            # Hydrate intimate_profile and intimate_events
            try:
                d["intimate_profile"] = json.loads(d.get("intimate_profile_json") or "{}")
            except Exception:
                d["intimate_profile"] = {}

            # Backward compatibility: populate appearance with intimate_profile fields and tracks
            if isinstance(d.get("intimate_profile"), dict):
                for ipk, ipv in d["intimate_profile"].items():
                    if ipk == "tracks" and isinstance(ipv, dict):
                        for trk_k, trk_v in ipv.items():
                            d["appearance"].setdefault(f"{trk_k}_experience", trk_v)
                    elif ipk == "disclosure_flags" and isinstance(ipv, dict):
                        for dfk, dfv in ipv.items():
                            d["appearance"].setdefault(dfk, dfv)
                    elif ipk not in d["appearance"]:
                        d["appearance"][ipk] = ipv
                if "tracks" in d["intimate_profile"] and "intercourse" in d["intimate_profile"]["tracks"]:
                    d["appearance"].setdefault("predetermined_intercourse", d["intimate_profile"]["tracks"]["intercourse"])

            char_nid_key = str(d.get("npc_id") or "").strip().lower()
            char_id_key = str(d.get("id") or "").strip().lower()
            evs = list(events_by_char.get(char_nid_key) or [])
            if char_id_key and char_id_key != char_nid_key:
                seen_ev_ids = {e.get("id") for e in evs if e.get("id")}
                for extra_ev in (events_by_char.get(char_id_key) or []):
                    if extra_ev.get("id") not in seen_ev_ids:
                        evs.append(extra_ev)
            past_evs = [e for e in evs if e.get("event_origin") == "past_history" or e.get("turn_number") == 0]
            game_evs = [e for e in evs if e.get("event_origin") == "gameplay" or e.get("turn_number", 0) > 0]
            d["past_intimate_events"] = past_evs
            d["gameplay_intimate_events"] = game_evs

            if past_evs:
                past_entries = []
                for pev in past_evs:
                    if pev.get("narrative_summary"):
                        if pev["narrative_summary"] not in past_entries:
                            past_entries.append(pev["narrative_summary"])
                    else:
                        p_name = pev.get("partner_name", "Past Partner")
                        p_role = pev.get("partner_role", "Former Acquaintance")
                        act = pev.get("act_type", "intimacy")
                        dir_val = pev.get("direction", "mutual")
                        cnt = pev.get("count", 1)
                        if act == "oral":
                            if dir_val == "give":
                                past_entries.append(f"Past History: performed oral on '{p_name}' ({p_role})")
                            elif dir_val == "receive":
                                past_entries.append(f"Past History: Received oral from '{p_name}' ({p_role})")
                            else:
                                past_entries.append(f"Past History: Mutual oral intimacy with '{p_name}' ({p_role})")
                        elif act == "manual":
                            if dir_val == "give":
                                past_entries.append(f"Past History: Manually stimulated '{p_name}' ({p_role})")
                            elif dir_val == "receive":
                                past_entries.append(f"Past History: Received manual stimulation from '{p_name}' ({p_role})")
                            else:
                                past_entries.append(f"Past History: Mutual manual petting & foreplay with '{p_name}' ({p_role})")
                        elif act == "anal":
                            if dir_val == "receive":
                                past_entries.append(f"Past History: Received anal intimacy from '{p_name}' ({p_role})")
                            else:
                                past_entries.append(f"Past History: Performed anal on '{p_name}' ({p_role})")
                        elif act == "intercourse":
                            past_entries.append(f"Past History: Prior intercourse encounter ({cnt} times) with '{p_name}' ({p_role})")
                        else:
                            past_entries.append(f"Past History: Prior {act} encounter ({cnt} times) with '{p_name}' ({p_role})")
                d["past_intimate_entries"] = past_entries
                d["past_intimate_history"] = "\n".join(past_entries)
            else:
                d["past_intimate_entries"] = []
                d["past_intimate_history"] = ""

            if game_evs:
                game_mems = []
                for ge in game_evs:
                    s = ge.get("narrative_summary")
                    if s and s not in game_mems:
                        game_mems.append(s)
                if game_mems:
                    d["shared_romantic_milestones"] = game_mems
                    for gm in game_mems:
                        if gm not in combined_mem:
                            combined_mem.append(gm)

            t = dict((d.get("intimate_profile") or {}).get("tracks") or {})
            if evs:
                from mechanics.social.persona.intimacy.ledger import compute_intimate_tracks_from_ledger
                from mechanics.social.persona.intimacy.logic import (
                    merge_intercourse_states,
                    merge_oral_states,
                    merge_manual_states,
                    merge_anal_states
                )
                ledger_tracks = compute_intimate_tracks_from_ledger(evs)
                t["intercourse"] = merge_intercourse_states(t.get("intercourse", "virgin"), ledger_tracks.get("intercourse", "virgin"))
                t["oral"] = merge_oral_states(t.get("oral", "inexperienced"), ledger_tracks.get("oral", "inexperienced"))
                t["manual"] = merge_manual_states(t.get("manual", "inexperienced"), ledger_tracks.get("manual", "inexperienced"))
                t["anal"] = merge_anal_states(t.get("anal", "inexperienced"), ledger_tracks.get("anal", "inexperienced"), gender=d.get("gender", ""))
                if isinstance(d.get("intimate_profile"), dict):
                    d["intimate_profile"]["tracks"] = t
            d["intercourse_experience"] = t.get("intercourse", "virgin")
            d["oral_experience"] = t.get("oral", "inexperienced")
            d["manual_experience"] = t.get("manual", "inexperienced")
            d["anal_experience"] = t.get("anal", "inexperienced")
            if isinstance(d.get("appearance"), dict):
                d["appearance"]["intercourse_experience"] = d["intercourse_experience"]
                d["appearance"]["oral_experience"] = d["oral_experience"]
                d["appearance"]["manual_experience"] = d["manual_experience"]
                d["appearance"]["anal_experience"] = d["anal_experience"]
                d["appearance"]["predetermined_intercourse"] = (d.get("intimate_profile") or {}).get("predetermined_intercourse") or d["intercourse_experience"]
                disc = (d.get("intimate_profile") or {}).get("disclosure_flags") or {}
                for dfk, dfv in disc.items():
                    if dfk not in d["appearance"]:
                        d["appearance"][dfk] = dfv
                for dfk in ("intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed"):
                    if (d.get("intimate_profile") or {}).get(dfk):
                        d["appearance"][dfk] = (d.get("intimate_profile") or {})[dfk]
            if isinstance(d.get("appearance"), dict):
                d["appearance"]["intimate_memories"] = combined_mem
                d["appearance"]["shared_romantic_milestones"] = clean_intimate
                d["appearance"]["recent_memories"] = rel_hist
                d["appearance"]["rel_history"] = rel_hist

            try:
                d["relations"] = json.loads(d.get("relations_json") or "{}")
            except Exception:
                d["relations"] = {}

            d["status_effects"] = (d.get("basic_info") or {}).get("status_effects") or []

            contacts.append(d)

    if resolve_relations:
        for d in contacts:
            if d.get("household_id"):
                import mechanics.social.genealogy as genealogy
                hh_id_int = int(d["household_id"])
                hh = households_by_id.get(hh_id_int) or get_household_by_id(hh_id_int)
                if hh:
                    hydrated_hh = genealogy._hydrate_household_entity(hh, d, scen_key)
                    if not isinstance(d.get("relations"), dict):
                        d["relations"] = {}
                    d["relations"]["family"] = genealogy.build_family_tree_from_household(
                        hydrated_hh,
                        d.get("name", ""),
                        scenario=scen_key,
                        member_role=d.get("household_role"),
                    )
                    if hh.get("residence_location"):
                        d["relations"]["residence_location"] = hh["residence_location"]
                    d["household_id"] = hh["id"]
            elif not d.get("relations") or not d["relations"].get("family"):
                _active_resolving_contacts.add(session_id)
                try:
                    import mechanics.social.genealogy as genealogy
                    d["relations"] = genealogy.ensure_contact_relations(d, session_id=session_id, scenario=scen_key)
                    if session_id and d.get("id"):
                        try:
                            with get_conn() as conn:
                                conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(d["relations"]), d["id"]))
                        except Exception:
                            pass
                finally:
                    _active_resolving_contacts.discard(session_id)

    return contacts

def update_contact_score(session_id: int, npc_id: str, new_score: int, character_id: int = 0):
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    from mechanics.social.relationships import clamp_score
    clamped_score = clamp_score(new_score)
    now = time.time()
    npc_clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    npc_raw_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    with get_conn() as conn:
        if clamped_score >= 100:
            rows_to_stamp = conn.execute(
                """SELECT id, basic_info_json FROM contacts
                   WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
                   AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
                (session_id, character_id, character_id, npc_clean_id, npc_raw_name, npc_raw_name, npc_clean_id),
            ).fetchall()
            for r_st in rows_to_stamp:
                try:
                    b_st = json.loads(r_st["basic_info_json"] or "{}")
                except Exception:
                    b_st = {}
                if isinstance(b_st, dict) and not b_st.get("unlocked_via_friendship"):
                    b_st["unlocked_via_friendship"] = True
                    conn.execute(
                        "UPDATE contacts SET basic_info_json=? WHERE id=?",
                        (json.dumps(b_st), r_st["id"]),
                    )
        conn.execute(
            """UPDATE contacts SET relationship_score=?, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (clamped_score, now, session_id, character_id, character_id, npc_clean_id, npc_raw_name, npc_raw_name, npc_clean_id)
        )

def _sync_contact_track_to_social_graph(
    conn,
    session_id: int,
    contact_npc_id: str,
    contact_name: str,
    norm_track: str,
    score: int = 60,
    gender: str = "",
    character_id: int = 0,
) -> None:
    """Write-time synchronization from contacts.track mutations into social_ties."""
    if not session_id:
        return
    try:
        import mechanics.social.relationship_graph as rg
        c_key = rg.canonical_person_key(contact_name or contact_npc_id)
        if not c_key:
            return
        rg.get_or_create_person(
            session_id,
            contact_name or contact_npc_id,
            person_key=c_key,
            gender=gender or "",
            origin="contact",
            contact_npc_id=contact_npc_id,
            conn=conn,
        )
        p_disp = "Player"
        if character_id:
            ch_r = conn.execute("SELECT name FROM characters WHERE id = ? LIMIT 1", (character_id,)).fetchone()
            if ch_r and ch_r["name"]:
                p_disp = str(ch_r["name"]).strip()
        if p_disp == "Player":
            p_disp = rg._resolve_player_display_name(session_id, conn)
        rg.get_or_create_person(session_id, p_disp, person_key="player", origin="player", conn=conn)

        if norm_track == "romantic":
            a_c, b_c = rg.canonical_pair(c_key, "player", is_directed=False)
            cur_player_p = rg.get_current_partner(session_id, "player", conn=conn)
            player_has_other_partner = bool(cur_player_p and cur_player_p.get("person_key") != c_key)
            has_rom = conn.execute(
                """SELECT 1 FROM social_ties
                   WHERE session_id = ? AND person_a_key = ? AND person_b_key = ?
                     AND tie_type IN ('dating', 'engaged', 'married')
                     AND status = 'active'
                   LIMIT 1""",
                (session_id, a_c, b_c),
            ).fetchone()
            if not has_rom:
                if not player_has_other_partner:
                    rg.end_tie(session_id, c_key, "player", rg.TIETYPE_AFFAIR, reason="promoted_to_dating", materialize=False, conn=conn)
                rg.form_tie(
                    session_id,
                    c_key,
                    "player",
                    rg.TIETYPE_DATING,
                    closeness=max(60, int(score or 60)),
                    origin="gameplay",
                    supersede=not player_has_other_partner,
                    conn=conn,
                )
        else:
            rg.end_all_romantic_ties(
                session_id,
                c_key,
                "player",
                reason="track_switched_platonic",
                conn=conn,
            )
    except Exception:
        pass


def update_contact_track(session_id: int, npc_id: str, new_track: str, character_id: int = 0) -> bool:
    """Updates the social track (platonic or romantic) for a contact."""
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    clean_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    norm_track = "romantic" if str(new_track).strip().lower() == "romantic" else "platonic"
    now = time.time()
    with get_conn() as conn:
        target_rows = conn.execute(
            """SELECT npc_id, name, relationship_score, gender FROM contacts
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id),
        ).fetchall()
        cursor = conn.execute(
            """UPDATE contacts SET track=?, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (norm_track, now, session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id)
        )
        updated = cursor.rowcount > 0
        if updated and session_id:
            for tr in target_rows:
                _sync_contact_track_to_social_graph(
                    conn,
                    session_id,
                    tr["npc_id"],
                    tr["name"],
                    norm_track,
                    score=tr["relationship_score"] or 60,
                    gender=tr["gender"] or "",
                    character_id=character_id,
                )
        return updated

def update_contact_open_thread(session_id: int, npc_id: str, open_thread: str, emotional_tone: str = "", character_id: int = 0) -> bool:
    """Updates the open thread and emotional tone for a contact."""
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    clean_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    now = time.time()
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE contacts SET open_thread=?, emotional_tone=CASE WHEN ? != '' THEN ? ELSE emotional_tone END, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (open_thread or "", emotional_tone or "", emotional_tone or "", now, session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id)
        )
        return cursor.rowcount > 0

def update_contact_relations(session_id: int, npc_id: str, relations: dict, character_id: int = 0) -> bool:
    """Updates the relations dict (family, romance, friends, rivals) for a contact."""
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    clean_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    rel_json = json.dumps(relations) if isinstance(relations, dict) else "{}"
    now = time.time()
    with get_conn() as conn:
        cursor = conn.execute(
            """UPDATE contacts SET relations_json=?, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (rel_json, now, session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id)
        )
        updated = cursor.rowcount > 0

    if updated and session_id and isinstance(relations, dict) and "romance" in relations:
        try:
            import mechanics.social.relationship_graph as rg
            c_key = rg.canonical_person_key(clean_name or clean_id)
            rom = relations.get("romance") or {}
            cp = rom.get("current_partner")
            if isinstance(cp, dict) and cp.get("name"):
                p_name = cp["name"].strip()
                if p_name.lower() not in ("player", "you") and not p_name.lower().startswith("player:"):
                    p_key = rg.canonical_person_key(p_name)
                    rg.get_or_create_person(session_id, clean_name or clean_id, person_key=c_key)
                    rg.get_or_create_person(session_id, p_name, person_key=p_key, role=cp.get("role", "Partner"))
                    curr_p = rg.get_current_partner(session_id, c_key)
                    if not curr_p or curr_p.get("person_key") != p_key:
                        rg.form_tie(session_id, c_key, p_key, rg.TIETYPE_DATING, closeness=70, supersede=True)
            elif rom.get("status") == "Single" or cp is None:
                curr_p = rg.get_current_partner(session_id, c_key)
                if curr_p and not curr_p.get("person_key", "").startswith("player:"):
                    rg.end_tie(session_id, c_key, curr_p["person_key"], curr_p.get("tie_type", rg.TIETYPE_DATING), reason="broken_up")
        except Exception:
            pass

    return updated

def update_contact_status_effects(session_id: int, npc_id: str, character_id: int = 0, status_effects: list = None) -> bool:
    """Updates the status effects list inside basic_info_json for a contact."""
    if isinstance(character_id, list) and status_effects is None:
        status_effects = character_id
        character_id = 0
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    clean_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    effs_list = [str(s).strip() for s in (status_effects or []) if str(s).strip()]
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, basic_info_json FROM contacts
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)
               ORDER BY id DESC LIMIT 1""",
            (session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id)
        ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT id, basic_info_json FROM contacts
                   WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
                   AND (npc_id LIKE ? OR lower(name) LIKE ? OR ? LIKE (lower(name) || '%'))
                   ORDER BY id DESC LIMIT 1""",
                (session_id, character_id, character_id, f"{clean_id}_%", f"{clean_name} %", clean_name)
            ).fetchone()
        if not row:
            return False
        c_id = row["id"]
        try:
            b_info = json.loads(row["basic_info_json"] or "{}")
        except Exception:
            b_info = {}
        b_info["status_effects"] = effs_list
        cursor = conn.execute(
            "UPDATE contacts SET basic_info_json=?, updated_at=? WHERE id=?",
            (json.dumps(b_info), now, c_id)
        )
        return cursor.rowcount > 0

# ==============================================================================
# HOUSEHOLDS & GENEALOGY ENTITY MODEL (ARCHITECTURE 1)
# ==============================================================================

def create_household(
    session_id: int,
    household_key: str,
    surname: str,
    father: dict | None = None,
    mother: dict | None = None,
    narrative_siblings: list | None = None,
    residence_location: str = ""
) -> int:
    """Creates a new normalized household entity in SQLite, returning its ID."""
    now = time.time()
    father_json = json.dumps(father or {})
    mother_json = json.dumps(mother or {})
    narrative_siblings_json = json.dumps(narrative_siblings or [])
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
            (session_id, household_key)
        ).fetchone()
        if existing:
            return existing["id"]

        try:
            cursor = conn.execute(
                """INSERT INTO households (
                    session_id, household_key, surname, father_json, mother_json,
                    narrative_siblings_json, residence_location, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, household_key, surname, father_json, mother_json,
                 narrative_siblings_json, residence_location or "", now, now)
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            existing = conn.execute(
                "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
                (session_id, household_key)
            ).fetchone()
            if existing:
                return existing["id"]
            raise


def _parse_household_row(row: sqlite3.Row | dict) -> dict:
    """Deserializes JSON columns of a raw households row into a dict."""
    d = dict(row)
    try:
        d["father"] = json.loads(d.get("father_json") or "{}")
    except Exception:
        d["father"] = {}
    try:
        d["mother"] = json.loads(d.get("mother_json") or "{}")
    except Exception:
        d["mother"] = {}
    try:
        d["narrative_siblings"] = json.loads(d.get("narrative_siblings_json") or "[]")
        if not isinstance(d["narrative_siblings"], list):
            d["narrative_siblings"] = []
    except Exception:
        d["narrative_siblings"] = []
    return d


def get_household_by_id(household_id: int) -> dict | None:
    """Retrieves a household by its primary key ID."""
    if not household_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM households WHERE id = ?", (household_id,)).fetchone()
        if not row:
            return None
        return _parse_household_row(row)


def get_household_by_key(session_id: int, household_key: str) -> dict | None:
    """Retrieves a household by its session-unique key."""
    if not session_id or not household_key:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM households WHERE session_id = ? AND household_key = ?",
            (session_id, household_key)
        ).fetchone()
        if not row:
            return None
        return _parse_household_row(row)


def get_household_members(household_id: int) -> list[dict]:
    """Retrieves all contact records assigned to the specified household."""
    if not household_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE household_id = ? ORDER BY id ASC",
            (household_id,)
        ).fetchall()
        members = []
        for r in rows:
            d = dict(r)
            for jcol in ("basic_info_json", "relations_json", "appearance_json", "unlocked_traits_json", "preferences_json", "intimate_memories_json", "rel_history_json"):
                plain = jcol.replace("_json", "")
                try:
                    d[plain] = json.loads(d.get(jcol) or ("[]" if "json" in jcol and jcol in ("unlocked_traits_json", "preferences_json", "intimate_memories_json", "rel_history_json") else "{}"))
                except Exception:
                    d[plain] = [] if "[]" in jcol else {}
            members.append(d)
        return members


def update_household(household_id: int, **fields) -> bool:
    """Updates fields on an existing household."""
    if not household_id or not fields:
        return False
    allowed = {"household_key", "surname", "father", "mother", "narrative_siblings", "residence_location", "father_json", "mother_json", "narrative_siblings_json"}
    updates = []
    vals = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k in ("father", "mother"):
            updates.append(f"{k}_json = ?")
            vals.append(json.dumps(v if isinstance(v, dict) else {}))
        elif k == "narrative_siblings":
            updates.append("narrative_siblings_json = ?")
            vals.append(json.dumps(v if isinstance(v, list) else []))
        else:
            updates.append(f"{k} = ?")
            vals.append(v)
    if not updates:
        return False
    updates.append("updated_at = ?")
    vals.append(time.time())
    vals.append(household_id)
    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE households SET {', '.join(updates)} WHERE id = ?",
            tuple(vals)
        )
        return cursor.rowcount > 0


def assign_contact_household(
    session_id: int,
    contact_identifier: int | str,
    household_id: int,
    household_role: str | None = None,
) -> bool:
    """Assigns or re-links a contact to a household by contact ID or npc_id/name."""
    if not contact_identifier or not household_id:
        return False
    now = time.time()
    role_clean = str(household_role).strip().lower() if household_role else None
    with get_conn() as conn:
        if isinstance(contact_identifier, int) or (isinstance(contact_identifier, str) and str(contact_identifier).isdigit()):
            cursor = conn.execute(
                "UPDATE contacts SET household_id = ?, household_role = COALESCE(?, household_role, 'child'), updated_at = ? WHERE id = ? AND session_id = ?",
                (household_id, role_clean, now, int(contact_identifier), session_id)
            )
        else:
            clean_id = str(contact_identifier).strip().lower().replace(" ", "_")
            clean_name = str(contact_identifier).strip().lower()
            cursor = conn.execute(
                """UPDATE contacts SET household_id = ?, household_role = COALESCE(?, household_role, 'child'), updated_at = ?
                   WHERE session_id = ? AND (npc_id = ? OR lower(npc_id) = ? OR lower(name) = ?)""",
                (household_id, role_clean, now, session_id, clean_id, clean_id, clean_name)
            )
        return cursor.rowcount > 0

def get_contact(session_id: int, npc_id: str, character_id: int = 0) -> dict | None:
    # If caller passed (session_id, character_id: int, npc_id: str) in reverse order
    if isinstance(npc_id, int) and isinstance(character_id, str):
        npc_id, character_id = character_id, npc_id
    import mechanics.social.persona as persona
    clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    clean_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    with get_conn() as conn:
        if character_id:
            r = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? AND (character_id=? OR character_id=0) AND (npc_id=? OR lower(name)=?) ORDER BY id DESC",
                (session_id, character_id, clean_id, clean_name)).fetchone()
            if not r:
                r = conn.execute(
                    """SELECT * FROM contacts WHERE session_id=? AND (character_id=? OR character_id=0)
                       AND (npc_id LIKE ? OR lower(name) LIKE ? OR ? LIKE (lower(name) || '%'))
                       ORDER BY id DESC LIMIT 1""",
                    (session_id, character_id, f"{clean_id}_%", f"{clean_name} %", clean_name)).fetchone()
        else:
            r = conn.execute(
                "SELECT * FROM contacts WHERE session_id=? AND (npc_id=? OR lower(name)=?) ORDER BY id DESC",
                (session_id, clean_id, clean_name)).fetchone()
            if not r:
                r = conn.execute(
                    """SELECT * FROM contacts WHERE session_id=?
                       AND (npc_id LIKE ? OR lower(name) LIKE ? OR ? LIKE (lower(name) || '%'))
                       ORDER BY id DESC LIMIT 1""",
                    (session_id, f"{clean_id}_%", f"{clean_name} %", clean_name)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        raw_info = json.loads(d.get("basic_info_json") or "{}")
    except Exception:
        raw_info = {}

    scen_key = "fantasy"
    scene_narrative = ""
    with get_conn() as conn:
        try:
            s_row = conn.execute("SELECT scenario, narrative FROM sessions WHERE id=?", (session_id,)).fetchone()
            if s_row:
                scen_key = s_row["scenario"] or "fantasy"
                scene_narrative = s_row["narrative"] or ""
        except Exception:
            pass
        enriched_info = _enrich_contact_basic_info(
            conn, session_id, d.get("name", ""), raw_info,
            scenario=scen_key, narrative_text=scene_narrative
        )
        if enriched_info != raw_info and d.get("id"):
            try:
                conn.execute(
                    "UPDATE contacts SET basic_info_json=? WHERE id=?",
                    (json.dumps(enriched_info), d["id"])
                )
            except Exception:
                pass
    d["basic_info"] = enriched_info
    try:
        raw_traits = json.loads(d.get("unlocked_traits_json") or "[]")
    except Exception:
        raw_traits = []
    try:
        raw_prefs = json.loads(d.get("preferences_json") or "[]")
    except Exception:
        raw_prefs = []
    try:
        col_mem = json.loads(d.get("intimate_memories_json") or "[]")
        if not isinstance(col_mem, list):
            col_mem = []
    except Exception:
        col_mem = []

    clean_traits, clean_prefs = persona.split_traits_and_preferences(
        raw_traits,
        raw_prefs,
        role=enriched_info.get("role", ""),
        race=d.get("race") or enriched_info.get("race") or "",
        seed_str=f"{d.get('name', '')}_{enriched_info.get('description', '')}"
    )
    d["unlocked_traits"] = clean_traits
    d["preferences"] = clean_prefs

    try:
        d["appearance"] = json.loads(d.get("appearance_json") or "{}")
    except Exception:
        d["appearance"] = {}

    app_mem = d["appearance"].get("intimate_memories") if isinstance(d.get("appearance"), dict) else []
    if not isinstance(app_mem, list):
        app_mem = []

    combined_mem = list(col_mem)
    for m in app_mem:
        m_clean = str(m).strip() if m else ""
        if m_clean and m_clean not in combined_mem:
            combined_mem.append(m_clean)

    try:
        rel_hist = json.loads(d.get("rel_history_json") or "[]")
        if not isinstance(rel_hist, list):
            rel_hist = []
    except Exception:
        rel_hist = []

    clean_intimate = []
    for m in combined_mem:
        m_clean = str(m).strip() if m else ""
        if not m_clean:
            continue
        if m_clean.startswith("Past History:") or persona.is_romantic_milestone_str(m_clean):
            clean_intimate.append(m_clean)
        else:
            if m_clean not in rel_hist:
                rel_hist.append(m_clean)

    d["intimate_memories"] = combined_mem
    d["shared_romantic_milestones"] = clean_intimate
    d["recent_memories"] = rel_hist
    d["rel_history"] = rel_hist

    # Hydrate intimate_profile and intimate_events
    try:
        d["intimate_profile"] = json.loads(d.get("intimate_profile_json") or "{}")
    except Exception:
        d["intimate_profile"] = {}

    # Backward compatibility: populate appearance with intimate_profile fields and tracks
    if isinstance(d.get("intimate_profile"), dict):
        for ipk, ipv in d["intimate_profile"].items():
            if ipk == "tracks" and isinstance(ipv, dict):
                for trk_k, trk_v in ipv.items():
                    d["appearance"].setdefault(f"{trk_k}_experience", trk_v)
            elif ipk == "disclosure_flags" and isinstance(ipv, dict):
                for dfk, dfv in ipv.items():
                    d["appearance"].setdefault(dfk, dfv)
            elif ipk not in d["appearance"]:
                d["appearance"][ipk] = ipv
        if "tracks" in d["intimate_profile"] and "intercourse" in d["intimate_profile"]["tracks"]:
            d["appearance"].setdefault("predetermined_intercourse", d["intimate_profile"]["tracks"]["intercourse"])

    from mechanics.social.persona.intimacy.ledger import get_intimate_events
    char_ref = str(d.get("npc_id") or d["id"])
    evs = get_intimate_events(session_id, char_ref)
    if d.get("id") and str(d["id"]) != char_ref:
        seen_ev_ids = {e.get("id") for e in evs if e.get("id")}
        for extra_ev in get_intimate_events(session_id, str(d["id"])):
            if extra_ev.get("id") not in seen_ev_ids:
                evs.append(extra_ev)
    past_evs = [e for e in evs if e.get("event_origin") == "past_history" or e.get("turn_number") == 0]
    game_evs = [e for e in evs if e.get("event_origin") == "gameplay" or e.get("turn_number", 0) > 0]
    d["past_intimate_events"] = past_evs
    d["gameplay_intimate_events"] = game_evs

    if past_evs:
        past_entries = []
        for pev in past_evs:
            if pev.get("narrative_summary"):
                if pev["narrative_summary"] not in past_entries:
                    past_entries.append(pev["narrative_summary"])
            else:
                p_name = pev.get("partner_name", "Past Partner")
                p_role = pev.get("partner_role", "Former Acquaintance")
                act = pev.get("act_type", "intimacy")
                dir_val = pev.get("direction", "mutual")
                cnt = pev.get("count", 1)
                if act == "oral":
                    if dir_val == "give":
                        past_entries.append(f"Past History: performed oral on '{p_name}' ({p_role})")
                    elif dir_val == "receive":
                        past_entries.append(f"Past History: Received oral from '{p_name}' ({p_role})")
                    else:
                        past_entries.append(f"Past History: Mutual oral intimacy with '{p_name}' ({p_role})")
                elif act == "manual":
                    if dir_val == "give":
                        past_entries.append(f"Past History: Manually stimulated '{p_name}' ({p_role})")
                    elif dir_val == "receive":
                        past_entries.append(f"Past History: Received manual stimulation from '{p_name}' ({p_role})")
                    else:
                        past_entries.append(f"Past History: Mutual manual petting & foreplay with '{p_name}' ({p_role})")
                elif act == "anal":
                    if dir_val == "receive":
                        past_entries.append(f"Past History: Received anal intimacy from '{p_name}' ({p_role})")
                    else:
                        past_entries.append(f"Past History: Performed anal on '{p_name}' ({p_role})")
                elif act == "intercourse":
                    past_entries.append(f"Past History: Prior intercourse encounter ({cnt} times) with '{p_name}' ({p_role})")
                else:
                    past_entries.append(f"Past History: Prior {act} encounter ({cnt} times) with '{p_name}' ({p_role})")
        d["past_intimate_entries"] = past_entries
        d["past_intimate_history"] = "\n".join(past_entries)
    else:
        d["past_intimate_entries"] = []
        d["past_intimate_history"] = ""

    if game_evs:
        game_mems = []
        for ge in game_evs:
            s = ge.get("narrative_summary")
            if s and s not in game_mems:
                game_mems.append(s)
        if game_mems:
            d["shared_romantic_milestones"] = game_mems
            for gm in game_mems:
                if gm not in combined_mem:
                    combined_mem.append(gm)

    t = dict((d.get("intimate_profile") or {}).get("tracks") or {})
    if evs:
        from mechanics.social.persona.intimacy.ledger import compute_intimate_tracks_from_ledger
        from mechanics.social.persona.intimacy.logic import (
            merge_intercourse_states,
            merge_oral_states,
            merge_manual_states,
            merge_anal_states
        )
        ledger_tracks = compute_intimate_tracks_from_ledger(evs)
        t["intercourse"] = merge_intercourse_states(t.get("intercourse", "virgin"), ledger_tracks.get("intercourse", "virgin"))
        t["oral"] = merge_oral_states(t.get("oral", "inexperienced"), ledger_tracks.get("oral", "inexperienced"))
        t["manual"] = merge_manual_states(t.get("manual", "inexperienced"), ledger_tracks.get("manual", "inexperienced"))
        t["anal"] = merge_anal_states(t.get("anal", "inexperienced"), ledger_tracks.get("anal", "inexperienced"), gender=d.get("gender", ""))
        if isinstance(d.get("intimate_profile"), dict):
            d["intimate_profile"]["tracks"] = t
    d["intercourse_experience"] = t.get("intercourse", "virgin")
    d["oral_experience"] = t.get("oral", "inexperienced")
    d["manual_experience"] = t.get("manual", "inexperienced")
    d["anal_experience"] = t.get("anal", "inexperienced")
    if isinstance(d.get("appearance"), dict):
        d["appearance"]["intercourse_experience"] = d["intercourse_experience"]
        d["appearance"]["oral_experience"] = d["oral_experience"]
        d["appearance"]["manual_experience"] = d["manual_experience"]
        d["appearance"]["anal_experience"] = d["anal_experience"]
        d["appearance"]["predetermined_intercourse"] = (d.get("intimate_profile") or {}).get("predetermined_intercourse") or d["intercourse_experience"]
        disc = (d.get("intimate_profile") or {}).get("disclosure_flags") or {}
        for dfk, dfv in disc.items():
            if dfk not in d["appearance"]:
                d["appearance"][dfk] = dfv
        for dfk in ("intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed", "anal_revealed"):
            if (d.get("intimate_profile") or {}).get(dfk):
                d["appearance"][dfk] = (d.get("intimate_profile") or {})[dfk]
    if isinstance(d.get("appearance"), dict):
        d["appearance"]["intimate_memories"] = combined_mem
        d["appearance"]["shared_romantic_milestones"] = clean_intimate
        d["appearance"]["recent_memories"] = rel_hist
        d["appearance"]["rel_history"] = rel_hist

    if d.get("basic_info") and isinstance(d["basic_info"], dict) and d["basic_info"].get("description"):
        d["basic_info"]["description"] = persona.sanitize_npc_description(d["basic_info"]["description"], d.get("appearance"))

    try:
        d["relations"] = json.loads(d.get("relations_json") or "{}")
    except Exception:
        d["relations"] = {}

    if d.get("household_id"):
        import mechanics.social.genealogy as genealogy
        hh = get_household_by_id(d["household_id"])
        if hh:
            hydrated_hh = genealogy._hydrate_household_entity(hh, d, scen_key)
            d["relations"]["family"] = genealogy.build_family_tree_from_household(
                hydrated_hh,
                d.get("name", ""),
                scenario=scen_key,
                member_role=d.get("household_role"),
            )
            if hh.get("residence_location"):
                d["relations"]["residence_location"] = hh["residence_location"]
            d["household_id"] = hh["id"]
    elif not d.get("relations") or not d["relations"].get("family"):
        import mechanics.social.genealogy as genealogy
        d["relations"] = genealogy.ensure_contact_relations(d, session_id=session_id, scenario=scen_key)
        if session_id and d.get("id"):
            try:
                with get_conn() as conn:
                    conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(d["relations"]), d["id"]))
            except Exception:
                pass

    d["status_effects"] = (d.get("basic_info") or {}).get("status_effects") or []
    return d

def update_relationship_score(session_id: int, npc_id: str, delta_score: int, character_id: int = 0) -> dict | None:
    return upsert_contact(session_id=session_id, npc_id=npc_id, name=npc_id, character_id=character_id, delta_score=delta_score)

def _parse_faction_row(d: dict) -> dict:
    """Deserialize JSON columns of a raw factions row dict."""
    for col, default in (
        ("perks_json", "[]"),
        ("leadership_roster_json", "[]"),
        ("rival_faction_ids_json", "[]"),
        ("allied_faction_ids_json", "[]"),
    ):
        try:
            d[col.replace("_json", "")] = json.loads(d.get(col) or default)
        except Exception:
            d[col.replace("_json", "")] = []
    return d

def upsert_faction(session_id: int, name: str, delta_score: int = 0, notes: str = "",
                   perks: list = None, category: str = "", hq_location_id: str = "",
                   hierarchy_template: str = "", leadership_roster: list = None,
                   rival_faction_ids: list = None, allied_faction_ids: list = None) -> dict:
    name = (name or "").strip()
    if not name:
        return {}
    faction_id = name.lower().replace(" ", "_")
    now = time.time()
    perks_json = json.dumps(perks) if isinstance(perks, (list, tuple)) else (perks or "[]")
    roster_json = json.dumps(leadership_roster) if isinstance(leadership_roster, list) else None
    rivals_json = json.dumps(rival_faction_ids) if isinstance(rival_faction_ids, list) else None
    allies_json = json.dumps(allied_faction_ids) if isinstance(allied_faction_ids, list) else None

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM factions WHERE session_id=? AND faction_id=?",
            (session_id, faction_id)).fetchone()
        if existing:
            new_score = max(-100, min(100, existing["reputation_score"] + delta_score))
            # Preserve existing rich description if already present; only fill if previously empty
            final_notes = existing["notes"] if (existing["notes"] and existing["notes"].strip()) else (notes or "")
            conn.execute(
                """UPDATE factions SET reputation_score=?,
                                        perks_json=COALESCE(NULLIF(?, '[]'), perks_json),
                                        notes=?,
                                        category=COALESCE(NULLIF(?, ''), category),
                                        hq_location_id=COALESCE(NULLIF(?, ''), hq_location_id),
                                        hierarchy_template=COALESCE(NULLIF(?, ''), hierarchy_template),
                                        leadership_roster_json=COALESCE(NULLIF(?, '[]'), leadership_roster_json),
                                        rival_faction_ids_json=COALESCE(NULLIF(?, '[]'), rival_faction_ids_json),
                                        allied_faction_ids_json=COALESCE(NULLIF(?, '[]'), allied_faction_ids_json),
                                        updated_at=? WHERE id=?""",
                (new_score, perks_json, final_notes,
                 category or "", hq_location_id or "", hierarchy_template or "",
                 roster_json or "[]", rivals_json or "[]", allies_json or "[]",
                 now, existing["id"]))
            row = dict(existing)
            row["notes"] = final_notes
            row["reputation_score"] = new_score
            row["updated_at"] = now
            return db._parse_faction_row(row)
        else:
            initial_score = max(-100, min(100, delta_score))
            from mechanics.social.factions import guess_hierarchy_template
            cat = category or hierarchy_template or (guess_hierarchy_template(name) if name else "default")
            tmpl = hierarchy_template or category or cat
            cursor = conn.execute(
                """INSERT INTO factions (session_id, faction_id, name, reputation_score, perks_json, notes,
                                         category, hq_location_id, hierarchy_template,
                                         leadership_roster_json, rival_faction_ids_json, allied_faction_ids_json,
                                         created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, faction_id, name, initial_score, perks_json, notes or "",
                 cat, hq_location_id or "", tmpl,
                 roster_json or "[]", rivals_json or "[]", allies_json or "[]", now, now))
            row = {
                "id": cursor.lastrowid, "session_id": session_id, "faction_id": faction_id,
                "name": name, "reputation_score": initial_score, "perks": perks or [],
                "notes": notes, "category": cat, "hq_location_id": hq_location_id or "",
                "hierarchy_template": tmpl, "leadership_roster": leadership_roster or [],
                "rival_faction_ids": rival_faction_ids or [],
                "allied_faction_ids": allied_faction_ids or [],
                "created_at": now, "updated_at": now,
            }
            return row

def get_factions(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM factions WHERE session_id=? ORDER BY updated_at DESC",
            (session_id,)).fetchall()
    return [db._parse_faction_row(dict(r)) for r in rows]

def get_faction(session_id: int, faction_id_or_name: str) -> dict | None:
    fid = (faction_id_or_name or "").strip().lower().replace(" ", "_")
    with get_conn() as conn:
        r = conn.execute(
            "SELECT * FROM factions WHERE session_id=? AND faction_id=?",
            (session_id, fid)).fetchone()
    if not r:
        return None
    return db._parse_faction_row(dict(r))

def get_faction_by_hq(session_id: int, location_id: str) -> dict | None:
    """
    Return the faction whose HQ is at the given location_id, or None.
    Handles bare location IDs, primary names, and full 3-tiered strings without
    false-positive matching on generic parent zone names.
    """
    if not location_id:
        return None
    with get_conn() as conn:
        loc_clean = str(location_id).strip().lower().replace("->", "➔")
        loc_parts = [p.strip() for p in loc_clean.split("➔") if p.strip()]
        if not loc_parts:
            return None

        # Fast path: exact match on hq_location_id
        r = conn.execute(
            "SELECT * FROM factions WHERE session_id=? AND hq_location_id=?",
            (session_id, location_id)).fetchone()
        if r:
            return db._parse_faction_row(dict(r))

        rows = conn.execute(
            "SELECT * FROM factions WHERE session_id=?",
            (session_id,)).fetchall()
        if not rows:
            return None

        for row in rows:
            hq_raw = (row["hq_location_id"] or "").strip()
            if not hq_raw:
                continue
            hq_clean = hq_raw.lower().replace("->", "➔")
            hq_parts = [p.strip() for p in hq_clean.split("➔") if p.strip()]
            if not hq_parts:
                continue

            # 1. Exact string match
            if hq_clean == loc_clean:
                return db._parse_faction_row(dict(row))

            # 2. Multi-tier HQ (e.g. "Westlake Academy ➔ AV & Esports Lounge"):
            # Every segment of hq_parts must be present in loc_parts
            if len(hq_parts) > 1:
                if all(any(hq_seg == lp or (len(hq_seg) >= 4 and hq_seg in lp) for lp in loc_parts) for hq_seg in hq_parts):
                    return db._parse_faction_row(dict(row))
            else:
                # 3. Single-tier / Bare HQ (e.g. "Student Council Office", "Behind Gym Storage Sheds"):
                bare_hq = hq_parts[0]
                if len(bare_hq) >= 4:
                    for i, lp in enumerate(loc_parts):
                        if i == 0 and len(loc_parts) > 1:
                            if bare_hq == lp:
                                return db._parse_faction_row(dict(row))
                        else:
                            if bare_hq == lp or (len(bare_hq) >= 5 and bare_hq in lp) or (len(lp) >= 5 and lp in bare_hq):
                                return db._parse_faction_row(dict(row))

    return None

def update_faction_leadership_roster(session_id: int, faction_id: str, roster: list) -> bool:
    """Persist an updated leadership roster list for a faction."""
    fid = (faction_id or "").strip().lower().replace(" ", "_")
    now = time.time()
    with get_conn() as conn:
        r = conn.execute(
            "UPDATE factions SET leadership_roster_json=?, updated_at=? WHERE session_id=? AND faction_id=?",
            (json.dumps(roster), now, session_id, fid))
        return r.rowcount > 0

def set_character_faction_membership(character_id: int, faction_id: str, rank: int, title: str) -> bool:
    """Set the pledged faction, rank, and title for a character."""
    params = ((faction_id or ""), max(0, int(rank)), (title or ""), character_id)
    with get_conn() as conn:
        r = conn.execute(
            "UPDATE characters SET joined_faction_id=?, faction_rank=?, faction_title=? WHERE id=?",
            params)
        if r.rowcount == 0:
            r = conn.execute(
                "UPDATE characters SET joined_faction_id=?, faction_rank=?, faction_title=? WHERE user_id=? AND is_active=1",
                params)
        return r.rowcount > 0

def get_character_faction_membership(character_id: int) -> dict:
    """Return {joined_faction_id, faction_rank, faction_title} for a character."""
    with get_conn() as conn:
        r = conn.execute(
            "SELECT joined_faction_id, faction_rank, faction_title FROM characters WHERE id=?",
            (character_id,)).fetchone()
        if not r:
            r = conn.execute(
                "SELECT joined_faction_id, faction_rank, faction_title FROM characters WHERE user_id=? AND is_active=1",
                (character_id,)).fetchone()
    if not r:
        return {"joined_faction_id": "", "faction_rank": 0, "faction_title": ""}
    return {"joined_faction_id": r["joined_faction_id"] or "",
            "faction_rank": r["faction_rank"] or 0,
            "faction_title": r["faction_title"] or ""}

def set_faction_reinforcements_used(session_id: int, used: bool = True) -> None:
    """Mark/unmark the faction reinforcements perk as used for this session."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET faction_reinforcements_used=? WHERE id=?",
            (1 if used else 0, session_id))

def _resolve_phone_contact_keys(conn: sqlite3.Connection, session_id: int, contact_npc_id: str) -> tuple[str, list[str]]:
    raw = str(contact_npc_id or "").strip()
    raw_slug = raw.lower().replace(" ", "_")
    try:
        from mechanics.social.relationship_graph import canonical_person_key
        canon_slug = canonical_person_key(raw)
    except Exception:
        canon_slug = raw_slug

    keys: list[str] = []
    for k in (raw_slug, canon_slug):
        if k and k not in keys:
            keys.append(k)

    if session_id and raw:
        row = conn.execute(
            "SELECT npc_id, name FROM contacts WHERE session_id=? AND (lower(npc_id) IN (?, ?) OR lower(name)=?)",
            (session_id, raw_slug, canon_slug, raw.lower()),
        ).fetchone()
        if row:
            db_npc_id = str(row["npc_id"] or "").strip().lower().replace(" ", "_")
            db_name_slug = str(row["name"] or "").strip().lower().replace(" ", "_")
            for k in (db_npc_id, db_name_slug):
                if k and k not in keys:
                    keys.append(k)
            if db_npc_id:
                return db_npc_id, keys

    return (raw_slug or canon_slug), keys


def save_phone_message(session_id: int, contact_npc_id: str, sender: str, message: str, intent: str = "chat"):
    now = time.time()
    with get_conn() as conn:
        primary_key, _ = _resolve_phone_contact_keys(conn, session_id, contact_npc_id)
        conn.execute(
            "INSERT INTO phone_messages (session_id, contact_npc_id, sender, message, intent, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, primary_key, sender, message, intent, now)
        )

def get_phone_messages(session_id: int, contact_npc_id: str, limit: int = 15) -> list[dict]:
    with get_conn() as conn:
        _, keys = _resolve_phone_contact_keys(conn, session_id, contact_npc_id)
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"""SELECT * FROM (
                SELECT * FROM phone_messages
                WHERE session_id=? AND contact_npc_id IN ({placeholders})
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) ORDER BY timestamp ASC, id ASC""",
            (session_id, *keys, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def update_contact_in_person_timestamp(session_id: int, npc_name_or_id: str | dict, ts: float = None) -> None:
    """Updates the last_in_person_ts timestamp in contact basic_info to mark recent phone messages as acknowledged in person."""
    if not session_id or not npc_name_or_id:
        return
    if isinstance(npc_name_or_id, dict):
        npc_name_or_id = npc_name_or_id.get("name") or npc_name_or_id.get("npc_id") or ""
    npc_str = str(npc_name_or_id).strip()
    if not npc_str:
        return
    if ts is None:
        ts = time.time()
    clean_id = npc_str.lower().replace(" ", "_")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, basic_info_json FROM contacts WHERE session_id=? AND (npc_id=? OR lower(name)=?)",
            (session_id, clean_id, npc_str.lower())
        ).fetchone()
        if row:
            cid = row["id"]
            try:
                binfo = json.loads(row["basic_info_json"] or "{}")
            except Exception:
                binfo = {}
            binfo["last_in_person_ts"] = ts
            conn.execute(
                "UPDATE contacts SET basic_info_json=? WHERE id=?",
                (json.dumps(binfo), cid)
            )


def save_gossip_feed(session_id: int, posts: list[dict]):
    now = time.time()
    with get_conn() as conn:
        for p in posts:
            conn.execute(
                """INSERT INTO phone_gossip_feed (session_id, author_name, author_handle, content, tag, clue_hook, time_ago, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    p.get("author_name", "Anonymous"),
                    p.get("author_handle", "@anon"),
                    p.get("content", ""),
                    p.get("tag", ""),
                    p.get("clue_hook", ""),
                    p.get("time_ago", "Just now"),
                    now
                )
            )

def get_gossip_feed(session_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM phone_gossip_feed WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def _commitment_row_to_appointment_dict(r: sqlite3.Row | dict) -> dict:
    """Projects a normalized commitments_ledger row into the phone appointment dict view."""
    d = dict(r)
    try:
        participants = json.loads(d.get("participants_json") or "[]")
    except Exception:
        participants = []
    try:
        meta = json.loads(d.get("metadata_json") or "{}")
    except Exception:
        meta = {}

    npc_id = ""
    npc_name = ""
    for p in participants:
        if not isinstance(p, dict):
            continue
        pk = str(p.get("npc_id") or p.get("person_key") or "").strip()
        if pk and pk.lower() != "player" and not pk.lower().startswith("player:"):
            npc_id = pk.lower().replace(" ", "_")
            npc_name = str(p.get("name") or pk.replace("_", " ").title()).strip()
            break
    if not npc_id:
        tgt = str(d.get("target_entity") or "").strip()
        src = str(d.get("source_entity") or "").strip()
        cand = tgt if (tgt and tgt.lower() != "player") else src
        npc_id = cand.lower().replace(" ", "_")
        npc_name = cand.replace("_", " ").title()

    s_day = max(1, int(d.get("scheduled_day") or 1))
    s_min = max(0, int(d.get("start_minute") or 0))
    e_min = max(0, int(d.get("end_minute") if d.get("end_minute") is not None else 1439))
    raw_end_day = d.get("end_day")
    if raw_end_day is not None:
        e_day = max(s_day, int(raw_end_day))
    else:
        e_day = s_day + 1 if e_min < s_min else s_day

    created_min = (s_day - 1) * 1440 + s_min
    expiry_min = (e_day - 1) * 1440 + e_min

    raw_status = str(d.get("status") or "pending").strip().lower()
    if raw_status == "fulfilled":
        mapped_status = "completed"
    elif raw_status in ("flaked", "broken", "expired"):
        mapped_status = "stood_up"
    elif raw_status in ("arrived", "in_progress"):
        mapped_status = "arrived"
    elif raw_status == "cancelled":
        mapped_status = "cancelled"
    else:
        mapped_status = "pending"

    return {
        "id": d.get("id"),
        "commitment_id": d.get("id"),
        "session_id": d.get("session_id"),
        "npc_id": npc_id,
        "npc_name": npc_name,
        "rendezvous_location": d.get("target_location") or "",
        "target_node_id": d.get("target_node_id") or "",
        "topic": d.get("description") or d.get("title") or "",
        "is_confidential": 1 if d.get("is_confidential") else 0,
        "origin": d.get("origin") or "phone",
        "created_minute": created_min,
        "expiry_minute": expiry_min,
        "reminder_sent": 1 if meta.get("reminder_sent") else 0,
        "status": mapped_status,
        "ledger_status": raw_status,
        "scheduled_day": s_day,
        "end_day": e_day,
        "start_minute": s_min,
        "end_minute": e_min,
        "created_at": d.get("created_at") or 0.0,
    }


def save_phone_appointment(
    session_id: int,
    npc_id: str,
    npc_name: str,
    rendezvous_location: str,
    topic: str = "",
    is_confidential: bool = False,
    origin: str = "phone",
    created_minute: int = 0,
    expiry_minute: int = 0,
    expiry_minutes: int = 0,
    target_node_id: str = "",
) -> bool:
    """Upserts a pending meetup appointment into commitments_ledger. Returns True if saved."""
    if not rendezvous_location or not npc_id:
        return False
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    now = time.time()
    if created_minute == 0 and session_id:
        try:
            curr_day, curr_min, _ = db.get_session_time(session_id)
            created_minute = max(0, curr_day - 1) * 1440 + curr_min
        except Exception:
            pass
    if not expiry_minute and expiry_minutes > 0 and created_minute >= 0:
        expiry_minute = created_minute + int(expiry_minutes)
    elif not expiry_minute and created_minute:
        expiry_minute = created_minute + 45

    day_val = (created_minute // 1440) + 1 if created_minute > 0 else 1
    start_m = created_minute % 1440 if created_minute > 0 else 0
    end_day_val = (expiry_minute // 1440) + 1 if expiry_minute > 0 else day_val
    end_m = expiry_minute % 1440 if expiry_minute > 0 else (min(1439, start_m + 45) if created_minute > 0 else 1439)
    if end_day_val < day_val:
        end_day_val = day_val

    try:
        from mechanics.social.relationship_graph import canonical_person_key
        canon_npc_id = canonical_person_key(npc_id)
    except Exception:
        canon_npc_id = clean_npc_id

    with get_conn() as conn:
        # Supersede any prior pending/approaching 1-on-1 rendezvous with this exact NPC (e.g. meetup relocation)
        conn.execute(
            """UPDATE commitments_ledger
               SET status = 'cancelled', updated_at = ?
               WHERE session_id = ? AND commitment_type = 'rendezvous'
                 AND status IN ('pending', 'approaching')
                 AND (lower(target_entity) IN (?, ?) OR lower(source_entity) IN (?, ?))""",
            (now, session_id, clean_npc_id, canon_npc_id, clean_npc_id, canon_npc_id)
        )
        from mechanics.system.commitments_engine import create_rendezvous
        created = create_rendezvous(
            session_id=session_id,
            organizer="player",
            participants=[{"npc_id": clean_npc_id, "name": npc_name.strip()}],
            location=rendezvous_location.strip(),
            day=day_val,
            end_day=end_day_val,
            start_minute=start_m,
            end_minute=end_m,
            title=f"Meetup with {npc_name.strip()}",
            description=topic.strip() or f"Meet at {rendezvous_location.strip()}",
            origin=origin,
            node_id=target_node_id or None,
            is_confidential=is_confidential,
            conn=conn,
        )
        return bool(created)


def save_rendezvous_appointment(
    session_id: int,
    npc_id: str,
    npc_name: str,
    rendezvous_location: str,
    topic: str = "",
    is_confidential: bool = True,
    created_minute: int = 0,
    expiry_minute: int = 0,
    expiry_minutes: int = 0,
    target_node_id: str = "",
) -> bool:
    """Specialized helper for in-person dialogue rendezvous appointments."""
    return save_phone_appointment(
        session_id=session_id,
        npc_id=npc_id,
        npc_name=npc_name,
        rendezvous_location=rendezvous_location,
        topic=topic,
        is_confidential=is_confidential,
        origin="dialogue",
        created_minute=created_minute,
        expiry_minute=expiry_minute,
        expiry_minutes=expiry_minutes,
        target_node_id=target_node_id,
    )


def get_phone_appointments(session_id: int, status: str = "pending") -> list[dict]:
    """Returns all rendezvous appointments for a session matching the requested status."""
    st_clean = str(status or "pending").strip().lower()
    if st_clean == "completed":
        ledger_statuses = ("fulfilled",)
    elif st_clean in ("stood_up", "flaked", "missed"):
        ledger_statuses = ("flaked", "broken", "expired")
    elif st_clean == "arrived":
        ledger_statuses = ("arrived", "in_progress")
    elif st_clean == "cancelled":
        ledger_statuses = ("cancelled",)
    else:
        ledger_statuses = ("pending", "approaching")

    placeholders = ",".join("?" for _ in ledger_statuses)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM commitments_ledger
                WHERE session_id=? AND commitment_type='rendezvous'
                  AND status IN ({placeholders})
                ORDER BY created_at ASC, id ASC""",
            (session_id, *ledger_statuses)
        ).fetchall()
        return [_commitment_row_to_appointment_dict(r) for r in rows]


def get_active_rendezvous_appointments(session_id: int) -> list[dict]:
    """Returns all active rendezvous appointments (pending, approaching, arrived, in_progress) for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching', 'arrived', 'in_progress')
               ORDER BY created_at ASC, id ASC""",
            (session_id,)
        ).fetchall()
        return [_commitment_row_to_appointment_dict(r) for r in rows]


def update_phone_appointment_status(session_id: int, npc_id: str, status: str):
    """Updates a meetup appointment status in commitments_ledger."""
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    ledger_status = str(status or "").strip().lower()
    if ledger_status == "stood_up":
        ledger_status = "flaked"
    elif ledger_status == "completed":
        ledger_status = "fulfilled"
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status=?, updated_at=?
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND (lower(target_entity)=? OR lower(source_entity)=? OR lower(participants_json) LIKE ?)
                 AND status IN ('pending', 'approaching', 'arrived', 'in_progress', 'active')""",
            (ledger_status, now, session_id, clean_npc_id, clean_npc_id, f"%{clean_npc_id}%")
        )


def mark_rendezvous_reminder_sent(session_id: int, npc_id: str):
    """Marks in commitments_ledger.metadata_json that an SMS reminder has been sent."""
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    now = time.time()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, metadata_json FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')
                 AND (lower(target_entity)=? OR lower(source_entity)=? OR lower(participants_json) LIKE ?)""",
            (session_id, clean_npc_id, clean_npc_id, f"%{clean_npc_id}%")
        ).fetchall()
        for r in rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except Exception:
                meta = {}
            meta["reminder_sent"] = True
            conn.execute(
                "UPDATE commitments_ledger SET metadata_json=?, updated_at=? WHERE id=?",
                (json.dumps(meta), now, r["id"])
            )


def get_due_reminder_appointments(session_id: int, current_minute: int) -> list[dict]:
    """Finds pending rendezvous appointments waiting >= 30 minutes without a reminder sent."""
    if not current_minute or current_minute <= 0:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')""",
            (session_id,)
        ).fetchall()
        due = []
        for r in rows:
            appt = _commitment_row_to_appointment_dict(r)
            if appt.get("reminder_sent"):
                continue
            c_min = appt.get("created_minute", 0)
            if c_min > 0 and (current_minute - c_min) >= 30:
                due.append(appt)
        return due


def expire_overdue_appointments(session_id: int, current_minute: int) -> list[dict]:
    """Delegates overdue rendezvous expiration to commitments_ledger using monotonic absolute minutes."""
    if not current_minute or current_minute <= 0:
        return []
    curr_day = (int(current_minute) // 1440) + 1
    curr_min_of_day = int(current_minute) % 1440
    from mechanics.system.commitments_engine import flake_commitment
    expired_appts = []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')""",
            (session_id,)
        ).fetchall()
        overdue_rows = []
        for r in rows:
            appt = _commitment_row_to_appointment_dict(r)
            exp_min = appt.get("expiry_minute", 0)
            if exp_min > 0 and int(current_minute) >= exp_min:
                overdue_rows.append((r["id"], appt))

    for cid, appt in overdue_rows:
        flake_commitment(
            session_id,
            cid,
            flaked_entity="player",
            reason="deadline_elapsed",
        )
        appt["status"] = "stood_up"
        appt["ledger_status"] = "flaked"
        expired_appts.append(appt)
    return expired_appts

def save_school_roster(session_id: int, roster: list[dict]) -> bool:
    """Saves or updates a pre-generated school directory roster for a session."""
    if not roster or not session_id:
        return False
    now = time.time()
    with get_conn() as conn:
        for char in roster:
            npc_id = str(char.get("npc_id") or char.get("name", "")).strip().lower().replace(" ", "_")
            if not npc_id:
                continue
            conn.execute(
                """INSERT INTO school_directory
                   (session_id, npc_id, name, gender, race, role, grade, club, clique, primary_facility, secondary_facility, sibling_name, personality_summary, is_hydrated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, npc_id) DO UPDATE SET
                   name=excluded.name,
                   gender=COALESCE(NULLIF(excluded.gender, ''), school_directory.gender),
                   race=COALESCE(NULLIF(excluded.race, ''), school_directory.race),
                   role=excluded.role,
                   grade=excluded.grade,
                   club=excluded.club,
                   clique=excluded.clique,
                   primary_facility=excluded.primary_facility,
                   secondary_facility=excluded.secondary_facility,
                   sibling_name=excluded.sibling_name,
                   personality_summary=excluded.personality_summary""",
                (
                    session_id,
                    npc_id,
                    char.get("name", "").strip(),
                    char.get("gender", "").strip(),
                    char.get("race", "").strip(),
                    char.get("role", "").strip(),
                    char.get("grade", "Student").strip(),
                    char.get("club", "").strip(),
                    char.get("clique", "").strip(),
                    char.get("primary_facility", "").strip(),
                    char.get("secondary_facility", "").strip(),
                    char.get("sibling_name", "").strip(),
                    char.get("personality_summary", "").strip(),
                    int(bool(char.get("is_hydrated", 0))),
                    now
                )
            )
    return True

def get_school_roster(session_id: int) -> list[dict]:
    """Returns the full school directory roster for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM school_directory WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_anomalous_agent_roster(session_id: int) -> list[dict]:
    """Returns the anomalous special agents roster for a session if present."""
    if not session_id:
        return []
    sess = db.get_session(session_id)
    if not sess:
        return []
    roster = sess.get("anomalous_agent_roster")
    if not isinstance(roster, list) and isinstance(sess.get("extra"), dict):
        roster = sess["extra"].get("anomalous_agent_roster")
    return list(roster) if isinstance(roster, list) else []

def get_school_characters_by_facility(session_id: int, location_str: str, limit: int = 3, allow_off_campus: bool = False) -> list[dict]:
    """
    Returns characters stationed at or frequenting the specified facility/room.
    Matches against primary_facility, secondary_facility, or location leaf tokens.
    If allow_off_campus is True, also permits matching recognized town youth hangout nodes
    during extracurricular or weekend hours.
    """
    if not location_str or not session_id:
        return []

    loc_clean = str(location_str).strip()
    loc_parts = [p.strip() for p in re.split(r'➔|->|>|→', loc_clean) if p.strip()]
    leaf = loc_parts[-1] if loc_parts else loc_clean
    primary_place = loc_parts[1] if len(loc_parts) > 1 else leaf

    parsed = None
    is_campus = True
    try:
        from mechanics.world.locations import (
            parse_tiered_location,
            get_session_school_name,
            get_session_athletics_complex_name,
            get_session_student_commons_name,
            get_session_cultural_arts_name,
            get_session_abandoned_campus_name,
            is_school_scenario
        )
        sess = db.get_session(session_id)
        scen = sess.get("scenario", "high_school_drama") if sess else "high_school_drama"
        if is_school_scenario(scen):
            campus_zones = [
                get_session_school_name(session_id, scen),
                get_session_athletics_complex_name(session_id, scen),
                get_session_student_commons_name(session_id, scen),
                get_session_cultural_arts_name(session_id, scen),
                get_session_abandoned_campus_name(session_id, scen)
            ]
            parsed = parse_tiered_location(loc_clean, scen, session_id=session_id)
            loc_zone = parsed[0] if parsed else (loc_parts[0] if loc_parts else "")
            is_campus = any(cz and (cz.lower() in loc_zone.lower() or loc_zone.lower() in cz.lower()) for cz in campus_zones) or any(k in loc_zone.lower() for k in ("academy", "school", "athletics", "commons", "annex", "old campus"))
            if not is_campus and not allow_off_campus:
                return []
    except Exception:
        pass

    if not is_campus and allow_off_campus:
        is_youth_hangout = any(k in loc_clean.lower() for k in (
            "arcade", "game center", "velvet mug", "cafe", "coffee", "park", "pier",
            "beach", "convenience store", "karaoke", "lookout", "lake"
        ))
        if not is_youth_hangout:
            return []
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM school_directory
                   WHERE session_id=? AND lower(grade) != 'faculty' AND lower(role) NOT LIKE '%teacher%' AND lower(role) NOT LIKE '%staff%'
                   ORDER BY is_hydrated ASC, id ASC LIMIT ?""",
                (session_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    cand_places = []
    if parsed:
        if parsed[1] and parsed[1] not in ("Main Area", ""):
            cand_places.append(parsed[1])
        if parsed[2] and parsed[2] not in ("Main Area", ""):
            cand_places.append(parsed[2])
    cand_places.append(leaf)
    if primary_place != leaf:
        cand_places.append(primary_place)

    if any(k in leaf.lower() for k in ("classroom", "homeroom", "class ")) and "empty" not in leaf.lower():
        try:
            from mechanics.world.locations import get_session_classroom_name
            c_name = get_session_classroom_name(session_id, scen if 'scen' in locals() else "high_school_drama")
            if c_name:
                cand_places.append(c_name)
        except Exception:
            pass
        cand_places.append("Homeroom")

    for w in re.findall(r'[A-Za-z]+', leaf):
        if len(w) >= 4 and w.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court'):
            if w.lower() == 'classroom' and 'empty' not in leaf.lower():
                continue
            cand_places.append(w)
    for w in re.findall(r'[A-Za-z]+', primary_place):
        if len(w) >= 3 and w.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court', 'and', 'the'):
            cand_places.append(w)

    with get_conn() as conn:
        for cp in cand_places:
            if not cp or len(cp) < 3:
                continue
            kw_match = ""
            for tok in re.findall(r'[A-Za-z]+', cp):
                if len(tok) >= 4 and tok.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court', 'and', 'the'):
                    kw_match = tok.lower()
                    break

            rows = conn.execute(
                """SELECT * FROM school_directory
                   WHERE session_id=? AND (
                       primary_facility = ? OR
                       primary_facility LIKE ? OR
                       secondary_facility = ? OR
                       secondary_facility LIKE ?
                   )
                   ORDER BY 
                       CASE 
                           WHEN ? != '' AND lower(role) LIKE '%' || ? || '%' THEN 0 
                           WHEN lower(role) LIKE '%teacher%' OR lower(role) LIKE '%faculty%' OR lower(role) LIKE '%coach%' OR lower(role) LIKE '%nurse%' OR lower(role) LIKE '%librarian%' OR lower(role) LIKE '%instructor%' THEN 1 
                           ELSE 2 
                       END ASC,
                       is_hydrated ASC, id ASC LIMIT ?""",
                (session_id, cp, f"%{cp}%", cp, f"%{cp}%", kw_match, kw_match, limit)
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]

        return []

def mark_school_character_hydrated(session_id: int, npc_id: str) -> bool:
    """Marks a character in the school directory as hydrated (active in contacts)."""
    clean_id = str(npc_id).strip().lower().replace(" ", "_")
    with get_conn() as conn:
        conn.execute(
            "UPDATE school_directory SET is_hydrated=1 WHERE session_id=? AND npc_id=?",
            (session_id, clean_id)
        )
    return True


_active_resolving_contacts = set()


def get_phone_daily_limits(session_id: int, npc_id: str, current_day: int) -> dict:
    """Returns structured daily action allowances, usage counts, and status for a contact on current_day."""
    clean_npc_id = str(npc_id).strip().lower().replace(" ", "_")
    raw_npc_low = str(npc_id).strip().lower()
    limits = {
        "chat": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "flirt": {"used": 0, "max": 3, "locked": False, "history": [], "last_outcome": "", "over_limit_count": 0},
        "meetup": {"used": 0, "max": 1, "locked": False, "status": "available", "relocations_left": 0, "relocations_used": 0, "last_outcome": "", "over_limit_count": 0},
        "photo": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "spicy": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "rumor": {"used": 0, "max": 1, "locked": False, "over_limit_count": 0},
    }
    with get_conn() as conn:
        c_row = conn.execute(
            """SELECT relationship_score FROM contacts
               WHERE session_id=? AND (lower(npc_id)=? OR lower(name)=? OR lower(name)=?)
               ORDER BY relationship_score DESC LIMIT 1""",
            (session_id, clean_npc_id, raw_npc_low, clean_npc_id.replace("_", " ")),
        ).fetchone()
        contact_score = int(c_row["relationship_score"] or 0) if c_row else 0
        max_chat = 5 if contact_score >= 100 else 3
        limits["chat"]["max"] = max_chat

        # Check active rendezvous commitments for this NPC
        appt_row = conn.execute(
            """SELECT target_location AS rendezvous_location, status FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')
                 AND (lower(target_entity)=? OR lower(source_entity)=? OR lower(participants_json) LIKE ?)
               ORDER BY id DESC LIMIT 1""",
            (session_id, clean_npc_id, clean_npc_id, f"%{clean_npc_id}%")
        ).fetchone()
        has_active_appt = bool(appt_row)

        try:
            rows = conn.execute(
                "SELECT intent, attempt_count, success_count, over_limit_count, last_outcome, metadata_json "
                "FROM phone_daily_interactions WHERE session_id=? AND npc_id=? AND current_day=?",
                (session_id, clean_npc_id, int(current_day))
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table: phone_daily_interactions" in str(e).lower():
                conn.execute("""CREATE TABLE IF NOT EXISTS phone_daily_interactions (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id          INTEGER NOT NULL,
                    npc_id              TEXT NOT NULL,
                    current_day         INTEGER NOT NULL,
                    intent              TEXT NOT NULL,
                    attempt_count       INTEGER DEFAULT 0,
                    success_count       INTEGER DEFAULT 0,
                    over_limit_count    INTEGER DEFAULT 0,
                    last_outcome        TEXT DEFAULT '',
                    metadata_json       TEXT DEFAULT '{}',
                    updated_at          REAL NOT NULL,
                    UNIQUE(session_id, npc_id, current_day, intent)
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_daily_lookup ON phone_daily_interactions(session_id, npc_id, current_day)")
                rows = []
            else:
                raise

        for r in rows:
            intent = r["intent"]
            used = int(r["attempt_count"] or 0)
            over_limit = int(r["over_limit_count"] or 0)
            outcome = r["last_outcome"] or ""
            meta = {}
            if r["metadata_json"]:
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    meta = {}

            if intent == "flirt":
                limits["flirt"]["used"] = used
                limits["flirt"]["locked"] = used >= 3
                limits["flirt"]["history"] = meta.get("history", [])
                limits["flirt"]["last_outcome"] = outcome
                limits["flirt"]["over_limit_count"] = over_limit
            elif intent == "meetup":
                limits["meetup"]["used"] = used
                relocations_used = meta.get("relocations_used", 0)
                limits["meetup"]["relocations_used"] = relocations_used
                if has_active_appt:
                    limits["meetup"]["status"] = "accepted"
                    limits["meetup"]["relocations_left"] = max(0, 2 - relocations_used)
                    limits["meetup"]["locked"] = relocations_used >= 2
                    limits["meetup"]["rendezvous_location"] = appt_row["rendezvous_location"]
                else:
                    limits["meetup"]["status"] = "failed" if used >= 1 else "available"
                    limits["meetup"]["relocations_left"] = 0
                    limits["meetup"]["locked"] = used >= 1
                limits["meetup"]["last_outcome"] = outcome
                limits["meetup"]["over_limit_count"] = over_limit
            elif intent in ("photo", "photo_ask", "photo_send"):
                limits["photo"]["used"] += used
                limits["photo"]["over_limit_count"] = limits["photo"].get("over_limit_count", 0) + over_limit
            elif intent in ("spicy", "spicy_ask", "spicy_send", "nsfw_photo", "nsfw_video"):
                limits["spicy"]["used"] += used
                limits["spicy"]["over_limit_count"] = limits["spicy"].get("over_limit_count", 0) + over_limit
            elif intent in ("rumor", "intel_rumor", "intel"):
                limits["rumor"]["used"] += used
                limits["rumor"]["locked"] = limits["rumor"]["used"] >= 1
                limits["rumor"]["over_limit_count"] += over_limit
            elif intent in ("chat", "custom"):
                limits["chat"]["used"] += used
                limits["chat"]["over_limit_count"] += over_limit

        limits["chat"]["locked"] = limits["chat"]["used"] >= limits["chat"]["max"]
        limits["photo"]["locked"] = limits["photo"]["used"] >= 3
        limits["spicy"]["locked"] = limits["spicy"]["used"] >= 3
        limits["flirt"]["locked"] = limits["flirt"]["used"] >= 3
        limits["rumor"]["locked"] = limits["rumor"]["used"] >= 1

        if has_active_appt and limits["meetup"]["status"] != "accepted":
            limits["meetup"]["status"] = "accepted"
            relocations_used = limits["meetup"].get("relocations_used", 0)
            limits["meetup"]["relocations_left"] = max(0, 2 - relocations_used)
            limits["meetup"]["locked"] = relocations_used >= 2
            limits["meetup"]["rendezvous_location"] = appt_row["rendezvous_location"]

    return limits


def record_phone_daily_interaction(session_id: int, npc_id: str, current_day: int, intent: str, outcome: str, metadata: dict = None, is_over_limit: bool = False) -> dict:
    """Atomically records or updates a daily interaction attempt."""
    clean_npc_id = str(npc_id).strip().lower().replace(" ", "_")
    norm_intent = intent
    if intent in ("photo_ask", "photo_send"):
        norm_intent = "photo"
    elif intent in ("spicy_ask", "spicy_send", "nsfw_photo", "nsfw_video"):
        norm_intent = "spicy"
    elif intent in ("intel_rumor", "intel"):
        norm_intent = "rumor"
    elif intent in ("chat", "custom"):
        norm_intent = "chat"

    with get_conn() as conn:
        try:
            row = conn.execute(
                "SELECT attempt_count, success_count, over_limit_count, metadata_json FROM phone_daily_interactions "
                "WHERE session_id=? AND npc_id=? AND current_day=? AND intent=?",
                (session_id, clean_npc_id, int(current_day), norm_intent)
            ).fetchone()
        except sqlite3.OperationalError as e:
            if "no such table: phone_daily_interactions" in str(e).lower():
                conn.execute("""CREATE TABLE IF NOT EXISTS phone_daily_interactions (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id          INTEGER NOT NULL,
                    npc_id              TEXT NOT NULL,
                    current_day         INTEGER NOT NULL,
                    intent              TEXT NOT NULL,
                    attempt_count       INTEGER DEFAULT 0,
                    success_count       INTEGER DEFAULT 0,
                    over_limit_count    INTEGER DEFAULT 0,
                    last_outcome        TEXT DEFAULT '',
                    metadata_json       TEXT DEFAULT '{}',
                    updated_at          REAL NOT NULL,
                    UNIQUE(session_id, npc_id, current_day, intent)
                )""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_phone_daily_lookup ON phone_daily_interactions(session_id, npc_id, current_day)")
                row = None
            else:
                raise

        now = time.time()
        succeeded = outcome in ("success", "crit_success")

        if row:
            curr_attempts = int(row["attempt_count"] or 0)
            curr_successes = int(row["success_count"] or 0)
            curr_over = int(row["over_limit_count"] or 0)
            existing_meta = {}
            if row["metadata_json"]:
                try:
                    existing_meta = json.loads(row["metadata_json"])
                except Exception:
                    existing_meta = {}

            if is_over_limit:
                new_over = curr_over + 1
                new_attempts = curr_attempts
                new_successes = curr_successes
            else:
                new_over = curr_over
                new_attempts = curr_attempts + 1
                new_successes = curr_successes + (1 if succeeded else 0)

            if metadata:
                existing_meta.update(metadata)

            conn.execute(
                """UPDATE phone_daily_interactions
                   SET attempt_count=?, success_count=?, over_limit_count=?, last_outcome=?, metadata_json=?, updated_at=?
                   WHERE session_id=? AND npc_id=? AND current_day=? AND intent=?""",
                (new_attempts, new_successes, new_over, outcome, json.dumps(existing_meta), now,
                 session_id, clean_npc_id, int(current_day), norm_intent)
            )
        else:
            new_attempts = 0 if is_over_limit else 1
            new_successes = 1 if (succeeded and not is_over_limit) else 0
            new_over = 1 if is_over_limit else 0
            meta_json = json.dumps(metadata or {})
            conn.execute(
                """INSERT INTO phone_daily_interactions
                   (session_id, npc_id, current_day, intent, attempt_count, success_count, over_limit_count, last_outcome, metadata_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, clean_npc_id, int(current_day), norm_intent, new_attempts, new_successes, new_over, outcome, meta_json, now)
            )

    return get_phone_daily_limits(session_id, clean_npc_id, current_day)


