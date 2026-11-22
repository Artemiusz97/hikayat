from __future__ import annotations

import json
import random
from typing import Any, Iterable, Mapping

import db
from mechanics.combat.items import generate_random_equipment
from mechanics.combat.items.anomalous_gear import apply_anomalous_incursions_gear_rules
from mechanics.world.anomalous_sites.catalog import (
    PACIFIABLE_WILD_SITE_IDS,
    get_anomalous_site_spec,
    get_site_state_dict,
    mutate_anomalous_site_state,
    parse_node_state,
    resolve_anomalous_site,
)
from mechanics.world.anomalous_sites.domain_rules import get_resonator_charges_status
from mechanics.world.anomaly_engine import (
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
)
from skill_check import is_check_success

ELIGIBLE_RELIC_SPELL_SLOTS: tuple[str, ...] = ("Weapon", "Accessory 1")
STANDARD_SITE_GEAR_SLOTS: tuple[str, ...] = ("Weapon", "Armor", "Shield", "Accessory 1")

_ELEMENT_WARD_REWARDS: dict[str, tuple[str, str]] = {
    "bio": ("Purging Salt", "Cleansing ward packet that counters bio-miasma hazards and site traps."),
    "earth": ("Purging Salt", "Mineral ward crystal calibrated against lithic tremors."),
    "water": ("Warding Charm", "Moisture-sealed paper charm countering drowning brine hazards."),
    "fire": ("Warding Charm", "Cinnabar-inked ward talisman deflecting ember curses."),
    "wind": ("Lantern Talisman", "Storm-anchored talisman steadying vertigo shears."),
    "ice": ("Stabilization Flare", "Thermite-grade flare dispersing sub-zero spatial drift."),
    "electric": ("Signal Flare", "Grounded magnesium flare disrupting cognitohazard interference."),
    "physical": ("Warding Charm", "Reinforced protective charm deflecting phantom kinetic hazards."),
    "aether": ("Anchor Flare", "Spatial resonance flare locking corridor geometry true."),
}


def _grant_guaranteed_site_gear(
    user_id: int,
    spec: Mapping[str, Any],
    scen_key: str,
    *,
    force_relic_spell: bool = False,
    force_tier: int | None = None,
    custom_name: str | None = None,
    seed_suffix: str = "pacify",
) -> dict[str, Any] | None:
    """
    Generate and grant a site-element `[Anomalous]` equipment piece.
    Grade V & special Relic rewards strictly use eligible spell-grant slots
    (`Weapon`, `Armor`, `Shield`, `Accessory 1`) and enforce `force_granted_spell=True`.
    """
    if not user_id:
        return None
    grade = int(spec.get("threat_grade") or 1)
    site_elem = str(spec.get("element") or "aether").lower()
    if force_tier is not None:
        tier = int(force_tier)
    elif grade >= 5:
        tier = 1
    elif grade == 4 and random.random() < 0.40:
        tier = 1
    else:
        tier = 2

    grant_spell = bool(force_relic_spell or grade >= 5)
    rng = random.Random(f"site_gear:{spec.get('site_id')}:{seed_suffix}:{grade}")
    if custom_name:
        slot = "Accessory 1"
    elif grant_spell:
        slot = rng.choice(ELIGIBLE_RELIC_SPELL_SLOTS)
    else:
        slot = rng.choice(STANDARD_SITE_GEAR_SLOTS)

    base_item = generate_random_equipment(
        scenario=scen_key or "anomalous_incursions",
        slot=slot,
        tier=tier,
        name=custom_name,
        force_anomalous=True,
        force_granted_spell=grant_spell,
    )
    if not isinstance(base_item, dict):
        return None

    styled = apply_anomalous_incursions_gear_rules(
        base_item,
        scenario=scen_key or "anomalous_incursions",
        slot=slot,
        tier=tier,
        force_anomalous=True,
        force_granted_spell=grant_spell,
        element=site_elem,
        rng_seed=f"{spec.get('site_id')}:{seed_suffix}",
    )
    if custom_name and isinstance(styled, dict):
        styled["name"] = custom_name
        if isinstance(styled.get("metadata"), dict):
            styled["metadata"]["name"] = custom_name
            raw_eff = str(styled.get("effect") or "")
            if raw_eff.startswith("[GEAR_JSON]"):
                styled["effect"] = f"[GEAR_JSON]{json.dumps(styled['metadata'])}"

    eff_str = str(styled.get("effect") or styled.get("description") or "")
    item_type = "equipment"
    if slot == "Weapon":
        item_type = "weapon"
    elif slot == "Armor":
        item_type = "armor"
    elif slot == "Shield":
        item_type = "shield"
    elif slot.startswith("Accessory"):
        item_type = "accessory"

    db.add_item(
        int(user_id),
        name=str(styled.get("name") or "[Anomalous] Containment Gear"),
        item_type=item_type,
        effect=eff_str,
        slot_cost=int(styled.get("slot_cost") or 1),
        force=True,
    )
    return styled


