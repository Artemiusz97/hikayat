from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import scenario_data
from models.llm_schemas import ChapterPlan, ChapterPlanClueSource
from mechanics.narrative.quest_engines import (
    build_engine_lead_approaches,
    get_masked_climax_teaser,
    load_quest_engines_catalog,
    normalize_quest_locale,
)
from mechanics.world.locations.hierarchy import format_short_venue_display, get_clean_leaf_location

log = logging.getLogger(__name__)

_CLUE_ELIGIBLE_BOUNTY_ENGINES = frozenset({"MYSTERY_CASE", "SOCIAL_BROKERAGE", "MAIN_MYSTERY", "INVESTIGATION", "SOCIAL_MANIPULATION"})
_MICRO_QUEST_PREFIXES = ("RMR-", "MNR-", "MAND-")
_LEAK_RE = re.compile(
    r"(?:\[(?:ITEM|GEAR|SPELLBOOK)_JSON\]|\b(?:HP|MP|DC)\s*[:=]?\s*\d+|\{\s*[a-z_]+\s*\})",
    re.IGNORECASE,
)
_BACKGROUND_PLAN_TASKS: Set[asyncio.Task[Any]] = set()
_IN_FLIGHT_PLANS: Set[Tuple[int, str]] = set()
_IN_FLIGHT_RESTITCHES: Set[Tuple[int, str, str]] = set()
_PLAN_SCHEDULE_LOCK = threading.Lock()


def _resolve_target_event_loop() -> Tuple[Optional[asyncio.AbstractEventLoop], bool]:
    """Returns `(loop, is_loop_thread)` supporting both async callers and `adb` worker threads."""
    try:
        return asyncio.get_running_loop(), True
    except RuntimeError:
        import db

        main_loop = db.get_main_event_loop()
        if main_loop is not None and not main_loop.is_closed() and main_loop.is_running():
            return main_loop, False
        return None, False


def is_clue_based_quest(family_tier: str, engine: str) -> bool:
    """Decision 6: Strictly MYSTERY_CASE and SOCIAL_BROKERAGE use key_clue 3-source stages."""
    return str(engine or "").strip().upper() in _CLUE_ELIGIBLE_BOUNTY_ENGINES


