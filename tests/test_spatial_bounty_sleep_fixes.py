import pytest
import re
import namegen
from mechanics.system.time_engine import (
    scenario_allows_camp_sleep,
    get_location_sleep_context,
    is_sleep_action,
    is_nap_action,
    apply_sleep_rest,
    apply_nap_rest,
)
from mechanics.world.waypoints.matching import (
    can_waypoint_match_via_npc_presence,
    is_waypoint_npc_present_in_scene,
)
from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices
from mechanics.world.mobility import has_narrative_continuity_bridge


# ==============================================================================
# 1. Modern Namelists & Procedural Acronym HQ Names
# ==============================================================================

def test_modern_namelist_for_anomalous_incursions():
    """Guarantee 1: Anomalous Incursions characters use modern namelists, not fantasy."""
    for i in range(50):
        name = namegen.generate_person_name("anomalous_incursions", seed=1000 + i)
        assert name, "Failed to generate name"
        # Should not pull from fantasy surname lists
        assert "Voidwalker" not in name
        assert "Mandragoran" not in name
        assert "Shadowrend" not in name
        assert "Bloodmoon" not in name
        # Must have both first and last name
        parts = name.split()
        assert len(parts) >= 2, f"Expected full name, got: {name}"


def test_agency_and_hq_naming_acronym_style():
    """Guarantee 2: Agency names are punchy (2-4 words) and HQs use crisp acronyms."""
    for i in range(20):
        agency = namegen.generate_agency_name(hash_val=2000 + i)
        words = agency.split()
        assert len(words) <= 4, f"Agency name too long: {agency} ({len(words)} words)"

        hq_name = namegen.generate_agency_hq_name(hash_val=2000 + i)
        assert hq_name.endswith(" HQ"), f"HQ name must end with ' HQ': {hq_name}"
        assert len(hq_name.split()) <= 3, f"HQ name too verbose: {hq_name}"

        priv_agency = namegen.generate_private_agency_name(hash_val=3000 + i)
        priv_words = priv_agency.split()
        assert len(priv_words) <= 3, f"Private agency too long: {priv_agency}"


def test_monastic_culture_weighting():
    """Guarantee: Monastic order roster weights favor East/SE/South Asian modern cultures."""
    from mechanics.social.agent_roster import MONASTIC_ORDER_CULTURE_WEIGHTS
    asian_keys = {"japanese", "chinese", "korean", "malay", "vietnamese", "indian"}
    asian_sum = sum(MONASTIC_ORDER_CULTURE_WEIGHTS.get(k, 0) for k in asian_keys)
    assert asian_sum >= 0.70, f"Expected >= 70% Asian culture weighting, got {asian_sum}"


# ==============================================================================
# 2. Strict Pre-Turn Spatial Whitelist
# ==============================================================================

def test_uninvited_npcs_do_not_bridge_across_locations():
    """Guarantee 3: Uninvited dialogue partners or patrons never follow across locations."""
    mock_session = {
        "dialogue_partner": "Astarion Voidwalker",
        "current_npcs": [{"name": "Astarion Voidwalker"}, {"name": "Megan Mandragoran"}],
        "current_location": "zone_agency_hq ➔ loc_hq_main_lobby ➔ sub_hq_entrance",
    }
    old_loc = "zone_agency_hq ➔ loc_hq_main_lobby ➔ sub_hq_entrance"
    new_loc = "zone_agency_hq ➔ loc_hq_main_lobby ➔ sub_hq_terminal"

    # With solo movement action (no escort / no party)
    solo_actions = [{"label": "Step through the secure corridor to the terminal", "text": "head to terminal"}]
    bridge = has_narrative_continuity_bridge(
        "Astarion Voidwalker",
        session=mock_session,
        actions=solo_actions,
        new_loc=new_loc,
    )
    assert bridge is False, "Uninvited dialogue partner should NOT bridge to new location"

    # With explicit escort action, bridge is permitted
    escort_actions = [{"label": "Lead Astarion to the terminal room", "text": "escort Astarion", "target_npc": "Astarion Voidwalker"}]
    bridge_escort = has_narrative_continuity_bridge(
        "Astarion Voidwalker",
        session=mock_session,
        actions=escort_actions,
        new_loc=new_loc,
    )
    assert bridge_escort is True, "Explicitly escorted companion should bridge to new location"


