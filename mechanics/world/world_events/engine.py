from __future__ import annotations

import logging
import random
from typing import Any

import db
import llm_client
import scenario_data
from db.core import UnitOfWork

from .catalog import get_eligible_templates, is_minor_event_scenario_eligible, render_localized_template
from .constants import (
    AFTERMATH_BUZZ_HOURS,
    DAY_1_MACRO_EVENTS,
    DAY_1_MINOR_EVENTS,
    DAY_1_RUMORS,
    EVENT_PITY_THRESHOLD_MINUTES,
    MAX_ACTIVE_MACRO_EVENTS,
    MAX_ACTIVE_MINOR_EVENTS,
    MAX_ACTIVE_RUMORS,
    MAX_TRACKED_MINOR_BOUNTIES,
    MAX_TRACKED_RUMORS,
    MINOR_EVENT_DEFAULT_DURATION_MINUTES,
    MINOR_EVENT_PITY_THRESHOLD_MINUTES,
    RUMOR_FAILSAFE_DISCOVERY_MINUTES,
    RUMOR_PITY_THRESHOLD_MINUTES,
    SLEEP_OVERFLOW_PITY_RATIO,
    SLEEP_SKIP_MAX_SPAWNS,
    STORY_AFTERMATH_SPAWN_CHANCE,
    STORY_MILESTONE_PITY_BONUS,
)
from .formatting import extract_minor_events, resolve_event_description, resolve_session_time_and_turn
from .social_hooks import is_npc_scandal_eligible

log = logging.getLogger(__name__)


def _abs_minutes(day: int, minute: int) -> int:
    return (max(1, int(day)) - 1) * 1440 + max(0, int(minute))


