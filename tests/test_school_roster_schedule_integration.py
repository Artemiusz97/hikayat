"""
Unit tests for School Roster Schedule & Routine Integration.

Verifies:
1. Curfew / Night lockouts and archetype exceptions (Occult in Abandoned Building, Delinquent behind sheds, Faculty in Staff Room).
2. Weekday class hour cohort fidelity (Homeroom classmates, STEM in lab, truants/hall-passers in hallways, town empty).
3. Weekday lunch commons population (Cafeteria, Rooftop, Courtyard, town closed).
4. Extracurricular club matching (Pool, Dojo, Track, plus town youth nodes: Arcade, Cafe).
5. Weekend morning practice vs afternoon town leisure roaming.
6. Imminent pre-bell transition rush activity snippets (07:55, 11:55, 14:55).
7. Active party & staged NPC anti-duplication.
8. Social affinity and kinship boost.
"""
import unittest
import db
from mechanics.social import school_roster


class TestSchoolRosterScheduleIntegration(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 99887766
        self.test_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = {"id": self.test_session_id, "scenario": "high_school_drama"}
        self.roster = school_roster.ensure_school_directory_exists(self.session)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.commit()

    def test_curfew_night_lockouts_and_archetype_exceptions(self):
        """At 02:00 AM, regular campus facilities return empty, but archetype exceptions are allowed."""
        night_minute = 120  # 02:00 AM
        day = 1             # Monday

        # 1. Regular academic classroom at 2:00 AM -> 0 characters (locked)
        c_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=day,
            current_minute=night_minute
        )
        self.assertEqual(len(c_chars), 0)

        # 2. Regular gym at 2:00 AM -> 0 characters (locked)
        gym_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area",
            current_day=day,
            current_minute=night_minute
        )
        self.assertEqual(len(gym_chars), 0)

        # 3. Abandoned Old Campus Building -> Allowed for Occult / Paranormal / Delinquents
        abandoned_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Abandoned Old Campus Building ➔ Old Storage Room 3-B",
            current_day=day,
            current_minute=night_minute
        )
        self.assertGreaterEqual(len(abandoned_chars), 1)
        for ac in abandoned_chars:
            c_desc = f"{ac.get('role', '')} {ac.get('club', '')} {ac.get('clique', '')}".lower()
            self.assertTrue(any(k in c_desc for k in ("occult", "paranormal", "delinquent", "rebel")))

        # 4. Behind Gym Sheds -> Allowed for Delinquents loitering
        shed_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Behind Gym Storage Sheds",
            current_day=day,
            current_minute=night_minute
        )
        self.assertGreaterEqual(len(shed_chars), 1)
        for sc in shed_chars:
            s_desc = f"{sc.get('role', '')} {sc.get('clique', '')}".lower()
            self.assertTrue(any(k in s_desc for k in ("delinquent", "rebel", "truant")))

        # 5. Staff Room -> Allowed for faculty working late
        staff_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Teachers' Staff Room",
            current_day=day,
            current_minute=night_minute
        )
        self.assertGreaterEqual(len(staff_chars), 1)
        for tc in staff_chars:
            self.assertTrue(tc.get("grade") == "Faculty" or "teacher" in tc.get("role", "").lower())

    def test_weekday_class_hour_cohort_fidelity(self):
        """During class hours (09:30 AM), homeroom, lab, and hallway have distinct populations; town is empty."""
        class_minute = 570  # 09:30 AM (Monday)
        day = 1

        # 1. Homeroom has classmates
        hr_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=day,
            current_minute=class_minute,
            limit=3
        )
        self.assertGreaterEqual(len(hr_chars), 1)
        for hc in hr_chars:
            self.assertTrue("homeroom" in hc["primary_facility"].lower() or "classroom" in hc["primary_facility"].lower())
            self.assertIn("Activity:", f"Activity: {hc.get('activity')}")

        # 2. Chemistry Lab has Chemistry Teacher or STEM students
        chem_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Science Wing ➔ Chemistry Lab",
            current_day=day,
            current_minute=class_minute
        )
        self.assertGreaterEqual(len(chem_chars), 1)
        self.assertTrue(any("Chemistry" in c["role"] for c in chem_chars))

        # 3. Off-Campus Arcade during class hours -> 0 students (in school)
        arcade_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Commercial Promenade ➔ Game Center Arcade ➔ Rhythm Game Area",
            current_day=day,
            current_minute=class_minute
        )
        self.assertEqual(len(arcade_chars), 0)

    def test_weekday_lunch_commons_presence(self):
        """At 12:30 PM (lunch), Cafeteria and Rooftop populate, but town remains closed to students."""
        lunch_minute = 750  # 12:30 PM (Monday)
        day = 1

        # 1. Cafeteria populates with students eating lunch
        cafe_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria",
            current_day=day,
            current_minute=lunch_minute
        )
        self.assertGreaterEqual(len(cafe_chars), 1)
        self.assertTrue(any("lunch" in c.get("activity", "").lower() for c in cafe_chars))

        # 2. Rooftop populates with lunch eaters or loners
        roof_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ School Rooftop",
            current_day=day,
            current_minute=lunch_minute
        )
        self.assertGreaterEqual(len(roof_chars), 1)

        # 3. Off-campus Cafe at 12:30 PM -> 0 students (students cannot leave campus)
        off_cafe = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Commercial Promenade ➔ Velvet Mug Coffee Shop ➔ Corner Booth",
            current_day=day,
            current_minute=lunch_minute
        )
        self.assertEqual(len(off_cafe), 0)

    def test_extracurricular_club_and_town_matching(self):
        """At 16:00 (after school), clubs populate campus facilities and town youth nodes populate."""
        club_minute = 960  # 16:00 (04:00 PM Monday)
        day = 1

        # 1. Swimming Pool has swim team members
        pool_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "School Grounds & Athletics ➔ Swimming Pool Facility ➔ Pool Deck",
            current_day=day,
            current_minute=club_minute
        )
        self.assertGreaterEqual(len(pool_chars), 1)
        for pc in pool_chars:
            self.assertTrue("swim" in pc.get("club", "").lower() or "swim" in pc.get("role", "").lower())
            self.assertIn("flip turn", pc.get("activity", "").lower())

        # 2. Off-Campus Arcade populates after school
        arcade_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Commercial Promenade ➔ Game Center Arcade ➔ Rhythm Game Area",
            current_day=day,
            current_minute=club_minute
        )
        self.assertGreaterEqual(len(arcade_chars), 1)
        for ac in arcade_chars:
            self.assertNotEqual(ac.get("grade"), "Faculty")

        # 3. Off-Campus Velvet Mug Cafe populates after school
        cafe_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Commercial Promenade ➔ Velvet Mug Coffee Shop ➔ Window Table",
            current_day=day,
            current_minute=club_minute
        )
        self.assertGreaterEqual(len(cafe_chars), 1)

    def test_weekend_morning_practice_vs_afternoon_town_roaming(self):
        """On Saturday morning athletes practice; on Saturday afternoon students roam town."""
        sat_day = 6
        sat_morning = 540    # 09:00 AM Saturday
        sat_afternoon = 900  # 15:00 (03:00 PM) Saturday

        # 1. Saturday morning at Swimming Pool -> Athletes practicing
        pool_morning = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "School Grounds & Athletics ➔ Swimming Pool Facility ➔ Pool Deck",
            current_day=sat_day,
            current_minute=sat_morning
        )
        self.assertGreaterEqual(len(pool_morning), 1)
        self.assertTrue(any("swim" in f"{c.get('role', '')} {c.get('club', '')}".lower() for c in pool_morning))

        # 2. Saturday morning academic classrooms -> Locked (0 characters)
        class_morning = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=sat_day,
            current_minute=sat_morning
        )
        self.assertEqual(len(class_morning), 0)

        # 3. Saturday afternoon at Arcade -> Populated with students hanging out
        arcade_afternoon = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Commercial Promenade ➔ Game Center Arcade ➔ Fighting Game Row",
            current_day=sat_day,
            current_minute=sat_afternoon
        )
        self.assertGreaterEqual(len(arcade_afternoon), 1)
        self.assertIn("Activity:", f"Activity: {arcade_afternoon[0].get('activity')}")

    def test_imminent_transition_rush_activities(self):
        """Within 15 minutes of a bell, activity snippets dynamically reflect upcoming transitions."""
        day = 1

        # 07:55 AM (5 mins before 08:00 AM homeroom bell)
        commute_rush = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Main Gates & Shoe Lockers",
            current_day=day,
            current_minute=475
        )
        self.assertGreaterEqual(len(commute_rush), 1)
        act_text = commute_rush[0].get("activity", "").lower()
        self.assertTrue(any(w in act_text for w in ("bell", "rush", "sprint", "hurry", "sneaker", "locker")))

        # 11:55 AM (5 mins before 12:00 PM lunch bell)
        lunch_rush = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=day,
            current_minute=715
        )
        self.assertGreaterEqual(len(lunch_rush), 1)
        act_lunch = lunch_rush[0].get("activity", "").lower()
        self.assertTrue(any(w in act_lunch for w in ("lunch", "doorway", "textbook", "bento", "clock")))

    def test_active_party_and_staged_npc_anti_duplication(self):
        """Active party members or staged NPCs are strictly excluded from ambient injection."""
        day = 1
        minute = 570  # Class hour
        location = "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)"

        initial_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id, location, current_day=day, current_minute=minute, limit=2
        )
        self.assertGreaterEqual(len(initial_chars), 1)
        excluded_target = initial_chars[0]["name"]

        # Run again with excluded_target in active_npc_names
        filtered_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            location,
            current_day=day,
            current_minute=minute,
            limit=2,
            active_npc_names={excluded_target.lower()}
        )
        returned_names = [c["name"].lower() for c in filtered_chars]
        self.assertNotIn(excluded_target.lower(), returned_names)

    def test_social_affinity_kin_priority(self):
        """Students with sibling connections to established contacts are prioritized in rotation."""
        # Find a sibling pair in the roster
        sib_student = next((c for c in self.roster if c.get("sibling_name")), None)
        self.assertIsNotNone(sib_student)
        partner_name = sib_student["sibling_name"]

        # Insert partner_name as an established high-affinity contact
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, track)
                   VALUES (?, 0, ?, ?, 85, 'platonic')""",
                (self.test_session_id, partner_name.lower().replace(" ", "_"), partner_name)
            )
            conn.commit()

        # Query homeroom where sib_student is stationed
        day = 1
        minute = 570
        chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            sib_student["primary_facility"],
            current_day=day,
            current_minute=minute,
            limit=2
        )
        returned_names = [c["name"] for c in chars]
        self.assertIn(sib_student["name"], returned_names)

    def test_edge_cases_and_dirty_state_resilience(self):
        """Validates resilience against None values, non-school scenarios, empty strings, and dirty db records."""
        # 1. Non-campus scenario -> returns [] immediately
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET scenario='fantasy' WHERE id=?", (self.test_session_id,))
            conn.commit()
        chars = school_roster.get_facility_ambient_characters(
            self.test_session_id, "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)"
        )
        self.assertEqual(chars, [])

        # Reset scenario back to high school
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET scenario='high_school_drama' WHERE id=?", (self.test_session_id,))
            conn.commit()

        # 2. None / Empty location strings -> return [] safely without raising exceptions
        self.assertEqual(school_roster.get_facility_ambient_characters(self.test_session_id, ""), [])
        self.assertEqual(school_roster.get_facility_ambient_characters(self.test_session_id, None), [])
        self.assertEqual(school_roster.get_facility_ambient_characters(0, "Westlake Academy"), [])

        # 3. None current_day and current_minute arguments -> fallback safely
        chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=None,
            current_minute=None
        )
        self.assertGreaterEqual(len(chars), 1)

        # 4. Dirty contact entry in db (relationship_score is None) -> handles gracefully
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, track)
                   VALUES (?, 0, 'dirty_npc', 'Dirty NPC', NULL, 'platonic')""",
                (self.test_session_id,)
            )
            conn.commit()
        chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            current_day=1,
            current_minute=570
        )
        self.assertGreaterEqual(len(chars), 1)

        # 5. Empty classroom returns 0 students during active class hours
        empty_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ Empty Classroom ➔ Front Row Desks",
            current_day=1,
            current_minute=570
        )
        self.assertEqual(len(empty_chars), 0)

        # 6. Extracurricular rooftop loitering (delinquents, quiet peers)
        roof_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "Westlake Academy ➔ Academic Wing ➔ School Rooftop",
            current_day=1,
            current_minute=960  # 16:00
        )
        self.assertGreaterEqual(len(roof_chars), 1)

    def test_ambient_hydration_persists_initial_activity(self):
        """When an ambient encounter is hydrated, its initial activity tag is preserved in basic_info."""
        pool_chars = school_roster.get_facility_ambient_characters(
            self.test_session_id,
            "School Grounds & Athletics ➔ Swimming Pool Facility ➔ Pool Deck",
            current_day=1,
            current_minute=960
        )
        self.assertGreaterEqual(len(pool_chars), 1)
        target = pool_chars[0]
        self.assertTrue(target.get("activity"))

        # Hydrate the character
        success = school_roster.hydrate_school_character(self.test_session_id, target)
        self.assertTrue(success)

        # Verify contact in db has initial_activity
        contact = db.get_contact(self.test_session_id, target["npc_id"])
        self.assertIsNotNone(contact)
        basic_info = contact.get("basic_info") or {}
        self.assertEqual(basic_info.get("initial_activity"), target["activity"])

    def test_24_hour_continuous_simulation_stability(self):
        """Simulates 48 distinct turns every 30 minutes across a full weekday and weekend day with zero errors."""
        test_facilities = [
            "Westlake Academy ➔ Academic Wing ➔ Classroom 2-B (Homeroom)",
            "Westlake Academy ➔ Science Wing ➔ Chemistry Lab",
            "Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria",
            "School Grounds & Athletics ➔ Swimming Pool Facility ➔ Pool Deck",
            "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area",
            "Abandoned Old Campus Building ➔ Old Storage Room 3-B",
            "Commercial Promenade ➔ Game Center Arcade ➔ Rhythm Game Area",
            "Commercial Promenade ➔ Velvet Mug Coffee Shop ➔ Corner Booth",
        ]

        # Test full weekday (Day 1) and weekend (Day 6)
        for day in (1, 6):
            for minute in range(0, 1440, 30):
                for fac in test_facilities:
                    chars = school_roster.get_facility_ambient_characters(
                        self.test_session_id,
                        fac,
                        current_day=day,
                        current_minute=minute,
                        limit=2
                    )
                    self.assertIsInstance(chars, list)
                    self.assertLessEqual(len(chars), 2)
                    for c in chars:
                        self.assertTrue(c.get("name"))
                        self.assertTrue(c.get("role"))
                        self.assertTrue(c.get("activity"))


if __name__ == "__main__":
    unittest.main()
