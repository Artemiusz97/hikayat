import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import mechanics.world.locations as locs


class TestCrossZoneMovementAndDestinationResolution(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 99112233
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def test_cross_zone_travel_from_forest_to_capital_guild_hall(self):
        """Verify that choosing to travel to Adventurers Guild Hall from forest transports to Capital, not creating a duplicate in forest."""
        locs.ensure_session_locations_seeded(self.test_session_id, "fantasy")
        kingdom = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        forest = locs.get_session_forest_name(self.test_session_id, "fantasy")
        capital_zone = f"Royal Capital of {kingdom}"

        current_loc = f"{forest} ➔ Sunken Moonwell ➔ Ruined Archway"
        action_text = "Travel toward the Adventurers Guild Hall with the contract"

        res = locs.reconcile_movement_location(
            session_id=self.test_session_id,
            current_loc=current_loc,
            result_loc=f"{forest} ➔ Adventurers Guild Hall ➔ Main Area",
            action_text=action_text,
            narrative="Alice departs the forest and travels back to the guild headquarters.",
            scen_key="fantasy"
        )

        self.assertIn(capital_zone, res)
        self.assertIn("Adventurers' Guild Hall", res)
        self.assertNotIn(forest, res)

    def test_cross_zone_travel_from_forest_to_imperial_palace(self):
        """Verify that choosing to travel to Imperial Palace Grounds transports to Capital."""
        locs.ensure_session_locations_seeded(self.test_session_id, "fantasy")
        kingdom = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        forest = locs.get_session_forest_name(self.test_session_id, "fantasy")
        capital_zone = f"Royal Capital of {kingdom}"

        current_loc = f"{forest} ➔ Sunken Moonwell ➔ Ruined Archway"
        action_text = "Bring the warning of the awakening to the Imperial Palace Grounds"

        res = locs.reconcile_movement_location(
            session_id=self.test_session_id,
            current_loc=current_loc,
            result_loc=f"{kingdom} ➔ Imperial Palace Grounds ➔ Eastern Wardstone Approach",
            action_text=action_text,
            narrative="Alice heads to the palace gates.",
            scen_key="fantasy"
        )

        self.assertIn(capital_zone, res)
        self.assertIn("Imperial Palace Grounds", res)
        self.assertIn("Eastern Wardstone Approach", res)

    def test_travel_within_capital_from_conservatory_to_guild_hall(self):
        """Verify that moving within the capital preserves Royal Capital of [Kingdom] without creating Guild Branch."""
        locs.ensure_session_locations_seeded(self.test_session_id, "fantasy")
        kingdom = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        capital_zone = f"Royal Capital of {kingdom}"

        current_loc = f"{capital_zone} ➔ Grand Arcanum Conservatory ➔ Star-Globe Balcony"
        action_text = "Travel toward the Adventurers Guild Hall with the contract"

        res = locs.reconcile_movement_location(
            session_id=self.test_session_id,
            current_loc=current_loc,
            result_loc=f"{capital_zone} ➔ Adventurers Guild Hall ➔ Contract Dais",
            action_text=action_text,
            narrative="Alice walks through the city to the guild hall.",
            scen_key="fantasy"
        )

        self.assertIn(capital_zone, res)
        self.assertIn("Adventurers' Guild Hall", res)
        self.assertNotIn("Guild Branch", res)

    def test_direct_tiered_travel_from_move_location_dropdown(self):
        """Verify that selecting a tiered destination from the Move Location menu works across zones."""
        locs.ensure_session_locations_seeded(self.test_session_id, "fantasy")
        kingdom = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        forest = locs.get_session_forest_name(self.test_session_id, "fantasy")
        capital_zone = f"Royal Capital of {kingdom}"

        current_loc = f"{forest} ➔ Sunken Moonwell ➔ Ruined Archway"
        action_text = f"I travel to {capital_zone} ➔ Imperial Palace Grounds."

        res = locs.reconcile_movement_location(
            session_id=self.test_session_id,
            current_loc=current_loc,
            result_loc="",
            action_text=action_text,
            narrative="Alice travels to the capital.",
            scen_key="fantasy"
        )

        self.assertIn(capital_zone, res)
        self.assertIn("Imperial Palace Grounds", res)

    def test_session_kingdom_token_resolves_to_full_capital_zone(self):
        """Verify that {session_kingdom} token resolves to Royal Capital of [Kingdom]."""
        template = "{session_kingdom} ➔ Grand Arcanum Conservatory ➔ Star-Globe Balcony"
        resolved = locs.resolve_session_location_tokens(
            session_id=self.test_session_id,
            template=template,
            scenario_key="fantasy"
        )
        kingdom = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        self.assertIn(f"Royal Capital of {kingdom}", resolved)


if __name__ == "__main__":
    unittest.main()
