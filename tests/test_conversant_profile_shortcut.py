import unittest
from unittest.mock import MagicMock, patch
import discord
from cogs.adventure import is_matching_contact_dialogue_partner, ChoiceView, SyncChoiceView

class TestConversantProfileShortcut(unittest.TestCase):
    def test_matcher_exact_and_variations(self):
        c_amanda = {"name": "Amanda Anderson", "npc_id": "amanda_anderson"}
        c_sofia = {"name": "Sofia Anderson", "npc_id": "sofia_anderson"}
        c_maerwyn = {"name": "Elder Maerwyn Rootspeaker", "npc_id": "maerwyn_rootspeaker"}

        # Exact matches
        self.assertTrue(is_matching_contact_dialogue_partner(c_amanda, "Amanda Anderson"))
        self.assertTrue(is_matching_contact_dialogue_partner(c_amanda, "amanda_anderson"))
        self.assertTrue(is_matching_contact_dialogue_partner(c_amanda, "Amanda"))
        self.assertTrue(is_matching_contact_dialogue_partner(c_amanda, "Mrs. Amanda Anderson"))

        # Negative matches across family members sharing the same surname
        self.assertFalse(is_matching_contact_dialogue_partner(c_amanda, "Sofia Anderson"))
        self.assertFalse(is_matching_contact_dialogue_partner(c_amanda, "Justin Anderson"))
        self.assertFalse(is_matching_contact_dialogue_partner(c_amanda, "Maya Anderson"))
        self.assertFalse(is_matching_contact_dialogue_partner(c_sofia, "Amanda Anderson"))

        # Titles and names
        self.assertTrue(is_matching_contact_dialogue_partner(c_maerwyn, "Maerwyn"))
        self.assertTrue(is_matching_contact_dialogue_partner(c_maerwyn, "Elder Maerwyn Rootspeaker"))
        self.assertTrue(is_matching_contact_dialogue_partner(c_maerwyn, "Maerwyn Rootspeaker"))

    @patch("cogs.adventure.views.choices.db")
    def test_choiceview_button_present_when_in_dialogue_with_contact(self, mock_db):
        session_id = 999
        user_id = 12345
        actor_char = {"id": 1, "name": "Protagonist", "user_id": user_id}
        contacts = [
            {"name": "Amanda Anderson", "npc_id": "amanda_anderson"},
            {"name": "Sofia Anderson", "npc_id": "sofia_anderson"}
        ]
        session = {
            "id": session_id,
            "scenario": "high_school_drama",
            "dialogue_partner": "Amanda Anderson",
            "dialogue_partners": ["Amanda Anderson"],
            "current_npcs": [{"name": "Amanda Anderson"}, {"name": "Sofia Anderson"}],
            "choices_style": "dropdown"
        }
        mock_db.get_session.return_value = session
        mock_db.get_contacts.return_value = contacts
        mock_db.get_settings.return_value = {}
        mock_db.get_faction_by_hq.return_value = None

        cog = MagicMock()
        view = ChoiceView(cog, session_id, user_id, choices=[], actor_char=actor_char)

        profile_btns = [
            btn for btn in view.children
            if isinstance(btn, discord.ui.Button) and str(btn.emoji) == "👤"
        ]
        # Must have exactly 1 button for Amanda, and NOT Sofia
        self.assertEqual(len(profile_btns), 1)
        self.assertIn("Amanda", profile_btns[0].label)
        self.assertNotIn("Sofia", profile_btns[0].label)

    @patch("cogs.adventure.views.choices.db")
    def test_choiceview_button_absent_when_npc_merely_in_scene(self, mock_db):
        session_id = 999
        user_id = 12345
        actor_char = {"id": 1, "name": "Protagonist", "user_id": user_id}
        contacts = [
            {"name": "Amanda Anderson", "npc_id": "amanda_anderson"},
            {"name": "Sofia Anderson", "npc_id": "sofia_anderson"}
        ]
        # NPC is in scene, but player is NOT in active dialogue with them!
        session = {
            "id": session_id,
            "scenario": "high_school_drama",
            "dialogue_partner": None,
            "dialogue_partners": [],
            "current_npcs": [{"name": "Amanda Anderson"}, {"name": "Sofia Anderson"}],
            "choices_style": "dropdown"
        }
        mock_db.get_session.return_value = session
        mock_db.get_contacts.return_value = contacts
        mock_db.get_settings.return_value = {}
        mock_db.get_faction_by_hq.return_value = None

        cog = MagicMock()
        view = ChoiceView(cog, session_id, user_id, choices=[], actor_char=actor_char)

        profile_btns = [
            btn for btn in view.children
            if isinstance(btn, discord.ui.Button) and str(btn.emoji) == "👤"
        ]
        # Must NOT have any profile button
        self.assertEqual(len(profile_btns), 0)

    @patch("cogs.adventure.views.choices.db")
    def test_choiceview_button_absent_when_conversant_not_in_contacts(self, mock_db):
        session_id = 999
        user_id = 12345
        actor_char = {"id": 1, "name": "Protagonist", "user_id": user_id}
        # Contacts list does NOT contain the stranger
        contacts = [
            {"name": "Sofia Anderson", "npc_id": "sofia_anderson"}
        ]
        session = {
            "id": session_id,
            "scenario": "high_school_drama",
            "dialogue_partner": "Mysterious Cloaked Figure",
            "dialogue_partners": ["Mysterious Cloaked Figure"],
            "current_npcs": [{"name": "Mysterious Cloaked Figure"}],
            "choices_style": "dropdown"
        }
        mock_db.get_session.return_value = session
        mock_db.get_contacts.return_value = contacts
        mock_db.get_settings.return_value = {}
        mock_db.get_faction_by_hq.return_value = None

        cog = MagicMock()
        view = ChoiceView(cog, session_id, user_id, choices=[], actor_char=actor_char)

        profile_btns = [
            btn for btn in view.children
            if isinstance(btn, discord.ui.Button) and str(btn.emoji) == "👤"
        ]
        self.assertEqual(len(profile_btns), 0)

    @patch("cogs.adventure.views.choices.db")
    def test_syncchoiceview_button_present_in_multiplayer(self, mock_db):
        session_id = 999
        user_id = 12345
        contacts = [{"name": "Sofia Anderson", "npc_id": "sofia_anderson"}]
        session = {
            "id": session_id,
            "scenario": "high_school_drama",
            "dialogue_partner": "Sofia Anderson",
            "dialogue_partners": ["Sofia Anderson"],
            "current_npcs": [{"name": "Sofia Anderson"}],
            "choices_style": "dropdown"
        }
        mock_db.get_session.return_value = session
        mock_db.get_contacts.return_value = contacts
        mock_db.get_faction_by_hq.return_value = None

        cog = MagicMock()
        view = SyncChoiceView(cog, session_id, member_ids=[user_id], choices=[], party=[({"id": 1, "name": "Player"}, [])])

        profile_btns = [
            btn for btn in view.children
            if isinstance(btn, discord.ui.Button) and str(btn.emoji) == "👤"
        ]
        self.assertEqual(len(profile_btns), 1)
        self.assertIn("Sofia", profile_btns[0].label)

if __name__ == "__main__":
    unittest.main()
