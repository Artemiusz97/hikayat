"""Quest reward claims, anomalous faction payouts/vault logs, strike counters, and contract failures."""
from __future__ import annotations

import re
import time

import db
import scenario_data
from ..core import UnitOfWork, get_conn
from ..dossiers import (
    append_dossier_state_event,
    get_effective_session_turn,
    get_quest_dossier,
)
from .core import get_quest_by_id


def claim_quest_reward(session_id: int, quest_id: str, party_user_ids: list[int]) -> dict:
    with UnitOfWork() as conn:
        quest = get_quest_by_id(session_id, quest_id)
        if not quest or quest.get("reward_claimed"):
            return {"already_claimed": True}

        claim_cur = conn.execute(
            "UPDATE quests SET reward_claimed=1, status='Completed', updated_at=? WHERE session_id=? AND quest_id=? AND COALESCE(reward_claimed, 0) = 0",
            (time.time(), session_id, quest_id),
        )
        if claim_cur.rowcount == 0:
            return {"already_claimed": True}

        try:
            from game_engine.quests import consume_quest_delivery_item_if_needed

            consume_quest_delivery_item_if_needed(session_id, quest, party_user_ids)
        except Exception:
            pass

        rxp = quest.get("reward_xp", 100)
        rgold = quest.get("reward_gold", 25)
        ritem = quest.get("reward_item") or ""
        notes = str(quest.get("quest_notes") or "")
        is_story_q = bool(
            quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest")
        )

        anom_promotion_result = None
        anom_reward_note = ""
        scen_key = "fantasy"
        sess_row = db.get_session(session_id) or {}
        try:
            scen_key = str(sess_row.get("scenario") or "fantasy")
            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                from mechanics.narrative.bounty import parse_anomalous_quest_board_source
                from mechanics.social.factions import (
                    faction_bonus_active,
                    get_anomalous_faction_state,
                    update_agent_promotion_reputation,
                )
                from mechanics.world.anomalous_events import (
                    extract_non_hostile_entity_name,
                    record_contained_anomaly_to_vault_log,
                )

                lead_uid = party_user_ids[0] if party_user_ids else sess_row.get("host_user_id")
                fac_st = get_anomalous_faction_state(session_id, user_id=lead_uid)
                player_arch = str(fac_st.get("faction_archetype_key") or "public_agency")
                board_src = parse_anomalous_quest_board_source(quest, session_id=session_id)
                is_mandatory = ("mandatory_daily:1" in notes) or str(
                    quest_id or ""
                ).upper().startswith("MAND-")

                if player_arch == "public_agency" and (
                    board_src == "public_agency" or is_story_q or is_mandatory
                ):
                    rgold = 0
                    ritem = ""
                    anom_reward_note = (
                        "Taxpayer Mandate: 0G / 0 Loot (salaried Public Agency duty)."
                    )
                elif player_arch == "monastic_order" and (
                    board_src == "monastic_order" or is_mandatory
                ):
                    rgold = 0
                    anom_reward_note = (
                        "Sacred Shrine Duty: 0G bounty fee (recovered relics/spoils retained)."
                    )
                elif (
                    player_arch == "clandestine_faction"
                    and board_src == "clandestine_faction"
                    and rgold > 0
                ):
                    if faction_bonus_active("clandestine_faction", fac_st):
                        rgold = max(1, int(round(rgold * 1.35)))
                        anom_reward_note = (
                            "Black-Ledger Cut: +35% Hazard Gold bonus applied (loot & relics retained)."
                        )
                    else:
                        anom_reward_note = (
                            "Black-Ledger Bonus Suspended (0 Rep — complete Mandatory Dispatch to restore +35% Hazard Gold)."
                        )

                if player_arch != "freelancer":
                    earns_promo_rep = is_mandatory or (board_src == player_arch) or is_story_q
                    if earns_promo_rep:
                        rep_delta = 15 if (is_mandatory or is_story_q) else 10
                        anom_promotion_result = update_agent_promotion_reputation(
                            session_id=session_id,
                            delta_rep=rep_delta,
                            reason=f"Completed '{quest.get('title', 'Mission')}'",
                            is_mandatory_completion=is_mandatory,
                            user_id=lead_uid,
                        )

                q_type_low = str(quest.get("quest_type") or "").lower()
                res_app_low = str(quest.get("resolution_approach") or "").lower()
                if res_app_low != "dire_cost" and any(
                    k in q_type_low
                    for k in (
                        "non-hostile",
                        "non_hostile",
                        "shepherd hunted entity",
                        "poach live specimen",
                        "resonance core",
                        "altered item",
                        "cursed relic",
                        "relic_retrieval",
                    )
                ):
                    is_nh_type = "non-hostile" in q_type_low or "non_hostile" in q_type_low
                    ent_disp = (
                        extract_non_hostile_entity_name(quest)
                        if is_nh_type
                        else str(
                            quest.get("required_item")
                            or quest.get("title")
                            or "Anomalous Specimen"
                        )
                    )
                    record_contained_anomaly_to_vault_log(
                        session_id=session_id,
                        entity_name=ent_disp,
                        category_tag="cursed_relic"
                        if ("relic" in q_type_low or "item" in q_type_low)
                        else "spatial_warp",
                        subtype="non_hostile_entity"
                        if is_nh_type
                        else "environmental_phenomenon",
                        location=str(
                            quest.get("client_location")
                            or sess_row.get("current_location")
                            or "Metropolitan Grid"
                        ),
                        containment_note=f"Secured and logged upon completion of '{quest.get('title', 'Containment Operation')}'.",
                        resolution_method="Bounty Containment Protocol",
                        user_id=lead_uid,
                        quest_id=str(quest_id or ""),
                    )
        except Exception:
            pass

        levels_gained_by_user = {}
        for uid in party_user_ids:
            lvl_ups = db.add_xp(uid, rxp)
            if lvl_ups:
                levels_gained_by_user[uid] = lvl_ups

            db.apply_hp_mp_delta(uid, 0, 0, rgold)

            if ritem:
                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    try:
                        from mechanics.combat.items.consumables.generators import (
                            generate_procedural_potion,
                        )

                        r_lower = str(ritem).lower()
                        eff_tags = (
                            ["mana_restore"]
                            if any(
                                w in r_lower
                                for w in ("stabilizer", "incense", "ampoule", "focus", "spirit")
                            )
                            else ["healing"]
                        )
                        pot = generate_procedural_potion(
                            tier=2, effect_tags=eff_tags, genre="anomalous_incursions"
                        )
                        db.add_item(
                            uid,
                            ritem,
                            pot.get("item_type", "Potion"),
                            pot.get("effect", "Restores HP"),
                            1,
                        )
                    except Exception:
                        db.add_item(uid, ritem, "Potion", "Restores 35 HP", 1)
                else:
                    db.add_item(uid, ritem, "Quest", "Quest Reward", 1)

        client_affinity_gain = 0
        client_npc = quest.get("client_npc") or ""
        notes = str(quest.get("quest_notes") or "")
        if client_npc:
            client_affinity_gain = (
                8 if (quest_id.startswith("COMM-") or "commission:1" in notes) else 5
            )
            try:
                db.update_relationship_score(
                    session_id, client_npc, delta_score=client_affinity_gain
                )
            except Exception:
                pass

        faction_rep_gained = 0
        rival_rep_deltas = {}
        if "faction:" in notes or "rival_faction:" in notes:
            try:
                parts = [p.strip() for p in re.split(r"[|\n]+", notes) if p.strip()]
                faction_id = ""
                riv_ids = []
                for p in parts:
                    if p.startswith("faction:"):
                        faction_id = p.split(":", 1)[1].strip()
                    elif p.startswith("rep_reward:"):
                        faction_rep_gained = int(p.split(":", 1)[1].strip())
                    elif p.startswith("rival_faction:"):
                        r_val = p.split(":", 1)[1].strip()
                        if r_val and r_val not in riv_ids:
                            riv_ids.append(r_val)
                if faction_id:
                    if faction_rep_gained <= 0:
                        faction_rep_gained = 10
                    db.upsert_faction(
                        session_id,
                        faction_id,
                        delta_score=faction_rep_gained,
                        notes="Faction bounty completed",
                    )
                    try:
                        s_fac = db.get_faction(session_id, faction_id)
                        if s_fac and s_fac.get("rival_faction_ids"):
                            for r in s_fac["rival_faction_ids"]:
                                if r and str(r).strip() not in riv_ids:
                                    riv_ids.append(str(r).strip())
                    except Exception:
                        pass

                for rid in riv_ids:
                    if rid and rid != faction_id:
                        try:
                            db.upsert_faction(
                                session_id,
                                rid,
                                delta_score=-5,
                                notes=f"Rival operation '{quest.get('title')}' completed",
                            )
                            rival_rep_deltas[rid] = -5
                        except Exception:
                            pass
            except Exception:
                pass

        dos_cl = get_quest_dossier(session_id, quest_id)
        if dos_cl:
            try:
                eff_turn_cl = int(db.infer_session_turn(sess_row))
                prev_status_cl = str(quest.get("status") or "Active")
                prev_tier_cl = str(dos_cl.get("outcome_tier") or "")
                eff_tier_cl = prev_tier_cl or "clean_success"
                if prev_status_cl != "Completed":
                    db.append_dossier_state_event(
                        session_id, quest_id, eff_turn_cl, "quest_status", prev_status_cl, "Completed"
                    )
                if not prev_tier_cl:
                    db.append_dossier_state_event(
                        session_id, quest_id, eff_turn_cl, "outcome_tier", prev_tier_cl, eff_tier_cl
                    )
                db.upsert_quest_dossier(
                    session_id, quest_id, engaged_flag=1, outcome_tier=eff_tier_cl
                )
            except Exception:
                pass

    return {
        "claimed": True,
        "title": quest["title"],
        "quest_type": quest["quest_type"],
        "is_story_quest": bool(
            quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest")
        ),
        "xp": rxp,
        "gold": rgold,
        "item": ritem,
        "levels_gained": levels_gained_by_user,
        "_item_granted_in_db": bool(ritem),
        "client_affinity_gained": client_affinity_gain,
        "faction_rep_gained": faction_rep_gained,
        "rival_rep_deltas": rival_rep_deltas,
        "anomalous_promotion": anom_promotion_result,
        "anomalous_reward_note": anom_reward_note,
    }


