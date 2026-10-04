"""
tests/test_chimera_guardrails_streamlining.py

Unit test suite for Issue #3: Location/Zone Resolution & Chimera Guardrail Streamlining.
Tests all 7 root causes identified and fixed in mechanics/locations/core.py.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mechanics.world.locations.core import (
    parse_tiered_location,
    is_incongruous_container,
    is_movement_action,
    auto_heal_incongruous_location,
    process_llm_location_update,
    _build_session_zone_index,
    reconcile_movement_location,
)

# ── Constants ─────────────────────────────────────────────────────────────────
HIGH_SCHOOL = "high_school"
SESSION_1 = 1   # has St. Michael Academy + Kaede Residential Quarter


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 1 + Fix 2: auto_heal_incongruous_location — Tier 1 Zone never promoted to Tier 2
# ══════════════════════════════════════════════════════════════════════════════

class TestAutoHealChimeraFallback:
    """Root Cause 1: auto_heal_incongruous_location blindly promoted a Tier 1 Zone to Tier 2."""

    def test_zone_in_sub_resolves_to_canonical_zone_gateway(self):
        """
        'Kaede Residential Quarter ➔ Artem's House ➔ St. Michael Academy'
        must resolve to St. Michael Academy's gateway, not stay as a chimera.
        """
        result = auto_heal_incongruous_location(
            "Kaede Residential Quarter",
            "Artem's House",
            "St. Michael Academy",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        zone, primary, sub = result
        assert zone == "St. Michael Academy", f"Expected St. Michael Academy as zone, got: {zone}"
        assert "foyer" in primary.lower() or "entrance" in primary.lower() or "main" in primary.lower(), \
            f"Expected a gateway primary, got: {primary}"
        assert zone != primary, "Zone and primary should not be identical"

    def test_heal_does_not_produce_chimera_zone_as_primary(self):
        """Healed result must never place a known Tier 1 Zone in the Tier 2 slot."""
        result = auto_heal_incongruous_location(
            "Kaede Residential Quarter",
            "Artem's House",
            "St. Michael Academy",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        zone, primary, sub = result
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        assert primary.strip().lower() not in zones_index, \
            f"Primary '{primary}' is a Tier 1 Zone — chimera still produced!"

    def test_heal_with_residential_zone_as_sub(self):
        """
        'St. Michael Academy ➔ Entrance Foyer ➔ Kaede Residential Quarter'
        must resolve to the residential zone's gateway, not be embedded under academy.
        """
        result = auto_heal_incongruous_location(
            "St. Michael Academy",
            "Entrance Foyer & Shoe Lockers",
            "Kaede Residential Quarter",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        zone, primary, sub = result
        assert "kaede" in zone.lower() or "residential" in zone.lower(), \
            f"Expected residential zone, got: {zone}"


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 1 (part 2): is_incongruous_container — unconditional tier check
# ══════════════════════════════════════════════════════════════════════════════

class TestIncongruousContainerUnconditional:
    """Root Cause 2: is_incongruous_container only checked tier violations for enclosed rooms."""

    def test_zone_as_sub_of_exterior_primary_is_incongruous(self):
        """
        'School Gates ➔ St. Michael Academy' must be incongruous even though
        'School Gates' is not an ENCLOSED_ROOM_KEYWORD container.
        """
        result = is_incongruous_container(
            "School Gates",
            "St. Michael Academy",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        assert result is True, "School Gates ➔ Tier1Zone must be flagged as incongruous"

    def test_zone_as_sub_of_residential_street_is_incongruous(self):
        """A residential walkway with a zone name as sub-location is always incongruous."""
        result = is_incongruous_container(
            "Residential Walkway",
            "St. Michael Academy",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        assert result is True, "Residential Walkway ➔ Tier1Zone must be flagged as incongruous"

    def test_zone_as_sub_of_enclosed_room_is_incongruous(self):
        """Enclosed room with a zone sub-location: still caught."""
        result = is_incongruous_container(
            "Student Council Office",
            "St. Michael Academy",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        assert result is True

    def test_valid_sub_inside_enclosed_room_not_incongruous(self):
        """Legitimate room sub-locations should not be flagged."""
        result = is_incongruous_container(
            "Student Council Office",
            "President's Desk",
            session_id=SESSION_1,
            scenario_key=HIGH_SCHOOL,
        )
        assert result is False

    def test_main_area_never_incongruous(self):
        result = is_incongruous_container(
            "Artem's House", "Main Area", session_id=SESSION_1, scenario_key=HIGH_SCHOOL
        )
        assert result is False


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 3: is_movement_action — intent check before conversational blacklist
# ══════════════════════════════════════════════════════════════════════════════

class TestMovementActionIntentFirst:
    """Root Cause 3: conversational blacklist ran before intent engine, blocking movement verbs."""

    def test_head_toward_with_rumor_keyword_is_movement(self):
        """'Head toward X to investigate campus rumors' must be classified as movement."""
        assert is_movement_action("Head toward St. Michael Academy to investigate campus rumors") is True

    def test_head_to_with_study_keyword_is_movement(self):
        """Movement imperative takes precedence over 'study' in the action text."""
        assert is_movement_action("Head to the library to study for exams") is True

    def test_walk_to_with_ask_keyword_is_movement(self):
        assert is_movement_action("Walk to the Student Council Office to ask about the budget") is True

    def test_pure_ask_with_no_movement_verb_is_not_movement(self):
        """Pure conversational action with no movement verb must return False."""
        assert is_movement_action("Ask about the rumor going around school") is False

    def test_pure_study_is_not_movement(self):
        assert is_movement_action("Study quietly in the corner") is False

    def test_investigate_rumors_stationary_is_not_movement(self):
        assert is_movement_action("Investigate the rumors about the stolen test papers") is False

    def test_travel_to_is_movement(self):
        assert is_movement_action("Travel to the park for a walk") is True

    def test_walk_into_library_is_movement(self):
        # 'Enter the library' alone isn't movement (intent engine: INSPECT_BOARD),
        # but explicitly heading there is.
        assert is_movement_action("Walk into the library to check the bulletin board") is True


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 4: Spatial Anchor Guard — atomic 3-tuple rollback
# ══════════════════════════════════════════════════════════════════════════════

class TestSpatialAnchorAtomicRollback:
    """Root Cause 4: Spatial Anchor Guard reverted primary+zone but kept res_s, creating partial chimeras."""

    def test_non_movement_at_house_keeps_all_three_tiers(self):
        """
        With a non-movement action, the anchor guard must restore ALL of (zone, primary, sub).
        A foreign sub-location must not survive in res_s.
        """
        # Simulate a narrative that merely mentions a school campus but player did not move
        curr_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Bedroom"
        result_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Main Area"
        result = reconcile_movement_location(
            session_id=SESSION_1,
            current_loc=curr_loc,
            result_loc=result_loc,
            action_text="Think about what happened at school today",
            narrative="You think back on the events at St. Michael Academy while sitting in the bedroom.",
            scen_key=HIGH_SCHOOL,
        )
        zone, primary, sub = [p.strip() for p in result.split("➔")]
        assert "kaede" in zone.lower() or "residential" in zone.lower(), \
            f"Zone must stay residential, got: {zone}"
        assert "artem" in primary.lower() or "house" in primary.lower() or "residence" in primary.lower(), \
            f"Primary must stay at Artem's House, got: {primary}"
        # Sub must not be a school-related location
        assert "michael" not in sub.lower() and "academy" not in sub.lower(), \
            f"Sub must not be a school location after anchor rollback, got: {sub}"


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 5: Residential Zone Enforcement — no blind prose override
# ══════════════════════════════════════════════════════════════════════════════

class TestResidentialZoneBlindMatch:
    """Root Cause 5: Blind 'residential district' prose match hijacked non-residential establishments."""

    def test_campus_building_not_overridden_by_residential_prose(self):
        """
        Being at a campus building and having 'residential neighborhood' in narrative prose
        must NOT override the zone to the residential zone.
        """
        curr_loc = "St. Michael Academy ➤ Classroom 2-B ➤ Back Row"
        result_loc = "St. Michael Academy ➤ Classroom 2-B ➤ Back Row"
        result = reconcile_movement_location(
            session_id=SESSION_1,
            current_loc=curr_loc,
            result_loc=result_loc,
            action_text="Listen carefully to the teacher's lecture",
            narrative=(
                "The lesson continues. Outside the window, you can see the residential neighborhood "
                "where most students live. The teacher drones on about algebraic equations."
            ),
            scen_key=HIGH_SCHOOL,
        )
        zone = result.split("➔")[0].strip()
        assert "michael" in zone.lower() or "academy" in zone.lower(), \
            f"Zone must stay at school, not be overridden to residential, got: {zone}"

    def test_actually_at_residential_location_keeps_residential_zone(self):
        """A residential location is correctly kept in the residential zone."""
        curr_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Living Room"
        result_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Living Room"
        result = reconcile_movement_location(
            session_id=SESSION_1,
            current_loc=curr_loc,
            result_loc=result_loc,
            action_text="Sit on the couch and relax",
            narrative="The living room is quiet. The residential neighborhood outside is peaceful.",
            scen_key=HIGH_SCHOOL,
        )
        zone = result.split("➔")[0].strip()
        assert "kaede" in zone.lower() or "residential" in zone.lower(), \
            f"Residential zone must be maintained, got: {zone}"


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 6: process_llm_location_update — save gate prevents DB poisoning
# ══════════════════════════════════════════════════════════════════════════════

class TestDynamicSaveGate:
    """Root Cause 6: process_llm_location_update saved unvalidated chimeras to SQLite."""

    def test_chimera_string_not_saved_as_dynamic(self):
        """
        A chimera location string must be normalized before saving.
        The saved entry must not have a Tier 1 Zone in the primary_name slot.
        """
        import db
        # Process a chimera string
        result = process_llm_location_update(
            session_id=SESSION_1,
            raw_location="Kaede Residential Quarter -> Artem's House -> St. Michael Academy",
            scenario_key=HIGH_SCHOOL,
        )
        # The returned string must be clean
        parts = [p.strip() for p in result.split("➔")]
        assert len(parts) == 3
        zone, primary, sub = parts
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        assert primary.strip().lower() not in zones_index, \
            f"Chimera persisted: primary '{primary}' is a Tier 1 Zone!"
        assert sub.strip().lower() not in zones_index, \
            f"Chimera persisted: sub '{sub}' is a Tier 1 Zone!"

    def test_valid_location_still_saved(self):
        """A valid new location must still be saved to SQLite normally."""
        import db
        result = process_llm_location_update(
            session_id=SESSION_1,
            raw_location="St. Michael Academy -> Student Council Office -> President's Desk",
            scenario_key=HIGH_SCHOOL,
        )
        parts = [p.strip() for p in result.split("➔")]
        assert len(parts) == 3
        # Should not raise and should return a clean string
        assert parts[0] and parts[1] and parts[2]


# ══════════════════════════════════════════════════════════════════════════════
#  Fix 7: parse_tiered_location — post-parse Tier 1 Zone invariant
# ══════════════════════════════════════════════════════════════════════════════

class TestParseTieredLocationZoneInvariant:
    """Root Cause 7: parse_tiered_location had no post-parse invariant for zones embedded in Tier 2/3."""

    def test_chimera_3part_string_resolves_cleanly(self):
        """
        'Kaede Residential Quarter ➔ Artem's House ➔ St. Michael Academy'
        must parse to St. Michael Academy zone with its gateway primary.
        """
        result = parse_tiered_location(
            "Kaede Residential Quarter -> Artem's House -> St. Michael Academy",
            scenario_key=HIGH_SCHOOL,
            session_id=SESSION_1,
        )
        zone, primary, sub = result
        assert zone == "St. Michael Academy", f"Zone should be St. Michael Academy, got: {zone}"
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        assert primary.strip().lower() not in zones_index, \
            f"Primary '{primary}' is a Tier 1 Zone — invariant violated!"

    def test_zone_in_primary_position_gets_promoted(self):
        """If the LLM outputs Zone ➔ Zone ➔ Main Area, the second zone should be promoted."""
        result = parse_tiered_location(
            "St. Michael Academy -> Kaede Residential Quarter -> Main Area",
            scenario_key=HIGH_SCHOOL,
            session_id=SESSION_1,
        )
        zone, primary, sub = result
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        assert primary.strip().lower() not in zones_index, \
            f"Primary '{primary}' is a Tier 1 Zone after parse — invariant violated!"

    def test_valid_3part_location_unchanged(self):
        """A correct 3-tier string must parse without modification."""
        result = parse_tiered_location(
            "St. Michael Academy -> Student Council Office -> President's Desk",
            scenario_key=HIGH_SCHOOL,
            session_id=SESSION_1,
        )
        zone, primary, sub = result
        assert "michael" in zone.lower() or "academy" in zone.lower()
        assert "council" in primary.lower() or "office" in primary.lower()

    def test_residential_location_parses_correctly(self):
        """A residential location must stay in the residential zone."""
        result = parse_tiered_location(
            "Kaede Residential Quarter -> Artem's House -> Living Room",
            scenario_key=HIGH_SCHOOL,
            session_id=SESSION_1,
        )
        zone, primary, sub = result
        assert "kaede" in zone.lower() or "residential" in zone.lower(), \
            f"Zone should be residential, got: {zone}"
        assert "artem" in primary.lower() or "house" in primary.lower(), \
            f"Primary should be Artem's House, got: {primary}"


# ══════════════════════════════════════════════════════════════════════════════
#  Integration: Full pipeline end-to-end chimera prevention
# ══════════════════════════════════════════════════════════════════════════════

class TestChimeraEndToEndPrevention:
    """End-to-end tests verifying no chimera survives the full pipeline."""

    def test_reconcile_movement_to_school_from_house_returns_school(self):
        """Moving from residential to school must produce a clean school location."""
        curr_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Main Area"
        result_loc = "St. Michael Academy ➤ Entrance Foyer & Shoe Lockers ➤ Main Area"
        result = reconcile_movement_location(
            session_id=SESSION_1,
            current_loc=curr_loc,
            result_loc=result_loc,
            action_text="Head toward St. Michael Academy for morning classes",
            narrative="You leave the residential neighborhood and walk toward the academy.",
            scen_key=HIGH_SCHOOL,
        )
        zone = result.split("➔")[0].strip()
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        primary = result.split("➔")[1].strip()
        assert "michael" in zone.lower() or "academy" in zone.lower(), \
            f"Should arrive at academy zone, got: {zone}"
        assert primary.strip().lower() not in zones_index, \
            f"Primary '{primary}' is a Tier 1 Zone — chimera in result!"

    def test_reconcile_non_movement_at_house_stays_at_house(self):
        """Non-movement while at Artem's House must keep location unchanged."""
        curr_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Living Room"
        result_loc = "Kaede Residential Quarter ➤ Artem's House ➤ Living Room"
        result = reconcile_movement_location(
            session_id=SESSION_1,
            current_loc=curr_loc,
            result_loc=result_loc,
            action_text="Chat with Artem about today's lesson",
            narrative="You and Artem sit together in the living room talking.",
            scen_key=HIGH_SCHOOL,
        )
        parts = [p.strip() for p in result.split("➔")]
        assert len(parts) == 3
        zone, primary, sub = parts
        zones_index = _build_session_zone_index(SESSION_1, HIGH_SCHOOL)
        assert primary.strip().lower() not in zones_index, \
            f"Primary '{primary}' is a Tier 1 Zone — chimera in result!"
        assert "kaede" in zone.lower() or "residential" in zone.lower(), \
            f"Should stay at residential zone, got: {zone}"
