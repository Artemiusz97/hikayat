"""
Tests for Issue #5: Central Intent Engine vs. Scattered Raw Substring Lists.
Verifies that intent classification overrides raw substring false positives.
"""
import pytest
from mechanics.narrative.intent import is_conversational_exit, is_escort_dismissal_action
from mechanics.world.mobility import is_solo_travel_intent

class TestCentralIntentStreamlining:

    def test_polite_dialogue_not_exit(self):
        """'Thank' should not falsely trigger conversational exit unless explicitly an exit intent."""
        # This was causing false-positives when "thank" was bare in exit_phrases
        lbl = "Thank Denise for the notes and review them together"
        assert not is_conversational_exit(lbl), "Polite continuation should not be an exit"

    def test_true_exit_still_detected(self):
        lbl1 = "Thank Denise, say goodbye, and head back to class"
        assert is_conversational_exit(lbl1), "Explicit exit phrases should trigger exit"
        
        lbl2 = "Excuse yourself and step away"
        assert is_conversational_exit(lbl2)

    def test_accompanied_walk_alone_disambiguation(self):
        """'Walk with X ... alone' should NOT be solo travel."""
        actions = [{"label": "Walk with Denise to find a quiet spot where we can be alone"}]
        assert not is_solo_travel_intent(actions), "Accompanied request for privacy is not solo travel"

    def test_protective_leave_alone_disambiguation(self):
        """'Leave X alone' should NOT be solo travel."""
        actions = [{"label": "Tell the thugs to leave Denise alone and step in front of her"}]
        assert not is_solo_travel_intent(actions), "Protective imperative is not solo travel"

    def test_true_solo_travel_detected(self):
        """True solo travel phrasing should still trigger."""
        a1 = [{"label": "Tell Zihan I'm going alone and head down to class"}]
        a2 = [{"label": "Excuse yourself and head to homeroom class alone"}]
        
        assert is_solo_travel_intent(a1)
        assert is_solo_travel_intent(a2)

    def test_escort_dismissal_action(self):
        """Escort dismissal correctly handles conversational exit + specialized phrases."""
        assert is_escort_dismissal_action("Say goodbye and head back to the dorm")
        assert is_escort_dismissal_action("Tell her to head home alone")
        assert is_escort_dismissal_action("Let's part ways here")
        assert not is_escort_dismissal_action("Walk home together")
        assert not is_escort_dismissal_action("Hang out together")
