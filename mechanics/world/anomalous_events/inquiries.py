from __future__ import annotations
"""
Non-Hostile Entity temperament evaluation, dossier reveals, scene-presence synchronization,
contextual containment approaches, and sapient anomaly dialogue inquiries.
"""
import hashlib
import json
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

from .generation import (
    NON_HOSTILE_APPROACH_SPECS,
    SAPIENCE_APPROACH_SPEC_OVERRIDES,
    _resolve_session_turn_number,
    get_active_incursion_at_location,
)


def _extract_quest_anomaly_blueprint(
    quest: Optional[Dict[str, Any]],
    sub_obj: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Extracts the anomaly blueprint dict from a quest row (supporting `anomaly_blueprint_json` and legacy notes)."""
    if isinstance(quest, dict):
        bp = parse_blueprint_from_notes(quest)
        if isinstance(bp, dict) and bp:
            return bp
    if isinstance(sub_obj, dict) and sub_obj.get("notes"):
        bp_so = parse_blueprint_from_notes(str(sub_obj.get("notes") or ""))
        if isinstance(bp_so, dict) and bp_so:
            return bp_so
    return None


def is_non_hostile_entity_quest(
    quest_or_wp: Optional[Dict[str, Any]],
    sub_obj: Optional[Dict[str, Any]] = None,
) -> bool:
    """Returns True if `quest_or_wp` (or `sub_obj`) represents a Non-Hostile Anomalous Entity containment task."""
    if not isinstance(quest_or_wp, dict):
        quest_or_wp = {}
    if not isinstance(sub_obj, dict):
        sub_obj = {}

    combined = " | ".join([
        str(quest_or_wp.get("quest_type") or ""),
        str(quest_or_wp.get("archetype") or ""),
        str(quest_or_wp.get("title") or quest_or_wp.get("quest_title") or ""),
        str(quest_or_wp.get("objective") or quest_or_wp.get("quest_objective") or ""),
        str(quest_or_wp.get("quest_notes") or ""),
        str(sub_obj.get("archetype") or ""),
        str(sub_obj.get("text") or ""),
        str(quest_or_wp.get("sub_obj_text") or ""),
    ]).lower()

    return any(
        kw in combined
        for kw in (
            "secure non-hostile anomalous entity",
            "non_hostile_entity_pacification",
            "non-hostile anomalous entity",
            "non-hostile entity",
            "non_hostile_entity",
            "live capture:",
            "non_hostile_temperament:",
        )
    )


def is_non_hostile_entity_containment_waypoint(
    wp: Optional[Dict[str, Any]],
    all_wps: Optional[List[Dict[str, Any]]] = None,
    sub_obj: Optional[Dict[str, Any]] = None,
    quest: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Returns True when `wp` is the active field-containment stage for a Non-Hostile Anomalous Entity
    (excluding Stage 1 pure arrival scouting and Stage 3 post-capture client delivery/turn-in).
    """
    if not isinstance(wp, dict):
        return False
    merged_q = dict(quest or {})
    for k, v in wp.items():
        if v is not None and (k not in merged_q or not merged_q.get(k)):
            merged_q[k] = v

    if not is_non_hostile_entity_quest(merged_q, sub_obj=sub_obj):
        return False

    trigger = str(wp.get("completion_trigger") or "skill_check").strip().lower()
    if trigger not in ("skill_check", "inspect_prop", "talk_to_npc", "action", "defeat_target"):
        return False

    q_notes = str(merged_q.get("quest_notes") or "")
    so_id_val = wp.get("sub_obj_id") if wp.get("sub_obj_id") is not None else (sub_obj.get("id") if isinstance(sub_obj, dict) else None)
    secured_flag = f"entity_secured_so_{so_id_val}:1" if so_id_val is not None else "entity_secured:1"
    if secured_flag in q_notes:
        return False

    stage_idx = int(wp.get("stage_index", 1) or 1)
    total_stages = len(all_wps) if isinstance(all_wps, list) and all_wps else int(wp.get("total_stages") or 0)
    lbl_low = str(wp.get("stage_label") or "").strip().lower()

    # If on Stage >= 3 of a 3+ stage quest and label is clearly client delivery/turn-in, do NOT treat as containment stage
    if stage_idx >= 3 and (total_stages == 0 or stage_idx >= total_stages):
        if any(
            turn_kw in lbl_low
            for turn_kw in ("deliver", "turn in", "hand over", "return to", "report to", "dispatch officer", "confirm receipt")
        ):
            return False

    return True


def get_non_hostile_entity_temperament(
    seed_key: str = "",
    quest_notes: str = "",
    explicit: str = "",
) -> str:
    """
    Deterministically returns one of the 4 non-hostile folklore temperaments:
      - `'timid'` (Elusive — flinches on Strike 1, flees on Strike 2)
      - `'volatile'` (Territorial — bristles on Strike 1, turns hostile in combat on Strike 2)
      - `'mischievous'` (Trickster — pockets 10-15G Trick-Tax on Strike 1, vanishes in illusion prank on Strike 2)
      - `'spook'` (Scare-Only / Odokashi — drains 4 MP on Strike 1, drains 8 MP + `Frightened` & vanishes on Strike 2)
    """
    exp_clean = str(explicit or "").strip().lower()
    if exp_clean in NON_HOSTILE_TEMPERAMENT_TYPES:
        return exp_clean

    if isinstance(quest_notes, dict):
        bp_dict = parse_blueprint_from_notes(quest_notes)
        if isinstance(bp_dict, dict):
            bp_t = str(bp_dict.get("non_hostile_temperament") or bp_dict.get("temperament") or "").strip().lower()
            if bp_t in NON_HOSTILE_TEMPERAMENT_TYPES:
                return bp_t
        notes_str = str(quest_notes.get("quest_notes") or "")
    else:
        notes_str = str(quest_notes or "")
    m = re.search(r"non_hostile_temperament:(timid|volatile|mischievous|spook)", notes_str, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()

    if "anomaly_bp:" in notes_str or "anomaly_blueprint:" in notes_str or notes_str.lstrip().startswith("{"):
        bp_parsed = parse_blueprint_from_notes(notes_str)
        if isinstance(bp_parsed, dict):
            bp_t = str(bp_parsed.get("non_hostile_temperament") or bp_parsed.get("temperament") or "").strip().lower()
            if bp_t in NON_HOSTILE_TEMPERAMENT_TYPES:
                return bp_t

    digest = hashlib.md5(str(seed_key or "default_entity").encode("utf-8")).digest()
    return NON_HOSTILE_TEMPERAMENT_TYPES[digest[0] % len(NON_HOSTILE_TEMPERAMENT_TYPES)]


def get_temperament_brief_cue(temperament: str) -> str:
    """Returns a compact 1-line dispatch cue for bounty boards and SMS alerts."""
    t_low = str(temperament or "timid").strip().lower()
    if t_low == "volatile":
        return "Volatile/territorial—provoking risks combat."
    if t_low == "mischievous":
        return "Mischievous/trickster—failed checks risk coin-prank & illusion escape."
    if t_low == "spook":
        return "Spook/startle-seeker—failed checks drain composure & risk vanish."
    return "Timid/elusive—startling risks escape."


def get_temperament_scene_hint(entity_name: str, temperament: str) -> str:
    """Returns a narrative scene hint telegraphing how repeated failures resolve for all 4 temperaments."""
    ent = str(entity_name or "The anomalous entity").strip()
    t_low = str(temperament or "timid").strip().lower()
    if t_low == "volatile":
        return (
            f"{ent} exhibits a **volatile, territorial aura**—static arcs violently whenever cornered, "
            f"signaling it will lash out in combat if provoked by repeated failed containment attempts."
        )
    if t_low == "mischievous":
        return (
            f"{ent} exhibits a **mischievous, trickster demeanor**—playful illusions shimmer around it, "
            f"signaling failed containment checks will invite a coin-pocketing prank before it vanishes in a decoy burst."
        )
    if t_low == "spook":
        return (
            f"{ent} exhibits a **theatrical spook-only demeanor**—looming strictly to elicit a startled gasp, "
            f"signaling failed containment checks will rattle your composure (MP & `Frightened`) before it cackles and vanishes."
        )
    return (
        f"{ent} exhibits a **timid, skittish demeanor**—hovering near an unstable spatial seam, "
        f"poised to slip away and vanish if startled by repeated failed containment attempts."
    )


def apply_non_hostile_strike_side_effects(
    session_id: int,
    user_id: Optional[int],
    entity_name: str,
    temperament: str,
    is_final_strike: bool,
    *,
    seed_key: str = "",
    quest_id: str = "",
    incursion_id: str = "",
    target_inc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Applies deterministic Strike 1 & Strike 2 non-combat folklore consequences for `mischievous` and `spook`:
      - `mischievous`:
        - Strike 1: Pockets 10-15G (`min(gold, tax)`) in escrow (refunded on capture) or +1 next-check DC if at 0G; 0 HP loss.
        - Strike 2: Vanishes in an illusion prank keeping pocketed coins (`escaped=True`, 0 HP loss, no combat).
      - `spook`:
        - Strike 1: Eerie fake-out draining 4 MP (floored at 0; +1 next-check DC if already at 0 MP); 0 HP loss.
        - Strike 2: Full jump-scare draining 8 MP + applying native `'Frightened'` status condition, then vanishes (`escaped=True`, 0 HP loss).
    """
    from db.quests import append_quest_note_flag_in_db

    t_low = str(temperament or "timid").strip().lower()
    ent = str(entity_name or "the Anomalous Entity").strip()
    out: Dict[str, Any] = {
        "temperament": t_low,
        "gold_stolen": 0,
        "total_escrowed_gold": 0,
        "mp_drained": 0,
        "status_applied": "",
        "prank_dc_penalty": 0,
        "hp_delta": 0,
        "warn_suffix": "",
        "escape_message": "",
        "directive": "",
    }
    if t_low not in ("mischievous", "spook"):
        return out

    char = (db.get_character(int(user_id)) or {}) if user_id else {}
    prev_tax = 0
    if quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        m_tx = re.search(r"trick_tax_gold:(\d+)", str(q_row.get("quest_notes") or ""))
        if m_tx:
            prev_tax = int(m_tx.group(1))
    elif isinstance(target_inc, dict):
        prev_tax = int(target_inc.get("trick_tax_gold", 0) or 0)

    if t_low == "mischievous":
        h_hex = hashlib.md5(f"{session_id}:{seed_key or quest_id or incursion_id}:{ent}".encode("utf-8")).hexdigest()
        tax_roll = 10 + (int(h_hex[:6], 16) % 6)  # 10..15G
        cur_gold = max(0, int(char.get("gold", 0) or 0))
        if not is_final_strike:
            stolen = min(cur_gold, tax_roll) if user_id else 0
            if stolen > 0 and user_id:
                db.apply_hp_mp_delta(int(user_id), gold_delta=-stolen)
                new_escrow = prev_tax + stolen
                out["gold_stolen"] = stolen
                out["total_escrowed_gold"] = new_escrow
                if quest_id and session_id:
                    append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_gold", str(new_escrow))
                if isinstance(target_inc, dict):
                    target_inc["trick_tax_gold"] = new_escrow
                out["warn_suffix"] = (
                    f"Giggling at your slip, **{ent}** picks your pocket for **{stolen}G** in loose coins "
                    f"*(contain it on the next attempt to recover your {new_escrow}G, or one more failure and it will vanish with them)*!"
                )
            else:
                out["prank_dc_penalty"] = 1
                if quest_id and session_id:
                    append_quest_note_flag_in_db(session_id, quest_id, "prank_dc", "1")
                if isinstance(target_inc, dict):
                    target_inc["prank_dc_penalty"] = 1
                out["warn_suffix"] = (
                    f"Finding your pockets empty, **{ent}** scrambles nearby decoys in a teasing laugh (**+1 DC** on next check unless Taboo exploited)—"
                    f"one more failed check and it will vanish in an illusion prank!"
                )
            out["directive"] = (
                f"[MISCHIEVOUS TRICKSTER PRANK — STRIKE 1]: '{ent}' played a harmless prank ({out['warn_suffix']}). "
                f"Zero HP damage occurred; one more failed check and it escapes in a burst of illusions."
            )
            return out

        # Final strike (Strike >= 2): Illusion Escape!
        stolen_final = 0
        if prev_tax == 0 and cur_gold > 0 and user_id:
            stolen_final = min(cur_gold, tax_roll)
            db.apply_hp_mp_delta(int(user_id), gold_delta=-stolen_final)
        kept_total = prev_tax + stolen_final
        out["gold_stolen"] = stolen_final
        out["total_escrowed_gold"] = kept_total
        if quest_id and session_id:
            append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_forfeited", "1")
        if isinstance(target_inc, dict):
            target_inc["trick_tax_forfeited"] = True
        coin_clause = f" keeping your **{kept_total}G** in pocketed coins and leaving a counterfeit leaf behind" if kept_total > 0 else " leaving a teasing counterfeit leaf behind"
        out["escape_message"] = (
            f"🃏 **Trickster Prank Escape!** Outwitting your repeated containment attempts, **{ent}** bursts into illusory confetti and vanishes,{coin_clause}! "
            f"Live-containment rewards forfeited as it slips away unharmed."
        )
        out["directive"] = (
            f"[MISCHIEVOUS TRICKSTER ESCAPED]: '{ent}' pulled a playful parting illusion prank ({coin_clause.strip()}) "
            f"and vanished without combat or injury!"
        )
        return out

    # `spook` temperament (Scare-Only / Odokashi)
    cur_mp = max(0, int(char.get("mp", 0) or 0))
    if not is_final_strike:
        drained = min(cur_mp, 4) if user_id else 0
        if drained > 0 and user_id:
            db.apply_hp_mp_delta(int(user_id), mp_delta=-drained)
            out["mp_drained"] = drained
            out["warn_suffix"] = (
                f"Delighted by your hesitation, **{ent}** lunges in an eerie fake-out that rattles your composure—"
                f"one more failed check and its full scare will send it vanishing in triumph!"
            )
        else:
            out["prank_dc_penalty"] = 1
            if quest_id and session_id:
                append_quest_note_flag_in_db(session_id, quest_id, "prank_dc", "1")
            if isinstance(target_inc, dict):
                target_inc["prank_dc_penalty"] = 1
            out["warn_suffix"] = (
                f"Sensing your drained composure, **{ent}** looms closer with an uncanny grin (containment challenge heightened unless Taboo exploited)—"
                f"one more failed check and it will unleash its jump-scare and vanish!"
            )
        out["directive"] = (
            f"[SPOOK FAKE-OUT — STRIKE 1]: '{ent}' staged an eerie non-lethal startle ({out['warn_suffix']}). "
            f"Zero physical harm occurred; one more failed check and it spooks the player and vanishes."
        )
        return out

    # Final strike (Strike >= 2): Full Jump-Scare + `Frightened` + Satisfied Vanish!
    drained_final = min(cur_mp, 8) if user_id else 0
    if user_id:
        if drained_final > 0:
            db.apply_hp_mp_delta(int(user_id), mp_delta=-drained_final)
        char_after = db.get_character(int(user_id)) or {}
        eff_list = list(char_after.get("status_effects") or [])
        has_fright = any(
            (isinstance(s, dict) and str(s.get("name") or "").lower() == "frightened")
            or (isinstance(s, str) and s.strip().lower() == "frightened")
            for s in eff_list
        )
        if not has_fright:
            eff_list.append("Frightened")
            db.set_status_effects(int(user_id), eff_list)
        out["status_applied"] = "Frightened"
    out["mp_drained"] = drained_final
    out["escape_message"] = (
        f"👻 **Startled & Spooked!** **{ent}** pulls a theatrical folklore jump-scare (leaving you shaken and **Frightened**)! "
        f"Satisfied by your startled gasp, it cackles and dissolves into mist—live-containment rewards forfeited."
    )
    out["directive"] = (
        f"[SPOOK ANOMALY VANISHED IN SATISFACTION]: '{ent}' startled the player (applied 'Frightened') "
        f"and vanished happily into mist now that its scare succeeded!"
    )
    return out


def refund_trick_tax_gold_on_containment(
    session_id: int,
    user_id: Optional[int],
    *,
    quest_id: str = "",
    incursion_id: str = "",
    target_inc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Idempotently refunds any `trick_tax_gold` pocketed on Strike 1 when a `mischievous`
    anomaly is successfully contained peacefully or subdued/de-escalated in combat.
    """
    from db.quests import append_quest_note_flag_in_db

    refund_amt = 0
    if isinstance(target_inc, dict) and not target_inc.get("trick_tax_forfeited") and not target_inc.get("trick_tax_refunded"):
        refund_amt = max(0, int(target_inc.get("trick_tax_gold", 0) or 0))
        if refund_amt > 0:
            target_inc["trick_tax_gold"] = 0
            target_inc["trick_tax_refunded"] = True
    elif incursion_id and session_id:
        sess = db.get_session(session_id) or {}
        incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
        changed = False
        for inc in incursions:
            if isinstance(inc, dict) and (inc.get("incursion_id") == incursion_id or inc.get("breach_id") == incursion_id):
                if not inc.get("trick_tax_forfeited") and not inc.get("trick_tax_refunded"):
                    refund_amt = max(0, int(inc.get("trick_tax_gold", 0) or 0))
                    if refund_amt > 0:
                        inc["trick_tax_gold"] = 0
                        inc["trick_tax_refunded"] = True
                        changed = True
                break
        if changed:

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    if refund_amt == 0 and quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        notes = str(q_row.get("quest_notes") or "")
        if "trick_tax_forfeited:1" not in notes and "trick_tax_refunded:1" not in notes:
            m_tx = re.search(r"trick_tax_gold:(\d+)", notes)
            if m_tx and int(m_tx.group(1)) > 0:
                refund_amt = int(m_tx.group(1))
                append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_refunded", "1")
                append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_gold", "0")

    if refund_amt > 0 and user_id:
        db.apply_hp_mp_delta(int(user_id), gold_delta=refund_amt)
        return {
            "refunded_gold": refund_amt,
            "notice": f"🪙 Recovered **+{refund_amt}G** in pocketed coins!",
        }
    return {"refunded_gold": 0, "notice": ""}


def extract_non_hostile_entity_name(
    quest_or_wp: Optional[Dict[str, Any]],
    sub_obj: Optional[Dict[str, Any]] = None,
) -> str:
    """Extracts a clean display name for the target Non-Hostile Entity from quest/waypoint metadata."""
    if not isinstance(quest_or_wp, dict):
        quest_or_wp = {}
    if not isinstance(sub_obj, dict):
        sub_obj = {}

    notes = str(quest_or_wp.get("quest_notes") or "")
    m_note = re.search(r"entity_name:([^|\n]+)", notes)
    if m_note and m_note.group(1).strip():
        return m_note.group(1).strip()

    for candidate in (
        str(quest_or_wp.get("title") or quest_or_wp.get("quest_title") or ""),
        str(quest_or_wp.get("stage_label") or ""),
        str(sub_obj.get("text") or ""),
        str(quest_or_wp.get("objective") or quest_or_wp.get("quest_objective") or ""),
    ):
        if not candidate:
            continue
        m_colon = re.search(r"(?:Live Capture|Non-Hostile Entity|Containment)\s*:\s*([^(\n|]+)", candidate, re.IGNORECASE)
        if m_colon and m_colon.group(1).strip():
            return m_colon.group(1).strip()
        m_quote = re.search(r"'([^']{3,60})'", candidate)
        if m_quote and m_quote.group(1).strip():
            val = m_quote.group(1).strip()
            if not any(skip in val.lower() for skip in ("live capture:", "[mandatory]")):
                return val

    req_item = str(quest_or_wp.get("required_item") or "").strip()
    if req_item and "containment" not in req_item.lower():
        return req_item
    return "the Anomalous Entity"


def reveal_anomaly_dossier(
    session_id: int,
    quest_id: str = "",
    incursion_id: str = "",
    breach_id: str = "",
) -> Dict[str, Any]:
    """
    Marks an Anomaly Dossier as fully investigated (`dossier_revealed = True`),
    revealing Physicality, Sapience, Elemental Resistances/Weaknesses, and Folklore/SCP Taboo,
    and unlocking the +2 Investigation Bonus & Taboo Exploitation!
    """
    from db.quests import append_quest_note_flag_in_db

    sess = db.get_session(session_id) or {}
    eff_inc = str(incursion_id or breach_id or "").strip()
    bp: Optional[Dict[str, Any]] = None
    unmask_msg = ""
    unmasked_from = ""

    if quest_id:
        q = db.get_quest_by_id(session_id, quest_id) or {}
        notes = str(q.get("quest_notes") or "")
        bp = parse_blueprint_from_notes(q)
        if bp:
            prev_alias_q = str((bp.get("disguise_state") or {}).get("disguise_alias") or "").strip()
            bp, unmask_msg = unmask_blueprint_disguise(bp)
            bp["dossier_revealed"] = True
            new_bp_token = serialize_blueprint_note(bp).split("|", 1)[0]
            cleaned_notes = re.sub(r"anomaly_(?:bp|blueprint):[A-Za-z0-9+/=_-]+", new_bp_token, notes)
            true_nm = str(bp.get("canonical_name") or bp.get("name") or "").strip()
            if unmask_msg and true_nm:
                unmasked_from = prev_alias_q
                if "entity_name:" in cleaned_notes:
                    cleaned_notes = re.sub(r"entity_name:[^|]+", f"entity_name:{true_nm}", cleaned_notes)
                else:
                    cleaned_notes = f"{cleaned_notes}|entity_name:{true_nm}"
            db.update_quest_anomaly_blueprint(session_id, quest_id, bp, quest_notes=cleaned_notes)
        append_quest_note_flag_in_db(session_id, quest_id, "dossier_revealed", "1")

    if eff_inc:
        incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
        for inc in incursions:
            if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc or inc.get("breach_id") == eff_inc):
                inc["dossier_revealed"] = True
                inc["revealed_at_turn"] = _resolve_session_turn_number(session_id, sess)
                if inc.get("original_entity_name") is None:
                    inc["original_entity_name"] = str(inc.get("entity_name") or "")
                if isinstance(inc.get("anomaly_blueprint"), dict):
                    prev_alias_i = str((inc["anomaly_blueprint"].get("disguise_state") or {}).get("disguise_alias") or inc.get("entity_name") or "").strip()
                    inc_bp, inc_unmask = unmask_blueprint_disguise(inc["anomaly_blueprint"])
                    inc_bp["dossier_revealed"] = True
                    inc["anomaly_blueprint"] = inc_bp
                    bp = inc_bp
                    if inc_unmask:
                        unmask_msg = inc_unmask
                        unmasked_from = prev_alias_i
                        true_inc_nm = str(inc_bp.get("canonical_name") or inc_bp.get("name") or inc.get("entity_name") or "")
                        old_nm = str(inc.get("entity_name") or "")
                        if true_inc_nm:
                            inc["entity_name"] = true_inc_nm
                            if old_nm and old_nm in str(inc.get("title") or ""):
                                inc["title"] = str(inc["title"]).replace(old_nm, true_inc_nm)

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    if bp and session_id:
        try:
            fresh_sess = db.get_session(session_id) or sess
            true_canon_nm = str(bp.get("canonical_name") or bp.get("name") or "").strip()
            if unmasked_from and true_canon_nm:
                cur_dp = str(fresh_sess.get("dialogue_partner") or "").strip()
                if cur_dp and cur_dp.lower() == unmasked_from.lower():
                    fresh_sess["dialogue_partner"] = true_canon_nm
                    fresh_sess["dialogue_partners"] = [true_canon_nm]
                    db.update_session(
                        session_id,
                        dialogue_partner=true_canon_nm,
                        extra={"dialogue_partners": [true_canon_nm]},
                    )
            sync_non_hostile_anomaly_scene_presence(session_id, session=fresh_sess, persist_db=True)
            db.record_session_anomaly_field_log(
                session_id,
                bp,
                stage="verified",
                location=str(fresh_sess.get("current_location") or ""),
            )
            if bp.get("codex_id"):
                db.record_folklore_codex_progress(
                    db.get_session_participant_user_ids(session_id),
                    str(bp["codex_id"]),
                    stage="verified",
                )
        except Exception:
            pass

    summary_obj = format_anomaly_dossier_summary(bp, revealed=True) if bp else None
    summary = (
        (summary_obj.get("summary_text") if isinstance(summary_obj, dict) else str(summary_obj))
        if summary_obj
        else "Dossier Revealed (+2 Containment Bonus)"
    )
    if unmask_msg:
        summary = f"{unmask_msg} {summary}"
    return {
        "revealed": True,
        "dossier_revealed": True,
        "unmask_notice": unmask_msg,
        "unmasked_from": unmasked_from,
        "blueprint": bp,
        "dossier_summary": summary,
        "dossier": summary_obj,
    }


_BIOME_CONTAINMENT_FIXTURES: Dict[str, str] = {
    "transit": "platform safety gates & conductive rails",
    "hospital": "quarantine ward bulkheads & lead shielding",
    "shrine": "sacred torii boundary ropes & stone lanterns",
    "broadcast": "relay Faraday cages & grounded antennae",
    "subterranean": "floodgate bulkheads & maintenance conduits",
    "commercial": "security shutters & mirrored display alcoves",
    "residential": "threshold doorframes & hallway ward-seals",
    "industrial": "hydraulic containment bay clamps & grounding grids",
    "natural": "ley-line boundary stones & canopy clearings",
    "nature": "ley-line boundary stones & canopy clearings",
    "coastal": "tide-gate sluices & salt-crusted pier pilings",
    "urban": "alley threshold doorframes & streetlamp ward-seals",
}


def _build_contextual_containment_verb(
    spec: Dict[str, str],
    entity_name: str,
    bp: Optional[Dict[str, Any]],
    eff_sap: str,
    is_revealed: bool,
    stat: str,
    exploit_stats: set[str],
) -> str:
    """
    Weaves the anomaly's specific form, biome fixtures, and—when `is_revealed` is True—its
    Folklore/SCP Taboo & Containment Protocol directly into the containment choice verb.
    """
    if not isinstance(bp, dict) or not bp:
        return spec["verb_template"].format(entity_name=entity_name)

    form_lbl = (
        "uncanny presence"
        if is_blueprint_disguised(bp, dossier_revealed=is_revealed)
        else str(bp.get("form_label") or bp.get("type") or "anomalous manifestation").strip().lower()
    )
    biome_key = str(bp.get("biome") or "urban").strip().lower()
    fixture = _BIOME_CONTAINMENT_FIXTURES.get(biome_key, "local structural geometry & ward-anchors")
    taboo = bp.get("taboo") if isinstance(bp.get("taboo"), dict) else {}
    taboo_name = str(bp.get("taboo_name") or taboo.get("name") or "").strip()
    protocol_str = str(bp.get("containment_protocol") or taboo.get("containment_protocol") or "").strip()
    short_proto = protocol_str.split(".")[0].strip() if protocol_str else ""

    if is_revealed and stat in exploit_stats and (taboo_name or short_proto):
        proto_tag = f"{taboo_name}: {short_proto[:48]}" if (taboo_name and short_proto) else (taboo_name or short_proto[:55])
        if stat == "CHA":
            if eff_sap == "compulsive":
                return f"Recite {proto_tag} courtesy script to satisfy {entity_name}"
            return f"Invoke {proto_tag} to bargain with {entity_name}"
        if stat == "PER":
            return f"Observe {proto_tag} to soothe {entity_name}"
        if stat == "INT":
            return f"Exploit {proto_tag} to snare {entity_name}"
        return f"Execute {proto_tag} across {fixture} to seal {entity_name}"

    if is_revealed and taboo_name:
        if stat == "CHA":
            if eff_sap == "sapient":
                return f"Negotiate containment terms with {entity_name} while honoring {taboo_name}"
            if eff_sap == "compulsive":
                return f"Recite the formal courtesy script for {entity_name} ({form_lbl}) under {taboo_name}"
            if eff_sap == "instinctual":
                return f"Project a non-threatening presence toward {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Attune your vocal cadence to harmonize with {entity_name}'s {form_lbl} frequency"
        if stat == "PER":
            if eff_sap == "compulsive":
                return f"Time the ritual loop cadence of {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Read {entity_name}'s {form_lbl} tells and calm its resonance under {taboo_name}"
        if stat == "INT":
            if eff_sap == "compulsive":
                return f"Spring a counting or rule snare on {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Configure a calibrated containment snare for {entity_name} ({form_lbl})"
        if eff_sap == "compulsive":
            return f"Mirror {entity_name}'s ritual choreography across {fixture} to seal it"
        return f"Leverage {fixture} to box in and seal {entity_name}"

    if stat == "CHA":
        if eff_sap == "sapient":
            return f"Reason with {entity_name} ({form_lbl}) and negotiate peaceful containment"
        if eff_sap == "compulsive":
            return f"Offer formal folklore courtesy to satisfy {entity_name}'s ({form_lbl}) ritual script"
        if eff_sap == "instinctual":
            return f"Project a calm, non-threatening posture to coax {entity_name} ({form_lbl})"
        return f"Attune your vocal cadence to stabilize {entity_name} ({form_lbl})"
    if stat == "PER":
        if eff_sap == "compulsive":
            return f"Study the exact repetition cadence of {entity_name}'s ({form_lbl}) loop"
        if eff_sap == "non_sapient":
            return f"Track the harmonic pulse of {entity_name} ({form_lbl}) and dampen its surge"
        return f"Read {entity_name}'s {form_lbl} aura and soothe its agitation"
    if stat == "INT":
        if eff_sap == "sapient":
            return f"Outmaneuver {entity_name} ({form_lbl}) into a field containment snare"
        if eff_sap == "compulsive":
            return f"Introduce a counting distraction to loop-lock {entity_name} ({form_lbl})"
        if eff_sap == "instinctual":
            return f"Lure {entity_name} ({form_lbl}) into a baited containment snare"
        return f"Triangulate the phase-pattern of {entity_name} ({form_lbl}) to lock a seal"
    if eff_sap == "compulsive":
        return f"Step in rhythm with {entity_name}'s choreography across {fixture} to seal it"
    return f"Use {fixture} to corner and seal {entity_name}"


def build_sapient_anomaly_converse_choice(
    entity_name: str,
    *,
    mode: str = "quest",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    stage_index: int = 2,
    is_story_quest: bool = False,
    incursion_id: str = "",
    breach_id: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
    sapience: str = "sapient",
) -> Dict[str, Any]:
    """
    Builds the strike-free '💬 Converse with {entity_name}' choice for Sapient anomalies,
    or '👁️ Study {entity_name}'s Pattern' choice for Compulsive (Pattern-Bound) anomalies.
    """
    ent = str(entity_name or "the Anomalous Entity").strip()
    eff_id = str(incursion_id or breach_id or "").strip()
    eff_sap = "compulsive" if str(sapience or (blueprint or {}).get("sapience") or "").strip().lower() == "compulsive" else "sapient"
    form_lbl = (
        "uncanny figure"
        if is_blueprint_disguised(blueprint or {}, dossier_revealed=bool((blueprint or {}).get("dossier_revealed")))
        else str((blueprint or {}).get("form_label") or "anomalous entity").strip().lower()
    )
    if eff_sap == "compulsive":
        lbl = f"👁️ Study {ent}'s Pattern: Observe this {form_lbl}'s compulsive loop & folklore rules (FREE)"
        act_key = "anomaly_pattern_study"
    else:
        lbl = f"💬 Converse with {ent}: Question this {form_lbl} about its origins, nature & motive (FREE)"
        act_key = "anomaly_inquiry"
    if mode == "incursion":
        return {
            "label": lbl[:190],
            "stat": "FREE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "dialogue_init",
            "target_npc": ent,
            "incursion_action": act_key,
            "incursion_id": eff_id,
            "breach_id": eff_id,
            "sapience": eff_sap,
            "is_anomaly_inquiry": True,
            "_npc_speak_choice": True,
            "_server_stamped": True,
        }
    return {
        "label": lbl[:190],
        "stat": "FREE",
        "requirement": 0,
        "mp_cost": 0,
        "intent": "dialogue_init",
        "sub_intent": act_key,
        "target_npc": ent,
        "is_fallback": False,
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_index": stage_index,
        "is_quest_action": False,
        "is_story_quest": bool(is_story_quest),
        "approach": act_key,
        "incursion_action": act_key,
        "sapience": eff_sap,
        "is_anomaly_inquiry": True,
        "_npc_speak_choice": True,
        "_server_stamped": True,
    }


def build_non_hostile_narrative_choices(
    entity_name: str,
    mode: str = "quest",
    *,
    char: Optional[Dict[str, Any]] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    stage_index: int = 2,
    is_story_quest: bool = False,
    contract_type: str = "skill_check",
    dc_mod: int = 0,
    incursion_id: str = "",
    breach_id: str = "",
    sapience: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
    dossier_revealed: Optional[bool] = None,
    session_id: Optional[int] = None,
    include_converse: bool = False,
) -> List[Dict[str, Any]]:
    """
    Builds all 4 guaranteed out-of-combat narrative containment choices:
      1. Persuade (CHA)
      2. Calm (PER)
      3. Outwit (INT)
      4. Use Environment (AGI)
    Dynamically weaves in the anomaly's form, biome fixtures, and—when `dossier_revealed` is True—
    its Folklore/SCP Taboo & Containment Protocol, and applies `-2` DC (`-3` DC on Taboo `exploit_stats`).
    When `include_converse=True`, prepends a strike-free `💬 Converse` (`sapient`) or
    `👁️ Study Pattern` (`compulsive`) choice before containing the entity.
    """
    eff_id = str(incursion_id or breach_id or "").strip()
    ent = str(entity_name or "the Anomalous Entity").strip()
    stats_dict = (char or {}).get("stats") if isinstance((char or {}).get("stats"), dict) else {}
    stat_col_map = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk"}

    if session_id is None and isinstance(char, dict) and char.get("active_session_id"):
        try:
            session_id = int(char["active_session_id"])
        except Exception:
            pass
    bp = dict(blueprint) if isinstance(blueprint, dict) else None
    prank_dc_pen = 0
    if session_id:
        if quest_id:
            q_row = db.get_quest_by_id(session_id, quest_id) or {}
            q_notes = str(q_row.get("quest_notes") or "")
            if bp is None:
                bp = parse_blueprint_from_notes(q_row)
            if dossier_revealed is None and "dossier_revealed:1" in q_notes:
                dossier_revealed = True
            if "prank_dc:1" in q_notes:
                prank_dc_pen = 1
        elif eff_id:
            sess_row = db.get_session(session_id) or {}
            for inc in (sess_row.get("daily_incursions") or sess_row.get("daily_breaches") or []):
                if isinstance(inc, dict) and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id):
                    if bp is None and isinstance(inc.get("anomaly_blueprint"), dict):
                        bp = dict(inc["anomaly_blueprint"])
                    if dossier_revealed is None:
                        dossier_revealed = bool(inc.get("dossier_revealed"))
                    if not sapience and inc.get("sapience"):
                        sapience = str(inc.get("sapience"))
                    prank_dc_pen = int(inc.get("prank_dc_penalty", 0) or 0)
                    break

    eff_sap = str(sapience or (bp.get("sapience") if bp else "") or "sapient").strip().lower()
    if eff_sap not in SAPIENCE_APPROACH_SPEC_OVERRIDES:
        eff_sap = "sapient"
    is_revealed = bool(dossier_revealed if dossier_revealed is not None else (bp.get("dossier_revealed") if bp else False))
    taboo = (bp.get("taboo") if bp else None) or {}
    exploit_stats = {str(s).upper() for s in (taboo.get("exploit_stats") or (bp.get("exploit_stats") if bp else []) or [])}

    prefix = "Story Quest" if is_story_quest else "Bounty"
    q_icon = "⭐" if is_story_quest else "🎯"
    specs = SAPIENCE_APPROACH_SPEC_OVERRIDES.get(eff_sap, NON_HOSTILE_APPROACH_SPECS)

    choices: List[Dict[str, Any]] = []
    if include_converse and eff_sap in ("sapient", "compulsive"):
        choices.append(
            build_sapient_anomaly_converse_choice(
                ent,
                mode=mode,
                quest_id=quest_id,
                sub_obj_id=sub_obj_id,
                stage_index=stage_index,
                is_story_quest=is_story_quest,
                incursion_id=eff_id,
                breach_id=eff_id,
                blueprint=bp,
                sapience=eff_sap,
            )
        )

    char_uid = int(char.get("user_id")) if isinstance(char, dict) and char.get("user_id") else None
    off_ch = build_offering_counter_rite_choice(
        bp,
        ent,
        user_id=char_uid,
        base_dc=7 if mode == "incursion" else 6,
        quest_id=quest_id if mode != "incursion" else "",
        sub_obj_id=sub_obj_id,
        incursion_id=eff_id,
        is_story_quest=bool(is_story_quest),
    )
    if off_ch:
        if mode == "incursion":
            choices.append({
                "label": off_ch["label"][:190],
                "stat": "INT",
                "requirement": max(2, int(off_ch.get("dc", 3))),
                "mp_cost": 0,
                "intent": "anomalous_incursion_action",
                "incursion_action": "folklore_offering_rite",
                "offering_item_name": off_ch["offering_item_name"],
                "incursion_id": eff_id,
                "breach_id": eff_id,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "_server_stamped": True,
            })
        else:
            choices.append({
                "label": f"{q_icon} [{prefix}] {off_ch['label']}"[:190],
                "stat": "INT",
                "requirement": max(2, int(off_ch.get("dc", 3))),
                "mp_cost": 0,
                "intent": "investigate_clue",
                "sub_intent": "folklore_offering_rite",
                "target_npc": "",
                "is_fallback": False,
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_index,
                "is_quest_action": True,
                "is_story_quest": bool(is_story_quest),
                "contract_type": contract_type,
                "approach": "folklore_offering_rite",
                "offering_item_name": off_ch["offering_item_name"],
                "gold_cost": 0,
                "dc_mod": -5,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "_server_stamped": True,
            })

    for spec in specs:
        stat = spec["stat"]
        if stats_dict and stat in stats_dict:
            c_stat_val = int(stats_dict.get(stat, 5) or 5)
        elif isinstance(char, dict) and stat_col_map.get(stat) in char:
            c_stat_val = int(char.get(stat_col_map[stat], 5) or 5)
        else:
            c_stat_val = 6

        dossier_dc_reduction = 2 if is_revealed else 0
        taboo_dc_reduction = 1 if (is_revealed and stat in exploit_stats) else 0
        total_reduction = dossier_dc_reduction + taboo_dc_reduction
        prank_add = prank_dc_pen if (prank_dc_pen < 0 or not (is_revealed and stat in exploit_stats)) else 0
        verb_str = _build_contextual_containment_verb(spec, ent, bp, eff_sap, is_revealed, stat, exploit_stats)

        if mode == "incursion":
            req = min(12, max(3, 7 - total_reduction) + prank_add)
            lbl = f"{spec['icon']} [{spec['tag']}] {verb_str} (Optional)"
            choices.append({
                "label": lbl[:190],
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": "anomalous_incursion_action",
                "incursion_action": spec["incursion_action"],
                "incursion_id": eff_id,
                "breach_id": eff_id,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "taboo_exploited_stat": bool(stat in exploit_stats),
                "_server_stamped": True,
            })
        else:
            base_req = max(4, min(8, c_stat_val))
            req = max(1, base_req - total_reduction)
            eff_dc_mod = dc_mod + prank_add
            if eff_dc_mod > 0:
                req = min(12, req + eff_dc_mod)
            lbl = f"{q_icon} [{prefix}] [{spec['tag']}] {verb_str} ({stat})"
            choices.append({
                "label": lbl[:190],
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": "investigate_clue",
                "sub_intent": "",
                "target_npc": "",
                "is_fallback": False,
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_index,
                "is_quest_action": True,
                "is_story_quest": bool(is_story_quest),
                "contract_type": contract_type,
                "approach": spec["quest_approach"],
                "gold_cost": 0,
                "dc_mod": eff_dc_mod,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "taboo_exploited_stat": bool(stat in exploit_stats),
                "_server_stamped": True,
            })
    return choices


def _resolve_active_non_hostile_anomaly_context(
    session_id: Optional[int],
    *,
    session: Optional[Dict[str, Any]] = None,
    entity_name: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    location_str: str = "",
    node_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Resolves the active non-hostile anomaly at the player's location (from either an active Quest
    containment waypoint or an unresolved Daily Anomaly Breach) and returns its unified metadata.
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else {}) or {}
    sid = int(session_id or sess.get("id") or 0)
    eff_loc = str(location_str or sess.get("current_location") or "").strip()
    eff_nid = str(node_id or sess.get("current_node_id") or "").strip()
    eff_inc = str(incursion_id or breach_id or "").strip()
    ent_low = str(entity_name or "").strip().lower()

    # 1. Explicit quest_id or local quest containment waypoint
    if sid:
        try:
            from mechanics.world.waypoints.core import get_active_local_quest_hooks
            candidate_wps: List[Dict[str, Any]] = []
            if quest_id:
                q_row = db.get_quest_by_id(sid, quest_id) or {}
                if str(q_row.get("status") or "").lower() == "active":
                    all_wps = db.get_quest_waypoints(sid, quest_id, sub_obj_id) or []
                    act_wp = db.get_active_waypoint(sid, quest_id, sub_obj_id) or (all_wps[-1] if all_wps else {})
                    wp_merged = {**q_row, **(act_wp or {}), "quest_id": quest_id, "sub_obj_id": sub_obj_id}
                    if is_non_hostile_entity_containment_waypoint(wp_merged, all_wps=all_wps, quest=q_row):
                        candidate_wps.append(wp_merged)
            if not candidate_wps and eff_loc:
                for w in (get_active_local_quest_hooks(sid, eff_loc) or []):
                    w_qid = str(w.get("quest_id") or "")
                    w_all = db.get_quest_waypoints(sid, w_qid, w.get("sub_obj_id")) or []
                    if is_non_hostile_entity_containment_waypoint(w, all_wps=w_all):
                        candidate_wps.append(w)

            for wp in candidate_wps:
                w_qid = str(wp.get("quest_id") or "")
                q_row = db.get_quest_by_id(sid, w_qid) or wp
                q_notes = str(q_row.get("quest_notes") or wp.get("quest_notes") or "")
                if "entity_secured" in q_notes or "vault_logged:1" in q_notes:
                    continue
                ent_nm = extract_non_hostile_entity_name(q_row, wp)
                if ent_low and ent_low != ent_nm.lower() and ent_low not in ent_nm.lower() and ent_nm.lower() not in ent_low:
                    continue
                bp = parse_blueprint_from_notes(q_row)
                sap = str((bp.get("sapience") if bp else "") or "sapient").strip().lower()
                if not bp:
                    m_sap = re.search(r"sapience:(sapient|compulsive|instinctual|non_sapient)", q_notes, re.IGNORECASE)
                    if m_sap:
                        sap = m_sap.group(1).strip().lower()
                is_rev = bool("dossier_revealed:1" in q_notes or (bp and bp.get("dossier_revealed")))
                temp = get_non_hostile_entity_temperament(
                    seed_key=w_qid,
                    quest_notes=q_notes,
                    explicit=str((bp or {}).get("non_hostile_temperament") or ""),
                )
                return {
                    "mode": "quest",
                    "entity_name": ent_nm,
                    "quest_id": w_qid,
                    "sub_obj_id": wp.get("sub_obj_id"),
                    "stage_index": int(wp.get("stage_index", 2) or 2),
                    "is_story_quest": bool(q_row.get("is_story_quest") or wp.get("is_story_quest")),
                    "contract_type": str(wp.get("completion_trigger") or "skill_check"),
                    "incursion_id": "",
                    "blueprint": bp,
                    "sapience": sap,
                    "temperament": temp,
                    "dossier_revealed": is_rev,
                }
        except Exception:
            pass

    # 2. Explicit incursion_id or active non-hostile Daily Anomaly Breach at location
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = None
    if eff_inc:
        target_inc = next(
            (inc for inc in incursions if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc or inc.get("breach_id") == eff_inc)),
            None,
        )
    if not target_inc and sid:
        target_inc = get_active_incursion_at_location(sid, location_str=eff_loc, node_id=eff_nid)
    if not target_inc and ent_low:
        target_inc = next(
            (
                inc for inc in incursions
                if isinstance(inc, dict)
                and not inc.get("resolved")
                and str(inc.get("entity_name") or "").strip().lower() == ent_low
            ),
            None,
        )
    if target_inc and not target_inc.get("resolved") and not target_inc.get("agitated") and target_inc.get("subtype") != "hostile_breach":
        ent_nm = str(target_inc.get("entity_name") or "Anomalous Entity").strip()
        if not ent_low or ent_low == ent_nm.lower() or ent_low in ent_nm.lower() or ent_nm.lower() in ent_low:
            bp = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
            sap = str(target_inc.get("sapience") or (bp.get("sapience") if bp else "") or "sapient").strip().lower()
            inc_id_val = str(target_inc.get("incursion_id") or target_inc.get("breach_id") or "")
            temp = get_non_hostile_entity_temperament(
                seed_key=inc_id_val,
                explicit=str(target_inc.get("temperament") or (bp or {}).get("non_hostile_temperament") or ""),
            )
            is_rev = bool(target_inc.get("dossier_revealed") or (bp and bp.get("dossier_revealed")))
            return {
                "mode": "incursion",
                "entity_name": ent_nm,
                "quest_id": "",
                "sub_obj_id": None,
                "stage_index": 2,
                "is_story_quest": False,
                "contract_type": "skill_check",
                "incursion_id": inc_id_val,
                "blueprint": bp,
                "sapience": sap,
                "temperament": temp,
                "dossier_revealed": is_rev,
            }
    return None


