from __future__ import annotations
import re
import random
from typing import Dict, Any, Tuple, Optional, List
import db
from skill_check import resolve_check

from .metadata import (
    POTION_PURPOSE_TAGS,
    POTION_EFFECT_TAGS,
    FOOD_TASTE_TAGS,
    FOOD_EFFECT_TAGS,
    DRINK_TASTE_TAGS,
    DRINK_EFFECT_TAGS,
    POTION_SCALING,
    FOOD_SCALING,
    DRINK_SCALING,
    serialize_consumable_metadata,
    parse_consumable_metadata,
    serialize_digital_item_metadata,
    parse_digital_item_metadata,
    is_digital_item,
    create_digital_media_item,
    normalize_consumable_scenario,
    parse_item_tier,
    is_key_item,
    is_giftable_item,
    parse_item_effect,
)


def generate_potion_name(genre: str, tier: int, effect_tags: List[str], purpose_tags: List[str]) -> str:
    """Dynamically generates evocative potion names based on genre, tier, and effect combinations."""
    scen = normalize_consumable_scenario(genre)

    # 1. Steampunk / Victorian Clockwork naming
    if scen == "steampunk":
        t3_prefixes = ["Standard", "Brass-Capped", "Copper", "Apothecary's", "Diluted", "Aetheric"]
        t2_prefixes = ["Galvanic", "Refined", "Pressurized", "Pneumatic", "Aetheric", "Voltaic"]
        t1_prefixes = ["Grand Victorian", "Master Artificer's", "Aether-Sovereign", "Perpetual-Motion", "Imperial"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))
        form = random.choice(["Inhaler", "Ampoule", "Tonic", "Tincture", "Flask", "Phial"])

        if "explosive_fire" in effect_tags:
            return f"{prefix} Phlogiston Fire Bomb" if tier <= 2 else "Perpetual Steam-Core Detonator"
        if "corrosive_acid" in effect_tags:
            return f"{prefix} Caustic Vitriol Canister"
        if "toxic_cloud" in effect_tags:
            return f"{prefix} Chlorine Vapor Flask"
        if "cleanse_all" in effect_tags or "cure_poison" in effect_tags:
            return "Grand Panacea of the Royal College" if tier == 1 else (f"{prefix} Galvanic Resuscitation Salts" if "cleanse_all" in effect_tags else f"{prefix} Carbolic Antidote Phial")

        if "healing" in effect_tags and "attack_buff" in effect_tags:
            return f"{prefix} Boiler-Charge Adrenaline Inhaler"
        if "healing" in effect_tags and "defense_buff" in effect_tags:
            return f"{prefix} Brass-Coagulant Tonic"
        if "healing" in effect_tags and "evasion_buff" in effect_tags:
            return f"{prefix} Clockwork Mercurial Draught"
        if "healing" in effect_tags:
            return "Aether-Sovereign Elixir of Life" if tier == 1 else f"{prefix} Tincture of Laudanum"
        if "mana_restore" in effect_tags:
            return "Imperial Aether-Capacitor Core" if tier == 1 else f"{prefix} Galvanic Aether Phial"
        if "attack_buff" in effect_tags:
            return f"{prefix} Boiler-Surge Vapor Inhaler"
        if "defense_buff" in effect_tags:
            return f"{prefix} Brasshide Plating Tonic"
        if "resistance_buff" in effect_tags:
            return f"{prefix} Insulating Voltaic Salve"
        if "evasion_buff" in effect_tags:
            return f"{prefix} Steam-Dash Inhaler"
        if "charisma_buff" in effect_tags:
            return f"{prefix} Dapper Gentleman's Smelling Salts"
        return f"{prefix} Alchemical Vapor {form}"

    # 2. Nuclear Post-Apocalypse / Wasteland naming
    elif scen == "post_apocalyptic":
        t3_prefixes = ["Makeshift", "Scavenged", "Dirty", "Crude", "Wasteland", "Filtered"]
        t2_prefixes = ["Pre-War", "Purified", "Rad-Shielded", "Enriched", "Distilled", "Military-Surplus"]
        t1_prefixes = ["Pristine Vault-Tec", "Apex Mutagen", "Project Purity", "Pre-Collapse Wonder", "G.E.C.K.-Infused"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))
        form = random.choice(["Auto-Injector", "Chem-Draught", "Inhaler", "Scrap-Vial", "Filter Salve", "Patch"])

        if "explosive_fire" in effect_tags:
            return f"{prefix} Molotov Cocktail" if tier >= 2 else "Crude Bottle Bomb"
        if "corrosive_acid" in effect_tags:
            return f"{prefix} Irradiated Acid Bottle"
        if "toxic_cloud" in effect_tags:
            return f"{prefix} Rad-Contagion Canister"
        if "cleanse_all" in effect_tags or "cure_poison" in effect_tags:
            return "Pristine Vault-Tec Rad-Away Flush" if tier == 1 else (f"{prefix} Rad-Away Flush Ampoule" if "cleanse_all" in effect_tags else f"{prefix} Activated Charcoal Pill")

        if "healing" in effect_tags and "attack_buff" in effect_tags:
            return f"{prefix} Psycho-Stim Auto-Injector"
        if "healing" in effect_tags and "defense_buff" in effect_tags:
            return f"{prefix} Rad-Hardened Medkit"
        if "healing" in effect_tags and "evasion_buff" in effect_tags:
            return f"{prefix} Jet-Adrenaline Inhaler"
        if "healing" in effect_tags:
            return "Pristine Super-Stimpak" if tier == 1 else (f"{prefix} Stimpak Auto-Injector" if tier == 2 else f"{prefix} Makeshift Suture Gel")
        if "mana_restore" in effect_tags:
            return "Project Purity Bio-Cell" if tier == 1 else f"{prefix} Rad-Cell Charge Capsule"
        if "attack_buff" in effect_tags:
            return f"{prefix} Berserk Psycho Inhaler"
        if "defense_buff" in effect_tags:
            return f"{prefix} Hardened Carapace Serum"
        if "resistance_buff" in effect_tags:
            return f"{prefix} Rad-X Shielding Pills"
        if "evasion_buff" in effect_tags:
            return f"{prefix} Turbo-Dash Chem Inhaler"
        if "charisma_buff" in effect_tags:
            return f"{prefix} Smooth-Skin Pheromone Chew"
        return f"{prefix} Chem-Stim {form}"

    # 3. Dark Fantasy / Eldritch / Gothic naming
    elif scen == "dark_fantasy":
        t3_prefixes = ["Tainted", "Ashen", "Haggard", "Grave-Dusted", "Crude", "Bitter"]
        t2_prefixes = ["Blood-Forged", "Occult", "Blight-Hardened", "Eldritch", "Corrupted", "Shadow-Bound"]
        t1_prefixes = ["Abyssal Sovereign", "Primordial Blood", "Ancient Lich-Lord's", "Eldritch God's", "Soul-Harvested"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))
        form = random.choice(["Blood Vial", "Sacramental Phial", "Eldritch Draught", "Bone Urn", "Leeching Salve"])

        if "explosive_fire" in effect_tags:
            return f"{prefix} Abyssal Hellfire Flask" if tier <= 2 else "Primordial Void-Fire Urn"
        if "corrosive_acid" in effect_tags:
            return f"{prefix} Black Vitriol Urn"
        if "toxic_cloud" in effect_tags:
            return f"{prefix} Corpse-Gas Miasma"
        if "cleanse_all" in effect_tags or "cure_poison" in effect_tags:
            return "Sacramental Panacea of the High Martyr" if tier == 1 else (f"{prefix} Sanctified Ashen Water" if "cleanse_all" in effect_tags else f"{prefix} Leeching Antidote Salve")

        if "healing" in effect_tags and "attack_buff" in effect_tags:
            return f"{prefix} Berserk Sanguine Draught"
        if "healing" in effect_tags and "defense_buff" in effect_tags:
            return f"{prefix} Ossuary Bone-Marrow Salve"
        if "healing" in effect_tags and "evasion_buff" in effect_tags:
            return f"{prefix} Phantom Mist Draught"
        if "healing" in effect_tags:
            return "Primordial Blood Chalice" if tier == 1 else f"{prefix} Coagulated Blood Vial"
        if "mana_restore" in effect_tags:
            return "Abyssal Void-Essence Vessel" if tier == 1 else f"{prefix} Spirit Marrow Draught"
        if "attack_buff" in effect_tags:
            return f"{prefix} Beast-Blood Pellet"
        if "defense_buff" in effect_tags:
            return f"{prefix} Gravetallow Flesh-Shielding"
        if "resistance_buff" in effect_tags:
            return f"{prefix} Shadow-Ward Holy Water"
        if "evasion_buff" in effect_tags:
            return f"{prefix} Wraith-Form Philter"
        if "charisma_buff" in effect_tags:
            return f"{prefix} Vampire's Seductive Draught"
        return f"{prefix} Necromantic Concoction"

    # 4. Cyberpunk & Sci-Fi naming
    elif scen == "cyberpunk":
        t3_prefixes = ["Standard", "Street-Grade", "Over-the-Counter", "Basic", "Synthetic"]
        t2_prefixes = ["Military-Grade", "Overclocked", "Reinforced", "Enhanced", "Synaptic", "High-Potency"]
        t1_prefixes = ["Black-Market Prototype", "Militech Black-Ops", "Apex Cybernetic", "Nano-Singularity", "Ghost-Protocol"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))
        form = random.choice(["Stim", "Injector", "Ampoule", "Serum", "Canister"])

        if "explosive_fire" in effect_tags or "throwable" in purpose_tags:
            return f"{prefix} Plasma Incendiary Grenade" if tier == 1 else f"{prefix} Thermal Flask"
        if "corrosive_acid" in effect_tags:
            return f"{prefix} Nanite Corrosive Ampoule"
        if "toxic_cloud" in effect_tags:
            return f"{prefix} Neurotoxin Aerosol Grenade"
        if "cleanse_all" in effect_tags or "cure_poison" in effect_tags:
            return "Militech Apex Detox Nanites" if tier == 1 else (f"{prefix} Bio-Cleanse Filter Ampoule" if "cleanse_all" in effect_tags else f"{prefix} Antitoxin Medi-Patch")

        if "healing" in effect_tags and "attack_buff" in effect_tags:
            return f"Overclocked Adrenaline {form}" if tier >= 2 else f"Combat Booster {form}"
        if "healing" in effect_tags and "defense_buff" in effect_tags:
            return f"Nanite Armor Weave {form}"
        if "healing" in effect_tags and "evasion_buff" in effect_tags:
            return f"Reflex Overdrive {form}"
        if "healing" in effect_tags:
            return f"Medical Nanite {form}" if tier >= 2 else f"{prefix} Medi-Patch {form}"
        if "mana_restore" in effect_tags:
            return f"Capacitance Bio-Cell {form}"
        if "attack_buff" in effect_tags:
            return f"Synaptic Hyper-Drive {form}"
        if "defense_buff" in effect_tags:
            return f"Dermal Plating {form}"
        if "resistance_buff" in effect_tags:
            return f"Subdermal Forcefield {form}"
        if "evasion_buff" in effect_tags:
            return f"Neural Acceleration {form}"
        if "charisma_buff" in effect_tags:
            return f"Pheromone Modulation {form}"
        return f"{prefix} Neuro-Stim {form}"

    # 5. High School & Modern Drama naming
    elif scen == "high_school":
        t3_prefixes = ["Daily", "Convenience Store", "Basic", "Sports", "Fresh"]
        t2_prefixes = ["Deluxe", "Premium", "Artisanal", "Imported", "Special Reserve"]
        t1_prefixes = ["Doctor's Secret", "Champion's Gold", "Legendary Gourmet", "Grand Festival Prize"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))

        if "healing" in effect_tags and "charisma_buff" in effect_tags:
            return "Deluxe Ginseng Glow Energy Drink" if tier >= 2 else "Vitamin Radiance Drink"
        if "healing" in effect_tags:
            return "Doctor's Restorative Vitamin Drink" if tier == 1 else (f"{prefix} Energy Recovery Drink" if tier == 2 else "Sports Electrolyte Drink")
        if "mana_restore" in effect_tags:
            return "Premium Matcha Focus Shot" if tier >= 2 else "Caffeine Focus Tonic"
        if "attack_buff" in effect_tags:
            return f"{prefix} Taurine Energy Booster"
        if "defense_buff" in effect_tags:
            return f"{prefix} Immune Defense Chew"
        if "evasion_buff" in effect_tags:
            return f"{prefix} Minty Alert Chewable"
        if "charisma_buff" in effect_tags:
            return "Honey Floral Breath Freshener Spray"
        return f"{prefix} Wellness Tonic"

    # 6. Fantasy & Default naming
    else:
        t3_prefixes = ["Lesser", "Minor", "Basic", "Standard", "Simple"]
        t2_prefixes = ["Potent", "Greater", "Superior", "Enhanced", "Reinforced", "Refined"]
        t1_prefixes = ["Supreme", "Legendary", "Mythic", "Primordial", "Celestial", "Archmage's", "Divine"]
        prefix = random.choice(t3_prefixes if tier == 3 else (t2_prefixes if tier == 2 else t1_prefixes))

        if "explosive_fire" in effect_tags:
            return f"{prefix} Dragonfire Flask" if tier <= 2 else "Primordial Hellfire Core"
        if "corrosive_acid" in effect_tags:
            return f"{prefix} Acidic Vial"
        if "toxic_cloud" in effect_tags:
            return f"{prefix} Nightshade Miasma"
        if "cleanse_all" in effect_tags or "cure_poison" in effect_tags:
            return "Panacea of Renewal" if tier == 1 else (f"{prefix} Herbal Antidote" if "cure_poison" in effect_tags else f"{prefix} Restorative Salve")

        # Multi-effect combos
        if "healing" in effect_tags and "attack_buff" in effect_tags:
            return "Warlord's Rejuvenating Draught" if tier >= 2 else "Soldier's Vitality Brew"
        if "healing" in effect_tags and "defense_buff" in effect_tags:
            return "Ironbark Elixir of Fortitude" if tier >= 2 else "Stoutheart Tonic"
        if "healing" in effect_tags and "evasion_buff" in effect_tags:
            return "Zephyr's Swift Draught"
        if "healing" in effect_tags:
            return "Elixir of Rebirth" if tier == 1 else f"{prefix} Healing Potion"
        if "mana_restore" in effect_tags:
            return "Primordial Aether Vial" if tier == 1 else f"{prefix} Mana Elixir"
        if "attack_buff" in effect_tags:
            return f"{prefix} Berserker's Draught"
        if "defense_buff" in effect_tags:
            return f"{prefix} Iron Skin Elixir"
        if "resistance_buff" in effect_tags:
            return f"{prefix} Elixir of Aegis Warding"
        if "evasion_buff" in effect_tags:
            return f"{prefix} Quickstep Phial"
        if "charisma_buff" in effect_tags:
            return f"{prefix} Alluring Philter"
        return f"{prefix} Alchemical Draught"


