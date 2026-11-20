"""
Static NPC Population Catalogs for Expanded Living Worlds.

Pure Layer-1 data module (zero DB calls, zero RNG, zero side effects) defining
pre-seeded District Merchants, Civic/Institutional Staff, Roaming Street Vendors,
multi-stop Roaming Pedestrians/Civilians, expanded HS/AHS Campus & Town casts,
Hidden-in-Plain-Sight Secrets, Cohabiting Pairs, and Combinatorial Trait Pools.

Every location ID in this file corresponds strictly to nodes seeded in
`data/locations_seed.json` and campus leaves registered in `npc_schedule.py`.
"""
from __future__ import annotations

from typing import Any


def _merch(
    slot_id: str,
    role: str,
    zone_id: str,
    workplace_node_id: str,
    merchant_archetype: str,
    shift_profile: str = "day",
    *,
    hangout_node_id: str = "",
    home_node_id: str = "",
    culture_hint: str = "",
    gender_hint: str = "",
    is_unique_proprietor: bool = False,
    folklore_pool: str = "",
    nsfw_venue: bool = False,
    closes_at_22: bool = False,
    closes_at_20: bool = False,
    is_24h_station: bool = False,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "origin": "district_merchant",
        "role": role,
        "zone_id": zone_id,
        "workplace_node_id": workplace_node_id,
        "hangout_node_id": hangout_node_id or workplace_node_id,
        "home_node_id": home_node_id,
        "merchant_archetype": merchant_archetype,
        "shift_profile": shift_profile,
        "culture_hint": culture_hint,
        "gender_hint": gender_hint,
        "is_unique_proprietor": is_unique_proprietor,
        "folklore_pool": folklore_pool,
        "nsfw_venue": nsfw_venue,
        "closes_at_22": closes_at_22,
        "closes_at_20": closes_at_20,
        "is_24h_station": is_24h_station,
        "age_group": "adult",
    }


def _civic(
    slot_id: str,
    role: str,
    zone_id: str,
    workplace_node_id: str,
    shift_profile: str = "day",
    *,
    hangout_node_id: str = "",
    home_node_id: str = "",
    culture_hint: str = "",
    gender_hint: str = "",
    age_group: str = "adult",
    closes_at_22: bool = False,
    closes_at_20: bool = False,
    is_24h_station: bool = False,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "origin": "civic_staff",
        "role": role,
        "zone_id": zone_id,
        "workplace_node_id": workplace_node_id,
        "hangout_node_id": hangout_node_id or workplace_node_id,
        "home_node_id": home_node_id,
        "shift_profile": shift_profile,
        "culture_hint": culture_hint,
        "gender_hint": gender_hint,
        "age_group": age_group,
        "closes_at_22": closes_at_22,
        "closes_at_20": closes_at_20,
        "is_24h_station": is_24h_station,
    }


def _vendor(
    slot_id: str,
    role: str,
    zone_id: str,
    roaming_route: tuple[str, ...],
    merchant_archetype: str,
    *,
    weekend_route: tuple[str, ...] = (),
    nocturnal: bool = False,
    contraband: bool = False,
    folklore_pool: str = "",
    culture_hint: str = "",
    gender_hint: str = "",
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "origin": "roaming_merchant",
        "role": role,
        "zone_id": zone_id,
        "workplace_node_id": roaming_route[0] if roaming_route else "",
        "hangout_node_id": roaming_route[-1] if roaming_route else "",
        "roaming_route": list(roaming_route),
        "weekend_route": list(weekend_route or roaming_route),
        "shift_profile": "street_vendor",
        "merchant_archetype": merchant_archetype,
        "nocturnal": nocturnal,
        "is_contraband_peddler": contraband,
        "folklore_pool": folklore_pool,
        "culture_hint": culture_hint,
        "gender_hint": gender_hint,
        "age_group": "adult",
    }


def _ped(
    slot_id: str,
    role: str,
    zone_id: str,
    roaming_route: tuple[str, ...],
    *,
    weekend_route: tuple[str, ...] = (),
    workplace_node_id: str = "",
    hangout_node_id: str = "",
    home_node_id: str = "",
    age_group: str = "adult",
    grade: str = "",
    culture_hint: str = "",
    gender_hint: str = "",
    is_truant_peer: bool = False,
) -> dict[str, Any]:
    wp = workplace_node_id or (roaming_route[1] if len(roaming_route) > 1 else roaming_route[0])
    hang = hangout_node_id or roaming_route[-1]
    return {
        "slot_id": slot_id,
        "origin": "roaming_citizen",
        "role": role,
        "zone_id": zone_id,
        "workplace_node_id": wp,
        "hangout_node_id": hang,
        "home_node_id": home_node_id,
        "roaming_route": list(roaming_route),
        "weekend_route": list(weekend_route or roaming_route),
        "shift_profile": "pedestrian",
        "age_group": age_group,
        "grade": grade,
        "culture_hint": culture_hint,
        "gender_hint": gender_hint,
        "is_truant_peer": is_truant_peer,
    }


def _hs_student(
    slot_id: str,
    role: str,
    grade: str,
    club: str,
    workplace_node_id: str,
    hangout_node_id: str,
    *,
    part_time_shift: dict[str, Any] | None = None,
    age_group: str = "young_adult",
    culture_hint: str = "",
    gender_hint: str = "",
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "origin": "campus_seed",
        "role": role,
        "grade": grade,
        "club": club,
        "zone_id": "zone_school_main",
        "workplace_node_id": workplace_node_id,
        "hangout_node_id": hangout_node_id,
        "shift_profile": "day" if grade == "Staff" else "student",
        "part_time_shift": dict(part_time_shift) if part_time_shift else None,
        "age_group": age_group,
        "culture_hint": culture_hint,
        "gender_hint": gender_hint,
    }


# ---------------------------------------------------------------------------
# ANOMALOUS INCURSIONS (+ AHS): 52 DISTRICT MERCHANTS across all 16 zones
# ---------------------------------------------------------------------------
ANOMALOUS_DISTRICT_MERCHANTS: tuple[dict[str, Any], ...] = (
    # zone_city_center (5)
    _merch("anom_m_metro_day", "Transit Terminal Convenience Clerk", "zone_city_center", "loc_metro_transit_terminal", "convenience_merchant", "day", hangout_node_id="loc_sunken_plaza"),
    _merch("anom_m_metro_night", "Terminal Owl Newsstand Clerk", "zone_city_center", "loc_metro_transit_terminal", "convenience_merchant", "night", hangout_node_id="loc_sunken_plaza"),
    _merch("anom_m_plaza_coffee", "Sunken Plaza Kiosk Barista", "zone_city_center", "loc_sunken_plaza", "cafe_merchant", "day"),
    _merch("anom_m_curio_prop", "Occult Curio Shopkeeper", "zone_city_center", "loc_occult_curio_shop", "accessories_merchant", "day", is_unique_proprietor=True, folklore_pool="urban_market"),
    _merch("anom_m_curio_eve", "Curio Archive Clerk", "zone_city_center", "loc_occult_curio_shop", "gift_merchant", "evening", folklore_pool="urban_market", closes_at_22=True),
    # zone_downtown (6)
    _merch("anom_m_arcade_shop_day", "Shopping Arcade Apparel Clerk", "zone_downtown", "loc_downtown_shopping_arcade", "clothes_merchant", "day"),
    _merch("anom_m_arcade_shop_eve", "Shopping Arcade Stylist", "zone_downtown", "loc_downtown_shopping_arcade", "clothes_merchant", "evening", closes_at_22=True),
    _merch("anom_m_jazz_bar", "Downtown Jazz Bar Mixologist", "zone_downtown", "loc_downtown_jazz_bar", "nightclub_merchant", "evening", is_unique_proprietor=True),
    _merch("anom_m_game_prize", "Game Arcade Prize Counter Clerk", "zone_downtown", "loc_downtown_game_arcade", "gift_merchant", "evening", closes_at_22=True),
    _merch("anom_m_ramen_chef", "Ramen Alley Broth Master", "zone_downtown", "loc_downtown_ramen_alley", "restaurant_merchant", "evening", is_unique_proprietor=True, closes_at_22=True),
    _merch("anom_m_velvet_vip", "Velvet Mirage Lounge Server", "zone_downtown", "loc_velvet_mirage_club", "nightclub_merchant", "night", nsfw_venue=True),
    # zone_uptown (4)
    _merch("anom_m_roastery_day", "Uptown Roastery Head Barista", "zone_uptown", "loc_uptown_roastery", "cafe_merchant", "day", is_unique_proprietor=True),
    _merch("anom_m_roastery_eve", "Uptown Pastry & Pour Clerk", "zone_uptown", "loc_uptown_roastery", "cafe_merchant", "evening", closes_at_22=True),
    _merch("anom_m_museum_gift", "Museum Pavilion Gift Clerk", "zone_uptown", "loc_uptown_museum", "gift_merchant", "day"),
    _merch("anom_m_cathedral_charm", "Cathedral Brass & Charm Keeper", "zone_uptown", "loc_historic_cathedral", "accessories_merchant", "day", folklore_pool="shrine"),
    # zone_ultra_rich (4)
    _merch("anom_m_couture_prop", "Haute Couture Master Tailor", "zone_ultra_rich", "loc_haute_couture_salon", "brand_clothes_merchant", "day", is_unique_proprietor=True),
    _merch("anom_m_couture_eve", "Haute Couture Private Stylist", "zone_ultra_rich", "loc_haute_couture_salon", "brand_clothes_merchant", "evening", closes_at_22=True),
    _merch("anom_m_sky_lounge", "Sky VIP Lounge Sommelier", "zone_ultra_rich", "loc_sky_vip_lounge", "nightclub_merchant", "evening"),
    _merch("anom_m_crimson_auc", "Crimson Auction Gallery Broker", "zone_ultra_rich", "loc_crimson_auction_house", "accessories_merchant", "evening"),
    # zone_low_cost_wards (5)
    _merch("anom_m_blackmkt_armorer", "Backstreet Arms Broker", "zone_low_cost_wards", "loc_backstreet_black_market", "weapon_merchant", "night", is_unique_proprietor=True),
    _merch("anom_m_blackmkt_gear", "Backstreet Surplus Outfitter", "zone_low_cost_wards", "loc_backstreet_black_market", "armor_merchant", "evening"),
    _merch("anom_m_rusty_pipe", "Rusty Pipe Tavern Bartender", "zone_low_cost_wards", "loc_rusty_pipe_bar", "food_merchant", "evening", is_unique_proprietor=True),
    _merch("anom_m_red_lantern", "Red Lantern Bottle Host", "zone_low_cost_wards", "loc_red_lantern_lounge", "nightclub_merchant", "night", nsfw_venue=True),
    _merch("anom_m_clinic_pharm", "Community Clinic Pharmacist", "zone_low_cost_wards", "loc_community_clinic", "potion_merchant", "day"),
    # zone_industrial (2)
    _merch("anom_m_freight_canteen", "Rail Yard Canteen Quartermaster", "zone_industrial", "loc_rail_freight_yard", "general_merchant", "day"),
    _merch("anom_m_substation_gear", "Night-Shift Tool & Plate Dealer", "zone_industrial", "loc_power_substation", "weapon_merchant", "night"),
    # zone_city_docks (4)
    _merch("anom_m_fishmkt_prop", "Harbor Fish Market Wholesaler", "zone_city_docks", "loc_harbor_fish_market", "food_merchant", "day", is_unique_proprietor=True),
    _merch("anom_m_fishmkt_eve", "Pier Skewer & Broth Hawker", "zone_city_docks", "loc_harbor_fish_market", "night_market_merchant", "evening", closes_at_22=True),
    _merch("anom_m_pier_rigging", "Container Pier Rigging Chandler", "zone_city_docks", "loc_container_pier", "general_merchant", "day"),
    _merch("anom_m_drydock_outfitter", "Shipyard Workwear Outfitter", "zone_city_docks", "loc_drydock_shipyard", "armor_merchant", "day"),
    # zone_suburbs (3)
    _merch("anom_m_konbini_day", "Suburb Konbini Morning Clerk", "zone_suburbs", "loc_suburb_konbini", "convenience_merchant", "day", hangout_node_id="loc_local_park"),
    _merch("anom_m_konbini_night", "Suburb Konbini Night Cashier", "zone_suburbs", "loc_suburb_konbini", "convenience_merchant", "night", hangout_node_id="loc_local_park"),
    _merch("anom_m_laundry_sundry", "Suburb Coin Laundry Keeper", "zone_suburbs", "loc_suburb_laundry", "general_merchant", "evening", closes_at_22=True),
    # zone_school_campus (2)
    _merch("anom_m_campus_coop", "Campus Co-op Supply Clerk", "zone_school_campus", "loc_school_academic", "school_merchant", "day"),
    _merch("anom_m_courtyard_bento", "Courtyard Bento & Beverage Seller", "zone_school_campus", "loc_school_courtyard", "food_merchant", "day"),
    # zone_seaside_beach (3)
    _merch("anom_m_seaside_cafe", "Seaside Café Grill Proprietor", "zone_seaside_beach", "loc_seaside_cafe", "cafe_merchant", "day", is_unique_proprietor=True),
    _merch("anom_m_pier_tackle", "Coastal Pier Bait & Sundries Clerk", "zone_seaside_beach", "loc_coastal_pier", "general_merchant", "day"),
    _merch("anom_m_themepark_gift", "Boardwalk Souvenir Kiosk Clerk", "zone_seaside_beach", "loc_theme_park", "gift_merchant", "evening", closes_at_22=True),
    # zone_woods_reserve (2)
    _merch("anom_m_ranger_supply", "Ranger Post Trail Supply Clerk", "zone_woods_reserve", "loc_ranger_station", "general_merchant", "day"),
    _merch("anom_m_hilltop_amulet", "Hilltop Shrine Amulet Steward", "zone_woods_reserve", "loc_hilltop_shrine", "accessories_merchant", "day", folklore_pool="shrine"),
    # zone_eastern_sanctuary (3)
    _merch("anom_m_teastreet_prop", "Lantern Tea Street Proprietor", "zone_eastern_sanctuary", "loc_es_lantern_tea_street", "cafe_merchant", "day", is_unique_proprietor=True),
    _merch("anom_m_teastreet_lacquer", "Sanctuary Lacquerware Artisan", "zone_eastern_sanctuary", "loc_es_lantern_tea_street", "gift_merchant", "evening", folklore_pool="shrine", closes_at_22=True),
    _merch("anom_m_temple_wards", "Eastern Temple Ward Apothecary", "zone_eastern_sanctuary", "loc_eastern_temple", "magic_merchant", "day", folklore_pool="shrine"),
    # zone_airport (3)
    _merch("anom_m_ap_dutyfree", "Airport Duty-Free Concierge", "zone_airport", "loc_ap_passenger_terminal", "brand_clothes_merchant", "day"),
    _merch("anom_m_ap_red_eye", "Terminal Red-Eye Travel Cashier", "zone_airport", "loc_ap_passenger_terminal", "convenience_merchant", "night"),
    _merch("anom_m_ap_skyline", "Skyline Lounge Mixologist", "zone_airport", "loc_ap_skyline_lounge", "nightclub_merchant", "evening"),
    # zone_university (2)
    _merch("anom_m_uni_union_day", "Student Union Bookshop Barista", "zone_university", "loc_uni_student_union", "cafe_merchant", "day"),
    _merch("anom_m_uni_union_eve", "Student Union Late-Night Kiosk", "zone_university", "loc_uni_student_union", "convenience_merchant", "evening"),
    # zone_chinatown (3)
    _merch("anom_m_ct_market_chef", "Chinatown Night Market Wok Chef", "zone_chinatown", "loc_ct_night_market", "night_market_merchant", "evening", is_unique_proprietor=True),
    _merch("anom_m_ct_apothecary_prop", "Herbal Apothecary Master", "zone_chinatown", "loc_ct_herbal_apothecary", "potion_merchant", "day", is_unique_proprietor=True, folklore_pool="urban_market"),
    _merch("anom_m_ct_apothecary_app", "Herbal Apothecary Mixer", "zone_chinatown", "loc_ct_herbal_apothecary", "potion_merchant", "evening", folklore_pool="urban_market", closes_at_22=True),
    # zone_undercity (1)
    _merch("anom_m_uc_bazaar", "Drifter Bazaar Salvage Peddler", "zone_undercity", "loc_uc_drifter_bazaar", "general_merchant", "night", is_unique_proprietor=True),
)

