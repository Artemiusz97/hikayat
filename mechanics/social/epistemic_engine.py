from __future__ import annotations

"""
Deterministic Epistemic Asymmetry Engine (Part B, B1-B17).

Handles:
- Scene witness detection with focus weighting, B9 companion alignment, B13 mask/stealth
  culprit anonymization, and B14 dialogue/public-venue overhearing.
- Containment actions (hush/bribe/threaten/discretion/confide/deny/proof/leverage) including
  B16 +2 DC kin/roommate/best_friend penalty.
- B17 deterministic witness neutralization on combat/skill knockout or death.
- Boundary-tick 1-hop gossip propagation, 2+ source corroboration, B5 Caught Lying checks,
  B8 rumor heat decay, B11 watch-role escalations, and B16 next-block kin alerts.
- B15 server-side fencing of LLM EpistemicSignal emissions.
"""

import random
from typing import Any, Mapping, Sequence

import db
from mechanics.stealth.alert_tracker import ALERT_DETECTED, get_alert_stage
from mechanics.social.epistemic_propagation import (
    _CONCEALING_GARMENT_TOKENS,
    _actor_key,
    _extract_present_actor_keys,
    _is_face_concealed,
    _is_kin_roommate_or_best_friend,
    _is_proof_ref_held,
    _is_watch_role,
    _norm_key,
    _npc_aliases,
    _parse_dict,
    _resolve_npc_schedule_node,
    resolve_fenced_epistemic_signal,
    tick_epistemic_boundary_propagation,
)

__all__ = [
    "_CONCEALING_GARMENT_TOKENS",
    "_SECRET_INTENTS",
    "_LAWFUL_TRAITS",
    "_ROGUISH_TRAITS",
    "_norm_key",
    "_parse_dict",
    "_actor_key",
    "_npc_aliases",
    "_is_watch_role",
    "_is_face_concealed",
    "_is_kin_roommate_or_best_friend",
    "_resolve_npc_schedule_node",
    "_extract_present_actor_keys",
    "_is_proof_ref_held",
    "detect_scene_witnesses",
    "resolve_containment_or_epistemic_action",
    "neutralize_witnesses_from_combat_or_skill",
    "tick_epistemic_boundary_propagation",
    "resolve_fenced_epistemic_signal",
]

_SECRET_INTENTS: frozenset[str] = frozenset({
    "intimate_act", "affection_touch", "romantic_confession", "stealth_covert",
    "disclosure_inquiry", "epistemic_containment",
})
_LAWFUL_TRAITS: tuple[str, ...] = (
    "lawful", "paladin", "disciplinary", "inspector", "monitor", "righteous", "knight", "strict",
)
_ROGUISH_TRAITS: tuple[str, ...] = (
    "rogue", "thief", "smuggler", "cynical", "accomplice", "delinquent", "pragmatic", "loyal",
)


