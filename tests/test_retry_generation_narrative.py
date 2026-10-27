from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import db
import db.core
import game_engine
from cogs.adventure import AdventureCog


class TestRetryGenerationNarrative(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        test_db = os.path.join(self._tmp_dir.name, "test_retry_narrative.db")
        db.DB_PATH = test_db
        db.core.DB_PATH = test_db
        db.init_db()
        self.user_id = 9991234

        db.create_character(user_id=self.user_id, name="Artemiusz", char_class="Warrior", gender="male", race="human")
        self.session_id = db.create_session(
            host_user_id=self.user_id,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="natural",
            image_gen_enabled=False,
            channel_id=12345,
            scenario="nsfw_furry_high_school_drama"
        )

        self.bot = MagicMock()
        self.cog = AdventureCog(self.bot)

    def tearDown(self):
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

    async def test_handle_retry_embeds_action_outcome_in_main_scene(self):
        db.save_session_scene(
            self.session_id,
            scene_title="The Cheetah's Challenge",
            narrative="The atmosphere settles around Campus Promenade...",
            choices=[{"label": "Proceed", "is_fallback": True}],
            history=["[SUCCESS] Artemiusz: Lean back and enjoy her efforts in silence. -> Artemiusz acts with deliberate intent: Lean back and enjoy her efforts in silence."]
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = self.user_id
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.followup.edit_message = AsyncMock()
        interaction.message = MagicMock(spec=discord.Message)

        self.cog._last_picks[self.session_id] = (
            self.user_id,
            {"direct_choice": {"label": "Lean back and enjoy her efforts in silence.", "stat": "NONE", "requirement": 0, "mp_cost": 0}}
        )

        mock_outcome = {
            "outcome_narrative": "Artemiusz leans back against the stone railing, watching Rachel with a subtle smirk as her cheetah tail swishes with delight.",
            "next_narrative": "The cool evening breeze sweeps across the terrace as Rachel pauses, catching her breath with a soft chuckle.",
            "scene_title": "The Cheetah's Challenge",
            "choices": [{"label": "Tease her softly", "stat": "CHA", "requirement": 0, "mp_cost": 0}],
            "location": "Old Garden Terrace"
        }

        from services.turn_service import TurnResponse, TurnService
        mock_response = TurnResponse(
            success=True,
            session={"history": []},
            outcome=mock_outcome,
            action={"char": {"name": "Artemiusz"}, "stat": "CHA", "check": {"chance": 100, "tier_label": "Success", "tier": "success"}},
            items_gained_by_user={},
            xp_gained=0,
            levels_gained=[],
            new_char={}
        )

        with patch.object(TurnService, "retry_narration", new=AsyncMock(return_value=mock_response)):
            with patch("discord.ui.View.from_message") as mock_view_from_msg:
                mock_old_view = MagicMock()
                mock_btn = MagicMock()
                mock_old_view.children = [mock_btn]
                mock_view_from_msg.return_value = mock_old_view

                await self.cog.handle_retry(interaction, self.session_id)

                self.assertEqual(interaction.followup.send.call_count, 2)

                outcome_kwargs = interaction.followup.send.call_args_list[0][1]
                outcome_embeds = outcome_kwargs.get("embeds", [])
                self.assertTrue(len(outcome_embeds) >= 1)
                self.assertIn("Artemiusz leans back against the stone railing", outcome_embeds[0].description)

                next_kwargs = interaction.followup.send.call_args_list[1][1]
                next_embeds = next_kwargs.get("embeds", [])
                self.assertTrue(len(next_embeds) >= 1)
                self.assertIn("The cool evening breeze sweeps across the terrace", next_embeds[0].description)

    async def test_handle_retry_does_not_embed_fallback_placeholder(self):
        db.save_session_scene(
            self.session_id,
            scene_title="Fallback Scene",
            narrative="The atmosphere settles around...",
            choices=[{"label": "Proceed", "is_fallback": True}],
            history=["[SUCCESS] Artemiusz: Acts -> Artemiusz acts with deliberate intent: Acts."]
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = self.user_id
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.followup.edit_message = AsyncMock()
        interaction.message = None

        self.cog._last_picks[self.session_id] = (
            self.user_id,
            {"direct_choice": {"label": "Acts", "stat": "NONE", "requirement": 0, "mp_cost": 0}}
        )

        mock_fallback_outcome = {
            "outcome_narrative": "Artemiusz acts with deliberate intent: Acts.",
            "_is_fallback_narrative": True,
            "next_narrative": "The atmosphere settles around the area as the immediate action resolves.",
            "scene_title": "Fallback Scene",
            "choices": [{"label": "Proceed", "is_fallback": True}]
        }

        from services.turn_service import TurnResponse, TurnService
        mock_response = TurnResponse(
            success=True,
            session={"history": [{"type": "action", "outcome_narrative": "Artemiusz acts with deliberate intent: Acts."}]},
            outcome=mock_fallback_outcome,
            action={"char": {"name": "Artemiusz"}, "stat": "NONE", "check": {"chance": 100, "tier_label": "Success", "tier": "success"}},
            items_gained_by_user={},
            xp_gained=0,
            levels_gained=[],
            new_char={}
        )

        with patch.object(TurnService, "retry_narration", new=AsyncMock(return_value=mock_response)):
            await self.cog.handle_retry(interaction, self.session_id)

            send_kwargs = interaction.followup.send.call_args[1]
            embeds = send_kwargs.get("embeds", [])
            story_embed = embeds[0]

            self.assertNotIn("**🎯 Action Outcome:**", story_embed.description)
            self.assertEqual(story_embed.description, "The atmosphere settles around the area as the immediate action resolves.")

    async def test_run_narration_pass_end_to_end_batch_and_stream(self):
        from game_engine.turn.narration import run_narration_pass
        from models.llm_schemas import NarrationOutcome, DeterministicTurnNarration

        session = db.get_session(self.session_id)
        snapshot = {
            "status": "completed",
            "actions": [{"label": "Survey surroundings", "check": {"tier_label": "Critical Success"}}],
            "applied": {
                "location": "Old Garden Terrace",
                "character_outcomes": [{"name": "Artemiusz", "hp_change": 0, "mp_change": 0, "status_effects_gained": []}],
                "npcs_present": [{"name": "Rachel"}],
                "nearby_enemies": [],
                "items_gained": {},
                "xp_gained": {},
            }
        }

        mock_llm_result = {
            "outcome_narrative": "You survey the moonlit garden in calm silence.",
            "next_narrative": "The stone fountain trickles quietly nearby.",
            "scene_title": "Garden Stillness",
            "next_choices": [{"label": "Step closer to the fountain"}]
        }

        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_llm_result)) as mock_call:
            res = await run_narration_pass(session, snapshot, attempt=1)
            self.assertEqual(res["outcome_narrative"], "You survey the moonlit garden in calm silence.")
            self.assertEqual(res["scene_title"], "Garden Stillness")
            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args[1]
            self.assertIn(call_kwargs["response_model"], (DeterministicTurnNarration, NarrationOutcome))
            self.assertTrue(call_kwargs["is_nsfw"])

        stream_cb = AsyncMock()
        with patch("game_engine.turn.narration.call_llm_json_stream", new=AsyncMock(return_value=mock_llm_result)) as mock_stream_call:
            res_stream = await run_narration_pass(session, snapshot, attempt=2, stream_callback=stream_cb)
            self.assertEqual(res_stream["outcome_narrative"], "You survey the moonlit garden in calm silence.")
            mock_stream_call.assert_called_once()
            call_kwargs = mock_stream_call.call_args[1]
            self.assertEqual(call_kwargs["on_narrative_token"], stream_cb)
            self.assertGreater(call_kwargs["temperature"], 0.7)

    async def test_turn_service_retry_narration_real_pipeline(self):
        from services.turn_service import TurnService

        snapshot = {
            "status": "completed",
            "retry_attempts": 0,
            "actions": [{"label": "Greet the student", "check": {"tier_label": "Success"}}],
            "applied": {
                "location": "Classroom 2-B",
                "character_outcomes": [],
                "npcs_present": [],
                "nearby_enemies": [],
                "items_gained": {},
                "xp_gained": {}
            }
        }
        db.set_turn_snapshot(self.session_id, snapshot)
        db.save_session_scene(
            self.session_id,
            scene_title="Old Scene",
            narrative="Old narrative",
            choices=[{"label": "Choice 1"}],
            history=[{"type": "action", "outcome_narrative": "Old outcome"}]
        )

        mock_llm_result = {
            "outcome_narrative": "You offer a warm smile to the classmate beside you.",
            "next_narrative": "The morning sun filters warmly through the classroom windows.",
            "scene_title": "Morning Greetings",
            "next_choices": [{"label": "Take your seat"}]
        }

        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_llm_result)):
            turn_response = await TurnService.retry_narration(self.session_id, self.user_id)
            self.assertTrue(turn_response.success)
            self.assertEqual(turn_response.outcome["outcome_narrative"], "You offer a warm smile to the classmate beside you.")
            self.assertEqual(turn_response.outcome["scene_title"], "Morning Greetings")

            updated_snap = db.get_turn_snapshot(self.session_id)
            self.assertEqual(updated_snap["retry_attempts"], 1)

            fresh_session = db.get_session(self.session_id)
            last_hist = fresh_session["history"][-1]
            self.assertEqual(last_hist["outcome_narrative"], "You offer a warm smile to the classmate beside you.")

    async def test_retry_narration_preserves_frozen_location_when_llm_hallucinates_location_dict(self):
        from services.turn_service import TurnService

        frozen_loc = "Sakuragaoka Academy ➔ Class 2-B (Homeroom) ➔ Artemiusz's Desk"
        snapshot = {
            "status": "completed",
            "retry_attempts": 0,
            "actions": [{"label": "Look around", "check": {"tier_label": "Success"}}],
            "applied": {
                "location": frozen_loc,
                "character_outcomes": [],
                "npcs_present": [],
                "nearby_enemies": [],
                "items_gained": {},
                "xp_gained": {}
            }
        }
        db.set_turn_snapshot(self.session_id, snapshot)
        db.save_session_scene(
            self.session_id,
            scene_title="Classroom Desk",
            narrative="Current scene",
            choices=[{"label": "Choice 1"}],
            history=[{"type": "action", "outcome_narrative": "Previous action"}],
            location=frozen_loc
        )

        hallucinated_loc_dict = {
            "Tier1_Zone_Biome": "Sakuragaoka Academy",
            "Tier2_Physical_Place_Structure_Building_City_Desk": ["Class 2-B (Homeroom)"],
            "Tier3_Location_Zone_Location_Name": ["Artemiusz's Desk"]
        }
        mock_llm_result = {
            "outcome_narrative": "You look around your desk quietly.",
            "next_narrative": "The morning sun shines through the window.",
            "scene_title": "Morning Desk",
            "next_choices": [{"label": "Review notes"}],
            "location": hallucinated_loc_dict
        }

        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_llm_result)):
            turn_response = await TurnService.retry_narration(self.session_id, self.user_id)
            self.assertTrue(turn_response.success)
            self.assertEqual(turn_response.outcome["location"], frozen_loc)

    def test_parse_tiered_location_handles_structured_json_dict(self):
        from mechanics.world.locations.hierarchy import parse_tiered_location
        from cogs.adventure.embeds import _location_text

        raw_dict = {
            "Tier1_Zone_Biome": "Sakuragaoka Academy",
            "Tier2_Physical_Place_Structure_Building_City_Desk": ["Class 2-B (Homeroom)"],
            "Tier3_Location_Zone_Location_Name": ["Artemiusz's Desk"]
        }
        z, p, s = parse_tiered_location(raw_dict, scenario_key="nsfw_furry_high_school_drama")
        self.assertEqual(z, "Sakuragaoka Academy")
        self.assertEqual(p, "Class 2-B (Homeroom)")
        self.assertEqual(s, "Artemiusz's Desk")

        raw_json_str = json.dumps(raw_dict)
        z2, p2, s2 = parse_tiered_location(raw_json_str, scenario_key="nsfw_furry_high_school_drama")
        self.assertEqual(z2, "Sakuragaoka Academy")
        self.assertEqual(p2, "Class 2-B (Homeroom)")
        self.assertEqual(s2, "Artemiusz's Desk")

        mock_sess = {"current_location": raw_json_str, "scenario": "nsfw_furry_high_school_drama"}
        loc_display = _location_text(mock_sess, char_name="Artemiusz")
        self.assertNotIn("{", loc_display)
        self.assertIn("Sakuragaoka Academy ➔ Class 2-B (Homeroom) ➔ Artemiusz's Desk", loc_display)

    async def test_retry_clears_stale_fallback_text_when_outcome_narrative_is_empty(self):
        from services.turn_service import TurnService
        fallback_history_entry = {
            "type": "action",
            "label": "Observe your surroundings and inspect those present",
            "outcome_narrative": "You acts with deliberate intent: Observe your surroundings and inspect those present.",
            "narrative": "You acts with deliberate intent: Observe your surroundings and inspect those present.",
            "next_narrative": "Old scene text.",
            "is_fallback": True
        }
        db.save_session_scene(
            self.session_id,
            scene_title="Observation",
            narrative="Old scene text.",
            choices=[{"label": "Next"}],
            history=[fallback_history_entry]
        )
        db.set_turn_snapshot(self.session_id, {
            "status": "completed",
            "retry_attempts": 0,
            "actions": [{"user_id": self.user_id, "label": "Observe surroundings"}],
            "applied": {}
        })

        mock_retry_result = {
            "outcome_narrative": "",
            "next_narrative": "The main hallway opens into a wide, sun-drenched corridor...",
            "scene_title": "Hallway Briefing",
            "next_choices": [{"label": "Talk to Yuki"}]
        }
        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_retry_result)):
            turn_response = await TurnService.retry_narration(self.session_id, self.user_id)
            self.assertTrue(turn_response.success)

            s = db.get_session(self.session_id)
            updated_entry = s["history"][-1]
            self.assertEqual(updated_entry["outcome_narrative"], "")
            self.assertIn("The main hallway opens into a wide", updated_entry["next_narrative"])
            self.assertFalse(updated_entry.get("is_fallback", False))

    def test_enrich_session_detects_deliberate_intent_in_history(self):
        from api.adventure import _enrich_session_for_client
        mock_session = {
            "id": self.session_id,
            "current_day": 1,
            "current_minute": 500,
            "narrative": "The corridor is quiet.",
            "choices": [{"label": "Walk ahead"}],
            "history": [{
                "type": "action",
                "outcome_narrative": "You acts with deliberate intent: Observe your surroundings.",
                "next_narrative": "The corridor is quiet."
            }]
        }
        enriched = _enrich_session_for_client(mock_session, self.user_id)
        self.assertTrue(enriched["is_fallback_generation"])

    def test_enrich_session_no_false_positive_fallback_on_deterministic_supplement_or_outcome_only(self):
        """Verify healthy LLM turns with deterministic Band-1/2 supplemented choices or single-paragraph
        outcome_narrative do NOT trigger the false-positive Fallback scene generation banner."""
        from api.adventure import _enrich_session_for_client

        # Case A: Healthy LLM turn supplemented by deterministic conversation choices
        healthy_supplemented = {
            "id": self.session_id,
            "current_day": 1,
            "current_minute": 510,
            "narrative": "Putri adjusts her field tablet and smiles politely.",
            "choices": [
                {"label": "Ask Putri Wijaya about her work as Junior Operative", "stat": "INT", "requirement": 6, "_deterministic_supplement": True, "is_fallback": False},
                {"label": "Leave conversation with Putri Wijaya", "stat": "NONE", "requirement": 0, "_pinned_dialogue_exit": True},
            ],
            "history": [{
                "type": "turn",
                "outcome_narrative": "You ask Putri how containment patrols have been going.",
                "next_narrative": "Putri adjusts her field tablet and smiles politely.",
                "is_fallback": False,
            }],
        }
        enriched_a = _enrich_session_for_client(healthy_supplemented, self.user_id)
        self.assertFalse(enriched_a["is_fallback_generation"])

        # Case B: Healthy LLM turn where full prose was placed into outcome_narrative with empty next_narrative
        healthy_outcome_only = {
            "id": self.session_id,
            "current_day": 1,
            "current_minute": 515,
            "narrative": "",
            "choices": [{"label": "Continue talking", "stat": "CHA", "requirement": 6}],
            "history": [{
                "type": "turn",
                "outcome_narrative": "Putri leans against the railing and explains the S.O.A.I. containment protocols in crisp detail.",
                "next_narrative": "",
                "is_fallback": False,
            }],
        }
        enriched_b = _enrich_session_for_client(healthy_outcome_only, self.user_id)
        self.assertFalse(enriched_b["is_fallback_generation"])

    def test_observation_and_subject_verb_agreement_fallbacks(self):
        from game_engine.keywords import sanitize_narrative_context_echo
        echoed_prose = "The hallway is completely silent as the heavy rain continues pouring outside against the glass windows."
        session_prev = {"narrative": echoed_prose}

        echo_res_you = sanitize_narrative_context_echo(echoed_prose, session_prev, action_label="Open the door", character_name="You")
        self.assertEqual(echo_res_you, "You act with deliberate intent: Open the door.")

        echo_res_npc = sanitize_narrative_context_echo(echoed_prose, session_prev, action_label="Open the door", character_name="Leon")
        self.assertEqual(echo_res_npc, "Leon acts with deliberate intent: Open the door.")

    async def test_run_narration_pass_sanitizes_echo_and_absent_npcs_without_name_error(self):
        from game_engine.turn.narration import run_narration_pass
        snapshot = {
            "status": "completed",
            "retry_attempts": 0,
            "actions": [{"user_id": self.user_id, "label": "Talk to Mia", "char": {"name": "Artemiusz"}}],
            "applied": {
                "location": "Old East Wing Music Room",
                "npcs_present": [{"name": "Mia Yamada"}],
            }
        }
        mock_result = {
            "outcome_narrative": "You lean in and whisper to Mia playfully.",
            "next_narrative": "Mia smiles, her tiger ears twitching in amusement.",
            "scene_title": "Music Room Whisper",
            "next_choices": [{"label": "Continue whispering", "stat": "CHA", "requirement": 6}]
        }
        session = db.get_session(self.session_id)
        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_result)):
            out = await run_narration_pass(session, snapshot)
            self.assertIn("whisper to Mia", out["outcome_narrative"])
            self.assertIn("Mia smiles", out["next_narrative"])

    async def test_handle_retry_opening_scene_reinvokes_launch_opening_scene(self):
        db.save_session_scene(
            self.session_id,
            scene_title="Hikayat",
            narrative="",
            choices=[{"label": "Proceed", "is_fallback": True}],
            history=[]
        )

        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = self.user_id
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()

        with patch.object(self.cog, "launch_opening_scene", new=AsyncMock()) as mock_launch:
            await self.cog.handle_retry(interaction, self.session_id)
            mock_launch.assert_called_once()
            _, called_kwargs = mock_launch.call_args
            self.assertEqual(called_kwargs.get("use_followup"), True)

    async def test_generate_opening_scene_empty_narrative_generates_contextual_fallback(self):
        from game_engine.turn.generation import generate_opening_scene
        session = db.get_session(self.session_id)
        char = db.get_character(self.user_id)
        party = [(char, [])]

        empty_llm_result = {
            "narrative": "",
            "scene_title": "",
            "choices": [{"label": "Observe surroundings", "stat": "PER", "requirement": 5}],
            "location": "Student Commons ➔ Central Courtyard"
        }

        with patch("game_engine.turn.generation.game_engine.call_llm_json", new=AsyncMock(return_value=empty_llm_result)):
            scene = await generate_opening_scene(session, party)
            self.assertTrue(len(scene["narrative"]) > 0)
            self.assertTrue(scene.get("is_fallback"))
            self.assertIn("Central Courtyard", scene["narrative"])
            self.assertNotEqual(scene.get("scene_title"), "")


if __name__ == "__main__":
    unittest.main()
