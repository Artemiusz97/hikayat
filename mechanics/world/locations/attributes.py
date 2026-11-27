from __future__ import annotations

import json
import re

import db
from .constants import *
from .constants import (
    _EXPLICIT_ROOM_SHOP_RE,
    _EXPLICIT_SHOP_NOUNS_RE,
    _HQ_SHOP_WING_RE,
    _HQ_TOKEN_RE,
    _NON_SHOP_ANOM_ROOM_RE,
    _NON_SHOP_ROOM_RE,
    _SHOP_KEYWORDS_RE,
)
from .seeds import *


def is_hub_location(location_str: str) -> bool:
    """Checks if a location string contains hub/safe-zone keywords."""
    if not location_str:
        return False
    location_lower = location_str.lower()
    return any(keyword in location_lower for keyword in HUB_LOCATION_KEYWORDS)


def is_location_engine_enabled(scenario_key: str) -> bool:
    """Checks if the tiered location engine is enabled for a given scenario."""
    if not scenario_key:
        return False
    return True


def get_zone_emoji(zone_name: str, scen_key: str = "") -> str:
    """
    Returns an intuitive, thematic biome/district emoji for a Tier 1 Zone.
    Used on the Game Dashboard and World Map to instantly signal the environment type.
    """
    if not zone_name:
        return "📍"
    z_lower = zone_name.lower()
    for keywords, emoji in ZONE_EMOJI_KEYWORD_RULES:
        if any(k in z_lower for k in keywords):
            return emoji
    return "📍"


def get_location_scout_description(session_id: int, location_str: str, scen_key: str = "fantasy", char_name: str = "") -> str:
    """
    Generates a rich, atmospheric layout and sensory scouting description for a location.
    Pulls structured sub-locations, zone theme, and environmental features from seed data
    without outputting raw database dumps or prop lists.
    """
    ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)
    z_name, p_name, s_name = parse_tiered_location(location_str, scen_key, session_id=session_id, char_name=char_name)

    scen_data = get_scenario_seed_data(scen_key or "fantasy")
    zone_list = list(scen_data.get("zones", []))
    for r in scen_data.get("realms") or []:
        if r.get("primary_locations"):
            zone_list.append({"id": r.get("id", ""), "name": r.get("name", ""), "primary_locations": r.get("primary_locations") or []})

    matched_zone = None
    matched_primary = None
    for z in zone_list:
        if z.get("name", "").lower() == z_name.lower() or z_name.lower() in z.get("name", "").lower() or z.get("name", "").lower() in z_name.lower():
            matched_zone = z
            for p in z.get("primary_locations", []):
                if p.get("name", "").lower() == p_name.lower() or p_name.lower() in p.get("name", "").lower() or p.get("name", "").lower() in p_name.lower():
                    matched_primary = p
                    break
            break

    if matched_primary is None:
        for z in zone_list:
            for p in z.get("primary_locations", []):
                if p.get("name", "").lower() == p_name.lower() or p_name.lower() in p.get("name", "").lower() or p.get("name", "").lower() in p_name.lower():
                    matched_primary = p
                    if not matched_zone:
                        matched_zone = z
                    break
            if matched_primary:
                break

    sub_names = []
    prop_names = []
    matched_sub = None

    if matched_primary:
        sub_names = [sub.get("name") for sub in matched_primary.get("sub_locations", []) if sub.get("name")]
        for sub in matched_primary.get("sub_locations", []):
            sub_nm = sub.get("name", "") if isinstance(sub, dict) else ""
            if s_name and sub_nm and (sub_nm.lower() == s_name.lower() or s_name.lower() in sub_nm.lower() or sub_nm.lower() in s_name.lower()):
                matched_sub = sub
                if isinstance(matched_sub.get("props"), list) and matched_sub["props"]:
                    prop_names = [str(pr) for pr in matched_sub["props"] if isinstance(pr, str) and pr]
                break
    else:
        for z in zone_list:
            for p in z.get("primary_locations", []):
                for sub in p.get("sub_locations", []):
                    sub_nm = sub.get("name", "") if isinstance(sub, dict) else ""
                    if sub_nm and p_name and (sub_nm.lower() == p_name.lower() or p_name.lower() in sub_nm.lower() or sub_nm.lower() in p_name.lower()):
                        matched_sub = sub
                        matched_primary = p
                        if not matched_zone:
                            matched_zone = z
                        if isinstance(sub.get("props"), list) and sub["props"]:
                            prop_names = [str(pr) for pr in sub["props"] if isinstance(pr, str) and pr]
                        sub_names = [s.get("name") for s in p.get("sub_locations", []) if s.get("name")]
                        break
                if matched_sub:
                    break
            if matched_sub:
                break

    if not sub_names and session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            if r.get("primary_name", "").lower() == p_name.lower() and r.get("sub_locations_json"):
                try:
                    subs = json.loads(r["sub_locations_json"])
                    if isinstance(subs, list):
                        sub_names = [s.get("name") if isinstance(s, dict) else str(s) for s in subs]
                except Exception:
                    pass

    lines = []
    area_label = (
        f"{p_name} — {matched_sub.get('name')}"
        if (matched_primary and matched_sub and matched_sub.get("name") and matched_sub.get("name", "").lower() != p_name.lower())
        else p_name
    )
    lines.append(f"**📍 Scouting Area: {area_label} ({z_name})**\n")

    if matched_zone:
        if matched_zone.get("sensory"):
            lines.append(f"*{matched_zone['sensory']}*\n")
        elif matched_zone.get("features"):
            lines.append(f"*{matched_zone['features']}*\n")

    if sub_names:
        clean_subs = ", ".join(f"**{s}**" for s in sub_names[:5])
        lines.append(f"• **Key Sections & Rooms**: {clean_subs}")

    if prop_names:
        clean_props = ", ".join(f"*{pr}*" for pr in prop_names[:4])
        lines.append(f"• **In-Room Features & Objects**: {clean_props}")

    from mechanics.world.waypoints import check_location_matches_waypoint
    active_wps = db.get_all_session_active_waypoints(session_id)
    local_wps = [wp for wp in active_wps if check_location_matches_waypoint(location_str, wp.get("target_location", ""))]
    if local_wps:
        for wp in local_wps:
            wp_label = wp.get("stage_label", "")
            is_story = bool(wp.get("is_story_quest") or "SQ-" in str(wp.get("quest_id", "")))
            tag = "Story Lead" if is_story else "Bounty Lead"
            lines.append(f"• **⭐ {tag}**: Notable interest centered around *\"{wp_label}\"*.")

    if any(k in z_name.lower() for k in ("theme park", "amusement")):
        try:
            sess = db.get_session(session_id) if session_id else None
            cur_min = int((sess or {}).get("current_minute", 480)) % 1440
            if cur_min >= 1320 or cur_min < 480:
                lines.append(
                    "• **🌙 After-Hours Anomalous Manifestation (22:00–08:00)**: The park gates closed at 10:00 PM; "
                    "reversed calliope organ music echoes through the fog, riderless coasters roar along inverted tracks, "
                    "and anomalous distortions actively manifest across the midway until the 08:00 AM reopening bell."
                )
        except Exception:
            pass

    return "\n".join(lines)


