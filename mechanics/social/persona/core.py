from __future__ import annotations
import json
import hashlib
import random
import re
from typing import Dict, Any, List, Optional


EYE_COLORS = {"blue", "brown", "green", "hazel", "amber", "red", "glowing_blue", "glowing_red", "violet", "black", "gold", "silver"}

HAIR_COLORS = {"black", "blonde", "brown", "red", "dark_blue", "silver", "pink", "purple", "white", "auburn", "brunette", "green"}

HAIR_LENGTHS = {"short", "medium", "long", "shoulder_length", "bald", "waist_length", "pixie"}

HAIR_STYLES = {"straight", "wavy", "curly", "braided", "ponytail", "messy", "afro", "bob", "bun", "spiky"}

STATURE_TIERS = ("short", "below_average", "average", "tall", "towering")
STATURES = {"short", "below_average", "average", "tall", "towering", "gigantic", "dwarf", "petite"}

BREAST_SIZES = {"flat", "small", "medium", "large", "huge", "hyper"}

PENIS_SIZES = {"tiny", "small", "average", "large", "huge"}

SCHEMA_GARBAGE_PATTERNS = (
    "new_traits", "new_turn_ons", "new_sensitive_spots", "new_demeanor",
    "new_dynamic", "new_fetishes", "new_preferences", "new_act_likes", "new_act_dislikes",
    "string or empty", "short 1-2", "short 1-3"
)

def is_schema_noise(val: Any) -> bool:
    """Checks whether a string contains schema template placeholders or unparsed code syntax."""
    if not val or not isinstance(val, str):
        return False
    s = val.strip().lower()
    if any(p in s for p in SCHEMA_GARBAGE_PATTERNS):
        return True
    if any(c in s for c in ("[", "]", "{", "}")):
        return True
    return False

def is_valid_persona_attribute_string(val: Any) -> bool:
    """Validates that a persona attribute string contains authentic descriptive text and is not raw schema/syntax noise."""
    if not val or not isinstance(val, str):
        return False
    s = val.strip().lower()
    if len(s) < 2:
        return False
    if s in ("none (vanilla)", "vanilla"):
        return True
    if is_schema_noise(s):
        return False
    if s in ("none", "null", "undefined", "unknown", "n/a", "string", "empty", "???", "?"):
        return False
    return True

def clean_attribute_list_string(val: Any) -> str:
    """Cleans a string, list, or stringified list into a clean, comma-separated display string without brackets or quotes."""
    if val is None:
        return ""
    if isinstance(val, (list, tuple, set)):
        items = [str(x).strip().strip("'\"") for x in val if str(x).strip().strip("'\"") and not is_schema_noise(str(x))]
        cleaned = [x.title() if len(x.split()) == 1 else x[0].upper() + x[1:] if x else x for x in items]
        return ", ".join(cleaned)
    s = str(val).strip()
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
        import ast
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple, set)):
                items = [str(x).strip().strip("'\"") for x in parsed if str(x).strip().strip("'\"") and not is_schema_noise(str(x))]
                cleaned = [x.title() if len(x.split()) == 1 else x[0].upper() + x[1:] if x else x for x in items]
                return ", ".join(cleaned)
        except Exception:
            inner = s[1:-1].replace("'", "").replace('"', "")
            items = [x.strip() for x in inner.split(",") if x.strip() and not is_schema_noise(x)]
            cleaned = [x.title() if len(x.split()) == 1 else x[0].upper() + x[1:] if x else x for x in items]
            return ", ".join(cleaned)
    if is_schema_noise(s):
        return ""
    return s

DIVERSE_BEASTFOLK_COATS = [
    "Snow White Fur", "Midnight Black Fur", "Pastel Pink Fur", "Cerulean Blue Fur",
    "Golden-Cream Fur", "Lavender Fur", "Silky Silver-Gray Fur", "Bright Orange Fur",
    "Smoky Charcoal Fur", "Crimson-Tipped Fur", "Calico Fur", "Rose-Gold Fur"
]

DIVERSE_BEASTFOLK_SCALES = [
    "Shiny Smooth Emerald Scales", "Shiny Smooth Cerulean Scales", "Shiny Smooth Obsidian Scales",
    "Shiny Smooth Ruby Scales", "Shiny Smooth Sapphire Scales", "Shiny Smooth Gilded Scales",
    "Gecko-Like Pale Mint Scales", "Gecko-Like Dusty Sand Scales", "Gecko-Like Mottled Amber Scales", "Gecko-Like Soft Olive Scales",
    "Flame-Red Dragon Scales", "Vibrant Flame-Red Scales", "Smoldering Crimson Scales", "Molten Copper Scales",
    "Shiny Blue Cerulean Scales", "Iridescent Cobalt Scales", "Shimmering Prismatic Scales", "Pearlescent Opal Scales", "Diamond-Bright Silver Scales",
    "Matte Charcoal Armored Scales", "Glistening Jade Scales", "Deep Obsidian Scales", "Sunburst Topaz Scales", "Metallic Bronze Scales"
]

DIVERSE_BEASTFOLK_EYES = [
    "Sapphire Blue", "Emerald Green", "Amethyst Purple", "Ruby Red",
    "Heterochromatic Blue-Green", "Golden-Yellow", "Violet", "Crimson",
    "Glistening Amber", "Silver-Gray", "Luminous Topaz", "Hypnotic Slit-Amber",
    "Emerald Slit", "Smoldering Molten-Gold"
]

COLOR_FAMILIES = {
    "blue": {
        "blue", "azure", "cobalt", "cerulean", "sapphire", "cyan", "sky", "indigo", "navy",
        "ice", "teal", "turquoise", "periwinkle", "denim", "aquamarine", "ultramarine"
    },
    "green": {
        "green", "emerald", "jade", "mint", "olive", "forest", "seafoam", "sage", "moss",
        "lime", "chartreuse", "pine", "fern", "pistachio"
    },
    "pink": {
        "pink", "rose", "sakura", "magenta", "bubblegum", "coral", "blush", "salmon",
        "fuchsia", "carnation", "peony"
    },
    "purple": {
        "purple", "violet", "lavender", "amethyst", "plum", "lilac", "orchid", "mauve",
        "grape", "mulberry", "iris"
    },
    "red": {
        "red", "crimson", "ruby", "scarlet", "vermilion", "cherry", "rust", "auburn",
        "copper", "ginger", "cinnamon", "orange", "flame", "amber", "ember", "brick", "maroon", "burgundy"
    },
    "blonde": {
        "blonde", "blond", "gold", "golden", "honey", "wheat", "cream", "champagne",
        "apricot", "flaxen", "straw", "sandy", "fawn", "citrine", "topaz"
    },
    "brown": {
        "brown", "chestnut", "chocolate", "hazel", "umber", "caramel", "tawny",
        "walnut", "sepia", "cocoa", "espresso", "brunette", "coffee", "mocha"
    },
    "black": {
        "black", "obsidian", "jet", "charcoal", "midnight", "slate", "ebony",
        "shadow", "onyx", "raven", "coal"
    },
    "white": {
        "white", "snow", "platinum", "silver", "ash", "frost", "pale",
        "ivory", "pearl", "alabaster"
    }
}

def get_color_families(text: str) -> set[str]:
    """Returns all color families that match tokens in the description string."""
    if not text:
        return set()
    low = str(text).lower()
    words = re.findall(r'[a-z]+', low)
    matched = set()
    for word in words:
        for family, keywords in COLOR_FAMILIES.items():
            if word in keywords or any(kw in word for kw in keywords if len(kw) >= 4):
                matched.add(family)
    return matched

def is_contrasting_shade(coat_color: str, hair_color: str) -> bool:
    """
    Checks if a beastfolk character's hair color is a contrasting shade to their fur/coat/scales.
    Contrasting shades (e.g. golden-blonde coat with black hair, or blue fur with red hair) indicate dyed hair.
    Matching or harmonious shades (e.g. blue fur with blue hair, or pink fur with pink hair) indicate natural hair.
    """
    if not coat_color or not hair_color:
        return False
    coat_fams = get_color_families(coat_color)
    hair_fams = get_color_families(hair_color)
    if not coat_fams or not hair_fams:
        return False
    # If they share any family, they are harmonious/matching, not contrasting
    if coat_fams & hair_fams:
        return False

    # Check compatible cross-family nuances (natural multi-tonal mammalian coats/hair)
    if ("blonde" in coat_fams and "red" in hair_fams) or ("red" in coat_fams and "blonde" in hair_fams):
        return False
    if ("brown" in coat_fams and "red" in hair_fams) or ("red" in coat_fams and "brown" in hair_fams):
        return False
    if ("brown" in coat_fams and "black" in hair_fams) or ("black" in coat_fams and "brown" in hair_fams):
        return False
    if ("blonde" in coat_fams and "brown" in hair_fams) or ("brown" in coat_fams and "blonde" in hair_fams):
        return False
    if ("white" in coat_fams and "blonde" in hair_fams) or ("blonde" in coat_fams and "white" in hair_fams):
        return False

    return True

def is_scaly_race(race_str: str, desc: str = "") -> bool:
    """Checks if a race/entity is reptilian, draconic, serpentine, or scaly subspecies."""
    r = (str(race_str or "") + " " + str(desc or "")).lower().replace("-", "_")
    return any(k in r for k in (
        "reptile", "reptilian", "lizard", "dragon", "dragonkin", "draconoid", "draconic",
        "drake", "wyvern", "wyrm", "snake", "serpent", "serpentine", "naga", "viper", "cobra",
        "crocodile", "alligator", "crocodilian", "gator", "gecko", "chameleon", "salamander",
        "tortoise", "turtle", "saurian", "dinosaur", "basilisk", "hydra", "scaly"
    ))

