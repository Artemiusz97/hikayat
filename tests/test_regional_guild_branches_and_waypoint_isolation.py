import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import mechanics.world.locations as locs
import mechanics.world.waypoints as waypoints


class TestRegionalGuildBranchesAndWaypointIsolation(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 987654321
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def test_clean_zone_short_name(self):
        """Verify clean extraction of short region names."""
        self.assertEqual(locs.get_clean_zone_short_name("Forest of Sunlit Vale"), "Sunlit Vale")
        self.assertEqual(locs.get_clean_zone_short_name("Royal Capital of Lunaria"), "Lunaria")
        self.assertEqual(locs.get_clean_zone_short_name("Central Farmlands & Plains"), "Farmlands")
        self.assertEqual(locs.get_clean_zone_short_name("High Mountain Range"), "High Mountain")

    def test_regional_guild_naming(self):
        """Verify major cities get headquarters/hall, while regional/frontier areas get branch/outpost."""
        self.assertEqual(locs.get_regional_guild_name("Royal Capital of Lunaria"), "Adventurers' Guild Headquarters")
        self.assertEqual(locs.get_regional_guild_name("Imperial Capital"), "Adventurers' Guild Headquarters")
        self.assertEqual(locs.get_regional_guild_name("Forest of Sunlit Vale"), "Guild Outpost: Sunlit Vale")
        self.assertEqual(locs.get_regional_guild_name("Central Farmlands & Plains"), "Guild Branch: Farmlands")

    def test_parse_tiered_location_auto_qualifies_regional_guilds(self):
        """Verify parse_tiered_location auto-names generic Guild Hall into a regional branch outside the capital."""
        z, p, s = locs.parse_tiered_location("Forest of Sunlit Vale ➔ Adventurers' Guild Hall ➔ Counter", scenario_key="fantasy")
        self.assertEqual(z, "Forest of Sunlit Vale")
        self.assertEqual(p, "Guild Outpost: Sunlit Vale")
        self.assertEqual(s, "Counter")

        # Capital retains main guild name
        zc, pc, sc = locs.parse_tiered_location("Royal Capital of Lunaria ➔ Adventurers' Guild Hall ➔ Counter", scenario_key="fantasy")
        self.assertEqual(zc, "Royal Capital of Lunaria")
        self.assertEqual(pc, "Adventurers' Guild Hall")

    def test_waypoint_marker_isolation_across_zones(self):
        """Verify that a story quest in the Capital does not leak its ⭐ marker into another zone's guild/outpost."""
        kingdom_name = locs.get_session_kingdom_name(self.test_session_id, "fantasy")
        capital_zone = f"Royal Capital of {kingdom_name}"
        forest_zone = locs.get_session_forest_name(self.test_session_id, "fantasy")
        short_forest = locs.get_clean_zone_short_name(forest_zone)
        forest_guild = f"Guild Outpost: {short_forest}"

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest)
                   VALUES (?, 'story_ch1', 'The Seventh Sigil', 'Consult Guildmaster', 'Active', 1)""",
                (self.test_session_id,)
            )
            conn.commit()

        db.save_quest_waypoints(
            session_id=self.test_session_id,
            quest_id="story_ch1",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Report to the Guild",
                "target_location": f"{capital_zone} ➔ Adventurers' Guild Hall",
                "completion_trigger": "arrival"
            }],
            sub_obj_id=1
        )

        # Seed Capital Guild Hall and Forest Outpost in session
        locs.process_llm_location_update(self.test_session_id, f"{capital_zone} ➔ Adventurers' Guild Hall ➔ Counter", "fantasy")
        locs.process_llm_location_update(self.test_session_id, f"{forest_zone} ➔ {forest_guild} ➔ Counter", "fantasy")

        # Check waypoint markers
        wp_markers = waypoints.get_location_waypoint_markers(self.test_session_id)
        
        # Capital Guild must have marker
        cap_key = f"{capital_zone} ➔ Adventurers' Guild Hall"
        self.assertIn(cap_key, wp_markers)
        self.assertTrue(any("⭐" in tag for tag in wp_markers[cap_key]))

        # Forest Outpost must NOT have marker
        forest_key = f"{forest_zone} ➔ {forest_guild}"
        self.assertNotIn(forest_key, wp_markers)

        # Check zone summary tree
        summary = locs.get_zone_summary_tree(self.test_session_id, "fantasy")
        capital_summary = next(z for z in summary if capital_zone == z["zone_name"])
        forest_summary = next(z for z in summary if forest_zone == z["zone_name"])

        capital_guild = next(p for p in capital_summary["primary_locations"] if "Guild" in p["name"])
        forest_outpost = next(p for p in forest_summary["primary_locations"] if "Guild" in p["name"] or "Outpost" in p["name"])

        self.assertIn("⭐", capital_guild["badges"])
        self.assertNotIn("⭐", forest_outpost["badges"])


if __name__ == "__main__":
    unittest.main()
