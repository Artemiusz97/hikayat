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
        """Verify that OUTCOME_SCHEMA lists entity_audit and story narrative at the top."""
        schema = game_engine.OUTCOME_SCHEMA
        pos_audit = schema.find('"entity_audit"')
        pos_narrative = schema.find('"outcome_narrative"')
        pos_next_narrative = schema.find('"next_narrative"')
        pos_choices = schema.find('"next_choices"')

        self.assertNotEqual(pos_audit, -1)
        self.assertNotEqual(pos_narrative, -1)
        self.assertNotEqual(pos_next_narrative, -1)
        self.assertNotEqual(pos_choices, -1)

        # entity_audit must precede narrative prose, and narrative must precede choices
        self.assertLess(pos_audit, pos_narrative, "entity_audit should precede outcome_narrative")
        self.assertLess(pos_narrative, pos_next_narrative, "outcome_narrative should precede next_narrative")
        self.assertLess(pos_next_narrative, pos_choices, "next_narrative should precede next_choices")

    def test_gate_routine_turn_returns_false(self):
        """Standard actions with success/ordinary checks bypass Pass 1 (fast 1-pass path)."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Inspect the ancient fountain carvings",
                "stat": "PER",
                "check": CheckResult(chance=75, roll=30.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0
            }
        ]
        should_trigger = game_engine.should_trigger_state_arbiter_pass(self.session, actions, self.party)
        self.assertFalse(should_trigger)

    def test_gate_crit_fail_triggers_pass1(self):
        """Critical failures require the State Arbiter Pass to enforce fail-forward consequences."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Attempt to pick the sealed archive lock",
                "stat": "AGI",
                "check": CheckResult(chance=40, roll=98.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False),
                "mp_spent": 0
            }
        ]
        should_trigger = game_engine.should_trigger_state_arbiter_pass(self.session, actions, self.party)
        self.assertTrue(should_trigger)

    def test_gate_multi_npc_room_triggers_pass1(self):
        """Rooms with 3+ NPCs trigger Pass 1 to prevent entity drift and hallucinations."""
        self.session["current_npcs"] = [
            {"name": "Elder Rowan"},
            {"name": "Captain Vance"},
            {"name": "Scholar Mira"}
        ]
        actions = [
            {
                "char": self.party[0][0],
                "label": "Greet the assembly",
                "stat": "CHA",
                "check": CheckResult(chance=80, roll=20.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0
            }
        ]
        should_trigger = game_engine.should_trigger_state_arbiter_pass(self.session, actions, self.party)
        self.assertTrue(should_trigger)

    def test_gate_dialogue_exit_triggers_pass1(self):
        """Conversational exits trigger Pass 1 to cleanly track departures."""
        self.session["dialogue_partners"] = ["Captain Vance"]
        actions = [
            {
                "char": self.party[0][0],
                "label": "Thank Captain Vance and step away to look around",
                "stat": "NONE",
                "check": CheckResult(chance=100, roll=0.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0
            }
        ]
        should_trigger = game_engine.should_trigger_state_arbiter_pass(self.session, actions, self.party)
        self.assertTrue(should_trigger)

    def test_gate_disabled_via_config(self):
        """When ENABLE_DYNAMIC_MULTIPASS is False, Pass 1 never triggers."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Climb the tower",
                "stat": "STR",
                "check": CheckResult(chance=30, roll=99.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False),
                "mp_spent": 0
            }
        ]
        with patch("game_engine.state.core.ENABLE_DYNAMIC_MULTIPASS", False):
            should_trigger = game_engine.should_trigger_state_arbiter_pass(self.session, actions, self.party)
            self.assertFalse(should_trigger)

    def test_execute_state_arbiter_pass_success(self):
        """Pass 1 executes with utility model and pass1 timeout, returning structured delta."""
        actions = [
            {
                "char": self.party[0][0],
                "label": "Bash the barred portcullis",
                "stat": "STR",
                "check": CheckResult(chance=30, roll=99.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False),
                "mp_spent": 0
            }
        ]
        mock_response = {
            "director_reasoning": "Aric shattered his shield against the gate, alerting two guard patrols.",
            "departed_characters": [],
            "present_characters": ["Guard Vance"],
            "speaking_characters": ["Guard Vance"],
            "character_outcomes": [
                {"name": "Aric", "hp_change": -8, "mp_change": 0, "gold_change": 0, "items_gained": [], "items_lost": ["Splintered Shield"], "status_effects": ["Exhausted"]}
            ],
            "quest_progress": {"completed_sub_quest_id": 0, "clue_discovered": ""},
            "fail_forward_complication": "Alarm horns sound across the courtyard; two sentries converge on the gate."
        }

        async def run_test():
            with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = mock_response
                result = await game_engine.execute_state_arbiter_pass(self.session, self.party, actions, "Aric bash")
                self.assertIsNotNone(result)
                self.assertEqual(result["director_reasoning"], mock_response["director_reasoning"])
                self.assertEqual(result["fail_forward_complication"], mock_response["fail_forward_complication"])
                
                # Check call parameters
                mock_call.assert_called_once()
                _, kwargs = mock_call.call_args
                self.assertTrue(kwargs.get("use_utility"))
                self.assertEqual(kwargs.get("timeout"), config.LLM_PASS1_TIMEOUT)
                self.assertEqual(kwargs.get("temperature"), 0.2)

        asyncio.run(run_test())

    def test_execute_state_arbiter_pass_timeout_graceful_fallback(self):
        """If Pass 1 times out or raises an error, it returns None cleanly without crashing."""
        actions = [{"char": self.party[0][0], "label": "Bash", "check": CheckResult(chance=30, roll=99.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False), "mp_spent": 0}]

        async def run_test():
            with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
                mock_call.side_effect = asyncio.TimeoutError("Pass 1 timeout reached")
                result = await game_engine.execute_state_arbiter_pass(self.session, self.party, actions, "Bash")
                # Must return None so turn can collapse to code fallback
                self.assertIsNone(result)

        asyncio.run(run_test())

    def test_resolve_turn_reconciles_pass1_departures_and_outcomes(self):
        """When Pass 1 marks an NPC departed, resolve_turn ensures they are pruned from npcs_present."""
        self.session["current_npcs"] = [{"name": "Merchant Silas"}, {"name": "Lady Seraphina"}]
        actions = [
            {
                "char": self.party[0][0],
                "label": "Bid farewell to Merchant Silas",
                "stat": "NONE",
                "check": CheckResult(chance=100, roll=0.0, tier="success", tier_label="Success", succeeded=True),
                "mp_spent": 0
            }
        ]
        self.session["dialogue_partners"] = ["Merchant Silas"]

        pass1_mock = {
            "director_reasoning": "Silas packed up his wagon and departed.",
            "departed_characters": ["Merchant Silas"],
            "present_characters": ["Lady Seraphina"],
            "speaking_characters": ["Merchant Silas"],
            "character_outcomes": [
                {"name": "Aric", "hp_change": 0, "mp_change": 0, "gold_change": 0, "items_gained": [], "items_lost": [], "status_effects": []}
            ],
            "quest_progress": {"completed_sub_quest_id": 0, "clue_discovered": ""},
            "fail_forward_complication": ""
        }

        # Pass 2 returns full scene, but mistakenly still included Silas in npcs_present
        pass2_mock = {
            "scene_title": "Parting of Ways",
            "entity_audit": {
                "present_named_characters": ["Lady Seraphina", "Merchant Silas"],
                "speaking_characters": ["Merchant Silas"],
                "departed_characters": ["Merchant Silas"]
            },
            "npcs_present": [{"name": "Lady Seraphina"}, {"name": "Merchant Silas"}],
            "npc_departures": [],
            "character_outcomes": [],
            "location": "Sunfall Citadel ➔ High Courtyard ➔ Fount",
            "outcome_narrative": "Silas tips his hat and rolls away with his cart.",
            "next_narrative": "Lady Seraphina remains by the fountain, watching the gate.",
            "next_choices": [
                {"label": "Speak with Seraphina", "stat": "CHA", "requirement": 4, "mp_cost": 0}
            ]
        }

        async def run_test():
            with patch("game_engine.execute_state_arbiter_pass", new_callable=AsyncMock) as mock_p1, \
                 patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_p2:
                mock_p1.return_value = pass1_mock
                mock_p2.return_value = pass2_mock

                result = await game_engine.resolve_turn(self.session, self.party, actions)

                # Silas should be in npc_departures
                self.assertIn("Merchant Silas", result.get("npc_departures", []))
                # Silas MUST be pruned from npcs_present because Pass 1 marked him departed!
                present_names = [n["name"] for n in result.get("npcs_present", [])]
                self.assertNotIn("Merchant Silas", present_names)
                self.assertIn("Lady Seraphina", present_names)

                # Character outcomes backfilled from Pass 1
                self.assertEqual(len(result.get("character_outcomes", [])), 1)
                self.assertEqual(result["character_outcomes"][0]["name"], "Aric")

        asyncio.run(run_test())

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

    def test_gate_social_arbiter_pass_triggers(self):
        """Verify should_trigger_social_arbiter_pass activates on social and quest cues."""
        from game_engine.state.core import should_trigger_social_arbiter_pass

        # 1. Active NPCs present
        p2_res = {"npcs_present": [{"name": "Guard Vance"}]}
        self.assertTrue(should_trigger_social_arbiter_pass({"current_npcs": []}, [], self.party, p2_res))

        # 2. Conversational action intent
        actions = [{"label": "Talk to the silent stranger in the corner"}]
        self.assertTrue(should_trigger_social_arbiter_pass({"current_npcs": []}, actions, self.party, {}))

        # 3. Active quests present
        self.assertTrue(should_trigger_social_arbiter_pass({"story_quests": [{"id": "SQ-1"}]}, [], self.party, {}))

        # 4. Routine non-social solo turn without NPCs or quests
        self.assertFalse(should_trigger_social_arbiter_pass({"current_npcs": []}, [{"label": "Examine the stone wall"}], self.party, {}))

    def test_resolve_turn_merges_pass1_and_pass3_memories(self):
        """Pass 1 and Pass 3 memories are merged rather than clobbering each other."""
        pass1_mock = {
            "director_reasoning": "Aric picked the lock under Vance's watchful gaze.",
            "character_outcomes": [],
            "npc_memories": [{"npc_name": "Guard Vance", "memory": "Saw Aric tamper with the lock"}],
        }
        pass2_mock = {
            "scene_title": "Courtyard Exchange",
            "npcs_present": [{"name": "Guard Vance"}, {"name": "Lady Seraphina"}],
            "outcome_narrative": "Aric chats politely with Lady Seraphina.",
            "next_narrative": "The guards maintain their patrol.",
            "next_choices": [{"label": "Leave the courtyard", "stat": "NONE", "requirement": 0, "mp_cost": 0}],
        }
        pass3_mock = {
            "relationship_updates": [{"npc_name": "Lady Seraphina", "delta_score": 3}],
            "npc_memories": [{"npc_name": "Lady Seraphina", "memory": "Impressed by Aric's courtly manners"}],
        }

        async def run_test():
            with patch("game_engine.execute_state_arbiter_pass", new_callable=AsyncMock) as mock_p1, \
                 patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_p2, \
                 patch("game_engine.state.core.execute_social_arbiter_pass", new_callable=AsyncMock) as mock_p3:
                mock_p1.return_value = pass1_mock
                mock_p2.return_value = pass2_mock
                mock_p3.return_value = pass3_mock

                # Crit fail triggers Pass 1 State Arbiter
                actions = [{
                    "char": self.party[0][0],
                    "label": "Attempt to pick the courtyard gate lock",
                    "stat": "AGI",
                    "check": CheckResult(chance=40, roll=95.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False),
                    "mp_spent": 0
                }]
                result = await game_engine.resolve_turn(self.session, self.party, actions)

                # Both Pass 3 and Pass 1 memories must be present!
                mems = result.get("npc_memories", [])
                self.assertEqual(len(mems), 2)
                mem_npcs = [m["npc_name"] for m in mems]
                self.assertIn("Guard Vance", mem_npcs)
                self.assertIn("Lady Seraphina", mem_npcs)

        asyncio.run(run_test())

    def test_resolve_turn_preserves_pass1_clue_when_pass3_omits_quest_updates(self):
        """If Pass 1 finds a clue but Pass 3 generates no quest_updates, clue is preserved."""
        pass1_mock = {
            "director_reasoning": "Aric found a hidden clue during the milestone inspection.",
            "quest_progress": {"clue_discovered": "A hidden raven insignia stamped into the stone."},
            "character_outcomes": [],
        }
        pass2_mock = {
            "scene_title": "Courtyard Clue",
            "npcs_present": [{"name": "Guard Vance"}],
            "outcome_narrative": "Aric uncovers the hidden sigil.",
            "next_narrative": "The courtyard falls quiet.",
            "next_choices": [{"label": "Inspect closer", "stat": "PER", "requirement": 4, "mp_cost": 0}],
        }
        pass3_mock = {
            "relationship_updates": [],
            "quest_updates": [],  # Pass 3 omitted quest updates
        }

        async def run_test():
            with patch("game_engine.execute_state_arbiter_pass", new_callable=AsyncMock) as mock_p1, \
                 patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_p2, \
                 patch("game_engine.state.core.execute_social_arbiter_pass", new_callable=AsyncMock) as mock_p3:
                mock_p1.return_value = pass1_mock
                mock_p2.return_value = pass2_mock
                mock_p3.return_value = pass3_mock

                self.session["pending_story_milestone"] = True
                actions = [{
                    "char": self.party[0][0],
                    "label": "Search for clues",
                    "stat": "PER",
                    "check": CheckResult(chance=80, roll=10.0, tier="success", tier_label="Success", succeeded=True),
                    "mp_spent": 0
                }]
                result = await game_engine.resolve_turn(self.session, self.party, actions)

                # Clue must be synthesized and preserved
                qu_list = result.get("quest_updates", [])
                self.assertTrue(len(qu_list) >= 1)
                self.assertEqual(qu_list[0]["current_clues"], "A hidden raven insignia stamped into the stone.")

        asyncio.run(run_test())

    def test_execute_social_arbiter_pass_timeout_graceful_fallback(self):
        """If Pass 3 times out or raises an error, it returns None cleanly."""
        from game_engine.state.core import execute_social_arbiter_pass

        async def run_test():
            with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
                mock_call.side_effect = asyncio.TimeoutError("Pass 3 timeout")
                result = await execute_social_arbiter_pass(self.session, self.party, [], "Actions", {"outcome_narrative": "Story"})
                self.assertIsNone(result)

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
