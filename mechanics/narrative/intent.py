from __future__ import annotations
"""
Unified Action Intent Engine for Hikayat.

Centralizes all linguistic parsing, regex pattern matching, negative disambiguation guards,
and structured intent classification across spatial movement, social meetups, romance milestones,
intimacy, disclosure, dialogue locks, party recruitment, rest, and notice boards.

Pure functional design: Zero database connections, zero cog dependencies, fail-safe fallbacks.
"""
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Set

logger = logging.getLogger("hikayat.mechanics.narrative.intent")


# ==============================================================================
# 1. INTENT CATEGORIES & DATA SCHEMAS
# ==============================================================================

class IntentCategory(str, Enum):
    ROMANTIC_CONFESSION = "romantic_confession"    # Relationship proposals, confessing feelings, dating
    INTIMATE_ACT = "intimate_act"                  # Kisses, sensual intimacy, oral sex, intercourse
    AFFECTION_TOUCH = "affection_touch"            # Handholding, hugs, cuddles, hair stroking, caresses
    DISCLOSURE_INQUIRY = "disclosure_inquiry"      # Prying into sensitive spots, mannerisms, secrets
    GIFT_OFFER = "gift_offer"                      # Giving or offering items/gifts to NPCs
    MEDIA_CAPTURE = "media_capture"                # Taking photos, selfies, or recording video on smartphone
    PHONE_COMM = "phone_comm"                      # Remote calls, texts, DMs, feed browsing on phone
    DIALOGUE_EXIT = "dialogue_exit"                # Saying goodbye, leaving conversation
    SOCIAL_INVITE = "social_invite"                # Inviting NPC to hang out, study, walk home, or casual date
    PARTY_RECRUIT = "party_recruit"                # Inviting NPC to permanent tactical party
    MERCHANT_TRADE = "merchant_trade"              # Browsing, buying, selling at a merchant
    INSPECT_BOARD = "inspect_board"                # Checking bounty/notice boards
    AREA_SCOUT = "area_scout"                      # Surveying surroundings, scouting room layout
    INVESTIGATE_CLUE = "investigate_clue"          # Examining physical evidence, searching desks/drawers
    REST_SLEEP = "rest_sleep"                      # Sleeping until morning, taking breathers
    STEALTH_COVERT = "stealth_covert"              # Sneaking, lockpicking, pickpocketing, infiltration
    MOVEMENT = "movement"                          # Travel between zones, establishments, households
    APPOINTMENT_MEETUP = "appointment_meetup"      # Arriving at a scheduled date/hangout
    DIALOGUE_INIT = "dialogue_init"                # Initiating conversation with an NPC
    GENERAL_ACTION = "general_action"              # Standard skill checks and generic actions


@dataclass
class IntentContext:
    """Lightweight caller context passed into the intent classifier."""
    dialogue_partner: str = ""
    dialogue_partners: List[str] = field(default_factory=list)
    current_zone: str = ""
    current_primary: str = ""
    present_npcs: List[str] = field(default_factory=list)
    known_locations: List[Dict[str, Any]] = field(default_factory=list)
    scenario: str = "default"


@dataclass
class ActionIntent:
    """Structured representation of a classified player or choice action."""
    category: IntentCategory
    target_entity: str = ""      # e.g., "Maya Anderson", "Vintage Bookstore", "Notice Board"
    sub_target: str = ""         # e.g., "Foyer", "sensitive_spots", "Chemistry Assignment"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


# ==============================================================================
# 2. CONSOLIDATED PATTERN MATRICES & DISAMBIGUATION GUARDS
# ==============================================================================

# --- ROMANCE & CONFESSION ---
ROMANTIC_CONFESSION_FRAMES = (
    # Relationship Initiation
    re.compile(r'\b(?:pursue|start|begin|enter|build|want|form)\s+(?:a\s+)?(?:romantic\s+|committed\s+|official\s+)?(?:relationship|future|bond|thing|partnership)\b', re.I),
    # Status Shift / Title
    re.compile(r'\b(?:be|become|make us|ask (?:her|him|them) to be)\s+(?:my|your|his|her|an?\s+)?(?:girlfriend|boyfriend|partner|couple|lovers|more than friends|exclusive|together)\b', re.I),
    # Affection Commitment & Dating
    re.compile(r'\b(?:take\s+(?:our|things|this|us)\s+to\s+the\s+next\s+level|give\s+(?:us|this)\s+a\s+chance|date\s+(?:each other|officially|exclusively|her|him|you|together)|confess\s+(?:my|his|her)?\s*(?:feelings|love|attraction))\b', re.I),
    # Dating Initiation / Official Dating
    re.compile(r'\b(?:start|begin|started|want(?:s)?\s+to\s+start)\s+dating\b', re.I),
    re.compile(r'\b(?:start\s+dating\s+officially|officially\s+start\s+dating|date\s+officially|officially\s+dating|started\s+dating\s+romantically)\b', re.I),
    # Direct confession of romantic love
    re.compile(r'\b(?:confess(?:ed|ing)?\s+(?:her|his|my|your|mutual|their)?\s*(?:romantic\s+)?(?:feelings|love)|admit(?:ted|ting)?\s+(?:her|his|my|your|their)?\s*(?:romantic\s+)?(?:feelings|love)|tell\s+(?:her|him|them|you)\s+(?:how\s+(?:i|he|she)\s+feels?|that\s+(?:i|he|she)\s+love\s+(?:her|him|you)))\b', re.I),
    # Romance agreement / official couple
    re.compile(r'\b(?:agreed\s+to\s+date|became\s+a\s+couple|become\s+romantically\s+involved|romantically\s+involved)\b', re.I),
)

NON_ROMANTIC_QUALIFIER_RE = re.compile(
    r'\b(?:working|business|professional|platonic|family|sibling|mentor|adversarial|strained|hostile|toxic)\s+relationship\b',
    re.I
)
ROMANCE_NEGATION_GUARD_RE = re.compile(
    r'\b(?:not|don\'t|dont|never|cannot|can\'t|cant|refuse\s+to|stop)\s+(?:want|pursue|date|be|start|enter)\b',
    re.I
)
THIRD_PARTY_GOSSIP_RE = re.compile(
    r'\b(?:ask\s+about|inquire\s+about|rumors?\s+about)\s+(?:her|his|their)\s+relationship\b',
    re.I
)

# --- INTIMACY & SENSUAL MILESTONES ---
INTIMATE_INTERCOURSE_RE = re.compile(
    r'\b(?:make\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?love|'
    r'made\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?love|'
    r'making\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?love|'
    r'have\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?(?:sex|intercourse)|'
    r'had\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?(?:sex|intercourse)|'
    r'having\s+(?:passionate\s+|sweet\s+|gentle\s+|rough\s+|intimate\s+)?(?:sex|intercourse)|'
    r'sleep\s+together|slept\s+together|intercourse|sexual\s+intercourse|full\s+intercourse|'
    r'penetrate\s+(?:her|him)|penetrating\s+(?:her|him)|slide\s+(?:(?:your|his|it)\s+)?(?:inside|into)|'
    r'thrust\s+(?:inside|into)|thrusting\s+intimately|ride\s+(?:him|his|her)|straddle\s+and\s+ride|'
    r'take\s+(?:her|his)\s+virginity|took\s+(?:her|his)\s+virginity|lose\s+(?:her|his)\s+virginity|'
    r'lost\s+(?:her|his)\s+virginity|fuck\s+(?:her|him)|breed\s+(?:her|him)|creampie|'
    r'enter\s+(?:her|his)\s+(?:warmth|body|pussy))\b',
    re.I
)

