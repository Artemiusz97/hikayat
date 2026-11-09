from __future__ import annotations
"""
Entity Contract Narrative Stage Directions & SDXL Visual Tag Formatting (Layer 2).

Enforces Hikayat's Zero Stat & Tag Leakage invariant:
- Never emit raw HP/MP integers, `%` numbers, `DC` values, or `[Pact-Bound]` / `[GEAR_JSON]`
  markers into player-facing narrative prose or LLM stage directions.
"""

from typing import Any, Dict, Iterable, List, Optional

from .catalog import apply_patron_variant_and_locale, get_patron_by_id, is_entity_contracts_scenario


def _clean_tag_leak_tokens(text: str) -> str:
    cleaned = str(text or "")
    for token in ("[Pact-Bound]", "[GEAR_JSON]", "[ITEM_JSON]", "[SPELLBOOK_JSON]"):
        cleaned = cleaned.replace(token, "").strip()
    return " ".join(cleaned.split())


def build_actor_pact_tell_phrase(
    pacts: Optional[Iterable[Dict[str, Any]]],
    scenario_or_key: Any = None,
) -> str:
    """
    Returns a compact, stat-free physical Contract Tell note for `Z2` actor sheets.
    Returns `""` when the actor holds no active Entity Contracts.
    """
    if not pacts:
        return ""
    tell_parts: List[str] = []
    for row in pacts:
        if not isinstance(row, dict) or str(row.get("status") or "active") != "active":
            continue
        pid = str(row.get("patron_id") or "").strip()
        patron = get_patron_by_id(pid, scenario_or_key=scenario_or_key)
        name = _clean_tag_leak_tokens(
            str((patron or {}).get("display_name") or row.get("entity_name") or pid)
        )
        visuals = (patron or {}).get("visuals") or {}
        tell_prose = _clean_tag_leak_tokens(
            str(visuals.get("rest_tell_prose") or row.get("pact_tell") or "a subtle occult covenant mark")
        )
        breach_note = " (restless, displeased aura)" if int(row.get("breach_stage") or 0) >= 1 else ""
        tell_parts.append(f"{name}: {tell_prose}{breach_note}")
    if not tell_parts:
        return ""
    return f"[Entity Contracts — {'; '.join(tell_parts)}]"


def build_pact_turn_stage_direction(events: Optional[Iterable[Dict[str, Any]]]) -> str:
    """
    Builds `Z3` deterministic stage directions for Pact casts, Lethal Overdraws, breaches,
    surrenders, and exorcisms without exposing raw numbers or internal bracketed item tags.
    """
    if not events:
        return ""
    lines: List[str] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        etype = str(ev.get("type") or "").strip().lower()
        actor = _clean_tag_leak_tokens(str(ev.get("actor") or "the protagonist"))
        patron_name = _clean_tag_leak_tokens(str(ev.get("patron_name") or ev.get("entity_name") or "their bound entity"))
        skill_name = _clean_tag_leak_tokens(str(ev.get("skill_name") or "their covenanted art"))

        if etype == "pact_cast":
            lines.append(
                f"- {actor} invokes their covenant with {patron_name} ({skill_name}), paying the entity's visceral toll in real time."
            )
        elif etype == "lethal_overdraw":
            lines.append(
                f"- LETHAL OVERDRAW: {actor} pushes {patron_name}'s covenant past mortal limits—{skill_name} erupts at full cataclysmic force before {actor} collapses from the toll, triggering emergency field extraction and leaving {patron_name} displeased with an unpaid blood debt."
            )
        elif etype == "breach_stage1":
            lines.append(
                f"- COVENANT DISPLEASURE: {patron_name}'s mark sears coldly against {actor}; until an offering settles the debt, {patron_name} withholds its power."
            )
        elif etype == "breach_stage2":
            nemesis_clause = (
                f" Manifesting in fury, {patron_name} tears loose into the scene as a vengeful apparition!"
                if ev.get("grudge_nemesis_spawned")
                else ""
            )
            lines.append(
                f"- VIOLENT SEVERANCE: {patron_name} violently rips its covenant from {actor}, leaving a lingering spiritual scar where the bond once rested.{nemesis_clause}"
            )
        elif etype == "boss_surrender_sealed":
            lines.append(
                f"- MID-DELVE COVENANT: Beaten to the brink, {patron_name} yields its true sigil to {actor} in exchange for sparing its core—forfeiting the standard extermination payout to seal a living Entity Contract."
            )
        elif etype == "exorcism_spawned":
            lines.append(
                f"- MANIFESTATION EXORCISM: Rejecting peaceful release, {patron_name} materializes across the room to test {actor} in a binding severance duel!"
            )
        elif etype == "exorcism_victory":
            lines.append(
                f"- CLEAN SEVERANCE: Defeated in ritual combat, {patron_name}'s manifestation dissolves and its contract mark fades cleanly from {actor}."
            )
        elif etype == "vip_exclusive_liberated":
            lines.append(
                f"- EXCLUSIVE CORE LIBERATED: With {actor}'s defeat, {patron_name}'s exclusive covenant core unbinds and drifts free."
            )
        elif etype == "school_civilian_panic":
            lines.append(
                f"- UNMASQUED INVOCATION ON CAMPUS: Unawakened students witnessing {actor}'s overt supernatural pact recoil in shock and commotion—portray startled whispers and witness alarm without numeric game terms."
            )

    if not lines:
        return ""
    return (
        "[ENTITY CONTRACT DIRECTIVE — NARRATE VISCERALLY WITHOUT RAW NUMBERS OR INTERNAL TAGS:]\n"
        + "\n".join(lines)
    )


def collect_pact_sdxl_tags(
    pacts: Optional[Iterable[Dict[str, Any]]],
    *,
    active_cast_patron_id: Optional[str] = None,
    scenario_or_key: Any = None,
) -> List[str]:
    """
    Collects Danbooru/SDXL visual tags for active Entity Contracts:
    - Always includes subtle `active_rest_tags` (respecting `gore` and `furry` scenario overrides).
    - Appends dramatic `cast_tags` when `active_cast_patron_id` matches a Patron invoked this turn.
    """
    if not pacts:
        return []
    if scenario_or_key is not None and not is_entity_contracts_scenario(scenario_or_key):
        return []

    tags: List[str] = []
    cast_pid = str(active_cast_patron_id or "").strip()

    for row in pacts:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "active") != "active":
            continue
        pid = str(row.get("patron_id") or row.get("pact_id") or "").strip()
        if not pid:
            continue
        patron = get_patron_by_id(pid, scenario_or_key=scenario_or_key)
        if not patron:
            continue
        enriched = apply_patron_variant_and_locale(patron, scenario_or_key=scenario_or_key)
        vis = enriched.get("visuals") or {}
        for t in vis.get("active_rest_tags") or vis.get("rest_tags") or []:
            t_clean = _clean_tag_leak_tokens(str(t)).lower()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)
        if cast_pid and pid == cast_pid:
            for ct in vis.get("cast_tags") or []:
                ct_clean = _clean_tag_leak_tokens(str(ct)).lower()
                if ct_clean and ct_clean not in tags:
                    tags.append(ct_clean)
    return tags