def is_full_arc_blueprint_eligible(family_tier: str, engine: str = "", quest_id: str = "") -> bool:
    """Decision 1: Story quests, full Bounties (all 8 engines), Companion Loyalty (CLR-), and Faction/World arcs get full-arc blueprints."""
    qid_u = str(quest_id or "").strip().upper()
    if qid_u.startswith(_MICRO_QUEST_PREFIXES):
        return False
    fam = str(family_tier or "").strip().lower()
    if fam in ("micro", "rumor", "minor"):
        return False
    if fam in ("story", "bounty", "loyalty", "world_event", "faction", "dispatch"):
        return True
    return qid_u.startswith(("SQ-", "BQ-", "CLR-", "FARC-"))


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
    (plus transient `namegen` cast padding when early-campaign contacts are sparse, without DB writes).
    """
    import db
    from mechanics.narrative.dossier_compiler import _pick_safe_npc_name, is_safe_sanctuary_location

    climax_loc = str(climax_location or (dossier.get("climax_spec") or {}).get("location") or "").strip()
    climax_leaf = _canon_loc_leaf(climax_loc)
    climax_spec = dossier.get("climax_spec") or {}
    qid = str(dossier.get("quest_id") or "")

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
        all_nodes = list(db.get_session_world_nodes(session_id) or [])
        parent_ids = {
            str(n.get("parent_id") or "")
            for n in all_nodes
            if isinstance(n, dict) and n.get("parent_id")
        }
        for node in all_nodes:
            if not isinstance(node, dict):
                continue
            nt = str(node.get("node_type") or "").upper()
            nid = str(node.get("node_id") or "")
            priv = str(node.get("privacy_level") or "public").lower()
            if priv == "private":
                continue
            if nt in ("ROOM", "FACILITY", "POI") or (nt == "BUILDING" and nid and nid not in parent_ids):
                tiered = db.format_node_tiered_location(session_id, nid) if nid else ""
                _add_room(tiered or node.get("name"))
        # Include non-climax rooms already bound to leads or main stages (avoid bare parent zones)
        for st in (climax_spec.get("main_stages") or []):
            if isinstance(st, dict) and not st.get("is_climax_stage"):
                st_tloc = str(st.get("target_location") or "").strip()
                if st_tloc and ("➔" in st_tloc or "->" in st_tloc or not rooms):
                    _add_room(st_tloc)
                for src in (st.get("clue_sources") or []):
                    if isinstance(src, dict):
                        _add_room(src.get("location"))

    # Stratify rooms round-robin across zone/building buckets so multi-stage leads span distinct areas
    if len(rooms) > 1:
        buckets: Dict[str, List[str]] = {}
        for r_item in rooms:
            segs = [p.strip().lower() for p in r_item.replace("->", "➔").split("➔") if p.strip()]
            b_key = "➔".join(segs[:2]) if len(segs) >= 2 else (segs[0] if segs else r_item.lower())
            buckets.setdefault(b_key, []).append(r_item)
        stratified: List[str] = []
        bucket_lists = list(buckets.values())
        while bucket_lists:
            nxt_buckets: List[List[str]] = []
            for bl in bucket_lists:
                stratified.append(bl.pop(0))
                if bl:
                    nxt_buckets.append(bl)
            bucket_lists = nxt_buckets
        rooms = stratified

    npcs: List[str] = []
    seen_npc: Set[str] = set()
    excluded_low: Set[str] = {"player", "none", "unknown"}
    scen_key = "fantasy"
    if session_id:
        sess = db.get_session(session_id) or {}
        scen_key = str(sess.get("scenario") or scen_key or "fantasy")
        for d_nm in (sess.get("dead_characters") or []):
            if str(d_nm or "").strip():
                excluded_low.add(str(d_nm).strip().lower())
        for p_npc in (db.get_session_party_npcs(session_id) or []):
            if isinstance(p_npc, dict) and p_npc.get("name"):
                excluded_low.add(str(p_npc["name"]).strip().lower())
        try:
            p_char = db.get_session_player_character(session_id) or {}
            if p_char.get("name"):
                excluded_low.add(str(p_char["name"]).strip().lower())
        except Exception:
            pass
    for antagonist_k in ("target_npc", "true_culprit", "innocent_suspect"):
        a_val = str(dossier.get(antagonist_k) or climax_spec.get(antagonist_k) or "").strip()
        if a_val:
            excluded_low.add(a_val.lower())

    def _add_npc(raw_npc: Any) -> None:
        nm = str(raw_npc or "").strip()
        if not nm:
            return
        low = nm.lower()
        if low in excluded_low:
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

    # Decision 8: Pad sparse early-campaign cast with deterministic namegen names (never mutating contacts table)
    synthetic_npcs: List[str] = []
    avoid_pad = set(excluded_low) | set(seen_npc)
    pad_idx = 0
    while len(npcs) < 4 and pad_idx < 12:
        pad_idx += 1
        synth_nm, _, _ = _pick_safe_npc_name(
            session_id,
            scen_key,
            f"chapter_plan_cast:{session_id}:{qid}:{pad_idx}",
            avoid_low=avoid_pad,
        )
        synth_clean = str(synth_nm or "").strip()
        if not synth_clean:
            continue
        s_low = synth_clean.lower()
        if s_low in avoid_pad:
            continue
        avoid_pad.add(s_low)
        seen_npc.add(s_low)
        npcs.append(synth_clean)
        synthetic_npcs.append(synth_clean)

    return {"rooms": rooms, "npcs": npcs, "synthetic_npcs": synthetic_npcs, "climax_location": climax_loc}


def validate_chapter_plan(
    plan: Any,
    *,
    candidate_rooms: List[str],
    candidate_npcs: List[str],
    climax_location: str,
    expected_clue_stage_indices: List[int],
    expected_stage_indices: Optional[List[int]] = None,
    climax_stage_index: Optional[int] = None,
    engine: str = "",
    target_npc: str = "",
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Strictly validates an AI `ChapterPlan` against Q5/E3 & Full-Arc invariants:
    - Clue stages use canonical rooms from `candidate_rooms` (never sanctuaries or climax) with >= 3 distinct-room sources.
    - Action stages validate canonical `target_location` (not climax) and optional `target_npc`.
    - Climax stages may reference `climax_location` and `target_npc`.
    - Witness NPCs and primary stage rooms are pairwise disjoint across non-climax stages.
    - `masked_climax_teaser` and `optional_specs` never leak stats/JSON or secret climax venue.
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
    distinct_non_climax_leaves: Set[str] = set()
    climax_low = str(climax_location or "").strip().lower()
    climax_leaf = _canon_loc_leaf(climax_location)
    for r in candidate_rooms:
        canon = str(r).strip()
        if not canon:
            continue
        r_leaf = _canon_loc_leaf(canon)
        room_map[canon.lower()] = canon
        room_map.setdefault(r_leaf, canon)
        if r_leaf and r_leaf != climax_leaf:
            distinct_non_climax_leaves.add(r_leaf)

    npc_map: Dict[str, str] = {str(n).strip().lower(): str(n).strip() for n in candidate_npcs if str(n or "").strip()}
    teaser = str(raw.get("masked_climax_teaser") or "").strip()
    if teaser:
        if _LEAK_RE.search(teaser):
            errors.append("masked_climax_teaser contains internal stat/JSON tokens.")
        if climax_leaf and len(climax_leaf) >= 4 and climax_leaf in teaser.lower():
            errors.append("masked_climax_teaser leaks climax venue name.")

    stages_in = raw.get("stages") or []
    stages_by_idx: Dict[int, Dict[str, Any]] = {}
    for st in stages_in:
        if isinstance(st, dict):
            s_i = int(st.get("stage_index") or 0)
            if s_i > 0:
                stages_by_idx[s_i] = dict(st)

    clue_set: Set[int] = {int(x) for x in (expected_clue_stage_indices or [])}
    req_non_climax: List[int] = (
        [int(x) for x in expected_stage_indices if int(x) != int(climax_stage_index or -1)]
        if expected_stage_indices is not None
        else list(expected_clue_stage_indices or [])
    )

    clean_stages: List[Dict[str, Any]] = []
    seen_witness_npcs: Set[str] = set()
    seen_primary_leaves: Set[str] = set()
    enforce_primary_room_disjoint = (
        len(req_non_climax) >= 2 and len(distinct_non_climax_leaves) >= len(req_non_climax)
    )

    for req_idx in req_non_climax:
        st = stages_by_idx.get(req_idx)
        if not st:
            errors.append(f"Missing required stage_index={req_idx}.")
            continue
        s_lbl = str(st.get("stage_label") or "").strip()
        if not s_lbl or _LEAK_RE.search(s_lbl):
            errors.append(f"Stage {req_idx}: invalid or leaking stage_label.")
        raw_bc = st.get("beat_contract")
        bc = {"player_verb": raw_bc.strip()} if isinstance(raw_bc, str) and raw_bc.strip() else (dict(raw_bc) if isinstance(raw_bc, dict) else {})
        is_clue_stage = req_idx in clue_set

        if is_clue_stage:
            raw_kc = st.get("key_clue")
            if isinstance(raw_kc, str) and raw_kc.strip():
                s = raw_kc.strip()
                kc = {"title": s[:80].strip(), "lead_text": f"Evidence related to {s}."}
            elif isinstance(raw_kc, dict):
                kc = dict(raw_kc)
            else:
                kc = {}
            if not str(kc.get("title") or "").strip():
                for syn in ("name", "clue", "clue_title", "label", "item"):
                    if kc.get(syn) and str(kc[syn]).strip():
                        kc["title"] = str(kc[syn]).strip()
                        break
            if not str(kc.get("lead_text") or "").strip():
                for syn in ("description", "summary", "details", "text", "clue_text"):
                    if kc.get(syn) and str(kc[syn]).strip():
                        kc["lead_text"] = str(kc[syn]).strip()
                        break
            kc_title = str(kc.get("title") or "").strip()
            kc_lead = str(kc.get("lead_text") or "").strip()
            if kc_title and not kc_lead:
                kc_lead = f"Evidence confirming {kc_title}."
                kc["lead_text"] = kc_lead
            elif kc_lead and not kc_title:
                kc_title = kc_lead[:60].strip()
                kc["title"] = kc_title
            if not kc_title or not kc_lead:
                errors.append(f"Stage {req_idx}: key_clue must include non-empty title and lead_text.")
            if _LEAK_RE.search(kc_title) or _LEAK_RE.search(kc_lead):
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
                    w_low = canon_npc.lower()
                    if len(npc_map) >= 2 and w_low in seen_witness_npcs:
                        errors.append(
                            f"Stage {req_idx} witness source #{src_idx+1}: duplicate witness NPC '{canon_npc}' across stages."
                        )
                        continue
                    seen_witness_npcs.add(w_low)

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

            primary_loc = clean_sources[0]["location"] if clean_sources else ""
            if enforce_primary_room_disjoint and primary_loc:
                p_leaf = _canon_loc_leaf(primary_loc)
                if p_leaf in seen_primary_leaves:
                    errors.append(f"Stage {req_idx}: duplicate primary room '{primary_loc}' across stages.")
                elif p_leaf:
                    seen_primary_leaves.add(p_leaf)

            clean_stages.append(
                {
                    "stage_index": req_idx,
                    "stage_label": s_lbl,
                    "is_climax_stage": False,
                    "target_location": primary_loc or str(st.get("target_location") or ""),
                    "target_npc": next((s["npc_name"] for s in clean_sources if s.get("npc_name")), ""),
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
        else:
            # Engine-native action stage (HEIST_BREACH, HUNT_CONTAINMENT, ACQUISITION_EXCHANGE, CRISIS_DEFENSE, RIVALRY_SHOWDOWN, INTIMATE_LIAISON)
            raw_loc = str(st.get("target_location") or st.get("location") or "").strip()
            canon_loc = room_map.get(raw_loc.lower()) or room_map.get(_canon_loc_leaf(raw_loc))
            if not canon_loc:
                errors.append(f"Stage {req_idx}: off-list action target_location '{raw_loc}'.")
            else:
                c_leaf = _canon_loc_leaf(canon_loc)
                if canon_loc.lower() == climax_low or (climax_leaf and c_leaf == climax_leaf):
                    errors.append(f"Stage {req_idx}: action stage cannot reuse climax room '{canon_loc}'.")
                elif enforce_primary_room_disjoint:
                    if c_leaf in seen_primary_leaves:
                        errors.append(f"Stage {req_idx}: duplicate primary room '{canon_loc}' across stages.")
                    elif c_leaf:
                        seen_primary_leaves.add(c_leaf)

            raw_npc = str(st.get("target_npc") or st.get("npc_name") or "").strip()
            canon_npc = ""
            if raw_npc:
                canon_npc = npc_map.get(raw_npc.lower(), "")
                if not canon_npc and target_npc and raw_npc.lower() == target_npc.strip().lower():
                    canon_npc = target_npc.strip()
                if not canon_npc:
                    errors.append(f"Stage {req_idx}: action NPC '{raw_npc}' not in candidate_npcs.")
                else:
                    n_low = canon_npc.lower()
                    if len(npc_map) >= 2 and n_low in seen_witness_npcs:
                        errors.append(f"Stage {req_idx}: duplicate NPC '{canon_npc}' across stages.")
                    seen_witness_npcs.add(n_low)

            apprs = [str(a).upper() for a in (st.get("approaches") or ["INT", "AGI", "CHA"]) if str(a or "").strip()]
            clean_stages.append(
                {
                    "stage_index": req_idx,
                    "stage_label": s_lbl,
                    "is_climax_stage": False,
                    "target_location": canon_loc or raw_loc,
                    "target_npc": canon_npc,
                    "approaches": apprs or ["INT", "AGI", "CHA"],
                    "beat_contract": {
                        "player_verb": str(bc.get("player_verb") or s_lbl).strip(),
                        "reveal": str(bc.get("reveal") or "").strip(),
                        "handover": str(bc.get("handover") or "").strip(),
                        "next_pointer": str(bc.get("next_pointer") or "").strip(),
                    },
                }
            )

    # Optional Climax stage in full-arc plan
    climax_st = None
    if climax_stage_index and climax_stage_index in stages_by_idx:
        climax_st = stages_by_idx[climax_stage_index]
    else:
        for st_cand in stages_in:
            if isinstance(st_cand, dict) and st_cand.get("is_climax_stage"):
                climax_st = dict(st_cand)
                break
    if climax_st:
        c_lbl = str(climax_st.get("stage_label") or "").strip()
        if not c_lbl or _LEAK_RE.search(c_lbl):
            errors.append("Climax stage: invalid or leaking stage_label.")
        raw_cbc = climax_st.get("beat_contract")
        cbc = {"player_verb": raw_cbc.strip()} if isinstance(raw_cbc, str) and raw_cbc.strip() else (dict(raw_cbc) if isinstance(raw_cbc, dict) else {})
        c_verb = str(cbc.get("player_verb") or c_lbl).strip()
        if _LEAK_RE.search(c_verb):
            errors.append("Climax stage: beat_contract.player_verb contains internal stat/JSON tokens.")
        clean_stages.append(
            {
                "stage_index": int(climax_st.get("stage_index") or climax_stage_index or (len(req_non_climax) + 1)),
                "stage_label": c_lbl,
                "is_climax_stage": True,
                "target_location": climax_location or str(climax_st.get("target_location") or ""),
                "target_npc": str(climax_st.get("target_npc") or target_npc or ""),
                "beat_contract": {
                    "player_verb": c_verb,
                    "reveal": str(cbc.get("reveal") or "").strip(),
                    "handover": str(cbc.get("handover") or "").strip(),
                    "next_pointer": str(cbc.get("next_pointer") or "").strip(),
                },
            }
        )

    clean_opt_specs: List[Dict[str, Any]] = []
    for o_idx, o_raw in enumerate((raw.get("optional_specs") or [])[:4]):
        if not isinstance(o_raw, dict):
            continue
        o_lbl = str(o_raw.get("label") or "").strip()
        o_hint = str(o_raw.get("approach_hint") or "").strip()
        if _LEAK_RE.search(o_lbl) or _LEAK_RE.search(o_hint):
            errors.append(f"Optional #{o_idx+1}: leaks internal stat/JSON tokens.")
            continue
        o_loc_raw = str(o_raw.get("target_location") or "").strip()
        o_loc_canon = room_map.get(o_loc_raw.lower()) or room_map.get(_canon_loc_leaf(o_loc_raw)) if o_loc_raw else ""
        if o_loc_raw and not o_loc_canon:
            errors.append(f"Optional #{o_idx+1}: off-list room '{o_loc_raw}'.")
            continue
        if o_loc_canon and climax_leaf and _canon_loc_leaf(o_loc_canon) == climax_leaf:
            errors.append(f"Optional #{o_idx+1}: cannot target climax room '{o_loc_canon}'.")
            continue
        o_npc_raw = str(o_raw.get("target_npc") or "").strip()
        o_npc_canon = npc_map.get(o_npc_raw.lower(), "") if o_npc_raw else ""
        if o_npc_raw and not o_npc_canon:
            errors.append(f"Optional #{o_idx+1}: NPC '{o_npc_raw}' not in candidate_npcs.")
            continue
        if o_lbl:
            clean_opt_specs.append(
                {
                    "role": str(o_raw.get("role") or "aid").strip().lower(),
                    "label": o_lbl[:180],
                    "target_location": o_loc_canon,
                    "target_npc": o_npc_canon,
                    "approach_hint": o_hint[:180],
                }
            )

    clean_non_climax = [s for s in clean_stages if not s.get("is_climax_stage")]
    is_valid = len(errors) == 0 and len(clean_non_climax) == len(req_non_climax)
    return is_valid, errors, {
        "title": title,
        "objective": objective,
        "climax_location": climax_location,
        "masked_climax_teaser": teaser,
        "stages": clean_stages,
        "optional_hooks": list(raw.get("optional_hooks") or [])[:4],
        "optional_specs": clean_opt_specs,
    }


_CLIMAX_CONFRONT_TPL: Dict[str, str] = {
    "en": "Confront {target} at {venue}",
    "pl": "Zmierz się z {target} w: {venue}",
    "ms": "Bersemuka dengan {target} di {venue}",
    "zh": "在{venue}与{target}展开对决",
    "de": "Stelle {target} bei {venue}",
}


def build_causal_deterministic_plan(
    session_id: int,
    quest_id: str,
    dossier: Dict[str, Any],
) -> Dict[str, Any]:
    """Builds a full-arc deterministic ChapterPlan (all stages + climax + teaser + optionals) with disjoint cast & primary rooms."""
    import db

    dos = dossier if isinstance(dossier, dict) else {}
    sess = db.get_session(session_id) or {} if session_id else {}
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    scen_key = str(sess.get("scenario") or dos.get("scenario") or "fantasy")
    engine = str(dos.get("engine") or "MYSTERY_CASE").strip().upper()
    clue_mode = is_clue_based_quest(str(dos.get("family_tier") or ""), engine)
    climax_spec = dos.get("climax_spec") or {}
    pitch = dos.get("pitch_stub") or {}
    cands = build_chapter_plan_candidates(session_id, dos)
    cand_rooms = list(cands.get("rooms") or [])
    cand_npcs = list(cands.get("npcs") or [])
    climax_loc = str(cands.get("climax_location") or climax_spec.get("location") or "Shadow Sanctum")
    q_title = str(pitch.get("title") or climax_spec.get("main_objective_text") or quest_id)
    q_obj = str(climax_spec.get("main_objective_text") or dos.get("objective") or q_title)
    target_npc = str(dos.get("target_npc") or climax_spec.get("target_npc") or "adversary")
    main_stages = [s for s in (climax_spec.get("main_stages") or []) if isinstance(s, dict)]
    if not main_stages:
        main_stages = [
            {"stage_index": 1, "stage_label": "Scout initial lead", "is_climax_stage": False},
            {"stage_index": 2, "stage_label": "Secure decisive leverage", "is_climax_stage": False},
            {"stage_index": 3, "stage_label": "Final confrontation", "is_climax_stage": True},
        ]

    used_primary_leaves: Set[str] = set()
    used_witnesses: Set[str] = set()
    built_stages: List[Dict[str, Any]] = []
    short_climax = format_short_venue_display(climax_loc) or get_clean_leaf_location(climax_loc, default=climax_loc)

    def _next_primary_room(preferred: str = "") -> str:
        pref_clean = str(preferred or "").strip()
        if pref_clean and _canon_loc_leaf(pref_clean) != _canon_loc_leaf(climax_loc):
            p_lf = _canon_loc_leaf(pref_clean)
            if p_lf and p_lf not in used_primary_leaves:
                used_primary_leaves.add(p_lf)
                return pref_clean
        for r in cand_rooms:
            lf = _canon_loc_leaf(r)
            if lf and lf not in used_primary_leaves:
                used_primary_leaves.add(lf)
                return r
        return cand_rooms[0] if cand_rooms else climax_loc

    def _next_witness_npc() -> str:
        for n in cand_npcs:
            n_clean = str(n or "").strip()
            if n_clean and n_clean.lower() not in used_witnesses:
                used_witnesses.add(n_clean.lower())
                return n_clean
        return cand_npcs[0] if cand_npcs else ""

    for idx_i, ms in enumerate(main_stages):
        st_idx = int(ms.get("stage_index") or (idx_i + 1))
        if ms.get("is_climax_stage"):
            c_lbl = str(ms.get("stage_label") or "").strip()
            if not c_lbl or " at " not in c_lbl.lower():
                tpl = _CLIMAX_CONFRONT_TPL.get(lang, _CLIMAX_CONFRONT_TPL["en"])
                c_lbl = tpl.format(target=target_npc, venue=short_climax)
            c_bc = dict(ms.get("beat_contract") or {})
            built_stages.append(
                {
                    "stage_index": st_idx,
                    "stage_label": c_lbl,
                    "is_climax_stage": True,
                    "target_location": climax_loc,
                    "target_npc": target_npc,
                    "beat_contract": {
                        "player_verb": str(c_bc.get("player_verb") or c_lbl),
                        "reveal": str(c_bc.get("reveal") or f"{target_npc} stands cornered as all threads converge."),
                        "handover": str(c_bc.get("handover") or ""),
                        "next_pointer": short_climax,
                    },
                }
            )
            continue

        prim_room = _next_primary_room(str(ms.get("target_location") or ""))
        short_prim = format_short_venue_display(prim_room) or get_clean_leaf_location(prim_room, default=prim_room)
        w_npc = _next_witness_npc()
        existing_bc = dict(ms.get("beat_contract") or {})
        st_lbl = str(ms.get("stage_label") or f"Investigate {short_prim}").strip()
        if clue_mode:
            kc = dict(ms.get("key_clue") or {})
            kc_title = str(kc.get("title") or st_lbl or f"Lead Fragment {st_idx}").strip()
            kc_lead = str(kc.get("lead_text") or existing_bc.get("reveal") or f"Recovered proof linking {short_prim} to the scheme.").strip()
            stage_locs = [prim_room]
            for r in cand_rooms:
                if len(stage_locs) >= 3:
                    break
                if _canon_loc_leaf(r) not in {_canon_loc_leaf(x) for x in stage_locs}:
                    stage_locs.append(r)
            while len(stage_locs) < 3 and cand_rooms:
                stage_locs.append(cand_rooms[len(stage_locs) % len(cand_rooms)])
            sources = []
            for s_pos, (skind, sstat) in enumerate([("witness", "CHA"), ("record", "INT"), ("item", "PER")]):
                s_loc = stage_locs[s_pos] if s_pos < len(stage_locs) else prim_room
                s_npc = w_npc if skind == "witness" else ""
                vhint, _ = build_clue_source_prose(kind=skind, location=s_loc, clue_title=kc_title, npc_name=s_npc, lang=lang)
                sources.append(
                    {
                        "source_id": f"S{st_idx}-{s_pos+1}",
                        "kind": skind,
                        "location": s_loc,
                        "npc_name": s_npc,
                        "approach_hint": vhint,
                        "stat": sstat,
                        "dc_offset": 0,
                    }
                )
            built_stages.append(
                {
                    "stage_index": st_idx,
                    "stage_label": st_lbl,
                    "is_climax_stage": False,
                    "target_location": prim_room,
                    "target_npc": w_npc,
                    "key_clue": {"title": kc_title, "lead_text": kc_lead, "category": "witness" if w_npc else "document"},
                    "clue_sources": sources,
                    "beat_contract": {
                        "player_verb": str(existing_bc.get("player_verb") or st_lbl),
                        "reveal": kc_lead,
                        "handover": kc_title,
                        "next_pointer": str(existing_bc.get("next_pointer") or short_climax),
                    },
                }
            )
        else:
            raw_apprs = [
                str(a.get("stat") if isinstance(a, dict) else a).upper()
                for a in (ms.get("approaches") or [])
                if str(a.get("stat") if isinstance(a, dict) else a).strip()
            ]
            built_stages.append(
                {
                    "stage_index": st_idx,
                    "stage_label": st_lbl,
                    "is_climax_stage": False,
                    "target_location": prim_room,
                    "target_npc": w_npc if engine in ("ACQUISITION_EXCHANGE", "RIVALRY_SHOWDOWN", "INTIMATE_LIAISON") else "",
                    "approaches": raw_apprs or ["INT", "AGI", "CHA"],
                    "beat_contract": {
                        "player_verb": str(existing_bc.get("player_verb") or st_lbl),
                        "reveal": str(existing_bc.get("reveal") or f"Action in {short_prim} clears the path toward {short_climax}."),
                        "handover": str(existing_bc.get("handover") or ""),
                        "next_pointer": str(existing_bc.get("next_pointer") or short_climax),
                    },
                }
            )

    opt_specs: List[Dict[str, Any]] = []
    for ld in (dos.get("leads_graph") or []):
        if isinstance(ld, dict) and ld.get("is_optional"):
            o_loc = str(ld.get("target_location") or "").strip()
            if _canon_loc_leaf(o_loc) == _canon_loc_leaf(climax_loc):
                o_loc = next((r for r in cand_rooms if _canon_loc_leaf(r) not in used_primary_leaves), cand_rooms[-1] if cand_rooms else "")
            opt_specs.append(
                {
                    "role": str(ld.get("role") or "aid").lower(),
                    "label": str(ld.get("title") or ld.get("label") or "Secure optional tactical edge"),
                    "target_location": o_loc if any(_canon_loc_leaf(r) == _canon_loc_leaf(o_loc) for r in cand_rooms) else (cand_rooms[-1] if cand_rooms else ""),
                    "target_npc": "",
                    "approach_hint": str(ld.get("stakes_hint") or ""),
                }
            )
    if not opt_specs and cand_rooms:
        opt_room = next((r for r in cand_rooms if _canon_loc_leaf(r) not in used_primary_leaves), cand_rooms[-1])
        opt_npc = _next_witness_npc()
        opt_specs.append(
            {
                "role": "bypass",
                "label": f"Scout alternate entry via {format_short_venue_display(opt_room) or _canon_loc_leaf(opt_room)}",
                "target_location": opt_room,
                "target_npc": opt_npc,
                "approach_hint": "Unlock side passage to ease final entry",
            }
        )

    teaser = get_masked_climax_teaser(engine, climax_spec, lang=lang)
    return {
        "title": q_title,
        "objective": q_obj,
        "climax_location": climax_loc,
        "masked_climax_teaser": teaser,
        "stages": built_stages,
        "optional_hooks": [o["label"] for o in opt_specs[:3]],
        "optional_specs": opt_specs[:3],
    }


async def generate_chapter_plan_with_resilience(
    session_id: int,
    quest_id: str,
    dossier: Dict[str, Any],
    *,
    timeout_seconds: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """
    Q4/Q6 + Full-Arc Blueprint: Calls the utility model (preserving NSFW routing) with bounded deadline
    and at most 1 validation-repair retry across all 8 canonical engines. Returns validated clean plan dict or None.
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
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    family_tier = str(dossier.get("family_tier") or "bounty")
    engine = str(dossier.get("engine") or "MYSTERY_CASE").strip().upper()
    if not is_full_arc_blueprint_eligible(family_tier, engine, quest_id):
        return None
    clue_mode = is_clue_based_quest(family_tier, engine)

    climax_spec = dossier.get("climax_spec") or {}
    main_stages = [s for s in (climax_spec.get("main_stages") or []) if isinstance(s, dict)]
    expected_indices = [
        int(s.get("stage_index") or i + 1)
        for i, s in enumerate(main_stages)
        if not s.get("is_climax_stage")
    ]
    climax_indices = [
        int(s.get("stage_index") or i + 1)
        for i, s in enumerate(main_stages)
        if s.get("is_climax_stage")
    ]
    climax_stage_idx = climax_indices[-1] if climax_indices else (max(expected_indices) + 1 if expected_indices else None)
    if not expected_indices:
        return None

    cand_rooms = cands["rooms"]
    cand_npcs = cands["npcs"]
    min_rooms_needed = 3 if (clue_mode or len(expected_indices) >= 2) else 1
    if len(cand_rooms) < min_rooms_needed:
        return None

    econ = dossier.get("contract_economy") or {}
    is_nsfw = bool(econ.get("uses_nsfw_routing") or scenario_data.uses_nsfw_model(scen_key))
    pitch = dossier.get("pitch_stub") or {}
    q_title = str(pitch.get("title") or climax_spec.get("main_objective_text") or quest_id)
    target_npc = str(dossier.get("target_npc") or climax_spec.get("target_npc") or "adversary")

    if clue_mode:
        mode_rules = (
            "2. Each non-climax stage MUST have >= 3 `clue_sources` in DISTINCT rooms from CANDIDATE_ROOMS.\n"
            "3. Every `'witness'` source MUST set `npc_name` verbatim from CANDIDATE_NPCS (use DISTINCT witnesses across stages); non-witness sources leave `npc_name` null.\n"
            "4. Keep each non-climax stage's primary room (`clue_sources[0].location`) DISTINCT across stages.\n"
        )
    else:
        mode_rules = (
            f"2. Quest engine is '{engine}': non-climax stages are focused ACTION beats (NOT clue_sources). Each non-climax stage sets `target_location` verbatim from CANDIDATE_ROOMS (DISTINCT across stages), optional `target_npc` from CANDIDATE_NPCS (DISTINCT), and `approaches` (3 stats from STR/PER/INT/CHA/AGI/LUK/BRIBE).\n"
            "3. Also include the Climax stage (`is_climax_stage: true`, targeting climax_location / target_adversary) and a spoiler-free `masked_climax_teaser`.\n"
            "4. Include 1-2 `optional_specs` (`role`: aid|bypass|alternative|threatened, `label`, `target_location` from CANDIDATE_ROOMS, `target_npc`, `approach_hint`).\n"
        )

    sys_prompt = (
        "You are designing a complete multi-stage quest blueprint for an interactive RPG.\n"
        f"Write ALL natural-language text in language code '{lang}'.\n"
        "STRICT RULES:\n"
        "1. Every non-climax `location` / `target_location` MUST be chosen verbatim from CANDIDATE_ROOMS (never invent rooms and never reuse the climax room).\n"
        f"{mode_rules}"
        "5. NEVER include raw HP, MP, DC numbers, dice math, or `[ITEM_JSON]` tags in any text.\n"
        "6. Output ONLY JSON matching schema: {'title': str, 'objective': str, 'masked_climax_teaser': str, 'optional_specs': [...], 'optional_hooks': [str], 'stages': [{'stage_index': int, 'stage_label': str, 'is_climax_stage': bool, 'target_location': str, 'target_npc': str, 'approaches': [str], 'beat_contract': {'player_verb': str, 'reveal': str, 'handover': str, 'next_pointer': str}, 'key_clue': {'title': str, 'lead_text': str}, 'clue_sources': [...]}]}."
    )
    usr_prompt = json.dumps(
        {
            "quest_title": q_title,
            "engine": engine,
            "scenario": scen_key,
            "chapter": int(climax_spec.get("chapter") or 1),
            "target_adversary": target_npc,
            "climax_location_forbidden_for_non_climax": cands["climax_location"],
            "expected_non_climax_stage_indices": expected_indices,
            "climax_stage_index": climax_stage_idx,
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
            if not plan_obj.title or len(plan_obj.title) < 3:
                plan_obj.title = q_title
            if not plan_obj.objective or len(plan_obj.objective) < 8:
                plan_obj.objective = str(climax_spec.get("main_objective_text") or dossier.get("objective") or q_title)

            # Attempt 0: validate raw LLM response first so validation errors drive Attempt-1 repair prompt.
            # Attempt >= 1: deterministic room/NPC auto-healing + cross-stage disjointness recovery before final validation.
            if attempt >= 1:
                climax_leaf_heal = _canon_loc_leaf(cands["climax_location"])
                cand_leaf_map = {_canon_loc_leaf(r): r for r in cand_rooms if r}
                cand_npc_set = {str(n).strip().lower() for n in cand_npcs if str(n or "").strip()}
                used_global_witnesses: Set[str] = set()
                used_global_primaries: Set[str] = set()
                for st_item in (plan_obj.stages or []):
                    if st_item.is_climax_stage:
                        st_item.target_location = cands["climax_location"]
                        if not st_item.target_npc:
                            st_item.target_npc = target_npc
                        continue
                    if clue_mode:
                        used_stage_leaves: Set[str] = set()
                        healed_sources: List[ChapterPlanClueSource] = []
                        stage_kc_title = str(
                            (st_item.key_clue.title if st_item.key_clue else "")
                            or st_item.stage_label
                            or ""
                        )
                        for src in (st_item.clue_sources or []):
                            src_loc = str(src.location or "").strip()
                            matched_room = cand_leaf_map.get(_canon_loc_leaf(src_loc)) or cand_leaf_map.get(src_loc.lower())
                            is_first = len(healed_sources) == 0
                            if (
                                not matched_room
                                or matched_room.lower() == cands["climax_location"].lower()
                                or _canon_loc_leaf(matched_room) == climax_leaf_heal
                                or _canon_loc_leaf(matched_room) in used_stage_leaves
                                or (is_first and len(cand_rooms) >= len(expected_indices) and _canon_loc_leaf(matched_room) in used_global_primaries)
                            ):
                                for r in cand_rooms:
                                    r_leaf = _canon_loc_leaf(r)
                                    if (
                                        r_leaf not in used_stage_leaves
                                        and r.lower() != cands["climax_location"].lower()
                                        and r_leaf != climax_leaf_heal
                                        and (not is_first or len(cand_rooms) < len(expected_indices) or r_leaf not in used_global_primaries)
                                    ):
                                        matched_room = r
                                        break
                            if matched_room:
                                src.location = matched_room
                                lf_m = _canon_loc_leaf(matched_room)
                                used_stage_leaves.add(lf_m)
                                if is_first:
                                    used_global_primaries.add(lf_m)
                            if str(src.kind or "").lower() == "witness":
                                raw_w = str(src.npc_name or "").strip().lower()
                                if raw_w not in cand_npc_set or (len(cand_npc_set) >= 2 and raw_w in used_global_witnesses):
                                    fresh_w = next((n for n in cand_npcs if n.strip().lower() not in used_global_witnesses), "")
                                    if fresh_w:
                                        src.npc_name = fresh_w
                                        used_global_witnesses.add(fresh_w.lower())
                                    else:
                                        src.kind = "record"
                                        src.npc_name = None
                                else:
                                    used_global_witnesses.add(raw_w)
                            if not src.approach_hint:
                                eff_hint, _ = build_clue_source_prose(
                                    kind=str(src.kind or "record").lower(),
                                    location=str(src.location or matched_room or ""),
                                    clue_title=stage_kc_title,
                                    npc_name=str(src.npc_name or ""),
                                    lang=lang,
                                )
                                src.approach_hint = eff_hint
                            healed_sources.append(src)
                        for r in cand_rooms:
                            if len(healed_sources) >= 3:
                                break
                            r_leaf = _canon_loc_leaf(r)
                            if r_leaf not in used_stage_leaves and r.lower() != cands["climax_location"].lower() and r_leaf != climax_leaf_heal:
                                used_stage_leaves.add(r_leaf)
                                if len(healed_sources) == 0:
                                    used_global_primaries.add(r_leaf)
                                eff_hint, _ = build_clue_source_prose(
                                    kind="record",
                                    location=r,
                                    clue_title=stage_kc_title,
                                    npc_name="",
                                    lang=lang,
                                )
                                healed_sources.append(
                                    ChapterPlanClueSource(
                                        source_id=f"S{st_item.stage_index}-{len(healed_sources)+1}",
                                        kind="record",
                                        location=r,
                                        approach_hint=eff_hint,
                                    )
                                )
                        st_item.clue_sources = healed_sources
                    else:
                        raw_tl = str(st_item.target_location or "").strip()
                        matched_tl = cand_leaf_map.get(_canon_loc_leaf(raw_tl)) or cand_leaf_map.get(raw_tl.lower())
                        if not matched_tl or _canon_loc_leaf(matched_tl) == climax_leaf_heal or (
                            len(cand_rooms) >= len(expected_indices) and _canon_loc_leaf(matched_tl) in used_global_primaries
                        ):
                            matched_tl = next(
                                (r for r in cand_rooms if _canon_loc_leaf(r) != climax_leaf_heal and _canon_loc_leaf(r) not in used_global_primaries),
                                cand_rooms[0],
                            )
                        st_item.target_location = matched_tl
                        used_global_primaries.add(_canon_loc_leaf(matched_tl))
                        raw_an = str(st_item.target_npc or "").strip().lower()
                        if raw_an and (raw_an not in cand_npc_set or raw_an in used_global_witnesses):
                            st_item.target_npc = next((n for n in cand_npcs if n.strip().lower() not in used_global_witnesses), "")
                        if st_item.target_npc:
                            used_global_witnesses.add(st_item.target_npc.lower())

            ok, errors, clean_plan = validate_chapter_plan(
                plan_obj,
                candidate_rooms=cand_rooms,
                candidate_npcs=cand_npcs,
                climax_location=cands["climax_location"],
                expected_clue_stage_indices=expected_indices if clue_mode else [],
                expected_stage_indices=expected_indices,
                climax_stage_index=climax_stage_idx,
                engine=engine,
                target_npc=target_npc,
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
    s_row = conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not s_row or str(s_row["status"] or "active").strip().lower() != "active":
        return None
    fresh_dos = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not fresh_dos:
        return None
    if str(fresh_dos.get("status_stage") or "").strip().lower() != "prewarmed":
        q_row = conn.execute(
            "SELECT status FROM quests WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        if q_row is not None and str(q_row["status"] or "").strip().lower() != "active":
            return None
    sess = db.get_session(session_id) or {}
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    danger_tier = max(1, int(fresh_dos.get("danger_tier") or 1))
    engaged = int(fresh_dos.get("engaged_flag") or 0) != 0
    climax = dict(fresh_dos.get("climax_spec") or {})
    leads_graph: List[Dict[str, Any]] = [
        dict(ld) for ld in (fresh_dos.get("leads_graph") or []) if isinstance(ld, dict)
    ]
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
            kcid = str(existing.get("key_clue_id") or existing.get("clue_key") or "")
            if cid in (kc_id, legacy_id) or kcid in (kc_id, legacy_id) or int(existing.get("stage_index") or 0) == st_num_val:
                existing["title"] = str(kc_dict.get("title") or existing.get("title") or "")
                existing["summary"] = str(kc_dict.get("lead_text") or existing.get("summary") or "")
                existing["category"] = str(kc_dict.get("category") or existing.get("category") or "document")
                existing["stage_index"] = int(st_num_val)
                existing["key_clue_id"] = kc_id
                existing["clue_key"] = kc_id
                return
        clue_graph.append(
            {
                "clue_id": None,
                "clue_key": kc_id,
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
    obj_updated = ""
    leads_updated = False
    engine_dos = str(fresh_dos.get("engine") or "MYSTERY_CASE").strip().upper()
    clue_mode_dos = is_clue_based_quest(str(fresh_dos.get("family_tier") or ""), engine_dos)

    plan_teaser = str(plan.get("masked_climax_teaser") or "").strip()
    if plan_teaser and not _LEAK_RE.search(plan_teaser):
        c_leaf_chk = _canon_loc_leaf(str(climax.get("location") or ""))
        if not c_leaf_chk or len(c_leaf_chk) < 4 or c_leaf_chk not in plan_teaser.lower():
            if not engaged or not str(climax.get("masked_climax_teaser") or "").strip():
                climax["masked_climax_teaser"] = plan_teaser[:320]
                any_updated = True

    if not engaged:
        plan_obj_txt = str(plan.get("objective") or "").strip()
        if plan_obj_txt and not _LEAK_RE.search(plan_obj_txt):
            climax["main_objective_text"] = plan_obj_txt[:220]
            climax["label"] = plan_obj_txt[:220]
            obj_updated = plan_obj_txt[:220]
            any_updated = True

        opt_specs = [
            dict(sp)
            for sp in (plan.get("optional_specs") or [])
            if isinstance(sp, dict) and str(sp.get("label") or "").strip() and not _LEAK_RE.search(str(sp.get("label")))
        ]
        if opt_specs and leads_graph:
            matched_lead_ids: Set[int] = set()
            for sp in opt_specs:
                sp_role = str(sp.get("role") or "aid").lower()
                cand_idx = next(
                    (
                        i
                        for i, ld in enumerate(leads_graph)
                        if i not in matched_lead_ids
                        and ld.get("is_optional", True)
                        and str(ld.get("status") or "active").lower() not in ("completed", "failed", "bypassed")
                        and not ld.get("completed")
                        and not ld.get("claimed_by")
                        and str(ld.get("role") or "aid").lower() == sp_role
                    ),
                    None,
                )
                if cand_idx is None:
                    cand_idx = next(
                        (
                            i
                            for i, ld in enumerate(leads_graph)
                            if i not in matched_lead_ids
                            and ld.get("is_optional", True)
                            and str(ld.get("status") or "active").lower() not in ("completed", "failed", "bypassed")
                            and not ld.get("completed")
                            and not ld.get("claimed_by")
                        ),
                        None,
                    )
                if cand_idx is None:
                    break
                matched_lead_ids.add(cand_idx)
                ld = leads_graph[cand_idx]
                sp_lbl = str(sp["label"])[:180]
                ld["title"] = sp_lbl
                ld["label"] = sp_lbl
                if sp.get("target_location"):
                    ld["target_location"] = str(sp["target_location"])
                if sp.get("target_npc"):
                    ld["target_npc"] = str(sp["target_npc"])
                if sp.get("approach_hint"):
                    ld["stakes_hint"] = str(sp["approach_hint"])[:180]
                leads_updated = True
                any_updated = True
        else:
            opt_hooks = [
                str(h).strip()
                for h in (plan.get("optional_hooks") or [])
                if str(h or "").strip() and not _LEAK_RE.search(str(h))
            ]
            if opt_hooks and leads_graph:
                hook_idx = 0
                for ld in leads_graph:
                    if hook_idx >= len(opt_hooks):
                        break
                    if not ld.get("is_optional", True):
                        continue
                    ld_st = str(ld.get("status") or "active").lower()
                    if ld_st in ("completed", "failed", "bypassed") or ld.get("completed") or ld.get("claimed_by"):
                        continue
                    hook_txt = opt_hooks[hook_idx][:180]
                    ld["title"] = hook_txt
                    ld["label"] = hook_txt
                    hook_idx += 1
                    leads_updated = True
                    any_updated = True

    climax_plan_st = next((ps for ps in (plan.get("stages") or []) if isinstance(ps, dict) and ps.get("is_climax_stage")), None)

    for idx, st in enumerate(main_stages):
        st_num = int(st.get("stage_index") or (idx + 1))
        status = str(st.get("status") or "locked").lower()
        if status in ("completed", "bypassed") or st.get("completed"):
            continue
        if st.get("is_climax_stage"):
            p_c = plan_by_idx.get(st_num) or climax_plan_st
            if p_c:
                if p_c.get("stage_label"):
                    st["stage_label"] = str(p_c["stage_label"])
                    st["label"] = str(p_c["stage_label"])
                p_cbc = p_c.get("beat_contract") or {}
                cbc = dict(st.get("beat_contract") or {})
                for bk in ("player_verb", "reveal", "handover", "next_pointer"):
                    if p_cbc.get(bk):
                        cbc[bk] = str(p_cbc[bk])
                st["beat_contract"] = cbc
                main_stages[idx] = st
                any_updated = True
            continue
        p_st = plan_by_idx.get(st_num)
        if not p_st:
            continue

        cur_sources = [dict(s) for s in (st.get("clue_sources") or []) if isinstance(s, dict)]
        any_touched = any(
            str(s.get("status") or "open").lower() in ("claimed", "burned", "cold") or s.get("claimed_by")
            for s in cur_sources
        ) or bool(st.get("burned_approaches"))
        p_kc = p_st.get("key_clue") or {}
        p_bc = p_st.get("beat_contract") or {}
        has_clue_sources_plan = bool(p_st.get("clue_sources")) and clue_mode_dos

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
            if has_clue_sources_plan:
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
            elif not engaged and p_st.get("target_location"):
                st["target_location"] = str(p_st["target_location"])
                if "target_npc" in p_st:
                    st["target_npc"] = str(p_st.get("target_npc") or "")
            main_stages[idx] = st
            any_updated = True
        elif status == "locked":
            # Locked stages freely adopt AI rooms, NPCs, key_clue/clue_sources or engine-native action fields
            if p_st.get("stage_label"):
                st["stage_label"] = str(p_st["stage_label"])
                st["label"] = str(p_st["stage_label"])
            if has_clue_sources_plan:
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
            else:
                if p_st.get("target_location"):
                    st["target_location"] = str(p_st["target_location"])
                if "target_npc" in p_st:
                    st["target_npc"] = str(p_st.get("target_npc") or "")
                raw_ap = [str(a).upper() for a in (p_st.get("approaches") or []) if str(a or "").strip()]
                if raw_ap:
                    st["approaches"] = build_engine_lead_approaches(
                        raw_ap,
                        danger_tier=danger_tier,
                        allow_curfew_stealth=(engine_dos != "INTIMATE_LIAISON"),
                    )
                bc = dict(st.get("beat_contract") or {})
                for bk in ("player_verb", "reveal", "handover", "next_pointer"):
                    if p_bc.get(bk):
                        bc[bk] = str(p_bc[bk])
                bc["is_dialogue_beat"] = bool(st.get("target_npc"))
                st["beat_contract"] = bc
            main_stages[idx] = st
            any_updated = True

    if not any_updated:
        return fresh_dos

    climax["main_stages"] = main_stages
    climax["chapter_plan_applied"] = True
    if obj_updated:
        conn.execute(
            "UPDATE quests SET objective = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
            (obj_updated, time.time(), session_id, quest_id),
        )
    upsert_kwargs: Dict[str, Any] = {
        "climax_spec": climax,
        "clue_graph": clue_graph,
        "is_baseline_enrichment": not engaged,
        "sync_projection": True,
        "conn": conn,
    }
    if leads_updated:
        upsert_kwargs["leads_graph"] = leads_graph
    return db.upsert_quest_dossier(session_id, quest_id, **upsert_kwargs)


async def compile_or_apply_eager_quest_plan(
    session_id: int,
    quest_id: str,
    *,
    timeout_seconds: float = 10.0,
    dossier: Optional[Dict[str, Any]] = None,
    defer_apply: bool = False,
) -> Optional[Dict[str, Any]]:
    """Decision 2: Compiles full-arc ChapterPlan eagerly before Frame-1 choices, with causal deterministic fallback (zero locks across LLM)."""
    import db
    from db import adb

    if not session_id or not quest_id:
        return None
    try:
        dos = dossier or await adb(db.get_quest_dossier, session_id, quest_id)
        if not dos:
            return None
        if not is_full_arc_blueprint_eligible(
            str(dos.get("family_tier") or ""), str(dos.get("engine") or ""), quest_id
        ):
            return None if defer_apply else dos
        climax = dos.get("climax_spec") or {}
        if climax.get("chapter_plan_applied") or int(dos.get("engaged_flag") or 0) != 0:
            return None if defer_apply else dos

        plan = await generate_chapter_plan_with_resilience(
            session_id, quest_id, dos, timeout_seconds=timeout_seconds
        )
        if not plan:
            plan = await adb(build_causal_deterministic_plan, session_id, quest_id, dos)
        if not plan:
            return None if defer_apply else dos
        if defer_apply:
            return plan
        updated = await adb(apply_chapter_plan_to_dossier, session_id, quest_id, plan)
        return updated or dos
    except Exception as exc:
        log.warning("Eager ChapterPlan skipped for session %s quest %s: %s", session_id, quest_id, exc)
        return None if defer_apply else dossier


def apply_deterministic_downstream_restitch(
    session_id: int,
    quest_id: str,
    mutation_reason: str,
    mutation_context: Optional[Dict[str, Any]] = None,
    *,
    conn: Any = None,
) -> Optional[Dict[str, Any]]:
    """Decision 7: Synchronously repairs ONLY uncompleted/locked future stages & untouched climax on NPC death/recruitment, twist flip, or rival deal."""
    import db

    if not session_id or not quest_id:
        return None
    if conn is None:
        with db.UnitOfWork() as uow_conn:
            return apply_deterministic_downstream_restitch(
                session_id, quest_id, mutation_reason, mutation_context, conn=uow_conn
            )

    s_row = conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not s_row or str(s_row["status"] or "active").strip().lower() != "active":
        return None
    dos = db.get_quest_dossier(session_id, quest_id, conn=conn)
    if not dos:
        return None
    if str(dos.get("status_stage") or "").strip().lower() != "prewarmed":
        q_row = conn.execute(
            "SELECT status FROM quests WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        if q_row is not None and str(q_row["status"] or "").strip().lower() != "active":
            return None
    ctx = dict(mutation_context or {})
    reason = str(mutation_reason or "").strip().lower()
    sess = db.get_session(session_id) or {}
    lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
    climax = dict(dos.get("climax_spec") or {})
    prev_climax = json.loads(json.dumps(climax))
    main_stages = [dict(s) for s in (climax.get("main_stages") or []) if isinstance(s, dict)]
    cast_bindings = {k: (dict(v) if isinstance(v, dict) else v) for k, v in (dos.get("cast_bindings") or {}).items()}
    prev_cb = json.loads(json.dumps(cast_bindings))
    mutated = False

    cands = build_chapter_plan_candidates(session_id, dos)
    cand_npcs = [str(n).strip() for n in (cands.get("npcs") or []) if str(n or "").strip()]
    cand_rooms = [str(r).strip() for r in (cands.get("rooms") or []) if str(r or "").strip()]
    used_npcs_low: Set[str] = {
        str(s.get("target_npc") or "").strip().lower()
        for s in main_stages
        if str(s.get("target_npc") or "").strip()
    }

    if reason in ("npc_dead", "npc_recruited"):
        dead_nm = str(ctx.get("npc_name") or "").strip()
        dead_low = dead_nm.lower()
        if dead_low:
            used_npcs_low.add(dead_low)
            rep_npc = next((n for n in cand_npcs if n.lower() not in used_npcs_low), "")
            for idx, st in enumerate(main_stages):
                st_stat = str(st.get("status") or "locked").lower()
                if st.get("completed") or st_stat in ("completed", "bypassed"):
                    continue
                is_clx = bool(st.get("is_climax_stage"))
                st_npc = str(st.get("target_npc") or "").strip()
                if is_clx:
                    if reason == "npc_dead" and st_npc.lower() == dead_low and rep_npc:
                        st["target_npc"] = rep_npc
                        climax["target_npc"] = rep_npc
                        climax["true_culprit"] = rep_npc
                        venue_disp = format_short_venue_display(str(st.get("target_location") or climax.get("location") or ""))
                        st["stage_label"] = _CLIMAX_CONFRONT_TPL.get(lang, _CLIMAX_CONFRONT_TPL["en"]).format(
                            target=rep_npc, venue=venue_disp
                        )
                        st["label"] = st["stage_label"]
                        used_npcs_low.add(rep_npc.lower())
                        rep_npc = next((n for n in cand_npcs if n.lower() not in used_npcs_low), "")
                        mutated = True
                    main_stages[idx] = st
                    continue

                if st_npc.lower() == dead_low:
                    fresh_n = rep_npc or next((n for n in cand_npcs if n.lower() not in used_npcs_low), "")
                    if fresh_n:
                        st["target_npc"] = fresh_n
                        used_npcs_low.add(fresh_n.lower())
                        rep_npc = next((n for n in cand_npcs if n.lower() not in used_npcs_low), "")
                    else:
                        st["target_npc"] = ""
                    mutated = True

                srcs = [dict(s) for s in (st.get("clue_sources") or []) if isinstance(s, dict)]
                srcs_changed = False
                for s_idx, src in enumerate(srcs):
                    if (
                        str(src.get("kind") or "").lower() == "witness"
                        and str(src.get("status") or "open").lower() == "open"
                        and str(src.get("npc_name") or "").strip().lower() == dead_low
                    ):
                        fresh_w = next((n for n in cand_npcs if n.lower() not in used_npcs_low), "")
                        kc_t = str((st.get("key_clue") or {}).get("title") or st.get("stage_label") or "")
                        if fresh_w:
                            used_npcs_low.add(fresh_w.lower())
                            src["npc_name"] = fresh_w
                            vhint, rtxt = build_clue_source_prose("witness", str(src.get("location") or ""), kc_t, fresh_w, lang=lang)
                            src["approach_hint"] = vhint
                            src["discovery_text"] = rtxt
                        else:
                            src["kind"] = "record"
                            src["npc_name"] = ""
                            vhint, rtxt = build_clue_source_prose("record", str(src.get("location") or cand_rooms[0] if cand_rooms else ""), kc_t, "", lang=lang)
                            src["approach_hint"] = vhint
                            src["discovery_text"] = rtxt
                        srcs[s_idx] = src
                        srcs_changed = True
                        mutated = True
                if srcs_changed:
                    st["clue_sources"] = srcs
                main_stages[idx] = st

    elif reason == "twist_culprit_flip":
        new_culprit = str(ctx.get("new_culprit") or ctx.get("culprit") or "").strip()
        if new_culprit:
            climax["true_culprit"] = new_culprit
            climax["target_npc"] = new_culprit
            if isinstance(cast_bindings.get("target"), dict):
                cast_bindings["target"]["name"] = new_culprit
            else:
                cast_bindings["target"] = {"name": new_culprit, "role": "target"}
            if main_stages:
                last_st = dict(main_stages[-1])
                if not last_st.get("completed"):
                    venue_str = str(last_st.get("target_location") or climax.get("location") or "")
                    venue_disp = format_short_venue_display(venue_str) or get_clean_leaf_location(venue_str, default=venue_str)
                    tpl = _CLIMAX_CONFRONT_TPL.get(lang, _CLIMAX_CONFRONT_TPL["en"])
                    new_lbl = tpl.format(target=new_culprit, venue=venue_disp)
                    last_st["target_npc"] = new_culprit
                    last_st["stage_label"] = new_lbl
                    last_st["label"] = new_lbl
                    bc = dict(last_st.get("beat_contract") or {})
                    bc["player_verb"] = new_lbl
                    last_st["beat_contract"] = bc
                    main_stages[-1] = last_st
            mutated = True

    elif reason == "rival_deal":
        deal_summary = str(ctx.get("deal_summary") or ctx.get("label") or "").strip()
        if deal_summary:
            climax["rival_deal"] = {"summary": deal_summary[:220], "ally_npc": str(ctx.get("ally_npc") or "")}
            if main_stages and not main_stages[-1].get("completed"):
                bc = dict(main_stages[-1].get("beat_contract") or {})
                bc["reveal"] = deal_summary[:220]
                main_stages[-1]["beat_contract"] = bc
            mutated = True

    if not mutated:
        return dos

    climax["main_stages"] = main_stages
    try:
        eff_turn_rs = int(db.get_effective_session_turn(session_id, conn=conn) or 0)
        if climax != prev_climax:
            db.append_dossier_state_event(
                session_id,
                quest_id,
                eff_turn_rs,
                "climax_spec",
                prev_climax,
                climax,
                conn=conn,
            )
        if cast_bindings != prev_cb:
            db.append_dossier_state_event(
                session_id,
                quest_id,
                eff_turn_rs,
                "cast_bindings",
                prev_cb,
                cast_bindings,
                conn=conn,
            )
    except Exception:
        pass
    return db.upsert_quest_dossier(
        session_id,
        quest_id,
        climax_spec=climax,
        cast_bindings=cast_bindings,
        sync_projection=True,
        conn=conn,
    )


async def restitch_downstream_quest_stages(
    session_id: int,
    quest_id: str,
    mutation_reason: str,
    mutation_context: Optional[Dict[str, Any]] = None,
    *,
    timeout_seconds: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Decision 7: Deterministically repairs locked future stages on event mutation, then optionally polishes labels via 1 utility LLM delta call outside locks."""
    import db
    from db import adb
    import llm_client
    from mechanics.system.concurrency import acquire_background_session_lock

    try:
        repaired: Optional[Dict[str, Any]] = None
        async with acquire_background_session_lock(session_id) as acq_det:
            if not acq_det:
                return None
            repaired = await adb(
                apply_deterministic_downstream_restitch,
                session_id,
                quest_id,
                mutation_reason,
                mutation_context,
            )
        if not repaired:
            return None
        dos = repaired
        climax = dict(dos.get("climax_spec") or {})
        main_stages = [dict(s) for s in (climax.get("main_stages") or []) if isinstance(s, dict)]
        locked_stages = [
            s
            for s in main_stages
            if not s.get("completed") and str(s.get("status") or "").lower() in ("locked", "active")
            and (s.get("is_climax_stage") or str(s.get("status") or "").lower() == "locked")
        ]
        if not locked_stages:
            return dos

        sess = await adb(db.get_session, session_id) or {}
        if str(sess.get("status") or "active").strip().lower() != "active":
            return None
        lang = normalize_quest_locale(sess.get("narration_language") or sess.get("language") or "en")
        scen_key = str(sess.get("scenario") or "fantasy")
        econ = dos.get("contract_economy") or {}
        is_nsfw = bool(econ.get("uses_nsfw_routing") or scenario_data.uses_nsfw_model(scen_key))

        sys_p = (
            f"Rewrite ONLY the provided uncompleted/locked downstream quest stage labels in language '{lang}' to reflect a story mutation.\n"
            "Do NOT leak HP, MP, DC, or JSON tags. Output JSON: {'stages': [{'stage_index': int, 'stage_label': str, 'player_verb': str}]}"
        )
        usr_p = json.dumps(
            {
                "mutation_reason": mutation_reason,
                "mutation_context": dict(mutation_context or {}),
                "true_culprit": climax.get("true_culprit") or "",
                "stages": [
                    {
                        "stage_index": int(s.get("stage_index") or 0),
                        "stage_label": str(s.get("stage_label") or ""),
                        "target_npc": str(s.get("target_npc") or ""),
                        "is_climax_stage": bool(s.get("is_climax_stage")),
                    }
                    for s in locked_stages
                ],
            },
            ensure_ascii=False,
        )
        raw = await llm_client.call_llm_json(
            sys_p, usr_p, max_tokens=500, retries=0, is_nsfw=is_nsfw, use_utility=True, timeout=timeout_seconds
        )
        if not isinstance(raw, dict) or not isinstance(raw.get("stages"), list):
            return dos

        patch_by_idx = {
            int(item.get("stage_index") or 0): item
            for item in raw["stages"]
            if isinstance(item, dict) and int(item.get("stage_index") or 0) > 0
        }
        if not patch_by_idx:
            return dos

        def _apply_polish() -> Optional[Dict[str, Any]]:
            with db.UnitOfWork() as uow_conn:
                s_row = uow_conn.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if not s_row or str(s_row["status"] or "active").strip().lower() != "active":
                    return None
                fresh = db.get_quest_dossier(session_id, quest_id, conn=uow_conn)
                if not fresh:
                    return None
                if str(fresh.get("status_stage") or "").strip().lower() != "prewarmed":
                    q_row = uow_conn.execute(
                        "SELECT status FROM quests WHERE session_id = ? AND quest_id = ?",
                        (session_id, quest_id),
                    ).fetchone()
                    if q_row is not None and str(q_row["status"] or "").strip().lower() != "active":
                        return None
                f_climax = dict(fresh.get("climax_spec") or {})
                prev_f_climax = json.loads(json.dumps(f_climax))
                f_stages = [dict(s) for s in (f_climax.get("main_stages") or []) if isinstance(s, dict)]
                changed = False
                for idx, st in enumerate(f_stages):
                    s_i = int(st.get("stage_index") or (idx + 1))
                    st_stat = str(st.get("status") or "locked").lower()
                    if st.get("completed") or st_stat in ("completed", "bypassed"):
                        continue
                    if st_stat != "locked" and not st.get("is_climax_stage"):
                        continue
                    p_item = patch_by_idx.get(s_i)
                    if not p_item:
                        continue
                    new_lbl = str(p_item.get("stage_label") or "").strip()[:200]
                    if new_lbl and not _LEAK_RE.search(new_lbl):
                        st["stage_label"] = new_lbl
                        st["label"] = new_lbl
                        bc = dict(st.get("beat_contract") or {})
                        new_vb = str(p_item.get("player_verb") or new_lbl).strip()[:180]
                        if new_vb and not _LEAK_RE.search(new_vb):
                            bc["player_verb"] = new_vb
                        st["beat_contract"] = bc
                        f_stages[idx] = st
                        changed = True
                if not changed:
                    return fresh
                f_climax["main_stages"] = f_stages
                try:
                    eff_turn_pol = int(db.get_effective_session_turn(session_id, conn=uow_conn) or 0)
                    db.append_dossier_state_event(
                        session_id,
                        quest_id,
                        eff_turn_pol,
                        "climax_spec",
                        prev_f_climax,
                        f_climax,
                        conn=uow_conn,
                    )
                except Exception:
                    pass
                return db.upsert_quest_dossier(
                    session_id,
                    quest_id,
                    climax_spec=f_climax,
                    sync_projection=True,
                    conn=uow_conn,
                )

        async with acquire_background_session_lock(session_id) as acq_pol:
            if not acq_pol:
                return dos
            return await adb(_apply_polish) or dos
    except Exception as exc:
        log.debug("Downstream restitch LLM polish skipped (%s %s): %s", session_id, quest_id, exc)
        return None


def schedule_restitch_downstream_quest_stages(
    session_id: int,
    quest_id: str,
    mutation_reason: str,
    mutation_context: Optional[Dict[str, Any]] = None,
) -> Optional[asyncio.Task[Any]]:
    """Schedules non-blocking event-driven downstream restitch safely from event loop or `adb` worker threads."""
    if not session_id or not quest_id:
        return None
    loop, on_loop_thread = _resolve_target_event_loop()
    if loop is None:
        return None
    key = (int(session_id), str(quest_id), str(mutation_reason or ""))
    with _PLAN_SCHEDULE_LOCK:
        if key in _IN_FLIGHT_RESTITCHES:
            return None
        _IN_FLIGHT_RESTITCHES.add(key)

    def _start_task() -> asyncio.Task[Any]:
        task = loop.create_task(
            restitch_downstream_quest_stages(session_id, quest_id, mutation_reason, mutation_context)
        )
        _BACKGROUND_PLAN_TASKS.add(task)

        def _cleanup(t: asyncio.Task[Any]) -> None:
            _BACKGROUND_PLAN_TASKS.discard(t)
            with _PLAN_SCHEDULE_LOCK:
                _IN_FLIGHT_RESTITCHES.discard(key)

        task.add_done_callback(_cleanup)
        return task

    if on_loop_thread:
        return _start_task()
    try:
        loop.call_soon_threadsafe(_start_task)
    except RuntimeError:
        with _PLAN_SCHEDULE_LOCK:
            _IN_FLIGHT_RESTITCHES.discard(key)
    return None


async def run_background_chapter_plan(session_id: int, quest_id: str) -> Optional[Dict[str, Any]]:
    """Background coroutine for Chapter 2+ prewarm and Loyalty arc ChapterPlan generation."""
    import db
    from db import adb
    from mechanics.system.concurrency import acquire_background_session_lock

    try:
        dos = await adb(db.get_quest_dossier, session_id, quest_id)
        if not dos:
            return None
        if not is_full_arc_blueprint_eligible(
            str(dos.get("family_tier") or ""), str(dos.get("engine") or ""), quest_id
        ):
            return dos
        plan = await generate_chapter_plan_with_resilience(session_id, quest_id, dos, timeout_seconds=30.0)
        if not plan:
            plan = await adb(build_causal_deterministic_plan, session_id, quest_id, dos)
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
    loop, on_loop_thread = _resolve_target_event_loop()
    if loop is None:
        return None
    key = (int(session_id), str(quest_id))
    with _PLAN_SCHEDULE_LOCK:
        if key in _IN_FLIGHT_PLANS:
            return None
        _IN_FLIGHT_PLANS.add(key)

    def _start_task() -> asyncio.Task[Any]:
        task = loop.create_task(run_background_chapter_plan(session_id, quest_id))
        _BACKGROUND_PLAN_TASKS.add(task)

        def _cleanup(t: asyncio.Task[Any]) -> None:
            _BACKGROUND_PLAN_TASKS.discard(t)
            with _PLAN_SCHEDULE_LOCK:
                _IN_FLIGHT_PLANS.discard(key)

        task.add_done_callback(_cleanup)
        return task

    if on_loop_thread:
        return _start_task()
    try:
        loop.call_soon_threadsafe(_start_task)
    except RuntimeError:
        with _PLAN_SCHEDULE_LOCK:
            _IN_FLIGHT_PLANS.discard(key)
    return None
