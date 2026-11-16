from __future__ import annotations
"""
Canonical wardrobe preset identifiers, time windows, and pure spatial/venue
predicates for Hikayat's Dynamic NPC Wardrobe System.
"""

import json
from typing import Any

from mechanics.world.world_schedule import is_weekend

# ---------------------------------------------------------------------------
# Core Personal Presets & Contextual Activity Kits / Outerwear Overlays
# ---------------------------------------------------------------------------
PRESET_DUTY = "duty"
PRESET_CASUAL = "casual"
PRESET_SLEEPWEAR = "sleepwear"

CORE_WARDROBE_PRESETS: tuple[str, ...] = (
    PRESET_DUTY,
    PRESET_CASUAL,
    PRESET_SLEEPWEAR,
)

KIT_SPORT = "activity:sport"
KIT_SWIM = "activity:swim"
KIT_BATH = "activity:bath"
KIT_DOJO = "activity:dojo"
KIT_TACTICAL = "activity:tactical"
KIT_SECRET_FACTION = "activity:secret_faction"

ACTIVITY_KITS: tuple[str, ...] = (
    KIT_SPORT,
    KIT_SWIM,
    KIT_BATH,
    KIT_DOJO,
    KIT_TACTICAL,
    KIT_SECRET_FACTION,
)

OVERLAY_APRON = "overlay:apron"
OVERLAY_LAB_COAT = "overlay:lab_coat"
OVERLAY_MODESTY_ROBE = "overlay:modesty_robe"

# ---------------------------------------------------------------------------
# Canonical Clock Thresholds (Minutes Since Midnight: 0..1439)
# ---------------------------------------------------------------------------
AFTER_SCHOOL_UNIFORM_END_MIN = 1050   # 17:30 weekday off-screen casual cutoff
SCHOOL_ARRIVAL_MIN = 420              # 07:00 school arrival / Wednesday Sport Day start
SLEEPWEAR_START_MIN = 1320            # 22:00 standard bedtime start
WEEKDAY_WAKE_MIN = 420                # 07:00 weekday wake
WEEKEND_WAKE_MIN = 510                # 08:30 weekend / rest-day wake
TIME_SKIP_FREEZE_BREAK_MIN = 30       # >= 30m Time Skip at Change Point breaks freeze
RENDEZVOUS_PREP_BUFFER_MIN = 30       # >= 30m pre-date gap lets NPC change into casual

# ---------------------------------------------------------------------------
# Genre & Scenario Family Classification
# ---------------------------------------------------------------------------


def is_school_context_scenario(scen_key: str = "") -> bool:
    """True when scenario includes school/academy mechanics."""
    try:
        import scenario_data
        return bool(scenario_data.has_school_campus_mechanics(scen_key))
    except Exception:
        low = str(scen_key or "").strip().lower()
        return any(k in low for k in ("school", "academy", "high_school"))


