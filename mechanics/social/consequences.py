from __future__ import annotations

"""Deterministic Social Turn Consequences, Bystander Ripples & Fog-of-War Dossier Unmasking.

Handles:
1. 4-tier check outcome adjustments (`CHA` -1 non-crit fail cushion, covert magic detection backfire).
2. Non-cruel `friction_rivalry` respect payoffs with Proud/Rebellious/Delinquent NPCs + `rival` tie formation.
3. Connected bystander reactions (romantic partner jealousy on bold flirts; kin/best-friend defensiveness on cruel insults).
4. Fog-of-War `"???"` Dossier fact selection, Gift preference auto-unmasking, and co-op earshot fan-out.
"""

import json
import re
from typing import Any

import db
from mechanics.social import locales, pacing
import mechanics.social.persona as persona
import mechanics.social.relationship_graph as rg

RESPECTS_FRICTION_TOKENS: tuple[str, ...] = (
    "proud",
    "rebellious",
    "delinquent",
    "stoic",
    "fierce",
    "bold",
    "competitive",
    "stubborn",
    "brat",
    "warrior",
    "mercenary",
    "rival",
)


def resolve_canonical_npc_dossier_facts(
    contact_or_npc: dict[str, Any] | None,
    *,
    scenario: str = "fantasy",
) -> dict[str, list[str]]:
    """Computes an NPC's deterministic underlying traits, likes, and dislikes without exposing them to UI."""
    c = dict(contact_or_npc or {})
    basic = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
    name = str(c.get("name") or basic.get("name") or c.get("npc_id") or "npc").strip()
    role = str(basic.get("role") or basic.get("occupation") or c.get("role") or "").strip()
    race = str(c.get("race") or basic.get("race") or "human").strip()
    desc = basic.get("description") or c.get("description") or ""
    if isinstance(desc, dict):
        desc = " ".join(str(v) for v in desc.values() if v)

    raw_traits = list(c.get("unlocked_traits") or c.get("traits") or basic.get("traits") or [])
    raw_prefs: list[str] = []
    if isinstance(c.get("preferences"), list):
        raw_prefs.extend(str(x) for x in c["preferences"] if str(x).strip() and "???" not in str(x))
    if isinstance(c.get("dislikes"), list):
        for d in c["dislikes"]:
            if str(d).strip() and "???" not in str(d):
                raw_prefs.append(persona.format_preference_phrase(str(d), is_dislike=True))
    if not raw_prefs:
        for l_item in (basic.get("likes") or []):
            if str(l_item).strip():
                raw_prefs.append(persona.format_preference_phrase(str(l_item), is_dislike=False))
        for d_item in (basic.get("dislikes") or []):
            if str(d_item).strip():
                raw_prefs.append(persona.format_preference_phrase(str(d_item), is_dislike=True))

    traits_clean = [t for t in raw_traits if str(t).strip() and "???" not in str(t)]
    gen_traits, gen_prefs = persona.split_traits_and_preferences(
        traits_clean,
        raw_prefs,
        role=role,
        race=race or "human",
        seed_str=f"{name}_{desc}_{scenario}",
    )
    likes, dislikes = persona.categorize_likes_and_dislikes(
        gen_prefs,
        traits=gen_traits,
        role=role,
        race=race or "human",
        desc=f"{name}_{desc}",
    )
    return {
        "traits": [str(t).strip() for t in gen_traits if str(t).strip()],
        "likes": [str(l).strip() for l in likes if str(l).strip()],
        "dislikes": [str(d).strip() for d in dislikes if str(d).strip()],
    }


def _npc_respects_friction(contact_obj: dict[str, Any] | None, canonical_traits: list[str]) -> bool:
    basic = (contact_obj or {}).get("basic_info") if isinstance((contact_obj or {}).get("basic_info"), dict) else {}
    haystack = " ".join(
        [
            " ".join(canonical_traits),
            str(basic.get("role") or ""),
            str(basic.get("description") or ""),
            str((contact_obj or {}).get("role") or ""),
        ]
    ).lower()
    return any(tok in haystack for tok in RESPECTS_FRICTION_TOKENS)


