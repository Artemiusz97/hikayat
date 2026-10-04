import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import discord
from cogs.adventure import (
    AdventureCog,
    ChoiceDropdown,
    ChoiceView,
    SyncChoiceView,
    _get_choice_emoji,
    _get_choice_quest_icon,
    _get_choice_skill_emoji,
    _strip_leading_emojis,
    scene_embed,
    sync_scene_embed,
)


class TestMultiEmojiQuestSkillChecks(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 11223344
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.execute("INSERT INTO sessions (id, mode, capacity, scenario, current_location, choices_style) VALUES (?, 'solo', 1, 'fantasy', 'Academy -> Library', 'dropdown')", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_quest_icon_and_skill_emoji_detection(self):
        """Verify _get_choice_quest_icon and _get_choice_skill_emoji accurately identify quest types and stats."""
        # 1. Story Quest with INT check
        sq_int = {
            "label": "⭐ [Story Quest] Decipher the ancient stone runes",
            "stat": "INT",
            "requirement": 7,
            "quest_id": "SQ-12345",
            "is_quest_action": True,
            "is_story_quest": True
        }
        self.assertEqual(_get_choice_quest_icon(sq_int), "⭐")
        self.assertEqual(_get_choice_skill_emoji(sq_int), "🧠")
        self.assertEqual(_get_choice_emoji(sq_int), "⭐ 🧠")

        # 2. Bounty with AGI check
        bnt_agi = {
            "label": "🎯 [Bounty] Infiltrate the smuggler's hideout",
            "stat": "AGI",
            "requirement": 8,
            "quest_id": "BNT-67890",
            "is_quest_action": True,
            "contract_type": "bounty"
        }
        self.assertEqual(_get_choice_quest_icon(bnt_agi), "🎯")
        self.assertEqual(_get_choice_skill_emoji(bnt_agi), "🏹")
        self.assertEqual(_get_choice_emoji(bnt_agi), "🎯 🏹")

        # 3. Story Climax with CHA check
        climax_cha = {
            "label": "⚡ [Story Climax] Confront the high inquisitor",
            "stat": "CHA",
            "requirement": 9,
            "is_climax_action": True
        }
        self.assertEqual(_get_choice_quest_icon(climax_cha), "⚡")
        self.assertEqual(_get_choice_skill_emoji(climax_cha), "🗣️")
        self.assertEqual(_get_choice_emoji(climax_cha), "⚡ 🗣️")

        # 4. Story Quest Free Action (Travel)
        sq_travel = {
            "label": "⭐ [Story Quest] Travel toward the Old Ruin",
            "stat": "NONE",
            "requirement": 0,
            "quest_id": "SQ-12345",
            "is_quest_action": True
        }
        self.assertEqual(_get_choice_quest_icon(sq_travel), "⭐")
        self.assertEqual(_get_choice_skill_emoji(sq_travel), "🚶")
        self.assertEqual(_get_choice_emoji(sq_travel), "⭐ 🚶")

        # 5. Non-Quest Standard Skill Check
        std_int = {
            "label": "Study the historical manuscripts on the shelf",
            "stat": "INT",
            "requirement": 6
        }
        self.assertIsNone(_get_choice_quest_icon(std_int))
        self.assertEqual(_get_choice_skill_emoji(std_int), "🧠")
        self.assertEqual(_get_choice_emoji(std_int), "🧠")

    def test_dropdown_options_multi_emoji_presentation(self):
        """Verify ChoiceDropdown provides both the quest icon and the stat emoji/tag in dropdown options."""
        choices = [
            {
                "label": "⭐ [Story Quest] Analyze the magical anomaly",
                "stat": "INT",
                "requirement": 7,
                "quest_id": "SQ-A1",
                "is_quest_action": True
            },
            {
                "label": "🎯 [Bounty] Track the rogue beast",
                "stat": "PER",
                "requirement": 8,
                "quest_id": "BNT-B1",
                "is_quest_action": True
            },
            {
                "label": "Speak with the local archivist",
                "stat": "NONE",
                "requirement": 0
            }
        ]

        actor_char = {
            "user_id": 1001,
            "name": "Arthur",
            "int_": 8,
            "per_": 7,
            "agi_": 6
        }

        dropdown = ChoiceDropdown(
            cog=None,
            session_id=self.test_session_id,
            choices=choices,
            actor_char=actor_char,
            is_sync=False,
            turn_user_id=1001
        )

        options = dropdown.options
        self.assertEqual(len(options), 3)

        # Option 1: Story quest INT check
        # Option emoji: ⭐
        # Label: contains percentage, stat emoji 🧠, [INT], and clean text
        self.assertEqual(str(options[0].emoji), "⭐")
        self.assertIn("🧠", options[0].label)
        self.assertIn("[INT]", options[0].label)
        self.assertIn("Analyze the magical anomaly", options[0].label)

        # Option 2: Bounty PER check
        # Option emoji: 🎯
        # Label: contains percentage, stat emoji 👁️, [PER], and clean text
        self.assertEqual(str(options[1].emoji), "🎯")
        self.assertIn("👁️", options[1].label)
        self.assertIn("[PER]", options[1].label)
        self.assertIn("Track the rogue beast", options[1].label)

        # Option 3: Dialogue Free Action
        # Option emoji: 💬
        self.assertEqual(str(options[2].emoji), "💬")
        self.assertIn("Speak with the local archivist", options[2].label)

    def test_scene_embed_and_dropdown_multi_emoji(self):
        """Verify scene_embed omits choices field (now dropdown only) and ChoiceDropdown renders multi-emojis for quest actions."""
        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "choices_style": "dropdown",
            "current_location": "Academy -> Library",
            "turn_order": [1001]
        }
        actor = {
            "user_id": 1001,
            "name": "Arthur",
            "int_": 8,
            "agi_": 6,
            "stats": {"INT": 8, "AGI": 6}
        }
        choices = [
            {
                "label": "⭐ [Story Quest] Decipher the ancient scroll",
                "stat": "INT",
                "requirement": 7,
                "quest_id": "SQ-TEST",
                "is_quest_action": True,
                "is_story_quest": True
            },
            {
                "label": "🎯 [Bounty] Ambush the goblin sentry",
                "stat": "AGI",
                "requirement": 6,
                "quest_id": "BNT-TEST",
                "is_quest_action": True,
                "contract_type": "bounty"
            },
            {
                "label": "Examine the bookshelves",
                "stat": "NONE",
                "requirement": 0
            }
        ]

        embeds = scene_embed(
            session=session,
            actor_char=actor,
            scene_title="Ancient Archives",
            narrative="You stand in the dusty archives.",
            choices=choices
        )

        dash_embed = embeds[1]
        # Verify no Choices field in dash_embed (dropdown menu is now the only way)
        self.assertFalse(any("Choices" in f.name for f in dash_embed.fields))

        # Verify ChoiceDropdown renders multi-emojis correctly
        dropdown = ChoiceDropdown(
            cog=None,
            session_id=self.test_session_id,
            choices=choices,
            actor_char=actor,
            is_sync=False,
            turn_user_id=1001
        )
        opts = dropdown.options
        self.assertEqual(len(opts), 3)

        # Must have ⭐ quest emoji and 🧠 [INT] skill indicator in label
        self.assertEqual(str(opts[0].emoji), "⭐")
        self.assertIn("🧠 [INT]", opts[0].label)
        self.assertIn("Decipher the ancient scroll", opts[0].label)

        # Must have 🎯 bounty emoji and 🏹 [AGI] skill indicator in label
        self.assertEqual(str(opts[1].emoji), "🎯")
        self.assertIn("🏹 [AGI]", opts[1].label)
        self.assertIn("Ambush the goblin sentry", opts[1].label)

        # Must have 🔍 search emoji for examine action
        self.assertEqual(str(opts[2].emoji), "🔍")
        self.assertIn("Examine the bookshelves", opts[2].label)


if __name__ == "__main__":
    unittest.main()