ORAL_RECEIVE_RE = re.compile(
    r'\b(?:eat\s+(?:(?:her|his|their)\s+)?out|eating\s+(?:(?:her|his|their)\s+)?out|'
    r'eats\s+(?:(?:her|his|their)\s+)?out|ate\s+(?:(?:her|his|their)\s+)?out|'
    r'go\s+down\s+on|went\s+down\s+on|going\s+down\s+on|'
    r'taste\s+(?:her|his|their)(?:\s+(?:folds|center|clit|entrance|nectar|body))?|tasting\s+(?:her|his|their)|'
    r'lick\s+(?:her|his|their)\s+(?:center|clit|folds|entrance)|'
    r'licking\s+(?:her|his|their)\s+(?:center|clit|folds|entrance)|'
    r'oral\s+(?:sex\s+)?on\s+(?:her|him|them)|(?:give|giving|gave)\s+head\s+to\s+(?:her|him|them))\b',
    re.I
)

ORAL_GIVE_RE = re.compile(
    r'\b(?:blowjob|blow\s+job|bj|fellatio|take\s+(?:your|his)\s+release|taking\s+(?:your|his)\s+release|'
    r'suck\s+(?:your|his)\s+(?:cock|dick|shaft)|sucking\s+(?:your|his)|mouth\s+suction|'
    r'swallow\s+(?:his|your)\s+release|swallowing\s+(?:his|your))\b',
    re.I
)

KISS_RE = re.compile(
    r'\b(?:kiss|kisses|kissed|kissing|shared\s+a\s+(?:tender|passionate|deep)?\s*kiss|'
    r'pull\s+(?:her|him)\s+into\s+a\s+kiss|pulled\s+(?:her|him)\s+into\s+a\s+kiss|'
    r'kiss\s+(?:her|him)\s+deeply|kissed\s+(?:her|him)\s+deeply)\b',
    re.I
)

# --- INFORMATION DISCLOSURE & OBSERVATION ---
DISCLOSURE_SENSITIVE_SPOTS_RE = re.compile(
    r'\b(?:sensitive\s+spots?|erogenous\s+zones?|touch\s+where|tickle\s+spots?)\b', re.I
)
DISCLOSURE_TURN_ONS_RE = re.compile(
    r'\b(?:turn-?ons?|turns?\s+(?:her|him)\s+on|arousal\s+triggers?)\b', re.I
)
DISCLOSURE_FETISHES_RE = re.compile(
    r'\b(?:fetish(?:es)?|kinks?|bedroom\s+fantas(?:y|ies)|roleplay\s+in\s+bed|bondage)\b', re.I
)
DISCLOSURE_VIRGINITY_RE = re.compile(
    r'\b(?:virgin(?:ity)?|first\s+time|past\s+partners?|done\s+oral|received\s+oral)\b', re.I
)
DISCLOSURE_DEMEANOR_RE = re.compile(
    r'\b(?:bedroom\s+demeanor|intimate\s+demeanor|in\s+private|in\s+bed)\b', re.I
)
DISCLOSURE_MANNERISMS_RE = re.compile(
    r'\b(?:observe\s+(?:expression|body\s+language|habits?)|watch\s+closely|study\s+(?:her|his)\s+expression|'
    r'notice\s+body\s+language|gauge\s+reaction|subtle\s+mannerisms?)\b',
    re.I
)

# --- MEDIA CAPTURE & SMARTPHONE RECORDINGS ---
MEDIA_PHOTO_RE = re.compile(
    r'\b(?:take|snap|capture|shoot|get)\s+(?:a\s+)?(?:[a-zA-Z0-9_\-]+\s+){0,3}(?:photo|picture|pic|selfie|snapshot|polaroid|image)s?\b|'
    r'\b(?:take|snap)\s+(?:a\s+)?(?:[a-zA-Z0-9_\-]+\s+){0,3}selfie\b|'
    r'\b(?:photograph|take\s+photos?\s+of|snap\s+photos?\s+of)\b',
    re.I
)

MEDIA_VIDEO_RE = re.compile(
    r'\b(?:record|film|capture|shoot)\s+(?:a\s+)?(?:[a-zA-Z0-9_\-]+\s+){0,3}(?:video|video\s+clip|footage|recording|clip)s?\b|'
    r'\b(?:take\s+a\s+video|film\s+(?:the|a|her|him|this|them))\b',
    re.I
)

MEDIA_DEVICE_AIM_RE = re.compile(
    r'\b(?:aim|point|hold\s+up|pull\s+out)\s+(?:[a-zA-Z0-9_\-]+\s+){0,3}(?:phone|smartphone|camera|cyberdeck|lens)\b',
    re.I
)

MEDIA_NEGATION_GUARD_RE = re.compile(
    r'\b(?:look\s+at\s+the\s+picture|picture\s+this|snapshot\s+of\s+the\s+economy|shoot\s+an\s+arrow|film\s+review|movie|cinema|theater)\b',
    re.I
)

# Central Media & Phone Messaging Vocabularies
MEDIA_NSFW_KEYWORDS = (
    "spicy", "nsfw", "intimate", "nude", "nudes", "naked", "lewd", "bedroom",
    "undies", "lingerie", "underwear", "boudoir", "bikini", "bra", "panties",
    "shirtless", "topless", "sexy"
)

MEDIA_VIDEO_KEYWORDS = ("video", "vid", "clip", "recording", "footage", "film")

MEDIA_PHOTO_KEYWORDS = (
    "photo", "picture", "pic", "pics", "pictures", "selfie", "selfies",
    "snapshot", "image", "snap", "look like"
)

INTEL_RUMOR_KEYWORDS = (
    "rumor", "rumours", "rumors", "intel", "gossip", "heard anything", "what's going on"
)

PHONE_MEETUP_PATTERNS = (
    re.compile(r"\b(?:want|wanna|wish)\s+to\s+(?:meet|hang\s*out|go\s+out|catch\s*up|grab|get)\b", re.I),
    re.compile(r"\b(?:can|could|should|shall|would)\s+we\s+(?:meet|hang\s*out|go\s+out|catch\s*up|grab|get)\b", re.I),
    re.compile(r"\blet'?s\s+(?:meet|hang\s*out|go\s+out|catch\s*up|grab|get)\b", re.I),
    re.compile(r"\bare\s+you\s+free\b", re.I),
    re.compile(r"\bfree\s+(?:to\s+(?:meet|hang\s*out|talk)|right\s+now|later|today|tonight)\b", re.I),
    re.compile(r"\b(?:grab|get)\s+(?:a\s+)?(?:coffee|lunch|dinner|drinks?)\b", re.I),
    re.compile(r"\b(?:want|wanna|let'?s|can\s+we|would\s+you\s+like\s+to)\s+go\s+on\s+a\s+date\b", re.I),
    re.compile(r"\b(?:go\s+out\s+(?:with\s+me|together)|ask\s+you\s+out)\b", re.I),
    re.compile(r"\bmeet\s*(?:up)?\s+(?:with\s+me|somewhere|at\s+the|in\s+the|near\s+the|later|soon|now|today|tonight)\b", re.I),
    re.compile(r"\bmeet\s+me\b", re.I),
)

