"""
Automated Pytest Suite for Hikayat Narrative & Turn Lifecycle Simulator.

Tests:
1. NLU Intent Benchmark: Evaluates intent categorization and target extraction accuracy.
2. Choice Generator Hygiene: Verifies choice count (>= 3), deduplication, and DC bounds [0..20].
3. Collective Entity Invariant: Auditor catches collective/plural nouns in session or contacts.
4. Player Action Scraping Guard: Auditor detects player action/inventory theft in contact descriptions.
5. Ghost/Departed NPC Invariant: Auditor detects resurrection of departed NPCs.
6. Multi-Archetype Turn Journeys: Batch runs across all 4 archetypes with zero violations.
7. Memory Stress Mode: Multi-turn prompt cache stability and quest preservation.
8. Deterministic Seed Consistency: Identical seeds produce identical traces.
"""
import pytest
import json
import db
from tests.simulators.narrative import (
    NarrativeSimulator,
    NarrativeInvariantAuditor,
    NarrativeFuzzer,
    NarrativeActorAI,
    NarrativeAction,
)
from mechanics.narrative.intent import classify_action_intent, IntentContext, IntentCategory
from game_engine.choices_cleaner import sanitize_and_diversify_choices


@pytest.mark.unit
class TestNarrativeSimulation:

    def test_nlu_intent_benchmark_clean(self):
        """Verify NLU benchmark correctly classifies core actions and filters collective targets."""
        sim = NarrativeSimulator(seed=101)
        res = sim.run_intent_mode(samples=30, scenario="high_school_drama", fuzz_mode="clean")

        assert res["total_samples"] == 30
        assert res["failed"] == 0, f"Intent benchmark failed on samples: {res['failures']}"
        assert res["pass_rate"] == 100.0

    def test_procedural_choice_hygiene_and_dc_bounds(self):
        """Verify choice cleaner maintains >= 3 choices, clamps DCs [0..20], and eliminates duplicates."""
        sim = NarrativeSimulator(seed=202)
        res = sim.run_choices_mode(scenarios=["high_school_drama", "fantasy"], iterations=10)

        assert res["total_evaluations"] == 20
        assert res["violations"] == 0, f"Choice hygiene violations detected: {res['details']}"
        assert res["clean_rate"] == 100.0

    def test_auditor_catches_collective_entity_leak(self):
        """Verify auditor catches collective nouns in dialogue_partner, current_npcs, or contacts."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")

        corrupt_session = {
            "dialogue_partner": "students",  # Illegal
            "current_npcs_json": json.dumps([{"name": "the patrons"}]),  # Illegal
        }
        corrupt_contacts = [
            {"name": "cluster of students", "basic_info": {}}  # Illegal
        ]

        violations = auditor._audit_entities_and_contacts(
            turn=1,
            session=corrupt_session,
            player_char={"name": "Artemiusz"},
            contacts=corrupt_contacts,
        )

        categories = [v.category for v in violations]
        assert categories.count("INVALID_ENTITY_TYPE") >= 3

    def test_auditor_catches_stolen_player_action(self):
        """Verify auditor catches contact descriptions containing stolen player actions."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")

        stolen_contacts = [
            {
                "name": "Mila Vance",
                "basic_info": {
                    "description": "He adjusts his newsboy cap and scans the room, greeting Mila."
                }
            }
        ]

        violations = auditor._audit_entities_and_contacts(
            turn=1,
            session={"dialogue_partner": "Mila Vance", "current_npcs_json": "[]"},
            player_char={"name": "Artemiusz"},
            contacts=stolen_contacts,
        )

        assert any("stolen from player action" in v.message or "newsboy cap" in v.message for v in violations)

    def test_auditor_catches_departed_npc_resurrection(self):
        """Verify auditor catches departed NPCs that linger in current_npcs or dialogue_partner."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")

        session_with_departed = {
            "dialogue_partner": "Gareth",
            "current_npcs_json": json.dumps([{"name": "Gareth"}, {"name": "Mila"}]),
        }

        violations = auditor._audit_ghost_summoning(
            turn=2,
            session=session_with_departed,
            departed_npcs=["Gareth"],
        )

        assert any(v.category == "GHOST_SUMMONING" for v in violations)
        assert any("Gareth" in v.message for v in violations)

    def test_multi_archetype_turn_journeys(self):
        """Verify multi-turn journeys execute cleanly across all 4 archetypes."""
        sim = NarrativeSimulator(seed=303)
        report = sim.run_batch(
            simulations=4,
            scenario="high_school_drama",
            archetype="all",
            fuzz_mode="clean",
            max_turns=5,
            fail_fast=True,
        )

        assert report.total_journeys == 4
        assert report.crashes == 0
        assert report.total_violations == 0
        assert report.successful_journeys == 4
        assert report.avg_turns_per_journey == 5.0

    def test_memory_stress_preserves_story_quest(self):
        """Verify long-horizon memory stress preserves active quests across simulated turns."""
        sim = NarrativeSimulator(seed=404)
        res = sim.run_memory_stress_mode(turns=15, scenario="high_school_drama")

        assert res["turns_simulated"] == 15
        assert res["active_quest_preserved"] is True
        assert res["violations"] == 0

    def test_deterministic_seed_consistency(self):
        """Verify that identical random seeds produce identical action histories."""
        sim = NarrativeSimulator()
        r1 = sim.simulate_journey(1, scenario="high_school_drama", archetype="cautious_explorer", seed=99999, max_turns=4)
        r2 = sim.simulate_journey(1, scenario="high_school_drama", archetype="cautious_explorer", seed=99999, max_turns=4)

        assert r1.total_turns == r2.total_turns
        assert len(r1.history) == len(r2.history)
        for h1, h2 in zip(r1.history, r2.history):
            assert h1["action"] == h2["action"]
            assert h1["intent"] == h2["intent"]
            assert h1["partner"] == h2["partner"]

    def test_auditor_catches_agency_fact_deletion(self):
        """Verify auditor catches dropped mechanical state facts (agency preservation)."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")

        mock_outcome = {
            "character_outcomes": [
                {
                    "name": "Artemiusz",
                    "items_gained": ["Ancient Grimoire"],
                    "gold_change": -50,
                }
            ]
        }

        orig_prose = "You pay 50 gold and receive the Ancient Grimoire from the merchant with a proud smile."
        # Rewritten prose dropped the Grimoire!
        rewritten_prose = "You pay 50 gold with a proud smile."

        violations = auditor.audit_agency_preservation(
            turn=1,
            original_prose=orig_prose,
            audited_prose=rewritten_prose,
            outcome=mock_outcome,
        )

        assert len(violations) >= 1
        assert any(v.category == "AGENCY_VIOLATION" for v in violations)
        assert any("ancient grimoire" in v.message for v in violations)

    def test_conversational_dialogue_exit_and_reentry(self):
        """Verify simulated journeys cleanly transition between dialogue and ambient exploration."""
        sim = NarrativeSimulator(seed=555)
        res = sim.simulate_journey(
            journey_id=1,
            scenario="fantasy",
            archetype="chaotic_provocateur",
            fuzz_mode="clean",
            max_turns=6,
        )

        assert res.success is True
        assert res.total_turns == 6
        assert len(res.violations) == 0
        # Verify both dialogue and non-dialogue actions occur in history
        partners = [step["partner"] for step in res.history]
        assert any(p is not None for p in partners)

    def test_adversarial_stress_withstands_injections(self):
        """Verify adversarial stress withstands corrupt entities and noise without crashing."""
        sim = NarrativeSimulator(seed=777)
        res = sim.simulate_journey(
            journey_id=1,
            scenario="high_school_drama",
            archetype="conversationalist",
            fuzz_mode="adversarial_stress",
            max_turns=5,
        )

        assert res.error is None
        assert res.total_turns == 5
        # Zero critical entity leaks or crashes
        critical_violations = [v for v in res.violations if v.severity == "CRITICAL"]
        assert len(critical_violations) == 0

    def test_intent_benchmark_realistic_fuzzing(self):
        """Verify NLU intent benchmark achieves 100% precision under realistic player mannerisms and quotes."""
        sim = NarrativeSimulator(seed=888)
        res = sim.run_intent_mode(samples=30, scenario="high_school_drama", fuzz_mode="realistic_llm")

        assert res["total_samples"] == 30
        assert res["failed"] == 0, f"Realistic fuzz failures: {res['failures']}"
        assert res["pass_rate"] == 100.0

    def test_intent_benchmark_adversarial_stress(self):
        """Verify NLU intent benchmark achieves 100% precision under adversarial props and noise injection."""
        sim = NarrativeSimulator(seed=999)
        res = sim.run_intent_mode(samples=30, scenario="high_school_drama", fuzz_mode="adversarial_stress")

        assert res["total_samples"] == 30
        assert res["failed"] == 0, f"Adversarial fuzz failures: {res['failures']}"
        assert res["pass_rate"] == 100.0

    def test_auditor_catches_departed_npc_first_name_in_choices(self):
        """Verify auditor flags choices targeting a departed NPC by first name."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        choices = [
            {"label": "Speak with Eldrin about the ancient map", "stat": "CHA", "requirement": 5},
            {"label": "Check your inventory quietly", "stat": "FREE", "requirement": 0},
            {"label": "Examine the tavern hearth", "stat": "PER", "requirement": 4},
        ]
        violations = auditor._audit_choice_hygiene(
            turn=1,
            cleaned_choices=choices,
            departed_npcs=["Eldrin the Wise"],
        )
        assert len(violations) == 1
        assert violations[0].category == "CHOICE_DEADLOCK"
        assert "Eldrin" in violations[0].message

    def test_auditor_catches_missing_party_companion(self):
        """Verify memory budget audit flags companions dropped from party_npcs_json."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        sim = NarrativeSimulator()
        fuzzer = NarrativeFuzzer()
        sess_dict, _ = fuzzer.create_test_session(scenario_key="fantasy")
        sid = sess_dict["id"]

        try:
            # Set Lyra as companion in DB
            db.set_session_party_npcs(sid, [{"name": "Lyra"}])

            # Audit expecting Lyra AND Bob (Bob is missing!)
            violations = auditor.audit_memory_and_prompt_budget(
                turn=1,
                session_id=sid,
                zones_content={"zone_static": "test"},
                companions=["Lyra", "Bob"],
            )
            assert any(v.category == "MEMORY_BUDGET_OVERFLOW" and "Bob" in v.message for v in violations)
            assert not any("Lyra" in v.message for v in violations)
        finally:
            with db.get_conn() as conn:
                for table in (
                    "session_locations", "lorebook", "school_directory", "contacts", "factions",
                    "quests", "quest_waypoints", "session_clues", "phone_messages",
                    "phone_appointments", "phone_gossip_feed", "commitments_ledger", "session_digests",
                    "session_chronicles", "npc_memories", "session_members", "inventory",
                ):
                    try:
                        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                    except Exception:
                        pass
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))

    def test_actor_ai_free_action_flag_and_string_npcs(self):
        """Verify actor AI accurately sets is_free_action and handles string NPC presence."""
        actor = NarrativeActorAI(archetype="conversationalist", seed=123)
        choices = [
            {"label": "Ask about the quest", "stat": "CHA", "requirement": 8},
            {"label": "Take a breath", "stat": "FREE", "requirement": 0},
        ]
        action = actor.choose_action(session={"dialogue_partner": None}, choices=choices, scenario="fantasy")
        # Best choice should be evaluated and is_free_action set correctly
        assert isinstance(action.is_free_action, bool)

        # Free form prose with string NPCs
        prose = actor.generate_free_form_prose(
            location="Marketplace",
            current_npcs=["Eldrin the Wise", "Lyra"],
            scenario="fantasy",
        )
        assert isinstance(prose, str)
        assert len(prose) > 10

    def test_auditor_catches_ghost_first_name_in_presence_and_partner(self):
        """Verify auditor catches departed NPC resurrected by first name in current_npcs or dialogue_partner."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        session_with_departed = {
            "dialogue_partner": "Eldrin",
            "current_npcs_json": json.dumps([{"name": "Eldrin"}, {"name": "Lyra"}]),
        }
        violations = auditor._audit_ghost_summoning(
            turn=1,
            session=session_with_departed,
            departed_npcs=["Eldrin the Wise"],
        )
        assert len(violations) >= 2
        assert all(v.category == "GHOST_SUMMONING" for v in violations)

    def test_auditor_catches_gold_gain_desync(self):
        """Verify auditor detects unreconciled gold gains mentioned in prose."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        outcome = {
            "outcome_narrative": "The guild receptionist smiles warmly. You receive 100 gold as a bounty reward.",
            "character_outcomes": [
                {"name": "Artemiusz", "gold_change": 0}
            ]
        }
        violations = auditor._audit_prose_state_parity(
            turn=1,
            outcome=outcome,
            player_char={"name": "Artemiusz"},
        )
        assert any(v.category == "PROSE_STATE_DESYNC" and "100 gold gained" in v.message for v in violations)

    def test_actor_ai_fallback_custom_prose_string_target(self):
        """Verify actor AI choose_action with empty choices and string current_npcs handles target safely."""
        actor = NarrativeActorAI(archetype="cautious_explorer", seed=42)
        action = actor.choose_action(
            session={"current_location": "Courtyard"},
            choices=[],
            current_npcs=["Chloe", "Mila Vance"],
            scenario="high_school_drama",
        )
        assert action.action_type == "custom_prose"
        assert action.target_entity == "Chloe"

    def test_fuzz_prose_deduplicates_leading_pronoun(self):
        """Verify realistic_llm fuzzing never produces duplicate 'I I' pronouns."""
        fuzzer = NarrativeFuzzer(fuzz_mode="realistic_llm", seed=42)
        base = "I examine the desk."
        # Generate multiple fuzzed outputs to hit the dressing prefix roll
        for _ in range(50):
            res = fuzzer.fuzz_prose(base)
            assert "I I " not in res, f"Duplicate pronoun detected in: {res}"
            assert "I i " not in res, f"Duplicate pronoun detected in: {res}"

    def test_auditor_catches_item_grant_desync(self):
        """Verify auditor catches unreconciled item grants in narrative prose."""
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        outcome = {
            "outcome_narrative": "Behind the stone altar, you find an Ancient Amulet tucked in the dust.",
            "character_outcomes": [
                {"name": "Artemiusz", "items_gained": []}
            ]
        }
        violations = auditor._audit_prose_state_parity(
            turn=1,
            outcome=outcome,
            player_char={"name": "Artemiusz"},
        )
        assert any(
            v.category == "PROSE_STATE_DESYNC" and "Ancient Amulet" in v.message
            for v in violations
        )

    def test_state_facts_extraction_handles_hp_and_gold_delta(self):
        from tests.simulators.narrative.auditor import _extract_state_facts
        outcome = {
            "character_outcomes": [
                {
                    "name": "Artemiusz",
                    "hp_change": 0,
                    "hp_delta": -12,
                    "gold_change": 0,
                    "gold_delta": 45,
                }
            ]
        }
        facts = _extract_state_facts(outcome)
        assert "12" in facts
        assert "45" in facts

    def test_effective_first_name_strips_titles_and_articles(self):
        """Verify _get_effective_first_name strips title prefixes and does not flag common words in choices."""
        from tests.simulators.narrative.auditor import _get_effective_first_name
        assert _get_effective_first_name("The Merchant") == "merchant"
        assert _get_effective_first_name("Sir Gareth") == "gareth"
        assert _get_effective_first_name("Dr. Vance") == "vance"
        assert _get_effective_first_name("The") == ""

        # Verify choice hygiene does not flag "Search the room" as interaction with "The Merchant"
        auditor = NarrativeInvariantAuditor(scenario_key="fantasy")
        choices = [
            {"label": "Search the room carefully", "stat": "PER", "requirement": 6},
            {"label": "Examine the heavy stone door", "stat": "PER", "requirement": 8},
            {"label": "Force the lock open", "stat": "STR", "requirement": 14},
        ]
        violations = auditor._audit_choice_hygiene(
            turn=1,
            cleaned_choices=choices,
            departed_npcs=["The Merchant"],
        )
        assert len(violations) == 0, f"False positive choice deadlock flagged: {violations}"

    def test_mp_cost_deduction_in_mock_outcome(self):
        """Verify generate_mock_outcome deducts mp_cost in character_outcomes."""
        fuzzer = NarrativeFuzzer(fuzz_mode="clean")
        player_char = {"name": "Artemiusz", "user_id": 123, "mp": 20}
        outcome = fuzzer.generate_mock_outcome(
            session={"scenario": "fantasy"},
            player_char=player_char,
            action_text="Cast Arcane Missile",
            mp_cost=8,
        )
        user_outcome = outcome["character_outcomes"][0]
        assert user_outcome["mp_change"] == -8
        assert user_outcome["mp_delta"] == -8

    def test_actor_ai_custom_prose_prioritizes_dialogue_partner(self):
        """Verify fallback custom prose prioritizes active dialogue_partner over first room NPC."""
        actor = NarrativeActorAI(archetype="conversationalist", seed=42)
        action = actor.choose_action(
            session={"current_location": "Courtyard", "dialogue_partner": "Mila Vance"},
            choices=[],
            current_npcs=["Chloe", "Mila Vance"],
            scenario="high_school_drama",
        )
        assert action.action_type == "custom_prose"
        assert action.target_entity == "Mila Vance"

    def test_auditor_catches_ambient_bystander_dialogue_hijack(self):
        """Verify auditor catches ambient bystanders who hijack dialogue without interacting directly."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")
        prev_session = {"dialogue_partner": "Mia Yamada", "dialogue_partners": ["Mia Yamada"]}
        curr_session = {"dialogue_partner": "Mia Yamada", "dialogue_partners": ["Mia Yamada", "Coach Kai Nakamura"]}
        outcome = {
            "outcome_narrative": "Alice talks with Mia about track.",
            "next_narrative": "Across the gym, Coach Kai Nakamura barked orders at the freshmen team.",
            "npcs_present": [{"name": "Mia Yamada"}, {"name": "Coach Kai Nakamura"}],
        }
        actions = [{"label": "Ask Mia about practice", "stat": "CHA"}]

        violations = auditor._audit_dialogue_lifecycle_and_bystanders(
            turn=2,
            session=curr_session,
            outcome=outcome,
            cleaned_choices=[],
            previous_session=prev_session,
            actions=actions,
        )

        categories = [v.category for v in violations]
        assert "DIALOGUE_LIFECYCLE_BREACH" in categories
        assert any("Ambient bystander 'Coach Kai Nakamura' hijacked" in v.message for v in violations)

    def test_auditor_catches_uninvited_follower_sublocation(self):
        """Verify auditor catches ambient bystanders following player across sub-location transitions."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")
        prev_session = {
            "dialogue_partner": "Mia Yamada",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [{"name": "Mia Yamada"}, {"name": "Coach Kai Nakamura"}],
        }
        curr_session = {
            "dialogue_partner": "Mia Yamada",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ East Alcove",
            "current_npcs": [{"name": "Mia Yamada"}, {"name": "Coach Kai Nakamura"}],
        }
        outcome = {
            "npcs_present": [{"name": "Mia Yamada"}, {"name": "Coach Kai Nakamura"}],
        }
        actions = [{"label": "Suggest heading over to the East Alcove with Mia to chat in private"}]

        violations = auditor._audit_dialogue_lifecycle_and_bystanders(
            turn=2,
            session=curr_session,
            outcome=outcome,
            cleaned_choices=[],
            previous_session=prev_session,
            actions=actions,
            old_loc="Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            new_loc="Westlake Academy ➔ Main Gymnasium ➔ East Alcove",
        )

        categories = [v.category for v in violations]
        assert "DIALOGUE_LIFECYCLE_BREACH" in categories
        assert any("Uninvited bystander 'Coach Kai Nakamura' followed" in v.message for v in violations)

    def test_auditor_catches_premature_dialogue_drop(self):
        """Verify auditor catches premature dialogue exit when player did not leave and partner is present."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")
        prev_session = {"dialogue_partner": "Mia Yamada", "dialogue_partners": ["Mia Yamada"]}
        curr_session = {"dialogue_partner": None, "dialogue_partners": []}
        outcome = {
            "outcome_narrative": "Alice asks Mia a question. She smiles.",
            "next_narrative": "\"Of course,\" Mia replies warmly.",
            "npcs_present": [{"name": "Mia Yamada"}],
        }
        actions = [{"label": "Ask Mia about her tournament memories", "stat": "CHA"}]

        violations = auditor._audit_dialogue_lifecycle_and_bystanders(
            turn=2,
            session=curr_session,
            outcome=outcome,
            cleaned_choices=[],
            previous_session=prev_session,
            actions=actions,
        )

        categories = [v.category for v in violations]
        assert "DIALOGUE_LIFECYCLE_BREACH" in categories
        assert any("dropped prematurely without player exiting conversation" in v.message for v in violations)

    def test_auditor_catches_dialogue_choice_skill_check_violations(self):
        """Verify auditor catches dialogue choices lacking DCs, redundant openers, or non-free exits."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")
        curr_session = {"dialogue_partner": "Mia Yamada"}
        invalid_choices = [
            {"label": "Speak with Mia Yamada", "stat": "NONE", "requirement": 0},  # Illegal redundant starter
            {"label": "Ask Mia about the rumors", "stat": "FREE", "requirement": 0},  # Illegal missing DC
            {"label": "Politely say goodbye and leave", "stat": "CHA", "requirement": 8},  # Illegal non-free exit
        ]

        violations = auditor._audit_dialogue_lifecycle_and_bystanders(
            turn=2,
            session=curr_session,
            outcome={"npcs_present": [{"name": "Mia Yamada"}]},
            cleaned_choices=invalid_choices,
        )

        categories = [v.category for v in violations]
        assert "DIALOGUE_LIFECYCLE_BREACH" in categories
        assert any("Redundant dialogue starter" in v.message for v in violations)
        assert any("lacks skill check" in v.message for v in violations)
        assert any("requires a skill check" in v.message for v in violations)

    def test_auditor_allows_legitimate_chime_in(self):
        """Verify auditor does NOT flag legitimate quest NPCs or conversational interjectors chiming in."""
        auditor = NarrativeInvariantAuditor(scenario_key="high_school_drama")
        prev_session = {"dialogue_partner": "Mia Yamada", "dialogue_partners": ["Mia Yamada"]}
        curr_session = {"dialogue_partner": "Mia Yamada", "dialogue_partners": ["Mia Yamada", "Sofia Anderson"]}
        outcome = {
            "outcome_narrative": "Alice and Mia are talking.",
            "next_narrative": "Sofia Anderson rushes over breathlessly. \"Alice, Mia, you need to see this!\" she gasps.",
            "npcs_present": [{"name": "Mia Yamada"}, {"name": "Sofia Anderson"}],
        }
        actions = [{"label": "Listen to Mia's answer", "stat": "CHA"}]

        violations = auditor._audit_dialogue_lifecycle_and_bystanders(
            turn=2,
            session=curr_session,
            outcome=outcome,
            cleaned_choices=[
                {"label": "Ask Sofia what she found", "stat": "CHA", "requirement": 6},
                {"label": "Thank them and step away", "stat": "NONE", "requirement": 0},
            ],
            previous_session=prev_session,
            actions=actions,
        )

        assert len(violations) == 0, f"Unexpected violation on legitimate chime-in: {violations}"

    def test_cross_locale_stat_bracket_parsing(self, capsys):
        """Verify stat brackets ([STR], [CHA], [INT], [PER], [AGI]), choice parsing,
        and UTF-8 console output function across all 5 languages (en, ms, id, ja, zh).
        """
        from scripts.simulate_narrative import safe_print

        multilingual_inputs = [
            # English
            {"label": "[STR] Force the heavy iron door open", "requirement": 10},
            # Malay
            {"label": "[STR] Robohkan pintu pagar besi dengan sekuat tenaga", "requirement": 8},
            # Indonesian
            {"label": "[CHA] Yakinkan penjaga pos untuk memberi jalan masuk", "requirement": 6},
            # Japanese
            {"label": "[INT] 古代の碑文を慎重に解読する", "requirement": 9},
            # Chinese
            {"label": "[AGI] 悄悄潜行穿过守卫的巡逻区", "requirement": 7},
            # Indonesian / Malay PER
            {"label": "[PER] Mengamati tanda-tanda jebakan di sepanjang koridor", "requirement": 6},
        ]

        cleaned = sanitize_and_diversify_choices(multilingual_inputs, scenario="fantasy")

        # Verify all choices were parsed and cleaned
        assert len(cleaned) >= 5

        # Check stat extraction and label cleaning
        stats_by_label_token = {
            "heavy iron door": ("STR", 10),
            "Robohkan pintu": ("STR", 8),
            "penjaga pos": ("CHA", 6),
            "古代の碑文": ("INT", 9),
            "悄悄潜行": ("AGI", 7),
            "tanda-tanda": ("PER", 6),
        }

        for c in cleaned:
            lbl = c.get("label", "")
            # Ensure stat bracket was stripped from the clean label
            assert not lbl.startswith("["), f"Stat bracket was not stripped from label: '{lbl}'"
            for token, (expected_stat, expected_req) in stats_by_label_token.items():
                if token in lbl:
                    assert c.get("stat") == expected_stat, f"Mismatch stat for '{lbl}': expected {expected_stat}, got {c.get('stat')}"
                    assert c.get("requirement") == expected_req, f"Mismatch req for '{lbl}': expected {expected_req}, got {c.get('requirement')}"

        # Verify string inputs also extract stats correctly
        raw_strings = [
            "[STR] Bash the reinforced gate",
            "[CHA] Pujuk pengawal pintu",
            "[INT] 呪文の構造を分析する",
            "[AGI] 翻越坚固的城墙",
        ]
        cleaned_strings = sanitize_and_diversify_choices(raw_strings, scenario="fantasy")
        assert len(cleaned_strings) >= 4
        assert any(c.get("stat") == "STR" and "Bash the reinforced gate" in c.get("label") for c in cleaned_strings)
        assert any(c.get("stat") == "CHA" and "Pujuk pengawal pintu" in c.get("label") for c in cleaned_strings)
        assert any(c.get("stat") == "INT" and "呪文の構造を分析する" in c.get("label") for c in cleaned_strings)
        assert any(c.get("stat") == "AGI" and "翻越坚固的城墙" in c.get("label") for c in cleaned_strings)

        # Test NarrativeActorAI can process and choose among multilingual options
        actor = NarrativeActorAI(archetype="bold_adventurer", seed=777)
        chosen = actor.choose_action(session={}, choices=cleaned, current_npcs=[], turn=1, scenario="fantasy")
        assert chosen.action_type == "choice"
        assert chosen.stat in ("STR", "AGI", "CHA", "INT", "PER")
        assert chosen.requirement > 0

        # Verify safe_print console output doesn't crash on multilingual text
        for c in cleaned:
            safe_print(f"  [Choice Locale Test] {c.get('stat')} DC {c.get('requirement')}: {c.get('label')}")

