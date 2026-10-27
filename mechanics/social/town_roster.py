from __future__ import annotations
"""
Town Commercial, Civic & Student Part-Time Roster Mechanics for Hikayat High School Scenarios.

Provides:
1. 24 persistent Town Characters (20 Adult Citizens + 4 Contact-Eligible Out-of-School Youth Peers)
   spanning Commercial Shopkeepers/Clerks, Civic/Transit/Safety Officers, and Regular Commuters/Neighbors.
2. Family kinship links connecting 4 Town Citizens directly to Campus Student lineages.
3. 6 alternating Student Part-Time Shift assignments (Mon/Wed/Fri or Tue/Thu 17:00–21:30 + 1 Weekend day 12:00–17:00),
   with strict 21:30/22:00 youth curfew handoff and automatic yield for active player appointments or party outings.
4. On-shift Shop Clerk resolution for `merchant.py` (including 10% "Classmate Hookup" discount at >= 40 affinity).
5. Idempotent retroactive seeding of `loc_transit_plaza` (`Commuter Station & Civic Plaza`) for existing saves.
"""
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen


# -----------------------------------------------------------------------------
# 24 DETERMINISTIC TOWN COMMERCIAL, CIVIC & YOUTH PEER BLUEPRINTS
# -----------------------------------------------------------------------------
TOWN_CITIZEN_TEMPLATES: List[Dict[str, Any]] = [
    # --- A. Commercial Shopkeepers & Clerks ---
    {
        "town_slot": "cafe_owner",
        "role": "Master Coffee Roaster & Café Owner",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_cafe",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ {cafe_name} ➔ Main Espresso & Seating Lounge",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "schedule_archetype": "day_merchant_cafe",
        "shop_venue_key": "loc_cafe",
        "family_lineage_idx": 0,
        "family_relation_to_student": "Uncle",
        "summary": "Warm-voiced master roaster who remembers every student's favorite drink order and quietly spots stressed regulars a free pastry.",
    },
    {
        "town_slot": "apprentice_barista_peer",
        "role": "Vocational Apprentice Barista",
        "grade": "Youth Peer",
        "gender": "female",
        "club": "Culinary Vocational School",
        "clique": "Town Youth",
        "social_role_type": "student_peer",
        "primary_node_id": "loc_cafe",
        "secondary_node_id": "loc_coastal_pier",
        "primary_facility": "{commercial_name} ➔ {cafe_name} ➔ Main Espresso & Seating Lounge",
        "secondary_facility": "{seaside_name} ➔ Boardwalk Pier & Lighthouse ➔ Timber Boardwalk Promenade",
        "schedule_archetype": "youth_peer_barista",
        "shop_venue_key": "loc_cafe",
        "summary": "Seventeen-year-old culinary vocational student practicing intricate swan latte art; curious about mainstream high school drama.",
    },
    {
        "town_slot": "konbini_day_clerk",
        "role": "Convenience Store Day Manager",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_convenience_store",
        "secondary_node_id": "loc_local_park",
        "primary_facility": "{commercial_name} ➔ Convenience Store ➔ Storefront & Checkout Counter",
        "secondary_facility": "{residential_name} ➔ {park_name} ➔ Tree-Lined Park Promenade",
        "schedule_archetype": "konbini_day",
        "shop_venue_key": "loc_convenience_store",
        "summary": "Brisk, eagle-eyed store manager who restocks hot steamed buns at lightning speed and keeps shoplifters on notice.",
    },
    {
        "town_slot": "konbini_night_clerk",
        "role": "Convenience Store Night-Shift Clerk",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Night Owls",
        "social_role_type": "adult_service",
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_convenience_store",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ Convenience Store ➔ Storefront & Checkout Counter",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Bus Terminal & Commuter Shelter",
        "schedule_archetype": "konbini_night",
        "shop_venue_key": "loc_convenience_store",
        "summary": "Deadpan insomniac clerk listening to indie radio through one earbud while ringing up midnight ramen and watching fluorescent-lit streets.",
    },
    {
        "town_slot": "arcade_attendant",
        "role": "Arcade Floor Technician & Manager",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_arcade",
        "secondary_node_id": "loc_convenience_store",
        "primary_facility": "{commercial_name} ➔ {arcade_name} ➔ Neon Entryway & Prize Floor",
        "secondary_facility": "{commercial_name} ➔ Convenience Store ➔ Window Eat-In Nook",
        "schedule_archetype": "afternoon_evening_merchant",
        "shop_venue_key": "loc_arcade",
        "summary": "Former fighting-game tournament finalist with a jingling keyring who repairs jammed arcade microswitches in thirty seconds flat.",
    },
    {
        "town_slot": "karaoke_receptionist",
        "role": "Karaoke Lounge Receptionist",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_karaoke",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ Karaoke Lounge ➔ Reception Lobby & Drink Bar",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Sidewalk Patio & Entryway",
        "schedule_archetype": "afternoon_evening_merchant",
        "shop_venue_key": "loc_karaoke",
        "summary": "Cheerful front-desk host who hands out tambourines with theatrical flair and tactfully ignores off-key heartbreak ballads.",
    },
    {
        "town_slot": "station_kiosk_vendor",
        "role": "Station Bookstore & Kiosk Proprietor",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_local_park",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "secondary_facility": "{residential_name} ➔ {park_name} ➔ Duck Pond & Timber Footbridge",
        "schedule_archetype": "day_merchant_kiosk",
        "shop_venue_key": "loc_city_square",
        "summary": "Bespectacled newsstand and paperback vendor who stocks exam cram guides, literary magazines, and limited-edition stationery.",
    },
    {
        "town_slot": "seaside_shack_boss",
        "role": "Seaside Grill & Shaved-Ice Vendor",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_seaside_cafe",
        "secondary_node_id": "loc_coastal_pier",
        "primary_facility": "{seaside_name} ➔ Seaside Beach Shack ➔ Walk-Up Shaved Ice & Grill Bar",
        "secondary_facility": "{seaside_name} ➔ Boardwalk Pier & Lighthouse ➔ End-of-Pier Lookout Deck",
        "schedule_archetype": "seaside_merchant",
        "shop_venue_key": "loc_seaside_cafe",
        "summary": "Sun-tanned retired surfer grilling soy-glazed corn skewers and piling syrup onto shaved ice with booming coastal hospitality.",
    },
    {
        "town_slot": "restaurant_chef_owner",
        "role": "Diner Head Chef & Proprietor",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_restaurant",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ Downtown Diner & Family Restaurant ➔ Open Grill & Order Counter",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Central Fountain & Street Stage",
        "schedule_archetype": "day_merchant_restaurant",
        "shop_venue_key": "loc_restaurant",
        "summary": "Jovial short-order chef flipping omurice and hamburger steaks on a sizzling iron griddle with generous portions for hungry regulars.",
    },
    {
        "town_slot": "streetwear_shopkeeper",
        "role": "Streetwear Boutique Manager",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_clothing_store",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ Casual Streetwear & Apparel Shop ➔ Streetwear Rack & Display Floor",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Sidewalk Patio & Entryway",
        "schedule_archetype": "day_merchant_clothing",
        "shop_venue_key": "loc_clothing_store",
        "summary": "Trend-savvy apparel buyer with layered silver chains who pairs effortless streetwear silhouettes for weekend hangouts.",
    },
    {
        "town_slot": "luxury_boutique_stylist",
        "role": "Luxury Fashion Stylist & Curator",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_brand_clothing_store",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ Luxury Designer Boutique ➔ Marble Showroom & Runway Racks",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Main Espresso & Seating Lounge",
        "schedule_archetype": "day_merchant_brand_clothing",
        "shop_venue_key": "loc_brand_clothing_store",
        "summary": "Impeccably tailored runway stylist who sizes up posture at a glance and curates head-turning designer pieces.",
    },
    {
        "town_slot": "bijoux_jeweler",
        "role": "Master Jeweler & Accessories Proprietor",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_accessories_store",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ Accessories & Bijoux Emporium ➔ Glass Watch & Jewelry Counter",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Central Fountain & Street Stage",
        "schedule_archetype": "day_merchant_accessories",
        "shop_venue_key": "loc_accessories_store",
        "summary": "Soft-spoken horologist and silversmith with a jeweler's loupe who polishes delicate lockets, watches, and hairpins.",
    },
    {
        "town_slot": "curio_gift_proprietor",
        "role": "Curio & Gift Shop Proprietor",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commercial Guild",
        "clique": "Town Merchants",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_gift_store",
        "secondary_node_id": "loc_local_park",
        "primary_facility": "{commercial_name} ➔ Curio & Gift Shop ➔ Plushie & Music-Box Display Shelves",
        "secondary_facility": "{residential_name} ➔ {park_name} ➔ Playground & Shaded Gazebo",
        "schedule_archetype": "day_merchant_gift",
        "shop_venue_key": "loc_gift_store",
        "summary": "Whimsical shopkeeper who wraps every ribboned gift box by hand and offers uncanny advice on romantic keepsakes.",
    },
    {
        "town_slot": "night_market_stall_master",
        "role": "Night Market Skewer & Lantern Master",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commercial Guild",
        "clique": "Night Owls",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_night_market",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ Lantern Night Market & Bazaar ➔ Sizzling Skewer & Street-Food Row",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Central Fountain & Street Stage",
        "schedule_archetype": "evening_merchant_night_market",
        "shop_venue_key": "loc_night_market",
        "summary": "Charcoal-smoke bazaar veteran stringing glowing paper lanterns at dusk and fanning spiced yakitori skewers for evening crowds.",
    },
    {
        "town_slot": "nightclub_bartender_host",
        "role": "Nightclub Head Bartender",
        "grade": "Citizen",
        "gender": "female",
        "club": "Downtown Nightlife Guild",
        "clique": "Night Owls",
        "social_role_type": "adult_service",
        "nsfw_only": True,
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_nightclub",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ Neon Pulse Nightclub ➔ Illuminated Neon Cocktail Bar",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Central Fountain & Street Stage",
        "schedule_archetype": "night_merchant_nightclub",
        "shop_venue_key": "loc_nightclub",
        "summary": "Sultry, razor-sharp mixologist flaring neon cocktails behind the bass-lit bar while keeping VIP booth secrets under lock and key.",
    },
    {
        "town_slot": "adult_boutique_curator",
        "role": "Adult Boutique Proprietor",
        "grade": "Citizen",
        "gender": "male",
        "club": "Downtown Nightlife Guild",
        "clique": "Night Owls",
        "social_role_type": "adult_service",
        "nsfw_only": True,
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_adult_store",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ Velvet Curtain Adult Boutique ➔ Velvet Curtain Front Counter",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Sidewalk Patio & Entryway",
        "schedule_archetype": "day_night_merchant_adult_store",
        "shop_venue_key": "loc_adult_store",
        "summary": "Unflappable, discreet boutique curator who packages lace lingerie and adult novelties in unmarked matte-black bags without judgment.",
    },

    # --- B. Civic, Transit & Public Safety Figures (8) ---
    {
        "town_slot": "koban_day_officer",
        "role": "Neighborhood Kōban Police Constable",
        "grade": "Citizen",
        "gender": "male",
        "club": "Municipal Civic Services",
        "clique": "Civic Authority",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_school_gate",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Neighborhood Kōban Police Box",
        "secondary_facility": "{school_name} ➔ Entrance Foyer & Shoe Lockers ➔ Entrance Doors",
        "schedule_archetype": "police_day_patrol",
        "family_lineage_idx": 1,
        "family_relation_to_student": "Older brother",
        "summary": "Community-minded patrol constable who directs morning crosswalk traffic, checks lost bicycles, and keeps an eye on school dismissal.",
    },
    {
        "town_slot": "koban_night_officer",
        "role": "Night-Beat Patrol Officer",
        "grade": "Citizen",
        "gender": "female",
        "club": "Municipal Civic Services",
        "clique": "Civic Authority",
        "social_role_type": "adult_service",
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_local_park",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Neighborhood Kōban Police Box",
        "secondary_facility": "{residential_name} ➔ {park_name} ➔ Tree-Lined Park Promenade",
        "schedule_archetype": "police_night_patrol",
        "summary": "No-nonsense night-watch officer carrying a heavy LED flashlight; firmly questions teenagers wandering the streets past the 22:00 curfew.",
    },
    {
        "town_slot": "municipal_bus_driver",
        "role": "Municipal Route Bus Driver",
        "grade": "Citizen",
        "gender": "male",
        "club": "Municipal Transit Authority",
        "clique": "Civic Workers",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_convenience_store",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Bus Terminal & Commuter Shelter",
        "secondary_facility": "{commercial_name} ➔ Convenience Store ➔ Window Eat-In Nook",
        "schedule_archetype": "transit_bus_driver",
        "summary": "Punctual veteran bus captain in crisp white driving gloves who waits an extra ten seconds when he spots a student sprinting for the stop.",
    },
    {
        "town_slot": "parcel_courier",
        "role": "Express Scooter Delivery Courier",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Logistics & Delivery",
        "clique": "Civic Workers",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Sidewalk Patio & Entryway",
        "schedule_archetype": "delivery_courier",
        "family_lineage_idx": 2,
        "family_relation_to_student": "Older sister",
        "summary": "Fast-talking parcel courier with a clipboard and cargo scooter who knows every shortcut alley and backyard gate in town.",
    },
    {
        "town_slot": "beach_lifeguard",
        "role": "Coastal Lifeguard Captain",
        "grade": "Citizen",
        "gender": "female",
        "club": "Municipal Civic Services",
        "clique": "Civic Workers",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_sandy_beach",
        "secondary_node_id": "loc_local_park",
        "primary_facility": "{seaside_name} ➔ Sandy Beach & Coastline ➔ Dune Boardwalk & Lifeguard Post",
        "secondary_facility": "{residential_name} ➔ {park_name} ➔ Tree-Lined Park Promenade",
        "schedule_archetype": "beach_lifeguard",
        "summary": "Vigilant coastal rescuer scanning rip currents through binoculars with zinc sunscreen on her nose and a brass whistle on a lanyard.",
    },
    {
        "town_slot": "lighthouse_keeper",
        "role": "Harbor Lighthouse Caretaker",
        "grade": "Citizen",
        "gender": "male",
        "club": "Maritime Heritage Trust",
        "clique": "Civic Workers",
        "social_role_type": "adult_service",
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_coastal_pier",
        "secondary_node_id": "loc_seaside_cafe",
        "primary_facility": "{seaside_name} ➔ Boardwalk Pier & Lighthouse ➔ Whitewashed Lighthouse Promontory",
        "secondary_facility": "{seaside_name} ➔ Seaside Beach Shack ➔ Open-Air Oceanview Patio",
        "schedule_archetype": "lighthouse_caretaker",
        "summary": "Weathered maritime historian who polishes the Fresnel beacon lens at dusk and tells eerie stories of old bay shipwrecks.",
    },
    {
        "town_slot": "recreational_park_ranger",
        "role": "Recreational Park Ranger & Warden",
        "grade": "Citizen",
        "gender": "female",
        "club": "Forestry & Parks Service",
        "clique": "Civic Workers",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_campsite",
        "secondary_node_id": "loc_hilltop_lookout",
        "primary_facility": "{rec_park_name} ➔ Woodland Campsite & Cabin Grounds ➔ Central Campfire Clearing",
        "secondary_facility": "{rec_park_name} ➔ Hilltop Scenic Lookout ➔ Panoramic Observation Deck",
        "schedule_archetype": "recreational_park_ranger",
        "summary": "Steady park warden who maintains woodland footpaths, checks campfire safety, and tends the sakura grove and lakeside boathouse.",
    },
    {
        "town_slot": "campus_night_guard",
        "role": "Campus Night-Watch Security Officer",
        "grade": "Citizen",
        "gender": "male",
        "club": "School Administration",
        "clique": "Staff",
        "social_role_type": "adult_service",
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_school_hallway",
        "secondary_node_id": "loc_courtyard",
        "primary_facility": "{school_name} ➔ School Hallways ➔ Locker Row",
        "secondary_facility": "{commons_name} ➔ Central Courtyard ➔ Courtyard Archway Entrance",
        "schedule_archetype": "campus_night_guard",
        "summary": "Former firefighter walking night rounds across locked academy corridors with a ring of brass master keys and a thermos of barley tea.",
    },

    # --- C. Regular Commuters, Neighbors & Rival Teen Peers (8) ---
    {
        "town_slot": "tired_salaryman",
        "role": "Overworked Corporate Office Worker",
        "grade": "Citizen",
        "gender": "male",
        "club": "Town Commuters",
        "clique": "Commuters",
        "social_role_type": "adult_service",
        "is_nocturnal_shift": True,
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_convenience_store",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Bus Terminal & Commuter Shelter",
        "secondary_facility": "{commercial_name} ➔ Convenience Store ➔ Window Eat-In Nook",
        "schedule_archetype": "commuter_salaryman",
        "summary": "Loosened-necktie corporate analyst clutching a briefcase, catching early buses at dawn and slurping hot konbini udon after the last meeting.",
    },
    {
        "town_slot": "career_office_commuter",
        "role": "Architectural Firm Office Commuter",
        "grade": "Citizen",
        "gender": "female",
        "club": "Town Commuters",
        "clique": "Commuters",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_cafe",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "secondary_facility": "{commercial_name} ➔ {cafe_name} ➔ Sidewalk Patio & Entryway",
        "schedule_archetype": "commuter_office",
        "family_lineage_idx": 3,
        "family_relation_to_student": "Older sister",
        "summary": "Sharp-dressed urban planner carrying rolled blueprint tubes who grabs morning iced americanos before catching the express bus.",
    },
    {
        "town_slot": "elderly_neighborhood_gossip",
        "role": "Retired Neighborhood Florist & Elder",
        "grade": "Citizen",
        "gender": "female",
        "club": "Neighborhood Watch Association",
        "clique": "Local Residents",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_local_park",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{residential_name} ➔ {park_name} ➔ Playground & Shaded Gazebo",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "schedule_archetype": "park_elder",
        "summary": "Sharp-eared neighborhood grandmother in a sunhat who feeds pond ducks, tends community flowerbeds, and knows fifty years of town secrets.",
    },
    {
        "town_slot": "morning_dog_walker",
        "role": "Freelance Illustrator & Dog Walker",
        "grade": "Citizen",
        "gender": "male",
        "club": "Local Residents",
        "clique": "Local Residents",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_local_park",
        "secondary_node_id": "loc_coastal_pier",
        "primary_facility": "{residential_name} ➔ {park_name} ➔ Duck Pond & Timber Footbridge",
        "secondary_facility": "{seaside_name} ➔ Boardwalk Pier & Lighthouse ➔ Timber Boardwalk Promenade",
        "schedule_archetype": "dog_walker_jogger",
        "summary": "Easygoing remote illustrator walking an overly enthusiastic Shiba Inu along the park footbridge and coastal boardwalk.",
    },
    {
        "town_slot": "cram_school_tutor",
        "role": "University Cram-School Tutor",
        "grade": "Citizen",
        "gender": "female",
        "club": "University Prep Circle",
        "clique": "Town Academics",
        "social_role_type": "adult_service",
        "primary_node_id": "loc_cafe",
        "secondary_node_id": "loc_city_square",
        "primary_facility": "{commercial_name} ➔ {cafe_name} ➔ Main Espresso & Seating Lounge",
        "secondary_facility": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "schedule_archetype": "cram_tutor",
        "summary": "University grad student grading mock entrance exams with four colors of highlighter in the café booth.",
    },
    {
        "town_slot": "rival_arcade_peer",
        "role": "Rival Academy Arcade Champion",
        "grade": "Youth Peer",
        "gender": "male",
        "club": "St. Jude's Esports Rivals",
        "clique": "Town Youth",
        "social_role_type": "student_peer",
        "primary_node_id": "loc_arcade",
        "secondary_node_id": "loc_convenience_store",
        "primary_facility": "{commercial_name} ➔ {arcade_name} ➔ Fighting & Rhythm Cabinet Hall",
        "secondary_facility": "{commercial_name} ➔ Convenience Store ➔ Snack Aisles & Chilled Coolers",
        "schedule_archetype": "youth_peer_arcade",
        "summary": "Cocky top-ranked fighting-game ace in a neighboring rival high school's crimson blazer who holds an unbeaten streak on Cabinet #1.",
    },
    {
        "town_slot": "plaza_indie_busker_peer",
        "role": "Plaza Indie Acoustic Busker",
        "grade": "Youth Peer",
        "gender": "female",
        "club": "Street Music Collective",
        "clique": "Town Youth",
        "social_role_type": "student_peer",
        "primary_node_id": "loc_city_square",
        "secondary_node_id": "loc_coastal_pier",
        "primary_facility": "{commercial_name} ➔ City Square ➔ Central Fountain & Street Stage",
        "secondary_facility": "{seaside_name} ➔ Boardwalk Pier & Lighthouse ➔ Timber Boardwalk Promenade",
        "schedule_archetype": "youth_peer_busker",
        "summary": "Seventeen-year-old correspondence-school songwriter performing soulful acoustic sets beside an open sticker-covered guitar case.",
    },
    {
        "town_slot": "park_skater_photographer_peer",
        "role": "Street Skater & Film Photographer",
        "grade": "Youth Peer",
        "gender": "male",
        "club": "Urban Skate & Zine Crew",
        "clique": "Town Youth",
        "social_role_type": "student_peer",
        "primary_node_id": "loc_local_park",
        "secondary_node_id": "loc_sandy_beach",
        "primary_facility": "{residential_name} ➔ {park_name} ➔ Tree-Lined Park Promenade",
        "secondary_facility": "{seaside_name} ➔ Sandy Beach & Coastline ➔ Dune Boardwalk & Lifeguard Post",
        "schedule_archetype": "youth_peer_skater",
        "summary": "Laid-back neighboring-town teen carrying a scuffed skateboard and a 35mm film camera, hunting golden-hour shots across town.",
    },
]

