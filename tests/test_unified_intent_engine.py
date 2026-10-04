import unittest
import asyncio
from mechanics.narrative.intent import (
    IntentCategory,
    IntentContext,
    ActionIntent,
    classify_action_intent,
    is_romantic_confession_intent,
    is_dialogue_initiation,
    is_conversational_exit,
    is_sleep_action,
    is_board_inspection_action,
    is_companion_recruitment_action,
    is_affection_action,
    is_gift_offer_action,
    is_social_invite_action,
    is_scout_action,
    is_investigate_action,
    is_stealth_action,
    is_phone_comm_action,
    is_merchant_action,
    is_free_ambient_action,
)


class TestUnifiedIntentEngine(unittest.TestCase):
    def setUp(self):
        self.context = IntentContext(
            dialogue_partner="Maya Anderson",
            dialogue_partners=["Maya Anderson"],
            current_zone="Sakura Hill Residential Town",
            present_npcs=["Maya Anderson", "Sofia Anderson", "Mr. Harrison"],
            scenario="high_school_drama"
        )

    def test_category_1_romantic_confession_positive_and_negative(self):
        """Test Category 1: Romance initiation and negative disambiguation guards."""
        positives = [
            "Ask her if she would like to pursue a relationship with you",
            "Confess your feelings and ask her to be your girlfriend",
            "Tell her you want to take things to the next level",
            "Ask if she wants to start dating officially",
            "Ask her to be more than friends",
            "Confess your love to her under the cherry blossoms",
            "Admit your romantic feelings for her",
            "Ask if she wants to become romantically involved",
        ]
        for text in positives:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.ROMANTIC_CONFESSION, f"Failed on positive: {text}")
            self.assertEqual(intent.target_entity, "Maya Anderson")
            self.assertTrue(is_romantic_confession_intent(text))

        negatives = [
            "Maintain a strictly professional and working relationship with the client",
            "Ask about her relationship with the student council president",
            "We have a strong platonic relationship as study buddies",
            "I don't want to pursue a relationship right now",
            "Refuse to date or enter a relationship with him",
            "Investigate rumors about their relationship",
        ]
        for text in negatives:
            intent = classify_action_intent(text, self.context)
            self.assertNotEqual(intent.category, IntentCategory.ROMANTIC_CONFESSION, f"False positive on: {text}")
            self.assertFalse(is_romantic_confession_intent(text))

    def test_category_2_intimate_and_sensual_milestones(self):
        """Test Category 2: Physical intimacy, kisses, oral give/receive, and intercourse."""
        # Kisses
        kisses = [
            "Lean in and share a tender kiss with Maya",
            "Pull her into a passionate kiss",
            "Kiss her deeply under the stars"
        ]
        for text in kisses:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.INTIMATE_ACT)
            self.assertEqual(intent.sub_target, "kiss")
            self.assertEqual(intent.target_entity, "Maya Anderson")

        # Intercourse
        intercourse = [
            "Make passionate love to Maya on the bed",
            "Slide inside her warmth as you hold her close",
            "Have intimate intercourse with her"
        ]
        for text in intercourse:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.INTIMATE_ACT)
            self.assertEqual(intent.sub_target, "intercourse")

        # Oral receive
        oral_rec = [
            "Go down on Maya and lick her center softly",
            "Taste her folds and bring her over the edge"
        ]
        for text in oral_rec:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.INTIMATE_ACT)
            self.assertEqual(intent.sub_target, "oral_receive")

        # Oral give
        oral_give = [
            "Let Maya give you a slow blowjob until release",
            "Suck his shaft deeply"
        ]
        for text in oral_give:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.INTIMATE_ACT)
            self.assertEqual(intent.sub_target, "oral_give")

    def test_category_3_disclosure_and_observation(self):
        """Test Category 3: Prying into intimate profiles, mannerisms, and turn-ons."""
        samples = [
            ("Ask Maya about her sensitive spots and tickle zones", "sensitive_spots"),
            ("Inquire about what turns her on when alone", "turn_ons"),
            ("Ask if she has any secret fetishes or bedroom fantasies", "fetishes"),
            ("Ask about her past partners and intercourse_experience", "intercourse_experience"),
            ("Study her subtle mannerisms and body language closely", "mannerisms"),
        ]
        for text, expected_sub in samples:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.DISCLOSURE_INQUIRY, f"Failed on: {text}")
            self.assertEqual(intent.sub_target, expected_sub)

    def test_category_4_dialogue_locks_and_exits(self):
        """Test Category 4: Conversational exits and dialogue initiation."""
        exits = [
            "Thank Maya, say goodbye, and head back to class",
            "Take your leave and excuse yourself politely",
            "Part ways with Maya and return to what you were doing"
        ]
        for text in exits:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.DIALOGUE_EXIT)
            self.assertTrue(is_conversational_exit(text))

        inits = [
            "Speak with Sofia Anderson about the student council",
            "Talk to Mr. Harrison regarding the biology test",
            "Converse with the local librarian"
        ]
        for text in inits:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.DIALOGUE_INIT)
            self.assertTrue(is_dialogue_initiation(text))

    def test_category_5_spatial_movement_and_residences(self):
        """Test Category 5: Movement, cross-zone travel, hallway traversal, and residence visits."""
        # Residence visits
        res_actions = [
            "Hold Maya's hand and head to her home together",
            "Walk to Maya's house after school",
            "Enter Anderson's residence foyer"
        ]
        for text in res_actions:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.MOVEMENT)
            self.assertEqual(intent.sub_target, "residence")
            self.assertTrue(intent.metadata.get("is_residence"))

        # Hallways
        hallway_actions = [
            "Step into the hallway and look around",
            "Walk into the 2nd floor corridor"
        ]
        for text in hallway_actions:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.MOVEMENT)
            self.assertEqual(intent.sub_target, "corridor")

        # General movement
        general_mv = [
            "Travel toward the Komorebi Commercial Strip",
            "Head to the Vintage Bookstore to browse novels"
        ]
        for text in general_mv:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.MOVEMENT)

    def test_category_6_rest_sleep_recruitment_and_boards(self):
        """Test Categories 6, 7, 8: Rest/Sleep, Party Recruitment, and Notice Boards."""
        # Sleep
        sleep_texts = [
            "Head to bed and sleep until morning",
            "Go to sleep for the night"
        ]
        for text in sleep_texts:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.REST_SLEEP)
            self.assertEqual(intent.sub_target, "sleep")
            self.assertTrue(is_sleep_action(text))

        # Rest
        rest_texts = [
            "Take a breather on the park bench",
            "Sit down, relax at the café, and rest"
        ]
        for text in rest_texts:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.REST_SLEEP)
            self.assertEqual(intent.sub_target, "rest")

        # Party recruit
        recruit_texts = [
            "Invite Maya to join your party as a permanent companion",
            "Ask the knight to join our party"
        ]
        for text in recruit_texts:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.PARTY_RECRUIT)
            self.assertTrue(is_companion_recruitment_action(text))

        # Notice board
        board_texts = [
            "Inspect the campus bulletin board for new announcements",
            "Check the guild notice board for active bounties"
        ]
        for text in board_texts:
            intent = classify_action_intent(text, self.context)
            self.assertEqual(intent.category, IntentCategory.INSPECT_BOARD)
            self.assertTrue(is_board_inspection_action(text))

    def test_priority_hierarchy_for_composite_actions(self):
        """Verify strict priority ordering when actions contain multiple keywords."""
        # Romance over Movement: "Walk with Maya to her house to confess your feelings"
        text = "Walk with Maya to her house and confess your feelings to pursue a relationship"
        intent = classify_action_intent(text, self.context)
        self.assertEqual(intent.category, IntentCategory.ROMANTIC_CONFESSION)

        # Intimacy over Movement: "Step into the bedroom and make passionate love"
        text2 = "Step into the bedroom and make passionate love with Maya"
        intent2 = classify_action_intent(text2, self.context)
        self.assertEqual(intent2.category, IntentCategory.INTIMATE_ACT)

        # Exit over Movement: "Say goodbye to Maya and walk out to the street"
        text3 = "Say goodbye to Maya and walk out to the street"
        intent3 = classify_action_intent(text3, self.context)
        self.assertEqual(intent3.category, IntentCategory.DIALOGUE_EXIT)

    def test_edge_case_and_fallback_resilience(self):
        """Verify that extreme inputs never crash and fallback gracefully."""
        extreme_inputs = [
            "",
            "   ",
            None,
            "🎉💖✨",
            "SELECT * FROM users WHERE 1=1; DROP TABLE sessions;",
            "<script>alert('xss')</script>",
            "A" * 5000,
            "12345 67890 !@#$%^&*()_+"
        ]
        for raw in extreme_inputs:
            intent = classify_action_intent(raw)
            self.assertIsInstance(intent, ActionIntent)
            self.assertEqual(intent.category, IntentCategory.GENERAL_ACTION)

    def test_accompanied_movement_and_room_exit(self):
        """Verify accompanied movement and room exit intents."""
        acc_text = "Follow Rachel out of the office to her favorite quiet spot"
        intent = classify_action_intent(acc_text, self.context)
        self.assertEqual(intent.category, IntentCategory.MOVEMENT)
        self.assertTrue(intent.metadata.get("is_accompanied"))
        self.assertTrue(intent.metadata.get("is_room_exit"))
        self.assertEqual(intent.target_entity, "Rachel")

        exit_text = "Step out of the office to get some fresh air"
        intent2 = classify_action_intent(exit_text, self.context)
        self.assertEqual(intent2.category, IntentCategory.MOVEMENT)
        self.assertTrue(intent2.metadata.get("is_room_exit"))

        terrace_text = "Step out onto the terrace overlooking the gardens"
        intent3 = classify_action_intent(terrace_text, self.context)
        self.assertEqual(intent3.category, IntentCategory.MOVEMENT)
        self.assertTrue(intent3.metadata.get("is_room_exit"))
        self.assertEqual(intent3.metadata.get("target_archetype"), "exterior")

    def test_category_affection_touch(self):
        """Test physical affection, handholding, hugs, cuddles, and hair stroking."""
        handholds = [
            "Gently hold Maya's hand under the cherry tree",
            "Take her hand and intertwine your fingers",
            "Hold hands with Maya"
        ]
        for t in handholds:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.AFFECTION_TOUCH, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, "handhold")
            self.assertEqual(intent.target_entity, "Maya Anderson")
            self.assertTrue(is_affection_action(t))

        hugs = [
            "Pull Maya into a warm embrace",
            "Wrap your arms around Maya in a comforting hug"
        ]
        for t in hugs:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.AFFECTION_TOUCH, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, "hug")

        cuddles = [
            "Cuddle beside Maya on the sofa",
            "Rest your head on her shoulder and relax"
        ]
        for t in cuddles:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.AFFECTION_TOUCH, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, "cuddle")

        caresses = [
            "Tenderly stroke Maya's hair",
            "Gently caress her cheek"
        ]
        for t in caresses:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.AFFECTION_TOUCH, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, "caress")

        # Disambiguation: Kissing goes to INTIMATE_ACT
        kiss_text = "Kiss Maya tenderly and hold her hand"
        self.assertEqual(classify_action_intent(kiss_text, self.context).category, IntentCategory.INTIMATE_ACT)

        # Disambiguation: Negation/hostile
        hostile_text = "Choke the guard and grab him by the throat"
        self.assertNotEqual(classify_action_intent(hostile_text, self.context).category, IntentCategory.AFFECTION_TOUCH)

    def test_category_gift_offer(self):
        """Test gifting and item offering."""
        gifts = [
            ("Give the silver pendant to Maya as a gift", "Silver Pendant"),
            ("Offer some hot tea to Maya", "Tea"),
            ("Present a bouquet of flowers to Maya", "Flowers"),
        ]
        for t, expected_item in gifts:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.GIFT_OFFER, f"Failed on: {t}")
            self.assertEqual(intent.target_entity, "Maya Anderson")
            self.assertTrue(is_gift_offer_action(t))

        # Disambiguation: "give up"
        self.assertFalse(is_gift_offer_action("Never give up on your training"))

    def test_category_phone_comm(self):
        """Test smartphone and cyberdeck remote communication."""
        texts = [
            ("Text Maya about the homework assignment", "Maya", "sms_text"),
            ("Call Maya on the phone", "Maya", "voice_call"),
            ("Scroll through the PeerPulse gossip feed", "Peerpulse", "feed_browse"),
            ("Check the NetWire feed for city news", "Netwire", "feed_browse"),
        ]
        for t, exp_target, exp_sub in texts:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.PHONE_COMM, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, exp_sub)
            self.assertTrue(is_phone_comm_action(t))

        # Disambiguation: "call for help"
        self.assertFalse(is_phone_comm_action("Call for help in the dark"))

    def test_category_social_invite(self):
        """Test casual hangout, study, and social invitations."""
        invites = [
            ("Ask Maya to walk home together after class", "walk_home"),
            ("Invite Maya to study together at the library", "study"),
            ("Ask Maya out on a casual date", "date"),
            ("Grab lunch with Maya at the courtyard", "lunch"),
            ("Hang out with Maya after school", "hangout")
        ]
        for t, exp_sub in invites:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.SOCIAL_INVITE, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, exp_sub)
            self.assertEqual(intent.target_entity, "Maya Anderson")
            self.assertTrue(is_social_invite_action(t))

    def test_category_area_scout(self):
        """Test environmental scouting and surroundings survey."""
        scouts = [
            "Scout the area around the campus gates",
            "Survey the surroundings carefully",
            "Look around the empty classroom layout",
            "Check the perimeter of the courtyard"
        ]
        for t in scouts:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.AREA_SCOUT, f"Failed on: {t}")
            self.assertTrue(is_scout_action(t))

        # Disambiguation: Hacking / lockpicking
        self.assertFalse(is_scout_action("Hack the security terminal and scout inside"))

    def test_category_investigate_clue(self):
        """Test clue, document, and crime scene investigation."""
        clues = [
            ("Examine the strange occult chalk marks on the blackboard", "Chalk Marks"),
            ("Search the desk drawers for hidden documents", "Drawer"),
            ("Inspect the crime scene for footprints", "Footprints"),
            ("Search for clues near the broken window", "Clues")
        ]
        for t, exp_target in clues:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.INVESTIGATE_CLUE, f"Failed on: {t}")
            self.assertTrue(is_investigate_action(t))

    def test_category_stealth_covert(self):
        """Test stealth, lockpicking, and pickpocketing."""
        stealth_actions = [
            ("Pick the lock on the chemistry lab door", "lockpick"),
            ("Pickpocket the guard's keycard", "pickpocket"),
            ("Sneak past the hallway monitors into the library", "sneak"),
            ("Sneak into the principal's office", "sneak")
        ]
        for t, exp_sub in stealth_actions:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.STEALTH_COVERT, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, exp_sub)
            self.assertTrue(is_stealth_action(t))
            self.assertTrue(intent.metadata.get("is_stealth"))

    def test_category_merchant_trade(self):
        """Test merchant browsing, buying, and selling."""
        trades = [
            ("Browse the shopkeeper's wares", "browse"),
            ("Buy potions from the store counter", "buy"),
            ("Sell old equipment to the merchant", "sell")
        ]
        for t, exp_sub in trades:
            intent = classify_action_intent(t, self.context)
            self.assertEqual(intent.category, IntentCategory.MERCHANT_TRADE, f"Failed on: {t}")
            self.assertEqual(intent.sub_target, exp_sub)
            self.assertTrue(is_merchant_action(t))

    def test_is_free_ambient_action(self):
        """Verify is_free_ambient_action helper correctly distinguishes zero-cost actions."""
        free_phrases = [
            "Speak with Sofia Anderson",
            "Say goodbye and head back to class",
            "Inspect the campus bulletin board",
            "Scout the area around the fountain",
            "Head to bed and sleep until morning",
            "Check the PeerPulse gossip feed",
            "Walk to the Vintage Bookstore",
        ]
        for t in free_phrases:
            intent = classify_action_intent(t, self.context)
            self.assertTrue(is_free_ambient_action(intent), f"Expected free ambient action for: '{t}', got {intent.category}")

        cost_phrases = [
            "Pick the lock on the laboratory door",
            "Confess your romantic feelings to Maya",
            "Invite Maya to join our tactical combat party",
            "Examine the crime scene for occult clues",
            "Make passionate love on the bed"
        ]
        for t in cost_phrases:
            intent = classify_action_intent(t, self.context)
            self.assertFalse(is_free_ambient_action(intent), f"Expected check/cost action for: '{t}', got {intent.category}")

    def test_classify_custom_action_fast_path(self):
        """Verify classify_custom_action fast-paths without needing an LLM call."""
        import game_engine
        session = {
            "id": 1,
            "scenario": "high_school_drama",
            "current_location": "Sakura Hill",
            "current_npcs": [{"name": "Maya Anderson"}],
            "dialogue_partner": "Maya Anderson",
            "history": []
        }
        char = {"name": "Alex", "mp": 10}
        inventory = []

        # Ambient movement
        res1 = asyncio.run(game_engine.classify_custom_action(session, char, inventory, "Walk to the library"))
        self.assertTrue(res1.get("fast_path"))
        self.assertEqual(res1["stat"], "NONE")
        self.assertEqual(res1["requirement"], 0)

        # Ambient exit
        res2 = asyncio.run(game_engine.classify_custom_action(session, char, inventory, "Say goodbye and leave"))
        self.assertTrue(res2.get("fast_path"))
        self.assertEqual(res2["stat"], "NONE")

        # Affection touch
        res3 = asyncio.run(game_engine.classify_custom_action(session, char, inventory, "Gently hold Maya's hand"))
        self.assertTrue(res3.get("fast_path"))
        self.assertEqual(res3["stat"], "CHA")
        self.assertEqual(res3["target_npc"], "Maya Anderson")

        # Lockpicking / stealth
        res4 = asyncio.run(game_engine.classify_custom_action(session, char, inventory, "Pick the lock on the office"))
        self.assertTrue(res4.get("fast_path"))
        self.assertEqual(res4["stat"], "INT")


if __name__ == "__main__":
    unittest.main()

