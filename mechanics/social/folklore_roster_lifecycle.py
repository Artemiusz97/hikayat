"""
mechanics/social/folklore_roster_lifecycle.py
=============================================
Atomic database hydration, befriending, Kitsune form shifting (bond & circadian),
companion recruitment, daytime human-glamour token grants, staged live-turn commits,
and turn-rollback reconciliation for veiled folklore villagers.
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import logging
import time
from typing import Any, Dict, List, Optional

import db
from mechanics.world.locations.folklore_veil import (
    get_village_veil_status,
    load_folklore_villages_catalog,
)

from .folklore_roster import (
    _build_villager_stats,
    _match_villager_entry,
    _slugify_id,
    build_villager_basic_info_dict,
    ensure_folklore_villager_roster,
    get_folklore_villager_spec,
    get_scheduled_villagers_for_node,
    is_myobu_fox_race,
)

log = logging.getLogger("hikayat.social.folklore_roster_lifecycle")


def _sync_villager_physical_garments(
    conn: Any,
    session_id: int,
    actor_name: str,
    race: str,
    humanoid_outfit: str,
) -> None:
    """Initializes or updates actor_physical_states and 6 actor_garments slots inside an active transaction."""
    from mechanics.social.physical_state import (
        ALL_GARMENT_SLOTS,
        COMPOSURE_COMPOSED,
        SLOT_BOTTOM,
        SLOT_FOOTWEAR,
        SLOT_LAYER_DEPTHS,
        SLOT_OUTERWEAR,
        SLOT_TOP,
        SLOT_UNDER_BOTTOM,
        SLOT_UNDER_TOP,
        STATE_NONE,
        STATE_WORN,
    )

    now = time.time()
    canon_key = _slugify_id(actor_name)
    is_fox_beast = is_myobu_fox_race(race)

    if is_fox_beast:
        canon_outfit = {slot: STATE_NONE for slot in ALL_GARMENT_SLOTS}
        posture = "Poised on four spirit-fox paws"
        holding = "Foxfire wisps"
    else:
        canon_outfit = {
            SLOT_OUTERWEAR: humanoid_outfit,
            SLOT_TOP: humanoid_outfit,
            SLOT_BOTTOM: "Traditional silk hakama / songket sarong",
            SLOT_UNDER_TOP: "Worn",
            SLOT_UNDER_BOTTOM: "Worn",
            SLOT_FOOTWEAR: "Woven shrine sandals / gilded capal",
        }
        posture = "Standing with serene poise"
        holding = "Empty hands"

    conn.execute(
        """INSERT INTO actor_physical_states
           (session_id, actor_name, canonical_key, actor_type, posture, holding, stance, composure, canonical_outfit_json, created_at, updated_at)
           VALUES (?, ?, ?, 'npc', ?, ?, 'Neutral', ?, ?, ?, ?)
           ON CONFLICT(session_id, canonical_key) DO UPDATE SET
               actor_name = excluded.actor_name,
               posture = excluded.posture,
               holding = excluded.holding,
               canonical_outfit_json = excluded.canonical_outfit_json,
               updated_at = excluded.updated_at""",
        (session_id, actor_name, canon_key, posture, holding, COMPOSURE_COMPOSED, json.dumps(canon_outfit), now, now),
    )

    for slot in ALL_GARMENT_SLOTS:
        g_state = STATE_NONE if is_fox_beast else STATE_WORN
        g_item = "" if is_fox_beast else str(canon_outfit.get(slot) or "")
        depth = int(SLOT_LAYER_DEPTHS.get(slot, 2))
        conn.execute(
            """INSERT INTO actor_garments (session_id, actor_key, slot, state, item_name, layer_depth, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, actor_key, slot) DO UPDATE SET
                   state = excluded.state,
                   item_name = excluded.item_name,
                   updated_at = excluded.updated_at""",
            (session_id, canon_key, slot, g_state, g_item, depth, now),
        )


def hydrate_folklore_villager_on_encounter(
    session_id: int,
    npc_id_or_name: str,
    turn_number: int = 0,
    befriended: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Lazily hydrates a pregenerated folklore villager into contacts, social_persons,
    social_ties (private secret_crush for Puteri/Putera), actor_physical_states,
    actor_garments, and lorebook inside one atomic UnitOfWork transaction.
    """
    import mechanics.social.relationship_graph as rg

    with db.UnitOfWork() as conn:
        roster = ensure_folklore_villager_roster(session_id, persist_db=True)
        if not roster:
            return None

        spec = _match_villager_entry(roster, npc_id_or_name)
        if spec is None:
            return None

        eff_turn = int(turn_number if turn_number else db.get_effective_session_turn(session_id))
        npc_id = str(spec["npc_id"])
        name = str(spec["name"])
        gender = str(spec["gender"])
        race = str(spec["race"])
        village_key = str(spec["folklore_village"])
        init_score = int(spec.get("initial_affinity") or 5)
        is_befriended = bool(befriended or spec.get("befriended") or init_score >= 30)

        basic_info = build_villager_basic_info_dict(spec, is_befriended=is_befriended)

        intimate_profile: Dict[str, Any] = {
            "tracks": {
                "intercourse": "virgin" if spec.get("virgin") else "inexperienced",
                "oral": "inexperienced",
                "manual": "inexperienced",
                "anal": "inexperienced",
            },
            "predetermined_intercourse": "virgin" if spec.get("virgin") else "inexperienced",
        }

        home_node = str(spec.get("home_node") or ("sub_kitsune_inner_plaza" if village_key == "kitsune" else "sub_bunian_inner_plaza"))
        enclave_disp = "Sato-no-Inari — Hidden Kitsune Village" if village_key == "kitsune" else "Kampung Kayangan — Hidden Bunian Village"
        court_house_name = "House of Shirakawa (Celestial Inari Court)" if village_key == "kitsune" else "Istana Seri Kayangan (Royal Bunian Court)"
        fellow_villagers = [
            e for e in roster
            if e.get("folklore_village") == village_key and e.get("npc_id") != npc_id and e.get("name")
        ]
        fellow_friend_entries = [
            {"name": str(fv["name"]), "role": str(fv.get("role") or "Enclave Kin"), "closeness": 65}
            for fv in fellow_villagers[:2]
        ]
        folklore_relations: Dict[str, Any] = {
            "family": [
                {
                    "relation": "Ancestral Spirit Court",
                    "name": court_house_name,
                    "occupation": enclave_disp,
                    "is_contactable": False,
                }
            ],
            "residence_location": enclave_disp,
            "residence_node_id": home_node,
            "cohabiting_family": False,
            "friends": fellow_friend_entries,
            "rivals": [],
            "romance": {
                "status": "Single",
                "current_partner": None,
                "secret_partner": None,
                "ex_partners": [],
            },
        }

        now = time.time()
        existing = conn.execute(
            "SELECT id, relationship_score, track, basic_info_json, relations_json FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
            (session_id, npc_id, name.lower()),
        ).fetchone()

        if existing:
            cur_score = max(int(existing["relationship_score"] or 0), init_score)
            if cur_score >= 30:
                is_befriended = True
            try:
                old_bi = json.loads(existing["basic_info_json"] or "{}")
            except Exception:
                old_bi = {}
            try:
                old_rel = json.loads(existing["relations_json"] or "{}") if existing["relations_json"] else {}
            except Exception:
                old_rel = {}
            merged_rel = {**folklore_relations, **(old_rel if isinstance(old_rel, dict) else {})}
            if not merged_rel.get("family"):
                merged_rel["family"] = folklore_relations["family"]
            merged_bi = {**old_bi, **basic_info}
            if old_bi.get("contact_added") or is_befriended:
                merged_bi["contact_added"] = True
                merged_bi["is_contact"] = True
                merged_bi["unlocked_via_friendship"] = True
                merged_bi["spirit_relay_unlocked"] = True
            conn.execute(
                """UPDATE contacts
                   SET npc_id = ?, race = ?, gender = ?, relationship_score = ?, basic_info_json = ?, appearance_json = ?, relations_json = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    npc_id,
                    race,
                    gender,
                    cur_score,
                    json.dumps(merged_bi),
                    json.dumps(spec.get("appearance") or {}),
                    json.dumps(merged_rel),
                    now,
                    existing["id"],
                ),
            )
        else:
            conn.execute(
                """INSERT INTO contacts
                   (session_id, character_id, npc_id, name, basic_info_json, relationship_score, track,
                    unlocked_traits_json, preferences_json, race, gender, appearance_json, relations_json, intimate_profile_json,
                    emotional_tone, open_thread, created_at, updated_at)
                   VALUES (?, 0, ?, ?, ?, ?, 'platonic', ?, '[]', ?, ?, ?, ?, ?, ?, '', ?, ?)""",
                (
                    session_id,
                    npc_id,
                    name,
                    json.dumps(basic_info),
                    init_score,
                    json.dumps([spec["role"], f"Tier {spec['agent_tier']} {spec['rank_title']}"]),
                    race,
                    gender,
                    json.dumps(spec.get("appearance") or {}),
                    json.dumps(folklore_relations),
                    json.dumps(intimate_profile),
                    "shy, quietly smitten warmth" if spec.get("secret_crush_on_pc") else "courteous folklore poise",
                    now,
                    now,
                ),
            )

        p_key = rg.get_or_create_person(
            session_id,
            name,
            gender=gender,
            role=spec["role"],
            origin="folklore_village",
            contact_npc_id=npc_id,
            conn=conn,
        )
        rg.get_or_create_person(session_id, "Player", person_key="player", origin="player", conn=conn)

        for fv in fellow_villagers[:1]:
            fv_key = rg.get_or_create_person(
                session_id,
                str(fv["name"]),
                gender=str(fv.get("gender") or ""),
                role=str(fv.get("role") or "Villager"),
                origin="folklore_village",
                contact_npc_id=str(fv.get("npc_id") or ""),
                conn=conn,
            )
            rg.form_tie(
                session_id,
                p_key,
                fv_key,
                rg.TIETYPE_FRIEND,
                closeness=65,
                visibility="public",
                turn=eff_turn,
                origin="folklore_village",
                materialize=False,
                conn=conn,
            )

        if spec.get("secret_crush_on_pc"):
            rg.form_tie(
                session_id,
                p_key,
                "player",
                "secret_crush",
                closeness=65,
                visibility="private",
                turn=eff_turn,
                origin="folklore_destiny",
                metadata={"folklore_secret_attraction": True, "single": True, "virgin": True},
                materialize=False,
                conn=conn,
            )

        _sync_villager_physical_garments(
            conn,
            session_id,
            name,
            race,
            str((spec.get("appearance") or {}).get("humanoid_outfit") or "Traditional folklore attire"),
        )

        db.upsert_lorebook_entity(
            session_id=session_id,
            entity_type="person",
            name=name,
            description=spec.get("personality_summary") or spec["role"],
            disposition="friendly",
            faction="Sato-no-Inari Kitsune Enclave" if village_key == "kitsune" else "Kampung Kayangan Bunian",
            traits=[spec["role"], spec["rank_title"]],
            race=race,
            appearance=spec.get("appearance") or {},
            gender=gender,
        )

        if not spec.get("hydrated"):
            spec["hydrated"] = True
            spec["hydrated_turn"] = eff_turn
        if is_befriended and not spec.get("befriended"):
            spec["befriended"] = True
            spec["befriended_turn"] = eff_turn
        db.update_session(session_id, extra={"folklore_villager_roster": roster})

    return db.get_contact(session_id, name)


def befriend_folklore_villager(
    session_id: int,
    npc_id_or_name: str,
    turn_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Unlocks Smartphone Spirit-Relay contact exchange for a met folklore villager atomically."""
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    with db.UnitOfWork() as conn:
        ct = hydrate_folklore_villager_on_encounter(session_id, npc_id_or_name, turn_number=eff_turn, befriended=True)
        if not ct:
            return None
        score = max(int(ct.get("relationship_score") or 0), 30)
        row = conn.execute("SELECT id, basic_info_json FROM contacts WHERE id = ?", (ct["id"],)).fetchone()
        if row:
            bi = json.loads(row["basic_info_json"] or "{}")
            bi["contact_added"] = True
            bi["is_contact"] = True
            bi["unlocked_via_friendship"] = True
            bi["spirit_relay_unlocked"] = True
            conn.execute(
                "UPDATE contacts SET relationship_score = ?, basic_info_json = ?, updated_at = ? WHERE id = ?",
                (score, json.dumps(bi), time.time(), row["id"]),
            )
        roster = ensure_folklore_villager_roster(session_id, persist_db=True)
        for entry in roster:
            if str(entry.get("npc_id")) == str(ct.get("npc_id")):
                if not entry.get("befriended"):
                    entry["befriended"] = True
                    entry["befriended_turn"] = eff_turn
                break
        db.update_session(session_id, extra={"folklore_villager_roster": roster})
    return db.get_contact(session_id, ct["name"])


def shift_kitsune_form(
    session_id: int,
    npc_id_or_name: str,
    target_form: str,
    current_minute: Optional[int] = None,
    force: bool = False,
    turn_number: Optional[int] = None,
    shift_reason: str = "manual",
) -> Dict[str, Any]:
    """
    Toggles a Kitsune villager between 'kitsune:myobu_fox' and 'kitsune:humanoid'.
    Shifting from Myōbu Spirit Fox -> Humanoid Guise requires affinity >= 45 or evening hours (18:00–23:59) unless force=True.
    Records turn-stamped form_history so turn rollback restores both race and 6-slot garments without split-brain.
    """
    norm_target = str(target_form or "").strip().lower()
    if norm_target not in ("kitsune:humanoid", "kitsune:myobu_fox"):
        raise ValueError(f"Invalid kitsune target form: {target_form}")

    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    with db.UnitOfWork() as conn:
        ct = hydrate_folklore_villager_on_encounter(session_id, npc_id_or_name, turn_number=eff_turn)
        if not ct:
            return {"shifted": False, "reason": "not_found"}

        cur_race = str(ct.get("race") or "").strip().lower()
        if not cur_race.startswith("kitsune:"):
            return {"shifted": False, "reason": "not_kitsune"}
        if cur_race == norm_target:
            return {"shifted": False, "reason": "already_in_form", "new_form": norm_target}

        if current_minute is None:
            _, current_minute, _ = db.get_session_time(session_id)
        safe_min = int(current_minute or 0) % 1440
        is_evening_shrine_hours = 1080 <= safe_min < 1440
        score = int(ct.get("relationship_score") or 0)

        if cur_race == "kitsune:myobu_fox" and norm_target == "kitsune:humanoid" and not force:
            if score < 45 and not is_evening_shrine_hours:
                return {"shifted": False, "reason": "bond_or_evening_required", "relationship_score": score}

        catalog = load_folklore_villages_catalog()
        kits = catalog.get("combat_kits") or {}
        roster = ensure_folklore_villager_roster(session_id, persist_db=True)
        spec = next((e for e in roster if str(e.get("npc_id")) == str(ct.get("npc_id"))), None) or {}
        humanoid_kit_key = str(spec.get("humanoid_kit_key") or (ct.get("basic_info") or {}).get("humanoid_kit_key") or "kitsune_mystic")
        new_kit_key = "kitsune_myobu_beast" if norm_target == "kitsune:myobu_fox" else humanoid_kit_key
        new_abilities = list(kits.get(new_kit_key) or [])

        app = dict(ct.get("appearance") or {})
        humanoid_outfit = str(app.get("humanoid_outfit") or "Vermilion-and-ivory Inari shrine kimono")
        app["kitsune_form"] = norm_target
        app["coat_color"] = str(app.get("fur_coat") or "") if norm_target == "kitsune:myobu_fox" else ""
        app["outfit_style"] = "" if norm_target == "kitsune:myobu_fox" else humanoid_outfit
        app["outfit_summary"] = (
            "Unclothed sacred spirit-fox coat wreathed in kitsunebi wisps"
            if norm_target == "kitsune:myobu_fox"
            else humanoid_outfit
        )

        row = conn.execute("SELECT id, basic_info_json, track FROM contacts WHERE id = ?", (ct["id"],)).fetchone()
        bi = json.loads(row["basic_info_json"] or "{}") if row else {}
        bi["race"] = norm_target
        bi["combat_kit_key"] = new_kit_key
        bi["innate_abilities"] = new_abilities
        new_track = "platonic" if norm_target == "kitsune:myobu_fox" else str(row["track"] or "platonic")
        conn.execute(
            "UPDATE contacts SET race = ?, track = ?, basic_info_json = ?, appearance_json = ?, updated_at = ? WHERE id = ?",
            (norm_target, new_track, json.dumps(bi), json.dumps(app), time.time(), ct["id"]),
        )
        conn.execute(
            "UPDATE lorebook SET race = ?, appearance_json = ? WHERE session_id = ? AND lower(name) = ?",
            (norm_target, json.dumps(app), session_id, ct["name"].lower()),
        )
        _sync_villager_physical_garments(conn, session_id, ct["name"], norm_target, humanoid_outfit)

        for entry in roster:
            if str(entry.get("npc_id")) == str(ct.get("npc_id")):
                hist = list(entry.get("form_history") or [])
                hist.append(
                    {
                        "turn": eff_turn,
                        "prev_form": cur_race,
                        "new_form": norm_target,
                        "reason": shift_reason,
                    }
                )
                entry["form_history"] = hist[-12:]
                if norm_target == "kitsune:humanoid" and (score >= 45 or shift_reason == "bond_affinity"):
                    entry["bond_humanoid_unlocked"] = True
                    entry.setdefault("bond_unlocked_turn", eff_turn)
                entry["race"] = norm_target
                entry["combat_kit_key"] = new_kit_key
                entry["innate_abilities"] = new_abilities
                entry["appearance"] = app
                break
        db.update_session(session_id, extra={"folklore_villager_roster": roster})

    return {"shifted": True, "name": ct["name"], "new_form": norm_target, "abilities": new_abilities}


def sync_kitsune_circadian_forms_for_node(
    session_id: int,
    node_id: str,
    current_minute: int = 480,
    turn_number: int = 0,
) -> List[Dict[str, Any]]:
    """
    Applies circadian form transitions for Kitsune villagers present at `node_id`:
    - Evening shrine hours (18:00–23:59): `kitsune:myobu_fox` shifts into `kitsune:humanoid` guise.
    - Daytime hours (06:00–17:59): circadian-shifted Kitsune revert to `initial_form` unless bonded (`affinity >= 45`).
    """
    if not session_id or not node_id:
        return []
    safe_min = int(current_minute or 0) % 1440
    is_evening = 1080 <= safe_min < 1440
    is_daytime = 360 <= safe_min < 1080
    scheduled = get_scheduled_villagers_for_node(session_id, node_id, current_minute=current_minute, persist_db=True)
    shifted_results: List[Dict[str, Any]] = []
    roster = ensure_folklore_villager_roster(session_id, persist_db=True)
    roster_by_id = {str(e.get("npc_id")): e for e in roster}

    for v in scheduled:
        if v.get("folklore_village") != "kitsune":
            continue
        spec = roster_by_id.get(str(v.get("npc_id"))) or v
        cur_race = str(spec.get("race") or "").strip().lower()
        init_form = str(spec.get("initial_form") or cur_race).strip().lower()
        ct = db.get_contact(session_id, str(spec.get("name") or ""))
        score = int((ct or {}).get("relationship_score") or spec.get("initial_affinity") or 0)
        if is_evening and cur_race == "kitsune:myobu_fox":
            res = shift_kitsune_form(
                session_id,
                str(spec["npc_id"]),
                "kitsune:humanoid",
                current_minute=safe_min,
                turn_number=turn_number,
                shift_reason="circadian_evening",
            )
            if res.get("shifted"):
                shifted_results.append(res)
        elif is_daytime and init_form == "kitsune:myobu_fox" and cur_race == "kitsune:humanoid":
            last_hist = (spec.get("form_history") or [{}])[-1]
            if score < 45 and not spec.get("bond_humanoid_unlocked") and last_hist.get("reason") == "circadian_evening":
                res = shift_kitsune_form(
                    session_id,
                    str(spec["npc_id"]),
                    "kitsune:myobu_fox",
                    current_minute=safe_min,
                    force=True,
                    turn_number=turn_number,
                    shift_reason="circadian_daytime_revert",
                )
                if res.get("shifted"):
                    shifted_results.append(res)
    return shifted_results


def _build_folklore_weapon_profile(race_val: str, village_key: str, tier: int) -> Dict[str, Any]:
    """Builds a mana-infused folklore spirit weapon profile capable of harming non-corporeal anomalies."""
    eff_tier = max(1, int(tier or 3))
    if is_myobu_fox_race(race_val):
        return {
            "name": "Sacred Kitsunebi Fangs & Claws",
            "damage_dice": "2d8",
            "damage_type": "fire",
            "atk_bonus": 6 + eff_tier * 3,
            "matk_bonus": 8 + eff_tier * 3,
            "is_mana_infused": True,
            "mundane_weapon": False,
        }
    if str(village_key or "").strip().lower() == "kitsune":
        return {
            "name": "Inari Kagura Spirit-Fan & Ofuda",
            "damage_dice": "2d8",
            "damage_type": "fire",
            "atk_bonus": 6 + eff_tier * 3,
            "matk_bonus": 8 + eff_tier * 3,
            "is_mana_infused": True,
            "mundane_weapon": False,
        }
    return {
        "name": "Kayangan Pamor Keris",
        "damage_dice": "2d8",
        "damage_type": "aether",
        "atk_bonus": 6 + eff_tier * 3,
        "matk_bonus": 8 + eff_tier * 3,
        "is_mana_infused": True,
        "mundane_weapon": False,
    }


def hydrate_village_cast_for_node(
    session_id: int,
    node_id: str,
    current_minute: int = 480,
    turn_number: int = 0,
) -> List[Dict[str, Any]]:
    """Hydrates any folklore villagers scheduled at an inner village room or glamour spot when the PC visits."""
    sync_kitsune_circadian_forms_for_node(session_id, node_id, current_minute=current_minute, turn_number=turn_number)
    scheduled = get_scheduled_villagers_for_node(session_id, node_id, current_minute=current_minute, persist_db=True)
    hydrated: List[Dict[str, Any]] = []
    veil_cache: Dict[str, Dict[str, Any]] = {}
    for entry in scheduled:
        if node_id in ("loc_et_fox_torii_tunnel", "loc_bunian_threshold_glade") and not entry.get("is_daytime_wanderer"):
            v_key_c = str(entry.get("folklore_village") or "")
            if v_key_c not in veil_cache:
                veil_cache[v_key_c] = get_village_veil_status(session_id, v_key_c)
            if not veil_cache[v_key_c].get("attuned"):
                continue
        ct = hydrate_folklore_villager_on_encounter(session_id, entry["npc_id"], turn_number=turn_number)
        if ct:
            hydrated.append(ct)
    return hydrated


def recruit_folklore_companion(
    session_id: int,
    npc_id_or_name: str,
    turn_number: int = 0,
) -> Dict[str, Any]:
    """
    Recruits a befriended folklore villager (including kitsune:myobu_fox as a fox-fire beast companion!)
    into session_party_npcs with their 5-ability folklore combat kit.
    """
    eff_turn = int(turn_number or db.get_effective_session_turn(session_id))
    ct = hydrate_folklore_villager_on_encounter(session_id, npc_id_or_name, turn_number=eff_turn)
    if not ct:
        return {"recruited": False, "reason": "not_found"}
    bi = ct.get("basic_info") or {}
    score = int(ct.get("relationship_score") or 0)
    if score < 20 and not bi.get("contact_added"):
        return {"recruited": False, "reason": "insufficient_trust"}

    tier = int(bi.get("agent_tier") or 3)
    abilities = list(bi.get("innate_abilities") or [])
    stats = dict(bi.get("stats") or _build_villager_stats(tier))
    max_hp = 70 + tier * 25
    max_mp = 50 + tier * 20
    race_str = str(ct.get("race") or "")
    v_key = str(bi.get("folklore_village") or ("kitsune" if "kitsune" in race_str.lower() else "bunian")).lower()
    is_fox = is_myobu_fox_race(race_str)
    attr = "fire" if (is_fox or v_key == "kitsune") else "aether"
    party_entry = {
        "npc_id": ct.get("npc_id"),
        "name": ct["name"],
        "role": bi.get("role") or "Folklore Companion",
        "anomalous_npc_tag": "folklore_villager",
        "is_special_agent": False,
        "race": race_str,
        "gender": ct.get("gender"),
        "is_folklore_villager": True,
        "is_beast_companion": is_fox,
        "folklore_village": v_key,
        "agent_tier": tier,
        "attribute": attr,
        "weapon_profile": _build_folklore_weapon_profile(race_str, v_key, tier),
        "recruited_turn": eff_turn,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": max_mp,
        "max_mp": max_mp,
        "stats": stats,
        "innate_abilities": abilities,
        "spells": abilities,
    }
    added = db.add_session_party_npc(session_id, party_entry)
    return {"recruited": bool(added), "companion": party_entry}


def resolve_glamour_wanderer_interaction(
    session_id: int,
    node_id: str,
    current_minute: int = 600,
    per_passed: bool = False,
    favor_completed: bool = False,
    user_id: int = 0,
    persist_db: bool = True,
    turn_number: int = 0,
) -> Dict[str, Any]:
    """
    Handles daytime (09:00–17:00) human-glamour wanderers in outer Sanctuary / Woods paths.
    Spotting their glamour tell (DC 13 PER) or completing a small favor grants that village's
    quest-locked Permission Token for free once per village per session.
    Supports pure preview (`persist_db=False`) during pre-turn stage evaluation.
    """
    safe_min = int(current_minute or 0) % 1440
    if not (540 <= safe_min <= 1020):
        return {"present": False, "reason": "outside_daytime_window"}

    roster = ensure_folklore_villager_roster(session_id, persist_db=persist_db)
    wanderer: Optional[Dict[str, Any]] = None
    for entry in roster:
        if not entry.get("is_daytime_wanderer"):
            continue
        sched_nodes = set((entry.get("schedule") or {}).values())
        if (
            node_id in sched_nodes
            or (
                entry["folklore_village"] == "kitsune"
                and node_id in ("loc_es_lantern_tea_street", "sub_es_lantern_steps", "loc_es_bamboo_footbath_bridge", "sub_es_vermilion_bridge")
            )
            or (
                entry["folklore_village"] == "bunian"
                and node_id in ("loc_forest_trails", "sub_trail_gateway", "sub_cedar_bridge")
            )
        ):
            wanderer = entry
            break

    if not wanderer:
        return {"present": False}

    village_key = str(wanderer["folklore_village"])
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    token_name = str(v_meta.get("permission_token_name") or "")

    sess = db.get_session(session_id) or {}
    gifted_map = dict(sess.get("folklore_free_tokens_granted") or {})
    already_granted = bool(gifted_map.get(village_key))
    eff_uid = int(user_id or sess.get("host_user_id") or 0)
    can_grant = bool((per_passed or favor_completed) and not already_granted and token_name and eff_uid)

    if not persist_db:
        return {
            "present": True,
            "villager": wanderer,
            "village_key": village_key,
            "glamour_tell": wanderer.get("glamour_tell", ""),
            "token_granted": can_grant,
            "staged": can_grant,
            "token_name": token_name if can_grant else "",
        }

    eff_turn = int(turn_number if turn_number else db.get_effective_session_turn(session_id))
    token_granted = False
    with db.UnitOfWork():
        ct = hydrate_folklore_villager_on_encounter(session_id, wanderer["npc_id"], turn_number=eff_turn)
        if can_grant:
            tok_meta = next(
                (v for v in (catalog.get("permission_tokens") or {}).values() if v.get("village_key") == village_key),
                {},
            )
            db.add_item(
                eff_uid,
                token_name,
                item_type="quest_item",
                effect=str(tok_meta.get("description") or "Parts the illusion veil of a hidden folklore village."),
                slot_cost=0,
                force=True,
                is_quest_locked=1,
            )
            gifted_map[village_key] = {
                "turn": eff_turn,
                "token_name": token_name,
                "user_id": eff_uid,
                "npc_id": wanderer["npc_id"],
            }
            db.update_session(session_id, extra={"folklore_free_tokens_granted": gifted_map})
            befriend_folklore_villager(session_id, wanderer["npc_id"], turn_number=eff_turn)
            token_granted = True

    return {
        "present": True,
        "villager": ct or wanderer,
        "village_key": village_key,
        "glamour_tell": wanderer.get("glamour_tell", ""),
        "token_granted": token_granted,
        "token_name": token_name if token_granted else "",
    }


from .folklore_roster_rollback import (  # noqa: E402
    commit_staged_folklore_ops,
    rollback_folklore_roster_state_after_turn,
)
