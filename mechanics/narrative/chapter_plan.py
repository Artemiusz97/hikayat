from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import scenario_data
from models.llm_schemas import ChapterPlan
from mechanics.narrative.quest_engines import (
    build_engine_lead_approaches,
    load_quest_engines_catalog,
    normalize_quest_locale,
)
from mechanics.world.locations.hierarchy import get_clean_leaf_location

log = logging.getLogger(__name__)

_CLUE_ELIGIBLE_BOUNTY_ENGINES = frozenset({"MYSTERY_CASE", "SOCIAL_BROKERAGE"})
_LEAK_RE = re.compile(
    r"(?:\[(?:ITEM|GEAR|SPELLBOOK)_JSON\]|\b(?:HP|MP|DC)\s*[:=]?\s*\d+|\{\s*[a-z_]+\s*\})",
    re.IGNORECASE,
)
_BACKGROUND_PLAN_TASKS: Set[asyncio.Task[Any]] = set()
_IN_FLIGHT_PLANS: Set[Tuple[int, str]] = set()


def is_clue_based_quest(family_tier: str, engine: str) -> bool:
    """Q1: Story quests + MYSTERY_CASE / SOCIAL_BROKERAGE bounties use clue-based stage progression."""
    if str(family_tier or "").strip().lower() == "story":
        return True
    return str(engine or "").strip().upper() in _CLUE_ELIGIBLE_BOUNTY_ENGINES


def _canon_loc_leaf(loc: str) -> str:
    return get_clean_leaf_location(loc, default="").lower()


def build_clue_source_prose(
    kind: str,
    location: str,
    clue_title: str,
    npc_name: str = "",
    lang: str = "en",
) -> Tuple[str, str]:
    """Renders 5-locale `(player_verb, discovery_text)` for a clue source."""
    from mechanics.world.locations.hierarchy import format_clean_location_prose

    eff_lang = normalize_quest_locale(lang)
    catalog = load_quest_engines_catalog()
    tmpl = ((catalog.get("clue_source_templates") or {}).get(kind) or {}).get("player_verb") or {}
    rev_tmpl = ((catalog.get("clue_source_templates") or {}).get(kind) or {}).get("reveal") or {}

    venue_prose = format_clean_location_prose(location, include_zone=True, preposition="in") or location
    eff_npc = str(npc_name or "local witness").strip()
    eff_clue = str(clue_title or "the missing link").strip()

    verb_raw = str(tmpl.get(eff_lang) or tmpl.get("en") or "Investigate {venue} for {clue_title}")
    rev_raw = str(rev_tmpl.get(eff_lang) or rev_tmpl.get("en") or "Evidence at {venue} confirms {clue_title}.")
    slots = {"venue": venue_prose, "npc": eff_npc, "clue_title": eff_clue}
    for k, v in slots.items():
        verb_raw = verb_raw.replace(f"{{{k}}}", v)
        rev_raw = rev_raw.replace(f"{{{k}}}", v)
    return verb_raw.strip(), rev_raw.strip()


