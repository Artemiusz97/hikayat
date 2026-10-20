"""
Unit tests for the Genealogy & Social Relations Engine (mechanics/genealogy.py).
Tests reverse-genealogy, interracial inheritance, surname consistency, species locking,
intercourse_experience decoupling, and 3-tier progressive information disclosure.
"""
import unittest
import tempfile
import os
import shutil
import db
import mechanics.social.genealogy as genealogy
from mechanics.social.relationships import get_unlocked_info_level


class TestGenealogy(unittest.TestCase):
    def test_extract_species_from_race(self):
        self.assertEqual(genealogy.extract_species_from_race("beastfolk:fox"), "fox")
        self.assertEqual(genealogy.extract_species_from_race("half_beast:cat"), "cat")
        self.assertEqual(genealogy.extract_species_from_race("hybrid:wolf"), "wolf")
        self.assertEqual(genealogy.extract_species_from_race("Fox-Beastfolk"), "fox")
        self.assertEqual(genealogy.extract_species_from_race("human"), "")
        self.assertEqual(genealogy.extract_species_from_race("elf"), "")
        self.assertEqual(genealogy.extract_species_from_race("preparatory directorate"), "")
        self.assertEqual(genealogy.extract_species_from_race("accurate certificate"), "")

    def test_extract_surname_and_firstname(self):
        self.assertEqual(genealogy.extract_surname_and_firstname("Sofia Anderson"), ("Sofia", "Anderson"))
        self.assertEqual(genealogy.extract_surname_and_firstname("Marcus"), ("Marcus", ""))
        self.assertEqual(genealogy.extract_surname_and_firstname("Elena Vance Anderson"), ("Elena", "Vance Anderson"))

    def test_reverse_generate_parents_surname_and_phenotype(self):
        child_appearance = {
            "eyes": "Amber",
            "hair": "Short Ponytail Golden-Blonde",
            "fur": "Golden-Blonde Fur"
        }
        father, mother = genealogy.reverse_generate_parents(
            child_race="beastfolk:fox",
            child_appearance=child_appearance,
            child_surname="Anderson",
            scenario="high_school_drama",
            hash_val=12345
        )

        # Surname checks
        self.assertEqual(father["surname"], "Anderson")
        self.assertIn("Anderson", father["name"])
        self.assertIn("Anderson", mother["name"])
        self.assertTrue("née" in mother["name"] or mother["surname"] == "Anderson")

        # Species consistency
        f_species = genealogy.extract_species_from_race(father["race"])
        m_species = genealogy.extract_species_from_race(mother["race"])
        if father["race"] != "human":
            self.assertEqual(f_species, "fox")
        if mother["race"] != "human":
            self.assertEqual(m_species, "fox")

        # Features consistency
        self.assertIn("Amber", father["features"])
        self.assertIn("Amber", mother["features"])

    def test_human_beastfolk_hybrid_sibling_split(self):
        """Tests that Human + Beastfolk cross rolls only Human, Half-Beast, or Beastfolk of the same species."""
        parent1_race = "human"
        parent2_race = "beastfolk:fox"
        species = "fox"

        races_seen = set()
        for seed in range(30):
            r = genealogy.roll_sibling_race(parent1_race, parent2_race, species, seed)
            races_seen.add(r)
            # Verify strict species locking (fox never turns into cat or wolf)
            if r != "human":
                self.assertIn("fox", r)
                self.assertNotIn("cat", r)
                self.assertNotIn("wolf", r)

        self.assertIn("human", races_seen)
        self.assertIn("half_beast:fox", races_seen)
        self.assertIn("beastfolk:fox", races_seen)

    def test_other_interracial_sibling_split(self):
        """Tests that non-hybrid interracial crosses (e.g. Elf + Human) split 50/50 between parent races."""
        parent1_race = "elf"
        parent2_race = "human"

        seen = set()
        for seed in range(20):
            r = genealogy.roll_sibling_race(parent1_race, parent2_race, "", seed)
            seen.add(r)
            self.assertIn(r, ("elf", "human"))

        self.assertEqual(seen, {"elf", "human"})

    def test_relationship_status_intercourse_experience_decoupling(self):
        """Tests that intercourse_experience status and romantic relationship status remain strictly decoupled."""
        # 1. Virgin contact with an ex-partner generated
        virgin_contact = {
            "name": "Hana Vance",
            "gender": "female",
            "appearance": {"predetermined_intercourse_experience": "virgin"},
            "intimate_memories": []
        }
        status = genealogy.generate_relationship_status(virgin_contact, scenario="fantasy", hash_val=42)
        self.assertIsInstance(status, dict)
        # Even if they have exes or current partner, predetermined_intercourse_experience remains untouched
        self.assertEqual(virgin_contact["appearance"]["predetermined_intercourse_experience"], "virgin")

        # 2. Non-virgin contact with past intimate partner synchronizes into exes
        non_virgin_contact = {
            "name": "Sofia Anderson",
            "gender": "female",
            "appearance": {"predetermined_intercourse_experience": "non_virgin"},
            "intimate_memories": ["Past History: Had intercourse during a relationship with 'Marcus Vance' (Former Classmate)"]
        }
        status_synced = genealogy.generate_relationship_status(non_virgin_contact, scenario="high_school_drama", hash_val=99)
        self.assertGreaterEqual(len(status_synced["ex_partners"]), 1)
        self.assertTrue(any("Marcus Vance" in ex["name"] for ex in status_synced["ex_partners"]))

    def test_information_disclosure_filtering(self):
        """Tests 3-tier information disclosure for relations."""
        relations = {
            "family": [
                {"relation": "Father", "name": "Marcus Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Coach"},
                {"relation": "Mother", "name": "Elena Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Doctor"},
                {"relation": "Older Brother", "name": "Leo Anderson", "race": "beastfolk:fox", "status": "Alive", "occupation": "Student"}
            ],
            "romance": {
                "status": "In a Relationship",
                "current_partner": {"name": "Adrian Reed", "role": "Student"},
                "secret_partner": {"name": "Damian Cole", "role": "Bad Boy"},
                "ex_partners": [{"name": "Marcus Vance", "role": "Ex"}]
            },
            "friends": [{"name": "Maya Sterling", "role": "Co-Captain", "closeness": "Close Friend"}],
            "rivals": [{"name": "Cassandra Cross", "role": "Rival Captain", "type": "Track Rival"}]
        }

        # Level 1 Disclosure (Score 0-30)
        d1 = genealogy.format_relations_for_disclosure(relations, info_level=1, debug_reveal=False)
        self.assertFalse(d1["family"]["revealed"])
        self.assertIn("🔒", d1["family"]["locked_message"])
        self.assertFalse(d1["romance"]["revealed"])
        self.assertIsNone(d1["romance"]["secret_partner"])
        self.assertEqual(d1["romance"]["ex_partners"], [])
        self.assertFalse(d1["friends"]["revealed"])
        self.assertFalse(d1["rivals"]["revealed"])

        # Level 2 Disclosure (Score 31-70)
        d2 = genealogy.format_relations_for_disclosure(relations, info_level=2, debug_reveal=False)
        self.assertFalse(d2["family"]["revealed"])
        self.assertTrue(d2["romance"]["revealed"])
        self.assertTrue(d2["romance"]["secret_partner"]["locked"])
        self.assertTrue(d2["romance"]["ex_partners"][0]["locked"])
        self.assertTrue(d2["friends"]["revealed"])
        self.assertTrue(d2["rivals"]["revealed"])

        # Level 3 Disclosure (Score 71+)
        d3 = genealogy.format_relations_for_disclosure(relations, info_level=3, debug_reveal=False)
        self.assertTrue(d3["family"]["revealed"])
        self.assertEqual(len(d3["family"]["members"]), 3)
        self.assertTrue(d3["romance"]["revealed"])
        self.assertEqual(d3["romance"]["secret_partner"]["name"], "Damian Cole")
        self.assertEqual(d3["romance"]["ex_partners"][0]["name"], "Marcus Vance")
        self.assertTrue(d3["friends"]["revealed"])
        self.assertTrue(d3["rivals"]["revealed"])

        # Debug reveal flag overrides any level to Level 3
        d_debug = genealogy.format_relations_for_disclosure(relations, info_level=1, debug_reveal=True)
        self.assertTrue(d_debug["family"]["revealed"])
        self.assertEqual(d_debug["romance"]["secret_partner"]["name"], "Damian Cole")

    def test_db_contact_relations_persistence(self):
        """Tests that db.py loads and persists relations."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Club President", "description": "Athletic fox girl."},
                delta_score=75,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            contacts = db.get_contacts(sess_id, character_id=1)
            self.assertEqual(len(contacts), 1)
            loaded = contacts[0]
            self.assertIn("relations", loaded)
            self.assertIn("family", loaded["relations"])
            self.assertGreaterEqual(len(loaded["relations"]["family"]), 2)

            father = loaded["relations"]["family"][0]
            self.assertIn("Anderson", father["name"])
            self.assertIn(father["race"], ("beastfolk:fox", "human"))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_player_interest_or_single_suppresses_random_current_partner(self):
        """Verify that contacts with high score, romantic track, or explicitly single never get an auto-generated partner."""
        contact_romantic = {
            "name": "Maya Anderson",
            "gender": "female",
            "relationship_score": 50,
            "track": "romantic",
            "appearance": {"intercourse_experience": "virgin"}
        }
        rom_status = genealogy.generate_relationship_status(contact_romantic, scenario="high_school_drama", hash_val=0)
        self.assertIsNotNone(rom_status["current_partner"])
        self.assertEqual(rom_status["current_partner"]["name"], "Player")
        self.assertEqual(rom_status["status"], "In a Relationship")

        contact_high_score = {
            "name": "Maya Anderson",
            "gender": "female",
            "relationship_score": 45,
            "track": "platonic",
            "appearance": {"intercourse_experience": "virgin"}
        }
        rom_status_2 = genealogy.generate_relationship_status(contact_high_score, scenario="high_school_drama", hash_val=0)
        self.assertIsNone(rom_status_2["current_partner"])
        self.assertEqual(rom_status_2["status"], "Single")


    def test_sibling_family_synchronization_and_identical_parents(self):
        """Verify that siblings (Sofia Anderson and Maya Anderson) share 100% identical parents and careers."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            # 1. Add Sofia Anderson
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Junior Robotics Apprentice", "grade": "Junior", "sibling_name": "Maya Anderson"},
                delta_score=50,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            # 2. Add Maya Anderson
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="maya_anderson",
                name="Maya Anderson",
                basic_info={"role": "Freshman Student", "grade": "Freshman", "sibling_name": "Sofia Anderson"},
                delta_score=50,
                track="platonic",
                race="beastfolk:fox",
                gender="female",
                appearance={"eyes": "Amber", "hair": "Golden-Blonde", "fur": "Golden-Blonde Fur"}
            )

            sofia = db.get_contact(sess_id, "sofia_anderson", character_id=1)
            maya = db.get_contact(sess_id, "maya_anderson", character_id=1)

            sofia_rel = genealogy.ensure_contact_relations(sofia, session_id=sess_id, scenario="high_school_drama")
            maya_rel = genealogy.ensure_contact_relations(maya, session_id=sess_id, scenario="high_school_drama")

            sofia_fam = sofia_rel["family"]
            maya_fam = maya_rel["family"]

            # Father comparison
            s_father = next(m for m in sofia_fam if m["relation"] == "Father")
            m_father = next(m for m in maya_fam if m["relation"] == "Father")
            self.assertEqual(s_father["name"], m_father["name"])
            self.assertEqual(s_father["occupation"], m_father["occupation"])
            self.assertEqual(s_father["race"], m_father["race"])
            self.assertEqual(s_father["status"], m_father["status"])

            # Mother comparison
            s_mother = next(m for m in sofia_fam if m["relation"] == "Mother")
            m_mother = next(m for m in maya_fam if m["relation"] == "Mother")
            self.assertEqual(s_mother["name"], m_mother["name"])
            self.assertEqual(s_mother["occupation"], m_mother["occupation"])
            self.assertEqual(s_mother["race"], m_mother["race"])
            self.assertEqual(s_mother["maiden_name"], m_mother["maiden_name"])

            # Cross-sibling presence and relative label
            sofia_sibs = [m for m in sofia_fam if "Sister" in m["relation"] or "Brother" in m["relation"]]
            maya_sibs = [m for m in maya_fam if "Sister" in m["relation"] or "Brother" in m["relation"]]

            self.assertTrue(any(s["first_name"] == "Maya" and "Sister" in s["relation"] for s in sofia_sibs))
            self.assertTrue(any(s["first_name"] == "Sofia" and s["relation"] == "Older Sister" for s in maya_sibs))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_dynamic_track_transition_and_social_mutations(self):
        """Verify dynamic transitions between platonic and romantic tracks and social graph modifications."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="zihan_moon",
                name="Zihan Moon",
                delta_score=75,
                track="romantic"
            )

            contact = db.get_contact(sess_id, "zihan_moon", character_id=1)
            self.assertEqual(contact["track"], "romantic")
            rel = genealogy.ensure_contact_relations(contact, session_id=sess_id, scenario="high_school_drama")
            self.assertEqual(rel["romance"]["status"], "In a Relationship")

            # Dynamically switch back to platonic
            db.update_contact_track(sess_id, "zihan_moon", "platonic", character_id=1)
            contact_platonic = db.get_contact(sess_id, "zihan_moon", character_id=1)
            self.assertEqual(contact_platonic["track"], "platonic")

            rel_platonic = genealogy.ensure_contact_relations(contact_platonic, session_id=sess_id, scenario="high_school_drama")
            self.assertEqual(rel_platonic["romance"]["status"], "Single")
            self.assertIsNone(rel_platonic["romance"]["current_partner"])

            # Test dynamic friend and rival mutations
            genealogy.add_friend_relation(contact_platonic, "Yea-ji Kang", role="Student Council President", closeness="Sworn Bestie")
            self.assertTrue(any(f["name"] == "Yea-ji Kang" and f["closeness"] == "Sworn Bestie" for f in contact_platonic["relations"]["friends"]))

            genealogy.add_rival_relation(contact_platonic, "Cassandra Cross", role="Track Star", rival_type="Bitter Nemesis")
            self.assertTrue(any(r["name"] == "Cassandra Cross" and r["type"] == "Bitter Nemesis" for r in contact_platonic["relations"]["rivals"]))

            genealogy.remove_relation(contact_platonic, "Yea-ji Kang")
            self.assertFalse(any(f["name"] == "Yea-ji Kang" for f in contact_platonic["relations"]["friends"]))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_race_compatibility_with_parents(self):
        """Verify is_race_compatible_with_parents rejects genetically impossible child races."""
        # Fox + Fox parents CANNOT have a Rabbit child
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:rabbit", "beastfolk:fox", "beastfolk:fox"))
        self.assertFalse(genealogy.is_race_compatible_with_parents("half_beast:rabbit", "beastfolk:fox", "beastfolk:fox"))
        # Fox + Fox CAN have Fox
        self.assertTrue(genealogy.is_race_compatible_with_parents("beastfolk:fox", "beastfolk:fox", "beastfolk:fox"))

        # Human + Fox can have Human, Half-Beast:fox, or Beastfolk:fox
        self.assertTrue(genealogy.is_race_compatible_with_parents("human", "human", "beastfolk:fox"))
        self.assertTrue(genealogy.is_race_compatible_with_parents("half_beast:fox", "human", "beastfolk:fox"))
        self.assertTrue(genealogy.is_race_compatible_with_parents("beastfolk:fox", "human", "beastfolk:fox"))
        # But NOT rabbit
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:rabbit", "human", "beastfolk:fox"))

        # Pure human parents cannot have beastfolk child
        self.assertFalse(genealogy.is_race_compatible_with_parents("beastfolk:cat", "human", "human"))

    def test_canonical_anderson_family_strictly_locked_to_three_fox_sisters(self):
        """Verify that the Anderson family is strictly locked to Amanda, Sofia, and Maya (all fox sisters)."""
        sess_id = db.create_session(host_user_id=1, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False, scenario="high_school_drama")
        try:
            # 1. Add Sofia Anderson (Fox)
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="sofia_anderson",
                name="Sofia Anderson",
                basic_info={"role": "Robotics & Tech Apprentice", "grade": "Junior", "sibling_name": "Maya Anderson"},
                race="beastfolk:fox",
                gender="female"
            )

            # 2. Add an unrelated NPC with surname Anderson (e.g. Justin Anderson, rabbit)
            db.upsert_contact(
                session_id=sess_id,
                character_id=1,
                npc_id="justin_anderson",
                name="Justin Anderson",
                basic_info={"role": "Student", "grade": "Junior", "sibling_name": "Yue Anderson"},
                race="beastfolk:rabbit",
                gender="male"
            )

            sofia = db.get_contact(sess_id, "sofia_anderson", character_id=1)
            sofia_rel = genealogy.ensure_contact_relations(sofia, session_id=sess_id, scenario="high_school_drama")
            fam = sofia_rel["family"]

            # Anderson family members must ONLY be Father, Mother, and the sisters (Amanda, Maya)
            names = [m["name"] for m in fam]
            self.assertNotIn("Justin Anderson", names)
            self.assertTrue(any("Amanda Anderson" in n for n in names))
            self.assertTrue(any("Maya Anderson" in n for n in names))

            # All Anderson family members must be Fox-Beastfolk
            for m in fam:
                self.assertIn("fox", m["race"].lower())

            # Female sisters only
            for m in fam:
                if "Sister" in m["relation"]:
                    self.assertEqual(m["gender"], "female")
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_male_sibling_never_labeled_sister(self):
        """Verify that male siblings with male names or gender male are never labeled Sister."""
        household = {
            "surname": "Vance",
            "father": {"name": "Harry Vance", "first_name": "Harry", "relation": "Father", "race": "human", "gender": "male", "status": "Alive"},
            "mother": {"name": "Sara Vance", "first_name": "Sara", "relation": "Mother", "race": "human", "gender": "female", "status": "Alive"},
            "children": [
                {"name": "Rachel Vance", "first_name": "Rachel", "gender": "female", "grade_val": 3, "race": "human", "status": "Alive"},
                {"name": "Justin Vance", "first_name": "Justin", "gender": "male", "grade_val": 4, "race": "human", "status": "Alive"},
                {"name": "Lucas Vance", "first_name": "Lucas", "gender": "", "grade_val": 1, "race": "human", "status": "Alive"}
            ]
        }
        tree = genealogy.build_family_tree_for_member(household, "Rachel Vance")
        sibs = [m for m in tree if m["relation"] not in ("Father", "Mother")]

        justin = next(s for s in sibs if s["first_name"] == "Justin")
        self.assertEqual(justin["relation"], "Older Brother")
        self.assertNotEqual(justin["relation"], "Older Sister")

        lucas = next(s for s in sibs if s["first_name"] == "Lucas")
        self.assertEqual(lucas["relation"], "Brother")
        self.assertNotEqual(lucas["relation"], "Sister")

    def test_get_contacts_no_recursion_on_unpopulated_relations(self):
        """Verify that get_contacts resolves relations for multiple contacts without recursion."""
        sess_id = db.create_session(
            host_user_id=1, mode="solo", capacity=1, verbosity="normal",
            dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
        )
        try:
            # Insert contacts with different surnames and NO relations populated
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="elena_vance",
                name="Elena Vance", basic_info={"role": "Merchant"}
            )
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="lucas_vance",
                name="Lucas Vance", basic_info={"role": "Apprentice", "sibling_name": "Elena Vance"}
            )
            db.upsert_contact(
                session_id=sess_id, character_id=1, npc_id="garrick_ironthorne",
                name="Garrick Ironthorne", basic_info={"role": "Blacksmith"}
            )

            # Clear any relations_json directly in the database
            with db.get_conn() as conn:
                conn.execute("UPDATE contacts SET relations_json = NULL WHERE session_id = ?", (sess_id,))

            # Call get_contacts: must terminate quickly and populate relations
            contacts = db.get_contacts(sess_id)
            self.assertEqual(len(contacts), 3)
            for c in contacts:
                self.assertIsNotNone(c.get("relations"))
                self.assertTrue(bool(c["relations"].get("family")))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_topic_aware_romance_context_includes_single_and_partner(self):
        """Verify build_topic_aware_npc_context activates on 'single' inquiry and includes current partner."""
        contact = {
            "name": "Mia Yamada",
            "track": "platonic",
            "relations": {
                "romance": {
                    "status": "In a Relationship",
                    "current_partner": {
                        "name": "Stephen Hernandez",
                        "role": "Former Lab Partner",
                        "relationship_type": "Dating / Partner"
                    },
                    "ex_partners": [
                        {"name": "Harry Ikeda", "role": "Dormitory Prefect"}
                    ]
                }
            }
        }
        # Inquire if she is single
        ctx = genealogy.build_topic_aware_npc_context(contact, actions="ask her if she's single")
        self.assertIn("[CANON ROMANCE & DATING HISTORY - Mia Yamada]", ctx)
        self.assertIn("Current Status: In a Relationship", ctx)
        self.assertIn("Stephen Hernandez", ctx)
        self.assertIn("Harry Ikeda", ctx)

    def test_ensure_contact_relations_preserves_previous_partner_in_exes(self):
        """Verify ensure_contact_relations preserves existing non-player partner in ex_partners when romantic track is activated."""
        sess_id = 999911
        try:
            contact = {
                "session_id": sess_id,
                "character_id": 1,
                "name": "Mia Yamada",
                "track": "romantic",
                "relationship_score": 60,
                "relations": {
                    "romance": {
                        "status": "In a Relationship",
                        "current_partner": {
                            "name": "Stephen Hernandez",
                            "role": "Former Lab Partner",
                            "relationship_type": "Dating / Partner"
                        },
                        "ex_partners": []
                    }
                }
            }
            rel = genealogy.ensure_contact_relations(contact, session_id=sess_id, scenario="high_school_drama")
            self.assertEqual(rel["romance"]["status"], "In a Relationship")
            self.assertNotEqual(rel["romance"]["current_partner"]["name"], "Stephen Hernandez")
            # Stephen Hernandez must have been moved to ex_partners
            exes = rel["romance"]["ex_partners"]
            self.assertTrue(any(e.get("name") == "Stephen Hernandez" for e in exes))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_bidirectional_and_transitive_sibling_symmetry(self):
        """Verify that siblings with unidirectional/transitive links across 3+ members all resolve to 100% symmetric rosters."""
        sess_id = 999977
        try:
            # Contact 1: Ayane Vance, sibling_name = "Mia Vance"
            c1 = {
                "session_id": sess_id,
                "name": "Ayane Vance",
                "race": "half_beast:fennec",
                "basic_info": {"sibling_name": "Mia Vance", "grade": "Sophomore", "role": "Theater Set Painter"},
                "appearance": {"eyes": "Amber", "hair": "Golden-Blonde"}
            }
            # Contact 2: Su-bin Vance, sibling_name = "Ayane Vance"
            c2 = {
                "session_id": sess_id,
                "name": "Su-bin Vance",
                "race": "half_beast:fennec",
                "basic_info": {"sibling_name": "Ayane Vance", "grade": "Freshman", "role": "Student Council Aide"},
                "appearance": {"eyes": "Amber", "hair": "Golden-Blonde"}
            }
            # Contact 3: Andrew Vance, sibling_name = "Ayane Vance"
            c3 = {
                "session_id": sess_id,
                "name": "Andrew Vance",
                "race": "half_beast:fennec",
                "basic_info": {"sibling_name": "Ayane Vance", "grade": "Senior", "role": "Art & Set Designer"},
                "appearance": {"eyes": "Amber", "hair": "Golden-Blonde"}
            }

            # Upsert into DB for session
            db.upsert_contact(sess_id, "ayane_vance", "Ayane Vance", 0, basic_info=c1["basic_info"], race=c1["race"])
            db.upsert_contact(sess_id, "su_bin_vance", "Su-bin Vance", 0, basic_info=c2["basic_info"], race=c2["race"])
            db.upsert_contact(sess_id, "andrew_vance", "Andrew Vance", 0, basic_info=c3["basic_info"], race=c3["race"])

            # Resolve canonical family unit from Su-bin's perspective
            h_subin = genealogy.get_canonical_family_unit(sess_id, "Vance", c2, scenario="high_school_drama")
            # Resolve from Ayane's perspective
            h_ayane = genealogy.get_canonical_family_unit(sess_id, "Vance", c1, scenario="high_school_drama")
            # Resolve from Andrew's perspective
            h_andrew = genealogy.get_canonical_family_unit(sess_id, "Vance", c3, scenario="high_school_drama")

            subin_kids = sorted([c["name"] for c in h_subin["children"]])
            ayane_kids = sorted([c["name"] for c in h_ayane["children"]])
            andrew_kids = sorted([c["name"] for c in h_andrew["children"]])

            # All three perspectives must yield the exact same roster of children
            self.assertEqual(subin_kids, ayane_kids)
            self.assertEqual(ayane_kids, andrew_kids)

            # Both Ayane, Andrew, and Mia must be in Su-bin's family tree
            subin_tree = genealogy.build_family_tree_for_member(h_subin, "Su-bin Vance", scenario="high_school_drama")
            subin_tree_names = [m["name"] for m in subin_tree]
            self.assertIn("Ayane Vance", subin_tree_names)
            self.assertIn("Andrew Vance", subin_tree_names)
            self.assertIn("Mia Vance", subin_tree_names)
            # Parents must be identical across households
            self.assertEqual(h_subin["father"]["name"], h_ayane["father"]["name"])
            self.assertEqual(h_ayane["father"]["name"], h_andrew["father"]["name"])
            self.assertEqual(h_subin["mother"]["name"], h_ayane["mother"]["name"])
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_household_entity_model_crud_and_single_source_of_truth(self):
        """Architecture 1: Verify single-row household mutation propagates to all siblings immediately."""
        sess_id = 999988
        try:
            # 1. Create household directly
            father = {
                "relation": "Father", "name": "Arthur Sterling", "first_name": "Arthur",
                "surname": "Sterling", "race": "human", "gender": "male", "status": "Alive",
                "occupation": "Bank Director", "features": "Blue eyes, Grey hair"
            }
            mother = {
                "relation": "Mother", "name": "Victoria Sterling", "first_name": "Victoria",
                "surname": "Sterling", "race": "human", "gender": "female", "status": "Alive",
                "occupation": "Art Collector", "features": "Emerald eyes, Auburn hair"
            }
            hh_id = db.create_household(
                session_id=sess_id,
                household_key=f"sterling_household_{sess_id}",
                surname="Sterling",
                father=father,
                mother=mother,
                narrative_siblings=[{"name": "Julian Sterling", "first_name": "Julian", "surname": "Sterling", "relation": "Older Brother", "role": "Diplomat", "status": "Off-Campus", "is_contactable": False}],
                residence_location="Upper Ward -> Sterling Manor"
            )
            self.assertGreater(hh_id, 0)

            # 2. Insert two student siblings
            c1 = db.upsert_contact(sess_id, "lucas_sterling", "Lucas Sterling", 0, basic_info={"grade": "Junior", "role": "Student"})
            c2 = db.upsert_contact(sess_id, "clara_sterling", "Clara Sterling", 0, basic_info={"grade": "Freshman", "role": "Student Council Aide"})

            db.assign_contact_household(sess_id, c1["id"], hh_id)
            db.assign_contact_household(sess_id, c2["id"], hh_id)

            # Retrieve household members
            members = db.get_household_members(hh_id)
            member_names = [m["name"] for m in members]
            self.assertIn("Lucas Sterling", member_names)
            self.assertIn("Clara Sterling", member_names)

            # 3. Retrieve contacts and verify household_id populated
            l_contact = db.get_contact(sess_id, "lucas_sterling")
            c_contact = db.get_contact(sess_id, "clara_sterling")
            self.assertEqual(l_contact["household_id"], hh_id)
            self.assertEqual(c_contact["household_id"], hh_id)

            # Both see Julian Sterling (narrative sibling)
            l_tree_names = [m["name"] for m in l_contact["relations"]["family"]]
            c_tree_names = [m["name"] for m in c_contact["relations"]["family"]]
            self.assertIn("Julian Sterling", l_tree_names)
            self.assertIn("Julian Sterling", c_tree_names)
            self.assertIn("Clara Sterling", l_tree_names)
            self.assertIn("Lucas Sterling", c_tree_names)

            # 4. Mutate single row in households table: e.g. Father promoted to 'Ambassador'
            father["occupation"] = "Ambassador"
            updated = db.update_household(hh_id, father=father)
            self.assertTrue(updated)

            # Immediately query both contacts without manual sync: both must reflect mutated father
            l_refreshed = db.get_contact(sess_id, "lucas_sterling")
            c_refreshed = db.get_contact(sess_id, "clara_sterling")
            l_father = next(m for m in l_refreshed["relations"]["family"] if m["relation"] == "Father")
            c_father = next(m for m in c_refreshed["relations"]["family"] if m["relation"] == "Father")
            self.assertEqual(l_father["occupation"], "Ambassador")
            self.assertEqual(c_father["occupation"], "Ambassador")
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_lazy_parent_hydration_to_active_contact(self):
        """Verify on-demand promotion of lightweight household parent into an active contact."""
        sess_id = 999989
        try:
            father = {
                "relation": "Father", "name": "Thomas Thorne", "first_name": "Thomas",
                "surname": "Thorne", "race": "human", "gender": "male", "status": "Alive",
                "occupation": "Master Blacksmith", "features": "Grey eyes, Beard"
            }
            mother = {
                "relation": "Mother", "name": "Sarah Thorne", "first_name": "Sarah",
                "surname": "Thorne", "race": "human", "gender": "female", "status": "Alive",
                "occupation": "Herbalist", "features": "Hazel eyes"
            }
            hh_id = db.create_household(
                session_id=sess_id,
                household_key=f"thorne_household_{sess_id}",
                surname="Thorne",
                father=father,
                mother=mother
            )
            # Hydrate Father into an active contact
            parent_contact = genealogy.hydrate_parent_to_contact(sess_id, hh_id, parent_role="father")
            self.assertIsNotNone(parent_contact)
            self.assertEqual(parent_contact["name"], "Thomas Thorne")
            self.assertEqual(parent_contact["household_id"], hh_id)

            # Verify Father is now queryable as an active contact in the session
            fetched = db.get_contact(sess_id, "thomas_thorne")
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["name"], "Thomas Thorne")
            self.assertEqual(fetched["household_id"], hh_id)
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_non_traditional_family_status(self):
        """Verify orphan, single mother, and deceased parent traits dynamically set status: 'Deceased'."""
        sess_id = 999990
        try:
            c_orphan = {
                "session_id": sess_id,
                "name": "Evelyn Cross",
                "race": "human",
                "basic_info": {"description": "An orphaned student raised by her late grandmother.", "traits": ["Orphan", "Determined"]},
                "appearance": {"eyes": "Blue"}
            }
            hh = genealogy.get_or_create_household(sess_id, "Cross", c_orphan, scenario="high_school_drama")
            self.assertEqual(hh["father"]["status"], "Deceased")
            self.assertEqual(hh["mother"]["status"], "Deceased")

            # Single mother scenario
            c_single_mom = {
                "session_id": sess_id,
                "name": "Leo Drake",
                "race": "human",
                "basic_info": {"description": "Raised solely by his single mother after his late father passed away.", "traits": ["Resourceful"]},
                "appearance": {"eyes": "Green"}
            }
            hh2 = genealogy.get_or_create_household(sess_id, "Drake", c_single_mom, scenario="high_school_drama")
            self.assertEqual(hh2["father"]["status"], "Deceased")
            self.assertEqual(hh2["mother"]["status"], "Alive")
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_player_character_lineage_protection(self):
        """Verify player character is protected from random procedural parentage."""
        sess_id = 999991
        try:
            player_contact = {
                "session_id": sess_id,
                "name": "Player",
                "is_player": True,
                "basic_info": {"role": "Protagonist"},
                "relations": {"family": []}
            }
            rel = genealogy.ensure_contact_relations(player_contact, session_id=sess_id, scenario="fantasy")
            # Family tree must NOT have procedurally generated parents
            self.assertEqual(rel.get("family"), [])
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)

    def test_hydrated_parent_excluded_from_children_and_parent_perspective(self):
        """Verify that hydrating a parent into contacts links them to father/mother dict,
        strictly excludes them from household['children'], and formats the family tree accurately
        both from a child's perspective and from a parent's perspective."""
        sess_id = 999992
        try:
            father = {
                "relation": "Father", "name": "George Vance", "first_name": "George",
                "surname": "Vance", "race": "human", "gender": "male", "status": "Alive",
                "occupation": "Guildmaster", "features": "Blue eyes, Grey beard"
            }
            mother = {
                "relation": "Mother", "name": "Evelyn Vance", "first_name": "Evelyn",
                "surname": "Vance", "race": "human", "gender": "female", "status": "Alive",
                "occupation": "Merchant", "features": "Hazel eyes"
            }
            hh_id = db.create_household(
                session_id=sess_id,
                household_key=f"vance_household_{sess_id}",
                surname="Vance",
                father=father,
                mother=mother,
                narrative_siblings=[
                    {"name": "Ayane Vance", "first_name": "Ayane", "gender": "female", "grade": "Freshman", "role": "Student"}
                ]
            )

            # Create child contact Su-bin Vance
            c_subin = db.upsert_contact(
                session_id=sess_id,
                npc_id="su_bin_vance",
                name="Su-bin Vance",
                gender="female",
                basic_info={"grade": "Junior", "role": "Student"}
            )
            db.assign_contact_household(sess_id, c_subin["id"], hh_id)

            # Hydrate George Vance into an active contact
            parent_contact = genealogy.hydrate_parent_to_contact(sess_id, hh_id, parent_role="father")
            self.assertIsNotNone(parent_contact)
            self.assertEqual(parent_contact["name"], "George Vance")
            self.assertEqual(parent_contact["household_id"], hh_id)

            # Re-hydrate the household entity
            hh_raw = db.get_household_by_id(hh_id)
            hh_hydrated = genealogy._hydrate_household_entity(hh_raw, c_subin, scenario="fantasy")

            # 1. Father dict should be linked to the active contact ID and is_contactable=True
            self.assertEqual(hh_hydrated["father"]["id"], parent_contact["id"])
            self.assertTrue(hh_hydrated["father"]["is_contactable"])

            # 2. George Vance must NOT be present in children list
            child_names = [c["name"] for c in hh_hydrated["children"]]
            self.assertNotIn("George Vance", child_names)
            self.assertIn("Su-bin Vance", child_names)
            self.assertIn("Ayane Vance", child_names)

            # 3. View family tree from child's perspective (Su-bin Vance)
            subin_tree = genealogy.build_family_tree_for_member(hh_hydrated, "Su-bin Vance", scenario="fantasy")
            self.assertEqual(subin_tree[0]["relation"], "Father")
            self.assertEqual(subin_tree[0]["name"], "George Vance")
            self.assertEqual(subin_tree[1]["relation"], "Mother")
            self.assertEqual(subin_tree[1]["name"], "Evelyn Vance")
            # Sibling must be Ayane Vance, NOT George Vance!
            sib_relations = [m["relation"] for m in subin_tree[2:]]
            sib_names = [m["name"] for m in subin_tree[2:]]
            self.assertNotIn("George Vance", sib_names)
            self.assertIn("Ayane Vance", sib_names)
            self.assertTrue(all("Brother" not in r and "Sister" in r for r in sib_relations))

            # 4. View family tree from parent's perspective (George Vance)
            george_tree = genealogy.build_family_tree_for_member(hh_hydrated, "George Vance", scenario="fantasy")
            self.assertEqual(george_tree[0]["relation"], "Wife")
            self.assertEqual(george_tree[0]["name"], "Evelyn Vance")
            # Descendants should be Su-bin and Ayane as Daughters
            desc_relations = [m["relation"] for m in george_tree[1:]]
            desc_names = [m["name"] for m in george_tree[1:]]
            self.assertIn("Su-bin Vance", desc_names)
            self.assertIn("Ayane Vance", desc_names)
            self.assertTrue(all(r == "Daughter" for r in desc_relations))
        finally:
            with db.get_conn() as conn:
                db.core._delete_session_records(conn, sess_id)


if __name__ == "__main__":
    unittest.main()


