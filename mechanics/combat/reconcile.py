from __future__ import annotations
"""
Post-LLM combat reconciliation, defeat routing, loot distribution, and session state cleanup.
"""
import logging
import random
from typing import Any, Dict, List, Optional

import db
import scenario_data
from .formulas import (
    calculate_opposed_dc,
)
from .status_effects import normalize_status_effect
from .post_combat import (
    cleanup_anomalous_combat_session_state,  # static-check: ignore[unused-import]
    decay_round_threat,  # static-check: ignore[unused-import]
    finalize_post_combat_state,
    prune_dead_combat_state,  # static-check: ignore[unused-import]
)

logger = logging.getLogger(__name__)


def _check_feral_hunt(
    session_id: int,
    session: Dict[str, Any] | None,
    dead_enemies: List[Any],
) -> tuple[Dict[str, Any], ...]:
    """Returns `(feral_mod,)` when Feral Al-Ghul Pack Hunt is active and feral enemies fell in Barrowlands/Mire."""
    from mechanics.world.world_events.spirit_realm_events import (
        get_feral_ghul_hunt_modifiers,
        is_feral_spirit_pack_enemy,
    )
    nid = str((session or {}).get("current_node_id") or "")
    mod = get_feral_ghul_hunt_modifiers(session_id, nid)
    if not mod.get("active"):
        return ()
    if not any(is_feral_spirit_pack_enemy(de) for de in (dead_enemies or [])):
        return ()
    return (mod,)

