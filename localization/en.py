# English (en) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("video", "clip", "recording"),
    "digital_photo": ("photo", "snapshot", "selfie"),
    
    # 1. Accessories
    "accessories": ("ring", "amulet", "bracelet", "necklace", "pendant"),
    "amulet": ("amulet", "necklace", "pendant", "rosary", "locket", "beads"),

    # 2. Weapons & Tools
    "phone": ("phone", "smartphone", "cellphone"),
    "backpack": ("backpack", "pack", "bag", "rucksack", "satchel"),
    "wand": ("wand", "staff", "stave", "rod", "scepter", "sceptre"),
    "grimoire": ("grimoire", "tome", "spellbook"),
    "bow": ("bow", "crossbow"),
    "gun": ("pistol", "rifle", "blaster", "gun", "revolver", "shotgun", "sniper"),
    "dagger": ("dagger", "knife", "blade", "cleaver", "scalpel", "stiletto", "keris", "tanto"),
    "axe": ("axe", "hatchet"),
    "hammer": ("hammer", "mace", "warhammer", "club", "baton"),
    "spear": ("spear", "halberd", "lance", "trident", "pike"),
    "whip": ("whip", "chain"),
    "sword": ("sword", "greatsword", "rapier", "katana", "scimitar", "broadsword"),

    # 3. Clothing / Armor / Headwear
    "crown": ("crown", "coronet", "diadem", "tiara"),
    "glasses": ("glasses", "spectacles", "monocle", "visor", "goggles", "hud"),
    "top_hat": ("top hat", "fedora", "bowler hat", "trilby"),
    "helm": ("helm", "helmet", "cowl", "hood", "gas mask", "respirator", "sallet", "armet", "casque"),
    "cap": ("cap", "beanie", "snapback", "beret"),
    "boots": ("boots", "shoes", "sneakers", "sandals", "loafers", "sabatons", "treads", "footwear", "greaves", "creepers", "sliders"),
    "gloves": ("gloves", "gauntlets", "bracers", "mittens", "cuff", "hand wraps"),
    "pants": ("pants", "trousers", "leggings", "skirt", "slacks", "jeans", "shorts"),
    "armor": (
        "breastplate", "tunic", "robe", "chest", "cuirass", "mail", "chainmail",
        "ringmail", "scalemail", "shirt", "coat", "jacket", "suit", "vest", "blazer",
        "cardigan", "duster", "jumpsuit", "uniform", "windbreaker", "hoodie", "sweater",
        "parka", "cloak", "kimono", "haori", "kebaya", "songket", "baju sikap"
    ),
    "shield": ("shield", "aegis", "buckler"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("weapon",),
    "slot_shield": ("shield",),
    "slot_head": ("head", "helmet"),
    "slot_bottom": ("bottom",),
    "slot_gloves": ("gloves",),
    "slot_shoes": ("shoes",),
    "slot_top": ("top",),
    "slot_armor": ("armor",),

    # 5. Consumables & Quest Items
    "boba": ("boba", "bubble tea", "milk tea"),
    "coffee": ("coffee", "latte", "espresso", "cappuccino", "cold brew"),
    "tea": ("tea", "matcha", "oolong", "jasmine", "herbal infusion"),
    "wine": ("wine", "chalice"),
    "beer": ("ale", "beer", "cider", "mead"),
    "drink": ("soda", "fizz", "ramune", "smoothie", "juice", "drink", "cocktail", "water", "hydrator", "milk"),
    "food": (
        "bento", "ramen", "roast", "stew", "bread", "cake", "cookie", "tart", "pie",
        "snack", "meal", "omakase", "wagyu", "sandwich", "melon pan", "ration", "food", "feast", "cucumber", "tofu", "aburaage", "offering"
    ),
    "health": ("health", "hp", "heal", "bandage", "salve", "stimpack"),
    "mana": ("mana", "mp", "elixir", "ether"),
    "potion": ("potion", "draught", "phial", "consumable", "kaffir lime", "blessed salt", "incense"),
    "quest": (
        "key", "map", "letter", "tome", "book", "scroll", "signet", "chip", "card",
        "keycard", "deck", "terminal", "clipboard", "relic", "lantern", "quest", "key item", "talisman", "iron charm", "ward",
        "suzu", "serunai", "pusaka", "foxfire", "spirit bell", "bamboo flute"
    ),
}