def get_regional_guild_name(zone_name: str, scenario_key: str = "fantasy") -> str:
    """Returns the distinct name for an Adventurers' Guild building in a given zone."""
    z_low = str(zone_name or "").lower()
    short_z = get_clean_zone_short_name(zone_name)

    if any(k in z_low for k in GUILD_CAPITAL_ZONE_KEYWORDS):
        return "Adventurers' Guild Headquarters"
    if any(k in z_low for k in GUILD_OUTPOST_ZONE_KEYWORDS):
        return f"Guild Outpost: {short_z}"
    return f"Guild Branch: {short_z}"


def get_location_archetype(primary_name: str, zone_name: str = "", scen_key: str = "") -> tuple[str, str]:
    """Returns (archetype_name, emoji) for a Tier 2 primary place."""
    if not primary_name:
        return ("Landmark / Area", "🗺️")

    p_lower = str(primary_name).strip().lower()

    if is_school_scenario(scen_key):
        if SCHOOL_DISUSED_RE.search(p_lower):
            return ("Disused & Rumored", "🏚️")
        if any(k in p_lower for k in SCHOOL_SECLUDED_CLUB_KEYWORDS):
            return ("Secluded & Club", "🤫")
        if any(k in p_lower for k in SCHOOL_ADMIN_KEYWORDS):
            return ("Campus Administration", "🏛️")
        if (
            SCHOOL_SOCIAL_HANGOUT_RE.search(p_lower)
            or any(k in p_lower for k in SCHOOL_TEA_LOUNGE_KEYWORDS)
        ) and "karaoke" not in p_lower:
            return ("Social & Hangout", "☕")
        if SCHOOL_ENTERTAINMENT_RE.search(p_lower) or any(k in p_lower for k in SCHOOL_GAME_LOUNGE_KEYWORDS):
            return ("Entertainment & Leisure", "🎮")
        if SCHOOL_RETAIL_RE.search(p_lower):
            return ("Retail & Shopping", "🛍️")
        if any(k in p_lower for k in SCHOOL_CLASSROOM_STUDY_KEYWORDS):
            return ("Classroom & Study", "🏫")
        if any(k in p_lower for k in SCHOOL_SPORTS_KEYWORDS):
            return ("Sports & Athletics", "⚽")
        if any(k in p_lower for k in SCHOOL_RESIDENCE_KEYWORDS):
            return ("Home & Residence", "🏠")
        if any(k in p_lower for k in SCHOOL_CIRCULATION_KEYWORDS):
            return ("Campus Circulation", "🚶")
        if any(k in p_lower for k in SCHOOL_OUTDOOR_KEYWORDS):
            return ("Parks & Outdoors", "🌳")
        return ("Campus Area", "🏫")

    from scenario_data import is_anomalous_incursions_scenario
    if is_anomalous_incursions_scenario(scen_key):
        z_lower_anom = str(zone_name or "").strip().lower()
        combo_anom = f"{z_lower_anom} {p_lower}"
        if any(k in p_lower for k in ANOM_RIFT_KEYWORDS):
            return ("Anomaly & Containment Site", "🌀")
        if any(k in combo_anom for k in ANOM_AGENCY_FACILITY_KEYWORDS):
            return ("Agency & Faction Facility", "🛡️")
        if any(k in p_lower for k in ANOM_MEDICAL_SANCTUARY_KEYWORDS):
            return ("Medical & Sanctuary", "🏥")
        if any(k in combo_anom for k in ANOM_CAMPUS_RESEARCH_KEYWORDS):
            return ("Campus & Research", "🎓")
        if any(k in p_lower for k in ANOM_TRANSIT_KEYWORDS):
            return ("Transit & Infrastructure", "🚆")
        if any(k in p_lower for k in ANOM_COMMERCIAL_LEISURE_KEYWORDS):
            return ("Urban Commercial & Leisure", "🏙️")
        if any(k in p_lower for k in ANOM_RESIDENTIAL_KEYWORDS) and "lighthouse" not in p_lower:
            return ("Residential & Safehouse", "🏠")
        if any(k in p_lower for k in ANOM_CIVIC_PARKS_KEYWORDS):
            return ("Civic Grounds & Parks", "🌳")
        return ("Urban Sector", "🏙️")

    if MONSTER_LAIR_RE.search(p_lower):
        return ("Monster Lair / Den", "🦇")
    if RUINS_ABANDONED_RE.search(p_lower):
        return ("Ruins / Abandoned", "🏚️")
    if BATTLEGROUND_RE.search(p_lower):
        return ("Historic Battleground", "🪦")
    if ARCANE_ANOMALY_RE.search(p_lower):
        return ("Arcane / Natural Anomaly", "🌀")
    if NATURAL_GROTTO_RE.search(p_lower):
        return ("Natural Grotto", "💧")
    if any(k in p_lower for k in GENERAL_FACILITY_KEYWORDS):
        return ("Infrastructure / Facility", "🛠️")
    if CAMPSITE_RE.search(p_lower):
        return ("Campsite / Encampment", "🏕️")
    if SOLITARY_DWELLING_RE.search(p_lower):
        return ("Solitary Retreat", "🛖")
    if SACRED_SITE_RE.search(p_lower):
        return ("Sacred / Mystical", "🔮")
    if any(k in p_lower for k in GENERAL_HAVEN_KEYWORDS) or ("house" in p_lower and "lighthouse" not in p_lower):
        return ("Haven / Settlement", "🏡")
    if any(k in p_lower for k in GENERAL_STRONGHOLD_KEYWORDS):
        return ("Stronghold / Fort", "⚔️")
    if any(k in p_lower for k in GENERAL_TRANSIT_KEYWORDS):
        return ("Transit Crossing", "🌉")
    if any(k in p_lower for k in GENERAL_LANDMARK_KEYWORDS):
        return ("Geographical Landmark", "🗺️")
    return ("Landmark / Area", "🗺️")


