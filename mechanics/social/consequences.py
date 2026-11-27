from __future__ import annotations

"""Deterministic Social Turn Consequences, Bystander Ripples & Fog-of-War Dossier Unmasking.

Handles:
1. 4-tier check outcome adjustments (`CHA` -1 non-crit fail cushion, covert magic detection backfire).
2. Non-cruel `friction_rivalry` respect payoffs with Proud/Rebellious/Delinquent NPCs + `rival` tie formation.
3. Connected bystander reactions (romantic partner jealousy on bold flirts; kin/best-friend defensiveness on cruel insults).
4. Fog-of-War `"???"` Dossier fact selection, Gift preference auto-unmasking, and co-op earshot fan-out.
"""

import re
from typing import Any

import db
from mechanics.social import locales, pacing
from mechanics.social.relationships import safe_get_contacts
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


def evaluate_bystander_openness_flavor(
    present_bystanders: list[str] | None,
    target_npc_name: str = "",
    *,
    category: str = "",
    is_provocative: bool = False,
    session_id: int = 0,
    contacts: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Returns Openness-colored qualitative reaction cues for partner jealousy and bystander PDA/attire."""
    if not present_bystanders:
        return []
    from mechanics.social.persona import normalize_openness_tier

    c_list = list(contacts or [])
    if not c_list and session_id:
        try:
            c_list = db.get_contacts(int(session_id)) or []
        except Exception:
            c_list = []
    by_name_map: dict[str, dict[str, Any]] = {}
    for row in c_list:
        if isinstance(row, dict) and row.get("name"):
            by_name_map[str(row["name"]).strip().lower()] = row

    player_rom_partners: set[str] = set()
    if session_id:
        try:
            for t in (rg.get_ties(int(session_id), "player") or []):
                if str(t.get("status") or "active") != "active":
                    continue
                other = t.get("person_b_key") if t.get("person_a_key") == "player" else t.get("person_a_key")
                if other and str(t.get("tie_type") or "") in rg.ROMANTIC_TYPES:
                    player_rom_partners.add(str(other))
        except Exception:
            pass

    target_low = str(target_npc_name or "").strip().lower()
    cues: list[dict[str, str]] = []
    for raw_b in present_bystanders:
        b_name = str(raw_b or "").strip()
        if not b_name or b_name.lower() == target_low:
            continue
        b_row = by_name_map.get(b_name.lower()) or {}
        b_app = b_row.get("appearance") if isinstance(b_row.get("appearance"), dict) else {}
        op_tier = normalize_openness_tier(b_app.get("erotic_openness") or b_app.get("openness") or "moderate")
        b_canon = rg.canonical_person_key(b_name)
        is_rom_partner = b_canon in player_rom_partners or str(b_row.get("relationship_track") or b_row.get("track") or "").lower() == "romantic"

        if category == "flirt_chemistry" and is_rom_partner:
            if op_tier == "prude":
                tone = "hurt, indignant dignity at your brazen public flirting"
            elif op_tier in ("bold", "shameless"):
                tone = "a sharp, territorial stare with a pointed teasing challenge"
            else:
                tone = "stung, coolly guarded withdrawal"
            cues.append({"npc_name": b_name, "openness_tier": op_tier, "kind": "partner_jealousy", "cue": tone})
        elif category == "flirt_chemistry" or is_provocative:
            if op_tier == "prude":
                tone = "averts eyes with stiff, scandalized disapproval"
            elif op_tier in ("bold", "shameless"):
                tone = "watches with an unbothered smirk and cheeky amusement"
            else:
                tone = "casts a surprised, slightly flustered side-glance"
            cues.append({"npc_name": b_name, "openness_tier": op_tier, "kind": "bystander_pda", "cue": tone})
    return cues


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
            for c_row in safe_get_contacts(session_id, character_id=int(character_id or 0), ensure_scene=False):
                if db.canon_social_npc_id(c_row.get("npc_id") or c_row.get("name") or "") == canon_target:
                    contact_obj = c_row
                    break
            if contact_obj is None:
                contact_obj = db.get_world_roster_npc(session_id, npc_name, include_legacy_rosters=True)
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


INTIMATE_DISCOVERY_CATEGORIES: tuple[str, ...] = (
    "sensitive_spot",
    "desire",
    "kink",
    "turn_off",
    "act_pref",
    "undergarment",
    "openness",
)

_INTIMATE_CATEGORY_PILL_KEY: dict[str, str] = {
    "sensitive_spot": "sensitive_spot_unlocked",
    "desire": "desire_unlocked",
    "kink": "kink_unlocked",
    "turn_off": "turn_off_unlocked",
    "act_pref": "act_pref_unlocked",
    "undergarment": "undergarment_unlocked",
    "openness": "openness_unlocked",
}


def build_intimate_discovery_pills(
    new_discoveries: list[dict[str, Any]] | None,
    lang: str = "en",
) -> list[str]:
    """Builds concise player-facing pills from newly recorded intimate dossier discoveries.

    1-2 discoveries emit individual category pills; 3+ bundle into one summary pill.
    """
    rows = [
        d for d in (new_discoveries or [])
        if isinstance(d, dict) and str(d.get("fact_category") or "").strip().lower() in _INTIMATE_CATEGORY_PILL_KEY
    ]
    if not rows:
        return []

    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for r in rows:
        cat = str(r.get("fact_category") or "").strip().lower()
        val = str(r.get("fact_value") or r.get("fact_key") or "").strip()
        if not val or val == "*":
            continue
        sig = (cat, val.lower())
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append({"category": cat, "value": val})

    if not deduped:
        return []

    eff_lang = locales.normalize_social_lang(lang)
    if len(deduped) <= 2:
        pills: list[str] = []
        for item in deduped:
            pk = _INTIMATE_CATEGORY_PILL_KEY[item["category"]]
            pills.append(locales.format_feedback_pill(pk, item["value"], lang=eff_lang))
        return pills

    preview = ", ".join(item["value"] for item in deduped[:2])
    detail = f"{preview} (+{len(deduped) - 2})" if len(deduped) > 2 else preview
    return [locales.format_feedback_pill("intimate_insights_bundle", detail, lang=eff_lang)]


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
    is_nsfw: bool | None = None,
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
    discovered_body_prefs = {
        str(d.get("fact_value") or "").strip().lower()
        for d in disc_rows
        if d.get("fact_category") == "body_pref" and str(d.get("fact_value") or "").strip()
    }
    discovered_intimate: dict[str, set[str]] = {cat: set() for cat in INTIMATE_DISCOVERY_CATEGORIES}
    for _dr in disc_rows:
        if not isinstance(_dr, dict):
            continue
        _fcat = str(_dr.get("fact_category") or "").strip().lower()
        _fval = str(_dr.get("fact_value") or _dr.get("fact_key") or "").strip()
        if _fcat in discovered_intimate and _fval:
            discovered_intimate[_fcat].add(_fval)
    any_intimate_disc = any(bool(v) for v in discovered_intimate.values())
    sched_known = exempt_basic or ("schedule" in wildcards) or any(d.get("fact_category") == "schedule" for d in disc_rows)
    intimate_known = exempt_intimate or ("intimate" in wildcards) or any(d.get("fact_category") == "intimate" for d in disc_rows)
    if is_nsfw is not None:
        _is_nsfw_fow = bool(is_nsfw)
    elif "is_nsfw" in c and c.get("is_nsfw") is not None:
        _is_nsfw_fow = bool(c.get("is_nsfw"))
    elif c.get("scenario"):
        from scenario_data import is_nsfw_scenario as _is_nsfw_scen_fow
        _is_nsfw_fow = bool(_is_nsfw_scen_fow(str(c.get("scenario"))))
    elif sid:
        _sess_fow = db.get_session(sid)
        if isinstance(_sess_fow, dict) and _sess_fow:
            from scenario_data import is_nsfw_scenario as _is_nsfw_scen_fow
            _is_nsfw_fow = bool(
                _is_nsfw_scen_fow(str(_sess_fow.get("scenario") or ""))
                or ("nsfw" in str(_sess_fow.get("tags") or "").lower())
            )
        else:
            _is_nsfw_fow = False
    else:
        _is_nsfw_fow = False
    c["is_nsfw"] = bool(_is_nsfw_fow)
    openness_unlocked = bool(
        _is_nsfw_fow
        and (
            intimate_known
            or ("openness" in wildcards)
            or bool(discovered_intimate.get("openness"))
            or int(c.get("info_level") or 0) >= 2
        )
    )
    from mechanics.social.persona.intimacy.constants import HEIGHT_PREFERENCE_KEYS
    height_pref_unlocked = bool(intimate_known or exempt_basic or int(c.get("info_level") or 0) >= 2)

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

    c["intimate_dossier_revealed"] = bool(intimate_known) if _is_nsfw_fow else False
    _chem_already_scoped = bool(c.pop("_enriched_chemistry_scoped", False))
    if not _is_nsfw_fow:
        c["past_intimate_history"] = ""
        c["past_intimate_entries"] = []
        c["intimate_memories"] = []
        c["intimate_profile"] = {}
        c["intimate_sections"] = {}
        c["intimate_structured"] = {}
        c["intimate_chemistry"] = {}
        c["shared_intimacy_stats"] = {}
        if isinstance(c.get("appearance"), dict):
            scrubbed_sfw_app = dict(c["appearance"])
            for _sfw_app_k in (
                "anatomy", "experience", "undergarments", "bra", "underwear",
                "breast_size", "penis_size", "asset_texture", "rear_size", "rear_texture",
                "intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                "virginity_intercourse", "virginity_oral", "virginity_manual", "virginity_anal",
                "intimate_demeanor", "intimate_dynamic", "erotic_openness", "openness",
                "sensitive_spots", "erogenous_zones", "turn_ons", "turn_offs",
                "fetishes", "kinks", "desires_and_kinks",
                "act_likes", "act_dislikes", "favorite_acts", "disliked_acts",
                "intimate_memories", "past_intimate_history", "past_intimate_entries",
                "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
                "anal_revealed", "demeanor_revealed", "dynamic_revealed", "openness_revealed",
                "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed",
                "fetishes_revealed", "act_preferences_revealed", "underwear_revealed", "all_revealed",
            ):
                scrubbed_sfw_app.pop(_sfw_app_k, None)
            if discovered_body_prefs or height_pref_unlocked:
                if isinstance(scrubbed_sfw_app.get("body_likes"), list):
                    scrubbed_sfw_app["body_likes"] = [
                        k for k in scrubbed_sfw_app["body_likes"]
                        if str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS
                        and (height_pref_unlocked or str(k).strip().lower() in discovered_body_prefs)
                    ]
                if isinstance(scrubbed_sfw_app.get("body_dislikes"), list):
                    scrubbed_sfw_app["body_dislikes"] = [
                        k for k in scrubbed_sfw_app["body_dislikes"]
                        if str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS
                        and (height_pref_unlocked or str(k).strip().lower() in discovered_body_prefs)
                    ]
                if not discovered_body_prefs:
                    scrubbed_sfw_app.pop("body_preferences_revealed", None)
            else:
                scrubbed_sfw_app.pop("body_likes", None)
                scrubbed_sfw_app.pop("body_dislikes", None)
                scrubbed_sfw_app.pop("body_preferences_revealed", None)
            c["appearance"] = scrubbed_sfw_app
    elif not intimate_known:
        c["past_intimate_history"] = ""
        c["past_intimate_entries"] = []
        c["intimate_memories"] = []
        c["intimate_profile"] = {}
        if not int((c.get("shared_intimacy_stats") or {}).get("shared_encounters") or 0):
            c["shared_intimacy_stats"] = {}

        if not _chem_already_scoped:
            try:
                from mechanics.social.persona import build_intimate_chemistry_summary
                c["intimate_chemistry"] = build_intimate_chemistry_summary(
                    c,
                    intimate_unlocked=False,
                    revealed_flags=c.get("revealed_flags") if isinstance(c.get("revealed_flags"), dict) else None,
                    discovered_intimate=discovered_intimate,
                    discovered_body_prefs=discovered_body_prefs,
                    is_nsfw=_is_nsfw_fow,
                    openness_unlocked=openness_unlocked,
                )
            except Exception:
                c["intimate_chemistry"] = {}

        if _is_nsfw_fow and isinstance(c.get("intimate_structured"), dict) and c["intimate_structured"]:
            from mechanics.social.persona import strip_internal_item_tags

            def _disc_norm(cat_k: str) -> set[str]:
                return {
                    strip_internal_item_tags(str(x)).lower()
                    for x in (discovered_intimate.get(cat_k) or set())
                    if str(x).strip()
                }

            _ds_spots = _disc_norm("sensitive_spot")
            _ds_des = _disc_norm("desire")
            _ds_kink = _disc_norm("kink")
            _ds_to = _disc_norm("turn_off")
            _ds_act = _disc_norm("act_pref")
            _ds_und = _disc_norm("undergarment")
            _rf_fow = c.get("revealed_flags") if isinstance(c.get("revealed_flags"), dict) else {}

            def _mask_struct_items(items_raw: Any, known_s: set[str], full_flag: str, keep_curious: bool = False) -> list[dict[str, Any]]:
                if not isinstance(items_raw, list):
                    return []
                is_full = bool(_rf_fow.get(full_flag))
                out_list: list[dict[str, Any]] = []
                for it in items_raw:
                    if not isinstance(it, dict):
                        continue
                    lbl = strip_internal_item_tags(str(it.get("label") or "")).strip()
                    was_masked = bool(it.get("masked")) or lbl in ("", "???")
                    if not was_masked and (is_full or lbl.lower() in known_s):
                        entry = {"label": lbl, "masked": False}
                        if keep_curious:
                            entry["curious"] = bool(it.get("curious"))
                        out_list.append(entry)
                    else:
                        entry = {"label": "???", "masked": True}
                        if keep_curious:
                            entry["curious"] = False
                        out_list.append(entry)
                return out_list

            st_in = dict(c["intimate_structured"])
            _in_open = st_in.get("openness") if isinstance(st_in.get("openness"), dict) else {}
            _in_comfort = st_in.get("with_you_comfort") if isinstance(st_in.get("with_you_comfort"), dict) else None
            _in_contrast = st_in.get("openness_contrast") if isinstance(st_in.get("openness_contrast"), dict) else None
            _dem_dyn_both = bool(_rf_fow.get("demeanor_revealed") and _rf_fow.get("dynamic_revealed"))
            _raw_app_pre = c.get("appearance") if isinstance(c.get("appearance"), dict) else {}
            _raw_open_pre = _raw_app_pre.get("erotic_openness") or _raw_app_pre.get("openness")
            if _raw_open_pre in (None, ""):
                for _dr_op in reversed(disc_rows):
                    if isinstance(_dr_op, dict) and str(_dr_op.get("fact_category") or "").strip().lower() == "openness":
                        _fk_op = str(_dr_op.get("fact_key") or "").strip()
                        _raw_open_pre = (
                            _fk_op.split(":", 1)[1].strip()
                            if ":" in _fk_op
                            else str(_dr_op.get("fact_value") or "").strip()
                        )
                        if _raw_open_pre:
                            break
            _st_open_out: dict[str, Any] = {"tier": "", "label": "???", "masked": True}
            if openness_unlocked:
                if _in_open and not _in_open.get("masked"):
                    _st_open_out = dict(_in_open, masked=False)
                elif _raw_open_pre not in (None, ""):
                    from mechanics.social.persona import get_erotic_openness_label, normalize_openness_tier
                    _op_t_fow = normalize_openness_tier(_raw_open_pre)
                    _st_open_out = {
                        "tier": _op_t_fow,
                        "label": get_erotic_openness_label(_raw_open_pre),
                        "masked": False,
                    }
            _eff_comfort_out = None
            if openness_unlocked and not _st_open_out.get("masked"):
                if isinstance(_in_comfort, dict):
                    _eff_comfort_out = dict(_in_comfort)
                elif _raw_open_pre not in (None, "") or _st_open_out.get("tier"):
                    from mechanics.social.persona import compute_with_you_comfort
                    _sh_fow = len(c.get("gameplay_intimate_events") or []) or int(
                        (c.get("shared_intimacy_stats") or {}).get("shared_encounters") or 0
                    )
                    _c_inf_fow = compute_with_you_comfort(
                        _raw_open_pre or _st_open_out.get("tier") or "moderate",
                        relationship_score=int(c.get("relationship_score", c.get("score", 0)) or 0),
                        relationship_track=str(
                            c.get("relationship_track")
                            or c.get("track")
                            or ("romantic" if int(c.get("relationship_score", c.get("score", 0)) or 0) >= 100 else "platonic")
                        ),
                        shared_intimate_count=_sh_fow,
                        is_hostile=(str(c.get("disposition") or "").strip().lower() == "hostile"),
                    )
                    if _c_inf_fow.get("show_badge"):
                        _eff_comfort_out = {
                            "stage": _c_inf_fow["stage"],
                            "badge_key": _c_inf_fow["badge_key"],
                            "badge_label": _c_inf_fow["badge_label"],
                        }
            _eff_contrast_out = None
            if _dem_dyn_both and not _st_open_out.get("masked"):
                if isinstance(_in_contrast, dict) and _in_contrast:
                    _eff_contrast_out = dict(_in_contrast)
                else:
                    try:
                        from mechanics.social.persona import resolve_openness_contrast
                        _sh_cont_fow = len(c.get("gameplay_intimate_events") or []) or int(
                            (c.get("shared_intimacy_stats") or {}).get("shared_encounters") or 0
                        )
                        _dyn_lines_raw = (c.get("intimate_sections") or {}).get("dynamic") or []
                        _dem_str_fow = str(_raw_app_pre.get("intimate_demeanor") or "")
                        _dyn_str_fow = str(_raw_app_pre.get("intimate_dynamic") or "")
                        for _dl_f in _dyn_lines_raw:
                            _dls = str(_dl_f or "")
                            if "**Demeanor**" in _dls and ":" in _dls and not _dem_str_fow:
                                _dem_str_fow = _dls.split(":", 1)[1].strip()
                            elif "**Dynamic**" in _dls and ":" in _dls and not _dyn_str_fow:
                                _dyn_str_fow = _dls.split(":", 1)[1].strip()
                        _ic_fow = str(_raw_app_pre.get("intercourse_experience") or _raw_app_pre.get("predetermined_intercourse") or "").strip().lower()
                        _c_cont_fow = resolve_openness_contrast(
                            _raw_open_pre or _st_open_out.get("tier") or "moderate",
                            _dem_str_fow,
                            _dyn_str_fow,
                            intercourse_experience=_ic_fow,
                            shared_intimate_count=_sh_cont_fow,
                            comfort_stage=(_eff_comfort_out or {}).get("stage", ""),
                        )
                        if isinstance(_c_cont_fow, dict) and _c_cont_fow.get("archetype"):
                            _eff_contrast_out = _c_cont_fow
                    except Exception:
                        _eff_contrast_out = None
            st_out: dict[str, Any] = {
                "openness": _st_open_out,
                "with_you_comfort": _eff_comfort_out,
                "openness_contrast": _eff_contrast_out,
                "sensitive_spots": _mask_struct_items(st_in.get("sensitive_spots"), _ds_spots, "sensitive_spots_revealed"),
                "desires": _mask_struct_items(st_in.get("desires"), _ds_des, "turn_ons_revealed"),
                "turn_offs": _mask_struct_items(st_in.get("turn_offs"), _ds_to, "turn_offs_revealed"),
                "act_likes": _mask_struct_items(st_in.get("act_likes"), _ds_act, "act_preferences_revealed", keep_curious=True),
                "act_dislikes": _mask_struct_items(st_in.get("act_dislikes"), _ds_act, "act_preferences_revealed"),
                "body_likes": [
                    k for k in (st_in.get("body_likes") or [])
                    if str(k).strip().lower() in discovered_body_prefs
                    or (height_pref_unlocked and str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS)
                ],
                "body_dislikes": [
                    k for k in (st_in.get("body_dislikes") or [])
                    if str(k).strip().lower() in discovered_body_prefs
                    or (height_pref_unlocked and str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS)
                ],
            }
            raw_ak = st_in.get("active_kink")
            if isinstance(raw_ak, dict):
                ak_lbl = strip_internal_item_tags(str(raw_ak.get("label") or "")).strip()
                if not raw_ak.get("masked") and ak_lbl and ak_lbl != "???":
                    _ak_parts = [p.strip() for p in ak_lbl.split(",") if p.strip() and p.strip() != "???"]
                    _ak_has_hid = "???" in ak_lbl
                    if _rf_fow.get("fetishes_revealed"):
                        st_out["active_kink"] = {"label": ", ".join(_ak_parts) or ak_lbl, "masked": False}
                    else:
                        _vis_ak_p = [p for p in _ak_parts if p.lower() in _ds_kink]
                        _any_hid_ak = _ak_has_hid or (len(_vis_ak_p) < len(_ak_parts))
                        if _vis_ak_p:
                            st_out["active_kink"] = {
                                "label": ", ".join(_vis_ak_p + (["???"] if _any_hid_ak else [])),
                                "masked": False,
                            }
                        else:
                            st_out["active_kink"] = {"label": "???", "masked": True}
                else:
                    st_out["active_kink"] = {"label": "???", "masked": True}
            else:
                st_out["active_kink"] = None

            raw_u = st_in.get("undergarments") if isinstance(st_in.get("undergarments"), dict) else {}
            u_bra = str(raw_u.get("bra") or "").strip()
            u_und = str(raw_u.get("underwear") or "").strip()
            bra_ok = bool(_rf_fow.get("underwear_revealed") or (not raw_u.get("bra_masked") and ("bra" in _ds_und or (u_bra and u_bra.lower() in _ds_und))))
            und_ok = bool(_rf_fow.get("underwear_revealed") or (not raw_u.get("underwear_masked") and ("underwear" in _ds_und or (u_und and u_und.lower() in _ds_und))))
            st_out["undergarments"] = {
                "bra": u_bra if (bra_ok and u_bra and u_bra != "???") else ("???" if u_bra else ""),
                "bra_masked": bool(u_bra and not (bra_ok and u_bra != "???")),
                "underwear": u_und if (und_ok and u_und and u_und != "???") else "???",
                "underwear_masked": not bool(und_ok and u_und and u_und != "???"),
            }
            c["intimate_structured"] = st_out

        if not _is_nsfw_fow and isinstance(c.get("intimate_structured"), dict):
            c["intimate_structured"] = {}

        masked_intimate_line = f"• {locales.get_masked_placeholder('intimate', lang=lang)}"
        if _is_nsfw_fow and isinstance(c.get("intimate_sections"), dict) and c["intimate_sections"]:
            masked_sections: dict[str, Any] = {
                k: [masked_intimate_line]
                for k in c["intimate_sections"]
            }
            if discovered_body_prefs or height_pref_unlocked:
                st_bp = c.get("intimate_structured") if isinstance(c.get("intimate_structured"), dict) else None
                preserved_bp: list[str] = []
                if st_bp is not None:
                    _bp_fow_labels = {
                        "smaller_bb": "Smaller Breasts",
                        "bigger_bb": "Bigger Breasts",
                        "smaller_ass": "Smaller Rear",
                        "bigger_ass": "Bigger Rear",
                        "taller_partner": "Taller Partners",
                        "shorter_partner": "Shorter Partners",
                    }
                    _bp_likes_vis = [_bp_fow_labels[k] for k in (st_bp.get("body_likes") or []) if k in _bp_fow_labels]
                    _bp_dislikes_vis = [_bp_fow_labels[k] for k in (st_bp.get("body_dislikes") or []) if k in _bp_fow_labels]
                    _bp_seg: list[str] = []
                    if _bp_likes_vis:
                        _bp_seg.append("Likes " + ", ".join(_bp_likes_vis))
                    if _bp_dislikes_vis:
                        _bp_seg.append("Dislikes " + ", ".join(_bp_dislikes_vis))
                    if _bp_seg:
                        preserved_bp = [f"• **Body Preferences**: {'; '.join(_bp_seg)}"]
                else:
                    orig_desires = c["intimate_sections"].get("desires_and_turn_offs") or []
                    preserved_bp = [
                        str(line)
                        for line in orig_desires
                        if isinstance(line, str) and "Body Preferences" in line
                    ]
                if preserved_bp:
                    masked_sections["desires_and_turn_offs"] = preserved_bp + [masked_intimate_line]
            if any_intimate_disc and isinstance(c.get("intimate_structured"), dict):
                st_sec = c["intimate_structured"]
                vis_sp = [x["label"] for x in (st_sec.get("sensitive_spots") or []) if not x.get("masked")]
                if vis_sp:
                    has_hid_sp = any(x.get("masked") for x in (st_sec.get("sensitive_spots") or []))
                    masked_sections["sensitive_spots"] = [
                        f"• **Sensitive Spots**: {', '.join(vis_sp + (['???'] if has_hid_sp else []))}"
                    ]
                vis_des = [x["label"] for x in (st_sec.get("desires") or []) if not x.get("masked")]
                ak_sec = st_sec.get("active_kink")
                if isinstance(ak_sec, dict) and not ak_sec.get("masked") and ak_sec.get("label"):
                    vis_des.append(ak_sec["label"])
                vis_to = [x["label"] for x in (st_sec.get("turn_offs") or []) if not x.get("masked")]
                if vis_des or vis_to:
                    des_lines_p = list(masked_sections.get("desires_and_turn_offs") or [])
                    des_lines_p = [l for l in des_lines_p if "Body Preferences" in l]
                    if vis_des:
                        des_lines_p.insert(0, f"• **Desires & Kinks**: {', '.join(vis_des + (['???'] if any(x.get('masked') for x in (st_sec.get('desires') or [])) else []))}")
                    elif st_sec.get("desires") or st_sec.get("active_kink"):
                        des_lines_p.insert(0, f"• **Desires & Kinks**: {slot_mask}")
                    if vis_to:
                        des_lines_p.append(f"• **Turn-Offs**: {', '.join(vis_to + (['???'] if any(x.get('masked') for x in (st_sec.get('turn_offs') or [])) else []))}")
                    elif st_sec.get("turn_offs"):
                        des_lines_p.append(f"• **Turn-Offs**: {slot_mask}")
                    if des_lines_p:
                        masked_sections["desires_and_turn_offs"] = des_lines_p
                vis_al = [x["label"] for x in (st_sec.get("act_likes") or []) if not x.get("masked")]
                vis_ad = [x["label"] for x in (st_sec.get("act_dislikes") or []) if not x.get("masked")]
                if vis_al or vis_ad:
                    act_lines_p = []
                    if vis_al:
                        act_lines_p.append(f"• **Preferred / Likes**: {', '.join(vis_al + (['???'] if any(x.get('masked') for x in (st_sec.get('act_likes') or [])) else []))}")
                    elif st_sec.get("act_likes"):
                        act_lines_p.append(f"• **Preferred / Likes**: {slot_mask}")
                    if vis_ad:
                        act_lines_p.append(f"• **Aversions / Dislikes**: {', '.join(vis_ad + (['???'] if any(x.get('masked') for x in (st_sec.get('act_dislikes') or [])) else []))}")
                    elif st_sec.get("act_dislikes"):
                        act_lines_p.append(f"• **Aversions / Dislikes**: {slot_mask}")
                    masked_sections["act_preferences"] = act_lines_p
                u_sec = st_sec.get("undergarments") if isinstance(st_sec.get("undergarments"), dict) else {}
                if (u_sec.get("bra") and not u_sec.get("bra_masked")) or (u_sec.get("underwear") and not u_sec.get("underwear_masked")):
                    u_lines_p = []
                    if u_sec.get("bra"):
                        u_lines_p.append(f"• **Bra**: {u_sec['bra'] if not u_sec.get('bra_masked') else slot_mask}")
                    u_lines_p.append(f"• **Underwear**: {u_sec['underwear'] if not u_sec.get('underwear_masked') else slot_mask}")
                    masked_sections["undergarments"] = u_lines_p
            _rf_dyn = c.get("revealed_flags") if isinstance(c.get("revealed_flags"), dict) else {}
            _orig_dyn_lines = [str(x) for x in (c["intimate_sections"].get("dynamic") or [])]
            _dem_rev_line = next((l for l in _orig_dyn_lines if "**Demeanor**" in l), "") if _rf_dyn.get("demeanor_revealed") else ""
            _dyn_rev_line = next((l for l in _orig_dyn_lines if "**Dynamic**" in l), "") if _rf_dyn.get("dynamic_revealed") else ""
            _st_open_sec = c["intimate_structured"].get("openness") if isinstance(c.get("intimate_structured"), dict) else None
            _st_comf_sec = c["intimate_structured"].get("with_you_comfort") if isinstance(c.get("intimate_structured"), dict) else None
            _has_open_line = bool(
                openness_unlocked
                and isinstance(_st_open_sec, dict)
                and not _st_open_sec.get("masked")
                and _st_open_sec.get("label")
            )
            if _has_open_line or _dem_rev_line or _dyn_rev_line:
                if _has_open_line:
                    _open_sec_line = f"• **Openness**: {_st_open_sec['label']}"
                    if isinstance(_st_comf_sec, dict) and _st_comf_sec.get("badge_label"):
                        _open_sec_line += f" • **With-You Comfort**: {_st_comf_sec['badge_label']}"
                else:
                    _open_sec_line = f"• **Openness**: {slot_mask}"
                masked_sections["dynamic"] = [
                    _dem_rev_line or f"• **Demeanor**: {slot_mask}",
                    _dyn_rev_line or f"• **Dynamic**: {slot_mask}",
                    _open_sec_line,
                ]
            c["intimate_sections"] = masked_sections
        elif not _is_nsfw_fow and isinstance(c.get("intimate_sections"), dict):
            c["intimate_sections"] = {}
        if isinstance(c.get("appearance"), dict):
            scrubbed_app = dict(c["appearance"])
            _kept_open_val = (scrubbed_app.get("erotic_openness") or scrubbed_app.get("openness")) if openness_unlocked else None
            for _secret_k in (
                "anatomy", "experience",
                "intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                "intimate_demeanor", "intimate_dynamic", "erotic_openness", "openness",
                "bra", "underwear", "undergarments", "asset_texture", "rear_texture",
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
            if openness_unlocked:
                _open_tier_norm = ""
                if isinstance(c.get("intimate_structured"), dict):
                    _st_o_app = c["intimate_structured"].get("openness")
                    if isinstance(_st_o_app, dict) and not _st_o_app.get("masked"):
                        _open_tier_norm = str(_st_o_app.get("tier") or "").strip().lower()
                if not _open_tier_norm and _kept_open_val not in (None, ""):
                    from mechanics.social.persona import normalize_openness_tier
                    _open_tier_norm = normalize_openness_tier(_kept_open_val)
                if _open_tier_norm:
                    scrubbed_app["erotic_openness"] = _open_tier_norm
                    scrubbed_app["openness_revealed"] = True
            if scrubbed_app.get("breast_size"):
                from mechanics.social.persona.intimacy.appearance import strip_asset_texture_from_size
                stripped_b = strip_asset_texture_from_size(str(scrubbed_app["breast_size"]), gender="female")
                if stripped_b:
                    scrubbed_app["breast_size"] = stripped_b
            if scrubbed_app.get("rear_size"):
                from mechanics.social.persona.intimacy.appearance import strip_rear_texture_from_size
                stripped_r = strip_rear_texture_from_size(str(scrubbed_app["rear_size"]))
                if stripped_r:
                    scrubbed_app["rear_size"] = stripped_r
            if discovered_body_prefs or height_pref_unlocked:
                if isinstance(scrubbed_app.get("body_likes"), list):
                    scrubbed_app["body_likes"] = [
                        k for k in scrubbed_app["body_likes"]
                        if (
                            str(k).strip().lower() in discovered_body_prefs
                            or (height_pref_unlocked and str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS)
                        )
                    ]
                if isinstance(scrubbed_app.get("body_dislikes"), list):
                    scrubbed_app["body_dislikes"] = [
                        k for k in scrubbed_app["body_dislikes"]
                        if (
                            str(k).strip().lower() in discovered_body_prefs
                            or (height_pref_unlocked and str(k).strip().lower() in HEIGHT_PREFERENCE_KEYS)
                        )
                    ]
                if not discovered_body_prefs:
                    scrubbed_app.pop("body_preferences_revealed", None)
            else:
                scrubbed_app.pop("body_likes", None)
                scrubbed_app.pop("body_dislikes", None)
                scrubbed_app.pop("body_preferences_revealed", None)
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
                b_contact = db.get_contact(session_id, b_name, character_id=int(character_id or 0))
                if b_contact:
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=int(character_id or 0),
                        npc_id=b_name,
                        name=b_name,
                        delta_score=int(b_del),
                    )
                else:
                    b_wr = db.get_world_roster_npc(session_id, b_name, include_legacy_rosters=False)
                    if b_wr:
                        upd_b_wr = db.record_world_roster_interaction(
                            session_id,
                            b_wr.get("npc_id") or b_name,
                            delta_score=int(b_del),
                            met_in_person=True,
                            turn_number=turn_number,
                        ) or b_wr
                        from mechanics.social.relationships import should_promote_roster_npc_to_contact
                        do_prom_b, prom_reason_b = should_promote_roster_npc_to_contact(
                            upd_b_wr,
                            affinity=int(upd_b_wr.get("affinity_score") or 0),
                            scenario=scen,
                            session_id=session_id,
                        )
                        if do_prom_b:
                            db.promote_world_roster_to_contact(
                                session_id,
                                int(character_id or 0),
                                upd_b_wr.get("name") or b_name,
                                reason=prom_reason_b or "bystander_delta",
                                has_contact_info=bool((upd_b_wr.get("basic_info") or {}).get("has_contact_info") is True),
                                turn_number=turn_number,
                            )
                    elif not (db.get_session_world_nodes(session_id) or []):
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