def _from_abs_minutes(abs_min: int) -> tuple[int, int]:
    clamped = max(0, int(abs_min))
    return (clamped // 1440) + 1, clamped % 1440


def _gather_world_slots(session_id: int, rng: random.Random, template: dict[str, Any] | None = None) -> dict[str, Any]:
    """Extracts live faction, zone, venue, and scandal-safe NPC slots from session tables."""
    sess = db.get_session(session_id) or {}
    loc_str = str(sess.get("current_location") or "Central District ➔ Town Plaza ➔ Main Hall")
    parts = [p.strip() for p in loc_str.split("➔") if p.strip()]
    zone_name = parts[0] if parts else "Central District"
    venue_name = parts[-1] if len(parts) > 1 else "Gathering Hall"
    node_id = str(sess.get("current_node_id") or "")

    faction_id = ""
    faction_name = "Local Council"
    npc_name = "a prominent insider"
    implicated_contact_id: int | None = None

    party_names = {
        str(p.get("name") or "").strip().lower()
        for p in (sess.get("party_npcs") or [])
        if isinstance(p, dict) and p.get("name")
    }

    cand_ctx = db.get_world_event_candidate_context(session_id)
    fac_rows = cand_ctx.get("factions") or []
    tmpl_fams = set((template or {}).get("genre_families") or [])
    is_school_tmpl = bool(tmpl_fams & {"modern_school", "slice_of_life", "minor_high_school"})
    if fac_rows and scenario_data.is_anomalous_high_school_scenario(str(sess.get("scenario") or "")):
        from mechanics.social.factions import is_school_club_faction
        domain_facs = [f for f in fac_rows if is_school_club_faction(dict(f)) == is_school_tmpl]
        if domain_facs:
            fac_rows = domain_facs
    if fac_rows:
        picked_fac = dict(rng.choice(fac_rows))
        faction_id = str(picked_fac.get("faction_id") or "")
        faction_name = str(picked_fac.get("name") or faction_name)

    facilities = cand_ctx.get("facilities") or []
    tmpl_key = str((template or {}).get("template_key") or "")
    if tmpl_key in ("rumor_kitsune_torii_bells", "evt_kitsune_hundred_foxfires"):
        from mechanics.world.locations.folklore_veil import get_village_veil_status
        v_st = get_village_veil_status(session_id, "kitsune")
        zone_name = "Sacred Mountain Sanctuary & Onsen Quarter"
        node_id = "sub_kitsune_inner_plaza" if v_st.get("attuned") else "loc_et_fox_torii_tunnel"
        venue_name = "Sato-no-Inari — Hidden Kitsune Village" if v_st.get("attuned") else "Thousand-Torii Fox Shrine Approach"
    elif tmpl_key in ("rumor_bunian_cempaka_flute", "evt_bunian_malam_cempaka"):
        from mechanics.world.locations.folklore_veil import get_village_veil_status
        v_st = get_village_veil_status(session_id, "bunian")
        zone_name = "Wilderness Forest Reserve"
        node_id = "sub_bunian_inner_plaza" if v_st.get("attuned") else "loc_bunian_threshold_glade"
        venue_name = "Kampung Kayangan — Hidden Bunian Village" if v_st.get("attuned") else "Mist-Veiled Banyan & Bamboo Glade"
    elif facilities:
        picked_node = rng.choice(facilities)
        node_id = str(picked_node.get("node_id") or node_id)
        venue_name = str(picked_node.get("name") or venue_name)

    c_rows = cand_ctx.get("contacts") or []
    eligible_contacts = [dict(r) for r in c_rows if is_npc_scandal_eligible(dict(r), party_names=party_names)]
    if eligible_contacts:
        picked_c = rng.choice(eligible_contacts)
        npc_name = str(picked_c.get("name") or npc_name)
        implicated_contact_id = int(picked_c["id"])

    return {
        "slots": {"faction": faction_name, "npc": npc_name, "zone": zone_name, "venue": venue_name},
        "faction_id": faction_id,
        "location_node_id": node_id,
        "location_name": venue_name,
        "implicated_contact_id": implicated_contact_id,
        "implicated_npc_name": npc_name if implicated_contact_id is not None else "",
        "lang": str(sess.get("narration_language") or sess.get("language") or "en"),
        "scen_key": str(sess.get("scenario") or "fantasy"),
        "turn_number": db.infer_session_turn(sess),
    }


def _spawn_from_catalog(
    session_id: int,
    entity_type: str,
    scen_key: str,
    current_day: int,
    current_minute: int,
    turn_number: int,
    rng: random.Random,
    include_nsfw: bool,
    lang: str = "en",
    preferred_subtype: str = "",
    preferred_family: str = "",
) -> dict[str, Any] | None:
    templates = get_eligible_templates(scen_key, entity_type=entity_type, include_nsfw=include_nsfw)
    if not templates:
        return None

    existing_keys = {
        str(e.get("template_key") or "")
        for e in db.get_world_events(session_id, entity_type=entity_type, include_hidden=True, statuses=("active", "resolved_aftermath"))
    }
    pool = [t for t in templates if str(t.get("template_key") or "") not in existing_keys] or templates
    if preferred_subtype:
        sub_pool = [t for t in pool if t.get("event_subtype") == preferred_subtype]
        if sub_pool:
            pool = sub_pool
    if preferred_family:
        fam_pool = [t for t in pool if preferred_family in (t.get("genre_families") or [])]
        if fam_pool:
            pool = fam_pool

    chosen = rng.choice(pool)
    ctx = _gather_world_slots(session_id, rng, template=chosen)
    eff_lang = lang or ctx["lang"]
    rendered = render_localized_template(chosen, slots=ctx["slots"], lang=eff_lang, force_sfw_fallback=False)

    is_macro = entity_type == "macro_event"
    is_minor = entity_type == "minor_event"

    default_dur = MINOR_EVENT_DEFAULT_DURATION_MINUTES if is_minor else 5760
    duration_min = int(rendered.get("default_duration_minutes") or default_dur)
    jitter_min = rng.choice([-1440, 0, 1440]) if is_minor else rng.choice([0, 720, 1440])
    if is_minor:
        duration_min = max(2880, min(5760, duration_min + jitter_min))
        jitter_min = 0
    exp_day, exp_min = _from_abs_minutes(_abs_minutes(current_day, current_minute) + duration_min + jitter_min)

    seq = rng.randint(100, 999999)
    ev_key = f"we_{session_id}_{rendered['event_subtype']}_{seq}"

    metadata: dict[str, Any] = {
        "bounty_title": rendered["bounty_title"],
        "bounty_objective": rendered["bounty_objective"],
    }
    if is_minor:
        metadata["can_spawn_bounty"] = bool(rendered.get("can_spawn_bounty", False))

    imp_cid = ctx["implicated_contact_id"] if (not is_macro and not is_minor) else None
    if imp_cid is not None:
        metadata["implicated_npc_name"] = ctx["implicated_npc_name"]

    is_disc = 1 if (is_macro or is_minor) else 0
    disc_src = "world_event" if is_macro else ("bulletin" if is_minor else "")

    return db.create_world_event(
        session_id=session_id,
        event_key=ev_key,
        template_key=rendered["template_key"],
        entity_type=entity_type,
        event_subtype=rendered["event_subtype"],
        title=rendered["title"],
        description=rendered["description"],
        sfw_fallback_description=rendered["sfw_fallback_description"],
        faction_id=ctx["faction_id"],
        implicated_contact_id=imp_cid,
        location_node_id=ctx["location_node_id"],
        location_name=ctx["location_name"],
        is_discovered=is_disc,
        discovery_source=disc_src,
        turn_created=int(turn_number),
        expires_day=exp_day,
        expires_minute=exp_min,
        escalation_chance=0.0 if is_minor else rendered["escalation_chance"],
        is_nsfw=rendered["is_nsfw"],
        modifiers={} if is_minor else rendered["modifiers"],
        metadata=metadata,
    )


def seed_opening_world_events(
    session_id: int,
    scen_key: str = "",
    scenario_key: str = "",
    scenario: str = "",
    turn_number: int = 1,
    current_day: int = 1,
    current_minute: int = 480,
    include_nsfw: bool | None = None,
    language: str = "",
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Idempotently seeds Day 1 campaign state: 1 discovered Macro Event + 2 hidden Rumors (+2 Minor Events when eligible)."""
    if not session_id:
        return []
    existing = db.get_world_events(session_id, include_hidden=True)
    if existing:
        return existing

    sess = db.get_session(session_id) or {}
    eff_scen = str(scen_key or scenario_key or scenario or sess.get("scenario") or "fantasy")
    eff_lang = str(language or sess.get("narration_language") or sess.get("language") or "en")
    eff_nsfw = scenario_data.has_tag(eff_scen, "nsfw") if include_nsfw is None else (bool(include_nsfw) and scenario_data.has_tag(eff_scen, "nsfw"))
    rng = random.Random(seed if seed is not None else int(session_id) * 7919)

    spawned: list[dict[str, Any]] = []
    for _ in range(DAY_1_MACRO_EVENTS):
        ev = _spawn_from_catalog(
            session_id=session_id,
            entity_type="macro_event",
            scen_key=eff_scen,
            current_day=current_day,
            current_minute=current_minute,
            turn_number=turn_number,
            rng=rng,
            include_nsfw=eff_nsfw,
            lang=eff_lang,
        )
        if ev:
            spawned.append(ev)

    is_hybrid_ahs = scenario_data.is_anomalous_high_school_scenario(eff_scen)
    rumor_fams = ["urban_fantasy", "modern_school"] if is_hybrid_ahs else [""] * DAY_1_RUMORS
    for _r_idx in range(DAY_1_RUMORS):
        rm = _spawn_from_catalog(
            session_id=session_id,
            entity_type="rumor",
            scen_key=eff_scen,
            current_day=current_day,
            current_minute=current_minute,
            turn_number=turn_number,
            rng=rng,
            include_nsfw=eff_nsfw,
            lang=eff_lang,
            preferred_family=rumor_fams[_r_idx] if _r_idx < len(rumor_fams) else "",
        )
        if rm:
            spawned.append(rm)

    if is_minor_event_scenario_eligible(eff_scen):
        minor_fams = ["minor_anomaly_bureau", "minor_high_school"] if is_hybrid_ahs else [""] * DAY_1_MINOR_EVENTS
        for _m_idx in range(DAY_1_MINOR_EVENTS):
            mnr = _spawn_from_catalog(
                session_id=session_id,
                entity_type="minor_event",
                scen_key=eff_scen,
                current_day=current_day,
                current_minute=current_minute,
                turn_number=turn_number,
                rng=rng,
                include_nsfw=eff_nsfw,
                lang=eff_lang,
                preferred_family=minor_fams[_m_idx] if _m_idx < len(minor_fams) else "",
            )
            if mnr:
                spawned.append(mnr)
    return spawned


def advance_world_pulse(
    session_id: int,
    delta_minutes: int = 0,
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int | None = None,
    scen_key: str = "",
    scenario_key: str = "",
    is_sleep_skip: bool = False,
    include_nsfw: bool | None = None,
    language: str = "",
    seed: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Advances world event/rumor timers, 24h whisper failsafes, ~30% escalations, and continuous pity counters."""
    if not session_id:
        return {"spawned_events": [], "expired_keys": [], "escalated_keys": [], "auto_revealed_keys": []}

    sess = db.get_session(session_id) or {}
    current_day, current_minute, turn_number = resolve_session_time_and_turn(
        session_id, current_day, current_minute, turn_number, sess
    )

    eff_scen = str(scen_key or scenario_key or sess.get("scenario") or "fantasy")
    eff_lang = str(language or sess.get("narration_language") or sess.get("language") or "en")
    eff_nsfw = scenario_data.has_tag(eff_scen, "nsfw") if include_nsfw is None else (bool(include_nsfw) and scenario_data.has_tag(eff_scen, "nsfw"))
    rng = random.Random(seed if seed is not None else (int(session_id) * 1009 + int(current_day) * 1440 + int(current_minute)))

    now_abs = _abs_minutes(int(current_day), int(current_minute))
    with UnitOfWork():
        all_active = db.get_world_events(session_id, include_hidden=True, statuses=("active", "resolved_aftermath"))

        active_macro_count = sum(1 for e in all_active if e["entity_type"] == "macro_event" and e["status"] in ("active", "resolved_aftermath"))
        expired_keys: list[str] = []
        escalated_keys: list[str] = []
        auto_revealed_keys: list[str] = []
        spawned_events: list[dict[str, Any]] = []

        for ev in all_active:
            ev_key = ev["event_key"]
            exp_day = ev.get("expires_day")
            exp_min = ev.get("expires_minute")
            if exp_day is None or exp_min is None:
                continue
            exp_abs = _abs_minutes(int(exp_day), int(exp_min))
            remaining = exp_abs - now_abs

            # 1. 24h Pre-Expiry Whisper Auto-Reveal Failsafe for hidden rumors
            if ev["entity_type"] == "rumor" and not ev["is_discovered"] and ev["status"] == "active":
                if 0 < remaining <= RUMOR_FAILSAFE_DISCOVERY_MINUTES:
                    if db.discover_world_event(session_id, ev_key, int(turn_number), discovery_source="whisper_escalation_warning"):
                        auto_revealed_keys.append(ev_key)
                    continue

            if remaining > 0:
                continue

            # 2. Timer reached: handle aftermath expiry, 4-day cold transition, or ~30% escalation
            if ev["status"] == "resolved_aftermath":
                db.resolve_world_event(session_id, ev_key, "expired", int(current_day), int(current_minute), int(turn_number))
                expired_keys.append(ev_key)
                if ev["entity_type"] == "macro_event":
                    active_macro_count = max(0, active_macro_count - 1)
                continue

            if ev["entity_type"] in ("rumor", "minor_event") and ev.get("claimed_turn") is not None and ev.get("linked_quest_id"):
                # Neglected 4-day rumor investigation or minor bounty goes cold
                old_qid = str(ev["linked_quest_id"])
                db.mark_world_event_cold(session_id, ev_key, int(turn_number), old_qid)
                expired_keys.append(ev_key)
                continue

            if ev["entity_type"] == "rumor":
                esc_chance = float(ev.get("escalation_chance") or 0.0)
                if esc_chance > 0.0 and rng.random() < esc_chance:
                    if active_macro_count >= MAX_ACTIVE_MACRO_EVENTS:
                        # Defer escalation while macro event cap is full
                        defer_day, defer_min = _from_abs_minutes(now_abs + 1440)
                        db.defer_world_event_expiry(session_id, ev_key, defer_day, defer_min)
                        continue
                    escalated_ev = _spawn_from_catalog(
                        session_id=session_id,
                        entity_type="macro_event",
                        scen_key=eff_scen,
                        current_day=int(current_day),
                        current_minute=int(current_minute),
                        turn_number=int(turn_number),
                        rng=rng,
                        include_nsfw=eff_nsfw,
                        lang=eff_lang,
                        preferred_subtype="crisis",
                    )
                    db.resolve_world_event(session_id, ev_key, "escalated", int(current_day), int(current_minute), int(turn_number))
                    escalated_keys.append(ev_key)
                    if escalated_ev:
                        spawned_events.append(escalated_ev)
                        active_macro_count += 1
                    continue

            db.resolve_world_event(session_id, ev_key, "expired", int(current_day), int(current_minute), int(turn_number))
            expired_keys.append(ev_key)
            if ev["entity_type"] == "macro_event":
                active_macro_count = max(0, active_macro_count - 1)

        # 3. Continuous Pity Accumulation & Spawn Clamping
        refreshed = db.get_world_events(session_id, include_hidden=True, statuses=("active", "resolved_aftermath"))
        macro_cnt = sum(1 for e in refreshed if e["entity_type"] == "macro_event")
        rumor_cnt = sum(1 for e in refreshed if e["entity_type"] == "rumor")
        minor_cnt = sum(1 for e in refreshed if e["entity_type"] == "minor_event")

        pity = db.get_session_world_pity_state(session_id)
        ev_pity = float(pity["event_pity_counter"]) + max(0, int(delta_minutes))
        rm_pity = float(pity["rumor_pity_counter"]) + max(0, int(delta_minutes))
        mnr_pity = float(pity.get("minor_event_pity_counter") or 0.0) + max(0, int(delta_minutes))

        spawns_this_tick = len(spawned_events)
        max_spawns = SLEEP_SKIP_MAX_SPAWNS if is_sleep_skip else 2

        if ev_pity >= EVENT_PITY_THRESHOLD_MINUTES and macro_cnt < MAX_ACTIVE_MACRO_EVENTS and spawns_this_tick < max_spawns:
            new_ev = _spawn_from_catalog(
                session_id=session_id,
                entity_type="macro_event",
                scen_key=eff_scen,
                current_day=int(current_day),
                current_minute=int(current_minute),
                turn_number=int(turn_number),
                rng=rng,
                include_nsfw=eff_nsfw,
                lang=eff_lang,
            )
            if new_ev:
                spawned_events.append(new_ev)
                spawns_this_tick += 1
                overflow = max(0.0, ev_pity - EVENT_PITY_THRESHOLD_MINUTES)
                ev_pity = overflow * SLEEP_OVERFLOW_PITY_RATIO if is_sleep_skip else 0.0
        elif is_sleep_skip and ev_pity >= EVENT_PITY_THRESHOLD_MINUTES:
            ev_pity = EVENT_PITY_THRESHOLD_MINUTES * SLEEP_OVERFLOW_PITY_RATIO

        if rm_pity >= RUMOR_PITY_THRESHOLD_MINUTES and rumor_cnt < MAX_ACTIVE_RUMORS and spawns_this_tick < max_spawns:
            new_rm = _spawn_from_catalog(
                session_id=session_id,
                entity_type="rumor",
                scen_key=eff_scen,
                current_day=int(current_day),
                current_minute=int(current_minute),
                turn_number=int(turn_number),
                rng=rng,
                include_nsfw=eff_nsfw,
                lang=eff_lang,
            )
            if new_rm:
                spawned_events.append(new_rm)
                spawns_this_tick += 1
                overflow = max(0.0, rm_pity - RUMOR_PITY_THRESHOLD_MINUTES)
                rm_pity = overflow * SLEEP_OVERFLOW_PITY_RATIO if is_sleep_skip else 0.0
        elif is_sleep_skip and rm_pity >= RUMOR_PITY_THRESHOLD_MINUTES:
            rm_pity = RUMOR_PITY_THRESHOLD_MINUTES * SLEEP_OVERFLOW_PITY_RATIO

        if is_minor_event_scenario_eligible(eff_scen):
            if mnr_pity >= MINOR_EVENT_PITY_THRESHOLD_MINUTES and minor_cnt < MAX_ACTIVE_MINOR_EVENTS and spawns_this_tick < max_spawns:
                new_mnr = _spawn_from_catalog(
                    session_id=session_id,
                    entity_type="minor_event",
                    scen_key=eff_scen,
                    current_day=int(current_day),
                    current_minute=int(current_minute),
                    turn_number=int(turn_number),
                    rng=rng,
                    include_nsfw=eff_nsfw,
                    lang=eff_lang,
                )
                if new_mnr:
                    spawned_events.append(new_mnr)
                    spawns_this_tick += 1
                    overflow = max(0.0, mnr_pity - MINOR_EVENT_PITY_THRESHOLD_MINUTES)
                    mnr_pity = overflow * SLEEP_OVERFLOW_PITY_RATIO if is_sleep_skip else 0.0
            elif is_sleep_skip and mnr_pity >= MINOR_EVENT_PITY_THRESHOLD_MINUTES:
                mnr_pity = MINOR_EVENT_PITY_THRESHOLD_MINUTES * SLEEP_OVERFLOW_PITY_RATIO
        else:
            mnr_pity = 0.0

        db.update_session_world_pity_state(
            session_id,
            event_pity_counter=round(ev_pity, 2),
            rumor_pity_counter=round(rm_pity, 2),
            minor_event_pity_counter=round(mnr_pity, 2),
        )

    return {
        "spawned_events": spawned_events,
        "expired_keys": expired_keys,
        "escalated_keys": escalated_keys,
        "auto_revealed_keys": auto_revealed_keys,
    }


def on_quest_or_bounty_completed(
    session_id: int,
    quest_id: str,
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int | None = None,
    quest_type: str = "bounty",
    **kwargs: Any,
) -> dict[str, Any]:
    """Resolves linked rumors & crisis events into 24h aftermath buzz while preserving festivals' full schedules."""
    if not session_id or not quest_id:
        return {"resolved_keys": [], "aftermath_spawned": None}

    sess = db.get_session(session_id) or {}
    current_day, current_minute, turn_number = resolve_session_time_and_turn(
        session_id, current_day, current_minute, turn_number, sess
    )

    resolved_keys: list[str] = []
    q_row = db.get_quest_by_id(session_id, str(quest_id)) or {}
    q_notes = str(q_row.get("quest_notes") or "")
    scar_ev_target = ""
    for part in q_notes.split("|"):
        if part.startswith("remediation_scar:"):
            scar_ev_target = part.split(":", 1)[1].strip()
            break

    events = db.get_world_events(session_id, include_hidden=True, statuses=("active",))
    for ev in events:
        matches_link = str(ev.get("linked_quest_id") or "") == str(quest_id)
        matches_scar_note = bool(scar_ev_target and str(ev.get("event_key") or "") == scar_ev_target)
        if not (matches_link or matches_scar_note):
            continue
        if ev["entity_type"] == "macro_event" and ev.get("event_subtype") == "festival":
            # Festivals run their full 4-7 day schedule even after completing festival bounties
            continue
        if db.resolve_world_event(
            session_id=session_id,
            event_key=ev["event_key"],
            new_status="resolved_aftermath",
            current_day=int(current_day),
            current_minute=int(current_minute),
            turn_number=int(turn_number),
            aftermath_hours=AFTERMATH_BUZZ_HOURS,
        ):
            resolved_keys.append(ev["event_key"])

    aftermath_spawned = None
    is_story = "story" in str(quest_type or "").lower() or "main" in str(quest_type or "").lower() or bool(kwargs.get("is_story_quest"))
    if is_story:
        pity = db.get_session_world_pity_state(session_id)
        db.update_session_world_pity_state(
            session_id,
            event_pity_counter=float(pity["event_pity_counter"]) + STORY_MILESTONE_PITY_BONUS,
            rumor_pity_counter=float(pity["rumor_pity_counter"]) + STORY_MILESTONE_PITY_BONUS,
        )
        rng = random.Random(int(session_id) * 313 + int(turn_number))
        if rng.random() < STORY_AFTERMATH_SPAWN_CHANCE:
            scen_key = str(sess.get("scenario") or "fantasy")
            refreshed = db.get_world_events(session_id, include_hidden=True, statuses=("active", "resolved_aftermath"))
            rumor_cnt = sum(1 for e in refreshed if e["entity_type"] == "rumor")
            if rumor_cnt < MAX_ACTIVE_RUMORS:
                aftermath_spawned = _spawn_from_catalog(
                    session_id=session_id,
                    entity_type="rumor",
                    scen_key=scen_key,
                    current_day=int(current_day),
                    current_minute=int(current_minute),
                    turn_number=int(turn_number),
                    rng=rng,
                    include_nsfw=scenario_data.has_tag(scen_key, "nsfw"),
                )

    return {"resolved_keys": resolved_keys, "aftermath_spawned": aftermath_spawned}


def discover_hidden_rumor_from_feed(
    session_id: int,
    discovery_source: str = "phone_gossip_feed",
) -> dict[str, Any] | None:
    """Reveals one hidden active rumor when the player scours phone gossip feeds or notice boards."""
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    turn_num = db.infer_session_turn(sess)
    hidden = [
        r for r in db.get_world_events(session_id, entity_type="rumor", include_hidden=True, statuses=("active",))
        if not r.get("is_discovered")
    ]
    if not hidden:
        return None
    picked = hidden[0]
    db.discover_world_event(session_id, picked["event_key"], turn_number=turn_num, discovery_source=discovery_source)
    updated = [
        r for r in db.get_world_events(session_id, entity_type="rumor", include_hidden=False, statuses=("active",))
        if r["event_key"] == picked["event_key"]
    ]
    return updated[0] if updated else picked


def build_client_world_pulse_payload(
    session_id: int,
    current_day: int | None = None,
    current_minute: int | None = None,
    lang: str = "en",
    scen_key: str = "",
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Builds safe omnichannel World Pulse payload (NEVER leaking undiscovered rumors over HTTP/WS/Discord)."""
    if not session_id:
        return {
            "session_id": 0,
            "current_day": 1,
            "current_minute": 480,
            "active_macro_events": [],
            "active_rumors": [],
            "active_minor_events": [],
            "can_track_rumor": True,
            "tracked_rumor_count": 0,
            "max_tracked_rumors": MAX_TRACKED_RUMORS,
            "can_track_minor_bounty": True,
            "tracked_minor_bounty_count": 0,
            "max_tracked_minor_bounties": MAX_TRACKED_MINOR_BOUNTIES,
        }
    current_day, current_minute, _ = resolve_session_time_and_turn(
        session_id, current_day, current_minute, turn_number=1
    )

    snap = snapshot if isinstance(snapshot, dict) else db.get_world_events_snapshot(session_id)
    eff_scen = str(
        scen_key
        or (snap.get("scen_key") if isinstance(snap, dict) else "")
        or (snap.get("scenario") if isinstance(snap, dict) else "")
    )
    if not eff_scen:
        sess = db.get_session(session_id) or {}
        eff_scen = str(sess.get("scenario") or "fantasy")
    allow_nsfw = bool(scenario_data.uses_nsfw_model(eff_scen) and llm_client.is_nsfw_configured())

    def _clean_item(ev: dict[str, Any]) -> dict[str, Any]:
        item = dict(ev)
        item["description"] = resolve_event_description(item, allow_nsfw=allow_nsfw)
        return item

    macros = [_clean_item(e) for e in (snap.get("active_macro_events") or [])]
    discovered_rumors = [
        _clean_item(r) for r in (snap.get("discovered_rumors") or [])
        if bool(r.get("is_discovered"))
    ]
    raw_minors = extract_minor_events(snap)
    active_minor = [_clean_item(m) for m in raw_minors]

    all_active_quests = db.get_session_quests(session_id, status="Active") or []
    active_rmr_quests = [
        q for q in all_active_quests
        if str(q.get("quest_id") or "").upper().startswith("RMR-")
        or "rumor_investigation:1" in str(q.get("quest_notes") or "")
    ]
    active_mnr_quests = [
        q for q in all_active_quests
        if str(q.get("quest_id") or "").upper().startswith("MNR-")
        or "minor_bounty:1" in str(q.get("quest_notes") or "")
    ]
    tracked_cnt = len(active_rmr_quests)
    tracked_mnr_cnt = len(active_mnr_quests)
    pity = snap.get("pity_state") or {}

    return {
        "session_id": int(session_id),
        "current_day": int(current_day),
        "current_minute": int(current_minute),
        "active_macro_events": macros,
        "active_rumors": discovered_rumors,
        "active_minor_events": active_minor,
        "can_track_rumor": tracked_cnt < MAX_TRACKED_RUMORS,
        "tracked_rumor_count": tracked_cnt,
        "max_tracked_rumors": MAX_TRACKED_RUMORS,
        "can_track_minor_bounty": tracked_mnr_cnt < MAX_TRACKED_MINOR_BOUNTIES,
        "tracked_minor_bounty_count": tracked_mnr_cnt,
        "max_tracked_minor_bounties": MAX_TRACKED_MINOR_BOUNTIES,
        "event_pity_counter": float(pity.get("event_pity_counter") or 0.0),
        "rumor_pity_counter": float(pity.get("rumor_pity_counter") or 0.0),
        "minor_event_pity_counter": float(pity.get("minor_event_pity_counter") or 0.0),
    }


def spawn_quest_world_scar(
    session_id: int,
    source_quest_id: str,
    scar_spec: dict[str, Any] | None = None,
    location_name: str = "",
    location_node_id: str = "",
    faction_id: str = "",
    turn_number: int | None = None,
    spawn_remediation_bounty: bool = True,
    scar_tier: str = "",
) -> dict[str, Any]:
    """
    Persists a permanent fail-forward `WorldScar` inside `world_events` (`is_world_scar: True`).
    Two-Tier Overhaul:
    - Side Bounties (`scar_tier == "bounty"`): spawn standard 65g `REM-` Remediation Bounties.
    - Main-Quest Buildup Scars (`scar_tier == "buildup"`, Ch. 1, 2, 4, 5, 7): suppress cheap `REM-`
      and spawn high-danger (`danger_tier >= 3`) `LIB-` Liberation Operations.
    - Main-Quest Peak Scars (`scar_tier == "peak"`, Ch. 3, 6, 8, 9, 10): spawn ZERO pre-Climax
      remediation (permanent through Ch. 10; liberatable in post-Ch. 11 Fallen-World Resistance Mode).
    """
    if not session_id:
        return {}
    sess = db.get_session(session_id) or {}
    eff_lang = str(sess.get("language") or "en").strip().lower()
    scen_key = str(sess.get("scenario") or "fantasy")
    c_day, _c_min, t_num = resolve_session_time_and_turn(session_id, None, None, turn_number, sess)
    spec = dict(scar_spec or {})
    venue = str(location_name or sess.get("current_location") or "Local District")
    nid = str(location_node_id or sess.get("current_node_id") or "")
    scar_type = str(spec.get("scar_type") or "security_crackdown")
    title = str(spec.get("title") or f"Fallout at {venue}")
    desc = str(spec.get("description") or f"Unresolved consequences from '{source_quest_id}' linger across {venue}.")
    modifiers = dict(spec.get("modifiers") or {"dc_modifiers": {"CHA": 1, "AGI": 1}, "price_multiplier": 1.15})

    # Determine scar_tier ("bounty" | "buildup" | "peak")
    eff_tier = str(scar_tier or spec.get("scar_tier") or "").strip().lower()
    if eff_tier not in ("bounty", "buildup", "peak"):
        src_q = db.get_quest_by_id(session_id, str(source_quest_id or "")) or {}
        is_story_src = bool(
            src_q.get("is_story_quest")
            or str(source_quest_id or "").upper().startswith("SQ-")
            or "story" in str(src_q.get("quest_type") or "").lower()
        )
        if is_story_src:
            ch_num = int(spec.get("chapter_number") or 0)
            if ch_num <= 0:
                spine_row = db.get_campaign_spine(session_id) or {}
                ch_num = int(spine_row.get("current_chapter") or 1)
            eff_tier = "peak" if ch_num in (3, 6, 8, 9, 10) else "buildup"
        else:
            eff_tier = "bounty"

    # Enforce Safe Hub Sanctuary exemption so >= 1 hub facility NEVER locks down
    sanctuary_nid = ""
    try:
        from mechanics.world.locations.access_gate import get_designated_hub_sanctuary_node_id, is_safe_sanctuary_node
        sanctuary_nid = get_designated_hub_sanctuary_node_id(session_id)
        is_lockdown_scar = bool(
            spec.get("lockdown")
            or scar_type in ("martial_law", "martial_curfew", "district_lockdown", "occupation", "quarantine")
        )
        if eff_tier == "peak" and is_lockdown_scar:
            modifiers["is_locked"] = True
            if scar_type in ("martial_law", "martial_curfew", "district_lockdown") or spec.get("lockdown") or not nid:
                modifiers["martial_law_lockdown"] = True
        if nid and is_safe_sanctuary_node(session_id, nid):
            modifiers.pop("is_locked", None)
        if sanctuary_nid and isinstance(modifiers.get("lockdown_nodes"), list):
            modifiers["lockdown_nodes"] = [
                n for n in modifiers["lockdown_nodes"] if str(n).strip().lower() != sanctuary_nid.lower()
            ]
    except Exception:
        pass

    clean_qid = "".join(ch if ch.isalnum() else "_" for ch in str(source_quest_id or "q")).strip("_")[:24]
    ev_key = f"scar_{session_id}_{clean_qid}"
    if eff_tier == "peak" or not spawn_remediation_bounty:
        rem_qid = ""
    elif eff_tier == "buildup":
        rem_qid = f"LIB-{clean_qid}"
    else:
        rem_qid = f"REM-{clean_qid}"

    ev = db.create_world_event(
        session_id=session_id,
        event_key=ev_key,
        template_key=f"world_scar_{scar_type}",
        entity_type="macro_event",
        event_subtype="crisis",
        title=title,
        description=desc,
        sfw_fallback_description=desc,
        faction_id=faction_id,
        location_node_id=nid,
        location_name=venue,
        is_discovered=1,
        discovery_source="quest_fallout",
        turn_created=int(t_num),
        expires_day=int(c_day) + 36500,
        expires_minute=0,
        escalation_chance=0.0,
        is_nsfw=0,
        modifiers=modifiers,
        metadata={
            "is_world_scar": True,
            "scar_tier": eff_tier,
            "scar_type": scar_type,
            "source_quest_id": str(source_quest_id or ""),
            "remediation_quest_id": rem_qid,
            "safe_sanctuary_exempt_node": sanctuary_nid,
        },
        linked_quest_id=rem_qid or None,
    )

    if spawn_remediation_bounty and rem_qid:
        if eff_tier == "buildup":
            from mechanics.narrative.quest_engines import render_liberation_op_spec
            lib_spec = render_liberation_op_spec(venue, lang=eff_lang, is_peak_resistance=False)
            lib_title = str(spec.get("remediation_title") or lib_spec["title"])
            lib_obj = str(spec.get("remediation_objective") or lib_spec["objective"])
            lib_danger = max(3, int(spec.get("danger_tier") or 3))
            db.upsert_quest(
                session_id=session_id,
                quest_id=rem_qid,
                quest_type="Liberation Operation",
                title=lib_title,
                objective=lib_obj,
                status="Available",
                reward_xp=210,
                reward_gold=140,
                quest_notes=f"remediation_scar:{ev_key}|liberation_op:1|scar_tier:buildup",
                blueprint_id="SITE_DEFENSE_RITUAL",
                client_npc="Resistance Coordinator",
                client_location=venue,
                deadline_day=int(c_day) + 10,
                deadline_minute=720,
                engine="CRISIS_DEFENSE",
                dossier_stage="compiled",
            )
            try:
                from mechanics.narrative.dossier_compiler import compile_quest_dossier
                compile_quest_dossier(
                    session_id=session_id,
                    quest_id=rem_qid,
                    tag_or_archetype="CRISIS_DEFENSE",
                    title=lib_title,
                    objective=lib_obj,
                    family_tier="bounty",
                    danger_tier=lib_danger,
                    turn_number=int(t_num),
                    client_npc="Resistance Coordinator",
                    preferred_location=venue,
                    scen_key=scen_key,
                    lang=eff_lang,
                )
            except Exception:
                db.save_quest_waypoints(
                    session_id,
                    rem_qid,
                    [
                        {"stage_index": 1, "sub_obj_id": 0, "stage_label": f"Break hostile occupation at {venue}", "target_location": venue, "completion_trigger": "skill_check", "status": "active"},
                        {"stage_index": 2, "sub_obj_id": 0, "stage_label": f"Restore civic control at {venue}", "target_location": venue, "completion_trigger": "skill_check", "status": "locked"},
                    ],
                )
        else:
            rem_title = str(spec.get("remediation_title") or f"Remediate: {title}")
            rem_obj = f"Stabilize fallout and lift '{title}' around {venue}."
            db.upsert_quest(
                session_id=session_id,
                quest_id=rem_qid,
                quest_type="Remediation Bounty",
                title=rem_title,
                objective=rem_obj,
                status="Available",
                reward_xp=125,
                reward_gold=65,
                quest_notes=f"remediation_scar:{ev_key}",
                blueprint_id="SITE_DEFENSE_RITUAL",
                client_npc="Civic Dispatcher",
                client_location=venue,
                deadline_day=int(c_day) + 7,
                deadline_minute=720,
                engine="CRISIS_DEFENSE",
                dossier_stage="pitch",
            )
            db.save_quest_waypoints(
                session_id,
                rem_qid,
                [
                    {"stage_index": 1, "stage_label": f"Assess fallout at {venue}", "target_location": venue, "completion_trigger": "arrival", "status": "active"},
                    {"stage_index": 2, "stage_label": f"Resolve {title}", "target_location": venue, "completion_trigger": "skill_check", "status": "locked"},
                ],
            )
            try:
                from mechanics.narrative.dossier_compiler import compile_bounty_pitch_stub
                compile_bounty_pitch_stub(
                    session_id=session_id,
                    quest_id=rem_qid,
                    tag_or_archetype="CRISIS_DEFENSE",
                    title=rem_title,
                    public_pitch=rem_obj,
                    client_npc="Civic Dispatcher",
                    client_location=venue,
                    reward_gold=65,
                    reward_xp=125,
                    danger_tier=2,
                    deadline_day=int(c_day) + 7,
                    deadline_minute=720,
                    scen_key=scen_key,
                )
            except Exception:
                pass
    return ev or {}


def resolve_world_scar_via_bounty(
    session_id: int,
    quest_id: str,
    turn_number: int | None = None,
) -> list[str]:
    """Resolves any active `WorldScar` linked to a completed Remediation Bounty."""
    res = on_quest_or_bounty_completed(session_id=session_id, quest_id=quest_id, turn_number=turn_number)
    return list(res.get("resolved_keys") or [])


def spawn_endless_mode_contracts(
    session_id: int,
    turn_number: int = 1,
) -> list[dict[str, Any]]:
    """
    Post-Chapter 11 Endless Sandbox Mode generator:
    Spawns Escaped Nemesis Hunts, WorldScar Remediation Bounties, Companion Loyalty (`CLR-`)
    milestones, and 2-3 part Faction Mini-Arcs.
    """
    if not session_id:
        return []
    sess = db.get_session(session_id) or {}
    eff_lang = str(sess.get("language") or "en").strip().lower()
    scen_key = str(sess.get("scenario") or "fantasy")
    c_day = int(sess.get("current_day") or 1)
    loc = str(sess.get("current_location") or "Central Ward")
    spawned: list[dict[str, Any]] = []

    from mechanics.narrative.dossier_compiler import compile_bounty_pitch_stub, compile_quest_dossier
    from mechanics.narrative.campaign_spine import resolve_campaign_ending_archetype
    from mechanics.narrative.quest_engines import render_liberation_op_spec

    spine = db.get_campaign_spine(session_id) or {}
    tapestry = spine.get("chronicle_tapestry") or {}
    ending_id = str(tapestry.get("ending_id") or "")
    if not ending_id:
        try:
            ending_id = resolve_campaign_ending_archetype(session_id, spine=spine)
        except Exception:
            ending_id = "golden_restoration"
    endless_mode_key = str(tapestry.get("endless_mode") or (
        "fallen_world_resistance" if ending_id == "fallen_world" else "reconstruction_sandbox"
    ))

    # 0. Fallen-World Resistance & Unresolved Peak Scar Liberation Operations (`LIB-RES-`)
    active_scars = [
        ev for ev in (db.get_world_events(session_id, entity_type="macro_event", statuses=("active",)) or [])
        if isinstance(ev, dict) and (ev.get("metadata") or {}).get("is_world_scar")
    ]
    for scar_ev in active_scars:
        meta = scar_ev.get("metadata") or {}
        s_tier = str(meta.get("scar_tier") or "")
        if s_tier != "peak" and endless_mode_key != "fallen_world_resistance":
            continue
        ev_key = str(scar_ev.get("event_key") or "")
        clean_ev = "".join(ch if ch.isalnum() else "_" for ch in ev_key).strip("_")[-20:] or "scar"
        lib_qid = f"LIB-RES-{clean_ev}".upper()
        if db.get_quest_by_id(session_id, lib_qid):
            continue
        scar_venue = str(scar_ev.get("location_name") or loc)
        lib_spec = render_liberation_op_spec(scar_venue, lang=eff_lang, is_peak_resistance=True)
        lib_q = db.upsert_quest(
            session_id=session_id,
            quest_id=lib_qid,
            quest_type="Liberation Operation",
            title=lib_spec["title"],
            objective=lib_spec["objective"],
            status="Available",
            reward_xp=260,
            reward_gold=180,
            quest_notes=f"remediation_scar:{ev_key}|liberation_op:1|scar_tier:peak|endless_mode:{endless_mode_key}",
            blueprint_id="SITE_DEFENSE_RITUAL",
            client_npc="Underground Resistance Cell",
            client_location=scar_venue,
            deadline_day=c_day + 14,
            deadline_minute=720,
            engine="CRISIS_DEFENSE",
            dossier_stage="compiled",
        )
        compile_quest_dossier(
            session_id=session_id,
            quest_id=lib_qid,
            tag_or_archetype="CRISIS_DEFENSE",
            title=lib_spec["title"],
            objective=lib_spec["objective"],
            family_tier="bounty",
            danger_tier=4,
            turn_number=turn_number,
            client_npc="Underground Resistance Cell",
            preferred_location=scar_venue,
            scen_key=scen_key,
            lang=eff_lang,
        )
        if lib_q:
            spawned.append(lib_q)

    # 1. Escaped Nemesis Hunts from campaign_spines.nemeses_json
    for nem in (spine.get("nemeses") or []):
        if nem.get("status") != "at_large":
            continue
        nem_qid = f"NEM-{nem.get('nemesis_id', 'hunt')}".upper()
        if db.get_quest_by_id(session_id, nem_qid):
            continue
        n_name = str(nem.get("name") or "Escaped Nemesis")
        q_row = db.upsert_quest(
            session_id=session_id,
            quest_id=nem_qid,
            quest_type="Nemesis Hunt",
            title=f"Nemesis Reckoning: {n_name}",
            objective=f"Track down and settle the score with escaped nemesis {n_name}.",
            status="Available",
            reward_xp=220,
            reward_gold=140,
            quest_notes=f"nemesis_hunt:1|nemesis_id:{nem.get('nemesis_id', '')}",
            blueprint_id="NEUTRALIZATION",
            client_npc="Vanguard Watch",
            client_location=loc,
            deadline_day=c_day + 7,
            deadline_minute=720,
            engine="HUNT_CONTAINMENT",
            dossier_stage="pitch",
        )
        db.save_quest_waypoints(
            session_id,
            nem_qid,
            [
                {"stage_index": 1, "stage_label": f"Pinpoint {n_name}'s stronghold", "target_location": loc, "completion_trigger": "skill_check", "status": "active"},
                {"stage_index": 2, "stage_label": f"Confront {n_name}", "target_location": loc, "target_npc": n_name, "completion_trigger": "skill_check", "status": "locked"},
            ],
        )
        compile_bounty_pitch_stub(
            session_id=session_id,
            quest_id=nem_qid,
            tag_or_archetype="HUNT_CONTAINMENT",
            title=f"Nemesis Reckoning: {n_name}",
            public_pitch=f"{n_name} has resurfaced stronger than before—finish what began.",
            client_npc="Vanguard Watch",
            client_location=loc,
            reward_gold=140,
            reward_xp=220,
            danger_tier=4,
            deadline_day=c_day + 7,
            scen_key=scen_key,
        )
        if q_row:
            spawned.append(q_row)

    # 2. Companion Loyalty Milestone (`CLR-`) if party has an NPC companion
    party_npcs = db.get_session_party_npcs(session_id) or []
    if party_npcs:
        comp_name = str(party_npcs[0].get("name") or "Companion")
        comp_slug = comp_name.lower().replace(" ", "_")[:12]
        clr_qid = f"CLR-{comp_slug}"
        if not db.get_quest_by_id(session_id, clr_qid):
            clr_q = db.upsert_quest(
                session_id=session_id,
                quest_id=clr_qid,
                quest_type="Companion Loyalty",
                title=f"Unfinished Past: {comp_name}",
                objective=f"Stand beside {comp_name} to resolve a personal debt from their past.",
                status="Active",
                reward_xp=180,
                reward_gold=80,
                quest_notes="companion_loyalty:1",
                blueprint_id="SOCIAL_MANIPULATION",
                client_npc=comp_name,
                client_location=loc,
                engine="SOCIAL_BROKERAGE",
                dossier_stage="compiled",
            )
            from mechanics.narrative.dossier_compiler import compile_quest_dossier
            compile_quest_dossier(
                session_id=session_id,
                quest_id=clr_qid,
                tag_or_archetype="SOCIAL_BROKERAGE",
                title=f"Unfinished Past: {comp_name}",
                objective=f"Stand beside {comp_name} to resolve a personal debt from their past.",
                family_tier="loyalty",
                danger_tier=3,
                turn_number=turn_number,
                client_npc=comp_name,
                preferred_location=loc,
                scen_key=scen_key,
            )
            if clr_q:
                spawned.append(clr_q)

    # 3. 2-3 Part Faction Mini-Arc Part 1
    arc_qid = "FARC-P1"
    if not db.get_quest_by_id(session_id, arc_qid):
        factions = db.get_factions(session_id) or []
        fac_name = str((factions[0].get("name") if factions else "") or "Regional Coalition")
        arc_q = db.upsert_quest(
            session_id=session_id,
            quest_id=arc_qid,
            quest_type="Faction Mini-Arc",
            title=f"{fac_name}: Shadow Accord (Part 1/3)",
            objective=f"Uncover who is sabotaging {fac_name}'s post-crisis truce.",
            status="Available",
            reward_xp=160,
            reward_gold=100,
            quest_notes="faction_mini_arc:1|arc_part:1|arc_total:3",
            blueprint_id="INVESTIGATION",
            client_npc=f"{fac_name} Envoy",
            client_location=loc,
            deadline_day=c_day + 7,
            engine="MYSTERY_CASE",
            dossier_stage="pitch",
        )
        db.save_quest_waypoints(
            session_id,
            arc_qid,
            [
                {"stage_index": 1, "stage_label": f"Inspect sabotaged outpost at {loc}", "target_location": loc, "completion_trigger": "skill_check", "status": "active"},
                {"stage_index": 2, "stage_label": "Report findings to Envoy", "target_location": loc, "completion_trigger": "skill_check", "status": "locked"},
            ],
        )
        compile_bounty_pitch_stub(
            session_id=session_id,
            quest_id=arc_qid,
            tag_or_archetype="MYSTERY_CASE",
            title=f"{fac_name}: Shadow Accord (Part 1/3)",
            public_pitch=f"{fac_name} seeks seasoned operatives for a 3-part post-crisis operation.",
            client_npc=f"{fac_name} Envoy",
            client_location=loc,
            reward_gold=100,
            reward_xp=160,
            danger_tier=3,
            deadline_day=c_day + 7,
            scen_key=scen_key,
        )
        if arc_q:
            spawned.append(arc_q)

    return spawned