# ==============================================================================
# 3. Location-Locked Quest & Bounty Choices
# ==============================================================================

def test_generic_npc_title_does_not_match_remote_bounties():
    """Guarantee 4: Generic titles like 'Dispatch Officer' cannot trigger site bounties."""
    bounty_target_npc = "Central Aberration Control Initiative Dispatch Officer"
    stage_key = "investigate_anomaly_site"

    can_match = can_waypoint_match_via_npc_presence(bounty_target_npc, stage_key=stage_key)
    assert can_match is False, "Investigation stage should NOT match via generic NPC presence"

    dialogue_stage_key = "report_to_dispatch"
    can_match_dialogue = can_waypoint_match_via_npc_presence(bounty_target_npc, stage_key=dialogue_stage_key)
    assert can_match_dialogue is True, "Dialogue/report stage CAN match via NPC presence"


def test_tag_and_enrich_strips_unverified_bounty_choices_at_wrong_location():
    """Guarantee 4: LLM hallucinated [🎯 BOUNTY] choices at HQ are stripped if bounty is elsewhere."""
    raw_choices = [
        {
            "label": "🎯 [Bounty] Interface with terminal to isolate resonance telemetry",
            "stat": "INT",
            "requirement": 6,
            "is_quest_action": True,
            "intent": "bounty_investigate",
        },
        {
            "label": "Speak with the dispatch officer regarding current alerts",
            "stat": "CHA",
            "requirement": 4,
            "is_quest_action": False,
        }
    ]

    # When no matching waypoints exist at current location (e.g. at HQ while bounty is at Foundry)
    # tag_and_enrich_quest_choices must strip is_quest_action and remove the [🎯 BOUNTY] prefix
    enriched = tag_and_enrich_quest_choices(
        raw_choices,
        session_id=0,
        current_location="zone_agency_hq ➔ loc_hq_main_lobby ➔ sub_hq_entrance",
        allow_fallback=False,
    )

    for c in enriched:
        assert c.get("is_quest_action") is False, f"Expected is_quest_action=False, got: {c}"
        assert not str(c.get("label")).startswith("🎯 [Bounty]"), f"Label still has bounty prefix: {c.get('label')}"


# ==============================================================================
# 4. Sleep Surface Gating & Recovery Rules
# ==============================================================================

def test_sleep_surface_gating_by_scenario():
    """Guarantee 5: Pure fantasy allows camping anywhere; modern/urban requires bed/couch."""
    # Pure fantasy / post-apocalypse allows camp
    assert scenario_allows_camp_sleep("fantasy") is True
    assert scenario_allows_camp_sleep("dark_fantasy") is True
    assert scenario_allows_camp_sleep("nuclear_post_apocalypse") is True

    # Modern, urban, high school, cyberpunk, sci-fi, steampunk DO NOT allow camping
    assert scenario_allows_camp_sleep("anomalous_incursions") is False
    assert scenario_allows_camp_sleep("urban_fantasy") is False
    assert scenario_allows_camp_sleep("high_school_drama") is False
    assert scenario_allows_camp_sleep("slice_of_life") is False
    assert scenario_allows_camp_sleep("cyberpunk") is False
    assert scenario_allows_camp_sleep("sci_fi") is False
    assert scenario_allows_camp_sleep("steampunk") is False


