from ..core import (
    EYE_COLORS, HAIR_COLORS, HAIR_LENGTHS, HAIR_STYLES,
    STATURE_TIERS, STATURES,
    PHYSIQUE_TIERS, PHYSIQUES,
    STATURE_INCOMPATIBLE_PHYSIQUES, GENDER_INCOMPATIBLE_PHYSIQUES,
    BREAST_SIZES, PENIS_SIZES,
    DIVERSE_BEASTFOLK_COATS, DIVERSE_BEASTFOLK_SCALES, DIVERSE_BEASTFOLK_EYES, COLOR_FAMILIES,
    SPECIES_TEMPLATES, DIVERSE_FEMALE_HAIR_STYLES, DIVERSE_MALE_HAIR_STYLES,
    DIVERSE_HAIR_LENGTHS_FEMALE, DIVERSE_HAIR_LENGTHS_MALE,
    PHYSIQUE_FEMALE_TEMPLATES, PHYSIQUE_MALE_TEMPLATES,
    normalize_physique, heal_physique_for_context,
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

STATURE_WEIGHTS_MALE_TALL_GRACEFUL = {
    'miniature': 0.0,
    'short': 0.02,
    'below_average': 0.08,
    'average': 0.40,
    'tall': 0.38,
    'towering': 0.12,
}

STATURE_WEIGHTS_FEMALE_TALL_GRACEFUL = {
    'miniature': 0.0,
    'short': 0.04,
    'below_average': 0.16,
    'average': 0.45,
    'tall': 0.28,
    'towering': 0.07,
}

STATURE_WEIGHTS_TALL_GRACEFUL = STATURE_WEIGHTS_MALE_TALL_GRACEFUL

STATURE_RANK_MAP = {
    'miniature': 1,
    'short': 2,
    'below_average': 3,
    'average': 4,
    'tall': 5,
    'towering': 6,
}

PROTAGONIST_STATURE_SPATIAL_FLAIR = {
    'miniature': 'Standing at miniature fantasy scale, they weave cleanly through tight quarters and look up sharply when locking eyes with taller figures.',
    'short': 'Compact and nimble-footed, they tilt their chin upward to meet taller gazes and fit effortlessly beneath a taller partner\'s reach.',
    'below_average': 'Slightly shorter than average with quick, natural poise, angles of eye contact and shoulder reach subtly tilt upward beside taller figures.',
    'average': 'Balanced at an everyday height that meets most humanoids cleanly eye-to-eye and shoulder-to-shoulder.',
    'tall': 'Long-limbed and statuesque, their gaze naturally angles slightly downward in conversation and their stride carries easy reach.',
    'towering': 'Imposingly tall with broad spatial presence, they duck slightly beneath low lintels, cast an unmistakable silhouette in close quarters, and look steeply down in contact.',
}

ASSET_SIZE_TIERS = ('flat', 'small', 'average', 'large', 'huge')

FEMALE_ASSET_TEXTURES = (
    'Perky',
    'Firm',
    'Supple',
    'Teardrop',
    'Plush',
    'Pillowy',
    'Bouncy',
    'Delicate',
    'Sensitive',
)

MALE_ASSET_TEXTURES = (
    'Firm',
    'Veined',
    'Smooth',
    'Thick',
    'Heavy',
    'Curved',
    'Tapered',
    'Sensitive',
)

FEMALE_ASSET_TEXTURE_TEMPLATES = list(FEMALE_ASSET_TEXTURES)
MALE_ASSET_TEXTURE_TEMPLATES = list(MALE_ASSET_TEXTURES)

FEMALE_TIER_INCOMPATIBLE_TEXTURES = {
    'flat': {'Plush', 'Pillowy', 'Bouncy', 'Teardrop'},
    'small': {'Plush', 'Pillowy', 'Bouncy'},
    'average': set(),
    'large': {'Delicate'},
    'huge': {'Delicate'},
}

MALE_TIER_INCOMPATIBLE_TEXTURES = {
    'flat': {'Heavy', 'Thick'},
    'small': {'Heavy', 'Thick'},
    'average': set(),
    'large': set(),
    'huge': {'Tapered'},
}

TIER_INCOMPATIBLE_TEXTURES = {
    tier: FEMALE_TIER_INCOMPATIBLE_TEXTURES[tier] | MALE_TIER_INCOMPATIBLE_TEXTURES[tier]
    for tier in ASSET_SIZE_TIERS
}

ASSET_TEXTURE_LEGACY_MAP_FEMALE = {
    'perky & high-set': 'Perky',
    'pillowy soft & yielding': 'Pillowy',
    'firm & toned': 'Firm',
    'smooth & supple': 'Supple',
    'warm & supple': 'Supple',
    'heavy & plush': 'Plush',
    'bouncy & sensitive': 'Bouncy',
    'tender & delicate': 'Delicate',
    'shapely teardrop': 'Teardrop',
    'compact & dense': 'Firm',
    'sensitive & responsive': 'Sensitive',
    'soft & downy chest fur': 'Supple',
    'silky fur-rimmed': 'Supple',
    'velvety underbelly down': 'Plush',
    'fluffy plush-accented': 'Plush',
    'silky warm with smooth micro-scales': 'Supple',
    'supple with shimmering scale borders': 'Supple',
    'sleek & supple drake-contour': 'Firm',
    'serpentine smooth with fine scales': 'Supple',
    'downy feather-lined': 'Delicate',
    'light & buoyant': 'Perky',
    'velvety plumage accents': 'Supple',
    'glistening & ultra-smooth': 'Supple',
    'soft scaled flank accents': 'Supple',
}

ASSET_TEXTURE_LEGACY_MAP_MALE = {
    'veined & firm': 'Veined',
    'smooth & heavy': 'Heavy',
    'toned & athletic': 'Firm',
    'warm & pulsing': 'Sensitive',
    'slender & ultra-sensitive': 'Sensitive',
    'dense & formidable': 'Thick',
    'balanced & firm': 'Firm',
    'soft fur-ringed base': 'Smooth',
    'sleek scaled base & firm': 'Firm',
    'sturdy draconic build': 'Thick',
    'silky fur-dusted & resilient': 'Firm',
}

SPECIES_TEXTURE_AFFINITIES = {
    'furred': ['Supple', 'Plush', 'Perky', 'Sensitive', 'Smooth', 'Firm'],
    'scaled': ['Firm', 'Supple', 'Veined', 'Thick', 'Heavy'],
    'feathered': ['Perky', 'Delicate', 'Supple', 'Smooth', 'Tapered'],
    'aquatic': ['Supple', 'Smooth', 'Sensitive', 'Curved'],
    'fever_warm': ['Sensitive', 'Supple', 'Plush', 'Veined', 'Curved', 'Heavy'],
    'porcelain_silky': ['Perky', 'Supple', 'Delicate', 'Sensitive', 'Smooth', 'Tapered'],
    'bio_synthetic': ['Firm', 'Perky', 'Supple', 'Smooth', 'Curved'],
    'athletic': ['Firm', 'Perky', 'Veined'],
    'voluptuous': ['Pillowy', 'Plush', 'Bouncy', 'Heavy', 'Thick'],
}

SPECIES_SURFACE_KEYS = (
    'furred',
    'scaled',
    'feathered',
    'aquatic',
    'fever_warm',
    'porcelain_silky',
    'bio_synthetic',
    'natural',
)

SPECIES_SURFACE_PROFILES = {
    'furred': {
        'key': 'furred',
        'label': 'Downy Fur',
        'female_prose': 'Soft, velvety underbelly fur rims their curves, parting warm skin under probing fingers and trembling cleanly against light strokes.',
        'male_prose': 'Fine, silky fur frames their lower belly and base, framing warm bare skin with a plush, downy contrast to every stroke.',
    },
    'scaled': {
        'key': 'scaled',
        'label': 'Micro-Scales',
        'female_prose': 'Iridescent micro-scales trace their ribs and underside like satin armor, warming rapidly as flushed skin radiates heat beneath smooth edges.',
        'male_prose': 'Sleek, satin-smooth micro-scale borders frame the base cleanly, flushing with radiant warmth as blood rushes beneath the skin.',
    },
    'feathered': {
        'key': 'feathered',
        'label': 'Downy Plumage',
        'female_prose': 'Delicate wisps of chest down ruffle along their collarbone and cleavage, puffing softly whenever flustered warmth steals their breath.',
        'male_prose': 'Soft, fine plumage accents frame their hipbones and lower belly, rustling faintly against nervous heat and eager proximity.',
    },
    'aquatic': {
        'key': 'aquatic',
        'label': 'Glistening Skin',
        'female_prose': 'Silky-slick, moisture-kissed skin gleams softly in dim light, gliding effortlessly and frictionless beneath slow palms.',
        'male_prose': 'Naturally glistening, frictionless skin shimmers with warm damp smoothness that slides effortlessly in a tight grip.',
    },
    'fever_warm': {
        'key': 'fever_warm',
        'label': 'Fever-Warm Skin',
        'female_prose': 'Their chest radiates a sultry, feverish body heat that warms chill palms on contact and deepens rapidly into a dark blush.',
        'male_prose': 'They radiate an intense, fever-warm pulse straight into every gripping palm and warm breath, heavy with simmered heat.',
    },
    'porcelain_silky': {
        'key': 'porcelain_silky',
        'label': 'Porcelain-Silky Skin',
        'female_prose': 'Fine-grained, porcelain-silky skin flushes pale rose at the lightest trace of fingertips, exquisitely smooth from collarbone to curve.',
        'male_prose': 'Fine-grained, porcelain-smooth skin carries an aristocratic silkiness that flushes visibly pink with rising arousal.',
    },
    'bio_synthetic': {
        'key': 'bio_synthetic',
        'label': 'Bio-Synthetic Skin',
        'female_prose': 'Lifelike bio-synthetic dermis warms steadily at sub-dermal contact points, pulsing faintly beneath hairline seams with calibrated haptics.',
        'male_prose': 'Precision bio-synthetic skin maintains a rich vascular warmth, registering every caress across fine haptic seams with steady pressure.',
    },
    'natural': {
        'key': 'natural',
        'label': '',
        'female_prose': '',
        'male_prose': '',
    },
}

FEMALE_TEXTURE_NARRATIVE_FLAIR = {
    'Perky': 'High-set and lively, holding a taut upward tilt even braless; they bounce lightly at brisk steps and tighten briskly under teasing fingertips.',
    'Firm': 'Dense, sculpted muscle-toned resilience beneath smooth skin; palms meet proud springy resistance that holds its silhouette cleanly without flattening.',
    'Supple': 'Balanced, elastic softness that molds smoothly to a cupping hand without sagging, swaying in a slow, graceful rhythm with every breath.',
    'Teardrop': 'Tapered top sloping cleanly into a lush, full base; soft fabric drapes and hugs the curved lower swell while swaying subtly at each stride.',
    'Plush': 'Generously cushioned and rich to squeeze, bulging warmly between parted fingers and straining softly against fitted seams when confined.',
    'Pillowy': 'Deep, cloud-like yielding softness that sinks endlessly into slow palms, bulging and spilling luxuriously with every shift in posture.',
    'Bouncy': 'Loose, supple weight primed for visible motion; every step, gasp, or thrust sends ripples trembling through thin tops and bare cleavage.',
    'Delicate': 'Featherlight, compact contours framed by fragile curves; ribs and collarbones sit close, magnifying light kisses and gentle cupping.',
    'Sensitive': 'Thinned, electricity-charged skin with tight nipples that stiffen instantaneously at cool air, fabric friction, or a single damp breath.',
}

REAR_SIZE_TIERS = ('flat', 'small', 'average', 'large', 'huge')

REAR_SIZE_LABELS = {
    'flat': 'Flat',
    'small': 'Compact',
    'average': 'Shapely',
    'large': 'Plump',
    'huge': 'Bountiful',
}

REAR_ASSET_TEXTURES = (
    'Firm',
    'Taut',
    'Supple',
    'Rounded',
    'Plush',
    'Jiggly',
)

REAR_TIER_INCOMPATIBLE_TEXTURES = {
    'flat': {'Plush', 'Jiggly'},
    'small': {'Plush', 'Jiggly'},
    'average': set(),
    'large': {'Taut'},
    'huge': {'Taut'},
}

REAR_TEXTURE_SYNONYMS = {
    'firm': 'Firm',
    'sculpted': 'Firm',
    'toned': 'Taut',
    'tight': 'Taut',
    'taut': 'Taut',
    'athletic': 'Firm',
    'supple': 'Supple',
    'soft': 'Supple',
    'smooth': 'Supple',
    'warm': 'Supple',
    'velvety': 'Supple',
    'silky': 'Supple',
    'rounded': 'Rounded',
    'round': 'Rounded',
    'curvy': 'Rounded',
    'full': 'Rounded',
    'peach': 'Rounded',
    'plush': 'Plush',
    'pillowy': 'Plush',
    'cushiony': 'Plush',
    'heavy': 'Plush',
    'jiggly': 'Jiggly',
    'bouncy': 'Jiggly',
    'wobbly': 'Jiggly',
    'yielding': 'Plush',
}

REAR_TEXTURE_NARRATIVE_FLAIR = {
    'Firm': 'Dense, sculpted resilience beneath smooth skin; hands meet coiled strength and proud lift that holds its curve even through sharp movement.',
    'Taut': 'Compact, high-set tightness with crisp contours that hug tailored hems closely and resist spreading under a sudden, sharp squeeze.',
    'Supple': 'Balanced, elastic softness with an effortless peach-curved drape in fitted trousers and warm, smooth give beneath an unhurried palm.',
    'Rounded': 'Full, curving contour swelling generously from waist to thigh crease, filling seams smoothly and inviting wide, lingering grips.',
    'Plush': 'Lush, deeply cushioned softness that parts easily under pressing fingers, spilling warmly over an embrace and straining tight waistbands.',
    'Jiggly': 'Generous, lively mass rippling visibly with every brisk step or rhythmic thrust, quivering long after a playful slap or shifting weight.',
}

HEIGHT_PREFERENCE_KEYS = (
    'taller_partner',
    'shorter_partner',
)

BODY_PREFERENCE_KEYS = (
    'smaller_bb',
    'bigger_bb',
    'smaller_ass',
    'bigger_ass',
    'taller_partner',
    'shorter_partner',
)

PP_PENETRATIVE_MULTIPLIERS = {
    'flat': 0.75,
    'small': 0.85,
    'average': 1.00,
    'large': 1.15,
    'huge': 1.25,
}

BODY_PREF_AMBIENT_LIKE_MULT = 1.15
BODY_PREF_TARGETED_LIKE_MULT = 1.25
BODY_PREF_AMBIENT_DISLIKE_MULT = 0.85
BODY_PREF_TARGETED_DISLIKE_MULT = 0.80
HEIGHT_PREF_MOD_LIKE_MULT = 1.10
HEIGHT_PREF_STRONG_LIKE_MULT = 1.18
HEIGHT_PREF_MOD_DISLIKE_MULT = 0.90
HEIGHT_PREF_STRONG_DISLIKE_MULT = 0.85
HEIGHT_PREF_MOD_LIKE_DC = -1
HEIGHT_PREF_STRONG_LIKE_DC = -2
HEIGHT_PREF_DISLIKE_DC = 1
ANATOMY_COMBINED_MULT_MIN = 0.65
ANATOMY_COMBINED_MULT_MAX = 1.50
HUGE_PP_ENTRY_EXCITEMENT_THRESHOLD = 35

OPENNESS_FETISH_CHANCE = {
    'prude': 0.10,
    'moderate': 0.22,
    'bold': 0.40,
    'shameless': 0.60,
}

SOFT_ROMANTIC_FETISH_ITEMS = (
    'Praise kink & verbal validation',
    'Aftercare obsession',
    'Lingerie & silk costumes',
    'Massage oils & tactile worship',
)

MODERATE_EXCLUDED_FETISH_ITEMS = frozenset({
    'Collaring & leashes',
    'Breath play (light)',
    'Bondage & shibari ropework',
    'Public thrill & risk of being caught',
    'Impact play & gentle spanking',
    'Latex & leather accents',
})

FEMALE_EXCLUDED_ACT_IDS = frozenset({'giving_anal'})
PRUDE_VIRGIN_EXCLUDED_ACT_IDS = frozenset({'facial', 'swallowing', 'giving_anal', 'receiving_anal'})

TURN_OFF_VS_ACT_LIKE_CONFLICTS = {
    'Anal play & backdoor intimacy': frozenset({'giving_anal', 'receiving_anal'}),
    'Clumsy / careless rough handling': frozenset({'rough_handling'}),
    'Overly aggressive biting or pinching': frozenset({'rough_handling'}),
    'Rushed impatience & entitlement': frozenset({'fast_urgent'}),
    'Crude degradation & insults': frozenset({'rough_handling', 'facial'}),
}

TURN_OFF_VS_FETISH_CONFLICTS = {
    'Overly aggressive biting or pinching': frozenset({'Biting & marking'}),
    'Clumsy / careless rough handling': frozenset({
        'Impact play & gentle spanking',
        'Bondage & shibari ropework',
        'Collaring & leashes',
        'Light silk restraints',
    }),
    'Lack of discretion & careless exposure': frozenset({
        'Public thrill & risk of being caught',
        'Mirror observation & exhibition',
    }),
    'Crude degradation & insults': frozenset({
        'Audio stimulation / dirty talk',
        'Collaring & leashes',
    }),
}

MUTUALLY_EXCLUSIVE_ACT_LIKE_PAIRS = (
    ('slow_sensual', 'fast_urgent'),
)

SHORT_ANATOMY_SPOT_WORDS = frozenset({'ear', 'hip', 'rib', 'jaw', 'lip', 'paw', 'fin'})

ACT_ID_TO_EXPERIENCE_TRACK = {
    'giving_oral': 'oral',
    'receiving_oral': 'oral',
    'swallowing': 'oral',
    'facial': 'oral',
    'missionary': 'intercourse',
    'cowgirl_riding': 'intercourse',
    'from_behind': 'intercourse',
    'spooning': 'intercourse',
    'giving_anal': 'anal',
    'receiving_anal': 'anal',
    'taking_charge': None,
    'slow_sensual': None,
    'fast_urgent': None,
    'prolonged_teasing': None,
    'rough_handling': None,
}

COMBINED_INTIMATE_MULT_MIN = 0.60
COMBINED_INTIMATE_MULT_MAX = 1.60
DESIRE_EXCITEMENT_MULT = 1.15
KINK_EXCITEMENT_MULT = 1.25
ACT_LIKE_EXCITEMENT_MULT = 1.15
ACT_DISLIKE_EXCITEMENT_MULT = 0.75
GIVING_SERVICE_PLAYER_MULT = 1.15
GIVING_SERVICE_NPC_BONUS = 6
GIVING_SERVICE_NPC_CAP = 75
FOREPLAY_SPOT_WARMUP_BONUS = 6
FOREPLAY_SPOT_WARMUP_CAP = 45
TURN_OFF_EXCITEMENT_DROP = 15
MAX_PREFERENCE_DC_PENALTY = 6

DESIRE_AND_KINK_REGISTRY = [
    # 20 Action Desires
    {'id': 'eye_contact', 'name': 'Intimate eye contact', 'kind': 'desire', 'keywords': ['eye contact', 'lock eyes', 'stare into', 'gaze into']},
    {'id': 'breath_on_skin', 'name': 'Breath against sensitive skin', 'kind': 'desire', 'keywords': ['warm breath', 'hot breath', 'breath against', 'breathe against', 'exhale softly']},
    {'id': 'breathless_moans', 'name': 'Soft breathless moans', 'kind': 'desire', 'keywords': ['moan', 'moans', 'breathless gasp', 'whimper softly']},
    {'id': 'neck_kisses', 'name': 'Neck kisses', 'kind': 'desire', 'keywords': ['kiss neck', 'kisses along neck', 'kissing neck', 'neck kiss', 'nape kiss', 'throat kiss']},
    {'id': 'dominant_whispers', 'name': 'Dominant whispers', 'kind': 'desire', 'keywords': ['dominant whisper', 'commanding whisper', 'low command', 'whisper firmly', 'murmur command']},
    {'id': 'gentle_nibbling', 'name': 'Gentle nibbling & biting', 'kind': 'desire', 'keywords': ['nibble', 'gentle bite', 'nibbling', 'tease with teeth', 'nip softly']},
    {'id': 'hair_stroking', 'name': 'Hair stroking & gentle pulling', 'kind': 'desire', 'keywords': ['stroke hair', 'tangle fingers in hair', 'hair pulling', 'tug hair', 'grip hair', 'card fingers through']},
    {'id': 'playful_teasing', 'name': 'Playful teasing', 'kind': 'desire', 'keywords': ['playful tease', 'teasingly', 'tease', 'banter', 'smirk', 'playfully']},
    {'id': 'hand_holding', 'name': 'Hand-holding with interlocked fingers', 'kind': 'desire', 'keywords': ['interlock fingers', 'lace fingers', 'hold hands', 'hand-holding', 'clasp hands']},
    {'id': 'physical_worship', 'name': 'Gentle physical worship', 'kind': 'desire', 'keywords': ['worship', 'reverent touch', 'adore every inch', 'tender worship', 'devoted touch']},
    {'id': 'warm_embraces', 'name': 'Sudden warm embraces', 'kind': 'desire', 'keywords': ['sudden embrace', 'pull close', 'wrap arms tightly', 'warm embrace', 'hold tight']},
    {'id': 'partner_scent', 'name': 'Scent of partner', 'kind': 'desire', 'keywords': ['inhale scent', 'breathe in', 'scent', 'perfume', 'musk']},
    {'id': 'light_nails', 'name': 'Light nails along skin', 'kind': 'desire', 'keywords': ['light nails', 'fingernails', 'trace nails', 'drag nails', 'scratch lightly']},
    {'id': 'pinned_gently', 'name': 'Being pinned gently', 'kind': 'desire', 'keywords': ['pin against', 'pinned', 'hold wrists down', 'press down gently']},
    {'id': 'collarbone_kisses', 'name': 'Teasing kisses on collarbone', 'kind': 'desire', 'keywords': ['collarbone kiss', 'kiss collarbone', 'kisses along collarbone', 'clavicle']},
    {'id': 'passionate_urgency', 'name': 'Passionate urgency', 'kind': 'desire', 'keywords': ['urgent', 'urgency', 'feverish', 'hungry pace', 'breathless rush']},
    {'id': 'forehead_rests', 'name': 'Affectionate forehead rests', 'kind': 'desire', 'keywords': ['forehead against', 'rest forehead', 'brow together', 'touch foreheads']},
    {'id': 'endearing_names', 'name': 'Being called endearing names', 'kind': 'desire', 'keywords': ['sweetheart', 'darling', 'my love', 'pet name', 'endearing', 'good girl', 'good boy']},
    {'id': 'slow_undressing', 'name': 'Slow undressing', 'kind': 'desire', 'keywords': ['slow undress', 'unbutton slowly', 'peel off slowly', 'slip off slowly', 'undress slowly']},
    {'id': 'ear_whispering', 'name': 'Ear whispering', 'kind': 'desire', 'keywords': ['whisper in ear', 'whispered in', 'murmur against ear', 'ear whisper']},
    # 21 Fetishes / Kinks
    {'id': 'petplay', 'name': 'Petplay & ear/tail caressing', 'kind': 'kink', 'keywords': ['petplay', 'pet play', 'caress tail', 'rub ears', 'scratch behind ear', 'good pet']},
    {'id': 'blindfolds', 'name': 'Blindfolds & sensory deprivation', 'kind': 'kink', 'keywords': ['blindfold', 'blindfolded', 'cover eyes', 'sensory deprivation', 'silk sash over eyes']},
    {'id': 'lingerie_costumes', 'name': 'Lingerie & silk costumes', 'kind': 'kink', 'keywords': ['lingerie', 'silk costume', 'lace', 'stockings', 'garter', 'corset']},
    {'id': 'silk_restraints', 'name': 'Light silk restraints', 'kind': 'kink', 'keywords': ['silk restraint', 'tie wrists', 'bind wrists', 'bound with ribbon', 'scarf around wrists']},
    {'id': 'praise_kink', 'name': 'Praise kink & verbal validation', 'kind': 'kink', 'keywords': ['praise', 'good girl', 'good boy', 'so proud of you', 'doing so well', 'perfect for me']},
    {'id': 'public_thrill', 'name': 'Public thrill & risk of being caught', 'kind': 'kink', 'keywords': ['caught', 'risk of', 'someone walks in', 'public', 'behind closed door', 'quietly so nobody']},
    {'id': 'gentle_dom_sub', 'name': 'Gentle dominance / submission', 'kind': 'kink', 'keywords': ['submit', 'obey', 'kneel', 'let me lead', 'yield to me', 'submission', 'dominate softly']},
    {'id': 'costume_roleplay', 'name': 'Costume / uniform roleplay', 'kind': 'kink', 'keywords': ['roleplay', 'uniform', 'costume', 'pretend to be', 'maid', 'knight']},
    {'id': 'biting_marking', 'name': 'Biting & marking', 'kind': 'kink', 'keywords': ['hickey', 'love bite', 'leave a mark', 'marking', 'bite mark']},
    {'id': 'temperature_play', 'name': 'Temperature play (ice & warmth)', 'kind': 'kink', 'keywords': ['ice cube', 'melt ice', 'warm wax', 'chill against', 'temperature play']},
    {'id': 'edging', 'name': 'Overstimulation & gentle edging', 'kind': 'kink', 'keywords': ['edge', 'edging', 'overstimulat', 'hold back', 'right on the brink', 'don\'t cum yet']},
    {'id': 'mirror_exhibition', 'name': 'Mirror observation & exhibition', 'kind': 'kink', 'keywords': ['mirror', 'watch yourself', 'reflection', 'exhibition']},
    {'id': 'massage_oils', 'name': 'Massage oils & tactile worship', 'kind': 'kink', 'keywords': ['massage oil', 'rub oil', 'slick oil', 'oil massage', 'scented oil']},
    {'id': 'aftercare', 'name': 'Aftercare obsession', 'kind': 'kink', 'keywords': ['aftercare', 'cuddle after', 'wipe clean', 'wrap in blanket', 'hold after climax']},
    {'id': 'collaring', 'name': 'Collaring & leashes', 'kind': 'kink', 'keywords': ['collar', 'leash', 'clasp collar', 'tug leash']},
    {'id': 'impact_spanking', 'name': 'Impact play & gentle spanking', 'kind': 'kink', 'keywords': ['spank', 'spanking', 'smack', 'slap rear', 'paddle']},
    {'id': 'breath_play', 'name': 'Breath play (light)', 'kind': 'kink', 'keywords': ['breath play', 'hand around throat', 'light choke', 'squeeze throat lightly']},
    {'id': 'mutual_voyeurism', 'name': 'Mutual masturbation / voyeurism', 'kind': 'kink', 'keywords': ['touch yourself', 'watch you touch', 'mutual masturbation', 'masturbate together']},
    {'id': 'latex_leather', 'name': 'Latex & leather accents', 'kind': 'kink', 'keywords': ['latex', 'leather', 'harness', 'vinyl', 'boots']},
    {'id': 'dirty_talk', 'name': 'Audio stimulation / dirty talk', 'kind': 'kink', 'keywords': ['dirty talk', 'filthy whisper', 'talk dirty', 'explicitly describe', 'lewd words']},
    {'id': 'shibari', 'name': 'Bondage & shibari ropework', 'kind': 'kink', 'keywords': ['shibari', 'rope', 'knot', 'ropework', 'tie up in rope']},
]

MALE_TEXTURE_NARRATIVE_FLAIR = {
    'Firm': 'Taut, dense rigidity that meets palms like spring-steel muscle, pulsing cleanly against tight fabric without flexing away under pressure.',
    'Veined': 'Ridged along its underside and flanks by raised, heat-throbbing veins that swell visibly against bare palms and trace distinct relief inside a grip.',
    'Smooth': 'Sleek, clean lines uninterrupted by heavy ridges; glides seamlessly between slick fingers or tight warmth with effortless friction.',
    'Thick': 'Substantial girth that forces fingers apart and stretches tight closures wide, pressing solidly from base to crown on every stroke.',
    'Heavy': 'Noticeable, pendulous mass that hangs low and swings slowly when freed, thudding with satisfying weight against warm thighs or stomach.',
    'Curved': 'Distinct natural upward arc angled to sweep firmly against shallow internal curves, bulging conspicuously along tight trousers.',
    'Tapered': 'Streamlined silhouette subtly narrower toward the crown, allowing easy initial parting and slick, gradual gliding straight to the hilt.',
    'Sensitive': 'Flush with heat-reactive nerve endings; every wet kiss, slow thumb swipe, or teasing squeeze triggers an immediate, shuddering pulse.',
}

PHYSIQUE_NARRATIVE_FLAIR = {
    'Slim': {
        'female': {
            'presence': 'Svelte, narrow-waisted silhouette with long, fine-boned limbs; tailored hems, belts, and loose cloaks drape effortlessly over slim collarbones and light steps.',
            'embrace': 'Fingers bridge easily around a lithe waist and slim ribs, emphasizing warm, featherlight responsiveness tucked close.',
        },
        'male': {
            'presence': 'Lean, narrow-framed silhouette with wire-light agility; fitted coats and tunics hang cleanly off trim shoulders while movement stays noiseless and swift.',
            'embrace': 'Lean flanks, slim hips, and crisp rib lines press close with wiry warmth and brisk responsiveness under wandering hands.',
        },
        'neutral': {
            'presence': 'Lithe, trim silhouette with fine bone lines and fluid grace; garments hang cleanly without bulk as every step stays light and nimble.',
            'embrace': 'Narrow ribs and a streamlined waist yield effortlessly inside curving arms, emphasizing nimble warmth.',
        },
    },
    'Average': {
        'female': {
            'presence': 'Balanced, natural proportions with soft symmetry across waist, hips, and shoulders; everyday attire fits with understated, comfortable poise.',
            'embrace': 'Natural, unhurried contours settle easily into an embrace, trading theatrical extremes for cozy, familiar body heat.',
        },
        'male': {
            'presence': 'Evenly proportioned frame with balanced shoulders and steady stride; everyday jackets and gear sit naturally without looking sparse or bulky.',
            'embrace': 'Solid, unpretentious proportions meet an embrace at comfortable symmetry with steady, approachable warmth.',
        },
        'neutral': {
            'presence': 'Proportionate, everyday build with balanced limbs and relaxed posture; clothes drape evenly through casual or brisk movement.',
            'embrace': 'Familiar, balanced contours press warmly against a partner without straining or receding.',
        },
    },
    'Athletic': {
        'female': {
            'presence': 'Toned, poised runner-and-duelist frame with sculpted calves, clean waist-to-shoulder taper, and springy posture; fitted sleeves hug lean, defined arms.',
            'embrace': 'Firm flanks, taut stomach, and resilient muscle beneath warm skin flex smoothly in response to gripping hands.',
        },
        'male': {
            'presence': 'Trim, corded swimmer-and-fighter build with defined forearms, V-tapered back, and coiled grace; shirts pull lightly across active shoulders on sharp turns.',
            'embrace': 'Taut core, wired forearms, and sculpted ridges shift with springy tension when pulled flush chest-to-chest.',
        },
        'neutral': {
            'presence': 'Lithesome, conditioned frame with crisp posture and economical, quick-footed stride; garments skim sleek muscle during motion.',
            'embrace': 'Conditioned resilience and firm contours answer every touch with agile, reactive tone.',
        },
    },
    'Muscular': {
        'male': {
            'presence': 'Thickly muscled, imposing frame with broad shoulders, corded neck, and rolling triceps that crowd tailored seams; every step carries heavy, unhurried authority.',
            'embrace': 'Hard pectoral planes, thick biceps, and iron-solid flanks feel immovable and furnace-warm when locked in close contact.',
        },
        'female': {
            'presence': 'Powerfully conditioned silhouette with bold shoulders, chiseled arms, and commanding stance that fills armor straps and coats with unmistakable strength.',
            'embrace': 'Dense, sculpted muscle across back and thighs imparts gripping strength and radiating heat against a partner.',
        },
        'neutral': {
            'presence': 'Heavy-muscled build with broad upper-body presence and seams pulled taut across dense shoulders and back.',
            'embrace': 'Solid, thick-corded muscle and deep core heat surround a partner with overpowering physical anchor.',
        },
    },
    'Voluptuous': {
        'female': {
            'presence': 'Lush hourglass sweep of full hips, soft thighs, and pinched waist that strains tailored buttons and sways with slow, magnetic rhythm at every step.',
            'embrace': 'Plush, intoxicating curves and warm, heavy thighs cushion an embrace deeply, spilling softly between tightening palms.',
        },
        'male': {
            'presence': 'Full, curving lower-body sweep and broad hip line carrying lush softness beneath draped fabric.',
            'embrace': 'Deep, soft curves yield luxuriantly beneath gripping palms with lingering body heat.',
        },
        'neutral': {
            'presence': 'Abundantly curved silhouette with generous lower swell and slow, alluring sway beneath fitted waistlines.',
            'embrace': 'Lush, cushioned contours mold deeply into holding arms with enveloping softness and heat.',
        },
    },
    'Stocky': {
        'male': {
            'presence': 'Thick-set, barrel-chested build with squared jaw, thick wrists, and broad trunk planted like stone; heavy boots and coats sit squarely on a sturdy frame.',
            'embrace': 'Broad ribcage, thick shoulders, and grounded weight wrap around a partner like a warm, unshakeable wall.',
        },
        'female': {
            'presence': 'Compact, solid-hipped and strong-framed build with sturdy limbs and grounded center of balance; tunics and aprons sit firmly across a durable silhouette.',
            'embrace': 'Sturdy hips, thick warm thighs, and compact strength press back with cozy, steadfast solidity in close holds.',
        },
        'neutral': {
            'presence': 'Broad-trunked, grounded build with sturdy joints and thick, enduring stance that refuses to be jostled.',
            'embrace': 'Compact density and reassuring physical weight anchor an embrace with steady warmth.',
        },
    },
    'Chubby': {
        'female': {
            'presence': 'Generously soft, rounded curves across belly, upper arms, and plush thighs; belted dresses dimple gently over cozy fullness with unhurried, cushioning movement.',
            'embrace': 'Pillowy, yielding softness and cozy body heat invite hands to sink into round hips and warm, plush flanks.',
        },
        'male': {
            'presence': 'Broad, full-bodied build with rounded midsection, hefty arms, and relaxed posture; vests and loose shirts settle comfortably across warm, generous bulk.',
            'embrace': 'Generous, heavy cushioning radiates oven-warm comfort, molding softly whenever a partner leans or climbs close.',
        },
        'neutral': {
            'presence': 'Rounded, full-bodied silhouette with gentle, soft lines across waist and limbs; loose fabric drapes in easy folds.',
            'embrace': 'Warm, deeply cushioned softness envelops touch with comforting weight and relaxed heat.',
        },
    },
}

VALID_MILESTONE_EVENTS = {'oral_receive', 'manual_receive', 'kiss', 'oral_give', 'oral_mutual', 'date', 'first_kiss', 'manual_give', 'manual_mutual', 'anal_give', 'anal_receive', 'anal_mutual', 'anal', 'affection', 'none', 'intercourse', 'confession'}
NSFW_SCENARIOS = {'nsfw_high_school_drama'}
INTIMATE_DEMEANOR_FEMALE_TEMPLATES = ['Playful & Bantering, teases warmly and laughs softly between kisses', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and emotional closeness', 'Poised & Articulate, calm, deliberate with a low, husky seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and fervent, vocal praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, flustered pauses, earnest sincerity and endearing shyness']
INTIMATE_DEMEANOR_MALE_TEMPLATES = ['Playful & Bantering, teases warmly with lighthearted confidence', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and steady emotional closeness', 'Poised & Articulate, calm, composed with a low, steady seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and fervent, vocal praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, thoughtful pauses, earnest sincerity and endearing shyness']
INTIMATE_DEMEANOR_TEMPLATES = ['Playful & Bantering, teases warmly and laughs softly between kisses', 'Soft & Deeply Affectionate, tender whispers, warm lingering touch and emotional closeness', 'Poised & Articulate, calm, deliberate with a low, husky seductive tone', 'Passionate & Vocal, deeply expressive, breathless gasps and fervent, vocal praise', 'Blunt & Teasing, energetic directness, honest reactions and confident remarks', 'Hesitant & Flustered, flustered pauses, earnest sincerity and endearing shyness']
INTIMATE_DYNAMIC_TEMPLATES = ['Boldly Proactive & Dominant (Takes physical initiative, guides the pace, confident on top)', 'Playful Switch / Teasing Brat (Tests limits and challenges partner, shifts fluidly between leading and yielding)', 'Eagerly Receptive / Surrenders Control (Enthusiastic participant who craves partner taking firm charge and guiding the pace)', 'Insatiable / Hidden High-Drive (Intensely voracious and relentless private physical drive, craving deep stamina and repeat closeness)', 'Gentle & Yielding (Soft, tenderly responsive surrender; thrives on unhurried affection and gentle reassurance)', "Attentive Service-Oriented (Derives peak pleasure from partner's pleasure, devoted and focused on giving)"]
EROTIC_OPENNESS_TIERS = ['prude', 'moderate', 'bold', 'shameless']
EROTIC_OPENNESS_TEMPLATES = {'prude': 'Prude / Modest (High modesty barrier around public decorum and explicit talk; strictly romance-focused until deep private trust is earned)', 'moderate': 'Reserved / Moderate (Values timing and private decorum; naturally comfortable with intimacy once mutual romance builds)', 'bold': 'Bold / Uninhibited (Sex-positive and unbothered by scandal; freely enjoys double entendres, confident flirting, and spicy media)', 'shameless': 'Shameless / Lewd (Zero verbal filter around intimacy and desire; candidly provocative in banter and DMs without shame)'}

# Zero-Schema With-You Comfort, Gap-Moe Contrast & Openness Gameplay Tuning
COMFORT_LIVE_STANDING_FLOOR = 50
COMFORT_WARMING_UP_SCORE = 100
COMFORT_WARMING_UP_DM_SCORE = 70
COMFORT_TRUSTING_SCORE = 150
COMFORT_TRUSTING_MILESTONES_ONLY = 3
ALL_TALK_TEASE_GRADUATION_MILESTONES = 2

OPENNESS_RUSHED_WARMUP_MULT = 0.80
OPENNESS_RUSHED_AROUSAL_THRESHOLD = 40
OPENNESS_TENDER_FOREPLAY_MULT = 1.15
OPENNESS_BOLD_MOMENTUM_MULT = 1.10
OPENNESS_HIDDEN_FIRE_MULT = 1.10
OPENNESS_HIDDEN_FIRE_DEMAND_BONUS = 0.10
OPENNESS_BYSTANDER_DAMPEN_MULT = 0.70
OPENNESS_BYSTANDER_THRILL_MULT = 1.15
OPENNESS_MULTIPARTNER_BOLD_MULT = 1.10
OPENNESS_MULTIPARTNER_SHY_MULT = 0.85
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
    'EYE_COLORS', 'HAIR_COLORS', 'HAIR_LENGTHS', 'HAIR_STYLES', 'STATURES', 'STATURE_TIERS', 'STATURE_RANK_MAP',
    'PROTAGONIST_STATURE_SPATIAL_FLAIR', 'STATURE_WEIGHTS_MINIATURE', 'STATURE_WEIGHTS_TINY_BEASTFOLK', 'STATURE_WEIGHTS_SMALL_BEASTFOLK',
    'STATURE_WEIGHTS_LARGE_BEASTFOLK', 'STATURE_WEIGHTS_STANDARD', 'STATURE_WEIGHTS_TALL_GRACEFUL',
    'STATURE_WEIGHTS_MALE_STANDARD', 'STATURE_WEIGHTS_FEMALE_STANDARD',
    'STATURE_WEIGHTS_MALE_TALL_GRACEFUL', 'STATURE_WEIGHTS_FEMALE_TALL_GRACEFUL',
    'STATURE_WEIGHTS_MALE_LARGE_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_LARGE_BEASTFOLK',
    'STATURE_WEIGHTS_MALE_SMALL_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_SMALL_BEASTFOLK',
    'STATURE_WEIGHTS_MALE_TINY_BEASTFOLK', 'STATURE_WEIGHTS_FEMALE_TINY_BEASTFOLK',
    'STATURE_INCOMPATIBLE_PHYSIQUES',
    'GENDER_INCOMPATIBLE_PHYSIQUES',
    'PHYSIQUE_TIERS', 'PHYSIQUES',
    'normalize_physique', 'heal_physique_for_context',
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
    'ASSET_SIZE_TIERS', 'FEMALE_ASSET_TEXTURES', 'MALE_ASSET_TEXTURES',
    'FEMALE_ASSET_TEXTURE_TEMPLATES', 'MALE_ASSET_TEXTURE_TEMPLATES',
    'FEMALE_TIER_INCOMPATIBLE_TEXTURES', 'MALE_TIER_INCOMPATIBLE_TEXTURES', 'TIER_INCOMPATIBLE_TEXTURES',
    'ASSET_TEXTURE_LEGACY_MAP_FEMALE', 'ASSET_TEXTURE_LEGACY_MAP_MALE',
    'SPECIES_TEXTURE_AFFINITIES', 'SPECIES_SURFACE_KEYS', 'SPECIES_SURFACE_PROFILES',
    'FEMALE_TEXTURE_NARRATIVE_FLAIR', 'MALE_TEXTURE_NARRATIVE_FLAIR', 'PHYSIQUE_NARRATIVE_FLAIR',
    'REAR_SIZE_TIERS', 'REAR_SIZE_LABELS', 'REAR_ASSET_TEXTURES',
    'REAR_TIER_INCOMPATIBLE_TEXTURES', 'REAR_TEXTURE_SYNONYMS', 'REAR_TEXTURE_NARRATIVE_FLAIR',
    'HEIGHT_PREFERENCE_KEYS', 'BODY_PREFERENCE_KEYS', 'PP_PENETRATIVE_MULTIPLIERS',
    'BODY_PREF_AMBIENT_LIKE_MULT', 'BODY_PREF_TARGETED_LIKE_MULT',
    'BODY_PREF_AMBIENT_DISLIKE_MULT', 'BODY_PREF_TARGETED_DISLIKE_MULT',
    'HEIGHT_PREF_MOD_LIKE_MULT', 'HEIGHT_PREF_STRONG_LIKE_MULT',
    'HEIGHT_PREF_MOD_DISLIKE_MULT', 'HEIGHT_PREF_STRONG_DISLIKE_MULT',
    'HEIGHT_PREF_MOD_LIKE_DC', 'HEIGHT_PREF_STRONG_LIKE_DC', 'HEIGHT_PREF_DISLIKE_DC',
    'ANATOMY_COMBINED_MULT_MIN', 'ANATOMY_COMBINED_MULT_MAX',
    'HUGE_PP_ENTRY_EXCITEMENT_THRESHOLD',
    'OPENNESS_FETISH_CHANCE', 'SOFT_ROMANTIC_FETISH_ITEMS', 'MODERATE_EXCLUDED_FETISH_ITEMS',
    'FEMALE_EXCLUDED_ACT_IDS', 'PRUDE_VIRGIN_EXCLUDED_ACT_IDS',
    'TURN_OFF_VS_ACT_LIKE_CONFLICTS', 'TURN_OFF_VS_FETISH_CONFLICTS', 'MUTUALLY_EXCLUSIVE_ACT_LIKE_PAIRS',
    'SHORT_ANATOMY_SPOT_WORDS', 'ACT_ID_TO_EXPERIENCE_TRACK',
    'COMBINED_INTIMATE_MULT_MIN', 'COMBINED_INTIMATE_MULT_MAX',
    'DESIRE_EXCITEMENT_MULT', 'KINK_EXCITEMENT_MULT',
    'ACT_LIKE_EXCITEMENT_MULT', 'ACT_DISLIKE_EXCITEMENT_MULT',
    'GIVING_SERVICE_PLAYER_MULT', 'GIVING_SERVICE_NPC_BONUS', 'GIVING_SERVICE_NPC_CAP',
    'FOREPLAY_SPOT_WARMUP_BONUS', 'FOREPLAY_SPOT_WARMUP_CAP',
    'TURN_OFF_EXCITEMENT_DROP', 'MAX_PREFERENCE_DC_PENALTY',
    'DESIRE_AND_KINK_REGISTRY',
    'COMFORT_LIVE_STANDING_FLOOR', 'COMFORT_WARMING_UP_SCORE', 'COMFORT_WARMING_UP_DM_SCORE',
    'COMFORT_TRUSTING_SCORE', 'COMFORT_TRUSTING_MILESTONES_ONLY',
    'ALL_TALK_TEASE_GRADUATION_MILESTONES', 'OPENNESS_RUSHED_WARMUP_MULT',
    'OPENNESS_RUSHED_AROUSAL_THRESHOLD', 'OPENNESS_TENDER_FOREPLAY_MULT',
    'OPENNESS_BOLD_MOMENTUM_MULT', 'OPENNESS_HIDDEN_FIRE_MULT',
    'OPENNESS_HIDDEN_FIRE_DEMAND_BONUS', 'OPENNESS_BYSTANDER_DAMPEN_MULT',
    'OPENNESS_BYSTANDER_THRILL_MULT', 'OPENNESS_MULTIPARTNER_BOLD_MULT',
    'OPENNESS_MULTIPARTNER_SHY_MULT',
]

