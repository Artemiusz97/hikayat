import pytest
from localization import (
    translate_affix,
    canonicalize_affix,
    get_all_item_lemmas,
    get_all_dialogue_exit_phrases,
    get_all_movement_prefixes,
)
from character_data import get_item_icon
from mechanics.combat.equipment.metadata import is_two_handed
from mechanics.narrative.intent import is_conversational_exit
from mechanics.combat.enemies import generate_scenario_enemy


def test_affix_translation_and_canonicalization():
    # English default
    assert translate_affix("Volatile", "en") == "Volatile"
    assert translate_affix("Volatile") == "Volatile"

    # Polish
    assert translate_affix("Volatile", "pl") == "Niestabilny"
    assert translate_affix("Overclocked", "pl") == "Podkręcony"
    assert translate_affix("Corrosive", "pl") == "Żrący"

    # Malay
    assert translate_affix("Volatile", "ms") == "Meruap"
    assert translate_affix("Overclocked", "ms") == "Terlebih Pacu"
    assert translate_affix("Corrosive", "ms") == "Mengkakis"

    # Canonicalization
    assert canonicalize_affix("Niestabilny") == "Volatile"
    assert canonicalize_affix("niestabilny") == "Volatile"
    assert canonicalize_affix("Meruap") == "Volatile"
    assert canonicalize_affix("meruap") == "Volatile"
    assert canonicalize_affix("Volatile") == "Volatile"


def test_item_icon_multilingual_lemmas():
    # Polish items
    assert get_item_icon("Żelazny miecz") == "⚔️"
    assert get_item_icon("Sztylet cienia") == "🗡️"
    assert get_item_icon("Mikstura leczenia") == "🧪"
    assert get_item_icon("Tarcza rycerska") == "🛡️"
    assert get_item_icon("Czarodziejska laska") == "🪄"
    assert get_item_icon("Księga zaklęć") == "📖"
    assert get_item_icon("Klucz do krypty") == "📜"
    assert get_item_icon("Złoty pierścień") == "💍"
    assert get_item_icon("Skórzane buty") == "👢"
    assert get_item_icon("Stalowy hełm") == "🪖"

    # Malay items
    assert get_item_icon("Pedang Besi") == "⚔️"
    assert get_item_icon("Keris Pusaka") == "🗡️"
    assert get_item_icon("Ramuan Nyawa") == "❤️"
    assert get_item_icon("Ramuan Ajaib") == "🧪"
    assert get_item_icon("Perisai") == "🛡️"
    assert get_item_icon("Perisai Kayu") == "🛡️"
    assert get_item_icon("Baju Perisai") == "👕"
    assert get_item_icon("Tongkat Sakti") == "🪄"
    assert get_item_icon("Kitab Sihir") == "📖"
    assert get_item_icon("Kunci Rahsia") == "📜"
    assert get_item_icon("Cincin Permata") == "💍"
    assert get_item_icon("Kasut Kulit") == "👢"
    assert get_item_icon("Topi Keledar Besi") == "🪖"


def test_two_handed_detection_multilingual():
    # English
    assert is_two_handed({"name": "Iron Greatsword"}) is True
    # Polish
    assert is_two_handed({"name": "Miecz dwuręczny"}) is True
    assert is_two_handed({"name": "Wielki miecz rycerski"}) is True
    assert is_two_handed({"name": "Ciężki łuk myśliwski"}) is True
    # Malay
    assert is_two_handed({"name": "Pedang dua tangan"}) is True
    assert is_two_handed({"name": "Pedang besar pahlawan"}) is True
    assert is_two_handed({"name": "Busur kayu jati"}) is True
    # 1H items should not be two-handed
    assert is_two_handed({"name": "Sztylet"}) is False
    assert is_two_handed({"name": "Keris"}) is False


def test_conversational_exit_intent_multilingual():
    # English
    assert is_conversational_exit("Say goodbye and leave") is True
    # Polish
    assert is_conversational_exit("Pożegnaj się i wyjdź") is True
    assert is_conversational_exit("Zakończ rozmowę z karczmarzem") is True
    assert is_conversational_exit("Odejdź od lady") is True
    # Malay
    assert is_conversational_exit("Ucapkan selamat tinggal dan pergi") is True
    assert is_conversational_exit("Tamatkan perbualan sekarang") is True
    assert is_conversational_exit("Beredar dari kedai") is True


def test_enemy_generation_localized_affixes():
    # Generate tier 3 enemy in Polish
    pl_enemy = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=3, language="pl")
    if pl_enemy.get("affixes"):
        affix_canonical = pl_enemy["affixes"][0]
        expected_pl = translate_affix(affix_canonical, "pl")
        assert expected_pl in pl_enemy["name"]
        assert affix_canonical in ["Volatile", "Overclocked", "Vampiric", "Phasing", "Corrosive", "Grounded", "Hydro-Shielded", "Tempest-Wreathed"]

    # Generate tier 3 enemy in Malay
    ms_enemy = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=3, language="ms")
    if ms_enemy.get("affixes"):
        affix_canonical = ms_enemy["affixes"][0]
        expected_ms = translate_affix(affix_canonical, "ms")
        assert expected_ms in ms_enemy["name"]
        assert affix_canonical in ["Volatile", "Overclocked", "Vampiric", "Phasing", "Corrosive", "Grounded", "Hydro-Shielded", "Tempest-Wreathed"]


