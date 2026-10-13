# Polish (pl) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("nagranie", "wideo", "klip"),
    "digital_photo": ("zdjęcie", "fotografia", "selfie"),

    # 1. Accessories
    "accessories": ("pierścień", "pierścionek", "bransoleta"),
    "amulet": ("naszyjnik", "wisiorek", "korale", "medalion"),

    # 2. Weapons & Tools
    "phone": ("telefon",),
    "backpack": ("plecak", "torba"),
    "wand": ("różdżka", "laska"),
    "grimoire": ("grimuar", "księga"),
    "bow": ("łuk", "kusza"),
    "gun": ("strzelba", "karabin", "pistolet"),
    "dagger": ("sztylet", "nóż", "ostrze"),
    "axe": ("topór", "toporek"),
    "hammer": ("młot", "buława", "pałka"),
    "spear": ("włócznia", "halabarda", "trójząb", "pika"),
    "whip": ("bicz", "łańcuch"),
    "sword": ("miecz", "szpada"),

    # 3. Clothing / Armor / Headwear
    "crown": ("korona", "diadem"),
    "glasses": ("okulary",),
    "top_hat": ("cylinder",),
    "helm": ("hełm", "kaptur", "przyłbica", "maska"),
    "cap": ("czapka", "beret"),
    "boots": ("buty", "trzewiki", "sandały", "nagolenniki", "kozaki", "mokasyny"),
    "gloves": ("rękawice", "karwasze", "rękawiczki"),
    "pants": ("spodnie", "spódnica", "legginsy", "bryczesy"),
    "armor": (
        "zbroja", "napierśnik", "kolczuga", "tunika", "szata", "płaszcz", "kurtka",
        "kamizelka", "mundur", "bluza", "kirys"
    ),
    "shield": ("tarcza", "puklerz", "pawęż"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("broń",),
    "slot_shield": ("tarcza",),
    "slot_head": ("hełm", "głowa"),
    "slot_bottom": ("dół", "spodnie"),
    "slot_gloves": ("rękawice",),
    "slot_shoes": ("buty",),
    "slot_top": ("góra",),
    "slot_armor": ("zbroja",),

    # 5. Consumables & Quest Items
    "boba": (),
    "coffee": ("kawa",),
    "tea": ("herbata",),
    "wine": ("wino",),
    "beer": ("piwo",),
    "drink": ("woda", "napój"),
    "food": ("jedzenie", "chleb", "pieczeń"),
    "health": ("leczenie", "zdrowie", "opatrunek", "balsam", "maść"),
    "mana": ("mana", "eliksir many"),
    "potion": ("mikstura", "eliksir", "zużywalny"),
    "quest": ("klucz", "mapa", "list", "zwój", "relikwia", "dokument"),
}

TWO_HANDED_ARCHETYPES = (
    "miecz dwuręczny", "halabarda", "pika", "łuk", "kusza", "karabin", "strzelba"
)

TWO_HANDED_KEYWORDS = (
    "dwuręczny", "wielki miecz", "pika", "łuk", "kusza", "strzelba", "karabin"
)

ITEM_LEMMAS = {
    "weapons": [
        "miecz", "miecz dwuręczny", "szpada", "katana", "sztylet", "nóż", "ostrze",
        "topór", "toporek", "młot", "buława", "pałka", "włócznia", "halabarda",
        "trójząb", "pika", "łuk", "kusza", "różdżka", "laska", "pistolet", "strzelba", "karabin"
    ],
    "shields": [
        "tarcza", "puklerz", "pawęż"
    ],
    "head": [
        "hełm", "czapka", "kaptur", "korona", "diadem", "okulary", "maska", "przyłbica"
    ],
    "armor": [
        "zbroja", "napierśnik", "kolczuga", "tunika", "szata", "płaszcz", "kurtka",
        "kamizelka", "mundur", "bluza", "kirys"
    ],
    "pants": [
        "spodnie", "spódnica", "legginsy", "bryczesy"
    ],
    "gloves": [
        "rękawice", "karwasze", "naramienniki", "rękawiczki"
    ],
    "shoes": [
        "buty", "trzewiki", "sandały", "nagolenniki", "kozaki", "mokasyny"
    ],
    "accessories": [
        "pierścień", "pierścionek", "amulet", "naszyjnik", "wisiorek", "bransoleta", "korale", "medalion"
    ],
    "usables": [
        "mikstura", "eliksir", "napój", "balsam", "opatrunek", "maść", "jedzenie",
        "chleb", "pieczeń", "herbata", "kawa", "wino", "piwo"
    ],
    "tomes_and_quests": [
        "zwój", "księga", "grimuar", "klucz", "mapa", "list", "dokument", "relikwia"
    ],
}

ENEMY_AFFIXES = {
    "Volatile": "Niestabilny",
    "Overclocked": "Podkręcony",
    "Vampiric": "Wampiryczny",
    "Phasing": "Fazujący",
    "Corrosive": "Żrący",
    "Grounded": "Uziemiony",
    "Hydro-Shielded": "Hydro-Tarcza",
    "Tempest-Wreathed": "Spowity Burzą",
}

REVERSE_ENEMY_AFFIXES = {v.lower(): k for k, v in ENEMY_AFFIXES.items()}

DIALOGUE_EXIT_PHRASES = (
    "pożegnaj się", "odejdź", "zakończ rozmowę", "odsuń się", "zostaw rozmowę",
    "wróć do swoich zajęć", "żegnaj", "zegnaj", "wymów się", "odejdź od"
)

DIALOGUE_INIT_PREFIXES = (
    "porozmawiaj z ", "porozmawiaj ze ", "pogadaj z ", "pogadaj ze ", "odezwij się do ",
    "przywitaj się z ", "podejdź do ", "zagadaj do ", "skonsultuj się z "
)

MOVEMENT_PREFIXES = (
    "udaj się do ", "idź do ", "podróżuj do ", "kieruj się do ", "wejdź do ",
    "wejdź w ", "przejdź do ", "odwiedź "
)
