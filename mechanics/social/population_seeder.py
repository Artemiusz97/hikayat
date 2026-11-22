"""
3-Stage Procedural World Population Seeder & Stage-1 Hydration Engine.

Implements:
- Stage 0 (`ensure_world_population_seeded`): Zero-LLM single-transaction bulk seed
  of skinny `world_roster` skeletons (~240 Anomalous Incursions, ~180 High School
  Drama, ~310 Anomalous High School total world casts) plus pre-wired `social_ties`
  for siblings/spouses/roommates/coworkers and `shared_residence_group` keys.
  Idempotent and safe for mid-campaign backfill on existing saves.
- Stage 1 (`hydrate_roster_npc_on_scene`): Lazy zero-LLM procedural generation of
  full appearance, traits, likes/dislikes, quirks, and drives the first time a
  `seeded` NPC shares a scene with the player.
"""
from __future__ import annotations

import hashlib
import random
import sqlite3
from typing import Any, Mapping

import db
from db.roster_adapters import parse_json_dict, slugify_npc_id
import namegen
import scenario_data
from mechanics.social.population_catalog import (
    ANOMALOUS_CIVIC_STAFF,
    ANOMALOUS_COHABITING_AND_TIE_SPECS,
    ANOMALOUS_DISTRICT_MERCHANTS,
    ANOMALOUS_HIDDEN_SECRETS,
    ANOMALOUS_PEDESTRIAN_ARCHETYPES,
    ANOMALOUS_STREET_VENDORS,
    HS_COHABITING_AND_TIE_SPECS,
    HS_EXTRA_CAMPUS_TEMPLATES,
    HS_EXTRA_TOWN_MERCHANTS_AND_VENDORS,
    HS_HIDDEN_SECRETS,
    HS_TOWN_PEDESTRIAN_ARCHETYPES,
    ROLE_DRIVE_POOLS,
    ROLE_QUIRK_POOLS,
)
from mechanics.social.races import normalize_race
from mechanics.social.town_roster import remap_town_node_for_scenario

_AHS_CAMPUS_LEAF_REMAP: dict[str, str] = {
    "loc_homeroom": "loc_school_academic",
    "loc_freshman_class": "loc_school_academic",
    "loc_sophomore_class": "loc_school_academic",
    "loc_junior_class": "loc_school_academic",
    "loc_senior_class": "loc_school_academic",
    "loc_library": "loc_school_academic",
    "loc_science_lab": "loc_school_academic",
    "loc_staff_room": "loc_school_academic",
    "loc_entrance_foyer": "loc_school_academic",
    "loc_school_hallway": "loc_school_academic",
    "loc_school_rooftop": "loc_school_academic",
    "loc_sports_field": "loc_school_athletics",
    "loc_gymnasium": "loc_school_athletics",
    "loc_pool": "loc_school_athletics",
    "loc_martial_arts_dojo": "loc_school_athletics",
    "loc_behind_gym_sheds": "loc_school_athletics",
    "loc_vending_pavilion": "loc_school_athletics",
    "loc_courtyard": "loc_school_courtyard",
    "loc_greenhouse": "loc_school_courtyard",
    "loc_student_council": "loc_student_council_facility",
    "loc_auditorium_stage": "loc_drama_club_facility",
    "loc_drama_club": "loc_drama_club_facility",
    "loc_clubroom_corridor": "loc_school_clubs",
    "loc_gaming_clubroom": "loc_school_clubs",
    "loc_broadcasting_room": "loc_school_clubs",
    "loc_fine_arts_studio": "loc_school_clubs",
    "loc_old_east_music_room": "loc_school_clubs",
    "loc_delinquent_boiler_den": "loc_school_clubs",
    "loc_cafeteria": "sub_school_cafeteria",
    "loc_school_gate": "sub_school_gate",
}

_CULTURE_WEIGHTS_BY_HINT: dict[str, dict[str, float]] = {
    "east_asian": {"east_asian": 1.0},
}


