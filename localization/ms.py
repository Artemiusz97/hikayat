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
        "pakaian seragam", "rompi", "kebaya", "songket", "baju sikap", "kimono", "haori"
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
    "potion": ("ramuan", "penawar", "ubat", "limau purut", "garam berkat", "kemenyan", "timun", "tauhu", "tangkal", "azimat besi"),
    "quest": ("kunci", "peta", "surat", "artifak", "manuskrip", "suzu", "serunai", "pusaka", "loceng musang", "api musang"),
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
        "pakaian seragam", "rompi", "kebaya", "songket", "baju sikap", "kimono", "haori"
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


REALTY_LABELS = {
    "app_name": "Hartanah & Geran",
    "app_sub": "Rumah Selamat & Kunci",
    "tab_owned": "Kediaman Saya",
    "tab_market": "Senarai Geran",
    "badge_starter": "Kuarters Permulaan",
    "badge_owned": "Kediaman Milikan",
    "badge_for_sale": "Untuk Dijual",
    "primary_home": "Kediaman Utama",
    "set_primary": "Jadikan Utama",
    "buy_deed": "Beli Geran",
    "deed_owned": "Dimiliki",
    "give_spare_key": "Beri Kunci",
    "revoke_key": "Tarik Kunci",
    "spare_keys_label": "Pemegang Kunci Pendua",
    "starter_spare_key_note": "Kuarters faksi berpindah apabila bertukar agensi. Beli geran kekal untuk memberi Kunci Pendua.",
    "no_deeds_owned": "Belum memiliki sebarang geran hartanah kekal.",
    "no_eligible_contacts": "Capai Keakraban 70+ atau hubungan romantis untuk memberi Kunci Pendua.",
    "purchased_ok": "Geran hartanah berjaya dibeli!",
    "purchase_failed": "Pembelian hartanah gagal.",
    "primary_updated": "Kediaman Utama dikemas kini.",
    "key_granted": "Kunci pendua diserahkan!",
    "key_revoked": "Kunci pendua ditarik balik.",
}


FOLKLORE_SANCTUARY_LABELS = {
    "kitsune_spirit_merchant": "Apotekari Roh Inari",
    "bunian_pusaka_merchant": "Tukang Warisan Balai Pusaka",
    "ranger_station_outfitter": "Pembekal Denai Hutan Simpan",
    "spirit_relay_badge": "Utusan Geganti Roh",
    "veil_unattuned_badge": "Ambang Zahir Biasa",
    "veil_attuned_badge": "Hijab Alam Ghaib Terbuka",
    "twilight_veil_badge": "Hijab Senja Menipis",
    "leyline_passage_badge": "Laluan Roh Garis Ley",
    "sanctuary_pact_warning": "Perjanjian Damai Tempat Suci dilanggar — persembahkan tebusan suci 100g di ambang luar.",
}


QUEST_UI_LABELS = {
    "main_objective": "Objektif Utama",
    "optional_routes": "Laluan Taktikal Pilihan",
    "peak_chapter": "Kemuncak Bab",
    "chronicle_tapestry": "Tenunan Hikayat",
    "fallen_world_ch11": "Dunia Tumbang — Epilog Penentangan Bab 11",
    "peak_scar": "Parut Kemuncak",
    "liberation_op": "Operasi Pembebasan",
    "optional_aid": "Bantuan Taktikal",
    "optional_bypass": "Laluan Pintas / Penyusupan",
    "optional_alternative": "Objektif Alternatif",
    "optional_threatened": "Bahaya / Pengekstrakan",
    "bonus_claimed": "Bonus Dituntut",
    "failed_route": "Laluan Gagal",
    "locked_out": "Terkunci",
    "fallen_world_epilogue": "Dunia Tumbang — Epilog Penentangan",
    "base_reward_note": "Ganjaran Asas Penyiapan",
    "threat_clock": "Jam Ancaman",
    "threat_paused": "Dijeda (Kemuncak)",
    "threat_dormant": "Pegun sehingga bab dimulakan",
    "threat_reinforced": "Bala Bantuan",
    "threat_pushed_back": "Ancaman Ditunda (-1)",
    "threat_scar_pending": "Risiko Parut Bab",
    "clue_sources": "Sumber Petunjuk",
    "source_open": "Terbuka",
    "source_burned": "Hangus",
    "source_cold": "Terputus",
    "source_claimed": "Diperoleh",
    "source_bonus": "Petunjuk Bonus",
}

PACT_UI_LABELS = {
    "title": "Kontrak Entiti & Perjanjian Iblis",
    "subtitle": "Perjanjian Sifar-MP • Lejar Darah & Persembahan",
    "tab_active": "Perjanjian Aktif",
    "tab_discover": "Temui & Nilai",
    "tab_compendium": "Kompendium Penaung",
    "slots_label": "Slot Perjanjian",
    "remote_ready": "Komuni Jarak Jauh Sedia",
    "remote_blocked": "Perlu Tempat Suci / Kuarters di Luar Pertempuran",
    "appraisal_favored": "Diperkenan (Kos 0.65x • Tahap II/III Terbuka)",
    "appraisal_neutral": "Neutral (Syarat Biasa 1.0x)",
    "appraisal_disdained": "Dibenci (Caj 1.50x • Tahap III Terkunci)",
    "sign_btn": "Meterai Perjanjian",
    "upgrade_btn": "Tingkatkan Tahap",
    "feed_btn": "Komuni / Bayar Ufti",
    "sever_scrub_btn": "Pembersihan Klinik / Kuil",
    "sever_exorcism_btn": "Cabar Manifestasi (Eksorsisme)",
    "pact_bound_badge": "[Terikat Perjanjian]",
    "lethal_overdraw": "Hutang Darah Maut",
    "breach_stage_1": "Murka — Hutang Darah Aktif (24j)",
    "breach_stage_2": "Pemutusan Ganas — Parut Jiwa",
    "contracted_badge": "Pernah Diikat",
    "currently_bound": "Terikat",
}
