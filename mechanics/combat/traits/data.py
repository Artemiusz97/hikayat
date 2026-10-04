from __future__ import annotations
"""
Data tables, archetype registries, and preference catalogs for Hikayat traits.
"""
from typing import Dict, Any, List, Optional, Tuple, Set

# -----------------------------------------------------------------------------
# MASTER TRAIT REGISTRY
# -----------------------------------------------------------------------------

TRAIT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "diligent": {
        "id": "diligent",
        "label": "Diligent",
        "category": "Academic & Work Ethic",
        "badge": "Favors INT checks; +2 affinity on work/academic focus; hates slacking",
        "incompatible_with": {"delinquent", "eccentric", "playful"},
        "speech_style": "Speaks with articulate, organized, and focused diction. Frequently references schedules, deadlines, duties, and practical goals. Dislikes frivolous rumors or unstructured rambling.",
        "mannerisms": [
            "Neatens notes, pens, or tools in precise alignment",
            "Glances at watch or phone to check the schedule between sentences",
            "Adjusts glasses thoughtfully while reviewing details",
            "Straightens posture alertly when discussing plans or responsibilities"
        ],
        "dc_modifiers": {"INT": -1, "CHA": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.0,
        "affinity_loss_mult": 1.3,
        "favored_stances": ["study", "academic", "planning", "duty", "punctual", "diligence", "responsibility", "organize"],
        "disliked_stances": ["slack", "skip", "lazy", "frivolous", "procrastinate", "careless", "cheat"]
    },
    "guarded": {
        "id": "guarded",
        "label": "Guarded",
        "category": "Social Demeanor",
        "badge": "+2 DC on CHA checks; slower affinity gain; double penalty on failures",
        "incompatible_with": {"warm", "flirtatious", "playful"},
        "speech_style": "Speaks in measured, clipped, and cautious sentences. Keeps personal history and emotional vulnerability strictly hidden. Analyzes motives before answering questions.",
        "mannerisms": [
            "Crosses arms and maintains a cautious physical distance",
            "Holds an unblinking, evaluative gaze before responding",
            "Taps fingers slowly against forearm in deep contemplation",
            "Subtly angles body toward the exit while conversing"
        ],
        "dc_modifiers": {"CHA": 2, "INT": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 0.7,
        "affinity_loss_mult": 1.6,
        "favored_stances": ["respect_boundaries", "patience", "sincerity", "give_space", "tactful", "reliable"],
        "disliked_stances": ["prying", "pushy", "interrogate", "demanding", "overly_familiar", "invasive"]
    },
    "playful": {
        "id": "playful",
        "label": "Playful",
        "category": "Social Demeanor",
        "badge": "Favors CHA banter (-1 DC); high affinity variance; laughs off minor missteps",
        "incompatible_with": {"stoic", "cynical", "guarded", "diligent"},
        "speech_style": "Uses lighthearted sarcasm, affectionate teasing, witty rhetorical jabs, and casual colloquialisms. Easily finds humor in awkward situations.",
        "mannerisms": [
            "Tilts head with a knowing smirk and playful eye-sparkle",
            "Leans in closer with an amused grin to provoke a reaction",
            "Winks or playfully gestures with hands while delivering punchlines",
            "Chuckles under breath with an infectious, relaxed smile"
        ],
        "dc_modifiers": {"CHA": -1, "LUK": -1, "INT": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 0.8,
        "favored_stances": ["teasing", "banter", "humor", "joke", "wit", "playful", "fun", "spontaneous"],
        "disliked_stances": ["overly_serious", "killjoy", "stiff", "scolding", "pompous", "moralizing"]
    },
    "proud": {
        "id": "proud",
        "label": "Proud",
        "category": "Ego & Standing",
        "badge": "Favors STR/Resolve; heavy affinity penalty (-4) if patronized or dismissed",
        "incompatible_with": {"hesitant", "gentle", "devoted"},
        "speech_style": "Speaks with absolute confidence, elevated vocabulary, and a commanding presence. Refuses to sound uncertain or needy. Values dignity, status, and competence.",
        "mannerisms": [
            "Stands tall with shoulders squared and chin tilted slightly upward",
            "Scoffs softly with an amused smirk when an opponent falters",
            "Flips hair or adjusts collar with effortless aristocratic poise",
            "Maintains commanding, unwavering eye contact"
        ],
        "dc_modifiers": {"STR": -1, "CHA": 1, "INT": 0, "PER": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 0.9,
        "affinity_loss_mult": 1.5,
        "favored_stances": ["acknowledge_skill", "praise_accomplishment", "respect_status", "competence", "honor", "challenge"],
        "disliked_stances": ["patronize", "condescend", "pity", "insult_pride", "dismiss", "mock", "underestimate"]
    },
    "gentle": {
        "id": "gentle",
        "label": "Gentle",
        "category": "Emotional Temperament",
        "badge": "Favors PER listening (-1 DC); severe penalty on aggressive/intimidating actions",
        "incompatible_with": {"blunt", "cynical", "delinquent", "proud"},
        "speech_style": "Soft-spoken, polite, and considerate. Speaks with soothing warmth, gentle pauses, and earnest concern for the well-being and feelings of others.",
        "mannerisms": [
            "Offers a warm, reassuring smile with gentle, kind eyes",
            "Clasps hands lightly in front of chest while listening intently",
            "Tends to speak in a lower, melodic tone to soothe tension",
            "Nods encouragingly with genuine empathy"
        ],
        "dc_modifiers": {"PER": -1, "CHA": -1, "STR": 2, "INT": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.4,
        "favored_stances": ["kindness", "gentle", "comfort", "listen", "empathy", "soft", "support", "care"],
        "disliked_stances": ["intimidate", "shout", "harsh", "cruel", "aggressive", "violence", "threaten"]
    },
    "blunt": {
        "id": "blunt",
        "label": "Blunt",
        "category": "Social Demeanor",
        "badge": "Rejects sycophancy (-2 affinity on flattery); respects direct, honest choices",
        "incompatible_with": {"gentle", "hesitant", "flirtatious", "devoted"},
        "speech_style": "Speaks with unvarnished, brutal honesty. Cuts straight to the point without pleasantries, sugarcoating, or polite preamble. Disdains indirect hints.",
        "mannerisms": [
            "Speaks flatly without sugarcoating or diplomatic hesitations",
            "Crosses arms and sighs at roundabout or evasive phrasing",
            "Points directly with a finger when emphasizing a raw truth",
            "Shrugs with nonchalant candor when stating hard facts"
        ],
        "dc_modifiers": {"CHA": 1, "INT": 0, "PER": -1, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.0,
        "affinity_loss_mult": 1.1,
        "favored_stances": ["direct_honesty", "candor", "cut_to_chase", "frank", "unfiltered", "straightforward"],
        "disliked_stances": ["flattery", "beating_around_bush", "sweet_talk", "deceit", "fake_politeness", "excuses"]
    },
    "ambitious": {
        "id": "ambitious",
        "label": "Ambitious",
        "category": "Drive & Motivation",
        "badge": "Rewards strategic cooperation; dislikes small-mindedness or lack of drive",
        "incompatible_with": {"hesitant", "stoic"},
        "speech_style": "Speaks with visionary enthusiasm and calculating foresight. Evaluates long-term alliances, competitive advantages, and transformative goals.",
        "mannerisms": [
            "Leans forward with focused, gleaming eyes when discussing opportunities",
            "Taps finger against tabletop in rhythmic, strategic calculation",
            "Paces with energetic, driven stride while outlining ambitions",
            "Smirks with resolute determination at high-stakes challenges"
        ],
        "dc_modifiers": {"INT": -1, "CHA": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.2,
        "favored_stances": ["strategy", "alliance", "ambition", "growth", "high_stakes", "initiative", "excellence"],
        "disliked_stances": ["defeatist", "quitting", "aimless", "mediocrity", "slacking", "aimless_chatter"]
    },
    "delinquent": {
        "id": "delinquent",
        "label": "Delinquent",
        "category": "Subversive / Street",
        "badge": "Rebels against school rules/authority; respects guts and street-smarts",
        "incompatible_with": {"diligent", "perfectionist", "scholarly", "gentle"},
        "speech_style": "Uses rough street slang, deadpan sarcasm, and rebellious dismissals of authority figures. Dislikes rules, pompous honorifics, and hall monitors.",
        "mannerisms": [
            "Slouches casually with hands shoved deep into coat/trouser pockets",
            "Leans against the wall or doorframe with a defiant, bored expression",
            "Clicks tongue with mild annoyance when lectured on rules",
            "Gives a sharp, lopsided smirk when recognizing a fellow rebel"
        ],
        "dc_modifiers": {"STR": -1, "AGI": -1, "CHA": 1, "INT": 1, "PER": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 0.9,
        "affinity_loss_mult": 1.3,
        "favored_stances": ["defiance", "street_smarts", "boldness", "loyalty", "rebellion", "guts", "casual"],
        "disliked_stances": ["snitching", "rule_policing", "teacher_pet", "scolding", "preachy", "haughty"]
    },
    "scholarly": {
        "id": "scholarly",
        "label": "Scholarly",
        "category": "Academic & Intellectual",
        "badge": "Favors INT/Lore checks (-2 DC); loses affinity on reckless/ignorant behavior",
        "incompatible_with": {"delinquent", "mischievous", "hesitant"},
        "speech_style": "Eloquent, deeply analytical, and fascinated by theory, codex lore, history, and scientific mechanisms. Explains phenomena with academic enthusiasm.",
        "mannerisms": [
            "Opens a notebook or data slate with brisk, eager curiosity",
            "Taps pen thoughtfully against temple while considering hypotheses",
            "Speaks rapidly with bright, excited eyes when delving into obscure trivia",
            "Gestures methodically with open hands while breaking down complex concepts"
        ],
        "dc_modifiers": {"INT": -2, "PER": -1, "STR": 1, "CHA": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.2,
        "favored_stances": ["lore", "research", "intellectual", "curiosity", "theory", "investigation", "analysis"],
        "disliked_stances": ["willful_ignorance", "superstition", "recklessness", "dismissing_facts", "destroying_books"]
    },
    "warm": {
        "id": "warm",
        "label": "Warm",
        "category": "Social Demeanor",
        "badge": "+20% bonus on all positive affinity gains; quick to make friends",
        "incompatible_with": {"guarded", "cynical", "stoic"},
        "speech_style": "Open-hearted, welcoming, and sincere. Easily expresses appreciation, gives cheerful greetings, and naturally includes others in conversations.",
        "mannerisms": [
            "Greets with a bright, luminous smile and welcoming posture",
            "Reaches out with a friendly hand gesture or light supportive shoulder touch",
            "Laughs heartily and comfortably, putting everyone around at ease",
            "Maintains warm, engaging eye contact that radiates genuine interest"
        ],
        "dc_modifiers": {"CHA": -1, "PER": 0, "INT": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.3,
        "affinity_loss_mult": 0.9,
        "favored_stances": ["friendliness", "hospitality", "inclusion", "compliment", "gratitude", "sharing", "warmth"],
        "disliked_stances": ["cold_shoulder", "hostility", "excluding_others", "rudeness", "spite", "mockery"]
    },
    "cynical": {
        "id": "cynical",
        "label": "Cynical",
        "category": "Worldview & Skepticism",
        "badge": "Skeptical of altruism (+2 DC on naive CHA); respects pragmatic leverage",
        "incompatible_with": {"warm", "idealistic", "gentle", "devoted", "playful"},
        "speech_style": "Deadpan, sarcastic, and world-weary. Questions noble platitudes and assumes everyone operates on hidden self-interest or pragmatic incentives.",
        "mannerisms": [
            "Rolls eyes with a dry, knowing smirk at grandiose heroics",
            "Leans back with arms folded, waiting for the hidden catch to be revealed",
            "Chuckles wryly under breath when idealistic promises are made",
            "Raises a single skeptical eyebrow with a piercing gaze"
        ],
        "dc_modifiers": {"CHA": 2, "INT": -1, "PER": -1, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 0.8,
        "affinity_loss_mult": 1.1,
        "favored_stances": ["pragmatism", "realism", "mutual_benefit", "contract", "candid_flaws", "hard_truths"],
        "disliked_stances": ["naive_idealism", "fairy_tale_promises", "moral_grandstanding", "blind_trust"]
    },
    "competitive": {
        "id": "competitive",
        "label": "Competitive",
        "category": "Athletic & Physical",
        "badge": "Favors physical/skill contests; thrilled by friendly wagers and rivalries",
        "incompatible_with": {"hesitant", "stoic"},
        "speech_style": "Energetic, dynamic, and spirited. Constantly measures progress, challenges peers to improve, and views obstacles as exciting contests to conquer.",
        "mannerisms": [
            "Cracks knuckles or stretches limbs with eager athletic energy",
            "Flashes a spirited, competitive grin before stepping into action",
            "Leans forward with bouncing energy, ready to sprint or compete",
            "Points a thumb at chest with confident sporting pride"
        ],
        "dc_modifiers": {"STR": -1, "AGI": -1, "END": -1, "CHA": 0, "INT": 0, "PER": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.1,
        "favored_stances": ["challenge", "contest", "rivalry", "athletics", "training", "wager", "pushing_limits"],
        "disliked_stances": ["giving_up", "slacking", "poor_sportsmanship", "cheating", "laziness", "making_excuses"]
    },
    "stoic": {
        "id": "stoic",
        "label": "Stoic",
        "category": "Emotional Temperament",
        "badge": "Immune to emotional intimidation; values steadfast calm and composure",
        "incompatible_with": {"playful", "flirtatious", "warm", "competitive", "ambitious", "eccentric", "mischievous"},
        "speech_style": "Unflinching, concise, and deeply composed. Rarely raises voice or shows visible agitation. Expresses loyalty and resolve through actions rather than words.",
        "mannerisms": [
            "Maintains an impenetrable, calm poker face in all situations",
            "Nods once with solemn, absolute finality",
            "Breathes slowly and evenly, unbothered by ambient chaos",
            "Crosses hands calmly behind back in a disciplined stance"
        ],
        "dc_modifiers": {"END": -2, "STR": -1, "CHA": 1, "INT": 0, "PER": 0, "AGI": 0, "LUK": 0},
        "affinity_gain_mult": 0.8,
        "affinity_loss_mult": 0.8,
        "favored_stances": ["composure", "calm_resolve", "discipline", "steadfastness", "tactical_silence", "duty"],
        "disliked_stances": ["whining", "hysteria", "dramatics", "panicking", "undisciplined_outbursts"]
    },
    "perfectionist": {
        "id": "perfectionist",
        "label": "Perfectionist",
        "category": "Academic & Standards",
        "badge": "Demands flawless execution; heavy penalty on sloppy or rushed actions",
        "incompatible_with": {"delinquent", "eccentric", "mischievous"},
        "speech_style": "Extremely precise, detail-oriented, and exacting. Noticeably winces at sloppy craftsmanship, grammatical errors, or half-hearted compromises.",
        "mannerisms": [
            "Straightens misaligned objects or papers with compulsive neatness",
            "Runs a finger along a surface or edge to inspect precision",
            "Sighs with focused concentration while fine-tuning small details",
            "Examines work with a magnifying lens or narrow, critical eye"
        ],
        "dc_modifiers": {"INT": -1, "PER": -1, "CHA": 1, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 0.9,
        "affinity_loss_mult": 1.5,
        "favored_stances": ["flawless_execution", "precision", "high_standards", "thoroughness", "quality", "mastery"],
        "disliked_stances": ["sloppy_work", "half_baked", "rushing", "shortcuts", "careless_mistakes", "laziness"]
    },
    "flirtatious": {
        "id": "flirtatious",
        "label": "Flirtatious",
        "category": "Social & Romance",
        "badge": "Favors CHA charm checks (-2 DC); loves bold romantic banter and compliments",
        "incompatible_with": {"guarded", "blunt", "stoic", "hesitant"},
        "speech_style": "Charismatic, suggestive, and playfully romantic. Uses lingering eye contact, double entendres, velvety tones, and charming compliments.",
        "mannerisms": [
            "Plays with a strand of hair while offering a smoldering, half-lidded glance",
            "Leans in delightfully close, invading personal space with scented warmth",
            "Bites lower lip gently with a teasing, captivating smile",
            "Traces a finger lightly along their own glass or collarbone"
        ],
        "dc_modifiers": {"CHA": -2, "LUK": -1, "INT": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0},
        "affinity_gain_mult": 1.3,
        "affinity_loss_mult": 1.0,
        "favored_stances": ["flirtation", "charming_compliment", "bold_romantic", "playful_touch", "charisma", "teasing"],
        "disliked_stances": ["oblivious", "priggish", "scolding_romance", "stiffness", "awkward_rejection"]
    },
    "mischievous": {
        "id": "mischievous",
        "label": "Mischievous",
        "category": "Subversive / Quirky",
        "badge": "Favors AGI/LUK stealth and trickery (-1 DC); loves harmless pranks & secrets",
        "incompatible_with": {"scholarly", "perfectionist", "stoic"},
        "speech_style": "Sly, conspiratorial, and whispery. Loves sharing juicy secrets, plotting clever harmless schemes, and bending arbitrary rules for fun.",
        "mannerisms": [
            "Presses an index finger to lips with a secretive, conspiratorial wink",
            "Hides an amused chuckle behind a hand while looking around the room",
            "Taps pocket where a clever hidden trinket or prank is stashed",
            "Tilts head with a fox-like grin when a chaotic idea strikes"
        ],
        "dc_modifiers": {"AGI": -1, "LUK": -1, "CHA": 0, "INT": 0, "PER": 0, "STR": 0, "END": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 0.9,
        "favored_stances": ["pranks", "secrets", "stealth", "clever_schemes", "harmless_chaos", "mischief", "rule_bending"],
        "disliked_stances": ["tattletale", "snitching", "party_pooper", "rigid_rules", "killjoy", "stiffness"]
    },
    "hesitant": {
        "id": "hesitant",
        "label": "Hesitant",
        "category": "Emotional Temperament",
        "badge": "Easily overwhelmed by pressure; requires patient, gentle encouragement",
        "incompatible_with": {"proud", "blunt", "competitive", "ambitious", "flirtatious", "scholarly"},
        "speech_style": "Timid, modest, and self-conscious. Frequently uses self-deprecating phrasing, pauses nervously, and downplays their own immense talents.",
        "mannerisms": [
            "Fiddles nervously with uniform sleeves or hem of clothing",
            "Glances down and blushes softly when receiving unexpected praise",
            "Speaks softly, clearing throat lightly before offering ideas",
            "Tucks hair behind ear with hesitant, bashful modesty"
        ],
        "dc_modifiers": {"PER": -1, "CHA": 0, "STR": 2, "INT": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.4,
        "favored_stances": ["gentle_encouragement", "patience", "kind_reassurance", "listening", "safe_space", "soft"],
        "disliked_stances": ["rushing", "putting_on_spot", "shouting", "harsh_criticism", "aggressive_pressure"]
    },
    "idealistic": {
        "id": "idealistic",
        "label": "Idealistic",
        "category": "Worldview & Drive",
        "badge": "Inspired by noble heroics & unity; deeply saddened by cynical betrayal",
        "incompatible_with": {"cynical"},
        "speech_style": "Passionate, hopeful, and inspiring. Believes in the best of people, justice, cooperation, and the possibility of a brighter future for the school/world.",
        "mannerisms": [
            "Speaks with bright, earnest eyes reflecting genuine conviction",
            "Clenches fist over heart when affirming a moral vow",
            "Leans forward with passionate, inspiring momentum in dialogue",
            "Smiles brightly at acts of unselfish kindness"
        ],
        "dc_modifiers": {"CHA": -1, "INT": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.3,
        "affinity_loss_mult": 1.5,
        "favored_stances": ["noble_ideals", "protecting_others", "justice", "unselfish_help", "hope", "solidarity"],
        "disliked_stances": ["betrayal", "cynical_exploitation", "abandoning_allies", "selfishness", "cruelty"]
    },
    "eccentric": {
        "id": "eccentric",
        "label": "Eccentric",
        "category": "Subversive / Quirky",
        "badge": "Fascinated by bizarre phenomena & unusual ideas; disdains boring norms",
        "incompatible_with": {"perfectionist", "stoic", "diligent"},
        "speech_style": "Unconventional, wildly imaginative, and poetic. Uses vivid metaphors, sudden leaps of creative logic, and enthusiastic tangents about strange fascinations.",
        "mannerisms": [
            "Gesticulates wildly with expressive hands while describing strange concepts",
            "Stares intensely at an unusual detail with fascinated wonder",
            "Mumbles rapid-fire internal monologues before abruptly turning to the player",
            "Taps feet in an eccentric, syncopated rhythm while thinking"
        ],
        "dc_modifiers": {"INT": -1, "LUK": -1, "CHA": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 0.9,
        "favored_stances": ["unusual_ideas", "bizarre_theories", "creative_thinking", "open_mindedness", "curiosity"],
        "disliked_stances": ["rigid_orthodoxy", "calling_them_crazy", "close_minded", "boring_routine", "dismissal"]
    },
    "devoted": {
        "id": "devoted",
        "label": "Devoted",
        "category": "Loyalty & Attachment",
        "badge": "Fiercely loyal to close allies; grants +2 affinity when defending or backing them",
        "incompatible_with": {"cynical", "proud", "blunt"},
        "speech_style": "Steadfast, supportive, and fiercely protective. Speaks with enduring fidelity, attentive care, and deep appreciation for shared bonds.",
        "mannerisms": [
            "Steps instinctively into a protective or supportive position near allies",
            "Watches with attentive, caring eyes to anticipate needs or comfort",
            "Places hand over chest when swearing enduring support",
            "Offers a gentle, unwavering nod of unconditional trust"
        ],
        "dc_modifiers": {"CHA": -1, "END": -1, "INT": 0, "PER": 0, "STR": 0, "AGI": 0, "LUK": 0},
        "affinity_gain_mult": 1.3,
        "affinity_loss_mult": 1.4,
        "favored_stances": ["loyalty", "standing_by_them", "backing_up", "protection", "shared_bonds", "gratitude"],
        "disliked_stances": ["abandonment", "backstabbing", "disloyalty", "mocking_dedication", "breaking_trust"]
    },
    "earnest": {
        "id": "earnest",
        "label": "Earnest",
        "category": "Emotional Temperament",
        "badge": "+2 affinity on sincere promises and honest efforts; dislikes cynicism and mockery",
        "incompatible_with": {"cynical", "mischievous", "delinquent"},
        "speech_style": "Speaks with openhearted sincerity, genuine enthusiasm, and honest transparency. Takes promises and commitments to heart.",
        "mannerisms": [
            "Looks directly into your eyes with an open, honest expression",
            "Nods with heartfelt agreement when discussing shared commitments",
            "Clasps hands earnestly while speaking from the heart",
            "Smiles with genuine, unforced warmth at sincere gestures"
        ],
        "dc_modifiers": {"CHA": -1, "PER": 0, "INT": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.3,
        "favored_stances": ["sincerity", "honesty", "promises", "earnest_effort", "genuine", "truth"],
        "disliked_stances": ["cynicism", "mockery", "sarcasm", "breaking_promises", "deceit"]
    },
    "anxious": {
        "id": "anxious",
        "label": "Anxious",
        "category": "Emotional Temperament",
        "badge": "Favors gentle reassurance; penalizes sudden aggressive, loud, or chaotic choices",
        "incompatible_with": {"proud", "delinquent", "flirtatious"},
        "speech_style": "Speaks with hesitant cadences, self-correcting pauses, and cautious inquiries. Quick to worry about worst-case scenarios.",
        "mannerisms": [
            "Fidgets with pen, sleeve, or hem of shirt while speaking",
            "Glances around nervously before answering personal questions",
            "Lets out a small, relieved breath when things proceed smoothly",
            "Tucks stray hair behind ear with slightly trembling fingers"
        ],
        "dc_modifiers": {"CHA": 1, "PER": -1, "INT": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.4,
        "favored_stances": ["reassurance", "gentle", "patience", "calm", "safe", "support"],
        "disliked_stances": ["aggression", "shouting", "chaos", "sudden_pressure", "mockery"]
    },
    "appreciative": {
        "id": "appreciative",
        "label": "Appreciative",
        "category": "Social Demeanor",
        "badge": "+20% bonus affinity when praised or thanked; dislikes ingratitude and entitlement",
        "incompatible_with": {"cynical", "proud"},
        "speech_style": "Speaks with heartfelt gratitude, attentive politeness, and enthusiastic validation of others' hard work.",
        "mannerisms": [
            "Bows or nods deeply in grateful acknowledgment",
            "Beams with genuine happiness when receiving sincere compliments",
            "Places hand over heart when expressing thankfulness",
            "Offers a bright, encouraging smile to anyone helping out"
        ],
        "dc_modifiers": {"CHA": -1, "PER": 0, "INT": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.25,
        "affinity_loss_mult": 1.1,
        "favored_stances": ["gratitude", "thankful", "praise", "acknowledgment", "kindness"],
        "disliked_stances": ["ingratitude", "entitlement", "taking_for_granted", "dismissal"]
    },
    "methodical": {
        "id": "methodical",
        "label": "Methodical",
        "category": "Academic & Work Ethic",
        "badge": "Favors INT/Planning checks (-1 DC); +2 affinity on organized choices; hates rushing",
        "incompatible_with": {"delinquent", "eccentric"},
        "speech_style": "Speaks in structured, step-by-step logic. Prefers organized outlines, clear procedures, and verified facts.",
        "mannerisms": [
            "Checks items off a mental or physical checklist with quiet satisfaction",
            "Lines up notebooks, pens, or tools in neat parallel rows",
            "Taps index finger thoughtfully while considering step sequence",
            "Pauses to ensure all prerequisites are met before proceeding"
        ],
        "dc_modifiers": {"INT": -1, "CHA": 0, "PER": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.0,
        "affinity_loss_mult": 1.2,
        "favored_stances": ["planning", "organization", "step_by_step", "preparation", "structure"],
        "disliked_stances": ["rushing", "carelessness", "chaos", "skipping_steps", "disorder"]
    },
    "commanding": {
        "id": "commanding",
        "label": "Commanding",
        "category": "Leadership & Authority",
        "badge": "Favors CHA leadership; +2 affinity when following protocol; penalizes insubordination",
        "incompatible_with": {"hesitant", "anxious"},
        "speech_style": "Speaks with clear authority, crisp decisiveness, and commanding composure. Expects respect, order, and competence.",
        "mannerisms": [
            "Stands with back straight and hands clasped behind back",
            "Projects voice clearly across the room without shouting",
            "Gives a decisive, authoritative nod when an order is acknowledged",
            "Maintains steady, evaluative eye contact that demands attention"
        ],
        "dc_modifiers": {"CHA": -1, "STR": -1, "INT": 0, "PER": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.0,
        "affinity_loss_mult": 1.5,
        "favored_stances": ["leadership", "discipline", "protocol", "respect", "competence"],
        "disliked_stances": ["insubordination", "chaos", "slacking", "disrespect", "insolence"]
    },
    "perceptive": {
        "id": "perceptive",
        "label": "Perceptive",
        "category": "Intellect & Insight",
        "badge": "Favors PER checks (-1 DC); detects subtle cues and hidden motives; dislikes deception",
        "incompatible_with": {"hesitant"},
        "speech_style": "Speaks with sharp observation, noting non-verbal tells, hidden shifts in mood, and underlying patterns.",
        "mannerisms": [
            "Tilts head slightly with narrowing eyes as if reading between the lines",
            "Catches micro-expressions before the speaker finishes their sentence",
            "Taps chin thoughtfully while analyzing motives",
            "Offers a knowing, insightful smirk when confirming a deduction"
        ],
        "dc_modifiers": {"PER": -1, "INT": -1, "CHA": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.3,
        "favored_stances": ["insight", "observation", "truth", "subtlety", "awareness"],
        "disliked_stances": ["deception", "lying", "bluffing", "shallow_thinking"]
    },
    "protective": {
        "id": "protective",
        "label": "Protective",
        "category": "Loyalty & Attachment",
        "badge": "Fiercely defends companions; +2 affinity when standing up for friends; hates bullies",
        "incompatible_with": {"cynical"},
        "speech_style": "Speaks with staunch resolve, watchful care, and unwavering loyalty. Always keeps an eye out for potential threats to others.",
        "mannerisms": [
            "Steps slightly forward to place themselves between danger and companions",
            "Scans the perimeter alertly before settling into conversation",
            "Crosses arms over chest with a vigilant, watchful presence",
            "Pats a friend's shoulder reassuringly with a steady hand"
        ],
        "dc_modifiers": {"STR": -1, "END": -1, "CHA": 0, "INT": 0, "PER": 0, "AGI": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.4,
        "favored_stances": ["protection", "standing_up", "loyalty", "defense", "courage"],
        "disliked_stances": ["bullying", "abandonment", "cowardice", "endangering_others"]
    },
    "honorable": {
        "id": "honorable",
        "label": "Honorable",
        "category": "Morality & Honor",
        "badge": "Favors direct, fair choices; heavy affinity penalty (-4) on underhanded tactics or cheating",
        "incompatible_with": {"mischievous", "delinquent"},
        "speech_style": "Speaks with righteous conviction, fairness, and unwavering moral clarity. Holds both self and others to a strict standard of honor.",
        "mannerisms": [
            "Extends an open, firm handshake to seal agreements",
            "Stands with unyielding, principled posture",
            "Meets eyes squarely without flinching or looking away",
            "Places hand on chest in solemn commitment"
        ],
        "dc_modifiers": {"STR": -1, "CHA": 0, "PER": 0, "INT": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.6,
        "favored_stances": ["honor", "fairness", "integrity", "keeping_word", "courage"],
        "disliked_stances": ["cheating", "underhanded", "dishonor", "backstabbing", "cowardice"]
    },
    "strategic": {
        "id": "strategic",
        "label": "Strategic",
        "category": "Drive & Motivation",
        "badge": "Favors tactical foresight; +2 affinity on well-prepared plans; hates reckless gambles",
        "incompatible_with": {"hesitant"},
        "speech_style": "Speaks in terms of leverage, preparation, contingencies, and objectives. Evaluates the downstream effects of every decision.",
        "mannerisms": [
            "Traces lines or points on a surface as if mapping out moves on a chessboard",
            "Pauses calculatingly before committing to a course of action",
            "Adjusts glasses or tilts head with a confident, analytical expression",
            "Smirks knowingly when a predicted outcome unfolds exactly as planned"
        ],
        "dc_modifiers": {"INT": -1, "PER": -1, "CHA": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.1,
        "affinity_loss_mult": 1.2,
        "favored_stances": ["strategy", "planning", "tactics", "foresight", "leverage"],
        "disliked_stances": ["reckless", "impulsive", "unprepared", "gambling", "careless"]
    },
    "diplomatic": {
        "id": "diplomatic",
        "label": "Diplomatic",
        "category": "Social Demeanor",
        "badge": "Favors peaceful compromise (-1 CHA DC); +2 affinity on defusing conflict; hates drama",
        "incompatible_with": {"blunt", "delinquent"},
        "speech_style": "Speaks with tactful poise, balanced phrasing, and respectful courtesy. Seeks common ground and mutual benefit in all interactions.",
        "mannerisms": [
            "Gestures with open, welcoming hands to defuse rising tension",
            "Listens patiently with an attentive, neutral nod before responding",
            "Offers a polite, reassuring smile that puts everyone at ease",
            "Carefully modulates tone of voice to remain calm and persuasive"
        ],
        "dc_modifiers": {"CHA": -1, "PER": 0, "INT": 0, "STR": 0, "AGI": 0, "END": 0, "LUK": 0},
        "affinity_gain_mult": 1.2,
        "affinity_loss_mult": 1.2,
        "favored_stances": ["compromise", "mediation", "diplomacy", "peace", "courtesy"],
        "disliked_stances": ["drama", "needless_conflict", "provocation", "rudeness", "insults"]
    }
}




# -----------------------------------------------------------------------------
# GROUNDED LIKES & DISLIKES POOLS
# -----------------------------------------------------------------------------

# Solid Foods (Tied to generate_food_name)
GROUNDED_FOOD_LIKES: List[str] = [
    "Matcha Melon Pan",
    "Strawberry Parfait",
    "Special Tonkatsu Bento Box",
    "Sweet Cinnamon Roll",
    "Crispy Pork Cutlet Sandwich",
    "Triple-Layer Berry Celebration Cake",
    "Glazed Honey Apple Tart",
    "Roast Boar Stew with Dumplings",
    "Grand Dragonfire Banquet Platter",
    "Crispy Salted Fish Skewer"
]

GROUNDED_FOOD_DISLIKES: List[str] = [
    "Dislikes Overly Sweet Desserts",
    "Dislikes Spicy Food",
    "Dislikes Greasy Street Food",
    "Dislikes Bland Energy Bars",
    "Dislikes Stale Vending Machine Snacks",
    "Dislikes Raw Seafood"
]

# Beverages & Drinks (Tied to generate_drink_name)
GROUNDED_DRINK_LIKES: List[str] = [
    "Iced Brown Sugar Boba Latte",
    "Chilled Canned Black Coffee",
    "Honey Citrus Jasmine Green Tea",
    "Vanilla Bean Nitro Cold Brew",
    "Fizzy Marble Ramune Soda",
    "Golden Supreme Milk Tea",
    "Tavern Mug of Spiced Cider",
    "Aged Dwarven Fire Ale",
    "Vintage Elven Sun-Nectar Wine",
    "Neon Spark Energy Fizz"
]

GROUNDED_DRINK_DISLIKES: List[str] = [
    "Dislikes Bitter Coffee",
    "Dislikes Sugary Sodas",
    "Dislikes Lukewarm Drinks",
    "Dislikes Strong Alcohol",
    "Dislikes Artificial Energy Drinks"
]

# Merchant & Gift Shop Items (Tied to merchant.py & items.py)
GROUNDED_GIFT_LIKES: List[str] = [
    "Lucky Shrine Amulet",
    "Antique Music Box",
    "Scented Jasmine Candle",
    "Premium Stationery Set",
    "Fluffy Animal Plush Keychain",
    "Vintage Vinyl Record",
    "Artisan Sketchbook",
    "Handcrafted Fountain Pen",
    "Silver Starlight Pendant"
]

GROUNDED_GIFT_DISLIKES: List[str] = [
    "Dislikes Cheap Plastic Novelties",
    "Dislikes Strong Perfume",
    "Dislikes Gaudy Accessories",
    "Dislikes Cluttered Knick-Knacks"
]

# -----------------------------------------------------------------------------
# MASTER SOCIAL STANCES REGISTRY (INTERPERSONAL DIALOGUE & TURNS)
# -----------------------------------------------------------------------------

SOCIAL_STANCES_LIKES: Dict[str, Dict[str, Any]] = {
    "direct_candor": {
        "id": "direct_candor",
        "label": "Favors Direct Candor & Honesty",
        "badge": "+2 Affinity on transparent, straightforward dialogue",
        "triggers": ["truth", "honest", "frank", "direct", "straightforward", "blunt", "confess", "sincere"],
        "bonus": 2
    },
    "tactical_depth": {
        "id": "tactical_depth",
        "label": "Favors Intellectual & Tactical Depth",
        "badge": "+2 Affinity on analytical dialogue & planning (Favors INT)",
        "triggers": ["theory", "analyze", "lore", "study", "research", "mechanism", "examine", "deduce", "scheme", "logic"],
        "bonus": 2
    },
    "playful_wit": {
        "id": "playful_wit",
        "label": "Favors Playful Wit & Teasing",
        "badge": "+2 Affinity on clever banter & lighthearted humor (Favors CHA)",
        "triggers": ["tease", "banter", "joke", "witty", "smirk", "laugh", "poking fun", "humor", "playful"],
        "bonus": 2
    },
    "emotional_empathy": {
        "id": "emotional_empathy",
        "label": "Favors Emotional Empathy & Sincerity",
        "badge": "+2 Affinity on compassionate, supportive choices (Favors PER)",
        "triggers": ["comfort", "listen", "reassure", "protect", "encourage", "hear out", "sympathize", "gentle"],
        "bonus": 2
    },
    "strategic_initiative": {
        "id": "strategic_initiative",
        "label": "Favors Strategic Initiative & Drive",
        "badge": "+2 Affinity on ambitious, goal-oriented leadership",
        "triggers": ["alliance", "ambition", "initiative", "seize", "opportunity", "strategy", "plan ahead", "leadership"],
        "bonus": 2
    },
    "boundary_respect": {
        "id": "boundary_respect",
        "label": "Favors Patient Boundary Respect",
        "badge": "+2 Affinity when giving space & showing discretion",
        "triggers": ["give space", "patient", "respect privacy", "wait", "step back", "no rush", "discretion"],
        "bonus": 2
    },
    "courageous_defense": {
        "id": "courageous_defense",
        "label": "Favors Courageous Solidarity & Defense",
        "badge": "+2 Affinity when standing up for others or allies (Favors STR/END)",
        "triggers": ["defend", "shield", "stand up for", "confront", "protect ally", "intervene", "brave"],
        "bonus": 2
    },
    "unconditional_loyalty": {
        "id": "unconditional_loyalty",
        "label": "Favors Unconditional Loyalty & Follow-Through",
        "badge": "+2 Affinity on honoring promises & standing firm",
        "triggers": ["promise", "loyal", "back up", "stay true", "reliable", "keep word", "stand by"],
        "bonus": 2
    },
    "rebellious_independence": {
        "id": "rebellious_independence",
        "label": "Favors Rebellious Independence & Guts",
        "badge": "+2 Affinity on defying authority & bold moves (Favors AGI/CHA)",
        "triggers": ["defy", "rogue", "street smart", "gutsy", "daring", "break rule", "bold move"],
        "bonus": 2
    },
    "creative_eccentricity": {
        "id": "creative_eccentricity",
        "label": "Favors Creative Eccentricity & Open-Mindedness",
        "badge": "+2 Affinity on outside-the-box, unorthodox ideas",
        "triggers": ["bizarre theory", "creative", "experiment", "wild idea", "unorthodox", "unconventional"],
        "bonus": 2
    },
    "diplomatic_grace": {
        "id": "diplomatic_grace",
        "label": "Favors Polite Decorum & Diplomatic Grace",
        "badge": "+2 Affinity on de-escalating tension & etiquette (Favors CHA)",
        "triggers": ["mediate", "compromise", "courteous", "defuse", "polite", "diplomatic", "de-escalate"],
        "bonus": 2
    },
    "athletic_rivalry": {
        "id": "athletic_rivalry",
        "label": "Favors Athletic Drive & Friendly Rivalry",
        "badge": "+2 Affinity on challenges, sparring & pushing limits (Favors STR/AGI)",
        "triggers": ["challenge", "spar", "race", "train", "test limits", "push limits", "athletic", "contest"],
        "bonus": 2
    },
    "subtle_tact": {
        "id": "subtle_tact",
        "label": "Favors Subtle Tact & Non-Verbal Understanding",
        "badge": "+2 Affinity when reading between the lines (Favors PER)",
        "triggers": ["subtle nod", "read room", "quiet glance", "discretion", "tactful", "unspoken", "perceptive"],
        "bonus": 2
    },
    "authentic_humility": {
        "id": "authentic_humility",
        "label": "Favors Authentic Humility & Self-Awareness",
        "badge": "+2 Affinity on admitting mistakes & humble honesty",
        "triggers": ["admit fault", "modest", "humble", "learn from mistake", "apologize sincerely", "drop pride"],
        "bonus": 2
    },
    "sincere_gratitude": {
        "id": "sincere_gratitude",
        "label": "Favors Sincere Gratitude & Validation",
        "badge": "+20% bonus Affinity when thanked or praised",
        "triggers": ["thank", "gratitude", "praise", "compliment", "admire", "impressed", "acknowledge effort"],
        "bonus": 2
    },
    "playful_flirtation": {
        "id": "playful_flirtation",
        "label": "Favors Playful Flirtation & Romantic Charm",
        "badge": "+2 Affinity on confident charm & smooth compliments (Favors CHA)",
        "triggers": ["flirt", "charming", "wink", "whisper", "romantic", "lean close", "compliment eyes"],
        "bonus": 2
    }
}

SOCIAL_STANCES_DISLIKES: Dict[str, Dict[str, Any]] = {
    "dishonesty_deceit": {
        "id": "dishonesty_deceit",
        "label": "Disdains Dishonesty & Deceit",
        "badge": "-4 Penalty on lies, manipulation, or broken trust",
        "triggers": ["lie", "lying", "deceit", "deceptive", "manipulate", "broken promise", "cheat", "double cross", "fake"],
        "penalty": -4
    },
    "condescension": {
        "id": "condescension",
        "label": "Resents Condescension & Belittling",
        "badge": "-4 Penalty if patronized, belittled, or dismissed",
        "triggers": ["patronize", "mock", "baby", "dismiss", "scoff", "condescend", "little girl", "too weak", "underestimate"],
        "penalty": -4
    },
    "micromanagement": {
        "id": "micromanagement",
        "label": "Resists Micromanagement & Forceful Orders",
        "badge": "-3 Penalty on forceful orders and bossy commands",
        "triggers": ["order", "command", "boss around", "force", "demand", "insist", "must obey"],
        "penalty": -3
    },
    "invasive_prying": {
        "id": "invasive_prying",
        "label": "Aversion to Invasive Prying & Boundary Pushing",
        "badge": "-3 Penalty on interrogating personal secrets",
        "triggers": ["pry", "interrogate", "demand secrets", "push boundary", "nosy", "force confession", "private matters"],
        "penalty": -3
    },
    "sycophancy_flattery": {
        "id": "sycophancy_flattery",
        "label": "Rejects Sycophancy & Obsequious Flattery",
        "badge": "-2 Penalty on insincere fawning or groveling",
        "triggers": ["grovel", "fawn", "fake praise", "butter up", "kiss up", "excessive flattery", "yes-man"],
        "penalty": -2
    },
    "arrogant_boasting": {
        "id": "arrogant_boasting",
        "label": "Contempt for Arrogant Boasting & Ego",
        "badge": "-3 Penalty on bragging, ego, or grandstanding",
        "triggers": ["brag", "boast", "show off", "arrogant", "self-important", "grandstand", "superiority"],
        "penalty": -3
    },
    "slacking_flakiness": {
        "id": "slacking_flakiness",
        "label": "Intolerant of Slacking & Flakiness",
        "badge": "-3 Penalty on dodging duty, laziness, or excuses",
        "triggers": ["slack", "ditch", "cut corners", "make excuses", "lazy", "skip work", "ignore rules", "careless"],
        "penalty": -3
    },
    "bullying_cruelty": {
        "id": "bullying_cruelty",
        "label": "Repulsed by Bullying & Cruelty",
        "badge": "-4 Penalty on cruelty, intimidation, or picking on the weak",
        "triggers": ["threaten", "bully", "mock helpless", "cruel", "intimidate", "shout down", "torment"],
        "penalty": -4
    },
    "manufactured_melodrama": {
        "id": "manufactured_melodrama",
        "label": "Exasperated by Manufactured Melodrama",
        "badge": "-2 Penalty on manufactured drama or guilt-trips",
        "triggers": ["overreact", "guilt-trip", "whine", "drama queen", "pout", "make a scene", "play victim"],
        "penalty": -2
    },
    "cynical_mockery": {
        "id": "cynical_mockery",
        "label": "Disgusted by Cynical Mockery",
        "badge": "-3 Penalty on ridiculing sincere efforts or dreams",
        "triggers": ["sneer", "ridicule", "mock passion", "cynical jab", "make fun of dreams", "belittle effort"],
        "penalty": -3
    },
    "rigid_dogmatism": {
        "id": "rigid_dogmatism",
        "label": "Frustrated by Rigid Dogmatism",
        "badge": "-2 Penalty on close-mindedness & blind rule-following",
        "triggers": ["dogmatic", "reject new ideas", "blind obedience", "close minded", "inflexible"],
        "penalty": -2
    },
    "public_embarrassment": {
        "id": "public_embarrassment",
        "label": "Dread of Public Embarrassment",
        "badge": "-3 Penalty on making a loud scene in public",
        "triggers": ["cause scene", "scream publicly", "put on spot", "shame in public", "humiliate publicly"],
        "penalty": -3
    },
    "underhanded_tactics": {
        "id": "underhanded_tactics",
        "label": "Hatred of Underhanded Tactics",
        "badge": "-4 Penalty on poison, dirty tricks, or cheap shortcuts",
        "triggers": ["poison", "backstab", "dirty trick", "dishonorable move", "cheat contest", "underhanded"],
        "penalty": -4
    },
    "over_familiarity": {
        "id": "over_familiarity",
        "label": "Discomfort with Over-Familiarity",
        "badge": "-2 Penalty on pushing physical touch or intimacy too fast",
        "triggers": ["touch without asking", "overly clingy", "smothering", "grab hand uninvited", "invade personal space"],
        "penalty": -2
    },
    "reckless_gambles": {
        "id": "reckless_gambles",
        "label": "Angered by Reckless Gambles",
        "badge": "-3 Penalty on endangering the group carelessly",
        "triggers": ["reckless gamble", "suicidal charge", "careless risk", "endanger everyone", "rush blindly"],
        "penalty": -3
    },
    "entitled_ingratitude": {
        "id": "entitled_ingratitude",
        "label": "Contempt for Entitled Ingratitude",
        "badge": "-2 Penalty on entitlement & taking help for granted",
        "triggers": ["entitled", "ungrateful", "take for granted", "ignore debt", "demand favor", "act entitled"],
        "penalty": -2
    }
}

BEHAVIORAL_LIKES: List[str] = [s["label"] for s in SOCIAL_STANCES_LIKES.values()]
BEHAVIORAL_DISLIKES: List[str] = [s["label"] for s in SOCIAL_STANCES_DISLIKES.values()]

