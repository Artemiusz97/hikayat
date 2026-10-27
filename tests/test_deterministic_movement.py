from __future__ import annotations
import os
import tempfile
import unittest
import db
import db.core
from game_engine.npcs import compute_pre_turn_stage
from mechanics.world.locations.pathfinding import (
    find_spatial_path,
    resolve_flee_destination,
    format_node_hierarchy,
    get_edge_between,
)


class TestDeterministicMovement(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._isolated_db = os.path.join(self._tmp_dir.name, "test_det_movement.db")
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        db.DB_PATH = self._isolated_db
        db.core.DB_PATH = self._isolated_db
        db.init_db()

        self.user_id = 999111222
        base_stats = {"STR": 5, "PER": 5, "END": 5, "CHA": 5, "INT": 5, "AGI": 7, "LUK": 5}
        self.char = db.create_character(
            user_id=self.user_id,
            name="Hiro",
            char_class="Student",
            class_description="Test Student",
            stats=base_stats,
        )
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = db.get_session(self.session_id)
        self.party = [(self.char, db.get_inventory(self.user_id))]

        with db.get_conn() as conn:
            conn.execute("DELETE FROM world_nodes WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM world_edges WHERE session_id = ?", (self.session_id,))

        db.save_world_node(
            self.session_id, "zone_campus", None, "Main Academy Campus",
            node_type="ZONE", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "fac_academic", "zone_campus", "Academic Main Building",
            node_type="FACILITY", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "room_classroom", "fac_academic", "Classroom 2-B",
            node_type="ROOM", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "room_hallway", "fac_academic", "First Floor Corridor",
            node_type="ROOM", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "room_private_dorm", "fac_academic", "Private Bedroom",
            node_type="ROOM", category="residential", privacy_level="private"
        )
        db.save_world_node(
            self.session_id, "fac_library", "zone_campus", "Grand Library",
            node_type="FACILITY", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "room_library_stacks", "fac_library", "Library Stacks",
            node_type="ROOM", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "room_secret_vault", "fac_library", "Concealed Archive",
            node_type="ROOM", category="academic", privacy_level="private",
            state_json={"is_hidden": 1}
        )
        db.save_world_node(
            self.session_id, "room_basement_cellar", "fac_academic", "Basement Cellar",
            node_type="ROOM", category="academic", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "zone_downtown", None, "Downtown District",
            node_type="ZONE", category="commercial", privacy_level="public"
        )
        db.save_world_node(
            self.session_id, "fac_transit_hub", "zone_downtown", "Central Station Hub",
            node_type="FACILITY", category="transit", privacy_level="public",
            is_transit_hub=1
        )

        db.save_world_edge(self.session_id, "room_classroom", "room_hallway", travel_minutes=2, is_bidirectional=1)
        db.save_world_edge(self.session_id, "room_hallway", "fac_academic", travel_minutes=1, is_bidirectional=1)
        db.save_world_edge(self.session_id, "fac_academic", "fac_library", travel_minutes=5, is_bidirectional=1, edge_type="pathway")
        db.save_world_edge(self.session_id, "fac_library", "room_library_stacks", travel_minutes=1, is_bidirectional=1)
        db.save_world_edge(
            self.session_id, "room_library_stacks", "room_secret_vault",
            travel_minutes=1, is_bidirectional=1, is_locked=1, lock_key_item="Vault Key"
        )
        db.save_world_edge(
            self.session_id, "room_hallway", "room_basement_cellar",
            travel_minutes=1, is_bidirectional=0, edge_type="chute"
        )
        db.save_world_edge(
            self.session_id, "fac_academic", "fac_transit_hub",
            travel_minutes=15, is_bidirectional=1, edge_type="transit_hub",
            lock_key_item="Subway Token"
        )

        self.session["current_node_id"] = "room_classroom"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_classroom")
        db.update_session(self.session_id, current_node_id="room_classroom", current_location=self.session["current_location"])

    def tearDown(self):
        if hasattr(db, "close_all_connections"):
            db.close_all_connections()
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

    def test_schema_target_node_authority(self):
        """Choice with explicit target_node_id deterministically moves player to exact node without regex parsing."""
        actions = [{
            "label": "Custom label that has zero movement verbs",
            "target_node_id": "room_hallway",
            "stat": "NONE",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_hallway")
        self.assertIn("First Floor Corridor", stage_info["effective_location"])

    def test_multi_node_automated_pathfinding(self):
        """Multi-edge pathfinding routes across intermediate edges, accumulating exact travel minutes."""
        actions = [{"label": "Visit library", "target_node_id": "room_library_stacks"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")
        self.assertEqual(self.session.get("travel_minutes_elapsed"), 9)

    def test_midway_barrier_threshold_halting(self):
        """Locked edge midway halts player at immediate predecessor node, syncs effective_location, and elapses partial time."""
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})

        actions = [{
            "label": "Sneak into secret archive",
            "target_node_id": "room_secret_vault",
            "check": {"tier": "fail"},
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")
        self.assertIn("Library Stacks", stage_info["effective_location"])
        self.assertEqual(self.session.get("travel_minutes_elapsed"), 9)
        self.assertTrue(any("[STAGE DIRECTION — ACCESS BLOCKED]" in d for d in stage_info["stage_directives"]))

    def test_key_item_unlock_and_reusability(self):
        """Having lock_key_item in inventory unlocks the edge permanently; standard key is retained."""
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})
        db.add_item(self.user_id, "Vault Key", "Key", "Iron vault key", 1)
        party = [(self.char, db.get_inventory(self.user_id))]

        actions = [{"label": "Unlock and enter archive", "target_node_id": "room_secret_vault"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=party)
        self.assertFalse(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "room_secret_vault")

        inv = db.get_inventory(self.user_id)
        self.assertTrue(any(it["name"] == "Vault Key" for it in inv))
        edge = get_edge_between(self.session_id, "room_library_stacks", "room_secret_vault")
        self.assertEqual(edge.get("is_locked"), 0)

    def test_single_use_key_consumed(self):
        """Keys flagged as consumable are consumed upon unlocking."""
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})
        db.add_item(self.user_id, "Vault Key", "Consumable", "Fragile key", 1)

        party = [(self.char, db.get_inventory(self.user_id))]
        actions = [{"label": "Open vault", "target_node_id": "room_secret_vault"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=party)
        self.assertEqual(stage_info["effective_node_id"], "room_secret_vault")

        inv_after = db.get_inventory(self.user_id)
        self.assertFalse(any(it.get("name") == "Vault Key" for it in inv_after))

    def test_skill_check_lockpicking(self):
        """Successful AGI lockpick check unlocks door without requiring key item."""
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})
        with db.get_conn() as conn:
            conn.execute("UPDATE world_edges SET skill_check_type = 'AGI', skill_check_dc = 12 WHERE session_id = ? AND to_node_id = 'room_secret_vault'", (self.session_id,))

        actions = [{
            "label": "Pick the archive lock",
            "target_node_id": "room_secret_vault",
            "stat": "AGI",
            "check": {"tier": "success", "roll": 14},
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertFalse(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "room_secret_vault")

    def test_curfew_gating(self):
        """Movement into curfew-restricted facility after hours is blocked with access halt."""
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE world_nodes SET access_tier = 'curfew_restricted', curfew_start_min = 1200, curfew_end_min = 420 WHERE session_id = ? AND node_id = 'fac_library'",
                (self.session_id,)
            )

        self.session["current_minute"] = 1320
        self.session["current_node_id"] = "fac_academic"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "fac_academic")
        db.update_session_time(self.session_id, current_day=1, current_minute=1320)

        actions = [{"label": "Go to library at night", "target_node_id": "room_library_stacks"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "fac_academic")

    def test_zero_llm_location_hallucination(self):
        """Turn engine and stage manager discard ungrounded LLM location prose when no movement occurred."""
        curr_loc = self.session["current_location"]
        curr_node = self.session["current_node_id"]

        actions = [{"label": "I nod and ask about the math homework", "target_node_id": ""}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertEqual(stage_info["effective_node_id"], curr_node)
        self.assertEqual(stage_info["effective_location"], curr_loc)

    def test_companion_privacy_filtering_and_auto_reunion(self):
        """Entering private room leaves non-romantic companions in hallway; exiting restores them."""
        self.session["current_node_id"] = "room_hallway"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_hallway")
        self.session["temporary_companions"] = [
            {"name": "Aoi", "affinity": 30, "is_romantic": False},
            {"name": "Yuna", "affinity": 90, "is_romantic": True},
        ]

        stage_info = compute_pre_turn_stage(
            self.session, [{"label": "Enter private bedroom", "target_node_id": "room_private_dorm"}], party=self.party
        )
        self.assertEqual(stage_info["effective_node_id"], "room_private_dorm")
        waiting = self.session.get("waiting_outside_companions", [])
        self.assertTrue(any(c["name"] == "Aoi" for c in waiting))
        self.assertTrue(any(c["name"] == "Yuna" for c in stage_info["traveling_companions"]))

        self.session["current_node_id"] = "room_private_dorm"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_private_dorm")
        stage_out = compute_pre_turn_stage(
            self.session, [{"label": "Step back out to hallway", "target_node_id": "room_hallway"}], party=self.party
        )
        self.assertEqual(stage_out["effective_node_id"], "room_hallway")
        self.assertEqual(len(self.session.get("waiting_outside_companions", [])), 0)
        self.assertTrue(any(c["name"] == "Aoi" for c in stage_out["traveling_companions"]))

    def test_fog_of_war_secret_nodes(self):
        """Hidden nodes (is_hidden=1) are barred from pathfinding until discovered."""
        path = find_spatial_path(self.session_id, "room_library_stacks", "room_secret_vault")
        self.assertEqual(path, [])

        path_discovered = find_spatial_path(
            self.session_id, "room_library_stacks", "room_secret_vault",
            discovered_nodes={"room_secret_vault"}
        )
        self.assertEqual(path_discovered, ["room_library_stacks", "room_secret_vault"])

    def test_combat_flee_and_one_way_edge_fallback(self):
        """Fleeing combat retreats along reverse edge; one-way chute cascades to parent facility."""
        self.session["current_node_id"] = "room_classroom"
        self.session["previous_node_id"] = "room_hallway"
        stage_info = compute_pre_turn_stage(
            self.session, [{"label": "Flee for your life!", "intent": "combat", "sub_intent": "combat_flee"}], party=self.party
        )
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_hallway")

        flee_nid, flee_loc = resolve_flee_destination(self.session_id, "room_basement_cellar", "room_hallway")
        self.assertEqual(flee_nid, "fac_academic")
        self.assertIn("Academic Main Building", flee_loc)

    def test_tactical_micro_features_no_node_mutation(self):
        """Action targeting local micro-feature retains current ROOM node ID without mutation."""
        stage_info = compute_pre_turn_stage(self.session, [{"label": "Hide under the teacher's desk"}], party=self.party)
        self.assertEqual(stage_info["effective_node_id"], "room_classroom")

    def test_freeform_text_fuzzy_matching(self):
        """Freeform text 'Head to library stacks' matches reachable node ID."""
        actions = [{"label": "I hurry down the hall and head to library stacks to investigate"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")

    def test_mid_route_ambush_interruption(self):
        """Hostile ambush on intermediate node halts pathfinding at that node and starts combat."""
        db.update_world_node_state(self.session_id, "fac_library", {"active_ambush": True})
        actions = [{"label": "Go to library stacks", "target_node_id": "room_library_stacks"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertEqual(stage_info["effective_node_id"], "fac_library")
        self.assertTrue(any("[STAGE DIRECTION — AMBUSH INTERRUPTION]" in d for d in stage_info["stage_directives"]))

    def test_transit_hub_gating(self):
        """Transit hub edge enforces lock_key_item (Subway Token)."""
        actions = [{"label": "Take transit to Downtown", "target_node_id": "fac_transit_hub"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "fac_academic")

    def test_unmatched_freeform_travel_campus_blocks_vs_open_world_stitches_node(self):
        """D10: Campus blocks unmatched freeform destination (0m elapsed + valid exits); Open-World stitches a 3m dynamic node."""
        # 1. Closed campus (high_school_drama) -> blocked with 0m elapsed
        campus_actions = [{"label": "Walk to the Underwater Volcano Observatory", "intent": "movement"}]
        campus_stage = compute_pre_turn_stage(self.session, campus_actions, party=self.party)
        self.assertEqual(campus_stage["effective_node_id"], "room_classroom")
        self.assertEqual(self.session.get("travel_minutes_elapsed", 0), 0)
        self.assertTrue(any("UNREACHABLE DESTINATION" in d or "ACCESS BLOCKED" in d or "First Floor Corridor" in d for d in campus_stage["stage_directives"]))

        # 2. Open-world (fantasy) -> spawns and stitches a 3m bidirectional child node
        ow_sess_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        db.save_world_node(ow_sess_id, "zone_forest", None, "Whispering Woods", node_type="ZONE", privacy_level="public")
        db.save_world_node(ow_sess_id, "fac_trail", "zone_forest", "Mossy Trailhead", node_type="FACILITY", privacy_level="public")
        ow_loc = format_node_hierarchy(ow_sess_id, "fac_trail")
        db.update_session(ow_sess_id, current_node_id="fac_trail", current_location=ow_loc)
        ow_session = db.get_session(ow_sess_id)

        ow_actions = [{"label": "Head toward Moonlit Druid Grove", "intent": "movement"}]
        ow_stage = compute_pre_turn_stage(ow_session, ow_actions, party=self.party)
        self.assertTrue(ow_stage["is_movement"])
        self.assertNotEqual(ow_stage["effective_node_id"], "fac_trail")
        self.assertIn("Moonlit Druid Grove", ow_stage["effective_location"])
        self.assertEqual(ow_session.get("travel_minutes_elapsed"), 3)
        edge = get_edge_between(ow_sess_id, "fac_trail", ow_stage["effective_node_id"])
        self.assertIsNotNone(edge)
        self.assertEqual(edge.get("is_bidirectional"), 1)

    def test_multiplayer_coop_local_first_priority_blocks_conflicting_party_movement(self):
        """D15: Teammate performing local action blocks conflicting party room transition and emits PARTY COHESION directive."""
        coop_actions = [
            {"label": "Head out to the First Floor Corridor", "target_node_id": "room_hallway", "intent": "movement"},
            {"label": "Inspect the chalkboard cipher carefully", "intent": "investigate_clue", "stat": "INT"},
        ]
        stage_info = compute_pre_turn_stage(self.session, coop_actions, party=self.party)
        self.assertFalse(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_classroom")
        self.assertTrue(any("PARTY COHESION" in d for d in stage_info["stage_directives"]))


if __name__ == "__main__":
    unittest.main()
