from __future__ import annotations

import random
from typing import Any, Callable, Iterable, Mapping

import db
import scenario_data
from mechanics.combat.enemy_profiles import is_anomalous_danger_zone
from mechanics.combat.items.anomalous_gear import aggregate_equipped_anomalous_passives
from mechanics.world.anomalous_sites.catalog import (
    HOSTILE_HQ_SITE_IDS,
    PACIFIABLE_WILD_SITE_IDS,
    THEME_PARK_SITE_ID,
    get_anomalous_site_spec,
    get_site_state_dict,
    is_site_dormant_by_schedule,
    is_site_pacified,
    is_spatial_loop_site,
    is_theme_park_witching_peak,
    load_anomalous_sites_catalog,
    mutate_anomalous_site_state,
    parse_node_state,
    resolve_anomalous_site,
)

SPATIAL_ANCHOR_KEYWORDS: tuple[str, ...] = (
    "stabilization flare",
    "anchor flare",
    "containment flare",
    "signal flare",
    "spatial anchor",
)

PASSIVE_WARD_KEYWORDS: tuple[str, ...] = (
    "purging salt",
    "warding charm",
    "stabilization flare",
    "anchor flare",
    "containment flare",
    "signal flare",
    "lantern talisman",
    "bunga rampai",
    "suzu bell",
    "serunai",
)


