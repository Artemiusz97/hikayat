from __future__ import annotations
"""
mechanics/world_forge/seeder.py
World Forge Pre-Seeder: deterministic diplomatic matrix + lightweight LLM Pass 0.

Execution flow (called from cogs/adventure/cog.py::launch_opening_scene):
  1. seed_diplomatic_matrix()   — pure Python, < 5ms, no LLM calls
  2. generate_macro_world_state() — fast utility LLM call, ~1–2 s, with graceful fallback
  3. forge_world_state()          — orchestrates both steps; called at adventure start
"""


import json
import logging
from typing import TYPE_CHECKING

import db
import scenario_data

log = logging.getLogger("hikayat.world_forge")

# ---------------------------------------------------------------------------
# Diplomatic Matrix Templates
# Maps (category_a, category_b) -> relationship: "rival" | "ally" | "neutral"
# Order of keys does not matter; both orderings are checked.
# ---------------------------------------------------------------------------
_DIPLOMACY_MATRIX: dict[frozenset, str] = {
    # Fantasy / Dark Fantasy
    frozenset({"guild", "order"}):        "ally",
    frozenset({"order", "delinquents"}):  "rival",
    frozenset({"guild", "delinquents"}):  "rival",
    frozenset({"guild", "guild"}):        "rival",    # competing guilds
    frozenset({"order", "order"}):        "neutral",  # rival orders — cautious

    # Cyberpunk
    frozenset({"corpo", "syndicate"}):    "rival",
    frozenset({"corpo", "corpo"}):        "rival",
    frozenset({"syndicate", "delinquents"}): "ally",

    # Steampunk
    frozenset({"guild", "syndicate"}):    "rival",
    frozenset({"syndicate", "delinquents"}): "ally",

    # Post-Apocalypse
    frozenset({"settlement", "delinquents"}): "rival",
    frozenset({"settlement", "guild"}):    "ally",
    frozenset({"guild", "delinquents"}):   "rival",

    # Sci-Fi / Space
    frozenset({"corpo", "delinquents"}):  "rival",

    # School / Slice-of-Life
    frozenset({"council", "delinquents"}): "rival",
    frozenset({"council", "club"}):        "ally",
    frozenset({"club", "delinquents"}):    "rival",
    frozenset({"sports", "council"}):      "ally",
    frozenset({"sports", "delinquents"}):  "rival",
    frozenset({"sports", "club"}):         "neutral",
}

# How large a fraction of the primary delta to apply as a ripple
_RIVAL_RIPPLE_FRACTION   = 0.30   # gain 10 with A → lose 3 with rival
_ALLY_RIPPLE_FRACTION    = 0.30   # gain 10 with A → gain 3 with ally


def _infer_relationship(cat_a: str, cat_b: str, name_a: str, name_b: str) -> str:
    """Return 'rival', 'ally', or 'neutral' for two faction categories."""
    key = frozenset({cat_a, cat_b})
    rel = _DIPLOMACY_MATRIX.get(key)
    if rel:
        return rel
    # Same category fallback: competing factions of the same type are rivals
    if cat_a == cat_b:
        return "rival"
    return "neutral"