TOWN_DRIVES: List[str] = [
    "Saving up quietly to renovate an inherited family storefront before redevelopment corporations buy the block.",
    "Keeping a protective neighborhood eye on local high schoolers so they don't repeat past mistakes.",
    "Collecting everyday slice-of-life stories from commuters for a self-published local anthology.",
    "Maintaining pride in an honest craft despite long hours, aching feet, and razor-thin margins.",
    "Trying to bridge the rivalry between neighboring town youth and the main academy's cliques.",
    "Looking forward to the town's seasonal waterfront festival and organizing community volunteers.",
]

TOWN_FRICTIONS: List[str] = [
    "Blunt and unsentimental with small talk until someone proves they respect working staff.",
    "Habitually meddles in neighborhood gossip while claiming to mind their own business.",
    "Chronically sleep-deprived and grumpy before their second cup of strong black coffee.",
    "Soft-hearted pushover when polite teenagers ask for directions, spare change, or life advice.",
    "Stubborn stickler for local etiquette, recycling sorting rules, and punctual timetables.",
]

TOWN_QUIRKS: List[str] = [
    "Checks a battered steel wristwatch every few minutes and speaks in crisp, practical rhythms.",
    "Wipes down counters in circular motions while delivering dry, observant one-liners.",
    "Jingles a heavy brass keyring on their belt loop and nods warmly at familiar faces.",
    "Hums nostalgic city-pop melodies under their breath during quiet lulls.",
    "Taps a pen against a clipboard and squints thoughtfully at the sky before predicting rain.",
]