TWO_HANDED_ARCHETYPES = (
    "greatsword", "polearm", "warhammer", "staff", "bow", "crossbow",
    "rifle", "shotgun", "machinegun", "explosive", "longsword", "halberd", "pike"
)

TWO_HANDED_KEYWORDS = (
    "greatsword", "halberd", "pike", "warhammer", "staff", "bow", "crossbow",
    "rifle", "shotgun", "machine gun", "cannon", "rocket", "two-handed", "2h"
)

ENEMY_AFFIXES = {
    "Volatile": "Volatile",
    "Overclocked": "Overclocked",
    "Vampiric": "Vampiric",
    "Phasing": "Phasing",
    "Corrosive": "Corrosive",
    "Grounded": "Grounded",
    "Hydro-Shielded": "Hydro-Shielded",
    "Tempest-Wreathed": "Tempest-Wreathed",
}

DIALOGUE_EXIT_PHRASES = (
    "say goodbye", "take your leave", "part ways", "excuse your", "excuse yourself",
    "leave the conversation", "end the conversation", "wrap up the chat", "step away",
    "bid farewell", "head back to class", "return to what you were doing",
    "walk away", "exit conversation", "farewell"
)

DIALOGUE_INIT_PREFIXES = (
    "speak with ", "speak to ", "talk to ", "talk with ", "consult the ", "consult with ",
    "address the ", "converse with ", "greet ", "chat with ",
    "strike up a conversation with ", "approach and speak with ", "approach and talk to ",
    "approach and greet ", "say hello to ", "say hi to ", "say hello", "say hi",
    "wave to ", "wave at ", "wave towards ", "wave toward ", "call over "
)

MOVEMENT_PREFIXES = (
    "travel to ", "travel toward ", "travel towards ", "travel through ", "travel into ",
    "head to ", "head toward ", "head towards ", "head into ", "head through ",
    "walk to ", "walk toward ", "walk towards ", "walk into ", "walk through ",
    "journey to ", "journey toward ", "journey towards ", "depart toward ",
    "step into ", "step through ", "enter the ", "enter ", "visit the ", "visit ",
    "descend into ", "descend the ", "cross into ", "venture into ",
    "go to ", "move to ", "move into ", "return to ", "leave for ", "make our way to ",
    "make your way to ", "make my way to ", "slip into ", "slip to "
)


REALTY_LABELS = {
    "app_name": "Realty & Deeds",
    "app_sub": "Safehouses & Keys",
    "tab_owned": "My Residences",
    "tab_market": "Market Deeds",
    "badge_starter": "Starter Quarters",
    "badge_owned": "Owned Residence",
    "badge_for_sale": "For Sale",
    "primary_home": "Primary Home",
    "set_primary": "Set Primary",
    "buy_deed": "Buy Deed",
    "deed_owned": "Owned",
    "give_spare_key": "Give Key",
    "revoke_key": "Revoke Key",
    "spare_keys_label": "Spare Key Holders",
    "starter_spare_key_note": "Assigned faction quarters relocate on transfer. Purchase a permanent deed to hand out Spare Keys.",
    "no_deeds_owned": "No permanent property deeds owned yet.",
    "no_eligible_contacts": "Reach Affinity 70+ or romance a contact to give them a Spare Key.",
    "purchased_ok": "Property deed purchased!",
    "purchase_failed": "Property purchase failed.",
    "primary_updated": "Primary Home updated.",
    "key_granted": "Spare key granted!",
    "key_revoked": "Spare key revoked.",
}


