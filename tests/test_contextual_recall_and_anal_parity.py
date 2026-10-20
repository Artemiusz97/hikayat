import pytest
from mechanics.social.persona import (
    transition_anal_experience,
    merge_anal_states,
    enforce_intimacy_safeguard_invariants,
    generate_dynamic_intimate_experience,
    generate_past_intimate_history,
    format_intimate_profile_sections,
    format_milestone_memory,
    ANAL_INTIMACY_STATES,
    NPC_ANAL_RECEIVE_KEYWORDS,
    NPC_ANAL_GIVE_KEYWORDS,
    ANAL_KEYWORDS,
)
from mechanics.social.genealogy import (
    _retrieve_contextual_memories,
    build_topic_aware_npc_context,
)
from game_engine.state.reducers import _evaluate_npc_milestones


def test_transition_anal_experience():
    assert transition_anal_experience("inexperienced", "anal_give") == "has_done_anal"
    assert transition_anal_experience("inexperienced", "anal_receive") == "has_received_anal"
    assert transition_anal_experience("has_done_anal", "anal_receive") == "has_done_and_received_anal"
    assert transition_anal_experience("has_received_anal", "anal_give") == "has_done_and_received_anal"
    assert transition_anal_experience("has_done_and_received_anal", "anal_give") == "has_done_and_received_anal"
    assert transition_anal_experience("has_done_and_received_anal", "anal_receive") == "has_done_and_received_anal"


def test_merge_anal_states():
    # Never downgrade experience
    assert merge_anal_states("has_done_anal", "inexperienced") == "has_done_anal"
    assert merge_anal_states("has_received_anal", "inexperienced") == "has_received_anal"
    assert merge_anal_states("has_done_anal", "has_received_anal") == "has_done_and_received_anal"
    assert merge_anal_states("has_received_anal", "has_done_anal") == "has_done_and_received_anal"
    assert merge_anal_states("has_done_and_received_anal", "inexperienced") == "has_done_and_received_anal"


def test_enforce_intimacy_safeguard_invariants_anal():
    # Virgin contact with memories mentioning anal receive
    app_virgin = {
        "intercourse_experience": "virgin",
        "intimate_memories": ["Engaged in deep anal penetration with player"],
    }
    safe_virgin = enforce_intimacy_safeguard_invariants(app_virgin)
    assert safe_virgin["anal_experience"] == "has_received_anal"
    assert safe_virgin["intercourse_experience"] == "virgin"  # Virginity intact!

    # Virgin contact with memory mentioning giving anal
    app_virgin_give = {
        "intercourse_experience": "virgin",
        "intimate_memories": ["Fucked his partner anally with a strap-on"],
    }
    safe_give = enforce_intimacy_safeguard_invariants(app_virgin_give)
    assert safe_give["anal_experience"] == "has_done_anal"
    assert safe_give["intercourse_experience"] == "virgin"


def test_generate_dynamic_intimate_experience():
    exp_high = generate_dynamic_intimate_experience(hash_val=100, openness="Shameless")
    assert "anal" in exp_high
    assert exp_high["anal"] in ANAL_INTIMACY_STATES

    exp_chaste = generate_dynamic_intimate_experience(hash_val=100, openness="Prude / Modest")
    assert "anal" in exp_chaste
    assert exp_chaste["anal"] in ANAL_INTIMACY_STATES


def test_generate_past_intimate_history_multi_act_anal():
    # Generate past intimate history with anal experience
    history_dict = generate_past_intimate_history(
        hash_val=42,
        gender="female",
        intercourse="non_virgin",
        oral="has_done_and_received_oral",
        manual="has_done_and_received_manual",
        anal="has_received_anal",
        openness="Bold",
        scenario="fantasy",
    )
    assert history_dict is not None
    entries = history_dict.get("entries", [])
    assert len(entries) > 0
    # At least one entry should synthesize anal intimacy or multi-act description
    combined_hist = " ".join(entries).lower()
    assert any(w in combined_hist for w in ("anal", "backdoor", "received", "intercourse", "oral"))