# ---------------------------------------------------------------------------
# ANOMALOUS INCURSIONS (+ AHS): 32 CIVIC & INSTITUTIONAL STAFF
# ---------------------------------------------------------------------------
ANOMALOUS_CIVIC_STAFF: tuple[dict[str, Any], ...] = (
    _civic("anom_c_cityhall_day", "Municipal Permits Registrar", "zone_city_center", "loc_municipal_city_hall", "day", hangout_node_id="loc_sunken_plaza"),
    _civic("anom_c_cityhall_arch", "City Hall Records Archivist", "zone_city_center", "loc_municipal_city_hall", "evening", hangout_node_id="loc_uptown_roastery"),
    _civic("anom_c_hosp_er_day", "General Hospital ER Intake Nurse", "zone_city_center", "loc_general_hospital", "day"),
    _civic("anom_c_hosp_night", "General Hospital Night Triage Medic", "zone_city_center", "loc_general_hospital", "night"),
    _civic("anom_c_cinema_proj", "Static Cinema Projectionist", "zone_downtown", "loc_static_cinema", "evening", hangout_node_id="loc_downtown_ramen_alley"),
    _civic("anom_c_jazz_bouncer", "Jazz Bar Door Steward", "zone_downtown", "loc_downtown_jazz_bar", "night"),
    _civic("anom_c_museum_docent", "Uptown Museum Exhibition Docent", "zone_uptown", "loc_uptown_museum", "day"),
    _civic("anom_c_zoo_keeper", "Botanical Zoo Conservatory Keeper", "zone_uptown", "loc_botanical_zoo", "day"),
    _civic("anom_c_cathedral_verger", "Historic Cathedral Verger", "zone_uptown", "loc_historic_cathedral", "evening"),
    _civic("anom_c_elysium_concierge", "Elysium Country Club Concierge", "zone_ultra_rich", "loc_elysium_country_club", "day"),
    _civic("anom_c_promenade_sec", "Sovereign Promenade Private Guard", "zone_ultra_rich", "loc_sovereign_promenade", "evening"),
    _civic("anom_c_clinic_paramedic", "Ward Clinic On-Call Paramedic", "zone_low_cost_wards", "loc_community_clinic", "evening"),
    _civic("anom_c_fight_medic", "Fight Ring Corner Cutman", "zone_low_cost_wards", "loc_underground_fight_ring", "night"),
    _civic("anom_c_substation_eng", "Power Substation Grid Engineer", "zone_industrial", "loc_power_substation", "day"),
    _civic("anom_c_foundry_foreman", "Steel Foundry Floor Foreman", "zone_industrial", "loc_steel_foundry", "day"),
    _civic("anom_c_chem_safety", "Chemical Plant Hazmat Monitor", "zone_industrial", "loc_chemical_plant", "evening"),
    _civic("anom_c_customs_insp", "Harbor Customs Cargo Inspector", "zone_city_docks", "loc_harbor_customs", "day"),
    _civic("anom_c_drydock_pilot", "Drydock Tide & Pilot Coordinator", "zone_city_docks", "loc_drydock_shipyard", "evening"),
    _civic("anom_c_suburb_warden", "Local Park Groundskeeper", "zone_suburbs", "loc_local_park", "day"),
    _civic("anom_c_campus_guard", "Campus Courtyard Gate Warden", "zone_school_campus", "loc_school_courtyard", "day"),
    _civic("anom_c_campus_nurse", "Campus Infirmary Nurse", "zone_school_campus", "loc_school_academic", "day"),
    _civic("anom_c_harbormaster", "Coastal Pier Harbormaster", "zone_seaside_beach", "loc_coastal_pier", "day"),
    _civic("anom_c_lifeguard", "Sandy Beach Lifeguard Captain", "zone_seaside_beach", "loc_sandy_beach", "day"),
    _civic("anom_c_ranger", "Woods Reserve Trail Ranger", "zone_woods_reserve", "loc_ranger_station", "day"),
    _civic("anom_c_sanctuary_gardener", "Footbath Bridge Groundskeeper", "zone_eastern_sanctuary", "loc_es_bamboo_footbath_bridge", "day"),
    _civic("anom_c_ap_atc", "Airport Tower Flight Controller", "zone_airport", "loc_ap_control_tower", "day"),
    _civic("anom_c_ap_hangar", "Cargo Hangar Logistics Marshal", "zone_airport", "loc_ap_cargo_hangars", "night"),
    _civic("anom_c_uni_librarian", "Clocktower Library Reference Librarian", "zone_university", "loc_uni_clocktower_library", "day"),
    _civic("anom_c_uni_obs", "Leyline Observatory Instrument Tech", "zone_university", "loc_uni_leyline_observatory", "evening"),
    _civic("anom_c_uni_parapsych", "Parapsychology Lab Assistant", "zone_university", "loc_uni_parapsych_lab", "day"),
    _civic("anom_c_opera_stagehand", "Chinatown Paper Opera Stagehand", "zone_chinatown", "loc_ct_paper_opera", "evening", culture_hint="east_asian"),
    _civic("anom_c_uc_stationmaster", "Forgotten Metro Tunnel Watchman", "zone_undercity", "loc_uc_forgotten_metro", "evening"),
)

# ---------------------------------------------------------------------------
# ANOMALOUS INCURSIONS (+ AHS): 6 ROAMING STREET VENDORS (4 day + 2 nocturnal contraband)
# ---------------------------------------------------------------------------
ANOMALOUS_STREET_VENDORS: tuple[dict[str, Any], ...] = (
    _vendor(
        "anom_v_espresso_trike",
        "Pour-Over Espresso Trike Barista",
        "zone_city_center",
        ("loc_sunken_plaza", "loc_uptown_roastery", "loc_uni_academic_quad", "loc_sovereign_promenade"),
        "cafe_merchant",
    ),
    _vendor(
        "anom_v_harbor_skewers",
        "Harbor Takoyaki & Skewer Cart Cook",
        "zone_city_docks",
        ("loc_harbor_fish_market", "loc_downtown_ramen_alley", "loc_coastal_pier", "loc_sandy_beach"),
        "food_merchant",
    ),
    _vendor(
        "anom_v_commuter_bento",
        "Commuter Plaza Bento Van Vendor",
        "zone_city_center",
        ("loc_metro_transit_terminal", "loc_school_courtyard", "loc_uni_student_union", "loc_local_park"),
        "convenience_merchant",
    ),
    _vendor(
        "anom_v_botanical_charms",
        "Flower & Lucky Charm Pushcart Seller",
        "zone_uptown",
        ("loc_botanical_zoo", "loc_es_lantern_tea_street", "loc_uptown_museum", "loc_theme_park"),
        "gift_merchant",
    ),
    # 2 Nocturnal / Backstreet Talisman & Contraband Peddlers (active 19:00 - 03:00)
    _vendor(
        "anom_v_night_talisman",
        "Midnight Cinnabar & Ward Peddler",
        "zone_chinatown",
        ("loc_ct_night_market", "loc_backstreet_black_market", "loc_uc_drifter_bazaar", "loc_es_lantern_tea_street"),
        "magic_merchant",
        nocturnal=True,
        contraband=True,
        folklore_pool="shrine",
        culture_hint="east_asian",
    ),
    _vendor(
        "anom_v_dead_drop_tinker",
        "Backstreet Dead-Drop & Talisman Tinker",
        "zone_low_cost_wards",
        ("loc_uc_forgotten_metro", "loc_rusty_pipe_bar", "loc_backstreet_black_market", "loc_rail_freight_yard"),
        "potion_merchant",
        nocturnal=True,
        contraband=True,
        folklore_pool="urban_market",
    ),
)

