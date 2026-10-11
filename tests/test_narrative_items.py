import unittest
import uuid
import db
from mechanics.combat.items.tags import is_narrative_item, make_narrative_metadata
from mechanics.combat.items import (
    generate_random_equipment,
    generate_starter_equipment_loadout,
    format_equipment_card,
)
from mechanics.combat.items.weapons import deduce_weapon_archetype
from mechanics.combat.items.consumables.generators import classify_and_enrich_ad_hoc_item
from game_engine.context import _character_sheet_text


class TestNarrativeItems(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 999666000 + (uuid.uuid4().int % 100000)
        self.char = db.create_character(
            self.user_id, "TestStudent", "Student", "",
            {"STR": 3, "PER": 2, "END": 2, "CHA": 1, "INT": 2, "AGI": 2, "LUK": 1},
            scenario="high_school_drama", gender="Male", race="Human"
        )

    def tearDown(self):
        db.delete_character(self.user_id, self.char["id"])

    def test_is_narrative_item_detection(self):
        """Verify is_narrative_item correctly detects narrative/non-combat tags and flags."""
        # 1. Explicit boolean flag
        self.assertTrue(is_narrative_item({"is_narrative": True}))
        self.assertTrue(is_narrative_item({"metadata": {"is_narrative": True}}))

        # 2. Canonical 'narrative' tag
        self.assertTrue(is_narrative_item({"tags": ["narrative", "light"]}))
        self.assertTrue(is_narrative_item({"metadata": {"tags": ["narrative"]}}))

        # 3. Synonyms: 'non-combat', 'non_combat', 'cosmetic'
        self.assertTrue(is_narrative_item({"tags": ["non-combat"]}))
        self.assertTrue(is_narrative_item({"tags": ["non_combat"]}))
        self.assertTrue(is_narrative_item({"tags": ["cosmetic"]}))

        # 4. Standard combat item should return False
        combat_item = {
            "name": "Steel Longsword",
            "metadata": {
                "archetype": "sword",
                "multiplier": 1.4,
                "tags": ["versatile", "slashing"]
            }
        }
        self.assertFalse(is_narrative_item(combat_item))
        self.assertFalse(is_narrative_item(combat_item["metadata"]))

    def test_make_narrative_metadata(self):
        """Verify make_narrative_metadata strips combat stats and enforces narrative properties."""
        raw_meta = {
            "name": "Practice Foil",
            "archetype": "foil",
            "multiplier": 1.45,
            "crit_bonus": 15,
            "armor_penetration": 0.2,
            "attack_profiles": {"strike": {"multiplier": 1.45}},
            "stat_modifiers": {"atk": 5, "acc": 10},
            "social_modifiers": {"cha": 1},
            "tags": ["fencing", "slender"],
        }
        narrative_meta = make_narrative_metadata(raw_meta)

        self.assertTrue(narrative_meta["is_narrative"])
        self.assertEqual(narrative_meta["multiplier"], 1.0)
        self.assertEqual(narrative_meta["crit_bonus"], 0)
        self.assertEqual(narrative_meta["armor_penetration"], 0.0)
        self.assertEqual(narrative_meta["attack_profiles"], {})
        self.assertEqual(narrative_meta["stat_modifiers"], {})
        self.assertEqual(narrative_meta["base_dt"], 0)
        self.assertEqual(narrative_meta["base_dr"], 0.0)
        self.assertEqual(narrative_meta["base_eva"], 0)
        # Social modifiers must be preserved
        self.assertEqual(narrative_meta["social_modifiers"], {"cha": 1})
        # Canonical 'narrative' tag must be present
        self.assertIn("narrative", narrative_meta["tags"])
        self.assertIn("fencing", narrative_meta["tags"])

    def test_generate_random_equipment_in_non_combat_scenario(self):
        """Verify generated weapons in non-combat scenarios automatically have narrative metadata."""
        weapon = generate_random_equipment(scenario="high_school_drama", slot="Weapon", tier=3, name="Fountain Pen")
        self.assertTrue(is_narrative_item(weapon))
        meta = weapon["metadata"]
        self.assertTrue(meta["is_narrative"])
        self.assertEqual(meta["multiplier"], 1.0)
        self.assertEqual(meta["crit_bonus"], 0)
        from mechanics.combat.items.tags import get_flat_tag_list
        self.assertIn("narrative", get_flat_tag_list(meta))

    def test_deduce_weapon_archetype_preserves_variety_in_non_combat(self):
        """Verify non-combat weapons deduce valid archetypes without falling back to fountain pen."""
        self.assertEqual(deduce_weapon_archetype("Wooden Kendo Sword"), "katana")
        self.assertEqual(deduce_weapon_archetype("Baseball Bat"), "bat")
        self.assertEqual(deduce_weapon_archetype("Pepper Spray"), "improvised")
        self.assertEqual(deduce_weapon_archetype("Fountain Pen"), "fountain_pen")

        # Generating a kendo sword in high_school_drama should deduce katana, not fountain pen
        kendo = generate_random_equipment(scenario="high_school_drama", slot="Weapon", tier=3, name="Wooden Kendo Sword")
        self.assertEqual(kendo["metadata"]["archetype"], "katana")
        self.assertTrue(is_narrative_item(kendo))

    def test_generate_starter_equipment_loadout_all_narrative(self):
        """Verify all equipment items in a non-combat loadout carry narrative metadata and zero combat stats."""
        loadout = generate_starter_equipment_loadout(
            scenario="high_school_drama",
            char_class="Student Council President",
            gender="Female",
            race="Human",
            weapon_name="Fountain Pen",
            tier=3
        )
        self.assertIn("Weapon", loadout)
        self.assertIn("Top", loadout)
        self.assertIn("Bottom", loadout)

        for slot, item in loadout.items():
            self.assertTrue(is_narrative_item(item), f"Slot {slot} ({item['name']}) is not tagged as narrative!")
            meta = item.get("metadata", {})
            self.assertTrue(meta.get("is_narrative"), f"Slot {slot} missing is_narrative flag")
            self.assertEqual(meta.get("multiplier", 1.0), 1.0, f"Slot {slot} has non-1.0 multiplier")
            self.assertEqual(meta.get("crit_bonus", 0), 0, f"Slot {slot} has non-zero crit")
            self.assertEqual(meta.get("stat_modifiers", {}), {}, f"Slot {slot} has combat stat modifiers")

    def test_format_equipment_card_narrative(self):
        """Verify format_equipment_card displays narrative info and suppresses combat multipliers."""
        meta = {
            "name": "School Blazer",
            "archetype": "blazer",
            "is_narrative": True,
            "tags": ["narrative", "formal"],
            "social_modifiers": {"cha": 1}
        }
        card = format_equipment_card(meta)
        self.assertIn("Narrative Equipment (Cosmetic / Roleplay)", card)
        self.assertIn("Flavor, Story & Social Actions (No Combat Stats)", card)
        self.assertIn("#narrative", card)
        self.assertIn("+1 CHA", card)
        self.assertNotIn("Power Multiplier", card)

    def test_classify_and_enrich_ad_hoc_item_non_combat(self):
        """Verify ad-hoc equipment items in non-combat scenarios receive narrative metadata."""
        item = classify_and_enrich_ad_hoc_item("Delinquent Wooden Bat", "high_school_drama")
        self.assertTrue(is_narrative_item(item))

    def test_character_sheet_text_narrative_tag(self):
        """Verify _character_sheet_text appends [Narrative Item] to equipped narrative gear."""
        # Equip a narrative item
        w_item = generate_random_equipment(scenario="high_school_drama", slot="Weapon", tier=3, name="Fountain Pen")
        item_id = db.add_item(self.user_id, w_item["name"], "Weapon", w_item["effect"], 1)
        db.equip_item(self.user_id, item_id, "Weapon")

        char = db.get_character(self.user_id)
        sheet_text = _character_sheet_text(char, [])
        self.assertIn("Fountain Pen [Narrative Item]", sheet_text)


if __name__ == "__main__":
    unittest.main()
