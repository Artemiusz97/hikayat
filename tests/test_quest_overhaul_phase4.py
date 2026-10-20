import unittest
import pytest
import json
import db
from game_engine.quests import (
    resolve_pre_turn_quests_and_clues,
    check_and_expire_overdue_quests,
    send_quest_comms_message,
    trigger_stage2_midquest_comms_if_eligible,
    apply_quest_approach_effects,
    handle_failed_quest_skill_check,
)
from mechanics.world.waypoints.choices import (
    generate_quest_action_choices,
    tag_and_enrich_quest_choices,
    has_caseboard_breakthrough_for_waypoint,
    get_active_companion_for_waypoint,
)
from mechanics.narrative.blueprints import (
    has_quest_note_flag,
    append_quest_note_flag,
    evaluate_companion_assist_for_blueprint,
    format_quest_comms_message,
    classify_choice_approach,
)
from mechanics.narrative.bounty import (
    build_consequence_followup_bounty,
    seed_contact_commission_if_eligible,
    replenish_daily_bounties_deterministic,
)


def _setup_session(
    session_id: int,
    user_id: int,
    name: str = "Aria Seeker",
    gold: int = 50,
    current_day: int = 1,
    current_minute: int = 480,
    current_location: str = "Old Docks",
    scenario: str = "fantasy",
) -> dict:
    with db.get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.execute("DELETE FROM quests WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM contacts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM factions WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM lorebook WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM session_clues WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM inventory WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
        conn.execute(
            """INSERT INTO characters (
                id, user_id, name, char_class, level, is_active, str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp, gold
            ) VALUES (?, ?, ?, 'Rogue', 1, 1, 6, 6, 6, 6, 6, 6, 5, 100, 100, 50, 50, ?)""",
            (user_id, user_id, name, gold),
        )
        conn.execute(
            """INSERT INTO sessions (
                id, mode, capacity, status, scenario, current_location, current_day, current_minute, host_user_id, turn_order, choices_json, history_json
            ) VALUES (?, 'solo', 1, 'active', ?, ?, ?, ?, ?, ?, '[]', '[]')""",
            (session_id, scenario, current_location, current_day, current_minute, user_id, json.dumps([user_id])),
        )
    return db.get_session(session_id)


def _insert_test_contact(session_id: int, name: str, relationship_score: int = 10, location: str = "", role: str = "", club: str = ""):
    npc_id = name.lower().replace(" ", "_")
    info_dict = {}
    if location:
        info_dict["location"] = location
        info_dict["primary_facility"] = location
    if role:
        info_dict["role"] = role
    if club:
        info_dict["club"] = club
    basic_info = json.dumps(info_dict)
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json) VALUES (?, 0, ?, ?, ?, ?)",
            (session_id, npc_id, name, relationship_score, basic_info),
        )