def infer_natural_hair_color_from_coat(coat_color: str, race: str = "") -> str:
    """Extracts or infers a clean natural hair color matching the character's biological coat or scales."""
    if coat_color:
        clean = re.sub(r'\b(fur|coat|scales|scale|feathers|feather|dragon|drake|reptile|reptilian|serpent|serpentine|pattern|dense|silky|fluffy|velvety|shiny|smooth|gecko-like|gecko|armored|mottled|iridescent|matte|like)\b', '', str(coat_color), flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s+', ' ', clean).strip(' -')
        if clean:
            return clean.lower()
    race_low = str(race or "").lower()
    if is_scaly_race(race_low):
        if "dragon" in race_low:
            return "crimson red"
        elif "snake" in race_low:
            return "serpentine black"
        return "emerald green"
    if "fox" in race_low or "kitsune" in race_low:
        return "golden-blonde"
    elif "wolf" in race_low:
        return "ash-gray"
    elif "cat" in race_low:
        return "warm brown"
    elif "rabbit" in race_low or "bunny" in race_low:
        return "snow-white"
    elif "bird" in race_low or "avian" in race_low:
        return "midnight raven"
    return "natural"

SPECIES_TEMPLATES = {
    "cat": {
        "eyes": ["Emerald Green", "Slit Amber", "Sapphire Blue", "Glistening Topaz", "Jade Green", "Dichroic Violet-Gold", "Amethyst"],
        "hair": ["Sleek Glossy Black", "Soft Cream Blonde", "Silver-Gray", "Warm Auburn", "Silky Charcoal", "Pastel Calico", "Pastel Sakura-Pink", "Azure Blue", "Lavender Silk"],
        "coats": [
            "Silky Midnight-Black Fur", "Snow-White Fur", "Calico Pattern Fur", "Golden Tabby Fur",
            "Silver-Gray Mackerel Fur", "Smoky Charcoal Fur", "Cream Pointed Fur",
            "Pastel Sakura-Pink Fur", "Vibrant Azure-Blue Fur", "Soft Mint-Green Fur",
            "Silky Lavender Fur", "Midnight-Violet Fur"
        ],
        "beastfolk_features": ["Feline Tail & Pointed Cat Ears", "Sleek Feline Tail & Twitching Ears", "Fluffy Plumed Tail & Cat Ears", "Long Slender Tail & Soft Pointed Ears"],
        "hybrid_features": [
            "Soft White Cat Ears & Matching Sleek White Tail",
            "Midnight-Black Cat Ears & Long Sleek Black Tail",
            "Golden Tabby Cat Ears & Matching Striped Feline Tail",
            "Calico-Spotted Cat Ears & Matching Calico Tail",
            "Silver-Gray Cat Ears & Slender Silver Tail",
            "Pastel Pink Cat Ears & Matching Soft Pink Tail",
            "Pastel Blue Cat Ears & Matching Sleek Blue Tail",
            "Lavender Cat Ears & Matching Fluffy Purple Tail"
        ],
        "mannerisms": [
            "Swishes tail subtly when amused and speaks in a calm, melodic tone",
            "Tilts head with one ear swiveling towards subtle sounds",
            "Gives a soft, barely audible purr when completely relaxed",
            "Gracefully stretches with a delicate feline yawn",
            "Kneads fingers gently against their palm when content"
        ]
    },
    "wolf": {
        "eyes": ["Piercing Amber", "Ice Blue", "Silver-Gray", "Golden-Yellow", "Fierce Hazel", "Deep Slate Blue"],
        "hair": ["Wild Ash-Gray", "Coarse Midnight Black", "Silver-White Shag", "Dark Slate", "Tawny Brown", "Frost Silver", "Midnight Cobalt", "Ghostly Lilac"],
        "coats": [
            "Dense Ash-Gray Fur", "Midnight Timber Black Fur", "Frost White Fur",
            "Grizzled Silver-Black Fur", "Warm Tawny Wolf Fur",
            "Midnight Cobalt-Blue Fur", "Frost-Cyan Fur", "Ghostly Lilac Fur", "Deep Indigo Timber Fur"
        ],
        "beastfolk_features": ["Wolf Tail & Pointed Ears", "Thick Bushy Wolf Tail & Alert Ears", "Sturdy Timber Wolf Tail & Broad Ears"],
        "hybrid_features": [
            "Ash-Gray Wolf Ears & Matching Bushy Gray Tail",
            "Midnight-Black Wolf Ears & Matching Sleek Black Timber Tail",
            "Frost-White Wolf Ears & Matching Thick White Tail",
            "Silver-Grizzled Wolf Ears & Matching Sturdy Silver Tail",
            "Warm Tawny Wolf Ears & Matching Tawny Tail",
            "Cobalt-Blue Wolf Ears & Matching Bushy Blue Tail",
            "Ghostly Lilac Wolf Ears & Matching Fluffy Lilac Tail"
        ],
        "mannerisms": [
            "Taps finger thoughtfully on chin and tilts head with perked ears when listening",
            "Subtly sniffs the air when assessing an unfamiliar room or mood",
            "Stands in a protective stance with their tail brushing against their leg",
            "Low rumble in their throat when sensing potential hostility",
            "Ears perk up sharply at sudden movements"
        ]
    },
    "fox": {
        "eyes": ["Bright Amber", "Glistening Emerald", "Amethyst Purple", "Warm Honey", "Ruby Red", "Sunburst Gold"],
        "hair": ["Flame Auburn", "Silky Snow White", "Golden Apricot", "Midnight with Silver Highlights", "Pastel Copper", "Rose-Gold", "Sky-Blue Silk", "Luminous Violet"],
        "coats": [
            "Vibrant Rust-Red Fur", "Snow-White Kitsune Fur", "Silver-Tipped Black Fur",
            "Golden-Cream Fur", "Pastel Rose-Gold Fur",
            "Ethereal Sky-Blue Fox Fur", "Pastel Sakura-Pink Fur", "Luminous Violet Fox Fur",
            "Jade-Green Kitsune Fur", "Frost-Cyan Fox Fur"
        ],
        "beastfolk_features": ["Fluffy Fox Tail & Twitching Ears", "Bushy Plumed Fox Tail & Alert Ears", "Tapered Brush Fox Tail & Soft Ears"],
        "hybrid_features": [
            "Snow-White Fox Ears & Matching Bushy White Fox Tail",
            "Rust-Red Fox Ears & Matching Fluffy Rust-Red Tail with White Tip",
            "Golden Fox Ears & Matching Fluffy Golden Tail with White Tip",
            "Midnight-Black Fox Ears & Matching Silky Black Tail with Silver Tip",
            "Rose-Gold Fox Ears & Matching Bushy Rose-Gold Tail",
            "Sky-Blue Fox Ears & Matching Fluffy Blue Fox Tail",
            "Pastel Pink Fox Ears & Matching Soft Pink Tail"
        ],
        "mannerisms": [
            "Twitches ears when excited and curls fluffy tail playfully around their waist",
            "Playful flick of the tail accompanied by an inquisitive smirk",
            "Tilts head with one ear tilted down in mischievous amusement",
            "Hides the lower half of their face behind a sleeve when flustered",
            "Winks playfully while their tail swishes in rhythmic beats"
        ]
    },
    "rabbit": {
        "eyes": ["Ruby Red", "Warm Chestnut Brown", "Soft Pastel Pink", "Amethyst", "Sky Blue", "Glistening Berry"],
        "hair": ["Silky Platinum Blonde", "Soft Chestnut Brown", "Pastel Pink", "Snow White", "Honey Caramel", "Silver Fawn", "Sky-Blue Angora", "Mint-Green"],
        "coats": [
            "Velvety Snow-White Fur", "Soft Ash-Brown Fur", "Pastel Cream Fur",
            "Dutch Spotted Fur", "Warm Caramel Fur", "Silver Marten Fur",
            "Pastel Cotton-Candy Pink Fur", "Sky-Blue Angora Fur", "Mint-Green Fur", "Lavender Lop Fur"
        ],
        "beastfolk_features": ["Long Bunny Ears & Soft Puff Tail", "Velvety Lop Ears & Fluffy Cotton Tail", "Upright Rabbit Ears & Soft Tufted Tail"],
        "hybrid_features": [
            "Snow-White Bunny Ears & Matching Fluffy White Cotton Tail",
            "Ash-Brown Rabbit Ears & Matching Soft Brown Puff Tail",
            "Pastel Cream Bunny Ears & Matching Fluffy Cream Tail",
            "Spotted Black-and-White Rabbit Ears & Matching Spotted Puff Tail",
            "Pastel Pink Bunny Ears & Matching Soft Pink Tail",
            "Sky-Blue Bunny Ears & Matching Fluffy Blue Cotton Tail",
            "Mint-Green Bunny Ears & Matching Mint Puff Tail"
        ],
        "mannerisms": [
            "Rapidly twitches nose and perches alert ears upright when curious",
            "Thumps foot lightly against the ground when flustered or impatient",
            "Gently grooms ear tips with both hands when nervous",
            "Takes small, cautious steps before relaxing into a cheerful smile",
            "Ears fold back bashfully when receiving unexpected compliments"
        ]
    },
    "bear": {
        "eyes": ["Deep Honey Brown", "Dark Amber", "Forest Hazel", "Warm Caramel", "Rich Molasses"],
        "hair": ["Thick Chestnut Waves", "Shaggy Charcoal Brown", "Frost Blonde", "Coarse Dark Chocolate", "Warm Umber", "Frost-Blue Shag"],
        "coats": [
            "Dense Cinnamon Brown Fur", "Deep Charcoal Grizzly Fur", "Polar White Fur",
            "Warm Golden-Brown Fur", "Dark Chocolate Fur",
            "Glacial Frost-Blue Fur", "Mossy Forest-Green Fur", "Twilight Violet Fur"
        ],
        "beastfolk_features": ["Rounded Bear Ears & Stubby Bear Tail", "Broad Furry Ears & Short Fuzzy Tail", "Sturdy Bear Ears & Thick Short Tail"],
        "hybrid_features": [
            "Cinnamon-Brown Bear Ears & Matching Short Fuzzy Brown Tail",
            "Charcoal Grizzly Ears & Matching Short Charcoal Tail",
            "Polar-White Bear Ears & Matching Stubby White Tail",
            "Golden-Brown Bear Ears & Matching Short Golden Tail",
            "Dark Chocolate Bear Ears & Matching Fuzzy Dark Brown Tail",
            "Frost-Blue Bear Ears & Matching Short Blue Tail",
            "Forest-Green Bear Ears & Matching Short Green Tail"
        ],
        "mannerisms": [
            "Rests heavy hands comfortably on their waist while ears twitch lazily",
            "Gives an easygoing deep rumble in their chest when pleased",
            "Rubs the back of their neck with broad, unhurried movements",
            "Chuckles with a hearty, grounding warmth that eases tension",
            "Leans against nearby furniture with relaxed, immovable presence"
        ]
    },
    "tiger": {
        "eyes": ["Burning Copper", "Fierce Amber-Gold", "Jade Green", "Luminous Topaz", "Deep Smoldering Bronze", "Ice Blue"],
        "hair": ["Wild Black-Striped Orange", "Flame Auburn with Dark Streaks", "Pure Snow-White with Slate Tips", "Coarse Golden-Amber", "Raven Black", "Ice-Blue Striped Mane"],
        "coats": [
            "Flame-Orange Fur with Black Stripes", "Snow-White Fur with Charcoal Stripes",
            "Golden Tabby Striped Fur", "Midnight Black with Shadow Stripes", "Amber-Ochre Striped Fur",
            "Ice-Blue Fur with Charcoal Stripes", "Amethyst-Violet Striped Fur", "Jade-Green Striped Fur"
        ],
        "beastfolk_features": ["Rounded Tiger Ears & Powerful Ringed Tail", "Ringed Tiger Tail & Twitching Ears", "Broad Tiger Ears & Sleek Ringed Tail"],
        "hybrid_features": [
            "Flame-Orange Striped Tiger Ears & Matching Ringed Tiger Tail",
            "Snow-White Striped Tiger Ears & Matching White-and-Charcoal Ringed Tail",
            "Golden Striped Tiger Ears & Matching Ringed Golden Tail",
            "Midnight-Black Shadow-Striped Tiger Ears & Matching Sleek Striped Tail",
            "Amber-Ochre Striped Tiger Ears & Matching Ringed Amber Tail",
            "Ice-Blue Striped Tiger Ears & Matching Ringed Blue Tail",
            "Violet Striped Tiger Ears & Matching Ringed Purple Tail"
        ],
        "mannerisms": [
            "Slowly swishes heavy striped tail in rhythmic concentration",
            "Gives a low, resonant chuff of greeting or quiet approval",
            "Flexes fingers rhythmically with focused feline intensity",
            "Glares with an unblinking, predatory golden stare before answering",
            "Rolls shoulders smoothly with feline grace when preparing for action"
        ]
    },
    "lion": {
        "eyes": ["Rich Golden-Amber", "Sunburst Topaz", "Tawny Hazel", "Warm Copper", "Luminous Honey"],
        "hair": ["Thick Voluminous Golden Mane", "Sun-Bleached Tawny Waves", "Coarse Sandy Blonde", "Rich Golden Amber Locks", "Tawny Caramel", "Radiant Crimson Mane"],
        "coats": [
            "Sun-Drenched Golden Fur", "Sandy Tawny Coat", "Desert Cream Fur",
            "Pale Ash-Gold Fur", "Warm Tawny Ochre Fur",
            "Radiant Sunburst-Red Fur", "Sapphire-Blue Lion Fur", "Ember-Gold Fur"
        ],
        "beastfolk_features": ["Rounded Lion Ears & Majestic Tufted Tail", "Proud Lion Ears & Fluffy Tufted Tail", "Alert Lion Ears & Long Tufted Tail"],
        "hybrid_features": [
            "Golden Lion Ears & Matching Tufted Golden Lion Tail",
            "Tawny Sand Lion Ears & Matching Tufted Tawny Tail",
            "Desert Cream Lion Ears & Matching Tufted Cream Tail",
            "Sun-Bleached Blonde Lion Ears & Matching Tufted Blonde Tail",
            "Rich Amber Lion Ears & Matching Tufted Amber Tail",
            "Sapphire-Blue Lion Ears & Matching Tufted Blue Tail",
            "Sunburst-Red Lion Ears & Matching Tufted Red Tail"
        ],
        "mannerisms": [
            "Proudly tosses hair and swishes tufted tail with regal composure",
            "Stretches languidly with a relaxed feline yawn before focusing",
            "Raises chin with calm dignity while ears flick attentively",
            "Rumbles a deep, confident chuckle in their chest",
            "Basks comfortably in warm sunlight or spotlight without hesitation"
        ]
    },
    "cheetah": {
        "eyes": ["Glistening Amber", "Sleek Honey-Gold", "Tear-Tracked Ochre", "Bright Topaz", "Clear Hazel"],
        "hair": ["Sleek Spotted Ochre", "Aerodynamic Tawny Mane", "Dust-Blonde with Dark Tips", "Sleek Amber Locks", "Tawny Streaked Blonde", "Azure-Streaked Mane"],
        "coats": [
            "Tawny Fur with Crisp Black Spots", "Golden Coat with Distinct Spot Patterns",
            "Pale Cream with Cheetah Spots", "Warm Amber Spotted Fur", "Sand-Gold Spotted Fur",
            "Azure-Blue with Obsidian Spots", "Pastel Rose with Cheetah Spots"
        ],
        "beastfolk_features": ["Small Rounded Cheetah Ears & Long Sleek Balancing Tail", "Facial Tear-Line Contours & Slender Rudder Tail", "Aerodynamic Cheetah Ears & Long Counter-Balancing Tail"],
        "hybrid_features": [
            "Spotted Tawny Cheetah Ears & Matching Long Spotted Balancing Tail",
            "Pale Cream Spotted Cheetah Ears & Matching Spotted Tail",
            "Golden Spotted Cheetah Ears & Matching Sleek Spotted Cheetah Tail",
            "Sand-Gold Spotted Cheetah Ears & Matching Long Spotted Balancing Tail",
            "Azure-Blue Spotted Cheetah Ears & Matching Long Blue Balancing Tail",
            "Pastel Rose Spotted Cheetah Ears & Matching Spotted Tail"
        ],
        "mannerisms": [
            "Paces with light-footed, restless athletic energy",
            "Flicks sleek balancing tail rapidly while scanning their surroundings",
            "Twitches spotted ears at the faintest sound with pinpoint accuracy",
            "Taps foot with lightning-fast impatience when forced to wait",
            "Darts a quick, razor-sharp glance across the room before speaking"
        ]
    },
    "fennec": {
        "eyes": ["Large Bright Amber", "Luminous Desert Topaz", "Warm Sand Hazel", "Inquisitive Obsidian", "Golden-Ochre"],
        "hair": ["Soft Pale Sand Blonde", "Creamy Fawn", "Silky Desert Peach", "Fluffy Pale Apricot", "Fine Champagne Blonde", "Sky-Blue Silk"],
        "coats": [
            "Pale Sandy Cream Fur", "Soft Fawn Fur", "Silky Pale Apricot Fur",
            "Desert Dune Cream Fur", "Warm Sand-Gold Fur",
            "Pastel Peach-Blush Fur", "Sky-Blue Desert Fur", "Soft Lilac Fur"
        ],
        "beastfolk_features": ["Enormous Alert Fennec Ears & Bushy Feathered Tail", "Oversized Fluffy Fennec Ears & Soft Bushy Tail", "Large Radiating Fennec Ears & Slender Brush Tail"],
        "hybrid_features": [
            "Oversized Sandy-Cream Fennec Ears & Matching Bushy Sandy-Cream Tail",
            "Large Pale Fawn Fennec Ears & Matching Fluffy Fawn Tail",
            "Feathered Apricot Fennec Ears & Matching Bushy Apricot Tail",
            "Soft Dune-Cream Fennec Ears & Matching Bushy Cream Tail",
            "Sky-Blue Fennec Ears & Matching Bushy Blue Tail",
            "Lilac Fennec Ears & Matching Bushy Lilac Tail"
        ],
        "mannerisms": [
            "Large ears pivot independently to catch distant murmurs across the room",
            "Fidgets eagerly with a rapid, fluttering tail wag",
            "Hides shyly behind oversized fluffy ears when complimented",
            "Tilts head with wide, intensely curious eyes at every new detail",
            "Bounces on their toes with bubbly enthusiasm when excited"
        ]
    },
    "mouse": {
        "eyes": ["Large Glossy Onyx", "Bright Ruby", "Bead-Like Obsidian", "Warm Chestnut", "Deep Currant", "Glittering Dark Hazel"],
        "hair": ["Silky Ash Brown", "Slate Gray Bob", "Fine Chestnut Locks", "Soft Cocoa Brown", "Dusty Gray-Blonde", "Powder-Blue Silk"],
        "coats": [
            "Soft Ash-Gray Fur", "Silky Chestnut-Brown Fur", "Warm Mouse-Brown Fur",
            "Slate-Blue Fur", "Dusty Cocoa Fur",
            "Powder-Blue Fur", "Pastel Rose-Pink Fur", "Lavender-Gray Fur"
        ],
        "beastfolk_features": ["Round Mouse Ears & Slender Whip Tail", "Large Rounded Ears & Whiskered Cheeks", "Delicate Cupped Mouse Ears & Long Flexible Tail"],
        "hybrid_features": [
            "Soft Ash-Gray Mouse Ears & Matching Slender Gray-Pink Tail",
            "Chestnut-Brown Mouse Ears & Matching Slender Brown Tail",
            "Slate-Gray Mouse Ears & Matching Long Flexible Slate Tail",
            "Warm Cocoa Mouse Ears & Matching Slender Pinkish-Brown Tail",
            "Powder-Blue Mouse Ears & Matching Slender Blue Tail",
            "Rose-Pink Mouse Ears & Matching Slender Pink Tail"
        ],
        "mannerisms": [
            "Nose twitches in quick, inquisitive rhythm when inspecting something new",
            "Tucks sleek tail close to their side with a cautious startle",
            "Darts skittish, observant glances around before speaking in a soft voice",
            "Rapidly smooths hair and ears with small, delicate hand motions",
            "Nibbles thoughtfully on snacks or pencil tips during deep thought"
        ]
    },
    "reptile": {
        "eyes": ["Golden Slit Pupils", "Emerald Green Slit", "Amber-Ochre Slit", "Ruby Red Slit", "Glistening Citrine", "Luminous Topaz", "Copper Slit", "Jade Green"],
        "hair": ["Silky Emerald Green", "Sleek Glossy Obsidian", "Glossy Jade Waves", "Forest Green Locks", "Midnight Slate", "Ash Silver", "Dusky Olive"],
        "coats": [
            "Shiny Smooth Emerald Scales", "Gecko-Like Pale Mint Scales", "Shiny Smooth Jade Scales",
            "Iridescent Shimmering Blue Scales", "Smooth Sleek Obsidian Scales", "Dusky Olive Matte Scales",
            "Pearlescent Ivory Scales", "Vibrant Flame-Red Scales", "Metallic Bronze Scales",
            "Sunburst Gold Scales", "Mottled Forest Green Scales"
        ],
        "scales": [
            "Shiny Smooth Emerald Scales", "Gecko-Like Pale Mint Scales", "Shiny Smooth Jade Scales",
            "Iridescent Shimmering Blue Scales", "Smooth Sleek Obsidian Scales", "Dusky Olive Matte Scales",
            "Pearlescent Ivory Scales", "Vibrant Flame-Red Scales", "Metallic Bronze Scales",
            "Sunburst Gold Scales", "Mottled Forest Green Scales"
        ],
        "beastfolk_features": [
            "Reptilian Horns & Sleek Scaled Tail",
            "Tapered Scaled Tail & Slit-Pupil Eyes",
            "Ridge-Crested Scaled Tail & Sleek Horns",
            "Flexible Scaled Tail & Smooth Horn Crests",
            "Slender Reptilian Tail & Scaled Cheeks"
        ],
        "hybrid_features": [
            "Emerald Horn Crests & Matching Sleek Emerald Scaled Tail",
            "Shiny Blue Horns & Matching Iridescent Scaled Tail",
            "Flame-Red Hornlets & Matching Scaled Flame Tail",
            "Gecko-Like Horn Buds & Matching Soft Pale Mint Tail",
            "Obsidian Horns & Matching Sleek Black Scaled Tail",
            "Sunburst Gold Horn Crests & Matching Gold Scaled Tail"
        ],
        "mannerisms": [
            "Blinks slowly with horizontal nictitating membrane and tilts head in calm calculation",
            "Swishes sleek scaled tail in measured, serpentine rhythm when pondering",
            "Basks contentedly in sunny or warm spots, letting out a relaxed sigh",
            "Slowly curls scaled tail around ankles or chair leg while observing silently",
            "Flicks tongue subtly when testing the atmosphere or scenting tension in the air",
            "Tilts head with quiet, unblinking focus before offering a deliberate response"
        ]
    },
    "dragon": {
        "eyes": ["Smoldering Ruby Red", "Burning Molten Gold", "Luminous Sapphire Blue", "Draconic Topaz", "Glowing Violet", "Prismatic Amethyst", "Fierce Smoldering Copper"],
        "hair": ["Fiery Crimson Mane", "Shimmering Platinum Silver", "Smoldering Ember-Auburn", "Sleek Midnight Black", "Royal Azure Blue", "Burnished Gold Locks"],
        "coats": [
            "Flame-Red Dragon Scales", "Shiny Blue Cerulean Scales", "Glistening Molten-Gold Scales",
            "Shiny Smooth Diamond-Bright Scales", "Iridescent Prismatic Scales", "Smoldering Obsidian Scales",
            "Deep Crimson Armored Scales", "Radiant Frost-Silver Scales", "Lustrous Emerald Drake Scales",
            "Midnight Abyssal Scales"
        ],
        "scales": [
            "Flame-Red Dragon Scales", "Shiny Blue Cerulean Scales", "Glistening Molten-Gold Scales",
            "Shiny Smooth Diamond-Bright Scales", "Iridescent Prismatic Scales", "Smoldering Obsidian Scales",
            "Deep Crimson Armored Scales", "Radiant Frost-Silver Scales", "Lustrous Emerald Drake Scales",
            "Midnight Abyssal Scales"
        ],
        "beastfolk_features": [
            "Draconic Horns & Heavy Spined Dragon Tail",
            "Curved Dragon Horns & Scaled Drake Tail with Back Ridge",
            "Majestic Dragon Horns & Powerful Scaled Tail",
            "Swept-Back Draconic Horns & Sleek Spaded Dragon Tail"
        ],
        "hybrid_features": [
            "Flame-Red Dragon Horns & Matching Spined Flame Tail",
            "Shiny Blue Dragon Horns & Matching Sleek Cerulean Tail",
            "Platinum Horns & Matching Radiant Silver Dragon Tail",
            "Smoldering Obsidian Horns & Matching Dark Spined Tail",
            "Molten-Gold Horns & Matching Heavy Gilded Dragon Tail"
        ],
        "mannerisms": [
            "Exhales a warm puff of breath with a proud, resonant rumble in chest",
            "Slowly curves heavy spined tail with commanding, regal poise",
            "Crosses arms and tilts head back with an aura of unshakeable draconic pride",
            "Eyes flare with a faint inner ember when challenged or deeply amused",
            "Restlessly adjusts posture with a sharp, disciplined flick of their spined tail"
        ]
    },
    "snake": {
        "eyes": ["Hypnotic Golden Slit", "Ruby Viper Slit", "Luminous Amber Slit", "Emerald Venom Slit", "Deep Amethyst Slit", "Topaz Slit Pupils"],
        "hair": ["Long Sleek Serpentine Black", "Glossy Emerald Waves", "Silky Platinum", "Wine Red Silk Locks", "Iridescent Violet Waves"],
        "coats": [
            "Shiny Smooth Coral-Red Scales", "Gecko-Like Soft Scaled Pattern", "Iridescent Diamondback Scales",
            "Glossy Viper-Green Scales", "Shiny Royal-Blue Scales", "Velvety Matte-Black Scales",
            "Sunburst Yellow-Banded Scales", "Pearlescent Opal Scales"
        ],
        "scales": [
            "Shiny Smooth Coral-Red Scales", "Gecko-Like Soft Scaled Pattern", "Iridescent Diamondback Scales",
            "Glossy Viper-Green Scales", "Shiny Royal-Blue Scales", "Velvety Matte-Black Scales",
            "Sunburst Yellow-Banded Scales", "Pearlescent Opal Scales"
        ],
        "beastfolk_features": [
            "Long Serpentine Tail & Scaled Jawline Accents",
            "Prehensile Scaled Tail & Slit-Pupil Viper Eyes",
            "Diamond-Patterned Scaled Tail & Hood Crest",
            "Sleek Scaled Tail & Subtle Fang Dimples"
        ],
        "hybrid_features": [
            "Glossy Emerald Scale Accents & Matching Long Emerald Snake Tail",
            "Coral-Red Scale Crest & Matching Banded Red Serpent Tail",
            "Shiny Blue Scale Accents & Matching Sleek Blue Serpent Tail",
            "Matte-Black Scale Accents & Matching Sleek Obsidian Snake Tail",
            "Opal Iridescent Accents & Matching Pearlescent Serpent Tail"
        ],
        "mannerisms": [
            "Sways subtly in place with mesmerizing, fluid serpentine poise",
            "Curls prehensile tail gracefully around nearby objects when speaking softly",
            "Subtly tilts chin down with a slow, hypnotic gaze from slit pupils",
            "Speaks with a soft, melodic drawl that lingers delicately on sibilants",
            "Draws shoulders close and rests chin on hand with quiet, predator-like calm"
        ]
    },
    "bird": {
        "eyes": [
            "Golden Amber", "Sharp Topaz", "Piercing Ruby", "Brilliant Sapphire", "Obsidian Bead"
        ],
        "hair": [
            "Feathered Midnight Black", "Silky Snow White", "Glossy Raven-Blue", "Warm Tawny Brown", "Silver-Gray Feathered Crest"
        ],
        "coats": [
            "Glossy Midnight Raven Feathers", "Snow-White Swan Feathers", "Tawny Hawk Feathers", "Iridescent Blue Feathers", "Warm Golden-Brown Feathers", "Mottled Falcon Feathers"
        ],
        "beastfolk_features": [
            "Feathered Avian Wings & Plumage Accents", "Large Sleek Feathered Wings & Fan-Tailed Plumage", "Swept-Back Feathered Wings & Sharp Taloned Accents", "Soft Feather Crest & Matching Plumaged Tail"
        ],
        "hybrid_features": [
            "Midnight Feather Crests & Matching Raven-Wing Feathered Tail",
            "Snow-White Wing Accents & Matching Sleek White Plumage Tail",
            "Golden-Hawk Feather Crests & Matching Tapered Feather Tail",
            "Tawny Falcon Wing Accents & Matching Feathered Plumage Tail"
        ],
        "mannerisms": [
            "Tilts head with rapid, bird-like precision to inspect their surroundings",
            "Subtly flutters feathered wingtips when startled or pleased",
            "Perches lightly on the balls of their feet, ready to take flight",
            "Smoothes down loose plumage with quick, meticulous hand gestures",
            "Emits a soft, melodious trill under their breath when content"
        ]
    }
}

DIVERSE_FEMALE_HAIR_STYLES = [
    "ponytail with side bangs", "twin braids", "messy bun", "loose wavy locks", 
    "curtain bangs with soft waves", "bob cut", "braided side plait", "half-up half-down", 
    "straight with blunt fringe", "layered shag", "low twin tails", "short pixie with feathered bangs",
    "wavy tresses with a headband", "asymmetrical bob", "high ponytail with ribbons"
]

DIVERSE_MALE_HAIR_STYLES = [
    "short textured crop", "undercut with swept-back top", "tousled messy fringe", 
    "side-parted clean cut", "wild layered shag", "fade with spiky top", "middle-part curtains", "neat crew cut",
    "shaggy mop with stray bangs", "short slicked back"
]

DIVERSE_HAIR_LENGTHS_FEMALE = [
    "shoulder-length", "long", "waist-length", "short", "medium-long", "chin-length"
]

DIVERSE_HAIR_LENGTHS_MALE = [
    "short", "cropped", "medium-length tousled", "ear-length", "short taper"
]

def is_half_beast_race(race_str: str) -> bool:
    """Checks if a race string designates a half-beast / hybrid / beastkin demi-human."""
    r = str(race_str or "").lower().replace("-", "_")
    return any(k in r for k in ("half_beast", "halfbeast", "hybrid", "demi_human", "beastkin", "half_breed"))

def is_beast_race(race_str: str) -> bool:
    """Checks if a race string designates a beastfolk, anthro, half-beast, or scaly/feathered creature."""
    r = str(race_str or "").lower().replace("-", "_")
    if is_half_beast_race(r):
        return True
    return any(k in r for k in (
        "beastfolk", "beast", "anthro", "furry", "fox", "cat", "wolf", "neko", "kitsune",
        "rabbit", "bunny", "tiger", "lion", "bear", "mouse", "reptile", "dragon",
        "snake", "bird", "avian", "lizard", "cheetah", "fennec"
    )) or is_scaly_race(r)

BEASTFOLK_COLOR_PATTERNS = [
    (r'\bwhite[\s\-_]tipped\b', 'plumed'),
    (r'\bcalico\b', 'plumed'),
    (r'\bspotted\b', 'tufted'),
    (r'\b(sleek\s+)?black\b', 'sleek'),
    (r'\b(thick\s+)?gray\b', 'thick'),
    (r'\b(thick\s+)?grey\b', 'thick'),
    (r'\bwhite\b', 'soft'),
    (r'\bgolden[\s\-_]cream\b', 'tapered'),
    (r'\bgolden\b', 'proud'),
    (r'\bcream\b', 'soft'),
    (r'\bbrown\b', 'dense'),
    (r'\bash[\s\-_]brown\b', 'velvety'),
    (r'\brust[\s\-_]red\b', 'tapered'),
    (r'\btawny\b', 'sturdy'),
    (r'\bcharcoal\b', 'heavy'),
    (r'\bsilver\b', 'sleek'),
    (r'\bpinkish\b', 'flexible'),
    (r'\bpink\b', 'soft'),
    (r'\bamber\b', 'warm'),
]

def sanitize_beastfolk_features(text: str) -> str:
    """Removes fur/coat color descriptors from beastfolk feature descriptions to prevent
    contradictions with the character's body coat color."""
    if not text or not isinstance(text, str):
        return ""
    import re
    res = text
    for pat, rep in BEASTFOLK_COLOR_PATTERNS:
        res = re.sub(pat, rep, res, flags=re.IGNORECASE)
    res = re.sub(r'\s+', ' ', res)
    res = re.sub(r'\s*&\s*', ' & ', res)
    res = re.sub(r'&\s*$', '', res)
    res = re.sub(r'^\s*&', '', res)
    words = res.strip().split()
    clean_words = []
    for w in words:
        if w == '&':
            clean_words.append('&')
        elif '-' in w:
            clean_words.append('-'.join(part.capitalize() for part in w.split('-')))
        else:
            clean_words.append(w.capitalize())
    return " ".join(clean_words).strip()

CULTURE_TO_GROUP = {
    # Scandinavian / Nordic
    "swedish": "scandinavian", "norwegian": "scandinavian", "danish": "scandinavian", "icelandic": "scandinavian",
    # Slavic / Eastern European
    "slavic": "slavic", "polish": "slavic", "russian": "slavic", "ukrainian": "slavic",
    # Western European / Celtic / Germanic
    "english": "celtic_germanic", "german": "celtic_germanic", "dutch": "celtic_germanic",
    "irish": "celtic_germanic", "scottish": "celtic_germanic", "french": "celtic_germanic",
    # Mediterranean / Southern European
    "italian": "mediterranean", "greek": "mediterranean", "hispanic": "mediterranean", "portuguese": "mediterranean",
    # East Asian
    "japanese": "east_asian", "chinese": "east_asian", "korean": "east_asian",
    # Southeast Asian
    "malay": "southeast_asian", "vietnamese": "southeast_asian",
    # South Asian
    "indian": "south_asian",
    # Middle Eastern
    "arabic": "middle_eastern", "persian": "middle_eastern", "turkish": "middle_eastern",
    # African
    "african": "african",
}

CULTURE_SKIN_TONE_POOLS = {
    "scandinavian": [
        ("porcelain white", 35), ("pale white", 25), ("silky ivory", 20),
        ("fair peach", 15), ("rosy pale", 5)
    ],
    "slavic": [
        ("pale alabaster", 30), ("porcelain white", 30), ("cool ivory", 25),
        ("fair peach", 15)
    ],
    "celtic_germanic": [
        ("fair ivory", 35), ("pale peach", 25), ("rosy fair", 20),
        ("light beige", 15), ("sun-freckled fair", 5)
    ],
    "mediterranean": [
        ("warm olive", 35), ("sun-kissed bronze", 25), ("golden honey", 20),
        ("warm tan", 15), ("light bronze", 5)
    ],
    "east_asian": [
        ("porcelain ivory", 35), ("fair alabaster", 25), ("warm peach ivory", 20),
        ("golden cream", 15), ("warm bisque", 5)
    ],
    "southeast_asian": [
        ("warm golden tan", 35), ("amber bronze", 25), ("sun-kissed olive", 25),
        ("warm honey brown", 15)
    ],
    "south_asian": [
        ("warm caramel", 30), ("golden brown", 25), ("deep bronze", 20),
        ("rich chestnut brown", 15), ("dusky amber", 10)
    ],
    "middle_eastern": [
        ("warm olive", 35), ("golden almond", 30), ("sun-kissed bronze", 20),
        ("light honey tan", 15)
    ],
    "african": [
        ("rich dark brown", 30), ("deep espresso", 25), ("warm mahogany", 20),
        ("dark cocoa", 15), ("radiant dark bronze", 10)
    ],
}

GLOBAL_SKIN_TONE_POOL = [
    ("porcelain white", 10),
    ("fair ivory", 15),
    ("pale peach", 10),
    ("warm peach ivory", 10),
    ("warm olive", 15),
    ("golden honey", 10),
    ("warm golden tan", 10),
    ("warm caramel", 10),
    ("rich dark brown", 10),
]

HUMANOID_RACE_SKIN_TONES = {
    "dark_elf": [
        ("ashen charcoal", 30), ("obsidian dusk", 25), ("slate gray", 20),
        ("dusky violet-gray", 15), ("pale moon-silver", 10)
    ],
    "drow": [
        ("ashen charcoal", 30), ("obsidian dusk", 25), ("slate gray", 20),
        ("dusky violet-gray", 15), ("pale moon-silver", 10)
    ],
    "elf": [
        ("porcelain white", 30), ("pale ivory", 25), ("silky alabaster", 20),
        ("fair peach", 15), ("golden sun-kissed", 10)
    ],
    "dwarf": [
        ("tanned bronze", 30), ("ruddy weather-beaten", 25), ("sun-baked tan", 20),
        ("warm golden brown", 15), ("pale subterranean ivory", 10)
    ],
    "orc": [
        ("olive-green", 35), ("dusty ash-gray", 25), ("dusky bronze", 20),
        ("slate green-gray", 20)
    ],
    "goblin": [
        ("mossy green", 40), ("pale olive", 30), ("yellow-ochre", 15),
        ("dusky brown", 15)
    ],
    "halfling": [
        ("warm peach", 35), ("sun-kissed tan", 30), ("rosy fair", 20),
        ("golden honey", 15)
    ],
    "gnome": [
        ("warm peach", 30), ("rosy fair", 25), ("pale ivory", 25),
        ("sun-kissed tan", 20)
    ],
}

def infer_humanoid_skin_color(race: str, name: str = "", seed: str = "") -> str:
    """Infers human and fantasy humanoid skin tone using cultural name origin or race weighting.
    - Fantasy races (Elf, Dwarf, Drow, Orc, etc.) roll from HUMANOID_RACE_SKIN_TONES.
    - Humans and Half-Beasts roll: ~70% primary cultural palette based on name + ~30% global/mixed-heritage variance.
    - Unmatched names roll from GLOBAL_SKIN_TONE_POOL.
    - Uses deterministic pseudo-random hashing if seed or name is provided.
    """
    import hashlib, random
    clean_race = str(race or "").strip().lower().replace("-", "_")

    # 1. Fantasy humanoid races (sorted longest first to match dark_elf before elf)
    for f_race, pool in sorted(HUMANOID_RACE_SKIN_TONES.items(), key=lambda x: len(x[0]), reverse=True):
        if f_race in clean_race:
            tones, weights = zip(*pool)
            if seed:
                h = int(hashlib.md5(f"{seed}_{f_race}_skin".encode("utf-8")).hexdigest(), 16)
                rng = random.Random(h)
                return rng.choices(tones, weights=weights, k=1)[0]
            return random.choices(tones, weights=weights, k=1)[0]

    # 2. Culture lookup from name (for humans and half-beasts)
    cult_group = None
    if name:
        try:
            import namegen
            parts = name.strip().split()
            first = parts[0].lower() if parts else ""
            last = parts[-1].lower() if len(parts) > 1 else ""
            raw_cult = namegen._SURNAME_TO_CULTURE.get(last) or namegen._FIRST_NAME_TO_CULTURE.get(first) or ""
            cult_group = CULTURE_TO_GROUP.get(raw_cult)
        except Exception:
            cult_group = None

    seed_key = f"{name}_{seed}_{race}_skin"
    h = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) if (name or seed) else None
    rng = random.Random(h) if h is not None else random

    # ~70% primary cultural palette, ~30% global / mixed-heritage variance
    use_global = rng.random() < 0.30 or not cult_group or cult_group not in CULTURE_SKIN_TONE_POOLS

    if use_global:
        tones, weights = zip(*GLOBAL_SKIN_TONE_POOL)
        return rng.choices(tones, weights=weights, k=1)[0]
    else:
        pool = CULTURE_SKIN_TONE_POOLS[cult_group]
        tones, weights = zip(*pool)
        return rng.choices(tones, weights=weights, k=1)[0]