def location_has_bounty_board(location_str: str, scen_key: str = None) -> bool:
    """Checks if a location string contains notice board, guild hall, student council, or bounty hub keywords."""
    if not location_str:
        return False

    loc_lower = location_str.lower()
    from scenario_data import has_school_campus_mechanics, is_anomalous_incursions_scenario

    raw_parts = [p.strip() for p in re.split(r"➔|->", str(location_str)) if p.strip()]
    leaf_lower = raw_parts[-1].lower() if raw_parts else loc_lower
    is_room_level = len(raw_parts) >= 3

    if scen_key and (is_school_scenario(scen_key) or has_school_campus_mechanics(scen_key)):
        check_leaf = leaf_lower if is_room_level else loc_lower
        if any(k in check_leaf for k in SCHOOL_ROOM_BOARD_KEYWORDS) and not (
            "reception foyer" in check_leaf or ("council office" in check_leaf and "foyer" in check_leaf)
        ):
            return True
        if "clubroom" in check_leaf and "clubroom wing" not in check_leaf:
            return True
        if not is_anomalous_incursions_scenario(scen_key):
            return False

    if scen_key and is_anomalous_incursions_scenario(scen_key):
        return any(k in loc_lower for k in ANOMALOUS_BOARD_KEYWORDS)

    return any(re.search(rf"\b{re.escape(k)}\b", loc_lower) for k in BOUNTY_BOARD_KEYWORDS)


