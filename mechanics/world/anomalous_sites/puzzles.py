from __future__ import annotations

import hashlib
import random
import re
from typing import Any, Iterable, Mapping

import db
from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag
from mechanics.world.anomalous_sites.catalog import (
    get_anomalous_site_spec,
    get_site_state_dict,
    is_site_dormant_by_schedule,
    mutate_anomalous_site_state,
    resolve_anomalous_site,
)
from mechanics.world.anomalous_sites.domain_rules import PASSIVE_WARD_KEYWORDS
from mechanics.world.anomalous_sites.harvest import complete_site_pacification
from mechanics.world.anomalous_sites.lifecycle import lazy_midnight_reknit_site
from mechanics.world.anomaly_engine import (
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
)

PUZZLE_INTERACTION_VERBS: tuple[str, ...] = (
    "inspect", "examine", "search", "pry", "sever", "cut", "slash", "burn",
    "torch", "salt", "purify", "align", "tune", "smash", "break", "seal",
    "lock", "attune", "activate", "pull", "press", "tie", "bind", "ground",
    "drain", "wipe", "unlock", "shut", "close", "unplug", "jam", "drop",
    "wedge", "clamp", "scatter", "cover", "shroud", "silence", "reset", "ring",
)

_STAT_COL_MAP = {
    "STR": "str_",
    "PER": "per_",
    "END": "end_",
    "CHA": "cha",
    "INT": "int_",
    "AGI": "agi",
    "LUK": "luk",
    "TECH": "int_",
    "WIL": "end_",
    "WIS": "per_",
}

_CANON_UI_STAT_MAP = {
    "TECH": "INT",
    "WIL": "END",
    "WIS": "PER",
}


def _stable_seed(seed_str: str) -> int:
    digest = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _resolve_char_stat(char: Mapping[str, Any] | None, stat_key: str) -> int:
    if not isinstance(char, Mapping):
        return 5
    s_up = str(stat_key or "PER").upper()
    stats = char.get("stats")
    if isinstance(stats, Mapping):
        if s_up in stats:
            return int(stats.get(s_up) or 5)
        if s_up == "TECH" and "INT" in stats:
            return int(stats.get("INT") or 5)
        if s_up == "WIS" and "PER" in stats:
            return int(stats.get("PER") or 5)
        if s_up == "WIL":
            return max(int(stats.get("END", 0) or 0), int(stats.get("INT", 0) or 0), int(stats.get("CHA", 0) or 0)) or 5
    col = _STAT_COL_MAP.get(s_up, "per_")
    return int(char.get(col, 5) or 5)


def get_site_puzzle_plan(session_id: int, site_id: str) -> dict[str, Any] | None:
    """
    Deterministically select the 3-step room/prop variants and base culmination roll
    for `(session_id, site_id)`.
    """
    spec = get_anomalous_site_spec(site_id)
    if not spec or not isinstance(spec.get("puzzle_spec"), Mapping):
        return None
    ps = spec["puzzle_spec"]
    rng = random.Random(_stable_seed(f"{session_id}:{spec['site_id']}:site_puzzle"))
    selected_steps: list[dict[str, Any]] = []
    anchors = list(ps.get("anchors") or [])
    for idx, step_block in enumerate(ps.get("steps") or ()):
        variants = list(step_block.get("variants") or ())
        if not variants:
            continue
        chosen_var = dict(rng.choice(variants))
        chosen_var["step_index"] = idx
        chosen_var["anchor"] = anchors[idx] if idx < len(anchors) else spec["site_id"]
        selected_steps.append(chosen_var)

    boss_weight = float(ps.get("culmination_boss_weight") or (0.75 if int(spec.get("threat_grade") or 1) >= 5 else 0.50))
    return {
        "site_id": spec["site_id"],
        "anchor_mode": str(ps.get("anchor_mode") or "rooms"),
        "steps": selected_steps,
        "culmination_boss_default": rng.random() < boss_weight,
        "boss_profile": dict(ps.get("boss_profile") or {}),
    }