def get_species_key_from_race(race_str: str, desc: str = "", seed: str = "") -> str | None:
    """Extracts the canonical animal/beastfolk sub-species key (cat, wolf, dragon, reptile, etc.) from race and description."""
    import re
    clean_race = str(race_str or "").strip().lower().replace("-", "_")
    
    # Priority 1: Explicit sub-race tag (e.g. "beastfolk:cat", "half_beast:fox")
    if ":" in clean_race:
        sub = clean_race.split(":", 1)[1].strip()
        if sub in ("dragon", "dragonkin", "draconoid", "draconic", "drake", "wyvern", "wyrm"): return "dragon"
        if sub in ("snake", "serpent", "serpentine", "viper", "cobra", "naga"): return "snake"
        if sub in ("reptile", "reptilian", "lizard", "gecko", "chameleon", "alligator", "crocodile", "gator", "crocodilian"): return "reptile"
        if sub in ("tiger", "tigress"): return "tiger"
        if sub in ("lion", "lioness"): return "lion"
        if sub in ("cheetah",): return "cheetah"
        if sub in ("fennec",): return "fennec"
        if sub in ("rabbit", "bunny"): return "rabbit"
        if sub in ("fox", "kitsune"): return "fox"
        if sub in ("wolf",): return "wolf"
        if sub in ("cat", "neko"): return "cat"
        if sub in ("mouse", "rat", "rodent"): return "mouse"
        if sub in ("bear", "ursine"): return "bear"
        if sub in ("bird", "avian", "raven", "crow", "hawk", "falcon", "eagle", "owl", "swan", "sparrow", "dove"): return "bird"
        if sub: return sub

    species_order = (
        ("dragon", ("dragon", "dragonkin", "draconoid", "draconic", "drake", "wyvern", "wyrm")),
        ("snake", ("snake", "serpent", "serpentine", "viper", "cobra", "naga")),
        ("reptile", ("reptile", "reptilian", "lizard", "gecko", "chameleon", "alligator", "crocodile", "gator", "crocodilian")),
        ("tiger", ("tiger", "tigress")),
        ("lion", ("lion", "lioness")),
        ("cheetah", ("cheetah",)),
        ("fennec", ("fennec",)),
        ("rabbit", ("rabbit", "bunny")),
        ("fox", ("fox", "kitsune")),
        ("wolf", ("wolf",)),
        ("cat", ("cat", "neko")),
        ("mouse", ("mouse", "rat", "rodent")),
        ("bear", ("bear", "ursine")),
        ("bird", ("bird", "avian", "raven", "crow", "hawk", "falcon", "eagle", "owl", "swan", "sparrow", "dove")),
    )

    # Priority 2: Race string matching with word boundaries
    search_race = clean_race.replace("_", " ")
    for canonical, synonyms in species_order:
        for syn in synonyms:
            if re.search(rf"\b{re.escape(syn)}\b", search_race):
                return canonical

    # Priority 3: Description matching with word boundaries
    clean_desc = str(desc or "").lower().replace("-", " ").replace("_", " ")
    for canonical, synonyms in species_order:
        for syn in synonyms:
            if re.search(rf"\b{re.escape(syn)}\b", clean_desc):
                return canonical

    text = f"{clean_race} {clean_desc}"

    # General animal families fallback
    from mechanics.social.races import resolve_animal_family_species, resolve_generic_beastfolk_species
    for fam in ("canine", "canid", "dog", "hound"):
        if fam in text:
            return resolve_animal_family_species("canine", seed=seed or text) or "wolf"
    for fam in ("feline", "felid"):
        if fam in text:
            return resolve_animal_family_species("feline", seed=seed or text) or "cat"
    for fam in ("reptilian", "scaly", "serpentine"):
        if fam in text:
            return resolve_animal_family_species("reptile", seed=seed or text) or "reptile"
    for fam in ("avian", "bird"):
        if fam in text:
            return "bird"

    # Generic beastfolk fallback if seed is provided
    if any(k in text for k in ("beastfolk", "half_beast", "halfbeast", "hybrid", "anthro", "demi_human", "beastkin")):
        return resolve_generic_beastfolk_species(seed=seed or text)

    return None

