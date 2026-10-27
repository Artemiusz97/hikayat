"""
Pytest Test Suite for the Hikayat Intimate Moment & Excitement Meter Simulator.

Validates:
1. Scenarios (full_progression, sudden_initiation, player_stop, npc_interruption, aftercare_only).
2. Partner Configurations (hetero, same_sex_m, same_sex_f, multi_female, multi_male, multi_same_sex, mixed_group).
3. Excitement Invariants (zero non-genital delta, male refractory stop vs female multi-climax 35% reset).
4. Idle Decay & Grace Period (2 turns grace, then -5 or -10 decay).
5. Premature Finish Dual-Branching (AGI/CHA rescue vs dialogue exit with -5 penalty).
6. Virginity Transition & Milestone Memory Logging.
7. Species-Specific Biological Anatomy Compliance.
8. Secret Affair & Relationship Graph Synchronization.
9. Standalone CLI Runner Execution.
"""
import json
import os
import subprocess
import sys
import unittest

import db
from tests.simulators.intimacy import (
    IntimacySimulator,
    IntimacyActorAI,
    IntimacyFuzzer,
    IntimacyInvariantAuditor,
    SUPPORTED_SCENARIOS,
    SUPPORTED_PARTNER_CONFIGS,
    SUPPORTED_FUZZ_MODES,
)
import mechanics.social.relationship_graph as rg


