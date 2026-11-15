# German (de) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("video", "videoclip", "aufnahme", "clip"),
    "digital_photo": ("foto", "aufnahme", "selfie", "schnappschuss"),

    # 1. Accessories
    "accessories": ("ring", "armreif", "armband"),
    "amulet": ("amulett", "halskette", "medaillon", "kette", "talisman"),

    # 2. Weapons & Tools
    "phone": ("telefon", "smartphone", "handy"),
    "backpack": ("rucksack", "tasche", "beutel", "ranzen"),
    "wand": ("zauberstab", "stab", "*stab", "szepter"),
    "grimoire": ("grimoire", "zauberbuch", "*buch", "tome", "magiebuch"),
    "bow": ("bogen", "*bogen", "langbogen", "kurzbogen", "armbrust", "*armbrust"),
    "gun": ("pistole", "gewehr", "*gewehr", "flinte", "muskete", "blaster"),
    "dagger": ("dolch", "*dolch", "messer", "*messer", "klinge", "*klinge", "keris", "tanto"),
    "axe": ("axt", "*axt", "streitaxt", "beil"),
    "hammer": ("hammer", "*hammer", "kriegshammer", "streitkolben", "keule"),
    "spear": ("speer", "*speer", "lanze", "*lanze", "hellebarde", "*hellebarde", "spieß", "*spieß", "dreizack"),
    "whip": ("peitsche", "kette"),
    "sword": ("schwert", "*schwert", "großschwert", "zweihänder", "*zweihänder", "degen", "krummsäbel", "katana", "langschwert"),

    # 3. Clothing / Armor / Headwear
    "crown": ("krone", "diadem", "tiara"),
    "glasses": ("brille", "monokel", "visier"),
    "top_hat": ("zylinder", "melone", "hut"),
    "helm": ("helm", "*helm", "haube", "visierhelm", "maske", "kapuze"),
    "cap": ("mütze", "kappe", "barett"),
    "boots": ("stiefel", "*stiefel", "schuhe", "*schuhe", "sandalen", "beinschienen", "treter"),
    "gloves": ("handschuhe", "*handschuhe", "panzerhandschuhe", "armschienen"),
    "pants": ("hose", "*hose", "beinkleid", "rock", "gamaschen"),
    "armor": (
        "harnisch", "*harnisch", "rüstung", "*rüstung", "brustplatte", "kettenhemd", "*panzer", "schuppenpanzer", "gewand", "robe",
        "tunika", "mantel", "jacke", "wams", "weste", "panzer", "kimono", "haori", "kebaya", "songket"
    ),
    "shield": ("schild", "*schild", "rundschild", "buckler", "turmschild"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("waffe",),
    "slot_shield": ("schild",),
    "slot_head": ("helm", "kopf"),
    "slot_bottom": ("unterteil", "hose"),
    "slot_gloves": ("handschuhe",),
    "slot_shoes": ("schuhe", "stiefel"),
    "slot_top": ("oberteil",),
    "slot_armor": ("rüstung", "harnisch"),

    # 5. Consumables & Quest Items
    "boba": ("bubble tea",),
    "coffee": ("kaffee", "espresso"),
    "tea": ("tee", "kräutertee"),
    "wine": ("wein", "rotwein"),
    "beer": ("bier", "ale", "met"),
    "drink": ("getränk", "wasser", "trank"),
    "food": ("essen", "proviant", "brot", "fleisch"),
    "health": ("heilung", "gesundheit", "lebenselixier", "verband", "salbe", "heiltrank", "*heiltrank"),
    "mana": ("mana", "manatrank", "*manatrank"),
    "potion": ("trank", "*trank", "elixier", "*elixier", "phiole", "mixtur", "heiltrank", "räucherwerk", "geweihtes salz", "kaffir-limette", "gurke", "tofu", "talisman", "eisenamulett"),
    "quest": ("schlüssel", "karte", "brief", "schriftrolle", "dokument", "relikt", "suzu", "serunai", "pusaka", "fuchsfeuer-glocke", "bambusflöte"),
}

TWO_HANDED_ARCHETYPES = (
    "zweihänder", "großschwert", "hellebarde", "lanze", "langbogen", "armbrust", "kriegshammer", "gewehr"
)

