from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import namegen
import scenario_data
from mechanics.combat import enemies as combat_enemies
from mechanics.narrative.campaign_spine import (
    PEAK_CHAPTERS,
    _PLACEHOLDER_ACTOR_RE,
    compile_or_get_campaign_spine,
    compute_chapter_10_world_scar_buffs,
)
from mechanics.narrative.quest_engines import (
    build_engine_lead_approaches,
    build_turn_in_rules,
    load_quest_engines_catalog,
    normalize_quest_locale,
    render_offline_pitch_stub,
    render_optional_objective_template,
    render_world_scar_spec,
    resolve_quest_engine,
    roll_dossier_twist_spec,
)
from mechanics.social import relationship_graph as rg
from mechanics.social.persona.intimacy.ledger import (
    enforce_biological_invariants,
    normalize_gender,
)

FAMILY_SCENE_PRIORITY: Dict[str, int] = {
    "story": 1,
    "loyalty": 2,
    "dispatch": 3,
    "bounty": 3,
    "rumor": 4,
    "minor": 4,
    "micro": 4,
}


def _det_int(seed_str: str, mod: int) -> int:
    if mod <= 0:
        return 0
    return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16) % mod


def infer_quest_family_tier(
    quest_id: str,
    quest_type: str = "",
    is_story_quest: bool = False,
    quest_notes: str = "",
) -> str:
    qid_up = str(quest_id or "").strip().upper()
    notes_low = str(quest_notes or "").lower()
    qtype_low = str(quest_type or "").lower()
    if is_story_quest or qid_up.startswith("SQ-") or qtype_low in ("story quest", "main quest"):
        return "story"
    if qid_up.startswith("CLR-") or "companion_loyalty:1" in notes_low or "loyalty" in qtype_low:
        return "loyalty"
    if qid_up.startswith("MAND-") or "mandatory_daily:1" in notes_low or "dispatch" in qtype_low:
        return "dispatch"
    if qid_up.startswith("RMR-") or "rumor_investigation:1" in notes_low or "rumor" in qtype_low:
        return "rumor"
    if qid_up.startswith("MNR-") or "minor_bounty:1" in notes_low or "minor incident" in qtype_low:
        return "minor"
    return "bounty"


def get_protected_quest_cast_names(session_id: int) -> Set[str]:
    """
    Returns lowercase names of NPCs protected from being rolled as killable Side Bounty targets:
    party companions, CampaignSpine Mastermind/Lieutenants, and active Story/Loyalty quest cast.
    """
    protected: Set[str] = set()
    if not session_id:
        return protected
    import db
    try:
        for p in (db.get_session_party_npcs(session_id) or []):
            if p.get("name"):
                protected.add(str(p["name"]).strip().lower())
    except Exception:
        pass

    spine = db.get_campaign_spine(session_id)
    if spine:
        mm_name = (spine.get("mastermind_profile") or {}).get("name")
        if mm_name:
            protected.add(str(mm_name).strip().lower())
        for lt in (spine.get("lieutenants_roster") or []):
            if lt.get("status") == "active" and lt.get("name"):
                protected.add(str(lt["name"]).strip().lower())

    for dos in (db.get_session_quest_dossiers(session_id, status_stage="compiled") or []):
        if dos.get("family_tier") in ("story", "loyalty"):
            cb = dos.get("cast_bindings") or {}
            for role_obj in cb.values():
                if isinstance(role_obj, dict) and role_obj.get("name"):
                    protected.add(str(role_obj["name"]).strip().lower())

    try:
        for c in (db.get_contacts(session_id) or []):
            c_nm = str(c.get("name") or "").strip().lower()
            if not c_nm:
                continue
            aff = int(c.get("affinity") or 0)
            rel = str(c.get("relationship") or "").lower()
            if aff >= 15 or rel in ("companion", "ally", "friend", "partner", "spouse", "lover"):
                protected.add(c_nm)
    except Exception:
        pass

    return protected


from mechanics.world.locations.hierarchy import format_venue_display, format_short_venue_display


SAFE_SANCTUARY_KEYWORDS: Tuple[str, ...] = (
    " hq", "hq ", "headquarters", "directorate", "main lobby", "security hub", "command complex",
    "operations facility", "dormitor", "dorm room", "player home", "apartment", "residence",
    "bedroom", "hospital", "infirmary", "clinic", "tavern", "inn ", "guild hall", "guildhall",
)
_INVESTIGATIVE_ENGINES: Tuple[str, ...] = ("MYSTERY_CASE", "SOCIAL_BROKERAGE", "ACQUISITION_EXCHANGE")
_OBJECTIVE_STOPWORDS: Set[str] = {
    "the", "and", "with", "from", "into", "within", "before", "after", "their", "your", "that", "this",
    "investigate", "district", "source", "reported", "sudden", "prevent", "secure", "trace", "origin",
}


def is_safe_sanctuary_location(location: str) -> bool:
    """True for safe hubs (agency HQ lobbies, homes/dorms, hospitals, taverns/guild halls) that must never host quest combat."""
    low = f" {str(location or '').strip().lower()} "
    return bool(low.strip()) and any(kw in low for kw in SAFE_SANCTUARY_KEYWORDS)


def select_deconflicted_climax_location(
    session_id: int,
    preferred_location: str = "",
    family_tier: str = "bounty",
    objective_hint: str = "",
    extra_exclude: Optional[Set[str]] = None,
    scen_key: str = "",
) -> Tuple[str, str]:
    """
    Ensures active quests prefer distinct Tier-3 rooms so Story, Loyalty, and Side Bounties
    do not stack multiple Boss encounters into the exact same room simultaneously.
    Never selects safe sanctuaries, the player's current room, or any `extra_exclude` room;
    prefers rooms matching the objective text, then anomalous danger rooms in Anomalous scenarios.
    """
    occupied_locs: Set[str] = set()
    import db
    cur_loc_low = ""
    if session_id:
        for dos in (db.get_session_quest_dossiers(session_id, status_stage="compiled") or []):
            cs = dos.get("climax_spec") or {}
            loc_str = str(cs.get("location") or "").strip().lower()
            if loc_str:
                occupied_locs.add(loc_str)
        try:
            cur_loc_low = str((db.get_session(session_id) or {}).get("current_location") or "").strip().lower()
        except Exception:
            cur_loc_low = ""
    excluded: Set[str] = {str(x).strip().lower() for x in (extra_exclude or set()) if x}
    if cur_loc_low:
        excluded.add(cur_loc_low)

    def _forbidden(loc: str) -> bool:
        low = str(loc or "").strip().lower()
        return bool(not low or low in excluded or is_safe_sanctuary_location(low))

    pref_clean = str(preferred_location or "").strip()
    if pref_clean and not _forbidden(pref_clean) and (family_tier == "story" or pref_clean.lower() not in occupied_locs):
        node_id = ""
        if session_id:
            try:
                node_id = str(db.resolve_node_id_from_location(session_id, pref_clean) or "")
            except Exception:
                node_id = ""
        return pref_clean, node_id

    if session_id:
        try:
            nodes = db.get_session_world_nodes(session_id) or []

            def _node_path(n: Dict[str, Any]) -> str:
                return str(n.get("full_path") or n.get("name") or "").strip()

            tier3_all = [
                n for n in nodes
                if int(n.get("tier") or 3) >= 3
                and not _forbidden(_node_path(n))
                and not _forbidden(str(n.get("name") or ""))
            ]
            tier3 = [n for n in tier3_all if _node_path(n).lower() not in occupied_locs] or tier3_all
            rooms_only = [n for n in tier3 if str(n.get("node_type") or "").upper() == "ROOM"]
            if rooms_only:
                tier3 = rooms_only
            # 1) Objective-text cue matching (e.g. "High School", named district)
            obj_tokens = {
                t for t in "".join(ch if ch.isalnum() else " " for ch in str(objective_hint or "").lower()).split()
                if len(t) >= 4 and t not in _OBJECTIVE_STOPWORDS
            }
            obj_matched = False
            if obj_tokens and tier3:
                scored = []
                for n in tier3:
                    hay = f"{_node_path(n)} {n.get('parent_id') or ''} {n.get('node_id') or ''}".lower()
                    score = sum(1 for t in obj_tokens if t in hay)
                    if score:
                        scored.append((score, n))
                if scored:
                    best = max(s for s, _ in scored)
                    tier3 = [n for s, n in scored if s == best]
                    obj_matched = True
            # 2) Anomalous scenarios: prefer anomalous danger rooms
            if not obj_matched and tier3 and (
                scenario_data.is_anomalous_high_school_scenario(scen_key or "")
                or scenario_data.is_anomalous_incursions_scenario(scen_key or "")
            ):
                try:
                    danger = [
                        n for n in tier3
                        if combat_enemies.is_anomalous_danger_zone(
                            location_name=_node_path(n), location_id=str(n.get("node_id") or ""), scen_key=scen_key,
                        )
                    ]
                    if danger:
                        tier3 = danger
                except Exception:
                    pass
            if tier3:
                chosen = tier3[_det_int(f"room:{session_id}:{pref_clean}:{family_tier}", len(tier3))]
                chosen_path = str(chosen.get("full_path") or "").strip()
                if not chosen_path and chosen.get("node_id"):
                    try:
                        ancestors = db.get_node_ancestors(session_id, str(chosen["node_id"])) or []
                        chain = [str(a.get("name") or "") for a in reversed(ancestors) if a.get("name")]
                        chosen_path = " ➔ ".join(chain + [str(chosen.get("name") or "")])
                    except Exception:
                        chosen_path = ""
                return str(chosen_path or chosen.get("name") or pref_clean or "District Sanctum"), str(chosen.get("node_id") or "")
        except Exception:
            pass

    if pref_clean and not is_safe_sanctuary_location(pref_clean) and pref_clean.lower() not in excluded:
        return pref_clean, ""
    return "District Inner Chamber", ""


def _is_incestuous_with_player(session_id: int, candidate_name: str) -> bool:
    if not session_id or not candidate_name:
        return False
    import db
    p_key = rg.canonical_person_key(candidate_name)
    try:
        if rg.is_incestuous(session_id, "player", p_key):
            return True
    except Exception:
        pass
    try:
        cand_low = candidate_name.strip().lower()
        for c in (db.get_contacts(session_id) or []):
            if str(c.get("name") or "").strip().lower() != cand_low:
                continue
            rel = c.get("relations") if isinstance(c.get("relations"), dict) else {}
            fam_role = str(rel.get("player_kinship") or rel.get("kinship_to_player") or c.get("relationship") or "").lower()
            if any(w in fam_role for w in ("sister", "brother", "mother", "father", "sibling", "parent", "daughter", "son", "cousin", "family")):
                return True
    except Exception:
        pass
    return False