def _get_folklore_spirit_merchant_stores(location_str: str) -> list[dict]:
    """
    Resolves Spirit Night Market 4-wing multi-culture stalls and Spirit Enclave / Ranger shops
    across `anomalous_incursions`, `anomalous_high_school`, and `urban_anomalies`.
    """
    from mechanics.combat.merchant import MERCHANT_ARCHETYPES

    loc_lower = str(location_str or "").lower()
    raw_parts = [p.strip() for p in re.split(r"➔|->", str(location_str or "")) if p.strip()]
    leaf_lower = raw_parts[-1].lower() if raw_parts else loc_lower

    def _pack(keys: tuple[str, ...]) -> list[dict]:
        return [{"type": k, **MERCHANT_ARCHETYPES[k]} for k in keys if k in MERCHANT_ARCHETYPES]

    def _match_target(target_lower: str) -> list[dict]:
        if any(k in target_lower for k in ("sub_crossroads_bazaar_walk", "lotus-canal lantern bazaar promenade", "lantern bazaar promenade")):
            return _pack(("bazaar_foxfire_tea_stall", "bazaar_cempaka_kuih_stall"))
        if any(k in target_lower for k in ("sub_crossroads_kitsune_alley", "kitsunebi craft", "mask alley")):
            return _pack(("bazaar_kagura_mask_stall", "bazaar_inari_ofuda_stall"))
        if any(k in target_lower for k in ("sub_crossroads_bunian_arcade", "songket & pusaka", "pusaka arcade", "seri nusantara")):
            return _pack(("bazaar_songket_silk_stall", "bazaar_empu_pusaka_stall"))
        if any(k in target_lower for k in ("sub_crossroads_curio_arcade", "dual-tradition spirit curio", "curio arcade")):
            return _pack(("crossroads_bazaar_merchant", "bazaar_ghoul_curio_stall"))
        if any(k in target_lower for k in ("loc_crossroads_night_market", "pasar malam ghaib", "lantern bazaar", "dusk confluence")):
            return _pack((
                "crossroads_bazaar_merchant",
                "bazaar_foxfire_tea_stall",
                "bazaar_cempaka_kuih_stall",
                "bazaar_kagura_mask_stall",
                "bazaar_inari_ofuda_stall",
                "bazaar_songket_silk_stall",
                "bazaar_empu_pusaka_stall",
                "bazaar_ghoul_curio_stall",
            ))
        if any(k in target_lower for k in ("sub_ghoul_curio_morgue", "formalin & bone-relic", "bone-relic apothecary", "ossuary court & inner crypt")):
            return _pack(("ghoul_ossuary_merchant",))
        if any(k in target_lower for k in ("sub_kitsune_curio_shop", "fox-fire apothecary", "spirit-fire curio", "myōbu spirit-fire", "myobu spirit-fire", "spirit curio", "sato-no-inari inner sanctuary")):
            return _pack(("kitsune_spirit_merchant",))
        if any(k in target_lower for k in ("sub_bunian_artisan_hall", "artisan hall", "istana & laman seri cempaka", "balai pusaka")):
            return _pack(("bunian_pusaka_merchant",))
        if any(k in target_lower for k in ("ranger station", "park ranger", "ranger field station", "trailhead information counter", "trailhead outpost", "trail permit", "emergency supply counter")):
            return _pack(("ranger_station_outfitter",))
        return []

    hits = _match_target(leaf_lower)
    if not hits and leaf_lower != loc_lower:
        hits = _match_target(loc_lower)
    return hits