# ---------------------------------------------------------------------------
# ANOMALOUS INCURSIONS: 102 ROAMING CIVILIANS / PEDESTRIANS
# Compact specs: (slot_id, role, zone_id, weekday_route, weekend_route, age_group, culture, gender)
# ---------------------------------------------------------------------------
_ANOM_PED_SPECS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...], str, str, str], ...] = (
    # zone_city_center (8)
    ("anom_p_cc_1", "Morning Rail Commuter", "zone_city_center", ("loc_metro_transit_terminal", "loc_sunken_plaza", "loc_municipal_city_hall", "loc_downtown_ramen_alley"), ("loc_sunken_plaza", "loc_uptown_museum", "loc_local_park"), "adult", "", ""),
    ("anom_p_cc_2", "Municipal Tax Accountant", "zone_city_center", ("loc_sunken_plaza", "loc_municipal_city_hall", "loc_uptown_roastery", "loc_metro_transit_terminal"), ("loc_uptown_roastery", "loc_botanical_zoo", "loc_downtown_shopping_arcade"), "adult", "", ""),
    ("anom_p_cc_3", "Metro Express Bike Courier", "zone_city_center", ("loc_metro_transit_terminal", "loc_downtown_shopping_arcade", "loc_sovereign_promenade", "loc_rail_freight_yard"), ("loc_coastal_pier", "loc_sunken_plaza", "loc_harbor_fish_market"), "young_adult", "", ""),
    ("anom_p_cc_4", "Off-Duty Hospital Resident", "zone_city_center", ("loc_general_hospital", "loc_sunken_plaza", "loc_uptown_roastery", "loc_local_park"), ("loc_es_bamboo_footbath_bridge", "loc_uptown_roastery", "loc_local_park"), "adult", "", ""),
    ("anom_p_cc_5", "Freelance Metro Journalist", "zone_city_center", ("loc_sunken_plaza", "loc_municipal_city_hall", "loc_downtown_jazz_bar", "loc_metro_transit_terminal"), ("loc_ct_night_market", "loc_uptown_museum", "loc_downtown_jazz_bar"), "adult", "", ""),
    ("anom_p_cc_6", "Plaza Busker Violinist", "zone_city_center", ("loc_sunken_plaza", "loc_metro_transit_terminal", "loc_downtown_shopping_arcade", "loc_ct_night_market"), ("loc_sunken_plaza", "loc_coastal_pier", "loc_theme_park"), "young_adult", "", ""),
    ("anom_p_cc_7", "Antique Appraiser", "zone_city_center", ("loc_occult_curio_shop", "loc_uptown_museum", "loc_crimson_auction_house", "loc_sunken_plaza"), ("loc_ct_herbal_apothecary", "loc_occult_curio_shop", "loc_uptown_roastery"), "elder", "", ""),
    ("anom_p_cc_8", "Night-Shift Janitorial Lead", "zone_city_center", ("loc_suburb_konbini", "loc_municipal_city_hall", "loc_general_hospital", "loc_metro_transit_terminal"), ("loc_rusty_pipe_bar", "loc_harbor_fish_market", "loc_local_park"), "adult", "", ""),
    # zone_downtown (8)
    ("anom_p_dt_1", "Downtown Pastry Shopper", "zone_downtown", ("loc_downtown_shopping_arcade", "loc_uptown_roastery", "loc_sunken_plaza", "loc_suburb_konbini"), ("loc_downtown_shopping_arcade", "loc_sandy_beach", "loc_theme_park"), "adult", "", ""),
    ("anom_p_dt_2", "Indie Film Critic", "zone_downtown", ("loc_static_cinema", "loc_downtown_game_arcade", "loc_downtown_ramen_alley", "loc_downtown_jazz_bar"), ("loc_static_cinema", "loc_uptown_museum", "loc_downtown_jazz_bar"), "young_adult", "", ""),
    ("anom_p_dt_3", "Arcade Fighting-Game Regular", "zone_downtown", ("loc_downtown_game_arcade", "loc_downtown_ramen_alley", "loc_downtown_shopping_arcade", "loc_metro_transit_terminal"), ("loc_downtown_game_arcade", "loc_ct_night_market", "loc_theme_park"), "young_adult", "", ""),
    ("anom_p_dt_4", "Jazz Vinyl Collector", "zone_downtown", ("loc_downtown_shopping_arcade", "loc_occult_curio_shop", "loc_downtown_jazz_bar", "loc_sunken_plaza"), ("loc_downtown_jazz_bar", "loc_uptown_roastery", "loc_ct_paper_opera"), "adult", "", ""),
    ("anom_p_dt_5", "Late-Night Ramen Regular", "zone_downtown", ("loc_metro_transit_terminal", "loc_downtown_ramen_alley", "loc_velvet_mirage_club", "loc_suburb_konbini"), ("loc_downtown_ramen_alley", "loc_ct_night_market", "loc_red_lantern_lounge"), "adult", "", ""),
    ("anom_p_dt_6", "Graphic Design Freelancer", "zone_downtown", ("loc_uptown_roastery", "loc_downtown_shopping_arcade", "loc_static_cinema", "loc_downtown_ramen_alley"), ("loc_botanical_zoo", "loc_seaside_cafe", "loc_downtown_shopping_arcade"), "young_adult", "", ""),
    ("anom_p_dt_7", "Club Lighting Technician", "zone_downtown", ("loc_downtown_game_arcade", "loc_velvet_mirage_club", "loc_red_lantern_lounge", "loc_downtown_ramen_alley"), ("loc_velvet_mirage_club", "loc_theme_park", "loc_downtown_jazz_bar"), "young_adult", "", ""),
    ("anom_p_dt_8", "City Window-Dresser", "zone_downtown", ("loc_haute_couture_salon", "loc_downtown_shopping_arcade", "loc_sunken_plaza", "loc_uptown_roastery"), ("loc_sovereign_promenade", "loc_downtown_shopping_arcade", "loc_seaside_cafe"), "adult", "", ""),
    # zone_uptown (7)
    ("anom_p_up_1", "Art History Grad Researcher", "zone_uptown", ("loc_uni_clocktower_library", "loc_uptown_museum", "loc_uptown_roastery", "loc_historic_cathedral"), ("loc_uptown_museum", "loc_botanical_zoo", "loc_es_lantern_tea_street"), "young_adult", "", ""),
    ("anom_p_up_2", "Botanical Sketch Artist", "zone_uptown", ("loc_botanical_zoo", "loc_uptown_roastery", "loc_local_park", "loc_uptown_museum"), ("loc_botanical_zoo", "loc_forest_trails", "loc_sandy_beach"), "young_adult", "", ""),
    ("anom_p_up_3", "Cathedral Choir Organist", "zone_uptown", ("loc_historic_cathedral", "loc_uptown_roastery", "loc_uptown_museum", "loc_es_lantern_tea_street"), ("loc_historic_cathedral", "loc_eastern_temple", "loc_ct_paper_opera"), "elder", "", ""),
    ("anom_p_up_4", "Retired Classics Professor", "zone_uptown", ("loc_uptown_roastery", "loc_uni_clocktower_library", "loc_uptown_museum", "loc_local_park"), ("loc_uptown_roastery", "loc_es_bamboo_footbath_bridge", "loc_botanical_zoo"), "elder", "", ""),
    ("anom_p_up_5", "Morning Jogger & Photographer", "zone_uptown", ("loc_local_park", "loc_botanical_zoo", "loc_uptown_roastery", "loc_sunken_plaza"), ("loc_coastal_overlook", "loc_sandy_beach", "loc_botanical_zoo"), "adult", "", ""),
    ("anom_p_up_6", "Orchestra Cellist", "zone_uptown", ("loc_uptown_roastery", "loc_downtown_jazz_bar", "loc_historic_cathedral", "loc_sovereign_promenade"), ("loc_ct_paper_opera", "loc_downtown_jazz_bar", "loc_sky_vip_lounge"), "adult", "", ""),
    ("anom_p_up_7", "Museum Conservation Intern", "zone_uptown", ("loc_uptown_museum", "loc_occult_curio_shop", "loc_uptown_roastery", "loc_metro_transit_terminal"), ("loc_uptown_museum", "loc_ct_herbal_apothecary", "loc_uni_academic_quad"), "young_adult", "", ""),
    # zone_ultra_rich (6)
    ("anom_p_ur_1", "Venture Capital Analyst", "zone_ultra_rich", ("loc_sovereign_promenade", "loc_ap_skyline_lounge", "loc_sky_vip_lounge", "loc_elysium_country_club"), ("loc_elysium_country_club", "loc_haute_couture_salon", "loc_sky_vip_lounge"), "adult", "", ""),
    ("anom_p_ur_2", "Runway Lookbook Model", "zone_ultra_rich", ("loc_haute_couture_salon", "loc_sovereign_promenade", "loc_uptown_roastery", "loc_velvet_mirage_club"), ("loc_haute_couture_salon", "loc_seaside_cafe", "loc_sky_vip_lounge"), "young_adult", "", "female"),
    ("anom_p_ur_3", "Fine-Art Estate Bidder", "zone_ultra_rich", ("loc_crimson_auction_house", "loc_uptown_museum", "loc_sovereign_promenade", "loc_sky_vip_lounge"), ("loc_crimson_auction_house", "loc_elysium_country_club", "loc_es_lantern_tea_street"), "elder", "", ""),
    ("anom_p_ur_4", "Chauffeur on Standby", "zone_ultra_rich", ("loc_sovereign_promenade", "loc_elysium_country_club", "loc_ap_passenger_terminal", "loc_sky_vip_lounge"), ("loc_sovereign_promenade", "loc_ap_passenger_terminal", "loc_downtown_ramen_alley"), "adult", "", ""),
    ("anom_p_ur_5", "Private Gala Violinist", "zone_ultra_rich", ("loc_elysium_country_club", "loc_sovereign_promenade", "loc_crimson_auction_house", "loc_downtown_jazz_bar"), ("loc_elysium_country_club", "loc_historic_cathedral", "loc_sky_vip_lounge"), "adult", "", ""),
    ("anom_p_ur_6", "Tech Patent Attorney", "zone_ultra_rich", ("loc_municipal_city_hall", "loc_sovereign_promenade", "loc_elysium_country_club", "loc_downtown_jazz_bar"), ("loc_elysium_country_club", "loc_botanical_zoo", "loc_crimson_auction_house"), "adult", "", ""),
    # zone_low_cost_wards (7)
    ("anom_p_lc_1", "Back-Alley Locksmith", "zone_low_cost_wards", ("loc_backstreet_black_market", "loc_rusty_pipe_bar", "loc_suburb_laundry", "loc_rail_freight_yard"), ("loc_backstreet_black_market", "loc_uc_drifter_bazaar", "loc_rusty_pipe_bar"), "adult", "", ""),
    ("anom_p_lc_2", "Amateur Welterweight Boxer", "zone_low_cost_wards", ("loc_ct_martial_dojo", "loc_local_park", "loc_underground_fight_ring", "loc_rusty_pipe_bar"), ("loc_underground_fight_ring", "loc_coastal_pier", "loc_rusty_pipe_bar"), "young_adult", "", ""),
    ("anom_p_lc_3", "Night-Shift Delivery Driver", "zone_low_cost_wards", ("loc_rail_freight_yard", "loc_harbor_fish_market", "loc_rusty_pipe_bar", "loc_red_lantern_lounge"), ("loc_ct_night_market", "loc_rusty_pipe_bar", "loc_downtown_ramen_alley"), "adult", "", ""),
    ("anom_p_lc_4", "Ward Social Worker", "zone_low_cost_wards", ("loc_community_clinic", "loc_municipal_city_hall", "loc_suburb_laundry", "loc_sunken_plaza"), ("loc_community_clinic", "loc_local_park", "loc_harbor_fish_market"), "adult", "", ""),
    ("anom_p_lc_5", "Scrap Copper Collector", "zone_low_cost_wards", ("loc_backstreet_black_market", "loc_uc_drifter_bazaar", "loc_rail_freight_yard", "loc_rusty_pipe_bar"), ("loc_uc_drifter_bazaar", "loc_harbor_fish_market", "loc_backstreet_black_market"), "elder", "", ""),
    ("anom_p_lc_6", "Off-Hours Lounge Singer", "zone_low_cost_wards", ("loc_suburb_konbini", "loc_downtown_jazz_bar", "loc_red_lantern_lounge", "loc_downtown_ramen_alley"), ("loc_red_lantern_lounge", "loc_velvet_mirage_club", "loc_ct_paper_opera"), "young_adult", "", ""),
    ("anom_p_lc_7", "Fight Ring Oddsmaker", "zone_low_cost_wards", ("loc_rusty_pipe_bar", "loc_ct_mahjong_parlor", "loc_underground_fight_ring", "loc_backstreet_black_market"), ("loc_underground_fight_ring", "loc_ct_mahjong_parlor", "loc_red_lantern_lounge"), "adult", "", ""),
    # zone_industrial (6)
    ("anom_p_in_1", "High-Voltage Line Tech", "zone_industrial", ("loc_power_substation", "loc_rail_freight_yard", "loc_rusty_pipe_bar", "loc_suburb_konbini"), ("loc_harbor_fish_market", "loc_rusty_pipe_bar", "loc_local_park"), "adult", "", ""),
    ("anom_p_in_2", "Steel Foundry Crane Operator", "zone_industrial", ("loc_steel_foundry", "loc_rail_freight_yard", "loc_rusty_pipe_bar", "loc_downtown_ramen_alley"), ("loc_coastal_pier", "loc_downtown_ramen_alley", "loc_rusty_pipe_bar"), "adult", "", ""),
    ("anom_p_in_3", "Freight Dispatch Clerk", "zone_industrial", ("loc_rail_freight_yard", "loc_container_pier", "loc_metro_transit_terminal", "loc_suburb_konbini"), ("loc_container_pier", "loc_downtown_game_arcade", "loc_downtown_ramen_alley"), "adult", "", ""),
    ("anom_p_in_4", "Chemical Solvent Analyst", "zone_industrial", ("loc_chemical_plant", "loc_uni_parapsych_lab", "loc_uptown_roastery", "loc_sunken_plaza"), ("loc_botanical_zoo", "loc_uptown_roastery", "loc_static_cinema"), "adult", "", ""),
    ("anom_p_in_5", "Diesel Locomotive Machinist", "zone_industrial", ("loc_rail_freight_yard", "loc_power_substation", "loc_drydock_shipyard", "loc_rusty_pipe_bar"), ("loc_harbor_fish_market", "loc_rail_freight_yard", "loc_ct_night_market"), "elder", "", ""),
    ("anom_p_in_6", "Industrial Union Shop Steward", "zone_industrial", ("loc_steel_foundry", "loc_chemical_plant", "loc_municipal_city_hall", "loc_rusty_pipe_bar"), ("loc_local_park", "loc_rusty_pipe_bar", "loc_harbor_fish_market"), "adult", "", ""),
    # zone_city_docks (7)
    ("anom_p_dk_1", "Morning Tuna Auction Buyer", "zone_city_docks", ("loc_harbor_fish_market", "loc_downtown_ramen_alley", "loc_container_pier", "loc_ct_night_market"), ("loc_harbor_fish_market", "loc_coastal_pier", "loc_ct_night_market"), "adult", "", ""),
    ("anom_p_dk_2", "Container Crane Signalman", "zone_city_docks", ("loc_container_pier", "loc_harbor_customs", "loc_harbor_fish_market", "loc_rusty_pipe_bar"), ("loc_coastal_pier", "loc_sandy_beach", "loc_harbor_fish_market"), "adult", "", ""),
    ("anom_p_dk_3", "Drydock Hull Welder", "zone_city_docks", ("loc_drydock_shipyard", "loc_container_pier", "loc_harbor_fish_market", "loc_downtown_ramen_alley"), ("loc_coastal_pier", "loc_downtown_ramen_alley", "loc_theme_park"), "adult", "", ""),
    ("anom_p_dk_4", "Maritime Freight Broker", "zone_city_docks", ("loc_harbor_customs", "loc_ap_cargo_hangars", "loc_sunken_plaza", "loc_downtown_jazz_bar"), ("loc_seaside_cafe", "loc_coastal_pier", "loc_downtown_jazz_bar"), "adult", "", ""),
    ("anom_p_dk_5", "Harbor Ferry Deckhand", "zone_city_docks", ("loc_container_pier", "loc_coastal_pier", "loc_harbor_fish_market", "loc_seaside_cafe"), ("loc_coastal_pier", "loc_sandy_beach", "loc_seaside_cafe"), "young_adult", "", ""),
    ("anom_p_dk_6", "Old Tugboat Skipper", "zone_city_docks", ("loc_harbor_fish_market", "loc_drydock_shipyard", "loc_coastal_pier", "loc_rusty_pipe_bar"), ("loc_coastal_pier", "loc_harbor_fish_market", "loc_coastal_overlook"), "elder", "", ""),
    ("anom_p_dk_7", "Seafood Stall Delivery Runner", "zone_city_docks", ("loc_harbor_fish_market", "loc_ct_night_market", "loc_downtown_ramen_alley", "loc_metro_transit_terminal"), ("loc_harbor_fish_market", "loc_ct_night_market", "loc_downtown_game_arcade"), "young_adult", "", ""),
    # zone_suburbs (6)
    ("anom_p_sb_1", "Morning Dog-Walking Retiree", "zone_suburbs", ("loc_local_park", "loc_suburb_konbini", "loc_suburb_laundry", "loc_sunken_plaza"), ("loc_local_park", "loc_es_bamboo_footbath_bridge", "loc_botanical_zoo"), "elder", "", ""),
    ("anom_p_sb_2", "Suburban Homemaker Shopper", "zone_suburbs", ("loc_suburb_konbini", "loc_local_park", "loc_downtown_shopping_arcade", "loc_suburb_laundry"), ("loc_harbor_fish_market", "loc_downtown_shopping_arcade", "loc_local_park"), "adult", "", ""),
    ("anom_p_sb_3", "Evening Marathon Runner", "zone_suburbs", ("loc_local_park", "loc_coastal_overlook", "loc_suburb_konbini", "loc_downtown_ramen_alley"), ("loc_forest_trails", "loc_sandy_beach", "loc_local_park"), "young_adult", "", ""),
    ("anom_p_sb_4", "Prep-School Cram Tutor", "zone_suburbs", ("loc_metro_transit_terminal", "loc_school_courtyard", "loc_suburb_konbini", "loc_uptown_roastery"), ("loc_uni_clocktower_library", "loc_uptown_roastery", "loc_static_cinema"), "adult", "", ""),
    ("anom_p_sb_5", "Apartment Maintenance Handyman", "zone_suburbs", ("loc_suburb_laundry", "loc_suburb_konbini", "loc_backstreet_black_market", "loc_local_park"), ("loc_suburb_laundry", "loc_ct_night_market", "loc_rusty_pipe_bar"), "adult", "", ""),
    ("anom_p_sb_6", "Freelance Translator Neighbor", "zone_suburbs", ("loc_suburb_konbini", "loc_uptown_roastery", "loc_uni_clocktower_library", "loc_local_park"), ("loc_uptown_roastery", "loc_es_lantern_tea_street", "loc_static_cinema"), "adult", "", ""),
    # zone_school_campus (5)
    ("anom_p_sc_1", "Academy Choir Sophomore", "zone_school_campus", ("loc_school_courtyard", "loc_school_academic", "loc_downtown_shopping_arcade", "loc_suburb_konbini"), ("loc_downtown_shopping_arcade", "loc_downtown_game_arcade", "loc_seaside_cafe"), "young_adult", "", ""),
    ("anom_p_sc_2", "Track Team Sprinter", "zone_school_campus", ("loc_school_athletics", "loc_school_courtyard", "loc_downtown_ramen_alley", "loc_local_park"), ("loc_sandy_beach", "loc_local_park", "loc_theme_park"), "young_adult", "", ""),
    ("anom_p_sc_3", "School Press Photographer", "zone_school_campus", ("loc_school_courtyard", "loc_school_clubs", "loc_sunken_plaza", "loc_downtown_shopping_arcade"), ("loc_botanical_zoo", "loc_coastal_pier", "loc_ct_night_market"), "young_adult", "", ""),
    ("anom_p_sc_4", "Honor-Roll Cram Commuter", "zone_school_campus", ("loc_metro_transit_terminal", "loc_school_academic", "loc_uni_clocktower_library", "loc_suburb_konbini"), ("loc_uni_clocktower_library", "loc_uptown_roastery", "loc_suburb_konbini"), "young_adult", "", ""),
    ("anom_p_sc_5", "After-School Skate Trio Regular", "zone_school_campus", ("loc_school_courtyard", "loc_downtown_game_arcade", "loc_sunken_plaza", "loc_sandy_beach"), ("loc_theme_park", "loc_sandy_beach", "loc_downtown_game_arcade"), "young_adult", "", ""),
    # zone_seaside_beach (6)
    ("anom_p_ss_1", "Dawn Reef Surfer", "zone_seaside_beach", ("loc_sandy_beach", "loc_seaside_cafe", "loc_coastal_pier", "loc_downtown_ramen_alley"), ("loc_sandy_beach", "loc_seaside_cafe", "loc_coastal_overlook"), "young_adult", "", ""),
    ("anom_p_ss_2", "Boardwalk Balloon Artist", "zone_seaside_beach", ("loc_theme_park", "loc_coastal_pier", "loc_sandy_beach", "loc_seaside_cafe"), ("loc_theme_park", "loc_botanical_zoo", "loc_coastal_pier"), "adult", "", ""),
    ("anom_p_ss_3", "Sunset Birdwatcher", "zone_seaside_beach", ("loc_coastal_overlook", "loc_coastal_pier", "loc_seaside_cafe", "loc_sandy_beach"), ("loc_coastal_overlook", "loc_summit_lookout", "loc_seaside_cafe"), "elder", "", ""),
    ("anom_p_ss_4", "Pier Line Fisherman", "zone_seaside_beach", ("loc_coastal_pier", "loc_harbor_fish_market", "loc_seaside_cafe", "loc_sandy_beach"), ("loc_coastal_pier", "loc_sandy_beach", "loc_harbor_fish_market"), "elder", "", ""),
    ("anom_p_ss_5", "Marine Biology Field Student", "zone_seaside_beach", ("loc_sandy_beach", "loc_coastal_pier", "loc_uni_academic_quad", "loc_seaside_cafe"), ("loc_sandy_beach", "loc_coastal_pier", "loc_botanical_zoo"), "young_adult", "", ""),
    ("anom_p_ss_6", "Weekend Tourist Couple Escort", "zone_seaside_beach", ("loc_ap_passenger_terminal", "loc_seaside_cafe", "loc_theme_park", "loc_coastal_overlook"), ("loc_theme_park", "loc_es_lantern_tea_street", "loc_coastal_overlook"), "adult", "", ""),
    # zone_woods_reserve (5)
    ("anom_p_wd_1", "Mycology Forager", "zone_woods_reserve", ("loc_forest_trails", "loc_ranger_station", "loc_mountain_campsite", "loc_hilltop_shrine"), ("loc_forest_trails", "loc_ct_herbal_apothecary", "loc_mountain_campsite"), "elder", "", ""),
    ("anom_p_wd_2", "Landscape Watercolorist", "zone_woods_reserve", ("loc_summit_lookout", "loc_mountain_campsite", "loc_hilltop_shrine", "loc_uptown_roastery"), ("loc_summit_lookout", "loc_coastal_overlook", "loc_es_bamboo_footbath_bridge"), "adult", "", ""),
    ("anom_p_wd_3", "Backpack Trail Hiker", "zone_woods_reserve", ("loc_ranger_station", "loc_forest_trails", "loc_summit_lookout", "loc_mountain_campsite"), ("loc_forest_trails", "loc_mountain_campsite", "loc_es_bamboo_footbath_bridge"), "young_adult", "", ""),
    ("anom_p_wd_4", "Shrine Trail Pilgrim", "zone_woods_reserve", ("loc_hilltop_shrine", "loc_eastern_temple", "loc_es_lantern_tea_street", "loc_metro_transit_terminal"), ("loc_hilltop_shrine", "loc_eastern_temple", "loc_historic_cathedral"), "elder", "", ""),
    ("anom_p_wd_5", "Astrophotography Hobbyist", "zone_woods_reserve", ("loc_uptown_roastery", "loc_summit_lookout", "loc_uni_leyline_observatory", "loc_mountain_campsite"), ("loc_summit_lookout", "loc_coastal_overlook", "loc_uni_leyline_observatory"), "adult", "", ""),
    # zone_eastern_sanctuary (5)
    ("anom_p_es_1", "Tea Ceremony Apprentice", "zone_eastern_sanctuary", ("loc_es_lantern_tea_street", "loc_eastern_temple", "loc_es_bamboo_footbath_bridge", "loc_uptown_museum"), ("loc_es_lantern_tea_street", "loc_eastern_temple", "loc_hilltop_shrine"), "young_adult", "east_asian", ""),
    ("anom_p_es_2", "Calligraphy Scroll Collector", "zone_eastern_sanctuary", ("loc_eastern_temple", "loc_es_lantern_tea_street", "loc_ct_herbal_apothecary", "loc_occult_curio_shop"), ("loc_es_lantern_tea_street", "loc_ct_paper_opera", "loc_uptown_museum"), "elder", "east_asian", ""),
    ("anom_p_es_3", "Sanctuary Footbath Regular", "zone_eastern_sanctuary", ("loc_es_bamboo_footbath_bridge", "loc_es_lantern_tea_street", "loc_eastern_temple", "loc_local_park"), ("loc_es_bamboo_footbath_bridge", "loc_mountain_campsite", "loc_es_lantern_tea_street"), "adult", "", ""),
    ("anom_p_es_4", "Bamboo Flute Busker", "zone_eastern_sanctuary", ("loc_es_bamboo_footbath_bridge", "loc_es_lantern_tea_street", "loc_sunken_plaza", "loc_ct_night_market"), ("loc_es_bamboo_footbath_bridge", "loc_hilltop_shrine", "loc_ct_night_market"), "adult", "east_asian", ""),
    ("anom_p_es_5", "Sanctuary Pilgrim Tourist", "zone_eastern_sanctuary", ("loc_ap_passenger_terminal", "loc_eastern_temple", "loc_es_lantern_tea_street", "loc_es_bamboo_footbath_bridge"), ("loc_eastern_temple", "loc_theme_park", "loc_uptown_museum"), "adult", "", ""),
    # zone_airport (5)
    ("anom_p_ap_1", "Long-Haul Cabin Attendant", "zone_airport", ("loc_ap_passenger_terminal", "loc_ap_skyline_lounge", "loc_sovereign_promenade", "loc_downtown_shopping_arcade"), ("loc_seaside_cafe", "loc_es_bamboo_footbath_bridge", "loc_downtown_jazz_bar"), "young_adult", "", ""),
    ("anom_p_ap_2", "Charter Pilot Off-Duty", "zone_airport", ("loc_ap_control_tower", "loc_ap_skyline_lounge", "loc_ap_passenger_terminal", "loc_elysium_country_club"), ("loc_coastal_overlook", "loc_ap_skyline_lounge", "loc_downtown_jazz_bar"), "adult", "", ""),
    ("anom_p_ap_3", "Import Cargo Customs Broker", "zone_airport", ("loc_ap_cargo_hangars", "loc_harbor_customs", "loc_ap_passenger_terminal", "loc_downtown_ramen_alley"), ("loc_ct_night_market", "loc_harbor_fish_market", "loc_downtown_ramen_alley"), "adult", "", ""),
    ("anom_p_ap_4", "Jet-Lagged Exchange Scholar", "zone_airport", ("loc_ap_passenger_terminal", "loc_metro_transit_terminal", "loc_uni_academic_quad", "loc_uni_student_union"), ("loc_uptown_museum", "loc_uni_academic_quad", "loc_ct_night_market"), "young_adult", "", ""),
    ("anom_p_ap_5", "Runway Ground Crew Tech", "zone_airport", ("loc_ap_cargo_hangars", "loc_ap_passenger_terminal", "loc_power_substation", "loc_rusty_pipe_bar"), ("loc_downtown_game_arcade", "loc_rusty_pipe_bar", "loc_harbor_fish_market"), "adult", "", ""),
    # zone_university (8)
    ("anom_p_un_1", "Linguistics Thesis Doctoral Student", "zone_university", ("loc_uni_clocktower_library", "loc_uni_academic_quad", "loc_uni_student_union", "loc_uptown_roastery"), ("loc_uptown_museum", "loc_es_lantern_tea_street", "loc_static_cinema"), "young_adult", "", ""),
    ("anom_p_un_2", "Astrophysics Undergrad", "zone_university", ("loc_uni_leyline_observatory", "loc_uni_academic_quad", "loc_uni_clocktower_library", "loc_downtown_ramen_alley"), ("loc_summit_lookout", "loc_uni_leyline_observatory", "loc_downtown_game_arcade"), "young_adult", "", ""),
    ("anom_p_un_3", "Folklore Seminar TA", "zone_university", ("loc_uni_parapsych_lab", "loc_uni_clocktower_library", "loc_occult_curio_shop", "loc_eastern_temple"), ("loc_ct_paper_opera", "loc_hilltop_shrine", "loc_occult_curio_shop"), "adult", "", ""),
    ("anom_p_un_4", "Campus Debate Society Captain", "zone_university", ("loc_uni_student_union", "loc_uni_academic_quad", "loc_municipal_city_hall", "loc_uptown_roastery"), ("loc_uni_student_union", "loc_sunken_plaza", "loc_downtown_jazz_bar"), "young_adult", "", ""),
    ("anom_p_un_5", "Student Radio DJ", "zone_university", ("loc_uni_student_union", "loc_downtown_shopping_arcade", "loc_downtown_jazz_bar", "loc_velvet_mirage_club"), ("loc_downtown_jazz_bar", "loc_static_cinema", "loc_ct_night_market"), "young_adult", "", ""),
    ("anom_p_un_6", "Late-Night Architecture Senior", "zone_university", ("loc_uni_academic_quad", "loc_uni_clocktower_library", "loc_uni_student_union", "loc_suburb_konbini"), ("loc_sunken_plaza", "loc_historic_cathedral", "loc_downtown_ramen_alley"), "young_adult", "", ""),
    ("anom_p_un_7", "University Bio-Chem Postdoc", "zone_university", ("loc_uni_parapsych_lab", "loc_general_hospital", "loc_uni_student_union", "loc_uptown_roastery"), ("loc_botanical_zoo", "loc_uptown_roastery", "loc_local_park"), "adult", "", ""),
    ("anom_p_un_8", "Visiting Visiting-Faculty Lecturer", "zone_university", ("loc_ap_passenger_terminal", "loc_uni_academic_quad", "loc_uni_clocktower_library", "loc_sky_vip_lounge"), ("loc_uptown_museum", "loc_es_lantern_tea_street", "loc_historic_cathedral"), "elder", "", ""),
    # zone_chinatown (7)
    ("anom_p_ct_1", "Chinatown Mahjong Hall Regular", "zone_chinatown", ("loc_ct_herbal_apothecary", "loc_ct_mahjong_parlor", "loc_ct_night_market", "loc_ct_paper_opera"), ("loc_ct_mahjong_parlor", "loc_ct_night_market", "loc_es_bamboo_footbath_bridge"), "elder", "east_asian", ""),
    ("anom_p_ct_2", "Wushu Sparring Disciple", "zone_chinatown", ("loc_ct_martial_dojo", "loc_local_park", "loc_ct_night_market", "loc_downtown_ramen_alley"), ("loc_ct_martial_dojo", "loc_underground_fight_ring", "loc_coastal_pier"), "young_adult", "east_asian", ""),
    ("anom_p_ct_3", "Paper Opera Falsetto Soprano", "zone_chinatown", ("loc_ct_paper_opera", "loc_ct_herbal_apothecary", "loc_ct_night_market", "loc_es_lantern_tea_street"), ("loc_ct_paper_opera", "loc_es_lantern_tea_street", "loc_uptown_museum"), "adult", "east_asian", "female"),
    ("anom_p_ct_4", "Night Market Pastry Hawker Regular", "zone_chinatown", ("loc_harbor_fish_market", "loc_ct_night_market", "loc_ct_mahjong_parlor", "loc_sunken_plaza"), ("loc_ct_night_market", "loc_harbor_fish_market", "loc_theme_park"), "adult", "east_asian", ""),
    ("anom_p_ct_5", "Jade Seal Engraver", "zone_chinatown", ("loc_ct_night_market", "loc_occult_curio_shop", "loc_ct_herbal_apothecary", "loc_es_lantern_tea_street"), ("loc_ct_night_market", "loc_es_lantern_tea_street", "loc_crimson_auction_house"), "elder", "east_asian", ""),
    ("anom_p_ct_6", "Neon Alley Street Photographer", "zone_chinatown", ("loc_sunken_plaza", "loc_ct_night_market", "loc_downtown_ramen_alley", "loc_ct_paper_opera"), ("loc_ct_night_market", "loc_coastal_overlook", "loc_static_cinema"), "young_adult", "", ""),
    ("anom_p_ct_7", "Herbal Tea Courier", "zone_chinatown", ("loc_ct_herbal_apothecary", "loc_es_lantern_tea_street", "loc_community_clinic", "loc_ct_night_market"), ("loc_ct_herbal_apothecary", "loc_es_bamboo_footbath_bridge", "loc_forest_trails"), "young_adult", "east_asian", ""),
    # zone_undercity (6)
    ("anom_p_uc_1", "Undercity Lantern Scavenger", "zone_undercity", ("loc_uc_drifter_bazaar", "loc_uc_forgotten_metro", "loc_backstreet_black_market", "loc_rusty_pipe_bar"), ("loc_uc_drifter_bazaar", "loc_backstreet_black_market", "loc_harbor_fish_market"), "adult", "", ""),
    ("anom_p_uc_2", "Forgotten Metro Graffiti Chronicler", "zone_undercity", ("loc_uc_forgotten_metro", "loc_uc_drifter_bazaar", "loc_metro_transit_terminal", "loc_downtown_game_arcade"), ("loc_uc_forgotten_metro", "loc_static_cinema", "loc_ct_night_market"), "young_adult", "", ""),
    ("anom_p_uc_3", "Subterranean Radio Tinker", "zone_undercity", ("loc_uc_drifter_bazaar", "loc_power_substation", "loc_backstreet_black_market", "loc_uc_forgotten_metro"), ("loc_uc_drifter_bazaar", "loc_rail_freight_yard", "loc_backstreet_black_market"), "adult", "", ""),
    ("anom_p_uc_4", "Drift-Market Noodle Peddler Patron", "zone_undercity", ("loc_uc_drifter_bazaar", "loc_rusty_pipe_bar", "loc_ct_night_market", "loc_uc_forgotten_metro"), ("loc_ct_night_market", "loc_uc_drifter_bazaar", "loc_rusty_pipe_bar"), "adult", "", ""),
    ("anom_p_uc_5", "Tunnel Map Cartographer", "zone_undercity", ("loc_uc_forgotten_metro", "loc_uni_clocktower_library", "loc_uc_drifter_bazaar", "loc_sunken_plaza"), ("loc_uc_forgotten_metro", "loc_forest_trails", "loc_occult_curio_shop"), "elder", "", ""),
    ("anom_p_uc_6", "Drifter Bazaar Fortune Teller", "zone_undercity", ("loc_uc_drifter_bazaar", "loc_ct_night_market", "loc_backstreet_black_market", "loc_red_lantern_lounge"), ("loc_uc_drifter_bazaar", "loc_es_lantern_tea_street", "loc_ct_night_market"), "adult", "", ""),
)

