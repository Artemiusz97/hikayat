import unittest
import json
import db
from mechanics.world.locations.movement import (
    is_movement_action,
    extract_movement_destination,
    reconcile_movement_location,
)
from mechanics.world.locations.seeding import ensure_session_locations_seeded
import game_engine.npcs.presence as pres
import game_engine.turn.dialogue as dlg

HIGH_SCHOOL_SCENARIO = "high_school_drama"

class TestPrivateMeetingAndQuieterSpotIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session_id = 99881133
        cls.char_id = 88771133
        cls.char_name = "Artem"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO characters 
                (id, user_id, name, char_class, gender, scenario, race, hp, max_hp, mp, max_mp, level) 
                VALUES (?, ?, ?, 'Student', 'male', ?, 'human', 100, 100, 50, 50, 1)""",
                (cls.char_id, 99991133, cls.char_name, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute(
                """INSERT OR REPLACE INTO sessions 
                (id, mode, capacity, scenario, current_location, current_day, current_minute, turn_order, dialogue_partner) 
                VALUES (?, 'solo', 1, ?, 'Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree', 1, 480, '[]', '["Seo-ah Vance", "Kazuya Halloway"]')""",
                (cls.session_id, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (cls.session_id,))
            conn.commit()
        ensure_session_locations_seeded(cls.session_id, HIGH_SCHOOL_SCENARIO, char_name=cls.char_name)

    @classmethod
    def tearDownClass(cls):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (cls.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (cls.char_id,))
            conn.commit()

    def test_propose_moving_to_quieter_spot_is_recognized_as_dialogue_proposal(self):
        """Action proposing to move to a quieter spot is a dialogue proposal on turn 1, not immediate movement."""
        label = "Propose moving to a quieter spot near the glasshouse to discuss the Circle's budget leaks"
        self.assertFalse(is_movement_action(label))

        dest = extract_movement_destination(
            label,
            self.session_id,
            current_zone="Campus Promenade & Student Commons",
            scen_key=HIGH_SCHOOL_SCENARIO,
            allow_proposal=True
        )
        self.assertIsNotNone(dest)
        zone, primary = dest
        self.assertEqual(primary, "Botanical Glasshouse")

        # Turn 2 travel action IS recognized as movement
        travel_label = "[Travel to Botanical Glasshouse] (Meetup: Seo-ah Vance)"
        self.assertTrue(is_movement_action(travel_label))
        travel_dest = extract_movement_destination(
            travel_label,
            self.session_id,
            current_zone="Campus Promenade & Student Commons",
            scen_key=HIGH_SCHOOL_SCENARIO
        )
        self.assertIsNotNone(travel_dest)
        self.assertEqual(travel_dest[1], "Botanical Glasshouse")

    def test_reconcile_movement_updates_to_botanical_glasshouse(self):
        """Reconciliation on the travel turn arrives at Botanical Glasshouse."""
        curr_loc = "Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree"
        action = "[Travel to Botanical Glasshouse] (Meetup: Seo-ah Vance)"
        nar = "They stepped onto the gravel path toward the Botanical Glasshouse, walking past the humid orchids."
        
        reconciled = reconcile_movement_location(
            self.session_id,
            curr_loc,
            "",
            action_text=action,
            narrative=nar,
            scen_key=HIGH_SCHOOL_SCENARIO
        )
        self.assertIn("Botanical Glasshouse", reconciled)
        self.assertNotIn("Central Courtyard", reconciled)

    def test_classify_scene_npcs_isolates_private_meeting_companion(self):
        """In a private meeting proposal or travel, bystanders are left behind."""
        current_npcs = [
            {"name": "Seo-ah Vance", "role": "Student Council President"},
            {"name": "Kazuya Halloway", "role": "Student Council Vice President"},
            {"name": "Manon", "role": "Student"}
        ]
        sess = {
            "id": self.session_id,
            "dialogue_partner": "Seo-ah Vance",
            "dialogue_partners": ["Seo-ah Vance", "Kazuya Halloway"],
            "current_npcs": current_npcs,
            "current_location": "Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree"
        }
        actions = [{"label": "Propose moving to a quieter spot near the glasshouse to discuss the Circle's budget leaks"}]
        
        traveling, left_behind = pres.classify_scene_npcs(
            sess,
            actions=actions,
            old_primary="Central Courtyard",
            dest_primary="Botanical Glasshouse",
            new_loc="Campus Promenade & Student Commons ➔ Botanical Glasshouse"
        )

        left_behind_names = [n["name"] for n in left_behind]
        self.assertIn("Kazuya Halloway", left_behind_names)
        self.assertIn("Manon", left_behind_names)

    def test_compute_dialogue_intent_creates_rendezvous_appointment(self):
        """Rendezvous proposal creates an appointment, excuses the NPC to head there first, and leaves bystanders."""
        sess = {
            "id": self.session_id,
            "scenario": HIGH_SCHOOL_SCENARIO,
            "dialogue_partner": "Seo-ah Vance",
            "dialogue_partners": ["Seo-ah Vance", "Kazuya Halloway"],
            "current_npcs": [
                {"name": "Seo-ah Vance", "role": "Student Council President"},
                {"name": "Kazuya Halloway", "role": "Student Council Vice President"}
            ],
            "current_location": "Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree",
            "current_minute": 480
        }
        actions = [{"label": "Propose moving to a quieter spot near the glasshouse to discuss the Circle's budget leaks"}]

        new_partners, has_exited = dlg._compute_dialogue_intent(sess, actions)
        self.assertTrue(has_exited)
        self.assertNotIn("Seo-ah Vance", new_partners)
        self.assertIn("Kazuya Halloway", new_partners)

        # Check DB appointment was created
        appts = db.get_active_rendezvous_appointments(self.session_id)
        self.assertTrue(len(appts) >= 1)
        self.assertEqual(appts[0]["npc_name"], "Seo-ah Vance")
        self.assertIn("Botanical Glasshouse", appts[0]["rendezvous_location"])
        self.assertTrue(appts[0]["is_confidential"])

    def test_in_room_conversational_action_retains_botanical_glasshouse_and_dialogue_partner(self):
        """Conversational/roleplay action inside Botanical Glasshouse must retain zone, venue, and sub-location."""
        from mechanics.world.locations.hierarchy import parse_tiered_location
        glasshouse_loc = "Campus Promenade & Student Commons ➔ Botanical Glasshouse ➔ Interior Greenery Path"
        
        # Test 1: parse_tiered_location must not mutate Botanical Glasshouse into Residential zone
        pz, pp, ps = parse_tiered_location(glasshouse_loc, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertEqual(pz, "Campus Promenade & Student Commons")
        self.assertEqual(pp, "Botanical Glasshouse")
        self.assertEqual(ps, "Interior Greenery Path")

        # Test 2: reconcile_movement_location must retain exact grounded location on conversational action
        action_text = "Step closer against the glass wall and tease her about how flustered her ears are getting"
        narrative = "You close the distance, your denim jacket creaking softly as you press your shoulder firmly against the warm glass wall."
        reconciled = reconcile_movement_location(
            self.session_id,
            glasshouse_loc,
            "",
            action_text=action_text,
            narrative=narrative,
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertEqual(reconciled, glasshouse_loc)
        self.assertNotIn("Residential", reconciled)
        self.assertNotIn("Wakaba", reconciled)
