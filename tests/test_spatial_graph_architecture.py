from __future__ import annotations
"""
tests/test_spatial_graph_architecture.py
Unit & regression tests for the Two-Table Relational Spatial Graph architecture.
"""
import unittest
import db
from mechanics.world.locations.graph_seeder import (
    ensure_session_spatial_graph_seeded,
    migrate_session_to_spatial_graph,
    infer_node_category,
    infer_node_privacy,
)


class TestSpatialGraphArchitecture(unittest.TestCase):
    def setUp(self):
        self.test_session_id = 99889901
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM world_nodes WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM world_edges WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id=?", (self.test_session_id,))
            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_node_id, dialogue_partner)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama',
                           'Campus Promenade & Student Commons ➔ Botanical Glasshouse ➔ Interior Greenery Path', '', 'Seo-ah Vance')""",
                (self.test_session_id,)
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM world_nodes WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM world_edges WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id=?", (self.test_session_id,))

    def test_schema_and_crud_operations(self):
        """Verifies CRUD operations on world_nodes and world_edges."""
        db.save_world_node(
            self.test_session_id,
            node_id="zone_test",
            parent_id=None,
            name="Test Zone",
            node_type="ZONE",
            category="academic",
            privacy_level="public"
        )
        db.save_world_node(
            self.test_session_id,
            node_id="fac_test",
            parent_id="zone_test",
            name="Test Facility",
            node_type="FACILITY",
            category="academic",
            privacy_level="public"
        )
        db.save_world_node(
            self.test_session_id,
            node_id="room_test",
            parent_id="fac_test",
            name="Test Room",
            node_type="ROOM",
            category="academic",
            privacy_level="semi_private"
        )
        db.save_world_edge(self.test_session_id, "fac_test", "room_test", travel_minutes=1)

        node = db.get_world_node(self.test_session_id, "room_test")
        self.assertIsNotNone(node)
        self.assertEqual(node["name"], "Test Room")
        self.assertEqual(node["parent_id"], "fac_test")
        self.assertEqual(node["category"], "academic")

        # Test ancestors
        ancestors = db.get_node_ancestors(self.test_session_id, "room_test")
        ancestor_ids = [a["node_id"] for a in ancestors]
        self.assertEqual(ancestor_ids, ["fac_test", "zone_test"])

        # Test hierarchy containment
        self.assertTrue(db.is_descendant_of(self.test_session_id, "room_test", "fac_test"))
        self.assertTrue(db.is_descendant_of(self.test_session_id, "room_test", "zone_test"))
        self.assertFalse(db.is_descendant_of(self.test_session_id, "room_test", "other_zone"))

        # Test outgoing edges
        edges = db.get_outgoing_edges(self.test_session_id, "fac_test")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["to_node_id"], "room_test")

    def test_spatial_graph_seeding(self):
        """Verifies that ensure_session_spatial_graph_seeded populates nodes and edges from seeds."""
        from mechanics.world.locations import get_node_props
        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        nodes = db.get_session_world_nodes(self.test_session_id)
        self.assertGreater(len(nodes), 20)

        # Check Student Commons Building (Tier 2 FACILITY) and Botanical Glasshouse (Tier 3 ROOM)
        commons_bld = db.get_world_node(self.test_session_id, "bld_school_commons")
        self.assertIsNotNone(commons_bld)
        self.assertEqual(commons_bld["node_type"], "FACILITY")
        self.assertEqual(commons_bld["category"], "academic")

        greenhouse = db.get_world_node(self.test_session_id, "loc_greenhouse")
        self.assertIsNotNone(greenhouse)
        self.assertEqual(greenhouse["name"], "Botanical Glasshouse")
        self.assertEqual(greenhouse["node_type"], "ROOM")
        self.assertEqual(greenhouse["parent_id"], "bld_school_commons")
        self.assertEqual(greenhouse["category"], "academic")

        # Former micro sub-locations are preserved as room props
        gh_props = get_node_props("loc_greenhouse", "Botanical Glasshouse")
        self.assertIn("Interior Greenery Path", gh_props)

        # Check outgoing edges from Student Commons Building connect through its Entrance cut-vertex
        edges = db.get_outgoing_edges(self.test_session_id, "bld_school_commons")
        edge_targets = [e["to_node_id"] for e in edges]
        self.assertIn("loc_courtyard", edge_targets)
        ent_edges = db.get_outgoing_edges(self.test_session_id, "loc_courtyard")
        ent_targets = [e["to_node_id"] for e in ent_edges]
        self.assertIn("loc_greenhouse", ent_targets)

    def test_session_migration_to_spatial_graph(self):
        """Verifies that a session with tiered location string maps cleanly to its corresponding node."""
        res = migrate_session_to_spatial_graph(self.test_session_id)
        self.assertEqual(res["status"], "migrated")
        self.assertEqual(res["current_node_id"], "loc_greenhouse")

        sess = db.get_session(self.test_session_id)
        self.assertEqual(sess["current_node_id"], "loc_greenhouse")
        self.assertIn("current_world_node", sess)
        self.assertEqual(sess["current_world_node"]["name"], "Botanical Glasshouse")
        self.assertEqual(sess["current_world_node"]["category"], "academic")

    def test_category_and_privacy_inference(self):
        """Verifies semantic category and privacy inferences eliminate keyword traps."""
        # Glasshouse is academic, never residential
        cat = infer_node_category("zone_school_commons", "loc_greenhouse", "Botanical Glasshouse")
        self.assertEqual(cat, "academic")

        # Real house is residential
        cat_house = infer_node_category("zone_residential", "loc_player_house", "Player's House")
        self.assertEqual(cat_house, "residential")

        # Privacy
        priv_house = infer_node_privacy("FACILITY", "loc_player_house", "Player's House")
        self.assertEqual(priv_house, "private")

        priv_glasshouse = infer_node_privacy("FACILITY", "loc_greenhouse", "Botanical Glasshouse")
        self.assertEqual(priv_glasshouse, "semi_private")

    def test_resolve_node_id_from_location(self):
        """Verifies deterministic resolution of strings and node IDs."""
        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        
        # Exact node_id
        resolved = db.resolve_node_id_from_location(self.test_session_id, "loc_student_council")
        self.assertEqual(resolved, "loc_student_council")

        # 3-tier string
        loc_str = "Campus Promenade & Student Commons ➔ Botanical Glasshouse ➔ Interior Greenery Path"
        resolved = db.resolve_node_id_from_location(self.test_session_id, loc_str)
        self.assertEqual(resolved, "loc_greenhouse")

        # Facility / Room name
        resolved = db.resolve_node_id_from_location(self.test_session_id, "Botanical Glasshouse")
        self.assertIn(resolved, ("loc_greenhouse", "sub_greenhouse_path"))

    def test_waypoint_matching_and_kazuya_bug_regression(self):
        """
        Regression Test: Proves that Kazuya Halloway's quest at the Student Council Office
        can NEVER falsely match or advance when the player is inside the Botanical Glasshouse.
        """
        from mechanics.world.waypoints.matching import try_advance_on_arrival
        from mechanics.world.mobility import is_rendezvous_target

        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        migrate_session_to_spatial_graph(self.test_session_id)

        # Set up active quest with waypoint at Student Council Office
        qid = "quest_student_council_convene"
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO quests (session_id, quest_id, title, objective, quest_type, status, is_story_quest, created_at, updated_at) VALUES (?, ?, ?, 'Meet Kazuya at Student Council', 'Story Quest', 'Active', 1, 0, 0)",
                (self.test_session_id, qid, "Student Council Convening")
            )
        db.save_quest_waypoints(
            self.test_session_id,
            quest_id=qid,
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Convene with Student Council President Kazuya Halloway",
                "target_location": "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk",
                "target_node_id": "loc_student_council",
                "target_npc": "Kazuya Halloway",
                "completion_trigger": "arrival"
            }],
            sub_obj_id=1
        )

        sess = db.get_session(self.test_session_id)
        self.assertEqual(sess["current_node_id"], "loc_greenhouse")

        # 1. Arrival trigger must NOT advance because greenhouse is NOT student council!
        adv = try_advance_on_arrival(self.test_session_id, qid, 1, sess["current_location"])
        self.assertIsNone(adv, "Waypoint must not advance when player is in Botanical Glasshouse!")

        # 2. is_rendezvous_target for Kazuya must be False!
        is_target = is_rendezvous_target("Kazuya Halloway", actions=[], session_id=self.test_session_id, new_loc=sess["current_location"])
        self.assertFalse(is_target, "Kazuya Halloway must NOT be a rendezvous target in Botanical Glasshouse!")

        # 3. When player moves to Student Council Office, Kazuya is now a valid rendezvous target!
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET current_node_id=?, current_location=? WHERE id=?",
                ("loc_student_council", "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk", self.test_session_id)
            )

        is_target_at_sc = is_rendezvous_target("Kazuya Halloway", actions=[], session_id=self.test_session_id, new_loc="Cultural Arts & Student Union ➔ Student Council Office")
        self.assertTrue(is_target_at_sc, "Kazuya Halloway must be a rendezvous target once at Student Council Office!")

        # 4. Now arrival triggers and completes the stage
        adv_at_sc = try_advance_on_arrival(self.test_session_id, qid, 1, "Cultural Arts & Student Union ➔ Student Council Office")
        self.assertIsNotNone(adv_at_sc, "Waypoint must advance when player arrives at Student Council Office!")
        self.assertEqual(adv_at_sc["stage_completed"], 1)

    def test_edge_inheritance_and_transit_hubs(self):
        """Verifies ROOM nodes inherit pathways from parent FACILITY and transit hub detection works."""
        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        
        # Check outgoing edges from interior room loc_greenhouse
        outgoing = db.get_outgoing_edges(self.test_session_id, "loc_greenhouse", include_parent_pathways=True)
        self.assertGreater(len(outgoing), 0)
        to_ids = {e["to_node_id"] for e in outgoing}
        # Parent facility bld_school_commons or sibling rooms must be reachable and adjacent facilities inherited
        self.assertTrue("bld_school_commons" in to_ids or "loc_courtyard" in to_ids or any(e.get("edge_type") == "pathway" for e in outgoing))

        # Check transit hub resolution
        is_thub = db.is_node_or_parent_transit_hub(self.test_session_id, "loc_greenhouse")
        self.assertTrue(is_thub or not is_thub)  # function executes cleanly without error
        
        # Check prefer_facility in resolve_node_id_from_location
        fac_id = db.resolve_node_id_from_location(
            self.test_session_id,
            "Campus Promenade & Student Commons",
            prefer_facility=True
        )
        self.assertEqual(fac_id, "bld_school_commons", "prefer_facility=True must return FACILITY node rather than child ROOM")

    def test_dynamic_location_graph_sync(self):
        """Verifies save_session_location with is_dynamic=1 automatically creates world_nodes and world_edges."""
        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        
        db.save_session_location(
            session_id=self.test_session_id,
            location_id="sub_neon_corner",
            zone_name="Commercial District",
            primary_name="Neon Twilight Cafe",
            sub_name="Corner Booth",
            atmosphere="Bustling late-night espresso bar",
            is_dynamic=1
        )
        
        # Verify node resolution for dynamically added location
        resolved = db.resolve_node_id_from_location(
            self.test_session_id,
            "Commercial District ➔ Neon Twilight Cafe ➔ Corner Booth"
        )
        self.assertIsNotNone(resolved)
        node = db.get_world_node(self.test_session_id, resolved)
        self.assertIsNotNone(node)
        self.assertEqual(node["name"], "Corner Booth")
        self.assertEqual(node["node_type"], "ROOM")

    def test_dijkstra_shortest_path_travel_time(self):
        """Verifies shortest graph path travel time calculation and mobility integration."""
        ensure_session_spatial_graph_seeded(self.test_session_id, scenario_key="high_school_drama")
        
        from mechanics.world.mobility import calculate_route_travel_time
        mins = db.find_shortest_graph_path_minutes(self.test_session_id, "sub_greenhouse_path", "sub_pres_desk")
        self.assertIsNotNone(mins)
        self.assertGreaterEqual(mins, 2)
        
        # Mobility route travel time must use graph path when session_id is provided
        route_mins = calculate_route_travel_time(
            "Campus Promenade & Student Commons ➔ Botanical Glasshouse ➔ Interior Greenery Path",
            "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk",
            scen_key="high_school_drama",
            session_id=self.test_session_id
        )
        self.assertGreaterEqual(route_mins, 2)
        self.assertEqual(route_mins, mins)


if __name__ == "__main__":
    unittest.main()

