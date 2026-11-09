"""
mechanics/social/folklore_roster_rollback.py
============================================
Turn-rollback reconciliation and staged live-turn `UnitOfWork` commit helpers for
veiled folklore villager hydrations, Kitsune form shifts, Spirit-Relay friendships,
and daytime glamour Permission Tokens.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
from typing import Any, Dict, Optional

import db
from mechanics.world.locations.folklore_veil import load_folklore_villages_catalog

from .folklore_roster import _slugify_id, ensure_folklore_villager_roster


def rollback_folklore_roster_state_after_turn(
    session_id: int,
    turn_number: int,
    conn: Any = None,
) -> Dict[str, int]:
    """
    Reconciles folklore villager hydrations, Kitsune form shifts (including 6-slot garments),
    Spirit-Relay friendships, and free glamour Permission Tokens created strictly after `turn_number`.
    """
    from .folklore_roster_lifecycle import _sync_villager_physical_garments

    if not session_id:
        return {
            "hydrations_reverted": 0,
            "forms_reverted": 0,
            "tokens_reverted": 0,
            "companions_pruned": 0,
        }
    t_num = int(turn_number)
    hydrations_reverted = 0
    forms_reverted = 0
    tokens_reverted = 0
    companions_pruned = 0
    catalog = load_folklore_villages_catalog()
    kits = catalog.get("combat_kits") or {}

    ctx = nullcontext(conn) if conn is not None else db.get_conn()
    with ctx as c:
        s_row = c.execute(
            "SELECT extra_json, party_npcs_json FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchone()
        if not s_row or not s_row["extra_json"]:
            return {
                "hydrations_reverted": 0,
                "forms_reverted": 0,
                "tokens_reverted": 0,
                "companions_pruned": 0,
            }
        try:
            ex = json.loads(s_row["extra_json"] or "{}")
        except Exception:
            ex = {}
        if not isinstance(ex, dict):
            return {
                "hydrations_reverted": 0,
                "forms_reverted": 0,
                "tokens_reverted": 0,
                "companions_pruned": 0,
            }

        dirty = False
        gifted_map = dict(ex.get("folklore_free_tokens_granted") or {})
        for v_key, grant_val in list(gifted_map.items()):
            g_turn = int(grant_val.get("turn") or 0) if isinstance(grant_val, dict) else 0
            if g_turn > t_num:
                tok_nm = str(
                    grant_val.get("token_name")
                    or ((catalog.get("villages") or {}).get(v_key) or {}).get("permission_token_name")
                    or ""
                )
                uid_hint = int(grant_val.get("user_id") or 0) if isinstance(grant_val, dict) else 0
                if tok_nm:
                    inv_row = c.execute(
                        """SELECT id FROM inventory
                           WHERE lower(name) = ? AND is_quest_locked = 1
                             AND (
                                 (? > 0 AND user_id = ?)
                                 OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?)
                                 OR character_id IN (SELECT id FROM characters WHERE active_session_id = ?)
                             )
                           ORDER BY id DESC LIMIT 1""",
                        (tok_nm.lower(), uid_hint, uid_hint, int(session_id), int(session_id)),
                    ).fetchone()
                    if inv_row:
                        c.execute("DELETE FROM inventory WHERE id = ?", (inv_row["id"],))
                gifted_map.pop(v_key, None)
                tokens_reverted += 1
                dirty = True
        if dirty:
            ex["folklore_free_tokens_granted"] = gifted_map

        roster = ex.get("folklore_villager_roster")
        if isinstance(roster, list):
            for entry in roster:
                if not isinstance(entry, dict):
                    continue
                npc_id = str(entry.get("npc_id") or "")
                name = str(entry.get("name") or "")
                canon_key = _slugify_id(name)
                hyd_t = int(entry.get("hydrated_turn") or 0)

                if hyd_t > t_num and entry.get("hydrated"):
                    c.execute(
                        "DELETE FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
                        (int(session_id), npc_id, name.lower()),
                    )
                    c.execute(
                        "DELETE FROM lorebook WHERE session_id = ? AND lower(name) = ?",
                        (int(session_id), name.lower()),
                    )
                    c.execute(
                        "DELETE FROM actor_garments WHERE session_id = ? AND actor_key = ?",
                        (int(session_id), canon_key),
                    )
                    c.execute(
                        "DELETE FROM actor_physical_states WHERE session_id = ? AND canonical_key = ?",
                        (int(session_id), canon_key),
                    )
                    c.execute(
                        "DELETE FROM social_ties WHERE session_id = ? AND (person_a_key = ? OR person_b_key = ?)",
                        (int(session_id), canon_key, canon_key),
                    )
                    c.execute(
                        "DELETE FROM social_persons WHERE session_id = ? AND (person_key = ? OR contact_npc_id = ?)",
                        (int(session_id), canon_key, npc_id),
                    )
                    entry["hydrated"] = False
                    entry.pop("hydrated_turn", None)
                    entry["befriended"] = False
                    entry.pop("befriended_turn", None)
                    entry.pop("form_history", None)
                    entry.pop("bond_humanoid_unlocked", None)
                    entry.pop("bond_unlocked_turn", None)
                    init_f = str(entry.get("initial_form") or entry.get("race") or "")
                    if init_f:
                        entry["race"] = init_f
                    hydrations_reverted += 1
                    dirty = True
                    continue

                if int(entry.get("befriended_turn") or 0) > t_num and entry.get("befriended"):
                    entry["befriended"] = False
                    entry.pop("befriended_turn", None)
                    ct_r = c.execute(
                        "SELECT id, basic_info_json FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
                        (int(session_id), npc_id, name.lower()),
                    ).fetchone()
                    if ct_r:
                        try:
                            bi = json.loads(ct_r["basic_info_json"] or "{}")
                        except Exception:
                            bi = {}
                        bi["contact_added"] = False
                        bi["is_contact"] = False
                        bi["unlocked_via_friendship"] = False
                        bi["spirit_relay_unlocked"] = False
                        c.execute(
                            "UPDATE contacts SET basic_info_json = ? WHERE id = ?",
                            (json.dumps(bi), ct_r["id"]),
                        )
                    dirty = True

                hist = list(entry.get("form_history") or [])
                after_shifts = [h for h in hist if isinstance(h, dict) and int(h.get("turn") or 0) > t_num]
                if after_shifts:
                    revert_form = str(after_shifts[0].get("prev_form") or entry.get("initial_form") or entry.get("race") or "")
                    kept_hist = [h for h in hist if isinstance(h, dict) and int(h.get("turn") or 0) <= t_num]
                    entry["form_history"] = kept_hist
                    if int(entry.get("bond_unlocked_turn") or 0) > t_num:
                        entry.pop("bond_humanoid_unlocked", None)
                        entry.pop("bond_unlocked_turn", None)
                    if revert_form in ("kitsune:humanoid", "kitsune:myobu_fox"):
                        h_kit = str(entry.get("humanoid_kit_key") or "kitsune_mystic")
                        r_kit = "kitsune_myobu_beast" if revert_form == "kitsune:myobu_fox" else h_kit
                        r_abils = list(kits.get(r_kit) or [])
                        app = dict(entry.get("appearance") or {})
                        h_outfit = str(app.get("humanoid_outfit") or "Vermilion-and-ivory Inari shrine kimono")
                        app["kitsune_form"] = revert_form
                        app["coat_color"] = str(app.get("fur_coat") or "") if revert_form == "kitsune:myobu_fox" else ""
                        app["outfit_style"] = "" if revert_form == "kitsune:myobu_fox" else h_outfit
                        app["outfit_summary"] = (
                            "Unclothed sacred spirit-fox coat wreathed in kitsunebi wisps"
                            if revert_form == "kitsune:myobu_fox"
                            else h_outfit
                        )
                        entry["race"] = revert_form
                        entry["combat_kit_key"] = r_kit
                        entry["innate_abilities"] = r_abils
                        entry["appearance"] = app
                        ct_r = c.execute(
                            "SELECT id, basic_info_json, track FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
                            (int(session_id), npc_id, name.lower()),
                        ).fetchone()
                        if ct_r:
                            try:
                                bi = json.loads(ct_r["basic_info_json"] or "{}")
                            except Exception:
                                bi = {}
                            bi["race"] = revert_form
                            bi["combat_kit_key"] = r_kit
                            bi["innate_abilities"] = r_abils
                            r_track = "platonic" if revert_form == "kitsune:myobu_fox" else str(ct_r["track"] or "platonic")
                            c.execute(
                                "UPDATE contacts SET race = ?, track = ?, basic_info_json = ?, appearance_json = ? WHERE id = ?",
                                (revert_form, r_track, json.dumps(bi), json.dumps(app), ct_r["id"]),
                            )
                        c.execute(
                            "UPDATE lorebook SET race = ?, appearance_json = ? WHERE session_id = ? AND lower(name) = ?",
                            (revert_form, json.dumps(app), int(session_id), name.lower()),
                        )
                        _sync_villager_physical_garments(c, int(session_id), name, revert_form, h_outfit)
                        forms_reverted += 1
                        dirty = True
                elif entry.get("hydrated") and str(entry.get("folklore_village") or "") == "kitsune":
                    cur_form = str(entry.get("race") or "kitsune:humanoid")
                    h_outfit = str((entry.get("appearance") or {}).get("humanoid_outfit") or "Vermilion-and-ivory Inari shrine kimono")
                    _sync_villager_physical_garments(c, int(session_id), name, cur_form, h_outfit)

            if dirty:
                ex["folklore_villager_roster"] = roster

            # Reconcile sessions.party_npcs_json for any reverted hydrations, late recruitments, or Kitsune form reverts
            try:
                raw_p_npcs = json.loads(s_row["party_npcs_json"] or "[]")
            except Exception:
                raw_p_npcs = []
            if isinstance(raw_p_npcs, list) and raw_p_npcs:
                from .folklore_roster_lifecycle import _build_folklore_weapon_profile
                from .folklore_roster import is_myobu_fox_race

                roster_by_key: Dict[str, Dict[str, Any]] = {}
                for r_ent in roster:
                    if isinstance(r_ent, dict):
                        if r_ent.get("npc_id"):
                            roster_by_key[str(r_ent["npc_id"]).strip().lower()] = r_ent
                        if r_ent.get("name"):
                            roster_by_key[str(r_ent["name"]).strip().lower()] = r_ent

                kept_p_npcs = []
                p_dirty = False
                for p_ent in raw_p_npcs:
                    if not isinstance(p_ent, dict):
                        kept_p_npcs.append(p_ent)
                        continue
                    p_nm = str(p_ent.get("name") or "").strip().lower()
                    p_id = str(p_ent.get("npc_id") or "").strip().lower()
                    r_match = roster_by_key.get(p_id) or roster_by_key.get(p_nm)
                    is_fk_comp = bool(
                        r_match
                        or p_ent.get("is_folklore_villager")
                        or p_ent.get("anomalous_npc_tag") == "folklore_villager"
                    )
                    if not is_fk_comp:
                        kept_p_npcs.append(p_ent)
                        continue
                    rec_t = int(p_ent.get("recruited_turn") or 0)
                    if rec_t > t_num or (r_match and not r_match.get("hydrated")):
                        companions_pruned += 1
                        p_dirty = True
                        continue
                    if r_match:
                        ct_chk = c.execute(
                            "SELECT relationship_score, basic_info_json FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
                            (int(session_id), str(r_match.get("npc_id") or ""), str(r_match.get("name") or "").lower()),
                        ).fetchone()
                        if not ct_chk:
                            companions_pruned += 1
                            p_dirty = True
                            continue
                        try:
                            chk_bi = json.loads(ct_chk["basic_info_json"] or "{}")
                        except Exception:
                            chk_bi = {}
                        if int(ct_chk["relationship_score"] or 0) < 20 and not chk_bi.get("contact_added"):
                            companions_pruned += 1
                            p_dirty = True
                            continue
                        r_form = str(r_match.get("race") or p_ent.get("race") or "")
                        if r_form and r_form != str(p_ent.get("race") or ""):
                            r_abils = list(r_match.get("innate_abilities") or p_ent.get("innate_abilities") or [])
                            r_tier = int(r_match.get("agent_tier") or p_ent.get("agent_tier") or 3)
                            r_vk = str(r_match.get("folklore_village") or p_ent.get("folklore_village") or "kitsune")
                            p_ent["race"] = r_form
                            p_ent["is_beast_companion"] = is_myobu_fox_race(r_form)
                            p_ent["innate_abilities"] = r_abils
                            p_ent["spells"] = r_abils
                            p_ent["weapon_profile"] = _build_folklore_weapon_profile(r_form, r_vk, r_tier)
                            p_dirty = True
                    kept_p_npcs.append(p_ent)
                if p_dirty:
                    c.execute(
                        "UPDATE sessions SET party_npcs_json = ? WHERE id = ?",
                        (json.dumps(kept_p_npcs, default=str), int(session_id)),
                    )

        if dirty:
            c.execute(
                "UPDATE sessions SET extra_json = ? WHERE id = ?",
                (json.dumps(ex, default=str), int(session_id)),
            )

    return {
        "hydrations_reverted": hydrations_reverted,
        "forms_reverted": forms_reverted,
        "tokens_reverted": tokens_reverted,
        "companions_pruned": companions_pruned,
    }


def commit_staged_folklore_ops(
    session_id: int,
    pending_ops: Optional[Dict[str, Any]],
    session: Optional[Dict[str, Any]] = None,
    turn_number: int = 0,
    advance_clock_on_expel: bool = True,
) -> Dict[str, Any]:
    """
    Atomically commits folklore operations staged during `compute_pre_turn_stage(..., persist_db=False)`
    once `game_engine.apply_outcome` enters its `UnitOfWork` commit phase.
    """
    if isinstance(session, dict):
        session.pop("_staged_attuned_villages", None)
    if not session_id or not isinstance(pending_ops, dict) or not pending_ops:
        return {}
    from mechanics.world.locations.folklore_veil import (
        apply_sanctuary_treaty_violation,
        attune_folklore_village,
        unlock_leyline_spirit_passage,
    )
    from .folklore_roster_lifecycle import (
        hydrate_village_cast_for_node,
        resolve_glamour_wanderer_interaction,
    )

    eff_turn = int(turn_number or (session or {}).get("_target_turn") or db.get_effective_session_turn(session_id))
    committed: Dict[str, Any] = {}
    with db.UnitOfWork():
        if pending_ops.get("ensure_roster"):
            ensure_folklore_villager_roster(session_id, session=session, persist_db=True)
            committed["roster_ensured"] = True

        viol_vk = str(pending_ops.get("treaty_violation_village") or "").strip()
        if viol_vk:
            exp_res = apply_sanctuary_treaty_violation(
                session_id,
                viol_vk,
                turn_number=eff_turn,
                session=session,
                advance_clock=advance_clock_on_expel,
            )
            committed["treaty_violation"] = exp_res
            return committed

        atone_spec = pending_ops.get("atonement_payment")
        if isinstance(atone_spec, dict) and not pending_ops.get("is_retry"):
            atone_uid = int(atone_spec.get("user_id") or 0)
            atone_cost = int(atone_spec.get("cost") or 0)
            if atone_uid > 0 and atone_cost > 0 and db.get_character(atone_uid):
                db.apply_hp_mp_delta(atone_uid, gold_delta=-atone_cost)
                committed["atonement_gold_paid"] = atone_cost

        att_spec = pending_ops.get("attune_village")
        if isinstance(att_spec, dict) and att_spec.get("village_key"):
            committed["village_attuned"] = attune_folklore_village(
                session_id,
                str(att_spec["village_key"]),
                turn_number=eff_turn,
                reason=str(att_spec.get("reason") or "veil_attunement"),
            )

        ley_reason = str(pending_ops.get("unlock_leyline_reason") or "").strip()
        if ley_reason:
            committed["leyline"] = unlock_leyline_spirit_passage(session_id, turn_number=eff_turn, reason=ley_reason)

        hyd_spec = pending_ops.get("hydrate_node")
        if isinstance(hyd_spec, dict) and hyd_spec.get("node_id"):
            committed["hydrated_count"] = len(
                hydrate_village_cast_for_node(
                    session_id,
                    str(hyd_spec["node_id"]),
                    current_minute=int(hyd_spec.get("current_minute", 480) or 480),
                    turn_number=eff_turn,
                )
            )

        glam_spec = pending_ops.get("glamour_grant")
        if isinstance(glam_spec, dict) and glam_spec.get("node_id"):
            committed["glamour"] = resolve_glamour_wanderer_interaction(
                session_id,
                str(glam_spec["node_id"]),
                current_minute=int(glam_spec.get("current_minute", 600) or 600),
                per_passed=bool(glam_spec.get("per_passed")),
                favor_completed=bool(glam_spec.get("favor_completed")),
                user_id=int(glam_spec.get("user_id") or 0),
                persist_db=True,
                turn_number=eff_turn,
            )

    return committed
