"""
Tests for tags and scenarios refactoring.
Validates tag renames (space, grimdark, isekai, high_school), generalized slice_of_life prompt instructions,
scenario tag associations, resolution, and class/weapon fallbacks.
"""
import unittest
from scenario_data import (
    load_genres,
    load_scenarios,
    get_scenario,
    get_scenario_tags,
    has_tag,
    resolve_tag_keys,
    scenario_prompt_block,
    PRIMARY_SETTING_TAGS,
    MODIFIER_TAGS,
)
from character_data import (
    get_class_templates,
    get_starting_weapons,
)
from mechanics.narrative.bounty import get_archetypes_for_scenario
from mechanics.social.races import get_scenario_race_hint, normalize_race
from mechanics.system.phone import scenario_has_smartphone, get_phone_branding
from cogs.contacts import get_scenario_contact_title


class TestTagsScenariosRefactor(unittest.TestCase):
    def test_tags_keys_and_schema(self):
        genres = load_genres()
        expected_tags = {
            "fantasy",
            "space",
            "cyberpunk",
            "steampunk",
            "grimdark",
            "isekai",
            "slice_of_life",
            "high_school",
            "post_apocalypse",
            "urban_fantasy",
            "nsfw",
            "furry",
            "non_combat",
            "gore",
            "horror",
        }
        self.assertEqual(set(genres.keys()), expected_tags)
        
        # Verify old tag keys are removed from primary genres dictionary
        self.assertNotIn("sci_fi", genres)
        self.assertNotIn("dark_fantasy", genres)
        self.assertNotIn("isekai_fantasy", genres)
        self.assertNotIn("high_school_drama", genres)

        # Verify category separation
        expected_genres = {
            "fantasy", "space", "cyberpunk", "steampunk",
            "isekai", "slice_of_life", "high_school", "post_apocalypse",
            "urban_fantasy",
        }
        expected_modifiers = {"grimdark", "furry", "nsfw", "non_combat", "gore", "horror"}

        for k, v in genres.items():
            self.assertIn("category", v, f"Genre {k} missing category")
            if k in expected_genres:
                self.assertEqual(v["category"], "genre", f"Genre {k} should be genre")
                self.assertIn("allowed_mechanics", v, f"Genre {k} should have allowed_mechanics")
            elif k in expected_modifiers:
                self.assertEqual(v["category"], "modifier", f"Genre {k} should be modifier")
                self.assertNotIn("allowed_mechanics", v, f"Modifier {k} must not define allowed_mechanics")

        # Verify all genre keys appear before all modifier keys
        ordered_keys = list(genres.keys())
        self.assertEqual(ordered_keys[:9], [
            "fantasy", "space", "cyberpunk", "steampunk",
            "isekai", "slice_of_life", "high_school", "post_apocalypse",
            "urban_fantasy",
        ])
        self.assertEqual(set(ordered_keys[9:]), expected_modifiers)

        self.assertEqual(set(PRIMARY_SETTING_TAGS), expected_genres)
        self.assertEqual(set(MODIFIER_TAGS), expected_modifiers)
        self.assertNotIn("starting_hooks", genres["grimdark"])
        self.assertNotIn("allowed_mechanics", genres["grimdark"])
        self.assertNotIn("allowed_mechanics", genres["non_combat"])
        self.assertIn("tactical_combat", genres["slice_of_life"]["allowed_mechanics"])

    def test_slice_of_life_instructions_generalized(self):
        genres = load_genres()
        sol = genres.get("slice_of_life", {})
        instructions = " ".join(sol.get("prompt_instructions", []))
        self.assertNotIn("academic performance", instructions.lower())
        self.assertNotIn("school club", instructions.lower())
        self.assertIn("everyday urban life", instructions.lower())

    def test_grimdark_instructions_generalized(self):
        genres = load_genres()
        grim = genres.get("grimdark", {})
        instructions = " ".join(grim.get("prompt_instructions", []))
        self.assertIn("oppressive", instructions.lower())
        self.assertIn("moral ambiguity", instructions.lower())

    def test_scenarios_tags_exact_associations(self):
        scenarios = load_scenarios()
        self.assertEqual(scenarios["sci_fi"]["tags"], ["space"])
        self.assertEqual(scenarios["dark_fantasy"]["tags"], ["fantasy", "grimdark"])
        self.assertEqual(len(scenarios["dark_fantasy"].get("starting_hooks", [])), 6)
        self.assertEqual(scenarios["isekai_fantasy"]["tags"], ["isekai", "fantasy"])
        self.assertEqual(scenarios["nsfw_isekai_fantasy"]["tags"], ["isekai", "fantasy", "nsfw"])
        self.assertEqual(scenarios["high_school_drama"]["tags"], ["high_school", "non_combat"])
        self.assertEqual(scenarios["nsfw_high_school_drama"]["tags"], ["high_school", "nsfw", "non_combat"])
        self.assertEqual(scenarios["furry_high_school_drama"]["tags"], ["high_school", "furry", "non_combat"])
        self.assertEqual(scenarios["nsfw_furry_high_school_drama"]["tags"], ["high_school", "furry", "nsfw", "non_combat"])
        self.assertEqual(scenarios["slice_of_life"]["tags"], ["slice_of_life"])

    def test_resolve_tag_keys_and_aliases(self):
        # Canonical new tag keys
        res = resolve_tag_keys("fantasy, + High School, + Slice of Life")
        self.assertEqual(res, ["fantasy", "high_school", "slice_of_life"])

        # Legacy aliases
        res_alias = resolve_tag_keys("sci-fi, dark-fantasy, isekai-fantasy")
        self.assertEqual(res_alias, ["space", "grimdark", "isekai"])

        # High school drama alias
        res_hs = resolve_tag_keys("high_school_drama")
        self.assertEqual(res_hs, ["high_school"])

    def test_character_template_and_weapon_resolution_with_new_tags(self):
        # Scenario key resolution
        self.assertEqual(len(get_class_templates("dark_fantasy")), 6)
        self.assertEqual(len(get_class_templates("slice_of_life")), 6)
        self.assertEqual(len(get_class_templates("space")), 6)
        self.assertEqual(len(get_class_templates("isekai")), 6)
        self.assertEqual(len(get_class_templates("high_school")), 14)

        # Starting weapons resolution
        self.assertEqual(len(get_starting_weapons("dark_fantasy")), 6)
        self.assertEqual(len(get_starting_weapons("slice_of_life")), 6)
        self.assertEqual(len(get_starting_weapons("space")), 6)
        self.assertEqual(len(get_starting_weapons("isekai")), 6)
        self.assertEqual(len(get_starting_weapons("high_school")), 0)

    def test_mechanics_tag_checks(self):
        # Contacts
        self.assertEqual(get_scenario_contact_title("sci_fi")[0], "🚀")
        self.assertEqual(get_scenario_contact_title("high_school_drama")[0], "📱")
        self.assertEqual(get_scenario_contact_title("dark_fantasy")[0], "📜")
        self.assertEqual(get_scenario_contact_title("isekai_fantasy")[0], "✨")

        # Phone
        self.assertTrue(scenario_has_smartphone("high_school_drama"))
        self.assertTrue(scenario_has_smartphone("sci_fi"))
        self.assertEqual(get_phone_branding("sci_fi")["emoji"], "📡")

        # Races
        hint_space = get_scenario_race_hint("sci_fi")
        self.assertIn("alien", hint_space)
        hint_hs = get_scenario_race_hint("high_school_drama")
        self.assertEqual(hint_hs, "human")

    def test_scenario_prompt_block_rendering(self):
        for s_key in ["fantasy", "sci_fi", "dark_fantasy", "isekai_fantasy", "high_school_drama", "slice_of_life", "nuclear_post_apocalypse"]:
            block = scenario_prompt_block(s_key)
            self.assertTrue(len(block) > 50, f"Prompt block for {s_key} was unexpectedly short")

    def test_slice_of_life_and_dark_fantasy_standalone_assets(self):
        from scenario_data import get_dynamic_starting_hook, is_non_combat_scenario
        from mechanics.world.locations.seeds import get_scenario_seed_data
        from mechanics.combat.items.weapons import (
            generate_random_equipment as gen_weapon,
            WEAPON_ARCHETYPES,
            NON_COMBAT_WEAPON_ARCHETYPES,
        )
        from mechanics.combat.items.armors import generate_random_equipment as gen_armor
        from mechanics.combat.items.shields import generate_random_equipment as gen_shield
        from mechanics.combat.enemies import generate_scenario_enemy

        # 1. dark_fantasy retains its 6 gothic hooks while grimdark modifier does not override fantasy hooks
        df_hook = get_dynamic_starting_hook("dark_fantasy")
        self.assertTrue(any(k in df_hook["hook_text"] for k in (
            "fortified enclave", "plague-shadowed cathedral town", "brutal ambush",
            "belfry of a half-collapsed cathedral", "desecrated crypt", "stagnant black bog",
        )))

        # 2. slice_of_life has its own starting hooks, locations, combat + non-combat support
        sol_hook = get_dynamic_starting_hook("slice_of_life")
        self.assertTrue(any(k in sol_hook["hook_text"] for k in (
            "coffee roastery", "river greenway", "jazz bar",
            "train station platform", "harbor warehouse pier", "antique curiosity shop",
        )))
        self.assertFalse(is_non_combat_scenario("slice_of_life"))
        self.assertTrue(is_non_combat_scenario("custom_combinator_slice_of_life_non_combat"))

        sol_seeds = get_scenario_seed_data("slice_of_life")
        self.assertEqual(len(sol_seeds.get("zones", [])), 4)

        # 3. Procedural equipment & enemies for slice_of_life
        w_combat = gen_weapon("slice_of_life", "Weapon", tier=2)
        self.assertIn(w_combat["metadata"]["archetype"], WEAPON_ARCHETYPES)
        w_non_combat = gen_weapon("custom_combinator_slice_of_life_non_combat", "Weapon", tier=2)
        self.assertIn(w_non_combat["metadata"]["archetype"], NON_COMBAT_WEAPON_ARCHETYPES)

        a_sol = gen_armor("slice_of_life", "Armor", tier=2)
        self.assertEqual(a_sol["slot"], "Armor")

        s_combat = gen_shield("slice_of_life", "Shield", tier=2)
        self.assertGreater(s_combat["metadata"]["block_chance"], 0)
        s_non_combat = gen_shield("custom_combinator_slice_of_life_non_combat", "Shield", tier=2)
        self.assertEqual(s_non_combat["metadata"]["block_chance"], 0)

        enemy = generate_scenario_enemy("slice_of_life", "Downtown Shopping Arcade & Café Row", 1)
        self.assertTrue(len(enemy["name"]) > 0)

    def test_scenario_display_names_and_dropdown_labels(self):
        from scenario_data import get_scenario_display_name, get_scenario_dropdown_label
        expected_display_names = {
            "fantasy": "Realms of Myth & Magic",
            "sci_fi": "Beyond the Outer Rim",
            "cyberpunk": "Neon Chrome & Mirrors",
            "steampunk": "Brass, Steam & Aether",
            "dark_fantasy": "Cursed Blood & Ashen Crowns",
            "isekai_fantasy": "Summoned to Another World",
            "nsfw_isekai_fantasy": "Summoned: Desires of Another World",
            "high_school_drama": "Youth, Bells & Rooftop Breezes",
            "nsfw_high_school_drama": "After-School Desires & Secrets",
            "furry_high_school_drama": "Paws, Bells & Rooftop Breezes",
            "nsfw_furry_high_school_drama": "After-School Instincts & Desires",
            "slice_of_life": "Downtown Lights & Lattes",
            "nuclear_post_apocalypse": "Ashes of the Fallout",
        }
        for key, expected_title in expected_display_names.items():
            self.assertEqual(get_scenario_display_name(key), expected_title)
            dropdown = get_scenario_dropdown_label(key)
            self.assertIn(expected_title, dropdown)
            self.assertIn("[", dropdown)

        custom_name = get_scenario_display_name("custom_combinator_slice_of_life_non_combat")
        self.assertTrue(custom_name.startswith("Custom:"))
        self.assertIn("Slice of Life", custom_name)

    def test_gore_tag_and_uses_nsfw_model(self):
        from scenario_data import is_nsfw_scenario, is_gore_scenario, uses_nsfw_model
        genres = load_genres(reload=True)
        self.assertIn("gore", genres)
        self.assertEqual(genres["gore"].get("category"), "modifier")
        self.assertGreaterEqual(len(genres["gore"].get("prompt_instructions", [])), 1)

        self.assertFalse(is_nsfw_scenario("custom_combinator_fantasy_gore"))
        self.assertTrue(is_gore_scenario("custom_combinator_fantasy_gore"))
        self.assertTrue(uses_nsfw_model("custom_combinator_fantasy_gore"))
        self.assertTrue(uses_nsfw_model("nsfw_isekai_fantasy"))
        self.assertFalse(uses_nsfw_model("fantasy"))


if __name__ == "__main__":
    unittest.main()
