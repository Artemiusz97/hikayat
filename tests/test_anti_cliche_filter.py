"""
Unit tests for Anti-Cliché Comparative Flattery Filter and History De-Echoer.
Verifies that immersion-breaking tropes like 'Most guys would be too nervous...'
are cleanly intercepted without touching legitimate factual group observations.
"""
import unittest
from unittest.mock import patch, AsyncMock
import game_engine
from game_engine import sanitize_comparative_cliches, push_history, _history_text
import db


class TestAntiClicheFilter(unittest.IsolatedAsyncioTestCase):
    def test_prunes_user_screenshot_1_flattery_trope(self):
        """Verify that Turn 1 flattery trope with internal ellipsis is cleanly pruned."""
        raw = (
            'Sofia lets out a soft, breathy laugh, her gaze lingering on him with a mixture of curiosity and genuine desire. '
            'She doesn\'t shy away; instead, she leans back further against the rooftop bench, her posture open and inviting. '
            '"You\'ve got some nerve, you know that?" she says, her voice carrying a playful, confident edge. '
            '"Most guys are too nervous to even look me in the eye, let alone... present themselves like this."'
        )
        cleaned = sanitize_comparative_cliches(raw)
        self.assertNotIn("Most guys are too nervous", cleaned)
        self.assertIn('"You\'ve got some nerve, you know that?"', cleaned)
        self.assertTrue(cleaned.endswith('playful, confident edge.'))

    def test_prunes_user_screenshot_2_flattery_trope(self):
        """Verify that Turn 2 repetitive trope is cleanly pruned with perfect quote preservation."""
        raw = (
            '"Not a bad view," she says, her voice carrying a playful, athletic directness. '
            '"Actually, it\'s quite a bold display. I like that you aren\'t hiding it. '
            'Most guys would be too nervous to just... stand there and wait for a reaction." '
            'She shifts slightly on the bench, the movement causing her chest to heave under her athletic gear, '
            'her eyes returning to his with a spark of genuine curiosity.'
        )
        cleaned = sanitize_comparative_cliches(raw)
        self.assertNotIn("Most guys would be too nervous", cleaned)
        self.assertIn('"Actually, it\'s quite a bold display. I like that you aren\'t hiding it."', cleaned)
        self.assertIn('She shifts slightly on the bench', cleaned)

    def test_preserves_factual_group_and_sports_observations(self):
        """Verify that non-flattery factual statements about groups are 100% preserved."""
        factual_1 = 'Sofia ties her running shoes tightly. "Most guys on the track team couldn\'t finish the 400m sprint in under 55 seconds," she says with a confident grin. "Let\'s see how you do."'
        factual_2 = 'The corridors are empty. Most students have already left the academy for the evening.'
        
        self.assertEqual(sanitize_comparative_cliches(factual_1), factual_1)
        self.assertEqual(sanitize_comparative_cliches(factual_2), factual_2)

    def test_strips_inline_comparative_clauses(self):
        """Verify that inline comparative clauses separated by commas are cleanly stripped."""
        raw = '"You\'re remarkably bold, unlike most guys who are too nervous to approach me." Sofia smirked.'
        cleaned = sanitize_comparative_cliches(raw)
        self.assertNotIn("unlike most guys", cleaned)
        self.assertIn('"You\'re remarkably bold."', cleaned)

    def test_strips_not_like_other_guys_trope(self):
        """Verify that 'You are not like the other guys' is stripped."""
        raw = '"You\'re not like the other guys at this school." She leaned against the railing.'
        cleaned = sanitize_comparative_cliches(raw)
        self.assertNotIn("not like the other guys", cleaned)
        self.assertIn("She leaned against the railing.", cleaned)

    def test_push_history_and_history_text_de_echoing(self):
        """Verify that history arrays are scrubbed upon entry and upon prompt preparation."""
        history = [
            '[Success] Artemiusz: Stare boldly -> Sofia smiles. "Most guys are too nervous to look at me."',
            '[Success] Artemiusz: Laugh -> Sofia nods approvingly.'
        ]
        
        # Test _history_text
        prompt_hist = _history_text(history)
        self.assertNotIn("Most guys are too nervous", prompt_hist)
        
        # Test push_history
        new_hist = push_history(history, 'Sofia says: "Most guys would be terrified." Then she smiled.')
        self.assertNotIn("Most guys would be terrified", new_hist[-1])
        self.assertIn("Then she smiled.", new_hist[-1])

    async def test_resolve_turn_sanitizes_llm_narrative_outputs(self):
        """Verify end-to-end turn resolution cleans comparative clichés from LLM output."""
        session = {
            "id": 999111,
            "scenario": "nsfw_high_school_drama",
            "current_location": "Westlake Academy ➔ School Rooftop",
            "history": [],
            "dialogue_partners": ["Sofia Anderson"],
            "current_npcs": [{"name": "Sofia Anderson", "role": "Track Captain"}],
            "turn_order": [12345]
        }
        party = [({"id": 12345, "name": "Artemiusz", "user_id": 12345}, [])]
        
        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"
            chance = 90
            tier_label = "Success"
            
        actions = [{
            "char": party[0][0],
            "label": "Look at Sofia confidently",
            "stat": "CHA",
            "check": MockCheck(),
            "mp_spent": 0
        }]
        
        mock_llm_response = {
            "outcome_narrative": 'Sofia blushes slightly. "Most guys would be too nervous to gaze at me like that." She turns toward him.',
            "next_narrative": 'The wind blows across the rooftop. "You\'re not like other men." Sofia grins.',
            "next_choices": [{"label": "Step forward", "stat": "CHA", "requirement": 6}]
        }
        
        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_llm_response
            result = await game_engine.resolve_turn(session, party, actions)
            
            self.assertNotIn("Most guys would be too nervous", result["outcome_narrative"])
            self.assertNotIn("not like other men", result["next_narrative"])
            self.assertIn("She turns toward him.", result["outcome_narrative"])
            self.assertIn("Sofia grins.", result["next_narrative"])


if __name__ == "__main__":
    unittest.main()
