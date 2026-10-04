import pytest
import db
import character_data as cd
from mechanics.combat.items.weapons import (
    WEAPON_ARCHETYPES,
    NON_COMBAT_WEAPON_ARCHETYPES,
    SCENARIO_AFFIXES,
    normalize_weapon_scenario,
    generate_random_equipment,
    format_equipment_card
)
from mechanics.social.attributes import calculate_combat_attributes, format_combat_attributes_text


# ---------------------------------------------------------------------------
# 1. Procedural Weapon Affixes & Genre Normalization
# ---------------------------------------------------------------------------

def test_normalize_weapon_scenario():
    assert normalize_weapon_scenario("fantasy") == "fantasy"
    assert normalize_weapon_scenario("steampunk") == "steampunk"
    assert normalize_weapon_scenario("clockwork_victorian") == "steampunk"
    assert normalize_weapon_scenario("cyberpunk") == "cyberpunk"
    assert normalize_weapon_scenario("sci_fi") == "sci_fi"
    assert normalize_weapon_scenario("scifi") == "sci_fi"
    assert normalize_weapon_scenario("space_opera") == "sci_fi"
    assert normalize_weapon_scenario("nuclear_post_apocalypse") == "nuclear_post_apocalypse"
    assert normalize_weapon_scenario("wasteland") == "nuclear_post_apocalypse"
    assert normalize_weapon_scenario("postapoc") == "nuclear_post_apocalypse"
    assert normalize_weapon_scenario("dark_fantasy") == "dark_fantasy"
    assert normalize_weapon_scenario("high_school_drama") == "high_school"
    assert normalize_weapon_scenario("slice_of_life") == "high_school"


def test_genre_weapon_generation_and_affixes():
    # Verify Steampunk weapons
    sp_weapon = generate_random_equipment("steampunk", "Weapon", tier=2)
    assert sp_weapon["slot"] == "Weapon"
    sp_name = sp_weapon["name"]
    sp_affixes = SCENARIO_AFFIXES["steampunk"]
    all_sp_words = sp_affixes["prefixes_t2"] + sp_affixes["suffixes_t2"]
    assert any(w.lower() in sp_name.lower() for w in all_sp_words)

    # Verify Cyberpunk weapons
    cb_weapon = generate_random_equipment("cyberpunk", "Weapon", tier=2)
    cb_name = cb_weapon["name"]
    cb_affixes = SCENARIO_AFFIXES["cyberpunk"]
    all_cb_words = cb_affixes["prefixes_t2"] + cb_affixes["suffixes_t2"]
    assert any(w.lower() in cb_name.lower() for w in all_cb_words)

    # Verify Post-Apocalypse weapons
    pa_weapon = generate_random_equipment("nuclear_post_apocalypse", "Weapon", tier=2)
    pa_name = pa_weapon["name"]
    pa_affixes = SCENARIO_AFFIXES["nuclear_post_apocalypse"]
    all_pa_words = pa_affixes["prefixes_t2"] + pa_affixes["suffixes_t2"]
    assert any(w.lower() in pa_name.lower() for w in all_pa_words)

    # Verify Sci-Fi weapons
    sf_weapon = generate_random_equipment("sci_fi", "Weapon", tier=2)
    sf_name = sf_weapon["name"]
    sf_affixes = SCENARIO_AFFIXES["sci_fi"]
    all_sf_words = sf_affixes["prefixes_t2"] + sf_affixes["suffixes_t2"]
    assert any(w.lower() in sf_name.lower() for w in all_sf_words)

    # Verify Dark Fantasy weapons
    df_weapon = generate_random_equipment("dark_fantasy", "Weapon", tier=2)
    df_name = df_weapon["name"]
    df_affixes = SCENARIO_AFFIXES["dark_fantasy"]
    all_df_words = df_affixes["prefixes_t2"] + df_affixes["suffixes_t2"]
    assert any(w.lower() in df_name.lower() for w in all_df_words)


# ---------------------------------------------------------------------------
# 2. Non-Combat Weapon Archetypes
# ---------------------------------------------------------------------------

def test_non_combat_weapon_archetypes_generation():
    # In high school / slice of life, weapons generated should be non-combat items
    for _ in range(25):
        w = generate_random_equipment("high_school_drama", "Weapon", tier=3)
        arch = w["metadata"]["archetype"]
        assert arch in NON_COMBAT_WEAPON_ARCHETYPES
        assert arch not in ("shotgun", "machinegun", "explosive", "greatsword", "railgun")
        assert w["metadata"]["multiplier"] > 0
        assert "tags" in w["metadata"]
        assert "handedness" in w["metadata"]

    # Verify formatting card for a non-combat weapon
    card = format_equipment_card(w["metadata"])
    assert "**Slot:** Weapon" in card


