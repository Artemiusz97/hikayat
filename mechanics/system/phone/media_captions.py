import random

def generate_npc_photo_caption(contact: dict, intent: str = "nsfw_photo", location: str = "") -> str:
    """Fallback & template generator for NPC photo/video descriptions tailored to personality traits and role."""
    contact_name = contact.get("name", "Contact")
    traits = [str(t).lower() for t in (contact.get("unlocked_traits") or contact.get("basic_info", {}).get("traits") or [])]
    role = str(contact.get("basic_info", {}).get("role") or "").lower()

    is_athletic = any(t in traits or t in role for t in ("athletic", "sporty", "jock", "runner", "gym", "fitness", "swimmer", "captain"))
    is_studious = any(t in traits or t in role for t in ("studious", "bookworm", "intellectual", "scholar", "librarian", "academic", "class rep"))
    is_artistic = any(t in traits or t in role for t in ("artistic", "creative", "artist", "musician", "painter", "writer", "poet"))
    is_shy = any(t in traits or t in role for t in ("shy", "quiet", "reserved", "introvert", "timid", "modest"))
    is_confident = any(t in traits or t in role for t in ("confident", "bold", "outgoing", "popular", "charming", "flirtatious", "extrovert"))

    if intent in ("video", "nsfw_video"):
        if "nsfw" in intent:
            captions = [
                f"A private, sultry 10-second video clip of {contact_name} lounging on soft bedsheets, smiling softly and running fingers through hair with a teasing glance",
                f"A short video clip of {contact_name} in relaxed silk loungewear, posing playfully in warm ambient lighting and blowing a gentle kiss to the camera",
                f"A candid video snapshot of {contact_name} catching golden hour light, spinning slowly with an alluring smile",
                f"A steamy 8-second video clip of {contact_name} by the bathroom mirror with damp hair, casting a sultry gaze over one bare shoulder"
            ]
        else:
            if is_athletic:
                captions = [
                    f"A quick 5-second video clip of {contact_name} catching their breath on the running track, wiping their brow and giving an energetic wave",
                    f"A high-energy clip of {contact_name} doing warm-up stretches under the sun, smiling cheerfully at the camera"
                ]
            elif is_studious:
                captions = [
                    f"A quiet 6-second video showing rain trickling down the library window, {contact_name} turning the page of a book and smiling softly",
                    f"A short clip of {contact_name} stirring an iced latte next to a tall stack of study notes, whispering a quiet greeting"
                ]
            elif is_artistic:
                captions = [
                    f"A time-lapse snippet of {contact_name} sketching a detailed courtyard scene, turning to flash a paint-speckled grin",
                    f"A peaceful video clip panning across vibrant autumn foliage and sketching pads on an outdoor stone bench"
                ]
            elif is_shy:
                captions = [
                    f"A short video clip of a friendly stray cat napping peacefully in the courtyard, {contact_name}'s gentle laugh audible in the background",
                    f"A quick video of afternoon sunlight filtering through tree canopies, {contact_name} offering a shy, brief wave at the edge of the frame"
                ]
            else:
                captions = [
                    f"A quick 5-second video clip showing {contact_name} waving cheerfully from {location or 'around campus'}, smiling warmly",
                    f"A short, high-energy video snippet of {contact_name} laughing and showing off the lively surroundings",
                    f"A warm video message from {contact_name} smiling brightly into the lens and wishing you a great day"
                ]
        return random.choice(captions)

    if intent in ("photo", "photo_ask"):
        if is_athletic:
            captions = [
                f"A post-workout selfie of {contact_name} holding a water bottle, glowing under the afternoon sun on the bleachers with an energetic smile",
                f"A candid snapshot of {contact_name}'s running shoes, gym bag, and fitness tracker resting on the track bench",
                f"A sunny selfie of {contact_name} in athletic wear, hair tied back, giving a cheerful thumbs-up"
            ]
        elif is_studious:
            captions = [
                f"A cozy snapshot of {contact_name}'s study desk with neatly highlighted notes, a pair of reading glasses, and an iced latte",
                f"A candid library photo of {contact_name} peering over a towering stack of reference books with an amused, studious smile",
                f"A scenic shot of rain gently pattering against the tall library window next to an open notebook"
            ]
        elif is_artistic:
            captions = [
                f"A photo of {contact_name}'s watercolor palette and an expressive sketch of the campus courtyard bathed in golden light",
                f"A candid snapshot of {contact_name} sitting on the lawn with charcoal-dusted fingers, smiling up at the camera",
                f"An artsy perspective shot of afternoon shadows stretching across the garden stone pathway"
            ]
        elif is_shy:
            captions = [
                f"A close-up photo of a sweet calico campus cat curled up sleeping on a sunlit bench",
                f"A scenic photo of warm afternoon light casting soft shadows across the quiet courtyard fountain",
                f"A shy over-the-shoulder snapshot of {contact_name} peeking from behind an oversized scarf with a gentle smile",
                f"A lovely picture of a warm cup of herbal tea and freshly baked pastry at a quiet corner table"
            ]
        elif is_confident:
            captions = [
                f"A radiant, stylish selfie of {contact_name} smiling warmly into the lens under bright blue skies",
                f"A playful mirror selfie of {contact_name} showing off today's outfit with a wink",
                f"A charming snapshot of {contact_name} leaning against the terrace railing, eyes sparkling in the afternoon breeze"
            ]
        else:
            captions = [
                f"A bright and sunny selfie of {contact_name} at {location or 'a quiet spot'}, smiling warmly with a refreshing drink in hand",
                f"A casual over-the-shoulder snapshot of {contact_name} enjoying the fresh air and relaxed downtime",
                f"A candid snapshot of {contact_name} looking directly into the lens with a happy, radiant smile",
                f"A scenic photo of the tranquil campus courtyard gardens bathed in soft natural daylight",
                f"A photo of today's delicious cafeteria lunch and an iced tea resting on a clean wooden table"
            ]
        return random.choice(captions)

    # nsfw_photo / spicy_ask
    captions = [
        f"A sultry bedroom mirror selfie of {contact_name} in an oversized button-down shirt unbuttoned halfway and slipping off bare shoulders",
        f"A candid bed snapshot of {contact_name} in a cropped baby tee pulled up playfully and relaxed loungewear slung low on the hips",
        f"A steamy bathroom selfie of {contact_name} with damp hair wrapped in a soft towel, casting an alluring glance into the camera",
        f"A warm-lit bedside photo of {contact_name} in an unzipped oversized hoodie teasing bare skin underneath, resting on one elbow",
        f"A daring top-down bed selfie of {contact_name} reclining completely nude with white sheets pulled tantalizingly low along the hips",
        f"A steamy mirror selfie of {contact_name} freshly stepped out of the shower, holding up a dropped towel with a flirtatious wink",
        f"A playful photo of {contact_name} in an off-the-shoulder knit sweater falling over bare thighs, smiling with bedroom eyes",
        f"An alluring silhouette snapshot of {contact_name} bathed in soft moonlight by the window, hands teasingly tracing bare collarbones",
    ]
    return random.choice(captions)


