import unittest
import time
import db
from mechanics.world.locations import (
    parse_tiered_location,
    ensure_session_locations_seeded,
    get_discovered_primary_locations,
)
from mechanics.world.waypoints import (
    check_location_matches_waypoint,
    try_advance_on_arrival,
    try_complete_on_skill_check,
)
from game_engine import apply_outcome


class TestReverseSpatialAndBountyCompletion(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 888123
        self.user_id = 999123
        self.char_id = 111123

        # Clean up existing test session if any
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (self.char_id,))
            conn.commit()

        # Seed test character & session
        char_dict = db.create_character(
            user_id=self.user_id,
            name="Artemiusz",
            char_class="Student",
            gold=50,
            scenario="high_school_drama"
        )
        self.char_id = char_dict["id"]
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO sessions (id, mode, capacity, scenario, current_location) VALUES (?, 'solo', 1, 'high_school_drama', 'Westlake Academy -> Classroom 2-B')",
                (self.session_id,)
            )
            conn.commit()
        ensure_session_locations_seeded(self.session_id, "high_school_drama", char_name="Artemiusz")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (self.char_id,))
            conn.commit()

    def test_reverse_spatial_resolution(self):
        # 1. Domestic single rooms must resolve to residential neighborhood, never Westlake Academy
        z, p, s = parse_tiered_location("Bedroom", "high_school_drama", session_id=self.session_id, char_name="Artemiusz")
        self.assertIn("Residential", z)
        self.assertIn("House", p)
        self.assertEqual(s, "Your Bedroom")

        z2, p2, s2 = parse_tiered_location("Maya's Room", "high_school_drama", session_id=self.session_id, char_name="Artemiusz")
        self.assertIn("Residential", z2)
        self.assertEqual(p2, "Anderson Residence")
        self.assertEqual(s2, "Maya's Room")

        # 2. Known Tier 2 primary place resolves to parent campus zone as primary
        from mechanics.world.locations import get_session_cultural_arts_name
        arts_name = get_session_cultural_arts_name(self.session_id, "high_school_drama")
        z3, p3, s3 = parse_tiered_location("Student Council Office", "high_school_drama", session_id=self.session_id)
        self.assertEqual(z3, arts_name)
        self.assertEqual(p3, "Student Council Office")
        self.assertEqual(s3, "Main Area")

        # 3. 3-part inversion auto-corrects primary place and prunes intermediate wings
        z4, p4, s4 = parse_tiered_location(f"{arts_name} -> Administration Wing -> Student Council Office", "high_school_drama", session_id=self.session_id)
        self.assertEqual(z4, arts_name)
        self.assertEqual(p4, "Student Council Office")
        self.assertEqual(s4, "Main Area")

        # 4. 2-part Primary -> Sub resolves parent zone
        z5, p5, s5 = parse_tiered_location("Artemiusz's House -> Bedroom", "high_school_drama", session_id=self.session_id, char_name="Artemiusz")
        self.assertIn("Residential", z5)
        self.assertIn("House", p5)
        self.assertEqual(s5, "Your Bedroom")

    
    def test_check_location_matches_waypoint(self):
        curr = "Westlake Academy ➔ Student Council Office ➔ Main Area"
        tgt_inverted = "Westlake Academy -> Administration Wing -> Student Council Office"
        tgt_direct = "Westlake Academy -> Student Council Office"
        tgt_different = "Westlake Academy -> School Library"

        self.assertTrue(check_location_matches_waypoint(curr, tgt_inverted))
        self.assertTrue(check_location_matches_waypoint(curr, tgt_direct))
        self.assertFalse(check_location_matches_waypoint(curr, tgt_different))

    def test_strict_linear_bounty_progression_and_completion(self):
        qid = "BNT-TEST01"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Side Bounty",
            title="Secret Admirer Letter Delivery",
            objective="Deliver the note to Rachel Vance.",
            progress="0/3 Stages",
            status="Active",
            reward_xp=150,
            reward_gold=40,
            is_story_quest=0
        )

        waypoints = [
            {
                "stage_index": 1,
                "stage_label": "Meet client Justin at Classroom 3-B",
                "target_location": "Westlake Academy -> Classroom 3-B",
                "completion_trigger": "arrival"
            },
            {
                "stage_index": 2,
                "stage_label": "Slip the note onto Rachel's desk at Student Council Office",
                "target_location": "Westlake Academy -> Student Council Office",
                "completion_trigger": "skill_check"
            },
            {
                "stage_index": 3,
                "stage_label": "Report back to Justin at Classroom 3-B",
                "target_location": "Westlake Academy -> Classroom 3-B",
                "completion_trigger": "arrival"
            }
        ]
        db.save_quest_waypoints(self.session_id, qid, waypoints, sub_obj_id=None)

        # Verify strict linear locking
        wp1 = db.get_active_waypoint(self.session_id, qid, None)
        self.assertEqual(wp1["stage_index"], 1)
        self.assertEqual(wp1["status"], "active")

        wps_all = db.get_quest_waypoints(self.session_id, qid, None)
        self.assertEqual(wps_all[0]["status"], "active")
        self.assertEqual(wps_all[1]["status"], "locked")
        self.assertEqual(wps_all[2]["status"], "locked")

        # Stage 2 cannot be triggered while locked
        res_premature = try_complete_on_skill_check(
            session_id=self.session_id,
            quest_id=qid,
            sub_obj_id=None,
            current_location="Westlake Academy ➔ Student Council Office ➔ Main Area",
            check_success=True,
            action_text="slip note on desk"
        )
        self.assertIsNone(res_premature)

        # Complete Stage 1 (arrival at Classroom 3-B)
        res1 = try_advance_on_arrival(
            session_id=self.session_id,
            quest_id=qid,
            sub_obj_id=None,
            current_location="Westlake Academy ➔ Classroom 3-B ➔ Front Row Desks"
        )
        self.assertIsNotNone(res1)
        self.assertEqual(res1["stage_completed"], 1)
        self.assertFalse(res1["all_stages_complete"])

        # Stage 2 is now unlocked and active
        wp2 = db.get_active_waypoint(self.session_id, qid, None)
        self.assertEqual(wp2["stage_index"], 2)
        self.assertEqual(wp2["status"], "active")

        # Complete Stage 2 (skill check at Student Council Office)
        res2 = try_complete_on_skill_check(
            session_id=self.session_id,
            quest_id=qid,
            sub_obj_id=None,
            current_location="Westlake Academy ➔ Student Council Office ➔ Main Area",
            check_success=True,
            action_text="slip note onto desk"
        )
        self.assertIsNotNone(res2)
        self.assertEqual(res2["stage_completed"], 2)
        self.assertFalse(res2["all_stages_complete"])

        # Stage 3 is now unlocked and active
        wp3 = db.get_active_waypoint(self.session_id, qid, None)
        self.assertEqual(wp3["stage_index"], 3)
        self.assertEqual(wp3["status"], "active")

        # Complete Stage 3 (arrival back at Classroom 3-B)
        res3 = try_advance_on_arrival(
            session_id=self.session_id,
            quest_id=qid,
            sub_obj_id=None,
            current_location="Westlake Academy ➔ Classroom 3-B ➔ Front Row Desks"
        )
        self.assertIsNotNone(res3)
        self.assertEqual(res3["stage_completed"], 3)
        self.assertTrue(res3["all_stages_complete"])

        # Execute apply_outcome to verify deterministic completion and rewards
        char_obj = db.get_character(self.user_id)
        party = [(char_obj, self.user_id)]
        outcome = {
            "location": "Westlake Academy ➔ Classroom 3-B ➔ Front Row Desks",
            "outcome_narrative": "Justin breathes a sigh of relief as you confirm the letter was safely delivered.",
            "next_narrative": "The favor is finished.",
            "character_outcomes": [{"hp_change": 0, "mp_change": 0}],
        }
        apply_outcome(self.session_id, party, outcome)

        # Verify rewards claimed deterministically
        self.assertIn("_quest_reward_notices", outcome)
        claim_notices = outcome["_quest_reward_notices"]
        self.assertEqual(len(claim_notices), 1)
        self.assertEqual(claim_notices[0]["title"], "Secret Admirer Letter Delivery")
        self.assertEqual(claim_notices[0]["xp"], 150)
        self.assertEqual(claim_notices[0]["gold"], 40)

        # Verify database quest status is Completed
        final_q = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(final_q["status"], "Completed")
        self.assertEqual(final_q["reward_claimed"], 1)


if __name__ == "__main__":
    unittest.main()