def _evaluate_bystander_deltas(
    session_id: int,
    target_npc_name: str,
    category: str,
    outcome_tier: str,
    is_cruel: bool,
    present_bystanders: list[str] | None,
) -> dict[str, int]:
    deltas: dict[str, int] = {}
    if not session_id or not present_bystanders:
        return deltas

    target_canon = rg.canonical_person_key(target_npc_name)
    try:
        player_ties = rg.get_ties(session_id, "player")
    except Exception:
        player_ties = []
    try:
        target_ties = rg.get_ties(session_id, target_canon)
    except Exception:
        target_ties = []

    player_rom_partners: set[str] = set()
    for t in player_ties:
        if str(t.get("status") or "active") != "active":
            continue
        other = t.get("person_b_key") if t.get("person_a_key") == "player" else t.get("person_a_key")
        if other and str(t.get("tie_type") or "") in rg.ROMANTIC_TYPES:
            player_rom_partners.add(str(other))

    target_allies: set[str] = set()
    target_rivals: set[str] = set()
    for t in target_ties:
        if str(t.get("status") or "active") != "active":
            continue
        other = t.get("person_b_key") if t.get("person_a_key") == target_canon else t.get("person_a_key")
        if not other or other == "player":
            continue
        tt = str(t.get("tie_type") or "")
        if tt in (rg.ROMANTIC_TYPES | {rg.TIETYPE_BEST_FRIEND, rg.TIETYPE_FRIEND}):
            target_allies.add(str(other))
        elif tt in rg.ANTAGONISTIC_TYPES:
            target_rivals.add(str(other))

    for by_name in present_bystanders:
        b_clean = str(by_name or "").strip()
        if not b_clean or b_clean.lower() == target_npc_name.strip().lower():
            continue
        b_canon = rg.canonical_person_key(b_clean)
        delta = 0

        # 1. Publicly flirting with someone else in front of a romantic partner sparks jealousy
        if category == "flirt_chemistry" and b_canon in player_rom_partners:
            delta = -3 if outcome_tier in ("success", "crit_success", "critical_success") else -2
        # 2. Cruel hostility / humiliation in front of target's partner/best-friend vs rival
        elif is_cruel or (category == "friction_rivalry" and outcome_tier in ("crit_fail", "critical_failure")):
            if b_canon in target_allies:
                delta = -2
            elif b_canon in target_rivals and is_cruel:
                delta = 1

        deltas[b_clean] = delta

    return deltas


def select_and_record_dialogue_discoveries(
    session_id: int,
    character_id: int,
    npc_name: str,
    *,
    category: str,
    topic_id: str = "",
    outcome_tier: str = "success",
    contact_obj: dict[str, Any] | None = None,
    scenario: str = "fantasy",
    turn_number: int = 0,
    earshot_character_ids: list[int] | None = None,
) -> list[dict[str, str]]:
    """Unlocks 1 (success) or 2 (crit_success) previously unrevealed Dossier facts on relevant checks."""
    tier = str(outcome_tier or "").strip().lower()
    cat = str(category or "").strip().lower()
    is_pass = tier in ("success", "crit_success", "critical_success", "partial_success", "mixed_success")

    # Guarded trait slip on Friction crit_success or high-tension clash
    allows_reveal = is_pass and cat in ("get_to_know", "friendly_situational", "callbacks_history", "friction_rivalry", "flirt_chemistry")
    if not allows_reveal or not session_id:
        return []

    canon_facts = resolve_canonical_npc_dossier_facts(contact_obj or {"name": npc_name}, scenario=scenario)
    existing = db.get_contact_dossier_discoveries(session_id, int(character_id or 0), npc_name)
    known_keys = {f"{d['fact_category']}:{str(d['fact_value']).lower()}" for d in existing}
    has_sched = any(d["fact_category"] == "schedule" for d in existing)

    candidates: list[dict[str, str]] = []
    t_low = str(topic_id or "").lower()
    if "routine" in t_low or "schedule" in t_low:
        if not has_sched:
            candidates.append({"fact_category": "schedule", "fact_key": "schedule:all", "fact_value": "Daily Routine"})

    for tr in canon_facts["traits"]:
        if f"trait:{tr.lower()}" not in known_keys:
            candidates.append({"fact_category": "trait", "fact_key": f"trait:{tr.lower()}", "fact_value": tr})
    for lk in canon_facts["likes"]:
        if f"like:{lk.lower()}" not in known_keys:
            candidates.append({"fact_category": "like", "fact_key": f"like:{lk.lower()}", "fact_value": lk})
    for dl in canon_facts["dislikes"]:
        if f"dislike:{dl.lower()}" not in known_keys:
            candidates.append({"fact_category": "dislike", "fact_key": f"dislike:{dl.lower()}", "fact_value": dl})
    if not has_sched:
        candidates.append({"fact_category": "schedule", "fact_key": "schedule:all", "fact_value": "Daily Routine"})

    if not candidates:
        return []

    reveal_count = 2 if tier in ("crit_success", "critical_success") else 1
    chosen = candidates[:reveal_count]
    char_targets = list(earshot_character_ids) if earshot_character_ids else [int(character_id or 0)]
    if int(character_id or 0) not in char_targets:
        char_targets.insert(0, int(character_id or 0))

    db.record_contact_dossier_discoveries(
        session_id,
        npc_name,
        chosen,
        character_ids=char_targets,
        discovered_turn=turn_number,
        primary_character_id=int(character_id or 0),
        discovery_source="dialogue",
    )
    return chosen


