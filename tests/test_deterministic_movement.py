import unittest
import db
import config
from game_engine.npcs import compute_pre_turn_stage
from mechanics.world.locations.pathfinding import (
    find_spatial_path,
    evaluate_spatial_route,
    resolve_flee_destination,
    match_freeform_spatial_destination,
    format_node_hierarchy,
    get_edge_between,
)
from mechanics.world.locations.movement import reconcile_movement_location


class TestDeterministicMovement(unittest.TestCase):
    def setUp(self):
        db.init_db()
        config.DETERMINISTIC_MOVEMENT = True
        self.user_id = 999111222
        self.session_id = 888222111

        for c in db.get_user_characters(self.user_id):
            db.delete_character(self.user_id, c["id"])

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

        # Seed spatial test graph in SQLite
        with db.get_conn() as conn:
            conn.execute("DELETE FROM world_nodes WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM world_edges WHERE session_id = ?", (self.session_id,))

        # Nodes
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

        # Edges
        db.save_world_edge(self.session_id, "room_classroom", "room_hallway", travel_minutes=2, is_bidirectional=1)
        db.save_world_edge(self.session_id, "room_hallway", "fac_academic", travel_minutes=1, is_bidirectional=1)
        db.save_world_edge(self.session_id, "fac_academic", "fac_library", travel_minutes=5, is_bidirectional=1, edge_type="pathway")
        db.save_world_edge(self.session_id, "fac_library", "room_library_stacks", travel_minutes=1, is_bidirectional=1)
        db.save_world_edge(
            self.session_id, "room_library_stacks", "room_secret_vault",
            travel_minutes=1, is_bidirectional=1, is_locked=1, lock_key_item="Vault Key"
        )
        # One-way emergency trapdoor/chute: hallway -> basement cellar (bidirectional = 0)
        db.save_world_edge(
            self.session_id, "room_hallway", "room_basement_cellar",
            travel_minutes=1, is_bidirectional=0, edge_type="chute"
        )
        # Transit edge with fare key item
        db.save_world_edge(
            self.session_id, "fac_academic", "fac_transit_hub",
            travel_minutes=15, is_bidirectional=1, edge_type="transit_hub",
            lock_key_item="Subway Token"
        )

        # Set session current location
        self.session["current_node_id"] = "room_classroom"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_classroom")
        db.update_session(self.session_id, current_node_id="room_classroom", current_location=self.session["current_location"])

    def tearDown(self):
        config.DETERMINISTIC_MOVEMENT = True
        for c in db.get_user_characters(self.user_id):
            db.delete_character(self.user_id, c["id"])
        if hasattr(self, "session_id"):
            db.delete_session(self.session_id)

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
        actions = [{
            "label": "Visit library",
            "target_node_id": "room_library_stacks",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")
        # 2 (classroom->hallway) + 1 (hallway->academic) + 5 (academic->library) + 1 (library->stacks) = 9 mins
        self.assertEqual(self.session.get("travel_minutes_elapsed"), 9)

    def test_midway_barrier_threshold_halting(self):
        """Locked edge midway halts player at immediate predecessor node and elapses partial travel time."""
        # Unhide vault for pathfinding so route is attempted
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})

        actions = [{
            "label": "Sneak into secret archive",
            "target_node_id": "room_secret_vault",
            "check": {"tier": "fail"},
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        # Halts at preceding node before locked barrier: room_library_stacks
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")
        # Elapsed time is 9 minutes (up to stacks), NOT 12 minutes (which would include the locked vault)
        self.assertEqual(self.session.get("travel_minutes_elapsed"), 9)
        self.assertTrue(any("[STAGE DIRECTION — ACCESS BLOCKED]" in d for d in stage_info["stage_directives"]))

    def test_key_item_unlock_and_reusability(self):
        """Having lock_key_item in inventory unlocks the edge permanently; standard key is retained."""
        # Unhide vault
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})

        # Add Vault Key to inventory
        db.add_item(self.user_id, "Vault Key", "Key", "Iron vault key", 1)
        party = [(self.char, db.get_inventory(self.user_id))]

        actions = [{
            "label": "Unlock and enter archive",
            "target_node_id": "room_secret_vault",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=party)
        self.assertFalse(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "room_secret_vault")

        # Key is retained in inventory (reusable, A3)
        inv = db.get_inventory(self.user_id)
        self.assertTrue(any(it["name"] == "Vault Key" for it in inv))

        # Edge in DB is now permanently unlocked
        edge = get_edge_between(self.session_id, "room_library_stacks", "room_secret_vault")
        self.assertEqual(edge.get("is_locked"), 0)

    def test_single_use_key_consumed(self):
        """Keys flagged as consumable are consumed upon unlocking."""
        db.update_world_node_state(self.session_id, "room_secret_vault", {"is_hidden": 0})

        # Add consumable key
        db.add_item(self.user_id, "Vault Key", "Consumable", "Fragile key", 1)

        party = [(self.char, db.get_inventory(self.user_id))]
        actions = [{"label": "Open vault", "target_node_id": "room_secret_vault"}]
        stage_info = compute_pre_turn_stage(self.session, actions, party=party)
        self.assertEqual(stage_info["effective_node_id"], "room_secret_vault")

        # Consumable key was consumed from party inventory and database
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
        # Set node curfew to night (20:00 to 07:00 => 1200 to 420 mins)
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE world_nodes SET access_tier = 'curfew_restricted', curfew_start_min = 1200, curfew_end_min = 420 WHERE session_id = ? AND node_id = 'fac_library'",
                (self.session_id,)
            )

        # Session time: 22:00 (1320 minutes)
        self.session["current_minute"] = 1320
        self.session["current_node_id"] = "fac_academic"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "fac_academic")
        db.update_session_time(self.session_id, current_day=1, current_minute=1320)

        actions = [{
            "label": "Go to library at night",
            "target_node_id": "room_library_stacks",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        # Halts at preceding open node (fac_academic)
        self.assertEqual(stage_info["effective_node_id"], "fac_academic")

    def test_zero_llm_location_hallucination(self):
        """Turn engine and stage manager discard ungrounded LLM location prose when no movement occurred."""
        from game_engine.npcs.stage_manager import compute_pre_turn_stage
        # Turn with non-movement conversation
        curr_loc = self.session["current_location"]
        curr_node = self.session["current_node_id"]

        actions = [{
            "label": "I nod and ask about the math homework",
            "target_node_id": "",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertEqual(stage_info["effective_node_id"], curr_node)
        self.assertEqual(stage_info["effective_location"], curr_loc)

    def test_companion_privacy_filtering(self):
        """Entering private room leaves non-romantic companions in hallway; romantic partner follows."""
        self.session["current_node_id"] = "room_hallway"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_hallway")

        # Two companions: Aoi (platonic, affinity 30) and Yuna (romantic, affinity 90)
        comp_platonic = {"name": "Aoi", "affinity": 30, "is_romantic": False}
        comp_romantic = {"name": "Yuna", "affinity": 90, "is_romantic": True}
        self.session["temporary_companions"] = [comp_platonic, comp_romantic]

        actions = [{
            "label": "Enter private bedroom",
            "target_node_id": "room_private_dorm",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertEqual(stage_info["effective_node_id"], "room_private_dorm")

        # Platonic companion Aoi is waiting outside; Yuna followed inside
        waiting = self.session.get("waiting_outside_companions", [])
        self.assertTrue(any(c["name"] == "Aoi" for c in waiting))
        self.assertFalse(any(c["name"] == "Yuna" for c in waiting))
        self.assertTrue(any(c["name"] == "Yuna" for c in stage_info["traveling_companions"]))

    def test_companion_auto_reunion(self):
        """Exiting a private room back into public hallway restores waiting companions."""
        # Set up player inside private dorm with companion waiting outside
        self.session["current_node_id"] = "room_private_dorm"
        self.session["current_location"] = format_node_hierarchy(self.session_id, "room_private_dorm")
        self.session["waiting_outside_companions"] = [{"name": "Aoi", "affinity": 30}]

        actions = [{
            "label": "Step back out to hallway",
            "target_node_id": "room_hallway",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertEqual(stage_info["effective_node_id"], "room_hallway")

        # Aoi re-joined active traveling party (A9)
        self.assertEqual(len(self.session.get("waiting_outside_companions", [])), 0)
        self.assertTrue(any(c["name"] == "Aoi" for c in stage_info["traveling_companions"]))

    def test_fog_of_war_secret_nodes(self):
        """Hidden nodes (is_hidden=1) are barred from pathfinding until discovered."""
        # Vault is hidden (is_hidden=1) and undiscovered
        path = find_spatial_path(self.session_id, "room_library_stacks", "room_secret_vault")
        self.assertEqual(path, [])

        # Once discovered, path is found
        path_discovered = find_spatial_path(
            self.session_id, "room_library_stacks", "room_secret_vault",
            discovered_nodes={"room_secret_vault"}
        )
        self.assertEqual(path_discovered, ["room_library_stacks", "room_secret_vault"])

    def test_combat_flee_displacement(self):
        """Fleeing combat retreats along reverse edge to previous_node_id."""
        self.session["current_node_id"] = "room_classroom"
        self.session["previous_node_id"] = "room_hallway"

        actions = [{
            "label": "Flee for your life!",
            "intent": "combat",
            "sub_intent": "combat_flee",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        # Retreats to previous node (room_hallway)
        self.assertEqual(stage_info["effective_node_id"], "room_hallway")

    def test_one_way_edge_flee_fallback(self):
        """Retreating from a room reached via a one-way edge cascades to parent facility entrance."""
        # Player was dropped into basement cellar via one-way chute from room_hallway
        self.session["current_node_id"] = "room_basement_cellar"
        self.session["previous_node_id"] = "room_hallway"

        flee_nid, flee_loc = resolve_flee_destination(
            self.session_id, "room_basement_cellar", "room_hallway"
        )
        # Cannot climb back up the one-way chute; cascades to parent facility
        self.assertEqual(flee_nid, "fac_academic")
        self.assertIn("Academic Main Building", flee_loc)

    def test_tactical_micro_features_no_node_mutation(self):
        """Action targeting local micro-feature retains current ROOM node ID without mutation."""
        actions = [{
            "label": "Hide under the teacher's desk",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        # Remained in room_classroom without changing node ID
        self.assertEqual(stage_info["effective_node_id"], "room_classroom")

    def test_freeform_text_fuzzy_matching(self):
        """Freeform text 'Head to library stacks' matches reachable node ID."""
        actions = [{
            "label": "I hurry down the hall and head to library stacks to investigate",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["is_movement"])
        self.assertEqual(stage_info["effective_node_id"], "room_library_stacks")

    def test_mid_route_ambush_interruption(self):
        """Hostile ambush on intermediate node halts pathfinding at that node and starts combat."""
        # Set ambush on intermediate node fac_library
        db.update_world_node_state(self.session_id, "fac_library", {"active_ambush": True})

        actions = [{
            "label": "Go to library stacks",
            "target_node_id": "room_library_stacks",
        }]
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        # Halts at intermediate node fac_library where ambush occurred
        self.assertEqual(stage_info["effective_node_id"], "fac_library")
        self.assertTrue(any("[STAGE DIRECTION — AMBUSH INTERRUPTION]" in d for d in stage_info["stage_directives"]))

    def test_transit_hub_gating_and_rollback(self):
        """Transit hub edge enforces lock_key_item; DETERMINISTIC_MOVEMENT=False restores legacy fallback."""
        actions = [{
            "label": "Take transit to Downtown",
            "target_node_id": "fac_transit_hub",
        }]
        # 1. Blocked without Subway Token
        stage_info = compute_pre_turn_stage(self.session, actions, party=self.party)
        self.assertTrue(stage_info["access_gate"]["gated"])
        self.assertEqual(stage_info["effective_node_id"], "fac_academic")

        # 2. Rollback guard: DETERMINISTIC_MOVEMENT = False restores legacy behavior
        config.DETERMINISTIC_MOVEMENT = False
        reconciled = reconcile_movement_location(
            self.session_id,
            current_loc="Main Academy Campus ➔ Academic Building ➔ Classroom 2-B",
            result_loc="Main Academy Campus ➔ First Floor Corridor ➔ Main Area",
            action_text="Step out into the hallway",
        )
        self.assertIn("School Hallways", reconciled)


if __name__ == "__main__":
    unittest.main()
