"""
tests/test_world_forge.py
Tests for the World Forge Pre-Seeder:
  - Deterministic diplomatic matrix seeding
  - LLM Pass 0 fallback behaviour
  - Macro-world state lorebook persistence
"""

import json
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_faction(name: str, category: str, faction_id: str = None, rivals=None, allies=None):
    fid = faction_id or name.lower().replace(" ", "_")
    return {
        "faction_id": fid,
        "name": name,
        "category": category,
        "hierarchy_template": category,
        "reputation_score": 0,
        "leadership_roster": [],
        "rival_faction_ids": rivals or [],
        "allied_faction_ids": allies or [],
        "hq_location_id": "",
        "notes": "",
    }


# ---------------------------------------------------------------------------
# 1. Diplomatic Matrix Tests
# ---------------------------------------------------------------------------
class TestSeedDiplomaticMatrix(unittest.TestCase):

    def setUp(self):
        self.session_id = 9001
        self.upserted = []

    def _run_seed(self, factions):
        """Invoke seed_diplomatic_matrix with mocked DB calls."""
        from mechanics.world.world_forge.seeder import seed_diplomatic_matrix

        with patch("mechanics.world.world_forge.seeder.db.get_factions", return_value=factions), \
             patch("mechanics.world.world_forge.seeder.db.upsert_faction", side_effect=lambda **kw: self.upserted.append(kw)):
            seed_diplomatic_matrix(self.session_id, "fantasy")

    def test_guild_and_delinquents_are_rivals(self):
        factions = [
            _make_faction("Adventurers Guild", "guild"),
            _make_faction("Iron Wolves", "delinquents"),
        ]
        self._run_seed(factions)
        # At least one upsert should set rivals
        rival_sets = [u.get("rival_faction_ids", []) for u in self.upserted]
        self.assertTrue(any(rival_sets), "Expected at least one faction to get rivals")

    def test_guild_and_order_are_allies(self):
        factions = [
            _make_faction("Adventurers Guild", "guild"),
            _make_faction("Knights of Dawn", "order"),
        ]
        self._run_seed(factions)
        ally_sets = [u.get("allied_faction_ids", []) for u in self.upserted]
        self.assertTrue(any(ally_sets), "Expected at least one faction to get allies")

    def test_symmetric_rivals(self):
        """If A rivals B, B must also rival A."""
        factions = [
            _make_faction("Merchants", "guild"),
            _make_faction("Thieves Syndicate", "syndicate"),
        ]
        self._run_seed(factions)
        # Build resulting map
        result = {}
        for u in self.upserted:
            name = u["name"]
            result[name] = u.get("rival_faction_ids", [])
        # Both should be in each other's rival list
        for name_a, rivals_a in result.items():
            for rival_id in rivals_a:
                # Check that the rival also lists name_a as a rival
                rival_key = next((n for n, _ in result.items() if n.lower().replace(" ", "_") == rival_id), None)
                if rival_key:
                    self.assertIn(
                        name_a.lower().replace(" ", "_"),
                        result.get(rival_key, []),
                        f"Relationship not symmetric: {name_a} rivals {rival_id} but not vice versa"
                    )

    def test_no_factions_is_noop(self):
        """seed_diplomatic_matrix should not crash or upsert anything with 0 factions."""
        self._run_seed([])
        self.assertEqual(self.upserted, [])

    def test_runs_fast(self):
        """Deterministic seeding should complete in < 50 ms for 5 factions."""
        from mechanics.world.world_forge.seeder import seed_diplomatic_matrix
        factions = [
            _make_faction("Guild A", "guild"),
            _make_faction("Order B", "order"),
            _make_faction("Gang C", "delinquents"),
            _make_faction("Corp D", "corpo"),
            _make_faction("Syndicate E", "syndicate"),
        ]
        with patch("mechanics.world.world_forge.seeder.db.get_factions", return_value=factions), \
             patch("mechanics.world.world_forge.seeder.db.upsert_faction"):
            start = time.perf_counter()
            seed_diplomatic_matrix(self.session_id, "cyberpunk")
            elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertLess(elapsed_ms, 50, f"seed_diplomatic_matrix took {elapsed_ms:.1f} ms (> 50 ms limit)")