# --- DIALOGUE LOCK & EXITS ---
DIALOGUE_EXIT_PHRASES = (
    "say goodbye", "take your leave", "part ways", "excuse your", "excuse yourself",
    "leave the conversation", "end the conversation", "wrap up the chat", "step away",
    "bid farewell", "head back to class", "return to what you were doing",
    "walk away", "exit conversation", "farewell"
)

DIALOGUE_INIT_PREFIXES = (
    "speak with ", "speak to ", "talk to ", "talk with ", "consult the ", "consult with ",
    "address the ", "converse with ", "greet ", "question ", "chat with ",
    "strike up a conversation with ", "approach and speak with ", "approach and talk to "
)

# --- SPATIAL MOVEMENT & RESIDENCES ---
MOVEMENT_PREFIXES = (
    "travel to ", "travel toward ", "travel towards ", "travel through ", "travel into ",
    "head to ", "head toward ", "head towards ", "head into ",
    "walk to ", "walk toward ", "walk towards ", "walk into ", "walk through ",
    "journey to ", "journey toward ", "journey towards ", "depart toward ",
    "step into ", "step through ", "enter the ", "enter ", "visit the ", "visit ",
    "go to ", "move to ", "move into ", "return to ", "leave for ", "make our way to ",
    "make your way to ", "make my way to ", "slip into ", "slip to "
)

RESIDENCE_VISIT_RE = re.compile(
    r"\b(?:her|his|their|my|our)\s+(?:home|house|place|apartment|residence|foyer|dorm|porch)\b|"
    r"\b([A-Za-z0-9_\-]+)'s\s+(?:home|house|place|apartment|residence|foyer|dorm|porch)\b|"
    r"\b(?:head|walk|travel|go|return|step)\s+(?:to\s+)?(?:her|his|their|my|our|[A-Za-z0-9_\-]+)\s*(?:'s)?\s*(?:home|house|place|apartment|residence)\b",
    re.I
)

HALLWAY_CORRIDOR_RE = re.compile(
    r"\b(?:hallway|corridor|hallways|corridors|stairwell|stairs|passage|passageway)\b",
    re.I
)

# Room / Facility exit patterns
ROOM_EXIT_RE = re.compile(
    r"\b(?:step\s+out|head\s+out|walk\s+out|leave\s+the|exit\s+the|leads?\s+the\s+way\s+out\s+of\s+the|go\s+out\s+of\s+the)\s+"
    r"(?:office|room|classroom|hall|building|staff\s+room|council\s+office|library|lab|guild|tavern|inn|shop|store|house|estate|mansion|castle)\b|"
    r"\b(?:step|head|walk|go)\s+outside\b|"
    r"\b(?:get\s+some\s+fresh\s+air|step\s+out\s+for\s+fresh\s+air)\b",
    re.I
)

# Accompanied movement / following NPC patterns
ACCOMPANIED_MOVEMENT_RE = re.compile(
    r"\b(?:follow|accompany|go\s+with|leave\s+with|walk\s+with|head\s+out\s+with)\s+([A-Za-z0-9_\-\s']+?)"
    r"(?:\s+(?:out|outside|to|into|toward|through)\b|\s*$)",
    re.I
)

# Exterior / Macro destination patterns
EXTERIOR_DESTINATION_RE = re.compile(
    r"\b(?:to\s+(?:the\s+)?|onto\s+(?:the\s+)?|toward\s+(?:the\s+)?|towards\s+(?:the\s+)?)"
    r"(?:terrace|garden|gardens|courtyard|balcony|rooftop|roof|patio|grounds|plaza|park|promenade|veranda|gazebo)\b|"
    r"\b(?:terrace|garden|gardens|courtyard|balcony|rooftop|roof|patio|grounds|plaza|park|promenade|veranda|gazebo)\b",
    re.I
)

GENERIC_COMMERCIAL_WORDS: Set[str] = {
    "store", "shop", "market", "bazaar", "outlet", "spot", "center", "centre",
    "place", "building", "district", "street", "road", "area", "zone", "corner"
}

# --- DOWNTIME & REST ---
SLEEP_ACTION_RE = re.compile(
    r"\b(?:sleep\s+until\s+morning|go\s+to\s+sleep|sleep\s+for\s+the\s+night|head\s+to\s+bed|go\s+to\s+bed|"
    r"retire\s+for\s+the\s+night|rest\s+until\s+morning|sleep\s+in\s+bed)\b",
    re.I
)

REST_DOWNTIME_RE = re.compile(
    r"\b(?:sit,\s*drink|sit\s+down|take\s+a\s+seat|rest\s+beside|rest\s+and\s+recover|take\s+a\s+breather|relax\s+at\s+the)\b",
    re.I
)

# --- RECRUITMENT & BOARDS ---
RECRUIT_KEYWORDS = (
    "join your party", "join party", "recruit", "join our party", "permanent companion",
    "travel with us", "party member", "join the party", "invite into party", "invite to party"
)

BOARD_INSPECT_RE = re.compile(
    r"\b(?:contract\s+boards?|notice\s+boards?|bounty\s+boards?|bulletin\s+boards?|quest\s+boards?|public\s+notices?|town\s+boards?|inn\s+boards?|guild\s+boards?)\b",
    re.I
)

# --- PHYSICAL AFFECTION & TENDER TOUCH ---
AFFECTION_HANDHOLD_RE = re.compile(
    r'\b(?:hold|holds|holding|take|takes|taking|clasp|clasping|intertwine|intertwining)\s+(?:[A-Za-z0-9_\-\']+\s*(?:\'s)?\s+|each other\'s\s+)?(?:hands?|fingers?)\b|'
    r'\b(?:walk\s+hand[- ]in[- ]hand|hold\s+hands?)\b',
    re.I
)
AFFECTION_HUG_RE = re.compile(
    r'\b(?:hug|hugs|hugged|hugging|pull\s+(?:her|him|them)\s+into\s+a\s+hug|pulled\s+(?:her|him|them)\s+into\s+a\s+hug|'
    r'wrap\s+(?:your|his|her)\s+arms?\s+around|embrace|embraced|embracing|tender\s+embrace|warm\s+embrace)\b',
    re.I
)
AFFECTION_CUDDLE_RE = re.compile(
    r'\b(?:cuddle|cuddles|cuddled|cuddling|snuggle|snuggles|snuggled|snuggling|'
    r'lean\s+against\s+(?:her|him|them)|rest\s+(?:your|his|her)\s+head\s+on\s+(?:her|his|their)\s+shoulder)\b',
    re.I
)
AFFECTION_CARESS_RE = re.compile(
    r'\b(?:stroke|strokes|stroked|stroking|caress|caresses|caressed|caressing)\s+(?:her|his|their|[A-Za-z0-9_\-\']+(?:\'s)?)\s+(?:[a-zA-Z0-9_\-]+\s+){0,2}(?:hair|cheek|head|face|back|arm|shoulder)\b|'
    r'\b(?:tuck|brush)\s+(?:her|his|their|[A-Za-z0-9_\-\']+(?:\'s)?)\s+hair\s+behind\s+(?:her|his|their)\s+ear\b|'
    r'\b(?:wrap\s+(?:your|his|her)\s+arm\s+around\s+(?:her|his|their)\s+waist|arm\s+around\s+(?:her|his|their)\s+waist|gentle\s+touch)\b',
    re.I
)
AFFECTION_NEGATION_GUARD_RE = re.compile(
    r'\b(?:choke|strangle|tackle|shove|push\s+away|punch|slap|strike|hit|grab\s+by\s+the\s+throat|wrestle|restrain)\b',
    re.I
)

