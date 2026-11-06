from __future__ import annotations
"""
Canonical Global Folklore Encyclopedia & Procedural Pool Loader (`mechanics/world/folklore_codex.py`).

Manages:
- Layer-1 catalog loading & caching (`data/folklore_codex.json`, `data/anomaly_procedural_pools.json`)
- Track B (~40%) Canonical Folklore selection with strict non-mutating filtering (Type, Disposition,
  Temperament, Sapience, Threat Tier Band, Biome/Time, Active Breach Deduplication, Singular Retirement,
  Species Multi-Day Cooldown, Unseen 3.5x Priority, and Gore/Furry Variant Weighting)
- Deterministic `AnomalyBlueprint` construction (100% consistent stats, elements, behavior & taboos across playthroughs)
- Headless Omnichannel Encyclopedia payload builder (`build_encyclopedia_payload`) shared by FastAPI and Discord.
"""

import hashlib
import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import db

_log = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_PROCEDURAL_POOLS_PATH = _DATA_DIR / "anomaly_procedural_pools.json"
_FOLKLORE_CODEX_PATH = _DATA_DIR / "folklore_codex.json"

_POOLS_CACHE: Optional[Dict[str, Any]] = None
_CODEX_CACHE: Optional[Dict[str, Any]] = None


def load_procedural_pools(reload: bool = False) -> Dict[str, Any]:
    """Loads and caches `data/anomaly_procedural_pools.json`."""
    global _POOLS_CACHE
    if _POOLS_CACHE is None or reload:
        with _PROCEDURAL_POOLS_PATH.open("r", encoding="utf-8") as fh:
            _POOLS_CACHE = json.load(fh)
    return _POOLS_CACHE


def load_folklore_codex_data(reload: bool = False) -> Dict[str, Any]:
    """Loads and caches `data/folklore_codex.json`."""
    global _CODEX_CACHE
    if _CODEX_CACHE is None or reload:
        with _FOLKLORE_CODEX_PATH.open("r", encoding="utf-8") as fh:
            _CODEX_CACHE = json.load(fh)
    return _CODEX_CACHE


def get_folklore_codex_entries() -> List[Dict[str, Any]]:
    data = load_folklore_codex_data()
    return list(data.get("entries") or [])


def get_folklore_traditions() -> List[Dict[str, str]]:
    data = load_folklore_codex_data()
    return list(data.get("traditions") or [])


def get_folklore_entry_by_id(codex_id: str) -> Optional[Dict[str, Any]]:
    cid = str(codex_id or "").strip()
    if not cid:
        return None
    for entry in get_folklore_codex_entries():
        if entry.get("codex_id") == cid:
            return dict(entry)
    return None


def _resolve_type_anchor_phrase(anom_type: str) -> str:
    t = str(anom_type or "entity").strip().lower()
    if t == "object":
        return "the anomalous relic"
    if t == "phenomenon":
        return "the distortion locus"
    return "its core silhouette"


def format_taboo_entry_for_type(taboo_entry: Dict[str, Any], anom_type: str) -> Dict[str, Any]:
    """Formats `{anchor_fixture}` placeholders in taboo rules/protocols cleanly for entity/object/phenomenon."""
    anchor = _resolve_type_anchor_phrase(anom_type)
    out = dict(taboo_entry)
    for field in ("taboo_rule", "containment_protocol", "clue_hint", "backlash_note"):
        if field in out and isinstance(out[field], str) and "{anchor_fixture}" in out[field]:
            out[field] = out[field].replace("{anchor_fixture}", anchor)
    return out


