from __future__ import annotations
"""
Deterministic Intimate Excitement Meter & In-Game Clock Refractory Engine for Hikayat.

Features:
- Deterministic 0-100% arousal/excitement progression (5-8 turns target).
- Strict genital specificity and directionality (giving vs receiving; non-genital acts award 0).
- Special spot bonus (+5% to +10%) if actions target Codex-revealed sensitive spots.
- Inverse endurance scaling:
    - Player uses SPECIAL END stat (1..10).
    - NPCs derive personal intimate endurance (1..10) from physique, traits, and dynamic.
- Dual-gender & anatomy handling:
    - Male anatomy: Hard physical stop on climax + in-game clock refractory cooldown.
    - Female anatomy: Climax triggers narration -> resets to 35% warm baseline (multi-climax).
- Post-Premature Finish Negotiation:
    - Unsatisfied partners roll a dynamic- and openness-driven Demand Probability.
    - Generates interactive [AGI] / [CHA] / [END] skill checks.
- In-Game Clock Refractory System:
    - Tracks absolute in-game minutes via mechanics/system/time_engine.py.
    - Emits a one-time stamina recovery toast when elapsed.
- Ephemeral lifecycle:
    - Dynamically appears on intimate acts, completely clears upon exit.
- Ultra-compact Discord formatting (<80 chars total) and high-fidelity Web UI payload.
"""
import re
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple

import db

log = logging.getLogger("hikayat.intimate_excitement")

# Non-genital body parts to prevent false positives (e.g. stroking hair, kissing cheek, touching breasts/chest)
NON_GENITAL_BODY_PARTS = (
    "cheek", "cheeks", "hair", "bangs", "forehead", "neck", "nape", "shoulder",
    "shoulders", "back", "hand", "hands", "palm", "palms", "arm", "arms", "lip",
    "lips", "eyelid", "eyelids", "ear", "ears", "chin", "jaw", "jawline",
    "breast", "breasts", "boob", "boobs", "tit", "tits", "chest", "nipple",
    "nipples", "stomach", "belly", "waist", "hip", "hips", "thigh", "thighs",
    "body", "fur", "torso", "rib", "ribs", "flank", "flanks", "tail", "collarbone"
)

# Common non-genital interaction verbs
NON_GENITAL_VERBS = (
    "kiss", "kissing", "hug", "hugging", "cuddle", "cuddling", "embrace",
    "hold close", "holding close", "whisper", "comfort", "soothe", "undress",
    "stroke cheek", "stroke hair", "brush hair", "hold hands", "interlock fingers",
    "lay together", "lie together", "pull blankets", "gaze", "look into eyes",
    "touch", "touching", "caress", "caressing", "stroke", "stroking", "fondle",
    "fondling", "rub", "rubbing", "massage", "massaging", "squeeze", "squeezing",
    "grope", "groping", "cup", "cupping", "tease", "teasing", "pat", "patting"
)

INTIMATE_DECAY_GRACE_TURNS = 2
BASE_DECAY_PER_TURN = 10
AROUSED_DECAY_PER_TURN = 5
AROUSED_STATUS_NAME = "Aroused"

SENSUAL_MAINTENANCE_KEYWORDS = (
    "kiss", "kissing", "whisper", "whispering", "dirty talk", "caress", "caressing",
    "stroke hair", "nuzzle", "nuzzling", "tease", "teasing", "hold close", "holding close",
    "gaze", "gazing", "embrace", "embracing", "tender", "praise", "praising", "pant", "panting",
    "comfort", "soothe", "stroke cheek", "brush hair", "interlock fingers"
)

INTIMATE_DISENGAGEMENT_KEYWORDS = (
    "step back", "step away", "pull back", "pull away", "let go", "break contact",
    "break the kiss", "break away", "excuse myself", "excuse yourself", "leave the room", "part ways",
    "goodbye", "farewell", "walk away", "turn away", "head out", "disengage",
    "pull out", "pulled out", "withdraw", "withdrew", "stop", "slow down and rest",
    "gently withdraw", "ease back", "pause to catch your breath", "pause to catch my breath",
    "get dressed", "leave the bed", "conclude",
    "attack", "strike", "swing sword", "cast spell", "shoot arrow", "draw weapon",
    "open chest", "loot", "equip", "use potion", "drink potion", "check inventory",
    "flee", "escape", "run away", "defend", "block", "parry", "dodge"
)

INTIMATE_INTENT_KEYWORDS = (
    "kiss", "hug", "cuddle", "embrace", "touch", "caress", "stroke", "massage",
    "undress", "fondle", "grope", "cup", "tease", "strip", "love", "seduce",
    "flirt", "bed", "pleasure", "surrender", "yield", "submit", "take the lead",
    "lean in", "draw close", "pull close", "whisper", "hold close", "hold her",
    "hold him", "take her", "take him", "intimate", "erotic", "sex", "intercourse",
    "naked", "bare", "skin", "body", "lips", "thighs", "chest", "breast", "breasts"
)

ANAL_PENETRATIVE_KEYWORDS = (
    "anal intercourse", "anal sex", "anal penetration", "penetrate anally",
    "penetrated anally", "penetrating anally", "take her anally", "takes her anally",
    "take him anally", "takes him anally", "taken anally", "takes you anally",
    "take you anally", "pegging", "peg him", "peg you", "pegged", "she pegs",
    "thrust into her rear", "thrust into his rear", "thrust into your rear",
    "thrusting into her rear", "thrusting into his rear", "thrusting into your rear",
    "thrust into her anus", "thrust into his anus", "thrust into your anus",
    "thrusting into her anus", "thrusting into his anus", "thrusting into your anus",
    "slide into her rear", "slide into his rear", "slide into your rear",
    "slide into her anus", "slide into his anus", "slide into your anus",
    "enter her rear", "enter his rear", "enter your rear",
    "enter her anus", "enter his anus", "enter your anus",
    "penetrate her rear", "penetrate his rear", "penetrate your rear",
    "penetrate her anus", "penetrate his anus", "penetrate your anus",
    "backdoor intercourse", "backdoor penetration"
)

ANAL_RECEIVE_INDICATORS = (
    "pegging", "peg him", "peg you", "pegged", "she pegs",
    "takes you anally", "take you anally", "into your rear", "into your anus",
    "enter your rear", "enter your anus", "penetrate your rear", "penetrate your anus",
    "thrust into your rear", "thrusting into your rear",
    "thrust into your anus", "thrusting into your anus",
    "slide into your rear", "slide into your anus"
)

# Direct penetrative keywords bound to intimate targets
PENETRATIVE_KEYWORDS = (
    "intercourse", "enter her", "enter him", "entered her", "entered him",
    "penetrate her", "penetrate him", "penetrated her", "penetrated him",
    "penetrating her", "penetrating him", "penetrate inside", "penetrated inside",
    "penetrating inside", "penetrate her core", "penetrate her folds", "penetrate her entrance",
    "sexual penetration", "thrust inside", "thrusts inside", "thrusted inside",
    "thrusting inside", "thrust into her", "thrust into him", "thrusting into her",
    "thrusting into him", "thrust into them", "thrusting into them",
    "thrust into both", "thrusting into both", "thrust between both", "thrusting between both",
    "penetrate both", "penetrating both",
    "thrust deeper inside", "thrusting deeper inside", "thrust deep",
    "thrust deeply inside", "thrusting deeply inside", "thrust deeply into her", "thrust deeply into him", "thrust deeply",
    "thrust steadily inside", "thrusting steadily inside", "thrust steadily into her", "thrust steadily into him", "thrust steadily into them", "thrust steadily",
    "thrust gently inside", "thrust gently into her", "thrust gently into him", "thrust rhythmically inside", "thrust rhythmically into her", "thrust rhythmically into him",
    "thrust hips", "thrusting hips", "thrust his pelvis",
    "thrust your pelvis", "deep thrusts", "steady thrusts", "rhythmic thrusts",
    "maintain a steady, deep rhythm", "maintain a steady deep rhythm",
    "shift position to drive deeper", "shift position for a deeper angle",
    "whisper breathless praise as you quicken your pace",
    "ride him", "rides him", "riding him", "rode him", "ride her", "rides her", "riding her",
    "ride his cock", "rides his cock", "riding his cock", "ride his shaft", "riding his shaft",
    "ride your shaft", "riding your shaft", "ride your cock", "riding your cock",
    "straddle and ride", "straddling and riding", "straddle and lower", "straddles and lowers",
    "plunge inside", "plunged inside", "plunging inside", "slide inside", "slid inside",
    "sliding inside", "slides inside", "deep inside her", "deep inside him",
    "take him inside", "takes him inside", "rhythm inside", "pound inside", "pounding inside",
    "fuck her", "fuck him", "fucking her", "fucking him", "fucked her", "fucked him",
    "fucking each other", "fuck inside", "fucking inside", "have sex", "having sex",
    "make love", "making love", "breed her", "breeding her", "breed him", "breeding him",
    "breed inside", "slide into her", "slide into him", "slid into her", "slid into him",
    "push inside her", "push inside him", "pushed inside her", "pushed inside him",
    "sink inside her", "sink inside him", "sank inside her", "sank inside him",
    "sink into her", "sink into him", "sank into her", "sank into him",
    "bottom out inside", "bottomed out inside", "bottoming out inside",
    "sheath yourself", "sheathed inside", "sheathing yourself",
    "fill her inside", "fill him inside", "fill her core", "fill his core",
    "fills her inside", "filled her inside", "fill her with your length",
    "fill her with your cock", "fill her with his cock", "buried to the hilt", "bury to the hilt",
    "pace inside her", "pace inside him", "quicken your pace inside",
    "drive deeper into her", "drive deeper into him", "drive deeper inside",
    "spill deep inside", "spilling deep inside", "spilled deep inside",
    "finish deep inside", "finishing deep inside", "finished deep inside",
    "cum deep inside", "cumming deep inside",
    "climax inside her", "climax inside him", "release inside her", "release inside him",
    "finish inside her", "finish inside him", "spill inside her", "spill inside him",
    "cum inside her", "cum inside him",
    "push over the edge together", "push over the edge into release", "over the edge to finish",
    "taking her from behind", "taking him from behind", "take her from behind", "take him from behind",
    "taking her harder from behind", "taking him harder from behind", "take her harder from behind",
    "taking them from behind", "take them from behind", "from behind",
    "hands and knees", "onto her hands and knees", "onto his hands and knees", "on her hands and knees", "on his hands and knees",
    "doggy style", "doggystyle", "flip her onto", "flip him onto", "turn her onto", "turn him onto",
    "pull out and flip", "pull out and take", "pull out and drive", "pull out and reposition"
) + ANAL_PENETRATIVE_KEYWORDS



PENETRATIVE_EXCLUSIVE_VERBS = (
    "thrust inside", "thrusting inside", "thrust into her", "thrust into him",
    "ride his cock", "ride his shaft", "riding his cock", "riding his shaft",
    "intercourse", "pound inside", "pounding inside", "fucking her", "fucking him",
    "breeding her", "breeding him", "sexual penetration",
    "maintain a steady, deep rhythm", "maintain a steady deep rhythm",
    "shift position to drive deeper", "shift position for a deeper angle"
) + ANAL_PENETRATIVE_KEYWORDS

# Oral stimulation keywords bound to explicit genital anatomy or oral sex indicators
ORAL_KEYWORDS = (
    "oral", "orally", "blowjob", "blowjobs", "fellatio", "cunnilingus", "anilingus",
    "pleasure her orally", "pleasures her orally", "pleasuring her orally",
    "pleasure him orally", "pleasures him orally", "pleasuring him orally",
    "pleasure them orally", "pleasures them orally", "pleasuring them orally",
    "pleasure both orally", "pleasures both orally", "pleasure orally",
    "lick her clit", "licks her clit", "licking her clit", "licked her clit",
    "lick her pussy", "licks her pussy", "licking her pussy",
    "lick her slit", "licks her slit", "licking her slit",
    "lick her core", "licks her core", "licking her core",
    "lick her folds", "licks her folds", "licking her folds",
    "lick his shaft", "licks his shaft", "licking his shaft", "licked his shaft",
    "lick his cock", "licks his cock", "licking his cock", "licked his cock",
    "lick your shaft", "licks your shaft", "lick your cock", "licks your cock",
    "lick between her thighs", "lick between her legs", "lick between his legs",
    "lick her entrance", "licks her entrance", "licking her entrance",
    "lick his balls", "licks his balls",
    "lick her anus", "licks her anus", "licking her anus", "licked her anus",
    "lick his anus", "licks his anus", "licking his anus",
    "lick your anus", "licks your anus", "licking your anus",
    "lick her rear", "licks her rear", "licking her rear",
    "lick his rear", "licks his rear", "lick your rear", "licks your rear",
    "lick tenderly through her", "lick tenderly through his",
    "rhythm of your tongue", "teasing rhythm of your tongue",
    "focus your tongue", "use your tongue", "use your tongue to", "use your tongue on", "use your tongue passionately",
    "circles with your tongue", "circles with his tongue", "teasing her with your tongue",
    "steady oral stimulation", "oral stimulation", "oral pace", "oral rhythm",
    "climax from her mouth", "climax from his mouth",
    "release from her mouth", "release from his mouth",
    "pleasures you with her mouth", "pleasures you with his mouth",
    "pleasure each other with your mouths",
    "rim her", "rims her", "rimming her", "rimmed her",
    "rim him", "rims him", "rimming him", "rimmed him",
    "rim you", "rims you", "rimming you",
    "tongue on her rear", "tongue on his rear", "tongue on your rear",
    "tongue on her anus", "tongue on his anus", "tongue on your anus",
    "suck his cock", "sucks his cock", "sucking his cock", "sucked his cock",
    "suck his shaft", "sucks his shaft", "sucking his shaft", "sucked his shaft",
    "suck your cock", "sucks your cock", "sucking your cock",
    "suck your shaft", "sucks your shaft", "sucking your shaft",
    "suck his penis", "sucks his penis", "sucking his penis",
    "suck your penis", "sucks your penis",
    "suck her clit", "sucks her clit", "sucking her clit", "sucked her clit",
    "suck her core", "sucks her core", "sucking her core",
    "suck him off", "sucks him off", "sucking him off", "suck you off", "sucks you off",
    "suck between her thighs", "suck between her legs",
    "taste her wetness", "taste his wetness", "taste her core", "taste his core",
    "taste her folds", "taste her clit", "taste her slit", "taste her pussy",
    "taste his shaft", "taste his cock", "taste between her thighs", "taste between her legs",
    "taste of her wetness", "taste of her core", "taste of her folds",
    "kneel between her thighs", "kneel between his thighs", "kneel between her legs", "kneel between his legs",
    "taste her intimately", "taste him intimately", "tasting her intimately", "tasting him intimately",
    "take in mouth", "takes in mouth", "took in mouth", "take into mouth", "takes into mouth",
    "took into mouth", "takes you into her mouth", "takes you into his mouth", "take you into mouth",
    "take his shaft into her mouth", "takes his shaft into her mouth",
    "takes your shaft into her mouth", "take your shaft into her mouth",
    "take his cock into her mouth", "takes his cock into her mouth",
    "takes your cock into her mouth", "take your cock into her mouth",
    "mouth around your shaft", "mouth around his shaft", "mouth around your cock", "mouth around his cock",
    "what that mouth can do", "show me what that mouth", "show you what that mouth",
    "warmth of her mouth", "warmth of his mouth", "warmth of your mouth",
    "deep throat", "deep-throat", "lap at her core", "lap at her clit", "lap at her slit",
    "head down toward your lap", "head down to your lap", "head to your lap",
    "toward your lap", "to your lap", "into your lap", "onto your lap", "in your lap",
    "lips around your shaft", "lips around his shaft", "lips around your cock", "lips around his cock",
    "lips parted around", "suction on your", "suction on his", "deepen the suction",
    "deepen suction", "deepens suction", "throat relaxes", "draw you deeper", "draws you deeper",
    "swirls around the crown", "swirl around the crown", "swirls around the head",
    "between your parted thighs", "between her parted thighs",
    "sink between your thighs", "sinks between your thighs",
    "sink between her thighs", "sinks between her thighs",
    "hollowing cheeks", "hollowing her cheeks", "hollowing his cheeks",
    "bobbing her head", "bobbing his head", "bobbing on your shaft", "bobbing on his shaft",
    "eat her out", "eat him out", "eating her out", "eating him out"
)

# Explicit anatomical words
EXPLICIT_GENITAL_WORDS = (
    "clit", "clitoris", "vagina", "core", "shaft", "cock", "penis", "pussy", "slit", "folds",
    "entrance", "groin", "wetness", "between legs", "between thighs", "balls", "ass", "rear", "anus",
    "sensitive crown", "crown", "anal", "anally", "backdoor", "pegging"
)

# Direct genital manual stimulation keywords (handjob, fingering)
MANUAL_KEYWORDS = (
    "finger her", "finger him", "fingering her", "fingering him", "fingering",
    "finger her pussy", "finger her clit", "finger her slit", "finger her cunt",
    "finger her vagina", "finger her core", "fingers inside", "finger inside",
    "fingers in her", "fingers in him", "fingers inside her", "fingers inside him",
    "slide fingers inside", "slip fingers inside", "thrust fingers inside",
    "slide your fingers inside", "slip your fingers inside",
    "two fingers inside", "three fingers inside", "fingers in her core",
    "curl your fingers", "quicken your fingers", "fingers' rhythm",
    "use your fingers to stroke", "use your hands to stroke", "use your hand to stroke",
    "use your hands to please", "use your hand to please", "use your fingers to please",
    "use your hands to please her", "use your hands to please him",
    "stroke her gently with your fingers", "stroke him gently with your fingers",
    "stroke her with your fingers", "stroke him with your fingers",
    "strokes her with your fingers", "strokes him with your fingers",
    "stroke her intimately between", "stroke him intimately between",
    "stroke her tenderly between", "stroke him tenderly between",
    "teasing her with your hand", "teasing her with your fingers",
    "teasing him with your hand", "teasing him with your fingers",
    "steady rhythm of her hand", "steady rhythm of his hand", "rhythm of her hand", "rhythm of his hand",
    "as she strokes you", "as he strokes you", "she strokes you", "he strokes you",
    "climax in her hand", "climax in his hand",
    "finger her anus", "fingers her anus", "fingering her anus",
    "finger his anus", "fingers his anus", "fingering his anus",
    "finger your anus", "fingers your anus", "fingering your anus",
    "finger her rear", "fingers her rear", "fingering her rear",
    "finger his rear", "fingers his rear", "fingering his rear",
    "finger your rear", "fingers your rear", "fingering your rear",
    "fingers in her rear", "fingers in his rear", "fingers in your rear",
    "fingers in her anus", "fingers in his anus", "fingers in your anus",
    "tease her anus", "teases her anus", "teasing her anus", "tease his anus",
    "tease your anus", "teases your anus", "teasing your anus",
    "tease her rear", "teases her rear", "teasing her rear",
    "tease your rear", "teases your rear",
    "handjob", "handjobs",
    "stroke shaft", "strokes shaft", "stroking shaft", "stroke cock", "strokes cock", "stroking cock",
    "stroke penis", "strokes penis", "stroking penis", "stroke his shaft", "strokes his shaft", "stroking his shaft",
    "stroke your shaft", "strokes your shaft", "stroking your shaft",
    "rub clit", "rubs clit", "rubbing clit", "rub her clit", "rubs her clit", "rubbing her clit",
    "rub her core", "rubs her core", "rubbing her core",
    "jack off", "jerk off", "jacking off", "jerking off",
    "pump shaft", "pumps shaft", "pumping shaft", "pump your shaft", "pumps your shaft", "pumping your shaft",
    "tease entrance", "teases entrance", "teasing entrance",
    "tease her entrance", "teases her entrance", "teasing her entrance",
    "tease his entrance", "teases his entrance", "teasing his entrance",
    "tease your entrance", "teases your entrance", "teasing your entrance",
    "massage core", "massages core", "massaging core", "massage her core", "massage his core", "massage your core",
    "touch her core", "touch his core", "touch your core",
    "tease her core", "teases her core", "teasing her core",
    "caress her core", "caressing her core",
    "circle her clit", "circles her clit", "circling her clit",
    "pump him", "pumps him", "pumped him", "pumping him",
    "pump his shaft", "pumps his shaft", "pumping his shaft",
    "stroke her core", "strokes her core", "stroking her core",
    "stroke her clit", "strokes her clit", "stroking her clit",
    "stroke her folds", "strokes her folds", "tease her folds", "teases her folds", "teasing her folds",
    "hand around his length", "hand around your length", "hand around his shaft", "hand around your shaft",
    "fingers around his length", "fingers around your length", "fingers around his shaft", "fingers around your shaft",
    "wrapping around your shaft", "wrapping around his shaft", "wraps around your shaft", "wraps around his shaft",
    "strokes your length", "strokes his length", "stroke your length", "stroke his length",
    "stroking your length", "stroking his length", "pumping your length", "pumping his length",
    "finger you", "fingers you", "fingering you", "fingers inside you", "slide fingers inside you", "slip fingers inside you",
    "stroke your core", "strokes your core", "stroking your core", "rub your core", "rubs your core", "rubbing your core",
    "fingers between her thighs", "fingers between her legs", "hands between her thighs", "hands between her legs",
    "fingers between your thighs", "fingers between your legs", "hand between your thighs", "hand between your legs"
)

ALL_GENITAL_KEYWORDS = PENETRATIVE_KEYWORDS + ORAL_KEYWORDS + MANUAL_KEYWORDS + EXPLICIT_GENITAL_WORDS

ANAL_DETECTION_KEYWORDS = ANAL_PENETRATIVE_KEYWORDS + (
    "anal", "anally", "anus", "backdoor", "pegging", "peg", "anilingus",
    "rim her", "rims her", "rimming her", "rimmed her",
    "rim him", "rims him", "rimming him", "rimmed him",
    "rim you", "rims you", "rimming you",
    "lick her rear", "licks her rear", "licking her rear", "lick his rear", "lick your rear",
    "finger her rear", "fingers her rear", "fingering her rear", "finger his rear", "finger your rear",
    "fingers in her rear", "fingers in his rear", "fingers in your rear",
    "tease her rear", "teases her rear", "teasing her rear", "tease your rear",
    "into her rear", "into his rear", "into your rear"
)

# Non-genital mouth-to-mouth kissing phrases
MOUTH_KISS_KEYWORDS = (
    "kiss her mouth", "kiss his mouth", "kiss on the mouth", "kissing her mouth",
    "kissing his mouth", "kiss on the lips", "kiss her lips", "kiss his lips",
    "kissing her lips", "kissing his lips", "pressed lips together", "press lips together",
    "lips meet", "lips touch", "soft kiss", "gentle kiss", "tender kiss"
)

# Explicit oral triggers that disambiguate genital oral from facial mouth contact
EXPLICIT_ORAL_TRIGGERS = (
    "blowjob", "fellatio", "cunnilingus", "anilingus", "what that mouth can do", "into her mouth",
    "into his mouth", "in her mouth", "in his mouth", "mouth around", "mouth on your",
    "mouth on my", "toward your lap", "to your lap", "into your lap", "in your lap",
    "onto your lap", "draw you deeper", "suction", "deep throat", "lap at",
    "swirls around", "shaft into", "takes you into", "takes him into", "cock into",
    "tongue between", "lick her clit", "lick his shaft", "lick her core",
    "lick her anus", "lick his anus", "lick your anus", "lick her rear", "lick your rear",
    "rim her", "rimming her", "rim him", "rimming him", "rim you", "rimming you",
    "hollowing her cheeks", "hollowing cheeks", "bobbing on",
    "rhythm of your tongue", "focus your tongue", "use your tongue", "use your tongue to", "use your tongue on", "use your tongue passionately",
    "circles with your tongue", "circles with his tongue", "steady oral stimulation",
    "oral stimulation", "oral pace", "oral rhythm", "climax from her mouth",
    "climax from his mouth", "release from her mouth", "release from his mouth",
    "pleasures you with her mouth", "pleasures you with his mouth",
    "pleasure each other with your mouths", "lick tenderly through her", "lick tenderly through his",
    "taste her intimately", "taste him intimately", "tasting her intimately", "tasting him intimately"
)

# Directionality indicators
ORAL_RECEIVE_INDICATORS = (
    "she takes", "he takes", "let her take", "let him take", "she licks", "he licks",
    "she sucks", "he sucks", "her mouth on", "his mouth on", "into her mouth", "into his mouth",
    "in her mouth", "in his mouth", "blowjob", "fellatio", "what that mouth can do",
    "show me what that mouth", "show you what that mouth", "toward your lap", "to your lap",
    "in your lap", "into your lap", "onto your lap", "takes you into", "take you into",
    "takes you in", "take you in", "takes him in", "draw you deeper", "draws you deeper",
    "guide her head", "guide his head", "her head down", "his head down", "between your thighs",
    "between your parted thighs", "bare skin of your groin", "her tongue swirls", "his tongue swirls",
    "she deepens the suction", "he deepens the suction", "on her knees before you",
    "on his knees before you", "mouth on your", "mouth on my", "lips around your",
    "lips around his", "hollowing her cheeks", "hollowing his cheeks",
    "deepens her oral pace", "deepens his oral pace",
    "climax from her mouth", "climax from his mouth",
    "release from her mouth", "release from his mouth",
    "pleasures you with her mouth", "pleasures you with his mouth",
    "lick your anus", "licks your anus", "licking your anus", "lick your rear", "licks your rear",
    "rim you", "rims you", "rimming you", "she rims", "he rims",
    "tongue on your rear", "tongue on your anus"
)

ORAL_GIVE_INDICATORS = (
    "taste her", "tastes her", "tasting her", "tasted her",
    "taste him", "tastes him", "tasting him", "tasted him",
    "kneel between", "kneels between", "kneeling between", "knelt between",
    "get on your knees", "gets on your knees", "drop to your knees", "drops to your knees",
    "eat her", "eats her", "eating her", "ate her",
    "eat her out", "eats her out", "eating her out", "ate her out",
    "eat him", "eats him", "eating him", "ate him",
    "eat him out", "eats him out", "eating him out", "ate him out",
    "lick her", "licks her", "licking her", "licked her",
    "lick his", "licks his", "licking his", "licked his",
    "lick tenderly through her", "lick tenderly through his",
    "suck her", "sucks her", "sucking her", "sucked her",
    "pleasure her", "pleasures her", "pleasuring her",
    "pleasure him", "pleasures him", "pleasuring him",
    "my tongue on", "your tongue on", "tongue between", "your tongue",
    "rhythm of your tongue", "focus your tongue", "use your tongue", "use your tongue to", "use your tongue on", "use your tongue passionately",
    "circles with your tongue", "circles with his tongue", "steady oral stimulation",
    "deepen your oral rhythm",
    "bury your face", "buries your face", "burying your face",
    "part her folds", "parts her folds", "parting her folds",
    "lap at her", "laps at her", "lapping at her", "lapped at her",
    "lap at his", "laps at his", "lapping at his", "lapped at his",
    "between her thighs", "between her spread thighs", "between her parted thighs",
    "between her legs", "between her spread legs", "between her parted legs",
    "between his thighs", "between his spread thighs", "between his legs",
    "press your mouth to her", "press your lips to her", "your lips meeting her",
    "your mouth on her", "your mouth on his", "take her into your mouth",
    "takes her into your mouth", "taking her into your mouth", "into your mouth",
    "cunnilingus", "anilingus", "taste of her", "taste of him", "lick her slit",
    "lick her clit", "lick her core",
    "lick her anus", "licks her anus", "licking her anus", "licked her anus",
    "lick his anus", "licks his anus", "licking his anus",
    "lick her rear", "licks her rear", "licking her rear", "lick his rear", "licks his rear",
    "rim her", "rims her", "rimming her", "rimmed her",
    "rim him", "rims him", "rimming him", "rimmed him",
    "tongue on her rear", "tongue on his rear", "tongue on her anus", "tongue on his anus"
)