# ---------------------------------------------------------------------------
# 2. LLM Pass 0 / Macro-World State Tests
# ---------------------------------------------------------------------------
class TestGenerateMacroWorldState(unittest.IsolatedAsyncioTestCase):

    async def test_llm_success_path(self):
        from mechanics.world.world_forge.seeder import generate_macro_world_state

        fake_factions = [
            _make_faction("Adventurers Guild", "guild", rivals=["iron_wolves"]),
            _make_faction("Iron Wolves", "delinquents", rivals=["adventurers_guild"]),
        ]
        fake_llm_result = {
            "macro_conflict": "The Guild and the Iron Wolves clash over territorial rights.",
            "world_rumor": "A witness saw Guild enforcers burning Wolf hideouts at night.",
            "active_flashpoint": "Guildmaster's Hall",
        }
        session = {"id": 9001, "scenario": "fantasy"}

        with patch("mechanics.world.world_forge.seeder.db.get_factions", return_value=fake_factions), \
             patch("mechanics.world.world_forge.seeder.db.upsert_lorebook_entity") as mock_lore, \
             patch("game_engine.call_llm_json", new=AsyncMock(return_value=fake_llm_result)):
            result = await generate_macro_world_state(9001, session, [])

        self.assertIsNotNone(result)
        self.assertIn("macro_conflict", result)
        mock_lore.assert_called_once()
        call_kwargs = mock_lore.call_args[1] if mock_lore.call_args[1] else {}
        description = call_kwargs.get("description", "")
        self.assertIn("Guild", description)

    async def test_llm_failure_fallback(self):
        """On LLM failure, should still persist a procedural fallback."""
        from mechanics.world.world_forge.seeder import generate_macro_world_state

        fake_factions = [
            _make_faction("Student Council", "council", rivals=["iron_wolves"]),
            _make_faction("Iron Wolves", "delinquents", rivals=["student_council"]),
        ]
        session = {"id": 9002, "scenario": "high_school_drama"}

        with patch("mechanics.world.world_forge.seeder.db.get_factions", return_value=fake_factions), \
             patch("mechanics.world.world_forge.seeder.db.upsert_lorebook_entity") as mock_lore, \
             patch("game_engine.call_llm_json", new=AsyncMock(side_effect=Exception("timeout"))):
            result = await generate_macro_world_state(9002, session, [])

        self.assertIsNotNone(result, "Fallback should return a non-None result")
        self.assertIn("macro_conflict", result)
        mock_lore.assert_called_once()

    async def test_no_factions_returns_none(self):
        from mechanics.world.world_forge.seeder import generate_macro_world_state

        with patch("mechanics.world.world_forge.seeder.db.get_factions", return_value=[]):
            result = await generate_macro_world_state(9003, {"id": 9003, "scenario": "fantasy"}, [])

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 3. Lorebook Persistence Tests
# ---------------------------------------------------------------------------
class TestPersistMacroWorld(unittest.TestCase):

    def test_persist_populates_description(self):
        from mechanics.world.world_forge.seeder import _persist_macro_world

        data = {
            "macro_conflict": "A great war looms.",
            "world_rumor": "Spies spotted near the northern wall.",
            "active_flashpoint": "Northern Bastion",
        }
        with patch("mechanics.world.world_forge.seeder.db.upsert_lorebook_entity") as mock_lore:
            _persist_macro_world(9999, data)

        mock_lore.assert_called_once()
        args = mock_lore.call_args
        description = (args[1] if args[1] else {}).get("description", "") or (args[0][3] if args[0] and len(args[0]) > 3 else "")
        self.assertIn("great war", description)
        self.assertIn("CURRENT RUMOR", description)
        self.assertIn("FLASHPOINT", description)

    def test_empty_macro_is_noop(self):
        from mechanics.world.world_forge.seeder import _persist_macro_world

        with patch("mechanics.world.world_forge.seeder.db.upsert_lorebook_entity") as mock_lore:
            _persist_macro_world(9999, {"macro_conflict": "", "world_rumor": ""})

        mock_lore.assert_not_called()


if __name__ == "__main__":
    unittest.main()