def _collect_session_folklore_exclusions(session_id: Optional[int]) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    Returns `(active_ids, retired_ids, cooldown_ids, already_seen_ids)` for `session_id` + host/party accounts.
    """
    active_ids: Set[str] = set()
    retired_ids: Set[str] = set()
    cooldown_ids: Set[str] = set()
    seen_ids: Set[str] = set()

    if not session_id:
        return active_ids, retired_ids, cooldown_ids, seen_ids

    try:
        sess = db.get_session(int(session_id))
    except Exception as exc:
        _log.debug("get_session skipped in folklore state lookup: %s", exc)
        return active_ids, retired_ids, cooldown_ids, seen_ids
    if not sess:
        return active_ids, retired_ids, cooldown_ids, seen_ids

    cur_day = int(sess.get("current_day") or 1)

    for inc in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
        if isinstance(inc, dict) and not inc.get("resolved"):
            bp = inc.get("anomaly_blueprint")
            cid = str((bp or {}).get("codex_id") or inc.get("codex_id") or "").strip()
            if cid:
                active_ids.add(cid)

    try:
        open_quests = db.get_session_quests(int(session_id)) or []
        for q in open_quests:
            st = str(q.get("status") or "").strip().lower()
            if st in ("completed", "failed", "abandoned", "turned_in"):
                continue
            q_notes = str(q.get("quest_notes") or "")
            if "codex_id:" in q_notes:
                for part in q_notes.split("|"):
                    if part.strip().startswith("codex_id:"):
                        cid_q = part.strip().split(":", 1)[1].strip()
                        if cid_q:
                            active_ids.add(cid_q)
    except Exception as exc:
        _log.debug("get_session_quests skipped in folklore state lookup: %s", exc)

    for r in (sess.get("retired_folklore_ids") or []):
        if isinstance(r, dict) and r.get("codex_id"):
            retired_ids.add(str(r["codex_id"]))
        elif isinstance(r, str) and r.strip():
            retired_ids.add(r.strip())

    cooldowns = sess.get("folklore_cooldowns")
    if isinstance(cooldowns, dict):
        for cid, meta in cooldowns.items():
            avail_day = int(meta.get("available_day", 0)) if isinstance(meta, dict) else int(meta or 0)
            if cur_day < avail_day:
                cooldown_ids.add(str(cid))

    for f_item in (sess.get("anomaly_field_log") or []):
        if isinstance(f_item, dict) and f_item.get("codex_id"):
            seen_ids.add(str(f_item["codex_id"]))

    try:
        uids = db.get_session_participant_user_ids(int(session_id))
        for uid in uids:
            u_map = db.get_user_folklore_codex(uid)
            seen_ids.update(u_map.keys())
    except Exception as exc:
        _log.debug("get_user_folklore_codex skipped in folklore state lookup: %s", exc)

    return active_ids, retired_ids, cooldown_ids, seen_ids


def _entry_matches_forced_constraints(
    entry: Dict[str, Any],
    *,
    force_type: Optional[str] = None,
    force_disposition: Optional[str] = None,
    force_temperament: Optional[str] = None,
    force_sapience: Optional[str] = None,
    force_physicality: Optional[str] = None,
    force_element: Optional[str] = None,
) -> bool:
    """Strictly checks whether a Canonical Folklore entry satisfies caller constraints WITHOUT mutating it."""
    if force_type and str(entry.get("type") or "") != str(force_type).strip().lower():
        return False

    if force_physicality and str(entry.get("physicality") or "") != str(force_physicality).strip().lower():
        return False

    if force_sapience and str(entry.get("sapience") or "") != str(force_sapience).strip().lower():
        return False

    if force_element and str(entry.get("primary_element") or "") != str(force_element).strip().lower():
        return False

    if force_temperament:
        ft = str(force_temperament).strip().lower()
        if ft in ("timid", "volatile", "mischievous", "spook"):
            if str(entry.get("disposition") or "") == "hostile":
                return False
            if str(entry.get("non_hostile_temperament") or "") != ft:
                return False

    if force_disposition:
        fd = str(force_disposition).strip().lower()
        e_disp = str(entry.get("disposition") or "hostile").strip().lower()
        e_temp = str(entry.get("non_hostile_temperament") or "").strip().lower()
        if fd in ("hostile", "combat", "elimination"):
            if e_disp != "hostile":
                return False
        elif fd in ("non_hostile", "non-hostile"):
            if e_disp == "hostile":
                return False
        elif fd == "passive":
            if e_disp != "passive":
                return False
        elif fd in ("reactive", "volatile"):
            if e_disp != "reactive" and e_temp != "volatile":
                return False
        elif fd in ("timid", "mischievous", "spook"):
            if e_disp == "hostile" or e_temp != fd:
                return False

    return True


def select_canonical_folklore_entry(
    rng: random.Random,
    *,
    biome: str = "urban",
    t_bucket: str = "night",
    tier_rank: int = 3,
    session_id: Optional[int] = None,
    is_gore: bool = False,
    is_furry: bool = False,
    force_codex_id: Optional[str] = None,
    force_procedural: bool = False,
    folklore_spawn_chance: float = 0.40,
    force_type: Optional[str] = None,
    force_disposition: Optional[str] = None,
    force_temperament: Optional[str] = None,
    force_sapience: Optional[str] = None,
    force_physicality: Optional[str] = None,
    force_element: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Hybrid router for Track B (Canonical Folklore Codex):
    - If `force_codex_id` is passed, returns that exact canonical entry unconditionally.
    - If `force_procedural` is True, returns `None` (Track A).
    - Otherwise rolls `folklore_spawn_chance` (~40%) and selects a weighted match respecting
      tier band, biome/time, active deduplication, singular retirement, species cooldown, and unseen boost.
    """
    if force_procedural and not force_codex_id:
        return None

    if force_codex_id:
        explicit = get_folklore_entry_by_id(force_codex_id)
        if explicit:
            return explicit

    if rng.random() >= float(folklore_spawn_chance):
        return None

    all_entries = get_folklore_codex_entries()
    if not all_entries:
        return None

    active_ids, retired_ids, cooldown_ids, seen_ids = _collect_session_folklore_exclusions(session_id)
    excluded = active_ids | retired_ids | cooldown_ids
    eff_tier = max(1, min(5, int(tier_rank or 3)))

    strict_candidates: List[Dict[str, Any]] = []
    for e in all_entries:
        cid = str(e.get("codex_id") or "")
        if cid in excluded:
            continue
        if not _entry_matches_forced_constraints(
            e,
            force_type=force_type,
            force_disposition=force_disposition,
            force_temperament=force_temperament,
            force_sapience=force_sapience,
            force_physicality=force_physicality,
            force_element=force_element,
        ):
            continue
        min_t = int(e.get("min_tier", 1) or 1)
        max_t = int(e.get("max_tier", 5) or 5)
        if min_t <= eff_tier <= max_t:
            strict_candidates.append(e)

    if not strict_candidates:
        return None

    biome_time_pool = [
        e for e in strict_candidates
        if biome in (e.get("biomes") or []) and ("any" in (e.get("times") or []) or t_bucket in (e.get("times") or []))
    ]
    if not biome_time_pool:
        biome_time_pool = [e for e in strict_candidates if biome in (e.get("biomes") or [])]

    pool = biome_time_pool if (biome_time_pool and rng.random() < 0.80) else strict_candidates

    weights: List[float] = []
    for e in pool:
        w = 1.0
        cid = str(e.get("codex_id") or "")
        if cid not in seen_ids:
            w *= 3.5
        if biome in (e.get("biomes") or []):
            w *= 1.5
        if is_gore and e.get("is_visceral_horror"):
            w *= 2.2
        if is_furry and e.get("is_therian_native"):
            w *= 2.5
        weights.append(w)

    chosen = rng.choices(pool, weights=weights, k=1)[0]
    return dict(chosen)