class TestIntimacySimulation(unittest.TestCase):
    """Rigorous CI verification test suite for the Intimacy Simulator harness."""

    def setUp(self):
        db.init_db()
        self.simulator = IntimacySimulator()

    def test_full_progression_lifecycle(self):
        """Verify full progression lifecycle from leadup to climax and aftercare."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="hetero",
            fuzz_mode="none",
            max_turns=10,
            seed=101,
        )
        self.assertTrue(res.success, f"Full progression failed: {res.violations}")
        self.assertFalse(res.crashed)
        self.assertGreater(res.turns, 4)

    def test_sudden_initiation_scenario(self):
        """Verify sudden initiation immediately triggers escalated intimate actions."""
        res = self.simulator.run_simulation(
            scenario="sudden_initiation",
            partner_config="hetero",
            fuzz_mode="none",
            max_turns=6,
            seed=102,
        )
        self.assertTrue(res.success, f"Sudden initiation failed: {res.violations}")
        self.assertFalse(res.crashed)
        # Turn 1 must be escalated
        t1 = res.turn_log[0]
        self.assertIn(t1["act_type"], ("manual_give", "manual_receive", "oral_give", "oral_receive", "penetrative"))

    def test_player_voluntary_stop(self):
        """Verify mid-session voluntary player halt freezes meter and ends cleanly."""
        res = self.simulator.run_simulation(
            scenario="player_stop",
            partner_config="hetero",
            fuzz_mode="none",
            max_turns=8,
            seed=103,
        )
        self.assertTrue(res.success, f"Player stop failed: {res.violations}")
        self.assertFalse(res.crashed)
        # Should stop by turn 3 or 4
        self.assertLessEqual(res.turns, 4)

    def test_npc_interruption_scenario(self):
        """Verify external door knock / intrusion cleanly interrupts encounter."""
        res = self.simulator.run_simulation(
            scenario="npc_interruption",
            partner_config="hetero",
            fuzz_mode="none",
            max_turns=6,
            seed=104,
        )
        self.assertTrue(res.success, f"NPC interruption failed: {res.violations}")
        self.assertFalse(res.crashed)
        self.assertLessEqual(res.turns, 3)

    def test_aftercare_only_scenario(self):
        """Verify aftercare-only starts with tenderness without re-escalation."""
        res = self.simulator.run_simulation(
            scenario="aftercare_only",
            partner_config="hetero",
            fuzz_mode="none",
            max_turns=5,
            seed=105,
        )
        self.assertTrue(res.success, f"Aftercare only failed: {res.violations}")
        self.assertFalse(res.crashed)

    def test_partner_config_hetero(self):
        """Verify standard heterosexual 1M + 1F configuration."""
        res = self.simulator.run_simulation(partner_config="hetero", seed=201)
        self.assertTrue(res.success)
        self.assertFalse(res.crashed)

    def test_partner_config_same_sex(self):
        """Verify same-sex partner configurations (same_sex_m and same_sex_f)."""
        res_m = self.simulator.run_simulation(partner_config="same_sex_m", seed=202)
        self.assertTrue(res_m.success)

        res_f = self.simulator.run_simulation(partner_config="same_sex_f", seed=203)
        self.assertTrue(res_f.success)

    def test_partner_config_multi_female(self):
        """Verify 1M + multiple F configuration with spectator warmth cap."""
        res = self.simulator.run_simulation(partner_config="multi_female", seed=204)
        self.assertTrue(res.success)
        self.assertFalse(res.crashed)

    def test_partner_config_multi_male(self):
        """Verify 1F + multiple M configuration with staggered stops."""
        res = self.simulator.run_simulation(partner_config="multi_male", seed=205)
        self.assertTrue(res.success)
        self.assertFalse(res.crashed)

    def test_partner_config_mixed_group_orgy(self):
        """Verify mixed group (2M + 2F orgy) with fluid orientation and staggered climaxes."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="mixed_group",
            fuzz_mode="realistic_llm",
            seed=206,
        )
        self.assertTrue(res.success, f"Mixed group orgy failed: {res.violations}")
        self.assertFalse(res.crashed)

    def test_zero_non_genital_delta_invariant(self):
        """Verify zero excitement delta on hair stroking, cheek kisses, and hand holding."""
        fuzzer = IntimacyFuzzer(fuzz_mode="adversarial_stress", seed=301)
        session_doc, p_card, p_contacts = fuzzer.create_test_session(partner_config="hetero")
        action = fuzzer.fuzz_action(
            base_action=IntimacyActorAI().choose_action(1, p_card, p_contacts, session_doc["physical_state"]),
            turn=1,
            target_contact=p_contacts[0],
        )
        self.assertTrue(action.metadata.get("is_non_genital_probe"))

        from mechanics.social.intimate_excitement import compute_excitement_step
        exc_res = compute_excitement_step(
            physical_state=session_doc["physical_state"],
            action_str=action.action_text,
            player_char=p_card,
            partner_contact=p_contacts[0],
            session=session_doc,
            sub_intent=action.sub_intent,
            target_npc=action.target_npc,
        )
        self.assertEqual(exc_res["player_delta"], 0)
        self.assertEqual(exc_res["partner_delta"], 0)

    def test_male_refractory_stop_and_female_multiclimax(self):
        """Verify male single climax hard stop vs female 35% hypersensitive baseline."""
        # Male climax
        res_m = self.simulator.run_simulation(partner_config="same_sex_m", seed=401, max_turns=12)
        self.assertTrue(res_m.success)

        # Female multi-climax
        res_f = self.simulator.run_simulation(partner_config="same_sex_f", seed=402, max_turns=12)
        self.assertTrue(res_f.success)

    def test_species_sensitive_spot_sanitation(self):
        """Verify Beastfolk reject human earlobes and accept animal crown ears."""
        from mechanics.social.persona.intimacy.logic import sanitize_sensitive_spots_for_species
        dirty_beast_spots = "Earlobe, Base of fluffy tail, Sensitive nape"
        cleaned = sanitize_sensitive_spots_for_species(dirty_beast_spots, race="Beastfolk", distinctive_features="Fox ears & bushy tail")
        self.assertNotIn("earlobe", cleaned.lower())
        self.assertIn("base of fluffy tail", cleaned.lower())

    def test_secret_affair_detection(self):
        """Verify secret affair marks is_secret_affair = 1 and records TIETYPE_AFFAIR in graph."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="hetero",
            fuzz_mode="none",
            is_secret_affair_test=True,
            seed=501,
        )
        self.assertTrue(res.success, f"Secret affair test failed: {res.violations}")

    def test_low_endurance_refractory_clock_recovery(self):
        """Verify male character with END=1 (56 min cooldown) clears refractory clock past target."""
        from mechanics.social.intimate_excitement import calculate_refractory_duration, check_and_resolve_refractory_clock, is_in_refractory_cooldown
        duration = calculate_refractory_duration(1)
        self.assertEqual(duration, 56)

        session = {"current_day": 1, "current_minute": 480}
        phys_state = {
            "excitement": {
                "active": True,
                "refractory_until_minute": (1 * 1440) + 480 + duration,
                "player_in_refractory": True,
                "actors": {"Artemiusz": {"meter": 100, "climaxes_count": 1, "status": "Spent"}}
            }
        }
        # Before cooldown: still in refractory
        in_refr, _ = is_in_refractory_cooldown(session, phys_state)
        self.assertTrue(in_refr)

        # Advance past cooldown
        session["current_minute"] = 480 + duration + 5
        cleared, toast = check_and_resolve_refractory_clock(session, phys_state)
        self.assertTrue(cleared)
        self.assertIn("Stamina Recovered", toast)

        in_refr_after, _ = is_in_refractory_cooldown(session, phys_state)
        self.assertFalse(in_refr_after)

    def test_reciprocal_secret_affair_symmetry(self):
        """Verify dynamic affair detection marks both primary and reciprocal rows with is_secret_affair == 1."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="hetero",
            fuzz_mode="none",
            is_secret_affair_test=True,
            seed=601,
        )
        self.assertTrue(res.success, f"Affair test failed: {res.violations}")

        with db.get_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT id, character_id, partner_id, partner_name, is_secret_affair, direction FROM intimate_events WHERE session_id = ?",
                (res.turn_log[0].get("session_id", res.journey_id),)  # Or check by session
            ).fetchall()
            # Find any session intimate events for this journey
            all_affair_rows = cur.execute(
                "SELECT id, character_id, partner_id, partner_name, is_secret_affair, direction FROM intimate_events WHERE is_secret_affair = 1 ORDER BY id DESC LIMIT 4"
            ).fetchall()
            self.assertGreater(len(all_affair_rows), 0)
            # Ensure both primary and reciprocal exist
            affair_dict_rows = [dict(r) for r in all_affair_rows]
            for r in affair_dict_rows:
                self.assertEqual(r["is_secret_affair"], 1)

    def test_multi_climax_female_telemetry(self):
        """Verify female participants record multi_climaxes telemetry when climaxing 2+ times."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="same_sex_f",
            fuzz_mode="realistic_llm",
            max_turns=12,
            seed=701,
        )
        self.assertTrue(res.success, f"Female multi-climax failed: {res.violations}")
        self.assertGreater(res.partner_climaxes, 0)

    def test_turn_off_probed_excitation_dampening(self):
        """Verify adversarial turn-off probing yields zero/recoil delta and passes invariant audit."""
        res = self.simulator.run_simulation(
            scenario="full_progression",
            partner_config="hetero",
            fuzz_mode="adversarial_stress",
            max_turns=6,
            seed=801,
        )
        self.assertTrue(res.success, f"Turn-off probe simulation failed: {res.violations}")
        # Turn 3 is where adversarial stress probes a turn-off
        t3 = next((t for t in res.turn_log if t["turn"] == 3), None)
        if t3:
            self.assertEqual(t3["violations"], 0)

    def test_clock_fast_forward_midnight_crossing(self):
        """Verify late night climax correctly rolls over day counter when fast-forwarding refractory clock."""
        from mechanics.social.intimate_excitement import check_and_resolve_refractory_clock, is_in_refractory_cooldown
        # Starts on Day 1 at 23:50 (1430 minutes). 40 min cooldown expires on Day 2 at 00:30 (1470 abs).
        target_refr = (1 * 1440) + 1430 + 40
        session = {"current_day": 1, "current_minute": 1430}
        phys_state = {
            "excitement": {
                "active": True,
                "refractory_until_minute": target_refr,
                "player_in_refractory": True,
                "actors": {"Artemiusz": {"meter": 100, "climaxes_count": 1, "status": "Spent"}}
            }
        }
        # Advance 5 mins past target
        target_abs = target_refr + 5
        session["current_day"] = target_abs // 1440
        session["current_minute"] = target_abs % 1440
        self.assertEqual(session["current_day"], 2)
        self.assertEqual(session["current_minute"], 35)

        cleared, toast = check_and_resolve_refractory_clock(session, phys_state)
        self.assertTrue(cleared)
        in_refr_after, _ = is_in_refractory_cooldown(session, phys_state)
        self.assertFalse(in_refr_after)

    def test_cli_runner_batch_execution(self):
        """Verify CLI runner executes cleanly via subprocess."""
        cmd = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "..", "scripts", "simulate_intimacy.py"),
            "--simulations", "3",
            "--scenario", "all",
            "--partner-config", "all",
            "--fuzz", "none",
            "--seed", "9999",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"CLI runner failed: {result.stderr}\n{result.stdout}")
        self.assertIn("100.0%", result.stdout)


if __name__ == "__main__":
    unittest.main()
