from __future__ import annotations

"""
Centralized Teen / Student Civilian Employment Policy & Save Auto-Healer.

Enforces the domain invariant that teen / high-school student civilians must NOT
hold full-time, public-agency, private-agency, medical, law-enforcement,
school-faculty/staff, corporate, or adult/nightlife jobs.
Teen/student civilians MAY hold everyday student-friendly commercial part-time
jobs (cafés, diners, bakeries, convenience stores, retail/bookstores/arcades,
campus co-op, night market stalls) on after-school/weekend shifts.
Teen/student Special Agents are an explicit special case and remain exempt.
"""

import json
import re
from typing import Any, Mapping

from .roster_tags import _is_agent_tier_grade, derive_age_group, is_school_scenario

_STUDENT_GRADES_LOWER: frozenset[str] = frozenset({
    "freshman",
    "sophomore",
    "junior",
    "senior",
    "student",
    "youth peer",
})

_NON_CLUB_FACTION_CATEGORIES: frozenset[str] = frozenset({
    "public_agency",
    "private_agency",
    "private_agency_1",
    "private_agency_2",
    "monastic_order",
    "cult_faction",
    "clandestine_faction",
    "nsfw_club",
})

_PROHIBITED_WORKPLACE_NODE_IDS: frozenset[str] = frozenset({
    "loc_agency_hq",
    "zone_agency_hq",
    "loc_hq_main_lobby",
    "loc_hq_containment_sector",
    "loc_hq_medical_bay",
    "loc_hq_tactical_armory",
    "loc_private_hq_1",
    "loc_private_hq_2",
    "loc_cult_sanctum_hq",
    "loc_clandestine_syndicate_hq",
    "loc_eastern_temple",
    "loc_et_main_sanctuary",
    "loc_et_five_story_pagoda",
    "loc_general_hospital",
    "fac_agency_residence",
    "fac_temple_residence",
    "loc_nightclub",
    "loc_adult_store",
    "loc_school_infirmary",
    "loc_staff_room",
    "loc_nsfw_boutique",
    "loc_nsfw_club_facility",
})

_PROHIBITED_WORKPLACE_PREFIXES: tuple[str, ...] = (
    "loc_hq_",
    "sub_priv1_",
    "sub_priv2_",
    "sub_cult_",
    "sub_synd_",
    "loc_et_",
)

_PROHIBITED_WORKPLACE_KEYWORDS: tuple[str, ...] = (
    "m.c.o.a",
    "oversight agency",
    "containment",
    "cornerstone",
    "agency",
    "bureau",
    "directorate",
    "syndicate",
    "sanctum",
    "monastic",
    "police",
    "precinct",
    "military",
    "armory",
    "barracks",
    "security hub",
    "hospital",
    "clinic",
    "infirmary",
    "medbay",
    "medical",
    "pharmacy",
    "apothecary",
    "city hall",
    "courthouse",
    "embassy",
    "government",
    "ministry",
    "corporate",
    "headquarters",
    "nightclub",
    "adult store",
    "brothel",
    "casino",
    "tavern",
    "cocktail bar",
    "lounge",
    "velvet basement",
    "velvet salon",
)

_ALLOWED_PART_TIME_VENUE_KEYWORDS: tuple[str, ...] = (
    "cafe",
    "café",
    "coffee",
    "bakery",
    "bistro",
    "diner",
    "ramen",
    "noodle",
    "tea house",
    "restaurant",
    "konbini",
    "convenience",
    "grocery",
    "mini-mart",
    "supermarket",
    "bookstore",
    "bookshop",
    "arcade",
    "apparel",
    "boutique",
    "clothing",
    "accessories",
    "gift",
    "florist",
    "flower",
    "stationery",
    "campus store",
    "campus co-op",
    "night market",
    "street stall",
    "food stall",
    "bento",
    "snack",
    "market",
    "shop",
    "store",
)

_STUDENT_ROLE_EXEMPTION_RE = re.compile(
    r"\b("
    r"student council|class rep|class representative|peer counselor|peer tutor|"
    r"club president|club vice[- ]president|club captain|team captain|varsity captain|"
    r"vice[- ]captain|club officer|robotics|lab monitor|audio tech|newspaper|journalism|"
    r"exchange student|transfer student|part[- ]time"
    r")\b",
    re.IGNORECASE,
)