def has_quest_or_breach_priority_at_node(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
) -> bool:
    """Return True if an active Quest waypoint or Daily Breach currently owns this node."""
    if not session_id:
        return False
    try:
        from mechanics.world.anomalous_events import get_active_incursion_at_location
        if get_active_incursion_at_location(int(session_id), location_str=location_str, node_id=node_id):
            return True
    except Exception:
        pass
    try:
        from mechanics.world.waypoints import check_location_matches_waypoint
        wps = db.get_all_session_active_waypoints(int(session_id)) or []
        for wp in wps:
            if not isinstance(wp, Mapping):
                continue
            wp_nid = str(wp.get("target_node_id") or "").strip().lower()
            wp_loc = str(wp.get("target_location") or "").strip()
            if node_id and wp_nid and wp_nid == str(node_id).strip().lower():
                return True
            if location_str and wp_loc and check_location_matches_waypoint(location_str, wp_loc):
                return True
    except Exception:
        pass
    return False


def detect_companion_assist(
    session_id: int,
    session: Mapping[str, Any] | None,
    check_stat: str,
    site_element: str,
) -> dict[str, Any]:
    """
    Check active companions (`party_npcs` + `temporary_companions`) for a Special Agent
    or Folklore Villager with matching high stat (`>= 5`) or site element (`+2` bonus).
    """
    if not isinstance(session, Mapping):
        return {"bonus": 0, "helper_name": ""}
    stat_up = str(check_stat or "PER").upper()
    elem_low = str(site_element or "").lower()
    scen_key = str(session.get("scenario") or "anomalous_incursions")

    pool: list[Any] = []
    pool.extend(session.get("party_npcs") or ())
    pool.extend(session.get("temporary_companions") or ())

    for comp in pool:
        if isinstance(comp, str):
            c_name = comp.strip()
            c_dict: Mapping[str, Any] = {"name": c_name}
        elif isinstance(comp, Mapping):
            c_name = str(comp.get("name") or "").strip()
            c_dict = comp
        else:
            continue
        if not c_name:
            continue
        tag = classify_anomalous_npc_tag(c_name, session_id=int(session_id or 0), scen_key=scen_key)
        if tag == "civilian":
            continue
        c_elem = str(c_dict.get("primary_element") or c_dict.get("element") or "").lower()
        c_stat_val = _resolve_char_stat(c_dict, stat_up)
        # Check stored stats or explicit element match; agents/villagers with matching stat >= 5 or element grant +2
        if c_stat_val >= 5 or (elem_low and c_elem == elem_low):
            return {"bonus": 2, "helper_name": c_name}
    return {"bonus": 0, "helper_name": ""}


def detect_ward_or_flare_in_inventory(
    inventory: Iterable[Any] | None,
    explicit_name: str = "",
) -> dict[str, Any] | None:
    """Find a consumable ward/talisman/signal flare item eligible for `+3` + Instability shield."""
    exp_low = str(explicit_name or "").strip().lower()
    for itm in (inventory or ()):
        if not isinstance(itm, Mapping):
            continue
        nm = str(itm.get("name") or "").strip()
        qty = int(itm.get("quantity", 1) or 1)
        if not nm or qty <= 0:
            continue
        nm_low = nm.lower()
        if exp_low and exp_low in nm_low:
            return dict(itm)
        if any(kw in nm_low for kw in PASSIVE_WARD_KEYWORDS):
            return dict(itm)
    return None