# ---------------------------------------------------------------------------
# Step 1 — Deterministic Diplomatic Matrix (no LLM)
# ---------------------------------------------------------------------------
def seed_diplomatic_matrix(session_id: int, scen_key: str) -> None:
    """
    Assigns symmetric ally / rival relationships between all starter factions
    and persists them to SQLite. Pure Python, < 5 ms.
    """
    factions = db.get_factions(session_id)
    if not factions:
        return

    # Build lookup: faction_id → faction row
    fac_map = {f["faction_id"]: f for f in factions}

    for fac in factions:
        rivals: list[str] = []
        allies: list[str] = []

        cat_a = str(fac.get("category") or fac.get("hierarchy_template") or "guild")
        fid_a = fac["faction_id"]

        for other in factions:
            fid_b = other["faction_id"]
            if fid_b == fid_a:
                continue
            cat_b = str(other.get("category") or other.get("hierarchy_template") or "guild")
            rel = _infer_relationship(cat_a, cat_b, fac.get("name", ""), other.get("name", ""))
            if rel == "rival":
                rivals.append(fid_b)
            elif rel == "ally":
                allies.append(fid_b)

        # Persist only if relations changed (avoid needless writes)
        existing_rivals = fac.get("rival_faction_ids") or []
        existing_allies = fac.get("allied_faction_ids") or []
        if set(rivals) != set(existing_rivals) or set(allies) != set(existing_allies):
            db.upsert_faction(
                session_id=session_id,
                name=fac["name"],
                delta_score=0,
                rival_faction_ids=rivals,
                allied_faction_ids=allies,
            )

    log.info("[WorldForge] Diplomatic matrix seeded for session %s (%d factions)", session_id, len(factions))


# ---------------------------------------------------------------------------
# Step 2 — Lightweight LLM Pass 0 (macro-conflict flavor)
# ---------------------------------------------------------------------------
_WORLD_FORGE_SCHEMA = """{
  "macro_conflict": "string — 1-sentence description of the dominant geopolitical tension between the major factions",
  "world_rumor": "string — 1 vivid street-level rumor circulating in the world right now",
  "active_flashpoint": "string — the specific location or event where the tension is currently erupting"
}"""


async def generate_macro_world_state(session_id: int, session: dict, party: list) -> dict | None:
    """
    Fast LLM utility Pass 0: generates a bespoke macro-conflict tailored to the
    player's character and the seeded factions. Stores result in lorebook.
    Returns the generated dict, or None on failure (graceful fallback).
    """
    import game_engine
    from scenario_data import is_nsfw_scenario

    factions = db.get_factions(session_id)
    if not factions:
        return None

    scen_key = session.get("scenario", "fantasy")

    # Build a compact faction summary including allies/rivals for Pass 0 context
    faction_summaries = []
    fac_map = {f["faction_id"]: f.get("name", f["faction_id"]) for f in factions}
    for f in factions:
        rivals_named = [fac_map.get(r, r) for r in (f.get("rival_faction_ids") or [])]
        allies_named = [fac_map.get(a, a) for a in (f.get("allied_faction_ids") or [])]
        line = f"- {f['name']} ({f.get('category', 'guild')})"
        if rivals_named:
            line += f" | Rivals: {', '.join(rivals_named)}"
        if allies_named:
            line += f" | Allies: {', '.join(allies_named)}"
        faction_summaries.append(line)

    char_name = ""
    char_class = ""
    if party and party[0]:
        char_obj = party[0][0] if isinstance(party[0], (list, tuple)) else party[0]
        if isinstance(char_obj, dict):
            char_name = char_obj.get("name", "")
            char_class = char_obj.get("char_class", "")

    system_prompt = (
        "You are the World Architect for a narrative RPG engine. Your task is to craft a brief "
        "macro-world state entry grounding the adventure's geopolitical backdrop. "
        "Be specific, thematic, and match the scenario genre. Output ONLY valid JSON."
    )
    user_prompt = (
        f"SCENARIO: {scen_key}\n"
        f"PLAYER CHARACTER: {char_name} the {char_class}\n\n"
        f"KNOWN FACTIONS AND THEIR DIPLOMATIC RELATIONS:\n"
        + "\n".join(faction_summaries)
        + f"\n\nGenerate the macro world state. Tie the tension directly to the factions listed above. "
        f"Respond with JSON matching this schema:\n{_WORLD_FORGE_SCHEMA}"
    )

    try:
        result = await game_engine.call_llm_json(
            system_prompt,
            user_prompt,
            temperature=0.7,
            max_tokens=256,
            retries=1,
            is_nsfw=is_nsfw_scenario(scen_key),
            use_utility=True,
            timeout=15.0,
        )
        if isinstance(result, dict) and result.get("macro_conflict"):
            _persist_macro_world(session_id, result)
            return result
    except Exception as e:
        log.warning("[WorldForge] LLM Pass 0 failed (%s). Falling back to procedural macro-conflict.", e)

    # Graceful fallback: deterministic placeholder from faction notes
    fallback = _build_fallback_macro(factions, scen_key)
    _persist_macro_world(session_id, fallback)
    return fallback


