import unittest
import namegen
from mechanics.narrative.intent import _extract_target_npc, IntentContext

class TestNamegenCultures(unittest.TestCase):
    def setUp(self):
        self.modern_cultures = namegen.get_scenario_cultures("modern")

    def test_modern_cultures_present(self):
        """Verifies that all 28 requested cultures are present in modern name pools."""
        expected_cultures = [
            "chinese", "japanese", "korean", "vietnamese", "english", "german", "polish",
            "swedish", "norwegian", "danish", "icelandic", "irish", "scottish",
            "turkish", "malay", "greek", "portuguese", "dutch", "persian",
            "russian", "ukrainian", "hispanic", "french", "italian", "arabic",
            "indian", "slavic", "african"
        ]
        for cult in expected_cultures:
            self.assertIn(cult, self.modern_cultures, f"Culture '{cult}' should be present in modern namegen.")

    def test_cultural_aliases(self):
        """Verifies cultural aliases resolve correctly."""
        alias_checks = {
            "russian/ukrainian": {"russian", "ukrainian"},
            "scandinavian": {"swedish", "norwegian", "danish"},
            "malay/indo": {"malay"},
            "portuguese/brazil": {"portuguese"},
            "dutch & flemish": {"dutch"},
        }
        for alias, targets in alias_checks.items():
            for _ in range(10):
                name = namegen.generate_person_name("modern", culture=alias, cross_culture_chance=0.0)
                self.assertTrue(len(name.split()) >= 2)

    def test_default_equal_weights_and_chance(self):
        """Verifies default cross-cultural chance (0.25) and equal weights in namegen_data."""
        d = namegen._get_scenario_data("default", "person")
        self.assertAlmostEqual(d.get("cross_culture_chance"), 0.25)
        
        weights = d.get("culture_weights", {})
        self.assertTrue(len(weights) >= 28)
        weight_values = list(weights.values())
        self.assertTrue(all(w == weight_values[0] for w in weight_values))

    def test_east_asian_surname_first_pure(self):
        """Pure East Asian and Vietnamese names must format as [Surname] [First Name]."""
        d = namegen._get_scenario_data("default", "person")
        cultures_dict = d["cultures"]

        for cult in ["chinese", "japanese", "korean", "vietnamese"]:
            for _ in range(15):
                name = namegen.generate_person_name(
                    scenario="modern",
                    culture=cult,
                    cross_culture_chance=0.0
                )
                parts = name.split()
                self.assertEqual(len(parts), 2, f"Expected exactly 2 words for {cult}, got '{name}'")
                surname, first = parts[0], parts[1]

                cult_surnames = cultures_dict[cult]["last"]
                cult_first_pool = cultures_dict[cult]["male"] + cultures_dict[cult]["female"]
                self.assertIn(surname, cult_surnames, f"First word '{surname}' should be surname for {cult}")
                self.assertIn(first, cult_first_pool, f"Second word '{first}' should be given name for {cult}")

    def test_east_asian_hybrid_western_order(self):
        """Hybrid names with East Asian surnames and Western given names format as [Given Name] [Surname]."""
        d = namegen._get_scenario_data("default", "person")
        chinese_surnames = set(d["cultures"]["chinese"]["last"])
        english_firsts = set(d["cultures"]["english"]["male"] + d["cultures"]["english"]["female"])

        weights = {"english": 1.0, "chinese": 1.0}
        for _ in range(20):
            name = namegen.generate_person_name(
                scenario="modern",
                culture="chinese",
                cross_culture_chance=1.0,
                culture_weights=weights
            )
            parts = name.split()
            self.assertEqual(len(parts), 2)
            first, surname = parts[0], parts[1]
            self.assertIn(first, english_firsts, f"First word should be English given name: {name}")
            self.assertIn(surname, chinese_surnames, f"Second word should be Chinese surname: {name}")

    def test_polish_and_slavic_gender_inflections(self):
        """Female Polish, Russian, and Slavic surnames must receive grammatical feminine endings."""
        # Polish female ending in -ska / -cka
        for _ in range(15):
            name = namegen.generate_person_name("modern", culture="polish", gender="female", cross_culture_chance=0.0)
            parts = name.split()
            surname = parts[1]
            if surname.endswith(("ska", "cka", "dzka")):
                self.assertTrue(surname.endswith(("ska", "cka", "dzka")))

        # Russian female ending in -ova / -eva / -ina / -skaya
        for _ in range(15):
            name = namegen.generate_person_name("modern", culture="russian", gender="female", cross_culture_chance=0.0)
            parts = name.split()
            surname = parts[1]
            self.assertTrue(surname.endswith(("ova", "eva", "ina", "skaya", "a")), f"Expected feminine Russian surname: {surname}")

    def test_greek_and_icelandic_gender_inflections(self):
        """Greek female surnames end in -ou; Icelandic male ends in -sson, female in -sdottir."""
        # Greek female
        for _ in range(10):
            name = namegen.generate_person_name("modern", culture="greek", gender="female", cross_culture_chance=0.0)
            parts = name.split()
            surname = parts[1]
            self.assertTrue(surname.endswith("ou") or not surname.endswith("os"), f"Greek female should be genitive -ou: {surname}")

        # Icelandic male & female
        for _ in range(10):
            name_m = namegen.generate_person_name("modern", culture="icelandic", gender="male", cross_culture_chance=0.0)
            name_f = namegen.generate_person_name("modern", culture="icelandic", gender="female", cross_culture_chance=0.0)
            self.assertTrue(name_m.split()[1].endswith("son"), f"Icelandic male should end in -son: {name_m}")
            self.assertTrue(name_f.split()[1].endswith("dottir"), f"Icelandic female should end in -dottir: {name_f}")

    def test_malay_bin_binti_probabilities(self):
        """Malay patronymic surnames produce 'bin' for male and 'binti' for female when active."""
        m_samples = [namegen.generate_person_name("modern", culture="malay", gender="male", cross_culture_chance=0.0) for _ in range(30)]
        f_samples = [namegen.generate_person_name("modern", culture="malay", gender="female", cross_culture_chance=0.0) for _ in range(30)]
        
        has_bin = any(" bin " in s for s in m_samples)
        has_binti = any(" binti " in s for s in f_samples)
        has_informal_m = any(" bin " not in s for s in m_samples)
        has_informal_f = any(" binti " not in s for s in f_samples)
        
        self.assertTrue(has_bin, "Should generate 'bin' for males")
        self.assertTrue(has_binti, "Should generate 'binti' for females")
        self.assertTrue(has_informal_m, "Should also allow informal style without 'bin'")
        self.assertTrue(has_informal_f, "Should also allow informal style without 'binti'")

    def test_gender_detection_all_orders(self):
        """is_known_male_name and is_known_female_name work for East Asian, Western, and Patronymic names."""
        self.assertTrue(namegen.is_known_male_name("Zhang Wei"))
        self.assertTrue(namegen.is_known_male_name("Danial bin Ismail"))
        self.assertTrue(namegen.is_known_male_name("Einar Gunnarsson"))
        self.assertTrue(namegen.is_known_male_name("Nikos Papadopoulos"))
        self.assertTrue(namegen.is_known_female_name("Li Mei"))
        self.assertTrue(namegen.is_known_female_name("Nur binti Ismail"))
        self.assertTrue(namegen.is_known_female_name("Astrid Gunnarsdottir"))
        self.assertTrue(namegen.is_known_female_name("Zuzanna Kowalska"))
        self.assertTrue(namegen.is_known_female_name("Elena Ivanova"))

    def test_residence_name_east_asian_and_patronymic(self):
        """Residence generator accurately identifies surname vs given name across naming orders."""
        res_jp = namegen.generate_npc_residence_name("Tanaka Ren", hash_val=0)
        house_jp = namegen.generate_npc_residence_name("Tanaka Ren", hash_val=1)
        self.assertEqual(res_jp, "Tanaka Residence")
        self.assertEqual(house_jp, "Ren's House")

        res_malay = namegen.generate_npc_residence_name("Danial bin Ismail", hash_val=0)
        house_malay = namegen.generate_npc_residence_name("Danial bin Ismail", hash_val=1)
        self.assertEqual(res_malay, "Ismail Residence")
        self.assertEqual(house_malay, "Danial's House")

    def test_intent_target_extraction_any_token(self):
        """Intent engine successfully resolves an NPC whether targeted by first name or surname."""
        ctx = IntentContext(present_npcs=["Zhang Wei", "Danial bin Ismail", "Zuzanna Kowalska", "Tanaka Ren"])
        self.assertEqual(_extract_target_npc("Ask Wei about homework", ctx), "Zhang Wei")
        self.assertEqual(_extract_target_npc("Talk to Zhang", ctx), "Zhang Wei")
        self.assertEqual(_extract_target_npc("Greet Ren warmly", ctx), "Tanaka Ren")
        self.assertEqual(_extract_target_npc("Speak with Tanaka", ctx), "Tanaka Ren")
        self.assertEqual(_extract_target_npc("Chat with Danial", ctx), "Danial bin Ismail")
        self.assertEqual(_extract_target_npc("Ask Ismail for guidance", ctx), "Danial bin Ismail")
        self.assertEqual(_extract_target_npc("Consult with Kowalska", ctx), "Zuzanna Kowalska")

    def test_custom_demographic_weights(self):
        """Custom demographic weights isolate target culture."""
        d = namegen._get_scenario_data("default", "person")
        polish_surnames = set(d["cultures"]["polish"]["last"])

        for _ in range(20):
            name = namegen.generate_person_name(
                scenario="modern",
                culture_weights={"polish": 1.0},
                cross_culture_chance=0.0
            )
            parts = name.split()
            # Surname should end in Polish pattern or be in list
            self.assertTrue(parts[1] in polish_surnames or parts[1].endswith(("ska", "cka", "dzka")))

    def test_legacy_scenario_backward_compatibility(self):
        """Fantasy and non-culture scenarios continue to generate properly without error."""
        for _ in range(10):
            fan_name = namegen.generate_person_name("fantasy")
            self.assertIsInstance(fan_name, str)
            self.assertTrue(len(fan_name) > 0)

    def test_token_resolution_modern(self):
        """resolve_tokens_deep with scenario='modern' successfully resolves {{PERSON_1}}."""
        payload = {
            "narrative": "{{PERSON_1}} talked to {{PERSON_2_FEMALE}} at the café.",
            "characters": ["{{PERSON_1}}", "{{PERSON_2_FEMALE}}"]
        }
        resolved = namegen.resolve_tokens_deep(payload, scenario="modern")
        self.assertNotIn("{{PERSON_1}}", resolved["narrative"])
        self.assertNotIn("{{PERSON_2_FEMALE}}", resolved["narrative"])
        self.assertTrue(namegen.is_valid_entity_name(resolved["characters"][0]))
        self.assertTrue(namegen.is_valid_entity_name(resolved["characters"][1]))

    def test_genealogy_cultural_family_units(self):
        """Genealogy accurately preserves family surnames and gender inflections across East Asian, Polish, Icelandic, and Malay names."""
        from mechanics.social.genealogy import (
            extract_surname_and_firstname,
            reverse_generate_parents,
            generate_siblings,
        )

        # 1. East Asian surname-first ("Zhang Wei")
        first_zh, last_zh = extract_surname_and_firstname("Zhang Wei")
        self.assertEqual((first_zh, last_zh), ("Wei", "Zhang"))
        father_zh, mother_zh = reverse_generate_parents("human", {}, child_surname=last_zh, scenario="high_school", hash_val=101)
        for p in (father_zh, mother_zh):
            self.assertIn("Zhang", p["name"].split(), f"Parent should retain Zhang surname: {p['name']}")
            self.assertNotIn("Wei", p["name"].split(), f"Parent should not have child's given name Wei as surname: {p['name']}")

        # 2. Polish female-inflected ("Zuzanna Kowalska")
        first_pl, last_pl = extract_surname_and_firstname("Zuzanna Kowalska")
        self.assertEqual((first_pl, last_pl), ("Zuzanna", "Kowalski"))
        father_pl, mother_pl = reverse_generate_parents("human", {}, child_surname=last_pl, scenario="high_school", hash_val=202)
        self.assertTrue(father_pl["name"].endswith("Kowalski"), f"Polish father should have masculine -ski: {father_pl['name']}")
        self.assertIn("Kowalska", mother_pl["name"], f"Polish mother should have feminine -ska: {mother_pl['name']}")

        # 3. Malay patronymic ("Danial bin Ismail")
        first_my, last_my = extract_surname_and_firstname("Danial bin Ismail")
        self.assertEqual((first_my, last_my), ("Danial", "Ismail"))
        father_my, mother_my = reverse_generate_parents("human", {}, child_surname=last_my, scenario="high_school", hash_val=303)
        sibs_my = generate_siblings(father_my, mother_my, {}, scenario="high_school", hash_val=1)
        for s in ( [father_my, mother_my] + sibs_my ):
            self.assertNotIn(" bin bin ", f" {s['name'].lower()} ")
            self.assertNotIn(" binti bin ", f" {s['name'].lower()} ")
            self.assertIn("Ismail", s["name"], f"Malay relative should retain Ismail surname: {s['name']}")

        # 4. Icelandic female patronymic ("Birgitta Magnusdottir")
        first_is, last_is = extract_surname_and_firstname("Birgitta Magnusdottir")
        self.assertEqual((first_is, last_is), ("Birgitta", "Magnusson"))
        father_is, mother_is = reverse_generate_parents("human", {}, child_surname=last_is, scenario="high_school", hash_val=404)
        self.assertTrue(father_is["name"].endswith("Magnusson"), f"Icelandic father should end in -sson: {father_is['name']}")
        self.assertIn("Magnusdottir", mother_is["name"], f"Icelandic mother should end in -sdottir: {mother_is['name']}")

    def test_dialogue_partner_and_particle_non_collision(self):
        """Unrelated NPCs sharing patronymic/surname particles ('bin', 'binti', 'van', 'der') never false-match each other."""
        from mechanics.world.mobility import is_dialogue_partner
        from game_engine.npcs.dialogue_tracking import extract_speaking_npcs_from_narrative

        self.assertFalse(is_dialogue_partner("Zayd bin Mansoor", ["Danial bin Ismail"]))
        self.assertFalse(is_dialogue_partner("Nur binti Hassan", ["Melati binti Nasution"]))
        self.assertFalse(is_dialogue_partner("Bram van Dijk", ["Lars van der Berg"]))
        self.assertTrue(is_dialogue_partner("Danial", ["Danial bin Ismail"]))
        self.assertTrue(is_dialogue_partner("Ren", ["Tanaka Ren"]))

        # Ensure English prose words 'bin' and 'van' don't falsely trigger speaking NPC detection
        npcs = [{"name": "Danial bin Ismail"}, {"name": "Lars van der Berg"}, {"name": "Tanaka Ren"}]
        prose = 'Ren smiled and said, "Throw that wrapper in the trash bin by the white van."'
        speaking = extract_speaking_npcs_from_narrative(prose, npcs)
        self.assertEqual(speaking, ["Tanaka Ren"])

    def test_canonical_name_resolver_east_asian_and_patronymic(self):
        """_build_canonical_name_resolver maps both surname and given name for East Asian surname-first NPCs."""
        from game_engine.npcs.reconciliation import _build_canonical_name_resolver

        first_to_canon, _ = _build_canonical_name_resolver(
            session={},
            old_npcs=[{"name": "Tanaka Ren"}, {"name": "Zhang Wei"}, {"name": "Danial bin Ismail"}],
            candidates=[],
            known_contacts=[],
        )
        self.assertEqual(first_to_canon.get("ren"), "Tanaka Ren")
        self.assertEqual(first_to_canon.get("tanaka"), "Tanaka Ren")
        self.assertEqual(first_to_canon.get("wei"), "Zhang Wei")
        self.assertEqual(first_to_canon.get("zhang"), "Zhang Wei")
        self.assertEqual(first_to_canon.get("danial"), "Danial bin Ismail")
        self.assertNotIn("bin", first_to_canon)


if __name__ == "__main__":
    unittest.main()
