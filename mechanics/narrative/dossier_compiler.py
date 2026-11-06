from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Tuple

import namegen
import scenario_data
from mechanics.combat import enemies as combat_enemies
from mechanics.narrative.campaign_spine import (
    compile_or_get_campaign_spine,
    compute_chapter_10_world_scar_buffs,
)
from mechanics.narrative.quest_engines import (
    build_engine_lead_approaches,
    build_turn_in_rules,
    load_quest_engines_catalog,
    normalize_quest_locale,
    render_offline_pitch_stub,
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
    return protected


def select_deconflicted_climax_location(
    session_id: int,
    preferred_location: str = "",
    family_tier: str = "bounty",
) -> Tuple[str, str]:
    """
    Ensures active quests prefer distinct Tier-3 rooms so Story, Loyalty, and Side Bounties
    do not stack multiple Boss encounters into the exact same room simultaneously.
    """
    occupied_locs: Set[str] = set()
    import db
    if session_id:
        for dos in (db.get_session_quest_dossiers(session_id, status_stage="compiled") or []):
            cs = dos.get("climax_spec") or {}
            loc_str = str(cs.get("location") or "").strip().lower()
            if loc_str:
                occupied_locs.add(loc_str)

    pref_clean = str(preferred_location or "").strip()
    if pref_clean and (family_tier == "story" or pref_clean.lower() not in occupied_locs):
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
            tier3 = [
                n for n in nodes
                if int(n.get("tier") or 3) >= 3
                and str(n.get("full_path") or n.get("name") or "").strip().lower() not in occupied_locs
            ]
            if tier3:
                chosen = tier3[_det_int(f"room:{session_id}:{pref_clean}:{family_tier}", len(tier3))]
                return str(chosen.get("full_path") or chosen.get("name") or pref_clean or "District Sanctum"), str(chosen.get("node_id") or "")
        except Exception:
            pass

    return (pref_clean or "District Inner Chamber"), ""


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
) -> Tuple[str, str, Optional[int]]:
    """Selects or procedurally generates an NPC name respecting protected-cast and genealogy/incest guards."""
    import db
    gender = preferred_gender or ("female" if _det_int(seed_tag, 2) == 0 else "male")
    if session_id:
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
            cand = namegen.generate_npc_name(scen_key=scen_key, gender=gender)
        except Exception:
            cand = f"Operative {attempt + 1}"
        if not cand or cand.lower() in avoid_low:
            continue
        if for_intimate and session_id and _is_incestuous_with_player(session_id, cand):
            continue
        return cand, gender, None
    return "Mysterious Broker", gender, None


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
    if "anomaly_bp:" not in notes and "anomaly_blueprint:" not in notes:
        return boss_sheet
    try:
        from mechanics.world.anomaly_engine import parse_blueprint_from_notes, instantiate_enemy_from_blueprint
        bp = parse_blueprint_from_notes(notes)
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

    try:
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
    engine = eng_info["engine"]

    protected_low = get_protected_quest_cast_names(session_id) if eff_family == "bounty" else set()
    avoid_set: Set[str] = set(protected_low)
    if session_id:
        p_char = db.get_session_player_character(session_id)
        if p_char and p_char.get("name"):
            avoid_set.add(str(p_char["name"]).strip().lower())

    eff_client = client_npc or stub.get("client_npc") or (existing_q or {}).get("client_npc") or ""
    if not eff_client:
        eff_client, _, client_cid = _pick_safe_npc_name(session_id, eff_scen, f"client:{quest_id}", set())
    else:
        client_cid = None
    avoid_set.add(eff_client.lower())

    for_intimate = engine == "INTIMATE_LIAISON"
    if target_npc and not (for_intimate and _is_incestuous_with_player(session_id, target_npc)) and target_npc.lower() not in protected_low:
        eff_target = target_npc
        target_gender = "female"
        target_cid = None
    else:
        eff_target, target_gender, target_cid = _pick_safe_npc_name(
            session_id, eff_scen, f"target:{quest_id}", avoid_set, for_intimate=for_intimate
        )
    avoid_set.add(eff_target.lower())

    if informant_npc and informant_npc.lower() not in avoid_set:
        eff_informant = informant_npc
        informant_cid = None
    else:
        eff_informant, _, informant_cid = _pick_safe_npc_name(session_id, eff_scen, f"informant:{quest_id}", avoid_set)
    avoid_set.add(eff_informant.lower())

    eff_accomplice, _, accomplice_cid = _pick_safe_npc_name(session_id, eff_scen, f"accomplice:{quest_id}", avoid_set)

    pref_loc = preferred_location or stub.get("client_location") or (existing_q or {}).get("client_location") or sess.get("current_location") or "Central District"
    climax_loc, climax_node_id = select_deconflicted_climax_location(session_id, pref_loc, family_tier=eff_family)

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
    leads_graph: List[Dict[str, Any]] = []
    for idx, lt in enumerate(lead_tmpls):
        lbl_map = lt.get("labels") or {}
        raw_lbl = str(lbl_map.get(eff_lang) or lbl_map.get("en") or f"Investigate Lead #{idx + 1}")
        lead_title = raw_lbl.format(
            venue=climax_loc,
            informant=eff_informant,
            target=eff_target,
            client=eff_client,
        )
        is_combat_lead = bool(idx == len(lead_tmpls) - 1 and encounter_roster)
        leads_graph.append(
            {
                "lead_id": f"{quest_id}-L{idx + 1}",
                "title": lead_title,
                "role": str(lt.get("role") or f"lead_{idx + 1}"),
                "target_npc": eff_informant if idx == 0 else eff_target,
                "target_location": climax_loc,
                "approaches": build_engine_lead_approaches(
                    list(lt.get("stats") or ["PER", "CHA", "AGI"]),
                    danger_tier=eff_danger,
                    allow_curfew_stealth=(engine != "INTIMATE_LIAISON"),
                ),
                "encounter_roster": list(encounter_roster) if is_combat_lead else [],
                "roster_scouted": False,
                "roster_cleared": False,
                "status": "active",
                "is_discovered": True,
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
    climax_spec: Dict[str, Any] = {
        "gate_type": gate_mode,  # open | secret
        "is_unlocked": bool(gate_mode == "open"),
        "location": climax_loc,
        "node_id": climax_node_id,
        "scene_priority": FAMILY_SCENE_PRIORITY.get(eff_family, 3),
        "true_culprit": true_culprit,
        "innocent_suspect": innocent_suspect,
        "is_elimination_strict": bool(eng_info["is_elimination_strict"]),
        "is_final_chapter_boss": bool(eff_family == "story" and eff_chapter == 10 and boss_sheet is not None),
        "boss_sheet": boss_sheet,
        "reinforcements": [],
        "rush_un_nerfed_buffs": {"bonus_dt": 4, "reinforce_from_uncleared_leads": True} if gate_mode == "open" else {},
    }
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
    outcomes_matrix = {
        "clean_success": {"gold_multiplier": 1.0, "xp_multiplier": 1.0, "spawns_world_scar": False},
        "twist_resolution": {"gold_multiplier": 1.25, "xp_multiplier": 1.15, "spawns_world_scar": False},
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
            "triggers_hard_game_over": bool(eff_family == "story" and eff_chapter == 10 and boss_sheet is not None),
        },
    }

    saved = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engine=engine,
        family_tier=eff_family,
        danger_tier=eff_danger,
        status_stage="compiled",
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
                "UPDATE quests SET engine = ?, dossier_stage = 'compiled' WHERE session_id = ? AND quest_id = ?",
                (engine, session_id, quest_id),
            )
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
) -> Dict[str, Any]:
    """Compiles a compact 1-2 beat `MicroDossier` for World Pulse `RMR-` Rumors & `MNR-` Minor Events."""
    import db
    engine = "SOCIAL_BROKERAGE" if not is_minor else "CRISIS_DEFENSE"
    family_tier = "minor" if is_minor else "rumor"
    leads = [
        {
            "lead_id": f"{quest_id}-M1",
            "title": f"Investigate on-site at {location_name}",
            "role": "micro_beat_1",
            "target_npc": "",
            "target_location": location_name,
            "approaches": build_engine_lead_approaches(["PER", "CHA", "AGI"], danger_tier=1),
            "encounter_roster": [],
            "status": "active",
            "is_discovered": True,
        }
    ]
    if not is_minor:
        leads.append(
            {
                "lead_id": f"{quest_id}-M2",
                "title": f"Verify source behind '{title}'",
                "role": "micro_beat_2",
                "target_npc": "",
                "target_location": location_name,
                "approaches": build_engine_lead_approaches(["INT", "CHA", "BRIBE"], danger_tier=1),
                "encounter_roster": [],
                "status": "active",
                "is_discovered": True,
            }
        )
    scar_spec = render_world_scar_spec(engine=engine, venue_name=location_name, lang=lang)
    return db.upsert_quest_dossier(
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
        climax_spec={"gate_type": "open", "is_unlocked": True, "location": location_name, "scene_priority": 4},
        turn_in_rules={"mode": "in_field"},
        outcomes_matrix={
            "clean_success": {"gold_multiplier": 1.0, "spawns_world_scar": False},
            "failure": {"gold_multiplier": 0.0, "spawns_world_scar": not is_minor, "world_scar": scar_spec},
        },
    ) or {}
