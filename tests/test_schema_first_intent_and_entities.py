from __future__ import annotations
"""
Comprehensive Test Suite for Schema-First Intent & Canonical Entity Architecture.
Tests all 8 decision points:
1. Pydantic & JSON Schema validation for Choice, ActionClassification, TrackerEntity, RelationshipUpdate.
2. Tagged intent resolution via resolve_action_intent.
3. Sub-intent disambiguation for intimate and social actions.
4. Legacy fallback resolution for untagged / general_action choices.
5. classify_custom_action fast-path vs. LLM routing rules.
6. Entity species and social_role_type isolation (preventing ear mutations and Scunthorpe contact disqualifications).
7. choices_cleaner intent-first filtering (saving club recruit choices and Ray/Pray bystander collisions).
8. affinity_engine structured tone & trait alignment and dialogue_tracking clean escalation without dict key contamination.
"""

import unittest
from unittest.mock import patch, MagicMock

from models.llm_schemas import Choice, ActionClassification, _VALID_INTENTS, _VALID_SUB_INTENTS
from models.trackers import TrackerEntity, RelationshipUpdate
from game_engine.schemas import (
    SCENE_SCHEMA,
    OUTCOME_SCHEMA,
    CLASSIFY_SCHEMA,
    RELATIONSHIP_UPDATE_FIELD,
    SOCIAL_ARBITER_SCHEMA,
)
from mechanics.narrative.intent import (
    IntentCategory,
    IntentContext,
    ActionIntent,
    resolve_action_intent,
    classify_action_intent,
)
from mechanics.social.relationships import is_contact_eligible
from mechanics.social.affinity_engine import calculate_social_affinity_delta
from mechanics.social.persona import SPECIES_TEMPLATES, get_species_key_from_race
from mechanics.social.races import normalize_race
from game_engine.choices_cleaner import clean_choices_impl
from game_engine.npcs.dialogue_tracking import (
    compute_scene_beat_linger_turns,
    build_scene_escalation_and_consequence_directives,
)
from game_engine.turn.generation import _fast_path_classify_ambient_action