UNNATURAL_HAIR_KEYWORDS = {
    "blue", "green", "pink", "purple", "violet", "teal", "cyan", "magenta",
    "lavender", "lilac", "rose", "pastel", "neon", "emerald", "jade",
    "cerulean", "azure", "cobalt", "sapphire", "mint", "turquoise",
    "aquamarine", "periwinkle", "streaks", "highlights", "balayage", "tips"
}

def is_unnatural_hair_color(hair_color: str) -> bool:
    """Checks if a hair color contains unnatural/vibrant dye pigments or highlights."""
    if not hair_color:
        return False
    low = str(hair_color).lower()
    words = re.findall(r'[a-z]+', low)
    return any(w in UNNATURAL_HAIR_KEYWORDS for w in words)

CULTURE_NATURAL_HAIR_POOLS = {
    # East Asian (Japanese, Chinese, Korean)
    "east_asian": [
        ("silky jet-black", 40), ("soft raven-black", 30), ("deep espresso brown", 15),
        ("dark charcoal brown", 10), ("warm dark chestnut", 5)
    ],
    # South Asian (Indian)
    "south_asian": [
        ("lustrous blue-black", 40), ("deep onyx black", 35), ("dark espresso", 15),
        ("warm dark chocolate", 10)
    ],
    # Southeast Asian (Malay, Vietnamese)
    "southeast_asian": [
        ("silky midnight-black", 45), ("soft black", 30), ("dark chestnut brown", 15),
        ("warm mocha brown", 10)
    ],
    # African
    "african": [
        ("deep onyx black", 45), ("rich midnight-black", 30), ("dark espresso brown", 15),
        ("warm dark cocoa", 10)
    ],
    # Middle Eastern / West Asian (Arabic, Persian, Turkish)
    "middle_eastern": [
        ("glossy jet-black", 35), ("deep sable brown", 30), ("warm chestnut brown", 20),
        ("dark chocolate", 10), ("rich hazelnut brown", 5)
    ],
    # Mediterranean / Southern European (Italian, Greek, Hispanic, Portuguese)
    "mediterranean": [
        ("dark espresso brown", 30), ("warm chestnut brown", 25), ("glossy soft black", 20),
        ("golden amber brown", 15), ("rich chocolate brown", 10)
    ],
    # Celtic / Germanic / Western European (English, German, Dutch, Irish, Scottish, French)
    "celtic_germanic": [
        ("golden honey blonde", 20), ("rich chestnut brown", 20), ("dark chocolate brown", 15),
        ("fiery copper red", 15), ("warm auburn", 10), ("strawberry blonde", 10),
        ("dirty blonde", 10)
    ],
    # Scandinavian / Nordic (Swedish, Norwegian, Danish, Icelandic)
    "scandinavian": [
        ("platinum blonde", 30), ("Nordic pale blonde", 25), ("golden honey blonde", 20),
        ("light ash blonde", 15), ("strawberry blonde", 5), ("soft golden brown", 5)
    ],
    # Slavic / Eastern European (Slavic, Polish, Russian, Ukrainian)
    "slavic": [
        ("dark ash blonde", 25), ("cool light brown", 25), ("warm chestnut", 20),
        ("honey blonde", 15), ("soft raven-black", 10), ("strawberry blonde", 5)
    ],
}