def generate_player_casual_photo(location: str = "") -> dict:
    """Generates a randomized casual photo/video from the player to send to an NPC contact."""
    category = random.choice(["selfie", "scenery", "object"])
    loc_str = location or "around campus"

    if category == "selfie":
        captions = [
            f"A casual, relaxed selfie under the shade of the courtyard trees, giving a warm easy smile",
            f"A quick mirror selfie while taking a breather, looking directly into the lens with a friendly grin",
            f"An over-the-shoulder selfie catching the natural golden hour light at {loc_str}",
            f"A cheerful candid selfie holding up a peace sign with a relaxed smile"
        ]
    elif category == "scenery":
        captions = [
            f"A scenic photo of golden sunlight reflecting off the fountain waters and stone pathways at {loc_str}",
            f"A tranquil view of the campus skyline and drifting clouds from the terrace railing",
            f"A beautiful snapshot of the tree-lined campus walkway bathed in warm afternoon shadows",
            f"A serene photo looking out the high windows at the quiet gardens outside"
        ]
    else:  # object
        captions = [
            f"A photo of a steaming cup of artisan coffee and a freshly baked pastry from the local cafe",
            f"A picture of a friendly campus cat curled up sleeping peacefully in a patch of sunlight",
            f"A photo of an interesting vintage book and notebook spread out on a wooden study table",
            f"A snapshot of delicious snacks and a refreshing drink picked up while out and about"
        ]

    chosen_caption = random.choice(captions)
    return {
        "media_type": "photo",
        "category": category,
        "caption": chosen_caption,
        "display_text": f"[Attached Photo: {chosen_caption}]"
    }


def generate_player_spicy_photo(char: dict) -> dict:
    """Generates a randomized intimate/spicy photo from the player to send to an NPC contact."""
    gender = (char.get("gender") or "neutral").lower() if char else "neutral"

    if "f" in gender:
        subtypes = [
            ("lingerie", "A bedroom mirror selfie wearing delicate lace lingerie, glancing back over bare shoulders with a teasing smile"),
            ("towel", "A steamy post-shower vanity selfie wrapped in a loosely tucked towel, damp hair resting against bare collarbones"),
            ("shirt", "A bedroom bed selfie wearing an unbuttoned oversized dress shirt slipping off bare shoulders, biting lip playfully"),
            ("risque", "Lounging across tangled sheets in a cropped tank top pulled up teasingly and unbuttoned low-rise denim shorts"),
            ("nude", "A daring high-angle bed selfie lying completely nude across tangled silk sheets with strategic shadows draped low along the hips")
        ]
    elif "m" in gender:
        subtypes = [
            ("boxers", "A bold mirror selfie showing off a defined, toned physique in low-slung boxer-briefs, smiling playfully into the camera"),
            ("towel", "Fresh out of the shower with damp hair, a dark towel slung dangerously low on the hips, smirking confidently at the camera"),
            ("unbuttoned", "Laying relaxed across the bed with an unbuttoned linen shirt exposing chest and abs, giving a teasing wink"),
            ("sweatpants", "Leaning back against the headboard in relaxed sweatpants sitting low on the waist, casting an intense sultry gaze"),
            ("nude", "A daring bed selfie reclining completely bare with white sheets pulled teasingly low across the hips, smirking into the lens")
        ]
    else:
        subtypes = [
            ("loungewear", "An alluring mirror selfie showing bare skin and a teasing, sultry glance under soft ambient bedroom lighting"),
            ("towel", "A steamy post-shower mirror selfie wrapped in a plush towel, hair still damp, offering a flirtatious wink"),
            ("robe", "Relaxing across tangled sheets in loosely tied silk loungewear slipping open, smirking playfully at the camera"),
            ("nude", "A daring high-angle bed selfie lounging across tangled sheets with bare skin bathed in soft golden ambient lighting")
        ]

    subtype, caption = random.choice(subtypes)
    return {
        "media_type": "nsfw_photo",
        "subtype": subtype,
        "caption": caption,
        "display_text": f"[Attached Intimate Photo: {caption}]"
    }


def generate_player_photo_caption(char: dict, intent: str = "nsfw_photo", location: str = "") -> str:
    """Generate dynamic photo captions for the player (backwards-compatible wrapper)."""
    if intent == "photo":
        return generate_player_casual_photo(location)["caption"]
    return generate_player_spicy_photo(char)["caption"]
