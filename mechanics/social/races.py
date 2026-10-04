from __future__ import annotations
"""
Modular NPC Race Engine & Genre Templates for Hikayat.

Handles race normalization, species template mapping, genre restriction rules,
and UI display formatting across Fantasy, Sci-Fi, Post-Apocalypse, and Slice-of-Life scenarios.
"""
from typing import Dict, Any, List

DEFAULT_RACE = "human"

# Core Fantasy templates
FANTASY_RACES = {
    "human": "human",
    "elf": "elf",
    "dwarf": "dwarf",
    "dark elf": "dark_elf",
    "dark_elf": "dark_elf",
    "drow": "dark_elf",
    "goblin": "goblin",
    "orc": "orc",
    "gnome": "gnome",
    "halfling": "halfling",
}

BEASTFOLK_ALIASES = {
    "cat": "beastfolk:cat", "catgirl": "beastfolk:cat", "neko": "beastfolk:cat",
    "wolf": "beastfolk:wolf", "lupine": "beastfolk:wolf",
    "fox": "beastfolk:fox", "kitsune": "beastfolk:fox", "vulpine": "beastfolk:fox",
    "rabbit": "beastfolk:rabbit", "bunny": "beastfolk:rabbit",
    "bear": "beastfolk:bear",
    "bird": "beastfolk:bird", "avian": "beastfolk:bird", "crow": "beastfolk:bird", "raven": "beastfolk:bird",
    "hawk": "beastfolk:bird", "falcon": "beastfolk:bird", "eagle": "beastfolk:bird", "owl": "beastfolk:bird",
    "snake": "beastfolk:snake", "serpent": "beastfolk:snake", "viper": "beastfolk:snake", "cobra": "beastfolk:snake", "naga": "beastfolk:snake",
    "lizard": "beastfolk:reptile", "reptile": "beastfolk:reptile", "gecko": "beastfolk:reptile", "chameleon": "beastfolk:reptile", "alligator": "beastfolk:reptile", "crocodile": "beastfolk:reptile",
    "dragon": "beastfolk:dragon", "dragonkin": "beastfolk:dragon", "draconoid": "beastfolk:dragon", "draconic": "beastfolk:dragon", "drake": "beastfolk:dragon", "wyvern": "beastfolk:dragon",
    "tiger": "beastfolk:tiger", "tigress": "beastfolk:tiger",
    "lion": "beastfolk:lion", "lioness": "beastfolk:lion",
    "cheetah": "beastfolk:cheetah",
    "fennec": "beastfolk:fennec", "fennec_fox": "beastfolk:fennec",
    "mouse": "beastfolk:mouse", "rat": "beastfolk:mouse",
}

ANIMAL_FAMILY_SUBSPECIES: Dict[str, List[str]] = {
    "canine": ["wolf", "fox", "fennec"],
    "canid": ["wolf", "fox", "fennec"],
    "dog": ["wolf", "fox", "fennec"],
    "hound": ["wolf", "fox", "fennec"],
    "feline": ["cat", "tiger", "lion", "cheetah"],
    "felid": ["cat", "tiger", "lion", "cheetah"],
    "reptilian": ["reptile", "snake", "dragon"],
    "reptile": ["reptile", "snake", "dragon"],
    "scaly": ["reptile", "snake", "dragon"],
    "serpentine": ["snake", "dragon", "reptile"],
    "ursine": ["bear"],
    "rodent": ["mouse"],
    "murine": ["mouse"],
    "lagomorph": ["rabbit"],
    "leporid": ["rabbit"],
    "avian": ["bird"],
}

def resolve_animal_family_species(family: str, seed: str = "") -> str:
    """Randomly or deterministically (via seed) resolves a general animal family
    (e.g. canine, canid, feline, felid) into one of its distinct beastfolk subspecies."""
    fam_low = str(family or "").strip().lower().replace("-", "_")
    for key, sublist in ANIMAL_FAMILY_SUBSPECIES.items():
        if key in fam_low:
            if seed:
                import hashlib
                h = int(hashlib.md5(str(seed).encode("utf-8")).hexdigest(), 16)
                return sublist[h % len(sublist)]
            return random.choice(sublist)
    return ""


