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

import json
import random
from typing import Any, Mapping, Sequence

import db
from mechanics.stealth.alert_tracker import ALERT_DETECTED, get_alert_stage
from mechanics.world.world_events.social_hooks import _KIN_AND_PARTNER_TOKENS, _WATCH_ROLE_TOKENS

_SECRET_INTENTS: frozenset[str] = frozenset({
    "intimate_act", "affection_touch", "romantic_confession", "stealth_covert",
    "disclosure_inquiry", "epistemic_containment",
})
_CONCEALING_GARMENT_TOKENS: tuple[str, ...] = (
    "mask", "veil", "balaclava", "hood_down", "concealed_face", "visor", "domino",
)
_LAWFUL_TRAITS: tuple[str, ...] = (
    "lawful", "paladin", "disciplinary", "inspector", "monitor", "righteous", "knight", "strict",
)
_ROGUISH_TRAITS: tuple[str, ...] = (
    "rogue", "thief", "smuggler", "cynical", "accomplice", "delinquent", "pragmatic", "loyal",
)


def _norm_key(val: Any) -> str:
    return str(val or "").strip().lower()


def _parse_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            return dict(loaded) if isinstance(loaded, Mapping) else {}
        except Exception:
            return {}
    return {}


def _actor_key(npc: Any) -> str:
    if isinstance(npc, Mapping):
        for field in ("person_key", "npc_id", "npc_key", "holder_actor_key", "name"):
            v = _norm_key(npc.get(field))
            if v:
                return v
        return ""
    return _norm_key(npc)