def evaluate_reclamation_milestones(
    session_id: int,
    user_id: int,
    *,
    scen_key: str = "anomalous_incursions",
    turn_number: int = 0,
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate and award City Reclamation Milestones at `10`, `22`, and `36` stabilized sites.
    Stores rollback snapshot in `sessions.extra`.
    """
    if not session_id:
        return []
    nodes = list(world_nodes) if world_nodes is not None else (db.get_session_world_nodes(int(session_id)) or [])
    stab = 0
    for wn in nodes:
        if not isinstance(wn, Mapping) or str(wn.get("node_id") or "") not in PACIFIABLE_WILD_SITE_IDS:
            continue
        st = parse_node_state(wn)
        if isinstance(st.get("anomalous_site"), Mapping) and st["anomalous_site"].get("pacified"):
            stab += 1

    sess = db.get_session(int(session_id)) or {}
    ex = dict(sess.get("extra") or {}) if isinstance(sess.get("extra"), Mapping) else dict(sess)
    claimed = [int(x) for x in (ex.get("anomalous_milestones_claimed") or []) if str(x).isdigit()]
    prev_claimed = list(claimed)
    unlocked: list[dict[str, Any]] = []

    if stab >= 10 and 10 not in claimed:
        claimed.append(10)
        if user_id:
            db.apply_hp_mp_delta(int(user_id), gold_delta=250)
            try:
                from mechanics.social.factions import update_agent_promotion_reputation
                update_agent_promotion_reputation(
                    session_id=int(session_id), delta_rep=15, reason="Outer Cordon Reclamation (10 Sites)", user_id=int(user_id)
                )
            except Exception:
                pass
        unlocked.append({"threshold": 10, "notice": "🏆 Milestone (10 Sites Reclaimed): +15 Promotion Rep & +250G Hazard Grant!"})

    if stab >= 22 and 22 not in claimed:
        claimed.append(22)
        unlocked.append({"threshold": 22, "notice": "⚡ Milestone (22 Sites Reclaimed): Field Resonator upgraded to 4 Daily Charges!"})

    total_target = len(PACIFIABLE_WILD_SITE_IDS)
    if stab >= total_target and total_target not in claimed:
        claimed.append(total_target)
        chronometer = _grant_guaranteed_site_gear(
            int(user_id or 0),
            {"site_id": "milestone_36", "element": "aether", "threat_grade": 5},
            scen_key,
            force_relic_spell=True,
            force_tier=1,
            custom_name="[Anomalous] Warden's Aether Chronometer",
            seed_suffix="warden_36",
        )
        if user_id:
            try:
                from mechanics.social.factions import update_agent_promotion_reputation
                update_agent_promotion_reputation(
                    session_id=int(session_id), delta_rep=30, reason="Metropolitan Warden Commendation (36/36 Sites)", user_id=int(user_id)
                )
            except Exception:
                pass
        gear_nm = chronometer.get("name") if isinstance(chronometer, dict) else "[Anomalous] Warden's Aether Chronometer"
        unlocked.append({"threshold": total_target, "item_name": gear_nm, "notice": f"👑 METROPOLITAN WARDEN (36/36 Sites): +30 Rep, 5 Daily Charges & Relic `{gear_nm}`!"})

    if unlocked:
        db.update_session(
            int(session_id),
            extra={
                "anomalous_milestones_claimed": claimed,
                "anomalous_milestones_prev": prev_claimed,
                "anomalous_milestones_turn": int(turn_number),
            },
        )
    return unlocked


def complete_site_pacification(
    session_id: int,
    site_id: str,
    user_id: int | None = None,
    *,
    method: str = "puzzle_nullification",
    scen_key: str = "anomalous_incursions",
    current_day: int = 1,
    turn_number: int = 1,
    party_user_ids: list[int] | None = None,
) -> dict[str, Any]:
    """
    Permanently stabilize/pacify one of the 36 wild anomalous sites, granting
    gold, XP, Faction Promotion Rep, a site-element `[Anomalous]` gear piece
    (Grade V = guaranteed Tier-1 Relic with granted spell), and checking 10/22/36 milestones.
    """
    spec = get_anomalous_site_spec(site_id)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return {"success": False, "error": "This site cannot be permanently pacified."}

    canon_site_id = str(spec["site_id"])
    nodes = db.get_session_world_nodes(int(session_id)) or [] if session_id else []
    cur_st = get_site_state_dict(int(session_id), canon_site_id, world_nodes=nodes) if session_id else {}
    if cur_st.get("pacified"):
        return {"success": True, "already_pacified": True, "pacified": True, "site_id": canon_site_id}

    sess = db.get_session(int(session_id)) or {} if session_id else {}
    eff_scen = str(scen_key or sess.get("scenario") or "anomalous_incursions")
    eff_uid = int(user_id or sess.get("host_user_id") or 1)
    grade = int(spec.get("threat_grade") or 1)

    new_state = mutate_anomalous_site_state(
        int(session_id),
        canon_site_id,
        int(turn_number),
        {
            "visited": True,
            "pacified": True,
            "pacified_turn": int(turn_number),
            "pacified_day": int(current_day),
            "pacified_method": method,
            "puzzle_step": 3,
            "instability": 0,
            "boss_forced": False,
            "jammed_until_day": 0,
        },
        world_nodes=nodes,
    )

    gold_gain = 75 + 45 * grade
    xp_gain = 60 + 35 * grade
    rep_gain = 10

    targets = [int(u) for u in (party_user_ids or [eff_uid]) if u]
    for uid in targets:
        db.apply_hp_mp_delta(uid, gold_delta=gold_gain)
        db.add_xp(uid, xp_gain)
        try:
            from mechanics.social.factions import update_agent_promotion_reputation
            update_agent_promotion_reputation(
                session_id=int(session_id),
                delta_rep=rep_gain,
                reason=f"Stabilized {spec['name']} (Grade {spec['threat_grade_roman']})",
                user_id=uid,
            )
        except Exception:
            pass

    reward_item = _grant_guaranteed_site_gear(eff_uid, spec, eff_scen, seed_suffix=f"pacify:{turn_number}")
    fresh_nodes = db.get_session_world_nodes(int(session_id)) or [] if session_id else []
    unlocked_ms = evaluate_reclamation_milestones(
        int(session_id), eff_uid, scen_key=eff_scen, turn_number=int(turn_number), world_nodes=fresh_nodes
    )

    gear_name = reward_item.get("name") if isinstance(reward_item, dict) else ""
    items_gained_names: list[str] = [str(gear_name)] if gear_name else []
    for _m in unlocked_ms:
        if isinstance(_m, dict) and _m.get("item_name"):
            items_gained_names.append(str(_m["item_name"]))
    ms_text = " ".join(m["notice"] for m in unlocked_ms)
    seal_prose = str((spec.get("puzzle_spec") or {}).get("boss_profile", {}).get("ritual_seal_prose") or spec.get("pacified_sensory") or "")
    msg = (
        f"🛡️ **SITE STABILIZED — {spec['name']} (Grade {spec['threat_grade_roman']})!** "
        f"Random ambushes and Domain Hazards are permanently neutralized. "
        f"Earned +{gold_gain}G, +{xp_gain} XP, +{rep_gain} Promotion Rep"
        + (f", and **`{gear_name}`**" if gear_name else "")
        + "!"
        + (f" {ms_text}" if ms_text else "")
    )
    directive = (
        f"[SITE PACIFICATION OUTCOME]: {seal_prose} "
        f"Narrate the permanent neutralization of hazardous threats at {spec['name']} while preserving its eerie ambient stillness. "
        "Do NOT quote game numbers, gold totals, percentages, or JSON item tags in prose."
    )
    return {
        "success": True,
        "pacified": True,
        "site_id": canon_site_id,
        "site_name": spec["name"],
        "threat_grade": grade,
        "gold_gain": gold_gain,
        "xp_gain": xp_gain,
        "rep_gain": rep_gain,
        "reward_item": reward_item,
        "items_gained_names": items_gained_names,
        "milestones_unlocked": unlocked_ms,
        "site_state": new_state,
        "message": msg,
        "directive": directive,
    }


def build_site_harvest_choices(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
    *,
    scen_key: str = "anomalous_incursions",
    current_day: int = 1,
    has_priority_event: bool = False,
) -> list[dict[str, Any]]:
    """Build daily Safe Harvest / Overdraw Core buttons (or navigation to deepest room) inside a stabilized site."""
    if not session_id or has_priority_event:
        return []
    eff_nid = str(node_id or "").strip()
    if not eff_nid and location_str:
        try:
            eff_nid = str(db.resolve_node_id_from_location(int(session_id), location_str, prefer_facility=False) or "").strip()
        except Exception:
            eff_nid = ""
    nodes = db.get_session_world_nodes(int(session_id)) or []
    spec = resolve_anomalous_site(node_id=eff_nid, location_str=location_str, session_nodes=nodes)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return []

    site_id = str(spec["site_id"])
    st = get_site_state_dict(int(session_id), site_id, world_nodes=nodes)
    if not st.get("pacified"):
        return []
    if int(st.get("last_harvest_day") or 0) >= int(current_day):
        return []

    r_stat = get_resonator_charges_status(int(session_id), world_nodes=nodes, current_day=current_day)
    rem = int(r_stat.get("remaining") or 0)
    max_c = int(r_stat.get("max") or 3)
    if rem <= 0:
        return []

    deepest_id = str(spec.get("deepest_id") or "").strip()
    nid_low = eff_nid.lower()
    if nid_low != deepest_id.lower():
        site_sub_lows = {str(s).lower() for s in (spec.get("sub_ids") or ())}
        if nid_low == site_id.lower() or nid_low in site_sub_lows:
            deep_node = next(
                (n for n in nodes if isinstance(n, Mapping) and str(n.get("node_id") or "").lower() == deepest_id.lower()),
                None,
            )
            try:
                deep_loc = db.format_node_tiered_location(int(session_id), deepest_id) or str((deep_node or {}).get("name") or deepest_id)
            except Exception:
                deep_loc = str((deep_node or {}).get("name") or deepest_id)
            return [{
                "label": f"🧭 Head to Stabilized Core: {(deep_node or {}).get('name', deepest_id)} ({rem}/{max_c} Charges)",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "fast_travel",
                "action_category": "movement",
                "target_node_id": deepest_id,
                "target_location": deep_loc,
            }]
        return []

    grade = int(spec.get("threat_grade") or 1)
    return [
        {
            "label": f"🔍 Harvest Stabilized Resonance ({rem}/{max_c} Charges)",
            "stat": "PER",
            "requirement": 8 + grade,
            "mp_cost": 0,
            "intent": "anomalous_site_action",
            "site_action": "harvest",
            "site_id": site_id,
        },
        {
            "label": f"⚡ Overdraw Core Resonance — High Risk ({rem}/{max_c} Charges)",
            "stat": "INT",
            "requirement": 10 + grade,
            "mp_cost": 0,
            "intent": "anomalous_site_action",
            "site_action": "overdraw",
            "site_id": site_id,
        },
    ]


def resolve_site_harvest_action(
    session_id: int,
    user_id: int,
    site_id: str,
    mode: str = "harvest",
    *,
    pre_rolled_check: Any = None,
    force_gear_roll: float | None = None,
    force_remnant_roll: float | None = None,
    scen_key: str = "anomalous_incursions",
    turn_number: int = 0,
) -> dict[str, Any]:
    """
    Execute once-per-day stabilized core harvest (`1/site/day`, consuming 1 Resonator Charge).
    - `harvest`: 100% safe, awards ward + gold + XP + 12% (18% crit) `[Anomalous]` gear chance.
    - `overdraw`: doubles gold/XP & wards, 30% gear chance, and 40% Remnant Manifestation spawn
      (never undoing `pacified: True`).
    """
    spec = get_anomalous_site_spec(site_id)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return {"success": False, "error": "Harvesting is only available inside stabilized wild sites."}

    canon_id = str(spec["site_id"])
    sess = db.get_session(int(session_id)) or {}
    eff_scen = str(scen_key or sess.get("scenario") or "anomalous_incursions")
    try:
        curr_day, curr_min, _ = db.get_session_time(int(session_id))
    except Exception:
        curr_day, curr_min = 1, 720
    nodes = db.get_session_world_nodes(int(session_id)) or []
    st = get_site_state_dict(int(session_id), canon_id, world_nodes=nodes)
    if not st.get("pacified"):
        return {"success": False, "error": "Site must be stabilized before harvesting its resonance core."}
    if int(st.get("last_harvest_day") or 0) >= int(curr_day):
        return {"success": False, "error": "This site's resonance core was already harvested today."}

    r_stat = get_resonator_charges_status(int(session_id), world_nodes=nodes, current_day=curr_day, session=sess)
    if int(r_stat["remaining"]) <= 0:
        return {"success": False, "error": "All daily Field Resonator Charges have been expended for today."}

    is_overdraw = str(mode or "harvest").strip().lower() == "overdraw"
    grade = int(spec.get("threat_grade") or 1)
    site_elem = str(spec.get("element") or "aether").lower()

    tier_str = str(getattr(pre_rolled_check, "tier", "") or (pre_rolled_check.get("tier") if isinstance(pre_rolled_check, Mapping) else "") or "success")
    if pre_rolled_check is not None:
        succeeded = bool(is_check_success(pre_rolled_check, default_if_none=True))
    else:
        succeeded = True
    is_crit = succeeded and tier_str == "crit_success"

    # Consume 1 Resonator Charge and mark today's site harvest
    prev_used = int(r_stat["used"])
    db.update_session(
        int(session_id),
        extra={
            "resonator_charges_day": int(curr_day),
            "resonator_charges_used": prev_used + 1,
            "resonator_charges_prev": {"day": int(curr_day), "used": prev_used},
            "resonator_charges_turn": int(turn_number),
        },
    )
    mutate_anomalous_site_state(
        int(session_id),
        canon_id,
        int(turn_number),
        {"last_harvest_day": int(curr_day)},
        world_nodes=nodes,
    )

    from mechanics.social.factions import faction_bonus_active, get_anomalous_faction_state

    f_state = get_anomalous_faction_state(int(session_id)) if session_id else {}
    p_arch = str((f_state or {}).get("faction_archetype_key") or "").strip().lower()
    synd_harvest_active = faction_bonus_active("clandestine_faction", f_state)

    mult = 2 if is_overdraw else 1
    gold_gain = (25 + 12 * grade) * mult
    xp_gain = (20 + 10 * grade) * mult
    if not succeeded and not is_overdraw:
        gold_gain = max(10, gold_gain // 2)
        xp_gain = max(10, xp_gain // 2)
    if synd_harvest_active:
        gold_gain = int(round(gold_gain * 1.25))

    ward_name, ward_desc = _ELEMENT_WARD_REWARDS.get(site_elem, ("Stabilization Flare", "Containment ward flare."))
    if user_id:
        db.apply_hp_mp_delta(int(user_id), gold_delta=gold_gain)
        db.add_xp(int(user_id), xp_gain)
        for _ in range(mult):
            db.add_item(int(user_id), name=ward_name, item_type="consumable", effect=ward_desc, slot_cost=1, force=True)

    items_gained_names: list[str] = [ward_name] * mult if user_id else []
    gear_roll = float(force_gear_roll) if force_gear_roll is not None else random.random()
    gear_thresh = 0.30 if is_overdraw else (0.18 if is_crit else 0.12)
    bonus_gear = None
    if gear_roll < gear_thresh:
        bonus_gear = _grant_guaranteed_site_gear(int(user_id or 0), spec, eff_scen, seed_suffix=f"harvest:{curr_day}")
        if isinstance(bonus_gear, dict) and bonus_gear.get("name"):
            items_gained_names.append(str(bonus_gear["name"]))

    codex_sighted_id = ""
    codex_sighted_name = ""
    if user_id:
        try:
            from mechanics.world.anomaly_engine import infer_location_biome_and_time
            from mechanics.world.folklore_codex import get_folklore_codex_entries
            h_biome, _ = infer_location_biome_and_time(
                str(sess.get("current_location") or spec["name"]),
                current_minute=curr_min,
            )
            u_codex = db.get_user_folklore_codex(int(user_id)) or {}
            codex_cands = []
            for ce in get_folklore_codex_entries():
                if not isinstance(ce, Mapping) or not ce.get("codex_id"):
                    continue
                cid_c = str(ce["codex_id"])
                cur_entry = u_codex.get(cid_c)
                cur_stg = (
                    str(cur_entry.get("stage") or "").lower()
                    if isinstance(cur_entry, Mapping)
                    else str(cur_entry or "").lower()
                )
                if cur_stg in ("sighted", "verified", "contained"):
                    continue
                if h_biome in (ce.get("biomes") or ()) or str(ce.get("primary_element") or "").lower() == site_elem:
                    codex_cands.append(ce)
            if codex_cands:
                picked_ce = random.Random(f"harvest_codex:{session_id}:{canon_id}:{curr_day}").choice(codex_cands)
                codex_sighted_id = str(picked_ce["codex_id"])
                codex_sighted_name = str(picked_ce.get("name") or codex_sighted_id)
                db.record_folklore_codex_progress(
                    int(user_id),
                    codex_sighted_id,
                    stage="sighted",
                    session_id=int(session_id),
                    turn_number=int(turn_number),
                )
        except Exception:
            codex_sighted_id = ""
            codex_sighted_name = ""

    remnant_spawned = None
    if is_overdraw:
        rem_roll = float(force_remnant_roll) if force_remnant_roll is not None else random.random()
        rem_thresh = 0.20 if faction_bonus_active("cult_faction", f_state) else 0.40
        if rem_roll < rem_thresh:
            bp = generate_anomaly_blueprint(
                session_id=int(session_id),
                seed_key=f"remnant:{canon_id}:{curr_day}:{turn_number}",
                scenario=eff_scen,
                location=str(sess.get("current_location") or spec["name"]),
                current_minute=curr_min,
                force_disposition="hostile",
                force_element=site_elem,
                tier=grade,
            )
            remnant_spawned = instantiate_enemy_from_blueprint(bp, tier=grade)
            remnant_spawned["is_remnant_manifestation"] = True
            remnant_spawned["anomalous_site_id"] = canon_id
            remnant_spawned["is_anomalous_manifestation"] = True
            enemies_now = list(sess.get("nearby_enemies") or [])
            enemies_now.append(remnant_spawned)
            db.update_session(int(session_id), nearby_enemies=enemies_now)

    gear_note = f" Bonus drop: **`{bonus_gear['name']}`**!" if isinstance(bonus_gear, dict) else ""
    codex_note = f" 📖 Codex Trace Sighted: **{codex_sighted_name}**!" if codex_sighted_name else ""
    rem_note = (
        f" ⚡ **Overdraw Backlash:** A hostile **{remnant_spawned['name']}** crystalized from residual energy (pacification intact)!"
        if remnant_spawned
        else ""
    )
    msg = (
        f"🔍 **Resonance {'Overdrawn' if is_overdraw else 'Harvested'}** at {spec['name']} "
        f"({prev_used + 1}/{r_stat['max']} Charges Used): Collected **{mult}x {ward_name}**, "
        f"+{gold_gain}G, +{xp_gain} XP.{gear_note}{codex_note}{rem_note}"
    )
    directive = (
        f"[RESONANCE HARVEST OUTCOME]: The player tapped the stabilized core at {spec['name']} safely extracting condensed reagent mist"
        + (f", though overdraw shook loose a hostile remnant manifestation ({remnant_spawned['name']}) without breaking site containment!" if remnant_spawned else ".")
        + " Narrate this sensory scene vividly without raw game numbers, percentages, or JSON tags."
    )
    return {
        "success": True,
        "resolved": not bool(remnant_spawned),
        "combat_started": bool(remnant_spawned),
        "pacified": True,
        "mode": "overdraw" if is_overdraw else "harvest",
        "ward_granted": ward_name,
        "ward_qty": mult,
        "gold_gain": gold_gain,
        "xp_gain": xp_gain,
        "reward_item": bonus_gear,
        "items_gained_names": items_gained_names,
        "codex_sighted_id": codex_sighted_id,
        "remnant_enemy": remnant_spawned,
        "charges_used": prev_used + 1,
        "charges_max": r_stat["max"],
        "message": msg,
        "directive": directive,
    }
