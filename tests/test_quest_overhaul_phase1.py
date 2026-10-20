"""
tests/test_quest_overhaul_phase1.py
===================================
Comprehensive verification test suite for Quest & Bounty Overhaul Phase 1:
1. Deterministic Two-Layer Blueprint + Genre Archetype mapping & stationary site whitelist.
2. Multi-location enforcement (>= 2 locations) and strict backward compatibility.
3. Named client NPC binding and turn-in seeding on every bounty.
4. Inventory pre-completion auto-advance and delivery consumption.
5. Multi-quantity tracking ('1/3 Iron Ore Collected') and equipped item protection.
6. Stage 2 physical item auto-grant and Story Quest sub-objective parity.
7. Dynamic hybrid NPC schedule waypoint resolution and UI enrichment.
"""
import json
import time
import unittest

import db
import game_engine
from mechanics.narrative.blueprints import (
    BLUEPRINT_DEFINITIONS,
    get_blueprint_for_archetype,
    is_single_location_allowed,
    infer_required_item_and_count_from_text,
    find_matching_inventory_items_for_quest,
)
from mechanics.narrative.bounty import (
    resolve_or_seed_bounty_client,
    generate_bounty_board,
)
from mechanics.world.waypoints import (
    ensure_multi_stage_waypoints,
    resolve_effective_waypoint_location,
    generate_quest_action_choices,
)
from mechanics.world.locations.seeding import ensure_session_locations_seeded
from game_engine.quests import (
    evaluate_quest_state_predicates,
    grant_stage_acquisition_item_if_needed,
    consume_quest_delivery_item_if_needed,
    resolve_pre_turn_quests_and_clues,
)


