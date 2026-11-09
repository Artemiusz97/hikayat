from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

import namegen
import scenario_data
from mechanics.narrative.blueprints import (
    ensure_world_ending_anomaly_blueprint,
    generate_anomalous_campaign_blueprint,
)
from mechanics.narrative.quest_engines import (
    get_scenario_bible_bucket,
    load_campaign_storylets_catalog,
    normalize_quest_locale,
    resolve_quest_engine,
)

UNIVERSAL_MAX_CHAPTERS = 11
PEAK_CHAPTERS: Tuple[int, ...] = (3, 6, 8, 9, 10)

_UNIVERSAL_CHAPTER_ENGINES: Dict[int, Tuple[str, str]] = {
    1: ("MYSTERY_CASE", "prologue"),
    2: ("ACQUISITION_EXCHANGE", "wave_1_buildup"),
    3: ("CRISIS_DEFENSE", "peak_1_stepping_stone"),
    4: ("HEIST_BREACH", "wave_2_buildup"),
    5: ("SOCIAL_BROKERAGE", "wave_2_complication"),
    6: ("MYSTERY_CASE", "peak_2_midpoint_twist"),
    7: ("HUNT_CONTAINMENT", "wave_3_buildup"),
    8: ("RIVALRY_SHOWDOWN", "peak_3_escalation"),
    9: ("CRISIS_DEFENSE", "pre_climax_darkest_hour"),
    10: ("HUNT_CONTAINMENT", "grand_climax"),
    11: ("SOCIAL_BROKERAGE", "playable_epilogue"),
}

_TAPESTRY_SLIDE_HEADERS: Dict[str, Dict[str, str]] = {
    "world": {"en": "The World Remade", "pl": "Przeobrażony Świat", "ms": "Dunia Yang Berubah", "zh": "世界新貌", "de": "Die Verwandelte Welt"},
    "factions": {"en": "Balance of Power", "pl": "Układ Sił", "ms": "Imbangan Kuasa", "zh": "派系格局", "de": "Machtgefüge"},
    "bonds": {"en": "Living Bonds & Scars", "pl": "Więzi i Blizny", "ms": "Ikatan & Parut", "zh": "羁绊与铭痕", "de": "Bande & Narben"},
    "title": {"en": "Earned Chronicle Title", "pl": "Zdobyty Tytuł Kroniki", "ms": "Gelaran Hikayat", "zh": "史诗称号", "de": "Chronik-Ehrentitel"},
}


def _seed_int(seed_str: str) -> int:
    return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)


def _loc_text(val: Any, loc: str, fallback: str = "") -> str:
    if isinstance(val, dict):
        return str(val.get(loc) or val.get("en") or fallback)
    if isinstance(val, str) and val:
        return val
    return fallback


def _format_chapter_heading(ch_idx: int, subtitle: str, loc: str) -> str:
    ch_prefix = {"en": "Chapter", "pl": "Rozdział", "ms": "Bab", "zh": "第", "de": "Kapitel"}.get(loc, "Chapter")
    if loc == "zh":
        return f"第{ch_idx}章：{subtitle}"
    return f"{ch_prefix} #{ch_idx}: {subtitle}"


def _default_ending_axes() -> Dict[str, Any]:
    return {
        "allegiance": "independent",  # independent | order | reform | shadow | usurper
        "faction_tallies": {"order": 0, "reform": 0, "shadow": 0},
        "collateral_toll": 0,
        "truth_stance": "pending",  # pending | exposed | buried | weaponized
        "usurper_pivots": 0,
        "golden_locked_out": False,
        "inner_circle_losses": [],
        "lieutenants_recruited": [],
        "double_crosses": 0,
        "resolved_ending": "",
    }