def build_blueprint_from_codex_entry(
    entry: Dict[str, Any],
    *,
    biome: str = "urban",
    t_bucket: str = "night",
    tier_rank: int = 3,
    is_gore: bool = False,
    is_furry: bool = False,
) -> Dict[str, Any]:
    """
    Constructs a 100% deterministic `AnomalyBlueprint` from a Canonical Folklore Codex entry.
    Stats, elements, behavior, disposition, sapience, and taboos remain identical across all playthroughs.
    """
    pools = load_procedural_pools()
    taboos_by_id = {t["taboo_id"]: t for t in (pools.get("taboo_rules_catalog") or [])}

    cid = str(entry.get("codex_id") or "UNKNOWN")
    canon_name = str(entry.get("canonical_name") or "Unknown Anomaly")
    anom_type = str(entry.get("type") or "entity")
    anom_form = str(entry.get("form") or "spectral")
    form_label = str(entry.get("form_label") or anom_form.replace("_", " ").title())
    physicality = str(entry.get("physicality") or "ethereal")
    sapience = str(entry.get("sapience") or "instinctive")
    disposition = str(entry.get("disposition") or "hostile")
    nh_temp = str(entry.get("non_hostile_temperament") or "")
    prim_elem = str(entry.get("primary_element") or "kinetic")
    off_elem = entry.get("offensive_element")
    weaknesses = list(entry.get("weaknesses") or [])
    resistances = list(entry.get("resistances") or [])
    immunities = list(entry.get("immunities") or [])

    default_taboo = next(iter(taboos_by_id.values())) if taboos_by_id else {
        "taboo_id": "default_silence",
        "taboo_rule": "Do not speak aloud in its presence.",
        "containment_protocol": "Maintain absolute silence and avert gaze.",
        "violate_actions": ["speak", "shout", "call"],
        "appease_actions": ["silence", "bow"],
    }
    taboo_key = entry.get("taboo_id")
    base_taboo = format_taboo_entry_for_type(
        taboos_by_id.get(taboo_key, default_taboo) if taboo_key else default_taboo,
        anom_type,
    )
    taboo_rule = format_taboo_entry_for_type(
        {"taboo_rule": str(entry.get("custom_taboo_rule") or base_taboo.get("taboo_rule", ""))},
        anom_type,
    )["taboo_rule"]
    protocol = format_taboo_entry_for_type(
        {"containment_protocol": str(entry.get("custom_protocol") or base_taboo.get("containment_protocol", ""))},
        anom_type,
    )["containment_protocol"]

    taboo_dict = {
        "key": base_taboo.get("taboo_id", "default_silence"),
        "taboo_id": base_taboo.get("taboo_id", "default_silence"),
        "name": base_taboo.get("name", "Silence Taboo"),
        "taboo_rule": taboo_rule,
        "containment_protocol": protocol,
        "exploit_stats": list(base_taboo.get("exploit_stats") or ["INT", "PER"]),
        "violate_stats": list(base_taboo.get("violate_stats") or []),
        # A canonical weakness must never simultaneously be a taboo violation (exploiting it would heal the entity)
        "violate_elements": [e for e in (base_taboo.get("violate_elements") or []) if e not in weaknesses],
        "exploit_keywords": list(base_taboo.get("exploit_keywords") or []),
        "clue_hint": base_taboo.get("clue_hint", ""),
        "backlash_note": base_taboo.get("backlash_note", ""),
    }

    appearance = (
        str(entry.get("furry_appearance_override") or entry.get("appearance") or "")
        if (is_furry and anom_type == "entity")
        else str(entry.get("appearance") or "")
    )
    sensory_omen = (
        str(entry.get("gore_omen_override") or entry.get("sensory_omen") or "")
        if is_gore
        else str(entry.get("sensory_omen") or "")
    )

    disguise_profile = entry.get("disguise_profile")
    disguise_state = None
    if isinstance(disguise_profile, dict) and disguise_profile.get("disguise_alias"):
        disguise_state = {
            "is_disguised": True,
            "disguise_alias": str(disguise_profile["disguise_alias"]),
            "cover_desc": str(disguise_profile.get("cover_desc") or ""),
            "unmask_cue": str(
                disguise_profile.get("unmask_cue")
                or f"The mundane guise shatters, unmasking {canon_name} ({entry.get('subtitle', form_label)})!"
            ),
        }

    tether_profile = entry.get("tether_profile")
    tether_state = None
    if isinstance(tether_profile, dict) and tether_profile.get("vessel_name"):
        tether_state = {
            "has_tether": True,
            "vessel_name": str(tether_profile["vessel_name"]),
            "sever_stat": str(tether_profile.get("sever_stat") or "INT"),
            "tether_hint": str(tether_profile.get("tether_hint") or ""),
            "reformed_once": False,
            "sealed": False,
        }

    from mechanics.world.folklore_mechanics import deduce_anomaly_category_tag
    category_tag = deduce_anomaly_category_tag(anom_type, sapience, physicality, prim_elem)

    blueprint_id = f"FCX-{hashlib.md5(cid.encode('utf-8')).hexdigest()[:8].upper()}"

    return {
        "blueprint_id": blueprint_id,
        "codex_id": cid,
        "is_canonical_folklore": True,
        "uniqueness": str(entry.get("uniqueness") or "species"),
        "cooldown_days": int(entry.get("cooldown_days", 4) or 4),
        "min_tier": int(entry.get("min_tier", 1) or 1),
        "max_tier": int(entry.get("max_tier", 5) or 5),
        "canonical_name": canon_name,
        "subtitle": str(entry.get("subtitle") or ""),
        "name": canon_name,
        "entity_name": canon_name,
        "type": anom_type,
        "form": anom_form,
        "form_label": form_label,
        "physicality": physicality,
        "disposition": disposition,
        "temperament": nh_temp or ("volatile" if disposition == "hostile" else "timid"),
        "non_hostile_temperament": nh_temp,
        "sapience": sapience,
        "element": prim_elem,
        "primary_element": prim_elem,
        "offensive_element": off_elem,
        "resistances": resistances,
        "immunities": immunities,
        "weaknesses": weaknesses,
        "motif_id": cid,
        "tradition_key": str(entry.get("tradition_key") or "global"),
        "folklore_tradition": str(entry.get("tradition") or "Global Folklore"),
        "appearance": appearance,
        "lore_summary": str(entry.get("lore_summary") or ""),
        "sensory_omen": sensory_omen,
        "description": f"{canon_name} ({entry.get('subtitle', form_label)}) — {entry.get('tradition', 'Folklore')}. {appearance}".strip(),
        "preferred_stat": (taboo_dict.get("exploit_stats") or ["INT"])[0],
        "containment_note": protocol,
        "taboo": taboo_dict,
        "taboo_id": taboo_dict["taboo_id"],
        "taboo_name": taboo_dict["name"],
        "taboo_rule": taboo_rule,
        "containment_protocol": protocol,
        "exploit_stats": list(taboo_dict["exploit_stats"]),
        "violate_stats": list(taboo_dict["violate_stats"]),
        "violate_elements": list(taboo_dict["violate_elements"]),
        "exploit_keywords": list(taboo_dict["exploit_keywords"]),
        "clue_hint": taboo_dict["clue_hint"],
        "backlash_note": taboo_dict["backlash_note"],
        "combat_profile": dict(entry.get("combat_profile") or {}),
        "relic_gear_profile": dict(entry["relic_gear_profile"]) if isinstance(entry.get("relic_gear_profile"), dict) else None,
        "disguise_state": disguise_state,
        "tether_state": tether_state,
        "dialogue_trap": dict(entry["dialogue_trap"]) if isinstance(entry.get("dialogue_trap"), dict) else None,
        "omen_paradox": dict(entry["omen_paradox"]) if isinstance(entry.get("omen_paradox"), dict) else None,
        "appeasement_tags": list(entry.get("appeasement_tags") or []),
        "category_tag": category_tag,
        "biome": biome,
        "time_bucket": t_bucket,
        "biome_weighted": biome in (entry.get("biomes") or []),
        "tier_rank": int(tier_rank or 3),
        "tier": int(tier_rank or 3),
        "dossier_revealed": False,
        "variant_tags": [t for t, flag in (("gore", is_gore), ("furry", is_furry)) if flag],
    }


