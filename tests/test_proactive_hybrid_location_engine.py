import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import mechanics.world.locations as locs


class TestProactiveHybridLocationEngine(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 991122
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

        # Seed Solaria with Boar's Tusk Tavern, Adventurers' Guild Hall, and Cobblestone Market Plaza
        locs.process_llm_location_update(self.test_session_id, "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table", "fantasy")
        locs.process_llm_location_update(self.test_session_id, "Solaria ➔ Adventurers' Guild Hall ➔ Main Hall", "fantasy")
        locs.process_llm_location_update(self.test_session_id, "Solaria ➔ Cobblestone Market Plaza ➔ Central Fountain", "fantasy")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_travel_openly_toward_guild_hall(self):
        """Verify 'Travel openly toward the Adventurers' Guild Hall' updates location to Guild Hall."""
        curr_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        action = "Travel openly toward the Adventurers' Guild Hall"
        narrative = "The Adventurers' Guild Hall rises beyond the Crownward avenue. Inside, mercenaries crowd around the board."
        llm_loc = "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium"

        reconciled = locs.reconcile_movement_location(
            self.test_session_id, curr_loc, llm_loc,
            action_text=action, narrative=narrative,
            scen_key="fantasy"
        )

        self.assertEqual(reconciled, "Solaria ➔ Adventurers' Guild Hall ➔ Contract Atrium")

    def test_slip_through_alleys_toward_guild_hall(self):
        """Verify 'Slip through rain-darkened alleys toward the Guild Hall' matches keywords and updates location."""
        curr_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        action = "Slip through rain-darkened alleys toward the Guild Hall"
        narrative = "Reaching the alley exit, Alice steps through into the Adventurers' Guild Hall."
        llm_loc = "Solaria ➔ Adventurers' Guild Hall ➔ Vaulted Entry"

        reconciled = locs.reconcile_movement_location(
            self.test_session_id, curr_loc, llm_loc,
            action_text=action, narrative=narrative,
            scen_key="fantasy"
        )

        self.assertEqual(reconciled, "Solaria ➔ Adventurers' Guild Hall ➔ Vaulted Entry")

    def test_leave_tavern_head_for_market(self):
        """Verify 'Leave the tavern and head for Cobblestone Market Plaza' updates to Market Plaza."""
        curr_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        action = "Leave the tavern and head for Cobblestone Market Plaza"
        narrative = "Stepping onto the wet cobblestones, market stalls surround the party."
        llm_loc = "Solaria ➔ Cobblestone Market Plaza ➔ Spice Stalls"

        reconciled = locs.reconcile_movement_location(
            self.test_session_id, curr_loc, llm_loc,
            action_text=action, narrative=narrative,
            scen_key="fantasy"
        )

        self.assertEqual(reconciled, "Solaria ➔ Cobblestone Market Plaza ➔ Spice Stalls")

    def test_stationary_speech_anchored_at_tavern(self):
        """Verify stationary dialogue without travel action stays anchored at the tavern."""
        curr_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        action = "Speak with Mara Vey about the contract runes"
        narrative = "Mara leans in close over the wooden table, her voice low."
        # LLM hallucinates teleporting to the castle library
        llm_loc = "Solaria ➔ Royal Castle Library ➔ Archives"

        reconciled = locs.reconcile_movement_location(
            self.test_session_id, curr_loc, llm_loc,
            action_text=action, narrative=narrative,
            scen_key="fantasy"
        )

        # Must retain The Boar's Tusk Tavern
        self.assertEqual(reconciled, "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table")

    def test_critical_failure_on_travel_allows_complication_hazard(self):
        """Verify critical failure on travel allows complication/hazard location instead of destination."""
        curr_loc = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        action = "Sprint across the rope bridge toward Highspire"
        narrative = "The bridge ropes snap! Alice plunges into the dark ravine below."
        llm_loc = "Solaria ➔ Sunken Ravine ➔ Chasm Floor"

        reconciled = locs.reconcile_movement_location(
            self.test_session_id, curr_loc, llm_loc,
            action_text=action, narrative=narrative,
            scen_key="fantasy", check_tier="crit_fail"
        )

        self.assertEqual(reconciled, "Solaria ➔ Sunken Ravine ➔ Chasm Floor")


if __name__ == "__main__":
    unittest.main()