def increment_quest_strikes(session_id: int, quest_id: str, delta: int = 1) -> dict:
    """Atomically increments strikes on a quest up to max_strikes (default 2)."""
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strikes, max_strikes, progress, title FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        if not row:
            return {"strikes": 0, "max_strikes": 2, "failed": False, "quest": None}

        curr_strikes = int(row["strikes"] or 0)
        max_s = int(row["max_strikes"] or 2)
        new_strikes = min(max_s, curr_strikes + max(1, delta))
        failed = new_strikes >= max_s

        prog = str(row["progress"] or "")
        if not failed:
            alert_tag = f"[⚠️ {new_strikes}/{max_s} Strikes: Target Alerted]"
            if "[⚠️" in prog:
                prog = re.sub(r"\[⚠️ \d+/\d+ Strikes: Target Alerted\]", alert_tag, prog)
            else:
                prog = f"{prog} {alert_tag}".strip()

        conn.execute(
            "UPDATE quests SET strikes=?, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (new_strikes, prog, now, session_id, quest_id),
        )
        try:
            eff_turn_s = int(get_effective_session_turn(session_id, conn=conn) or 0)
            append_dossier_state_event(
                session_id,
                quest_id,
                eff_turn_s,
                "quest_strikes",
                curr_strikes,
                new_strikes,
                conn=conn,
            )
        except Exception:
            pass

    updated_q = get_quest_by_id(session_id, quest_id)
    return {
        "strikes": new_strikes,
        "max_strikes": max_s,
        "failed": failed,
        "quest": updated_q,
    }


