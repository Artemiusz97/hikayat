"""
mechanics/social/discreet_encounters.py
=======================================
Deterministic High School & NSFW High School spatial event engine:
1. Active-lecture grade-exclusive classroom interruptions & rotating teacher confrontations.
2. School Infirmary Nurse interactions & official Sick / Early-Dismissal Passes.
3. Gendered Restroom & Athletic Shower Room physical staging, wash-up refresh, and opposite-gender entry hazards (with Gossip Feed scandal rumors & Student Council rep loss).
4. NSFW `is_discreet` random couple encounters (15% roll, 2/day soft cap, 4 activity tiers) and ~25% Secret Affair discoveries (`TIETYPE_AFFAIR`, breakup exposure, discretion promises, bold propositions).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data
from mechanics.social import relationship_graph as rg
from mechanics.social.physical_state import (
    apply_player_shower_refresh,
    is_discreet_venue,
    is_shower_or_locker_location,
    stage_shower_room_actors,
)
from mechanics.system.phone.gossip_feed import queue_witness_gossip_post
from mechanics.world.locations.seeds import (
    get_session_athletics_complex_name,
    get_session_school_name,
    is_school_scenario,
)
from mechanics.world.world_schedule import is_weekend

log = logging.getLogger("hikayat.social.discreet_encounters")

GRADE_CLASSROOM_MAP: Dict[str, str] = {
    "loc_freshman_class": "Freshman",
    "loc_sophomore_class": "Sophomore",
    "loc_junior_class": "Junior (Class 3-B)",
    "loc_senior_class": "Senior",
}

MALE_GENDERED_NODES = {"loc_male_restroom", "loc_male_shower_room"}
FEMALE_GENDERED_NODES = {"loc_female_restroom", "loc_female_shower_room"}

DISCREET_ACTIVITY_TIERS: List[Dict[str, str]] = [
    {
        "tier_id": "quiet_hangout",
        "summary": "huddled close together in a quiet corner, whispering and holding hands away from prying eyes",
    },
    {
        "tier_id": "making_out",
        "summary": "pressed against the wall in a heated embrace, trading breathless kisses",
    },
    {
        "tier_id": "getting_frisky",
        "summary": "tangled up together with flushed cheeks and half-unbuttoned clothes in the middle of heavy petting",
    },
    {
        "tier_id": "intimate_session",
        "summary": "caught right in the middle of a passionate, uninhibited intimate tryst behind closed doors",
    },
]


def _det_float(seed_str: str) -> float:
    """Returns a deterministic float in [0.0, 1.0) from seed_str."""
    digest = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
    return (int(digest[:8], 16) % 10000) / 10000.0


def _det_int(seed_str: str, mod: int) -> int:
    if mod <= 0:
        return 0
    digest = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % mod


def _get_social_state(session: Dict[str, Any]) -> Dict[str, Any]:
    raw = session.get("phone_social_state")
    if not isinstance(raw, dict):
        extra = session.get("extra")
        if isinstance(extra, dict) and isinstance(extra.get("phone_social_state"), dict):
            raw = dict(extra["phone_social_state"])
        else:
            raw = {}
    session["phone_social_state"] = raw
    return raw


def _persist_social_state(session: Dict[str, Any], extra_fields: Optional[Dict[str, Any]] = None) -> None:
    sess_id = int(session.get("id") or 0)
    if not sess_id:
        return
    st = _get_social_state(session)
    payload: Dict[str, Any] = {"phone_social_state": st}
    if extra_fields:
        payload.update(extra_fields)
    try:
        db.update_session(sess_id, extra=payload)
    except Exception as exc:
        log.warning("Failed persisting discreet_encounters state: %s", exc)


def _extract_lead_player(session: Dict[str, Any], party: Optional[List[Any]]) -> Tuple[int, str, str]:
    """Returns (char_id, player_name, player_gender_lower)."""
    char_obj: Dict[str, Any] = {}
    if party:
        first = party[0]
        cand = first[0] if isinstance(first, (tuple, list)) else first
        if isinstance(cand, dict):
            char_obj = cand
    if not char_obj and isinstance(session.get("player_character"), dict):
        char_obj = session["player_character"]

    char_id = int(char_obj.get("id") or session.get("character_id") or 0)
    if not char_obj and char_id:
        try:
            c_rec = db.get_character_by_id(char_id)
            if c_rec:
                char_obj = c_rec
        except Exception:
            pass

    p_name = str(char_obj.get("name") or "Player").strip()
    p_gender = str(char_obj.get("gender") or "").strip().lower()
    return char_id, p_name, p_gender


def _resolve_node_and_parent(session_id: int, node_id: str, location_str: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str]:
    """Resolves (node_dict, parent_facility_dict, effective_facility_or_node_id)."""
    nid = str(node_id or "").strip()
    if not nid and session_id and location_str:
        try:
            nid = db.resolve_node_id_from_location(session_id, location_str) or ""
        except Exception:
            nid = ""
    node = db.get_world_node(session_id, nid) if (session_id and nid) else None
    parent = None
    if node and node.get("parent_id"):
        parent = db.get_world_node(session_id, node["parent_id"])
    fac_id = ""
    if node:
        if str(node.get("node_type") or "").upper() == "ROOM" and parent:
            fac_id = str(parent.get("node_id") or "")
        else:
            fac_id = str(node.get("node_id") or "")
    return node, parent, (fac_id or nid)


def _adjust_student_council_reputation(session_id: int, delta: int) -> None:
    if not session_id or not delta:
        return
    try:
        factions = db.get_factions(session_id) or []
        target_name = "Student Council"
        for f in factions:
            fn = str(f.get("name") or "")
            fc = str(f.get("category") or "").lower()
            if "student council" in fn.lower() or fc == "council":
                target_name = fn
                break
        db.upsert_faction(session_id, name=target_name, delta_score=delta)
    except Exception as exc:
        log.warning("Failed adjusting Student Council rep: %s", exc)


def _is_check_success(action: Dict[str, Any]) -> bool:
    chk = action.get("check")
    if isinstance(chk, dict):
        if "succeeded" in chk:
            return bool(chk["succeeded"])
        return str(chk.get("tier") or "").lower() in ("crit_success", "critical_success", "success", "partial_success")
    if chk is not None and hasattr(chk, "succeeded"):
        return bool(getattr(chk, "succeeded"))
    if "success" in action:
        return bool(action["success"])
    return True


def _is_bold_or_uninhibited_npc(npc_or_contact: Dict[str, Any]) -> bool:
    blob_parts = [
        str(npc_or_contact.get("personality_summary") or ""),
        str(npc_or_contact.get("clique") or ""),
        str(npc_or_contact.get("openness") or ""),
    ]
    app = npc_or_contact.get("appearance")
    if isinstance(app, dict):
        blob_parts.append(str(app.get("erotic_openness") or app.get("openness") or ""))
    traits = npc_or_contact.get("unlocked_traits") or npc_or_contact.get("traits") or []
    if isinstance(traits, list):
        blob_parts.extend(str(t) for t in traits)
    blob = " ".join(blob_parts).lower()
    return any(
        kw in blob
        for kw in ("bold", "uninhibited", "shameless", "hedon", "flirt", "playful", "teas", "seduc", "rebel", "lewd")
    )


# ---------------------------------------------------------------------------
# 1. Active-Lecture Grade-Exclusive Classroom Interruptions
# ---------------------------------------------------------------------------

def evaluate_classroom_lecture_intrusion(
    session_id: int,
    scen_key: str,
    fac_id: str,
    current_day: int,
    current_minute: int,
) -> Optional[Dict[str, Any]]:
    """
    During weekday lecture windows (08:00–12:00 & 13:00–15:00), entering a non-homeroom
    grade classroom (`loc_freshman_class`, `loc_sophomore_class`, `loc_junior_class`, `loc_senior_class`)
    triggers an active-lecture teacher confrontation.
    """
    if not is_school_scenario(scen_key) or is_weekend(current_day):
        return None
    fid = str(fac_id or "").lower()
    if fid not in GRADE_CLASSROOM_MAP:
        return None
    safe_min = int(current_minute or 0) % 1440
    in_lecture = (480 <= safe_min < 720) or (780 <= safe_min < 900)
    if not in_lecture:
        return None

    grade_label = GRADE_CLASSROOM_MAP[fid]
    teacher_name = "Ms. Vance"
    teacher_role = "Subject Teacher"
    try:
        from mechanics.world.npc_schedule import get_rotating_classroom_for_teacher
        lec_phase = "morning" if safe_min < 720 else "class_afternoon"
        roster = db.get_school_roster(session_id) or []
        for r in roster:
            if str(r.get("grade") or "") == "Faculty":
                assigned_cls = get_rotating_classroom_for_teacher(
                    r.get("role", ""), current_day=current_day, phase=lec_phase
                )
                if assigned_cls == fid:
                    teacher_name = str(r.get("name") or teacher_name)
                    teacher_role = str(r.get("role") or teacher_role)
                    break
    except Exception:
        pass

    choices = [
        {
            "label": f"[CHA] Apologize to {teacher_name} and claim you're delivering a homeroom handout",
            "stat": "CHA",
            "requirement": 8,
            "intent": "hs_campus_event_action",
            "hs_event_action": "classroom_excuse",
        },
        {
            "label": f"[INT] Cite a believable faculty office request to {teacher_name}",
            "stat": "INT",
            "requirement": 8,
            "intent": "hs_campus_event_action",
            "hs_event_action": "classroom_faculty_cover",
        },
        {
            "label": "[AGI] Duck back out into the corridor before the lecture halts",
            "stat": "AGI",
            "requirement": 7,
            "intent": "hs_campus_event_action",
            "hs_event_action": "classroom_slip_out",
        },
    ]

    directive = (
        f"[ACTIVE LECTURE INTERRUPTION — {grade_label.upper()} CLASSROOM]:\n"
        f"- Class is actively in session! Only {grade_label} students belong here right now, and {teacher_name} ({teacher_role}) "
        f"pauses mid-lecture at the chalkboard as the classroom door opens.\n"
        f"- Rows of {grade_label} students turn in their seats to stare at the player.\n"
        f"- End the scene at the threshold as {teacher_name} asks what business the player has interrupting class."
    )
    return {
        "event_type": "classroom_intrusion",
        "teacher_name": teacher_name,
        "teacher_role": teacher_role,
        "grade_label": grade_label,
        "facility_id": fid,
        "directive": directive,
        "choices": choices,
    }


# ---------------------------------------------------------------------------
# 2. School Infirmary Nurse & Official Sick / Early-Dismissal Pass
# ---------------------------------------------------------------------------

def grant_infirmary_sick_pass(session: Dict[str, Any], current_day: int) -> None:
    """Grants an official School Nurse Sick / Early-Dismissal Pass for `current_day`."""
    sess_id = int(session.get("id") or 0)
    session["infirmary_pass_day"] = int(current_day)
    if sess_id:
        _persist_social_state(session, extra_fields={"infirmary_pass_day": int(current_day)})
        try:
            db.update_world_node_state(
                sess_id,
                "loc_school_gate",
                {"truancy_unlocked_day": int(current_day), "last_unlock_reason": "infirmary_sick_pass"},
            )
        except Exception:
            pass


def evaluate_infirmary_nurse_interaction(
    session: Dict[str, Any],
    scen_key: str,
    fac_id: str,
    current_day: int,
    current_minute: int,
) -> Optional[Dict[str, Any]]:
    """
    On weekdays 08:00–17:00 inside `loc_school_infirmary`, stages the School Nurse and offers
    curtained bed rest plus a [CHA] check for an official Sick / Early-Dismissal Pass.
    """
    if not is_school_scenario(scen_key) or is_weekend(current_day):
        return None
    if str(fac_id or "").lower() != "loc_school_infirmary":
        return None
    safe_min = int(current_minute or 0) % 1440
    if not (480 <= safe_min < 1020):
        return None

    sess_id = int(session.get("id") or 0)
    nurse_name = " the School Nurse"
    try:
        for r in (db.get_school_roster(sess_id) or []):
            if "nurse" in str(r.get("role") or "").lower():
                nurse_name = str(r.get("name") or "School Nurse")
                break
    except Exception:
        nurse_name = "School Nurse"

    has_pass_today = int(session.get("infirmary_pass_day") or 0) >= int(current_day)
    choices: List[Dict[str, Any]] = [
        {
            "label": "Rest quietly on a curtained infirmary bed to recover composure",
            "stat": "NONE",
            "requirement": 0,
            "intent": "hs_campus_event_action",
            "hs_event_action": "infirmary_rest",
        }
    ]
    if not has_pass_today:
        choices.insert(
            0,
            {
                "label": f"[CHA] Convince {nurse_name} to sign a Sick / Early-Dismissal Pass",
                "stat": "CHA",
                "requirement": 8,
                "intent": "hs_campus_event_action",
                "hs_event_action": "infirmary_sick_pass",
            },
        )

    directive = (
        f"[SCHOOL INFIRMARY — NURSE ON DUTY (08:00–17:00)]:\n"
        f"- {nurse_name} is on duty at the medical desk surrounded by antiseptic cabinets and white privacy curtains.\n"
        + (
            "- The player already holds a signed Sick / Early-Dismissal Pass for today."
            if has_pass_today
            else "- The player may rest on a curtained cot or try convincing the Nurse to sign an official Sick / Early-Dismissal Pass."
        )
    )
    return {
        "event_type": "infirmary_visit",
        "nurse_name": nurse_name,
        "has_pass_today": has_pass_today,
        "directive": directive,
        "choices": choices,
    }


# ---------------------------------------------------------------------------
# 3. Gendered Restrooms & Athletic Shower Rooms
# ---------------------------------------------------------------------------

def _detect_gendered_facility_kind(fac_id: str, location_str: str) -> Tuple[str, str]:
    """
    Returns (target_gender, facility_kind) where target_gender in ('male', 'female', '')
    and facility_kind in ('restroom', 'shower', '').
    """
    fid = str(fac_id or "").lower()
    loc_low = str(location_str or "").lower()
    # Check female markers BEFORE male markers so "women's" never substring-matches "men's"
    if fid == "loc_female_restroom" or "girls' restroom" in loc_low or "women's restroom" in loc_low:
        return "female", "restroom"
    if fid == "loc_male_restroom" or "boys' restroom" in loc_low or "men's restroom" in loc_low:
        return "male", "restroom"
    if fid == "loc_female_shower_room" or "women's locker" in loc_low or "girls' locker" in loc_low or "women's shower" in loc_low:
        return "female", "shower"
    if fid == "loc_male_shower_room" or "men's locker" in loc_low or "boys' locker" in loc_low or "men's shower" in loc_low:
        return "male", "shower"
    return "", ""


def _has_consenting_partner_exemption(
    session: Dict[str, Any],
    session_id: int,
    target_gender: str,
    fac_id: str,
    location_str: str,
) -> bool:
    """Exempts wrong-gender entry if accompanied/invited by a consenting romantic partner."""
    active_dps = session.get("dialogue_partners") or ([session["dialogue_partner"]] if session.get("dialogue_partner") else [])
    for dp in active_dps:
        if not dp:
            continue
        dp_key = rg.canonical_person_key(str(dp))
        curr_p = rg.get_current_partner(session_id, dp_key)
        if curr_p and rg.is_player_person_key(curr_p.get("person_key")):
            return True
        c_row = db.get_contact(session_id, str(dp).lower().replace(" ", "_"), 0)
        if c_row and str(c_row.get("track") or "").lower() == "romantic":
            return True

    for appt in (db.get_active_rendezvous_appointments(session_id) or []):
        t_nid = str(appt.get("target_node_id") or "").lower()
        r_loc = str(appt.get("rendezvous_location") or "").lower()
        if (fac_id and fac_id.lower() in t_nid) or (location_str and location_str.split("➔")[-1].strip().lower() in r_loc):
            return True
    return False


def evaluate_gendered_room_hazard(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    fac_id: str,
    node_id: str,
    location_str: str,
    current_day: int,
    current_minute: int,
    rng_roll_override: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handles both own-gender shower staging/refresh choices AND opposite-gender restroom/shower
    walk-in / occupancy confrontations.
    """
    sess_id = int(session.get("id") or 0)
    scen_key = str(session.get("scenario") or "high_school_drama")
    target_gender, fac_kind = _detect_gendered_facility_kind(fac_id, location_str)
    if not target_gender or not fac_kind:
        return None

    char_id, player_name, player_gender = _extract_lead_player(session, party)
    safe_min = int(current_minute or 0) % 1440

    # Stage scheduled athletes in shower/locker rooms during morning/afternoon practice windows
    roster = db.get_school_roster(sess_id) if sess_id else []
    scheduled_occupants: List[Dict[str, Any]] = []
    if roster:
        is_athletic_shower_window = (435 <= safe_min <= 470) or (900 <= safe_min <= 1170)
        for r in roster:
            if str(r.get("gender") or "").lower() != target_gender:
                continue
            if str(r.get("grade") or "") == "Faculty":
                continue
            club_low = str(r.get("club") or "").lower()
            role_low = str(r.get("role") or "").lower()
            if fac_kind == "shower":
                if is_athletic_shower_window and any(k in f"{club_low} {role_low}" for k in ("swim", "athletic", "track", "basketball", "martial", "kendo", "tennis", "sprinter", "runner")):
                    scheduled_occupants.append(r)
            else:
                # Restrooms have light rotation between classes / lunch
                if not is_weekend(current_day) and ((465 <= safe_min <= 480) or (720 <= safe_min <= 775) or (900 <= safe_min <= 960)):
                    if _det_int(f"restroom_occ:{sess_id}:{current_day}:{safe_min // 30}:{r.get('npc_id')}", 8) == 0:
                        scheduled_occupants.append(r)

    if fac_kind == "shower" and scheduled_occupants and sess_id:
        phys_st = db.get_session_physical_state(sess_id) or {"actors": {}}
        stage_shower_room_actors(
            phys_st,
            session_id=sess_id,
            location_str=location_str,
            node_id=node_id or fac_id,
            npc_records=[
                {"person_key": rg.canonical_person_key(o["name"]), "name": o["name"], "gender": o.get("gender", target_gender)}
                for o in scheduled_occupants[:2]
            ],
            seed=int(session.get("turn_count") or 0),
        )

    is_opposite_gender = (
        player_gender in ("male", "female")
        and target_gender in ("male", "female")
        and player_gender != target_gender
    )

    if not is_opposite_gender:
        # Own-gender shower room: offer functional refresh wash-up if disheveled/sweaty or in shower room
        if fac_kind == "shower":
            choices = [
                {
                    "label": "Wash up & freshen yourself in the warm showers",
                    "stat": "NONE",
                    "requirement": 0,
                    "intent": "hs_campus_event_action",
                    "hs_event_action": "player_shower_refresh",
                }
            ]
            occ_note = ""
            if scheduled_occupants:
                names = ", ".join(o["name"] for o in scheduled_occupants[:2])
                occ_note = f" Steam curls through the tiled room as {names} towels off after practice."
            return {
                "event_type": "own_shower_room",
                "directive": f"[LOCKER & SHOWER ROOM]: Warm steam hangs in the tiled locker room.{occ_note}",
                "choices": choices,
            }
        return None

    # Opposite-gender entry! Check romantic partner exemption first
    if sess_id and _has_consenting_partner_exemption(session, sess_id, target_gender, fac_id, location_str):
        return {
            "event_type": "partner_accompanied_gendered_room",
            "directive": (
                f"[ILLICIT SHARED ENTRY]: {player_name} slips inside {location_str.split('➔')[-1].strip()} "
                f"alongside a consenting partner, keeping voices hushed against outside footsteps."
            ),
            "choices": [],
        }

    # Determine occupancy or walk-in roll
    witness: Optional[Dict[str, Any]] = scheduled_occupants[0] if scheduled_occupants else None
    if not witness:
        if 420 <= safe_min < 1170:
            base_prob = 0.20
        elif 1170 <= safe_min < 1320:
            base_prob = 0.05
        else:
            base_prob = 0.0

        st_state = session.get("stealth_state") or {}
        if isinstance(st_state, dict) and st_state.get("active"):
            base_prob *= 0.5

        roll = rng_roll_override if rng_roll_override is not None else _det_float(
            f"gendered_walkin:{sess_id}:{current_day}:{safe_min // 15}:{fac_id}:{session.get('turn_count', 0)}"
        )
        if roll < base_prob and roster:
            same_gen_peers = [
                r for r in roster
                if str(r.get("gender") or "").lower() == target_gender and str(r.get("grade") or "") != "Faculty"
            ]
            if same_gen_peers:
                pick_idx = _det_int(f"gendered_witness:{sess_id}:{current_day}:{safe_min}:{fac_id}", len(same_gen_peers))
                witness = same_gen_peers[pick_idx]

    if not witness:
        return {
            "event_type": "gendered_room_tense_empty",
            "directive": (
                f"[OPPOSITE-GENDER FACILITY — UNSPOTTED FOR NOW]: {player_name} is inside the opposite-gender "
                f"{'locker & shower room' if fac_kind == 'shower' else 'restroom'}. No one is inside right this second, "
                f"but footsteps could approach the door at any moment."
            ),
            "choices": [],
        }

    w_name = str(witness.get("name") or "A startled student")
    w_npc_id = str(witness.get("npc_id") or w_name.lower().replace(" ", "_"))
    w_contact = db.get_contact(sess_id, w_npc_id, char_id) if sess_id else None
    w_score = int((w_contact or {}).get("relationship_score") or 0)
    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)

    # NSFW teasing reaction when caught alone by a high-affinity or bold/uninhibited NPC
    if is_nsfw and len(scheduled_occupants) <= 1 and (w_score >= 45 or _is_bold_or_uninhibited_npc(w_contact or witness)):
        return {
            "event_type": "gendered_room_teasing",
            "witness_name": w_name,
            "witness_npc_id": w_npc_id,
            "directive": (
                f"[OPPOSITE-GENDER {'SHOWER' if fac_kind == 'shower' else 'RESTROOM'} — PLAYFUL DISCOVERY]:\n"
                f"- {w_name} catches {player_name} stepping into the {location_str.split('➔')[-1].strip()}.\n"
                + (
                    f"- {w_name} is damp from the showers with a towel clutched loosely, blinking in surprise before curving a teasing, unbothered smirk rather than screaming for a teacher.\n"
                    if fac_kind == "shower"
                    else f"- Instead of reporting {player_name}, {w_name} leans against the sink counter with an amused, teasing arch of their brow, asking if {player_name} wandered in looking for trouble.\n"
                )
            ),
            "choices": [
                {
                    "label": f"[CHA] Flirt back & lean into {w_name}'s teasing",
                    "stat": "CHA",
                    "requirement": 8,
                    "intent": "hs_campus_event_action",
                    "hs_event_action": "gendered_tease_flirt",
                    "witness_name": w_name,
                    "witness_npc_id": w_npc_id,
                },
                {
                    "label": "Excuse yourself with a sheepish grin and step back outside",
                    "stat": "NONE",
                    "requirement": 0,
                    "intent": "hs_campus_event_action",
                    "hs_event_action": "gendered_polite_exit",
                    "facility_kind": fac_kind,
                },
            ],
        }

    # Standard strong confrontation!
    st = _get_social_state(session)
    st["pending_gendered_confrontation"] = {
        "witness_name": w_name,
        "witness_npc_id": w_npc_id,
        "facility_kind": fac_kind,
        "facility_id": fac_id,
        "location_display": location_str,
    }
    _persist_social_state(session)

    shower_detail = (
        f"{w_name} is mid-change amid the steamy lockers and whirls around clutching a towel, cheeks blazing crimson!"
        if fac_kind == "shower"
        else f"{w_name} freezes by the mirrors and stares at {player_name} in shock, demanding to know why they're in here!"
    )
    choices = [
        {
            "label": f"[CHA] Apologize profusely to {w_name} & claim an honest wrong-door mistake",
            "stat": "CHA",
            "requirement": 9,
            "intent": "hs_campus_event_action",
            "hs_event_action": "gendered_apologize",
            "witness_name": w_name,
            "witness_npc_id": w_npc_id,
            "facility_kind": fac_kind,
        },
        {
            "label": f"[INT] Offer a quick, plausible maintenance/errand excuse to {w_name}",
            "stat": "INT",
            "requirement": 10,
            "intent": "hs_campus_event_action",
            "hs_event_action": "gendered_errand_cover",
            "witness_name": w_name,
            "witness_npc_id": w_npc_id,
            "facility_kind": fac_kind,
        },
        {
            "label": "[AGI] Bolt out the door before anyone can raise an uproar",
            "stat": "AGI",
            "requirement": 9,
            "intent": "hs_campus_event_action",
            "hs_event_action": "gendered_bolt_out",
            "witness_name": w_name,
            "witness_npc_id": w_npc_id,
            "facility_kind": fac_kind,
        },
    ]
    return {
        "event_type": "gendered_room_confrontation",
        "witness_name": w_name,
        "witness_npc_id": w_npc_id,
        "facility_kind": fac_kind,
        "directive": (
            f"[OPPOSITE-GENDER {'SHOWER' if fac_kind == 'shower' else 'RESTROOM'} CONFRONTATION!]:\n"
            f"- {shower_detail}\n"
            f"- End the narration right at the moment of confrontation so the player must react!"
        ),
        "choices": choices,
    }


