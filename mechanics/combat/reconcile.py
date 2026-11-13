from __future__ import annotations
"""
Post-LLM combat reconciliation, defeat routing, loot distribution, and session state cleanup.
"""
import json
import logging
import random
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import db
import scenario_data
from scenario_data import is_mechanic_enabled
from .formulas import (
    calculate_opposed_dc,
    get_elemental_multiplier,
    try_inflict_status,
    calculate_tactical_damage,
    calculate_turn_damage,
    tick_status_timers,
)
from .sparring import (
    is_sparring_monster,
    resolve_sparring_defeat,
    make_sparring_monster,
    call_faction_reinforcements,
)
from .status_effects import (
    apply_status_effect,
    tick_status_instance_timers,
    format_status_badge,
    normalize_status_effect,
)
from .types import CombatantState, StatusEffectInstance, get_combatant_stat

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

def _enemy_has_unsealed_tether(enemy: dict) -> bool:
    """True when an anomaly is still anchored by an unsealed Vessel Tether (no Vault capture until sealed)."""
    if not isinstance(enemy, dict) or enemy.get("tether_sealed") or enemy.get("taboo_exploited"):
        return False
    try:
        from mechanics.world.folklore_mechanics import get_enemy_tether_state
        ts = get_enemy_tether_state(enemy)
    except Exception:
        return False
    return bool(ts and not ts.get("sealed"))


def _record_non_incursion_anomaly_kills(session: dict, party: Optional[list], dead_dicts: list) -> None:
    """
    Records Folklore Codex / field-log / retirement progress for hostile anomalies defeated in combat that are
    NOT tied to a Daily Breach (handled by `mark_hostile_incursion_resolved_on_victory`) and NOT objects
    (handled by `handle_secured_object_anomaly_conversion`). Unsealed tether dispersals only count as a sighting.
    """
    sess_id = int(session.get("id") or 0)
    if not sess_id:
        return
    party_uids = [
        int(p[0]["user_id"])
        for p in (party or [])
        if p and isinstance(p[0], dict) and p[0].get("user_id")
    ]
    for d in (dead_dicts or []):
        if not isinstance(d, dict) or d.get("requires_non_lethal_subdue"):
            continue
        if d.get("incursion_id") or d.get("breach_id"):
            continue
        bp = d.get("anomaly_blueprint") if isinstance(d.get("anomaly_blueprint"), dict) else {}
        if not bp or str(d.get("anomaly_type") or bp.get("type") or "").lower() == "object":
            continue
        if not (bp.get("blueprint_id") or bp.get("codex_id")):
            continue
        dispersed = bool(d.get("prevent_vault_capture") or d.get("tether_dispersed_unsealed"))
        stage = "sighted" if dispersed else "contained"
        try:
            db.record_session_anomaly_field_log(
                sess_id,
                bp,
                stage=stage,
                location=str(session.get("current_location") or ""),
                resolution_method="Neutralized in Combat" if not dispersed else "Dispersed (Unsealed Tether)",
            )
            codex_id = str(bp.get("codex_id") or "")
            if codex_id:
                p_uids = db.get_session_participant_user_ids(sess_id)
                for u in party_uids:
                    if u not in p_uids:
                        p_uids.append(u)
                db.record_folklore_codex_progress(p_uids, codex_id, stage=stage)
                if not dispersed:
                    db.retire_or_cooldown_folklore_in_session(
                        sess_id,
                        codex_id,
                        uniqueness=str(bp.get("uniqueness") or "species"),
                        current_day=int(session.get("current_day") or 1),
                        cooldown_days=int(bp.get("cooldown_days") or 4),
                    )
        except Exception as rec_err:  # noqa: BLE001 - codex bookkeeping must never break combat reconciliation
            import logging
            logging.getLogger(__name__).warning("Folklore codex kill record failed for %s: %s", d.get("name"), rec_err)