def _extract_primary_char(party: list[Any] | None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    for entry in (party or []):
        if isinstance(entry, (tuple, list)) and len(entry) >= 2 and isinstance(entry[0], dict):
            return entry[0], list(entry[1] or [])
        if isinstance(entry, dict):
            return entry, []
    return None, []


def _collect_item_names(inventory_items: Iterable[Any] | None, equipped_items: Mapping[str, Any] | Iterable[Any] | None) -> list[str]:
    names: list[str] = []
    for col in (inventory_items or ()):
        if isinstance(col, Mapping) and col.get("name"):
            names.append(str(col["name"]).lower())
    eq_vals = equipped_items.values() if isinstance(equipped_items, Mapping) else (equipped_items or ())
    for eq in eq_vals:
        if isinstance(eq, Mapping) and eq.get("name"):
            names.append(str(eq["name"]).lower())
    return names


def compute_domain_mitigation(
    session_id: int,
    user_id: int,
    char_data: Mapping[str, Any] | None,
    equipped_items: Mapping[str, Any] | Iterable[Any] | None,
    inventory_items: Iterable[Any] | None,
    spec: Mapping[str, Any],
    *,
    active_pacts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Inspect Entity Pacts, `[Anomalous]` gear/protective traits, and passive wards
    to determine Domain Hazard mitigation (`0.0`, `0.5`, or `1.0`).
    """
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    mit_elements = {str(e).lower() for e in (rule.get("mitigation_elements") or ())}
    mit_keywords = tuple(str(k).lower() for k in (rule.get("mitigation_keywords") or ()))
    site_elem = str(spec.get("element") or "").lower()

    # 1. Entity Pact elemental affinity check -> 100% mitigation
    pacts = active_pacts
    if pacts is None and session_id and user_id:
        try:
            pacts = db.get_player_active_pacts(int(session_id), int(user_id)) or []
        except Exception:
            pacts = []
    for p_row in (pacts or []):
        if not isinstance(p_row, Mapping):
            continue
        p_elem = str(p_row.get("primary_element") or p_row.get("element") or "").lower()
        p_meta = p_row.get("patron_id") or ""
        if (p_elem and (p_elem in mit_elements or p_elem == site_elem)) or (
            site_elem and site_elem in str(p_meta).lower()
        ):
            return {"mitigation_ratio": 1.0, "source": "entity_pact", "has_spatial_anchor": True}

    all_item_names = _collect_item_names(inventory_items, equipped_items)
    has_spatial_anchor = any(kw in nm for nm in all_item_names for kw in SPATIAL_ANCHOR_KEYWORDS)

    # 2. Equipped gear traits / anomalous elemental passives
    eq_passives: dict[str, Any] = {}
    if equipped_items:
        try:
            eq_passives = aggregate_equipped_anomalous_passives(equipped_items)
        except Exception:
            eq_passives = {}
    res_pct = eq_passives.get("elemental_res_pct") if isinstance(eq_passives, Mapping) else {}

    eq_vals = list(equipped_items.values()) if isinstance(equipped_items, Mapping) else list(equipped_items or ())
    has_kw_gear = any(
        isinstance(eq, Mapping) and (
            any(kw in str(eq.get("name") or "").lower() for kw in mit_keywords)
            or any(kw in str(eq.get("effect") or "").lower() for kw in mit_keywords)
        )
        for eq in eq_vals
    )
    has_elem_res_full = isinstance(res_pct, Mapping) and any(
        int(res_pct.get(el, 0) or 0) >= 15 for el in (mit_elements | {site_elem} - {""})
    )
    if has_kw_gear or has_elem_res_full:
        return {"mitigation_ratio": 1.0, "source": "matched_gear", "has_spatial_anchor": has_spatial_anchor}

    # 3. Passive warding items held in inventory -> 100% mitigation for wards matching hazard
    has_ward_item = any(
        any(kw in nm for kw in (mit_keywords + PASSIVE_WARD_KEYWORDS))
        for nm in all_item_names
    )
    if has_ward_item:
        return {"mitigation_ratio": 1.0, "source": "ward_item", "has_spatial_anchor": has_spatial_anchor}

    # 4. Partial [Anomalous] gear protection -> 50% mitigation
    has_any_anom_gear = any(
        isinstance(eq, Mapping) and "[anomalous]" in str(eq.get("name") or "").lower()
        for eq in eq_vals
    ) or (isinstance(res_pct, Mapping) and any(int(v or 0) > 0 for v in res_pct.values()))
    if has_any_anom_gear:
        return {"mitigation_ratio": 0.5, "source": "partial_anomalous_gear", "has_spatial_anchor": has_spatial_anchor}

    return {"mitigation_ratio": 0.0, "source": "none", "has_spatial_anchor": has_spatial_anchor}


def _apply_ambient_modifiers_dict(spec: Mapping[str, Any]) -> dict[str, Any]:
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    site_elem = str(spec.get("element") or "").lower()
    amp_map: dict[str, float] = {}
    res_map: dict[str, int] = {}
    if site_elem:
        amp_map[site_elem] = float(rule.get("ambient_element_amp") or 0.15)
        res_map[site_elem] = int(rule.get("ambient_res_pct") or 15)
    sec_amp = rule.get("ambient_secondary_amp")
    if isinstance(sec_amp, Mapping):
        for k, v in sec_amp.items():
            kl = str(k).lower()
            amp_map[kl] = float(v or 0.10)
            res_map[kl] = max(res_map.get(kl, 0), int(round(float(v or 0.10) * 100)))

    return {
        "elemental_amp": amp_map,
        "elemental_res_pct": res_map,
        "stat_bonuses": dict(rule.get("ambient_stat_bonus") or {}),
        "out_of_combat_hp_regen": int(rule.get("ambient_out_of_combat_hp_regen") or 0),
        "out_of_combat_mp_regen": int(rule.get("ambient_out_of_combat_mp_regen") or 0),
        "crit_bonus": float(rule.get("ambient_crit_bonus") or 0.0),
        "salvage_bonus": int(rule.get("ambient_salvage_bonus") or 0),
        "knockback_immune": bool(rule.get("ambient_knockback_immune") or False),
        "ambient_summary": str(rule.get("ambient_summary") or ""),
    }


def _build_combat_modifiers_dict(spec: Mapping[str, Any], pacified: bool) -> dict[str, Any]:
    if pacified:
        return {}
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    return {
        "enemy_crit_bonus": float(rule.get("combat_enemy_crit_bonus") or 0.0),
        "enemy_lifesteal": float(rule.get("combat_enemy_lifesteal") or 0.0),
        "enemy_regen_pct": float(rule.get("combat_enemy_regen_pct") or 0.0),
        "enemy_element_amp": dict(rule.get("combat_enemy_element_amp") or {}),
        "ranged_acc_penalty": int(rule.get("combat_ranged_acc_penalty") or 0),
        "stealth_penalty": int(rule.get("combat_stealth_penalty") or 0),
        "heavy_speed_penalty": int(rule.get("combat_heavy_speed_penalty") or 0),
        "bio_rot": bool(rule.get("combat_bio_rot") or False),
        "jam_comms": bool(rule.get("combat_jam_comms") or False),
    }


def compute_domain_skill_check_modifiers(
    session_id: int,
    session: Mapping[str, Any] | None,
    user_id: int,
    char_data: Mapping[str, Any] | None,
    stat_key: str,
    inventory_items: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """
    Return `{stat_bonus, dc_penalty, jam_comms}` for an active anomalous site.
    - `stat_bonus` comes from persistent `ambient_stat_bonus` (active pre- & post-pacification).
    - `dc_penalty` and `jam_comms` run only pre-pacification when Domain Hazard mitigation < 1.0.
    """
    no_op = {"stat_bonus": 0, "dc_penalty": 0, "jam_comms": False}
    if not isinstance(session, Mapping):
        return no_op
    scen_key = str(session.get("scenario") or "")
    if not (scenario_data.is_anomalous_incursions_scenario(scen_key) or scenario_data.is_anomalous_high_school_scenario(scen_key)):
        return no_op

    curr_nid = str(session.get("current_node_id") or "")
    curr_loc = str(session.get("current_location") or "")
    current_minute = int(session.get("current_minute", 720) or 720)
    world_nodes = db.get_session_world_nodes(int(session_id)) if session_id else None
    spec = resolve_anomalous_site(node_id=curr_nid, location_str=curr_loc, session_nodes=world_nodes)
    if not spec or is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=curr_nid):
        return no_op

    site_id = str(spec["site_id"])
    site_state = get_site_state_dict(int(session_id), site_id, world_nodes=world_nodes) if session_id else {}
    pacified = bool(spec.get("site_type") not in ("theme_park_night", "hostile_hq") and site_state.get("pacified"))

    ambient_mods = _apply_ambient_modifiers_dict(spec)
    stat_up = {"TECH": "INT", "WIL": "END", "WIS": "PER"}.get(str(stat_key or "").upper(), str(stat_key or "").upper())
    stat_bonus = int((ambient_mods.get("stat_bonuses") or {}).get(stat_up, 0) or 0)

    dc_penalty = 0
    jam_comms = False
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    if not pacified:
        equipped = db.get_equipment(int(user_id)) if (session_id and user_id) else {}
        inv = list(inventory_items) if inventory_items is not None else (db.get_inventory(int(user_id)) if (session_id and user_id) else [])
        mit = compute_domain_mitigation(int(session_id or 0), int(user_id or 0), char_data, equipped, inv, spec)
        if float(mit.get("mitigation_ratio") or 0.0) < 1.0:
            raw_pen = int(rule.get("dc_penalty") or 0)
            pen_stats = {
                {"TECH": "INT", "WIL": "END", "WIS": "PER"}.get(str(s).upper(), str(s).upper())
                for s in (rule.get("dc_penalty_stats") or ())
            }
            if raw_pen > 0 and (not pen_stats or stat_up in pen_stats):
                dc_penalty = raw_pen
            jam_comms = bool(rule.get("combat_jam_comms") or False)

    return {"stat_bonus": stat_bonus, "dc_penalty": dc_penalty, "jam_comms": jam_comms}


def evaluate_turn_domain_effects(
    session_id: int,
    session: dict[str, Any],
    party: list[Any],
    curr_node: Mapping[str, Any] | None = None,
    actions: list[Any] | None = None,
    *,
    persist_db: bool = True,
    is_retry: bool = False,
) -> dict[str, Any]:
    """
    Evaluate dual-layer Domain Rules for the player's current anomalous site:
    - Marks `visited: True` on first arrival into any catalog site (unlocking Codex Site Registry).
    - Always provides `ambient_modifiers` (kept permanently post-pacification).
    - When un-pacified and past Turn-1 grace, applies Signature Hazard effects (1 HP floor).
    """
    if not isinstance(session, dict):
        return {"active": False}
    scen_key = str(session.get("scenario") or "")
    if not (scenario_data.is_anomalous_incursions_scenario(scen_key) or scenario_data.is_anomalous_high_school_scenario(scen_key)):
        session.pop("_active_anomalous_domain", None)
        return {"active": False}

    curr_nid = str((curr_node or {}).get("node_id") or session.get("current_node_id") or "")
    curr_pid = str((curr_node or {}).get("parent_id") or "")
    curr_loc = str(session.get("current_location") or "")
    current_minute = int(session.get("current_minute", 720) or 720)
    turn_now = int(session.get("turn_count") or 0)

    world_nodes = db.get_session_world_nodes(int(session_id)) if session_id else None
    spec = resolve_anomalous_site(
        node_id=curr_nid,
        parent_id=curr_pid,
        location_str=curr_loc,
        curr_node=curr_node,
        session_nodes=world_nodes,
    )
    if not spec or is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=curr_nid):
        session.pop("_active_anomalous_domain", None)
        return {"active": False}

    site_id = str(spec["site_id"])
    site_state = get_site_state_dict(int(session_id), site_id, world_nodes=world_nodes) if session_id else {}
    pacified = bool(spec.get("site_type") not in ("theme_park_night", "hostile_hq") and site_state.get("pacified"))

    if persist_db and session_id and not site_state.get("visited"):
        site_state = mutate_anomalous_site_state(
            int(session_id),
            site_id,
            turn_now,
            {"visited": True, "visited_turn": max(1, turn_now)},
            world_nodes=world_nodes,
        )

    char_data, inv_items = _extract_primary_char(party)
    user_id = int((char_data or {}).get("user_id") or 0)
    equipped = db.get_equipment(user_id) if (session_id and user_id) else {}
    mit = compute_domain_mitigation(session_id, user_id, char_data, equipped, inv_items, spec)
    mit_ratio = float(mit.get("mitigation_ratio") or 0.0)

    ambient_mods = _apply_ambient_modifiers_dict(spec)
    combat_mods = _build_combat_modifiers_dict(spec, pacified=pacified)
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}

    hp_delta = 0
    mp_delta = 0
    time_slip_min = 0
    composure_shift = ""
    wet_flag = False
    stage_directives: list[str] = []

    is_peaceful_turn = bool(actions) and all(
        isinstance(a, Mapping) and str(a.get("intent") or "").lower() in ("dialogue_init", "social_talk", "npc_talk", "peaceful")
        for a in actions
    )

    if not pacified and not is_retry and turn_now > 1 and char_data is not None and not is_peaceful_turn:
        instability = int(site_state.get("instability") or 0)
        surge_mult = 1.5 if instability == 1 else 1.0

        raw_hp_drain = int(round(int(rule.get("hp_drain") or 0) * surge_mult * (1.0 - mit_ratio)))
        raw_mp_drain = int(round(int(rule.get("mp_drain") or 0) * surge_mult * (1.0 - mit_ratio)))

        cur_hp = int(char_data.get("hp", 20) or 20)
        cur_mp = int(char_data.get("mp", 10) or 10)
        if raw_hp_drain > 0:
            # Strict 1 HP floor on out-of-combat environmental hazard drain
            actual_dmg = min(raw_hp_drain, max(0, cur_hp - 1))
            if actual_dmg > 0:
                char_data["hp"] = cur_hp - actual_dmg
                hp_delta = -actual_dmg
        if raw_mp_drain > 0:
            actual_mp_loss = min(raw_mp_drain, max(0, cur_mp))
            if actual_mp_loss > 0:
                char_data["mp"] = cur_mp - actual_mp_loss
                mp_delta = -actual_mp_loss

        if mit_ratio < 1.0:
            time_slip_min = int(rule.get("time_slip_min") or 0)
            composure_shift = str(rule.get("composure_shift") or "")
            wet_flag = bool(rule.get("wet_flag"))

        if persist_db and user_id and (hp_delta != 0 or mp_delta != 0):
            db.update_character_fields(user_id, hp=int(char_data["hp"]), mp=int(char_data["mp"]))

        if hp_delta < 0 or mp_delta < 0 or composure_shift or wet_flag or time_slip_min > 0:
            stage_directives.append(
                f"[DOMAIN HAZARD — {rule.get('name', 'Anomalous Distortion')}]: "
                f"{rule.get('hazard_cue', 'The site warps atmosphere and drains intruders.')}"
            )
        elif mit_ratio >= 1.0:
            stage_directives.append(
                f"[WARD MITIGATION ACTIVE — {rule.get('name', 'Anomalous Distortion')}]: "
                "Protective gear, wards, or active pact seals deflect the environmental hazard cleanly."
            )
    elif pacified and not is_retry and char_data is not None and not session.get("nearby_enemies"):
        hp_regen = int(ambient_mods.get("out_of_combat_hp_regen") or 0)
        mp_regen = int(ambient_mods.get("out_of_combat_mp_regen") or 0)
        cur_hp = int(char_data.get("hp", 20) or 20)
        max_hp = int(char_data.get("max_hp", cur_hp) or cur_hp)
        cur_mp = int(char_data.get("mp", 10) or 10)
        max_mp = int(char_data.get("max_mp", cur_mp) or cur_mp)
        if hp_regen > 0 and cur_hp < max_hp:
            gain_hp = min(hp_regen, max_hp - cur_hp)
            char_data["hp"] = cur_hp + gain_hp
            hp_delta = gain_hp
        if mp_regen > 0 and cur_mp < max_mp:
            gain_mp = min(mp_regen, max_mp - cur_mp)
            char_data["mp"] = cur_mp + gain_mp
            mp_delta = gain_mp
        if persist_db and user_id and (hp_delta > 0 or mp_delta > 0):
            db.update_character_fields(user_id, hp=int(char_data["hp"]), mp=int(char_data["mp"]))

    result = {
        "active": True,
        "site_id": site_id,
        "site_name": spec["name"],
        "element": spec["element"],
        "threat_grade": spec["threat_grade"],
        "pacified": pacified,
        "mitigation_ratio": mit_ratio,
        "mitigation_source": mit["source"],
        "hp_delta": hp_delta,
        "mp_delta": mp_delta,
        "time_slip_min": time_slip_min,
        "composure_shift": composure_shift,
        "wet_flag": wet_flag,
        "ambient_modifiers": ambient_mods,
        "combat_modifiers": combat_mods,
        "stage_directives": stage_directives,
    }
    session["_active_anomalous_domain"] = result
    return result


def apply_domain_modifiers_to_combat_attrs(
    player_attrs: dict[str, Any],
    domain_res: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """
    Merge persistent Domain ambient effects (+15% element Amp/Res, crit bonus) and
    pre-pacification penalties into `player_attrs`, strictly honoring gear stacking caps.
    """
    if not isinstance(player_attrs, dict) or not isinstance(domain_res, Mapping) or not domain_res.get("active"):
        return player_attrs
    if player_attrs.get("_domain_mods_applied"):
        return player_attrs
    player_attrs["_domain_mods_applied"] = True

    amb = domain_res.get("ambient_modifiers") if isinstance(domain_res.get("ambient_modifiers"), Mapping) else {}
    amp_cur = dict(player_attrs.get("elemental_amp") or {})
    for el, val in (amb.get("elemental_amp") or {}).items():
        el_l = str(el).lower()
        amp_cur[el_l] = min(0.60, round(float(amp_cur.get(el_l, 0.0) or 0.0) + float(val or 0.0), 3))
    player_attrs["elemental_amp"] = amp_cur

    gear_dr = dict(player_attrs.get("gear_dr") or {})
    for el, pct in (amb.get("elemental_res_pct") or {}).items():
        el_l = str(el).lower()
        gear_dr[el_l] = min(0.75, round(float(gear_dr.get(el_l, 0.0) or 0.0) + (float(pct or 0.0) / 100.0), 3))
    player_attrs["gear_dr"] = gear_dr

    if amb.get("crit_bonus"):
        player_attrs["crit_chance"] = round(float(player_attrs.get("crit_chance", 0.05) or 0.05) + float(amb["crit_bonus"]), 3)

    stat_bonuses = amb.get("stat_bonuses") if isinstance(amb.get("stat_bonuses"), Mapping) else {}
    if int(stat_bonuses.get("AGI", 0) or 0) > 0:
        player_attrs["eva"] = int(player_attrs.get("eva", 11)) + int(stat_bonuses["AGI"]) * 2
    if int(stat_bonuses.get("PER", 0) or 0) > 0:
        player_attrs["acc"] = int(player_attrs.get("acc", 66)) + int(stat_bonuses["PER"]) * 3
    if int(stat_bonuses.get("END", 0) or 0) > 0:
        player_attrs["def"] = int(player_attrs.get("def", 0)) + int(stat_bonuses["END"]) * 2

    if not domain_res.get("pacified") and float(domain_res.get("mitigation_ratio") or 0.0) < 1.0:
        c_mods = domain_res.get("combat_modifiers") if isinstance(domain_res.get("combat_modifiers"), Mapping) else {}
        ranged_pen = int(c_mods.get("ranged_acc_penalty") or 0)
        if ranged_pen > 0:
            player_attrs["acc"] = max(10, int(player_attrs.get("acc", 66)) - ranged_pen * 3)
        stealth_pen = int(c_mods.get("stealth_penalty") or 0)
        if stealth_pen > 0:
            player_attrs["eva"] = max(0, int(player_attrs.get("eva", 11)) - stealth_pen * 3)
        heavy_pen = int(c_mods.get("heavy_speed_penalty") or 0)
        if heavy_pen > 0:
            player_attrs["acc"] = max(10, int(player_attrs.get("acc", 66)) - heavy_pen * 2)

    return player_attrs


def evaluate_spatial_loop_travel(
    session_id: int,
    session: dict[str, Any],
    curr_node_id: str,
    dest_node_id: str,
    party: list[Any] | None = None,
    actions: list[Any] | None = None,
    *,
    rng_roll_fn: Callable[[], int] | None = None,
    consume_flare: bool = True,
    persist_db: bool = True,
) -> dict[str, Any]:
    """
    Check Spatial-Loop escape when traveling OUT of an un-pacified inner room of a
    Spatial-Loop site (`loc_endless_dept_store`, `loc_liminal_residential`, `loc_cul_de_sac_9`,
    `loc_13th_stairwell`, `loc_uni_escher_stairwell`, `loc_glass_mirage_estate`, or night
    `loc_tp_mirror_labyrinth`). Failing adds +15m, -5 MP, shaken composure, and reroutes
    cleanly to the site's outer entrance cordon so players never soft-lock.
    """
    no_op = {"triggered": False, "passed": True, "rerouted": False, "extra_minutes": 0, "mp_drain": 0, "stage_directive": ""}
    if not curr_node_id or not dest_node_id or curr_node_id == dest_node_id:
        return no_op

    scen_key = str((session or {}).get("scenario") or "")
    current_minute = int((session or {}).get("current_minute", 720) or 720)
    spec = resolve_anomalous_site(node_id=curr_node_id)
    if not spec or not is_spatial_loop_site(spec, node_id=curr_node_id):
        return no_op
    if is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=curr_node_id):
        return no_op

    site_id = str(spec["site_id"])
    # For Theme Park Mirror Labyrinth, the spatial trap catches exiting loc_tp_mirror_labyrinth itself
    entrance_id = str(spec.get("entrance_id") or site_id)
    if site_id == THEME_PARK_SITE_ID:
        if curr_node_id.lower() != "loc_tp_mirror_labyrinth":
            return no_op
        # Stumble drops player out onto Main Midway cordon
        entrance_id = "loc_tp_main_midway"
    else:
        # Already standing at outer cordon OR moving inside the site itself (no escape stumble)
        if curr_node_id.lower() == entrance_id.lower():
            return no_op
        if dest_node_id.lower() in {str(x).lower() for x in (spec.get("sub_ids") or ())} and dest_node_id.lower() != entrance_id.lower():
            return no_op
        if is_site_pacified(session_id, site_id=site_id, node_id=curr_node_id):
            return no_op

    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    dc = int(rule.get("spatial_loop_dc") or 12)

    char_data, inv_items = _extract_primary_char(party)
    user_id = int((char_data or {}).get("user_id") or 0)
    equipped = db.get_equipment(user_id) if (session_id and user_id) else {}
    mit = compute_domain_mitigation(session_id, user_id, char_data, equipped, inv_items, spec)
    if mit.get("has_spatial_anchor"):
        if consume_flare and persist_db and user_id:
            for item in inv_items:
                nm = str((item or {}).get("name") or "")
                if any(kw in nm.lower() for kw in SPATIAL_ANCHOR_KEYWORDS):
                    try:
                        db.remove_item(user_id, nm, 1)
                    except Exception:
                        pass
                    break
        return {
            "triggered": True,
            "passed": True,
            "rerouted": False,
            "extra_minutes": 0,
            "mp_drain": 0,
            "stage_directive": "[SPATIAL ANCHOR FLARE]: A crisp anchor pulse pins corridor bearings true, letting you exit cleanly.",
        }

    stats = (char_data or {}).get("stats") or {}
    if not isinstance(stats, Mapping):
        stats = {}
    per_val = int(stats.get("PER", char_data.get("per", 5)) if char_data else 5)
    int_val = int(stats.get("INT", char_data.get("int", 5)) if char_data else 5)
    best_mod = max(per_val, int_val)
    d20_roll = int(rng_roll_fn()) if callable(rng_roll_fn) else random.randint(1, 20)
    passed = (d20_roll + best_mod) >= dc

    if passed:
        return {
            "triggered": True,
            "passed": True,
            "rerouted": False,
            "extra_minutes": 0,
            "mp_drain": 0,
            "stage_directive": "",
        }

    # Stumble back to outer entrance cordon (+15m, -5 MP, composure: shaken) — never soft-lock!
    mp_drain = 0
    if char_data is not None:
        cur_mp = int(char_data.get("mp", 0) or 0)
        mp_drain = min(5, max(0, cur_mp))
        char_data["mp"] = cur_mp - mp_drain
        if persist_db and user_id and mp_drain > 0:
            db.update_character_fields(user_id, mp=int(char_data["mp"]))

    reroute_loc = ""
    if session_id:
        try:
            reroute_loc = db.format_node_tiered_location(int(session_id), entrance_id) or ""
        except Exception:
            reroute_loc = ""

    return {
        "triggered": True,
        "passed": False,
        "rerouted": True,
        "reroute_node_id": entrance_id,
        "reroute_location": reroute_loc,
        "extra_minutes": 15,
        "mp_drain": mp_drain,
        "composure_shift": "shaken",
        "stage_directive": (
            "[STAGE DIRECTION — SPATIAL LOOP ESCAPE STUMBLE]: Repeating corridors twist exit paths backward! "
            "After disorienting minutes of fighting through impossible bends, you stumble battered and shaken back out to the entrance cordon."
        ),
    }


def is_sleep_blocked_in_anomalous_zone(
    session_id: int = 0,
    location_name: str = "",
    node_id: str = "",
    current_minute: int = 720,
    scen_key: str = "anomalous_incursions",
) -> tuple[bool, str]:
    """Return `(True, reason)` when player attempts to sleep/nap inside an active danger zone."""
    if not (scenario_data.is_anomalous_incursions_scenario(scen_key) or scenario_data.is_anomalous_high_school_scenario(scen_key)):
        return False, ""
    if is_anomalous_danger_zone(
        location_name=location_name,
        location_id=node_id,
        current_minute=current_minute,
        session_id=session_id,
        scen_key=scen_key,
    ):
        return True, "You cannot sleep or nap inside an active anomalous quarantine zone!"
    return False, ""


def _read_session_extra_map(session_id: int, session: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(session, Mapping):
        ex = session.get("extra")
        if isinstance(ex, Mapping):
            return dict(ex)
        return dict(session)
    if not session_id:
        return {}
    s_row = db.get_session(int(session_id)) or {}
    ex = s_row.get("extra")
    if isinstance(ex, Mapping):
        return dict(ex)
    return dict(s_row)


def get_resonator_charges_status(
    session_id: int,
    *,
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
    current_day: int = 1,
    session: Mapping[str, Any] | None = None,
) -> dict[str, int]:
    """Return daily Field Resonator charge usage/cap and total stabilized wild sites."""
    nodes = list(world_nodes) if world_nodes is not None else (db.get_session_world_nodes(int(session_id)) or [] if session_id else [])
    stabilized = 0
    for wn in nodes:
        if not isinstance(wn, Mapping):
            continue
        nid = str(wn.get("node_id") or "")
        if nid not in PACIFIABLE_WILD_SITE_IDS:
            continue
        st = parse_node_state(wn)
        as_st = st.get("anomalous_site")
        if isinstance(as_st, Mapping) and as_st.get("pacified"):
            stabilized += 1

    max_charges = 5 if stabilized >= 36 else (4 if stabilized >= 22 else 3)
    ex = _read_session_extra_map(session_id, session=session)
    stored_day = int(ex.get("resonator_charges_day") or 0)
    used = int(ex.get("resonator_charges_used") or 0) if stored_day == int(current_day) else 0
    used = max(0, min(max_charges, used))
    return {
        "used": used,
        "max": max_charges,
        "remaining": max(0, max_charges - used),
        "stabilized_count": stabilized,
        "total_sites": len(PACIFIABLE_WILD_SITE_IDS),
    }


def build_site_map_meta(
    session_id: int,
    spec: Mapping[str, Any],
    *,
    current_minute: int = 720,
    current_day: int = 1,
    scen_key: str = "anomalous_incursions",
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
    resonator_status: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Build progressive World Map badge metadata for an anomalous site without spoiling unvisited sites."""
    site_id = str(spec["site_id"])
    site_type = str(spec.get("site_type") or "wild_facility")
    grade_r = str(spec.get("threat_grade_roman") or "I")
    grade_n = int(spec.get("threat_grade") or 1)
    elem = str(spec.get("element") or "aether").lower()
    elem_title = elem.title()
    rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
    tod = int(current_minute or 0) % 1440

    if site_type == "theme_park_night":
        if 480 <= tod < 1320:
            return {
                "site_id": site_id,
                "site_type": site_type,
                "threat_grade": grade_n,
                "threat_grade_roman": grade_r,
                "visited": True,
                "pacified": False,
                "status": "daytime_open",
                "badge": "🎡 Open (08:00–22:00)",
                "badge_tone": "emerald",
                "harvest_ready": False,
                "element_masked": False,
                "element": "",
                "domain_rule_name": "",
                "ambient_summary": "",
                "tooltip": "Public resort hours; Mirror Labyrinth & Carousel remain cordoned.",
            }
        wp = is_theme_park_witching_peak(tod)
        badge = "🩸 Nightly Anomalous Shift (Grade IV–V • Witching Peak)" if wp else "🩸 Nightly Anomalous Shift (Grade IV–V)"
        return {
            "site_id": site_id,
            "site_type": site_type,
            "threat_grade": grade_n,
            "threat_grade_roman": grade_r,
            "visited": True,
            "pacified": False,
            "status": "night_shift",
            "badge": badge,
            "badge_tone": "crimson",
            "harvest_ready": False,
            "element_masked": False,
            "element": elem,
            "domain_rule_name": str(rule.get("name") or ""),
            "ambient_summary": str(rule.get("ambient_summary") or ""),
            "tooltip": f"{rule.get('name', 'Night Shift')} — {rule.get('ambient_summary', '')}",
        }

    nodes = list(world_nodes) if world_nodes is not None else (db.get_session_world_nodes(int(session_id)) or [] if session_id else [])
    site_state = get_site_state_dict(int(session_id), site_id, world_nodes=nodes) if session_id else {}
    visited = bool(site_state.get("visited") or site_state.get("pacified"))

    if site_type == "hostile_hq":
        return {
            "site_id": site_id,
            "site_type": site_type,
            "threat_grade": grade_n,
            "threat_grade_roman": grade_r,
            "visited": visited,
            "pacified": False,
            "status": "hostile_hq",
            "badge": f"⚠️ Grade {grade_r} • Hostile Stronghold" + (f" ({elem_title})" if visited else ""),
            "badge_tone": "red",
            "harvest_ready": False,
            "element_masked": not visited,
            "element": elem if visited else "",
            "domain_rule_name": str(rule.get("name") or "") if visited else "",
            "ambient_summary": str(rule.get("ambient_summary") or "") if visited else "",
            "tooltip": (
                f"{rule.get('name', '')} — {rule.get('ambient_summary', '')}"
                if visited
                else f"Grade {grade_r} hostile stronghold. Unreconnoitered perimeter."
            ),
        }

    if is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute):
        return {
            "site_id": site_id,
            "site_type": site_type,
            "threat_grade": grade_n,
            "threat_grade_roman": grade_r,
            "visited": visited,
            "pacified": bool(site_state.get("pacified")),
            "status": "dormant",
            "badge": f"🏫 Grade {grade_r} • Daytime Dormant",
            "badge_tone": "slate",
            "harvest_ready": False,
            "element_masked": not visited,
            "element": elem if visited else "",
            "domain_rule_name": str(rule.get("name") or "") if visited else "",
            "ambient_summary": str(rule.get("ambient_summary") or "") if visited else "",
            "tooltip": "Campus phenomenon remains dormant during daylight hours.",
        }

    pacified = bool(site_state.get("pacified"))
    if pacified:
        r_stat = dict(resonator_status) if resonator_status else get_resonator_charges_status(session_id, world_nodes=nodes, current_day=current_day)
        last_h_day = int(site_state.get("last_harvest_day") or 0)
        harvest_ready = bool(int(current_day) > last_h_day and int(r_stat.get("remaining") or 0) > 0)
        badge = f"🛡️ Stabilized ({elem_title} +15%)" + (" • ✨ Harvest Ready" if harvest_ready else "")
        return {
            "site_id": site_id,
            "site_type": site_type,
            "threat_grade": grade_n,
            "threat_grade_roman": grade_r,
            "visited": True,
            "pacified": True,
            "status": "stabilized",
            "badge": badge,
            "badge_tone": "emerald",
            "harvest_ready": harvest_ready,
            "element_masked": False,
            "element": elem,
            "domain_rule_name": str(rule.get("name") or ""),
            "ambient_summary": str(rule.get("ambient_summary") or ""),
            "tooltip": str(rule.get("ambient_summary") or "Stabilized anomalous site."),
        }

    if visited:
        return {
            "site_id": site_id,
            "site_type": site_type,
            "threat_grade": grade_n,
            "threat_grade_roman": grade_r,
            "visited": True,
            "pacified": False,
            "status": "visited_uncontained",
            "badge": f"⚠️ Grade {grade_r} • Uncontained ({elem_title})",
            "badge_tone": "amber",
            "harvest_ready": False,
            "element_masked": False,
            "element": elem,
            "domain_rule_name": str(rule.get("name") or ""),
            "ambient_summary": str(rule.get("ambient_summary") or ""),
            "tooltip": f"{rule.get('name', 'Active Domain')}: {rule.get('ambient_summary', '')}",
        }

    return {
        "site_id": site_id,
        "site_type": site_type,
        "threat_grade": grade_n,
        "threat_grade_roman": grade_r,
        "visited": False,
        "pacified": False,
        "status": "unvisited_uncontained",
        "badge": f"⚠️ Grade {grade_r} • Uncontained",
        "badge_tone": "amber",
        "harvest_ready": False,
        "element_masked": True,
        "element": "",
        "domain_rule_name": "",
        "ambient_summary": "",
        "tooltip": "Unreconnoitered anomalous site. Enter to analyze its Domain Rule and elemental signature.",
    }


def build_site_registry_payload(
    session_id: int | None = None,
    lang: str = "en",
    *,
    debug_reveal_all: bool = False,
) -> dict[str, Any]:
    """
    Build the Codex `site_registry` payload tracking all 36 Pacifiable Wild Sites,
    Resonator Charges, and Reclamation Milestones (`10 / 22 / 36`).
    Unvisited sites mask Domain Rules & elements behind localized `[UNRECONNOITERED]`.
    """
    from localization import get_anomalous_site_ui_label

    eff_lang = str(lang or "en").lower().strip()[:2]
    sid = int(session_id or 0)
    nodes = db.get_session_world_nodes(sid) or [] if sid else []
    sess = db.get_session(sid) or {} if sid else {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    try:
        curr_day, curr_min, _ = db.get_session_time(sid) if sid else (1, 720, 0)
    except Exception:
        curr_day, curr_min = 1, 720

    res_stat = get_resonator_charges_status(sid, world_nodes=nodes, current_day=curr_day, session=sess)
    ex = _read_session_extra_map(sid, session=sess)
    claimed = set(int(x) for x in (ex.get("anomalous_milestones_claimed") or []) if str(x).isdigit())

    cat = load_anomalous_sites_catalog()
    unrec_tpl = get_anomalous_site_ui_label("unreconnoitered_badge", eff_lang)
    unrec_summary = get_anomalous_site_ui_label("unreconnoitered_summary", eff_lang)

    cards: list[dict[str, Any]] = []
    ordered_ids = list(cat.get("pacifiable_wild_site_ids") or sorted(PACIFIABLE_WILD_SITE_IDS))
    ordered_ids.append(THEME_PARK_SITE_ID)
    ordered_ids.extend(sorted(HOSTILE_HQ_SITE_IDS))

    for s_id in ordered_ids:
        spec = get_anomalous_site_spec(s_id)
        if not spec:
            continue
        meta = build_site_map_meta(
            sid,
            spec,
            current_minute=curr_min,
            current_day=curr_day,
            scen_key=scen_key,
            world_nodes=nodes,
            resonator_status=res_stat,
        )
        site_state = get_site_state_dict(sid, s_id, world_nodes=nodes) if sid else {}
        revealed = bool(meta.get("visited") or meta.get("pacified") or debug_reveal_all or spec.get("site_type") == "theme_park_night")
        rule = spec.get("domain_rule") if isinstance(spec.get("domain_rule"), Mapping) else {}
        cards.append({
            "site_id": s_id,
            "zone_id": str(spec.get("zone_id") or ""),
            "name": str(spec.get("name") or s_id),
            "site_type": str(spec.get("site_type") or "wild_facility"),
            "threat_grade": int(spec.get("threat_grade") or 1),
            "threat_grade_roman": str(spec.get("threat_grade_roman") or "I"),
            "horror_subgenre": str(spec.get("horror_subgenre") or "") if revealed else unrec_tpl.replace("{grade}", str(spec.get("threat_grade_roman") or "I")),
            "visited": bool(meta.get("visited")),
            "pacified": bool(meta.get("pacified")),
            "status": meta["status"],
            "badge": meta["badge"],
            "badge_tone": meta["badge_tone"],
            "harvest_ready": bool(meta.get("harvest_ready")),
            "puzzle_step": int(site_state.get("puzzle_step") or 0),
            "instability": int(site_state.get("instability") or 0),
            "element": str(spec.get("element") or "aether") if revealed else "???",
            "domain_rule_name": str(rule.get("name") or "") if revealed else unrec_tpl.replace("{grade}", str(spec.get("threat_grade_roman") or "I")),
            "ambient_summary": str(rule.get("ambient_summary") or "") if revealed else unrec_summary,
        })

    stab = int(res_stat["stabilized_count"])
    total = int(res_stat["total_sites"])
    milestones = [
        {
            "threshold": 10,
            "title": get_anomalous_site_ui_label("milestone_10_title", eff_lang),
            "reward": get_anomalous_site_ui_label("milestone_10_reward", eff_lang),
            "unlocked": stab >= 10,
            "claimed": 10 in claimed,
        },
        {
            "threshold": 22,
            "title": get_anomalous_site_ui_label("milestone_22_title", eff_lang),
            "reward": get_anomalous_site_ui_label("milestone_22_reward", eff_lang),
            "unlocked": stab >= 22,
            "claimed": 22 in claimed,
        },
        {
            "threshold": total,
            "title": get_anomalous_site_ui_label("milestone_36_title", eff_lang),
            "reward": get_anomalous_site_ui_label("milestone_36_reward", eff_lang),
            "unlocked": stab >= total,
            "claimed": total in claimed,
        },
    ]

    return {
        "stabilized_count": stab,
        "total_sites": total,
        "resonator_charges_used": int(res_stat["used"]),
        "resonator_charges_max": int(res_stat["max"]),
        "resonator_charges_remaining": int(res_stat["remaining"]),
        "milestones": milestones,
        "sites": cards,
    }
