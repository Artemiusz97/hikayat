from __future__ import annotations

import db
import hashlib
import json
import logging
import sqlite3
import threading
import time
from typing import Any
from ..core import (UnitOfWork, get_conn, is_in_readonly_uow)
from .contacts_enrichment import _enrich_contact_basic_info, _is_empty_info_val, _merge_basic_info_safely
from .households_factions import _parse_household_row, get_household_by_id

log = logging.getLogger(__name__)

def upsert_contact(session_id: int, npc_id: str, name: str, character_id: int = 0,
                   basic_info: dict = None, delta_score: int = 0, track: str = None,
                   new_traits: list = None, new_preferences: list = None, race: str = "", gender: str = "", appearance: dict = None,
                   new_memory: str = None, new_general_memory: str = None, narrative_text: str = "",
                   open_thread: str = "", emotional_tone: str = "", intimate_profile: dict = None,
                   household_role: str | None = None, scenario: str | None = None) -> dict:
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

    sess = None
    if scenario and str(scenario).strip():
        scen = str(scenario).strip()
    else:
        sess = db.get_session(session_id)
        scen = sess.get("scenario", "fantasy") if sess else "fantasy"
    import mechanics.social.relationships as relationships
    import scenario_data
    n_role = (basic_info.get("role") if isinstance(basic_info, dict) else "") or ""
    n_desc = (basic_info.get("description") if isinstance(basic_info, dict) else "") or ""
    n_grade = (basic_info.get("grade") if isinstance(basic_info, dict) else "") or ""
    n_srt = (basic_info.get("social_role_type") if isinstance(basic_info, dict) else "") or ""
    n_age_group = (basic_info.get("age_group") if isinstance(basic_info, dict) else "") or ""
    is_promoted_adult_family = (
        str(household_role or "").strip().lower() in ("father", "mother")
        or bool(isinstance(basic_info, dict) and basic_info.get("is_adult_family"))
    )
    skip_sess_lookup = bool(
        scenario
        and str(scenario).strip()
        and not scenario_data.is_anomalous_incursions_scenario(scen)
        and not scenario_data.is_anomalous_high_school_scenario(scen)
    )
    if not is_promoted_adult_family and not relationships.is_contact_eligible(
        name=name,
        role=n_role,
        description=n_desc,
        scenario=scen,
        session_id=session_id,
        grade=n_grade,
        social_role_type=n_srt,
        age_group=n_age_group,
        is_adult_family=is_promoted_adult_family,
        preloaded_session=sess,
        skip_session_lookup=skip_sess_lookup,
    ):
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
            canonical_gender = cur_info.pop("_canonical_gender", "")
            canonical_race = cur_info.pop("_canonical_race", "")
            if canonical_gender:
                cur_gender = canonical_gender
                cur_info["gender"] = canonical_gender

            existing_dict = dict(existing)
            existing_race = canonical_race or existing_dict.get("race")
            from mechanics.social.races import extract_race_from_text, normalize_race
            inferred_race = canonical_race or race or cur_info.get("race") or extract_race_from_text(narrative_text, scen_key=scen, name=final_name)
            
            # 1. Prefer canonical roster race or explicitly known non-empty, non-human existing race
            if canonical_race:
                cur_race = normalize_race(canonical_race, scen_key=scen, seed=final_name)
            elif existing_race and str(existing_race).strip().lower() not in ("", "unknown", "human"):
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
            if cur_race:
                cur_info["race"] = cur_race

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
            if str(cur_race or "").strip().lower() in ("kitsune:myobu_fox", "ghoul:canid") and cur_track == "romantic":
                cur_track = "platonic"

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
            if cur_app.get("openness") not in (None, "") and not cur_prof.get("erotic_openness"):
                cur_prof["erotic_openness"] = cur_app["openness"]
            cur_app.pop("openness", None)

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
                    openness=str(cur_prof.get("erotic_openness") or cur_prof.get("openness") or "moderate"),
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
            canonical_gender = info.pop("_canonical_gender", "")
            canonical_race = info.pop("_canonical_race", "")
            from mechanics.social.races import extract_race_from_text, normalize_race
            inferred_race = canonical_race or race or info.get("race") or extract_race_from_text(narrative_text, scen_key=scen, name=name)
            
            if inferred_race and str(inferred_race).strip().lower() not in ("", "unknown"):
                cur_race = normalize_race(inferred_race, scen_key=scen, seed=name)
            else:
                fallback_race = normalize_race("", scen_key=scen, seed=name)
                cur_race = fallback_race if fallback_race != "human" else ""
            if cur_race:
                info["race"] = cur_race
            clean_traits, clean_prefs = persona.split_traits_and_preferences(
                new_traits or [],
                new_preferences or [],
                role=info.get("role", ""),
                race=cur_race,
                seed_str=f"{name}_{info.get('description', '')}"
            )
            cur_track = track if (track and str(track).strip()) else "platonic"
            if str(cur_race or "").strip().lower() in ("kitsune:myobu_fox", "ghoul:canid") and str(cur_track).strip().lower() == "romantic":
                cur_track = "platonic"
            cur_gender = canonical_gender or info.get("gender") or gender or ""
            if cur_gender:
                info["gender"] = cur_gender
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
            if app_dict.get("openness") not in (None, "") and not prof_dict.get("erotic_openness"):
                prof_dict["erotic_openness"] = app_dict["openness"]
            app_dict.pop("openness", None)

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
                    openness=str(prof_dict.get("erotic_openness") or prof_dict.get("openness") or "moderate"),
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
    if is_in_readonly_uow():
        return
    ensuring_set = _get_ensuring_scene_set()
    if session_id in ensuring_set:
        return
    ensuring_set.add(session_id)
    try:
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

        for npc in unadded:
            n_name = game_engine._get_npc_name(npc)
            if not n_name or n_name.lower() in enemy_names or n_name.lower() in party_char_names:
                continue

            # A1: If an NPC parent from an existing household appears in-scene, promote them to a Contact
            try:
                import mechanics.social.genealogy as genealogy
                genealogy.maybe_promote_scene_parent(session_id, n_name)
            except Exception:
                pass
    finally:
        ensuring_set.discard(session_id)

