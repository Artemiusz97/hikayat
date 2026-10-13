# English (en) mechanics dictionary for Hikayat

ITEM_ICON_KEYWORDS = {
    # 0. Digital Media Items
    "digital_video": ("video", "clip", "recording"),
    "digital_photo": ("photo", "snapshot", "selfie"),
    
    # 1. Accessories
    "accessories": ("ring", "amulet", "bracelet", "necklace", "pendant"),
    "amulet": ("amulet", "necklace", "pendant", "rosary", "locket", "beads"),

    # 2. Weapons & Tools
    "phone": ("phone", "smartphone", "cellphone"),
    "backpack": ("backpack", "pack", "bag", "rucksack", "satchel"),
    "wand": ("wand", "staff", "stave", "rod", "scepter", "sceptre"),
    "grimoire": ("grimoire", "tome", "spellbook"),
    "bow": ("bow", "crossbow"),
    "gun": ("pistol", "rifle", "blaster", "gun", "revolver", "shotgun", "sniper"),
    "dagger": ("dagger", "knife", "blade", "cleaver", "scalpel", "stiletto"),
    "axe": ("axe", "hatchet"),
    "hammer": ("hammer", "mace", "warhammer", "club", "baton"),
    "spear": ("spear", "halberd", "lance", "trident", "pike"),
    "whip": ("whip", "chain"),
    "sword": ("sword", "greatsword", "rapier", "katana", "scimitar", "broadsword"),

    # 3. Clothing / Armor / Headwear
    "crown": ("crown", "coronet", "diadem", "tiara"),
    "glasses": ("glasses", "spectacles", "monocle", "visor", "goggles", "hud"),
    "top_hat": ("top hat", "fedora", "bowler hat", "trilby"),
    "helm": ("helm", "helmet", "cowl", "hood", "gas mask", "respirator", "sallet", "armet", "casque"),
    "cap": ("cap", "beanie", "snapback", "beret"),
    "boots": ("boots", "shoes", "sneakers", "sandals", "loafers", "sabatons", "treads", "footwear", "greaves", "creepers", "sliders"),
    "gloves": ("gloves", "gauntlets", "bracers", "mittens", "cuff", "hand wraps"),
    "pants": ("pants", "trousers", "leggings", "skirt", "slacks", "jeans", "shorts"),
    "armor": (
        "breastplate", "tunic", "robe", "chest", "cuirass", "mail", "chainmail",
        "ringmail", "scalemail", "shirt", "coat", "jacket", "suit", "vest", "blazer",
        "cardigan", "duster", "jumpsuit", "uniform", "windbreaker", "hoodie", "sweater",
        "parka", "cloak"
    ),
    "shield": ("shield", "aegis", "buckler"),

    # 4. Slot Type Fallbacks
    "slot_weapon": ("weapon",),
    "slot_shield": ("shield",),
    "slot_head": ("head", "helmet"),
    "slot_bottom": ("bottom",),
    "slot_gloves": ("gloves",),
    "slot_shoes": ("shoes",),
    "slot_top": ("top",),
    "slot_armor": ("armor",),

    # 5. Consumables & Quest Items
    "boba": ("boba", "bubble tea", "milk tea"),
    "coffee": ("coffee", "latte", "espresso", "cappuccino", "cold brew"),
    "tea": ("tea", "matcha", "oolong", "jasmine", "herbal infusion"),
    "wine": ("wine", "chalice"),
    "beer": ("ale", "beer", "cider", "mead"),
    "drink": ("soda", "fizz", "ramune", "smoothie", "juice", "drink", "cocktail", "water", "hydrator"),
    "food": (
        "bento", "ramen", "roast", "stew", "bread", "cake", "cookie", "tart", "pie",
        "snack", "meal", "omakase", "wagyu", "sandwich", "melon pan", "ration", "food", "feast"
    ),
    "health": ("health", "hp", "heal", "bandage", "salve", "stimpack"),
    "mana": ("mana", "mp", "elixir", "ether"),
    "potion": ("potion", "draught", "phial", "consumable"),
    "quest": (
        "key", "map", "letter", "tome", "book", "scroll", "signet", "chip", "card",
        "keycard", "deck", "terminal", "clipboard", "relic", "lantern", "quest", "key item"
    ),
}

TWO_HANDED_ARCHETYPES = (
    "greatsword", "polearm", "warhammer", "staff", "bow", "crossbow",
    "rifle", "shotgun", "machinegun", "explosive", "longsword", "halberd", "pike"
)

TWO_HANDED_KEYWORDS = (
    "greatsword", "halberd", "pike", "warhammer", "staff", "bow", "crossbow",
    "rifle", "shotgun", "machine gun", "cannon", "rocket", "two-handed", "2h"
)

ENEMY_AFFIXES = {
    "Volatile": "Volatile",
    "Overclocked": "Overclocked",
    "Vampiric": "Vampiric",
    "Phasing": "Phasing",
    "Corrosive": "Corrosive",
    "Grounded": "Grounded",
    "Hydro-Shielded": "Hydro-Shielded",
    "Tempest-Wreathed": "Tempest-Wreathed",
}

DIALOGUE_EXIT_PHRASES = (
    "say goodbye", "take your leave", "part ways", "excuse your", "excuse yourself",
    "leave the conversation", "end the conversation", "wrap up the chat", "step away",
    "bid farewell", "head back to class", "return to what you were doing",
    "walk away", "exit conversation", "farewell"
)

DIALOGUE_INIT_PREFIXES = (
    "speak with ", "speak to ", "talk to ", "talk with ", "consult the ", "consult with ",
    "address the ", "converse with ", "greet ", "chat with ",
    "strike up a conversation with ", "approach and speak with ", "approach and talk to ",
    "approach and greet ", "say hello to ", "say hi to ", "say hello", "say hi",
    "wave to ", "wave at ", "wave towards ", "wave toward ", "call over "
)

MOVEMENT_PREFIXES = (
    "travel to ", "travel toward ", "travel towards ", "travel through ", "travel into ",
    "head to ", "head toward ", "head towards ", "head into ",
    "walk to ", "walk toward ", "walk towards ", "walk into ", "walk through ",
    "journey to ", "journey toward ", "journey towards ", "depart toward ",
    "step into ", "step through ", "enter the ", "enter ", "visit the ", "visit ",
    "go to ", "move to ", "move into ", "return to ", "leave for ", "make our way to ",
    "make your way to ", "make my way to ", "slip into ", "slip to "
)
