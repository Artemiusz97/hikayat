"""
Tests for tags and scenarios refactoring.
Validates tag renames (space, grimdark, isekai, high_school), generalized slice_of_life prompt instructions,
scenario tag associations, resolution, and class/weapon fallbacks.
"""
import unittest
from scenario_data import (
    load_tags,
    load_scenarios,
    get_scenario,
    get_scenario_tags,
    has_tag,
    resolve_tag_keys,
    scenario_prompt_block,
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
        tags = load_tags()
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
            "nsfw",
            "furry",
            "non_combat",
        }
        self.assertEqual(set(tags.keys()), expected_tags)
        
        # Verify old tag keys are removed from primary tags dictionary
        self.assertNotIn("sci_fi", tags)
        self.assertNotIn("dark_fantasy", tags)
        self.assertNotIn("isekai_fantasy", tags)
        self.assertNotIn("high_school_drama", tags)

    def test_slice_of_life_instructions_generalized(self):
        tags = load_tags()
        sol = tags.get("slice_of_life", {})
        instructions = " ".join(sol.get("prompt_instructions", []))
        self.assertNotIn("academic performance", instructions.lower())
        self.assertNotIn("school club", instructions.lower())
        self.assertIn("everyday life", instructions.lower())

    def test_grimdark_instructions_generalized(self):
        tags = load_tags()
        grim = tags.get("grimdark", {})
        instructions = " ".join(grim.get("prompt_instructions", []))
        self.assertIn("oppressive", instructions.lower())
        self.assertIn("moral ambiguity", instructions.lower())

    def test_scenarios_tags_exact_associations(self):
        scenarios = load_scenarios()
        self.assertEqual(scenarios["sci_fi"]["tags"], ["space"])
        self.assertEqual(scenarios["dark_fantasy"]["tags"], ["fantasy", "grimdark"])
        self.assertEqual(scenarios["isekai_fantasy"]["tags"], ["isekai", "fantasy"])
        self.assertEqual(scenarios["nsfw_isekai_fantasy"]["tags"], ["isekai", "fantasy", "nsfw"])
        self.assertEqual(scenarios["high_school_drama"]["tags"], ["high_school", "slice_of_life", "non_combat"])
        self.assertEqual(scenarios["nsfw_high_school_drama"]["tags"], ["high_school", "slice_of_life", "nsfw", "non_combat"])
        self.assertEqual(scenarios["furry_high_school_drama"]["tags"], ["high_school", "slice_of_life", "furry", "non_combat"])
        self.assertEqual(scenarios["nsfw_furry_high_school_drama"]["tags"], ["high_school", "slice_of_life", "furry", "nsfw", "non_combat"])

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
        self.assertEqual(len(get_class_templates("grimdark")), 6)
        self.assertEqual(len(get_class_templates("space")), 6)
        self.assertEqual(len(get_class_templates("isekai")), 6)
        self.assertEqual(len(get_class_templates("high_school")), 6)

        # Starting weapons resolution
        self.assertEqual(len(get_starting_weapons("dark_fantasy")), 6)
        self.assertEqual(len(get_starting_weapons("space")), 6)
        self.assertEqual(len(get_starting_weapons("isekai")), 6)
        self.assertEqual(len(get_starting_weapons("high_school")), 6)

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
        for s_key in ["fantasy", "sci_fi", "dark_fantasy", "isekai_fantasy", "high_school_drama", "nuclear_post_apocalypse"]:
            block = scenario_prompt_block(s_key)
            self.assertTrue(len(block) > 50, f"Prompt block for {s_key} was unexpectedly short")


if __name__ == "__main__":
    unittest.main()
