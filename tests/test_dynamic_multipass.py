import asyncio
import unittest
from unittest.mock import patch, AsyncMock, MagicMock

import config
import game_engine
import llm_client
from skill_check import CheckResult


class TestDynamicMultiPass(unittest.TestCase):

    def setUp(self):
        import db
        db.init_db()
        self.session = {
            "id": 101,
            "scenario": "fantasy",
            "current_location": "Sunfall Citadel ➔ High Courtyard ➔ Fount",
            "current_npcs": [{"name": "Guard Vance"}, {"name": "Lady Seraphina"}],
            "dialogue_partners": None,
            "nearby_monsters": [],
            "history": [],
        }
        self.party = [
            ({"name": "Aric", "user_id": 1001, "class": "Warrior", "hp": 50, "max_hp": 50, "mp": 20, "max_mp": 20, "gold": 100, "str": 8, "per": 5, "status_effects": []}, [])
        ]

    def test_schema_causal_order(self):
        """Verify that OUTCOME_SCHEMA lists prose-first narrative and choices before cosmetic poses and memory."""
        schema = game_engine.OUTCOME_SCHEMA
        pos_title = schema.find('"scene_title"')
        pos_narrative = schema.find('"outcome_narrative"')
        pos_next_narrative = schema.find('"next_narrative"')
        pos_choices = schema.find('"next_choices"')
        pos_poses = schema.find('"actor_poses"')
        pos_memory = schema.find('"episodic_memory"')

        self.assertNotEqual(pos_title, -1)
        self.assertNotEqual(pos_narrative, -1)
        self.assertNotEqual(pos_next_narrative, -1)
        self.assertNotEqual(pos_choices, -1)
        self.assertNotEqual(pos_poses, -1)
        self.assertNotEqual(pos_memory, -1)

        self.assertLess(pos_title, pos_narrative)
        self.assertLess(pos_narrative, pos_next_narrative)
        self.assertLess(pos_next_narrative, pos_choices)
        self.assertLess(pos_choices, pos_poses)
        self.assertLess(pos_poses, pos_memory)
        self.assertNotIn('"next_choices"', game_engine.COMBAT_OUTCOME_SCHEMA)

    def test_llm_client_timeout_override(self):
        """call_llm_json respects custom timeout parameter."""
        async def run_test():
            with patch("llm_client.get_candidate_models") as mock_candidates:
                mock_client = MagicMock()
                mock_create = AsyncMock()
                mock_resp = MagicMock()
                mock_choice = MagicMock()
                mock_choice.message.content = '{"status": "ok"}'
                mock_resp.choices = [mock_choice]
                mock_create.return_value = mock_resp
                mock_client.chat.completions.create = mock_create
                mock_candidates.return_value = [(mock_client, "gpt-4o-mini")]

                result = await llm_client.call_llm_json(
                    "System prompt", "User prompt", timeout=12.5
                )
                self.assertEqual(result, {"status": "ok"})
                mock_create.assert_called_once()
                _, kwargs = mock_create.call_args
                self.assertEqual(kwargs.get("timeout"), 12.5)

        asyncio.run(run_test())

    def test_pre_turn_vitals_deterministic_resolution(self):
        """Pre-turn vitals engine resolves gold spending, hazard HP, and loot deterministically."""
        from game_engine.state.core import resolve_pre_turn_vitals_and_resources

        actions = [
            {
                "char": self.party[0][0],
                "label": "Pay 25 gold to bribe the gatekeeper",
                "gold_spent": 25,
                "check": CheckResult(chance=80, roll=20.0, tier="success", tier_label="Success", succeeded=True),
            }
        ]
        res = resolve_pre_turn_vitals_and_resources(self.session, self.party, actions)
        self.assertIn("character_outcomes", res)
        self.assertEqual(len(res["character_outcomes"]), 1)
        self.assertEqual(res["character_outcomes"][0]["gold_change"], -25)

    def test_pre_turn_social_deterministic_resolution(self):
        """Pre-turn social engine resolves affinity deltas and canonical disclosures before LLM."""
        from game_engine.state.social import resolve_pre_turn_social_and_disclosures
        import db

        db.upsert_contact(
            session_id=101,
            character_id=1001,
            npc_id="lady_seraphina",
            name="Lady Seraphina",
            appearance={"sensitive_spots": "nape of her neck", "sensitive_spots_revealed": False},
        )

        actions = [
            {
                "char": self.party[0][0],
                "label": "Gently inquire about Lady Seraphina's sensitive spots",
                "check": CheckResult(chance=75, roll=15.0, tier="success", tier_label="Success", succeeded=True),
            }
        ]
        res = resolve_pre_turn_social_and_disclosures(
            self.session, self.party, actions, new_dialogue_partners=["Lady Seraphina"]
        )
        self.assertIn("directives", res)
        self.assertTrue(any("CANONICAL DISCLOSURE" in d for d in res["directives"]))
        self.assertIn("Lady Seraphina", res.get("affinity_deltas", {}))

    def test_pre_turn_quest_dual_trigger_resolution(self):
        """Pre-turn quest engine advances waypoints and detects completions before LLM."""
        from game_engine.quests import resolve_pre_turn_quests_and_clues
        import db

        db.upsert_quest(
            session_id=101,
            quest_id="quest_test_01",
            quest_type="main",
            title="Inspect the Courtyard",
            objective="Inspect the ancient fountain",
            status="Active",
            is_story_quest=1,
        )
        db.save_quest_waypoints(
            session_id=101,
            quest_id="quest_test_01",
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Reach the Fountain",
                    "target_location": "Sunfall Citadel ➔ High Courtyard ➔ Fount",
                    "completion_trigger": "arrival",
                    "status": "active",
                }
            ],
            sub_obj_id=None,
        )

        actions = [
            {
                "char": self.party[0][0],
                "label": "Look around the fountain",
                "check": CheckResult(chance=90, roll=10.0, tier="success", tier_label="Success", succeeded=True),
            }
        ]
        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions)
        self.assertIn("completed_quests", res)
        self.assertIn("quest_test_01", res["completed_quests"])

    def test_resolve_turn_single_llm_call_zero_arbiters(self):
        """resolve_turn makes exactly 1 LLM call with 0 arbiter LLM calls."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Greet Lady Seraphina with a polite bow",
                "stat": "CHA",
                "check": CheckResult(chance=85, roll=25.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0,
            }
        ]

        llm_mock_response = {
            "scene_title": "Courtyard Pleasantry",
            "entity_audit": {
                "present_named_characters": ["Lady Seraphina"],
                "speaking_characters": ["Lady Seraphina"],
                "departed_characters": [],
            },
            "npcs_present": [{"name": "Lady Seraphina"}],
            "location": "Sunfall Citadel ➔ High Courtyard ➔ Fount",
            "outcome_narrative": "Aric bows courtly before Lady Seraphina. She smiles in appreciation.",
            "next_narrative": "The waters of the marble fountain burble softly behind her.",
            "next_choices": [
                {"label": "Ask about the Citadel rumors", "stat": "CHA", "requirement": 4, "mp_cost": 0}
            ],
            "character_outcomes": [],
            "relationship_updates": [],
        }

        async def run_test():
            with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_mock_response

                result = await game_engine.resolve_turn(self.session, self.party, actions)

                # Exactly 1 LLM call for single-pass narration
                self.assertEqual(mock_llm.call_count, 1)

                # Deterministic pre-turn engines ran and attached their results
                self.assertIn("_pre_turn_vitals", result)
                self.assertIn("_pre_turn_social", result)
                self.assertIn("_pre_turn_quests", result)

                # Outcome narrative is present
                self.assertIn("Aric bows", result.get("outcome_narrative", ""))

        asyncio.run(run_test())

    def test_resolve_turn_merges_pre_turn_deterministic_outcomes(self):
        """resolve_turn merges precomputed deterministic vitals, affinity, and quest updates into result."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Pay 15 gold to consult Lady Seraphina",
                "gold_spent": 15,
                "check": CheckResult(chance=80, roll=10.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0,
            }
        ]

        llm_mock_response = {
            "scene_title": "Consulation",
            "outcome_narrative": "Aric hands over the coin and begins the inquiry.",
            "next_narrative": "Seraphina nods thoughtfully.",
            "next_choices": [{"label": "Continue", "stat": "NONE", "requirement": 0, "mp_cost": 0}],
            "character_outcomes": [],
            "relationship_updates": [],
        }

        async def run_test():
            with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = llm_mock_response

                result = await game_engine.resolve_turn(self.session, self.party, actions)

                # Character outcomes merged from pre-turn vitals
                self.assertTrue(len(result.get("character_outcomes", [])) >= 1)
                co = result["character_outcomes"][0]
                self.assertEqual(co["name"], "Aric")
                self.assertEqual(co["gold_change"], -15)

                # Affinity merged from pre-turn social
                self.assertTrue(len(result.get("relationship_updates", [])) >= 1)
                ru_names = [ru["npc_name"] for ru in result["relationship_updates"]]
                self.assertIn("Lady Seraphina", ru_names)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