def _pick_safe_npc_name(
    session_id: int,
    scen_key: str,
    seed_tag: str,
    avoid_low: Set[str],
    for_intimate: bool = False,
    preferred_gender: str = "",
    role: str = "",
) -> Tuple[str, str, Optional[int]]:
    """Selects or procedurally generates an NPC name respecting protected-cast and genealogy/incest guards."""
    import db
    gender = preferred_gender or ("female" if _det_int(seed_tag, 2) == 0 else "male")
    is_target_role = bool((role in ("target", "antagonist", "enemy") or seed_tag.startswith("target:")) and not for_intimate)
    if session_id and not is_target_role:
        try:
            contacts = db.get_contacts(session_id) or []
            for c in contacts:
                c_name = str(c.get("name") or "").strip()
                if not c_name or c_name.lower() in avoid_low:
                    continue
                if for_intimate and _is_incestuous_with_player(session_id, c_name):
                    continue
                c_gender = normalize_gender(c.get("gender") or (c.get("basic_info") or {}).get("gender") or gender)
                return c_name, (c_gender if c_gender != "unknown" else gender), int(c["id"]) if c.get("id") else None
        except Exception:
            pass

    for attempt in range(8):
        try:
            cand = namegen.generate_npc_name(scenario=scen_key, gender=gender)
        except Exception:
            cand = f"Operative {attempt + 1}"
        if not cand or cand.lower() in avoid_low:
            continue
        if for_intimate and session_id and _is_incestuous_with_player(session_id, cand):
            continue
        return cand, gender, None
    return "Mysterious Broker", gender, None


def _pick_inner_circle_ally(session_id: int) -> str:
    """Finds a real party companion, romantic partner, or high-affinity contact for Ch. 9 Darkest Hour on-screen triage."""
    if not session_id:
        return ""
    import db

    try:
        party_npcs = db.get_session_party_npcs(session_id) or []
        for p in party_npcs:
            if p.get("name"):
                return str(p["name"]).strip()
    except Exception:
        pass
    try:
        contacts = db.get_contacts(session_id) or []
        ranked = sorted(contacts, key=lambda c: int(c.get("affinity") or 0), reverse=True)
        for c in ranked:
            if c.get("name") and int(c.get("affinity") or 0) >= 10:
                return str(c["name"]).strip()
    except Exception:
        pass
    return ""