def _apply_contact_household_residence(session_id: int, d: dict, hh: dict, scen_key: str) -> None:
    rel = d.get("relations") if isinstance(d.get("relations"), dict) else {}
    if rel.get("cohabiting_family") is False and rel.get("residence_location"):
        return
    try:
        from mechanics.world.locations.realty_catalog import is_anomalous_realty_scenario
        if is_anomalous_realty_scenario(scen_key):
            from mechanics.world.locations.residences import (
                is_adult_special_agent_contact,
                resolve_agent_residence_blueprint,
            )
            if is_adult_special_agent_contact(d):
                bp = resolve_agent_residence_blueprint(int(session_id or 0), d, scen_key=scen_key)
                if bp.get("residence_display"):
                    rel["residence_location"] = bp["residence_display"]
                    rel["residence_node_id"] = bp.get("bedroom_node_id", "")
                    rel["cohabiting_family"] = False
                    d["relations"] = rel
                    return
    except Exception:
        pass
    if hh.get("residence_location"):
        rel["residence_location"] = hh["residence_location"]
        d["relations"] = rel

def get_contacts(session_id: int, character_id: int = 0, resolve_relations: bool = True, ensure_scene: bool = True) -> list[dict]:
    import mechanics.social.persona as persona
    import namegen

    # Guard against recursive relation / scene-contact resolution
    if session_id in _get_resolving_contacts_set() or session_id in _get_ensuring_scene_set():
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
        anomalous_roster_by_key: dict[str, dict] = {}
        try:
            s_row = conn.execute(
                "SELECT scenario, narrative, extra_json FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
            if s_row:
                scen_key = s_row["scenario"] or "fantasy"
                scene_narrative = s_row["narrative"] or ""
                if s_row["extra_json"]:
                    try:
                        extra_data = json.loads(s_row["extra_json"]) or {}
                    except Exception:
                        extra_data = {}
                    raw_ar = (
                        extra_data.get("anomalous_agent_roster")
                        if isinstance(extra_data, dict)
                        else None
                    )
                    if isinstance(raw_ar, list):
                        for ar in raw_ar:
                            if not isinstance(ar, dict):
                                continue
                            ar_name = str(ar.get("name") or "").strip().lower()
                            ar_nid = str(ar.get("npc_id") or "").strip().lower()
                            if ar_name and ar_name not in anomalous_roster_by_key:
                                anomalous_roster_by_key[ar_name] = ar
                            if ar_nid and ar_nid not in anomalous_roster_by_key:
                                anomalous_roster_by_key[ar_nid] = ar
        except Exception:
            pass

        # Batch-load school_directory, factions, and lorebook once per get_contacts() call (O(1) enrichment)
        school_rows_cache: list = []
        school_by_name: dict[str, object] = {}
        school_by_id: dict[str, object] = {}
        factions_cache: list[tuple[str, list]] = []
        faction_names_cache: list[str] = []
        lorebook_by_name: dict[str, object] = {}
        if rows:
            try:
                school_rows_cache = conn.execute(
                    """SELECT role, grade, club, clique, primary_facility, secondary_facility,
                              personality_summary, race, gender, name, npc_id
                       FROM school_directory
                       WHERE session_id=?""",
                    (session_id,),
                ).fetchall()
                for sr in school_rows_cache:
                    s_name = str(sr["name"] or "").strip().lower()
                    s_nid = str(sr["npc_id"] or "").strip().lower()
                    if s_name and s_name not in school_by_name:
                        school_by_name[s_name] = sr
                    if s_nid and s_nid not in school_by_id:
                        school_by_id[s_nid] = sr
            except Exception:
                school_rows_cache = []
            try:
                fac_rows = conn.execute(
                    "SELECT name, leadership_roster_json FROM factions WHERE session_id=?",
                    (session_id,),
                ).fetchall()
                for fr in fac_rows:
                    fac_name = (fr["name"] or "").strip()
                    if fac_name:
                        faction_names_cache.append(fac_name)
                    try:
                        parsed_roster = json.loads(fr["leadership_roster_json"] or "[]")
                    except Exception:
                        parsed_roster = []
                    if not isinstance(parsed_roster, list):
                        parsed_roster = []
                    factions_cache.append((fac_name, parsed_roster))
            except Exception:
                factions_cache = []
                faction_names_cache = []
            try:
                lb_rows = conn.execute(
                    """SELECT id, name, description, faction, motivation, mannerisms, race
                       FROM lorebook
                       WHERE session_id=? AND lower(entity_type) IN ('person', 'npc', 'character')""",
                    (session_id,),
                ).fetchall()
                for lbr in lb_rows:
                    lb_name = str(lbr["name"] or "").strip().lower()
                    if lb_name and lb_name not in lorebook_by_name:
                        lorebook_by_name[lb_name] = lbr
            except Exception:
                lorebook_by_name = {}

        enrichment_ctx = {
            "school_rows": school_rows_cache,
            "school_by_name": school_by_name,
            "school_by_id": school_by_id,
            "anomalous_roster_by_key": anomalous_roster_by_key,
            "factions": factions_cache,
            "faction_names": faction_names_cache,
            "lorebook_by_name": lorebook_by_name,
            "narrative_loaded": True,
        }

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
                scenario=scen_key, narrative_text=scene_narrative,
                preloaded_enrichment=enrichment_ctx,
            )
            # Keep get_contacts() read-only; do not persist enriched_info back on read.
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
                    _apply_contact_household_residence(session_id, d, hh, scen_key)
                    d["household_id"] = hh["id"]
            elif (not d.get("relations") or not d["relations"].get("family")) and not is_in_readonly_uow():
                resolving_set = _get_resolving_contacts_set()
                resolving_set.add(session_id)
                try:
                    import mechanics.social.genealogy as genealogy
                    d["relations"] = genealogy.ensure_contact_relations(d, session_id=session_id, scenario=scen_key)
                    if session_id and d.get("id") and not is_in_readonly_uow():
                        try:
                            with get_conn() as conn:
                                conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(d["relations"]), d["id"]))
                        except sqlite3.Error as exc:
                            log.debug("Relations cache write skipped in get_contacts: %s", exc)
                finally:
                    resolving_set.discard(session_id)

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
    if norm_track == "romantic" and session_id:
        with get_conn() as _fox_conn:
            _fox_chk = _fox_conn.execute(
                """SELECT race FROM contacts
                   WHERE session_id=? AND (? = 0 OR character_id=? OR character_id=0)
                   AND (npc_id=? OR lower(npc_id)=? OR lower(name)=? OR lower(name)=?)""",
                (session_id, character_id, character_id, clean_id, clean_name, clean_name, clean_id),
            ).fetchall()
            if any(str(r["race"] or "").strip().lower() in ("kitsune:myobu_fox", "ghoul:canid") for r in _fox_chk):
                return False
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
            _apply_contact_household_residence(session_id, d, hh, scen_key)
            d["household_id"] = hh["id"]
    elif (not d.get("relations") or not d["relations"].get("family")) and not is_in_readonly_uow():
        import mechanics.social.genealogy as genealogy
        d["relations"] = genealogy.ensure_contact_relations(d, session_id=session_id, scenario=scen_key)
        if session_id and d.get("id") and not is_in_readonly_uow():
            try:
                with get_conn() as conn:
                    conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(d["relations"]), d["id"]))
            except sqlite3.Error as exc:
                log.debug("Relations cache write skipped in get_contact: %s", exc)

    d["status_effects"] = (d.get("basic_info") or {}).get("status_effects") or []
    return d