def _npc_aliases(npc: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for field in ("person_key", "npc_id", "npc_key", "name"):
        v = _norm_key(npc.get(field))
        if v:
            out.add(v)
    return out


def _is_watch_role(npc: Mapping[str, Any]) -> bool:
    basic = _parse_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    blob = " ".join(
        str(x or "").lower()
        for x in (npc.get("role"), npc.get("occupation"), npc.get("faction"), basic.get("role"), basic.get("occupation"))
    )
    return any(tok in blob for tok in _WATCH_ROLE_TOKENS)


def _is_face_concealed(session: Mapping[str, Any], act_payload: Mapping[str, Any]) -> bool:
    if act_payload.get("culprit_masked") or act_payload.get("face_concealed"):
        return True
    for container in (act_payload.get("actor_garments"), session.get("actor_garments")):
        garments = _parse_dict(container)
        player_g = garments.get("player") if isinstance(garments.get("player"), Mapping) else garments
        blob = json.dumps(player_g, default=str).lower() if player_g else ""
        if any(tok in blob for tok in _CONCEALING_GARMENT_TOKENS):
            return True
    return False


def _is_kin_roommate_or_best_friend(
    subject_key: str,
    holder_key: str,
    *,
    social_ties: Sequence[Mapping[str, Any]] = (),
    households: Sequence[Mapping[str, Any]] = (),
    contacts: Sequence[Mapping[str, Any]] = (),
    roster_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    skey = _norm_key(subject_key)
    hkey = _norm_key(holder_key)
    if not skey or not hkey or skey == hkey:
        return False

    # 1. Social ties: best_friend, romantic partners, or explicit kin metadata
    for t in social_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if {pa, pb} != {skey, hkey}:
            continue
        ttype = _norm_key(t.get("tie_type"))
        if ttype in ("best_friend", "married", "engaged", "dating", "sibling", "family", "roommate"):
            return True
        meta_blob = f"{ttype} {t.get('role') or ''} {json.dumps(t.get('metadata') or {}, default=str)}".lower()
        if any(tok in meta_blob for tok in (*_KIN_AND_PARTNER_TOKENS, "best_friend", "best friend", "roommate", "housemate")):
            return True

    # 2. Households (either normalized household dicts with member_keys, or roster rows sharing household_id)
    for hh in households or ():
        members: set[str] = set()
        raw_m = hh.get("members") or hh.get("member_keys") or ()
        for m in raw_m:
            mk = _actor_key(m)
            if mk:
                members.add(mk)
        if skey in members and hkey in members:
            return True

    if roster_map:
        s_row = roster_map.get(skey) or {}
        h_row = roster_map.get(hkey) or {}
        shid = s_row.get("household_id")
        hhid = h_row.get("household_id")
        if shid and hhid and str(shid) == str(hhid):
            return True
        shome = _norm_key(s_row.get("home_node_id"))
        hhome = _norm_key(h_row.get("home_node_id"))
        if shome and hhome and shome == hhome and (shome != "" and not shome.startswith("loc_dorm_public")):
            return True

    # 3. Contacts relationship text fallback
    for c in contacts or ():
        ck = _actor_key(c)
        if ck in (skey, hkey):
            rel_blob = f"{c.get('relationship') or ''} {c.get('kinship') or ''} {c.get('family_role') or ''}".lower()
            if (skey in rel_blob or hkey in rel_blob) and any(
                tok in rel_blob for tok in (*_KIN_AND_PARTNER_TOKENS, "best friend", "roommate")
            ):
                return True

    return False


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
        watch_bonus = 0.2 if _is_watch_role(npc) else 0.0

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
        base_spot = (0.85 if is_present else 0.40) + watch_bonus
        spot_prob = max(0.08, min(0.98, base_spot - 0.28 * focus_mod))
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

    # Surviving witnesses record a higher-severity assault/homicide crime fact
    survivors = [w for w in (present_witnesses or ()) if isinstance(w, Mapping) and _actor_key(w) not in neutralized]
    if sid and neutralized and survivors:
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


def _resolve_npc_schedule_node(row: Mapping[str, Any], bell_slot: str) -> str:
    b = _norm_key(bell_slot)
    if b in ("morning", "afternoon"):
        return str(row.get("workplace_node_id") or row.get("home_node_id") or "").strip()
    if b in ("lunch", "evening"):
        return str(row.get("hangout_node_id") or row.get("workplace_node_id") or "").strip()
    return str(row.get("home_node_id") or "").strip()


def tick_epistemic_boundary_propagation(
    session_id: int,
    session: Mapping[str, Any],
    day: int,
    bell_slot: str,
    roster_map: Mapping[str, Mapping[str, Any]],
    social_ties: Sequence[Mapping[str, Any]],
    households: Sequence[Mapping[str, Any]],
    rng: random.Random | Any,
    turn: int,
    *,
    contacts: Sequence[Mapping[str, Any]] = (),
    conn=None,
) -> dict[str, Any]:
    """
    Runs boundary-tick epistemic simulation:
    - B8 daily rumor heat decay (`-10/day`, `status='decayed'` at 0)
    - B4 1-hop gossip propagation (`player_aware=0`) + 2+ firsthand source corroboration
    - B5 Caught Lying busted-alibi check (double trust loss)
    - B16 kin/roommate/best_friend automatic next-block alert on active uncontained facts
    - B11 Watch-role escalation emissions
    """
    sid = int(session_id or 0)
    cur_day = max(1, int(day or 1))
    t_num = int(turn or 0)
    empty = {
        "propagated": [],
        "corroborated": [],
        "busted_alibis": [],
        "decayed": [],
        "escalations": [],
        "kin_alerts": [],
    }
    if not sid:
        return empty

    matrix = db.preload_epistemic_matrix(sid, conn=conn)
    facts_by_key = matrix["facts_by_key"]
    by_fact = matrix["by_fact"]
    if not facts_by_key:
        return empty

    norm_roster: dict[str, Mapping[str, Any]] = {_norm_key(k): v for k, v in (roster_map or {}).items() if _norm_key(k)}
    propagated: list[dict[str, Any]] = []
    corroborated: list[dict[str, Any]] = []
    busted_alibis: list[dict[str, Any]] = []
    decayed: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    kin_alerts: list[dict[str, Any]] = []

    # Build neighbor map from social_ties + households + same schedule node
    neighbors: dict[str, set[str]] = {}
    for t in social_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if not pa or not pb or pa == "player" or pb == "player":
            continue
        closeness = float(t.get("closeness") or 0.0)
        ttype = _norm_key(t.get("tie_type"))
        if closeness >= 35.0 or ttype in ("friend", "best_friend", "dating", "engaged", "married", "rival"):
            neighbors.setdefault(pa, set()).add(pb)
            neighbors.setdefault(pb, set()).add(pa)

    node_groups: dict[str, list[str]] = {}
    for nk, r in norm_roster.items():
        if _norm_key(r.get("staff_status") or "active") in ("deceased", "wiped", "removed"):
            continue
        node = _resolve_npc_schedule_node(r, bell_slot)
        if node:
            node_groups.setdefault(node, []).append(nk)
    for group in node_groups.values():
        if len(group) >= 2:
            for a in group:
                for b in group:
                    if a != b:
                        neighbors.setdefault(a, set()).add(b)

    for hh in households or ():
        mkeys = [_actor_key(m) for m in (hh.get("members") or hh.get("member_keys") or ()) if _actor_key(m)]
        for a in mkeys:
            for b in mkeys:
                if a != b:
                    neighbors.setdefault(a, set()).add(b)

    # 1. B8 Decay on uncorroborated rumor-only facts
    for fkey, fact in list(facts_by_key.items()):
        if fact.get("status") != "active":
            continue
        last_tick = int(fact.get("decay_day_last_ticked") or cur_day)
        holders = by_fact.get(fkey) or {}
        if cur_day > last_tick:
            has_hard_or_firsthand = any(
                h.get("confidence") in ("firsthand", "hard_proof")
                and h.get("containment_state") not in ("wiped", "incapacitated", "decayed")
                for h in holders.values()
            )
            if not has_hard_or_firsthand:
                elapsed = max(1, cur_day - last_tick)
                old_heat = int(fact.get("heat_score") or 0)
                new_heat = max(0, old_heat - 10 * elapsed)
                new_status = "decayed" if new_heat == 0 else "active"
                db.upsert_epistemic_fact(
                    sid, fkey,
                    heat_score=new_heat,
                    decay_day_last_ticked=cur_day,
                    status=new_status,
                    turn=t_num,
                    conn=conn,
                )
                fact["heat_score"] = new_heat
                fact["status"] = new_status
                if new_status == "decayed":
                    decayed.append({"fact_key": fkey, "heat_score": 0})
            else:
                db.upsert_epistemic_fact(sid, fkey, decay_day_last_ticked=cur_day, turn=t_num, conn=conn)

    # 2. B4 Propagation, Corroboration, B16 Kin Alert, B5 Alibi Bust & B11 Escalation
    for fkey, fact in facts_by_key.items():
        if fact.get("status") != "active":
            continue
        holders = by_fact.get(fkey) or {}
        firsthand_active_holders = [
            hk for hk, h in holders.items()
            if h.get("containment_state") == "active" and h.get("confidence") in ("firsthand", "hard_proof")
        ]
        active_holders = [
            (hk, h) for hk, h in holders.items()
            if h.get("containment_state") == "active"
        ]

        # B16: Alert wronged subject's kin/roommate/best_friend when uncontained high-severity active witness exists
        subject_k = _norm_key(fact.get("subject_actor_key"))
        if subject_k and int(fact.get("severity") or 1) >= 2 and active_holders:
            for cand_k in sorted(norm_roster.keys()):
                if cand_k in holders or cand_k == subject_k:
                    continue
                if _is_kin_roommate_or_best_friend(
                    subject_k,
                    cand_k,
                    social_ties=social_ties,
                    households=households,
                    contacts=contacts,
                    roster_map=norm_roster,
                ):
                    src_k = active_holders[0][0]
                    new_row = db.upsert_epistemic_knowledge(
                        sid, fkey, cand_k,
                        confidence="firsthand",
                        containment_state="active",
                        source_actor_key=src_k,
                        acquisition_channel="kin_alert",
                        hop_count=1,
                        player_aware=0,
                        turn=t_num,
                        conn=conn,
                    )
                    holders[cand_k] = new_row
                    kin_alerts.append({"fact_key": fkey, "holder_actor_key": cand_k, "subject_actor_key": subject_k})

        # B4: 1-hop gossip propagation (player_aware=0) & multi-source corroboration
        new_hops_this_fact = 0
        for src_k, src_row in sorted(active_holders):
            if new_hops_this_fact >= 4:
                break
            src_hop = int(src_row.get("hop_count") or 0)
            src_conf = str(src_row.get("confidence") or "rumor")
            for rec_k in sorted(neighbors.get(src_k, ())):
                if rec_k in norm_roster and _norm_key(norm_roster[rec_k].get("staff_status")) in ("deceased", "wiped"):
                    continue
                rec_existing = holders.get(rec_k)
                if rec_existing:
                    # Track independent firsthand corroboration
                    if src_conf in ("firsthand", "hard_proof") and rec_existing.get("confidence") == "rumor":
                        meta = _parse_dict(rec_existing.get("metadata"))
                        sources = {str(s) for s in (meta.get("corroborating_sources") or ()) if s}
                        if rec_existing.get("source_actor_key"):
                            sources.add(str(rec_existing["source_actor_key"]))
                        sources.add(src_k)
                        if len(sources) >= 2:
                            updated = db.upsert_epistemic_knowledge(
                                sid, fkey, rec_k,
                                confidence="firsthand",
                                metadata={"corroborating_sources": sorted(sources)},
                                turn=t_num,
                                conn=conn,
                            )
                            holders[rec_k] = updated
                            corroborated.append({"fact_key": fkey, "holder_actor_key": rec_k, "sources": sorted(sources)})
                    continue

                if len(firsthand_active_holders) >= 2:
                    prob = 0.75
                else:
                    prob = 0.50 if src_conf in ("firsthand", "hard_proof") else 0.25
                roll = float(rng.random()) if hasattr(rng, "random") else 0.0
                if roll >= prob:
                    continue

                inserted = db.upsert_epistemic_knowledge(
                    sid, fkey, rec_k,
                    confidence="rumor",
                    containment_state="active",
                    source_actor_key=src_k,
                    acquisition_channel="gossip",
                    hop_count=src_hop + 1,
                    player_aware=0,
                    metadata={"corroborating_sources": [src_k]},
                    turn=t_num,
                    conn=conn,
                )
                holders[rec_k] = inserted
                propagated.append({
                    "fact_key": fkey,
                    "holder_actor_key": rec_k,
                    "source_actor_key": src_k,
                    "hop_count": src_hop + 1,
                    "player_aware": 0,
                })
                new_hops_this_fact += 1
                if new_hops_this_fact >= 4:
                    break

        # B5: Caught Lying check across all holders with an unbusted alibi_claim
        for hk, hrow in list(holders.items()):
            if not str(hrow.get("alibi_claim") or "").strip() or int(hrow.get("is_alibi_busted") or 0):
                continue
            wkey = _norm_key(hrow.get("alibi_witness_key"))
            w_prepped = bool(
                wkey
                and holders.get(wkey, {}).get("containment_state") in ("co_conspirator", "hushed")
            )
            meets_witness = bool(wkey and (wkey in neighbors.get(hk, ()) or not norm_roster))
            unprepped_witness_contradicts = bool(wkey and meets_witness and not w_prepped)
            h_meta = _parse_dict(hrow.get("metadata"))
            h_sources = {str(s) for s in (h_meta.get("corroborating_sources") or ()) if s}
            hard_contradiction = (
                hrow.get("confidence") == "hard_proof"
                or len(h_sources) >= 2
                or len([x for x in firsthand_active_holders if x != hk]) >= 2
            )
            if unprepped_witness_contradicts or hard_contradiction:
                db.upsert_epistemic_knowledge(
                    sid, fkey, hk,
                    containment_state="active",
                    is_alibi_busted=1,
                    player_aware=1,
                    turn=t_num,
                    conn=conn,
                )
                db.upsert_epistemic_fact(
                    sid, fkey,
                    heat_score=min(100, int(fact.get("heat_score") or 50) + 20),
                    turn=t_num,
                    conn=conn,
                )
                busted_alibis.append({
                    "fact_key": fkey,
                    "holder_actor_key": hk,
                    "alibi_witness_key": wkey,
                    "trust_delta": -20,
                    "double_penalty": True,
                })

        # B11: Watch-role authority escalation
        if fact.get("category") in ("crime", "faction_breach", "anomaly"):
            for hk, hrow in list(holders.items()):
                if hrow.get("containment_state") != "active":
                    continue
                npc_meta = norm_roster.get(hk) or {}
                if not _is_watch_role(npc_meta):
                    continue
                if hrow.get("confidence") in ("firsthand", "hard_proof") or int(fact.get("heat_score") or 0) >= 60:
                    esc_type = "summons" if int(fact.get("severity") or 1) >= 3 else "faction_rep"
                    escalations.append({
                        "fact_key": fkey,
                        "holder_actor_key": hk,
                        "escalation_type": esc_type,
                        "severity": int(fact.get("severity") or 1),
                    })
                    break

    return {
        "propagated": propagated,
        "corroborated": corroborated,
        "busted_alibis": busted_alibis,
        "decayed": decayed,
        "escalations": escalations,
        "kin_alerts": kin_alerts,
    }


def _extract_present_actor_keys(present_npcs: Sequence[Any]) -> set[str]:
    keys: set[str] = set()
    for item in present_npcs or ():
        if isinstance(item, Mapping):
            keys |= _npc_aliases(item)
        else:
            k = _norm_key(item)
            if k:
                keys.add(k)
    return keys


def _is_proof_ref_held(
    proof_ref: str,
    held_item_ids: Sequence[Any],
    clue_ids: Sequence[Any],
) -> bool:
    pref = str(proof_ref or "").strip()
    if not pref:
        return False
    norm_items = {str(x).strip() for x in (held_item_ids or ()) if str(x or "").strip()}
    norm_clues = {str(x).strip() for x in (clue_ids or ()) if str(x or "").strip()}
    if ":" in pref:
        prefix, ident = pref.split(":", 1)
        prefix = prefix.lower().strip()
        if prefix in ("inv", "photo"):
            return ident in norm_items or pref in norm_items
        if prefix == "clue":
            return ident in norm_clues or pref in norm_clues
        if prefix == "dm":
            return (pref in norm_items) or (pref in norm_clues)
    return (pref in norm_items) or (pref in norm_clues)


def resolve_fenced_epistemic_signal(
    session_id: int,
    raw_signal: Any,
    *,
    present_npcs: Sequence[Any],
    held_item_ids: Sequence[Any] = (),
    clue_ids: Sequence[Any] = (),
    turn: int = 0,
    conn=None,
) -> list[dict[str, Any]]:
    """
    B15: Validates narrator `EpistemicSignal` outputs against present scene NPCs and real held proofs.
    Drops hallucinated actors/proofs and caps commits to <= 3 per turn.
    """
    sid = int(session_id or 0)
    if not sid or not raw_signal:
        return []

    signals = [raw_signal] if isinstance(raw_signal, Mapping) else (list(raw_signal) if isinstance(raw_signal, (list, tuple)) else [])
    present_keys = _extract_present_actor_keys(present_npcs)
    committed: list[dict[str, Any]] = []
    t_num = int(turn or 0)

    for sig in signals[:3]:
        if isinstance(sig, Mapping):
            sig_d = dict(sig)
        elif hasattr(sig, "model_dump"):
            sig_d = sig.model_dump()
        else:
            continue

        target_npc = _norm_key(sig_d.get("target_npc"))
        if target_npc and target_npc not in present_keys:
            continue
        if not target_npc and present_keys:
            continue

        raw_proof = str(sig_d.get("proof_ref") or "").strip()
        verified_proof = raw_proof if _is_proof_ref_held(raw_proof, held_item_ids, clue_ids) else ""
        conf = _norm_key(sig_d.get("confidence")) or "rumor"
        if conf == "hard_proof" and not verified_proof:
            conf = "rumor"
        if conf not in ("rumor", "firsthand", "hard_proof"):
            conf = "rumor"

        kind = _norm_key(sig_d.get("kind")) or "secret_revealed"
        fkey = str(sig_d.get("fact_key") or f"sig_{kind}_{target_npc}_{t_num}").strip()
        summary = str(sig_d.get("summary") or f"{kind} involving {target_npc}").strip()[:220]
        cat = str(sig_d.get("category") or "secret").strip().lower()

        db.upsert_epistemic_fact(
            sid,
            fkey,
            category=cat if cat in db.ALLOWED_FACT_CATEGORIES else "secret",
            culprit_actor_key="player",
            summary=summary,
            proof_artifact_ref=verified_proof,
            status="active",
            turn=t_num,
            conn=conn,
        )
        if target_npc:
            db.upsert_epistemic_knowledge(
                sid,
                fkey,
                target_npc,
                confidence=conf,
                containment_state="active",
                source_actor_key="player",
                acquisition_channel=kind,
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
        committed.append({
            "fact_key": fkey,
            "target_npc": target_npc,
            "confidence": conf,
            "proof_ref": verified_proof,
            "kind": kind,
        })

    return committed
