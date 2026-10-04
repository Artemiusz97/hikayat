"""
Unit tests for the /hub command (and aliases /device, /phone) on AdventureCog.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
import db
from cogs.adventure import AdventureCog


class TestHubCommand(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = 991122
        self.session_id = 771122

        # Clean up database
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))

        self.bot = MagicMock()
        self.cog = AdventureCog(self.bot)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))

    def _create_mock_interaction(self):
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.user = MagicMock()
        interaction.user.id = self.user_id
        interaction.response = AsyncMock()
        return interaction

    def test_command_registration(self):
        """Verify that /hub, /device, /phone, and /adventure hub commands are registered."""
        # Top-level commands on the cog
        app_cmds = [cmd.name for cmd in self.cog.get_app_commands()]
        self.assertIn("hub", app_cmds)
        self.assertIn("device", app_cmds)
        self.assertIn("phone", app_cmds)

        # Adventure subcommands
        sub_cmds = [cmd.name for cmd in self.cog.adventure_group.commands]
        self.assertIn("hub", sub_cmds)

    async def test_hub_no_character(self):
        """When user has no character, _do_hub informs them to create one."""
        interaction = self._create_mock_interaction()
        await self.cog._do_hub(interaction)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("You need a character first", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_hub_no_active_session(self):
        """When user has a character but no active session, _do_hub rejects."""
        db.create_character(self.user_id, "Protagonist", "female")
        interaction = self._create_mock_interaction()
        await self.cog._do_hub(interaction)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("No active adventure", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_hub_unsupported_scenario(self):
        """When active scenario does not feature smartphone/cyberdeck (e.g. pure fantasy), _do_hub rejects."""
        db.create_character(self.user_id, "Protagonist", "female")
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy"
        )

        interaction = self._create_mock_interaction()
        await self.cog._do_hub(interaction)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("does not feature a personal device or communication hub", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_hub_in_combat(self):
        """When user is in combat, device access is blocked."""
        db.create_character(self.user_id, "Protagonist", "female")
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="cyberpunk"
        )
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET nearby_enemies_json = ? WHERE id = ?",
                ('[{"name": "School Bully", "hp": 20}]', sess_id)
            )

        interaction = self._create_mock_interaction()
        await self.cog._do_hub(interaction)

        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.call_args
        self.assertIn("cannot access your communication device while engaged in combat", args[0])
        self.assertTrue(kwargs.get("ephemeral"))

    async def test_hub_success_opens_device(self):
        """When all checks pass, _do_hub sends home embed and PhoneMainView."""
        from mechanics.system.phone import PhoneMainView

        db.create_character(self.user_id, "Protagonist", "female")
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

        interaction = self._create_mock_interaction()
        await self.cog._do_hub(interaction)

        interaction.response.send_message.assert_awaited_once()
        _, kwargs = interaction.response.send_message.call_args
        embed = kwargs.get("embed")
        view = kwargs.get("view")

        self.assertIsNotNone(embed)
        self.assertIn("Smartphone", embed.title)
        self.assertIsInstance(view, PhoneMainView)
        self.assertTrue(kwargs.get("ephemeral"))


if __name__ == "__main__":
    unittest.main()
