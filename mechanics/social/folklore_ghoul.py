"""
mechanics/social/folklore_ghoul.py
==================================
Domain mechanics for the Dual-Form Al-Ghul (`ghoul:humanoid` / `ghoul:canid`)
Folklore Race, Context & Prowl Driven Shifting, Distrusted Sentinel Toll/Nerve Gate,
Ossuary Blood-Truce Exile & Atonement, and Cross-Village Companion Banter.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

import db
from mechanics.world.locations.folklore_spirit_courts import (
    SPIRIT_FRONTIER_ZONE_IDS,
    adjust_spirit_court_reputation,
    ensure_spirit_court_faction_discovered,
    is_ghoul_council_distrusted,
)

log = logging.getLogger("hikayat.social.folklore_ghoul")

GHOUL_CANID_SPECIES: tuple[str, ...] = ("striped_hyena", "wolf", "coyote", "jackal")

CANID_SPECIES_SDXL_TAGS: Dict[str, str] = {
    "striped_hyena": "feral, quadruped, striped hyena, ash-grey brindle fur, dark dorsal mane, glowing pale amber eyes",
    "wolf": "feral, quadruped, gaunt grey wolf, slate-silver coat, glowing frost-pale eyes",
    "coyote": "feral, quadruped, lithe dusk coyote, ash-tan fur, pointed ears, glowing sodium-gold eyes",
    "jackal": "feral, quadruped, sleek black-backed jackal, obsidian and silver coat, narrow muzzle, glowing pale eyes",
}

CANID_SPECIES_PROSE_DESCS: Dict[str, str] = {
    "striped_hyena": "lean ash-maned striped hyena with bristling hackles and pale amber eyes",
    "wolf": "gaunt slate-furred cemetery wolf with frost-pale eyes and a silent low-slung stride",
    "coyote": "lithe dusk-coated coyote with sharp pricked ears and sodium-gold eyes",
    "jackal": "sleek obsidian-and-silver jackal with a narrow lupine muzzle and cold pale eyes",
}

GHOUL_CONTEMPORARY_FEMALE_NAMES: tuple[str, ...] = (
    "Layla Al-Masri",
    "Nadia Haddad",
    "Soraya Mansour",
    "Yara Khalil",
    "Mariam Darwish",
    "Dalia Qureshi",
    "Salma Nassar",
    "Rania Khoury",
)

GHOUL_CONTEMPORARY_MALE_NAMES: tuple[str, ...] = (
    "Zayd Al-Masri",
    "Tariq Haddad",
    "Karam Mansour",
    "Rami Khalil",
    "Sami Darwish",
    "Idris Qureshi",
    "Nabil Nassar",
    "Farid Khoury",
)

GHOUL_ENCLOSED_OR_CIVIL_NODES: frozenset[str] = frozenset({
    "sub_ghoul_sovereign_manor",
    "sub_ghoul_curio_morgue",
    "sub_ghoul_prep_gallery",
    "sub_ghoul_distillation_vault",
    "sub_ghoul_wake_lounge",
    "sub_ghoul_private_booth",
    "sub_ghoul_ledger_hall",
    "sub_ghoul_bell_columbarium",
    "sub_ghoul_suite_foyer",
    "sub_ghoul_suite_bedroom",
})

GHOUL_ASH_PIT_PROWL_NODES: frozenset[str] = frozenset({
    "sub_ghoul_sparring_pit",
    "sub_ghoul_trophy_rack",
    "loc_ghoul_kennel_pit",
})

GHOUL_OPEN_AIR_ENCLAVE_NODES: frozenset[str] = frozenset({
    "sub_ghoul_inner_plaza",
    "sub_ghoul_leyline_crypt",
})

GHOUL_SENTINEL_TOLL_GOLD = 35
GHOUL_ATONEMENT_GOLD = 100


def normalize_canid_species(species: Any, seed: str = "") -> str:
    """Normalizes a Ghoul's `canid_species` onto `striped_hyena|wolf|coyote|jackal`."""
    raw = str(species or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in GHOUL_CANID_SPECIES:
        return raw
    if "hyena" in raw:
        return "striped_hyena"
    if "wolf" in raw or "lupin" in raw:
        return "wolf"
    if "coyote" in raw:
        return "coyote"
    if "jackal" in raw:
        return "jackal"
    digest = hashlib.md5((seed or raw or "ghoul").encode("utf-8")).hexdigest()
    return GHOUL_CANID_SPECIES[int(digest[:8], 16) % len(GHOUL_CANID_SPECIES)]


def resolve_ghoul_contextual_form(
    node_id: str,
    *,
    current_minute: int = 480,
    in_combat: bool = False,
    default_humanoid_outside_hunt: bool = False,
    slot_key: str = "",
) -> str:
    """
    Context & Prowl Driven Shifting for Al-Ghul NPCs:
    - `ghoul:humanoid` inside enclave buildings, Dusk Confluence, and human city streets.
    - `ghoul:canid` on all 4 Frontier wilderness patrols, Ash-Pit Pack Grounds sparring,
      active combat, and late-night open-air prowls (22:00-04:59) inside the Pale Ossuary.
    - Exception: The Ghoul Heir, Apothecary Merchant, Sommelier, Archivist-Elder, and
      City-Wanderers stay `ghoul:humanoid` outside active combat/frontier hunts.
    """
    nid = str(node_id or "").strip()
    sk = str(slot_key or "").strip().lower()
    if in_combat:
        return "ghoul:canid"
    if nid.startswith((
        "sub_wilds_", "loc_wilds_",
        "sub_peaks_", "loc_peaks_",
        "sub_mire_", "loc_mire_",
        "sub_boneyard_", "loc_boneyard_",
    )) or nid in SPIRIT_FRONTIER_ZONE_IDS:
        if default_humanoid_outside_hunt or sk in ("ghoul_sovereign_heir", "ghoul_merchant", "ghoul_elder", "ghoul_bartender"):
            # Only trackers/sentinels/pack alphas prowl frontiers in canid outside combat unless hunting
            return "ghoul:humanoid"
        return "ghoul:canid"
    if nid in GHOUL_ASH_PIT_PROWL_NODES and not default_humanoid_outside_hunt and sk not in ("ghoul_sovereign_heir", "ghoul_merchant"):
        return "ghoul:canid"
    safe_min = int(current_minute or 0) % 1440
    is_late_night_prowl = safe_min >= 1320 or safe_min < 300
    if is_late_night_prowl and nid in GHOUL_OPEN_AIR_ENCLAVE_NODES and not default_humanoid_outside_hunt:
        return "ghoul:canid"
    return "ghoul:humanoid"


def shift_ghoul_form(
    session_id: int,
    npc_id_or_name: str,
    target_form: str,
    *,
    turn_number: Optional[int] = None,
    shift_reason: str = "context_prowl",
    conn: Any = None,
    roster: Optional[List[Dict[str, Any]]] = None,
    defer_roster_save: bool = False,
) -> Dict[str, Any]:
    """
    Atomically transitions an Al-Ghul villager between `ghoul:humanoid` and `ghoul:canid`.
    Updates `contacts.race`, `contacts.track` (clamping romantic -> platonic in canid form
    and restoring `romantic` when shifting back to `ghoul:humanoid`),
    `lorebook`, `actor_physical_states`, 6-slot `actor_garments`, and turn-stamped `form_history`.
    """
    from .folklore_roster_lifecycle import (
        _sync_villager_physical_garments,
        hydrate_folklore_villager_on_encounter,
    )
    from .folklore_roster import ensure_folklore_villager_roster
    from mechanics.world.locations.folklore_veil import load_folklore_villages_catalog

    norm_target = str(target_form or "").strip().lower()
    if norm_target not in ("ghoul:humanoid", "ghoul:canid"):
        raise ValueError(f"Invalid ghoul target form: {target_form}")

    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    with (db.UnitOfWork() if conn is None else _NullCtx(conn)) as c:
        ct = hydrate_folklore_villager_on_encounter(session_id, npc_id_or_name, turn_number=eff_turn)
        if not ct:
            return {"shifted": False, "reason": "not_found"}

        cur_race = str(ct.get("race") or "").strip().lower()
        if not cur_race.startswith("ghoul:"):
            return {"shifted": False, "reason": "not_ghoul"}
        if cur_race == norm_target:
            return {"shifted": False, "reason": "already_in_form", "new_form": norm_target}

        catalog = load_folklore_villages_catalog()
        kits = catalog.get("combat_kits") or {}
        eff_roster = roster if roster is not None else ensure_folklore_villager_roster(session_id, persist_db=True, conn=c)
        spec = next((e for e in eff_roster if str(e.get("npc_id")) == str(ct.get("npc_id"))), None) or {}
        humanoid_kit_key = str(spec.get("humanoid_kit_key") or "ghoul_humanoid_duelist")
        new_kit_key = "ghoul_canid_beast" if norm_target == "ghoul:canid" else humanoid_kit_key
        new_abilities = list(kits.get(new_kit_key) or [])

        app = dict(ct.get("appearance") or {})
        canid_sp = normalize_canid_species(app.get("canid_species") or spec.get("canid_species"), seed=str(ct["name"]))
        humanoid_outfit = str(app.get("humanoid_outfit") or "Dark-tailored charcoal wool coat over a black silk shirt")
        app["canid_species"] = canid_sp
        app["ghoul_form"] = norm_target
        app["coat_color"] = str(app.get("fur_coat") or "ash-grey charcoal coat") if norm_target == "ghoul:canid" else ""
        app["outfit_style"] = "" if norm_target == "ghoul:canid" else humanoid_outfit
        app["outfit_summary"] = (
            f"Quadruped {canid_sp.replace('_', ' ')} canid form wearing only an iron-silver pack collar"
            if norm_target == "ghoul:canid"
            else humanoid_outfit
        )

        row = c.execute("SELECT id, basic_info_json, track FROM contacts WHERE id = ?", (ct["id"],)).fetchone()
        bi = json.loads(row["basic_info_json"] or "{}") if row else {}
        prev_track = str((row["track"] if row else None) or "platonic")
        bi["race"] = norm_target
        bi["canid_species"] = canid_sp
        bi["combat_kit_key"] = new_kit_key
        bi["innate_abilities"] = new_abilities
        restored_track = prev_track
        if norm_target == "ghoul:humanoid" and prev_track == "platonic":
            for hist_item in reversed(list(spec.get("form_history") or [])):
                if not isinstance(hist_item, dict):
                    continue
                if str(hist_item.get("new_form") or "").strip().lower() == "ghoul:canid":
                    saved_prev = str(hist_item.get("prev_track") or "").strip().lower()
                    if saved_prev == "romantic":
                        restored_track = "romantic"
                    break
        new_track = "platonic" if norm_target == "ghoul:canid" else restored_track
        c.execute(
            "UPDATE contacts SET race = ?, track = ?, basic_info_json = ?, appearance_json = ?, updated_at = ? WHERE id = ?",
            (norm_target, new_track, json.dumps(bi), json.dumps(app), time.time(), ct["id"]),
        )
        c.execute(
            "UPDATE lorebook SET race = ?, appearance_json = ? WHERE session_id = ? AND lower(name) = ?",
            (norm_target, json.dumps(app), session_id, ct["name"].lower()),
        )
        _sync_villager_physical_garments(c, session_id, ct["name"], norm_target, humanoid_outfit)

        for entry in eff_roster:
            if str(entry.get("npc_id")) == str(ct.get("npc_id")):
                hist = list(entry.get("form_history") or [])
                hist.append({
                    "turn": eff_turn,
                    "prev_form": cur_race,
                    "prev_track": prev_track,
                    "new_form": norm_target,
                    "reason": shift_reason,
                })
                entry["form_history"] = hist[-12:]
                entry["race"] = norm_target
                entry["combat_kit_key"] = new_kit_key
                entry["innate_abilities"] = new_abilities
                entry["appearance"] = app
                break
        if not defer_roster_save:
            db.update_session(session_id, extra={"folklore_villager_roster": eff_roster})

    return {
        "shifted": True,
        "name": ct["name"],
        "new_form": norm_target,
        "canid_species": canid_sp,
        "abilities": new_abilities,
    }


def sync_ghoul_contextual_forms_for_node(
    session_id: int,
    node_id: str,
    *,
    current_minute: int = 480,
    in_combat: bool = False,
    turn_number: int = 0,
) -> List[Dict[str, Any]]:
    """Synchronizes Al-Ghul NPCs scheduled at `node_id` into their contextual humanoid/canid form."""
    from .folklore_roster import ensure_folklore_villager_roster, get_scheduled_villagers_for_node

    if not session_id or not node_id:
        return []
    results: List[Dict[str, Any]] = []
    with db.UnitOfWork() as c:
        scheduled = get_scheduled_villagers_for_node(session_id, node_id, current_minute=current_minute, persist_db=True)
        roster = ensure_folklore_villager_roster(session_id, persist_db=True, conn=c)
        by_id = {str(e.get("npc_id")): e for e in roster}
        any_shifted = False
        for v in scheduled:
            if v.get("folklore_village") != "ghoul":
                continue
            spec = by_id.get(str(v.get("npc_id"))) or v
            target_form = resolve_ghoul_contextual_form(
                node_id,
                current_minute=current_minute,
                in_combat=in_combat,
                default_humanoid_outside_hunt=bool(spec.get("default_humanoid_outside_hunt")),
                slot_key=str(spec.get("slot_key") or ""),
            )
            if str(spec.get("race") or "").strip().lower() != target_form:
                res = shift_ghoul_form(
                    session_id,
                    str(spec["npc_id"]),
                    target_form,
                    turn_number=turn_number,
                    shift_reason="context_prowl",
                    conn=c,
                    roster=roster,
                    defer_roster_save=True,
                )
                if res.get("shifted"):
                    any_shifted = True
                    results.append(res)
        if any_shifted:
            db.update_session(session_id, extra={"folklore_villager_roster": roster})
    return results


def evaluate_ghoul_sentinel_gate(
    session_id: int,
    target_node_id: str,
    *,
    current_day: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Enforces the Pale Ossuary's Distrusted Sentinel rule:
    - While Ghoul Council standing < 0:
      - At `sub_ghoul_inner_plaza` (if not cleared today): sentinels demand a 35g outsider
        toll OR a CHA/INT/STR nerve check (never attack on sight).
      - Inner private chambers (`sub_ghoul_sovereign_manor`, `fac_ghoul_guest_manor`, etc.) remain
        gated until Council standing reaches Neutral (0+), even if toll is paid.
      - Public inner shops/parlors (`sub_ghoul_curio_morgue`, `loc_ghoul_*`) require plaza clearance
        or Neutral (0+) Court standing.
    """
    nid = str(target_node_id or "").strip()
    is_ghoul_inner = nid.startswith(("sub_ghoul_", "loc_ghoul_", "fac_ghoul_")) or nid == "loc_hidden_ghoul_village"
    if not session_id or not is_ghoul_inner:
        return {"gated": False, "distrusted": False}

    distrusted = is_ghoul_council_distrusted(int(session_id))
    if not distrusted:
        return {"gated": False, "distrusted": False}

    sess = db.get_session(int(session_id)) or {}
    eff_day = int(current_day if current_day is not None else (sess.get("current_day") or 1))
    ex = sess.get("extra") if isinstance(sess.get("extra"), dict) else {}
    srs = (
        sess.get("spirit_realm_state")
        if isinstance(sess.get("spirit_realm_state"), dict)
        else (ex.get("spirit_realm_state") if isinstance(ex.get("spirit_realm_state"), dict) else {})
    )
    cleared_day = int(srs.get("ghoul_plaza_clearance_day") or 0)
    has_day_pass = (cleared_day == eff_day)

    private_gated = nid in (
        "sub_ghoul_sovereign_manor",
        "fac_ghoul_guest_manor",
        "sub_ghoul_suite_foyer",
        "sub_ghoul_suite_bedroom",
        "sub_ghoul_bell_columbarium",
    )
    if private_gated:
        return {
            "gated": True,
            "distrusted": True,
            "reason": "ghoul_distrusted_private_chamber",
            "requires_neutral_rep": True,
            "has_day_pass": has_day_pass,
            "message": "Pale Ossuary sentinels bar inner private chambers until the Court no longer views you as Distrusted (standing 0+).",
        }
    from mechanics.world.world_events.spirit_realm_events import is_ghoul_entry_toll_waived

    if is_ghoul_entry_toll_waived(int(session_id)):
        return {
            "gated": False,
            "distrusted": True,
            "requires_plaza_clearance": False,
            "has_day_pass": has_day_pass,
            "toll_waived": True,
            "toll_gold": 0,
            "waiver_event": "evt_spirit_pale_wake",
        }
    if has_day_pass or nid == "sub_ghoul_inner_plaza":
        return {
            "gated": False,
            "distrusted": True,
            "requires_plaza_clearance": (nid == "sub_ghoul_inner_plaza" and not has_day_pass),
            "has_day_pass": has_day_pass,
            "toll_waived": False,
            "toll_gold": GHOUL_SENTINEL_TOLL_GOLD,
        }
    return {
        "gated": True,
        "distrusted": True,
        "reason": "ghoul_sentinel_toll_or_nerve_required",
        "has_day_pass": False,
        "toll_waived": False,
        "toll_gold": GHOUL_SENTINEL_TOLL_GOLD,
        "message": (
            f"Ghoul sentinels on Ashen Cypress Funeral Square bar passage inward until you pay the {GHOUL_SENTINEL_TOLL_GOLD}g "
            "outsider toll or pass a steady nerve check."
        ),
    }


def resolve_ghoul_sentinel_clearance(
    session_id: int,
    *,
    method: str = "toll",
    stat: str = "CHA",
    user_id: Optional[int] = None,
    roll_override: Optional[int] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Resolves the Distrusted Sentinel challenge at `sub_ghoul_inner_plaza`:
    - `method="toll"`: pays 35g outsider toll (0g while `evt_spirit_pale_wake` is active) and grants daily Ossuary passage.
    - `method="nerve"`: evaluates `CHA`/`INT`/`STR` (DC 11); success grants daily passage + +5 Ghoul Court rep.
    """
    if not session_id:
        return {"ok": False, "reason": "invalid_session"}

    from mechanics.world.world_events.spirit_realm_events import is_ghoul_entry_toll_waived

    clean_m = str(method or "toll").strip().lower()
    stat_u = str(stat or "CHA").strip().upper()
    if stat_u not in ("CHA", "INT", "STR"):
        stat_u = "CHA"
    toll_waived = is_ghoul_entry_toll_waived(int(session_id))

    with db.UnitOfWork() as conn:
        s_row = conn.execute(
            "SELECT current_day, host_user_id, character_id, extra_json FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchone()
        if not s_row:
            return {"ok": False, "reason": "session_not_found"}
        eff_day = int(s_row["current_day"] or 1)
        eff_uid = int(user_id or s_row["host_user_id"] or 0)
        eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(int(session_id)))

        ensure_spirit_court_faction_discovered(int(session_id), "ghoul", turn_number=eff_turn, conn=conn)
        gold_paid = 0
        payer_cid = 0
        rep_delta = 0

        if clean_m == "toll":
            if not toll_waived:
                char_row = None
                if eff_uid:
                    char_row = conn.execute(
                        "SELECT id, gold FROM characters WHERE user_id = ? ORDER BY active_session_id = ? DESC, is_active DESC, id DESC LIMIT 1",
                        (eff_uid, int(session_id)),
                    ).fetchone()
                elif s_row["character_id"]:
                    char_row = conn.execute("SELECT id, gold FROM characters WHERE id = ?", (int(s_row["character_id"]),)).fetchone()
                cur_gold = int(char_row["gold"] or 0) if char_row else 0
                if not char_row or cur_gold < GHOUL_SENTINEL_TOLL_GOLD:
                    return {"ok": False, "reason": "insufficient_gold", "required": GHOUL_SENTINEL_TOLL_GOLD, "gold": cur_gold}
                gold_paid = GHOUL_SENTINEL_TOLL_GOLD
                payer_cid = int(char_row["id"])
                conn.execute("UPDATE characters SET gold = gold - ? WHERE id = ?", (gold_paid, payer_cid))
        elif clean_m == "nerve":
            char = db.get_character(eff_uid, session_id=int(session_id)) if eff_uid else None
            stat_val = int((char or {}).get(stat_u.lower(), 5) or 5)
            eff_roll = int(roll_override) if roll_override is not None else (stat_val + 6)
            if eff_roll < 11:
                return {"ok": False, "reason": "nerve_check_failed", "stat": stat_u, "roll": eff_roll, "dc": 11}
            rep_res = adjust_spirit_court_reputation(
                int(session_id),
                "ghoul",
                5,
                reason=f"ghoul_sentinel_nerve_{stat_u.lower()}",
                turn_number=eff_turn,
                conn=conn,
            )
            rep_delta = int(rep_res.get("delta") or 0)
        else:
            return {"ok": False, "reason": "unknown_method"}

        ex = json.loads(s_row["extra_json"] or "{}") if s_row["extra_json"] else {}
        srs = dict(ex.get("spirit_realm_state") or {})
        if int(srs.get("ghoul_plaza_clearance_turn") or 0) != eff_turn:
            srs["prev_ghoul_plaza_clearance_day"] = int(srs.get("ghoul_plaza_clearance_day") or 0)
        srs["ghoul_plaza_clearance_day"] = eff_day
        srs["ghoul_plaza_clearance_turn"] = eff_turn
        srs["ghoul_plaza_toll_gold_paid"] = gold_paid
        srs["ghoul_plaza_toll_payer_cid"] = payer_cid
        ex["spirit_realm_state"] = srs
        conn.execute("UPDATE sessions SET extra_json = ? WHERE id = ?", (json.dumps(ex, default=str), int(session_id)))

    return {
        "ok": True,
        "method": clean_m,
        "stat": stat_u if clean_m == "nerve" else "NONE",
        "gold_paid": gold_paid,
        "toll_waived": bool(toll_waived and clean_m == "toll"),
        "rep_gained": rep_delta,
        "cleared_day": eff_day,
        "turn_number": eff_turn,
    }


def build_rival_companion_enclave_banter(
    session_id: int,
    current_node_id: Optional[str],
    party_npcs: Sequence[Mapping[str, Any]],
) -> str:
    """
    When bringing a recruited Spirit companion from Court X into opposing Enclave Y
    (`kitsune`, `bunian`, or `ghoul`), builds reactive suspicion/banter prompt cues
    (softening into grudging respect when both courts stand >= 40).
    """
    from mechanics.world.locations.folklore_spirit_realm import (
        get_effective_village_standing,
        infer_spirit_village_for_node,
    )

    host_village = infer_spirit_village_for_node(current_node_id)
    if host_village not in ("kitsune", "bunian", "ghoul") or not party_npcs:
        return ""
    if str(current_node_id or "").strip() in ("loc_et_fox_torii_tunnel", "loc_bunian_threshold_glade", "sub_uc_black_font"):
        return ""

    host_labels = {
        "kitsune": "Sato-no-Inari Kitsune",
        "bunian": "Kampung Kayangan Bunian",
        "ghoul": "Pale Ossuary Al-Ghul",
    }
    cues: List[str] = []
    for p in party_npcs:
        if not isinstance(p, Mapping):
            continue
        p_name = str(p.get("name") or "").strip()
        if not p_name:
            continue
        p_bi = p.get("basic_info") if isinstance(p.get("basic_info"), Mapping) else {}
        p_race = str(p.get("race") or p_bi.get("race") or "").lower()
        comp_village = str(p.get("folklore_village") or p_bi.get("folklore_village") or "").strip().lower()
        if not comp_village:
            if "kitsune" in p_race:
                comp_village = "kitsune"
            elif "bunian" in p_race:
                comp_village = "bunian"
            elif "ghoul" in p_race:
                comp_village = "ghoul"
        if comp_village not in ("kitsune", "bunian", "ghoul") or comp_village == host_village:
            continue

        host_rep = get_effective_village_standing(session_id, host_village, court_only=True) if session_id else 0
        comp_rep = get_effective_village_standing(session_id, comp_village, court_only=True) if session_id else 0
        high_dual = (host_rep >= 40 and comp_rep >= 40)

        if "ghoul" in (host_village, comp_village):
            if high_dual:
                cues.append(
                    f"{p_name} ({host_labels[comp_village]}) walks beside you under your personal Veil vouch; "
                    f"{host_labels[host_village]} elders trade dry, grudgingly respectful jabs rather than baring steel."
                )
            else:
                cues.append(
                    f"{host_labels[host_village]} sentinels narrow their eyes at {p_name} ({host_labels[comp_village]})—only "
                    "your personal Veil vouch keeps bristling fangs, foxfire, or keris blades sheathed amidst icy rival banter."
                )
        else:
            if high_dual:
                cues.append(
                    f"{p_name} ({host_labels[comp_village]}) draws knowing smiles and polished diplomatic banter from {host_labels[host_village]} hosts."
                )
            else:
                cues.append(
                    f"{host_labels[host_village]} onlookers murmur warily around {p_name} ({host_labels[comp_village]}), prompting quick, poised courtly repartee under your Veil vouch."
                )

    if not cues:
        return ""
    return "[RIVAL SPIRIT COURT COMPANION VOUCH]: " + " ".join(cues)


class _NullCtx:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def __enter__(self) -> Any:
        return self._conn

    def __exit__(self, *_exc: Any) -> None:
        return None


__all__ = [
    "CANID_SPECIES_PROSE_DESCS",
    "CANID_SPECIES_SDXL_TAGS",
    "GHOUL_ATONEMENT_GOLD",
    "GHOUL_CANID_SPECIES",
    "GHOUL_CONTEMPORARY_FEMALE_NAMES",
    "GHOUL_CONTEMPORARY_MALE_NAMES",
    "GHOUL_SENTINEL_TOLL_GOLD",
    "build_rival_companion_enclave_banter",
    "evaluate_ghoul_sentinel_gate",
    "normalize_canid_species",
    "resolve_ghoul_contextual_form",
    "resolve_ghoul_sentinel_clearance",
    "shift_ghoul_form",
    "sync_ghoul_contextual_forms_for_node",
]