ANOMALOUS_PEDESTRIAN_ARCHETYPES: tuple[dict[str, Any], ...] = tuple(
    _ped(s_id, role, z_id, w_rt, weekend_route=we_rt, age_group=ag, culture_hint=cul, gender_hint=gen)
    for s_id, role, z_id, w_rt, we_rt, ag, cul, gen in _ANOM_PED_SPECS
)


# ---------------------------------------------------------------------------
# HIGH SCHOOL DRAMA (+ AHS): 26 EXTRA CAMPUS STUDENTS & STAFF (incl. 5 extra Part-Timers)
# Combined with legacy 6 `STUDENT_PART_TIME_SPECS` -> 11 total HS student shifts!
# ---------------------------------------------------------------------------
HS_EXTRA_CAMPUS_TEMPLATES: tuple[dict[str, Any], ...] = (
    # 5 Student Part-Time Shift Holders (distinct venues -> brings total shifts from 6 to 11!)
    _hs_student(
        "hs_c_pt_diner", "Part-Time Family Diner Waitstaff", "Junior", "Culinary Club",
        "loc_homeroom", "loc_cafeteria",
        part_time_shift={
            "job_title": "Part-Time Diner Server",
            "venue_node_id": "loc_restaurant",
            "weekday_mods": (1, 3, 5), "weekend_mods": (6,),
            "weekday_start": 1020, "weekday_end": 1260,
            "weekend_start": 720, "weekend_end": 1020,
            "shift_activity": "Balancing sizzling trays and iced melon floats across Downtown Diner booths",
        },
    ),
    _hs_student(
        "hs_c_pt_apparel", "Part-Time Streetwear Fold Clerk", "Senior", "Fashion & Sewing Club",
        "loc_homeroom", "loc_courtyard",
        part_time_shift={
            "job_title": "Part-Time Streetwear Clerk",
            "venue_node_id": "loc_clothing_store",
            "weekday_mods": (2, 4), "weekend_mods": (0,),
            "weekday_start": 1020, "weekday_end": 1260,
            "weekend_start": 720, "weekend_end": 1020,
            "shift_activity": "Steaming hoodies and sizing pleated skirts along the Streetwear display rack",
        },
    ),
    _hs_student(
        "hs_c_pt_gift", "Part-Time Curio & Gift Wrapper", "Sophomore", "Fine Arts Club",
        "loc_fine_arts_studio", "loc_courtyard",
        part_time_shift={
            "job_title": "Part-Time Gift Shop Wrapper",
            "venue_node_id": "loc_gift_store",
            "weekday_mods": (1, 3, 5), "weekend_mods": (6,),
            "weekday_start": 1020, "weekday_end": 1260,
            "weekend_start": 720, "weekend_end": 1020,
            "shift_activity": "Tying satin ribbons onto plushies and music boxes behind the Curio & Gift counter",
        },
    ),
    _hs_student(
        "hs_c_pt_bijoux", "Part-Time Bijoux Counter Trainee", "Junior", "Chorus & Ensemble",
        "loc_old_east_music_room", "loc_school_hallway",
        part_time_shift={
            "job_title": "Part-Time Accessories Clerk",
            "venue_node_id": "loc_accessories_store",
            "weekday_mods": (2, 4), "weekend_mods": (0,),
            "weekday_start": 1020, "weekday_end": 1260,
            "weekend_start": 720, "weekend_end": 1020,
            "shift_activity": "Polishing glass display cases and silver charm bracelets at the Accessories counter",
        },
    ),
    _hs_student(
        "hs_c_pt_market", "Part-Time Lantern Stall Helper", "Freshman", "Volunteering Circle",
        "loc_freshman_class", "loc_vending_pavilion",
        part_time_shift={
            "job_title": "Part-Time Night Market Server",
            "venue_node_id": "loc_night_market",
            "weekday_mods": (3, 5), "weekend_mods": (6, 0),
            "weekday_start": 1050, "weekday_end": 1290,
            "weekend_start": 1020, "weekend_end": 1290,
            "shift_activity": "Handing warm taiyaki and yakitori skewers beneath paper lanterns before youth curfew",
        },
    ),
    # 16 Additional Campus Classmates across grades & clubs
    _hs_student("hs_c_s6", "Archery Club Captain", "Senior", "Kyudo Club", "loc_sports_field", "loc_behind_gym_sheds"),
    _hs_student("hs_c_s7", "Broadcast Room Audio Tech", "Junior", "Broadcasting Club", "loc_broadcasting_room", "loc_clubroom_corridor"),
    _hs_student("hs_c_s8", "Greenhouse Botanist", "Sophomore", "Gardening Club", "loc_greenhouse", "loc_courtyard"),
    _hs_student("hs_c_s9", "Kendo Sparring Vice-Captain", "Senior", "Martial Arts Club", "loc_martial_arts_dojo", "loc_gymnasium"),
    _hs_student("hs_c_s10", "Chess & Shogi Strategist", "Freshman", "Board Games Club", "loc_library", "loc_gaming_clubroom"),
    _hs_student("hs_c_s11", "Swim Team Freestyle Ace", "Junior", "Swimming Club", "loc_pool", "loc_vending_pavilion"),
    _hs_student("hs_c_s12", "School Newspaper Columnist", "Sophomore", "Journalism Club", "loc_clubroom_corridor", "loc_cafeteria"),
    _hs_student("hs_c_s13", "Chemistry Lab Monitor", "Senior", "Science Society", "loc_science_lab", "loc_library"),
    _hs_student("hs_c_s14", "Rooftop Sketcher", "Freshman", "Manga & Illustration Club", "loc_freshman_class", "loc_courtyard"),
    _hs_student("hs_c_s15", "Stage Lighting Crew Lead", "Junior", "Drama Club", "loc_auditorium_stage", "loc_clubroom_corridor"),
    _hs_student("hs_c_s16", "Track Relay Anchor", "Sophomore", "Track & Field", "loc_sports_field", "loc_vending_pavilion"),
    _hs_student("hs_c_s17", "Brass Band Trombonist", "Freshman", "Wind Ensemble", "loc_old_east_music_room", "loc_courtyard"),
    _hs_student("hs_c_s18", "Student Council Treasurer Aide", "Junior", "Student Council", "loc_student_council", "loc_library"),
    _hs_student("hs_c_s19", "Delinquent Boiler-Den Lookout", "Sophomore", "Unaffiliated", "loc_sophomore_class", "loc_delinquent_boiler_den"),
    _hs_student("hs_c_s20", "Transfer Exchange Listener", "Senior", "Literature Circle", "loc_senior_class", "loc_library"),
    _hs_student("hs_c_s21", "Bakery Home-Ec Prodigy", "Freshman", "Culinary Club", "loc_freshman_class", "loc_cafeteria"),
    # 5 Campus Support Staff (Adults)
    _civic("hs_staff_gate", "Academy Front Gate Security Guard", "zone_school_main", "loc_school_gate", "day", hangout_node_id="loc_convenience_store"),
    _civic("hs_staff_sous", "Cafeteria Morning Sous-Chef", "zone_school_main", "loc_cafeteria", "day", hangout_node_id="loc_staff_room"),
    _civic("hs_staff_grounds", "Athletic Field Groundskeeper", "zone_school_main", "loc_sports_field", "day", hangout_node_id="loc_behind_gym_sheds"),
    _civic("hs_staff_janitor", "Evening Wing Custodian", "zone_school_main", "loc_school_hallway", "evening", hangout_node_id="loc_entrance_foyer", closes_at_20=True),
    _civic("hs_staff_proctor", "Substitute Study-Hall Proctor", "zone_school_main", "loc_library", "day", hangout_node_id="loc_staff_room"),
)