def evaluate_social_turn_consequences(
    session_id: int,
    character_id: int,
    npc_name: str,
    *,
    stat: str = "CHA",
    category: str = "friendly_situational",
    topic_id: str = "",
    outcome_tier: str = "success",
    base_affinity_delta: int = 0,
    is_cruel: bool = False,
    is_covert_ability: bool = False,
    present_bystanders: list[str] | None = None,
    earshot_character_ids: list[int] | None = None,
    scenario: str = "fantasy",
    turn_number: int = 0,
    already_cushioned: bool = False,
) -> dict[str, Any]:
    """Evaluates 4-tier social check consequences, CHA fail cushioning, rivalry respect, and bystander ripples."""
    st = str(stat or "CHA").strip().upper()
    cat = str(category or "").strip().lower()
    tier = str(outcome_tier or "success").strip().lower()
    adj_delta = int(base_affinity_delta or 0)
    cha_cushioned = bool(already_cushioned)
    magic_backfire = False
    rival_sparked = False

    contact_obj: dict[str, Any] | None = None
    if session_id:
        try:
            canon_target = db.canon_social_npc_id(npc_name)
            for c_row in db.get_contacts(session_id, character_id=int(character_id or 0)):
                if db.canon_social_npc_id(c_row.get("npc_id") or c_row.get("name") or "") == canon_target:
                    contact_obj = c_row
                    break
        except Exception:
            contact_obj = None

    canon_facts = resolve_canonical_npc_dossier_facts(contact_obj or {"name": npc_name}, scenario=scenario)

    # 1. Covert mental/charm magic detection backfire on fail / crit_fail
    if is_covert_ability and tier in ("fail", "failure", "crit_fail", "critical_failure"):
        magic_backfire = True
        adj_delta = min(adj_delta, -6 if tier in ("crit_fail", "critical_failure") else -4)
    # 2. CHA cushions non-crit fail affinity loss by +1 (up to 0 ceiling)
    elif st == "CHA" and tier in ("fail", "failure") and adj_delta < 0 and not already_cushioned:
        adj_delta = min(0, adj_delta + 1)
        cha_cushioned = True

    # 3. Non-cruel Friction pass: grudging respect with Proud/Rebellious NPCs + rival tie
    if cat == "friction_rivalry" and not is_cruel and tier in ("success", "crit_success", "critical_success"):
        if _npc_respects_friction(contact_obj, canon_facts["traits"]):
            adj_delta = max(2 if tier == "success" else 3, adj_delta)
        else:
            adj_delta = max(0, adj_delta)

        if session_id:
            try:
                existing_ties = rg.get_ties(session_id, "player")
                npc_pkey = rg.canonical_person_key(npc_name)
                has_close_bond = any(
                    str(t.get("status") or "active") == "active"
                    and (t.get("person_a_key") == npc_pkey or t.get("person_b_key") == npc_pkey)
                    and str(t.get("tie_type") or "") in (
                        rg.ROMANTIC_TYPES | {rg.TIETYPE_FRIEND, rg.TIETYPE_BEST_FRIEND, rg.TIETYPE_RIVAL}
                    )
                    for t in existing_ties
                )
                if not has_close_bond:
                    rg.form_tie(session_id, "player", npc_name, rg.TIETYPE_RIVAL, closeness=45, turn=turn_number)
                    rival_sparked = True
                elif any(
                    str(t.get("status") or "active") == "active"
                    and (t.get("person_a_key") == npc_pkey or t.get("person_b_key") == npc_pkey)
                    and str(t.get("tie_type") or "") == rg.TIETYPE_RIVAL
                    for t in existing_ties
                ):
                    rival_sparked = True
            except Exception:
                pass

    # 4. Clearing Clear-the-Air gate when a clear_the_air stance succeeds
    if cat == "clear_the_air" and tier in ("success", "crit_success", "critical_success") and session_id:
        db.clear_clear_the_air_gate(session_id, npc_name)

    # 5. Connected bystander reactions (partners, allies, rivals; unrelated bystanders stay 0)
    bystander_deltas = _evaluate_bystander_deltas(
        session_id=session_id,
        target_npc_name=npc_name,
        category=cat,
        outcome_tier=tier,
        is_cruel=is_cruel,
        present_bystanders=present_bystanders,
    )

    # 6. Unlock Dossier facts on passing check
    discoveries = select_and_record_dialogue_discoveries(
        session_id=session_id,
        character_id=character_id,
        npc_name=npc_name,
        category=cat,
        topic_id=topic_id,
        outcome_tier=tier,
        contact_obj=contact_obj,
        scenario=scenario,
        turn_number=turn_number,
        earshot_character_ids=earshot_character_ids,
    )

    return {
        "adjusted_affinity_delta": adj_delta,
        "cha_cushioned": cha_cushioned,
        "magic_backfire": magic_backfire,
        "rival_sparked": rival_sparked,
        "bystander_deltas": bystander_deltas,
        "discoveries": discoveries,
    }


