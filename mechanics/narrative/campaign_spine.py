from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

import namegen
import scenario_data
from mechanics.narrative.blueprints import (
    ensure_world_ending_anomaly_blueprint,
    generate_anomalous_campaign_blueprint,
)
from mechanics.narrative.quest_engines import normalize_quest_locale, resolve_quest_engine

UNIVERSAL_MAX_CHAPTERS = 11

_SCENARIO_MASTERMIND_ARCHETYPES: Dict[str, List[Dict[str, str]]] = {
    "school": [
        {
            "title": "Shadow Regent of the Board",
            "archetype": "social_architect",
            "goal": "privatize campus charters and purge independent student clubs before the Festival",
            "omen": "sealed disciplinary envelopes and whispered expulsions across the hallways",
        },
        {
            "title": "Curator of the Black Ledger",
            "archetype": "blackmail_broker",
            "goal": "manipulate the Student Council election through fabricated scandals",
            "omen": "anonymous rumor broadcasts flickering across student phones at midnight",
        },
    ],
    "scifi": [
        {
            "title": "Architect of Directive Zero",
            "archetype": "rogue_directorate",
            "goal": "lock the sector grid under autonomous neural pacification",
            "omen": "encrypted telemetry blackouts and cold sub-harmonic static",
        },
        {
            "title": "Sovereign of the Ghost Net",
            "archetype": "cyber_syndicate",
            "goal": "seize orbital relay cores and rewrite citizen identity ledgers",
            "omen": "corrupted holo-beacons and rogue drone sweeps in outer wards",
        },
    ],
    "fantasy": [
        {
            "title": "Herald of the Sunken Crown",
            "archetype": "cabal_warlord",
            "goal": "shatter the wardstones binding the Rift beneath the capital",
            "omen": "ashen frost along ancient ley-markers and restless wildlife",
        },
        {
            "title": "Grand Magistrat of the Crimson Tithe",
            "archetype": "corrupt_inquisitor",
            "goal": "monopolize relic vaults and usurp the realm's charter",
            "omen": "iron-sealed inquisitorial warrants posted at dusk",
        },
    ],
}

_UNIVERSAL_CHAPTER_ENGINES: Dict[int, Tuple[str, str]] = {
    1: ("MYSTERY_CASE", "inciting_omen"),
    2: ("ACQUISITION_EXCHANGE", "early_trail"),
    3: ("SOCIAL_BROKERAGE", "web_of_influence"),
    4: ("HEIST_BREACH", "inner_perimeter"),
    5: ("MYSTERY_CASE", "midpoint_revelation"),
    6: ("CRISIS_DEFENSE", "counterstroke"),
    7: ("HUNT_CONTAINMENT", "active_escalation"),
    8: ("RIVALRY_SHOWDOWN", "lieutenant_reckoning"),
    9: ("CRISIS_DEFENSE", "darkest_hour"),
    10: ("HUNT_CONTAINMENT", "final_climax"),
    11: ("SOCIAL_BROKERAGE", "playable_epilogue"),
}


def _seed_int(seed_str: str) -> int:
    return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)


def _pick_scenario_bucket(scen_key: str) -> str:
    if scenario_data.is_school_scenario(scen_key) or scenario_data.is_non_combat_scenario(scen_key):
        return "school"
    low = str(scen_key or "fantasy").lower()
    if any(k in low for k in ("sci", "cyber", "post_apoc", "space", "modern")):
        return "scifi"
    return "fantasy"