_PROHIBITED_ROLE_RE = re.compile(
    r"\b("
    r"special agent|agent|operative|field specialist|hazmat|containment|"
    r"field associate|managing partner|team supervisor|director|dispatcher|"
    r"dispatch operator|duty officer|operations supervisor|quartermaster|"
    r"exorcist|broker|cleaner|fixer|acolyte|hierophant|conduit|"
    r"investigator|detective|inspector|analyst|researcher|scientist|engineer|"
    r"archivist|curator|"
    r"nurse|school nurse|doctor|physician|medic|paramedic|surgeon|healer|pharmacist|apothecary|therapist|"
    r"police|cop|officer|sheriff|constable|guard|security|warden|patrol|soldier|knight|mercenary|bouncer|firefighter|"
    r"teacher|professor|faculty|principal|vice[- ]principal|dean|counselor|coach|librarian|"
    r"headmaster|headmistress|custodian|janitor|groundskeeper|caretaker|lunch lady|cafeteria staff|cafeteria worker|"
    r"executive|ceo|manager|supervisor|lawyer|attorney|judge|accountant|landlord|landlady|mayor|governor|"
    r"bartender|barkeep|barman|barmaid|mixologist|hostess|stripper|escort|innkeeper|proprietor|owner|"
    r"guildmaster|blacksmith|armorer|gunsmith|priest|priestess|monk|shrine keeper|"
    r"bus driver|driver|pilot|captain|commander|mechanic|plumber|electrician|carpenter|"
    r"tailor|head clothier|chef|cook|receptionist|lifeguard"
    r")\b",
    re.IGNORECASE,
)

_SCHOOL_STAFF_ROLE_TOKENS: tuple[str, ...] = (
    "school nurse",
    "nurse",
    "librarian",
    "custodian",
    "janitor",
    "groundskeeper",
    "caretaker",
    "lunch lady",
    "cafeteria",
    "security guard",
    "campus guard",
    "gate security",
    "proctor",
    "teacher",
    "professor",
    "faculty",
    "principal",
    "dean",
    "counselor",
    "coach",
)

_PART_TIME_FRIENDLY_ROLE_RE = re.compile(
    r"\b("
    r"waitstaff|waiter|waitress|server|barista|cashier|clerk|wrapper|helper|trainee|"
    r"stocker|attendant|host|assistant|runner|seller|busker"
    r")\b",
    re.IGNORECASE,
)


