from ..core import (
    EYE_COLORS, HAIR_COLORS, HAIR_LENGTHS, HAIR_STYLES,
    STATURE_TIERS, STATURES,
    BREAST_SIZES, PENIS_SIZES,
    DIVERSE_BEASTFOLK_COATS, DIVERSE_BEASTFOLK_SCALES, DIVERSE_BEASTFOLK_EYES, COLOR_FAMILIES,
    SPECIES_TEMPLATES, DIVERSE_FEMALE_HAIR_STYLES, DIVERSE_MALE_HAIR_STYLES,
    DIVERSE_HAIR_LENGTHS_FEMALE, DIVERSE_HAIR_LENGTHS_MALE,
    PHYSIQUE_FEMALE_TEMPLATES, PHYSIQUE_MALE_TEMPLATES,
    UNDERGARMENT_COLOR_PALETTES,
    FEMALE_BRA_STYLES_PRUDE, FEMALE_BRA_STYLES_MODERATE, FEMALE_BRA_STYLES_BOLD,
    FEMALE_UNDERWEAR_STYLES_PRUDE, FEMALE_UNDERWEAR_STYLES_MODERATE, FEMALE_UNDERWEAR_STYLES_BOLD,
    MALE_UNDERWEAR_STYLES_PRUDE, MALE_UNDERWEAR_STYLES_MODERATE, MALE_UNDERWEAR_STYLES_BOLD,
    TRAIT_TEMPLATES, MANNERISM_TEMPLATES,
    IMMUTABLE_PHYSICAL_APPEARANCE_KEYS,
    PREFERENCE_KEYWORDS, DISLIKE_KEYWORDS, LIKE_KEYWORDS
)

STATURE_WEIGHTS_MINIATURE = {
    'miniature': 1.0,
    'short': 0.0,
    'below_average': 0.0,
    'average': 0.0,
    'tall': 0.0,
    'towering': 0.0
}

# Male Stature Distributions
STATURE_WEIGHTS_MALE_STANDARD = {
    'miniature': 0.0,
    'short': 0.05,
    'below_average': 0.15,
    'average': 0.50,
    'tall': 0.25,
    'towering': 0.05
}

STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.01,
    'below_average': 0.04,
    'average': 0.25,
    'tall': 0.45,
    'towering': 0.25
}

STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.10,
    'below_average': 0.30,
    'average': 0.43,
    'tall': 0.15,
    'towering': 0.02
}

STATURE_WEIGHTS_MALE_TINY_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.34,
    'below_average': 0.45,
    'average': 0.15,
    'tall': 0.05,
    'towering': 0.01
}

# Female Stature Distributions
STATURE_WEIGHTS_FEMALE_STANDARD = {
    'miniature': 0.0,
    'short': 0.10,
    'below_average': 0.34,
    'average': 0.45,
    'tall': 0.10,
    'towering': 0.01
}

STATURE_WEIGHTS_FEMALE_LARGE_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.01,
    'below_average': 0.14,
    'average': 0.55,
    'tall': 0.20,
    'towering': 0.10
}

STATURE_WEIGHTS_FEMALE_SMALL_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.15,
    'below_average': 0.45,
    'average': 0.34,
    'tall': 0.05,
    'towering': 0.01
}

STATURE_WEIGHTS_FEMALE_TINY_BEASTFOLK = {
    'miniature': 0.0,
    'short': 0.55,
    'below_average': 0.35,
    'average': 0.07,
    'tall': 0.02,
    'towering': 0.01
}

# Backwards compatibility aliases
STATURE_WEIGHTS_STANDARD = STATURE_WEIGHTS_MALE_STANDARD
STATURE_WEIGHTS_LARGE_BEASTFOLK = STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK
STATURE_WEIGHTS_SMALL_BEASTFOLK = STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK
STATURE_WEIGHTS_TINY_BEASTFOLK = STATURE_WEIGHTS_MALE_TINY_BEASTFOLK

STATURE_INCOMPATIBLE_PHYSIQUES = {
    'tall': {'Petite & Soft'},
    'towering': {'Petite & Soft'}
}

ASSET_SIZE_TIERS = ('flat', 'small', 'average', 'large', 'huge')

FEMALE_ASSET_TEXTURE_TEMPLATES = [
    'Perky & High-Set',
    'Pillowy Soft & Yielding',
    'Firm & Toned',
    'Smooth & Supple',
    'Heavy & Plush',
    'Bouncy & Sensitive',
    'Tender & Delicate',
    'Shapely Teardrop',
    'Compact & Dense',
    'Sensitive & Responsive',
    'Warm & Supple',
    'Soft & Downy Chest Fur',
    'Silky Fur-Rimmed',
    'Velvety Underbelly Down',
    'Fluffy Plush-Accented',
    'Silky Warm with Smooth Micro-Scales',
    'Supple with Shimmering Scale Borders',
    'Sleek & Supple Drake-Contour',
    'Serpentine Smooth with Fine Scales',
    'Downy Feather-Lined',
    'Light & Buoyant',
    'Velvety Plumage Accents',
    'Glistening & Ultra-Smooth',
    'Soft Scaled Flank Accents'
]