MANUAL_RECEIVE_INDICATORS = (
    "she strokes", "he strokes", "she is stroking", "he is stroking",
    "as she strokes you", "as he strokes you", "she strokes you", "he strokes you",
    "steady rhythm of her hand", "steady rhythm of his hand", "rhythm of her hand", "rhythm of his hand",
    "climax in her hand", "climax in his hand",
    "she pumps", "he pumps", "she is pumping", "he is pumping",
    "her hand on your", "his hand on your", "her hand around", "his hand around",
    "wraps her hand", "wraps his hand", "wraps her fingers", "wraps his fingers",
    "her fingers wrap", "his fingers wrap", "wrapping around your", "wraps around your",
    "hand around your", "fingers around your",
    "pump your shaft", "pumps your shaft", "pumping your shaft",
    "pump your length", "pumps your length", "pumping your length",
    "stroke your shaft", "strokes your shaft", "stroking your shaft",
    "stroke your length", "strokes your length", "stroking your length",
    "her palm around", "his palm around", "her fingers stroke", "his fingers stroke",
    "let her stroke", "let him stroke", "guide her hand", "guide his hand",
    "give you a handjob", "gives you a handjob", "giving you a handjob",
    "finger you", "fingers you", "fingering you", "she fingers you", "he fingers you",
    "fingers inside you", "slide fingers inside you", "slip fingers inside you",
    "stroke your core", "strokes your core", "stroking your core",
    "rub your core", "rubs your core", "rubbing your core",
    "tease your entrance", "teases your entrance", "teasing your entrance",
    "massage your core", "touch your core",
    "fingers between your thighs", "fingers between your legs",
    "hand between your thighs", "hand between your legs",
    "finger your anus", "fingers your anus", "fingering your anus",
    "finger your rear", "fingers your rear", "fingering your rear",
    "fingers in your rear", "fingers in your anus",
    "tease your anus", "teases your anus", "teasing your anus",
    "tease your rear", "teases your rear"
)

MANUAL_GIVE_INDICATORS = (
    "slip fingers", "slips fingers", "slipping fingers",
    "slide fingers", "slides fingers", "sliding fingers",
    "thrust fingers", "thrusts fingers", "thrusting fingers",
    "two fingers inside", "three fingers inside",
    "fingers in her", "fingers in him", "fingers inside her", "fingers inside him",
    "curl your fingers", "quicken your fingers", "fingers' rhythm",
    "use your fingers to stroke", "use your hands to stroke", "use your hand to stroke",
    "use your hands to please", "use your hand to please", "use your fingers to please",
    "use your hands to please her", "use your hands to please him",
    "stroke her gently with your fingers", "stroke him gently with your fingers",
    "stroke her with your fingers", "stroke him with your fingers",
    "strokes her with your fingers", "strokes him with your fingers",
    "stroke her intimately between", "stroke him intimately between",
    "stroke her tenderly between", "stroke him tenderly between",
    "teasing her with your hand", "teasing her with your fingers",
    "teasing him with your hand", "teasing him with your fingers",
    "rub clit", "rubs clit", "rubbing clit", "rub her", "rubs her", "rubbing her",
    "rub her core", "rubs her core", "rubbing her core",
    "stroke shaft", "strokes shaft", "stroking shaft",
    "circle her clit", "circles her clit", "circling her clit",
    "stroke her core", "strokes her core", "stroking her core",
    "stroke her clit", "strokes her clit", "stroking her clit",
    "stroke her folds", "strokes her folds",
    "tease entrance", "tease her entrance", "teases her entrance", "teasing her entrance",
    "tease his entrance", "teases his entrance", "teasing his entrance",
    "massage core", "massage her core", "massaging her core", "massage his core",
    "slip your fingers", "slide your fingers",
    "touch her core", "touching her core", "touch his core",
    "caress her core", "caressing her core", "caress thighs",
    "tease her core", "teases her core", "teasing her core",
    "tease her folds", "teases her folds", "teasing her folds",
    "fingers between her thighs", "fingers between her legs",
    "hands between her thighs", "hands between her legs",
    "give him a handjob", "giving him a handjob",
    "finger her", "fingers her", "fingering her", "fingered her",
    "finger him", "fingers him", "fingering him", "fingered him", "fingering",
    "finger her anus", "fingers her anus", "fingering her anus",
    "finger his anus", "fingers his anus", "fingering his anus",
    "finger her rear", "fingers her rear", "fingering her rear",
    "finger his rear", "fingers his rear", "fingering his rear",
    "fingers in her rear", "fingers in his rear",
    "fingers in her anus", "fingers in his anus",
    "tease her anus", "teases her anus", "teasing her anus", "tease his anus",
    "tease her rear", "teases her rear", "teasing her rear"
)

# Scunthorpe problem benign phrase and idiom exclusion regexes
SCUNTHORPE_EXCLUSION_PATTERNS = (
    # Cock derivatives & benign weapon/head gestures
    re.compile(r"\bcock(?:tail|atoo|swain|pit|roach)\w*\b", re.IGNORECASE),
    re.compile(r"\bcock(?:ed|ing)?\s+(?:an?\s+eyebrow|(?:his|her|their|your|one's)?\s*head|the\s+(?:gun|pistol|hammer|trigger|rifle|weapon))\b", re.IGNORECASE),
    # Shaft benign idioms (light, mine, architectural, weapon)
    re.compile(r"\bshaft\s+of\s+(?:light|sunlight|sun|dawn|moonlight|gold|golden\s+light|silver|darkness)\b", re.IGNORECASE),
    re.compile(r"\b(?:mine|elevator|arrow|spear|ventilation|cart|wagon)\s+shaft\w*\b", re.IGNORECASE),
    # Riding benign idioms (horse, vehicle, travel)
    re.compile(r"\b(?:horseback|horse|carriage|boat|cart|wagon|train|bus)\s+ride\w*\b", re.IGNORECASE),
    re.compile(r"\b(?:rode|ride|riding|rides)\s+(?:into\s+town|a\s+horse|the\s+carriage|away|home|back|on\s+horseback|along|past|through\s+town)\b", re.IGNORECASE),
    # Words with 'oral' substring
    re.compile(r"\b(?:moral|morals|morale|coral|floral|pastoral|corporal)\b", re.IGNORECASE),
    # Words with 'cum' substring
    re.compile(r"\b(?:document\w*|cucumber\w*|accumulat\w*|circumstan\w*|succumb\w*)\b", re.IGNORECASE),
    # Words with 'ass' substring
    re.compile(r"\b(?:assassin\w*|assign\w*|assembl\w*|assist\w*|compass\w*|grass\w*|glass\w*|classic\w*|embarrass\w*|harass\w*)\b", re.IGNORECASE),
    # Benign finger gestures & foods
    re.compile(r"\b(?:pointed?\s+a?\s*finger|crossed?\s+(?:his|her|their|your)?\s*fingers?|finger\s+foods?|snapped?\s+(?:his|her|their|your)?\s*fingers?|wagged?\s+(?:his|her|their|your)?\s*finger)\b", re.IGNORECASE),
    # Benign breath / suction idioms
    re.compile(r"\b(?:suck(?:ed|ing)?\s+in\s+a?\s*(?:sharp\s+)?breath|suck(?:ed|ing)?\s+in\s+air|that\s+sucks|it\s+sucks)\b", re.IGNORECASE),
    # Benign swallow idioms
    re.compile(r"\bswallow(?:ed|ing)?\s+(?:hard|dryly|a\s+lump|his\s+pride|her\s+pride|their\s+pride)\b", re.IGNORECASE),
    # Benign lap idioms
    re.compile(r"\b(?:running|run|ran|walked?)\s+a\s+lap\b", re.IGNORECASE),
    re.compile(r"\b(?:lap\s+of\s+luxury|waves?\s+lap(?:ped|ping)?|water\s+lap(?:ped|ping)?)\b", re.IGNORECASE),
    # Benign taste idioms
    re.compile(r"\btast(?:ed|ing|e)\s+(?:the\s+(?:tea|food|wine|ale|soup|stew|drink|meal|bread|meat)|of\s+(?:victory|defeat|blood|iron|ash|ashes|fear|copper))\b", re.IGNORECASE),
    # Benign lick idioms
    re.compile(r"\bflames?\s+lick(?:ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\blick(?:ed|ing|s)?\s+(?:the\s+spoon|(?:his|her|their|your|one's)?\s*(?:dry\s+|chapped\s+|parched\s+|nervous\s+|own\s+)?lips|his\s+wounds|her\s+wounds|their\s+wounds|its\s+paws?)\b", re.IGNORECASE),
    # Benign enter / penetrate / plunge / thrust idioms
    re.compile(r"\benter(?:ed|ing)?\s+(?:the\s+(?:room|tavern|inn|house|building|hall|dungeon|cave|chamber|shop|gate|portal|clearing)|through\s+the)\b", re.IGNORECASE),
    re.compile(r"\bpenetrat(?:ed|ing|e)?\s+(?:the\s+(?:armor|shield|defense|darkness|gloom|mist|fog|forest|veil)|enemy\s+lines)\b", re.IGNORECASE),
    re.compile(r"\bplung(?:ed|ing|e)?\s+(?:into\s+(?:darkness|the\s+water|the\s+lake|the\s+river|the\s+sea|the\s+depths|despair|thought))\b", re.IGNORECASE),
    re.compile(r"\bthrust(?:ed|ing)?\s+(?:his|her|the|a)?\s*(?:sword|spear|dagger|blade|rapier|weapon|torch)\b", re.IGNORECASE),
    # Benign furniture / dungeon chest idioms (prevents RPG treasure chest matching body chest)
    re.compile(r"\b(?:wooden|iron|metal|treasure|dungeon|gold|storage|loot|locked|open)\s+chests?\b", re.IGNORECASE),
    re.compile(r"\b(?:open|opened|opening|unlock|unlocked|unlocking|investigate|investigated|investigating|loot|looted|looting|search|searched|searching|examine|examined|examining)\s+(?:the\s+|a\s+|an?\s+)?chests?\b", re.IGNORECASE),
    re.compile(r"\bchests?\s+of\s+drawers\b", re.IGNORECASE),
    # Profanities used as expletives/adverbs (not sexual intercourse)
    re.compile(r"\b(?:what|who|why|where|how)\s+the\s+fuck\b", re.IGNORECASE),
    re.compile(r"\bfuck\s+(?:off|you|that|it|no|yeah|this|me\s+sideways)\b", re.IGNORECASE),
    re.compile(r"\b(?:give|gives|gave|giving)\s+a\s+fuck\b", re.IGNORECASE),
    re.compile(r"\bholy\s+fuck\b", re.IGNORECASE),
    re.compile(r"\bfucking\s+(?:hell|idiot|moron|crazy|insane|ridiculous|awesome|cool|great|terrible|bad|liar|bastard|jerk|annoying|stupid|kidding|serious)\b", re.IGNORECASE),
    re.compile(r"\bfuck(?:ed)?\s+up\b", re.IGNORECASE),
    # Food / beverage / utensil tasting, licking, or eating
    re.compile(r"\b(?:tast(?:e|ed|ing|es)|lick(?:ed|ing|s)?|suck(?:ed|ing|s)?)\s+(?:the\s+|a\s+|some\s+|her\s+|his\s+|their\s+|your\s+)?(?:tea|coffee|wine|beer|ale|cider|soup|stew|broth|bread|meal|dish|food|meat|fruit|apple|berry|berries|candy|lollipop|ice\s+cream|syrup|honey|sauce|salt|sugar|potion|elixir|draught|brew|drink|water|juice|cooking|baking|pastry|cake|pie)\b", re.IGNORECASE),
    re.compile(r"\btaste\s+(?:of\s+)?(?:her|his|their|your)\s+(?:cooking|baking|food|recipe|dish|cuisine)\b", re.IGNORECASE),
    re.compile(r"\blick(?:ed|ing|s)?\s+(?:the\s+|a\s+)?(?:plate|bowl|spoon|fork|knife|pan|pot|cup|glass|fingers?|lips?)\b", re.IGNORECASE),
    # Investigation / interrogation / workout "pumping"
    re.compile(r"\bpump(?:ed|ing|s)?\s+(?:him|her|them|someone|the\s+guard|the\s+merchant|the\s+witness|the\s+informant)\s+for\s+(?:info|information|answers|details|clues|secrets|news)\b", re.IGNORECASE),
    re.compile(r"\bpump(?:ed|ing|s)?\s+(?:iron|fists?|shotgun|brakes?|water|gas|fuel|tires?|air)\b", re.IGNORECASE),
    re.compile(r"\bpumped\s+up\b", re.IGNORECASE),
    # Emotional metaphors ("touch to the core") and non-genital gestures
    re.compile(r"\btouch(?:ed|ing|es)?\s+(?:her|him|them|me|us|you|one)\s+(?:to\s+the\s+core|deeply|emotionally)\b", re.IGNORECASE),
    re.compile(r"\bcore\s+(?:values?|beliefs?|principles?|strength|workout|concept|idea|problem|issue)\b", re.IGNORECASE),
    re.compile(r"\bstrok(?:e|ed|ing|es)\s+(?:his|her|their|your|one's)?\s*(?:chin|beard|mustache|hair|head|cat|dog|pet|ego)\b", re.IGNORECASE),
    re.compile(r"\brub(?:bed|bing|s)?\s+(?:his|her|their|your|one's)?\s*(?:eyes?|temples?|forehead|brow|hands?\s+together|shoulders?\s+with)\b", re.IGNORECASE),
    # Container, room, and emotional filling
    re.compile(r"\bfill(?:ed|ing|s)?\s+(?:the\s+|a\s+|her\s+|his\s+|their\s+|your\s+)?(?:cup|glass|mug|tankard|plate|bowl|room|hall|air|lungs|silence|mind|pages?|gap|void|blanks?)\b", re.IGNORECASE),
    re.compile(r"\bfill(?:ed|ing|s)?\s+(?:him|her|them|me|us|you)\s+with\s+(?:pride|joy|rage|dread|fear|hope|determination|wonder|disgust|sorrow)\b", re.IGNORECASE),
    # Spatial furniture sinking & sliding
    re.compile(r"\bsink(?:ing|s)?\s+(?:into\s+the\s+|onto\s+the\s+)?(?:chair|couch|sofa|bed|seat|floor|ground|cushion|shadows?)\b", re.IGNORECASE),
    re.compile(r"\bsank\s+(?:into\s+the\s+|onto\s+the\s+)?(?:chair|couch|sofa|bed|seat|floor|ground|cushion|shadows?)\b", re.IGNORECASE),
    re.compile(r"\bslide\s+(?:the\s+|a\s+)?(?:door|drawer|window|bolt|latch|glass|coin)\b", re.IGNORECASE),
    re.compile(r"\bslid\s+(?:the\s+|a\s+)?(?:door|drawer|window|bolt|latch|glass|coin)\b", re.IGNORECASE),
    # Food into mouth
    re.compile(r"\b(?:put|placed?|toss(?:ed)?|pop(?:ped)?)\s+(?:food|bread|meat|fruit|berry|pill|medicine|candy)\s+(?:in|into)\s+(?:his|her|their|your)?\s*mouth\b", re.IGNORECASE),
    # Heart pounding inside chest / skull
    re.compile(r"\b(?:heart|pulse|chest)\s+(?:was\s+)?pound(?:ed|ing|s)?\s+(?:inside|deep\s+inside)\b", re.IGNORECASE),
    re.compile(r"\bpound(?:ed|ing|s)?\s+inside\s+(?:her|his|their|your)?\s*(?:chest|ribs|head|ears|skull)\b", re.IGNORECASE),
    # Spatial enter her / his room, home, or metaphorical thoughts
    re.compile(r"\benter(?:ed|ing)?\s+(?:her|his|their)\s+(?:house|home|room|chamber|office|shop|tavern|inn|store|tent|castle|cabin|cell|carriage|mind|thoughts|head|dreams|life)\b", re.IGNORECASE),
    # Combat or accidental penetration of armor, limbs, or defense
    re.compile(r"\bpenetrat(?:e|ed|ing|es)?\s+(?:her|his|their)\s+(?:shoulder|arm|leg|chest|body\s+armor|flesh|skin\s+with|armor|shield)\b", re.IGNORECASE),
    # Sliding items into pocket, purse, or hand
    re.compile(r"\bslid(?:e|ing|es)?\s+into\s+(?:her|his|their)\s+(?:pocket|bag|purse|hand|room|ear|mind)\b", re.IGNORECASE),
    # Pushing into non-intimate physical rooms or buildings
    re.compile(r"\bpush(?:ed|ing|es)?\s+inside\s+(?:her|his|their)\s+(?:room|house|shop|chamber|tent|cabin)\b", re.IGNORECASE),
    # Metaphorical sink into thoughts, mind, or gaze
    re.compile(r"\bs(?:i|a)nk\s+(?:into|inside)\s+(?:her|his|their)\s+(?:thoughts|mind|eyes|memory|memories|chair|seat)\b", re.IGNORECASE),
    # Acoustic or spatial rhythm inside a structure
    re.compile(r"\brhythm\s+inside\s+(?:the\s+)?(?:room|hall|house|clock|tavern|inn|carriage)\b", re.IGNORECASE),
    # Spatial transport into buildings
    re.compile(r"\btakes?\s+(?:him|her|them)\s+inside\s+(?:the\s+)?\w*\s*(?:tavern|inn|room|house|clinic|hospital|shop|store|tent|carriage|station)\b", re.IGNORECASE),
    # Non-intimate oral terminology
    re.compile(r"\boral\s+(?:tradition|history|hygiene|exam|examination|argument|report|presentation|medication|medicine|pill|dosage|surgery)\b", re.IGNORECASE),
    # Combat / beast teeth or weapon sinking
    re.compile(r"\bs(?:i|a)nk\s+(?:(?:his|her|their|its|your)?\s*(?:teeth|fangs|claws|talons|blade|dagger|knife|sword|spear|weapon)\s+into\s+(?:her|him|them|me|you))\b", re.IGNORECASE),
    # Thrusting an opponent away or aside
    re.compile(r"\bthrust(?:ed|ing)?\s+(?:him|her|them|it)\s+(?:away|aside|back|off)\b", re.IGNORECASE),
    # Benign spatial / architectural "rear" and "peg" idioms
    re.compile(r"\brear\s+(?:of\s+the|door|doors|entrance|gate|window|guard|flank|view|end|wheel|seat|ranks?|wall|courtyard|alley|room|building|tavern|inn|house|shop|wagon|cart)\b", re.IGNORECASE),
    re.compile(r"\b(?:in|at|to|from|toward|towards|into|through)\s+the\s+rear\b", re.IGNORECASE),
    re.compile(r"\brear(?:ed|ing|s)?\s+(?:up|back|its\s+head|his\s+head|her\s+head)\b", re.IGNORECASE),
    re.compile(r"\b(?:wooden|tent|clothes|iron|coat|tuning)\s+pegs?\b", re.IGNORECASE),
    re.compile(r"\bpeg(?:ged|ging)?\s+(?:down|the\s+tent|him\s+as|her\s+as|them\s+as|you\s+as)\b", re.IGNORECASE),
    # Non-erotic narrative / quest / chapter climax idioms
    re.compile(r"\b(?:story|chapter|narrative|quest|dramatic|arc|plot|final|act)\s+climax\b", re.IGNORECASE),
    re.compile(r"\bclimax\s+of\s+the\s+(?:story|chapter|quest|battle|fight|trial|play|performance|investigation|case|arc|act)\b", re.IGNORECASE),
)

_BOUNDARY_CACHE: Dict[Tuple[str, ...], re.Pattern] = {}

def get_boundary_pattern(keywords: Tuple[str, ...]) -> re.Pattern:
    """Compiles and caches word-boundary regex for the given tuple of keywords."""
    cached = _BOUNDARY_CACHE.get(keywords)
    if cached is not None:
        return cached
    patterns = []
    for k in keywords:
        clean_k = k.strip()
        if not clean_k:
            continue
        escaped = re.escape(clean_k)
        flexible = re.sub(r"\\\s+", r"\\s+", escaped)
        patterns.append(rf"\b{flexible}\b")
    compiled = re.compile("|".join(patterns), re.IGNORECASE) if patterns else re.compile(r"$^")
    _BOUNDARY_CACHE[keywords] = compiled
    return compiled

def matches_boundary(text: str, keywords: Tuple[str, ...]) -> bool:
    """Checks whether text contains any of the keywords bounded by word boundaries."""
    if not text or not keywords:
        return False
    return bool(get_boundary_pattern(keywords).search(text))

def sanitize_scunthorpe_text(text: str) -> str:
    """Sanitizes benign non-intimate words and idioms before running intimate keyword detection."""
    if not text:
        return ""
    sanitized = text
    for pattern in SCUNTHORPE_EXCLUSION_PATTERNS:
        sanitized = pattern.sub(" ", sanitized)
    return sanitized


DEMAND_BASE_RATES = {
    "dominant": 0.85,
    "proactive": 0.85,
    "insatiable": 0.85,
    "switch": 0.70,
    "brat": 0.70,
    "receptive": 0.30,
    "surrender": 0.30,
    "service": 0.20,
    "gentle": 0.15,
    "yielding": 0.15,
}

OPENNESS_MODIFIERS = {
    "shameless": 0.20,
    "lewd": 0.20,
    "bold": 0.10,
    "moderate": 0.00,
    "reserved": 0.00,
    "prude": -0.20,
    "modest": -0.20,
}


def get_actor_endurance(actor: Dict[str, Any], is_player: bool = False) -> int:
    """Computes actor's intimate endurance rating (1 to 10)."""
    if is_player:
        end_val = actor.get("end_", actor.get("END", 5))
        try:
            return max(1, min(10, int(end_val)))
        except (ValueError, TypeError):
            return 5

    # Derive NPC intimate endurance deterministically
    base = 5
    appr = actor.get("appearance", {}) if isinstance(actor, dict) else {}
    if not isinstance(appr, dict):
        appr = {}

    physique = str(appr.get("physique") or "").lower()
    dyn = str(appr.get("intimate_dynamic") or appr.get("dynamic") or "").lower()
    traits = [str(t).lower() for t in (actor.get("traits") or [])]

    # Physique impact
    if any(k in physique for k in ("athletic", "muscular", "toned", "tall", "beastfolk")):
        base += 2
    elif any(k in physique for k in ("stocky", "burly", "sturdy")):
        base += 1
    elif any(k in physique for k in ("slim", "petite", "frail", "slender", "soft")):
        base -= 1

    # Dynamic impact
    if any(k in dyn for k in ("dominant", "proactive", "insatiable")):
        base += 2
    elif any(k in dyn for k in ("receptive", "yielding", "gentle", "submissive")):
        base -= 2

    # Traits impact
    if any(k in traits for k in ("athletic", "tough", "resilient", "determined", "competitive")):
        base += 1
    elif any(k in traits for k in ("sensitive", "frail", "delicate", "shy", "timid")):
        base -= 1

    # Deterministic seed hash based on name for natural variety
    name = str(actor.get("name", "npc")).lower()
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:4], 16)
    variance = (h % 3) - 1  # -1, 0, or +1

    return max(1, min(10, base + variance))


def _actor_has_aroused(char_dict: Optional[Dict[str, Any]] = None, actor_data: Optional[Dict[str, Any]] = None) -> bool:
    """Checks if a character or actor entry currently has the Aroused status active."""
    if char_dict:
        raw_eff = char_dict.get("status_effects")
        if isinstance(raw_eff, list):
            for e in raw_eff:
                if isinstance(e, str) and "aroused" in e.lower():
                    return True
                elif isinstance(e, dict) and "aroused" in str(e.get("name", "")).lower():
                    return True
        elif isinstance(raw_eff, str) and "aroused" in raw_eff.lower():
            return True
        if char_dict.get("aroused") is True or int(char_dict.get("aroused_turns", 0) or 0) > 0:
            return True

    if actor_data:
        if actor_data.get("aroused") is True or int(actor_data.get("aroused_turns", 0) or 0) > 0:
            return True
        raw_eff = actor_data.get("status_effects")
        if isinstance(raw_eff, list):
            for e in raw_eff:
                if isinstance(e, str) and "aroused" in e.lower():
                    return True
                elif isinstance(e, dict) and "aroused" in str(e.get("name", "")).lower():
                    return True
        elif isinstance(raw_eff, str) and "aroused" in raw_eff.lower():
            return True

    return False


def _normalize_partner_pronouns(
    text: str,
    partner_name: str,
    partner_contact: Optional[Dict[str, Any]] = None
) -> str:
    """
    Produces a copy of `text` with partner name references normalized to gendered
    pronouns ('her'/'his' for possessives, 'her'/'him' for objects) so keyword tuples
    like 'lick her core', 'guide her head', 'focus your tongue on her core' match
    seamlessly when the player or LLM uses the NPC's name (e.g. "Mia Yamada's core").
    """
    if not text or not partner_name:
        return ""
    p_clean = str(partner_name).strip().strip("*_`\"' ").lower()
    if not p_clean or p_clean == "partner":
        return ""
    gender = ""
    if isinstance(partner_contact, dict):
        gender = str(partner_contact.get("gender") or "").lower()
        if not gender and isinstance(partner_contact.get("appearance"), dict):
            gender = str(partner_contact["appearance"].get("gender") or "").lower()
    t_low = text.lower()
    is_male = gender in ("male", "man", "boy", "m") or (
        not gender and bool(re.search(r"\b(he|him|his)\b", t_low)) and not bool(re.search(r"\b(she|her|hers)\b", t_low))
    )
    poss_pronoun = "his" if is_male else "her"
    obj_pronoun = "him" if is_male else "her"

    import namegen
    names_to_replace = [p_clean]
    first_name = (p_clean.split() or [""])[0]
    given_name = namegen.extract_first_and_last_name(partner_name)[0].lower().strip()
    for fn in (first_name, given_name):
        if fn and len(fn) >= 3 and fn != p_clean and fn not in namegen.NAME_PARTICLES_AND_HONORIFICS and fn not in names_to_replace:
            names_to_replace.append(fn)

    if not any(n in t_low for n in names_to_replace):
        return t_low

    norm = t_low
    for n in names_to_replace:
        esc = re.escape(n)
        norm = re.sub(rf"\b{esc}'s\b", poss_pronoun, norm)
        norm = re.sub(rf"\b{esc}\b", obj_pronoun, norm)

    # Collapse coordinate partner phrases (e.g. "finger kana and her" -> "finger her",
    # "stroke her and elena with your fingers" -> "stroke her with your fingers")
    # so pronoun-bound keyword tuples match for every partner in a coordinate list.
    _coord_stop = r"(?!you\b|your\b|yours\b|yourself\b|kiss\b|touch\b|caress\b|lick\b|suck\b|stroke\b|rub\b|hold\b|pull\b|draw\b|tease\b|press\b|slide\b|thrust\b|sink\b|guide\b|bring\b|make\b|take\b|give\b|use\b|keep\b|let\b|leave\b)[a-z]+(?:'s)?"
    norm_coord = re.sub(
        rf"\b(?:both\s+)?({obj_pronoun}|{poss_pronoun})\s+and\s+{_coord_stop}\b",
        r"\1",
        norm,
    )
    norm_coord = re.sub(
        rf"\b(?:both\s+)?{_coord_stop}\s+and\s+({obj_pronoun}|{poss_pronoun})\b",
        r"\1",
        norm_coord,
    )
    if norm_coord != norm:
        return f"{norm} {norm_coord}"
    return norm


def is_name_in_turn(name_str: str, text: str) -> bool:
    """Checks whether `name_str` (full name or >=3 char first/given name) appears in `text` on word boundaries."""
    if not name_str or not text:
        return False
    clean_n = str(name_str).strip().strip("*_`\"' ").lower()
    if not clean_n:
        return False
    if re.search(rf"\b{re.escape(clean_n)}\b", text, re.IGNORECASE):
        return True
    import namegen
    first_n = (clean_n.split() or [""])[0]
    given_n = namegen.extract_first_and_last_name(clean_n)[0].lower().strip()
    for fn in {first_n, given_n}:
        if len(fn) >= 3 and fn not in namegen.NAME_PARTICLES_AND_HONORIFICS and re.search(rf"\b{re.escape(fn)}\b", text, re.IGNORECASE):
            return True
    return False