TWO_HANDED_KEYWORDS = (
    "zweihändig", "zweihänder", "großschwert", "hellebarde", "langbogen", "armbrust", "kriegshammer"
)

ITEM_LEMMAS = {
    "weapons": [
        "schwert", "großschwert", "zweihänder", "dolch", "messer", "axt", "streitaxt", "hammer",
        "kriegshammer", "speer", "lanze", "hellebarde", "bogen", "armbrust", "zauberstab", "stab",
        "pistole", "gewehr"
    ],
    "shields": [
        "schild", "rundschild", "buckler", "turmschild"
    ],
    "head": [
        "helm", "mütze", "kapuze", "krone", "diadem", "brille", "maske"
    ],
    "armor": [
        "harnisch", "rüstung", "brustplatte", "kettenhemd", "panzer", "gewand", "robe", "tunika",
        "mantel", "jacke", "wams"
    ],
    "pants": [
        "hose", "beinkleid", "rock", "gamaschen"
    ],
    "gloves": [
        "handschuhe", "panzerhandschuhe", "armschienen"
    ],
    "shoes": [
        "stiefel", "schuhe", "sandalen", "beinschienen"
    ],
    "accessories": [
        "ring", "amulett", "halskette", "medaillon", "armreif", "armband", "talisman"
    ],
    "usables": [
        "trank", "elixier", "heiltrank", "manatrank", "brot", "fleisch", "wasser", "tee", "wein", "bier"
    ],
    "tomes_and_quests": [
        "schriftrolle", "buch", "zauberbuch", "grimoire", "schlüssel", "karte", "brief", "dokument", "relikt"
    ],
}

ENEMY_AFFIXES = {
    "Volatile": "Flüchtig",
    "Overclocked": "Übertaktet",
    "Vampiric": "Vampirisch",
    "Phasing": "Phasend",
    "Corrosive": "Ätzend",
    "Grounded": "Geerdet",
    "Hydro-Shielded": "Wassergeschirmt",
    "Tempest-Wreathed": "Sturmgewoben",
}

REVERSE_ENEMY_AFFIXES = {v.lower(): k for k, v in ENEMY_AFFIXES.items()}

DIALOGUE_EXIT_PHRASES = (
    "verabschieden", "gehen", "gespräch beenden", "weggehen", "sich verabschieden",
    "lebe wohl", "abwenden", "verlassen"
)

DIALOGUE_INIT_PREFIXES = (
    "sprich mit ", "spreche mit ", "rede mit ", "grüße ", "ansprechen ", "nähere dich "
)

MOVEMENT_PREFIXES = (
    "gehe zu ", "gehe nach ", "reise nach ", "betrete ", "begib dich zu ", "zurückkehren nach "
)


REALTY_LABELS = {
    "app_name": "Immobilien & Urkunden",
    "app_sub": "Unterschlüpfe & Schlüssel",
    "tab_owned": "Meine Wohnsitze",
    "tab_market": "Immobilienmarkt",
    "badge_starter": "Startquartier",
    "badge_owned": "Eigener Wohnsitz",
    "badge_for_sale": "Zu Verkaufen",
    "primary_home": "Hauptwohnsitz",
    "set_primary": "Als Hauptwohnsitz",
    "buy_deed": "Urkunde Kaufen",
    "deed_owned": "Im Besitz",
    "give_spare_key": "Schlüssel Geben",
    "revoke_key": "Schlüssel Entziehen",
    "spare_keys_label": "Zweitschlüssel-Inhaber",
    "starter_spare_key_note": "Zugewiesene Fraktionsquartiere wechseln beim Transfer. Kaufe eine Eigentumsurkunde, um Zweitschlüssel zu vergeben.",
    "no_deeds_owned": "Noch keine dauerhaften Eigentumsurkunden im Besitz.",
    "no_eligible_contacts": "Erreiche Zuneigung 70+ oder eine Romanze, um einen Zweitschlüssel zu vergeben.",
    "purchased_ok": "Eigentumsurkunde erworben!",
    "purchase_failed": "Immobilienkauf fehlgeschlagen.",
    "primary_updated": "Hauptwohnsitz aktualisiert.",
    "key_granted": "Zweitschlüssel überreicht!",
    "key_revoked": "Zweitschlüssel entzogen.",
}


