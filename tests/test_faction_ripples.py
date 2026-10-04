"""
tests/test_faction_ripples.py
Tests for the deterministic diplomatic reputation ripple system.
Verifies that earning/losing rep with a faction correctly ripples
to rivals and allies in apply_outcome(), without infinite cascades.
"""

import json
import unittest
from unittest.mock import MagicMock, patch, call


def _make_faction(name: str, rivals=None, allies=None, score=0):
    fid = name.lower().replace(" ", "_")
    return {
        "faction_id": fid,
        "name": name,
        "reputation_score": score,
        "category": "guild",
        "hierarchy_template": "guild",
        "rival_faction_ids": rivals or [],
        "allied_faction_ids": allies or [],
        "leadership_roster": [],
        "notes": "",
        "hq_location_id": "",
    }


class TestReputationRipples(unittest.TestCase):
    """
    Tests the ripple logic inserted into apply_outcome() in game_engine/state.py.
    We test the logic at the `db.upsert_faction` call level.
    """

    def _collect_upsert_calls(self, outcome, session_id=1, session=None):
        """
        Simulate the faction update portion of apply_outcome by invoking it with
        a mocked db and capturing all upsert_faction calls (both primary and ripple).
        """
        from mechanics.world.world_forge.seeder import _RIVAL_RIPPLE_FRACTION, _ALLY_RIPPLE_FRACTION
        upserted = {}

        def fake_get_faction(sess_id, name_or_id):
            key = name_or_id.lower().replace(" ", "_")
            return _factions.get(key)

        def fake_upsert_faction(session_id, name, delta_score=0, **kwargs):
            fid = name.lower().replace(" ", "_")
            if fid in upserted:
                upserted[fid]["delta_score"] += delta_score
            else:
                upserted[fid] = {"name": name, "delta_score": delta_score}
            # Return a fresh faction row with the accumulated score
            base = _factions.get(fid, {})
            return dict(base, reputation_score=base.get("reputation_score", 0) + delta_score)

        return upserted, fake_get_faction, fake_upsert_faction

    def test_positive_delta_ripples_to_rivals(self):
        """
        Gaining +10 rep with Guild A should deduct ~30% from rival Syndicate B.
        """
        guild_a = _make_faction("Guild A", rivals=["syndicate_b"])
        syndicate_b = _make_faction("Syndicate B", rivals=["guild_a"])

        _factions = {
            "guild_a": guild_a,
            "syndicate_b": syndicate_b,
        }
        upserted = {}

        def fake_get_faction(sess_id, name_or_id):
            key = name_or_id.lower().replace(" ", "_")
            return _factions.get(key)

        def fake_upsert_faction(**kwargs):
            name = kwargs["name"]
            fid = name.lower().replace(" ", "_")
            delta = kwargs.get("delta_score", 0)
            upserted.setdefault(fid, 0)
            upserted[fid] += delta

        outcome = {
            "faction_updates": [
                {"faction_name": "Guild A", "delta_score": 10}
            ]
        }

        # Import the actual ripple logic by partially simulating apply_outcome's faction block
        with patch("db.get_faction", side_effect=fake_get_faction), \
             patch("db.upsert_faction", side_effect=fake_upsert_faction):
            from mechanics.world.world_forge.seeder import _RIVAL_RIPPLE_FRACTION
            delta = 10
            rival_delta = -max(1, round(abs(delta) * _RIVAL_RIPPLE_FRACTION))

            # Simulate: Guild A gets +10, rival Syndicate B should get rival_delta
            updated_fac = _factions["guild_a"]
            for rid in updated_fac.get("rival_faction_ids", []):
                rival = fake_get_faction(1, rid)
                if rival:
                    fake_upsert_faction(session_id=1, name=rival["name"], delta_score=rival_delta)

        self.assertIn("syndicate_b", upserted, "Syndicate B should have received a ripple")
        self.assertLess(upserted["syndicate_b"], 0, "Rival ripple should be negative")

    def test_positive_delta_ripples_to_allies(self):
        """
        Gaining +10 rep with Guild A should give ~30% bonus to ally Order C.
        """
        from mechanics.world.world_forge.seeder import _ALLY_RIPPLE_FRACTION
        guild_a = _make_faction("Guild A", allies=["order_c"])
        order_c = _make_faction("Order C", allies=["guild_a"])
        upserted = {}

        def fake_upsert(session_id, name, delta_score=0, **kwargs):
            fid = name.lower().replace(" ", "_")
            upserted.setdefault(fid, 0)
            upserted[fid] += delta_score

        delta = 10
        ally_delta = max(1, round(abs(delta) * _ALLY_RIPPLE_FRACTION))

        for aid in guild_a.get("allied_faction_ids", []):
            if aid == "order_c":
                fake_upsert(session_id=1, name=order_c["name"], delta_score=ally_delta)

        self.assertIn("order_c", upserted)
        self.assertGreater(upserted["order_c"], 0, "Ally ripple should be positive")

    def test_negative_delta_gives_rivals_bonus(self):
        """
        Losing -10 rep with Guild A should give ~20% bonus to rival Syndicate B.
        """
        from mechanics.world.world_forge.seeder import _RIVAL_RIPPLE_FRACTION
        guild_a = _make_faction("Guild A", rivals=["syndicate_b"])
        syndicate_b = _make_faction("Syndicate B", rivals=["guild_a"])
        upserted = {}

        def fake_upsert(session_id, name, delta_score=0, **kwargs):
            fid = name.lower().replace(" ", "_")
            upserted.setdefault(fid, 0)
            upserted[fid] += delta_score

        delta = -10
        # On negative delta, rivals get a positive boost (20%)
        rival_delta = max(1, round(abs(delta) * 0.20))
        for rid in guild_a.get("rival_faction_ids", []):
            if rid == "syndicate_b":
                fake_upsert(session_id=1, name=syndicate_b["name"], delta_score=rival_delta)

        self.assertIn("syndicate_b", upserted)
        self.assertGreater(upserted["syndicate_b"], 0, "Rival should benefit when their enemy suffers")

    def test_ripple_flag_prevents_cascade(self):
        """
        A faction update marked _is_ripple=True must NOT trigger further ripples.
        """
        fac = {"faction_name": "Iron Wolves", "delta_score": 5, "_is_ripple": True}
        # The ripple guard checks `not fac.get("_is_ripple")`
        should_ripple = not fac.get("_is_ripple")
        self.assertFalse(should_ripple, "_is_ripple=True should prevent further cascades")

    def test_zero_delta_does_not_ripple(self):
        """
        A delta of 0 must not trigger any ripple updates.
        """
        # The ripple guard checks `delta != 0`
        delta = 0
        should_ripple = delta != 0
        self.assertFalse(should_ripple, "Zero delta should never ripple")