MALE_ASSET_TEXTURE_TEMPLATES = [
    'Veined & Firm',
    'Smooth & Heavy',
    'Toned & Athletic',
    'Warm & Pulsing',
    'Slender & Ultra-Sensitive',
    'Dense & Formidable',
    'Balanced & Firm',
    'Soft Fur-Ringed Base',
    'Sleek Scaled Base & Firm',
    'Sturdy Draconic Build',
    'Silky Fur-Dusted & Resilient'
]

SPECIES_TEXTURE_AFFINITIES = {
    'furred': [
        'Soft & Downy Chest Fur',
        'Silky Fur-Rimmed',
        'Velvety Underbelly Down',
        'Fluffy Plush-Accented',
        'Soft Fur-Ringed Base',
        'Silky Fur-Dusted & Resilient'
    ],
    'scaled': [
        'Silky Warm with Smooth Micro-Scales',
        'Supple with Shimmering Scale Borders',
        'Sleek & Supple Drake-Contour',
        'Serpentine Smooth with Fine Scales',
        'Sleek Scaled Base & Firm',
        'Sturdy Draconic Build'
    ],
    'feathered': [
        'Downy Feather-Lined',
        'Light & Buoyant',
        'Velvety Plumage Accents'
    ],
    'aquatic': [
        'Glistening & Ultra-Smooth',
        'Soft Scaled Flank Accents'
    ],
    'athletic': [
        'Firm & Toned',
        'Perky & High-Set',
        'Toned & Athletic'
    ],
    'voluptuous': [
        'Heavy & Plush',
        'Pillowy Soft & Yielding',
        'Smooth & Heavy'
    ]
}

TIER_INCOMPATIBLE_TEXTURES = {
    'flat': {
        'Heavy & Plush',
        'Pillowy Soft & Yielding',
        'Heavy & Bountiful',
        'Deep & Pillowy',
        'Fluffy Plush-Accented',
        'Smooth & Heavy',
        'Dense & Formidable'
    },
    'small': {
        'Heavy & Plush',
        'Pillowy Soft & Yielding',
        'Heavy & Bountiful',
        'Deep & Pillowy',
        'Smooth & Heavy',
        'Dense & Formidable'
    },
    'average': set(),
    'large': {
        'Compact & Dense',
        'Tender & Delicate',
        'Light & Buoyant',
        'Slender & Ultra-Sensitive'
    },
    'huge': {
        'Compact & Dense',
        'Tender & Delicate',
        'Light & Buoyant',
        'Slender & Ultra-Sensitive'
    }
}