def reconcile_combat_results(session: dict, llm_outcome: dict, precomputed: dict, party: list = None) -> dict:
    """Applies precomputed outcomes to the final LLM response and handles post-combat choices."""
    if not precomputed:
        return llm_outcome

    if "next_choices" in llm_outcome and "choices" not in llm_outcome:
        llm_outcome["choices"] = llm_outcome["next_choices"]
    elif "choices" in llm_outcome and "next_choices" not in llm_outcome:
        llm_outcome["next_choices"] = llm_outcome["choices"]

    # Session enemies, NPCs, and Resonance Pips were mutated by precompute_combat_turn (or passed in precomputed)
    if isinstance(precomputed, dict):
        if precomputed.get("fled_battle"):
            session["nearby_enemies"] = []
            precomputed["surviving_enemies"] = []
        elif "surviving_enemies" in precomputed:
            session["nearby_enemies"] = precomputed["surviving_enemies"]
        if "player_resonance_pips" in precomputed:
            session["player_resonance_pips"] = precomputed["player_resonance_pips"]
    enemies = session.get("nearby_enemies", [])
    llm_outcome["nearby_enemies"] = enemies
    llm_outcome["npcs_present"] = session.get("current_npcs", [])
    if "party_npcs" in session:
        llm_outcome["party_npcs"] = session["party_npcs"]
    if "player_resonance_pips" in session:
        llm_outcome["player_resonance_pips"] = session["player_resonance_pips"]

    if isinstance(precomputed, list):
        actions = precomputed
        precomputed = {
            "dead_enemies": [],
            "dead_monsters": [],
            "yielded_enemies": [],
            "yielded_monsters": [],
            "combat_log": [],
            "player_damage_taken": 0,
            "xp_gain": 0,
            "gold_gain": 0
        }
        for act in actions:
            tier = act.get("tier")
            char_info = act.get("char", {})
            if tier == "crit_success":
                dmg = 45
                if enemies:
                    enemies[0]["hp"] = max(0, enemies[0].get("hp", 30) - dmg)
                    if enemies[0]["hp"] == 0:
                        dead_m = enemies.pop(0)
                        precomputed["dead_enemies"].append(dead_m.get("name", "Enemy"))
                        precomputed["dead_monsters"].append(dead_m.get("name", "Enemy"))
                        precomputed.setdefault("dead_enemy_dicts", []).append(dict(dead_m))
            elif tier == "crit_fail":
                char_name = char_info.get("name", "Hero")
                precomputed["acting_char_name"] = char_name
                precomputed["player_damage_taken"] = 25

    dead_enemies = precomputed.get("dead_enemies") or precomputed.get("dead_monsters", [])
    dead_enemy_dicts_rec = precomputed.get("dead_enemy_dicts") or []
    surrendered_enemy_dicts_rec = precomputed.get("surrendered_enemy_dicts") or []
    total_xp_gain = precomputed.get("xp_gain", 0)
    total_gold_gain = precomputed.get("gold_gain", 0)
    confiscate_anomalous_loot = False
    suppress_non_hostile_loot = False
    killed_nh_messages = []
    parley_contained_messages = []

    party_uids_rec = []
    for p in (party or []):
        p_obj = p[0] if isinstance(p, (tuple, list)) else p
        if isinstance(p_obj, dict) and p_obj.get("user_id"):
            party_uids_rec.append(p_obj.get("user_id"))
    lead_uid = party_uids_rec[0] if party_uids_rec else (session.get("host_user_id") if isinstance(session, dict) else None)

    killed_non_hostiles = [
        d for d in dead_enemy_dicts_rec
        if isinstance(d, dict) and d.get("requires_non_lethal_subdue") and not d.get("surrendered")
    ]
    if killed_non_hostiles:
        if len(killed_non_hostiles) >= len(dead_enemies):
            total_gold_gain = 0
            suppress_non_hostile_loot = True
        if isinstance(session, dict) and session.get("id"):
            try:
                from mechanics.world.anomalous_events import handle_killed_non_hostile_entity
                for nh_dead in killed_non_hostiles:
                    nh_res = handle_killed_non_hostile_entity(
                        session_id=int(session["id"]),
                        dead_enemy=nh_dead,
                        user_id=lead_uid,
                        party_user_ids=party_uids_rec,
                        session=session,
                    )
                    if nh_res.get("message"):
                        killed_nh_messages.append(nh_res["message"])
            except Exception:
                pass

    parley_contained = [
        d for d in surrendered_enemy_dicts_rec
        if isinstance(d, dict) and d.get("contained_via_parley")
    ]
    if parley_contained and isinstance(session, dict) and session.get("id"):
        suppress_non_hostile_loot = True
        try:
            import db
            from mechanics.world.anomalous_events import (
                _complete_or_advance_linked_quest_containment,
                record_contained_anomaly_to_vault_log,
                _roll_optional_incursion_gear_drop,
            )
            sess_id_int = int(session["id"])
            scen_rec = str(session.get("scenario") or "anomalous_incursions")
            for p_ent in parley_contained:
                p_name = str(p_ent.get("name") or "Non-Hostile Entity")
                p_inc_id = str(p_ent.get("incursion_id") or "")
                p_qid = str(p_ent.get("linked_quest_id") or "")
                p_so_id = p_ent.get("linked_sub_obj_id")
                if p_inc_id:
                    fresh_s = db.get_session(sess_id_int) or session
                    incs = list(fresh_s.get("daily_incursions") or [])
                    t_inc = next((x for x in incs if x.get("incursion_id") == p_inc_id), None)
                    if t_inc and not t_inc.get("resolved"):
                        for x in incs:
                            if x.get("incursion_id") == p_inc_id:
                                x["resolved"] = True
                                x["agitated"] = False
                        db.update_session(sess_id_int, extra={"daily_incursions": incs})
                        session["daily_incursions"] = incs
                        g_gain = int(t_inc.get("reward_gold", 120) or 120)
                        x_gain = int(t_inc.get("reward_xp", 85) or 85)
                        if lead_uid:
                            db.apply_hp_mp_delta(lead_uid, gold_delta=g_gain)
                            db.add_xp(lead_uid, x_gain)
                        v_ent = record_contained_anomaly_to_vault_log(
                            session_id=sess_id_int,
                            entity_name=t_inc["entity_name"],
                            category_tag=t_inc["category_tag"],
                            subtype=t_inc["subtype"],
                            location=t_inc["location"],
                            containment_note=t_inc.get("containment_note", ""),
                            resolution_method="De-escalated & Contained in Combat",
                            user_id=lead_uid,
                        )
                        _roll_optional_incursion_gear_drop(lead_uid, scen_rec)
                        parley_contained_messages.append(
                            f"🗣️ Contained **{t_inc['entity_name']}** alive via combat de-escalation! "
                            f"Earned +{g_gain}G, +{x_gain} XP, and logged into {v_ent['vault_facility']}."
                        )
                elif p_qid:
                    q_res = _complete_or_advance_linked_quest_containment(
                        session_id=sess_id_int,
                        quest_id=p_qid,
                        sub_obj_id=p_so_id,
                        entity_name=p_name,
                        category_tag=str(p_ent.get("category_tag") or "spatial_warp"),
                        resolution_method="De-escalated & Contained in Combat",
                        party_user_ids=party_uids_rec or ([lead_uid] if lead_uid else []),
                    )
                    v_fac = (q_res.get("vault_entry") or {}).get("vault_facility", "Containment Vault")
                    parley_contained_messages.append(
                        f"🗣️ Contained **{p_name}** alive via combat de-escalation and logged to {v_fac}!"
                    )
                elif p_ent.get("is_anomalous_manifestation"):
                    from mechanics.world.anomalous_events import resolve_anomalous_combat_containment
                    c_res = resolve_anomalous_combat_containment(
                        session_id=sess_id_int,
                        target_enemy=p_ent,
                        user_id=lead_uid,
                        party_user_ids=party_uids_rec or ([lead_uid] if lead_uid else []),
                        resolution_method="Live Capture (Mid-Combat Parley)",
                    )
                    if c_res and c_res.get("message"):
                        parley_contained_messages.append(str(c_res["message"]))
        except Exception:
            pass

    if isinstance(session, dict):
        import scenario_data
        if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
            try:
                from mechanics.narrative.bounty import should_confiscate_anomalous_combat_loot
                confiscate_anomalous_loot = should_confiscate_anomalous_combat_loot(
                    int(session.get("id") or 0),
                    session=session,
                    user_id=lead_uid,
                    defeated_enemies=dead_enemy_dicts_rec or dead_enemies,
                )
            except Exception:
                confiscate_anomalous_loot = False
    if confiscate_anomalous_loot:
        total_gold_gain = 0
    if total_gold_gain > 0:
        llm_outcome["_combat_gold"] = int(llm_outcome.get("_combat_gold", 0) or 0) + total_gold_gain
    combat_log = precomputed.get("combat_log", [])
    player_damage_by_name = precomputed.get("player_damage_by_name", {})
    player_damage_taken = precomputed.get("player_damage_taken", 0)

    if combat_log:
        llm_outcome["_combat_log"] = combat_log

    yielded_enemies = precomputed.get("yielded_enemies") or precomputed.get("yielded_monsters", [])
    fled_enemies = precomputed.get("fled_enemies") or precomputed.get("fled_monsters", [])
    if yielded_enemies and not enemies:
        llm_outcome["_combat_resolved_notice"] = f"⚔️ Duel Concluded! {', '.join(yielded_enemies)} yielded!"
        llm_outcome["faction_promotion_result"] = "success"
    elif precomputed.get("fled_battle") and not enemies:
        llm_outcome["_combat_resolved_notice"] = "🏃 Tactical Retreat! The party successfully disengaged and fled from combat."
    elif fled_enemies and not enemies:
        if parley_contained_messages:
            llm_outcome["_combat_resolved_notice"] = "\n".join(parley_contained_messages)
        else:
            llm_outcome["_combat_resolved_notice"] = f"⚔️ Encounter Survived! {', '.join(fled_enemies)} fled the battle!"
    elif dead_enemies and not enemies:
        if len(killed_non_hostiles) >= len(dead_enemies) and killed_nh_messages:
            llm_outcome["_combat_resolved_notice"] = "\n".join(killed_nh_messages)
        else:
            llm_outcome["_combat_resolved_notice"] = (
                f"⚔️ Victory! {', '.join(str(d.get('name') if isinstance(d, dict) else d) for d in dead_enemies)} defeated!\n"
                f"**Rewards:** +{total_xp_gain} XP, +0 Gold *(Taxpayer Mandate: All anomalous salvage & spoils requisitioned by Public Agency HQ)*"
                if confiscate_anomalous_loot
                else f"⚔️ Victory! {', '.join(str(d.get('name') if isinstance(d, dict) else d) for d in dead_enemies)} defeated!\n**Rewards:** +{total_xp_gain} XP, +{total_gold_gain} Gold"
            )
            if killed_nh_messages:
                llm_outcome["_combat_resolved_notice"] += "\n" + "\n".join(killed_nh_messages)
        # Fail-Forward Suspect Pocket Evidence Extraction on Combat Defeat (Phase 5 A14)
        try:
            if isinstance(session, dict) and session.get("id"):
                import game_engine as _ge_ev
                for _de in (dead_enemies or []):
                    _de_name = str(_de.get("name") if isinstance(_de, dict) else _de).strip()
                    if _de_name:
                        _ev_res = _ge_ev.check_and_extract_defeated_suspect_evidence(
                            int(session["id"]),
                            _de_name,
                            cur_loc=str(session.get("current_location") or ""),
                        )
                        if _ev_res and _ev_res.get("title"):
                            llm_outcome["_combat_resolved_notice"] += f"\n🔍 **Evidence Recovered:** {_ev_res['title']}"
        except Exception:
            pass
        # Resolve any linked Hostile Daily Anomaly Breach (excluding killed non-hostile entities)
        try:
            dead_dicts = precomputed.get("dead_enemy_dicts") or []
            inc_map = {}
            for d in dead_dicts:
                if isinstance(d, dict) and (d.get("incursion_id") or d.get("breach_id")) and not d.get("requires_non_lethal_subdue"):
                    iid = str(d.get("incursion_id") or d.get("breach_id"))
                    inc_map[iid] = bool(d.get("prevent_vault_capture") or d.get("tether_dispersed_unsealed"))
            if inc_map and isinstance(session, dict) and session.get("id"):
                from mechanics.world.anomalous_events import mark_hostile_incursion_resolved_on_victory
                lead_uid_inc = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                for inc_id_done, skip_vault in inc_map.items():
                    inc_done_res = mark_hostile_incursion_resolved_on_victory(
                        int(session["id"]),
                        inc_id_done,
                        user_id=lead_uid_inc,
                        prevent_vault_capture=skip_vault,
                    )
                    if inc_done_res and inc_done_res.get("message"):
                        llm_outcome["_combat_resolved_notice"] += f"\n{inc_done_res['message']}"
            if isinstance(session, dict) and session.get("id"):
                from mechanics.world.anomalous_events import handle_secured_object_anomaly_conversion
                lead_uid_obj = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                scen_obj = str(session.get("scenario") or "anomalous_incursions")
                for d_obj in dead_dicts:
                    if not isinstance(d_obj, dict) or d_obj.get("requires_non_lethal_subdue"):
                        continue
                    if d_obj.get("incursion_id") or d_obj.get("breach_id"):
                        continue
                    if d_obj.get("prevent_vault_capture") or d_obj.get("tether_dispersed_unsealed"):
                        continue
                    bp_obj = d_obj.get("anomaly_blueprint") if isinstance(d_obj.get("anomaly_blueprint"), dict) else {}
                    a_type_obj = str(d_obj.get("anomaly_type") or bp_obj.get("type") or "").lower()
                    if a_type_obj == "object":
                        conv_out = handle_secured_object_anomaly_conversion(
                            session_id=int(session["id"]),
                            user_id=lead_uid_obj,
                            blueprint=bp_obj or {"name": d_obj.get("name", "Anomalous Object"), "type": "object", "form": d_obj.get("anomaly_form", "impossible_weapon_relic"), "primary_element": d_obj.get("primary_element", "aether")},
                            scen_key=scen_obj,
                            entity_name=str(d_obj.get("name") or "Anomalous Object"),
                        )
                        if conv_out and conv_out.get("notice"):
                            llm_outcome["_combat_resolved_notice"] += f"\n{conv_out['notice']}"
            # Non-incursion hostile folklore kills (quest/bounty climax bosses, wild encounters) still update the
            # session field log, account-wide Folklore Codex (party credit), and singular retirement / species cooldown.
            if isinstance(session, dict) and session.get("id"):
                _record_non_incursion_anomaly_kills(session, party, dead_dicts)
        except Exception:
            pass

    if player_damage_taken > 0:
        acting_name = precomputed.get("acting_char_name", "Hero")
        attackers = precomputed.get("attackers_against_player", [])
        if len(attackers) == 1:
            llm_outcome["_enemy_attack_notice"] = f"💥 **{attackers[0]} Counter-Attack:** Dealt **{player_damage_taken} damage** to {acting_name}"
        elif len(attackers) > 1:
            llm_outcome["_enemy_attack_notice"] = f"💥 **Enemy Counter-Attacks ({', '.join(attackers)}):** Dealt **{player_damage_taken} total damage** to {acting_name}"
        else:
            target_name = enemies[0].get("name", "Enemy") if enemies else "Enemy"
            llm_outcome["_enemy_attack_notice"] = f"💥 **{target_name} Counter-Attack:** Dealt **{player_damage_taken} damage** to {acting_name}"

    # Process next choices
    llm_choices = llm_outcome.get("next_choices") or []

    if enemies and isinstance(llm_choices, list):
        target_m = enemies[0]
        m_stats = target_m.get("stats", {})
        p_stats = precomputed.get("player_stats", {})
        p_luk = p_stats.get("luk", 5)

        # Keep track of labels to prevent duplicates
        seen_labels = set()
        for c in llm_choices:
            if isinstance(c, dict):
                c_stat_name = c.get("stat", "STR")
                c_stat_key = f"{c_stat_name.lower()}_" if c_stat_name in ("STR", "PER", "END", "INT") else c_stat_name.lower()

                p_stat_val = p_stats.get(c_stat_key, 5)
                m_stat_val = m_stats.get(c_stat_name, 3)

                c["requirement"] = calculate_opposed_dc(p_stat_val, m_stat_val, p_luk)

                # Sanitize exact duplicates
                lbl = str(c.get("label", ""))
                if lbl in seen_labels:
                    c["label"] = f"{lbl} (Alternate Approach)"
                seen_labels.add(c["label"])

        # Inject Non-Lethal Persuade/Calm & Subdue & Contain for agitated non-hostile entities AND Born-Hostile Anomalies
        for e_sub in enemies:
            if isinstance(e_sub, dict) and (e_sub.get("requires_non_lethal_subdue") or e_sub.get("is_anomalous_manifestation")) and int(e_sub.get("hp", 0) or 0) > 0:
                e_hp = int(e_sub.get("hp", 10) or 10)
                e_max = max(1, int(e_sub.get("max_hp", 40) or 40))
                e_sap = str(e_sub.get("sapience") or "").strip().lower()
                is_born_h = bool(not e_sub.get("requires_non_lethal_subdue") and e_sub.get("is_anomalous_manifestation"))
                default_sub_pct = 0.50 if (is_born_h and e_sap == "instinctual") else 0.35
                sub_pct = float(e_sub.get("subdue_threshold_pct") or default_sub_pct)
                ent_disp = e_sub.get("name", "Entity")
                can_persuade = bool(e_sub.get("requires_non_lethal_subdue") or e_sap == "sapient")
                if can_persuade:
                    persuade_dc = 6 if (e_hp <= max(1, int(e_max * 0.50)) or bool(e_sub.get("taboo_exploited"))) else 8
                    persuade_lbl = f"🗣️ Persuade / Calm {ent_disp} (De-escalate)"
                    if not any(persuade_lbl.lower() in str(ch.get("label", "")).lower() for ch in llm_choices if isinstance(ch, dict)):
                        llm_choices.insert(0, {
                            "label": persuade_lbl,
                            "stat": "CHA",
                            "requirement": persuade_dc,
                            "mp_cost": 0,
                            "intent": "anomalous_incursion_action",
                            "incursion_action": "combat_persuade",
                            "incursion_id": e_sub.get("incursion_id", ""),
                            "quest_id": e_sub.get("linked_quest_id", ""),
                        })
                if e_hp <= max(1, int(e_max * sub_pct)) or bool(e_sub.get("is_breached")) or bool(e_sub.get("taboo_exploited")):
                    subdue_lbl = f"🛡️ Subdue & Contain {ent_disp}"
                    if not any(subdue_lbl.lower() in str(ch.get("label", "")).lower() for ch in llm_choices if isinstance(ch, dict)):
                        llm_choices.insert(0, {
                            "label": subdue_lbl,
                            "stat": "FREE",
                            "requirement": 0,
                            "mp_cost": 0,
                            "intent": "anomalous_incursion_action",
                            "incursion_action": "subdue",
                            "incursion_id": e_sub.get("incursion_id", ""),
                            "quest_id": e_sub.get("linked_quest_id", ""),
                        })
                # Inject Folklore Vessel/Master Tether Seal & Offering Counter-Rite when applicable
                try:
                    from mechanics.world.folklore_mechanics import (
                        find_matching_offering_in_inventory,
                        get_enemy_tether_state,
                    )
                    ts_cbt = get_enemy_tether_state(e_sub)
                    if ts_cbt and not ts_cbt.get("sealed") and not e_sub.get("tether_sealed"):
                        bp_e = e_sub.get("anomaly_blueprint") if isinstance(e_sub.get("anomaly_blueprint"), dict) else {}
                        if (
                            e_sub.get("tether_reformed_once")
                            or ts_cbt.get("reformed_once")
                            or e_sub.get("dossier_revealed")
                            or bp_e.get("dossier_revealed")
                        ):
                            vessel_nm = str(ts_cbt.get("vessel_name") or "Binding Vessel")
                            sever_lbl = f"🏺 Sever/Seal {vessel_nm} ({ent_disp})"
                            if not any(sever_lbl.lower() in str(ch.get("label", "")).lower() for ch in llm_choices if isinstance(ch, dict)):
                                llm_choices.insert(0, {
                                    "label": sever_lbl,
                                    "stat": str(ts_cbt.get("sever_stat") or "INT"),
                                    "requirement": 7,
                                    "mp_cost": 0,
                                    "intent": "anomalous_incursion_action",
                                    "incursion_action": "sever_tether",
                                    "incursion_id": e_sub.get("incursion_id", ""),
                                    "quest_id": e_sub.get("linked_quest_id", ""),
                                })
                    off_match = find_matching_offering_in_inventory(lead_uid, e_sub.get("anomaly_blueprint"))
                    if off_match:
                        off_lbl = f"🎁 Folklore Counter-Rite: Present {off_match['item_name']} ({ent_disp})"
                        if not any(off_lbl.lower() in str(ch.get("label", "")).lower() for ch in llm_choices if isinstance(ch, dict)):
                            llm_choices.insert(0, {
                                "label": off_lbl,
                                "stat": "INT",
                                "requirement": 5,
                                "mp_cost": 0,
                                "intent": "anomalous_incursion_action",
                                "incursion_action": "folklore_offering_rite",
                                "offering_item_name": off_match["item_name"],
                                "incursion_id": e_sub.get("incursion_id", ""),
                                "quest_id": e_sub.get("linked_quest_id", ""),
                            })
                except Exception:
                    pass
                llm_outcome["next_choices"] = llm_choices
                llm_outcome["choices"] = llm_choices

    # IF ALL ENEMIES DEFEATED -> Clear combat state and ensure dynamic post-combat choices!
    if not enemies:
        if isinstance(session, dict):
            from mechanics.stealth import clear_all_combat_vanished
            clear_all_combat_vanished(session)
        loc = session.get("current_location") or "area"
        llm_choices = llm_outcome.get("next_choices") or llm_outcome.get("choices") or []

        # 1. Dynamically identify or construct the dedicated Free Loot Choice at the top (Slot 1)
        dynamic_loot_label = None
        if isinstance(llm_choices, list):
            for c in llm_choices:
                if isinstance(c, dict):
                    lbl = str(c.get("label", "")).strip()
                    lbl_lower = lbl.lower()
                    if any(kw in lbl_lower for kw in ("loot", "search the fallen", "scavenge the fallen", "search the bodies", "search and loot", "inspect the fallen", "scavenge the remains", "gather spoils")):
                        dynamic_loot_label = lbl
                        break

        if not dynamic_loot_label:
            if dead_enemies and len(dead_enemies) == 1:
                e_name = dead_enemies[0].get("name") if isinstance(dead_enemies[0], dict) else str(dead_enemies[0])
                dynamic_loot_label = f"Search and loot the fallen {e_name}"
            else:
                dynamic_loot_label = "Search and loot the fallen enemies"

        loot_choice = None
        if dead_enemies:
            loot_choice = {
                "label": dynamic_loot_label[:100],
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0
            }

        # 2. Filter LLM's natural scene/conversation/event choices (discarding leftover weapon attack actions against dead foes)
        contextual_choices = []
        if isinstance(llm_choices, list):
            for c in llm_choices:
                if isinstance(c, dict):
                    lbl = str(c.get("label", "")).strip()
                    lbl_lower = lbl.lower()
                    # Skip leftover combat attacks targeting dead hostiles
                    if any(kw in lbl_lower for kw in ("attack", "strike with", "slash with", "thrust into", "fire 9mm", "shoot with", "channel spell against", "roundhouse kick")):
                        continue
                    # Skip duplicate loot options generated by LLM
                    if any(kw in lbl_lower for kw in ("loot", "search the body", "search the bodies", "search the fallen", "inspect the corpse", "strip the gear")):
                        continue
                    contextual_choices.append({
                        "label": lbl[:120],
                        "stat": c.get("stat", "AGI"),
                        "requirement": max(0, min(20, int(c.get("requirement", 5)))),
                        "mp_cost": max(0, int(c.get("mp_cost", 0)))
                    })

        # 3. If LLM returned fewer than 3 valid contextual choices, supplement with procedural scene choices
        if len(contextual_choices) < 3:
            from mechanics.narrative.choice_generator import generate_procedural_scene_choices
            scen_key = session.get("scenario", "fantasy")
            supplements = generate_procedural_scene_choices(scenario=scen_key, location=loc, char=precomputed.get("player_stats"))
            for s in supplements:
                if len(contextual_choices) >= 3:
                    break
                s_lbl = str(s.get("label", "")).strip()
                if not any(s_lbl.lower() in cc["label"].lower() for cc in contextual_choices):
                    contextual_choices.append(s)

        # 4. Final choices: Slot 1 is ALWAYS the Loot Option (if applicable), followed by contextual choices
        if confiscate_anomalous_loot or suppress_non_hostile_loot:
            loot_choice = None
        final_post_combat_choices = ([loot_choice] if loot_choice else []) + contextual_choices[:3]

        llm_outcome["next_choices"] = final_post_combat_choices
        llm_outcome["choices"] = final_post_combat_choices

        # Despawn all active summons immediately upon combat victory so they never linger in exploration scenes
        session["current_npcs"] = [npc for npc in session.get("current_npcs", []) if not npc.get("is_summon")]
        llm_outcome["npcs_present"] = session["current_npcs"]

    # HARD CODE ENFORCEMENT: Strip any clues or note discovery from combat turns
    llm_outcome.pop("_newly_discovered_clue", None)
    if "quest_updates" in llm_outcome and isinstance(llm_outcome["quest_updates"], list):
        for qu in llm_outcome["quest_updates"]:
            if isinstance(qu, dict):
                qu.pop("current_clues", None)

    # Set deterministic character outcomes (PREVENT DOUBLE DAMAGE SUBTRACTION BUG!)
    if "character_outcomes" not in llm_outcome or not isinstance(llm_outcome["character_outcomes"], list):
        llm_outcome["character_outcomes"] = []

    acting_char_name = precomputed.get("acting_char_name", "Hero")
    if not player_damage_by_name:
        player_damage_by_name = {acting_char_name: player_damage_taken}

    player_heal_by_name = precomputed.get("player_heal_by_name", {})
    player_mp_change_by_name = precomputed.get("player_mp_change_by_name", {})
    all_participant_names = set(list(player_damage_by_name.keys()) + list(player_heal_by_name.keys()) + list(player_mp_change_by_name.keys()))

    for p_name in all_participant_names:
        p_dmg = player_damage_by_name.get(p_name, 0)
        p_heal = player_heal_by_name.get(p_name, 0)
        net_hp = p_heal - p_dmg
        p_mp_delta = player_mp_change_by_name.get(p_name, 0)

        items_consumed = precomputed.get("items_consumed", []) if p_name.lower() == acting_char_name.lower() else []
        found = False
        for co in llm_outcome["character_outcomes"]:
            if isinstance(co, dict) and co.get("name", "").lower() == p_name.lower():
                co["hp_change"] = net_hp
                if p_mp_delta != 0 or co.get("mp_change") is None:
                    co["mp_change"] = p_mp_delta
                co["gold_change"] = co.get("gold_change", 0) + total_gold_gain
                co["xp_change"] = co.get("xp_change", 0) + total_xp_gain
                if items_consumed:
                    co.setdefault("items_lost", []).extend(items_consumed)
                found = True
                break
        if not found and (net_hp != 0 or p_mp_delta != 0 or total_xp_gain > 0 or total_gold_gain != 0 or items_consumed):
            llm_outcome["character_outcomes"].append({
                "name": p_name,
                "hp_change": net_hp,
                "mp_change": p_mp_delta,
                "gold_change": total_gold_gain,
                "xp_change": total_xp_gain,
                "items_lost": list(items_consumed) if items_consumed else []
            })
        if total_xp_gain > 0:
            _auth_xp_map = llm_outcome.setdefault("_auth_combat_xp", {})
            _auth_xp_map[p_name.lower()] = int(_auth_xp_map.get(p_name.lower(), 0) or 0) + int(total_xp_gain)

    session_id = session.get("id", 0) if session else 0
    import db
    party_npcs = db.get_session_party_npcs(session_id) if session_id else []

    # If combat victory and player is downed with companions standing, auto-revive at 1 HP
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

    # If hostiles remain and all party players + companions are downed -> Complete Party Defeat Recovery
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

        import scenario_data as _sd_comb
        is_anom_defeat = bool(isinstance(session, dict) and _sd_comb.is_anomalous_incursions_scenario(session.get("scenario", "")))
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
                            "status_effects": ["Exhausted / Recovering"]
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
                    {"label": "Consult with companions about what happened", "stat": "CHA", "requirement": 4, "mp_cost": 0}
                ]
                llm_outcome["choices"] = llm_outcome["next_choices"]

    # Scale companion levels when party gains XP
    if not enemies and total_xp_gain > 0 and party_npcs and party and party[0]:
        import scenario_data as _sd_lvl
        is_anom_lvl = bool(isinstance(session, dict) and _sd_lvl.is_anomalous_incursions_scenario(session.get("scenario", "")))
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
                c["max_hp"] = 15 + c_lvl * 3
                c["max_mp"] = 10 + c_lvl * 2
            c["hp"] = min(c.get("hp", c["max_hp"]), c["max_hp"])
            c["mp"] = min(c.get("mp", c["max_mp"]), c["max_mp"])
            updated_npcs.append(c)
        db.set_session_party_npcs(session_id, updated_npcs)


    # Dynamic Threat Ledger Round Decay & Persistence
    try:
        if not enemies:
            session["combat_threat_ledger"] = {}
            session["combat_boss_telegraph"] = {}
            llm_outcome["combat_threat_ledger"] = {}
            llm_outcome["combat_boss_telegraph"] = {}
            cleanup_anomalous_combat_session_state(session)
        else:
            # Prune dead enemies from threat matrix and boss telegraphs
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

                # Gather downed actor IDs across players, party companions, and temporary allies
                downed_ids: Set[str] = set()

                def _cand_actor_keys(a: Dict[str, Any]) -> Set[str]:
                    keys = set()
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

    return llm_outcome


def cleanup_anomalous_combat_session_state(session: dict) -> None:
    """Purges autonomous constructs, summons, resonance pips, and vanished stealth states when combat ends or is subdued."""
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
    try:
        from mechanics.stealth.core import clear_all_combat_vanished
        clear_all_combat_vanished(session)
    except Exception:
        pass




