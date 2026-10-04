import unittest
from skill_check import calculate_hazard_damage

class TestHazardFormulas(unittest.TestCase):
    
    def test_no_damage_on_success(self):
        self.assertEqual(calculate_hazard_damage(10, "success", 100), 0)
        self.assertEqual(calculate_hazard_damage(15, "crit_success", 100), 0)

    def test_fail_tier_damage_scaling(self):
        # Base damage is req * 2
        self.assertEqual(calculate_hazard_damage(5, "fail", 100), 10)
        self.assertEqual(calculate_hazard_damage(10, "fail", 100), 20)
        self.assertEqual(calculate_hazard_damage(15, "fail", 100), 30)

    def test_crit_fail_tier_damage_scaling(self):
        # Base damage is req * 3.5
        self.assertEqual(calculate_hazard_damage(5, "crit_fail", 100), 17)
        self.assertEqual(calculate_hazard_damage(10, "crit_fail", 100), 35)

    def test_max_hp_caps_for_fail(self):
        # Cap is 40% of max_hp for fail
        # req 25 -> dmg 50. cap for 100 hp is 40.
        self.assertEqual(calculate_hazard_damage(25, "fail", 100), 40)
        # cap for 50 hp is 20
        self.assertEqual(calculate_hazard_damage(25, "fail", 50), 20)

    def test_max_hp_caps_for_crit_fail(self):
        # Cap is 70% of max_hp for crit_fail
        # req 25 -> dmg 87. cap for 100 hp is 70.
        self.assertEqual(calculate_hazard_damage(25, "crit_fail", 100), 70)
        # cap for 50 hp is 35
        self.assertEqual(calculate_hazard_damage(25, "crit_fail", 50), 35)

    def test_minimum_damage(self):
        # Ensure it never returns < 1 if it's a fail/crit_fail
        self.assertEqual(calculate_hazard_damage(0, "fail", 100), 1)
        self.assertEqual(calculate_hazard_damage(0, "crit_fail", 100), 1)

if __name__ == "__main__":
    unittest.main()