def generate_food_name(genre: str, tier: int, taste_tags: List[str], effect_tags: List[str]) -> str:
    """Dynamically generates culinary solid food names based on genre, tier, and taste profile."""
    scen = normalize_consumable_scenario(genre)

    # 1. High School / Modern
    if scen == "high_school":
        t3_adjs = ["Fresh", "Warm", "Crispy", "Street-Style", "Daily", "Homestyle"]
        t2_adjs = ["Artisanal", "Deluxe", "Gourmet", "Hearty", "Slow-Roasted", "Handcrafted"]
        t1_adjs = ["Royal", "Celestial", "Grand Banquet", "Master Chef's", "Legendary", "Imperial"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "sweet" in taste_tags or "bakery" in taste_tags:
            if tier == 1: return f"{adj} Triple-Layer Berry Celebration Cake"
            if tier == 2: return f"{adj} Strawberry Parfait"
            return "Matcha Melon Pan"
        if "spicy" in taste_tags:
            if tier == 1: return f"{adj} Szechuan Chili Hotpot Feast"
            if tier == 2: return f"{adj} Spicy Kimchi Fried Rice"
            return "Spicy Chili Noodles"
        if "vegetarian" in taste_tags or "comfort" in taste_tags:
            if tier == 1: return f"{adj} Organic Garden Omakase"
            if tier == 2: return f"{adj} Avocado & Tamagoyaki Rice Bowl"
            return "Homestyle Onigiri Rice Ball"
        if "savory" in taste_tags or "meat" in taste_tags or "crispy" in taste_tags:
            if tier == 1: return f"{adj} Omakase Wagyu Course"
            if tier == 2: return f"{adj} Special Tonkatsu Bento Box"
            return "Crispy Pork Cutlet Sandwich"
        return f"{adj} Campus Bento Lunch"

    # 2. Cyberpunk / Sci-Fi
    elif scen == "cyberpunk":
        t3_adjs = ["Synthetic", "Neon", "Street-Grade", "Quick-Prep", "Crispy"]
        t2_adjs = ["Artisanal", "Deluxe", "Gourmet", "Bio-Engineered", "Enhanced"]
        t1_adjs = ["Pristine Non-Synthetic", "Apex Executive", "Master Chef's", "Imperial"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "luxury" in taste_tags or tier == 1:
            return "Pristine Non-Synthetic Wagyu Steak"
        if "sweet" in taste_tags or "bakery" in taste_tags:
            return f"{adj} Holographic Glaze Mochi"
        if "spicy" in taste_tags:
            return f"{adj} Neon Red Chili Dumplings"
        if "savory" in taste_tags or "meat" in taste_tags:
            return f"{adj} Neo-Shinjuku Street Cart Ramen"
        return f"{adj} Synth-Protein Nutri-Meal"

    # 3. Steampunk / Victorian Clockwork
    elif scen == "steampunk":
        t3_adjs = ["Boiler-Baked", "Stoker's", "Street-Cart", "Apothecary's", "Warm", "Hearty"]
        t2_adjs = ["Artisanal", "Victorian", "Gourmet", "Aether-Smoked", "Copper-Roasted", "Handcrafted"]
        t1_adjs = ["Grand Victorian", "Master Artificer's", "Imperial Guild", "Royal Banquet", "Dreadnought"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "sweet" in taste_tags or "bakery" in taste_tags:
            if tier == 1: return f"{adj} Victoria Sponge & Glazed Tart"
            if tier == 2: return f"{adj} Warm Treacle Pudding"
            return f"{adj} Currant Bun"
        if "seafood" in taste_tags:
            if tier == 1: return f"{adj} Dockside Lobster Course"
            if tier == 2: return f"{adj} Smoked Kipper Toast"
            return f"{adj} Crispy Fried Whitefish Skewer"
        if "spicy" in taste_tags:
            if tier == 1: return f"{adj} Bengal Spiced Mutton Roast"
            if tier == 2: return f"{adj} Peppered Beef Stew with Dumplings"
            return f"{adj} Spicy Mustard Sausage Skewer"
        if "savory" in taste_tags or "meat" in taste_tags:
            if tier == 1: return f"{adj} Prime Beef Wellington Banquet"
            if tier == 2: return f"{adj} Mutton & Potato Hand Pie"
            return f"{adj} Boiler-Baked Meat Pie"
        return f"{adj} Master Artificer's Feast" if tier == 1 else (f"{adj} High-Society Dinner Platter" if tier == 2 else f"{adj} Stoker's Pressed Hardtack")

    # 4. Nuclear Post-Apocalypse / Wasteland
    elif scen == "post_apocalyptic":
        t3_adjs = ["Charred", "Scavenged", "Dirty", "Makeshift", "Crispy", "Campfire"]
        t2_adjs = ["Smoked", "Purified", "Pre-War", "Enriched", "Slow-Roasted", "Hearty"]
        t1_adjs = ["Pristine Vault-Tec", "Apex Hunter's", "Project Purity", "Wonder-Grade", "Legendary"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "sweet" in taste_tags or "bakery" in taste_tags:
            if tier == 1: return f"{adj} Preserved Fancy Lads Snack Cakes"
            if tier == 2: return f"{adj} Glazed Yum-Yum Roll"
            return f"{adj} Sugar Bombs Cereal Treat"
        if "seafood" in taste_tags:
            if tier == 1: return f"{adj} Softshell Mirelurk King Feast"
            if tier == 2: return f"{adj} Smoked Mirelurk Crab Patty"
            return f"{adj} Crispy River Carp Skewer"
        if "spicy" in taste_tags:
            if tier == 1: return f"{adj} Fire-Ant Hot Pepper Roast"
            if tier == 2: return f"{adj} Spiced Molerat Belly Skewer"
            return f"{adj} Chili Powder Rad-Jerky Skewer"
        if "savory" in taste_tags or "meat" in taste_tags:
            if tier == 1: return f"{adj} Prime Brahmin Tenderloin Platter"
            if tier == 2: return f"{adj} Slow-Cooked Brahmin Stew with Dumplings"
            return f"{adj} Charred Rad-Roach Skewer"
        return f"{adj} Vault-Tec Emergency Banquet" if tier == 1 else (f"{adj} Canned Mystery Meat Loaf" if tier == 2 else f"{adj} Dirty Ash-Baked Cornbread")

    # 5. Dark Fantasy / Eldritch / Gothic
    elif scen == "dark_fantasy":
        t3_adjs = ["Ashen", "Tainted", "Salted", "Grave-Dusted", "Crude", "Coarse"]
        t2_adjs = ["Blood-Forged", "Smoked", "Occult", "Hearty", "Slow-Roasted", "Savory"]
        t1_adjs = ["Abyssal Banquet", "Primordial", "Eldritch", "Grand Sacramental", "Ancient King's"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "sweet" in taste_tags or "bakery" in taste_tags:
            if tier == 1: return f"{adj} Ambrosial Honeycomb Loaf"
            if tier == 2: return f"{adj} Spiced Blackcurrant Tart"
            return f"{adj} Coarse Black Rye Loaf"
        if "seafood" in taste_tags:
            if tier == 1: return f"{adj} Abyssal Kraken Tenderloin"
            if tier == 2: return f"{adj} Salt-Cured Cave Eel"
            return f"{adj} Dried River Leech Skewer"
        if "spicy" in taste_tags:
            if tier == 1: return f"{adj} Brimstone Spiced Beast Roast"
            if tier == 2: return f"{adj} Fiery Cinder-Goulash Stew"
            return f"{adj} Spiced Cinder Jerky Skewer"
        if "savory" in taste_tags or "meat" in taste_tags:
            if tier == 1: return f"{adj} Grand Dragon-Marrow Banquet"
            if tier == 2: return f"{adj} Spiced Black Blood Sausage"
            return f"{adj} Smoked Venison Jerky Skewer"
        return f"{adj} Abyssal Lord's Sacrificial Feast" if tier == 1 else (f"{adj} Turnip & Bone Marrow Porridge" if tier == 2 else f"{adj} Ash-Baked Hardtack Biscuit")

    # 6. Fantasy & Default
    else:
        t3_adjs = ["Fresh", "Warm", "Crispy", "Street-Style", "Daily", "Homestyle"]
        t2_adjs = ["Artisanal", "Deluxe", "Gourmet", "Hearty", "Slow-Roasted", "Handcrafted"]
        t1_adjs = ["Royal", "Celestial", "Grand Banquet", "Master Chef's", "Legendary", "Imperial"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "sweet" in taste_tags or "bakery" in taste_tags:
            if tier == 1: return "Celestial Ambrosia & Honey Feast"
            if tier == 2: return f"{adj} Glazed Honey Apple Tart"
            return "Sweet Cinnamon Roll"
        if "seafood" in taste_tags:
            if tier == 1: return "Abyssal King Crab Feast"
            if tier == 2: return f"{adj} Grilled River Trout with Herbs"
            return "Crispy Salted Fish Skewer"
        if "spicy" in taste_tags:
            if tier == 1: return f"{adj} Fire Drake Pepper Roast"
            if tier == 2: return f"{adj} Spiced Mountain Stew"
            return "Spicy Jerky Skewer"
        if "savory" in taste_tags or "meat" in taste_tags:
            if tier == 1: return "Grand Dragonfire Banquet Platter"
            if tier == 2: return f"{adj} Roast Boar Stew with Dumplings"
            return "Smoked Sausage & Bread Skewer"
        return f"{adj} Traveler's Hearty Feast" if tier == 1 else (f"{adj} Tavern Meal" if tier == 2 else "Traveler's Ration")


def generate_drink_name(genre: str, tier: int, taste_tags: List[str], effect_tags: List[str]) -> str:
    """Dynamically generates evocative drink and beverage names based on genre, tier, and beverage profile."""
    scen = normalize_consumable_scenario(genre)

    # 1. High School / Modern
    if scen == "high_school":
        t3_adjs = ["Chilled", "Fresh", "Sparkling", "Iced", "Steaming", "Crisp"]
        t2_adjs = ["Artisanal", "Handcrafted", "Cold-Pressed", "Aged", "Infused", "Signature"]
        t1_adjs = ["Grand Cru", "Vintage", "Celestial", "Master Blend", "Imperial", "Pristine"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "boba" in taste_tags or ("tea" in taste_tags and "sweet" in taste_tags):
            if tier == 1: return f"{adj} Golden Supreme Milk Tea"
            if tier == 2: return f"{adj} Iced Brown Sugar Boba Latte"
            return "Classic Roasted Milk Tea"
        if "coffee" in taste_tags or "caffeine" in taste_tags:
            if tier == 1: return f"{adj} Single-Origin Geisha Pour-Over"
            if tier == 2: return f"{adj} Vanilla Bean Nitro Cold Brew"
            return "Chilled Canned Black Coffee"
        if "tea" in taste_tags or "herbal" in taste_tags:
            if tier == 1: return f"{adj} Imperial Gyokuro Green Tea"
            if tier == 2: return f"{adj} Honey Citrus Jasmine Green Tea"
            return "Iced Oolong Tea"
        if "soda" in taste_tags or "fizzy" in taste_tags:
            if tier == 2: return f"{adj} Blue Lagoon Sparkling Mocktail"
            return "Fizzy Marble Ramune Soda"
        if "smoothie" in taste_tags or "juice" in taste_tags or "citrus" in taste_tags:
            if tier == 1: return f"{adj} Golden Mango Dragonfruit Smoothie"
            if tier == 2: return f"{adj} Strawberry Banana Smoothie"
            return "Fresh Squeezed Orange Juice"
        return f"{adj} Sport Electrolyte Drink"

    # 2. Cyberpunk / Sci-Fi
    elif scen == "cyberpunk":
        t3_adjs = ["Chilled", "Neon", "Street-Grade", "Carbonated", "Crisp"]
        t2_adjs = ["Artisanal", "Synthesized", "High-Proof", "Cold-Pressed", "Infused"]
        t1_adjs = ["Pre-Collapse", "Apex Executive", "Master Blend", "Pristine"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "alcohol" in taste_tags:
            if tier == 1: return "Pre-Collapse Vintage Scotch"
            if tier == 2: return f"{adj} Synthehol Vodka Shot"
            return "Neon Blue Cocktail Can"
        if "caffeine" in taste_tags or "coffee" in taste_tags:
            if tier == 1: return f"{adj} Neuro-Overclock Hyper-Espresso"
            if tier == 2: return f"{adj} Synaptic Focus Bio-Brew"
            return "Stim-Caf Double Shot"
        if "fizzy" in taste_tags or "soda" in taste_tags:
            if tier == 2: return f"{adj} Bioluminescent Blue Lagoon Cordial"
            return "Neon Spark Energy Fizz"
        if "infused_water" in taste_tags or "refreshing" in taste_tags or tier == 1:
            return "Pristine Glacial Artesian Water"
        return f"{adj} Synth-Electrolyte Hydrator"

    # 3. Steampunk / Victorian Clockwork
    elif scen == "steampunk":
        t3_adjs = ["Chilled", "Steaming", "Brass-Filtered", "Copper-Stilled", "Fresh", "Crisp"]
        t2_adjs = ["Artisanal", "Pressurized", "Aether-Infused", "Aged", "High-Society", "Signature"]
        t1_adjs = ["Grand Victorian", "Imperial Reserve", "Master Artificer's", "Royal Academy", "Celestial"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "caffeine" in taste_tags or "coffee" in taste_tags:
            if tier == 1: return f"{adj} High-Pressure Steam Espresso"
            if tier == 2: return f"{adj} Dark-Brew Coal-Burner Coffee"
            return f"{adj} Barometer Black Coffee"
        if "tea" in taste_tags or "herbal" in taste_tags:
            if tier == 1: return f"{adj} Imperial Earl Grey Bergamot Infusion"
            if tier == 2: return f"{adj} Aether-Steeped Jasmine Tea"
            return f"{adj} Copper-Kettle Peppermint Tea"
        if "alcohol" in taste_tags:
            if tier == 1: return f"{adj} Green Fairy Bohemian Absinthe"
            if tier == 2: return f"{adj} Copper-Stilled London Dry Gin"
            return f"{adj} Old Dockyard Dark Ale"
        if "soda" in taste_tags or "fizzy" in taste_tags:
            if tier == 2: return f"{adj} Carbonated Seltzer Punch"
            return f"{adj} Sarsaparilla Effervescent Fizz"
        return f"{adj} Royal Aether Nectar Chalice" if tier == 1 else (f"{adj} Boiler-Filtered Tonic" if tier == 2 else f"{adj} Boiler-Filtered Mineral Water")

    # 4. Nuclear Post-Apocalypse / Wasteland
    elif scen == "post_apocalyptic":
        t3_adjs = ["Dirty", "Scavenged", "Makeshift", "Filtered", "Rusty", "Chilled"]
        t2_adjs = ["Purified", "Pre-War", "Enriched", "Aged", "Distilled", "Cold-Pressed"]
        t1_adjs = ["Pristine Vault-Tec", "Project Purity", "Pre-Collapse Vintage", "G.E.C.K.-Purified"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "soda" in taste_tags or "fizzy" in taste_tags:
            if tier == 1: return f"{adj} Radioactive Quantum Cola"
            if tier == 2: return f"{adj} Atomic Fizz Soda"
            return f"{adj} Flat Warm Atomic Soda"
        if "alcohol" in taste_tags:
            if tier == 1: return f"{adj} Pre-War Sealed Bourbon"
            if tier == 2: return f"{adj} Fermented Molerat Moonshine"
            return f"{adj} Scrap-Stilled Radiated Whiskey"
        if "caffeine" in taste_tags or "coffee" in taste_tags:
            if tier == 1: return f"{adj} Vacuum-Sealed Pre-War Coffee"
            if tier == 2: return f"{adj} Rad-Scrap Percolator Coffee"
            return f"{adj} Instant Chicory Black Coffee"
        if "tea" in taste_tags or "herbal" in taste_tags:
            if tier == 2: return f"{adj} Boiled Mut-Fruit Herbal Infusion"
            return f"{adj} Desolation Sage Herbal Brew"
        if "refreshing" in taste_tags or "infused_water" in taste_tags or tier == 1:
            return f"{adj} Untouched Artesian Spring Water"
        if tier == 2:
            return f"{adj} Purified Canteen Water"
        return f"{adj} Filtered Scrap-Bucket Water"

    # 5. Dark Fantasy / Eldritch / Gothic
    elif scen == "dark_fantasy":
        t3_adjs = ["Murky", "Bitter", "Sour", "Ashen", "Chilled", "Rough"]
        t2_adjs = ["Blood-Forged", "Aged", "Infused", "Sacramental", "Occult", "Vintage"]
        t1_adjs = ["Abyssal Sovereign", "Primordial", "Grand Vintage", "Ancient Lich-King's", "Celestial Chalice"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "alcohol" in taste_tags:
            if tier == 1: return f"{adj} Crimson Sacrificial Blood Wine"
            if tier == 2: return f"{adj} Aged Dwarven Fire Ale"
            return f"{adj} Sour Graveyard Mead"
        if "tea" in taste_tags or "herbal" in taste_tags:
            if tier == 1: return f"{adj} Celestial Moonflower Herbal Infusion"
            if tier == 2: return f"{adj} Dried Hemlock & Nightshade Tea"
            return f"{adj} Bitter Marrow-Root Brew"
        if "sweet" in taste_tags or "dairy" in taste_tags:
            if tier == 1: return f"{adj} Ambrosial Honey Nectar Chalice"
            if tier == 2: return f"{adj} Spiced Goat Milk with Cinnamon"
            return f"{adj} Curdled Warm Milk"
        if "citrus" in taste_tags or "refreshing" in taste_tags:
            if tier == 2: return f"{adj} Wild Mountain Berry Cordial"
            return f"{adj} Sour Blackcurrant Cordial"
        return f"{adj} Primordial Nectar Draught" if tier == 1 else (f"{adj} Sanctified Holy Cathedral Spring Water" if tier == 2 else f"{adj} Murky Crypt Well Water")

    # 6. Fantasy & Default
    else:
        t3_adjs = ["Chilled", "Fresh", "Sparkling", "Iced", "Steaming", "Crisp"]
        t2_adjs = ["Artisanal", "Handcrafted", "Cold-Pressed", "Aged", "Infused", "Signature"]
        t1_adjs = ["Grand Cru", "Vintage", "Celestial", "Master Blend", "Imperial", "Pristine"]
        adj = random.choice(t3_adjs if tier == 3 else (t2_adjs if tier == 2 else t1_adjs))

        if "alcohol" in taste_tags:
            if tier == 1: return "Vintage Elven Sun-Nectar Wine"
            if tier == 2: return "Aged Dwarven Fire Ale"
            return "Tavern Mug of Spiced Cider"
        if "tea" in taste_tags or "herbal" in taste_tags:
            if tier == 1: return "Celestial Starlight Herbal Infusion"
            if tier == 2: return f"{adj} Moonflower Blossom Tea"
            return "Soothing Chamomile Brew"
        if "sweet" in taste_tags or "dairy" in taste_tags:
            if tier == 1: return "Ambrosial Honey Nectar Chalice"
            if tier == 2: return f"{adj} Sweet Spiced Honeyed Mead"
            return "Warm Spiced Milk"
        if "citrus" in taste_tags or "refreshing" in taste_tags or "juice" in taste_tags:
            if tier == 2: return f"{adj} Mountain Berry Cordial"
            return "Fresh Pressed Orchard Apple Juice"

        return f"{adj} Spring Water Flagon" if tier == 3 else (f"{adj} Tavern Spiced Ale" if tier == 2 else "Celestial Nectar Draught")


# -----------------------------------------------------------------------------
# PROCEDURAL CONSUMABLE GENERATORS
# -----------------------------------------------------------------------------

def generate_procedural_potion(tier: int = 3, effect_tags: List[str] = None, genre: str = "fantasy") -> Dict[str, Any]:
    """
    Generates a structured, deterministic potion with explicit purpose tags,
    effect tags, numeric values, and genre-based name.
    """
    if effect_tags is None:
        if tier == 3:
            effect_tags = random.choice([["healing"], ["mana_restore"], ["cure_poison"], ["attack_buff"], ["explosive_fire"]])
        elif tier == 2:
            effect_tags = random.choice([
                ["healing", "attack_buff"],
                ["healing", "defense_buff"],
                ["mana_restore", "evasion_buff"],
                ["healing", "cure_poison"],
                ["explosive_fire"],
                ["corrosive_acid"]
            ])
        else:
            effect_tags = random.choice([
                ["healing", "cleanse_all"],
                ["healing", "attack_buff", "defense_buff"],
                ["mana_restore", "healing", "cleanse_all"],
                ["explosive_fire"]
            ])

    purpose_tags = []
    if any(k in effect_tags for k in ["healing", "cleanse_all", "cure_poison", "cure_bleed", "cure_burn"]):
        purpose_tags.append("health")
    if "mana_restore" in effect_tags:
        purpose_tags.append("mana")
    if any("buff" in k for k in effect_tags):
        purpose_tags.append("buff")
    if any(k in effect_tags for k in ["explosive_fire", "corrosive_acid", "toxic_cloud"]):
        purpose_tags.extend(["throwable", "debuff"])
    if not purpose_tags:
        purpose_tags.append("utility")

    # Calculate numeric values
    hp_val = POTION_SCALING["healing"][tier] if "healing" in effect_tags else 0
    mp_val = POTION_SCALING["mana_restore"][tier] if "mana_restore" in effect_tags else 0
    
    buffs = {}
    if "attack_buff" in effect_tags: buffs["atk_pct"] = POTION_SCALING["attack_buff"][tier]
    if "defense_buff" in effect_tags: buffs["dt"] = POTION_SCALING["defense_buff"][tier]
    if "resistance_buff" in effect_tags: buffs["dr"] = POTION_SCALING["resistance_buff"][tier]
    if "evasion_buff" in effect_tags: buffs["eva"] = POTION_SCALING["evasion_buff"][tier]
    if "charisma_buff" in effect_tags: buffs["cha"] = POTION_SCALING["charisma_buff"][tier]

    cure_status = []
    if "cure_poison" in effect_tags: cure_status.append("Poisoned")
    if "cure_bleed" in effect_tags: cure_status.append("Bleeding")
    if "cleanse_all" in effect_tags: cure_status.extend(["Poisoned", "Bleeding", "Burned", "Stunned", "Corroded", "Frightened"])

    inflict_status = []
    damage = 0
    if "explosive_fire" in effect_tags:
        damage = POTION_SCALING["explosive_fire"][tier]
        inflict_status.append("Burned")
    elif "corrosive_acid" in effect_tags:
        damage = POTION_SCALING["corrosive_acid"][tier]
        inflict_status.append("Corroded")
    elif "toxic_cloud" in effect_tags:
        inflict_status.append("Poisoned")

    # Dynamic Name & Description
    name = generate_potion_name(genre, tier, effect_tags, purpose_tags)
    
    desc_parts = []
    if hp_val > 0: desc_parts.append(f"Restores {hp_val} HP")
    if mp_val > 0: desc_parts.append(f"Restores {mp_val} MP")
    if buffs:
        formatted_buffs = []
        for k, v in buffs.items():
            if k == "atk_pct":
                formatted_buffs.append(f"+{int(v * 100)}% ATK")
            elif k == "dr":
                formatted_buffs.append(f"+{int(v * 100)}% DR")
            elif k == "dt":
                formatted_buffs.append(f"+{v} DT")
            elif k == "eva":
                formatted_buffs.append(f"+{v}% EVA")
            else:
                formatted_buffs.append(f"+{v} {k.upper()}")
        b_str = ", ".join(formatted_buffs)
        desc_parts.append(f"Grants {b_str}")
    if cure_status:
        c_str = "all ailments" if "cleanse_all" in effect_tags else ", ".join(cure_status)
        desc_parts.append(f"Cleanses {c_str}")
    if damage > 0:
        desc_parts.append(f"Deals {damage} damage")
    if inflict_status:
        desc_parts.append(f"Inflicts {', '.join(inflict_status)}")

    effect_desc = " • ".join(desc_parts)

    meta = {
        "item_type": "Throwable" if "throwable" in purpose_tags else "Potion",
        "tier": tier,
        "purpose_tags": purpose_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "inflict_status": inflict_status,
        "damage": damage,
        "effect_desc": effect_desc
    }

    from mechanics.combat.merchant import calculate_balanced_price
    price = calculate_balanced_price("Potion", name, tier, genre)

    scen_key = normalize_consumable_scenario(genre)
    potion_taste = ["herb", "bitter"]
    if scen_key == "steampunk":
        potion_taste = ["copper", "steam", "bitter"]
    elif scen_key == "cyberpunk":
        potion_taste = ["chemical", "synthetic", "ozone"]
    elif scen_key == "post_apocalyptic":
        potion_taste = ["rads", "chemical", "bitter"]
    elif scen_key == "dark_fantasy":
        potion_taste = ["iron", "ash", "bitter"]
    elif scen_key == "high_school":
        potion_taste = ["citrus", "sweet"]

    return {
        "name": name,
        "item_type": meta["item_type"],
        "tier": tier,
        "price": price,
        "quantity": random.randint(1, 3),
        "purpose_tags": purpose_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "inflict_status": inflict_status,
        "damage": damage,
        "tags": {
            "consumable_type": "throwable" if "throwable" in purpose_tags else "potion",
            "delivery": "splash_aoe" if "throwable" in purpose_tags else "ingest",
            "purpose": purpose_tags,
            "effects": effect_tags,
            "taste": potion_taste if "throwable" not in purpose_tags else [],
            "damage_types": ["fire"] if "explosive_fire" in effect_tags else (["acid"] if "corrosive_acid" in effect_tags else [])
        },
        "effect": serialize_consumable_metadata(meta),
        "description": f"{effect_desc}."
    }


def generate_procedural_food(tier: int = 3, taste_tags: List[str] = None, effect_tags: List[str] = None, genre: str = "fantasy") -> Dict[str, Any]:
    """
    Generates a structured solid food item with explicit taste tags,
    purpose tags, numeric recovery, and genre-based name.
    """
    if taste_tags is None:
        if tier == 3:
            taste_tags = random.choice([["sweet", "bakery"], ["savory", "comfort"], ["savory", "crispy"], ["savory", "street"]])
        elif tier == 2:
            taste_tags = random.choice([["savory", "comfort"], ["sweet", "bakery"], ["seafood", "savory"], ["spicy", "comfort"]])
        else:
            taste_tags = random.choice([["savory", "luxury"], ["sweet", "luxury"], ["seafood", "luxury"]])

    if effect_tags is None:
        if tier == 3:
            effect_tags = ["healing"]
        elif tier == 2:
            effect_tags = random.choice([["healing"], ["healing", "attack_buff"], ["healing", "defense_buff"], ["healing", "morale_boost"]])
        else:
            effect_tags = random.choice([["healing", "cleanse_all"], ["healing", "charisma_buff", "morale_boost"]])

    purpose_tags = ["health", "sustenance", "gift"]
    if "sweet" in taste_tags: purpose_tags.append("dessert")
    if any("buff" in k for k in effect_tags): purpose_tags.append("buff")

    hp_val = FOOD_SCALING["healing"][tier] if "healing" in effect_tags else 0
    mp_val = FOOD_SCALING["mana_restore"][tier] if "mana_restore" in effect_tags else 0

    buffs = {}
    if "attack_buff" in effect_tags: buffs["atk_pct"] = FOOD_SCALING["attack_buff"][tier]
    if "defense_buff" in effect_tags: buffs["dt"] = FOOD_SCALING["defense_buff"][tier]
    if "resistance_buff" in effect_tags: buffs["dr"] = FOOD_SCALING["resistance_buff"][tier]
    if "charisma_buff" in effect_tags: buffs["cha"] = FOOD_SCALING["charisma_buff"][tier]

    cure_status = ["Poisoned", "Bleeding", "Burned", "Stunned", "Corroded", "Frightened"] if "cleanse_all" in effect_tags else []

    name = generate_food_name(genre, tier, taste_tags, effect_tags)

    desc_parts = []
    if hp_val > 0: desc_parts.append(f"Restores {hp_val} HP")
    if mp_val > 0: desc_parts.append(f"Restores {mp_val} MP")
    if buffs:
        formatted_buffs = []
        for k, v in buffs.items():
            if k == "atk_pct":
                formatted_buffs.append(f"+{int(v * 100)}% ATK")
            elif k == "dr":
                formatted_buffs.append(f"+{int(v * 100)}% DR")
            elif k == "dt":
                formatted_buffs.append(f"+{v} DT")
            else:
                formatted_buffs.append(f"+{v} {k.upper()}")
        b_str = ", ".join(formatted_buffs)
        desc_parts.append(f"Grants {b_str}")
    if cure_status:
        desc_parts.append("Cleanses all ailments")
    desc_parts.append(f"Taste: {', '.join(taste_tags).title()}")

    effect_desc = " • ".join(desc_parts)

    meta = {
        "item_type": "Food",
        "tier": tier,
        "purpose_tags": purpose_tags,
        "taste_tags": taste_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "damage": 0,
        "effect_desc": effect_desc
    }

    from mechanics.combat.merchant import calculate_balanced_price
    price = calculate_balanced_price("Food", name, tier, genre)

    return {
        "name": name,
        "item_type": "Food",
        "tier": tier,
        "price": price,
        "quantity": random.randint(1, 4),
        "purpose_tags": purpose_tags,
        "taste_tags": taste_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "damage": 0,
        "tags": {
            "consumable_type": "food",
            "delivery": "ingest",
            "purpose": purpose_tags,
            "effects": effect_tags,
            "taste": taste_tags,
            "social_flags": ["giftable", "shareable"]
        },
        "effect": serialize_consumable_metadata(meta),
        "description": f"{effect_desc}."
    }


def generate_procedural_drink(tier: int = 3, taste_tags: List[str] = None, effect_tags: List[str] = None, genre: str = "fantasy") -> Dict[str, Any]:
    """
    Generates a structured drink/beverage item with explicit beverage taste tags,
    purpose tags, numeric recovery (favors MP & focus), and genre-based name.
    """
    if taste_tags is None:
        if tier == 3:
            taste_tags = random.choice([["caffeine", "coffee"], ["tea", "refreshing"], ["soda", "fizzy"], ["juice", "citrus"], ["chilled", "refreshing"]])
        elif tier == 2:
            taste_tags = random.choice([["boba", "sweet"], ["caffeine", "creamy"], ["tea", "herbal"], ["alcohol", "spiced"], ["smoothie", "sweet"]])
        else:
            taste_tags = random.choice([["caffeine", "bitter"], ["alcohol", "aged"], ["tea", "ceremonial"], ["infused_water", "refreshing"]])

    if effect_tags is None:
        if tier == 3:
            effect_tags = random.choice([["mana_restore"], ["healing"], ["morale_boost"]])
        elif tier == 2:
            effect_tags = random.choice([
                ["mana_restore", "evasion_buff"],
                ["mana_restore", "charisma_buff"],
                ["healing", "mana_restore"],
                ["attack_buff", "morale_boost"] if "alcohol" in taste_tags else ["mana_restore", "morale_boost"]
            ])
        else:
            effect_tags = random.choice([
                ["mana_restore", "cleanse_all"],
                ["mana_restore", "charisma_buff", "evasion_buff"],
                ["healing", "mana_restore", "morale_boost"]
            ])

    purpose_tags = ["beverage", "hydration", "gift"]
    if "mana_restore" in effect_tags: purpose_tags.append("mana")
    if "healing" in effect_tags: purpose_tags.append("health")
    if any("buff" in k for k in effect_tags): purpose_tags.append("buff")

    hp_val = DRINK_SCALING["healing"][tier] if "healing" in effect_tags else 0
    mp_val = DRINK_SCALING["mana_restore"][tier] if "mana_restore" in effect_tags else (12 if "caffeine" in taste_tags else 0)

    buffs = {}
    if "attack_buff" in effect_tags: buffs["atk_pct"] = DRINK_SCALING["attack_buff"][tier]
    if "defense_buff" in effect_tags: buffs["dt"] = DRINK_SCALING["defense_buff"][tier]
    if "resistance_buff" in effect_tags: buffs["dr"] = DRINK_SCALING["resistance_buff"][tier]
    if "evasion_buff" in effect_tags: buffs["eva"] = DRINK_SCALING["evasion_buff"][tier]
    if "charisma_buff" in effect_tags: buffs["cha"] = DRINK_SCALING["charisma_buff"][tier]

    cure_status = ["Poisoned", "Bleeding", "Burned", "Stunned", "Corroded", "Frightened"] if "cleanse_all" in effect_tags else []

    name = generate_drink_name(genre, tier, taste_tags, effect_tags)

    desc_parts = []
    if hp_val > 0: desc_parts.append(f"Restores {hp_val} HP")
    if mp_val > 0: desc_parts.append(f"Restores {mp_val} MP")
    if buffs:
        formatted_buffs = []
        for k, v in buffs.items():
            if k == "atk_pct":
                formatted_buffs.append(f"+{int(v * 100)}% ATK")
            elif k == "dr":
                formatted_buffs.append(f"+{int(v * 100)}% DR")
            elif k == "dt":
                formatted_buffs.append(f"+{v} DT")
            elif k == "eva":
                formatted_buffs.append(f"+{v}% EVA")
            else:
                formatted_buffs.append(f"+{v} {k.upper()}")
        b_str = ", ".join(formatted_buffs)
        desc_parts.append(f"Grants {b_str}")
    if cure_status:
        desc_parts.append("Cleanses all ailments")
    desc_parts.append(f"Taste: {', '.join(taste_tags).title()}")

    effect_desc = " • ".join(desc_parts)

    meta = {
        "item_type": "Drink",
        "tier": tier,
        "purpose_tags": purpose_tags,
        "taste_tags": taste_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "damage": 0,
        "effect_desc": effect_desc
    }

    from mechanics.combat.merchant import calculate_balanced_price
    price = calculate_balanced_price("Drink", name, tier, genre)

    return {
        "name": name,
        "item_type": "Drink",
        "tier": tier,
        "price": price,
        "quantity": random.randint(1, 4),
        "purpose_tags": purpose_tags,
        "taste_tags": taste_tags,
        "effect_tags": effect_tags,
        "hp_restore": hp_val,
        "mp_restore": mp_val,
        "buffs": buffs,
        "cure_status": cure_status,
        "damage": 0,
        "tags": {
            "consumable_type": "drink",
            "delivery": "ingest",
            "purpose": purpose_tags,
            "effects": effect_tags,
            "taste": taste_tags,
            "social_flags": ["giftable", "shareable"]
        },
        "effect": serialize_consumable_metadata(meta),
        "description": f"{effect_desc}."
    }




def classify_and_enrich_ad_hoc_item(item_name: str, scenario_key: str = "fantasy") -> dict:
    """
    Classifies an ad-hoc item name produced during gameplay and enriches it with
    proper item_type, structured metadata (effect), equipment slot, and slot_cost.
    """
    raw_name = (item_name or "Item").strip()
    name_low = raw_name.lower()

    # Determine item tier
    tier = 3
    if any(w in name_low for w in ["legendary", "mythic", "ancient", "celestial", "demonic", "divine", "relic", "godly", "prismatic"]):
        tier = 1
    elif any(w in name_low for w in ["masterwork", "enchanted", "superior", "fine", "reinforced", "sharp", "glowing", "runic", "blessed", "refined", "sturdy", "expert", "high-grade"]):
        tier = 2

    # Check Digital Media Collectible
    from mechanics.system.phone import scenario_has_smartphone
    if scenario_has_smartphone(scenario_key) and any(k in name_low for k in ("photo", "selfie", "video", "snapshot", "recording", "clip")):
        return {
            "name": raw_name,
            "item_type": "Digital Media",
            "effect": f"[DIGITAL_JSON]{{\"media_type\": \"photo\", \"caption\": \"{raw_name}\"}}",
            "slot": None,
            "slot_cost": 0,
            "tier": tier
        }

    # Check Potions / Consumables
    potion_kws = (
        "potion", "elixir", "draught", "tincture", "vial of", "brew", "serum", "tonic",
        "flask of", "salve", "remedy", "inhaler", "stim", "stimpak", "injector", "ampoule",
        "smelling salts", "rad-away", "rad-x", "chems", "phial"
    )
    if any(k in name_low for k in potion_kws):
        purpose = "healing"
        eff_tag = "healing"
        if any(w in name_low for w in ["mana", "spirit", "ether", "mind", "intellect"]):
            purpose = "mana"
            eff_tag = "mana_restore"
        elif any(w in name_low for w in ["strength", "might", "power", "attack", "fury", "berserk"]):
            purpose = "buff"
            eff_tag = "attack_buff"
        elif any(w in name_low for w in ["iron", "stone", "defense", "shield", "ward", "armor"]):
            purpose = "buff"
            eff_tag = "defense_buff"
        elif any(w in name_low for w in ["speed", "swift", "agility", "evasion", "haste"]):
            purpose = "buff"
            eff_tag = "evasion_buff"
        elif any(w in name_low for w in ["cure", "antidote", "cleanse", "purify"]):
            purpose = "cure"
            eff_tag = "cleanse_all"

        scale_dict = POTION_SCALING.get(eff_tag, {3: 35, 2: 65, 1: 150})
        amount = scale_dict.get(tier, 35)

        buffs = {}
        if eff_tag == "attack_buff":
            buffs["atk_pct"] = amount
        elif eff_tag == "defense_buff":
            buffs["dt"] = amount
        elif eff_tag == "resistance_buff":
            buffs["dr"] = amount
        elif eff_tag == "evasion_buff":
            buffs["eva"] = amount

        scen_k = normalize_consumable_scenario(scenario_key)
        pot_taste = "herb"
        if scen_k == "steampunk": pot_taste = "copper"
        elif scen_k == "cyberpunk": pot_taste = "chemical"
        elif scen_k == "post_apocalyptic": pot_taste = "rads"
        elif scen_k == "dark_fantasy": pot_taste = "iron"
        elif scen_k == "high_school": pot_taste = "citrus"

        meta = {
            "name": raw_name,
            "item_type": "Potion",
            "tier": tier,
            "purpose_tags": [purpose],
            "effect_tags": [eff_tag],
            "taste_tags": [pot_taste],
            "hp_restore": amount if eff_tag == "healing" else 0,
            "mp_restore": amount if eff_tag == "mana_restore" else 0,
            "buffs": buffs,
            "buff_values": {eff_tag: amount} if "buff" in eff_tag else {}
        }
        return {
            "name": raw_name,
            "item_type": "Potion",
            "effect": serialize_consumable_metadata(meta),
            "slot": None,
            "slot_cost": 1,
            "tier": tier
        }

    # Check Drinks & Beverages
    drink_kws = (
        "tea", "coffee", "latte", "boba", "cider", "ale", "wine", "beer", "mead", "juice",
        "soda", "ramune", "smoothie", "espresso", "water", "beverage", "cocktail", "cordial",
        "fizz", "hydrator", "absinthe", "bourbon", "whiskey", "vodka", "moonshine", "seltzer",
        "stout", "gin", "rum", "liqueur", "lager"
    )
    if any(k in name_low for k in drink_kws):
        taste = "refreshing"
        if any(w in name_low for w in ["boba", "milk tea", "sweet"]):
            taste = "sweet"
        elif any(w in name_low for w in ["coffee", "espresso", "caff"]):
            taste = "caffeine"
        elif any(w in name_low for w in ["tea", "matcha", "oolong", "jasmine", "herbal"]):
            taste = "tea"
        elif any(w in name_low for w in ["wine", "ale", "beer", "mead", "cocktail", "scotch", "absinthe", "bourbon", "whiskey", "vodka", "moonshine", "stout", "gin", "rum", "liqueur", "lager"]):
            taste = "alcohol"
        elif any(w in name_low for w in ["soda", "fizz", "ramune", "seltzer"]):
            taste = "fizzy"
        elif any(w in name_low for w in ["juice", "citrus", "orange", "lemon"]):
            taste = "citrus"

        drink_heal = DRINK_SCALING["healing"].get(tier, 10)
        drink_mana = DRINK_SCALING["mana_restore"].get(tier, 18)
        meta = {
            "name": raw_name,
            "item_type": "Drink",
            "tier": tier,
            "purpose_tags": ["beverage", "hydration"],
            "effect_tags": ["mana_restore", "healing"],
            "taste_tags": [taste],
            "hp_restore": drink_heal,
            "mp_restore": drink_mana,
            "buffs": {},
            "cure_status": [],
            "damage": 0
        }
        return {
            "name": raw_name,
            "item_type": "Drink",
            "effect": serialize_consumable_metadata(meta),
            "slot": None,
            "slot_cost": 1,
            "tier": tier
        }

    # Check Foods (Solid)
    food_kws = (
        "bento", "lunch", "snack", "bread", "apple", "sandwich", "soup", "curry", "pie",
        "cake", "cookie", "chocolate", "ramen", "burger", "rice", "onigiri", "pastry",
        "candy", "biscuit", "meat", "roast", "fruit", "dumpling", "steak", "tart",
        "melon pan", "roll", "skewer", "jerky", "hardtack", "loaf", "sausage", "porridge"
    )
    if any(k in name_low for k in food_kws):
        taste = "comfort"
        if any(w in name_low for w in ["sweet", "cake", "cookie", "chocolate", "pie", "candy", "tart"]):
            taste = "sweet"
        elif any(w in name_low for w in ["spicy", "curry", "pepper", "chili"]):
            taste = "spicy"
        elif any(w in name_low for w in ["bento", "ramen", "burger", "meat", "roast", "dumpling", "sandwich", "steak", "skewer", "jerky", "sausage"]):
            taste = "savory"

        food_heal = FOOD_SCALING["healing"].get(tier, 15)
        meta = {
            "name": raw_name,
            "item_type": "Food",
            "tier": tier,
            "purpose_tags": ["health", "sustenance"],
            "effect_tags": ["healing"],
            "taste_tags": [taste],
            "hp_restore": food_heal,
            "mp_restore": FOOD_SCALING["mana_restore"].get(tier, 10),
            "buffs": {},
            "cure_status": [],
            "damage": 0
        }
        return {
            "name": raw_name,
            "item_type": "Food",
            "effect": serialize_consumable_metadata(meta),
            "slot": None,
            "slot_cost": 1,
            "tier": tier
        }

    # Check Key Items
    key_kws = ("key", "keycard", "pass", "note", "letter", "envelope", "scroll", "tome", "diary", "journal", "map", "token", "student id", "permit", "cipher", "blueprint", "document", "badge", "certificate", "sample", "reagent", "calculator", "evidence", "ledger", "manifest", "report")
    if any(k in name_low for k in key_kws) and not any(w in name_low for w in ["ring", "necklace", "amulet"]):
        return {
            "name": raw_name,
            "item_type": "Key Item",
            "effect": f"Important narrative item: {raw_name}",
            "slot": None,
            "slot_cost": 0,
            "tier": tier
        }

    # Check Equipment (Weapons, Armors, Shields, Accessories)
    from mechanics.combat.equipment import parse_equipment_metadata, build_equipment_effect_str
    weapon_kws = ("sword", "blade", "dagger", "knife", "axe", "mace", "bow", "crossbow", "staff", "wand", "spear", "halberd", "rapier", "hammer", "pistol", "revolver", "rifle", "shotgun", "katana", "shinai", "bokken", "baton", "club", "lance", "scythe", "greatsword")
    shield_kws = ("shield", "buckler", "aegis", "targe", "pavise")
    accessory_kws = ("ring", "amulet", "necklace", "charm", "earring", "bracelet", "pendant", "badge", "ribbon", "watch", "glasses", "pin", "scarf", "hairpin", "locket", "band", "brooch", "talisman")
    top_kws = ("armor", "tunic", "jacket", "coat", "robe", "shirt", "blazer", "uniform", "vest", "cloak", "hoodie", "cardigan", "hauberk", "cuirass", "mail")
    bottom_kws = ("pants", "trousers", "skirt", "jeans", "shorts", "slacks", "leggings", "greaves")
    gloves_kws = ("gloves", "gauntlets", "mitts", "bracers")
    shoes_kws = ("boots", "shoes", "sneakers", "loafers", "sandals", "oxford", "oxfords", "heels", "slippers")

    slot = None
    item_type = None

    if any(k in name_low for k in weapon_kws):
        item_type = "Weapon"
        slot = "Weapon"
    elif any(k in name_low for k in shield_kws):
        item_type = "Shield"
        slot = "Shield"
    elif any(k in name_low for k in accessory_kws):
        item_type = "Accessory"
        slot = "Accessory"
    elif any(k in name_low for k in top_kws):
        item_type = "Armor"
        slot = "Top"
    elif any(k in name_low for k in bottom_kws):
        item_type = "Armor"
        slot = "Bottom"
    elif any(k in name_low for k in gloves_kws):
        item_type = "Armor"
        slot = "Gloves"
    elif any(k in name_low for k in shoes_kws):
        item_type = "Armor"
        slot = "Shoes"

    if item_type and slot:
        dummy_item = {"name": raw_name, "item_type": item_type, "slot": slot}
        meta = parse_equipment_metadata(dummy_item)
        meta["tier"] = tier
        meta["tier_name"] = {1: "Legendary", 2: "Enchanted", 3: "Standard"}.get(tier, "Standard")
        meta["slot"] = slot
        meta["item_type"] = item_type
        if tier == 2:
            for s_key in meta.get("stat_modifiers", {}):
                meta["stat_modifiers"][s_key] = int(meta["stat_modifiers"][s_key] * 1.5) + 3
        elif tier == 1:
            for s_key in meta.get("stat_modifiers", {}):
                meta["stat_modifiers"][s_key] = int(meta["stat_modifiers"][s_key] * 2.2) + 8

        effect_str = build_equipment_effect_str(meta)
        return {
            "name": raw_name,
            "item_type": item_type,
            "effect": effect_str,
            "slot": slot,
            "slot_cost": 1,
            "tier": tier
        }

    # Fallback to general Item
    return {
        "name": raw_name,
        "item_type": "Item",
        "effect": f"Gained during adventure: {raw_name}",
        "slot": None,
        "slot_cost": 1,
        "tier": tier
    }
