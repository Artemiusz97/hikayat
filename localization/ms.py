# Malay (ms) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("video", "klip", "rakaman"),
    "digital_photo": ("foto", "gambar", "swafoto"),

    # 1. Accessories
    "accessories": ("cincin", "tangkal", "loket", "rantai", "gelang", "subang"),
    "amulet": ("tangkal", "loket", "rantai"),

    # 2. Weapons & Tools
    "phone": ("telefon", "telefon pintar"),
    "backpack": ("beg", "galas", "beg sandang"),
    "wand": ("tongkat sakti", "tongkat"),
    "grimoire": ("kitab", "buku sihir"),
    "bow": ("busur", "panah", "panah silang"),
    "gun": ("senapang", "pistol"),
    "dagger": ("keris", "parang", "pisau", "belati"),
    "axe": ("kapak",),
    "hammer": ("tukul", "gada"),
    "spear": ("tombak", "lembing"),
    "whip": ("cemeti", "rantai"),
    "sword": ("pedang", "pedang panjang"),

    # 3. Clothing / Armor / Headwear
    "crown": ("mahkota", "tiara"),
    "glasses": ("cermin mata",),
    "top_hat": ("topi tinggi",),
    "helm": ("topi keledar", "topeng", "serban"),
    "cap": ("topi", "songkok", "kopiah"),
    "boots": ("kasut", "but", "sandal", "terompah", "pelindung kaki"),
    "gloves": ("sarung tangan", "pelindung lengan"),
    "pants": ("seluar", "kain", "sarung", "seluar panjang"),
    "armor": (
        "baju perisai", "perisai dada", "baju besi", "baju zirah", "jubah", "baju", "jaket", "kot",
        "pakaian seragam", "rompi"
    ),
    "shield": ("perisai", "perisai bulat", "perisai kayu"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("senjata",),
    "slot_shield": ("perisai",),
    "slot_head": ("kepala", "topi"),
    "slot_bottom": ("bawah", "seluar"),
    "slot_gloves": ("sarung tangan",),
    "slot_shoes": ("kasut",),
    "slot_top": ("atas", "baju"),
    "slot_armor": ("baju perisai", "baju zirah", "baju besi", "perisai dada"),

    # 5. Consumables & Quest Items
    "boba": (),
    "coffee": ("kopi",),
    "tea": ("teh",),
    "wine": ("wain",),
    "beer": ("bir",),
    "drink": ("air", "minuman"),
    "food": ("makanan", "roti", "daging"),
    "health": ("nyawa", "kesihatan", "pemulihan", "penawar", "ubat"),
    "mana": ("mana", "ramuan mana"),
    "potion": ("ramuan", "penawar", "ubat"),
    "quest": ("kunci", "peta", "surat", "artifak", "manuskrip"),
}

TWO_HANDED_ARCHETYPES = (
    "pedang dua tangan", "pedang besar", "lembing", "busur", "panah silang", "senapang"
)

TWO_HANDED_KEYWORDS = (
    "dua tangan", "pedang besar", "lembing", "busur", "panah silang", "senapang"
)

ITEM_LEMMAS = {
    "weapons": [
        "pedang", "pedang panjang", "keris", "parang", "pisau", "belati", "kapak",
        "tukul", "gada", "tombak", "lembing", "busur", "panah", "tongkat sakti",
        "senapang", "pistol", "panah silang"
    ],
    "shields": [
        "perisai", "perisai bulat", "perisai kayu"
    ],
    "head": [
        "topi keledar", "topi", "tudung", "mahkota", "serban", "cermin mata", "topeng"
    ],
    "armor": [
        "baju perisai", "baju besi", "perisai dada", "baju zirah", "jubah", "baju", "jaket", "kot",
        "pakaian seragam", "rompi"
    ],
    "pants": [
        "seluar", "kain", "sarung", "seluar panjang"
    ],
    "gloves": [
        "sarung tangan", "pelindung lengan"
    ],
    "shoes": [
        "kasut", "but", "sandal", "terompah", "pelindung kaki"
    ],
    "accessories": [
        "cincin", "tangkal", "loket", "rantai", "gelang", "subang"
    ],
    "usables": [
        "ramuan", "penawar", "ubat", "minuman", "air", "makanan", "roti",
        "daging", "teh", "kopi"
    ],
    "tomes_and_quests": [
        "kitab", "manuskrip", "surat", "kunci", "peta", "buku sihir", "artifak"
    ],
}

ENEMY_AFFIXES = {
    "Volatile": "Meruap",
    "Overclocked": "Terlebih Pacu",
    "Vampiric": "Vampirik",
    "Phasing": "Memfasa",
    "Corrosive": "Mengkakis",
    "Grounded": "Terbumi",
    "Hydro-Shielded": "Berperisai-Air",
    "Tempest-Wreathed": "Dibalut Ribut",
}

REVERSE_ENEMY_AFFIXES = {v.lower(): k for k, v in ENEMY_AFFIXES.items()}

DIALOGUE_EXIT_PHRASES = (
    "ucapkan selamat tinggal", "beredar", "tinggalkan perbualan", "tamatkan perbualan",
    "undur diri", "selamat tinggal", "minta diri", "berlalu pergi"
)

DIALOGUE_INIT_PREFIXES = (
    "bercakap dengan ", "berbual dengan ", "sapa ", "tegur ", "hampiri dan bercakap dengan ",
    "berbincang dengan ", "temui "
)

MOVEMENT_PREFIXES = (
    "pergi ke ", "menuju ke ", "berjalan ke ", "masuk ke ", "melangkah ke ",
    "lawati ", "kembali ke "
)
