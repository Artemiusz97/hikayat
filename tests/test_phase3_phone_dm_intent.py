import unittest
from mechanics.narrative.intent import classify_message_intent
from mechanics.system.phone.messaging import detect_custom_message_intent


class TestPhase3PhoneDMIntent(unittest.TestCase):
    """Verifies Phase 3 Phone DM Intent Alignment and central vocabulary integration."""

    def test_photo_and_video_classification(self):
        """Verify normal and intimate photo/video requests are accurately distinguished."""
        # Photos
        self.assertEqual(classify_message_intent("can you send a quick selfie?"), "photo")
        self.assertEqual(classify_message_intent("send a picture of the courtyard"), "photo")
        self.assertEqual(classify_message_intent("what do you look like today?"), "photo")

        # NSFW Photos
        self.assertEqual(classify_message_intent("send nudes"), "nsfw_photo")
        self.assertEqual(classify_message_intent("can you send a spicy selfie?"), "nsfw_photo")
        self.assertEqual(classify_message_intent("wear some lingerie and send a pic"), "nsfw_photo")
        self.assertEqual(classify_message_intent("send a photo in your bikini"), "nsfw_photo")

        # Videos
        self.assertEqual(classify_message_intent("send a video clip of your rehearsal"), "video")
        self.assertEqual(classify_message_intent("record a short vid of the scenery"), "video")

        # NSFW Videos
        self.assertEqual(classify_message_intent("send an intimate video just for me"), "nsfw_video")
        self.assertEqual(classify_message_intent("record a spicy clip in bed"), "nsfw_video")

    def test_meetup_invitation_patterns(self):
        """Verify explicit meetup/date invitations are classified as meetup."""
        meetup_cases = [
            "want to meet up for coffee later?",
            "are you free right now? want to meet up?",
            "let's hang out after school",
            "can we meet at the park?",
            "wanna grab lunch together?",
            "would you like to go on a date with me?",
            "meet me near the clock tower tonight",
            "are you free today?",
        ]
        for msg in meetup_cases:
            self.assertEqual(classify_message_intent(msg), "meetup", f"Failed on: {msg}")

    def test_conversational_mentions_are_not_meetup(self):
        """Verify passing conversational mentions of hanging out/coffee are treated as custom text."""
        custom_cases = [
            "do you think she'll be mad if i hang out with you?",
            "i had fun when we hung out",
            "i was just drinking coffee with Sofia",
            "hello how are you doing today",
            "thanks for helping me earlier",
        ]
        for msg in custom_cases:
            self.assertEqual(classify_message_intent(msg), "custom", f"Failed on: {msg}")

    def test_intel_and_rumor_classification(self):
        """Verify rumor inquiries are classified as intel_rumor."""
        self.assertEqual(classify_message_intent("heard any interesting rumors?"), "intel_rumor")
        self.assertEqual(classify_message_intent("any gossip from the council?"), "intel_rumor")
        self.assertEqual(classify_message_intent("what's going on around the docks?"), "intel_rumor")

    def test_messaging_delegation_matches_intent_engine(self):
        """Verify detect_custom_message_intent in messaging.py behaves identically to classify_message_intent."""
        samples = [
            "send a spicy pic",
            "want to meet up?",
            "heard any rumors?",
            "just saying hi!",
            "",
            None
        ]
        for s in samples:
            self.assertEqual(detect_custom_message_intent(s), classify_message_intent(s))


if __name__ == "__main__":
    unittest.main()