# ---------------------------------------------------------------------------
# HIGH SCHOOL DRAMA (+ AHS): 12 EXTRA TOWN MERCHANTS/STAFF + 3 MODERN STREET VENDORS
# ---------------------------------------------------------------------------
HS_EXTRA_TOWN_MERCHANTS_AND_VENDORS: tuple[dict[str, Any], ...] = (
    # 12 Town Shop Shift Clerks & Civic Support
    _merch("hs_m_konbini_dawn", "Konbini Early-Morning Baker Clerk", "zone_downtown", "loc_convenience_store", "convenience_merchant", "day"),
    _merch("hs_m_cafe_roast", "Artisan Café Pastry Roaster", "zone_downtown", "loc_cafe", "cafe_merchant", "day"),
    _merch("hs_m_diner_night", "Family Diner Late-Shift Fry Cook", "zone_downtown", "loc_restaurant", "restaurant_merchant", "evening", closes_at_22=True),
    _merch("hs_m_apparel_buyer", "Streetwear Boutique Rack Buyer", "zone_downtown", "loc_clothing_store", "clothes_merchant", "day"),
    _merch("hs_m_luxury_stylist", "Designer Salon Alteration Tailor", "zone_downtown", "loc_brand_clothing_store", "brand_clothes_merchant", "evening", closes_at_22=True),
    _merch("hs_m_bijoux_jeweler", "Accessories Watch & Ring Setter", "zone_downtown", "loc_accessories_store", "accessories_merchant", "day"),
    _merch("hs_m_gift_stationer", "Curio & Plushie Buyer", "zone_downtown", "loc_gift_store", "gift_merchant", "day"),
    _merch("hs_m_market_lantern", "Night Market Candied-Fruit Seller", "zone_downtown", "loc_night_market", "night_market_merchant", "evening", closes_at_22=True),
    _civic("hs_c_arcade_tech", "Arcade Cabinet Maintenance Tech", "zone_downtown", "loc_arcade", "evening", closes_at_22=True),
    _civic("hs_c_karaoke_mix", "Karaoke Lounge Audio Host", "zone_downtown", "loc_karaoke", "night"),
    _civic("hs_c_park_warden", "Neighborhood Park Caretaker", "zone_residential", "loc_local_park", "day"),
    _civic("hs_c_shrine_keeper", "Hilltop Shrine Stone-Step Sweeper", "zone_recreational_park", "loc_park_shrine", "day"),
    # 3 Modern Roaming Street Vendors
    _vendor(
        "hs_v_crepe_van",
        "Matcha & Strawberry Crêpe Van Vendor",
        "zone_downtown",
        ("loc_city_square", "loc_sandy_beach", "loc_local_park", "loc_arcade"),
        "cafe_merchant",
    ),
    _vendor(
        "hs_v_takoyaki_cart",
        "Coastal Pier Takoyaki Cart Cook",
        "zone_seaside_bay",
        ("loc_coastal_pier", "loc_night_market", "loc_city_square", "loc_picnic_pavilions"),
        "food_merchant",
    ),
    _vendor(
        "hs_v_boba_bike",
        "Parkside Bubble-Tea Cargo Cyclist",
        "zone_recreational_park",
        ("loc_local_park", "loc_park_lake", "loc_sakura_grove", "loc_city_square"),
        "cafe_merchant",
    ),
)

