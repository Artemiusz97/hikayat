import unittest
from cogs.adventure import _get_choice_emoji, _get_choice_quest_icon, _get_choice_skill_emoji


class TestChoiceEmojiClassification(unittest.TestCase):
    def test_climax_actions(self):
        choice = {'label': '⚡ [Story Climax] Present your leadership plan', 'stat': 'CHA', 'requirement': 7, 'is_climax_action': True}
        self.assertEqual(_get_choice_quest_icon(choice), '⚡')
        self.assertEqual(_get_choice_skill_emoji(choice), '🗣️')
        self.assertEqual(_get_choice_emoji(choice), '⚡ 🗣️')

        choice2 = {'label': 'Conclude the final chapter', 'stat': 'NONE', 'requirement': 0, 'contract_type': 'climax'}
        self.assertEqual(_get_choice_quest_icon(choice2), '⚡')
        self.assertEqual(_get_choice_skill_emoji(choice2), '✨')
        self.assertEqual(_get_choice_emoji(choice2), '⚡ ✨')

    def test_quest_actions(self):
        choice = {'label': '🎯 [Story Quest] Inspect the secured evidence locker', 'stat': 'INT', 'requirement': 6, 'is_quest_action': True}
        self.assertEqual(_get_choice_quest_icon(choice), '⭐')
        self.assertEqual(_get_choice_skill_emoji(choice), '🧠')
        self.assertEqual(_get_choice_emoji(choice), '⭐ 🧠')

        choice2 = {'label': '🎯 [Bounty] Hunt the shadow prowler', 'stat': 'STR', 'requirement': 8, 'contract_type': 'bounty'}
        self.assertEqual(_get_choice_quest_icon(choice2), '🎯')
        self.assertEqual(_get_choice_skill_emoji(choice2), '💪')
        self.assertEqual(_get_choice_emoji(choice2), '🎯 💪')

    def test_dialogue_actions_including_next_steps(self):
        choice = {'label': 'Discuss next steps with Yea-ji Kang', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '💬')

        choice2 = {'label': 'Comfort Zihan Moon and offer guidance', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice2), '💬')

        choice3 = {'label': 'Consult Amélie on immediate rollout logistics', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice3), '💬')

        choice4 = {'label': 'Speak with Harold Wójcik', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice4), '💬')

    def test_scene_inspection_actions(self):
        choice = {'label': 'Look around the Student Council Office and observe the atmosphere', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '🔍')

        choice2 = {'label': 'Inspect the intricate crest carved above the fireplace', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice2), '🔍')

    def test_ambient_prop_interactions(self):
        choice = {'label': 'Sit on the sofa and review notes', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '🛋️')

        choice2 = {'label': 'Pour a warm cup of tea while listening to the council', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice2), '☕')

        choice3 = {'label': 'Check the documents and records on the table', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice3), '🖐️')

        choice4 = {'label': 'Read the public notice board', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice4), '📜')

    def test_travel_and_movement_actions(self):
        choice = {'label': 'Travel toward the Westlake Courtyard', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '🚶')

        choice2 = {'label': 'Exit the office and step into the hallway', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice2), '🚶')

        choice3 = {'label': 'Depart for the library to meet the contact', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice3), '🚶')

    def test_wilderness_actions(self):
        choice = {'label': 'Scout deeper into the overgrown ruins', 'stat': 'NONE', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '🧭')

    def test_stat_checks(self):
        choice_str = {'label': 'Force open the rusted door', 'stat': 'STR', 'requirement': 8}
        self.assertEqual(_get_choice_emoji(choice_str), '💪')

        choice_cha = {'label': 'Persuade the stubborn guard', 'stat': 'CHA', 'requirement': 7}
        self.assertEqual(_get_choice_emoji(choice_cha), '🗣️')

        choice_int = {'label': 'Decipher the ancient runes', 'stat': 'INT', 'requirement': 6}
        self.assertEqual(_get_choice_emoji(choice_int), '🧠')

    def test_item_stat(self):
        choice = {'label': 'Use the skeleton key on the vault', 'stat': 'ITEM', 'requirement': 0}
        self.assertEqual(_get_choice_emoji(choice), '🎒')


if __name__ == '__main__':
    unittest.main()