def build_encyclopedia_payload(
    session_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Builds the complete progressive Folklore Encyclopedia & Session Field Log payload
    shared across Web (`GET /api/codex/encyclopedia`) and Discord (`/encyclopedia`).
    """
    sess = db.get_session(int(session_id)) if session_id else {}
    sess = sess or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions").lower()
    is_furry = "furry" in scen_key
    is_gore = "gore" in scen_key

    eff_uid = int(user_id or sess.get("host_user_id") or 0)
    settings = db.get_settings(eff_uid) if eff_uid > 0 else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))

    user_unlocks: Dict[str, Dict[str, Any]] = {}
    if session_id:
        for uid in db.get_session_participant_user_ids(int(session_id), extra_user_id=eff_uid):
            for cid, row in db.get_user_folklore_codex(uid).items():
                prev = user_unlocks.get(cid)
                rank_map = {"sighted": 1, "verified": 2, "contained": 3}
                if not prev or rank_map.get(str(row.get("unlock_stage")), 0) > rank_map.get(str(prev.get("unlock_stage")), 0):
                    user_unlocks[cid] = row
    elif eff_uid > 0:
        user_unlocks = db.get_user_folklore_codex(eff_uid)

    pools = load_procedural_pools()
    taboos_by_id = {t["taboo_id"]: t for t in (pools.get("taboo_rules_catalog") or [])}
    all_entries = get_folklore_codex_entries()
    traditions = get_folklore_traditions()

    codex_cards: List[Dict[str, Any]] = []
    discovered_count = 0
    verified_count = 0
    contained_count = 0

    for entry in all_entries:
        cid = str(entry["codex_id"])
        u_row = user_unlocks.get(cid)
        stage = "contained" if debug_reveal_all and not u_row else str((u_row or {}).get("unlock_stage") or "undiscovered")
        if debug_reveal_all and stage in ("undiscovered", "sighted"):
            stage = "verified"

        if stage != "undiscovered":
            discovered_count += 1
        if stage in ("verified", "contained"):
            verified_count += 1
        if stage == "contained":
            contained_count += 1

        if stage == "undiscovered":
            codex_cards.append({
                "codex_id": cid,
                "unlock_stage": "undiscovered",
                "is_discovered": False,
                "name": "???",
                "canonical_name": "???",
                "subtitle": "Unencountered Folklore Record",
                "tradition_key": entry["tradition_key"],
                "tradition": entry["tradition"],
                "tradition_label": entry["tradition"],
                "type": entry["type"],
                "form_label": "???",
                "min_tier": entry.get("min_tier", 1),
                "max_tier": entry.get("max_tier", 5),
                "biomes": list(entry.get("biomes") or []),
                "times": list(entry.get("times") or []),
                "hint": f"Rumored in {', '.join(entry.get('biomes') or ['urban'])} sectors ({', '.join(entry.get('times') or ['night'])}).",
            })
            continue

        appearance = (
            str(entry.get("furry_appearance_override") or entry.get("appearance") or "")
            if (is_furry and entry.get("type") == "entity")
            else str(entry.get("appearance") or "")
        )
        omen = (
            str(entry.get("gore_omen_override") or entry.get("sensory_omen") or "")
            if is_gore
            else str(entry.get("sensory_omen") or "")
        )
        base_taboo = format_taboo_entry_for_type(
            taboos_by_id.get(entry["taboo_id"], {}),
            str(entry.get("type") or "entity"),
        )
        t_rule = format_taboo_entry_for_type(
            {"taboo_rule": str(entry.get("custom_taboo_rule") or base_taboo.get("taboo_rule") or "")},
            str(entry.get("type") or "entity"),
        )["taboo_rule"]
        t_proto = format_taboo_entry_for_type(
            {"containment_protocol": str(entry.get("custom_protocol") or base_taboo.get("containment_protocol") or "")},
            str(entry.get("type") or "entity"),
        )["containment_protocol"]

        is_ver = stage in ("verified", "contained")
        t_sighted = int((u_row or {}).get("times_sighted") or 1)
        t_contained = int((u_row or {}).get("times_contained") or (1 if stage == "contained" else 0))
        omen_rule_str = (entry.get("omen_paradox") or {}).get("rule_summary", "") if is_ver else ""
        relic_prof = entry.get("relic_gear_profile") if isinstance(entry.get("relic_gear_profile"), dict) else {}
        card = {
            "codex_id": cid,
            "unlock_stage": stage,
            "is_discovered": True,
            "is_verified": is_ver,
            "is_contained": stage == "contained",
            "folklore_recognition_active": is_ver,
            "times_sighted": t_sighted,
            "sightings_count": t_sighted,
            "times_contained": t_contained,
            "contained_count": t_contained,
            "name": entry["canonical_name"],
            "canonical_name": entry["canonical_name"],
            "subtitle": entry["subtitle"],
            "tradition_key": entry["tradition_key"],
            "tradition": entry["tradition"],
            "tradition_label": entry["tradition"],
            "uniqueness": entry.get("uniqueness", "species"),
            "type": entry["type"],
            "form": entry["form"],
            "form_label": entry["form_label"],
            "disposition": entry["disposition"],
            "temperament": entry.get("non_hostile_temperament", ""),
            "non_hostile_temperament": entry.get("non_hostile_temperament", ""),
            "min_tier": entry.get("min_tier", 1),
            "max_tier": entry.get("max_tier", 5),
            "biomes": list(entry.get("biomes") or []),
            "times": list(entry.get("times") or []),
            "appearance": appearance,
            "sensory_omen": omen,
            "lore_summary": entry["lore_summary"] if is_ver else "[UNVERIFIED — Complete Stage 1 Investigation or Scan to unlock full Folklore Archive]",
            "physicality": entry["physicality"] if is_ver else "unknown",
            "sapience": entry["sapience"] if is_ver else "unknown",
            "primary_element": entry["primary_element"] if is_ver else "unknown",
            "weaknesses": list(entry.get("weaknesses") or []) if is_ver else [],
            "resistances": list(entry.get("resistances") or []) if is_ver else [],
            "immunities": list(entry.get("immunities") or []) if is_ver else [],
            "combat_archetype": (entry.get("combat_profile") or {}).get("archetype", "Stalker") if is_ver else "???",
            "taboo_name": base_taboo.get("name", "Folklore Taboo") if is_ver else "[UNVERIFIED]",
            "taboo_rule": t_rule if is_ver else "[UNVERIFIED]",
            "containment_protocol": t_proto if is_ver else "[UNVERIFIED]",
            "appeasement_tags": list(entry.get("appeasement_tags") or []) if is_ver else [],
            "has_disguise": bool(entry.get("disguise_profile")) if is_ver else False,
            "disguise_alias": (entry.get("disguise_profile") or {}).get("disguise_alias", "") if is_ver else "",
            "has_tether": bool(entry.get("tether_profile")) if is_ver else False,
            "tether_vessel": (entry.get("tether_profile") or {}).get("vessel_name", "") if is_ver else "",
            "has_dialogue_trap": bool(entry.get("dialogue_trap")) if is_ver else False,
            "has_omen_paradox": bool(entry.get("omen_paradox")) if is_ver else False,
            "omen_paradox_summary": omen_rule_str if is_ver else "",
            "omen_paradox_rule": omen_rule_str if is_ver else "",
            "relic_gear_name": str(relic_prof.get("display_name") or relic_prof.get("name") or "") if is_ver else "",
        }
        codex_cards.append(card)

    enriched_traditions: List[Dict[str, Any]] = []
    for tr in traditions:
        t_key = str(tr.get("key") or "")
        t_cards = [c for c in codex_cards if c.get("tradition_key") == t_key]
        enriched_traditions.append({
            **tr,
            "total": len(t_cards),
            "discovered": sum(1 for c in t_cards if c.get("unlock_stage") != "undiscovered"),
            "contained": sum(1 for c in t_cards if c.get("unlock_stage") == "contained"),
        })

    field_log: List[Dict[str, Any]] = []
    for fl_row in reversed(list(sess.get("anomaly_field_log") or [])):
        if not isinstance(fl_row, dict):
            continue
        if fl_row.get("is_disguised") and not debug_reveal_all:
            # Disguised sightings must not leak their canonical identity (searchable codex_id / true name / taboo)
            fl_row = {
                k: v for k, v in fl_row.items()
                if k not in ("codex_id", "true_name", "canonical_name", "form", "form_label", "tradition",
                             "taboo_rule", "containment_protocol", "weaknesses")
            }
            fl_row["codex_id"] = ""
            fl_row["name"] = str(fl_row.get("public_name") or fl_row.get("name") or "Uncanny Presence")
        field_log.append(fl_row)
    vault_log = list(reversed(list(sess.get("contained_anomalies_log") or sess.get("anomalous_vault_log") or [])))
    requisitions = list(sess.get("anomalous_vault_requisitions") or [])

    return {
        "scenario": scen_key,
        "total_folklore_count": len(all_entries),
        "discovered_count": discovered_count,
        "verified_count": verified_count,
        "contained_count": contained_count,
        "traditions": enriched_traditions,
        "folklore_codex": codex_cards,
        "field_log": field_log,
        "vault_log": vault_log,
        "vault_requisitions": requisitions,
    }