FOLKLORE_SANCTUARY_LABELS = {
    "kitsune_spirit_merchant": "Inari Spirit Apothecary",
    "bunian_pusaka_merchant": "Balai Pusaka Heirloom Artisan",
    "ranger_station_outfitter": "Reserve Trail Outfitter",
    "spirit_relay_badge": "Spirit-Relay Messenger",
    "veil_unattuned_badge": "Mundane Threshold",
    "veil_attuned_badge": "Spirit Veil Attuned",
    "twilight_veil_badge": "Twilight Veil Thinning",
    "leyline_passage_badge": "Leyline Spirit Passage",
    "sanctuary_pact_warning": "Sanctuary Non-Aggression Pact broken — offer 100g sacred atonement at the outer threshold.",
}


QUEST_UI_LABELS = {
    "main_objective": "Main Objective",
    "optional_routes": "Optional Tactical Routes",
    "peak_chapter": "Peak Set-Piece",
    "chronicle_tapestry": "Chronicle Tapestry",
    "fallen_world_ch11": "Fallen World — Chapter 11 Resistance Epilogue",
    "peak_scar": "Peak Scar",
    "liberation_op": "Liberation Op",
    "optional_aid": "Tactical Aid",
    "optional_bypass": "Infiltration Bypass",
    "optional_alternative": "Alternative Objective",
    "optional_threatened": "Jeopardy / Extraction",
    "bonus_claimed": "Bonus Claimed",
    "failed_route": "Failed Route",
    "locked_out": "Locked Out",
    "fallen_world_epilogue": "Fallen World — Resistance Epilogue",
    "base_reward_note": "Base Completion Rewards",
    "threat_clock": "Threat Clock",
    "threat_paused": "Paused (Climax)",
    "threat_dormant": "Dormant until Chapter engaged",
    "threat_reinforced": "Reinforcements",
    "threat_pushed_back": "Threat Delayed (-1)",
    "threat_scar_pending": "Chapter Scar Risk",
    "clue_sources": "Clue Avenues",
    "source_open": "Open",
    "source_burned": "Burned",
    "source_cold": "Gone Cold",
    "source_claimed": "Claimed",
    "source_bonus": "Bonus Lead",
    "stage_short": "Stage",
    "aid_active": "Aid Active",
    "shortcut_active": "Shortcut Active",
    "bypassed": "Bypassed",
    "quest_travel_to": "Travel to {dest}",
    "quest_wrap_up_and_head_to": "Wrap up with {npc} and head to {dest}",
}

PACT_UI_LABELS = {
    "title": "Entity Contracts & Devil Pacts",
    "subtitle": "Zero-MP Covenants • Blood & Tribute Ledger",
    "tab_active": "Active Covenants",
    "tab_discover": "Discover & Appraise",
    "tab_compendium": "Patron Compendium",
    "slots_label": "Pact Slots",
    "remote_ready": "Remote Communion Ready",
    "remote_blocked": "Requires Sanctuary / Quarters Outside Combat",
    "appraisal_favored": "Favored (0.65x Cost • Upfront Tier II/III)",
    "appraisal_neutral": "Neutral (1.0x Standard Terms)",
    "appraisal_disdained": "Disdained (1.50x Surcharge • Tier III Locked)",
    "sign_btn": "Forge Covenant",
    "upgrade_btn": "Deepen Tier",
    "feed_btn": "Commune / Pay Tithe",
    "sever_scrub_btn": "Medical / Shrine Scrub",
    "sever_exorcism_btn": "Challenge Manifestation (Exorcism)",
    "pact_bound_badge": "[Pact-Bound]",
    "lethal_overdraw": "Lethal Overdraw (Blood Debt)",
    "breach_stage_1": "Displeased — Blood Debt Active (24h)",
    "breach_stage_2": "Violent Severance — Soul Scar",
    "contracted_badge": "Contracted",
    "currently_bound": "Bound",
}

ANOMALOUS_SITE_UI_LABELS = {
    "unreconnoitered_badge": "[UNRECONNOITERED — Grade {grade}]",
    "unreconnoitered_summary": "Enter this quarantine zone to reconnoiter its Domain Rule, elemental signature, and stabilization anchors.",
    "milestone_10_title": "Outer Cordon Reclamation (10 Sites)",
    "milestone_10_reward": "+15 Faction Promotion Rep & +250G Hazard Grant",
    "milestone_22_title": "Metropolitan Grid Stabilization (22 Sites)",
    "milestone_22_reward": "Field Resonator Upgrade (4 Daily Charges)",
    "milestone_36_title": "Metropolitan Warden Commendation (36/36 Sites)",
    "milestone_36_reward": "+30 Rep, 5 Daily Charges & Warden's Aether Chronometer Relic"
}