# -----------------------------------------------------------------------------
# 6 DETERMINISTIC STUDENT PART-TIME SHIFT ASSIGNMENTS
# -----------------------------------------------------------------------------
# Day-of-week math matches `is_weekend(current_day)`:
# day % 7 == 1 (Mon), 2 (Tue), 3 (Wed), 4 (Thu), 5 (Fri), 6 (Sat), 0 (Sun)
STUDENT_PART_TIME_SPECS: List[Dict[str, Any]] = [
    {
        "match_role": "Part-Time Barista & Baker",
        "job_title": "Part-Time Café Barista",
        "venue_node_id": "loc_cafe",
        "venue_facility_template": "{commercial_name} ➔ {cafe_name} ➔ Main Espresso & Seating Lounge",
        "weekday_mods": (1, 3, 5),  # Mon, Wed, Fri
        "weekend_mods": (6,),       # Saturday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1260,        # 21:00
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Wearing a canvas café apron behind the espresso bar, steaming milk and wiping down pastry tongs",
    },
    {
        "match_role": "Rebellious Delinquent",
        "job_title": "Part-Time Konbini Cashier",
        "venue_node_id": "loc_convenience_store",
        "venue_facility_template": "{commercial_name} ➔ Convenience Store ➔ Storefront & Checkout Counter",
        "weekday_mods": (2, 4),     # Tue, Thu
        "weekend_mods": (0,),       # Sunday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1290,        # 21:30 (hands off to Night Clerk before 22:00 curfew)
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Reluctantly wearing a convenience store vest behind the register, scanning barcode snacks with practiced speed",
    },
    {
        "match_role": "Gamer & Tech Tinkerer",
        "job_title": "Part-Time Arcade Floor Tech",
        "venue_node_id": "loc_arcade",
        "venue_facility_template": "{commercial_name} ➔ {arcade_name} ➔ Neon Entryway & Prize Floor",
        "weekday_mods": (1, 3, 5),  # Mon, Wed, Fri
        "weekend_mods": (6,),       # Saturday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1290,        # 21:30
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Wearing a staff lanyard and coin belt at the arcade prize counter, calibrating rhythm cabinet sensors",
    },
    {
        "match_role": "Social Media Trendsetter",
        "job_title": "Part-Time Karaoke Host",
        "venue_node_id": "loc_karaoke",
        "venue_facility_template": "{commercial_name} ➔ Karaoke Lounge ➔ Reception Lobby & Drink Bar",
        "weekday_mods": (2, 4),     # Tue, Thu
        "weekend_mods": (0,),       # Sunday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1290,        # 21:30
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Checking in karaoke booth reservations at the front desk while sanitizing wireless microphones",
    },
    {
        "match_role": "Cafeteria Gamer",
        "job_title": "Part-Time Station Kiosk Clerk",
        "venue_node_id": "loc_city_square",
        "venue_facility_template": "{commercial_name} ➔ City Square ➔ Pedestrian Crosswalk & Station Kiosk",
        "weekday_mods": (1, 3, 5),  # Mon, Wed, Fri
        "weekend_mods": (6,),       # Saturday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1230,        # 20:30
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Stacking weekly manga issues and commuter newspapers behind the station kiosk window",
    },
    {
        "match_role": "Cross-Country Runner",
        "job_title": "Part-Time Beach Shack Server",
        "venue_node_id": "loc_seaside_cafe",
        "venue_facility_template": "{seaside_name} ➔ Seaside Beach Shack ➔ Walk-Up Shaved Ice & Grill Bar",
        "weekday_mods": (2, 4),     # Tue, Thu
        "weekend_mods": (0,),       # Sunday
        "weekday_start": 1020,      # 17:00
        "weekday_end": 1230,        # 20:30
        "weekend_start": 720,       # 12:00
        "weekend_end": 1020,        # 17:00
        "shift_activity": "Serving syruped shaved ice and chilled ramune bottles across the breezy beach shack counter",
    },
]

_ROLE_TO_PART_TIME_SPEC: Dict[str, Dict[str, Any]] = {
    s["match_role"].lower(): s for s in STUDENT_PART_TIME_SPECS
}


def get_town_format_kwargs(session_id: int, scen_key: str = "high_school_drama") -> Dict[str, str]:
    """Resolves session-specific localized/procedural names for Campus & Town 3-tier paths."""
    from mechanics.world.locations import (
        get_session_school_name,
        get_session_classroom_name,
        get_session_athletics_complex_name,
        get_session_student_commons_name,
        get_session_cultural_arts_name,
        get_session_abandoned_campus_name,
    )
    from mechanics.world.locations.seeding import (
        get_session_commercial_district_name,
        get_session_residential_neighborhood_name,
        get_session_cafe_name,
        get_session_arcade_name,
        get_session_park_name,
        get_session_seaside_name,
        get_session_recreation_park_name,
    )
    return {
        "school_name": get_session_school_name(session_id, scen_key) or "Main Academy Campus",
        "classroom_name": get_session_classroom_name(session_id, scen_key) or "Homeroom Classroom",
        "athletics_name": get_session_athletics_complex_name(session_id, scen_key) or "School Grounds & Athletics",
        "commons_name": get_session_student_commons_name(session_id, scen_key) or "Student Commons & Central Plaza",
        "arts_name": get_session_cultural_arts_name(session_id, scen_key) or "Cultural Arts & Student Union",
        "abandoned_name": get_session_abandoned_campus_name(session_id, scen_key) or "Abandoned Old Campus Building",
        "commercial_name": get_session_commercial_district_name(session_id, scen_key) or "Downtown",
        "residential_name": get_session_residential_neighborhood_name(session_id, scen_key) or "Residential Neighborhood",
        "cafe_name": get_session_cafe_name(session_id, scen_key) or "Local Café",
        "arcade_name": get_session_arcade_name(session_id, scen_key) or "Game Arcade",
        "park_name": get_session_park_name(session_id, scen_key) or "Neighborhood Park",
        "seaside_name": get_session_seaside_name(session_id, scen_key) or "Seaside & Coastal Bay",
        "rec_park_name": get_session_recreation_park_name(session_id, scen_key) or "Recreational Park",
        "mountain_park_name": get_session_recreation_park_name(session_id, scen_key) or "Recreational Park",
    }


def get_expected_town_roster_count(scen_key: str = "high_school_drama") -> int:
    """Returns the expected Town character count (30 in SFW; 32 in NSFW)."""
    import scenario_data
    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
    return sum(1 for tmpl in TOWN_CITIZEN_TEMPLATES if is_nsfw or not tmpl.get("nsfw_only"))


