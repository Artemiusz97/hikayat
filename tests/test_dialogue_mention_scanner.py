import unittest
from mechanics.world.mobility import is_mentioned_only_in_dialogue, has_active_physical_presence


class TestDialogueMentionScanner(unittest.TestCase):
    def test_dialogue_mention_not_physically_present(self):
        text = (
            "Maya looks out over the campus, her fluffy tail swaying slowly behind her. "
            'She turns back to Artemiusz. "Most people just assume it is for fashion," she says. '
            '"Sofia has her own thing going on—she is all about the mechanics—and I wanted something mine."'
        )

        self.assertTrue(is_mentioned_only_in_dialogue("Sofia Anderson", text))
        self.assertFalse(has_active_physical_presence("Sofia Anderson", {}, narrative_text=text))
        self.assertTrue(has_active_physical_presence("Maya Anderson", {}, narrative_text=text))


if __name__ == "__main__":
    unittest.main()
