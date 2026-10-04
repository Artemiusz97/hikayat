"""
Unit tests for general animal family subspecies distribution,
role-to-faction dynamic profile coupling, and narrative appearance extraction.
"""
import unittest
import json
from mechanics.social.races import (
    resolve_animal_family_species,
    normalize_race,
    extract_race_from_text,
    ANIMAL_FAMILY_SUBSPECIES,
)
from mechanics.social.persona import get_species_key_from_race
from cogs.contacts import build_contact_detail_embed


class TestCanidFelidFamilyAndRoleCoupling(unittest.TestCase):

    def test_animal_family_subspecies_randomized_distribution(self):
        """Verify animal families distribute across subspecies (wolf/fox/fennec, cat/tiger/lion/cheetah)."""
        canine_results = {resolve_animal_family_species("canine", seed=f"seed_{i}") for i in range(50)}
        self.assertIn("wolf", canine_results)
        self.assertIn("fox", canine_results)
        self.assertIn("fennec", canine_results)

        feline_results = {resolve_animal_family_species("feline", seed=f"seed_{i}") for i in range(50)}
        self.assertIn("cat", feline_results)
        self.assertTrue(any(sub in feline_results for sub in ("tiger", "lion", "cheetah")))

    def test_extract_race_from_narrative_with_animal_family(self):
        """Verify extract_race_from_text handles canine/feline family keywords."""
        text_canine = "Near the fountain, Yea-ji, a tall canine student with snow-white fur, is fielding questions."
        race_canine = extract_race_from_text(text_canine, scen_key="nsfw_furry_high_school_drama", name="Yea-ji")
        self.assertTrue(race_canine.startswith("beastfolk:"))
        self.assertIn(race_canine.split(":")[-1], ("wolf", "fox", "fennec"))

        text_feline = "Sitting by the tree, a calm felid girl watched the cherry blossoms."
        race_feline = extract_race_from_text(text_feline, scen_key="nsfw_furry_high_school_drama", name="Sora")
        self.assertTrue(race_feline.startswith("beastfolk:"))
        self.assertIn(race_feline.split(":")[-1], ("cat", "tiger", "lion", "cheetah"))

    def test_role_tightly_coupled_to_faction_affiliation(self):
        """Verify role shows specific title/Member when affiliated, but is dynamically hidden when unaffiliated."""
        # 1. Affiliated contact with explicit role
        aff_with_role = {
            "name": "Sofia Anderson",
            "relationship_score": 10,
            "basic_info": {
                "grade": "Senior",
                "club": "Student Council",
                "role": "Council President"
            },
            "appearance": {}
        }
        embed_aff = build_contact_detail_embed(aff_with_role, "nsfw_high_school_drama")
        basic_aff = next(f for f in embed_aff.fields if f.name == "Basic Details").value
        self.assertIn("• **Role**: Council President", basic_aff)
        self.assertIn("• **Faction Affiliation**: Student Council", basic_aff)

        # 2. Affiliated contact without explicit role -> defaults to Member
        aff_default_member = {
            "name": "Kenji",
            "relationship_score": 10,
            "basic_info": {
                "grade": "Freshman",
                "club": "Kendo Club",
                "role": "None"
            },
            "appearance": {}
        }
        embed_mem = build_contact_detail_embed(aff_default_member, "nsfw_high_school_drama")
        basic_mem = next(f for f in embed_mem.fields if f.name == "Basic Details").value
        self.assertIn("• **Role**: Member", basic_mem)
        self.assertIn("• **Faction Affiliation**: Kendo Club", basic_mem)

        # 3. Unaffiliated contact -> Role is dynamically hidden
        unaffiliated = {
            "name": "Yea-ji",
            "relationship_score": 1,
            "basic_info": {
                "grade": "None",
                "faction": "None",
                "role": "None"
            },
            "appearance": {}
        }
        embed_unaff = build_contact_detail_embed(unaffiliated, "nsfw_furry_high_school_drama")
        basic_unaff = next(f for f in embed_unaff.fields if f.name == "Basic Details").value
        self.assertIn("• **Faction Affiliation**: None", basic_unaff)
        self.assertNotIn("• **Role**:", basic_unaff)


if __name__ == "__main__":
    unittest.main()