def is_anomalous_scene_entity(
    npc_or_name: Any,
    *,
    session: Optional[Dict[str, Any]] = None,
    current_npcs: Optional[List[Any]] = None,
) -> bool:
    """Returns True if `npc_or_name` is an anomalous entity in the scene (`is_anomalous_entity: True`)."""
    if isinstance(npc_or_name, dict):
        if (
            npc_or_name.get("is_anomalous_entity")
            or str(npc_or_name.get("npc_type") or "").lower() == "anomaly"
            or str(npc_or_name.get("social_role_type") or "").lower() == "anomaly"
            or str(npc_or_name.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
        ):
            return True
        role_low = str(npc_or_name.get("role") or "").lower()
        if "non-hostile entity" in role_low or "non-hostile object" in role_low or "non-hostile phenomenon" in role_low:
            return True
        name_str = str(npc_or_name.get("name") or "").strip()
    else:
        name_str = str(npc_or_name or "").strip()

    if not name_str:
        return False
    nm_low = name_str.lower()
    npc_list = list(current_npcs or [])
    if isinstance(session, dict) and isinstance(session.get("current_npcs"), list):
        npc_list.extend(session["current_npcs"])
    for n in npc_list:
        if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == nm_low:
            if (
                n.get("is_anomalous_entity")
                or str(n.get("npc_type") or "").lower() == "anomaly"
                or str(n.get("social_role_type") or "").lower() == "anomaly"
                or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
            ):
                return True
    return False


def prune_anomaly_from_scene_npcs(
    session_id: Optional[int],
    entity_name: str = "",
    *,
    extra_names: Optional[List[str]] = None,
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
) -> None:
    """Removes a contained, escaped, or agitated anomaly (including any disguise alias) from `current_npcs` and `dialogue_partners`."""
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else None)
    if not isinstance(sess, dict):
        return
    name_targets = {str(entity_name or "").strip().lower()} - {""}
    for ex_nm in (extra_names or []):
        ex_clean = str(ex_nm or "").strip().lower()
        if ex_clean:
            name_targets.add(ex_clean)
    changed = False
    if isinstance(sess.get("current_npcs"), list):
        new_npcs = []
        for n in sess["current_npcs"]:
            if isinstance(n, dict):
                n_nm = str(n.get("name") or "").strip().lower()
                is_anom = bool(
                    n.get("is_anomalous_entity")
                    or str(n.get("npc_type") or "").lower() == "anomaly"
                    or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
                )
                if (is_anom and (not name_targets or n_nm in name_targets)) or (name_targets and n_nm in name_targets):
                    changed = True
                    continue
            new_npcs.append(n)
        if changed:
            sess["current_npcs"] = new_npcs

    if name_targets:
        dp_single = str(sess.get("dialogue_partner") or "").strip()
        if dp_single and dp_single.lower() in name_targets:
            sess["dialogue_partner"] = None
            changed = True
        if isinstance(sess.get("dialogue_partners"), list):
            new_dps = [p for p in sess["dialogue_partners"] if str(p).strip().lower() not in name_targets]
            if len(new_dps) != len(sess["dialogue_partners"]):
                sess["dialogue_partners"] = new_dps
                sess["dialogue_partner"] = new_dps[0] if new_dps else None
                changed = True

    if changed and persist_db and session_id:
        try:
            db.update_session(
                int(session_id),
                current_npcs=sess.get("current_npcs", []),
                dialogue_partner=sess.get("dialogue_partner"),
                extra={"dialogue_partners": sess.get("dialogue_partners", [])},
            )
        except Exception:
            pass