def ensure_high_school_transit_plaza_seeded(session_id: int, scen_key: str = "high_school_drama") -> None:
    """
    Idempotently backfills `loc_city_square` (`City Square`) and its 5 sub-locations
    into existing High School save files whose `world_nodes` were seeded before the expansion.
    """
    if not session_id:
        return
    nodes = db.get_session_world_nodes(session_id)
    if not nodes:
        return
    node_ids = {str(n.get("node_id") or "") for n in nodes}
    if "loc_city_square" in node_ids or "loc_transit_plaza" in node_ids:
        return
    parent_zone = "zone_downtown" if "zone_downtown" in node_ids else ("zone_commercial" if "zone_commercial" in node_ids else "")
    if not parent_zone:
        return

    db.save_world_node(
        session_id=session_id,
        node_id="loc_city_square",
        parent_id=parent_zone,
        name="City Square",
        node_type="FACILITY",
        category="commercial",
        privacy_level="public",
        is_enclosed=0,
        is_transit_hub=1,
        access_tier="open",
        is_dynamic=0,
    )
    sub_defs = [
        ("sub_bus_shelter", "Bus Terminal & Commuter Shelter", 1, "public", "{}"),
        ("sub_koban_police_box", "Neighborhood Kōban Police Box", 1, "public", "{}"),
        ("sub_shopping_crosswalk", "Pedestrian Crosswalk & Station Kiosk", 0, "public", "{}"),
        ("sub_square_fountain", "Central Fountain & Street Stage", 0, "public", "{}"),
        ("sub_square_underpass", "Pedestrian Underpass & Service Alley", 1, "semi_private", '{"is_discreet": true}'),
    ]
    for sub_id, sub_name, enclosed, priv, st_json in sub_defs:
        db.save_world_node(
            session_id=session_id,
            node_id=sub_id,
            parent_id="loc_city_square",
            name=sub_name,
            node_type="ROOM",
            category="commercial",
            privacy_level=priv,
            is_enclosed=enclosed,
            is_transit_hub=0,
            access_tier="open",
            is_dynamic=0,
            state_json=st_json,
        )

    # Connect Facility to Entrance Room + internal Room-to-Room edges
    db.save_world_edge(session_id, "loc_city_square", "sub_bus_shelter", travel_minutes=1, edge_type="door")
    db.save_world_edge(session_id, "sub_bus_shelter", "sub_koban_police_box", travel_minutes=1, edge_type="door")
    db.save_world_edge(session_id, "sub_bus_shelter", "sub_shopping_crosswalk", travel_minutes=1, edge_type="door")
    db.save_world_edge(session_id, "sub_bus_shelter", "sub_square_fountain", travel_minutes=1, edge_type="door")
    db.save_world_edge(session_id, "sub_bus_shelter", "sub_square_underpass", travel_minutes=2, edge_type="door")
    db.save_world_edge(session_id, "sub_koban_police_box", "sub_shopping_crosswalk", travel_minutes=2, edge_type="door")

    # Connect Downtown Zone sibling facilities & entrances
    for sibling_fac in ("loc_cafe", "loc_arcade", "loc_karaoke", "loc_convenience_store", "loc_restaurant", "loc_clothing_store", "loc_brand_clothing_store", "loc_accessories_store", "loc_gift_store", "loc_night_market"):
        if sibling_fac in node_ids:
            db.save_world_edge(session_id, "loc_city_square", sibling_fac, travel_minutes=5, edge_type="pathway")
    for sibling_ent in ("sub_cafe_patio", "sub_arcade_foyer", "sub_karaoke_lobby", "sub_konbini_front", "sub_restaurant_counter", "sub_clothing_front", "sub_brand_clothing_front", "sub_accessories_front", "sub_gift_front", "sub_night_market_gate"):
        if sibling_ent in node_ids:
            db.save_world_edge(session_id, "sub_bus_shelter", sibling_ent, travel_minutes=4, edge_type="pathway")


def assign_student_part_time_shifts(
    campus_directory: List[Dict[str, Any]],
    fmt_kwargs: Dict[str, str],
) -> None:
    """
    Mutates the 6 designated student records in `campus_directory` in-place to attach
    their town part-time shift metadata (`secondary_facility`, `part_time_job`, `part_time_node_id`).
    """
    assigned_roles: set[str] = set()
    for entry in campus_directory:
        if entry.get("grade") in ("Faculty", "Citizen", "Youth Peer"):
            continue
        r_key = str(entry.get("role") or "").strip().lower()
        spec = _ROLE_TO_PART_TIME_SPEC.get(r_key)
        if spec and r_key not in assigned_roles:
            assigned_roles.add(r_key)
            venue_path = spec["venue_facility_template"].format(**fmt_kwargs)
            entry["secondary_facility"] = venue_path
            entry["part_time_job"] = spec["job_title"]
            entry["part_time_node_id"] = spec["venue_node_id"]
            if "Part-Time:" not in entry.get("personality_summary", ""):
                entry["personality_summary"] = (
                    f"{entry['personality_summary']} Part-Time: {spec['job_title']} at {venue_path.split(' ➔ ')[1]}."
                ).strip()