def _extract_witnessable_deed(session: Mapping[str, Any], act_payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Determines if an action/turn triggers epistemic fact tracking."""
    explicit_fk = str(act_payload.get("fact_key") or "").strip()
    intent = _norm_key(act_payload.get("intent"))
    sub_intent = _norm_key(act_payload.get("sub_intent"))
    has_deed_flag = bool(
        explicit_fk
        or act_payload.get("is_secret_deed")
        or act_payload.get("is_crime")
        or act_payload.get("is_spoken_confession")
        or act_payload.get("witnessable")
        or intent in _SECRET_INTENTS
        or sub_intent in ("pickpocket", "lockpick", "hide", "eavesdrop", "intercourse", "kiss", "affair")
    )
    if not has_deed_flag:
        return None

    cat = str(act_payload.get("category") or "").strip().lower()
    if not cat:
        if intent in ("intimate_act", "affection_touch", "romantic_confession"):
            cat = "affair" if act_payload.get("is_illicit") or act_payload.get("has_exclusive_partner") else "secret"
        elif intent == "stealth_covert" or sub_intent in ("pickpocket", "lockpick"):
            cat = "crime"
        else:
            cat = "secret"

    turn_num = int(act_payload.get("turn") or session.get("turn_count") or 0)
    loc_node = str(
        act_payload.get("location_node_id") or session.get("current_location_node_id") or session.get("location") or ""
    ).strip()
    fkey = explicit_fk or f"{cat}_{loc_node or 'scene'}_{turn_num}"
    sev = int(act_payload.get("severity") or (2 if cat in ("crime", "affair", "faction_breach") else 1))
    sev = max(1, min(3, sev))
    summary = str(act_payload.get("summary") or act_payload.get("action_text") or f"Observed {cat} event").strip()[:220]
    proof_ref = str(act_payload.get("proof_artifact_ref") or "").strip()

    stealth_val = act_payload.get("alert_level")
    if stealth_val is None:
        stealth_val = session.get("stealth_alert_level")
    concealed = _is_face_concealed(session, act_payload)
    stealth_unblown = (stealth_val is not None) and (get_alert_stage(int(stealth_val)) != ALERT_DETECTED) and intent == "stealth_covert"

    if concealed or stealth_unblown:
        culprit = "unknown"
    else:
        culprit = _norm_key(act_payload.get("culprit_actor_key") or "player") or "player"

    subject = _norm_key(act_payload.get("subject_actor_key") or "")
    return {
        "fact_key": fkey,
        "category": cat,
        "culprit_actor_key": culprit,
        "subject_actor_key": subject,
        "location_node_id": loc_node,
        "summary": summary,
        "severity": sev,
        "proof_artifact_ref": proof_ref,
        "heat_score": int(act_payload.get("heat_score") or (40 + sev * 15)),
    }


def detect_scene_witnesses(
    session_id: int,
    session: Mapping[str, Any],
    present_npcs: Sequence[Mapping[str, Any]],
    nearby_npcs: Sequence[Mapping[str, Any]],
    act_payload: Mapping[str, Any],
    rng: random.Random | Any,
    *,
    turn: int = 0,
    conn=None,
) -> list[dict[str, Any]]:
    """
    Detects real world_roster witnesses for sensitive/witnessable player actions (`B3`, `B9`, `B13`, `B14`).
    Writes `epistemic_facts` and staged `epistemic_knowledge` rows (`player_aware=1`).
    """
    deed = _extract_witnessable_deed(session, act_payload)
    if deed is None:
        return []

    sid = int(session_id or 0)
    t_num = int(turn or act_payload.get("turn") or session.get("turn_count") or 0)
    fkey = deed["fact_key"]
    culprit = deed["culprit_actor_key"]
    subject = deed["subject_actor_key"]

    dialogue_partners = {_norm_key(x) for x in (act_payload.get("dialogue_partners") or ()) if _norm_key(x)}
    is_spoken = bool(act_payload.get("is_spoken_confession") or dialogue_partners)
    is_private_room = bool(act_payload.get("is_private_venue"))
    stealth_val = act_payload.get("alert_level")
    if stealth_val is None:
        stealth_val = session.get("stealth_alert_level")
    stealth_undetected = (
        _norm_key(act_payload.get("intent")) == "stealth_covert"
        and stealth_val is not None
        and get_alert_stage(int(stealth_val)) != ALERT_DETECTED
        and not act_payload.get("force_spotted")
    )

    events_out: list[dict[str, Any]] = []
    seen_holders: set[str] = set()

    def _ensure_fact() -> None:
        db.upsert_epistemic_fact(
            sid,
            fkey,
            category=deed["category"],
            culprit_actor_key=culprit,
            subject_actor_key=subject,
            location_node_id=deed["location_node_id"],
            summary=deed["summary"],
            severity=deed["severity"],
            proof_artifact_ref=deed["proof_artifact_ref"],
            heat_score=deed["heat_score"],
            decay_day_last_ticked=int(session.get("current_day") or 1),
            status="active",
            turn=t_num,
            conn=conn,
        )

    fact_persisted = False

    def _record_holder(
        holder_k: str,
        *,
        confidence: str,
        containment_state: str,
        channel: str,
        objected: bool = False,
    ) -> None:
        nonlocal fact_persisted
        if not holder_k or holder_k in seen_holders:
            return
        seen_holders.add(holder_k)
        if not fact_persisted:
            _ensure_fact()
            fact_persisted = True
        db.upsert_epistemic_knowledge(
            sid,
            fkey,
            holder_k,
            confidence=confidence,
            containment_state=containment_state,
            source_actor_key="player" if channel == "dialogue" else holder_k,
            acquisition_channel=channel,
            hop_count=0,
            player_aware=1,
            turn=t_num,
            conn=conn,
        )
        events_out.append({
            "fact_key": fkey,
            "holder_actor_key": holder_k,
            "confidence": confidence,
            "containment_state": containment_state,
            "acquisition_channel": channel,
            "culprit_actor_key": culprit,
            "objected": objected,
            "player_aware": 1,
        })

    def _roll_float() -> float:
        return float(rng.random()) if hasattr(rng, "random") else 0.0

    # Pool: present NPCs then nearby NPCs
    all_candidates = [(npc, True) for npc in (present_npcs or ())] + [(npc, False) for npc in (nearby_npcs or ())]
    for npc, is_present in all_candidates:
        if not isinstance(npc, Mapping):
            continue
        hk = _actor_key(npc)
        if not hk or hk in seen_holders:
            continue

        stage_role = _norm_key(npc.get("stage_role"))
        basic = _parse_dict(npc.get("basic_info") or npc.get("basic_info_json"))
        traits_blob = " ".join(
            str(x or "").lower()
            for x in (npc.get("traits"), npc.get("alignment"), npc.get("role"), basic.get("traits"), basic.get("alignment"))
        )
        aff = int(npc.get("affinity") or npc.get("relationship_level") or basic.get("affinity") or 0)
        is_party = bool(npc.get("in_party") or stage_role == "party_companion")

        # 1. B14 Dialogue partners learn spoken secrets at firsthand
        aliases = _npc_aliases(npc)
        if is_spoken and (hk in dialogue_partners or (aliases & dialogue_partners)):
            _record_holder(
                hk,
                confidence="firsthand",
                containment_state="active",
                channel="dialogue",
            )
            continue

        # 2. B9 Party companions: loyal/roguish become co_conspirator, lawful object
        if is_party:
            is_lawful = any(tok in traits_blob for tok in _LAWFUL_TRAITS)
            is_loyal_or_rogue = (aff >= 60) or any(tok in traits_blob for tok in _ROGUISH_TRAITS)
            if is_lawful and not is_loyal_or_rogue:
                _record_holder(
                    hk,
                    confidence="firsthand",
                    containment_state="spotted_window",
                    channel="witness",
                    objected=True,
                )
            elif is_loyal_or_rogue:
                _record_holder(
                    hk,
                    confidence="firsthand",
                    containment_state="co_conspirator",
                    channel="witness",
                    objected=False,
                )
            else:
                _record_holder(
                    hk,
                    confidence="firsthand",
                    containment_state="spotted_window",
                    channel="witness",
                )
            continue

        # Stealth stays unwitnessed if alert < ALERT_DETECTED (100) and not forced
        if stealth_undetected:
            continue

        focus_mod = max(0, int(npc.get("focus_dc_mod") or 0))
        watch_bonus = 0.2 if (is_present and _is_watch_role(npc)) else 0.0

        # 3. B14 Public-venue overhearing for spoken confessions / loud confrontations
        if is_spoken:
            if is_private_room and not is_present:
                continue
            base_hear = (0.18 if is_private_room else (0.72 if is_present else 0.35)) + watch_bonus
            hear_prob = max(0.05, min(0.95, base_hear - 0.25 * focus_mod))
            if act_payload.get("force_spotted") or _roll_float() < hear_prob:
                _record_holder(
                    hk,
                    confidence="firsthand" if (is_present and focus_mod == 0 and not is_private_room) else "rumor",
                    containment_state="spotted_window",
                    channel="overheard",
                )
            continue

        # 4. B3 Visual/physical scene spotting weighted by focus_dc_mod
        if hk == subject and act_payload.get("subject_is_participant"):
            continue
        base_spot = (0.85 if is_present else (0.08 if is_private_room else 0.35)) + watch_bonus
        spot_prob = max(0.05, min(0.98, base_spot - 0.28 * focus_mod))
        if act_payload.get("force_spotted") or _roll_float() < spot_prob:
            _record_holder(
                hk,
                confidence="firsthand" if is_present else "rumor",
                containment_state="spotted_window",
                channel="witness",
            )

    return events_out


def _evaluate_check_passed(check_res: Any, extra_dc: int = 0) -> tuple[bool, int, int]:
    """Re-evaluates a check result dict or CheckResult object cleanly under an additive DC penalty."""
    if check_res is None:
        return True, 0, 0
    if isinstance(check_res, Mapping):
        passed = bool(check_res.get("passed", True))
        total = check_res.get("total")
        dc = check_res.get("dc")
    else:
        passed = bool(getattr(check_res, "passed", True))
        total = getattr(check_res, "total", None)
        dc = getattr(check_res, "dc", None)

    if total is not None and dc is not None:
        eff_dc = int(dc) + int(extra_dc)
        return int(total) >= eff_dc, int(total), eff_dc
    return passed, 0, int(extra_dc)


def resolve_containment_or_epistemic_action(
    session_id: int,
    session: Mapping[str, Any],
    action_subtype: str,
    fact_key: str,
    target_actor_key: str,
    check_res: Any,
    turn: int,
    *,
    alibi_claim: str = "",
    alibi_witness_key: str = "",
    proof_artifact_ref: str = "",
    gold_spent: int = 0,
    social_ties: Sequence[Mapping[str, Any]] = (),
    households: Sequence[Mapping[str, Any]] = (),
    contacts: Sequence[Mapping[str, Any]] = (),
    conn=None,
) -> dict[str, Any]:
    """
    Executes player containment, confession/denial, proof, leverage, or damage-control actions
    (`B3`, `B5`, `B6`, `B8`, `B10`, `B16`).
    """
    sid = int(session_id or 0)
    subtype = _norm_key(action_subtype)
    fkey = str(fact_key or "").strip()
    target_k = _norm_key(target_actor_key)
    t_num = int(turn or 0)

    fact = db.get_epistemic_fact(sid, fkey, conn=conn) if fkey else None
    subject_k = _norm_key((fact or {}).get("subject_actor_key"))

    # B16: +2 DC hush penalty when target is kin, roommate, or best_friend of wronged subject
    extra_dc = 0
    if subtype in ("hush_bribe", "threaten_silence", "discretion_request") and subject_k and target_k:
        if _is_kin_roommate_or_best_friend(
            subject_k,
            target_k,
            social_ties=social_ties,
            households=households,
            contacts=contacts,
        ):
            extra_dc = 2

    passed, total_roll, eff_dc = _evaluate_check_passed(check_res, extra_dc)
    result: dict[str, Any] = {
        "ok": True,
        "action_subtype": subtype,
        "fact_key": fkey,
        "target_actor_key": target_k,
        "passed": passed,
        "effective_dc_mod": extra_dc,
        "effective_dc": eff_dc,
        "roll_total": total_roll,
        "containment_state": "",
        "trust_delta": 0,
        "heat_delta": 0,
        "affected_facts": [],
    }

    if subtype in ("hush_bribe", "threaten_silence", "discretion_request"):
        if not fkey or not target_k:
            result["ok"] = False
            return result
        cur_heat = int((fact or {}).get("heat_score") or 50)
        if passed:
            db.upsert_epistemic_knowledge(
                sid, fkey, target_k,
                containment_state="hushed",
                player_aware=1,
                turn=t_num,
                metadata={"hush_gold_spent": int(gold_spent or 0), "hush_method": subtype},
                conn=conn,
            )
            new_heat = max(10, cur_heat - 10)
            if fact:
                db.upsert_epistemic_fact(sid, fkey, heat_score=new_heat, turn=t_num, conn=conn)
            result["containment_state"] = "hushed"
            result["heat_delta"] = new_heat - cur_heat
            result["trust_delta"] = -5 if subtype == "threaten_silence" else 0
        else:
            db.upsert_epistemic_knowledge(
                sid, fkey, target_k,
                containment_state="active",
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
            new_heat = min(100, cur_heat + 15)
            if fact:
                db.upsert_epistemic_fact(sid, fkey, heat_score=new_heat, turn=t_num, conn=conn)
            result["containment_state"] = "active"
            result["heat_delta"] = new_heat - cur_heat
            result["trust_delta"] = -15 if subtype == "threaten_silence" else -8
        return result

    if subtype == "confide":
        if not fkey or not target_k:
            result["ok"] = False
            return result
        db.upsert_epistemic_knowledge(
            sid, fkey, target_k,
            confidence="firsthand",
            containment_state="co_conspirator",
            source_actor_key="player",
            acquisition_channel="dialogue",
            player_aware=1,
            alibi_claim="",
            is_alibi_busted=0,
            turn=t_num,
            conn=conn,
        )
        result["containment_state"] = "co_conspirator"
        result["trust_delta"] = 10
        return result

    if subtype == "deny":
        if not fkey or not target_k:
            result["ok"] = False
            return result
        claim_txt = str(alibi_claim or "I was nowhere near there.").strip()
        wkey = _norm_key(alibi_witness_key)
        db.upsert_epistemic_knowledge(
            sid, fkey, target_k,
            containment_state="hushed" if passed else "active",
            player_aware=1,
            alibi_claim=claim_txt,
            alibi_witness_key=wkey,
            is_alibi_busted=0,
            turn=t_num,
            conn=conn,
        )
        result["containment_state"] = "hushed" if passed else "active"
        return result

    if subtype in ("present_proof", "destroy_proof"):
        pref = str(proof_artifact_ref or (fact or {}).get("proof_artifact_ref") or "").strip()
        if not pref:
            result["ok"] = False
            return result
        action_mode = "present" if subtype == "present_proof" else "destroy_or_steal"
        affected = db.downgrade_or_upgrade_proof_ref(
            sid, pref, action=action_mode, target_holder_key=target_k, turn=t_num, conn=conn,
        )
        result["affected_facts"] = affected
        result["containment_state"] = "active" if subtype == "present_proof" else "hushed"
        return result

    if subtype in ("use_leverage", "warn_target"):
        if not fkey or not target_k:
            result["ok"] = False
            return result
        if subtype == "use_leverage":
            cstate = "co_conspirator" if passed else "active"
            db.upsert_epistemic_knowledge(
                sid, fkey, target_k,
                containment_state=cstate,
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
            result["containment_state"] = cstate
            result["trust_delta"] = -10 if passed else -18
        else:
            db.upsert_epistemic_knowledge(
                sid, fkey, target_k,
                containment_state="hushed",
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
            result["containment_state"] = "hushed"
            result["trust_delta"] = 12
        return result

    if subtype == "damage_control":
        if not fact:
            result["ok"] = False
            return result
        cur_heat = int(fact.get("heat_score") or 50)
        drop = 20 if passed else 5
        new_heat = max(0, cur_heat - drop)
        new_status = "decayed" if new_heat == 0 else str(fact.get("status") or "active")
        db.upsert_epistemic_fact(
            sid, fkey, heat_score=new_heat, status=new_status, turn=t_num, conn=conn,
        )
        result["heat_delta"] = new_heat - cur_heat
        return result

    result["ok"] = False
    return result


def neutralize_witnesses_from_combat_or_skill(
    session_id: int,
    defeated_npcs: Sequence[Any],
    killed_npcs: Sequence[Any],
    present_witnesses: Sequence[Mapping[str, Any]] = (),
    turn: int = 0,
    *,
    location_node_id: str = "",
    mode: str = "combat",
    conn=None,
) -> list[dict[str, Any]]:
    """
    B17: Deterministic witness neutralization on combat/skill KO or kill.
    Silences `spotted_window`/`active` witnesses who were neutralized, while creating a
    higher-severity Crime fact for any surviving eyewitnesses.
    """
    sid = int(session_id or 0)
    t_num = int(turn or 0)
    killed_keys = {_actor_key(x) for x in (killed_npcs or ()) if _actor_key(x)}
    defeated_keys = {_actor_key(x) for x in (defeated_npcs or ()) if _actor_key(x)} - killed_keys
    neutralized = killed_keys | defeated_keys
    updates: list[dict[str, Any]] = []

    if sid and neutralized:
        all_rows = db.get_epistemic_knowledge_rows(sid, conn=conn)
        for row in all_rows:
            hk = _norm_key(row.get("holder_actor_key"))
            if hk not in neutralized:
                continue
            if str(row.get("containment_state") or "") not in ("spotted_window", "active"):
                continue
            target_state = "wiped" if hk in killed_keys else "incapacitated"
            db.upsert_epistemic_knowledge(
                sid,
                row["fact_key"],
                hk,
                containment_state=target_state,
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
            updates.append({
                "kind": "witness_neutralized",
                "fact_key": row["fact_key"],
                "holder_actor_key": hk,
                "containment_state": target_state,
            })

    # Surviving witnesses record a higher-severity assault/homicide crime fact (physical combat/KO only)
    survivors = [w for w in (present_witnesses or ()) if isinstance(w, Mapping) and _actor_key(w) not in neutralized]
    if sid and neutralized and survivors and mode not in ("skill", "pact", "memory_wipe", "patron_suppress"):
        verb = "killing" if killed_keys else "assault"
        crime_fk = f"crime_{verb}_{_norm_key(location_node_id) or 'scene'}_{t_num}"
        db.upsert_epistemic_fact(
            sid,
            crime_fk,
            category="crime",
            culprit_actor_key="player",
            subject_actor_key=next(iter(sorted(neutralized))),
            location_node_id=str(location_node_id or "").strip(),
            summary=f"Witnessed {verb} during {mode} encounter",
            severity=3,
            heat_score=85,
            status="active",
            turn=t_num,
            conn=conn,
        )
        for sw in survivors:
            sk = _actor_key(sw)
            if not sk:
                continue
            db.upsert_epistemic_knowledge(
                sid,
                crime_fk,
                sk,
                confidence="firsthand",
                containment_state="active",
                source_actor_key=sk,
                acquisition_channel="witness",
                hop_count=0,
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
            updates.append({
                "kind": "survivor_crime_witness",
                "fact_key": crime_fk,
                "holder_actor_key": sk,
                "severity": 3,
                "containment_state": "active",
            })

    return updates