class TestSchemaFirstIntentAndEntities(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. SCHEMA VALIDATION
    # -------------------------------------------------------------------------
    def test_schema_validation(self):
        """Validates that models serialize and validate structured intent and entity enums."""
        # Choice model
        c = Choice(
            label="Step outside into the garden",
            intent="movement",
            sub_intent="explore",
            target_npc="Maya",
            stat="NONE",
            requirement=0,
        )
        self.assertEqual(c.intent, "movement")
        self.assertEqual(c.sub_intent, "explore")
        self.assertEqual(c.target_npc, "Maya")

        # Invalid intent cleanly coerces to general_action
        c_bad = Choice(label="Invalid", intent="nonexistent_alien_intent")
        self.assertEqual(c_bad.intent, "general_action")

        # ActionClassification model
        ac = ActionClassification(
            intent="dialogue_exit",
            target_npc="Alice",
            confidence=0.98,
        )
        self.assertEqual(ac.intent, "dialogue_exit")

        # TrackerEntity model
        te = TrackerEntity(
            name="Chloe",
            species="cat",
            social_role_type="classmate",
        )
        self.assertEqual(te.species, "cat")
        self.assertEqual(te.social_role_type, "student_peer")

        # JSON schema prompt strings contain new properties
        self.assertIn('"intent"', SCENE_SCHEMA)
        self.assertIn('"sub_intent"', SCENE_SCHEMA)
        self.assertIn('"target_npc"', SCENE_SCHEMA)

        # RelationshipUpdate model
        ru = RelationshipUpdate(
            npc_name="Maya",
            delta_score=2,
            interaction_tone="warm",
            trait_alignment="resonated",
        )
        self.assertEqual(ru.interaction_tone, "warm")
        self.assertEqual(ru.trait_alignment, "resonated")

        self.assertIn('"interaction_tone"', RELATIONSHIP_UPDATE_FIELD)
        self.assertIn('"trait_alignment"', RELATIONSHIP_UPDATE_FIELD)
        self.assertIn('"interaction_tone"', SOCIAL_ARBITER_SCHEMA)
        self.assertIn('"trait_alignment"', SOCIAL_ARBITER_SCHEMA)

        self.assertIn('"intent"', CLASSIFY_SCHEMA)
        self.assertIn('"sub_intent"', CLASSIFY_SCHEMA)
        self.assertIn('"target_npc"', CLASSIFY_SCHEMA)

    # -------------------------------------------------------------------------
    # 2. TAGGED INTENT RESOLUTION
    # -------------------------------------------------------------------------
    def test_resolve_action_intent_tagged(self):
        """Tagged choice resolves directly to enum without relying on regex guessing."""
        tagged_choice = {
            "label": "Bid farewell and depart gracefully",
            "intent": "dialogue_exit",
            "target_npc": "Lady Alice",
        }
        res = resolve_action_intent(tagged_choice)
        self.assertEqual(res.category, IntentCategory.DIALOGUE_EXIT)
        self.assertEqual(res.target_entity, "Lady Alice")

        # Tag overrides ambiguous words in label
        tricky_choice = {
            "label": "Travel to the market stall and recruit companions",
            "intent": "merchant_trade",
            "target_npc": "Boran",
        }
        res_tricky = resolve_action_intent(tricky_choice)
        self.assertEqual(res_tricky.category, IntentCategory.MERCHANT_TRADE)
        self.assertEqual(res_tricky.target_entity, "Boran")

    # -------------------------------------------------------------------------
    # 3. SUB-INTENT DISAMBIGUATION
    # -------------------------------------------------------------------------
    def test_resolve_action_intent_unambiguous_sub_intent(self):
        """Tagged choice preserves sub_intent for intimate and social mechanics."""
        intimate_choice = {
            "label": "Embrace her passionately and make love",
            "intent": "intimate_act",
            "sub_intent": "intercourse",
            "target_npc": "Maya Anderson",
        }
        res = resolve_action_intent(intimate_choice)
        self.assertEqual(res.category, IntentCategory.INTIMATE_ACT)
        self.assertEqual(res.sub_target, "intercourse")
        self.assertEqual(res.metadata.get("sub_intent"), "intercourse")
        self.assertEqual(res.target_entity, "Maya Anderson")

    # -------------------------------------------------------------------------
    # 4. LEGACY FALLBACK RESOLUTION
    # -------------------------------------------------------------------------
    def test_resolve_action_intent_legacy_fallback(self):
        """Untagged string or general_action dict falls back to classify_action_intent."""
        raw_text = "Confess your romantic feelings and ask her out"
        res_str = resolve_action_intent(raw_text)
        self.assertEqual(res_str.category, IntentCategory.ROMANTIC_CONFESSION)

        general_choice = {
            "label": "Confess your romantic feelings and ask her out",
            "intent": "general_action",
        }
        res_dict = resolve_action_intent(general_choice)
        self.assertEqual(res_dict.category, IntentCategory.ROMANTIC_CONFESSION)

    # -------------------------------------------------------------------------
    # 5. CUSTOM ACTION FAST-PATH
    # -------------------------------------------------------------------------
    def test_custom_action_fast_path(self):
        """Fast-path handles short, unambiguous ambient commands; rejects complex/negated ones."""
        # Simple ambient commands fast-path successfully
        goodbye_res = _fast_path_classify_ambient_action("say goodbye")
        self.assertIsNotNone(goodbye_res)
        self.assertEqual(goodbye_res["intent"], "dialogue_exit")

        move_res = _fast_path_classify_ambient_action("leave the room")
        self.assertIsNotNone(move_res)
        self.assertEqual(move_res["intent"], "movement")

        go_res = _fast_path_classify_ambient_action("go to library")
        self.assertIsNotNone(go_res)
        self.assertEqual(go_res["intent"], "movement")

        sleep_res = _fast_path_classify_ambient_action("sleep until morning")
        self.assertIsNotNone(sleep_res)
        self.assertEqual(sleep_res["intent"], "rest_sleep")

        photo_res = _fast_path_classify_ambient_action("take a photo")
        self.assertIsNotNone(photo_res)
        self.assertEqual(photo_res["intent"], "media_capture")

        # Complex, negated, or multi-clause commands do NOT fast-path
        negated_res = _fast_path_classify_ambient_action("leave the room but don't say goodbye")
        self.assertIsNone(negated_res)

        long_res = _fast_path_classify_ambient_action("carefully negotiate the price without angering her in front of the others")
        self.assertIsNone(long_res)

        social_res = _fast_path_classify_ambient_action("ask Maya why she is upset")
        self.assertIsNone(social_res)

    # -------------------------------------------------------------------------
    # 6. ENTITY SPECIES & SOCIAL ROLE ISOLATION
    # -------------------------------------------------------------------------
    def test_entity_species_and_social_role_isolation(self):
        """Prevents cross-species feature bleed and Scunthorpe contact disqualifications."""
        # Beastfolk species isolation
        cat_key = get_species_key_from_race("beastfolk:cat")
        self.assertEqual(cat_key, "cat")
        cat_tmpl = SPECIES_TEMPLATES["cat"]
        # All cat features must be feline, never mouse
        for feat in cat_tmpl.get("beastfolk_features", []):
            self.assertNotIn("round mouse ears", feat.lower())
            self.assertNotIn("mouse", feat.lower())
        for feat in cat_tmpl.get("hybrid_features", []):
            self.assertNotIn("round mouse ears", feat.lower())
            self.assertNotIn("mouse", feat.lower())

        # Contact eligibility: Priority 1 (family_relative enum)
        rel_npc = {"name": "Aunt Sarah", "social_role_type": "family_relative", "role": "Aunt"}
        self.assertFalse(is_contact_eligible(rel_npc, scenario="high_school_drama", social_role_type="family_relative"))

        parent_npc = {"name": "Mother", "social_role_type": "parent", "role": "Mom"}
        self.assertFalse(is_contact_eligible(parent_npc, scenario="high_school_drama", social_role_type="parent"))

        # Contact eligibility: Priority 2 (backstory mentioning 'mom' must NOT disqualify a classmate/friend)
        classmate_npc = {
            "name": "Evelyn Reed",
            "social_role_type": "classmate",
            "role": "Classmate",
            "notes": "She is an orphan who lost her mom in a storm.",
            "background": "Living alone since her mom passed away.",
        }
        self.assertTrue(is_contact_eligible(classmate_npc, scenario="high_school_drama", social_role_type="classmate"),
                        "Classmate was wrongly disqualified due to 'mom' in backstory!")

        # Contact eligibility: Scunthorpe substring protection (e.g. 'demon' contains 'mo' not 'mom', but test boundary)
        demon_npc = {"name": "Malakor", "role": "Demon Summoner", "social_role_type": "neutral"}
        self.assertTrue(is_contact_eligible(demon_npc, scenario="fantasy"))

    # -------------------------------------------------------------------------
    # 7. CHOICES CLEANER STEP-1 & SCUNTHORPE FIXES
    # -------------------------------------------------------------------------
    def test_choices_cleaner_no_substring_false_positives(self):
        """Ensures choices cleaner uses intent first and does not delete club recruit or Ray/Pray."""
        # 1. Ambient exploration mode (no dialogue partner)
        ambient_choices = [
            # School club recruitment choice: MUST NOT BE PRUNED in non-combat mode
            {
                "label": "Recruit members for the literature club at the courtyard",
                "intent": "general_action",
                "stat": "CHA",
                "requirement": 5,
            },
            # Tactical party recruit choice in non-combat mode: SHOULD BE PRUNED
            {
                "label": "Invite Boran to join your combat party permanently",
                "intent": "party_recruit",
                "stat": "CHA",
                "requirement": 7,
            },
            {
                "label": "Inspect the bookshelf in the library",
                "intent": "general_action",
                "stat": "INT",
                "requirement": 5,
            }
        ]
        cleaned_ambient = clean_choices_impl(
            None,
            choices=ambient_choices,
            scenario="high_school_drama",
            dialogue_partner=None,
        )
        labels_ambient = [c["label"] for c in cleaned_ambient]
        self.assertTrue(any("literature club" in l for l in labels_ambient), "Literature club recruitment was wrongly deleted in non-combat mode!")
        self.assertFalse(any("combat party permanently" in l for l in labels_ambient), "Tactical party recruit was not filtered in non-combat mode!")

        # 2. Dialogue mode with partner 'Ray'
        dialogue_choices = [
            # Dialogue choice with bystander name substring 'Ray' inside 'Pray': MUST NOT BE PRUNED
            {
                "label": "Pray silently at the altar before speaking with Ray",
                "intent": "general_action",
                "target_npc": "Ray",
                "stat": "NONE",
                "requirement": 0,
            },
            # Standard dialogue exit choice
            {
                "label": "Thank Ray and step outside into the hall",
                "intent": "dialogue_exit",
                "target_npc": "Ray",
                "stat": "NONE",
                "requirement": 0,
            }
        ]
        cleaned_dialogue = clean_choices_impl(
            None,
            choices=dialogue_choices,
            scenario="high_school_drama",
            dialogue_partner="Ray",
            current_npcs=[{"name": "Ray"}, {"name": "Rachel"}, {"name": "Maya"}],
        )
        labels_dialogue = [c["label"] for c in cleaned_dialogue]
        self.assertTrue(any("Pray silently" in l for l in labels_dialogue), "'Pray' was wrongly pruned due to 'Ray' token collision!")

    # -------------------------------------------------------------------------
    # 8. AFFINITY ENGINE STRUCTURED TONE & DIALOGUE TRACKING ESCALATION
    # -------------------------------------------------------------------------
    def test_affinity_engine_structured_tone_and_traits(self):
        """Tests that affinity engine respects interaction_tone, trait_alignment, and boundary guards."""
        # 1. Structured Tone
        hostile_act = {
            "label": "Look at him carefully",
            "interaction_tone": "hostile",
            "stat": "NONE",
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action=hostile_act,
            npc_name="Boran",
            contact_data={},
            is_target_npc=True,
        )
        self.assertEqual(delta, -2)
        self.assertTrue(any("Hostile" in r for r in reasons))

        warm_act = {
            "label": "Look at him carefully",
            "interaction_tone": "warm",
            "stat": "NONE",
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action=warm_act,
            npc_name="Boran",
            contact_data={},
            is_target_npc=True,
        )
        self.assertEqual(delta, 1)
        self.assertTrue(any("Warm" in r for r in reasons))

        neutral_act = {
            "label": "Look at him carefully",
            "interaction_tone": "neutral",
            "stat": "NONE",
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action=neutral_act,
            npc_name="Boran",
            contact_data={},
            is_target_npc=True,
        )
        self.assertEqual(delta, 0)

        # 2. Structured Trait Alignment
        res_act = {
            "label": "Discuss local history",
            "interaction_tone": "neutral",
            "trait_alignment": "resonated",
            "stat": "NONE",
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action=res_act,
            npc_name="Boran",
            contact_data={"traits": ["scholarly"]},
            is_target_npc=True,
        )
        self.assertGreaterEqual(delta, 1)
        self.assertTrue(any("resonance" in r.lower() for r in reasons))

    def test_dialogue_tracking_escalation_clean(self):
        """Ensures dialogue tracking escalation inspects only narrative and avoids dict key contamination."""
        # Contaminated history: dict has key 'is_guarded', role 'guard', etc., but peaceful narrative
        contaminated_history = [
            {
                "type": "turn",
                "label": "Read the ancient tome",
                "is_guarded": True,
                "role": "guard",
                "timer": 60,
                "outcome_narrative": "They sit quietly by the fire, reading without interruption.",
            },
            {
                "type": "turn",
                "label": "Drink some hot tea",
                "is_guarded": True,
                "role": "guard",
                "outcome_narrative": "The tea warms their throat. The library remains peaceful.",
            }
        ]
        session = {"scenario": "fantasy", "history": contaminated_history}
        directives = build_scene_escalation_and_consequence_directives(session, [], [])
        # MUST NOT contain mandatory escalation directive
        self.assertNotIn("MANDATORY SCENE ESCALATION", directives,
                         "False positive escalation triggered by dict keys ('guard', 'timer')!")

        # Genuine crisis history: actual narrative mentions door breach/hammering
        crisis_history = [
            {
                "type": "turn",
                "label": "Hold the door",
                "outcome_narrative": "Heavy thuds shake the corridor as enemies are hammering on the reinforced barricade.",
            },
            {
                "type": "turn",
                "label": "Brace the wood",
                "outcome_narrative": "Splinters fly from the door. Hostile standoff reaches critical mass seconds away from breaching.",
            }
        ]
        session_crisis = {"scenario": "fantasy", "history": crisis_history}
        directives_crisis = build_scene_escalation_and_consequence_directives(session_crisis, [], [])
        self.assertIn("MANDATORY SCENE ESCALATION", directives_crisis,
                      "Genuine crisis narrative failed to trigger escalation directive!")

    def test_dialogue_tracking_linger_exit_intent(self):
        """Ensures compute_scene_beat_linger_turns recognizes intent='dialogue_exit' immediately."""
        history = [
            {"type": "turn", "label": "Talk about politics", "outcome_narrative": "They discuss.", "witnessed_by": ["Maya"]},
            {"type": "turn", "label": "Discuss strategy", "outcome_narrative": "They plan.", "witnessed_by": ["Maya"]},
            {"type": "turn", "label": "Depart the pavilion", "intent": "dialogue_exit", "target_npc": "Maya"},
        ]
        session = {"history": history, "current_location": ""}
        linger = compute_scene_beat_linger_turns(session, ["Maya"])
        # Because the latest turn has intent='dialogue_exit', linger turns should break immediately (0)
        self.assertEqual(linger, 0)


if __name__ == "__main__":
    unittest.main()