def _roll_hidden_campaign_bible(
    session_id: int,
    scen_key: str,
    mastermind_name: str,
    lieutenants: List[Dict[str, Any]],
    anomaly: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    catalog = load_campaign_storylets_catalog()
    bucket_key = get_scenario_bible_bucket(scen_key)
    pool = (catalog.get("bible_pools") or {}).get(bucket_key) or (catalog.get("bible_pools") or {}).get("fantasy_mythic") or {}

    crises = list(pool.get("crises") or [])
    ch3_threats = list(pool.get("ch3_threats") or [])
    ch6_twists = list(pool.get("ch6_twists") or [])
    tri_cfg = dict(pool.get("faction_triangles") or {})

    picked_crisis = dict(crises[_seed_int(f"bible_crisis:{session_id}:{scen_key}") % len(crises)]) if crises else {}
    picked_ch3 = dict(ch3_threats[_seed_int(f"bible_ch3:{session_id}:{scen_key}") % len(ch3_threats)]) if ch3_threats else {}
    picked_ch6 = dict(ch6_twists[_seed_int(f"bible_ch6:{session_id}:{scen_key}") % len(ch6_twists)]) if ch6_twists else {}

    if isinstance(anomaly, dict) and anomaly.get("name"):
        picked_crisis = {
            "id": str(picked_crisis.get("id") or "non_euclidean_convergence"),
            "archetype": "eldritch_cataclysm",
            "title": dict(picked_crisis.get("title") or {"en": anomaly.get("title", "Sovereign of the Folded Horizon")}),
            "goal": dict(picked_crisis.get("goal") or {"en": anomaly.get("cult_goal", "awaken the World-Ending Anomaly")}),
            "omen": dict(picked_crisis.get("omen") or {"en": anomaly.get("foreshadow_sign") or "geometric distortions and bleeding static"}),
        }
        picked_crisis["title"]["en"] = str(anomaly.get("title") or picked_crisis["title"].get("en") or "Sovereign of the Folded Horizon")
        picked_crisis["goal"]["en"] = str(anomaly.get("cult_goal") or picked_crisis["goal"].get("en") or "awaken the World-Ending Anomaly")
        picked_crisis["omen"]["en"] = str(anomaly.get("foreshadow_sign") or picked_crisis["omen"].get("en") or "geometric distortions")

    hook_info: Dict[str, Any] = {}
    try:
        raw_hook = scenario_data.get_dynamic_starting_hook(scen_key, session_id=int(session_id or 1))
        if isinstance(raw_hook, dict):
            hook_info = {
                "archetype": str(raw_hook.get("archetype") or "hub_launchpad"),
                "suggested_location": str(raw_hook.get("suggested_location") or ""),
                "focal_point": str(raw_hook.get("focal_point") or ""),
            }
    except Exception:
        hook_info = {}

    lt_lead = lieutenants[0]["name"] if lieutenants else "the Vanguard Envoy"
    return {
        "bible_id": f"bible_{int(session_id or 0)}_{bucket_key}",
        "bucket": bucket_key,
        "mastermind_name": mastermind_name,
        "crisis": picked_crisis,
        "ch3_threat": picked_ch3,
        "ch6_twist": picked_ch6,
        "ch6_featured_lt": lt_lead,
        "faction_triangle": tri_cfg,
        "hook_binding": hook_info,
    }


def _build_universal_chapters_blueprint(
    session_id: int,
    scen_key: str,
    mastermind: Dict[str, Any],
    lieutenants: List[Dict[str, Any]],
    hidden_bible: Dict[str, Any],
    is_non_combat: bool,
    lang: str = "en",
) -> Dict[str, Any]:
    storylets_cat = load_campaign_storylets_catalog()
    rhythm_map = storylets_cat.get("chapter_rhythm") or {}
    loc = normalize_quest_locale(lang)

    lt_lead = lieutenants[0]["name"] if lieutenants else "the Vanguard Envoy"
    lt_second = lieutenants[1]["name"] if len(lieutenants) > 1 else lt_lead

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        anom_bp = generate_anomalous_campaign_blueprint(session_id)
        out: Dict[str, Any] = {}
        for ch_num, ch_data in (anom_bp.get("chapters") or {}).items():
            c_idx = int(ch_num)
            r_meta = rhythm_map.get(str(c_idx)) or {}
            eng_info = resolve_quest_engine(ch_data.get("archetype", ""), "")
            is_peak = bool(c_idx in PEAK_CHAPTERS)
            base_title = str(ch_data.get("title_template", f"Chapter #{c_idx}"))
            if loc != "en":
                st_block = (storylets_cat.get("storylets") or {}).get(
                    "prologue" if c_idx == 1 else (f"peak_ch{c_idx}" if is_peak else ("epilogue_ch11" if c_idx == 11 else "buildup_standard"))
                ) or {}
                if c_idx == 11:
                    st_block = st_block.get("golden_restoration") or {}
                sub_raw = _loc_text(st_block.get("subtitle"), loc, base_title)
                ch3_lbl = _loc_text((hidden_bible.get("ch3_threat") or {}).get("label"), loc, "Spatial Fold")
                base_title = _format_chapter_heading(
                    c_idx,
                    sub_raw.format(
                        zone="Metropolitan Grid",
                        threat=ch3_lbl,
                        lieutenant=lt_lead if c_idx <= 6 else lt_second,
                        mastermind=mastermind.get("name", "The Convergence"),
                    ),
                    loc,
                )
            out[str(c_idx)] = {
                "chapter": c_idx,
                "phase": str(r_meta.get("phase") or ch_data.get("phase", "rising_action")),
                "is_peak": is_peak,
                "main_stages": 3 if is_peak else 2,
                "optional_min": int(r_meta.get("optional_min") or (2 if is_peak else 1)),
                "optional_max": int(r_meta.get("optional_max") or (2 if c_idx == 11 else 3)),
                "engine": "SOCIAL_BROKERAGE" if c_idx == 11 else eng_info["engine"],
                "title_template": base_title,
                "archetype": ch_data.get("archetype", ""),
                "sub_archetypes": list(ch_data.get("sub_archetypes") or []),
                "pacing_directive": ch_data.get("pacing_directive", ""),
                "featured_lieutenant": lt_lead if c_idx <= 6 else (lt_second if c_idx <= 9 else ""),
                "has_final_bossfight": bool(c_idx == 10 and not is_non_combat),
                "is_playable_epilogue": bool(c_idx == 11),
            }
        return out

    m_name = mastermind.get("name", "The Hidden Architect")
    m_title = _loc_text((hidden_bible.get("crisis") or {}).get("title"), loc, mastermind.get("title", "Shadow Sovereign"))
    m_goal = _loc_text((hidden_bible.get("crisis") or {}).get("goal"), loc, mastermind.get("goal", "reshape the realm"))
    omen = _loc_text((hidden_bible.get("crisis") or {}).get("omen"), loc, mastermind.get("omen", "unsettling signs across the district"))
    ch3_threat = hidden_bible.get("ch3_threat") or {}
    ch3_label = _loc_text(ch3_threat.get("label"), loc, "Escalating Vanguard Crisis")
    ch6_twist = hidden_bible.get("ch6_twist") or {}
    ch6_summary = _loc_text(ch6_twist.get("summary"), loc, "{mastermind}'s true leverage surfaces.").format(
        mastermind=m_name,
        lieutenant=lt_lead,
    )

    storylets = storylets_cat.get("storylets") or {}
    chapters: Dict[str, Any] = {}
    for ch_idx in range(1, UNIVERSAL_MAX_CHAPTERS + 1):
        r_meta = rhythm_map.get(str(ch_idx)) or {}
        eng, phase = _UNIVERSAL_CHAPTER_ENGINES[ch_idx]
        if ch_idx == 3 and ch3_threat.get("engine"):
            eng = str(ch3_threat["engine"])
        if is_non_combat and eng == "HUNT_CONTAINMENT":
            eng = "RIVALRY_SHOWDOWN" if ch_idx == 10 else "MYSTERY_CASE"

        is_peak = bool(ch_idx in PEAK_CHAPTERS)
        feat_lt = lt_lead if ch_idx <= 6 else (lt_second if ch_idx <= 9 else "")

        if ch_idx == 1:
            st_key = "prologue"
        elif ch_idx in PEAK_CHAPTERS:
            st_key = f"peak_ch{ch_idx}"
        elif ch_idx == 11:
            st_key = "epilogue_ch11"
        else:
            st_key = "buildup_standard"

        st_cfg = storylets.get(st_key) or {}
        if ch_idx == 11:
            st_cfg = st_cfg.get("golden_restoration") or {}

        default_zone_lbl = {"en": "the Realm", "pl": "Sektor", "ms": "Wilayah", "zh": "核心辖区", "de": "der Sektor"}.get(loc, "the Realm")
        default_venue_lbl = {"en": "the Central Hub", "pl": "Centrum", "ms": "Nadi Utama", "zh": "中枢据点", "de": "das Zentrum"}.get(loc, "the Central Hub")
        raw_sub = _loc_text(st_cfg.get("subtitle"), loc, f"Threads of {m_title}")
        subtitle = raw_sub.format(
            zone=default_zone_lbl,
            threat=ch3_label,
            lieutenant=feat_lt or lt_lead,
            mastermind=m_name,
        )
        raw_obj = _loc_text(st_cfg.get("objective"), loc, f"Counter {m_name}'s operation ({omen}).")
        directive = raw_obj.format(
            venue=default_venue_lbl,
            zone=default_zone_lbl,
            mastermind=m_name,
            mastermind_title=m_title,
            goal=m_goal,
            omen=omen,
            lieutenant=feat_lt or lt_lead,
            threat=ch3_label,
            twist_summary=ch6_summary,
        )

        chapters[str(ch_idx)] = {
            "chapter": ch_idx,
            "phase": str(r_meta.get("phase") or phase),
            "is_peak": is_peak,
            "main_stages": 3 if is_peak else 2,
            "optional_min": int(r_meta.get("optional_min") or (2 if is_peak else 1)),
            "optional_max": int(r_meta.get("optional_max") or (2 if ch_idx == 11 else 3)),
            "engine": eng,
            "storylet_id": st_key,
            "title_template": _format_chapter_heading(ch_idx, subtitle, loc),
            "archetype": eng.replace("_", " ").title(),
            "pacing_directive": directive,
            "featured_lieutenant": feat_lt,
            "has_final_bossfight": bool(ch_idx == 10 and not is_non_combat),
            "is_playable_epilogue": bool(ch_idx == 11),
        }
    return chapters


def compile_or_get_campaign_spine(
    session_id: int,
    scen_key: str = "",
    lang: str = "en",
    force_recompile: bool = False,
) -> Dict[str, Any]:
    """
    Deterministically compiles (at `t = 0`) or fetches the session's 11-chapter Triple-Peak `CampaignSpine`
    across ALL 21 scenarios, including Turn-0 `hidden_bible`, `ending_axes`, and recurring Lieutenants.
    """
    import db

    if not force_recompile and session_id:
        existing = db.get_campaign_spine(session_id)
        if existing and existing.get("chapters_blueprint"):
            # Backfill Turn-0 hidden_bible / ending_axes on pre-v51 spines transparently
            if not existing.get("hidden_bible") or not existing.get("ending_axes"):
                sess_tmp = db.get_session(session_id) or {}
                eff_s = str(existing.get("scenario") or scen_key or sess_tmp.get("scenario") or "fantasy")
                mm = dict(existing.get("mastermind_profile") or {})
                lts = list(existing.get("lieutenants_roster") or [])
                anom_ex = ensure_world_ending_anomaly_blueprint(session_id, session=sess_tmp) if scenario_data.is_anomalous_incursions_scenario(eff_s) else None
                hb = existing.get("hidden_bible") or _roll_hidden_campaign_bible(
                    session_id, eff_s, str(mm.get("name") or "The Hidden Architect"), lts, anomaly=anom_ex
                )
                ea = existing.get("ending_axes") or _default_ending_axes()
                patched = db.upsert_campaign_spine(session_id, eff_s, hidden_bible=hb, ending_axes=ea)
                if patched:
                    return patched
            return existing

    sess = db.get_session(session_id) if session_id else {}
    sess = sess or {}
    eff_scen = str(scen_key or sess.get("scenario") or "fantasy")
    eff_lang = normalize_quest_locale(lang or sess.get("narration_language") or sess.get("language") or "en")
    is_non_combat = bool(scenario_data.is_non_combat_scenario(eff_scen))

    lieutenants: List[Dict[str, Any]] = []
    lt_roles = ("Enforcer", "Spymaster", "Quartermaster")
    for idx, role_lbl in enumerate(lt_roles):
        g_str = "female" if ((idx + int(session_id or 1)) % 2 == 1) else "male"
        try:
            lt_name = namegen.generate_npc_name(scen_key=eff_scen, gender=g_str)
        except Exception:
            lt_name = f"Envoy {idx + 1}"
        lieutenants.append(
            {
                "key": f"lt_{session_id}_{idx + 1}",
                "name": lt_name,
                "role": role_lbl,
                "gender": g_str,
                "status": "active",  # active | dead | recruited | promoted_successor
                "contact_id": None,
            }
        )

    anomaly: Optional[Dict[str, Any]] = None
    if scenario_data.is_anomalous_incursions_scenario(eff_scen):
        anomaly = ensure_world_ending_anomaly_blueprint(session_id, session=sess)
        mm_name = str(anomaly.get("name") or "The Non-Euclidean Convergence")
    else:
        try:
            mm_name = namegen.generate_npc_name(
                scen_key=eff_scen,
                gender="male" if (_seed_int(f"g:{session_id}") % 2 == 0) else "female",
            )
        except Exception:
            mm_name = "Sovereign Vane"

    hidden_bible = _roll_hidden_campaign_bible(
        session_id=session_id,
        scen_key=eff_scen,
        mastermind_name=mm_name,
        lieutenants=lieutenants,
        anomaly=anomaly,
    )
    crisis_cfg = hidden_bible.get("crisis") or {}

    if anomaly is not None:
        mastermind = {
            "name": mm_name,
            "title": anomaly.get("title", "Sovereign of the Folded Horizon"),
            "archetype": "eldritch_cataclysm",
            "goal": anomaly.get("cult_goal", "awaken the World-Ending Anomaly across the metropolitan grid"),
            "omen": anomaly.get("foreshadow_sign") or "geometric distortions and bleeding static",
            "escalation_tier": 0,
            "is_non_combat": False,
        }
    else:
        mastermind = {
            "name": mm_name,
            "title": _loc_text(crisis_cfg.get("title"), eff_lang, "Shadow Sovereign"),
            "archetype": str(crisis_cfg.get("archetype") or "cabal_warlord"),
            "goal": _loc_text(crisis_cfg.get("goal"), eff_lang, "reshape the realm"),
            "omen": _loc_text(crisis_cfg.get("omen"), eff_lang, "unsettling signs across the district"),
            "escalation_tier": 0,
            "is_non_combat": is_non_combat,
        }

    chapters = _build_universal_chapters_blueprint(
        session_id=session_id,
        scen_key=eff_scen,
        mastermind=mastermind,
        lieutenants=lieutenants,
        hidden_bible=hidden_bible,
        is_non_combat=is_non_combat,
        lang=eff_lang,
    )
    ending_axes = _default_ending_axes()

    if session_id:
        saved = db.upsert_campaign_spine(
            session_id,
            eff_scen,
            mastermind_profile=mastermind,
            lieutenants_roster=lieutenants,
            chapters_blueprint=chapters,
            nemeses=[],
            hidden_bible=hidden_bible,
            ending_axes=ending_axes,
            chronicle_tapestry={},
            climax_status="pending",
            epilogue_status="pending",
            state_events=[],
        )
        if saved:
            return saved
    return {
        "session_id": session_id,
        "scenario": eff_scen,
        "mastermind_profile": mastermind,
        "lieutenants_roster": lieutenants,
        "chapters_blueprint": chapters,
        "nemeses": [],
        "hidden_bible": hidden_bible,
        "ending_axes": ending_axes,
        "chronicle_tapestry": {},
        "climax_status": "pending",
        "epilogue_status": "pending",
    }


def select_chapter_storylet(
    session_id: int,
    chapter_num: int,
    spine: Optional[Dict[str, Any]] = None,
    venue_name: str = "",
    lang: str = "en",
) -> Dict[str, Any]:
    """
    State-filtered Storylet selector (`<5ms` deterministic):
    Adapts the chapter's title, objective, engine, `main_stages` (`2` vs `3`), and optional bounds
    to accumulated `WorldScars`, recruited/slain Lieutenants, `Ch. 6` twists, and `Ch. 11` ending archetype.
    """
    import db

    eff_spine = spine or compile_or_get_campaign_spine(session_id, lang=lang)
    eff_scen = str(eff_spine.get("scenario") or "fantasy")
    loc = normalize_quest_locale(lang)
    is_non_combat = bool(scenario_data.is_non_combat_scenario(eff_scen))

    ch_idx = max(1, min(UNIVERSAL_MAX_CHAPTERS, int(chapter_num or 1)))
    chapters_bp = eff_spine.get("chapters_blueprint") or {}
    ch_bp = dict(chapters_bp.get(str(ch_idx)) or {})
    hb = eff_spine.get("hidden_bible") or {}
    mm = eff_spine.get("mastermind_profile") or {}
    lts = list(eff_spine.get("lieutenants_roster") or [])
    active_lts = [lt for lt in lts if lt.get("status") == "active"]
    recruited_lts = [lt for lt in lts if lt.get("status") == "recruited"]

    storylets_cat = load_campaign_storylets_catalog()
    rhythm = (storylets_cat.get("chapter_rhythm") or {}).get(str(ch_idx)) or {}
    storylets = storylets_cat.get("storylets") or {}

    hook_loc = str((hb.get("hook_binding") or {}).get("suggested_location") or "")
    eff_venue = str(venue_name or (hook_loc if ch_idx == 1 else "") or "Central District").strip()
    eff_zone = eff_venue.split("➔")[0].strip() if "➔" in eff_venue else eff_venue

    active_scars = 0
    if session_id:
        try:
            evs = db.get_world_events(session_id, include_hidden=True, statuses=("active",)) or []
            active_scars = sum(1 for ev in evs if bool((ev.get("metadata") or {}).get("is_world_scar")))
        except Exception:
            active_scars = 0

    feat_lt = (
        active_lts[0]["name"]
        if (ch_idx <= 6 and active_lts)
        else (active_lts[min(1, len(active_lts) - 1)]["name"] if active_lts else "the Inner Envoy")
    )
    m_name = str(mm.get("name") or "The Hidden Architect")
    crisis_cfg = hb.get("crisis") or {}
    m_title = _loc_text(crisis_cfg.get("title"), loc, str(mm.get("title") or "Shadow Sovereign"))
    m_goal = _loc_text(crisis_cfg.get("goal"), loc, str(mm.get("goal") or "reshape the realm"))
    omen = _loc_text(crisis_cfg.get("omen"), loc, str(mm.get("omen") or "ominous signs"))
    ch3_threat = hb.get("ch3_threat") or {}
    ch3_label = _loc_text(ch3_threat.get("label"), loc, "Vanguard Crisis")
    ch6_twist = hb.get("ch6_twist") or {}
    ch6_summary = _loc_text(ch6_twist.get("summary"), loc, f"{m_name}'s hidden design comes to light.").format(
        mastermind=m_name,
        lieutenant=feat_lt,
    )

    is_peak = bool(ch_idx in PEAK_CHAPTERS)
    ending_key = ""
    if ch_idx == 1:
        storylet_id = "prologue"
        st_cfg = storylets.get("prologue") or {}
    elif ch_idx in PEAK_CHAPTERS:
        storylet_id = f"peak_ch{ch_idx}"
        st_cfg = storylets.get(storylet_id) or {}
    elif ch_idx == 11:
        ch10_failed = str(eff_spine.get("climax_status") or "").lower() == "fallen_world"
        ending_key = resolve_campaign_ending_archetype(session_id, ch10_failed=ch10_failed, spine=eff_spine)
        storylet_id = f"epilogue_ch11.{ending_key}"
        st_cfg = ((storylets.get("epilogue_ch11") or {}).get(ending_key)) or ((storylets.get("epilogue_ch11") or {}).get("golden_restoration")) or {}
    else:
        if recruited_lts and ch_idx in (4, 7):
            storylet_id = "buildup_lt_recruited"
        elif active_scars >= 1:
            storylet_id = "buildup_high_scars"
        else:
            storylet_id = "buildup_standard"
        st_cfg = storylets.get(storylet_id) or storylets.get("buildup_standard") or {}

    slots = {
        "venue": eff_venue,
        "zone": eff_zone,
        "mastermind": m_name,
        "mastermind_title": m_title,
        "goal": m_goal,
        "omen": omen,
        "lieutenant": feat_lt,
        "threat": ch3_label,
        "twist_summary": ch6_summary,
    }
    subtitle = _loc_text(st_cfg.get("subtitle"), loc, f"Chapter {ch_idx}").format(**slots)
    objective_text = _loc_text(st_cfg.get("objective"), loc, f"Advance against {m_name} at {eff_venue}.").format(**slots)

    # Preserve bespoke English Anomalous chapter title when playing Anomalous Incursions in English (except dynamic Fallen World Ch.11)
    if scenario_data.is_anomalous_incursions_scenario(eff_scen) and loc == "en" and ending_key != "fallen_world" and ch_bp.get("title_template"):
        title_text = str(ch_bp["title_template"])
    else:
        title_text = _format_chapter_heading(ch_idx, subtitle, loc)

    eng = str(ch_bp.get("engine") or rhythm.get("default_engine") or _UNIVERSAL_CHAPTER_ENGINES[ch_idx][0])
    if ch_idx == 3 and ch3_threat.get("engine") and not scenario_data.is_anomalous_incursions_scenario(eff_scen):
        eng = str(ch3_threat["engine"])
    if ch_idx == 11 and ending_key == "fallen_world" and not is_non_combat:
        eng = "CRISIS_DEFENSE"
    if is_non_combat and eng == "HUNT_CONTAINMENT":
        eng = "RIVALRY_SHOWDOWN" if ch_idx == 10 else "MYSTERY_CASE"

    return {
        "chapter": ch_idx,
        "storylet_id": storylet_id,
        "phase": str(rhythm.get("phase") or ch_bp.get("phase") or "rising_action"),
        "is_peak": is_peak,
        "main_stages": 3 if is_peak else 2,
        "optional_min": int(rhythm.get("optional_min") or (2 if is_peak else 1)),
        "optional_max": int(rhythm.get("optional_max") or (2 if ch_idx == 11 else 3)),
        "engine": eng,
        "title": title_text,
        "subtitle": subtitle,
        "objective": objective_text,
        "featured_lieutenant": feat_lt,
        "preferred_location": eff_venue,
        "ending_archetype": ending_key,
        "pacing_directive": str(ch_bp.get("pacing_directive") or objective_text),
    }


def update_campaign_ending_axes(
    session_id: int,
    turn_number: int = 1,
    faction_pillar: str = "",
    collateral_delta: int = 0,
    truth_stance: str = "",
    usurper_delta: int = 0,
    lock_golden: bool = False,
    inner_circle_loss: str = "",
    recruited_lieutenant: str = "",
    double_cross_delta: int = 0,
    resolved_ending: str = "",
    ch10_defeated: Optional[bool] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Atomically updates `campaign_spines.ending_axes` and appends a turn-stamped rollback delta."""
    import db

    if not session_id:
        return _default_ending_axes()
    spine = compile_or_get_campaign_spine(session_id)
    prev_axes = dict(_default_ending_axes())
    prev_axes.update(dict(spine.get("ending_axes") or {}))
    prev_axes["faction_tallies"] = dict(prev_axes.get("faction_tallies") or {"order": 0, "reform": 0, "shadow": 0})
    prev_axes["inner_circle_losses"] = list(prev_axes.get("inner_circle_losses") or [])
    prev_axes["lieutenants_recruited"] = list(prev_axes.get("lieutenants_recruited") or [])

    import copy

    next_axes = copy.deepcopy(prev_axes)
    pillar_clean = str(faction_pillar or "").strip().lower()
    if pillar_clean in ("order", "reform", "shadow"):
        next_axes["faction_tallies"][pillar_clean] = int(next_axes["faction_tallies"].get(pillar_clean, 0)) + 1
        if next_axes.get("allegiance") != "usurper":
            best_p = max(("order", "reform", "shadow"), key=lambda p: int(next_axes["faction_tallies"].get(p, 0)))
            if int(next_axes["faction_tallies"].get(best_p, 0)) >= 1:
                next_axes["allegiance"] = best_p
    elif pillar_clean == "usurper":
        next_axes["allegiance"] = "usurper"
        next_axes["usurper_pivots"] = int(next_axes.get("usurper_pivots") or 0) + 1
        next_axes["golden_locked_out"] = True

    if collateral_delta:
        next_axes["collateral_toll"] = max(0, int(next_axes.get("collateral_toll") or 0) + int(collateral_delta))
    if truth_stance in ("exposed", "buried", "weaponized"):
        next_axes["truth_stance"] = truth_stance
        if truth_stance in ("buried", "weaponized"):
            next_axes["golden_locked_out"] = True
    if usurper_delta:
        next_axes["usurper_pivots"] = max(0, int(next_axes.get("usurper_pivots") or 0) + int(usurper_delta))
        if next_axes["usurper_pivots"] >= 1:
            next_axes["allegiance"] = "usurper"
            next_axes["golden_locked_out"] = True
    if lock_golden:
        next_axes["golden_locked_out"] = True
    if inner_circle_loss and inner_circle_loss not in next_axes["inner_circle_losses"]:
        next_axes["inner_circle_losses"].append(str(inner_circle_loss))
        next_axes["collateral_toll"] = int(next_axes.get("collateral_toll") or 0) + 2
        next_axes["golden_locked_out"] = True
    if recruited_lieutenant and recruited_lieutenant not in next_axes["lieutenants_recruited"]:
        next_axes["lieutenants_recruited"].append(str(recruited_lieutenant))
    if double_cross_delta:
        next_axes["double_crosses"] = max(0, int(next_axes.get("double_crosses") or 0) + int(double_cross_delta))
    if ch10_defeated:
        next_axes["ch10_defeated"] = True
        next_axes["resolved_ending"] = "fallen_world"
        next_axes["golden_locked_out"] = True
    if resolved_ending:
        next_axes["resolved_ending"] = str(resolved_ending)

    events = list(spine.get("state_events") or [])
    events.append({"turn": int(turn_number), "kind": "ending_axes", "prev": prev_axes, "next": next_axes})
    db.upsert_campaign_spine(
        session_id,
        spine.get("scenario") or "fantasy",
        ending_axes=next_axes,
        state_events=events,
    )
    return next_axes


def resolve_campaign_ending_archetype(
    session_id: int,
    ch10_failed: bool = False,
    spine: Optional[Dict[str, Any]] = None,
) -> str:
    """Deterministically resolves one of the 6 canonical campaign Ending Archetypes."""
    import db

    if isinstance(ch10_failed, dict) and spine is None:
        spine = ch10_failed
        ch10_failed = False

    eff_spine = spine or (compile_or_get_campaign_spine(session_id) if session_id else {})
    if ch10_failed or str(eff_spine.get("climax_status") or "").lower() == "fallen_world":
        return "fallen_world"

    axes = dict(_default_ending_axes())
    axes.update(dict(eff_spine.get("ending_axes") or {}))
    if axes.get("resolved_ending") and axes["resolved_ending"] != "fallen_world":
        return str(axes["resolved_ending"])

    active_scars = 0
    if session_id:
        try:
            evs = db.get_world_events(session_id, include_hidden=True, statuses=("active",)) or []
            active_scars = sum(1 for ev in evs if bool((ev.get("metadata") or {}).get("is_world_scar")))
        except Exception:
            active_scars = 0

    if axes.get("allegiance") == "usurper" or int(axes.get("usurper_pivots") or 0) >= 2:
        return "shadow_usurper"
    if axes.get("truth_stance") == "buried":
        return "buried_truth"
    if (
        int(axes.get("collateral_toll") or 0) >= 3
        or len(axes.get("inner_circle_losses") or []) >= 1
        or active_scars >= 3
    ):
        return "pyrrhic_memorial"

    tallies = axes.get("faction_tallies") or {}
    best_pillar = max(("order", "reform", "shadow"), key=lambda p: int(tallies.get(p, 0)))
    if int(tallies.get(best_pillar, 0)) >= 2 or (axes.get("golden_locked_out") and int(tallies.get(best_pillar, 0)) >= 1):
        return "faction_hegemony"
    if axes.get("golden_locked_out"):
        return "pyrrhic_memorial"
    return "golden_restoration"


def compile_chronicle_tapestry(
    session_id: int,
    lang: str = "en",
    turn_number: int = 1,
) -> Dict[str, Any]:
    """
    Synthesizes the 4-Slide Chronicle Tapestry (`World`, `Factions`, `Bonds`, `Earned Title`)
    upon Chapter 11 completion, persisting it on `campaign_spines` with rollback support.
    """
    import db

    spine = compile_or_get_campaign_spine(session_id, lang=lang)
    loc = normalize_quest_locale(lang)
    ch10_failed = str(spine.get("climax_status") or "").lower() == "fallen_world"
    ending_key = resolve_campaign_ending_archetype(session_id, ch10_failed=ch10_failed, spine=spine)

    storylets_cat = load_campaign_storylets_catalog()
    endings_cfg = storylets_cat.get("endings") or {}
    end_meta = endings_cfg.get(ending_key) or endings_cfg.get("golden_restoration") or {}

    sess = db.get_session(session_id) if session_id else {}
    sess = sess or {}
    cur_loc = str(sess.get("current_location") or "Central District")
    zone_name = cur_loc.split("➔")[0].strip() if "➔" in cur_loc else cur_loc

    hb = spine.get("hidden_bible") or {}
    mm = spine.get("mastermind_profile") or {}
    m_name = str(mm.get("name") or "The Hidden Architect")
    axes = dict(_default_ending_axes())
    axes.update(dict(spine.get("ending_axes") or {}))

    tri = hb.get("faction_triangle") or {}
    tallies = axes.get("faction_tallies") or {}
    best_pillar = max(("order", "reform", "shadow"), key=lambda p: int(tallies.get(p, 0)))
    ally_fac_name = _loc_text((tri.get(best_pillar) or {}).get("name"), loc, "the Ascendant Coalition")

    # Gather real faction standing if present in session
    factions = db.get_factions(session_id) if session_id else []
    if factions:
        def _fac_rep(fac_row: Dict[str, Any]) -> int:
            raw_r = fac_row.get("reputation_score")
            if raw_r is None:
                raw_r = fac_row.get("reputation")
            return int(raw_r or 0)

        top_fac = max(factions, key=_fac_rep)
        if _fac_rep(top_fac) > 0:
            ally_fac_name = str(top_fac.get("name") or ally_fac_name)

    world_text = _loc_text(end_meta.get("world_slide"), loc, f"{zone_name} enters a new era.").format(
        zone=zone_name,
        mastermind=m_name,
        ally_faction=ally_fac_name,
    )

    # Faction slide text (5 locales)
    double_crosses = int(axes.get("double_crosses") or 0)
    fac_templates = {
        "en": f"{ally_fac_name} shapes the post-crisis balance across {zone_name}" + (f", remembering {double_crosses} bold double-cross(es)." if double_crosses else " through hard-won accords."),
        "pl": f"{ally_fac_name} kształtuje nowy układ sił w dzielnicy {zone_name}.",
        "ms": f"{ally_fac_name} mencorakkan imbangan kuasa baharu di {zone_name}.",
        "zh": f"{ally_fac_name}主导了{zone_name}的战后权力格局" + (f"（历经{double_crosses}次惊险反水博弈）。" if double_crosses else "。"),
        "de": f"{ally_fac_name} prägt das neue Machtgefüge in {zone_name}.",
    }
    factions_text = fac_templates.get(loc, fac_templates["en"])

    # Bonds slide text (party companions + high-affinity contacts + fallen inner circle)
    party_names: List[str] = []
    if session_id:
        try:
            party_names = [str(p.get("name")) for p in (db.get_session_party_npcs(session_id) or []) if p.get("name")]
        except Exception:
            party_names = []
        if not party_names:
            try:
                contacts = db.get_contacts(session_id) or []
                top_c = sorted(contacts, key=lambda c: int(c.get("affinity") or 0), reverse=True)[:3]
                party_names = [str(c.get("name")) for c in top_c if c.get("name") and int(c.get("affinity") or 0) >= 15]
            except Exception:
                party_names = []

    losses = list(axes.get("inner_circle_losses") or [])
    companion_str = ", ".join(party_names[:3]) if party_names else (
        {"en": "your trusted allies", "pl": "twoi zaufani sojusznicy", "ms": "sekutu setia anda", "zh": "并肩作战的同伴", "de": "deine vertrauten Gefährten"}.get(loc, "your trusted allies")
    )
    loss_str = ", ".join(losses[:2])
    if loss_str:
        bonds_templates = {
            "en": f"Standing beside {companion_str}, you carry forward the memory of {loss_str}.",
            "pl": f"U boku {companion_str} niesiesz pamięć o osobach: {loss_str}.",
            "ms": f"Di sisi {companion_str}, anda terus mengenang pengorbanan {loss_str}.",
            "zh": f"与{companion_str}并肩而立，你们将{loss_str}的记忆永远铭刻于心。",
            "de": f"An der Seite von {companion_str} bewahrst du das Andenken an {loss_str}.",
        }
    else:
        bonds_templates = {
            "en": f"Your inner circle ({companion_str}) emerges intact, bound by shared trials across every chapter.",
            "pl": f"Twój bliski krąg ({companion_str}) przetrwał próby, złączony wspólną walką.",
            "ms": f"Lingkaran rapat anda ({companion_str}) kekal utuh mengharungi setiap ujian.",
            "zh": f"你的核心挚友（{companion_str}）全员挺过重重试炼，羁绊愈发坚不可摧。",
            "de": f"Dein innerer Kreis ({companion_str}) geht unversehrt und vereint aus allen Prüfungen hervor.",
        }
    bonds_text = bonds_templates.get(loc, bonds_templates["en"])

    earned_title = _loc_text(end_meta.get("earned_title"), loc, "Chronicler of the Realm")
    ending_title = _loc_text(end_meta.get("title"), loc, "Dawn After the Storm")
    endless_mode = str(end_meta.get("endless_mode") or "restoration_peacekeeping")

    title_templates = {
        "en": f"History records your name under the title '{earned_title}' ({ending_title}).",
        "pl": f"Kroniki zapisują twoje imię pod tytułem „{earned_title}” ({ending_title}).",
        "ms": f"Hikayat merakamkan nama anda dengan gelaran '{earned_title}' ({ending_title}).",
        "zh": f"史册以“{earned_title}”（{ending_title}）之名铭记你的传奇。",
        "de": f"Die Chroniken führen deinen Namen unter dem Titel „{earned_title}“ ({ending_title}).",
    }

    tapestry = {
        "ending_id": ending_key,
        "ending_archetype": ending_key,
        "ending_title": ending_title,
        "earned_title": earned_title,
        "endless_mode": endless_mode,
        "is_fallen_world": bool(ending_key == "fallen_world"),
        "slides": [
            {
                "id": "world",
                "slide_id": "world",
                "heading": _loc_text(_TAPESTRY_SLIDE_HEADERS["world"], loc),
                "body": world_text,
                "text": world_text,
            },
            {
                "id": "factions",
                "slide_id": "factions",
                "heading": _loc_text(_TAPESTRY_SLIDE_HEADERS["factions"], loc),
                "body": factions_text,
                "text": factions_text,
            },
            {
                "id": "bonds",
                "slide_id": "bonds",
                "heading": _loc_text(_TAPESTRY_SLIDE_HEADERS["bonds"], loc),
                "body": bonds_text,
                "text": bonds_text,
            },
            {
                "id": "title",
                "slide_id": "title",
                "heading": _loc_text(_TAPESTRY_SLIDE_HEADERS["title"], loc),
                "body": title_templates.get(loc, title_templates["en"]),
                "text": title_templates.get(loc, title_templates["en"]),
            },
        ],
    }

    if session_id:
        prev_tap = dict(spine.get("chronicle_tapestry") or {})
        events = list(spine.get("state_events") or [])
        events.append({"turn": int(turn_number), "kind": "chronicle_tapestry", "prev": prev_tap, "next": tapestry})
        db.upsert_campaign_spine(
            session_id,
            spine.get("scenario") or "fantasy",
            chronicle_tapestry=tapestry,
            state_events=events,
        )
    return tapestry


def mutate_spine_on_lieutenant_fate(
    session_id: int,
    npc_name: str,
    fate: str,
    turn_number: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Zero-Plot-Armor Spine Mutation (Decision 13):
    When a recurring CampaignSpine Lieutenant dies or is recruited early, records a
    turn-stamped rollback delta, updates their status, promotes a vengeful successor,
    and escalates Mastermind countermeasures.
    """
    import db

    spine = db.get_campaign_spine(session_id)
    if not spine:
        return None
    target_low = str(npc_name or "").strip().lower()
    if not target_low:
        return None

    old_lts = [dict(lt) for lt in (spine.get("lieutenants_roster") or [])]
    matched_idx = next(
        (i for i, lt in enumerate(old_lts) if str(lt.get("name") or "").strip().lower() == target_low and lt.get("status") == "active"),
        None,
    )
    if matched_idx is None:
        return None

    new_lts = [dict(lt) for lt in old_lts]
    clean_fate = "recruited" if "recruit" in str(fate).lower() else "dead"
    departed = new_lts[matched_idx]
    departed["status"] = clean_fate
    departed["resolved_turn"] = int(turn_number)

    eff_scen = str(spine.get("scenario") or "fantasy")
    try:
        succ_name = namegen.generate_npc_name(scen_key=eff_scen, gender=departed.get("gender") or "female")
    except Exception:
        succ_name = f"Vengeful {departed.get('role', 'envoy')}"

    new_lts.append(
        {
            "key": f"lt_{session_id}_succ_{int(turn_number)}",
            "name": succ_name,
            "role": f"Vengeful {departed.get('role', 'Lieutenant')}",
            "gender": departed.get("gender") or "female",
            "status": "active",
            "replaces": departed.get("name"),
            "contact_id": None,
        }
    )

    old_mm = dict(spine.get("mastermind_profile") or {})
    mm = dict(old_mm)
    mm["escalation_tier"] = int(mm.get("escalation_tier") or 0) + 1

    prev_axes = dict(_default_ending_axes())
    prev_axes.update(dict(spine.get("ending_axes") or {}))
    next_axes = dict(prev_axes)
    if clean_fate == "recruited":
        rec_list = list(next_axes.get("lieutenants_recruited") or [])
        if departed.get("name") and departed["name"] not in rec_list:
            rec_list.append(str(departed["name"]))
        next_axes["lieutenants_recruited"] = rec_list

    events = list(spine.get("state_events") or [])
    events.append(
        {
            "turn": int(turn_number),
            "kind": "lieutenants_roster",
            "prev": old_lts,
            "next": new_lts,
        }
    )
    events.append(
        {
            "turn": int(turn_number),
            "kind": "mastermind_profile",
            "prev": old_mm,
            "next": mm,
        }
    )
    if next_axes != prev_axes:
        events.append({"turn": int(turn_number), "kind": "ending_axes", "prev": prev_axes, "next": next_axes})
    return db.upsert_campaign_spine(
        session_id,
        eff_scen,
        mastermind_profile=mm,
        lieutenants_roster=new_lts,
        ending_axes=next_axes,
        state_events=events,
    )


def compute_chapter_10_world_scar_buffs(session_id: int) -> Dict[str, Any]:
    """
    Computes Chapter 10 Climax Boss buffs (or non-combat tribunal DC penalties)
    from all unresolved persistent `WorldScars` accumulated across Chapters 1-9.
    """
    import db

    events = db.get_world_events(session_id, include_hidden=True, statuses=("active",)) if session_id else []
    scars = [
        ev for ev in events
        if bool((ev.get("metadata") or {}).get("is_world_scar"))
    ]
    scar_count = len(scars)
    return {
        "active_scar_count": scar_count,
        "scar_titles": [str(s.get("title") or "") for s in scars],
        "boss_hp_multiplier": round(1.0 + min(0.60, 0.15 * scar_count), 2),
        "boss_bonus_stat_points": min(8, 2 * scar_count),
        "extra_reinforcements": min(3, scar_count),
        "climax_dc_penalty": min(4, scar_count),
    }


def promote_escaped_boss_to_nemesis(
    session_id: int,
    boss_sheet: Dict[str, Any],
    quest_id: str,
    turn_number: int = 1,
    reason: str = "fled",
) -> Optional[Dict[str, Any]]:
    """
    Promotes a wounded escaping Boss (`fled_enemies`) into `campaign_spines.nemeses_json`
    so they can resurface in future chapters or Endless Mode Nemesis Hunts.
    """
    import db

    spine = compile_or_get_campaign_spine(session_id)
    nemeses = list(spine.get("nemeses") or [])
    b_name = str(boss_sheet.get("name") or boss_sheet.get("base_name") or "Escaped Nemesis").strip()
    slug = "".join(ch if ch.isalnum() else "_" for ch in b_name.lower()).strip("_")[:24] or "boss"
    nem_id = f"nem_{session_id}_{slug}"

    existing = next((n for n in nemeses if n.get("nemesis_id") == nem_id or str(n.get("name", "")).lower() == b_name.lower()), None)
    if existing:
        existing["grudge_level"] = int(existing.get("grudge_level") or 1) + 1
        existing["last_escaped_turn"] = int(turn_number)
    else:
        upgraded_sheet = dict(boss_sheet)
        upgraded_sheet["level"] = int(upgraded_sheet.get("level") or 1) + 1
        upgraded_sheet["max_hp"] = int(int(upgraded_sheet.get("max_hp") or 120) * 1.15)
        upgraded_sheet["hp"] = upgraded_sheet["max_hp"]
        nemeses.append(
            {
                "nemesis_id": nem_id,
                "name": b_name,
                "source_quest_id": str(quest_id or ""),
                "escape_reason": reason,
                "grudge_level": 1,
                "status": "at_large",
                "spawned_at_turn": int(turn_number),
                "boss_sheet": upgraded_sheet,
            }
        )
    return db.upsert_campaign_spine(session_id, spine.get("scenario") or "fantasy", nemeses=nemeses)