def build_site_puzzle_choices(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
    *,
    scen_key: str = "anomalous_incursions",
    current_day: int = 1,
    current_minute: int = 720,
    inventory: Iterable[Any] | None = None,
    has_priority_event: bool | None = None,
    session: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate `[🧩 Step X/3]` (and `[🧿 Use Ward + Step X/3]`) exploration choices
    when inside the active anchor room of an un-pacified wild site, or a `FREE`
    navigation choice to advance to the current step's anchor room from another
    room within the same facility.
    """
    if not session_id:
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
    if is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=eff_nid):
        return []

    site_id = str(spec["site_id"])
    prio = has_quest_or_breach_priority_at_node(int(session_id), location_str, eff_nid) if has_priority_event is None else bool(has_priority_event)
    if prio:
        return []

    st = lazy_midnight_reknit_site(int(session_id), site_id, int(current_day), world_nodes=nodes, persist_db=True)
    if st.get("pacified"):
        return []
    if int(st.get("jammed_until_day") or 0) > int(current_day):
        return []

    step_idx = max(0, min(2, int(st.get("puzzle_step") or 0)))
    plan = get_site_puzzle_plan(int(session_id), site_id)
    if not plan or step_idx >= len(plan["steps"]):
        return []
    cur_var = plan["steps"][step_idx]
    anchor_mode = plan["anchor_mode"]
    expected_anchor = str(cur_var.get("anchor") or "").lower()
    nid_low = eff_nid.lower()
    site_sub_lows = {str(s).lower() for s in (spec.get("sub_ids") or ())}

    if anchor_mode == "rooms" and expected_anchor and nid_low != expected_anchor:
        if nid_low == site_id.lower() or nid_low in site_sub_lows:
            anchor_node = next(
                (n for n in nodes if isinstance(n, Mapping) and str(n.get("node_id") or "").lower() == expected_anchor),
                None,
            )
            if anchor_node:
                anchor_nid = str(anchor_node["node_id"])
                try:
                    full_loc = db.format_node_tiered_location(int(session_id), anchor_nid) or str(anchor_node.get("name") or expected_anchor)
                except Exception:
                    full_loc = str(anchor_node.get("name") or expected_anchor)
                return [{
                    "label": f"🧭 Advance to Anomaly Anchor: {anchor_node.get('name', expected_anchor)} (Step {step_idx + 1}/3)",
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "fast_travel",
                    "action_category": "movement",
                    "target_node_id": anchor_nid,
                    "target_location": full_loc,
                }]
        return []
    if anchor_mode == "props" and nid_low != site_id.lower() and nid_low not in site_sub_lows:
        return []

    dc = 8 + int(spec.get("threat_grade") or 1) * 2
    raw_primary_stat = str((cur_var.get("stat_options") or ["PER"])[0]).upper()
    primary_stat = _CANON_UI_STAT_MAP.get(raw_primary_stat, raw_primary_stat)
    sess_obj = session if isinstance(session, Mapping) else (db.get_session(int(session_id)) or {})
    comp_assist = detect_companion_assist(int(session_id), sess_obj, primary_stat, str(spec.get("element") or ""))
    comp_bonus = int(comp_assist.get("bonus") or 0)
    eff_base_dc = max(3, dc - comp_bonus)

    choices = [
        {
            "label": f"🧩 Step {step_idx + 1}/3 — {cur_var['label']}",
            "stat": primary_stat,
            "requirement": eff_base_dc,
            "mp_cost": 0,
            "intent": "anomalous_site_action",
            "site_action": "puzzle_step",
            "site_id": site_id,
            "step_index": step_idx,
            "use_ward": False,
        }
    ]
    ward_itm = detect_ward_or_flare_in_inventory(inventory)
    if ward_itm:
        choices.append({
            "label": f"🧿 Use {ward_itm['name']} + Step {step_idx + 1}/3 — {cur_var['label']}",
            "stat": primary_stat,
            "requirement": max(3, eff_base_dc - 3),
            "mp_cost": 0,
            "intent": "anomalous_site_action",
            "site_action": "puzzle_step",
            "site_id": site_id,
            "step_index": step_idx,
            "use_ward": True,
            "ward_item_name": ward_itm["name"],
        })
    return choices


def match_freeform_puzzle_action(
    session_id: int,
    custom_text: str,
    location_str: str = "",
    node_id: str = "",
    *,
    scen_key: str = "anomalous_incursions",
    current_day: int = 1,
    current_minute: int = 720,
    inventory: Iterable[Any] | None = None,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Match freeform typed player action against active step `prop_keywords` + interaction verbs,
    honoring any plausible player-chosen stat or Ward/Flare invocation.
    """
    txt_low = str(custom_text or "").strip().lower()
    if not session_id or not txt_low:
        return None
    eff_nid = str(node_id or "").strip()
    if not eff_nid and location_str:
        try:
            eff_nid = str(db.resolve_node_id_from_location(int(session_id), location_str, prefer_facility=False) or "").strip()
        except Exception:
            eff_nid = ""
    if has_quest_or_breach_priority_at_node(int(session_id), location_str, eff_nid):
        return None

    nodes = db.get_session_world_nodes(int(session_id)) or []
    spec = resolve_anomalous_site(node_id=eff_nid, location_str=location_str, session_nodes=nodes)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return None
    if is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=eff_nid):
        return None

    site_id = str(spec["site_id"])
    st = get_site_state_dict(int(session_id), site_id, world_nodes=nodes)
    if st.get("pacified") or int(st.get("jammed_until_day") or 0) > int(current_day):
        return None

    step_idx = max(0, min(2, int(st.get("puzzle_step") or 0)))
    plan = get_site_puzzle_plan(int(session_id), site_id)
    if not plan or step_idx >= len(plan["steps"]):
        return None
    cur_var = plan["steps"][step_idx]
    expected_anchor = str(cur_var.get("anchor") or "").lower()
    nid_low = eff_nid.lower()
    site_sub_lows = {str(s).lower() for s in (spec.get("sub_ids") or ())}
    if plan["anchor_mode"] == "rooms" and expected_anchor and nid_low != expected_anchor:
        return None
    if plan["anchor_mode"] == "props" and nid_low != site_id.lower() and nid_low not in site_sub_lows:
        return None

    prop_kws = [str(k).lower() for k in (cur_var.get("prop_keywords") or ())]
    has_prop = any(kw in txt_low for kw in prop_kws)
    has_verb = any(re.search(rf"\b{re.escape(v)}\b", txt_low) for v in PUZZLE_INTERACTION_VERBS) or (cur_var.get("verb", "").lower() in txt_low)
    if not (has_prop and has_verb):
        return None

    # Infer plausible player stat cleanly (map TECH/WIL/WIS aliases to canonical TurnService/STAT_COLUMN keys)
    stat_opts = [str(s).upper() for s in (cur_var.get("stat_options") or ["PER"])]
    chosen_stat = stat_opts[0]
    if any(w in txt_low for w in ("smash", "wrench", "force", "break", "heave", "pry")):
        chosen_stat = "STR"
    elif any(w in txt_low for w in ("rewire", "bypass", "decode", "analyze", "compute", "burn")):
        chosen_stat = "INT"
    elif any(w in txt_low for w in ("slip", "snatch", "dodge", "slash", "cut", "sever")):
        chosen_stat = "AGI"
    elif any(w in txt_low for w in ("salt", "ward", "attune", "banish", "chant", "calm")):
        chosen_stat = "CHA" if "CHA" in stat_opts else "END"
    chosen_stat = _CANON_UI_STAT_MAP.get(chosen_stat, chosen_stat)

    ward_itm = detect_ward_or_flare_in_inventory(inventory) if any(
        w in txt_low for w in ("salt", "charm", "flare", "talisman", "bell", "serunai", "rampai", "ward")
    ) else None

    dc = 8 + int(spec.get("threat_grade") or 1) * 2
    sess_obj = session if isinstance(session, Mapping) else (db.get_session(int(session_id)) or {})
    comp_assist = detect_companion_assist(int(session_id), sess_obj, chosen_stat, str(spec.get("element") or ""))
    comp_bonus = int(comp_assist.get("bonus") or 0)
    eff_req = max(3, dc - comp_bonus - (3 if ward_itm else 0))

    return {
        "label": str(custom_text).strip(),
        "text": str(custom_text).strip(),
        "stat": chosen_stat,
        "requirement": eff_req,
        "mp_cost": 0,
        "intent": "anomalous_site_action",
        "site_action": "puzzle_step",
        "site_id": site_id,
        "step_index": step_idx,
        "use_ward": bool(ward_itm),
        "ward_item_name": ward_itm["name"] if ward_itm else "",
        "_verified_ambient_intent": True,
    }


