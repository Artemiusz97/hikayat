"""
Unit tests for Meetup Location Filtering and Quest Target Isolation.
"""
import unittest
import db
import mechanics.world.waypoints as waypoints


class TestMeetupAndQuestIsolation(unittest.TestCase):
    def setUp(self):
        self.session_id = 994411
        self.user_id = 884411

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))

        db.create_character(self.user_id, "Protagonist", "male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))

    def test_quest_action_not_injected_when_target_npc_absent(self):
        """When a waypoint requires Michael Suzuki, but only Maya is present, quest action is NOT injected."""
        rooftop = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO quests (session_id, quest_id, quest_type, title, objective, status, is_story_quest, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.session_id, "SQ-TEST", "Story Quest", "School Hierarchy Dispute", "Resolve disputes", "Active", 1, 1000, 1000)
            )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id="SQ-TEST",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Negotiate a compromise that satisfies both academic and athletic needs",
                "target_location": "Westlake Academy -> School Rooftop",
                "target_npc": "Michael Suzuki",
                "completion_trigger": "skill_check"
            }],
            sub_obj_id=1
        )

        # Set session on rooftop with only Maya present
        db.save_session_scene(
            self.session_id,
            scene_title="Rooftop Chat",
            narrative="Maya is chatting with you on the rooftop.",
            choices=[],
            history=["Turn 1"],
            location=rooftop,
            current_npcs=[{"name": "Maya Anderson"}],
            dialogue_partner="Maya Anderson"
        )

        raw_choices = [
            {"label": "Ask Maya about her hobbies", "stat": "INT", "requirement": 5},
            {"label": "Tease Maya about her observation skills", "stat": "CHA", "requirement": 6}
        ]

        enriched = waypoints.tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location=rooftop,
            scen_key="high_school_drama",
            char=self.char
        )

        # No choices should be tagged as quest action because Michael Suzuki is not present
        self.assertFalse(any(c.get("is_quest_action") for c in enriched))
        # No fallback compromise choice should be injected
        self.assertFalse(any("compromise" in str(c.get("label", "")).lower() for c in enriched))

    def test_quest_action_injected_when_target_npc_present(self):
        """When Michael Suzuki is physically present, quest action IS injected."""
        gym = "School Grounds & Athletics ➔ Main Gymnasium ➔ Basketball Court"

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO quests (session_id, quest_id, quest_type, title, objective, status, is_story_quest, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.session_id, "SQ-TEST", "Story Quest", "School Hierarchy Dispute", "Resolve disputes", "Active", 1, 1000, 1000)
            )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id="SQ-TEST",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Negotiate a compromise that satisfies both academic and athletic needs",
                "target_location": "School Grounds & Athletics -> Main Gymnasium",
                "target_npc": "Michael Suzuki",
                "completion_trigger": "skill_check"
            }],
            sub_obj_id=1
        )

        db.save_session_scene(
            self.session_id,
            scene_title="Gym Confrontation",
            narrative="Michael Suzuki is practicing his forms in the gym.",
            choices=[],
            history=["Turn 1"],
            location=gym,
            current_npcs=[{"name": "Michael Suzuki"}],
            dialogue_partner="Michael Suzuki"
        )

        raw_choices = [
            {"label": "Propose a compromise that satisfies both sides", "stat": "CHA", "requirement": 6},
            {"label": "Observe his martial arts technique", "stat": "PER", "requirement": 5}
        ]

        enriched = waypoints.tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location=gym,
            scen_key="high_school_drama",
            char=self.char
        )

        self.assertTrue(any(c.get("is_quest_action") for c in enriched))

    def test_meetup_locations_exclude_active_quest_locations(self):
        """Active quest waypoint locations must not be suggested for social meetups."""
        db.save_session_location(self.session_id, "gym_court", "School Grounds & Athletics", "Main Gymnasium", "Basketball Court", atmosphere="Squeak of sneakers")
        db.save_session_location(self.session_id, "school_rooftop", "Westlake Academy", "School Rooftop", "Rooftop Benches", atmosphere="Breeze")
        db.save_session_location(self.session_id, "courtyard_fountain", "Westlake Academy", "Central Courtyard", "Fountain Benches", atmosphere="Charming fountain")

        # Quest occupies Gymnasium
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO quests (session_id, quest_id, quest_type, title, objective, status, is_story_quest, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.session_id, "SQ-GYM", "Story Quest", "Gym Dispute", "Resolve gym dispute", "Active", 1, 1000, 1000)
            )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id="SQ-GYM",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Go to Gym",
                "target_location": "School Grounds & Athletics -> Main Gymnasium",
                "target_npc": "Michael Suzuki",
                "completion_trigger": "arrival"
            }],
            sub_obj_id=1
        )

        all_locs = db.get_session_locations(self.session_id)
        active_wps = db.get_all_session_active_waypoints(self.session_id)
        quest_occupied_locs = [wp.get("target_location", "") for wp in active_wps if wp.get("target_location")]

        from mechanics.world.waypoints import check_location_matches_waypoint
        public_locs = []
        for loc in all_locs:
            full_loc = f"{loc.get('zone_name', '')} ➔ {loc.get('primary_name', '')} ➔ {loc.get('sub_name', '')}"
            prim_loc = f"{loc.get('zone_name', '')} -> {loc.get('primary_name', '')}"
            is_quest_loc = any(
                check_location_matches_waypoint(full_loc, ql) or check_location_matches_waypoint(prim_loc, ql) or check_location_matches_waypoint(ql, full_loc)
                for ql in quest_occupied_locs
            )
            if not is_quest_loc:
                public_locs.append(loc)

        public_names = [l["primary_name"] for l in public_locs]
        self.assertIn("Central Courtyard", public_names)
        self.assertIn("School Rooftop", public_names)
        self.assertNotIn("Main Gymnasium", public_names)


if __name__ == "__main__":
    unittest.main()
