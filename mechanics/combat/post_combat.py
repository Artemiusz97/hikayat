"""mechanics/combat/post_combat.py

Post-combat recovery, companion XP/vitality scaling, round threat decay,
DoT-kill boss telegraph pruning, and end-of-combat session cleanup.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import db
import scenario_data

from .loadouts import (
    build_combatant_stat_sheet,
    compute_companion_vitals,
    reset_combatant_cooldowns,
)

logger = logging.getLogger(__name__)


def decay_round_threat(
    threat_ledger: Dict[str, Any],
    downed_actor_ids: Set[str],
) -> None:
    """Applies 25% exponential round decay to threat scores and instantly drops downed actors to zero threat."""
    matrix = threat_ledger.get("threat_matrix", threat_ledger)
    if isinstance(matrix, dict):
        for eid in list(matrix.keys()):
            if not isinstance(matrix[eid], dict):
                continue
            for aid in list(matrix[eid].keys()):
                if aid in downed_actor_ids:
                    matrix[eid][aid] = 0.0
                else:
                    matrix[eid][aid] = round(matrix[eid][aid] * 0.75, 2)

    taunts = threat_ledger.get("sticky_taunts")
    if isinstance(taunts, dict):
        for eid in list(taunts.keys()):
            t_info = taunts[eid]
            if isinstance(t_info, dict):
                rem = int(t_info.get("remaining_turns", 1)) - 1
                if rem <= 0 or str(t_info.get("target_id")) in downed_actor_ids:
                    taunts.pop(eid, None)
                else:
                    t_info["remaining_turns"] = rem


def cleanup_anomalous_combat_session_state(session: Dict[str, Any]) -> None:
    """Purges autonomous constructs, summons, resonance pips, and vanished stealth states when combat ends."""
    if not isinstance(session, dict):
        return
    session["_active_constructs"] = []
    session.pop("_construct_initialized_this_combat", None)
    session["player_resonance_pips"] = {}
    session["combat_threat_ledger"] = {}
    session["combat_boss_telegraph"] = {}
    session["current_npcs"] = [
        n for n in session.get("current_npcs", [])
        if not (isinstance(n, dict) and (n.get("is_summon") or n.get("is_autonomous_construct")))
    ]
    for group_key in ("party_npcs", "current_npcs"):
        for npc in (session.get(group_key) or []):
            if isinstance(npc, dict):
                reset_combatant_cooldowns(npc)
    try:
        from mechanics.stealth.core import clear_all_combat_vanished
        clear_all_combat_vanished(session)
    except Exception:
        pass


def prune_dead_combat_state(
    session: Dict[str, Any],
    surviving_enemies: List[Dict[str, Any]],
    llm_outcome: Optional[Dict[str, Any]] = None,
) -> None:
    """Prunes dead enemies (including post-turn DoT kills) from boss telegraphs and threat ledgers, or resets all on victory."""
    if not isinstance(session, dict):
        return
    live_keys: Set[str] = set()
    for e in (surviving_enemies or []):
        if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0:
            for k in ("id", "name"):
                v = e.get(k)
                if v:
                    live_keys.add(str(v))

    if not live_keys:
        cleanup_anomalous_combat_session_state(session)
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_boss_telegraph"] = {}
            llm_outcome["combat_threat_ledger"] = {}
        return

    raw_telegraph = session.get("combat_boss_telegraph")
    if isinstance(raw_telegraph, dict):
        for eid in list(raw_telegraph.keys()):
            if str(eid) not in live_keys:
                raw_telegraph.pop(eid, None)
        session["combat_boss_telegraph"] = raw_telegraph
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_boss_telegraph"] = raw_telegraph

    raw_ledger = session.get("combat_threat_ledger")
    if isinstance(raw_ledger, dict):
        matrix = raw_ledger.get("threat_matrix", raw_ledger)
        if isinstance(matrix, dict):
            for eid in list(matrix.keys()):
                if eid == "sticky_taunts" or eid == "threat_matrix" or eid == "current_aggro_targets":
                    continue
                if str(eid) not in live_keys and isinstance(matrix[eid], dict):
                    matrix.pop(eid, None)
        sticky = raw_ledger.get("sticky_taunts")
        if isinstance(sticky, dict):
            for eid in list(sticky.keys()):
                if str(eid) not in live_keys:
                    sticky.pop(eid, None)
        session["combat_threat_ledger"] = raw_ledger
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_threat_ledger"] = raw_ledger


def finalize_post_combat_state(
    session: Dict[str, Any],
    llm_outcome: Dict[str, Any],
    enemies: List[Dict[str, Any]],
    party: Optional[List[Any]],
    total_xp_gain: int,
    dead_enemies: List[Any],
    dead_enemy_dicts_rec: List[Dict[str, Any]],
) -> None:
    """Handles post-turn companion auto-revive, party defeat extraction/recovery, companion scaling, and threat decay."""
    session_id = session.get("id", 0) if session else 0
    party_npcs = db.get_session_party_npcs(session_id) if session_id else []

    if not enemies and (party_npcs or (party and len(party) > 1)):
        for co in llm_outcome.get("character_outcomes", []):
            if isinstance(co, dict):
                p_char = next((char for char, _ in (party or []) if char.get("name", "").lower() == co.get("name", "").lower()), None)
                if p_char:
                    p_hp = int(p_char.get("hp") if p_char.get("hp") is not None else 10)
                    projected_hp = p_hp + int(co.get("hp_change", 0) or 0)
                    if projected_hp <= 0:
                        co["hp_change"] = 1 - p_hp
                        co["status_effects"] = ["Exhausted / Recovering"]
                        llm_outcome["_combat_resolved_notice"] = (str(llm_outcome.get("_combat_resolved_notice", "")) + "\n🩹 Your companion tended to your wounds — revived with **1 HP**!").strip()

    if enemies and party:
        all_downed = True
        for p_entry in party:
            char = p_entry[0] if isinstance(p_entry, (tuple, list)) and len(p_entry) > 0 else (p_entry if isinstance(p_entry, dict) else {})
            c_name = char.get("name", "").lower()
            matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == c_name), None)
            c_hp = int(char.get("hp") if char.get("hp") is not None else 10)
            c_proj_hp = c_hp + (int(matching_co.get("hp_change", 0) or 0) if matching_co else 0)
            if c_proj_hp > 0:
                all_downed = False
                break
        if all_downed and party_npcs:
            for npc in party_npcs:
                if int(npc.get("hp") or 0) > 0:
                    all_downed = False
                    break

        is_anom_defeat = bool(isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")))
        if all_downed and is_anom_defeat:
            session["nearby_enemies"] = []
            llm_outcome["nearby_enemies"] = []
            lead_char = party[0][0] if (party and party[0] and isinstance(party[0][0], dict)) else {}
            lead_uid = lead_char.get("user_id") or (session.get("host_user_id") if isinstance(session, dict) else 0)
            from mechanics.world.anomalous_events import resolve_anomalous_emergency_extraction
            ext = resolve_anomalous_emergency_extraction(int(session_id or 0), int(lead_uid or 0), apply_vitals_to_db=False)
            session["current_location"] = ext["destination_location"]
            session["current_node_id"] = ext["destination_node_id"]
            session["current_day"] = ext.get("new_day", session.get("current_day", 1))
            session["current_minute"] = ext.get("new_minute", session.get("current_minute", 480))
            llm_outcome["location"] = ext["destination_location"]
            llm_outcome["current_node_id"] = ext["destination_node_id"]
            llm_outcome["_anomalous_extracted"] = True
            llm_outcome["_authorized_gold_spend"] = int(ext.get("fee_paid", 0) or 0)

            for idx_p, (char, _) in enumerate(party):
                uid = char.get("user_id")
                max_hp = int(char.get("max_hp") or 30)
                max_mp = int(char.get("max_mp") or 15)
                revive_hp = max(1, max_hp // 2)
                revive_mp = max(1, max_mp // 2)
                cur_hp = int(char.get("hp") or 0)
                cur_mp = int(char.get("mp") or 0)
                fee_delta = -int(ext.get("fee_paid", 0)) if idx_p == 0 else 0
                matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                if matching_co:
                    matching_co["hp_change"] = revive_hp - cur_hp
                    matching_co["mp_change"] = max(0, revive_mp - cur_mp)
                    matching_co["gold_change"] = matching_co.get("gold_change", 0) + fee_delta
                    matching_co["status_effects"] = ["Stabilized / Triage Recovery"]
                else:
                    llm_outcome.setdefault("character_outcomes", []).append({
                        "name": char.get("name", "Operative"),
                        "hp_change": revive_hp - cur_hp,
                        "mp_change": max(0, revive_mp - cur_mp),
                        "gold_change": fee_delta,
                        "status_effects": ["Stabilized / Triage Recovery"],
                    })
                if uid:
                    db.set_status_effects(uid, ["Stabilized / Triage Recovery"])

            if party_npcs:
                updated_npcs = []
                for c in party_npcs:
                    c["hp"] = max(1, c.get("max_hp", 20) // 2)
                    c["status_effects"] = ["Stabilized / Triage Recovery"]
                    updated_npcs.append(c)
                db.set_session_party_npcs(session_id, updated_npcs)
                session["current_npcs"] = updated_npcs

            llm_outcome["_party_defeated_notice"] = ext["narrative"]
            llm_outcome["next_choices"] = [
                {"label": "Check medical telemetry and stabilize your psychic resonance", "stat": "END", "requirement": 4, "mp_cost": 0},
                {"label": "Review field logs and inspect your tactical loadout", "stat": "PER", "requirement": 4, "mp_cost": 0},
                {"label": "Debrief with triage staff before redeploying to the breach", "stat": "CHA", "requirement": 4, "mp_cost": 0},
            ]
            llm_outcome["choices"] = llm_outcome["next_choices"]
        elif all_downed:
            is_climax = any(
                e.get("is_boss") or e.get("tier_rank", 1) >= 5 or (isinstance(session, dict) and session.get("is_climax_encounter"))
                for e in (session.get("nearby_enemies") or session.get("_pre_combat_enemies") or [])
            )
            if is_climax:
                session["status"] = "finished"
                llm_outcome["is_game_over"] = True
                llm_outcome["_party_defeated_notice"] = "💀 **The Party Has Fallen!** Slain in climax battle."
                llm_outcome["next_choices"] = []
                llm_outcome["choices"] = []
            else:
                session["nearby_enemies"] = []
                llm_outcome["nearby_enemies"] = []

                for p_entry in party:
                    char = p_entry[0] if isinstance(p_entry, (tuple, list)) and len(p_entry) > 0 else (p_entry if isinstance(p_entry, dict) else {})
                    uid = char.get("user_id")
                    max_hp = int(char.get("max_hp") or 30)
                    revive_hp = max(1, max_hp // 2)
                    cur_hp = int(char.get("hp") or 0)
                    matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                    if matching_co:
                        matching_co["hp_change"] = revive_hp - cur_hp
                        matching_co["status_effects"] = ["Exhausted / Recovering"]
                    else:
                        llm_outcome.setdefault("character_outcomes", []).append({
                            "name": char.get("name", "Hero"),
                            "hp_change": revive_hp - cur_hp,
                            "mp_change": 0,
                            "gold_change": 0,
                            "status_effects": ["Exhausted / Recovering"],
                        })
                    if uid:
                        db.set_status_effects(uid, ["Exhausted / Recovering"])

                if party_npcs:
                    updated_npcs = []
                    for c in party_npcs:
                        c["hp"] = max(1, c.get("max_hp", 20) // 2)
                        c["status_effects"] = ["Exhausted / Recovering"]
                        updated_npcs.append(c)
                    db.set_session_party_npcs(session_id, updated_npcs)
                    session["current_npcs"] = updated_npcs

                llm_outcome["_party_defeated_notice"] = "💀 **Party Defeated!** You were overwhelmed and fell in battle, but were recovered to safety. You awaken stabilized, nursing your injuries."
                llm_outcome["next_choices"] = [
                    {"label": "Rest and recuperate from your injuries", "stat": "END", "requirement": 4, "mp_cost": 0},
                    {"label": "Assess your surroundings and check equipment", "stat": "PER", "requirement": 4, "mp_cost": 0},
                    {"label": "Consult with companions about what happened", "stat": "CHA", "requirement": 4, "mp_cost": 0},
                ]
                llm_outcome["choices"] = llm_outcome["next_choices"]

    if not enemies and total_xp_gain > 0 and party_npcs and party and party[0]:
        scen_lvl = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"
        is_anom_lvl = bool(isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(scen_lvl))
        p_lvl = party[0][0].get("level", 1)
        updated_npcs = []
        for c in party_npcs:
            c_lvl = max(c.get("level", 1), p_lvl)
            c["level"] = c_lvl
            if is_anom_lvl and c.get("anomalous_npc_tag") == "special_agent":
                from mechanics.social.anomalous_npc_tags import compute_special_agent_combat_stats
                scaled_st = compute_special_agent_combat_stats(
                    agent_tier=int(c.get("agent_tier", 1) or 1),
                    player_level=c_lvl,
                    agent_class=str(c.get("agent_class") or ""),
                    faction_id=str(c.get("faction_id") or ""),
                    is_party_companion=True,
                    seed_str=f"{session_id}:{str(c.get('name') or '').lower()}",
                )
                c["max_hp"] = scaled_st["max_hp"]
                c["max_mp"] = scaled_st["max_mp"]
                c["stats"] = scaled_st["stats"]
            else:
                if not isinstance(c.get("stats"), dict) or not c.get("stats"):
                    c["stats"] = build_combatant_stat_sheet(c_lvl, c.get("archetype", "Companion"), role_tier="companion")
                is_civ = str(c.get("anomalous_npc_tag") or "").strip().lower() == "civilian"
                c_max_hp, c_max_mp = compute_companion_vitals(c_lvl, c.get("stats"), is_civilian=is_civ)
                c["max_hp"] = c_max_hp
                c["max_mp"] = c_max_mp
            reset_combatant_cooldowns(c)
            c["hp"] = min(c.get("hp", c["max_hp"]), c["max_hp"])
            c["mp"] = min(c.get("mp", c["max_mp"]), c["max_mp"])
            updated_npcs.append(c)
        if isinstance(session, dict):
            session["party_npcs"] = updated_npcs
        llm_outcome["party_npcs"] = updated_npcs
        db.set_session_party_npcs(session_id, updated_npcs)

    try:
        if not enemies:
            session["combat_threat_ledger"] = {}
            session["combat_boss_telegraph"] = {}
            llm_outcome["combat_threat_ledger"] = {}
            llm_outcome["combat_boss_telegraph"] = {}
            for p_comp in (party_npcs or []):
                if isinstance(p_comp, dict):
                    reset_combatant_cooldowns(p_comp)
            if session_id and party_npcs and total_xp_gain <= 0:
                session["party_npcs"] = party_npcs
                llm_outcome["party_npcs"] = party_npcs
                db.set_session_party_npcs(session_id, party_npcs)
            cleanup_anomalous_combat_session_state(session)
        else:
            dead_eids: Set[str] = set()
            for d in (dead_enemies or []):
                if isinstance(d, dict):
                    for k in ("id", "name"):
                        v = d.get(k)
                        if v:
                            dead_eids.add(str(v))
                elif d:
                    dead_eids.add(str(d))
            for d in (dead_enemy_dicts_rec or []):
                if isinstance(d, dict):
                    for k in ("id", "name"):
                        v = d.get(k)
                        if v:
                            dead_eids.add(str(v))

            raw_telegraph = session.get("combat_boss_telegraph")
            if isinstance(raw_telegraph, dict):
                for eid in list(raw_telegraph.keys()):
                    if eid in dead_eids:
                        raw_telegraph.pop(eid, None)
                session["combat_boss_telegraph"] = raw_telegraph
                llm_outcome["combat_boss_telegraph"] = raw_telegraph

            raw_ledger = session.get("combat_threat_ledger")
            if isinstance(raw_ledger, dict):
                matrix = raw_ledger.get("threat_matrix", raw_ledger)
                if isinstance(matrix, dict):
                    for eid in list(matrix.keys()):
                        if eid in dead_eids:
                            matrix.pop(eid, None)
                sticky = raw_ledger.get("sticky_taunts")
                if isinstance(sticky, dict):
                    for eid in list(sticky.keys()):
                        if eid in dead_eids:
                            sticky.pop(eid, None)

                downed_ids: Set[str] = set()

                def _cand_actor_keys(a: Dict[str, Any]) -> Set[str]:
                    keys: Set[str] = set()
                    for k in ("name", "id", "user_id", "npc_id"):
                        val = a.get(k)
                        if val is not None:
                            s_val = str(val).strip()
                            if s_val and s_val.lower() != "none":
                                keys.add(s_val)
                    return keys

                for p in (party or []):
                    p_obj = p[0] if isinstance(p, (tuple, list)) else p
                    if isinstance(p_obj, dict):
                        p_hp = p_obj.get("hp")
                        if p_hp is not None and int(p_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(p_obj))
                for npc in (session.get("party_npcs") or []):
                    if isinstance(npc, dict):
                        n_hp = npc.get("hp")
                        if n_hp is not None and int(n_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(npc))
                for comp in (session.get("temporary_companions") or []):
                    if isinstance(comp, dict):
                        c_hp = comp.get("hp")
                        if c_hp is not None and int(c_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(comp))
                decay_round_threat(raw_ledger, downed_ids)
                session["combat_threat_ledger"] = raw_ledger
                llm_outcome["combat_threat_ledger"] = raw_ledger
    except Exception as _th_err:
        logger.debug("Threat decay failed: %s", _th_err)