def resolve_wardrobe_genre_family(scen_key: str = "") -> str:
    """Maps any Hikayat scenario key to its canonical wardrobe genre pool."""
    raw = str(scen_key or "fantasy").strip().lower()
    try:
        import scenario_data
        if scenario_data.is_anomalous_high_school_scenario(raw):
            return "anomalous_high"
        if scenario_data.is_anomalous_incursions_scenario(raw):
            return "anomalous_incursions"
        if scenario_data.has_school_campus_mechanics(raw) or scenario_data.is_high_school_scenario(raw):
            return "high_school"
        if scenario_data.has_tag(raw, "cyberpunk"):
            return "cyberpunk"
        if scenario_data.has_tag(raw, "space") or scenario_data.has_tag(raw, "sci_fi"):
            return "sci_fi"
        if scenario_data.has_tag(raw, "steampunk"):
            return "steampunk"
        if scenario_data.has_tag(raw, "post_apocalypse") or scenario_data.has_tag(raw, "nuclear_post_apocalypse"):
            return "post_apocalypse"
        if scenario_data.has_tag(raw, "grimdark") or scenario_data.has_tag(raw, "dark_fantasy"):
            return "dark_fantasy"
        if scenario_data.has_tag(raw, "isekai"):
            return "isekai"
        if scenario_data.has_tag(raw, "slice_of_life"):
            return "slice_of_life"
    except Exception:
        pass

    if "anomalous" in raw and ("high" in raw or "school" in raw):
        return "anomalous_high"
    if "anomalous" in raw or "incursion" in raw:
        return "anomalous_incursions"
    if "school" in raw or "academy" in raw:
        return "high_school"
    if "cyber" in raw:
        return "cyberpunk"
    if "sci_fi" in raw or "space" in raw:
        return "sci_fi"
    if "steam" in raw:
        return "steampunk"
    if "apocalyp" in raw or "wasteland" in raw:
        return "post_apocalypse"
    if "dark_fantasy" in raw or "grimdark" in raw:
        return "dark_fantasy"
    if "isekai" in raw:
        return "isekai"
    if "slice" in raw:
        return "slice_of_life"
    return "fantasy"


# ---------------------------------------------------------------------------
# Pure Time Window Helpers
# ---------------------------------------------------------------------------


def is_wednesday_sport_window(
    current_day: int,
    current_minute: int,
    scen_key: str = "high_school_drama",
) -> bool:
    """True on Wednesdays (day % 7 == 3, i.e., (day - 1) % 7 == 2) from 07:00 to 17:29 in school scenarios."""
    if not is_school_context_scenario(scen_key):
        return False
    safe_day = max(1, int(current_day or 1))
    if (safe_day - 1) % 7 != 2:
        return False
    safe_min = int(current_minute if current_minute is not None else 480) % 1440
    return SCHOOL_ARRIVAL_MIN <= safe_min < AFTER_SCHOOL_UNIFORM_END_MIN


def is_sleepwear_window(
    current_day: int,
    current_minute: int,
    *,
    shift_profile: str = "day",
    on_rest_day: bool = False,
) -> bool:
    """Returns True when the clock falls in the actor's circadian sleep window."""
    safe_day = max(1, int(current_day or 1))
    safe_min = int(current_minute if current_minute is not None else 480) % 1440
    prof = str(shift_profile or "day").strip().lower()

    if prof == "night":
        # Night-shift workers sleep 05:00 - 13:59
        return 300 <= safe_min < 840
    if prof == "evening" and not on_rest_day:
        # Evening-shift workers finish at 23:00 -> sleep 23:00 - 08:59
        return safe_min >= 1380 or safe_min < 540

    wake_min = WEEKEND_WAKE_MIN if (on_rest_day or is_weekend(safe_day)) else WEEKDAY_WAKE_MIN
    return safe_min >= SLEEPWEAR_START_MIN or safe_min < wake_min


# ---------------------------------------------------------------------------
# Pure Spatial & Venue Classifiers
# ---------------------------------------------------------------------------
_NON_RESIDENTIAL_HOUSE_WORDS = (
    "clubhouse",
    "bathhouse",
    "boathouse",
    "glasshouse",
    "greenhouse",
    "warehouse",
    "storehouse",
    "courthouse",
    "gatehouse",
    "guardhouse",
    "tea house",
    "teahouse",
    "coffee house",
    "house of ",
)


def _probe_loc(location_str: str = "", node_id: str = "") -> str:
    return f"{node_id or ''} {location_str or ''}".strip().lower()


def _has_false_house_token(probe: str) -> bool:
    return any(tok in probe for tok in _NON_RESIDENTIAL_HOUSE_WORDS)


def is_private_bedroom_sublocation(location_str: str = "", node_id: str = "") -> bool:
    probe = _probe_loc(location_str, node_id)
    return any(
        k in probe
        for k in (
            "bedroom",
            "bedchamber",
            "sleeping quarters",
            "mirrored velvet suite",
            "rooftop jacuzzi suite",
            "love hotel",
            "master suite",
            "sub_player_bedroom",
        )
    )