_prune_anomaly_from_scene_npcs = prune_anomaly_from_scene_npcs


def get_blueprint_alias_names(blueprint: Optional[Dict[str, Any]], entity_name: str = "") -> List[str]:
    """Every name an anomaly may appear under in scene state: public/entity name, canonical name, and disguise alias."""
    names: List[str] = []
    bp = blueprint if isinstance(blueprint, dict) else {}
    ds = bp.get("disguise_state") if isinstance(bp.get("disguise_state"), dict) else {}
    for cand in (entity_name, bp.get("entity_name"), bp.get("name"), bp.get("canonical_name"), ds.get("disguise_alias")):
        c_clean = str(cand or "").strip()
        if c_clean and c_clean not in names:
            names.append(c_clean)
    return names


def prune_expired_incursion_anomalies_from_scene(
    session_id: Optional[int],
    incursions: Optional[List[Dict[str, Any]]],
    session: Optional[Dict[str, Any]] = None,
) -> None:
    """At midnight rollover, removes every still-unresolved breach (and disguise alias) of the expiring day from the scene."""
    alias_pool: List[str] = []
    sess = session or (db.get_session(session_id) if session_id else {}) or {}
    for inc in (incursions or []):
        if not isinstance(inc, dict) or inc.get("resolved"):
            continue
        if str(inc.get("time_window") or "") == "after_hours":
            cur_min = int(sess.get("current_minute", 480) or 480) % 1440
            if not (cur_min >= 1200 or cur_min < 360):
                continue
        for nm in get_blueprint_alias_names(inc.get("anomaly_blueprint"), str(inc.get("entity_name") or "")):
            if nm not in alias_pool:
                alias_pool.append(nm)
    if alias_pool and session_id:
        prune_anomaly_from_scene_npcs(session_id, alias_pool[0], extra_names=alias_pool[1:], persist_db=True)


