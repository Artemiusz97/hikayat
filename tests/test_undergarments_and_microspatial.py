"""
Unit and integration tests for Undergarments System and Microspatial Physical Engine Synchronization.
"""
import unittest
import json
from mechanics import persona, physical_state
import db
from cogs.contacts import build_intimate_profile_embed


class TestUndergarmentsAndMicrospatial(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_procedural_undergarment_female_matching_set(self):
        """Verify female characters receive matching bra and underwear sets with realistic styling."""
        res = persona.generate_procedural_undergarments(
            seed_str="elena_vance",
            gender="female",
            openness="moderate",
            hash_val=100
        )
        self.assertIn("bra", res)
        self.assertIn("underwear", res)
        self.assertTrue(len(res["bra"]) > 0)
        self.assertTrue(len(res["underwear"]) > 0)

    def test_procedural_undergarment_male(self):
        """Verify male characters receive underwear without bra."""
        res = persona.generate_procedural_undergarments(
            seed_str="marcus_reid",
            gender="male",
            openness="moderate",
            hash_val=102
        )
        self.assertEqual(res["bra"], "")
        self.assertTrue(len(res["underwear"]) > 0)

    def test_prude_characters_never_commando(self):
        """Verify prude/modest characters have 0% commando rates across 50 seeds."""
        for i in range(50):
            res_f = persona.generate_procedural_undergarments(
                seed_str=f"prude_female_{i}",
                gender="female",
                openness="prude",
                hash_val=i * 137
            )
            self.assertNotIn("none", res_f["bra"].lower())
            self.assertNotIn("none", res_f["underwear"].lower())

            res_m = persona.generate_procedural_undergarments(
                seed_str=f"prude_male_{i}",
                gender="male",
                openness="prude",
                hash_val=i * 137
            )
            self.assertNotIn("none", res_m["underwear"].lower())

    def test_bold_characters_commando_and_daring_styles(self):
        """Verify bold/shameless characters generate commando/bra-less states and daring lingerie styles."""
        commando_count = 0
        for i in range(50):
            res_f = persona.generate_procedural_undergarments(
                seed_str=f"bold_female_{i}",
                gender="female",
                openness="shameless",
                dynamic="insatiable / voracious",
                hash_val=i * 100
            )
            if "none" in res_f["bra"].lower() or "none" in res_f["underwear"].lower():
                commando_count += 1
            else:
                is_bold_style = any(k in (res_f["bra"] + " " + res_f["underwear"]).lower() for k in (
                    "sheer", "lace", "strappy", "thong", "mesh", "g-string", "peekaboo", "bra-less", "commando"
                ))
                self.assertTrue(is_bold_style)

        self.assertGreater(commando_count, 0)

    def test_custom_undergarments_preserved_in_normalize_appearance(self):
        """Verify custom undergarments from LLM narrative overrides are strictly preserved."""
        custom_input = {
            "undergarments": {
                "bra": "Crimson silk corset with gold lace",
                "underwear": "Matching sheer crimson silk thong"
            }
        }
        normalized = persona.normalize_appearance(custom_input, gender="female", scen_key="nsfw_high_school_drama")
        self.assertEqual(normalized["undergarments"]["bra"], "Crimson silk corset with gold lace")
        self.assertEqual(normalized["undergarments"]["underwear"], "Matching sheer crimson silk thong")

    def test_progressive_disclosure_masking_and_unmasking(self):
        """Verify undergarments are masked at Level 1 and unmasked at Level 3 or when revealed."""
        app_data = {
            "undergarments": {
                "bra": "Black lace plunge bra",
                "underwear": "Matching black lace thong"
            }
        }
        # Level 1 -> *Unknown*
        sec_l1 = persona.format_intimate_profile_sections(app_data, gender="female", info_level=1)
        self.assertIn("• **Bra**: *Unknown*", sec_l1["undergarments"])
        self.assertIn("• **Underwear**: *Unknown*", sec_l1["undergarments"])
        self.assertNotIn("bra", sec_l1["discovered"])

        # Level 3 -> Revealed
        sec_l3 = persona.format_intimate_profile_sections(app_data, gender="female", info_level=3)
        self.assertIn("• **Bra**: Black lace plunge bra", sec_l3["undergarments"])
        self.assertIn("• **Underwear**: Matching black lace thong", sec_l3["undergarments"])
        self.assertEqual(sec_l3["discovered"]["bra"], "Black lace plunge bra")

        # Level 1 with underwear_revealed -> Revealed
        sec_rev = persona.format_intimate_profile_sections(
            app_data, gender="female", info_level=1, revealed_flags={"underwear_revealed": True}
        )
        self.assertIn("• **Bra**: Black lace plunge bra", sec_rev["undergarments"])

    def test_microspatial_engine_initializes_commando_states(self):
        """Verify physical_state engine initializes under_top and under_bottom as None when character is bra-less or commando."""
        char_commando = {
            "name": "Maya Anderson",
            "gender": "female",
            "appearance": {
                "undergarments": {
                    "bra": "None (Bra-less)",
                    "underwear": "None (Commando)"
                }
            }
        }
        state = physical_state.init_default_physical_state(
            session_id=0,
            party=[(char_commando, [])],
            scen_key="nsfw_high_school_drama"
        )
        actor_data = state["actors"]["Maya Anderson"]
        self.assertEqual(actor_data["clothing"]["under_top"], "None (Bra-less)")
        self.assertEqual(actor_data["clothing"]["under_bottom"], "None (Commando)")

    def test_microspatial_prompt_block_injects_continuity_directives(self):
        """Verify intimate prompt block injects strict continuity directive forbidding non-existent undergarment removal."""
        session = {
            "id": 12345,
            "physical_state": {
                "actors": {
                    "Maya Anderson": {
                        "posture": "Sitting on bed",
                        "holding": "Empty hands",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": "None (Bra-less)",
                            "under_bottom": "Worn (Matching black lace thong)"
                        }
                    }
                },
                "props": {},
                "intimate_contact": "kissing / embrace"
            }
        }
        prompt_block = physical_state.build_physical_prompt_block(session, party=[], is_nsfw=True)
        self.assertIn("None (Bra-less)", prompt_block)
        self.assertIn("Matching black lace thong", prompt_block)
        self.assertIn("Strictly respect clothing removal states and worn undergarments", prompt_block)
        self.assertIn("NEVER describe unclasping, stripping, or removing a non-existent undergarment", prompt_block)

    def test_intimate_profile_embed_contains_undergarments_field(self):
        """Verify Discord /contacts intimate profile embed includes the 👙 Undergarments field."""
        contact = {
            "name": "Maya Anderson",
            "gender": "female",
            "relationship_score": 100,
            "appearance": {
                "undergarments": {
                    "bra": "Black lace plunge bra",
                    "underwear": "Matching black lace thong"
                }
            }
        }
        embed = build_intimate_profile_embed(contact, scenario_key="nsfw_high_school_drama")
        field_names = [f.name for f in embed.fields]
        self.assertIn("👙 Undergarments", field_names)
        under_field = next(f for f in embed.fields if f.name == "👙 Undergarments")
        self.assertIn("Black lace plunge bra", under_field.value)
        self.assertIn("Matching black lace thong", under_field.value)


if __name__ == "__main__":
    unittest.main()