def is_sleep_venue(
    location_str: str = "",
    node_id: str = "",
    *,
    npc_home_node_id: str = "",
    is_player_safe_res: bool = False,
) -> bool:
    """True when location is a valid residential/inn/sleepover venue for sleepwear."""
    if is_player_safe_res:
        return True
    nid = str(node_id or "").strip()
    home_nid = str(npc_home_node_id or "").strip()
    if home_nid and nid and (nid == home_nid or nid.startswith(f"{home_nid}_") or home_nid in nid):
        return True

    probe = _probe_loc(location_str, node_id)
    if not probe:
        return False
    if any(
        k in probe
        for k in (
            "sub_npc_res_",
            "fac_npc_res_",
            "npc_res_",
            "fac_agency_residence",
            "fac_temple_residence",
            "loc_player_house",
            "sub_player_front_porch",
            "sub_player_living_room",
            "sub_player_bedroom",
            "residence",
            "dormitory",
            "dorm room",
            "private quarters",
            "sleeping quarters",
            "starter quarters",
            "bedroom",
            "bedchamber",
            "apartment",
            "penthouse",
            "safehouse",
            "safe house",
            "inn room",
            "tavern room",
            "guest room",
            "hotel room",
            "love hotel",
            "mirrored velvet suite",
            "rooftop jacuzzi suite",
            "pine cabin",
        )
    ):
        return True
    if ("house" in probe or "home" in probe) and not _has_false_house_token(probe):
        if any(k in probe for k in ("parents' house", "family house", "player's house", "npc's home", "home foyer", "living room", "porch", "at home")):
            return True
    return False


def is_change_point_location(
    location_str: str = "",
    node_id: str = "",
    *,
    npc_home_node_id: str = "",
    is_player_safe_res: bool = False,
    workplace_node_id: str = "",
) -> bool:
    """True at locations where an actor can plausibly change outfits."""
    if is_sleep_venue(
        location_str,
        node_id,
        npc_home_node_id=npc_home_node_id,
        is_player_safe_res=is_player_safe_res,
    ):
        return True
    nid = str(node_id or "").strip()
    wp_nid = str(workplace_node_id or "").strip()
    if wp_nid and nid and (nid == wp_nid or wp_nid in nid):
        if any(k in nid.lower() for k in ("armory", "outfitter", "staff", "locker", "quarters", "barracks")):
            return True
    probe = _probe_loc(location_str, node_id)
    return any(
        k in probe
        for k in (
            "loc_male_shower_room",
            "loc_female_shower_room",
            "locker & shower",
            "locker room",
            "changing room",
            "curtained fitting",
            "fitting room",
            "loc_hq_tactical_armory",
            "loc_hq_field_outfitter",
            "tactical armory",
            "field outfitter",
            "teachers' staff room",
            "staff room",
            "loc_staff_room",
            "barracks",
            "camp",
            "campsite",
            "infirmary",
            "medical bay",
        )
    )


def is_school_campus_location(location_str: str = "", node_id: str = "") -> bool:
    """True for High School campus zones & facilities (excludes town commercial venues)."""
    probe = _probe_loc(location_str, node_id)
    if not probe:
        return False
    if any(k in probe for k in ("commercial", "downtown", "seaside", "arcade", "karaoke", "convenience store", "cafe", "coffee", "station", "city square")):
        if "campus" not in probe and "school" not in probe and "academy" not in probe:
            return False
    return any(
        k in probe
        for k in (
            "zone_school",
            "main academy",
            "academy campus",
            "campus building",
            "campus dining",
            "campus auditorium",
            "school ",
            "school_",
            "homeroom",
            "classroom",
            "loc_homeroom",
            "loc_freshman_class",
            "loc_sophomore_class",
            "loc_junior_class",
            "loc_senior_class",
            "loc_staff_room",
            "teachers' staff room",
            "school library",
            "infirmary",
            "central courtyard",
            "botanical glasshouse",
            "varsity",
            "gymnasium",
            "athletic field",
            "running track",
            "swimming pool",
            "martial arts dojo",
            "student council",
            "abandoned school",
            "velvet basement salon",
            "shoe lockers",
        )
    )


