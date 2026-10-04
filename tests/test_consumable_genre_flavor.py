import unittest
import re
from mechanics.combat.items.consumables import (
    normalize_consumable_scenario,
    generate_potion_name,
    generate_food_name,
    generate_drink_name,
    generate_procedural_potion,
    generate_procedural_food,
    generate_procedural_drink,
    classify_and_enrich_ad_hoc_item
)


class TestConsumableGenreFlavor(unittest.TestCase):
    """Verifies that consumables exhibit distinct, evocative genre flavoring across all scenarios."""

    def test_normalize_consumable_scenario(self):
        """All 12 canonical scenario keys from scenarios.json map to distinct canonical buckets."""
        mapping = {
            "fantasy": "fantasy",
            "isekai_fantasy": "fantasy",
            "nsfw_isekai_fantasy": "fantasy",
            "steampunk": "steampunk",
            "cyberpunk": "cyberpunk",
            "sci_fi": "cyberpunk",
            "dark_fantasy": "dark_fantasy",
            "nuclear_post_apocalypse": "post_apocalyptic",
            "high_school_drama": "high_school",
            "nsfw_high_school_drama": "high_school",
            "furry_high_school_drama": "high_school",
            "nsfw_furry_high_school_drama": "high_school",
        }
        for scen, expected in mapping.items():
            self.assertEqual(normalize_consumable_scenario(scen), expected, f"Scenario {scen} did not map to {expected}")

    def test_steampunk_consumable_naming(self):
        """Steampunk consumables feature clockwork, aether, galvanic, and Victorian themes."""
        # Potions / Inhalers
        p_heal = generate_potion_name("steampunk", 2, ["healing"], ["health"])
        self.assertTrue(any(k in p_heal.lower() for k in ["aether", "laudanum", "tincture", "ampoule", "inhaler", "tonic", "draught", "galvanic"]))

        p_throw = generate_potion_name("steampunk", 2, ["explosive_fire"], ["throwable"])
        self.assertTrue(any(k in p_throw.lower() for k in ["phlogiston", "steam-core", "bomb", "detonator"]))

        # Food (No drink keywords)
        f_savory = generate_food_name("steampunk", 2, ["savory", "meat"], ["healing"])
        self.assertTrue(any(k in f_savory.lower() for k in ["pie", "wellington", "pudding", "platter", "feast", "stew"]))

        # Drinks (No food keywords)
        d_coffee = generate_drink_name("steampunk", 2, ["coffee", "caffeine"], ["mana_restore"])
        self.assertTrue(any(k in d_coffee.lower() for k in ["espresso", "coffee", "coal-burner", "barometer"]))

        d_alc = generate_drink_name("steampunk", 2, ["alcohol"], ["attack_buff"])
        self.assertTrue(any(k in d_alc.lower() for k in ["gin", "absinthe", "ale"]))

    def test_post_apocalyptic_consumable_naming(self):
        """Post-apocalyptic consumables feature irradiated wasteland, stimpak, rad-away, and scavenging themes."""
        # Potions / Stims
        p_heal = generate_potion_name("nuclear_post_apocalypse", 2, ["healing"], ["health"])
        self.assertTrue(any(k in p_heal.lower() for k in ["stimpak", "suture", "injector", "medkit"]))

        p_cleanse = generate_potion_name("nuclear_post_apocalypse", 2, ["cleanse_all"], ["health"])
        self.assertTrue(any(k in p_cleanse.lower() for k in ["rad-away", "charcoal", "flush"]))

        p_throw = generate_potion_name("nuclear_post_apocalypse", 2, ["explosive_fire"], ["throwable"])
        self.assertTrue(any(k in p_throw.lower() for k in ["molotov", "bottle bomb"]))

        # Food
        f_meat = generate_food_name("nuclear_post_apocalypse", 3, ["savory", "meat"], ["healing"])
        self.assertTrue(any(k in f_meat.lower() for k in ["rad-roach", "brahmin", "cornbread", "mystery meat", "stew", "skewer"]))

        # Drinks
        d_soda = generate_drink_name("nuclear_post_apocalypse", 2, ["fizzy", "soda"], ["morale_boost"])
        self.assertTrue(any(k in d_soda.lower() for k in ["quantum", "cola", "atomic", "soda", "fizz"]))

        d_water = generate_drink_name("nuclear_post_apocalypse", 2, ["refreshing", "infused_water"], ["hydration"])
        self.assertTrue(any(k in d_water.lower() for k in ["water", "canteen", "spring", "scrap-bucket"]))

    def test_dark_fantasy_consumable_naming(self):
        """Dark fantasy consumables feature blood, bone, sacrificial, and eldritch concoctions."""
        # Potions
        p_heal = generate_potion_name("dark_fantasy", 2, ["healing"], ["health"])
        self.assertTrue(any(k in p_heal.lower() for k in ["blood", "chalice", "sacramental", "coagulated", "salve"]))

        p_throw = generate_potion_name("dark_fantasy", 2, ["explosive_fire"], ["throwable"])
        self.assertTrue(any(k in p_throw.lower() for k in ["hellfire", "abyssal", "void-fire"]))

        # Food
        f_meat = generate_food_name("dark_fantasy", 2, ["savory", "meat"], ["healing"])
        self.assertTrue(any(k in f_meat.lower() for k in ["sausage", "blood", "venison", "dragon-marrow", "porridge"]))

        # Drinks
        d_alc = generate_drink_name("dark_fantasy", 2, ["alcohol"], ["attack_buff"])
        self.assertTrue(any(k in d_alc.lower() for k in ["wine", "blood", "mead", "ale", "stout"]))

    def test_cross_genre_food_and_drink_keyword_safety(self):
        """Foods must never produce drink keywords, and drinks must never produce food keywords across all genres and tiers."""
        drink_keywords = ["coffee", "latte", "boba", "tea", "cider", "ale", "wine", "soda", "smoothie", "ramune", "fizz", "water"]
        food_keywords = ["bento", "stew", "roast", "steak", "melon pan", "cake", "tart", "sandwich", "skewer", "dumplings", "omakase"]

        genres = ["fantasy", "steampunk", "cyberpunk", "dark_fantasy", "nuclear_post_apocalypse", "high_school_drama"]

        for genre in genres:
            for tier in (1, 2, 3):
                for _ in range(5):
                    food = generate_procedural_food(tier=tier, genre=genre)
                    food_name_low = food["name"].lower()
                    for dkw in drink_keywords:
                        self.assertFalse(
                            re.search(r'\b' + re.escape(dkw) + r'\b', food_name_low),
                            f"Food '{food['name']}' in genre '{genre}' contains drink keyword '{dkw}'"
                        )

                    drink = generate_procedural_drink(tier=tier, genre=genre)
                    drink_name_low = drink["name"].lower()
                    for fkw in food_keywords:
                        self.assertFalse(
                            re.search(r'\b' + re.escape(fkw) + r'\b', drink_name_low),
                            f"Drink '{drink['name']}' in genre '{genre}' contains food keyword '{fkw}'"
                        )

    def test_procedural_potion_genre_taste_palette(self):
        """Procedural potion default taste palettes reflect their respective genres."""
        p_steam = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="steampunk")
        self.assertIn("copper", p_steam["tags"]["taste"])

        p_cyber = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="cyberpunk")
        self.assertIn("chemical", p_cyber["tags"]["taste"])

        p_apoc = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="nuclear_post_apocalypse")
        self.assertIn("rads", p_apoc["tags"]["taste"])

        p_dark = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="dark_fantasy")
        self.assertIn("iron", p_dark["tags"]["taste"])

        p_school = generate_procedural_potion(tier=3, effect_tags=["healing"], genre="high_school_drama")
        self.assertIn("citrus", p_school["tags"]["taste"])

        # Throwables should have empty taste
        p_throw = generate_procedural_potion(tier=3, effect_tags=["explosive_fire"], genre="steampunk")
        self.assertEqual(p_throw["tags"]["taste"], [])

    def test_classify_and_enrich_ad_hoc_genre_consumables(self):
        """classify_and_enrich_ad_hoc_item successfully recognizes newly supported genre consumables."""
        items = [
            ("Makeshift Stimpak", "Potion", "nuclear_post_apocalypse"),
            ("Galvanic Ampoule", "Potion", "steampunk"),
            ("Rad-Away Flush", "Potion", "nuclear_post_apocalypse"),
            ("Charred Rad-Roach Skewer", "Food", "nuclear_post_apocalypse"),
            ("Boiler-Baked Meat Pie", "Food", "steampunk"),
            ("Spiced Black Blood Sausage", "Food", "dark_fantasy"),
            ("Copper-Stilled London Dry Gin", "Drink", "steampunk"),
            ("Fermented Molerat Moonshine", "Drink", "nuclear_post_apocalypse"),
            ("Green Fairy Bohemian Absinthe", "Drink", "steampunk"),
            ("Monastery Black Stout", "Drink", "dark_fantasy"),
        ]
        for name, expected_type, scenario in items:
            enriched = classify_and_enrich_ad_hoc_item(name, scenario)
            self.assertEqual(
                enriched["item_type"],
                expected_type,
                f"Item '{name}' should be classified as '{expected_type}', got '{enriched['item_type']}'"
            )


if __name__ == "__main__":
    unittest.main()
