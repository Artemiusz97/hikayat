"""
tests/test_pre_turn_stage_manager.py
====================================
Tests for pre-turn stage resolution in game_engine/npcs/stage_manager.py:
  - Deterministic effective_location resolution before prompting
  - Traveling companions carried over
  - Left-behind patrons separated from active stage
  - Destination rendezvous and scheduled station NPCs injected into stage_npcs
  - Explicit dismissal / dialogue exit
"""
import unittest
import db
from game_engine.npcs.stage_manager import compute_pre_turn_stage


class TestPreTurnStageManager(unittest.TestCase):
    def setUp(self):
        self.user_id = 999801
        self.session_id = 999802
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

        self.char = db.create_character(
            user_id=self.user_id,
            name="Ren",
            char_class="Student",
            gender="male"
        )
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        db.save_session_location(self.session_id, "classroom", "Westlake Academy", "Classroom 2-B", "Desks", atmosphere="Sunlit room")
        db.save_session_location(self.session_id, "library", "Westlake Academy", "Library", "Study Tables", atmosphere="Quiet rows of books")
        db.save_session_location(self.session_id, "courtyard", "Westlake Academy", "Central Courtyard", "Fountain", atmosphere="Fresh breeze")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

    def test_same_room_preserves_npcs_with_roles(self):
        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Classroom 2-B ➔ Desks",
            "current_npcs": [
                {"name": "Mia Tanaka", "role": "Classmate"},
                {"name": "Kenji Sato", "role": "Bystander"}
            ],
            "dialogue_partner": "Mia Tanaka"
        }
        actions = [{"label": "Talk with Mia about the homework", "stat": "CHA"}]

        stage = compute_pre_turn_stage(session, actions)
        self.assertFalse(stage["is_movement"])
        self.assertEqual(stage["effective_location"], "Classroom 2-B ➔ Desks")

        names = [n["name"] for n in stage["stage_npcs"]]
        self.assertIn("Mia Tanaka", names)
        self.assertIn("Kenji Sato", names)

        # Stage roles
        mia = next(n for n in stage["stage_npcs"] if n["name"] == "Mia Tanaka")
        kenji = next(n for n in stage["stage_npcs"] if n["name"] == "Kenji Sato")
        self.assertEqual(mia["stage_role"], "active_partner")
        self.assertEqual(kenji["stage_role"], "room_bystander")

    def test_movement_drops_left_behind_and_carries_companions(self):
        # Register a temporary companion
        db.add_temporary_companion(self.session_id, {"name": "Mia Tanaka", "role": "Companion"})

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Classroom 2-B ➔ Desks",
            "current_npcs": [
                {"name": "Mia Tanaka", "role": "Companion"},
                {"name": "Kenji Sato", "role": "Patron"}
            ],
            "dialogue_partner": "Mia Tanaka"
        }
        actions = [{"label": "Head to the Library with Mia", "stat": "AGI"}]

        stage = compute_pre_turn_stage(session, actions)
        self.assertTrue(stage["is_movement"])
        self.assertIn("Library", stage["effective_location"])

        stage_names = [n["name"] for n in stage["stage_npcs"]]
        # Mia is traveling companion
        self.assertIn("Mia Tanaka", stage_names)
        # Kenji was left behind
        self.assertNotIn("Kenji Sato", stage_names)
        left_behind_names = [n["name"] for n in stage["left_behind_patrons"]]
        self.assertIn("Kenji Sato", left_behind_names)

    def test_movement_injects_rendezvous_partner(self):
        # Save pending rendezvous appointment at Library
        db.save_rendezvous_appointment(
            session_id=self.session_id,
            npc_id="yuki_mori",
            npc_name="Yuki Mori",
            rendezvous_location="Westlake Academy ➔ Library ➔ Study Tables",
            topic="Secret Meeting",
            is_confidential=False,
            created_minute=500,
            expiry_minute=600
        )

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Central Courtyard ➔ Fountain",
            "current_npcs": [
                {"name": "Kenji Sato", "role": "Bystander"}
            ]
        }
        actions = [{"label": "Walk over to the Library for the meeting", "stat": "AGI"}]

        stage = compute_pre_turn_stage(session, actions)
        self.assertTrue(stage["is_movement"])
        self.assertIn("Library", stage["effective_location"])

        stage_names = [n["name"] for n in stage["stage_npcs"]]
        self.assertIn("Yuki Mori", stage_names)
        self.assertIn("Yuki Mori", stage["new_partners"])

    def test_stage_npcs_have_micro_blocking_and_composure(self):
        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Classroom 2-B ➔ Desks",
            "current_minute": 500,
            "current_npcs": [
                {"name": "Mia Tanaka", "role": "Classmate", "club": "Literature", "preferences": ["Likes Green Tea"]},
                {"name": "Kenji Sato", "role": "Bystander", "club": "Track"}
            ],
            "dialogue_partner": "Mia Tanaka"
        }
        actions = [{"label": "Talk with Mia about the homework", "stat": "CHA"}]

        stage = compute_pre_turn_stage(session, actions)
        mia = next(n for n in stage["stage_npcs"] if n["name"] == "Mia Tanaka")
        kenji = next(n for n in stage["stage_npcs"] if n["name"] == "Kenji Sato")

        # Mia is active partner: proximity conversational_distance, focus paused_attentive
        self.assertIn("micro_blocking", mia)
        self.assertEqual(mia["micro_blocking"]["proximity"], "conversational_distance")
        self.assertEqual(mia["micro_blocking"]["prop_focus"], "paused_attentive")
        self.assertEqual(mia["composure_state"], "composed")

        # Kenji is room bystander: proximity across_room, focus absorbed
        self.assertIn("micro_blocking", kenji)
        self.assertEqual(kenji["micro_blocking"]["proximity"], "across_room")
        self.assertEqual(kenji["micro_blocking"]["prop_focus"], "absorbed")
        self.assertEqual(kenji["composure_state"], "composed")

    def test_update_stage_blocking_and_composure_post_turn(self):
        from game_engine.npcs.stage_manager import update_stage_blocking_and_composure_post_turn
        session = {
            "id": self.session_id,
            "scene_stage_state": {
                "mia tanaka": {
                    "micro_blocking": {
                        "spot_and_posture": "seated at a desk",
                        "active_prop": "a notebook",
                        "prop_focus": "paused_attentive",
                        "proximity": "conversational_distance",
                    },
                    "composure_state": "composed",
                    "composure_ttl": 0,
                }
            }
        }

        # 1. Flirtatious / teasing action triggers flustered with ttl=3
        actions = [{"label": "Playfully tease Mia with a bold compliment"}]
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=actions,
            narrative="Mia Tanaka blushes deeply, flustered by your words.",
            rel_deltas={"mia tanaka": 1}
        )
        mia_state = session["scene_stage_state"]["mia tanaka"]
        self.assertEqual(mia_state["composure_state"], "flustered")
        self.assertEqual(mia_state["composure_ttl"], 3)

        # 2. Touch / physical contact evolves proximity to personal_space and prop_focus to set_aside
        touch_actions = [{"label": "Gently hold Mia's hand across the table"}]
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=touch_actions,
            narrative="You take her hand gently.",
            rel_deltas={"mia tanaka": 2}
        )
        self.assertEqual(mia_state["micro_blocking"]["proximity"], "personal_space")
        self.assertEqual(mia_state["micro_blocking"]["prop_focus"], "set_aside")

        # 3. Calm turn decrements ttl (from 2 down to 1)
        calm_actions = [{"label": "Listen attentively"}]
        update_stage_blocking_and_composure_post_turn(
            session=session,
            actions=calm_actions,
            narrative="The conversation settles into a peaceful rhythm.",
            rel_deltas={"mia tanaka": 0}
        )
        self.assertEqual(mia_state["composure_ttl"], 1)


if __name__ == "__main__":
    unittest.main()
