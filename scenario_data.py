from __future__ import annotations
"""
Modular scenario definitions for Hikayat adventures.

Scenarios live in data/scenarios.json and dictate narration tone, world
mechanics, and environmental hazards for a session's lifetime.
"""

import json
import logging
import random
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_SCENARIO = "fantasy"
SCENARIOS_PATH = Path(__file__).resolve().parent / "data" / "scenarios.json"
GENRES_PATH = Path(__file__).resolve().parent / "data" / "genres.json"

_REQUIRED_FIELDS = ("name", "description", "tone_guidelines", "tags")

_scenarios_cache: dict | None = None
_genres_cache: dict | None = None

class ScenarioError(Exception):
    """Raised when scenario data is missing or invalid."""


def load_genres(*, reload: bool = False) -> dict[str, dict]:
    """Load genre and modifier definitions from disk. Cached after first call."""
    global _genres_cache
    if _genres_cache is not None and not reload:
        return _genres_cache

    if not GENRES_PATH.is_file():
        raise ScenarioError(f"Genre file not found: {GENRES_PATH}")

    try:
        raw = json.loads(GENRES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"Invalid JSON in {GENRES_PATH}: {exc}") from exc

    parsed: dict[str, dict] = {}
    if isinstance(raw, dict):
        if "genres" in raw and isinstance(raw["genres"], dict):
            for k, v in raw["genres"].items():
                if not k.startswith("_") and isinstance(v, dict):
                    parsed[k] = v
            for sec_key in ("tone_and_modifiers", "modifiers"):
                if sec_key in raw and isinstance(raw[sec_key], dict):
                    for k, v in raw[sec_key].items():
                        if not k.startswith("_") and isinstance(v, dict):
                            parsed[k] = v
        else:
            for k, v in raw.items():
                if not k.startswith("_") and isinstance(v, dict):
                    parsed[k] = v

    _genres_cache = parsed
    return parsed


