import unittest
from mechanics.combat.spells import get_starter_spells, get_spell

class TestINTSpellScaling(unittest.TestCase):
    def test_low_int_spell_budget(self):
        # INT = 2 -> 3 + (2//2) = 4 Tier 3 spells, 0 Tier 2 spells
        spells_int2 = get_starter_spells("fantasy", "Warrior", int_stat=2)
        self.assertGreaterEqual(len(spells_int2), 3)
        t2_spells = [s for s in spells_int2 if get_spell(s) and get_spell(s).get("tier") == 2]
        self.assertEqual(len(t2_spells), 0)

    def test_moderate_int_spell_budget(self):
        # INT = 5 -> 3 + 2 = 5 Tier 3 spells, (5-3)//2 = 1 Tier 2 spell
        spells_int5 = get_starter_spells("fantasy", "Spellblade", int_stat=5)
        self.assertGreaterEqual(len(spells_int5), 5)
        t2_spells = [s for s in spells_int5 if get_spell(s) and get_spell(s).get("tier") == 2]
        self.assertGreaterEqual(len(t2_spells), 1)

    def test_high_int_spell_budget(self):
        # INT = 8 -> 3 + 4 = 7 Tier 3 spells, (8-3)//2 = 2 Tier 2 spells
        spells_int8 = get_starter_spells("fantasy", "Mage", int_stat=8)
        self.assertGreaterEqual(len(spells_int8), 7)
        t2_spells = [s for s in spells_int8 if get_spell(s) and get_spell(s).get("tier") == 2]
        self.assertGreaterEqual(len(t2_spells), 2)

    def test_master_int_spell_budget(self):
        # INT = 10 -> 7 Tier 3 spells + 3 Tier 2 spells + 1 Tier 1 spell
        spells_int10 = get_starter_spells("fantasy", "Archmage", int_stat=10)
        t1_spells = [s for s in spells_int10 if get_spell(s) and get_spell(s).get("tier") == 1]
        self.assertGreaterEqual(len(t1_spells), 1)

    def test_custom_class_heuristics(self):
        # 1. Custom Necromancer
        necro_spells = get_starter_spells("fantasy", "Death Knight", int_stat=6, class_description="Wields dark necrotic curses and summons skeletons")
        self.assertTrue(any("shadow" in s or "necro" in s or "skeleton" in s or "weaken" in s for s in necro_spells))

        # 2. Custom Frost Mage
        frost_spells = get_starter_spells("fantasy", "Glacial Elementalist", int_stat=6, class_description="Masters frost and icy blizzards")
        self.assertTrue(any("frost" in s or "glacial" in s or "ice" in s or "slow" in s for s in frost_spells))

        # 3. Custom Holy Inquisitor
        holy_spells = get_starter_spells("fantasy", "Solar Templar", int_stat=6, class_description="Channels radiant holy light")
        self.assertTrue(any("radiant" in s or "holy" in s or "celestial" in s or "aegis" in s for s in holy_spells))