def _build_fallback_macro(factions: list[dict], scen_key: str) -> dict:
    """Build a purely procedural macro-conflict when the LLM is unavailable."""
    if not factions:
        return {
            "macro_conflict": "An uneasy political tension grips the region.",
            "world_rumor": "Travelers speak of strange movements along the roads.",
            "active_flashpoint": "The heart of the regional capital",
        }

    # Find a rival pair to base the conflict on
    fac_map = {f["faction_id"]: f.get("name", f["faction_id"]) for f in factions}
    conflict_pair: tuple[str, str] | None = None
    for f in factions:
        rivals = f.get("rival_faction_ids") or []
        if rivals:
            rival_name = fac_map.get(rivals[0], rivals[0])
            conflict_pair = (f["name"], rival_name)
            break

    if conflict_pair:
        a, b = conflict_pair
        macro = f"A bitter power struggle between {a} and {b} threatens to fracture the region's stability."
        rumor = f"Word on the street is that {a} is making moves against {b}'s influence."
        hq = next((f.get("hq_location_id", "") for f in factions if f.get("name") == a), "")
        flashpoint = hq or "The contested border between rival territories"
    else:
        macro = f"Political tension among the major powers of the region simmers beneath the surface."
        rumor = "Merchants whisper of secret meetings and shifting alliances."
        flashpoint = factions[0].get("hq_location_id", "") or "The central market district"

    return {"macro_conflict": macro, "world_rumor": rumor, "active_flashpoint": flashpoint}


def _persist_macro_world(session_id: int, data: dict) -> None:
    """Save the macro-world state as a lorebook entry of type 'world_lore'."""
    macro = str(data.get("macro_conflict", "")).strip()
    rumor = str(data.get("world_rumor", "")).strip()
    flashpoint = str(data.get("active_flashpoint", "")).strip()
    if not macro:
        return

    full_desc = macro
    if rumor:
        full_desc += f" | CURRENT RUMOR: {rumor}"
    if flashpoint:
        full_desc += f" | FLASHPOINT: {flashpoint}"

    db.upsert_lorebook_entity(
        session_id=session_id,
        entity_type="world_lore",
        name="_macro_world_state",
        description=full_desc,
        disposition="neutral",
    )
    log.info("[WorldForge] Macro-world state persisted for session %s", session_id)


# ---------------------------------------------------------------------------
# Public Orchestrator — called from launch_opening_scene
# ---------------------------------------------------------------------------
async def forge_world_state(session: dict, party: list) -> None:
    """
    Entry point. Orchestrates:
      1. Deterministic diplomatic matrix seeding (< 5 ms)
      2. Lightweight LLM Pass 0 for macro-conflict flavor (~1–2 s)

    Called after ensure_session_factions_seeded() and before generate_opening_scene().
    All failures are swallowed gracefully so the adventure launch is never blocked.
    """
    session_id = session.get("id")
    scen_key   = session.get("scenario", "fantasy")

    if not scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
        log.debug("[WorldForge] faction_reputation disabled for scenario %s — skipping.", scen_key)
        return

    try:
        # Step 1 — Deterministic Python (no await needed)
        seed_diplomatic_matrix(session_id, scen_key)
    except Exception as e:
        log.error("[WorldForge] seed_diplomatic_matrix failed: %s", e, exc_info=True)

    try:
        # Step 2 — LLM Pass 0 (fast utility call)
        await generate_macro_world_state(session_id, session, party)
    except Exception as e:
        log.error("[WorldForge] generate_macro_world_state failed: %s", e, exc_info=True)
