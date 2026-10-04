"""
Tests for School Roster & Grade Hierarchy integration into Quests and Bounties.
"""
import unittest
from unittest.mock import patch
import db
import game_engine
from mechanics import bounty, school_roster


class TestSchoolGradeQuestsAndBounties(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 887766
        self.test_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B",
            "current_npcs": []
        }
        with db.get_conn() as conn:
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.test_session_id,))
            conn.commit()
        school_roster.ensure_school_directory_exists(self.session)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.test_session_id,))
            conn.commit()

    @patch("mechanics.narrative.bounty.call_llm_json")
    async def test_generate_bounty_board_injects_grade_hierarchy_and_roster(self, mock_llm):
        """Verify generate_bounty_board injects directory NPCs and grade dynamics into the prompt."""
        mock_llm.return_value = {
            "bounties": [
                {
                    "quest_type": "Campus Commission",
                    "title": "Senior Council Audit",
                    "objective": "Help Julian Vance audit the club budget receipts in the Student Council Office.",
                    "reward_xp": 150,
                    "reward_gold": 50,
                    "reward_item": "Academy Commendation",
                    "waypoints": [
                        {
                            "stage_index": 1,
                            "stage_label": "Go to the Student Council Office",
                            "target_location": "Westlake Academy ➔ Administration Wing ➔ Student Council Office",
                            "target_npc": "Julian Vance",
                            "completion_trigger": "arrival"
                        }
                    ]
                }
            ]
        }

        bounties = await bounty.generate_bounty_board(self.session, force_refresh=True)
        self.assertEqual(len(bounties), 1)
        self.assertEqual(bounties[0]["title"], "Senior Council Audit")

        call_args = mock_llm.call_args
        user_prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("user_prompt", "")
        self.assertIn("CAMPUS DIRECTORY & GRADE HIERARCHY COMMISSIONS", user_prompt)
        self.assertIn("[Senior]", user_prompt)
        self.assertIn("[Junior]", user_prompt)
        self.assertIn("[Faculty]", user_prompt)
        self.assertIn("VALID REGIONAL DESTINATIONS FOR WAYPOINTS", user_prompt)
        self.assertIn("Town & Commercial Hangouts", user_prompt)
        self.assertIn("APPROPRIATE NARRATIVE REASONS & OBJECTIVES FOR TARGETING WIDER AREAS", user_prompt)
        self.assertIn("Study Fuel & Sugar Runs", user_prompt)

    @patch("mechanics.narrative.bounty.call_llm_json")
    async def test_generate_bounty_board_with_off_campus_multi_stage_waypoints(self, mock_llm):
        """Verify bounty board saves off-campus multi-stage waypoints across campus and commercial spots."""
        mock_llm.return_value = {
            "bounties": [
                {
                    "quest_type": "Off-Campus Errand",
                    "title": "Matcha Latte Study Fuel",
                    "objective": "Run down to Café Monolith in the commercial strip to fetch special pastries and matcha lattes for an all-night study session.",
                    "reward_xp": 180,
                    "reward_gold": 60,
                    "reward_item": "Café Loyalty Card",
                    "waypoints": [
                        {
                            "stage_index": 1,
                            "stage_label": "Meet the stressed classmate in the library to take their order",
                            "target_location": "Westlake Academy ➔ School Library",
                            "target_npc": "Chloe",
                            "completion_trigger": "arrival"
                        },
                        {
                            "stage_index": 2,
                            "stage_label": "Travel to Café Monolith in town and buy the study snacks",
                            "target_location": "Komorebi Commercial Strip ➔ Café Monolith",
                            "target_npc": "Barista",
                            "completion_trigger": "skill_check"
                        },
                        {
                            "stage_index": 3,
                            "stage_label": "Deliver the warm drinks back to the library",
                            "target_location": "Westlake Academy ➔ School Library",
                            "target_npc": "Chloe",
                            "completion_trigger": "skill_check"
                        }
                    ]
                }
            ]
        }

        bounties = await bounty.generate_bounty_board(self.session, force_refresh=True)
        self.assertEqual(len(bounties), 1)
        b_id = bounties[0]["quest_id"]

        wps = db.get_quest_waypoints(self.test_session_id, b_id)
        self.assertEqual(len(wps), 3)
        self.assertEqual(wps[0]["status"], "active")
        self.assertEqual(wps[1]["status"], "locked")
        self.assertEqual(wps[2]["status"], "locked")
        self.assertIn("Café Monolith", wps[1]["target_location"])
        self.assertIn("➔", wps[1]["target_location"])

    @patch("game_engine.call_llm_json")
    async def test_generate_story_quest_injects_campus_directory_leads(self, mock_llm):
        """Verify generate_story_quest injects school roster leads and grade dynamics for high school drama."""
        mock_llm.return_value = {
            "title": "Shadows Across Westlake Academy",
            "objective": "Unravel the missing council funds and clear your homeroom's name.",
            "sub_quests": [
                {
                    "id": 1,
                    "archetype": "Investigation",
                    "text": "Interview the Chemistry Teacher Dr. Thorne in the Science Wing.",
                    "waypoints": [
                        {
                            "stage_index": 1,
                            "stage_label": "Enter the Chemistry Lab",
                            "target_location": "Westlake Academy ➔ Science Wing ➔ Chemistry Lab",
                            "target_npc": "Dr. Aris Thorne",
                            "completion_trigger": "arrival"
                        }
                    ]
                }
            ]
        }

        sq = await game_engine.generate_story_quest(
            session_id=self.test_session_id,
            session=self.session,
            chapter_num=1
        )
        self.assertEqual(sq["title"], "Shadows Across Westlake Academy")

        call_args = mock_llm.call_args
        user_prompt = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("user_prompt", "")
        self.assertIn("CAMPUS DIRECTORY LEADS & GRADE DYNAMICS", user_prompt)
        self.assertIn("Westlake Academy", user_prompt)

    async def test_bounty_archetypes_prioritization_and_diversity(self):
        """Verify school and nsfw archetypes are prioritized over generic, icons match correctly, and diversity is enforced."""
        # 1. School scenario prioritization
        school_archs = bounty.get_archetypes_for_scenario("high_school_drama")
        # All 8 modern archetypes should be present at the beginning
        modern_expected = bounty.ARCHETYPES_BY_SCENARIO["modern"]
        for m in modern_expected:
            self.assertIn(m, school_archs)
            self.assertLess(school_archs.index(m), len(modern_expected))

        # Fantasy/combat exclusions
        self.assertNotIn("Monster Hunting", school_archs)
        self.assertNotIn("Arcane Ritual", school_archs)
        self.assertNotIn("Exorcism", school_archs)

        # 2. System prompt includes diversity requirement and all archetypes
        prompt = bounty.build_bounty_system_prompt("high_school_drama")
        self.assertIn("CRITICAL DIVERSITY REQUIREMENT", prompt)
        for m in modern_expected:
            self.assertIn(m, prompt)

        # 3. Icon matching resolves multi-word specificity correctly
        self.assertEqual(bounty.get_quest_type_icon("Academic Rescue"), "📚")
        self.assertEqual(bounty.get_quest_type_icon("Rescue"), "🛡️")
        self.assertEqual(bounty.get_quest_type_icon("Club Showdown"), "🏆")
        self.assertEqual(bounty.get_quest_type_icon("Gossip Control"), "💬")

        # 4. Refresh clears stale available bounties
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO quests (session_id, quest_id, quest_type, title, objective, status) VALUES (?, ?, ?, ?, ?, ?)",
                (self.test_session_id, "BNT-OLDTEST1", "Academic Rescue", "Old Stale Bounty", "Do work", "Available")
            )
            conn.commit()

        with patch("mechanics.narrative.bounty.call_llm_json") as mock_llm:
            mock_llm.return_value = {
                "bounties": [
                    {
                        "quest_type": "Club Showdown",
                        "title": "Drama Club Duel",
                        "objective": "Help win the rehearsal stage.",
                        "reward_xp": 100,
                        "reward_gold": 30,
                        "reward_item": "",
                        "waypoints": []
                    }
                ]
            }
            refreshed = await bounty.generate_bounty_board(self.session, force_refresh=True)
            self.assertEqual(len(refreshed), 1)
            self.assertEqual(refreshed[0]["title"], "Drama Club Duel")
            # The old stale available bounty should have been purged
            titles = [q["title"] for q in refreshed]
            self.assertNotIn("Old Stale Bounty", titles)


if __name__ == "__main__":
    unittest.main()