def is_actively_targeted_in_action(name_str: str, text: str) -> bool:
    """
    Returns True if `name_str` is actively targeted in `text` (ignoring passive
    subordinate spectator/recovery clauses such as 'while Kana watches/rests/recovers'
    or 'staying close to Kana').
    """
    if not is_name_in_turn(name_str, text):
        return False
    import namegen
    clean_n = str(name_str).strip().strip("*_`\"' ").lower()
    first_n = (clean_n.split() or [""])[0]
    given_n = namegen.extract_first_and_last_name(clean_n)[0].lower().strip()
    patterns = [re.escape(clean_n)]
    for fn in (first_n, given_n):
        if len(fn) >= 3 and fn != clean_n and fn not in namegen.NAME_PARTICLES_AND_HONORIFICS and re.escape(fn) not in patterns:
            patterns.append(re.escape(fn))
    n_pat = "(?:" + "|".join(patterns) + ")"
    stripped = re.sub(
        rf"\b(?:as|while)\s+{n_pat}(?:'s|\s+\w+)?\s+(?:recovers|rests|watches|waits|catches|lies|sits|sleeps|breathes|trembles|shudders)\b[^,.;]*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(
        rf"\b(?:resting|lying|sitting|kneeling)\s+(?:beside|against|near|next\s+to)\s+{n_pat}\b",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(
        rf"\bbeside\s+{n_pat}\b",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    return is_name_in_turn(name_str, stripped)


def scope_text_to_partner(text: str, target_partner: str, other_partners: List[str]) -> str:
    """
    In multi-partner encounters, filters out clauses from `text` that explicitly
    target ONLY an `other_partner` (e.g. 'while maintaining rhythm with Kana' when
    evaluating Elena), while preserving coordinate multi-partner clauses (e.g.
    'both Kana and Elena') and clauses addressing `target_partner`.
    """
    if not text or not other_partners:
        return text
    if not any(is_name_in_turn(op, text) for op in other_partners):
        return text

    import namegen
    raw_clauses = re.split(
        r"(?<=[.!?;])\s+|\b(?:while|as|whereas)\b",
        text,
        flags=re.IGNORECASE,
    )
    all_p = [target_partner] + list(other_partners)
    p_tokens = []
    for pn in all_p:
        cn = str(pn).strip().strip("*_`\"' ").lower()
        if cn:
            p_tokens.append(re.escape(cn))
            fn = (cn.split() or [""])[0]
            gn = namegen.extract_first_and_last_name(cn)[0].lower().strip()
            for tok in (fn, gn):
                if len(tok) >= 3 and tok != cn and tok not in namegen.NAME_PARTICLES_AND_HONORIFICS and re.escape(tok) not in p_tokens:
                    p_tokens.append(re.escape(tok))
    p_union = "(?:" + "|".join(p_tokens) + ")(?:'s)?" if p_tokens else ""

    clauses: List[str] = []
    for rc in raw_clauses:
        rc_str = rc.strip()
        if not rc_str:
            continue
        has_t = is_name_in_turn(target_partner, rc_str)
        has_o = any(is_name_in_turn(op, rc_str) for op in other_partners)
        if has_t and has_o and p_union:
            is_coord = bool(
                re.search(
                    rf"\b{p_union}\s*(?:,\s*{p_union}\s*)*(?:,\s*)?\b(?:and|or)\s+(?:both\s+)?{p_union}\b",
                    rc_str,
                    flags=re.IGNORECASE,
                )
                or re.search(
                    r"\b(?:between|both|among)\b[^.!?;]*\b(?:and|&)\b",
                    rc_str,
                    flags=re.IGNORECASE,
                )
            )
            if not is_coord:
                sub_parts = [sp.strip() for sp in re.split(r",\s+|\s+\band\b\s+", rc_str, flags=re.IGNORECASE) if sp.strip()]
                if len(sub_parts) > 1 and any(
                    is_name_in_turn(target_partner, sp) != any(is_name_in_turn(op, sp) for op in other_partners)
                    for sp in sub_parts
                ):
                    clauses.extend(sub_parts)
                    continue
        clauses.append(rc_str)

    kept: List[str] = []
    current_owner: Optional[str] = None
    for cl_str in clauses:
        has_t = is_name_in_turn(target_partner, cl_str)
        has_o = any(is_name_in_turn(op, cl_str) for op in other_partners)
        if has_t:
            kept.append(cl_str)
            current_owner = "target"
        elif has_o:
            current_owner = "other"
        else:
            if current_owner != "other":
                kept.append(cl_str)

    return " ".join(kept).strip() if kept else text


def classify_intimate_act(
    action_str: str,
    intimate_contact_str: str = "",
    player_name: str = "Player",
    partner_name: str = "Partner",
    partner_contact: Optional[Dict[str, Any]] = None,
    narrative_str: str = ""
) -> Dict[str, Any]:
    """
    Classifies an intimate action to determine act type, directionality, and sensitive spot matches.

    Returns:
        {
            "act_type": "penetrative" | "anal_give" | "anal_receive" | "oral_give" | "oral_receive"
                        | "oral_mutual" | "manual_give" | "manual_receive" | "foreplay_nongenital" | "none",
            "player_stimulated": bool,
            "partner_stimulated": bool,
            "sensitive_spot_matched": bool,
            "matched_spot": str
        }
    """
    turn_raw = f"{action_str or ''} {narrative_str or ''}".lower().strip()
    if not turn_raw:
        turn_raw = (intimate_contact_str or "").lower().strip()
    p_name_low = player_name.lower().strip()
    partner_low = partner_name.lower().strip()
    ic_low = (intimate_contact_str or "").lower().strip()

    res = {
        "act_type": "none",
        "player_stimulated": False,
        "partner_stimulated": False,
        "sensitive_spot_matched": False,
        "matched_spot": "",
        "turn_off_triggered": False,
    }

    if not turn_raw:
        return res

    turn_norm = _normalize_partner_pronouns(turn_raw, partner_name, partner_contact)
    clean_text = f"{sanitize_scunthorpe_text(turn_raw)} {sanitize_scunthorpe_text(turn_norm)}".strip()

    act_raw = (action_str or "").lower().strip()
    act_norm_str = _normalize_partner_pronouns(act_raw, partner_name, partner_contact)
    act_only = f"{sanitize_scunthorpe_text(act_raw)} {sanitize_scunthorpe_text(act_norm_str)}".strip()

    # 0. Action Disengagement & Intent Gate
    if action_str:
        has_act_genital = matches_boundary(act_only, ALL_GENITAL_KEYWORDS)
        if not has_act_genital:
            # If the player chose an explicit disengagement, withdrawal, or combat action
            if any(kw in act_only for kw in INTIMATE_DISENGAGEMENT_KEYWORDS):
                has_continuation = any(
                    cue in act_only
                    for cue in (
                        "flip", "hands and knees", "harder", "from behind", "thrust", "drive",
                        "pound", "deep", "deeper", "behind", "position", "positions", "turn her",
                        "turn him", "over the edge", "finish", "cum", "spill", "pleasure", "take her",
                        "taking her", "take him", "taking him"
                    )
                )
                is_prop_retrieval = bool(re.search(r"\bpull(?:ed)?\s+out\s+(?:a|an|the|that|this|her|his|my|some|your)?\s*(?:paper|script|page|note|clue|item|weapon|coin|book|letter|phone|device|wallet|card|key|sheet)\b", act_only))
                if not (has_continuation or is_prop_retrieval):
                    return res
            # If not currently in an ongoing intimate contact, innocent actions cannot be made intimate by background narrative
            from mechanics.social.physical_state import is_erotic_intimate_contact
            if not is_erotic_intimate_contact(intimate_contact_str):
                has_partner_ref = bool(
                    (partner_low and partner_low in act_raw)
                    or matches_boundary(act_raw, ("her", "she", "hers", "him", "his", "them", "their"))
                    or matches_boundary(act_only, MOUTH_KISS_KEYWORDS)
                    or any(
                        kw in act_only
                        for kw in (
                            "kiss", "kissing", "cuddle", "cuddling", "embrace", "embracing",
                            "hug", "hugging", "undress", "undressing", "strip", "stripping",
                            "make love", "seduce", "seducing", "flirt", "flirting"
                        )
                    )
                )
                has_act_intimate = has_partner_ref and (
                    matches_boundary(act_only, NON_GENITAL_VERBS) or
                    matches_boundary(act_only, NON_GENITAL_BODY_PARTS) or
                    any(kw in act_only for kw in INTIMATE_INTENT_KEYWORDS) or
                    matches_boundary(act_only, MOUTH_KISS_KEYWORDS)
                )
                if not has_act_intimate:
                    return res

    # Check for mouth kissing (non-genital) to avoid false oral triggers:
    # E.g. "Kiss Kana softly on the mouth", "Kiss her lips" without lap/groin/cock/clit/suction/etc.
    is_mouth_kiss = matches_boundary(clean_text, MOUTH_KISS_KEYWORDS)
    has_explicit_oral_trigger = matches_boundary(clean_text, EXPLICIT_ORAL_TRIGGERS)
    is_foreplay_only = False
    if is_mouth_kiss and not has_explicit_oral_trigger and not matches_boundary(clean_text, PENETRATIVE_KEYWORDS) and not matches_boundary(clean_text, MANUAL_KEYWORDS):
        res["act_type"] = "foreplay_nongenital"
        is_foreplay_only = True

    has_active_continuation_cue = any(
        cue in clean_text
        for cue in (
            "rhythm", "pace", "deeper", "deepen", "angle", "shift position",
            "transition positions", "build the heat", "build her pleasure",
            "build his pleasure", "build their pleasure", "over the edge",
            "to the edge", "into climax", "toward climax", "reach climax",
            "toward your own release", "into your own release",
            "coordinating your touch", "coordinate your touch", "rising passion",
            "aftershocks", "relentless", "from behind", "hands and knees",
            "taking her", "taking him", "take her", "take him", "harder", "flip her", "flip him"
        )
    ) or (("mutual oral" in ic_low or "oral mutual" in ic_low or "69" in ic_low) and "staying close to" in clean_text)
    has_ongoing_genital_ic = (
        "player reached climax spent" not in ic_low
        and any(
            g_ic in ic_low
            for g_ic in (
                "intercourse", "oral give", "oral receive", "oral mutual", "mutual oral", "69",
                "manual give", "manual receive", "anal give", "anal receive",
            )
        )
    )

    # If text explicitly only mentions non-genital parts and verbs without any genital keywords
    has_genital_kw = matches_boundary(clean_text, ALL_GENITAL_KEYWORDS)
    if not is_foreplay_only and not has_genital_kw and not (has_ongoing_genital_ic and has_active_continuation_cue):
        if matches_boundary(clean_text, NON_GENITAL_VERBS) or matches_boundary(clean_text, NON_GENITAL_BODY_PARTS):
            res["act_type"] = "foreplay_nongenital"
            is_foreplay_only = True

    # Prioritize explicit player action category over narrative recaps of previous turns
    act_is_penetrative_only = bool(
        act_only
        and matches_boundary(act_only, PENETRATIVE_KEYWORDS)
        and not matches_boundary(act_only, ORAL_KEYWORDS)
        and not matches_boundary(act_only, MANUAL_KEYWORDS)
    )
    act_is_manual_only = bool(
        act_only
        and matches_boundary(act_only, MANUAL_KEYWORDS)
        and not matches_boundary(act_only, ORAL_KEYWORDS)
        and not matches_boundary(act_only, PENETRATIVE_EXCLUSIVE_VERBS)
    )

    act_lbl = clean_text

    if not is_foreplay_only:
        # 2. Check Oral
        if (
            not act_is_penetrative_only
            and not act_is_manual_only
            and matches_boundary(clean_text, ORAL_KEYWORDS)
            and (has_explicit_oral_trigger or not is_mouth_kiss)
        ):
            # Determine directionality: oral_give vs oral_receive vs oral_mutual
            # Prioritize explicit player action intent first before checking narrative prose
            if (
                "69" in act_lbl
                or "mutual" in act_lbl
                or "each other's mouth" in act_lbl
                or "each other with your mouths" in act_lbl
                or "match her oral rhythm" in act_lbl
                or "match his oral rhythm" in act_lbl
                or "maintaining your oral rhythm" in act_lbl
                or ("both yourself and" in act_lbl and "oral" in act_lbl)
            ):
                res["act_type"] = "oral_mutual"
                res["player_stimulated"] = True
                res["partner_stimulated"] = True
            elif act_only and matches_boundary(act_only, ORAL_GIVE_INDICATORS) and not matches_boundary(act_only, ORAL_RECEIVE_INDICATORS):
                res["act_type"] = "oral_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            elif act_only and matches_boundary(act_only, ORAL_RECEIVE_INDICATORS) and not matches_boundary(act_only, ORAL_GIVE_INDICATORS):
                res["act_type"] = "oral_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            elif matches_boundary(act_lbl, ORAL_GIVE_INDICATORS) and not matches_boundary(act_lbl, ORAL_RECEIVE_INDICATORS):
                res["act_type"] = "oral_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            elif matches_boundary(act_lbl, ORAL_RECEIVE_INDICATORS):
                res["act_type"] = "oral_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            elif matches_boundary(act_lbl, ORAL_GIVE_INDICATORS):
                res["act_type"] = "oral_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            else:
                if (
                    f"on {partner_low}" in act_lbl
                    or f"taste {partner_low}" in act_lbl
                    or f"eat {partner_low}" in act_lbl
                    or f"eating {partner_low}" in act_lbl
                    or f"lick {partner_low}" in act_lbl
                    or f"licking {partner_low}" in act_lbl
                    or "her out" in act_lbl
                    or "him out" in act_lbl
                    or "into your mouth" in act_lbl
                    or "oral give" in ic_low
                    or "cunnilingus" in ic_low
                ):
                    res["act_type"] = "oral_give"
                    res["player_stimulated"] = False
                    res["partner_stimulated"] = True
                else:
                    # Default oral fallback: if action was directed toward partner's mouth/lap
                    res["act_type"] = "oral_receive"
                    res["player_stimulated"] = True
                    res["partner_stimulated"] = False

        # 3. Check Manual (fingering / handjob)
        elif (
            not act_is_penetrative_only
            and matches_boundary(clean_text, MANUAL_KEYWORDS)
            and (act_is_manual_only or not matches_boundary(clean_text, PENETRATIVE_EXCLUSIVE_VERBS))
        ):
            if act_only and matches_boundary(act_only, MANUAL_RECEIVE_INDICATORS):
                res["act_type"] = "manual_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            elif act_only and matches_boundary(act_only, MANUAL_GIVE_INDICATORS):
                res["act_type"] = "manual_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            elif matches_boundary(act_lbl, MANUAL_RECEIVE_INDICATORS) and not matches_boundary(act_lbl, MANUAL_GIVE_INDICATORS):
                res["act_type"] = "manual_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            else:
                res["act_type"] = "manual_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True

        # 4. Check Penetrative Intercourse (Vaginal or Anal)
        elif matches_boundary(clean_text, PENETRATIVE_KEYWORDS):
            has_vaginal_override = matches_boundary(clean_text, ("vagina", "pussy", "slit", "folds", "clit", "cunnilingus"))
            is_anal_penetrative = (
                matches_boundary(clean_text, ANAL_PENETRATIVE_KEYWORDS)
                or matches_boundary(clean_text, ("anal", "anally", "rear", "anus", "backdoor", "pegging", "peg"))
                or (not has_vaginal_override and ("anal give" in ic_low or "anal receive" in ic_low))
            )
            if is_anal_penetrative:
                if (
                    (act_only and matches_boundary(act_only, ANAL_RECEIVE_INDICATORS))
                    or matches_boundary(act_lbl, ANAL_RECEIVE_INDICATORS)
                    or ("anal receive" in ic_low and not matches_boundary(clean_text, ANAL_PENETRATIVE_KEYWORDS))
                ):
                    res["act_type"] = "anal_receive"
                else:
                    res["act_type"] = "anal_give"
            else:
                res["act_type"] = "penetrative"
            res["player_stimulated"] = True
            res["partner_stimulated"] = True

        # 4b. Ongoing Genital Act Continuity on Adapted Continuation Choices
        elif has_ongoing_genital_ic and has_active_continuation_cue:
            if "oral mutual" in ic_low or "mutual oral" in ic_low or "69" in ic_low:
                res["act_type"] = "oral_mutual"
                res["player_stimulated"] = True
                res["partner_stimulated"] = True
            elif "oral give" in ic_low:
                res["act_type"] = "oral_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            elif "oral receive" in ic_low:
                res["act_type"] = "oral_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            elif "manual give" in ic_low:
                res["act_type"] = "manual_give"
                res["player_stimulated"] = False
                res["partner_stimulated"] = True
            elif "manual receive" in ic_low:
                res["act_type"] = "manual_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = False
            elif "anal receive" in ic_low:
                res["act_type"] = "anal_receive"
                res["player_stimulated"] = True
                res["partner_stimulated"] = True
            elif "anal give" in ic_low:
                res["act_type"] = "anal_give"
                res["player_stimulated"] = True
                res["partner_stimulated"] = True
            else:
                res["act_type"] = "penetrative"
                res["player_stimulated"] = True
                res["partner_stimulated"] = True

    # 5. Check Turn-Offs & Anal Preferences & Sensitive Spots bonus
    if partner_contact:
        appr = partner_contact.get("appearance", {}) if isinstance(partner_contact, dict) else {}
        if not isinstance(appr, dict):
            appr = {}
        is_anal_act = (
            res["act_type"] in ("anal_give", "anal_receive")
            or matches_boundary(clean_text, ANAL_DETECTION_KEYWORDS)
        )
        turn_offs_val = appr.get("turn_offs") or ""
        turn_offs_str = (
            ", ".join(str(x) for x in turn_offs_val).lower()
            if isinstance(turn_offs_val, (list, tuple))
            else str(turn_offs_val).lower()
        )
        if turn_offs_str and turn_offs_str not in ("none", "unknown", ""):
            from mechanics.social.persona.intimacy.logic import is_turn_off_triggered
            likes_val = appr.get("act_likes") or appr.get("desires_and_kinks") or ""
            likes_str = (
                ", ".join(str(x) for x in likes_val).lower()
                if isinstance(likes_val, (list, tuple))
                else str(likes_val).lower()
            )
            # Prioritize evaluating explicit player action choices over generated narrative prose for turn-offs
            target_to_text = act_only if act_only else clean_text
            if (is_anal_act and ("anal" in turn_offs_str or "backdoor" in turn_offs_str)) or is_turn_off_triggered(target_to_text, turn_offs_str, likes_str):
                res["partner_stimulated"] = False
                res["sensitive_spot_matched"] = False
                res["matched_spot"] = ""
                res["turn_off_triggered"] = True

        if is_anal_act and not res.get("turn_off_triggered") and res["partner_stimulated"]:
            likes_val = appr.get("act_likes") or appr.get("desires_and_kinks") or ""
            likes_str = (
                ", ".join(str(x) for x in likes_val).lower()
                if isinstance(likes_val, (list, tuple))
                else str(likes_val).lower()
            )
            if "anal" in likes_str or "backdoor" in likes_str:
                res["sensitive_spot_matched"] = True
                res["matched_spot"] = "Anal Intimacy"

    if (res["partner_stimulated"] or res["act_type"] == "foreplay_nongenital") and partner_contact and not res.get("turn_off_triggered"):
        appr = partner_contact.get("appearance", {}) if isinstance(partner_contact, dict) else {}
        from mechanics.social.persona.intimacy.logic import (
            match_desires_and_kinks,
            match_sensitive_spots,
        )
        target_spot_text = act_only if action_str else clean_text
        if not res["sensitive_spot_matched"]:
            matched_spots = match_sensitive_spots(target_spot_text, appr.get("sensitive_spots"))
            if matched_spots:
                res["sensitive_spot_matched"] = True
                res["matched_spot"] = matched_spots[0]
        m_desires, m_kinks = match_desires_and_kinks(
            target_spot_text,
            appr.get("desires_and_kinks") or appr.get("turn_ons"),
            appr.get("fetishes"),
        )
        res["matched_desires"] = m_desires
        res["matched_kinks"] = m_kinks

    return res


def calculate_excitement_delta(
    base_stim: int,
    endurance: int,
    sensitive_spot_bonus: bool = False,
    event_arousal_multiplier: float = 1.0,
    anatomy_multiplier: float = 1.0,
    preference_multiplier: float = 1.0,
) -> int:
    """Calculates single-turn excitement delta scaled inversely by endurance and combined anatomy/preference modifiers."""
    if base_stim <= 0:
        return 0
    from mechanics.social.persona.intimacy.constants import (
        ANATOMY_COMBINED_MULT_MAX,
        ANATOMY_COMBINED_MULT_MIN,
        COMBINED_INTIMATE_MULT_MAX,
        COMBINED_INTIMATE_MULT_MIN,
    )
    safe_end = max(1, min(10, endurance))
    multiplier = 10.0 / (5.0 + safe_end)
    safe_ev = max(0.5, min(2.0, float(event_arousal_multiplier or 1.0)))
    safe_anat = max(
        ANATOMY_COMBINED_MULT_MIN,
        min(ANATOMY_COMBINED_MULT_MAX, float(anatomy_multiplier if anatomy_multiplier is not None else 1.0)),
    )
    safe_pref = max(0.5, min(2.0, float(preference_multiplier if preference_multiplier is not None else 1.0)))
    if abs(safe_pref - 1.0) > 1e-6:
        combined_mult = max(
            COMBINED_INTIMATE_MULT_MIN,
            min(COMBINED_INTIMATE_MULT_MAX, safe_anat * safe_pref),
        )
    else:
        combined_mult = safe_anat
    raw_delta = int(round(base_stim * multiplier * safe_ev * combined_mult))
    if sensitive_spot_bonus:
        raw_delta += 6  # +6% flat bonus for targeting revealed sensitive spot (strictly x1.00)
    return max(5, min(35, raw_delta))


def evaluate_preference_excitement_modifiers(
    partner_contact: Optional[Dict[str, Any]],
    act_type: str,
    action_str: str = "",
    sub_intent: str = "",
    partner_classification: Optional[Dict[str, Any]] = None,
    *,
    relationship_score: int = 0,
    relationship_track: str = "platonic",
    shared_intimate_count: int = 0,
    is_hostile: bool = False,
    has_bystanders: bool = False,
    partner_count: int = 1,
    partner_current_excitement: int = 0,
) -> Dict[str, Any]:
    """Evaluates Desires, Active Kinks, Liked/Disliked Acts, Openness pacing/privacy/multi-partner, Giving/Service reward, and discovery emission."""
    from mechanics.social.persona.intimacy.constants import (
        ACT_DISLIKE_EXCITEMENT_MULT,
        ACT_LIKE_EXCITEMENT_MULT,
        COMBINED_INTIMATE_MULT_MAX,
        COMBINED_INTIMATE_MULT_MIN,
        DESIRE_EXCITEMENT_MULT,
        GIVING_SERVICE_PLAYER_MULT,
        KINK_EXCITEMENT_MULT,
        OPENNESS_BOLD_MOMENTUM_MULT,
        OPENNESS_BYSTANDER_DAMPEN_MULT,
        OPENNESS_BYSTANDER_THRILL_MULT,
        OPENNESS_HIDDEN_FIRE_MULT,
        OPENNESS_MULTIPARTNER_BOLD_MULT,
        OPENNESS_MULTIPARTNER_SHY_MULT,
        OPENNESS_RUSHED_AROUSAL_THRESHOLD,
        OPENNESS_RUSHED_WARMUP_MULT,
        OPENNESS_TENDER_FOREPLAY_MULT,
    )
    from mechanics.social.persona.intimacy.logic import (
        compute_with_you_comfort,
        match_act_preferences,
        match_desires_and_kinks,
        match_sensitive_spots,
        normalize_openness_tier,
        resolve_openness_contrast,
    )

    n_char = partner_contact if isinstance(partner_contact, dict) else {}
    n_app = _coerce_app_dict(n_char)
    cl = partner_classification if isinstance(partner_classification, dict) else {}
    npc_name = str(n_char.get("name") or "").strip()

    type_l = str(act_type or "").strip().lower()
    sub_l = str(sub_intent or "").strip().lower()
    act_l = str(action_str or "").lower()

    turn_off_hit = bool(cl.get("turn_off_triggered"))
    discoveries: List[Dict[str, str]] = []

    if turn_off_hit:
        raw_to = str(n_app.get("turn_offs") or "").strip()
        if npc_name and raw_to and raw_to.lower() not in ("none", "unknown"):
            from mechanics.social.persona.intimacy.constants import TURN_OFF_DETECTION_REGISTRY
            matched_to = None
            for reg in TURN_OFF_DETECTION_REGISTRY:
                if reg["name"].lower() in raw_to.lower() and any(
                    (kw in act_l) if " " in kw else bool(re.search(r'\b' + re.escape(kw) + r'\b', act_l))
                    for kw in reg["keywords"]
                ):
                    matched_to = reg["name"]
                    break
            if not matched_to:
                matched_to = [x.strip() for x in raw_to.split(",") if x.strip()][0]
            discoveries.append({
                "npc_name": npc_name,
                "fact_category": "turn_off",
                "fact_key": f"turn_off:{matched_to.lower()}",
                "fact_value": matched_to,
            })
        return {
            "player_multiplier": 1.0,
            "partner_multiplier": 1.0,
            "matched_desires": [],
            "matched_kinks": [],
            "matched_liked_acts": [],
            "matched_disliked_acts": [],
            "giving_service_reward": False,
            "discoveries": discoveries,
        }

    # Spots discovery if matched
    matched_spots = match_sensitive_spots(act_l, n_app.get("sensitive_spots"))
    if cl.get("sensitive_spot_matched") and cl.get("matched_spot") and cl["matched_spot"] != "Anal Intimacy":
        raw_sp = re.sub(r'\([^)]*\)', '', str(cl["matched_spot"])).strip()
        if npc_name and raw_sp:
            discoveries.append({
                "npc_name": npc_name,
                "fact_category": "sensitive_spot",
                "fact_key": f"sensitive_spot:{raw_sp.lower()}",
                "fact_value": raw_sp,
            })
    elif matched_spots and npc_name:
        for ms in matched_spots[:1]:
            raw_sp = re.sub(r'\([^)]*\)', '', ms).strip()
            if raw_sp:
                discoveries.append({
                    "npc_name": npc_name,
                    "fact_category": "sensitive_spot",
                    "fact_key": f"sensitive_spot:{raw_sp.lower()}",
                    "fact_value": raw_sp,
                })

    matched_desires, matched_kinks = match_desires_and_kinks(
        act_l,
        n_app.get("desires_and_kinks") or n_app.get("turn_ons"),
        n_app.get("fetishes"),
    )
    matched_liked_acts, matched_disliked_acts = match_act_preferences(
        act_l,
        n_app.get("act_likes"),
        n_app.get("act_dislikes"),
        sub_intent=sub_l,
        act_type=type_l,
    )

    partner_mult = 1.0
    player_mult = 1.0

    if matched_desires:
        partner_mult *= DESIRE_EXCITEMENT_MULT
        if npc_name:
            for d_item in matched_desires[:2]:
                discoveries.append({
                    "npc_name": npc_name,
                    "fact_category": "desire",
                    "fact_key": f"desire:{d_item.lower()}",
                    "fact_value": d_item,
                })

    if matched_kinks:
        partner_mult *= KINK_EXCITEMENT_MULT
        if npc_name:
            for k_item in matched_kinks[:1]:
                discoveries.append({
                    "npc_name": npc_name,
                    "fact_category": "kink",
                    "fact_key": f"kink:{k_item.lower()}",
                    "fact_value": k_item,
                })

    if matched_liked_acts:
        partner_mult *= ACT_LIKE_EXCITEMENT_MULT
        if npc_name:
            for a_item in matched_liked_acts[:2]:
                discoveries.append({
                    "npc_name": npc_name,
                    "fact_category": "act_pref",
                    "fact_key": f"act_pref:{a_item.lower()}",
                    "fact_value": a_item,
                })

    if matched_disliked_acts:
        partner_mult *= ACT_DISLIKE_EXCITEMENT_MULT
        if npc_name:
            for a_item in matched_disliked_acts[:2]:
                discoveries.append({
                    "npc_name": npc_name,
                    "fact_category": "act_pref",
                    "fact_key": f"act_pref:{a_item.lower()}",
                    "fact_value": a_item,
                })

    # Giving / Service-Oriented Dual Reward
    act_likes_str = str(n_app.get("act_likes") or "").lower()
    dyn_str = str(n_app.get("intimate_dynamic") or n_app.get("dynamic") or "").lower()
    eff_act = sub_l or type_l
    giving_service_reward = False
    if eff_act in ("oral_receive", "manual_receive"):
        if "service" in dyn_str or (eff_act == "oral_receive" and ("giving oral" in act_likes_str or "giving_oral" in act_likes_str)):
            giving_service_reward = True
            player_mult *= GIVING_SERVICE_PLAYER_MULT

    # Openness + With-You Comfort + Gap-Moe Contrast + Bystander + Multi-Partner Scaling
    openness_cue = ""
    multipartner_cue = ""
    raw_open_ev = n_app.get("erotic_openness") or n_app.get("openness")
    if raw_open_ev not in (None, ""):
        op_tier = normalize_openness_tier(raw_open_ev)
        dem_ev = str(n_app.get("intimate_demeanor") or n_char.get("demeanor") or "")
        dyn_ev = str(n_app.get("intimate_dynamic") or n_app.get("dynamic") or "")
        ic_ev = str(n_app.get("intercourse_experience") or n_app.get("predetermined_intercourse") or "")
        eff_score = int(relationship_score or n_char.get("relationship_score", n_char.get("score", 0)) or 0)
        eff_track = str(relationship_track if relationship_track != "platonic" else (n_char.get("relationship_track") or n_char.get("track") or "platonic"))
        eff_shared = int(shared_intimate_count or (n_char.get("shared_intimacy_stats") or {}).get("shared_encounters") or len(n_char.get("gameplay_intimate_events") or []) or 0)
        eff_hostile = bool(is_hostile or str(n_char.get("disposition") or "").strip().lower() == "hostile")

        pre_comf = compute_with_you_comfort(
            op_tier,
            relationship_score=eff_score,
            relationship_track=eff_track,
            shared_intimate_count=eff_shared,
            is_hostile=eff_hostile,
        )
        contrast_ev = resolve_openness_contrast(
            op_tier,
            dem_ev,
            dyn_ev,
            intercourse_experience=ic_ev,
            shared_intimate_count=eff_shared,
            comfort_stage=pre_comf["stage"],
        )
        comf_ev = compute_with_you_comfort(
            op_tier,
            relationship_score=eff_score,
            relationship_track=eff_track,
            shared_intimate_count=eff_shared,
            is_hostile=eff_hostile,
            contrast_archetype=contrast_ev["archetype"],
            bluff_crack_active=contrast_ev["bluff_crack_active"],
        )

        needs_warmup = (
            (op_tier == "prude" and comf_ev["stage"] in ("guarded", "warming_up"))
            or (contrast_ev["archetype"] == "all_talk_tease" and contrast_ev["bluff_crack_active"])
        )
        is_explicit_fast = type_l in ("penetrative", "anal_give", "anal_receive") or any(
            k in act_l for k in ("rush", "hurry", "force", "slam", "shove", "straight inside", "skip foreplay", "thrust", "penetrat")
        )
        is_tender_foreplay = (type_l == "foreplay_nongenital" and not is_explicit_fast) or any(
            k in act_l for k in ("gentle", "gently", "slow", "slowly", "tender", "tenderly", "reassur", "warm up", "caress", "kiss")
        )
        if needs_warmup:
            if is_explicit_fast and int(partner_current_excitement or 0) < OPENNESS_RUSHED_AROUSAL_THRESHOLD:
                partner_mult *= OPENNESS_RUSHED_WARMUP_MULT
                openness_cue = "warmup_rushed"
            elif is_tender_foreplay:
                partner_mult *= OPENNESS_TENDER_FOREPLAY_MULT
                openness_cue = "tender_warmup"

        if op_tier in ("bold", "shameless") and not (contrast_ev["archetype"] == "all_talk_tease" and contrast_ev["bluff_crack_active"]):
            if any(k in act_l for k in ("teas", "dirty", "urgent", "passion", "bold", "claim", "deep", "eager", "hard", "fast")):
                partner_mult *= OPENNESS_BOLD_MOMENTUM_MULT
        if contrast_ev["archetype"] == "hidden_fire" and contrast_ev["mechanical_active"] and not has_bystanders:
            partner_mult *= OPENNESS_HIDDEN_FIRE_MULT
            if not openness_cue:
                openness_cue = "hidden_fire_unleashed"

        if has_bystanders:
            pref_blob = f"{n_app.get('fetishes') or ''} {n_app.get('desires_and_kinks') or ''} {n_app.get('turn_ons') or ''}".lower()
            has_public_thrill = any(k in pref_blob for k in ("public", "exhibition", "risk of being caught", "voyeur"))
            if op_tier in ("prude", "moderate") and not has_public_thrill:
                partner_mult *= OPENNESS_BYSTANDER_DAMPEN_MULT
                openness_cue = "bystander_hesitation"
            elif op_tier == "shameless" or (op_tier == "bold" and has_public_thrill):
                partner_mult *= OPENNESS_BYSTANDER_THRILL_MULT
                openness_cue = "bystander_thrill"

        if int(partner_count or 1) >= 2:
            if op_tier in ("bold", "shameless"):
                partner_mult *= OPENNESS_MULTIPARTNER_BOLD_MULT
                multipartner_cue = "bold_group"
            elif op_tier == "prude" or (op_tier == "moderate" and comf_ev["stage"] == "guarded"):
                if comf_ev["stage"] != "trusting_private":
                    partner_mult *= OPENNESS_MULTIPARTNER_SHY_MULT
                    multipartner_cue = "shy_group"

    partner_mult = max(COMBINED_INTIMATE_MULT_MIN, min(COMBINED_INTIMATE_MULT_MAX, partner_mult))
    player_mult = max(COMBINED_INTIMATE_MULT_MIN, min(COMBINED_INTIMATE_MULT_MAX, player_mult))

    return {
        "player_multiplier": round(player_mult, 4),
        "partner_multiplier": round(partner_mult, 4),
        "matched_desires": matched_desires,
        "matched_kinks": matched_kinks,
        "matched_liked_acts": matched_liked_acts,
        "matched_disliked_acts": matched_disliked_acts,
        "giving_service_reward": giving_service_reward,
        "openness_cue": openness_cue,
        "multipartner_cue": multipartner_cue,
        "discoveries": discoveries,
    }


def _coerce_app_dict(entity: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(entity, dict):
        return {}
    app = entity.get("appearance")
    if isinstance(app, str):
        try:
            import json
            parsed = json.loads(app)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return dict(app) if isinstance(app, dict) else {}


def _clean_anatomy_raw(val: Any) -> str:
    s = str(val or "").strip()
    if s.lower() in ("", "none", "unknown", "null", "n/a", "false", "0"):
        return ""
    return s


def _size_tier_to_pref_bucket(tier: str) -> Optional[str]:
    t = str(tier or "").strip().lower()
    if t in ("flat", "small"):
        return "smaller"
    if t in ("large", "huge"):
        return "bigger"
    return None


def detect_targeted_anatomy_parts(
    action_str: str,
    act_type: str = "",
    sub_intent: str = "",
) -> set[str]:
    """Detects whether the turn directly targets breasts ('bb') or rear/anal ('ass')."""
    targeted: set[str] = set()
    act_l = str(action_str or "").lower()
    sub_l = str(sub_intent or "").strip().lower()
    type_l = str(act_type or "").strip().lower()

    if re.search(
        r"\b(breasts?|bust|cleavage|nipples?|boobs?|tits?|titties|titjob|paizuri|underbust|bosom|(?<!treasure )chest)\b",
        act_l,
    ):
        targeted.add("bb")

    if (
        type_l in ("anal_give", "anal_receive")
        or sub_l in ("anal_give", "anal_receive", "anal_mutual")
        or re.search(
            r"\b(ass|asshole|arse|rear|rear\s+entry|butt|butts|buttocks?|butt[\s\-]?cheeks?|ass[\s\-]?cheeks?|booty|glutes?|spank|spanks|spanking|backdoor|anal|anally|pegging|doggy|doggy[\s\-]?style|from\s+behind)\b",
            act_l,
        )
    ):
        targeted.add("ass")

    return targeted


def evaluate_anatomy_excitement_modifiers(
    player_char: Optional[Dict[str, Any]],
    partner_contact: Optional[Dict[str, Any]],
    act_type: str,
    action_str: str = "",
    sub_intent: str = "",
    partner_classification: Optional[Dict[str, Any]] = None,
    refractory_downgraded: bool = False,
    targeted_parts: Optional[set[str]] = None,
) -> Dict[str, Any]:
    """Evaluates PP penetrative multiplier (bidirectional) and NPC BB/Ass size preferences (ambient + targeted)."""
    from mechanics.social.persona.intimacy.constants import (
        ANATOMY_COMBINED_MULT_MAX,
        ANATOMY_COMBINED_MULT_MIN,
        BODY_PREF_AMBIENT_DISLIKE_MULT,
        BODY_PREF_AMBIENT_LIKE_MULT,
        BODY_PREF_TARGETED_DISLIKE_MULT,
        BODY_PREF_TARGETED_LIKE_MULT,
        PP_PENETRATIVE_MULTIPLIERS,
    )
    from mechanics.social.persona.intimacy.appearance import (
        classify_asset_size_tier,
        classify_rear_size_tier,
        is_feral_rear_excluded,
    )
    from mechanics.social.persona.intimacy.generation import (
        generate_dynamic_body_preferences,
        normalize_body_preferences,
    )

    p_char = player_char if isinstance(player_char, dict) else {}
    n_char = partner_contact if isinstance(partner_contact, dict) else {}
    p_app = _coerce_app_dict(p_char)
    n_app = _coerce_app_dict(n_char)
    cl = partner_classification if isinstance(partner_classification, dict) else {}

    p_gender_l = str(p_char.get("gender") or p_app.get("gender") or "").strip().lower()
    n_gender_l = str(n_char.get("gender") or n_app.get("gender") or "").strip().lower()
    from mechanics.social.persona.core import is_female_gender, is_male_gender

    p_is_male = is_male_gender(p_gender_l)
    p_is_female = is_female_gender(p_gender_l)
    n_is_male = is_male_gender(n_gender_l)
    n_is_female = is_female_gender(n_gender_l)

    raw_p_pp = _clean_anatomy_raw(p_char.get("penis_size") or p_app.get("penis_size"))
    raw_n_pp = _clean_anatomy_raw(n_char.get("penis_size") or n_app.get("penis_size"))
    p_has_pp = bool(raw_p_pp) or (p_is_male and not p_is_female)
    n_has_pp = bool(raw_n_pp) or (n_is_male and not n_is_female)

    p_pp_tier = classify_asset_size_tier(raw_p_pp, "male") if raw_p_pp else "average"
    n_pp_tier = classify_asset_size_tier(raw_n_pp, "male") if raw_n_pp else "average"

    type_l = str(act_type or "").strip().lower()
    act_l = str(action_str or "").lower()
    targets = targeted_parts if targeted_parts is not None else detect_targeted_anatomy_parts(action_str, type_l, sub_intent)

    # 1. Bidirectional PP penetrative multiplier (strictly penetrative / anal_give / anal_receive only)
    p_pp_mult = 1.0
    n_pp_mult = 1.0
    penetrator_side: Optional[str] = None
    penetrator_pp_tier = "average"

    if (not refractory_downgraded) and type_l in ("penetrative", "anal_give", "anal_receive"):
        if type_l == "anal_give":
            if p_has_pp:
                n_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(p_pp_tier, 1.0)
                penetrator_side = "player"
                penetrator_pp_tier = p_pp_tier
        elif type_l == "anal_receive":
            if n_has_pp:
                p_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(n_pp_tier, 1.0)
                penetrator_side = "partner"
                penetrator_pp_tier = n_pp_tier
        else:
            if p_has_pp and not n_has_pp:
                n_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(p_pp_tier, 1.0)
                penetrator_side = "player"
                penetrator_pp_tier = p_pp_tier
            elif n_has_pp and not p_has_pp:
                p_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(n_pp_tier, 1.0)
                penetrator_side = "partner"
                penetrator_pp_tier = n_pp_tier
            elif p_has_pp and n_has_pp:
                if any(cue in act_l for cue in ("inside you", "inside me", "into you", "into me", "fucks you", "fucks me", "takes you", "rides his", "ride him")):
                    p_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(n_pp_tier, 1.0)
                    penetrator_side = "partner"
                    penetrator_pp_tier = n_pp_tier
                else:
                    n_pp_mult = PP_PENETRATIVE_MULTIPLIERS.get(p_pp_tier, 1.0)
                    penetrator_side = "player"
                    penetrator_pp_tier = p_pp_tier

    # 2. Player BB & Ass size buckets (strict guard: male without breast_size -> None, feral myobu_fox -> skip rear)
    player_race = str(p_char.get("race") or p_app.get("race") or "").strip().lower()
    npc_race = str(n_char.get("race") or n_app.get("race") or "").strip().lower()

    raw_p_bb = _clean_anatomy_raw(p_char.get("breast_size") or p_app.get("breast_size"))
    bb_bucket = _size_tier_to_pref_bucket(classify_asset_size_tier(raw_p_bb, "female")) if raw_p_bb else None

    raw_p_rear = _clean_anatomy_raw(p_char.get("rear_size") or p_app.get("rear_size"))
    if raw_p_rear and not is_feral_rear_excluded(player_race) and not is_feral_rear_excluded(npc_race):
        ass_bucket = _size_tier_to_pref_bucket(classify_rear_size_tier(raw_p_rear))
    else:
        ass_bucket = None

    # 3. NPC BB & Ass preferences (preserve explicit []; lazy-seed only real legacy contact records)
    has_pref_keys = (
        ("body_likes" in n_app and n_app["body_likes"] is not None)
        or ("body_dislikes" in n_app and n_app["body_dislikes"] is not None)
        or ("body_likes" in n_char and n_char["body_likes"] is not None)
        or ("body_dislikes" in n_char and n_char["body_dislikes"] is not None)
    )
    if has_pref_keys:
        npc_likes, npc_dislikes = normalize_body_preferences(
            n_char.get("body_likes") if "body_likes" in n_char else n_app.get("body_likes"),
            n_char.get("body_dislikes") if "body_dislikes" in n_char else n_app.get("body_dislikes"),
        )
    elif n_app and not is_feral_rear_excluded(npc_race):
        seed_str = f"{n_char.get('desc', '')}_{npc_race}_{n_char.get('name', '')}".encode("utf-8")
        h_val = int(hashlib.md5(seed_str).hexdigest(), 16)
        seeded = generate_dynamic_body_preferences(h_val)
        npc_likes = list(seeded.get("body_likes") or [])
        npc_dislikes = list(seeded.get("body_dislikes") or [])
    else:
        npc_likes, npc_dislikes = [], []

    bb_mult = 1.0
    ass_mult = 1.0
    height_mult = 1.0
    triggered_prefs: List[Dict[str, Any]] = []
    partner_active = bool(cl.get("partner_stimulated", True)) and not bool(cl.get("turn_off_triggered", False))
    npc_name = str(n_char.get("name") or "").strip()

    if partner_active:
        if bb_bucket is not None:
            bb_key = f"{bb_bucket}_bb"
            bb_targeted = "bb" in targets
            if bb_key in npc_likes:
                bb_mult = BODY_PREF_TARGETED_LIKE_MULT if bb_targeted else BODY_PREF_AMBIENT_LIKE_MULT
                triggered_prefs.append({
                    "npc_name": npc_name,
                    "fact_category": "body_pref",
                    "fact_key": f"body_pref:{bb_key}",
                    "fact_value": bb_key,
                    "sentiment": "like",
                    "part": "bb",
                    "targeted": bb_targeted,
                })
            elif bb_key in npc_dislikes:
                bb_mult = BODY_PREF_TARGETED_DISLIKE_MULT if bb_targeted else BODY_PREF_AMBIENT_DISLIKE_MULT
                triggered_prefs.append({
                    "npc_name": npc_name,
                    "fact_category": "body_pref",
                    "fact_key": f"body_pref:{bb_key}",
                    "fact_value": bb_key,
                    "sentiment": "dislike",
                    "part": "bb",
                    "targeted": bb_targeted,
                })

        if ass_bucket is not None:
            ass_key = f"{ass_bucket}_ass"
            ass_targeted = "ass" in targets
            if ass_key in npc_likes:
                ass_mult = BODY_PREF_TARGETED_LIKE_MULT if ass_targeted else BODY_PREF_AMBIENT_LIKE_MULT
                triggered_prefs.append({
                    "npc_name": npc_name,
                    "fact_category": "body_pref",
                    "fact_key": f"body_pref:{ass_key}",
                    "fact_value": ass_key,
                    "sentiment": "like",
                    "part": "ass",
                    "targeted": ass_targeted,
                })
            elif ass_key in npc_dislikes:
                ass_mult = BODY_PREF_TARGETED_DISLIKE_MULT if ass_targeted else BODY_PREF_AMBIENT_DISLIKE_MULT
                triggered_prefs.append({
                    "npc_name": npc_name,
                    "fact_category": "body_pref",
                    "fact_key": f"body_pref:{ass_key}",
                    "fact_value": ass_key,
                    "sentiment": "dislike",
                    "part": "ass",
                    "targeted": ass_targeted,
                })

        from mechanics.social.persona.intimacy.logic import evaluate_height_preference

        p_height_app = dict(p_app)
        if p_char.get("stature") and not p_height_app.get("stature"):
            p_height_app["stature"] = p_char.get("stature")
        n_height_app = dict(n_app)
        if n_char.get("stature") and not n_height_app.get("stature"):
            n_height_app["stature"] = n_char.get("stature")
        if "body_likes" in n_char and n_char.get("body_likes") is not None and "body_likes" not in n_height_app:
            n_height_app["body_likes"] = n_char.get("body_likes")
        if "body_dislikes" in n_char and n_char.get("body_dislikes") is not None and "body_dislikes" not in n_height_app:
            n_height_app["body_dislikes"] = n_char.get("body_dislikes")
        if "height_pref_seeded" in n_char and n_char.get("height_pref_seeded") is not None and "height_pref_seeded" not in n_height_app:
            n_height_app["height_pref_seeded"] = n_char.get("height_pref_seeded")
        if n_char.get("desc") and "desc" not in n_height_app:
            n_height_app["desc"] = n_char.get("desc")

        h_eval = evaluate_height_preference(
            p_height_app,
            n_height_app,
            npc_gender=n_gender_l,
            npc_race=npc_race,
            npc_name=npc_name,
            player_race=player_race,
        )
        height_mult = float(h_eval.get("excitement_mult", 1.0))
        h_tp = h_eval.get("triggered_pref")
        if isinstance(h_tp, dict) and h_tp.get("fact_key"):
            triggered_prefs.append(h_tp)

    n_combined = max(ANATOMY_COMBINED_MULT_MIN, min(ANATOMY_COMBINED_MULT_MAX, n_pp_mult * bb_mult * ass_mult * height_mult))
    p_combined = max(ANATOMY_COMBINED_MULT_MIN, min(ANATOMY_COMBINED_MULT_MAX, p_pp_mult))

    return {
        "player_multiplier": round(p_combined, 4),
        "partner_multiplier": round(n_combined, 4),
        "pp_player_mult": p_pp_mult,
        "pp_partner_mult": n_pp_mult,
        "bb_mult": bb_mult,
        "ass_mult": ass_mult,
        "height_mult": height_mult,
        "penetrator_side": penetrator_side,
        "penetrator_pp_tier": penetrator_pp_tier,
        "triggered_preferences": triggered_prefs,
    }


def roll_partner_demand(partner_contact: Dict[str, Any], *, has_bystanders: bool = False) -> bool:
    """
    Computes whether an unsatisfied partner demands manual or oral stimulation
    based on their intimate dynamic, erotic openness, and active Hidden Fire contrast.
    """
    from mechanics.social.persona.intimacy.constants import OPENNESS_HIDDEN_FIRE_DEMAND_BONUS
    from mechanics.social.persona.intimacy.logic import (
        compute_with_you_comfort,
        normalize_openness_tier,
        resolve_openness_contrast,
    )

    appr = partner_contact.get("appearance", {}) if isinstance(partner_contact, dict) else {}
    dyn = str(appr.get("intimate_dynamic") or appr.get("dynamic") or "").lower()
    openness = str(appr.get("erotic_openness") or appr.get("openness") or "").lower()
    op_tier = normalize_openness_tier(openness or "moderate")

    # Determine base chance
    base_rate = 0.30
    for k, rate in DEMAND_BASE_RATES.items():
        if k in dyn:
            base_rate = rate
            break

    # Determine openness modifier
    mod = OPENNESS_MODIFIERS.get(op_tier, 0.0)
    if mod == 0.0 and openness:
        for k, m in OPENNESS_MODIFIERS.items():
            if k in openness:
                mod = m
                break

    # Hidden Fire demand boost once private and comfortable
    hf_bonus = 0.0
    if isinstance(partner_contact, dict) and not has_bystanders:
        rel_score = int(partner_contact.get("relationship_score", partner_contact.get("score", 0)) or 0)
        rel_track = str(partner_contact.get("relationship_track") or partner_contact.get("track") or "platonic")
        shared_cnt = int(
            (partner_contact.get("shared_intimacy_stats") or {}).get("shared_encounters")
            or len(partner_contact.get("gameplay_intimate_events") or [])
            or 0
        )
        is_host = str(partner_contact.get("disposition") or "").strip().lower() == "hostile"
        comf = compute_with_you_comfort(
            op_tier,
            relationship_score=rel_score,
            relationship_track=rel_track,
            shared_intimate_count=shared_cnt,
            is_hostile=is_host,
        )
        cont = resolve_openness_contrast(
            op_tier,
            appr.get("intimate_demeanor") or "",
            dyn,
            intercourse_experience=str(appr.get("intercourse_experience") or ""),
            shared_intimate_count=shared_cnt,
            comfort_stage=comf["stage"],
        )
        if cont["archetype"] == "hidden_fire" and cont["mechanical_active"]:
            hf_bonus = OPENNESS_HIDDEN_FIRE_DEMAND_BONUS

    final_chance = max(0.05, min(0.95, base_rate + mod + hf_bonus))
    import random
    return random.random() < final_chance


def calculate_refractory_duration(player_endurance: int) -> int:
    """Calculates in-game minutes required for male physical refractory recovery."""
    safe_end = max(1, min(10, player_endurance))
    # END 10 -> 20 mins; END 5 -> 40 mins; END 2 -> 52 mins
    return max(20, 60 - (safe_end * 4))


def compute_excitement_step(
    physical_state: Dict[str, Any],
    action_str: str,
    player_char: Dict[str, Any],
    partner_contact: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
    narrative_str: str = "",
    partner_contacts: Optional[List[Dict[str, Any]]] = None,
    sub_intent: Optional[str] = None,
    target_npc: Optional[str] = None,
    action_check_margin: Optional[int] = None,
    has_bystanders: Optional[bool] = None,
    partner_count: Optional[int] = None,
    relationship_score: Optional[int] = None,
    relationship_track: Optional[str] = None,
    shared_intimate_count: Optional[int] = None,
    is_hostile: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Executes a turn step on the intimate excitement meters.
    Updates and mutates physical_state["excitement"] dynamically.
    Supports single or multiple simultaneous partners.
    """
    player_name = str(player_char.get("name", "Player"))
    player_gender = str(player_char.get("gender", "Male")).lower()
    is_female_player = "female" in player_gender or "woman" in player_gender

    curr_excitement = physical_state.setdefault("excitement", {})
    actors = curr_excitement.setdefault("actors", {})
    if not actors and isinstance(physical_state.get("actors"), dict):
        for k, v in physical_state["actors"].items():
            if isinstance(v, dict) and "meter" in v:
                actors[k] = dict(v)

    def _find_or_create_actor(name: str, char_dict: dict, is_player: bool) -> Tuple[str, dict]:
        clean_name = str(name).strip().strip("*_`\"' ")
        matched_k = None
        # 1. Exact or stripped match
        for k in actors:
            if str(k).strip().strip("*_`\"' ").lower() == clean_name.lower():
                matched_k = k
                break
        # 2. First name match
        if not matched_k:
            n_first = (clean_name.lower().split() or [""])[0]
            if len(n_first) >= 3:
                for k in actors:
                    k_first = (str(k).strip().strip("*_`\"' ").lower().split() or [""])[0]
                    if k_first == n_first:
                        matched_k = k
                        break
        # 3. Substring match
        if not matched_k:
            for k in actors:
                k_clean = str(k).strip().strip("*_`\"' ").lower()
                if (len(clean_name) >= 3 and clean_name.lower() in k_clean) or (len(k_clean) >= 3 and k_clean in clean_name.lower()):
                    matched_k = k
                    break

        if matched_k:
            if matched_k != clean_name:
                actors[clean_name] = actors.pop(matched_k)
                matched_k = clean_name
            act_entry = actors[matched_k]
            if "endurance" not in act_entry:
                act_entry["endurance"] = get_actor_endurance(char_dict, is_player=is_player)
            if "climaxes_count" not in act_entry:
                act_entry["climaxes_count"] = 0
            if "max" not in act_entry:
                act_entry["max"] = 100
            if "status" not in act_entry:
                act_entry["status"] = "Warming Up"
            if "idle_turns" not in act_entry:
                act_entry["idle_turns"] = 0
            if "aroused_turns" not in act_entry:
                init_aroused = 0
                raw_st = char_dict.get("status_effects") if isinstance(char_dict, dict) else None
                if isinstance(raw_st, list):
                    for s_item in raw_st:
                        if isinstance(s_item, str) and "aroused" in s_item.lower():
                            m_ar = re.search(r"\[(\d+)\s*turns?\]", s_item, re.IGNORECASE)
                            init_aroused = int(m_ar.group(1)) if m_ar else 3
                            break
                act_entry["aroused_turns"] = init_aroused
            return matched_k, act_entry

        init_aroused_new = 0
        raw_st_new = char_dict.get("status_effects") if isinstance(char_dict, dict) else None
        if isinstance(raw_st_new, list):
            for s_item in raw_st_new:
                if isinstance(s_item, str) and "aroused" in s_item.lower():
                    m_ar = re.search(r"\[(\d+)\s*turns?\]", s_item, re.IGNORECASE)
                    init_aroused_new = int(m_ar.group(1)) if m_ar else 3
                    break
        actors[clean_name] = {
            "meter": 0, "max": 100, "delta": 0,
            "endurance": get_actor_endurance(char_dict, is_player=is_player),
            "climaxes_count": 0,
            "status": "Warming Up",
            "idle_turns": 0,
            "aroused_turns": init_aroused_new
        }
        return clean_name, actors[clean_name]

    # Assemble all partner contacts
    contacts_list: List[Dict[str, Any]] = []
    if partner_contacts:
        contacts_list = [c for c in partner_contacts if isinstance(c, dict) and c.get("name")]
    if not contacts_list and partner_contact and isinstance(partner_contact, dict):
        contacts_list = [partner_contact]

    if session and isinstance(session, dict):
        from mechanics.world.mobility import get_session_dialogue_partners
        sess_dps = get_session_dialogue_partners(session)
        known_names = {str(c.get("name", "")).strip().lower() for c in contacts_list}
        for dp in sess_dps:
            if dp and str(dp).strip().lower() not in known_names:
                contacts_list.append({"name": str(dp).strip()})
                known_names.add(str(dp).strip().lower())

    if not contacts_list:
        contacts_list = [{"name": "Partner"}]

    p_key, p_data = _find_or_create_actor(player_name, player_char, is_player=True)
    player_name = p_key

    partner_actor_tuples: List[Tuple[str, dict, dict]] = []
    for pc in contacts_list:
        p_raw = str(pc.get("name") or "Partner").strip()
        n_k, n_d = _find_or_create_actor(p_raw, pc, is_player=False)
        partner_actor_tuples.append((n_k, n_d, pc))

    primary_n_key, primary_n_data, primary_contact = partner_actor_tuples[0]
    partner_name = primary_n_key

    # Prune only truly absent actors (preserving all active partners in this encounter)
    valid_keys = {p_key} | {t[0] for t in partner_actor_tuples}
    for stale_k in list(actors.keys()):
        if stale_k not in valid_keys:
            actors.pop(stale_k, None)

    curr_excitement["current_partner"] = partner_name
    curr_excitement["current_partners"] = [t[0] for t in partner_actor_tuples]

    curr_ic = str(physical_state.get("intimate_contact", ""))
    curr_ic_low = curr_ic.lower()
    prev_last_act_str = str(curr_excitement.get("last_act") or "").strip().lower()

    # Evaluate action classification for all active partners
    act_low = (action_str or "").lower()
    nar_low = (narrative_str or "").lower()
    turn_low = f"{act_low} {nar_low}"

    raw_named_in_act = {
        t[0]: is_name_in_turn(t[0], act_low)
        for t in partner_actor_tuples
    }
    active_named_in_act = {
        t[0]: is_actively_targeted_in_action(t[0], act_low)
        for t in partner_actor_tuples
    }
    named_in_act = active_named_in_act if any(active_named_in_act.values()) else raw_named_in_act
    any_named_in_act = any(named_in_act.values())

    scoped_acts: Dict[str, str] = {}
    act_has_genital_or_cont: Dict[str, bool] = {}
    for n_k, n_d, pc in partner_actor_tuples:
        is_targeted = named_in_act[n_k] if any_named_in_act else True
        other_names = [t[0] for t in partner_actor_tuples if t[0] != n_k]
        s_act = (
            scope_text_to_partner(action_str, n_k, other_names)
            if (action_str and is_targeted and other_names)
            else (action_str if is_targeted else "")
        )
        scoped_acts[n_k] = s_act
        if s_act:
            s_norm = _normalize_partner_pronouns(s_act.lower(), n_k, pc)
            s_clean = f"{sanitize_scunthorpe_text(s_act.lower())} {sanitize_scunthorpe_text(s_norm)}".strip()
            has_g = matches_boundary(s_clean, ALL_GENITAL_KEYWORDS)
            has_c = any(
                cue in s_clean
                for cue in (
                    "rhythm", "pace", "deeper", "deepen", "angle", "shift position",
                    "transition positions", "build the heat", "build her pleasure",
                    "build his pleasure", "build their pleasure", "over the edge",
                    "to the edge", "into climax", "toward climax", "reach climax",
                    "toward your own release", "into your own release",
                    "coordinating your touch", "coordinate your touch", "rising passion",
                    "aftershocks", "relentless",
                )
            ) or (
                ("oral mutual" in curr_ic_low or "mutual oral" in curr_ic_low or "69" in curr_ic_low or prev_last_act_str == "oral_mutual")
                and "staying close to" in s_clean
            )
            act_has_genital_or_cont[n_k] = bool(has_g or has_c)
        else:
            act_has_genital_or_cont[n_k] = False

    any_act_genital_or_cont = any(act_has_genital_or_cont.values())

    partner_classifications: Dict[str, Dict[str, Any]] = {}
    if sub_intent:
        _ACT_MAP = {
            "intercourse": "penetrative",
            "oral_give": "oral_give",
            "oral_receive": "oral_receive",
            "oral_mutual": "oral_mutual",
            "manual_give": "manual_give",
            "manual_receive": "manual_receive",
            "manual_mutual": "manual_give",
            "anal_give": "anal_give",
            "anal_receive": "anal_receive",
            "anal_mutual": "anal_give",
            "kiss": "foreplay_nongenital",
            "foreplay": "foreplay_nongenital",
            "aftercare": "none",
            "redress": "none",
        }
        mapped_type = _ACT_MAP.get(sub_intent, "foreplay_nongenital")
        target_tokens = [t.strip().lower() for t in (target_npc or "").split(",") if t.strip()]

        for n_k, n_d, pc in partner_actor_tuples:
            is_targeted = any(t in n_k.lower() or n_k.lower() in t for t in target_tokens) if target_tokens else True
            if is_targeted:
                appr = pc.get("appearance", {}) if isinstance(pc, dict) else {}
                turn_offs_val = appr.get("turn_offs") or ""
                turn_offs_str = (
                    ", ".join(str(x) for x in turn_offs_val).lower()
                    if isinstance(turn_offs_val, (list, tuple))
                    else str(turn_offs_val).lower()
                )
                turn_off_hit = False
                if turn_offs_str and turn_offs_str not in ("none", "unknown", ""):
                    from mechanics.social.persona.intimacy.logic import is_turn_off_triggered
                    likes_val = appr.get("act_likes") or appr.get("desires_and_kinks") or ""
                    likes_str = (
                        ", ".join(str(x) for x in likes_val).lower()
                        if isinstance(likes_val, (list, tuple))
                        else str(likes_val).lower()
                    )
                    act_clean = (action_str or "").lower()
                    if ("anal" in sub_intent and ("anal" in turn_offs_str or "backdoor" in turn_offs_str)) or is_turn_off_triggered(act_clean, turn_offs_str, likes_str):
                        turn_off_hit = True

                spot_matched = False
                matched_spot = None
                if not turn_off_hit and (sub_intent != "none"):
                    from mechanics.social.persona.intimacy.logic import match_sensitive_spots
                    act_spot_text = (action_str or "").lower()
                    if "anal" in sub_intent:
                        likes_val_s = appr.get("act_likes") or appr.get("desires_and_kinks") or ""
                        likes_str_s = (
                            ", ".join(str(x) for x in likes_val_s).lower()
                            if isinstance(likes_val_s, (list, tuple))
                            else str(likes_val_s).lower()
                        )
                        if "anal" in likes_str_s or "backdoor" in likes_str_s:
                            spot_matched = True
                            matched_spot = "Anal Intimacy"
                    if not spot_matched:
                        m_spots = match_sensitive_spots(act_spot_text, appr.get("sensitive_spots"))
                        if m_spots:
                            spot_matched = True
                            matched_spot = m_spots[0]

                p_cl = {
                    "act_type": mapped_type,
                    "player_stimulated": sub_intent in ("intercourse", "oral_receive", "oral_mutual", "manual_receive", "anal_receive"),
                    "partner_stimulated": (not turn_off_hit) and (sub_intent in ("intercourse", "oral_give", "oral_mutual", "manual_give", "anal_give")),
                    "sensitive_spot_matched": spot_matched,
                    "matched_spot": matched_spot,
                    "turn_off_triggered": turn_off_hit,
                }
            else:
                p_cl = {
                    "act_type": "none",
                    "player_stimulated": False,
                    "partner_stimulated": False,
                    "sensitive_spot_matched": False,
                    "matched_spot": None,
                    "turn_off_triggered": False,
                }
            partner_classifications[n_k] = p_cl
    else:
        for n_k, n_d, pc in partner_actor_tuples:
            is_targeted = named_in_act[n_k] if any_named_in_act else True
            is_in_nar = is_name_in_turn(n_k, turn_low)
            other_names = [t[0] for t in partner_actor_tuples if t[0] != n_k]
            restrict_to_scoped_act = (
                len(partner_actor_tuples) > 1
                and any_act_genital_or_cont
                and not act_has_genital_or_cont.get(n_k, False)
            )
            scoped_nar = (
                ""
                if restrict_to_scoped_act
                else (
                    scope_text_to_partner(narrative_str, n_k, other_names)
                    if (narrative_str and is_in_nar and is_targeted and other_names)
                    else (narrative_str if (is_in_nar and is_targeted) else "")
                )
            )
            p_cl = classify_intimate_act(
                action_str=scoped_acts[n_k],
                intimate_contact_str="" if restrict_to_scoped_act else (curr_ic if is_targeted else ""),
                player_name=player_name,
                partner_name=n_k,
                partner_contact=pc,
                narrative_str=scoped_nar
            )
            if any_named_in_act and not is_targeted:
                p_cl["partner_stimulated"] = False
                p_cl["player_stimulated"] = False

            partner_classifications[n_k] = p_cl

    primary_class = partner_classifications[partner_name]

    # Resolve dominant intimate act across participants
    act_type = primary_class["act_type"]
    if act_type in ("none", "foreplay_nongenital"):
        for cl in partner_classifications.values():
            if cl["act_type"] not in ("none", "foreplay_nongenital"):
                act_type = cl["act_type"]
                break

    # Climax state tracking
    climax_st = physical_state.setdefault("climax_state", {"partner_climaxed": False, "player_climaxed": False})
    partner_climaxes = climax_st.setdefault("partner_climaxes", {})
    if "partner_climaxed" in climax_st and not partner_climaxes:
        partner_climaxes[partner_name] = bool(climax_st["partner_climaxed"])
    for t in partner_actor_tuples:
        partner_climaxes.setdefault(t[0], False)

    in_refr, _ = is_in_refractory_cooldown(session or {}, physical_state)
    refr_partners_existing = curr_excitement.get("refractory_partners") if isinstance(curr_excitement.get("refractory_partners"), dict) else {}

    if curr_excitement.get("active") is False and not curr_excitement.get("premature_finish", False):
        keep_pl_climaxed = bool(in_refr and curr_excitement.get("player_in_refractory") and not is_female_player)
        climax_st["player_climaxed"] = keep_pl_climaxed
        for k in partner_climaxes:
            partner_climaxes[k] = bool(in_refr and refr_partners_existing.get(k, False))
        climax_st["partner_climaxed"] = any(partner_climaxes.values())
        p_data["meter"] = 100 if keep_pl_climaxed else 0
        p_data["delta"] = 0
        p_data["idle_turns"] = 0
        p_data["status"] = "💥 Climaxed (Spent)" if keep_pl_climaxed else "Warming Up"
        for t in partner_actor_tuples:
            t[1]["meter"] = 0
            t[1]["delta"] = 0
            t[1]["idle_turns"] = 0
            t[1]["turn_off_strikes"] = 0
            t[1]["status"] = "Warming Up"
        curr_excitement["turn_off_terminated"] = False

    is_sensual_action = bool(
        (matches_boundary(act_low, SENSUAL_MAINTENANCE_KEYWORDS)
        or any(matches_boundary(s.lower(), SENSUAL_MAINTENANCE_KEYWORDS) for s in scoped_acts.values() if s))
        and not any(neg in act_low for neg in ("without touching", "without kissing", "step away", "look away", "silently without", "awkward"))
    )

    player_already_climaxed = bool(climax_st.get("player_climaxed"))
    if curr_excitement.get("player_in_refractory") is not None:
        player_in_refr = bool(in_refr and curr_excitement.get("player_in_refractory"))
    else:
        player_in_refr = bool(in_refr and (player_already_climaxed or "ongoing for player" not in curr_ic_low))
    male_spent = (not is_female_player) and (player_already_climaxed or player_in_refr)
    refractory_downgraded = bool(
        male_spent and (
            sub_intent in ("intercourse", "anal_give")
            or act_type in ("penetrative", "anal_give")
        )
    )
    effective_sub_intent = "foreplay" if refractory_downgraded else (sub_intent or "")
    if refractory_downgraded:
        act_type = "foreplay_nongenital"

    player_stimulated = any(cl["player_stimulated"] for cl in partner_classifications.values())
    _ev_arousal_mult = 1.0
    if isinstance(session, dict) and session.get("id"):
        try:
            from mechanics.world.world_events.modifiers import compute_arousal_event_multiplier
            _snap_ev = session.get("_world_events_snapshot") or db.get_world_events_snapshot(int(session["id"]))
            _ev_arousal_mult = compute_arousal_event_multiplier(_snap_ev, location_node_id=str(session.get("current_node_id") or ""))
        except Exception:
            _ev_arousal_mult = 1.0
    any_partner_stimulated_now = any(cl.get("partner_stimulated") for cl in partner_classifications.values())
    targeted_parts_turn = detect_targeted_anatomy_parts(action_str, act_type=act_type, sub_intent=sub_intent or "")
    eff_partner_count = int(partner_count or len(partner_actor_tuples) or 1)
    if has_bystanders is None:
        _pl_nm_l = player_name.strip().lower()
        _active_partner_names_l = {str(t[0] or "").strip().lower() for t in partner_actor_tuples if t[0]}
        _room_chars = (session.get("npcs_present") or session.get("current_npcs") or []) if isinstance(session, dict) else []
        eff_has_bystanders = any(
            (isinstance(rc, dict) and str(rc.get("name") or "").strip().lower() not in _active_partner_names_l and str(rc.get("name") or "").strip().lower() != _pl_nm_l)
            or (isinstance(rc, str) and rc.strip().lower() not in _active_partner_names_l and rc.strip().lower() != _pl_nm_l)
            for rc in (_room_chars if isinstance(_room_chars, list) else [])
        )
    else:
        eff_has_bystanders = bool(has_bystanders)

    partner_anatomy_mods: Dict[str, Dict[str, Any]] = {}
    partner_pref_mods: Dict[str, Dict[str, Any]] = {}
    triggered_body_preferences: List[Dict[str, Any]] = []
    triggered_intimate_discoveries: List[Dict[str, str]] = []
    for n_k_a, n_d_a, pc_a in partner_actor_tuples:
        cl_a = partner_classifications[n_k_a]
        is_explicit_untargeted = any_named_in_act and not named_in_act.get(n_k_a, False)
        scoped_act_a = "" if is_explicit_untargeted else (scoped_acts.get(n_k_a) or action_str)
        partner_targeted_parts = (
            set()
            if is_explicit_untargeted
            else (
                detect_targeted_anatomy_parts(scoped_act_a, act_type=act_type, sub_intent=sub_intent or "")
                if scoped_act_a != action_str
                else targeted_parts_turn
            )
        )
        anat_res = evaluate_anatomy_excitement_modifiers(
            player_char=player_char,
            partner_contact=pc_a,
            act_type=act_type,
            action_str=scoped_act_a,
            sub_intent=sub_intent or "",
            partner_classification=cl_a,
            refractory_downgraded=refractory_downgraded,
            targeted_parts=partner_targeted_parts,
        )
        partner_anatomy_mods[n_k_a] = anat_res
        if not is_explicit_untargeted:
            for tp in anat_res.get("triggered_preferences") or []:
                triggered_body_preferences.append(tp)

        if is_explicit_untargeted:
            pref_res = {
                "player_multiplier": 1.0,
                "partner_multiplier": 1.0,
                "matched_desires": [],
                "matched_kinks": [],
                "matched_liked_acts": [],
                "matched_disliked_acts": [],
                "giving_service_reward": False,
                "openness_cue": "",
                "multipartner_cue": "",
                "discoveries": [],
            }
        else:
            pc_dict = pc_a if isinstance(pc_a, dict) else {}
            eff_score_a = int(relationship_score if relationship_score is not None else (pc_dict.get("relationship_score", pc_dict.get("score", 0)) or 0))
            eff_track_a = str(relationship_track if relationship_track is not None else (pc_dict.get("relationship_track") or pc_dict.get("track") or "platonic"))
            eff_shared_a = int(
                shared_intimate_count
                if shared_intimate_count is not None
                else ((pc_dict.get("shared_intimacy_stats") or {}).get("shared_encounters") or len(pc_dict.get("gameplay_intimate_events") or []) or 0)
            )
            eff_hostile_a = bool(is_hostile if is_hostile is not None else (str(pc_dict.get("disposition") or "").strip().lower() == "hostile"))
            pref_res = evaluate_preference_excitement_modifiers(
                partner_contact=pc_a,
                act_type=cl_a.get("act_type") or act_type,
                action_str=scoped_act_a,
                sub_intent=sub_intent or "",
                partner_classification=cl_a,
                relationship_score=eff_score_a,
                relationship_track=eff_track_a,
                shared_intimate_count=eff_shared_a,
                is_hostile=eff_hostile_a,
                has_bystanders=eff_has_bystanders,
                partner_count=eff_partner_count,
                partner_current_excitement=int(n_d_a.get("meter", 0) or 0),
            )
        partner_pref_mods[n_k_a] = pref_res
        for disc_rec in pref_res.get("discoveries") or []:
            triggered_intimate_discoveries.append(disc_rec)

    p_anat_cands: List[float] = []
    p_pref_cands: List[float] = []
    for n_k_a, _, _ in partner_actor_tuples:
        cl_a = partner_classifications[n_k_a]
        if cl_a.get("player_stimulated"):
            cand_pm = float(partner_anatomy_mods[n_k_a].get("player_multiplier", 1.0))
            if cand_pm != 1.0:
                p_anat_cands.append(cand_pm)
            cand_pref = float(partner_pref_mods[n_k_a].get("player_multiplier", 1.0))
            if cand_pref != 1.0:
                p_pref_cands.append(cand_pref)
    p_anatomy_mult = round(sum(p_anat_cands) / len(p_anat_cands), 4) if p_anat_cands else 1.0
    p_pref_mult = round(sum(p_pref_cands) / len(p_pref_cands), 4) if p_pref_cands else 1.0

    p_delta = 0
    if male_spent:
        p_delta = 0
    elif player_stimulated:
        p_data["idle_turns"] = 0
        p_data["aroused_turns"] = 3
        base_p = 18 if act_type in ("penetrative", "anal_give", "anal_receive", "oral_receive", "oral_mutual") else 14
        p_delta = calculate_excitement_delta(
            base_p,
            p_data.get("endurance", 10),
            event_arousal_multiplier=_ev_arousal_mult,
            anatomy_multiplier=p_anatomy_mult,
            preference_multiplier=p_pref_mult,
        )
    elif is_sensual_action:
        p_data["idle_turns"] = 0
        p_data["aroused_turns"] = 3
        p_delta = 0
    else:
        # Non-stimulating action for player: check grace period and gradual decay
        if p_data.get("meter", 0) > 0:
            p_data["idle_turns"] = p_data.get("idle_turns", 0) + 1
            if p_data["idle_turns"] <= INTIMATE_DECAY_GRACE_TURNS:
                p_delta = 0
            else:
                p_has_aroused = _actor_has_aroused(player_char, p_data)
                decay_rate = AROUSED_DECAY_PER_TURN if p_has_aroused else BASE_DECAY_PER_TURN
                p_delta = -min(p_data.get("meter", 0), decay_rate)
            if any_partner_stimulated_now:
                p_data["aroused_turns"] = 3
            elif p_data.get("aroused_turns", 0) > 0:
                p_data["aroused_turns"] = max(0, p_data["aroused_turns"] - 1)
        else:
            p_delta = 0
            if any_partner_stimulated_now:
                p_data["aroused_turns"] = 3
            elif p_data.get("aroused_turns", 0) > 0:
                p_data["aroused_turns"] = max(0, p_data["aroused_turns"] - 1)
            else:
                p_data["aroused_turns"] = 0

    p_data["delta"] = p_delta
    p_data["meter"] = max(0, min(100, p_data.get("meter", 0) + p_delta))

    # Process deltas, baselines, and climaxes for all partners
    newly_climaxed_partners: List[str] = []
    any_turn_off_terminated = False
    from mechanics.social.persona.intimacy.constants import (
        FOREPLAY_SPOT_WARMUP_BONUS,
        FOREPLAY_SPOT_WARMUP_CAP,
        GIVING_SERVICE_NPC_BONUS,
        GIVING_SERVICE_NPC_CAP,
        TURN_OFF_EXCITEMENT_DROP,
    )

    for n_k, n_d, pc in partner_actor_tuples:
        cl = partner_classifications[n_k]
        pref_mod_n = partner_pref_mods.get(n_k, {})
        p_already_climaxed = bool(partner_climaxes.get(n_k, False))
        is_targeted_p = named_in_act.get(n_k, False) if any_named_in_act else True
        n_gender = str(pc.get("gender") or (pc.get("appearance") or {}).get("gender") or "Female").lower()
        is_female_npc = "male" not in n_gender or "female" in n_gender
        male_npc_spent = (not is_female_npc) and p_already_climaxed

        n_delta = 0
        secondary_only = False
        if cl.get("turn_off_triggered"):
            cur_m = int(n_d.get("meter", 0) or 0)
            n_delta = -min(cur_m, TURN_OFF_EXCITEMENT_DROP)
            n_d["turn_off_strikes"] = int(n_d.get("turn_off_strikes", 0) or 0) + 1
            n_d["idle_turns"] = n_d.get("idle_turns", 0) + 1
            if n_d.get("aroused_turns", 0) > 0:
                n_d["aroused_turns"] = max(0, n_d["aroused_turns"] - 1)
            if n_d["turn_off_strikes"] >= 2 or (action_check_margin is not None and action_check_margin <= -5):
                any_turn_off_terminated = True
        elif cl["partner_stimulated"]:
            n_d["idle_turns"] = 0
            n_d["aroused_turns"] = 3
            base_n = 14 if refractory_downgraded else (18 if act_type in ("penetrative", "anal_give", "anal_receive", "oral_give", "oral_mutual") else 14)
            n_anat_mult = float(partner_anatomy_mods.get(n_k, {}).get("partner_multiplier", 1.0))
            n_pref_mult = float(pref_mod_n.get("partner_multiplier", 1.0))
            n_delta = calculate_excitement_delta(
                base_n,
                n_d.get("endurance", 10),
                sensitive_spot_bonus=cl["sensitive_spot_matched"],
                event_arousal_multiplier=_ev_arousal_mult,
                anatomy_multiplier=n_anat_mult,
                preference_multiplier=n_pref_mult,
            )
        elif act_type == "foreplay_nongenital" and cl.get("sensitive_spot_matched") and (is_targeted_p or not any_named_in_act) and not male_npc_spent:
            cur_m = int(n_d.get("meter", 0) or 0)
            if cur_m < FOREPLAY_SPOT_WARMUP_CAP:
                n_delta = min(FOREPLAY_SPOT_WARMUP_CAP - cur_m, FOREPLAY_SPOT_WARMUP_BONUS)
            else:
                n_delta = 0
            n_d["idle_turns"] = 0
            n_d["aroused_turns"] = 3
            secondary_only = True
        elif pref_mod_n.get("giving_service_reward") and not male_npc_spent:
            cur_m = int(n_d.get("meter", 0) or 0)
            if cur_m < GIVING_SERVICE_NPC_CAP:
                n_delta = min(GIVING_SERVICE_NPC_CAP - cur_m, GIVING_SERVICE_NPC_BONUS)
            else:
                n_delta = 0
            n_d["idle_turns"] = 0
            n_d["aroused_turns"] = 3
            secondary_only = True
        elif len(partner_actor_tuples) > 1 and act_type not in ("none", "foreplay_nongenital"):
            # Passive spectator warmth or secondary foreplay warmth in active multi-partner scene
            spot_bonus = 6 if (is_targeted_p and cl.get("sensitive_spot_matched")) else 0
            cap_limit = 90 if spot_bonus else 80
            if n_d["meter"] < cap_limit:
                n_delta = min(cap_limit - n_d["meter"], 4 + spot_bonus)
            else:
                n_delta = 0
            n_d["idle_turns"] = 0
            n_d["aroused_turns"] = 3
        elif is_sensual_action and (is_targeted_p or not any_named_in_act):
            n_d["idle_turns"] = 0
            n_d["aroused_turns"] = 3
            n_delta = 0
        else:
            if male_npc_spent:
                n_delta = 0
            elif n_d.get("meter", 0) > 0:
                n_d["idle_turns"] = n_d.get("idle_turns", 0) + 1
                if n_d["idle_turns"] <= INTIMATE_DECAY_GRACE_TURNS:
                    n_delta = 0
                else:
                    n_has_aroused = _actor_has_aroused(pc, n_d)
                    n_decay = AROUSED_DECAY_PER_TURN if n_has_aroused else BASE_DECAY_PER_TURN
                    n_delta = -min(n_d.get("meter", 0), n_decay)
                if cl.get("player_stimulated"):
                    n_d["aroused_turns"] = 3
                elif n_d.get("aroused_turns", 0) > 0:
                    n_d["aroused_turns"] = max(0, n_d["aroused_turns"] - 1)
            else:
                n_delta = 0
                if cl.get("player_stimulated"):
                    n_d["aroused_turns"] = 3
                elif n_d.get("aroused_turns", 0) > 0:
                    n_d["aroused_turns"] = max(0, n_d["aroused_turns"] - 1)
                else:
                    n_d["aroused_turns"] = 0

        # Multi-climax reset to 35% hypersensitive baseline if already peaked earlier (female anatomy)
        # Male anatomy stays spent at 100%
        if male_npc_spent:
            n_delta = 0
            n_d["delta"] = 0
            n_d["meter"] = 100
            n_d["status"] = "💥 Climaxed (Spent)"
        else:
            if p_already_climaxed and n_d["meter"] >= 100 and cl["partner_stimulated"]:
                if is_female_npc:
                    n_d["meter"] = 35

            n_d["delta"] = n_delta
            n_d["meter"] = max(0, min(100, n_d["meter"] + n_delta))

            # Partner climax check: strictly gauge-driven (>= 100% or >= 80% on explicit finisher phrase)
            act_low = str(action_str or "").lower()
            explicit_partner_finisher = any(
                p in act_low for p in (
                    "over the edge", "to climax", "into climax", "reach climax",
                    "make her cum", "make him cum", "finish together", "climax together"
                )
            )
            partner_newly_climaxed = False
            if act_type != "foreplay_nongenital" and not male_npc_spent and not secondary_only:
                if cl["partner_stimulated"] and (n_d["meter"] >= 100 or (n_d["meter"] >= 80 and explicit_partner_finisher)):
                    partner_newly_climaxed = True
                elif n_delta > 0 and n_d["meter"] >= 100 and not p_already_climaxed:
                    partner_newly_climaxed = True

            if partner_newly_climaxed:
                partner_climaxes[n_k] = True
                n_d["meter"] = 100
                n_d["climaxes_count"] = n_d.get("climaxes_count", 0) + 1
                n_d["status"] = "💥 Climax Reached!"
                newly_climaxed_partners.append(n_k)
            elif cl.get("turn_off_triggered"):
                n_d["status"] = "Turned Off / Recoiling ⚠️"
            elif p_already_climaxed and not cl["partner_stimulated"] and n_d.get("idle_turns", 0) == 0 and not male_npc_spent:
                n_d["status"] = "Trembling from Aftershocks 🔥"
            elif n_delta < 0:
                rate_lbl = 5 if abs(n_delta) == 5 or (n_delta < 0 and _actor_has_aroused(pc, n_d)) else 10
                n_d["status"] = f"Cooling Down ⏳ (-{rate_lbl}%)" if n_d["meter"] > 0 else "Cooled Down"
            elif n_d.get("idle_turns", 0) == 1 and n_d["meter"] > 0 and not cl["partner_stimulated"] and not is_sensual_action:
                n_d["status"] = "Lingering Heat 🔥"
            elif n_d.get("idle_turns", 0) == 2 and n_d["meter"] > 0 and not cl["partner_stimulated"] and not is_sensual_action:
                n_d["status"] = "Catching Breath 💨"
            elif is_sensual_action and (is_targeted_p or not any_named_in_act) and n_d["meter"] > 0 and not cl["partner_stimulated"]:
                if n_d["meter"] >= 75:
                    n_d["status"] = "On the Brink 🔥"
                elif n_d["meter"] >= 50:
                    n_d["status"] = "Deepening Pleasure"
                else:
                    n_d["status"] = "Sensual Warmth 🔥"
            elif not cl["partner_stimulated"] and not is_targeted_p and len(partner_actor_tuples) > 1 and n_d.get("idle_turns", 0) == 0 and not male_npc_spent:
                n_d["status"] = "Watching with Arousal"
            elif n_d["meter"] >= 75:
                n_d["status"] = "On the Brink 🔥"
            elif n_d["meter"] >= 50:
                n_d["status"] = "Deepening Pleasure"
            elif n_d["meter"] == 0 and n_d.get("idle_turns", 0) >= 3:
                n_d["status"] = "Cooled Down"
            else:
                n_d["status"] = "Arousal Building"

    # Re-evaluate unsatisfied partners dynamically if premature finish was active
    if curr_excitement.get("premature_finish"):
        still_unsatisfied = [
            t[0] for t in partner_actor_tuples
            if not partner_climaxes.get(t[0], False) and t[1]["meter"] < 100
        ]
        if not still_unsatisfied:
            curr_excitement["premature_finish"] = False
            curr_excitement["partner_demanded"] = False
            curr_excitement["unsatisfied_partner"] = ""
            curr_excitement["unsatisfied_partners"] = []
        else:
            curr_excitement["unsatisfied_partner"] = still_unsatisfied[0]
            curr_excitement["unsatisfied_partners"] = still_unsatisfied

    # Synchronize aggregate partner climax state
    climax_st["partner_climaxed"] = any(partner_climaxes.values())
    curr_excitement["all_partners_climaxed"] = all(partner_climaxes.values())
    simultaneous_partner_climax = (
        len(partner_actor_tuples) >= 2 and
        len(newly_climaxed_partners) >= 2
    )
    curr_excitement["simultaneous_partner_climax"] = simultaneous_partner_climax

    curr_excitement["active"] = True
    prev_last_act = str(curr_excitement.get("last_act") or "").strip().lower()
    curr_ic_low = str(physical_state.get("intimate_contact") or "").lower()
    if (
        act_type in ("none", "foreplay_nongenital")
        and prev_last_act not in ("", "none", "foreplay_nongenital")
        and curr_ic_low not in ("", "none")
        and not any(k in curr_ic_low for k in ("kissing", "cuddling", "aftercare", "holding hands"))
    ):
        curr_excitement["last_act"] = prev_last_act
    else:
        curr_excitement["last_act"] = act_type

    any_spot_matched = any(cl.get("sensitive_spot_matched") for cl in partner_classifications.values())
    matched_spots = [
        f"{n_k}: {cl['matched_spot']}" if len(partner_classifications) > 1 else str(cl["matched_spot"])
        for n_k, cl in partner_classifications.items()
        if cl.get("sensitive_spot_matched") and cl.get("matched_spot")
    ]
    matched_spot_val = ", ".join(matched_spots) if matched_spots else None
    curr_excitement["sensitive_spot_hit"] = matched_spot_val or ""

    act_low = str(action_str or "").lower()
    explicit_player_finisher = any(
        p in act_low for p in (
            "finish inside", "pull out and finish", "spills inside", "release inside",
            "toward your own release", "into your own release", "finish together",
            "climax together", "reach your climax", "reach my climax"
        )
    )

    player_newly_climaxed = False
    # Check Player Climax
    if male_spent:
        p_data["status"] = "💥 Climaxed (Spent)"
    elif (p_data["meter"] >= 100 or (p_data["meter"] >= 80 and explicit_player_finisher)) and player_stimulated and act_type != "foreplay_nongenital":
        player_newly_climaxed = True
        climax_st["player_climaxed"] = True
        p_data["climaxes_count"] += 1

        if is_female_player:
            # Female multi-climax: drops to warm hypersensitive baseline
            p_data["meter"] = 35
            p_data["status"] = "💥 Climaxed (Hypersensitive)"
        else:
            # Male refractory stop
            p_data["meter"] = 100
            p_data["status"] = "💥 Climaxed (Spent)"
            unsatisfied = [
                t[0] for t in partner_actor_tuples
                if not partner_climaxes.get(t[0], False) and t[1]["meter"] < 100
            ]
            if unsatisfied:
                curr_excitement["premature_finish"] = True
                unsatisfied_contacts = [t[2] for t in partner_actor_tuples if t[0] in unsatisfied]
                curr_excitement["partner_demanded"] = any(roll_partner_demand(c) for c in unsatisfied_contacts) if unsatisfied_contacts else roll_partner_demand(primary_contact)
                curr_excitement["unsatisfied_partner"] = unsatisfied[0]
                curr_excitement["unsatisfied_partners"] = unsatisfied
            else:
                curr_excitement["premature_finish"] = False
                curr_excitement["partner_demanded"] = False
                curr_excitement["unsatisfied_partner"] = ""
                curr_excitement["unsatisfied_partners"] = []

            cooldown_dur = calculate_refractory_duration(p_data.get("endurance", 10))
            curr_day = (session or {}).get("current_day", 1)
            curr_min = (session or {}).get("current_minute", 480)
            target_abs = (curr_day * 1440) + curr_min + cooldown_dur
            curr_turn = int((session or {}).get("turn_count") or len((session or {}).get("history") or []) or 0)
            curr_excitement["refractory_until_minute"] = target_abs
            curr_excitement["refractory_until_turn"] = curr_turn + 3
            curr_excitement["cooldown_notified"] = False
            curr_excitement["player_in_refractory"] = True
    elif p_delta < 0:
        p_rate_lbl = 5 if abs(p_delta) == 5 or (p_delta < 0 and _actor_has_aroused(player_char, p_data)) else 10
        p_data["status"] = f"Cooling Down ⏳ (-{p_rate_lbl}%)" if p_data["meter"] > 0 else "Cooled Down"
    elif p_data.get("idle_turns", 0) == 1 and p_data["meter"] > 0 and not player_stimulated and not is_sensual_action:
        p_data["status"] = "Lingering Heat 🔥"
    elif p_data.get("idle_turns", 0) == 2 and p_data["meter"] > 0 and not player_stimulated and not is_sensual_action:
        p_data["status"] = "Catching Breath 💨"
    elif is_sensual_action and p_data["meter"] > 0 and not player_stimulated:
        if p_data["meter"] >= 75:
            p_data["status"] = "On the Brink 🔥"
        elif p_data["meter"] >= 50:
            p_data["status"] = "Maintaining Rhythm"
        else:
            p_data["status"] = "Sensual Warmth 🔥"
    elif p_data["meter"] >= 75:
        p_data["status"] = "On the Brink 🔥"
    elif p_data["meter"] >= 50:
        p_data["status"] = "Maintaining Rhythm"
    elif p_data["meter"] == 0 and p_data.get("idle_turns", 0) >= 3:
        p_data["status"] = "Cooled Down"
    else:
        p_data["status"] = "Arousal Building"

    any_male_partner_climaxed = any(
        t[0] in newly_climaxed_partners
        and "male" in str(t[2].get("gender") or (t[2].get("appearance") or {}).get("gender") or "Female").lower()
        and "female" not in str(t[2].get("gender") or (t[2].get("appearance") or {}).get("gender") or "Female").lower()
        for t in partner_actor_tuples
    )
    all_partners_climaxed = bool(
        partner_actor_tuples and all(partner_climaxes.get(t[0], False) for t in partner_actor_tuples)
    )
    both_climaxed_now = bool(climax_st.get("player_climaxed") and all_partners_climaxed)
    refr_partners_map = curr_excitement.setdefault("refractory_partners", {})
    if both_climaxed_now:
        curr_excitement["player_in_refractory"] = True
        for t in partner_actor_tuples:
            if partner_climaxes.get(t[0], False):
                refr_partners_map[t[0]] = True
    elif any_male_partner_climaxed:
        curr_excitement.setdefault("player_in_refractory", False)
        for t in partner_actor_tuples:
            if (
                t[0] in newly_climaxed_partners
                and "male" in str(t[2].get("gender") or (t[2].get("appearance") or {}).get("gender") or "Female").lower()
                and "female" not in str(t[2].get("gender") or (t[2].get("appearance") or {}).get("gender") or "Female").lower()
            ):
                refr_partners_map[t[0]] = True
    if (both_climaxed_now or any_male_partner_climaxed) and not curr_excitement.get("refractory_until_minute"):
        p_end = (primary_contact.get("stats") or {}).get("endurance") or primary_contact.get("endurance") or 10 if isinstance(primary_contact, dict) else 10
        cooldown_dur = calculate_refractory_duration(p_end)
        curr_day = (session or {}).get("current_day", 1)
        curr_min = (session or {}).get("current_minute", 480)
        target_abs = (curr_day * 1440) + curr_min + cooldown_dur
        curr_excitement["refractory_until_minute"] = target_abs
        curr_excitement["cooldown_notified"] = False

    mutual_group_climax = (
        player_newly_climaxed and
        len(partner_actor_tuples) >= 2 and
        (len(newly_climaxed_partners) >= 2 or (len(newly_climaxed_partners) >= 1 and all(partner_climaxes.values())))
    )
    curr_excitement["mutual_group_climax"] = mutual_group_climax

    all_cooled_down = bool(
        p_data.get("meter", 0) == 0
        and all(t[1].get("meter", 0) == 0 for t in partner_actor_tuples)
        and (p_data.get("idle_turns", 0) >= 3 or all(t[1].get("idle_turns", 0) >= 3 for t in partner_actor_tuples))
    )
    curr_excitement["all_cooled_down"] = all_cooled_down

    partner_meters_list = [
        {
            "name": t[0],
            "meter": t[1]["meter"],
            "delta": t[1].get("delta", 0),
            "status": t[1].get("status", "Warming Up"),
            "climaxed": bool(partner_climaxes.get(t[0], False)),
            "idle_turns": t[1].get("idle_turns", 0),
        }
        for t in partner_actor_tuples
    ]

    curr_excitement["turn_off_terminated"] = any_turn_off_terminated

    return {
        "active": not any_turn_off_terminated,
        "act_type": act_type,
        "player_meter": p_data["meter"],
        "player_delta": p_delta,
        "partner_meter": primary_n_data["meter"],
        "partner_delta": primary_n_data["delta"],
        "sensitive_spot_matched": any_spot_matched,
        "matched_spot": matched_spot_val,
        "partner_climaxed": climax_st.get("partner_climaxed", False),
        "player_climaxed": climax_st.get("player_climaxed", False),
        "premature_finish": curr_excitement.get("premature_finish", False),
        "partner_demanded": curr_excitement.get("partner_demanded", False),
        "unsatisfied_partner": curr_excitement.get("unsatisfied_partner", ""),
        "unsatisfied_partners": curr_excitement.get("unsatisfied_partners", []),
        "player_name": player_name,
        "partner_name": partner_name,
        "actors": actors,
        "partner_meters": partner_meters_list,
        "partner_climaxes": partner_climaxes,
        "all_partners_climaxed": all_partners_climaxed,
        "player_in_refractory": curr_excitement.get("player_in_refractory", False),
        "refractory_partners": dict(curr_excitement.get("refractory_partners") or {}),
        "simultaneous_partner_climax": simultaneous_partner_climax,
        "mutual_group_climax": mutual_group_climax,
        "all_cooled_down": all_cooled_down,
        "player_idle_turns": p_data.get("idle_turns", 0),
        "player_stimulated": bool(player_stimulated),
        "is_sensual_action": bool(is_sensual_action),
        "any_partner_stimulated": bool(any(cl.get("partner_stimulated") for cl in partner_classifications.values())),
        "refractory_downgraded": bool(refractory_downgraded),
        "effective_sub_intent": effective_sub_intent,
        "anatomy_modifiers": partner_anatomy_mods,
        "preference_modifiers": partner_pref_mods,
        "triggered_body_preferences": triggered_body_preferences,
        "triggered_intimate_discoveries": triggered_intimate_discoveries,
        "turn_off_terminated": any_turn_off_terminated,
    }


def format_compact_discord_meter(
    player_name: str,
    player_meter: int,
    partner_name: str = "",
    partner_meter: int = 0,
    partner_climaxed: bool = False,
    actors: Optional[Dict[str, Any]] = None,
    partner_meters: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Renders the compact Discord progress string. Supports single or multiple partners.
    Single: 💋 Artemiusz: 52% [▰▰▰▰▰▱▱▱▱▱] | Kana: 84% [▰▰▰▰▰▰▰▰▱▱] 🔥
    Multi:  💋 Artemiusz: 52% [▰▰▰▰▰▱▱▱▱▱] | Kana: 84% [▰▰▰▰▰▰▰▰▱▱] 🔥 | Elena: 40% [▰▰▰▰▱▱▱▱▱▱]
    """
    def _bar(val: int) -> str:
        filled = max(0, min(10, val // 10))
        return "▰" * filled + "▱" * (10 - filled)

    p_short = player_name[:10]
    p_bar = _bar(player_meter)
    p_st = str((actors or {}).get(player_name, {}).get("status", "")).lower()
    p_flame = " ⏳" if "cooling down" in p_st else (" 🔥" if player_meter >= 75 else "")
    lead_part = f"💋 {p_short}: {player_meter}% [{p_bar}]{p_flame}"

    partners: List[Dict[str, Any]] = []
    if partner_meters and isinstance(partner_meters, list):
        partners = partner_meters
    elif actors and isinstance(actors, dict):
        p_low = player_name.strip().lower()
        for k, v in actors.items():
            if str(k).strip().lower() != p_low and isinstance(v, dict):
                partners.append({
                    "name": str(k),
                    "meter": int(v.get("meter", 0) or 0),
                    "status": str(v.get("status", "")),
                    "climaxed": "climax" in str(v.get("status", "")).lower() or int(v.get("meter", 0) or 0) >= 100
                })

    if len(partners) > 1:
        parts = [lead_part]
        for p in partners:
            p_nm = str(p.get("name", "Partner"))[:10]
            p_val = int(p.get("meter", 0) or 0)
            p_cl = bool(p.get("climaxed", False))
            p_st = str(p.get("status", "")).lower()
            if (p_cl and p_val >= 100) or "climax" in p_st:
                flame = " 💥"
            elif "recoil" in p_st or "turned off" in p_st:
                flame = " ⚠️"
            elif "cooling down" in p_st:
                flame = " ⏳"
            elif p_val >= 75:
                flame = " 🔥"
            else:
                flame = ""
            parts.append(f"💖 {p_nm}: {p_val}% [{_bar(p_val)}]{flame}")
        inline_str = " | ".join(parts)
        if len(inline_str) <= 85:
            return inline_str
        return "\n".join(parts)

    n_nm = (partner_name or (partners[0]["name"] if partners else "Partner"))[:10]
    n_val = partner_meter if partner_name else (partners[0]["meter"] if partners else 0)
    n_cl = partner_climaxed if partner_name else (partners[0].get("climaxed", False) if partners else False)
    n_st = str(partners[0].get("status", "")).lower() if partners else ""
    if (n_cl and n_val >= 100) or "climax" in n_st:
        flame = " 💥"
    elif "recoil" in n_st or "turned off" in n_st:
        flame = " ⚠️"
    elif "cooling down" in n_st:
        flame = " ⏳"
    elif n_val >= 75:
        flame = " 🔥"
    else:
        flame = ""

    return f"{lead_part} | {n_nm}: {n_val}% [{_bar(n_val)}]{flame}"


def check_and_resolve_refractory_clock(
    session: Dict[str, Any],
    physical_state: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    Checks if active refractory cooldown in in-game clock has elapsed.
    Returns (is_recovered_now, toast_message).
    """
    excitement = physical_state.get("excitement", {}) if isinstance(physical_state, dict) else {}
    target_abs = excitement.get("refractory_until_minute") or (physical_state.get("refractory_until_minute") if isinstance(physical_state, dict) else None)
    target_turn = excitement.get("refractory_until_turn") or (physical_state.get("refractory_until_turn") if isinstance(physical_state, dict) else None)
    if not target_abs and not target_turn:
        return False, None

    if excitement.get("cooldown_notified"):
        return False, None

    curr_day = session.get("current_day", 1)
    curr_min = session.get("current_minute", 480)
    current_abs = (curr_day * 1440) + curr_min
    curr_turn = int(session.get("turn_count") or len(session.get("history") or []) or 0)

    is_elapsed = False
    if target_abs and current_abs >= int(target_abs):
        is_elapsed = True
    elif not target_abs and target_turn and curr_turn >= int(target_turn):
        is_elapsed = True

    if is_elapsed:
        excitement["cooldown_notified"] = True
        excitement["refractory_until_minute"] = None
        excitement["refractory_until_turn"] = 0
        excitement["player_in_refractory"] = False
        excitement["refractory_partners"] = {}
        if isinstance(physical_state, dict):
            physical_state["refractory_until_minute"] = None
            physical_state["refractory_until_turn"] = 0
        excitement["premature_finish"] = False
        excitement["partner_demanded"] = False
        excitement["unsatisfied_partner"] = ""
        excitement["unsatisfied_partners"] = []
        if isinstance(physical_state, dict):
            climax_st = physical_state.get("climax_state")
            if isinstance(climax_st, dict):
                climax_st["player_climaxed"] = False
                if not excitement.get("active", False):
                    climax_st["partner_climaxed"] = False
                    if "partner_climaxes" in climax_st and isinstance(climax_st["partner_climaxes"], dict):
                        for k in climax_st["partner_climaxes"]:
                            climax_st["partner_climaxes"][k] = False
            else:
                physical_state["climax_state"] = {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}}
            ic_now = str(physical_state.get("intimate_contact") or "")
            if "player reached climax spent" in ic_now.lower():
                physical_state["intimate_contact"] = re.sub(
                    r"\s*\(player reached climax spent[^\)]*\)",
                    "",
                    ic_now,
                    flags=re.IGNORECASE
                ).strip()
        for a_dict in (excitement.get("actors") or {}).values():
            if isinstance(a_dict, dict):
                if not excitement.get("active", False) or int(a_dict.get("meter", 0) or 0) >= 100 or "spent" in str(a_dict.get("status", "")).lower():
                    a_dict["meter"] = 0
                    a_dict["delta"] = 0
                    a_dict["status"] = "Warming Up"
        toast = "⚡ **Stamina Recovered:** Fully rested and ready for intimacy."
        return True, toast

    return False, None


def is_in_refractory_cooldown(
    session: Dict[str, Any],
    physical_state: Dict[str, Any]
) -> Tuple[bool, int]:
    """
    Returns (is_active, minutes_remaining).
    """
    excitement = physical_state.get("excitement", {}) if isinstance(physical_state, dict) else {}
    target_abs = excitement.get("refractory_until_minute") or (physical_state.get("refractory_until_minute") if isinstance(physical_state, dict) else None)
    if target_abs:
        curr_day = session.get("current_day", 1)
        curr_min = session.get("current_minute", 480)
        current_abs = (curr_day * 1440) + curr_min
        if current_abs < target_abs:
            return True, target_abs - current_abs

    target_turn = excitement.get("refractory_until_turn") or (physical_state.get("refractory_until_turn") if isinstance(physical_state, dict) else None)
    if target_turn:
        curr_turn = int(session.get("turn_count") or len(session.get("history") or []) or 0)
        if curr_turn < int(target_turn):
            return True, max(1, (int(target_turn) - curr_turn) * 10)

    return False, 0


def format_refractory_status_tag(mins_remaining: int) -> str:
    """Formats clock-accurate male refractory recovery status effect."""
    return f"Refractory Recovery [{max(1, int(mins_remaining))} min]"


def format_partner_recovery_status_tag(mins_remaining: int, gender: str = "Female") -> str:
    """Formats clock-accurate partner recovery/satisfied status effect."""
    gen = str(gender or "Female").lower()
    if "male" in gen and "female" not in gen:
        return f"Refractory Recovery [{max(1, int(mins_remaining))} min]"
    return f"Satisfied [{max(1, int(mins_remaining))} min]"


INTIMATE_CHOICE_KEYWORDS = (
    # Penetrative & Rhythm
    "rhythm", "pace", "climax", "orgasm", "release", "thrust", "thrusts", "thrusting",
    "finish", "deeper", "hips", "pelvis", "ride", "riding", "straddle", "edge",
    "inside", "enter", "penetrate", "sheath", "hilt", "breed",
    # Oral Intimacy
    "lick", "licking", "tongue", "suck", "sucking", "suction", "taste", "tasting",
    "eat", "eating", "mouth", "lips", "lap", "kneel", "knees", "cunnilingus",
    "fellatio", "blowjob", "throat", "swallow", "crown",
    # Manual Intimacy
    "stroke", "stroking", "finger", "fingers", "fingering", "hand", "hands",
    "palm", "rub", "rubbing", "pump", "pumping", "circle", "circling", "handjob",
    "touch", "touching",
    # Anal Intimacy
    "rear", "anus", "anal", "anally", "backdoor", "rim", "rimming", "peg", "pegging",
    # Foreplay, Anatomy & Sensual Actions
    "praise", "dirty talk", "whisper", "caress", "caressing", "fondle", "fondling",
    "massage", "massaging", "squeeze", "cup", "tease", "teasing", "kiss", "kissing",
    "embrace", "hold", "pull close", "draw close", "undress", "strip", "clit",
    "core", "folds", "entrance", "shaft", "length", "cock", "pussy", "slit",
    "groin", "thighs", "legs", "breasts", "boobs", "chest", "nipples", "neck",
    "nape", "collarbone", "ear", "ears", "spine", "back", "shoulder", "shoulders",
    "waist", "stomach", "belly", "tail", "fur", "skin", "body", "pleasure",
    "please", "arousal", "intimate", "position", "shift", "guide", "continue"
)

# Narrow, unambiguous intimate vocabulary for classifying an action label as intimate
# OUTSIDE an active encounter (e.g. social/non-combat HP-damage gating). The broad
# INTIMATE_CHOICE_KEYWORDS list above contains generic words ("chest", "hand", "back",
# "hold", "enter", "edge", "eat", "ear") that, when substring-matched, misclassify
# physical/combat actions like "Disarm the chest trap" or "Search the room" as social.
UNAMBIGUOUS_INTIMATE_LABEL_KEYWORDS = (
    "kiss", "kisses", "kissing", "caress", "caresses", "caressing", "fondle", "fondling",
    "cuddle", "cuddling", "embrace", "embracing", "undress", "undressing", "make love",
    "making love", "seduce", "seducing", "foreplay", "climax", "orgasm",
    "cunnilingus", "fellatio", "blowjob", "handjob", "fingering", "rimming", "pegging",
    "clit", "pussy", "cock", "nipples", "breasts", "boobs", "groin", "anal", "anally",
    "intimate", "intimately", "arousal", "dirty talk", "pull close", "draw close",
    "hold her close", "hold him close", "hold them close",
    "fuck", "fucking", "fucked", "aftershocks", "aftercare", "thrusting",
    "straddle", "straddling", "mating press", "cowgirl", "missionary", "breed", "breeding", "creampie",
)


def is_intimate_action_label(label: str) -> bool:
    """Boundary-matched, Scunthorpe-sanitized check for unambiguously intimate action labels."""
    if not label:
        return False
    return matches_boundary(sanitize_scunthorpe_text(str(label).lower()), UNAMBIGUOUS_INTIMATE_LABEL_KEYWORDS)

INTIMATE_EXIT_KEYWORDS = (
    "slow your rhythm, gently withdraw",
    "gently withdraw, and hold",
    "ease back gently, pause",
    "pause to catch your breath",
    "step back gently, excuse yourself",
    "catch your breath with",
    "rest together in aftercare",
    "hold close in aftercare",
)


def _clean_spot_phrase(sensitive_spots: Any, is_kneeling: bool = False) -> str:
    """Extracts a clean, natural body-part phrase from sensitive_spots for choice blueprints."""
    spots_list: List[str] = []
    if isinstance(sensitive_spots, str):
        spots_list = [s.strip() for s in sensitive_spots.split(",") if s.strip()]
    elif isinstance(sensitive_spots, (list, tuple)):
        spots_list = [str(s).strip() for s in sensitive_spots if str(s).strip()]

    cleaned_spots: List[str] = []
    for s in spots_list:
        s_clean = re.sub(r"\([^)]*\)", "", s).strip().lower()
        if s_clean:
            cleaned_spots.append(s_clean)

    if cleaned_spots:
        if is_kneeling:
            for cs in cleaned_spots:
                if any(k in cs for k in ("thigh", "hip", "tail", "spine", "back", "waist", "leg", "flank")):
                    return cs
        return cleaned_spots[0]

    return "hips and thighs" if is_kneeling else "neck and shoulders"


def has_state_contradiction_in_choice(
    label: str,
    last_act: str = "",
    partner_climaxed: bool = False,
    player_meter: int = 0,
    partner_meter: int = 0,
    player_posture: str = "",
    player_spent: bool = False,
    partner_climaxes: Optional[Dict[str, bool]] = None,
    player_climaxed: bool = False,
) -> bool:
    """
    Returns True if a choice label contradicts the current intimate act, climax state,
    excitement meter threshold, physical posture, or male refractory state.
    Supports per-partner climax evaluation when partner_climaxes map is provided.
    Strictly gates aftercare choices behind player climax.
    """
    lbl = str(label or "").lower()
    if not lbl:
        return False

    act_norm = str(last_act or "").lower()
    is_penetrative_act = act_norm in ("penetrative", "anal_give", "anal_receive") and not player_spent
    is_transition_to_pen = (
        any(
            k in lbl for k in (
                "rise from your knees", "guide her onto", "guide him onto", "position yourself to",
                "transition to", "move to enter", "line yourself up", "straddle and lower"
            )
        )
        and not player_spent
    )

    # 0. Contradiction: Male player is physically spent / in refractory cooldown but choice assumes penetrative intercourse
    if player_spent:
        if re.search(
            r"\b(?:"
            r"thrust(?:ing|s)?|"
            r"drive\s+deeper|"
            r"keep\s+thrusting|"
            r"maintain\s+(?:a\s+)?(?:steady,?\s+)?(?:deep\s+)?rhythm|"
            r"slow\s+your\s+rhythm,?\s+gently\s+withdraw|"
            r"gently\s+withdraw|"
            r"bury\s+yourself\s+deeper|"
            r"hilt\s+inside|"
            r"finish\s+inside|"
            r"spill\s+(?:deep\s+)?inside|"
            r"penetrat(?:e|ing|ion)|"
            r"(?:lift|pull|guide|heave)\s+(?:.*?\s+)?onto\s+(?:your\s+)?lap|"
            r"take\s+(?:.*?\s+)?from\s+behind|"
            r"another\s+round|"
            r"resume\s+(?:intercourse|lovemaking)|"
            r"straddle\s+and\s+lower|"
            r"move\s+to\s+enter|"
            r"enter\s+(?:her|him|them)"
            r")\b",
            lbl,
            re.IGNORECASE,
        ):
            return True

    # 0b. Contradiction: Both player and partner have climaxed / all satisfied, but choice attempts to escalate intimacy or start another round
    player_finished = bool(player_climaxed or player_spent or player_meter >= 100)
    all_partners_finished = bool(
        partner_climaxed
        or (partner_climaxes and isinstance(partner_climaxes, dict) and len(partner_climaxes) > 0 and all(partner_climaxes.values()))
    )
    if player_finished and all_partners_finished:
        if any(
            p in lbl for p in (
                "thrust", "deeper", "penetrate", "enter", "finger", "fingers",
                "tongue", "fellatio", "cunnilingus", "undress", "strip",
                "another round", "resume", "straddle", "pump"
            )
        ):
            return True

    # 1. Contradiction: Assumes ongoing penetration when currently in oral, manual, or foreplay
    if not is_penetrative_act and not is_transition_to_pen:
        if any(
            p in lbl for p in (
                "maintain a steady, deep rhythm",
                "drive deeper",
                "thrust deeper",
                "gently withdraw",
                "slow your rhythm, gently withdraw",
                "bury yourself deeper",
                "hilt inside",
            )
        ):
            return True

    # 2. Contradiction: Assumes partner has already climaxed ("through her tremors / aftershocks") when she hasn't
    # or assumes aftercare before the player character has reached climax
    is_aftercare_claim = any(
        p in lbl for p in ("aftercare", "post-coital", "post-climax")
    )
    player_finished = bool(player_climaxed or player_spent or player_meter >= 100)
    if is_aftercare_claim and not player_finished:
        return True

    is_climax_aftershock_claim = any(
        p in lbl for p in (
            "through her tremors",
            "through his tremors",
            "through her aftershocks",
            "through his aftershocks",
            "through her climax",
            "through his climax",
            "through their tremors",
            "through their aftershocks",
        )
    )
    if is_climax_aftershock_claim:
        if partner_climaxes and isinstance(partner_climaxes, dict):
            # When multiple partners are named, determine which partner is experiencing the aftershocks/recovery
            specific_aftermath_p = None
            for p_name in partner_climaxes:
                p_first = p_name.lower().split()[0]
                p_esc = rf"(?:{re.escape(p_name.lower())}|{re.escape(p_first)})" if len(p_first) >= 3 else re.escape(p_name.lower())
                if (
                    re.search(rf"\b(?:as|while)\s+{p_esc}\s+(?:recovers|rests|trembles|breathes)\b", lbl)
                    or re.search(rf"\b{p_esc}'?s?\s+(?:aftershocks|tremors|climax|aftermath)\b", lbl)
                    or re.search(rf"\b(?:with|hold|guide)\s+{p_esc}\s+through\b", lbl)
                    or re.search(rf"\bthrough\s+{p_esc}'?s?\b", lbl)
                ):
                    specific_aftermath_p = p_name
                    break

            if specific_aftermath_p:
                if not partner_climaxes.get(specific_aftermath_p, False):
                    return True
            else:
                mentioned_partners = [
                    p_name for p_name in partner_climaxes
                    if (p_name.lower() in lbl) or (len(p_name.lower().split()[0]) >= 3 and p_name.lower().split()[0] in lbl)
                ]
                if mentioned_partners:
                    if not any(partner_climaxes.get(p, False) for p in mentioned_partners):
                        return True
                elif not partner_climaxed:
                    return True
        elif not partner_climaxed:
            return True

    # 3. Contradiction: Assumes immediate mutual climax when both meters are still low (< 65%)
    if max(player_meter, partner_meter) < 65 and not partner_climaxed:
        if any(
            p in lbl for p in (
                "push over the edge together",
                "reach climax together",
                "climax together with",
                "finish inside",
                "spill deep inside",
            )
        ):
            return True

    # 4. Contradiction: Whispering into ear while kneeling between thighs without rising
    is_kneeling = "kneel" in str(player_posture or "").lower() or act_norm == "oral_give"
    if is_kneeling and not any(k in lbl for k in ("rise", "stand", "pull yourself up", "kiss up")):
        if "into " in lbl and "ear" in lbl and "quicken your pace" in lbl:
            return True

    # 5. Contradiction: Splices quest, bounty, clue, or document investigation props into an active intimate encounter
    if any(
        p in lbl for p in (
            "study the handwriting",
            "doctored script",
            "water-stained paper",
            "wedged by the bench",
            "examine the clue",
            "inspect the clue",
            "inspect the evidence",
            "examine the evidence",
            "search for clues",
            "check the ledger",
            "inspect the ledger",
            "read the document",
            "study the document",
            "investigate the ",
            "bounty target",
            "caseboard",
        )
    ) or bool(
        re.search(
            r"\b(?:pull\s+out|reach\s+for|smooth|examine|inspect|study|read|analyze|decipher)\b.*\b(?:paper|script|page|ledger|document|clue|evidence|handwriting|note|scroll|dossier|manifest|logbook)\b",
            lbl,
        )
    ):
        return True

    return False


def infer_last_act_from_state(phys_state: Optional[Dict[str, Any]], action_str: str = "") -> str:
    """
    Infers the current intimate act from `action_str` (if transitioning acts this turn),
    `phys_state['excitement']['last_act']` (when the encounter is active), or falls back
    to inspecting `intimate_contact` and actor postures.
    """
    if not isinstance(phys_state, dict):
        if action_str:
            cls_act = classify_intimate_act(action_str).get("act_type", "none")
            if cls_act not in ("", "none"):
                return cls_act
        return "foreplay_nongenital"

    ic_only = str(phys_state.get("intimate_contact") or "").lower()
    if action_str:
        cand_partners: List[str] = []
        exc_d = phys_state.get("excitement")
        if isinstance(exc_d, dict):
            for cp in (exc_d.get("current_partners") or []):
                if cp and str(cp).strip() not in cand_partners:
                    cand_partners.append(str(cp).strip())
            for ak in (exc_d.get("actors") or {}):
                if ak and str(ak).strip() not in cand_partners:
                    cand_partners.append(str(ak).strip())
        for ak in (phys_state.get("actors") or {}):
            if ak and str(ak).strip() not in cand_partners:
                cand_partners.append(str(ak).strip())
        if " with " in ic_only:
            rec_p = str(phys_state.get("intimate_contact") or "").split(" with ", 1)[1].split("(")[0].strip()
            for chunk in rec_p.split(","):
                for sp in chunk.split(" and "):
                    if sp.strip() and sp.strip().lower() != "partner" and sp.strip() not in cand_partners:
                        cand_partners.append(sp.strip())
        for p_cand in (cand_partners or ["Partner"]):
            cls_act = classify_intimate_act(action_str, intimate_contact_str=ic_only, partner_name=p_cand).get("act_type", "none")
            if cls_act not in ("", "none", "foreplay_nongenital"):
                return cls_act

    if any(k in ic_only for k in ("kissing", "cuddling", "aftercare", "holding hands")) and not any(
        k in ic_only for k in ("oral", "manual", "anal", "intercourse", "intimate encounter")
    ):
        return "foreplay_nongenital"

    exc_st = phys_state.get("excitement")
    explicit_act = ""
    if isinstance(exc_st, dict) and exc_st.get("active", True) is not False:
        explicit_act = str(exc_st.get("last_act") or "").strip().lower()
        if explicit_act and explicit_act not in ("none", "foreplay_nongenital"):
            return explicit_act

    parts = [ic_only]
    actors = phys_state.get("actors")
    if isinstance(actors, dict):
        for a_data in actors.values():
            if isinstance(a_data, dict):
                parts.append(str(a_data.get("posture") or "").lower())
    combined = " ".join(parts)

    if "oral mutual" in combined or "69" in combined:
        return "oral_mutual"
    if any(k in combined for k in ("oral give", "cunnilingus", "between her thighs", "between his thighs", "between their thighs", "kneeling between")):
        return "oral_give"
    if any(k in combined for k in ("oral receive", "fellatio", "blowjob")):
        return "oral_receive"
    if any(k in combined for k in ("manual give", "fingering")):
        return "manual_give"
    if any(k in combined for k in ("manual receive", "handjob")):
        return "manual_receive"
    if "anal give" in combined:
        return "anal_give"
    if "anal receive" in combined:
        return "anal_receive"
    if any(
        k in combined
        for k in (
            "intercourse",
            "penetrative",
            "penetration",
            "inside ",
            "maintaining rhythm",
            "straddling",
            "riding",
            "missionary",
            "doggy",
            "mating press",
            "cowgirl",
            "thrusting",
        )
    ):
        return "penetrative"
    return explicit_act if explicit_act and explicit_act != "none" else "foreplay_nongenital"



def build_intimate_choice_blueprints(
    partner_name: str,
    last_act: str = "foreplay_nongenital",
    player_posture: str = "",
    partner_posture: str = "",
    player_meter: int = 0,
    partner_meter: int = 0,
    partner_climaxed: bool = False,
    player_climaxed: bool = False,
    premature_finish: bool = False,
    partner_demanded: bool = True,
    sensitive_spots: Any = None,
    partner_actors: Optional[List[Dict[str, Any]]] = None,
    partner_gender: str = "Female",
    discovered_intimate: Optional[Dict[str, Any]] = None,
    openness_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Builds Act-, Posture-, Sensitive-Spot-, Preference-, and Meter-Aware choice blueprints for the
    Hybrid Guided Intimate System. Supports single or multiple partners:
      - Used by `format_physical_state_prompt` to guide the LLM before generation.
      - Used by `clean_choices_impl` as the state-accurate fallback safety net.
    """
    p_name = partner_name or "Partner"
    act_norm = str(last_act or "foreplay_nongenital").lower()
    is_kneeling = "kneel" in str(player_posture or "").lower() or act_norm == "oral_give"
    disc = discovered_intimate if isinstance(discovered_intimate, dict) else {}
    eff_spots = sensitive_spots or disc.get("sensitive_spots")
    spot_phrase = _clean_spot_phrase(eff_spots, is_kneeling=is_kneeling)
    high_excitement = (player_meter >= 70 or partner_meter >= 70)

    def _disc_list(key: str) -> List[str]:
        val = disc.get(key)
        if not val:
            return []
        if isinstance(val, (list, tuple, set)):
            items = [str(x).strip() for x in val if str(x).strip()]
        else:
            items = [x.strip() for x in str(val).split(",") if x.strip()]
        return [re.sub(r'\([^)]*\)', '', x).strip() for x in items if x and x.lower() not in ("none", "unknown", "none (vanilla)")]

    disc_desires = _disc_list("desires") + _disc_list("kinks")
    disc_likes_low = ", ".join(_disc_list("act_likes")).lower()
    disc_dislikes_low = ", ".join(_disc_list("act_dislikes")).lower()
    prefers_receiving_oral = ("receiving oral" in disc_likes_low or "receiving_oral" in disc_likes_low)
    dislikes_receiving_oral = ("receiving oral" in disc_dislikes_low or "receiving_oral" in disc_dislikes_low)
    prefers_slow = ("slow & sensual" in disc_likes_low or "slow_sensual" in disc_likes_low)
    dislikes_rough = ("rough handling" in disc_dislikes_low or "rough_handling" in disc_dislikes_low)
    first_desire_cue = disc_desires[0].lower() if disc_desires else ""

    def _stamp_intimate_choice(c: dict, default_partner: str, act_nm: str, ex_lbl: str) -> dict:
        lbl = c.get("label", "")
        lbl_low = lbl.lower()
        if c.get("stat") in ("NONE", "FREE") or lbl == ex_lbl:
            c["intent"] = "dialogue_exit"
            c["ends_dialogue"] = True
            c["sub_intent"] = "aftercare" if "aftercare" in lbl_low else ""
            c["target_npc"] = default_partner
        elif "aftercare" in lbl_low:
            c["intent"] = "affection_touch"
            c["ends_dialogue"] = False
            c["sub_intent"] = "aftercare"
            c["target_npc"] = default_partner
        else:
            c["intent"] = "intimate_act"
            c["ends_dialogue"] = False
            if any(w in lbl_low for w in ("anal", "pegging", "rear", "anus")):
                c["sub_intent"] = "anal_receive" if any(w in lbl_low for w in ("pegs", "takes you", "into your rear")) else "anal_give"
            elif any(w in lbl_low for w in (
                "thrust", "drive deeper", "penetrat", "intercourse", "ride his", "ride her",
                "deeper angle", "deeper intimacy", "more intimate position", "escalate from manual",
                "shift positions", "rising passion", "drive toward your own release"
            )):
                c["sub_intent"] = "intercourse"
            elif any(w in lbl_low for w in ("oral", "tongue", "lick", "suck", "mouth")):
                if act_nm == "oral_receive" or "mouth around" in lbl_low or "pleasures you with" in lbl_low:
                    c["sub_intent"] = "oral_receive"
                elif act_nm == "oral_mutual":
                    c["sub_intent"] = "oral_mutual"
                else:
                    c["sub_intent"] = "oral_give"
            elif any(w in lbl_low for w in ("finger", "hand")):
                if act_nm == "manual_receive" or "strokes you" in lbl_low:
                    c["sub_intent"] = "manual_receive"
                else:
                    c["sub_intent"] = "manual_give"
            elif "kiss" in lbl_low:
                c["sub_intent"] = "kiss"
            else:
                c["sub_intent"] = act_nm if act_nm in ("kiss", "foreplay", "manual_give", "manual_receive", "oral_give", "oral_receive", "oral_mutual", "intercourse", "anal_give", "anal_receive", "aftercare") else "foreplay"

            # Check if an individual partner is specifically addressed in label (Decision A5)
            matched_p = None
            if partner_actors:
                for pa in partner_actors:
                    pa_name = str(pa.get("name") or "").strip()
                    if pa_name and (pa_name.lower() in lbl_low or (pa_name.split() and len(pa_name.split()[0]) >= 3 and pa_name.split()[0].lower() in lbl_low)):
                        matched_p = pa_name
                        break
            c["target_npc"] = matched_p or default_partner
        return c

    # ─────────────────────────────────────────────────────────────────────────────
    # MULTI-PARTNER CHOICE BLUEPRINT GENERATION (2 or more active partners)
    # ─────────────────────────────────────────────────────────────────────────────
    if partner_actors and len(partner_actors) >= 2:
        pA = partner_actors[0]
        pB = partner_actors[1]
        pA_name = str(pA.get("name") or p_name or "Partner A").strip()
        pB_name = str(pB.get("name") or "Partner B").strip()
        pA_meter = int(pA.get("meter", 0) or 0)
        pB_meter = int(pB.get("meter", 0) or 0)
        pA_climaxed = bool(pA.get("climaxed", False))
        pB_climaxed = bool(pB.get("climaxed", False))
        pA_spot = _clean_spot_phrase(pA.get("spots") or pA.get("sensitive_spots") or sensitive_spots)
        pB_spot = _clean_spot_phrase(pB.get("spots") or pB.get("sensitive_spots"))

        def _get_p_pronouns(p_dict, def_gender="Female"):
            gen = str(p_dict.get("gender") or def_gender).lower()
            is_m = "male" in gen and "female" not in gen
            return ("his" if is_m else "her", "him" if is_m else "her", "he" if is_m else "she")

        pA_poss, pA_obj, pA_subj = _get_p_pronouns(pA, partner_gender)
        pB_poss, pB_obj, pB_subj = _get_p_pronouns(pB, partner_gender)

        all_p_names = [str(p.get("name")).strip() for p in partner_actors if p.get("name")]
        if len(all_p_names) == 2:
            all_p_names_str = f"both {all_p_names[0]} and {all_p_names[1]}"
            all_p_names_flat = f"{all_p_names[0]} and {all_p_names[1]}"
        elif len(all_p_names) > 2:
            all_p_names_str = f"all of {', '.join(all_p_names[:-1])}, and {all_p_names[-1]}"
            all_p_names_flat = f"{', '.join(all_p_names[:-1])}, and {all_p_names[-1]}"
        else:
            all_p_names_str = pA_name
            all_p_names_flat = pA_name

        # Case A: Post-Premature Finish with Multiple Partners
        if player_climaxed and premature_finish:
            unsat_actors = [p for p in partner_actors if not p.get("climaxed")]
            uA = unsat_actors[0] if unsat_actors else pA
            uB = unsat_actors[1] if len(unsat_actors) > 1 else (unsat_actors[0] if unsat_actors else pB)
            uA_name = str(uA.get("name") or pA_name).strip()
            uB_name = str(uB.get("name") or pB_name).strip()
            uA_poss, uA_obj, uA_subj = _get_p_pronouns(uA, partner_gender)
            uB_poss, uB_obj, uB_subj = _get_p_pronouns(uB, partner_gender)

            if len(unsat_actors) == 1:
                choices = [
                    {
                        "label": f"Use your fingers to stroke and please {uA_name} toward {uA_poss} climax",
                        "stat": "AGI",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Kneel close and use your tongue passionately to bring {uA_name} over the edge",
                        "stat": "CHA",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Hold {all_p_names_str} close, apologizing breathlessly and promising to satisfy {uA_name}",
                        "stat": "END",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Step back gently, excuse yourself, and catch your breath with {all_p_names_flat}",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                ]
            else:
                choices = [
                    {
                        "label": f"Use your fingers to stroke and please {uA_name} toward {uA_poss} climax",
                        "stat": "AGI",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Kneel close and use your tongue passionately to bring {uB_name} over the edge",
                        "stat": "CHA",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Hold {all_p_names_str} close, apologizing breathlessly and promising to satisfy them",
                        "stat": "END",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    {
                        "label": f"Step back gently, excuse yourself, and catch your breath with {all_p_names_flat}",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                ]
            exit_label = choices[-1]["label"]
        # Case B: Post-Climax Aftercare / All Satisfied
        elif player_climaxed and not premature_finish:
            exit_label = f"Rest together in aftercare, excuse yourself gently, and catch your breath with {all_p_names_flat}"
            choices = [
                {
                    "label": f"Hold {pA_name} close in tender aftercare and trace gentle circles along {pA_poss} {pA_spot}",
                    "stat": "CHA",
                    "requirement": 5,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
                {
                    "label": f"Brush {pB_name}'s hair back, kiss {pB_obj} softly, and share quiet post-climax warmth",
                    "stat": "PER",
                    "requirement": 5,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
                {
                    "label": f"Keep {all_p_names_str} wrapped securely in your arms in sweet aftercare",
                    "stat": "END",
                    "requirement": 5,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
                {
                    "label": exit_label,
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
            ]
        # Case C: Active Multi-Partner Intimate Encounter
        else:
            # Slot 1: Partner A Focus
            if act_norm == "oral_give":
                slot1_lbl = (
                    f"Hold {pA_name} steady by the hips and lick tenderly through {pA_poss} trembling aftershocks"
                    if pA_climaxed
                    else f"Hold {pA_name} by the hips and deepen the teasing rhythm of your tongue"
                )
                slot1_stat = "AGI"
            elif act_norm == "manual_give":
                slot1_lbl = (
                    f"Stroke {pA_name} gently with your fingers through {pA_poss} trembling aftershocks"
                    if pA_climaxed
                    else f"Curl your fingers with a steady, attentive pace to build {pA_name}'s pleasure"
                )
                slot1_stat = "AGI"
            elif act_norm in ("penetrative", "anal_give", "anal_receive"):
                slot1_lbl = (
                    (
                        f"Hold {pA_name} close as {pA_subj} catches {pA_poss} breath through {pA_poss} climax aftershocks"
                        if pA_poss == "his"
                        else f"Maintain a steady, deep rhythm and hold {pA_name} through {pA_poss} climax aftershocks"
                    )
                    if pA_climaxed
                    else f"Maintain a steady, deep rhythm and lock eyes with {pA_name}"
                )
                slot1_stat = "END"
            elif act_norm == "oral_receive":
                slot1_lbl = f"Steady your breathing and guide {pA_name}'s head as {pA_subj} deepens {pA_poss} oral pace"
                slot1_stat = "END"
            elif act_norm == "manual_receive":
                slot1_lbl = f"Hold {pA_name}'s gaze and lean into the steady rhythm of {pA_poss} hand"
                slot1_stat = "END"
            elif act_norm == "oral_mutual":
                slot1_lbl = (
                    f"Ease your oral pace, licking tenderly as {pA_name} recovers through {pA_poss} climax"
                    if pA_climaxed
                    else f"Match {pA_name}'s oral rhythm with eager, unwavering focus"
                )
                slot1_stat = "AGI"
            else:
                slot1_lbl = f"Deepen your kiss and caress {pA_name}'s {pA_spot} with lingering warmth"
                slot1_stat = "CHA"

            # Slot 2: Partner B Focus / Transition Focus
            if act_norm == "oral_give":
                slot2_lbl = (
                    f"Shift your attention to {pB_name}, caressing {pB_poss} {pB_spot} through {pB_poss} trembling aftershocks"
                    if pB_climaxed
                    else f"Shift your attention to {pB_name}, caressing {pB_poss} {pB_spot} while tasting {pB_obj} intimately"
                )
                slot2_stat = "PER"
            elif act_norm == "manual_give":
                slot2_lbl = (
                    f"Reach with your other hand to stroke {pB_name} tenderly between {pB_poss} thighs through {pB_poss} aftershocks"
                    if pB_climaxed
                    else f"Reach with your other hand to stroke {pB_name} intimately between {pB_poss} thighs"
                )
                slot2_stat = "CHA"
            elif act_norm in ("penetrative", "anal_give", "anal_receive"):
                slot2_lbl = (
                    f"Draw {pB_name} into your embrace, kissing {pB_obj} passionately as {pA_name} recovers through {pA_poss} aftershocks"
                    if pA_climaxed
                    else f"Draw {pB_name} into your embrace, kissing {pB_obj} passionately while maintaining rhythm with {pA_name}"
                )
                slot2_stat = "CHA"
            elif act_norm == "oral_receive":
                slot2_lbl = (
                    f"Pull {pB_name} close with your free arm, sharing breathless kisses as {pA_name} rests against you"
                    if pA_climaxed
                    else f"Pull {pB_name} close with your free arm, kissing {pB_poss} lips as {pA_name} pleasures you with {pA_poss} mouth"
                )
                slot2_stat = "CHA"
            elif act_norm == "manual_receive":
                slot2_lbl = (
                    f"Turn to {pB_name}, trailing breathless kisses along {pB_poss} neck as {pA_name} rests against you"
                    if pA_climaxed
                    else f"Turn to {pB_name}, trailing breathless kisses along {pB_poss} neck and {pB_spot} as {pA_name} strokes you"
                )
                slot2_stat = "CHA"
            elif act_norm == "oral_mutual":
                slot2_lbl = (
                    f"Reach with your hands to caress {pB_name}'s {pB_spot} through {pB_poss} aftershocks"
                    if pB_climaxed
                    else f"Reach with your hands to caress {pB_name}'s {pB_spot} while staying close to {pA_name}"
                )
                slot2_stat = "CHA"
            else:
                slot2_lbl = (
                    f"Slide your hands to caress {pB_name}'s {pB_spot} and hold {pB_obj} close through {pB_poss} aftershocks"
                    if pB_climaxed
                    else f"Slide your hands to caress {pB_name}'s {pB_spot} and draw {pB_obj} into the kiss"
                )
                slot2_stat = "AGI"

            # Slot 3: Climax Push (for highest unclimaxed partner) or Coordinated Dual Intimacy
            unclimaxed_partners = [p for p in partner_actors if not p.get("climaxed")]
            top_unclimaxed = max(unclimaxed_partners, key=lambda p: int(p.get("meter", 0) or 0)) if unclimaxed_partners else None
            high_unclimaxed = [p for p in unclimaxed_partners if int(p.get("meter", 0) or 0) >= 70]
            if len(high_unclimaxed) >= 2:
                dual_climax_lbl = (
                    f"Coordinate your touch between both {pA_name} and {pB_name}, bringing them both to the edge together into climax"
                    if len(all_p_names) == 2
                    else f"Coordinate your touch among {all_p_names_flat}, bringing everyone to the edge together into climax"
                )
                slot3 = {
                    "label": dual_climax_lbl,
                    "stat": "CHA",
                    "requirement": 7,
                    "mp_cost": 0,
                    "is_fallback": False,
                }
            elif top_unclimaxed and int(top_unclimaxed.get("meter", 0) or 0) >= 70:
                top_u_name = str(top_unclimaxed.get("name") or pA_name).strip()
                top_u_poss, top_u_obj, top_u_subj = _get_p_pronouns(top_unclimaxed, partner_gender)
                slot3 = {
                    "label": f"Focus your rhythm relentlessly on {top_u_name} to push {top_u_obj} over the edge into climax",
                    "stat": "END",
                    "requirement": 7,
                    "mp_cost": 0,
                    "is_fallback": False,
                }
            elif player_meter >= 70:
                slot3 = {
                    "label": f"Hold {all_p_names_str} close as you drive toward your own release",
                    "stat": "END",
                    "requirement": 7,
                    "mp_cost": 0,
                    "is_fallback": False,
                }
            else:
                slot3 = {
                    "label": f"Pull {all_p_names_str} tight against you, coordinating your touch between them in rising passion",
                    "stat": "STR",
                    "requirement": 6,
                    "mp_cost": 0,
                    "is_fallback": False,
                }

            # Slot 4: Shared Exit / Natural Pause
            exit_label = f"Ease back gently, pause to catch your breath, and hold {all_p_names_str} close"
            choices = [
                {"label": slot1_lbl, "stat": slot1_stat, "requirement": 6, "mp_cost": 0, "is_fallback": False},
                {"label": slot2_lbl, "stat": slot2_stat, "requirement": 6, "mp_cost": 0, "is_fallback": False},
                slot3,
                {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
            ]

        coord_target = f"among {all_p_names_flat}" if len(all_p_names) > 2 else f"between {pA_name} and {pB_name}"
        guide_lines = [
            f"- MULTI-PARTNER HYBRID CHOICE BLUEPRINTS (Coordinate choices {coord_target} in `next_choices` — NEVER mix in quest objectives, clues, or investigation props, and NEVER prefix with ⭐, 🎯, or ⚡):",
        ]
        for idx, c in enumerate(choices, 1):
            _stamp_intimate_choice(c, all_p_names_flat, act_norm, exit_label)
            stat_tag = "FREE" if c["stat"] in ("NONE", "FREE") else c["stat"]
            guide_lines.append(f"  {idx}. [{stat_tag}] \"{c['label']}\"")

        return {
            "choices": choices,
            "exit_label": exit_label,
            "guide_lines": guide_lines,
        }

    # ─────────────────────────────────────────────────────────────────────────────
    # SINGLE-PARTNER CHOICE BLUEPRINT GENERATION (1-on-1 encounter)
    # ─────────────────────────────────────────────────────────────────────────────
    p_gender_low = str(partner_gender or "Female").lower()
    is_male_p = "male" in p_gender_low and "female" not in p_gender_low
    p_poss = "his" if is_male_p else "her"
    p_obj = "him" if is_male_p else "her"
    p_subj = "he" if is_male_p else "she"

    # 1. Post-Premature Finish Negotiation
    if player_climaxed and premature_finish:
        if partner_demanded:
            finger_opt = {
                "label": f"Use your fingers to stroke and please {p_name} toward {p_poss} climax",
                "stat": "AGI",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
            oral_opt = {
                "label": f"Kneel close and use your tongue passionately to bring {p_name} over the edge",
                "stat": "CHA",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
            hold_opt = {
                "label": f"Apologize breathlessly, hold {p_name} close, and promise to make it up to {p_obj}",
                "stat": "END",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
            exit_opt = {
                "label": f"Step back gently, excuse yourself, and catch your breath with {p_name}",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
            }
            if dislikes_receiving_oral:
                choices = [
                    finger_opt,
                    {
                        "label": f"Caress {p_name}'s {spot_phrase} with tender fingers to keep {p_poss} arousal warm",
                        "stat": "CHA",
                        "requirement": 6,
                        "mp_cost": 0,
                        "is_fallback": False,
                    },
                    hold_opt,
                    exit_opt,
                ]
            elif prefers_receiving_oral:
                choices = [oral_opt, finger_opt, hold_opt, exit_opt]
            else:
                choices = [finger_opt, oral_opt, hold_opt, exit_opt]
        else:
            choices = [
                {
                    "label": (
                        f"Kneel close and please {p_name} warmly with your tongue"
                        if prefers_receiving_oral and not dislikes_receiving_oral
                        else f"Notice {p_name}'s flushed longing and tenderly use your hands to please {p_obj}"
                    ),
                    "stat": "AGI",
                    "requirement": 5,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
                {
                    "label": f"Kiss {p_name} softly and hold {p_obj} tight against your chest in sweet aftercare",
                    "stat": "CHA",
                    "requirement": 5,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
                {
                    "label": f"Step back gently, excuse yourself, and catch your breath with {p_name}",
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "is_fallback": False,
                },
            ]
        exit_label = choices[-1]["label"]
    # 1.5. Post-Climax Aftercare / Refractory Rest (Player spent & partner satisfied)
    elif player_climaxed and not premature_finish:
        exit_label = f"Rest together in aftercare, excuse yourself gently, and catch your breath with {p_name}"
        choices = [
            {
                "label": f"Hold {p_name} close in tender aftercare and trace gentle circles along {p_poss} {spot_phrase}",
                "stat": "CHA",
                "requirement": 5,
                "mp_cost": 0,
                "is_fallback": False,
            },
            {
                "label": f"Brush {p_name}'s hair back, kiss {p_obj} softly, and share quiet post-climax warmth",
                "stat": "PER",
                "requirement": 5,
                "mp_cost": 0,
                "is_fallback": False,
            },
            {
                "label": f"Catch your breath against {p_name} and keep {p_obj} wrapped securely in your arms",
                "stat": "END",
                "requirement": 5,
                "mp_cost": 0,
                "is_fallback": False,
            },
            {
                "label": exit_label,
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
            },
        ]
    # 2. Oral Give (Player kneeling / performing oral on partner)
    elif act_norm == "oral_give":
        slot1_lbl = (
            f"Hold {p_name} steady by the hips and lick tenderly through {p_poss} trembling aftershocks"
            if partner_climaxed
            else f"Hold {p_name} by the hips and deepen the teasing rhythm of your tongue"
        )
        slot2_lbl = f"Caress {p_name}'s {spot_phrase} while maintaining steady oral stimulation"
        if partner_meter >= 70:
            slot3 = {
                "label": f"Focus your tongue relentlessly on {p_name}'s core to push {p_obj} over the edge",
                "stat": "END",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        else:
            slot3 = {
                "label": f"Rise from your knees, kiss up {p_name}'s body, and shift positions to take the lead",
                "stat": "STR",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "AGI", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "PER", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            slot3,
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 3. Oral Receive (Partner performing oral on player)
    elif act_norm == "oral_receive":
        slot1_lbl = f"Steady your breathing and guide {p_name}'s head as {p_subj} deepens {p_poss} oral pace"
        slot2_lbl = f"Caress {p_name}'s {spot_phrase} and whisper breathless praise as {p_subj} pleasures you with {p_poss} mouth"
        if player_meter >= 70:
            slot3 = {
                "label": f"Grip {p_name}'s shoulders and let yourself reach climax from {p_poss} mouth",
                "stat": "END",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        else:
            slot3 = {
                "label": f"Draw {p_name} up into your arms to kiss {p_obj} deeply and transition positions",
                "stat": "STR",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "END", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "CHA", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            slot3,
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 4. Oral Mutual (69)
    elif act_norm == "oral_mutual":
        slot1_lbl = (
            f"Ease your oral pace, licking tenderly as {p_name} recovers through {p_poss} climax"
            if partner_climaxed
            else f"Match {p_name}'s oral rhythm with eager, unwavering focus"
        )
        slot2_lbl = f"Grip {p_name}'s hips and caress {p_poss} {spot_phrase} as you pleasure each other with your mouths"
        if partner_climaxed:
            slot3 = {
                "label": f"Hold {p_name} close as you push over the edge into your own release from {p_poss} mouth",
                "stat": "END",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        elif high_excitement:
            slot3 = {
                "label": f"Deepen your oral pace to drive both yourself and {p_name} toward climax",
                "stat": "END",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        else:
            slot3 = {
                "label": f"Shift positions with {p_name} to transition into direct embrace and deeper intimacy",
                "stat": "STR",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "AGI", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "PER", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            slot3,
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 5. Manual Give (Player stimulating partner with fingers/hands)
    elif act_norm == "manual_give":
        slot1_lbl = (
            f"Stroke {p_name} gently with your fingers through {p_poss} trembling aftershocks"
            if partner_climaxed
            else f"Curl your fingers with a steady, attentive pace to build {p_name}'s pleasure"
        )
        slot2_lbl = f"Kiss and caress {p_name}'s {spot_phrase} while teasing {p_obj} with your hand"
        if partner_meter >= 70:
            slot3 = {
                "label": f"Quicken your fingers' rhythm to push {p_name} over the edge into climax",
                "stat": "AGI",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        else:
            slot3 = {
                "label": f"Draw {p_name} closer to escalate from manual teasing into deeper intimacy",
                "stat": "STR",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "AGI", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "CHA", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            slot3,
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 6. Manual Receive (Partner stimulating player with hands/fingers)
    elif act_norm == "manual_receive":
        slot1_lbl = f"Hold {p_name}'s gaze and lean into the steady rhythm of {p_poss} hand"
        slot2_lbl = f"Caress {p_name}'s {spot_phrase} and whisper encouragement as {p_subj} strokes you"
        if player_meter >= 70:
            slot3 = {
                "label": f"Surrender to the building tension and reach climax in {p_name}'s hand",
                "stat": "END",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": False,
            }
        else:
            slot3 = {
                "label": f"Pull {p_name} close to kiss {p_obj} deeply and take the physical lead",
                "stat": "STR",
                "requirement": 6,
                "mp_cost": 0,
                "is_fallback": False,
            }
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "END", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "CHA", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            slot3,
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 7. Penetrative Intercourse (Vaginal or Anal)
    elif act_norm in ("penetrative", "anal_give", "anal_receive"):
        slot1_lbl = (
            (
                f"Hold {p_name} close as {p_subj} catches {p_poss} breath through {p_poss} climax aftershocks"
                if is_male_p
                else f"Maintain a steady, deep rhythm and hold {p_name} through {p_poss} climax aftershocks"
            )
            if partner_climaxed
            else f"Maintain a steady, deep rhythm and lock eyes with {p_name}"
        )
        slot2_lbl = f"Caress {p_name}'s {spot_phrase} and whisper breathless praise as you quicken your pace"
        if partner_climaxed:
            if is_male_p and act_norm != "anal_give":
                slot3_lbl = f"Guide {p_name}'s touch and push over the edge into your own release in {p_name}'s arms"
            else:
                slot3_lbl = f"Shift position to drive deeper and push over the edge into your own release in {p_name}'s arms"
        elif high_excitement:
            slot3_lbl = f"Shift position to drive deeper and push over the edge with {p_name}"
        else:
            slot3_lbl = f"Shift position for a deeper angle and build the heat with {p_name}"
        exit_label = f"Slow your rhythm, gently withdraw, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "END", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "CHA", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot3_lbl, "stat": "STR", "requirement": 7, "mp_cost": 0, "is_fallback": False},
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]
    # 8. Non-Genital Foreplay / Kissing / Touching Body
    else:
        desire_hook = f", indulging {first_desire_cue}" if first_desire_cue else ""
        op_prof = openness_profile if isinstance(openness_profile, dict) else {}
        op_tier_bp = str(op_prof.get("tier") or "").lower()
        op_comfort_bp = str(op_prof.get("comfort_stage") or "guarded").lower()
        op_contrast_bp = str(op_prof.get("contrast_archetype") or "").lower()
        needs_gentle_warmup_bp = bool(
            partner_meter < 40
            and (
                (op_tier_bp == "prude" and op_comfort_bp in ("guarded", "warming_up"))
                or (op_contrast_bp == "all_talk_tease" and op_prof.get("bluff_crack_active"))
            )
        )
        is_daring_bp = bool(
            (op_tier_bp in ("bold", "shameless") and not op_prof.get("bluff_crack_active"))
            or (op_contrast_bp == "hidden_fire" and op_prof.get("hidden_fire_active"))
        )
        slot1_lbl = f"Deepen your kiss and caress {p_name}'s {spot_phrase} with lingering warmth{desire_hook}"
        if needs_gentle_warmup_bp:
            slot2_lbl = f"Speak softly and tease {p_name}'s {spot_phrase} with gentle, unhurried reassurance to ease {p_poss} nerves"
            slot3_lbl = f"Check in tenderly with {p_name} as you draw {p_obj} closer at {p_poss} own comfort pace"
        elif prefers_slow or dislikes_rough:
            slot2_lbl = f"Take an unhurried, sensual pace as your hands tease {p_name} gently to build {p_poss} arousal"
            slot3_lbl = f"Draw {p_name} closer and guide {p_obj} into a more intimate position"
        elif is_daring_bp:
            slot2_lbl = f"Whisper daring encouragement as your hands slide boldly over {p_name} to stoke {p_poss} heat"
            slot3_lbl = f"Draw {p_name} flush against you and steer {p_obj} eagerly into deeper intimacy"
        else:
            slot2_lbl = f"Slide your hands lower to tease {p_name} more intimately and build {p_poss} arousal"
            slot3_lbl = f"Draw {p_name} closer and guide {p_obj} into a more intimate position"
        exit_label = f"Ease back gently, pause to catch your breath, and hold {p_name} close"
        choices = [
            {"label": slot1_lbl, "stat": "CHA", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot2_lbl, "stat": "AGI", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": slot3_lbl, "stat": "STR", "requirement": 6, "mp_cost": 0, "is_fallback": False},
            {"label": exit_label, "stat": "NONE", "requirement": 0, "mp_cost": 0, "is_fallback": False},
        ]

    if dislikes_receiving_oral:
        for _c in choices:
            if "tongue" in _c["label"].lower() and "edge" in _c["label"].lower():
                _c["label"] = f"Use gentle, attentive fingers along {p_name}'s {spot_phrase} to bring {p_obj} closer"

    guide_lines = [
        f"- HYBRID CHOICE BLUEPRINTS (Adapt these situational archetypes to the exact intimate act, partner reactions, and postures for `next_choices` — NEVER mix in quest objectives, clues, or investigation props, and NEVER prefix with ⭐, 🎯, or ⚡):"
    ]
    if disc:
        cue_parts = []
        if first_desire_cue:
            cue_parts.append(f"discovered desires/kinks ({first_desire_cue})")
        if disc_likes_low:
            cue_parts.append(f"liked acts ({disc_likes_low})")
        if disc_dislikes_low:
            cue_parts.append(f"EXCLUDE disliked acts ({disc_dislikes_low})")
        if cue_parts:
            guide_lines.append(f"  * Discovered Preference Guidance: " + "; ".join(cue_parts) + ".")
    for idx, c in enumerate(choices, 1):
        _stamp_intimate_choice(c, p_name, act_norm, exit_label)
        stat_tag = "FREE" if c["stat"] in ("NONE", "FREE") else c["stat"]
        guide_lines.append(f"  {idx}. [{stat_tag}] \"{c['label']}\"")

    return {
        "choices": choices,
        "exit_label": exit_label,
        "guide_lines": guide_lines,
    }


def resolve_pre_turn_intimacy_and_clothing(
    session: Dict[str, Any],
    party: Optional[List[Any]] = None,
    actions: Optional[List[Any]] = None,
    new_partners: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Deterministic pre-turn intimacy and clothing resolution engine.
    Runs BEFORE the Narrator LLM on intimate/social turns:
    1. Classifies the player's action via classify_intimate_act.
    2. Displaces/removes blocking clothing layers (bottom, under_bottom, top, under_top)
       for participating actors in session['physical_state'].
    3. Computes the excitement step pre-turn and caches the result in session['_pre_turn_excitement_res'].
    4. Generates [MANDATORY CLIMAX DIRECTIVE] instructions when meters peak so narrative matches state 100%.
    """
    from mechanics.social.physical_state import is_erotic_intimate_contact

    player_char = session.get("player_character")
    if not player_char and party:
        first_party = party[0]
        player_char = first_party[0] if isinstance(first_party, (tuple, list)) else first_party
    if not isinstance(player_char, dict):
        player_char = {}

    # Select active intimate/redress/disengage action across all co-op actions (D15)
    selected_act_dict: Dict[str, Any] = {}
    action_str = ""
    _INTIMATE_SUB_SET = {
        "intercourse", "oral_give", "oral_receive", "oral_mutual",
        "manual_give", "manual_receive", "manual_mutual",
        "anal_give", "anal_receive", "anal_mutual",
        "kiss", "foreplay", "aftercare", "redress",
    }
    for _cand_a in (actions or []):
        if isinstance(_cand_a, dict):
            _cr = _cand_a.get("resolved_intent") if isinstance(_cand_a.get("resolved_intent"), dict) else {}
            _cs = str(_cr.get("sub_intent") or _cand_a.get("sub_intent") or "").lower().strip()
            _ci = str(_cr.get("intent") or _cand_a.get("intent") or "").lower().strip()
            if _cs in _INTIMATE_SUB_SET or _ci in ("intimate_act", "dialogue_exit") or _cand_a.get("ends_dialogue") or _cr.get("ends_dialogue"):
                selected_act_dict = _cand_a
                action_str = str(_cand_a.get("label") or _cand_a.get("action") or "")
                if isinstance(_cand_a.get("char"), dict) and _cand_a["char"].get("name"):
                    player_char = _cand_a["char"]
                break
    if not selected_act_dict and actions:
        first_act = actions[0]
        if isinstance(first_act, dict):
            selected_act_dict = first_act
            action_str = str(first_act.get("label") or first_act.get("action") or "")
            if isinstance(first_act.get("char"), dict) and first_act["char"].get("name"):
                player_char = first_act["char"]
        else:
            action_str = str(first_act or "")

    player_name = str(player_char.get("name") or "Player").strip()

    session_id = session.get("id") or 0
    physical_state = session.get("_physical_state") or session.get("physical_state")
    if not isinstance(physical_state, dict) or not physical_state:
        if session_id:
            try:
                physical_state = db.get_session_physical_state(session_id) or {}
            except Exception:
                physical_state = {}
        else:
            physical_state = {}
    session["physical_state"] = physical_state
    session["_physical_state"] = physical_state

    is_check_success = True
    if selected_act_dict and selected_act_dict.get("check"):
        chk = selected_act_dict["check"]
        tier = getattr(chk, "tier", None) if not isinstance(chk, dict) else chk.get("tier")
        succeeded_flag = getattr(chk, "succeeded", None) if not isinstance(chk, dict) else chk.get("succeeded")
        if tier in ("fail", "crit_fail") or succeeded_flag is False:
            is_check_success = False
    elif selected_act_dict and selected_act_dict.get("success") is False:
        is_check_success = False

    from mechanics.world.mobility import get_session_dialogue_partners
    sess_dps = list(get_session_dialogue_partners(session))
    if new_partners:
        for np in new_partners:
            if np and np not in sess_dps:
                sess_dps.append(np)

    partner_name = sess_dps[0] if sess_dps else (session.get("dialogue_partner") or "Partner")

    partner_contacts: List[Dict[str, Any]] = []
    target_names = sess_dps or [partner_name]
    for p in target_names:
        c = None
        if session_id:
            try:
                c = db.get_contact(session_id, p)
            except Exception:
                c = None
        if not c:
            c = {"name": p}
        partner_contacts.append(c)

    primary_contact = partner_contacts[0] if partner_contacts else {"name": partner_name}

    r_intent = selected_act_dict.get("resolved_intent") if isinstance(selected_act_dict.get("resolved_intent"), dict) else {}
    sub_intent = str(r_intent.get("sub_intent") or selected_act_dict.get("sub_intent") or "").lower().strip()
    target_npc = str(r_intent.get("target_npc") or selected_act_dict.get("target_npc") or "").strip()
    orig_sub_intent = sub_intent

    directives: List[str] = []

    # Male Refractory Soft-Gate: penetrative intercourse/anal_give during active refractory downgrades to foreplay
    p_gender_low = str(player_char.get("gender") or player_char.get("sex") or "male").lower()
    is_female_pl = "female" in p_gender_low or "woman" in p_gender_low or "girl" in p_gender_low
    in_refr_now, _ = is_in_refractory_cooldown(session or {}, physical_state)
    excit_now = physical_state.get("excitement") if isinstance(physical_state.get("excitement"), dict) else {}
    climax_now = physical_state.get("climax_state") if isinstance(physical_state.get("climax_state"), dict) else {}
    male_refr_active = (
        not is_female_pl
        and in_refr_now
        and bool(
            excit_now.get("player_in_refractory")
            or climax_now.get("player_climaxed")
            or excit_now.get("refractory_until_turn")
            or physical_state.get("refractory_until_turn")
        )
    )
    refractory_soft_gated = False
    if male_refr_active and is_check_success and sub_intent in ("intercourse", "anal_give"):
        refractory_soft_gated = True
        sub_intent = "foreplay"
        if selected_act_dict:
            selected_act_dict["sub_intent"] = "foreplay"
            selected_act_dict["_refractory_downgraded_from"] = orig_sub_intent
            if isinstance(selected_act_dict.get("resolved_intent"), dict):
                selected_act_dict["resolved_intent"]["sub_intent"] = "foreplay"
        t_lbl = target_npc or partner_name
        directives.append(
            f"[STAGE DIRECTION — REFRACTORY LIMIT]: {player_name} is still in post-climax refractory recovery and cannot perform penetrative intercourse yet; narrate shifting seamlessly into tender hands/lips foreplay to pleasure {t_lbl} instead."
        )

    if sub_intent:
        _ACT_MAP = {
            "intercourse": "penetrative",
            "oral_give": "oral_give",
            "oral_receive": "oral_receive",
            "oral_mutual": "oral_mutual",
            "manual_give": "manual_give",
            "manual_receive": "manual_receive",
            "manual_mutual": "manual_give",
            "anal_give": "anal_give",
            "anal_receive": "anal_receive",
            "anal_mutual": "anal_give",
            "kiss": "foreplay_nongenital",
            "foreplay": "foreplay_nongenital",
            "aftercare": "none",
            "redress": "none",
        }
        act_type = _ACT_MAP.get(sub_intent, "foreplay_nongenital")
        act_class = {
            "act_type": act_type,
            "player_stimulated": (not refractory_soft_gated) and sub_intent in ("intercourse", "oral_receive", "oral_mutual", "manual_receive", "anal_receive"),
            "partner_stimulated": refractory_soft_gated or sub_intent in ("intercourse", "oral_give", "oral_mutual", "manual_give", "manual_mutual", "anal_give", "anal_mutual"),
            "target_partner": target_npc or partner_name,
        }
    else:
        act_class = classify_intimate_act(
            action_str=action_str,
            intimate_contact_str=str(physical_state.get("intimate_contact") or ""),
            player_name=player_name,
            partner_name=partner_name,
            partner_contact=primary_contact,
        )
        act_type = act_class.get("act_type", "none")

    is_genital_or_escalated = act_type in (
        "oral_give", "oral_receive", "oral_mutual", "manual_give",
        "manual_receive", "penetrative", "anal_give", "anal_receive"
    )

    # Displace clothing for participating actors when check succeeds
    if is_genital_or_escalated and is_check_success:
        actors_dict = physical_state.setdefault("actors", {})
        if target_npc:
            target_list = [t.strip() for t in target_npc.split(",") if t.strip()]
            participating_names = [player_name] + target_list
        else:
            participating_names = [player_name, partner_name]

        for p_n in participating_names:
            if not p_n:
                continue
            matched_k = next(
                (ak for ak in actors_dict.keys() if p_n.lower() in ak.lower() or ak.lower() in p_n.lower()),
                None,
            )
            if not matched_k:
                matched_k = p_n
                actors_dict[matched_k] = {
                    "clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}
                }
            actor_data = actors_dict[matched_k]
            cloth = actor_data.setdefault("clothing", {
                "top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"
            })
            for slot in ("bottom", "under_bottom"):
                curr_val = str(cloth.get(slot, "")).strip().lower()
                if not curr_val or any(k in curr_val for k in ("none", "commando", "off", "removed", "stripped", "displaced")):
                    continue
                cloth[slot] = "Displaced"
            if act_type in ("penetrative", "anal_give", "anal_receive", "oral_mutual"):
                for slot in ("top", "under_top"):
                    curr_val = str(cloth.get(slot, "")).strip().lower()
                    if not curr_val or any(k in curr_val for k in ("none", "n/a", "off", "removed", "stripped", "displaced")):
                        continue
                    cloth[slot] = "Disheveled"

    if sub_intent == "redress":
        from mechanics.social.physical_state import redress_actor_to_canonical
        physical_state["intimate_contact"] = "none"
        if isinstance(physical_state.get("excitement"), dict):
            physical_state["excitement"]["active"] = False
        actors_dict = physical_state.get("actors") if isinstance(physical_state.get("actors"), dict) else {}
        for _ak, _adata in actors_dict.items():
            if isinstance(_adata, dict) and isinstance(_adata.get("clothing"), dict):
                _adata["clothing"] = redress_actor_to_canonical(_adata["clothing"], _adata.get("canonical_outfit"))
        physical_state["dropped_clothing"] = []
    elif selected_act_dict.get("ends_dialogue") or r_intent.get("ends_dialogue") or sub_intent == "aftercare":
        physical_state["intimate_contact"] = "none"
        if isinstance(physical_state.get("excitement"), dict):
            physical_state["excitement"]["active"] = False
    elif is_check_success and (is_genital_or_escalated or refractory_soft_gated):
        t_str = target_npc or partner_name
        physical_state["intimate_contact"] = f"{sub_intent} with {t_str}"
    elif not is_check_success:
        physical_state["intimate_contact"] = "none"

    is_erotic = (
        is_erotic_intimate_contact(physical_state.get("intimate_contact", ""))
        or ((act_type not in ("none", "") or refractory_soft_gated) and is_check_success)
    )
    excitement_res = None

    if is_erotic:
        _pre_margin = None
        if selected_act_dict and isinstance(selected_act_dict.get("check"), dict):
            _chk_d = selected_act_dict["check"]
            if _chk_d.get("roll") is not None and _chk_d.get("requirement") is not None:
                _pre_margin = int(_chk_d["roll"]) - int(_chk_d["requirement"])
        elif selected_act_dict and selected_act_dict.get("check") is not None:
            _chk_o = selected_act_dict["check"]
            if getattr(_chk_o, "roll", None) is not None and getattr(_chk_o, "requirement", None) is not None:
                _pre_margin = int(getattr(_chk_o, "roll")) - int(getattr(_chk_o, "requirement"))
        excitement_res = compute_excitement_step(
            physical_state=physical_state,
            action_str=action_str,
            player_char=player_char,
            partner_contact=primary_contact,
            session=session,
            narrative_str="",
            partner_contacts=partner_contacts,
            sub_intent=orig_sub_intent if refractory_soft_gated else (sub_intent or None),
            target_npc=target_npc or None,
            action_check_margin=_pre_margin,
        )
        session["_pre_turn_excitement_res"] = excitement_res

        if excitement_res:
            # Qualitative zero-number anatomy reaction cues
            anat_mods_map = excitement_res.get("anatomy_modifiers") or {}
            for _n_k, _amod in anat_mods_map.items():
                _pside = _amod.get("penetrator_side")
                _ptier = _amod.get("penetrator_pp_tier")
                if _pside == "player" and _ptier in ("large", "huge"):
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {player_name}'s generous thickness fills and stretches {_n_k} snugly; weave sensations of heavy fullness and breath-stealing depth into {_n_k}'s reaction."
                    )
                elif _pside == "player" and _ptier in ("flat", "small"):
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {player_name}'s compact size glides with gentle, tight friction that invites unhurried closeness and steady, attentive rhythm to satisfy {_n_k}."
                    )
                elif _pside == "partner" and _ptier in ("large", "huge"):
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_n_k}'s thick proportions press deeply into {player_name}; highlight intense stretching fullness and overwhelming sensation."
                    )
                elif _pside == "partner" and _ptier in ("flat", "small"):
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_n_k}'s modest size moves smoothly with light, focused contact rather than overwhelming depth."
                    )

            seen_cue_pairs: set[tuple[str, str, str]] = set()
            for _tpref in excitement_res.get("triggered_body_preferences") or []:
                _npc_nm = str(_tpref.get("npc_name") or partner_name).strip()
                _sent = str(_tpref.get("sentiment") or "").strip()
                _part = str(_tpref.get("part") or "").strip()
                _pair = (_npc_nm, _sent, _part)
                if not _npc_nm or _pair in seen_cue_pairs:
                    continue
                seen_cue_pairs.add(_pair)
                if _part == "bb" and _sent == "like":
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} is visibly captivated by {player_name}'s bust contours—show lingering admiring glances, ragged breath, or eager cradling."
                    )
                elif _part == "bb" and _sent == "dislike":
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} shows understated or mild response toward {player_name}'s chest, naturally gravitating to other caresses without discourtesy."
                    )
                elif _part == "ass" and _sent == "like":
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} is clearly thrilled by {player_name}'s rear silhouette—weave appreciative grips, heated focus, or eager rhythm into the moment."
                    )
                elif _part == "ass" and _sent == "dislike":
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} reacts more neutrally to {player_name}'s rear contours, letting attention drift naturally toward other intimate focal points."
                    )
                elif _part == "height" and _sent == "like":
                    _gap = int(_tpref.get("gap") or 1)
                    _scale_phrase = (
                        "dramatic height contrast"
                        if _gap >= 2
                        else "noticeable height difference"
                    )
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} is visibly charmed and stirred by the {_scale_phrase} with {player_name}—weave subtle posture awareness, upturned or downward gazes, and natural physical closeness into {_npc_nm}'s reaction."
                    )
                elif _part == "height" and _sent == "dislike":
                    directives.append(
                        f"[ANATOMY REACTION CUE]: {_npc_nm} finds the height pairing slightly awkward to align at first, gently adjusting posture and angle for comfort without discourtesy."
                    )

            # Qualitative zero-number preference, kink, and turn-off cues
            pref_mods_map = excitement_res.get("preference_modifiers") or {}
            for _p_nm, _pmod in pref_mods_map.items():
                if _pmod.get("matched_kinks"):
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: Indulging {_p_nm}'s active kink ({', '.join(_pmod['matched_kinks'])}) sends an electric shiver of thrilled surrender through them."
                    )
                if _pmod.get("matched_desires"):
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: Touching upon {_p_nm}'s desire ({', '.join(_pmod['matched_desires'])}) sparks ragged breath and eager closeness."
                    )
                if _pmod.get("matched_liked_acts"):
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm} enthusiastically melts into a preferred act ({', '.join(_pmod['matched_liked_acts'])})."
                    )
                if _pmod.get("matched_disliked_acts"):
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm} stiffens slightly through a disliked act ({', '.join(_pmod['matched_disliked_acts'])}), enduring it with muted enthusiasm."
                    )
                if _pmod.get("giving_service_reward"):
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm} visibly thrills with devoted warmth as they focus on pleasing {player_name}."
                    )
                _ocue = str(_pmod.get("openness_cue") or "").strip()
                if _ocue == "warmup_rushed":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm} tenses and flusters at the sudden rush before catching their breath—slower reassurance will win deeper response."
                    )
                elif _ocue == "tender_warmup":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm}'s guard melts visibly under patient, tender warm-up and gentle reassurance."
                    )
                elif _ocue == "hidden_fire_unleashed":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: Behind closed doors and trusting you, {_p_nm}'s modest veil slips—their hidden intensity takes over fiercely."
                    )
                elif _ocue == "bystander_hesitation":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: Aware of nearby strangers, {_p_nm} stays self-conscious and restrained rather than letting go."
                    )
                elif _ocue == "bystander_thrill":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: The nearness of unsuspecting onlookers sparks an audacious thrill through {_p_nm}."
                    )
                _mcue = str(_pmod.get("multipartner_cue") or "").strip()
                if _mcue == "bold_group":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: {_p_nm} leans eagerly into the shared group heat without hesitation."
                    )
                elif _mcue == "shy_group":
                    directives.append(
                        f"[PREFERENCE & SYNERGY CUE]: Sharing the moment with multiple partners leaves {_p_nm} shyly flustered and seeking reassurance."
                    )
            if excitement_res.get("turn_off_terminated"):
                directives.append(
                    "[TURN-OFF TERMINATION DIRECTIVE]: A partner's tolerance snapped after hitting their turn-off; they abruptly pull away, put a firm stop to the intimate encounter, and refuse to continue."
                )

            if excitement_res.get("player_climaxed") and not male_refr_active:
                directives.append(
                    f"[MANDATORY CLIMAX DIRECTIVE]: Player character {player_name} has deterministically reached climax (meter at {excitement_res.get('player_meter', 100)}%). Narrate {player_name}'s peak/release vividly and authentically."
                )
            if excitement_res.get("partner_climaxed"):
                newly_climaxes = [k for k, v in (excitement_res.get("partner_climaxes") or {}).items() if v]
                p_clim_str = ", ".join(newly_climaxes) if newly_climaxes else partner_name
                directives.append(
                    f"[MANDATORY CLIMAX DIRECTIVE]: {p_clim_str} has deterministically reached climax (meter at 100%). Narrate their peak/release vividly and authentically."
                )

    return {
        "action_classified": act_class,
        "excitement_res": excitement_res,
        "physical_state": physical_state,
        "directives": directives,
    }