HUMANOID_RACE_NATURAL_HAIR_POOLS = {
    # Dark Elves / Drow: Famously moon-silver and stark white, with slate and midnight darks
    "dark_elf": [
        ("pale moon-silver", 35), ("stark white", 30), ("ash-gray", 15),
        ("platinum white", 10), ("midnight slate", 10)
    ],
    "drow": [
        ("pale moon-silver", 35), ("stark white", 30), ("ash-gray", 15),
        ("platinum white", 10), ("midnight slate", 10)
    ],
    # Elves: Ethereal blondes, silvers, rich black, chestnut, and fiery autumn copper
    "elf": [
        ("golden honey blonde", 25), ("silvery platinum", 20), ("glossy raven-black", 20),
        ("fiery autumn copper", 15), ("rich chestnut brown", 10), ("flaxen pale blonde", 10)
    ],
    # Dwarves: Earthy, fiery, and dark tones
    "dwarf": [
        ("fiery copper red", 25), ("rich dark chocolate", 25), ("grizzled charcoal black", 20),
        ("warm chestnut auburn", 15), ("sandy blonde", 10), ("iron gray", 5)
    ],
    # Orcs: Coarse darks and earthy tones
    "orc": [
        ("coarse jet-black", 40), ("deep charcoal", 25), ("dark chocolate brown", 20),
        ("grizzled steel gray", 15)
    ],
    # Goblins: Dark earth tones
    "goblin": [
        ("sooty black", 35), ("muddy dark brown", 30), ("dark rust brown", 20),
        ("dusky ash", 15)
    ],
    # Halflings & Gnomes: Warm curls and bright tones
    "halfling": [
        ("warm chestnut curls", 30), ("golden honey blonde", 25), ("rich caramel brown", 20),
        ("strawberry blonde", 15), ("fiery ginger", 10)
    ],
    "gnome": [
        ("warm chestnut curls", 25), ("golden honey blonde", 25), ("strawberry blonde", 25),
        ("fiery copper red", 25)
    ],
}

EXPANDED_HAIR_DYE_TEMPLATES = [
    # Vibrant & Pastel Anime Dyes
    "pastel pink", "bubblegum pink", "lavender violet", "electric neon blue",
    "sky blue", "mint green", "emerald teal", "turquoise", "rose gold",
    "sunset coral", "neon magenta", "amethyst purple", "periwinkle",
    # Modern / Fashion Shades
    "bleached platinum blonde", "smoky ash-silver", "vibrant fire-engine red",
    "deep wine burgundy", "midnight navy blue",
    # Two-Tone & Balayage Highlights
    "black with frosted silver tips", "blonde with pastel pink streaks",
    "dark brown with caramel balayage", "raven black with crimson underlayer",
    "silver-white with lilac highlights", "ash brown with honey highlights"
]