def unmask_preferences_on_gift(
    session_id: int,
    character_id: int,
    npc_name: str,
    item_name: str,
    *,
    turn_number: int = 0,
    earshot_character_ids: list[int] | None = None,
    scenario: str = "fantasy",
) -> list[dict[str, str]]:
    """Auto-unmasks any Like or Dislike matched by a gifted item in contact_dossier_discoveries."""
    gift_clean = str(item_name or "").strip().lower()
    if not session_id or not gift_clean:
        return []

    contact_obj = None
    canon_target = db.canon_social_npc_id(npc_name)
    for c_row in db.get_contacts(session_id, character_id=int(character_id or 0)):
        if db.canon_social_npc_id(c_row.get("npc_id") or c_row.get("name") or "") == canon_target:
            contact_obj = c_row
            break

    canon_facts = resolve_canonical_npc_dossier_facts(contact_obj or {"name": npc_name}, scenario=scenario)
    gift_base = re.sub(r"\b(aged|cheap|vintage|rare|imported|instant|sweet|fresh|warm|hot|cold|bowl|of|box|cup)\b", "", gift_clean).strip()

    matched_records: list[dict[str, str]] = []
    for fact_cat, items in (("like", canon_facts["likes"]), ("dislike", canon_facts["dislikes"])):
        for p_phrase in items:
            p_core = re.sub(
                r"^(likes|dislikes|prefers|loves|enjoys|hates|fears|avoids)\s+",
                "",
                p_phrase,
                flags=re.IGNORECASE,
            ).strip().lower()
            if not p_core:
                continue
            if (
                p_core in gift_clean
                or gift_clean in p_core
                or (gift_base and len(gift_base) >= 3 and (gift_base in p_core or p_core in gift_base))
            ):
                matched_records.append(
                    {
                        "fact_category": fact_cat,
                        "fact_key": f"{fact_cat}:{p_phrase.lower()}",
                        "fact_value": p_phrase,
                    }
                )

    if matched_records:
        targets = list(earshot_character_ids) if earshot_character_ids else [int(character_id or 0)]
        db.record_contact_dossier_discoveries(
            session_id,
            npc_name,
            matched_records,
            character_ids=targets,
            discovered_turn=turn_number,
            primary_character_id=int(character_id or 0),
            discovery_source="gift",
        )
    return matched_records


def is_contact_exempt_from_fog_of_war(
    contact_obj: dict[str, Any],
    *,
    session_id: int | None = None,
    party_npc_keys: set[str] | None = None,
    kin_npc_keys: set[str] | None = None,
    romantic_npc_keys: set[str] | None = None,
) -> tuple[bool, bool]:
    """Returns (exempt_basic_dossier, exempt_intimate_dossier)."""
    c = contact_obj or {}
    nid = db.canon_social_npc_id(c.get("npc_id") or c.get("name") or "")
    basic = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
    rel_role = str(basic.get("relationship_to_player") or "").strip().lower()
    score = int(c.get("relationship_score") or 0)
    track = str(c.get("track") or "").strip().lower()

    is_kin = bool(
        (kin_npc_keys and nid in kin_npc_keys)
        or basic.get("is_player_kin")
        or basic.get("is_household_member")
        or any(k in rel_role for k in ("sister", "brother", "mother", "father", "sibling", "parent", "cousin", "spouse", "wife", "husband"))
    )
    is_comp = bool((party_npc_keys and nid in party_npc_keys) or basic.get("is_starting_companion") or c.get("is_party_member"))
    is_rom = bool(
        (romantic_npc_keys and nid in romantic_npc_keys)
        or (track == "romantic" and score >= 180)
        or any(k in rel_role for k in ("girlfriend", "boyfriend", "lover", "fiance", "fiancee", "wife", "husband", "spouse"))
    )

    if session_id and nid and not (is_kin or is_comp or is_rom):
        try:
            ex_sets = db.get_player_fow_exemption_sets(int(session_id))
            is_comp = is_comp or (nid in ex_sets.get("party_npc_keys", set()))
            is_kin = is_kin or (nid in ex_sets.get("kin_npc_keys", set()))
            is_rom = is_rom or (nid in ex_sets.get("romantic_npc_keys", set()))
        except Exception:
            pass

    has_intimate_encounter = bool(c.get("gameplay_intimate_events")) or bool((c.get("appearance") or {}).get("had_first_time_with_player"))
    return (is_kin or is_comp or is_rom), (is_rom or has_intimate_encounter)