# ---------------------------------------------------------------------------
# 3. Class Templates Starter Gear Weapons Harmonization
# ---------------------------------------------------------------------------

def test_class_templates_all_have_starter_gear_weapons():
    templates = cd.load_class_templates()
    total_classes = 0
    for scen, classes in templates.items():
        for cname, cdata in classes.items():
            total_classes += 1
            sg = cdata.get("starter_gear", {})
            assert "Weapon" in sg, f"Class {scen}:{cname} is missing 'Weapon' in starter_gear"
            w_entry = sg["Weapon"]
            assert isinstance(w_entry, list) and len(w_entry) >= 3
            assert len(w_entry[0].strip()) > 0  # Weapon name
            assert w_entry[2] >= 1              # Slot cost

            # Verify no weapon remained duplicated in starting_items
            si = cdata.get("starting_items", [])
            for s_item in si:
                assert s_item[1] not in ("Weapon", "Magical Implement"), (
                    f"Class {scen}:{cname} still has weapon in starting_items: {s_item}"
                )

    assert total_classes == 48


def test_spellcaster_starter_weapons():
    # Specific verification for former 'Magical Implement' classes
    archmage_gear = cd.get_starter_gear_by_class("fantasy", "Archmage")
    assert archmage_gear["Weapon"][0] == "Arcane Staff"

    druid_gear = cd.get_starter_gear_by_class("fantasy", "Druid")
    assert druid_gear["Weapon"][0] == "Oak Shaman Staff"

    hex_weaver_gear = cd.get_starter_gear_by_class("dark_fantasy", "Hex Weaver")
    assert hex_weaver_gear["Weapon"][0] == "Bone-Carved Wand"

    cheat_caster_gear = cd.get_starter_gear_by_class("isekai_fantasy", "Cheat Spellcaster")
    assert cheat_caster_gear["Weapon"][0] == "Goddess Staff"


# ---------------------------------------------------------------------------
# 4. Database Inventory Initialization
# ---------------------------------------------------------------------------

def test_db_init_character_inventory_equips_starter_weapon():
    user_id = 999111222
    db.init_db()

    # Clean up previous runs
    for c in db.get_user_characters(user_id):
        db.delete_character(user_id, c["id"])

    stats = {"STR": 3, "PER": 2, "END": 2, "CHA": 1, "INT": 2, "AGI": 2, "LUK": 1}
    db.create_character(user_id, "TestArchmage", "Archmage", "A powerful wizard", stats)

    # Initialize inventory for Archmage in fantasy scenario
    db.reset_character_for_new_adventure(user_id, "fantasy")

    equipped = db.get_equipment(user_id)
    assert "Weapon" in equipped
    weapon = equipped["Weapon"]
    assert weapon is not None
    assert weapon["name"] == "Archmage Starter Weapon"
    assert "Placeholder" not in weapon["name"]  # Guaranteed no placeholder fallback!

    for c in db.get_user_characters(user_id):
        db.delete_character(user_id, c["id"])


# ---------------------------------------------------------------------------
# 5. Dual-Wielding Equipping Rules & 2H Mutual Exclusion
# ---------------------------------------------------------------------------

def test_dual_wielding_equipping_rules():
    from mechanics.combat.items.envelope import serialize_item

    user_id = 999333444
    db.init_db()

    for c in db.get_user_characters(user_id):
        db.delete_character(user_id, c["id"])

    stats = {"STR": 3, "PER": 2, "END": 2, "CHA": 1, "INT": 2, "AGI": 2, "LUK": 1}
    db.create_character(user_id, "DualWielder", "Rogue", "A nimble rogue", stats)

    # Add 1H Dagger 1
    d1_meta = {"name": "Main Dagger", "archetype": "dagger", "handedness": "1H", "multiplier": 1.0, "crit_bonus": 8}
    id_d1 = db.add_item(user_id, "Main Dagger", "Weapon", serialize_item(d1_meta), 1)

    # Add 1H Dagger 2
    d2_meta = {"name": "Offhand Dagger", "archetype": "dagger", "handedness": "1H", "multiplier": 1.0, "crit_bonus": 12}
    id_d2 = db.add_item(user_id, "Offhand Dagger", "Weapon", serialize_item(d2_meta), 1)

    # Add 2H Greatsword
    gs_meta = {"name": "Heavy Greatsword", "archetype": "greatsword", "handedness": "2H", "multiplier": 1.75}
    id_gs = db.add_item(user_id, "Heavy Greatsword", "Weapon", serialize_item(gs_meta), 2)

    # 1. Equip 1H in Weapon, 1H in Shield (Off-Hand) -> Success!
    db.equip_item(user_id, id_d1, "Weapon")
    db.equip_item(user_id, id_d2, "Shield")

    eq = db.get_equipment(user_id)
    assert eq["Weapon"]["name"] == "Main Dagger"
    assert eq["Shield"]["name"] == "Offhand Dagger"

    # 2. Cannot equip 2H weapon in Shield slot -> ValueError!
    with pytest.raises(ValueError, match="Two-handed"):
        db.equip_item(user_id, id_gs, "Shield")

    # 3. Equipping 2H weapon in Weapon slot automatically unequips off-hand!
    db.equip_item(user_id, id_gs, "Weapon")
    eq_after_2h = db.get_equipment(user_id)
    assert eq_after_2h["Weapon"]["name"] == "Heavy Greatsword"
    assert eq_after_2h["Shield"] is None  # Auto-unequipped!

    # 4. Equipping an off-hand weapon when 2H is equipped automatically unequips the 2H weapon!
    db.equip_item(user_id, id_d2, "Shield")
    eq_after_offhand = db.get_equipment(user_id)
    assert eq_after_offhand["Shield"]["name"] == "Offhand Dagger"
    assert eq_after_offhand["Weapon"] is None  # 2H main weapon was unequipped!

    for c in db.get_user_characters(user_id):
        db.delete_character(user_id, c["id"])


