import unittest
from mechanics.combat.spells import (
    DND_SCHOOLS,
    DND_DAMAGE_TYPES,
    DND_SHAPES,
    METAMAGIC_AFFIX_POOL,
    SUMMON_TEMPLATES,
    generate_procedural_spell,
    generate_spell_name,
    generate_procedural_spellbook_item
)
from mechanics.combat.spells import register_spell, get_spell
from mechanics.combat.items import parse_item_effect

class TestProceduralSpells(unittest.TestCase):
    def test_dnd_taxonomy_coverage(self):
        # 8 D&D Schools
        self.assertEqual(len(DND_SCHOOLS), 8)
        self.assertIn("Evocation", DND_SCHOOLS)
        self.assertIn("Abjuration", DND_SCHOOLS)
        self.assertIn("Necromancy", DND_SCHOOLS)
        self.assertIn("Conjuration", DND_SCHOOLS)
        self.assertIn("Transmutation", DND_SCHOOLS)
        self.assertIn("Enchantment", DND_SCHOOLS)
        self.assertIn("Illusion", DND_SCHOOLS)
        self.assertIn("Divination", DND_SCHOOLS)

        # 13 D&D Damage Types
        self.assertEqual(len(DND_DAMAGE_TYPES), 13)
        self.assertIn("fire", DND_DAMAGE_TYPES)
        self.assertIn("cold", DND_DAMAGE_TYPES)
        self.assertIn("lightning", DND_DAMAGE_TYPES)
        self.assertIn("thunder", DND_DAMAGE_TYPES)
        self.assertIn("radiant", DND_DAMAGE_TYPES)
        self.assertIn("necrotic", DND_DAMAGE_TYPES)
        self.assertIn("psychic", DND_DAMAGE_TYPES)
        self.assertIn("force", DND_DAMAGE_TYPES)

    def test_procedural_spell_generation_tier3(self):
        spell = generate_procedural_spell("fantasy", tier=3, school="Evocation", element="fire", shape="bolt")
        self.assertEqual(spell["tier"], 3)
        self.assertEqual(spell["school"], "Evocation")
        self.assertEqual(spell["damage_type"], "fire")
        self.assertEqual(spell["target_type"], "single")
        self.assertGreaterEqual(spell["mp_cost"], 3)
        self.assertIn("Fire", spell["tags"])
        self.assertIn("Evocation", spell["tags"])

    def test_procedural_spell_generation_tier2(self):
        spell = generate_procedural_spell("fantasy", tier=2, school="Necromancy", element="necrotic")
        self.assertEqual(spell["tier"], 2)
        self.assertEqual(spell["school"], "Necromancy")
        self.assertEqual(spell["damage_type"], "necrotic")
        self.assertGreaterEqual(len(spell["affixes"]), 2)

    def test_procedural_spell_generation_tier1(self):
        spell = generate_procedural_spell("fantasy", tier=1, school="Conjuration")
        self.assertEqual(spell["tier"], 1)
        self.assertEqual(spell["school"], "Conjuration")
        self.assertGreaterEqual(len(spell["affixes"]), 3)

    def test_procedural_spellbook_item_and_registry(self):
        book_item = generate_procedural_spellbook_item("fantasy", tier=2, school="Evocation")
        self.assertEqual(book_item["item_type"], "Spellbook")
        self.assertTrue(book_item["effect"].startswith("[SPELLBOOK_JSON]"))

        meta = book_item["metadata"]
        self.assertIn("spell_data", meta)
        spell_data = meta["spell_data"]
        
        # Test registering into spells engine
        register_spell(spell_data)
        fetched = get_spell(spell_data["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["name"], spell_data["name"])

        # Test item effect parser
        from mechanics.combat.equipment import parse_equipment_metadata
        parsed = parse_equipment_metadata(book_item)
        self.assertTrue(parsed.get("is_spellbook"))
        self.assertEqual(parsed.get("spell_id"), spell_data["id"])

    def test_spell_naming_engine(self):
        name_t3 = generate_spell_name("Evocation", "fire", "bolt", tier=3, affixes=[])
        self.assertIn("Bolt", name_t3)

        name_t1 = generate_spell_name("Evocation", "lightning", "lance", tier=1, affixes=["empowered"])
        self.assertTrue(any(p in name_t1 for p in ["Cataclysmic", "Mythic", "Archon's", "Ancient", "Supreme", "God-King's", "Cosmic", "Apocalyptic"]))
