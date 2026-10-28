from __future__ import annotations
import unittest
import db
from game_engine.npcs import compute_pre_turn_stage
from mechanics.world.locations.movement import is_movement_action
from mechanics.world.locations.pathfinding import match_freeform_spatial_destination, format_node_hierarchy


class TestInvestigationActionSpatialImmunity(unittest.TestCase):
    def setUp(self):
        db.isolate_simulation_db()
        self.user_id = 9991234
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "balanced", False,
            scenario="nsfw_furry_gore_anomalous_incursions"
        )
        from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
        ensure_session_spatial_graph_seeded(self.session_id, "nsfw_furry_gore_anomalous_incursions")

    def test_analytical_and_infinitive_actions_do_not_trigger_movement(self):
        """
        Verify that investigative, analytical, tactical, and infinitive 'to <verb>' actions
        never falsely evaluate as movement actions.
        """
        non_movement_actions = [
            "Analyze the backward-running clock for resonance patterns",
            "Draw your service pistol and take a defensive stance near the kiosk",
            "Take a defensive stance in the room",
            "Take a moment to recalibrate your visor",
            "Attempt to run a diagnostic on the terminal",
            "Try to follow the instructions carefully",
            "Leave the blast door sealed to block the breach",
            "Use your strength to carry the injured investigator",
            "Keep the generator running in the hall",
            "Follow the resonance signal on the screen in the room",
            "Step up your efforts to seal the gate",
            "Analyze the data and take notes to prepare for the briefing",
            "Inspect the lock and move the pick to open it",
        ]
        for act in non_movement_actions:
            with self.subTest(action=act):
                self.assertFalse(is_movement_action(act), f"False positive movement on: {act}")

    def test_cross_zone_immunity_from_metro_terminal(self):
        """
        Verify that from the Metro Transit Terminal (zone_city_center), neither investigative
        actions nor LLM-mislabeled 'movement' tactical stances jump to school or airport nodes.
        """
        metro_nid = "loc_metro_transit_terminal"
        metro_loc = format_node_hierarchy(self.session_id, metro_nid)
        db.update_session(self.session_id, current_node_id=metro_nid, current_location=metro_loc)
        session = db.get_session(self.session_id)

        # 1. Clock analysis with investigate_clue intent
        act1 = {
            "label": "Analyze the backward-running clock for resonance patterns",
            "intent": "investigate_clue",
            "sub_intent": "deduce_clues",
            "stat": "INT",
        }
        stage1 = compute_pre_turn_stage(session, [act1])
        self.assertFalse(stage1["is_movement"])
        self.assertEqual(stage1["effective_node_id"], metro_nid)
        self.assertEqual(stage1["effective_location"], metro_loc)

        # 2. Tactical stance near kiosk even when LLM mislabels intent='movement' with empty target_node_id
        act2 = {
            "label": "Draw your service pistol and take a defensive stance near the kiosk",
            "intent": "movement",
            "target_node_id": "",
            "stat": "AGI",
        }
        stage2 = compute_pre_turn_stage(session, [act2])
        self.assertFalse(stage2["is_movement"])
        self.assertEqual(stage2["effective_node_id"], metro_nid)
        self.assertEqual(stage2["effective_location"], metro_loc)

    def test_same_zone_campus_facility_freeform_movement_preserved(self):
        """
        Verify that when the player is actually inside the school campus zone (sub_school_gate),
        natural single-noun freeform commands ('Walk to the cafeteria', 'Walk to the library',
        'Head to the gymnasium', 'Go to the rooftop', 'Head to the running track') still resolve cleanly.
        """
        gate_nid = "sub_school_gate"
        expected = {
            "Walk to the cafeteria": "loc_school_courtyard",
            "Walk to the library": "sub_school_library",
            "Head to the gymnasium": "sub_gym_foyer",
            "Go to the rooftop": "loc_school_rooftop",
            "Head to the running track": "sub_athletic_track",
            "Go to the basketball court": "sub_gym_court",
        }
        for phrase, target_nid in expected.items():
            with self.subTest(phrase=phrase):
                matched = match_freeform_spatial_destination(
                    self.session_id, gate_nid, phrase, intent="movement"
                )
                self.assertEqual(matched, target_nid)


if __name__ == "__main__":
    unittest.main()