class TestQuestOverhaulPhase1(unittest.TestCase):

    def setUp(self):
        self.session_id = 99112233
        self.user_id = 88001
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute(
                "INSERT INTO characters (id, user_id, name, char_class, level, is_active, str_) VALUES (?, ?, 'Hero', 'Warrior', 1, 1, 10)",
                (self.user_id, self.user_id)
            )
            conn.execute(
                """INSERT INTO sessions (
                    id, mode, capacity, status, scenario, current_location, current_day, current_minute, host_user_id
                ) VALUES (?, 'solo', 1, 'active', 'fantasy', 'Ruins', 1, 480, ?)""",
                (self.session_id, self.user_id)
            )
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.commit()

    def test_1_blueprint_mapping_and_single_site_whitelist(self):
        """Validates all 10 canonical Blueprints and single-site whitelisting."""
        # 1. Blueprint definitions exist
        self.assertEqual(len(BLUEPRINT_DEFINITIONS), 10)
        expected_bps = {
            "ACQUISITION", "NEUTRALIZATION", "HEIST_INFILTRATION", "INVESTIGATION",
            "SOCIAL_MANIPULATION", "ESCORT_RESCUE", "CONTEST_RIVALRY", "SITE_DEFENSE_RITUAL",
            "EXPLORATION_HAZARD", "INTIMATE_ENCOUNTER"
        }
        self.assertEqual(set(BLUEPRINT_DEFINITIONS.keys()), expected_bps)

        # 2. Key archetype mappings
        mappings = {
            "herb gathering": "ACQUISITION",
            "beast hunt": "NEUTRALIZATION",
            "campus theft": "HEIST_INFILTRATION",
            "infiltrate syndicate": "HEIST_INFILTRATION",
            "forensic autopsy": "INVESTIGATION",
            "blackmail": "SOCIAL_MANIPULATION",
            "convoy escort": "ESCORT_RESCUE",
            "club showdown": "CONTEST_RIVALRY",
            "siege defense": "SITE_DEFENSE_RITUAL",
            "survival": "SITE_DEFENSE_RITUAL",
            "arcane ritual": "SITE_DEFENSE_RITUAL",
            "rune archaeology": "EXPLORATION_HAZARD",
            "seduction": "INTIMATE_ENCOUNTER",
        }
        for arch, expected_bp in mappings.items():
            mapped = get_blueprint_for_archetype(arch)
            self.assertEqual(mapped, expected_bp, f"Archetype '{arch}' mapped to '{mapped}', expected '{expected_bp}'")

        # 3. Single-site whitelist
        self.assertTrue(is_single_location_allowed("SITE_DEFENSE_RITUAL"))
        self.assertTrue(is_single_location_allowed("siege defense"))
        self.assertTrue(is_single_location_allowed("survival"))
        self.assertTrue(is_single_location_allowed("arcane ritual"))
        self.assertFalse(is_single_location_allowed("ACQUISITION"))
        self.assertFalse(is_single_location_allowed("NEUTRALIZATION"))
        self.assertFalse(is_single_location_allowed("HEIST_INFILTRATION"))

    def test_2_multi_location_enforcement_and_backward_compat(self):
        """Validates backward compatibility when secondary_loc/session_id are omitted, and >= 2 locations otherwise."""
        # Backward compatibility: all stages remain at default_loc
        legacy_stages = ensure_multi_stage_waypoints([], default_loc="Academy -> Library", archetype="investigation")
        self.assertEqual(len(legacy_stages), 3)
        self.assertTrue(all(w["target_location"] == "Academy -> Library" for w in legacy_stages))

        # Explicit secondary location supplied: distinct routing enforced
        multi_stages = ensure_multi_stage_waypoints(
            [],
            default_loc="Town Square",
            secondary_loc="Dark Forest",
            archetype="investigation"
        )
        self.assertEqual(len(multi_stages), 3)
        distinct_locs = {w["target_location"] for w in multi_stages}
        self.assertGreaterEqual(len(distinct_locs), 2)
        self.assertIn("Town Square", distinct_locs)
        self.assertIn("Dark Forest", distinct_locs)

        # Stationary whitelist permits single location even when secondary_loc is provided
        stationary_stages = ensure_multi_stage_waypoints(
            [],
            default_loc="Fortress Wall",
            secondary_loc="Distant Woods",
            archetype="siege defense"
        )
        self.assertEqual(len(stationary_stages), 3)
        # In siege defense, defense stages remain anchored at default_loc
        self.assertEqual(stationary_stages[0]["target_location"], "Fortress Wall")
        self.assertEqual(stationary_stages[1]["target_location"], "Fortress Wall")

    def test_3_bounty_client_npc_seeding_and_turn_in_stage(self):
        """Validates client NPC/location seeding and final delivery waypoint binding."""
        client_npc, client_loc = resolve_or_seed_bounty_client(self.session_id, "fantasy")
        self.assertTrue(bool(client_npc))
        self.assertTrue(bool(client_loc))

        session_obj = db.get_session(self.session_id)
        import asyncio
        bounties = asyncio.run(generate_bounty_board(self.session_id, session_obj))
        self.assertGreater(len(bounties), 0)

        for b in bounties:
            self.assertTrue(bool(b.get("blueprint_id")), f"Bounty {b['title']} missing blueprint_id")
            self.assertTrue(bool(b.get("client_npc")), f"Bounty {b['title']} missing client_npc")
            self.assertTrue(bool(b.get("client_location")), f"Bounty {b['title']} missing client_location")

            # Check waypoints for this bounty
            wps = db.get_quest_waypoints(self.session_id, b["quest_id"])
            self.assertGreaterEqual(len(wps), 2)
            final_wp = wps[-1]
            self.assertEqual(final_wp["target_npc"], b["client_npc"])
            self.assertEqual(final_wp["target_location"], b["client_location"])

    def test_4_inventory_pre_completion_and_delivery_consumption(self):
        """Validates that possessing required items auto-advances to delivery, and completion consumes the item."""
        quest_id = "BNT-TEST-ACQ"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=quest_id,
            quest_type="Herb Gathering",
            title="Gather Ancient Relic",
            objective="Retrieve 1 Ancient Relic and deliver to Scholar Marcus at the Library.",
            progress="Find Ancient Relic",
            status="Active",
            reward_xp=150,
            reward_gold=50,
            blueprint_id="ACQUISITION",
            client_npc="Scholar Marcus",
            client_location="Library",
            required_item="Ancient Relic",
            required_item_count=1,
        )
        wps = [
            {"stage_index": 1, "stage_label": "Search for Ancient Relic", "target_location": "Ruins", "completion_trigger": "skill_check", "status": "active"},
            {"stage_index": 2, "stage_label": "Deliver Ancient Relic to Scholar Marcus", "target_location": "Library", "target_npc": "Scholar Marcus", "completion_trigger": "arrival", "status": "locked"},
        ]
        db.save_quest_waypoints(self.session_id, quest_id, wps)

        # Player physically possesses 1 Ancient Relic
        item_id = db.add_item(self.user_id, "Ancient Relic", "Quest Item", "An ancient artifact", slot_cost=0, force=True)
        self.assertIsNotNone(item_id)

        # Evaluate quest state predicates
        eval_res = evaluate_quest_state_predicates(self.session_id, user_id=self.user_id)
        self.assertTrue(any(r.get("type") == "inventory_ready" for r in eval_res))

        # Check waypoint statuses in DB
        wps_after = db.get_quest_waypoints(self.session_id, quest_id)
        self.assertEqual(wps_after[0]["status"], "completed")
        self.assertEqual(wps_after[1]["status"], "active")

        # Check quest progress string
        q_after = db.get_quest_by_id(self.session_id, quest_id)
        self.assertIn("Ready to deliver Ancient Relic", q_after["progress"])

        # Now simulate player arriving at the Library
        session_obj = db.get_session(self.session_id)
        session_obj["current_location"] = "Library"
        turn_res = resolve_pre_turn_quests_and_clues(session_obj, party=[{"user_id": self.user_id}])

        # Quest should be completed!
        self.assertIn(quest_id, turn_res["completed_quests"])

        # Ancient Relic must be consumed from SQLite inventory!
        inv = db.get_inventory(self.user_id)
        matching_after = find_matching_inventory_items_for_quest("Ancient Relic", inv, exclude_equipped=False)
        self.assertEqual(len(matching_after), 0, "Ancient Relic should have been consumed upon quest completion")

    def test_5_multi_quantity_progress_and_equipped_item_protection(self):
        """Validates multi-quantity partial progress and guarantees equipped items are never consumed."""
        quest_id = "BNT-TEST-MULTI"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=quest_id,
            quest_type="Mining Bounty",
            title="Iron Ore Gathering",
            objective="Mine 3 Iron Ore and deliver to Blacksmith Brok at the Forge.",
            progress="Mine Iron Ore",
            status="Active",
            blueprint_id="ACQUISITION",
            client_npc="Blacksmith Brok",
            client_location="Forge",
            required_item="Iron Ore",
            required_item_count=3,
        )
        wps = [
            {"stage_index": 1, "stage_label": "Mine Iron Ore", "target_location": "Mines", "completion_trigger": "skill_check", "status": "active"},
            {"stage_index": 2, "stage_label": "Deliver Iron Ore to Brok", "target_location": "Forge", "target_npc": "Blacksmith Brok", "completion_trigger": "arrival", "status": "locked"},
        ]
        db.save_quest_waypoints(self.session_id, quest_id, wps)

        # 1. Player has 1 unequipped Iron Ore
        db.add_item(self.user_id, "Iron Ore", "Material", "Rough iron ore", slot_cost=0, force=True)

        # 2. Player has an EQUIPPED Iron Ore Ring
        equipped_id = db.add_item(self.user_id, "Iron Ore Ring", "Accessory", "Ring of iron", slot_cost=0, force=True)
        with db.get_conn() as conn:
            conn.execute("UPDATE inventory SET equipped=1 WHERE id=?", (equipped_id,))

        # Evaluate predicates
        eval_res = evaluate_quest_state_predicates(self.session_id, user_id=self.user_id)
        self.assertTrue(any(r.get("type") == "partial_progress" for r in eval_res))

        # Progress should show partial progress '1/3' (ignoring the equipped ring)
        q_after = db.get_quest_by_id(self.session_id, quest_id)
        self.assertEqual(q_after["progress"], "1/3 Iron Ore Collected")

        # Stage 1 must STILL be active
        wps_after = db.get_quest_waypoints(self.session_id, quest_id)
        self.assertEqual(wps_after[0]["status"], "active")

        # Add 2 more unequipped Iron Ore (total 3 unequipped)
        db.add_item(self.user_id, "Iron Ore", "Material", "Rough iron ore", slot_cost=0, force=True)
        db.add_item(self.user_id, "Iron Ore", "Material", "Rough iron ore", slot_cost=0, force=True)

        eval_res2 = evaluate_quest_state_predicates(self.session_id, user_id=self.user_id)
        self.assertTrue(any(r.get("type") == "inventory_ready" for r in eval_res2))

        wps_after2 = db.get_quest_waypoints(self.session_id, quest_id)
        self.assertEqual(wps_after2[0]["status"], "completed")
        self.assertEqual(wps_after2[1]["status"], "active")

        # Now consume items via quest completion
        consume_res = consume_quest_delivery_item_if_needed(self.session_id, q_after, [self.user_id])
        self.assertIn("Consumed 3x Iron Ore", consume_res)

        # Equipped item MUST still exist!
        inv = db.get_inventory(self.user_id)
        eq_item = next((it for it in inv if it["id"] == equipped_id), None)
        self.assertIsNotNone(eq_item, "Equipped Iron Ore Ring must NOT be deleted!")
        self.assertEqual(eq_item["equipped"], 1)

    def test_6_stage2_physical_item_auto_grant_and_story_quest_sub_objective_parity(self):
        """Validates auto-grant of physical items on intermediate stage completion and Story Quest parity."""
        sq_id = "SQ-CH1-PARITY"
        sub_objs = [
            {
                "id": 1,
                "archetype": "Herb Gathering",
                "blueprint_id": "ACQUISITION",
                "text": "Harvest 2 Glow Herbs at the Mystic Grove",
                "required_item": "Glow Herbs",
                "required_item_count": 2,
                "completed": False,
            }
        ]
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=sq_id,
            quest_type="Story Quest",
            title="Chapter 1: The Glow Herb Cure",
            objective="Gather 2 Glow Herbs to brew the medicine.",
            progress="0/1 Cleared",
            status="Active",
            is_story_quest=1,
            sub_objectives=sub_objs,
        )
        sub_wps = [
            {"stage_index": 1, "stage_label": "Harvest Glow Herbs", "target_location": "Grove", "completion_trigger": "skill_check", "status": "active"},
            {"stage_index": 2, "stage_label": "Deliver Glow Herbs to Alchemist", "target_location": "Clinic", "target_npc": "Alchemist", "completion_trigger": "arrival", "status": "locked"},
        ]
        db.save_quest_waypoints(self.session_id, sq_id, sub_wps, sub_obj_id=1)

        # Player does NOT have Glow Herbs
        inv_before = db.get_inventory(self.user_id)
        self.assertEqual(len(find_matching_inventory_items_for_quest("Glow Herbs", inv_before)), 0)

        # Simulate Stage 1 skill check completion
        granted = grant_stage_acquisition_item_if_needed(
            session_id=self.session_id,
            quest=db.get_quest_by_id(self.session_id, sq_id),
            completed_stage_index=1,
            total_stages=2,
            party_user_ids=[self.user_id],
            sub_obj=sub_objs[0],
        )
        self.assertEqual(granted, "Glow Herbs")

        # Verify physical items now exist in SQLite inventory
        inv_after = db.get_inventory(self.user_id)
        matching_after = find_matching_inventory_items_for_quest("Glow Herbs", inv_after)
        self.assertEqual(len(matching_after), 2, "Should have auto-granted exactly 2 physical Glow Herbs")

        # Now evaluate predicates: Stage 1 complete, Stage 2 active
        eval_res = evaluate_quest_state_predicates(self.session_id, user_id=self.user_id)
        self.assertTrue(any(r.get("type") == "inventory_ready" for r in eval_res))

        # Simulate completing Stage 2 (turn-in): consumption removes items
        consume_res = consume_quest_delivery_item_if_needed(
            session_id=self.session_id,
            quest=db.get_quest_by_id(self.session_id, sq_id),
            party_user_ids=[self.user_id],
            sub_obj=sub_objs[0],
        )
        self.assertIn("Consumed 2x Glow Herbs", consume_res)
        inv_final = db.get_inventory(self.user_id)
        self.assertEqual(len(find_matching_inventory_items_for_quest("Glow Herbs", inv_final)), 0)

    def test_7_dynamic_npc_schedule_waypoint_resolution_and_ui_enrichment(self):
        """Validates dynamic NPC schedule waypoint resolution and UI enrichment with [Turn-In: ...] / [Talk to ...]."""
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET scenario='high_school_drama', current_day=1, current_minute=540 WHERE id=?", (self.session_id,))

        ensure_session_locations_seeded(self.session_id, "high_school_drama", char_name="Hero")

        # Add a student contact who has scheduled locations
        db.upsert_contact(
            session_id=self.session_id,
            npc_id="kaito_takahashi",
            name="Kaito Takahashi",
            character_id=self.user_id,
            delta_score=10,
        )

        quest_id = "BNT-SCHEDULE-TEST"
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=quest_id,
            quest_type="Campus Delivery",
            title="Deliver Club Notes",
            objective="Deliver club notes to Kaito Takahashi.",
            progress="Find Kaito",
            status="Active",
            blueprint_id="ACQUISITION",
            client_npc="Kaito Takahashi",
            client_location="Default Hub",
            required_item="Club Notes",
            required_item_count=1,
        )
        wp = {
            "stage_index": 1,
            "stage_label": "Deliver Club Notes to Kaito Takahashi",
            "target_location": "Default Hub",
            "target_npc": "Kaito Takahashi",
            "follow_npc_schedule": 1,
            "required_item": "Club Notes",
            "completion_trigger": "talk_to_npc",
            "status": "active",
        }
        db.save_quest_waypoints(self.session_id, quest_id, [wp])

        # Resolve effective location at minute 540 (Class hours)
        eff_loc_morning = resolve_effective_waypoint_location(self.session_id, wp)
        self.assertTrue(bool(eff_loc_morning))

        # Check UI enrichment on quest dict
        enriched_q = db.get_quest_by_id(self.session_id, quest_id)
        self.assertIsNotNone(enriched_q)
        active_wps = enriched_q.get("active_waypoints", [])
        self.assertGreater(len(active_wps), 0)
        self.assertTrue(bool(active_wps[0].get("effective_location")))

        # Test choice generation when at effective location
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET current_location=?, current_npcs_json=? WHERE id=?",
                (eff_loc_morning, json.dumps(["Kaito Takahashi"]), self.session_id)
            )

        session_obj = db.get_session(self.session_id)
        choices = generate_quest_action_choices(session_obj, [enriched_q])
        self.assertGreater(len(choices), 0)
        labels = [c.get("label", "") for c in choices]
        self.assertTrue(any("[Talk to Kaito Takahashi]" in l or "[Turn-In: Club Notes]" in l for l in labels), f"Generated choices: {labels}")


if __name__ == "__main__":
    unittest.main()
