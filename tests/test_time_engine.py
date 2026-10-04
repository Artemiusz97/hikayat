import os
import tempfile
import unittest
import json

import db
from mechanics.system.time_engine import (
    DAYS_OF_WEEK,
    format_clock,
    get_time_of_day_phase,
    get_day_of_week,
    format_time_header,
    is_sleep_time,
    is_sleep_action,
    calculate_action_time_cost,
    advance_time,
    apply_sleep_rest,
    check_and_apply_fatigue,
    format_llm_time_context
)


class TestTimeEngine(unittest.TestCase):

    def setUp(self):
        db.init_db()
        db.delete_character(12345)

        # Create a sample character and session
        self.char = db.create_character(
            user_id=12345,
            name="Aiden",
            char_class="Student",
            scenario="high_school_drama"
        )
        self.session_id = self._create_test_session()

    def tearDown(self):
        db.delete_character(12345)
        if getattr(self, "session_id", None):
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, self.session_id)

    def _create_test_session(self, scenario="high_school_drama", current_day=1, current_minute=480):
        with db.get_conn() as conn:
            cur = conn.execute("""
                INSERT INTO sessions (
                    mode, capacity, status, turn_order, scenario, current_day, current_minute, consecutive_days_awake
                ) VALUES ('solo', 1, 'active', ?, ?, ?, ?, 0)
            """, (json.dumps([12345]), scenario, current_day, current_minute))
            return cur.lastrowid

    def test_clock_formatting(self):
        self.assertEqual(format_clock(0), "00:00")
        self.assertEqual(format_clock(480), "08:00")
        self.assertEqual(format_clock(875), "14:35")
        self.assertEqual(format_clock(1335), "22:15")
        self.assertEqual(format_clock(1439), "23:59")
        self.assertEqual(format_clock(1440), "00:00")  # wrap around

    def test_weekday_rotation(self):
        self.assertEqual(get_day_of_week(1), "Monday")
        self.assertEqual(get_day_of_week(2), "Tuesday")
        self.assertEqual(get_day_of_week(3), "Wednesday")
        self.assertEqual(get_day_of_week(4), "Thursday")
        self.assertEqual(get_day_of_week(5), "Friday")
        self.assertEqual(get_day_of_week(6), "Saturday")
        self.assertEqual(get_day_of_week(7), "Sunday")
        self.assertEqual(get_day_of_week(8), "Monday")
        self.assertEqual(get_day_of_week(15), "Monday")

    def test_time_of_day_phases(self):
        # 06:00 -> Early Morning (Dawn)
        phase, emoji, _ = get_time_of_day_phase(360)
        self.assertEqual(phase, "Early Morning")
        self.assertEqual(emoji, "🌅")

        # 10:00 -> Morning
        phase, emoji, _ = get_time_of_day_phase(600)
        self.assertEqual(phase, "Morning")
        self.assertEqual(emoji, "☀️")

        # 14:00 -> Afternoon
        phase, emoji, _ = get_time_of_day_phase(840)
        self.assertEqual(phase, "Afternoon")
        self.assertEqual(emoji, "☀️")

        # 18:00 -> Evening
        phase, emoji, _ = get_time_of_day_phase(1080)
        self.assertEqual(phase, "Evening")
        self.assertEqual(emoji, "🌇")

        # 22:00 -> Night
        phase, emoji, _ = get_time_of_day_phase(1320)
        self.assertEqual(phase, "Night")
        self.assertEqual(emoji, "🌙")

        # 02:00 -> Midnight
        phase, emoji, _ = get_time_of_day_phase(120)
        self.assertEqual(phase, "Midnight")
        self.assertEqual(emoji, "🌌")

    def test_format_time_header(self):
        header = format_time_header(current_day=1, current_minute=510)
        self.assertEqual(header, "📅 Monday | 🕒 08:30 (Morning ☀️)")

        header_night = format_time_header(current_day=2, current_minute=1335)
        self.assertEqual(header_night, "📅 Tuesday | 🕒 22:15 (Night 🌙)")

    def test_bedtime_detection(self):
        self.assertFalse(is_sleep_time(480))   # 08:00
        self.assertFalse(is_sleep_time(1200))  # 20:00
        self.assertTrue(is_sleep_time(1320))   # 22:00
        self.assertTrue(is_sleep_time(1400))   # 23:20
        self.assertTrue(is_sleep_time(60))     # 01:00
        self.assertTrue(is_sleep_time(300))    # 05:00
        self.assertFalse(is_sleep_time(360))   # 06:00

    def test_action_time_costs(self):
        # 1. Dialogue
        cost = calculate_action_time_cost({"label": "Talk with Aoi"}, is_dialogue=True)
        self.assertEqual(cost, 2)

        # 2. Room Investigation
        cost = calculate_action_time_cost({"label": "Search the room for clues"})
        self.assertEqual(cost, 10)

        # 3. Modern Tier 2 travel (Classroom -> Cafeteria) must be 5 minutes
        cost_m2 = calculate_action_time_cost(
            {"label": "Walk to cafeteria"},
            scen_key="high_school_drama",
            old_loc="Silverwood High ➔ West Wing ➔ Room 101",
            new_loc="Silverwood High ➔ East Wing ➔ Cafeteria"
        )
        self.assertEqual(cost_m2, 5)

        # 3b. Tier 3 Room-to-Room travel (Room 101 -> Room 102 / Hallway) must be 2 minutes
        cost_t3 = calculate_action_time_cost(
            {"label": "Step into the hallway"},
            scen_key="high_school_drama",
            old_loc="Silverwood High ➔ West Wing ➔ Room 101",
            new_loc="Silverwood High ➔ West Wing ➔ Hallway"
        )
        self.assertEqual(cost_t3, 2)

        # 4. Modern Interzone travel must be ~25 minutes
        cost_m1 = calculate_action_time_cost(
            {"label": "Take subway to Downtown"},
            scen_key="high_school_drama",
            old_loc="Silverwood High ➔ West Wing ➔ Room 101",
            new_loc="Downtown District ➔ Shopping Mall ➔ Arcade"
        )
        self.assertEqual(cost_m1, 25)

        # 5. Fantasy Interzone travel must be 120 minutes (2 hours)
        cost_f1 = calculate_action_time_cost(
            {"label": "Travel through the wilderness to Riverwood"},
            scen_key="fantasy",
            old_loc="Valenwood Region ➔ Whiterun ➔ Plaza",
            new_loc="Riverwood Region ➔ Riverwood ➔ Tavern"
        )
        self.assertEqual(cost_f1, 120)

    def test_advance_time_and_day_rollover(self):
        # Start at Monday 23:30 (minute 1410)
        db.update_session_time(self.session_id, current_day=1, current_minute=1410)
        
        # Advance 40 minutes -> should cross midnight to Tuesday 00:10 (minute 10)
        res = advance_time(self.session_id, delta_minutes=40, party_uids=[12345])
        
        self.assertEqual(res["new_day"], 2)
        self.assertEqual(res["new_minute"], 10)
        self.assertTrue(res["day_rolled_over"])
        
        # Verify DB persisted
        day, minute, _ = db.get_session_time(self.session_id)
        self.assertEqual(day, 2)
        self.assertEqual(minute, 10)

        # Verify character days_adventured incremented
        updated_char = db.get_character(12345)
        self.assertEqual(updated_char["days_adventured"], 2)

    def test_sleep_rest_resolution(self):
        # Damage character HP/MP and add Fatigue
        db.update_character_fields(12345, hp=20, mp=5)
        db.set_status_effects(12345, ["Fatigued"])
        
        # Session is at 22:30 (minute 1350) on Monday (Day 1)
        db.update_session_time(self.session_id, current_day=1, current_minute=1350)
        
        # Apply sleep
        sleep_res = apply_sleep_rest(self.session_id, party_uids=[12345], wake_minute=450)
        
        # Verify clock advanced to 07:30 AM on Tuesday (Day 2)
        self.assertEqual(sleep_res["new_day"], 2)
        self.assertEqual(sleep_res["new_minute"], 450)
        self.assertEqual(sleep_res["clock_display"], "07:30")
        self.assertEqual(sleep_res["day_name"], "Tuesday")
        self.assertIn("Fatigued", sleep_res["fatigue_cleared"])

        # Verify Character Vitals fully restored
        rested_char = db.get_character(12345)
        self.assertEqual(rested_char["hp"], rested_char["max_hp"])
        self.assertEqual(rested_char["mp"], rested_char["max_mp"])
        self.assertEqual(json.loads(rested_char["status_effects"]), [])
        self.assertEqual(rested_char["days_adventured"], 2)

    def test_progressive_fatigue_all_nighter(self):
        # Session stays up past 05:00 AM without sleeping
        db.update_session_time(self.session_id, current_day=1, current_minute=290, consecutive_days_awake=0)
        
        # Advance past 05:00 AM (minute 300)
        res = advance_time(self.session_id, delta_minutes=20, party_uids=[12345])
        
        # Should apply Stage 1: Fatigued
        char = db.get_character(12345)
        status_list = json.loads(char["status_effects"])
        self.assertTrue("Fatigued" in status_list)

    def test_llm_time_context_formatting(self):
        ctx = format_llm_time_context(current_day=1, current_minute=510, scen_key="high_school_drama")
        self.assertIn("Monday (Day 1), 08:30 [Morning ☀️]", ctx)
        self.assertIn("Day Progression", ctx)

        ctx_night = format_llm_time_context(current_day=3, current_minute=1350, scen_key="cyberpunk")
        self.assertIn("Wednesday (Day 3), 22:30 [Night 🌙]", ctx_night)
        self.assertIn("Late-Night Flavor", ctx_night)


    def test_campus_area_link_topological_travel(self):
        # 1. Adjacent campus wings: Academic to Commons = 5 minutes
        cost_adj = calculate_action_time_cost(
            {"label": "Walk to plaza"},
            scen_key="high_school_drama",
            old_loc="Westlake Academy ➔ Homeroom Classroom ➔ Front Row Desks",
            new_loc="Student Commons & Central Plaza ➔ Central Courtyard ➔ Courtyard Fountain"
        )
        self.assertEqual(cost_adj, 5)

        # 2. Multi-hop campus wings: Academic to Athletics via Commons = 10 minutes
        cost_2hop = calculate_action_time_cost(
            {"label": "Head to gym"},
            scen_key="high_school_drama",
            old_loc="Westlake Academy ➔ Homeroom Classroom ➔ Front Row Desks",
            new_loc="School Grounds & Athletics ➔ Main Gymnasium ➔ Basketball Court"
        )
        self.assertEqual(cost_2hop, 10)

        # 3. Multi-hop cross campus: Athletics to Cultural Arts via Commons = 10 minutes
        cost_cross = calculate_action_time_cost(
            {"label": "Go to student council"},
            scen_key="high_school_drama",
            old_loc="School Grounds & Athletics ➔ Main Gymnasium ➔ Basketball Court",
            new_loc="Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk"
        )
        self.assertEqual(cost_cross, 10)

        # 4. Campus wing to Off-Campus: Cultural Arts ➔ Commons (5m) ➔ Academic (5m) ➔ Residential (25m) = 35 minutes!
        cost_to_town = calculate_action_time_cost(
            {"label": "Walk home from club"},
            scen_key="high_school_drama",
            old_loc="Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk",
            new_loc="Sakura Hill Residential Town ➔ Anderson Residence ➔ Living Room"
        )
        self.assertEqual(cost_to_town, 35)

        # 5. Off-Campus to Inner Campus Wing: Commercial ➔ Academic (25m) ➔ Commons (5m) ➔ Abandoned Old Campus (5m) = 35 minutes!
        cost_to_campus = calculate_action_time_cost(
            {"label": "Sneak into clock tower after shopping"},
            scen_key="high_school_drama",
            old_loc="Komorebi Commercial Strip ➔ Café Monolith ➔ Patio Table",
            new_loc="Abandoned Old Campus Building ➔ Decaying Clock Tower ➔ Attic Gearworks Chamber"
        )
        self.assertEqual(cost_to_campus, 35)

        # 6. Academic gate to Off-Campus: 25 minutes
        cost_gate = calculate_action_time_cost(
            {"label": "Leave school grounds"},
            scen_key="high_school_drama",
            old_loc="Westlake Academy ➔ Entrance Foyer & Shoe Lockers ➔ Shoe Lockers",
            new_loc="Sakura Hill Residential Town ➔ Greenwood Gardens ➔ Park Gazebo"
        )
        self.assertEqual(cost_gate, 25)

        # 7. Off-Campus to Off-Campus: Commercial to Residential = 25 minutes
        cost_off = calculate_action_time_cost(
            {"label": "Head home from arcade"},
            scen_key="high_school_drama",
            old_loc="Komorebi Commercial Strip ➔ Chrono-Quest Arcade ➔ Rhythm Machine",
            new_loc="Sakura Hill Residential Town ➔ Anderson Residence ➔ Living Room"
        )
        self.assertEqual(cost_off, 25)


if __name__ == "__main__":
    unittest.main()