def test_format_intimate_profile_sections_anal():
    appearance = {
        "breast_size": "Large D-Cup",
        "intercourse_experience": "virgin",
        "oral_experience": "has_done_oral",
        "manual_experience": "has_received_manual",
        "anal_experience": "has_received_anal",
        "anal_revealed": True,
        "intimate_revealed": True,
        "intercourse_revealed": True,
        "oral_revealed": True,
        "manual_revealed": True,
        "demeanor_revealed": True,
        "dynamic_revealed": True,
        "openness_revealed": True,
    }
    sections = format_intimate_profile_sections(appearance, gender="female")
    assert "anatomy" in sections
    anatomy_sec = "\n".join(sections["anatomy"])
    assert "• **Anal Intimacy**: Has Received" in anatomy_sec
    # Ensure Anal Intimacy comes after Manual Intimacy
    assert anatomy_sec.index("Manual Intimacy") < anatomy_sec.index("Anal Intimacy")


def test_evaluate_npc_milestones_tier1_anal():
    app_dict = {
        "intercourse_experience": "virgin",
        "oral_experience": "inexperienced",
        "manual_experience": "inexperienced",
        "anal_experience": "inexperienced",
    }
    res = _evaluate_npc_milestones(
        npc_name="Lyra",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="anal_receive",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[{"label": "took him anal"}],
        narrative_text="Lyra gasped as they engaged in backdoor intimacy.",
        overall_check_success=True,
        is_player_romantic_action=False,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Lyra",
    )
    # Check 7-tuple return contract
    assert len(res) == 7
    new_mem, current_intercourse, current_oral, current_manual, track, is_intimate_act, delta_boost = res

    assert "Engaged in anal intimacy" in new_mem or "Lyra" in new_mem
    assert current_intercourse == "virgin"  # Virginity strictly preserved!
    assert app_dict["anal_experience"] == "has_received_anal"
    assert app_dict["anal_revealed"] is True
    assert app_dict["underwear_revealed"] is True
    assert is_intimate_act is True


def test_evaluate_npc_milestones_tier2_anal_safety_net():
    app_dict = {
        "intercourse_experience": "virgin",
        "oral_experience": "inexperienced",
        "manual_experience": "inexperienced",
        "anal_experience": "inexperienced",
    }
    # Player performs an anal act without LLM milestone_ev, caught by Tier 2 safety net
    res = _evaluate_npc_milestones(
        npc_name="Lyra",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[{"label": "penetrated her ass"}],
        narrative_text="They experienced anal penetration together for the first time.",
        overall_check_success=True,
        is_player_romantic_action=False,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Lyra",
    )
    assert len(res) == 7
    new_mem, current_intercourse, current_oral, current_manual, track, is_intimate_act, delta_boost = res

    assert current_intercourse == "virgin"  # Pure anal does not break vaginal virginity!
    assert app_dict["anal_experience"] == "has_received_anal"
    assert app_dict["anal_revealed"] is True


def test_contextual_memory_recall_zero_token_bloat():
    # Generate 10 memories
    memories = [
        f"Shared memorable event number {i} with Lyra" for i in range(1, 11)
    ]
    # Memory 1 is an older memory:
    memories[0] = "Shared their first tender kiss in the campus library under the moonlight"

    # Case 1: Player asks about older event ("remember when we kissed in the library")
    query = "Do you remember when we kissed in the campus library?"
    retrieved = _retrieve_contextual_memories(query, memories, max_recent=3, max_recalled=2)

    # Invariant: Never exceed 5 items
    assert len(retrieved) <= 5
    # Recalled older moment must be present with banner prefix
    assert any("[RECALLED PAST MOMENT]:" in item and "library" in item for item in retrieved)
    # The last 3 recent memories must still be present
    assert memories[-1] in retrieved
    assert memories[-2] in retrieved
    assert memories[-3] in retrieved

    # Case 2: Player action without mention of past memories -> exactly 5 most recent
    neutral_query = "Walk forward and examine the crystal statue"
    retrieved_neutral = _retrieve_contextual_memories(neutral_query, memories, max_recent=3, max_recalled=2)
    assert len(retrieved_neutral) == 5
    assert retrieved_neutral == memories[-5:]
    assert not any("[RECALLED PAST MOMENT]:" in item for item in retrieved_neutral)