def resolve_anomalous_site_puzzle_step(
    session_id: int,
    user_id: int,
    site_id: str,
    step_index: int | None = None,
    *,
    stat_used: str = "",
    pre_rolled_check: Any = None,
    force_roll: int | None = None,
    use_ward: bool = False,
    ward_item_name: str = "",
    force_culmination_boss: bool | None = None,
    session: dict[str, Any] | None = None,
    party: list[Any] | None = None,
    scen_key: str = "anomalous_incursions",
    turn_number: int = 0,
) -> dict[str, Any]:
    """
    Resolve one step of a 3-step Anomalous Site Stabilization Puzzle:
    - Applies +2 Companion Assist & +3 Ward/Flare bonus (+ Instability shield on fail).
    - On Step 3 pass: resolves either Ritual Nullification OR Locus Boss Awakening.
    - On Fail: deals Grade trauma (floored at 1 HP) & climbs Instability 0 -> 3.
    """
    spec = get_anomalous_site_spec(site_id)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return {"success": False, "error": "No stabilization puzzle at this location."}

    canon_id = str(spec["site_id"])
    sess = session if isinstance(session, dict) else (db.get_session(int(session_id)) or {})
    eff_scen = str(scen_key or sess.get("scenario") or "anomalous_incursions")
    try:
        curr_day, curr_min, _ = db.get_session_time(int(session_id))
    except Exception:
        curr_day, curr_min = 1, 720

    nodes = db.get_session_world_nodes(int(session_id)) or []
    st = lazy_midnight_reknit_site(int(session_id), canon_id, int(curr_day), turn_number=int(turn_number), world_nodes=nodes, persist_db=True)
    if st.get("pacified"):
        return {"success": True, "resolved": True, "already_pacified": True, "pacified": True, "message": f"**{spec['name']}** is already stabilized."}
    if int(st.get("jammed_until_day") or 0) > int(curr_day):
        return {"success": False, "resolved": False, "jammed": True, "message": f"⚠️ **{spec['name']}**'s resonance anchor is jammed until tomorrow."}

    cur_step = max(0, min(2, int(st.get("puzzle_step") or 0) if step_index is None else int(step_index)))
    plan = get_site_puzzle_plan(int(session_id), canon_id)
    if not plan or cur_step >= len(plan["steps"]):
        return {"success": False, "error": "Puzzle plan unavailable."}
    var = plan["steps"][cur_step]

    grade = int(spec.get("threat_grade") or 1)
    dc = 8 + grade * 2
    eff_stat = str(stat_used or (var.get("stat_options") or ["PER"])[0]).upper()
    char = db.get_character(int(user_id)) if user_id else {}
    if party and isinstance(party[0], (tuple, list)) and isinstance(party[0][0], dict):
        char = party[0][0]
    inv = db.get_inventory(int(user_id)) if user_id else []

    comp_assist = detect_companion_assist(int(session_id), sess, eff_stat, str(spec.get("element") or ""))
    comp_bonus = int(comp_assist["bonus"] or 0)

    ward_bonus = 0
    block_instability = False
    consumed_ward_name = ""
    if use_ward or ward_item_name:
        ward_itm = detect_ward_or_flare_in_inventory(inv, explicit_name=ward_item_name)
        if ward_itm:
            ward_bonus = 3
            block_instability = True
            consumed_ward_name = str(ward_itm["name"])
            if user_id:
                try:
                    db.remove_item(int(user_id), consumed_ward_name, 1)
                except Exception:
                    pass

    stat_val = _resolve_char_stat(char, eff_stat)
    if force_roll is not None:
        nat_roll = int(force_roll)
        total = nat_roll + stat_val + comp_bonus + ward_bonus
        succeeded = (nat_roll > 1) and (nat_roll == 20 or total >= dc)
        tier_str = "crit_success" if (nat_roll == 20 or (succeeded and total >= dc + 5)) else ("success" if succeeded else "fail")
    elif pre_rolled_check is not None:
        from skill_check import is_check_success as _chk_ok, success_chance as _sc_pct
        succeeded = bool(_chk_ok(pre_rolled_check, default_if_none=False))
        tier_str = str(getattr(pre_rolled_check, "tier", "") or (pre_rolled_check.get("tier") if isinstance(pre_rolled_check, Mapping) else "") or ("success" if succeeded else "fail"))
        eff_dc = max(3, dc - comp_bonus - ward_bonus)
        rolled_req = int(
            getattr(pre_rolled_check, "requirement", eff_dc)
            if not isinstance(pre_rolled_check, Mapping)
            else (pre_rolled_check.get("requirement") or eff_dc)
        )
        raw_roll = float(
            getattr(pre_rolled_check, "roll", 100.0)
            if not isinstance(pre_rolled_check, Mapping)
            else (pre_rolled_check.get("roll") if pre_rolled_check.get("roll") is not None else 100.0)
        )
        # Re-evaluate against lowered DC if TurnService rolled pre_rolled_check before bonuses
        if not succeeded and tier_str != "crit_fail" and (comp_bonus + ward_bonus) > 0 and rolled_req > eff_dc:
            if raw_roll <= float(_sc_pct(stat_val, eff_dc)):
                succeeded = True
                tier_str = "success"
    else:
        from skill_check import resolve_check as _res_chk
        eff_dc = max(3, dc - comp_bonus - ward_bonus)
        luk_val = int((char or {}).get("luk", 3) or 3)
        _chk = _res_chk(stat_val, eff_dc, luk_val)
        succeeded = bool(_chk.succeeded)
        tier_str = str(_chk.tier or ("success" if succeeded else "fail"))

    is_crit = succeeded and tier_str == "crit_success"
    assist_note = f" *(+{comp_bonus} {comp_assist['helper_name']} Assist)*" if comp_bonus else ""
    ward_note = f" *(+{ward_bonus} `{consumed_ward_name}`)*" if ward_bonus else ""

    if succeeded:
        next_step = cur_step + 1
        dossier_rev = bool(st.get("boss_dossier_revealed") or is_crit)
        if next_step < 3:
            mutate_anomalous_site_state(
                int(session_id),
                canon_id,
                int(turn_number),
                {
                    "visited": True,
                    "puzzle_step": next_step,
                    "puzzle_day": int(curr_day),
                    "boss_dossier_revealed": dossier_rev,
                },
                world_nodes=nodes,
            )
            next_var = plan["steps"][next_step]
            crit_note = " *(Critical breakthrough pre-exposed Locus Boss weaknesses!)*" if is_crit else ""
            msg = (
                f"🧩 **Step {cur_step + 1}/3 Cleared** at {spec['name']}{assist_note}{ward_note}: "
                f"{var['success_prose']}{crit_note}"
            )
            directive = (
                f"[SITE PUZZLE STEP {cur_step + 1}/3 SUCCESS]: {var['success_prose']} "
                f"Subtle clue points onward: {next_var['clue_text']} "
                "Narrate cleanly without raw stats, DCs, or JSON tags."
            )
            return {
                "success": True,
                "resolved": False,
                "combat_started": False,
                "puzzle_step": next_step,
                "boss_dossier_revealed": dossier_rev,
                "companion_assist": comp_assist,
                "message": msg,
                "directive": directive,
            }

        # Step 3 Culmination: Boss Forced / Default Roll vs Ritual Nullification
        spawn_boss = (
            bool(force_culmination_boss)
            if force_culmination_boss is not None
            else (bool(st.get("boss_forced")) or bool(plan.get("culmination_boss_default")))
        )
        if not spawn_boss:
            pac_res = complete_site_pacification(
                int(session_id),
                canon_id,
                int(user_id or 1),
                method="ritual_nullification",
                scen_key=eff_scen,
                current_day=int(curr_day),
                turn_number=int(turn_number),
            )
            pac_res["puzzle_step"] = 3
            return pac_res

        # Spawn Locus Boss via AnomalyBlueprint
        empowered = bool(st.get("boss_forced"))
        bp_prof = plan.get("boss_profile") or {}
        eff_tier = min(5, grade + (1 if empowered and grade < 5 else 0))
        bp = generate_anomaly_blueprint(
            session_id=int(session_id),
            seed_key=f"locus_boss:{canon_id}:{session_id}",
            scenario=eff_scen,
            location=str(sess.get("current_location") or spec["name"]),
            current_minute=curr_min,
            force_disposition="hostile",
            force_element=str(spec.get("element") or "aether"),
            tier=eff_tier,
        )
        if bp_prof.get("sapience"):
            bp["sapience"] = str(bp_prof["sapience"])
        if bp_prof.get("title_epithet"):
            bp["title_epithet"] = str(bp_prof["title_epithet"])
        boss = instantiate_enemy_from_blueprint(bp, tier=eff_tier)
        boss["is_site_locus_boss"] = True
        boss["anomalous_site_id"] = canon_id
        boss["is_anomalous_manifestation"] = True
        if dossier_rev:
            boss["dossier_revealed"] = True
        if empowered:
            boss["empowered_locus_boss"] = True
            boss["max_hp"] = int(round(int(boss.get("max_hp", 40) or 40) * 1.25))
            boss["hp"] = boss["max_hp"]

        mutate_anomalous_site_state(
            int(session_id),
            canon_id,
            int(turn_number),
            {"visited": True, "puzzle_step": 3, "puzzle_day": int(curr_day), "boss_dossier_revealed": dossier_rev},
            world_nodes=nodes,
        )
        enemies_now = list(sess.get("nearby_enemies") or [])
        enemies_now.append(boss)
        db.update_session(int(session_id), nearby_enemies=enemies_now)
        sess["nearby_enemies"] = enemies_now

        emp_note = " *(Empowered by Instability Spike!)*" if empowered else ""
        msg = (
            f"💀 **LOCUS BOSS AWAKENED — {boss['name']}!**{emp_note} "
            f"Final containment cracked open the site's core manifestation — defeat, Live-Capture, or Pact-Bind it at <=15% HP to stabilize **{spec['name']}**!"
        )
        directive = (
            f"[SITE LOCUS BOSS AWAKENING]: At the final step in {spec['name']}, the Locus Anomaly **{boss['name']}** materializes into battle! "
            "Dramatically set the stage for confrontation without resolving combat this turn or leaking HP/DC numbers."
        )
        return {
            "success": True,
            "resolved": False,
            "combat_started": True,
            "puzzle_step": 3,
            "locus_boss": boss,
            "empowered": empowered,
            "message": msg,
            "directive": directive,
        }

    # FAILURE PATH: Grade trauma floored at 1 HP + Instability ladder (0 -> 3)
    hp_loss = 4 + grade * 2
    mp_loss = 3 + grade
    if isinstance(char, dict):
        cur_hp = int(char.get("hp", 20) or 20)
        cur_mp = int(char.get("mp", 10) or 10)
        actual_hp = min(hp_loss, max(0, cur_hp - 1))
        actual_mp = min(mp_loss, max(0, cur_mp))
        char["hp"] = cur_hp - actual_hp
        char["mp"] = cur_mp - actual_mp
        if user_id and (actual_hp > 0 or actual_mp > 0):
            db.update_character_fields(int(user_id), hp=int(char["hp"]), mp=int(char["mp"]))

    cur_inst = int(st.get("instability") or 0)
    new_inst = cur_inst if block_instability else (cur_inst + 1)
    apex_ambush = None

    if new_inst >= 3:
        apex_tier = min(5, grade + 1)
        bp_apex = generate_anomaly_blueprint(
            session_id=int(session_id),
            seed_key=f"apex_breach:{canon_id}:{curr_day}:{turn_number}",
            scenario=eff_scen,
            location=str(sess.get("current_location") or spec["name"]),
            current_minute=curr_min,
            force_disposition="hostile",
            force_element=str(spec.get("element") or "aether"),
            tier=apex_tier,
        )
        apex_ambush = instantiate_enemy_from_blueprint(bp_apex, tier=apex_tier)
        apex_ambush["is_apex_breach_ambush"] = True
        apex_ambush["anomalous_site_id"] = canon_id
        enemies_now = list(sess.get("nearby_enemies") or [])
        enemies_now.append(apex_ambush)
        db.update_session(int(session_id), nearby_enemies=enemies_now)
        sess["nearby_enemies"] = enemies_now

        mutate_anomalous_site_state(
            int(session_id),
            canon_id,
            int(turn_number),
            {
                "visited": True,
                "puzzle_step": 0,
                "instability": 0,
                "boss_forced": False,
                "jammed_until_day": int(curr_day) + 1,
                "puzzle_day": int(curr_day),
            },
            world_nodes=nodes,
        )
        final_inst = 0
        jammed = True
    else:
        boss_forced_now = bool(st.get("boss_forced") or (new_inst >= 2))
        mutate_anomalous_site_state(
            int(session_id),
            canon_id,
            int(turn_number),
            {
                "visited": True,
                "instability": new_inst,
                "boss_forced": boss_forced_now,
                "puzzle_day": int(curr_day),
            },
            world_nodes=nodes,
        )
        final_inst = new_inst
        jammed = False

    shield_note = f" *(Instability shielded by `{consumed_ward_name}`!)*" if block_instability else ""
    inst_note = (
        f" 💥 **INSTABILITY CRITICAL (3/3):** Apex Breach Ambush (**{apex_ambush['name']}**) erupts and site anchors jam until tomorrow!"
        if apex_ambush
        else (f" Instability escalated to {final_inst}/3!" if not block_instability else "")
    )
    return {
        "success": False,
        "resolved": False,
        "combat_started": bool(apex_ambush),
        "composure_shift": "shaken",
        "puzzle_step": 0 if apex_ambush else cur_step,
        "instability": final_inst,
        "boss_forced": bool(final_inst >= 2),
        "jammed": jammed,
        "apex_ambush": apex_ambush,
        "message": f"⚠️ **Anchor Backlash (Step {cur_step + 1}/3 Failed)**{ward_note}: {var['backlash_prose']}{inst_note}",
        "directive": (
            f"[SITE PUZZLE BACKLASH]: {var['backlash_prose']} "
            + (f"An Apex Manifestation (**{apex_ambush['name']}**) tears through the room, forcing combat! " if apex_ambush else "")
            + "Narrate this setback vividly with shaken composure and zero raw HP/MP/DC integers."
        ),
    }