def infer_natural_hair_color(
    race: str,
    name: str = "",
    coat_color: str = "",
    ear_tail_feature: str = "",
    seed: str = ""
) -> str:
    """Infers natural biological hair color for any character:
    - Full Beastfolk: derived from body coat color or species template.
    - Half-Beast: 50% ear/tail fur color match, 50% human name culture match.
    - Humans: derived from cultural name origin pool.
    - Fantasy Humanoids: derived from race-weighted natural hair pool.
    """
    clean_race = str(race or "").strip().lower().replace("-", "_")
    is_half = is_half_beast_race(clean_race)
    is_full = is_beast_race(clean_race) and not is_half

    seed_key = f"{name}_{seed}_{race}_hair"
    h = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) if (name or seed) else None
    rng = random.Random(h) if h is not None else random

    # 1. Full Beastfolk: coat color takes precedence
    if is_full:
        if coat_color:
            return infer_natural_hair_color_from_coat(coat_color, race=clean_race)
        spec = get_species_key_from_race(clean_race)
        if spec and spec in SPECIES_TEMPLATES:
            coats = SPECIES_TEMPLATES[spec].get("coats", [])
            if coats:
                return infer_natural_hair_color_from_coat(coats[rng.randint(0, len(coats)-1)], race=clean_race)
        return infer_natural_hair_color_from_coat("", race=clean_race)

    # 2. Half-Beast: 50% chance to match ear/tail fur color, 50% chance to match human heritage
    if is_half:
        match_ear = rng.random() < 0.50
        if match_ear and ear_tail_feature:
            clean_ear = re.sub(
                r'\b(ears?|tail|horns?|crest|wings?|matching|soft|puff|cotton|tufted|fur|furry|plumage|accents?)\b',
                '',
                str(ear_tail_feature),
                flags=re.IGNORECASE
            ).strip()
            clean_ear = re.sub(r'\s+', ' ', clean_ear).strip(' -&')
            if clean_ear:
                ear_nat = infer_natural_hair_color_from_coat(clean_ear, race=clean_race)
                if ear_nat and ear_nat != "natural":
                    return ear_nat

    # 3. Fantasy Humanoids: race-weighted pool
    for f_race, pool in sorted(HUMANOID_RACE_NATURAL_HAIR_POOLS.items(), key=lambda x: len(x[0]), reverse=True):
        if f_race in clean_race:
            tones, weights = zip(*pool)
            return rng.choices(tones, weights=weights, k=1)[0]

    # 4. Humans (and Half-Beasts with human heritage expression)
    cult_group = None
    if name:
        try:
            import namegen
            parts = name.strip().split()
            first = parts[0].lower() if parts else ""
            last = parts[-1].lower() if len(parts) > 1 else ""
            raw_cult = namegen._SURNAME_TO_CULTURE.get(last) or namegen._FIRST_NAME_TO_CULTURE.get(first) or ""
            cult_group = CULTURE_TO_GROUP.get(raw_cult)
        except Exception:
            cult_group = None

    if cult_group and cult_group in CULTURE_NATURAL_HAIR_POOLS:
        tones, weights = zip(*CULTURE_NATURAL_HAIR_POOLS[cult_group])
        return rng.choices(tones, weights=weights, k=1)[0]
    else:
        # Default global/western natural palette fallback
        tones, weights = zip(*CULTURE_NATURAL_HAIR_POOLS["celtic_germanic"])
        return rng.choices(tones, weights=weights, k=1)[0]

def roll_hair_color_and_dye(
    race: str,
    name: str = "",
    coat_color: str = "",
    ear_tail_feature: str = "",
    seed: str = "",
    force_dye: bool = False
) -> tuple[str, bool, str]:
    """Rolls hair color with a 35% dye rate across all archetypes (Humans, Beastfolk, Half-Beasts, Fantasy Humanoids).
    Returns: (hair_color, is_dyed, natural_hair_color)
    """
    clean_race = str(race or "").strip().lower().replace("-", "_")
    is_half = is_half_beast_race(clean_race)
    is_full = is_beast_race(clean_race) and not is_half

    seed_key = f"{name}_{seed}_{race}_hair_roll"
    h = int(hashlib.md5(seed_key.encode("utf-8")).hexdigest(), 16) if (name or seed) else None
    rng = random.Random(h) if h is not None else random

    natural_color = infer_natural_hair_color(
        clean_race, name=name, coat_color=coat_color, ear_tail_feature=ear_tail_feature, seed=seed
    )

    is_dyed = force_dye or (rng.random() < 0.35)

    if is_dyed:
        dye_candidates = list(EXPANDED_HAIR_DYE_TEMPLATES)
        spec = get_species_key_from_race(clean_race)
        if is_full and spec and spec in SPECIES_TEMPLATES:
            for sh in SPECIES_TEMPLATES[spec].get("hair", []):
                if is_contrasting_shade(coat_color, sh):
                    dye_candidates.append(sh.lower())

        # When character has a coat color (Full Beastfolk), dyed hair MUST be a contrasting shade to their coat!
        if is_full and coat_color:
            coat_fams = get_color_families(coat_color)
            if coat_fams:
                contrast_candidates = [
                    d for d in dye_candidates
                    if not (get_color_families(d) & coat_fams) and is_contrasting_shade(coat_color, d)
                ]
                if contrast_candidates:
                    dye_candidates = contrast_candidates

        hair_color = rng.choice(dye_candidates)

        if is_full and coat_color:
            coat_fams = get_color_families(coat_color)
            if (get_color_families(hair_color) & coat_fams) or hair_color.lower() == natural_color.lower():
                fallback_pool = [
                    "crimson red", "midnight jet-black", "pastel sakura-pink",
                    "electric neon blue", "emerald green", "platinum blonde", "royal violet"
                ]
                safe_fallbacks = [fb for fb in fallback_pool if not (get_color_families(fb) & coat_fams)]
                hair_color = safe_fallbacks[rng.randint(0, len(safe_fallbacks) - 1)] if safe_fallbacks else "midnight jet-black"
        else:
            if hair_color.lower() == natural_color.lower():
                hair_color = "pastel pink" if "pink" not in natural_color else "electric neon blue"

        return hair_color, True, natural_color
    else:
        return natural_color, False, natural_color

PHYSIQUE_FEMALE_TEMPLATES = [
    "Soft & Curved",
    "Toned & Athletic",
    "Hourglass & Slender",
    "Petite & Soft",
    "Full-Figured & Voluptuous",
    "Thick & Curvy",
    "Soft & Overweight"
]

PHYSIQUE_MALE_TEMPLATES = [
    "Average & Proportionate",
    "Broad Shoulders & Lean",
    "Toned & Athletic",
    "Muscular & Powerful",
    "Slender & Lanky",
    "Stocky & Thick",
    "Heavy & Overweight"
]

UNDERGARMENT_COLOR_PALETTES = [
    "Black", "White", "Baby Pink", "Crimson", "Midnight Navy",
    "Emerald Green", "Pastel Lavender", "Charcoal Grey", "Beige / Skin-Tone",
    "Royal Purple", "Wine Red", "Powder Blue"
]

FEMALE_BRA_STYLES_PRUDE = [
    "soft cotton bralette",
    "wireless seamless bra",
    "simple white t-shirt bra",
    "pastel ribbed crop bralette",
    "full-coverage beige comfort bra",
    "unpadded modal triangle bra"
]

FEMALE_BRA_STYLES_MODERATE = [
    "lace-trimmed plunge bra",
    "demi-cup balcony bra",
    "sporty racerback bralette",
    "smooth microfiber push-up bra",
    "satin contour bra with delicate bows",
    "scalloped lace t-shirt bra"
]

FEMALE_BRA_STYLES_BOLD = [
    "sheer floral lace balcony bra",
    "strappy black satin plunge bra",
    "unlined mesh peekaboo bra",
    "crimson silk corset-style bra",
    "low-cut halter lace bralette",
    "translucent silk underwire bra",
    "scant lace quarter-cup bra"
]

FEMALE_UNDERWEAR_STYLES_PRUDE = [
    "full-coverage cotton briefs",
    "soft pastel hipster panties",
    "seamless stretch boyshorts",
    "ribbed white cotton panties",
    "classic low-rise modal briefs"
]

FEMALE_UNDERWEAR_STYLES_MODERATE = [
    "lace-trimmed bikini panties",
    "satin cheekies with side lace",
    "low-rise seamless stretch briefs",
    "stretch modal hipster panties",
    "delicate lace-trimmed thong",
    "soft microfiber boyshorts"
]

FEMALE_UNDERWEAR_STYLES_BOLD = [
    "sheer black lace thong",
    "strappy satin G-string",
    "micro lace thong",
    "silk peekaboo briefs",
    "low-slung Brazilian-cut lace cheeky",
    "translucent mesh thong",
    "open-back lace thong"
]

MALE_UNDERWEAR_STYLES_PRUDE = [
    "classic grey cotton boxer briefs",
    "navy knit relaxed boxers",
    "white ribbed athletic briefs",
    "relaxed fit plaid cotton boxers",
    "soft modal everyday boxer briefs"
]

MALE_UNDERWEAR_STYLES_MODERATE = [
    "fitted black modal boxer briefs",
    "athletic compression trunks",
    "low-rise charcoal trunks",
    "seamless stretch boxer briefs",
    "navy performance trunks"
]

MALE_UNDERWEAR_STYLES_BOLD = [
    "low-rise black silk boxer briefs",
    "snug athletic micro trunks",
    "sheer performance trunks",
    "fitted crimson satin boxers",
    "body-hugging low-waist trunks"
]

