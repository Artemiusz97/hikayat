"""
Realm-Scoped Veiled Spirit World Events & Live Gameplay Hooks.

Provides cohesive query helpers and event-spawn / combat / rest / toll / Bazaar
modifiers strictly scoped to `realm_veiled_spirit_world` (`VEILED_SPIRIT_EVENT_KEYS`):
- Dusk Confluence Bazaar: `evt_spirit_twin_moon_fair`, `evt_spirit_midnight_curio_auction`,
  `evt_spirit_drifting_lanterns`
- Enclave Ceremonies: `evt_spirit_kagura_revelry`, `evt_spirit_malam_berinai_feast`,
  `evt_spirit_pale_wake`
- Frontier Crises: `evt_spirit_neon_static_surge`, `evt_spirit_cold_iron_raid`,
  `evt_spirit_feral_ghul_hunt`
"""
from __future__ import annotations

import json
import re
from contextlib import nullcontext
from typing import Any, Mapping, Sequence

import db

SPIRIT_REALM_ID = "realm_veiled_spirit_world"

VEILED_SPIRIT_EVENT_KEYS: frozenset[str] = frozenset({
    "evt_spirit_twin_moon_fair",
    "evt_spirit_midnight_curio_auction",
    "evt_spirit_drifting_lanterns",
    "evt_spirit_kagura_revelry",
    "evt_spirit_malam_berinai_feast",
    "evt_spirit_pale_wake",
    "evt_spirit_neon_static_surge",
    "evt_spirit_cold_iron_raid",
    "evt_spirit_feral_ghul_hunt",
})

VEILED_ENCLAVE_EVENT_VILLAGE: dict[str, str] = {
    "evt_spirit_kagura_revelry": "kitsune",
    "evt_spirit_malam_berinai_feast": "bunian",
    "evt_spirit_pale_wake": "ghoul",
}

VEILED_ZONE_NODE_PREFIXES: dict[str, tuple[str, ...]] = {
    "zone_spirit_crossroads": ("zone_spirit_crossroads", "loc_crossroads_", "sub_crossroads_"),
    "zone_spirit_kitsune": ("zone_spirit_kitsune", "loc_hidden_kitsune_village", "loc_kitsune_", "fac_kitsune_", "sub_kitsune_"),
    "zone_spirit_bunian": ("zone_spirit_bunian", "loc_hidden_bunian_village", "loc_bunian_", "fac_bunian_", "sub_bunian_"),
    "zone_spirit_ghoul": ("zone_spirit_ghoul", "loc_hidden_ghoul_village", "loc_ghoul_", "fac_ghoul_", "sub_ghoul_"),
    "zone_spirit_wilds": ("zone_spirit_wilds", "loc_wilds_", "sub_wilds_"),
    "zone_spirit_peaks": ("zone_spirit_peaks", "loc_peaks_", "sub_peaks_"),
    "zone_spirit_mire": ("zone_spirit_mire", "loc_mire_", "sub_mire_"),
    "zone_spirit_boneyard": ("zone_spirit_boneyard", "loc_boneyard_", "sub_boneyard_"),
}

_FALLBACK_STATIC_NOTE = "⚡ Neon-Static Leyline Surge: Spirit Relay signals crackle with astral static."