def resolve_generic_beastfolk_species(seed: str = "") -> str:
    """Deterministically (via seed) resolves generic 'beastfolk', 'anthro', 'furry', or 'half-beast'
    into one of the canonical beastfolk species."""
    species_pool = [
        "cat", "fox", "wolf", "fennec", "rabbit", "tiger", "lion", "cheetah",
        "bear", "mouse", "bird", "reptile"
    ]
    if seed:
        import hashlib
        h = int(hashlib.md5(str(seed).encode("utf-8")).hexdigest(), 16)
        return species_pool[h % len(species_pool)]
    return random.choice(species_pool)


HALF_BEAST_ALIASES = {
    "half_beast": "half_beast", "half-beast": "half_beast", "halfbeast": "half_beast",
    "hybrid": "hybrid", "beast_hybrid": "hybrid", "demi_human": "half_beast", "demi-human": "half_beast",
    "beastkin": "half_beast",
    "half_cat": "half_beast:cat", "half_fox": "half_beast:fox", "half_wolf": "half_beast:wolf",
    "half_rabbit": "half_beast:rabbit", "half_tiger": "half_beast:tiger", "half_lion": "half_beast:lion",
    "half_cheetah": "half_beast:cheetah", "half_fennec": "half_beast:fennec", "half_bear": "half_beast:bear",
    "half_mouse": "half_beast:mouse", "half_bird": "half_beast:bird", "half_avian": "half_beast:bird",
    "half_reptile": "half_beast:reptile", "half_lizard": "half_beast:reptile", "half_dragon": "half_beast:dragon", "half_snake": "half_beast:snake",
    "cat_hybrid": "hybrid:cat", "fox_hybrid": "hybrid:fox", "wolf_hybrid": "hybrid:wolf",
    "rabbit_hybrid": "hybrid:rabbit", "tiger_hybrid": "hybrid:tiger", "lion_hybrid": "hybrid:lion",
    "cheetah_hybrid": "hybrid:cheetah", "fennec_hybrid": "hybrid:fennec", "bear_hybrid": "hybrid:bear",
    "mouse_hybrid": "hybrid:mouse", "bird_hybrid": "hybrid:bird", "avian_hybrid": "hybrid:bird",
    "reptile_hybrid": "hybrid:reptile", "lizard_hybrid": "hybrid:reptile", "dragon_hybrid": "hybrid:dragon", "snake_hybrid": "hybrid:snake",
}

# Sci-Fi templates
SCI_FI_RACES = {
    "human": "human",
    "android": "android",
    "synth": "synth",
    "cyborg": "cyborg",
    "clone": "clone",
}

ALIEN_ALIASES = {
    "grey": "alien:grey", "gray": "alien:grey",
    "insectoid": "alien:insectoid", "bug": "alien:insectoid",
    "reptilian": "alien:reptilian", "lizardman": "alien:reptilian",
    "energy": "alien:energy_being", "plasma": "alien:energy_being",
    "humanoid": "alien:humanoid",
}

# Post-Apocalypse templates
POST_APOC_RACES = {
    "human": "human",
    "irradiated_human": "irradiated_human",
    "cyborg": "cyborg",
    "synth": "synth",
}

MUTANT_ALIASES = {
    "ghoul": "mutant:ghoul", "zombie": "mutant:ghoul",
    "rad_beast": "mutant:rad_beast", "beast": "mutant:rad_beast",
    "subhuman": "mutant:subhuman", "troglodyte": "mutant:subhuman",
    "psionic": "mutant:psionic", "esper": "mutant:psionic",
}


import random

FURRY_HIGH_SCHOOL_RACES = [
    # Baseline Human (10%)
    "human",
    # Primary Beastfolk (Cat 15%, Fox 15%)
    "beastfolk:cat", "beastfolk:fox",
    # Other Canids & Felines Beastfolk (15% total -> 3% each)
    "beastfolk:wolf", "beastfolk:fennec", "beastfolk:tiger", "beastfolk:cheetah", "beastfolk:lion",
    # Mouse & Rabbit Beastfolk (5% total -> 2.5% each)
    "beastfolk:mouse", "beastfolk:rabbit",
    # Other Minor Beastfolk (10% total)
    "beastfolk:bear", "beastfolk:bird", "beastfolk:reptile",
    # Cat & Fox Half-Beasts (20% total -> 10% each)
    "half_beast:cat", "half_beast:fox",
    # Other Half-Beasts (10% total -> 1.25% each across 8 species)
    "half_beast:wolf", "half_beast:tiger", "half_beast:lion", "half_beast:cheetah",
    "half_beast:fennec", "half_beast:rabbit", "half_beast:mouse", "half_beast:bear"
]