def get_available_merchant_types_for_location(location_str: str, scen_key: str = None) -> list[dict]:
    """Returns a list of available specialist merchant stores for the current location."""
    from mechanics.combat.merchant import MERCHANT_ARCHETYPES
    from scenario_data import has_school_campus_mechanics, is_anomalous_incursions_scenario, is_nsfw_scenario

    if not location_str:
        return [{"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]}]

    folklore_stores = _get_folklore_spirit_merchant_stores(location_str)
    if folklore_stores:
        return folklore_stores

    loc_lower = str(location_str).lower()
    is_nsfw = is_nsfw_scenario(scen_key) if scen_key else False

    # 1. Non-Combat / High School Scenarios
    if scen_key and is_school_scenario(scen_key):
        if any(k in loc_lower for k in ("love hotel", "mirage boutique")):
            return []

        stores = []
        if is_nsfw and any(k in loc_lower for k in ("adult boutique", "velvet curtain", "adult store", "erotic boutique", "afterdark", "secret boutique", "adult novelty")):
            stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
        if is_nsfw and any(k in loc_lower for k in ("nightclub", "neon pulse", "vip lounge")):
            stores.append({"type": "nightclub_merchant", **MERCHANT_ARCHETYPES["nightclub_merchant"]})
        if any(k in loc_lower for k in ("luxury designer", "designer boutique", "brand clothing", "haute couture", "high-end fashion")):
            stores.append({"type": "brand_clothes_merchant", **MERCHANT_ARCHETYPES["brand_clothes_merchant"]})
        elif any(k in loc_lower for k in ("streetwear", "casual apparel", "clothing", "apparel", "fashion boutique", "boutique")) and not any(
            k in loc_lower for k in ("adult", "velvet curtain", "erotic")
        ):
            stores.append({"type": "clothes_merchant", **MERCHANT_ARCHETYPES["clothes_merchant"]})
        if any(k in loc_lower for k in ("accessories", "bijoux", "jewelry", "jewellery")):
            stores.append({"type": "accessories_merchant", **MERCHANT_ARCHETYPES["accessories_merchant"]})
        if any(k in loc_lower for k in ("gift", "curio", "merchandise", "souvenir", "shrine shop", "merch", "toy shop")):
            stores.append({"type": "gift_merchant", **MERCHANT_ARCHETYPES["gift_merchant"]})
        if any(k in loc_lower for k in ("night market", "lantern night", "street bazaar", "night bazaar")):
            stores.append({"type": "night_market_merchant", **MERCHANT_ARCHETYPES["night_market_merchant"]})
        if any(k in loc_lower for k in ("downtown diner", "family restaurant", "restaurant", "ramen", "steakhouse", "bistro")):
            stores.append({"type": "restaurant_merchant", **MERCHANT_ARCHETYPES["restaurant_merchant"]})
        if any(k in loc_lower for k in ("convenience store", "24-hour convenience", "konbini", "mini-mart")):
            stores.append({"type": "convenience_merchant", **MERCHANT_ARCHETYPES["convenience_merchant"]})
        if any(k in loc_lower for k in ("cafe", "café", "boba", "bakery", "coffee", "espresso", "canteen", "cafeteria", "tea house", "snack bar", "beach shack")):
            stores.append({"type": "cafe_merchant", **MERCHANT_ARCHETYPES["cafe_merchant"]})
        if any(k in loc_lower for k in ("co-op", "bookstore", "school store", "stationery", "campus kiosk")):
            stores.append({"type": "school_merchant", **MERCHANT_ARCHETYPES["school_merchant"]})
        if any(k in loc_lower for k in ("quiet alley", "underpass")) and location_has_merchant_shop(location_str, scen_key):
            stores.append({"type": "student_merchant", **MERCHANT_ARCHETYPES["student_merchant"]})
        if is_nsfw and any(k in loc_lower for k in ("silk & curio", "apothecary counter", "velvet basement")) and location_has_merchant_shop(location_str, scen_key):
            if not any(s["type"] == "adult_store_merchant" for s in stores):
                stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
            stores.append({"type": "club_merchant", **MERCHANT_ARCHETYPES["club_merchant"]})
        if (any(k in loc_lower for k in SCHOOL_CLUB_MERCHANT_KEYWORDS) or ("clubroom" in loc_lower and "clubroom wing" not in loc_lower)) and location_has_merchant_shop(location_str, scen_key):
            if not any(s["type"] == "club_merchant" for s in stores):
                stores.append({"type": "club_merchant", **MERCHANT_ARCHETYPES["club_merchant"]})

        if stores:
            return stores

        if any(k in loc_lower for k in ("downtown", "commercial", "shopping mall", "arcade", "city square", "plaza")):
            hub_stores = [
                {"type": "cafe_merchant", **MERCHANT_ARCHETYPES["cafe_merchant"]},
                {"type": "restaurant_merchant", **MERCHANT_ARCHETYPES["restaurant_merchant"]},
                {"type": "clothes_merchant", **MERCHANT_ARCHETYPES["clothes_merchant"]},
                {"type": "brand_clothes_merchant", **MERCHANT_ARCHETYPES["brand_clothes_merchant"]},
                {"type": "accessories_merchant", **MERCHANT_ARCHETYPES["accessories_merchant"]},
                {"type": "gift_merchant", **MERCHANT_ARCHETYPES["gift_merchant"]},
            ]
            if is_nsfw:
                hub_stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
                hub_stores.append({"type": "nightclub_merchant", **MERCHANT_ARCHETYPES["nightclub_merchant"]})
            return hub_stores

        return [{"type": "school_merchant", **MERCHANT_ARCHETYPES["school_merchant"]}]

    # 2. Combat / Fantasy / Sci-Fi / Cyberpunk Scenarios
    is_anom_scen = is_anomalous_incursions_scenario(scen_key) if scen_key else False
    if any(k in loc_lower for k in BAZAAR_HUB_KEYWORDS):
        hub_stores = [
            {"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]},
            {"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]},
            {"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]},
            {"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]},
            {"type": "food_merchant", **MERCHANT_ARCHETYPES["food_merchant"]},
            {"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]},
        ]
        if not is_anom_scen:
            hub_stores.insert(4, {"type": "spellbook_merchant", **MERCHANT_ARCHETYPES["spellbook_merchant"]})
        if is_nsfw:
            hub_stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
        return hub_stores

    raw_parts = [p.strip() for p in re.split(r"➔|->", str(location_str)) if p.strip()]
    parent_join_lower = " ".join(raw_parts[:-1]).lower() if len(raw_parts) >= 2 else ""
    is_multi_wing_target = (
        len(raw_parts) >= 2
        and (
            any(m in parent_join_lower for m in MULTI_WING_COMPLEX_MARKERS)
            or bool(_HQ_TOKEN_RE.search(parent_join_lower))
        )
    )
    match_lower = raw_parts[-1].lower() if is_multi_wing_target else loc_lower

    def _collect_specialist_stores(target_lower: str) -> list[dict]:
        found = []
        if any(k in target_lower for k in ("formalin & bone-relic", "bone-relic apothecary", "ossuary court & inner crypt")) and "ghoul_ossuary_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "ghoul_ossuary_merchant", **MERCHANT_ARCHETYPES["ghoul_ossuary_merchant"]})
            return found
        if any(k in target_lower for k in ("kitsunebi craft", "mask alley")) and "kitsune_spirit_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "kitsune_spirit_merchant", **MERCHANT_ARCHETYPES["kitsune_spirit_merchant"]})
            if "crossroads_bazaar_merchant" in MERCHANT_ARCHETYPES:
                found.append({"type": "crossroads_bazaar_merchant", **MERCHANT_ARCHETYPES["crossroads_bazaar_merchant"]})
            return found
        if any(k in target_lower for k in ("songket & pusaka", "pusaka arcade", "seri nusantara")) and "bunian_pusaka_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "bunian_pusaka_merchant", **MERCHANT_ARCHETYPES["bunian_pusaka_merchant"]})
            if "crossroads_bazaar_merchant" in MERCHANT_ARCHETYPES:
                found.append({"type": "crossroads_bazaar_merchant", **MERCHANT_ARCHETYPES["crossroads_bazaar_merchant"]})
            return found
        if any(k in target_lower for k in ("pasar malam ghaib", "lantern bazaar", "curio arcade", "dusk confluence")) and "crossroads_bazaar_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "crossroads_bazaar_merchant", **MERCHANT_ARCHETYPES["crossroads_bazaar_merchant"]})
            return found
        if any(k in target_lower for k in ("fox-fire apothecary", "spirit-fire curio", "myōbu spirit-fire", "myobu spirit-fire", "spirit curio", "sato-no-inari inner sanctuary")) and "kitsune_spirit_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "kitsune_spirit_merchant", **MERCHANT_ARCHETYPES["kitsune_spirit_merchant"]})
            return found
        if any(k in target_lower for k in ("pusaka", "artisan hall", "istana & laman seri cempaka")) and "bunian_pusaka_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "bunian_pusaka_merchant", **MERCHANT_ARCHETYPES["bunian_pusaka_merchant"]})
            return found
        if any(k in target_lower for k in ("salvage stalls", "drifter bazaar", "relic, ammo & salvage")) and "potion_merchant" in MERCHANT_ARCHETYPES:
            found.append({"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]})
            found.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})
            return found
        if any(k in target_lower for k in ("wake parlor", "velvet & clove lounge", "black-velvet wake")):
            found.append({"type": "food_merchant", **MERCHANT_ARCHETYPES["food_merchant"]})
            return found
        if any(k in target_lower for k in ("ranger station", "park ranger", "ranger field station", "trailhead information counter", "trailhead outpost", "trail permit", "emergency supply")) and "ranger_station_outfitter" in MERCHANT_ARCHETYPES:
            found.append({"type": "ranger_station_outfitter", **MERCHANT_ARCHETYPES["ranger_station_outfitter"]})
            return found
        if any(k in target_lower for k in ("regional tower hq", "operations spire hq", "tower hq", "operations hq", "syndicate anomalous armory", "syndicate tactical armory", "requisition shop", "requisition depot", "boiler-room locker", "custodian's boiler")):
            found.append({"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]})
            found.append({"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]})
            found.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})
        if any(k in target_lower for k in ("tactical armory", "ordnance depot", "special ordnance", "requisition vault", "vaulted armory", "gunsmithing bench", "ossuary armory", "ritual athame", "black-bag ballistics", "suppressed ordnance")):
            if not any(s["type"] == "weapon_merchant" for s in found):
                found.append({"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]})
        elif any(k in target_lower for k in ("forge", "smithy", "blacksmith", "weaponsmith", "armory")):
            if not any(s["type"] == "weapon_merchant" for s in found):
                found.append({"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]})
            if not any(s["type"] == "armor_merchant" for s in found):
                found.append({"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]})
        if any(k in target_lower for k in ("field outfitter", "tailoring quartermaster", "bespoke ballistic outfitter", "ballistic tailoring", "exo-weave atelier", "tactical rigging", "fitted armor", "covenant vestment", "warded silk loom", "faraday-weave", "counter-surveillance tailor", "outfitter", "couture", "boutique", "apparel")):
            if not any(s["type"] == "armor_merchant" for s in found):
                found.append({"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]})
            if not any(s["type"] == "clothes_merchant" for s in found):
                found.append({"type": "clothes_merchant", **MERCHANT_ARCHETYPES["clothes_merchant"]})
        if any(k in target_lower for k in ("apothecary", "apotheca", "ichor distillation", "cognitohazard lab", "alchemist", "herbalist", "potion", "pharmacy", "cleansing bay", "psychic detox", "neural recovery", "field infirmary", "dispensary")):
            if not any(s["type"] == "potion_merchant" for s in found):
                found.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})
        if not is_anom_scen and any(k in target_lower for k in ("arcane", "magic", "mystic", "enchanter", "sorcery", "grimoire", "scribe", "antiquities", "licensed wards", "alchemical apothecary")):
            if not any(s["type"] == "magic_merchant" for s in found):
                found.append({"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]})
            if not any(s["type"] == "spellbook_merchant" for s in found):
                found.append({"type": "spellbook_merchant", **MERCHANT_ARCHETYPES["spellbook_merchant"]})
        elif is_anom_scen and any(k in target_lower for k in ("antiquities", "licensed wards", "occult shop", "relic shop")):
            if not any(s["type"] == "magic_merchant" for s in found):
                found.append({"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]})
            if not any(s["type"] == "potion_merchant" for s in found):
                found.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})
        if any(k in target_lower for k in ("omikuji", "talisman stand", "carnival midway", "gift emporium", "duty-free", "campus bookstore", "bookstore", "curio", "campus co-op", "co-op")):
            if not any(s["type"] == "gift_merchant" for s in found):
                found.append({"type": "gift_merchant", **MERCHANT_ARCHETYPES["gift_merchant"]})
        if any(k in target_lower for k in ("bakery", "tavern", "inn", "saloon", "canteen", "refectory", "commissary", "mess hall", "food stall", "diner", "espresso", "roastery", "pour-over", "kitchenette", "skyline lounge", "ramen", "izakaya", "cafe", "café", "konbini", "convenience", "fish market", "carnival midway", "night market", "street food", "tea house", "garden terrace", "duty-free", "black bazaar")):
            found.append({"type": "food_merchant", **MERCHANT_ARCHETYPES["food_merchant"]})
        if any(k in target_lower for k in ("espresso", "roastery", "pour-over", "kitchenette", "skyline lounge", "cafe", "café", "canteen", "refectory", "commissary", "boba")):
            found.append({"type": "cafe_merchant", **MERCHANT_ARCHETYPES["cafe_merchant"]})
        if any(k in target_lower for k in ("black market", "pawn", "crimson masquerade", "black bazaar", "drifter enclave")):
            if not any(s["type"] == "weapon_merchant" for s in found):
                found.append({"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]})
            if not any(s["type"] == "magic_merchant" for s in found):
                found.append({"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]})
            if not any(s["type"] == "potion_merchant" for s in found):
                found.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})
        if is_nsfw and any(k in target_lower for k in ("adult", "brothel", "pleasure", "cyber-den", "erotic", "novelty", "afterdark", "velvet mirage", "red-lantern")):
            found.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
        if scen_key and has_school_campus_mechanics(scen_key) and location_has_merchant_shop(location_str, scen_key):
            if is_nsfw and any(k in target_lower for k in ("silk & curio", "apothecary counter", "velvet boutique")):
                if not any(s["type"] == "adult_store_merchant" for s in found):
                    found.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})
                if not any(s["type"] == "club_merchant" for s in found) and "club_merchant" in MERCHANT_ARCHETYPES:
                    found.append({"type": "club_merchant", **MERCHANT_ARCHETYPES["club_merchant"]})
            if (any(k in target_lower for k in ANOM_SCHOOL_CLUB_MERCHANT_KEYWORDS) or ("clubroom" in target_lower and "clubroom wing" not in target_lower)) and "club_merchant" in MERCHANT_ARCHETYPES:
                if not any(s["type"] == "club_merchant" for s in found):
                    found.append({"type": "club_merchant", **MERCHANT_ARCHETYPES["club_merchant"]})
        return found

    stores = _collect_specialist_stores(match_lower)
    if not stores and match_lower != loc_lower:
        stores = _collect_specialist_stores(loc_lower)
    if stores:
        return stores

    return [{"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]}]


def location_has_merchant_shop(location_str: str, scen_key: str = None) -> bool:
    """Checks if a location is an actual commercial shop, store, market, café, canteen, or merchant establishment."""
    if not location_str:
        return False

    raw_parts = [p.strip() for p in re.split(r"➔|->", str(location_str)) if p.strip()]
    is_room_level = len(raw_parts) >= 3
    target = raw_parts[1] if len(raw_parts) >= 2 else (raw_parts[0] if raw_parts else location_str)
    leaf_target = raw_parts[-1] if raw_parts else target

    p_lower = target.lower()
    leaf_lower = leaf_target.lower()
    school_check_lower = leaf_lower if is_room_level else p_lower

    _folklore_shop_leaf_markers = (
        "sub_crossroads_bazaar_walk", "lotus-canal lantern bazaar promenade", "lantern bazaar promenade",
        "sub_crossroads_kitsune_alley", "kitsunebi craft", "mask alley",
        "sub_crossroads_bunian_arcade", "songket & pusaka", "pusaka arcade", "seri nusantara",
        "sub_crossroads_curio_arcade", "dual-tradition spirit curio", "curio arcade",
        "loc_crossroads_night_market", "pasar malam ghaib", "lantern bazaar",
        "sub_kitsune_curio_shop", "fox-fire apothecary", "spirit-fire curio",
        "sub_bunian_artisan_hall", "artisan hall", "balai pusaka",
        "sub_ghoul_curio_morgue", "formalin & bone-relic", "bone-relic apothecary",
    )
    if any(k in leaf_lower for k in _folklore_shop_leaf_markers) or (
        not is_room_level and any(k in p_lower for k in _folklore_shop_leaf_markers)
    ):
        return True

    from scenario_data import has_school_campus_mechanics, is_anomalous_incursions_scenario
    is_anom_scen = is_anomalous_incursions_scenario(scen_key) if scen_key else False

    if scen_key and (is_school_scenario(scen_key) or has_school_campus_mechanics(scen_key)):
        if any(k in school_check_lower for k in SCHOOL_QUARTERMASTER_OR_MINOR_SHOPS):
            return True
        if "clubroom" in school_check_lower and "clubroom wing" not in school_check_lower:
            return True

        if not is_anom_scen or any(nsp in school_check_lower for nsp in NON_SHOP_SCHOOL_PLACES):
            if any(nsp in school_check_lower for nsp in NON_SHOP_SCHOOL_PLACES):
                if not is_anom_scen or not any(hq_w in leaf_lower for hq_w in SCHOOL_HQ_EXEMPT_SHOP_WINGS):
                    return False

        if any(k in school_check_lower for k in SCHOOL_SHOP_KEYWORDS):
            return True
        if not is_anom_scen:
            return False

    if is_room_level:
        has_explicit_room_shop = (
            bool(_EXPLICIT_ROOM_SHOP_RE.search(leaf_lower))
            or any(mc in leaf_lower for mc in DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS)
        )
        if not has_explicit_room_shop and _NON_SHOP_ROOM_RE.search(leaf_lower):
            return False

    if is_anom_scen:
        if _EXPLICIT_SHOP_NOUNS_RE.search(leaf_lower):
            return True
        if _NON_SHOP_ANOM_ROOM_RE.search(leaf_lower):
            return False
        return bool(_EXPLICIT_SHOP_NOUNS_RE.search(p_lower))

    parent_chain_lower = " ".join(raw_parts[:-1]).lower() if len(raw_parts) >= 2 else ""
    if len(raw_parts) >= 2 and (
        any(hq_k in parent_chain_lower for hq_k in HQ_PARENT_CHAIN_KEYWORDS)
        or _HQ_TOKEN_RE.search(parent_chain_lower)
    ):
        return bool(_HQ_SHOP_WING_RE.search(leaf_lower))

    full_lower = str(location_str).lower()
    return bool(_SHOP_KEYWORDS_RE.search(p_lower) or _SHOP_KEYWORDS_RE.search(full_lower))


def location_has_faction_hq(
    location_str: str,
    session_id: int = None,
    *,
    preloaded_factions: list[dict] | None = None,
) -> bool:
    """Checks if the given location (Tier 2 Facility or Tier 3 Room) is registered as a Faction HQ."""
    if not location_str:
        return False

    raw_parts = [p.strip() for p in re.split(r"➔|->", str(location_str)) if p.strip()]
    leaf_lower = (raw_parts[-1] if raw_parts else str(location_str)).lower()
    is_room_level = len(raw_parts) >= 3

    if len(raw_parts) <= 2 and any(leaf_lower == w or w in leaf_lower for w in EXCLUDED_FACTION_HQ_PARENT_WINGS):
        return False

    if session_id:
        try:
            if preloaded_factions is not None:
                faction = db.get_faction_by_hq(session_id, location_str, preloaded_factions=preloaded_factions)
            else:
                faction = db.get_faction_by_hq(session_id, location_str)
            if faction:
                return True
        except Exception:
            pass

    target_lower = leaf_lower if is_room_level else str(location_str).lower()
    if any(k in target_lower for k in FACTION_HQ_KEYWORDS):
        return True
    if (
        not is_room_level
        and "reception foyer" not in leaf_lower
        and any(k in target_lower for k in FACTION_HQ_SCHOOL_FACILITY_KEYWORDS)
    ):
        return True
    if "clubroom" in leaf_lower and not any(w in leaf_lower for w in EXCLUDED_FACTION_HQ_PARENT_WINGS):
        return True
    return False


def get_location_emoji(
    location_name: str,
    zone_name: str = "",
    waypoint_markers: dict = None,
    session_id: int = None,
    scen_key: str = None,
    char_name: str = "",
    *,
    preloaded_factions: list[dict] | None = None,
    player_house_name: str | None = None,
) -> str:
    """Determines the single clean emoji for a location in the travel dropdown."""
    value_str = f"{zone_name} ➔ {location_name}" if zone_name else location_name

    if waypoint_markers:
        wp_tags = waypoint_markers.get(value_str) or waypoint_markers.get(location_name)
        if wp_tags:
            if any("⚡" in tag for tag in wp_tags):
                return "⚡"
            if any("⭐" in tag for tag in wp_tags):
                return "⭐"
            return "🎯"

    if (
        location_has_faction_hq(location_name, session_id=session_id, preloaded_factions=preloaded_factions)
        or (zone_name and location_has_faction_hq(zone_name, session_id=session_id, preloaded_factions=preloaded_factions))
    ):
        return "🏛️"
    if location_has_bounty_board(location_name, scen_key=scen_key):
        return "📋"
    if location_has_merchant_shop(location_name, scen_key=scen_key):
        return "🛍️"

    if player_house_name is not None:
        if player_house_name and (location_name == player_house_name or player_house_name in location_name):
            return "🏠"
    elif session_id or char_name:
        try:
            p_house = get_session_player_house_name(session_id or 0, char_name=char_name, scenario_key=scen_key or "fantasy")
            if location_name == p_house or (p_house and p_house in location_name):
                return "🏠"
        except Exception:
            pass

    return "📍"


def get_notice_board_label(scen_key: str = None) -> tuple[str, str]:
    """Returns (button_label, emoji) for the Notice Board button based on scenario."""
    scen = str(scen_key or "").lower()
    if is_school_scenario(scen):
        return ("Campus Bulletin", "📋")
    if "cyberpunk" in scen or "sci_fi" in scen:
        return ("Job Terminal", "💾")
    if "steampunk" in scen:
        return ("Dispatch Board", "📻")
    if "apocalypse" in scen:
        return ("Radio Dispatch", "📻")
    return ("Notice Board", "📋")


from .hierarchy import get_clean_zone_short_name, parse_tiered_location
from .seeding import ensure_session_locations_seeded