def _parse_json_obj(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def node_matches_spirit_event_zones(target_node_id: str, allowed_zone_ids: Sequence[str]) -> bool:
    """Returns True when `target_node_id` sits inside any zone in `allowed_zone_ids`."""
    tgt = str(target_node_id or "").strip().lower()
    if not tgt or not allowed_zone_ids:
        return False
    for zid in allowed_zone_ids:
        z_low = str(zid or "").strip().lower()
        if not z_low:
            continue
        prefixes = VEILED_ZONE_NODE_PREFIXES.get(z_low, (z_low,))
        if any(tgt == p or tgt.startswith(p) for p in prefixes):
            return True
    return False


def infer_spirit_zone_for_node(node_id: str) -> str:
    """Returns canonical `zone_spirit_*` zone_id for a facility/room node inside `realm_veiled_spirit_world`, else `''`."""
    tgt = str(node_id or "").strip().lower()
    if not tgt:
        return ""
    for zid, prefixes in VEILED_ZONE_NODE_PREFIXES.items():
        if any(tgt == p or tgt.startswith(p) for p in prefixes):
            return zid
    return ""


def get_active_spirit_events(
    session_id: int,
    template_keys: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Lists currently active Veiled Spirit World macro events for `session_id`."""
    if not session_id:
        return []
    wanted = {str(k).strip() for k in template_keys if k} if template_keys else VEILED_SPIRIT_EVENT_KEYS
    rows = db.get_world_events(int(session_id), entity_type="macro_event", include_hidden=True, statuses=("active",)) or []
    return [dict(r) for r in rows if str(r.get("template_key") or "") in wanted]


def has_active_spirit_event(session_id: int, template_key: str) -> bool:
    """Returns True if `template_key` is an active macro event in `session_id`."""
    return bool(get_active_spirit_events(session_id, template_keys=(template_key,)))


def is_ferryman_toll_waived(session_id: int) -> bool:
    """Returns True when `evt_spirit_drifting_lanterns` waives the 50g Spirit Ferryman fee."""
    return has_active_spirit_event(session_id, "evt_spirit_drifting_lanterns")


def is_ghoul_entry_toll_waived(session_id: int) -> bool:
    """Returns True when `evt_spirit_pale_wake` temporarily waives the Ghoul Distrusted 35g entry toll."""
    return has_active_spirit_event(session_id, "evt_spirit_pale_wake")


def is_spirit_relay_static_active(session_id: int) -> bool:
    """Returns True when `evt_spirit_neon_static_surge` causes Spirit Relay static interference."""
    return has_active_spirit_event(session_id, "evt_spirit_neon_static_surge")


def get_spirit_relay_static_note(session_id: int, lang: str = "en") -> str:
    """Returns localized static interference flavor note for Phone Spirit Relay during Neon-Static Surge."""
    if not is_spirit_relay_static_active(session_id):
        return ""
    try:
        import localization
        getter = getattr(localization, "get_spirit_court_label", None)
        if callable(getter):
            lbl = str(getter("spirit_relay_neon_static_note", lang) or "").strip()
            if lbl and lbl != "spirit_relay_neon_static_note":
                return lbl
    except Exception:
        pass
    return _FALLBACK_STATIC_NOTE


def get_spirit_event_sparring_bonuses(session_id: int, village_key: str) -> tuple[int, int]:
    """Returns `(bonus_xp, bonus_rep)` for enclave sparring drills (`+15 XP`, `+2 rep` during Kagura Revelry)."""
    if str(village_key or "").strip().lower() == "kitsune" and has_active_spirit_event(session_id, "evt_spirit_kagura_revelry"):
        return 15, 2
    return 0, 0


def get_spirit_event_rep_bonus(session_id: int, village_key: str) -> int:
    """Returns flat event reputation bonus on positive gains (`+2` Kitsune Kagura / `+2` Bunian Feast)."""
    vk = str(village_key or "").strip().lower()
    if vk == "kitsune" and has_active_spirit_event(session_id, "evt_spirit_kagura_revelry"):
        return 2
    if vk == "bunian" and has_active_spirit_event(session_id, "evt_spirit_malam_berinai_feast"):
        return 2
    return 0


def get_bunian_banquet_rest_bonus(session_id: int, node_id: str) -> dict[str, Any]:
    """Returns complimentary banquet restorative buff info when resting inside `zone_spirit_bunian` during Malam Berinai."""
    if not session_id or not has_active_spirit_event(session_id, "evt_spirit_malam_berinai_feast"):
        return {"active": False, "rest_multiplier": 1.0, "buff_name": ""}
    if infer_spirit_zone_for_node(node_id) != "zone_spirit_bunian":
        return {"active": False, "rest_multiplier": 1.0, "buff_name": ""}
    return {
        "active": True,
        "rest_multiplier": 1.25,
        "buff_name": "Royal Songket Banquet Restored",
    }


def get_drifting_lanterns_affinity_bonus(session_id: int, node_id: str = "") -> int:
    """Returns `+2` social affinity boost during `evt_spirit_drifting_lanterns` inside the Veiled Spirit Realm."""
    if not session_id or not has_active_spirit_event(session_id, "evt_spirit_drifting_lanterns"):
        return 0
    nid = str(node_id or "").strip()
    if not nid:
        sess = db.get_session(int(session_id)) or {}
        nid = str(sess.get("current_node_id") or "").strip()
    if not nid:
        return 0
    from mechanics.world.locations.folklore_spirit_realm import is_node_in_spirit_realm
    return 2 if is_node_in_spirit_realm(int(session_id), nid) else 0


def get_feral_ghul_hunt_modifiers(session_id: int, node_id: str = "") -> dict[str, Any]:
    """Returns encounter/loot/cull bonuses during `evt_spirit_feral_ghul_hunt` in Barrowlands/Lotus Mire."""
    if not session_id or not has_active_spirit_event(session_id, "evt_spirit_feral_ghul_hunt"):
        return {"active": False, "loot_tier_bonus": 0, "cull_rep_bonus": 0, "encounter_weight_mult": 1.0}
    nid = str(node_id or "").strip()
    if not nid:
        sess = db.get_session(int(session_id)) or {}
        nid = str(sess.get("current_node_id") or "").strip()
    zone_id = infer_spirit_zone_for_node(nid)
    if zone_id not in ("zone_spirit_boneyard", "zone_spirit_mire"):
        return {"active": False, "loot_tier_bonus": 0, "cull_rep_bonus": 0, "encounter_weight_mult": 1.0}
    return {
        "active": True,
        "loot_tier_bonus": 1,
        "cull_rep_bonus": 5,
        "encounter_weight_mult": 1.5,
    }


_FERAL_PACK_RE = re.compile(
    r"\b(?:feral\s+gh[uū]l|feral\s+ghoul|al-?gh[uū]l|gh[uū]l\s+(?:pack|hound|stalker|beast)|"
    r"feral\s+(?:pack|hound|jackal|hyena|scavenger|carcass)|barrow\s+hound|hyena|jackal|coyote|carrion\s+(?:pack|hound|beast|scavenger))\b"
)


def is_feral_spirit_pack_enemy(enemy: Any) -> bool:
    """Matches feral Al-Ghul / barrow-pack hostiles for Feral Pack Hunt loot & cull rep bonuses."""
    if not isinstance(enemy, Mapping):
        raw = str(enemy or "").lower()
        return bool(_FERAL_PACK_RE.search(raw))
    race_str = str(enemy.get("race") or "").strip().lower()
    raw = " ".join(
        str(enemy.get(k) or "").lower()
        for k in ("name", "race", "species", "type", "archetype", "category")
    )
    tags = enemy.get("tags")
    if isinstance(tags, (list, tuple)):
        tag_str = " ".join(str(t).lower() for t in tags)
        raw += " " + tag_str
    else:
        tag_str = ""
    if race_str == "ghoul:humanoid" and "feral" not in tag_str and "pack_beast" not in tag_str:
        return False
    if race_str == "ghoul:canid":
        return True
    return bool(_FERAL_PACK_RE.search(raw))


def pick_discovered_spirit_event_target(
    session_id: int,
    template: Mapping[str, Any],
    rng: Any,
) -> dict[str, Any]:
    """Resolves valid Veiled Spirit Realm faction/zone/venue slots strictly inside `realm_veiled_spirit_world`."""
    from mechanics.world.locations.folklore_spirit_courts import (
        SPIRIT_COURT_FACTIONS,
        SPIRIT_ZONE_BY_VILLAGE,
    )
    from mechanics.world.locations.folklore_spirit_naming import (
        get_spirit_court_procedural_name,
        get_spirit_enclave_zone_title,
    )

    allowed_zones = [str(z) for z in (template.get("allowed_zone_ids") or []) if z]
    default_nid = str(template.get("default_node_id") or "sub_crossroads_bazaar_walk")
    target_vk = str(template.get("target_village_key") or "").strip().lower()

    all_nodes = db.get_session_world_nodes(int(session_id)) or []
    by_id = {str(n.get("node_id") or ""): dict(n) for n in all_nodes if n.get("node_id")}

    candidate_rooms: list[dict[str, Any]] = []
    for nid, node in by_id.items():
        if str(node.get("node_type") or "").upper() != "ROOM":
            continue
        if allowed_zones and not node_matches_spirit_event_zones(nid, allowed_zones):
            continue
        st = _parse_json_obj(node.get("state_json"))
        if st.get("is_hidden"):
            continue
        if str(node.get("access_tier") or "open").lower() == "private":
            continue
        candidate_rooms.append(node)

    picked_room = next((r for r in candidate_rooms if str(r.get("node_id")) == default_nid), None)
    if picked_room is None and candidate_rooms:
        picked_room = rng.choice(candidate_rooms)
    if picked_room is None:
        picked_room = by_id.get(default_nid) or {}

    loc_node_id = str(picked_room.get("node_id") or default_nid)
    venue_name = str(picked_room.get("name") or template.get("default_venue_name") or "Dusk Confluence Plaza")
    zone_id = infer_spirit_zone_for_node(loc_node_id) or (allowed_zones[0] if allowed_zones else "zone_spirit_crossroads")
    zone_node = by_id.get(zone_id) or {}
    zone_name = str(zone_node.get("name") or "The Veiled Spirit Realm")
    if target_vk in SPIRIT_ZONE_BY_VILLAGE:
        zone_name = get_spirit_enclave_zone_title(int(session_id), target_vk) or zone_name

    faction_id = ""
    faction_name = "Confluence Council"
    factions = db.get_factions(int(session_id)) or []
    spirit_factions = [f for f in factions if str(f.get("category") or "").lower() == "spirit_court"]
    if target_vk and target_vk in SPIRIT_COURT_FACTIONS:
        spec = SPIRIT_COURT_FACTIONS[target_vk]
        faction_id = spec["faction_id"]
        matched = next((f for f in spirit_factions if f.get("faction_id") == faction_id), None)
        faction_name = str((matched or {}).get("name") or get_spirit_court_procedural_name(int(session_id), target_vk))
    elif spirit_factions:
        picked_fac = rng.choice(spirit_factions)
        faction_id = str(picked_fac.get("faction_id") or "")
        faction_name = str(picked_fac.get("name") or faction_name)

    return {
        "faction_id": faction_id,
        "faction_name": faction_name,
        "zone_id": zone_id,
        "zone_name": zone_name,
        "location_node_id": loc_node_id,
        "location_name": venue_name,
    }


def spawn_crisis_commissions_for_spirit_event(
    session_id: int,
    event_dict: Mapping[str, Any],
    *,
    turn_number: int | None = None,
) -> list[dict[str, Any]]:
    """Spawns urgent Crisis commissions when `evt_spirit_neon_static_surge` or `evt_spirit_cold_iron_raid` triggers."""
    from mechanics.world.locations.folklore_spirit_courts import (
        SPIRIT_COURT_FACTIONS,
        SPIRIT_VILLAGE_KEYS,
    )
    from mechanics.world.locations.folklore_spirit_naming import get_spirit_court_procedural_name

    tpl_key = str(event_dict.get("template_key") or "").strip()
    if not session_id or tpl_key not in ("evt_spirit_neon_static_surge", "evt_spirit_cold_iron_raid"):
        return []

    sess = db.get_session(int(session_id)) or {}
    c_day = max(1, int(sess.get("current_day") or 1))
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(int(session_id)))
    existing_qids = {str(q.get("quest_id") or "") for q in (db.get_session_quests(int(session_id)) or [])}

    specs: list[tuple[str, str, str, str, str, str, int, int, int]] = []
    if tpl_key == "evt_spirit_neon_static_surge":
        specs.append((
            f"EVT-SPC-SURGE-D{c_day}",
            "kitsune",
            "Surge Stabilization: Leyline Static Conduit",
            "Realign the storm-charged relay pylons inside Cloud-Fang Crags before neon static severs Veiled comms.",
            "zone_spirit_peaks",
            "Cloud-Fang Crags — Thunder-Torii Summit",
            160,
            320,
            12,
        ))
    elif tpl_key == "evt_spirit_cold_iron_raid":
        factions_present = {
            str(f.get("faction_id") or "").lower()
            for f in (db.get_factions(int(session_id)) or [])
        }
        vks = [vk for vk in SPIRIT_VILLAGE_KEYS if SPIRIT_COURT_FACTIONS[vk]["faction_id"] in factions_present]
        if not vks:
            vks = list(SPIRIT_VILLAGE_KEYS)
        zone_map = {
            "kitsune": ("zone_spirit_peaks", "Cloud-Fang Crags — Storm-Torii Pass"),
            "bunian": ("zone_spirit_mire", "Sunken Lotus Mire — Reed Crossing"),
            "ghoul": ("zone_spirit_wilds", "The Weeping Bleedwood — Poacher's Iron-Ward Ravine"),
        }
        for vk in vks:
            z_nid, z_lbl = zone_map[vk]
            specs.append((
                f"EVT-SPC-RAID-{vk[:3].upper()}-D{c_day}",
                vk,
                f"Cold-Iron Incursion Defense ({vk.title()} Accord)",
                f"Intercept Syndicate cold-iron poacher teams breaching {z_lbl} and shatter their containment spikes.",
                z_nid,
                z_lbl,
                140,
                260,
                10,
            ))

    created: list[dict[str, Any]] = []
    for qid, vk, title, objective, t_nid, t_loc, xp_r, gold_r, rep_r in specs:
        if qid in existing_qids:
            continue
        fid = SPIRIT_COURT_FACTIONS[vk]["faction_id"]
        c_name = get_spirit_court_procedural_name(int(session_id), vk)
        notes = " | ".join([
            f"faction:{fid}",
            "board_source:spirit_court",
            f"spirit_court:{vk}",
            "optional_spirit_court:1",
            "target_realm_id:realm_veiled_spirit_world",
            f"target_node_id:{t_nid}",
            f"rep_reward:{rep_r}",
            "ghoul_track:grey_neutral" if vk == "ghoul" else "ghoul_track:standard",
            f"event_crisis:{tpl_key}",
            f"created_turn:{eff_turn}",
            "zero_cross_court_splash:1",
        ])
        db.upsert_quest(
            session_id=int(session_id),
            quest_id=qid,
            quest_type="Urgent Frontier Commission",
            title=title,
            objective=objective,
            status="Available",
            reward_xp=xp_r,
            reward_gold=gold_r,
            reward_item="",
            is_story_quest=0,
            quest_notes=notes,
            client_npc=f"{c_name} Herald",
            client_location=t_loc,
        )
        created.append({"quest_id": qid, "village_key": vk, "faction_id": fid, "title": title})
    return created


def cleanup_expired_spirit_crisis_commissions(
    session_id: int,
    template_key: str,
    *,
    conn: Any = None,
) -> int:
    """Deletes unaccepted (`Available`) `EVT-SPC-*` crisis commissions when their parent event expires."""
    tpl_key = str(template_key or "").strip()
    if not session_id or tpl_key not in ("evt_spirit_neon_static_surge", "evt_spirit_cold_iron_raid"):
        return 0
    ctx = nullcontext(conn) if conn is not None else db.UnitOfWork()
    deleted = 0
    with ctx as c:
        rows = c.execute(
            """SELECT quest_id FROM quests
               WHERE session_id = ? AND quest_id LIKE 'EVT-SPC-%'
                 AND LOWER(COALESCE(status, '')) = 'available'
                 AND quest_notes LIKE ?""",
            (int(session_id), f"%event_crisis:{tpl_key}%"),
        ).fetchall()
        for r in rows:
            qid = str(r["quest_id"] or "")
            if not qid:
                continue
            c.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (int(session_id), qid))
            c.execute("DELETE FROM quest_dossiers WHERE session_id = ? AND quest_id = ?", (int(session_id), qid))
            c.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (int(session_id), qid))
            deleted += 1
    return deleted


def apply_spirit_event_on_spawn(
    session_id: int,
    event_dict: Mapping[str, Any],
    *,
    turn_number: int | None = None,
) -> list[dict[str, Any]]:
    """Triggers immediate side effects (e.g., urgent Frontier Crisis commissions) on Veiled event spawn."""
    tpl_key = str(event_dict.get("template_key") or "").strip()
    if tpl_key in ("evt_spirit_neon_static_surge", "evt_spirit_cold_iron_raid"):
        return spawn_crisis_commissions_for_spirit_event(session_id, event_dict, turn_number=turn_number)
    return []


__all__ = [
    "SPIRIT_REALM_ID",
    "VEILED_SPIRIT_EVENT_KEYS",
    "VEILED_ENCLAVE_EVENT_VILLAGE",
    "VEILED_ZONE_NODE_PREFIXES",
    "node_matches_spirit_event_zones",
    "infer_spirit_zone_for_node",
    "cleanup_expired_spirit_crisis_commissions",
    "get_active_spirit_events",
    "has_active_spirit_event",
    "is_ferryman_toll_waived",
    "is_ghoul_entry_toll_waived",
    "is_spirit_relay_static_active",
    "get_spirit_relay_static_note",
    "get_spirit_event_sparring_bonuses",
    "get_spirit_event_rep_bonus",
    "get_bunian_banquet_rest_bonus",
    "get_drifting_lanterns_affinity_bonus",
    "get_feral_ghul_hunt_modifiers",
    "is_feral_spirit_pack_enemy",
    "pick_discovered_spirit_event_target",
    "spawn_crisis_commissions_for_spirit_event",
    "apply_spirit_event_on_spawn",
]
