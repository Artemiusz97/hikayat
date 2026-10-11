import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import db
import game_engine
from cogs.adventure import AdventureCog

class TestRetryGenerationNarrative(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 9991234
        self.session_id = 7771234

        # Clean DB
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))

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

    async def test_handle_retry_embeds_action_outcome_in_main_scene(self):
        # Setup session in fallback state
        db.save_session_scene(
            self.session_id,
            scene_title="The Cheetah's Challenge",
            narrative="The atmosphere settles around Campus Promenade...",
            choices=[{"label": "Proceed", "is_fallback": True}],
            history=["[SUCCESS] Artemiusz: Lean back and enjoy her efforts in silence. -> Artemiusz acts with deliberate intent: Lean back and enjoy her efforts in silence."]
        )

        # Mock interaction
        interaction = MagicMock(spec=discord.Interaction)
        interaction.user.id = self.user_id
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        interaction.followup.edit_message = AsyncMock()
        interaction.message = MagicMock(spec=discord.Message)

        # Mock last pick info
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

                # Verify interaction.followup.send was called
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

            # Should NOT prepend "🎯 Action Outcome:" when the outcome is a fallback placeholder
            self.assertNotIn("**🎯 Action Outcome:**", story_embed.description)
            self.assertEqual(story_embed.description, "The atmosphere settles around the area as the immediate action resolves.")

    async def test_run_narration_pass_end_to_end_batch_and_stream(self):
        """Verify that game_engine.turn.narration.run_narration_pass executes without import errors
        and correctly invokes call_llm_json and call_llm_json_stream."""
        from game_engine.turn.narration import run_narration_pass
        from models.llm_schemas import NarrationOutcome

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

        # 1. Test batch execution
        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_llm_result)) as mock_call:
            res = await run_narration_pass(session, snapshot, attempt=1)
            self.assertEqual(res["outcome_narrative"], "You survey the moonlit garden in calm silence.")
            self.assertEqual(res["scene_title"], "Garden Stillness")
            mock_call.assert_called_once()
            call_kwargs = mock_call.call_args[1]
            self.assertEqual(call_kwargs["response_model"], NarrationOutcome)
            self.assertTrue(call_kwargs["is_nsfw"])

        # 2. Test stream execution
        stream_cb = AsyncMock()
        with patch("game_engine.turn.narration.call_llm_json_stream", new=AsyncMock(return_value=mock_llm_result)) as mock_stream_call:
            res_stream = await run_narration_pass(session, snapshot, attempt=2, stream_callback=stream_cb)
            self.assertEqual(res_stream["outcome_narrative"], "You survey the moonlit garden in calm silence.")
            mock_stream_call.assert_called_once()
            call_kwargs = mock_stream_call.call_args[1]
            self.assertEqual(call_kwargs["on_narrative_token"], stream_cb)
            self.assertGreater(call_kwargs["temperature"], 0.7)  # Bumped on attempt 2

    async def test_turn_service_retry_narration_real_pipeline(self):
        """Verify TurnService.retry_narration end-to-end pipeline without mocking retry_narration itself."""
        from services.turn_service import TurnService

        # Seed turn snapshot in DB
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

            # Check snapshot attempts were incremented in DB
            updated_snap = db.get_turn_snapshot(self.session_id)
            self.assertEqual(updated_snap["retry_attempts"], 1)

            # Check history in DB was updated
            fresh_session = db.get_session(self.session_id)
            last_hist = fresh_session["history"][-1]
            self.assertEqual(last_hist["outcome_narrative"], "You offer a warm smile to the classmate beside you.")

    async def test_retry_narration_preserves_frozen_location_when_llm_hallucinates_location_dict(self):
        """Verify TurnService.retry_narration never allows LLM output to overwrite the snapshot's frozen location."""
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
            # The outcome location MUST remain the frozen location, NOT the hallucinated dict
            self.assertEqual(turn_response.outcome["location"], frozen_loc)

    def test_parse_tiered_location_handles_structured_json_dict(self):
        """Verify parse_tiered_location decodes structured dicts and JSON strings."""
        from mechanics.world.locations.hierarchy import parse_tiered_location, format_tiered_location_string
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

        import json
        raw_json_str = json.dumps(raw_dict)
        z2, p2, s2 = parse_tiered_location(raw_json_str, scenario_key="nsfw_furry_high_school_drama")
        self.assertEqual(z2, "Sakuragaoka Academy")
        self.assertEqual(p2, "Class 2-B (Homeroom)")
        self.assertEqual(s2, "Artemiusz's Desk")

        # Test dashboard embed output
        mock_sess = {"current_location": raw_json_str, "scenario": "nsfw_furry_high_school_drama"}
        loc_display = _location_text(mock_sess, char_name="Artemiusz")
        self.assertNotIn("{", loc_display)
        self.assertIn("Sakuragaoka Academy ➔ Class 2-B (Homeroom) ➔ Artemiusz's Desk", loc_display)

    async def test_retry_clears_stale_fallback_text_when_outcome_narrative_is_empty(self):
        """Verify that when retry returns only next_narrative, previous fallback text is cleared."""
        from services.turn_service import TurnService
        # Setup snapshot and history with emergency fallback text
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

        # Mock LLM return where outcome_narrative is empty but next_narrative is vivid prose
        mock_retry_result = {
            "outcome_narrative": "",
            "next_narrative": "The main hallway opens into a wide, sun-drenched corridor...",
            "scene_title": "Hallway Briefing",
            "next_choices": [{"label": "Talk to Yuki"}]
        }
        with patch("game_engine.turn.narration.call_llm_json", new=AsyncMock(return_value=mock_retry_result)):
            turn_response = await TurnService.retry_narration(self.session_id, self.user_id)
            self.assertTrue(turn_response.success)

            # Check DB session history
            s = db.get_session(self.session_id)
            updated_entry = s["history"][-1]
            # Stale fallback text must NOT remain in outcome_narrative!
            self.assertEqual(updated_entry["outcome_narrative"], "")
            self.assertIn("The main hallway opens into a wide", updated_entry["next_narrative"])
            self.assertFalse(updated_entry.get("is_fallback", False))

    def test_enrich_session_detects_deliberate_intent_in_history(self):
        """Verify _enrich_session_for_client flags is_fallback_generation when history has deliberate intent fallback."""
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

    def test_observation_and_subject_verb_agreement_fallbacks(self):
        """Verify subject-verb agreement and natural prose generation for perception fallbacks."""
        from game_engine.keywords import sanitize_narrative_context_echo
        echoed_prose = "The hallway is completely silent as the heavy rain continues pouring outside against the glass windows."
        session_prev = {"narrative": echoed_prose}

        # Test keywords echo fallback helper for second-person
        echo_res_you = sanitize_narrative_context_echo(echoed_prose, session_prev, action_label="Open the door", character_name="You")
        self.assertEqual(echo_res_you, "You act with deliberate intent: Open the door.")

        # Test keywords echo fallback helper for third-person
        echo_res_npc = sanitize_narrative_context_echo(echoed_prose, session_prev, action_label="Open the door", character_name="Leon")
        self.assertEqual(echo_res_npc, "Leon acts with deliberate intent: Open the door.")

    async def test_run_narration_pass_sanitizes_echo_and_absent_npcs_without_name_error(self):
        """Verify run_narration_pass executes sanitize_narrative_context_echo and sanitize_absent_npc_hallucinations without session_for_next NameError."""
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


if __name__ == "__main__":
    unittest.main()

