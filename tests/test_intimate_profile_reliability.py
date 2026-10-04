"""
Unit tests for Hikayat Intimate Profile Reliability, Milestone Validation Pipeline,
and Information Disclosure Gating.
"""
import unittest
import json
import db
import game_engine
from mechanics.social.persona import format_persona_embed_fields


class TestIntimateProfileReliability(unittest.TestCase):
    def setUp(self):
        self.session_id = 997755
        self.user_id = 886644

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Artemiusz",
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama"
        )
        db.save_session_scene(
            self.session_id,
            scene_title="Rooftop Benches",
            narrative="Artemiusz and Sofia are sitting by the railing.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ School Rooftop",
            current_npcs=[{"name": "Sofia Anderson", "role": "Club President"}],
            dialogue_partner="Sofia Anderson"
        )

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            basic_info={"role": "Club President"},
            appearance={
                "breast_size": "C-cup",
                "predetermined_intercourse": "has_received_oral",
                "intercourse_experience": "has_received_oral",
                "intimate_revealed": False,
                "intercourse_experience_revealed": False,
                "demeanor_revealed": False,
                "sensitive_spots_revealed": False,
                "turn_ons_revealed": False,
                "fetishes_revealed": False
            },
            track="platonic"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_intentional_romantic_action_records_kiss_milestone(self):
        """Verify that an intentional romantic kiss action with roll success accurately records a first_kiss milestone."""
        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"

        actions = [{"label": "💖 [CHA] Lean in close and share a tender first kiss with Sofia", "check": MockCheck()}]
        raw_result = {
            "scene_title": "Rooftop Benches",
            "narrative": "Artemiusz leaned in and Sofia smiled warmly as they shared a tender kiss against the rooftop railing.",
            "next_choices": [{"label": "Hold her hand"}],
            "relationship_updates": [
                {
                    "npc_name": "Sofia Anderson",
                    "milestone_event": "first_kiss",
                    "memory_summary": "Shared a tender first kiss under the rooftop railing.",
                    "delta_score": 8
                }
            ]
        }

        game_engine.apply_outcome(
            self.session_id,
            [(self.char, None)],
            raw_result,
            actions=actions
        )

        contact = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        mems = contact.get("intimate_memories", [])
        self.assertTrue(any("Shared a tender first kiss" in str(m) for m in mems))

    def test_disclosure_level_2_masks_intimate_profile(self):
        """Verify that at Information Disclosure Level 2, format_persona_embed_fields masks the intimate profile."""
        app = {
            "eye_color": "amber",
            "hair_color": "golden-blonde",
            "hair_length": "short",
            "hair_style": "ponytail",
            "stature": "athletic/tall",
            "breast_size": "C-cup",
            "intercourse_experience": "has_received_oral",
            "intimate_revealed": False,
            "intercourse_experience_revealed": False,
            "demeanor_revealed": False,
            "sensitive_spots_revealed": False,
            "turn_ons_revealed": False,
            "fetishes_revealed": False
        }

        fields = format_persona_embed_fields(
            app_dict=app,
            gender="female",
            race="human",
            scen_key="nsfw_high_school_drama",
            info_level=2,
            revealed_flags={}
        )

        intimate_field = next((f for f in fields if "Intimate Profile" in f["name"]), None)
        self.assertIsNotNone(intimate_field)
        self.assertIn("• **Intercourse**: *Unknown*", intimate_field["value"])
        self.assertIn("• **Demeanor**: *Unknown*", intimate_field["value"])
        self.assertIn("• **Sensitive Spots**: *Unknown*", intimate_field["value"])
        self.assertIn("• **Turn-Ons**: *Unknown*", intimate_field["value"])
        self.assertIn("• **Fetishes & Kinks**: *Unknown*", intimate_field["value"])
        self.assertNotIn("has_received_oral", intimate_field["value"])
        self.assertNotIn("C-cup", intimate_field["value"])

    def test_established_contact_race_is_immutable(self):
        """Verify that an established contact's race cannot be overwritten by subsequent upsert calls."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="kitsune_girl",
            name="Kitsune Girl",
            race="beastfolk:fox"
        )
        c1 = db.get_contact(self.session_id, "kitsune_girl", self.char["id"])
        self.assertEqual(c1["race"], "beastfolk:fox")

        # Subsequent upsert attempts to downgrade to human
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="kitsune_girl",
            name="Kitsune Girl",
            race="human"
        )
        c2 = db.get_contact(self.session_id, "kitsune_girl", self.char["id"])
        self.assertEqual(c2["race"], "beastfolk:fox", "Established race must be immutable against generic human downgrades")


if __name__ == "__main__":
    unittest.main()