def resolve_gendered_room_confrontation(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    action: Dict[str, Any],
    succeeded: bool,
) -> Dict[str, Any]:
    """
    Resolves a player's skill check response to an opposite-gender restroom/shower confrontation.
    On failure: ejects to corridor/gymnasium, drops witness affinity (-12), drops Student Council rep (-10),
    and posts a `#CampusScandal` rumor to the Smartphone Gossip Feed.
    """
    sess_id = int(session.get("id") or 0)
    scen_key = str(session.get("scenario") or "high_school_drama")
    char_id, player_name, _ = _extract_lead_player(session, party)

    st = _get_social_state(session)
    pending = st.pop("pending_gendered_confrontation", None) or {}
    _persist_social_state(session)

    w_name = str(action.get("witness_name") or pending.get("witness_name") or "A witness")
    w_npc_id = str(action.get("witness_npc_id") or pending.get("witness_npc_id") or w_name.lower().replace(" ", "_"))
    fac_kind = str(action.get("facility_kind") or pending.get("facility_kind") or "restroom")
    loc_disp = str(pending.get("location_display") or session.get("current_location") or "the restroom")

    if fac_kind == "shower":
        ath_zone = get_session_athletics_complex_name(sess_id, scen_key) or "School Grounds & Athletics"
        eject_node_id = "loc_gymnasium"
        eject_loc = f"{ath_zone} ➔ Main Gymnasium"
    else:
        sch_zone = get_session_school_name(sess_id, scen_key) or "Main Academic Building"
        eject_node_id = "loc_school_hallway"
        eject_loc = f"{sch_zone} ➔ Main Corridor & Lockers"

    if succeeded:
        return {
            "ejected": True,
            "override_node_id": eject_node_id,
            "override_location": eject_loc,
            "scandal_posted": False,
            "directive": (
                f"[CONFRONTATION DEFUSED]: {player_name} smoothly defuses the awkwardness with {w_name} "
                f"and steps briskly back out into {eject_loc} without a scandal breaking out."
            ),
        }

    # Failure consequences!
    if sess_id:
        try:
            db.update_relationship_score(sess_id, w_npc_id, -12, character_id=char_id)
            if char_id != 0:
                db.update_relationship_score(sess_id, w_npc_id, -12, character_id=0)
        except Exception:
            pass
        _adjust_student_council_reputation(sess_id, -10)
        gossip_post = queue_witness_gossip_post(
            session_id=sess_id,
            witness_name=w_name,
            player_name=player_name,
            partner_name="",
            location_display=loc_disp,
            event_kind="restroom_intrusion",
        )
    else:
        gossip_post = None

    return {
        "ejected": True,
        "override_node_id": eject_node_id,
        "override_location": eject_loc,
        "scandal_posted": True,
        "gossip_post": gossip_post,
        "directive": (
            f"[CONFRONTATION FAILED — EJECTED & REPORTED!]:\n"
            f"- {w_name} doesn't buy {player_name}'s excuse at all, shouting indignantly and chasing {player_name} straight out into {eject_loc}!\n"
            f"- Word of the incident spreads fast toward the Student Council and campus gossip feed."
        ),
    }