def generate_procedural_undergarments(
    seed_str: str = "",
    gender: str = "female",
    openness: str = "moderate",
    dynamic: str = "",
    traits: List[str] = None,
    scen_key: str = "fantasy",
    hash_val: int = None
) -> Dict[str, str]:
    """
    Generates procedural undergarments with realistic style, color coordination, and openness-scaled commando rates.
    """
    if hash_val is None:
        raw_seed = (str(seed_str) + "_" + str(gender) + "_undergarments_v1").encode("utf-8")
        hash_val = int(hashlib.md5(raw_seed).hexdigest(), 16) if seed_str else 0

    raw_g = str(gender or "").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
    is_female = not is_male

    open_l = str(openness or "moderate").lower()
    traits_l = " ".join(str(t).lower() for t in (traits or []))
    dyn_l = str(dynamic or "").lower()

    is_prude = "prude" in open_l or "modest" in open_l or "innocent" in open_l or "shy" in traits_l
    is_bold = "bold" in open_l or "shameless" in open_l or "lewd" in open_l or "hedonistic" in open_l or "uninhibited" in open_l or any(k in dyn_l for k in ("hedonist", "insatiable", "high-drive", "dominant", "voracious")) or any(k in traits_l for k in ("shameless", "bold", "seductive", "exhibitionist", "teasing"))

    color = UNDERGARMENT_COLOR_PALETTES[hash_val % len(UNDERGARMENT_COLOR_PALETTES)]

    if is_female:
        roll_commando = (hash_val // 19) % 100
        if is_prude:
            bra_missing = False
            und_missing = False
        elif is_bold:
            if roll_commando < 8:
                bra_missing = True
                und_missing = False
            elif roll_commando < 16:
                bra_missing = False
                und_missing = True
            elif roll_commando < 20:
                bra_missing = True
                und_missing = True
            else:
                bra_missing = False
                und_missing = False
        else:
            if roll_commando < 2:
                bra_missing = True
                und_missing = False
            elif roll_commando < 4:
                bra_missing = False
                und_missing = True
            elif roll_commando < 5:
                bra_missing = True
                und_missing = True
            else:
                bra_missing = False
                und_missing = False

        if bra_missing:
            bra = "None (Bra-less)"
        else:
            if is_prude:
                bra_pool = FEMALE_BRA_STYLES_PRUDE
            elif is_bold:
                bra_pool = FEMALE_BRA_STYLES_BOLD
            else:
                bra_pool = FEMALE_BRA_STYLES_MODERATE
            bra_style = bra_pool[(hash_val // 23) % len(bra_pool)]
            if any(c.lower() in bra_style.lower() for c in ("black", "white", "crimson", "beige", "pastel")):
                bra = bra_style.capitalize()
            else:
                bra = f"{color} {bra_style}"

        if und_missing:
            underwear = "None (Commando)"
        else:
            if is_prude:
                und_pool = FEMALE_UNDERWEAR_STYLES_PRUDE
            elif is_bold:
                und_pool = FEMALE_UNDERWEAR_STYLES_BOLD
            else:
                und_pool = FEMALE_UNDERWEAR_STYLES_MODERATE
            und_style = und_pool[(hash_val // 29) % len(und_pool)]

            if not bra_missing and not any(c.lower() in und_style.lower() for c in ("black", "white", "crimson", "beige", "pastel")):
                underwear = f"Matching {color.lower()} {und_style}"
            elif any(c.lower() in und_style.lower() for c in ("black", "white", "crimson", "beige", "pastel")):
                underwear = und_style.capitalize()
            else:
                underwear = f"{color} {und_style}"

        return {
            "bra": bra,
            "underwear": underwear
        }

    else:
        roll_commando = (hash_val // 19) % 100
        if is_prude:
            und_missing = False
        elif is_bold:
            und_missing = (roll_commando < 15)
        else:
            und_missing = (roll_commando < 5)

        if und_missing:
            underwear = "None (Freeballing / Commando)"
        else:
            if is_prude:
                und_pool = MALE_UNDERWEAR_STYLES_PRUDE
            elif is_bold:
                und_pool = MALE_UNDERWEAR_STYLES_BOLD
            else:
                und_pool = MALE_UNDERWEAR_STYLES_MODERATE
            und_style = und_pool[(hash_val // 31) % len(und_pool)]
            if any(c.lower() in und_style.lower() for c in ("black", "white", "crimson", "grey", "navy", "plaid")):
                underwear = und_style.capitalize()
            else:
                underwear = f"{color} {und_style}"

        return {
            "bra": "",
            "underwear": underwear
        }

TRAIT_TEMPLATES = [
    ["Observant", "Analytic", "Competitive", "Secretly Lonely"],
    ["Sensitive", "Studious", "Easily Flustered"],
    ["Manipulative", "Charismatic", "Judgmental"],
    ["Mysterious", "Determined", "Inquisitive"],
    ["Protective", "Loyal", "Perfectionist", "Sarcastic"],
    ["Playful", "Energetic", "Impulsive", "Kindhearted"],
    ["Stoic", "Resourceful", "Cynical", "Duty-Bound"],
]

MANNERISM_TEMPLATES = [
    "Adjusts glasses when thinking",
    "Twirls hair when nervous",
    "Crosses arms and scowls when challenged",
    "Fidgets with hoodie strings",
    "Speaks in a quiet, measured tone",
    "Twitches ears when excited",
    "Taps finger impatiently on cheek",
    "Smiles faintly before answering",
]

def is_nsfw_scenario(scen_key: str = "fantasy") -> bool:
    from scenario_data import has_tag
    return has_tag(scen_key, "nsfw")

def get_default_stature_for_race(race_str: str) -> str:
    r = (race_str or "human").lower()
    if r in ("dwarf", "goblin", "halfling", "gnome"):
        return "short"
    if r in ("elf", "dark_elf"):
        return "tall"
    return "average"

def infer_contact_gender(contact: Dict[str, Any]) -> str:
    """Infers gender from explicit gender column, basic_info, appearance, description, or name/pronoun hints.
    Guarantees a concrete, immediately known gender string ('female' or 'male').
    Includes self-healing safeguards for corrupted 'female' defaults on unambiguous male names.
    """
    if not isinstance(contact, dict):
        return "female"
    g = str(contact.get("gender") or "").strip().lower()
    basic = contact.get("basic_info") or {}
    bg = str(basic.get("gender") or "").strip().lower() if isinstance(basic, dict) else ""

    name_str = str(contact.get("name", "")).strip().lower()
    first_name = name_str.split()[0] if name_str else ""

    known_male = False
    known_female = False
    try:
        from namegen import is_known_male_name, is_known_female_name
        known_male = bool(is_known_male_name(first_name) or is_known_male_name(name_str))
        known_female = bool(is_known_female_name(first_name) or is_known_female_name(name_str))
    except Exception:
        pass

    app = contact.get("appearance") or {}
    has_breast = False
    has_penis = False
    if isinstance(app, dict):
        if app.get("breast_size") and str(app.get("breast_size")).lower() not in ("flat", "none", ""):
            has_breast = True
        if app.get("penis_size") and str(app.get("penis_size")).lower() not in ("none", ""):
            has_penis = True

    raw_traits = contact.get("unlocked_traits", []) or []
    traits_text = " ".join(str(t.get("name") or t.get("trait") or t) if isinstance(t, dict) else str(t) for t in raw_traits if t)
    text = (
        name_str + " " +
        (str(basic.get("description", "")) if isinstance(basic, dict) else "") + " " +
        (str(basic.get("role", "")) if isinstance(basic, dict) else "") + " " +
        traits_text
    ).lower()

    words = set(text.replace(".", " ").replace(",", " ").replace("!", " ").replace("?", " ").split())
    female_kws = {"girl", "woman", "female", "lady", "she", "her", "hers", "daughter", "mother", "sister", "queen", "princess", "heroine", "mrs", "miss", "ms", "waifu"}
    male_kws = {"boy", "man", "male", "guy", "he", "him", "his", "son", "father", "brother", "king", "prince", "lord", "sir", "mr"}

    has_f = bool(words.intersection(female_kws)) or has_breast
    has_m = bool(words.intersection(male_kws)) or has_penis

    # Self-healing: if an unambiguous male name (e.g. Ronald, Robert) was saved with gender 'female'
    # due to the uninitialized fallback, but has no explicit female indicators in appearance or text:
    if (g == "female" or bg == "female") and known_male and not known_female and not has_f:
        return "male"
    if (g == "male" or bg == "male") and known_female and not known_male and not has_m:
        return "female"

    if g and g not in ("unknown", "none", "n/a", "null", ""):
        return g
    if bg and bg not in ("unknown", "none", "n/a", "null", ""):
        return bg

    if has_breast:
        return "female"
    if has_penis:
        return "male"

    if known_male and not known_female:
        return "male"
    if known_female and not known_male:
        return "female"

    if has_f and not has_m:
        return "female"
    if has_m and not has_f:
        return "male"
    if has_f:
        return "female"
    if has_m:
        return "male"

    return "female"


IMMUTABLE_PHYSICAL_APPEARANCE_KEYS = {
    "eye_color", "eyes",
    "hair_color", "hair_style", "hair_length", "hair",
    "is_dyed", "natural_hair_color", "natural_hair",
    "stature", "height",
    "physique",
    "coat_color", "fur_color", "coat", "scale_color", "feather_color",
    "skin_color", "skin", "skin_type", "coat_type",
    "distinctive_features", "features", "marks",
    "breast_size", "penis_size",
    "predetermined_intercourse",
    "intimate_demeanor", "intimate_dynamic",
    "erotic_openness", "openness",
    "undergarments", "bra", "underwear",
}

def format_persona_summary(app_dict: Dict[str, Any], scen_key: str = "fantasy", mannerisms: str = "", traits: List[str] = None, revealed_flags: Dict[str, Any] = None, gender: str = "", include_intimate: bool = False, **kwargs) -> str:
    """Formats a concise persona summary (appearance, mannerisms, 3-4 traits) for LLM system prompt context."""
    if not app_dict:
        app_dict = {}
    eye = (app_dict.get("eye_color") or "").replace("_", " ").title()
    h_color = (app_dict.get("hair_color") or "").title()
    h_len = (app_dict.get("hair_length") or "").lower()
    h_style = (app_dict.get("hair_style") or "").lower()
    stature = (app_dict.get("stature") or "").lower().replace("_", " ")
    physique = (app_dict.get("physique") or "").strip()
    skin = (app_dict.get("skin_color") or "").title()
    coat = (app_dict.get("coat_color") or "").title()
    features = (app_dict.get("distinctive_features") or "").strip()
    outfit = (app_dict.get("outfit_style") or "").strip()

    parts = []
    gen_val = str(gender or app_dict.get("gender") or "").strip().lower()
    if gen_val:
        if any(kw in gen_val for kw in ("male", "man", "boy")) and "female" not in gen_val:
            parts.append("Gender: Male (he/him)")
        elif any(kw in gen_val for kw in ("female", "woman", "girl")):
            parts.append("Gender: Female (she/her)")
        elif any(kw in gen_val for kw in ("non-binary", "enby", "neutral")):
            parts.append("Gender: Non-binary (they/them)")
        else:
            parts.append(f"Gender: {gen_val.title()}")
    if eye:
        parts.append(f"{eye} eyes")
    if h_color or h_len or h_style:
        is_dyed = bool(app_dict.get("is_dyed"))
        if not is_dyed and coat and is_contrasting_shade(coat, h_color):
            is_dyed = True
        natural_hair = app_dict.get("natural_hair_color") or (infer_natural_hair_color_from_coat(coat) if is_dyed and coat else "")
        if is_dyed and natural_hair and natural_hair.lower() != h_color.lower():
            hair_str = f"{h_len} {h_style} {h_color} hair (dyed; naturally {natural_hair.lower()})".strip()
        else:
            hair_str = f"{h_len} {h_style} {h_color} hair".strip()
        parts.append(hair_str)
    if stature:
        stat_str = f"{stature} stature"
        if physique:
            stat_str += f" ({physique})"
        parts.append(stat_str)
    if coat:
        c_lower = coat.lower()
        if any(term in c_lower for term in ("fur", "coat", "scales", "scale", "feather", "fleece", "pelt", "hide")):
            parts.append(f"{coat}")
        else:
            parts.append(f"{coat} coat")
    elif skin:
        s_lower = skin.lower()
        if "skin" in s_lower or "complexion" in s_lower:
            parts.append(f"{skin}")
        else:
            parts.append(f"{skin} skin")
    if features:
        parts.append(f"{features}")
    if outfit:
        parts.append(f"wearing {outfit}")

    if mannerisms:
        parts.append(f"Mannerisms: {mannerisms}")
    if traits and isinstance(traits, list):
        clean_traits = [str(t.get("name") or t.get("trait") or t) if isinstance(t, dict) else str(t) for t in traits[:4] if t]
        if clean_traits:
            parts.append(f"Traits: {', '.join(clean_traits)}")

    if is_nsfw_scenario(scen_key):
        if app_dict.get("breast_size"):
            parts.append(f"{app_dict['breast_size'].title()} breasts")
        if app_dict.get("penis_size"):
            parts.append(f"{app_dict['penis_size'].title()} penis")
        if app_dict.get("intercourse_experience") and app_dict["intercourse_experience"] != "unknown":
            parts.append(f"Intercourse: {app_dict['intercourse_experience'].replace('_', ' ').title()}")
        if app_dict.get("oral_experience") and app_dict["oral_experience"] not in ("unknown", "inexperienced"):
            parts.append(f"Oral: {app_dict['oral_experience'].replace('_', ' ').title()}")
        if app_dict.get("intimate_demeanor"):
            parts.append(f"Intimate Demeanor: {app_dict['intimate_demeanor']}")
        if app_dict.get("intimate_dynamic"):
            parts.append(f"Intimate Dynamic: {app_dict['intimate_dynamic']}")
        if app_dict.get("sensitive_spots"):
            parts.append(f"Sensitive Spots: {app_dict['sensitive_spots']}")
        if app_dict.get("turn_ons"):
            parts.append(f"Turn-Ons: {app_dict['turn_ons']}")
        if app_dict.get("fetishes"):
            parts.append(f"Fetishes: {app_dict['fetishes']}")

    return ", ".join(parts)

def infer_mannerism_default(race: str = "human", desc: Any = "") -> str:
    """Generates a smart fallback mannerism for contacts with authentic animalistic quirks for beastfolk and hybrids."""
    if isinstance(desc, dict):
        desc = " ".join(str(v) for v in desc.values() if v)
    desc_lower = str(desc or "").lower()
    race_lower = str(race or "").lower().replace("-", "_")

    sp_key = get_species_key_from_race(race_lower, desc_lower)
    seed_str = (desc_lower + "_" + race_lower).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0

    if sp_key and sp_key in SPECIES_TEMPLATES:
        manner_pool = SPECIES_TEMPLATES[sp_key]["mannerisms"]
        return manner_pool[hash_val % len(manner_pool)]

    if "student" in desc_lower or "school" in desc_lower:
        if "queen bee" in desc_lower or "popular" in desc_lower or "disciplined" in desc_lower:
            return "Adjusts glasses when thinking and smirks dismissively"
        return "Crosses arms thoughtfully and smiles faintly before answering"

    return MANNERISM_TEMPLATES[hash_val % len(MANNERISM_TEMPLATES)]

PREFERENCE_KEYWORDS = (
    "like", "likes", "dislike", "dislikes", "prefer", "prefers", "preference",
    "enjoy", "enjoys", "hate", "hates", "fond", "afraid", "fearful", "fear",
    "value", "values", "respect", "respects", "trust", "trusts", "rely", "relies",
    "willing", "reluctant", "candid", "protective", "awed", "responds"
)

def sanitize_traits(traits: list, max_words: int = 3, max_count: int = 3) -> list[str]:
    """Filters personality traits to clean 1-3 word attributes (e.g. 'Confident', 'Secretly Failing Math').
    Caps strictly to max_count (default 3).
    """
    if not isinstance(traits, list):
        return []
    cleaned = []
    for t in traits:
        if not isinstance(t, str):
            continue
        s = t.strip()
        if not s or s.endswith('.') or ',' in s:
            continue
        # Strip out non-printable or corrupt unicode chars
        s = "".join(ch for ch in s if ch.isprintable() and ord(ch) < 1000)
        s = s.strip()
        if not s:
            continue
        # Filter out multi-word sentence entries (>2 words)
        words = s.split()
        if len(words) > max_words:
            continue
        # Capitalize nicely
        s_cap = " ".join(w.capitalize() for w in words)
        if s_cap.lower() not in (c.lower() for c in cleaned):
            cleaned.append(s_cap)
    return cleaned[:max_count]

def sanitize_preferences(preferences: list, max_words: int = 3, max_count: int = 3) -> list[str]:
    """Filters preferences/likes/dislikes to clean 1-3 word tags (e.g. 'Likes Honesty', 'Dislikes Arrogance').
    Caps strictly to max_count (default 3).
    """
    if not isinstance(preferences, list):
        return []
    cleaned = []
    for p in preferences:
        if not isinstance(p, str):
            continue
        s = p.strip()
        if not s or s.endswith('.'):
            continue
        s = "".join(ch for ch in s if ch.isprintable() and ord(ch) < 1000)
        s = s.strip()
        if not s:
            continue
        words = s.split()
        if len(words) > max_words:
            continue
        s_cap = " ".join(w.capitalize() for w in words)
        if s_cap.lower() not in (c.lower() for c in cleaned):
            cleaned.append(s_cap)
    return cleaned[:max_count]

def split_traits_and_preferences(
    raw_traits: list,
    raw_prefs: list = None,
    role: str = "",
    race: str = "",
    seed_str: str = ""
) -> tuple[list[str], list[str]]:
    """Splits and sanitizes a character's trait/preference data into 2 separate categories:
    1. Personality Traits (Normalized from hardcoded trait registry, Max 3)
    2. Preferences & Dislikes (Grounded in-game items & behavioral stances, Max 3 each)
    """
    from mechanics.combat.traits import normalize_traits, assign_npc_traits, assign_npc_preferences

    traits_in = raw_traits if isinstance(raw_traits, list) else []
    prefs_in = raw_prefs if isinstance(raw_prefs, list) else []

    # Normalize traits against canonical trait registry
    traits_out = normalize_traits(traits_in)
    if not traits_out:
        fallback_seed = seed_str or " ".join(str(t) for t in traits_in) or role or race
        traits_out = assign_npc_traits(fallback_seed, count=3, role=role, race=race)

    # Process preferences with grounded items & behavioral stances
    likes_out, dislikes_out = categorize_likes_and_dislikes(
        prefs_in,
        traits=traits_out,
        role=role,
        race=race,
        desc=seed_str
    )
    combined_prefs = likes_out + dislikes_out

    return traits_out[:3], combined_prefs[:6]

DISLIKE_KEYWORDS = (
    "dislike", "dislikes", "hate", "hates", "fears", "fear", "afraid", "avoid", "avoids",
    "detest", "detests", "loathe", "loathes", "allergic", "cannot stand", "can't stand",
    "intolerant", "annoyed by", "averse", "despise", "despises", "disdains", "disdain",
    "resents", "resent", "resists", "resist", "repulsed", "disgusted", "exasperated",
    "angered", "frustrated", "aversion", "dread", "contempt", "hatred"
)

LIKE_KEYWORDS = (
    "like", "likes", "prefer", "prefers", "love", "loves", "enjoy", "enjoys",
    "fond of", "appreciates", "values", "fascinated by", "adores", "favors", "favor"
)

def format_mannerisms_list(
    mannerisms_raw: Any,
    race: str = "human",
    desc: Any = "",
    traits: list = None,
    role: str = ""
) -> list[str]:
    """
    Parses and formats 1-3 distinct behavioral mannerisms and habits for a character.
    Anchored directly to the character's active Traits and biological Race.
    """
    from mechanics.combat.traits import generate_trait_anchored_mannerisms

    cleaned = []
    if isinstance(mannerisms_raw, list):
        for item in mannerisms_raw:
            if isinstance(item, str) and item.strip():
                sub_items = re.split(r'[\n;•·\r]+', item)
                for si in sub_items:
                    s_str = si.strip().lstrip("-*•· ").rstrip(".")
                    if s_str and len(s_str.split()) >= 2 and s_str.lower() not in (c.lower() for c in cleaned):
                        cleaned.append(s_str[0].upper() + s_str[1:])
    elif isinstance(mannerisms_raw, str) and mannerisms_raw.strip():
        sub_items = re.split(r'[\n;•·\r]+', mannerisms_raw)
        for si in sub_items:
            s_str = si.strip().lstrip("-*•· ").rstrip(".")
            if s_str and len(s_str.split()) >= 2 and s_str.lower() not in (c.lower() for c in cleaned):
                cleaned.append(s_str[0].upper() + s_str[1:])

    # If empty or fewer than 2, supplement with trait- and race-anchored mannerisms
    if len(cleaned) < 2:
        seed_str = str(desc or "") + "_" + str(role or "") + "_" + str(race or "")
        anchored = generate_trait_anchored_mannerisms(traits or ["Diligent"], race=race, seed_str=seed_str)
        for m in anchored:
            if m.lower() not in (c.lower() for c in cleaned):
                cleaned.append(m)
            if len(cleaned) >= 2:
                break

    return cleaned[:3]

def format_preference_phrase(text: str, is_dislike: bool = False) -> str:
    """Formats a preference item cleanly, ensuring a proper prefix like 'Likes X' or 'Dislikes X'."""
    s = text.strip().rstrip(".")
    if not s:
        return ""
    words = s.split()
    first_w = words[0].lower()
    if is_dislike:
        if first_w in ("dislike", "dislikes"):
            return "Dislikes " + " ".join(words[1:]) if len(words) > 1 else "Dislikes Incompetence"
        elif first_w in ("hate", "hates"):
            return "Hates " + " ".join(words[1:]) if len(words) > 1 else "Hates Lies"
        elif first_w in ("avoids", "avoid"):
            return "Avoids " + " ".join(words[1:]) if len(words) > 1 else "Avoids Crowds"
        elif first_w in ("disdains", "disdain", "resents", "resent", "resists", "resist", "repulsed", "disgusted", "exasperated", "angered", "frustrated", "aversion", "dread", "contempt", "hatred", "intolerant"):
            return s
        else:
            return f"Dislikes {s}"
    else:
        if first_w in ("like", "likes"):
            return "Likes " + " ".join(words[1:]) if len(words) > 1 else "Likes Sincerity"
        elif first_w in ("prefer", "prefers"):
            return "Prefers " + " ".join(words[1:]) if len(words) > 1 else "Prefers Directness"
        elif first_w in ("love", "loves"):
            return "Loves " + " ".join(words[1:]) if len(words) > 1 else "Loves Warmth"
        elif first_w in ("enjoy", "enjoys"):
            return "Enjoys " + " ".join(words[1:]) if len(words) > 1 else "Enjoys Peace"
        elif first_w in ("favors", "favor", "values", "value", "appreciates", "appreciate"):
            return s
        else:
            return f"Likes {s}"

def categorize_likes_and_dislikes(
    preferences_raw: Any,
    traits: list = None,
    role: str = "",
    race: str = "",
    desc: Any = ""
) -> tuple[list[str], list[str]]:
    """
    Separates preferences into 2 distinct categories:
    1. Likes (2-3 items: Grounded Foods/Drinks, In-game Gifts, and Behavioral Stances)
    2. Dislikes (2-3 items: Disliked Foods/Items and Behavioral Dislikes)
    """
    from mechanics.combat.traits import assign_npc_preferences

    raw_list = []
    if isinstance(preferences_raw, list):
        raw_list = preferences_raw
    elif isinstance(preferences_raw, str) and preferences_raw.strip():
        raw_list = re.split(r'[,;\n]+', preferences_raw)

    likes: list[str] = []
    dislikes: list[str] = []

    for item in raw_list:
        if not isinstance(item, str):
            continue
        clean = item.strip().lstrip("-*•· ").rstrip(".")
        if not clean:
            continue
        clean_low = clean.lower()
        if any(kw in clean_low for kw in DISLIKE_KEYWORDS):
            formatted = format_preference_phrase(clean, is_dislike=True)
            if formatted.lower() not in (d.lower() for d in dislikes):
                dislikes.append(formatted)
        else:
            formatted = format_preference_phrase(clean, is_dislike=False)
            if formatted.lower() not in (l.lower() for l in likes):
                likes.append(formatted)

    # If fewer than 2 likes or dislikes, supplement with grounded in-game items and behavioral stances
    seed_str = str(desc or "") + "_" + str(role or "") + "_" + str(race or "")
    if len(likes) < 2 or len(dislikes) < 2:
        g_likes, g_dislikes = assign_npc_preferences(seed_str, traits=traits, role=role, race=race)
        
        for gl in g_likes:
            if len(likes) >= 3:
                break
            if gl.lower() not in (l.lower() for l in likes):
                likes.append(gl)

        for gd in g_dislikes:
            if len(dislikes) >= 3:
                break
            if gd.lower() not in (d.lower() for d in dislikes):
                dislikes.append(gd)

    # Ensure at least 1 grounded physical gift like exists so the NPC can receive favorite gifts
    from mechanics.combat.traits import is_gift_item
    if not any(is_gift_item(l) for l in likes):
        g_likes, _ = assign_npc_preferences(seed_str, traits=traits, role=role, race=race)
        for gl in g_likes:
            if is_gift_item(gl) and gl.lower() not in (l.lower() for l in likes):
                if len(likes) >= 3:
                    likes[-1] = gl
                else:
                    likes.append(gl)
                break

    return likes[:3], dislikes[:3]

def sanitize_npc_description(description: str, appearance: dict = None) -> str:
    """Strips raw physical adjective mashups, internal prompt/psychological tags
    (Drive, Flaw, Mannerism, Contradiction, Family), and legacy sibling/lineage references
    from an NPC's description field so it remains a clean 1-sentence narrative identity/role summary.
    """
    if not description or not isinstance(description, str):
        return ""
    s = description.strip()
    # Strip internal prompt / psychological tags (Drive, Flaw, Mannerism, Contradiction, Family)
    s = re.split(r'(?i)\b(?:Drive|Flaw|Mannerism|Contradiction|Family)\s*:', s)[0].strip(' .,-')
    # Strip sibling / family lineage sentences (these belong exclusively in Relations & Family)
    s = re.sub(r'(?i)\b(sibling|brother|sister|son|daughter)\s+of\s+[A-Za-z\s\'-]+[\.]?', '', s)
    s = re.sub(r'\s+', ' ', s).strip(' .,-')

    phys_keywords = {"hazel", "chestnut", "blonde", "brunette", "wavy", "slender", "petite", "average", "sharp eyes", "manicured", "high-school fashion", "designer accessories"}
    words_lower = set(s.lower().replace("/", " ").replace(",", " ").split())
    
    matches = words_lower.intersection(phys_keywords)
    if len(matches) >= 2:
        return ""
    return s