VALID_MILESTONE_EVENTS = {'oral_receive', 'manual_receive', 'kiss', 'oral_give', 'oral_mutual', 'date', 'first_kiss', 'manual_give', 'manual_mutual', 'anal_give', 'anal_receive', 'anal_mutual', 'anal', 'affection', 'none', 'intercourse', 'confession'}
NSFW_SCENARIOS = {'nsfw_high_school_drama'}
INTIMATE_DEMEANOR_FEMALE_TEMPLATES = ['Playful & Bantering, teases warmly and laughs softly between kisses', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and emotional closeness', 'Poised & Articulate, calm, deliberate with a low, husky seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and uninhibited praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, flustered pauses, earnest sincerity and endearing shyness']
INTIMATE_DEMEANOR_MALE_TEMPLATES = ['Playful & Bantering, teases warmly with lighthearted confidence', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and steady emotional closeness', 'Poised & Articulate, calm, composed with a low, steady seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and uninhibited praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, thoughtful pauses, earnest sincerity and endearing shyness']
INTIMATE_DEMEANOR_TEMPLATES = ['Playful & Bantering, teases warmly and laughs softly between kisses', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and emotional closeness', 'Poised & Articulate, calm, deliberate with a low, husky seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and uninhibited praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, flustered pauses, earnest sincerity and endearing shyness']
INTIMATE_DYNAMIC_TEMPLATES = ['Boldly Proactive & Dominant (Takes physical initiative, guides the pace, confident on top)', 'Playful Switch / Teasing Brat (Tests limits and challenges partner, shifts fluidly between leading and yielding)', 'Eagerly Receptive / Surrenders Control (Enthusiastic participant who craves partner taking complete charge and guiding)', 'Insatiable / Hidden High-Drive (Quiet or composed in public, intensely voracious and relentless in private)', "Gentle & Yielding (Submissive, tenderly responsive, follows partner's lead with trusting surrender)", "Attentive Service-Oriented (Derives peak pleasure from partner's pleasure, devoted and focused on giving)"]
EROTIC_OPENNESS_TIERS = ['prude', 'moderate', 'bold', 'shameless']
EROTIC_OPENNESS_TEMPLATES = {'prude': 'Prude / Modest (High modesty barrier, flustered or defensive around crude talk, strictly romance-focused)', 'moderate': 'Reserved / Moderate (Values timing and private decorum, comfortable with natural intimacy when romance builds)', 'bold': 'Bold / Uninhibited (Sex-positive, unbothered by scandal, freely makes double entendres, generous with spicy media)', 'shameless': 'Shameless / Lewd (Hedonistic high-drive, zero verbal filter, actively craves erotic stimulation, openly provocative in DMs)'}
INTERCOURSE_STATES = ('virgin', 'non_virgin', 'unknown')
ORAL_INTIMACY_STATES = ('inexperienced', 'has_done_oral', 'has_received_oral', 'has_done_and_received_oral', 'unknown')
MANUAL_INTIMACY_STATES = ('inexperienced', 'has_done_manual', 'has_received_manual', 'has_done_and_received_manual', 'unknown')
ANAL_INTIMACY_STATES = ('inexperienced', 'has_done_anal', 'has_received_anal', 'has_done_and_received_anal', 'unknown')
TURN_ON_PHYSICAL_HUMANOID_ITEMS = ['Inner thighs', 'Nape of neck', 'Collarbone', 'Lower back', 'Behind the ears', 'Sides of waist', 'Wrists & palms', 'Shoulder blades', 'Chest & sternum', 'Hip bones', 'Sensitive stomach', 'Throat & neckline', 'Back of knees', 'Arch of feet', 'Base of spine', 'Earlobe & jawline', 'Navel area', 'Upper ribs', 'Inner arms', 'Back of neck', 'Hollow of collarbone', 'Tender hips', 'Underbust area', 'Sides of torso']
TURN_ON_MAMMALIAN_BEASTFOLK_ITEMS = ['Base of tail', 'Soft ear tips', 'Inner ear fluff', 'Behind animal ears', 'Tail base & spine line', 'Fur along the jawline', 'Sensitive tail fur', 'Underside of tail', 'Sensitive footpads & paw pads', 'Vulnerable throat fur', 'Soft underbelly', 'Flank along the ribcage', 'Between shoulder blades along spine', 'Tufted ear base']
TURN_ON_HORNED_ITEMS = ['Root of horns / antlers', 'Base of horns', 'Crown between horns', 'Ridges along horn base']
TURN_ON_WINGED_ITEMS = ['Wing base & flight joints', 'Underside of wings', 'Wing joints & primary feathers', 'Feathered nape']
TURN_ON_SCALY_AQUATIC_ITEMS = ['Dorsal fin base', 'Soft scales along the flank', 'Gills & neck crest', 'Scale line along spine']
TURN_ON_PHYSICAL_ITEMS = ['Inner thighs', 'Nape of neck', 'Collarbone', 'Lower back', 'Behind the ears', 'Sides of waist', 'Wrists & palms', 'Shoulder blades', 'Chest & sternum', 'Hip bones', 'Sensitive stomach', 'Throat & neckline', 'Back of knees', 'Arch of feet', 'Base of spine', 'Earlobe & jawline', 'Navel area', 'Upper ribs', 'Inner arms', 'Back of neck', 'Hollow of collarbone', 'Tender hips', 'Underbust area', 'Sides of torso', 'Base of tail', 'Soft ear tips', 'Inner ear fluff', 'Behind animal ears', 'Tail base & spine line', 'Fur along the jawline', 'Sensitive tail fur', 'Underside of tail', 'Sensitive footpads & paw pads', 'Vulnerable throat fur', 'Soft underbelly', 'Flank along the ribcage', 'Between shoulder blades along spine', 'Tufted ear base', 'Root of horns / antlers', 'Base of horns', 'Crown between horns', 'Ridges along horn base', 'Wing base & flight joints', 'Underside of wings', 'Wing joints & primary feathers', 'Feathered nape', 'Dorsal fin base', 'Soft scales along the flank', 'Gills & neck crest', 'Scale line along spine']
TURN_ON_ACTION_ITEMS = ['Intimate eye contact', 'Breath against sensitive skin', 'Soft breathless moans', 'Neck kisses', 'Dominant whispers', 'Gentle nibbling & biting', 'Hair stroking & gentle pulling', 'Playful teasing', 'Hand-holding with interlocked fingers', 'Gentle physical worship', 'Sudden warm embraces', 'Scent of partner', 'Light nails along skin', 'Being pinned gently', 'Teasing kisses on collarbone', 'Passionate urgency', 'Affectionate forehead rests', 'Being called endearing names', 'Slow undressing', 'Ear whispering']
SENSITIVE_SPOT_ITEMS = ['Inner thighs', 'Nape of neck', 'Collarbone', 'Lower back', 'Behind the ears', 'Sides of waist', 'Wrists & palms', 'Shoulder blades', 'Chest & sternum', 'Hip bones', 'Sensitive stomach', 'Throat & neckline', 'Back of knees', 'Arch of feet', 'Base of spine', 'Earlobe & jawline', 'Navel area', 'Upper ribs', 'Inner arms', 'Back of neck', 'Hollow of collarbone', 'Tender hips', 'Underbust area', 'Sides of torso']
SENSITIVE_SPOT_MAMMALIAN_BEASTFOLK_ITEMS = ['Base of tail', 'Soft ear tips', 'Inner ear fluff', 'Behind animal ears', 'Tail base & spine line', 'Fur along the jawline', 'Sensitive tail fur', 'Underside of tail', 'Sensitive footpads & paw pads', 'Vulnerable throat fur', 'Soft underbelly', 'Flank along the ribcage', 'Between shoulder blades along spine', 'Tufted ear base']
SENSITIVE_SPOT_HORNED_ITEMS = ['Root of horns / antlers', 'Base of horns', 'Crown between horns', 'Ridges along horn base']
SENSITIVE_SPOT_WINGED_ITEMS = ['Wing base & flight joints', 'Underside of wings', 'Wing joints & primary feathers', 'Feathered nape']
SENSITIVE_SPOT_SCALY_AQUATIC_ITEMS = ['Dorsal fin base', 'Soft scales along the flank', 'Gills & neck crest', 'Scale line along spine']
SENSITIVE_SPOT_BEASTFOLK_ITEMS = ['Inner thighs', 'Nape of neck', 'Collarbone', 'Lower back', 'Behind the ears', 'Sides of waist', 'Wrists & palms', 'Shoulder blades', 'Chest & sternum', 'Hip bones', 'Sensitive stomach', 'Throat & neckline', 'Back of knees', 'Arch of feet', 'Base of spine', 'Earlobe & jawline', 'Navel area', 'Upper ribs', 'Inner arms', 'Back of neck', 'Hollow of collarbone', 'Tender hips', 'Underbust area', 'Sides of torso', 'Base of tail', 'Soft ear tips', 'Inner ear fluff', 'Behind animal ears', 'Tail base & spine line', 'Fur along the jawline', 'Sensitive tail fur', 'Underside of tail', 'Sensitive footpads & paw pads', 'Vulnerable throat fur', 'Soft underbelly', 'Flank along the ribcage', 'Between shoulder blades along spine', 'Tufted ear base', 'Root of horns / antlers', 'Base of horns', 'Crown between horns', 'Ridges along horn base', 'Wing base & flight joints', 'Underside of wings', 'Wing joints & primary feathers', 'Feathered nape', 'Dorsal fin base', 'Soft scales along the flank', 'Gills & neck crest', 'Scale line along spine']
TURN_ON_ITEMS = ['Intimate eye contact', 'Breath against sensitive skin', 'Soft breathless moans', 'Neck kisses', 'Dominant whispers', 'Gentle nibbling & biting', 'Hair stroking & gentle pulling', 'Playful teasing', 'Hand-holding with interlocked fingers', 'Gentle physical worship', 'Sudden warm embraces', 'Scent of partner', 'Light nails along skin', 'Being pinned gently', 'Teasing kisses on collarbone', 'Passionate urgency', 'Affectionate forehead rests', 'Being called endearing names', 'Slow undressing', 'Ear whispering']
FETISH_ITEMS = ['Petplay & ear/tail caressing', 'Blindfolds & sensory deprivation', 'Lingerie & silk costumes', 'Light silk restraints', 'Praise kink & verbal validation', 'Public thrill & risk of being caught', 'Gentle dominance / submission', 'Costume / uniform roleplay', 'Biting & marking', 'Temperature play (ice & warmth)', 'Overstimulation & gentle edging', 'Mirror observation & exhibition', 'Massage oils & tactile worship', 'Aftercare obsession', 'Collaring & leashes', 'Impact play & gentle spanking', 'Breath play (light)', 'Mutual masturbation / voyeurism', 'Latex & leather accents', 'Audio stimulation / dirty talk', 'Bondage & shibari ropework']
DESIRES_AND_KINKS_ITEMS = list(TURN_ON_ACTION_ITEMS) + list(FETISH_ITEMS)

TURN_OFF_ITEMS = [
    'Crude degradation & insults',
    'Rushed impatience & entitlement',
    'Dead silence & emotional detachment',
    'Clumsy / careless rough handling',
    'Unearned bossiness & arrogance',
    'Limp passivity & lack of effort',
    'Poor hygiene & neglect',
    'Purely transactional feeling',
    'Lack of discretion & careless exposure',
    'Overly aggressive biting or pinching',
    'Mocking or laughing at vulnerability',
    'Smothering clinginess during intimacy',
    'Anal play & backdoor intimacy'
]
TURN_OFF_TEMPLATES = list(TURN_OFF_ITEMS)

TURN_OFF_DETECTION_REGISTRY = [
    {
        'id': 'anal_aversion',
        'name': 'Anal play & backdoor intimacy',
        'keywords': ['anal', 'backdoor', 'asshole', 'pegging', 'peg']
    },
    {
        'id': 'crude_degradation',
        'name': 'Crude degradation & insults',
        'keywords': ['degrade', 'insult', 'whore', 'slut', 'bitch', 'filthy', 'humiliate', 'name-calling', 'crude']
    },
    {
        'id': 'rushed_impatience',
        'name': 'Rushed impatience & entitlement',
        'keywords': ['hurry', 'hurry up', 'rush', 'faster', 'skip foreplay', 'get on with it', 'waste time', 'impatient', 'demand', 'entitled']
    },
    {
        'id': 'dead_silence',
        'name': 'Dead silence & emotional detachment',
        'keywords': ['dead silence', 'cold silence', 'in silence', 'silence', 'silent', 'ignoring', 'detached', 'emotionless', 'look away', 'stare blankly', 'bored']
    },
    {
        'id': 'clumsy_rough_handling',
        'name': 'Clumsy / careless rough handling',
        'keywords': ['yank', 'pinch hard', 'bruise', 'careless', 'clumsy', 'painful grip', 'rough squeeze', 'drag roughly', 'harsh tug', 'yank hair', 'hair pull', 'pull hair', 'careless rough handling', 'clumsy rough handling', 'too rough', 'painful rough', 'aggressively', 'hair pulling']
    },
    {
        'id': 'unearned_bossiness',
        'name': 'Unearned bossiness & arrogance',
        'keywords': ['order around', 'command', 'bark orders', 'obey me', 'arrogant', 'boss around', 'know your place', 'subjugate']
    },
    {
        'id': 'limp_passivity',
        'name': 'Limp passivity & lack of effort',
        'keywords': ['lie still', 'do nothing', 'dead weight', 'limp', 'passive', 'motionless', 'make no effort', 'unresponsive']
    },
    {
        'id': 'poor_hygiene',
        'name': 'Poor hygiene & neglect',
        'keywords': ['grimy', 'unwashed', 'sweaty stench', 'bad breath', 'dirty clothes', 'foul smell', 'muddy', 'filth']
    },
    {
        'id': 'purely_transactional',
        'name': 'Purely transactional feeling',
        'keywords': ['transactional', 'like an object', 'treat as tool', 'pay for', 'deal is a deal', 'business', 'commodity', 'use for pleasure']
    },
    {
        'id': 'careless_exposure',
        'name': 'Lack of discretion & careless exposure',
        'keywords': ['leave door open', 'let anyone see', 'make loud noise', 'expose in public', 'broadcast', 'careless risk', 'draw crowd']
    },
    {
        'id': 'aggressive_biting',
        'name': 'Overly aggressive biting or pinching',
        'keywords': ['bite hard', 'draw blood', 'painful bite', 'dig nails', 'sharp pinch', 'excessive force']
    },
    {
        'id': 'mocking_vulnerability',
        'name': 'Mocking or laughing at vulnerability',
        'keywords': ['laugh at', 'mock', 'ridicule', 'giggle at size', 'tease cruelly', 'make fun of', 'scoff']
    },
    {
        'id': 'invasive_prying',
        'name': 'Prying into past intimacy & personal secrets',
        'keywords': [
            'past experience', 'past intimacy', 'past relationship', 'dating history', 'virgin',
            'who have you', 'body count', 'intimate secrets', 'interrogate', 'pry', 'prying',
            'demand secrets', 'past partner', 'challenge her about past', 'challenge him about past'
        ]
    },
    {
        'id': 'smothering_clinginess',
        'name': 'Smothering clinginess during intimacy',
        'keywords': ['cling desperately', 'smother', 'whine', 'needy', 'beg continuously', 'possessive grasp']
    }
]

ACT_PREFERENCE_REGISTRY = [
    {'id': 'giving_oral', 'name': 'Giving oral intimacy', 'keywords': ['give oral', 'giving oral', 'go down', 'going down', 'oral give', 'fellatio', 'cunnilingus', 'blowjob', 'eat out', 'eating out']},
    {'id': 'receiving_oral', 'name': 'Receiving oral intimacy', 'keywords': ['receive oral', 'receiving oral', 'oral receive', 'head from', 'eaten out', 'blown', 'getting oral']},
    {'id': 'swallowing', 'name': 'Swallowing climax', 'keywords': ['swallow', 'swallowing', 'drink climax', 'swallow down']},
    {'id': 'facial', 'name': 'Facial climax', 'keywords': ['facial', 'climax on face', 'on her face', 'on his face', 'across face']},
    {'id': 'missionary', 'name': 'Face-to-face missionary', 'keywords': ['missionary', 'face-to-face', 'face to face', 'looking into eyes on back', 'chest to chest']},
    {'id': 'cowgirl_riding', 'name': 'Riding / On top (Cowgirl)', 'keywords': ['cowgirl', 'riding', 'ride', 'straddle', 'on top', 'reverse cowgirl']},
    {'id': 'from_behind', 'name': 'From behind (Doggy style)', 'keywords': ['from behind', 'doggy', 'doggy style', 'rear entry', 'take from behind']},
    {'id': 'spooning', 'name': 'Spooning & back embrace', 'keywords': ['spooning', 'spoon', 'side by side', 'back embrace', 'wrapped around from behind']},
    {'id': 'taking_charge', 'name': 'Taking physical charge / leading', 'keywords': ['take charge', 'taking charge', 'in command', 'dominant pace', 'guiding pace', 'leading']},
    {'id': 'slow_sensual', 'name': 'Slow & sensual pacing', 'keywords': ['slow', 'sensual', 'slowly', 'unhurried', 'lingering', 'tender pace']},
    {'id': 'fast_urgent', 'name': 'Fast & passionate urgency', 'keywords': ['fast', 'urgent', 'urgency', 'rough and fast', 'feverish pace', 'passionate speed']},
    {'id': 'prolonged_teasing', 'name': 'Prolonged foreplay & teasing', 'keywords': ['foreplay', 'teasing', 'edging', 'prolonged', 'deny climax', 'building anticipation']},
    {'id': 'rough_handling', 'name': 'Rough handling & firm grips', 'keywords': ['rough', 'firm grip', 'gripping tightly', 'hair pull', 'bruising', 'aggressive touch']},
    {'id': 'giving_anal', 'name': 'Giving anal intimacy', 'keywords': ['give anal', 'giving anal', 'penetrate anally', 'pegging', 'peg', 'take anally']},
    {'id': 'receiving_anal', 'name': 'Receiving anal intimacy', 'keywords': ['receive anal', 'receiving anal', 'taken anally', 'backdoor', 'anal receive']}
]
SENSITIVE_SPOTS_TEMPLATES = ['Inner thighs', 'Nape of neck', 'Collarbone', 'Lower back', 'Behind the ears', 'Sides of waist', 'Wrists & palms', 'Shoulder blades', 'Chest & sternum', 'Hip bones', 'Sensitive stomach', 'Throat & neckline', 'Back of knees', 'Arch of feet', 'Base of spine', 'Earlobe & jawline', 'Navel area', 'Upper ribs', 'Inner arms', 'Back of neck', 'Hollow of collarbone', 'Tender hips', 'Underbust area', 'Sides of torso']
TURN_ONS_TEMPLATES = ['Intimate eye contact', 'Breath against sensitive skin', 'Soft breathless moans', 'Neck kisses', 'Dominant whispers', 'Gentle nibbling & biting', 'Hair stroking & gentle pulling', 'Playful teasing', 'Hand-holding with interlocked fingers', 'Gentle physical worship', 'Sudden warm embraces', 'Scent of partner', 'Light nails along skin', 'Being pinned gently', 'Teasing kisses on collarbone', 'Passionate urgency', 'Affectionate forehead rests', 'Being called endearing names', 'Slow undressing', 'Ear whispering']
FETISH_TEMPLATES = ['Petplay & ear/tail caressing', 'Blindfolds & sensory deprivation', 'Lingerie & silk costumes', 'Light silk restraints', 'Praise kink & verbal validation', 'Public thrill & risk of being caught', 'Gentle dominance / submission', 'Costume / uniform roleplay', 'Biting & marking', 'Temperature play (ice & warmth)', 'Overstimulation & gentle edging', 'Mirror observation & exhibition', 'Massage oils & tactile worship', 'Aftercare obsession', 'Collaring & leashes', 'Impact play & gentle spanking', 'Breath play (light)', 'Mutual masturbation / voyeurism', 'Latex & leather accents', 'Audio stimulation / dirty talk', 'Bondage & shibari ropework']

PLAYER_ROMANTIC_ACTION_KEYWORDS = {'kiss', 'hug', 'caress', 'embrace', 'hold hands', 'stroke', 'flirt', 'cuddle', 'snuggle', 'touch', 'massage'}
CONFESSION_KEYWORDS = {'confess', 'confession', 'i love you', 'feelings', 'admit', 'romantic feelings'}

NPC_ORAL_RECEIVE_KEYWORDS = ('receive oral', 'receiving oral', 'oral receive', 'head from', 'eaten out', 'blown', 'getting oral')
NPC_ORAL_GIVE_KEYWORDS = ('give oral', 'giving oral', 'go down', 'going down', 'oral give', 'fellatio', 'cunnilingus', 'blowjob', 'eat out', 'eating out')
NPC_MANUAL_RECEIVE_KEYWORDS = ('receive manual', 'receiving manual', 'fingered', 'fingering', 'handjob', 'fingers inside', 'rubbed', 'rubbing')
NPC_MANUAL_GIVE_KEYWORDS = ('give manual', 'giving manual', 'finger her', 'finger him', 'give handjob', 'rub her', 'rub him')
NPC_ANAL_RECEIVE_KEYWORDS = ('receive anal', 'receiving anal', 'taken anally', 'take anally', 'anal receive', 'backdoor', 'anal sex', 'in her ass', 'in his ass')
NPC_ANAL_GIVE_KEYWORDS = ('give anal', 'giving anal', 'penetrate anally', 'pegging', 'peg', 'anal give')
ANAL_KEYWORDS = ('anal', 'backdoor', 'asshole', 'pegging')
INTERCOURSE_KEYWORDS = ('intercourse', 'sex', 'fuck', 'penetration', 'inside her', 'inside him', 'pounding', 'thrusting')
KISS_KEYWORDS = ('kiss', 'kisses', 'make out', 'making out', 'lock lips', 'kissing')
DATE_KEYWORDS = ('date', 'romantic date', 'hang out romantically')
ROMANCE_KEYWORDS = ('love', 'romantic', 'feelings', 'confess', 'my heart', 'dating')

INTERCOURSE_MEMORY_KEYWORDS = (
    "shared intimate night", "intercourse", "penetrat", "took her virginity", "took his virginity",
    "made love", "first time together", "intimate night", "slept together", "lost her virginity", "lost his virginity", "sex with"
)
ORAL_GIVE_MEMORY_KEYWORDS = (
    "performed oral", "provided oral", "shared oral", "mutual oral", "took his release", "took her release",
    "sucked", "blowjob", "fellatio", "pleasure with her lips", "pleasure with his lips", "oral intimacy to",
    "tasted his", "tasted her", "went down on", "gave oral"
)
ORAL_RECEIVE_MEMORY_KEYWORDS = (
    "received oral", "first taste of his skill", "first taste of her skill", "eaten out", "cunnilingus",
    "pleasured orally", "oral intimacy from"
)
MANUAL_GIVE_MEMORY_KEYWORDS = (
    "manually stimulated", "stroked his", "stroked her", "gave a handjob", "hand stimulation",
    "manual intimacy to", "manual stimulation to", "fingered", "handjob"
)
MANUAL_RECEIVE_MEMORY_KEYWORDS = (
    "received manual", "fingered by", "touched her intimate", "stimulated by",
    "manual intimacy from", "manual stimulation from"
)
ANAL_GIVE_MEMORY_KEYWORDS = (
    "performed anal", "penetrated anally", "pegged", "anal intimacy to", "gave anal", "fucked anally", "fucked his partner anally"
)
ANAL_RECEIVE_MEMORY_KEYWORDS = (
    "received anal", "taken anally", "anal intimacy from", "anal penetration", "fucked in the ass"
)

__all__ = [
    'EYE_COLORS', 'HAIR_COLORS', 'HAIR_LENGTHS', 'HAIR_STYLES', 'STATURES', 'STATURE_TIERS',
    'STATURE_WEIGHTS_MINIATURE', 'STATURE_WEIGHTS_TINY_BEASTFOLK', 'STATURE_WEIGHTS_SMALL_BEASTFOLK',
    'STATURE_WEIGHTS_LARGE_BEASTFOLK', 'STATURE_WEIGHTS_STANDARD',
    'STATURE_WEIGHTS_MALE_STANDARD', 'STATURE_WEIGHTS_FEMALE_STANDARD',
    'STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_LARGE_BEASTFOLK',
    'STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_SMALL_BEASTFOLK',
    'STATURE_WEIGHTS_MALE_TINY_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_TINY_BEASTFOLK',
    'STATURE_INCOMPATIBLE_PHYSIQUES',
    'BREAST_SIZES', 'PENIS_SIZES',
    'DIVERSE_BEASTFOLK_COATS', 'DIVERSE_BEASTFOLK_SCALES', 'DIVERSE_BEASTFOLK_EYES', 'COLOR_FAMILIES',
    'SPECIES_TEMPLATES', 'DIVERSE_FEMALE_HAIR_STYLES', 'DIVERSE_MALE_HAIR_STYLES', 'DIVERSE_HAIR_LENGTHS_FEMALE',
    'DIVERSE_HAIR_LENGTHS_MALE', 'PHYSIQUE_FEMALE_TEMPLATES', 'PHYSIQUE_MALE_TEMPLATES', 'UNDERGARMENT_COLOR_PALETTES',
    'FEMALE_BRA_STYLES_PRUDE', 'FEMALE_BRA_STYLES_MODERATE', 'FEMALE_BRA_STYLES_BOLD', 'FEMALE_UNDERWEAR_STYLES_PRUDE',
    'FEMALE_UNDERWEAR_STYLES_MODERATE', 'FEMALE_UNDERWEAR_STYLES_BOLD', 'MALE_UNDERWEAR_STYLES_PRUDE',
    'MALE_UNDERWEAR_STYLES_MODERATE', 'MALE_UNDERWEAR_STYLES_BOLD', 'TRAIT_TEMPLATES', 'MANNERISM_TEMPLATES',
    'IMMUTABLE_PHYSICAL_APPEARANCE_KEYS', 'PREFERENCE_KEYWORDS', 'DISLIKE_KEYWORDS', 'LIKE_KEYWORDS',
    'VALID_MILESTONE_EVENTS', 'NSFW_SCENARIOS', 'INTIMATE_DEMEANOR_FEMALE_TEMPLATES', 'INTIMATE_DEMEANOR_MALE_TEMPLATES',
    'INTIMATE_DEMEANOR_TEMPLATES', 'INTIMATE_DYNAMIC_TEMPLATES', 'EROTIC_OPENNESS_TIERS', 'EROTIC_OPENNESS_TEMPLATES',
    'INTERCOURSE_STATES', 'ORAL_INTIMACY_STATES', 'MANUAL_INTIMACY_STATES', 'ANAL_INTIMACY_STATES', 'TURN_ON_PHYSICAL_HUMANOID_ITEMS',
    'TURN_ON_MAMMALIAN_BEASTFOLK_ITEMS', 'TURN_ON_HORNED_ITEMS', 'TURN_ON_WINGED_ITEMS', 'TURN_ON_SCALY_AQUATIC_ITEMS',
    'TURN_ON_PHYSICAL_ITEMS', 'TURN_ON_ACTION_ITEMS', 'SENSITIVE_SPOT_ITEMS', 'SENSITIVE_SPOT_MAMMALIAN_BEASTFOLK_ITEMS',
    'SENSITIVE_SPOT_HORNED_ITEMS', 'SENSITIVE_SPOT_WINGED_ITEMS', 'SENSITIVE_SPOT_SCALY_AQUATIC_ITEMS',
    'SENSITIVE_SPOT_BEASTFOLK_ITEMS', 'TURN_ON_ITEMS', 'FETISH_ITEMS', 'ACT_PREFERENCE_REGISTRY',
    'SENSITIVE_SPOTS_TEMPLATES', 'TURN_ONS_TEMPLATES', 'FETISH_TEMPLATES', 'PLAYER_ROMANTIC_ACTION_KEYWORDS',
    'NPC_ORAL_RECEIVE_KEYWORDS', 'CONFESSION_KEYWORDS', 'NPC_ORAL_GIVE_KEYWORDS', 'NPC_MANUAL_RECEIVE_KEYWORDS',
    'NPC_MANUAL_GIVE_KEYWORDS', 'NPC_ANAL_RECEIVE_KEYWORDS', 'NPC_ANAL_GIVE_KEYWORDS', 'ANAL_KEYWORDS',
    'INTERCOURSE_KEYWORDS', 'KISS_KEYWORDS', 'DATE_KEYWORDS', 'ROMANCE_KEYWORDS',
    'INTERCOURSE_MEMORY_KEYWORDS', 'ORAL_GIVE_MEMORY_KEYWORDS', 'ORAL_RECEIVE_MEMORY_KEYWORDS',
    'MANUAL_GIVE_MEMORY_KEYWORDS', 'MANUAL_RECEIVE_MEMORY_KEYWORDS',
    'ANAL_GIVE_MEMORY_KEYWORDS', 'ANAL_RECEIVE_MEMORY_KEYWORDS',
    'TURN_OFF_ITEMS', 'TURN_OFF_TEMPLATES', 'TURN_OFF_DETECTION_REGISTRY', 'DESIRES_AND_KINKS_ITEMS',
    'ASSET_SIZE_TIERS', 'FEMALE_ASSET_TEXTURE_TEMPLATES', 'MALE_ASSET_TEXTURE_TEMPLATES',
    'SPECIES_TEXTURE_AFFINITIES', 'TIER_INCOMPATIBLE_TEXTURES'
]