def test_build_topic_aware_npc_context_recall():
    contact = {
        "name": "Evelyn",
        "track": "romantic",
        "relations": {},
        "appearance": {
            "intimate_memories": [
                "Shared their first kiss under the willow tree at midnight",
                "Shared a romantic date at the lakeside",
                "Confessed feelings on the rooftop",
                "Shared a tender embrace in the rain",
                "Shared an intimate kiss in the hallway",
                "Shared a passionate embrace in the royal garden",
            ]
        }
    }
    # Evelyn has 6 romantic memories.
    # Player mentions the willow tree:
    actions = [{"label": "Do you still remember our kiss under the willow tree?"}]
    context = build_topic_aware_npc_context(contact=contact, actions=actions)

    assert "[ESTABLISHED SHARED MEMORIES WITH PLAYER - Evelyn]" in context
    assert "[RECALLED PAST MOMENT]: Shared their first kiss under the willow tree" in context
    # Recent items must also be intact
    assert "Shared a passionate embrace in the royal garden" in context


def test_female_anal_biological_invariants():
    # 1. Dynamic generation for females across multiple seeds
    for h in range(1, 200, 7):
        exp = generate_dynamic_intimate_experience(hash_val=h, openness="Shameless", gender="female")
        assert exp["anal"] in ("inexperienced", "has_received_anal"), f"Female rolled invalid anal state: {exp['anal']}"
        assert exp["anal"] != "has_done_anal"
        assert exp["anal"] != "has_done_and_received_anal"

    # 2. Invariant normalizer clamps invalid female anal states
    app_female_done = {
        "gender": "female",
        "intercourse_experience": "virgin",
        "anal_experience": "has_done_anal",
    }
    normalized = enforce_intimacy_safeguard_invariants(app_female_done, gender="female")
    assert normalized["anal_experience"] == "has_received_anal"

    app_female_both = {
        "gender": "female",
        "intercourse_experience": "non_virgin",
        "anal_experience": "has_done_and_received_anal",
    }
    normalized_both = enforce_intimacy_safeguard_invariants(app_female_both, gender="female")
    assert normalized_both["anal_experience"] == "has_received_anal"

    # 3. Transition anal experience preserves female invariant
    assert transition_anal_experience("inexperienced", "anal_give", gender="female") == "inexperienced"
    assert transition_anal_experience("inexperienced", "anal_receive", gender="female") == "has_received_anal"
    assert transition_anal_experience("has_received_anal", "anal_give", gender="female") == "has_received_anal"


def test_male_and_female_past_history_anal_roles():
    # Female past history must synthesize 'received anal', never 'performed anal'
    fem_hist = generate_past_intimate_history(
        hash_val=88,
        gender="female",
        intercourse="virgin",
        oral="inexperienced",
        manual="inexperienced",
        anal="has_received_anal",
        openness="Bold",
        scenario="high_school_drama"
    )
    assert fem_hist is not None
    combined_fem = " ".join(fem_hist["entries"]).lower()
    assert "received anal" in combined_fem
    assert "performed anal" not in combined_fem

    # Male with female partner can give anal ('performed anal')
    male_hist_done = generate_past_intimate_history(
        hash_val=99,
        gender="male",
        intercourse="non_virgin",
        oral="inexperienced",
        manual="inexperienced",
        anal="has_done_anal",
        openness="Bold",
        scenario="high_school_drama"
    )
    assert male_hist_done is not None
    combined_male_done = " ".join(male_hist_done["entries"]).lower()
    assert "performed anal" in combined_male_done

    # Male who receives anal must have a male partner
    male_hist_rec = generate_past_intimate_history(
        hash_val=105,
        gender="male",
        intercourse="virgin",
        oral="inexperienced",
        manual="inexperienced",
        anal="has_received_anal",
        openness="Bold",
        scenario="high_school_drama"
    )
    assert male_hist_rec is not None
    combined_male_rec = " ".join(male_hist_rec["entries"]).lower()
    assert "received anal" in combined_male_rec


def test_manual_and_anal_history_synthesis_no_dropping():
    # Su-bin Vance's exact case: virgin intercourse, inexperienced oral, manual + anal
    hist = generate_past_intimate_history(
        hash_val=42,
        gender="female",
        intercourse="virgin",
        oral="inexperienced",
        manual="has_done_and_received_manual",
        anal="has_received_anal",
        openness="Bold",
        scenario="high_school_drama"
    )
    assert hist is not None
    entries = hist["entries"]
    assert len(entries) > 0
    combined = " ".join(entries).lower()
    # BOTH manual foreplay AND anal intimacy MUST be present
    assert "manual foreplay" in combined or "manual" in combined
    assert "anal" in combined
    assert "received anal" in combined
    assert "performed anal" not in combined