def _build_universal_chapters_blueprint(
    session_id: int,
    scen_key: str,
    mastermind: Dict[str, Any],
    lieutenants: List[Dict[str, Any]],
    is_non_combat: bool,
    lang: str = "en",
) -> Dict[str, Any]:
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        anom_bp = generate_anomalous_campaign_blueprint(session_id)
        out: Dict[str, Any] = {}
        for ch_num, ch_data in (anom_bp.get("chapters") or {}).items():
            c_idx = int(ch_num)
            eng_info = resolve_quest_engine(ch_data.get("archetype", ""), "")
            out[str(c_idx)] = {
                "chapter": c_idx,
                "phase": ch_data.get("phase", "rising_action"),
                "engine": "SOCIAL_BROKERAGE" if c_idx == 11 else eng_info["engine"],
                "title_template": ch_data.get("title_template", f"Chapter #{c_idx}"),
                "archetype": ch_data.get("archetype", ""),
                "sub_archetypes": list(ch_data.get("sub_archetypes") or []),
                "pacing_directive": ch_data.get("pacing_directive", ""),
                "has_final_bossfight": bool(c_idx == 10 and not is_non_combat),
                "is_playable_epilogue": bool(c_idx == 11),
            }
        return out

    m_name = mastermind.get("name", "The Hidden Architect")
    m_title = mastermind.get("title", "Shadow Sovereign")
    m_goal = mastermind.get("goal", "reshape the realm")
    omen = mastermind.get("omen", "unsettling signs across the district")
    lt_lead = lieutenants[0]["name"] if lieutenants else "the Vanguard Envoy"
    lt_second = lieutenants[1]["name"] if len(lieutenants) > 1 else lt_lead

    loc = normalize_quest_locale(lang)
    ch_prefix = {"en": "Chapter", "pl": "Rozdział", "ms": "Bab", "zh": "第", "de": "Kapitel"}.get(loc, "Chapter")

    def _fmt_ch(n: int, subtitle: str) -> str:
        if loc == "zh":
            return f"第{n}章：{subtitle}"
        return f"{ch_prefix} #{n}: {subtitle}"

    chapters: Dict[str, Any] = {}
    for ch_idx in range(1, UNIVERSAL_MAX_CHAPTERS + 1):
        eng, phase = _UNIVERSAL_CHAPTER_ENGINES[ch_idx]
        if is_non_combat and eng == "HUNT_CONTAINMENT":
            eng = "RIVALRY_SHOWDOWN" if ch_idx == 10 else "MYSTERY_CASE"

        if ch_idx == 1:
            subtitle = "First Sparks & The Quiet Omen"
            directive = f"Introduce the inciting thread and end with an unmistakable omen ({omen}) tied to {m_name}."
        elif ch_idx == 5:
            subtitle = f"The Mask of {lt_lead}"
            directive = f"Midpoint twist: expose how {lt_lead} serves {m_name} ({m_title}) to {m_goal}."
        elif ch_idx == 8:
            subtitle = f"Reckoning with {lt_second}"
            directive = f"Confront {lt_second}'s inner operation and sever key support before the finale."
        elif ch_idx == 9:
            subtitle = "Eve of the Reckoning"
            directive = f"Darkest Hour: {m_name}'s plan nears completion ({omen}); rally allies for the decisive push."
        elif ch_idx == 10:
            subtitle = f"Climax — {m_name}"
            directive = (
                f"Final Chapter Climax against {m_name} ({m_title})! Accumulated WorldScars and Lieutenant fates shape the final confrontation."
            )
        elif ch_idx == 11:
            subtitle = "Epilogue — Dawn After the Storm"
            directive = (
                f"Universal Playable Epilogue following {m_name}'s downfall: settle lingering threads, celebrate or mourn with companions, "
                f"and choose between [Archive Chronicle] or [Endless Sandbox Mode]."
            )
        else:
            subtitle = f"Threads of {m_title} ({ch_idx})"
            directive = f"Advance the investigation and counter-operations against {m_name}'s network ({omen})."

        chapters[str(ch_idx)] = {
            "chapter": ch_idx,
            "phase": phase,
            "engine": eng,
            "title_template": _fmt_ch(ch_idx, subtitle),
            "archetype": eng.replace("_", " ").title(),
            "pacing_directive": directive,
            "featured_lieutenant": lt_lead if ch_idx <= 5 else (lt_second if ch_idx <= 9 else ""),
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
    Deterministically compiles (at `t = 0`) or fetches the session's 11-chapter `CampaignSpine`
    across ALL scenarios, including recurring Lieutenants and Ch.10/Ch.11 arc metadata.
    """
    import db
    if not force_recompile and session_id:
        existing = db.get_campaign_spine(session_id)
        if existing and existing.get("chapters_blueprint"):
            return existing

    sess = db.get_session(session_id) if session_id else {}
    sess = sess or {}
    eff_scen = str(scen_key or sess.get("scenario") or "fantasy")
    eff_lang = normalize_quest_locale(lang or sess.get("narration_language") or sess.get("language") or "en")
    is_non_combat = bool(scenario_data.is_non_combat_scenario(eff_scen))

    if scenario_data.is_anomalous_incursions_scenario(eff_scen):
        anomaly = ensure_world_ending_anomaly_blueprint(session_id, session=sess)
        mastermind = {
            "name": anomaly.get("name", "The Non-Euclidean Convergence"),
            "title": anomaly.get("title", "Sovereign of the Folded Horizon"),
            "archetype": "eldritch_cataclysm",
            "goal": anomaly.get("cult_goal", "awaken the World-Ending Anomaly across the metropolitan grid"),
            "omen": anomaly.get("foreshadow_sign") or "geometric distortions and bleeding static",
            "escalation_tier": 0,
            "is_non_combat": False,
        }
    else:
        bucket = _pick_scenario_bucket(eff_scen)
        pool = _SCENARIO_MASTERMIND_ARCHETYPES[bucket]
        picked = pool[_seed_int(f"spine_mm:{session_id}:{eff_scen}") % len(pool)]
        try:
            mm_name = namegen.generate_npc_name(scen_key=eff_scen, gender="male" if (_seed_int(f"g:{session_id}") % 2 == 0) else "female")
        except Exception:
            mm_name = "Sovereign Vane"
        mastermind = {
            "name": mm_name,
            "title": picked["title"],
            "archetype": picked["archetype"],
            "goal": picked["goal"],
            "omen": picked["omen"],
            "escalation_tier": 0,
            "is_non_combat": is_non_combat,
        }

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

    chapters = _build_universal_chapters_blueprint(
        session_id=session_id,
        scen_key=eff_scen,
        mastermind=mastermind,
        lieutenants=lieutenants,
        is_non_combat=is_non_combat,
        lang=eff_lang,
    )

    saved = db.upsert_campaign_spine(
        session_id,
        eff_scen,
        mastermind_profile=mastermind,
        lieutenants_roster=lieutenants,
        chapters_blueprint=chapters,
        nemeses=[],
        climax_status="pending",
        epilogue_status="pending",
        state_events=[],
    )
    return saved or {
        "session_id": session_id,
        "scenario": eff_scen,
        "mastermind_profile": mastermind,
        "lieutenants_roster": lieutenants,
        "chapters_blueprint": chapters,
        "nemeses": [],
        "climax_status": "pending",
        "epilogue_status": "pending",
    }


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

    mm = dict(spine.get("mastermind_profile") or {})
    mm["escalation_tier"] = int(mm.get("escalation_tier") or 0) + 1

    events = list(spine.get("state_events") or [])
    events.append(
        {
            "turn": int(turn_number),
            "kind": "lieutenants_roster",
            "prev": old_lts,
            "next": new_lts,
        }
    )
    return db.upsert_campaign_spine(
        session_id,
        eff_scen,
        mastermind_profile=mm,
        lieutenants_roster=new_lts,
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