def award_post_combat_auto_loot(
    session: Dict[str, Any],
    party: Optional[List[Any]],
    dead_enemies: List[Any],
    llm_outcome: Dict[str, Any],
    *,
    confiscated: bool = False,
    killed_non_hostiles_count: int = 0,
    persist_db: bool = True,
) -> List[str]:
    """
    Immediately rolls and awards level-scaled post-combat spoils per living party member
    upon victory (unless confiscated or all defeated targets were non-hostile).
    Overflow when a player's backpack is full is handled by reducers.py into dropped_items.
    """
    if confiscated or not dead_enemies or killed_non_hostiles_count >= len(dead_enemies):
        return []
    if not isinstance(llm_outcome, dict):
        return []

    scen_key = str((session or {}).get("scenario") or "fantasy").strip() or "fantasy"
    from mechanics.combat.items.consumables.generators import generate_random_consumable
    from mechanics.combat.items import generate_random_equipment

    c_outcomes = llm_outcome.setdefault("character_outcomes", [])
    auth_loot = llm_outcome.setdefault("_authorized_loot", [])
    auth_meta = llm_outcome.setdefault("_authorized_loot_meta", {})

    # Estimate highest tier from defeated enemies
    max_tier = 3
    for de in dead_enemies:
        if isinstance(de, dict):
            t_val = de.get("tier") or de.get("tier_rank")
            if isinstance(t_val, int):
                max_tier = min(max_tier, max(1, min(3, t_val)))

    # Active Veiled World Event hook: Feral Al-Ghul Pack Hunt boosts loot tier & awards +5 cull rep
    sess_id = int((session or {}).get("id") or 0)
    if sess_id and any(is_feral := _check_feral_hunt(sess_id, session, dead_enemies)):
        feral_mod = is_feral[0]
        if feral_mod.get("loot_tier_bonus"):
            max_tier = max(1, max_tier - int(feral_mod["loot_tier_bonus"]))
        cull_rep = int(feral_mod.get("cull_rep_bonus") or 0)
        if cull_rep > 0 and persist_db:
            try:
                from mechanics.world.locations.folklore_spirit_courts import (
                    SPIRIT_COURT_FACTIONS,
                    adjust_spirit_court_reputation,
                )
                target_vk = "ghoul" if db.get_faction(sess_id, SPIRIT_COURT_FACTIONS["ghoul"]["faction_id"]) else next(
                    (
                        vk for vk in ("kitsune", "bunian", "ghoul")
                        if db.get_faction(sess_id, SPIRIT_COURT_FACTIONS[vk]["faction_id"])
                    ),
                    "ghoul",
                )
                adj_feral = adjust_spirit_court_reputation(
                    sess_id,
                    target_vk,
                    cull_rep,
                    reason="feral_ghul_pack_hunt_cull",
                )
                llm_outcome["_feral_hunt_cull_bonus"] = {
                    "village_key": target_vk,
                    "rep_gained": int(adj_feral.get("delta") or cull_rep),
                    "loot_tier_boosted": int(feral_mod.get("loot_tier_bonus") or 0),
                }
            except Exception as _feral_exc:
                logger.warning("Feral hunt cull rep award skipped for session %s: %s", sess_id, _feral_exc)

    loot_display_names: List[str] = []
    living_chars: List[Dict[str, Any]] = []
    for p_entry in (party or []):
        c_dict = p_entry[0] if isinstance(p_entry, (tuple, list)) and p_entry else (p_entry if isinstance(p_entry, dict) else None)
        if not isinstance(c_dict, dict) or not c_dict.get("name"):
            continue
        p_nm = str(c_dict["name"]).strip()
        cur_hp = int(c_dict.get("hp", 10) if c_dict.get("hp") is not None else 10)
        matching_co = next(
            (co for co in c_outcomes if isinstance(co, dict) and str(co.get("name") or "").strip().lower() == p_nm.lower()),
            None,
        )
        proj_hp = cur_hp + (int(matching_co.get("hp_change", 0) or 0) if matching_co else 0)
        if proj_hp > 0:
            living_chars.append(c_dict)

    for c_dict in living_chars:
        p_nm = str(c_dict["name"]).strip()
        p_lvl = max(1, int(c_dict.get("level", 1) or 1))
        p_luk = int(c_dict.get("luk", c_dict.get("luk_", 5)) or 5)

        drops: List[Dict[str, Any]] = []
        try:
            cons = generate_random_consumable(scenario=scen_key, party_level=p_lvl)
            if isinstance(cons, dict) and cons.get("name"):
                drops.append(cons)
        except Exception:
            pass

        equip_chance = 0.25 + max(0, p_luk - 5) * 0.02 + (0.15 if len(dead_enemies) > 1 or max_tier < 3 else 0.0)
        if random.random() < min(0.75, equip_chance):
            try:
                eq_slot = random.choice(("Weapon", "Armor", "Accessory 1", "Gloves", "Shoes"))
                eq_tier = max_tier if random.random() < 0.5 else (1 if p_lvl >= 10 else (2 if p_lvl >= 5 else 3))
                eq = generate_random_equipment(scenario=scen_key, slot=eq_slot, tier=eq_tier)
                if isinstance(eq, dict) and eq.get("name"):
                    drops.append(eq)
            except Exception:
                pass

        if not drops:
            continue

        co_entry = next(
            (co for co in c_outcomes if isinstance(co, dict) and str(co.get("name") or "").strip().lower() == p_nm.lower()),
            None,
        )
        if co_entry is None:
            co_entry = {"name": p_nm, "hp_change": 0, "mp_change": 0, "gold_change": 0, "xp_change": 0, "items_gained": []}
            c_outcomes.append(co_entry)
        gained_list = co_entry.setdefault("items_gained", [])

        for drop in drops:
            d_name = str(drop["name"]).strip()
            if not d_name:
                continue
            gained_list.append(d_name)
            if d_name not in auth_loot:
                auth_loot.append(d_name)
            auth_meta[d_name.lower()] = {
                "name": d_name,
                "item_type": str(drop.get("item_type") or "Potion"),
                "effect": str(drop.get("effect") or drop.get("description") or ""),
                "slot_cost": int(drop["slot_cost"]) if drop.get("slot_cost") is not None else 1,
            }
            loot_display_names.append(d_name)

    if loot_display_names:
        cur_notice = str(llm_outcome.get("_combat_resolved_notice") or "").strip()
        spoils_line = f"🎒 **Spoils Recovered:** {', '.join(loot_display_names)}"
        if spoils_line not in cur_notice:
            llm_outcome["_combat_resolved_notice"] = f"{cur_notice}\n{spoils_line}".strip()
    return loot_display_names


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
            logger.warning("Folklore codex kill record failed for %s: %s", d.get("name"), rec_err)


