import unittest
from unittest.mock import patch, AsyncMock
import db
import game_engine
from cogs.contacts import build_contact_detail_embed
from mechanics.social.persona import (
    categorize_likes_and_dislikes, format_mannerisms_list,
    sanitize_npc_description
)

class MockCheck:
    succeeded = True
    is_success = True
    tier = "success"
    chance = 90

class TestLikesDislikesAndMannerisms(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 11223344
        self.user_id = 55667788

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(user_id=self.user_id, name="Hero", gender="male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")

        self.contact_sofia = {
            "session_id": self.session_id,
            "character_id": self.char["id"],
            "npc_id": "sofia_anderson",
            "name": "Sofia Anderson",
            "race": "fox_beastfolk",
            "gender": "female",
            "relationship_score": 100,
            "track": "platonic",
            "traits": ["Confident", "Responsive", "Focused"],
            "preferences": ["Likes Attention", "Likes Precision", "Likes Control", "Dislikes Sloppiness", "Dislikes Power Outages"],
            "mannerisms": "Winks playfully while their tail swishes in rhythmic beats",
            "basic_info": {
                "grade": "Junior",
                "role": "Robotics & Tech Apprentice",
                "club": "Science & Robotics Club",
                "club_role": "Club Officer",
                "sibling_name": "Maya Anderson",
                "mannerisms": "Winks playfully while their tail swishes in rhythmic beats",
                "description": "Junior at Westlake Academy. Analytical tinkerer with boundless creative energy. Sibling of Maya Anderson."
            },
            "appearance": {
                "breast_size": "large",
                "predetermined_intercourse_experience": "virgin",
                "intimate_demeanor": "Blunt & Teasing",
                "intimate_dynamic": "Switch / Sensual"
            }
        }

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            delta_score=100,
            track="platonic",
            new_traits=self.contact_sofia["traits"],
            new_preferences=self.contact_sofia["preferences"],
            basic_info=self.contact_sofia["basic_info"],
            appearance=self.contact_sofia["appearance"]
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_categorize_likes_and_dislikes(self):
        """Verify that preferences are properly categorized into 2-3 Likes and 2-3 Dislikes."""
        raw_prefs = ["Likes Attention", "Likes Precision", "Likes Control", "Dislikes Sloppiness"]
        likes, dislikes = categorize_likes_and_dislikes(raw_prefs, role="Robotics")

        self.assertGreaterEqual(len(likes), 2)
        self.assertLessEqual(len(likes), 3)
        self.assertGreaterEqual(len(dislikes), 2)
        self.assertLessEqual(len(dislikes), 3)

        self.assertIn("Likes Attention", likes)
        self.assertIn("Likes Precision", likes)
        self.assertIn("Dislikes Sloppiness", dislikes)

    def test_format_mannerisms_list(self):
        """Verify that mannerisms format into 1-3 distinct bulleted items."""
        single_mannerism = "Winks playfully while their tail swishes in rhythmic beats"
        res = format_mannerisms_list(single_mannerism, race="fox_beastfolk", desc="Fox student")

        self.assertGreaterEqual(len(res), 1)
        self.assertLessEqual(len(res), 3)
        self.assertIn("Winks playfully while their tail swishes in rhythmic beats", res)

    def test_sanitize_npc_description_removes_sibling(self):
        """Verify that sibling strings are stripped from description text."""
        raw_desc = "Junior at Westlake Academy. Analytical tinkerer. Sibling of Maya Anderson."
        cleaned = sanitize_npc_description(raw_desc)
        self.assertNotIn("Sibling of Maya Anderson", cleaned)
        self.assertIn("Analytical tinkerer", cleaned)

    def test_basic_details_embed_formatting_and_fallback(self):
        """Verify that Grade, Role, Faction Affiliation, and Details are always shown, and Sibling is removed."""
        embed = build_contact_detail_embed(self.contact_sofia, "nsfw_high_school_drama", user_id=self.user_id)
        basic_field = next(f for f in embed.fields if f.name == "Basic Details")

        self.assertIn("• **Grade / Standing**: Junior", basic_field.value)
        self.assertIn("• **Role**: Robotics & Tech Apprentice", basic_field.value)
        self.assertIn("• **Faction Affiliation**: Science & Robotics Club (Club Officer)", basic_field.value)
        self.assertIn("• **Details**:", basic_field.value)
        self.assertNotIn("Sibling", basic_field.value)

        # Test fallback with empty character
        empty_contact = {
            "name": "Nameless Wanderer",
            "relationship_score": 0,
            "basic_info": {},
            "appearance": {}
        }
        empty_embed = build_contact_detail_embed(empty_contact, "fantasy", user_id=self.user_id)
        empty_basic = next(f for f in empty_embed.fields if f.name == "Basic Details")
        self.assertIn("• **Grade / Standing**: None", empty_basic.value)
        self.assertNotIn("• **Role**:", empty_basic.value)
        self.assertIn("• **Faction Affiliation**: None", empty_basic.value)
        self.assertIn("• **Details**: None", empty_basic.value)

    def test_embed_progressive_disclosure_of_likes_dislikes_and_mannerisms(self):
        """Verify disclosure across Level 1 (masked) vs Level 3 (fully revealed)."""
        # Level 1 Stranger View
        stranger_contact = dict(self.contact_sofia)
        stranger_contact["relationship_score"] = 10
        embed_lvl1 = build_contact_detail_embed(stranger_contact, "nsfw_high_school_drama", user_id=self.user_id)

        field_map_lvl1 = {f.name: f for f in embed_lvl1.fields}
        self.assertEqual(field_map_lvl1["🎭 Mannerisms & Habits"].value, "• *Not yet observed*")
        self.assertEqual(field_map_lvl1["🧠 Unlocked Traits"].value, "*0/3 traits discovered*")
        self.assertEqual(field_map_lvl1["👍 Likes & Preferences"].value, "*0/3 likes discovered*")
        self.assertEqual(field_map_lvl1["👎 Dislikes"].value, "*0/3 dislikes discovered*")

        # Level 3 Devoted View
        embed_lvl3 = build_contact_detail_embed(self.contact_sofia, "nsfw_high_school_drama", user_id=self.user_id)
        field_map_lvl3 = {f.name: f for f in embed_lvl3.fields}

        self.assertIn("• Winks playfully", field_map_lvl3["🎭 Mannerisms & Habits"].value)
        self.assertIn("Confident", field_map_lvl3["🧠 Unlocked Traits"].value)
        self.assertIn("Likes Attention", field_map_lvl3["👍 Likes & Preferences"].value)
        self.assertIn("Dislikes Sloppiness", field_map_lvl3["👎 Dislikes"].value)

    async def test_llm_prompt_injects_faction_likes_and_dislikes_at_level_3(self):
        """Verify that dialogue prompts receive Faction, Likes, Dislikes, and Preference Synergy at level 3."""
        db.save_session_scene(
            session_id=self.session_id,
            scene_title="Workshop",
            narrative="Sofia is testing robot motors.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ Robotics Lab",
            current_npcs=[{"name": "Sofia Anderson", "role": "Robotics & Tech Apprentice"}],
            dialogue_partner="Sofia Anderson"
        )
        session = db.get_session(self.session_id)

        actions = [{
            "char": self.char,
            "label": "Chat with Sofia Anderson about precision circuitry",
            "stat": "INT",
            "check": MockCheck(),
            "mp_spent": 0
        }]

        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "outcome_narrative": "Sofia lights up excitedly.",
                "next_narrative": "She demonstrates the new gear setup.",
                "next_choices": [{"label": "Help wire the circuit", "stat": "INT", "requirement": 5}]
            }
            await game_engine.resolve_turn(session, [(self.char, [])], actions)

            self.assertTrue(mock_call.called)
            user_prompt = mock_call.call_args_list[0][0][1]

            # Faction
            self.assertIn("Faction: Science & Robotics Club", user_prompt)
            # Likes & Dislikes
            self.assertIn("Likes & Desires: Likes Attention", user_prompt)
            self.assertIn("Dislikes & Aversions: Dislikes Sloppiness", user_prompt)
            self.assertIn("PREFERENCE SYNERGY:", user_prompt)
            # Mannerisms
            self.assertIn("Mannerisms & Habits: Winks playfully while their tail swishes in rhythmic beats", user_prompt)

    async def test_observation_action_reveals_mannerisms_early(self):
        """Verify that an observation check reveals mannerisms early."""
        # Reset score to 10 (Level 1)
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            delta_score=-90
        )

        db.save_session_scene(
            session_id=self.session_id,
            scene_title="Workshop",
            narrative="Sofia is sitting at the workbench.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ Robotics Lab",
            current_npcs=[{"name": "Sofia Anderson", "role": "Robotics & Tech Apprentice"}],
            dialogue_partner="Sofia Anderson"
        )
        session = db.get_session(self.session_id)

        actions = [{
            "char": self.char,
            "label": "Watch Sofia Anderson closely and observe her subtle habits",
            "stat": "PER",
            "check": MockCheck(),
            "mp_spent": 0
        }]

        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "outcome_narrative": "You watch Sofia closely.",
                "next_narrative": "She notices your glance and winks.",
                "next_choices": [{"label": "Smile back", "stat": "CHA", "requirement": 5}],
                "relationship_updates": [{"npc_name": "Sofia Anderson", "delta_score": 1}]
            }
            res = await game_engine.resolve_turn(session, [(self.char, [])], actions)
            game_engine.apply_outcome(self.session_id, [(self.char, [])], res, actions=actions)

        updated_contact = db.get_contact(self.session_id, "sofia_anderson", self.char["id"])
        app = updated_contact.get("appearance", {})
        self.assertTrue(app.get("mannerisms_revealed"))

if __name__ == "__main__":
    unittest.main()