def build_chapter_plan_candidates(
    session_id: int,
    dossier: Dict[str, Any],
    *,
    climax_location: str = "",
) -> Dict[str, Any]:
    """
    Collects strict allow-listed non-sanctuary, non-climax rooms and valid candidate NPCs
    so the AI ChapterPlan chooses only from grounded world entities (Q5).
    """
    import db
    from mechanics.narrative.dossier_compiler import is_safe_sanctuary_location

    climax_loc = str(climax_location or (dossier.get("climax_spec") or {}).get("location") or "").strip()
    climax_leaf = _canon_loc_leaf(climax_loc)

    rooms: List[str] = []
    seen_low: Set[str] = set()
    seen_leaves: Set[str] = set()

    def _add_room(raw_name: Any) -> None:
        nm = str(raw_name or "").strip()
        if not nm:
            return
        low = nm.lower()
        leaf = _canon_loc_leaf(nm)
        if low == climax_loc.lower() or (climax_leaf and leaf == climax_leaf):
            return
        if is_safe_sanctuary_location(nm):
            return
        if low not in seen_low and (not leaf or leaf not in seen_leaves):
            seen_low.add(low)
            if leaf:
                seen_leaves.add(leaf)
            rooms.append(nm)

    if session_id:
        for sl in (db.get_session_locations(session_id) or []):
            if not isinstance(sl, dict):
                continue
            parts = []
            for seg in (sl.get("zone_name"), sl.get("primary_name"), sl.get("sub_name")):
                s_clean = str(seg or "").strip()
                if s_clean and s_clean.lower() not in ("main area", "area") and (not parts or parts[-1].lower() != s_clean.lower()):
                    parts.append(s_clean)
            if len(parts) >= 2:
                _add_room(" ➔ ".join(parts))
        for node in (db.get_session_world_nodes(session_id) or []):
            if not isinstance(node, dict):
                continue
            if str(node.get("node_type") or "").upper() in ("ROOM", "FACILITY", "POI"):
                tiered = db.format_node_tiered_location(session_id, str(node.get("node_id") or "")) if node.get("node_id") else ""
                _add_room(tiered or node.get("name"))
        # Include non-climax rooms already bound to leads or main stages (avoid bare parent zones)
        for st in ((dossier.get("climax_spec") or {}).get("main_stages") or []):
            if isinstance(st, dict) and not st.get("is_climax_stage"):
                st_tloc = str(st.get("target_location") or "").strip()
                if st_tloc and ("➔" in st_tloc or "->" in st_tloc or not rooms):
                    _add_room(st_tloc)
                for src in (st.get("clue_sources") or []):
                    if isinstance(src, dict):
                        _add_room(src.get("location"))

    npcs: List[str] = []
    seen_npc: Set[str] = set()
    dead_low: Set[str] = set()
    party_low: Set[str] = set()
    if session_id:
        sess = db.get_session(session_id) or {}
        for d_nm in (sess.get("dead_characters") or []):
            dead_low.add(str(d_nm or "").strip().lower())
        for p_npc in (db.get_session_party_npcs(session_id) or []):
            if isinstance(p_npc, dict) and p_npc.get("name"):
                party_low.add(str(p_npc["name"]).strip().lower())

    def _add_npc(raw_npc: Any) -> None:
        nm = str(raw_npc or "").strip()
        if not nm:
            return
        low = nm.lower()
        if low in ("player", "none", "unknown") or low in dead_low or low in party_low:
            return
        if low not in seen_npc:
            seen_npc.add(low)
            npcs.append(nm)

    cast = dossier.get("cast_bindings") or {}
    for role_k in ("informant", "accomplice", "client"):
        entry = cast.get(role_k)
        if isinstance(entry, dict):
            _add_npc(entry.get("name"))
    _add_npc(dossier.get("informant_npc"))
    if session_id:
        for c in (db.get_contacts(session_id) or []):
            if isinstance(c, dict):
                if c.get("is_deceased") or c.get("deceased"):
                    continue
                _add_npc(c.get("name"))

    return {"rooms": rooms, "npcs": npcs, "climax_location": climax_loc}