# Total Breakdown: 60% Beastfolk, 30% Half-Beast, 10% Human = 100%
FURRY_HIGH_SCHOOL_WEIGHTS = [
    0.10,                           # Human (10%)
    0.15, 0.15,                     # Cat (15%), Fox (15%)
    0.03, 0.03, 0.03, 0.03, 0.03,   # Wolf, Fennec, Tiger, Cheetah, Lion (15% total)
    0.025, 0.025,                   # Mouse, Rabbit (5% total)
    0.04, 0.03, 0.03,               # Bear (4%), Bird (3%), Reptile (3%) (10% total)
    0.10, 0.10,                     # Half-Beast Cat (10%), Half-Beast Fox (10%) (20% total)
    0.0125, 0.0125, 0.0125, 0.0125, # Half-Beast Wolf, Tiger, Lion, Cheetah (5% total)
    0.0125, 0.0125, 0.0125, 0.0125  # Half-Beast Fennec, Rabbit, Mouse, Bear (5% total)
]


def resolve_half_beast(clean: str, seed: str = "") -> str | None:
    """Helper to detect and resolve half-beast / hybrid input strings."""
    if not clean:
        return None
    # 1. Exact match in aliases
    if clean in HALF_BEAST_ALIASES:
        return HALF_BEAST_ALIASES[clean]
    # 2. Check compound animal + hybrid/half-beast (e.g. "lion hybrid", "cheetah half-beast", "half-fox")
    if any(k in clean for k in ("half_beast", "halfbeast", "hybrid", "demi_human", "beastkin", "half_breed", "half")):
        for fam_key in ANIMAL_FAMILY_SUBSPECIES:
            if fam_key in clean:
                sub = resolve_animal_family_species(fam_key, seed=seed)
                prefix = "hybrid" if "hybrid" in clean else "half_beast"
                return f"{prefix}:{sub}"
        for animal in ("fennec_fox", "fennec", "cheetah", "tiger", "tigress", "lion", "lioness", "mouse", "rat", "rodent", "rabbit", "bunny", "cat", "neko", "wolf", "lupine", "fox", "kitsune", "vulpine", "bear", "ursine", "bird", "avian", "dragon", "drake", "wyvern", "draconoid", "reptile", "snake", "serpent", "viper", "lizard", "gecko", "chameleon", "alligator", "crocodile"):
            if animal in clean:
                canonical = BEASTFOLK_ALIASES.get(animal, f"beastfolk:{animal}").split(":")[-1]
                prefix = "hybrid" if "hybrid" in clean else "half_beast"
                return f"{prefix}:{canonical}"
    # 3. Check explicit prefix
    if clean.startswith("half_beast:") or clean.startswith("hybrid:") or clean.startswith("halfbeast:"):
        return clean.replace(" ", "_")
    # 4. Longest-first alias matching
    for key, norm in sorted(HALF_BEAST_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if key in clean:
            if norm in ("half_beast", "hybrid") and seed:
                sub = resolve_generic_beastfolk_species(seed=seed)
                prefix = "hybrid" if "hybrid" in clean else "half_beast"
                return f"{prefix}:{sub}"
            return norm
    if clean in ("half_beast", "halfbeast", "hybrid", "demi_human", "beastkin"):
        if seed:
            sub = resolve_generic_beastfolk_species(seed=seed)
            prefix = "hybrid" if "hybrid" in clean else "half_beast"
            return f"{prefix}:{sub}"
        return clean
    if any(k in clean for k in ("half_beast", "halfbeast", "hybrid", "demi_human", "beastkin", "half_breed")):
        if seed:
            sub = resolve_generic_beastfolk_species(seed=seed)
            prefix = "hybrid" if "hybrid" in clean else "half_beast"
            return f"{prefix}:{sub}"
        return "half_beast"
    return None


def normalize_race(raw_race: str, scen_key: str = "fantasy", seed: str = "") -> str:
    """Normalizes raw race inputs against genre templates, enforcing human baseline defaults
    and restricting invalid races per genre.
    """
    from scenario_data import has_tag
    clean = (raw_race or "").strip().lower().replace("-", "_")

    # 1. Slice of Life / High School Drama: Strictly human only (except Furry variants)
    if has_tag(scen_key, "high_school") or has_tag(scen_key, "high_school_drama"):
        if has_tag(scen_key, "furry"):
            hb = resolve_half_beast(clean, seed=seed)
            if hb:
                return hb
            fam_sub = resolve_animal_family_species(clean, seed=seed)
            if fam_sub:
                return f"beastfolk:{fam_sub}"
            if clean in BEASTFOLK_ALIASES:
                return BEASTFOLK_ALIASES[clean]
            for key, norm in sorted(BEASTFOLK_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
                if key in clean:
                    return norm
            if clean.startswith("beastfolk") or clean.startswith("beast") or clean in ("anthro", "furry"):
                for fam_key in ANIMAL_FAMILY_SUBSPECIES:
                    if fam_key in clean:
                        sub = resolve_animal_family_species(fam_key, seed=seed)
                        return f"beastfolk:{sub}"
                if seed:
                    sub = resolve_generic_beastfolk_species(seed=seed)
                    return f"beastfolk:{sub}"
                return clean.replace(" ", "_")
            if clean and clean not in ("human", "default"):
                # Check general family in clean
                for fam_key in ANIMAL_FAMILY_SUBSPECIES:
                    if fam_key in clean:
                        sub = resolve_animal_family_species(fam_key, seed=seed)
                        return f"beastfolk:{sub}"
            # Code-enforced probability roll (80% Beastfolk [Cat 25%, Fox 22.5%, Wolf 22.5%, Minor 10%], 20% Human)
            if not clean:
                return random.choices(FURRY_HIGH_SCHOOL_RACES, weights=FURRY_HIGH_SCHOOL_WEIGHTS, k=1)[0]
            if clean == "human":
                return "human"
            return random.choices(FURRY_HIGH_SCHOOL_RACES, weights=FURRY_HIGH_SCHOOL_WEIGHTS, k=1)[0]
        elif clean and (clean in BEASTFOLK_ALIASES or resolve_half_beast(clean, seed=seed) or clean.startswith("beastfolk") or clean.startswith("half_beast") or clean in FANTASY_RACES):
            hb = resolve_half_beast(clean, seed=seed)
            if hb:
                return hb
            fam_sub = resolve_animal_family_species(clean, seed=seed)
            if fam_sub:
                return f"beastfolk:{fam_sub}"
            if clean in BEASTFOLK_ALIASES:
                return BEASTFOLK_ALIASES[clean]
            for key, norm in sorted(BEASTFOLK_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
                if key in clean:
                    return norm
            if clean.startswith("beastfolk"):
                return clean.replace(" ", "_")
            if clean in FANTASY_RACES:
                return FANTASY_RACES[clean]
            return clean
        else:
            return DEFAULT_RACE

    if not clean:
        return DEFAULT_RACE

    # 2. Space / Sci-Fi / Cyberpunk / Steampunk
    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi") or has_tag(scen_key, "cyberpunk") or has_tag(scen_key, "steampunk"):
        if clean in SCI_FI_RACES:
            return SCI_FI_RACES[clean]
        for key, norm in sorted(ALIEN_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if key in clean:
                return norm
        if clean.startswith("alien") or clean.startswith("automaton"):
            return clean.replace(" ", "_")
        # Restrict fantasy races -> default to human or synth
        if any(f_race in clean for f_race in ("elf", "dwarf", "goblin", "drow", "beastfolk")):
            return DEFAULT_RACE
        # Allow generic sci-fi/cyberpunk/steampunk species
        return clean[:30]

    # 3. Nuclear Post-Apocalypse
    if has_tag(scen_key, "post_apocalypse"):
        if clean in POST_APOC_RACES:
            return POST_APOC_RACES[clean]
        for key, norm in sorted(MUTANT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if key in clean:
                return norm
        if clean.startswith("mutant"):
            return clean.replace(" ", "_")
        # Restrict fantasy races -> default to human
        if any(f_race in clean for f_race in ("elf", "dwarf", "goblin", "drow", "beastfolk")):
            return DEFAULT_RACE
        # Allow generic post-apoc mutant/cyborg variant
        return clean[:30]

    # 4. Fantasy / Dark Fantasy / Isekai Fantasy (Default)
    hb = resolve_half_beast(clean, seed=seed)
    if hb:
        return hb

    fam_sub = resolve_animal_family_species(clean, seed=seed)
    if fam_sub:
        return f"beastfolk:{fam_sub}"

    if clean in FANTASY_RACES:
        return FANTASY_RACES[clean]

    if clean in BEASTFOLK_ALIASES:
        return BEASTFOLK_ALIASES[clean]

    for key, norm in sorted(BEASTFOLK_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if key in clean:
            return norm

    if clean.startswith("beastfolk") or clean.startswith("beast") or clean in ("anthro", "furry"):
        for fam_key in ANIMAL_FAMILY_SUBSPECIES:
            if fam_key in clean:
                sub = resolve_animal_family_species(fam_key, seed=seed)
                return f"beastfolk:{sub}"
        if seed:
            sub = resolve_generic_beastfolk_species(seed=seed)
            return f"beastfolk:{sub}"
        return clean.replace(" ", "_")

    # Restrict sci-fi aliens from fantasy
    if clean.startswith("alien") or clean in ("android", "synth"):
        return DEFAULT_RACE

    # Allow custom fantasy race (e.g. dryad, tiefling)
    return clean[:30]


def extract_race_from_text(text: str, scen_key: str = "fantasy", name: str = "") -> str | None:
    """Extracts and normalizes an NPC's race or species directly from narrative sentences or descriptions.
    If general animal family words (canine, canid, feline, felid, etc.) are present, randomly/deterministically
    resolves them to existing beastfolk subspecies (wolf, fox, fennec; cat, tiger, lion, cheetah) instead of
    always assigning to wolf and cat.
    """
    if not text or not isinstance(text, str):
        return None

    import re
    target_text = text
    if name and len(name) >= 3:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
        matching = [s for s in sentences if name.lower() in s.lower()]
        if matching:
            target_text = " ".join(matching)

    # 1. Check half-beast / hybrid indicators
    is_half = bool(re.search(r"\b(half[\s\-_]beast|half[\s\-_]breed|hybrid|demi[\s\-_]human|beastkin)\b", target_text, re.IGNORECASE))

    # 2. General animal families -> randomize across subspecies
    seed_str = name or target_text
    if re.search(r"\b(canines?|canids?|dogs?|hounds?)\b", target_text, re.IGNORECASE):
        sub = resolve_animal_family_species("canine", seed=seed_str)
        return f"half_beast:{sub}" if is_half else f"beastfolk:{sub}"

    if re.search(r"\b(felines?|felids?)\b", target_text, re.IGNORECASE):
        sub = resolve_animal_family_species("feline", seed=seed_str)
        return f"half_beast:{sub}" if is_half else f"beastfolk:{sub}"

    if re.search(r"\b(reptilians?|reptiles?|scaly|serpentines?)\b", target_text, re.IGNORECASE):
        sub = resolve_animal_family_species("reptile", seed=seed_str)
        return f"half_beast:{sub}" if is_half else f"beastfolk:{sub}"

    if re.search(r"\b(ursines?)\b", target_text, re.IGNORECASE):
        return "half_beast:bear" if is_half else "beastfolk:bear"

    if re.search(r"\b(murines?|rodents?)\b", target_text, re.IGNORECASE):
        return "half_beast:mouse" if is_half else "beastfolk:mouse"

    if re.search(r"\b(lagomorphs?|leporids?)\b", target_text, re.IGNORECASE):
        return "half_beast:rabbit" if is_half else "beastfolk:rabbit"

    if re.search(r"\b(avians?)\b", target_text, re.IGNORECASE):
        return "half_beast:bird" if is_half else "beastfolk:bird"

    # 3. Specific animal beastfolk/hybrid mentions
    SPECIFIC_ANIMAL_PATTERNS = [
        (r"\b(wolves|wolf|lupine)\b", "wolf"),
        (r"\b(foxes|fox|kitsune|vulpine)\b", "fox"),
        (r"\b(fennec)\b", "fennec"),
        (r"\b(tigers?|tigress)\b", "tiger"),
        (r"\b(lions?|lioness)\b", "lion"),
        (r"\b(cheetahs?)\b", "cheetah"),
        (r"\b(cats?|nekos?)\b", "cat"),
        (r"\b(bears?)\b", "bear"),
        (r"\b(rabbits?|bunnies|bunny|hares?)\b", "rabbit"),
        (r"\b(mice|mouse|rats?)\b", "mouse"),
        (r"\b(snakes?|serpents?|vipers?|cobras?|nagas?)\b", "snake"),
        (r"\b(dragons?|drakes?|wyverns?|draconic)\b", "dragon"),
        (r"\b(lizards?|geckos?|chameleons?|alligators?|crocodiles?)\b", "reptile"),
        (r"\b(birds?)\b", "bird"),
    ]
    for pat, spec in SPECIFIC_ANIMAL_PATTERNS:
        if re.search(pat, target_text, re.IGNORECASE):
            return f"half_beast:{spec}" if is_half else f"beastfolk:{spec}"

    # 4. Non-beastfolk fantasy & sci-fi races
    for f_race in ("dark elf", "dark_elf", "elf", "dwarf", "goblin", "orc", "gnome", "halfling", "cyborg", "android", "synth", "clone"):
        if re.search(rf"\b{f_race}\b", target_text, re.IGNORECASE):
            return normalize_race(f_race, scen_key=scen_key, seed=name)

    # 5. Explicit human
    if re.search(r"\b(human)\b", target_text, re.IGNORECASE):
        return "human"

    # 6. Generic beastfolk / anthro / furry / half-beast without a specific animal specified
    if is_half or re.search(r"\b(beastfolk|anthros?|furrys?|furries|beastkin|beast[\s\-_]person|demi[\s\-_]human)\b", target_text, re.IGNORECASE):
        sub = resolve_generic_beastfolk_species(seed=seed_str)
        return f"half_beast:{sub}" if is_half else f"beastfolk:{sub}"

    return None


def format_race_display(race_str: str) -> str:
    """Formats race codes into clean human-readable title strings for UI display."""
    if not race_str:
        return "Unknown"

    clean = race_str.strip().lower().replace("-", "_")
    if clean == "human":
        return "Human"
    if clean == "dark_elf":
        return "Dark Elf"
    if clean == "irradiated_human":
        return "Irradiated Human"
    if clean in ("half_beast", "halfbeast"):
        return "Half-Beast"
    if clean == "hybrid":
        return "Hybrid"

    if ":" in clean:
        category, species = clean.split(":", 1)
        cat_title = category.replace("_", " ").title()
        spec_title = species.replace("_", " ").title()
        if category in ("half_beast", "halfbeast"):
            return f"{spec_title} Half-Beast"
        if category == "hybrid":
            return f"{spec_title} Hybrid"
        return f"{spec_title}-{cat_title}"

    return clean.replace("_", " ").title()


def get_scenario_race_hint(scen_key: str = "fantasy") -> str:
    """Provides schema race hint string for LLM system prompt context."""
    from scenario_data import has_tag
    if has_tag(scen_key, "high_school") or has_tag(scen_key, "high_school_drama"):
        if has_tag(scen_key, "furry"):
            return (
                "beastfolk:cat|beastfolk:fox|beastfolk:wolf|beastfolk:fennec|beastfolk:tiger|beastfolk:cheetah|beastfolk:lion|"
                "beastfolk:mouse|beastfolk:rabbit|beastfolk:bear|beastfolk:bird|beastfolk:reptile|"
                "half_beast:cat|half_beast:fox|half_beast:wolf|half_beast:tiger|half_beast:lion|half_beast:cheetah|half_beast:fennec|half_beast:rabbit|half_beast:mouse|half_beast:bear|"
                "human (~60% Beastfolk [Cat 15%, Fox 15%, Canid/Feline 15%, Mouse/Rabbit 5%, Minor 10%], ~30% Half-Beast [Cat/Fox 20%, Other 10%], ~10% Human)"
            )
        return "human"
    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        return "human|android|synth|cyborg|clone|alien:<species>"
    if has_tag(scen_key, "cyberpunk"):
        return "human|cyborg|android|synth|augmented_human"
    if has_tag(scen_key, "steampunk"):
        return "human|clockwork_automaton|steam_cyborg|alchemist"
    if has_tag(scen_key, "post_apocalypse"):
        return "human|irradiated_human|cyborg|synth|mutant:<type>"
    return "human|elf|dwarf|dark_elf|goblin|beastfolk:<species>|half_beast:<species>|hybrid:<species>|string"