# --- GIFT OFFERING ---
GIFT_OFFER_RE = re.compile(
    r'\b(?:give|gift|offer|present|hand\s+over)\s+(?:a\s+|the\s+|some\s+)?([A-Za-z0-9_\-\s\']+?)\s+(?:to|as\s+a\s+gift\s+to|as\s+a\s+present\s+to)\s+([A-Za-z0-9_\-\s\']+)\b|'
    r'\b(?:give|gift|offer|present)\s+([A-Za-z0-9_\-\s\']+?)\s+(?:a\s+|the\s+|some\s+)?(?:gift|present|bouquet|flowers?|chocolates?|drink|tea|coffee|pendant|token)\b|'
    r'\b(?:give|gift|offer)\s+(?:her|him|them)\s+(?:a\s+|the\s+|some\s+)?([A-Za-z0-9_\-\s\']+?)(?:\s+as\s+a\s+gift)?\b',
    re.I
)
GIFT_NEGATION_GUARD_RE = re.compile(
    r'\b(?:give\s+up|give\s+in|give\s+(?:her|him|them)\s+a\s+(?:punch|slap|beating|lesson|warning|scare)|give\s+way)\b',
    re.I
)

# --- PHONE & CYBERDECK REMOTE COMMS ---
PHONE_COMM_RE = re.compile(
    r'\b\[phone\]\b|'
    r'\b(?:text|message|dm|send\s+(?:a\s+)?(?:text|message|dm)\s+to)\s+([A-Za-z0-9_\-\s\']+)\b|'
    r'\b(?:call|phone|ring|dial|voice\s+call)\s+([A-Za-z0-9_\-\s\']+)\b|'
    r'\b(?:check|open|browse|scroll\s+through|view)\s+(?:the\s+)?(?:peerpulse|netwire|gossip\s+feed|social\s+feed|feed\s+app|phone\s+feed|student\s+directory|net\s+directory)\b',
    re.I
)
PHONE_NEGATION_GUARD_RE = re.compile(
    r'\b(?:call\s+(?:for\s+help|an\s+ambulance|the\s+police|him\s+a|her\s+a|them\s+a)|textbook|call\s+out|call\s+upon)\b',
    re.I
)

# --- SOCIAL ESCORT & CASUAL INVITATIONS ---
SOCIAL_INVITE_RE = re.compile(
    r'\b(?:ask|invite)\s+([A-Za-z0-9_\-\s\']+?)\s+(?:to\s+(?:walk\s+home(?:\s+together)?|study(?:\s+together)?|hang\s+out(?:\s+together)?|grab\s+lunch(?:\s+together)?|eat\s+(?:lunch\s+)?together|get\s+coffee|go\s+on\s+a\s+date|come\s+over|join\s+me)|out\s+on\s+a\s+(?:casual\s+)?date|out\s+for\s+(?:coffee|lunch|dinner))\b|'
    r'\b(?:walk\s+home\s+with|hang\s+out\s+with|study\s+with|grab\s+lunch\s+with|eat\s+lunch\s+with|go\s+on\s+a\s+date\s+with|walk\s+together\s+with|get\s+coffee\s+with)\s+([A-Za-z0-9_\-\s\']+)\b|'
    r'\b(?:walk\s+home\s+together|hang\s+out\s+together|study\s+together|eat\s+lunch\s+together|grab\s+lunch\s+together|head\s+out\s+together|go\s+on\s+a\s+casual\s+date)\b',
    re.I
)

# --- ENVIRONMENTAL SCOUTING & SURROUNDINGS ---
AREA_SCOUT_RE = re.compile(
    r'\b(?:scout\s+(?:the\s+)?|survey\s+(?:the\s+)?|look\s+around\s+(?:the\s+)?|observe\s+the\s+surroundings|examine\s+the\s+room\s+layout|survey\s+the\s+area|scout\s+area|check\s+the\s+perimeter|scan\s+the\s+area|scan\s+the\s+room|inspect\s+(?:the\s+)?(?:undercroft|basement|room|area)|search\s+(?:the\s+)?(?:undercroft|basement|room|area)|explore\s+(?:the\s+)?(?:undercroft|basement|room|area))\b',
    re.I
)
AREA_SCOUT_NEGATION_RE = re.compile(
    r'\b(?:hack|pick\s+lock|breach|force\s+open|steal|pickpocket|infiltrate)\b',
    re.I
)

# --- CLUE & CASEBOARD INVESTIGATION ---
INVESTIGATE_CLUE_RE = re.compile(
    r'\b(?:investigate|examine|inspect|search|check)\s+(?:the\s+)?(?:[a-zA-Z0-9_\-]+\s+){0,3}(?:desk|drawer|drawers|documents?|clues?|evidence|chalk\s+marks?|footprints?|computer|terminal|records?|safe|ledger|body|crime\s+scene|bloodstains?|markings?|notes?|files?|archives?|caseboard|hidden\s+compartment)\b|'
    r'\b(?:search|look)\s+for\s+(?:clues?|evidence|leads?|prints?|hidden\s+items?|fingerprints?)\b',
    re.I
)

# --- STEALTH, LOCKPICKING & SUBTERFUGE ---
STEALTH_COVERT_RE = re.compile(
    r'\b(?:pick\s+(?:the\s+)?lock|picklock|crack\s+the\s+safe|bypass\s+(?:the\s+)?lock|tamper\s+with\s+(?:the\s+)?lock)\b|'
    r'\b(?:pickpocket|pick\s+the\s+pocket|steal\s+from|lift\s+(?:the|a)\s+(?:wallet|keycard|key|creds?|credits)|palm\s+the\s+item)\b|'
    r'\b(?:sneak|sneaks|sneaking|sneaked|snuck|slip\s+past|creep|creeping|tiptoe|skulk|skulking|infiltrate|infiltrating|blend\s+into\s+shadows?|move\s+silently|stealthily\s+(?:approach|move|step)|stay\s+hidden|hide\s+in\s+the\s+shadows?)\b',
    re.I
)

# --- MERCHANT & COMMERCIAL TRANSACTIONS ---
MERCHANT_TRADE_RE = re.compile(
    r'\b(?:browse\s+(?:the\s+)?(?:[a-zA-Z0-9_\-\']+\s+){0,2}(?:wares|goods|stock|shop|store|counter|inventory)|'
    r'buy\s+(?:[a-zA-Z0-9_\-]+\s+){0,2}(?:items?|potions?|gear|equipment|supplies|weapons?|armor)(?:\s+from\s+(?:the\s+)?(?:merchant|shopkeeper|trader))?|'
    r'sell\s+(?:[a-zA-Z0-9_\-]+\s+){0,2}(?:items?|gear|loot|equipment|weapons?|armor)(?:\s+to\s+(?:the\s+)?(?:merchant|shopkeeper|trader))?|'
    r'(?:buy|sell)\s+(?:from|to)\s+(?:the\s+)?(?:merchant|shopkeeper|trader)|'
    r'open\s+(?:the\s+)?(?:shop|store)|visit\s+(?:the\s+)?merchant|trade\s+with\s+(?:the\s+)?(?:merchant|shopkeeper|trader))\b',
    re.I
)



