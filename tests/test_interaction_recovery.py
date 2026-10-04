"""
Unit tests for recovering expired component interactions and seamless scene continuation.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import db
import bot


class TestInteractionRecovery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = 992211
        self.session_id = 882211

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))

        db.create_character(self.user_id, "Protagonist", "female")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))

    def _create_mock_interaction(self, is_done=False, is_ephemeral=False, itype=discord.InteractionType.component):
        interaction = MagicMock(spec=discord.Interaction)
        interaction.type = itype
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.channel_id = 12345
        interaction.channel = MagicMock()
        interaction.channel.parent_id = None
        interaction.response = MagicMock()
        interaction.response.is_done = MagicMock(return_value=is_done)
        interaction.response.send_message = AsyncMock()
        interaction.response.defer = AsyncMock()

        interaction.message = MagicMock()
        flags = MagicMock()
        flags.ephemeral = is_ephemeral
        interaction.message.flags = flags
        return interaction

    async def test_ignores_non_component_interaction(self):
        """Slash commands / non-components are ignored by the fallback handler."""
        interaction = self._create_mock_interaction(itype=discord.InteractionType.application_command)
        await bot.on_interaction(interaction)
        interaction.response.send_message.assert_not_called()
        interaction.response.defer.assert_not_called()

    async def test_ignores_already_acknowledged_interaction(self):
        """If an active View in memory already handled the interaction, do nothing."""
        interaction = self._create_mock_interaction(is_done=True)
        await bot.on_interaction(interaction)
        interaction.response.send_message.assert_not_called()
        interaction.response.defer.assert_not_called()

    async def test_recovers_active_session_and_resends_scene(self):
        """When an unhandled button click occurs with an active session, seamlessly resend the scene."""
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        interaction = self._create_mock_interaction(is_done=False, is_ephemeral=False)

        mock_cog = AsyncMock()
        with patch.object(bot.bot, "get_cog", return_value=mock_cog):
            await bot.on_interaction(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=False)
        mock_cog._resend_current_scene.assert_awaited_once()

    async def test_ephemeral_message_informs_player(self):
        """If the expired button was on an ephemeral message, send an ephemeral guidance note."""
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        interaction = self._create_mock_interaction(is_done=False, is_ephemeral=True)

        await bot.on_interaction(interaction)
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("This menu expired", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_no_active_session_informs_player(self):
        """If user has no active session, send an ephemeral message explaining it expired."""
        interaction = self._create_mock_interaction(is_done=False, is_ephemeral=False)

        await bot.on_interaction(interaction)
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("expired after an idle period or restart", args[0])
    async def test_skips_when_view_store_has_registered_item(self):
        """If discord.py view_store has an active view registered for this button, skip immediately."""
        interaction = self._create_mock_interaction(is_done=False, is_ephemeral=False)
        interaction.data = {"component_type": 2, "custom_id": "test_button"}
        interaction.message.id = 123456

        mock_state = MagicMock()
        mock_view_store = MagicMock()
        mock_view_store._views = {123456: {(2, "test_button"): MagicMock()}}
        mock_state._view_store = mock_view_store
        interaction._state = mock_state

        await bot.on_interaction(interaction)
        interaction.response.send_message.assert_not_called()
        interaction.response.defer.assert_not_called()

    async def test_suppresses_40060_error(self):
        """If 40060 (already acknowledged) occurs due to concurrent response, do not raise."""
        db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        interaction = self._create_mock_interaction(is_done=False, is_ephemeral=False)

        # Simulate 40060 error when defer is called
        mock_resp = MagicMock()
        mock_resp.status = 400
        err = discord.HTTPException(mock_resp, {"code": 40060, "message": "Interaction has already been acknowledged."})
        interaction.response.defer.side_effect = err

        mock_cog = AsyncMock()
        with patch.object(bot.bot, "get_cog", return_value=mock_cog):
            # Should not raise exception
            await bot.on_interaction(interaction)

    async def test_choice_view_move_location_defers_and_sends_followup(self):
        """ChoiceView._move_location_callback defers early and sends via followup."""
        from cogs.adventure import ChoiceView
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", ("Classroom 2-B", sess_id))

        mock_cog = MagicMock()
        char = db.get_character(self.user_id)
        view = ChoiceView(mock_cog, sess_id, self.user_id, [{"label": "Wait", "stat": "NONE"}], actor_char=char)

        interaction = self._create_mock_interaction(is_done=False)
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        # Simulate is_done becoming True after defer is awaited
        async def fake_defer(ephemeral=False):
            interaction.response.is_done.return_value = True
        interaction.response.defer.side_effect = fake_defer

        await view._move_location_callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.call_args[1].get("ephemeral"))

    async def test_sync_choice_view_move_location_defers_and_sends_followup(self):
        """SyncChoiceView._move_location_callback defers early and sends via followup."""
        from cogs.adventure import SyncChoiceView
        sess_id = db.create_session(
            self.user_id, "party", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", ("Classroom 2-B", sess_id))

        mock_cog = MagicMock()
        view = SyncChoiceView(mock_cog, sess_id, [self.user_id], [{"label": "Wait", "stat": "NONE"}], [])

        interaction = self._create_mock_interaction(is_done=False)
        interaction.followup = MagicMock()
        interaction.followup.send = AsyncMock()

        async def fake_defer(ephemeral=False):
            interaction.response.is_done.return_value = True
        interaction.response.defer.side_effect = fake_defer

        await view._move_location_callback(interaction)

        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.call_args[1].get("ephemeral"))

    async def test_do_resume_defers_immediately_and_resends_scene(self):
        """_do_resume defers immediately before querying DB or rendering scenes."""
        from cogs.adventure import AdventureCog
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        mock_bot = MagicMock()
        cog = AdventureCog(mock_bot)
        cog._resend_current_scene = AsyncMock()

        interaction = self._create_mock_interaction(is_done=False)
        async def fake_defer():
            interaction.response.is_done.return_value = True
        interaction.response.defer.side_effect = fake_defer

        await cog._do_resume(interaction)

        interaction.response.defer.assert_awaited_once()
        cog._resend_current_scene.assert_awaited_once_with(interaction, unittest.mock.ANY, use_followup=True)

    async def test_do_resume_handles_unknown_interaction_gracefully(self):
        """If Discord throws 10062 NotFound on defer, _do_resume does not crash."""
        from cogs.adventure import AdventureCog
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        mock_bot = MagicMock()
        cog = AdventureCog(mock_bot)
        cog._resend_current_scene = AsyncMock()

        interaction = self._create_mock_interaction(is_done=False)
        mock_resp = MagicMock()
        mock_resp.status = 404
        interaction.response.defer.side_effect = discord.NotFound(mock_resp, {"code": 10062, "message": "Unknown interaction"})

        # Should not raise
        await cog._do_resume(interaction)
        cog._resend_current_scene.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()

