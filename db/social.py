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
        row = conn.execute("SELECT party_recruit_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_recruit_cooldowns_json"]:
            return 0
        try:
            cds = json.loads(row["party_recruit_cooldowns_json"])
            return int(cds.get(str(npc_name).strip().lower(), 0))
        except Exception:
            return 0

def set_recruitment_cooldown(session_id: int, npc_name: str, turns: int = 3):
    with get_conn() as conn:
        row = conn.execute("SELECT party_recruit_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        cds = {}
        if row and row["party_recruit_cooldowns_json"]:
            try:
                cds = json.loads(row["party_recruit_cooldowns_json"])
            except Exception:
                cds = {}
        cds[str(npc_name).strip().lower()] = turns
        conn.execute("UPDATE sessions SET party_recruit_cooldowns_json=?, updated_at=? WHERE id=?",
                     (json.dumps(cds), time.time(), session_id))

def decrement_recruitment_cooldowns(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT party_recruit_cooldowns_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_recruit_cooldowns_json"]:
            return
        try:
            cds = json.loads(row["party_recruit_cooldowns_json"])
        except Exception:
            return
        new_cds = {k: v - 1 for k, v in cds.items() if v > 1}
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
            if name_clean.lower() in sent.lower():
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
            """SELECT role, grade, club, clique, personality_summary
               FROM school_directory
               WHERE session_id=? AND (lower(name)=? OR npc_id=?)
               LIMIT 1""",
            (session_id, name_low, npc_slug)
        ).fetchone()
        if not sd_row and " " not in name_clean:
            cand_rows = conn.execute(
                """SELECT role, grade, club, clique, personality_summary
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
            if _is_empty_info_val(info.get("description")) and not _is_empty_info_val(sd_row["personality_summary"]):
                info["description"] = sd_row["personality_summary"].strip()
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
            "coach", "athletic director", "advisor", "parent", "detective", "police", "officer", "vendor"
        )
        is_faculty_or_adult = any(kw in role_lower for kw in faculty_keywords) or (
            str(info.get("grade")).strip().lower() == "faculty"
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
                   new_memory: str = None, narrative_text: str = "") -> dict:
    import mechanics.social.persona as persona
    import namegen

    # Reject invalid / corrupted entity names from LLM reasoning leaks
    if not namegen.is_valid_entity_name(name) and not namegen.is_valid_entity_name(npc_id):
        return {}

    # Code-level guarantee: named characters/contacts must have a proper personal name
    raw_identifier = name or npc_id or ""
    if namegen.is_generic_role_name(name) or namegen.is_generic_role_name(npc_id):
        role_title = name if namegen.is_generic_role_name(name) else npc_id
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

        sess = db.get_session(session_id)
        scen = sess.get("scenario", "fantasy") if sess else "fantasy"
        clean_name = matched_name or namegen.generate_person_name(scen, gender=gender)

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
    if not relationships.is_contact_eligible(name=name, role=n_role, description=n_desc, scenario=scen):
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
            current_score = existing["relationship_score"] + delta_score
            current_score = max(-100, min(100, current_score))

            raw_cur_info = json.loads(existing["basic_info_json"] or "{}")
            cur_info = _merge_basic_info_safely(raw_cur_info, basic_info)
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
            if existing_dict.get("appearance_json"):
                try:
                    old_app = json.loads(existing_dict.get("appearance_json") or "{}")
                    if isinstance(old_app.get("intimate_memories"), list):
                        for m in old_app["intimate_memories"]:
                            m_str = str(m).strip() if m else ""
                            if m_str and m_str not in cur_memories:
                                cur_memories.append(m_str)
                except Exception:
                    pass

            if appearance and isinstance(appearance, dict) and isinstance(appearance.get("intimate_memories"), list):
                for m in appearance["intimate_memories"]:
                    m_str = str(m).strip() if m else ""
                    if m_str and m_str not in cur_memories:
                        cur_memories.append(m_str)

            merged_traits_in = cur_raw_traits + (new_traits or [])
            merged_prefs_in = cur_raw_prefs + (new_preferences or [])
            clean_traits, clean_prefs = persona.split_traits_and_preferences(
                merged_traits_in,
                merged_prefs_in,
                role=cur_info.get("role", ""),
                race=cur_race,
                seed_str=f"{final_name}_{cur_info.get('description', '')}"
            )
            
            if new_memory and isinstance(new_memory, str) and new_memory.strip():
                m_str = new_memory.strip()
                if m_str not in cur_memories:
                    cur_memories.append(m_str)
                    if len(cur_memories) > 100:
                        cur_memories = cur_memories[-100:]

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
            from mechanics.social.persona.intimacy.appearance import extract_appearance_from_text
            extracted_app = extract_appearance_from_text(f"{cur_info.get('description', '')} {narrative_text}", name=final_name)
            if extracted_app:
                cur_app = persona.merge_appearance_safely(cur_app, extracted_app)

            if cur_memories:
                cur_app["intimate_memories"] = list(cur_memories)
            if appearance and isinstance(appearance, dict):
                cur_app = persona.merge_appearance_safely(cur_app, appearance)
            cur_app["intimate_memories"] = list(cur_memories)
            cur_app = persona.enforce_intimacy_safeguard_invariants(cur_app)

            if not cur_gender:
                try:
                    cur_gender = persona.infer_contact_gender({"name": final_name, "basic_info": cur_info, "appearance": cur_app}) or ""
                except Exception:
                    pass

            conn.execute(
                """UPDATE contacts SET name=?, basic_info_json=?, relationship_score=?,
                                       track=?, unlocked_traits_json=?, preferences_json=?, race=?, gender=?, appearance_json=?, intimate_memories_json=?, updated_at=?
                    WHERE id=?""",
                (final_name, json.dumps(cur_info), current_score, cur_track, json.dumps(clean_traits), json.dumps(clean_prefs), cur_race, cur_gender, json.dumps(cur_app), json.dumps(cur_memories), now, existing["id"])
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
                "appearance": cur_app,
                "intimate_memories": cur_memories,
                "updated_at": now
            }
        else:
            initial_score = max(-100, min(100, delta_score))
            info = _merge_basic_info_safely({}, basic_info)
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
            if isinstance(app_dict.get("intimate_memories"), list):
                for m in app_dict["intimate_memories"]:
                    m_str = str(m).strip() if m else ""
                    if m_str and m_str not in cur_memories:
                        cur_memories.append(m_str)

            if new_memory and isinstance(new_memory, str) and new_memory.strip():
                m_str = new_memory.strip()
                if m_str not in cur_memories:
                    cur_memories.append(m_str)
                    if len(cur_memories) > 100:
                        cur_memories = cur_memories[-100:]

            from mechanics.social.persona.intimacy.appearance import extract_appearance_from_text
            extracted_app = extract_appearance_from_text(f"{info.get('description', '')} {narrative_text}", name=name)
            if extracted_app:
                app_dict = persona.merge_appearance_safely(app_dict, extracted_app)
            app_dict["intimate_memories"] = list(cur_memories)
            app_dict = persona.enforce_intimacy_safeguard_invariants(app_dict)
            if not cur_gender:
                try:
                    cur_gender = persona.infer_contact_gender({"name": name, "basic_info": info, "appearance": app_dict}) or ""
                except Exception:
                    pass

            cursor = conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, basic_info_json,
                                          relationship_score, track, unlocked_traits_json, preferences_json, race, gender, appearance_json, intimate_memories_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, character_id, npc_id, name, json.dumps(info), initial_score,
                 cur_track, json.dumps(clean_traits), json.dumps(clean_prefs), cur_race, cur_gender, json.dumps(app_dict), json.dumps(cur_memories), now, now)
            )
            return {
                "id": cursor.lastrowid,
                "session_id": session_id,
                "character_id": character_id,
                "npc_id": npc_id,
                "name": name,
                "basic_info": info,
                "relationship_score": initial_score,
                "track": cur_track,
                "unlocked_traits": clean_traits,
                "preferences": clean_prefs,
                "race": cur_race,
                "gender": cur_gender,
                "appearance": app_dict,
                "intimate_memories": cur_memories,
                "created_at": now,
                "updated_at": now
            }

def ensure_scene_npcs_in_contacts(session_id: int, character_id: int = 0):
    """Ensure all non-hostile present scene NPCs are registered as contacts in this session."""
    sess = db.get_session(session_id)
    if not sess:
        return
    scen_key = sess.get("scenario", "fantasy")
    import scenario_data
    if not (scenario_data.is_mechanic_enabled(scen_key, "contact_list") or scenario_data.is_mechanic_enabled(scen_key, "relationship_meter")):
        return

    enemies = sess.get("nearby_enemies", [])
    import game_engine
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
    for npc in (sess.get("current_npcs") or []):
        n_name = game_engine._get_npc_name(npc)
        if not n_name or n_name.lower() in enemy_names or n_name.lower() in party_char_names:
            continue

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

        b_info = {}
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

            d["intimate_memories"] = combined_mem
            if isinstance(d.get("appearance"), dict):
                d["appearance"]["intimate_memories"] = combined_mem

            try:
                d["relations"] = json.loads(d.get("relations_json") or "{}")
            except Exception:
                d["relations"] = {}

            contacts.append(d)

    if resolve_relations:
        for d in contacts:
            if not d.get("relations") or not d["relations"].get("family"):
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
    clamped_score = max(-100, min(100, int(new_score)))
    now = time.time()
    npc_clean_id = str(npc_id or "").strip().lower().replace(" ", "_")
    npc_raw_name = str(npc_id or "").strip().lower()
    character_id = int(character_id or 0)
    with get_conn() as conn:
        conn.execute(
            """UPDATE contacts SET relationship_score=?, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (clamped_score, now, session_id, character_id, character_id, npc_clean_id, npc_raw_name, npc_raw_name, npc_clean_id)
        )

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
        cursor = conn.execute(
            """UPDATE contacts SET track=?, updated_at=?
               WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
               AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
            (norm_track, now, session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id)
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

    d["intimate_memories"] = combined_mem
    if isinstance(d.get("appearance"), dict):
        d["appearance"]["intimate_memories"] = combined_mem

    if d.get("basic_info") and isinstance(d["basic_info"], dict) and d["basic_info"].get("description"):
        d["basic_info"]["description"] = persona.sanitize_npc_description(d["basic_info"]["description"], d.get("appearance"))

    try:
        d["relations"] = json.loads(d.get("relations_json") or "{}")
    except Exception:
        d["relations"] = {}

    if not d.get("relations") or not d["relations"].get("family"):
        import mechanics.social.genealogy as genealogy
        d["relations"] = genealogy.ensure_contact_relations(d, session_id=session_id, scenario=scen_key)
        if session_id and d.get("id"):
            try:
                with get_conn() as conn:
                    conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(d["relations"]), d["id"]))
            except Exception:
                pass

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

def save_phone_message(session_id: int, contact_npc_id: str, sender: str, message: str, intent: str = "chat"):
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO phone_messages (session_id, contact_npc_id, sender, message, intent, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, contact_npc_id.strip().lower().replace(" ", "_"), sender, message, intent, now)
        )

def get_phone_messages(session_id: int, contact_npc_id: str, limit: int = 15) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM (
                SELECT * FROM phone_messages
                WHERE session_id=? AND contact_npc_id=?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) ORDER BY timestamp ASC, id ASC""",
            (session_id, contact_npc_id.strip().lower().replace(" ", "_"), limit)
        ).fetchall()
        return [dict(r) for r in rows]

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

def save_phone_appointment(session_id: int, npc_id: str, npc_name: str, rendezvous_location: str) -> bool:
    """Upserts a pending meetup appointment set via DM. Returns True if saved."""
    if not rendezvous_location or not npc_id:
        return False
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO phone_appointments (session_id, npc_id, npc_name, rendezvous_location, status, created_at)
               VALUES (?, ?, ?, ?, 'pending', ?)
               ON CONFLICT(session_id, npc_id) DO UPDATE SET
               rendezvous_location=excluded.rendezvous_location,
               status='pending',
               created_at=excluded.created_at""",
            (session_id, clean_npc_id, npc_name.strip(), rendezvous_location.strip(), now)
        )
    return True

def get_phone_appointments(session_id: int, status: str = "pending") -> list[dict]:
    """Returns all appointments for a session with the given status."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM phone_appointments WHERE session_id=? AND status=? ORDER BY created_at ASC",
            (session_id, status)
        ).fetchall()
        return [dict(r) for r in rows]