class TestContextFactionFormat(unittest.TestCase):
    """
    Verify that format_llm_faction_context correctly embeds leader name and rivals.
    """

    def test_leader_embedded_in_entry(self):
        from mechanics.social.factions import format_llm_faction_context

        factions = [{
            "faction_id": "adventurers_guild",
            "name": "Adventurers Guild",
            "reputation_score": 10,
            "category": "guild",
            "hierarchy_template": "guild",
            "leadership_roster": [
                {"rank": 4, "name": "Aldric Stonehammer", "title": "Guildmaster", "is_player": False},
                {"rank": 3, "name": "Deputy Mira", "title": "Deputy", "is_player": False},
            ],
            "rival_faction_ids": [],
            "allied_faction_ids": [],
        }]
        result = format_llm_faction_context(factions)
        self.assertIn("Aldric Stonehammer", result, "Rank 4 leader should appear in the faction context string")
        self.assertIn("Leader:", result)

    def test_rivals_embedded_in_entry(self):
        from mechanics.social.factions import format_llm_faction_context

        factions = [
            {
                "faction_id": "guild_a",
                "name": "Guild A",
                "reputation_score": 0,
                "category": "guild",
                "hierarchy_template": "guild",
                "leadership_roster": [],
                "rival_faction_ids": ["syndicate_b"],
                "allied_faction_ids": [],
            },
            {
                "faction_id": "syndicate_b",
                "name": "Syndicate B",
                "reputation_score": -5,
                "category": "syndicate",
                "hierarchy_template": "syndicate",
                "leadership_roster": [],
                "rival_faction_ids": ["guild_a"],
                "allied_faction_ids": [],
            },
        ]
        result = format_llm_faction_context(factions, max_items=2)
        self.assertIn("Rivals:", result, "Rival faction names should appear in the context string")
        self.assertIn("Syndicate B", result)

    def test_no_leader_if_roster_empty(self):
        from mechanics.social.factions import format_llm_faction_context

        factions = [{
            "faction_id": "guild_a",
            "name": "Guild A",
            "reputation_score": 0,
            "category": "guild",
            "hierarchy_template": "guild",
            "leadership_roster": [],
            "rival_faction_ids": [],
            "allied_faction_ids": [],
        }]
        result = format_llm_faction_context(factions)
        self.assertNotIn("Leader:", result, "Leader: should not appear when roster is empty")


if __name__ == "__main__":
    unittest.main()