class TestQuestOverhaulPhase4(unittest.TestCase):
    def test_1_caseboard_breakthrough_shortcut_and_choice(self):
        """Caseboard deduction synthesis auto-advances Stage 1 scouting and unlocks Breakthrough Leverage."""
        sid = 9401
        uid = 9401
        sess = _setup_session(sid, uid, current_location="Grand Parlor", scenario="fantasy")
        char = db.get_character(uid)

        qid = "BNT-CASE-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid,
            quest_type="Campus Investigation",
            title="The Embezzlement Secret",
            objective="Discover the truth about Michael's forged records.",
            progress="0/1 Leads Found",
            current_clues="",
            status="Active",
            reward_xp=120,
            reward_gold=40,
            blueprint_id="INVESTIGATION",
            client_npc="Headmistress",
            client_location="Admin Office",
        )
        wps = [
            {
                "stage_index": 1,
                "stage_label": "Search for hidden ledger at Study",
                "target_location": "Manor Study",
                "completion_trigger": "arrival",
                "status": "active",
                "is_active": 1,
            },
            {
                "stage_index": 2,
                "stage_label": "Confront Michael with the ledger",
                "target_location": "Grand Parlor",
                "target_npc": "Michael",
                "completion_trigger": "skill_check",
                "status": "pending",
                "is_active": 0,
            },
        ]
        db.save_quest_waypoints(sid, qid, wps, sub_obj_id=None)

        # Insert 2 parent clues linked to this quest and target
        c1_id = db.add_session_clue(sid, title="Torn Page", lead_text="Ledger entry with missing funds", linked_npc="Michael", quest_id=qid)
        c2_id = db.add_session_clue(sid, title="Michael's Seal", lead_text="Wax seal confirming Michael signed the order", linked_npc="Michael", quest_id=qid)

        # Synthesize verified deduction
        deduction = db.synthesize_deduction_clue(
            session_id=sid,
            clue_ids=[c1_id, c2_id],
            title="Michael's Direct Embezzlement",
            lead_text="Michael forged the transactions to divert gold.",
        )
        self.assertIsNotNone(deduction)

        # Assert Stage 1 completed, Stage 2 active
        active_wp = db.get_active_waypoint(sid, qid, None)
        self.assertIsNotNone(active_wp)
        self.assertEqual(int(active_wp["stage_index"]), 2)

        # Assert quest tagged with caseboard_breakthrough:1
        fresh_q = db.get_quest_by_id(sid, qid)
        self.assertTrue(has_quest_note_flag(fresh_q["quest_notes"], "caseboard_breakthrough"))

        # Generate choices at Grand Parlor where Michael and Stage 2 are located
        choices = generate_quest_action_choices(sid, current_location="Grand Parlor", scen_key="fantasy", char=char)
        breakthrough_choice = next((c for c in choices if c.get("approach") == "breakthrough_leverage"), None)
        self.assertIsNotNone(breakthrough_choice, "Breakthrough Leverage choice should be offered")
        self.assertEqual(breakthrough_choice["stat"], "FREE")
        self.assertEqual(breakthrough_choice["requirement"], 0)
        self.assertIn("[Breakthrough Leverage]", breakthrough_choice["label"])

        # Execute breakthrough approach in pre-turn resolution
        action = {
            "label": breakthrough_choice["label"],
            "approach": "breakthrough_leverage",
            "quest_id": qid,
            "is_quest_action": True,
            "check": {"success": True, "result_tier": "success"},
        }
        turn_res = resolve_pre_turn_quests_and_clues(session=sess, actions=[action])
        has_breakthrough_directive = any("BREAKTHROUGH LEVERAGE" in d for d in turn_res.get("directives", []))
        self.assertTrue(has_breakthrough_directive)

    def test_2_companion_assist_choice_and_role_match_scaling(self):
        """Active companion injects assist choice; role match gives FREE Auto-Success while non-match gives -3 DC."""
        sid = 9402
        uid = 9402
        sess = _setup_session(sid, uid, current_location="Vault Infiltration", scenario="fantasy")
        char = db.get_character(uid)

        qid = "BNT-COMP-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid,
            quest_type="Heist",
            title="The Vault Infiltration",
            objective="Infiltrate the vault and secure the relic.",
            progress="0/1 Infiltration",
            current_clues="",
            status="Active",
            reward_xp=150,
            reward_gold=50,
            blueprint_id="HEIST_INFILTRATION",
            client_npc="Shadow Broker",
            client_location="Alleyway",
        )
        wps = [
            {
                "stage_index": 2,
                "stage_label": "Pick the vault security tumblers",
                "target_location": "Vault Infiltration",
                "target_npc": "Vault Sentry",
                "completion_trigger": "skill_check",
                "status": "active",
                "is_active": 1,
            }
        ]
        db.save_quest_waypoints(sid, qid, wps, sub_obj_id=None)

        # 1. Matching Companion: Rogue/Thief matches HEIST_INFILTRATION
        rogue_comp = {"name": "Lyra", "role": "Rogue", "char_class": "Thief"}
        db.set_session_party_npcs(sid, [rogue_comp])

        eval_match = evaluate_companion_assist_for_blueprint(rogue_comp, "HEIST_INFILTRATION")
        self.assertTrue(eval_match["is_role_match"])
        self.assertEqual(eval_match["stat"], "FREE")

        choices = generate_quest_action_choices(sid, current_location="Vault Infiltration", scen_key="fantasy", char=char)
        assist_choice = next((c for c in choices if c.get("approach") == "companion_assist"), None)
        self.assertIsNotNone(assist_choice)
        self.assertEqual(assist_choice["stat"], "FREE")
        self.assertEqual(assist_choice["requirement"], 0)
        self.assertIn("Lyra", assist_choice["label"])

        # 2. Non-Matching Companion: Scholar does not match HEIST_INFILTRATION
        scholar_comp = {"name": "Cyrus", "role": "Scholar", "char_class": "Mage"}
        db.set_session_party_npcs(sid, [scholar_comp])

        eval_nomatch = evaluate_companion_assist_for_blueprint(scholar_comp, "HEIST_INFILTRATION")
        self.assertFalse(eval_nomatch["is_role_match"])
        self.assertEqual(eval_nomatch["dc_mod"], -3)

        choices_nomatch = generate_quest_action_choices(sid, current_location="Vault Infiltration", scen_key="fantasy", char=char)
        assist_nomatch = next((c for c in choices_nomatch if c.get("approach") == "companion_assist"), None)
        self.assertIsNotNone(assist_nomatch)
        self.assertEqual(assist_nomatch["dc_mod"], -3)
        self.assertNotEqual(assist_nomatch["stat"], "FREE")

        # 3. Successful companion assist execution awards +3 companion affinity
        _insert_test_contact(sid, name="Cyrus", relationship_score=10)
        q_obj = db.get_quest_by_id(sid, qid)
        active_wp = db.get_active_waypoint(sid, qid, None)
        eff = apply_quest_approach_effects(sid, q_obj, active_wp, "companion_assist", 0, [uid])
        self.assertTrue(eff.get("companion_assisted"))
        contacts = db.get_contacts(sid)
        cyrus_contact = next(c for c in contacts if c["name"] == "Cyrus")
        self.assertEqual(int(cyrus_contact["relationship_score"]), 13)  # 10 + 3

    def test_3_companion_strike_shield_absorbs_failure(self):
        """Active companion provides a once-per-quest strike shield that absorbs the first failure."""
        sid = 9403
        uid = 9403
        sess = _setup_session(sid, uid, current_location="Arena", scenario="fantasy")

        qid = "BNT-SHIELD-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid,
            quest_type="Duel",
            title="Trial by Combat",
            objective="Survive the champion's assault.",
            progress="0/1 Rounds",
            current_clues="",
            status="Active",
            reward_xp=100,
            reward_gold=30,
            blueprint_id="CONTEST_RIVALRY",
            strikes=0,
        )
        wp = {
            "stage_index": 2,
            "stage_label": "Parry the champion's heavy onslaught",
            "target_location": "Arena",
            "completion_trigger": "skill_check",
            "status": "active",
            "is_active": 1,
        }
        db.save_quest_waypoints(sid, qid, [wp], sub_obj_id=None)

        # Set active companion in party
        db.set_session_party_npcs(sid, [{"name": "Garrick", "role": "Defender", "char_class": "Warrior"}])

        q_row = db.get_quest_by_id(sid, qid)
        # First failure: Strike Shield triggers and absorbs the blow!
        res1 = handle_failed_quest_skill_check(sid, q_row, wp, "failure", [uid])
        self.assertEqual(res1.get("status"), "companion_shield_absorbed")
        self.assertTrue(res1.get("shield_absorbed"))

        # Strike count remains 0, and quest notes has companion_shield_used:1
        q_row_after = db.get_quest_by_id(sid, qid)
        self.assertEqual(int(q_row_after.get("strikes", 0)), 0)
        self.assertTrue(has_quest_note_flag(q_row_after["quest_notes"], "companion_shield_used"))

        # Second failure: Shield already used, strikes increment normally!
        res2 = handle_failed_quest_skill_check(sid, q_row_after, wp, "failure", [uid])
        self.assertEqual(res2.get("status"), "strike_warning")
        self.assertEqual(res2.get("strikes"), 1)
        q_row_final = db.get_quest_by_id(sid, qid)
        self.assertEqual(int(q_row_final.get("strikes", 0)), 1)

    def test_4_phone_dm_and_guild_courier_messaging(self):
        """Dispatches scenario-branded comms (SMS/DM in modern, Guild Courier in fantasy) and persists to phone_messages."""
        # 1. Modern / School Setting -> SMS/DM
        sid_mod = 9404
        uid_mod = 9404
        sess_mod = _setup_session(sid_mod, uid_mod, current_location="Campus Library", scenario="high_school")

        send_quest_comms_message(
            session_id=sid_mod,
            sender_npc_id="Maya",
            msg_type="stage2_client_intel",
            quest_title="Exam Notes Search",
            target_npc="Michael",
            target_loc="Study Room",
            scen_key="high_school",
        )
        msgs_mod = db.get_phone_messages(sid_mod, "maya")
        self.assertTrue(len(msgs_mod) >= 1)
        self.assertIn("📱 [SMS / DM]", msgs_mod[0]["message"])
        self.assertIn("Exam Notes Search", msgs_mod[0]["message"])

        # 2. Fantasy Setting -> Guild Courier 24h warning
        sid_fan = 9405
        uid_fan = 9405
        sess_fan = _setup_session(sid_fan, uid_fan, current_location="Guild Hall", scenario="fantasy", current_day=1, current_minute=480)

        # Quest with deadline in 20 hours (day 2, minute 240) -> 1200 mins remaining (<= 1440)
        qid_fan = "BNT-FAN-TIME"
        db.upsert_quest(
            session_id=sid_fan,
            quest_id=qid_fan,
            quest_type="Bounty",
            title="Slay the Manticore",
            objective="Eliminate the beast before time runs out.",
            progress="In Pursuit",
            current_clues="",
            status="Active",
            reward_xp=150,
            reward_gold=50,
            client_npc="Guild Registrar",
            deadline_day=2,
            deadline_minute=240,
        )
        exp_res = check_and_expire_overdue_quests(sid_fan, session=sess_fan)
        # Should send 24h deadline reminder warning DM
        msgs_fan = db.get_phone_messages(sid_fan, "guild_registrar")
        self.assertTrue(len(msgs_fan) >= 1)
        self.assertIn("🦅 [Guild Courier]", msgs_fan[0]["message"])
        self.assertTrue(any(w in msgs_fan[0]["message"].lower() for w in ("sands", "sundown", "rival", "run out")))

    def test_5_world_ripples_client_affinity_and_rival_factions(self):
        """Quest completion awards client affinity (+8 for commissions) and updates rival faction reputation."""
        sid = 9406
        uid = 9406
        sess = _setup_session(sid, uid, current_location="Town", scenario="fantasy")

        _insert_test_contact(sid, name="Lord Bennett", relationship_score=10)

        # 1. Standard Quest completion -> +5 client affinity
        qid_std = "BNT-STD-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid_std,
            quest_type="Bounty",
            title="Protect the Shipment",
            objective="Defend the cargo from raiders.",
            progress="Cleared",
            current_clues="",
            status="Active",
            reward_xp=100,
            reward_gold=25,
            client_npc="Lord Bennett",
        )
        res_std = db.claim_quest_reward(sid, qid_std, [uid])
        self.assertFalse(res_std.get("already_claimed"))
        c1 = next(c for c in db.get_contacts(sid) if c["name"] == "Lord Bennett")
        self.assertEqual(int(c1["relationship_score"]), 15)  # 10 + 5

        # 2. Personal Commission completion -> +8 client affinity
        qid_comm = "COMM-001"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid_comm,
            quest_type="Personal Commission",
            title="Discreet Deliverable",
            objective="Deliver the private heirloom.",
            progress="Cleared",
            current_clues="",
            status="Active",
            reward_xp=150,
            reward_gold=50,
            client_npc="Lord Bennett",
            quest_notes="commission:1",
        )
        res_comm = db.claim_quest_reward(sid, qid_comm, [uid])
        self.assertFalse(res_comm.get("already_claimed"))
        c2 = next(c for c in db.get_contacts(sid) if c["name"] == "Lord Bennett")
        self.assertEqual(int(c2["relationship_score"]), 23)  # 15 + 8

        # 3. Rival Faction Betrayal Ripple: Counter-Offer awards +5 rival rep, -15 client faction
        db.upsert_faction(sid, "iron_syndicate", delta_score=0, notes="Underworld cartel")
        db.upsert_faction(sid, "crown_guard", delta_score=0, notes="Royal enforcers")

        qid_riv = "BNT-RIV-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid_riv,
            quest_type="Neutralization",
            title="Infiltrate the Syndicate",
            objective="Subdue the syndicate captain.",
            progress="0/1 Subdued",
            current_clues="",
            status="Active",
            reward_xp=120,
            reward_gold=40,
            client_npc="Captain Vance",
            quest_notes="faction:crown_guard|rival_faction:iron_syndicate",
        )
        wp_riv = {
            "stage_index": 2,
            "stage_label": "Confront the syndicate enforcer",
            "target_location": "Docks",
            "target_npc": "Syndicate Enforcer",
            "completion_trigger": "skill_check",
        }
        db.save_quest_waypoints(sid, qid_riv, [wp_riv], sub_obj_id=None)

        q_obj = db.get_quest_by_id(sid, qid_riv)
        eff_betray = apply_quest_approach_effects(sid, q_obj, wp_riv, "counter_offer", 0, [uid], session=sess)
        self.assertTrue(eff_betray.get("terminated_by_betrayal"))

        # Verify rival faction gained +5 rep and sponsoring faction dropped -15 rep
        f_rival = db.get_faction(sid, "iron_syndicate")
        f_spons = db.get_faction(sid, "crown_guard")
        self.assertEqual(int(f_rival["reputation_score"]), 5)
        self.assertEqual(int(f_spons["reputation_score"]), -15)

    def test_6_consequence_followup_bounties_and_daily_replenishment(self):
        """Consequence follow-ups spawn from spared targets, commissions seed from high-affinity contacts, and daily replenishment fills board."""
        sid = 9407
        uid = 9407
        sess = _setup_session(sid, uid, current_location="Town Square", scenario="fantasy")

        # 1. Spared Target produces Consequence Follow-Up Bounty
        qid_spared = "BNT-SPARE-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid_spared,
            quest_type="Neutralization",
            title="Eliminate Rico the Smuggler",
            objective="Track down Rico and eliminate him.",
            progress="Spared and in hiding",
            current_clues="",
            status="Completed",
            reward_xp=100,
            reward_gold=30,
            client_npc="Sheriff Vance",
            resolution_approach="spared_deception",
        )

        flw_bounty = build_consequence_followup_bounty(sid, session=sess)
        self.assertIsNotNone(flw_bounty)
        self.assertTrue(flw_bounty["quest_id"].startswith("BNT-FLW-"))
        self.assertIn("Rico", flw_bounty["title"])
        # Parent quest marked with followup_spawned:1
        parent_q = db.get_quest_by_id(sid, qid_spared)
        self.assertTrue(has_quest_note_flag(parent_q["quest_notes"], "followup_spawned"))

        # 2. High-Affinity Contact seeds Personal Commission
        _insert_test_contact(sid, name="Elena", relationship_score=35, location="Herbalist Shop")
        comm = seed_contact_commission_if_eligible(sid, session=sess)
        self.assertIsNotNone(comm)
        self.assertTrue(comm["quest_id"].startswith("COMM-"))
        self.assertEqual(comm["client_npc"], "Elena")
        self.assertEqual(int(comm["reward_gold"]), 60)  # 1.5x payout

        # Confirm incoming comms message dispatched
        elena_msgs = db.get_phone_messages(sid, "elena")
        self.assertTrue(len(elena_msgs) >= 1)

        # 3. Daily Board Replenishment fills available board to 3 without blocking LLM calls
        board = replenish_daily_bounties_deterministic(sid, session=sess)
        self.assertEqual(len(board), 3)
        self.assertTrue(all(q["status"] == "Available" for q in board))

        # 4. Once Elena's commission is completed, she does not spam a repeat commission
        with db.get_conn() as conn:
            conn.execute("UPDATE quests SET status='Completed' WHERE session_id=? AND quest_id=?", (sid, comm["quest_id"]))
        repeat_comm = seed_contact_commission_if_eligible(sid, session=sess)
        self.assertIsNone(repeat_comm)

    def test_7_temporary_hangout_companions_and_cross_system_edge_cases(self):
        """Temporary hangout companions in non-combat scenarios enrich from contacts, grant assist DC -3, and absorb 1 strike."""
        sid = 9408
        uid = 9408
        sess = _setup_session(sid, uid, current_location="Student Council Room", scenario="high_school")
        char = {"stats": {"STR": 6, "DEX": 6, "INT": 6, "CHA": 6}}

        # Insert Maya into contacts with role in basic_info, and add her as a temporary hangout companion (no party_npcs)
        _insert_test_contact(sid, name="Maya", relationship_score=20, role="Student Council Secretary", club="Debate Club", location="Student Council Room")
        db.add_temporary_companion(sid, "Maya")

        qid = "BNT-HS-01"
        db.upsert_quest(
            session_id=sid,
            quest_id=qid,
            quest_type="Social Mediation",
            title="Persuade the Committee Chair",
            objective="Convince the chair to approve the festival budget.",
            progress="1/2 Stage",
            current_clues="",
            status="Active",
            reward_xp=100,
            reward_gold=30,
            blueprint_id="SOCIAL_MANIPULATION",
            client_npc="Principal Sato",
        )
        wps = [
            {"stage_index": 1, "stage_label": "Go to Student Council Room", "target_location": "Student Council Room", "completion_trigger": "arrival", "status": "completed"},
            {"stage_index": 2, "stage_label": "Negotiate with the Committee Chair", "target_location": "Student Council Room", "target_npc": "Committee Chair", "completion_trigger": "skill_check", "status": "active"},
        ]
        db.save_quest_waypoints(sid, qid, wps, sub_obj_id=None)

        choices = generate_quest_action_choices(sid, current_location="Student Council Room", scen_key="high_school", char=char)
        comp_choices = [c for c in choices if c.get("approach") == "companion_assist"]
        self.assertEqual(len(comp_choices), 1)
        self.assertIn("Maya", comp_choices[0]["label"])
        # Role match ("Debate Club" / "Secretary" matches SOCIAL_MANIPULATION) -> Auto-Success (FREE, requirement 0)
        self.assertEqual(comp_choices[0]["stat"], "FREE")
        self.assertEqual(comp_choices[0]["requirement"], 0)


        # Verify Companion Strike Shield works for temporary hangout companion
        active_wp = db.get_active_waypoint(sid, qid, None)
        q_row = db.get_quest_by_id(sid, qid)
        shield_res = handle_failed_quest_skill_check(sid, q_row, active_wp, "failure", [uid], session=sess)
        self.assertIsNotNone(shield_res)
        self.assertTrue(shield_res.get("shield_absorbed"))
        self.assertEqual(shield_res.get("companion_name"), "Maya")


if __name__ == "__main__":
    unittest.main()

