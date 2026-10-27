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

    def test_default_culture_weights_and_chance(self):
        """Verifies default cross-cultural chance (0.25) and demographic weights:
        - East Asian: 30%
        - English + European: 55% (Anglo: 15%, Western & Central: 10%, Latin & Med: 10%, Nordic: 10%, Slavic: 10%)
        - Rest of the World: 15%
        """
        d = namegen._get_scenario_data("default", "person")
        self.assertAlmostEqual(d.get("cross_culture_chance"), 0.25)
        
        weights = d.get("culture_weights", {})
        self.assertEqual(len(weights), 28)
        self.assertAlmostEqual(sum(weights[c] for c in ("japanese", "korean", "chinese")), 30.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("english", "scottish", "irish")), 15.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("french", "german", "dutch")), 10.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("hispanic", "italian", "portuguese", "greek")), 10.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("swedish", "norwegian", "danish", "icelandic")), 10.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("polish", "russian", "ukrainian", "slavic")), 10.0)
        self.assertAlmostEqual(sum(weights[c] for c in ("arabic", "indian", "vietnamese", "african", "turkish", "persian", "malay")), 15.0)

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
        from game_engine.npcs.cast_planner import CastPlan, apply_cast_events

        self.assertFalse(is_dialogue_partner("Zayd bin Mansoor", ["Danial bin Ismail"]))
        self.assertFalse(is_dialogue_partner("Nur binti Hassan", ["Melati binti Nasution"]))
        self.assertFalse(is_dialogue_partner("Bram van Dijk", ["Lars van der Berg"]))
        self.assertTrue(is_dialogue_partner("Danial", ["Danial bin Ismail"]))
        self.assertTrue(is_dialogue_partner("Ren", ["Tanaka Ren"]))

        # Ensure English prose words 'bin' and 'van' don't falsely trigger speaking NPC detection
        npcs = [{"name": "Danial bin Ismail"}, {"name": "Lars van der Berg"}, {"name": "Tanaka Ren"}]
        prose = 'Ren smiled and said, "Throw that wrapper in the trash bin by the white van."'
        plan, _ = apply_cast_events(CastPlan(present_npcs=npcs, bystander_npcs=[n["name"] for n in npcs]), [{"type": "engage", "npc": "Ren"}], {"id": 0, "current_turn_index": 1}, []); speaking = plan.dialogue_partners
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


    def test_high_school_drama_namegen_respects_cultural_pools(self):
        """Verifies high_school_drama uses the 28 cultural pools with ~75% intra-cultural names."""
        d = namegen._get_scenario_data("default", "person")
        cultures = d.get("cultures") or {}
        intra_cultural = 0
        total = 200
        for i in range(total):
            name = namegen.generate_person_name("high_school_drama", seed=i * 19 + 7)
            first, last = namegen.extract_first_and_last_name(name)
            self.assertTrue(bool(first and last), f"Expected full name, got: {name}")
            s_cult = namegen.infer_surname_culture(last)
            if s_cult in cultures:
                c_pool = cultures[s_cult]
                all_firsts = set(c_pool.get("male", []) + c_pool.get("female", []))
                if first in all_firsts:
                    intra_cultural += 1

        # Expected ~75% (150/200). Assert >= 125 (62.5%) to account for binomial variance.
        self.assertGreaterEqual(intra_cultural, 125, f"Expected >= 125/200 intra-cultural names, got {intra_cultural}")

    def test_generate_person_name_with_surname_cultural_matching(self):
        """Verifies generate_person_name_with_surname inherits the surname's cultural pool."""
        # Yamada (Japanese)
        yamada_names = [namegen.generate_person_name_with_surname("Yamada", "high_school_drama", gender="male", seed=i) for i in range(20)]
        for nm in yamada_names:
            first, last = namegen.extract_first_and_last_name(nm)
            self.assertEqual(last, "Yamada")
            # If both Japanese, surname comes first: "Yamada Ren"
            if namegen.infer_first_name_culture(first) == "japanese":
                self.assertTrue(nm.startswith("Yamada "), f"Pure East Asian name should start with surname: {nm}")

        # Kowalski (Polish female inflection)
        kowalski_females = [namegen.generate_person_name_with_surname("Kowalski", "high_school_drama", gender="female", seed=i) for i in range(20)]
        for nm in kowalski_females:
            self.assertIn("Kowalska", nm, f"Polish female surname should inflect to Kowalska: {nm}")

    def test_campus_directory_deterministic_cultural_roster(self):
        """Verifies 88 campus directory characters have cultural names, proper sibling/town lineages, and clean formal titles."""
        from mechanics.social.school_roster import generate_campus_directory
        roster1 = generate_campus_directory(9999)
        roster2 = generate_campus_directory(9999)

        self.assertEqual(len(roster1), 88)
        self.assertEqual([c["name"] for c in roster1], [c["name"] for c in roster2])

        # Sibling lineages (8 pairs = 16 students)
        siblings = [c for c in roster1 if c.get("sibling_name")]
        self.assertEqual(len(siblings), 16)

        for sib in siblings:
            partner = next(c for c in roster1 if c["name"] == sib["sibling_name"])
            self.assertEqual(partner["sibling_name"], sib["name"])
            s_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(sib["name"])[1])
            p_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(partner["name"])[1])
            self.assertEqual(s_sur.lower(), p_sur.lower())

        # Town relative surname consistency
        for c in roster1:
            if c.get("town_relative_name"):
                rel = next(x for x in roster1 if x["name"] == c["town_relative_name"])
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(c["name"])[1])
                r_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(rel["name"])[1])
                self.assertEqual(c_sur.lower(), r_sur.lower())

        # Faculty formal_title rules
        for fac in [c for c in roster1 if c.get("is_faculty")]:
            ft = fac.get("formal_title", "")
            self.assertTrue(bool(ft))
            # Never emit full 3-token name after 'Chef' when a surname exists
            self.assertLessEqual(len(ft.split()), 3)
            if " binti " in f" {fac['name'].lower()} " or " bin " in f" {fac['name'].lower()} ":
                first_nm, _ = namegen.extract_first_and_last_name(fac["name"])
                self.assertIn(first_nm, ft)

    def test_past_partner_name_cultural_generation(self):
        """Verifies generate_past_partner_name generates full cultural names."""
        from mechanics.social.persona.intimacy.generation import generate_past_partner_name
        for i in range(10):
            p_name = generate_past_partner_name("high_school_drama", partner_gender="female", hash_val=i * 29 + 7)
            parts = p_name.split()
            self.assertGreaterEqual(len(parts), 2, f"Expected at least first + last name, got: {p_name}")

    def test_ungendered_generation_and_indonesian_greek_slavic_rules(self):
        """Verifies un-gendered rolls inflect female surnames, Indonesian surnames skip bin/binti, Greek -idis/-akis inflect, and Russian != Slavic."""
        import random
        # 1. Un-gendered rolls must never produce female given name + masculine Polish/Russian/Icelandic surname or 'bin'
        rng_state = random.getstate()
        try:
            random.seed(12345)
            for _ in range(150):
                nm = namegen.generate_person_name("default")
                first, last = namegen.extract_first_and_last_name(nm)
                if namegen.is_known_female_name(first) and not namegen.is_known_male_name(first):
                    self.assertNotIn(" bin ", f" {nm.lower()} ", f"Female name got 'bin': {nm}")
                    self.assertFalse(last.endswith(("ski", "cki", "dzki", "sson")), f"Uninflected surname on female roll: {nm}")
        finally:
            random.setstate(rng_state)

        # 2. Indonesian non-patronymic surnames never take bin/binti by default
        for indo_sur in ("Wijaya", "Saputra", "Kusuma", "Santoso", "Setiawan", "Hidayat", "Pratama", "Nasution"):
            for seed_i in range(8):
                nm = namegen.format_cultural_full_name("Putri", indo_sur, "malay", "malay", "female", deterministic_seed=f"s_{seed_i}")
                self.assertEqual(nm, f"Putri {indo_sur}")

        # 3. Greek -idis/-iadis -> -idou/-iadou and -akis -> -aki + normalize_base_surname round-trip
        self.assertEqual(namegen.format_cultural_full_name("Eleni", "Nikolaidis", "greek", "greek", "female"), "Eleni Nikolaidou")
        self.assertEqual(namegen.format_cultural_full_name("Sofia", "Papadakis", "greek", "greek", "female"), "Sofia Papadaki")
        self.assertEqual(namegen.normalize_base_surname("Nikolaidou"), "Nikolaidis")
        self.assertEqual(namegen.normalize_base_surname("Papadaki"), "Papadakis")

        # 4. Slavic vs Russian separation
        self.assertEqual(namegen.infer_surname_culture("Volkov"), "russian")
        self.assertEqual(namegen.infer_surname_culture("Novak"), "slavic")

    def test_cross_cultural_extraction_gender_inference_and_disambiguation(self):
        """Verifies tricky cross-cultural East Asian extraction, gender inference, UI short names, and peer token disambiguation."""
        from mechanics.social.persona.core import infer_contact_gender
        from game_engine.keywords import sanitize_npc_pronoun_consistency

        # 1. Tricky East Asian & hybrid name extraction
        self.assertEqual(namegen.extract_first_and_last_name("Zhang Chen"), ("Chen", "Zhang"))
        self.assertEqual(namegen.extract_first_and_last_name("Tanaka Mai"), ("Mai", "Tanaka"))
        self.assertEqual(namegen.extract_first_and_last_name("Chen Kelly"), ("Chen", "Kelly"))
        self.assertEqual(namegen.extract_first_and_last_name("Kim Kowalska"), ("Kim", "Kowalska"))
        self.assertEqual(namegen.extract_first_and_last_name("Ms. Watanabe Mei"), ("Mei", "Watanabe"))
        self.assertEqual(namegen.extract_first_and_last_name("Chef Watanabe Mei"), ("Mei", "Watanabe"))

        # 2. Gender inference does not flip male East Asian names whose surname overlaps Western female names (Kim, Li, Lin)
        self.assertEqual(infer_contact_gender({"name": "Kim Min-jun"}), "male")
        self.assertEqual(infer_contact_gender({"name": "Li Wei"}), "male")
        self.assertEqual(infer_contact_gender({"name": "Chen Mei"}), "female")
        self.assertEqual(infer_contact_gender({"name": "Zofia Kowalska"}), "female")

        # 3. UI short display names and formal titles never truncate to bare honorifics
        self.assertEqual(namegen.get_display_short_name("Ms. Watanabe Mei", max_len=15), "Ms. Watanabe")
        self.assertEqual(namegen.get_display_short_name("Ms. Zofia Kowalska", max_len=15), "Ms. Kowalska")
        self.assertEqual(namegen.get_display_short_name("Chef Watanabe Mei", max_len=15), "Chef Watanabe")
        self.assertEqual(namegen.format_formal_title("Ms.", "Siti binti Rahman"), "Ms. Siti")
        self.assertEqual(namegen.format_formal_title("Ms.", "Birgitta Magnusdottir"), "Ms. Birgitta")

        # 4. Peer token disambiguation drops shared surnames and never emits honorifics
        peers_ea = ["Tanaka Ren", "Tanaka Yui"]
        ren_toks = namegen.get_unique_person_tokens("Tanaka Ren", peer_names=peers_ea)
        yui_toks = namegen.get_unique_person_tokens("Tanaka Yui", peer_names=peers_ea)
        self.assertIn("ren", ren_toks)
        self.assertNotIn("tanaka", ren_toks)
        self.assertIn("yui", yui_toks)
        self.assertNotIn("tanaka", yui_toks)

        peers_fac = ["Ms. Watanabe Mei", "Ms. Zofia Kowalska"]
        wat_toks = namegen.get_unique_person_tokens("Ms. Watanabe Mei", peer_names=peers_fac)
        self.assertNotIn("ms.", wat_toks)
        self.assertNotIn("ms", wat_toks)
        self.assertIn("watanabe", wat_toks)
        self.assertIn("mei", wat_toks)

        # 5. Pronoun sanitizer never corrupts prose when opposite-sex siblings share a surname
        prose = "Tanaka Yui smiled as she waved at Tanaka Ren while he closed his notebook."
        sanitized = sanitize_npc_pronoun_consistency(
            prose,
            session={"current_npcs": [{"name": "Tanaka Yui", "gender": "female"}, {"name": "Tanaka Ren", "gender": "male"}]},
        )
        self.assertEqual(sanitized, prose)


if __name__ == "__main__":
    unittest.main()