CROWD_DENSITY_LABELS = {
    "quiet": "Quiet",
    "moderate": "Moderate",
    "bustling": "Bustling",
    "packed": "Packed",
    "crowd_label": "Crowd",
    "nearby_bystanders": "Nearby Bystanders"
}

STATURE_LABELS = {
    "miniature": "Miniature",
    "short": "Short",
    "below_average": "Below Average",
    "average": "Average",
    "tall": "Tall",
    "towering": "Towering",
}

PHYSIQUE_LABELS = {
    "slim": "Slim",
    "average": "Average",
    "athletic": "Athletic",
    "muscular": "Muscular",
    "voluptuous": "Voluptuous",
    "stocky": "Stocky",
    "chubby": "Chubby",
}

ASSET_TEXTURE_LABELS = {
    "perky": "Perky",
    "firm": "Firm",
    "supple": "Supple",
    "teardrop": "Teardrop",
    "plush": "Plush",
    "pillowy": "Pillowy",
    "bouncy": "Bouncy",
    "delicate": "Delicate",
    "sensitive": "Sensitive",
    "veined": "Veined",
    "smooth": "Smooth",
    "thick": "Thick",
    "heavy": "Heavy",
    "curved": "Curved",
    "tapered": "Tapered",
}

SPECIES_SURFACE_LABELS = {
    "furred": "Downy Fur",
    "scaled": "Micro-Scales",
    "feathered": "Downy Plumage",
    "aquatic": "Glistening Skin",
    "fever_warm": "Fever-Warm Skin",
    "porcelain_silky": "Porcelain-Silky Skin",
    "bio_synthetic": "Bio-Synthetic Skin",
}

REAR_SIZE_LABELS = {
    "flat": "Flat",
    "small": "Compact",
    "average": "Shapely",
    "large": "Plump",
    "huge": "Bountiful",
}

REAR_TEXTURE_LABELS = {
    "firm": "Firm",
    "taut": "Taut",
    "supple": "Supple",
    "rounded": "Rounded",
    "plush": "Plush",
    "jiggly": "Jiggly",
}

BODY_PREFERENCE_LABELS = {
    "smaller_bb": "Smaller Breasts",
    "bigger_bb": "Bigger Breasts",
    "smaller_ass": "Smaller Rear",
    "bigger_ass": "Bigger Rear",
    "taller_partner": "Taller Partners",
    "shorter_partner": "Shorter Partners",
}

SPIRIT_COURT_LABELS = {
    "badge_human_world": "🏙️ Human World",
    "badge_veiled_realm": "⛩️ Veiled Realm",
    "sworn_ally_active_header": "Sworn Ally — 90+ Court Pact",
    "sworn_ally_summon_ready": "3-Turn Combat Summon Active",
    "sworn_ally_stat_bonus": "Passive Stat Aura",
    "autonomous_spirit_court_badge": "Autonomous Spirit Court",
    "spirit_court_non_joinable_note": "Independent Spirit Court — earn standing through deeds, sparring & commissions.",
    "ghoul_track_dark_crime": "Dark Crime (Fast Rep)",
    "ghoul_track_grey_neutral": "Grey-Neutral (Zero Splash)",
    "night_market_wing_selector": "Select a Night Market Wing Stall...",
    "spirit_relay_neon_static_note": "⚡ Neon-Static Leyline Surge: Spirit Relay signals crackle with astral static.",
    "spirit_relay_ghoul_channel": "🦴 Ossuary Bone-Relay Active",
    "pale_wake_toll_waived": "🕯️ Night of the Pale Wake — Ossuary entry toll waived",
    "lantern_tide_ferry_waived": "🏮 Tide of Drifting Lanterns — Ferryman crossing fee waived",
    "event_crisis_commission_badge": "Urgent Realm Crisis",
}