def update_phone_appointment_status(session_id: int, npc_id: str, status: str):
    """Updates a meetup appointment status to 'arrived' or 'cancelled'."""
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    with get_conn() as conn:
        conn.execute(
            "UPDATE phone_appointments SET status=? WHERE session_id=? AND npc_id=?",
            (status, session_id, clean_npc_id)
        )

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
                   (session_id, npc_id, name, role, grade, club, clique, primary_facility, secondary_facility, sibling_name, personality_summary, is_hydrated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, npc_id) DO UPDATE SET
                   name=excluded.name,
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

def get_school_characters_by_facility(session_id: int, location_str: str, limit: int = 3) -> list[dict]:
    """
    Returns characters stationed at or frequenting the specified facility/room.
    Matches against primary_facility, secondary_facility, or location leaf tokens.
    """
    if not location_str or not session_id:
        return []

    loc_clean = str(location_str).strip()
    loc_parts = [p.strip() for p in re.split(r'➔|->|>', loc_clean) if p.strip()]
    leaf = loc_parts[-1] if loc_parts else loc_clean
    primary_place = loc_parts[1] if len(loc_parts) > 1 else leaf

    parsed = None
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
            if not is_campus:
                return []
    except Exception:
        pass

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
            rows = conn.execute(
                """SELECT * FROM school_directory
                   WHERE session_id=? AND (
                       primary_facility = ? OR
                       primary_facility LIKE ? OR
                       secondary_facility = ? OR
                       secondary_facility LIKE ?
                   )
                   ORDER BY is_hydrated ASC, id ASC LIMIT ?""",
                (session_id, cp, f"%{cp}%", cp, f"%{cp}%", limit)
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