def validate_chapter_plan(
    plan: Any,
    *,
    candidate_rooms: List[str],
    candidate_npcs: List[str],
    climax_location: str,
    expected_clue_stage_indices: List[int],
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Strictly validates an AI `ChapterPlan` against Q5/E3 invariants:
    - All clue sources use canonical rooms from `candidate_rooms` (never sanctuaries or climax).
    - Every clue stage has >= 3 sources across distinct rooms.
    - Every `"witness"` source names a canonical NPC from `candidate_npcs`.
    - Zero raw HP/MP/DC/`[*_JSON]` leaks.
    """
    errors: List[str] = []
    if hasattr(plan, "model_dump"):
        raw = plan.model_dump()
    elif isinstance(plan, dict):
        raw = dict(plan)
    else:
        return False, ["Plan must be a JSON object."], {}

    title = str(raw.get("title") or "").strip()
    objective = str(raw.get("objective") or "").strip()
    if not title or len(title) < 3:
        errors.append("Plan title is missing or too short.")
    if not objective or len(objective) < 8:
        errors.append("Plan objective is missing or too short.")
    if _LEAK_RE.search(title) or _LEAK_RE.search(objective):
        errors.append("Plan title or objective contains internal stat/JSON tokens.")

    room_map: Dict[str, str] = {}
    for r in candidate_rooms:
        canon = str(r).strip()
        if not canon:
            continue
        room_map[canon.lower()] = canon
        room_map.setdefault(_canon_loc_leaf(canon), canon)

    npc_map: Dict[str, str] = {str(n).strip().lower(): str(n).strip() for n in candidate_npcs if str(n or "").strip()}
    climax_low = str(climax_location or "").strip().lower()
    climax_leaf = _canon_loc_leaf(climax_location)

    stages_in = raw.get("stages") or []
    stages_by_idx: Dict[int, Dict[str, Any]] = {}
    for st in stages_in:
        if isinstance(st, dict):
            s_i = int(st.get("stage_index") or 0)
            if s_i > 0:
                stages_by_idx[s_i] = dict(st)

    clean_stages: List[Dict[str, Any]] = []
    for req_idx in expected_clue_stage_indices:
        st = stages_by_idx.get(req_idx)
        if not st:
            errors.append(f"Missing required stage_index={req_idx}.")
            continue
        s_lbl = str(st.get("stage_label") or "").strip()
        if not s_lbl or _LEAK_RE.search(s_lbl):
            errors.append(f"Stage {req_idx}: invalid or leaking stage_label.")
        bc = dict(st.get("beat_contract") or {})
        kc = dict(st.get("key_clue") or {})
        if not str(kc.get("title") or "").strip() or not str(kc.get("lead_text") or "").strip():
            errors.append(f"Stage {req_idx}: key_clue must include non-empty title and lead_text.")
        if _LEAK_RE.search(str(kc.get("title") or "")) or _LEAK_RE.search(str(kc.get("lead_text") or "")):
            errors.append(f"Stage {req_idx}: key_clue contains internal stat/JSON tokens.")

        sources = st.get("clue_sources") or []
        if len(sources) < 3:
            errors.append(f"Stage {req_idx}: needs at least 3 clue_sources, got {len(sources)}.")

        clean_sources: List[Dict[str, Any]] = []
        used_locs_low: Set[str] = set()
        for src_idx, src in enumerate(sources[:4]):
            if not isinstance(src, dict):
                continue
            raw_loc = str(src.get("location") or "").strip()
            canon_loc = room_map.get(raw_loc.lower()) or room_map.get(_canon_loc_leaf(raw_loc))
            if not canon_loc:
                errors.append(f"Stage {req_idx} source #{src_idx+1}: off-list room '{raw_loc}'.")
                continue
            c_leaf = _canon_loc_leaf(canon_loc)
            if canon_loc.lower() == climax_low or (climax_leaf and c_leaf == climax_leaf):
                errors.append(f"Stage {req_idx} source #{src_idx+1}: cannot use climax room '{canon_loc}'.")
                continue
            if canon_loc.lower() in used_locs_low:
                errors.append(f"Stage {req_idx} source #{src_idx+1}: duplicate room '{canon_loc}' within stage.")
                continue
            used_locs_low.add(canon_loc.lower())

            kind = str(src.get("kind") or "record").strip().lower()
            if kind not in ("witness", "record", "item"):
                kind = "record"

            canon_npc = ""
            if kind == "witness":
                raw_npc = str(src.get("npc_name") or "").strip()
                canon_npc = npc_map.get(raw_npc.lower(), "")
                if not canon_npc:
                    errors.append(
                        f"Stage {req_idx} witness source #{src_idx+1}: NPC '{raw_npc}' not in candidate_npcs."
                    )
                    continue

            hint = str(src.get("approach_hint") or "").strip()
            if _LEAK_RE.search(hint):
                errors.append(f"Stage {req_idx} source #{src_idx+1}: approach_hint leaks internal tokens.")

            clean_sources.append(
                {
                    "source_id": str(src.get("source_id") or f"S{req_idx}-{src_idx+1}"),
                    "kind": kind,
                    "location": canon_loc,
                    "npc_name": canon_npc,
                    "approach_hint": hint,
                    "stat": str(src.get("stat") or ("CHA" if kind == "witness" else ("INT" if kind == "record" else "PER"))).upper(),
                    "dc_offset": max(-2, min(2, int(src.get("dc_offset") or 0))),
                    "status": "open",
                    "bonus": False,
                }
            )

        if len(clean_sources) < 3:
            errors.append(f"Stage {req_idx}: fewer than 3 valid distinct clue_sources ({len(clean_sources)}).")

        clean_stages.append(
            {
                "stage_index": req_idx,
                "stage_label": s_lbl,
                "beat_contract": {
                    "player_verb": str(bc.get("player_verb") or s_lbl).strip(),
                    "reveal": str(bc.get("reveal") or kc.get("lead_text") or "").strip(),
                    "handover": str(bc.get("handover") or kc.get("title") or "").strip(),
                    "next_pointer": str(bc.get("next_pointer") or "").strip(),
                },
                "key_clue": {
                    "title": str(kc.get("title") or "").strip(),
                    "lead_text": str(kc.get("lead_text") or "").strip(),
                    "category": str(kc.get("category") or "document").strip().lower(),
                },
                "clue_sources": clean_sources,
            }
        )

    is_valid = len(errors) == 0 and len(clean_stages) == len(expected_clue_stage_indices)
    return is_valid, errors, {
        "title": title,
        "objective": objective,
        "climax_location": climax_location,
        "stages": clean_stages,
        "optional_hooks": list(raw.get("optional_hooks") or [])[:3],
    }


async def generate_chapter_plan_with_resilience(
    session_id: int,
    quest_id: str,
    dossier: Dict[str, Any],
    *,
    timeout_seconds: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """
    Q4/Q6: Calls the utility model (preserving NSFW routing) with a ~30s deadline and
    at most 1 validation-repair retry. Returns validated clean plan dict or None.
    """
    import db
    from db import adb
    import llm_client

    if not session_id or not isinstance(dossier, dict):
        return None

    def _gather() -> Tuple[Dict[str, Any], Dict[str, Any]]:
        s_row = db.get_session(session_id) or {}
        c_row = build_chapter_plan_candidates(session_id, dossier)
        return s_row, c_row

    sess, cands = await adb(_gather)
    scen_key = str(sess.get("scenario") or "fantasy")
    lang = normalize_quest_locale(sess.get("language") or "en")
    climax_spec = dossier.get("climax_spec") or {}
    main_stages = [s for s in (climax_spec.get("main_stages") or []) if isinstance(s, dict)]
    expected_indices = [
        int(s.get("stage_index") or i + 1)
        for i, s in enumerate(main_stages)
        if not s.get("is_climax_stage")
    ]
    if not expected_indices:
        return None

    cand_rooms = cands["rooms"]
    cand_npcs = cands["npcs"]
    if len(cand_rooms) < 3:
        return None

    econ = dossier.get("contract_economy") or {}
    is_nsfw = bool(econ.get("uses_nsfw_routing") or scenario_data.uses_nsfw_model(scen_key))
    pitch = dossier.get("pitch_stub") or {}
    q_title = str(pitch.get("title") or climax_spec.get("main_objective_text") or quest_id)
    target_npc = str(dossier.get("target_npc") or climax_spec.get("target_npc") or "adversary")

    sys_prompt = (
        "You are designing an investigative quest chapter blueprint for an interactive RPG.\n"
        f"Write ALL natural-language text in language code '{lang}'.\n"
        "STRICT RULES:\n"
        "1. Every clue source `location` MUST be chosen verbatim from CANDIDATE_ROOMS (never invent rooms).\n"
        "2. Each non-climax stage MUST have >= 3 `clue_sources` in DISTINCT rooms from CANDIDATE_ROOMS.\n"
        "3. Every `'witness'` source MUST set `npc_name` verbatim from CANDIDATE_NPCS; non-witness sources leave `npc_name` null.\n"
        "4. NEVER include raw HP, MP, DC numbers, dice math, or `[ITEM_JSON]` tags in any text.\n"
        "5. Output ONLY JSON matching the ChapterPlan schema."
    )
    usr_prompt = json.dumps(
        {
            "quest_title": q_title,
            "scenario": scen_key,
            "chapter": int(climax_spec.get("chapter") or 1),
            "target_adversary": target_npc,
            "climax_location_forbidden_for_clues": cands["climax_location"],
            "expected_clue_stage_indices": expected_indices,
            "CANDIDATE_ROOMS": cand_rooms[:20],
            "CANDIDATE_NPCS": cand_npcs[:16],
        },
        ensure_ascii=False,
    )

    deadline = time.monotonic() + max(5.0, float(timeout_seconds or 30.0))
    last_errors: List[str] = []

    for attempt in range(2):
        rem = deadline - time.monotonic()
        if rem < 2.5:
            break
        prompt_to_send = usr_prompt
        if attempt == 1 and last_errors:
            prompt_to_send = (
                f"{usr_prompt}\n\nREPAIR REQUIRED — fix these validation errors strictly:\n- "
                + "\n- ".join(last_errors[:8])
            )
        try:
            raw = await llm_client.call_llm_json(
                sys_prompt,
                prompt_to_send,
                max_tokens=1800,
                retries=0,
                is_nsfw=is_nsfw,
                use_utility=True,
                timeout=rem,
                response_model=ChapterPlan,
            )
            plan_obj = ChapterPlan.model_validate(raw if isinstance(raw, dict) else {})
            ok, errors, clean_plan = validate_chapter_plan(
                plan_obj,
                candidate_rooms=cand_rooms,
                candidate_npcs=cand_npcs,
                climax_location=cands["climax_location"],
                expected_clue_stage_indices=expected_indices,
            )
            if ok:
                return clean_plan
            last_errors = errors
            log.info("ChapterPlan attempt %d validation failed for %s: %s", attempt + 1, quest_id, errors[:3])
        except Exception as exc:
            last_errors = [str(exc)]
            log.info("ChapterPlan attempt %d failed for %s: %s", attempt + 1, quest_id, exc)
            if isinstance(exc, asyncio.TimeoutError):
                break

    return None


def apply_chapter_plan_to_dossier(
    session_id: int,
    quest_id: str,
    plan: Dict[str, Any],
    *,
    conn: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    E3 Hot-Swap Guard:
    - Completed/bypassed stages: untouched.
    - Active stage: updates prose ONLY if 0 clue sources are claimed/burned/cold; NEVER mutates rooms or NPCs.
    - Locked stages: adopts AI stage prose, beat_contract, key_clue, and clue_sources, then re-syncs waypoints.
    """
    import db

    if not session_id or not quest_id or not isinstance(plan, dict):
        return None
    if conn is None:
        with db.UnitOfWork() as uow_conn:
            return apply_chapter_plan_to_dossier(session_id, quest_id, plan, conn=uow_conn)
    fresh_dos = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not fresh_dos:
        return None
    sess = db.get_session(session_id) or {}
    lang = normalize_quest_locale(sess.get("language") or "en")
    danger_tier = max(1, int(fresh_dos.get("danger_tier") or 1))
    climax = dict(fresh_dos.get("climax_spec") or {})
    main_stages = [dict(s) for s in (climax.get("main_stages") or []) if isinstance(s, dict)]
    plan_by_idx = {int(s.get("stage_index") or 0): s for s in (plan.get("stages") or []) if isinstance(s, dict)}
    raw_clue_graph = fresh_dos.get("clue_graph")
    clue_graph: List[Dict[str, Any]] = [
        dict(c) for c in (raw_clue_graph if isinstance(raw_clue_graph, list) else []) if isinstance(c, dict)
    ]

    def _upsert_clue_node(st_num_val: int, kc_dict: Dict[str, Any]) -> None:
        kc_id = str(kc_dict.get("clue_id") or f"{quest_id}-KC-{st_num_val}")
        legacy_id = f"{quest_id}_clue_{st_num_val}"
        for existing in clue_graph:
            cid = str(existing.get("clue_id") or "")
            if cid in (kc_id, legacy_id) or int(existing.get("stage_index") or 0) == st_num_val:
                existing["title"] = str(kc_dict.get("title") or existing.get("title") or "")
                existing["summary"] = str(kc_dict.get("lead_text") or existing.get("summary") or "")
                existing["category"] = str(kc_dict.get("category") or existing.get("category") or "document")
                existing["stage_index"] = int(st_num_val)
                existing["key_clue_id"] = kc_id
                return
        clue_graph.append(
            {
                "clue_id": kc_id,
                "key_clue_id": kc_id,
                "stage_index": int(st_num_val),
                "title": str(kc_dict.get("title") or ""),
                "summary": str(kc_dict.get("lead_text") or ""),
                "category": str(kc_dict.get("category") or "document"),
                "is_red_herring": False,
                "paired_with": [],
                "status": "open",
            }
        )

    any_updated = False
    for idx, st in enumerate(main_stages):
        st_num = int(st.get("stage_index") or (idx + 1))
        status = str(st.get("status") or "locked").lower()
        if status in ("completed", "bypassed") or st.get("completed") or st.get("is_climax_stage"):
            continue
        p_st = plan_by_idx.get(st_num)
        if not p_st:
            continue

        cur_sources = [dict(s) for s in (st.get("clue_sources") or []) if isinstance(s, dict)]
        any_touched = any(
            str(s.get("status") or "open").lower() in ("claimed", "burned", "cold") or s.get("claimed_by")
            for s in cur_sources
        )
        p_kc = p_st.get("key_clue") or {}
        p_bc = p_st.get("beat_contract") or {}

        if status == "active":
            if any_touched:
                continue
            # E3: Active untouched stage updates prose only; NEVER change rooms or NPCs already shown!
            if p_st.get("stage_label"):
                st["stage_label"] = str(p_st["stage_label"])
                st["label"] = str(p_st["stage_label"])
            bc = dict(st.get("beat_contract") or {})
            for bk in ("player_verb", "reveal", "handover", "next_pointer"):
                if p_bc.get(bk):
                    bc[bk] = str(p_bc[bk])
            st["beat_contract"] = bc
            kc = dict(st.get("key_clue") or {})
            if p_kc.get("title"):
                kc["title"] = str(p_kc["title"])
            if p_kc.get("lead_text"):
                kc["lead_text"] = str(p_kc["lead_text"])
            if p_kc.get("category"):
                kc["category"] = str(p_kc["category"])
            st["key_clue"] = kc
            p_srcs = p_st.get("clue_sources") or []
            for si, existing_src in enumerate(cur_sources):
                src_hint = p_srcs[si].get("approach_hint") if si < len(p_srcs) else ""
                eff_hint, rev_hint = build_clue_source_prose(
                    kind=str(existing_src.get("kind") or "record"),
                    location=str(existing_src.get("location") or ""),
                    clue_title=str(kc.get("title") or p_st.get("stage_label") or ""),
                    npc_name=str(existing_src.get("npc_name") or ""),
                    lang=lang,
                )
                existing_src["approach_hint"] = str(src_hint or eff_hint)
                existing_src["discovery_text"] = rev_hint
            st["clue_sources"] = cur_sources
            _upsert_clue_node(st_num, kc)
            main_stages[idx] = st
            any_updated = True
        elif status == "locked":
            # Locked stages freely adopt AI rooms, NPCs, key_clue, and clue_sources
            if p_st.get("stage_label"):
                st["stage_label"] = str(p_st["stage_label"])
                st["label"] = str(p_st["stage_label"])
            st["completion_trigger"] = "key_clue"
            kc = {
                "clue_id": str((st.get("key_clue") or {}).get("clue_id") or f"{quest_id}-KC-{st_num}"),
                "title": str(p_kc.get("title") or st["stage_label"]),
                "lead_text": str(p_kc.get("lead_text") or p_bc.get("reveal") or st["stage_label"]),
                "category": str(p_kc.get("category") or "document"),
            }
            st["key_clue"] = kc
            built_sources: List[Dict[str, Any]] = []
            for si, psrc in enumerate(p_st.get("clue_sources") or []):
                kind = str(psrc.get("kind") or "record").lower()
                s_loc = str(psrc.get("location") or "")
                s_npc = str(psrc.get("npc_name") or "") if kind == "witness" else ""
                verb_txt, rev_txt = build_clue_source_prose(
                    kind=kind,
                    location=s_loc,
                    clue_title=kc["title"],
                    npc_name=s_npc,
                    lang=lang,
                )
                s_stat = str(psrc.get("stat") or ("CHA" if kind == "witness" else "PER")).upper()
                built_sources.append(
                    {
                        "source_id": str(psrc.get("source_id") or f"S{st_num}-{si+1}"),
                        "kind": kind,
                        "location": s_loc,
                        "npc_name": s_npc,
                        "approach_hint": str(psrc.get("approach_hint") or verb_txt),
                        "discovery_text": rev_txt,
                        "stat": s_stat,
                        "dc_offset": int(psrc.get("dc_offset") or 0),
                        "approaches": build_engine_lead_approaches([s_stat, "PER", "INT"], danger_tier=danger_tier),
                        "status": "open",
                        "bonus": False,
                    }
                )
            if built_sources:
                st["clue_sources"] = built_sources
                st["target_location"] = built_sources[0]["location"]
                st["target_npc"] = built_sources[0]["npc_name"]
                _upsert_clue_node(st_num, kc)
            bc = dict(st.get("beat_contract") or {})
            for bk in ("player_verb", "reveal", "handover", "next_pointer"):
                if p_bc.get(bk):
                    bc[bk] = str(p_bc[bk])
            bc["is_dialogue_beat"] = bool(built_sources and built_sources[0].get("npc_name"))
            st["beat_contract"] = bc
            main_stages[idx] = st
            any_updated = True

    if not any_updated:
        return fresh_dos

    climax["main_stages"] = main_stages
    climax["chapter_plan_applied"] = True
    saved = db.upsert_quest_dossier(
        session_id,
        quest_id,
        climax_spec=climax,
        clue_graph=clue_graph,
        conn=conn,
    )
    if saved:
        db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved, conn=conn)
    return saved