FOLKLORE_SANCTUARY_LABELS = {
    "kitsune_spirit_merchant": "Inari-Geisterapotheke",
    "bunian_pusaka_merchant": "Balai-Pusaka-Erbstückschmiede",
    "ranger_station_outfitter": "Waldpfad-Ausrüster",
    "spirit_relay_badge": "Geister-Relais-Bote",
    "veil_unattuned_badge": "Weltliche Schwelle",
    "veil_attuned_badge": "Geisterschleier Eingestimmt",
    "twilight_veil_badge": "Dämmerungs-Schleierlichtung",
    "leyline_passage_badge": "Leylinien-Geisterpfad",
    "sanctuary_pact_warning": "Nichtangriffspakt des Heiligtums gebrochen — bringe 100g heilige Sühneopfer an der äußeren Schwelle dar.",
}


QUEST_UI_LABELS = {
    "main_objective": "Hauptziel",
    "optional_routes": "Optionale Taktische Routen",
    "peak_chapter": "Höhepunkt-Kapitel",
    "chronicle_tapestry": "Chronik-Wandteppich",
    "fallen_world_ch11": "Gefallene Welt — Kapitel 11 Widerstands-Epilog",
    "peak_scar": "Höhepunkt-Narbe",
    "liberation_op": "Befreiungsoperation",
    "optional_aid": "Taktische Hilfe",
    "optional_bypass": "Infiltrations-Umgehung",
    "optional_alternative": "Alternatives Ziel",
    "optional_threatened": "Gefahr / Extraktion",
    "bonus_claimed": "Bonus Beansprucht",
    "failed_route": "Gescheiterte Route",
    "locked_out": "Gesperrt",
    "fallen_world_epilogue": "Gefallene Welt — Widerstands-Epilog",
    "base_reward_note": "Grundlegende Abschlussbelohnungen",
    "threat_clock": "Bedrohungsuhr",
    "threat_paused": "Pausiert (Höhepunkt)",
    "threat_dormant": "Ruhend bis Kapitelbeginn",
    "threat_reinforced": "Verstärkung",
    "threat_pushed_back": "Bedrohung Verzögert (-1)",
    "threat_scar_pending": "Kapitel-Narbenrisiko",
    "clue_sources": "Hinweisquellen",
    "source_open": "Offen",
    "source_burned": "Verbrannt",
    "source_cold": "Kalt",
    "source_claimed": "Gesichert",
    "source_bonus": "Bonus-Spur",
}

PACT_UI_LABELS = {
    "title": "Entitätsverträge & Teufelspakte",
    "subtitle": "Null-MP-Bündnisse • Blut- & Tributregister",
    "tab_active": "Aktive Bündnisse",
    "tab_discover": "Entdecken & Prüfen",
    "tab_compendium": "Patron-Kompendium",
    "slots_label": "Paktplätze",
    "remote_ready": "Fernkommunion Bereit",
    "remote_blocked": "Erfordert Heiligtum / Quartier außerhalb des Kampfes",
    "appraisal_favored": "Begünstigt (0.65x Kosten • Stufe II/III Sofort)",
    "appraisal_neutral": "Neutral (1.0x Standardbedingungen)",
    "appraisal_disdained": "Verachtet (1.50x Aufschlag • Stufe III Gesperrt)",
    "sign_btn": "Bündnis Siegeln",
    "upgrade_btn": "Stufe Vertiefen",
    "feed_btn": "Kommunion / Tribut Zahlen",
    "sever_scrub_btn": "Klinik- / Schrein-Reinigung",
    "sever_exorcism_btn": "Manifestation Herausfordern (Exorzismus)",
    "pact_bound_badge": "[Paktgebunden]",
    "lethal_overdraw": "Tödliche Überziehung (Blutschuld)",
    "breach_stage_1": "Verstimmt — Blutschuld Aktiv (24h)",
    "breach_stage_2": "Gewaltsame Trennung — Seelennarbe",
    "contracted_badge": "Vertrag Geschlossen",
    "currently_bound": "Gebunden",
}
