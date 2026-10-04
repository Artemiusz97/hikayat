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

if __name__ == "__main__":
    unittest.main()
