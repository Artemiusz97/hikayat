from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Query, Request

import db
from db import adb
from mechanics.world.world_events.engine import build_client_world_pulse_payload
from ..security import verify_session_participant
from .common import (
    _enrich_commitments_for_ui,
    _get_contacts_ro,
    _infer_school_grade_badge,
    _verify_missing_session_codex_auth,
)
from .contacts import _enrich_contact_record, _preload_fog_of_war_context

router = APIRouter()


def _format_world_lore_entity_for_ui(ent: dict[str, Any]) -> dict[str, Any]:
    """Formats internal world_lore entries (such as `_macro_world_state`) for player-facing Codex UI."""
    out = dict(ent)
    raw_name = str(out.get("name") or "").strip()
    raw_type = str(out.get("entity_type") or "").strip()
    raw_desc = str(out.get("description") or "").strip()

    is_macro = bool(
        raw_name == "_macro_world_state"
        or "| CURRENT RUMOR:" in raw_desc
        or "| FLASHPOINT:" in raw_desc
    )
    if raw_type:
        out["entity_type_label"] = (
            "World Lore" if raw_type.lower() == "world_lore" else raw_type.replace("_", " ").title()
        )

    if is_macro:
        out["is_macro_world_state"] = True
        if raw_name == "_macro_world_state":
            out["raw_name"] = raw_name
            out["name"] = "Regional Power Dynamics"
            out["display_name"] = "Regional Power Dynamics"

        macro_conflict = raw_desc
        current_rumor = str(out.get("current_rumor") or "").strip()
        flashpoint = str(out.get("flashpoint") or "").strip()

        segments = re.split(r"\s*\|\s*(?=(?:CURRENT\s+RUMOR|FLASHPOINT)\s*:)", raw_desc, flags=re.IGNORECASE)
        conflict_parts: list[str] = []
        for seg in segments:
            s_clean = seg.strip()
            if not s_clean:
                continue
            m_rumor = re.match(r"^CURRENT\s+RUMOR\s*:\s*(.+)$", s_clean, flags=re.IGNORECASE | re.DOTALL)
            m_flash = re.match(r"^FLASHPOINT\s*:\s*(.+)$", s_clean, flags=re.IGNORECASE | re.DOTALL)
            if m_rumor:
                current_rumor = m_rumor.group(1).strip()
            elif m_flash:
                flashpoint = m_flash.group(1).strip()
            else:
                conflict_parts.append(s_clean)
        if conflict_parts:
            macro_conflict = " ".join(conflict_parts).strip()

        out["description"] = macro_conflict
        if current_rumor:
            out["current_rumor"] = current_rumor
        if flashpoint:
            out["flashpoint"] = flashpoint
            if not out.get("location"):
                out["location"] = flashpoint

    return out


