from __future__ import annotations
import json
import os
import tempfile
import unittest
import db
import db.core
from game_engine.choices_cleaner import clean_choices_impl
from game_engine.quests import (
    resolve_pre_turn_quests_and_clues,
    apply_quest_update,
    forfeit_side_bounty,
    can_accept_side_bounty,
    check_and_extract_defeated_suspect_evidence,
    evaluate_quest_state_predicates,
)
from game_engine.state.core import apply_outcome
from mechanics.combat.merchant import (
    generate_grounded_merchant_rumors,
    reveal_hidden_node_from_rumor,
)
from mechanics.world.waypoints.choices import (
    generate_quest_action_choices,
    get_active_companion_for_waypoint,
)


class TestDeterministicQuests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._isolated_db = os.path.join(self._tmp_dir.name, "test_det_quests.db")
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        db.DB_PATH = self._isolated_db
        db.core.DB_PATH = self._isolated_db
        db.init_db()

        self.user_id = 999888111
        base_stats = {"STR": 6, "PER": 5, "END": 5, "CHA": 6, "INT": 7, "AGI": 5, "LUK": 5}
        self.char = db.create_character(
            user_id=self.user_id,
            name="Detective Hiro",
            char_class="Investigator",
            class_description="Test Investigator",
            stats=base_stats,
        )
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = db.get_session(self.session_id)
        self.party = [(self.char, db.get_inventory(self.user_id))]

    def tearDown(self):
        if hasattr(db, "close_all_connections"):
            db.close_all_connections()
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

    def test_zero_llm_objective_authority_and_deterministic_campaign_goals(self):
        """D1 & D11: Unverified LLM quest_updates cannot complete quests or spoof rewards; campaign_goals sync deterministically."""
        qid = "SQ-101"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Stolen Exam Papers",
            objective="Find who leaked the midterm exam.",
            progress="1/2 Cleared",
            status="Active",
            reward_xp=200,
            reward_gold=50,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Inspect the faculty desk", "completed": True},
                {"id": 2, "text": "Interrogate the suspect", "completed": False},
            ],
        )
        db.update_session_campaign_goals(self.session_id, [
            {"id": "goal_main", "title": "Uncover Campus Conspiracy", "progress_pct": 0, "status": "Active"}
        ])

        fake_llm_outcome = {
            "outcome_narrative": "The player easily wraps up the investigation and gets rich.",
            "quest_updates": [
                {
                    "quest_id": qid,
                    "title": "The Stolen Exam Papers",
                    "status": "Completed",
                    "reward_xp": 9999,
                    "reward_gold": 5000,
                }
            ],
            "campaign_goal_progress": [{"id": "goal_main", "progress": 100, "status": "Completed"}],
        }

        # 1. Direct apply_quest_update with from_llm=True blocks status/reward spoofing
        notice = apply_quest_update(
            self.session_id,
            fake_llm_outcome["quest_updates"][0],
            party_user_ids=[self.user_id],
            outcome=fake_llm_outcome,
            actions=[{"label": "Look around", "stat": "NONE", "requirement": 0}],
            from_llm=True,
        )
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(q_after["status"], "Active")
        self.assertEqual(q_after["reward_xp"], 200)
        self.assertEqual(q_after["reward_gold"], 50)
        self.assertIsNone(notice)

        # 2. Full apply_outcome ignores LLM quest_updates and computes campaign_goals % deterministically
        apply_outcome(self.session_id, self.party, fake_llm_outcome, actions=[])
        self.assertEqual(db.get_quest_by_id(self.session_id, qid)["status"], "Active")
        goals = db.get_session_campaign_goals(self.session_id)
        self.assertGreater(goals[0]["progress_pct"], 0)
        self.assertLess(goals[0]["progress_pct"], 100)

    def test_server_direct_apply_quest_update_authority(self):
        """Server-internal calls (from_llm=False) retain quest status & reward payout authority."""
        qid = "SRV-001"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Side Bounty",
            title="Server Errand",
            objective="Perform an errand.",
            status="Active",
            reward_xp=50,
            reward_gold=10,
            is_story_quest=0,
        )

        notice = apply_quest_update(
            self.session_id,
            {"quest_id": qid, "title": "Server Errand", "status": "Completed"},
            party_user_ids=[self.user_id],
            from_llm=False,
        )
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(q_after["status"], "Completed")
        self.assertIsNotNone(notice)
        self.assertTrue(notice.get("claimed"))

    def test_pre_registered_clue_discovery_and_savepoint_rollback(self):
        """D3: persist_db=False stages sub-objective completion & clue via SAVEPOINT rollback, committing only inside apply_outcome."""
        qid = "SQ-102"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Vault Heist",
            objective="Uncover who unlocked the academy vault.",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=[
                {
                    "id": 1,
                    "text": "Investigate the vault entrance for physical traces",
                    "clue": "Scratched bronze key fragment found jammed in the deadbolt",
                    "completed": False,
                }
            ],
        )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 1,
                    "stage_label": "Examine the lock mechanism",
                    "target_location": "Academic Building ➔ Vault",
                    "target_npc": "Archivist Donald",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=1,
        )
        self.session["current_location"] = "Academic Building ➔ Vault"

        actions = [
            {
                "label": "Carefully examine the deadbolt with a magnifying glass",
                "stat": "INT",
                "requirement": 5,
                "quest_id": qid,
                "sub_obj_id": 1,
                "is_quest_action": True,
                "check": {"succeeded": True, "result_tier": "success"},
            }
        ]

        # 1. Pre-LLM staging (persist_db=False): stages result, leaves SQLite untouched!
        staged_res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions, persist_db=False)
        self.assertEqual(len(staged_res["completed_sub_quests"]), 1)
        self.assertEqual(len(db.get_session_clues(self.session_id)), 0, "Rolled-back savepoint must leave 0 clues before narration")

        # 2. Post-LLM commit via apply_outcome: replays deterministically inside UnitOfWork!
        self.session["_pre_turn_quest_res"] = staged_res
        outcome = {"outcome_narrative": "You extract the bronze key fragment from the lock.", "_pre_turn_quest_res": staged_res}
        apply_outcome(self.session_id, self.party, outcome, actions=actions)

        clues = db.get_session_clues(self.session_id)
        self.assertGreaterEqual(len(clues), 1)
        self.assertIn("bronze key fragment", clues[0]["lead_text"].lower())

    def test_interactive_caseboard_deductive_synthesis_and_choice_injection(self):
        """D18: Clues are NOT silently auto-consumed; [🧩 Synthesize Leads] choice is injected and awards +50 XP on sub_intent='deduce_clues'."""
        qid = "SQ-103"
        cur_ch = 1

        db.add_session_clue(
            session_id=self.session_id,
            title="Encrypted USB Stick",
            lead_text="Found in the student council office containing student records.",
            category="digital",
            source_location="Student Council Room",
            linked_npc="Council President Kevin",
            quest_id=qid,
            chapter=cur_ch,
        )
        db.add_session_clue(
            session_id=self.session_id,
            title="Witness Statement",
            lead_text="A janitor observed Council President Kevin entering the archive room at midnight.",
            category="testimonial",
            source_location="Archive Room",
            linked_npc="Council President Kevin",
            quest_id=qid,
            chapter=cur_ch,
        )

        # 1. Idle turn (actions=[]) must NOT silently auto-deduce
        idle_res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions=[])
        self.assertEqual(len([c for c in db.get_session_clues(self.session_id) if c.get("category") == "deduction"]), 0)
        self.assertEqual(idle_res.get("synthesized_deductions", []), [])

        # 2. Hybrid choice builder injects [🧩 Synthesize Leads] priority button when valid pair exists
        from game_engine.choices_cleaner import build_hybrid_turn_choices
        cleaned = build_hybrid_turn_choices(
            raw_choices=[{"label": "Check bulletin board", "stat": "NONE", "requirement": 0}],
            session=self.session,
            party=self.party,
            result={"location": "Student Council Room"},
            actions=[],
        )
        synth_choices = [c for c in cleaned if c.get("sub_intent") == "deduce_clues"]
        self.assertEqual(len(synth_choices), 1)
        self.assertIn("Synthesize Leads", synth_choices[0]["label"])

        # 3. Executing deduce_clues synthesizes Breakthrough, awards +50 XP, and emits directive
        xp_before = db.get_character(self.user_id)["xp"]
        deduce_act = [{
            "label": synth_choices[0]["label"],
            "sub_intent": "deduce_clues",
            "stat": "INT",
            "check": {"succeeded": True, "tier": "success"},
        }]
        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions=deduce_act)
        verified_clues = db.get_session_clues(self.session_id, is_verified=1)
        deductions = [c for c in verified_clues if c.get("category") == "deduction"]
        self.assertEqual(len(deductions), 1)
        self.assertIn("Kevin", deductions[0]["linked_npc"])
        self.assertEqual(res.get("deduction_xp_bonus"), 50)
        self.assertGreaterEqual(db.get_character(self.user_id)["xp"], xp_before + 50)
        self.assertTrue(any("BREAKTHROUGH SYNTHESIZED" in d for d in res.get("directives", [])))

    def test_caseboard_20_clue_cap_smart_tiered_eviction(self):
        """D12: Caseboard caps active unconsumed clues at 20, archiving completed-chapter & circumstantial clues while protecting Story Quests & deductions."""
        db.set_session_chapter(self.session_id, 2)
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-CH2",
            quest_type="Story Quest",
            title="Chapter 2 Mystery",
            objective="Active story quest",
            status="Active",
            is_story_quest=1,
        )

        # Insert 1 protected Story Quest clue and 1 protected deduction clue
        sq_clue_id = db.add_session_clue(
            self.session_id, "Protected Story Lead", "Crucial Chapter 2 evidence",
            category="physical", quest_id="SQ-CH2", chapter=2
        )
        ded_clue_id = db.add_session_clue(
            self.session_id, "Breakthrough: Suspect X", "Synthesized deduction",
            category="deduction", quest_id="SQ-CH2", chapter=2, is_verified=1
        )
        # Insert 5 old Chapter 1 clues (eviction tier 1)
        alpha_tags = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
        old_ch1_ids = [
            db.add_session_clue(
                self.session_id, f"Old Ch1 Note {alpha_tags[i]}", f"Outdated archival report {alpha_tags[i]} regarding semester one",
                category="testimonial", quest_id="OLD-Q", chapter=1
            )
            for i in range(5)
        ]
        # Insert 16 circumstantial clues (active unconsumed non-deduction leads = 1 + 5 + 16 = 22 -> 2 archived to cap at 20!)
        phonetic_words = [
            "Foxtrot", "Golf", "Hotel", "India", "Juliet", "Kilo", "Lima", "Mike",
            "November", "Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango", "Uniform",
        ]
        for word in phonetic_words:
            db.add_session_clue(
                self.session_id, f"Ambient Lead {word}", f"Unique hallway observation involving code {word} near stairwell",
                category="physical", chapter=2
            )

        all_clues = db.get_session_clues(self.session_id)
        active_unconsumed = [c for c in all_clues if not c.get("is_consumed") and c.get("category") != "deduction"]
        self.assertEqual(len(active_unconsumed), 20)
        active_ids = {c["id"] for c in all_clues if not c.get("is_consumed")}
        self.assertIn(sq_clue_id, active_ids, "Active Story Quest clue must NEVER be evicted")
        self.assertIn(ded_clue_id, active_ids, "Verified deduction breakthrough must NEVER be evicted")
        self.assertNotIn(old_ch1_ids[0], active_ids, "Oldest Chapter 1 clue must be archived first")
        self.assertNotIn(old_ch1_ids[1], active_ids, "Second oldest Chapter 1 clue must be archived second")

    def test_checkpoint_save_and_load_remaps_deduction_parent_clue_ids(self):
        """D2: Saving and loading a checkpoint remaps session_clues.deduction_parents_json to the newly inserted clue IDs."""
        c1 = db.add_session_clue(self.session_id, "Footprint Cast", "Muddy boot print", category="physical", chapter=1)
        c2 = db.add_session_clue(self.session_id, "Security Log", "Badge swipe at 23:50", category="digital", chapter=1)
        db.add_session_clue(
            self.session_id,
            "Breakthrough: Night Intruder",
            "Boot print matches badge holder.",
            category="deduction",
            is_verified=1,
            deduction_parents=[c1, c2],
            chapter=1,
        )

        db.save_adventure_slot(self.user_id, "case_slot", overwrite=True)
        loaded = db.load_adventure_slot(self.user_id, "case_slot")
        new_sess_id = loaded["id"]
        self.assertNotEqual(new_sess_id, self.session_id)

        restored_clues = db.get_session_clues(new_sess_id)
        by_title = {c["title"]: c for c in restored_clues}
        new_c1 = by_title["Footprint Cast"]["id"]
        new_c2 = by_title["Security Log"]["id"]
        ded_row = by_title["Breakthrough: Night Intruder"]
        parents = ded_row.get("deduction_parents") or json.loads(ded_row.get("deduction_parents_json") or "[]")
        self.assertEqual(set(parents), {new_c1, new_c2})

    def test_grounded_merchant_rumors_and_hidden_node_reveal(self):
        """D19: Merchant rumors link to active quests / hidden world_nodes; ambient fallback rumors stay unlinked."""
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="BNT-RUMOR",
            quest_type="Side Bounty",
            title="The Missing Alchemist",
            objective="Locate Alchemist Venn near the Old Clocktower.",
            status="Active",
            is_story_quest=0,
        )
        db.save_world_node(
            self.session_id, "room_hidden_crypt", None, "Sunken Ossuary",
            node_type="ROOM", privacy_level="public", state_json={"is_hidden": True}
        )

        rumors = generate_grounded_merchant_rumors(
            self.session_id, scen_key="fantasy", fallback_rumors=["Nice weather we're having lately."]
        )
        self.assertGreaterEqual(len(rumors), 2)
        quest_rumor = next((r for r in rumors if r.get("linked_quest_id") == "BNT-RUMOR"), None)
        node_rumor = next((r for r in rumors if r.get("linked_node_id") == "room_hidden_crypt"), None)
        ambient_rumor = next((r for r in rumors if not r.get("linked_quest_id") and not r.get("linked_node_id")), None)

        self.assertIsNotNone(quest_rumor)
        self.assertIsNotNone(node_rumor)
        if ambient_rumor:
            self.assertIsNone(ambient_rumor.get("linked_quest_id"))

        # Revealing hidden node flips is_hidden -> False
        self.assertTrue(reveal_hidden_node_from_rumor(self.session_id, "room_hidden_crypt"))
        wn = db.get_world_node(self.session_id, "room_hidden_crypt")
        st = wn.get("state_json") if isinstance(wn.get("state_json"), dict) else json.loads(wn.get("state_json") or "{}")
        self.assertFalse(bool(st.get("is_hidden")))

    def test_shop_item_acquisition_triggers_quest_state_predicates(self):
        """D20: Acquiring a required quest item (e.g. via Merchant Shop) advances ACQUISITION quest predicates."""
        qid = "BNT-ACQ-1"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Side Bounty",
            title="Supply Run: Silver Herb",
            objective="Acquire 1 Silver Herb and deliver it to Nurse Joy.",
            status="Active",
            is_story_quest=0,
            blueprint_id="ACQUISITION",
            required_item="Silver Herb",
            required_item_count=1,
        )
        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {"stage_index": 1, "stage_label": "Buy Silver Herb", "target_location": "Market", "completion_trigger": "item_acquired"},
                {"stage_index": 2, "stage_label": "Deliver to Nurse Joy", "target_location": "Infirmary", "completion_trigger": "dialogue"},
            ],
        )

        db.add_item(self.user_id, "Silver Herb", "Consumable", "Medicinal herb", 1)
        updates = evaluate_quest_state_predicates(
            self.session_id, user_id=self.user_id, event_info={"event": "ItemGained", "item_name": "Silver Herb"}
        )
        self.assertGreaterEqual(len(updates), 1)
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertIn("Ready to deliver", q_after.get("progress", ""))

    def test_two_phase_climax_gate_standard(self):
        """Clearing all sub-objectives primes climax; resolving the climax completes chapter and seeds next."""
        qid = "SQ-104"
        cur_ch = 1
        db.set_session_chapter(self.session_id, cur_ch)

        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="Chapter 1 Crisis",
            objective="Solve the campus mystery.",
            status="Active",
            reward_xp=300,
            reward_gold=75,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Gather lead 1", "completed": True},
                {"id": 2, "text": "Gather lead 2", "completed": True},
            ],
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 99,
                    "stage_label": "Confront the mastermind",
                    "target_location": "Academy Rooftop",
                    "target_npc": "Mastermind Vance",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=None,
        )

        self.session["current_location"] = "Academy Rooftop"
        self.session["chapter"] = cur_ch

        actions = [
            {
                "label": "⚡ [Story Climax] Confront Mastermind Vance with the evidence",
                "stat": "CHA",
                "requirement": 6,
                "quest_id": qid,
                "is_quest_action": True,
                "is_climax_action": True,
                "check": {"succeeded": True, "result_tier": "success"},
            }
        ]

        res = resolve_pre_turn_quests_and_clues(self.session, self.party, actions)
        self.assertIn(qid, res["completed_quests"])
        self.assertTrue(res["chapter_climax"])
        self.assertEqual(db.get_session_chapter(self.session_id), 2)
        next_sq = db.get_active_story_quest(self.session_id)
        self.assertIsNotNone(next_sq)
        self.assertEqual(next_sq["status"], "Active")

    def test_premature_climax_confrontation_penalty(self):
        """Arriving at climax venue with incomplete sub-objectives incurs +4 DC penalty; failure escalates strikes."""
        qid = "SQ-105"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="Chapter 1 Mystery",
            objective="Investigate before confronting.",
            status="Active",
            reward_xp=300,
            reward_gold=75,
            is_story_quest=1,
            sub_objectives=[
                {"id": 1, "text": "Gather physical evidence", "completed": False},
                {"id": 2, "text": "Interview witness", "completed": False},
            ],
        )

        db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=qid,
            waypoints=[
                {
                    "stage_index": 99,
                    "stage_label": "Showdown",
                    "target_location": "Abandoned Gym",
                    "target_npc": "Rival Gary",
                    "completion_trigger": "skill_check",
                }
            ],
            sub_obj_id=None,
        )

        self.session["current_location"] = "Abandoned Gym"
        choices = generate_quest_action_choices(self.session_id, "Abandoned Gym", scen_key="high_school_drama", char=self.char)
        premature_choices = [c for c in choices if c.get("is_premature_climax")]
        self.assertEqual(len(premature_choices), 1)
        self.assertEqual(premature_choices[0]["requirement"], 10)

        fail_actions = [
            {
                "label": "⚡ [Story Climax - Premature Showdown] Force confrontation",
                "stat": "CHA",
                "requirement": 10,
                "quest_id": qid,
                "is_quest_action": True,
                "is_climax_action": True,
                "check": {"succeeded": False, "result_tier": "failure"},
            }
        ]
        res = resolve_pre_turn_quests_and_clues(self.session, self.party, fail_actions)
        q_after = db.get_quest_by_id(self.session_id, qid)
        self.assertEqual(int(q_after.get("strikes") or 0), 2)
        self.assertEqual(len([d for d in res.get("directives", []) if "PREMATURE CLIMAX FAILED" in d]), 1)

    def test_companion_privacy_gate_for_assists(self):
        """Companions waiting outside private rooms cannot assist with internal waypoint checks."""
        db.save_world_node(
            self.session_id, "room_dorm_private", "fac_dorms", "Alice's Private Room",
            node_type="ROOM", privacy_level="private"
        )
        db.add_session_party_npc(self.session_id, {"name": "Bob"})
        db.update_session(self.session_id, extra={"current_node_id": "room_dorm_private"})

        sess = db.get_session(self.session_id)
        comp = get_active_companion_for_waypoint(sess, {"target_npc": ""})
        self.assertIsNone(comp)

    def test_bounty_forfeiture_and_concurrency_cap_exempts_mandatory_daily(self):
        """Forfeiting side bounty applies -5 client affinity; cap is 3 optional bounties and exempts MAND-* daily duties."""
        client_name = "Chloe Davis"
        db.upsert_contact(self.session_id, "chloe_davis", client_name, basic_info={"role": "Student", "description": "Classmate"}, delta_score=20)
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="BNT-FORFEIT",
            quest_type="Side Bounty",
            title="Escort Caravan",
            objective="Deliver cargo safely.",
            client_npc=client_name,
            status="Active",
            reward_xp=100,
            reward_gold=40,
            is_story_quest=0,
        )
        res = forfeit_side_bounty(self.session_id, "BNT-FORFEIT", [self.user_id])
        self.assertTrue(res["success"])
        self.assertEqual(db.get_quest_by_id(self.session_id, "BNT-FORFEIT")["status"], "Abandoned")
        self.assertEqual(db.get_contact(self.session_id, client_name)["relationship_score"], 15)

        # Mandatory daily duty does NOT count against the 3 optional bounty cap!
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="MAND-DAILY-1",
            quest_type="Mandatory Duty",
            title="Morning Homeroom Attendance",
            objective="Attend class.",
            status="Active",
            is_story_quest=0,
        )
        for i in range(1, 3):
            db.upsert_quest(
                session_id=self.session_id,
                quest_id=f"BNT-00{i}",
                quest_type="Side Bounty",
                title=f"Bounty #{i}",
                objective="Task",
                status="Active",
                is_story_quest=0,
            )
        self.assertTrue(can_accept_side_bounty(self.session_id), "MAND-* must not consume optional bounty slot")
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="BNT-003",
            quest_type="Side Bounty",
            title="Bounty #3",
            objective="Task",
            status="Active",
            is_story_quest=0,
        )
        self.assertFalse(can_accept_side_bounty(self.session_id))

    def test_suspect_elimination_genre_grounded_pocket_clue_drop(self):
        """Defeating an investigation suspect extracts genre-grounded pocket evidence ('hidden notebook' in school, 'wax-sealed ledger' in fantasy)."""
        qid = "SQ-106"
        suspect_name = "Smuggler Jax"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=qid,
            quest_type="Story Quest",
            title="The Contraband Ring",
            objective=f"Track down {suspect_name} and find the contraband source.",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=[{"id": 1, "text": f"Interrogate {suspect_name}", "completed": False}],
        )

        res = check_and_extract_defeated_suspect_evidence(self.session_id, suspect_name, cur_loc="Underground Warehouse")
        self.assertIsNotNone(res)
        self.assertIn("Pocket Evidence", res["title"])
        clues = db.get_session_clues(self.session_id, linked_npc=suspect_name)
        self.assertEqual(len(clues), 1)
        self.assertIn("hidden notebook", clues[0]["lead_text"].lower())

    def test_clean_location_grammar_and_stutter_deduplication(self):
        """Location names in quests/bounties eliminate stuttered words ('Neon-Mirage Neon ...') and format arrow chains cleanly in prose and badges."""
        from mechanics.world.locations import (
            dedupe_location_stutter,
            format_clean_location_prose,
            format_clean_location_badge,
            clean_narrative_location_arrows,
        )
        from game_engine.quests import create_contextual_story_quest_data

        # 1. Stutter deduplication
        self.assertEqual(
            dedupe_location_stutter("Neon-Mirage Neon Shopping Arcade & Mall"),
            "Neon-Mirage Shopping Arcade & Mall",
        )
        self.assertEqual(
            dedupe_location_stutter("Vespera Downtown ➔ Neon-Mirage Neon Shopping Arcade & Mall"),
            "Vespera Downtown ➔ Neon-Mirage Shopping Arcade & Mall",
        )

        # 2. Clean prose & badge formatting
        self.assertEqual(
            format_clean_location_prose("Sovereign-Core City Center -> S.O.A.I. HQ"),
            "S.O.A.I. HQ",
        )
        self.assertEqual(
            format_clean_location_prose("Sovereign-Core City Center -> S.O.A.I. HQ", include_zone=True),
            "S.O.A.I. HQ in Sovereign-Core City Center",
        )
        self.assertEqual(
            format_clean_location_badge("Sovereign-Core City Center -> S.O.A.I. HQ"),
            "S.O.A.I. HQ (Sovereign-Core City Center)",
        )

        # 3. Embedded arrow prose cleaning across multiple locations separated by 'and'
        raw_sentence = (
            "Investigate anomalous telemetry readings across Sovereign-Core City Center ➔ Obelisk Central Transit Terminal "
            "and Vespera Downtown ➔ Neon-Mirage Neon Shopping Arcade & Mall."
        )
        cleaned = clean_narrative_location_arrows(raw_sentence)
        self.assertNotIn("➔", cleaned)
        self.assertNotIn("->", cleaned)
        self.assertNotIn("Neon-Mirage Neon", cleaned)
        self.assertIn("Obelisk Central Transit Terminal in Sovereign-Core City Center", cleaned)
        self.assertIn("Neon-Mirage Shopping Arcade & Mall in Vespera Downtown", cleaned)

        # 4. Newly generated contextual story quest has zero raw arrows in title, objective, or sub-objective text
        qdata = create_contextual_story_quest_data(
            session_id=self.session_id,
            session={"scenario": "urban_paranormal", "current_location": "Sovereign-Core City Center ➔ S.O.A.I. HQ"},
            chapter_num=1,
        )
        self.assertNotIn("➔", qdata["title"])
        self.assertNotIn("->", qdata["title"])
        self.assertNotIn("➔", qdata["objective"])
        self.assertNotIn("->", qdata["objective"])
        for so in qdata["sub_objectives"]:
            self.assertNotIn("➔", so["text"])
            self.assertNotIn("->", so["text"])


if __name__ == "__main__":
    unittest.main()