def test_locales_architecture_scalability_and_clean_character_data():
    import inspect
    import character_data
    import mechanics.combat.equipment.metadata as equip_meta
    from localization import SUPPORTED_LOCALES, ICON_KEYWORDS, TWO_HANDED_KEYWORDS

    # 1. Supported locales exist and include en, pl, ms
    assert "en" in SUPPORTED_LOCALES
    assert "pl" in SUPPORTED_LOCALES
    assert "ms" in SUPPORTED_LOCALES

    # 2. ICON_KEYWORDS aggregates across all locales
    assert "pierścień" in ICON_KEYWORDS["accessories"]
    assert "cincin" in ICON_KEYWORDS["accessories"]
    assert "ring" in ICON_KEYWORDS["accessories"]

    assert "dwuręczny" in TWO_HANDED_KEYWORDS
    assert "dua tangan" in TWO_HANDED_KEYWORDS
    assert "greatsword" in TWO_HANDED_KEYWORDS

    # 3. character_data.py get_item_icon has zero hardcoded non-English keyword literals
    func_source = inspect.getsource(character_data.get_item_icon)
    for forbidden_literal in ["pierścień", "cincin", "miecz", "pedang", "topór", "kapak", "strzelba", "senapang"]:
        assert f'"{forbidden_literal}"' not in func_source, f"Found hardcoded foreign word in get_item_icon: {forbidden_literal}"

    # 4. metadata.py is_two_handed has zero hardcoded foreign keyword literals
    meta_source = inspect.getsource(equip_meta.is_two_handed)
    for forbidden_literal in ["dwuręczny", "dua tangan", "wielki miecz", "pedang besar"]:
        assert f'"{forbidden_literal}"' not in meta_source, f"Found hardcoded foreign word in is_two_handed: {forbidden_literal}"


def test_dual_language_settings_separation_and_directive():
    import db
    from game_engine.prompt_layout import build_language_directive

    user_id = 99299
    # Save independent settings: UI in Polish, Narration in Malay
    db.update_settings(user_id, ui_language="pl", narration_language="ms")
    settings = db.get_settings(user_id)

    assert settings["ui_language"] == "pl"
    assert settings["narration_language"] == "ms"
    assert settings["language"] == "ms"  # fallback sync

    # Verify directive follows narration_language
    mock_session = {"narration_language": "ms", "language": "pl"}
    directive_ms = build_language_directive(mock_session)
    assert "LANGUAGE DIRECTIVE: MALAY" in directive_ms
    assert "Bahasa Melayu" in directive_ms

    mock_session_pl = {"narration_language": "pl", "language": "en"}
    directive_pl = build_language_directive(mock_session_pl)
    assert "LANGUAGE DIRECTIVE: POLISH" in directive_pl
    assert "Język polski" in directive_pl


def test_locales_json_key_parity_and_no_duplicates():
    import json, glob, os

    def check_dups(filepath):
        dups = []
        def hook(pairs):
            seen = set()
            d = {}
            for k, v in pairs:
                if k in seen:
                    dups.append(k)
                seen.add(k)
                d[k] = v
            return d
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=hook)
        return dups, data

    def flatten_keys(d, prefix=""):
        res = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                res |= flatten_keys(v, full)
            else:
                res.add(full)
        return res

    loc_files = sorted(glob.glob("web/src/locales/*.json"))
    assert len(loc_files) >= 3, "Expected at least en.json, ms.json, pl.json"

    file_keys = {}
    for fp in loc_files:
        dups, data = check_dups(fp)
        assert dups == [], f"Found duplicate keys in {fp}: {dups}"
        file_keys[os.path.basename(fp)] = flatten_keys(data)

    base_keys = file_keys["en.json"]
    for fname, kset in file_keys.items():
        missing = base_keys - kset
        extra = kset - base_keys
        assert not missing, f"{fname} is missing keys from en.json: {missing}"
        assert not extra, f"{fname} has extra keys not in en.json: {extra}"


def test_client_session_enrichment_non_combat_safe_char():
    import db
    from api.adventure import _enrich_session_for_client

    # Non-combat session
    session = {
        "id": 998877,
        "is_in_combat": False,
        "scenario": "fantasy",
        "current_location": "Tavern",
        "current_npcs": [{"name": "Aria", "role": "Bard"}],
        "character": {"name": "Geralt", "gender": "Male"},
    }
    # Should not raise UnboundLocalError or fail
    enriched = _enrich_session_for_client(session, user_id=0)
    assert enriched["player_clothing_status"] == "Fully Clothed 👕"
    assert enriched["character"]["clothing_status"] == "Fully Clothed 👕"
    assert len(enriched["current_npcs"]) == 1
    assert enriched["current_npcs"][0]["clothing_status"] == "Fully Clothed 👕"


def test_clean_choices_preserves_dynamic_aftercare():
    import db
    from game_engine.choices_cleaner import clean_choices_impl

    # Setup spent & satisfied state
    dynamic_aftercare_choices = [
        {"label": "Hold Elena close and whisper tender words in aftercare", "stat": "CHA", "requirement": 5},
        {"label": "Rest together quietly beneath the sheets", "stat": "END", "requirement": 5},
        {"label": "Ease back gently, pause to catch your breath, and hold Elena close", "stat": "NONE", "requirement": 0},
    ]

    cleaned = clean_choices_impl(
        None,
        choices=dynamic_aftercare_choices,
        scenario="fantasy",
        location="Bedroom",
        char={"name": "Hero", "gender": "Male"},
        dialogue_partner="Elena",
        session_id=None,
    )
    lbls = [c["label"] for c in cleaned]
    assert any("whisper tender words in aftercare" in l for l in lbls)


