from __future__ import annotations
"""
Deterministic Stealth Escalation & Covert Choice Injection.

Handles Phase 3/4 consequences when detection reaches 100% (context-aware
tactical combat vs. active guard/authority confrontation) and injects
covert exploration tactics when Stealth stance is active outside combat.
"""
from typing import Dict, Any, List, Optional

from mechanics.stealth.alert_tracker import ALERT_UNAWARE
from mechanics.stealth.core import (
    any_actor_hidden,
    break_stealth,
    classify_detection_escalation,
    consume_stealth_turn_transients,
    get_session_stealth_state,
    apply_stealth_spatial_transition,
    set_session_stealth_state,
)


def _build_spawned_sentry_enemy(scen_key: str, party_level: int = 1, current_npcs: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Builds a deterministic hostile sentry statblock scaled to party level when 100% detection triggers combat."""
    lvl = max(1, int(party_level or 1))
    scen = str(scen_key or "fantasy").lower()

    # Prefer promoting a hostile/guard NPC already named in the scene if available
    guard_name = ""
    for n in (current_npcs or []):
        if not isinstance(n, dict):
            continue
        r_low = str(n.get("role") or n.get("occupation") or "").lower()
        disp_low = str(n.get("disposition") or "").lower()
        if disp_low == "hostile" or any(k in r_low for k in ("sentry", "guard", "enforcer", "raider", "cultist", "bandit", "watchman", "patrol", "soldier")):
            guard_name = str(n.get("name") or "").strip()
            break

    if not guard_name:
        if "cyber" in scen:
            guard_name = "CorpSec Patrol Enforcer"
        elif "sci" in scen or "space" in scen:
            guard_name = "Sector Security Sentry"
        elif "anom" in scen or "incursion" in scen:
            guard_name = "Breach Perimeter Stalker"
        elif "post" in scen or "apoc" in scen:
            guard_name = "Wasteland Lookout"
        elif "steam" in scen:
            guard_name = "Clockwork Watchman"
        else:
            guard_name = "Alerted Guard Sentry"

    base_hp = 35 + (lvl * 12)
    stat_base = min(10, 3 + (lvl // 2))
    return {
        "name": guard_name,
        "archetype": "Skirmisher",
        "level": lvl,
        "hp": base_hp,
        "max_hp": base_hp,
        "intent": "Pressing the alarm and engaging intruders!",
        "status_effects": ["Alerted"],
        "stats": {
            "STR": stat_base + 1,
            "PER": stat_base + 2,
            "END": stat_base + 1,
            "CHA": max(2, stat_base - 1),
            "INT": stat_base,
            "AGI": stat_base + 1,
            "LUK": 3,
        },
    }


def _resolve_confrontation_authority_npc(session: Dict[str, Any], outcome: Dict[str, Any], scen_key: str) -> Dict[str, Any]:
    """Selects an existing scene authority/bystander or spawns a fitting local authority NPC for 100% apprehension."""
    npcs = [n for n in (outcome.get("npcs_present") or session.get("current_npcs") or []) if isinstance(n, dict) and n.get("name")]
    for n in npcs:
        r_low = str(n.get("role") or n.get("occupation") or "").lower()
        if any(k in r_low for k in ("guard", "watch", "officer", "security", "teacher", "prefect", "monitor", "warden", "shopkeeper", "innkeeper", "barkeep", "staff")):
            promoted = dict(n)
            promoted["stage_role"] = "active_partner"
            promoted["attention_ring"] = "ring_1_primary"
            effs = list(promoted.get("status_effects") or [])
            if "Alerted" not in effs:
                effs.append("Alerted")
            promoted["status_effects"] = effs
            return promoted

    if npcs:
        promoted = dict(npcs[0])
        promoted["stage_role"] = "active_partner"
        promoted["attention_ring"] = "ring_1_primary"
        effs = list(promoted.get("status_effects") or [])
        if "Alerted" not in effs:
            effs.append("Alerted")
        promoted["status_effects"] = effs
        return promoted

    scen = str(scen_key or "fantasy").lower()
    if any(k in scen for k in ("high_school", "highschool", "school", "academy")):
        name, role = "Officer Takahashi", "Campus Security Officer"
    elif "slice_of_life" in scen:
        name, role = "Officer Sato", "Neighborhood Patrol Officer"
    elif "cyber" in scen:
        name, role = "Officer Vance", "District Precinct Patrol"
    else:
        name, role = "Captain Aldric", "Town Watch Patrol"

    return {
        "name": name,
        "role": role,
        "disposition": "suspicious",
        "stage_role": "active_partner",
        "attention_ring": "ring_1_primary",
        "status_effects": ["Alerted"],
    }


def build_confrontation_choices(authority_name: str, scen_key: str) -> List[Dict[str, Any]]:
    """Builds the 4 deterministic apprehension confrontation choices when spotted in a non-hostile/civilian zone."""
    scen = str(scen_key or "fantasy").lower()
    is_school = any(k in scen for k in ("high_school", "highschool", "school", "academy", "slice_of_life"))

    choices: List[Dict[str, Any]] = [
        {
            "label": f"Offer a calm, believable excuse to {authority_name} to defuse suspicion",
            "stat": "CHA",
            "requirement": 7,
            "mp_cost": 0,
            "intent": "dialogue_turn",
            "target_npc": authority_name,
            "_server_stamped": True,
        },
    ]
    if is_school:
        choices.append({
            "label": f"Cite an urgent faculty or club errand to justify being here to {authority_name}",
            "stat": "INT",
            "requirement": 7,
            "mp_cost": 0,
            "intent": "dialogue_turn",
            "target_npc": authority_name,
            "_server_stamped": True,
        })
    else:
        choices.append({
            "label": f"Slip {authority_name} a discreet 15-gold bribe to look the other way",
            "stat": "CHA",
            "requirement": 6,
            "mp_cost": 0,
            "gold_cost": 15,
            "intent": "dialogue_turn",
            "target_npc": authority_name,
            "_server_stamped": True,
        })

    choices.extend([
        {
            "label": f"Break line-of-sight and sprint away from {authority_name}",
            "stat": "AGI",
            "requirement": 7,
            "mp_cost": 0,
            "intent": "general_action",
            "_server_stamped": True,
        },
        {
            "label": f"Comply quietly with {authority_name} and step out peacefully",
            "stat": "NONE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "dialogue_exit",
            "target_npc": authority_name,
            "_server_stamped": True,
        },
    ])
    return choices


def inject_covert_exploration_choices(
    choices: List[Dict[str, Any]],
    session: Optional[Dict[str, Any]],
    max_total: int = 6,
) -> List[Dict[str, Any]]:
    """
    Injects dedicated covert tactical choices when Stealth stance is active outside combat
    (Blueprint Section 6), without clobbering quest-tagged, barrier, or trailing FREE utility choices.
    """
    if not isinstance(session, dict) or not any_actor_hidden(session):
        return choices

    from mechanics.combat import is_in_combat
    if is_in_combat(session):
        return choices

    st = get_session_stealth_state(session)
    if st.get("detection_meter", 0) >= 100 or st.get("alert_level") == "detected":
        return choices

    base = [dict(c) for c in (choices or []) if isinstance(c, dict)]
    existing_low = " ".join(str(c.get("label") or "").lower() for c in base)

    covert_additions: List[Dict[str, Any]] = []
    if not any(k in existing_low for k in ("shadow step", "sneak", "slip past", "creep")):
        covert_additions.append({
            "label": "Shadow Step — Slip quietly through cover past nearby sightlines",
            "stat": "AGI",
            "requirement": 6,
            "mp_cost": 0,
            "intent": "stealth_covert",
            "action_category": "stealth",
            "is_stealth": True,
            "stance": "stealth",
            "_server_stamped": True,
        })

    meter = int(st.get("detection_meter", 0) or 0)
    if meter > 0:
        if "freeze & blend" not in existing_low and "hold still" not in existing_low:
            covert_additions.append({
                "label": "Freeze & Blend — Hold motionless in shadow to let suspicion cool",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "stealth_covert",
                "action_category": "stealth",
                "is_stealth": True,
                "stance": "stealth",
                "_server_stamped": True,
            })
        if not any(k in existing_low for k in ("distract", "diversion", "pebble", "stone")):
            if not st.get("free_distraction_used", False):
                covert_additions.append({
                    "label": "Toss a small noise distraction to lure sentries away",
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "stealth_covert",
                    "action_category": "stealth",
                    "is_stealth": True,
                    "stance": "stealth",
                    "_server_stamped": True,
                })
            else:
                covert_additions.append({
                    "label": "Improvise a contested diversion to misdirect wary guards",
                    "stat": "AGI",
                    "requirement": 7,
                    "mp_cost": 0,
                    "intent": "stealth_covert",
                    "action_category": "stealth",
                    "is_stealth": True,
                    "stance": "stealth",
                    "_server_stamped": True,
                })

    if not covert_additions:
        return base

    # Keep FREE utility actions (Observe, Redress, Put down) anchored at the tail
    utility_free = [c for c in base if str(c.get("stat") or "").upper() == "FREE"]
    core_base = [c for c in base if c not in utility_free]
    pinned = [c for c in core_base if c.get("is_quest_action") or c.get("is_climax_action") or c.get("_priority_slot")]
    regular = [c for c in core_base if c not in pinned]

    selected_covert = covert_additions[:2]
    budget_for_regular = max(1, max_total - len(pinned) - len(selected_covert))
    merged_core = (pinned + regular[:budget_for_regular] + selected_covert)[:max_total]
    return merged_core + utility_free


def reduce_stealth_turn_outcome(
    session_id: int,
    session: Optional[Dict[str, Any]],
    party: List[Any],
    outcome: Dict[str, Any],
    actions: List[Dict[str, Any]],
    scen_key: str,
    is_combat: bool,
) -> None:
    """
    Phase 4 Atomic Stealth Reducer (runs inside apply_outcome's UnitOfWork):
    1. Merges in-turn stealth mutations (combat_vanished, CastPlanner, TurnService).
    2. Applies spatial suspicion reset (0% on facility exit) or halving (// 2 in adjacent room).
    3. Syncs failed access_gate stealth breaches.
    4. Executes context-aware 100% detection escalation (combat spawn vs. authority confrontation).
    5. Injects covert exploration choices when Stealth remains active outside combat.
    6. Consumes single-turn alert transients and persists stealth_state to SQLite.
    """
    if not isinstance(session, dict) or not isinstance(outcome, dict):
        return

    import db

    # 1. Merge latest in-turn stealth_state (from combat/core.py, CastPlanner, or action)
    if isinstance(outcome.get("stealth_state"), dict):
        set_session_stealth_state(session, outcome["stealth_state"])
    else:
        for a in reversed(actions or []):
            if isinstance(a, dict) and isinstance(a.get("stealth_state"), dict):
                set_session_stealth_state(session, a["stealth_state"])
                break

    st = get_session_stealth_state(session)

    # 2. Evaluate 100% detection escalation flags first so spatial transitions never erase blown cover
    trigger_combat = False
    trigger_confrontation = False
    for a in (actions or []):
        if isinstance(a, dict) and isinstance(a.get("stealth_outcome"), dict):
            so = a["stealth_outcome"]
            if so.get("trigger_combat"):
                trigger_combat = True
            if so.get("trigger_confrontation"):
                trigger_confrontation = True

    if not (trigger_combat or trigger_confrontation) and (st.get("detection_meter", 0) >= 100 or st.get("alert_level") == "detected"):
        trigger_combat, trigger_confrontation = classify_detection_escalation(session)

    # 3. Spatial suspicion transition (0% on facility/zone exit; // 2 on clean same-facility room hop)
    prev_node_id = session.get("current_node_id")
    prev_loc = str(session.get("current_location") or "")
    new_node_id = outcome.get("current_node_id") or prev_node_id
    new_loc = str(outcome.get("location") or prev_loc)
    moved_spatially = bool((new_node_id and new_node_id != prev_node_id) or (new_loc and new_loc != prev_loc))
    if moved_spatially and not (trigger_combat or trigger_confrontation):
        raised_this_turn = (st.get("alert_event") == "suspicion_raised")
        if not raised_this_turn:
            apply_stealth_spatial_transition(
                session,
                prev_node_id=prev_node_id,
                new_node_id=new_node_id,
                prev_location=prev_loc,
                new_location=new_loc,
            )
            st = get_session_stealth_state(session)
        else:
            # Even on a noisy room entry, reset per-room distraction allowance for the new room;
            # if leaving the facility completely, still clear old facility pursuit.
            from mechanics.stealth.core import _resolve_node_facility_key
            _, prev_fac = _resolve_node_facility_key(session.get("id"), prev_node_id, prev_loc)
            _, new_fac = _resolve_node_facility_key(session.get("id"), new_node_id, new_loc)
            if prev_fac and new_fac and prev_fac != new_fac:
                apply_stealth_spatial_transition(
                    session,
                    prev_node_id=prev_node_id,
                    new_node_id=new_node_id,
                    prev_location=prev_loc,
                    new_location=new_loc,
                )
                st = get_session_stealth_state(session)
            else:
                st["free_distraction_used"] = False
                set_session_stealth_state(session, st)

    # 4. Sync failed access_gate breach patrol confrontations
    gate_res = outcome.get("_access_gate_result") if isinstance(outcome.get("_access_gate_result"), dict) else {}
    if gate_res.get("patrol_confrontation") and any_actor_hidden(session):
        break_stealth(session, reason="caught_at_restricted_gate", break_all=True)
        st = get_session_stealth_state(session)

    if not is_combat and (trigger_combat or trigger_confrontation):
        break_stealth(session, reason="detected_at_100_percent", break_all=True)
        st = get_session_stealth_state(session)

        if trigger_combat:
            existing_enemies = [
                e for e in (outcome.get("nearby_enemies") or session.get("nearby_enemies") or [])
                if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0
            ]
            if not existing_enemies:
                avg_lvl = 1
                if party:
                    lvls = [int((c[0] if isinstance(c, (list, tuple)) else c).get("level", 1) or 1) for c in party if isinstance(c[0] if isinstance(c, (list, tuple)) else c, dict)]
                    if lvls:
                        avg_lvl = max(1, sum(lvls) // len(lvls))
                spawned = _build_spawned_sentry_enemy(
                    scen_key,
                    party_level=avg_lvl,
                    current_npcs=outcome.get("npcs_present") or session.get("current_npcs") or [],
                )
                existing_enemies = [spawned]

            outcome["nearby_enemies"] = existing_enemies
            session["nearby_enemies"] = existing_enemies
            outcome["is_ambush"] = False
            session["is_ambush"] = False
            outcome["dialogue_partner"] = None
            outcome["dialogue_partners"] = []
            outcome.pop("_hybrid_choices_built", None)
            alert_callout = f"🚨 **Cover Blown!** **{existing_enemies[0]['name']}** spots your movement and moves to engage!"
            curr_next = str(outcome.get("next_narrative") or outcome.get("narrative") or "").strip()
            if "Cover Blown!" not in curr_next:
                outcome["next_narrative"] = f"{curr_next}\n\n{alert_callout}".strip() if curr_next else alert_callout

        elif trigger_confrontation:
            auth_npc = _resolve_confrontation_authority_npc(session, outcome, scen_key)
            npcs_list = [dict(n) for n in (outcome.get("npcs_present") or session.get("current_npcs") or []) if isinstance(n, dict)]
            auth_low = auth_npc["name"].strip().lower()
            replaced = False
            for idx, n in enumerate(npcs_list):
                if str(n.get("name") or "").strip().lower() == auth_low:
                    npcs_list[idx] = auth_npc
                    replaced = True
                    break
            if not replaced:
                npcs_list.insert(0, auth_npc)
            outcome["npcs_present"] = npcs_list
            outcome["dialogue_partner"] = auth_npc["name"]
            outcome["dialogue_partners"] = [auth_npc["name"]]
            conf_choices = build_confrontation_choices(auth_npc["name"], scen_key)
            outcome["choices"] = conf_choices
            outcome["next_choices"] = conf_choices
            outcome["_hybrid_choices_built"] = True
            alert_callout = f"⚠️ **Spotted!** **{auth_npc['name']}** steps into your path and demands an explanation."
            curr_next = str(outcome.get("next_narrative") or outcome.get("narrative") or "").strip()
            if "Spotted!" not in curr_next and auth_npc["name"].lower() not in curr_next.lower():
                outcome["next_narrative"] = f"{curr_next}\n\n{alert_callout}".strip() if curr_next else alert_callout

    # 5. Inject covert exploration choices when Stealth remains active outside combat
    elif not is_combat and any_actor_hidden(session) and not outcome.get("nearby_enemies"):
        from mechanics.social.physical_state import is_erotic_intimate_contact
        phys_d = outcome.get("_physical_state") if isinstance(outcome.get("_physical_state"), dict) else {}
        ic_str = str(phys_d.get("intimate_contact") or "")
        if not is_erotic_intimate_contact(ic_str):
            cur_choices = outcome.get("next_choices") or outcome.get("choices") or []
            if isinstance(cur_choices, list) and cur_choices:
                enriched_covert = inject_covert_exploration_choices(cur_choices, session)
                outcome["choices"] = enriched_covert
                outcome["next_choices"] = enriched_covert

    # 6. Consume one-turn transients & persist stealth_state atomically to SQLite
    consume_stealth_turn_transients(session)
    outcome["stealth_state"] = dict(session["stealth_state"])
    if session_id:
        db.update_session(session_id, stealth_state=session["stealth_state"])