def apply_fog_of_war_to_enriched_contact(
    enriched_contact: dict[str, Any],
    *,
    session_id: int | None = None,
    character_id: int = 0,
    preloaded_discoveries: list[dict[str, Any]] | None = None,
    lang: str = "en",
    party_npc_keys: set[str] | None = None,
    kin_npc_keys: set[str] | None = None,
    romantic_npc_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Masks unrevealed Traits, Likes, Dislikes, Schedule, and Intimate fields with '???' unless discovered or exempt."""
    c = dict(enriched_contact or {})
    if c.get("debug_revealed"):
        return c

    sid = int(session_id or c.get("session_id") or 0)
    cid = int(character_id or c.get("character_id") or 0)
    nid = db.canon_social_npc_id(c.get("npc_id") or c.get("name") or "")

    exempt_basic, exempt_intimate = is_contact_exempt_from_fog_of_war(
        c,
        session_id=sid if (party_npc_keys is None and kin_npc_keys is None and romantic_npc_keys is None) else None,
        party_npc_keys=party_npc_keys,
        kin_npc_keys=kin_npc_keys,
        romantic_npc_keys=romantic_npc_keys,
    )

    disc_rows = (
        preloaded_discoveries
        if preloaded_discoveries is not None
        else (db.get_contact_dossier_discoveries(sid, cid, nid) if (sid and nid) else [])
    )

    wildcards = {
        d["fact_category"]
        for d in disc_rows
        if str(d.get("fact_key") or "").endswith(":*") or str(d.get("fact_value") or "") == "*"
    }
    known_traits = {str(d["fact_value"]).strip().lower() for d in disc_rows if d.get("fact_category") == "trait"}
    known_likes = {str(d["fact_value"]).strip().lower() for d in disc_rows if d.get("fact_category") == "like"}
    known_dislikes = {str(d["fact_value"]).strip().lower() for d in disc_rows if d.get("fact_category") == "dislike"}
    sched_known = exempt_basic or ("schedule" in wildcards) or any(d.get("fact_category") == "schedule" for d in disc_rows)
    intimate_known = exempt_intimate or ("intimate" in wildcards) or any(d.get("fact_category") == "intimate" for d in disc_rows)

    slot_mask = locales.get_masked_placeholder("slot", lang=lang)
    sched_mask = locales.get_masked_placeholder("schedule", lang=lang)

    def _mask_list(items: list[Any], known_set: set[str], cat_wildcard: str) -> list[str]:
        if exempt_basic or (cat_wildcard in wildcards):
            return [str(x) for x in items if str(x).strip()]
        masked_out: list[str] = []
        for raw_item in items:
            s_val = str(raw_item or "").strip()
            if not s_val:
                continue
            s_low = s_val.lower()
            s_core = re.sub(r"^(likes|dislikes|prefers|loves|enjoys|hates|fears|avoids)\s+", "", s_low).strip()
            if s_low in known_set or any(s_core and (s_core == k or s_core in k or k in s_low) for k in known_set):
                masked_out.append(s_val)
            else:
                masked_out.append(slot_mask)
        return masked_out or [slot_mask]

    c["unlocked_traits"] = _mask_list(list(c.get("unlocked_traits") or c.get("traits") or []), known_traits, "trait")
    c["traits"] = list(c["unlocked_traits"])
    c["preferences"] = _mask_list(list(c.get("preferences") or []), known_likes, "like")
    c["dislikes"] = _mask_list(list(c.get("dislikes") or []), known_dislikes, "dislike")
    c["schedule_revealed"] = bool(sched_known)
    if not sched_known:
        c["known_schedule"] = sched_mask
        if "schedule_summary" in c:
            c["schedule_summary"] = sched_mask
        if isinstance(c.get("basic_info"), dict) and (
            "known_schedule" in c["basic_info"] or "schedule_summary" in c["basic_info"]
        ):
            c["basic_info"] = dict(c["basic_info"])
            if "known_schedule" in c["basic_info"]:
                c["basic_info"]["known_schedule"] = sched_mask
            if "schedule_summary" in c["basic_info"]:
                c["basic_info"]["schedule_summary"] = sched_mask

    for _raw_json_k in (
        "unlocked_traits_json",
        "preferences_json",
        "appearance_json",
        "intimate_profile_json",
        "intimate_memories_json",
        "rel_history_json",
    ):
        c.pop(_raw_json_k, None)

    c["intimate_dossier_revealed"] = bool(intimate_known)
    if not intimate_known:
        c["past_intimate_history"] = ""
        c["past_intimate_entries"] = []
        c["intimate_memories"] = []
        c["intimate_profile"] = {}
        masked_intimate_line = f"• {locales.get_masked_placeholder('intimate', lang=lang)}"
        if isinstance(c.get("intimate_sections"), dict):
            c["intimate_sections"] = {
                k: [masked_intimate_line]
                for k in c["intimate_sections"]
            }
        if isinstance(c.get("appearance"), dict):
            scrubbed_app = dict(c["appearance"])
            for _secret_k in (
                "intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                "intimate_demeanor", "intimate_dynamic", "erotic_openness", "openness",
                "bra", "underwear", "undergarments", "asset_texture",
                "sensitive_spots", "erogenous_zones", "turn_ons", "turn_offs",
                "fetishes", "kinks", "desires_and_kinks",
                "act_likes", "act_dislikes", "favorite_acts", "disliked_acts",
                "penis_size", "intimate_memories",
                "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
                "anal_revealed", "demeanor_revealed", "dynamic_revealed", "openness_revealed",
                "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed",
                "fetishes_revealed", "act_preferences_revealed", "underwear_revealed", "all_revealed",
            ):
                scrubbed_app.pop(_secret_k, None)
            c["appearance"] = scrubbed_app
        if isinstance(c.get("revealed_flags"), dict):
            scrubbed_flags = dict(c["revealed_flags"])
            for _rf_k in list(scrubbed_flags.keys()):
                if _rf_k != "mannerisms_revealed":
                    scrubbed_flags.pop(_rf_k, None)
            c["revealed_flags"] = scrubbed_flags

    return c


def apply_v50_social_turn_for_npc(
    session_id: int,
    character_id: int,
    npc_name: str,
    *,
    raw_delta: int,
    action: dict[str, Any] | None,
    session: dict[str, Any] | None,
    outcome: dict[str, Any],
    party: list[Any] | None = None,
    all_scene_npcs: list[Any] | None = None,
    target_scene_npc: dict[str, Any] | None = None,
    already_cushioned: bool = False,
    is_gift: bool = False,
    gift_item_name: str = "",
    is_confession: bool = False,
    is_intimate_turn: bool = False,
    turn_number: int = 1,
    contact_eligible: bool = True,
) -> dict[str, Any]:
    """Orchestrates v50 3-clock pacing, consequences, dossier reveals, pills, and composure exit for one NPC."""
    if not session_id or not npc_name:
        return {"delta": int(raw_delta or 0), "pills": [], "mood_payload": None}

    sess = session if isinstance(session, dict) else {}
    if is_intimate_turn or bool(sess.get("_in_active_erotic_dlg")):
        return {"delta": int(raw_delta or 0), "pills": [], "mood_payload": None}

    lang = locales.normalize_social_lang(str(sess.get("language") or "en"))
    scen = str(sess.get("scenario") or "fantasy")
    cur_day = int(sess.get("current_day") or 1)
    cur_min = int(sess.get("current_minute") or 480)
    cur_loc = str(outcome.get("location") or sess.get("current_location") or "")
    venue_leaf = cur_loc.split("➔")[-1].strip() if "➔" in cur_loc else cur_loc.strip()

    from mechanics.narrative.intent import is_dialogue_exit_action

    if action and is_dialogue_exit_action(action):
        return {"delta": int(raw_delta or 0), "pills": [], "mood_payload": None}

    act_stat = str((action or {}).get("stat") or "NONE").upper()
    act_req = int((action or {}).get("requirement") or 0)
    act_intent = str((action or {}).get("intent") or "").lower().strip()
    is_free_init = bool(
        not action
        or act_intent == "dialogue_init"
        or (act_stat in ("NONE", "FREE") and act_req <= 0 and not is_gift)
    )

    if is_free_init:
        comp_sync = pacing.sync_and_get_composure(
            session_id,
            npc_name,
            current_day=cur_day,
            current_minute=cur_min,
            scenario=scen,
            turn_updated=turn_number,
        )
        m_str = str(comp_sync.get("mood") or "Engaged")
        cta = bool(int(comp_sync.get("clear_the_air_required") or 0) == 1)
        init_pills: list[dict[str, Any]] = []
        if cta:
            init_pills.append(
                locales.build_turn_feedback_pill_payload("clear_the_air", detail=npc_name, lang=lang, tone="warning")
            )
        return {
            "delta": int(raw_delta or 0),
            "pills": init_pills,
            "mood_payload": {
                "npc_name": npc_name,
                "mood": m_str,
                "mood_label": locales.get_mood_label(m_str, lang=lang),
                "composure_state": str(comp_sync.get("composure_state") or "composed"),
                "clear_the_air": cta,
            },
        }

    from mechanics.social.conversation_choices import (
        _infer_social_category_from_choice,
        resolve_partner_conversation_profile,
    )

    cat = str((action or {}).get("category") or "").strip().lower()
    if not cat:
        cat = _infer_social_category_from_choice(action or {})
    topic_id = str((action or {}).get("topic_id") or "").strip()

    tier = str((action or {}).get("tier") or "").strip().lower()
    if not tier:
        chk = (action or {}).get("check")
        if hasattr(chk, "tier") and chk.tier is not None:
            tier = str(chk.tier).lower()
        elif isinstance(chk, dict):
            tier = str(chk.get("tier") or "success").lower()
        else:
            tier = "success" if bool((action or {}).get("success", True)) else "fail"

    earshot_cids: list[int] = []
    party_names_low: set[str] = set()
    for entry in (party or []):
        p_c = entry[0] if isinstance(entry, (tuple, list)) else entry
        if isinstance(p_c, dict):
            if p_c.get("id") is not None:
                earshot_cids.append(int(p_c["id"]))
            if p_c.get("name"):
                party_names_low.add(str(p_c["name"]).strip().lower())
    if int(character_id or 0) not in earshot_cids:
        earshot_cids.insert(0, int(character_id or 0))

    present_bystanders: list[str] = []
    n_low = npc_name.strip().lower()
    for sn in (all_scene_npcs or []):
        sn_nm = str(sn.get("name") if isinstance(sn, dict) else sn).strip()
        if sn_nm and sn_nm.lower() != n_low and sn_nm.lower() not in party_names_low:
            present_bystanders.append(sn_nm)

    pills: list[dict[str, Any]] = []
    final_delta = int(raw_delta or 0)
    magic_backfire = False

    if contact_eligible:
        conseq = evaluate_social_turn_consequences(
            session_id=session_id,
            character_id=int(character_id or 0),
            npc_name=npc_name,
            stat=act_stat if act_stat not in ("NONE", "FREE", "ITEM") else "CHA",
            category=cat,
            topic_id=topic_id,
            outcome_tier=tier,
            base_affinity_delta=final_delta,
            is_cruel=bool((action or {}).get("is_cruel")),
            is_covert_ability=bool((action or {}).get("is_covert_ability")),
            present_bystanders=present_bystanders,
            earshot_character_ids=earshot_cids,
            scenario=scen,
            turn_number=turn_number,
            already_cushioned=already_cushioned,
        )
        magic_backfire = bool(conseq.get("magic_backfire"))
        adj_delta = int(conseq.get("adjusted_affinity_delta") or 0)

        is_on_date = False
        try:
            prof = resolve_partner_conversation_profile(sess, npc_name, party=party, current_npcs=all_scene_npcs)
            is_on_date = bool(prof.get("is_private_meetup"))
        except Exception:
            is_on_date = False

        dig = pacing.apply_shared_daily_digestion(
            session_id,
            int(character_id or 0),
            npc_name,
            raw_delta=adj_delta,
            current_day=cur_day,
            is_on_date=is_on_date,
            is_gift=is_gift,
            is_confession=is_confession,
            turn_updated=turn_number,
        )
        final_delta = int(dig["applied_delta"])

        cat_to_pill = {
            "trait": "trait_unlocked",
            "like": "like_unlocked",
            "dislike": "dislike_unlocked",
            "schedule": "schedule_unlocked",
            "intimate": "intimate_unlocked",
        }
        for d_item in (conseq.get("discoveries") or []):
            pkey = cat_to_pill.get(str(d_item.get("fact_category") or ""), "trait_unlocked")
            pills.append(
                locales.build_turn_feedback_pill_payload(
                    pkey, detail=str(d_item.get("fact_value") or ""), lang=lang, tone="positive"
                )
            )

        if is_gift and gift_item_name:
            gift_unmasked = unmask_preferences_on_gift(
                session_id=session_id,
                character_id=int(character_id or 0),
                npc_name=npc_name,
                item_name=gift_item_name,
                turn_number=turn_number,
                earshot_character_ids=earshot_cids,
                scenario=scen,
            )
            for gu in gift_unmasked:
                g_pkey = "dislike_unlocked" if gu.get("fact_category") == "dislike" else "like_unlocked"
                pills.append(
                    locales.build_turn_feedback_pill_payload(
                        g_pkey, detail=str(gu.get("fact_value") or ""), lang=lang, tone="positive"
                    )
                )

        if conseq.get("rival_sparked"):
            pills.append(
                locales.build_turn_feedback_pill_payload("rival_sparked", detail=npc_name, lang=lang, tone="warning")
            )
        if dig.get("capped"):
            pills.append(
                locales.build_turn_feedback_pill_payload("bond_settling", detail=npc_name, lang=lang, tone="neutral")
            )

        for b_name, b_del in (conseq.get("bystander_deltas") or {}).items():
            if int(b_del or 0) != 0:
                db.upsert_contact(
                    session_id=session_id,
                    character_id=int(character_id or 0),
                    npc_id=b_name,
                    name=b_name,
                    delta_score=int(b_del),
                )

        if not is_gift:
            eff_tid = topic_id or f"{cat}:dialogue_turn"
            pacing.record_topic_resolution(
                session_id,
                int(character_id or 0),
                npc_name,
                topic_id=eff_tid,
                category=cat,
                outcome_tier=tier,
                current_day=cur_day,
                current_minute=cur_min,
                venue_leaf=venue_leaf,
                turn_updated=turn_number,
            )
            if tier in ("fail", "failure", "crit_fail", "critical_failure"):
                pills.append(
                    locales.build_turn_feedback_pill_payload("topic_locked", detail=npc_name, lang=lang, tone="warning")
                )

    is_party_member = any(
        isinstance(pm, dict) and str(pm.get("name") or "").strip().lower() == n_low
        for pm in (db.get_session_party_npcs(session_id) or [])
    )
    is_quest_stationed_here = bool(
        (target_scene_npc or {}).get("quest_protected")
        or (target_scene_npc or {}).get("is_quest_giver")
        or any(n_low in str(q).lower() for q in (db.get_quests(session_id, status="active") or []))
    )

    c_drain = 0 if (is_gift and final_delta >= 0) else pacing.compute_turn_composure_delta(
        outcome_tier=tier,
        category=cat,
        stat=act_stat if act_stat not in ("NONE", "FREE", "ITEM") else "CHA",
        is_bold_or_prying=(cat in ("flirt_chemistry", "friction_rivalry") or act_req >= 9),
        is_magic_backfire=magic_backfire,
    )
    comp_after = pacing.apply_composure_delta(
        session_id,
        npc_name,
        delta=c_drain,
        current_day=cur_day,
        current_minute=cur_min,
        scenario=scen,
        outcome_tier=tier,
        is_quest_stationed_here=is_quest_stationed_here,
        is_party_member=is_party_member,
        turn_updated=turn_number,
    )

    c_st = str(comp_after.get("composure_state") or "composed")
    if int(comp_after.get("current_composure", 100)) <= 0:
        if c_st == "cold_shoulder":
            pills.append(
                locales.build_turn_feedback_pill_payload("cold_shoulder", detail=npc_name, lang=lang, tone="warning")
            )
        elif c_st == "focus_on_road":
            pills.append(
                locales.build_turn_feedback_pill_payload("focus_on_road", detail=npc_name, lang=lang, tone="warning")
            )
        elif c_st == "walked_away":
            cur_dps = list(outcome.get("dialogue_partners") or sess.get("dialogue_partners") or [])
            rem_dps = [p for p in cur_dps if str(p).strip().lower() != n_low]
            outcome["dialogue_partners"] = rem_dps
            outcome["dialogue_partner"] = rem_dps[0] if rem_dps else None
            if isinstance(session, dict):
                session["dialogue_partners"] = rem_dps
                session["dialogue_partner"] = rem_dps[0] if rem_dps else None
            if not rem_dps:
                outcome["has_exited_convo"] = True
            if isinstance(outcome.get("npcs_present"), list):
                outcome["npcs_present"] = [
                    ent for ent in outcome["npcs_present"]
                    if str(ent.get("name") if isinstance(ent, dict) else ent).strip().lower() != n_low
                ]

    mood_str = str(comp_after.get("mood") or "Engaged")
    mood_payload = {
        "npc_name": npc_name,
        "mood": mood_str,
        "mood_label": locales.get_mood_label(mood_str, lang=lang),
        "composure_state": c_st,
        "clear_the_air": bool(int(comp_after.get("clear_the_air_required") or 0) == 1),
    }
    return {
        "delta": final_delta,
        "pills": pills,
        "mood_payload": mood_payload,
    }


def finalize_v50_social_turn(
    session_id: int,
    character_id: int,
    *,
    outcome: dict[str, Any],
    session: dict[str, Any] | None,
    actions: list[Any] | None,
    party: list[Any] | None,
    all_scene_npcs: list[Any] | None,
    handled_npc_ids: set[str],
    accumulated_pills: list[dict[str, Any]],
    latest_mood: dict[str, Any] | None,
    is_intimate_turn: bool,
    turn_number: int,
) -> None:
    """Drains Composure for non-contact partners (Merchants/Faculty), attaches UI mood/pills, and snapshots turn."""
    if not session_id:
        return
    sess = session if isinstance(session, dict) else {}
    primary_act = actions[0] if (actions and isinstance(actions[0], dict)) else None
    active_dps = list(outcome.get("dialogue_partners") or sess.get("dialogue_partners") or [])
    if not is_intimate_turn and active_dps:
        lead_dp = str((primary_act or {}).get("target_npc") or active_dps[0] or "").strip()
        if lead_dp and db.canon_social_npc_id(lead_dp) not in handled_npc_ids:
            extra = apply_v50_social_turn_for_npc(
                session_id=session_id,
                character_id=character_id,
                npc_name=lead_dp,
                raw_delta=0,
                action=primary_act,
                session=session,
                outcome=outcome,
                party=party,
                all_scene_npcs=all_scene_npcs,
                is_intimate_turn=is_intimate_turn,
                turn_number=turn_number,
                contact_eligible=False,
            )
            accumulated_pills.extend(extra.get("pills") or [])
            if extra.get("mood_payload"):
                latest_mood = extra["mood_payload"]

    dedup_pills: list[dict[str, Any]] = []
    seen_p: set[tuple[str, str]] = set()
    for p in accumulated_pills:
        if not isinstance(p, dict):
            continue
        pk = (str(p.get("key") or ""), str(p.get("detail") or ""))
        if pk not in seen_p:
            seen_p.add(pk)
            dedup_pills.append(p)

    outcome["social_feedback_pills"] = dedup_pills
    if latest_mood and (outcome.get("dialogue_partners") or sess.get("dialogue_partners")):
        outcome["active_dialogue_mood"] = latest_mood
    else:
        outcome["active_dialogue_mood"] = None

    if isinstance(session, dict):
        session["social_feedback_pills"] = dedup_pills
        session["active_dialogue_mood"] = outcome["active_dialogue_mood"]

    db.snapshot_session_social_state_for_turn(session_id, turn_number)