def update_relationship_score(session_id: int, npc_id: str, delta_score: int, character_id: int = 0) -> dict | None:
    return upsert_contact(session_id=session_id, npc_id=npc_id, name=npc_id, character_id=character_id, delta_score=delta_score)

def delete_contact(session_id: int, contact_id_or_npc_id: int | str) -> bool:
    """Deletes a contact safely while clearing any soft implicated_contact_id references in world_events."""
    with UnitOfWork() as conn:
        if isinstance(contact_id_or_npc_id, int) or str(contact_id_or_npc_id).isdigit():
            row = conn.execute(
                "SELECT id FROM contacts WHERE session_id = ? AND id = ?",
                (int(session_id), int(contact_id_or_npc_id)),
            ).fetchone()
        else:
            clean_key = str(contact_id_or_npc_id or "").strip().lower()
            row = conn.execute(
                "SELECT id FROM contacts WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)",
                (int(session_id), clean_key, clean_key),
            ).fetchone()
        if not row:
            return False
        cid = int(row["id"])
        conn.execute(
            "UPDATE world_events SET implicated_contact_id = NULL WHERE session_id = ? AND implicated_contact_id = ?",
            (int(session_id), cid),
        )
        cur = conn.execute("DELETE FROM contacts WHERE session_id = ? AND id = ?", (int(session_id), cid))
        return cur.rowcount > 0

_contact_reentrancy = threading.local()

def _get_resolving_contacts_set() -> set[int]:
    s = getattr(_contact_reentrancy, "resolving", None)
    if s is None:
        s = set()
        _contact_reentrancy.resolving = s
    return s

def _get_ensuring_scene_set() -> set[int]:
    s = getattr(_contact_reentrancy, "ensuring", None)
    if s is None:
        s = set()
        _contact_reentrancy.ensuring = s
    return s

def get_session_active_social_ties(session_id: int) -> list[dict[str, Any]]:
    """Fetch active social_ties rows for a session ordered newest-updated first."""
    if not session_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM social_ties WHERE session_id = ? AND status = 'active' ORDER BY updated_at DESC",
            (int(session_id),),
        ).fetchall()
        return [dict(r) for r in rows]
