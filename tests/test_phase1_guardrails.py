import unittest
from mechanics.narrative.intent import (
    is_conversational_exit,
    is_travel_action,
    is_conversational_action,
    classify_action_intent,
    IntentCategory
)
from mechanics.world.waypoints.matching import check_action_matches_waypoint
from game_engine.state import should_trigger_state_arbiter_pass


class TestPhase1Guardrails(unittest.TestCase):
    """Verifies Phase 1 critical guardrails and elimination of bare 'thank' false-positives."""

    def test_polite_dialogue_does_not_trigger_conversational_exit(self):
        """Verify polite dialogue choices starting with or containing 'thank' are not flagged as exits."""
        polite_choices = [
            "Thank Denise for the notes and review them together",
            "Thank Elder Maerwyn and ask about the blue fire",
            "Express gratitude to Justin and discuss the plan",
            "Thank the merchant and inspect the potions"
        ]
        for choice in polite_choices:
            self.assertFalse(
                is_conversational_exit(choice),
                f"Choice '{choice}' was erroneously flagged as an exit!"
            )

    def test_genuine_exits_are_reliably_detected(self):
        """Verify true departures and farewells are detected as exits."""
        true_exits = [
            "Say goodbye to Denise and step away",
            "Excuse yourself from the council chamber",
            "Part ways with Elder Maerwyn and return to the road",
            "Bid farewell to Justin and walk away",
            "Thank Elder Maerwyn Rootspeaker, excuse yourself, and look around the room"
        ]
        for exit_text in true_exits:
            self.assertTrue(
                is_conversational_exit(exit_text),
                f"Exit '{exit_text}' was NOT detected as an exit!"
            )

    def test_multipass_generation_arbiter_does_not_flag_polite_dialogue_as_departure(self):
        """Verify should_run_multipass_generation does not trigger for polite thank-you dialogue."""
        session = {
            "dialogue_partner": "Denise Richards",
            "current_npcs": [{"name": "Denise Richards", "role": "Classmate"}]
        }
        actions = [
            {"label": "Thank Denise for the notes and review them together"}
        ]
        # Should NOT trigger multi-pass solely due to 'thank'
        self.assertFalse(should_trigger_state_arbiter_pass(session, actions))

    def test_multipass_generation_arbiter_detects_genuine_departure(self):
        """Verify should_trigger_state_arbiter_pass triggers on true conversational exit."""
        session = {
            "dialogue_partner": "Denise Richards",
            "current_npcs": [{"name": "Denise Richards", "role": "Classmate"}]
        }
        actions = [
            {"label": "Say goodbye to Denise and leave the room"}
        ]
        self.assertTrue(should_trigger_state_arbiter_pass(session, actions))

    def test_waypoint_matching_rejects_expanded_movement_phrases(self):
        """Verify novel movement actions do NOT complete stationary skill-check waypoints."""
        movement_phrases = [
            "I travel to Westlake Academy ➔ Classroom 2-B (Homeroom).",
            "Travel to the docks to search the crates",
            "Head to the student council office",
            "Walk to the library archives",
            "Slip into the alleyway",
            "Move to the central courtyard",
            "Make our way to the faculty lounge",
            "Step into the underground crypt"
        ]
        for act in movement_phrases:
            # Stationary skill check waypoint: "Inspect the ancient runes"
            matched = check_action_matches_waypoint(
                action_text=act,
                narrative="The dust settles around the chamber.",
                stage_label="Inspect the ancient runes carved into the pedestal"
            )
            self.assertFalse(
                matched,
                f"Movement action '{act}' falsely completed stationary waypoint!"
            )

    def test_waypoint_matching_blocks_dialogue_on_physical_objectives(self):
        """Verify conversational dialogue actions cannot complete non-dialogue physical waypoints."""
        dialogue_actions = [
            "Ask which specific Guild members are involved",
            "Question Maelin about the ledger",
            "Inquire about the secret meeting location",
            "Chat with the guard about the weather"
        ]
        for act in dialogue_actions:
            matched = check_action_matches_waypoint(
                action_text=act,
                narrative="The clockwork engine hums quietly in the background.",
                stage_label="Carefully decouple the clockwork prototype from the console housing"
            )
            self.assertFalse(
                matched,
                f"Dialogue action '{act}' falsely completed physical objective!"
            )


if __name__ == "__main__":
    unittest.main()