def is_recreational_water_sublocation(location_str: str = "", node_id: str = "") -> bool:
    """True strictly for wet beach/surf/swimming-pool sub-locations (excludes dry Boardwalk/Pier/Shack)."""
    probe = _probe_loc(location_str, node_id)
    if not probe:
        return False
    # Dry coastal venues stay in casual attire
    if any(k in probe for k in ("boardwalk", "pier", "lookout deck", "fishing", "beach shack", "shaved ice", "shaved-ice", "grill bar", "seaside cafe", "seaside_cafe", "promenade", "lighthouse", "coastal road")):
        if "pool" not in probe and "surf" not in probe and "shoreline" not in probe:
            return False
    return any(
        k in probe
        for k in (
            "swimming pool",
            "pool deck",
            "poolside",
            "swim lane",
            "loc_pool",
            "loc_swimming_pool",
            "beach shore",
            "sandy shore",
            "shoreline",
            "ocean surf",
            "waves",
            "tide pool",
            "cove",
            "lagoon",
            "sub_beach_shore",
            "sub_ocean",
        )
    )


def is_bathing_sublocation(location_str: str = "", node_id: str = "") -> bool:
    """True for bathhouses, onsens, jacuzzis, and locker/shower stalls."""
    probe = _probe_loc(location_str, node_id)
    return any(
        k in probe
        for k in (
            "onsen",
            "hot spring",
            "bathhouse",
            "jacuzzi",
            "private bath",
            "loc_male_shower_room",
            "loc_female_shower_room",
            "locker & shower",
            "shower stall",
            "sub_love_hotel_jacuzzi",
        )
    )


def resolve_athletic_kit_for_venue(location_str: str = "", node_id: str = "") -> str:
    """Returns KIT_DOJO, KIT_SWIM, KIT_SPORT, or '' for an athletic/practice venue."""
    probe = _probe_loc(location_str, node_id)
    if not probe:
        return ""
    if any(k in probe for k in ("dojo", "kendo", "martial arts")):
        return KIT_DOJO
    if is_recreational_water_sublocation(location_str, node_id):
        return KIT_SWIM
    if any(k in probe for k in ("gymnasium", "varsity court", "athletic field", "running track", "stadium", "track & field", "loc_gym", "loc_track", "loc_athletic")):
        return KIT_SPORT
    return ""


def is_secret_faction_venue(location_str: str = "", node_id: str = "") -> bool:
    """True inside secret cult/syndicate/Velvet Salon sanctums."""
    probe = _probe_loc(location_str, node_id)
    return any(
        k in probe
        for k in (
            "loc_nsfw_faction_hq",
            "velvet basement salon",
            "cult_",
            "cult sanctum",
            "ritual chamber",
            "syndicate",
            "clandestine",
            "black-market vault",
            "obsidian sanctum",
        )
    )


def is_breach_or_tactical_zone(location_str: str = "", node_id: str = "", active_incursion: Any = None) -> bool:
    """True inside active anomaly breach zones or agency tactical training ranges."""
    if active_incursion:
        return True
    probe = _probe_loc(location_str, node_id)
    return any(
        k in probe
        for k in (
            "breach",
            "incursion",
            "spatial collapse",
            "rift",
            "containment sector",
            "quarantine",
            "training & calibration",
            "training range",
            "subterranean containment",
            "corrupted",
            "anomaly",
        )
    )


def safe_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}