def _build_main_objective_stages(
    engine: str,
    family_tier: str,
    chapter: int,
    main_stage_count: int,
    climax_loc: str,
    origin_loc: str,
    target_npc: str,
    informant_npc: str,
    danger_tier: int,
    gate_mode: str,
    inner_circle_ally: str = "",
    lang: str = "en",
    mid_loc: str = "",
    custom_stage_labels: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    loc = normalize_quest_locale(lang)
    short_venue = format_short_venue_display(climax_loc) or (climax_loc.split("➔")[-1].strip() if "➔" in climax_loc else climax_loc)
    outer_loc = origin_loc if (origin_loc and origin_loc != climax_loc) else climax_loc
    short_outer = format_short_venue_display(outer_loc) or outer_loc
    eff_mid_loc = mid_loc if (mid_loc and mid_loc != outer_loc) else climax_loc
    short_mid = format_short_venue_display(eff_mid_loc) or eff_mid_loc

    catalog = load_quest_engines_catalog()
    eng_data = (catalog.get("engines") or {}).get(engine) or {}
    b_tmpls = eng_data.get("beat_templates") or {}

    def _render_beat_field(field_val: Any, slots: Dict[str, str], fallback: str = "") -> str:
        raw = ""
        if isinstance(field_val, dict):
            raw = str(field_val.get(loc) or field_val.get("en") or fallback)
        elif isinstance(field_val, str):
            raw = field_val
        else:
            raw = fallback
        for k, v in slots.items():
            raw = raw.replace(f"{{{k}}}", str(v))
        raw = re.sub(r"\{[a-zA-Z0-9_]+\}", "", raw)
        return raw.strip()

    if gate_mode == "secret":
        masked_target = {
            "en": "the target's hidden whereabouts",
            "pl": "kryjówki celu",
            "ms": "lokasi tersembunyi sasaran",
            "zh": "目标的隐秘藏身点",
            "de": "den geheimen Aufenthaltsort des Ziels",
        }.get(loc, "the target's hidden whereabouts")
        eff_venue_label = masked_target
    else:
        eff_venue_label = short_venue

    stage1_labels = {
        "en": f"Breach the outer perimeter and secure approach to {eff_venue_label}",
        "pl": f"Przełam zewnętrzny kordon i otwórz drogę do: {eff_venue_label}",
        "ms": f"Tembusi perimeter luar dan buka laluan ke {eff_venue_label}",
        "zh": f"突破外围防线，打开通往{eff_venue_label}的推进路线",
        "de": f"Durchbrich den Außenring und sichere den Zugang zu {eff_venue_label}",
    }
    if engine in ("MYSTERY_CASE", "SOCIAL_BROKERAGE"):
        stage1_labels = {
            "en": f"Establish the field trail and leverage points around {eff_venue_label}",
            "pl": f"Ustal trop terenowy i punkty nacisku wokół: {eff_venue_label}",
            "ms": f"Kenal pasti jejak lapangan dan titik pengaruh sekitar {eff_venue_label}",
            "zh": f"摸清{eff_venue_label}周边的现场线索与关键筹码",
            "de": f"Sichere Spuren und Druckmittel rund um {eff_venue_label}",
        }

    eff_st1_lbl = (
        custom_stage_labels[0]
        if (custom_stage_labels and len(custom_stage_labels) > 0 and custom_stage_labels[0])
        else stage1_labels.get(loc, stage1_labels["en"])
    )

    next_v1 = short_mid if main_stage_count >= 3 else short_venue
    slots_1 = {
        "informant": informant_npc or "informant",
        "target": target_npc or "adversary",
        "venue": short_outer,
        "next_venue": next_v1,
    }
    st1_b = b_tmpls.get("stage_1") or {}
    st1_verb = _render_beat_field(st1_b.get("player_verb"), slots_1, f"Investigate {short_outer}")
    st1_rev = _render_beat_field(st1_b.get("reveal"), slots_1, f"Leads confirm operations at {next_v1}")
    st1_hand = _render_beat_field(st1_b.get("handover"), slots_1, "Field telemetry log")
    st1_next = _render_beat_field(st1_b.get("next_pointer"), slots_1, next_v1) or next_v1

    stages: List[Dict[str, Any]] = [
        {
            "stage_index": 1,
            "stage_label": eff_st1_lbl,
            "target_location": outer_loc,
            "target_npc": informant_npc if engine in ("MYSTERY_CASE", "SOCIAL_BROKERAGE") else "",
            "completion_trigger": "action",
            "approaches": build_engine_lead_approaches(["PER", "AGI", "CHA"], danger_tier=danger_tier, allow_curfew_stealth=(engine != "INTIMATE_LIAISON")),
            "status": "active",
            "can_be_bypassed": True,
            "beat_contract": {
                "player_verb": st1_verb,
                "reveal": st1_rev,
                "handover": st1_hand,
                "next_pointer": st1_next,
                "is_dialogue_beat": bool(st1_b.get("is_dialogue_beat", True) if informant_npc else False),
            },
        }
    ]

    if main_stage_count >= 3:
        if family_tier == "story" and chapter == 9 and inner_circle_ally:
            mid_labels = {
                "en": f"On-Screen Triage: Hold the line with {inner_circle_ally} inside {short_venue}",
                "pl": f"Ratunek na żywo: Utrzymaj pozycję z osobą {inner_circle_ally} w {short_venue}",
                "ms": f"Penyelamatan Langsung: Pertahankan barisan bersama {inner_circle_ally} di {short_venue}",
                "zh": f"当面救援抉择：在{short_venue}与{inner_circle_ally}死守防线",
                "de": f"Rettung vor Ort: Halte mit {inner_circle_ally} die Stellung in {short_venue}",
            }
            mid_npc = inner_circle_ally
        else:
            mid_labels = {
                "en": f"Shatter the inner defense nexus at {short_venue}",
                "pl": f"Rozbij wewnętrzny węzeł obrony w: {short_venue}",
                "ms": f"Hancurkan teras pertahanan dalaman di {short_venue}",
                "zh": f"瓦解{short_venue}的核心内层防卫中枢",
                "de": f"Zerschlage den inneren Verteidigungsknoten bei {short_venue}",
            }
            mid_npc = ""
        eff_mid_lbl = (
            custom_stage_labels[1]
            if (custom_stage_labels and len(custom_stage_labels) > 1 and custom_stage_labels[1])
            else mid_labels.get(loc, mid_labels["en"])
        )

        st2_b = b_tmpls.get("stage_mid") or {}
        slots_2 = {
            "informant": informant_npc or "informant",
            "target": target_npc or "adversary",
            "venue": short_mid,
            "next_venue": short_venue,
        }
        st2_verb = _render_beat_field(st2_b.get("player_verb"), slots_2, f"Breach defenses at {short_mid}")
        st2_rev = _render_beat_field(st2_b.get("reveal"), slots_2, f"Dispatch traces headquarters to {short_venue}")
        st2_hand = _render_beat_field(st2_b.get("handover"), slots_2, "Relay access cipher")
        st2_next = _render_beat_field(st2_b.get("next_pointer"), slots_2, short_venue) or short_venue

        stages.append(
            {
                "stage_index": 2,
                "stage_label": eff_mid_lbl,
                "target_location": eff_mid_loc,
                "target_npc": mid_npc,
                "completion_trigger": "action",
                "approaches": build_engine_lead_approaches(["STR", "INT", "CHA"], danger_tier=danger_tier, allow_curfew_stealth=(engine != "INTIMATE_LIAISON")),
                "status": "locked",
                "fair_jeopardy_on_screen_only": bool(mid_npc),
                "beat_contract": {
                    "player_verb": st2_verb,
                    "reveal": st2_rev,
                    "handover": st2_hand,
                    "next_pointer": st2_next,
                    "is_dialogue_beat": bool(st2_b.get("is_dialogue_beat", False) if mid_npc else False),
                },
            }
        )

    final_idx = len(stages) + 1
    final_labels = {
        "en": f"Resolve the decisive confrontation with {target_npc} at {short_venue}",
        "pl": f"Rozstrzygnij decydujące starcie z {target_npc} w: {short_venue}",
        "ms": f"Selesaikan pertembungan penentu bersama {target_npc} di {short_venue}",
        "zh": f"在{short_venue}与{target_npc}展开终极对决并做下决断",
        "de": f"Führe die entscheidende Konfrontation mit {target_npc} bei {short_venue} zu Ende",
    }
    eff_fnl_lbl = (
        custom_stage_labels[final_idx - 1]
        if (custom_stage_labels and len(custom_stage_labels) >= final_idx and custom_stage_labels[final_idx - 1])
        else final_labels.get(loc, final_labels["en"])
    )

    st_c_b = b_tmpls.get("stage_climax") or {}
    slots_c = {
        "informant": informant_npc or "informant",
        "target": target_npc or "adversary",
        "venue": short_venue,
        "next_venue": short_venue,
    }
    st_c_verb = _render_beat_field(st_c_b.get("player_verb"), slots_c, f"Confront {target_npc} at {short_venue}")
    st_c_rev = _render_beat_field(st_c_b.get("reveal"), slots_c, f"{target_npc}'s operations are decisively shattered")
    st_c_hand = _render_beat_field(st_c_b.get("handover"), slots_c, "Decisive operation ledger")
    st_c_next = short_venue

    stages.append(
        {
            "stage_index": final_idx,
            "stage_label": eff_fnl_lbl,
            "target_location": climax_loc,
            "target_npc": target_npc,
            "completion_trigger": "action",
            "approaches": build_engine_lead_approaches(["STR", "CHA", "INT", "AGI"], danger_tier=danger_tier, allow_curfew_stealth=(engine != "INTIMATE_LIAISON")),
            "status": "locked",
            "is_climax_stage": True,
            "follow_npc_schedule": 0,
            "requires_secret_unlock": bool(gate_mode == "secret"),
            "beat_contract": {
                "player_verb": st_c_verb,
                "reveal": st_c_rev,
                "handover": st_c_hand,
                "next_pointer": st_c_next,
                "is_dialogue_beat": bool(st_c_b.get("is_dialogue_beat", False)),
            },
        }
    )
    return stages


def compile_bounty_pitch_stub(
    session_id: int,
    quest_id: str,
    tag_or_archetype: str,
    title: str = "",
    public_pitch: str = "",
    client_npc: str = "",
    client_location: str = "",
    origin_location: str = "",
    reward_gold: int = 40,
    reward_xp: int = 100,
    reward_item: str = "",
    danger_tier: int = 1,
    deadline_day: Optional[int] = None,
    deadline_minute: Optional[int] = None,
    scen_key: str = "fantasy",
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Stage 1 Two-Tier Bounty (`status='Available'`, `dossier_stage='pitch'`):
    Stores lightweight PitchStub in `quest_dossiers` without spawning orphan cast NPCs in `contacts`.
    """
    is_nsfw_scen = bool(scenario_data.has_tag(scen_key, "nsfw") or scenario_data.uses_nsfw_model(scen_key))
    eng_info = resolve_quest_engine(tag_or_archetype, public_pitch or title, is_nsfw_scenario=is_nsfw_scen)
    engine = eng_info["engine"]

    eff_client = client_npc or "Guild Dispatcher"
    eff_loc = client_location or origin_location or "Notice Board"
    fb_title, fb_pitch = render_offline_pitch_stub(
        engine,
        {"client": eff_client, "venue": eff_loc, "zone": eff_loc.split("➔")[0].strip(), "target": "an elusive party"},
        lang=lang,
    )
    eff_title = title or fb_title
    eff_pitch = public_pitch or fb_pitch

    stub_payload = {
        "quest_id": quest_id,
        "title": eff_title,
        "engine": engine,
        "legacy_blueprint": eng_info["legacy_blueprint"],
        "public_pitch": eff_pitch,
        "client_npc": eff_client,
        "client_location": eff_loc,
        "origin_location": origin_location or eff_loc,
        "reward_gold": int(reward_gold or 40),
        "reward_xp": int(reward_xp or 100),
        "reward_item": str(reward_item or ""),
        "danger_tier": max(1, min(5, int(danger_tier or 1))),
        "deadline_day": deadline_day,
        "deadline_minute": deadline_minute,
        "uses_nsfw_routing": bool(eng_info["uses_nsfw_routing"]),
        "raw_archetype": str(tag_or_archetype or ""),
    }

    import db
    saved = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engine=engine,
        family_tier="bounty",
        danger_tier=stub_payload["danger_tier"],
        status_stage="pitch",
        compiled_at_turn=0,
        pitch_stub=stub_payload,
    )
    return saved or stub_payload


def hydrate_boss_sheet_from_quest_blueprint(boss_sheet: Dict[str, Any], quest_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Re-binds a quest climax boss to the quest's persisted hostile AnomalyBlueprint (`anomaly_bp:` in quest_notes),
    preserving Folklore Codex identity, Vessel Tether, taboo, offerings and disguise, and the LATEST dossier
    reveal state (so a mid-quest reveal is reflected when the boss spawns). Non-anomalous quests are untouched.
    """
    if not isinstance(boss_sheet, dict) or not isinstance(quest_row, dict):
        return boss_sheet
    notes = str(quest_row.get("quest_notes") or "")
    has_col_bp = bool(
        isinstance(quest_row.get("anomaly_blueprint"), dict) and quest_row.get("anomaly_blueprint")
    ) or str(quest_row.get("anomaly_blueprint_json") or "").strip() not in ("", "{}")
    if not has_col_bp and "anomaly_bp:" not in notes and "anomaly_blueprint:" not in notes:
        return boss_sheet
    try:
        from mechanics.world.anomaly_engine import parse_blueprint_from_notes, instantiate_enemy_from_blueprint
        bp = parse_blueprint_from_notes(quest_row)
        if not isinstance(bp, dict) or str(bp.get("disposition") or "hostile").lower() != "hostile":
            return boss_sheet
        if "dossier_revealed:1" in notes:
            bp["dossier_revealed"] = True
        hydrated = instantiate_enemy_from_blueprint(
            bp,
            level=int(boss_sheet.get("level") or 1),
            tier_rank=int(boss_sheet.get("tier_rank") or bp.get("tier_rank") or 3),
            linked_quest_id=str(quest_row.get("quest_id") or ""),
            is_story_quest=bool(quest_row.get("is_story_quest")),
            base_enemy=dict(boss_sheet),
        )
        if isinstance(hydrated, dict):
            # Keep the dossier's party-scaled / Chapter-10 scar-buffed vitals
            for keep_k in ("max_hp", "hp", "world_scar_buffs"):
                if keep_k in boss_sheet:
                    hydrated[keep_k] = boss_sheet[keep_k]
            return hydrated
    except Exception:
        return boss_sheet
    return boss_sheet


def _build_combat_rosters_for_dossier(
    session_id: int,
    scen_key: str,
    engine: str,
    family_tier: str,
    danger_tier: int,
    chapter: int,
    climax_location: str,
    target_name: str,
    lang: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Pre-generates party-scaled objective `encounter_roster` and Climax `boss_sheet` (skipped in non-combat scenarios)."""
    if scenario_data.is_non_combat_scenario(scen_key) or engine == "INTIMATE_LIAISON":
        return [], None

    combat_heavy = engine in ("HUNT_CONTAINMENT", "CRISIS_DEFENSE", "RIVALRY_SHOWDOWN", "HEIST_BREACH")
    if not combat_heavy and family_tier not in ("story", "dispatch") and danger_tier < 3:
        return [], None

    import db
    party_chars = db.get_session_characters(session_id) if session_id else []
    eff_chapter = max(1, int(chapter or danger_tier or 1))

    # Investigative/social engines never pre-seed mandatory Lead monster packs.
    skip_lead_pack = engine in _INVESTIGATIVE_ENGINES
    try:
        if skip_lead_pack:
            encounter_roster = []
        else:
            pack, _mult = combat_enemies.generate_balanced_encounter(
                party_members=party_chars,
                scenario=scen_key,
                location=climax_location,
                chapter=eff_chapter,
                language=lang,
            )
            encounter_roster = pack[: max(1, min(3, len(pack)))]
    except Exception:
        encounter_roster = []

    boss_tier = 5 if (family_tier == "story" and eff_chapter >= 10) else (4 if danger_tier >= 3 or family_tier == "story" else 3)
    boss_sheet = combat_enemies.generate_scenario_enemy(
        scenario=scen_key,
        location=climax_location,
        chapter=eff_chapter,
        custom_name=target_name if engine in ("HUNT_CONTAINMENT", "RIVALRY_SHOWDOWN") or (family_tier == "story" and eff_chapter == 10) else None,
        exact_tier=boss_tier,
        language=lang,
    )

    if family_tier == "story" and eff_chapter == 10 and session_id:
        scar_buffs = compute_chapter_10_world_scar_buffs(session_id)
        hp_mult = float(scar_buffs.get("boss_hp_multiplier") or 1.0)
        bonus_pts = int(scar_buffs.get("boss_bonus_stat_points") or 0)
        boss_sheet["max_hp"] = int(int(boss_sheet.get("max_hp") or 180) * hp_mult)
        boss_sheet["hp"] = boss_sheet["max_hp"]
        if bonus_pts > 0 and isinstance(boss_sheet.get("stats"), dict):
            boss_sheet["stats"]["STR"] = int(boss_sheet["stats"].get("STR", 3)) + (bonus_pts // 2)
            boss_sheet["stats"]["END"] = int(boss_sheet["stats"].get("END", 3)) + (bonus_pts - bonus_pts // 2)
        boss_sheet["world_scar_buffs"] = scar_buffs

    return encounter_roster, boss_sheet


def _build_intimate_liaison_spec(
    session_id: int,
    raw_tag: str,
    target_name: str,
    target_gender: str,
    climax_location: str,
) -> Dict[str, Any]:
    """Enforces genealogy/incest block, biological invariants, consensual D/s wager framing, and privacy gates."""
    import db
    player_char = db.get_session_player_character(session_id) if session_id else None
    player_gender = normalize_gender((player_char or {}).get("gender") or "male")
    part_gender = normalize_gender(target_gender or "female")

    raw_low = str(raw_tag or "").lower()
    is_dom_wager = any(w in raw_low for w in ("domination", "subjugation"))
    is_secret_affair = ("secret affair" in raw_low) or ("#secretaffair" in raw_low) or ("affair" in raw_low)
    desired_act = "anal" if "anal" in raw_low else ("oral" if "oral" in raw_low else "intercourse")
    raw_dir = "give" if player_gender == "male" else "receive"
    safe_direction = enforce_biological_invariants(
        gender=player_gender,
        act_type=desired_act,
        direction=raw_dir,
        partner_gender=part_gender,
    )

    if _is_incestuous_with_player(session_id, target_name):
        raise ValueError(f"Incest invariant blocked INTIMATE_LIAISON target '{target_name}'.")

    return {
        "target_npc": target_name,
        "target_gender": part_gender,
        "player_gender": player_gender,
        "act_type": desired_act,
        "direction": safe_direction,
        "framing": "consensual_wager_or_ds" if is_dom_wager else "mutual_passion",
        "hard_non_consent_fails_immediately": True,
        "suppress_mid_act_waypoints": True,
        "evaluation_mode": "silent_post_act",
        "is_secret_affair": is_secret_affair,
        "requires_discreet_venue": True,
        "preferred_venue": climax_location,
        "walk_in_salvage": {
            "one_shot": True,
            "allowed_approaches": ["CHA", "AGI", "BRIBE"],
            "bribe_gold": 35,
            "scandal_scar_on_fail": True,
        },
    }


def populate_stage_clue_sources(
    session_id: int,
    quest_id: str,
    stage: Dict[str, Any],
    *,
    climax_loc: str = "",
    leads_graph: Optional[List[Dict[str, Any]]] = None,
    candidate_rooms: Optional[List[str]] = None,
    candidate_npcs: Optional[List[str]] = None,
    used_room_leaves: Optional[Set[str]] = None,
    danger_tier: int = 1,
    lang: str = "en",
    scen_key: str = "",
) -> Dict[str, Any]:
    """Ensures an active or fresh non-climax stage has `completion_trigger='key_clue'` and >=3 clue_sources in distinct safe rooms."""
    from mechanics.narrative.chapter_plan import (
        build_chapter_plan_candidates,
        build_clue_source_prose,
    )

    st = dict(stage)
    if st.get("is_climax_stage"):
        return st

    def _leaf(loc_str: Any) -> str:
        raw = str(loc_str or "").strip()
        if "➔" in raw:
            return raw.split("➔")[-1].strip().lower()
        if "->" in raw:
            return raw.split("->")[-1].strip().lower()
        return raw.lower()

    climax_leaf = _leaf(climax_loc)
    eff_lang = normalize_quest_locale(lang)
    eff_danger = max(1, int(danger_tier or 1))
    st_idx = int(st.get("stage_index") or 1)
    bc = dict(st.get("beat_contract") or {})

    existing_kc = st.get("key_clue") if isinstance(st.get("key_clue"), dict) else {}
    kc_title = str(existing_kc.get("title") or bc.get("handover") or st.get("stage_label") or st.get("label") or f"Critical Evidence {st_idx}").strip()
    kc_lead = str(existing_kc.get("lead_text") or bc.get("reveal") or st.get("stage_label") or kc_title).strip()
    kc_cat = str(existing_kc.get("category") or ("witness" if st.get("target_npc") else "document")).strip()
    kc_id = str(existing_kc.get("clue_id") or f"{quest_id}-KC-{st_idx}").strip()
    st["key_clue"] = {"clue_id": kc_id, "title": kc_title, "lead_text": kc_lead, "category": kc_cat}
    st["completion_trigger"] = "key_clue"

    def _valid_room(loc_str: str) -> bool:
        s = str(loc_str or "").strip()
        if not s:
            return False
        lf = _leaf(s)
        if not lf or (climax_leaf and lf == climax_leaf):
            return False
        return not is_safe_sanctuary_location(s)

    cands = (
        {"rooms": list(candidate_rooms), "npcs": list(candidate_npcs or [])}
        if candidate_rooms is not None
        else build_chapter_plan_candidates(session_id, {"climax_spec": {"location": climax_loc}}, climax_location=climax_loc)
    )
    pool_rooms: List[str] = []
    seen_pool: Set[str] = set()

    def _push_room(raw_r: Any) -> None:
        r = str(raw_r or "").strip()
        if not _valid_room(r):
            return
        lf = _leaf(r)
        if lf not in seen_pool:
            seen_pool.add(lf)
            pool_rooms.append(r)

    for r in (cands.get("rooms") or []):
        _push_room(r)
    for ld in (leads_graph or []):
        if isinstance(ld, dict):
            _push_room(ld.get("target_location"))
            _push_room(ld.get("lead_loc"))

    # Anchor prefix from climax or first non-sanctuary room so synthesized fallbacks fit the district
    zone_prefix = ""
    for probe in [str(st.get("target_location") or ""), *(pool_rooms[:1]), str(climax_loc or "")]:
        if "➔" in probe:
            zone_prefix = probe.rsplit("➔", 1)[0].strip() + " ➔ "
            break
    for suffix in (
        "North Archive Annex",
        "Freight Manifest Office",
        "Signal Watchpost",
        "Backstreet Exchange",
        "Harbor Customs Desk",
        "Underpass Lockbox",
    ):
        if len(pool_rooms) >= 6:
            break
        _push_room(f"{zone_prefix}{suffix}")

    existing_sources = [dict(s) for s in (st.get("clue_sources") or []) if isinstance(s, dict) and _valid_room(str(s.get("location") or ""))]
    stage_leaves: Set[str] = {_leaf(s.get("location")) for s in existing_sources if _leaf(s.get("location"))}

    def _pick_room(preferred: str = "") -> str:
        pref_clean = str(preferred or "").strip()
        if pref_clean and _valid_room(pref_clean):
            pref_is_bare_zone = (
                "➔" not in pref_clean
                and "->" not in pref_clean
                and any(
                    pref_clean.lower() == str(r).split("➔")[0].split("->")[0].strip().lower()
                    for r in pool_rooms
                )
            )
            lf = _leaf(pref_clean)
            if not pref_is_bare_zone and lf not in stage_leaves:
                stage_leaves.add(lf)
                if used_room_leaves is not None:
                    used_room_leaves.add(lf)
                return pref_clean
        # Prefer rooms not yet used on earlier stages first
        if used_room_leaves is not None:
            for cand in pool_rooms:
                lf = _leaf(cand)
                if lf not in stage_leaves and lf not in used_room_leaves:
                    stage_leaves.add(lf)
                    used_room_leaves.add(lf)
                    return cand
        for cand in pool_rooms:
            lf = _leaf(cand)
            if lf not in stage_leaves:
                stage_leaves.add(lf)
                if used_room_leaves is not None:
                    used_room_leaves.add(lf)
                return cand
        fallback = f"{zone_prefix}Sector Alcove {len(stage_leaves) + 1}"
        stage_leaves.add(_leaf(fallback))
        return fallback

    if len(existing_sources) >= 3 and len(stage_leaves) >= 3:
        st["clue_sources"] = existing_sources
        if not _valid_room(str(st.get("target_location") or "")):
            st["target_location"] = existing_sources[0]["location"]
        return st

    t_npc = str(st.get("target_npc") or "").strip()
    witness_npc = t_npc
    if not witness_npc:
        for c_npc in (cands.get("npcs") or []):
            if str(c_npc or "").strip():
                witness_npc = str(c_npc).strip()
                break
    if not witness_npc:
        witness_npc, _, _ = _pick_safe_npc_name(
            session_id,
            scen_key or "modern_urban",
            f"clue_witness:{quest_id}:{st_idx}",
            avoid_low=set(),
        )

    plan_slots = (
        [("witness", t_npc or witness_npc, "CHA"), ("record", "", "INT"), ("item", "", "PER")]
        if t_npc
        else [("record", "", "PER"), ("item", "", "INT"), ("witness", witness_npc, "CHA")]
    )
    used_kinds = {str(s.get("kind") or "").lower() for s in existing_sources}
    for s_i, (kind, s_npc, s_stat) in enumerate(plan_slots):
        if len(existing_sources) >= 3:
            break
        if existing_sources and kind in used_kinds:
            continue
        pref = str(st.get("target_location") or "") if len(existing_sources) == 0 else ""
        s_loc = _pick_room(pref)
        eff_npc = str(s_npc or "") if kind == "witness" else ""
        verb_txt, rev_txt = build_clue_source_prose(
            kind=kind,
            location=s_loc,
            clue_title=kc_title,
            npc_name=eff_npc,
            lang=eff_lang,
        )
        existing_sources.append(
            {
                "source_id": f"S{st_idx}-{len(existing_sources) + 1}",
                "kind": kind,
                "location": s_loc,
                "npc_name": eff_npc,
                "approach_hint": verb_txt,
                "discovery_text": rev_txt,
                "stat": s_stat,
                "dc_offset": 0 if len(existing_sources) == 0 else (-1 if len(existing_sources) == 1 else 1),
                "approaches": build_engine_lead_approaches([s_stat, "PER", "INT"], danger_tier=eff_danger),
                "status": "open",
                "bonus": False,
            }
        )
        used_kinds.add(kind)

    cur_tloc = str(st.get("target_location") or "").strip()
    cur_tloc_is_bare_zone = (
        bool(cur_tloc)
        and "➔" not in cur_tloc
        and "->" not in cur_tloc
        and any(cur_tloc.lower() == str(r).split("➔")[0].split("->")[0].strip().lower() for r in pool_rooms)
    )
    if existing_sources and (not _valid_room(cur_tloc) or cur_tloc_is_bare_zone):
        st["target_location"] = existing_sources[0]["location"]

    # Safety loop in case existing_sources already covered 1..2 kinds and still < 3
    extra_idx = 0
    while len(existing_sources) < 3:
        extra_idx += 1
        kind = "item" if extra_idx % 2 == 1 else "record"
        s_stat = "PER" if kind == "item" else "INT"
        s_loc = _pick_room("")
        verb_txt, rev_txt = build_clue_source_prose(
            kind=kind,
            location=s_loc,
            clue_title=kc_title,
            npc_name="",
            lang=eff_lang,
        )
        existing_sources.append(
            {
                "source_id": f"S{st_idx}-{len(existing_sources) + 1}",
                "kind": kind,
                "location": s_loc,
                "npc_name": "",
                "approach_hint": verb_txt,
                "discovery_text": rev_txt,
                "stat": s_stat,
                "dc_offset": 1,
                "approaches": build_engine_lead_approaches([s_stat, "PER", "INT"], danger_tier=eff_danger),
                "status": "open",
                "bonus": False,
            }
        )

    st["clue_sources"] = existing_sources
    st["target_location"] = existing_sources[0]["location"]
    return st


def validate_and_repair_dossier(session_id: int, dossier: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and repairs a QuestDossier before persistence:
    - Asserts 0 placeholder tokens (_PLACEHOLDER_ACTOR_RE).
    - Protects friendly contacts from becoming hostile target_npc.
    - Enforces >=3 stages for story quests with smart mid-stage splicing.
    - Ensures all main stages carry complete beat_contract.
    - Sanitizes secret climax venue leaks in Optional titles and targets.
    """
    if not isinstance(dossier, dict):
        return {}

    from mechanics.narrative.campaign_spine import _SCENARIO_BACKUP_NAMES
    dos = dict(dossier)
    qid = str(dos.get("quest_id") or "")
    family_tier = str(dos.get("family_tier") or "bounty")
    scen_key = str(dos.get("scenario") or "fantasy")
    if session_id:
        import db
        sess = db.get_session(session_id) or {}
        scen_key = str(sess.get("scenario") or scen_key or "fantasy")
    backups = _SCENARIO_BACKUP_NAMES.get(scen_key, _SCENARIO_BACKUP_NAMES["fantasy"])

    climax = dict(dos.get("climax_spec") or {})
    leads = [dict(l) for l in (dos.get("leads_graph") or [])]
    cast = dict(dos.get("cast_bindings") or {})
    main_stages = [dict(s) for s in (climax.get("main_stages") or [])]

    # 1. Target & Informant Placeholders & Friendly Protection
    protected_low = get_protected_quest_cast_names(session_id) if session_id else set()
    cur_target = str(dos.get("target_npc") or climax.get("true_culprit") or climax.get("target_npc") or (cast.get("target") or {}).get("name") or "").strip()

    needs_target_replace = (
        not cur_target
        or bool(_PLACEHOLDER_ACTOR_RE.search(cur_target))
        or (cur_target.lower() in protected_low and family_tier not in ("story", "loyalty") and str(dos.get("engine") or "").upper() != "INTIMATE_LIAISON")
    )
    if needs_target_replace:
        avoid = set(protected_low)
        if session_id:
            try:
                import db
                p_char = db.get_session_player_character(session_id)
                if p_char and p_char.get("name"):
                    avoid.add(str(p_char["name"]).strip().lower())
            except Exception:
                pass
        new_target, _, _ = _pick_safe_npc_name(session_id, scen_key, f"repair_tgt:{qid}", avoid_low=avoid)
        if _PLACEHOLDER_ACTOR_RE.search(new_target) or new_target.lower() in protected_low:
            new_target = backups[0]
        dos["target_npc"] = new_target
        climax["true_culprit"] = new_target
        climax["target_npc"] = new_target
        if "target" in cast and isinstance(cast["target"], dict):
            cast["target"]["name"] = new_target
        for ms in main_stages:
            if ms.get("is_climax_stage") or str(ms.get("target_npc") or "").lower() == cur_target.lower():
                ms["target_npc"] = new_target
        cur_target = new_target

    cur_informant = str(dos.get("informant_npc") or (cast.get("informant") or {}).get("name") or "").strip()
    if cur_informant and _PLACEHOLDER_ACTOR_RE.search(cur_informant):
        new_inf, _, _ = _pick_safe_npc_name(session_id, scen_key, f"repair_inf:{qid}", avoid_low={cur_target.lower()})
        dos["informant_npc"] = new_inf
        if "informant" in cast and isinstance(cast["informant"], dict):
            cast["informant"]["name"] = new_inf
        cur_informant = new_inf

    # 2. Main Stage Count (>= 3 for Story Quests)
    climax_loc = str(climax.get("location") or "")
    if family_tier == "story" and len(main_stages) < 3 and not climax.get("completed"):
        st1 = dict(main_stages[0]) if main_stages else {"stage_index": 1, "status": "active", "label": "Initial investigation"}
        old_climax = dict(main_stages[-1]) if len(main_stages) >= 2 else {"stage_index": 2, "status": "locked", "label": "Confrontation", "target_location": climax_loc, "is_climax_stage": True}
        st1_loc = str(st1.get("target_location") or "")
        mid_loc = ""
        if session_id:
            try:
                import db
                with db.get_conn() as _conn:
                    node = _conn.execute(
                        "SELECT name FROM world_nodes WHERE session_id=? AND node_type='ROOM' AND name NOT IN (?, ?) LIMIT 1",
                        (session_id, st1_loc, climax_loc),
                    ).fetchone()
                    if node and node[0]:
                        mid_loc = str(node[0])
            except Exception:
                pass
        if not mid_loc:
            mid_loc = str(leads[0].get("target_location") if leads else f"Relay Sub-Node of {format_short_venue_display(climax_loc)}")

        st1_done = bool(st1.get("completed") or str(st1.get("status") or "").lower() in ("completed", "bypassed"))
        new_st2 = {
            "stage_index": 2,
            "stage_label": f"Infiltrate supply relay at {format_short_venue_display(mid_loc)}",
            "label": f"Infiltrate supply relay at {format_short_venue_display(mid_loc)}",
            "target_location": mid_loc,
            "target_npc": "",
            "completion_trigger": "action",
            "approaches": ["STR", "INT", "CHA"],
            "status": "active" if st1_done else "locked",
            "completed": False,
            "is_climax_stage": False,
            "beat_contract": {
                "player_verb": f"Breach relay at {format_short_venue_display(mid_loc)}",
                "reveal": f"Telemetry logs pinpoint headquarters at {format_short_venue_display(climax_loc)}",
                "handover": "Relay access cipher",
                "next_pointer": format_short_venue_display(climax_loc),
                "is_dialogue_beat": False,
            },
        }
        old_climax["stage_index"] = 3
        old_climax["status"] = "locked"
        old_climax["completed"] = False
        main_stages = [st1, new_st2, old_climax]
        climax["main_stages"] = main_stages
        climax["main_stage_count"] = 3
        if str(climax.get("gate_type") or "").lower() == "secret":
            climax["is_unlocked"] = False

    # 3. Ensure Complete beat_contract on all Main Stages
    tot_st = len(main_stages)
    for idx_ms, ms in enumerate(main_stages):
        if not ms.get("beat_contract") or not isinstance(ms.get("beat_contract"), dict):
            ms_loc = format_short_venue_display(str(ms.get("target_location") or climax_loc))
            nxt_loc = format_short_venue_display(str(main_stages[min(tot_st - 1, idx_ms + 1)].get("target_location") or climax_loc))
            ms["beat_contract"] = {
                "player_verb": f"Investigate {ms_loc}",
                "reveal": f"Leads confirm operations at {nxt_loc}",
                "handover": "Operational dispatch logs",
                "next_pointer": nxt_loc,
                "is_dialogue_beat": bool(ms.get("target_npc")),
            }

    # 4. Optional Climax Venue & Title Leak Sanitization
    climax_short = format_short_venue_display(climax_loc)
    for ld in leads:
        lead_tgt = str(ld.get("target_location") or "")
        if lead_tgt == climax_loc or not lead_tgt or is_safe_sanctuary_location(lead_tgt):
            sub_alt = str(ld.get("lead_loc") or "")
            if not sub_alt or sub_alt == climax_loc or is_safe_sanctuary_location(sub_alt):
                sub_alt = "District Forward Post"
            ld["target_location"] = sub_alt
        lead_short = format_short_venue_display(str(ld.get("target_location") or "District"))
        for k_title in ("title", "label"):
            if k_title in ld and ld[k_title]:
                t_str = str(ld[k_title])
                if climax_loc and climax_loc in t_str:
                    t_str = t_str.replace(climax_loc, lead_short)
                if climax_short and climax_short in t_str:
                    t_str = t_str.replace(climax_short, lead_short)
                ld[k_title] = t_str

    # 5. Clue-Based Stage Sources & Threat Clock Repair
    from mechanics.narrative.chapter_plan import build_chapter_plan_candidates, is_clue_based_quest
    from mechanics.narrative.threat_clock import build_initial_threat_clock
    import db as _db_rep

    eff_engine = str(dos.get("engine") or "")
    sess_rep = _db_rep.get_session(session_id) or {} if session_id else {}
    eff_lang_rep = normalize_quest_locale(sess_rep.get("narration_language") or sess_rep.get("language") or "en")
    eff_scen_rep = str(sess_rep.get("scenario") or "")
    eff_danger_rep = max(1, int(dos.get("danger_tier") or 1))
    if family_tier == "story" and not isinstance(climax.get("threat_clock"), dict):
        climax["threat_clock"] = build_initial_threat_clock(
            chapter=int(climax.get("chapter") or sess_rep.get("chapter") or 1),
            endless_mode_unlocked=bool(sess_rep.get("endless_mode_unlocked")),
        )
    if is_clue_based_quest(family_tier, eff_engine) and not climax.get("completed"):
        cands_rep = build_chapter_plan_candidates(session_id, dos, climax_location=climax_loc)
        used_leaves_rep: Set[str] = set()
        repaired_stages: List[Dict[str, Any]] = []
        for ms in main_stages:
            is_done = bool(ms.get("completed") or str(ms.get("status") or "").lower() in ("completed", "bypassed"))
            if is_done or ms.get("is_climax_stage"):
                repaired_stages.append(ms)
                continue
            cur_srcs = [s for s in (ms.get("clue_sources") or []) if isinstance(s, dict)]
            if str(ms.get("completion_trigger") or "") != "key_clue" or len(cur_srcs) < 3:
                repaired_stages.append(
                    populate_stage_clue_sources(
                        session_id,
                        qid,
                        ms,
                        climax_loc=climax_loc,
                        leads_graph=leads,
                        candidate_rooms=cands_rep.get("rooms"),
                        candidate_npcs=cands_rep.get("npcs"),
                        used_room_leaves=used_leaves_rep,
                        danger_tier=eff_danger_rep,
                        lang=eff_lang_rep,
                        scen_key=eff_scen_rep,
                    )
                )
            else:
                repaired_stages.append(ms)
        climax["main_stages"] = repaired_stages

    dos["cast_bindings"] = cast
    dos["climax_spec"] = climax
    dos["leads_graph"] = leads
    return dos


def compile_quest_dossier(
    session_id: int,
    quest_id: str,
    tag_or_archetype: str = "",
    title: str = "",
    objective: str = "",
    family_tier: str = "",
    danger_tier: int = 1,
    chapter: int = 1,
    turn_number: int = 0,
    client_npc: str = "",
    target_npc: str = "",
    informant_npc: str = "",
    preferred_location: str = "",
    required_item: str = "",
    reward_gold: int = 50,
    scen_key: str = "",
    lang: str = "",
    status_stage: str = "compiled",
) -> Dict[str, Any]:
    """
    Deterministically compiles a complete Stage-2 `QuestDossier` in `<20ms`, enforcing:
    - Protected-cast & Tier-3 spatial room de-confliction
    - Non-linear multi-approach leads (`leads_graph`)
    - Party-scaled `encounter_roster` + Climax `boss_sheet`
    - Deterministic Caseboard `clue_graph` + Private vs. Formal Accusation truth
    - ~70/30 Bounty Twist roll + `2x` hush-money blackmail & side-switching
    - Tangible `[ITEM_JSON]`/`[GEAR_JSON]` MacGuffin lock + Context-Smart Turn-In
    - NSFW `INTIMATE_LIAISON` genealogy, biological, consensual-wager, & salvage rules
    """
    import db
    sess = db.get_session(session_id) if session_id else {}
    sess = sess or {}
    eff_scen = str(scen_key or sess.get("scenario") or "fantasy")
    eff_lang = normalize_quest_locale(lang or sess.get("narration_language") or sess.get("language") or "en")
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    eff_chapter = max(1, int(chapter or sess.get("current_chapter") or 1))

    existing_q = db.get_quest_by_id(session_id, quest_id) if session_id else None
    existing_dos = db.get_quest_dossier(session_id, quest_id) if session_id else None
    stub = (existing_dos or {}).get("pitch_stub") or {}

    eff_family = family_tier or infer_quest_family_tier(
        quest_id,
        quest_type=(existing_q or {}).get("quest_type", ""),
        is_story_quest=bool((existing_q or {}).get("is_story_quest")),
        quest_notes=(existing_q or {}).get("quest_notes", ""),
    )

    raw_arch = tag_or_archetype or stub.get("raw_archetype") or (existing_q or {}).get("quest_type") or "Investigation"
    eff_obj = objective or stub.get("public_pitch") or (existing_q or {}).get("objective") or ""
    eff_title = title or stub.get("title") or (existing_q or {}).get("title") or "Active Contract"
    eff_danger = max(1, min(5, int(danger_tier or stub.get("danger_tier") or max(1, (eff_chapter + 1) // 2))))

    is_nsfw_scen = bool(scenario_data.has_tag(eff_scen, "nsfw") or scenario_data.uses_nsfw_model(eff_scen))
    eng_info = resolve_quest_engine(raw_arch, eff_obj, is_nsfw_scenario=is_nsfw_scen)
    extra_nsfw_ctx = f"{(existing_q or {}).get('quest_type') or ''} {stub.get('raw_archetype') or ''}".lower().strip()
    if stub.get("uses_nsfw_routing") or any(kw in extra_nsfw_ctx for kw in (load_quest_engines_catalog().get("hybrid_nsfw_keywords") or [])):
        eng_info["uses_nsfw_routing"] = True
    engine = eng_info["engine"]

    protected_low = get_protected_quest_cast_names(session_id) if session_id else set()
    avoid_set: Set[str] = set(protected_low)
    if session_id:
        p_char = db.get_session_player_character(session_id)
        if p_char and p_char.get("name"):
            avoid_set.add(str(p_char["name"]).strip().lower())

    for_intimate = engine == "INTIMATE_LIAISON"
    is_target_valid = (
        bool(target_npc)
        and not (for_intimate and _is_incestuous_with_player(session_id, target_npc))
        and (target_npc.lower() not in protected_low or for_intimate or family_tier in ("story", "loyalty"))
        and not _PLACEHOLDER_ACTOR_RE.search(target_npc)
    )
    if is_target_valid:
        eff_target = target_npc
        target_gender = "female"
        target_cid = None
    else:
        eff_target, target_gender, target_cid = _pick_safe_npc_name(
            session_id, eff_scen, f"target:{quest_id}", avoid_set, for_intimate=for_intimate
        )
    avoid_set.add(eff_target.lower())

    eff_client = client_npc or stub.get("client_npc") or (existing_q or {}).get("client_npc") or ""
    if not eff_client or _PLACEHOLDER_ACTOR_RE.search(eff_client):
        eff_client, _, client_cid = _pick_safe_npc_name(session_id, eff_scen, f"client:{quest_id}", avoid_set)
    else:
        client_cid = None
    avoid_set.add(eff_client.lower())

    if informant_npc and informant_npc.lower() not in avoid_set and not _PLACEHOLDER_ACTOR_RE.search(informant_npc):
        eff_informant = informant_npc
        informant_cid = None
    else:
        eff_informant, _, informant_cid = _pick_safe_npc_name(session_id, eff_scen, f"informant:{quest_id}", avoid_set)
    avoid_set.add(eff_informant.lower())

    eff_accomplice, _, accomplice_cid = _pick_safe_npc_name(session_id, eff_scen, f"accomplice:{quest_id}", avoid_set)

    pref_loc = preferred_location or stub.get("client_location") or (existing_q or {}).get("client_location") or sess.get("current_location") or "Central District"
    climax_loc, climax_node_id = select_deconflicted_climax_location(
        session_id, pref_loc, family_tier=eff_family, objective_hint=f"{eff_title} {eff_obj}", scen_key=eff_scen,
    )
    # Optional Leads use a distinct room from the Climax whenever another valid room exists.
    lead_loc, _lead_nid = select_deconflicted_climax_location(
        session_id, "", family_tier=f"lead:{eff_family}", objective_hint=f"{eff_title} {eff_obj}",
        extra_exclude={climax_loc}, scen_key=eff_scen,
    )
    if not lead_loc or lead_loc == "District Inner Chamber" or lead_loc == climax_loc or is_safe_sanctuary_location(lead_loc):
        lead_loc = ""
        if session_id:
            try:
                with db.get_conn() as _conn:
                    nodes = _conn.execute(
                        "SELECT name FROM world_nodes WHERE session_id=? AND node_type='ROOM' AND name NOT IN (?, ?)",
                        (session_id, climax_loc, pref_loc),
                    ).fetchall()
                    for n_row in nodes:
                        cand_name = str(n_row[0] or "")
                        if cand_name and not is_safe_sanctuary_location(cand_name):
                            lead_loc = cand_name
                            break
            except Exception:
                pass
        if not lead_loc:
            lead_loc = pref_loc if (pref_loc and pref_loc != climax_loc and not is_safe_sanctuary_location(pref_loc)) else "District Forward Post"

    cast_bindings = {
        "client": {"name": eff_client, "contact_id": client_cid, "status": "alive", "fallback_on_death": "contract_void_or_successor"},
        "target": {"name": eff_target, "contact_id": target_cid, "gender": target_gender, "status": "alive", "plot_armor": False},
        "informant": {"name": eff_informant, "contact_id": informant_cid, "status": "alive", "fallback_on_death": "lootable_cipher_or_room_search"},
        "accomplice": {"name": eff_accomplice, "contact_id": accomplice_cid, "status": "alive", "is_red_herring_suspect": True},
    }

    encounter_roster, boss_sheet = _build_combat_rosters_for_dossier(
        session_id=session_id,
        scen_key=eff_scen,
        engine=engine,
        family_tier=eff_family,
        danger_tier=eff_danger,
        chapter=eff_chapter,
        climax_location=climax_loc,
        target_name=eff_target,
        lang=eff_lang,
    )
    if isinstance(boss_sheet, dict) and existing_q:
        boss_sheet = hydrate_boss_sheet_from_quest_blueprint(boss_sheet, existing_q)

    catalog = load_quest_engines_catalog()
    lead_tmpls = ((catalog.get("engines") or {}).get(engine) or {}).get("lead_templates") or []

    spine = compile_or_get_campaign_spine(session_id, scen_key=eff_scen, lang=eff_lang) if (session_id and eff_family == "story") else (db.get_campaign_spine(session_id) if session_id else None)
    hb = (spine or {}).get("hidden_bible") or {}
    tri_cfg = hb.get("faction_triangle") or {}
    order_slug = str((tri_cfg.get("order") or {}).get("slug") or "order_pillar")
    reform_slug = str((tri_cfg.get("reform") or {}).get("slug") or "reform_pillar")
    shadow_slug = str((tri_cfg.get("shadow") or {}).get("slug") or "shadow_pillar")

    is_peak_story = bool(eff_family == "story" and eff_chapter in PEAK_CHAPTERS)
    main_stage_count = (4 if is_peak_story else 3) if eff_family == "story" else (3 if is_peak_story else 2)
    inner_ally = _pick_inner_circle_ally(session_id) if (eff_family == "story" and eff_chapter in (6, 9)) else ""

    # Determine Optional Objective count:
    # - `dispatch` / `rumor` / `minor` / `micro` (`RMR-`, `MNR-`, `MAND-`): 1 Optional
    # - Peak Story (`Ch. 3, 6, 8, 9, 10`): 2..3 Optionals
    # - Buildup Story / Full Bounty / Companion Loyalty (`CLR-`): 1..3 Optionals
    qid_up = str(quest_id or "").strip().upper()
    if eff_family in ("dispatch", "rumor", "minor", "micro") or qid_up.startswith(("RMR-", "MNR-", "MAND-")):
        opt_count = 1
    elif eff_family == "story" and eff_chapter == 11:
        opt_count = 1 + _det_int(f"opt_cnt:{session_id}:{quest_id}", 2)  # 1..2
    elif is_peak_story:
        opt_count = 2 + _det_int(f"opt_cnt:{session_id}:{quest_id}", 2)  # 2..3
    else:
        opt_count = 1 + _det_int(f"opt_cnt:{session_id}:{quest_id}", 3)  # 1..3

    # Select typed Optional roles (`aid`, `bypass`, `alternative`, `threatened`)
    use_threatened = bool(
        (eff_family == "story" and eff_chapter in (3, 8, 9))
        or (engine == "CRISIS_DEFENSE" and eff_danger >= 3 and opt_count >= 2)
    )
    role_plan: List[str] = []
    if opt_count == 1:
        role_plan = ["threatened" if (eff_family == "story" and eff_chapter == 9) else ("aid" if _det_int(f"r1:{quest_id}", 2) == 0 else "bypass")]
    elif opt_count == 2:
        if use_threatened:
            role_plan = ["threatened", "alternative" if engine != "INTIMATE_LIAISON" else "aid"]
        else:
            role_plan = ["aid", "bypass" if _det_int(f"r2:{quest_id}", 2) == 0 else "alternative"]
    else:
        if use_threatened:
            role_plan = ["aid", "threatened", "alternative"]
        else:
            role_plan = ["aid", "bypass", "alternative"]

    if engine == "INTIMATE_LIAISON":
        role_plan = ["aid" if r == "alternative" else r for r in role_plan]

    unlock_triggers = ("clue_found", "npc_dialogue", "incoming_comms")
    opt_venue_short = format_short_venue_display(lead_loc) or lead_loc
    gate_mode = str(eng_info.get("climax_gate_mode") or "open")
    masked_target_opt = eff_target
    if gate_mode == "secret":
        masked_target_opt = {
            "en": "the target's vanguard",
            "pl": "straży przedniej celu",
            "ms": "barisan hadapan sasaran",
            "zh": "目标的先遣爪牙",
            "de": "der Vorhut des Ziels",
        }.get(eff_lang, "the target's vanguard")

    opt_slots = {
        "client": eff_client,
        "target": masked_target_opt,
        "informant": inner_ally if (use_threatened and inner_ally) else eff_informant,
        "accomplice": eff_accomplice,
        "venue": opt_venue_short,
        "zone": lead_loc.split("➔")[0].strip() if "➔" in lead_loc else lead_loc,
    }

    leads_graph: List[Dict[str, Any]] = []
    for idx, opt_role in enumerate(role_plan):
        sub_obj_id = idx + 1
        lt = lead_tmpls[idx % len(lead_tmpls)] if lead_tmpls else {}
        rendered_opt = render_optional_objective_template(opt_role, opt_slots, lang=eff_lang)

        # Hybrid Discovery: `1-2` upfront tactical Optionals (`is_discovered=True`);
        # `alternative` (when >=2 optionals exist) starts hidden (`is_discovered=False`) to be uncovered mid-quest!
        is_secret_opt = bool(opt_count >= 2 and opt_role == "alternative" and idx >= 1)
        is_discovered = not is_secret_opt
        trig = "upfront" if is_discovered else unlock_triggers[_det_int(f"utrig:{quest_id}:{idx}", len(unlock_triggers))]

        if opt_role == "aid" and lt.get("labels"):
            lbl_map = lt.get("labels") or {}
            raw_lbl = str(lbl_map.get(eff_lang) or lbl_map.get("en") or rendered_opt["label"])
            opt_label = raw_lbl.format(
                venue=opt_venue_short,
                informant=eff_informant,
                target=masked_target_opt,
                client=eff_client,
            )
        else:
            opt_label = rendered_opt["label"]

        role_stats = (
            list(lt.get("stats") or ["PER", "STR", "INT"])
            if opt_role == "aid"
            else (
                ["AGI", "INT", "BRIBE"]
                if opt_role == "bypass"
                else (["CHA", "INT", "BRIBE"] if opt_role == "alternative" else ["END", "STR", "CHA"])
            )
        )
        is_combat_lead = bool(idx == 0 and encounter_roster)
        opt_target_npc = (
            (inner_ally or eff_informant)
            if opt_role == "threatened"
            else (eff_accomplice if opt_role == "alternative" else (eff_informant if idx == 0 else eff_target))
        )

        rival_slug = ""
        opposing_slug = ""
        if opt_role == "aid":
            rival_slug = order_slug
        elif opt_role == "alternative":
            rival_slug = shadow_slug if _det_int(f"rfac:{quest_id}", 2) == 0 else reform_slug
            opposing_slug = order_slug

        leads_graph.append(
            {
                "lead_id": f"{quest_id}-L{sub_obj_id}",
                "optional_id": f"{quest_id}-OPT{sub_obj_id}",
                "sub_obj_id": sub_obj_id,
                "is_optional": True,
                "title": opt_label,
                "label": opt_label,
                "role": opt_role,
                "badge": rendered_opt["badge"],
                "stakes_hint": rendered_opt["stakes_hint"],
                "target_npc": "" if any(kw in opt_label.lower() for kw in ("inspect physical", "traces", "search site", "examine")) else opt_target_npc,
                "target_location": lead_loc,
                "follow_npc_schedule": 0 if any(kw in opt_label.lower() for kw in ("inspect physical", "traces", "search site", "examine")) else int(bool(opt_target_npc)),
                "approaches": build_engine_lead_approaches(
                    role_stats,
                    danger_tier=eff_danger,
                    allow_curfew_stealth=(engine != "INTIMATE_LIAISON"),
                ),
                "encounter_roster": list(encounter_roster) if is_combat_lead else [],
                "roster_scouted": False,
                "roster_cleared": False,
                "status": "active",
                "is_discovered": is_discovered,
                "unlock_trigger": trig,
                "field_bonus": {
                    "xp": max(25, 15 * eff_danger),
                    "gold": max(10, int(round((reward_gold or 40) * 0.20))) if opt_role == "alternative" else 0,
                    "affinity": 5 if opt_target_npc else 0,
                },
                "bonus_claimed": False,
                "rival_faction_slug": rival_slug,
                "opposing_faction_slug": opposing_slug,
                "implicated_ally_npc": inner_ally if opt_role == "threatened" else "",
                "fair_jeopardy_on_screen_only": bool(opt_role == "threatened" and inner_ally),
                "is_inner_circle_rescue": bool(opt_role == "threatened" and inner_ally),
                "lockout_reason": "",
                "supports_phone_lure": bool(engine in ("SOCIAL_BROKERAGE", "INTIMATE_LIAISON", "MYSTERY_CASE")),
            }
        )

    twist_prob = 0.70 if eff_family == "bounty" else (0.55 if eff_family in ("story", "loyalty") else 0.40)
    twist_spec = roll_dossier_twist_spec(
        seed_key=f"{session_id}:{quest_id}",
        engine=engine,
        slots={"client": eff_client, "target": eff_target, "informant": eff_informant, "accomplice": eff_accomplice},
        lang=eff_lang,
        twist_probability=twist_prob,
    )

    true_culprit = eff_client if twist_spec.get("twist_type") == "client_culprit" else (
        eff_accomplice if twist_spec.get("twist_type") == "framed_target" else eff_target
    )
    innocent_suspect = eff_target if true_culprit != eff_target else eff_accomplice

    clue_graph = [
        {
            "clue_key": f"{quest_id}_clue_1",
            "clue_id": None,
            "title": f" Ledger Trace at {climax_loc.split('➔')[-1].strip()}",
            "lead_text": f"Physical evidence tying recent activity at {climax_loc} to {true_culprit}.",
            "paired_with": [f"{quest_id}_clue_2"],
            "conclusion": f"Confirmed Culprit & Lair: {true_culprit} operating through {climax_loc}.",
            "unlocks_climax": True,
            "reveals_twist": bool(twist_spec.get("has_twist")),
            "is_red_herring": False,
        },
        {
            "clue_key": f"{quest_id}_clue_2",
            "clue_id": None,
            "title": f"Testimony from {eff_informant}",
            "lead_text": f"Corroborating witness account implicating {true_culprit}.",
            "paired_with": [f"{quest_id}_clue_1"],
            "conclusion": f"Confirmed Culprit & Lair: {true_culprit} operating through {climax_loc}.",
            "unlocks_climax": True,
            "reveals_twist": bool(twist_spec.get("has_twist")),
            "is_red_herring": False,
        },
        {
            "clue_key": f"{quest_id}_red_herring",
            "clue_id": None,
            "title": f"Planted Token near {innocent_suspect}",
            "lead_text": f"Superficial clue pointing toward {innocent_suspect}, lacking corroboration.",
            "paired_with": [],
            "conclusion": "",
            "unlocks_climax": False,
            "reveals_twist": False,
            "is_red_herring": True,
        },
    ]

    macguffin_name = str(
        required_item
        or (existing_q or {}).get("required_item")
        or (f"Sealed {eff_title} Relic" if engine in ("ACQUISITION_EXCHANGE", "HEIST_BREACH") else "")
    ).strip()
    has_macguffin = bool(macguffin_name)
    is_equippable_gear = bool(has_macguffin and any(w in macguffin_name.lower() for w in ("blade", "sword", "ring", "amulet", "pistol", "rifle", "cloak", "crown", "staff", "dagger")))
    tangible_item = (
        {
            "has_item": True,
            "name": macguffin_name,
            "item_type": "Accessory" if is_equippable_gear else "Quest Item",
            "envelope_tag": "[GEAR_JSON]" if is_equippable_gear else "[ITEM_JSON]",
            "effect_payload": (
                f'[GEAR_JSON]{{"slot":"Accessory 1","archetype":"amulet","tier":2,"value":{max(60, reward_gold * 2)}}}'
                if is_equippable_gear
                else f'[ITEM_JSON]{{"category":"artifact","tier":2,"value":{max(50, reward_gold * 2)}}}'
            ),
            "is_quest_locked": 1,
            "linked_quest_id": quest_id,
            "fencing_gold": int(max(45, round(reward_gold * 1.5))),
            "disposition": "unclaimed",  # unclaimed | acquired | delivered | kept | consumed | destroyed | fenced
            "pending_retaliation": False,
        }
        if has_macguffin
        else {"has_item": False, "disposition": "none"}
    )

    gate_mode = str(eng_info["climax_gate_mode"])
    origin_loc = str(stub.get("origin_location") or (existing_q or {}).get("client_location") or sess.get("current_location") or climax_loc)
    custom_stg_lbls: list[str] = []
    if existing_q and isinstance(existing_q.get("sub_objectives"), list):
        for so in existing_q["sub_objectives"]:
            if isinstance(so, dict) and so.get("text"):
                custom_stg_lbls.append(str(so["text"]).strip())
    main_stages = _build_main_objective_stages(
        engine=engine,
        family_tier=eff_family,
        chapter=eff_chapter,
        main_stage_count=main_stage_count,
        climax_loc=climax_loc,
        origin_loc=origin_loc,
        target_npc=eff_target,
        informant_npc=eff_informant,
        danger_tier=eff_danger,
        gate_mode=gate_mode,
        inner_circle_ally=inner_ally,
        lang=eff_lang,
        mid_loc=lead_loc,
        custom_stage_labels=custom_stg_lbls if custom_stg_lbls else None,
    )
    from mechanics.narrative.chapter_plan import build_chapter_plan_candidates, is_clue_based_quest
    from mechanics.narrative.threat_clock import build_initial_threat_clock

    if is_clue_based_quest(eff_family, engine):
        cands_comp = build_chapter_plan_candidates(
            session_id,
            {"climax_spec": {"location": climax_loc, "main_stages": main_stages}},
            climax_location=climax_loc,
        )
        used_leaves_comp: Set[str] = set()
        main_stages = [
            populate_stage_clue_sources(
                session_id,
                quest_id,
                st,
                climax_loc=climax_loc,
                leads_graph=leads_graph,
                candidate_rooms=cands_comp.get("rooms"),
                candidate_npcs=cands_comp.get("npcs"),
                used_room_leaves=used_leaves_comp,
                danger_tier=eff_danger,
                lang=eff_lang,
                scen_key=eff_scen,
            )
            if not st.get("is_climax_stage")
            else st
            for st in main_stages
        ]
    climax_spec: Dict[str, Any] = {
        "has_structured_model": True,
        "gate_type": gate_mode,  # open | secret
        "gate_mode": gate_mode,
        "is_unlocked": bool(gate_mode == "open"),
        "is_peak_chapter": is_peak_story,
        "chapter": eff_chapter,
        "main_objective_text": eff_obj or eff_title,
        "label": eff_obj or eff_title,
        "main_stage_count": main_stage_count,
        "main_stages": main_stages,
        "location": climax_loc,
        "target_location": climax_loc,
        "target_npc": eff_target,
        "node_id": climax_node_id,
        "scene_priority": FAMILY_SCENE_PRIORITY.get(eff_family, 3),
        "true_culprit": true_culprit,
        "innocent_suspect": innocent_suspect,
        "is_elimination_strict": bool(eng_info["is_elimination_strict"]),
        "is_final_chapter_boss": bool(eff_family == "story" and eff_chapter == 10 and boss_sheet is not None),
        "boss_sheet": boss_sheet,
        "aid_dc_reduction": 0,
        "aid_ally_striker": "",
        "claimed_aid_factions": [],
        "reinforcements": [],
        # Investigative/social engines keep the boss on reserve for escalation only (outside the Ch.10 finale)
        "boss_escalation_only": bool(
            engine in _INVESTIGATIVE_ENGINES and not (eff_family == "story" and eff_chapter == 10)
        ),
        "escalated": False,
        "rush_un_nerfed_buffs": {"bonus_dt": 4, "reinforce_from_uncleared_leads": True} if gate_mode == "open" else {},
    }
    if eff_family == "story":
        climax_spec["threat_clock"] = build_initial_threat_clock(
            chapter=eff_chapter,
            endless_mode_unlocked=bool(sess.get("endless_mode_unlocked")),
        )
    if engine == "INTIMATE_LIAISON":
        climax_spec["intimacy_spec"] = _build_intimate_liaison_spec(
            session_id=session_id,
            raw_tag=f"{raw_arch} {eff_obj}",
            target_name=eff_target,
            target_gender=target_gender,
            climax_location=climax_loc,
        )

    base_fee = int(reward_gold or (existing_q or {}).get("reward_gold") or stub.get("reward_gold") or 50)
    contract_economy = {
        "base_gold": base_fee,
        "haggled_bonus_gold": 0,
        "upfront_advance_gold": 0,
        "advance_taken": False,
        "bribes_spent_gold": 0,
        "uses_nsfw_routing": bool(eng_info["uses_nsfw_routing"]),
    }

    turn_in_rules = build_turn_in_rules(
        engine=engine,
        has_physical_macguffin=has_macguffin,
        requires_prisoner_handoff=("capture" in eff_obj.lower() or "alive" in eff_obj.lower()),
        twist_spec=twist_spec,
        advance_haggled=False,
    )

    scar_spec = render_world_scar_spec(engine=engine, venue_name=climax_loc, lang=eff_lang)
    scar_spec["scar_tier"] = "peak" if is_peak_story else ("buildup" if eff_family == "story" else "bounty")
    outcomes_matrix = {
        "clean_success": {"gold_multiplier": 1.0, "xp_multiplier": 1.0, "spawns_world_scar": False},
        "twist_resolution": {"gold_multiplier": 1.25, "xp_multiplier": 1.15, "spawns_world_scar": False},
        "alternative_deal": {"gold_multiplier": 1.5, "xp_multiplier": 1.0, "spawns_world_scar": False},
        "partial_success": {
            "gold_multiplier": 0.5,
            "xp_multiplier": 0.75,
            "promotes_escaped_boss_to_nemesis": True,
            "spawns_world_scar": False,
        },
        "failure": {
            "gold_multiplier": 0.0,
            "xp_multiplier": 0.25,
            "spawns_world_scar": True,
            "world_scar": scar_spec,
            "companion_arc_scarred": bool(eff_family == "loyalty"),
            "triggers_hard_game_over": False,
            "routes_to_fallen_world_epilogue": bool(eff_family == "story" and eff_chapter == 10),
        },
    }

    dossier_candidate = {
        "quest_id": quest_id,
        "engine": engine,
        "family_tier": eff_family,
        "danger_tier": eff_danger,
        "scenario": eff_scen,
        "target_npc": eff_target,
        "informant_npc": eff_informant,
        "cast_bindings": cast_bindings,
        "leads_graph": leads_graph,
        "clue_graph": clue_graph,
        "climax_spec": climax_spec,
    }
    validated = validate_and_repair_dossier(session_id, dossier_candidate)
    cast_bindings = validated.get("cast_bindings") or cast_bindings
    leads_graph = validated.get("leads_graph") or leads_graph
    climax_spec = validated.get("climax_spec") or climax_spec

    saved = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engine=engine,
        family_tier=eff_family,
        danger_tier=eff_danger,
        status_stage=status_stage,
        compiled_at_turn=eff_turn,
        pitch_stub=stub or {"quest_id": quest_id, "title": eff_title, "engine": engine, "public_pitch": eff_obj},
        cast_bindings=cast_bindings,
        leads_graph=leads_graph,
        clue_graph=clue_graph,
        climax_spec=climax_spec,
        twist_spec=twist_spec,
        tangible_item=tangible_item,
        contract_economy=contract_economy,
        turn_in_rules=turn_in_rules,
        outcomes_matrix=outcomes_matrix,
    )
    if session_id and existing_q:
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET engine = ?, dossier_stage = ? WHERE session_id = ? AND quest_id = ?",
                (engine, status_stage, session_id, quest_id),
            )
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved, conn=conn)
    return saved or {}


def compile_micro_dossier(
    session_id: int,
    quest_id: str,
    title: str,
    objective: str,
    location_name: str,
    is_minor: bool = False,
    turn_number: int = 0,
    lang: str = "en",
    conn: Optional[Any] = None,
    sync_waypoints: bool = True,
) -> Dict[str, Any]:
    """Compiles a compact `1 Main + 1 Optional` `MicroDossier` for World Pulse `RMR-` Rumors & `MNR-` Minor Events."""
    import db

    eff_lang = normalize_quest_locale(lang)
    engine = "SOCIAL_BROKERAGE" if not is_minor else "CRISIS_DEFENSE"
    family_tier = "minor" if is_minor else "rumor"
    opt_role = "bypass" if not is_minor else "aid"
    rendered_opt = render_optional_objective_template(
        opt_role,
        {"venue": location_name, "zone": location_name.split("➔")[0].strip(), "informant": "local witnesses", "target": title},
        lang=eff_lang,
    )
    leads = [
        {
            "lead_id": f"{quest_id}-L1",
            "optional_id": f"{quest_id}-OPT1",
            "sub_obj_id": 1,
            "is_optional": True,
            "title": rendered_opt["label"],
            "label": rendered_opt["label"],
            "role": opt_role,
            "badge": rendered_opt["badge"],
            "stakes_hint": rendered_opt["stakes_hint"],
            "target_npc": "",
            "target_location": location_name,
            "follow_npc_schedule": 0,
            "approaches": build_engine_lead_approaches(["PER", "CHA", "AGI"], danger_tier=1),
            "encounter_roster": [],
            "status": "active",
            "is_discovered": True,
            "unlock_trigger": "upfront",
            "field_bonus": {"xp": 15, "gold": 0, "affinity": 0},
            "bonus_claimed": False,
        }
    ]
    main_stages = [
        {
            "stage_index": 1,
            "stage_label": f"Investigate on-site at {location_name}",
            "target_location": location_name,
            "target_npc": "",
            "completion_trigger": "action",
            "approaches": build_engine_lead_approaches(["PER", "CHA", "AGI"], danger_tier=1),
            "status": "active",
            "can_be_bypassed": True,
        },
        {
            "stage_index": 2,
            "stage_label": objective or f"Resolve '{title}' at {location_name}",
            "target_location": location_name,
            "target_npc": "",
            "completion_trigger": "action",
            "approaches": build_engine_lead_approaches(["INT", "CHA", "STR"], danger_tier=1),
            "status": "locked",
            "is_climax_stage": True,
        },
    ]
    climax_spec = {
        "has_structured_model": True,
        "gate_type": "open",
        "gate_mode": "open",
        "is_unlocked": True,
        "main_objective_text": objective or title,
        "label": objective or title,
        "main_stage_count": 2,
        "main_stages": main_stages,
        "location": location_name,
        "target_location": location_name,
        "scene_priority": 4,
    }
    scar_spec = render_world_scar_spec(engine=engine, venue_name=location_name, lang=eff_lang)
    scar_spec["scar_tier"] = "bounty"
    saved = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engine=engine,
        family_tier=family_tier,
        danger_tier=1,
        status_stage="compiled",
        compiled_at_turn=int(turn_number or 0),
        conn=conn,
        pitch_stub={"quest_id": quest_id, "title": title, "engine": engine, "public_pitch": objective},
        leads_graph=leads,
        climax_spec=climax_spec,
        turn_in_rules={"mode": "in_field"},
        outcomes_matrix={
            "clean_success": {"gold_multiplier": 1.0, "spawns_world_scar": False},
            "failure": {"gold_multiplier": 0.0, "spawns_world_scar": not is_minor, "world_scar": scar_spec},
        },
    ) or {}
    if session_id and saved and sync_waypoints:
        try:
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved, conn=conn)
        except Exception:
            pass
    return saved