# ==============================================================================
# 3. CORE CLASSIFICATION & DISAMBIGUATION ENGINE
# ==============================================================================

def classify_action_intent(action_text: str, context: Optional[IntentContext] = None) -> ActionIntent:
    """
    Parses any raw player action or choice label through the 3-layer intent pipeline:
    1. Tests structural regex frames across all 10 gameplay categories.
    2. Runs negative disambiguation guards (excludes non-romantic qualifiers, generic nouns, negations).
    3. Resolves specific target entities and sub-targets based on context.
    4. Enforces strict priority hierarchy (Romance/Intimacy > Exit > Movement > Dialogue > Rest > General).
    """
    if not action_text:
        return ActionIntent(category=IntentCategory.GENERAL_ACTION, raw_text="")

    raw_text = str(action_text).strip()
    act_lower = raw_text.lower()
    ctx = context or IntentContext()

    try:
        # ----------------------------------------------------------------------
        # Priority 1: Romantic Confessions & Relationship Milestones
        # ----------------------------------------------------------------------
        if not NON_ROMANTIC_QUALIFIER_RE.search(act_lower) and not ROMANCE_NEGATION_GUARD_RE.search(act_lower) and not THIRD_PARTY_GOSSIP_RE.search(act_lower):
            for rx in ROMANTIC_CONFESSION_FRAMES:
                if rx.search(act_lower):
                    target = _extract_target_npc(raw_text, ctx)
                    return ActionIntent(
                        category=IntentCategory.ROMANTIC_CONFESSION,
                        target_entity=target,
                        raw_text=raw_text,
                        metadata={"milestone_type": "confession"}
                    )

        # ----------------------------------------------------------------------
        # Priority 2: Intimate & Sensual Milestones
        # ----------------------------------------------------------------------
        if ORAL_RECEIVE_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(
                category=IntentCategory.INTIMATE_ACT,
                target_entity=target,
                sub_target="oral_receive",
                raw_text=raw_text,
                metadata={"milestone_event": "oral_receive"}
            )

        if ORAL_GIVE_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(
                category=IntentCategory.INTIMATE_ACT,
                target_entity=target,
                sub_target="oral_give",
                raw_text=raw_text,
                metadata={"milestone_event": "oral_give"}
            )

        if INTIMATE_INTERCOURSE_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(
                category=IntentCategory.INTIMATE_ACT,
                target_entity=target,
                sub_target="intercourse",
                raw_text=raw_text,
                metadata={"milestone_event": "intercourse"}
            )

        if KISS_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(
                category=IntentCategory.INTIMATE_ACT,
                target_entity=target,
                sub_target="kiss",
                raw_text=raw_text,
                metadata={"milestone_event": "kiss"}
            )

        # ----------------------------------------------------------------------
        # Priority 2.5: Physical Affection & Tender Touch
        # ----------------------------------------------------------------------
        is_residence_travel = bool(RESIDENCE_VISIT_RE.search(act_lower) and any(mv in act_lower for mv in ("head to", "walk to", "travel to", "go to", "return to", "enter ", "step into ")))
        if not is_residence_travel and not AFFECTION_NEGATION_GUARD_RE.search(act_lower):
            is_handhold = bool(AFFECTION_HANDHOLD_RE.search(act_lower))
            is_hug = bool(AFFECTION_HUG_RE.search(act_lower))
            is_cuddle = bool(AFFECTION_CUDDLE_RE.search(act_lower))
            is_caress = bool(AFFECTION_CARESS_RE.search(act_lower))
            if is_handhold or is_hug or is_cuddle or is_caress:
                target = _extract_target_npc(raw_text, ctx)
                if is_handhold:
                    sub_t = "handhold"
                elif is_hug:
                    sub_t = "hug"
                elif is_cuddle:
                    sub_t = "cuddle"
                else:
                    sub_t = "caress"
                return ActionIntent(
                    category=IntentCategory.AFFECTION_TOUCH,
                    target_entity=target,
                    sub_target=sub_t,
                    raw_text=raw_text,
                    metadata={"sub_type": sub_t}
                )

        # ----------------------------------------------------------------------
        # Priority 3: Progressive Information Disclosure & Observation
        # ----------------------------------------------------------------------
        if DISCLOSURE_SENSITIVE_SPOTS_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="sensitive_spots", raw_text=raw_text)

        if DISCLOSURE_TURN_ONS_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="turn_ons", raw_text=raw_text)

        if DISCLOSURE_FETISHES_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="fetishes", raw_text=raw_text)

        if DISCLOSURE_VIRGINITY_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="intercourse_experience", raw_text=raw_text)

        if DISCLOSURE_DEMEANOR_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="demeanor", raw_text=raw_text)

        if DISCLOSURE_MANNERISMS_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DISCLOSURE_INQUIRY, target_entity=target, sub_target="mannerisms", raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 3.2: Gift & Item Offering
        # ----------------------------------------------------------------------
        if not GIFT_NEGATION_GUARD_RE.search(act_lower):
            if GIFT_OFFER_RE.search(act_lower):
                target = _extract_target_npc(raw_text, ctx)
                gift_item = _extract_gift_item(raw_text)
                return ActionIntent(
                    category=IntentCategory.GIFT_OFFER,
                    target_entity=target,
                    sub_target=gift_item,
                    raw_text=raw_text,
                    metadata={"item_name": gift_item}
                )

        # ----------------------------------------------------------------------
        # Priority 3.5: Media Capture (Photos, Selfies, Videos)
        # ----------------------------------------------------------------------
        if not MEDIA_NEGATION_GUARD_RE.search(act_lower):
            has_device_aim = bool(MEDIA_DEVICE_AIM_RE.search(act_lower))
            is_video = bool(MEDIA_VIDEO_RE.search(act_lower) or (has_device_aim and any(k in act_lower for k in ("record", "video", "film", "footage"))))
            is_photo = bool(MEDIA_PHOTO_RE.search(act_lower) or (has_device_aim and any(k in act_lower for k in ("photo", "picture", "pic", "snap", "shoot", "selfie", "capture", "scene", "stage", "performance"))))
            if is_video or is_photo:
                # Use regex with word boundaries to prevent Scunthorpe problems (e.g. "bra" in "library")
                nsfw_pattern = r'\b(?:' + '|'.join(map(re.escape, MEDIA_NSFW_KEYWORDS)) + r')\b'
                is_nsfw = bool(re.search(nsfw_pattern, act_lower, re.IGNORECASE))
                
                target = _extract_target_npc(raw_text, ctx)
                if not target:
                    m = re.search(r'\b(?:of|with|at)\s+([A-Za-z0-9_\-\s]+?)(?:$|\s*[,.\-(])', raw_text, re.I)
                    if m:
                        target = m.group(1).strip()
                if not target and ctx.dialogue_partner:
                    target = ctx.dialogue_partner

                if is_video:
                    media_type = "nsfw_video" if is_nsfw else "video"
                    sub_target = "video"
                else:
                    is_selfie = "selfie" in act_lower
                    media_type = "nsfw_photo" if is_nsfw else "photo"
                    sub_target = "selfie" if is_selfie else "photo"

                return ActionIntent(
                    category=IntentCategory.MEDIA_CAPTURE,
                    target_entity=target or "Scene",
                    sub_target=sub_target,
                    raw_text=raw_text,
                    metadata={"media_type": media_type, "is_selfie": "selfie" in act_lower, "is_nsfw": is_nsfw}
                )

        # ----------------------------------------------------------------------
        # Priority 3.8: Smartphone & Cyberdeck Remote Communication
        # ----------------------------------------------------------------------
        if not PHONE_NEGATION_GUARD_RE.search(act_lower):
            if PHONE_COMM_RE.search(act_lower):
                phone_target, comm_type = _extract_phone_target(raw_text, ctx)
                return ActionIntent(
                    category=IntentCategory.PHONE_COMM,
                    target_entity=phone_target,
                    sub_target=comm_type,
                    raw_text=raw_text,
                    metadata={"comm_type": comm_type}
                )

        # ----------------------------------------------------------------------
        # Priority 4: Conversational Exits
        # ----------------------------------------------------------------------
        if any(p in act_lower for p in DIALOGUE_EXIT_PHRASES):
            return ActionIntent(category=IntentCategory.DIALOGUE_EXIT, raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 4.5: Social Escort & Hangout Invitations
        # ----------------------------------------------------------------------
        if SOCIAL_INVITE_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            if "walk home" in act_lower:
                sub_t = "walk_home"
            elif "study" in act_lower:
                sub_t = "study"
            elif "date" in act_lower:
                sub_t = "date"
            elif any(k in act_lower for k in ("lunch", "eat", "coffee")):
                sub_t = "lunch"
            else:
                sub_t = "hangout"
            return ActionIntent(
                category=IntentCategory.SOCIAL_INVITE,
                target_entity=target,
                sub_target=sub_t,
                raw_text=raw_text,
                metadata={"invite_type": sub_t, "is_social": True}
            )

        # ----------------------------------------------------------------------
        # Priority 5: Companion Recruitment (Combat Scenarios)
        # ----------------------------------------------------------------------
        if any(kw in act_lower for kw in RECRUIT_KEYWORDS):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.PARTY_RECRUIT, target_entity=target, raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 5.5: Merchant & Commercial Trade
        # ----------------------------------------------------------------------
        if MERCHANT_TRADE_RE.search(act_lower) and not any(k in act_lower for k in ("steal", "rob", "loot the corpse", "kill the merchant")):
            if "buy" in act_lower:
                sub_t = "buy"
            elif "sell" in act_lower:
                sub_t = "sell"
            else:
                sub_t = "browse"
            target = _extract_target_npc(raw_text, ctx) or "Merchant"
            return ActionIntent(
                category=IntentCategory.MERCHANT_TRADE,
                target_entity=target,
                sub_target=sub_t,
                raw_text=raw_text,
                metadata={"trade_action": sub_t}
            )

        # ----------------------------------------------------------------------
        # Priority 6: Notice & Bounty Board Inspections
        # ----------------------------------------------------------------------
        if BOARD_INSPECT_RE.search(act_lower) and not any(k in act_lower for k in ("steal", "vandalize", "destroy", "tear down")):
            return ActionIntent(category=IntentCategory.INSPECT_BOARD, raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 6.2: Environmental Area Scouting
        # ----------------------------------------------------------------------
        if AREA_SCOUT_RE.search(act_lower) and not AREA_SCOUT_NEGATION_RE.search(act_lower):
            return ActionIntent(
                category=IntentCategory.AREA_SCOUT,
                target_entity=ctx.current_zone or "Surroundings",
                sub_target="scout",
                raw_text=raw_text
            )

        # ----------------------------------------------------------------------
        # Priority 6.4: Clue & Evidence Investigation
        # ----------------------------------------------------------------------
        if INVESTIGATE_CLUE_RE.search(act_lower):
            examined_target = _extract_examined_target(raw_text)
            return ActionIntent(
                category=IntentCategory.INVESTIGATE_CLUE,
                target_entity=examined_target,
                sub_target="evidence",
                raw_text=raw_text,
                metadata={"examined_target": examined_target}
            )

        # ----------------------------------------------------------------------
        # Priority 7: Rest & Nighttime Sleep
        # ----------------------------------------------------------------------
        if SLEEP_ACTION_RE.search(act_lower):
            return ActionIntent(category=IntentCategory.REST_SLEEP, sub_target="sleep", raw_text=raw_text)

        if REST_DOWNTIME_RE.search(act_lower) and not any(k in act_lower for k in ("resist", "endure", "withstand")):
            return ActionIntent(category=IntentCategory.REST_SLEEP, sub_target="rest", raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 7.5: Stealth, Lockpicking & Covert Actions
        # ----------------------------------------------------------------------
        if STEALTH_COVERT_RE.search(act_lower):
            if any(k in act_lower for k in ("pick lock", "pick the lock", "picklock", "crack the safe", "bypass")):
                sub_t = "lockpick"
            elif any(k in act_lower for k in ("pickpocket", "pick the pocket", "steal from", "lift")):
                sub_t = "pickpocket"
            else:
                sub_t = "sneak"
            target = _extract_target_npc(raw_text, ctx) or "Shadows"
            return ActionIntent(
                category=IntentCategory.STEALTH_COVERT,
                target_entity=target,
                sub_target=sub_t,
                raw_text=raw_text,
                metadata={"sub_type": sub_t, "is_stealth": True}
            )

        # ----------------------------------------------------------------------
        # Priority 8: Spatial Movement & Residence Navigation
        # ----------------------------------------------------------------------
        # Check accompanied movement (e.g. "Follow Rachel out of the office", "Go with Maya to the garden")
        acc_match = ACCOMPANIED_MOVEMENT_RE.search(act_lower)
        if acc_match:
            cand_npc = acc_match.group(1).strip()
            cand_clean = cand_npc.title() if len(cand_npc) <= 30 else cand_npc
            if cand_npc.lower() in ("her", "him", "them", "someone", "the npc"):
                target = _extract_target_npc(raw_text, ctx) or cand_clean
            else:
                target = cand_clean
            is_exit = bool(ROOM_EXIT_RE.search(act_lower) or any(k in act_lower for k in ("out", "outside", "away", "leave", "exit")))
            ext_match = EXTERIOR_DESTINATION_RE.search(act_lower)
            target_archetype = "exterior" if ext_match else ("corridor" if HALLWAY_CORRIDOR_RE.search(act_lower) else "")
            return ActionIntent(
                category=IntentCategory.MOVEMENT,
                target_entity=target,
                sub_target="accompanied_travel",
                raw_text=raw_text,
                metadata={
                    "is_accompanied": True,
                    "accompanying_npc": target,
                    "is_room_exit": is_exit,
                    "target_archetype": target_archetype
                }
            )

        # Check room / building exit intents (e.g. "Step out of the office", "Head outside")
        if ROOM_EXIT_RE.search(act_lower):
            ext_match = EXTERIOR_DESTINATION_RE.search(act_lower)
            dest = _extract_movement_target(raw_text) or ("Exterior" if ext_match else "Hallway")
            return ActionIntent(
                category=IntentCategory.MOVEMENT,
                target_entity=dest,
                sub_target="room_exit",
                raw_text=raw_text,
                metadata={
                    "is_room_exit": True,
                    "target_archetype": "exterior" if ext_match else "corridor"
                }
            )

        # Check direct exterior destination intents (e.g. "Step out onto the terrace", "Head to the botanical garden")
        if EXTERIOR_DESTINATION_RE.search(act_lower) and any(pfx in act_lower for pfx in ("to ", "toward ", "onto ", "walk ", "head ", "go ", "step ")):
            dest = _extract_movement_target(raw_text) or "Exterior"
            return ActionIntent(
                category=IntentCategory.MOVEMENT,
                target_entity=dest,
                sub_target="exterior",
                raw_text=raw_text,
                metadata={
                    "is_room_exit": True,
                    "target_archetype": "exterior"
                }
            )

        # Check residence visit intents (e.g. "Maya's home", "her house")
        if RESIDENCE_VISIT_RE.search(act_lower):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(
                category=IntentCategory.MOVEMENT,
                target_entity=target,
                sub_target="residence",
                raw_text=raw_text,
                metadata={"is_residence": True}
            )

        # Check hallway/corridor transitions
        if HALLWAY_CORRIDOR_RE.search(act_lower) and any(pfx in act_lower for pfx in ("enter ", "step into ", "walk into ", "step out into ", "into ")):
            return ActionIntent(
                category=IntentCategory.MOVEMENT,
                target_entity="Hallway",
                sub_target="corridor",
                raw_text=raw_text,
                metadata={"is_hallway": True, "is_room_exit": True}
            )

        # Check general travel / movement prefixes
        is_mv = any(act_lower.startswith(pfx) or f" {pfx}" in act_lower for pfx in MOVEMENT_PREFIXES)
        if is_mv and not any(k in act_lower for k in ("speak", "talk", "greet", "address")):
            # Extract destination string if present
            dest = _extract_movement_target(raw_text)
            return ActionIntent(category=IntentCategory.MOVEMENT, target_entity=dest, raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Priority 9: Dialogue Initiation
        # ----------------------------------------------------------------------
        is_diag_init = any(act_lower.startswith(v) or f" {v}" in act_lower for v in DIALOGUE_INIT_PREFIXES)
        if is_diag_init and not any(k in act_lower for k in ("intimidate", "threaten", "torture", "deceive", "bribe", "attack")):
            target = _extract_target_npc(raw_text, ctx)
            return ActionIntent(category=IntentCategory.DIALOGUE_INIT, target_entity=target, raw_text=raw_text)

        # ----------------------------------------------------------------------
        # Default Fallback: General Action
        # ----------------------------------------------------------------------
        return ActionIntent(category=IntentCategory.GENERAL_ACTION, raw_text=raw_text)


    except Exception as e:
        logger.warning(f"Error during intent classification on '{action_text}': {e}")
        return ActionIntent(category=IntentCategory.GENERAL_ACTION, raw_text=raw_text)


# ==============================================================================
# 4. ENTITY EXTRACTION HELPERS (PURE FUNCTIONAL)
# ==============================================================================

def _extract_target_npc(action_text: str, context: IntentContext) -> str:
    """Extracts target NPC name from text or resolves from context."""
    act_lower = action_text.lower()

    # 1. Match against known present NPCs or dialogue partners
    candidates = list(context.dialogue_partners)
    if context.dialogue_partner and context.dialogue_partner not in candidates:
        candidates.append(context.dialogue_partner)
    for np in context.present_npcs:
        if np and np not in candidates:
            candidates.append(np)

    for cand in candidates:
        c_low = cand.lower().strip()
        c_first = c_low.split()[0] if c_low else ""
        if c_low in act_lower or (len(c_first) >= 3 and (f" {c_first} " in f" {act_lower} " or f" {c_first}'" in act_lower or f" {c_first}s" in act_lower or act_lower.startswith(f"{c_first} "))):
            return cand

    # 2. Extract from possessive patterns (e.g. "enter Maya's home" -> "Maya")
    poss_match = re.search(r"\b([A-Za-z0-9_\-]+)'s\b", action_text)
    if poss_match:
        cand = poss_match.group(1).strip()
        for pfx in ("enter ", "visit ", "walk to ", "head to ", "go to "):
            if cand.lower().startswith(pfx):
                cand = cand[len(pfx):].strip()
        if cand and cand.lower() not in ("it", "that", "this"):
            return cand

    # 3. Default to active dialogue partner if set
    if context.dialogue_partner:
        return context.dialogue_partner

    return ""


def _extract_movement_target(action_text: str) -> str:
    """Extracts raw destination string following movement verbs."""
    act_lower = action_text.lower()
    for pfx in MOVEMENT_PREFIXES:
        if pfx in act_lower:
            idx = act_lower.find(pfx) + len(pfx)
            target = action_text[idx:].strip().rstrip(".")
            # Clean up trailing conjunctions or subordinate clauses
            for sep in (" and ", " to ", " with ", " while ", " before ", ","):
                if sep in target.lower():
                    sep_idx = target.lower().find(sep)
                    target = target[:sep_idx].strip()
            return target
    return ""


def _extract_gift_item(action_text: str) -> str:
    """Extracts candidate item or gift name from action text."""
    act_lower = action_text.lower()
    m1 = re.search(r'\b(?:give|gift|offer|present|hand\s+over)\s+(?:a\s+|the\s+|some\s+)?([A-Za-z0-9_\-\s\']+?)\s+(?:to|as\s+a\s+gift\s+to|as\s+a\s+present\s+to)\b', action_text, re.I)
    if m1:
        cand = m1.group(1).strip()
        if cand.lower() not in ("it", "this", "that", "her", "him", "them"):
            return cand
    m2 = re.search(r'\b(?:give|gift|offer|present)\s+[A-Za-z0-9_\-\s\']+?\s+(?:a\s+|the\s+|some\s+)?([A-Za-z0-9_\-\s\']+)$', action_text, re.I)
    if m2:
        cand = m2.group(1).strip()
        if cand.lower() not in ("gift", "present", "it", "this", "that"):
            return cand
    for kw in ("bouquet", "flowers", "chocolates", "pendant", "tea", "coffee", "gift", "present", "drink"):
        if kw in act_lower:
            return kw.title()
    return "Gift"


def _extract_phone_target(action_text: str, context: IntentContext) -> tuple[str, str]:
    """Returns (target_entity, sub_target) for smartphone/cyberdeck communication."""
    act_lower = action_text.lower()
    for app in ("peerpulse", "netwire", "gossip feed", "social feed", "feed app", "student directory", "net directory", "gallery", "photo vault"):
        if app in act_lower:
            return app.title(), "feed_browse"

    for kw in ("send a message to ", "send a text to ", "send a dm to ", "text ", "message ", "dm "):
        if kw in act_lower:
            idx = act_lower.find(kw) + len(kw)
            cand = action_text[idx:].strip().rstrip(".")
            for sep in (" about ", " saying ", " to ", " and ", " regarding ", ","):
                if sep in cand.lower():
                    cand = cand[:cand.lower().find(sep)].strip()
            if cand.lower() in ("her", "him", "them", "someone"):
                cand = context.dialogue_partner or cand.title()
            return cand or context.dialogue_partner or "Contact", "sms_text"

    for kw in ("voice call ", "call ", "phone ", "ring ", "dial "):
        if kw in act_lower:
            idx = act_lower.find(kw) + len(kw)
            cand = action_text[idx:].strip().rstrip(".")
            for sep in (" about ", " to ", " and ", " regarding ", ","):
                if sep in cand.lower():
                    cand = cand[:cand.lower().find(sep)].strip()
            if cand.lower() in ("her", "him", "them", "someone"):
                cand = context.dialogue_partner or cand.title()
            return cand or context.dialogue_partner or "Contact", "voice_call"

    return context.dialogue_partner or "Phone", "sms_text"


def _extract_examined_target(action_text: str) -> str:
    """Extracts clue or object examined from text."""
    act_lower = action_text.lower()
    for obj in (
        "desk", "drawer", "drawers", "documents", "document", "chalk marks", "chalk mark",
        "footprints", "footprint", "terminal", "computer", "records", "safe", "ledger",
        "crime scene", "bloodstain", "bloodstains", "markings", "marking", "notes", "note",
        "files", "file", "archives", "caseboard", "hidden compartment", "clues", "clue", "evidence"
    ):
        if obj in act_lower:
            return obj.title()
    m = re.search(r'\b(?:examine|inspect|search|investigate)\s+(?:the\s+)?([A-Za-z0-9_\-\s]+?)(?:$|\s*[,.\-(])', action_text, re.I)
    if m:
        cand = m.group(1).strip()
        if len(cand) <= 40:
            return cand.title()
    return "Clue"


# ==============================================================================
# 5. CONVENIENCE WRAPPERS & AMBIENT NORMALIZATION
# ==============================================================================

def is_free_ambient_action(intent: ActionIntent) -> bool:
    """
    Returns True if the intent represents a routine ambient exploration interaction
    that requires no skill check (stat="NONE", requirement=0, mp_cost=0).
    """
    if not intent:
        return False
    cat = intent.category
    if cat in (
        IntentCategory.DIALOGUE_INIT,
        IntentCategory.DIALOGUE_EXIT,
        IntentCategory.INSPECT_BOARD,
        IntentCategory.AREA_SCOUT,
        IntentCategory.REST_SLEEP,
        IntentCategory.PHONE_COMM,
    ):
        return True
    if cat == IntentCategory.MOVEMENT:
        return not intent.metadata.get("is_stealth", False)
    return False


def is_romantic_confession_intent(text: str) -> bool:
    """Facade for checking romantic confession intent."""
    return classify_action_intent(text).category == IntentCategory.ROMANTIC_CONFESSION


def is_dialogue_initiation(text: str) -> bool:
    """Facade for checking dialogue initiation intent."""
    return classify_action_intent(text).category == IntentCategory.DIALOGUE_INIT


def is_conversational_exit(text: str) -> bool:
    """Facade for checking conversational exit intent."""
    return classify_action_intent(text).category == IntentCategory.DIALOGUE_EXIT


def is_sleep_action(text: str) -> bool:
    """Facade for checking nighttime sleep action."""
    intent = classify_action_intent(text)
    return intent.category == IntentCategory.REST_SLEEP and intent.sub_target == "sleep"


def is_board_inspection_action(text: str) -> bool:
    """Facade for checking notice/bounty board inspection."""
    return classify_action_intent(text).category == IntentCategory.INSPECT_BOARD


def is_companion_recruitment_action(text: str) -> bool:
    """Facade for checking party companion recruitment."""
    return classify_action_intent(text).category == IntentCategory.PARTY_RECRUIT


def is_affection_action(text: str) -> bool:
    """Facade for checking non-explicit physical affection intent."""
    return classify_action_intent(text).category == IntentCategory.AFFECTION_TOUCH


def is_gift_offer_action(text: str) -> bool:
    """Facade for checking item or gift offering intent."""
    return classify_action_intent(text).category == IntentCategory.GIFT_OFFER


def is_social_invite_action(text: str) -> bool:
    """Facade for checking social hangout or casual date invitation."""
    return classify_action_intent(text).category == IntentCategory.SOCIAL_INVITE


def is_scout_action(text: str) -> bool:
    """Facade for checking environmental scouting or area survey."""
    return classify_action_intent(text).category == IntentCategory.AREA_SCOUT


def is_investigate_action(text: str) -> bool:
    """Facade for checking clue or crime scene investigation."""
    return classify_action_intent(text).category == IntentCategory.INVESTIGATE_CLUE


def is_stealth_action(text: str) -> bool:
    """Facade for checking stealth, lockpicking, or pickpocketing."""
    return classify_action_intent(text).category == IntentCategory.STEALTH_COVERT


def is_escort_dismissal_action(text: str) -> bool:
    """Facade for checking party/social escort dismissal."""
    t = text.lower()
    return bool(
        is_conversational_exit(text) 
        or any(k in t for k in ("head home alone", "go home alone", "head out alone", "leave alone", "split up", "see you tomorrow", "goodnight", "part ways", "say goodbye"))
    )


def is_phone_comm_action(text: str) -> bool:
    """Facade for checking remote smartphone or cyberdeck communication."""
    return classify_action_intent(text).category == IntentCategory.PHONE_COMM


def is_merchant_action(text: str) -> bool:
    """Facade for checking merchant trade or shop browsing."""
    return classify_action_intent(text).category == IntentCategory.MERCHANT_TRADE


def is_travel_action(text: str) -> bool:
    """Facade for checking movement or travel action."""
    return classify_action_intent(text).category == IntentCategory.MOVEMENT


CONVERSATIONAL_ACTION_PREFIXES = (
    "ask ", "inquire ", "chat ", "talk ", "speak ", "greet ", "compliment ", "flirt ",
    "confess ", "whisper ", "joke ", "reassure ", "tell ", "say ", "thank ", "converse ",
    "question ", "bicker ", "taunt ", "tease ", "banter ", "discuss "
)


def is_conversational_action(text: str) -> bool:
    """Facade for checking conversational or social dialogue action."""
    intent = classify_action_intent(text)
    if intent.category in (
        IntentCategory.DIALOGUE_INIT,
        IntentCategory.DIALOGUE_EXIT,
        IntentCategory.ROMANTIC_CONFESSION,
        IntentCategory.SOCIAL_INVITE
    ):
        return True
    act_lower = str(text or "").lower().strip()
    return any(act_lower.startswith(pfx) or f" {pfx}" in act_lower for pfx in CONVERSATIONAL_ACTION_PREFIXES)


def classify_message_intent(user_message: str) -> str:
    """Classifies user's freeform text message / phone DM into mechanical intents."""
    msg = (user_message or "").lower().strip()
    if not msg:
        return "custom"

    # Use regex to prevent "bra" matching "library"
    nsfw_pattern = r'\b(?:' + '|'.join(map(re.escape, ["nude", "nudes", "naked"] + list(MEDIA_NSFW_KEYWORDS))) + r')\b'
    is_intimate = bool(re.search(nsfw_pattern, msg, re.IGNORECASE))
    
    is_video = any(w in msg for w in MEDIA_VIDEO_KEYWORDS)
    is_photo = is_intimate or any(w in msg for w in MEDIA_PHOTO_KEYWORDS)

    if is_video and is_intimate:
        return "nsfw_video"
    if is_video:
        return "video"
    if is_photo and is_intimate:
        return "nsfw_photo"
    if is_photo:
        return "photo"

    if any(pat.search(msg) for pat in PHONE_MEETUP_PATTERNS):
        return "meetup"

    if any(w in msg for w in INTEL_RUMOR_KEYWORDS):
        return "intel_rumor"

    return "custom"