# ---------------------------------------------------------------------------
# 6. Combat Attributes Resolution: Dual-Wielding Bonuses & Drawbacks
# ---------------------------------------------------------------------------

def test_combat_attributes_loadout_tradeoffs():
    char = {"level": 1, "str_": 2, "per_": 2, "end_": 2, "cha_": 2, "int_": 2, "agi_": 2, "luk_": 2}

    # Base 1H weapon
    main_1h = {
        "name": "Main Katana", "slot": "Weapon", "item_type": "Weapon",
        "metadata": {"handedness": "1H", "multiplier": 1.25, "crit_bonus": 5.0}
    }

    # Off-hand 1H weapon
    off_1h = {
        "name": "Offhand Wakizashi", "slot": "Shield", "item_type": "Weapon",
        "metadata": {"handedness": "1H", "multiplier": 1.00, "crit_bonus": 8.0}
    }

    # Shield
    shield = {
        "name": "Heater Shield", "slot": "Shield", "item_type": "Shield",
        "metadata": {"base_dt": 8, "block_chance": 20}
    }

    # Versatile weapon
    versatile_w = {
        "name": "Bastard Sword", "slot": "Weapon", "item_type": "Weapon",
        "metadata": {"handedness": "Versatile", "multiplier": 1.25, "crit_bonus": 5.0}
    }

    # 1. Single 1H Finesse
    attrs_single = calculate_combat_attributes(char, [main_1h])
    assert attrs_single["finesse_single_wield"] is True
    assert attrs_single["dual_wield"] is False
    # Gains +2 EVA finesse bonus
    assert attrs_single["eva"] == 13  # Base 11 + 2

    # 2. Dual Wielding (Main 1H + Offhand 1H)
    attrs_dual = calculate_combat_attributes(char, [main_1h, off_1h])
    assert attrs_dual["dual_wield"] is True
    assert attrs_dual["finesse_single_wield"] is False

    # Offensive gains:
    # +15% multiplier: 1.25 * 1.15 = 1.4375
    assert attrs_dual["weapon_mult"] == pytest.approx(1.25 * 1.15)
    assert attrs_dual["atk"] > attrs_single["atk"]
    # Gains offhand crit bonus: +8%
    assert attrs_dual["crit_success"] == pytest.approx(attrs_single["crit_success"] + 8.0)

    # Minor drawbacks:
    # Split-focus: -3 ACC compared to base
    assert attrs_dual["acc"] == attrs_single["acc"] - 3
    # Flurry commitment: -2 EVA compared to base (and -4 compared to finesse single wield)
    assert attrs_dual["eva"] == attrs_single["eva"] - 4  # 13 - 4 = 9 (Base 11 - 2)

    # 3. Sword & Shield
    attrs_shield = calculate_combat_attributes(char, [main_1h, shield])
    assert attrs_shield["block_chance"] == 20
    assert attrs_shield["base_dt"] == 8
    assert attrs_shield["dual_wield"] is False
    assert attrs_shield["finesse_single_wield"] is False

    # 4. Versatile Two-Handed Grip
    attrs_versatile = calculate_combat_attributes(char, [versatile_w])
    assert attrs_versatile["versatile_stance"] == "2H"
    assert attrs_versatile["weapon_mult"] == pytest.approx(1.25 * 1.15)
    assert attrs_versatile["crit_success"] == pytest.approx(attrs_single["crit_success"] + 4.0)
    assert attrs_versatile["acc"] == 72  # +2 ACC
    assert attrs_versatile["eva"] == 9   # -2 EVA