def _parse_basic(npc: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(npc, Mapping):
        return {}
    raw = npc.get("basic_info") if npc.get("basic_info") is not None else npc.get("basic_info_json")
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def is_special_agent_npc(npc: Mapping[str, Any] | None) -> bool:
    """True for Special Agents (including teen/student Special Agents, who are exempt)."""
    if not isinstance(npc, Mapping):
        return False
    basic = _parse_basic(npc)
    if (
        npc.get("is_special_agent")
        or basic.get("is_special_agent")
        or npc.get("is_student_agent")
        or basic.get("is_student_agent")
        or npc.get("is_student_operative")
        or basic.get("is_student_operative")
    ):
        return True
    tag = str(npc.get("anomalous_npc_tag") or basic.get("anomalous_npc_tag") or "").strip().lower()
    if tag == "special_agent":
        return True
    srt = str(npc.get("social_role_type") or basic.get("social_role_type") or "").strip().lower()
    if srt == "special_agent":
        return True
    grade = str(npc.get("grade") or basic.get("grade") or npc.get("standing") or "").strip().lower()
    return _is_agent_tier_grade(grade)


def is_teen_student_civilian(npc: Mapping[str, Any] | None, *, scen_key: str = "") -> bool:
    """True if `npc` represents a teen / high-school student civilian (excludes Special Agents)."""
    if not isinstance(npc, Mapping) or is_special_agent_npc(npc):
        return False
    basic = _parse_basic(npc)
    age_grp = str(npc.get("age_group") or basic.get("age_group") or "").strip().lower()
    if age_grp == "teen":
        return True
    grade = str(npc.get("grade") or basic.get("grade") or npc.get("standing") or "").strip().lower()
    if grade in _STUDENT_GRADES_LOWER:
        return True
    if bool(npc.get("is_student") or basic.get("is_student")):
        return True
    srt = str(npc.get("social_role_type") or basic.get("social_role_type") or "").strip().lower()
    if srt in ("student_peer", "peer", "contemporary", "classmate"):
        return True
    if age_grp in ("adult", "elder") or grade in ("faculty", "staff", "citizen", "adult"):
        return False
    if scen_key and is_school_scenario(scen_key):
        role = str(npc.get("role") or basic.get("role") or basic.get("occupation") or "").strip()
        return derive_age_group(grade=grade, role=role, social_role_type=srt, scen_key=scen_key) == "teen"
    return False


def is_prohibited_teen_civilian_workplace(
    node_id: str = "",
    venue_name: str = "",
    faction_name: str = "",
    faction_category: str = "",
) -> bool:
    """True for agency HQs, civic/corporate hubs, clinics, law enforcement, and adult nightlife venues."""
    nid = str(node_id or "").strip().lower()
    if nid:
        if nid in _PROHIBITED_WORKPLACE_NODE_IDS or any(nid.startswith(p) for p in _PROHIBITED_WORKPLACE_PREFIXES):
            return True
    cat = str(faction_category or "").strip().lower()
    if cat in _NON_CLUB_FACTION_CATEGORIES:
        return True
    probe = f"{venue_name or ''} {faction_name or ''} {nid}".lower()
    if "student council office" in probe:
        return False
    if any(tok in probe for tok in _PROHIBITED_WORKPLACE_KEYWORDS):
        return True
    if re.search(r"\b(police|fire)\s+station\b", probe) or re.search(r"\bbar\b", probe):
        return True
    return False


def is_allowed_teen_part_time_venue(node_id: str = "", venue_name: str = "", role: str = "") -> bool:
    """True ONLY for everyday student-friendly commercial part-time venues."""
    if is_prohibited_teen_civilian_workplace(node_id, venue_name):
        return False
    probe = f"{node_id or ''} {venue_name or ''} {role or ''}".lower()
    if not probe.strip():
        return False
    return any(tok in probe for tok in _ALLOWED_PART_TIME_VENUE_KEYWORDS)


def is_prohibited_teen_civilian_role(role: str = "", occupation: str = "") -> bool:
    """True for full-time, public/private agency, medical, law-enforcement, school-faculty/staff, and adult roles."""
    combined = " ".join(part for part in (str(role or "").strip(), str(occupation or "").strip()) if part).strip()
    if not combined:
        return False
    low = combined.lower()
    if low.startswith("part-time ") or low.startswith("part time "):
        if _PART_TIME_FRIENDLY_ROLE_RE.search(low) and not any(
            k in low for k in ("agent", "operative", "nurse", "doctor", "security", "police", "bartender")
        ):
            return False
    cleaned = _STUDENT_ROLE_EXEMPTION_RE.sub(" ", low)
    if re.search(r"\bspecialist\b", cleaned) and not any(k in low for k in ("robotics", "peer", "club")):
        return True
    if "school nurse" in low or "special agent" in low:
        return True
    return bool(_PROHIBITED_ROLE_RE.search(cleaned))


def is_prohibited_teen_civilian_assignment(
    npc: Mapping[str, Any] | None,
    *,
    role: str = "",
    workplace_node_id: str = "",
    workplace_name: str = "",
    faction: str = "",
    faction_category: str = "",
    shift_profile: str = "",
    scen_key: str = "",
) -> bool:
    """True when assigning `role`/`workplace` to a teen/student civilian would violate employment rules."""
    if not is_teen_student_civilian(npc, scen_key=scen_key):
        return False
    basic = _parse_basic(npc)
    eff_role = str(role or (npc or {}).get("role") or basic.get("role") or basic.get("occupation") or "").strip()
    eff_wp = str(workplace_node_id or (npc or {}).get("workplace_node_id") or basic.get("workplace_node_id") or "").strip()
    eff_fac = str(faction or (npc or {}).get("faction") or basic.get("faction") or (npc or {}).get("club") or basic.get("club") or "").strip()
    eff_fcat = str(faction_category or (npc or {}).get("faction_category") or basic.get("faction_category") or "").strip()
    eff_shift = str(shift_profile or (npc or {}).get("shift_profile") or basic.get("shift_profile") or "").strip().lower()

    if is_prohibited_teen_civilian_role(eff_role):
        return True
    if is_prohibited_teen_civilian_workplace(eff_wp, workplace_name, eff_fac, eff_fcat):
        return True

    has_part_time = bool((npc or {}).get("part_time_shift") or basic.get("part_time_shift"))
    if eff_wp and not has_part_time and eff_shift in ("day", "night", "24h", "evening", "street_vendor"):
        wp_low = eff_wp.lower()
        if not (wp_low.startswith("loc_school_") or wp_low.startswith("bld_school_") or wp_low in ("loc_homeroom", "loc_courtyard", "loc_library")):
            return True
    return False


def _resolve_faction_hq_node(fac: Mapping[str, Any], nodes_by_id: Mapping[str, dict[str, Any]]) -> tuple[str, str]:
    from mechanics.social.factions import get_anomalous_faction_spec, infer_anomalous_faction_archetype

    arch = infer_anomalous_faction_archetype(dict(fac))
    spec = get_anomalous_faction_spec(arch)
    hq_nid = str(fac.get("hq_node_id") or spec.get("hq_id") or "").strip()
    hq_label = ""
    if hq_nid and hq_nid in nodes_by_id:
        hq_label = str((nodes_by_id[hq_nid] or {}).get("name") or "").strip()
    if not hq_label:
        hq_label = str(fac.get("hq_location_id") or spec.get("hq_id") or "").strip()
    return hq_nid, hq_label


def heal_invalid_teen_civilian_employment(
    session_id: int,
    scen_key: str = "",
    *,
    factions: list[dict[str, Any]] | None = None,
    roster: list[dict[str, Any]] | None = None,
    nodes_by_id: Mapping[str, dict[str, Any]] | None = None,
    session: dict[str, Any] | None = None,
) -> int:
    """
    Idempotently self-heals persisted saves where adult agency/professional staff
    were tagged as teen students or synced into `school_directory`, or where genuine
    teen/student civilians hold prohibited workplaces. Performs zero DB writes when clean.
    """
    sid = int(session_id or 0)
    if sid <= 0:
        return 0
    import db
    from mechanics.social.factions import is_school_club_faction

    eff_sess = session if isinstance(session, dict) else (db.get_session(sid) or {})
    eff_scen = str(scen_key or eff_sess.get("scenario") or "").strip()
    if not is_school_scenario(eff_scen):
        return 0

    eff_factions = factions if factions is not None else (db.get_factions(sid) or [])
    school_dir = db.get_school_roster(sid) or []
    eff_roster = roster if roster is not None else (db.get_world_roster(sid, include_legacy_rosters=False) or [])
    eff_nodes = nodes_by_id
    if eff_nodes is None:
        eff_nodes = {
            str(n["node_id"]): n
            for n in (db.get_session_world_nodes(sid) or [])
            if isinstance(n, Mapping) and n.get("node_id")
        }

    agent_roster = eff_sess.get("anomalous_agent_roster")
    if not isinstance(agent_roster, list) and isinstance(eff_sess.get("extra"), dict):
        agent_roster = eff_sess["extra"].get("anomalous_agent_roster")
    if not isinstance(agent_roster, list):
        agent_roster = db.get_anomalous_agent_roster(sid) or []
    student_agent_names: set[str] = {
        str(a.get("name") or "").strip().lower()
        for a in agent_roster
        if isinstance(a, Mapping)
        and a.get("name")
        and (a.get("is_student_agent") or a.get("is_special_agent") or (a.get("basic_info") or {}).get("is_special_agent"))
        and bool(a.get("is_student_agent") or a.get("grade") in ("Freshman", "Sophomore", "Junior", "Senior"))
    }

    officer_by_name: dict[str, dict[str, Any]] = {}
    non_club_fac_names: set[str] = set()
    for fac in eff_factions:
        if not isinstance(fac, Mapping) or is_school_club_faction(dict(fac)):
            continue
        fac_name = str(fac.get("name") or "").strip()
        if fac_name:
            non_club_fac_names.add(fac_name.lower())
        for entry in (fac.get("leadership_roster") or []):
            if not isinstance(entry, Mapping) or entry.get("is_vacant") or entry.get("is_player"):
                continue
            m_low = str(entry.get("name") or "").strip().lower()
            if m_low and m_low not in officer_by_name:
                officer_by_name[m_low] = dict(fac)

    # Plan Phase 1: Purge adult non-club faction officers & prohibited non-students wrongly placed in school_directory
    purge_school_keys: list[str] = []
    purged_names_low: set[str] = set()
    surviving_school_names: set[str] = set()
    for srow in school_dir:
        s_name = str(srow.get("name") or "").strip()
        s_low = s_name.lower()
        s_club_low = str(srow.get("club") or "").strip().lower()
        s_role = str(srow.get("role") or "").strip()
        s_grade_low = str(srow.get("grade") or "").strip().lower()
        if not s_name or s_low in student_agent_names:
            if s_low and s_grade_low in _STUDENT_GRADES_LOWER:
                surviving_school_names.add(s_low)
            continue
        is_wrong_officer = (s_low in officer_by_name) or (bool(s_club_low) and s_club_low in non_club_fac_names)
        if is_wrong_officer or (s_grade_low in _STUDENT_GRADES_LOWER and is_prohibited_teen_civilian_role(s_role)):
            purge_school_keys.append(str(srow.get("npc_id") or s_name))
            purged_names_low.add(s_low)
        elif s_grade_low in _STUDENT_GRADES_LOWER:
            surviving_school_names.add(s_low)

    # Plan Phase 2: Heal world_roster rows (and mirrored contacts)
    roster_mutations: list[tuple[str, dict[str, Any], dict[str, Any], tuple[str, ...]]] = []
    healed_npc_snapshots: dict[str, dict[str, Any]] = {}

    for row in eff_roster:
        if not isinstance(row, Mapping) or is_special_agent_npc(row):
            continue
        npc_id = str(row.get("npc_id") or "").strip()
        name = str(row.get("name") or "").strip()
        name_low = name.lower()
        if not npc_id or not name:
            continue
        basic = _parse_basic(row)
        role_val = str(row.get("role") or basic.get("role") or basic.get("occupation") or "").strip()
        origin_val = str(row.get("origin") or "").strip().lower()
        wp_nid = str(row.get("workplace_node_id") or basic.get("workplace_node_id") or "").strip()
        wp_name = str((eff_nodes.get(wp_nid) or {}).get("name") or basic.get("workplace_label") or basic.get("workplace") or "").strip()
        club_val = str(basic.get("club") or "").strip()
        club_low = club_val.lower()
        fac_obj = officer_by_name.get(name_low)

        is_teen_civ = is_teen_student_civilian(row, scen_key=eff_scen)
        if not is_teen_civ and not (name_low in purged_names_low or (club_low and club_low in non_club_fac_names)):
            continue

        should_be_adult = bool(
            (name_low in purged_names_low)
            or (fac_obj is not None)
            or (club_low and club_low in non_club_fac_names)
            or (origin_val in ("venue_seed", "replacement_hire", "roaming_merchant", "role_slot_fill", "civic_staff")
                and (is_prohibited_teen_civilian_role(role_val) or is_prohibited_teen_civilian_workplace(wp_nid, wp_name)))
            or is_prohibited_teen_civilian_role(role_val)
        )

        if should_be_adult:
            role_low = role_val.lower()
            target_grade = "Staff" if any(tok in role_low for tok in _SCHOOL_STAFF_ROLE_TOKENS) else "Citizen"
            col_updates: dict[str, Any] = {}
            bi_updates: dict[str, Any] = {
                "age_group": "adult",
                "grade": target_grade,
                "social_role_type": "faculty_staff" if target_grade == "Staff" else "adult_service",
            }
            remove_keys: list[str] = ["is_student"]
            if str(row.get("shift_profile") or "").strip().lower() == "student":
                col_updates["shift_profile"] = "day"
                bi_updates["shift_profile"] = "day"
            if club_val and (club_low in non_club_fac_names or target_grade in ("Citizen", "Staff")):
                bi_updates["club"] = ""
                if str(basic.get("clique") or "").strip().lower() in non_club_fac_names:
                    bi_updates["clique"] = ""

            new_wp_nid = wp_nid
            new_wp_label = wp_name
            if fac_obj is not None:
                fac_name = str(fac_obj.get("name") or "").strip()
                fac_hq_nid, fac_hq_label = _resolve_faction_hq_node(fac_obj, eff_nodes)
                if fac_name:
                    bi_updates["faction"] = fac_name
                    bi_updates["faction_affiliation"] = fac_name
                if fac_hq_nid and (not wp_nid or wp_nid != fac_hq_nid):
                    new_wp_nid = fac_hq_nid
                    new_wp_label = fac_hq_label
                    col_updates["workplace_node_id"] = fac_hq_nid
                    bi_updates["workplace_node_id"] = fac_hq_nid
                    if fac_hq_label:
                        bi_updates["workplace_label"] = fac_hq_label
                    remove_keys.extend(["location", "primary_facility"])

            needs_write = (
                str(basic.get("age_group") or "").strip().lower() != "adult"
                or str(basic.get("grade") or "").strip() != target_grade
                or bool(col_updates)
                or (club_val and bi_updates.get("club") == "")
                or ("faction" in bi_updates and str(basic.get("faction") or "").strip() != bi_updates["faction"])
            )
            if needs_write:
                roster_mutations.append((npc_id, col_updates, bi_updates, tuple(remove_keys)))
                healed_npc_snapshots[name_low] = {
                    "grade": target_grade,
                    "age_group": "adult",
                    "club": bi_updates.get("club", club_val),
                    "faction": bi_updates.get("faction", ""),
                    "workplace_node_id": new_wp_nid,
                    "workplace_label": new_wp_label,
                    "bi_updates": bi_updates,
                    "remove_keys": tuple(remove_keys),
                }
            continue

        # Case B: Genuine student civilian holding a prohibited full-time / agency workplace
        if (name_low in surviving_school_names or origin_val == "campus_seed" or basic.get("is_student")) and wp_nid:
            pt_spec = row.get("part_time_shift") or basic.get("part_time_shift")
            wp_low = wp_nid.lower()
            is_campus_node = wp_low.startswith("loc_school_") or wp_low.startswith("bld_school_") or wp_low in (
                "loc_homeroom",
                "loc_courtyard",
                "loc_library",
                "loc_fine_arts_studio",
                "loc_old_east_music_room",
                "loc_freshman_class",
                "loc_sophomore_class",
                "loc_senior_class",
                "loc_sports_field",
                "loc_broadcasting_room",
                "loc_greenhouse",
                "loc_martial_arts_dojo",
                "loc_pool",
                "loc_clubroom_corridor",
                "loc_science_lab",
                "loc_auditorium_stage",
                "loc_student_council",
            )
            if is_prohibited_teen_civilian_workplace(wp_nid, wp_name) or (
                not is_campus_node and str(row.get("shift_profile") or "").strip().lower() in ("day", "night", "24h")
            ):
                col_updates = {"workplace_node_id": "", "shift_profile": "student"}
                bi_updates = {"workplace_node_id": "", "shift_profile": "student", "age_group": "teen"}
                remove_keys_b: list[str] = ["workplace_label", "workplace", "work_location_label"]
                if isinstance(pt_spec, Mapping) and not is_allowed_teen_part_time_venue(
                    str(pt_spec.get("venue_node_id") or ""),
                    role=str(pt_spec.get("job_title") or ""),
                ):
                    remove_keys_b.append("part_time_shift")
                roster_mutations.append((npc_id, col_updates, bi_updates, tuple(remove_keys_b)))
                healed_npc_snapshots[name_low] = {
                    "grade": str(basic.get("grade") or row.get("grade") or ""),
                    "age_group": "teen",
                    "club": club_val,
                    "faction": "",
                    "workplace_node_id": "",
                    "workplace_label": "",
                    "bi_updates": bi_updates,
                    "remove_keys": tuple(remove_keys_b),
                }

    if not purge_school_keys and not roster_mutations:
        return 0

    def _apply_tx() -> int:
        changed = 0
        if purge_school_keys:
            changed += int(db.delete_school_roster_entries(sid, purge_school_keys) or 0)
        for nid_val, cols_u, bi_u, rm_k in roster_mutations:
            if db.heal_world_roster_npc_employment(
                sid,
                nid_val,
                updates=cols_u,
                basic_info_updates=bi_u,
                remove_basic_keys=rm_k,
            ):
                changed += 1
        curr_npcs = eff_sess.get("current_npcs")
        if healed_npc_snapshots and isinstance(curr_npcs, list):
            curr_changed = False
            for c_entry in curr_npcs:
                if not isinstance(c_entry, dict):
                    continue
                c_low = str(c_entry.get("name") or "").strip().lower()
                snap = healed_npc_snapshots.get(c_low)
                if not snap:
                    continue
                curr_changed = True
                c_entry["age_group"] = snap["age_group"]
                if snap["grade"]:
                    c_entry["grade"] = snap["grade"]
                c_entry["club"] = snap["club"]
                if snap["faction"]:
                    c_entry["faction"] = snap["faction"]
                c_entry["workplace_node_id"] = snap["workplace_node_id"]
                c_entry["workplace_label"] = snap["workplace_label"]
                cb = dict(c_entry.get("basic_info") or {}) if isinstance(c_entry.get("basic_info"), dict) else {}
                cb.update(snap["bi_updates"])
                for rk in snap["remove_keys"]:
                    cb.pop(rk, None)
                c_entry["basic_info"] = cb
            if curr_changed:
                db.update_session(sid, current_npcs=curr_npcs)
        return changed

    if db.is_in_uow():
        return _apply_tx()
    with db.UnitOfWork():
        return _apply_tx()