def test_sleep_context_surface_detection():
    """Guarantee 5: Accurately detects bed (1.0), couch (0.5), camp (1.0), and none (0.0)."""
    # 1. Bed at Operative Dormitories
    dorm_ctx = get_location_sleep_context(
        "zone_agency_hq ➔ loc_hq_agent_dormitories ➔ Soundproofed Agent Sleeping Quarters",
        scenario="anomalous_incursions"
    )
    assert dorm_ctx["can_sleep"] is True
    assert dorm_ctx["surface"] == "bed"
    assert dorm_ctx["recovery_ratio"] == 1.0

    # 2. Couch at Lounge
    lounge_ctx = get_location_sleep_context(
        "zone_city_center ➔ loc_office ➔ Breakroom Lounge Couch",
        scenario="anomalous_incursions"
    )
    assert lounge_ctx["can_sleep"] is True
    assert lounge_ctx["surface"] == "couch"
    assert lounge_ctx["recovery_ratio"] == 0.5

    # 3. None at Street / Lobby
    street_ctx = get_location_sleep_context(
        "zone_city_center ➔ loc_civic_plaza ➔ Central Fountain",
        scenario="anomalous_incursions"
    )
    assert street_ctx["can_sleep"] is False
    assert street_ctx["surface"] == "none"
    assert street_ctx["recovery_ratio"] == 0.0

    # 4. False positive exclusion: "Planter Beds" should NOT count as a sleeping bed
    planter_ctx = get_location_sleep_context(
        "zone_school_grounds ➔ Botanical Greenhouse ➔ Orchid Nursery & Planter Beds",
        scenario="high_school_drama"
    )
    assert planter_ctx["can_sleep"] is False
    assert planter_ctx["surface"] == "none"

    # 5. Entrance / Foyer / Porch Guard: standing in the foyer of a dorm or entrance of an apartment
    # must NOT count as a sleeping surface
    foyer_ctx = get_location_sleep_context(
        "C.W.C.A. HQ ➔ Operative Dormitories & Rest Quarters ➔ Barracks Foyer & Keycard Desk",
        scenario="anomalous_incursions"
    )
    assert foyer_ctx["can_sleep"] is False
    assert foyer_ctx["surface"] == "none"

    doorway_ctx = get_location_sleep_context(
        "Residential Suburbs ➔ Walk-Up Studio Apartments ➔ Walk-Up Studio Apartments Entrance Doorway",
        scenario="anomalous_incursions"
    )
    assert doorway_ctx["can_sleep"] is False
    assert doorway_ctx["surface"] == "none"

    # 6. Living Room / Velvet Lounge registers as Sofa/Couch (0.5)
    living_ctx = get_location_sleep_context(
        "Residential Suburbs ➔ Walk-Up Studio Apartments ➔ Living Room & Kitchenette",
        scenario="anomalous_incursions"
    )
    assert living_ctx["can_sleep"] is True
    assert living_ctx["surface"] == "couch"
    assert living_ctx["recovery_ratio"] == 0.5


def test_arrival_waypoint_does_not_match_via_generic_npc():
    """Guarantee 4: Stage 0 arrival waypoints at remote sites cannot complete via Dispatch Officer presence at HQ."""
    wp = {
        "stage_key": "stage_0",
        "stage_label": "Arrive at Ironworks Foundry",
        "completion_trigger": "arrival",
        "target_npc": "C.W.C.A. Dispatch Officer",
    }
    assert can_waypoint_match_via_npc_presence("C.W.C.A. Dispatch Officer", waypoint=wp) is False


def test_nap_action_duration_parsing():
    """Guarantee 5: is_nap_action accurately parses nap duration."""
    assert is_nap_action("Take a 1 hour nap")[0] is True
    assert is_nap_action("Take a 1 hour nap")[1] == 60

    assert is_nap_action("Take a 2 hr nap")[0] is True
    assert is_nap_action("Take a 2 hr nap")[1] == 120

    assert is_nap_action("Power nap on the couch")[0] is True
    assert is_nap_action("Power nap on the couch")[1] == 60

    assert is_nap_action("Inspect the control terminal")[0] is False