# ---------------------------------------------------------------------------
# 4. NSFW Discreet Location Couple Encounters & ~25% Secret Affair Twist
# ---------------------------------------------------------------------------

def evaluate_discreet_couple_encounter(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    node_id: str,
    fac_id: str,
    location_str: str,
    current_day: int,
    current_minute: int,
    *,
    rng_roll_override: Optional[float] = None,
    affair_roll_override: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    In NSFW scenarios, visiting an `is_discreet` spot has a deterministic 15% chance
    (cached per `(day, time_block, node_id)` with a soft cap of 2 discoveries/day)
    to stumble upon a couple across 4 activity tiers — with a ~25% twist that one of
    them is cheating on their canonical partner (`TIETYPE_AFFAIR`).
    """
    sess_id = int(session.get("id") or 0)
    scen_key = str(session.get("scenario") or "high_school_drama")
    if not sess_id or not scenario_data.is_nsfw_scenario(scen_key):
        return None

    check_nid = node_id or fac_id
    if not is_discreet_venue(location_str, check_nid, session_id=sess_id):
        return None

    # Do not interrupt if player is actively arriving with a dialogue/date partner
    if session.get("dialogue_partners") or session.get("dialogue_partner"):
        return None

    safe_min = int(current_minute or 0) % 1440
    time_block = safe_min // 180  # 3-hour blocks
    cache_key = f"{current_day}:{time_block}:{check_nid or location_str}"

    st = _get_social_state(session)
    cache = st.setdefault("discreet_encounters_cache", {})
    daily_counts = st.setdefault("discreet_daily_counts", {})
    day_key = str(current_day)

    if rng_roll_override is None and cache_key in cache:
        cached_val = cache[cache_key]
        return cached_val if isinstance(cached_val, dict) else None

    if int(daily_counts.get(day_key) or 0) >= 2 and rng_roll_override is None:
        cache[cache_key] = False
        _persist_social_state(session)
        return None

    roll = rng_roll_override if rng_roll_override is not None else _det_float(f"discreet_couple:{sess_id}:{cache_key}")
    if roll >= 0.15:
        cache[cache_key] = False
        _persist_social_state(session)
        return None

    # Ensure canonical peer couples exist so we can draw authentic couples or secret affairs
    couples = rg.ensure_canonical_peer_couples(sess_id, scen_key=scen_key)
    roster = db.get_school_roster(sess_id) or []
    peer_pool = [
        r for r in roster
        if str(r.get("grade") or "") in ("Freshman", "Sophomore", "Junior", "Senior", "Youth Peer")
    ]

    affair_roll = affair_roll_override if affair_roll_override is not None else _det_float(f"discreet_affair:{sess_id}:{cache_key}")
    is_affair = bool(couples and len(peer_pool) >= 4 and affair_roll < 0.25)

    tier_idx = _det_int(f"discreet_tier:{sess_id}:{cache_key}", len(DISCREET_ACTIVITY_TIERS))
    if is_affair and tier_idx == 0:
        tier_idx = 2  # Affairs are unambiguously romantic/frisky so the discovery carries dramatic weight!
    activity = DISCREET_ACTIVITY_TIERS[tier_idx]

    reactions = ["flustered", "annoyed", "bold_teasing"]
    reaction = reactions[_det_int(f"discreet_react:{sess_id}:{cache_key}", len(reactions))]

    actor_a_name = ""
    actor_a_key = ""
    actor_b_name = ""
    actor_b_key = ""
    betrayed_name = ""
    betrayed_key = ""

    if is_affair and couples:
        cp = couples[_det_int(f"affair_cp:{sess_id}:{cache_key}", len(couples))]
        pick_b_side = (_det_int(f"affair_side:{sess_id}:{cache_key}", 2) == 1)
        if pick_b_side:
            actor_a_key = cp["person_b_key"]
            actor_a_name = cp["person_b_name"]
            actor_a_role = cp.get("person_b_role") or "Student"
            actor_a_gender = cp.get("person_b_gender") or ""
            betrayed_key = cp["person_a_key"]
            betrayed_name = cp["person_a_name"]
        else:
            actor_a_key = cp["person_a_key"]
            actor_a_name = cp["person_a_name"]
            actor_a_role = cp.get("person_a_role") or "Student"
            actor_a_gender = cp.get("person_a_gender") or ""
            betrayed_key = cp["person_b_key"]
            betrayed_name = cp["person_b_name"]

        # Pick an illicit secret lover (not actor_a, not betrayed_partner, not sibling)
        _, raw_sur_a = namegen.extract_first_and_last_name(actor_a_name)
        base_sur_a = namegen.normalize_base_surname(raw_sur_a).lower()
        lover_cands = []
        for p in peer_pool:
            pk = rg.canonical_person_key(p.get("name") or "")
            if pk in (actor_a_key, betrayed_key) or rg.is_player_person_key(pk):
                continue
            _, raw_sur_p = namegen.extract_first_and_last_name(p.get("name") or "")
            if base_sur_a and namegen.normalize_base_surname(raw_sur_p).lower() == base_sur_a:
                continue
            if str(p.get("sibling_name") or "").strip().lower() == actor_a_name.lower():
                continue
            lover_cands.append(p)

        if lover_cands:
            lover = lover_cands[_det_int(f"affair_lover:{sess_id}:{cache_key}", len(lover_cands))]
            actor_b_name = lover["name"]
            actor_b_key = rg.canonical_person_key(actor_b_name)
            rg.get_or_create_person(
                sess_id,
                actor_a_name,
                person_key=actor_a_key,
                gender=actor_a_gender,
                role=actor_a_role,
                origin="roster",
            )
            rg.get_or_create_person(
                sess_id,
                actor_b_name,
                person_key=actor_b_key,
                gender=lover.get("gender") or "",
                role=lover.get("role") or "Student",
                origin="roster",
            )
            rg.form_tie(
                sess_id,
                actor_a_key,
                actor_b_key,
                rg.TIETYPE_AFFAIR,
                closeness=65,
                origin="discreet_affair",
                turn=int(session.get("turn_count") or 0),
                materialize=True,
            )
        else:
            is_affair = False

    if not is_affair:
        if couples:
            cp = couples[_det_int(f"canon_cp_spot:{sess_id}:{cache_key}", len(couples))]
            actor_a_key = cp["person_a_key"]
            actor_a_name = cp["person_a_name"]
            actor_b_key = cp["person_b_key"]
            actor_b_name = cp["person_b_name"]
        elif len(peer_pool) >= 2:
            i1 = _det_int(f"rand_cp1:{sess_id}:{cache_key}", len(peer_pool))
            i2 = (i1 + 1 + _det_int(f"rand_cp2:{sess_id}:{cache_key}", max(1, len(peer_pool) - 1))) % len(peer_pool)
            actor_a_name = peer_pool[i1]["name"]
            actor_a_key = rg.canonical_person_key(actor_a_name)
            actor_b_name = peer_pool[i2]["name"]
            actor_b_key = rg.canonical_person_key(actor_b_name)
        else:
            return None

    loc_leaf = str(location_str or "this secluded spot").split("➔")[-1].strip()
    reaction_prose = {
        "flustered": f"Both freeze in mortified shock, scrambling with scarlet faces to straighten their clothes as {actor_a_name} stammers!",
        "annoyed": f"{actor_a_name} glares sharply over {actor_b_name}'s shoulder, snapping in a hushed hiss to ask if anyone knocks anymore!",
        "bold_teasing": f"Rather than panicking, {actor_a_name} holds {actor_b_name} close and meets the player's eyes with a slow, shameless smirk.",
    }[reaction]

    if is_affair:
        choices = [
            {
                "label": f"[AGI] Slip away quietly before {actor_a_name} & {actor_b_name} realize who saw them",
                "stat": "AGI",
                "requirement": 8,
                "intent": "hs_campus_event_action",
                "hs_event_action": "affair_slip_away",
            },
            {
                "label": f"[CHA] Promise {actor_a_name} & {actor_b_name} your discretion so they owe you a favor",
                "stat": "CHA",
                "requirement": 8,
                "intent": "hs_campus_event_action",
                "hs_event_action": "affair_promise_discretion",
            },
            {
                "label": f"[INT] Expose {actor_a_name}'s secret affair with {actor_b_name} to {betrayed_name}",
                "stat": "INT",
                "requirement": 9,
                "intent": "hs_campus_event_action",
                "hs_event_action": "affair_expose",
            },
            {
                "label": f"[CHA] Make a bold proposition to join {actor_a_name} & {actor_b_name} (or leverage their secret)",
                "stat": "CHA",
                "requirement": 11,
                "intent": "hs_campus_event_action",
                "hs_event_action": "affair_bold_proposition",
            },
        ]
        directive = (
            f"[DISCREET SPOT DISCOVERY — SECRET AFFAIR CAUGHT RED-HANDED!]:\n"
            f"- Stepping into {loc_leaf}, the player stumbles right onto {actor_a_name} and {actor_b_name}, who are {activity['summary']}!\n"
            f"- SCANDAL TWIST: {actor_a_name} is canonically dating {betrayed_name}—meaning this tryst with {actor_b_name} is a secret affair!\n"
            f"- {reaction_prose}\n"
            f"- Hold the tension on the moment of discovery so the player can decide how to handle their explosive secret."
        )
        callout = (
            f"\n\n🤫 **[SECRET AFFAIR DISCOVERED]**: You caught **{actor_a_name}** (currently dating **{betrayed_name}**) "
            f"and **{actor_b_name}** {activity['summary']}!"
        )
    else:
        choices = [
            {
                "label": f"[AGI] Slip back out of {loc_leaf} quietly without making it awkward",
                "stat": "AGI",
                "requirement": 7,
                "intent": "hs_campus_event_action",
                "hs_event_action": "couple_slip_away",
            },
            {
                "label": f"[CHA] Play it cool and smooth over walking in on {actor_a_name} & {actor_b_name}",
                "stat": "CHA",
                "requirement": 8,
                "intent": "hs_campus_event_action",
                "hs_event_action": "couple_play_cool",
            },
            {
                "label": f"[CHA] Boldly tease {actor_a_name} & {actor_b_name} instead of backing down",
                "stat": "CHA",
                "requirement": 10,
                "intent": "hs_campus_event_action",
                "hs_event_action": "couple_bold_tease",
            },
        ]
        directive = (
            f"[DISCREET SPOT COUPLE ENCOUNTER]:\n"
            f"- Inside {loc_leaf}, the player walks right in on {actor_a_name} and {actor_b_name}, who are {activity['summary']}.\n"
            f"- {reaction_prose}\n"
            f"- Let the player choose how to handle walking in on the couple."
        )
        callout = (
            f"\n\n👀 **[SECLUDED ENCOUNTER]**: You walked in on **{actor_a_name}** and **{actor_b_name}** {activity['summary']}."
        )

    event_payload: Dict[str, Any] = {
        "event_type": "discreet_affair" if is_affair else "discreet_couple",
        "is_affair": is_affair,
        "activity_tier": activity["tier_id"],
        "activity_summary": activity["summary"],
        "reaction": reaction,
        "actor_a_key": actor_a_key,
        "actor_a_name": actor_a_name,
        "actor_b_key": actor_b_key,
        "actor_b_name": actor_b_name,
        "betrayed_key": betrayed_key,
        "betrayed_name": betrayed_name,
        "location_display": location_str,
        "directive": directive,
        "callout": callout,
        "choices": choices,
    }

    daily_counts[day_key] = int(daily_counts.get(day_key) or 0) + 1
    cache[cache_key] = event_payload
    st["pending_discreet_encounter"] = event_payload
    _persist_social_state(session)
    return event_payload


def resolve_discreet_couple_action(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    action_key: str,
    succeeded: bool,
) -> Dict[str, Any]:
    """Resolves player's skill-check choice on a discreet couple or secret affair encounter."""
    sess_id = int(session.get("id") or 0)
    char_id, player_name, _ = _extract_lead_player(session, party)

    st = _get_social_state(session)
    enc = st.pop("pending_discreet_encounter", None) or {}
    _persist_social_state(session)

    a_name = str(enc.get("actor_a_name") or "the student")
    a_key = str(enc.get("actor_a_key") or rg.canonical_person_key(a_name))
    b_name = str(enc.get("actor_b_name") or "their partner")
    b_key = str(enc.get("actor_b_key") or rg.canonical_person_key(b_name))
    betrayed_name = str(enc.get("betrayed_name") or "their partner")
    betrayed_key = str(enc.get("betrayed_key") or rg.canonical_person_key(betrayed_name))
    loc_disp = str(enc.get("location_display") or session.get("current_location") or "campus")

    if action_key in ("affair_slip_away", "couple_slip_away"):
        if succeeded:
            return {
                "directive": (
                    f"[DISCREET EXIT — UNSEEN]: {player_name} eases backward out of sight without a sound, "
                    f"leaving {a_name} and {b_name} breathless and unsure anyone actually saw their faces."
                ),
            }
        return {
            "directive": (
                f"[AWKWARD STUMBLE]: A floorboard creaks as {player_name} tries backing out—{a_name} and {b_name} "
                f"definitely spot {player_name} retreating in flustered silence!"
            ),
        }

    if action_key == "affair_promise_discretion":
        if succeeded and sess_id:
            for k, nm in ((a_key, a_name), (b_key, b_name)):
                try:
                    db.upsert_contact(sess_id, k, nm, character_id=char_id, delta_score=8)
                    if char_id != 0:
                        db.upsert_contact(sess_id, k, nm, character_id=0, delta_score=8)
                except Exception:
                    pass
            try:
                from db.memory import add_commitment
                curr_day, curr_min, _ = db.get_session_time(sess_id)
                add_commitment(
                    session_id=sess_id,
                    commitment_type="promise",
                    title=f"Sworn Discretion: {a_name} & {b_name}",
                    description=f"Promised to keep {a_name} and {b_name}'s secret tryst hidden from {betrayed_name}; both owe you a quiet favor.",
                    source_entity=a_key,
                    target_entity="player",
                    scheduled_day=curr_day,
                    start_minute=curr_min,
                    is_confidential=True,
                )
            except Exception:
                pass
            return {
                "promised_discretion": True,
                "directive": (
                    f"[SECRET PACT SEALED]: {a_name} and {b_name} exhale in visible relief as {player_name} promises total discretion. "
                    f"Both murmur grateful thanks—they now owe {player_name} a genuine personal favor."
                ),
            }
        return {
            "promised_discretion": False,
            "directive": (
                f"[UNEASY STANDOFF]: {a_name} eyes {player_name} warily, unconvinced their secret with {b_name} is truly safe."
            ),
        }

    if action_key == "affair_expose":
        if succeeded and sess_id:
            turn_now = int(session.get("turn_count") or 0)
            rg.end_tie(sess_id, a_key, betrayed_key, rg.TIETYPE_DATING, turn=turn_now, reason="exposed_affair", materialize=True)
            rg.end_tie(sess_id, a_key, b_key, rg.TIETYPE_AFFAIR, turn=turn_now, reason="exposed_affair", materialize=True)
            try:
                db.upsert_contact(sess_id, betrayed_key, betrayed_name, character_id=char_id, delta_score=10)
                db.upsert_contact(sess_id, a_key, a_name, character_id=char_id, delta_score=-15)
            except Exception:
                pass
            gossip_post = queue_witness_gossip_post(
                session_id=sess_id,
                witness_name="Campus Rumor Mill",
                player_name=a_name,
                partner_name=b_name,
                location_display=loc_disp,
                event_kind="affair_exposed",
            )
            return {
                "affair_exposed": True,
                "gossip_post": gossip_post,
                "directive": (
                    f"[SECRET AFFAIR EXPOSED — BREAKUP BOMBSHELL!]:\n"
                    f"- {player_name} brings undeniable proof of {a_name} and {b_name}'s secret tryst to {betrayed_name}!\n"
                    f"- {betrayed_name} immediately dumps {a_name} on the spot, grateful to {player_name} for the truth while campus phones buzz with the breakup bombshell!"
                ),
            }
        return {
            "affair_exposed": False,
            "directive": (
                f"[EXPOSURE FUMBLED]: {a_name} and {b_name} scramble to cover their tracks and spin a quick alibi before {player_name} can prove anything."
            ),
        }

    if action_key in ("affair_bold_proposition", "couple_bold_tease", "couple_play_cool"):
        if succeeded:
            if sess_id:
                for k, nm in ((a_key, a_name), (b_key, b_name)):
                    try:
                        db.upsert_contact(sess_id, k, nm, character_id=char_id, delta_score=6)
                    except Exception:
                        pass
            if action_key == "affair_bold_proposition":
                return {
                    "bold_joined": True,
                    "dialogue_partners": [a_name, b_name],
                    "directive": (
                        f"[BOLD PROPOSITION ACCEPTED]: {player_name}'s audacious confidence disarms both {a_name} and {b_name}. "
                        f"Exchanging a breathless, thrilled glance, they pull {player_name} inside and click the door shut behind them."
                    ),
                }
            return {
                "directive": (
                    f"[SMOOTH CHARM]: {player_name}'s easygoing confidence melts the awkwardness right away; "
                    f"{a_name} and {b_name} laugh breathless and relaxed."
                ),
            }
        return {
            "directive": (
                f"[BRUSHED OFF]: Flushed and defensive, {a_name} and {b_name} hastily gather their things and usher {player_name} back from their private corner."
            ),
        }

    return {"directive": ""}


# ---------------------------------------------------------------------------
# 5. Unified Pre-Turn & Post-Choice Orchestrator for Turn Pipeline
# ---------------------------------------------------------------------------

def evaluate_high_school_turn_events(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    actions: Optional[List[Any]],
    *,
    effective_location: str = "",
    effective_node_id: str = "",
) -> Dict[str, Any]:
    """
    Single deterministic entry point invoked by `game_engine/turn/core.py`:
    1. Resolves any explicit `hs_campus_event_action` or freeform shower wash-up in `actions`.
    2. Evaluates arrival hazards/encounters at `effective_location` / `effective_node_id`.
    """
    out: Dict[str, Any] = {
        "directives": [],
        "choices": [],
        "callout": "",
        "override_location": "",
        "override_node_id": "",
        "dialogue_partners": [],
    }
    if not isinstance(session, dict) or not session.get("id"):
        return out

    sess_id = int(session["id"])
    scen_key = str(session.get("scenario") or "")
    if not is_school_scenario(scen_key):
        return out

    curr_day, curr_min, _ = db.get_session_time(sess_id)
    loc_str = str(effective_location or session.get("current_location") or "")
    nid_str = str(effective_node_id or session.get("current_node_id") or "")
    node, parent, fac_id = _resolve_node_and_parent(sess_id, nid_str, loc_str)

    # Step A: Check if player selected an `hs_campus_event_action` or freeform shower wash-up
    first_act = actions[0] if (actions and isinstance(actions[0], dict)) else None
    hs_act_key = str((first_act or {}).get("hs_event_action") or "").strip()
    act_label_low = str((first_act or {}).get("label") or (actions[0] if actions else "") or "").lower()

    if not hs_act_key and is_shower_or_locker_location(loc_str, nid_str or fac_id):
        if any(w in act_label_low for w in ("wash up", "rinse off", "take a shower", "freshen up", "shower")):
            hs_act_key = "player_shower_refresh"

    if hs_act_key and first_act is not None:
        succeeded = _is_check_success(first_act)
        char_id, player_name, _ = _extract_lead_player(session, party)

        if hs_act_key == "infirmary_sick_pass":
            if succeeded:
                grant_infirmary_sick_pass(session, curr_day)
                out["directives"].append(
                    f"[INFIRMARY SICK PASS GRANTED]: {player_name} convinces the School Nurse to sign an official "
                    f"Sick / Early-Dismissal Pass for Day {curr_day}! They are legally excused from lectures and campus gate lockdown today."
                )
            else:
                out["directives"].append(
                    f"[INFIRMARY PASS DENIED]: The School Nurse checks {player_name}'s temperature skeptically, "
                    f"hands over a glass of water, and tells them they're healthy enough for class."
                )
            return out

        if hs_act_key == "infirmary_rest":
            if party:
                p0 = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
                if isinstance(p0, dict) and p0.get("user_id"):
                    try:
                        db.apply_hp_mp_delta(int(p0["user_id"]), hp_delta=5, mp_delta=5)
                    except Exception:
                        pass
            out["directives"].append(
                f"[INFIRMARY BED REST]: {player_name} rests quietly behind a drawn white curtain in the School Infirmary, feeling refreshed and composed."
            )
            return out

        if hs_act_key == "player_shower_refresh":
            _, _, p_gen = _extract_lead_player(session, party)
            apply_player_shower_refresh(
                sess_id,
                party=party,
                action_text=act_label_low or "wash up in shower",
                location_str=loc_str,
                node_id=nid_str or fac_id,
                player_gender=p_gen,
            )
            out["directives"].append(
                f"[SHOWER REFRESH]: {player_name} rinses off beneath the warm athletic showers, washing away sweat and grime and stepping out clean and composed."
            )
            return out

        if hs_act_key in ("classroom_excuse", "classroom_faculty_cover", "classroom_slip_out"):
            sch_zone = get_session_school_name(sess_id, scen_key) or "Main Academic Building"
            hall_loc = f"{sch_zone} ➔ Main Corridor & Lockers"
            if succeeded:
                out["override_location"] = hall_loc
                out["override_node_id"] = "loc_school_hallway"
                out["directives"].append(
                    f"[LECTURE INTERRUPTION SMOOTHED OVER]: {player_name} handles the interruption smoothly and steps back out into {hall_loc} without getting written up."
                )
            else:
                _adjust_student_council_reputation(sess_id, -5)
                out["override_location"] = hall_loc
                out["override_node_id"] = "loc_school_hallway"
                out["directives"].append(
                    f"[CHASTISED OUT OF LECTURE]: The lecturing teacher sees right through {player_name}'s excuse and sternly sends {player_name} back into {hall_loc}."
                )
            return out

        if hs_act_key in ("gendered_apologize", "gendered_errand_cover", "gendered_bolt_out"):
            conf_res = resolve_gendered_room_confrontation(session, party, first_act, succeeded)
            if conf_res.get("override_location"):
                out["override_location"] = conf_res["override_location"]
                out["override_node_id"] = conf_res.get("override_node_id", "")
            if conf_res.get("directive"):
                out["directives"].append(conf_res["directive"])
            return out

        if hs_act_key == "gendered_polite_exit":
            fac_kind = str(first_act.get("facility_kind") or "restroom")
            if fac_kind == "shower":
                ath_zone = get_session_athletics_complex_name(sess_id, scen_key) or "School Grounds & Athletics"
                out["override_node_id"] = "loc_gymnasium"
                out["override_location"] = f"{ath_zone} ➔ Main Gymnasium"
            else:
                sch_zone = get_session_school_name(sess_id, scen_key) or "Main Academic Building"
                out["override_node_id"] = "loc_school_hallway"
                out["override_location"] = f"{sch_zone} ➔ Main Corridor & Lockers"
            out["directives"].append(f"[POLITE EXIT]: {player_name} excuses themselves with a grin and steps back outside.")
            return out

        if hs_act_key == "gendered_tease_flirt":
            w_name = str(first_act.get("witness_name") or "them")
            w_npc_id = str(first_act.get("witness_npc_id") or w_name.lower().replace(" ", "_"))
            if succeeded:
                try:
                    db.upsert_contact(sess_id, w_npc_id, w_name, character_id=char_id, delta_score=6)
                except Exception:
                    pass
                out["dialogue_partners"] = [w_name]
                out["directives"].append(
                    f"[PLAYFUL CHEMISTRY]: {w_name} laughs softly at {player_name}'s bold comeback, stepping closer instead of shooing them out."
                )
            else:
                out["directives"].append(
                    f"[TEASED & SHOOED OUT]: {w_name} rolls their eyes with a smirk and points {player_name} back toward the door."
                )
            return out

        if hs_act_key.startswith("affair_") or hs_act_key.startswith("couple_"):
            dc_res = resolve_discreet_couple_action(session, party, hs_act_key, succeeded)
            if dc_res.get("directive"):
                out["directives"].append(dc_res["directive"])
            if dc_res.get("dialogue_partners"):
                out["dialogue_partners"] = list(dc_res["dialogue_partners"])
            return out

    # Step B: Evaluate new arrival / room events when entering or standing in a High School facility
    prev_nid = str(session.get("previous_node_id") or "")
    just_arrived = bool(nid_str and nid_str != prev_nid)

    # 1. Active-lecture classroom intrusion
    if just_arrived:
        cls_ev = evaluate_classroom_lecture_intrusion(sess_id, scen_key, fac_id, curr_day, curr_min)
        if cls_ev:
            out["directives"].append(cls_ev["directive"])
            out["choices"].extend(cls_ev["choices"])
            return out

    # 2. School Infirmary Nurse interaction
    inf_ev = evaluate_infirmary_nurse_interaction(session, scen_key, fac_id, curr_day, curr_min)
    if inf_ev:
        out["directives"].append(inf_ev["directive"])
        out["choices"].extend(inf_ev["choices"])
        return out

    # 3. Gendered Restroom & Shower Room staging + hazard
    gen_ev = evaluate_gendered_room_hazard(
        session, party, fac_id, nid_str, loc_str, curr_day, curr_min
    )
    if gen_ev:
        if gen_ev.get("directive"):
            out["directives"].append(gen_ev["directive"])
        if gen_ev.get("choices"):
            out["choices"].extend(gen_ev["choices"])
        if gen_ev.get("event_type") in ("gendered_room_confrontation", "gendered_room_teasing"):
            return out

    # 4. NSFW Discreet Location Couple & Secret Affair Encounter
    if just_arrived and is_discreet_venue(loc_str, nid_str or fac_id, session_id=sess_id):
        disc_ev = evaluate_discreet_couple_encounter(
            session, party, nid_str, fac_id, loc_str, curr_day, curr_min
        )
        if disc_ev:
            out["directives"].append(disc_ev["directive"])
            out["choices"].extend(disc_ev["choices"])
            out["callout"] = disc_ev.get("callout") or ""
            return out

    return out
