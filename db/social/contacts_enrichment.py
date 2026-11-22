from __future__ import annotations

import hashlib
import json
import random
import re
from ..core import (_find_anomalous_agent_entry)

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

    # 0. Extract role from parenthetical in description if role is missing or generic (e.g. "Eline Vos (Dispatch Operator) encountered at...")
    if char_text:
        m_paren = re.search(rf"\b{re.escape(name_clean)}\s*\(([^)]{{3,45}})\)", char_text, flags=re.IGNORECASE)
        if m_paren:
            p_cand = m_paren.group(1).strip()
            if p_cand and not any(k in p_cand.lower() for k in ("née", "nee", "formerly", "tier ", "freshman", "sophomore", "junior", "senior")):
                out["role"] = p_cand

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
    narrative_text: str = "",
    preloaded_enrichment: dict | None = None,
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
        sd_row = None
        if preloaded_enrichment is not None:
            sd_row = (
                (preloaded_enrichment.get("school_by_name") or {}).get(name_low)
                or (preloaded_enrichment.get("school_by_id") or {}).get(npc_slug)
            )
            if not sd_row and " " not in name_clean:
                cand_rows = []
                for sr in (preloaded_enrichment.get("school_rows") or []):
                    s_name = str(sr["name"] or "").strip().lower()
                    s_nid = str(sr["npc_id"] or "").strip().lower()
                    if (
                        s_name.startswith(f"{name_low} ")
                        or s_name.endswith(f" {name_low}")
                        or s_nid.startswith(f"{npc_slug}_")
                        or s_nid.endswith(f"_{npc_slug}")
                    ):
                        cand_rows.append(sr)
                        if len(cand_rows) >= 2:
                            break
                if len(cand_rows) == 1:
                    sd_row = cand_rows[0]
        else:
            sd_row = conn.execute(
                """SELECT role, grade, club, clique, primary_facility, secondary_facility, personality_summary, race, gender
                   FROM school_directory
                   WHERE session_id=? AND (lower(name)=? OR npc_id=?)
                   LIMIT 1""",
                (session_id, name_low, npc_slug)
            ).fetchone()
            if not sd_row and " " not in name_clean:
                cand_rows = conn.execute(
                    """SELECT role, grade, club, clique, primary_facility, secondary_facility, personality_summary, race, gender
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
            if not _is_empty_info_val(sd_row["race"]):
                info["race"] = sd_row["race"].strip()
                info["_canonical_race"] = sd_row["race"].strip()
            if not _is_empty_info_val(sd_row["gender"]):
                info["gender"] = sd_row["gender"].strip().lower()
                info["_canonical_gender"] = sd_row["gender"].strip().lower()
    except Exception:
        pass

    # 1b. Cross-reference anomalous_agent_roster (stored in sessions.extra_json)
    try:
        if preloaded_enrichment is not None:
            ar_map = preloaded_enrichment.get("anomalous_roster_by_key") or {}
            ar_row = ar_map.get(name_low) or ar_map.get(npc_slug)
        else:
            ar_row = _find_anomalous_agent_entry(conn, session_id, name_low, npc_slug)
        if ar_row:
            if isinstance(ar_row, dict):
                ar_race = ar_row.get("race")
                ar_gender = ar_row.get("gender")
                ar_cls = ar_row.get("agent_class")
                ar_fac = ar_row.get("faction_name")
            else:
                ar_race = ar_row["race"]
                ar_gender = ar_row["gender"]
                ar_cls = ar_row["agent_class"]
                ar_fac = ar_row["faction_name"]
            if not _is_empty_info_val(ar_race):
                info["race"] = ar_race.strip()
                info["_canonical_race"] = ar_race.strip()
            if not _is_empty_info_val(ar_gender):
                info["gender"] = ar_gender.strip().lower()
                info["_canonical_gender"] = ar_gender.strip().lower()
            if _is_empty_info_val(info.get("role")) and not _is_empty_info_val(ar_cls):
                info["role"] = ar_cls.strip()
            if _is_empty_info_val(info.get("faction")) and not _is_empty_info_val(ar_fac):
                info["faction"] = ar_fac.strip()
    except Exception:
        pass

    # 2. Cross-reference factions leadership_roster_json
    try:
        if preloaded_enrichment is not None:
            fac_entries = preloaded_enrichment.get("factions") or []
        else:
            fac_rows = conn.execute(
                "SELECT name, leadership_roster_json FROM factions WHERE session_id=?",
                (session_id,)
            ).fetchall()
            fac_entries = []
            for fr in fac_rows:
                fac_name = (fr["name"] or "").strip()
                roster = json.loads(fr["leadership_roster_json"] or "[]")
                fac_entries.append((fac_name, roster))
        for fac_name, roster in fac_entries:
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
        if preloaded_enrichment is not None:
            lb_row = (preloaded_enrichment.get("lorebook_by_name") or {}).get(name_low)
        else:
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
    if needs_narrative and not scene_narr and not (preloaded_enrichment and preloaded_enrichment.get("narrative_loaded")):
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
            "coach", "athletic director", "advisor", "parent", "father", "mother", "detective", "police", "officer", "vendor",
            "operator", "dispatch", "operative", "agent", "investigator", "director", "commander", "clerk", "receptionist", "bartender", "barista"
        )
        grade_lower = str(info.get("grade") or "").strip().lower()
        age_grp_lower = str(info.get("age_group") or "").strip().lower()
        srt_lower = str(info.get("social_role_type") or "").strip().lower()
        is_faculty_or_adult = (
            any(kw in role_lower for kw in faculty_keywords)
            or grade_lower in ("faculty", "adult", "citizen", "staff", "operative")
            or grade_lower.startswith("tier ")
            or age_grp_lower == "adult"
            or srt_lower in ("faculty_staff", "adult_service", "special_agent", "family_relative", "parent")
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
                        if preloaded_enrichment is not None:
                            fac_names = preloaded_enrichment.get("faction_names") or []
                        else:
                            fac_rows = conn.execute(
                                "SELECT name FROM factions WHERE session_id=?",
                                (session_id,)
                            ).fetchall()
                            fac_names = [fr["name"].strip() for fr in fac_rows if fr["name"]]
                        candidate_factions = [
                            fname for fname in fac_names
                            if fname and not any(kw in fname.lower() for kw in ("faculty", "staff", "board", "administration", "directorate", "security group", "investigations", "congregation", "sealing order", "syndicate", "bureau", "agency"))
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

    # 5. Backfill lorebook if lorebook row exists with empty description/faction (skip during read-only batch calls)
    if preloaded_enrichment is None and lb_row and (not _is_empty_info_val(info.get("description")) or not _is_empty_info_val(info.get("faction"))):
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
