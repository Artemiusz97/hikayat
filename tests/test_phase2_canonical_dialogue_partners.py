import unittest
import json
from mechanics.world.mobility import get_session_dialogue_partners, is_dialogue_partner
from game_engine.npcs import get_session_dialogue_partners as npcs_get_session_dps


class TestPhase2CanonicalDialoguePartners(unittest.TestCase):
    """Verifies Phase 2 canonical dialogue partner state and eradication of string-splitting bugs."""

    def test_legacy_single_partner_string(self):
        """Verify legacy single string 'dialogue_partner' resolves to a clean single-item list."""
        sess = {"dialogue_partner": "Denise Richards"}
        dps = get_session_dialogue_partners(sess)
        self.assertEqual(dps, ["Denise Richards"])
        # Crucial: Must NEVER iterate characters
        self.assertNotIn("D", dps)
        self.assertNotIn("e", dps)

    def test_json_encoded_dialogue_partners_string(self):
        """Verify JSON-serialized array in 'dialogue_partners' parses correctly."""
        sess = {"dialogue_partners": json.dumps(["Denise Richards", "Justin Anderson"])}
        dps = get_session_dialogue_partners(sess)
        self.assertEqual(dps, ["Denise Richards", "Justin Anderson"])

    def test_native_list_dialogue_partners(self):
        """Verify native Python list in 'dialogue_partners' is returned cleanly."""
        sess = {"dialogue_partners": ["Denise Richards", "Justin Anderson"]}
        dps = get_session_dialogue_partners(sess)
        self.assertEqual(dps, ["Denise Richards", "Justin Anderson"])

    def test_both_keys_populated_deduplication(self):
        """Verify that when both dialogue_partner and dialogue_partners are present, they are merged and deduplicated."""
        sess = {
            "dialogue_partner": "Denise Richards",
            "dialogue_partners": ["Justin Anderson", "denise richards"]
        }
        dps = get_session_dialogue_partners(sess)
        self.assertEqual(len(dps), 2)
        self.assertEqual(dps[0], "Justin Anderson")
        self.assertEqual(dps[1].lower(), "denise richards")

    def test_empty_or_malformed_dialogue_state(self):
        """Verify empty strings, empty lists, and invalid JSON fail safely to empty lists."""
        cases = [
            {},
            None,
            {"dialogue_partner": ""},
            {"dialogue_partners": []},
            {"dialogue_partners": "[]"},
            {"dialogue_partners": "{invalid json}"},
            {"dialogue_partner": None, "dialogue_partners": None}
        ]
        for sess in cases:
            self.assertEqual(get_session_dialogue_partners(sess), [])

    def test_is_dialogue_partner_with_session_kwarg(self):
        """Verify is_dialogue_partner accepts session dict directly."""
        sess = {"dialogue_partner": "Elder Maerwyn Rootspeaker"}
        self.assertTrue(is_dialogue_partner("Elder Maerwyn", session=sess))
        self.assertTrue(is_dialogue_partner("Maerwyn", session=sess))
        self.assertFalse(is_dialogue_partner("Justin Anderson", session=sess))

    def test_npcs_facade_matches_mobility(self):
        """Verify game_engine.npcs exports the same canonical helper."""
        sess = {"dialogue_partner": "Beatrice Sterling"}
        self.assertEqual(npcs_get_session_dps(sess), ["Beatrice Sterling"])


if __name__ == "__main__":
    unittest.main()