def get_student_part_time_spec(npc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Returns the deterministic part-time shift spec for a student NPC if they hold one."""
    if not isinstance(npc, dict):
        return None
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    grade = str(npc.get("grade") or basic.get("grade") or "").strip()
    if grade in ("Faculty", "Citizen", "Youth Peer"):
        return None
    role_low = str(npc.get("role") or basic.get("role") or "").strip().lower()
    if role_low in _ROLE_TO_PART_TIME_SPEC:
        return _ROLE_TO_PART_TIME_SPEC[role_low]
    # Also check personality_summary or part_time_job tag persisted on DB rows
    pt_job = str(npc.get("part_time_job") or basic.get("part_time_job") or "").strip().lower()
    summary_low = str(npc.get("personality_summary") or basic.get("description") or "").lower()
    for spec in STUDENT_PART_TIME_SPECS:
        if pt_job and pt_job == spec["job_title"].lower():
            return spec
        if f"part-time: {spec['job_title'].lower()}" in summary_low:
            return spec
        if spec["match_role"].lower() in role_low:
            return spec
    return None


def _has_conflicting_party_or_appointment(
    session_id: int,
    npc_name: str,
    current_day: int,
    current_minute: int,
) -> bool:
    """
    Returns True if the student is currently in the player's active party or has an active
    scheduled appointment/commitment overlapping the current day/window (yielding their work shift).
    """
    if not session_id or not npc_name:
        return False
    clean_target = npc_name.strip().lower()
    try:
        party = db.get_session_party_npcs(session_id) or []
        for pm in party:
            p_name = str(pm.get("name") if isinstance(pm, dict) else pm).strip().lower()
            if p_name == clean_target:
                return True
        commitments = db.get_active_commitments(session_id, entity_name=npc_name) or []
        for cm in commitments:
            s_day = cm.get("scheduled_day")
            if s_day is None:
                s_day = cm.get("due_day") if cm.get("due_day") is not None else cm.get("target_day")
            e_day = cm.get("end_day") if cm.get("end_day") is not None else s_day
            if s_day is not None and not (int(s_day) <= int(current_day) <= int(e_day or s_day)):
                continue
            start_m = cm.get("start_minute")
            if start_m is None:
                start_m = cm.get("window_start_minute") if cm.get("window_start_minute") is not None else cm.get("target_minute")
            end_m = cm.get("end_minute") if cm.get("end_minute") is not None else cm.get("window_end_minute")
            if start_m is not None:
                s_min = int(start_m)
                e_min = int(end_m) if end_m is not None else (s_min + 180)
                if (s_min - 60) <= int(current_minute) <= e_min:
                    return True
            else:
                return True
    except Exception:
        pass
    return False


def is_student_on_part_time_shift(
    npc: Dict[str, Any],
    current_day: int,
    current_minute: int,
    session_id: int = 0,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates whether `npc` is actively working their after-school or weekend part-time shift
    at `(current_day, current_minute)`. Automatically yields before 22:00 youth curfew and when
    the player has an active appointment or party outing with them.
    """
    spec = get_student_part_time_spec(npc)
    if not spec:
        return None
    safe_day = max(1, int(current_day or 1))
    safe_min = int(current_minute or 0) % 1440
    # Hard youth labor / curfew cutoff: never after 21:30 (1290)
    if safe_min >= 1290 or safe_min < 720:
        return None

    day_mod = safe_day % 7
    in_window = False
    if day_mod in (6, 0):
        if day_mod in spec["weekend_mods"] and spec["weekend_start"] <= safe_min < spec["weekend_end"]:
            in_window = True
    else:
        if day_mod in spec["weekday_mods"] and spec["weekday_start"] <= safe_min < spec["weekday_end"]:
            in_window = True

    if not in_window:
        return None

    npc_name = str(npc.get("name") or "").strip()
    if session_id and _has_conflicting_party_or_appointment(session_id, npc_name, safe_day, safe_min):
        return None
    return spec


def generate_town_roster(
    session_id: int,
    scen_key: str = "high_school_drama",
    used_names: Optional[set[str]] = None,
    sibling_surnames: Optional[List[str]] = None,
    family_races: Optional[Dict[str, str]] = None,
    campus_directory: Optional[List[Dict[str, Any]]] = None,
    fmt_kwargs: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministically generates the Town Commercial, Civic & Youth Peer characters
    (30 in SFW; 32 in NSFW), weaving 4 family kinship links directly into Campus Student lineages.
    """
    import scenario_data
    from mechanics.social.races import normalize_race

    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
    used = used_names if used_names is not None else set()
    fmt = fmt_kwargs or get_town_format_kwargs(session_id, scen_key)
    sib_surnames = list(sibling_surnames or [])
    fam_races = dict(family_races or {})
    seed_base = int(session_id or 12345) * 43 + 709

    town_entries: List[Dict[str, Any]] = []
    for idx, tmpl in enumerate(TOWN_CITIZEN_TEMPLATES):
        if tmpl.get("nsfw_only") and not is_nsfw:
            continue
        g = tmpl["gender"]
        lin_idx = tmpl.get("family_lineage_idx")
        forced_surname = sib_surnames[lin_idx] if (lin_idx is not None and lin_idx < len(sib_surnames)) else ""

        full_name = ""
        for attempt in range(30):
            s_val = seed_base + idx * 29 + attempt * 113
            if forced_surname:
                fam_pat = None if forced_surname.lower() in namegen._INDONESIAN_NON_PATRONYMIC_SURNAMES else (sum(ord(ch) for ch in f"{session_id}:{forced_surname.lower()}") % 2 == 0)
                cand = namegen.generate_person_name_with_surname(forced_surname, scen_key, gender=g, seed=s_val, use_patronymic=fam_pat)
            else:
                cand = namegen.generate_person_name(scen_key, gender=g, seed=s_val)
            if cand and cand.lower() not in used:
                full_name = cand
                used.add(full_name.lower())
                break
        if not full_name:
            full_name = f"Citizen {idx + 1}"
            used.add(full_name.lower())

        if forced_surname and forced_surname.lower() in fam_races:
            char_race = fam_races[forced_surname.lower()]
        else:
            char_race = normalize_race("", scen_key, seed=f"{session_id}:town:{full_name.lower()}")

        drive = TOWN_DRIVES[(seed_base + idx * 7) % len(TOWN_DRIVES)]
        friction = TOWN_FRICTIONS[(seed_base + idx * 11 + 3) % len(TOWN_FRICTIONS)]
        quirk = TOWN_QUIRKS[(seed_base + idx * 13 + 5) % len(TOWN_QUIRKS)]

        rel_student_name = ""
        family_clause = ""
        if forced_surname and campus_directory:
            # Find the student(s) belonging to this family surname
            matching_students = [
                s for s in campus_directory
                if s.get("grade") in ("Freshman", "Sophomore", "Junior", "Senior")
                and namegen.normalize_base_surname(namegen.extract_first_and_last_name(s.get("name", ""))[1]).lower() == forced_surname.lower()
            ]
            if matching_students:
                rel_student = matching_students[0]
                rel_student_name = rel_student["name"]
                rel_label = tmpl.get("family_relation_to_student", "Relative")
                family_clause = f" Family: {rel_label} of {rel_student_name} ({rel_student['grade']})."
                rel_student["town_relative_name"] = full_name
                if "Town Kin:" not in rel_student.get("personality_summary", ""):
                    rel_student["personality_summary"] = (
                        f"{rel_student['personality_summary']} Town Kin: {rel_label} {full_name} ({tmpl['role']})."
                    ).strip()

        personality = (
            f"{tmpl['summary']} "
            f"[TownArchetype:{tmpl['schedule_archetype']}] "
            f"Drive: {drive} Flaw: {friction} Mannerism: {quirk}{family_clause}"
        ).strip()

        town_entries.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_").replace(".", ""),
            "name": full_name,
            "gender": g,
            "race": char_race,
            "role": tmpl["role"],
            "grade": tmpl["grade"],  # "Citizen" or "Youth Peer"
            "club": tmpl["club"],
            "clique": tmpl["clique"],
            "social_role_type": tmpl["social_role_type"],
            "is_nocturnal_shift": bool(tmpl.get("is_nocturnal_shift", False)),
            "schedule_archetype": tmpl["schedule_archetype"],
            "shop_venue_key": tmpl.get("shop_venue_key", ""),
            "primary_node_id": tmpl["primary_node_id"],
            "secondary_node_id": tmpl["secondary_node_id"],
            "primary_facility": tmpl["primary_facility"].format(**fmt),
            "secondary_facility": tmpl["secondary_facility"].format(**fmt),
            "sibling_name": "",
            "town_relative_name": rel_student_name,
            "personality_summary": personality,
            "mannerisms": quirk,
            "is_hydrated": 0,
        })

    return town_entries


def infer_town_schedule_archetype(npc: Dict[str, Any]) -> str:
    """Extracts or infers the deterministic `schedule_archetype` for a Town Citizen or Youth Peer."""
    if not isinstance(npc, dict):
        return ""
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    direct = str(npc.get("schedule_archetype") or basic.get("schedule_archetype") or "").strip()
    if direct:
        return direct
    summary = str(npc.get("personality_summary") or basic.get("description") or "")
    if "[TownArchetype:" in summary:
        return summary.split("[TownArchetype:", 1)[1].split("]", 1)[0].strip()

    role_low = str(npc.get("role") or basic.get("role") or "").lower()
    for tmpl in TOWN_CITIZEN_TEMPLATES:
        if tmpl["role"].lower() == role_low or tmpl["role"].lower() in role_low:
            return tmpl["schedule_archetype"]
    if "night-shift clerk" in role_low or ("night" in role_low and "clerk" in role_low):
        return "konbini_night"
    if "convenience store" in role_low or "konbini" in role_low:
        return "konbini_day"
    if "diner" in role_low or "restaurant" in role_low:
        return "day_merchant_restaurant"
    if "luxury" in role_low or "designer" in role_low or "fashion stylist" in role_low:
        return "day_merchant_brand_clothing"
    if "streetwear" in role_low or "apparel" in role_low:
        return "day_merchant_clothing"
    if "jeweler" in role_low or "accessories" in role_low or "bijoux" in role_low:
        return "day_merchant_accessories"
    if "curio" in role_low or "gift shop" in role_low:
        return "day_merchant_gift"
    if "night market" in role_low or "lantern master" in role_low or "bazaar" in role_low:
        return "evening_merchant_night_market"
    if "nightclub" in role_low or "bartender" in role_low:
        return "night_merchant_nightclub"
    if "adult boutique" in role_low or "velvet curtain" in role_low:
        return "day_night_merchant_adult_store"
    if "roaster" in role_low or "café owner" in role_low:
        return "day_merchant_cafe"
    if "apprentice barista" in role_low:
        return "youth_peer_barista"
    if "arcade champion" in role_low:
        return "youth_peer_arcade"
    if "busker" in role_low:
        return "youth_peer_busker"
    if "skater" in role_low:
        return "youth_peer_skater"
    if "night-beat" in role_low or ("night" in role_low and "patrol" in role_low):
        return "police_night_patrol"
    if "police" in role_low or "constable" in role_low or "kōban" in role_low:
        return "police_day_patrol"
    if "bus driver" in role_low:
        return "transit_bus_driver"
    if "courier" in role_low or "delivery" in role_low:
        return "delivery_courier"
    if "lifeguard" in role_low:
        return "beach_lifeguard"
    if "lighthouse" in role_low:
        return "lighthouse_caretaker"
    if "ranger" in role_low:
        return "recreational_park_ranger"
    if "night-watch security" in role_low or ("security" in role_low and "campus" in role_low):
        return "campus_night_guard"
    if "corporate office" in role_low or "salaryman" in role_low:
        return "commuter_salaryman"
    if "office commuter" in role_low or "architectural" in role_low:
        return "commuter_office"
    if "florist" in role_low or "elder" in role_low:
        return "park_elder"
    if "dog walker" in role_low:
        return "dog_walker_jogger"
    if "cram-school" in role_low or "cram school" in role_low:
        return "cram_tutor"
    if "arcade" in role_low:
        return "afternoon_evening_merchant"
    if "karaoke" in role_low:
        return "afternoon_evening_merchant"
    if "kiosk" in role_low or "bookstore" in role_low:
        return "day_merchant_kiosk"
    if "shaved-ice" in role_low or "seaside grill" in role_low:
        return "seaside_merchant"
    return "day_merchant_cafe"


def get_town_citizen_schedule_nodes(
    npc: Dict[str, Any],
    current_day: int = 1,
    seed_val: int = 0,
    current_minute: Optional[int] = None,
) -> Dict[str, str]:
    """
    Computes the 8-phase node_id schedule map (`commute`, `morning`, `lunch`,
    `class_afternoon`, `extracurricular`, `afternoon`, `evening`, `night`)
    for a Town Citizen or Out-of-School Youth Peer, with minute-level precision
    between 20:00 (campus lockup) and 22:00+ (town commercial & nightlife hours).
    """
    arch = infer_town_schedule_archetype(npc)
    name = str(npc.get("name") or "citizen").lower().replace(" ", "_")
    home_nid = f"loc_{name}_residence"
    safe_min = (int(current_minute) % 1440) if current_minute is not None else None
    is_late_commercial_hour = bool(safe_min is not None and 1200 <= safe_min < 1320)  # 20:00–21:59

    # Default daytime commercial schedule
    s: Dict[str, str] = {
        "commute": "loc_city_square",
        "morning": "loc_cafe",
        "lunch": "loc_cafe",
        "class_afternoon": "loc_cafe",
        "extracurricular": "loc_cafe",
        "afternoon": "loc_cafe",
        "evening": "loc_cafe",
        "night": home_nid,
    }

    if arch == "day_merchant_cafe":
        s.update({
            "commute": "loc_cafe",
            "morning": "loc_cafe",
            "lunch": "loc_cafe",
            "class_afternoon": "loc_cafe",
            "extracurricular": "loc_cafe",
            "afternoon": "loc_cafe",
            "evening": "loc_cafe",
            "night": "loc_cafe" if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_restaurant":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_restaurant",
            "lunch": "loc_restaurant",
            "class_afternoon": "loc_restaurant",
            "extracurricular": "loc_restaurant",
            "afternoon": "loc_restaurant",
            "evening": "loc_restaurant",
            "night": "loc_restaurant" if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_clothing":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_clothing_store",
            "lunch": "loc_clothing_store",
            "class_afternoon": "loc_clothing_store",
            "extracurricular": "loc_clothing_store",
            "afternoon": "loc_clothing_store",
            "evening": "loc_clothing_store",
            "night": "loc_clothing_store" if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_brand_clothing":
        # Luxury Designer Boutique opens at 10:00 (600) and closes at 22:00 (1320)
        before_open = bool(safe_min is not None and safe_min < 600)
        s.update({
            "commute": "loc_cafe",
            "morning": "loc_cafe" if before_open else "loc_brand_clothing_store",
            "lunch": "loc_brand_clothing_store",
            "class_afternoon": "loc_brand_clothing_store",
            "extracurricular": "loc_brand_clothing_store",
            "afternoon": "loc_brand_clothing_store",
            "evening": "loc_brand_clothing_store",
            "night": "loc_brand_clothing_store" if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_accessories":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_accessories_store",
            "lunch": "loc_accessories_store",
            "class_afternoon": "loc_accessories_store",
            "extracurricular": "loc_accessories_store",
            "afternoon": "loc_accessories_store",
            "evening": "loc_accessories_store",
            "night": "loc_accessories_store" if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_gift":
        s.update({
            "commute": "loc_local_park",
            "morning": "loc_gift_store",
            "lunch": "loc_gift_store",
            "class_afternoon": "loc_gift_store",
            "extracurricular": "loc_gift_store",
            "afternoon": "loc_gift_store",
            "evening": "loc_gift_store",
            "night": "loc_gift_store" if is_late_commercial_hour else home_nid,
        })
    elif arch == "evening_merchant_night_market":
        # Lantern Night Market operates strictly 18:00–22:00 (1080..1319)
        in_bazaar_window = (safe_min is None) or (1080 <= safe_min < 1320)
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": home_nid,
            "class_afternoon": home_nid,
            "extracurricular": "loc_city_square",
            "afternoon": "loc_city_square",
            "evening": "loc_night_market" if in_bazaar_window else "loc_city_square",
            "night": "loc_night_market" if is_late_commercial_hour else home_nid,
        })
    elif arch == "night_merchant_nightclub":
        # Neon Pulse Nightclub operates 18:00–02:00 (safe_min >= 1080 or safe_min < 120)
        in_club_eve = (safe_min is None) or (safe_min >= 1080)
        in_club_night = (safe_min is None) or (safe_min >= 1080 or safe_min < 120)
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": home_nid,
            "class_afternoon": home_nid,
            "extracurricular": "loc_city_square",
            "afternoon": home_nid,
            "evening": "loc_nightclub" if in_club_eve else "loc_city_square",
            "night": "loc_nightclub" if in_club_night else home_nid,
        })
    elif arch == "day_night_merchant_adult_store":
        # Velvet Curtain Adult Boutique operates 12:00–00:00 (720 <= safe_min < 1440)
        in_late_night = (safe_min is None) or (safe_min >= 1200)
        s.update({
            "commute": home_nid,
            "morning": "loc_cafe",
            "lunch": "loc_adult_store",
            "class_afternoon": "loc_adult_store",
            "extracurricular": "loc_adult_store",
            "afternoon": "loc_adult_store",
            "evening": "loc_adult_store",
            "night": "loc_adult_store" if in_late_night else home_nid,
        })
    elif arch == "youth_peer_barista":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_cafe",
            "lunch": "loc_cafe",
            "class_afternoon": "loc_cafe",
            "extracurricular": "loc_coastal_pier",
            "afternoon": "loc_cafe",
            "evening": "loc_coastal_pier",
            "night": "loc_coastal_pier" if (safe_min is not None and 1200 <= safe_min < 1290) else home_nid,
        })
    elif arch == "konbini_day":
        s.update({
            "commute": "loc_convenience_store",
            "morning": "loc_convenience_store",
            "lunch": "loc_convenience_store",
            "class_afternoon": "loc_convenience_store",
            "extracurricular": "loc_convenience_store",
            "afternoon": "loc_convenience_store",
            "evening": "loc_convenience_store",
            "night": "loc_convenience_store" if (safe_min is not None and 1200 <= safe_min < 1290) else home_nid,
        })
    elif arch == "konbini_night":
        # Starts graveyard shift at 21:30 (1290), right as student part-timers & day staff hand off!
        on_graveyard = (safe_min is None) or (safe_min >= 1290 or safe_min < 420)
        s.update({
            "commute": "loc_city_square",
            "morning": home_nid,
            "lunch": home_nid,
            "class_afternoon": home_nid,
            "extracurricular": home_nid,
            "afternoon": home_nid,
            "evening": "loc_city_square",
            "night": "loc_convenience_store" if on_graveyard else "loc_city_square",
        })
    elif arch == "afternoon_evening_merchant":
        role_low = str(npc.get("role") or "").lower()
        venue = "loc_karaoke" if "karaoke" in role_low else "loc_arcade"
        s.update({
            "commute": home_nid,
            "morning": "loc_cafe" if "karaoke" in role_low else "loc_convenience_store",
            "lunch": venue,
            "class_afternoon": venue,
            "extracurricular": venue,
            "afternoon": venue,
            "evening": venue,
            "night": venue if is_late_commercial_hour else home_nid,
        })
    elif arch == "day_merchant_kiosk":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_city_square",
            "lunch": "loc_city_square",
            "class_afternoon": "loc_city_square",
            "extracurricular": "loc_city_square",
            "afternoon": "loc_city_square",
            "evening": "loc_local_park",
            "night": home_nid,
        })
    elif arch == "seaside_merchant":
        s.update({
            "commute": "loc_coastal_pier",
            "morning": "loc_seaside_cafe",
            "lunch": "loc_seaside_cafe",
            "class_afternoon": "loc_seaside_cafe",
            "extracurricular": "loc_seaside_cafe",
            "afternoon": "loc_seaside_cafe",
            "evening": "loc_coastal_pier",
            "night": home_nid,
        })
    elif arch == "police_day_patrol":
        weekend = (int(current_day or 1) % 7) in (6, 0)
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_city_square",
            "lunch": "loc_convenience_store",
            "class_afternoon": "loc_city_square",
            "extracurricular": "loc_local_park" if weekend else "loc_school_gate",
            "afternoon": "loc_city_square",
            "evening": "loc_city_square",
            "night": home_nid,
        })
    elif arch == "police_night_patrol":
        night_patrol = ["loc_city_square", "loc_local_park", "loc_coastal_pier"][(seed_val + int(current_day or 1)) % 3]
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": home_nid,
            "class_afternoon": home_nid,
            "extracurricular": "loc_city_square",
            "afternoon": home_nid,
            "evening": "loc_city_square",
            "night": night_patrol,
        })
    elif arch == "transit_bus_driver":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_city_square",
            "lunch": "loc_convenience_store",
            "class_afternoon": "loc_city_square",
            "extracurricular": "loc_city_square",
            "afternoon": "loc_city_square",
            "evening": "loc_city_square",
            "night": home_nid,
        })
    elif arch == "delivery_courier":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_cafe",
            "lunch": "loc_convenience_store",
            "class_afternoon": "loc_school_gate",
            "extracurricular": "loc_city_square",
            "afternoon": "loc_city_square",
            "evening": "loc_local_park",
            "night": home_nid,
        })
    elif arch == "beach_lifeguard":
        s.update({
            "commute": "loc_sandy_beach",
            "morning": "loc_sandy_beach",
            "lunch": "loc_seaside_cafe",
            "class_afternoon": "loc_sandy_beach",
            "extracurricular": "loc_sandy_beach",
            "afternoon": "loc_sandy_beach",
            "evening": "loc_local_park",
            "night": home_nid,
        })
    elif arch == "lighthouse_caretaker":
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": "loc_seaside_cafe",
            "class_afternoon": "loc_coastal_pier",
            "extracurricular": "loc_coastal_pier",
            "afternoon": "loc_coastal_pier",
            "evening": "loc_coastal_pier",
            "night": "loc_coastal_pier",
        })
    elif arch in ("recreational_park_ranger", "mountain_ranger"):
        afternoon_spot = "loc_sakura_grove" if (int(current_day or 1) % 2 == 0) else "loc_hilltop_lookout"
        s.update({
            "commute": "loc_campsite",
            "morning": "loc_campsite",
            "lunch": "loc_park_lake",
            "class_afternoon": afternoon_spot,
            "extracurricular": "loc_campsite",
            "afternoon": afternoon_spot,
            "evening": "loc_campsite",
            "night": home_nid,
        })
    elif arch == "campus_night_guard":
        guard_nodes = ["loc_school_hallway", "loc_courtyard", "loc_school_gate"]
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": home_nid,
            "class_afternoon": home_nid,
            "extracurricular": home_nid,
            "afternoon": home_nid,
            "evening": "loc_school_gate",
            "night": guard_nodes[(seed_val + int(current_day or 1)) % len(guard_nodes)],
        })
    elif arch == "commuter_salaryman":
        weekend = (int(current_day or 1) % 7) in (6, 0)
        if weekend:
            s.update({
                "commute": home_nid,
                "morning": "loc_local_park",
                "lunch": "loc_cafe",
                "class_afternoon": "loc_coastal_pier",
                "extracurricular": "loc_convenience_store",
                "afternoon": "loc_coastal_pier",
                "evening": "loc_convenience_store",
                "night": home_nid,
            })
        else:
            s.update({
                "commute": "loc_city_square",
                "morning": "loc_downtown_office_away",
                "lunch": "loc_downtown_office_away",
                "class_afternoon": "loc_downtown_office_away",
                "extracurricular": "loc_city_square",
                "afternoon": "loc_downtown_office_away",
                "evening": "loc_city_square",
                "night": "loc_convenience_store",
            })
    elif arch == "commuter_office":
        weekend = (int(current_day or 1) % 7) in (6, 0)
        if weekend:
            s.update({
                "commute": "loc_cafe",
                "morning": "loc_cafe",
                "lunch": "loc_seaside_cafe",
                "class_afternoon": "loc_coastal_pier",
                "extracurricular": "loc_cafe",
                "afternoon": "loc_coastal_pier",
                "evening": "loc_cafe",
                "night": home_nid,
            })
        else:
            s.update({
                "commute": "loc_cafe",
                "morning": "loc_downtown_office_away",
                "lunch": "loc_downtown_office_away",
                "class_afternoon": "loc_downtown_office_away",
                "extracurricular": "loc_city_square",
                "afternoon": "loc_downtown_office_away",
                "evening": "loc_cafe",
                "night": home_nid,
            })
    elif arch == "park_elder":
        s.update({
            "commute": "loc_local_park",
            "morning": "loc_local_park",
            "lunch": "loc_cafe",
            "class_afternoon": "loc_local_park",
            "extracurricular": "loc_city_square",
            "afternoon": "loc_local_park",
            "evening": home_nid,
            "night": home_nid,
        })
    elif arch == "dog_walker_jogger":
        s.update({
            "commute": "loc_local_park",
            "morning": "loc_coastal_pier",
            "lunch": "loc_cafe",
            "class_afternoon": home_nid,
            "extracurricular": "loc_local_park",
            "afternoon": home_nid,
            "evening": "loc_coastal_pier",
            "night": home_nid,
        })
    elif arch == "cram_tutor":
        s.update({
            "commute": home_nid,
            "morning": home_nid,
            "lunch": "loc_city_square",
            "class_afternoon": "loc_cafe",
            "extracurricular": "loc_cafe",
            "afternoon": "loc_cafe",
            "evening": "loc_cafe",
            "night": home_nid,
        })
    elif arch == "youth_peer_arcade":
        s.update({
            "commute": "loc_city_square",
            "morning": "loc_rival_academy_away",
            "lunch": "loc_rival_academy_away",
            "class_afternoon": "loc_arcade",
            "extracurricular": "loc_arcade",
            "afternoon": "loc_arcade",
            "evening": "loc_convenience_store",
            "night": home_nid,
        })
    elif arch == "youth_peer_busker":
        s.update({
            "commute": home_nid,
            "morning": "loc_cafe",
            "lunch": "loc_local_park",
            "class_afternoon": "loc_city_square",
            "extracurricular": "loc_city_square",
            "afternoon": "loc_city_square",
            "evening": "loc_coastal_pier",
            "night": home_nid,
        })
    elif arch == "youth_peer_skater":
        s.update({
            "commute": "loc_local_park",
            "morning": "loc_sandy_beach",
            "lunch": "loc_seaside_cafe",
            "class_afternoon": "loc_local_park",
            "extracurricular": "loc_local_park",
            "afternoon": "loc_local_park",
            "evening": "loc_city_square",
            "night": home_nid,
        })
    return s


def generate_town_citizen_activity(
    npc: Dict[str, Any],
    phase: str,
    location_str: str,
    current_minute: int,
) -> str:
    """Generates vivid, role-specific activity descriptions for Town Citizens & Youth Peers."""
    arch = infer_town_schedule_archetype(npc)
    loc_low = str(location_str or "").lower()

    if arch == "day_merchant_cafe":
        return "Dialing in espresso grind weights and wiping down the brass steam wand behind the café counter"
    if arch == "day_merchant_restaurant":
        return "Flipping sizzling hamburger steaks and omurice on the open diner griddle while calling out hot orders"
    if arch == "day_merchant_clothing":
        return "Steaming fresh streetwear hoodies and arranging seasonal lookbook mannequins on the shop floor"
    if arch == "day_merchant_brand_clothing":
        if "cafe" in loc_low or "café" in loc_low:
            return "Reviewing seasonal runway lookbooks over a morning cortado before opening the boutique"
        return "Draping silk couture pieces across marble display racks and offering tailored styling consultations"
    if arch == "day_merchant_accessories":
        return "Polishing silver lockets, hairpins, and chronograph watches through a jeweler's brass loupe"
    if arch == "day_merchant_gift":
        return "Tying satin ribbons onto hand-wrapped keepsake boxes beside shelves of music boxes and plushies"
    if arch == "evening_merchant_night_market":
        if "night market" in loc_low or "bazaar" in loc_low:
            return "Fanning charcoal-glazed yakitori skewers beneath glowing strings of paper bazaar lanterns"
        return "Unloading bamboo lantern frames and spice crates at City Square ahead of the 18:00 night bazaar"
    if arch == "night_merchant_nightclub":
        if "nightclub" in loc_low or "neon pulse" in loc_low:
            return "Shaking ultraviolet neon cocktails behind the bass-thumping bar while keeping an eye on VIP booths"
        return "Picking up fresh citrus garnishes in Downtown before unlocking the nightclub doors at 18:00"
    if arch == "day_night_merchant_adult_store":
        if "adult" in loc_low or "velvet curtain" in loc_low:
            return "Maintaining discreet boutique displays of lace lingerie and sealing unmarked matte-black gift bags"
        return "Reading a paperback over morning espresso before opening the Velvet Curtain boutique at noon"
    if arch == "youth_peer_barista":
        if "cafe" in loc_low or "café" in loc_low:
            return "Practicing steamed-milk tulip latte art behind the counter in a flour-dusted apron"
        return "Leaning on the timber pier railing with an iced matcha, sketching pastry plating ideas"
    if arch == "konbini_day":
        return "Restocking warm nikuman buns and ringing up commuters at the convenience store register"
    if arch == "konbini_night":
        if current_minute >= 1290 or current_minute < 420:
            return "Manning the fluorescent-lit checkout counter on graveyard shift with a single earbud in"
        return "Waiting at the City Square bus shelter with an iced black coffee before starting night shift"
    if arch == "afternoon_evening_merchant":
        if "karaoke" in loc_low:
            return "Assigning private karaoke booth numbers at reception and wiping down song tablets"
        return "Emptying token hoppers and tuning arcade joystick microswitches on the prize floor"
    if arch == "day_merchant_kiosk":
        return "Arranging commuter newspapers, exam study guides, and fountain pens at the City Square kiosk"
    if arch == "seaside_merchant":
        return "Fanning charcoal-grilled corn skewers and shaving fluffy ice hills under the beach shack awning"
    if arch == "police_day_patrol":
        if "school" in loc_low or "gate" in loc_low or "foyer" in loc_low:
            return "Keeping a friendly watchful eye on afternoon student dismissal outside the school gate"
        return "Updating the community Kōban noticeboard in City Square and greeting passing pedestrians"
    if arch == "police_night_patrol":
        return "Sweeping a heavy patrol flashlight along the walkway and checking on anyone out past the 22:00 curfew"
    if arch == "transit_bus_driver":
        if "convenience" in loc_low:
            return "Taking a ten-minute route break with a warm bento and thermos tea at the window counter"
        return "Checking the municipal bus timetable board in City Square and tipping a white-gloved salute to riders"
    if arch == "delivery_courier":
        return "Checking parcel addresses on a handheld scanner beside a parked yellow delivery scooter"
    if arch == "beach_lifeguard":
        return "Scanning the surf line with binoculars from the lifeguard post with a rescue buoy slung nearby"
    if arch == "lighthouse_caretaker":
        return "Inspecting the salt-weathered lighthouse iron door and logging evening tide levels"
    if arch in ("recreational_park_ranger", "mountain_ranger"):
        return "Checking woodland trail markers, tending sakura grove footpaths, and inspecting the lookout rail"
    if arch == "campus_night_guard":
        return "Walking quiet night security rounds down the darkened corridor with a flashlight and brass master keys"
    if arch == "commuter_salaryman":
        if "convenience" in loc_low:
            return "Slurping hot cup udon at the window eat-in counter with a loosened tie and tired eyes"
        return "Checking commuter bus arrival times in City Square while replying to work emails on a smartphone"
    if arch == "commuter_office":
        return "Tucking rolled architectural blueprints under one arm while sipping a takeaway espresso"
    if arch == "park_elder":
        return "Tossing breadcrumbs to pond ducks from a shaded bench and chatting about neighborhood happenings"
    if arch == "dog_walker_jogger":
        return "Holding the leash of a cheerful Shiba Inu trotting eagerly along the walkway"
    if arch == "cram_tutor":
        return "Marking practice university entrance essays with color-coded highlighters in a quiet corner"
    if arch == "youth_peer_arcade":
        return "Racking up a double-perfect combo streak on the lead fighting cabinet in a rival school blazer"
    if arch == "youth_peer_busker":
        return "Strumming warm indie-folk chords by the City Square fountain beside a sticker-patched guitar case"
    if arch == "youth_peer_skater":
        return "Adjusting the aperture ring on a vintage 35mm camera with a skateboard resting beneath one sneaker"
    return "Going about daily town business"


def resolve_canonical_hs_node_id(
    location_str: str,
    session_id: int = 0,
    scen_key: str = "high_school_drama",
) -> str:
    """
    Resolves a 3-tier location string to its canonical High School facility `node_id`
    (e.g. `loc_cafe`, `loc_convenience_store`, `loc_city_square`, `loc_school_gate`),
    returning `""` for unknown/unseeded external locations (such as 'Downtown ➔ Velvet Mug').
    """
    loc_clean = str(location_str or "").strip()
    if not loc_clean:
        return ""

    fmt = get_town_format_kwargs(session_id, scen_key)
    parts = [p.strip() for p in loc_clean.split("➔") if p.strip()]
    zone_part = parts[0].lower() if parts else ""
    low = loc_clean.lower()

    # Reject explicit foreign urban districts not belonging to the High School town map
    known_zones = {
        fmt["school_name"].lower(),
        fmt["athletics_name"].lower(),
        fmt["commons_name"].lower(),
        fmt["arts_name"].lower(),
        fmt["abandoned_name"].lower(),
        fmt["commercial_name"].lower(),
        fmt["residential_name"].lower(),
        fmt["seaside_name"].lower(),
        fmt["rec_park_name"].lower(),
        "main academy campus",
        "downtown",
        "commercial district",
        "residential neighborhood",
        "seaside & coastal bay",
        "recreational park",
        "recreational mountain park",
    }
    if len(parts) >= 2 and zone_part not in known_zones and not any(
        z in zone_part for z in ("academy", "campus", "school", "downtown", "commercial", "residential", "seaside", "coastal", "recreational", "park")
    ):
        return ""

    if session_id:
        try:
            nid = db.resolve_node_id_from_location(session_id, loc_clean)
            if nid:
                node = db.get_world_node(session_id, nid)
                if node:
                    if node.get("node_type") in ("ROOM", "SUBLOCATION") and node.get("parent_id"):
                        p_id = str(node["parent_id"])
                        if p_id.startswith("bld_"):
                            return str(nid)
                        return p_id
                    return str(nid)
        except Exception:
            pass

    if any(k in low for k in (
        "city square", "transit_plaza", "commuter station", "civic plaza",
        "bus terminal", "bus shelter", "koban", "kōban", "police box",
        "station kiosk", "pedestrian crosswalk", "fountain & street stage", "pedestrian underpass",
    )):
        return "loc_city_square"
    if any(k in low for k in ("convenience store", "konbini")):
        return "loc_convenience_store"
    if any(k in low for k in ("downtown diner", "family restaurant", "open grill & order counter")):
        return "loc_restaurant"
    if any(k in low for k in ("luxury designer boutique", "marble showroom", "runway racks")):
        return "loc_brand_clothing_store"
    if any(k in low for k in ("casual streetwear", "apparel shop", "streetwear rack")):
        return "loc_clothing_store"
    if any(k in low for k in ("accessories & bijoux", "bijoux emporium", "watch & jewelry")):
        return "loc_accessories_store"
    if any(k in low for k in ("curio & gift shop", "music-box display")):
        return "loc_gift_store"
    if any(k in low for k in ("lantern night market", "night market & bazaar", "sizzling skewer")):
        return "loc_night_market"
    if any(k in low for k in ("neon pulse nightclub", "neon nightclub", "illuminated neon cocktail bar")):
        return "loc_nightclub"
    if any(k in low for k in ("velvet curtain adult", "adult boutique")):
        return "loc_adult_store"
    if any(k in low for k in ("mirage boutique love hotel", "love hotel")):
        return "loc_love_hotel"
    if any(k in low for k in ("seaside beach shack", "shaved ice", "seaside cafe", "seaside café")):
        return "loc_seaside_cafe"
    if fmt["cafe_name"].lower() in low or "local café" in low or "local cafe" in low or "espresso & seating lounge" in low:
        return "loc_cafe"
    if fmt["arcade_name"].lower() in low or "game arcade" in low or "cabinet hall" in low:
        return "loc_arcade"
    if "karaoke" in low:
        return "loc_karaoke"
    if fmt["park_name"].lower() in low or "neighborhood park" in low or "duck pond" in low:
        return "loc_local_park"
    if "sandy beach" in low or "lifeguard post" in low or "tidepool" in low:
        return "loc_sandy_beach"
    if "boardwalk pier" in low or "lighthouse" in low:
        return "loc_coastal_pier"
    if "campsite" in low or "campfire" in low:
        return "loc_campsite"
    if "park lake" in low or "mountain lake" in low or "boathouse" in low:
        return "loc_park_lake"
    if "hilltop scenic lookout" in low or "hilltop lookout" in low or "summit lookout" in low or "observation deck" in low:
        return "loc_hilltop_lookout"
    if "sakura blossom grove" in low or "sakura grove" in low or "cherry-blossom" in low:
        return "loc_sakura_grove"
    if "wayside shrine" in low or "wooden torii" in low:
        return "loc_park_shrine"
    if "picnic pavilions" in low or "lawn & barbecue" in low:
        return "loc_picnic_pavilions"
    if any(k in low for k in ("entrance foyer", "shoe lockers", "school gate", "main gate")):
        return "loc_school_gate"
    if "courtyard" in low:
        return "loc_courtyard"
    if "hallway" in low and "overgrown" not in low:
        return "loc_school_hallway"
    if "cafeteria" in low or "dining hall" in low:
        return "loc_cafeteria"
    return ""


def get_active_shop_clerk_for_location(
    session_id: int,
    location_str: str = "",
    merchant_type: str = "",
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Deterministically resolves the on-shift High School town/campus clerk for physical stores
    (`loc_convenience_store`, `loc_cafe`, `loc_restaurant`, `loc_clothing_store`,
    `loc_brand_clothing_store`, `loc_accessories_store`, `loc_gift_store`,
    `loc_night_market`, `loc_nightclub`, `loc_adult_store`, `loc_arcade`,
    `loc_karaoke`, `loc_seaside_cafe`, `loc_city_square`, `loc_cafeteria`).

    Note: `loc_love_hotel` intentionally returns `None` (clerkless touchscreen check-in).

    Priority when both an owner/adult manager AND a Student Part-Timer are on shift (`17:00–21:30`):
    - Surfaces the **Student Part-Timer** behind the register so players organically encounter
      their classmate working! And if player affinity >= 40, grants a 10% "Classmate Hookup" discount.
    """
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "fantasy")
    from mechanics.world.locations import is_school_scenario
    if not is_school_scenario(scen_key):
        return None

    loc = str(location_str or sess.get("current_location") or "").strip()
    loc_low = loc.lower()
    node_id = str(sess.get("current_node_id") or "").strip().lower()
    probe = f"{node_id} {loc_low} {merchant_type}".lower()

    # Mirage Boutique Love Hotel uses automated clerkless touchscreen check-in
    if any(k in probe for k in ("love_hotel", "love hotel", "mirage boutique")):
        return None

    target_venue = ""
    if any(k in probe for k in ("convenience", "konbini")):
        target_venue = "loc_convenience_store"
    elif any(k in probe for k in ("brand_clothing", "brand_clothes", "luxury designer", "designer boutique")):
        target_venue = "loc_brand_clothing_store"
    elif any(k in probe for k in ("clothing_store", "streetwear", "apparel shop", "clothes_merchant")):
        target_venue = "loc_clothing_store"
    elif any(k in probe for k in ("accessories_store", "accessories_merchant", "bijoux", "watch & jewelry")):
        target_venue = "loc_accessories_store"
    elif any(k in probe for k in ("gift_store", "gift_merchant", "curio & gift")):
        target_venue = "loc_gift_store"
    elif any(k in probe for k in ("night_market", "night market", "lantern night", "bazaar")):
        target_venue = "loc_night_market"
    elif any(k in probe for k in ("nightclub", "neon pulse")):
        target_venue = "loc_nightclub"
    elif any(k in probe for k in ("adult_store", "adult_merchant", "adult boutique", "velvet curtain")):
        target_venue = "loc_adult_store"
    elif any(k in probe for k in ("loc_restaurant", "restaurant_merchant", "downtown diner", "family restaurant")):
        target_venue = "loc_restaurant"
    elif "seaside" in probe or "beach shack" in probe or "shaved ice" in probe:
        target_venue = "loc_seaside_cafe"
    elif any(k in probe for k in ("cafe", "café", "espresso", "bakery")):
        target_venue = "loc_cafe"
    elif "arcade" in probe:
        target_venue = "loc_arcade"
    elif "karaoke" in probe:
        target_venue = "loc_karaoke"
    elif any(k in probe for k in ("kiosk", "crosswalk", "city_square", "city square", "transit_plaza", "commuter station", "school_merchant")):
        target_venue = "loc_city_square"
    elif "cafeteria" in probe or "dining hall" in probe:
        target_venue = "loc_cafeteria"

    if not target_venue:
        return None

    from mechanics.social.school_roster import ensure_school_directory_exists
    roster = ensure_school_directory_exists(sess) or []
    curr_day, curr_min, _ = db.get_session_time(session_id)
    safe_min = int(curr_min or 480) % 1440

    # 1. Check if a Campus Student Part-Timer is actively working this counter right now!
    for entry in roster:
        pt_spec = is_student_on_part_time_shift(entry, curr_day, safe_min, session_id=session_id)
        if pt_spec and pt_spec["venue_node_id"] == target_venue:
            char_id = 0
            if user_id:
                ch = db.get_character(user_id)
                char_id = int(ch.get("id", 0)) if ch else 0
            contact = db.get_contact(session_id, entry["name"], character_id=char_id)
            affinity = int((contact or {}).get("relationship_score") or 0)
            has_discount = affinity >= 40
            return {
                "name": entry["name"],
                "role": pt_spec["job_title"],
                "description": f"{entry['name']} ({entry['grade']} classmate working as {pt_spec['job_title']}). {pt_spec['shift_activity']}.",
                "is_student_part_timer": True,
                "affinity": affinity,
                "price_multiplier": 0.90 if has_discount else 1.0,
                "pricing_badge": "10% Classmate Hookup" if has_discount else None,
            }

    # 2. Check Campus Cafeteria Head Chef
    if target_venue == "loc_cafeteria":
        for entry in roster:
            if "cafeteria" in str(entry.get("role") or "").lower() or "chef" in str(entry.get("role") or "").lower():
                return {
                    "name": entry["name"],
                    "role": entry["role"],
                    "description": entry.get("personality_summary", ""),
                    "is_student_part_timer": False,
                    "affinity": 0,
                    "price_multiplier": 1.0,
                    "pricing_badge": None,
                }

    # 3. Resolve on-shift Town Commercial Clerk / Owner
    from mechanics.world.npc_schedule import get_npc_scheduled_node_id
    candidates: List[Dict[str, Any]] = []
    for entry in roster:
        if entry.get("grade") not in ("Citizen", "Youth Peer"):
            continue
        sched_nid = get_npc_scheduled_node_id(
            entry, current_minute=safe_min, scen_key=scen_key, current_day=curr_day, session_id=session_id
        )
        if sched_nid == target_venue:
            # Prefer actual clerks/owners of this venue over regular customers
            arch = infer_town_schedule_archetype(entry)
            is_staff = arch in (
                "day_merchant_cafe", "youth_peer_barista", "konbini_day", "konbini_night",
                "afternoon_evening_merchant", "day_merchant_kiosk", "seaside_merchant",
                "day_merchant_restaurant", "day_merchant_clothing", "day_merchant_brand_clothing",
                "day_merchant_accessories", "day_merchant_gift", "evening_merchant_night_market",
                "night_merchant_nightclub", "day_night_merchant_adult_store",
            )
            if is_staff:
                candidates.insert(0, entry)
            else:
                candidates.append(entry)

    if candidates:
        chosen = candidates[0]
        is_peer = (chosen.get("grade") == "Youth Peer")
        affinity = 0
        if is_peer:
            contact = db.get_contact(session_id, chosen["name"])
            affinity = int((contact or {}).get("relationship_score") or 0)
        has_discount = is_peer and affinity >= 40
        return {
            "name": chosen["name"],
            "role": chosen["role"],
            "description": chosen.get("personality_summary", ""),
            "is_student_part_timer": is_peer,
            "affinity": affinity,
            "price_multiplier": 0.90 if has_discount else 1.0,
            "pricing_badge": "10% Friend Hookup" if has_discount else None,
        }

    return None
