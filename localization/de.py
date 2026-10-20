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
    "dagger": ("dolch", "*dolch", "messer", "*messer", "klinge", "*klinge"),
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
        "tunika", "mantel", "jacke", "wams", "weste", "panzer"
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
    "potion": ("trank", "*trank", "elixier", "*elixier", "phiole", "mixtur", "heiltrank"),
    "quest": ("schlüssel", "karte", "brief", "schriftrolle", "dokument", "relikt"),
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
