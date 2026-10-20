import unittest
from unittest.mock import patch, AsyncMock
from skill_check import CheckResult
import game_engine
from game_engine.npcs.dialogue_tracking import extract_speaking_npcs_from_narrative
from game_engine.state.social import resolve_pre_turn_social_and_disclosures
from mechanics.social.affinity_engine import calculate_social_affinity_delta


class TestTargetedDialogueAndNameCollisionGuard(unittest.IsolatedAsyncioTestCase):
    """Verifies that:
    1. Player character name tokens do not cause NPCs with overlapping names to be misidentified as speaking.
    2. Failed checks targeting a specific NPC in a multi-dialogue scene do not penalize other dialogue partners.
    """

    def test_extract_speaking_npcs_ignores_player_name_collision(self):
        party = [({"id": 1, "name": "Artem"}, [])]
        npcs_present = [
            {"name": "Alicja Yamamoto"},
            {"name": "Artem Suzuki"},
            {"name": "Henry Sterling"},
        ]

        narrative = (
            "Artem offers a reassuring, easygoing shrug, his voice maintaining a steady, conversational pitch. "
            "'A casual approach is better,' she says, leaning slightly toward Alicja with a relaxed posture. "
            "Alicja smiles and replies, 'That makes sense.' "
            "Henry Sterling nods in agreement."
        )

        speaking = extract_speaking_npcs_from_narrative(
            narrative,
            npcs_present,
            party=party,
            player_name="Artem",
        )

        self.assertIn("Alicja Yamamoto", speaking)
        self.assertIn("Henry Sterling", speaking)
        self.assertNotIn(
            "Artem Suzuki",
            speaking,
            "Artem Suzuki must not be extracted as speaking when only player Artem spoke.",
        )

    def test_multi_dialogue_partner_targeted_failure_affinity_isolation(self):
        """When an action explicitly targets Alicja in a scene where both Alicja and Artem Suzuki
        are dialogue partners, a failed check must only penalize Alicja, leaving Artem Suzuki at 0.
        """
        party = [({"id": 1, "name": "Artem"}, [])]
        session = {
            "id": 8887711,
            "scenario": "high_school_drama",
            "dialogue_partners": ["Alicja Yamamoto", "Artem Suzuki"],
            "current_npcs": [
                {"name": "Alicja Yamamoto"},
                {"name": "Artem Suzuki"},
            ],
        }

        failed_check = CheckResult(
            chance=27,
            roll=75.0,
            tier="fail",
            tier_label="Failure",
            succeeded=False,
            requirement=15,
        )
        action = {
            "label": "Ask for Alicja Yamamoto's Phone Number / Contact Info",
            "stat": "CHA",
            "check": failed_check,
        }

        with patch("db.get_contact", return_value=None):
            pre_res = resolve_pre_turn_social_and_disclosures(session, party, [action])

        affinity_deltas = pre_res.get("affinity_deltas", {})
        self.assertEqual(
            affinity_deltas.get("Alicja Yamamoto"),
            -1,
            "Alicja must lose 1 affinity on failed skill check.",
        )
        self.assertEqual(
            affinity_deltas.get("Artem Suzuki"),
            0,
            "Artem Suzuki must not lose affinity on an action targeting Alicja.",
        )

    @patch("game_engine.call_llm_json", new_callable=AsyncMock)
    async def test_full_resolve_turn_affinity_isolation(self, mock_llm):
        """End-to-end verification that resolve_turn does not penalize non-targeted dialogue partner."""
        mock_llm.return_value = {
            "scene_title": "A Stiff Rejection",
            "outcome_narrative": "Alicja straightens her posture with sudden professional rigidity.",
            "next_narrative": "The air in the classroom feels colder.",
            "character_outcomes": [],
            "relationship_updates": [],
            "next_choices": [{"label": "Apologize politely", "stat": "CHA", "requirement": 4}]
        }

        char = {"id": 1, "user_id": 1001, "name": "Artem", "hp": 100, "max_hp": 100, "mp": 50, "max_mp": 50, "gold": 10, "status_effects": []}
        party = [(char, [])]
        session = {
            "id": 8887712,
            "scenario": "high_school_drama",
            "dialogue_partners": ["Alicja Yamamoto", "Artem Suzuki"],
            "current_npcs": [{"name": "Alicja Yamamoto"}, {"name": "Artem Suzuki"}],
            "history": [],
            "current_location": "Homeroom 204",
            "status": "active"
        }

        failed_check = CheckResult(
            chance=27,
            roll=75.0,
            tier="fail",
            tier_label="Failure",
            succeeded=False,
            requirement=15,
        )
        action = {
            "char": char,
            "label": "Ask for Alicja Yamamoto's Phone Number / Contact Info",
            "stat": "CHA",
            "check": failed_check,
        }

        with patch("db.get_contact", return_value=None), \
             patch("db.get_session_campaign_goals", return_value=[]), \
             patch("db.get_active_story_quest", return_value=None), \
             patch("db.get_session_quests", return_value=[]), \
             patch("db.get_session_chapter", return_value=1), \
             patch("game_engine.reconcile_movement_location", return_value="Homeroom 204"):
            outcome = await game_engine.resolve_turn(session, party, [action])

        rus = outcome.get("relationship_updates") or []
        alicja_ru = next((r for r in rus if r.get("npc_name") == "Alicja Yamamoto"), None)
        artem_s_ru = next((r for r in rus if r.get("npc_name") == "Artem Suzuki"), None)

        self.assertIsNotNone(alicja_ru, "Alicja must have a relationship update")
        self.assertEqual(alicja_ru["delta_score"], -1, "Alicja must receive -1 affinity")

        if artem_s_ru is not None:
            self.assertGreaterEqual(artem_s_ru["delta_score"], 0, "Artem Suzuki must not receive negative affinity")


if __name__ == "__main__":
    unittest.main()