def sync_non_hostile_anomaly_scene_presence(
    session_id: Optional[int],
    *,
    session: Optional[Dict[str, Any]] = None,
    location_str: str = "",
    node_id: str = "",
    persist_db: bool = False,
) -> List[Dict[str, Any]]:
    """
    Synchronizes active non-hostile anomalies at the player's current location into `session['current_npcs']`
    so they appear in the 'Present in Scene' UI with the `[👁️ Anomaly]` badge:
      - `sapient` anomalies have `talkable: True` (`Talking` badge when focused).
      - `compulsive` anomalies have `talkable: False, pattern_observable: True` (`Observing` badge when focused).
      - `instinctual` and `non_sapient` anomalies have `talkable: False, pattern_observable: False`.
      - Automatically prunes stale anomalies from `current_npcs` when contained, escaped, agitated into
        `nearby_enemies`, or when the player moves to another location.
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else {}) or {}
    sid = int(session_id or sess.get("id") or 0)
    scen_key = str(sess.get("scenario") or "")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return list(sess.get("current_npcs") or [])

    cur_enemies = sess.get("nearby_enemies") or []
    in_combat_now = any(isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0 for e in cur_enemies)

    anom_ctx = None
    if not in_combat_now:
        anom_ctx = _resolve_active_non_hostile_anomaly_context(
            sid,
            session=sess,
            location_str=location_str,
            node_id=node_id,
        )

    cur_npcs = list(sess.get("current_npcs") or [])
    cleaned_npcs: List[Any] = []
    pruned_anom_names: set[str] = set()
    for n in cur_npcs:
        if isinstance(n, dict) and (
            n.get("is_anomalous_entity")
            or str(n.get("npc_type") or "").lower() == "anomaly"
            or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
        ):
            n_nm_low = str(n.get("name") or "").strip().lower()
            if n_nm_low:
                pruned_anom_names.add(n_nm_low)
            continue
        cleaned_npcs.append(n)

    active_focusable_anom_low = ""
    dp_changed = False
    if anom_ctx:
        bp = anom_ctx.get("blueprint") or {}
        is_rev_anom = bool(anom_ctx.get("dossier_revealed") or bp.get("dossier_revealed"))
        is_disg = is_blueprint_disguised(bp, dossier_revealed=is_rev_anom)
        ent_nm = (
            get_public_anomaly_name(bp, dossier_revealed=is_rev_anom, fallback=anom_ctx["entity_name"])
            if is_disg
            else anom_ctx["entity_name"]
        )
        eff_sap = str(anom_ctx.get("sapience") or "sapient").strip().lower()
        is_talkable = bool(eff_sap == "sapient")
        is_pattern_observable = bool(eff_sap == "compulsive")
        can_focus_interact = bool(is_talkable or is_pattern_observable)
        if can_focus_interact:
            active_focusable_anom_low = ent_nm.strip().lower()
        else:
            pruned_anom_names.add(ent_nm.strip().lower())
        temp = str(anom_ctx.get("temperament") or "timid").strip().lower()
        a_type = str(bp.get("type") or "entity").strip().title()
        form_lbl = str(bp.get("form_label") or "Anomalous Manifestation").strip()
        if eff_sap == "sapient":
            sap_disp = "Sapient — Can Converse"
        elif eff_sap == "compulsive":
            sap_disp = "Compulsive — Pattern-Bound"
        elif eff_sap == "instinctual":
            sap_disp = "Instinctual — Non-Verbal"
        else:
            sap_disp = "Non-Sapient — Automaton/Hazard"
        temp_disp_map = {
            "timid": "Timid / Skittish",
            "volatile": "Volatile / Territorial",
            "mischievous": "Mischievous / Trickster",
            "spook": "Spook / Startle-Seeker",
        }
        temp_disp = temp_disp_map.get(temp, "Timid / Skittish")
        dp_now = str(sess.get("dialogue_partner") or "").strip().lower() == ent_nm.lower()
        disg_cover = str((bp.get("disguise_state") or {}).get("cover_desc") or "")
        anom_entry = {
            "name": ent_nm,
            "role": (
                f"[Uncanny Presence] ({sap_disp})"
                if is_disg
                else f"Non-Hostile {a_type} • {form_lbl} ({sap_disp})"
            ),
            "description": (
                disg_cover
                if (is_disg and disg_cover)
                else str(
                    bp.get("sensory_omen")
                    or bp.get("description")
                    or f"An active non-hostile {form_lbl.lower()} ({temp_disp})."
                )
            ),
            "disposition": "neutral",
            "mood": temp_disp,
            "is_anomalous_entity": True,
            "is_disguised": is_disg,
            "uncanny_presence": is_disg,
            "npc_type": "anomaly",
            "social_role_type": "anomaly",
            "anomalous_npc_tag": "anomaly_entity",
            "sapience": eff_sap,
            "talkable": is_talkable,
            "pattern_observable": is_pattern_observable,
            "temperament": temp,
            "quest_id": str(anom_ctx.get("quest_id") or ""),
            "sub_obj_id": anom_ctx.get("sub_obj_id"),
            "incursion_id": str(anom_ctx.get("incursion_id") or ""),
            "dossier_revealed": is_rev_anom,
            "stage_role": "active_partner" if (dp_now and can_focus_interact) else "room_bystander",
        }
        if sid and isinstance(bp, dict) and (bp.get("blueprint_id") or bp.get("codex_id")):
            anom_sight_key = str(anom_ctx.get("incursion_id") or bp.get("blueprint_id") or bp.get("codex_id") or ent_nm)
            sighted_set = set(sess.get("_sighted_anomalies") or [])
            if anom_sight_key not in sighted_set:
                sighted_set.add(anom_sight_key)
                try:
                    db.update_session(sid, extra={"_sighted_anomalies": list(sighted_set)})
                    db.record_session_anomaly_field_log(
                        sid,
                        bp,
                        stage="sighted",
                        location=str(sess.get("current_location") or ""),
                    )
                    if bp.get("codex_id") and not is_disg:
                        db.record_folklore_codex_progress(
                            db.get_session_participant_user_ids(sid),
                            str(bp["codex_id"]),
                            stage="sighted",
                        )
                except Exception:
                    pass
        if not any(
            isinstance(x, dict) and str(x.get("name") or "").strip().lower() == ent_nm.lower()
            for x in cleaned_npcs
        ):
            cleaned_npcs.append(anom_entry)

    stale_anom_dps = {nm for nm in pruned_anom_names if nm and nm != active_focusable_anom_low}
    if stale_anom_dps:
        dp_cur = str(sess.get("dialogue_partner") or "").strip()
        if dp_cur and dp_cur.lower() in stale_anom_dps:
            sess["dialogue_partner"] = None
            dp_changed = True
        if isinstance(sess.get("dialogue_partners"), list):
            filtered_dps = [p for p in sess["dialogue_partners"] if str(p).strip().lower() not in stale_anom_dps]
            if len(filtered_dps) != len(sess["dialogue_partners"]):
                sess["dialogue_partners"] = filtered_dps
                sess["dialogue_partner"] = filtered_dps[0] if filtered_dps else None
                dp_changed = True

    sess["current_npcs"] = cleaned_npcs
    if persist_db and sid:
        try:
            if dp_changed:
                db.update_session(
                    sid,
                    current_npcs=cleaned_npcs,
                    dialogue_partner=sess.get("dialogue_partner"),
                    extra={"dialogue_partners": sess.get("dialogue_partners", [])},
                )
            else:
                db.update_session(sid, current_npcs=cleaned_npcs)
        except Exception:
            pass
    return cleaned_npcs


def build_sapient_anomaly_dialogue_choices(
    entity_name: str,
    *,
    session_id: Optional[int] = None,
    session: Optional[Dict[str, Any]] = None,
    char: Optional[Dict[str, Any]] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Builds the specialized interaction submenu for `sapient` (Lore Dialogue) and `compulsive` (Pattern Study) anomalies:
      - 3 strike-free Lore Inquiry (`sapient`) or Ritual Pattern Observation (`compulsive`) prompts
        that automatically reveal the Anomaly Dossier (`dossier_revealed = True`, `-2`/`-3` DC containment bonus).
      - The 4 contextual Containment choices.
      - Standardized FREE exit option (`Leave conversation with ...` or `Step back from observing ...`).
    """
    anom_ctx = _resolve_active_non_hostile_anomaly_context(
        session_id,
        session=session,
        entity_name=entity_name,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        incursion_id=incursion_id,
        breach_id=breach_id,
    )
    ent = str((anom_ctx or {}).get("entity_name") or entity_name or "the Anomalous Entity").strip()
    bp = blueprint or ((anom_ctx or {}).get("blueprint") if anom_ctx else None) or {}
    eff_sap = str((anom_ctx or {}).get("sapience") or bp.get("sapience") or "sapient").strip().lower()
    if eff_sap not in ("sapient", "compulsive"):
        eff_sap = "sapient"
    mode = str((anom_ctx or {}).get("mode") or ("incursion" if (incursion_id or breach_id) else "quest"))
    eff_qid = str(quest_id or (anom_ctx or {}).get("quest_id") or "")
    eff_so_id = sub_obj_id if sub_obj_id is not None else (anom_ctx or {}).get("sub_obj_id")
    eff_inc = str(incursion_id or breach_id or (anom_ctx or {}).get("incursion_id") or "")
    is_story = bool((anom_ctx or {}).get("is_story_quest"))
    stage_idx = int((anom_ctx or {}).get("stage_index", 2) or 2)
    is_rev = bool((anom_ctx or {}).get("dossier_revealed") or bp.get("dossier_revealed"))

    form_lbl = (
        "uncanny figure"
        if is_blueprint_disguised(bp, dossier_revealed=is_rev)
        else str(bp.get("form_label") or "anomalous manifestation").strip().lower()
    )
    if eff_sap == "compulsive":
        inquiry_specs = [
            (
                "anomaly_pattern_loop",
                f"👁️ [Vocal / Gesture Loop] Listen closely to {ent}'s repetitive phrases and count its exact cadence",
            ),
            (
                "anomaly_pattern_trigger",
                f"🔍 [Trigger & Reset] Observe what interrupts or resets this {form_lbl}'s ritual script",
            ),
            (
                "anomaly_pattern_courtesy",
                f"🕯️ [Courtesy & Taboo Test] Study the folklore threshold or rule binding {ent} to this spot",
            ),
        ]
        exit_lbl = f"Step back from observing {ent}"
    else:
        inquiry_specs = [
            (
                "anomaly_inquiry_origins",
                f"💬 [Origins & Folklore] Ask {ent} about its origins and how this {form_lbl} manifested here",
            ),
            (
                "anomaly_inquiry_nature",
                f"🔍 [Nature & Taboo] Question {ent} about its anomalous nature and what agitates its resonance",
            ),
            (
                "anomaly_inquiry_motive",
                f"🧭 [Motive & Bargain] Ask {ent} what it seeks here and what would convince it to yield peacefully",
            ),
        ]
        exit_lbl = f"Leave conversation with {ent}"

    inquiry_choices: List[Dict[str, Any]] = []
    if has_active_dialogue_trap(bp):
        raw_trap_choices = build_dialogue_trap_choices(
            bp,
            ent,
            quest_id=eff_qid if mode != "incursion" else "",
            sub_obj_id=eff_so_id,
            incursion_id=eff_inc,
            is_story_quest=is_story,
        )
        for tc in raw_trap_choices:
            t_act = str(tc.get("incursion_action") or "question_trap_evasive")
            if mode == "incursion":
                inquiry_choices.append({
                    "label": tc["label"][:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "target_npc": ent,
                    "incursion_action": t_act,
                    "trap_choice_kind": tc.get("trap_choice_kind", ""),
                    "incursion_id": eff_inc,
                    "breach_id": eff_inc,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": True,
                    "_server_stamped": True,
                })
            else:
                inquiry_choices.append({
                    "label": tc["label"][:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "sub_intent": t_act,
                    "target_npc": ent,
                    "quest_id": eff_qid,
                    "sub_obj_id": eff_so_id,
                    "stage_index": stage_idx,
                    "is_quest_action": False,
                    "is_story_quest": is_story,
                    "approach": t_act,
                    "incursion_action": t_act,
                    "trap_choice_kind": tc.get("trap_choice_kind", ""),
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": True,
                    "_server_stamped": True,
                })
    else:
        for inq_key, inq_lbl in inquiry_specs:
            if mode == "incursion":
                inquiry_choices.append({
                    "label": inq_lbl[:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "target_npc": ent,
                    "incursion_action": inq_key,
                    "incursion_id": eff_inc,
                    "breach_id": eff_inc,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": False,
                    "_server_stamped": True,
                })
            else:
                inquiry_choices.append({
                    "label": inq_lbl[:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "sub_intent": inq_key,
                    "target_npc": ent,
                    "quest_id": eff_qid,
                    "sub_obj_id": eff_so_id,
                    "stage_index": stage_idx,
                    "is_quest_action": False,
                    "is_story_quest": is_story,
                    "approach": inq_key,
                    "incursion_action": inq_key,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": False,
                    "_server_stamped": True,
                })

    containment_choices = build_non_hostile_narrative_choices(
        ent,
        mode=mode,
        char=char,
        quest_id=eff_qid,
        sub_obj_id=eff_so_id,
        stage_index=stage_idx,
        is_story_quest=is_story,
        incursion_id=eff_inc,
        breach_id=eff_inc,
        sapience=eff_sap,
        blueprint=bp if bp else None,
        dossier_revealed=is_rev,
        session_id=session_id,
        include_converse=False,
    )

    exit_choice = {
        "label": exit_lbl,
        "stat": "NONE",
        "requirement": 0,
        "mp_cost": 0,
        "is_fallback": False,
        "intent": "dialogue_exit",
        "ends_dialogue": True,
        "_pinned_dialogue_exit": True,
        "_server_stamped": True,
    }
    return inquiry_choices + containment_choices + [exit_choice]


def resolve_anomaly_dialogue_inquiry(
    session_id: int,
    *,
    entity_name: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    inquiry_type: str = "anomaly_inquiry",
    player_text: str = "",
    user_id: Optional[int] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolves a strike-free Lore Inquiry (`sapient`) or Ritual Pattern Study (`compulsive`) with a non-hostile anomaly:
      - Rejects interaction if the anomaly is `instinctual` or `non_sapient`.
      - Automatically unseals the Anomaly Dossier (`reveal_anomaly_dossier`), unlocking the `-2` DC
        containment bonus (`-3` DC on Taboo `exploit_stats`).
      - Sets `dialogue_partner = entity_name` (rendered as `Talking` for `sapient`, `Observing` for `compulsive`).
      - For `compulsive` entities, enforces strict non-rational repetition/mimicry directives (zero Q&A small talk).
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    anom_ctx = _resolve_active_non_hostile_anomaly_context(
        session_id,
        session=sess,
        entity_name=entity_name,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        incursion_id=incursion_id,
        breach_id=breach_id,
    )
    ent = str((anom_ctx or {}).get("entity_name") or entity_name or "the Anomalous Entity").strip()
    eff_qid = str(quest_id or (anom_ctx or {}).get("quest_id") or "")
    eff_inc = str(incursion_id or breach_id or (anom_ctx or {}).get("incursion_id") or "")
    bp = ((anom_ctx or {}).get("blueprint") if anom_ctx else None) or {}
    eff_sap = str((anom_ctx or {}).get("sapience") or bp.get("sapience") or "sapient").strip().lower()

    if eff_sap not in ("sapient", "compulsive"):
        return {
            "success": False,
            "talkable": False,
            "pattern_observable": False,
            "resolved": False,
            "sapience": eff_sap,
            "message": (
                f"⚠️ **{ent}** is **{eff_sap.replace('_', '-').title()}** and lacks human speech or ritual loop scripts—"
                f"use field containment tactics instead of verbal conversation."
            ),
        }

    inq_low = str(inquiry_type or "anomaly_inquiry").strip().lower()
    if has_active_dialogue_trap(bp) and inq_low in ("converse", "study_pattern") and not str(player_text or "").strip():
        pub_ent = get_public_anomaly_name(bp, fallback=ent)
        dt_prompt = str((bp.get("dialogue_trap") or {}).get("prompt_question") or "Do you recognize what I am?")
        sess["dialogue_partner"] = pub_ent
        sess["dialogue_partners"] = [pub_ent]
        sync_non_hostile_anomaly_scene_presence(session_id, session=sess, persist_db=False)
        try:
            db.update_session(
                session_id,
                current_npcs=sess.get("current_npcs", []),
                dialogue_partner=pub_ent,
                extra={"dialogue_partners": [pub_ent]},
            )
        except Exception:
            pass
        trap_open_msg = (
            f"❓ **Folklore Riddle Trap:** **{pub_ent}** fixes an unblinking gaze on you and asks: *\"{dt_prompt}\"* "
            f"(Beware answering a direct Yes or No—folklore riddles often punish both binary answers!)"
        )
        return {
            "success": True,
            "question_trap_presented": True,
            "talkable": eff_sap == "sapient",
            "pattern_observable": eff_sap == "compulsive",
            "sapience": eff_sap,
            "resolved": False,
            "dossier_revealed": bool(bp.get("dossier_revealed")),
            "dialogue_partner": pub_ent,
            "message": trap_open_msg,
            "directive": (
                f"[MANDATORY FOLKLORE RIDDLE TRAP OPENING]:\n"
                f"- **{pub_ent}** confronts the player with a binding folklore question-trap: \"{dt_prompt}\".\n"
                f"- Keep **{pub_ent}**'s true identity veiled if disguised, and end the turn waiting for the player's answer (`dialogue_partner` = `{pub_ent}`)."
            ),
        }

    trap_kind = (
        "evasive"
        if "evasive" in inq_low
        else ("trap_yes" if "trap_yes" in inq_low else ("trap_no" if "trap_no" in inq_low else ""))
    )
    pre_trap_eval: Dict[str, Any] = {}
    if (trap_kind or player_text) and isinstance((bp or {}).get("dialogue_trap"), dict) and not (bp or {}).get("dialogue_trap", {}).get("resolved"):
        pre_trap_eval = evaluate_dialogue_trap_response(bp, player_text=player_text, trap_choice_kind=trap_kind)
    trap_sprung = bool(pre_trap_eval.get("matched") and pre_trap_eval.get("triggered_trap"))

    # Falling into a binary Question-Trap never rewards the player with a Dossier reveal / unmasking
    rev_res = {} if trap_sprung else reveal_anomaly_dossier(
        session_id=session_id,
        quest_id=eff_qid,
        incursion_id=eff_inc,
        breach_id=eff_inc,
    )
    bp = rev_res.get("blueprint") or bp or {}
    d_sum = str(rev_res.get("dossier_summary") or "Anomaly Taboo and Containment Protocol unsealed.")
    unmasked_from = str(rev_res.get("unmasked_from") or "").strip()
    if rev_res.get("unmask_notice") and bp.get("canonical_name"):
        ent = str(bp["canonical_name"])
    if trap_sprung:
        ent = get_public_anomaly_name(bp, dossier_revealed=bool(bp.get("dossier_revealed")), fallback=ent)

    if session_id:
        fresh_after_rev = db.get_session(session_id) or {}
        if "daily_incursions" in fresh_after_rev:
            sess["daily_incursions"] = fresh_after_rev["daily_incursions"]
        if "daily_breaches" in fresh_after_rev:
            sess["daily_breaches"] = fresh_after_rev["daily_breaches"]

    sess["dialogue_partner"] = ent
    sess["dialogue_partners"] = [ent]
    sync_non_hostile_anomaly_scene_presence(session_id, session=sess, persist_db=False)
    try:
        db.update_session(
            session_id,
            current_npcs=sess.get("current_npcs", []),
            dialogue_partner=ent,
            extra={"dialogue_partners": [ent]},
        )
    except Exception:
        pass

    form_lbl = str(bp.get("form_label") or "anomalous manifestation")
    trad_lbl = str(bp.get("folklore_tradition") or "urban_legend").replace("_", " ").title()
    omen_str = str(bp.get("sensory_omen") or "A localized distortion hums around the entity.")
    taboo_name = str(bp.get("taboo_name") or (bp.get("taboo") or {}).get("name") or "Folklore Taboo")
    taboo_rule = str(bp.get("taboo_rule") or (bp.get("taboo") or {}).get("taboo_rule") or "Avoid sudden aggressive force.")
    proto_str = str(bp.get("containment_protocol") or (bp.get("taboo") or {}).get("containment_protocol") or "Approach with calm, measured protocol.")

    if pre_trap_eval and isinstance(bp.get("dialogue_trap"), dict):
        trap_eval = pre_trap_eval
        if trap_eval.get("matched"):
            bp["dialogue_trap"] = {**dict(bp["dialogue_trap"]), "resolved": True}
            lead_uid_trap = int(user_id or sess.get("host_user_id") or 1)
            if eff_inc:
                incs_t = list((db.get_session(session_id) or sess).get("daily_incursions") or [])
                for inc_t in incs_t:
                    if isinstance(inc_t, dict) and (inc_t.get("incursion_id") == eff_inc or inc_t.get("breach_id") == eff_inc):
                        inc_t["anomaly_blueprint"] = bp
                        if trap_eval.get("satisfied"):
                            inc_t["prank_dc_penalty"] = -3
                        elif trap_eval.get("triggered_trap"):
                            # A sprung trap is a warning strike; it never silently exhausts the final escape strike
                            max_st = int(inc_t.get("max_strikes", 2) or 2)
                            inc_t["strikes"] = min(
                                max(0, max_st - 1),
                                int(inc_t.get("strikes", 0) or 0) + int(trap_eval.get("strike_delta", 1) or 1),
                            )
                db.update_session(session_id, extra={"daily_incursions": incs_t, "daily_breaches": None})
                sess["daily_incursions"] = incs_t
                sess["daily_breaches"] = incs_t
            elif eff_qid:
                q_t = db.get_quest_by_id(session_id, eff_qid) or {}
                notes_t = str(q_t.get("quest_notes") or "")
                new_tok = serialize_blueprint_note(bp).split("|", 1)[0]
                cleaned_t = re.sub(r"anomaly_(?:bp|blueprint):[A-Za-z0-9+/=_-]+", new_tok, notes_t)
                db.update_quest_anomaly_blueprint(session_id, eff_qid, bp, quest_notes=cleaned_t)
            if trap_eval.get("triggered_trap") and lead_uid_trap:
                try:
                    db.apply_hp_mp_delta(lead_uid_trap, hp_delta=-int(trap_eval.get("backlash_damage", 8) or 8))
                except Exception:
                    pass
            trap_msg = (
                f"{trap_eval['message']} 🔍 **Anomaly Dossier Unsealed:** {d_sum}"
                if not trap_sprung
                else f"{trap_eval['message']} *(Its true nature remains veiled.)*"
            )
            return {
                "success": bool(trap_eval.get("satisfied")),
                "question_trap_evaluated": True,
                "trap_satisfied": bool(trap_eval.get("satisfied")),
                "trap_triggered": bool(trap_eval.get("triggered_trap")),
                "talkable": eff_sap == "sapient",
                "pattern_observable": eff_sap == "compulsive",
                "sapience": eff_sap,
                "resolved": False,
                "dossier_revealed": not trap_sprung,
                "dialogue_partner": ent,
                "unmasked_from": unmasked_from,
                "dossier_summary": "" if trap_sprung else d_sum,
                "message": trap_msg,
                "directive": (
                    f"[MANDATORY FOLKLORE QUESTION-TRAP OUTCOME]: {trap_eval['message']} "
                    f"Narrate how **{ent}** reacts to the player's answer without leaking raw HP or DC integers."
                ),
            }

    paradox_obs = evaluate_omen_paradox(bp, dossier_revealed=True, is_observation=True)
    paradox_suffix = f" {paradox_obs['note']}" if paradox_obs.get("has_paradox") else ""
    if eff_sap == "compulsive":
        if "loop" in inq_low:
            obs_focus = f"its clockwork repetition cadence as a {form_lbl} rooted in {trad_lbl} lore ({omen_str})"
        elif "trigger" in inq_low:
            obs_focus = f"what interrupts or agitates its ritual loop (**{taboo_name}**: *{taboo_rule}*)"
        elif "courtesy" in inq_low:
            obs_focus = f"the exact folklore counter-script that satisfies its compulsion (*{proto_str}*)"
        else:
            obs_focus = f"its repetitive {form_lbl.lower()} loop, **{taboo_name}** (*{taboo_rule}*), and ritual counter-script (*{proto_str}*)"

        msg = (
            f"👁️ **Studied {ent}'s Ritual Pattern (Strike-Free Observation):** Watching the pattern-bound {form_lbl.lower()} "
            f"from a careful distance, you decipher {obs_focus}. 🔍 **Anomaly Dossier Unsealed:** {d_sum}{paradox_suffix}"
        )
        directive = (
            f"[MANDATORY COMPULSIVE ANOMALY PATTERN STUDY & DOSSIER REVEAL]:\n"
            f"- The player is quietly observing the **Compulsive (Pattern-Bound)** non-hostile anomaly **{ent}** ({form_lbl}, {trad_lbl}).\n"
            f"- Focus of observation: {obs_focus}.\n"
            f"- CRITICAL PROSE RULE: **{ent}** is NOT rationally sapient and CANNOT hold a normal Q&A conversation or explain its backstory in lucid prose!\n"
            f"- Depict **{ent}** ONLY repeating eerie scripted phrases, counting, mimicking sounds, or performing clockwork folklore gestures that reveal **{taboo_name}** ({taboo_rule}) and its ritual counter-protocol ({proto_str}) without leaking raw game numbers or DC stats.\n"
            f"- Keep `dialogue_partner` set to `{ent}` while observing; the anomaly is NOT yet contained until the player executes a containment action."
        )
        return {
            "success": True,
            "talkable": False,
            "pattern_observable": True,
            "sapience": "compulsive",
            "resolved": False,
            "dossier_revealed": True,
            "dialogue_partner": ent,
            "unmasked_from": unmasked_from,
            "dossier_summary": d_sum,
            "message": msg,
            "directive": directive,
        }

    if "origin" in inq_low:
        topic_focus = f"its origins as a {form_lbl} rooted in {trad_lbl} lore ({omen_str})"
    elif "nature" in inq_low or "taboo" in inq_low:
        topic_focus = f"its anomalous nature and **{taboo_name}** (*{taboo_rule}*)"
    elif "motive" in inq_low or "bargain" in inq_low:
        topic_focus = f"why it lingers at this anchor point and the terms required for peaceful containment (*{proto_str}*)"
    else:
        topic_focus = f"its origins ({form_lbl}), **{taboo_name}** (*{taboo_rule}*), and peaceful containment terms (*{proto_str}*)"

    msg = (
        f"💬 **Conversed with {ent} (Strike-Free Lore Inquiry):** Through direct dialogue with the sapient {form_lbl.lower()}, "
        f"you uncover {topic_focus}. 🔍 **Anomaly Dossier Unsealed:** {d_sum}{paradox_suffix}"
    )
    directive = (
        f"[MANDATORY SAPIENT ANOMALY DIALOGUE & DOSSIER REVEAL]:\n"
        f"- The player is conversing directly with the sapient non-hostile anomaly **{ent}** ({form_lbl}, {trad_lbl}).\n"
        f"- Focus of inquiry: {topic_focus}.\n"
        f"- Voice **{ent}** in-character as an eerie, otherworldly yet articulate {form_lbl.lower()}—NEVER as a mundane human peer making small talk.\n"
        f"- Have **{ent}** reveal its nature, taboo (**{taboo_name}**: {taboo_rule}), and what would convince it to yield peacefully ({proto_str}) without leaking raw game numbers or DC stats.\n"
        f"- Keep `dialogue_partner` set to `{ent}`; the anomaly is NOT yet contained until the player executes a containment action."
    )
    return {
        "success": True,
        "talkable": True,
        "pattern_observable": False,
        "sapience": "sapient",
        "resolved": False,
        "dossier_revealed": True,
        "dialogue_partner": ent,
        "unmasked_from": unmasked_from,
        "dossier_summary": d_sum,
        "message": msg,
        "directive": directive,
    }
