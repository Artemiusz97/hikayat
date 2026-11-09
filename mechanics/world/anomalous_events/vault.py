from __future__ import annotations
"""
Object Anomaly relic conversion (with full-inventory floor/vault overflow protection)
and Containment Vault flavor/codex logging.
"""
import hashlib
import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data
from mechanics.world.anomaly_engine import (
    ANOMALOUS_9_ELEMENTS,
    NON_HOSTILE_TEMPERAMENT_TYPES,
    evaluate_taboo_interaction,
    format_anomaly_dossier_summary,
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
    parse_blueprint_from_notes,
    serialize_blueprint_note,
)
from mechanics.world.folklore_mechanics import (
    build_dialogue_trap_choices,
    build_offering_counter_rite_choice,
    consume_folklore_offering_item,
    evaluate_dialogue_trap_response,
    evaluate_omen_paradox,
    find_matching_offering_in_inventory,
    get_enemy_tether_state,
    get_public_anomaly_name,
    has_active_dialogue_trap,
    is_blueprint_disguised,
    seal_enemy_tether,
    unmask_blueprint_disguise,
)

from .generation import _resolve_session_turn_number
from .inquiries import _prune_anomaly_from_scene_npcs

logger = logging.getLogger(__name__)


def handle_secured_object_anomaly_conversion(
    session_id: int,
    user_id: Optional[int],
    blueprint: Optional[Dict[str, Any]],
    scen_key: str = "anomalous_incursions",
    entity_name: str = "",
    *,
    skip_codex_progress: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Converts a secured or neutralized `object` anomaly into a usable `[Anomalous]` Weapon, Accessory, or Wearable:
    - Private Agencies (`private_agency_1`, `private_agency_2`), Monastic Order (`monastic_order`), & Freelancers (`freelancer`):
      Immediately keep the converted `[Anomalous]` relic in player inventory!
    - Public Agency (`public_agency`):
      Logs the relic to the Bureau Containment Vault (`session['anomalous_vault_requisitions']`), awards `+5` Promotion Rep,
      and unlocks it for **50%-off Requisition** at the HQ Tactical Armory (`loc_hq_tactical_armory`)!
    """
    from mechanics.combat.items.anomalous_gear import convert_object_anomaly_to_gear
    from mechanics.social.factions import get_anomalous_faction_state, update_agent_promotion_reputation

    bp = dict(blueprint) if isinstance(blueprint, dict) else {}
    anom_type = str(bp.get("type") or bp.get("anomaly_type") or "").strip().lower()
    if anom_type != "object":
        return None
    if entity_name and not bp.get("name"):
        bp["name"] = entity_name

    gear_item = convert_object_anomaly_to_gear(bp, scenario=scen_key)
    if session_id and not skip_codex_progress:
        try:
            sess_obj_log = db.get_session(session_id) or {}
            db.record_session_anomaly_field_log(
                session_id,
                bp,
                stage="contained",
                location=str(sess_obj_log.get("current_location") or ""),
                resolution_method="Object Relic Secured & Converted",
            )
            if bp.get("codex_id"):
                uids_obj = db.get_session_participant_user_ids(session_id) or ([int(user_id)] if user_id else [])
                db.record_folklore_codex_progress(uids_obj, str(bp["codex_id"]), stage="contained")
                db.retire_or_cooldown_folklore_in_session(
                    session_id,
                    str(bp["codex_id"]),
                    uniqueness=str(bp.get("uniqueness") or "species"),
                    current_day=int(sess_obj_log.get("current_day") or sess_obj_log.get("in_game_day") or 1),
                    cooldown_days=int(bp.get("cooldown_days", 4) or 4),
                )
        except Exception as exc:
            logger.warning("Failed to record object anomaly codex/field-log progress for session %s: %s", session_id, exc)
    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    if arch == "public_agency":
        sess = db.get_session(session_id) or {}
        t_cur = _resolve_session_turn_number(session_id, sess)
        gear_item["turn_captured"] = t_cur
        gear_item["first_turn"] = t_cur
        req_list = list(sess.get("anomalous_vault_requisitions") or [])
        if not any(isinstance(r, dict) and r.get("name") == gear_item["name"] for r in req_list):
            req_list.append(gear_item)
            db.update_session(session_id, extra={"anomalous_vault_requisitions": req_list})
        update_agent_promotion_reputation(
            session_id=session_id,
            delta_rep=5,
            reason=f"Logged Object Anomaly '{gear_item['name']}' to Bureau Vault",
            user_id=user_id,
        )
        return {
            "converted": True,
            "mode": "public_agency_requisition",
            "faction_archetype_key": arch,
            "item": gear_item,
            "rep_bonus": 5,
            "notice": (
                f"🏛️ **Object Relic Logged to Bureau Vault:** **{gear_item['name']}** ({gear_item['item_type']}) "
                f"earned **+5 Promotion Rep** and is now unlocked for **50%-off Requisition** at the HQ Tactical Armory!"
            ),
        }

    if user_id:
        added_id = db.add_item(
            user_id,
            gear_item["name"],
            item_type=gear_item.get("item_type", "Weapon"),
            effect=gear_item.get("effect", ""),
            slot_cost=int(gear_item.get("slot_cost", 1) or 1),
        )
        if added_id is None:
            dropped = db.drop_item_to_session_floor(user_id, gear_item, session_id=session_id)
            if dropped:
                return {
                    "converted": True,
                    "mode": "floor_overflow",
                    "faction_archetype_key": arch,
                    "item": gear_item,
                    "rep_bonus": 0,
                    "notice": (
                        f"🔮 **Anomalous Object Converted (Inventory Full):** **{gear_item['name']}** ({gear_item['item_type']}) "
                        f"could not fit in your pack and was placed safely on the floor here for pickup!"
                    ),
                }
            sess = (db.get_session(session_id) or {}) if session_id else {}
            t_cur = _resolve_session_turn_number(session_id, sess) if session_id else 0
            gear_item["turn_captured"] = t_cur
            gear_item["first_turn"] = t_cur
            if session_id:
                req_list = list(sess.get("anomalous_vault_requisitions") or [])
                if not any(isinstance(r, dict) and r.get("name") == gear_item["name"] for r in req_list):
                    req_list.append(gear_item)
                    db.update_session(session_id, extra={"anomalous_vault_requisitions": req_list})
            return {
                "converted": True,
                "mode": "vault_overflow",
                "faction_archetype_key": arch,
                "item": gear_item,
                "rep_bonus": 0,
                "notice": (
                    f"🔮 **Anomalous Object Routed to Containment Vault (Inventory Full):** **{gear_item['name']}** ({gear_item['item_type']}) "
                    f"was transferred to your Containment Vault Requisitions so it is never lost!"
                ),
            }
    return {
        "converted": True,
        "mode": "direct_keep",
        "faction_archetype_key": arch,
        "item": gear_item,
        "rep_bonus": 0,
        "notice": (
            f"🔮 **Anomalous Object Converted:** Harnessed **{gear_item['name']}** ({gear_item['item_type']}) "
            f"directly into your inventory!"
        ),
    }


def record_contained_anomaly_to_vault_log(
    session_id: int,
    entity_name: str,
    category_tag: str,
    subtype: str,
    location: str,
    containment_note: str = "",
    resolution_method: str = "Pacified & Sealed",
    user_id: Optional[int] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    blueprint: Optional[Dict[str, Any]] = None,
    incursion_id: str = "",
) -> Dict[str, Any]:
    """
    Appends a secured Non-Hostile Entity or Altered Item/Phenomenon to `session['contained_anomalies_log']`
    for display in the Containment Vaults, Reliquary Pagoda, Private Vault, and Agent Dossier UI.
    Also ratchets the account-wide `user_folklore_codex` + session `anomaly_field_log` & cooldowns!
    """
    from mechanics.social.factions import get_anomalous_faction_state

    sess = db.get_session(session_id) or {}
    bp_resolved = dict(blueprint) if isinstance(blueprint, dict) else None
    if bp_resolved is None and quest_id:
        q_v = db.get_quest_by_id(session_id, quest_id) or {}
        bp_resolved = parse_blueprint_from_notes(q_v)
    if bp_resolved is None:
        for inc_v in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
            if not isinstance(inc_v, dict):
                continue
            if (incursion_id and (inc_v.get("incursion_id") == incursion_id or inc_v.get("breach_id") == incursion_id)) or (
                str(inc_v.get("entity_name") or "").strip().lower() == str(entity_name or "").strip().lower()
            ):
                if isinstance(inc_v.get("anomaly_blueprint"), dict):
                    bp_resolved = dict(inc_v["anomaly_blueprint"])
                break

    orig_entity_name = str(entity_name or "").strip()
    disguise_alias_prune = ""
    if isinstance(bp_resolved, dict):
        disguise_alias_prune = str((bp_resolved.get("disguise_state") or {}).get("disguise_alias") or "").strip()
        bp_resolved, _ = unmask_blueprint_disguise(bp_resolved)
        if bp_resolved.get("canonical_name"):
            entity_name = str(bp_resolved["canonical_name"])
        try:
            db.record_session_anomaly_field_log(
                session_id,
                bp_resolved,
                stage="contained",
                location=location,
                resolution_method=resolution_method,
            )
            if bp_resolved.get("codex_id"):
                uids_v = db.get_session_participant_user_ids(session_id) or ([int(user_id)] if user_id else [])
                db.record_folklore_codex_progress(uids_v, str(bp_resolved["codex_id"]), stage="contained")
                db.retire_or_cooldown_folklore_in_session(
                    session_id,
                    str(bp_resolved["codex_id"]),
                    uniqueness=str(bp_resolved.get("uniqueness") or "species"),
                    current_day=int(sess.get("current_day") or sess.get("in_game_day") or 1),
                    cooldown_days=int(bp_resolved.get("cooldown_days", 4) or 4),
                )
                sess = db.get_session(session_id) or sess
        except Exception as exc:
            logger.warning("Failed to record contained anomaly codex/field-log progress for session %s: %s", session_id, exc)

    log_list = list(sess.get("contained_anomalies_log") or [])
    if quest_id:
        for existing_entry in log_list:
            if (
                isinstance(existing_entry, dict)
                and str(existing_entry.get("quest_id") or "") == str(quest_id)
                and existing_entry.get("sub_obj_id") == sub_obj_id
            ):
                return existing_entry

    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    if arch == "monastic_order":
        vault_facility = "Inner Sanctum & Reliquary Pagoda"
    elif arch == "private_agency_1":
        vault_facility = f"{fac_state.get('joined_faction_name', 'Conglomerate')} Cryogenic Asset Vault"
    elif arch == "private_agency_2":
        vault_facility = f"{fac_state.get('joined_faction_name', 'Agency')} Lead-Lined Evidence Vault"
    else:
        vault_facility = "Subterranean Containment & Quarantine Vaults"

    t_cur_cap = _resolve_session_turn_number(session_id, sess)
    entry = {
        "entry_id": f"vault_{len(log_list) + 1}_{int(time.time())}",
        "entity_name": entity_name,
        "category_tag": category_tag,
        "subtype": subtype,
        "captured_at": location,
        "location": location,
        "day_captured": int(sess.get("current_day", 1) or 1),
        "turn_captured": t_cur_cap,
        "first_turn": t_cur_cap,
        "resolution_method": resolution_method,
        "vault_facility": vault_facility,
        "containment_note": containment_note or f"Safely contained at {vault_facility}.",
    }
    if quest_id:
        entry["quest_id"] = str(quest_id)
        if sub_obj_id is not None:
            entry["sub_obj_id"] = sub_obj_id
    if isinstance(bp_resolved, dict):
        if bp_resolved.get("codex_id"):
            entry["codex_id"] = str(bp_resolved["codex_id"])
            entry["is_canonical_folklore"] = True
        if bp_resolved.get("folklore_tradition"):
            entry["folklore_tradition"] = str(bp_resolved["folklore_tradition"])
        for _p_key in ("primary_element", "sapience", "form", "threat_tier"):
            if bp_resolved.get(_p_key) is not None:
                entry[_p_key] = bp_resolved[_p_key]
        _c_prof = bp_resolved.get("combat_profile") if isinstance(bp_resolved.get("combat_profile"), dict) else {}
        if bp_resolved.get("archetype") or _c_prof.get("archetype"):
            entry["archetype"] = str(bp_resolved.get("archetype") or _c_prof.get("archetype"))
        if isinstance(bp_resolved.get("taboo"), dict):
            entry["taboo"] = dict(bp_resolved["taboo"])

    log_list.append(entry)
    db.update_session(session_id, extra={"contained_anomalies_log": log_list})
    _prune_anomaly_from_scene_npcs(
        session_id,
        entity_name,
        extra_names=[orig_entity_name, disguise_alias_prune],
        session=sess,
        persist_db=True,
    )
    return entry