async def run_background_chapter_plan(session_id: int, quest_id: str) -> Optional[Dict[str, Any]]:
    """Background coroutine for Ch.1 post-opening and bounty accept ChapterPlan generation."""
    import db
    from db import adb
    from mechanics.system.concurrency import acquire_background_session_lock

    try:
        dos = await adb(db.get_quest_dossier, session_id, quest_id)
        if not dos:
            return None
        if not is_clue_based_quest(str(dos.get("family_tier") or ""), str(dos.get("engine") or "")):
            return dos
        plan = await generate_chapter_plan_with_resilience(session_id, quest_id, dos, timeout_seconds=30.0)
        if not plan:
            return dos
        async with acquire_background_session_lock(session_id) as acquired:
            if not acquired:
                log.debug("Background ChapterPlan skipped DB apply for session %s quest %s: session busy", session_id, quest_id)
                return dos
            updated = await adb(apply_chapter_plan_to_dossier, session_id, quest_id, plan)
            return updated or dos
    except Exception as exc:
        log.warning("Background ChapterPlan skipped for session %s quest %s: %s", session_id, quest_id, exc)
        return None


def schedule_background_chapter_plan(session_id: int, quest_id: str) -> Optional[asyncio.Task[Any]]:
    """Schedules `run_background_chapter_plan` on the active event loop without duplicate in-flight jobs."""
    if not session_id or not quest_id:
        return None
    key = (int(session_id), str(quest_id))
    if key in _IN_FLIGHT_PLANS:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    _IN_FLIGHT_PLANS.add(key)
    task = loop.create_task(run_background_chapter_plan(session_id, quest_id))
    _BACKGROUND_PLAN_TASKS.add(task)

    def _cleanup(t: asyncio.Task[Any]) -> None:
        _BACKGROUND_PLAN_TASKS.discard(t)
        _IN_FLIGHT_PLANS.discard(key)

    task.add_done_callback(_cleanup)
    return task