def is_population_seeding_supported(scen_key: str) -> bool:
    """Returns True strictly for Anomalous Incursions, High School Drama, and AHS scenarios."""
    clean = str(scen_key or "").strip().lower()
    if not clean:
        return False
    return bool(
        scenario_data.is_anomalous_incursions_scenario(clean)
        or scenario_data.is_high_school_scenario(clean)
        or scenario_data.is_anomalous_high_school_scenario(clean)
    )


def _deterministic_idx(seed_text: str, pool_len: int) -> int:
    if pool_len <= 0:
        return 0
    digest = hashlib.md5(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % pool_len


def _evenly_sampled_slice(items: tuple[dict[str, Any], ...], target_count: int) -> tuple[dict[str, Any], ...]:
    total = len(items)
    if target_count >= total or target_count <= 0:
        return items if target_count > 0 else ()
    return tuple(
        items[i]
        for i in range(total)
        if ((i + 1) * target_count) // total > (i * target_count) // total
    )


_SFW_NODE_REMAP: dict[str, str] = {
    "loc_nightclub": "loc_city_square",
    "loc_adult_store": "loc_clothing_store",
    "loc_love_hotel": "loc_local_park",
}

_SFW_ROLE_REMAP: dict[str, str] = {
    "Adult Boutique Window Shopper": "Fashion Boutique Window Shopper",
    "Nightclub Sound Mixer": "Livehouse Sound Mixer",
}


def _remap_node_for_scenario(node_id: str, scen_key: str) -> str:
    nid = str(node_id or "").strip()
    if not nid:
        return ""
    if not scenario_data.is_nsfw_scenario(scen_key) and nid in _SFW_NODE_REMAP:
        nid = _SFW_NODE_REMAP[nid]
    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        if nid in _AHS_CAMPUS_LEAF_REMAP:
            return _AHS_CAMPUS_LEAF_REMAP[nid]
        return remap_town_node_for_scenario(nid, scen_key)
    return nid


def _select_catalog_and_ties(
    scen_key: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[tuple[str, str, str, str]]]:
    """Selects deterministic skeleton catalog, hidden secrets map, and tie specs for `scen_key`."""
    is_ahs = scenario_data.is_anomalous_high_school_scenario(scen_key)
    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    is_hs = scenario_data.is_high_school_scenario(scen_key)

    if is_ahs:
        # 52 + 32 + 6 + 26 + 14 + 44 = 174 world_roster additions (+ ~136 school_directory = ~310 total)
        youth_peers = [p for p in HS_TOWN_PEDESTRIAN_ARCHETYPES if p.get("grade") == "Youth Peer"]
        metro_peds = list(_evenly_sampled_slice(ANOMALOUS_PEDESTRIAN_ARCHETYPES, 44))
        templates = (
            list(ANOMALOUS_DISTRICT_MERCHANTS)
            + list(ANOMALOUS_CIVIC_STAFF)
            + list(ANOMALOUS_STREET_VENDORS)
            + list(HS_EXTRA_CAMPUS_TEMPLATES)
            + youth_peers
            + metro_peds
        )
        secrets = {**ANOMALOUS_HIDDEN_SECRETS, **HS_HIDDEN_SECRETS}
        ties = list(ANOMALOUS_COHABITING_AND_TIE_SPECS) + list(HS_COHABITING_AND_TIE_SPECS)
        return templates, secrets, ties

    if is_anom:
        # 52 + 32 + 6 + 102 = 192 world_roster (+ 48 Special Agents = 240 total)
        templates = (
            list(ANOMALOUS_DISTRICT_MERCHANTS)
            + list(ANOMALOUS_CIVIC_STAFF)
            + list(ANOMALOUS_STREET_VENDORS)
            + list(ANOMALOUS_PEDESTRIAN_ARCHETYPES)
        )
        return templates, dict(ANOMALOUS_HIDDEN_SECRETS), list(ANOMALOUS_COHABITING_AND_TIE_SPECS)

    if is_hs:
        # 26 + 15 + 46 = 87 world_roster (+ ~94 school_directory = ~181 total)
        templates = (
            list(HS_EXTRA_CAMPUS_TEMPLATES)
            + list(HS_EXTRA_TOWN_MERCHANTS_AND_VENDORS)
            + list(HS_TOWN_PEDESTRIAN_ARCHETYPES)
        )
        return templates, dict(HS_HIDDEN_SECRETS), list(HS_COHABITING_AND_TIE_SPECS)

    return [], {}, []


def _resolve_player_gender(conn: sqlite3.Connection, session: Mapping[str, Any] | None, sid: int) -> str:
    if isinstance(session, Mapping) and session.get("player_gender"):
        return str(session.get("player_gender") or "")
    try:
        sess_row = conn.execute("SELECT user_id FROM sessions WHERE id = ? LIMIT 1", (sid,)).fetchone()
        if sess_row and sess_row["user_id"]:
            ch_row = conn.execute(
                "SELECT gender FROM characters WHERE user_id = ? LIMIT 1",
                (int(sess_row["user_id"]),),
            ).fetchone()
            if ch_row and ch_row["gender"]:
                return str(ch_row["gender"] or "")
    except sqlite3.OperationalError:
        pass
    return ""


def _collect_existing_collision_sets(
    conn: sqlite3.Connection,
    sid: int,
) -> tuple[set[str], set[str], dict[str, dict[str, str]]]:
    """Collects already-present npc_ids, names, and `slot_id -> {name, npc_id}` mappings."""
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    slot_to_info: dict[str, dict[str, str]] = {}

    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_roster' LIMIT 1").fetchone():
        for sql in db.WORLD_ROSTER_V54_DDL:
            conn.execute(sql)
    for row in conn.execute(
        "SELECT npc_id, name, basic_info_json FROM world_roster WHERE session_id = ?",
        (sid,),
    ).fetchall():
        nid = str(row["npc_id"] or "").strip()
        nm = str(row["name"] or "").strip()
        if nid:
            seen_ids.add(nid.lower())
        if nm:
            seen_names.add(nm.lower())
        b_info = parse_json_dict(row["basic_info_json"])
        slot_key = str(b_info.get("population_slot_id") or "").strip()
        if slot_key and nm:
            slot_to_info[slot_key] = {"name": nm, "npc_id": nid}

    for sql in (
        "SELECT name FROM school_directory WHERE session_id = ?",
        "SELECT name FROM contacts WHERE session_id = ?",
        "SELECT name FROM lorebook WHERE session_id = ? AND entity_type = 'person'",
    ):
        try:
            for row in conn.execute(sql, (sid,)).fetchall():
                nm = str(row["name"] or "").strip()
                if nm:
                    seen_names.add(nm.lower())
        except sqlite3.OperationalError:
            pass

    return seen_ids, seen_names, slot_to_info


def _build_family_metadata(
    tie_specs: list[tuple[str, str, str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Maps `slot_id -> family_group_key` (surname sharing) and `slot_id -> shared_residence_group`."""
    family_group_by_slot: dict[str, str] = {}
    residence_group_by_slot: dict[str, str] = {}

    for slot_a, slot_b, tie_type, res_group in tie_specs:
        if res_group:
            residence_group_by_slot[slot_a] = res_group
            residence_group_by_slot[slot_b] = res_group
        if tie_type in ("married", "sibling"):
            grp_a = family_group_by_slot.get(slot_a)
            grp_b = family_group_by_slot.get(slot_b)
            fam_grp = grp_a or grp_b or f"fam_{slot_a}"
            family_group_by_slot[slot_a] = fam_grp
            family_group_by_slot[slot_b] = fam_grp

    return family_group_by_slot, residence_group_by_slot


def _generate_unique_identity(
    *,
    slot_id: str,
    scen_key: str,
    gender_hint: str,
    culture_hint: str,
    player_gender: str,
    rng: random.Random,
    seen_ids: set[str],
    seen_names: set[str],
    shared_surname: str = "",
) -> tuple[str, str]:
    resolved_gender = str(gender_hint or "").strip()
    if not resolved_gender:
        resolved_gender = scenario_data.resolve_scenario_npc_gender(
            scen_key,
            player_gender_or_char=player_gender,
            rng=rng,
        )
    c_weights = _CULTURE_WEIGHTS_BY_HINT.get(culture_hint) if culture_hint else None

    for attempt in range(20):
        seed_val = f"{scen_key}:{slot_id}:{attempt}"
        if shared_surname:
            candidate = namegen.generate_person_name_with_surname(
                shared_surname,
                scenario=scen_key,
                gender=resolved_gender,
                culture_weights=c_weights,
                player_gender=player_gender,
                seed=seed_val,
            )
        else:
            prof = namegen.generate_npc_profile(
                scenario=scen_key,
                gender=resolved_gender,
                player_gender=player_gender,
                culture_weights=c_weights,
                rng=rng,
            )
            candidate = str(prof.get("name") or "").strip()
            resolved_gender = str(prof.get("gender") or resolved_gender)

        clean_name = " ".join(candidate.split()).strip()
        slug = slugify_npc_id(clean_name)
        if clean_name and slug and clean_name.lower() not in seen_names and slug.lower() not in seen_ids:
            seen_names.add(clean_name.lower())
            seen_ids.add(slug.lower())
            return clean_name, resolved_gender

    # Guaranteed deterministic suffix-free or numeric-free fallback via middle initial
    base_name = namegen.generate_person_name(scenario=scen_key, gender=resolved_gender, rng=rng)
    for letter in "ABCDEFGHJKLMNPQRSTUVWXYZ":
        cand = f"{base_name} {letter}."
        slug = slugify_npc_id(cand)
        if cand.lower() not in seen_names and slug.lower() not in seen_ids:
            seen_names.add(cand.lower())
            seen_ids.add(slug.lower())
            return cand, resolved_gender
    return f"{base_name} {slot_id[-4:]}", resolved_gender


def _build_skeleton_payload(
    tmpl: dict[str, Any],
    *,
    scen_key: str,
    full_name: str,
    gender: str,
    race: str,
    secrets_map: dict[str, dict[str, Any]],
    res_group: str,
    cohabitant_home_nodes: dict[str, str],
) -> dict[str, Any]:
    slot_id = str(tmpl["slot_id"])
    origin = str(tmpl.get("origin") or "roaming_citizen")
    workplace = _remap_node_for_scenario(str(tmpl.get("workplace_node_id") or ""), scen_key)
    hangout = _remap_node_for_scenario(str(tmpl.get("hangout_node_id") or ""), scen_key)
    raw_home = _remap_node_for_scenario(str(tmpl.get("home_node_id") or ""), scen_key)
    if res_group:
        if not raw_home:
            raw_home = cohabitant_home_nodes.setdefault(res_group, f"sub_npc_res_hh_{res_group}")
        else:
            cohabitant_home_nodes.setdefault(res_group, raw_home)
    home_node = raw_home or workplace

    roaming_route = list(dict.fromkeys(
        n for n in (_remap_node_for_scenario(s, scen_key) for s in (tmpl.get("roaming_route") or ())) if n
    ))
    weekend_route = list(dict.fromkeys(
        n for n in (_remap_node_for_scenario(s, scen_key) for s in (tmpl.get("weekend_route") or ())) if n
    ))
    raw_role = str(tmpl.get("role") or "")
    eff_role = raw_role if scenario_data.is_nsfw_scenario(scen_key) else _SFW_ROLE_REMAP.get(raw_role, raw_role)

    part_time_shift = tmpl.get("part_time_shift")
    if isinstance(part_time_shift, dict):
        part_time_shift = {
            **part_time_shift,
            "venue_node_id": _remap_node_for_scenario(str(part_time_shift.get("venue_node_id") or ""), scen_key),
        }

    grade = str(tmpl.get("grade") or "")
    age_group = str(tmpl.get("age_group") or "adult")
    if origin == "campus_seed" and grade != "Staff":
        social_role_type = "student_peer"
    elif grade == "Youth Peer":
        social_role_type = "contemporary"
    elif grade == "Staff":
        social_role_type = "faculty_staff"
    else:
        social_role_type = "civilian_resident"

    m_arch = str(tmpl.get("merchant_archetype") or "").strip()
    m_arches = [m_arch] if m_arch else []
    is_anom_family = (
        scenario_data.is_anomalous_incursions_scenario(scen_key)
        or scenario_data.is_anomalous_high_school_scenario(scen_key)
    )

    basic_info: dict[str, Any] = {
        "population_slot_id": slot_id,
        "zone_id": str(tmpl.get("zone_id") or ""),
        "role": eff_role,
        "occupation": eff_role,
        "age_group": age_group,
        "grade": grade,
        "club": str(tmpl.get("club") or ""),
        "social_role_type": social_role_type,
        "merchant_archetype": m_arch,
        "merchant_archetypes": m_arches,
        "folklore_pool": str(tmpl.get("folklore_pool") or ""),
        "nocturnal": bool(tmpl.get("nocturnal")),
        "closes_at_22": bool(tmpl.get("closes_at_22")),
        "closes_at_20": bool(tmpl.get("closes_at_20")),
        "is_24h_station": bool(tmpl.get("is_24h_station")),
        "is_truant_peer": bool(tmpl.get("is_truant_peer")),
        "is_contraband_peddler": bool(tmpl.get("is_contraband_peddler")),
        "nsfw_venue": bool(tmpl.get("nsfw_venue")),
        "weekend_route": weekend_route,
        "part_time_shift": part_time_shift,
        "shared_residence_group": res_group,
        "visual_hydrated": False,
    }
    if is_anom_family:
        basic_info["anomalous_npc_tag"] = "civilian"

    secret_spec = secrets_map.get(slot_id)
    if isinstance(secret_spec, dict):
        basic_info["hidden_secret"] = str(secret_spec.get("hidden_secret") or "")
        basic_info["hidden_secret_telltale"] = str(secret_spec.get("telltale_key") or "micro_telltale")
        basic_info["hidden_awakened"] = bool(secret_spec.get("hidden_awakened", False))
        basic_info["secret_faction"] = str(secret_spec.get("secret_faction") or "")
        basic_info["hidden_secret_revealed"] = False

    return {
        "npc_id": slugify_npc_id(full_name),
        "name": full_name,
        "gender": gender,
        "race": race,
        "role": eff_role,
        "origin": origin,
        "tier_status": "seeded",
        "affinity_score": 0,
        "met_in_person": 0,
        "workplace_node_id": workplace,
        "home_node_id": home_node,
        "hangout_node_id": hangout,
        "roaming_route": roaming_route,
        "shift_profile": str(tmpl.get("shift_profile") or "day"),
        "staff_status": "active",
        "is_unique_proprietor": bool(tmpl.get("is_unique_proprietor")),
        "residence_unlocked": False,
        "basic_info": basic_info,
        "appearance": {},
        "traits": [],
    }


def _wire_population_social_ties(
    conn: sqlite3.Connection,
    sid: int,
    tie_specs: list[tuple[str, str, str, str]],
    slot_to_info: dict[str, dict[str, str]],
    seen_slots_newly_added: set[str],
) -> int:
    if not tie_specs:
        return 0
    import mechanics.social.relationship_graph as rg

    ties_written = 0
    for slot_a, slot_b, tie_type, res_group in tie_specs:
        if slot_a not in seen_slots_newly_added and slot_b not in seen_slots_newly_added:
            continue
        info_a = slot_to_info.get(slot_a)
        info_b = slot_to_info.get(slot_b)
        if not info_a or not info_b:
            continue
        closeness = 78 if tie_type in ("married", "sibling") else (64 if tie_type == "roommate" else 56)
        try:
            rg.form_tie(
                sid,
                info_a["name"],
                info_b["name"],
                tie_type=tie_type,
                closeness=closeness,
                visibility="public",
                origin="population_seed",
                turn=0,
                metadata={"shared_residence_group": res_group} if res_group else None,
                materialize=False,
                conn=conn,
            )
            ties_written += 1
        except Exception:
            pass
    return ties_written


def ensure_world_population_seeded(
    session_id: int,
    scen_key: str = "",
    *,
    session: Mapping[str, Any] | None = None,
    turn_number: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Stage-0 deterministic bulk seeder (Turn 0 or mid-campaign backfill).
    Inserts skinny `world_roster` skeletons in one transaction with zero LLM tokens
    and wires baseline `social_ties` without mutating `contacts` or `lorebook`.
    """
    if not session_id:
        return {"seeded": 0, "ties": 0, "skipped": True}
    sid = int(session_id)

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        eff_scen = str(scen_key or "").strip()
        if not eff_scen and isinstance(session, Mapping):
            eff_scen = str(session.get("scenario") or "").strip()
        if not eff_scen:
            row_s = c.execute("SELECT scenario FROM sessions WHERE id = ? LIMIT 1", (sid,)).fetchone()
            if row_s and row_s["scenario"]:
                eff_scen = str(row_s["scenario"]).strip()
        if not is_population_seeding_supported(eff_scen):
            return {"seeded": 0, "ties": 0, "skipped": True}

        templates, secrets_map, tie_specs = _select_catalog_and_ties(eff_scen)
        if not templates:
            return {"seeded": 0, "ties": 0, "skipped": True}

        seen_ids, seen_names, slot_to_info = _collect_existing_collision_sets(c, sid)
        missing_templates = [t for t in templates if t["slot_id"] not in slot_to_info]
        if not missing_templates:
            return {"seeded": 0, "ties": 0, "already_seeded": True}

        rng = random.Random(f"world_pop:{sid}:{eff_scen}")
        player_gender = _resolve_player_gender(c, session, sid)
        family_groups, res_groups = _build_family_metadata(tie_specs)
        cohabitant_home_nodes: dict[str, str] = {}
        family_surnames: dict[str, str] = {}

        # Pre-seed known family surnames when backfilling partial saves
        for s_id, fam_grp in family_groups.items():
            if s_id in slot_to_info and fam_grp not in family_surnames:
                _, raw_sur = namegen.extract_first_and_last_name(slot_to_info[s_id]["name"])
                if raw_sur:
                    family_surnames[fam_grp] = namegen.normalize_base_surname(raw_sur)

        payloads: list[dict[str, Any]] = []
        newly_added_slots: set[str] = set()
        for tmpl in missing_templates:
            slot_id = str(tmpl["slot_id"])
            fam_grp = family_groups.get(slot_id, "")
            shared_sur = family_surnames.get(fam_grp, "") if fam_grp else ""

            full_name, gender = _generate_unique_identity(
                slot_id=slot_id,
                scen_key=eff_scen,
                gender_hint=str(tmpl.get("gender_hint") or ""),
                culture_hint=str(tmpl.get("culture_hint") or ""),
                player_gender=player_gender,
                rng=rng,
                seen_ids=seen_ids,
                seen_names=seen_names,
                shared_surname=shared_sur,
            )
            if fam_grp and fam_grp not in family_surnames:
                _, raw_sur = namegen.extract_first_and_last_name(full_name)
                if raw_sur:
                    family_surnames[fam_grp] = namegen.normalize_base_surname(raw_sur)

            race = normalize_race("", eff_scen, seed=f"{sid}:{slot_id}:{full_name}")
            skeleton = _build_skeleton_payload(
                tmpl,
                scen_key=eff_scen,
                full_name=full_name,
                gender=gender,
                race=race,
                secrets_map=secrets_map,
                res_group=res_groups.get(slot_id, ""),
                cohabitant_home_nodes=cohabitant_home_nodes,
            )
            payloads.append(skeleton)
            slot_to_info[slot_id] = {"name": full_name, "npc_id": skeleton["npc_id"]}
            newly_added_slots.add(slot_id)

        inserted = db.bulk_upsert_world_roster(sid, payloads, turn_number=int(turn_number or 0), conn=c)
        ties_written = _wire_population_social_ties(c, sid, tie_specs, slot_to_info, newly_added_slots)
        return {"seeded": len(inserted), "ties": ties_written, "skipped": False}

    if conn is not None:
        return _run(conn)
    with db.get_conn() as c:
        return _run(c)


def _outfit_hint_for_npc(npc: Mapping[str, Any], basic: Mapping[str, Any], scen_key: str) -> str:
    origin = str(npc.get("origin") or "").strip().lower()
    role = str(npc.get("role") or basic.get("role") or "").strip()
    role_low = role.lower()
    grade = str(basic.get("grade") or "").strip()
    if origin == "campus_seed" and grade != "Staff":
        return "Crisp academy uniform blazer with subtle club accents"
    if origin == "district_merchant" or "clerk" in role_low or "barista" in role_low:
        return f"Practical shop apron or neat storefront uniform suited to a {role or 'shopkeeper'}"
    if origin == "civic_staff":
        return f"Clean civic/institutional uniform with badge for a {role or 'staff member'}"
    if origin == "roaming_merchant":
        return f"Weatherproof vendor apron and sturdy utility pouch fit for a {role or 'street vendor'}"
    if "nocturnal" in role_low or basic.get("nocturnal"):
        return "Dark hooded urban trenchcoat with brass-buttoned satchel"
    return f"Everyday urban clothing suited to a {role or 'local resident'} in {scen_key.replace('_', ' ')}"


def hydrate_roster_npc_on_scene(npc: Mapping[str, Any], scen_key: str) -> dict[str, Any] | None:
    """
    Stage-1 zero-LLM visual & trait hydration invoked the first time a `seeded`
    `world_roster` NPC shares a location with the player.
    """
    if not isinstance(npc, Mapping):
        return None
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), Mapping) else {}
    existing_app = npc.get("appearance") if isinstance(npc.get("appearance"), Mapping) else {}
    existing_traits = npc.get("traits") if isinstance(npc.get("traits"), list) else []
    if basic.get("visual_hydrated") and existing_app and existing_traits:
        return None

    from mechanics.social.persona import (
        categorize_likes_and_dislikes,
        normalize_appearance,
        split_traits_and_preferences,
    )

    name = str(npc.get("name") or "").strip()
    npc_id = str(npc.get("npc_id") or slugify_npc_id(name)).strip()
    if not name or not npc_id:
        return None
    role = str(npc.get("role") or basic.get("role") or "Resident").strip()
    race = str(npc.get("race") or basic.get("race") or "human").strip()
    gender = str(npc.get("gender") or basic.get("gender") or "").strip()
    slot_seed = str(basic.get("population_slot_id") or npc_id or name)

    traits, _prefs = split_traits_and_preferences(
        list(existing_traits),
        [],
        role=role,
        race=race,
        seed_str=f"{slot_seed}:{role}",
    )
    likes, dislikes = categorize_likes_and_dislikes(
        [],
        traits=traits,
        role=role,
        race=race,
        desc=f"{role} ({slot_seed})",
    )
    outfit_hint = _outfit_hint_for_npc(npc, basic, scen_key)
    appearance = normalize_appearance(
        dict(existing_app) or {"outfit_style": outfit_hint},
        gender=gender,
        race=race,
        scen_key=scen_key,
        desc=outfit_hint,
        traits=traits,
        role=role,
        name=name,
    )
    quirk = ROLE_QUIRK_POOLS[_deterministic_idx(f"quirk:{slot_seed}", len(ROLE_QUIRK_POOLS))]
    drive = ROLE_DRIVE_POOLS[_deterministic_idx(f"drive:{slot_seed}", len(ROLE_DRIVE_POOLS))]

    basic_updates: dict[str, Any] = {
        "visual_hydrated": True,
        "likes": likes,
        "dislikes": dislikes,
        "quirk": quirk,
        "drive": drive,
    }
    return {
        "npc_id": npc_id,
        "name": name,
        "appearance": appearance,
        "traits": traits,
        "basic_info_updates": basic_updates,
    }