def _validate_entry(key: str, entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ScenarioError(f"Scenario '{key}' must be a JSON object.")
    missing = [field for field in _REQUIRED_FIELDS if field not in entry]
    if missing:
        raise ScenarioError(f"Scenario '{key}' is missing required fields: {', '.join(missing)}")
    tags = entry["tags"]
    if not isinstance(tags, list):
        raise ScenarioError(f"Scenario '{key}' must define a tags list.")
    return entry


def load_scenarios(*, reload: bool = False) -> dict[str, dict]:
    """Load and validate all scenarios from disk. Cached after first call."""
    global _scenarios_cache
    if _scenarios_cache is not None and not reload:
        return _scenarios_cache

    if not SCENARIOS_PATH.is_file():
        raise ScenarioError(f"Scenario file not found: {SCENARIOS_PATH}")

    try:
        raw = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"Invalid JSON in {SCENARIOS_PATH}: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ScenarioError("Scenario file must be a non-empty JSON object.")

    scenarios = {}
    for key, entry in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise ScenarioError("Scenario keys must be non-empty strings.")
        scenarios[key.strip()] = _validate_entry(key, entry)

    if DEFAULT_SCENARIO not in scenarios:
        raise ScenarioError(
            f"Default scenario '{DEFAULT_SCENARIO}' is not defined in {SCENARIOS_PATH.name}."
        )

    _scenarios_cache = scenarios
    return scenarios


def scenario_keys() -> list[str]:
    return list(load_scenarios().keys())


TAG_ALIASES = {
    "sci_fi": "space",
    "sci-fi": "space",
    "science_fiction": "space",
    "space_frontier": "space",
    "dark_fantasy": "grimdark",
    "dark-fantasy": "grimdark",
    "isekai_fantasy": "isekai",
    "isekai-fantasy": "isekai",
    "high_school_drama": "high_school",
    "high-school-drama": "high_school",
    "high-school": "high_school",
    "slice-of-life": "slice_of_life",
    "post-apocalypse": "post_apocalypse",
    "nuclear_post_apocalypse": "post_apocalypse",
    "non-combat": "non_combat",
    "noncombat": "non_combat",
    "violent": "gore",
    "violence": "gore",
    "modern": "urban_fantasy",
    "urban-fantasy": "urban_fantasy",
    "urban_fantasy": "urban_fantasy",
    "urban": "urban_fantasy",
    "paranormal": "horror",
    "eldritch": "horror",
}


def resolve_tag_keys(raw_input: str | list[str] | None) -> list[str]:
    """Parses raw tag inputs (e.g. 'fantasy, + High School, + Slice of Life'
    or 'custom_combinator_fantasy_+ high school') into valid tag keys defined in data/genres.json."""
    if not raw_input:
        return [DEFAULT_SCENARIO]

    if isinstance(raw_input, list):
        raw_str = ", ".join(str(item) for item in raw_input)
    else:
        raw_str = str(raw_input)

    import re
    cleaned_str = re.sub(r"\(.*?\)", "", raw_str).lower()
    genres_data = load_genres()
    all_lookup_keys = set(genres_data.keys()) | set(TAG_ALIASES.keys())
    all_sorted_keys = sorted(all_lookup_keys, key=lambda k: len(k), reverse=True)

    claimed_spans: list[tuple[int, int]] = []
    matches: list[tuple[int, str]] = []

    for key in all_sorted_keys:
        patterns = [
            re.escape(key),
            re.escape(key.replace("_", " ")),
            re.escape(key.replace("_", "-"))
        ]
        for pat in patterns:
            # First look for word-bounded matches
            for m in re.finditer(r"(?:^|[\s,_\-+])(" + pat + r")(?:$|[\s,_\-+])", cleaned_str):
                start, end = m.start(1), m.end(1)
                if not any(cs <= start < ce or cs < end <= ce or (start <= cs and ce <= end) for cs, ce in claimed_spans):
                    canonical_key = TAG_ALIASES.get(key, key)
                    if canonical_key in genres_data:
                        claimed_spans.append((start, end))
                        matches.append((start, canonical_key))
            # Also search direct pattern matches
            for m in re.finditer(pat, cleaned_str):
                start, end = m.start(), m.end()
                if not any(cs <= start < ce or cs < end <= ce or (start <= cs and ce <= end) for cs, ce in claimed_spans):
                    canonical_key = TAG_ALIASES.get(key, key)
                    if canonical_key in genres_data:
                        claimed_spans.append((start, end))
                        matches.append((start, canonical_key))

    matches.sort(key=lambda x: x[0])
    resolved = []
    for _, key in matches:
        if key not in resolved:
            resolved.append(key)

    return resolved if resolved else [DEFAULT_SCENARIO]


def find_matching_preset_scenario(tag_keys: list[str]) -> str | None:
    """If the given set of tag keys exactly matches a preset scenario's tags, return the preset scenario key."""
    scenarios = load_scenarios()
    target_set = set(tag_keys)
    if not target_set:
        return None

    for key, scen in scenarios.items():
        if key.startswith("custom_combinator_"):
            continue
        scen_tags = set(scen.get("tags") or [])
        if scen_tags == target_set:
            return key

    return None


def resolve_scenario_or_custom_key(raw_input: str | list[str] | None) -> str:
    """Resolves tag input to a preset scenario key if tags match an existing scenario, otherwise returns a custom_combinator key."""
    valid_tags = resolve_tag_keys(raw_input)
    preset_key = find_matching_preset_scenario(valid_tags)
    if preset_key:
        return preset_key

    custom_key = "custom_combinator_" + "_".join(valid_tags)
    scenarios = load_scenarios()
    if custom_key not in scenarios:
        scenarios[custom_key] = build_custom_scenario(valid_tags, f"Custom ({', '.join(valid_tags)})")
    return custom_key


COMMON_SCENARIO_ALIASES = {
    "scifi": "sci_fi",
    "space": "sci_fi",
    "school": "high_school_drama",
    "highschool": "high_school_drama",
    "high_school": "high_school_drama",
    "academy": "magical_academy",
    "furry_school": "nsfw_furry_high_school_drama",
    "furry_high_school": "nsfw_furry_high_school_drama",
    "postapoc": "nuclear_post_apocalypse",
    "post_apoc": "nuclear_post_apocalypse",
    "post_apocalypse": "nuclear_post_apocalypse",
    "darkfantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "anomalies": "anomalous_incursions",
    "anomaly": "anomalous_incursions",
    "anomalous": "anomalous_incursions",
    "incursions": "anomalous_incursions",
    "incursion": "anomalous_incursions",
    "urban_anomalies": "anomalous_incursions",
    "mcb": "anomalous_incursions",
    "scp": "anomalous_incursions",
    "control": "anomalous_incursions",
}


def resolve_scenario_key(key: str | None) -> str:
    """Return a valid scenario key, falling back to DEFAULT_SCENARIO or dynamically building custom combinators."""
    if not key:
        return DEFAULT_SCENARIO
    clean_k = str(key).strip().lower()
    if clean_k in COMMON_SCENARIO_ALIASES:
        key = COMMON_SCENARIO_ALIASES[clean_k]
    scenarios = load_scenarios()
    if key in scenarios:
        return key
    if key.startswith("custom_combinator_"):
        raw_tags_part = key[len("custom_combinator_"):]
        valid_tags = resolve_tag_keys(raw_tags_part)
        preset_key = find_matching_preset_scenario(valid_tags)
        if preset_key:
            return preset_key
        clean_key = "custom_combinator_" + "_".join(valid_tags)
        if clean_key not in scenarios:
            scenarios[clean_key] = build_custom_scenario(valid_tags, f"Custom ({', '.join(valid_tags)})")
        return clean_key

    tag_preset = find_matching_preset_scenario([key])
    if tag_preset:
        return tag_preset

    for s_k, s_val in scenarios.items():
        if key in (s_val.get("tags") or []):
            return s_k

    log.warning("Unknown scenario '%s'; falling back to '%s'.", key, DEFAULT_SCENARIO)
    return DEFAULT_SCENARIO


def get_scenario(key: str | None) -> dict:
    """Return the scenario dict for `key`, or the default scenario."""
    scenarios = load_scenarios()
    return scenarios[resolve_scenario_key(key)]


def get_scenario_tags(scenario_or_key: dict | str | None) -> list[str]:
    if scenario_or_key is None:
        return []
    if isinstance(scenario_or_key, dict):
        scen = scenario_or_key
    else:
        try:
            scen = get_scenario(scenario_or_key)
        except Exception:
            return []
    return scen.get("tags") or []


def has_tag(scenario_or_key: dict | str | None, tag_name: str) -> bool:
    tags = get_scenario_tags(scenario_or_key)
    return tag_name in tags


def get_base_scenario_key(key: str | None) -> str:
    """Return the base_scenario key or matching tag key for fallback data lookups."""
    scen = get_scenario(key)
    if scen.get("base_scenario") and scen["base_scenario"] in load_scenarios():
        return scen["base_scenario"]
    tags = scen.get("tags") or []
    scenarios = load_scenarios()
    for tag in tags:
        if tag in scenarios:
            return tag
    return resolve_scenario_key(key)


def is_mechanic_enabled(scenario_or_key: dict | str | None, mechanic_name: str) -> bool:
    """Return True if `mechanic_name` is present in the scenario's genre allowed_mechanics list."""
    if mechanic_name == "tactical_combat" and (has_tag(scenario_or_key, "non_combat") or has_tag(scenario_or_key, "non-combat")):
        return False
    genres_data = load_genres()
    tags = get_scenario_tags(scenario_or_key)
    allowed = []
    for tag in tags:
        tag_data = genres_data.get(tag, {})
        if tag_data.get("category") == "genre":
            allowed.extend(tag_data.get("allowed_mechanics", []))
    return mechanic_name in set(allowed)


def is_nsfw_scenario(scenario_or_key: dict | str | None) -> bool:
    """Return True if the scenario is tagged as NSFW.

    Accepts either a scenario dict (as returned by get_scenario) or a scenario
    key string.  Returns False for unknown or None keys so callers never need
    to guard against exceptions.
    """
    return has_tag(scenario_or_key, "nsfw")


def is_gore_scenario(scenario_or_key: dict | str | None) -> bool:
    """Return True if the scenario is tagged with gore."""
    return has_tag(scenario_or_key, "gore")


def uses_nsfw_model(scenario_or_key: dict | str | None) -> bool:
    """Return True if LLM calls for this scenario should route to the NSFW/uncensored model chain."""
    return has_tag(scenario_or_key, "nsfw") or has_tag(scenario_or_key, "gore")


def is_non_combat_scenario(scenario_or_key: dict | str | None) -> bool:
    """Return True if the scenario is tagged as non_combat or has tactical_combat disabled."""
    if has_tag(scenario_or_key, "non_combat") or has_tag(scenario_or_key, "non-combat"):
        return True
    return not is_mechanic_enabled(scenario_or_key, "tactical_combat")


def is_combat_enabled(scenario_or_key: dict | str | None) -> bool:
    """Return True if tactical combat and combat attributes are active for this scenario."""
    return not is_non_combat_scenario(scenario_or_key)


def build_custom_scenario(tag_keys: list[str] | str, title: str = "") -> dict:
    valid_tags = resolve_tag_keys(tag_keys)
    genres_data = load_genres()
    tag_labels = [genres_data.get(t, {}).get("name", t.replace("_", " ").title()) for t in valid_tags]
    clean_display = f"Custom: {' • '.join(tag_labels)}" if tag_labels else "Custom Scenario"
    return {
        "name": title or clean_display,
        "display_name": clean_display,
        "emoji": "✨",
        "dropdown_label": clean_display,
        "tags": valid_tags,
        "description": "A custom adventure synthesized from multiple genres.",
        "tone_guidelines": "Blend the themes, aesthetics, and tones of the active tags into a cohesive narrative. Keep the setting consistent based on the primary genre elements selected."
    }


def get_scenario_display_name(scenario_or_key: dict | str | None) -> str:
    """Returns the human-readable thematic display name for a scenario or custom combinator key."""
    if not scenario_or_key:
        return get_scenario(DEFAULT_SCENARIO).get("display_name", "Realms of Myth & Magic")
    if isinstance(scenario_or_key, dict):
        return scenario_or_key.get("display_name") or scenario_or_key.get("name") or "Realms of Myth & Magic"
    key_str = str(scenario_or_key).strip()
    if key_str.startswith("custom_combinator_"):
        valid_tags = resolve_tag_keys(key_str[len("custom_combinator_"):])
        preset_key = find_matching_preset_scenario(valid_tags)
        if preset_key:
            scen = get_scenario(preset_key)
            return scen.get("display_name") or scen.get("name") or preset_key
        genres_data = load_genres()
        tag_labels = [genres_data.get(t, {}).get("name", t.replace("_", " ").title()) for t in valid_tags]
        return f"Custom: {' • '.join(tag_labels)}" if tag_labels else "Custom Scenario"
    try:
        scen = get_scenario(key_str)
        return scen.get("display_name") or scen.get("name") or key_str
    except Exception:
        return key_str.replace("_", " ").title()


def get_scenario_dropdown_label(scenario_or_key: dict | str | None) -> str:
    """Returns the dropdown label with genre/modifier hints (e.g., 'Realms of Myth & Magic [Fantasy]')."""
    if isinstance(scenario_or_key, dict):
        scen = scenario_or_key
    else:
        scen = get_scenario(scenario_or_key)
    if scen.get("dropdown_label"):
        return scen["dropdown_label"]
    display = scen.get("display_name") or scen.get("name") or "Adventure"
    genres_data = load_genres()
    tags = [t for t in (scen.get("tags") or []) if t != "non_combat"]
    tag_labels = [genres_data.get(t, {}).get("name", t.replace("_", " ").title()) for t in tags]
    if tag_labels and not display.startswith("Custom:"):
        return f"{display} [{' • '.join(tag_labels)}]"
    return display


def scenario_prompt_block(scenario: dict | str | None) -> str:
    """Format scenario data for injection into LLM user prompts."""
    if not isinstance(scenario, dict):
        scenario = get_scenario(scenario)

    tags_str = f" [Tags: {', '.join(scenario.get('tags', []))}]" if scenario.get("tags") else ""
    
    genres_data = load_genres()
    tags = scenario.get("tags", [])
    
    instructions = []
    active_mechanics = []
    for tag in tags:
        tag_data = genres_data.get(tag, {})
        instructions.extend(tag_data.get("prompt_instructions", []))
        if tag_data.get("category") == "genre":
            active_mechanics.extend(tag_data.get("allowed_mechanics", []))
        
    # Deduplicate mechanics and strip tactical_combat when non_combat modifier is active
    active_mechanics = list(dict.fromkeys(active_mechanics))
    if "non_combat" in tags or "non-combat" in tags:
        active_mechanics = [m for m in active_mechanics if m != "tactical_combat"]
    
    instructions_text = "\n".join(f"- {inst}" for inst in instructions) if instructions else "- None"
    mechanics_text = ", ".join(active_mechanics) or "none"
    return (
        f"ACTIVE SCENARIO: {scenario['name']}{tags_str}\n"
        f"World: {scenario['description']}\n"
        f"Tone: {scenario['tone_guidelines']}\n"
        f"Active Code Mechanics: {mechanics_text}\n"
        f"Special GM Instructions:\n{instructions_text}\n"
        f"Stay within this genre's technology, vocabulary, and threats — "
        f"do not drift into unrelated settings."
    )


def get_genre_tags() -> tuple[str, ...]:
    return tuple(k for k, v in load_genres().items() if v.get("category") == "genre")


def get_setting_tags() -> tuple[str, ...]:
    return get_genre_tags()


def get_modifier_tags() -> tuple[str, ...]:
    return tuple(k for k, v in load_genres().items() if v.get("category") == "modifier")


PRIMARY_SETTING_TAGS = get_genre_tags()

MODIFIER_TAGS = get_modifier_tags()

STARTING_ARCHETYPES = ("hub_launchpad", "in_media_res", "delve_threshold")


def get_dynamic_starting_hook(scenario: dict | str | None, session_id: int = 0, char_name: str = "") -> dict:
    """Selects a map-anchored starting hook from active scenario or genre tags and randomly chooses one of 3 Starting Archetypes:
    - hub_launchpad: Open Hub Exploration (Social / Investigative / Notice Board / Present NPCs)
    - in_media_res: High-Tension Crisis (Combat / Ambush / Alarms / Tactical Survival)
    - delve_threshold: Frontier / Ruin Threshold (Expedition / Scouting / Multi-Chamber Delves)
    
    Guarantees that the starting location is anchored directly to a seeded location on the world map.
    Returns a dict with archetype, hook_text, suggested_location, and directive.
    """
    if isinstance(scenario, dict):
        scen_dict = scenario
        scen_key = scen_dict.get("key") or scen_dict.get("scenario") or ""
        if not scen_key:
            scenarios = load_scenarios()
            for k, v in scenarios.items():
                if v.get("name") == scen_dict.get("name") or (scen_dict.get("tags") and v.get("tags") == scen_dict.get("tags")):
                    scen_key = k
                    break
        if not scen_key:
            scen_key = resolve_scenario_key(scen_dict.get("tags", [DEFAULT_SCENARIO])[0] if scen_dict.get("tags") else DEFAULT_SCENARIO)
    else:
        scen_dict = get_scenario(scenario)
        scen_key = resolve_scenario_key(scenario)

    tags = scen_dict.get("tags", [])
    genres_data = load_genres()
    
    # Collect hooks by archetype: prefer scenario-specific starting_hooks if defined (e.g. dark_fantasy), otherwise pool from genre tags
    archetype_pools = {"hub_launchpad": [], "in_media_res": [], "delve_threshold": []}
    
    scen_hooks = scen_dict.get("starting_hooks", [])
    if scen_hooks:
        for h in scen_hooks:
            if isinstance(h, dict):
                arch = h.get("archetype", "hub_launchpad")
                if arch in archetype_pools:
                    archetype_pools[arch].append(h)
                else:
                    archetype_pools["hub_launchpad"].append(h)
            elif isinstance(h, str):
                archetype_pools["hub_launchpad"].append({
                    "archetype": "hub_launchpad",
                    "hook": h,
                    "suggested_location": "",
                    "directive": ""
                })
    else:
        # Prioritize primary genre tags so modifier tags (grimdark, furry, nsfw, non_combat) do not override the setting environment
        candidate_tags = [t for t in tags if t in PRIMARY_SETTING_TAGS]
        if not candidate_tags:
            candidate_tags = [t for t in tags if t not in MODIFIER_TAGS] or tags

        for tag in candidate_tags:
            tag_data = genres_data.get(tag, {})
            hooks = tag_data.get("starting_hooks", [])
            for h in hooks:
                if isinstance(h, dict):
                    arch = h.get("archetype", "hub_launchpad")
                    if arch in archetype_pools:
                        archetype_pools[arch].append(h)
                    else:
                        archetype_pools["hub_launchpad"].append(h)
                elif isinstance(h, str):
                    archetype_pools["hub_launchpad"].append({
                        "archetype": "hub_launchpad",
                        "hook": h,
                        "suggested_location": "",
                        "directive": ""
                    })
                
    available_archetypes = [arch for arch, pool in archetype_pools.items() if pool]
    
    from mechanics.world.locations import get_archetype_starting_location, resolve_session_location_tokens

    if not available_archetypes:
        chosen_archetype = "hub_launchpad"
        z, p, s = get_archetype_starting_location(
            session_id=session_id,
            scenario_key=scen_key,
            archetype=chosen_archetype,
            char_name=char_name
        )
        resolved_location = f"{z} ➔ {p} ➔ {s}"
        fallback_hook = scen_dict.get("starting_environment", f"in {p} as you begin your adventure")
        return {
            "archetype": chosen_archetype,
            "hook_text": f"Begin {fallback_hook}.",
            "suggested_location": resolved_location,
            "directive": "Open Hub Exploration: Establish ambient surroundings, present NPCs, and open choices.",
            "starting_minute": 480,
            "focal_point": s or p,
            "scheduled_roles": [],
            "initial_physical_state": {},
            "starting_prop": None,
            "visual_cues": "",
        }
        
    chosen_archetype = random.choice(available_archetypes)
    chosen_entry = random.choice(archetype_pools[chosen_archetype])
    
    # Resolve guaranteed-valid map location from session's seeded map
    loc_hint = chosen_entry.get("suggested_location", "") or chosen_entry.get("location_hint", "")
    if loc_hint:
        loc_hint = resolve_session_location_tokens(session_id=session_id, template=loc_hint, scenario_key=scen_key, char_name=char_name)
    z, p, s = get_archetype_starting_location(
        session_id=session_id,
        scenario_key=scen_key,
        archetype=chosen_archetype,
        char_name=char_name,
        preferred_hint=loc_hint
    )
    resolved_location = f"{z} ➔ {p} ➔ {s}"
    
    hook_str = chosen_entry.get("hook", "")
    hook_str = hook_str.replace("{starting_zone}", z).replace("{starting_primary}", p).replace("{starting_sub}", s).replace("{starting_location}", resolved_location)
    hook_str = resolve_session_location_tokens(session_id=session_id, template=hook_str, scenario_key=scen_key, char_name=char_name)

    if not hook_str.lower().startswith("begin"):
        hook_text = f"Begin {hook_str}."
    else:
        hook_text = hook_str
        
    directive = chosen_entry.get("directive", "")
    if not directive:
        if chosen_archetype == "hub_launchpad":
            directive = "Open Hub Exploration: Establish ambient atmosphere, 2-3 present NPCs with motives, and open choices (talking to NPCs, inspecting notices, free roleplay actions, moving outside)."
        elif chosen_archetype == "in_media_res":
            directive = "In Media Res: Stage an immediate high-stakes crisis (weapons drawn, alarms blaring, ticking clock) with urgent tactical choices."
        else:
            directive = "Delve Threshold: Stage the mystery of the ancient frontier/ruin threshold, survival/scouting choices, deciphering clues, and preparing equipment."

    starting_min = chosen_entry.get("starting_minute")
    if starting_min is not None:
        try:
            starting_min = int(starting_min)
        except Exception:
            starting_min = None

    focal_point_str = chosen_entry.get("focal_point", "")
    if focal_point_str:
        focal_point_str = focal_point_str.replace("{starting_zone}", z).replace("{starting_primary}", p).replace("{starting_sub}", s).replace("{starting_location}", resolved_location)
        focal_point_str = resolve_session_location_tokens(session_id=session_id, template=focal_point_str, scenario_key=scen_key, char_name=char_name)
    else:
        focal_point_str = s or p

    scheduled_roles = chosen_entry.get("scheduled_roles", [])
    if isinstance(scheduled_roles, str):
        scheduled_roles = [scheduled_roles]
    elif not isinstance(scheduled_roles, list):
        scheduled_roles = []

    initial_physical_state = chosen_entry.get("initial_physical_state") or {}
    if not isinstance(initial_physical_state, dict):
        initial_physical_state = {}

    starting_prop = chosen_entry.get("starting_prop")
    if isinstance(starting_prop, str):
        starting_prop = {"name": starting_prop, "item_type": "tool", "effect": ""}
    elif not isinstance(starting_prop, dict):
        starting_prop = None

    visual_cues = chosen_entry.get("visual_cues", "")

    return {
        "archetype": chosen_archetype,
        "hook_text": hook_text,
        "suggested_location": resolved_location,
        "directive": directive,
        "starting_minute": starting_min,
        "focal_point": focal_point_str,
        "scheduled_roles": scheduled_roles,
        "initial_physical_state": initial_physical_state,
        "starting_prop": starting_prop,
        "visual_cues": visual_cues,
    }


def get_dynamic_starting_environment(scenario: dict | str | None, session_id: int = 0, char_name: str = "") -> str:
    hook_info = get_dynamic_starting_hook(scenario, session_id=session_id, char_name=char_name)
    return hook_info["hook_text"]


def opening_environment_note(scenario: dict | str | None, session_id: int = 0, char_name: str = "") -> str:
    hook_info = get_dynamic_starting_hook(scenario, session_id=session_id, char_name=char_name)
    arch_label = hook_info["archetype"].replace("_", " ").title()
    loc_note = f" (Suggested Location: {hook_info['suggested_location']})" if hook_info["suggested_location"] else ""
    return f"OPENING ENVIRONMENT [{arch_label}]: {hook_info['hook_text']}{loc_note}\nARCHETYPE DIRECTIVE: {hook_info['directive']}"



ANOMALOUS_INCURSIONS_SCENARIO_KEYS = frozenset({
    "anomalous_incursions",
    "nsfw_gore_anomalous_incursions",
    "furry_anomalous_incursions",
    "nsfw_furry_gore_anomalous_incursions",
    "urban_anomalies",
})


def is_anomalous_incursions_scenario(scenario_or_key: dict | str | None) -> bool:
    """Return True strictly if the scenario is one of the 4 Anomalous Incursions preset scenarios
    (or legacy alias 'urban_anomalies'), keeping generic custom 'urban_fantasy' scenarios separate."""
    if not scenario_or_key:
        return False
    if isinstance(scenario_or_key, dict):
        k = str(scenario_or_key.get("key") or scenario_or_key.get("scenario") or "").strip().lower()
        base = str(scenario_or_key.get("base_scenario") or "").strip().lower()
        name = str(scenario_or_key.get("name") or "").strip().lower()
        if k in ANOMALOUS_INCURSIONS_SCENARIO_KEYS or base in ANOMALOUS_INCURSIONS_SCENARIO_KEYS:
            return True
        return "anomalous incursions" in name
    s = str(scenario_or_key).strip().lower()
    if s in ANOMALOUS_INCURSIONS_SCENARIO_KEYS:
        return True
    if s.startswith("custom"):
        return False
    resolved = resolve_scenario_key(s)
    if resolved in ANOMALOUS_INCURSIONS_SCENARIO_KEYS:
        return True
    try:
        scen = get_scenario(s)
        return str(scen.get("base_scenario") or "").strip().lower() in ANOMALOUS_INCURSIONS_SCENARIO_KEYS
    except Exception:
        return False


def get_max_campaign_chapters(scenario_or_key: dict | str | None) -> int:
    """Returns 11 for Anomalous Incursions (10 story chapters + Chapter 11 Resolution/Epilogue), and 10 for others."""
    if is_anomalous_incursions_scenario(scenario_or_key):
        return 11
    return 10