def reconcile_combat_results(
    session: dict,
    llm_outcome: dict,
    precomputed: dict,
    party: list = None,
    *,
    persist_db: bool = True,
) -> dict:
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
        if "party_npcs" in precomputed:
            session["party_npcs"] = precomputed["party_npcs"]
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
                            db.apply_hp_mp_delta(lead_uid, gold_delta=g_gain, session_id=sess_id_int)
                            db.add_xp(lead_uid, x_gain, session_id=sess_id_int)
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
                        _roll_optional_incursion_gear_drop(lead_uid, scen_rec, session_id=sess_id_int)
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
                from mechanics.world.anomalous_sites import complete_site_pacification
                _lead_uid_sb = party[0][0].get("user_id") if (party and party[0] and isinstance(party[0][0], dict)) else session.get("host_user_id")
                _party_uids_sb = [p[0].get("user_id") for p in (party or []) if isinstance(p, (tuple, list)) and isinstance(p[0], dict) and p[0].get("user_id")]
                _scen_sb = str(session.get("scenario") or "anomalous_incursions")
                _day_sb = int(session.get("current_day", 1) or 1)
                _turn_sb = len(session.get("history") or []) + 1
                _seen_sites_sb: set[str] = set()
                for _d_sb in dead_dicts:
                    if not isinstance(_d_sb, dict) or _d_sb.get("requires_non_lethal_subdue"):
                        continue
                    if not _d_sb.get("is_site_locus_boss"):
                        continue
                    _sid_sb = str(_d_sb.get("anomalous_site_id") or session.get("current_node_id") or "").strip()
                    if not _sid_sb or _sid_sb in _seen_sites_sb:
                        continue
                    _seen_sites_sb.add(_sid_sb)
                    _pac_sb = complete_site_pacification(
                        int(session["id"]),
                        _sid_sb,
                        user_id=int(_lead_uid_sb or 1),
                        method="locus_boss_slain",
                        scen_key=_scen_sb,
                        current_day=_day_sb,
                        turn_number=_turn_sb,
                        party_user_ids=_party_uids_sb or None,
                    )
                    if isinstance(_pac_sb, dict) and _pac_sb.get("message"):
                        llm_outcome["_combat_resolved_notice"] += f"\n{_pac_sb['message']}"
                _wp_bonus_rec = max((float(d.get("anomalous_loot_bonus") or 0.0) for d in dead_dicts if isinstance(d, dict)), default=0.0)
                if _wp_bonus_rec > 0 and not confiscate_anomalous_loot and _lead_uid_sb and random.random() < _wp_bonus_rec:
                    from mechanics.combat.items import generate_random_equipment
                    _wp_tier = 1 if random.random() < 0.35 else 2
                    _wp_slot = random.choice(("Weapon", "Armor", "Shield", "Accessory 1"))
                    _wp_eq = generate_random_equipment(scenario=_scen_sb, slot=_wp_slot, tier=_wp_tier, force_anomalous=True)
                    if isinstance(_wp_eq, dict) and _wp_eq.get("name"):
                        db.add_item(
                            int(_lead_uid_sb),
                            name=str(_wp_eq["name"]),
                            item_type=str(_wp_eq.get("item_type") or "equipment").lower(),
                            effect=str(_wp_eq.get("effect") or _wp_eq.get("description") or ""),
                            slot_cost=int(_wp_eq.get("slot_cost") or 1),
                            force=True,
                            session_id=int(session["id"]),
                        )
                        llm_outcome["_combat_resolved_notice"] += f"\n🎡 **Witching Peak Relic Salvage:** Recovered **`{_wp_eq['name']}`**!"
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

        # 1. Filter LLM's natural scene/conversation/event choices (discarding leftover combat attacks & obsolete post-combat loot prompts)
        contextual_choices = []
        if isinstance(llm_choices, list):
            for c in llm_choices:
                if isinstance(c, dict):
                    lbl = str(c.get("label", "")).strip()
                    lbl_lower = lbl.lower()
                    if any(kw in lbl_lower for kw in ("attack", "strike with", "slash with", "thrust into", "fire 9mm", "shoot with", "channel spell against", "roundhouse kick")):
                        continue
                    if any(kw in lbl_lower for kw in ("loot", "search the body", "search the bodies", "search the fallen", "inspect the corpse", "strip the gear", "gather spoils")):
                        continue
                    contextual_choices.append({
                        "label": lbl[:120],
                        "stat": c.get("stat", "AGI"),
                        "requirement": max(0, min(20, int(c.get("requirement", 5)))),
                        "mp_cost": max(0, int(c.get("mp_cost", 0)))
                    })

        # 2. If LLM returned fewer than 3 valid contextual choices, supplement with procedural scene choices
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

        final_post_combat_choices = contextual_choices[:4]

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
    player_status_sync_by_name = precomputed.get("player_status_sync_by_name", {})
    all_participant_names = set(
        list(player_damage_by_name.keys())
        + list(player_heal_by_name.keys())
        + list(player_mp_change_by_name.keys())
        + list(player_status_sync_by_name.keys())
    )

    for p_name in all_participant_names:
        p_dmg = player_damage_by_name.get(p_name, 0)
        p_heal = player_heal_by_name.get(p_name, 0)
        net_hp = p_heal - p_dmg
        p_mp_delta = player_mp_change_by_name.get(p_name, 0)
        synced_statuses = list(player_status_sync_by_name.get(p_name) or [])

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
                if synced_statuses:
                    existing_st = co.setdefault("status_effects", [])
                    seen_names = {normalize_status_effect(s)["name"].strip().lower() for s in existing_st}
                    for st_entry in synced_statuses:
                        st_low = normalize_status_effect(st_entry)["name"].strip().lower()
                        if st_low and st_low not in seen_names:
                            existing_st.append(st_entry)
                            seen_names.add(st_low)
                found = True
                break
        if not found and (net_hp != 0 or p_mp_delta != 0 or total_xp_gain > 0 or total_gold_gain != 0 or items_consumed or synced_statuses):
            co_new: Dict[str, Any] = {
                "name": p_name,
                "hp_change": net_hp,
                "mp_change": p_mp_delta,
                "gold_change": total_gold_gain,
                "xp_change": total_xp_gain,
                "items_lost": list(items_consumed) if items_consumed else [],
            }
            if synced_statuses:
                co_new["status_effects"] = list(synced_statuses)
            llm_outcome["character_outcomes"].append(co_new)
        if total_xp_gain > 0:
            _auth_xp_map = llm_outcome.setdefault("_auth_combat_xp", {})
            _auth_xp_map[p_name.lower()] = int(_auth_xp_map.get(p_name.lower(), 0) or 0) + int(total_xp_gain)

    if dead_enemies and not enemies:
        award_post_combat_auto_loot(
            session,
            party,
            dead_enemies,
            llm_outcome,
            confiscated=confiscate_anomalous_loot,
            killed_non_hostiles_count=len(killed_non_hostiles),
            persist_db=persist_db,
        )

    finalize_post_combat_state(
        session=session,
        llm_outcome=llm_outcome,
        enemies=enemies,
        party=party,
        total_xp_gain=total_xp_gain,
        dead_enemies=dead_enemies,
        dead_enemy_dicts_rec=dead_enemy_dicts_rec,
        persist_db=persist_db,
    )
    if dead_enemies and isinstance(session, dict) and session.get("id"):
        try:
            from mechanics.social.epistemic_engine import neutralize_witnesses_from_combat_or_skill
            _is_nl = bool(session.get("non_lethal_combat") or session.get("non_lethal_mode"))
            _dead_items = list(dead_enemy_dicts_rec or dead_enemies or [])
            _ko_npcs = [d for d in _dead_items if isinstance(d, dict) and (d.get("knocked_out") or d.get("non_lethal") or _is_nl)] if not _is_nl else _dead_items
            _ko_set = {str(d.get("name") if isinstance(d, dict) else d).strip().lower() for d in _ko_npcs}
            _kill_npcs = [d for d in _dead_items if str(d.get("name") if isinstance(d, dict) else d).strip().lower() not in _ko_set]
            _surviving_w = [
                n for n in list(session.get("current_npcs") or []) + list(enemies or [])
                if isinstance(n, dict) and not n.get("is_summon")
                and str(n.get("name") or "").strip().lower() not in {
                    str(x.get("name") if isinstance(x, dict) else x).strip().lower() for x in _dead_items
                }
            ]
            neutralize_witnesses_from_combat_or_skill(
                int(session["id"]),
                _ko_npcs,
                _kill_npcs,
                present_witnesses=_surviving_w,
                turn=int(session.get("turn_count") or 0),
                location_node_id=str(session.get("current_node_id") or ""),
                mode="non_lethal" if _is_nl else "combat",
            )
            llm_outcome["_b17_neutralized"] = True
        except Exception:
            pass
    return llm_outcome

    