def reset_quest_strikes(session_id: int, quest_id: str) -> None:
    """Resets strikes to 0 for a quest (used on story quest fail-forward)."""
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strikes, progress FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        prev_strikes = int((row["strikes"] if row and "strikes" in row.keys() else 0) or 0)
        clean_prog = ""
        if row and row["progress"]:
            clean_prog = re.sub(
                r"\s*\[⚠️ \d+/\d+ Strikes: Target Alerted\]", "", str(row["progress"])
            ).strip()
        conn.execute(
            "UPDATE quests SET strikes=0, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (clean_prog, now, session_id, quest_id),
        )
        try:
            eff_turn_rs = int(get_effective_session_turn(session_id, conn=conn) or 0)
            append_dossier_state_event(
                session_id, quest_id, eff_turn_rs, "quest_strikes", prev_strikes, 0, conn=conn
            )
        except Exception:
            pass


def set_quest_resolution_approach(
    session_id: int, quest_id: str, resolution_approach: str
) -> dict | None:
    """Updates the resolution_approach on a quest."""
    now = time.time()
    new_app = str(resolution_approach or "")
    with get_conn() as conn:
        prev_row = conn.execute(
            "SELECT resolution_approach FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        prev_app = str(
            (prev_row["resolution_approach"] if prev_row and prev_row["resolution_approach"] else "")
            or ""
        )
        conn.execute(
            "UPDATE quests SET resolution_approach=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (new_app, now, session_id, quest_id),
        )
        try:
            eff_turn_ra = int(get_effective_session_turn(session_id, conn=conn) or 0)
            append_dossier_state_event(
                session_id,
                quest_id,
                eff_turn_ra,
                "resolution_approach",
                prev_app,
                new_app,
                conn=conn,
            )
        except Exception:
            pass
    return get_quest_by_id(session_id, quest_id)


def fail_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    resolution_approach: str = "failed_strikes",
    progress_note: str = "Failed",
) -> dict | None:
    """Deterministically marks a quest as 'Failed' and sets all non-completed waypoints to 'failed'."""
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """UPDATE quests
               SET status='Failed', resolution_approach=?, progress=?, updated_at=?
               WHERE session_id=? AND quest_id=?""",
            (
                str(resolution_approach or "failed_strikes"),
                str(progress_note or "Failed"),
                now,
                session_id,
                quest_id,
            ),
        )
        conn.execute(
            """UPDATE quest_waypoints
               SET status='failed', updated_at=?
               WHERE session_id=? AND quest_id=? AND status IN ('active', 'locked')""",
            (now, session_id, quest_id),
        )
    return get_quest_by_id(session_id, quest_id)


def expire_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    progress_note: str = "Failed (Contract Expired — Claimed by Rival)",
) -> dict | None:
    """Marks a timed quest as Failed due to deadline expiration (`expired_deadline`)."""
    return fail_quest_and_waypoints(
        session_id=session_id,
        quest_id=quest_id,
        resolution_approach="expired_deadline",
        progress_note=progress_note,
    )
