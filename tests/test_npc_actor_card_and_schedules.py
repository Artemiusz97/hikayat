"""
tests/test_npc_actor_card_and_schedules.py
==========================================
Unit and integration tests for:
  - Unified Actor Direction Card builder (mechanics/social/persona/actor_card.py)
  - 3-Tier Situational Persona Gating (Layer 1 Social, Layer 2 Romantic, Layer 3 Erotic)
  - Grounded in-room physical activity derivation
  - Categorized mannerisms with repetition cooldown
  - Immediate conversational agenda & schedule transitions
  - Friction and boundaries from dislikes & traits
  - Time-of-day deterministic schedules (mechanics/world/schedules.py)
  - Open relational threads and emotional tone persistence (Migration 20)
"""
import unittest
import time
import db
from mechanics.social.persona.actor_card import (
    derive_scene_activity,
    format_mannerisms_categorized,
    derive_immediate_agenda,
    format_friction_and_boundaries,
    determine_situational_layer,
    build_actor_direction_card,
)
from mechanics.world.schedules import (
    get_time_block_key,
    is_schedule_transition_imminent,
    get_npc_schedule,
    get_npc_scheduled_location,
)
from game_engine.npcs.stage_manager import compute_pre_turn_stage


class TestNPCActorCardAndSchedules(unittest.TestCase):
    def setUp(self):
        self.user_id = 999901
        self.session_id = 999902
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM npc_memories WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id = ?", (self.session_id,))

        self.char = db.create_character(
            user_id=self.user_id,
            name="Hiroshi",
            char_class="Student",
            gender="male"
        )
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM npc_memories WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id = ?", (self.session_id,))

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Schedules & Time Blocks
    # ──────────────────────────────────────────────────────────────────────────

    def test_time_block_keys(self):
        self.assertEqual(get_time_block_key(360), "morning")   # 06:00
        self.assertEqual(get_time_block_key(500), "morning")   # 08:20
        self.assertEqual(get_time_block_key(720), "lunch")     # 12:00
        self.assertEqual(get_time_block_key(750), "lunch")     # 12:30
        self.assertEqual(get_time_block_key(780), "afternoon") # 13:00
        self.assertEqual(get_time_block_key(900), "afternoon") # 15:00
        self.assertEqual(get_time_block_key(1020), "evening")  # 17:00
        self.assertEqual(get_time_block_key(1200), "night")    # 20:00
        self.assertEqual(get_time_block_key(100), "night")     # 01:40

    def test_schedule_transition_imminent(self):
        # 11:45 is 15 minutes before 12:00 (lunch)
        imminent, cur_b, next_b, mins = is_schedule_transition_imminent(705, window_minutes=20)
        self.assertTrue(imminent)
        self.assertEqual(cur_b, "morning")
        self.assertEqual(next_b, "lunch")
        self.assertEqual(mins, 15)

        # 10:00 is not near boundary
        imminent_false, cur_b, _, _ = is_schedule_transition_imminent(600, window_minutes=15)
        self.assertFalse(imminent_false)

    def test_npc_schedule_derivation_school(self):
        npc = {
            "name": "Ayame Suzuki",
            "role": "Student",
            "club": "Kendo Club",
            "primary_facility": "Westlake Academy ➔ Classroom 2-A",
            "unlocked_traits": ["Disciplined", "Athletic"],
        }
        sched = get_npc_schedule(npc, scen_key="high_school_drama")
        self.assertIn("morning", sched)
        self.assertIn("lunch", sched)
        self.assertIn("afternoon", sched)
        self.assertIn("evening", sched)
        self.assertIn("night", sched)
        # Kendo club goes to dojo/gym in afternoon
        self.assertIn("Martial Arts Dojo", sched["afternoon"])

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Scene Activity & Immediate Agenda
    # ──────────────────────────────────────────────────────────────────────────

    def test_derive_scene_activity_grounded(self):
        npc = {
            "name": "Ayame",
            "role": "Student",
            "club": "Swim Club",
            "preferences": ["Likes Green Tea", "Dislikes Crowds"]
        }
        # In swimming pool
        act_pool = derive_scene_activity(npc, location="Indoor Swimming Pool", current_minute=900)
        self.assertIn("swim", act_pool.lower())

        # In library
        act_lib = derive_scene_activity(npc, location="School Library", current_minute=500)
        self.assertIn("table", act_lib.lower())

        # In courtyard with dislike crowds
        act_court = derive_scene_activity(npc, location="Central Courtyard", current_minute=730)
        self.assertIn("bench", act_court.lower())

    def test_derive_immediate_agenda_imminent_transition(self):
        npc = {
            "name": "Ayame",
            "role": "Student",
            "club": "Kendo Club",
            "primary_facility": "Classroom 2-A"
        }
        session = {"current_minute": 705, "scenario": "high_school_drama"}
        agenda = derive_immediate_agenda(npc, session=session)
        self.assertIn("15 minutes", agenda)
        self.assertIn("Lunch", agenda)

    def test_derive_immediate_agenda_open_thread(self):
        npc = {
            "name": "Ayame",
            "open_thread": "Borrowed history notes need to be returned"
        }
        session = {"current_minute": 500, "scenario": "high_school_drama"}
        agenda = derive_immediate_agenda(npc, session=session)
        self.assertIn("Borrowed history notes", agenda)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Categorized Mannerisms & Repetition Cooldown
    # ──────────────────────────────────────────────────────────────────────────

    def test_format_mannerisms_categorized_and_cooldown(self):
        raw = [
            "Adjusts glasses when thinking",
            "Crosses arms defensively when challenged",
            "Smiles warmly and leans close"
        ]
        # Without history
        cat = format_mannerisms_categorized(raw, history_text="")
        self.assertTrue(len(cat["idle"]) >= 1)
        self.assertTrue(len(cat["guarded"]) >= 1)
        self.assertTrue(len(cat["warm"]) >= 1)
        self.assertNotIn("Used last turn", cat["guarded"][0])

        # With previous turn narrative using 'crosses arms'
        cat_used = format_mannerisms_categorized(raw, history_text="Ayame crosses arms defensively as she speaks.")
        self.assertTrue(any("Used last turn — vary body language this turn" in m for m in cat_used["guarded"]))

    # ──────────────────────────────────────────────────────────────────────────
    # 4. Friction and Boundaries
    # ──────────────────────────────────────────────────────────────────────────

    def test_friction_and_boundaries(self):
        npc = {
            "name": "Kaito",
            "preferences": ["Dislikes Arrogance", "Hates Lies"],
            "unlocked_traits": ["Proud"]
        }
        frictions = format_friction_and_boundaries(npc)
        self.assertTrue(len(frictions) >= 2)
        combined = " ".join(frictions).lower()
        self.assertIn("arrogant", combined)
        self.assertIn("dishonesty", combined)
        self.assertIn("pride", combined)

    # ──────────────────────────────────────────────────────────────────────────
    # 5. 3-Tier Situational Persona Gating (Actor Direction Card)
    # ──────────────────────────────────────────────────────────────────────────

    def test_layer_1_everyday_social_card_gates_out_intimacy(self):
        """Layer 1 must NEVER leak anatomy, undergarments, sensitive spots, or climax rules."""
        npc = {
            "name": "Ayame Suzuki",
            "role": "Class President",
            "gender": "female",
            "race": "human",
            "relationship_score": 20,
            "track": "platonic",
            "appearance": {
                "eye_color": "amber",
                "hair_color": "black",
                "hair_length": "long",
                "hair_style": "straight",
                "stature": "average",
                "physique": "toned",
                "breast_size": "perky C-cup",
                "asset_texture": "silky smooth",
                "bra": "black lace bra",
                "underwear": "matching lace panties",
                "sensitive_spots": "nape of neck",
                "turn_ons": "whispered praise",
                "fetishes": "bondage",
                "intercourse_experience": "virgin",
                "intimate_demeanor": "Secretly bashful",
                "intimate_dynamic": "Submissive / sensual",
                "erotic_openness": "moderate"
            },
            "preferences": ["Likes Green Tea", "Dislikes Noise"],
            "unlocked_traits": ["Dignified", "Diligent"]
        }
        session = {"current_minute": 500, "scenario": "high_school_drama", "current_location": "Classroom 2-A"}
        card = build_actor_direction_card(session, npc, in_active_erotic=False)

        # Layer 1 elements present
        self.assertIn("ACTOR DIRECTION CARD — Ayame Suzuki", card)
        self.assertIn("[Situational Presence & Agency]", card)
        self.assertIn("[Behavioral Cues & Mannerisms]", card)
        self.assertIn("[Relational Standing & Open Threads]", card)
        self.assertIn("Likes & Desires: Likes Green Tea", card)
        self.assertIn("PREFERENCE SYNERGY:", card)

        # Explicit intimacy strictly gated out in Layer 1
        self.assertNotIn("perky C-cup", card)
        self.assertNotIn("black lace bra", card)
        self.assertNotIn("matching lace panties", card)
        self.assertNotIn("Sensitive Spots: nape of neck", card)
        self.assertNotIn("Kinks: bondage", card)
        self.assertNotIn("INTIMATE PACING & CLIMAX PRIMACY", card)
        self.assertNotIn("[Layer 2: Romantic Tension", card)
        self.assertNotIn("[Layer 3: Active Intimacy", card)

    def test_layer_2_romantic_card_activates_demeanor_and_dynamic(self):
        """Layer 2 activates demeanor, dynamic, turn-ons/offs preview, but keeps full erotic anatomy gated."""
        npc = {
            "name": "Ayame Suzuki",
            "role": "Class President",
            "gender": "female",
            "race": "human",
            "relationship_score": 110,  # Level 2 / High Affinity
            "track": "romantic",
            "appearance": {
                "intimate_demeanor": "Secretly bashful",
                "intimate_dynamic": "Submissive / sensual",
                "turn_ons": "whispered praise",
                "turn_offs": "crude remarks",
                "intercourse_experience": "virgin",
                "breast_size": "perky C-cup",
                "bra": "black lace bra"
            },
            "preferences": ["Likes Green Tea"],
            "unlocked_traits": ["Dignified"]
        }
        session = {"current_minute": 500, "scenario": "high_school_drama", "current_location": "Classroom 2-A"}
        card = build_actor_direction_card(session, npc, in_active_erotic=False)

        # Layer 2 elements present
        self.assertIn("[Layer 2: Romantic Tension & Private Demeanor]", card)
        self.assertIn("Intimate Demeanor: Secretly bashful", card)
        self.assertIn("Intimate Dynamic: Submissive / sensual", card)
        self.assertIn("INTIMATE TURN-OFFS & AVERSIONS", card)
        self.assertIn("Romantic Canon:", card)

        # Layer 3 elements NOT present
        self.assertNotIn("[Layer 3: Active Intimacy", card)
        self.assertNotIn("black lace bra", card)
        self.assertNotIn("INTIMATE PACING & CLIMAX PRIMACY", card)

    def test_layer_3_erotic_card_activates_full_intimacy_and_climax_rules(self):
        """Layer 3 activates undergarments, anatomy directives, kinks, and climax rules."""
        npc = {
            "name": "Ayame Suzuki",
            "role": "Class President",
            "gender": "female",
            "race": "human",
            "relationship_score": 150,
            "track": "romantic",
            "appearance": {
                "intimate_demeanor": "Secretly bashful",
                "intimate_dynamic": "Submissive / sensual",
                "sensitive_spots": "nape of neck, inner thighs",
                "turn_ons": "whispered praise",
                "turn_offs": "crude remarks",
                "fetishes": "sensory tease",
                "intercourse_experience": "virgin",
                "breast_size": "delicate C-cup",
                "asset_texture": "silky soft skin",
                "bra": "lace bralette",
                "underwear": "silk panties",
                "undergarment_color": "crimson"
            },
            "preferences": ["Likes Green Tea"],
            "unlocked_traits": ["Dignified"]
        }
        session = {"current_minute": 1300, "scenario": "nsfw_high_school_drama", "current_location": "Bedroom"}
        # in_active_erotic = True triggers Layer 3
        card = build_actor_direction_card(session, npc, in_active_erotic=True)

        self.assertIn("[Layer 3: Active Intimacy & Anatomy Directive]", card)
        self.assertIn("Wearing crimson lace bralette and silk panties", card)
        self.assertIn("Sensitive Spots: nape of neck, inner thighs", card)
        self.assertIn("Kinks: sensory tease", card)
        self.assertIn("INTIMATE PACING & CLIMAX PRIMACY", card)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. Open Relational Threads & Migration 20
    # ──────────────────────────────────────────────────────────────────────────

    def test_migration_20_persistence(self):
        # Insert contact with open_thread and emotional_tone
        c = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="ayame_suzuki",
            name="Ayame Suzuki",
            open_thread="Agreed to study together this Friday evening",
            emotional_tone="grateful"
        )
        self.assertEqual(c["open_thread"], "Agreed to study together this Friday evening")
        self.assertEqual(c["emotional_tone"], "grateful")

        # Update contact open thread
        db.update_contact_open_thread(
            session_id=self.session_id,
            npc_id="ayame_suzuki",
            open_thread="Met on Friday and agreed to visit the shrine next week",
            emotional_tone="flustered"
        )
        fetched = db.get_contact(self.session_id, "ayame_suzuki")
        self.assertEqual(fetched["open_thread"], "Met on Friday and agreed to visit the shrine next week")
        self.assertEqual(fetched["emotional_tone"], "flustered")

        # Memory insertion with open thread and emotional tone
        db.add_npc_memory(
            session_id=self.session_id,
            npc_name="Ayame Suzuki",
            turn_index=2,
            memory_fact="Player helped her pick up scattered documents",
            emotional_tone="grateful",
            open_thread="Wants to buy player a juice box as thanks"
        )
        mems = db.get_npc_memories(self.session_id, "Ayame Suzuki")
        self.assertEqual(len(mems), 1)
        self.assertEqual(mems[0]["emotional_tone"], "grateful")
        self.assertEqual(mems[0]["open_thread"], "Wants to buy player a juice box as thanks")


if __name__ == "__main__":
    unittest.main()