@router.get("/api/lorebook/{session_id}")
async def get_lorebook(session_id: int, user_id: int | None = Query(None), request: Request = None):
    """Fetches lorebook entities grouped by category, restricting person entities to discovered characters."""
    from mechanics.social.persona import infer_contact_gender
    from mechanics.social.persona.intimacy.appearance import normalize_appearance

    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    session = raw_sess or {}
    scen_key = str(session.get("scenario") or "fantasy")
    curr_npcs = session.get("current_npcs") or []
    party_npcs = await adb(db.get_session_party_npcs, session_id) or []

    valid_uid = (
        user_id
        if isinstance(user_id, int)
        else (int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None)
    )
    lookup_uid = valid_uid or session.get("host_user_id") or 0
    settings = await adb(db.get_settings, lookup_uid) if lookup_uid else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))
    phys_st = session.get("physical_state") if isinstance(session.get("physical_state"), dict) else None

    import scenario_data as _sd_lore

    if _sd_lore.is_anomalous_incursions_scenario(scen_key):
        from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents

        await adb(prune_unmet_preseeded_special_agents, session_id)

    grouped = await adb(db.get_lorebook, session_id)
    commitments = await adb(db.get_active_commitments, session_id)
    contacts = await _get_contacts_ro(session_id)
    school_roster = await adb(db.get_school_roster, session_id) or []
    dir_by_name = {str(d.get("name", "")).strip().lower(): d for d in school_roster if d.get("name")}
    wr_rows_codex = await adb(db.get_world_roster, session_id, include_legacy_rosters=False) or []
    wr_by_name = {str(w.get("name", "")).strip().lower(): w for w in wr_rows_codex if w.get("name")}

    contact_map = {(c.get("name") or "").lower().strip(): c for c in contacts if c.get("name")}

    char_row = await adb(db.get_character, lookup_uid, session_id=session_id) if lookup_uid else None
    player_char_name = str((char_row or {}).get("name") or session.get("character_name") or "").strip().lower()

    party_names = {
        str(p.get("name", "")).strip().lower()
        for p in (party_npcs or [])
        if isinstance(p, dict) and p.get("name")
    } | {str(p).strip().lower() for p in (party_npcs or []) if isinstance(p, str) and p.strip()}

    from mechanics.social.relationships import (
        collect_met_npc_names,
        is_npc_discovered_by_player,
        is_unlocked_contact,
    )

    met_in_story_names = collect_met_npc_names(session, party_npcs=party_npcs, player_char_name=player_char_name)
    codex_char_id = int((char_row or {}).get("id") or 0)
    codex_ui_lang = str((settings or {}).get("ui_language") or "en")
    codex_fow_ctx = await adb(
        _preload_fog_of_war_context,
        session_id,
        codex_char_id,
        party_names,
        codex_ui_lang,
        contacts,
        party_npcs,
        scen_key,
        session if raw_sess else None,
        char_row if isinstance(char_row, dict) else None,
    )

    discovered_people_names = set()
    all_entities = []

    if isinstance(grouped, dict):
        for cat, items in list(grouped.items()):
            formatted_non_person: list[dict[str, Any]] = []
            for it in items:
                it_dict = dict(it)
                is_person = cat == "person" or it_dict.get("entity_type") == "person"

                if is_person:
                    p_name = (it_dict.get("name") or "").lower().strip()
                    if p_name == player_char_name:
                        continue
                    c = contact_map.get(p_name)
                    dir_entry = dir_by_name.get(p_name)
                    score = int(it_dict.get("relationship_score", 0) or 0)
                    if c:
                        score = int(c.get("relationship_score", 0) or 0)

                    is_discovered = is_npc_discovered_by_player(
                        p_name,
                        c,
                        met_in_story_names,
                        party_names=party_names,
                        score_override=score,
                    )
                    if not is_discovered:
                        continue

                    it_dict["relationship_score"] = score
                    if c:
                        b_info = c.get("basic_info") or {}
                        if isinstance(b_info, str):
                            try:
                                b_info = json.loads(b_info)
                            except (json.JSONDecodeError, TypeError, ValueError):
                                b_info = {}
                        it_dict["grade"] = it_dict.get("grade") or b_info.get("grade") or ""
                        it_dict["club"] = it_dict.get("club") or b_info.get("club") or ""
                        it_dict["mannerisms"] = it_dict.get("mannerisms") or b_info.get("mannerisms") or ""
                        it_dict["description"] = it_dict.get("description") or b_info.get("description") or ""
                        it_dict["race"] = it_dict.get("race") or c.get("race") or b_info.get("race") or "human"
                        it_dict["gender"] = it_dict.get("gender") or c.get("gender") or b_info.get("gender") or ""
                        it_dict["role"] = it_dict.get("role") or b_info.get("role") or b_info.get("occupation") or ""
                        if c.get("appearance"):
                            it_dict["appearance"] = c["appearance"]
                            it_dict["appearance_json"] = c.get("appearance_json") or json.dumps(c["appearance"])

                    if dir_entry:
                        it_dict["grade"] = it_dict.get("grade") or dir_entry.get("grade") or ""
                        it_dict["club"] = it_dict.get("club") or dir_entry.get("club") or ""
                        it_dict["mannerisms"] = it_dict.get("mannerisms") or dir_entry.get("mannerisms") or ""
                        it_dict["race"] = dir_entry["race"] if dir_entry.get("race") else (it_dict.get("race") or "human")
                        it_dict["gender"] = dir_entry["gender"] if dir_entry.get("gender") else (it_dict.get("gender") or "")
                        it_dict["role"] = it_dict.get("role") or dir_entry.get("role") or ""
                    elif p_name in wr_by_name:
                        wr_ent = wr_by_name[p_name]
                        wb_ent = wr_ent.get("basic_info") or {}
                        it_dict["grade"] = it_dict.get("grade") or wb_ent.get("grade") or ""
                        it_dict["club"] = it_dict.get("club") or wb_ent.get("club") or ""
                        it_dict["race"] = it_dict.get("race") or wr_ent.get("race") or "human"
                        it_dict["gender"] = it_dict.get("gender") or wr_ent.get("gender") or ""
                        it_dict["role"] = it_dict.get("role") or wr_ent.get("role") or wb_ent.get("role") or ""

                    matched_curr_npc = next(
                        (n for n in curr_npcs if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == p_name),
                        None,
                    )
                    if matched_curr_npc:
                        c_role_val = matched_curr_npc.get("role")
                        if c_role_val and str(c_role_val).lower() != "none":
                            it_dict["role"] = it_dict.get("role") or str(c_role_val)
                        if matched_curr_npc.get("grade"):
                            it_dict["grade"] = it_dict.get("grade") or str(matched_curr_npc["grade"])
                        if matched_curr_npc.get("club"):
                            it_dict["club"] = it_dict.get("club") or str(matched_curr_npc["club"])

                    if not it_dict.get("role") or str(it_dict.get("role")).lower() == "none":
                        desc_str = str(it_dict.get("description") or "")
                        m_desc_role = re.search(r"\(([^)]+)\)", desc_str)
                        if m_desc_role:
                            extracted_role = m_desc_role.group(1).strip()
                            if extracted_role and not any(k in extracted_role.lower() for k in ("née", "nee", "formerly")):
                                it_dict["role"] = extracted_role

                    it_dict["grade"] = _infer_school_grade_badge(
                        it_dict.get("role") or "", it_dict.get("grade") or "", scen_key
                    )

                    raw_g = str(it_dict.get("gender") or "").strip().lower()
                    if not raw_g or raw_g in ("unknown", "none"):
                        it_dict["gender"] = (
                            infer_contact_gender({"name": it_dict.get("name"), "basic_info": it_dict}) or "female"
                        )

                    app = it_dict.get("appearance")
                    if isinstance(app, str):
                        try:
                            app = json.loads(app)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            app = {}
                    if not isinstance(app, dict):
                        app = {}

                    has_full_app = bool(
                        app.get("eye_color") and app.get("hair_color") and (app.get("stature") or app.get("physique"))
                    )
                    if not has_full_app:
                        norm_app = normalize_appearance(
                            app,
                            gender=it_dict["gender"],
                            race=it_dict.get("race", "human"),
                            scen_key=scen_key,
                            desc=it_dict.get("description", ""),
                            name=it_dict.get("name", ""),
                        )
                        it_dict["appearance"] = norm_app
                        it_dict["appearance_json"] = json.dumps(norm_app)

                    it_basic = it_dict.get("basic_info") or {}
                    if isinstance(it_basic, str):
                        try:
                            it_basic = json.loads(it_basic)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            it_basic = {}
                    if not it_basic.get("role"):
                        it_basic["role"] = it_dict.get("role") or ""
                    if not it_basic.get("grade"):
                        it_basic["grade"] = it_dict.get("grade") or ""
                    if not it_basic.get("club"):
                        it_basic["club"] = it_dict.get("club") or ""
                    it_basic.setdefault("race", it_dict.get("race") or "human")
                    it_basic.setdefault("gender", it_dict["gender"])
                    it_basic.setdefault("description", it_dict.get("description") or "")
                    it_basic.setdefault("mannerisms", it_dict.get("mannerisms") or "")
                    it_dict["basic_info"] = it_basic

                    enriched_person = _enrich_contact_record(
                        it_dict,
                        session_id,
                        scen_key,
                        debug_reveal_all,
                        phys_st=phys_st,
                        party_names=party_names,
                        fow_context=codex_fow_ctx,
                    )
                    it_dict.update(enriched_person)
                    it_dict["is_contact"] = bool(
                        c is not None and is_unlocked_contact(c, party_names, met_in_story_names=met_in_story_names)
                    )
                    it_dict["is_discovered"] = True

                    discovered_people_names.add(p_name)
                    all_entities.append(it_dict)
                else:
                    formatted_ent = _format_world_lore_entity_for_ui(it_dict)
                    all_entities.append(formatted_ent)
                    formatted_non_person.append(formatted_ent)
            if cat != "person" and formatted_non_person:
                grouped[cat] = formatted_non_person

        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            c_name_lower = c_name.lower()
            if not c_name or c_name_lower == player_char_name or c_name_lower in discovered_people_names:
                continue

            score = int(c.get("relationship_score", 0) or 0)
            is_discovered_c = is_npc_discovered_by_player(
                c_name_lower,
                c,
                met_in_story_names,
                party_names=party_names,
                score_override=score,
            )
            if not is_discovered_c:
                continue

            b_info = c.get("basic_info") or {}
            if isinstance(b_info, str):
                try:
                    b_info = json.loads(b_info)
                except (json.JSONDecodeError, TypeError, ValueError):
                    b_info = {}

            dir_entry_c = dir_by_name.get(c_name_lower)
            c_gender = (
                (dir_entry_c.get("gender") if dir_entry_c else None)
                or c.get("gender")
                or b_info.get("gender")
                or infer_contact_gender({"name": c_name, "basic_info": b_info})
                or "female"
            )
            c_race = (dir_entry_c.get("race") if dir_entry_c else None) or c.get("race") or b_info.get("race") or "human"
            c_app = c.get("appearance")
            if isinstance(c_app, str):
                try:
                    c_app = json.loads(c_app)
                except (json.JSONDecodeError, TypeError, ValueError):
                    c_app = {}
            if not isinstance(c_app, dict) or not (c_app.get("eye_color") and c_app.get("hair_color")):
                c_app = normalize_appearance(
                    c_app or {},
                    gender=c_gender,
                    race=c_race,
                    scen_key=scen_key,
                    desc=b_info.get("description", ""),
                    name=c_name,
                )

            p_dict = dict(c)
            p_dict["name"] = c_name
            p_dict["role"] = (
                b_info.get("role")
                or b_info.get("occupation")
                or (dir_entry_c.get("role") if dir_entry_c else None)
                or "Contact"
            )
            p_dict["race"] = c_race
            p_dict["gender"] = c_gender
            raw_c_grade = b_info.get("grade") or (dir_entry_c.get("grade") if dir_entry_c else "") or ""
            p_dict["grade"] = _infer_school_grade_badge(p_dict["role"], raw_c_grade, scen_key)
            p_dict["club"] = b_info.get("club") or (dir_entry_c.get("club") if dir_entry_c else "") or ""
            p_dict["mannerisms"] = b_info.get("mannerisms") or (dir_entry_c.get("mannerisms") if dir_entry_c else "") or ""
            p_dict["description"] = (
                b_info.get("description") or (dir_entry_c.get("personality_summary") if dir_entry_c else "") or ""
            )
            p_dict["appearance"] = c_app
            p_dict["appearance_json"] = json.dumps(c_app)
            p_dict["entity_type"] = "person"
            p_dict["basic_info"] = b_info
            p_dict["relationship_score"] = score
            p_dict["is_contact"] = bool(is_unlocked_contact(c, party_names, met_in_story_names=met_in_story_names))
            p_dict["is_discovered"] = True

            enriched_p = _enrich_contact_record(
                p_dict,
                session_id,
                scen_key,
                debug_reveal_all,
                phys_st=phys_st,
                party_names=party_names,
                fow_context=codex_fow_ctx,
            )
            p_dict.update(enriched_p)
            grouped.setdefault("person", []).append(p_dict)
            all_entities.append(p_dict)
            discovered_people_names.add(c_name_lower)

        for met_name_lower in met_in_story_names:
            if met_name_lower in discovered_people_names or met_name_lower == player_char_name:
                continue
            r_entry = dir_by_name.get(met_name_lower) or wr_by_name.get(met_name_lower)
            matched_curr_npc = None
            for n in curr_npcs:
                if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == met_name_lower:
                    matched_curr_npc = n
                    break

            display_name = (
                (r_entry.get("name") if r_entry else None)
                or (matched_curr_npc.get("name") if matched_curr_npc else met_name_lower.title())
            )
            synth_gender = (
                (r_entry.get("gender") if r_entry else None)
                or (matched_curr_npc.get("gender") if matched_curr_npc else None)
                or infer_contact_gender({"name": display_name, "basic_info": matched_curr_npc or {}})
                or "female"
            )
            synth_race = (
                (r_entry.get("race") if r_entry else None)
                or (matched_curr_npc.get("race") if matched_curr_npc else None)
                or "human"
            )
            synth_role = (
                (r_entry.get("role") if r_entry else None)
                or (matched_curr_npc.get("role") if matched_curr_npc else "Acquaintance")
            )
            raw_s_grade = (
                (r_entry.get("grade") if r_entry else None)
                or (matched_curr_npc.get("grade") if matched_curr_npc else "")
                or ""
            )
            synth_grade = _infer_school_grade_badge(synth_role, raw_s_grade, scen_key)
            synth_club = (
                (r_entry.get("club") if r_entry else None)
                or (matched_curr_npc.get("club") if matched_curr_npc else "")
                or ""
            )
            synth_desc = (
                (r_entry.get("personality_summary") if r_entry else None)
                or (matched_curr_npc.get("description") if matched_curr_npc else "")
                or ""
            )
            synth_app = normalize_appearance(
                (
                    matched_curr_npc.get("appearance")
                    if isinstance(matched_curr_npc, dict) and isinstance(matched_curr_npc.get("appearance"), dict)
                    else {}
                ),
                gender=synth_gender,
                race=synth_race,
                scen_key=scen_key,
                desc=synth_desc,
                name=display_name,
            )
            p_dict = {
                "name": display_name,
                "formal_title": (r_entry.get("formal_title") if r_entry else "") or "",
                "role": synth_role,
                "grade": synth_grade,
                "club": synth_club,
                "race": synth_race,
                "gender": synth_gender,
                "description": synth_desc,
                "appearance": synth_app,
                "appearance_json": json.dumps(synth_app),
                "basic_info": {
                    "role": synth_role,
                    "grade": synth_grade,
                    "club": synth_club,
                    "race": synth_race,
                    "gender": synth_gender,
                    "description": synth_desc,
                },
                "entity_type": "person",
                "relationship_score": 0,
                "is_contact": False,
                "is_discovered": True,
            }
            enriched_p = _enrich_contact_record(
                p_dict,
                session_id,
                scen_key,
                debug_reveal_all,
                phys_st=phys_st,
                party_names=party_names,
                fow_context=codex_fow_ctx,
            )
            p_dict.update(enriched_p)
            p_dict["is_discovered"] = True
            grouped.setdefault("person", []).append(p_dict)
            all_entities.append(p_dict)
            discovered_people_names.add(met_name_lower)

        grouped["person"] = [e for e in all_entities if e.get("entity_type") == "person"]

    return {
        "categories": grouped,
        "entities": all_entities,
        "commitments": _enrich_commitments_for_ui(session_id, commitments, contacts),
        "world_pulse": await adb(build_client_world_pulse_payload, session_id),
    }
