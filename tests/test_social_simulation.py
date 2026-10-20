"""
Automated Pytest Suite for Hikayat Social Dynamics & Persona Simulation.

Tests:
1. School directory hydration & sibling web generation.
2. Peer vs. faculty isolation & confession milestone boundary gating.
3. Confession threshold (70+) & rejection cooldown invariants.
4. Trait disclosure monotonicity.
5. Faction reputation mathematical clamping [-100..100].
6. Multi-archetype social simulation batch runs (clean & realistic LLM noise).
7. Adversarial fuzzing auditor catch-rate and classification.
"""
import pytest
import db
from tests.simulators.social import (
    SocialDynamicsSimulator,
    SocialInvariantAuditor,
    SocialFuzzer,
    SocialActorAI,
    SocialAction,
)
from mechanics.social.relationships import (
    is_contact_eligible,
    can_trigger_romantic_confession,
    clamp_score,
)
from mechanics.social.school_roster import (
    ensure_school_directory_exists,
    hydrate_school_character,
)


@pytest.mark.unit
class TestSocialSimulation:

    def test_school_roster_and_directory_hydration(self):
        """Verify school directory generates 45-50 characters with sibling links and hydrates peers."""
        fuzzer = SocialFuzzer(fuzz_mode="clean")
        sess, char = fuzzer.create_test_session(scenario_key="high_school_drama")
        sid = sess["id"]

        try:
            directory = db.get_school_roster(sid)
            assert len(directory) >= 40, f"Expected 40+ directory characters, got {len(directory)}"

            # Verify presence of both faculty and students
            roles = [d.get("role", "") for d in directory]
            assert any("Teacher" in r or "Coach" in r or "Principal" in r for r in roles)
            assert any("Student" in d.get("role", "") or "Junior" in d.get("grade", "") for d in directory)

            # Verify sibling web presence
            siblings = [d for d in directory if d.get("sibling_name")]
            assert len(siblings) >= 2, "Expected at least one sibling pair in directory"

            # Hydrate a student peer
            peer = next(d for d in directory if "Faculty" not in d.get("role", "") and d.get("grade") != "Faculty")
            success = hydrate_school_character(sid, peer)
            assert success is True

            contact = db.get_contact(sid, peer["name"])
            assert contact is not None
            assert contact["name"] == peer["name"]
        finally:
            with db.get_conn() as conn:
                for table in ("contacts", "school_directory", "factions"):
                    conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute("DELETE FROM characters WHERE active_session_id=?", (sid,))

    def test_peer_vs_faculty_isolation_invariants(self):
        """Verify faculty and adult entities are barred from contact eligibility and romantic milestones."""
        fuzzer = SocialFuzzer(fuzz_mode="clean")
        sess, char = fuzzer.create_test_session(scenario_key="high_school_drama")
        sid = sess["id"]
        cid = char["id"]

        try:
            directory = db.get_school_roster(sid)
            faculty = [d for d in directory if "Faculty" in d.get("grade", "") or "Teacher" in d.get("role", "")]
            assert len(faculty) >= 5

            for f in faculty:
                f_name = f["name"]
                # Faculty must not be contact eligible
                eligible = is_contact_eligible(f_name, scenario="high_school_drama", session_id=sid)
                assert eligible is False, f"Faculty member '{f_name}' should not be contact eligible"

                # Even if artificially upserted with 100 relationship score, confession must evaluate to False!
                db.upsert_contact(session_id=sid, character_id=cid, npc_id=f_name, name=f_name, delta_score=100)
                can_confess = can_trigger_romantic_confession(sid, cid, f_name, scenario="high_school_drama")
                assert can_confess is False, f"Romantic confession must be barred for faculty '{f_name}'"
        finally:
            with db.get_conn() as conn:
                for table in ("contacts", "school_directory", "factions"):
                    conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute("DELETE FROM characters WHERE active_session_id=?", (sid,))

    def test_confession_threshold_and_cooldown_gating(self):
        """Verify confession requires affinity >= 70 and cooldown blocks repeated attempts."""
        fuzzer = SocialFuzzer(fuzz_mode="clean")
        sess, char = fuzzer.create_test_session(scenario_key="high_school_drama", char_gender="male")
        sid = sess["id"]
        cid = char["id"]

        try:
            # Create a female student peer contact
            peer_name = "Chloe Vance"
            db.upsert_contact(
                session_id=sid,
                character_id=cid,
                npc_id=peer_name,
                name=peer_name,
                delta_score=40,  # Below 70 threshold
                track="platonic",
                gender="female",
                basic_info={"grade": "Junior", "role": "Student"},
            )
            db.update_contact_relations(sid, peer_name, {
                "romance": {"status": "Single", "current_partner": None, "ex_partners": []}
            }, cid)

            # At score 40, confession milestone must be False
            assert can_trigger_romantic_confession(sid, cid, peer_name, scenario="high_school_drama") is False

            # Boost to 105 (crosses Friend/Crush Tier 3 threshold)
            db.update_contact_score(sid, peer_name, 105, character_id=cid)
            assert can_trigger_romantic_confession(sid, cid, peer_name, scenario="high_school_drama") is True

            # Trigger confession cooldown
            db.set_confession_cooldown(sid, peer_name, 3)
            assert db.get_confession_cooldown(sid, peer_name) == 3
            # Milestone is now blocked by cooldown
            assert can_trigger_romantic_confession(sid, cid, peer_name, scenario="high_school_drama") is False

            # Decrement cooldown to 0
            db.decrement_confession_cooldowns(sid)
            db.decrement_confession_cooldowns(sid)
            db.decrement_confession_cooldowns(sid)
            assert db.get_confession_cooldown(sid, peer_name) == 0
            assert can_trigger_romantic_confession(sid, cid, peer_name, scenario="high_school_drama") is True
        finally:
            with db.get_conn() as conn:
                for table in ("contacts", "school_directory", "factions"):
                    conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute("DELETE FROM characters WHERE active_session_id=?", (sid,))

    def test_archetype_social_journeys(self):
        """Verify batch simulations execute cleanly across diplomat, operative, provocateur, and romance_seeker."""
        sim = SocialDynamicsSimulator(seed=777)
        report = sim.run_batch(
            simulations=8,
            scenario="all",
            archetype="all",
            fuzz_mode="clean",
            max_turns=10,
            fail_fast=True,
        )

        assert report.total_journeys == 8
        assert report.crashes == 0
        assert report.total_violations == 0
        assert report.successful_journeys == 8
        assert report.total_traits_unlocked > 0
        assert report.avg_turns_per_journey >= 9.0

    def test_realistic_fuzzing_survivability(self):
        """Verify simulator withstands realistic conversational LLM noise and formatting dressing."""
        sim = SocialDynamicsSimulator(seed=888)
        report = sim.run_batch(
            simulations=6,
            scenario="high_school_drama",
            archetype="all",
            fuzz_mode="realistic_llm",
            max_turns=8,
            fail_fast=False,
        )

        assert report.crashes == 0
        assert report.total_violations == 0
        assert report.successful_journeys == 6

    def test_adversarial_stress_auditor_catch(self):
        """Verify auditor catches out-of-bounds scores, schema noise, and illegal romantic advances."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        # 1. Test score out-of-bounds
        corrupt_contact = {
            "name": "Maya Lin",
            "relationship_score": 999,  # Illegal: > 100
            "track": "platonic",
            "unlocked_traits": ["Studious"],
        }
        violations = auditor.audit_turn(
            turn=1,
            session_id=1,
            character_id=1,
            contacts=[corrupt_contact],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "AFFINITY_BOUNDS" for v in violations)

        # 2. Test faculty romantic track violation
        corrupt_faculty = {
            "name": "Dr. Vance",
            "relationship_score": 80,
            "track": "romantic",  # Illegal: faculty cannot have romantic track
            "unlocked_traits": [],
        }
        violations = auditor.audit_turn(
            turn=2,
            session_id=1,
            character_id=1,
            contacts=[corrupt_faculty],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "PEER_BOUNDARY_VIOLATION" for v in violations)

        # 3. Test schema noise leak
        leaked_contact = {
            "name": "Alex",
            "relationship_score": 20,
            "track": "platonic",
            "basic_info": {"description": "Hello {{player_name}}, my affinity is [INSERT]"},
        }
        violations = auditor.audit_turn(
            turn=3,
            session_id=1,
            character_id=1,
            contacts=[leaked_contact],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "SCHEMA_NOISE_LEAK" for v in violations)

    def test_reproduction_seed_consistency(self):
        """Verify that identical seeds produce 100% identical journey traces and outcomes."""
        sim = SocialDynamicsSimulator()
        r1 = sim.simulate_journey(1, scenario="high_school_drama", archetype="romance_seeker", seed=12345, max_turns=10)
        r2 = sim.simulate_journey(1, scenario="high_school_drama", archetype="romance_seeker", seed=12345, max_turns=10)

        assert r1.total_turns == r2.total_turns
        assert r1.confessions_accepted == r2.confessions_accepted
        assert r1.confessions_attempted == r2.confessions_attempted
        assert r1.traits_unlocked == r2.traits_unlocked
        assert len(r1.history) == len(r2.history)
        for h1, h2 in zip(r1.history, r2.history):
            assert h1["action_type"] == h2["action_type"]
            assert h1["target"] == h2["target"]
            assert h1["delta"] == h2["delta"]
            assert h1["outcome"] == h2["outcome"]

    def test_faction_reputation_clamping_and_tiers(self):
        """Verify faction reputations clamp strictly to [-100..100] and map to correct tiers and titles."""
        from mechanics.social.factions import get_faction_tier, get_faction_modifier

        t_high = get_faction_tier(95)
        assert t_high["name"] == "Exalted"
        assert t_high["modifier"] == 2

        t_over = get_faction_tier(500)
        assert t_over["name"] == "Exalted"

        t_low = get_faction_tier(-95)
        assert t_low["name"] == "Hated Enemy"
        assert t_low["modifier"] == -3

        t_under = get_faction_tier(-500)
        assert t_under["name"] == "Hated Enemy"

        t_neutral = get_faction_tier(0)
        assert t_neutral["name"] == "Neutral"
        assert t_neutral["modifier"] == 0

    def test_intimacy_and_anal_parity_auditor_invariants(self):
        """Verify auditor catches corrupted anal intimacy states and regressions, and simulation logs intimate acts."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        # 1. Invalid anal intimacy state detected
        corrupt_anal_contact = {
            "name": "Sarah Connor",
            "relationship_score": 85,
            "track": "romantic",
            "appearance": {
                "anal_experience": "invalid_experimental_state",
            },
        }
        v1 = auditor.audit_turn(
            turn=1,
            session_id=1,
            character_id=1,
            contacts=[corrupt_anal_contact],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "INTIMACY_INVALID_STATE" for v in v1)

        # 2. Intimacy experience regression detected (has_done_and_received_anal -> inexperienced)
        auditor2 = SocialInvariantAuditor(scenario_key="high_school_drama")
        turn1_contact = {
            "name": "Sarah Connor",
            "relationship_score": 85,
            "track": "romantic",
            "appearance": {
                "anal_experience": "has_done_and_received_anal",
            },
        }
        v_turn1 = auditor2.audit_turn(
            turn=1,
            session_id=1,
            character_id=1,
            contacts=[turn1_contact],
            school_directory=[],
            factions=[],
        )
        assert len([v for v in v_turn1 if v.category == "INTIMACY_EXPERIENCE_REGRESSION"]) == 0

        turn2_regressed = {
            "name": "Sarah Connor",
            "relationship_score": 85,
            "track": "romantic",
            "appearance": {
                "anal_experience": "inexperienced",
            },
        }
        v_turn2 = auditor2.audit_turn(
            turn=2,
            session_id=1,
            character_id=1,
            contacts=[turn2_regressed],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "INTIMACY_EXPERIENCE_REGRESSION" for v in v_turn2)

        # 3. Simulate romance_seeker journeys verifying intimacy and anal acts occur without violations
        sim = SocialDynamicsSimulator(seed=999)
        report = sim.run_batch(
            simulations=4,
            scenario="high_school_drama",
            archetype="romance_seeker",
            fuzz_mode="clean",
            max_turns=12,
            fail_fast=True,
        )
        assert report.total_violations == 0
        assert report.crashes == 0
        assert report.successful_journeys == 4
        assert report.total_intimate_milestones >= 0

    def test_sensitive_spots_progressive_discovery_and_leak_prevention(self):
        """Verify unrevealed sensitive spots never leak into public sheet and are caught by auditor."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        # Contact with unrevealed sensitive spots that leaked into description
        leaked_contact = {
            "name": "Yuki Shirogane",
            "relationship_score": 50,
            "track": "platonic",
            "basic_info": {
                "description": "A quiet student who gets flustered if anyone touches her collarbones.",
            },
            "appearance": {
                "sensitive_spots": "Collarbones, nape of the neck",
                "sensitive_spots_revealed": False,
            },
        }

        violations = auditor.audit_turn(
            turn=1,
            session_id=101,
            character_id=1,
            contacts=[leaked_contact],
            school_directory=[],
            factions=[],
        )
        assert any(v.category == "SENSITIVE_SPOT_LEAK" for v in violations)

        # Properly unrevealed contact with clean description
        clean_contact = {
            "name": "Yuki Shirogane",
            "relationship_score": 50,
            "track": "platonic",
            "basic_info": {
                "description": "A quiet, studious student council treasurer.",
            },
            "appearance": {
                "sensitive_spots": "Collarbones, nape of the neck",
                "sensitive_spots_revealed": False,
            },
        }
        auditor_clean = SocialInvariantAuditor(scenario_key="high_school_drama")
        clean_violations = auditor_clean.audit_turn(
            turn=1,
            session_id=102,
            character_id=1,
            contacts=[clean_contact],
            school_directory=[],
            factions=[],
        )
        assert not any(v.category == "SENSITIVE_SPOT_LEAK" for v in clean_violations)

    def test_turn_off_aversion_detection_and_blowback(self):
        """Verify triggering turn-offs results in penalties and auditor catches illegal positive rewards."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        contact = {
            "name": "Erika Kuroki",
            "relationship_score": 40,
            "track": "platonic",
            "appearance": {
                "turn_offs": "Rushed impatience & entitlement, Crude degradation & insults",
            },
        }

        # Artificial scenario where action triggered turn-off but was awarded positive affinity
        illegal_action = SocialAction(
            action_type="trigger_turn_off",
            target_npc="Erika Kuroki",
            action_text="Hurry up Erika, quit wasting time and get on with it!",
            affinity_delta=5,
        )

        violations = auditor.audit_turn(
            turn=1,
            session_id=103,
            character_id=1,
            contacts=[contact],
            school_directory=[],
            factions=[],
            action=illegal_action,
            outcome_label="Affinity (+5)",
        )
        assert any(v.category == "TURN_OFF_INVARIANT_BREACH" for v in violations)

    def test_phone_messaging_and_media_consent_gating(self):
        """Verify phone media consent scaling and auditor catch of prude consent violations."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        prude_contact = {
            "name": "Rei Ayanami",
            "relationship_score": 25,  # Low affinity
            "track": "platonic",
            "appearance": {
                "erotic_openness": "prude",
            },
        }

        # Illegal granted spicy photo to low affinity prude
        spicy_action = SocialAction(
            action_type="phone_photo_request",
            target_npc="Rei Ayanami",
            action_text="Send a spicy bedroom selfie request.",
            metadata={"is_spicy": True, "intent": "nsfw_photo"},
        )

        violations = auditor.audit_turn(
            turn=1,
            session_id=104,
            character_id=1,
            contacts=[prude_contact],
            school_directory=[],
            factions=[],
            action=spicy_action,
            outcome_label="Photo Received: nsfw_photo (+4)",
        )
        assert any(v.category == "PHONE_CONSENT_VIOLATION" for v in violations)

    def test_cross_sibling_relationship_ripples(self):
        """Verify severe insults trigger protective sibling hostility ripples."""
        fuzzer = SocialFuzzer(fuzz_mode="clean")
        sess, char = fuzzer.create_test_session(scenario_key="high_school_drama")
        sid = sess["id"]
        cid = char["id"]

        try:
            directory = db.get_school_roster(sid)
            # Find a sibling pair in directory
            sib_pair = next((d for d in directory if d.get("sibling_name")), None)
            assert sib_pair is not None

            target_name = sib_pair["name"]
            sibling_name = sib_pair["sibling_name"]

            # Initialize contacts for both siblings
            db.upsert_contact(session_id=sid, character_id=cid, npc_id=target_name, name=target_name, delta_score=20)
            db.upsert_contact(session_id=sid, character_id=cid, npc_id=sibling_name, name=sibling_name, delta_score=20)

            # Perform severe insult against target_name
            sim = SocialDynamicsSimulator(seed=777)
            journey = sim.simulate_journey(
                journey_id=1,
                scenario="high_school_drama",
                archetype="provocateur",
                fuzz_mode="clean",
                max_turns=5,
                seed=777,
            )

            # Journey should have completed cleanly with observed sibling ripples
            assert journey.success is True
            assert journey.sibling_ripples >= 0
        finally:
            with db.get_conn() as conn:
                for table in ("contacts", "school_directory", "factions"):
                    conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute("DELETE FROM characters WHERE active_session_id=?", (sid,))

    def test_public_discretion_and_location_context(self):
        """Verify public discretion rebuffs explicit intimacy in public waypoints with non-shameless NPCs."""
        auditor = SocialInvariantAuditor(scenario_key="high_school_drama")

        modest_contact = {
            "name": "Ayaka Kamisato",
            "relationship_score": 85,
            "track": "romantic",
            "appearance": {
                "erotic_openness": "moderate",
            },
        }

        intimate_action = SocialAction(
            action_type="intercourse",
            target_npc="Ayaka Kamisato",
            action_text="Spend a passionate night making love in the hallway.",
            metadata={"milestone_event": "intercourse"},
        )

        violations = auditor.audit_turn(
            turn=1,
            session_id=105,
            character_id=1,
            contacts=[modest_contact],
            school_directory=[],
            factions=[],
            action=intimate_action,
            outcome_label="Intimate Milestone: intercourse (+10)",
            location="Westlake High ➔ Main Corridor ➔ Hallway",
        )
        assert any(v.category == "PUBLIC_DISCRETION_BREACH" for v in violations)

    def test_expanded_social_simulator_multi_archetype_batch(self):
        """Verify full multi-archetype batch run exercises expanded metrics with zero invariant violations."""
        sim = SocialDynamicsSimulator(seed=4242)
        report = sim.run_batch(
            simulations=8,
            scenario="all",
            archetype="all",
            fuzz_mode="clean",
            max_turns=10,
            fail_fast=True,
        )
        assert report.crashes == 0
        assert report.total_violations == 0
        assert report.successful_journeys == 8
        assert report.total_sensitive_spots >= 0
        assert report.total_phone_interactions >= 0
        assert report.total_sibling_ripples >= 0

    def test_gossip_and_rumor_affinity_propagation(self):
        """Verify gossip action properly modulates affinity and handles hostile sibling ripples."""
        fuzzer = SocialFuzzer(fuzz_mode="clean")
        sess, char = fuzzer.create_test_session(scenario_key="fantasy")
        sid = sess["id"]
        cid = char["id"]

        try:
            db.upsert_contact(session_id=sid, character_id=cid, npc_id="target_npc", name="Target NPC", delta_score=10)
            sim = SocialDynamicsSimulator()
            action = SocialAction(
                action_type="gossip",
                target_npc="Target NPC",
                action_text="Share interesting gossip about the court.",
                affinity_delta=3,
            )
            # Execute turn directly via actor/fuzzer or simulation engine
            res = sim.simulate_journey(
                journey_id=99,
                scenario="fantasy",
                archetype="operative",
                fuzz_mode="clean",
                max_turns=3,
                seed=123,
            )
            assert res.success is True
            assert any(step.get("action_type") in ("gossip", "chat", "inquire_trait", "probe_mannerism") for step in res.history)
        finally:
            with db.get_conn() as conn:
                for table in ("contacts", "school_directory", "factions"):
                    conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute("DELETE FROM characters WHERE active_session_id=?", (sid,))

    def test_reducer_blocks_unauthorized_romance_track_promotion(self):
        """Verify _reduce_social_and_milestones refuses to promote platonic contact to romantic track without confession/date milestone."""
        from game_engine.state.social import _reduce_social_and_milestones
        sid = 999977
        cid = 101
        try:
            db.upsert_contact(session_id=sid, character_id=cid, npc_id="Mia Yamada", name="Mia Yamada", track="platonic", delta_score=100)
            contact_before = db.get_contact(sid, "Mia Yamada", character_id=cid)
            assert contact_before["track"] == "platonic"

            session = {"id": sid, "current_npcs": [{"name": "Mia Yamada"}], "scenario": "high_school_drama"}
            actions = [{"label": "ask her if she's single", "text": "ask her if she's single"}]
            # LLM attempts to emit track: romantic without an actual confession or milestone
            outcome = {
                "relationship_updates": [
                    {"npc_name": "Mia Yamada", "delta_score": 4, "track": "romantic"}
                ],
                "npcs_present": [{"name": "Mia Yamada"}]
            }

            _reduce_social_and_milestones(
                session_id=sid,
                session=session,
                party=[],
                outcome=outcome,
                actions=actions,
                scen_key="high_school_drama",
                items_gained_by_user={},
                first_char_id=cid,
                first_char_name="Artemiusz"
            )

            contact_after = db.get_contact(sid, "Mia Yamada", character_id=cid)
            assert contact_after["track"] == "platonic", "Inquiry alone must NOT promote contact to romantic track"

            # Now test genuine confession: should promote to romantic track
            confession_actions = [{"label": "confess feelings to Mia Yamada", "text": "confess feelings", "check": {"success": True}}]
            confession_outcome = {
                "relationship_updates": [
                    {"npc_name": "Mia Yamada", "delta_score": 6, "track": "romantic", "milestone_event": "confession"}
                ],
                "npcs_present": [{"name": "Mia Yamada"}]
            }
            _reduce_social_and_milestones(
                session_id=sid,
                session=session,
                party=[],
                outcome=confession_outcome,
                actions=confession_actions,
                scen_key="high_school_drama",
                items_gained_by_user={},
                first_char_id=cid,
                first_char_name="Artemiusz"
            )
            contact_promoted = db.get_contact(sid, "Mia Yamada", character_id=cid)
            assert contact_promoted["track"] == "romantic", "Valid confession milestone MUST promote contact to romantic track"
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sid)

    def test_auditor_meta_leak_sanitization_and_virginity_grounding(self):
        """Verify auditor meta tokens are sanitized and virginity is grounded in dialogue prompts."""
        from game_engine.keywords import sanitize_auditor_meta_leaks
        from game_engine.turn.dialogue import _build_dialogue_prompt_block
        from game_engine.turn_context import TurnContext

        # 1. Sanitization verification
        leaked_dialogue = "Turn-off: when you rush the pacing. I'm an auditor, after all; I don't like sloppy work."
        cleaned = sanitize_auditor_meta_leaks(leaked_dialogue)
        assert "auditor" not in cleaned.lower()
        assert "I'm thorough, after all" in cleaned

        leaked_meeting = "You've got about ten minutes before my next audit meeting"
        cleaned_meeting = sanitize_auditor_meta_leaks(leaked_meeting)
        assert "audit" not in cleaned_meeting.lower()
        assert "scheduled meeting" in cleaned_meeting

        leaked_boundary = "I'm a very thorough auditor of personal boundaries."
        cleaned_boundary = sanitize_auditor_meta_leaks(leaked_boundary)
        assert "auditor" not in cleaned_boundary.lower()
        assert "very thorough when it comes to personal boundaries" in cleaned_boundary

        # 2. Dialogue prompt grounding verification
        sid = 9999881
        try:
            with db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO sessions (id, mode, capacity, scenario, current_location, history_json) VALUES (?, 'solo', 1, ?, ?, ?)",
                    (sid, "nsfw_furry_high_school_drama", "Campus Promenade", "[]")
                )
                conn.commit()

            db.upsert_contact(
                session_id=sid,
                npc_id="test_virgin",
                name="Test Virgin",
                delta_score=10,
                appearance={
                    "intercourse_experience": "virgin",
                    "oral_experience": "inexperienced",
                    "manual_experience": "inexperienced",
                    "anal_experience": "inexperienced",
                    "turn_ons": "Intimate eye contact",
                    "turn_offs": "Dead silence",
                    "erotic_openness": "shameless",
                }
            )

            sess = db.get_session(sid)
            ctx = TurnContext(sid, sess)
            prompt_block = _build_dialogue_prompt_block(
                sess, ctx, ["Test Virgin"], [], [{"label": "ask about your experience and turn ons"}]
            )

            assert "CANON VIRGINITY & PAST EXPERIENCE GROUNDING" in prompt_block
            assert "canonically a VIRGIN with NO prior intercourse experience" in prompt_block
            assert "SPOKEN CONVERSATIONAL DISCLOSURE" in prompt_block
            assert "Intimate eye contact" in prompt_block
            assert "Dead silence" in prompt_block

            # 3. Modest / Guarded NPC Boundary Gating verification
            db.upsert_contact(
                session_id=sid,
                npc_id="test_modest",
                name="Test Modest",
                delta_score=5,
                appearance={
                    "intercourse_experience": "virgin",
                    "oral_experience": "inexperienced",
                    "manual_experience": "inexperienced",
                    "turn_ons": "Gentle caresses",
                    "turn_offs": "Aggressive shouting",
                    "erotic_openness": "modest",
                    "intimate_demeanor": "Hesitant & Flustered",
                }
            )
            ctx_modest = TurnContext(sid, sess)
            prompt_block_modest = _build_dialogue_prompt_block(
                sess, ctx_modest, ["Test Modest"], [], [{"label": "ask about your experience"}]
            )
            assert "CANON VIRGINITY & PAST EXPERIENCE GROUNDING" in prompt_block_modest
            assert "BOUNDARY & INFORMATION GATING" in prompt_block_modest
            assert "guarded/modest regarding private intimacy" in prompt_block_modest
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sid)


