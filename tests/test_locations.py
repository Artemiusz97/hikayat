import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mechanics.world.locations.core import (
    is_movement_action,
    extract_movement_destination,
    parse_tiered_location,
    _resolve_reverse_hierarchy,
    is_incongruous_container
)


def test_movement_intent_with_purpose_clause():
    action1 = "Head toward St. Michael Academy to investigate campus rumors"
    assert is_movement_action(action1) is True


def test_incongruous_container_guards():
    assert is_incongruous_container("Artem's House", "St. Michael Academy", session_id=1, scenario_key="high_school_drama") is True
    assert is_incongruous_container("Artem's House", "Street", session_id=1, scenario_key="high_school_drama") is True


def test_parse_tiered_location_demotion_guards():
    z, p, s = parse_tiered_location("Kaede Residential Quarter ➔ Artem's House ➔ St. Michael Academy", scenario_key="high_school_drama", session_id=1)
    assert z == "St. Michael Academy"
    assert p == "Entrance Foyer & Shoe Lockers"
    assert s == "Main Area"
