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
    "dagger": ("sztylet", "nóż", "ostrze", "keris", "tanto"),
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
        "kamizelka", "mundur", "bluza", "kirys", "kimono", "haori", "kebaya", "songket"
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
    "potion": ("mikstura", "eliksir", "zużywalny", "kadzidło", "święcona sól", "limonka kaffir", "ogórek", "tofu", "talizman", "żelazny amulet"),
    "quest": ("klucz", "mapa", "list", "zwój", "relikwia", "dokument", "suzu", "serunai", "pusaka", "lisi dzwonek", "bambusowy flet"),
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
        "kamizelka", "mundur", "bluza", "kirys", "kimono", "haori", "kebaya", "songket"
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


REALTY_LABELS = {
    "app_name": "Nieruchomości i Akty",
    "app_sub": "Kryjówki i Klucze",
    "tab_owned": "Moje Rezydencje",
    "tab_market": "Oferty Rynkowe",
    "badge_starter": "Kwatera Startowa",
    "badge_owned": "Własna Rezydencja",
    "badge_for_sale": "Na Sprzedaż",
    "primary_home": "Główny Dom",
    "set_primary": "Ustaw Główny",
    "buy_deed": "Kup Akt",
    "deed_owned": "Posiadane",
    "give_spare_key": "Daj Klucz",
    "revoke_key": "Odbierz Klucz",
    "spare_keys_label": "Posiadacze Zapasowego Klucza",
    "starter_spare_key_note": "Kwatery frakcyjne zmieniają się przy transferze. Kup stały akt własności, aby wręczać zapasowe klucze.",
    "no_deeds_owned": "Nie posiadasz jeszcze stałych aktów własności.",
    "no_eligible_contacts": "Osiągnij Więź 70+ lub romans z kontaktem, aby wręczyć zapasowy klucz.",
    "purchased_ok": "Zakupiono akt własności nieruchomości!",
    "purchase_failed": "Nie udało się kupić nieruchomości.",
    "primary_updated": "Zaktualizowano Główny Dom.",
    "key_granted": "Przekazano zapasowy klucz!",
    "key_revoked": "Odebrano zapasowy klucz.",
}


FOLKLORE_SANCTUARY_LABELS = {
    "kitsune_spirit_merchant": "Duchowa Apteka Inari",
    "bunian_pusaka_merchant": "Rzemieślnik Dziedzictwa Balai Pusaka",
    "ranger_station_outfitter": "Kwatermistrz Szlaku Rezerwatu",
    "spirit_relay_badge": "Duchowy Przekaźnik",
    "veil_unattuned_badge": "Zwyczajny Próg",
    "veil_attuned_badge": "Zasłona Duchów Dostrojona",
    "twilight_veil_badge": "Przerzedzenie Zasłony o Zmierzchu",
    "leyline_passage_badge": "Duchowe Przejście Linii Mocy",
    "sanctuary_pact_warning": "Pakt o Nieagresji Sanktuarium złamany — złóż świętą ofiarę 100g u zewnętrznego progu.",
}


QUEST_UI_LABELS = {
    "main_objective": "Cel Główny",
    "optional_routes": "Opcjonalne Ścieżki Taktyczne",
    "peak_chapter": "Kulminacja",
    "chronicle_tapestry": "Gobelin Kroniki",
    "fallen_world_ch11": "Upadły Świat — Rozdział 11: Ruch Oporu",
    "peak_scar": "Blizna Kulminacji",
    "liberation_op": "Operacja Wyzwolenia",
    "optional_aid": "Wsparcie Taktyczne",
    "optional_bypass": "Obejście / Infiltracja",
    "optional_alternative": "Cel Alternatywny",
    "optional_threatened": "Zagrożenie / Ewakuacja",
    "bonus_claimed": "Premia Odebrana",
    "failed_route": "Ścieżka Przerwana",
    "locked_out": "Zablokowane",
    "fallen_world_epilogue": "Upadły Świat — Epilog Ruchu Oporu",
    "base_reward_note": "Podstawowe Nagrody za Ukończenie",
    "threat_clock": "Zegar Zagrożenia",
    "threat_paused": "Wstrzymany (Kulminacja)",
    "threat_dormant": "Uśpiony do rozpoczęcia rozdziału",
    "threat_reinforced": "Posiłki Wroga",
    "threat_scar_pending": "Ryzyko Blizny Rozdziału",
    "clue_sources": "Tropy i Źródła",
    "source_open": "Otwarty",
    "source_burned": "Spalony",
    "source_cold": "Wygasł",
    "source_claimed": "Zdobyty",
    "source_bonus": "Dodatkowy Trop",
}

PACT_UI_LABELS = {
    "title": "Kontrakty Bytów i Pakty Diabelskie",
    "subtitle": "Przymierza 0 MP • Księga Krwi i Danin",
    "tab_active": "Aktywne Przymierza",
    "tab_discover": "Odkryj i Oceń",
    "tab_compendium": "Kompendium Patronów",
    "slots_label": "Miejsca na Pakty",
    "remote_ready": "Zdalna Komunia Dostępna",
    "remote_blocked": "Wymaga Sanktuarium lub Kwatery poza Walką",
    "appraisal_favored": "Przychylny (Koszt 0.65x • Odblokowany Krąg II/III)",
    "appraisal_neutral": "Neutralny (Standardowe Warunki 1.0x)",
    "appraisal_disdained": "Wzgardzony (Dopłata 1.50x • Krąg III Zablokowany)",
    "sign_btn": "Zawrzyj Przymierze",
    "upgrade_btn": "Pogłęb Krąg",
    "feed_btn": "Komunia / Złóż Daninę",
    "sever_scrub_btn": "Oczyszczenie Kliniczne / Świątynne",
    "sever_exorcism_btn": "Wyzwij Manifestację (Egzorcyzm)",
    "pact_bound_badge": "[Związany Paktem]",
    "lethal_overdraw": "Śmiertelny Dług Krwi",
    "breach_stage_1": "Rozgniewany — Aktywny Dług Krwi (24h)",
    "breach_stage_2": "Gwałtowne Zerwanie — Blizna Duszy",
    "contracted_badge": "Związano Paktem",
    "currently_bound": "Aktywny Pakt",
}