# ---------------------------------------------------------------------------
# HIGH SCHOOL DRAMA: 46 ROAMING TOWN PEDESTRIANS & RIVAL-ACADEMY YOUTH PEERS
# Compact specs: (slot_id, role, zone_id, weekday_route, weekend_route, age_group, grade)
# ---------------------------------------------------------------------------
_HS_PED_SPECS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...], str, str], ...] = (
    # 14 Rival-Academy Youth Peers
    ("hs_y_1", "Rival-Academy Track Sprinter", "zone_downtown", ("loc_city_square", "loc_local_park", "loc_cafe", "loc_convenience_store"), ("loc_sandy_beach", "loc_city_square", "loc_arcade"), "young_adult", "Youth Peer"),
    ("hs_y_2", "Prep Cram-School Ace", "zone_downtown", ("loc_city_square", "loc_cafe", "loc_gift_store", "loc_convenience_store"), ("loc_cafe", "loc_city_square", "loc_karaoke"), "young_adult", "Youth Peer"),
    ("hs_y_3", "Conservatory Violinist Teen", "zone_downtown", ("loc_city_square", "loc_accessories_store", "loc_cafe", "loc_sakura_grove"), ("loc_park_shrine", "loc_cafe", "loc_restaurant"), "young_adult", "Youth Peer"),
    ("hs_y_4", "Downtown Skate Crew Leader", "zone_downtown", ("loc_city_square", "loc_arcade", "loc_clothing_store", "loc_night_market"), ("loc_coastal_pier", "loc_arcade", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_5", "Rival Swim Club Captain", "zone_seaside_bay", ("loc_coastal_pier", "loc_sandy_beach", "loc_seaside_cafe", "loc_city_square"), ("loc_sandy_beach", "loc_seaside_cafe", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_6", "St. Jude Transfer Gamer", "zone_downtown", ("loc_arcade", "loc_convenience_store", "loc_restaurant", "loc_karaoke"), ("loc_arcade", "loc_night_market", "loc_karaoke"), "young_adult", "Youth Peer"),
    ("hs_y_7", "Kendo District Finalist", "zone_recreational_park", ("loc_park_shrine", "loc_local_park", "loc_city_square", "loc_restaurant"), ("loc_park_shrine", "loc_hilltop_lookout", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_8", "Boutique Part-Time Fashionista", "zone_downtown", ("loc_clothing_store", "loc_accessories_store", "loc_cafe", "loc_city_square"), ("loc_brand_clothing_store", "loc_seaside_cafe", "loc_karaoke"), "young_adult", "Youth Peer"),
    ("hs_y_9", "Seaside Volleys Sophomore", "zone_seaside_bay", ("loc_sandy_beach", "loc_seaside_cafe", "loc_coastal_pier", "loc_city_square"), ("loc_sandy_beach", "loc_picnic_pavilions", "loc_seaside_cafe"), "young_adult", "Youth Peer"),
    ("hs_y_10", "Indies Band Bassist Teen", "zone_downtown", ("loc_karaoke", "loc_city_square", "loc_arcade", "loc_night_market"), ("loc_karaoke", "loc_coastal_pier", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_11", "Photography Contest Teen", "zone_recreational_park", ("loc_sakura_grove", "loc_hilltop_lookout", "loc_cafe", "loc_city_square"), ("loc_park_lake", "loc_coastal_pier", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_12", "Evening Cram Commuter", "zone_downtown", ("loc_city_square", "loc_convenience_store", "loc_cafe", "loc_restaurant"), ("loc_gift_store", "loc_arcade", "loc_restaurant"), "young_adult", "Youth Peer"),
    ("hs_y_13", "Parkside Street Dancer", "zone_downtown", ("loc_city_square", "loc_local_park", "loc_clothing_store", "loc_night_market"), ("loc_city_square", "loc_sandy_beach", "loc_night_market"), "young_adult", "Youth Peer"),
    ("hs_y_14", "Botanical Tea-Club Rival", "zone_recreational_park", ("loc_sakura_grove", "loc_park_shrine", "loc_cafe", "loc_gift_store"), ("loc_sakura_grove", "loc_park_lake", "loc_seaside_cafe"), "young_adult", "Youth Peer"),
    # 32 Adult & Elder Townspeople Pedestrians
    ("hs_p_1", "Morning Rail Salaryman", "zone_downtown", ("loc_city_square", "loc_convenience_store", "loc_restaurant", "loc_karaoke"), ("loc_local_park", "loc_cafe", "loc_restaurant"), "adult", "Citizen"),
    ("hs_p_2", "Neighborhood Florist", "zone_downtown", ("loc_gift_store", "loc_city_square", "loc_cafe", "loc_local_park"), ("loc_sakura_grove", "loc_gift_store", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_3", "Retiree Dog Walker", "zone_residential", ("loc_local_park", "loc_convenience_store", "loc_park_lake", "loc_local_park"), ("loc_local_park", "loc_sakura_grove", "loc_park_shrine"), "elder", "Citizen"),
    ("hs_p_4", "Off-Duty Postal Carrier", "zone_residential", ("loc_local_park", "loc_city_square", "loc_restaurant", "loc_convenience_store"), ("loc_coastal_pier", "loc_local_park", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_5", "Local Bakery Patron", "zone_downtown", ("loc_cafe", "loc_clothing_store", "loc_city_square", "loc_local_park"), ("loc_cafe", "loc_brand_clothing_store", "loc_restaurant"), "adult", "Citizen"),
    ("hs_p_6", "Freelance Manga Assistant", "zone_downtown", ("loc_convenience_store", "loc_cafe", "loc_arcade", "loc_night_market"), ("loc_gift_store", "loc_arcade", "loc_restaurant"), "young_adult", "Citizen"),
    ("hs_p_7", "Pier Angler Retiree", "zone_seaside_bay", ("loc_coastal_pier", "loc_seaside_cafe", "loc_sandy_beach", "loc_city_square"), ("loc_coastal_pier", "loc_sandy_beach", "loc_night_market"), "elder", "Citizen"),
    ("hs_p_8", "Jogging Pediatric Nurse", "zone_residential", ("loc_local_park", "loc_cafe", "loc_convenience_store", "loc_city_square"), ("loc_sandy_beach", "loc_seaside_cafe", "loc_local_park"), "adult", "Citizen"),
    ("hs_p_9", "Downtown Music Store Regular", "zone_downtown", ("loc_city_square", "loc_karaoke", "loc_cafe", "loc_restaurant"), ("loc_karaoke", "loc_arcade", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_10", "Seaside Paddleboard Instructor", "zone_seaside_bay", ("loc_sandy_beach", "loc_seaside_cafe", "loc_coastal_pier", "loc_local_park"), ("loc_sandy_beach", "loc_coastal_pier", "loc_seaside_cafe"), "adult", "Citizen"),
    ("hs_p_11", "Park Birdwatcher Elder", "zone_recreational_park", ("loc_park_lake", "loc_sakura_grove", "loc_park_shrine", "loc_picnic_pavilions"), ("loc_hilltop_lookout", "loc_park_lake", "loc_sakura_grove"), "elder", "Citizen"),
    ("hs_p_12", "Wedding Boutique Seamstress", "zone_downtown", ("loc_brand_clothing_store", "loc_accessories_store", "loc_cafe", "loc_city_square"), ("loc_brand_clothing_store", "loc_gift_store", "loc_restaurant"), "adult", "Citizen"),
    ("hs_p_13", "Nightly Konbini Delivery Driver", "zone_downtown", ("loc_city_square", "loc_convenience_store", "loc_restaurant", "loc_night_market"), ("loc_convenience_store", "loc_night_market", "loc_karaoke"), "adult", "Citizen"),
    ("hs_p_14", "Amateur Plein-Air Painter", "zone_recreational_park", ("loc_hilltop_lookout", "loc_sakura_grove", "loc_coastal_pier", "loc_cafe"), ("loc_hilltop_lookout", "loc_sandy_beach", "loc_seaside_cafe"), "adult", "Citizen"),
    ("hs_p_15", "Family Diner Regular", "zone_downtown", ("loc_city_square", "loc_restaurant", "loc_convenience_store", "loc_local_park"), ("loc_restaurant", "loc_night_market", "loc_karaoke"), "adult", "Citizen"),
    ("hs_p_16", "Suburban Jazz Pianist", "zone_downtown", ("loc_cafe", "loc_city_square", "loc_karaoke", "loc_nightclub"), ("loc_cafe", "loc_night_market", "loc_nightclub"), "adult", "Citizen"),
    ("hs_p_17", "Boutique Dog-Groomer", "zone_residential", ("loc_local_park", "loc_clothing_store", "loc_cafe", "loc_convenience_store"), ("loc_local_park", "loc_sandy_beach", "loc_cafe"), "adult", "Citizen"),
    ("hs_p_18", "Highland Trail Hiker", "zone_recreational_park", ("loc_campsite", "loc_hilltop_lookout", "loc_park_shrine", "loc_picnic_pavilions"), ("loc_campsite", "loc_hilltop_lookout", "loc_park_lake"), "adult", "Citizen"),
    ("hs_p_19", "Weekend Camper Photographer", "zone_recreational_park", ("loc_picnic_pavilions", "loc_park_lake", "loc_campsite", "loc_night_market"), ("loc_campsite", "loc_park_lake", "loc_seaside_cafe"), "young_adult", "Citizen"),
    ("hs_p_20", "Station Bookstore Editor", "zone_downtown", ("loc_city_square", "loc_cafe", "loc_gift_store", "loc_restaurant"), ("loc_cafe", "loc_park_shrine", "loc_restaurant"), "adult", "Citizen"),
    ("hs_p_21", "Nightclub Sound Mixer", "zone_downtown", ("loc_convenience_store", "loc_arcade", "loc_nightclub", "loc_night_market"), ("loc_nightclub", "loc_karaoke", "loc_restaurant"), "young_adult", "Citizen"),
    ("hs_p_22", "Shrine Calligraphy Volunteer", "zone_recreational_park", ("loc_park_shrine", "loc_sakura_grove", "loc_cafe", "loc_city_square"), ("loc_park_shrine", "loc_sakura_grove", "loc_night_market"), "elder", "Citizen"),
    ("hs_p_23", "Marine Shellcraft Artisan", "zone_seaside_bay", ("loc_sandy_beach", "loc_gift_store", "loc_seaside_cafe", "loc_coastal_pier"), ("loc_sandy_beach", "loc_coastal_pier", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_24", "Downtown Pastry Critic", "zone_downtown", ("loc_cafe", "loc_seaside_cafe", "loc_restaurant", "loc_brand_clothing_store"), ("loc_cafe", "loc_seaside_cafe", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_25", "Evening Commuter Cyclist", "zone_residential", ("loc_local_park", "loc_city_square", "loc_convenience_store", "loc_coastal_pier"), ("loc_park_lake", "loc_coastal_pier", "loc_picnic_pavilions"), "adult", "Citizen"),
    ("hs_p_26", "Boardwalk Street Magician", "zone_seaside_bay", ("loc_coastal_pier", "loc_city_square", "loc_night_market", "loc_sandy_beach"), ("loc_coastal_pier", "loc_sandy_beach", "loc_night_market"), "young_adult", "Citizen"),
    ("hs_p_27", "Adult Boutique Window Shopper", "zone_downtown", ("loc_brand_clothing_store", "loc_accessories_store", "loc_adult_store", "loc_nightclub"), ("loc_nightclub", "loc_adult_store", "loc_karaoke"), "adult", "Citizen"),
    ("hs_p_28", "Morning Newspaper Deliverer", "zone_residential", ("loc_convenience_store", "loc_local_park", "loc_city_square", "loc_cafe"), ("loc_local_park", "loc_convenience_store", "loc_park_lake"), "young_adult", "Citizen"),
    ("hs_p_29", "Antique Clock Tinkerer", "zone_downtown", ("loc_accessories_store", "loc_gift_store", "loc_cafe", "loc_park_shrine"), ("loc_gift_store", "loc_night_market", "loc_cafe"), "elder", "Citizen"),
    ("hs_p_30", "Harbor Bento Caterer", "zone_seaside_bay", ("loc_coastal_pier", "loc_seaside_cafe", "loc_city_square", "loc_night_market"), ("loc_seaside_cafe", "loc_picnic_pavilions", "loc_night_market"), "adult", "Citizen"),
    ("hs_p_31", "Late-Shift Pharmacy Tech", "zone_downtown", ("loc_convenience_store", "loc_city_square", "loc_restaurant", "loc_local_park"), ("loc_local_park", "loc_cafe", "loc_restaurant"), "adult", "Citizen"),
    ("hs_p_32", "Park Picnic Musician", "zone_recreational_park", ("loc_picnic_pavilions", "loc_sakura_grove", "loc_city_square", "loc_night_market"), ("loc_picnic_pavilions", "loc_sandy_beach", "loc_night_market"), "young_adult", "Citizen"),
)

HS_TOWN_PEDESTRIAN_ARCHETYPES: tuple[dict[str, Any], ...] = tuple(
    _ped(
        s_id,
        role,
        z_id,
        w_rt,
        weekend_route=we_rt,
        age_group=ag,
        grade=gr,
        is_truant_peer=(s_id in ("hs_y_2", "hs_y_4")),
    )
    for s_id, role, z_id, w_rt, we_rt, ag, gr in _HS_PED_SPECS
)

# ---------------------------------------------------------------------------
# HIDDEN-IN-PLAIN-SIGHT SECRETS (~6-8%)
# ---------------------------------------------------------------------------
ANOMALOUS_HIDDEN_SECRETS: dict[str, dict[str, Any]] = {
    "anom_m_fishmkt_prop": {
        "hidden_secret": "Retired Freelance Anomaly Tracker who hung up a Ward-forged fillet knife behind the Harbor Fish Market stall.",
        "telltale_key": "ward_scent",
        "hidden_awakened": True,
        "secret_faction": "freelancer",
    },
    "anom_m_ramen_chef": {
        "hidden_secret": "Closet Pyrokinetic Awakened who boils tonkotsu bones over suppressed spark-vein heat.",
        "telltale_key": "amber_sparks",
        "hidden_awakened": True,
        "secret_faction": "freelancer",
    },
    "anom_m_laundry_sundry": {
        "hidden_secret": "Former Bureau cryptanalyst washing bloodstained trenchcoats no-questions-asked in the Suburb Laundromat.",
        "telltale_key": "micro_telltale",
        "hidden_awakened": True,
        "secret_faction": "public_agency",
    },
    "anom_c_zoo_keeper": {
        "hidden_secret": "Unregistered Beast-Tamers Ward Weaver calming anomalous sparrows inside the Conservatory glasshouse.",
        "telltale_key": "ward_scent",
        "hidden_awakened": True,
        "secret_faction": "monastic_order",
    },
    "anom_m_metro_night": {
        "hidden_secret": "Covert Velvet Syndicate lookout passing encrypted transit timetables inside folded evening tabloids.",
        "telltale_key": "syndicate_ink",
        "hidden_awakened": False,
        "secret_faction": "clandestine_faction",
    },
    "anom_p_up_7": {
        "hidden_secret": "Ash-Vein Cult spotter cataloging which museum relics hum back when visitors linger too long.",
        "telltale_key": "whispering_aura",
        "hidden_awakened": True,
        "secret_faction": "cult_faction",
    },
    "anom_p_dt_8": {
        "hidden_secret": "Black-market courier slipping cold-iron stitching needles into mannequin cuffs across Shopping Arcade.",
        "telltale_key": "syndicate_ink",
        "hidden_awakened": False,
        "secret_faction": "clandestine_faction",
    },
    "anom_p_ap_4": {
        "hidden_secret": "Unsuspecting exchange scholar carrying an unsealed bronze astrolabe that whispers coordinates at dusk.",
        "telltale_key": "whispering_aura",
        "hidden_awakened": False,
        "secret_faction": "",
    },
    "anom_p_sb_6": {
        "hidden_secret": "Night-shift hospital nurse secretly wearing a ticking brass chronometer recovered from Platform Zero.",
        "telltale_key": "cursed_trinket",
        "hidden_awakened": False,
        "secret_faction": "",
    },
    "anom_p_dk_5": {
        "hidden_secret": "Harbor ferry deckhand with salt-white ward scars under wool sleeves, ferrying Monastic couriers silently.",
        "telltale_key": "ward_scent",
        "hidden_awakened": True,
        "secret_faction": "monastic_order",
    },
    "anom_m_uni_union_eve": {
        "hidden_secret": "Freelance barrier-hacker selling low-grade spirit-chalk disguised as study-room chalk sticks.",
        "telltale_key": "micro_telltale",
        "hidden_awakened": True,
        "secret_faction": "freelancer",
    },
    "anom_p_ct_6": {
        "hidden_secret": "Street photographer whose analog negatives capture shadow silhouettes half a second before people move.",
        "telltale_key": "cursed_trinket",
        "hidden_awakened": True,
        "secret_faction": "freelancer",
    },
}

HS_HIDDEN_SECRETS: dict[str, dict[str, Any]] = {
    "hs_staff_proctor": {
        "hidden_secret": "Runs a hush-hush second-hand textbook and exam-prep tip ledger tucked behind Library index drawers.",
        "telltale_key": "micro_telltale",
    },
    "hs_y_3": {
        "hidden_secret": "Runaway conservatory heiress living off scholarship savings while dodging her family's chauffeur.",
        "telltale_key": "micro_telltale",
    },
    "hs_y_10": {
        "hidden_secret": "Secretly records masked acoustic covers at Karaoke that have hit half a million anonymous views.",
        "telltale_key": "micro_telltale",
    },
    "hs_c_s19": {
        "hidden_secret": "Keeps lost student IDs and locker spare keys cataloged behind the Boiler Den pipes for favors.",
        "telltale_key": "micro_telltale",
    },
    "hs_p_12": {
        "hidden_secret": "Designs idol stage outfits anonymously under an online alias that half the Sophomore class follows.",
        "telltale_key": "micro_telltale",
    },
    "hs_p_21": {
        "hidden_secret": "Rehearses subterranean DJ sets past 23:00 that local talent scouts quietly sneak in to judge.",
        "telltale_key": "micro_telltale",
    },
}

# ---------------------------------------------------------------------------
# PRE-WIRED SOCIAL TIES & SHARED HOUSEHOLD PAIRS
# Tuple: (slot_a, slot_b, tie_type, shared_residence_group)
# shared_residence_group != "" -> share home_node_id + fac_npc_res_hh_<group>
# ---------------------------------------------------------------------------
ANOMALOUS_COHABITING_AND_TIE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("anom_m_roastery_day", "anom_m_roastery_eve", "married", "hh_roastery_couple"),
    ("anom_m_fishmkt_prop", "anom_p_dk_7", "sibling", "hh_harbor_fish"),
    ("anom_m_ct_apothecary_prop", "anom_m_ct_apothecary_app", "sibling", "hh_chinatown_herb"),
    ("anom_m_konbini_day", "anom_m_laundry_sundry", "married", "hh_suburb_lanes"),
    ("anom_m_curio_prop", "anom_m_curio_eve", "coworker", ""),
    ("anom_p_cc_1", "anom_p_cc_2", "married", "hh_plaza_commuters"),
    ("anom_p_un_1", "anom_p_un_2", "roommate", "hh_uni_loft"),
    ("anom_p_un_5", "anom_p_un_6", "roommate", "hh_uni_union_flat"),
    ("anom_p_dt_2", "anom_p_dt_6", "roommate", "hh_downtown_studio"),
    ("anom_c_hosp_er_day", "anom_c_hosp_night", "coworker", ""),
    ("anom_c_cityhall_day", "anom_c_cityhall_arch", "coworker", ""),
    ("anom_p_sb_1", "anom_p_sb_2", "sibling", "hh_suburb_elders"),
    ("anom_m_seaside_cafe", "anom_p_ss_1", "sibling", "hh_seaside_shack"),
    ("anom_m_teastreet_prop", "anom_p_es_1", "sibling", ""),
    ("anom_m_couture_prop", "anom_m_couture_eve", "coworker", ""),
    ("anom_p_ct_1", "anom_m_ct_market_chef", "married", "hh_ct_market_flat"),
    ("anom_p_uc_1", "anom_p_uc_3", "roommate", "hh_uc_loft"),
    ("anom_m_metro_day", "anom_m_metro_night", "coworker", ""),
    ("anom_p_sc_1", "anom_p_sc_4", "sibling", "hh_academy_twins"),
    ("anom_p_dk_2", "anom_p_dk_3", "coworker", ""),
)

HS_COHABITING_AND_TIE_SPECS: tuple[tuple[str, str, str, str], ...] = (
    ("hs_c_pt_diner", "hs_c_s21", "sibling", "hh_hs_culinary"),
    ("hs_c_pt_gift", "hs_c_s14", "sibling", "hh_hs_artists"),
    ("hs_p_1", "hs_p_2", "married", "hh_hs_downtown_home"),
    ("hs_p_7", "hs_p_23", "married", "hh_hs_seaside_cottage"),
    ("hs_y_1", "hs_y_9", "sibling", "hh_hs_rival_sibs"),
    ("hs_p_6", "hs_p_21", "roommate", "hh_hs_studio"),
    ("hs_m_konbini_dawn", "hs_m_cafe_roast", "coworker", ""),
    ("hs_staff_gate", "hs_staff_grounds", "coworker", ""),
)

# ---------------------------------------------------------------------------
# COMBINATORIAL PROCEDURAL MICRO-QUIRK & DRIVE POOLS (0-LLM Stage 1 Hydration)
# ---------------------------------------------------------------------------
ROLE_QUIRK_POOLS: tuple[str, ...] = (
    "taps a pen twice before speaking",
    "always carries spare peppermint candies",
    "checks a scuffed wristwatch out of habit",
    "hums old radio jingles when sorting things",
    "remembers customers by their usual drink order",
    "folds paper receipts into tiny geometric cranes",
    "keeps an umbrella hooked over one forearm rain or shine",
    "squints carefully before smiling warmly",
    "jots shorthand observations onto pocket sticky notes",
    "adjusts glasses whenever thinking through a problem",
    "speaks in brisk, rhythmic sentences",
    "leaves generous room along counters for tired regulars",
)

ROLE_DRIVE_POOLS: tuple[str, ...] = (
    "saving up for a quiet storefront upgrade",
    "keeping the neighborhood peaceful after sundown",
    "tracking down an estranged sibling across districts",
    "earning enough tips to clear an overdue lease",
    "collecting firsthand stories for a self-published zine",
    "protecting regular customers from predatory loan sharks",
    "perfecting a signature seasonal recipe",
    "landing a steady municipal contract before winter",
)
